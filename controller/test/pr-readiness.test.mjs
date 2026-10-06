import test from 'node:test';
import assert from 'node:assert/strict';
import { fixture, memoryStore } from './fixture.mjs';
import { runAttempt } from '../src/attempt.mjs';
import { prReadiness } from '../src/pr-readiness.mjs';
import { VERSION } from '../src/execution-contract.mjs';

const head = 'a'.repeat(40); const base = 'b'.repeat(40);
for (const [mergeable, status] of [[null, 'PENDING'], [undefined, 'PENDING'], [false, 'BLOCKED'], [true, 'READY']]) {
  test(`mergeable=${mergeable} is ${status} for the candidate head`, () => {
    const result = prReadiness({ mergeable, head: { sha: head }, base: { sha: base } }, head);
    assert.equal(result.status, status); assert.equal(result.head, head); assert.equal(result.observedBase, base);
  });
}

async function completed(t, mergeable, options = {}) {
  const f = await fixture(t, options); const get = f.api.get.bind(f.api); let observed = mergeable; let observedBase;
  f.api.get = async path => {
    const pr = await get(path);
    return path === '/pulls/43' ? { ...pr, mergeable: observed,
      base: { ...pr.base, sha: observedBase ?? pr.base.sha } } : pr;
  };
  const journal = memoryStore(); let executions = 0;
  const args = { ...f, journal, execute: async () => {
    executions++; await f.commit(); return { version: VERSION, attemptId: f.envelope.attemptId, child: 'started', containment: 'reaped',
      result: { status: 'success', summary: 'Candidate complete.', validation: ['local candidate validation'] } };
  } };
  const outcome = await runAttempt(args);
  return { ...f, args, outcome, executions: () => executions,
    observe: (value, newBase) => { observed = value; observedBase = newBase; } };
}

for (const continuation of [false, true]) {
  test(`completed ${continuation ? 'Issue continuation' : 'fresh Issue'} uses detailed mergeability rather than the PR list summary`, async t => {
    const f = await completed(t, true, { continuation });
    const summaries = await f.api.list('/pulls?state=open');
    assert.equal(summaries[0].mergeable, undefined);
    assert.equal((await f.api.get('/pulls/43')).mergeable, true);
    assert.equal(f.outcome.readiness.status, 'READY');
    assert.equal(f.outcome.draft, false);
    assert.equal((await f.api.get('/pulls/43')).draft, false);
    assert.equal(f.outcome.head, await f.remoteHead());
    assert.equal(f.outcome.prNumber, 43);
    assert.equal(f.comments.length, 1);
    assert.equal(f.executions(), 1);
    assert.equal(f.pushes(), 1);
  });
}

test('observing an already ready candidate does not draft it because the list omits mergeability', async t => {
  const f = await completed(t, null, { continuation: true });
  f.observe(true);
  await f.api.ready('PR_node');
  let transitions = 0;
  for (const name of ['ready', 'draft']) {
    const mutate = f.api[name].bind(f.api);
    f.api[name] = async node => { transitions++; return mutate(node); };
  }
  const result = await f.broker.invoke({ operation: 'observe-readiness', runId: f.envelope.runId,
    attemptId: f.envelope.attemptId, head: f.outcome.head });
  assert.equal(result.readiness.status, 'READY');
  assert.equal(result.draft, false);
  assert.equal(transitions, 0);
  assert.equal(result.outcomeId, f.outcome.outcomeId);
  assert.equal(f.comments.length, 1);
  assert.equal(f.executions(), 1);
  assert.equal(f.pushes(), 1);
});

for (const mergeable of [null, false]) {
  test(`${mergeable === null ? 'unresolved mergeability' : 'proven conflict'} preserves published progress and successful orchestration`, async t => {
    const f = await completed(t, mergeable);
    assert.equal(f.outcome.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
    assert.equal(f.outcome.readiness.status, mergeable === null ? 'PENDING' : 'BLOCKED');
    assert.equal(f.outcome.draft, true); assert.equal(f.pushes(), 1);
    assert.equal(f.outcome.head, await f.remoteHead());
    assert.match(f.comments[0].body, /Latest durable candidate head:/);
    assert.doesNotMatch(f.comments[0].body, /Latest durable and ready head:/);
    assert.match(f.comments[0].body, /Review readiness: (PENDING|BLOCKED)/);
    await runAttempt(f.args);
    assert.equal(f.executions(), 1); assert.equal(f.pushes(), 1); assert.equal(f.comments.length, 1);
  });
}

test('one bounded observation resolves transient mergeability on the same Outcome without worker or push', async t => {
  const f = await completed(t, null); const request = { operation: 'observe-readiness', runId: f.envelope.runId,
    attemptId: f.envelope.attemptId, head: f.outcome.head };
  f.observe(true);
  const result = await f.broker.invoke(request);
  assert.equal(result.readiness.status, 'READY'); assert.equal(result.draft, false);
  assert.equal(result.outcomeId, f.outcome.outcomeId); assert.equal(f.comments.length, 1);
  assert.match(f.comments[0].body, /Review readiness: READY/);
  assert.match(f.comments[0].body, /Candidate complete\./);
  assert.deepEqual(await f.broker.invoke(request), result);
  assert.equal(f.executions(), 1); assert.equal(f.pushes(), 1);
});

test('later base movement refreshes a readiness snapshot while keeping the exact review candidate', async t => {
  const f = await completed(t, true, { continuation: true }); f.observe(false, base);
  const result = await f.broker.invoke({ operation: 'observe-readiness', runId: f.envelope.runId,
    attemptId: f.envelope.attemptId, head: f.outcome.head });
  assert.equal(result.readiness.status, 'BLOCKED'); assert.equal(result.readiness.observedBase, base);
  assert.equal(result.head, f.outcome.head); assert.equal(await f.remoteHead(), f.outcome.head);
  assert.equal(result.draft, true); assert.equal(f.pushes(), 1); assert.equal(f.executions(), 1);
  assert.equal(f.comments.length, 1);
});

test('observation cannot replace the exact published candidate or reconcile changed authority', async t => {
  const f = await completed(t, null); const request = { operation: 'observe-readiness', runId: f.envelope.runId,
    attemptId: f.envelope.attemptId, head: base };
  await assert.rejects(f.broker.invoke(request), { code: 'COMPLETED_PUBLICATION_REQUIRED' });
  f.issue.body += '\nChanged scope'; request.head = f.outcome.head;
  await assert.rejects(f.broker.invoke(request), { code: 'AUTHORITY_CHANGED' });
  assert.equal(f.pushes(), 1); assert.equal(f.comments.length, 1);
});

test('an accepted readiness Outcome PATCH with a lost response reconciles its existing comment', async t => {
  const f = await completed(t, null); f.observe(true);
  const patch = f.api.patch.bind(f.api); let calls = 0;
  f.api.patch = async (path, body) => {
    calls++; const result = await patch(path, body);
    if (calls === 1) throw Object.assign(new Error('lost response'), { code: 'GITHUB_REQUEST_FAILED' });
    return result;
  };
  const request = { operation: 'observe-readiness', runId: f.envelope.runId,
    attemptId: f.envelope.attemptId, head: f.outcome.head };
  await assert.rejects(f.broker.invoke(request), { code: 'GITHUB_REQUEST_FAILED' });
  assert.ok((await f.store.get(f.envelope.runId)).readinessIntent);
  const recovered = await f.broker.invoke(request);
  assert.equal(recovered.readiness.status, 'READY'); assert.equal(calls, 1);
  assert.equal(f.comments.length, 1); assert.equal(f.pushes(), 1);
  assert.equal((await f.store.get(f.envelope.runId)).readinessIntent, null);
});

test('a changed native candidate cannot be adopted by a readiness observation', async t => {
  const f = await completed(t, null); const get = f.api.get.bind(f.api);
  f.api.get = async path => {
    const pr = await get(path);
    return path === '/pulls/43' ? { ...pr, head: { ...pr.head, sha: base } } : pr;
  };
  await assert.rejects(f.broker.invoke({ operation: 'observe-readiness', runId: f.envelope.runId,
    attemptId: f.envelope.attemptId, head: f.outcome.head }), { code: 'PR_HEAD_OBSERVATION_STALE' });
  assert.equal(f.pushes(), 1); assert.equal(f.comments.length, 1);
});

test('mergeability becoming unresolved during native ready mutation returns pending and restores draft', async t => {
  const f = await completed(t, null); f.observe(true);
  const ready = f.api.ready.bind(f.api);
  f.api.ready = async node => { await ready(node); f.observe(null); };
  const result = await f.broker.invoke({ operation: 'observe-readiness', runId: f.envelope.runId,
    attemptId: f.envelope.attemptId, head: f.outcome.head });
  assert.equal(result.readiness.status, 'PENDING'); assert.equal(result.readiness.code, 'MERGEABILITY_UNRESOLVED');
  assert.equal(result.draft, true); assert.equal(f.pushes(), 1); assert.equal(f.comments.length, 1);
});
