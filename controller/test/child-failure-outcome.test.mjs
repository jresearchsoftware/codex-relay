import test from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { PassThrough } from 'node:stream';
import { dirname, join } from 'node:path';
import { rm } from 'node:fs/promises';
import { fixture, memoryStore } from './fixture.mjs';
import { runAttempt } from '../src/attempt.mjs';
import { causalEvidence } from '../src/execution-contract.mjs';
import { createOnDemandDispatchAdapter } from '../src/github.mjs';
import { reserveRuntimeDiagnostic } from '../src/diagnostic-fallback.mjs';
import { terminalOutcomeBody } from '../src/outcome.mjs';
import { runGovernedCodexTask, parseLauncherDiagnostic } from '../../runtime/src/codex-runtime.mjs';
import { finalizeRuntimeArtifacts } from '../../runtime/src/runtime-finalization.mjs';
import { buildChildDiagnostic } from '../../deploy/ansible/roles/relay_codex_runtime/files/relay-codex-diagnostic.mjs';

const privateText = 'private-prompt-fixture /protected/private-file token=synthetic-private-secret';
const observedBytes = 5 * 1024 * 1024;
function processFixture() {
  const child = new EventEmitter();
  child.stdin = new PassThrough(); child.stdout = new PassThrough(); child.stderr = new PassThrough();
  return child;
}

for (const example of [
  { name: 'classified exit', exit: 7, signal: null, cause: 'PROCESS_IO_ERROR' },
  { name: 'inner signal', exit: null, signal: 'SIGTERM', cause: 'PROCESS_IO_ERROR' },
  { name: 'unavailable inner observation', exit: null, signal: null, cause: 'PROCESS_IO_ERROR' },
  { name: 'invalid inner observation', exit: 256, signal: 'SIGTERM\nprivate', cause: 'PROCESS_IO_ERROR' },
  { name: 'launcher failure before child', exit: null, signal: null, cause: 'EACCES', notStarted: true },
  { name: 'missing launcher diagnostic', missing: true, exit: null, signal: null },
  { name: 'primary store unavailable', exit: 7, signal: null, cause: 'PROCESS_IO_ERROR', storeFails: true }
]) test(`automatic Outcome preserves ${example.name} across runtime, dispatcher, Writer and replay`, async t => {
  const f = await fixture(t); const journal = memoryStore(); let capsule; let launches = 0;
  const primary = [];
  const diagnosticStore = async value => {
    if (example.storeFails) throw Object.assign(new Error(privateText), { code: 'ENOSPC' });
    primary.push(value);
    return { status: 'stored', executionId: value.executionId };
  };
  const launcher = {
    ...buildChildDiagnostic({ code: 'PROCESS_IO_ERROR', childStarted: !example.notStarted, exitCode: example.exit,
      signal: example.signal, stderr: privateText, stderrBytes: observedBytes }),
    // Invalid input exercises the runtime's bounded observation checks.
    childExitCode: example.exit, signal: example.signal, primaryCause: example.notStarted ? 'EACCES' : null
  };
  const dispatcher = createOnDemandDispatchAdapter({
    reserveDiagnostic: async ({ executionId }) => capsule = await reserveRuntimeDiagnostic({ executionId, root: join(f.root, 'fallback') }),
    spawnImpl: () => {
      const child = processFixture();
      child.stdin.resume();
      child.stdin.on('end', async () => {
        try {
          await runGovernedCodexTask({ attemptId: f.envelope.attemptId, inputText: privateText, cwd: f.cwd,
            buildArgs: () => [], env: { PATH: process.env.PATH }, existingFallback: true, openFallback: async () => capsule,
            readDiagnosticConfig: async () => ({ mode: 'normal' }), diagnosticStore,
            spawnImpl: () => {
              launches++;
              const inner = processFixture();
              setImmediate(() => {
                inner.emit('spawn'); inner.stdout.end();
                inner.stderr.end(example.missing ? privateText : JSON.stringify(launcher) + '\n');
                inner.emit('close', 64, null);
              });
              return inner;
            } });
          assert.fail('nonzero launcher must fail');
        } catch (error) {
          child.stdout.end();
          child.stderr.end(JSON.stringify({ version: f.envelope.version, status: 'blocked', code: error.code,
            diagnostic: causalEvidence(error, { child: error.details?.childState, stage: 'execution' }) }));
          child.emit('close', 1, null);
        }
      });
      return child;
    },
    finalizeArtifacts: options => finalizeRuntimeArtifacts({ ...options, workRoot: dirname(f.cwd), diagnosticStore,
      cleanupSandbox: async ({ cwd }) => {
        assert.equal(cwd, f.cwd);
        await rm(join(cwd, '.codex-sandbox'), { recursive: true });
      } })
  });
  const args = { ...f, journal, execute: envelope => dispatcher.dispatch(envelope),
    // Retained diagnostic artifacts are separate from this fixture's task work.
    ...(example.storeFails ? { collect: async () => ({ head: f.envelope.startHead, clean: true }) } : {}) };
  if (example.missing || example.storeFails || example.notStarted) await assert.rejects(runAttempt(args), { code: 'CODEX_NONZERO_EXIT' });
  else assert.equal((await runAttempt(args)).status, 'BLOCKED');
  const saved = await journal.get(f.envelope.runId);
  const body = f.comments[0].body;
  assert.match(body, /Terminal code: CODEX_NONZERO_EXIT/);
  assert.match(body, new RegExp(`Launcher diagnostic: ${example.missing ? 'UNCLASSIFIED_CHILD_FAILURE' : 'PROCESS_IO_ERROR'}`));
  assert.match(body, new RegExp(`Cause summary: ${example.cause ?? 'UNAVAILABLE'}`));
  assert.match(body, new RegExp(`Codex child: ${example.missing ? 'unknown' : example.notStarted ? 'not_started' : 'started'}; exit code: ${example.exit === 7 ? 7 : 'UNAVAILABLE'}; signal: ${example.signal === 'SIGTERM' ? 'SIGTERM' : 'UNAVAILABLE'}`));
  if (example.notStarted) assert.match(body, /Failure boundary: launcher/);
  if (!example.missing) assert.match(body, new RegExp(`bytes: ${observedBytes}; truncated: true`));
  if (example.storeFails) assert.match(body, /Primary diagnostics: unavailable; reference: run-99; store cause: ENOSPC/);
  assert.doesNotMatch(body, /private-prompt-fixture|protected\/private-file|synthetic-private-secret|exit code: 64/);
  assert.doesNotMatch(JSON.stringify(saved.diagnostic), /private-prompt-fixture|protected\/private-file|synthetic-private-secret/);
  if (!example.storeFails) assert.equal(primary[0].process.exitCode, 64);
  const replay = { ...args, execute: () => assert.fail('replay must not execute'), prepare: () => assert.fail('replay must not prepare'), collect: () => assert.fail('replay must not collect') };
  if (example.missing || example.storeFails || example.notStarted) await assert.rejects(runAttempt(replay), { code: 'CODEX_NONZERO_EXIT' });
  else assert.deepEqual(await runAttempt(replay), saved.outcome);
  assert.equal(launches, 1); assert.equal(f.comments.length, 1); assert.equal(f.comments[0].body, body);
});

test('public child evidence rejects free text, invalid numbers and raw diagnostic previews', () => {
  const diagnostic = causalEvidence({ code: 'CODEX_NONZERO_EXIT', details: { failureDiagnostic: {
    diagnosticCode: privateText, primaryCause: privateText, childState: privateText,
    childExitCode: 256, signal: privateText, diagnosticBytes: -1, truncated: 'yes', preview: privateText
  } } });
  const body = terminalOutcomeBody({}, { terminalCode: 'CODEX_NONZERO_EXIT', diagnostic });
  assert.match(body, /Launcher diagnostic: UNAVAILABLE/);
  assert.match(body, /Codex child: unknown; exit code: UNAVAILABLE; signal: UNAVAILABLE/);
  assert.doesNotMatch(body, /private-prompt-fixture|protected\/private-file|synthetic-private-secret/);
});

test('normal and debug truncation retain total observed bytes without raising capture limits', () => {
  for (const debug of [false, true]) {
    const value = buildChildDiagnostic({ code: 'CHILD_STDERR', stderr: privateText, stderrBytes: observedBytes, debug });
    const parsed = parseLauncherDiagnostic(JSON.stringify(value));
    assert.equal(parsed.code, 'CHILD_STDERR'); assert.equal(parsed.bytes, observedBytes); assert.equal(parsed.truncated, true);
    for (const bytes of [-1, 1.5, Number.MAX_SAFE_INTEGER + 1]) {
      assert.equal(parseLauncherDiagnostic(JSON.stringify({ ...value, bytes })).code, 'UNCLASSIFIED_CHILD_FAILURE');
    }
  }
});

test('Git publication bytes cannot become launcher evidence or replace inherited launcher counts', () => {
  const original = causalEvidence({ code: 'CODEX_NONZERO_EXIT', details: { failureDiagnostic: {
    diagnosticCode: 'PROCESS_IO_ERROR', primaryCause: 'PROCESS_IO_ERROR', bytes: observedBytes, truncated: true,
    childState: 'started', childExitCode: 7, signal: 'SIGKILL'
  } } });
  const publicationFailure = { code: 'TRUSTED_GIT_FAILED', details: { failureDiagnostic: {
    classification: 'GIT_AUTHORIZATION_REJECTED', primaryCause: 'GIT_AUTHORIZATION_REJECTED',
    operation: 'push', gitExitCode: 128, signal: 'SIGTERM', bytes: 16, truncated: false, preview: 'private Git output'
  } } };
  const alone = causalEvidence(publicationFailure, { stage: 'progress' });
  assert.equal(alone.launcher, undefined);
  assert.equal(alone.observed.signal, undefined);
  assert.equal(alone.publication.signal, 'SIGTERM');
  const inherited = causalEvidence({ ...publicationFailure, details: { ...publicationFailure.details, causal: original } }, { stage: 'progress' });
  assert.deepEqual(inherited.launcher, original.launcher);
  assert.equal(inherited.observed.exitCode, 7);
  assert.equal(inherited.observed.signal, 'SIGKILL');
  assert.equal(inherited.publication.gitExitCode, 128);
  assert.equal(inherited.publication.signal, 'SIGTERM');
  const body = terminalOutcomeBody({}, { terminalCode: 'TRUSTED_GIT_FAILED', diagnostic: inherited });
  assert.match(body, new RegExp(`Launcher diagnostic: PROCESS_IO_ERROR; bytes: ${observedBytes}; truncated: true`));
  assert.match(body, /Cause summary: GIT_AUTHORIZATION_REJECTED/);
  assert.match(body, /Codex child: started; exit code: 7; signal: SIGKILL/);
  assert.doesNotMatch(body, /private Git output/);
});
