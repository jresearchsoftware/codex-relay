import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fixture, memoryStore } from './fixture.mjs';
import { createPublicationBroker } from '../src/publication-broker.mjs';
import { createAdmissionControl } from '../src/admission-control.mjs';
import { nextAdmissionStep } from '../src/admission-step.mjs';
import { digest, REPOSITORY } from '../src/execution-contract.mjs';
import { completedPredispatchRecovery } from '../src/predispatch-recovery.mjs';
import { parseRecoveryRequest } from '../src/recover-attempt-publication.mjs';

async function partial(t) {
  let f;
  const journal = memoryStore();
  let busy = false;
  journal.withLock = async (id, action) => {
    if (busy) throw Object.assign(new Error('busy'), { code: 'ATTEMPT_CONTROLLER_BUSY' });
    busy = true;
    try { return await action(); } finally { busy = false; }
  };
  await assert.rejects(fixture(t, { labelLaunch: true, continuation: true, createJournal: () => journal,
    createAdmission: async () => ({ assertOpen: async () => {}, assertSlotComplete: async () => {},
      reserve: async () => ({ version: 1, status: 'active' }) }),
    beforeAdmission(value) {
      f = value; value.issue.labels = [{ name: 'step-1' }, { name: 'codex-ready-auto' }];
      value.api.ensureStepLabel = async () => { throw new TypeError('synthetic projection failure'); };
    } }), { code: 'ADMISSION_STEP_PROJECTION_FAILED' });
  f.run.status = 'completed'; f.run.conclusion = 'failure'; f.run.run_attempt = 1;
  f.run.updated_at = '2026-09-04T12:01:00Z';
  // Model the retained old Writer record, before the pending marker existed.
  const retained = await f.store.get(99);
  delete retained.predispatchPending;
  await f.store.put(99, retained);
  f.original = await f.store.get(99);
  f.journal = journal;
  f.comments = [];
  f.liveHead = f.original.envelope.startHead;
  const get = f.api.get;
  f.api.get = async path => {
    if (path === `/git/ref/heads/${f.original.envelope.branch}`) return { object: { sha: f.liveHead } };
    if (path.startsWith('/issues/comments/')) return structuredClone(f.comments.find(c => c.id === Number(path.split('/').at(-1))));
    return get(path);
  };
  f.checkoutExists = false;
  f.broker = createPublicationBroker({ api: f.api, store: f.store, publisher: {}, journal,
    checkoutAbsent: async () => !f.checkoutExists });
  f.inspect = { operation: 'predispatch-state', runId: 99, attemptId: 'run-99' };
  f.authorize = async () => {
    const state = await f.broker.dispatch(f.inspect);
    const created_at = '2026-09-04T12:02:00Z';
    f.comments.push({ id: 10000, user: { login: 'example-owner', type: 'User' },
      issue_url: `https://api.github.com/repos/${REPOSITORY}/issues/42`,
      created_at, updated_at: created_at, body: state.authorizationBody });
    return { ...f.inspect, operation: 'finalize-predispatch', authorizationId: 10000 };
  };
  return f;
}

test('operator finalizes only the original pre-dispatch reservation; no native mutations or fabricated execution', async t => {
  const f = await partial(t);
  const request = await f.authorize();
  for (const method of ['post', 'patch', 'delete']) f.api[method] = () => assert.fail(`native ${method}`);
  const result = await f.broker.dispatch(request);
  assert.equal(result.recovery.status, 'finalized');
  const record = await f.store.get(99);
  const { predispatchRecovery, ...original } = record;
  assert.deepEqual(original, f.original);
  assert.equal(predispatchRecovery.binding.recordDigest, digest(original));
  assert.ok(completedPredispatchRecovery(record));
  assert.equal(await f.journal.get(99), null);
  assert.equal(record.outcome, null);
  assert.equal(record.controllerLifecycle.status, 'active');
  assert.deepEqual((await f.broker.dispatch(request)).recovery, predispatchRecovery);
  await assert.rejects(f.broker.dispatch({ ...request, authorizationId: 10001 }), { code: 'PREDISPATCH_RECOVERY_BINDING_CHANGED' });
  await assert.rejects(f.broker.dispatch(f.admissionRequest), { code: 'PREDISPATCH_ATTEMPT_FINALIZED' });
  await assert.rejects(f.broker.dispatch({ ...f.inspect, operation: 'terminal-outcome' }), { code: 'PREDISPATCH_ATTEMPT_FINALIZED' });
  const gateRoot = await mkdtemp(join(tmpdir(), 'predispatch-gate-'));
  t.after(() => rm(gateRoot, { recursive: true, force: true }));
  const gate = createAdmissionControl({ root: gateRoot,
    consumerDigest: record.envelope.consumerDigest, store: f.store, journal: f.journal, protectedRoot: false });
  await gate.initialize();
  assert.deepEqual((await gate.status()).active, []);
  assert.deepEqual((await gate.status()).unknown, []);
  await gate.assertSlotComplete('primary');
  await gate.assertTaskComplete(42);
  assert.equal(nextAdmissionStep([record], 42, [{ name: 'step-1' }]).step, 3);
  assert.equal(nextAdmissionStep([record], 42, [{ name: 'step-2' }]).step, 3);
  // A late contradictory journal makes the reservation unknown again.
  await f.journal.put(99, { unexpected: true });
  assert.deepEqual((await gate.status()).unknown, [99]);
});

for (const [name, mutate] of [
  ['ready intent exists', f => { f.original.readyConsumption = { status: 'deleting' }; }],
  ['ready consumed', f => { f.original.readyConsumed = true; }],
  ['projection completed', f => { f.original.stepProjected = true; }],
  ['publication intent', f => { f.original.publicationIntent = { head: 'a'.repeat(40) }; }],
  ['journal exists', f => f.journal.put(99, { execution: null })],
  ['checkout exists', f => { f.checkoutExists = true; }],
  ['rerun', f => { f.run.run_attempt = 2; }],
  ['still running', f => { f.run.status = 'in_progress'; }],
  ['wrong event', f => { f.original.envelope.readyEventId++; }],
  ['wrong head', f => { f.liveHead = 'a'.repeat(40); }],
  ['wrong slot', f => { f.original.envelope.executionSlot = 'foreign-slot'; }],
]) {
  test(`reject ${name} without changing protected state`, async t => {
    const f = await partial(t);
    const request = await f.authorize();
    await mutate(f); await f.store.put(99, f.original);
    const before = await f.store.get(99);
    await assert.rejects(f.broker.dispatch(request));
    assert.deepEqual(await f.store.get(99), before);
  });
}

test('changed record after authorization and forged/edited owner comments fail closed', async t => {
  for (const mutation of [f => { f.original.admissionFailure.extra = true; },
    f => { f.comments.at(-1).user.login = 'foreign'; },
    f => { f.comments.at(-1).updated_at = '2026-09-04T12:03:00Z'; }]) {
    const f = await partial(t); const request = await f.authorize();
    mutation(f); await f.store.put(99, f.original);
    await assert.rejects(f.broker.dispatch(request), { code: 'RECOVERY_OWNER_AUTHORIZATION_INVALID' });
    assert.equal((await f.store.get(99)).predispatchRecovery, undefined);
  }
});

test('controller contention and concurrent/repeated finalization never create a second receipt', async t => {
  const f = await partial(t); const request = await f.authorize();
  const results = await Promise.allSettled([f.broker.dispatch(request), f.broker.dispatch(request)]);
  assert.equal(results.filter(r => r.status === 'fulfilled').length, 1);
  assert.equal(results.find(r => r.status === 'rejected').reason.code, 'ATTEMPT_CONTROLLER_BUSY');
  const record = await f.store.get(99);
  const result = await f.broker.dispatch(request);
  assert.deepEqual(result.recovery, record.predispatchRecovery);
  assert.deepEqual(await f.store.get(99), record);
});

test('bounded recovery request accepts only explicit inspect/finalize arguments', () => {
  const inspect = { operation: 'inspect-predispatch', runId: 99, attemptId: 'run-99' };
  assert.deepEqual(parseRecoveryRequest(inspect), inspect);
  const request = { ...inspect, operation: 'finalize-predispatch', authorizationId: 9 };
  assert.deepEqual(parseRecoveryRequest(request), request);
  assert.throws(() => parseRecoveryRequest({ ...request, head: 'a'.repeat(40) }));
  assert.throws(() => parseRecoveryRequest({ ...request, authorizationId: null }));
});

test('the old native event stays spent and a fresh owner event admits Step 3 in the same PR', async t => {
  const f = await partial(t); const request = await f.authorize();
  await f.broker.dispatch(request);
  const originalRun = structuredClone(f.run);
  const nextRun = { ...originalRun, id: 100, status: 'in_progress', conclusion: null };
  f.api.getRun = async id => structuredClone(id === 99 ? originalRun : nextRun);
  f.api.ensureStepLabel = async () => {};
  const nextRequest = { ...f.admissionRequest, runId: 100 };
  const broker = createPublicationBroker({ api: f.api, store: f.store, publisher: {}, journal: f.journal,
    admission: f.admissionControl, checkoutAbsent: async () => true });
  await assert.rejects(broker.dispatch(nextRequest), { code: 'READY_EVENT_ALREADY_CONSUMED' });
  assert.equal(await f.store.get(100), null);
  const event = f.events.at(-1);
  f.events.push({ ...event, id: event.id + 1, event: 'unlabeled' },
    { ...event, id: event.id + 2, created_at: '2026-09-04T12:03:00Z' });
  nextRun.created_at = '2026-09-04T12:03:01Z';
  const admitted = await broker.dispatch(nextRequest);
  assert.equal(admitted.envelope.step, 3);
  assert.equal(admitted.envelope.continuation.pullRequest, 43);
  assert.equal(admitted.envelope.startHead, f.original.envelope.startHead);
  assert.equal(admitted.envelope.readyEventId, event.id + 2);
  assert.equal((await f.store.get(99)).predispatchRecovery.binding.recordDigest, digest(f.original));
});

for (const accepted of [false, true]) {
  test(`atomic receipt write ${accepted ? 'accepted with lost response' : 'rejected before write'} reconciles without external mutation`, async t => {
    const f = await partial(t); const request = await f.authorize();
    const put = f.store.put; let writes = 0;
    f.store.put = async (id, record) => {
      writes++;
      if (accepted) await put(id, record);
      throw Object.assign(new Error('synthetic storage response loss'), { code: 'EIO' });
    };
    await assert.rejects(f.broker.dispatch(request), { code: 'EIO' });
    assert.equal(Boolean((await f.store.get(99)).predispatchRecovery), accepted);
    f.store.put = async (...args) => { writes++; return put(...args); };
    assert.equal((await f.broker.dispatch(request)).recovery.status, 'finalized');
    assert.equal(writes, accepted ? 1 : 2);
    assert.ok(completedPredispatchRecovery(await f.store.get(99)));
  });
}

test('wrong attempt and a foreign original run actor never authorize retirement', async t => {
  const f = await partial(t); const request = await f.authorize();
  await assert.rejects(f.broker.dispatch({ ...request, attemptId: 'run-100' }), { code: 'ATTEMPT_NOT_ADMITTED' });
  f.run.actor.login = 'foreign';
  await assert.rejects(f.broker.dispatch(request), { code: 'RECOVERY_ORIGINAL_RUN_NOT_COMPLETED' });
  assert.equal((await f.store.get(99)).predispatchRecovery, undefined);
});

test('retire an uncertain ready DELETE only after exact removal evidence and no publication effects', async t => {
  const f = await partial(t);
  const record = await f.store.get(99);
  record.predispatchPending = { version: 1, projectionFrom: record.stepProjectionFrom };
  record.readyConsumption = { status: 'deleting', eventId: record.envelope.readyEventId, label: record.envelope.readyLabel };
  await f.store.put(99, record);
  f.issue.labels = [{ name: 'step-1' }];
  f.events.push({ id: record.envelope.readyEventId + 1, event: 'unlabeled', label: { name: record.envelope.readyLabel },
    actor: { login: 'example-owner', type: 'User' }, created_at: '2026-09-04T12:01:01Z' });
  const request = await f.authorize();
  const native = Object.fromEntries(['post', 'patch', 'delete'].map(method => [method, f.api[method]]));
  for (const method of ['post', 'patch', 'delete']) f.api[method] = () => assert.fail(`native ${method}`);
  const result = await f.broker.dispatch(request);
  assert.equal(result.recovery.version, 2);
  assert.equal(result.recovery.binding.readyRemovalEventId, record.envelope.readyEventId + 1);
  const saved = await f.store.get(99);
  assert.ok(completedPredispatchRecovery(saved));
  assert.equal(saved.readyConsumed, undefined);
  const root = await mkdtemp(join(tmpdir(), 'ready-reconcile-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const gate = createAdmissionControl({ root, consumerDigest: saved.envelope.consumerDigest, store: f.store,
    journal: f.journal, checkoutAbsent: async () => true, protectedRoot: false });
  await gate.initialize();
  assert.deepEqual((await gate.status()).unknown, []);
  await assert.rejects(f.broker.dispatch(f.admissionRequest), { code: 'PREDISPATCH_ATTEMPT_FINALIZED' });
  assert.deepEqual((await f.broker.dispatch(request)).recovery, result.recovery);
  await assert.rejects(f.broker.dispatch({ ...request, authorizationId: 10001 }), { code: 'PREDISPATCH_RECOVERY_BINDING_CHANGED' });
  const originalRun = structuredClone(f.run);
  const nextRun = { ...originalRun, id: 100, status: 'in_progress', conclusion: null,
    created_at: '2026-09-04T12:03:01Z' };
  f.api.getRun = async id => structuredClone(id === 99 ? originalRun : nextRun);
  f.api.ensureStepLabel = async () => {};
  f.issue.labels.push({ name: record.envelope.readyLabel });
  f.events.push({ id: record.envelope.readyEventId + 2, event: 'labeled',
    label: { name: record.envelope.readyLabel }, actor: { login: 'example-owner', type: 'User' },
    created_at: '2026-09-04T12:03:00Z' });
  Object.assign(f.api, native);
  const nextBroker = createPublicationBroker({ api: f.api, store: f.store, publisher: {}, journal: f.journal,
    admission: f.admissionControl, checkoutAbsent: async () => true });
  const admitted = await nextBroker.dispatch({ ...f.admissionRequest, runId: 100 });
  assert.equal(admitted.envelope.step, 3);
  assert.equal(admitted.envelope.readyEventId, record.envelope.readyEventId + 2);
  assert.deepEqual((await f.store.get(99)).predispatchRecovery, result.recovery);
});

test('ready reconciliation refuses missing removal, replacement and pending comment publication', async t => {
  for (const scenario of ['missing', 'replacement', 'comment']) {
    const f = await partial(t);
    const record = await f.store.get(99);
    record.predispatchPending = { version: 1, projectionFrom: record.stepProjectionFrom };
    record.readyConsumption = { status: 'deleting', eventId: record.envelope.readyEventId, label: record.envelope.readyLabel };
    if (scenario === 'comment') record.commentIntent = { uncertain: true };
    await f.store.put(99, record);
    f.issue.labels = [{ name: 'step-1' }];
    if (scenario !== 'missing') f.events.push({ id: record.envelope.readyEventId + 1, event: 'unlabeled',
      label: { name: record.envelope.readyLabel }, created_at: '2026-09-04T12:01:01Z' });
    if (scenario === 'replacement') f.events.push({ id: record.envelope.readyEventId + 2, event: 'labeled',
      label: { name: record.envelope.readyLabel }, created_at: '2026-09-04T12:01:02Z' });
    await assert.rejects(f.broker.dispatch(f.inspect));
    assert.deepEqual(await f.store.get(99), record);
  }
});

test('ready recovery rechecks event evidence after owner authorization', async t => {
  const f = await partial(t);
  const record = await f.store.get(99);
  record.predispatchPending = { version: 1, projectionFrom: record.stepProjectionFrom };
  record.readyConsumption = { status: 'deleting', eventId: record.envelope.readyEventId, label: record.envelope.readyLabel };
  await f.store.put(99, record);
  f.issue.labels = [{ name: 'step-1' }];
  f.events.push({ id: record.envelope.readyEventId + 1, event: 'unlabeled', label: { name: record.envelope.readyLabel },
    created_at: '2026-09-04T12:01:01Z' });
  const request = await f.authorize();
  f.events.push({ id: record.envelope.readyEventId + 2, event: 'labeled', label: { name: record.envelope.readyLabel },
    created_at: '2026-09-04T12:01:02Z' });
  await assert.rejects(f.broker.dispatch(request), { code: 'READY_RECONCILIATION_UNPROVEN' });
  assert.deepEqual(await f.store.get(99), record);
});
