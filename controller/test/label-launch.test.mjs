import test from 'node:test';
import assert from 'node:assert/strict';
import { currentStep } from '../src/step-metadata.mjs';
import { parseLabelLaunch, labelRunName } from '../src/launch-metadata.mjs';
import { admitEnvelope } from '../src/live-authority.mjs';
import { runAttempt } from '../src/attempt.mjs';
import { createPublicationBroker } from '../src/publication-broker.mjs';
import { fixture, memoryStore } from './fixture.mjs';

const labels = (...names) => names.map(name => ({ name }));
const receipt = e => ({ version: 2, attemptId: e.attemptId, child: 'started', containment: 'reaped',
  result: { status: 'success', summary: 'Implemented authorized work.', validation: ['local checks passed'] } });

test('canonical current Step position is positive, unique and explicit', () => {
  for (const step of [1, 5, 937, Number.MAX_SAFE_INTEGER]) assert.equal(currentStep(labels('enhancement', `step-${step}`)), step);
  for (const [names, code] of [[[], 'STEP_LABEL_MISSING'], [['step-1', 'step-2'], 'STEP_LABEL_MULTIPLE']])
    assert.throws(() => currentStep(labels(...names)), { code });
  for (const name of ['step', 'Step-1', 'step-0', 'step-01', 'step-1.5', 'step-9007199254740992'])
    assert.throws(() => currentStep(labels(name)), { code: 'STEP_LABEL_INVALID' });
});

test('native ready events carry routing identity without allocating Step from their payload', () => {
  for (const eventName of ['issues', 'pull_request_target']) for (const route of ['auto', 'manual']) {
    const isPr = eventName === 'pull_request_target';
    const subject = { number: isPr ? 13 : 12, labels: labels('step-5', `codex-ready-${route}`),
      title: 'Task 12 · Step 5 · Bounded goal', body: 'Authority model: github-native-v1' };
    const event = { action: 'labeled', label: { name: `codex-ready-${route}` }, [isPr ? 'pull_request' : 'issue']: subject };
    const launch = parseLabelLaunch(event, eventName);
    assert.equal(launch.number, subject.number); assert.equal(launch.route, route);
    assert.equal(launch.step, null); assert.equal(launch.issueNumber, undefined);
    assert.match(labelRunName(launch, subject), /Task 12/);
    for (const label of ['step-5', 'enhancement', 'Codex-ready-auto'])
      assert.throws(() => parseLabelLaunch({ ...event, label: { name: label } }, eventName), { code: 'READY_EVENT_REQUIRED' });
    assert.throws(() => parseLabelLaunch({ ...event, action: 'unlabeled' }, eventName), { code: 'READY_EVENT_REQUIRED' });
  }
});

for (const remediation of [false, true]) {
  test(`one fresh ready event runs bounded ${remediation ? 'remediation' : 'implementation'} once`, async t => {
    const f = await fixture(t, { remediation, labelLaunch: true, step: 5 });
    assert.equal(f.envelope.step, 5); assert.equal(f.envelope.readyEventId, 71);
    assert.equal(currentStep(f.issue.labels), 5);
    assert.ok(!(f.pr ?? f.issue).labels.some(l => l.name === 'codex-ready-auto'));
    let calls = 0;
    const run = () => runAttempt({ ...f, execute: async () => { calls++; await f.commit(); return receipt(f.envelope); } });
    assert.equal((await run()).status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
    assert.equal((await run()).status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
    assert.equal(calls, 1); assert.equal(f.pushes(), 1);
    assert.equal(currentStep((await f.api.get('/issues/43')).labels), 5);
    assert.equal((await f.broker.invoke(f.admissionRequest)).resumed, true);
  });
  test(`manual ready event publishes a copyable ${remediation ? 'CR' : 'Issue'} handoff without a worker`, async t => {
    const f = await fixture(t, { remediation, labelLaunch: true, route: 'manual', step: 5 });
    const run = () => runAttempt({ ...f, execute: () => assert.fail('manual started Codex') });
    assert.equal((await run()).status, 'handed-off'); assert.equal((await run()).status, 'handed-off');
    assert.equal(f.comments.length, 1); assert.equal(f.pushes(), 0);
    const prompt = /```text\n([\s\S]*?)\n```/.exec(f.comments[0].body)[1];
    assert.match(prompt, /Task: #42; Step: 5/); assert.match(prompt, /Required starting head:/);
    assert.match(prompt, /base SHA: [a-f0-9]{40}/); assert.ok(prompt.split('\n').length <= 15);
    assert.ok(prompt.includes(`Subagents: ${remediation ? 'Off' : 'On'}`));
    assert.equal(currentStep(f.issue.labels), 5);
  });
}

test('stale, removed, conflicting, unauthorized and rerun ready events fail without mutation', async t => {
  const f = await fixture(t, { labelLaunch: true });
  const subject = { ...f.issue, labels: labels('step-1', 'codex-ready-auto') };
  const fresh = { ...f.run, display_title: labelRunName(f.envelope, subject) };
  const event = structuredClone(f.events[0]);
  for (const [delta, code] of [
    [{ event: { ...event, actor: { login: 'other', type: 'User' } } }, 'READY_EVENT_STALE'],
    [{ event: { ...event, actor: { login: 'example-owner', type: 'Bot' } } }, 'READY_EVENT_STALE'],
    [{ event: { ...event, event: 'unlabeled' } }, 'READY_EVENT_STALE'],
    [{ event: { ...event, created_at: '2026-09-04T11:00:00Z' } }, 'READY_EVENT_STALE'],
    [{ event: { ...event, created_at: '2026-09-04T12:01:00Z' } }, 'READY_EVENT_STALE'],
    [{ run: { ...fresh, run_attempt: 2 } }, 'OWNER_RUN_NOT_ADMITTED'],
    [{ run: { ...fresh, actor: { login: 'other' } } }, 'OWNER_RUN_NOT_ADMITTED'],
    [{ run: { ...fresh, triggering_actor: { login: 'other' } } }, 'OWNER_RUN_NOT_ADMITTED'],
    [{ run: { ...fresh, path: '.github/workflows/other.yml' } }, 'OWNER_RUN_NOT_ADMITTED'],
    [{ labels: labels('step-1', 'codex-ready-auto', 'codex-ready-manual') }, 'READY_LABEL_AMBIGUOUS']
  ]) {
    const api = { ...f.api, getRun: async () => delta.run ?? fresh,
      get: async path => path === '/issues/42' ? { ...subject, labels: delta.labels ?? subject.labels } : f.api.get(path),
      list: async path => path.endsWith('/events') ? [delta.event ?? event] : f.api.list(path) };
    await assert.rejects(admitEnvelope(api, f.admissionRequest, { nextStep: 2 }), { code });
  }
  assert.equal(f.comments.length, 0); assert.equal(f.pushes(), 0);
});

test('a consumed native event holds new admission until the original controller journal is terminal', async t => {
  const f = await fixture(t, { labelLaunch: true });
  const previous = structuredClone(await f.store.get(99));
  f.issue.labels = labels('step-1', 'codex-ready-auto');
  const request = { ...f.admissionRequest, runId: 100 };
  const run = { ...f.run, id: 100, display_title: labelRunName(f.envelope, f.issue) };
  f.api.getRun = async id => structuredClone(id === 100 ? run : { ...f.run, status: 'completed', updated_at: '2026-09-04T12:01:00Z' });
  await assert.rejects(f.broker.invoke(request), { code: 'PREDISPATCH_EXECUTION_EVIDENCE_CONFLICT' });
  f.events.splice(0, f.events.length, { ...f.events[0], id: 73, created_at: '2026-09-04T12:02:00Z' });
  run.created_at = '2026-09-04T12:02:01Z';
  await assert.rejects(f.broker.invoke(request), { code: 'PREDISPATCH_EXECUTION_EVIDENCE_CONFLICT' });
  assert.equal(await f.store.get(100), null);
  assert.deepEqual(await f.store.get(99), previous);
});

test('partial ready-label consumption is an uncertain native effect and never executes on replay', async t => {
  const f = await fixture(t, { labelLaunch: true });
  const record = await f.store.get(99); record.readyConsumed = false; await f.store.put(99, record);
  await assert.rejects(f.broker.invoke(f.admissionRequest), { code: 'READY_CONSUMPTION_UNCERTAIN' });
  assert.equal(f.pushes(), 0);
});

test('a label run cannot target an unrelated Issue even for a blocked Outcome', async t => {
  const f = await fixture(t, { labelLaunch: true });
  const api = { ...f.api, get: async path => path === '/issues/44' ? { ...f.issue, number: 44, labels: [] } : f.api.get(path) };
  const store = memoryStore();
  const broker = createPublicationBroker({ api, store, publisher: f.publisher });
  await assert.rejects(broker.dispatch({ ...f.admissionRequest, number: 44, issueNumber: 44 }), { code: 'OWNER_RUN_NOT_ADMITTED' });
  assert.deepEqual(await store.all(), []); assert.equal(f.comments.length, 0); assert.equal(f.pushes(), 0);
});

test('replacement ready events found after source reads are never consumed', async t => {
  await assert.rejects(fixture(t, { labelLaunch: true, beforeAdmission(f) {
    const get = f.api.get;
    f.api.get = async path => { if (path === '/git/ref/heads/main') f.events[0].id++; return get.call(f.api, path); };
    f.api.delete = f.api.post = async () => assert.fail('replacement command mutated');
  } }), { code: 'READY_EVENT_STALE' });
});

test('a lost ready deletion response retains the exact admitted event and does not repeat deletion', async t => {
  let context, deletes = 0;
  await assert.rejects(fixture(t, { labelLaunch: true, beforeAdmission(f) {
    context = f;
    f.api.delete = async () => { deletes++; throw Object.assign(new Error('lost native response'), { code: 'EIO' }); };
  } }), { code: 'READY_CONSUMPTION_UNCERTAIN' });
  const record = await context.store.get(99);
  assert.equal(record.envelope.readyEventId, 71); assert.equal(record.readyConsumption.status, 'uncertain');
  assert.equal(record.outcome.status, 'BLOCKED'); assert.equal(deletes, 1);
  const broker = createPublicationBroker({ api: context.api, store: context.store, publisher: {} });
  await assert.rejects(broker.dispatch(context.admissionRequest), { code: 'READY_CONSUMPTION_UNCERTAIN' });
  assert.equal(deletes, 1); assert.deepEqual((await context.store.get(99)).outcome, record.outcome);
});
