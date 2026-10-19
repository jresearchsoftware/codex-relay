import test from 'node:test';
import assert from 'node:assert/strict';
import { fixture } from './fixture.mjs';
import { CONSUMER } from '../../consumer/consumer.mjs';

const charter = 'Authority model: github-native-v1\nIssue closure policy: keep-open\nImplement independent source attempts.';
const ownerEvent = (id, event, route = 'auto', created_at = '2026-09-04T12:00:01Z') => ({ id, event,
  actor: { login: CONSUMER.owner, type: 'User' }, label: { name: `codex-ready-${route}` }, created_at });
const options = { issueBody: charter, labelLaunch: true, streamlinedAdmission: true };

test('replacement during Step projection remains visible and is never deleted', async t => {
  let state; let deletes = 0;
  await assert.rejects(fixture(t, { ...options, beforeAdmission(f) {
    state = f;
    f.api.ensureStepLabel = async () => {
      f.events.push(ownerEvent(72, 'unlabeled'), ownerEvent(73, 'labeled', 'manual'));
      f.issue.labels = [{ name: 'codex-ready-manual' }];
    };
    const remove = f.api.delete;
    f.api.delete = path => { deletes++; return remove(path); };
  } }), { code: 'READY_EVENT_REPLACED' });
  assert.equal(deletes, 0);
  assert.ok(state.issue.labels.some(label => label.name === 'codex-ready-manual'));
  const record = await state.store.get(99);
  assert.equal(record.envelope.readyEventId, 71);
  assert.equal(record.readyConsumed, undefined);
  assert.match(record.readyConsumption.diagnostic, /fresh independent attempt/);
});

for (const when of ['before-delete', 'between-delete-and-get']) {
  test(`replacement ${when} is diagnosed by event identity, including same-second transitions`, async t => {
    let state; let deletes = 0; let deleted = false;
    const code = 'READY_EVENT_REPLACED';
    await assert.rejects(fixture(t, { ...options, beforeAdmission(f) {
      state = f;
      const replace = () => {
        const id = Math.max(...f.events.map(event => event.id)) + 1;
        f.events.push(ownerEvent(id, 'unlabeled'), ownerEvent(id + 1, 'labeled'));
        f.issue.labels = [{ name: 'step-1' }, { name: 'codex-ready-auto' }];
      };
      const remove = f.api.delete;
      f.api.delete = async path => {
        deletes++;
        if (when === 'before-delete') replace();
        await remove(path); deleted = true;
      };
      const get = f.api.get;
      f.api.get = async path => {
        if (deleted && path === '/issues/42' && when === 'between-delete-and-get') {
          deleted = false; replace();
        }
        return get(path);
      };
    } }), error => error.code === code && /original event 71/.test(error.details.failureDiagnostic.preview)
      && /later second/.test(error.details.failureDiagnostic.preview));
    assert.equal(deletes, 1);
    const record = await state.store.get(99);
    assert.equal(record.readyConsumed, undefined);
    assert.equal(record.readyConsumption.code, code);
    assert.ok(record.readyConsumption.laterEvents.length >= 3);
    if (when === 'between-delete-and-get') assert.ok(state.issue.labels.some(label => label.name === 'codex-ready-auto'));
  });
}

test('ambiguous native DELETE never retries, even after a lost successful response', async t => {
  let state; let deletes = 0;
  await assert.rejects(fixture(t, { ...options, beforeAdmission(f) {
    state = f;
    const remove = f.api.delete;
    f.api.delete = async path => { deletes++; await remove(path); throw Object.assign(new Error('lost response'), { code: 'EIO' }); };
  } }), { code: 'READY_CONSUMPTION_UNCERTAIN' });
  const { createPublicationBroker } = await import('../src/publication-broker.mjs');
  const broker = createPublicationBroker({ api: state.api, store: state.store, publisher: {} });
  await assert.rejects(broker.dispatch(state.admissionRequest), { code: 'READY_CONSUMPTION_UNCERTAIN' });
  assert.equal(deletes, 1);
  assert.equal((await state.store.get(99)).readyConsumed, undefined);
});

test('multiple labeled native events in one timestamp second require a fresh owner command', async t => {
  let state;
  await assert.rejects(fixture(t, { ...options, beforeAdmission(f) {
    state = f;
    f.events.push(ownerEvent(72, 'unlabeled', 'auto', f.events[0].created_at),
      ownerEvent(73, 'labeled', 'auto', f.events[0].created_at));
    f.api.delete = f.api.post = async () => assert.fail('ambiguous event mutated');
  } }), error => error.code === 'READY_EVENT_AMBIGUOUS' && /No command was consumed/.test(error.details.failureDiagnostic.preview));
  assert.deepEqual(await state.store.all(), []);
});

test('duplicate delivery of one native event does not invent a replacement', async t => {
  const f = await fixture(t, { ...options, beforeAdmission(f) { f.events.push(structuredClone(f.events[0])); } });
  const record = await f.store.get(99);
  assert.equal(record.readyConsumed, true);
  assert.equal(record.readyConsumption.removalEventId, 72);
  assert.equal(record.envelope.readyEventId, 71);
});

test('a later owner command admits a new immutable manual Step despite the original missing Outcome', async t => {
  const f = await fixture(t, { ...options, route: 'manual' });
  const old = await f.store.get(99);
  const next = { ...structuredClone(f.run), id: 100, created_at: '2026-09-04T12:00:04Z' };
  f.api.getRun = async id => structuredClone(id === 99 ? f.run : next);
  f.issue.labels.push({ name: 'codex-ready-manual' });
  f.events.push(ownerEvent(73, 'labeled', 'manual', '2026-09-04T12:00:03Z'));
  const result = await f.broker.invoke({ ...f.admissionRequest, runId: 100 });
  assert.equal(result.envelope.step, 2);
  assert.equal(result.envelope.request.lineage.attempt, 'run-99');
  assert.equal((await f.store.get(99)).outcome, null);
  assert.deepEqual((await f.store.get(99)).envelope, old.envelope);
  assert.equal((await f.broker.invoke(f.admissionRequest)).envelope.step, 1);
  assert.equal(f.issue.labels.find(label => /^step-/.test(label.name)).name, 'step-2');
});
