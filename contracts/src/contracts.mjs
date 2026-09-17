import { CONSUMER } from '../../consumer/consumer.mjs';
import { resolveCodexProfile } from '../../runtime/src/codex-profile.mjs';
import { CR_DEFINITION, extractExecutableCr, validateStructuredCr } from './executable-cr.mjs';

export const ALLOWED_REPOSITORY = CONSUMER.repository;
export const REVIEW_ACTOR = CONSUMER.reviewerApp.expectedActor;
export const REVIEW_STATE = "CHANGES_REQUESTED";
export const BASE_BRANCH = CONSUMER.baseBranch;
export const REQUIRED_CONTRACT_KEYS = Object.freeze([
  "schema_version", "change_request_id", "repository", "pull_request",
  "reviewed_head_sha", "required_starting_head", "remediation_thread_title",
  "finding_ids", "required_validation", "success_token", "blocked_token"
]);

export class RemediationBlockedError extends Error {
  constructor(code, message, details = {}) { super(message); this.name = "RemediationBlockedError"; this.code = code; this.details = details; }
}

const sha = value => typeof value === "string" && /^[0-9a-f]{40}$/i.test(value);
const digest = value => typeof value === "string" && /^[0-9a-f]{64}$/i.test(value);
const nonEmpty = (value, field) => {
  if (typeof value !== "string" || value.trim() === "") throw new RemediationBlockedError("MALFORMED_CONTRACT", `${field} must be non-empty`);
  return value.trim();
};
const placeholder = value => /^(?:<[^>]+>|TODO|TBD|unknown|pending|n\/a)$/i.test(String(value).trim());

const findingIdPattern = /\b(?:F\d+|(?:F|CR|T)\-[A-Z0-9]+(?:\-[A-Z0-9]+)+)\b/g;
const findingIdValue = /^(?:F\d+|(?:F|CR|T)\-[A-Z0-9]+(?:\-[A-Z0-9]+)+)$/;

export function extractHumanFindingIds(body) {
  return [...new Set([...String(body).matchAll(/(?:^|\n)\s*(?:#{1,6}\s+|[-*+]\s+|[0-9]+[.)]\s+)[*`]*((?:F[0-9]+|[FCT]-[A-Z0-9]+(?:-[A-Z0-9]+)+|CR[0-9]+-F[0-9]+))\b/g)].map(m => m[1]))];
}

export function extractFindingIds(body) {
  return extractHumanFindingIds(body);
}

function parseScalar(raw) {
  const value = raw.trim();
  if (value === "true") return true;
  if (value === "false") return false;
  if (/^\d+$/.test(value)) return Number(value);
  if ((value.startsWith("\"") && value.endsWith("\"")) || (value.startsWith("'") && value.endsWith("'"))) return value.slice(1, -1);
  if (value.startsWith("[") && value.endsWith("]")) {
    return value.slice(1, -1).split(",").map(item => item.trim()).filter(Boolean).map(parseScalar);
  }
  return value;
}

function parseYamlContract(text) {
  const result = {};
  for (const line of text.split(/\r?\n/)) {
    if (!line.trim() || /^\s*#/.test(line)) continue;
    if (/^\s/.test(line)) throw new RemediationBlockedError("CONTRACT_NESTING", "Remediation contract must contain only top-level scalar or inline-array fields");
    const match = line.match(/^([^:#][^:]*):(?:\s*)(.*)$/);
    if (!match) throw new RemediationBlockedError("CONTRACT_YAML_INVALID", "Remediation contract contains a malformed YAML line");
    const key = match[1].trim();
    if (Object.hasOwn(result, key)) throw new RemediationBlockedError("CONTRACT_DUPLICATE_KEY", `Duplicate remediation contract key: ${key}`);
    result[key] = parseScalar(match[2]);
  }
  return result;
}

function assertSafeText(value, field, max = 512) {
  nonEmpty(value, field);
  if (String(value).length > max || String(value).includes("\uFFFD") || /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/.test(String(value))) {
    throw new RemediationBlockedError("CONTRACT_TEXT_INVALID", `${field} contains malformed Unicode/control data or is oversized`);
  }
  if (placeholder(value)) throw new RemediationBlockedError("CONTRACT_PLACEHOLDER", `${field} contains a placeholder`);
}

function assertUnique(values, field) {
  if (new Set(values).size !== values.length) throw new RemediationBlockedError("CONTRACT_DUPLICATE_VALUE", `${field} must not contain duplicate values`);
}

function nativeValidationSet(body) {
  const text = `${sectionText(body, "Required validation")}\n${sectionText(body, "Validation")}`.toLowerCase();
  const checks = [];
  const add = (needle, value) => { if (text.includes(needle)) checks.push(value); };
  add("routing", "routing-tests");
  add("issue writer", "issue-writer-tests");
  add("remediation", "remediation-tests");
  add("reviewer", "rust-reviewer-tests-format");
  add("diagnostic", "diagnostics-tests");
  add("launcher", "diagnostics-tests");
  add("ansible", "ansible-tests");
  add("workflow", "workflow-static");
  add("static", "workflow-static");
  add("yaml", "workflow-static");
  add("bash", "workflow-static");
  add("git diff", "diff-check");
  add("secret", "secret-scan");
  add("exact-head github", "github-test-validate");
  if (text.includes("github") && text.includes("validation")) checks.push("github-test-validate");
  return [...new Set(checks)];
}

function deriveNativeContract(body, canonicalIssueBody) {
  if (typeof canonicalIssueBody !== "string" || canonicalIssueBody.length === 0) throw new RemediationBlockedError("CURRENT_TASK_AUTHORITY_MISSING", "Current native Change Request requires the live canonical Issue body");
  const metadata = body;
  const profile = body;
  const start = body;
  const outcome = `${sectionText(body, "Completion and publication requirements")}\n${sectionText(body, "Completion outcome")}\n${sectionText(body, "Outcome")}`;

  const changeRequestId = inlineValue(metadata, ["Change Request ID"]);
  const repository = inlineValue(metadata, ["Target repository"]);
  const pullRequest = inlineValue(metadata, ["Target pull request"]);
  const reviewedHead = inlineValue(metadata, ["Reviewed head SHA"]);
  const requiredStart = inlineValue(start, ["Required starting head", "Required starting/reviewed head"]) ?? inlineValue(profile, ["Required starting head", "Required starting/reviewed head"]);
  const remediationThreadTitle = inlineValue(profile, ["Thread name"]);
  const codexModel = inlineValue(profile, ["Codex model"]);
  const codexEffort = inlineValue(profile, ["Codex reasoning effort"]);
  const subagents = inlineValue(profile, ["Subagents"]);
  const successToken = outcome.match(/(?:Allowed\s+)?success(?:\s+token)?\s*:\s*`([^`]+)`/i)?.[1]
    ?? outcome.match(/Expected successful remediation outcome\s*:\s*`([^`]+)`/i)?.[1];
  const blockedToken = outcome.match(/(?:Allowed\s+)?blocked(?:\s+token)?\s*:\s*`([^`]+)`/i)?.[1];
  const missing = [
    ["change_request_id", changeRequestId], ["repository", repository], ["pull_request", pullRequest],
    ["reviewed_head_sha", reviewedHead], ["required_starting_head", requiredStart],
    ["remediation_thread_title", remediationThreadTitle],

  ].filter(([, value]) => !value).map(([name]) => name);
  if (missing.length > 0) {
    throw new RemediationBlockedError("CURRENT_METADATA_MISSING", "Current native Change Request is missing executable metadata", { missing });
  }
  const findingIds = extractHumanFindingIds(body);
  const requiredValidation = nativeValidationSet(body);
  if (requiredValidation.length === 0) throw new RemediationBlockedError("CURRENT_VALIDATION_MISSING", "Current native Change Request does not declare executable validation");
  return {
    schema_version: "1.0",
    change_request_id: changeRequestId,
    repository,
    pull_request: Number(pullRequest.replace(/^#/, "")),
    reviewed_head_sha: reviewedHead,
    required_starting_head: requiredStart,
    remediation_thread_title: remediationThreadTitle,
    codex_model: codexModel,
    codex_effort: codexEffort,
    subagents_allowed: subagents === undefined ? false : /^(enabled|on|true)$/i.test(subagents) ? true
      : /^(disabled|off|false)$/i.test(subagents) ? false : subagents,
    finding_ids: findingIds,
    required_validation: requiredValidation,
    success_token: successToken ?? "REMEDIATED_PENDING_REVIEW",
    blocked_token: blockedToken ?? "REMEDIATION_BLOCKED"
  };
}

export function extractRemediationContract(body, { canonicalIssueBody } = {}) {
  if (typeof body !== "string" || body.length > 100000) throw new RemediationBlockedError("REVIEW_BODY_INVALID", "Native Change Request body is missing or oversized");
  const executable = extractExecutableCr(body);
  if (executable) return executable;
  const blocks = [...body.matchAll(/```ya?ml\s*\n([\s\S]*?)\n```/gi)].map(match => match[1]);
  const candidates = blocks.filter(block => /(^|\n)\s*schema_version\s*:/m.test(block));
  if (candidates.length === 1) return parseYamlContract(candidates[0]);
  if (candidates.length > 1) throw new RemediationBlockedError("CONTRACT_COUNT_INVALID", "Exactly one remediation execution contract is required");
  return deriveNativeContract(body, canonicalIssueBody);
}


function sectionText(body, heading) {
  const sections = String(body).split(/(?=^#{1,6}\s)/m);
  const normal = s => s.replace(/[#*`]/g, '').trim().toLowerCase();
  return sections.find(s => normal(s.split('\n')[0]) === normal(heading)) ?? '';
}
function inlineValue(body, labels) {
  const values = [];
  for (const line of String(body).split(/\r?\n/)) {
    const plain = line.replace(/^[ \t]*(?:[-*+]\s*)?/, '').replace(/[*`]/g, '').trim();
    const colon = plain.indexOf(':');
    if (colon < 0) continue;
    if (labels.some(label => label.toLowerCase() === plain.slice(0, colon).trim().toLowerCase())) values.push(plain.slice(colon+1).trim());
  }
  const unique = [...new Set(values)];
  if (unique.length > 1) throw new RemediationBlockedError('CONTRACT_VALUE_AMBIGUOUS', 'Conflicting executable field');
  return unique[0];
}
export function validateRemediationContract(c, context) {
  const reject = code => { throw new RemediationBlockedError(code, code); };
  if (!c || !['1.0', CR_DEFINITION.schema_version].includes(c.schema_version) || c.repository !== ALLOWED_REPOSITORY || c.pull_request !== context.pullRequest) reject('CONTRACT_BINDING_INVALID');
  if (!sha(c.reviewed_head_sha) || c.reviewed_head_sha !== context.reviewedHeadSha || c.required_starting_head !== c.reviewed_head_sha) reject('CONTRACT_HEAD_MISMATCH');
  if (c.schema_version === CR_DEFINITION.schema_version) {
    const { schema_version, repository, pull_request, reviewed_head_sha, required_starting_head, finding_ids, ...input } = c;
    validateStructuredCr(input);
    if (JSON.stringify(finding_ids) !== JSON.stringify(input.findings.map(f => f.id))) reject('EXECUTABLE_CR_INVALID');
    if (!Number.isSafeInteger(pull_request) || pull_request < 1 || !/^[a-f0-9]{40}$/.test(reviewed_head_sha)) reject('CONTRACT_BINDING_INVALID');
  }
  const profile = resolveCodexProfile({ cliModelId: c.codex_model, effort: c.codex_effort });
  const subagentsAllowed = c.subagents_allowed === undefined ? false : c.subagents_allowed;
  if (typeof subagentsAllowed !== 'boolean') reject('SUBAGENTS_PERMISSION_INVALID');
  assertSafeText(c.change_request_id, 'change_request_id');
  assertSafeText(c.remediation_thread_title, 'thread');
  for (const key of ['finding_ids', 'required_validation']) {
    if (!Array.isArray(c[key]) || !c[key].length || c[key].length > 64 || c[key].some(v => typeof v !== 'string' || !v.trim())) reject('CONTRACT_SET_INVALID');
    assertUnique(c[key], key);
  }
  // Historical path metadata has no execution role. Retain all other contract
  // instructions in the authority fingerprint, including outcome tokens.
  const { allowed_paths: retiredPaths, ...current } = c;
  return Object.freeze({ ...current,
    codex_model: profile.cliModelId, codex_effort: profile.effort, subagents_allowed: subagentsAllowed });
}
