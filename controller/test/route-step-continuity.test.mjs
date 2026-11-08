import test from 'node:test';
import assert from 'node:assert/strict';
import { fixture } from './fixture.mjs';
import { REPOSITORY } from '../src/execution-contract.mjs';
import { currentStep } from '../src/step-metadata.mjs';

const charter = 'Authority model: github-native-v1\nIssue closure policy: keep-open\nDeliver the admitted bounded repository work.';
const copy = value => structuredClone(value);
const prior = step => ({ envelope: { repository: REPOSITORY, issueNumber: 42, target: 'issue', number: 42,
  step, runId: 98, attemptId: 'run-98', route: 'manual' }, outcome: { status: 'BLOCKED' } });

for (const route of ['auto', 'manual']) {
  for (const [position, previous, expected] of [[null, null, 1], [null, 3, 4], [3, 3, 4], [5, 3, 6], [5, null, 6]]) {
    test(`${route} admission continues Issue Step ${position ?? 'absent'} / Writer Step ${previous ?? 'absent'} as ${expected}`, async t => {
      const f = await fixture(t, { issueBody: charter, route, labelLaunch: true, streamlinedAdmission: true,
        beforeAdmission: async ({ issue, store }) => {
          issue.labels = [{ name: `codex-ready-${route}` }, ...(position ? [{ name: `step-${position}` }] : [])];
          if (previous) await store.put(98, prior(previous));
        } });
      assert.equal(f.envelope.step, expected);
      assert.equal(currentStep(f.issue.labels), expected);
      assert.equal((await f.store.get(99)).stepProjected, true);
      assert.equal((await f.store.get(99)).stepProjectionFrom, undefined);
      assert.equal(f.envelope.request.lineage?.step ?? null, previous);
      const original = copy(f.envelope);
      f.issue.labels = [{ name: `step-${expected + 7}` }];
      const replay = await f.broker.invoke(f.admissionRequest);
      assert.equal(replay.resumed, true); assert.deepEqual(replay.envelope, original);
      assert.equal(currentStep(f.issue.labels), expected + 7, 'same-attempt replay cannot rewrite a later owner position');
      if (previous) assert.deepEqual(await f.store.get(98), prior(previous));
    });
  }

  for (const [labels, code] of [
    [['step-2'], 'STEP_LABEL_BEHIND_ADMISSION'], [['step-3', 'step-5'], 'STEP_LABEL_MULTIPLE'],
    [['step-invalid'], 'STEP_LABEL_INVALID'], [[`step-${Number.MAX_SAFE_INTEGER}`], 'AUTHORITY_STEP_INVALID']
  ]) test(`${route} rejects ${labels.join(', ')} without allocating or projecting a Step`, async t => {
    let context;
    await assert.rejects(fixture(t, { issueBody: charter, route, labelLaunch: true, streamlinedAdmission: true,
      beforeAdmission: async value => {
        context = value;
        value.issue.labels = [{ name: `codex-ready-${route}` }, ...labels.map(name => ({ name }))];
        await value.store.put(98, prior(3));
      } }), { code });
    assert.equal(await context.store.get(99), null);
    assert.deepEqual(context.issue.labels.map(label => label.name), [`codex-ready-${route}`, ...labels]);
    assert.deepEqual(await context.store.get(98), prior(3));
  });
}

test('a changed Issue numbering position during admission stops before durable reservation or projection', async t => {
  let context;
  await assert.rejects(fixture(t, { issueBody: charter, labelLaunch: true, streamlinedAdmission: true,
    beforeAdmission: value => {
      context = value;
      const get = value.api.get.bind(value.api);
      value.api.get = async path => {
        if (path.startsWith('/git/ref/heads/')) value.issue.labels = [{ name: 'codex-ready-auto' }, { name: 'step-7' }];
        return get(path);
      };
    } }), { code: 'STEP_LABEL_POSITION_CHANGED' });
  assert.equal(await context.store.get(99), null);
  assert.equal(currentStep(context.issue.labels), 7);
  assert.ok(context.issue.labels.some(label => label.name === 'codex-ready-auto'));
});

test('an owner position change after durable admission leaves a recoverable same-attempt projection refusal', async t => {
  let context;
  await assert.rejects(fixture(t, { issueBody: charter, route: 'manual', labelLaunch: true, streamlinedAdmission: true,
    beforeAdmission: value => {
      context = value;
      const put = value.store.put.bind(value.store);
      value.store.put = async (id, record) => {
        await put(id, record);
        if (id === 99 && !record.stepProjected) value.issue.labels = [{ name: 'codex-ready-manual' }, { name: 'step-7' }];
      };
    } }), { code: 'STEP_LABEL_POSITION_CHANGED' });
  const retained = await context.store.get(99);
  assert.equal(retained.envelope.step, 1);
  assert.equal(retained.readyConsumed, undefined);
  assert.deepEqual(retained.stepProjectionFrom, []);
  assert.equal(currentStep(context.issue.labels), 7);
});
