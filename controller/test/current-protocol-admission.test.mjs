import test from 'node:test';
import assert from 'node:assert/strict';
import { fixture } from './fixture.mjs';
import { createPublicationBroker } from '../src/publication-broker.mjs';
import { admitEnvelope, revalidateAuthority } from '../src/live-authority.mjs';
import { runAttempt } from '../src/attempt.mjs';
import { CONSUMER } from '../../consumer/consumer.mjs';
import { REPOSITORY, REVIEWER, WRITER, isAdmissionDomainBlock } from '../src/execution-contract.mjs';
import { admissionBinding, authoritySourceDigest, extractAuthorityRecord, canonicalAuthorityJson, nativeReference, sha256Body } from '../../contracts/src/github-authority.mjs';

const charter = 'Authority model: github-native-v1\nIssue closure policy: keep-open\nImplement the current authorized repository work.';
const actor = { login: REVIEWER, id: 701, type: 'Bot' };
const copy = value => structuredClone(value);
const render = value => '```relay-authority\n' + canonicalAuthorityJson(value) + '\n```\n';
function requestSource({ route }, id = 901) {
  return { id, user: actor, issue_url: `https://api.github.com/repos/${REPOSITORY}/issues/42`,
    body: render({ schema_version: '3.0', kind: 'task-request', repository: REPOSITORY, task: 42,
      parent: { kind: 'issue', number: 42 }, charter_sha256: sha256Body(charter), step: 8, route,
      scope: ['Old Request scope must not be inherited.'], purpose: 'Old direction', model: 'old-model',
      branch: 'codex/old-branch' }) };
}
function decision(amendments, id = 902, context = []) {
  return { id, user: actor, issue_url: `https://api.github.com/repos/${REPOSITORY}/issues/42`,
    body: render({ schema_version: '4.0', kind: 'decision', repository: REPOSITORY, task: 42,
      parent: { kind: 'issue', number: 42 }, charter_sha256: sha256Body(charter), purpose: 'Select current authorized work',
      amendments, supersedes: null, context }) };
}
function sources({ api }, values) {
  const list = api.list.bind(api); const get = api.get.bind(api);
  api.list = async path => path === '/issues/42/comments' ? [...values, ...await list(path)] : list(path);
  api.get = async path => copy(values.find(value => path === `/issues/comments/${value.id}`)) ?? get(path);
}
async function refuses(t, options = {}, setup = () => {}) {
  let context; let mutations = 0;
  await assert.rejects(fixture(t, { labelLaunch: true, issueBody: charter, ...options,
    beforeAdmission: async value => {
      context = value; await setup(value);
      for (const name of ['post', 'patch', 'delete', 'draft', 'ready', 'ensureStepLabel']) {
        const original = value.api[name].bind(value.api);
        value.api[name] = (...args) => { mutations++; return original(...args); };
      }
    } }), { code: 'CURRENT_PROTOCOL_REQUIRED' });
  assert.equal(await context.store.get(99), null);
  assert.deepEqual(await context.store.all(), []);
  assert.equal(mutations, 0);
  assert.ok((context.pr ?? context.issue).labels.some(value => value.name === `codex-ready-${options.route ?? 'auto'}`));
  return context;
}
for (const route of ['auto', 'manual']) {
  for (const remediation of [false, true]) test(`current ${route} ${remediation ? 'PR' : 'Issue'} rejects unmarked authority before any mutation`, async t => {
    const context = await refuses(t, { route, remediation, issueBody: 'Unmarked old execution prose.\nIssue closure policy: keep-open' });
    await assert.rejects(admitEnvelope(context.api, context.admissionRequest, { nextStep: 1 }), { code: 'CURRENT_PROTOCOL_REQUIRED' });
    assert.equal(isAdmissionDomainBlock('CURRENT_PROTOCOL_REQUIRED'), false);
  });
  test(`current ${route} rejects an old or untyped active CR instead of creating a new old-schema chain`, async t => {
    await refuses(t, { route, remediation: true }, ({ review }) => {
      review.body = render({ schema_version: '3.0', kind: 'change-request', repository: REPOSITORY, task: 42,
        parent: { kind: 'pull_request', number: 43 }, reviewed_head_sha: review.commit_id });
    });
  });
}
test('old native execution text is opaque selected context with exact body hashes and no execution fields', async t => {
  let old;
  const f = await fixture(t, { issueBody: charter, labelLaunch: true, beforeAdmission: value => {
    old = requestSource({ route: 'manual' });
    const reference = nativeReference({ kind: 'issue-comment', id: old.id, parent: { kind: 'issue', number: 42 }, body: old.body });
    sources(value, [old, decision({ scope: ['Current bounded scope'] }, 902, [reference])]);
  } });
  assert.equal(f.envelope.step, 1);
  assert.equal(f.envelope.request.authority.compatibility_request, null);
  assert.equal(f.envelope.branch, `${CONSUMER.taskBranchPrefix}task-42`);
  assert.deepEqual(f.envelope.profile, CONSUMER.defaultProfile);
  assert.deepEqual(f.envelope.request.scope, ['Current bounded scope']);
  assert.ok(f.envelope.input.includes(old.body));
  await revalidateAuthority(f.api, f.envelope);
  const before = copy(f.envelope.request);
  old.body += '<!-- changed native bytes -->';
  await assert.rejects(revalidateAuthority(f.api, f.envelope), { code: 'AUTHORITY_SOURCE_MISMATCH' });
  assert.deepEqual((await f.store.get(99)).envelope.request, before);
});

test('current manual admission completes and recovers its exact Outcome without reselecting old v3 authority', async t => {
  const f = await fixture(t, { issueBody: charter, route: 'manual', labelLaunch: true,
    beforeAdmission: context => {
      const source = requestSource({ ...context, route: 'auto' });
      sources(context, [source, decision({ purpose: 'Current bounded manual qualification', scope: ['Qualify current work.'],
        branch: null, base_sha: null, starting_head: null })]);
    } });
  const originalIdentity = f.api.userIdentity.bind(f.api);
  f.api.userIdentity = login => login === WRITER ? Promise.resolve({ login, id: 702, type: 'Bot' }) : originalIdentity(login);
  const post = f.api.post.bind(f.api); let posts = 0; let loseResponse = false;
  f.api.post = async (path, body) => {
    const comment = await post(path, body); posts++;
    comment.user = { login: WRITER, id: 702, type: 'Bot' };
    f.comments.find(value => value.id === comment.id).user = copy(comment.user);
    if (loseResponse) { loseResponse = false; throw Object.assign(new Error('Lost Outcome response'), { code: 'POST_UNCERTAIN' }); }
    return comment;
  };
  const upgraded = createPublicationBroker({ api: f.api, store: f.store, publisher: f.publisher,
    journal: f.journal, lifecycleStore: f.lifecycleStore, streamlinedAdmission: true, allowManualOutcome: true });
  await runAttempt({ ...f, broker: { invoke: request => upgraded.dispatch(request) } });
  assert.match(f.comments[0].body, /Admitted Git start: none \(source-free manual work\)/);
  const snapshot = copy(f.envelope.request);
  const result = { schema_version: '4.0', kind: 'outcome', repository: REPOSITORY, task: 42,
    parent: { kind: 'issue', number: 42 }, charter_sha256: snapshot.charter_sha256, step: snapshot.step,
    authority: copy(snapshot.authority), admission: admissionBinding(snapshot), attempt: f.envelope.attemptId,
    status: 'implemented', result: { kind: 'qualification', revision: 'qualification-99', identities: [{ kind: 'github-actions-run', id: '99' }] },
    summary: 'Manual current qualification completed.', warnings: [], limitations: [] };
  const request = { operation: 'manual-outcome-direct', runId: 99, attemptId: f.envelope.attemptId,
    submission: { repository: REPOSITORY, task: 42, run_id: 99, result } };
  loseResponse = true;
  await assert.rejects(upgraded.dispatch(request), { code: 'POST_UNCERTAIN' });
  assert.equal((await upgraded.dispatch(request)).status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
  await upgraded.dispatch(request);
  assert.equal(posts, 2, 'One handoff and one immutable Writer Outcome');
  assert.equal(extractAuthorityRecord(f.comments[1].body).authority.compatibility_request, null);
  assert.deepEqual((await f.store.get(99)).envelope.request, snapshot);
});

test('pending v4 manual result preserves an already selected historical Decision and its later current scope replacement', async t => {
  const old = { id: 901, user: copy(actor), issue_url: `https://api.github.com/repos/${REPOSITORY}/issues/42`,
    body: render({ schema_version: '3.0', kind: 'decision', repository: REPOSITORY, task: 42,
      parent: { kind: 'issue', number: 42 }, charter_sha256: sha256Body(charter), purpose: 'Original durable source scope',
      amendments: { scope: ['Original Task goal before the later current Decision.'] }, supersedes: null, context: [] }) };
  const current = decision({ scope: ['Complete the current authorized Task goal.'], branch: null, base_sha: null, starting_head: null });
  const f = await fixture(t, { issueBody: charter, route: 'manual', labelLaunch: true,
    beforeAdmission: value => sources(value, [current]) });
  // Model a protected snapshot that was admitted by the prior producer, whose
  // selected native references must survive completion by the current Writer.
  const record = await f.store.get(99);
  const oldReference = nativeReference({ kind: 'issue-comment', id: old.id, parent: { kind: 'issue', number: 42 }, body: old.body });
  const exactSources = { ...record.envelope.request.authority,
    decisions: [oldReference, ...record.envelope.request.authority.decisions] };
  const authority = { ...exactSources, sha256: authoritySourceDigest(exactSources) };
  record.envelope.request.authority = authority;
  record.envelope.authorityDigest = authority.sha256;
  await f.store.put(99, record);
  const list = f.api.list.bind(f.api);
  f.api.list = async path => path === '/issues/42/comments' ? [old, ...await list(path)] : list(path);
  const identity = f.api.userIdentity.bind(f.api), post = f.api.post.bind(f.api);
  f.api.userIdentity = login => login === WRITER ? Promise.resolve({ login, id: 702, type: 'Bot' }) : identity(login);
  f.api.post = async (path, data) => {
    const value = await post(path, data);
    if (path.endsWith('/comments')) {
      value.user = { login: WRITER, id: 702, type: 'Bot' };
      f.comments.find(item => item.id === value.id).user = copy(value.user);
    }
    return value;
  };
  const e = record.envelope;
  await revalidateAuthority(f.api, e);
  const broker = createPublicationBroker({ api: f.api, store: f.store, publisher: f.publisher,
    journal: f.journal, lifecycleStore: f.lifecycleStore, allowManualOutcome: true });
  const result = { schema_version: '4.0', kind: 'outcome', repository: REPOSITORY, task: 42,
    parent: { kind: 'issue', number: 42 }, charter_sha256: e.request.charter_sha256, step: e.step,
    authority, admission: admissionBinding(e.request), attempt: e.attemptId, status: 'implemented',
    result: { kind: 'qualification', revision: 'bounded-proof', identities: [] },
    summary: 'The complete current Task goal is delivered.', warnings: [], limitations: [] };
  const invoke = () => broker.dispatch({ operation: 'manual-outcome-direct', runId: 99, attemptId: e.attemptId,
    submission: { repository: REPOSITORY, task: 42, run_id: 99, result } });
  const outcome = await invoke();
  assert.equal(outcome.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
  assert.deepEqual(extractAuthorityRecord(f.comments[0].body).authority, authority);
  assert.deepEqual(await invoke(), outcome); assert.equal(f.comments.length, 1);
  assert.deepEqual((await f.store.get(99)).envelope, e);
  old.body += '<!-- changed original native source -->';
  await assert.rejects(invoke(), { code: 'AUTHORITY_SOURCE_MISMATCH' });
  assert.equal(f.comments.length, 1);
});
