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
    assert.ok(await openRuntimeDiagnostic({ executionId: 'run-39', root: f.fallbackRoot, includeReleased: true }));
    if (result.cleanup === 'complete') assert.equal(await openRuntimeDiagnostic({ executionId: 'run-39', root: f.fallbackRoot }), null);
  });
});

test('diagnostic capture and primary store failure retain sandbox plus an independent durable capsule', async t => {
  for (const capture of [true, false]) await t.test(capture ? 'capture' : 'store', async t => {
    const f = await fixture(t);
    const fail = () => { throw Object.assign(new Error('private detail token=secret'), { code: 'ENOSPC' }); };
    const override = capture ? { createDiagnostic: fail } : { diagnosticStore: fail };
    await assert.rejects(runGovernedCodexTask({ ...f.options, ...override, readDiagnosticConfig: async () => ({ mode: 'debug' }) }), error => {
      assert.equal(error.code, 'RUNTIME_DIAGNOSTICS_FAILED');
      assert.equal(causalEvidence(error).primaryCause, 'ENOSPC');
      return true;
    });
    const reopened = await openRuntimeDiagnostic({ executionId: 'run-39', root: f.fallbackRoot });
    const record = await reopened.read();
    assert.equal(record.persistence, 'failed'); assert.equal(record.diagnosticStore.storeCode, 'ENOSPC');
    assert.equal(record.retention, 'retained'); assert.equal(record.childState, 'started');
    assert.match(record.recorderFailure.exception.text, /private detail/);
    assert.doesNotMatch(JSON.stringify(record), /token=secret/);
    assert.doesNotMatch(JSON.stringify(causalEvidence({ code: 'RUNTIME_DIAGNOSTICS_FAILED', details: record })), /private detail|token=secret/);
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

test('more than eight contained preflight failures retire diagnostic capacity without deleting retained resources', async t => {
  const f = await fixture(t);
  // Release the fixture's unused reservation; each real failure below shares
  // this same bounded root rather than getting a fresh capacity pool.
  await f.capsule.write({ cleanup: 'complete', persistence: 'not_required', retention: 'none' });
  await f.capsule.release();
  for (let index = 0; index < 12; index++) {
    const executionId = `run-${100 + index}`;
    const capsule = await reserveRuntimeDiagnostic({ executionId, root: f.fallbackRoot });
    const cwd = join(f.root, 'work', executionId); await mkdir(cwd, { recursive: true });
    await assert.rejects(runGovernedCodexTask({ ...f.options, attemptId: executionId, cwd,
      openFallback: async () => capsule,
      readDiagnosticConfig: async () => { throw Object.assign(new Error('config unavailable'), { code: 'EIO' }); } }), { code: 'EIO' });
    const result = await finalizeRuntimeArtifacts({ executionId, containment: 'not_required', fallbackStore: capsule,
      diagnosticStore: f.options.diagnosticStore,
      failure: { code: 'EIO' }, cleanupSandbox: () => assert.fail('unknown resource identity must not be cleaned') });
    assert.equal(result.cleanup, 'retained'); assert.equal(result.retention, 'unknown');
    assert.equal(result.fallbackReference.status, 'released');
    assert.equal(result.diagnosticStore.executionId, `${executionId}-finalization`);
    assert.equal(await openRuntimeDiagnostic({ executionId, root: f.fallbackRoot }), null);
    const archived = JSON.parse(await readFile(join(f.primaryRoot, `${executionId}-finalization.json`), 'utf8'));
    assert.equal(archived.lifecycle.failureDiagnostic.code, 'EIO');
    assert.equal(archived.lifecycle.cleanup, 'retained');
    assert.equal(archived.lifecycle.sandboxCreated, false);
    assert.equal(archived.lifecycle.diagnosticStore.executionId, executionId);
  }
});

test('contained cleanup failures preserve resources and final inode evidence while reclaiming diagnostic capacity', async t => {
  const f = await fixture(t);
  await f.capsule.write({ cleanup: 'complete', persistence: 'not_required', retention: 'none' }); await f.capsule.release();
  for (let index = 0; index < 10; index++) {
    const executionId = `run-${200 + index}`;
    const capsule = await reserveRuntimeDiagnostic({ executionId, root: f.fallbackRoot });
    const cwd = join(f.root, 'work', executionId); await mkdir(cwd, { recursive: true });
    await runGovernedCodexTask({ ...f.options, attemptId: executionId, cwd, openFallback: async () => capsule });
    const before = await capsule.read();
    let failure;
    await assert.rejects(finalizeRuntimeArtifacts({ executionId, containment: 'reaped', fallbackStore: capsule,
      diagnosticStore: f.options.diagnosticStore,
      cleanupSandbox: async () => { throw Object.assign(new Error('denied'), { code: 'EACCES', syscall: 'unlink', cleanupContainment: 'reaped' }); } }),
    error => { failure = error; return error.code === 'SANDBOX_CLEANUP_FAILED'; });
    assert.equal(failure.details.cleanup, 'failed'); assert.equal(failure.details.retention, 'retained');
    assert.equal(failure.details.fallbackReference.status, 'released');
    assert.equal((await stat(join(cwd, '.codex-sandbox'))).isDirectory(), true);
    const archived = JSON.parse(await readFile(join(f.primaryRoot, `${executionId}-finalization.json`), 'utf8'));
    assert.deepEqual(archived.lifecycle.sandboxIdentity, before.sandboxIdentity);
    assert.equal(archived.lifecycle.cleanupContainment, 'reaped');
    assert.equal(archived.lifecycle.cleanup, 'failed');
    assert.equal(await openRuntimeDiagnostic({ executionId, root: f.fallbackRoot }), null);
  }
});

test('unknown cleanup processes and unproven final diagnostic persistence keep their active capsules', async t => {
  for (const mode of ['unknown-cleanup', 'archive-store-failed', 'archive-store-unproven']) await t.test(mode, async t => {
    const f = await fixture(t); await runGovernedCodexTask(f.options);
    const overrides = mode === 'unknown-cleanup'
      ? { cleanupSandbox: async () => { throw Object.assign(new Error('unknown process'), { code: 'EIO', cleanupContainment: 'unknown' }); } }
      : { failure: { code: 'CODEX_NONZERO_EXIT' }, diagnosticStore: async () => {
        if (mode === 'archive-store-failed') throw Object.assign(new Error('disk unavailable'), { code: 'ENOSPC' });
        return undefined;
      } };
    await assert.rejects(f.finalize(overrides), { code: mode === 'unknown-cleanup' ? 'SANDBOX_CLEANUP_FAILED' : 'RUNTIME_DIAGNOSTICS_FAILED' });
    assert.ok(await openRuntimeDiagnostic({ executionId: 'run-39', root: f.fallbackRoot }));
    const capsule = await f.capsule.read();
    assert.notEqual(capsule.released, true);
    if (mode === 'unknown-cleanup') assert.equal(capsule.cleanupContainment, 'unknown');
    else assert.equal(capsule.terminalDiagnostic.status, 'unavailable');
  });
});

test('final diagnostic retirement preserves the configured debug store mode', async t => {
  const f = await fixture(t);
  await runGovernedCodexTask({ ...f.options, readDiagnosticConfig: async () => ({ mode: 'debug' }) });
  const receipt = await f.finalize({ failure: { code: 'FIXTURE_CONTAINED_FAILURE' } });
  assert.equal(receipt.fallbackReference.status, 'released');
  assert.equal(receipt.diagnosticStore.mode, 'debug');
  const archived = JSON.parse(await readFile(join(f.primaryRoot, 'run-39-finalization.json'), 'utf8'));
  assert.equal(archived.mode, 'debug');
  assert.equal(archived.lifecycle.diagnosticStore.mode, 'debug');
});

test('no-child dispatch retirement never replaces unknown or pending actual runtime evidence', async t => {
  for (const mode of ['unknown-child', 'unknown-containment', 'sandbox-created', 'input-created', 'runtime-stage', 'runtime-child', 'persistence-failed']) await t.test(mode, async t => {
    const f = await fixture(t);
    const initial = { stage: 'dispatcher', operation: 'dispatch', childState: 'unknown', containment: 'unknown',
      persistence: 'pending', cleanup: 'pending', retention: 'unknown', sandboxCreated: false, inputSchemaCreated: false };
    const failure = { code: 'DISPATCH_NOT_STARTED', operation: 'dispatch', childState: 'not_started', containment: 'not_required' };
    if (mode === 'unknown-child') failure.childState = 'unknown';
    if (mode === 'unknown-containment') failure.containment = 'unknown';
    if (mode === 'sandbox-created') initial.sandboxCreated = true;
    if (mode === 'input-created') initial.inputSchemaCreated = true;
    if (mode === 'runtime-stage') initial.stage = 'preflight';
    if (mode === 'runtime-child') initial.childState = 'started';
    if (mode === 'persistence-failed') initial.persistence = 'failed';
    await f.capsule.write(initial);
    await assert.rejects(f.finalize({ containment: mode === 'unknown-containment' ? 'unknown' : 'not_required', failure }),
      { code: mode === 'unknown-containment' ? 'CONTAINMENT_NOT_PROVEN' : 'RUNTIME_DIAGNOSTICS_FAILED' });
    const retained = await f.capsule.read();
    assert.equal(retained.childState, initial.childState);
    assert.equal(retained.persistence, initial.persistence);
    assert.ok(await openRuntimeDiagnostic({ executionId: 'run-39', root: f.fallbackRoot }));
  });
});

test('normal runtime retains original parse output and code-less exceptions while public details remain bounded references', async t => {
  for (const kind of ['invalid-json', 'uncoded-exception']) await t.test(kind, async t => {
    const f = await fixture(t); let failure;
    const override = kind === 'invalid-json'
      ? { spawnImpl: childFixture({ stdout: 'native invalid result token=hidden-value\n' }) }
      : { buildArgs() { throw new Error('original argument cause token=hidden-value'); } };
    await assert.rejects(runGovernedCodexTask({ ...f.options, ...override }), error => { failure = error; return true; });
    const saved = JSON.parse(await readFile(join(f.primaryRoot, 'run-39.json'), 'utf8'));
    assert.match(JSON.stringify(saved.causalEvidence), kind === 'invalid-json' ? /native invalid result/ : /original argument cause/);
    assert.doesNotMatch(JSON.stringify(saved), /hidden-value/);
    assert.doesNotMatch(JSON.stringify(failure.details), /native invalid result|original argument cause|hidden-value|causalEvidence/);
    assert.equal(saved.causalEvidence.executionId, 'run-39');
    assert.equal(saved.causalEvidence.operation, kind === 'invalid-json' ? 'result-parse' : 'build-arguments');
  });
});

test('original child evidence and independent recorder failure both survive a primary serializer failure', async t => {
  const f = await fixture(t);
  await assert.rejects(runGovernedCodexTask({ ...f.options,
    spawnImpl: childFixture({ code: 7, stderr: 'upstream failed at native boundary token=hidden-value\n' }),
    createDiagnostic() { throw Object.assign(new Error('serializer exhausted storage token=second-hidden'), { code: 'ENOSPC' }); }
  }), { code: 'CODEX_NONZERO_EXIT' });
  const record = await f.capsule.read();
  assert.match(record.causalEvidence.stderr.text, /upstream failed at native boundary/);
  assert.match(record.recorderFailure.exception.text, /serializer exhausted storage|ENOSPC/);
  assert.doesNotMatch(JSON.stringify(record), /hidden-value|second-hidden/);
  assert.equal(record.persistence, 'failed'); assert.equal(record.cleanup, 'retained');
  assert.equal(record.causalEvidence.operation, 'child-result');
  assert.ok((await stat(join(f.cwd, '.codex-sandbox'))).isDirectory());
});

test('native structured errors without a message survive normal capture independently of semantic result', async t => {
  const f = await fixture(t);
  await assert.rejects(runGovernedCodexTask({ ...f.options, spawnImpl: childFixture({ code: 1,
    stdout: JSON.stringify({ type: 'error', error: { code: 'NATIVE_POLICY_DENIED', status: 403, token: 'native-private' } }) + '\n'
  }) }), { code: 'CODEX_NONZERO_EXIT' });
  const saved = JSON.parse(await readFile(join(f.primaryRoot, 'run-39.json'), 'utf8'));
  assert.match(saved.codexErrors.events[0].native.text, /NATIVE_POLICY_DENIED|403/);
  assert.doesNotMatch(JSON.stringify(saved), /native-private/);
});

test('runtime stream errors are captured with their original cause and retain unknown containment', async t => {
  const f = await fixture(t);
  let failure;
  await assert.rejects(runGovernedCodexTask({ ...f.options, spawnImpl() {
    const child = new EventEmitter(); child.stdout = new PassThrough(); child.stderr = new PassThrough(); child.pid = 4242;
    setImmediate(() => child.stdout.emit('error', Object.assign(new Error('read pipe broke'), { code: 'EIO', syscall: 'read' })));
    return child;
  } }), error => { failure = error; return error.code === 'CODEX_STREAM_FAILED'; });
  const record = await f.capsule.read();
  assert.match(record.causalEvidence.exception.text, /read pipe broke|EIO/);
  assert.equal(f.options.evidence.codexContainment, 'unknown');
  assert.doesNotMatch(JSON.stringify(failure.details), /read pipe broke/);
});
test('observed native errors remain durable after successful recovery without changing semantic success', async t => {
  const f = await fixture(t);
  const stdout = JSON.stringify({ type: 'error', message: 'native request temporarily unavailable token=private-fixture' }) + '\n'
    + JSON.stringify({ type: 'task_result', result: { status: 'success', summary: 'recovered', validation: [], blockedReason: '' } }) + '\n';
  const result = await runGovernedCodexTask({ ...f.options, spawnImpl: childFixture({ stdout }) });
  assert.equal(result.status, 'success'); assert.equal(result.summary, 'recovered');
  const state = await f.capsule.read(); assert.equal(state.persistence, 'stored');
  assert.match(state.causalEvidence.native.text, /native request temporarily unavailable/);
  assert.doesNotMatch(JSON.stringify(state), /private-fixture/);
});
