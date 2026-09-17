import test from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { readFileSync } from 'node:fs';
import { CONSUMER } from '../../consumer/consumer.mjs';
import { mkdtemp, mkdir, rm, symlink } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { PassThrough } from 'node:stream';
import { join } from 'node:path';
import { parseLauncherDiagnostic, parseCodexJsonLines, buildCodexProcessSpec, runGovernedCodexTask, preflightCodexWorkspace, buildCodexEnvironment } from '../src/codex-runtime.mjs';
import { causalEvidence } from '../../controller/src/execution-contract.mjs';

test('worker arguments resolve absent profiles and preserve explicit unknown identifiers', async t => {
  const root = await mkdtemp(join(tmpdir(), 'codex-profile-runtime-test-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  for (const [profile, expected] of [
    [undefined, CONSUMER.defaultProfile],
    [{ cliModelId: 'future-model', effort: 'future-effort' }, { cliModelId: 'future-model', effort: 'future-effort' }]
  ]) {
    let invoked = false;
    const result = await runGovernedCodexTask({ profile, inputText: 'Admitted task', cwd: root, targetNumber: 12,
      diagnosticStore: async () => undefined,
      buildArgs: ({ profile, inputPath }) => {
        const delivered = readFileSync(inputPath, 'utf8');
        assert.ok(delivered.startsWith('Admitted task\n'));
        assert.match(delivered, /Progress-bounded execution/);
        assert.match(delivered, /no fixed correction-count default/);
        assert.match(delivered, /Unknown prior execution state, ambiguous external mutation, uncontained prior execution/);
        assert.match(delivered, /does not authorize blind Relay retries/);
        return ['--model', profile.cliModelId, '--effort', profile.effort];
      },
      env: { PATH: '/usr/bin:/bin' }, spawnImpl(command, args) {
        invoked = true;
        assert.equal(command, '/usr/bin/sudo');
        assert.equal(args[args.indexOf('--model') + 1], expected.cliModelId);
        assert.equal(args[args.indexOf('--effort') + 1], expected.effort);
        const child = new EventEmitter(); child.stdout = new PassThrough(); child.stderr = new PassThrough();
        setImmediate(() => {
          child.emit('spawn');
          child.stdout.end(JSON.stringify({ type: 'item.completed', item: { type: 'agent_message',
            text: JSON.stringify({ status: 'success', summary: 'done', validation: [], blockedReason: '' }) } }) + '\n');
          child.stderr.end(); child.emit('close', 0, null);
        });
        return child;
      }
    });
    assert.equal(invoked, true); assert.equal(result.status, 'success');
  }
});

test('workspace preflight needs no path list and preserves sandbox and symlink containment', async t => {
  const root = await mkdtemp(join(tmpdir(), 'codex-workspace-test-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const cwd = join(root, 'checkout'); await mkdir(cwd);
  assert.equal((await preflightCodexWorkspace({ cwd })).checkoutRoot, cwd);
  await assert.rejects(preflightCodexWorkspace({ cwd, sandboxRoot: join(root, 'outside') }), { code: 'CODEX_PATH_PREFLIGHT_INVALID' });
  await symlink(cwd, join(root, 'checkout-link'));
  await assert.rejects(preflightCodexWorkspace({ cwd: join(root, 'checkout-link') }), { code: 'CODEX_PATH_PREFLIGHT_FAILED' });
  await symlink(root, join(cwd, 'escape'));
  await assert.rejects(preflightCodexWorkspace({ cwd, sandboxRoot: join(cwd, 'escape/sandbox') }), { code: 'CODEX_PATH_PREFLIGHT_FAILED' });
  const env = buildCodexEnvironment({ PATH: '/usr/bin:/bin', GITHUB_TOKEN: 'synthetic', SSH_AUTH_SOCK: '/synthetic' });
  assert.ok(!('GITHUB_TOKEN' in env)); assert.ok(!('SSH_AUTH_SOCK' in env));
  assert.equal(env.GIT_CONFIG_NOSYSTEM, '1'); assert.equal(env.GIT_TERMINAL_PROMPT, '0');
});
test('missing and malformed diagnostics cannot prove the child did not start', () => {
  for (const input of ['', 'arbitrary stderr', '{broken']) {
    const d = parseLauncherDiagnostic(input); assert.equal(d.childState, 'unknown'); assert.equal(d.childStarted, null);
    assert.equal(d.childExitCode, null); assert.equal(d.signal, null);
  }
});
test('explicit launcher observations preserve each child state', () => {
  for (const started of [true, false]) {
    const d = parseLauncherDiagnostic(JSON.stringify({ source: 'relay-codex-launcher', schemaVersion: 1, code: 'PROCESS_START_FAILED', bytes: 0, preview: '', childStarted: started }));
    assert.equal(d.childState, started ? 'started' : 'not_started');
  }
});
test('launcher diagnostics preserve bounded inner child exits and safe signals', () => {
  const diagnostic = { source: 'relay-codex-launcher', schemaVersion: 1, code: 'CHILD_STDERR', bytes: 0, preview: '', childStarted: true };
  for (const childExitCode of [0, 1, 101, 255]) {
    const parsed = parseLauncherDiagnostic(JSON.stringify({ ...diagnostic, childExitCode, signal: null }));
    assert.equal(parsed.childExitCode, childExitCode);
    assert.equal(parsed.signal, null);
  }
  for (const signal of ['SIGTERM', 'SIGKILL', 'SIGABRT', 'SIGRT32']) {
    const parsed = parseLauncherDiagnostic(JSON.stringify({ ...diagnostic, childExitCode: null, signal }));
    assert.equal(parsed.childExitCode, null);
    assert.equal(parsed.signal, signal);
  }
  for (const fields of [{}, { childExitCode: null, signal: null }]) {
    const parsed = parseLauncherDiagnostic(JSON.stringify({ ...diagnostic, ...fields }));
    assert.equal(parsed.childExitCode, null);
    assert.equal(parsed.signal, null);
    assert.equal(parsed.childStarted, true);
  }
});
test('invalid inner child exit metadata remains unknown without discarding the causal diagnostic', () => {
  const diagnostic = { source: 'relay-codex-launcher', schemaVersion: 1, code: 'CHILD_STDERR', bytes: 10, preview: 'cargo-test', childStarted: true };
  for (const childExitCode of ['-1', '256', '1.5', '1e309', '-1e309', '9007199254740992', '"101"', '""', 'true', 'false', '[]', '{}']) {
    const parsed = parseLauncherDiagnostic(JSON.stringify({ ...diagnostic, signal: 'SIGTERM' }).replace(/}$/, `,"childExitCode":${childExitCode}}`));
    assert.equal(parsed.childExitCode, null, childExitCode);
    assert.equal(parsed.signal, 'SIGTERM');
    assert.equal(parsed.childStarted, true);
    assert.equal(parsed.code, diagnostic.code);
    assert.equal(parsed.preview, diagnostic.preview);
  }
  for (const signal of ['', 'SIG', 'TERM', 'sigterm', 'SIGterm', 'SIG TERM', 'SIGTERM\n', 'SIGTERM\r', 'SIGTERM\u0000', 'SIGTERM\u2028', 'SIG;TERM', `SIG${'A'.repeat(30)}`, 15, true, [], {}]) {
    const parsed = parseLauncherDiagnostic(JSON.stringify({ ...diagnostic, childExitCode: 101, signal }));
    assert.equal(parsed.signal, null, JSON.stringify(signal));
    assert.equal(parsed.childExitCode, 101);
    assert.equal(parsed.childStarted, true);
    assert.equal(parsed.code, diagnostic.code);
    assert.equal(parsed.preview, diagnostic.preview);
  }
});
test('semantic result contains no model-managed deterministic metadata', () => {
  const value = { status: 'success', summary: 'Changed docs', validation: ['diff-check'], blockedReason: '' };
  const stream = result => [JSON.stringify({ type: 'thread.started', thread_id: 'native-thread-1' }), JSON.stringify({ type: 'item.completed', item: { type: 'agent_message', text: JSON.stringify(result) } })].join('\n');
  const result = parseCodexJsonLines(stream(value)); assert.equal(result.sessionId, 'native-thread-1');
  assert.throws(() => parseCodexJsonLines(stream({ ...value, headSha: 'a'.repeat(40) })), { code: 'CODEX_RESULT_INVALID' });
  assert.throws(() => buildCodexProcessSpec({ executable: '/tmp/model-launcher', args: [] }));
});
test('Codex child exit remains an execution exit and is not confused with publication exit', async t => {
  const root = await mkdtemp(join(tmpdir(), 'codex-runtime-exit-test-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  await mkdir(join(root, 'docs'));
  let failure;
  const spawnImpl = (command, args) => {
    assert.equal(command, '/usr/bin/sudo');
    assert.equal(args[0], '-n');
    const child = new EventEmitter();
    child.stdout = new PassThrough();
    child.stderr = new PassThrough();
    child.pid = 4242;
    setImmediate(() => {
      child.emit('spawn');
      child.stdout.end();
      child.stderr.end(`${JSON.stringify({ source: 'relay-codex-launcher', schemaVersion: 1, code: 'CODEX_RESULT_MISSING', bytes: 0, preview: '', childStarted: true })}\n`);
      child.emit('close', 7, null);
    });
    return child;
  };
  await assert.rejects(runGovernedCodexTask({
    operation: 'review-remediation', attemptId: 'event-245', profile: { cliModelId: 'gpt-5.6-luna', effort: 'high' },
    inputText: 'bounded test input', cwd: root, targetNumber: 245,
    buildArgs: () => [], env: { PATH: process.env.PATH }, spawnImpl, diagnosticStore: async () => undefined
  }), error => {
    failure = error;
    assert.equal(error.code, 'CODEX_NONZERO_EXIT');
    assert.equal(error.details.exitCode, undefined);
    assert.equal(error.details.childExitCode, 7);
    assert.equal(error.details.failureDiagnostic.childExitCode, 7);
    return true;
  });
  assert.equal(causalEvidence(failure, { child: 'started', containment: 'reaped', stage: 'execution' }).observed.exitCode, 7);
});
