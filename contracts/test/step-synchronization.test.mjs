import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { prepareReviewStep, synchronizeReviewStep } from '../src/step-synchronization.mjs';
import { canonicalJson } from '../src/executable-cr.mjs';
import { REPOSITORY, OWNER, REVIEWER } from '../../controller/src/execution-contract.mjs';
import { currentStep } from '../../controller/src/step-metadata.mjs';
import { createGithubApi } from '../../controller/src/github-api.mjs';

const labels = n => [{ name: 'enhancement' }, { name: `step-${n}` }];
function fixture() {
  const input = JSON.parse(readFileSync(new URL('./fixtures/executable-cr-v2-input.json', import.meta.url)));
  const cr = { ...input.change_request, step: 6 };
  const body = () => '```reviewer-executable-cr\n' + canonicalJson({ schema_version: '2.0', repository: REPOSITORY,
    pull_request: 25, reviewed_head_sha: input.expected_head_sha, change_request: cr }) + '\n```';
  const issue = { number: 24, state: 'open', user: { login: OWNER }, body: 'Implement the canonical goal.', labels: labels(5) };
  const pr = { number: 25, state: 'open', merged: false, title: 'Task 24 · Step 5 · implementation', body: 'Related to #24', labels: labels(5),
    base: { ref: 'main', sha: input.expected_head_sha, repo: { full_name: REPOSITORY } },
    head: { ref: 'codex/task-24', sha: input.expected_head_sha, repo: { full_name: REPOSITORY } } };
  const review = { id: 90, state: 'CHANGES_REQUESTED', user: { login: REVIEWER }, commit_id: input.expected_head_sha, body: body() };
  const mutations = []; let failPr = false;
  const api = {
    viewer: async () => ({ login: OWNER, type: 'User' }),
    get: async path => structuredClone(path === '/issues/24' ? issue : path === '/pulls/25' ? pr : assert.fail(`Unexpected GET ${path}`)),
    list: async path => { assert.equal(path, '/pulls/25/reviews'); return [structuredClone(review)]; },
    ensureStepLabel: async step => { assert.equal(step, cr.step); },
    patch: async (path, value) => {
      if (path === '/issues/25' && failPr) throw Object.assign(new Error('transport'), { code: 'EIO' });
      mutations.push({ path, value });
      const subject = path === '/issues/24' ? issue : ['/issues/25', '/pulls/25'].includes(path) ? pr : assert.fail(`Unexpected mutation ${path}`);
      if (value.labels) subject.labels = value.labels.map(name => ({ name }));
      if (value.title) subject.title = value.title;
    }
  };
  return { api, issue, pr, review, cr, body, mutations, failPr: value => { failPr = value; } };
}

test('new executable CR takes N+1 from current labels and owner syncs both after publication', async () => {
  const f = fixture();
  const profile = await prepareReviewStep(f.api, 25);
  assert.equal(profile.currentStep, 5); assert.equal(profile.step, 6);
  assert.equal(f.mutations.length, 0);
  const result = await synchronizeReviewStep(f.api, 25, 90);
  assert.equal(result.step, 6);
  assert.equal(currentStep(f.issue.labels), 6); assert.equal(currentStep(f.pr.labels), 6);
  assert.match(f.pr.title, /^Task 24 · Step 6 ·/);
  assert.ok(f.issue.labels.some(l => l.name === 'enhancement'));
  assert.deepEqual(f.mutations.map(m => m.path), ['/issues/24', '/issues/25', '/pulls/25']);
  await synchronizeReviewStep(f.api, 25, 90);
  assert.equal(f.mutations.length, 3); // same CR transport repair never increments
});

test('partial native metadata failure is visible, blocks a new CR and repairs only the same published Step', async () => {
  const f = fixture(); f.failPr(true);
  await assert.rejects(synchronizeReviewStep(f.api, 25, 90), { code: 'EIO' });
  assert.equal(currentStep(f.issue.labels), 6); assert.equal(currentStep(f.pr.labels), 5);
  await assert.rejects(prepareReviewStep(f.api, 25), { code: 'STEP_LABEL_MISMATCH' });
  f.failPr(false);
  await synchronizeReviewStep(f.api, 25, 90);
  assert.equal(currentStep(f.issue.labels), 6); assert.equal(currentStep(f.pr.labels), 6);
  assert.equal(f.mutations.filter(m => m.path === '/issues/24').length, 1);
});

test('APPROVE changes no Step and creates no labels or remediation', async () => {
  const f = fixture(); f.review.state = 'APPROVED'; f.review.body = 'Approved for independent acceptance.';
  f.api.ensureStepLabel = async () => assert.fail('approval created a label');
  assert.deepEqual(await synchronizeReviewStep(f.api, 25, 90), { status: 'unchanged', step: 5 });
  assert.equal(f.mutations.length, 0); assert.equal(currentStep(f.pr.labels), 5);
});

test('metadata cannot be mutated by Reviewer/Writer Apps or non-owner actors', async () => {
  for (const actor of [{ login: REVIEWER, type: 'Bot' }, { login: 'example-writer[bot]', type: 'Bot' },
    { login: 'someone', type: 'User' }, { login: OWNER, type: 'Bot' }]) {
    const f = fixture(); f.api.viewer = async () => actor;
    await assert.rejects(prepareReviewStep(f.api, 25), { code: 'OWNER_METADATA_ACTOR_REQUIRED' });
    await assert.rejects(synchronizeReviewStep(f.api, 25, 90), { code: 'OWNER_METADATA_ACTOR_REQUIRED' });
    assert.equal(f.mutations.length, 0);
  }
});

test('unpublished, stale, superseded or invalid CRs and inconsistent metadata cause zero label writes', async () => {
  for (const mutate of [
    f => { f.review.id++; }, f => { f.review.user.login = OWNER; }, f => { f.review.state = 'DISMISSED'; },
    f => { f.pr.head.sha = 'b'.repeat(40); }, f => { f.review.body = 'No executable authority.'; },
    f => { f.pr.labels = []; }, f => { f.issue.labels = labels(2); },
    f => { f.pr.labels.push({ name: 'step-6' }); }, f => { f.issue.labels = [{ name: 'Step-5' }]; },
    f => { f.cr.step = 8; f.review.body = f.body(); }
  ]) {
    const f = fixture(); mutate(f);
    await assert.rejects(synchronizeReviewStep(f.api, 25, 90));
    assert.equal(f.mutations.length, 0);
  }
});

test('new CR authoring rejects missing, multiple or mismatched current labels and overflow', async () => {
  for (const mutate of [f => { f.issue.labels = []; }, f => { f.pr.labels.push({ name: 'step-6' }); },
    f => { f.pr.labels = labels(6); }, f => { f.issue.labels = f.pr.labels = labels(Number.MAX_SAFE_INTEGER); }]) {
    const f = fixture(); mutate(f);
    await assert.rejects(prepareReviewStep(f.api, 25)); assert.equal(f.mutations.length, 0);
  }
});

test('ordinary API adapter creates only a missing native Step label, not on read failure', async () => {
  for (const status of [200, 404, 403]) {
    const calls = [];
    const api = createGithubApi({ token: 'synthetic-owner-test', fetchImpl: async (url, options) => {
      calls.push({ url, options });
      return { ok: options.method === 'POST' || status === 200, status: options.method === 'POST' ? 201 : status, json: async () => ({}) };
    } });
    if (status === 403) await assert.rejects(api.ensureStepLabel(6), { code: 'GITHUB_REQUEST_FAILED' });
    else await api.ensureStepLabel(6);
    assert.equal(calls.length, status === 404 ? 2 : 1);
    if (status === 404) assert.equal(JSON.parse(calls[1].options.body).name, 'step-6');
  }
});
