import test from 'node:test';
import assert from 'node:assert/strict';
import { CONSUMER } from '../../consumer/consumer.mjs';
import { dispatchRunName, launchStep, parseLaunchInputs } from '../src/launch-metadata.mjs';
import { admitEnvelope } from '../src/live-authority.mjs';
import { runAttempt } from '../src/attempt.mjs';
import { executeCodex } from '../src/attempt-runtime.mjs';
import { validateEnvelope } from '../src/execution-contract.mjs';
import { fixture, memoryStore } from './fixture.mjs';

test('native launch inputs preserve explicit Step and bind Task to an Issue number', () => {
  const inputs = { task: '12', step: '2', pull_request: '13', route: 'auto' };
  const launch = parseLaunchInputs(inputs);
  assert.deepEqual(launch, { issueNumber: 12, step: 2, target: 'pull_request', number: 13, route: 'auto' });
  assert.equal(dispatchRunName(launch), 'Auto remediation · Task 12 · Step 2 · PR #13');
  assert.deepEqual(parseLaunchInputs(inputs), launch);
  assert.equal(dispatchRunName(parseLaunchInputs({ ...inputs, pull_request: '' })), 'Auto implementation · Task 12 · Step 2');
  assert.equal(dispatchRunName(parseLaunchInputs({ ...inputs, route: 'manual' })), 'Manual handoff · Task 12 · Step 2 · PR #13');
  assert.ok(dispatchRunName(parseLaunchInputs({ ...inputs, step: String(Number.MAX_SAFE_INTEGER) })).length <= 80);
});

test('missing and unsafe launch metadata cannot be replaced by a Step default', () => {
  for (const value of [undefined, '', '0', '-2', 'Step 2', '02', '2.5', '2e3', '2\n', '2;echo', '9'.repeat(17), ['2'], true]) {
    assert.throws(() => launchStep(value), { code: 'LAUNCH_STEP_INVALID' });
  }
  for (const [field, value, code] of [['task', 'Task 12', 'LAUNCH_TASK_INVALID'],
    ['pull_request', '../13', 'LAUNCH_PR_INVALID'], ['route', 'shell', 'ROUTE_INVALID']]) {
    assert.throws(() => parseLaunchInputs({ task: '12', step: '2', route: 'auto', [field]: value }), { code });
  }
});

test('legacy terminal/non-routing envelopes remain readable while new dispatches require supplied Step', async t => {
  const f = await fixture(t);
  assert.throws(() => validateEnvelope({ ...f.envelope, step: undefined }), { code: 'EXECUTION_ENVELOPE_INVALID' });
  const legacy = { ...f.envelope, attemptId: 'event-7', eventId: 7, step: undefined };
  assert.equal(validateEnvelope(legacy), legacy);
  assert.throws(() => validateEnvelope({ ...legacy, attemptId: 'event-8' }), { code: 'EXECUTION_ENVELOPE_INVALID' });
});

test('a new Issue with no paths, base, branch or profile publishes task-required repository files on its default branch', async t => {
  const f = await fixture(t, { step: 12, issueBody: '# Implement the admitted goal\nIssue closure policy: keep-open' });
  assert.equal(f.envelope.branch, 'codex/task-42');
  assert.equal(f.envelope.startHead, f.envelope.targetBase);
  assert.deepEqual(f.envelope.profile, CONSUMER.defaultProfile);
  assert.ok(!f.envelope.warnings.some(w => ['branch', 'accepted starting base', 'closure'].includes(w.field)));
  const result = await runAttempt({ ...f, journal: memoryStore(), execute: async () => {
    await f.commit('unanticipated-required-file.mjs', '// required by the admitted goal\n');
    return { version: 2, attemptId: f.envelope.attemptId, child: 'started', containment: 'reaped',
      result: { status: 'success', summary: 'Task-required repository change completed.', validation: ['local check passed'] } };
  } });
  assert.equal(result.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
  assert.equal(f.pushes(), 1);
  assert.match((await f.api.get('/pulls/43')).body, /Related to #42/);
  assert.equal(await f.command(f.root, ['--git-dir=' + f.remote, 'rev-parse', 'main']), f.envelope.startHead);
});

test('native dispatch binds owner, workflow, main, target, phase, Task and Step before admission', async t => {
  const f = await fixture(t);
  for (const delta of [{ actor: { login: 'other' } }, { triggering_actor: { login: 'other' } },
    { repository: { full_name: 'other/repo' } }, { event: 'issues' }, { head_branch: 'codex/untrusted' },
    { path: '.github/workflows/other.yml' }, { run_attempt: 2 }, { status: 'completed' },
    { display_title: 'Auto implementation · Task 42 · Step 99' }]) {
    const api = { ...f.api, getRun: async () => ({ ...f.run, ...delta }) };
    await assert.rejects(admitEnvelope(api, f.admissionRequest), { code: 'OWNER_RUN_NOT_ADMITTED' });
  }
  for (const delta of [{ step: 3 }, { issueNumber: 43, number: 43 }, { route: 'manual' },
    { target: 'pull_request', number: 43 }]) {
    await assert.rejects(admitEnvelope(f.api, { ...f.admissionRequest, ...delta }), { code: 'OWNER_RUN_NOT_ADMITTED' });
    await assert.rejects(f.broker.invoke({ ...f.admissionRequest, ...delta }), { code: 'RUN_BINDING_CHANGED' });
  }
});

test('fresh owner dispatch retries keep Step; explicit continuation changes current metadata and CR without history lookup', async t => {
  const f = await fixture(t, { remediation: true, step: 5 });
  for (const [runId, step] of [[100, 5], [101, 23], [102, 2]]) {
    const request = { ...f.admissionRequest, runId, step };
    f.issue.labels = f.pr.labels = [{ name: `step-${step}` }];
    f.review.body = f.review.body.replace(/Step [0-9]+/, `Step ${step}`);
    Object.assign(f.run, { id: runId, display_title: dispatchRunName(request) });
    const { envelope } = await f.broker.invoke(request);
    assert.equal(envelope.step, step);
    assert.equal(envelope.attemptId, `run-${runId}`);
    assert.match(envelope.thread, new RegExp(`^Task 42 — Step ${step} — CR-42-001 core$`));
  }
  assert.equal(f.comments.length, 0);
});

test('both worker operations receive supplied launch metadata despite historical Markdown titles', async t => {
  for (const remediation of [false, true]) {
    const f = await fixture(t, { remediation, step: 42 });
    let request;
    await executeCodex(f.envelope, { runTask: async value => { request = value; return { status: 'success' }; } });
    assert.ok(request.inputText.startsWith(f.envelope.input)); // Canonical goal remains intact.
    assert.ok(request.inputText.includes(`Task: #42\nStep: 42\nThread name: ${f.envelope.thread}`));
    assert.equal(request.taskTitle, f.envelope.thread);
    assert.match(request.inputText, /Subagents: Off/);
    assert.match(request.inputText, /Do not push, publish, merge PRs, close Issues/);
    assert.equal(request.inputText.includes('Bounded base-branch reconciliation:'), remediation);
  }
});

test('remediation run uses linked Issue identity and supplied Step in PR metadata before publication', async t => {
  const f = await fixture(t, { remediation: true, step: 42 });
  let title;
  await runAttempt({ ...f, journal: memoryStore(), execute: async () => {
    title = (await f.api.get('/pulls/43')).title;
    await f.commit('needed-at-repository-root.md', 'task-required file\n');
    return { version: 2, attemptId: f.envelope.attemptId, child: 'started', containment: 'reaped',
      result: { status: 'success', summary: 'Completed admitted remediation.', validation: ['local checks passed'] } };
  } });
  assert.equal(title, 'Task 42 · Step 42 · CR-42-001 core');
  assert.equal(f.pushes(), 1);
  assert.equal(f.comments.filter(c => c.body.startsWith('## Codex Outcome')).length, 1);
});
