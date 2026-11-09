import test from 'node:test';
import assert from 'node:assert/strict';
import { admissionBinding, authoritySourceDigest, canonicalAuthorityJson, createAdmissionSnapshot,
  extractAuthorityRecord, nativeReference, resolveTaskAuthority, resolveOutcomeAuthority, sha256Body, validateAdmissionSnapshot,
  validateAuthorityRecord } from '../src/github-authority.mjs';
import { resolveExecutionProfile } from '../src/execution-defaults.mjs';

const repository = 'example-org/sample-project';
const task = 23;
const issue = { kind: 'issue', number: task };
const charter = 'Authority model: github-native-v1\n\nGoal: Implement the authorized charter.\nIssue closure policy: keep-open\n';
const reviewer = { login: 'reviewer-app[bot]', id: 7, type: 'Bot' };
const writer = { login: 'writer-app[bot]', id: 8, type: 'Bot' };
const owner = { login: 'owner', id: 9, type: 'User' };
const head = 'a'.repeat(40);
const base = 'b'.repeat(40);
const common = kind => ({ schema_version: '4.0', kind, repository, task, parent: issue, charter_sha256: sha256Body(charter) });
const body = record => '```relay-authority\n' + canonicalAuthorityJson(record) + '\n```\n';
const native = (record, id, extra = {}) => ({ kind: 'issue-comment', repository, id, parent: record.parent,
  body: body(record), author: reviewer, ...extra });
const charterNative = { kind: 'issue-body', repository, id: 1000, parent: issue, body: charter, author: owner };
const binding = { repository, task, charterBody: charter, charterId: charterNative.id, trustedAuthor: reviewer, trustedWriter: writer,
  route: 'auto', purpose: 'Implement the authorized charter', projectDefaults: { model: 'project-model', effort: 'high', subagents: false },
  startingState: { branch: 'codex/task-23', base_sha: base, starting_head: head, existing_pr: null } };
const decision = (amendments, id, extra = {}) => native({ ...common('decision'), purpose: 'Apply the accepted owner amendment',
  amendments, supersedes: null, context: [], ...extra }, id);
const resolve = (records = [], extra = {}) => resolveTaskAuthority([charterNative, ...records], { ...binding, ...extra });
const admits = (resolved, extra = {}) => createAdmissionSnapshot(resolved, { step: 1, attempt: '123', runId: '123', ...extra });
const finding = { id: 'F1', severity: 'major', problem: 'The current candidate violates the accepted invariant.',
  impact: 'Publication can use stale source state.', remediation: 'Bind the exact reviewed source.', acceptance_criteria: ['Reject stale source.'] };
const cr = (overrides = {}) => ({ ...common('change-request'), parent: { kind: 'pull_request', number: 42 },
  purpose: 'Correct the exact reviewed candidate', change_request_id: 'CR-23-001', branch: 'codex/task-23', base_sha: base,
  reviewed_head_sha: head, findings: [finding], context: [], ...overrides });
const crNative = (value = cr()) => native(value, 300, { kind: 'review', state: 'CHANGES_REQUESTED', commit_id: head });
const reject = (fn, code) => assert.throws(fn, { code });

test('charter-only new authority needs no public Request or preallocated Step', () => {
  const resolved = resolve();
  assert.equal(resolved.request.model, 'project-model');
  assert.equal(resolved.request.effort, 'high');
  assert.equal(resolved.request.subagents, false);
  assert.deepEqual(resolved.request.scope, []);
  assert.equal(Object.hasOwn(resolved.request, 'step'), false);
  assert.deepEqual(resolved.reference, nativeReference(charterNative));
  assert.equal(resolved.authority.compatibility_request, null);
  assert.equal(resolved.authority.sha256, authoritySourceDigest(resolved.authority));
  assert.equal(admits(resolved).step, 1);
  reject(() => admits(resolved, { step: undefined }), 'AUTHORITY_ADMISSION_INVALID');
});

test('profile precedence is CR then trusted Decision then project then supported system defaults', () => {
  assert.deepEqual(resolveExecutionProfile(), { model: 'gpt-6.1-sol', effort: 'xhigh', subagents: true });
  assert.deepEqual(resolveExecutionProfile({ project: { model: 'p', subagentsAllowed: false },
    decisions: { effort: 'ultra' }, changeRequest: { model: 'cr' } }), { model: 'cr', effort: 'ultra', subagents: false });
  const amendment = decision({ model: 'decision-model', effort: 'max', subagents: true }, 200);
  const change = crNative(cr({ overrides: { effort: 'ultra', subagents: false } }));
  const resolved = resolve([amendment, change], { pullRequest: 42 });
  assert.equal(resolved.request.model, 'decision-model');
  assert.equal(resolved.request.effort, 'ultra');
  assert.equal(resolved.request.subagents, false);
  reject(() => resolveExecutionProfile({ project: { model: '--execute' } }), 'AUTHORITY_PROFILE_INVALID');
});

test('backlog Decisions accumulate deterministically with explicit supersession and no Step', () => {
  const first = decision({ scope: ['First accepted scope'], effort: 'max' }, 200);
  const second = decision({ boundaries: ['No deployment'], purpose: 'Current authorized purpose' }, 201);
  const replacement = decision({ scope: ['Replacement scope'], effort: 'high' }, 202, { supersedes: nativeReference(first) });
  const resolved = resolve([replacement, first, second]);
  assert.deepEqual(resolved.authority.decisions, [nativeReference(second), nativeReference(replacement)]);
  assert.deepEqual(resolved.request.scope, ['Replacement scope']);
  assert.deepEqual(resolved.request.boundaries, ['No deployment']);
  assert.equal(resolved.request.purpose, 'Current authorized purpose');
  assert.equal(Object.hasOwn(extractAuthorityRecord(replacement.body), 'step'), false);
  reject(() => resolve([first, replacement, decision({ scope: ['Fork'] }, 203, { supersedes: nativeReference(first) })]), 'AUTHORITY_DECISION_SUPERSESSION_INVALID');
  reject(() => resolve([replacement]), 'AUTHORITY_DECISION_SUPERSESSION_INVALID');
  const changed = { ...first, body: first.body + '<!-- changed native bytes -->' };
  reject(() => resolve([changed, replacement]), 'AUTHORITY_DECISION_SUPERSESSION_INVALID');
});

test('ordinary comments and lookalike Bot identities cannot amend or create execution authority', () => {
  const spoof = decision({ issue_closure_policy: 'close-authorized', model: 'spoof' }, 200);
  assert.equal(resolve([{ ...spoof, author: { ...reviewer, id: 99 } }]).request.model, 'project-model');
  assert.equal(resolve([{ ...spoof, author: owner, body: '```relay-authority\n{malformed}\n```' }]).request.issue_closure_policy, 'keep-open');
  reject(() => resolveTaskAuthority([], binding), 'AUTHORITY_CHARTER_SOURCE_MISSING');
  reject(() => resolve([], { trustedAuthor: { ...reviewer, type: 'User' } }), 'AUTHORITY_TRUST_BINDING_INVALID');
});

test('trusted Task Decisions override effective closure in both directions, while CR cannot', () => {
  const close = decision({ issue_closure_policy: 'close-authorized' }, 200);
  assert.equal(resolve([close, crNative()], { pullRequest: 42 }).request.issue_closure_policy, 'close-authorized');
  const keep = decision({ issue_closure_policy: 'keep-open' }, 201);
  assert.equal(resolve([keep, close]).request.issue_closure_policy, 'keep-open');
  reject(() => validateAuthorityRecord(cr({ overrides: { issue_closure_policy: 'close-authorized' } })), 'AUTHORITY_RECORD_INVALID');
  reject(() => validateAuthorityRecord({ ...common('decision'), parent: { kind: 'pull_request', number: 42 },
    purpose: 'Change global closure from a PR', amendments: { issue_closure_policy: 'close-authorized' }, supersedes: null, context: [] }), 'AUTHORITY_DECISION_SCOPE_MISMATCH');
  assert.equal(resolve([close]).authority.charter.sha256, sha256Body(charter));
});

test('native v4 CR is independent of public Requests and does not allocate a Step', () => {
  const change = crNative(cr({ overrides: { boundaries: ['No protected service mutation'], validation: ['diff-check'] } }));
  const resolved = resolve([decision({ boundaries: ['No merge'] }, 200), change], { pullRequest: 42, validationNames: ['diff-check'] });
  assert.equal(resolved.reference.kind, 'review');
  assert.deepEqual(resolved.request.boundaries, ['No merge', 'No protected service mutation']);
  assert.equal(Object.hasOwn(extractAuthorityRecord(change.body), 'step'), false);
  const snapshot = admits(resolved, { step: 2 });
  assert.equal(snapshot.reviewed_head_sha, head);
  assert.equal(snapshot.existing_pr, 42);
  reject(() => resolve([{ ...change, commit_id: base }], { pullRequest: 42 }), 'AUTHORITY_NATIVE_KIND_MISMATCH');
  reject(() => resolve([change], { pullRequest: 42, validationNames: [] }), 'AUTHORITY_VALIDATION_UNKNOWN');
  assert.equal(resolve([change], { activePullRequests: [] }).authority.change_request, null);
  assert.equal(resolve([change, { ...change, id: 301, state: 'APPROVED', body: '' }]).authority.change_request, null);
});

test('accepted Outcome retains its originating CR after APPROVE without granting another admission', () => {
  const change = crNative();
  const origin = resolve([change], { pullRequest: 42 });
  const approved = { ...change, id: 301, state: 'APPROVED', body: '' };
  assert.equal(resolve([change, approved], { pullRequest: 42 }).authority.change_request, null);
  const accepted = resolveOutcomeAuthority(origin.authority, [charterNative, change, approved], { ...binding, pullRequest: 42 });
  assert.deepEqual(accepted.authority, origin.authority);
  reject(() => admits(accepted), 'AUTHORITY_ADMISSION_INVALID');
  const newer = { ...change, id: 302, body: body(cr({ purpose: 'New exact remediation' })) };
  reject(() => resolveOutcomeAuthority(origin.authority, [charterNative, change, approved, newer], binding), 'AUTHORITY_APPROVAL_STALE_REQUEST');
});

test('selected context preserves native body hashes and cannot smuggle conflicting reference bytes', () => {
  const evidence = { kind: 'issue-comment', repository, id: 400, parent: issue, author: owner, body: 'Selected diagnostic evidence.' };
  const amendment = decision({ purpose: 'Use bounded evidence' }, 200, { context: [nativeReference(evidence)] });
  assert.equal(resolve([amendment, evidence]).selectedContext[0].body, evidence.body);
  reject(() => resolve([amendment, { ...evidence, body: evidence.body + 'changed' }]), 'AUTHORITY_SOURCE_MISMATCH');
  const conflicting = decision({ effort: 'max' }, 201, { context: [{ ...nativeReference(evidence), sha256: 'c'.repeat(64) }] });
  reject(() => resolve([amendment, conflicting, evidence]), 'AUTHORITY_SOURCE_MISMATCH');
});

test('old native Request is opaque selected evidence and cannot supply current execution fields', () => {
  const old = { ...common('task-request'), schema_version: '3.0', step: 3, route: 'manual', purpose: 'Retained old direction',
    model: 'old-model', effort: 'max', subagents: true, branch: 'codex/old-branch' };
  const source = native(old, 100);
  const amendment = decision({ effort: 'ultra' }, 200, { context: [nativeReference(source)] });
  const resolved = resolve([source, amendment]);
  assert.equal(extractAuthorityRecord(source.body), null);
  assert.equal(resolved.authority.compatibility_request, null);
  assert.equal(resolved.request.branch, binding.startingState.branch);
  assert.equal(resolved.request.model, 'project-model');
  assert.equal(resolved.request.effort, 'ultra');
  assert.equal(resolved.request.route, 'auto');
  assert.equal(resolved.selectedContext[0].body, source.body);
  reject(() => validateAuthorityRecord(old), 'AUTHORITY_RECORD_INVALID');
  reject(() => resolve([amendment, { ...source, body: source.body + '<!-- edited -->' }]), 'AUTHORITY_SOURCE_MISMATCH');
});

test('an admitted v4 result revalidates its exact selected historical Decision without enabling fresh old authority', () => {
  const retained = native({ ...common('decision'), schema_version: '3.0', purpose: 'Original durable source scope',
    amendments: { scope: ['Original authorized scope remains historical evidence.'] }, supersedes: null, context: [] }, 190);
  const current = decision({ scope: ['Current explicit scope replaces the old scope value.'], effort: 'medium' }, 200);
  const resolved = resolve([current]);
  const sources = { ...resolved.authority, decisions: [nativeReference(retained), nativeReference(current)] };
  const authority = { ...sources, sha256: authoritySourceDigest(sources) };
  // This is an existing protected v4 binding, not permission to admit a new
  // schema-v3 execution or mutate its historical native source.
  const snapshot = createAdmissionSnapshot({ ...resolved, authority }, { step: 2, attempt: 'run-123', runId: 123 });
  const nativeRecords = [charterNative, retained, current];
  const report = resolveOutcomeAuthority(snapshot.authority, nativeRecords, binding);
  assert.deepEqual(report.authority, authority);
  assert.deepEqual(report.originalAuthority.authority, authority);
  assert.deepEqual(report.request.scope, ['Current explicit scope replaces the old scope value.']);
  assert.deepEqual(report.authorityDrift.changed_fields, []);
  assert.equal(extractAuthorityRecord(retained.body), null, 'ordinary context reading does not decode old executable authority');
  const freshShadowed = resolve([retained, current]);
  assert.deepEqual(freshShadowed.authority, authority);
  assert.deepEqual(freshShadowed.request.scope, report.request.scope);
  const effectiveOld = native({ ...common('decision'), schema_version: '3.0', purpose: 'Still effective old semantics',
    amendments: { boundaries: ['A protected obligation not replaced by current direction.'] }, supersedes: null, context: [] }, 191);
  reject(() => resolve([retained, effectiveOld, current]), 'CURRENT_PROTOCOL_REQUIRED');
  reject(() => resolveOutcomeAuthority(authority, [charterNative, { ...retained, body: retained.body + '<!-- edited -->' }, current], binding),
    'AUTHORITY_SOURCE_MISMATCH');
  reject(() => resolveOutcomeAuthority(authority, [charterNative, { ...retained, author: owner }, current], binding),
    'AUTHORITY_SOURCE_MISMATCH');
  const successor = decision({ scope: ['Current explicit scope replaces the old scope value.'] }, 201,
    { supersedes: nativeReference(retained) });
  const fresh = resolve([retained, current, successor]);
  assert.deepEqual(fresh.authority.decisions, [nativeReference(current), nativeReference(successor)]);
  assert.deepEqual(fresh.request.scope, report.request.scope);
  const amended = resolveOutcomeAuthority(authority, [...nativeRecords, successor], binding);
  assert.deepEqual(amended.originalAuthority.authority, authority);
  assert.deepEqual(amended.authority, fresh.authority);
});

test('current v4 Outcome ignores old Request history while preserving current authority identity', () => {
  const old = native({ ...common('task-request'), schema_version: '3.0', step: 3, route: 'auto', purpose: 'Old Request direction',
    scope: ['Old scope'], model: 'old-model', effort: 'max', subagents: true, validation: ['diff-check'],
    boundaries: ['Old boundary'], decisions: [], context: [], supersedes: null, branch: 'codex/old-branch', base_sha: base,
    starting_head: head, existing_pr: null, issue_closure_policy: 'keep-open' }, 100);
  const direction = decision({ purpose: 'Current explicit direction', scope: ['Current accepted scope'] }, 200);
  const resolved = resolve([old, direction]);
  const admission = admissionBinding(admits(resolved));
  const result = { kind: 'no-change', revision: head, identities: [] };
  const outcome = { ...common('outcome'), authority: resolved.authority, admission, step: 1, attempt: '123',
    status: 'implemented', result, warnings: [], limitations: [], summary: 'Current work completed.' };
  const published = native(outcome, 500, { author: writer });
  const records = [charterNative, old, direction, published];
  const current = resolveOutcomeAuthority(outcome.authority, records, binding);
  assert.equal(current.authority.compatibility_request, null);
  assert.deepEqual(current.originalAuthority.authority, outcome.authority);
  assert.deepEqual(current.authorityDrift.changed_fields, []);
  assert.equal(current.request.model, 'project-model');
  assert.deepEqual(current.request.scope, ['Current accepted scope']);
  reject(() => resolveOutcomeAuthority(outcome.authority, [charterNative, old,
    { ...direction, body: direction.body + '<!-- edited -->' }, published], binding), 'AUTHORITY_SOURCE_MISMATCH');
});

test('new execution snapshot binds exact authority, run, attempt, Step and lineage; replay preserves digest', () => {
  const resolved = resolve();
  const first = admits(resolved);
  const identity = admissionBinding(first);
  assert.deepEqual(identity, admissionBinding(validateAdmissionSnapshot(structuredClone(first))));
  const successor = admits(resolved, { step: 2, attempt: '124', runId: '124', lineage: identity });
  const afterStandalone = admits(resolved, { step: 6, attempt: '125', runId: '125', lineage: identity });
  assert.equal(afterStandalone.step, 6);
  assert.deepEqual(afterStandalone.lineage, identity);
  assert.notEqual(admissionBinding(successor).sha256, identity.sha256);
  reject(() => admits(resolved, { step: 1, attempt: '124', lineage: identity }), 'AUTHORITY_ADMISSION_MISMATCH');
  reject(() => admits(resolved, { step: 2, lineage: identity }), 'AUTHORITY_ADMISSION_MISMATCH');
  reject(() => validateAdmissionSnapshot({ ...first, authority: { ...first.authority, sha256: 'c'.repeat(64) } }), 'AUTHORITY_SOURCE_MISMATCH');
  reject(() => validateAdmissionSnapshot(first, { step: 2 }), 'AUTHORITY_ADMISSION_MISMATCH');
  reject(() => createAdmissionSnapshot(resolved, { step: 1, attempt: '123', branch: null }), 'AUTHORITY_STARTING_STATE_INVALID');
});

test('same-CR successor snapshot retains the original reviewed head with a distinct Writer starting head and immediate lineage', () => {
  const change = crNative();
  const originalReview = structuredClone(change);
  const resolved = resolve([change], { pullRequest: 42 });
  const first = admits(resolved);
  const originalSnapshot = structuredClone(first);
  const originalDigest = admissionBinding(first).sha256;
  const lineage = { attempt: first.attempt, step: first.step, sha256: 'd'.repeat(64) };
  const published = 'c'.repeat(40);
  const successor = admits(resolved, { step: 2, attempt: '124', runId: '124', lineage, starting_head: published });

  assert.equal(successor.starting_head, published);
  assert.equal(successor.reviewed_head_sha, head);
  assert.equal(successor.existing_pr, first.existing_pr);
  assert.equal(successor.branch, first.branch);
  assert.equal(successor.base_sha, first.base_sha);
  assert.equal(successor.change_request_id, first.change_request_id);
  assert.deepEqual(successor.authority.change_request, nativeReference(change));
  assert.deepEqual(successor.lineage, lineage);
  assert.deepEqual(validateAdmissionSnapshot(structuredClone(successor)), successor);
  assert.notEqual(admissionBinding(successor).sha256, originalDigest);
  assert.deepEqual(first, originalSnapshot);
  assert.equal(admissionBinding(first).sha256, originalDigest);
  assert.deepEqual(change, originalReview);
  // The shape validator cannot prove Writer publication or authenticate lineage;
  // the protected admission path must supply that independent evidence.
  assert.equal(resolve([change], { pullRequest: 42 }).request.starting_head, head);
});

test('distinct same-CR starting heads keep source, target and earlier-admission lineage validation gates', () => {
  const resolved = resolve([crNative()], { pullRequest: 42 });
  const first = admits(resolved);
  const starting_head = 'c'.repeat(40);
  const lineage = { attempt: first.attempt, step: first.step, sha256: 'd'.repeat(64) };
  const admission = { step: 2, attempt: '124', runId: '124', starting_head, lineage };

  reject(() => admits(resolved, { ...admission, lineage: null }), 'AUTHORITY_CR_BINDING_INVALID');
  reject(() => admits(resolved, { ...admission, lineage: undefined }), 'AUTHORITY_CR_BINDING_INVALID');
  reject(() => admits(resolved, { ...admission, lineage: {} }), 'AUTHORITY_ADMISSION_INVALID');
  reject(() => admits(resolved, { ...admission, lineage: { ...lineage, sha256: 'forged' } }), 'AUTHORITY_ADMISSION_INVALID');
  assert.equal(admits(resolved, { ...admission, step: 3 }).lineage.step, first.step);
  reject(() => admits(resolved, { ...admission, step: first.step }), 'AUTHORITY_ADMISSION_MISMATCH');
  reject(() => admits(resolved, { ...admission, attempt: first.attempt }), 'AUTHORITY_ADMISSION_MISMATCH');
  reject(() => admits(resolved, { ...admission, existing_pr: 43 }), 'AUTHORITY_CR_BINDING_INVALID');
  reject(() => admits(resolved, { ...admission, starting_head: null }), 'AUTHORITY_STARTING_STATE_INVALID');
  const snapshot = admits(resolved, admission);
  for (const field of ['change_request_id', 'reviewed_head_sha']) {
    const missing = structuredClone(snapshot);
    delete missing[field];
    reject(() => validateAdmissionSnapshot(missing), 'AUTHORITY_CR_BINDING_INVALID');
  }
  reject(() => validateAdmissionSnapshot({ ...snapshot, authority: { ...snapshot.authority, sha256: 'f'.repeat(64) } }), 'AUTHORITY_SOURCE_MISMATCH');
  reject(() => validateAdmissionSnapshot(snapshot, { authority: first.authority, attempt: first.attempt }), 'AUTHORITY_ADMISSION_MISMATCH');
});

function outcomeFixture() {
  const resolved = resolve();
  const admission = admissionBinding(admits(resolved));
  const warning = { source: 'run:123:warning', impact: 'A material limitation remains.', resolution: 'Unresolved',
    next_action: 'Inspect before acceptance.', evidence_gaps: ['Installed behavior was not observed.'] };
  const result = { kind: 'no-change', revision: head, identities: [{ kind: 'github-actions-run', id: '123' }] };
  const outcome = { ...common('outcome'), authority: resolved.authority, admission, attempt: admission.attempt, step: admission.step,
    status: 'implemented', result, warnings: [warning], limitations: ['Source qualification only.'], summary: 'Authorized source work completed.' };
  const published = native(outcome, 500, { author: writer });
  return { resolved, admission, outcome, published };
}

test('current authority resolves original execution after amended scope while original sources remain immutable', () => {
  const f = outcomeFixture();
  const changed = decision({ scope: ['Original and added requirement'], boundaries: ['Unused permission expansion'] }, 200);
  const records = [charterNative, f.published, changed];
  const current = resolveOutcomeAuthority(f.outcome.authority, records, binding);
  assert.deepEqual(current.authorityDrift.changed_fields, ['boundaries', 'scope']);
  assert.equal(current.authorityDrift.review_required, true);
  assert.deepEqual(current.originalAuthority.authority, f.outcome.authority);
  const tampered = { ...changed, body: changed.body + '<!-- edited -->' };
  reject(() => resolveOutcomeAuthority(current.authority, [charterNative, f.published, tampered], binding), 'AUTHORITY_SOURCE_MISMATCH');
  reject(() => resolveOutcomeAuthority(current.authority, [charterNative, f.published, { ...changed, author: owner }], binding), 'AUTHORITY_SOURCE_MISMATCH');
});

test('a provenance-only trusted Decision change reports no fictional executor delta', () => {
  const first = decision({ scope: ['Same current requirement'] }, 200);
  const origin = resolve([first]);
  const equivalent = decision({ scope: ['Same current requirement'] }, 201, { supersedes: nativeReference(first) });
  const current = resolveOutcomeAuthority(origin.authority, [charterNative, first, equivalent], binding);
  assert.notDeepEqual(current.authority, origin.authority);
  assert.deepEqual(current.authorityDrift.changed_fields, []);
  assert.equal(current.authorityDrift.review_required, false);
  reject(() => admits(current), 'AUTHORITY_ADMISSION_INVALID');

});

test('authority drift schema binds current source identity, ordered fields and truthful review-needed signal', () => {
  const f = outcomeFixture();
  const drift = resolveOutcomeAuthority(f.outcome.authority, [charterNative, decision({ scope: ['Added requirement'] }, 200)], binding).authorityDrift;
  assert.deepEqual(validateAuthorityRecord({ ...f.outcome, authority_drift: drift }).authority_drift, drift);
  reject(() => validateAuthorityRecord({ ...f.outcome, authority_drift: { ...drift, review_required: false } }), 'AUTHORITY_SOURCE_MISMATCH');
  reject(() => validateAuthorityRecord({ ...f.outcome, authority_drift: { ...drift, changed_fields: ['scope', 'boundaries'] } }), 'AUTHORITY_SOURCE_MISMATCH');
  reject(() => validateAuthorityRecord({ ...f.outcome, authority_drift: { ...drift, current_authority: { ...drift.current_authority, sha256: 'f'.repeat(64) } } }), 'AUTHORITY_SOURCE_MISMATCH');
  const unknown = { ...drift, changed_fields: [], comparison_gaps: ['model'], review_required: true };
  assert.deepEqual(validateAuthorityRecord({ ...f.outcome, authority_drift: unknown }).authority_drift, unknown);
  reject(() => validateAuthorityRecord({ ...f.outcome, authority_drift: { ...unknown, review_required: false } }), 'AUTHORITY_SOURCE_MISMATCH');
  reject(() => validateAuthorityRecord({ ...f.outcome, authority_drift: { ...unknown, comparison_gaps: ['purpose', 'model'] } }), 'AUTHORITY_SOURCE_MISMATCH');
  reject(() => validateAuthorityRecord({ ...f.outcome, authority_drift: { ...drift, comparison_gaps: ['scope'] } }), 'AUTHORITY_SOURCE_MISMATCH');
});

test('new admissions capture exact nonstandard resolver inputs under the existing snapshot digest; explicit retention is no semantic delta', () => {
  const projectDefaults = { model: 'configured-model', effort: 'high', subagents: false, validation: ['diff-check'] };
  const purpose = 'Configured purpose fallback';
  const input = { ...binding, projectDefaults, purpose };
  const original = resolveTaskAuthority([charterNative], input);
  const snapshot = admits(original);
  const resolution = { project_defaults: projectDefaults, purpose, starting_state: binding.startingState };
  assert.deepEqual(snapshot.authority_resolution, resolution);
  assert.deepEqual(validateAdmissionSnapshot(snapshot).authority_resolution, resolution);
  const explicit = decision({ ...projectDefaults, purpose, ...binding.startingState }, 200);
  const current = resolveOutcomeAuthority(original.authority, [charterNative, explicit], input);
  assert.deepEqual(current.authorityDrift.changed_fields, []);
  assert.equal(current.authorityDrift.review_required, false);
  const incompleteBinding = { repository, task, charterBody: charter, trustedAuthor: reviewer, trustedWriter: writer,
    authorityResolution: resolution };
  assert.deepEqual(resolveOutcomeAuthority(original.authority, [charterNative, explicit], incompleteBinding).authorityDrift.changed_fields, []);
  const changed = structuredClone(snapshot);
  changed.authority_resolution.project_defaults.model = 'different-default';
  assert.notEqual(admissionBinding(changed).sha256, admissionBinding(snapshot).sha256);
  // Historical snapshots do not acquire resolver data during validation or replay.
  const historical = structuredClone(snapshot);
  delete historical.authority_resolution;
  assert.equal(Object.hasOwn(validateAdmissionSnapshot(historical), 'authority_resolution'), false);
  const f = outcomeFixture();
  assert.deepEqual(validateAuthorityRecord({ ...f.outcome, authority_resolution: resolution }).authority_resolution, resolution);
  const malformed = structuredClone(resolution);
  malformed.project_defaults.secret = 'not-an-allowed-resolver-field';
  reject(() => validateAuthorityRecord({ ...f.outcome, authority_resolution: malformed }), 'AUTHORITY_RECORD_INVALID');
});

test('typed malicious fence strings round trip while real conflicting authority blocks fail closed', () => {
  const amendment = { ...common('decision'), purpose: 'Literal ```relay-authority and ```yaml data',
    amendments: { boundaries: ['Literal ```reviewer-executable-cr input'] }, supersedes: null, context: [] };
  assert.deepEqual(extractAuthorityRecord(body(amendment)), amendment);
  reject(() => extractAuthorityRecord(body(amendment) + '\n```yaml\n{}\n```\n'), 'AUTHORITY_BLOCK_AMBIGUOUS');
});
