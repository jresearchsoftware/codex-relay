import test from 'node:test';
import assert from 'node:assert/strict';
import { assertPublicationIsolation, latestProjection } from '../src/publication-isolation.mjs';
import { fixture } from './fixture.mjs';
import { runAttempt } from '../src/attempt.mjs';
import { CONSUMER } from '../../consumer/consumer.mjs';
import { OWNER, REPOSITORY, REVIEWER } from '../src/execution-contract.mjs';
import { recoveryAuthorization, recoveryAuthorizationBody } from '../src/publication-recovery.mjs';
import { createAdmissionSnapshot, extractAuthorityRecord, renderAuthorityRecord, sha256Body } from '../../contracts/src/github-authority.mjs';

const charter = 'Authority model: github-native-v1\nIssue closure policy: keep-open\nImplement independent source work.';
const success = e => ({ version: e.version, attemptId: e.attemptId, child: 'started', containment: 'reaped',
  result: { status: 'success', summary: 'Isolated candidate completed.', validation: [] } });
const nativeFixture = t => fixture(t, { issueBody: charter, labelLaunch: true, streamlinedAdmission: true });
function successor(e, { branch = e.branch, step = e.step + 1 } = {}) {
  const request = createAdmissionSnapshot({ request: { ...e.request, branch }, authority: e.request.authority },
    { step, attempt: 'run-100', runId: 100, route: e.route });
  return { ...e, runId: 100, attemptId: 'run-100', step, branch, request };
}
async function holdLifecycle(f, head = f.envelope.startHead) {
  const record = { envelope: { ...f.envelope, runId: 100, attemptId: 'run-100' },
    prNumber: 43, lifecycleIntent: { number: 43, head, draft: false } };
  await f.store.put(100, record);
  return record;
}
async function publishProgress(f) {
  await f.prepare(f.envelope); const head = await f.commit();
  const progress = await f.collect(f.envelope);
  await f.broker.invoke({ operation: 'publish-progress', runId: f.envelope.runId,
    attemptId: f.envelope.attemptId, bundle: progress.bundle });
  return { head, progress };
}

const envelope = (step, overrides = {}) => ({ repository: REPOSITORY, issueNumber: 42,
  target: 'issue', number: 42, branch: 'codex/task-42', attemptId: `run-${step}`,
  step, request: { kind: 'admission' }, ...overrides });

test('only successful same-Task native admissions select the latest display projection', () => {
  const e = envelope(1);
  const records = [{ envelope: envelope(2) }, { envelope: envelope(9), admissionBlock: {} },
    { envelope: envelope(90, { issueNumber: 43 }) }, { envelope: envelope(99, { repository: 'foreign/repo' }) }];
  assert.equal(latestProjection(records, e).step, 2);
  assert.equal(latestProjection(records, { ...e, request: undefined }).step, 2);
  const independent = [{ envelope: envelope(2, { branch: 'codex/independent' }) }];
  assert.equal(latestProjection(independent, e).step, 2);
  assert.equal(latestProjection(independent, e, { sameBranch: true }).step, 1);
});

test('uncertain sibling push/PR intent holds only its exact repository and ref', () => {
  const e = envelope(1);
  for (const intent of [{ publicationIntent: { previous: null, head: 'a'.repeat(40) } }, { prIntent: true }]) {
    const record = { envelope: envelope(2), ...intent };
    assert.throws(() => assertPublicationIsolation([record], e), { code: 'PUBLICATION_TARGET_HELD' });
    assert.doesNotThrow(() => assertPublicationIsolation([{ ...record, envelope: envelope(2, { branch: 'independent' }) }], e));
    assert.doesNotThrow(() => assertPublicationIsolation([{ ...record, envelope: envelope(2, { repository: 'foreign/repo' }) }], e));
  }
  assert.doesNotThrow(() => assertPublicationIsolation([{ envelope: envelope(2), commentIntent: { key: 'outcome' } }], e));
});

test('unknown lifecycle operation holds its exact PR while same-attempt recovery remains available', () => {
  const e = envelope(1, { target: 'pull_request', number: 43 });
  const row = { envelope: envelope(2), prNumber: 43, lifecycleIntent: { draft: false } };
  assert.throws(() => assertPublicationIsolation([row], e), { code: 'PUBLICATION_TARGET_HELD' });
  assert.doesNotThrow(() => assertPublicationIsolation([{ ...row, envelope: e }], e));
  assert.throws(() => assertPublicationIsolation([row], envelope(1)), { code: 'PUBLICATION_TARGET_HELD' });
});

for (const operation of ['terminal-outcome', 'finish']) {
  test(`${operation} cannot change a fresh Issue PR while a sibling owns its unresolved lifecycle operation`, async t => {
    const f = await fixture(t); const { head } = await publishProgress(f);
    await f.api.ready(); const before = await f.api.get('/pulls/43');
    const sibling = await holdLifecycle(f, head);
    await assert.rejects(f.broker.invoke({ operation, runId: f.envelope.runId,
      attemptId: f.envelope.attemptId, head, status: 'blocked', terminalCode: 'SEMANTIC_RESULT_BLOCKED' }),
    { code: 'PUBLICATION_TARGET_HELD' });
    assert.deepEqual(await f.api.get('/pulls/43'), before);
    assert.deepEqual(await f.store.get(100), sibling);
    assert.equal(f.pushes(), 1); assert.equal(f.comments.length, 0);
  });
}

test('complete-handoff retains its durable Outcome without Ready while a sibling lifecycle intent is unresolved', async t => {
  const f = await fixture(t); let ready = 0; let sibling;
  const originalReady = f.api.ready.bind(f.api);
  f.api.ready = async (...args) => { ready++; return originalReady(...args); };
  const broker = { async invoke(request) {
    if (request.operation === 'complete-handoff') sibling = await holdLifecycle(f, (await f.store.get(99)).finalHead);
    return f.broker.invoke(request);
  } };
  await assert.rejects(runAttempt({ ...f, broker, execute: async e => {
    await f.commit(); return success(e);
  } }), { code: 'PUBLICATION_TARGET_HELD' });
  assert.equal(ready, 0); assert.equal((await f.api.get('/pulls/43')).draft, true);
  assert.equal(f.comments.length, 1); assert.equal(f.pushes(), 1);
  assert.equal((await f.store.get(99)).outcome.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
  assert.deepEqual(await f.store.get(100), sibling);
});

test('authorized original push recovery cannot bypass a sibling lifecycle hold on the same ref', async t => {
  const f = await fixture(t); await f.prepare(f.envelope); await f.commit();
  const progress = await f.collect(f.envelope);
  f.failPush(true);
  await assert.rejects(f.broker.invoke({ operation: 'publish-progress', runId: 99,
    attemptId: f.envelope.attemptId, bundle: progress.bundle }), { code: 'PUBLICATION_UNCERTAIN' });
  f.failPush(false);
  const original = await f.store.get(99);
  f.run.status = 'completed'; f.run.updated_at = '2026-09-04T12:01:00Z';
  const authorizationId = 10000;
  f.comments.push({ id: authorizationId, user: { login: OWNER, type: 'User' },
    issue_url: `https://api.github.com/repos/${REPOSITORY}/issues/42`,
    created_at: '2026-09-04T12:02:00Z', updated_at: '2026-09-04T12:02:00Z',
    body: recoveryAuthorizationBody(recoveryAuthorization(f.envelope, original.publicationIntent)) });
  const sibling = await holdLifecycle(f);
  await assert.rejects(f.broker.invoke({ operation: 'recover-publication', runId: 99,
    attemptId: f.envelope.attemptId, authorizationId, bundle: progress.bundle }), { code: 'PUBLICATION_TARGET_HELD' });
  assert.equal(f.pushes(), 1); assert.equal(await f.remoteHead(), null);
  assert.deepEqual(await f.store.get(99), original);
  assert.deepEqual(await f.store.get(100), sibling);
});

test('a late automatic result on an independent branch reports its original PR without restoring Task projections', async t => {
  const f = await nativeFixture(t); const { head } = await publishProgress(f);
  const original = await f.api.get('/pulls/43');
  const next = successor(f.envelope, { branch: 'codex/independent-42' });
  await f.store.put(100, { envelope: next });
  f.issue.labels = [{ name: 'step-2' }];
  const outcome = await f.broker.invoke({ operation: 'finish', runId: 99,
    attemptId: f.envelope.attemptId, head, taskResult: { summary: 'Original branch result.', validation: [] } });
  assert.equal(outcome.head, head); assert.equal(outcome.prNumber, 43);
  const published = extractAuthorityRecord(f.comments[0].body);
  assert.equal(published.step, 1); assert.equal(published.attempt, f.envelope.attemptId);
  assert.deepEqual(await f.api.get('/pulls/43'), original);
  assert.deepEqual(f.issue.labels, [{ name: 'step-2' }]);
  assert.deepEqual(await f.store.get(100), { envelope: next });
});

async function retainedRequestFixture(t) {
  return fixture(t, { beforeAdmission: async ({ issue, api }) => {
    const base = /Required starting base: `([^`]+)`/.exec(issue.body)[1];
    issue.body = charter;
    const request = { schema_version: '3.0', kind: 'task-request', repository: REPOSITORY, task: 42,
      parent: { kind: 'issue', number: 42 }, charter_sha256: sha256Body(charter), step: 1, route: 'auto',
      purpose: 'Retained source work', scope: ['Implement the authorized change.'],
      model: 'gpt-6.1-sol', effort: 'xhigh', subagents: true, validation: ['diff-check', 'secret-scan'],
      boundaries: ['No deployment, merge or closure.'], decisions: [], context: [], supersedes: null,
      branch: `${CONSUMER.taskBranchPrefix}test-42`, base_sha: base, starting_head: base, existing_pr: null,
      issue_closure_policy: 'keep-open' };
    const actor = { login: REVIEWER, id: 701, type: 'Bot' };
    const comment = { id: 901, body: renderAuthorityRecord(request), user: actor,
      issue_url: `https://api.github.com/repos/${REPOSITORY}/issues/42` };
    const get = api.get.bind(api); const list = api.list.bind(api);
    api.userIdentity = async login => { assert.equal(login, REVIEWER); return structuredClone(actor); };
    api.get = path => path === '/issues/comments/901' ? Promise.resolve(structuredClone(comment)) : get(path);
    api.list = async path => path === '/issues/42/comments' ? [structuredClone(comment), ...await list(path)]
      : /^\/pulls\/\d+\/reviews$/.test(path) ? [] : list(path);
  } });
}

for (const protocol of ['legacy', '3.0']) {
  test(`late retained ${protocol} BLOCKED Outcome cannot draft a newer native Step's Ready PR`, async t => {
    const f = protocol === 'legacy' ? await fixture(t, { remediation: true }) : await retainedRequestFixture(t);
    if (protocol === '3.0') await publishProgress(f);
    const seed = await nativeFixture(t);
    const next = successor(seed.envelope, { branch: f.envelope.branch, step: f.envelope.step + 1 });
    await f.store.put(100, { envelope: next });
    const title = `Task 42 · Step ${next.step} · ${next.request.purpose}`;
    await f.api.patch('/pulls/43', { title });
    await f.api.patch('/issues/43', { labels: [`step-${next.step}`] });
    f.issue.labels = [{ name: `step-${next.step}` }];
    await f.api.ready(); const before = await f.api.get('/pulls/43');
    const outcome = await f.broker.invoke({ operation: 'terminal-outcome', runId: 99,
      attemptId: f.envelope.attemptId, status: 'blocked', terminalCode: 'SEMANTIC_RESULT_BLOCKED' });
    assert.equal(outcome.status, 'BLOCKED');
    assert.deepEqual(await f.api.get('/pulls/43'), before);
    assert.deepEqual(f.issue.labels, [{ name: `step-${next.step}` }]);
    assert.deepEqual(await f.store.get(100), { envelope: next });
    assert.equal(f.comments.length, 1);
  });
}

test('Writer stops a competing candidate before push', async t => {
  const f = await fixture(t);
  await f.store.put(100, { envelope: { ...f.envelope, runId: 100, attemptId: 'run-100' },
    publicationIntent: { previous: null, head: 'a'.repeat(40) } });
  const execute = async e => { await f.commit(); return { version: 2, attemptId: e.attemptId, child: 'started', containment: 'reaped',
    result: { status: 'success', summary: 'Isolated candidate', validation: [] } }; };
  await assert.rejects(runAttempt({ ...f, execute }), { code: 'PUBLICATION_TARGET_HELD' });
  assert.equal(await f.remoteHead(), null);
});

test('an uncertain sibling PR creation cannot fall back to an Issue Outcome', async t => {
  const f = await fixture(t);
  await f.store.put(100, { envelope: { ...f.envelope, runId: 100, attemptId: 'run-100' }, prIntent: true });
  await assert.rejects(runAttempt({ ...f, execute: async e => {
    await f.commit(); return { version: 2, attemptId: e.attemptId, child: 'started', containment: 'reaped',
      result: { status: 'success', summary: 'Independent computation', validation: [] } };
  } }), { code: 'PUBLICATION_TARGET_HELD' });
  assert.equal(await f.remoteHead(), null);
  assert.equal(f.comments.length, 0);
});

test('first authorized sibling publication uses current Step metadata without completing its newer sibling', async t => {
  const f = await fixture(t, { issueBody: 'Authority model: github-native-v1\nIssue closure policy: keep-open\nImplement independent source work.',
    labelLaunch: true, streamlinedAdmission: true });
  const e = f.envelope;
  const next = { ...e, runId: 100, attemptId: 'run-100', step: 2,
    request: createAdmissionSnapshot({ request: e.request, authority: e.request.authority },
      { step: 2, attempt: 'run-100', runId: 100, route: 'auto' }) };
  const result = await runAttempt({ ...f, execute: async execution => {
    await f.store.put(100, { envelope: next });
    f.issue.labels = [{ name: 'step-2' }];
    await f.commit();
    return { version: 2, attemptId: execution.attemptId, child: 'started', containment: 'reaped',
      result: { status: 'success', summary: 'First authorized sibling output', validation: [] } };
  } });
  assert.equal(result.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
  assert.equal(f.pushes(), 1);
  const pr = await f.api.get('/pulls/43');
  assert.match(pr.title, /Step 2/);
  assert.deepEqual(pr.labels.map(label => label.name), ['step-2']);
  assert.equal(pr.draft, true);
  assert.equal((await f.store.get(100)).outcome, undefined);
});
