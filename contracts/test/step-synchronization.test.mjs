import test from 'node:test';
import assert from 'node:assert/strict';
import { prepareReviewStep, prepareOwnerPhase, recoverLegacyReviewStep, executeMetadataRequest } from '../src/step-synchronization.mjs';
import { REPOSITORY, OWNER, REVIEWER } from '../../controller/src/execution-contract.mjs';
import { currentStep, reviewStepTitle } from '../../controller/src/step-metadata.mjs';
import { RUN_NAME_IDENTITY_MAX_CHARS } from '../../controller/src/run-name.mjs';
import { createGithubApi } from '../../controller/src/github-api.mjs';
import { readFileSync } from 'node:fs';
import { canonicalJson } from '../src/executable-cr.mjs';

const labels = n => [{ name: 'enhancement' }, { name: `step-${n}` }];
const request = (overrides = {}) => ({ operation: 'advance-phase', issueNumber: 24, currentStep: 5,
  newPhaseAuthorized: true, pullRequest: 25, purpose: 'new implementation phase', ...overrides });
function fixture() {
  const head = 'a'.repeat(40);
  const issue = { number: 24, state: 'open', user: { login: OWNER }, body: 'Implement the canonical goal.', labels: labels(5) };
  const pr = { number: 25, state: 'open', merged: false, title: 'Task 24 · Step 5 · implementation', body: 'Related to #24', labels: labels(5),
    base: { ref: 'main', sha: head, repo: { full_name: REPOSITORY } },
    head: { ref: 'codex/task-24', sha: head, repo: { full_name: REPOSITORY } } };
  const mutations = []; let failPr = false; let reads = 0;
  const api = {
    viewer: async () => ({ login: OWNER, type: 'User' }),
    get: async path => { reads++; return structuredClone(path === '/issues/24' ? issue : path === '/pulls/25' ? pr : assert.fail(`Unexpected GET ${path}`)); },
    list: async () => assert.fail('phase preparation must not infer review history'),
    ensureStepLabel: async step => { assert.equal(step, 6); },
    patch: async (path, value) => {
      if (path === '/issues/25' && failPr) throw Object.assign(new Error('transport'), { code: 'EIO' });
      mutations.push({ path, value });
      const subject = path === '/issues/24' ? issue : ['/issues/25', '/pulls/25'].includes(path) ? pr : assert.fail(`Unexpected mutation ${path}`);
      if (value.labels) subject.labels = value.labels.map(name => ({ name }));
      if (value.title) subject.title = value.title;
    }
  };
  return { api, issue, pr, mutations, reads: () => reads, failPr: value => { failPr = value; } };
}

const recoveryRequest = (overrides = {}) => ({ operation: 'recover-legacy-review', pullRequest: 25,
  reviewId: 90, legacyPublicationRecoveryAuthorized: true, ...overrides });
function legacyFixture() {
  const f = fixture();
  const input = JSON.parse(readFileSync(new URL('./fixtures/executable-cr-v2-input.json', import.meta.url)));
  const cr = { ...input.change_request, step: 6 };
  f.pr.head.sha = f.pr.base.sha = input.expected_head_sha;
  const body = () => '```reviewer-executable-cr\n' + canonicalJson({ schema_version: '2.0', repository: REPOSITORY,
    pull_request: 25, reviewed_head_sha: input.expected_head_sha, change_request: cr }) + '\n```';
  const review = { id: 90, state: 'CHANGES_REQUESTED', user: { login: REVIEWER }, commit_id: input.expected_head_sha, body: body() };
  f.api.list = async path => { assert.equal(path, '/pulls/25/reviews'); return [structuredClone(review)]; };
  return { ...f, cr, review, body };
}

test('new CR authoring reads synchronized native labels without changing metadata', async () => {
  const f = fixture();
  const profile = await prepareReviewStep(f.api, 25);
  assert.deepEqual(profile, { issueNumber: 24, pullRequest: 25, reviewedHead: f.pr.head.sha, currentStep: 5, step: 6 });
  assert.equal(f.mutations.length, 0);
});

test('owner-authorized new phase advances only N to N+1, preserves unrelated labels and verifies bounded title', async () => {
  const f = fixture();
  const r = request({ purpose: 'A lengthy descriptive phase '.repeat(12).trim() });
  const result = await executeMetadataRequest(f.api, r);
  assert.equal(result.step, 6);
  assert.equal(currentStep(f.issue.labels), 6); assert.equal(currentStep(f.pr.labels), 6);
  assert.match(f.pr.title, /^Task 24 · Step 6 ·/);
  assert.ok(Array.from(f.pr.title).length <= RUN_NAME_IDENTITY_MAX_CHARS);
  assert.ok(f.issue.labels.some(l => l.name === 'enhancement'));
  assert.ok(f.pr.labels.some(l => l.name === 'enhancement'));
  assert.deepEqual(f.mutations.map(m => m.path), ['/issues/24', '/issues/25', '/pulls/25']);
  assert.ok(f.reads() >= 10);
  await executeMetadataRequest(f.api, r);
  assert.equal(f.mutations.length, 3); // same bounded operation cannot become N+2
});

test('new phase with no PR is valid and cannot create a PR or edit Issue authority', async () => {
  const f = fixture();
  await prepareOwnerPhase(f.api, { operation: 'advance-phase', issueNumber: 24, currentStep: 5, newPhaseAuthorized: true });
  assert.equal(currentStep(f.issue.labels), 6);
  assert.deepEqual(f.mutations, [{ path: '/issues/24', value: { labels: ['enhancement', 'step-6'] } }]);
});

test('partial phase metadata failure is visible and same N-bound operation finishes only N+1', async () => {
  const f = fixture(); f.failPr(true);
  await assert.rejects(prepareOwnerPhase(f.api, request()), { code: 'EIO' });
  assert.equal(currentStep(f.issue.labels), 6); assert.equal(currentStep(f.pr.labels), 5);
  await assert.rejects(prepareReviewStep(f.api, 25), { code: 'STEP_LABEL_MISMATCH' });
  f.failPr(false);
  await prepareOwnerPhase(f.api, request());
  assert.equal(currentStep(f.issue.labels), 6); assert.equal(currentStep(f.pr.labels), 6);
  assert.equal(f.mutations.filter(m => m.path === '/issues/24').length, 1);
});

test('same-phase retry explicitly keeps Step and bypasses label creation and all writes', async () => {
  const f = fixture();
  f.api.ensureStepLabel = async () => assert.fail('retry created a label');
  assert.deepEqual(await executeMetadataRequest(f.api, { operation: 'keep-step', issueNumber: 24, currentStep: 5, pullRequest: 25 }),
    { status: 'unchanged', issueNumber: 24, pullRequest: 25, step: 5 });
  assert.equal(f.mutations.length, 0);
});

test('Reviewer/Writer Apps, non-owner users and a bot impersonating owner cannot prepare phase metadata', async () => {
  for (const actor of [{ login: REVIEWER, type: 'Bot' }, { login: 'example-writer[bot]', type: 'Bot' },
    { login: 'someone', type: 'User' }, { login: OWNER, type: 'Bot' }]) {
    const f = fixture(); f.api.viewer = async () => actor;
    await assert.rejects(prepareReviewStep(f.api, 25), { code: 'OWNER_METADATA_ACTOR_REQUIRED' });
    await assert.rejects(prepareOwnerPhase(f.api, request()), { code: 'OWNER_METADATA_ACTOR_REQUIRED' });
    await assert.rejects(recoverLegacyReviewStep(f.api, recoveryRequest()), { code: 'OWNER_METADATA_ACTOR_REQUIRED' });
    assert.equal(f.mutations.length, 0);
  }
});

test('payload is bounded to explicit phase intent and cannot become a normal owner post-CR writer', async () => {
  for (const r of [request({ newPhaseAuthorized: false }), request({ newPhaseAuthorized: undefined }),
    request({ title: 'arbitrary title' }), request({ labels: ['other'] }), request({ reviewId: 90 }), request({ purpose: 'line\nbreak' }),
    request({ purpose: '' }), request({ purpose: 'x'.repeat(513) }), request({ currentStep: 0 }), request({ currentStep: Number.MAX_SAFE_INTEGER }),
    request({ pullRequest: null }), { operation: 'synchronize', pullRequest: 25, reviewId: 90 },
    { operation: 'prepare', pullRequest: 25, title: 'arbitrary' },
    { operation: 'keep-step', issueNumber: 24, currentStep: 5, newPhaseAuthorized: true },
    recoveryRequest({ legacyPublicationRecoveryAuthorized: false }), recoveryRequest({ legacyPublicationRecoveryAuthorized: undefined }),
    recoveryRequest({ labels: ['step-9'] }), recoveryRequest({ currentStep: 5 }), recoveryRequest({ reviewId: 0 })]) {
    const f = fixture();
    await assert.rejects(executeMetadataRequest(f.api, r));
    assert.equal(f.reads(), 0); assert.equal(f.mutations.length, 0);
  }
});

test('wrong Issue/PR binding, closed targets, malformed labels and other Steps fail before mutation', async () => {
  for (const mutate of [f => { f.issue.number = 26; }, f => { f.pr.body = 'Related to #26'; },
    f => { f.pr.head.repo.full_name = 'someone/else'; }, f => { f.pr.state = 'closed'; }, f => { f.issue.state = 'closed'; },
    f => { f.issue.user.login = 'someone'; }, f => { f.issue.labels = []; }, f => { f.pr.labels.push({ name: 'step-6' }); },
    f => { f.pr.labels = labels(7); }, f => { f.issue.labels = [{ name: 'Step-5' }]; }]) {
    const f = fixture(); mutate(f);
    await assert.rejects(prepareOwnerPhase(f.api, request())); assert.equal(f.mutations.length, 0);
  }
});

test('changed head, title or canonical Issue authority during preparation prevents remaining writes', async () => {
  for (const mutate of [f => { f.pr.head.sha = 'b'.repeat(40); }, f => { f.pr.title = 'Concurrent owner title'; },
    f => { f.issue.body = 'Different authorized goal'; }]) {
    const f = fixture();
    f.api.ensureStepLabel = async () => mutate(f);
    await assert.rejects(prepareOwnerPhase(f.api, request()), { code: 'AUTHORITY_CHANGED' });
    assert.equal(f.mutations.length, 0);
  }
});

test('unobserved label/title mutations fail final verification', async () => {
  for (const drop of ['/issues/25', '/pulls/25']) {
    const f = fixture(); const patch = f.api.patch;
    f.api.patch = async (path, value) => { if (path !== drop) await patch(path, value); };
    await assert.rejects(prepareOwnerPhase(f.api, request()), { code: drop === '/issues/25' ? 'STEP_LABEL_MISMATCH' : 'STEP_DISPLAY_MISMATCH' });
  }
});

test('new CR authoring rejects missing, multiple, mismatched labels and overflow', async () => {
  for (const mutate of [f => { f.issue.labels = []; }, f => { f.pr.labels.push({ name: 'step-6' }); },
    f => { f.pr.labels = labels(6); }, f => { f.issue.labels = f.pr.labels = labels(Number.MAX_SAFE_INTEGER); }]) {
    const f = fixture(); mutate(f);
    await assert.rejects(prepareReviewStep(f.api, 25)); assert.equal(f.mutations.length, 0);
  }
});

test('explicit legacy publication recovery synchronizes only that same decisive native CR and adds its ID once', async () => {
  const f = legacyFixture();
  const result = await executeMetadataRequest(f.api, recoveryRequest());
  assert.deepEqual(result, { status: 'synchronized', issueNumber: 24, pullRequest: 25, reviewId: 90, step: 6 });
  assert.equal(currentStep(f.issue.labels), 6); assert.equal(currentStep(f.pr.labels), 6);
  assert.match(f.pr.title, new RegExp(`^Task 24 · Step 6 · ${f.cr.change_request_id} ·`));
  assert.ok(f.issue.labels.some(l => l.name === 'enhancement')); assert.ok(f.pr.labels.some(l => l.name === 'enhancement'));
  assert.deepEqual(f.mutations.map(m => m.path), ['/issues/24', '/issues/25', '/pulls/25']);
  await executeMetadataRequest(f.api, recoveryRequest());
  assert.equal(f.mutations.length, 3);
  const title = reviewStepTitle({ schema_version: '2.0', ...f.cr }, 24);
  assert.equal(reviewStepTitle({ schema_version: '2.0', ...f.cr,
    remediation_thread_title: `Task 24 — Step 6 — ${f.cr.change_request_id} — Reviewer-owned CR serialization` }, 24), title);
  assert.ok(Array.from(title).length <= RUN_NAME_IDENTITY_MAX_CHARS);
});

test('legacy partial transport resumes N/N+1 without another review or Step increment', async () => {
  const f = legacyFixture(); f.failPr(true);
  await assert.rejects(recoverLegacyReviewStep(f.api, recoveryRequest()), { code: 'EIO' });
  assert.equal(currentStep(f.issue.labels), 6); assert.equal(currentStep(f.pr.labels), 5);
  f.failPr(false);
  await recoverLegacyReviewStep(f.api, recoveryRequest());
  assert.equal(currentStep(f.pr.labels), 6);
  assert.equal(f.mutations.filter(m => m.path === '/issues/24').length, 1);
});

test('legacy recovery rejects stale, superseded, foreign, dismissed and malformed CRs before writes', async () => {
  for (const mutate of [f => { f.review.id++; }, f => { f.review.user.login = OWNER; }, f => { f.review.state = 'APPROVED'; },
    f => { f.review.state = 'DISMISSED'; }, f => { f.pr.head.sha = 'b'.repeat(40); }, f => { f.review.body = 'No executable authority'; },
    f => { f.issue.labels = labels(3); }, f => { f.pr.labels.push({ name: 'step-6' }); },
    f => { f.cr.step = 8; f.review.body = f.body(); },
    f => { f.api.list = async () => [f.review, { ...f.review, id: 91, state: 'APPROVED' }]; }]) {
    const f = legacyFixture(); mutate(f);
    await assert.rejects(recoverLegacyReviewStep(f.api, recoveryRequest()));
    assert.equal(f.mutations.length, 0);
  }
});

test('legacy recovery rejects changed authority and verifies final label/title observation', async () => {
  const f = legacyFixture(); f.api.ensureStepLabel = async () => { f.review.body += '\nChanged authority'; };
  await assert.rejects(recoverLegacyReviewStep(f.api, recoveryRequest()), { code: 'AUTHORITY_CHANGED' });
  assert.equal(f.mutations.length, 0);
  for (const drop of ['/issues/25', '/pulls/25']) {
    const g = legacyFixture(); const patch = g.api.patch;
    g.api.patch = async (path, value) => { if (path !== drop) await patch(path, value); };
    await assert.rejects(recoverLegacyReviewStep(g.api, recoveryRequest()), { code: drop === '/issues/25' ? 'STEP_LABEL_MISMATCH' : 'STEP_DISPLAY_MISMATCH' });
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
