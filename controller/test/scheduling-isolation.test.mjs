import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { CONSUMER, CONSUMER_DIGEST } from '../../consumer/consumer.mjs';
import { createPublicationBroker } from '../src/publication-broker.mjs';
import { createAdmissionControl } from '../src/admission-control.mjs';
import { createOnDemandDispatchAdapter } from '../src/github.mjs';
import { runAttempt } from '../src/attempt.mjs';
import { REPOSITORY, WRITER, digest } from '../src/execution-contract.mjs';
import { labelRunName } from '../src/launch-metadata.mjs';
import { memoryStore } from './fixture.mjs';

const copy = value => structuredClone(value);
const head = 'a'.repeat(40);
const foreignRepository = 'synthetic-other/relay-consumer';
const charter = 'Authority model: github-native-v1\n\nIssue closure policy: keep-open\n\nImplement a bounded repository change.';
const operationId = '12345678-1234-1234-1234-123456789abc';

// This fixture calls the actual admission and Writer APIs in a fixed consumer.
// Native Actions scheduling and a multi-repository Writer are not simulated.
function harness(root = tmpdir()) {
  const store = memoryStore(); const journal = memoryStore();
  const control = createAdmissionControl({ root, consumerDigest: CONSUMER_DIGEST,
    store, journal, protectedRoot: false });
  const issues = new Map([42, 44].map(number => [number, { id: 1000 + number, number,
    title: `Task ${number} — Scheduling fixture`, state: 'open', user: { login: CONSUMER.owner },
    body: charter, labels: [{ name: 'codex-ready-auto' }] }]));
  const pr = { number: 43, body: 'Related to #42', state: 'open', merged: false,
    head: { ref: `${CONSUMER.taskBranchPrefix}task-42`, sha: head, repo: { full_name: REPOSITORY } },
    base: { ref: CONSUMER.baseBranch, sha: head, repo: { full_name: REPOSITORY } } };
  const runs = new Map(); const events = new Map(); const mutations = [];
  const api = {
    getRun: async id => copy(runs.get(id)),
    userIdentity: async login => ({ login, id: 701, type: 'Bot' }),
    async get(path) {
      if (path === '/pulls/43') return copy(pr);
      if (/^\/issues\/(42|44)$/.test(path)) return copy(issues.get(Number(path.split('/').at(-1))));
      if (path.startsWith('/git/ref/heads/')) return { object: { sha: head } };
      if (path.startsWith('/git/matching-refs/heads/')) return [];
      throw new Error(`Unexpected GET ${path}`);
    },
    async list(path) {
      if (path.endsWith('/events')) return copy(events.get(Number(path.split('/')[2])) ?? []);
      if (path.endsWith('/comments') || path.startsWith('/pulls?')) return [];
      throw new Error(`Unexpected list ${path}`);
    },
    async ensureStepLabel(step) { mutations.push(['step-label', step]); },
    async patch(path, body) {
      mutations.push(['patch', path]);
      const issue = issues.get(Number(path.split('/').at(-1)));
      assert.deepEqual(Object.keys(body), ['labels']);
      issue.labels = body.labels.map(name => ({ name })); return copy(issue);
    },
    async delete(path) {
      mutations.push(['delete', path]);
      const issue = issues.get(Number(path.split('/')[2]));
      issue.labels = issue.labels.filter(label => label.name !== path.split('/').at(-1));
      const label = decodeURIComponent(path.split('/').at(-1));
      if (label.startsWith('codex-ready-')) {
        const history = events.get(issue.number) ?? [];
        history.push({ id: Math.max(...history.map(event => event.id)) + 1, event: 'unlabeled',
          actor: { login: WRITER, type: 'Bot' }, label: { name: label }, created_at: '2026-09-04T12:00:01Z' });
        events.set(issue.number, history);
      }
    },
    async post(path, body) {
      if (!/^\/issues\/\d+\/labels$/.test(path)) assert.fail('Rejected scheduling input must not publish');
      mutations.push(['post-labels', path]);
      const issue = issues.get(Number(path.split('/')[2]));
      for (const name of body.labels) if (!issue.labels.some(label => label.name === name)) issue.labels.push({ name });
      return copy(issue.labels);
    },
    async draft() { assert.fail('Rejected scheduling input must not change PR lifecycle'); }
  };
  // The fixture isolates Task inventory semantics from privileged filesystem
  // gate checks. Installed flock/gate qualification belongs to Linux tests.
  const admission = { assertOpen: async () => {}, reserve: async () => ({ version: 1, status: 'active' }),
    assertSlotComplete: slot => control.assertSlotComplete(slot) };
  const broker = createPublicationBroker({ api, store, journal, admission, publisher: {
    inspect: async () => assert.fail('Rejected scheduling input must not publish Git') }, streamlinedAdmission: true });
  function ready(runId, number, { target = 'issue', repository = REPOSITORY, route = 'auto' } = {}) {
    const subject = target === 'issue' ? issues.get(number) : pr;
    subject.labels = [...(subject.labels ?? []).filter(label => !label.name.startsWith('codex-ready-')), { name: `codex-ready-${route}` }];
    const launch = { route, target, number };
    runs.set(runId, { id: runId, repository: { full_name: repository }, actor: { login: CONSUMER.owner },
      status: 'in_progress', event: target === 'issue' ? 'issues' : 'pull_request_target',
      head_branch: CONSUMER.baseBranch, display_title: labelRunName(launch, subject),
      path: CONSUMER.routingWorkflow, run_attempt: 1, created_at: '2026-09-04T12:00:01Z' });
    events.set(number, [{ id: runId + 1000, event: 'labeled', actor: { login: CONSUMER.owner, type: 'User' },
      label: { name: `codex-ready-${route}` }, created_at: '2026-09-04T12:00:00Z' }]);
    return { operation: 'admit', runId, target, number, route, transport: 'label', step: null };
  }
  return { store, journal, control, issues, runs, mutations, broker, ready };
}

test('colliding Task, PR and run numbers from a foreign repository cannot reserve a child or reach Writer mutation', async () => {
  const f = harness();
  const admitted = await f.broker.dispatch(f.ready(99, 42));
  for (const target of ['issue', 'pull_request']) {
    const local = { ...admitted.envelope, target, number: target === 'issue' ? 42 : 43 };
    const foreign = { ...local, repository: foreignRepository };
    let children = 0; let reservations = 0; let callbacks = 0;
    const dispatcher = createOnDemandDispatchAdapter({ spawnImpl: () => { children++; assert.fail('Foreign child'); },
      reserveDiagnostic: async () => { reservations++; assert.fail('Foreign reservation'); } });
    await assert.rejects(dispatcher.dispatch(foreign), { code: 'EXECUTION_ENVELOPE_INVALID' });
    await assert.rejects(runAttempt({ envelope: foreign, broker: { invoke: () => { callbacks++; } },
      journal: f.journal, prepare: () => { callbacks++; }, execute: () => { children++; }, collect: () => { callbacks++; } }),
    { code: 'EXECUTION_ENVELOPE_INVALID' });
    const record = await f.store.get(99); record.envelope = foreign; await f.store.put(99, record);
    const before = copy(f.mutations);
    await assert.rejects(f.broker.dispatch({ operation: 'preflight', runId: 99, attemptId: 'run-99' }),
      { code: 'EXECUTION_ENVELOPE_INVALID' });
    assert.deepEqual(f.mutations, before);
    assert.equal(children, 0); assert.equal(reservations, 0); assert.equal(callbacks, 0);
    record.envelope = admitted.envelope; await f.store.put(99, record);
  }
});

test('a foreign native run with identical numeric identities cannot create an admission or consume its ready label', async () => {
  const f = harness(); const request = f.ready(99, 42, { repository: foreignRepository });
  await assert.rejects(f.broker.dispatch(request), { code: 'OWNER_RUN_NOT_ADMITTED' });
  assert.equal(await f.store.get(99), null); assert.deepEqual(f.mutations, []);
  assert.deepEqual(f.issues.get(42).labels, [{ name: 'codex-ready-auto' }]);
});

test('a SERIAL physical slot is exclusive across Tasks, while independent manual work may proceed', async () => {
  const f = harness(); const first = await f.broker.dispatch(f.ready(99, 42));
  for (const request of [f.ready(100, 42), f.ready(101, 43, { target: 'pull_request' })]) {
    const before = copy(f.mutations);
    await assert.rejects(f.broker.dispatch(request), { code: 'EXECUTION_SLOT_UNAVAILABLE' });
    assert.equal(await f.store.get(request.runId), null); assert.deepEqual(f.mutations, before);
  }
  await assert.rejects(f.broker.dispatch(f.ready(102, 44)), { code: 'EXECUTION_SLOT_UNAVAILABLE' });
  const independent = await f.broker.dispatch(f.ready(103, 44, { route: 'manual' }));
  assert.equal(independent.envelope.step, 1); assert.equal(independent.envelope.issueNumber, 44);
  assert.notEqual(independent.envelope.branch, first.envelope.branch);
  assert.deepEqual((await f.store.get(99)).envelope, first.envelope);
  assert.equal((await f.store.get(103)).controllerLifecycle, undefined);
});

for (const priorState of ['cancelled-unknown', 'interrupted-no-journal', 'recovery-pending']) {
  test(`${priorState} predecessor holds its actual resource without occupying an independent manual identity`, async () => {
    const f = harness(); await f.broker.dispatch(f.ready(99, 42));
    const record = await f.store.get(99);
    record.outcome = { status: 'BLOCKED', head: null, outcomeId: 801 };
    if (priorState === 'cancelled-unknown') {
      await f.journal.put(99, { version: 2, envelope: record.envelope, outcome: record.outcome,
        execution: { reserved: true, returned: true, child: 'unknown', containment: 'unknown' } });
      f.runs.get(99).status = 'completed'; f.runs.get(99).conclusion = 'cancelled';
    } else if (priorState === 'recovery-pending') {
      record.controllerLifecycle = { version: 1, status: 'complete', child: 'started', containment: 'reaped' };
      record.prepublicationRecovery = { complete: false };
    }
    await f.store.put(99, record);
    const originalDigest = digest(record);
    const before = copy(f.mutations);
    if (priorState === 'recovery-pending') {
      // Historical physical completion releases the slot. Recovery remains an
      // exact publication operation and a global lifecycle drain boundary.
      const next = await f.broker.dispatch(f.ready(100, 42));
      assert.equal(next.envelope.step, 2);
      assert.deepEqual(await f.control.complete({ runId: 99, attemptId: 'run-99' }), { complete: true });
      await assert.rejects(f.control.assertTaskComplete(42), { code: 'PRIOR_EXECUTION_UNRESOLVED' });
    } else {
      await assert.rejects(f.broker.dispatch(f.ready(100, 42)), { code: 'EXECUTION_SLOT_UNAVAILABLE' });
      await assert.rejects(f.control.complete({ runId: 99, attemptId: 'run-99' }), { code: 'ADMISSION_COMPLETION_UNKNOWN' });
      assert.equal(await f.store.get(100), null); assert.deepEqual(f.mutations, before);
    }
    assert.equal(digest(await f.store.get(99)), originalDigest);
    const independent = await f.broker.dispatch(f.ready(101, 44, { route: 'manual' }));
    assert.equal(independent.envelope.step, 1);
  });
}

test('drain observes every admitted Task and pending recovery even after one controller completes',
  { skip: process.platform === 'win32' && 'Filesystem gate proof runs on Linux' }, async t => {
    const root = await mkdtemp(join(tmpdir(), 'relay-scheduling-isolation-'));
    t.after(() => rm(root, { recursive: true, force: true }));
    const f = harness(root); await f.control.initialize();
    await f.broker.dispatch(f.ready(99, 42));
    const finish = async runId => {
      const record = await f.store.get(runId);
      record.outcome = { status: 'BLOCKED', head: null, outcomeId: runId + 800 };
      await f.store.put(runId, record);
      await f.journal.put(runId, { version: 2, envelope: record.envelope, outcome: record.outcome,
        execution: { reserved: true, returned: true, child: 'started', containment: 'reaped' } });
      await f.control.complete({ runId, attemptId: `run-${runId}` });
    };
    await finish(99); await f.broker.dispatch(f.ready(100, 44));
    await f.control.quiesce({ operationId, target: head });
    const waiting = await f.control.drained({ operationId });
    assert.equal(waiting.drained, false); assert.deepEqual(waiting.active, [100]);
    await finish(100);
    const record = await f.store.get(99); record.prepublicationRecovery = { complete: false };
    await f.store.put(99, record);
    await assert.rejects(f.control.drained({ operationId }), { code: 'ADMISSION_DRAIN_UNKNOWN' });
    assert.equal((await f.control.read()).phase, 'quiesced');
    assert.deepEqual((await f.control.status({ operationId })).unknown, [99]);
  });
