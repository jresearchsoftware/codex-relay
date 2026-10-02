import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, rm, readFile, stat } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { EventEmitter } from 'node:events';
import { PassThrough } from 'node:stream';
import { reserveRuntimeDiagnostic, openRuntimeDiagnostic } from '../../controller/src/diagnostic-fallback.mjs';
import { writeDiagnosticBundle } from '../../controller/src/diagnostic-store.mjs';
import { runGovernedCodexTask } from '../src/codex-runtime.mjs';
import { finalizeRuntimeArtifacts } from '../src/runtime-finalization.mjs';
import { causalEvidence } from '../../controller/src/execution-contract.mjs';

async function fixture(t) {
  const root = await mkdtemp(join(tmpdir(), 'relay-durable-runtime-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const workRoot = join(root, 'work'); const cwd = join(workRoot, 'run-39');
  await mkdir(cwd, { recursive: true });
  const fallbackRoot = join(root, 'fallback'); const primaryRoot = join(root, 'primary');
  const capsule = await reserveRuntimeDiagnostic({ executionId: 'run-39', root: fallbackRoot });
  let cleanupCalls = 0;
  const diagnosticStore = diagnostic => writeDiagnosticBundle(diagnostic, { root: primaryRoot });
  const options = { attemptId: 'run-39', cwd, inputText: 'Admitted fixture', buildArgs: () => [],
    env: { PATH: '/usr/bin:/bin' }, existingFallback: true, openFallback: async () => capsule,
    diagnosticStore, spawnImpl: childFixture(), evidence: {} };
  const finalize = overrides => finalizeRuntimeArtifacts({ executionId: 'run-39', containment: 'reaped',
    fallbackStore: capsule, workRoot, diagnosticStore,
    cleanupSandbox: async ({ cwd: actual }) => { cleanupCalls++; assert.equal(actual, cwd); await rm(join(actual, '.codex-sandbox'), { recursive: true }); },
    ...overrides });
  return { root, cwd, fallbackRoot, primaryRoot, capsule, options, finalize, cleanupCalls: () => cleanupCalls };
}

function childFixture({ code = 0, stdout, stderr } = {}) {
  return () => {
    const child = new EventEmitter(); child.stdout = new PassThrough(); child.stderr = new PassThrough(); child.pid = 4242;
    setImmediate(() => {
      child.emit('spawn');
      child.stdout.end(stdout ?? JSON.stringify({ type: 'task_result', result: { status: 'success', summary: 'done', validation: [], blockedReason: '' } }) + '\n');
      child.stderr.end(stderr ?? JSON.stringify({ source: 'relay-codex-launcher', schemaVersion: 1,
        code: code ? 'CHILD_STDERR' : 'CODEX_EXIT_OK', childStarted: true, childExitCode: code, bytes: 0, preview: '', primaryCause: code ? 'CHILD_STDERR' : null }) + '\n');
      child.emit('close', code, null);
    });
    return child;
  };
}

test('successful runtime durably prepares evidence then cleans only after outer containment', async t => {
  const f = await fixture(t);
  assert.equal((await runGovernedCodexTask(f.options)).status, 'success');
  assert.equal(f.cleanupCalls(), 0);
  assert.equal((await f.capsule.read()).persistence, 'not_required');
  assert.ok((await stat(join(f.cwd, '.codex-sandbox'))).isDirectory());
  const receipt = await f.finalize();
  assert.equal(receipt.cleanup, 'complete'); assert.equal(receipt.retention, 'none');
  assert.equal(f.cleanupCalls(), 1);
  assert.equal(await openRuntimeDiagnostic({ executionId: 'run-39', root: f.fallbackRoot }), null);
  await assert.rejects(stat(join(f.cwd, '.codex-sandbox')), { code: 'ENOENT' });
});

test('failures before child, child nonzero, parsing and runtime finalization persist independently', async t => {
  for (const example of [
    { name: 'config', override: { readDiagnosticConfig: async () => { throw Object.assign(new Error('configuration'), { code: 'EIO', syscall: 'read' }); } }, code: 'EIO', operation: 'diagnostic-config' },
    { name: 'arguments', override: { buildArgs: () => { throw Object.assign(new Error('physical failure'), { code: 'ENOMEM', syscall: 'spawn' }); } }, code: 'ENOMEM', operation: 'build-arguments' },
    { name: 'spawn', override: { spawnImpl: () => { throw Object.assign(new Error('launch'), { code: 'EACCES', syscall: 'spawn' }); } }, code: 'PROCESS_START_FAILED', operation: 'launcher-spawn' },
    { name: 'child', override: { spawnImpl: childFixture({ code: 9 }) }, code: 'CODEX_NONZERO_EXIT', operation: 'child-result' },
    { name: 'parse', override: { spawnImpl: childFixture({ stdout: '{broken\n' }) }, code: 'CODEX_JSON_INVALID', operation: 'result-parse' }
  ]) await t.test(example.name, async t => {
    const f = await fixture(t); let failure;
    await assert.rejects(runGovernedCodexTask({ ...f.options, ...example.override }), error => { failure = error; return error.code === example.code; });
    const record = await f.capsule.read();
    assert.equal(record.persistence, 'stored'); assert.equal(record.failureDiagnostic.operation, example.operation);
    assert.equal(failure.details.diagnosticStore.status, 'stored');
    const saved = JSON.parse(await readFile(join(f.primaryRoot, 'run-39.json'), 'utf8'));
    assert.equal(saved.lifecycle.cleanupComplete, false);
    const result = await f.finalize({ failure: { code: example.code } });
    assert.ok(['complete', 'retained'].includes(result.cleanup));
    const propagated = causalEvidence({ code: example.code, details: { ...failure.details, ...result,
      failureDiagnostic: failure.details.failureDiagnostic } }, { child: record.childState, containment: 'reaped' });
    assert.equal(propagated.runtime.cleanup, result.cleanup);
    assert.ok(await openRuntimeDiagnostic({ executionId: 'run-39', root: f.fallbackRoot }));
  });
});

test('diagnostic capture and primary store failure retain sandbox plus an independent durable capsule', async t => {
  for (const capture of [true, false]) await t.test(capture ? 'capture' : 'store', async t => {
    const f = await fixture(t);
    const fail = () => { throw Object.assign(new Error('private detail token=secret'), { code: 'ENOSPC' }); };
    const override = capture ? { createDiagnostic: fail } : { diagnosticStore: fail };
    await assert.rejects(runGovernedCodexTask({ ...f.options, ...override, readDiagnosticConfig: async () => ({ mode: 'debug' }) }), { code: 'RUNTIME_DIAGNOSTICS_FAILED' });
    const reopened = await openRuntimeDiagnostic({ executionId: 'run-39', root: f.fallbackRoot });
    const record = await reopened.read();
    assert.equal(record.persistence, 'failed'); assert.equal(record.diagnosticStore.storeCode, 'ENOSPC');
    assert.equal(record.retention, 'retained'); assert.equal(record.childState, 'started');
    assert.doesNotMatch(JSON.stringify(record), /private detail|secret/);
    await assert.rejects(f.finalize(), { code: 'RUNTIME_DIAGNOSTICS_FAILED' });
    assert.equal(f.cleanupCalls(), 0); assert.ok((await stat(join(f.cwd, '.codex-sandbox'))).isDirectory());
  });
});

test('cleanup EACCES and EPERM survive as cleanup causes, with safe OS context and retained artifacts', async t => {
  for (const code of ['EACCES', 'EPERM']) await t.test(code, async t => {
    const f = await fixture(t); await runGovernedCodexTask(f.options);
    let failure;
    await assert.rejects(f.finalize({ cleanupSandbox: async () => { throw Object.assign(new Error('arbitrary credentials'), {
      code, syscall: 'unlink', path: '.codex-sandbox/home/tmp/arg0/token=secret' }); } }), error => { failure = error; return error.code === 'SANDBOX_CLEANUP_FAILED'; });
    const record = await f.capsule.read();
    assert.equal(record.cleanup, 'failed'); assert.equal(record.retention, 'retained');
    assert.equal(record.primaryCause, code); assert.equal(record.syscall, 'unlink');
    const causal = causalEvidence(failure, { child: 'started', containment: 'reaped' });
    assert.equal(causal.failureBoundary, 'cleanup'); assert.equal(causal.primaryCause, code);
    assert.doesNotMatch(JSON.stringify(causal), /arbitrary|token=secret|\.codex-sandbox/);
    const saved = await readFile(join(f.primaryRoot, 'run-39-cleanup.json'), 'utf8');
    assert.match(saved, /arg0/); assert.doesNotMatch(saved, /token=secret/);
  });
});

test('primary and cleanup-store failure still leave cleanup cause in independent capsule', async t => {
  const f = await fixture(t); await runGovernedCodexTask(f.options);
  await assert.rejects(f.finalize({
    cleanupSandbox: async () => { throw Object.assign(new Error('denied'), { code: 'EACCES', syscall: 'rmdir' }); },
    diagnosticStore: async () => { throw Object.assign(new Error('disk'), { code: 'EIO' }); }
  }), { code: 'SANDBOX_CLEANUP_FAILED' });
  const record = await f.capsule.read();
  assert.equal(record.primaryCause, 'EACCES'); assert.equal(record.diagnosticStore.storeCode, 'EIO');
  assert.equal(record.retention, 'retained');
});

test('unknown containment and failure of fallback update prohibit deletion', async t => {
  const f = await fixture(t); await runGovernedCodexTask(f.options);
  await assert.rejects(f.finalize({ containment: 'unknown' }), { code: 'CONTAINMENT_NOT_PROVEN' });
  assert.equal(f.cleanupCalls(), 0);
  const old = await f.capsule.read();
  await assert.rejects(f.finalize({ fallbackStore: { ...f.capsule, write: async () => { throw Object.assign(new Error('disk'), { code: 'EIO' }); } } }), { code: 'RUNTIME_DIAGNOSTICS_FAILED' });
  assert.deepEqual(await f.capsule.read(), old); assert.equal(f.cleanupCalls(), 0);
});

test('existing protected sandbox is never adopted, chmodded or deleted by another invocation', async t => {
  const f = await fixture(t);
  const privateRoot = join(f.cwd, '.codex-sandbox');
  await mkdir(privateRoot, { mode: 0o700 });
  await assert.rejects(runGovernedCodexTask(f.options), { code: 'CODEX_SANDBOX_ALREADY_EXISTS' });
  const state = await f.capsule.read();
  assert.equal(state.sandboxCreated, false); assert.equal(state.sandboxIdentity, undefined);
  await f.finalize({ failure: { code: 'CODEX_SANDBOX_ALREADY_EXISTS' } });
  assert.equal(f.cleanupCalls(), 0); assert.equal((await stat(privateRoot)).mode & 0o777, 0o700);
});

test('fallback update failure during finalization leaves the preceding durable operation intact', async t => {
  const f = await fixture(t);
  const write = f.capsule.write.bind(f.capsule);
  let failed = false;
  const failing = { ...f.capsule, write: async value => {
    if (value.operation === 'runtime-finalization') failed = true;
    if (failed) throw Object.assign(new Error('failed filesystem'), { code: 'EIO' });
    return write(value);
  } };
  await assert.rejects(runGovernedCodexTask({ ...f.options, openFallback: async () => failing }), { code: 'EIO' });
  const record = await f.capsule.read();
  assert.equal(record.operation, 'result-parse'); assert.equal(record.persistence, 'pending');
  await assert.rejects(f.finalize(), { code: 'RUNTIME_DIAGNOSTICS_FAILED' });
  assert.equal(f.cleanupCalls(), 0);
  assert.ok((await stat(join(f.cwd, '.codex-sandbox'))).isDirectory());
});
