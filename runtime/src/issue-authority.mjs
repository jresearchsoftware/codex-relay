import { safeBranch as safeConsumerBranch } from '../../consumer/consumer-config.mjs';
import { CONSUMER } from '../../consumer/consumer.mjs';
import { CANONICAL_CODEX_DEFAULT_PROFILE, safeModel, safeEffort } from './codex-profile.mjs';
import { launchStep } from '../../controller/src/launch-metadata.mjs';
export { CANONICAL_CODEX_DEFAULT_PROFILE } from './codex-profile.mjs';
export const SAFE_PROJECT_DEFAULTS = Object.freeze({ subagentsAllowed: false });
export const ISSUE_CLOSURE_POLICIES = Object.freeze(["keep-open", "close-authorized"]);

const MAX_ISSUE_BODY_BYTES = 256 * 1024;
const MAX_AUTHORING_VALUE_BYTES = 512;
const MAX_FIELD_VALUES = 64;
const SAFE_SHA = /^[0-9a-f]{40}$/i;
const SECRET_SHAPES = /github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9_]{20,}|-----BEGIN [^-]*PRIVATE KEY-----|\b(?:bearer|authorization)\s*:/i;

export class IssueAuthorityError extends Error {
  constructor(code, message, details = {}) {
    super(message);
    this.name = "IssueAuthorityError";
    this.code = code;
    this.details = details;
  }
}

function fail(code, message, field, details = {}) {
  throw new IssueAuthorityError(code, message, { ...(field ? { field } : {}), ...details });
}

function requireBody(body) {
  if (typeof body !== "string" || body.trim() === "") fail("ISSUE_AUTHORITY_MISSING", "The live Issue body is required", "body");
  if (Buffer.byteLength(body, "utf8") > MAX_ISSUE_BODY_BYTES) fail("ISSUE_AUTHORITY_INVALID", "The live Issue body is oversized", "body");
  return body.replace(/\r\n?/g, "\n");
}

function normalizedText(value, maximumBytes = MAX_AUTHORING_VALUE_BYTES) {
  if (typeof value !== "string") return null;
  const result = value.normalize("NFC").replace(/\r\n?/g, "\n").replace(/[ \t\n]+/g, " ").trim();
  if (!result || Buffer.byteLength(result, "utf8") > maximumBytes || /[\u0000-\u001f\u007f]/.test(result)) return null;
  return result;
}

function safeRequestedValue(values) {
  if (values.length === 0) return null;
  const safe = values.map(value => {
    const result = normalizedText(value);
    return result && !SECRET_SHAPES.test(result) ? result : "[omitted]";
  });
  return safe.length === 1 ? safe[0] : safe.join(" | ");
}

function stripListPrefix(line) {
  return line.trim().replace(/^(?:[-*+]\s+|\d+[.)]\s+)/, "").replace(/^>\s*/, "").trim();
}

function stripScalar(value) {
  let result = String(value ?? "").trim();
  for (let i = 0; i < 2; i++) {
    if ((result.startsWith("`") && result.endsWith("`")) || (result.startsWith("\"") && result.endsWith("\""))
      || (result.startsWith("'") && result.endsWith("'"))) result = result.slice(1, -1).trim();
    else if ((result.startsWith("**") && result.endsWith("**")) || (result.startsWith("__") && result.endsWith("__"))) result = result.slice(2, -2).trim();
    else break;
  }
  return result;
}

function authoringScalar(value) {
  let result = stripScalar(value);
  for (let i = 0; i < 2; i++) {
    const trimmed = result.replace(/[.,;:!?]+$/, "").trim();
    if (trimmed === result) break;
    result = stripScalar(trimmed);
  }
  return result;
}

function escapeRegex(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function collectFieldValues(source, labels) {
  const values = [];
  for (const rawLine of source.split("\n")) {
    const line = stripListPrefix(rawLine).replace(/^([*_]{1,2})([^:\n]+:)\1\s*/, '$2 ');
    for (const label of labels) {
      const escaped = escapeRegex(label).replace(/ /g, "\\s+");
      const match = line.match(new RegExp("^[`*_~\\s]*" + escaped + "[`*_~\\s]*(?:\\s*[:=]\\s*|\\s+[-–—]\\s+)(.*?)\\s*$", "i"));
      if (match) {
        values.push(stripScalar(match[1]));
        if (values.length >= MAX_FIELD_VALUES) return values;
        break;
      }
    }
  }
  return values;
}

function addResolution(resolutions, field, requested, resolved, source) {
  resolutions.push({ field, requested, resolved, source });
}

function addWarning(warnings, code, field, message, requested, resolved) {
  warnings.push({ code, field, message, requested, resolved });
}

function parseProfileValue(value) {
  const text = stripScalar(value);
  const match = text.match(/^(.+?)\s*(?:\/|,|\|)\s*(?:(?:reasoning|effort)\s*(?:[:=]\s*)?)?(.+)$/i);
  return match ? [stripScalar(match[1]), stripScalar(match[2])] : [text, null];
}

function resolveProfileValue(rawValues, validator, fallback, field, defaultCode, warnings, resolutions) {
  if (rawValues.length === 0) {
    addResolution(resolutions, field, null, fallback, "canonical-default");
    addWarning(warnings, defaultCode, field, `${field} was absent; the automatic-worker default was selected`, null, fallback);
    return fallback;
  }
  // Strip Markdown wrapping only. Do not case-fold, alias, substitute, or
  // consult a local capability inventory for an explicit value.
  const values = rawValues.map(stripScalar);
  if (values.some(value => !validator(value)) || new Set(values).size !== 1) {
    fail("ISSUE_PROFILE_INVALID", `${field} must be a single syntactically safe identifier`, field);
  }
  const resolved = values[0];
  addResolution(resolutions, field, safeRequestedValue(rawValues), resolved, "explicit");
  if (values.length > 1) addWarning(warnings, `${defaultCode}_DUPLICATE_EQUIVALENT`, field,
    `${field} metadata contained duplicate equivalent values`, safeRequestedValue(rawValues), resolved);
  return resolved;
}

function parseProfile(source, warnings, resolutions) {
  const modelValues = collectFieldValues(source, ["Codex model"]);
  const effortValues = collectFieldValues(source, ["Codex reasoning effort", "Codex effort"]);
  const profileValues = collectFieldValues(source, ["Current Codex profile", "Codex profile"]);
  for (const value of profileValues) {
    const [model, effort] = parseProfileValue(value);
    modelValues.push(model);
    if (effort !== null) effortValues.push(effort);
  }
  const cliModelId = resolveProfileValue(modelValues, safeModel, CANONICAL_CODEX_DEFAULT_PROFILE.cliModelId,
    "model", "CODEX_MODEL_DEFAULTED", warnings, resolutions);
  const effort = resolveProfileValue(effortValues, safeEffort, CANONICAL_CODEX_DEFAULT_PROFILE.effort,
    "effort", "CODEX_EFFORT_DEFAULTED", warnings, resolutions);
  return {
    humanProfile: `${cliModelId}/${effort}`,
    cliModelId,
    effort
  };
}

function safeBranch(value) {
  const result = normalizedText(authoringScalar(value), 240);
  return result && result.startsWith(CONSUMER.taskBranchPrefix) && safeConsumerBranch(result) && !result.includes("..") && !result.includes("//") && !result.endsWith("/") && !result.endsWith(".lock")
    && !result.includes("\\") ? result : null;
}

function issueIdentity(issueNumber) {
  return Number.isSafeInteger(issueNumber) && issueNumber > 0 ? String(issueNumber) : "unknown";
}

function titleFromBody(source) {
  return normalizedText(stripScalar(source.match(/^#\s+([^\n]+)$/m)?.[1]), 240);
}

function taskTitle(value, issueNumber) {
  const result = normalizedText(value, 240) ?? `Task ${issueIdentity(issueNumber)}`;
  const id = issueIdentity(issueNumber);
  return result.replace(/^Task\s+#?[0-9]+[A-Za-z]*\b\s*(?:[-–—:·|]+\s*)?/i, "").trim() || `Task ${id}`;
}

function parseBranch(source, issueNumber, warnings, resolutions) {
  const values = collectFieldValues(source, ["Current implementation branch", "Required branch", "Implementation branch"]);
  const normalized = values.map(safeBranch);
  const valid = normalized.filter(Boolean);
  const unique = new Set(valid);
  if (values.length > 0 && valid.length === values.length && unique.size === 1) {
    const resolved = valid[0];
    addResolution(resolutions, "branch", safeRequestedValue(values), resolved, "authoring-normalized");
    if (values.length > 1) addWarning(warnings, "ISSUE_BRANCH_DUPLICATE_EQUIVALENT", "branch", "Branch metadata contained duplicate equivalent values; one canonical value was retained", safeRequestedValue(values), resolved);
    return resolved;
  }
  const resolved = `${CONSUMER.taskBranchPrefix}task-${issueIdentity(issueNumber)}`;
  addResolution(resolutions, "branch", safeRequestedValue(values), resolved, "derived-from-issue-identity");
  if (values.length > 0) addWarning(warnings, "ISSUE_BRANCH_DEFAULTED", "branch", "Branch metadata was malformed; a deterministic codex branch was derived", safeRequestedValue(values), resolved);
  return resolved;
}

function normalizeClosure(value) {
  const key = authoringScalar(value).toLowerCase().replace(/[\s_]+/g, "-");
  return ISSUE_CLOSURE_POLICIES.includes(key) ? key : null;
}

function parseClosurePolicy(source, issueNumber, warnings, resolutions) {
  const explicit = collectFieldValues(source, ["Issue closure policy", "Issue lifecycle"]);
  const legacy = [...source.matchAll(/Issue\s+#([1-9][0-9]*)\s+remains\s+open/gi)].map(match => match[1]);
  const values = [...explicit];
  if (legacy.length === 1 && legacy[0] === issueIdentity(issueNumber)) values.push("keep-open");
  else if (legacy.length > 0) values.push("");
  const normalized = values.map(normalizeClosure);
  const valid = normalized.filter(Boolean);
  const unique = new Set(valid);
  if (values.length > 0 && valid.length === values.length && unique.size === 1) {
    const resolved = valid[0];
    addResolution(resolutions, "closure", safeRequestedValue(values), resolved, "authoring-normalized");
    if (values.length > 1) addWarning(warnings, "ISSUE_CLOSURE_DUPLICATE_EQUIVALENT", "closure", "Closure metadata contained duplicate equivalent values; one canonical value was retained", safeRequestedValue(values), resolved);
    return resolved;
  }
  const resolved = "keep-open";
  addResolution(resolutions, "closure", safeRequestedValue(values), resolved, "safe-project-default");
  addWarning(warnings, "ISSUE_CLOSURE_POLICY_DEFAULTED", "closure", "Closure metadata was missing, malformed, or conflicting; the safe keep-open policy was selected", safeRequestedValue(values), resolved);
  return resolved;
}

function collectStartingBaseValues(source) {
  const values = collectFieldValues(source, ["Required starting base", "Accepted starting base", "Required starting head"]);
  for (const rawLine of source.split("\n")) {
    const line = stripListPrefix(rawLine);
    const match = line.match(/^[`*_~\s]*(?:(?:Accepted|Required)\s+starting\s+[`*_~\s]*main[`*_~\s]*|Accepted\s+base\/main\s+for\s+the\s+current\s+PR)[`*_~\s]*(?:\s*[:=]\s*|\s+[-–—]\s+)(.*?)\s*$/i);
    if (match) {
      if (CONSUMER.baseBranch !== 'main') fail("ISSUE_STARTING_HEAD_INVALID", "Starting base names another consumer branch", "accepted starting base");
      values.push(stripScalar(match[1]));
    }
    if (CONSUMER.baseBranch !== 'main') {
      const prefix = new RegExp('^(?:Accepted|Required)\\s+starting\\s+' + escapeRegex(CONSUMER.baseBranch) + '\\s*:', 'i');
      const plain = line.replace(/[`*_~]/g, '');
      if (prefix.test(plain)) values.push(stripScalar(plain.slice(plain.indexOf(':') + 1)));
    }
  }
  return values;
}

function parseStartingBase(source, targetBaseSha, warnings, resolutions) {
  const values = collectStartingBaseValues(source);
  const normalized = values.map(value => {
    const candidate = authoringScalar(value);
    return SAFE_SHA.test(candidate) ? candidate.toLowerCase() : null;
  });
  const valid = normalized.filter(Boolean);
  const unique = new Set(valid);
  if (values.length > 0 && valid.length === values.length && unique.size === 1) {
    const resolved = valid[0];
    addResolution(resolutions, "accepted starting base", safeRequestedValue(values), resolved, "authoring-normalized");
    if (values.length > 1) addWarning(warnings, "ISSUE_BASE_DUPLICATE_EQUIVALENT", "accepted starting base", "Starting-base metadata contained duplicate equivalent values; one canonical value was retained", safeRequestedValue(values), resolved);
    return resolved;
  }
  if (values.length > 0) fail("ISSUE_STARTING_HEAD_INVALID", "The Issue contains a malformed or conflicting accepted starting head", "accepted starting base");
  if (!SAFE_SHA.test(String(targetBaseSha ?? ""))) fail("ISSUE_STARTING_HEAD_REQUIRED", "A fresh Issue requires an exact current target-branch SHA before execution can be admitted", "accepted starting base");
  const resolved = String(targetBaseSha).toLowerCase();
  addResolution(resolutions, "accepted starting base", null, resolved, "current-target-branch-at-admission");
  return resolved;
}

function parseProjectDefaults(source, warnings, resolutions) {
  const subagentValues = collectFieldValues(source, ["Subagents", "Subagents allowed", "Subagent execution"]);
  const boolean = value => {
    const key = stripScalar(value).toLowerCase().replace(/[\s_-]+/g, "");
    if (["off", "false", "no", "disabled", "forbidden", "none"].includes(key)) return false;
    if (["on", "true", "yes", "enabled", "allowed"].includes(key)) return true;
    return null;
  };
  function resolve(values, field, code, defaultValue, defaultDisplay) {
    const normalized = values.map(boolean);
    const valid = normalized.filter(value => value !== null);
    const unique = new Set(valid);
    if (values.length > 0 && valid.length === values.length && unique.size === 1) {
      const requested = safeRequestedValue(values); const resolved = valid[0];
      addResolution(resolutions, field, requested, resolved ? "On" : "Off", "authoring-normalized");
      if (values.length > 1) addWarning(warnings, `${code}_DUPLICATE_EQUIVALENT`, field, `${field} metadata contained duplicate equivalent values; one safe value was retained`, requested, defaultDisplay);
      return resolved;
    }
    addResolution(resolutions, field, safeRequestedValue(values), defaultValue ? "allowed" : defaultDisplay, "project-default");
    if (values.length > 0) addWarning(warnings, code, field, `${field} metadata was malformed or unrecognized; the safe project default was selected`, safeRequestedValue(values), defaultDisplay);
    return defaultValue;
  }
  return {
    subagentsAllowed: resolve(subagentValues, "subagents", "SUBAGENTS_DEFAULTED", SAFE_PROJECT_DEFAULTS.subagentsAllowed, "Off")
  };
}

export function parseIssueAuthority(body, { issueNumber, repository, issueTitle, step, targetBaseSha } = {}) {
  const source = requireBody(body);
  if (issueNumber !== undefined && (!Number.isInteger(issueNumber) || issueNumber < 1)) fail("ISSUE_AUTHORITY_INVALID", "Issue number must be a positive integer", "issue number");
  const warnings = [];
  const resolutions = [];
  const displayTitle = normalizedText(stripScalar(issueTitle), 240) ?? titleFromBody(source) ?? `Task ${issueIdentity(issueNumber)}`;
  const title = taskTitle(displayTitle, issueNumber);
  const baseSha = parseStartingBase(source, targetBaseSha, warnings, resolutions);
  const branch = parseBranch(source, issueNumber, warnings, resolutions);
  const threadTitle = `Task ${issueIdentity(issueNumber)} — Step ${launchStep(step)} — ${title}`;
  const cliProfile = parseProfile(source, warnings, resolutions);
  const closurePolicy = parseClosurePolicy(source, issueNumber, warnings, resolutions);
  const projectDefaults = parseProjectDefaults(source, warnings, resolutions);
  return {
    issueUrl: repository && issueNumber ? `https://github.com/${repository}/issues/${issueNumber}` : undefined,
    closingReference: issueNumber === undefined ? undefined : closurePolicy === "keep-open" ? `Related to #${issueNumber}` : `Closes #${issueNumber}`,
    closurePolicy,
    baseSha,
    branch,
    prTitle: displayTitle,
    threadTitle,
    cliProfile,
    profile: { cliModelId: cliProfile.cliModelId, effort: cliProfile.effort },
    subagentsAllowed: projectDefaults.subagentsAllowed,
    admission: { kind: "new-issue-implementation", warnings, resolutions },
    warnings,
    resolutions
  };
}
