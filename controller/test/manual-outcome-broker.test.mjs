import test from 'node:test';
import assert from 'node:assert/strict';
import { fixture } from './fixture.mjs';
import { createPublicationBroker } from '../src/publication-broker.mjs';
import { CONSUMER } from '../../consumer/consumer.mjs';
import { REPOSITORY, WRITER, REVIEWER } from '../src/execution-contract.mjs';
import { admissionBinding, canonicalAuthorityJson, createAdmissionSnapshot, extractAuthorityRecord, sha256Body } from '../../contracts/src/github-authority.mjs';

const charter = 'Authority model: github-native-v1\nIssue closure policy: keep-open\nImplement the admitted repository change through manual Codex; independent acceptance remains required.';
const copy = value => structuredClone(value);

async function manualBroker(t, race) {
  const decisions = [];
  const f = await fixture(t, { issueBody: charter, route: 'manual', labelLaunch: true, streamlinedAdmission: true });
  const e = f.envelope;
  const pr = { number: 43, node_id: 'PR_manual', state: 'open', merged: false, draft: true,
    body: 'Related to #42', base: { ref: CONSUMER.baseBranch, sha: e.historicalBase, repo: { full_name: REPOSITORY } },
    head: { ref: e.branch, sha: e.startHead, repo: { full_name: REPOSITORY } } };
  const result = { schema_version: '4.0', kind: 'outcome', repository: REPOSITORY, task: 42,
    parent: { kind: 'pull_request', number: pr.number }, charter_sha256: e.request.charter_sha256,
    step: e.step, authority: copy(e.request.authority), admission: admissionBinding(e.request), attempt: e.attemptId,
    status: 'implemented', result: { kind: 'git', revision: pr.head.sha, identities: [] },
    summary: 'Manual implementation is complete at the exact candidate head.', warnings: [], limitations: [] };
  let posts = 0; let ready = 0; let changed = false; let reservedBeforeChange = false;
  const removeMarker = () => { changed = true; pr.body = 'Related to #42\nAdmission binding removed concurrently.'; };
  const originalGet = f.api.get.bind(f.api);
  const originalList = f.api.list.bind(f.api);
  const originalPost = f.api.post.bind(f.api);
  const originalIdentity = f.api.userIdentity.bind(f.api);
  const originalPut = f.store.put.bind(f.store);
  f.api.get = path => path === '/pulls/43' ? Promise.resolve(copy(pr)) : originalGet(path);
  f.api.list = path => path.startsWith('/pulls?') ? assert.fail('An explicit new v4 PR must not scan unrelated PRs')
    : path === '/pulls/43/reviews' ? Promise.resolve([])
    : path === '/issues/42/comments' ? originalList(path).then(values => [...decisions, ...values]) : originalList(path);
  f.api.userIdentity = login => login === WRITER ? Promise.resolve({ login, type: 'Bot', id: 702 }) : originalIdentity(login);
  f.api.post = async (path, body) => {
    assert.equal(path, '/issues/43/comments');
    posts++;
    const comment = await originalPost(path, body);
    comment.user = { login: WRITER, type: 'Bot', id: 702 };
    f.comments.find(value => value.id === comment.id).user = copy(comment.user);
    if (race === 'after-outcome') removeMarker();
    if (race === 'lost-outcome-response' && posts === 1) {
      throw Object.assign(new Error('Lost native Outcome POST response'), { code: 'POST_UNCERTAIN' });
    }
    return copy(comment);
  };
  f.api.ready = async node => { assert.equal(node, pr.node_id); ready++; pr.draft = false; };
  f.api.draft = async () => { assert.fail('Implemented manual result should only request Ready'); };
  f.store.put = async (id, record) => {
    await originalPut(id, record);
    if (race === 'after-reservation' && record.lifecycleIntent && record.outcome && !changed) {
      reservedBeforeChange = true; removeMarker();
    }
  };
  const broker = createPublicationBroker({ api: f.api, store: f.store, publisher: {}, journal: f.journal, allowManualOutcome: true });
  const invoke = () => broker.dispatch({ operation: 'manual-outcome-direct', runId: e.runId, attemptId: e.attemptId,
    submission: { repository: REPOSITORY, task: 42, run_id: e.runId, result } });
  const amend = amendments => decisions.push({ id: 900 + decisions.length,
    user: { login: REVIEWER, type: 'Bot', id: 701 }, body: '```relay-authority\n' + canonicalAuthorityJson({
      schema_version: '4.0', kind: 'decision', repository: REPOSITORY, task: 42,
      parent: { kind: 'issue', number: 42 }, charter_sha256: sha256Body(charter),
      purpose: 'Require owner discussion before approval', amendments, supersedes: null, context: [] }) + '\n```\n' });
  return { ...f, pr, result, invoke, amend, posts: () => posts, ready: () => ready,
    reservedBeforeChange: () => reservedBeforeChange };
}

test('real broker publishes bound manual Git Outcome before a verified native Ready transition', async t => {
  const f = await manualBroker(t);
  const receipt = await f.invoke();
  assert.equal(receipt.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
  assert.equal(f.posts(), 1); assert.equal(f.ready(), 1); assert.equal(f.pr.draft, false);
  assert.deepEqual(extractAuthorityRecord(f.comments[0].body), { ...f.result, authority_resolution: f.envelope.request.authority_resolution });
  assert.equal((await f.store.get(f.envelope.runId)).lifecycleIntent, null);
});

test('manual successful Outcome remains review-ready under new Deliberative approval constraints, including replay', async t => {
  const f = await manualBroker(t);
  f.amend({ purpose: 'Discuss this exact result before APPROVE',
    boundaries: [...f.envelope.request.boundaries, 'No APPROVE before owner discussion'] });
  await f.invoke();
  assert.equal(f.pr.draft, false); assert.equal(f.ready(), 1);
  const body = f.comments[0].body;
  const outcome = extractAuthorityRecord(body);
  assert.equal(outcome.authority_drift.review_required, true);
  assert.deepEqual(outcome.authority_drift.changed_fields, ['boundaries', 'purpose']);
  await f.invoke(); await f.invoke();
  assert.equal(f.posts(), 1); assert.equal(f.ready(), 1); assert.equal(f.comments[0].body, body);
});

test('manual blocked Outcome stays Draft under amended authority', async t => {
  const f = await manualBroker(t);
  f.result.status = 'blocked';
  f.amend({ boundaries: [...f.envelope.request.boundaries, 'No APPROVE before owner discussion'] });
  await f.invoke(); await f.invoke();
  assert.equal(f.pr.draft, true); assert.equal(f.ready(), 0); assert.equal(f.posts(), 1);
});

test('handoff still rejects changed starting pins after publishing one manual Outcome', async t => {
  const f = await manualBroker(t);
  f.amend({ starting_head: 'f'.repeat(40) });
  await assert.rejects(f.invoke(), { code: 'AUTHORITY_CHANGED' });
  assert.equal(f.pr.draft, true); assert.equal(f.ready(), 0); assert.equal(f.posts(), 1);
});

for (const [name, mutate, code] of [
  ['repository', f => { f.pr.head.repo.full_name = 'foreign/repo'; }, 'MANUAL_PR_REPOSITORY_MISMATCH'],
  ['Task', f => { f.pr.body = 'Related to #41'; }, 'MANUAL_PR_TASK_MISMATCH'],
  ['branch', f => { f.pr.head.ref += '-wrong'; }, 'MANUAL_PR_BRANCH_MISMATCH'],
  ['base', f => { f.pr.base.ref = 'wrong'; }, 'MANUAL_PR_BASE_MISMATCH'],
  ['head', f => { f.pr.head.sha = 'b'.repeat(40); }, 'MANUAL_PR_HEAD_MISMATCH'],
  ['PR number', f => { f.pr.number = 44; }, 'MANUAL_PR_TARGET_MISMATCH'],
]) test(`explicit manual ${name} input error is specific and correctable before reservation`, async t => {
  const f = await manualBroker(t); const before = copy(f.pr); mutate(f);
  await assert.rejects(f.invoke(), { code });
  assert.equal(f.posts(), 0); assert.equal(f.ready(), 0);
  assert.equal((await f.store.get(f.envelope.runId)).manualSubmission, undefined);
  Object.assign(f.pr, before);
  await f.invoke(); assert.equal(f.posts(), 1); assert.equal(f.ready(), 1);
});

test('explicit manual target is author-neutral and ignores historical or unrelated open branch PRs', async t => {
  const f = await manualBroker(t);
  f.pr.user = { login: 'another-contributor', type: 'User', id: 900 };
  await f.invoke(); assert.equal(f.posts(), 1); assert.equal(f.ready(), 1);
});

test('unresolved sibling publication blocks explicit manual reporting before a claim or Outcome is reserved', async t => {
  const f = await manualBroker(t);
  await f.store.put(100, { envelope: { ...f.envelope, runId: 100, attemptId: 'run-100' },
    publicationIntent: { previous: null, head: f.pr.head.sha } });
  await assert.rejects(f.invoke(), { code: 'PUBLICATION_TARGET_HELD' });
  assert.equal(f.posts(), 0); assert.equal(f.ready(), 0);
  assert.equal((await f.store.get(f.envelope.runId)).manualSubmission, undefined);
});

test('lost manual Outcome POST followed by a later Step replays the exact original result twice without another POST or Ready', async t => {
  const f = await manualBroker(t, 'lost-outcome-response');
  await assert.rejects(f.invoke(), { code: 'POST_UNCERTAIN' });
  const original = await f.store.get(f.envelope.runId);
  const originalBody = f.comments[0].body;
  assert.equal(original.outcome, null);
  assert.equal(original.commentIntent.body, originalBody);
  assert.deepEqual(original.manualSubmission.publishedResult, extractAuthorityRecord(originalBody));
  const e = f.envelope;
  const next = { ...e, runId: 100, attemptId: 'run-100', step: e.step + 1,
    request: createAdmissionSnapshot({ request: e.request, authority: e.request.authority },
      { step: e.step + 1, attempt: 'run-100', runId: 100, route: e.route }) };
  await f.store.put(100, { envelope: next });
  f.issue.labels = [{ name: `step-${next.step}` }];
  f.pr.draft = false;
  const before = copy(f.pr);
  const recovered = await f.invoke();
  assert.equal(recovered.outcomeId, f.comments[0].id);
  assert.deepEqual(await f.invoke(), recovered);
  assert.equal(f.posts(), 1); assert.equal(f.ready(), 0);
  assert.equal(f.comments.length, 1); assert.equal(f.comments[0].body, originalBody);
  assert.deepEqual(f.pr, before);
  const saved = await f.store.get(e.runId);
  assert.equal(saved.commentIntent, null);
  assert.deepEqual(saved.manualSubmission.publishedResult, original.manualSubmission.publishedResult);
  assert.deepEqual(await f.store.get(100), { envelope: next });
});

for (const race of ['after-outcome', 'after-reservation']) {
  test(`real broker ignores optional admission marker edits ${race} and completes native Ready`, async t => {
    const f = await manualBroker(t, race);
    await f.invoke();
    assert.equal(f.posts(), 1); assert.equal(f.ready(), 1); assert.equal(f.pr.draft, false);
    assert.deepEqual(extractAuthorityRecord(f.comments[0].body), { ...f.result, authority_resolution: f.envelope.request.authority_resolution });
    const durable = await f.store.get(f.envelope.runId);
    assert.equal(durable.outcome.outcomeId, f.comments[0].id);
    if (race === 'after-reservation') {
      assert.equal(f.reservedBeforeChange(), true);
      assert.equal(durable.lifecycleIntent, null);
    }
    await f.invoke();
    assert.equal(f.posts(), 1); assert.equal(f.ready(), 1);
  });
}
