import test from 'node:test';
import assert from 'node:assert/strict';
import { CONSUMER } from '../../consumer/consumer.mjs';
import { findCurrentIssuePullRequest } from '../src/publication-target.mjs';

const branch = `${CONSUMER.taskBranchPrefix}test-42`;
const envelope = { branch, issueNumber: 42, continuation: { pullRequest: 43 } };
function nativePullRequest() {
  return { number: 43, state: 'open', merged: false, draft: true, body: 'Related to #42',
    title: 'Task 42 · Step 1 · implementation', labels: [{ name: 'step-1' }],
    base: { ref: CONSUMER.baseBranch, sha: 'b'.repeat(40), repo: { full_name: CONSUMER.repository } },
    head: { ref: branch, sha: 'a'.repeat(40), repo: { full_name: CONSUMER.repository } } };
}
function nativeApi(mutate = () => {}) {
  const summary = nativePullRequest();
  const detail = { ...structuredClone(summary), mergeable: true };
  mutate(detail);
  return {
    list: async () => [structuredClone(summary)],
    get: async path => { if (path.startsWith('/compare/')) return { status: 'diverged' }; assert.equal(path, '/pulls/43'); return structuredClone(detail); }
  };
}

test('unique Issue PR discovery returns fresh detail including native mergeability', async () => {
  const pr = await findCurrentIssuePullRequest(nativeApi(), envelope, 43);
  assert.equal(pr.number, 43);
  assert.equal(pr.mergeable, true);
});

test('only a verified Writer transition permits known predecessor/candidate propagation', async () => {
  const transition = { previous: 'a'.repeat(40), head: 'c'.repeat(40) };
  const api = nativeApi(pr => { pr.head.sha = transition.head; });
  await assert.rejects(findCurrentIssuePullRequest(api, envelope, 43), { code: 'PR_AUTHORITY_CHANGED' });
  assert.equal((await findCurrentIssuePullRequest(api, envelope, 43, transition)).head.sha, transition.head);
  await assert.rejects(findCurrentIssuePullRequest(api, envelope, null, transition), { code: 'PR_AUTHORITY_CHANGED' });
  await assert.rejects(findCurrentIssuePullRequest(api, envelope, 43,
    { previous: 'b'.repeat(40), head: transition.head }), { code: 'PR_AUTHORITY_CHANGED' });
});

for (const [name, mutate, code] of [
  ['foreign head', pr => { pr.head.sha = 'd'.repeat(40); }, 'PR_AUTHORITY_CHANGED'],
    ['foreign linkage', pr => { pr.head.sha = 'c'.repeat(40); pr.body = 'Related to #99'; }, 'PR_AUTHORITY_CHANGED'],
  ['base rewrite', pr => { pr.base.sha = 'd'.repeat(40); }, 'STARTING_STATE_MISMATCH']
]) test(`Writer transition still rejects ${name}`, async () => {
  await assert.rejects(findCurrentIssuePullRequest(nativeApi(mutate), envelope, 43,
    { previous: 'a'.repeat(40), head: 'c'.repeat(40) }), { code });
});

for (const [name, mutate, code] of [
  ['head', pr => { pr.head.sha = 'c'.repeat(40); }, 'PR_AUTHORITY_CHANGED'],
  ['branch', pr => { pr.head.ref = `${CONSUMER.taskBranchPrefix}other`; }, 'PR_AUTHORITY_CHANGED'],
  ['base head', pr => { pr.base.sha = 'c'.repeat(40); }, 'STARTING_STATE_MISMATCH'],
  ['base branch', pr => { pr.base.ref = 'other-base'; }, 'PR_NOT_ADMITTED'],
  ['head repository', pr => { pr.head.repo.full_name = 'other/repository'; }, 'PR_NOT_ADMITTED'],
  ['base repository', pr => { pr.base.repo.full_name = 'other/repository'; }, 'PR_NOT_ADMITTED'],
  ['Issue linkage', pr => { pr.body = 'Related to #44'; }, 'PR_AUTHORITY_CHANGED'],
  ['PR number', pr => { pr.number = 44; }, 'PR_NOT_ADMITTED'],
  ['open state', pr => { pr.state = 'closed'; }, 'PR_NOT_ADMITTED'],
  ['merge state', pr => { pr.merged = true; }, 'PR_NOT_ADMITTED']
]) {
  test(`Issue PR discovery rejects changed ${name} between list and detail`, async () => {
    await assert.rejects(findCurrentIssuePullRequest(nativeApi(mutate), envelope, 43), { code });
  });
}


test('list/detail descendant main movement preserves PR identity and independent mergeability', async () => {
  const api = nativeApi(pr => { pr.base.sha = 'c'.repeat(40); pr.mergeable = false; });
  const get = api.get;
  api.get = async path => path.startsWith('/compare/') ? {
    status: 'ahead', base_commit: { sha: 'b'.repeat(40) }, merge_base_commit: { sha: 'b'.repeat(40) }
  } : get(path);
  const pr = await findCurrentIssuePullRequest(api, envelope, 43);
  assert.equal(pr.base.sha, 'c'.repeat(40));
  assert.equal(pr.mergeable, false);
});

test('derived title and Step label drift between list/detail reads is not a Task identity change', async () => {
  const pr = await findCurrentIssuePullRequest(nativeApi(pr => {
    pr.title = 'Owner-edited presentation'; pr.labels = [{ name: 'step-2' }];
  }), envelope, 43);
  assert.equal(pr.title, 'Owner-edited presentation');
  assert.deepEqual(pr.labels, [{ name: 'step-2' }]);
});
