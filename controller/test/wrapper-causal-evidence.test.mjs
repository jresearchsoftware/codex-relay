import test from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { PassThrough } from 'node:stream';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { createAttemptStore } from '../src/attempt-store.mjs';
import { originalProgram } from '../src/serial-pool-program.mjs';
import { assertPredispatchTargetCompatible } from '../src/predispatch-target-compatibility.mjs';
import { runConsumerPreflightProgram } from '../src/consumer-preflight-cli.mjs';
import { withStoreLock } from '../src/store-lock.mjs';
import { captureCausalDiagnostic } from '../src/diagnostics.mjs';

const context = { original: { sourceRoot: '/fixture/accepted', consumerPath: '/fixture/consumer.json' } };
function processFixture(run) {
  const child = new EventEmitter(); child.stdout = new PassThrough(); child.stderr = new PassThrough(); child.stdin = new PassThrough();
  child.stdin.resume(); child.kill = () => true;
  setImmediate(() => run(child)); return child;
}

test('attempt journal parsing preserves original exception through direct reads and handled scans', async t => {
  const root = await mkdtemp(join(tmpdir(), 'relay-wrapper-store-')); t.after(() => rm(root, { recursive: true, force: true }));
  await writeFile(join(root, '244.json'), '{original malformed record token=private-fixture');
  const recorded = [];
  const store = createAttemptStore(root, { recordFailure: async (error, operation) => {
    recorded.push(captureCausalDiagnostic({ error, operation })); return { status: 'stored', executionId: 'host-fixture' };
  } });
  await assert.rejects(store.get(244), error => error.code === 'ATTEMPT_RECORD_UNREADABLE' && error.cause instanceof SyntaxError);
  const rows = await store.scan();
  assert.equal(rows[0].error, 'ATTEMPT_RECORD_UNREADABLE'); assert.ok(rows[0].cause.cause instanceof SyntaxError);
  assert.match(recorded[0].exception.text, /SyntaxError/);
  assert.doesNotMatch(JSON.stringify(rows), /original malformed record|SyntaxError|private-fixture/);
  await assert.rejects(store.all(), error => error.cause.cause instanceof SyntaxError);
});

test('original compatibility process failure retains native output, exit and signal behind unchanged public code', async () => {
  await assert.rejects(originalProgram(context, 'writer', {}, { execute() {
    return processFixture(child => {
      child.stdout.end('{invalid original response'); child.stderr.end('native original failure token=private-fixture');
      child.emit('close', 9, 'SIGTERM');
    });
  } }), error => {
    assert.equal(error.code, 'SERIAL_POOL_ORIGINAL_PROGRAM_UNAVAILABLE');
    const evidence = captureCausalDiagnostic({ error });
    assert.match(evidence.exception.text, /native original failure|invalid original response/);
    assert.doesNotMatch(JSON.stringify(evidence), /private-fixture/);
    assert.equal(error.native.exitCode, 9); assert.equal(error.native.signal, 'SIGTERM'); return true;
  });
});

test('compatibility process spawn and stream exceptions preserve their original native cause', async () => {
  for (const kind of ['spawn', 'stream']) await assert.rejects(originalProgram(context, 'writer', {}, { execute() {
    if (kind === 'spawn') throw Object.assign(new Error('original spawn denied'), { code: 'EACCES' });
    return processFixture(child => child.stdout.emit('error', Object.assign(new Error('original stream broke'), { code: 'EIO' })));
  } }), error => {
    assert.equal(error.code, 'SERIAL_POOL_ORIGINAL_PROGRAM_UNAVAILABLE');
    assert.equal(error.cause.code, kind === 'spawn' ? 'EACCES' : 'EIO'); return true;
  });
});

test('predispatch target wrapper preserves the protected filesystem failure without exposing it as public code', async t => {
  const root = await mkdtemp(join(tmpdir(), 'relay-wrapper-target-')); t.after(() => rm(root, { recursive: true, force: true }));
  await assert.rejects(assertPredispatchTargetCompatible({ records: [{ predispatchPending: {} }],
    target: 'a'.repeat(40), sourceRoot: join(root, 'missing'), root, ownerUid: process.getuid() }), error => {
    assert.equal(error.code, 'PREDISPATCH_TARGET_INCOMPATIBLE'); assert.equal(error.cause.code, 'ENOENT');
    assert.equal(error.observation.check, 'target-metadata'); return true;
  });
});

test('consumer bootstrap internal program retains original process output while keeping its domain classification', async () => {
  await assert.rejects(runConsumerPreflightProgram('/fixture/python', [], { spawnImpl() {
    return processFixture(child => {
      child.stderr.end('{"code":"CONSUMER_PREFLIGHT_WRITER_BUSY","native":{"message":"original native lock cause"}}');
      child.stdout.end(); child.emit('close', 40, null);
    });
  } }), error => {
    assert.equal(error.code, 'CONSUMER_PREFLIGHT_WRITER_BUSY');
    assert.match(captureCausalDiagnostic({ error }).exception.text, /original native lock cause/);
    assert.equal(error.native.exitCode, 40); return true;
  });
  await assert.rejects(runConsumerPreflightProgram('/fixture/python', [], { spawnImpl() {
    throw Object.assign(new Error('bootstrap spawn failed'), { code: 'ENOENT' });
  } }), error => error.code === 'CONSUMER_PREFLIGHT_EXECUTION_UNAVAILABLE' && error.cause.code === 'ENOENT');
});

test('lock helper failure preserves original stderr and exit without running the protected action', async t => {
  const root = await mkdtemp(join(tmpdir(), 'relay-wrapper-lock-')); t.after(() => rm(root, { recursive: true, force: true }));
  await assert.rejects(withStoreLock(join(root, 'lock'), () => assert.fail('busy lock must not run action'), {
    busyCode: 'ATTEMPT_CONTROLLER_BUSY', spawnImpl() {
      return processFixture(child => { child.stderr.end('native flock contention token=private-fixture'); child.emit('close', 75, null); });
    }
  }), error => {
    assert.equal(error.code, 'ATTEMPT_CONTROLLER_BUSY'); assert.equal(error.native.exitCode, 75);
    const evidence = captureCausalDiagnostic({ error }); assert.match(evidence.exception.text, /native flock contention/);
    assert.doesNotMatch(JSON.stringify(evidence), /private-fixture/); return true;
  });
});
test('lock release keeps a stream failure and an earlier action cause independently', async t => {
  const root = await mkdtemp(join(tmpdir(), 'relay-wrapper-lock-release-')); t.after(() => rm(root, { recursive: true, force: true }));
  let child;
  const actionCause = Object.assign(new Error('original protected action failed'), { code: 'EIO' });
  await assert.rejects(withStoreLock(join(root, 'lock'), async () => {
    child.stdin.emit('error', Object.assign(new Error('lock lifetime pipe failed'), { code: 'EPIPE' }));
    child.emit('close', 0, null); throw actionCause;
  }, { spawnImpl() { child = processFixture(value => value.stdout.write('locked\n')); return child; } }), error => {
    assert.equal(error.code, 'STORE_LOCK_RELEASE_FAILED'); assert.equal(error.cause, actionCause);
    assert.match(captureCausalDiagnostic({ error }).exception.text, /original protected action failed|lock lifetime pipe failed/);
    assert.doesNotMatch(JSON.stringify(error), /original protected action failed|lock lifetime pipe failed/); return true;
  });
});
