import test from 'node:test';
import assert from 'node:assert/strict';
import { CONSUMER } from '../../consumer/consumer.mjs';
import { admitEnvelope, revalidateReadyEvent } from '../src/live-authority.mjs';
import { createPublicationBroker } from '../src/publication-broker.mjs';
import { fixture } from './fixture.mjs';
import { harness } from './independent-admission-fixture.mjs';

const rejection = reason => ({ code: 'OWNER_RUN_NOT_ADMITTED', details: { reason } });

// Observe both the guard and the real admission boundary: a diagnostic must
// never turn an unauthenticated native run into a reservation or publication.
async function refused(f, { reason, run = {}, subject = {}, removeRunField }) {
  const observedRun = { ...structuredClone(f.run), ...run };
  if (removeRunField) delete observedRun[removeRunField];
  const subjectPath = f.admissionRequest.target === 'issue' ? '/issues/42' : '/pulls/43';
  const mutations = [];
  const api = { ...f.api,
    getRun: async () => structuredClone(observedRun),
    get: async path => {
      const value = await f.api.get(path);
      return path === subjectPath ? { ...value, ...structuredClone(subject) } : value;
    }
  };
  for (const operation of ['post', 'patch', 'delete', 'ensureStepLabel', 'ready', 'draft']) {
    api[operation] = async (...args) => {
      mutations.push({ operation, args });
      assert.fail(`Rejected owner run attempted ${operation}`);
    };
  }
  const before = { issue: structuredClone(f.issue), pr: structuredClone(f.pr),
    events: structuredClone(f.events), records: await f.store.all() };
  await assert.rejects(admitEnvelope(api, f.admissionRequest, { nextStep: f.envelope.step }), rejection(reason));
  const broker = createPublicationBroker({ api, store: f.store,
    publisher: { inspect: async () => assert.fail('Rejected owner run reached Git publication') } });
  await assert.rejects(broker.dispatch(f.admissionRequest), rejection(reason));
  assert.deepEqual(mutations, []);
  assert.deepEqual(await f.store.all(), before.records);
  assert.deepEqual(f.issue, before.issue);
  assert.deepEqual(f.pr, before.pr);
  assert.deepEqual(f.events, before.events);
  assert.deepEqual(f.comments, []);
  assert.equal(f.pushes(), 0);
}

test('owner run predicates retain categorical reasons without reserving or mutating native state', async t => {
  const f = await fixture(t, { labelLaunch: true, deferAdmission: true });
  for (const entry of [
    { reason: 'run_id', run: { id: f.run.id + 1 } },
    { reason: 'repository', run: { repository: { full_name: 'other/repository' } } },
    { reason: 'actor', run: { actor: { login: 'other-owner' } } },
    { reason: 'triggering_actor', run: { triggering_actor: { login: 'other-owner' } } },
    { reason: 'workflow_path', run: { path: '.github/workflows/other.yml' } },
    { reason: 'event', run: { event: 'workflow_dispatch' } },
    { reason: 'head_branch', run: { head_branch: 'untrusted-branch' } },
    { reason: 'run_attempt', run: { run_attempt: 2 } },
    { reason: 'run_title', run: { display_title: 'Auto implementation · Task 99 · codex-ready-auto' } },
    { reason: 'run_title', run: { display_title: 'Manual handoff · Task 42 · codex-ready-manual' } },
    { reason: 'run_title', run: { display_title: 'Auto implementation · Task 42 · Step 1' } },
    { reason: 'run_title', run: { display_title: 'Auto implementation · Task 42 · codex-ready-auto · codex-ready-auto' } },
    { reason: 'subject_number', subject: { number: 99 } },
    { reason: 'issue_kind', subject: { pull_request: { url: 'https://example.test/pull/42' } } }
  ]) await t.test(entry.reason + ' ' + JSON.stringify(entry.run ?? entry.subject), () => refused(f, entry));
  assert.deepEqual(await f.store.all(), []);
});

test('only an in-progress first native run may pass the owner status predicate', async t => {
  const f = await fixture(t, { labelLaunch: true, deferAdmission: true });
  for (const status of ['queued', 'pending', 'waiting', 'completed']) {
    await t.test(status, () => refused(f, { reason: 'status', run: { status } }));
  }
  await t.test('missing status', () => refused(f, { reason: 'status', removeRunField: 'status' }));
  const admitted = await admitEnvelope(f.api, f.admissionRequest, { nextStep: f.envelope.step });
  assert.equal(admitted.runId, f.run.id);
  assert.deepEqual(await f.store.all(), []);
});

test('automatic label admission reobserves the same queued run before allocating the admitted envelope', async t => {
  const f = await fixture(t, { labelLaunch: true, deferAdmission: true });
  let reads = 0;
  let previousBudget = 10_000;
  const api = { ...f.api, getRun: async (id, options) => {
    assert.equal(id, f.run.id);
    assert.deepEqual(await f.store.all(), []);
    assert.deepEqual(f.issue.labels, [{ name: 'codex-ready-auto' }]);
    if (reads === 0) assert.equal(options, undefined);
    else {
      assert(options.deadlineMs > 0 && options.deadlineMs < previousBudget);
      previousBudget = options.deadlineMs;
    }
    reads += 1;
    return { ...f.run, status: reads < 3 ? 'queued' : 'in_progress' };
  } };
  const admitted = await admitEnvelope(api, f.admissionRequest, { nextStep: f.envelope.step });
  assert.equal(admitted.runId, f.run.id);
  assert.equal(admitted.readyEventId, f.envelope.readyEventId);
  assert.equal(admitted.step, f.envelope.step);
  assert.equal(reads, 3);
});

test('queued run reobservation checks authority again and stops if the run has ended', async t => {
  const f = await fixture(t, { labelLaunch: true, deferAdmission: true });
  for (const [followup, reason] of [
    [{ status: 'in_progress', run_attempt: 2 }, 'run_attempt'],
    [{ status: 'completed' }, 'status']
  ]) {
    const observations = [{ ...f.run, status: 'queued' }, { ...f.run, ...followup }];
    const api = { ...f.api, getRun: async id => {
      assert.equal(id, f.run.id);
      assert(observations.length);
      return observations.shift();
    } };
    await assert.rejects(admitEnvelope(api, f.admissionRequest, { nextStep: f.envelope.step }), rejection(reason));
    assert.deepEqual(observations, []);
    assert.deepEqual(await f.store.all(), []);
    assert.deepEqual(f.issue.labels, [{ name: 'codex-ready-auto' }]);
  }
});

test('dispatch title rejection uses the same category as label title rejection', async t => {
  const f = await fixture(t, { deferAdmission: true });
  await refused(f, { reason: 'run_title', run: { display_title: 'Auto implementation · Task 42 · Step 99' } });
});

test('PR owner-run target predicates identify repository and branch mismatches', async t => {
  const f = await fixture(t, { remediation: true, labelLaunch: true, deferAdmission: true });
  for (const entry of [
    { reason: 'subject_number', subject: { number: 99 } },
    { reason: 'pr_base_repository', subject: { base: { ...f.pr.base, repo: { full_name: 'other/repository' } } } },
    { reason: 'pr_head_repository', subject: { head: { ...f.pr.head, repo: { full_name: 'other/repository' } } } },
    { reason: 'pr_head_branch', run: { head_branch: 'untrusted-branch' } }
  ]) await t.test(entry.reason, () => refused(f, entry));
  // GitHub may describe a PR target run with either its base or its head ref.
  const api = { ...f.api, getRun: async () => ({ ...f.run, head_branch: f.pr.head.ref }) };
  assert.equal((await admitEnvelope(api, f.admissionRequest, { nextStep: f.envelope.step })).number, 43);
});

test('owner-run reasons preserve first-failure precedence', async t => {
  const f = await fixture(t, { labelLaunch: true, deferAdmission: true });
  await refused(f, { reason: 'run_id', run: { id: f.run.id + 1, status: 'completed', display_title: 'unbound' },
    subject: { number: 99 } });
  await refused(f, { reason: 'actor', run: { actor: { login: 'other-owner' }, status: 'completed' } });
  await refused(f, { reason: 'status', run: { status: 'completed', path: '.github/workflows/other.yml' } });
  await refused(f, { reason: 'subject_number', run: { display_title: 'unbound' }, subject: { number: 99 } });
});

test('an absent triggering actor retains the existing supported admission behavior', async t => {
  const f = await fixture(t, { labelLaunch: true, deferAdmission: true });
  for (const triggeringActor of [undefined, { login: CONSUMER.owner }]) {
    const run = structuredClone(f.run);
    if (triggeringActor === undefined) delete run.triggering_actor;
    else run.triggering_actor = triggeringActor;
    const api = { ...f.api, getRun: async () => structuredClone(run) };
    assert.equal((await admitEnvelope(api, f.admissionRequest, { nextStep: f.envelope.step })).runId, f.run.id);
  }
});

test('the incident-shaped Task 96 command-only title is supported without a Step in the run name', async t => {
  const f = await harness(t, { tasks: [96] });
  const request = f.ready(43448389613, 96, 'auto');
  const run = f.runs.get(request.runId);
  run.triggering_actor = { login: CONSUMER.owner };
  assert.equal(run.display_title, 'Auto implementation · Task 96 · codex-ready-auto');
  const admitted = await admitEnvelope(f.api, request, { nextStep: 1 });
  assert.equal(admitted.issueNumber, 96);
  assert.equal(admitted.step, 1);
  assert.deepEqual(await f.store.all(), []);
  assert.equal(f.deletes(), 0);
  assert.deepEqual(f.comments, []);
});

test('ready-event revalidation retains the subject-number rejection category', async t => {
  const f = await fixture(t, { labelLaunch: true, deferAdmission: true });
  const api = { ...f.api, get: async path => path === '/issues/42'
    ? { ...f.issue, number: 99 } : f.api.get(path) };
  await assert.rejects(revalidateReadyEvent(api, f.envelope), rejection('subject_number'));
  assert.deepEqual(await f.store.all(), []);
  assert.deepEqual(f.comments, []);
});
