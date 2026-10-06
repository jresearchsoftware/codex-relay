import test from 'node:test';
import assert from 'node:assert/strict';
import { extractAuthorityRecord, nativeReference, renderAuthorityRecord, sha256Body } from '../src/github-authority.mjs';
import { continueAfterApproval } from '../src/post-review-continuation.mjs';

const repository = 'example-org/sample-project';
const reviewer = { login: 'reviewer-app[bot]', id: 7, type: 'Bot' };
const writer = { login: 'writer-app[bot]', id: 8, type: 'Bot' };
const head = 'a'.repeat(40);
const base = 'b'.repeat(40);
const merge = 'c'.repeat(40);
const charter = policy => `Authority model: github-native-v1\nIssue closure policy: ${policy}\nGoal: Complete the bounded scope.\n`;
function taskRequest(task, charterBody, continuation = { hold: false, task_complete: true, next: null }, route = 'auto') {
  return { schema_version: '3.0', kind: 'task-request', repository, task, parent: { kind: 'issue', number: task },
    charter_sha256: sha256Body(charterBody), step: 1, route, purpose: 'Implement the admitted scope', scope: ['Complete the bounded scope.'],
    model: 'future-model', effort: 'xhigh', subagents: true, validation: ['remediation-tests'], boundaries: ['Keep protected operations separate.'],
    decisions: [], context: [], supersedes: null, branch: `codex/task-${task}`, base_sha: base, starting_head: head,
    existing_pr: null, issue_closure_policy: charterBody.includes('close-authorized') ? 'close-authorized' : 'keep-open', continuation };
}
function nativeRecord(payload, id, author = reviewer) {
  return { kind: 'issue-comment', id, repository, parent: payload.parent, author, body: renderAuthorityRecord(payload) };
}
function fixture(options = {}) {
  const charterBody = charter(options.closure ?? 'close-authorized');
  const nextCharter = charter('keep-open');
  const nextRequest = nativeRecord(taskRequest(24, nextCharter, { hold: false, task_complete: false, next: null }, options.nextRoute ?? 'auto'), 200);
  const current = nativeRecord(taskRequest(23, charterBody, { hold: options.hold ?? false,
    task_complete: options.taskComplete ?? true, next: options.next ? { task: 24, request: nativeReference(nextRequest) } : null }), 100);
  const approved = { kind: 'review', id: 300, parent: { kind: 'pull_request', number: 25 }, repository,
    author: reviewer, body: 'Independent exact-head APPROVE.', state: 'APPROVED', commit_id: head };
  const state = {
    binding: { repository, task: 23, charterBody, trustedAuthor: reviewer, trustedWriter: writer }, nativeRecords: [current, approved],
    task: { number: 23, remainingWork: options.remainingWork ?? false, protectedBoundary: options.protectedBoundary ?? false, hold: false, closed: false },
    currentApproval: nativeReference(approved),
    pr: { number: 25, taskNumber: 23, closesTask: false, state: 'open', headSha: head, baseSha: base, merged: false, readiness: 'ready', mergeability: 'clean',
      requiredChecksComplete: true, requiredChecks: [{ name: 'qualification', headSha: head, status: 'completed', conclusion: 'success' }] }
  };
  const receipt = { publication_status: 'verified', repository, task: 23, approval: nativeReference(approved),
    request: nativeReference(current), charter_sha256: sha256Body(charterBody), reviewed_head_sha: head, reviewed_base_sha: base };
  const calls = [];
  const completed = new Map();
  const ports = {
    readCanonicalState: async () => { calls.push('read'); return structuredClone(state); },
    reserveAction: async ({ operationId, action }) => {
      calls.push(`reserve:${action.kind}`);
      if (completed.has(operationId)) return { status: 'completed', operationId, result: completed.get(operationId) };
      return { status: 'reserved', operationId };
    },
    recordActionResult: async ({ operationId, action, result }) => { calls.push(`record:${action.kind}:${result?.status}`); if (result?.status === 'verified') completed.set(operationId, result); },
    mergeSquash: async action => {
      calls.push('merge'); assert.equal(action.expectedHeadSha, head); assert.equal(action.expectedBaseSha, state.pr.baseSha);
      if (action.commitTitle !== undefined) {
        assert.equal(action.commitTitle, 'Task 23 implementation');
        assert.ok(!/\b(?:closes|fixes|resolves)\b/i.test(action.commitTitle + action.commitBody));
        assert.ok(!action.commitBody.includes('#23'));
      }
      state.pr.merged = true; state.pr.state = 'closed'; state.pr.mergeCommitSha = merge;
      return { status: 'verified', mergeCommitSha: merge };
    },
    closeIssue: async action => { calls.push('close'); assert.equal(action.issueNumber, 23); state.task.closed = true; return { status: 'verified', issueNumber: 23 }; },
    readNextAuthority: async () => { calls.push('read-next'); return { binding: { repository, task: 24, charterBody: nextCharter, trustedAuthor: reviewer },
      nativeRecords: [nextRequest], protectedBoundary: false }; },
    launchRequest: async action => { calls.push('launch'); assert.deepEqual(action.nextRequest, nativeReference(nextRequest)); return { status: 'verified', runId: 600 }; },
    manualHandoff: async action => { calls.push('handoff'); assert.equal(action.route, 'manual'); return { status: 'verified', nativeId: 700 }; }
  };
  return { state, receipt, calls, ports, current, approved, nextRequest, completed };
}

function assertNoMutation(f) { assert.equal(f.calls.some(call => ['merge', 'close', 'launch', 'handoff'].includes(call)), false); }

test('verified independent native approval immediately executes squash, authorized closure and exact next automatic Request', async () => {
  const f = fixture({ next: true });
  const outcome = await continueAfterApproval(f.receipt, f.ports);
  assert.equal(outcome.status, 'complete');
  assert.deepEqual(outcome.actions.map(action => action.kind), ['squash-merge', 'close-issue', 'launch-request']);
  assert.deepEqual(f.calls.filter(call => ['merge', 'close', 'launch', 'handoff'].includes(call)), ['merge', 'close', 'launch']);
  assert.equal(f.state.task.closed, true);
  assert.ok(f.calls.indexOf('reserve:squash-merge') < f.calls.indexOf('merge'));
  assert.ok(f.calls.indexOf('record:squash-merge:verified') < f.calls.indexOf('close'));
  // Reconciliation uses the same action identity and does not relaunch the next Task.
  const again = await continueAfterApproval(f.receipt, f.ports);
  assert.equal(again.status, 'complete');
  assert.equal(f.calls.filter(call => call === 'merge').length, 1);
  assert.equal(f.calls.filter(call => call === 'close').length, 1);
  assert.equal(f.calls.filter(call => call === 'launch').length, 1);
});

test('manual next Request creates the bounded handoff through the owner adapter', async () => {
  const f = fixture({ next: true, nextRoute: 'manual' });
  const result = await continueAfterApproval(f.receipt, f.ports);
  assert.equal(result.status, 'complete');
  assert.ok(f.calls.includes('handoff')); assert.ok(!f.calls.includes('launch'));
});

test('keep-open preserves the Issue while accepting and continuing already authorized work', async () => {
  const f = fixture({ closure: 'keep-open', next: true });
  const result = await continueAfterApproval(f.receipt, f.ports);
  assert.equal(result.status, 'complete');
  assert.ok(f.calls.includes('merge')); assert.ok(f.calls.includes('launch')); assert.ok(!f.calls.includes('close'));
  assert.equal(f.state.task.closed, false);
});

test('close-authorized does not close an incomplete Task or one with remaining work', async () => {
  for (const options of [{ taskComplete: false }, { remainingWork: true }]) {
    const f = fixture(options);
    assert.equal((await continueAfterApproval(f.receipt, f.ports)).status, 'complete');
    assert.ok(!f.calls.includes('close'));
  }
});

test('changed head, native actor, charter or current Request stops before mutation', async () => {
  for (const alter of [
    f => { f.state.pr.headSha = merge; },
    f => { f.state.nativeRecords[1].author = { ...reviewer, id: 99 }; },
    f => { f.state.currentApproval = { ...f.receipt.approval, id: 301 }; },
    f => { f.state.binding.charterBody += 'Changed scope.\n'; },
    f => {
      const next = { ...taskRequest(23, f.state.binding.charterBody), supersedes: nativeReference(f.current) };
      f.state.nativeRecords.push(nativeRecord(next, 102));
    }
  ]) {
    const f = fixture(); alter(f);
    assert.equal((await continueAfterApproval(f.receipt, f.ports)).status, 'stopped');
    assertNoMutation(f);
  }
});

test('unresolved, stale, missing or failed required checks and unknown base readiness stop', async () => {
  for (const alter of [
    f => { f.state.pr.requiredChecks[0].status = 'in_progress'; },
    f => { f.state.pr.requiredChecks[0].conclusion = 'failure'; },
    f => { f.state.pr.requiredChecks[0].headSha = merge; },
    f => { f.state.pr.requiredChecksComplete = false; },
    f => { f.state.pr.mergeability = 'unknown'; },
    f => { f.state.pr.readiness = 'unknown'; }
  ]) {
    const f = fixture(); alter(f);
    const result = await continueAfterApproval(f.receipt, f.ports);
    assert.equal(result.reason, 'CONTINUATION_NOT_READY'); assertNoMutation(f);
  }
});

test('checks are re-read after reservation before any merge is sent', async () => {
  const f = fixture();
  const reserve = f.ports.reserveAction;
  f.ports.reserveAction = async action => { const result = await reserve(action); f.state.pr.requiredChecks[0].conclusion = 'failure'; return result; };
  const result = await continueAfterApproval(f.receipt, f.ports);
  assert.equal(result.reason, 'CONTINUATION_NOT_READY'); assertNoMutation(f);
  assert.ok(f.calls.includes('record:squash-merge:not-started'));
});

test('ordinary moving base is allowed with fresh exact-head checks; an explicit exact-base boundary remains enforced', async () => {
  const f = fixture(); f.state.pr.baseSha = merge;
  assert.equal((await continueAfterApproval(f.receipt, f.ports)).status, 'complete');
  assert.ok(f.calls.includes('merge'));
  const exact = fixture(); exact.state.pr.baseSha = merge; exact.state.pr.exactBaseRequired = true;
  assert.equal((await continueAfterApproval(exact.receipt, exact.ports)).reason, 'CONTINUATION_BASE_CHANGED');
  assertNoMutation(exact);
});

test('explicit hold and a protected boundary prevent every continuation action', async () => {
  for (const options of [{ hold: true }, { protectedBoundary: true }]) {
    const f = fixture(options);
    assert.equal((await continueAfterApproval(f.receipt, f.ports)).reason, 'CONTINUATION_PROTECTED_BOUNDARY');
    assertNoMutation(f);
  }
});

test('migrated PR implicit Task closure is blocked and squash messages do not inherit closing keywords', async () => {
  for (const closesTask of [true, null, undefined]) {
    const f = fixture({ closure: 'keep-open' }); f.state.pr.closesTask = closesTask;
    assert.equal((await continueAfterApproval(f.receipt, f.ports)).reason, 'CONTINUATION_IMPLICIT_CLOSURE');
    assertNoMutation(f);
  }
  const f = fixture({ closure: 'keep-open' }); f.state.pr.title = 'Fixes #23';
  f.state.pr.sourceCommitBody = 'Closes #23';
  let action;
  const mergePort = f.ports.mergeSquash;
  f.ports.mergeSquash = async input => { action = input; return mergePort(input); };
  assert.equal((await continueAfterApproval(f.receipt, f.ports)).status, 'complete');
  assert.equal(action.commitTitle, 'Task 23 implementation');
  assert.ok(!/Fixes|Closes|Resolves|#23/i.test(action.commitBody));
  assert.equal(f.state.task.closed, false);
});

test('failed or uncertain native publication never falls back to manual approval or mutation', async () => {
  const f = fixture(); f.receipt.publication_status = 'uncertain';
  const result = await continueAfterApproval(f.receipt, f.ports);
  assert.equal(result.reason, 'CONTINUATION_PUBLICATION_UNVERIFIED'); assert.deepEqual(f.calls, []);
});

test('uncertain merge or existing mutation intent stops without closure, relaunch or blind retry', async () => {
  const f = fixture({ next: true });
  f.ports.mergeSquash = async () => { f.calls.push('merge'); return { status: 'uncertain' }; };
  assert.equal((await continueAfterApproval(f.receipt, f.ports)).reason, 'CONTINUATION_ACTION_UNCERTAIN');
  assert.equal(f.calls.filter(call => call === 'merge').length, 1); assert.ok(!f.calls.includes('close')); assert.ok(!f.calls.includes('launch'));
  const reserved = fixture();
  reserved.ports.reserveAction = async ({ operationId }) => ({ status: 'uncertain', operationId });
  assert.equal((await continueAfterApproval(reserved.receipt, reserved.ports)).reason, 'CONTINUATION_ACTION_UNCERTAIN'); assertNoMutation(reserved);
});

test('a successful merge response requires native readback before closure', async () => {
  const f = fixture();
  f.ports.mergeSquash = async () => { f.calls.push('merge'); return { status: 'verified', mergeCommitSha: merge }; };
  assert.equal((await continueAfterApproval(f.receipt, f.ports)).reason, 'CONTINUATION_MERGE_UNVERIFIED');
  assert.ok(!f.calls.includes('close'));
});

test('next Request is revalidated after reservation and superseded next authority is never launched', async () => {
  const f = fixture({ next: true });
  const read = f.ports.readNextAuthority; let count = 0;
  f.ports.readNextAuthority = async args => {
    const state = await read(args); count++;
    if (count > 1) {
      const next = { ...taskRequest(24, state.binding.charterBody), supersedes: nativeReference(f.nextRequest) };
      state.nativeRecords.push(nativeRecord(next, 202));
    }
    return state;
  };
  assert.equal((await continueAfterApproval(f.receipt, f.ports)).reason, 'CONTINUATION_NEXT_REQUEST_CHANGED');
  assert.ok(!f.calls.includes('launch')); assert.ok(f.calls.includes('merge'));
});

test('Task Approval accepts no-PR immutable qualification result and can close only under charter authority', async () => {
  const f = fixture();
  const result = { kind: 'qualification', revision: null, identities: [{ kind: 'check-run', id: '501' }] };
  const outcome = nativeRecord({ schema_version: '3.0', kind: 'outcome', repository, task: 23, parent: { kind: 'issue', number: 23 },
    charter_sha256: sha256Body(f.state.binding.charterBody), request: nativeReference(f.current), attempt: '123', status: 'implemented',
    result, warnings: [], limitations: [], summary: 'Native qualification passed.' }, 101, writer);
  const approval = nativeRecord({ schema_version: '3.0', kind: 'task-approval', repository, task: 23, parent: { kind: 'issue', number: 23 },
    charter_sha256: sha256Body(f.state.binding.charterBody), request: nativeReference(f.current), outcome: nativeReference(outcome),
    step: 1, result, warnings: [], limitations: [], verdict: 'APPROVE', summary: 'Accept the immutable qualification result.' }, 102);
  f.state.nativeRecords = [f.current, outcome, approval]; f.state.pr = null;
  f.receipt.approval = nativeReference(approval);
  f.state.currentApproval = nativeReference(approval);
  assert.equal((await continueAfterApproval(f.receipt, f.ports)).status, 'complete');
  assert.ok(f.calls.includes('close')); assert.ok(!f.calls.includes('merge'));
});

test('legacy native PR acceptance retains its canonical authority digest and no implicit typed migration', async () => {
  const f = fixture(); f.state.binding.charterBody = 'Legacy Task contract\nIssue closure policy: keep-open\n';
  f.receipt.charter_sha256 = sha256Body(f.state.binding.charterBody); f.receipt.request = null;
  f.state.authorityDigest = f.receipt.authority_digest = 'd'.repeat(64);
  f.state.legacyContinuation = { hold: false, task_complete: true, next: null };
  f.state.pr.closesTask = true;
  assert.equal((await continueAfterApproval(f.receipt, f.ports)).status, 'complete');
  assert.ok(f.calls.includes('merge')); assert.ok(!f.calls.includes('close'));
});

function sameTaskFixture({ changedProfile = false } = {}) {
  const f = fixture({ taskComplete: false, remainingWork: true });
  const direction = nativeRecord({ schema_version: '3.0', kind: 'decision', repository, task: 23,
    parent: { kind: 'issue', number: 23 }, charter_sha256: sha256Body(f.state.binding.charterBody),
    purpose: 'Authorize the same complete snapshot at the next explicit Step', amendments: { scope: ['Complete the bounded scope.'] },
    supersedes: null, context: [] }, 250);
  const payload = taskRequest(23, f.state.binding.charterBody, { hold: false, task_complete: false,
    next: { task: 23, direction: nativeReference(direction), step: 2 } });
  payload.decisions = [nativeReference(direction)];
  f.current = nativeRecord(payload, 100); f.state.nativeRecords = [f.current, f.approved, direction];
  f.receipt.request = nativeReference(f.current);
  f.ports.prepareNextAuthority = async action => {
    f.calls.push('prepare');
    if (f.state.pr) assert.equal(f.state.pr.merged, true);
    assert.equal(f.state.nativeRecords.filter(record => record.id === 100).length, 1);
    assert.deepEqual(action.acceptedRequest, f.receipt.request);
    assert.equal(action.step, 2);
    assert.deepEqual(action.snapshot.scope, payload.scope);
    const next = nativeRecord({ ...action.snapshot, base_sha: merge,
      ...(changedProfile ? { model: 'unapproved-profile' } : {}) }, 105);
    f.state.nativeRecords.push(next); f.state.binding.step = 2;
    return { status: 'verified', request: nativeReference(next) };
  };
  f.ports.readNextAuthority = async ({ task }) => {
    f.calls.push('read-next'); assert.equal(task, 23);
    return { binding: f.state.binding, nativeRecords: f.state.nativeRecords, protectedBoundary: false };
  };
  f.ports.launchRequest = async action => { f.calls.push('launch'); assert.equal(action.nextTask, 23);
    assert.equal(action.nextRequest.id, 105); return { status: 'verified', runId: 800 }; };
  return f;
}

test('same-Task phase preparation follows native acceptance and verified merge while old authority stays current until preparation', async () => {
  const f = sameTaskFixture();
  const result = await continueAfterApproval(f.receipt, f.ports);
  assert.equal(result.status, 'complete');
  assert.deepEqual(f.calls.filter(call => ['merge', 'prepare', 'launch', 'close'].includes(call)), ['merge', 'prepare', 'launch']);
  assert.ok(f.calls.indexOf('record:squash-merge:verified') < f.calls.indexOf('prepare'));
  assert.ok(f.calls.indexOf('record:prepare-next-authority:verified') < f.calls.indexOf('launch'));
  assert.deepEqual(result.actions.map(action => action.kind), ['squash-merge', 'prepare-next-authority', 'launch-request']);
  assert.equal(f.state.task.closed, false);
});

test('a prepared same-Task Request cannot invent a different execution profile', async () => {
  const f = sameTaskFixture({ changedProfile: true });
  assert.equal((await continueAfterApproval(f.receipt, f.ports)).reason, 'CONTINUATION_PREPARED_REQUEST_INVALID');
  assert.ok(f.calls.includes('merge')); assert.ok(f.calls.includes('prepare')); assert.ok(!f.calls.includes('launch'));
});

test('a superseding same-Task Request published before merge invalidates the accepted source and prevents every action', async () => {
  const f = sameTaskFixture();
  const future = nativeRecord({ ...taskRequest(23, f.state.binding.charterBody), step: 2, supersedes: f.receipt.request }, 105);
  f.state.nativeRecords.push(future);
  assert.equal((await continueAfterApproval(f.receipt, f.ports)).reason, 'CONTINUATION_REQUEST_CHANGED');
  assertNoMutation(f); assert.ok(!f.calls.includes('prepare'));
});

test('same-Task preparation after no-PR Task Approval preserves the immutable accepted Outcome', async () => {
  const f = sameTaskFixture();
  const result = { kind: 'qualification', revision: null, identities: [{ kind: 'check-run', id: '501' }] };
  const outcome = nativeRecord({ schema_version: '3.0', kind: 'outcome', repository, task: 23, parent: { kind: 'issue', number: 23 },
    charter_sha256: sha256Body(f.state.binding.charterBody), request: nativeReference(f.current), attempt: '123', status: 'implemented',
    result, warnings: [], limitations: [], summary: 'Native qualification passed.' }, 101, writer);
  const approval = nativeRecord({ schema_version: '3.0', kind: 'task-approval', repository, task: 23, parent: { kind: 'issue', number: 23 },
    charter_sha256: sha256Body(f.state.binding.charterBody), request: nativeReference(f.current), outcome: nativeReference(outcome),
    step: 1, result, warnings: [], limitations: [], verdict: 'APPROVE', summary: 'Accept the immutable qualification result.' }, 102);
  f.state.nativeRecords = [f.current, f.state.nativeRecords[2], outcome, approval]; f.state.pr = null;
  f.receipt.approval = nativeReference(approval); f.state.currentApproval = f.receipt.approval;
  const completed = await continueAfterApproval(f.receipt, f.ports);
  assert.equal(completed.status, 'complete');
  assert.deepEqual(f.calls.filter(call => ['merge', 'prepare', 'launch'].includes(call)), ['prepare', 'launch']);
});

test('same-Task preparation stops before publication when a selected Decision still owns conflicting continuation', async () => {
  const f = sameTaskFixture();
  const payload = extractAuthorityRecord(f.current.body);
  const continuationDecision = nativeRecord({ schema_version: '3.0', kind: 'decision', repository, task: 23,
    parent: { kind: 'issue', number: 23 }, charter_sha256: sha256Body(f.state.binding.charterBody),
    purpose: 'Retain the accepted continuation amendment', amendments: { continuation: payload.continuation },
    supersedes: null, context: [] }, 251);
  payload.decisions.push(nativeReference(continuationDecision));
  f.current = nativeRecord(payload, 100); f.state.nativeRecords[0] = f.current;
  f.state.nativeRecords.push(continuationDecision); f.receipt.request = nativeReference(f.current);
  assert.equal((await continueAfterApproval(f.receipt, f.ports)).reason, 'CONTINUATION_DIRECTION_INCOMPLETE');
  assert.ok(f.calls.includes('merge')); assert.ok(!f.calls.includes('prepare')); assert.ok(!f.calls.includes('launch'));
});
