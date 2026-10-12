import test from 'node:test';
import assert from 'node:assert/strict';
import { fixture } from './fixture.mjs';
import { createPublicationBroker } from '../src/publication-broker.mjs';
import { admitEnvelope, revalidateAuthority } from '../src/live-authority.mjs';
import { runAttempt } from '../src/attempt.mjs';
import { dispatchRunName } from '../src/launch-metadata.mjs';
import { projectedRequestTitle } from '../src/step-metadata.mjs';
import { CONSUMER } from '../../consumer/consumer.mjs';
import { REPOSITORY, REVIEWER, WRITER, isAdmissionDomainBlock } from '../src/execution-contract.mjs';
import { admissionBinding, extractAuthorityRecord, canonicalAuthorityJson, nativeReference, sha256Body } from '../../contracts/src/github-authority.mjs';

const charter = 'Authority model: github-native-v1\nIssue closure policy: keep-open\nImplement the current authorized repository work.';
const actor = { login: REVIEWER, id: 701, type: 'Bot' };
const copy = value => structuredClone(value);
const render = value => '```relay-authority\n' + canonicalAuthorityJson(value) + '\n```\n';
const reference = comment => nativeReference({ kind: 'issue-comment', id: comment.id, body: comment.body,
  parent: { kind: 'issue', number: 42 }, repository: REPOSITORY });

function requestSource({ issue, pr, route }, id = 901) {
  const base = pr?.base.sha ?? /Required starting base: `([^`]+)`/.exec(issue.body)?.[1];
  const request = { schema_version: '3.0', kind: 'task-request', repository: REPOSITORY, task: 42,
    parent: { kind: 'issue', number: 42 }, charter_sha256: sha256Body(charter), step: 1, route,
    purpose: 'Old complete Request direction', scope: ['Old Request scope must not be inherited.'],
    model: 'old-request-model', effort: 'high', subagents: false, validation: ['diff-check'],
    boundaries: ['Old Request boundary'], decisions: [], context: [], supersedes: null,
    branch: pr?.head.ref ?? `${CONSUMER.taskBranchPrefix}test-42`, base_sha: base,
    starting_head: base, existing_pr: null, issue_closure_policy: 'keep-open' };
  return { id, user: actor, issue_url: `https://api.github.com/repos/${REPOSITORY}/issues/42`, body: render(request) };
}

function decision(amendments, id = 902, parent = { kind: 'issue', number: 42 }, supersedes = null) {
  return { id, user: actor, issue_url: `https://api.github.com/repos/${REPOSITORY}/issues/${parent.number}`,
    body: render({ schema_version: '4.0', kind: 'decision', repository: REPOSITORY, task: 42,
      parent, charter_sha256: sha256Body(charter), purpose: 'Select current authorized work', amendments, supersedes, context: [] }) };
}

function sources(context, values, { v3Review = false } = {}) {
  const { api, issue, pr, review } = context;
  issue.body = charter;
  const list = api.list.bind(api); const get = api.get.bind(api);
  api.list = async path => path === '/issues/42/comments'
    ? [...values.filter(value => value.issue_url.endsWith('/issues/42')), ...await list(path)]
    : path === '/issues/43/comments' ? [...values.filter(value => value.issue_url.endsWith('/issues/43')), ...await list(path)] : list(path);
  api.get = async path => values.find(value => path === `/issues/comments/${value.id}`) ?? get(path);
  if (v3Review) {
    const original = JSON.parse(/^```relay-authority\n([\s\S]*?)\n```$/m.exec(values[0].body)[1]);
    const request = { ...original, kind: 'change-request', parent: { kind: 'pull_request', number: pr.number },
      step: 2, existing_pr: pr.number, reviewed_head_sha: review.commit_id, change_request_id: 'CR-42-001',
      supersedes: reference(values[0]), findings: [{ id: 'F1', severity: 'major', problem: 'Exact binding is incomplete.',
        impact: 'Work can use stale authority.', remediation: 'Bind exact current authority.', acceptance_criteria: ['Reject changed authority.'] }] };
    review.body = render(request);
    pr.title = projectedRequestTitle(request);
  }
}

async function refuses(t, options = {}, setup = () => {}) {
  let context; let mutations = 0;
  await assert.rejects(fixture(t, { labelLaunch: true, streamlinedAdmission: true, ...options,
    beforeAdmission: async value => {
      context = value;
      await setup(value);
      for (const name of ['post', 'patch', 'delete', 'draft', 'ready', 'ensureStepLabel']) {
        const original = value.api[name].bind(value.api);
        value.api[name] = (...args) => { mutations++; return original(...args); };
      }
    } }), error => error.code === 'CURRENT_PROTOCOL_REQUIRED'
      && /schema 4\.0/.test(error.message) && /qualified installation/.test(error.message) && /do not fall back/.test(error.message));
  assert.equal(await context.store.get(99), null, 'No execution attempt or rejected old-format chain is persisted');
  assert.deepEqual(await context.store.all(), []);
  assert.equal(mutations, 0, 'No Outcome, ready consumption, Step projection or PR transition');
  assert.ok((context.pr ?? context.issue).labels.some(value => value.name === `codex-ready-${options.route ?? 'auto'}`));
  return context;
}

for (const route of ['auto', 'manual']) {
  for (const remediation of [false, true]) {
    test(`current ${route} ${remediation ? 'PR' : 'Issue'} admission refuses missing native marker without publication`, async t => {
      await refuses(t, { route, remediation });
    });
    test(`current ${route} ${remediation ? 'PR' : 'Issue'} admission refuses a fresh v3 execution chain`, async t => {
      await refuses(t, { route, remediation }, context => {
        const source = requestSource({ ...context, route });
        sources(context, [source], { v3Review: remediation });
      });
    });
  }
  test(`direct current ${route} admission cannot downgrade an unmarked Task`, async t => {
    const context = await refuses(t, { route });
    await assert.rejects(admitEnvelope(context.api, context.admissionRequest, { streamlined: true, nextStep: 1 }),
      { code: 'CURRENT_PROTOCOL_REQUIRED' });
    assert.equal(isAdmissionDomainBlock('CURRENT_PROTOCOL_REQUIRED'), false);
    assert.equal(await context.store.get(99), null);
  });
  test(`current ${route} remediation refuses a v3 CR even after explicit Task migration direction`, async t => {
    await refuses(t, { route, remediation: true }, context => {
      const source = requestSource({ ...context, route });
      sources(context, [source, decision({ scope: ['Current exact remediation scope.'] })], { v3Review: true });
    });
  });
}

test('current v4 CR supersedes historical v3 CR for explicitly migrated Task without changing old native bytes', async t => {
  let oldReview;
  const f = await fixture(t, { remediation: true, labelLaunch: true, streamlinedAdmission: true,
    beforeAdmission: context => {
      const source = requestSource({ ...context, route: 'auto' });
      sources(context, [source, decision({ scope: ['Correct current exact finding.'] })], { v3Review: true });
      oldReview = copy(context.review);
      const current = { ...copy(oldReview), id: oldReview.id + 1, body: render({ schema_version: '4.0', kind: 'change-request',
        repository: REPOSITORY, task: 42, parent: { kind: 'pull_request', number: 43 }, charter_sha256: sha256Body(charter),
        purpose: 'Correct current reviewed source', branch: context.pr.head.ref, base_sha: context.pr.base.sha,
        reviewed_head_sha: oldReview.commit_id, change_request_id: 'CR-42-002', context: [],
        findings: [{ id: 'F1', severity: 'major', problem: 'Current source binding is incomplete.', impact: 'Stale publication is possible.',
          remediation: 'Bind exact current head.', acceptance_criteria: ['Reject changed current heads.'] }] }) };
      const list = context.api.list.bind(context.api);
      context.api.list = path => path === '/pulls/43/reviews' ? Promise.resolve([copy(oldReview), copy(current)]) : list(path);
    } });
  assert.equal(f.envelope.request.authority.compatibility_request, null);
  assert.equal(f.envelope.reviewId, oldReview.id + 1);
  assert.deepEqual(f.envelope.profile, CONSUMER.defaultProfile);
  assert.equal((await f.api.list('/pulls/43/reviews'))[0].body, oldReview.body);
  await revalidateAuthority(f.api, f.envelope);
});

test('an explicit current Task Decision admits older work without inheriting any v3 execution fields', async t => {
  let source;
  const f = await fixture(t, { labelLaunch: true, streamlinedAdmission: true,
    beforeAdmission: context => {
      source = requestSource({ ...context, route: 'manual' });
      sources(context, [source, decision({ scope: ['Implement current bounded scope.'] })]);
    } });
  assert.equal(f.envelope.request.schema_version, '4.0');
  assert.equal(f.envelope.request.kind, 'admission');
  assert.equal(f.envelope.step, 1);
  assert.equal(f.envelope.request.authority.compatibility_request, null);
  assert.equal(f.envelope.branch, `${CONSUMER.taskBranchPrefix}task-42`);
  assert.deepEqual(f.envelope.profile, CONSUMER.defaultProfile);
  assert.deepEqual(f.envelope.request.scope, ['Implement current bounded scope.']);
  assert.deepEqual(f.envelope.request.boundaries, []);
  assert.doesNotMatch(f.envelope.input, /Old Request scope must not be inherited/);
  assert.equal((await f.api.get('/issues/comments/901')).body, source.body);
  await revalidateAuthority(f.api, f.envelope);
  const snapshot = copy(f.envelope.request);
  const result = await runAttempt({ ...f, execute: async e => ({ version: 2, attemptId: e.attemptId,
    child: 'started', containment: 'reaped', result: { status: 'success', summary: 'Current work completed.', validation: [] } }) });
  assert.equal(result.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
  assert.equal(extractAuthorityRecord(f.comments[0].body).authority.compatibility_request, null);
  const replay = await f.broker.invoke(f.admissionRequest);
  assert.equal(replay.resumed, true); assert.deepEqual(replay.envelope.request, snapshot);
});

test('migrated manual admission completes and recovers its exact Outcome without reselecting old v3 authority', async t => {
  const f = await fixture(t, { route: 'manual', labelLaunch: true, streamlinedAdmission: true,
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

for (const kind of ['closure-only', 'profile-only', 'older', 'untrusted', 'PR-scoped', 'superseded']) {
  test(`${kind} v4 Decision cannot ambiguously migrate an older v3 Task`, async t => {
    await refuses(t, {}, context => {
      const source = requestSource({ ...context, route: 'auto' });
      let amendment = decision(kind === 'closure-only' ? { issue_closure_policy: 'keep-open' }
        : kind === 'profile-only' ? { model: 'current-model' } : { purpose: 'Current native direction' },
      kind === 'older' ? 900 : 902, kind === 'PR-scoped' ? { kind: 'pull_request', number: 43 } : undefined);
      if (kind === 'untrusted') amendment = { ...amendment, user: { login: 'contributor', id: 9, type: 'User' } };
      const values = [source, amendment];
      if (kind === 'superseded') values.push(decision({ issue_closure_policy: 'keep-open' }, 903, undefined, reference(amendment)));
      sources(context, values);
    });
  });
}

test('duplicate and malformed dedicated native markers cannot fall back or reserve a fresh attempt', async t => {
  for (const body of ['Authority model: github-native-v1\nAuthority model: github-native-v1', 'Authority model: unknown']) {
    let context;
    await assert.rejects(fixture(t, { issueBody: body, labelLaunch: true, streamlinedAdmission: true,
      beforeAdmission: value => { context = value; } }), { code: 'AUTHORITY_MODEL_INVALID' });
    assert.equal(await context.store.get(99), null);
    assert.ok(context.issue.labels.some(value => value.name === 'codex-ready-auto'));
  }
});

test('forked current migration Decisions preserve the specific authority blocker without fabricating old execution', async t => {
  const f = await fixture(t, { labelLaunch: true, streamlinedAdmission: true,
    beforeAdmission: context => {
      const source = requestSource({ ...context, route: 'auto' });
      const first = decision({ scope: ['Current native work'] });
      sources(context, [source, first, decision({ purpose: 'First successor' }, 903, undefined, reference(first)),
        decision({ scope: ['Conflicting successor'] }, 904, undefined, reference(first))]);
    } });
  assert.equal(f.admission.status, 'BLOCKED');
  assert.equal(f.envelope.admissionBlock.code, 'AUTHORITY_DECISION_SUPERSESSION_INVALID');
  assert.equal(f.envelope.step, null);
  assert.equal(f.envelope.branch, null);
  assert.equal(f.envelope.authorityDigest, null);
  assert.equal(f.envelope.request, undefined);
  assert.equal(f.envelope.input, '');
  assert.equal(extractAuthorityRecord(f.comments[0].body), null);
  assert.match(f.comments[0].body, /BLOCKED_BEFORE_WORKER/);
});

for (const typed of [false, true]) {
  for (const route of ['auto', 'manual']) {
    for (const remediation of [false, true]) {
    test(`upgraded Writer preserves exact admitted ${typed ? 'v3' : 'legacy'} ${route} ${remediation ? 'PR' : 'Issue'} while refusing a new attempt`, async t => {
      const f = await fixture(t, { route, remediation, streamlinedAdmission: false,
        beforeAdmission: context => { if (typed) sources(context, [requestSource({ ...context, route })], { v3Review: remediation }); } });
      const original = copy(f.envelope);
      const upgraded = createPublicationBroker({ api: f.api, store: f.store, publisher: f.publisher,
        journal: f.journal, lifecycleStore: f.lifecycleStore, streamlinedAdmission: true });
      const replay = await upgraded.dispatch(f.admissionRequest);
      assert.equal(replay.resumed, true); assert.deepEqual(replay.envelope, original);
      await upgraded.dispatch({ operation: 'preflight', runId: 99, attemptId: original.attemptId });
      const newRequest = { ...f.admissionRequest, runId: 100 };
      f.api.getRun = async id => ({ ...copy(f.run), id, display_title: dispatchRunName(newRequest) });
      await assert.rejects(upgraded.dispatch(newRequest), error => ['CURRENT_PROTOCOL_REQUIRED', 'PRIOR_EXECUTION_UNRESOLVED'].includes(error.code));
      assert.equal(await f.store.get(100), null);
      assert.deepEqual((await f.store.get(99)).envelope, original);
      const changed = { ...f.admissionRequest, step: f.admissionRequest.step + 1 };
      await assert.rejects(upgraded.dispatch(changed), { code: 'RUN_BINDING_CHANGED' });
    });
    }
  }
}
