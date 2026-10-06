import test from 'node:test';
import assert from 'node:assert/strict';
import { fixture } from './fixture.mjs';
import { runAttempt } from '../src/attempt.mjs';
import { continueAfterChangeRequest } from '../src/pr-lifecycle.mjs';
import { REVIEWER, WRITER } from '../src/execution-contract.mjs';

const failure = code => Object.assign(new Error(code), { code });
const success = e => ({ version: e.version, attemptId: e.attemptId, child: 'started', containment: 'reaped',
  result: { status: 'success', summary: 'Exact candidate complete.', validation: ['local check'] } });
const handoff = f => ({ operation: 'complete-handoff', runId: f.envelope.runId, attemptId: f.envelope.attemptId });

test('Outcome readback and protected terminal journal precede Ready even with conflict and failed checks', async t => {
  const f = await fixture(t, { remediation: true }); const ready = f.api.ready;
  const get = f.api.get.bind(f.api); let outcomeReads = 0;
  f.api.get = async path => {
    const value = await get(path);
    if (path === '/issues/comments/1') outcomeReads++;
    return path === '/pulls/43' ? { ...value, mergeable: false, mergeable_state: 'dirty' } : value;
  };
  f.api.validations = () => assert.fail('checks must not gate execution handoff');
  f.api.ready = async id => {
    assert.equal(id, 'PR_node'); assert.ok(outcomeReads >= 2);
    const saved = await f.journal.get(99); const published = await f.store.get(99);
    assert.equal(saved.outcome.head, await f.remoteHead());
    assert.equal(saved.outcome.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
    assert.equal(published.lifecycleIntent.head, saved.outcome.head);
    assert.equal(f.comments[0].user.login, WRITER);
    await ready(id);
  };
  const result = await runAttempt({ ...f, execute: async () => {
    assert.equal((await get('/pulls/43')).draft, true);
    await f.commit(); return success(f.envelope);
  } });
  assert.equal(result.draft, false); assert.equal(result.readiness.status, 'BLOCKED');
  assert.equal(f.pushes(), 1); assert.equal(f.comments.length, 1);
});

test('Ready failure resumes from the successful Outcome without reexecution, push or repost', async t => {
  const f = await fixture(t); const ready = f.api.ready; let executions = 0;
  f.api.ready = async () => { throw failure('READY_MUTATION_FAILED'); };
  const args = { ...f, execute: async () => { executions++; await f.commit(); return success(f.envelope); } };
  await assert.rejects(runAttempt(args), { code: 'READY_MUTATION_FAILED' });
  assert.equal((await f.api.get('/pulls/43')).draft, true);
  assert.equal((await f.store.get(99)).outcome.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
  assert.ok((await f.store.get(99)).lifecycleIntent);
  f.api.ready = ready;
  const recovered = await runAttempt({ ...args, collect: () => assert.fail('recollection') });
  assert.equal(recovered.draft, false);
  assert.equal(executions, 1); assert.equal(f.pushes(), 1); assert.equal(f.comments.length, 1);
  assert.deepEqual(await f.broker.invoke(handoff(f)), recovered);
});

test('lost Ready response is reconciled by exact native readback without repeating the mutation', async t => {
  const f = await fixture(t); const ready = f.api.ready; let calls = 0;
  f.api.ready = async id => { calls++; await ready(id); throw failure('GITHUB_REQUEST_FAILED'); };
  const result = await runAttempt({ ...f, execute: async () => { await f.commit(); return success(f.envelope); } });
  assert.equal(result.draft, false); assert.equal(calls, 1);
  await f.broker.invoke(handoff(f)); assert.equal(calls, 1);
});

test('lost successful Outcome response recovers its exact body despite later integration changes', async t => {
  const f = await fixture(t); const post = f.api.post.bind(f.api); let lost = false; let calls = 0;
  f.api.post = async (path, body) => {
    const value = await post(path, body);
    if (path.endsWith('/comments')) {
      calls++;
      if (!lost) { lost = true; throw failure('GITHUB_REQUEST_FAILED'); }
    }
    return value;
  };
  const args = { ...f, execute: async () => { await f.commit(); return success(f.envelope); } };
  await assert.rejects(runAttempt(args), { code: 'GITHUB_REQUEST_FAILED' });
  assert.equal((await f.api.get('/pulls/43')).draft, true);
  const get = f.api.get.bind(f.api);
  f.api.get = async path => {
    const value = await get(path);
    return path === '/pulls/43' ? { ...value, mergeable: null, base: { ...value.base, sha: 'b'.repeat(40) } } : value;
  };
  const recovered = await runAttempt({ ...args, execute: () => assert.fail('reexecution') });
  assert.equal(recovered.draft, false); assert.equal(calls, 1); assert.equal(f.pushes(), 1);
  const refreshed = await f.broker.invoke({ operation: 'observe-readiness', runId: 99,
    attemptId: f.envelope.attemptId, head: recovered.head });
  assert.equal(refreshed.readiness.status, 'PENDING'); assert.equal(f.comments.length, 1);
});

for (const boundary of ['journal', 'outcome', 'head', 'authority', 'ready-readback']) {
  test(`unproven ${boundary} blocks Ready success and preserves publication`, async t => {
    const f = await fixture(t); const ready = f.api.ready; let mutations = 0;
    const nativeGet = f.api.get.bind(f.api);
    f.api.ready = async id => { mutations++; await ready(id); };
    const broker = { invoke: async request => {
      if (request.operation === 'complete-handoff') {
        if (boundary === 'journal') {
          const saved = await f.journal.get(99); saved.execution.containment = 'unknown'; await f.journal.put(99, saved);
        }
        if (boundary === 'outcome') f.comments[0].body += '\nEdited';
        if (boundary === 'authority') f.issue.body += '\nNew required work';
        if (boundary === 'head' || boundary === 'ready-readback') {
          const get = f.api.get.bind(f.api);
          f.api.get = async path => {
            if (boundary === 'ready-readback' && mutations && path === '/pulls/43') throw failure('READBACK_UNAVAILABLE');
            const value = await get(path);
            return boundary === 'head' && path === '/pulls/43' ? { ...value, head: { ...value.head, sha: 'a'.repeat(40) } } : value;
          };
        }
      }
      return f.broker.invoke(request);
    } };
    await assert.rejects(runAttempt({ ...f, broker, execute: async () => { await f.commit(); return success(f.envelope); } }));
    assert.equal(mutations, boundary === 'ready-readback' ? 1 : 0);
    assert.equal((await f.store.get(99)).handoffComplete, false);
    assert.equal(f.pushes(), 1); assert.equal(f.comments.length, 1);
    if (boundary === 'ready-readback') {
      f.api.get = nativeGet;
      assert.equal((await f.broker.invoke(handoff(f))).draft, false);
      assert.equal(mutations, 1);
    }
  });
}

async function reviewed(t) {
  return fixture(t, { remediation: true, deferAdmission: true, beforeAdmission: ({ review, api }) => {
    review.user = { login: REVIEWER, id: 701, type: 'Bot' };
    api.userIdentity = async login => { assert.equal(login, REVIEWER); return { ...review.user }; };
  } });
}
const publication = f => ({ structuredContent: { pr_lifecycle: {
  operation: 'begin-remediation', prNumber: 43, reviewId: f.review.id, head: f.review.commit_id } } });

test('successful CR continuation drafts its exact target before remediation and completion returns Ready', async t => {
  const f = await reviewed(t); const draft = f.api.draft; let mutations = 0;
  f.api.draft = async id => { mutations++; assert.equal(id, 'PR_node'); await draft(id); };
  const drafted = await continueAfterChangeRequest(publication(f), f.broker);
  assert.equal(drafted.head, f.review.commit_id); assert.equal(drafted.draft, true);
  await continueAfterChangeRequest(publication(f), f.broker); assert.equal(mutations, 1);
  // Re-admission of the already-Draft exact head is valid, without a new Step.
  const { createPublicationBroker } = await import('../src/publication-broker.mjs');
  const fresh = createPublicationBroker({ api: f.api, store: { get: async () => null, put: async () => {} }, publisher: f.publisher,
    lifecycleStore: f.lifecycleStore });
  assert.equal((await fresh.dispatch(f.admissionRequest)).envelope.startHead, drafted.head);
  await f.broker.invoke(f.admissionRequest);
  const completed = await runAttempt({ ...f, execute: async () => { await f.commit(); return success(f.envelope); } });
  assert.equal(completed.draft, false); assert.equal(mutations, 1);
});

test('CR Draft failure stops continuation and exact native replay repairs it', async t => {
  const f = await reviewed(t); const draft = f.api.draft;
  f.api.draft = async () => { throw failure('DRAFT_MUTATION_FAILED'); };
  await assert.rejects(continueAfterChangeRequest(publication(f), f.broker), { code: 'DRAFT_MUTATION_FAILED' });
  assert.ok((await f.lifecycleStore.get(f.review.id)).lifecycleIntent);
  f.api.draft = draft;
  assert.equal((await continueAfterChangeRequest(publication(f), f.broker)).draft, true);
  assert.equal(f.pushes(), 0); assert.equal(f.comments.length, 0);
});

test('lost CR Draft response reconciles the same exact native target', async t => {
  const f = await reviewed(t); const draft = f.api.draft; let calls = 0;
  f.api.draft = async id => { calls++; await draft(id); throw failure('GITHUB_REQUEST_FAILED'); };
  assert.equal((await continueAfterChangeRequest(publication(f), f.broker)).draft, true);
  await continueAfterChangeRequest(publication(f), f.broker);
  assert.equal(calls, 1); assert.equal(f.pushes(), 0);
});

for (const changed of ['review', 'head', 'identity', 'failed-publication']) {
  test(`CR lifecycle rejects ${changed} without mutation`, async t => {
    const f = await reviewed(t); const result = publication(f);
    f.api.draft = () => assert.fail('unauthorized mutation');
    if (changed === 'review') result.structuredContent.pr_lifecycle.reviewId++;
    if (changed === 'head') result.structuredContent.pr_lifecycle.head = 'a'.repeat(40);
    if (changed === 'identity') f.api.userIdentity = async () => ({ login: REVIEWER, type: 'Bot', id: 702 });
    if (changed === 'failed-publication') result.isError = true;
    await assert.rejects(continueAfterChangeRequest(result, f.broker));
    assert.equal(f.pushes(), 0); assert.equal(f.comments.length, 0);
  });
}
