import test from 'node:test';
import assert from 'node:assert/strict';
import { canonicalAuthorityJson, admissionBinding, createAdmissionSnapshot, nativeReference,
  resolveTaskAuthority, sha256Body } from '../src/github-authority.mjs';
import { continueAfterApproval } from '../src/post-review-continuation.mjs';

const repository = 'example-org/sample-project';
const reviewer = { login: 'reviewer-app[bot]', id: 7, type: 'Bot' };
const writer = { login: 'writer-app[bot]', id: 8, type: 'Bot' };
const head = 'a'.repeat(40);
const base = 'b'.repeat(40);
const render = value => '```relay-authority\n' + canonicalAuthorityJson(value) + '\n```\n';
function fixture({ policy = 'close-authorized', complete = true, remainingWork = false, next = false, pr = false } = {}) {
  const task = 23;
  const parent = { kind: 'issue', number: task };
  const charter = 'Authority model: github-native-v1\n\nGoal: Complete the authorized task.\nIssue closure policy: keep-open\n';
  const common = kind => ({ schema_version: '4.0', kind, repository, task, parent, charter_sha256: sha256Body(charter) });
  const native = (value, id, extra = {}) => ({ kind: 'issue-comment', repository, id, parent: value.parent,
    body: render(value), author: reviewer, ...extra });
  const charterNative = { kind: 'issue-body', repository, id: 1000, parent, body: charter, author: { login: 'owner', id: 9, type: 'User' } };
  const direction = native({ ...common('decision'), purpose: 'Authorized next implementation phase',
    amendments: { scope: ['Next accepted scope'] }, supersedes: null, context: [] }, 200);
  const closure = native({ ...common('decision'), purpose: 'Accepted closure and continuation disposition',
    amendments: { issue_closure_policy: policy, ...(next ? { continuation: { hold: false,
      next: { task, direction: nativeReference(direction) } } } : {}) }, supersedes: null, context: [] }, 201);
  const binding = { repository, task, charterBody: charter, trustedAuthor: reviewer, trustedWriter: writer, route: 'auto',
    startingState: { branch: 'codex/task-23', base_sha: base, starting_head: head, existing_pr: null } };
  const records = [charterNative, ...(next ? [direction] : []), closure];
  let origin;
  if (pr) {
    origin = native({ ...common('change-request'), parent: { kind: 'pull_request', number: 42 },
      purpose: 'Correct exact candidate', change_request_id: 'CR-23-001', reviewed_head_sha: head, branch: 'codex/task-23', base_sha: base,
      context: [], findings: [{ id: 'F1', severity: 'major', problem: 'Source binding is missing.', impact: 'Stale publication is possible.',
        remediation: 'Bind exact head.', acceptance_criteria: ['Reject changed heads.'] }] }, 300,
    { kind: 'review', state: 'CHANGES_REQUESTED', commit_id: head });
    records.push(origin);
  }
  const resolved = resolveTaskAuthority(records, binding);
  const admission = admissionBinding(createAdmissionSnapshot(resolved, { step: 1, attempt: '123', runId: '123' }));
  const result = { kind: 'no-change', revision: head, identities: [{ kind: 'qualification', id: 'run-123' }] };
  const outcome = native({ ...common('outcome'), authority: resolved.authority, admission, step: 1, attempt: '123', status: 'implemented',
    result, warnings: [], limitations: [], summary: 'Bounded qualification completed.' }, 500, { author: writer });
  records.push(outcome);
  const approval = pr ? { kind: 'review', repository, id: 501, parent: { kind: 'pull_request', number: 42 }, author: reviewer,
    body: 'The exact head meets the accepted task.', state: 'APPROVED', commit_id: head }
    : native({ ...common('task-approval'), authority: resolved.authority, admission, outcome: nativeReference(outcome), step: 1,
      result, warnings: [], limitations: [], summary: 'Accept the immutable result.', verdict: 'APPROVE' }, 501);
  records.push(approval);
  const receipt = { publication_status: 'verified', repository, task, charter_sha256: sha256Body(charter), authority: resolved.authority,
    admission, approval: nativeReference(approval), reviewed_head_sha: pr ? head : undefined };
  const state = { binding, nativeRecords: records, currentApproval: receipt.approval,
    task: { number: task, complete, remainingWork, protectedBoundary: false, hold: false, closed: false },
    ...(pr ? { pr: { number: 42, taskNumber: task, state: 'open', merged: false, baseSha: base, headSha: head,
      closesTask: false, readiness: 'ready', mergeability: 'clean', requiredChecksComplete: true,
      requiredChecks: [{ headSha: head, status: 'completed', conclusion: 'success' }] } } : {}) };
  const mutations = [];
  const reservations = new Map();
  const ports = {
    readCanonicalState: async () => state,
    reserveAction: async ({ operationId }) => reservations.get(operationId) ?? { status: 'reserved', operationId },
    recordActionResult: async ({ operationId, result }) => { reservations.set(operationId, { status: 'completed', operationId, result }); },
    closeIssue: async () => { mutations.push('close'); state.task.closed = true; return { status: 'verified' }; },
    mergeSquash: async () => { mutations.push('merge'); state.pr.merged = true; state.pr.mergeCommitSha = 'c'.repeat(40);
      return { status: 'verified', mergeCommitSha: state.pr.mergeCommitSha }; },
    readNextAuthority: async () => ({ binding, nativeRecords: records, protectedBoundary: false }),
    launchAuthority: async action => { mutations.push('launch'); assert.equal(Object.hasOwn(action, 'step'), false);
      assert.equal(Object.hasOwn(action, 'nextRequest'), false); return { status: 'verified' }; }
  };
  return { receipt, state, records, mutations, ports, closure, direction };
}

test('trusted Decision closure uses verified complete Task state, without a public task_complete flag', async () => {
  const f = fixture();
  const result = await continueAfterApproval(f.receipt, f.ports);
  assert.equal(result.status, 'complete');
  assert.deepEqual(f.mutations, ['close']);
  for (const options of [{ complete: false }, { remainingWork: true }]) {
    const retained = fixture(options);
    assert.equal((await continueAfterApproval(retained.receipt, retained.ports)).status, 'complete');
    assert.deepEqual(retained.mutations, []);
  }
});

test('completed keep-open Task with no actual remaining work surfaces owner disposition', async () => {
  const f = fixture({ policy: 'keep-open' });
  const result = await continueAfterApproval(f.receipt, f.ports);
  assert.equal(result.reason, 'CONTINUATION_CLOSURE_POLICY_RECONCILIATION_REQUIRED');
  assert.deepEqual(f.mutations, []);
});

test('native exact-head APPROVE preserves originating CR provenance and uses squash-only owner continuation', async () => {
  const f = fixture({ pr: true });
  const result = await continueAfterApproval(f.receipt, f.ports);
  assert.equal(result.status, 'complete');
  assert.deepEqual(f.mutations, ['merge', 'close']);
});

test('v4 authorized continuation launches native authority without preparing a Request or Step', async () => {
  const f = fixture({ policy: 'keep-open', complete: false, remainingWork: true, next: true });
  const result = await continueAfterApproval(f.receipt, f.ports);
  assert.equal(result.status, 'complete');
  assert.deepEqual(f.mutations, ['launch']);
  assert.equal(result.actions[0].kind, 'launch-authority');
  assert.equal((await continueAfterApproval(f.receipt, f.ports)).status, 'complete');
  assert.deepEqual(f.mutations, ['launch']);
});

test('changed trusted Decision, unknown completion, protected hold and delayed mutation remain bounded', async () => {
  const missing = fixture();
  delete missing.state.task.complete;
  assert.equal((await continueAfterApproval(missing.receipt, missing.ports)).reason, 'CONTINUATION_COMPLETION_UNVERIFIED');
  assert.deepEqual(missing.mutations, []);
  const held = fixture();
  held.state.task.hold = true;
  assert.equal((await continueAfterApproval(held.receipt, held.ports)).reason, 'CONTINUATION_PROTECTED_BOUNDARY');
  const changed = fixture();
  const reserve = changed.ports.reserveAction;
  changed.ports.reserveAction = async action => { changed.closure.body += '<!-- edited -->'; return reserve(action); };
  assert.equal((await continueAfterApproval(changed.receipt, changed.ports)).reason, 'AUTHORITY_APPROVAL_STALE_REQUEST');
  assert.deepEqual(changed.mutations, []);
});
