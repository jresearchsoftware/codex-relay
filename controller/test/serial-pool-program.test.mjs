import test from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { PassThrough, Writable } from 'node:stream';
import { spawn, execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { copyFile, readFile, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { historicalProgram, originalProgram } from '../src/serial-pool-program.mjs';
import { loadSerialPoolCompatibility, protectedSourceTreeSha256 } from '../src/serial-pool-compatibility.mjs';
import { serialPoolFixture } from './serial-pool-fixture.mjs';

const executeFile = promisify(execFile);
const linux = process.platform === 'linux';
const moduleRoot = fileURLToPath(new URL('../..', import.meta.url));
const fakeContext = { original: { sourceRoot: '/opt/relay/releases/' + 'a'.repeat(40) + '/reviewed-source',
  consumerPath: '/etc/relay/serial-consumer-v1.json' } };
function fakeExecution({ stdout = '{}', stderr = '', code = 0, neverClose = false } = {}) {
  const calls = []; let killed = 0;
  const execute = (command, args, options) => {
    const child = new EventEmitter(); child.stdout = new PassThrough(); child.stderr = new PassThrough();
    const chunks = [];
    child.kill = () => { killed++; queueMicrotask(() => child.emit('close', null, 'SIGTERM')); };
    child.stdin = new Writable({ write(chunk, _encoding, callback) { chunks.push(chunk); callback(); },
      final(callback) {
        calls.push({ command, args, options, input: JSON.parse(Buffer.concat(chunks)) }); callback();
        queueMicrotask(() => {
          child.stdout.write(stdout); child.stderr.write(stderr);
          if (!neverClose) child.emit('close', code);
        });
      } });
    return child;
  };
  return { execute, calls, killed: () => killed };
}
function route(f, overrides = {}) {
  return { consumer: f.currentConsumer, consumerPath: f.consumerPath,
    env: { RELAY_CALLER_UID: String(f.receipt.original.runnerUid) },
    load: options => loadSerialPoolCompatibility({ ...f.options, ...options, root: f.root, ownerUid: f.options.ownerUid }), ...overrides };
}

test('fixed original program preserves duplicate receipts and only recreates the permitted environment', async () => {
  const result = { status: 'DUPLICATE_SUPPRESSED', repository: 'example-org/sample-project', outcome: { id: 72, sha256: 'a'.repeat(64) } };
  const fake = fakeExecution({ stdout: JSON.stringify(result), stderr: 'private diagnostic sentinel' });
  assert.deepEqual(await originalProgram(fakeContext, 'manual-outcome', { run_id: 100 }, { execute: fake.execute,
    env: { HOME: '/home/runner', NODE_OPTIONS: '--import=/foreign/code.mjs', RELAY_CONSUMER_CONFIG: '/foreign/consumer.json',
      RELAY_EXECUTION_SLOT: 'pool-2', RELAY_CALLER_UID: '1000', GITHUB_TOKEN: 'synthetic-read-token', UNRELATED_SECRET: 'private sentinel' } }), result);
  const call = fake.calls[0];
  assert.equal(call.command, '/usr/bin/node');
  assert.deepEqual(call.args, [join(fakeContext.original.sourceRoot, 'controller/src/manual-outcome-helper.mjs')]);
  assert.equal(call.options.env.RELAY_CONSUMER_CONFIG, fakeContext.original.consumerPath);
  assert.equal(call.options.env.RELAY_CALLER_UID, '1000'); assert.equal(call.options.env.GITHUB_TOKEN, 'synthetic-read-token');
  for (const key of ['NODE_OPTIONS', 'UNRELATED_SECRET', 'RELAY_EXECUTION_SLOT']) assert.equal(call.options.env[key], undefined);
});

for (const stdout of ['[]', 'null', 'true', '"private diagnostic sentinel"', '{}\nnot-json', '{"status":"ok","status":"bad"}']) {
  test(`malformed original receipt is rejected (${stdout.slice(0, 12)}) without diagnostic leakage`, async () => {
    const fake = fakeExecution({ stdout, stderr: 'private diagnostic sentinel' });
    await assert.rejects(originalProgram(fakeContext, 'writer', {}, { execute: fake.execute }), error => {
      assert.equal(error.code, 'SERIAL_POOL_ORIGINAL_PROGRAM_UNAVAILABLE');
      assert.ok(!JSON.stringify(error).includes('private diagnostic sentinel')); return true;
    });
  });
}

test('failed original programs expose only fixed public codes; bounds terminate the subprocess', async () => {
  for (const stderr of ['private diagnostic sentinel', '{"code":"private diagnostic sentinel"}', '{"code":"AUTHORITY_CHANGED","detail":"private diagnostic sentinel"}']) {
    const fake = fakeExecution({ stdout: '', stderr, code: 1 });
    await assert.rejects(originalProgram(fakeContext, 'writer', {}, { execute: fake.execute }), error => {
      assert.equal(error.code, stderr.includes('AUTHORITY_CHANGED') ? 'AUTHORITY_CHANGED' : 'SERIAL_POOL_ORIGINAL_PROGRAM_UNAVAILABLE');
      assert.ok(!JSON.stringify(error).includes('private diagnostic sentinel')); return true;
    });
  }
  const oversized = fakeExecution({ stdout: 'x'.repeat(65) });
  await assert.rejects(originalProgram(fakeContext, 'writer', {}, { execute: oversized.execute, maxOutput: 64 }),
    { code: 'SERIAL_POOL_ORIGINAL_PROGRAM_UNAVAILABLE' });
  assert.equal(oversized.killed(), 1);
  const stalled = fakeExecution({ neverClose: true });
  await assert.rejects(originalProgram(fakeContext, 'writer', {}, { execute: stalled.execute, timeoutMs: 10 }),
    { code: 'SERIAL_POOL_ORIGINAL_PROGRAM_UNAVAILABLE' });
  assert.equal(stalled.killed(), 1);
  await assert.rejects(originalProgram(fakeContext, 'writer', {}, { execute: () => { throw new Error('private diagnostic sentinel'); } }),
    { code: 'SERIAL_POOL_ORIGINAL_PROGRAM_UNAVAILABLE' });
});

test('historical root dispatch validates both stores, strips only the transport slot, and leaves current runs for current Writer', { skip: !linux }, async t => {
  const f = await serialPoolFixture(t); let invoked = 0;
  const request = { operation: 'publication-state', runId: 99, attemptId: 'run-99', executionSlot: 'pool-2', authorizationId: 19 };
  const before = await readFile(join((await f.load()).original.storeRoot, '99.json'));
  const result = await historicalProgram({ ...route(f), kind: 'writer', request,
    invoke: async (context, kind, input) => { invoked++; assert.equal(kind, 'writer'); assert.equal(context.original.consumerPath, f.oldConsumerPath);
      assert.deepEqual(input, { operation: 'publication-state', runId: 99, attemptId: 'run-99', authorizationId: 19 }); return { repository: f.receipt.repository }; } });
  assert.equal(result.handled, true); assert.equal(invoked, 1);
  assert.equal(request.executionSlot, 'pool-2'); assert.deepEqual(await readFile(join((await f.load()).original.storeRoot, '99.json')), before);
  assert.deepEqual(await historicalProgram({ ...route(f), kind: 'writer', request: { ...request, runId: 200, attemptId: 'run-200' },
    invoke: async () => assert.fail('Current run must remain in current Writer') }), { handled: false });
  await f.originalStore.put(103, { envelope: f.envelope(103) });
  await assert.rejects(historicalProgram({ ...route(f), kind: 'writer', request: { ...request, runId: 200 }, invoke: async () => assert.fail() }),
    { code: 'SERIAL_POOL_COMPATIBILITY_RUN_SET_CHANGED' });
});

test('old inference, ordinary automatic completion and wrong caller UID never invoke original programs', { skip: !linux }, async t => {
  const f = await serialPoolFixture(t);
  for (const operation of ['admit', 'preflight', 'publish-progress', 'handoff', 'dispatch', 'finish-no-change', 'terminal-outcome', 'observe-readiness']) {
    await assert.rejects(historicalProgram({ ...route(f), kind: 'writer', request: { operation, runId: 99, attemptId: 'run-99' },
      invoke: async () => assert.fail('Historical execution cannot run') }));
  }
  await assert.rejects(historicalProgram({ ...route(f, { env: { RELAY_CALLER_UID: String(f.receipt.original.runnerUid + 1) } }),
    kind: 'writer', request: { operation: 'publication-state', runId: 99, attemptId: 'run-99' }, invoke: async () => assert.fail() }),
  { code: 'SERIAL_POOL_ORIGINAL_RUNNER_IDENTITY_REQUIRED' });
  await assert.rejects(historicalProgram({ ...route(f), kind: 'writer', request: { operation: 'finish', runId: 99, attemptId: 'run-99' }, invoke: async () => assert.fail() }),
    { code: 'RECOVERED_OUTCOME_REQUIRED' });
  const record = structuredClone(f.records[0]); record.publishedHead = 'd'.repeat(40);
  record.publicationRecoveries = [{ authorizationId: 19, result: { status: 'PUBLISHED', publishedHead: record.publishedHead } }];
  await f.originalStore.put(99, record);
  assert.equal((await historicalProgram({ ...route(f), kind: 'writer', request: { operation: 'finish', runId: 99, attemptId: 'run-99', recoveryAuthorizationId: 19 },
    invoke: async () => ({ status: 'IMPLEMENTED_PENDING_FRESH_REVIEW' }) })).handled, true);
});

test('manual socket route preserves original duplicate result without granting ordinary Writer the capability', { skip: !linux }, async t => {
  const f = await serialPoolFixture(t); const submission = { repository: f.receipt.repository, task: 42, run_id: 100,
    result: { attempt: 'run-100', parent: { kind: 'issue', number: 42 } } };
  const expected = { status: 'DUPLICATE_SUPPRESSED', run_id: 100, repository: f.receipt.repository, outcome: { id: 15, sha256: 'b'.repeat(64) } };
  const fake = fakeExecution({ stdout: JSON.stringify(expected) });
  const result = await historicalProgram({ ...route(f, { env: {} }), kind: 'manual-outcome', request: submission,
    invoke: (context, kind, input, options) => originalProgram(context, kind, input, { ...options, execute: fake.execute }) });
  assert.deepEqual(result, { handled: true, value: expected }); assert.deepEqual(fake.calls[0].input, submission);
  assert.equal(fake.calls[0].args[0], join(f.sourceRoot, 'controller/src/manual-outcome-helper.mjs'));
  await assert.rejects(historicalProgram({ ...route(f), kind: 'writer', request: { operation: 'manual-outcome-direct', runId: 100 }, invoke: async () => assert.fail() }),
    { code: 'MANUAL_CAPABILITY_REQUIRED' });
});

test('unprivileged recovery uses public membership without opening private stores', { skip: !linux || process.getuid?.() === 0 }, async t => {
  const f = await serialPoolFixture(t); const ctx = await f.load();
  await rm(ctx.original.storeRoot, { recursive: true }); await rm(ctx.current.storeRoot, { recursive: true }); await rm(f.gatePath);
  const expected = { repository: f.receipt.repository, runId: 99, attemptId: 'run-99' };
  assert.deepEqual(await historicalProgram({ ...route(f), kind: 'publication-recovery', request: { operation: 'inspect', runId: 99, attemptId: 'run-99' },
    invoke: async (_context, kind, input) => { assert.equal(kind, 'publication-recovery'); assert.equal(input.operation, 'inspect'); return expected; } }),
  { handled: true, value: expected });
  await assert.rejects(historicalProgram({ ...route(f), kind: 'writer', request: { operation: 'publication-state', runId: 99, attemptId: 'run-99' } }));
});

test('actual archived recovery entrypoint rejects invalid requests without launching inference', { skip: !linux }, async t => {
  const f = await serialPoolFixture(t); const ctx = await f.load(); let invocations = 0;
  await assert.rejects(originalProgram(ctx, 'publication-recovery', { operation: 'inspect', runId: 'invalid', attemptId: 'run-99' }, {
    execute: (command, args, options) => { invocations++; assert.equal(command, '/usr/bin/node');
      assert.equal(args[0], join(f.sourceRoot, 'controller/src/recover-attempt-publication.mjs'));
      return spawn(process.execPath, args, options); }
  }), { code: 'RECOVERY_REQUEST_INVALID' });
  assert.equal(invocations, 1);
});

test('real archived Writer broker reads and replays the original envelope in its isolated module graph', { skip: !linux }, async t => {
  const f = await serialPoolFixture(t); const ctx = await f.load();
  const before = await readFile(join(ctx.original.storeRoot, '99.json'));
  // A test driver supplies the protected store and rejects all native mutation
  // dependencies; validation/dispatch itself is the unmodified archived broker.
  const driver = `
    import {pathToFileURL} from 'node:url';
    const root=${JSON.stringify(f.sourceRoot)};
    const {createPublicationBroker}=await import(pathToFileURL(root+'/controller/src/publication-broker.mjs'));
    const {createAttemptStore}=await import(pathToFileURL(root+'/controller/src/attempt-store.mjs'));
    const chunks=[];for await(const chunk of process.stdin)chunks.push(chunk);
    const unexpected=()=>{throw Error('UNEXPECTED_MUTATION_OR_NETWORK')};
    const broker=createPublicationBroker({store:createAttemptStore(${JSON.stringify(ctx.original.storeRoot)}),
      api:new Proxy({},{get:()=>unexpected}),publisher:new Proxy({},{get:()=>unexpected})});
    process.stdout.write(JSON.stringify(await broker.dispatch(JSON.parse(Buffer.concat(chunks)))));`;
  const options = route(f, { invoke: (context, kind, input, dependencies) => originalProgram(context, kind, input, {
    ...dependencies, execute: (_command, _args, childOptions) => spawn(process.execPath, ['--input-type=module', '-e', driver], childOptions) }) });
  const request = { operation: 'publication-state', runId: 99, attemptId: 'run-99', executionSlot: 'pool-2' };
  const first = await historicalProgram({ ...options, kind: 'writer', request });
  const second = await historicalProgram({ ...options, kind: 'writer', request });
  assert.deepEqual(first, second); assert.equal(first.handled, true);
  assert.deepEqual(first.value.envelope, f.records[0].envelope);
  assert.equal(first.value.envelope.consumerDigest, f.receipt.original.consumerDigest);
  assert.notEqual(first.value.envelope.consumerDigest, f.receipt.target.consumerDigest);
  assert.deepEqual(await readFile(join(ctx.original.storeRoot, '99.json')), before);
});

test('retained release containing the adapter verifies its exact graph before preserving original SERIAL context', { skip: !linux }, async t => {
  const f = await serialPoolFixture(t);
  await copyFile(join(moduleRoot, 'controller/src/serial-pool-compatibility.mjs'), join(f.sourceRoot, 'controller/src/serial-pool-compatibility.mjs'));
  f.receipt.original.sourceTreeSha256 = await protectedSourceTreeSha256(f.sourceRoot, f.options);
  await f.write(f.receiptPath, f.receipt, 0o644);
  await assert.rejects(loadSerialPoolCompatibility({ ...f.options, consumerPath: f.oldConsumerPath, consumer: undefined }),
    { code: 'SERIAL_POOL_COMPATIBILITY_ORIGINAL_CONTEXT_INVALID' });
  const script = `
    import {pathToFileURL} from 'node:url';
    const value=JSON.parse(process.argv[1]);process.env.RELAY_CONSUMER_CONFIG=value.consumerPath;
    const module=await import(pathToFileURL(value.sourceRoot+'/controller/src/serial-pool-compatibility.mjs'));
    const result=await module.loadSerialPoolCompatibility(value.options);
    process.stdout.write(JSON.stringify({originalContext:result===null}));`;
  const payload = { consumerPath: f.oldConsumerPath, sourceRoot: f.sourceRoot,
    options: { ...f.options, consumerPath: f.oldConsumerPath, consumer: undefined } };
  const result = await executeFile(process.execPath, ['--input-type=module', '-e', script, JSON.stringify(payload)]);
  assert.deepEqual(JSON.parse(result.stdout), { originalContext: true });
  // Before backend publication the sibling consumer is still the exact old
  // SERIAL snapshot. Only this sealed original graph can operate its closed
  // gate during that bounded transition; current routing remains unavailable.
  await f.write(f.consumerPath, await readFile(f.oldConsumerPath), 0o644);
  const beforeCutover = await executeFile(process.execPath, ['--input-type=module', '-e', script, JSON.stringify(payload)]);
  assert.deepEqual(JSON.parse(beforeCutover.stdout), { originalContext: true });
  await assert.rejects(f.load());
  await f.write(f.consumerPath, f.currentConsumer, 0o644);
  await f.write(f.at(f.receipt.original.configPath), '{}\n');
  await assert.rejects(executeFile(process.execPath, ['--input-type=module', '-e', script, JSON.stringify(payload)]));
});
