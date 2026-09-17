import test from 'node:test';
import assert from 'node:assert/strict';
import { access, readFile } from 'node:fs/promises';
import { fixture } from './fixture.mjs';
import { runAttempt } from '../src/attempt.mjs';
import { createAttemptStore } from '../src/attempt-store.mjs';
import { createOnDemandDispatchAdapter } from '../src/github.mjs';
import { threadCorrelationIdentity } from '../src/run-name.mjs';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

const exec = promisify(execFile);

const escapeRegex = value => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

// Executed only after installation in the disposable Linux namespace. All
// runtime imports resolve inside the staged release, including the fixture's
// real admission/publication core. GitHub transport is a local fake; Git is real.
assert.equal(process.getuid(), Number(process.env.INSTALLED_RUNNER_UID ?? 24001));
const attemptStore = f => createAttemptStore(process.getuid() === 24003
  ? `/var/lib/codex-relay/dispatch/attempts-v2/${f.envelope.attemptId}` : `${f.root}/journal`);

test('installed dedicated Rust development qualification', async t => {
  const f = await fixture(t, { installed: true, remediation: true,
    instruction: 'fixture-mode=rust-development; Маркер UTF-8' });
  await f.prepare(f.envelope);
  const dispatch = () => createOnDemandDispatchAdapter().dispatch(f.envelope);
  if (process.env.INSTALLED_RUST_LINKER === 'missing') {
    await assert.rejects(dispatch(), error => {
      assert.equal(error.code, 'CODEX_NONZERO_EXIT');
      assert.equal(error.details.childState, 'started');
      assert.equal(error.details.containment, 'reaped');
      return true;
    });
    // The root proof verifies the stored, redacted Cargo cause for this run.
  } else {
    assert.equal(process.env.INSTALLED_RUST_LINKER, 'ready');
    const result = await dispatch();
    assert.equal(result.child, 'started');
    assert.equal(result.containment, 'reaped');
    assert.equal(result.result.status, 'success');
    assert.equal(result.result.summary, 'managed-rust-development-qualified');
    assert.deepEqual(result.result.validation, ['MANAGED_RUST_DEVELOPMENT_PROOF_PASS']);
    console.log('MANAGED_RUST_DEVELOPMENT_PROOF_PASS uid=24002;exact-tools;task-local-cargo-home;protected-roots-denied;locked-offline-test');
  }
  assert.equal(f.pushes(), 0);
  assert.equal(f.comments.length, 0);
});

async function withoutCheckout(f, journal, args) {
  await f.removeCheckout();
  await assert.rejects(access(f.cwd), { code: 'ENOENT' });
  const forbidden = boundary => () => assert.fail(`terminal replay invoked ${boundary}`);
  return { ...args, admissionResumed: true,
    journal: { get: journal.get, put: forbidden('journal mutation') },
    prepare: forbidden('prepare'), execute: forbidden('execute'), collect: forbidden('collect'),
    broker: { invoke: forbidden('broker') } };
}

const explicitProfiles = [
  ['gpt-5.6-luna', 'high'], ['gpt-5.6-terra', 'high'], ['gpt-5.6-sol', 'high'],
  ...['low', 'medium', 'high', 'xhigh', 'max', 'ultra'].map(effort => ['gpt-6-astra', effort]),
  ['future-model', 'future-effort'], ['gpt-5.6-luna', 'ultra'],
];
for (const remediation of [false, true]) for (const [cliModelId, effort] of explicitProfiles) {
  test(`installed ${remediation ? 'CR remediation' : 'Issue'} ${cliModelId}/${effort} reaches durable publication and review stop once`, async t => {
    // The child is a deterministic fixture; no model or subagent runs.
    const f = await fixture(t, { remediation, installed: true, profile: { cliModelId, effort },
      instruction: `fixture-mode=success; fixture-profile=${cliModelId}/${effort}; Маркер UTF-8` });
    assert.deepEqual(f.envelope.profile, { cliModelId, effort });
    const journal = attemptStore(f);
    const dispatcher = createOnDemandDispatchAdapter(); let calls = 0;
    const args = { ...f, journal, execute: e => { calls++; return dispatcher.dispatch(e); } };
    const result = await runAttempt(args);
    assert.equal(result.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
    const saved = await journal.get(f.envelope.runId);
    assert.equal(saved.execution.child, 'started'); assert.equal(saved.execution.containment, 'reaped');
    assert.equal(saved.progress.head, await f.remoteHead()); assert.notEqual(saved.progress.head, f.envelope.startHead);
    const artifact = JSON.parse(await readFile(`${f.cwd}/docs/work.md`, 'utf8'));
    assert.equal(artifact.uid, 24002); assert.equal(artifact.input, true); assert.equal(artifact.umask, 7);
    assert.equal(artifact.model, cliModelId); assert.equal(artifact.effort, effort);
    assert.equal(artifact.identity, remediation ? 'example-remediation' : 'example-writer');
    assert.deepEqual(await runAttempt(await withoutCheckout(f, journal, args)), result);
    assert.deepEqual(await journal.get(f.envelope.runId), saved);
    assert.equal(calls, 1); assert.equal(f.pushes(), 1);
    assert.equal(f.comments.filter(c => c.body.includes('## Codex Outcome')).length, 1);
  });
}

test('installed profile rejection never starts a child or inherits a model default', async () => {
  const common = ['--input-file', '/not-read/task-input.md', '--cwd', '/not-read', '--issue', '209'];
  for (const profile of [
    ['../escape', 'high'], ['--flag', 'high'], ['model with spaces', 'high'],
    ['gpt-6-astra', 'max;echo'], ['gpt-6-astra', 'effort=high'], ['', 'high'], ['gpt-6-astra', ''],
    ['m'.repeat(129), 'high'], ['gpt-6-astra', 'e'.repeat(65)],
  ]) {
    await assert.rejects(exec('/usr/bin/sudo', ['-n', '-u', 'relay-codex', '/opt/codex-relay/relay-codex',
      'exec', '--json', '--model', profile[0], '--effort', profile[1], ...common]), error => {
      assert.equal(error.code, 64);
      assert.match(error.stderr, /CODEX_LAUNCHER_ARGUMENT_VALUE_INVALID/);
      assert.match(error.stderr, /"childStarted":false/);
      return true;
    });
  }
  for (const args of [[], ['exec', '--json', ...common], ['exec', '--json', '--model', 'gpt-6-astra', ...common]]) {
    await assert.rejects(exec('/usr/bin/sudo', ['-n', '-u', 'relay-codex', '/opt/codex-relay/relay-codex', ...args]), error => {
      assert.equal(error.code, 64);
      assert.match(error.stderr, /CODEX_LAUNCHER_ARGUMENT_CONTRACT_INVALID/);
      assert.match(error.stderr, /"childStarted":false/);
      return true;
    });
  }
});

test('installed checkout-ownership keeps fixture cleanup and collection isolated', async t => {
  const first = await fixture(t, { installed: true, remediation: true, instruction: 'fixture-mode=checkout-ownership-first' });
  const second = await fixture(t, { installed: true, remediation: true, instruction: 'fixture-mode=checkout-ownership-second' });
  assert.notEqual(first.envelope.attemptId, second.envelope.attemptId);
  assert.match(first.envelope.attemptId, /^run-\d+$/);
  assert.match(second.envelope.attemptId, /^run-\d+$/);
  assert.equal(Number(second.envelope.attemptId.slice(4)), Number(first.envelope.attemptId.slice(4)) + 1);
  assert.equal(first.envelope.startHead, second.envelope.startHead);
  assert.notEqual(first.cwd, second.cwd);
  await first.prepare(first.envelope); await first.commit();
  await second.prepare(second.envelope); await second.commit();
  // This is the same idempotent cleanup registered with t.after(). Before
  // checkout ownership was isolated, event-77 made it remove the checkout
  // whose loose objects the other fixture was about to import.
  await first.removeCheckout();
  const secondProgress = await second.collect(second.envelope);
  assert.notEqual(secondProgress.head, second.envelope.startHead);
  assert.ok(secondProgress.bundle);
});

for (const [mode, code, state] of [
  ['invalid-result', 'CODEX_RESULT_MISSING', 'confirmed'],
  ['child-failure', 'CODEX_NONZERO_EXIT', 'confirmed'],
  ['missing-token', 'CODEX_NONZERO_EXIT', 'known-not-executed'],
  ['missing-binary', 'CODEX_NONZERO_EXIT', 'known-not-executed'],
  ['missing-import', 'CODEX_NONZERO_EXIT', 'uncertain'],
  ['package-eacces', 'CODEX_NONZERO_EXIT', 'known-not-executed'],
]) {
  test(`installed ${mode} preserves cause, correlation, progress and no duplicate`, async t => {
    const f = await fixture(t, { installed: true, remediation: true, instruction: `fixture-mode=${mode}; Маркер UTF-8` });
    const journal = attemptStore(f);
    const dispatcher = createOnDemandDispatchAdapter(); let calls = 0;
    const path = mode === 'missing-token' ? '/etc/codex-relay/codex-credentials/access-token'
      : mode === 'missing-binary' ? '/opt/codex-relay/codex-runtime/bin/codex'
      : mode === 'missing-import' ? '/opt/codex-relay/codex-runtime/relay-codex-diagnostic.mjs' : null;
    if (path) {
      // Root fixture prepares distinct failure configurations before each
      // unprivileged test process; no runner access to protected files.
      assert.equal(process.env.INSTALLED_FAILURE_MODE, mode);
    }
    const args = { ...f, journal, execute: e => { calls++; return dispatcher.dispatch(e); } };
    let initialError;
    let initialResult;
    const domain = state === 'confirmed';
    if (domain) {
      initialResult = await runAttempt(args);
      assert.equal(initialResult.status, 'BLOCKED');
      assert.equal((await f.api.get(`/pulls/${f.pr.number}`)).draft, true);
    } else await assert.rejects(runAttempt(args), error => {
      assert.equal(error.code, code); initialError = error; return true;
    });
    const saved = await journal.get(f.envelope.runId); const d = saved.diagnostic;
    assert.equal(d.executionState, state); assert.equal(d.executionId, f.envelope.attemptId);
    assert.equal(d.durable.diagnosticStore.status, 'stored');
    assert.equal(d.durable.diagnosticStore.executionId, f.envelope.attemptId);
    assert.ok(d.lastSuccessfulBoundary); assert.ok(d.failureBoundary);
    if (mode === 'invalid-result') assert.equal(d.primaryCause, 'CODEX_RESULT_MISSING');
    if (mode === 'missing-token') assert.equal(d.primaryCause, 'CODEX_LAUNCHER_ACCESS_TOKEN_UNAVAILABLE');
    if (mode === 'missing-binary') assert.equal(d.primaryCause, 'ENOENT');
    if (mode === 'package-eacces') {
      assert.equal(d.primaryCause, 'EACCES');
      assert.equal(saved.execution.child, 'not_started');
      assert.equal(d.lastSuccessfulBoundary, 'launcher');
      assert.equal(d.failureBoundary, 'launcher');
      assert.equal(d.containment, 'reaped');
      assert.equal(f.pushes(), 0);
      console.log('GENERAL_RUNNER_EACCES_REPRODUCED child=not_started;boundary=launcher;cause=EACCES;publication=once');
    }
    if (state === 'confirmed') {
      assert.equal(saved.progress.head, await f.remoteHead());
      assert.equal(d.durable.publishedHead, saved.progress.head);
    }
    const outcomes = () => f.comments.filter(c => c.body.includes('## Codex Outcome'));
    assert.equal(outcomes().length, 1);
    const body = outcomes()[0].body;
    assert.match(body, /^## Codex Outcome\n\nStatus: BLOCKED/);
    assert.match(body, new RegExp(`Thread: ${escapeRegex(f.envelope.thread)}`));
    assert.match(body, new RegExp(`Correlation: ${escapeRegex(threadCorrelationIdentity(f.envelope.thread))}`));
    assert.match(body, new RegExp(`Attempt: ${escapeRegex(f.envelope.attemptId)}`));
    assert.match(body, new RegExp(`Cause summary: ${escapeRegex(d.primaryCause ?? 'UNAVAILABLE')}`));
    if (state === 'confirmed') {
      assert.match(body, new RegExp(`Durable/published head: ${saved.progress.head}`));
    } else {
      assert.match(body, /Durable\/published head: NONE PUBLISHED/);
    }
    assert.match(body, /Last successful boundary: [a-z][a-z0-9-]*/);
    assert.match(body, /Failure boundary: [a-z][a-z0-9-]*/);
    const pushes = f.pushes();
    if (domain) assert.deepEqual(await runAttempt(await withoutCheckout(f, journal, args)), initialResult);
    else await assert.rejects(runAttempt(await withoutCheckout(f, journal, args)), error => {
      assert.equal(error.code, initialError.code);
      assert.equal(error.message, initialError.message);
      assert.deepEqual(error.details.diagnostic, initialError.details.diagnostic);
      assert.deepEqual(error.details.causal, initialError.details.causal);
      assert.deepEqual(error.details.outcomePublication, initialError.details.outcomePublication);
      assert.equal(error.details.executionId, initialError.details.executionId);
      assert.equal(error.details.attemptId, initialError.details.attemptId);
      return true;
    });
    assert.deepEqual(await journal.get(f.envelope.runId), saved);
    assert.equal(f.pushes(), pushes); assert.equal(calls, 1);
    assert.equal(outcomes().length, 1);
  });
}

test('installed first collection ENOENT remains a failure before progress publication', async t => {
  const f = await fixture(t, { installed: true, remediation: true });
  const journal = attemptStore(f);
  const missing = Object.assign(new Error('first required collection unavailable'), { code: 'ENOENT' });
  let collections = 0;
  await assert.rejects(runAttempt({ ...f, journal,
    execute: async e => {
      await f.commit();
      return { version: e.version, attemptId: e.attemptId, child: 'started', containment: 'reaped', result: { status: 'success' } };
    },
    collect: () => { collections++; throw missing; }
  }), error => { assert.equal(error, missing); return true; });
  const saved = await journal.get(f.envelope.runId);
  assert.equal(collections, 1); assert.equal(f.pushes(), 0);
  assert.equal(saved.progress, null); assert.equal(saved.outcome.status, 'BLOCKED');
  assert.equal(saved.diagnostic.classification.code, 'ENOENT');
  assert.equal(saved.diagnostic.failureBoundary, 'progress');
  assert.equal(f.comments.filter(c => c.body.includes('## Codex Outcome')).length, 1);
});
