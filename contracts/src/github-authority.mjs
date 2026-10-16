import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { resolveExecutionProfile } from './execution-defaults.mjs';
import { renderPublication } from './publication-rendering.mjs';

// Rust includes this same definition at compile time. It is product source,
// never caller-supplied schema, a credential selector or an authority ledger.
export const AUTHORITY_DEFINITION = JSON.parse(readFileSync(new URL('./github-authority-v1.json', import.meta.url), 'utf8'));
export const AUTHORITY_V4_DEFINITION = JSON.parse(readFileSync(new URL('./github-authority-v4.json', import.meta.url), 'utf8'));
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
  const definition = record?.schema_version === '4.0' ? AUTHORITY_V4_DEFINITION : AUTHORITY_DEFINITION;
  const schema = record && definition.input_schemas[record.kind];
  if (!schema || !conforms(record, schema) || bytes(canonicalAuthorityJson(record)) > AUTHORITY_DEFINITION.max_payload_bytes) fail('AUTHORITY_RECORD_INVALID');
  if (binding.repository !== undefined && record.repository !== binding.repository
    || binding.task !== undefined && record.task !== binding.task) fail('AUTHORITY_TARGET_MISMATCH');
  if (['task-request', 'task-approval', 'task-review'].includes(record.kind)
    && (record.parent.kind !== 'issue' || record.parent.number !== record.task)) fail('AUTHORITY_PARENT_MISMATCH');
  if (record.kind === 'decision' && record.parent.kind === 'issue' && record.parent.number !== record.task) fail('AUTHORITY_PARENT_MISMATCH');
  if (record.kind === 'decision' && Object.keys(record.amendments).length === 0) fail('AUTHORITY_DECISION_EMPTY');
  if (record.schema_version === '3.0' && ['task-request', 'change-request'].includes(record.kind)) {
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
  if (record.schema_version === '3.0' && record.kind === 'change-request' && (record.parent.kind !== 'pull_request'
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
    if (record.schema_version === '3.0' && ['task-request', 'change-request'].includes(record.kind)
      && record.issue_closure_policy !== stableClosurePolicy(binding.charterBody).policy) fail('AUTHORITY_CLOSURE_MISMATCH');
  }
  if (record.schema_version === '4.0') {
    if (record.kind === 'decision' && record.parent.kind !== 'issue'
      && Object.hasOwn(record.amendments, 'issue_closure_policy')) fail('AUTHORITY_DECISION_SCOPE_MISMATCH');
    if (record.kind === 'change-request' && (record.parent.kind !== 'pull_request'
      || record.branch === null || record.base_sha === null
      || new Set(record.findings.map(finding => finding.id)).size !== record.findings.length)) fail('AUTHORITY_CR_BINDING_INVALID');
    if (record.kind === 'change-request' && binding.validationNames
      && record.overrides?.validation?.some(value => !binding.validationNames.includes(value))) fail('AUTHORITY_VALIDATION_UNKNOWN');
    if (record.authority && (record.authority.charter.kind !== 'issue-body'
      || record.authority.charter.parent.kind !== 'issue' || record.authority.charter.parent.number !== record.task
      || record.authority.charter.sha256 !== record.charter_sha256
      || record.authority.sha256 !== authoritySourceDigest(record.authority))) fail('AUTHORITY_SOURCE_MISMATCH');
    if (record.authority) validateAuthoritySources(record.authority, record.task);
    if (record.authority_drift) {
      const drift = record.authority_drift; const current = drift.current_authority;
      validateAuthoritySources(current, record.task);
      if (current.sha256 !== authoritySourceDigest(current) || !equal(current.charter, record.authority.charter)
        || !equal(current.change_request, record.authority.change_request)
        || !equal(current.compatibility_request, record.authority.compatibility_request)
        || drift.review_required !== (drift.changed_fields.length > 0 || (drift.comparison_gaps?.length ?? 0) > 0)
        || !equal(drift.changed_fields, [...drift.changed_fields].sort())
        || drift.comparison_gaps && (!equal(drift.comparison_gaps, [...drift.comparison_gaps].sort())
          || drift.comparison_gaps.some(field => drift.changed_fields.includes(field)))) fail('AUTHORITY_SOURCE_MISMATCH');
    }
    if (record.admission && (record.step !== record.admission.step
      || record.kind === 'outcome' && record.attempt !== record.admission.attempt)) fail('AUTHORITY_ADMISSION_MISMATCH');
  }
  return structuredClone(record);
}

export function validateAuthorityResolution(resolution) {
  if (!conforms(resolution, AUTHORITY_V4_DEFINITION.input_schemas.outcome.properties.authority_resolution)) fail('AUTHORITY_RESOLUTION_INVALID');
  return structuredClone(resolution);
}

export function renderAuthorityRecord(record, binding = {}) {
  const validated = validateAuthorityRecord(record, binding);
  return renderPublication(validated, { title: AUTHORITY_DEFINITION.record_titles[record.kind],
    authorityModel: AUTHORITY_DEFINITION.authority_model, fence: AUTHORITY_DEFINITION.fence,
    canonicalJson: canonicalAuthorityJson(validated), rendererVersion: binding.rendererVersion,
    maxBodyBytes: AUTHORITY_DEFINITION.max_body_bytes });
}
export function extractAuthorityRecord(body, binding = {}) {
  if (typeof body !== 'string' || bytes(body) > AUTHORITY_DEFINITION.max_body_bytes) fail('AUTHORITY_BODY_INVALID');
  const starts = [...body.matchAll(/^```relay-authority[^\n]*/gm)];
  if (!starts.length) return null;
  const blocks = [...body.matchAll(/^```relay-authority\n([\s\S]*?)\n```(?=\n|$)/gm)];
  if (starts.length !== 1 || blocks.length !== 1 || /^```(?:reviewer-executable-cr|ya?ml)\b/m.test(body)) fail('AUTHORITY_BLOCK_AMBIGUOUS');
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
  if (payload?.schema_version !== '3.0') return false;
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
  if (approval.schema_version === '4.0') return validateAdmissionApproval(approval, nativeRecords, binding);
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

// Source identity is public, while the complete execution snapshot is retained
// in the existing protected Writer attempt. No synthetic GitHub ID is allocated.
export function authoritySourceDigest(authority) {
  const { charter, decisions, change_request, compatibility_request } = authority;
  return sha256Body(canonicalAuthorityJson({ charter, decisions, change_request, compatibility_request }));
}

function validateAuthoritySources(authority, task) {
  if (authority.charter.kind !== 'issue-body' || authority.charter.parent.kind !== 'issue' || authority.charter.parent.number !== task
    || authority.change_request !== null && (authority.change_request.kind !== 'review' || authority.change_request.parent.kind !== 'pull_request')
    || authority.compatibility_request !== null && !['issue-comment', 'review'].includes(authority.compatibility_request.kind)
    || authority.decisions.some(reference => reference.kind !== 'issue-comment'
      || reference.parent.kind === 'issue' && reference.parent.number !== task)
    || new Set(authority.decisions.map(referenceKey)).size !== authority.decisions.length
    || authority.decisions.some((reference, index) => index > 0 && authority.decisions[index - 1].id >= reference.id)) fail('AUTHORITY_SOURCE_MISMATCH');
}

export function resolveTaskAuthority(nativeRecords, binding) {
  if (!binding || authorityMode(binding.charterBody) === 'legacy') return null;
  if (!formats.repository(binding.repository) || !Number.isSafeInteger(binding.task) || binding.task < 1
    || !isTrusted({ author: binding.trustedAuthor }, binding.trustedAuthor)) fail('AUTHORITY_TRUST_BINDING_INVALID');
  const records = recordsById(nativeRecords, binding);
  const charter = [...records.values()].find(record => record.kind === 'issue-body'
    && record.parent.number === binding.task && record.body === binding.charterBody
    && (binding.charterId === undefined || binding.charterId === record.id));
  if (!charter) fail('AUTHORITY_CHARTER_SOURCE_MISSING');
  const typed = [...records.values()].flatMap(native => {
    if (!isTrusted(native, binding.trustedAuthor)) return [];
    const payload = typedNative(native, binding);
    return payload ? [{ native, payload }] : [];
  });
  // Retained schema-v3 Requests are optional compatibility inputs for a new
  // admission. Already admitted v3 attempts continue using the original selector.
  const oldRecords = [...records.values()].filter(native => !isTrusted(native, binding.trustedAuthor)
    || typed.find(item => referenceKey(item.native) === referenceKey(native))?.payload.schema_version !== '4.0');
  let compatibility = null;
  if (binding.compatibility !== false && typed.some(item => item.payload.schema_version === '3.0'
    && ['task-request', 'change-request'].includes(item.payload.kind))) {
    compatibility = selectCurrentRequest(oldRecords, { ...binding, step: undefined });
  }
  const latestReviews = new Map();
  for (const native of records.values()) {
    if (native.kind !== 'review' || !isTrusted(native, binding.trustedAuthor)
      || !['CHANGES_REQUESTED', 'APPROVED', 'DISMISSED'].includes(native.state)) continue;
    if (binding.pullRequest !== undefined && native.parent.number !== binding.pullRequest) continue;
    if (binding.activePullRequests && !binding.activePullRequests.includes(native.parent.number)) continue;
    const previous = latestReviews.get(native.parent.number);
    if (!previous || native.id > previous.id) latestReviews.set(native.parent.number, native);
  }
  const changes = [...latestReviews.values()].filter(native => native.state === 'CHANGES_REQUESTED').map(native => {
    const payload = typedNative(native, binding);
    if (payload?.kind !== 'change-request' || native.commit_id !== payload.reviewed_head_sha) fail('AUTHORITY_NATIVE_KIND_MISMATCH');
    validateAuthorityRecord(payload, binding);
    return { native, payload };
  });
  if (changes.length > 1) fail('AUTHORITY_REQUEST_TARGET_MISMATCH');
  let change = changes[0] ?? null;
  if (binding.acceptedAuthority?.change_request) {
    const reference = binding.acceptedAuthority.change_request;
    if (change && !equal(nativeReference(change.native), reference)) fail('AUTHORITY_APPROVAL_STALE_REQUEST');
    const origin = resolveReference(reference, records, binding);
    const payload = typedNative(origin, binding);
    if (!isTrusted(origin, binding.trustedAuthor) || origin.kind !== 'review' || payload?.kind !== 'change-request'
      || origin.commit_id !== payload.reviewed_head_sha) fail('AUTHORITY_CR_BINDING_INVALID');
    validateAuthorityRecord(payload, binding);
    change = { native: origin, payload };
  }
  const existingPr = change?.native.parent.number ?? binding.pullRequest ?? binding.startingState?.existing_pr
    ?? compatibility?.request.existing_pr ?? null;
  const decisions = typed.filter(item => item.payload.kind === 'decision'
    && item.payload.charter_sha256 === sha256Body(binding.charterBody)
    && (item.payload.parent.kind === 'issue' || item.payload.parent.number === existingPr));
  const byKey = new Map(decisions.map(item => [referenceKey(item.native), item]));
  const superseded = new Set();
  for (const item of decisions) {
    if (item.native.kind !== 'issue-comment') fail('AUTHORITY_NATIVE_KIND_MISMATCH');
    const predecessor = item.payload.supersedes;
    if (predecessor === null) continue;
    const previous = byKey.get(referenceKey(predecessor));
    if (!previous || !equal(nativeReference(previous.native), predecessor)
      || !equal(previous.payload.parent, item.payload.parent) || previous.native.id >= item.native.id) fail('AUTHORITY_DECISION_SUPERSESSION_INVALID');
    if (superseded.has(referenceKey(predecessor))) fail('AUTHORITY_DECISION_SUPERSESSION_INVALID');
    superseded.add(referenceKey(predecessor));
  }
  const active = decisions.filter(item => !superseded.has(referenceKey(item.native)))
    .sort((left, right) => left.native.id - right.native.id);
  const amendments = Object.assign({}, ...active.map(item => item.payload.amendments));
  const old = compatibility?.request ?? {};
  const project = binding.projectDefaults ?? {};
  const crOverrides = change?.payload.schema_version === '4.0' ? change.payload.overrides ?? {}
    : change ? Object.fromEntries(['model', 'effort', 'subagents', 'validation', 'boundaries'].map(field => [field, change.payload[field]])) : {};
  const profile = resolveExecutionProfile({ changeRequest: crOverrides,
    decisions: { ...Object.fromEntries(['model', 'effort', 'subagents'].filter(field => old[field] !== undefined).map(field => [field, old[field]])), ...amendments },
    project, ...(binding.systemDefaults ? { system: binding.systemDefaults } : {}) });
  const policy = stableClosurePolicy(binding.charterBody);
  const closureDecision = active.filter(item => item.payload.parent.kind === 'issue'
    && Object.hasOwn(item.payload.amendments, 'issue_closure_policy')).at(-1);
  const allContextRefs = [...(compatibility?.selectedContext.map(item => item.reference) ?? []),
    ...active.flatMap(item => item.payload.context), ...(change?.payload.context ?? [])];
  if (allContextRefs.some((reference, index) => allContextRefs.slice(0, index)
    .some(other => referenceKey(other) === referenceKey(reference) && !equal(other, reference)))) fail('AUTHORITY_SOURCE_MISMATCH');
  const contextRefs = allContextRefs
    .filter((reference, index, all) => all.findIndex(other => referenceKey(other) === referenceKey(reference)) === index);
  const selectedContext = contextRefs.map(reference => ({ reference: structuredClone(reference), body: resolveReference(reference, records, binding).body }));
  if (selectedContext.reduce((total, item) => total + bytes(item.body), 0) > AUTHORITY_DEFINITION.max_context_bytes) fail('AUTHORITY_CONTEXT_TOO_LARGE');
  const source = { charter: nativeReference(charter), decisions: active.map(item => nativeReference(item.native)),
    change_request: change ? nativeReference(change.native) : null, compatibility_request: compatibility?.reference ?? null };
  const authority = { ...source, sha256: authoritySourceDigest(source) };
  const starting = { branch: null, base_sha: null, starting_head: null, existing_pr: null,
    ...binding.startingState,
    ...Object.fromEntries(['branch', 'base_sha', 'starting_head', 'existing_pr'].filter(field => old[field] !== undefined).map(field => [field, old[field]])),
    ...Object.fromEntries(['branch', 'base_sha', 'starting_head', 'existing_pr']
      .filter(field => amendments[field] !== undefined).map(field => [field, amendments[field]])) };
  if (change) Object.assign(starting, { branch: change.payload.branch, base_sha: change.payload.base_sha,
    starting_head: change.payload.reviewed_head_sha, existing_pr: change.native.parent.number });
  const oldContinuation = old.continuation;
  const continuation = amendments.continuation ?? (oldContinuation ? { hold: oldContinuation.hold,
    next: oldContinuation.next?.direction ? { task: oldContinuation.next.task, direction: oldContinuation.next.direction } : null } : { hold: false, next: null });
  const request = { schema_version: '4.0', kind: change ? 'change-request' : 'task-request', repository: binding.repository,
    task: binding.task, parent: change?.payload.parent ?? { kind: 'issue', number: binding.task }, charter_sha256: sha256Body(binding.charterBody),
    route: binding.route ?? old.route, purpose: change?.payload.purpose ?? amendments.purpose ?? old.purpose ?? binding.purpose ?? `Task ${binding.task}`,
    scope: amendments.scope ?? old.scope ?? [], boundaries: [...new Set([...(amendments.boundaries ?? old.boundaries ?? []),
      ...(crOverrides.boundaries ?? [])])],
    validation: crOverrides.validation ?? amendments.validation ?? old.validation ?? project.validation ?? ['diff-check', 'secret-scan'],
    ...profile, ...starting, issue_closure_policy: closureDecision?.payload.amendments.issue_closure_policy ?? policy.policy,
    continuation, ...(change ? { change_request_id: change.payload.change_request_id, reviewed_head_sha: change.payload.reviewed_head_sha,
      findings: change.payload.findings } : {}) };
  return { request, record: structuredClone(change?.native ?? charter), reference: nativeReference(change?.native ?? charter),
    ...(binding.acceptedAuthority ? { acceptanceOnly: true } : {}),
    ...(compatibility ? { compatibilityRequest: compatibility } : {}),
    authority, authorityDigest: authority.sha256, selectedContext,
    ...(typeof binding.purpose === 'string' && binding.startingState
      && ['model', 'effort', 'subagents', 'validation'].every(field => Object.hasOwn(project, field))
      && ['branch', 'base_sha', 'starting_head', 'existing_pr'].every(field => Object.hasOwn(binding.startingState, field))
      ? { resolution: validateAuthorityResolution({ project_defaults: project, purpose: binding.purpose,
        starting_state: binding.startingState }) } : {}),
    decisions: active.map(item => ({ reference: nativeReference(item.native), decision: item.payload })), warnings: policy.warnings };
}

// Acceptance keeps the originating exact CR as provenance after APPROVE or a
// disposed artifact. It cannot turn an already accepted CR into a new execution.
// Native source integrity remains immutable. A trusted successor Decision may
// amend the Task without rewriting an admitted execution or suppressing its
// truthful Outcome. Resolve the old and current semantics independently.
export function resolveOutcomeAuthority(authority, nativeRecords, binding) {
  if (binding.authorityResolution) {
    const resolution = validateAuthorityResolution(binding.authorityResolution);
    binding = { ...binding, projectDefaults: resolution.project_defaults,
      purpose: resolution.purpose, startingState: resolution.starting_state };
  }
  validateAuthoritySources(authority, binding.task);
  if (authority.sha256 !== authoritySourceDigest(authority)) fail('AUTHORITY_SOURCE_MISMATCH');
  const records = recordsById(nativeRecords, binding);
  const originalDecisions = new Set();
  const pending = [...authority.decisions];
  for (const reference of [authority.charter, authority.change_request, authority.compatibility_request].filter(Boolean)) {
    const native = resolveReference(reference, records, binding);
    if (!equal(nativeReference(native), reference) || reference.kind !== 'issue-body' && !isTrusted(native, binding.trustedAuthor)) fail('AUTHORITY_SOURCE_MISMATCH');
  }
  while (pending.length) {
    const reference = pending.pop();
    const key = referenceKey(reference);
    if (originalDecisions.has(key)) continue;
    const native = resolveReference(reference, records, binding);
    const payload = typedNative(native, binding);
    if (!equal(nativeReference(native), reference) || !isTrusted(native, binding.trustedAuthor)
      || payload?.kind !== 'decision') fail('AUTHORITY_SOURCE_MISMATCH');
    originalDecisions.add(key);
    if (payload.supersedes) pending.push(payload.supersedes);
  }
  // Completion and acceptance retain the admission's exact compatibility
  // choice. Historical v3 bytes cannot become a new source for a v4 attempt
  // that was admitted without them; retained references keep their selector.
  const options = { ...binding, compatibility: authority.compatibility_request !== null, acceptedAuthority: authority };
  const current = resolveTaskAuthority(nativeRecords, options);
  if (!current || !equal(current.authority.charter, authority.charter)
    || !equal(current.authority.change_request, authority.change_request)
    || !equal(current.authority.compatibility_request, authority.compatibility_request)) fail('AUTHORITY_APPROVAL_STALE_REQUEST');
  const originalRecords = nativeRecords.filter(native => !isTrusted(native, binding.trustedAuthor)
    || typedNative(native, binding)?.kind !== 'decision' || originalDecisions.has(referenceKey(native)));
  const original = resolveTaskAuthority(originalRecords, options);
  if (!original || !equal(original.authority, authority)) fail('AUTHORITY_SOURCE_MISMATCH');
  const changed_fields = ['purpose', 'scope', 'boundaries', 'validation', 'model', 'effort', 'subagents',
    'branch', 'base_sha', 'starting_head', 'existing_pr', 'issue_closure_policy', 'continuation']
    .filter(field => !equal(original.request[field], current.request[field])).sort();
  return { ...current, originalAuthority: original,
    authorityDrift: { current_authority: current.authority, changed_fields, review_required: changed_fields.length > 0 } };
}

export function validateAdmissionSnapshot(snapshot, binding = {}) {
  if (!conforms(snapshot, AUTHORITY_V4_DEFINITION.admission_schema)
    || bytes(canonicalAuthorityJson(snapshot)) > AUTHORITY_V4_DEFINITION.max_payload_bytes) fail('AUTHORITY_ADMISSION_INVALID');
  if (snapshot.repository !== (binding.repository ?? snapshot.repository) || snapshot.task !== (binding.task ?? snapshot.task)
    || snapshot.parent.kind !== 'issue' || snapshot.parent.number !== snapshot.task) fail('AUTHORITY_TARGET_MISMATCH');
  if (snapshot.authority.sha256 !== authoritySourceDigest(snapshot.authority)
    || snapshot.charter_sha256 !== snapshot.authority.charter.sha256) fail('AUTHORITY_SOURCE_MISMATCH');
  validateAuthoritySources(snapshot.authority, snapshot.task);
  const starting = [snapshot.branch, snapshot.base_sha, snapshot.starting_head];
  if (starting.some(value => value === null) && !starting.every(value => value === null)
    || snapshot.route === 'auto' && starting.some(value => value === null)
    || snapshot.existing_pr !== null && snapshot.branch === null) fail('AUTHORITY_STARTING_STATE_INVALID');
  if (snapshot.lineage && (snapshot.lineage.step + 1 !== snapshot.step || snapshot.lineage.attempt === snapshot.attempt)) fail('AUTHORITY_ADMISSION_MISMATCH');
  // A fresh successor can start at the prior Writer result while retaining the
  // original CR's reviewed head as provenance. Lineage is only a structural
  // prerequisite here: protected Writer admission verifies the exact prior
  // attempt, terminal Outcome, current authority and published starting head.
  if (snapshot.authority.change_request && (!snapshot.change_request_id || !snapshot.reviewed_head_sha
    || snapshot.existing_pr !== snapshot.authority.change_request.parent.number
    || snapshot.starting_head !== snapshot.reviewed_head_sha && !snapshot.lineage)) fail('AUTHORITY_CR_BINDING_INVALID');
  if (binding.step !== undefined && snapshot.step !== binding.step || binding.route !== undefined && snapshot.route !== binding.route
    || binding.attempt !== undefined && snapshot.attempt !== binding.attempt) fail('AUTHORITY_ADMISSION_MISMATCH');
  if (binding.authority && !equal(snapshot.authority, binding.authority)) fail('AUTHORITY_SOURCE_MISMATCH');
  if (binding.validationNames && snapshot.validation.some(value => !binding.validationNames.includes(value))) fail('AUTHORITY_VALIDATION_UNKNOWN');
  return structuredClone(snapshot);
}

export function createAdmissionSnapshot(resolved, admission) {
  if (!resolved?.authority || resolved.acceptanceOnly || !admission) fail('AUTHORITY_ADMISSION_INVALID');
  const q = resolved.request;
  const keys = ['repository', 'task', 'charter_sha256', 'purpose', 'scope', 'model', 'effort', 'subagents', 'validation',
    'boundaries', 'branch', 'base_sha', 'starting_head', 'existing_pr', 'issue_closure_policy', 'continuation'];
  const snapshot = { ...Object.fromEntries(keys.map(field => [field, q[field]])), schema_version: '4.0', kind: 'admission',
    parent: { kind: 'issue', number: q.task }, authority: resolved.authority, route: admission.route ?? q.route,
    step: admission.step, attempt: admission.attempt,
    run_id: Number.isSafeInteger(admission.runId) && admission.runId > 0 ? String(admission.runId)
      : admission.runId ?? admission.run_id ?? admission.attempt,
    lineage: admission.lineage ?? null,
    ...(resolved.resolution ? { authority_resolution: validateAuthorityResolution(resolved.resolution) } : {}),
    ...Object.fromEntries(['change_request_id', 'reviewed_head_sha'].filter(field => q[field] !== undefined).map(field => [field, q[field]])),
    ...Object.fromEntries(['branch', 'base_sha', 'starting_head', 'existing_pr'].filter(field => admission[field] !== undefined)
      .map(field => [field, admission[field]])) };
  return validateAdmissionSnapshot(snapshot, { authority: resolved.authority });
}

export function admissionBinding(snapshot) {
  const validated = validateAdmissionSnapshot(snapshot);
  return { attempt: validated.attempt, step: validated.step, sha256: sha256Body(canonicalAuthorityJson(validated)) };
}

function validateAdmissionApproval(approval, nativeRecords, binding) {
  const records = recordsById(nativeRecords, binding);
  const native = resolveReference(approval.outcome, records, binding);
  if (native.kind !== 'issue-comment' || !isTrusted(native, binding.trustedWriter)) fail('AUTHORITY_OUTCOME_UNTRUSTED');
  const outcome = typedNative(native, binding);
  if (outcome?.kind !== 'outcome' || outcome.schema_version !== '4.0'
    || !equal(outcome.admission, approval.admission) || outcome.status !== 'implemented' || !equal(outcome.result, approval.result)
    || outcome.warnings.some(warning => !approval.warnings.some(disposition => disposition.source === warning.source
      && disposition.impact === warning.impact))) fail('AUTHORITY_APPROVAL_RESULT_MISMATCH');
  if (outcome.limitations.some(limitation => !approval.limitations.includes(limitation))) fail('AUTHORITY_APPROVAL_LIMITATIONS_MISSING');
  const acceptanceBinding = outcome.authority_resolution ? { ...binding, authorityResolution: outcome.authority_resolution } : binding;
  const current = resolveOutcomeAuthority(approval.authority, nativeRecords, acceptanceBinding);
  if (!equal(current.authority, approval.authority)) fail('AUTHORITY_APPROVAL_STALE_REQUEST');
  const delivered = resolveOutcomeAuthority(outcome.authority, nativeRecords, acceptanceBinding);
  if (!equal(delivered.authority, current.authority)) fail('AUTHORITY_APPROVAL_STALE_REQUEST');
  if (binding.openImplementationPr === true) fail('AUTHORITY_APPROVAL_PR_REVIEW_REQUIRED');
  const later = [...records.values()].some(record => record.kind === 'issue-comment' && isTrusted(record, binding.trustedWriter)
    && record.id > native.id && (() => { const value = typedNative(record, binding); return value?.kind === 'outcome'
      && value.schema_version === '4.0' && value.step > outcome.step; })());
  if (later) fail('AUTHORITY_APPROVAL_STALE_REQUEST');
  return { approval: structuredClone(approval), current, outcome, outcomeRecord: structuredClone(native),
    authorityDrift: delivered.authorityDrift };
}
