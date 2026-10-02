import test from 'node:test';
import assert from 'node:assert/strict';
import { CONSUMER } from '../../consumer/consumer.mjs';
import { REPOSITORY } from '../src/execution-contract.mjs';
import { fixture } from './fixture.mjs';

function priorPull(f, { number = 50, state = 'closed', merged = false } = {}) {
  return { number, node_id: `PR_history_${number}`, state, merged, draft: false, labels: [], body: 'Closes #42',
    base: { ref: CONSUMER.baseBranch, sha: f.envelope.startHead, repo: { full_name: REPOSITORY } },
    head: { ref: f.envelope.branch, sha: f.envelope.startHead, repo: { full_name: REPOSITORY } } };
}

// Keep historical rows independently of the fixture's current PR. Model the
// native state filter so a regression to state=all exposes the older targets.
function publicationApi(f, history = []) {
  const get = f.api.get.bind(f.api); const list = f.api.list.bind(f.api); const post = f.api.post.bind(f.api);
  const draft = f.api.draft.bind(f.api); const ready = f.api.ready.bind(f.api); const patch = f.api.patch.bind(f.api);
  const surface = { history, mutations: [], lookups: [], current: value => value, createFailure: null };
  f.api.get = async path => {
    const old = history.find(pr => path === `/pulls/${pr.number}` || path === `/issues/${pr.number}`);
    if (old) return structuredClone(old);
    const value = await get(path);
    return path === '/pulls/43' ? surface.current(value) : value;
  };
  f.api.list = async path => {
    if (!path.startsWith('/pulls?')) return list(path);
    surface.lookups.push(path);
    const query = new URL(path, 'https://example.test').searchParams;
    const rows = [...structuredClone(history), ...await list(path)];
    return rows.filter(pr => query.get('state') === 'all' || pr.state === (query.get('state') ?? 'open'));
  };
  f.api.post = async (path, body) => {
    surface.mutations.push({ method: 'post', path, body: structuredClone(body) });
    if (path === '/pulls' && surface.createFailure) {
      const failure = surface.createFailure;
      if (failure.accepted) await post(path, body);
      throw Object.assign(new Error('GITHUB_REQUEST_FAILED'), { code: 'GITHUB_REQUEST_FAILED' });
    }
    return post(path, body);
  };
  f.api.patch = async (path, body) => {
    surface.mutations.push({ method: 'patch', path, body: structuredClone(body) });
    return patch(path, body);
  };
  f.api.draft = async node => {
    surface.mutations.push({ method: 'draft', node });
    assert.equal(node, 'PR_node'); return draft(node);
  };
  f.api.ready = async node => {
    surface.mutations.push({ method: 'ready', node });
    assert.equal(node, 'PR_node'); return ready(node);
  };
  surface.creations = () => surface.mutations.filter(call => call.method === 'post' && call.path === '/pulls');
  surface.assertHistoryUntouched = () => {
    for (const pr of history) {
      assert.ok(surface.mutations.every(call => call.node !== pr.node_id
        && !call.path?.startsWith(`/issues/${pr.number}/`) && call.path !== `/pulls/${pr.number}`));
    }
  };
  return surface;
}

async function candidate(f) {
  await f.prepare(f.envelope); await f.commit();
  const progress = await f.collect(f.envelope);
  return { progress, request: { operation: 'publish-progress', runId: f.envelope.runId,
    attemptId: f.envelope.attemptId, bundle: progress.bundle } };
}

const terminal = f => ({ operation: 'terminal-outcome', runId: f.envelope.runId,
  attemptId: f.envelope.attemptId, status: 'blocked', terminalCode: 'SEMANTIC_RESULT_BLOCKED' });

function supplyExistingCurrentPull(f) {
  const list = f.api.list.bind(f.api); let supplied = false;
  f.api.list = async path => {
    if (path.startsWith('/pulls?') && !supplied) {
      supplied = true;
      // Another actor may publish the compatible PR after the branch push but
      // before Writer's first lookup. Writer has made no PR creation intent.
      await f.api.post('/pulls', { title: 'Existing compatible task PR', head: f.envelope.branch,
        base: CONSUMER.baseBranch, draft: true, body: 'Closes #42' });
    }
    return list(path);
  };
}

for (const historical of ['none', 'closed', 'merged']) {
  test(`fresh Issue publication creates a current PR with ${historical} branch history`, async t => {
    const f = await fixture(t);
    const history = historical === 'none' ? [] : [priorPull(f, { merged: historical === 'merged' })];
    const original = structuredClone(history); const surface = publicationApi(f, history);
    const { progress, request } = await candidate(f);
    const result = await f.broker.invoke(request);
    assert.equal(result.prNumber, 43); assert.equal(result.publishedHead, progress.head);
    assert.equal(result.prObservedHead, progress.head); assert.equal(f.pushes(), 1);
    assert.equal(surface.creations().length, 1); assert.equal((await f.api.get('/pulls/43')).state, 'open');
    assert.deepEqual(history, original); surface.assertHistoryUntouched();
  });
}

test('a matching current open PR reconciles idempotently alongside closed and merged history', async t => {
  const f = await fixture(t); const surface = publicationApi(f, [priorPull(f), priorPull(f, { number: 51, merged: true })]);
  const { request } = await candidate(f);
  const first = await f.broker.invoke(request); const mutations = surface.mutations.length;
  assert.deepEqual(await f.broker.invoke(request), first);
  assert.equal(surface.creations().length, 1); assert.equal(surface.mutations.length, mutations);
  assert.equal(f.pushes(), 1); surface.assertHistoryUntouched();
});

for (const merged of [false, true]) {
  test(`a reconciled existing PR that later ${merged ? 'merges' : 'closes'} cannot authorize a replacement creation`, async t => {
    const f = await fixture(t); const surface = publicationApi(f, [priorPull(f)]);
    supplyExistingCurrentPull(f);
    const { progress, request } = await candidate(f);
    assert.equal((await f.broker.invoke(request)).prNumber, 43);
    assert.ok(!(await f.store.get(f.envelope.runId)).prIntent);
    const before = surface.mutations.length;
    surface.current = pr => ({ ...pr, state: 'closed', merged });
    await assert.rejects(f.broker.invoke(request), { code: 'PR_PUBLICATION_UNCERTAIN' });
    await assert.rejects(f.broker.invoke({ operation: 'finish', runId: f.envelope.runId,
      attemptId: f.envelope.attemptId, head: progress.head }), { code: 'PR_PUBLICATION_UNCERTAIN' });
    assert.equal(surface.creations().length, 1); assert.equal(surface.mutations.length, before);
    assert.equal(f.pushes(), 1); surface.assertHistoryUntouched();
  });
}

test('a different compatible open PR cannot replace the already observed current publication target', async t => {
  const f = await fixture(t); const surface = publicationApi(f, [priorPull(f)]);
  supplyExistingCurrentPull(f);
  const { progress, request } = await candidate(f);
  assert.equal((await f.broker.invoke(request)).prNumber, 43);
  assert.ok(!(await f.store.get(f.envelope.runId)).prIntent);
  const before = surface.mutations.length;
  surface.current = pr => ({ ...pr, number: 44, node_id: 'PR_replacement' });
  await assert.rejects(f.broker.invoke(request), { code: 'PR_AUTHORITY_CHANGED' });
  await assert.rejects(f.broker.invoke({ operation: 'finish', runId: f.envelope.runId,
    attemptId: f.envelope.attemptId, head: progress.head }), { code: 'PR_AUTHORITY_CHANGED' });
  await assert.rejects(f.broker.invoke(terminal(f)), { code: 'PR_AUTHORITY_CHANGED' });
  assert.equal(surface.creations().length, 1); assert.equal(surface.mutations.length, before);
  assert.equal(f.pushes(), 1); surface.assertHistoryUntouched();
});

test('multiple current PR candidates fail closed without choosing a compatible subset', async t => {
  const f = await fixture(t);
  const compatible = priorPull(f, { state: 'open' });
  const conflicting = { ...priorPull(f, { number: 51, state: 'open' }), body: 'Closes #99' };
  const surface = publicationApi(f, [compatible, conflicting, priorPull(f, { number: 52 })]);
  const { request } = await candidate(f);
  await assert.rejects(f.broker.invoke(request), { code: 'PR_AMBIGUOUS' });
  await assert.rejects(f.broker.invoke(terminal(f)), { code: 'PR_AMBIGUOUS' });
  assert.equal(surface.mutations.length, 0); assert.equal(f.comments.length, 0); surface.assertHistoryUntouched();
});

test('an accepted PR POST with a lost response reconciles once despite historical branch reuse', async t => {
  const f = await fixture(t); const surface = publicationApi(f, [priorPull(f)]);
  const { progress, request } = await candidate(f);
  surface.createFailure = { accepted: true };
  await assert.rejects(f.broker.invoke(request), { code: 'GITHUB_REQUEST_FAILED' });
  assert.equal((await f.store.get(f.envelope.runId)).prIntent, true);
  surface.createFailure = null;
  const recovered = await f.broker.invoke(request);
  assert.equal(recovered.prNumber, 43); assert.equal(recovered.prObservedHead, progress.head);
  assert.deepEqual(await f.broker.invoke(request), recovered);
  assert.equal(surface.creations().length, 1); assert.equal(f.pushes(), 1); surface.assertHistoryUntouched();
});

for (const marker of ['missing', 'another attempt', 'matching prefix']) {
  test(`uncertain PR creation rejects a replacement with ${marker} binding`, async t => {
    const f = await fixture(t); const surface = publicationApi(f, [priorPull(f)]);
    const { request } = await candidate(f);
    surface.createFailure = { accepted: true };
    await assert.rejects(f.broker.invoke(request), { code: 'GITHUB_REQUEST_FAILED' });
    surface.createFailure = null;
    const before = surface.mutations.length;
    const attempt = marker === 'missing' ? '' : `\nAttempt: ${marker === 'another attempt' ? 'run-100' : `${f.envelope.attemptId}-other`}`;
    surface.current = pr => ({ ...pr, number: 44, node_id: 'PR_replacement', body: `Closes #42${attempt}` });
    await assert.rejects(f.broker.invoke(request), { code: 'PR_PUBLICATION_UNCERTAIN' });
    await assert.rejects(f.broker.invoke(terminal(f)), { code: 'PR_PUBLICATION_UNCERTAIN' });
    assert.equal(surface.creations().length, 1); assert.equal(surface.mutations.length, before);
    assert.equal(f.pushes(), 1); surface.assertHistoryUntouched();
  });
}

for (const outcome of ['absent', 'closed', 'merged']) {
  test(`an uncertain PR POST whose current result is ${outcome} never creates a duplicate`, async t => {
    const f = await fixture(t); const surface = publicationApi(f, [priorPull(f)]);
    const { request } = await candidate(f);
    surface.createFailure = { accepted: outcome !== 'absent' };
    await assert.rejects(f.broker.invoke(request), { code: 'GITHUB_REQUEST_FAILED' });
    surface.createFailure = null;
    if (outcome !== 'absent') surface.current = pr => ({ ...pr, state: 'closed', merged: outcome === 'merged' });
    await assert.rejects(f.broker.invoke(request), { code: 'PR_PUBLICATION_UNCERTAIN' });
    await assert.rejects(f.broker.invoke(request), { code: 'PR_PUBLICATION_UNCERTAIN' });
    assert.equal(surface.creations().length, 1); assert.equal(f.pushes(), 1);
    assert.equal((await f.store.get(f.envelope.runId)).prIntent, true); surface.assertHistoryUntouched();
  });
}

for (const merged of [false, true]) {
  test(`blocked Issue execution uses the Issue when only ${merged ? 'merged' : 'closed'} history exists`, async t => {
    const f = await fixture(t); const history = [priorPull(f, { merged })]; const original = structuredClone(history);
    const surface = publicationApi(f, history);
    const result = await f.broker.invoke(terminal(f));
    assert.equal(result.prNumber, null);
    assert.deepEqual(surface.mutations.map(call => [call.method, call.path]), [['post', '/issues/42/comments']]);
    assert.equal(f.comments.length, 1); assert.deepEqual(history, original); surface.assertHistoryUntouched();
  });
}

test('blocked publication targets and drafts only the current PR among historical branch matches', async t => {
  const f = await fixture(t); const surface = publicationApi(f, [priorPull(f), priorPull(f, { number: 51, merged: true })]);
  const { request } = await candidate(f); await f.broker.invoke(request);
  await f.api.ready('PR_node'); surface.mutations.length = 0;
  const result = await f.broker.invoke(terminal(f));
  assert.equal(result.prNumber, 43); assert.equal((await f.api.get('/pulls/43')).draft, true);
  assert.deepEqual(surface.mutations.map(call => [call.method, call.path ?? call.node]),
    [['draft', 'PR_node'], ['post', '/issues/43/comments']]);
  surface.assertHistoryUntouched();
});

for (const [name, corrupt, code] of [
  ['head repository', pr => { pr.head.repo.full_name = 'other/repository'; }, 'PR_NOT_ADMITTED'],
  ['base repository', pr => { pr.base.repo.full_name = 'other/repository'; }, 'PR_NOT_ADMITTED'],
  ['base branch', pr => { pr.base.ref = 'other-base'; }, 'PR_NOT_ADMITTED'],
  ['head branch', pr => { pr.head.ref = `${CONSUMER.taskBranchPrefix}other-task`; }, 'PR_AUTHORITY_CHANGED'],
  ['Issue linkage', pr => { pr.body = 'Closes #99'; }, 'PR_AUTHORITY_CHANGED']
]) {
  test(`current PR resolution preserves the ${name} binding`, async t => {
    const f = await fixture(t); const surface = publicationApi(f, [priorPull(f)]);
    const { request } = await candidate(f); await f.broker.invoke(request);
    const before = surface.mutations.length;
    surface.current = pr => { const changed = structuredClone(pr); corrupt(changed); return changed; };
    await assert.rejects(f.broker.invoke(request), { code });
    await assert.rejects(f.broker.invoke(terminal(f)), { code });
    assert.equal(surface.mutations.length, before); assert.equal(surface.creations().length, 1);
    assert.equal(f.pushes(), 1); surface.assertHistoryUntouched();
  });
}

test('current open PR resolution preserves the exact published-head readiness gate', async t => {
  const f = await fixture(t); const surface = publicationApi(f, [priorPull(f)]);
  const { progress, request } = await candidate(f); await f.broker.invoke(request);
  const before = surface.mutations.length;
  surface.current = pr => ({ ...pr, head: { ...pr.head, sha: f.envelope.startHead } });
  await assert.rejects(f.broker.invoke({ operation: 'finish', runId: f.envelope.runId,
    attemptId: f.envelope.attemptId, head: progress.head }), { code: 'PR_HEAD_OBSERVATION_STALE' });
  assert.equal(surface.mutations.length, before); assert.equal((await f.api.get('/pulls/43')).draft, true);
  assert.equal(f.comments.length, 0); surface.assertHistoryUntouched();
});
