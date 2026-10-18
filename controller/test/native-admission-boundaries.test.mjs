import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, writeFile, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { promisify } from 'node:util';
import { execFile } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { fixture, memoryStore } from './fixture.mjs';
import { createAdmissionControl } from '../src/admission-control.mjs';
import { createPublicationBroker } from '../src/publication-broker.mjs';
import { runAttempt } from '../src/attempt.mjs';
import { revalidateAuthority } from '../src/live-authority.mjs';
import { beginRemediation } from '../src/pr-lifecycle.mjs';
import { validateEnvelope, REPOSITORY, REVIEWER } from '../src/execution-contract.mjs';
import { CONSUMER, CONSUMER_DIGEST } from '../../consumer/consumer.mjs';
import { extractAuthorityRecord, canonicalAuthorityJson, nativeReference, sha256Body } from '../../contracts/src/github-authority.mjs';

const exec = promisify(execFile);
const charter = 'Authority model: github-native-v1\n\nIssue closure policy: keep-open\n\nImplement the repository change within existing protected boundaries.';
const actor = { login: REVIEWER, id: 701, type: 'Bot' };
const copy = value => structuredClone(value);
const render = value => '```relay-authority\n' + canonicalAuthorityJson(value) + '\n```\n';
const common = kind => ({ schema_version: '4.0', kind, repository: REPOSITORY, task: 42,
  parent: { kind: 'issue', number: 42 }, charter_sha256: sha256Body(charter) });
const decision = (amendments, id = 901) => ({ id, user: actor,
  issue_url: `https://api.github.com/repos/${REPOSITORY}/issues/42`,
  body: render({ ...common('decision'), purpose: 'Apply the explicit owner direction', amendments, supersedes: null, context: [] }) });
async function admissionControl({ root, store, journal }) {
  const control = createAdmissionControl({ root, consumerDigest: CONSUMER_DIGEST, store, journal, protectedRoot: false });
  await control.initialize(); return control;
}
function nextReady(f, runId = 100) {
  const previous = { ...copy(f.run), id: 99, status: 'completed', updated_at: '2026-09-04T12:02:00Z' };
  const next = { ...copy(f.run), id: runId, status: 'in_progress', created_at: '2026-09-04T12:03:01Z' };
  f.api.getRun = async id => copy(id === 99 ? previous : next);
  f.events.splice(0, f.events.length, { id: 72, event: 'labeled', actor: { login: CONSUMER.owner, type: 'User' },
    label: { name: 'codex-ready-auto' }, created_at: '2026-09-04T12:03:00Z' });
  f.issue.labels = [{ name: 'step-900' }, { name: 'codex-ready-auto' }];
  return { ...f.admissionRequest, runId, step: null };
}

test('a contained BLOCKED attempt admits a fresh Step while its exact replay retains the original snapshot', async t => {
  const f = await fixture(t, { issueBody: charter, labelLaunch: true, streamlinedAdmission: true, createAdmission: admissionControl });
  const original = copy(f.envelope);
  let calls = 0;
  const result = await runAttempt({ ...f, execute: async e => {
    calls++; return { version: 2, attemptId: e.attemptId, child: 'started', containment: 'reaped',
      result: { status: 'blocked', summary: 'A bounded owner decision remains.', validation: [], blockedReason: 'No unsafe continuation.' } };
  } });
  assert.equal(result.status, 'BLOCKED');
  await f.admissionControl.complete({ runId: 99, attemptId: original.attemptId });
  const replay = await f.broker.invoke(f.admissionRequest);
  assert.equal(replay.resumed, true); assert.deepEqual(replay.envelope, original);
  assert.deepEqual(await runAttempt({ ...f, admissionResumed: true, execute: () => assert.fail('BLOCKED replay executed') }), result);
  const admitted = await f.broker.invoke(nextReady(f));
  assert.equal(admitted.envelope.step, 2);
  assert.equal(admitted.envelope.request.lineage.step, 1);
  assert.equal(admitted.envelope.request.lineage.attempt, original.attemptId);
  assert.equal(calls, 1); assert.deepEqual((await f.store.get(99)).envelope, original);
});

test('a public BLOCKED Outcome cannot authorize a new execution when prior containment remains unknown', async t => {
  const f = await fixture(t, { issueBody: charter, labelLaunch: true, streamlinedAdmission: true, createAdmission: admissionControl });
  await assert.rejects(runAttempt({ ...f, execute: async () => {
    throw Object.assign(new Error('Synthetic unknown execution'), { code: 'EXECUTION_FAILED',
      details: { childState: 'unknown', containment: 'unknown' } });
  } }));
  assert.equal((await f.store.get(99)).outcome.status, 'BLOCKED');
  await assert.rejects(f.broker.invoke(nextReady(f)), { code: 'EXECUTION_SLOT_UNAVAILABLE' });
  assert.equal(await f.store.get(100), null);
});

test('a fresh native Step continues exact Writer-published progress from a contained BLOCKED attempt', async t => {
  const f = await fixture(t, { issueBody: charter, labelLaunch: true, streamlinedAdmission: true, createAdmission: admissionControl });
  const list = f.api.list.bind(f.api);
  f.api.list = async path => path === '/pulls/43/reviews' ? [] : list(path);
  const original = copy(f.envelope);
  const result = await runAttempt({ ...f, execute: async e => {
    await f.commit();
    return { version: 2, attemptId: e.attemptId, child: 'started', containment: 'reaped',
      result: { status: 'blocked', summary: 'Safe progress is retained; one owner decision remains.',
        validation: [], blockedReason: 'Do not proceed before the next authorized execution.' } };
  } });
  assert.equal(result.status, 'BLOCKED');
  await f.admissionControl.complete({ runId: 99, attemptId: original.attemptId });
  const prior = await f.store.get(99);
  assert.equal(prior.publishedHead, await f.remoteHead());
  assert.equal(prior.outcome.head, prior.publishedHead);
  assert.equal(prior.outcome.prNumber, 43);
  const admitted = await f.broker.invoke(nextReady(f));
  assert.notEqual(admitted.status, 'BLOCKED', JSON.stringify(admitted.envelope));
  assert.equal(admitted.envelope.step, 2);
  assert.equal(admitted.envelope.branch, original.branch);
  assert.equal(admitted.envelope.startHead, prior.publishedHead);
  assert.deepEqual(admitted.envelope.continuation, { head: prior.publishedHead, pullRequest: 43 });
  assert.deepEqual((await f.store.get(99)).envelope, original);
});

test('new trusted Decision starting-head authority takes precedence over implicit retained branch progress', async t => {
  const f = await fixture(t, { issueBody: charter, labelLaunch: true, streamlinedAdmission: true, createAdmission: admissionControl });
  const list = f.api.list.bind(f.api);
  let amend;
  f.api.list = async path => path === '/pulls/43/reviews' ? [] : path === '/issues/42/comments' && amend
    ? [amend, ...await list(path)] : list(path);
  await runAttempt({ ...f, execute: async e => {
    await f.commit();
    return { version: 2, attemptId: e.attemptId, child: 'started', containment: 'reaped',
      result: { status: 'blocked', summary: 'Progress is retained before new owner direction.', validation: [],
        blockedReason: 'The owner resolves the next execution state.' } };
  } });
  await f.admissionControl.complete({ runId: 99, attemptId: f.envelope.attemptId });
  amend = decision({ starting_head: 'f'.repeat(40) });
  const admitted = await f.broker.invoke(nextReady(f));
  assert.equal(admitted.status, 'BLOCKED');
  assert.equal(admitted.envelope.step, null);
  assert.equal(admitted.envelope.admissionBlock.code, 'STARTING_STATE_MISMATCH');
  assert.equal((await f.store.get(99)).envelope.step, 1);
});

test('a new profile Decision preserves exact contained Writer branch continuation', async t => {
  const f = await fixture(t, { issueBody: charter, labelLaunch: true, streamlinedAdmission: true, createAdmission: admissionControl });
  const list = f.api.list.bind(f.api); let amend;
  f.api.list = async path => path === '/pulls/43/reviews' ? [] : path === '/issues/42/comments' && amend
    ? [amend, ...await list(path)] : list(path);
  await runAttempt({ ...f, execute: async e => {
    await f.commit();
    return { version: 2, attemptId: e.attemptId, child: 'started', containment: 'reaped',
      result: { status: 'blocked', summary: 'Progress is retained before the next profile decision.', validation: [],
        blockedReason: 'The owner chooses the next execution profile.' } };
  } });
  await f.admissionControl.complete({ runId: 99, attemptId: f.envelope.attemptId });
  const prior = await f.store.get(99);
  amend = decision({ model: 'owner-new-model', effort: 'max', subagents: false });
  const admitted = await f.broker.invoke(nextReady(f));
  assert.notEqual(admitted.status, 'BLOCKED');
  assert.equal(admitted.envelope.step, 2);
  assert.equal(admitted.envelope.startHead, prior.publishedHead);
  assert.deepEqual(admitted.envelope.profile, { cliModelId: 'owner-new-model', effort: 'max' });
  assert.equal(admitted.envelope.subagentsAllowed, false);
  assert.notEqual(admitted.envelope.authorityDigest, f.envelope.authorityDigest);
});

test('rejected native admission has no Step in its protected record, labels or public Outcome', async t => {
  const f = await fixture(t, { issueBody: charter, labelLaunch: true, streamlinedAdmission: true,
    beforeAdmission: ({ api, issue, admissionRequest }) => {
      issue.labels = [{ name: 'codex-ready-auto' }]; admissionRequest.step = null;
      const amend = decision({ branch: 'codex/wrong-start', base_sha: 'f'.repeat(40), starting_head: 'f'.repeat(40) });
      const list = api.list.bind(api);
      api.list = async path => path === '/issues/42/comments' ? [amend, ...await list(path)] : list(path);
    } });
  assert.equal(f.admission.status, 'BLOCKED');
  assert.equal(f.envelope.step, null);
  assert.equal(f.issue.labels.some(label => /^step-/.test(label.name)), false);
  assert.doesNotMatch(f.comments[0].body, /Step\s*:?\s*1\b/);
  assert.equal((await f.store.get(99)).admissionBlock.code, 'STARTING_STATE_MISMATCH');
});

test('native execution snapshot and envelope reject disagreement on exact source, run or attempt identity', async t => {
  const f = await fixture(t, { issueBody: charter, labelLaunch: true, streamlinedAdmission: true });
  for (const changed of [
    { ...f.envelope, authorityDigest: 'f'.repeat(64) },
    { ...f.envelope, requestReference: { ...f.envelope.requestReference, id: 9999 } },
    { ...f.envelope, request: { ...f.envelope.request, attempt: 'run-100' } },
    { ...f.envelope, request: { ...f.envelope.request, run_id: '100' } }
  ]) assert.throws(() => validateEnvelope(changed), { code: 'EXECUTION_ENVELOPE_INVALID' });
});

test('trusted Decision profile and exact CR override resolve without preallocating a review Step', async t => {
  let amend;
  const f = await fixture(t, { remediation: true, issueBody: charter, labelLaunch: true, streamlinedAdmission: true,
    beforeAdmission: ({ api, issue, pr, review, admissionRequest }) => {
      issue.labels = []; pr.labels = [{ name: 'codex-ready-auto' }]; admissionRequest.step = null;
      amend = decision({ model: 'decision-model', effort: 'max', subagents: true, issue_closure_policy: 'close-authorized' });
      review.body = render({ ...common('change-request'), parent: { kind: 'pull_request', number: 43 },
        purpose: 'Correct the exact reviewed source', branch: pr.head.ref, base_sha: pr.base.sha, reviewed_head_sha: review.commit_id,
        change_request_id: 'CR-42-001', context: [], overrides: { effort: 'ultra', subagents: false },
        findings: [{ id: 'F1', severity: 'major', problem: 'The source binding is incomplete.', impact: 'A stale head can be used.',
          remediation: 'Bind the exact source.', acceptance_criteria: ['Reject a changed head.'] }] });
      const list = api.list.bind(api);
      api.list = async path => path === '/issues/42/comments' ? [amend] : list(path);
    } });
  assert.equal(f.envelope.request.step, 1);
  assert.deepEqual(f.envelope.profile, { cliModelId: 'decision-model', effort: 'ultra' });
  assert.equal(f.envelope.subagentsAllowed, false);
  assert.equal(f.envelope.request.issue_closure_policy, 'close-authorized');
  assert.equal(f.envelope.request.authority.change_request.id, f.review.id);
  assert.equal(Object.hasOwn(extractAuthorityRecord(f.review.body), 'step'), false);
  amend.body += '<!-- edited authority bytes -->';
  await assert.rejects(revalidateAuthority(f.api, f.envelope), { code: 'AUTHORITY_SOURCE_MISMATCH' });
});

test('standalone v4 CR Draft transition reserves exact authority without allocating an admission or Step', async t => {
  const lifecycle = memoryStore(); let mutations = 0;
  const f = await fixture(t, { remediation: true, issueBody: charter, labelLaunch: true, streamlinedAdmission: true,
    beforeAdmission: async ({ api, issue, pr, review, store, admissionRequest }) => {
      issue.labels = []; pr.labels = [{ name: 'codex-ready-auto' }]; admissionRequest.step = null;
      review.body = render({ ...common('change-request'), parent: { kind: 'pull_request', number: 43 },
        purpose: 'Correct the exact reviewed source', branch: pr.head.ref, base_sha: pr.base.sha,
        reviewed_head_sha: review.commit_id, change_request_id: 'CR-42-001', context: [],
        findings: [{ id: 'F1', severity: 'major', problem: 'The source binding is incomplete.', impact: 'A stale head can be used.',
          remediation: 'Bind the exact source.', acceptance_criteria: ['Reject a changed head.'] }] });
      const draft = api.draft;
      api.draft = async id => { mutations++; await draft(id); };
      const request = { operation: 'begin-remediation', prNumber: 43, reviewId: review.id, head: review.commit_id };
      assert.equal((await beginRemediation({ api, store: lifecycle, request })).draft, true);
      assert.equal((await beginRemediation({ api, store: lifecycle, request })).draft, true);
      assert.equal(mutations, 1);
      assert.deepEqual(await store.all(), []);
      assert.deepEqual(issue.labels, []);
      assert.deepEqual(pr.labels, [{ name: 'codex-ready-auto' }]);
      assert.equal(Object.hasOwn((await lifecycle.get(review.id)).binding, 'step'), false);
      await assert.rejects(beginRemediation({ api, store: lifecycle, request: { ...request, reviewId: review.id + 1 } }),
        { code: 'CURRENT_CHANGE_REQUEST_MISSING' });
      await assert.rejects(beginRemediation({ api, store: lifecycle, request: { ...request, head: 'f'.repeat(40) } }),
        { code: 'CURRENT_CHANGE_REQUEST_MISSING' });
      const originalBody = review.body;
      review.body = render({ ...extractAuthorityRecord(review.body), branch: 'codex/wrong-current' });
      await assert.rejects(beginRemediation({ api, store: memoryStore(), request }), { code: 'STARTING_STATE_MISMATCH' });
      review.body = originalBody;
      assert.equal(mutations, 1);
    } });
  assert.equal(f.envelope.step, 1);
  assert.equal(mutations, 1);
});

test('retained v3 admission replays under upgraded broker without adopting new Decisions or a new Step', async t => {
  let source;
  const f = await fixture(t, { labelLaunch: true, streamlinedAdmission: false,
    beforeAdmission: ({ api, issue }) => {
      const base = /Required starting base: `([^`]+)`/.exec(issue.body)[1];
      issue.body = charter;
      source = { id: 901, user: actor, issue_url: `https://api.github.com/repos/${REPOSITORY}/issues/42`,
        body: render({ ...common('task-request'), schema_version: '3.0', step: 1, route: 'auto', purpose: 'Original admitted implementation',
          scope: ['Original authorized scope'], model: 'original-model', effort: 'high', subagents: false,
          validation: ['diff-check'], boundaries: ['No production'], decisions: [], context: [], supersedes: null,
          branch: `${CONSUMER.taskBranchPrefix}test-42`, base_sha: base, starting_head: base, existing_pr: null, issue_closure_policy: 'keep-open' }) };
      const list = api.list.bind(api);
      api.list = async path => path === '/issues/42/comments' ? [source, ...await list(path)] : list(path);
    } });
  let calls = 0;
  const result = await runAttempt({ ...f, execute: async e => { calls++; return { version: 2, attemptId: e.attemptId,
    child: 'started', containment: 'reaped', result: { status: 'success', summary: 'Original no-change result.', validation: [] } }; } });
  const original = copy((await f.store.get(99)).envelope);
  const list = f.api.list.bind(f.api);
  f.api.list = async path => path === '/issues/42/comments' ? [decision({ model: 'new-model' }, 902), ...await list(path)] : list(path);
  const upgraded = createPublicationBroker({ api: f.api, store: f.store, publisher: f.publisher, journal: f.journal,
    lifecycleStore: f.lifecycleStore, streamlinedAdmission: true });
  const replay = await upgraded.dispatch(f.admissionRequest);
  assert.equal(replay.resumed, true); assert.deepEqual(replay.envelope, original);
  assert.equal(replay.envelope.request.schema_version, '3.0');
  assert.deepEqual(await runAttempt({ ...f, broker: { invoke: request => upgraded.dispatch(request) }, admissionResumed: true,
    execute: () => assert.fail('historical replay executed') }), result);
  assert.equal(calls, 1);
});

test('concurrent delivery of one native command serializes through OS flock and admits it once', async t => {
  assert.equal(process.platform, 'linux', 'This concurrency proof requires Linux flock.');
  const root = await mkdtemp(join(tmpdir(), 'relay-native-admission-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const subject = { id: 1000, number: 42, state: 'open', user: { login: CONSUMER.owner }, body: charter,
    labels: [{ name: 'codex-ready-auto' }] };
  await writeFile(join(root, 'subject.json'), JSON.stringify(subject), { mode: 0o600 });
  const moduleSource = `
    import {readFile,writeFile} from 'node:fs/promises';
    import {join} from 'node:path';
    import {CONSUMER} from './consumer/consumer.mjs';
    import {createPublicationBroker} from './controller/src/publication-broker.mjs';
    import {createAttemptStore} from './controller/src/attempt-store.mjs';
    import {labelRunName} from './controller/src/launch-metadata.mjs';
    import {WRITER} from './controller/src/execution-contract.mjs';
    const root=process.env.TEST_FIXTURE_ROOT;const runId=Number(process.env.TEST_RUN_ID);
    const repository=CONSUMER.repository;const subjectPath=join(root,'subject.json');
    const read=async()=>JSON.parse(await readFile(subjectPath,'utf8'));
    const write=async value=>writeFile(subjectPath,JSON.stringify(value),{mode:0o600});
    const events=[{id:71,event:'labeled',actor:{login:CONSUMER.owner,type:'User'},
      label:{name:'codex-ready-auto'},created_at:'2026-09-04T12:00:00Z'}];
    const api={getRun:async id=>({id,repository:{full_name:repository},actor:{login:CONSUMER.owner},status:'in_progress',
      event:'issues',head_branch:CONSUMER.baseBranch,display_title:labelRunName({route:'auto',target:'issue',number:42},
        {body:'Authority model: github-native-v1',labels:[{name:'codex-ready-auto'}]}),path:CONSUMER.routingWorkflow,run_attempt:1,
      created_at:'2026-09-04T12:00:01Z'}),userIdentity:async login=>({login,id:701,type:'Bot'}),
      get:async path=>path==='/issues/42'?read():path.startsWith('/git/ref/heads/')?{object:{sha:'a'.repeat(40)}}
        :path.startsWith('/git/matching-refs/heads/')?[]:Promise.reject(new Error('Unexpected GET '+path)),
      list:async path=>path.endsWith('/events')?events:[],ensureStepLabel:async()=>{},
      post:async(path,data)=>{const subject=await read();subject.labels.push(...data.labels.map(name=>({name})));await write(subject);return subject.labels;},
      patch:async(path,data)=>{const subject=await read();subject.labels=data.labels.map(name=>({name}));await write(subject);return subject;},
      delete:async()=>{const subject=await read();subject.labels=subject.labels.filter(label=>label.name!=='codex-ready-auto');await write(subject);
        events.push({id:72,event:'unlabeled',actor:{login:WRITER,type:'Bot'},label:{name:'codex-ready-auto'},created_at:'2026-09-04T12:00:01Z'});}};
    try { const receipt=await createPublicationBroker({api,store:createAttemptStore(join(root,'attempts')),publisher:{},streamlinedAdmission:true})
      .dispatch({operation:'admit',runId,target:'issue',number:42,issueNumber:42,route:'auto',transport:'label',step:null});
      process.stdout.write(JSON.stringify({step:receipt.envelope.step})+'\\n'); }
    catch(error){process.stdout.write(JSON.stringify({code:error.code??'UNEXPECTED'})+'\\n');}
  `;
  const run = async runId => JSON.parse((await exec('/usr/bin/flock', ['-w', '10', join(root, 'publication-v2.lock'),
    process.execPath, '--import', './consumer/test-support/consumer-env.mjs', '--input-type=module', '-e', moduleSource],
  { cwd: fileURLToPath(new URL('../../', import.meta.url)), env: { ...process.env, TEST_FIXTURE_ROOT: root, TEST_RUN_ID: String(runId) } })).stdout.trim());
  const results = await Promise.all([run(100), run(101)]);
  assert.deepEqual(results.filter(result => result.step), [{ step: 1 }], JSON.stringify(results));
  assert.deepEqual(results.filter(result => result.code), [{ code: 'READY_LABEL_AMBIGUOUS' }]);
  const labels = JSON.parse(await readFile(join(root, 'subject.json'), 'utf8')).labels;
  assert.deepEqual(labels, [{ name: 'step-1' }]);
});
