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
const envelope = { version: 2, consumerDigest: CONSUMER_DIGEST, repository: REPOSITORY, attemptId: 'run-9', step: 2, runId: 9,
  target: 'issue', number: 42, issueNumber: 42, route: 'auto', branch: 'codex/test', subagentsAllowed: true,
  startHead: 'a'.repeat(40), historicalBase: 'a'.repeat(40), targetBase: 'b'.repeat(40), authorityDigest: 'c'.repeat(64), profile: { cliModelId: 'fixture-model', effort: 'high' }, validation: ['diff-check'] };
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
    reserveDiagnostic: async () => handle,
    finalizeArtifacts: async () => ({ cleanup: 'complete', persistence: 'not_required', retention: 'none' }),
    ...options });
}
test('real bounded dispatcher process returns the same attempt envelope without publication credentials', async () => {
  const dispatcher = fixture({ spawnImpl: launch(`const e=JSON.parse(require('node:fs').readFileSync(0,'utf8'));writeSync(1, JSON.stringify({version:e.version,attemptId:e.attemptId,child:'started',result:{status:'blocked'}}));`) });
  const value = await dispatcher.dispatch(envelope);
  assert.equal(value.attemptId, envelope.attemptId); assert.equal(value.containment, 'reaped');
});
test('a failed process with unparseable stderr retains unknown child evidence', async () => {
  const dispatcher = fixture({ spawnImpl: launch("process.stdin.resume(); process.stdin.on('end',()=>{writeSync(2, 'non-diagnostic failure');process.exitCode=1;});") });
  await assert.rejects(dispatcher.dispatch(envelope), error => {
    assert.equal(error.details.childState, 'unknown'); assert.equal(error.details.containment, 'reaped'); return true;
  });
});
test('native process timeout is bounded and cannot be relabeled not_started', async () => {
  let finalized;
  const dispatcher = fixture({ timeoutMs: 100, spawnImpl: launch('process.stdin.resume(); setInterval(()=>{},1000);'),
    finalizeArtifacts: async value => { finalized = value; return { cleanup: 'retained', retention: 'retained' }; } });
  await assert.rejects(dispatcher.dispatch(envelope), error => {
    assert.equal(error.code, 'EXECUTION_TIMEOUT'); assert.equal(error.details.childState, 'unknown'); return true;
  });
  assert.equal(finalized.failure.code, 'EXECUTION_TIMEOUT'); assert.equal(finalized.containment, 'reaped');
});

test('cancellation reaps the dispatcher before durable finalization', async () => {
  let finalized;
  const start = launch('process.stdin.resume(); setInterval(()=>{},1000);');
  const dispatcher = fixture({ spawnImpl: (...args) => {
    const child = start(...args);
    child.once('spawn', () => setImmediate(() => process.emit('SIGTERM')));
    return child;
  }, finalizeArtifacts: async value => { finalized = value; return { cleanup: 'retained', retention: 'retained' }; } });
  await assert.rejects(dispatcher.dispatch(envelope), { code: 'EXECUTION_CANCELLED' });
  assert.equal(finalized.failure.code, 'EXECUTION_CANCELLED'); assert.equal(finalized.containment, 'reaped');
  assert.equal(finalized.failure.childState, 'unknown');
});
test('an unsupported required validation stops before the process boundary', async () => {
  const dispatcher = fixture({ spawnImpl: () => assert.fail('must not start') });
  await assert.rejects(dispatcher.dispatch({ ...envelope, validation: ['custom-unknown-check'] }), { code: 'REQUIRED_VALIDATION_UNSUPPORTED' });
});
test('dispatcher refuses unresolved permission rather than supplying another default', async () => {
  const dispatcher = fixture({ spawnImpl: () => assert.fail('must not start') });
  for (const subagentsAllowed of [undefined, null, 'Off', 0]) {
    await assert.rejects(dispatcher.dispatch({ ...envelope, subagentsAllowed }), { code: 'SUBAGENTS_PERMISSION_INVALID' });
  }
});
test('specific safe worker failure and known cause survive the dispatcher', async () => {
  const dispatcher = fixture({ spawnImpl: launch(`process.stdin.resume(); process.stdin.on('end',()=>{writeSync(2, JSON.stringify({version:2,status:'blocked',code:'CODEX_RESULT_MISSING',diagnostic:{observed:{child:'started'},primaryCause:'CODEX_RESULT_MISSING'}}));process.exitCode=1;});`) });
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

test('successful process cannot hide a cleanup failure', async () => {
  const dispatcher = fixture({
    spawnImpl: launch(`const e=JSON.parse(require('node:fs').readFileSync(0,'utf8'));writeSync(1, JSON.stringify({version:e.version,attemptId:e.attemptId,child:'started',result:{status:'success'}}));`),
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
    spawnImpl: launch(`process.stdin.resume(); process.stdin.on('end',()=>{writeSync(2, JSON.stringify({version:2,status:'blocked',code:'CODEX_RESULT_MISSING',diagnostic:{observed:{child:'started'},primaryCause:'CODEX_RESULT_MISSING'}}));process.exitCode=1;});`),
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
  await assert.rejects(dispatcher.dispatch(envelope), { code: 'EXECUTION_FAILED' });
  const reopened = await openRuntimeDiagnostic({ executionId: envelope.attemptId, root });
  const capsule = await reopened.read();
  assert.equal(capsule.failureDiagnostic.code, 'EXECUTION_FAILED');
  assert.equal(capsule.failureDiagnostic.dispatcherExitCode, 9);
  assert.equal(capsule.failureDiagnostic.childExitCode, undefined);
  assert.equal(capsule.containment, 'reaped'); assert.equal(capsule.retention, 'retained');
  assert.equal(capsule.cleanup, 'retained');
  const saved = await readFile(join(root, String(reopened.reference.slot), `${envelope.attemptId}.json`), 'utf8');
  assert.ok(Buffer.byteLength(saved) < 16 * 1024);
});
