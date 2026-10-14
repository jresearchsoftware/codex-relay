import test from 'node:test';
import assert from 'node:assert/strict';
import { CONSUMER } from '../../consumer/consumer.mjs';
import { admitEnvelope, revalidateReadyEvent } from '../src/live-authority.mjs';

// Exercise the real admission checks with read-only native-record responses.
// This fixture does not model or qualify GitHub Actions queue implementation.
function readyCommand({ route = 'auto', creationGap = 1000 } = {}) {
  const event = { id: 71, event: 'labeled', actor: { login: CONSUMER.owner, type: 'User' },
    label: { name: `codex-ready-${route}` }, created_at: '2026-10-14T12:00:00Z' };
  const subject = { number: 42, labels: [event.label] };
  const run = { id: 99, repository: { full_name: CONSUMER.repository }, actor: { login: CONSUMER.owner },
    status: 'in_progress', event: 'issues', head_branch: CONSUMER.baseBranch,
    path: CONSUMER.routingWorkflow, run_attempt: 1,
    created_at: new Date(Date.parse(event.created_at) + creationGap).toISOString() };
  const events = [event];
  const mutations = [];
  const api = {
    getRun: async () => structuredClone(run),
    get: async path => { assert.equal(path, '/issues/42'); return structuredClone(subject); },
    list: async path => { assert.equal(path, '/issues/42/events'); return structuredClone(events); },
    post: async (...args) => { mutations.push(args); assert.fail('Ready validation mutated GitHub'); },
    patch: async (...args) => { mutations.push(args); assert.fail('Ready validation mutated GitHub'); },
    delete: async (...args) => { mutations.push(args); assert.fail('Ready validation mutated GitHub'); },
  };
  const envelope = { runId: run.id, number: subject.number, route,
    readyEventId: event.id, readyEventAt: event.created_at };
  return { api, envelope, event, events, subject, run, mutations };
}

test('waiting beyond two minutes preserves a ready event bound at native run creation', async t => {
  t.mock.timers.enable({ apis: ['Date'], now: new Date('2026-10-14T13:00:00Z') });
  for (const route of ['auto', 'manual']) {
    const f = readyCommand({ route });
    assert.ok(Date.now() - Date.parse(f.event.created_at) > 120000);
    await revalidateReadyEvent(f.api, f.envelope);
    assert.deepEqual(f.mutations, []);
    assert.deepEqual(f.subject.labels, [f.event.label]);
  }
});

test('run-creation freshness stays bounded even after a valid queue wait', async () => {
  for (const creationGap of [0, 120000]) {
    const f = readyCommand({ creationGap });
    await revalidateReadyEvent(f.api, f.envelope);
  }
  for (const creationGap of [-1, 120001]) {
    const f = readyCommand({ creationGap });
    await assert.rejects(revalidateReadyEvent(f.api, f.envelope), { code: 'READY_EVENT_STALE' });
    assert.deepEqual(f.mutations, []);
  }
});

test('a waiting run cannot consume a removed or replacement ready command', async () => {
  for (const transition of ['unlabeled', 'labeled']) {
    const f = readyCommand();
    f.events.push({ ...f.event, id: 72, event: transition });
    await assert.rejects(revalidateReadyEvent(f.api, f.envelope), { code: 'READY_EVENT_STALE' });
    assert.deepEqual(f.mutations, []);
  }
  const f = readyCommand();
  f.subject.labels = [];
  await assert.rejects(revalidateReadyEvent(f.api, f.envelope), { code: 'READY_LABEL_AMBIGUOUS' });
  assert.deepEqual(f.mutations, []);
});

test('a canceled pending run or native rerun cannot create a fresh admission', async () => {
  for (const state of [{ status: 'completed', conclusion: 'cancelled' }, { run_attempt: 2 }]) {
    const f = readyCommand();
    Object.assign(f.run, state);
    await assert.rejects(admitEnvelope(f.api, { runId: f.run.id, target: 'issue', number: 42,
      route: 'auto', transport: 'label' }, { streamlined: true, nextStep: 1 }),
    { code: 'OWNER_RUN_NOT_ADMITTED' });
    assert.deepEqual(f.mutations, []);
    assert.deepEqual(f.subject.labels, [f.event.label]);
  }
});
