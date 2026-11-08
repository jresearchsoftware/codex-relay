import test from 'node:test';
import assert from 'node:assert/strict';
import { fixture } from './fixture.mjs';
import { runAttempt } from '../src/attempt.mjs';
import { extractAuthorityRecord, admissionBinding } from '../../contracts/src/github-authority.mjs';
import { currentStep } from '../src/step-metadata.mjs';

const charter = 'Authority model: github-native-v1\n\nIssue closure policy: keep-open\n\nImplement the repository change; independent acceptance remains required.';
test('ready label admits charter-only work once, allocates Step under Writer reservation and publishes one bound Outcome', async t => {
  let initialLabels;
  const f = await fixture(t, { issueBody: charter, labelLaunch: true, streamlinedAdmission: true,
    beforeAdmission: ({ issue, admissionRequest }) => {
      issue.labels = issue.labels.filter(label => !label.name.startsWith('step-'));
      initialLabels = structuredClone(issue.labels); admissionRequest.step = null;
    } });
  assert.deepEqual(initialLabels.map(label => label.name), ['codex-ready-auto']);
  assert.equal(f.envelope.request.kind, 'admission'); assert.equal(f.envelope.step, 1);
  assert.equal(currentStep(f.issue.labels), 1); assert.equal(f.comments.length, 0);
  const snapshot = (await f.store.get(99)).envelope.request;
  let executions = 0;
  const result = await runAttempt({ ...f, execute: async () => {
    executions++; return { version: 2, attemptId: f.envelope.attemptId, child: 'started', containment: 'reaped',
      result: { status: 'success', summary: 'No source changes were necessary.', validation: ['local validation'] } };
  } });
  assert.equal(result.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW'); assert.equal(f.comments.length, 1);
  const outcome = extractAuthorityRecord(f.comments[0].body);
  assert.equal(outcome.schema_version, '4.0'); assert.deepEqual(outcome.admission, admissionBinding(snapshot));
  assert.equal((await f.broker.invoke(f.admissionRequest)).resumed, true);
  await runAttempt({ ...f, admissionResumed: true, execute: () => { throw new Error('replayed execution'); } });
  assert.equal(executions, 1); assert.equal(f.comments.length, 1);
  assert.deepEqual((await f.store.get(99)).envelope.request, snapshot);
});

test('a new native manual admission preserves a later owner-maintained standalone Step position', async t => {
  const f = await fixture(t, { issueBody: charter, route: 'manual', labelLaunch: true, streamlinedAdmission: true,
    beforeAdmission: async ({ issue, run, store, api }) => {
      issue.labels = [{ name: 'step-900' }, { name: 'codex-ready-manual' }];
      const prior = { version: 2, repository: run.repository.full_name, issueNumber: 42, target: 'issue', number: 42, route: 'manual', step: 4, runId: 98, attemptId: 'run-98' };
      await store.put(98, { envelope: prior, outcome: { status: 'BLOCKED' } });
      // Prior command completion is independently read through the existing run adapter.
      api.getRun = async id => structuredClone(id === 98 ? { ...run, id, status: 'completed', updated_at: '2026-09-04T11:59:00Z' } : run);
    } });
  assert.equal(f.envelope.step, 901); assert.equal(currentStep(f.issue.labels), 901);
  assert.equal(f.envelope.request.lineage.step, 4);
});

test('manual handoff exposes exact public Outcome bindings without a private journal read', async t => {
  const f = await fixture(t, { issueBody: charter, route: 'manual', labelLaunch: true, streamlinedAdmission: true });
  const handoff = await runAttempt({ ...f, execute: () => { throw new Error('manual execution is owner-launched'); } });
  assert.equal(handoff.status, 'handed-off');
  const body = f.comments[0].body;
  const binding = JSON.parse(/^```json\n([\s\S]*?)\n```$/m.exec(body)[1]);
  assert.equal(binding.repository, f.envelope.request.repository);
  assert.equal(binding.task, f.envelope.issueNumber);
  assert.equal(binding.run_id, f.envelope.runId);
  assert.deepEqual(binding.result.authority, f.envelope.request.authority);
  assert.deepEqual(binding.result.admission, admissionBinding(f.envelope.request));
  assert.equal(binding.result.charter_sha256, f.envelope.request.charter_sha256);
  assert.equal(binding.result.attempt, f.envelope.attemptId);
  assert.ok(body.indexOf('Manual Outcome binding:') > body.indexOf('</details>'));
  assert.match(body, /This binding is not an execution result/);
  assert.ok(body.includes(`Admitted branch: ${f.envelope.branch}; base SHA: ${f.envelope.historicalBase}`));
  assert.ok(body.includes(`Required starting head: ${f.envelope.startHead}`));
  assert.ok(body.includes('source PR: none (new source work)'));
  await runAttempt({ ...f, admissionResumed: true });
  assert.equal(f.comments.length, 1);
  assert.equal(f.comments[0].body, body);
});

test('an incomplete stored Git start cannot be published as a ready manual handoff', async t => {
  const f = await fixture(t, { issueBody: charter, route: 'manual', labelLaunch: true, streamlinedAdmission: true });
  const record = await f.store.get(f.envelope.runId);
  record.envelope.historicalBase = null;
  await f.store.put(f.envelope.runId, record);
  await assert.rejects(f.broker.invoke({ operation: 'handoff', runId: f.envelope.runId, attemptId: f.envelope.attemptId }),
    { code: 'EXECUTION_ENVELOPE_INVALID' });
  assert.equal(f.comments.length, 0);
});
