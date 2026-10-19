import test from 'node:test';
import assert from 'node:assert/strict';
import { writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { fixture } from './fixture.mjs';
import { createPublicationBroker } from '../src/publication-broker.mjs';
import { REPOSITORY, WRITER } from '../src/execution-contract.mjs';
import { CONSUMER } from '../../consumer/consumer.mjs';
import { projectedRequestTitle } from '../src/step-metadata.mjs';
import { admissionBinding, createAdmissionSnapshot, extractAuthorityRecord } from '../../contracts/src/github-authority.mjs';

const copy = value => structuredClone(value);
const charter = 'Authority model: github-native-v1\nIssue closure policy: keep-open\nImplement the admitted source and preserve historical manual reports.';
const writer = { login: WRITER, type: 'Bot', id: 702 };

async function historicalIssue(t, { delivery = 'normal', successorEffects = false } = {}) {
  const f = await fixture(t, { issueBody: charter, route: 'manual', labelLaunch: true, streamlinedAdmission: true,
    beforeAdmission: async ({ store }) => store.put(98, { envelope: { repository: REPOSITORY,
      issueNumber: 42, runId: 98, attemptId: 'run-98', step: 1 } }) });
  const e = f.envelope;
  assert.equal(e.step, 2);
  const successor = { ...copy(e), runId: 100, attemptId: 'run-100', step: 3,
    request: createAdmissionSnapshot({ request: e.request, authority: e.request.authority,
      resolution: e.request.authority_resolution }, { step: 3, attempt: 'run-100', runId: 100, route: 'manual' }) };
  await f.command(f.source, ['switch', '-c', e.branch]);
  await writeFile(join(f.source, 'docs/work.md'), 'independent Step 3 implementation\n');
  await f.command(f.source, ['commit', '-am', 'independent successor implementation']);
  await f.command(f.source, ['push', f.remote, e.branch]);
  const head = await f.remoteHead();
  const pr = { number: 43, node_id: 'PR_successor', title: projectedRequestTitle(successor.request),
    labels: [{ name: 'step-3' }, { name: 'owner-label' }], state: 'open', merged: false, draft: false,
    body: `Related to #42\nAttempt: ${successor.attemptId}\nExecution admission digest: ${admissionBinding(successor.request).sha256}`,
    base: { ref: CONSUMER.baseBranch, sha: e.historicalBase, repo: { full_name: REPOSITORY } },
    head: { ref: e.branch, sha: head, repo: { full_name: REPOSITORY } } };
  const nextRecord = { envelope: successor, nativeAdmission: true, prNumber: 43,
    ...(successorEffects ? { publicationIntent: { previous: e.startHead, head },
      lifecycleIntent: { number: 43, head, draft: true }, prIntent: true,
      relationshipIntent: { number: 43, head, before: pr.body, body: pr.body },
      commentIntent: { key: 'outcome', number: 43, body: 'successor-owned pending Outcome' } } : {}) };
  await f.store.put(100, nextRecord);
  f.issue.labels = [{ name: 'step-3' }, { name: 'owner-label' }];
  const result = { schema_version: '4.0', kind: 'outcome', repository: REPOSITORY, task: 42,
    parent: { kind: 'issue', number: 42 }, charter_sha256: e.request.charter_sha256, step: e.step,
    authority: copy(e.request.authority), admission: admissionBinding(e.request), attempt: e.attemptId,
    status: 'blocked', result: { kind: 'qualification', revision: 'manual-step-2-blocked', identities: [] },
    summary: 'Original manual Step 2 stopped before publishing source or creating a PR.', warnings: [],
    limitations: ['The original blocker requires owner disposition.'] };
  const artifacts = [pr]; const reads = []; const posts = []; const writes = [];
  let readFailure = null;
  const get = f.api.get.bind(f.api); const list = f.api.list.bind(f.api); const post = f.api.post.bind(f.api);
  const identity = f.api.userIdentity.bind(f.api);
  f.api.get = async path => {
    reads.push(path);
    if (readFailure && path === readFailure.path) throw readFailure.error;
    if (path === '/pulls/43' || path === '/issues/43') return copy(pr);
    const artifact = artifacts.find(value => path === `/pulls/${value.number}`);
    return artifact ? copy(artifact) : get(path);
  };
  f.api.list = async path => {
    reads.push(path);
    if (readFailure && (path === readFailure.path || readFailure.path === 'pulls' && path.startsWith('/pulls?')))
      throw readFailure.error;
    if (path.startsWith('/pulls?')) return copy(artifacts.filter(value => !path.includes('state=open') || value.state === 'open'));
    return list(path);
  };
  f.api.userIdentity = async login => login === WRITER ? copy(writer) : identity(login);
  f.api.post = async (path, body) => {
    posts.push({ path, body: copy(body) });
    assert.equal(path, '/issues/42/comments', 'historical Outcome belongs to its original Issue');
    if (delivery === 'uncertain-before' && posts.length === 1)
      throw Object.assign(new Error('Native POST delivery is unknown'), { code: 'POST_UNCERTAIN' });
    const comment = await post(path, body);
    comment.user = copy(writer);
    f.comments.find(value => value.id === comment.id).user = copy(writer);
    if (delivery === 'lost-response' && posts.length === 1)
      throw Object.assign(new Error('Native POST response was lost'), { code: 'POST_UNCERTAIN' });
    return copy(comment);
  };
  for (const method of ['patch', 'delete', 'ready', 'draft']) f.api[method] = async (...args) => {
    writes.push({ method, args }); assert.fail(`Historical publication attempted native ${method}`);
  };
  const broker = createPublicationBroker({ api: f.api, store: f.store, publisher: {}, journal: f.journal, allowManualOutcome: true });
  const invoke = (value = result) => broker.dispatch({ operation: 'manual-outcome-direct', runId: e.runId,
    attemptId: e.attemptId, submission: { repository: REPOSITORY, task: 42, run_id: e.runId, result: value } });
  const before = { pr: copy(pr), issue: copy(f.issue), successor: copy(nextRecord), head };
  async function assertSuccessorUntouched() {
    assert.deepEqual(pr, before.pr);
    assert.deepEqual(f.issue, before.issue);
    assert.deepEqual(await f.store.get(100), before.successor);
    assert.equal(await f.remoteHead(), before.head);
    assert.deepEqual(writes, []);
    const own = await f.store.get(e.runId);
    assert.equal(own.prNumber, undefined);
    assert.equal(own.prIntent, undefined);
    assert.equal(own.publicationIntent, null);
  }
  return { ...f, pr, successor, result, artifacts, reads, posts, invoke, assertSuccessorUntouched,
    failRead: (path, error) => { readFailure = { path, error }; } };
}

for (const successorEffects of [false, true]) test(`historical Issue BLOCKED Outcome ignores a later Step PR and its pending effects=${successorEffects}`, async t => {
  const f = await historicalIssue(t, { successorEffects });
  const receipt = await f.invoke();
  assert.equal(receipt.status, 'BLOCKED'); assert.equal(receipt.prNumber, null); assert.equal(receipt.head, null);
  assert.equal(f.posts.length, 1); assert.equal(f.comments.length, 1);
  assert.ok(f.reads.some(path => path.startsWith('/pulls?state=all&')));
  const body = f.comments[0].body; const published = extractAuthorityRecord(body);
  assert.deepEqual(published.parent, f.result.parent);
  assert.deepEqual(published.admission, f.result.admission);
  assert.deepEqual(published.authority, f.result.authority);
  assert.equal(published.attempt, f.result.attempt); assert.equal(published.step, 2);
  assert.equal(published.status, 'blocked'); assert.deepEqual(published.result, f.result.result);
  assert.ok(published.limitations.some(value => value.includes('Historical attempt report only')));
  const saved = await f.store.get(f.envelope.runId);
  assert.deepEqual(await f.invoke(), receipt); assert.deepEqual(await f.invoke(), receipt);
  assert.equal(f.posts.length, 1); assert.equal(f.comments[0].body, body);
  assert.deepEqual((await f.store.get(f.envelope.runId)).manualSubmission, saved.manualSubmission);
  await f.assertSuccessorUntouched();
});

test('lost historical Issue Outcome POST response recovers exact bytes once without successor mutation', async t => {
  const f = await historicalIssue(t, { delivery: 'lost-response', successorEffects: true });
  await assert.rejects(f.invoke(), { code: 'POST_UNCERTAIN' });
  const reserved = await f.store.get(f.envelope.runId); const body = f.comments[0].body;
  assert.equal(reserved.outcome, null); assert.equal(reserved.commentIntent.number, 42);
  assert.equal(reserved.commentIntent.body, body);
  assert.deepEqual(reserved.manualSubmission.publishedResult, extractAuthorityRecord(body));
  const receipt = await f.invoke(); assert.equal(receipt.outcomeId, f.comments[0].id);
  assert.deepEqual(await f.invoke(), receipt); assert.equal(f.posts.length, 1);
  assert.equal(f.comments[0].body, body); assert.equal((await f.store.get(f.envelope.runId)).commentIntent, null);
  await f.assertSuccessorUntouched();
});

test('historical Issue qualification success reports the original admission without changing successor readiness', async t => {
  const f = await historicalIssue(t, { successorEffects: true });
  f.result.status = 'implemented';
  f.result.summary = 'The original manual qualification completed without publishing source or creating a PR.';
  const receipt = await f.invoke();
  assert.equal(receipt.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
  assert.equal(receipt.prNumber, null);
  const published = extractAuthorityRecord(f.comments[0].body);
  assert.equal(published.status, 'implemented'); assert.deepEqual(published.parent, f.result.parent);
  assert.deepEqual(published.admission, f.result.admission);
  assert.deepEqual(await f.invoke(), receipt); assert.equal(f.posts.length, 1);
  await f.assertSuccessorUntouched();
});

test('uncertain historical Issue Outcome POST with no native record never retries delivery', async t => {
  const f = await historicalIssue(t, { delivery: 'uncertain-before' });
  await assert.rejects(f.invoke(), { code: 'POST_UNCERTAIN' });
  const reserved = await f.store.get(f.envelope.runId);
  await assert.rejects(f.invoke(), { code: 'COMMENT_PUBLICATION_UNCERTAIN' });
  assert.equal(f.posts.length, 1); assert.equal(f.comments.length, 0);
  assert.deepEqual((await f.store.get(f.envelope.runId)).commentIntent, reserved.commentIntent);
  await f.assertSuccessorUntouched();
});

test('historical Issue Outcome replay rejects caller changes and altered durable content', async t => {
  const f = await historicalIssue(t);
  await f.invoke();
  await assert.rejects(f.invoke({ ...copy(f.result), summary: 'Changed original report' }), { code: 'MANUAL_OUTCOME_CHANGED' });
  f.comments[0].body += '\nchanged native bytes';
  await assert.rejects(f.invoke(), { code: 'COMMENT_CONTENT_CHANGED' });
  assert.equal(f.posts.length, 1); await f.assertSuccessorUntouched();
});

for (const [name, value, code] of [
  ['prIntent', true, 'PR_AUTHORITY_CHANGED'], ['prNumber', 43, 'PR_AUTHORITY_CHANGED'],
  ['publicationIntent', { previous: null, head: 'a'.repeat(40) }, 'MANUAL_OUTCOME_PUBLICATION_UNRESOLVED'],
  ['publishedHead', 'a'.repeat(40), 'MANUAL_OUTCOME_PUBLICATION_UNRESOLVED'],
  ['lifecycleIntent', { number: 43, head: 'a'.repeat(40), draft: true }, 'MANUAL_OUTCOME_PUBLICATION_UNRESOLVED'],
  ['relationshipIntent', { number: 43, head: 'a'.repeat(40) }, 'MANUAL_OUTCOME_PUBLICATION_UNRESOLVED'],
  ['readinessIntent', { number: 43, head: 'a'.repeat(40) }, 'MANUAL_OUTCOME_PUBLICATION_UNRESOLVED'],
  ['successOutcomeIntent', { prNumber: 43, head: 'a'.repeat(40), body: 'reserved success' }, 'MANUAL_OUTCOME_PUBLICATION_UNRESOLVED'],
  ['commentIntent', { key: 'outcome', number: 43, body: 'unresolved PR Outcome' }, 'MANUAL_OUTCOME_PUBLICATION_UNRESOLVED'],
]) test(`historical Issue Outcome does not bypass its own ${name}`, async t => {
  const f = await historicalIssue(t); const record = await f.store.get(f.envelope.runId);
  record[name] = value; await f.store.put(f.envelope.runId, record);
  await assert.rejects(f.invoke(), { code });
  assert.equal(f.posts.length, 0); assert.deepEqual(await f.store.get(100), { envelope: f.successor, nativeAdmission: true, prNumber: 43 });
});

for (const state of ['open', 'closed']) for (const marker of ['digest', 'attempt'])
  test(`historical Issue Outcome rejects its own ${state} PR identified by ${marker}`, async t => {
    const f = await historicalIssue(t);
    f.pr.state = state;
    f.pr.body = `Related to #42\n${marker === 'digest' ? `Execution admission digest: ${admissionBinding(f.envelope.request).sha256}` : `Attempt: ${f.envelope.attemptId}`}`;
    await assert.rejects(f.invoke(), { code: 'PR_AUTHORITY_CHANGED' });
    assert.equal(f.posts.length, 0);
  });

test('historical Issue Outcome rejects ambiguous open PR artifacts before publication', async t => {
  const f = await historicalIssue(t);
  f.artifacts.push({ ...copy(f.pr), number: 44 });
  await assert.rejects(f.invoke(), { code: 'PR_AMBIGUOUS' });
  assert.equal(f.posts.length, 0);
});

for (const binding of ['absent', 'unknown', 'wrong-task', 'wrong-branch'])
  test(`historical Issue Outcome refuses an open PR with ${binding} successor admission binding`, async t => {
    const f = await historicalIssue(t);
    if (binding === 'absent') f.pr.body = 'Related to #42';
    if (binding === 'unknown') f.pr.body = 'Related to #42\nExecution admission digest: ' + 'f'.repeat(64);
    if (binding === 'wrong-task' || binding === 'wrong-branch') {
      const record = await f.store.get(100);
      if (binding === 'wrong-task') {
        // Keep an independent later Task projection, so this exercises the
        // historical lookup rather than falling back to the current path.
        const latest = { ...copy(f.successor), runId: 101, attemptId: 'run-101', step: 4,
          request: createAdmissionSnapshot({ request: f.successor.request, authority: f.successor.request.authority,
            resolution: f.successor.request.authority_resolution }, { step: 4, attempt: 'run-101', runId: 101 }) };
        await f.store.put(101, { envelope: latest });
        record.envelope.issueNumber = 45;
      }
      else record.envelope.branch = `${f.envelope.branch}-other`;
      await f.store.put(100, record);
    }
    await assert.rejects(f.invoke(), { code: 'PR_AUTHORITY_CHANGED' });
    assert.equal(f.posts.length, 0);
  });

for (const target of ['prNumber', 'target', 'continuation', 'existing_pr'])
  test(`historical Issue Outcome rejects successor ${target} bound to a different PR`, async t => {
    const f = await historicalIssue(t); const record = await f.store.get(100);
    if (target === 'prNumber') record.prNumber = 44;
    if (target === 'target') { record.envelope.target = 'pull_request'; record.envelope.number = 44; delete record.prNumber; }
    if (target === 'continuation') {
      record.envelope.continuation = { head: record.envelope.startHead, pullRequest: 44 };
      delete record.prNumber;
    }
    if (target === 'existing_pr') {
      record.envelope.request.existing_pr = 44; delete record.prNumber;
      f.pr.body = `Related to #42\nAttempt: ${record.envelope.attemptId}\nExecution admission digest: ${admissionBinding(record.envelope.request).sha256}`;
    }
    await f.store.put(100, record);
    await assert.rejects(f.invoke(), { code: 'PR_AUTHORITY_CHANGED' });
    assert.equal(f.posts.length, 0);
    assert.deepEqual(await f.store.get(100), record);
  });

for (const field of ['parent', 'task', 'admission', 'attempt']) test(`historical Issue Outcome rejects mismatched ${field}`, async t => {
  const f = await historicalIssue(t); const result = copy(f.result);
  if (field === 'parent') result.parent.number = 45;
  if (field === 'task') result.task = 45;
  if (field === 'admission') result.admission.sha256 = 'f'.repeat(64);
  if (field === 'attempt') result.attempt = 'run-100';
  await assert.rejects(f.invoke(result), { code: field === 'parent' ? 'PR_AUTHORITY_CHANGED'
    : field === 'task' ? 'AUTHORITY_TARGET_MISMATCH'
      : field === 'attempt' ? 'AUTHORITY_ADMISSION_MISMATCH' : 'MANUAL_OUTCOME_BINDING_INVALID' });
  assert.equal(f.posts.length, 0);
});

test('a closed unbound PR from branch history does not become the historical Issue Outcome parent', async t => {
  const f = await historicalIssue(t);
  f.artifacts.push({ ...copy(f.pr), number: 44, state: 'closed', body: 'Related to #42\nOld branch history' });
  const receipt = await f.invoke(); assert.equal(receipt.prNumber, null);
  assert.equal(f.posts.length, 1); await f.assertSuccessorUntouched();
});

test('historical Issue Outcome replay propagates a failed native exact-comment read without another POST', async t => {
  const f = await historicalIssue(t);
  const receipt = await f.invoke();
  f.failRead(`/issues/comments/${receipt.outcomeId}`, Object.assign(new Error('Native comment read unavailable'), { code: 'GITHUB_REQUEST_FAILED' }));
  await assert.rejects(f.invoke(), { code: 'GITHUB_REQUEST_FAILED' });
  assert.equal(f.posts.length, 1); assert.equal(f.comments.length, 1);
  await f.assertSuccessorUntouched();
});

for (const path of ['pulls', '/issues/42/comments']) test(`historical Issue Outcome preserves native read failure at ${path}`, async t => {
  const f = await historicalIssue(t); const error = Object.assign(new Error('Native API read failed'), { code: 'GITHUB_REQUEST_FAILED' });
  f.failRead(path, error);
  await assert.rejects(f.invoke(), { code: 'GITHUB_REQUEST_FAILED' });
  assert.equal(f.posts.length, 0); assert.equal(f.comments.length, 0);
  await f.assertSuccessorUntouched();
});
