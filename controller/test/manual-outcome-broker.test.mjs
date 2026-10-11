import test from 'node:test';
import assert from 'node:assert/strict';
import { fixture } from './fixture.mjs';
import { createPublicationBroker } from '../src/publication-broker.mjs';
import { CONSUMER } from '../../consumer/consumer.mjs';
import { REPOSITORY, WRITER } from '../src/execution-contract.mjs';
import { admissionBinding, extractAuthorityRecord } from '../../contracts/src/github-authority.mjs';

const charter = 'Authority model: github-native-v1\nIssue closure policy: keep-open\nImplement the admitted repository change through manual Codex; independent acceptance remains required.';
const copy = value => structuredClone(value);

async function manualBroker(t, race) {
  const f = await fixture(t, { issueBody: charter, route: 'manual', labelLaunch: true, streamlinedAdmission: true });
  const e = f.envelope;
  const marker = `Execution admission digest: ${admissionBinding(e.request).sha256}`;
  const pr = { number: 43, node_id: 'PR_manual', state: 'open', merged: false, draft: true,
    body: `Related to #42\n${marker}`, base: { ref: CONSUMER.baseBranch, sha: e.historicalBase, repo: { full_name: REPOSITORY } },
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
  f.api.list = path => path.startsWith('/pulls?') ? Promise.resolve([copy(pr)])
    : path === '/pulls/43/reviews' ? Promise.resolve([]) : originalList(path);
  f.api.userIdentity = login => login === WRITER ? Promise.resolve({ login, type: 'Bot', id: 702 }) : originalIdentity(login);
  f.api.post = async (path, body) => {
    assert.equal(path, '/issues/43/comments');
    posts++;
    const comment = await originalPost(path, body);
    comment.user = { login: WRITER, type: 'Bot', id: 702 };
    f.comments.find(value => value.id === comment.id).user = copy(comment.user);
    if (race === 'after-outcome') removeMarker();
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
  return { ...f, pr, result, invoke, posts: () => posts, ready: () => ready,
    reservedBeforeChange: () => reservedBeforeChange };
}

test('real broker publishes bound manual Git Outcome before a verified native Ready transition', async t => {
  const f = await manualBroker(t);
  const receipt = await f.invoke();
  assert.equal(receipt.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
  assert.equal(f.posts(), 1); assert.equal(f.ready(), 1); assert.equal(f.pr.draft, false);
  assert.deepEqual(extractAuthorityRecord(f.comments[0].body), f.result);
  assert.equal((await f.store.get(f.envelope.runId)).lifecycleIntent, null);
});

for (const race of ['after-outcome', 'after-reservation']) {
  test(`real broker rejects an admission marker removed ${race} without native Ready mutation`, async t => {
    const f = await manualBroker(t, race);
    await assert.rejects(f.invoke(), { code: 'PR_AUTHORITY_CHANGED' });
    assert.equal(f.posts(), 1); assert.equal(f.ready(), 0); assert.equal(f.pr.draft, true);
    assert.deepEqual(extractAuthorityRecord(f.comments[0].body), f.result);
    const durable = await f.store.get(f.envelope.runId);
    assert.equal(durable.outcome.outcomeId, f.comments[0].id);
    if (race === 'after-reservation') {
      assert.equal(f.reservedBeforeChange(), true);
      assert.deepEqual(durable.lifecycleIntent, { number: f.pr.number, head: f.pr.head.sha, draft: false });
    }
    await assert.rejects(f.invoke(), { code: 'PR_AUTHORITY_CHANGED' });
    assert.equal(f.posts(), 1); assert.equal(f.ready(), 0);
  });
}
