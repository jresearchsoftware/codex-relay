import { currentEnvelope } from './fixture.mjs';
import { CONSUMER_DIGEST } from '../../consumer/consumer.mjs';
import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createOnDemandDispatchAdapter } from '../src/github.mjs';
import { REPOSITORY } from '../src/execution-contract.mjs';
import { reserveRuntimeDiagnostic, openRuntimeDiagnostic } from '../src/diagnostic-fallback.mjs';
import { finalizeRuntimeArtifacts } from '../../runtime/src/runtime-finalization.mjs';
const envelope = currentEnvelope({ version: 2, consumerDigest: CONSUMER_DIGEST, repository: REPOSITORY, attemptId: 'run-9', step: 2, runId: 9,
  target: 'issue', number: 42, issueNumber: 42, route: 'auto', branch: 'codex/test', subagentsAllowed: true,
  startHead: 'a'.repeat(40), historicalBase: 'a'.repeat(40), targetBase: 'b'.repeat(40), authorityDigest: 'c'.repeat(64), profile: { cliModelId: 'fixture-model', effort: 'high' }, validation: ['diff-check'] });
function launch(code) {
  return (command, args, options) => {
    assert.equal(command, '/opt/relay-example/relay-codex-dispatch'); assert.deepEqual(args, []);
    assert.equal(options.env.GITHUB_TOKEN, undefined); assert.equal(options.env.workflowReadToken, undefined);
    // Emit deterministic fixture bytes through the actual descriptors. This
    // also works when a sandbox restricts Node's socket-backed stdio wrappers.
    return spawn(process.execPath, ['-e', `const { writeSync } = require('node:fs'); ${code}`], options);
  };
}
function fixture(options = {}) {
  let capsule;
  const handle = { reference: { status: 'stored', executionId: envelope.attemptId, slot: 0 },
    async read() { return capsule; }, async write(value) { capsule = value; }, async release() {} };
  return createOnDemandDispatchAdapter({
    diagnosticStore: async value => ({ status: 'stored', executionId: value.executionId, mode: value.mode }),
    readDiagnosticConfig: async () => ({ mode: 'normal' }),
    reserveDiagnostic: async () => handle,
    finalizeArtifacts: async () => ({ cleanup: 'complete', persistence: 'not_required', retention: 'none' }),
    ...options });
}
test('real bounded dispatcher process returns the same attempt envelope without publication credentials', async () => {
  const dispatcher = fixture({ spawnImpl: launch(`const e=JSON.parse(require('node:fs').readFileSync(0,'utf8'));writeSync(1, JSON.stringify({version:e.version,attemptId:e.attemptId,child:'started',containment:'reaped',result:{status:'blocked'}}));`) });
  const value = await dispatcher.dispatch(envelope);
  assert.equal(value.attemptId, envelope.attemptId); assert.equal(value.containment, 'reaped');
});
test('a failed process with unparseable stderr retains unknown child evidence', async () => {
  const dispatcher = fixture({ spawnImpl: launch("process.stdin.resume(); process.stdin.on('end',()=>{writeSync(2, 'non-diagnostic failure');process.exitCode=1;});") });
  await assert.rejects(dispatcher.dispatch(envelope), error => {
    assert.equal(error.details.childState, 'unknown'); assert.equal(error.details.containment, 'unknown'); return true;
  });
});
test('native process timeout is bounded and cannot be relabeled not_started', async () => {
  let finalized;
  const dispatcher = fixture({ timeoutMs: 100, spawnImpl: launch('process.stdin.resume(); setInterval(()=>{},1000);'),
    finalizeArtifacts: async value => { finalized = value; return { cleanup: 'retained', retention: 'retained' }; } });
  await assert.rejects(dispatcher.dispatch(envelope), error => {
    assert.equal(error.code, 'CONTAINMENT_NOT_PROVEN'); assert.equal(error.details.childState, 'unknown'); return true;
  });
  assert.equal(finalized.failure.code, 'CONTAINMENT_NOT_PROVEN'); assert.equal(finalized.containment, 'unknown');
});

test('cancellation without model-UID acknowledgement retains unknown containment', async () => {
  let finalized;
  const start = launch('process.stdin.resume(); setInterval(()=>{},1000);');
  const dispatcher = fixture({ spawnImpl: (...args) => {
    const child = start(...args);
    child.once('spawn', () => setImmediate(() => process.emit('SIGTERM')));
    return child;
  }, finalizeArtifacts: async value => { finalized = value; return { cleanup: 'retained', retention: 'retained' }; } });
  await assert.rejects(dispatcher.dispatch(envelope), { code: 'CONTAINMENT_NOT_PROVEN' });
  assert.equal(finalized.failure.code, 'CONTAINMENT_NOT_PROVEN'); assert.equal(finalized.containment, 'unknown');
  assert.equal(finalized.failure.childState, 'unknown');
});
test('an unsupported required validation stops before the process boundary', async () => {
  const dispatcher = fixture({ spawnImpl: () => assert.fail('must not start') });
  await assert.rejects(dispatcher.dispatch({ ...envelope, validation: ['custom-unknown-check'] }), { code: 'REQUIRED_VALIDATION_UNSUPPORTED' });
});
test('cooperative cancellation requires the inner receipt before durable finalization', async () => {
  let finalized;
  const start = launch(`
    process.stdin.resume(); const hold=setInterval(()=>{},1000);
    process.on('SIGTERM',()=>{
      writeSync(2,JSON.stringify({version:2,status:'blocked',code:'EXECUTION_CANCELLED',
        diagnostic:{containment:'reaped',observed:{child:'started'}}}));
      clearInterval(hold);process.stdin.destroy();process.exitCode=1;
    });writeSync(1,'READY');`);
  const dispatcher = fixture({ spawnImpl: (...args) => {
    const child = start(...args); child.stdout.once('data', () => process.emit('SIGINT')); return child;
  }, finalizeArtifacts: async value => { finalized = value; return { cleanup: 'retained', retention: 'retained' }; } });
  await assert.rejects(dispatcher.dispatch(envelope), { code: 'EXECUTION_CANCELLED' });
  assert.equal(finalized.containment, 'reaped'); assert.equal(finalized.failure.childState, 'started');
});
test('an already cancelled controller never launches another dispatcher', async () => {
  const cancellation = new AbortController(); cancellation.abort();
  const dispatcher = fixture({ signal: cancellation.signal, spawnImpl: () => assert.fail('must not launch') });
  await assert.rejects(dispatcher.dispatch(envelope), error => {
    assert.equal(error.code, 'EXECUTION_CANCELLED'); assert.equal(error.details.containment, 'not_required');
    assert.equal(error.details.childState, 'not_started'); return true;
  });
});
test('exit zero cannot replace an absent inner containment receipt', async () => {
  const dispatcher = fixture({ spawnImpl: launch(`const e=JSON.parse(require('node:fs').readFileSync(0,'utf8'));writeSync(1,JSON.stringify({version:2,attemptId:e.attemptId,child:'started',result:{status:'success'}}));`) });
  await assert.rejects(dispatcher.dispatch(envelope), error => {
    assert.equal(error.code, 'CONTAINMENT_NOT_PROVEN'); assert.equal(error.details.containment, 'unknown'); return true;
  });
});
test('dispatcher refuses unresolved permission rather than supplying another default', async () => {
  const dispatcher = fixture({ spawnImpl: () => assert.fail('must not start') });
  for (const subagentsAllowed of [undefined, null, 'Off', 0]) {
    await assert.rejects(dispatcher.dispatch({ ...envelope, subagentsAllowed }), { code: 'EXECUTION_ENVELOPE_INVALID' });
  }
});
test('specific safe worker failure and known cause survive the dispatcher', async () => {
  const dispatcher = fixture({ spawnImpl: launch(`process.stdin.resume(); process.stdin.on('end',()=>{writeSync(2, JSON.stringify({version:2,status:'blocked',code:'CODEX_RESULT_MISSING',diagnostic:{containment:'reaped',observed:{child:'started'},primaryCause:'CODEX_RESULT_MISSING'}}));process.exitCode=1;});`) });
  await assert.rejects(dispatcher.dispatch(envelope), error => {
    assert.equal(error.code, 'CODEX_RESULT_MISSING'); assert.equal(error.details.primaryCause, 'CODEX_RESULT_MISSING');
    assert.equal(error.details.childState, 'started'); assert.equal(error.details.containment, 'reaped'); return true;
  });
});

test('fallback admission fails closed before a dispatcher can start', async () => {
  const dispatcher = fixture({
    reserveDiagnostic: async () => { throw Object.assign(new Error('full'), { code: 'DIAGNOSTIC_RETENTION_LIMIT' }); },
    spawnImpl: () => assert.fail('must not start without durable reservation'),
    finalizeArtifacts: () => assert.fail('no attempt was reserved') });
  await assert.rejects(dispatcher.dispatch(envelope), error => {
    assert.equal(error.code, 'DIAGNOSTIC_RETENTION_LIMIT');
    assert.equal(error.details.childState, 'not_started'); assert.equal(error.details.containment, 'not_required');
    assert.equal(error.details.primaryCause, 'DIAGNOSTIC_RETENTION_LIMIT');
    assert.equal(error.details.operation, 'reserve-fallback'); return true;
  });
});

test('synchronous spawn failure reaches finalization with safe OS evidence and no child', async () => {
  let finalized;
  const dispatcher = fixture({
    spawnImpl: () => { throw Object.assign(new Error('private arbitrary text'), { code: 'EACCES', syscall: 'spawn', path: '/private/token' }); },
    finalizeArtifacts: async value => { finalized = value; return { cleanup: 'not_required', retention: 'none' }; } });
  await assert.rejects(dispatcher.dispatch(envelope), error => {
    assert.equal(error.code, 'DISPATCH_NOT_STARTED');
    assert.equal(error.details.childState, 'not_started');
    assert.equal(error.details.containment, 'not_required');
    return true;
  });
  assert.equal(finalized.failure.code, 'DISPATCH_NOT_STARTED');
  assert.equal(finalized.failure.primaryCause, 'EACCES');
  assert.equal(finalized.failure.syscall, 'spawn');
  assert.equal(finalized.failure.path, undefined);
  assert.doesNotMatch(JSON.stringify(finalized.failure), /private/);
});

test('asynchronous missing executable proves no child and retires only after durable failure evidence', async t => {
  const root = await mkdtemp(join(tmpdir(), 'relay-missing-dispatch-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  let archived;
  const dispatcher = fixture({
    reserveDiagnostic: value => reserveRuntimeDiagnostic({ ...value, root }),
    spawnImpl: (command, args, options) => spawn(join(root, 'missing-dispatch'), args, options),
    finalizeArtifacts: value => finalizeRuntimeArtifacts({ ...value,
      readDiagnosticConfig: async () => ({ mode: 'normal' }),
      diagnosticStore: async diagnostic => {
        archived = diagnostic;
        return { status: 'stored', mode: 'normal', executionId: diagnostic.executionId };
      }, cleanupSandbox: () => assert.fail('no runtime or sandbox existed') })
  });
  await assert.rejects(dispatcher.dispatch(envelope), error => {
    assert.equal(error.code, 'DISPATCH_NOT_STARTED');
    assert.equal(error.details.childState, 'not_started');
    assert.equal(error.details.containment, 'not_required');
    assert.equal(error.details.primaryCause, 'ENOENT');
    return true;
  });
  const handle = await openRuntimeDiagnostic({ executionId: envelope.attemptId, root, includeReleased: true });
  const capsule = await handle.read();
  assert.equal(capsule.released, true);
  assert.equal(capsule.terminalDiagnostic.status, 'stored');
  assert.equal(archived.lifecycle.failureDiagnostic.code, 'DISPATCH_NOT_STARTED');
  assert.equal(archived.lifecycle.failureDiagnostic.primaryCause, 'ENOENT');
});

test('successful process cannot hide a cleanup failure', async () => {
  const dispatcher = fixture({
    spawnImpl: launch(`const e=JSON.parse(require('node:fs').readFileSync(0,'utf8'));writeSync(1, JSON.stringify({version:e.version,attemptId:e.attemptId,child:'started',containment:'reaped',result:{status:'success'}}));`),
    finalizeArtifacts: async ({ containment, failure }) => {
      assert.equal(containment, 'reaped'); assert.equal(failure, undefined);
      throw Object.assign(new Error('cleanup failed'), { code: 'SANDBOX_CLEANUP_FAILED', details: {
        cleanup: 'failed', retention: 'retained', failureDiagnostic: { primaryCause: 'EPERM', boundary: 'cleanup' } } });
    } });
  await assert.rejects(dispatcher.dispatch(envelope), error => {
    assert.equal(error.code, 'SANDBOX_CLEANUP_FAILED'); assert.equal(error.details.childState, 'started');
    assert.equal(error.details.failureDiagnostic.primaryCause, 'EPERM');
    assert.equal(error.details.retention, 'retained'); return true;
  });
});

test('worker cause survives a later cleanup failure and both retain durable references', async () => {
  const reference = { status: 'stored', executionId: envelope.attemptId, slot: 1 };
  const dispatcher = fixture({
    spawnImpl: launch(`process.stdin.resume(); process.stdin.on('end',()=>{writeSync(2, JSON.stringify({version:2,status:'blocked',code:'CODEX_RESULT_MISSING',diagnostic:{containment:'reaped',observed:{child:'started'},primaryCause:'CODEX_RESULT_MISSING'}}));process.exitCode=1;});`),
    finalizeArtifacts: async ({ failure, containment }) => {
      assert.equal(containment, 'reaped'); assert.equal(failure.code, 'CODEX_RESULT_MISSING');
      throw Object.assign(new Error('cleanup failed'), { code: 'SANDBOX_CLEANUP_FAILED', details: {
        cleanup: 'failed', retention: 'retained', fallbackReference: reference,
        failureDiagnostic: { primaryCause: 'EACCES', boundary: 'cleanup' } } });
    } });
  await assert.rejects(dispatcher.dispatch(envelope), error => {
    assert.equal(error.code, 'CODEX_RESULT_MISSING');
    assert.equal(error.details.failureDiagnostic.primaryCause, 'CODEX_RESULT_MISSING');
    assert.equal(error.details.cleanup, 'failed'); assert.equal(error.details.retention, 'retained');
    assert.deepEqual(error.details.fallbackReference, reference); return true;
  });
});

test('dispatcher process crash leaves an independently readable durable capsule', async t => {
  const root = await mkdtemp(join(tmpdir(), 'relay-dispatch-capsule-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const dispatcher = fixture({
    reserveDiagnostic: value => reserveRuntimeDiagnostic({ ...value, root }),
    spawnImpl: launch('process.stdin.resume(); process.stdin.on("end",()=>process.exit(9));'),
    finalizeArtifacts: value => finalizeRuntimeArtifacts({ ...value,
      cleanupSandbox: () => assert.fail('unknown runtime state must retain artifacts') }) });
  await assert.rejects(dispatcher.dispatch(envelope), { code: 'CONTAINMENT_NOT_PROVEN' });
  const reopened = await openRuntimeDiagnostic({ executionId: envelope.attemptId, root });
  const capsule = await reopened.read();
  assert.equal(capsule.failureDiagnostic.code, 'CONTAINMENT_NOT_PROVEN');
  assert.equal(capsule.failureDiagnostic.dispatcherExitCode, 9);
  assert.equal(capsule.failureDiagnostic.childExitCode, undefined);
  assert.equal(capsule.containment, 'unknown'); assert.equal(capsule.retention, 'retained');
  assert.equal(capsule.cleanup, 'retained');
  const saved = await readFile(join(root, String(reopened.reference.slot), `${envelope.attemptId}.json`), 'utf8');
  assert.ok(Buffer.byteLength(saved) < 16 * 1024);
});


test('contained cleanup failure preserves the semantic result with an explicit retained-resource warning', async () => {
  const dispatcher = fixture({
    spawnImpl: launch(`const e=JSON.parse(require('node:fs').readFileSync(0,'utf8'));writeSync(1, JSON.stringify({version:e.version,attemptId:e.attemptId,child:'started',containment:'reaped',result:{status:'success'}}));`),
    finalizeArtifacts: async () => {
      throw Object.assign(new Error('cleanup failed'), { code: 'SANDBOX_CLEANUP_FAILED', details: {
        cleanup: 'failed', cleanupContainment: 'reaped', persistence: 'stored', retention: 'retained',
        fallbackReference: { status: 'stored', executionId: envelope.attemptId, slot: 0 } } });
    } });
  const result = await dispatcher.dispatch(envelope);
  assert.equal(result.result.status, 'success');
  assert.deepEqual(result.executionWarnings, ['RUNTIME_CLEANUP_FAILED']);
  assert.equal(result.runtimeLifecycle.retention, 'retained');
});


test('automatic dispatch default follows the scrubbed worker budget rather than the controller environment', async t => {
  const old = process.env.CODEX_RUNTIME_TIMEOUT_MS;
  process.env.CODEX_RUNTIME_TIMEOUT_MS = '1000';
  t.after(() => { if (old === undefined) delete process.env.CODEX_RUNTIME_TIMEOUT_MS; else process.env.CODEX_RUNTIME_TIMEOUT_MS = old; });
  const delays = [], nativeTimer = globalThis.setTimeout;
  t.mock.method(globalThis, 'setTimeout', (callback, delay, ...args) => {
    delays.push(delay);
    return nativeTimer(callback, delay, ...args);
  });
  const start = launch(`const e=JSON.parse(require('node:fs').readFileSync(0,'utf8'));writeSync(1, JSON.stringify({version:e.version,attemptId:e.attemptId,child:'started',containment:'reaped',result:{status:'success'}}));`);
  const dispatcher = fixture({ spawnImpl: (command, args, options) => {
    assert.equal(options.env.CODEX_RUNTIME_TIMEOUT_MS, undefined);
    return start(command, args, options);
  } });
  assert.equal((await dispatcher.dispatch(envelope)).result.status, 'success');
  assert.ok(delays.includes(100 * 60 * 1000), JSON.stringify(delays));
  assert.ok(!delays.includes(1000 + 10 * 60 * 1000), JSON.stringify(delays));
});

test('dispatch preserves malformed native output plus recorder failure before finalization and excludes it from public details', async t => {
  const root = await mkdtemp(join(tmpdir(), 'relay-dispatch-causal-')); t.after(() => rm(root, { recursive: true, force: true }));
  let handle; let beforeFinalization;
  const dispatcher = fixture({ reserveDiagnostic: async options => handle = await reserveRuntimeDiagnostic({ ...options, root }),
    diagnosticStore: async () => { throw Object.assign(new Error('primary filesystem unavailable'), { code: 'ENOSPC' }); },
    spawnImpl: launch('require("node:fs").readFileSync(0);writeSync(1,"{native malformed response token=private-fixture");writeSync(2,"transport error at boundary");process.exitCode=2;'),
    finalizeArtifacts: async () => { beforeFinalization = await handle.read(); return { cleanup: 'retained', retention: 'retained' }; }
  });
  await assert.rejects(dispatcher.dispatch(envelope), error => {
    assert.doesNotMatch(JSON.stringify(error.details), /native malformed|transport error|private-fixture/);
    return error.code === 'CONTAINMENT_NOT_PROVEN';
  });
  assert.match(beforeFinalization.causalEvidence.stdout.text, /native malformed response/);
  assert.match(beforeFinalization.causalEvidence.stderr.text, /transport error at boundary/);
  assert.match(beforeFinalization.causalEvidence.exception.text, /SyntaxError/);
  assert.match(beforeFinalization.recorderFailure.exception.text, /primary filesystem unavailable|ENOSPC/);
  assert.equal(beforeFinalization.causalEvidence.process.exitCode, 2);
  assert.doesNotMatch(JSON.stringify(beforeFinalization), /private-fixture/);
});
test('containment group probe exceptions survive as protected observations without proving absence', async t => {
  const originalKill = process.kill;
  let probeFailed = false; let saved;
  t.mock.method(process, 'kill', function(pid, signal) {
    if (signal === 0 && !probeFailed) {
      probeFailed = true; throw Object.assign(new Error('group existence probe denied'), { code: 'EPERM', syscall: 'kill' });
    }
    return originalKill.call(process, pid, signal);
  });
  const dispatcher = fixture({
    diagnosticStore: async value => { saved = value; return { status: 'stored', executionId: value.executionId, mode: value.mode }; },
    spawnImpl: launch('require("node:fs").readFileSync(0);writeSync(2,JSON.stringify({version:2,status:"blocked",code:"CODEX_RESULT_MISSING",diagnostic:{containment:"reaped",observed:{child:"started"}}}));process.exitCode=1;')
  });
  await assert.rejects(dispatcher.dispatch(envelope), error => {
    assert.equal(error.code, 'CODEX_RESULT_MISSING');
    assert.doesNotMatch(JSON.stringify(error.details), /group existence probe denied/); return true;
  });
  assert.equal(probeFailed, true);
  assert.match(saved.causalEvidence.native.text, /probe-dispatch-group|group existence probe denied/);
});
