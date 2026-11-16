import test from 'node:test';
import assert from 'node:assert/strict';
import { fixture } from './fixture.mjs';
import { runAttempt } from '../src/attempt.mjs';
import { nonClosingTaskBody, taskReferences } from '../src/task-relationship.mjs';
import { REPOSITORY } from '../src/execution-contract.mjs';

const request = (f, operation) => ({ operation, runId: f.envelope.runId, attemptId: f.envelope.attemptId });

test('neutral projection preserves Task identity, other repositories and unrelated prose', () => {
  const body = `Implementation details.\nCloses #42\nFIXES: ${REPOSITORY}#42\nResolves https://github.com/${REPOSITORY}/issues/42\nRelated to #42\nCloses other/repo#42\nCloses #99`;
  const neutral = nonClosingTaskBody(body, REPOSITORY, 42);
  assert.equal(neutral, 'Implementation details.\nRelated to #42\nRelated to #42\nRelated to #42\nRelated to #42\nCloses other/repo#42\nCloses #99');
  assert.deepEqual(taskReferences(neutral, REPOSITORY), [42, 99]);
  assert.equal(nonClosingTaskBody(neutral, REPOSITORY, 42), neutral);
});

for (const policy of ['keep-open', 'close-authorized']) {
  test(`Writer execution handoff remains neutral under ${policy} until trusted final designation`, async t => {
    const f = await fixture(t, { issueBody: `Authority model: github-native-v1\nIssue closure policy: ${policy}\nImplement the finite repository work.` });
    const result = await runAttempt({ ...f, journal: f.journal, execute: async () => {
      await f.commit();
      return { version: 2, attemptId: f.envelope.attemptId, child: 'started', containment: 'reaped',
        result: { status: 'success', summary: 'The admitted source change is complete.', validation: ['local check passed'] } };
    } });
    assert.equal(result.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
    const pr = await f.api.get('/pulls/43');
    assert.match(pr.body, /Related to #42/);
    assert.doesNotMatch(pr.body, /\b(?:closes|fixes|resolves)\s+#42\b/i);
    assert.equal(f.issue.state, 'open');
    assert.equal(f.envelope.request.issue_closure_policy, policy);
  });
}

for (const route of ['auto', 'manual']) {
  for (const remediation of [false, true]) {
    test(`new ${route} ${remediation ? 'remediation' : 'Issue continuation'} clears a prior final closing designation before work`, async t => {
      const f = await fixture(t, { route, remediation, ...(!remediation ? { continuation: true } : {}) });
      f.pr.body = `Implementation retained.\nCloses #42\nNative source provenance stays unchanged.`;
      const before = await f.store.get(f.envelope.runId);
      const first = await f.broker.invoke(request(f, route === 'auto' ? 'preflight' : 'handoff'));
      const pr = await f.api.get('/pulls/43');
      assert.equal(pr.body, 'Implementation retained.\nRelated to #42\nNative source provenance stays unchanged.');
      assert.equal(pr.draft, true);
      assert.equal(f.issue.state, 'open');
      assert.deepEqual((await f.store.get(f.envelope.runId)).envelope, before.envelope);
      assert.equal((await f.store.get(f.envelope.runId)).relationshipIntent, null);
      assert.deepEqual(await f.broker.invoke(request(f, route === 'auto' ? 'preflight' : 'handoff')), first);
    });
  }
}

test('relationship reservation detects a concurrent owner edit before PATCH and preserves it', async t => {
  const f = await fixture(t, { continuation: true });
  f.pr.body = 'Closes #42\nOriginal text.';
  const put = f.store.put.bind(f.store);
  let patches = 0;
  const patch = f.api.patch.bind(f.api);
  f.api.patch = async (path, value) => { if (value.body !== undefined) patches++; return patch(path, value); };
  f.store.put = async (id, record) => {
    await put(id, record);
    if (record.relationshipIntent) f.pr.body = 'Closes #42\nConcurrent owner amendment.';
  };
  await assert.rejects(f.broker.invoke(request(f, 'preflight')), { code: 'PR_AUTHORITY_CHANGED' });
  assert.equal(patches, 0);
  assert.equal(f.pr.body, 'Closes #42\nConcurrent owner amendment.');
  assert.ok((await f.store.get(f.envelope.runId)).relationshipIntent);
});

test('an accepted neutralizing PATCH with a lost response reconciles by native readback without another PATCH', async t => {
  const f = await fixture(t, { continuation: true });
  f.pr.body = 'Closes #42\nPreserve this text.';
  const patch = f.api.patch.bind(f.api);
  let patches = 0;
  f.api.patch = async (path, value) => {
    const result = await patch(path, value);
    if (value.body !== undefined) {
      patches++;
      throw Object.assign(new Error('Native response lost'), { code: 'PATCH_UNCERTAIN' });
    }
    return result;
  };
  await assert.rejects(f.broker.invoke(request(f, 'preflight')), { code: 'PATCH_UNCERTAIN' });
  assert.ok((await f.store.get(f.envelope.runId)).relationshipIntent);
  await f.broker.invoke(request(f, 'preflight'));
  assert.equal(patches, 1);
  assert.equal(f.pr.body, 'Related to #42\nPreserve this text.');
  assert.equal((await f.store.get(f.envelope.runId)).relationshipIntent, null);
});

for (const phase of ['reservation', 'readback']) {
  test(`neutral projection rejects a branch replacement at ${phase} and retains its unresolved intent`, async t => {
    const f = await fixture(t, { continuation: true });
    f.pr.body = 'Closes #42';
    let patches = 0;
    const patch = f.api.patch.bind(f.api);
    const put = f.store.put.bind(f.store);
    const replaceBranch = () => { f.pr.head.ref += '-replacement'; };
    f.store.put = async (id, record) => {
      await put(id, record);
      if (phase === 'reservation' && record.relationshipIntent) replaceBranch();
    };
    f.api.patch = async (path, value) => {
      const result = await patch(path, value);
      if (value.body !== undefined) {
        patches++;
        if (phase === 'readback') replaceBranch();
      }
      return result;
    };
    await assert.rejects(f.broker.invoke(request(f, 'preflight')), { code: 'PR_AUTHORITY_CHANGED' });
    assert.equal(patches, phase === 'reservation' ? 0 : 1);
    assert.equal(f.issue.state, 'open');
    assert.ok((await f.store.get(f.envelope.runId)).relationshipIntent);
  });
}

test('completed execution replay preserves the owner final linkage and original Outcome body hash', async t => {
  const f = await fixture(t, { continuation: true });
  await f.prepare(f.envelope);
  const head = await f.commit();
  const progress = await f.collect(f.envelope);
  await f.broker.invoke({ ...request(f, 'publish-progress'), bundle: progress.bundle });
  const result = await f.broker.invoke({ ...request(f, 'finish'), head,
    taskResult: { status: 'success', summary: 'Implementation complete.', validation: ['local check passed'] } });
  // This edit models the existing trusted owner connector after independent
  // acceptance and completion verification. Writer never selects it.
  f.pr.body = nonClosingTaskBody(f.pr.body, REPOSITORY, 42).replace('Related to #42', 'Closes #42');
  const before = (await f.store.get(f.envelope.runId)).outcome.bodySha256;
  await f.broker.invoke(request(f, 'preflight'));
  assert.deepEqual(await f.broker.invoke({ ...request(f, 'finish'), head }), result);
  assert.match(f.pr.body, /Closes #42/);
  assert.equal((await f.store.get(f.envelope.runId)).outcome.bodySha256, before);
  assert.equal(f.pushes(), 1);
});
