import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';

// Rust includes this same definition at compile time. It is product source,
// never caller-supplied schema, a credential selector or an authority ledger.
export const AUTHORITY_DEFINITION = JSON.parse(readFileSync(new URL('./github-authority-v1.json', import.meta.url), 'utf8'));
const fail = (code, message = 'Invalid GitHub-native authority') => { throw Object.assign(new Error(message), { code }); };
export const sha256Body = body => createHash('sha256').update(body, 'utf8').digest('hex');
export function canonicalAuthorityJson(value) {
  const sorted = v => Array.isArray(v) ? v.map(sorted) : v !== null && typeof v === 'object'
    ? Object.fromEntries(Object.keys(v).sort().map(key => [key, sorted(v[key])])) : v;
  return JSON.stringify(sorted(value), null, 2);
}
const equal = (a, b) => canonicalAuthorityJson(a) === canonicalAuthorityJson(b);
const bytes = value => Buffer.byteLength(value, 'utf8');
const safeText = value => value.trim().length > 0 && value.normalize('NFC') === value
  && !/[\p{Cc}\uFFFD\u200B-\u200F\u2028-\u202E\u2060-\u2069\uFEFF\uD800-\uDFFF]/u.test(value);
const formats = {
  repository: value => /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(value) && !value.split('/').some(v => v === '.' || v === '..'),
  sha256: value => /^[a-f0-9]{64}$/.test(value),
  'git-sha': value => /^[a-f0-9]{40}$/.test(value),
  argument: value => /^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(value) && !/(?:github_pat_|gh[pousr]_)[A-Za-z0-9_]{20,}/.test(value),
  'stable-id': value => /^[A-Za-z][A-Za-z0-9_-]*$/.test(value),
  'validation-id': value => /^[a-z][a-z0-9-]{0,63}$/.test(value),
  branch: value => /^[A-Za-z0-9][A-Za-z0-9._/-]*$/.test(value) && !value.includes('..') && !value.includes('//')
    && !value.endsWith('/') && !value.endsWith('.') && !value.split('/').some(v => v.startsWith('.') || v.endsWith('.lock'))
};
// The definition deliberately uses only this small shared JSON-schema subset.
function conforms(value, spec) {
  if (spec.anyOf) return spec.anyOf.some(option => conforms(value, option));
  if (spec.enum && !spec.enum.some(option => equal(value, option))) return false;
  switch (spec.type) {
    case 'null': return value === null;
    case 'object': return value !== null && typeof value === 'object' && !Array.isArray(value)
      && spec.required.every(key => Object.hasOwn(value, key))
      && Object.entries(value).every(([key, item]) => Object.hasOwn(spec.properties, key) && conforms(item, spec.properties[key]));
    case 'array': return Array.isArray(value) && value.length >= spec.minItems && value.length <= spec.maxItems
      && value.every(item => conforms(item, spec.items))
      && (!spec.uniqueItems || new Set(value.map(canonicalAuthorityJson)).size === value.length);
    case 'string': return typeof value === 'string' && safeText(value)
      && bytes(value) >= (spec.minLength ?? 0) && bytes(value) <= (spec.maxLength ?? 1000)
      && (!spec.format || formats[spec.format]?.(value) === true);
    case 'integer': return Number.isSafeInteger(value) && value >= spec.minimum && value <= spec.maximum;
    case 'boolean': return typeof value === 'boolean';
    default: return false;
  }
}

export function authorityMode(charterBody) {
  if (typeof charterBody !== 'string') fail('AUTHORITY_CHARTER_INVALID');
  const lines = charterBody.split(/\r?\n/).filter(line => /^\s*(?:[-*]\s*)?Authority model\s*:/i.test(line));
  if (!lines.length) return 'legacy';
  if (lines.length !== 1 || lines[0] !== `Authority model: ${AUTHORITY_DEFINITION.authority_model}`) fail('AUTHORITY_MODEL_INVALID');
  return AUTHORITY_DEFINITION.authority_model;
}
export function stableClosurePolicy(body) {
  if (typeof body !== 'string') fail('AUTHORITY_CHARTER_INVALID');
  const lines = body.split(/\r?\n/).filter(line => /^\s*(?:[-*]\s*)?Issue closure policy\s*:/i.test(line));
  const match = lines.length === 1 ? /^Issue closure policy: (keep-open|close-authorized)$/.exec(lines[0]) : null;
  return match ? { policy: match[1], warnings: [] } : { policy: 'keep-open', warnings: ['ISSUE_CLOSURE_POLICY_INVALID'] };
}

export function validateAuthorityRecord(record, binding = {}) {
  const schema = record && AUTHORITY_DEFINITION.input_schemas[record.kind];
  if (!schema || !conforms(record, schema) || bytes(canonicalAuthorityJson(record)) > AUTHORITY_DEFINITION.max_payload_bytes) fail('AUTHORITY_RECORD_INVALID');
  if (binding.repository !== undefined && record.repository !== binding.repository
    || binding.task !== undefined && record.task !== binding.task) fail('AUTHORITY_TARGET_MISMATCH');
  if (['task-request', 'task-approval', 'task-review'].includes(record.kind)
    && (record.parent.kind !== 'issue' || record.parent.number !== record.task)) fail('AUTHORITY_PARENT_MISMATCH');
  if (record.kind === 'decision' && record.parent.kind === 'issue' && record.parent.number !== record.task) fail('AUTHORITY_PARENT_MISMATCH');
  if (record.kind === 'decision' && Object.keys(record.amendments).length === 0) fail('AUTHORITY_DECISION_EMPTY');
  if (['task-request', 'change-request'].includes(record.kind)) {
    const starting = [record.branch, record.base_sha, record.starting_head];
    if (starting.some(value => value === null) && !starting.every(value => value === null)) fail('AUTHORITY_STARTING_STATE_INVALID');
    if ((record.route === 'auto' || record.kind === 'change-request')
      && starting.some(value => value === null)) fail('AUTHORITY_STARTING_STATE_INVALID');
    if (record.existing_pr !== null && record.branch === null) fail('AUTHORITY_STARTING_STATE_INVALID');
    if (binding.validationNames && record.validation.some(value => !binding.validationNames.includes(value))) fail('AUTHORITY_VALIDATION_UNKNOWN');
    const refs = [...record.decisions, ...record.context];
    if (new Set(refs.map(referenceKey)).size !== refs.length) fail('AUTHORITY_REFERENCE_DUPLICATE');
    const next = record.continuation?.next;
    if (next?.direction && (next.task !== record.task || next.step < record.step || next.step > record.step + 1
      || next.direction.kind !== 'issue-comment' || next.direction.parent.kind !== 'issue' || next.direction.parent.number !== record.task
      || !record.decisions.some(reference => equal(reference, next.direction)))) fail('AUTHORITY_CONTINUATION_INVALID');
  }
  if (record.kind === 'change-request' && (record.parent.kind !== 'pull_request'
    || record.existing_pr !== record.parent.number || record.starting_head !== record.reviewed_head_sha
    || record.supersedes === null
    || new Set(record.findings.map(finding => finding.id)).size !== record.findings.length)) fail('AUTHORITY_CR_BINDING_INVALID');
  if (['outcome', 'task-approval', 'task-review'].includes(record.kind)) {
    if (record.result.revision === null && record.result.identities.length === 0
      || record.result.kind === 'git' && !formats['git-sha'](record.result.revision)
      || new Set(record.result.identities.map(identity => `${identity.kind}:${identity.id}`)).size !== record.result.identities.length) fail('AUTHORITY_RESULT_INVALID');
    if (new Set(record.warnings.map(warning => warning.source)).size !== record.warnings.length) fail('AUTHORITY_WARNING_DUPLICATE');
  }
  if (record.kind === 'task-review' && new Set(record.findings.map(finding => finding.id)).size !== record.findings.length) fail('AUTHORITY_FINDING_DUPLICATE');
  if (binding.charterBody !== undefined) {
    if (authorityMode(binding.charterBody) !== AUTHORITY_DEFINITION.authority_model) fail('AUTHORITY_MIGRATION_REQUIRED');
    if (record.charter_sha256 !== sha256Body(binding.charterBody)) fail('AUTHORITY_CHARTER_MISMATCH');
    if (['task-request', 'change-request'].includes(record.kind)
      && record.issue_closure_policy !== stableClosurePolicy(binding.charterBody).policy) fail('AUTHORITY_CLOSURE_MISMATCH');
  }
  return structuredClone(record);
}

export function renderAuthorityRecord(record, binding = {}) {
  const validated = validateAuthorityRecord(record, binding);
  return `## Relay ${AUTHORITY_DEFINITION.record_titles[record.kind]}\n\nAuthority model: ${AUTHORITY_DEFINITION.authority_model}\n\n\`\`\`${AUTHORITY_DEFINITION.fence}\n${canonicalAuthorityJson(validated)}\n\`\`\`\n`;
}
export function extractAuthorityRecord(body, binding = {}) {
  if (typeof body !== 'string' || bytes(body) > AUTHORITY_DEFINITION.max_body_bytes) fail('AUTHORITY_BODY_INVALID');
  const starts = [...body.matchAll(/^```relay-authority[^\n]*/gm)];
  if (!starts.length) return null;
  const blocks = [...body.matchAll(/^```relay-authority\n([\s\S]*?)\n```(?=\n|$)/gm)];
  if (starts.length !== 1 || blocks.length !== 1 || /```(?:reviewer-executable-cr|ya?ml)\b/.test(body)) fail('AUTHORITY_BLOCK_AMBIGUOUS');
  let record;
  try { record = JSON.parse(blocks[0][1]); } catch { fail('AUTHORITY_JSON_INVALID'); }
  if (canonicalAuthorityJson(record) !== blocks[0][1]) fail('AUTHORITY_JSON_NONCANONICAL');
  return validateAuthorityRecord(record, binding);
}

const parentKey = parent => `${parent.kind}:${parent.number}`;
export const referenceKey = reference => `${reference.kind}:${reference.id}:${parentKey(reference.parent)}`;
export function nativeReference(record) {
  return { kind: record.kind, id: record.id, parent: structuredClone(record.parent), sha256: sha256Body(record.body) };
}
export const nativeSourceRef = nativeReference;
function isTrusted(record, identity) {
  return identity && typeof identity.login === 'string' && identity.login.length > 0 && bytes(identity.login) <= 140
    && identity.type === 'Bot' && Number.isSafeInteger(identity.id) && identity.id > 0
    && record.author?.login === identity.login && record.author?.id === identity.id && record.author?.type === 'Bot';
}
function recordsById(records, binding) {
  if (!Array.isArray(records) || records.length > AUTHORITY_DEFINITION.max_native_records) fail('AUTHORITY_RECORDS_INVALID');
  const map = new Map();
  for (const record of records) {
    if (!record || !['issue-body', 'issue-comment', 'review', 'review-comment'].includes(record.kind)
      || !Number.isSafeInteger(record.id) || record.id < 1 || !record.parent
      || !['issue', 'pull_request'].includes(record.parent.kind) || !Number.isSafeInteger(record.parent.number) || record.parent.number < 1
      || record.repository !== binding.repository || typeof record.body !== 'string' || bytes(record.body) > AUTHORITY_DEFINITION.max_body_bytes
      || ['review', 'review-comment'].includes(record.kind) && record.parent.kind !== 'pull_request'
      || record.kind === 'issue-body' && (record.parent.kind !== 'issue' || record.parent.number !== binding.task)) fail('AUTHORITY_NATIVE_RECORD_INVALID');
    const key = referenceKey(record);
    if (map.has(key)) fail('AUTHORITY_NATIVE_RECORD_DUPLICATE');
    map.set(key, record);
  }
  return map;
}
function resolveReference(reference, records, binding) {
  const native = records.get(referenceKey(reference));
  if (!native || native.repository !== binding.repository || sha256Body(native.body) !== reference.sha256) fail('AUTHORITY_SOURCE_MISMATCH');
  return native;
}
function typedNative(native, binding) {
  const payload = extractAuthorityRecord(native.body, { repository: binding.repository, task: binding.task });
  if (payload && !equal(payload.parent, native.parent)) fail('AUTHORITY_NATIVE_PARENT_MISMATCH');
  return payload;
}
function trustedRequest(native, payload, binding) {
  if (!['task-request', 'change-request'].includes(payload?.kind)) return false;
  if (!isTrusted(native, binding.trustedAuthor)) return false;
  if (payload.kind === 'task-request' && native.kind !== 'issue-comment') fail('AUTHORITY_NATIVE_KIND_MISMATCH');
  if (payload.kind === 'change-request' && (native.kind !== 'review'
    || native.commit_id !== payload.reviewed_head_sha)) fail('AUTHORITY_NATIVE_KIND_MISMATCH');
  return true;
}

export function resolveRequestContext(request, nativeRecords, binding) {
  validateAuthorityRecord(request, binding);
  const records = recordsById(nativeRecords, binding);
  const selectedContext = request.context.map(reference => {
    const native = resolveReference(reference, records, binding);
    return { reference: structuredClone(reference), body: native.body };
  });
  if (selectedContext.reduce((total, selected) => total + bytes(selected.body), 0) > AUTHORITY_DEFINITION.max_context_bytes) fail('AUTHORITY_CONTEXT_TOO_LARGE');
  const amendments = {};
  const selectedDecisions = new Set(request.decisions.map(referenceKey));
  const trustedDecisions = [...records.values()].flatMap(native => {
    if (native.kind !== 'issue-comment' || !isTrusted(native, binding.trustedAuthor)) return [];
    const decision = typedNative(native, binding);
    return decision?.kind === 'decision' ? [{ native, decision }] : [];
  });
  const decisions = request.decisions.map(reference => {
    const native = resolveReference(reference, records, binding);
    if (native.kind !== 'issue-comment' || !isTrusted(native, binding.trustedAuthor)) fail('AUTHORITY_DECISION_UNTRUSTED');
    const decision = typedNative(native, binding);
    if (decision?.kind !== 'decision' || decision.charter_sha256 !== request.charter_sha256) fail('AUTHORITY_DECISION_MISMATCH');
    if (decision.parent.kind === 'pull_request' && request.existing_pr !== decision.parent.number) fail('AUTHORITY_DECISION_SCOPE_MISMATCH');
    for (const successor of trustedDecisions) {
      if (successor.decision.supersedes === null || referenceKey(successor.decision.supersedes) !== referenceKey(reference)) continue;
      if (!equal(successor.decision.supersedes, reference) || !equal(successor.decision.parent, decision.parent)) fail('AUTHORITY_DECISION_SUPERSESSION_INVALID');
      fail('AUTHORITY_DECISION_SUPERSEDED');
    }
    if (decision.supersedes !== null) {
      if (selectedDecisions.has(referenceKey(decision.supersedes))) fail('AUTHORITY_DECISION_SUPERSEDED');
      const prior = resolveReference(decision.supersedes, records, binding);
      const previous = typedNative(prior, binding);
      if (!isTrusted(prior, binding.trustedAuthor) || previous?.kind !== 'decision'
        || !equal(previous.parent, decision.parent)) fail('AUTHORITY_DECISION_SUPERSESSION_INVALID');
    }
    Object.assign(amendments, decision.amendments);
    return { reference: structuredClone(reference), decision };
  });
  for (const [field, value] of Object.entries(amendments)) if (!equal(request[field], value)) fail('AUTHORITY_DECISION_NOT_NORMALIZED');
  return { selectedContext, decisions };
}

// Input records must come from bounded trusted GitHub API reads. Text cannot
// establish author identity, target, native ID, currentness or review state.
export function selectCurrentRequest(nativeRecords, binding) {
  if (!binding || authorityMode(binding.charterBody) === 'legacy') return null;
  if (!formats.repository(binding.repository) || !Number.isSafeInteger(binding.task) || binding.task < 1
    || !isTrusted({ author: binding.trustedAuthor }, binding.trustedAuthor)) fail('AUTHORITY_TRUST_BINDING_INVALID');
  const records = recordsById(nativeRecords, binding);
  const requests = new Map();
  for (const native of records.values()) {
    // Untrusted lookalike text never becomes authority, including malformed blocks.
    if (!isTrusted(native, binding.trustedAuthor)) continue;
    const payload = typedNative(native, binding);
    if (trustedRequest(native, payload, binding)) requests.set(referenceKey(native), { native, request: payload });
  }
  if (!requests.size) fail('AUTHORITY_REQUEST_MISSING');
  const children = new Map();
  const roots = [];
  for (const [key, selected] of requests) {
    const predecessor = selected.request.supersedes;
    if (predecessor === null) { roots.push(key); continue; }
    const prior = requests.get(referenceKey(predecessor));
    if (!prior || sha256Body(prior.native.body) !== predecessor.sha256 || referenceKey(predecessor) === key) fail('AUTHORITY_SUPERSESSION_INVALID');
    if (children.has(referenceKey(predecessor))) fail('AUTHORITY_SUPERSESSION_AMBIGUOUS');
    const sameCr = selected.request.kind === 'change-request' && prior.request.kind === 'change-request'
      && selected.request.change_request_id === prior.request.change_request_id
      && selected.request.reviewed_head_sha === prior.request.reviewed_head_sha
      && equal(selected.request.parent, prior.request.parent);
    if (selected.request.step < prior.request.step || selected.request.step > prior.request.step + 1
      || selected.request.kind === 'change-request' && selected.request.step === prior.request.step && !sameCr) fail('AUTHORITY_STEP_INVALID');
    children.set(referenceKey(predecessor), key);
  }
  if (roots.length !== 1) fail('AUTHORITY_SUPERSESSION_AMBIGUOUS');
  const visited = new Set();
  let current = roots[0];
  while (children.has(current)) {
    if (visited.has(current)) fail('AUTHORITY_SUPERSESSION_INVALID');
    visited.add(current); current = children.get(current);
  }
  visited.add(current);
  if (visited.size !== requests.size) fail('AUTHORITY_SUPERSESSION_AMBIGUOUS');
  const selected = requests.get(current);
  if (selected.request.kind === 'change-request' && selected.native.state !== 'CHANGES_REQUESTED') fail('AUTHORITY_NATIVE_KIND_MISMATCH');
  validateAuthorityRecord(selected.request, binding);
  if (binding.step !== undefined && binding.step !== selected.request.step) fail('AUTHORITY_STEP_MISMATCH');
  const resolved = resolveRequestContext(selected.request, nativeRecords, binding);
  return { request: selected.request, record: structuredClone(selected.native), reference: nativeReference(selected.native), ...resolved,
    warnings: stableClosurePolicy(binding.charterBody).warnings };
}

export function validateTaskApproval(approval, nativeRecords, binding) {
  validateAuthorityRecord(approval, binding);
  if (approval.kind !== 'task-approval') fail('AUTHORITY_APPROVAL_INVALID');
  const current = selectCurrentRequest(nativeRecords, binding);
  if (current?.request.kind !== 'task-request' || !equal(approval.request, current.reference)) fail('AUTHORITY_APPROVAL_STALE_REQUEST');
  if (approval.step !== current.request.step) fail('AUTHORITY_APPROVAL_STEP_MISMATCH');
  const records = recordsById(nativeRecords, binding);
  const native = resolveReference(approval.outcome, records, binding);
  if (native.kind !== 'issue-comment' || !isTrusted(native, binding.trustedWriter)) fail('AUTHORITY_OUTCOME_UNTRUSTED');
  const outcome = typedNative(native, binding);
  if (outcome?.kind !== 'outcome' || !equal(outcome.request, current.reference)
    || outcome.charter_sha256 !== approval.charter_sha256
    || outcome.status !== 'implemented' || !equal(outcome.result, approval.result)
    || outcome.warnings.some(warning => !approval.warnings.some(disposition => disposition.source === warning.source
      && disposition.impact === warning.impact))) fail('AUTHORITY_APPROVAL_RESULT_MISMATCH');
  if (outcome.limitations.some(limitation => !approval.limitations.includes(limitation))) fail('AUTHORITY_APPROVAL_LIMITATIONS_MISSING');
  return { approval: structuredClone(approval), current, outcome, outcomeRecord: structuredClone(native) };
}
