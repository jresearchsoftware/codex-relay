import test from 'node:test';
import assert from 'node:assert/strict';
import { writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { fixture, memoryStore } from './fixture.mjs';
import { createPublicationBroker } from '../src/publication-broker.mjs';
import { blockedCrContinuation } from '../src/blocked-cr-continuation.mjs';
import { readTaskAuthority } from '../src/task-authority.mjs';
import { REPOSITORY, REVIEWER, WRITER, digest } from '../src/execution-contract.mjs';
import { CONSUMER } from '../../consumer/consumer.mjs';
import { labelRunName } from '../src/launch-metadata.mjs';
import { admissionBinding, renderAuthorityRecord, sha256Body } from '../../contracts/src/github-authority.mjs';

const copy = value => structuredClone(value);
const charter = 'Authority model: github-native-v1\nIssue closure policy: keep-open\nCorrect the admitted PR finding after the owner resolves the external blocker.';
const reviewer = { login: REVIEWER, id: 701, type: 'Bot' };
const writer = { login: WRITER, id: 702, type: 'Bot' };

async function manualFixture(t, { mainAdvance = false } = {}) {
  const directions = [];
  const f = await fixture(t, { remediation: true, route: 'manual', issueBody: charter, mainAdvance,
    labelLaunch: true, streamlinedAdmission: true,
    beforeAdmission: async ({ api, review, pr, admissionRequest }) => {
      admissionRequest.step = null;
      review.body = renderAuthorityRecord({ schema_version: '4.0', kind: 'change-request', repository: REPOSITORY,
        task: 42, parent: { kind: 'pull_request', number: 43 }, charter_sha256: sha256Body(charter),
        purpose: 'Correct the exact reviewed source', branch: pr.head.ref, base_sha: pr.base.sha,
        reviewed_head_sha: review.commit_id, change_request_id: 'CR-42-001', context: [],
        findings: [{ id: 'F1', severity: 'major', problem: 'The admitted invariant is incomplete.',
          impact: 'Continuation can use stale source.', remediation: 'Bind exact trusted publication.',
          acceptance_criteria: ['Keep the original review source and verify the new starting head.'] }] });
      // Native PR base reflects current main, while CR provenance retains the
      // exact base on which the original review was published.
      if (mainAdvance) pr.base.sha = (await api.get(`/git/ref/heads/${CONSUMER.baseBranch}`)).object.sha;
      api.userIdentity = async login => copy(login === WRITER ? writer : reviewer);
      const get = api.get.bind(api); const list = api.list.bind(api);
      api.get = async path => {
        const selected = directions.find(value => path === `/issues/comments/${value.id}`);
        return selected ? copy(selected) : get(path);
      };
      api.list = async path => path === '/issues/42/comments' ? [...copy(directions), ...await list(path)] : list(path);
    } });
  // Decorate fixture-native comments at GET as well: its list API returns copies.
  const get = f.api.get.bind(f.api); const list = f.api.list.bind(f.api);
  f.api.get = async path => {
    const value = await get(path);
    if (/^\/issues\/comments\/\d+$/.test(path) && value.user?.login === WRITER) return { ...value,
      user: copy(writer), issue_url: `https://api.github.com/repos/${REPOSITORY}/issues/43`,
      created_at: '2026-09-04T12:01:00Z' };
    return value;
  };
  f.api.list = async path => (await list(path)).map(value => value.user?.login === WRITER
    ? { ...value, user: copy(writer), issue_url: `https://api.github.com/repos/${REPOSITORY}/issues/43` } : value);
  const manual = createPublicationBroker({ api: f.api, store: f.store, publisher: f.publisher,
    journal: f.journal, lifecycleStore: f.lifecycleStore, admissionLifecycleStore: memoryStore(), allowManualOutcome: true });
  const broker = { invoke: request => manual.dispatch(request) };
  const runs = new Map([[99, copy(f.run)]]);
  f.api.getRun = async id => copy(runs.get(id));
  let progress = 0;
  await f.command(f.source, mainAdvance ? ['switch', f.envelope.branch]
    : ['switch', '-c', f.envelope.branch, f.envelope.startHead]);
  assert.equal(await f.command(f.source, ['rev-parse', 'HEAD']), f.envelope.startHead);

  async function publishBlocked(envelope, { includeResolution = false } = {}) {
    await writeFile(join(f.source, 'docs/work.md'), `manual source progress ${++progress}\n`);
    await f.command(f.source, ['commit', '-am', `manual progress ${progress}`]);
    await f.command(f.source, ['push', f.remote, envelope.branch]);
    const head = await f.remoteHead();
    f.pr.body += `\nExecution admission digest: ${admissionBinding(envelope.request).sha256}`;
    const result = { schema_version: '4.0', kind: 'outcome', repository: REPOSITORY, task: 42,
      parent: { kind: 'pull_request', number: 43 }, charter_sha256: sha256Body(charter),
      authority: envelope.request.authority, admission: admissionBinding(envelope.request), step: envelope.step,
      ...(includeResolution ? { authority_resolution: envelope.request.authority_resolution } : {}),
      attempt: envelope.attemptId, status: 'blocked', result: { kind: 'git', revision: head,
        identities: [{ kind: 'github-actions-run', id: String(envelope.runId) }] }, warnings: [],
      limitations: ['An owner decision must resolve the external blocker.'], summary: 'Safe manual source progress is published.' };
    const outcome = await manual.dispatch({ operation: 'manual-outcome-direct', runId: envelope.runId,
      attemptId: envelope.attemptId, submission: { repository: REPOSITORY, task: 42, run_id: envelope.runId, result } });
    const record = await f.store.get(envelope.runId);
    assert.equal(outcome.status, 'BLOCKED'); assert.equal(outcome.manual, true);
    assert.equal(record.publishedHead, null); assert.equal(record.outcome.head, head);
    assert.ok(record.manualSubmission.publishedResult);
    return record;
  }
  function resolveBlocker(envelope) {
    directions.push({ id: 900 + envelope.step, user: copy(reviewer),
      issue_url: `https://api.github.com/repos/${REPOSITORY}/issues/42`,
      body: renderAuthorityRecord({ schema_version: '4.0', kind: 'decision', repository: REPOSITORY, task: 42,
        parent: { kind: 'issue', number: 42 }, charter_sha256: sha256Body(charter), purpose: 'Resolve the prior external blocker',
        amendments: { scope: [`The owner resolved the external blocker after Step ${envelope.step}; continue the same finding.`] },
        supersedes: null, context: [] }) });
  }
  async function nextReady(envelope) {
    const runId = envelope.runId + 1;
    const minute = 3 * envelope.step;
    const timestamp = offset => `2026-09-04T12:${String(minute + offset).padStart(2, '0')}:00Z`;
    runs.set(envelope.runId, { ...runs.get(envelope.runId), status: 'completed', updated_at: timestamp(-1) });
    f.events.splice(0, f.events.length, { id: 71 + envelope.step, event: 'labeled',
      actor: { login: CONSUMER.owner, type: 'User' }, label: { name: 'codex-ready-manual' }, created_at: timestamp(0) });
    f.pr.labels.push({ name: 'codex-ready-manual' });
    runs.set(runId, { ...copy(f.run), id: runId, created_at: timestamp(0),
      display_title: labelRunName({ route: 'manual', target: 'pull_request', number: 43 }, f.pr) });
    return broker.invoke({ ...f.admissionRequest, runId, step: null });
  }
  async function helperInput(record) {
    const pr = await f.api.get('/pulls/43');
    const typed = await readTaskAuthority(f.api, f.issue, pr, { streamlined: true, currentProtocol: true, route: 'manual' });
    return { typed, pr, step: record.envelope.step + 1,
      lineage: { attempt: record.envelope.attemptId, step: record.envelope.step, sha256: digest(record.envelope) },
      previousRecord: record, targetBase: record.envelope.targetBase };
  }
  return { ...f, broker, publishBlocked, resolveBlocker, nextReady, helperInput };
}

test('native manual BLOCKED publication admits successive fresh Steps on the same immutable CR without an automatic push receipt', async t => {
  const f = await manualFixture(t);
  const originalReview = copy(f.review);
  const originalLifecycle = await f.lifecycleStore.get(f.review.id);
  let envelope = f.envelope;
  for (let iteration = 0; iteration < 2; iteration++) {
    const record = await f.publishBlocked(envelope);
    const oldRecord = copy(record); const oldComments = copy(f.comments);
    f.resolveBlocker(envelope);
    const admitted = await f.nextReady(envelope);
    assert.notEqual(admitted.status, 'BLOCKED', JSON.stringify(admitted.envelope));
    assert.equal(admitted.envelope.step, envelope.step + 1);
    assert.equal(admitted.envelope.startHead, record.outcome.head);
    assert.equal(admitted.envelope.request.reviewed_head_sha, originalReview.commit_id);
    assert.deepEqual(admitted.envelope.request.authority.change_request, envelope.request.authority.change_request);
    assert.equal(admitted.envelope.request.lineage.sha256, digest(envelope));
    assert.deepEqual(await f.store.get(envelope.runId), oldRecord);
    assert.deepEqual(f.comments, oldComments);
    const replay = await f.broker.invoke({ ...f.admissionRequest, runId: admitted.envelope.runId, step: null });
    assert.equal(replay.resumed, true); assert.deepEqual(replay.envelope, admitted.envelope);
    envelope = admitted.envelope;
  }
  assert.deepEqual(f.review, originalReview);
  assert.deepEqual(await f.lifecycleStore.get(f.review.id), originalLifecycle);
  assert.equal(f.pushes(), 0);
});

test('manual same-CR continuation rejects missing or forged canonical submission and native Writer evidence', async t => {
  const f = await manualFixture(t);
  const record = await f.publishBlocked(f.envelope, { includeResolution: true });
  f.resolveBlocker(f.envelope);
  const input = await f.helperInput(record);
  assert.equal((await blockedCrContinuation(f.api, input)).starting_head, record.outcome.head);
  const retained = copy(record);
  delete retained.manualSubmission.publishedResult;
  assert.equal((await blockedCrContinuation(f.api, { ...input, previousRecord: retained })).starting_head, record.outcome.head);
  for (const mutate of [
    value => { delete value.manualSubmission; },
    value => { value.manualSubmission.sha256 = 'f'.repeat(64); },
    value => { value.manualSubmission.publishedResult.summary = 'Forged submitted result.'; },
    value => { value.outcome.manual = false; },
    value => { value.outcome.bodySha256 = 'f'.repeat(64); }
  ]) {
    const changed = copy(record); mutate(changed);
    await assert.rejects(blockedCrContinuation(f.api, { ...input, previousRecord: changed }),
      { code: 'AUTHORITY_CONTINUATION_INVALID' });
  }
  const identity = f.api.userIdentity;
  f.api.userIdentity = async login => login === WRITER ? { ...writer, id: writer.id + 1 } : identity(login);
  await assert.rejects(blockedCrContinuation(f.api, input), { code: 'AUTHORITY_CONTINUATION_INVALID' });
  assert.deepEqual(await f.store.get(f.envelope.runId), record);
});

test('manual same-CR continuation preserves an unchanged admitted integration base newer than the original CR base', async t => {
  const f = await manualFixture(t, { mainAdvance: true });
  assert.notEqual(f.envelope.historicalBase, f.envelope.targetBase);
  assert.equal(f.pr.base.sha, f.envelope.targetBase);
  const record = await f.publishBlocked(f.envelope);
  f.resolveBlocker(f.envelope);
  const admitted = await f.nextReady(f.envelope);
  assert.notEqual(admitted.status, 'BLOCKED', JSON.stringify(admitted.envelope));
  assert.equal(admitted.envelope.startHead, record.outcome.head);
  assert.equal(admitted.envelope.historicalBase, f.envelope.historicalBase);
  assert.equal(admitted.envelope.targetBase, f.envelope.targetBase);
});
