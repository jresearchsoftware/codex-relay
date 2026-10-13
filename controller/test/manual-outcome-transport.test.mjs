import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:net';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { submit } from '../src/manual-outcome-client.mjs';

// Native Unix-socket client qualification. This does not install or impersonate
// a root Writer service, publish GitHub content, or read any credential file.
const native = { skip: process.platform === 'win32' };
async function socketFixture(t, receive) {
  const root = await mkdtemp(join(tmpdir(), 'relay-manual-transport-'));
  const socketPath = join(root, 'writer.sock');
  const connections = new Set();
  const server = createServer({ allowHalfOpen: true }, socket => {
    connections.add(socket);
    socket.on('error', () => {});
    socket.on('close', () => connections.delete(socket));
    receive(socket);
  });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(socketPath, resolve); });
  t.after(async () => {
    for (const connection of connections) connection.destroy();
    await new Promise(resolve => server.close(resolve));
    await rm(root, { recursive: true, force: true });
  });
  return socketPath;
}

test('native socket sends exact complete JSON then reads a bounded split receipt', native, async t => {
  const request = Buffer.from(JSON.stringify({ repository: 'example-org/project', task: 42, run_id: 123,
    result: { summary: 'Complete evidence <>&: Unicode λ', limitations: ['No installed proof.'] } }));
  const response = Buffer.from('{"status":"PUBLISHED","outcome":{"id":321}}\n');
  let received;
  const path = await socketFixture(t, socket => {
    const chunks = [];
    socket.on('data', chunk => chunks.push(chunk));
    socket.on('end', () => { received = Buffer.concat(chunks); socket.write(response.subarray(0, 11)); socket.end(response.subarray(11)); });
  });
  assert.deepEqual(await submit(path, request), response);
  assert.deepEqual(received, request);
});

test('native socket bounds input before connection and accepts the full limit', native, async t => {
  let connects = 0; let received = 0;
  const path = await socketFixture(t, socket => {
    connects++;
    socket.on('data', chunk => { received += chunk.length; });
    socket.on('end', () => socket.end('bounded'));
  });
  await assert.rejects(submit(path, Buffer.alloc(100 * 1024 + 1)), /MANUAL_SUBMISSION_INVALID/);
  assert.equal(connects, 0);
  assert.equal((await submit(path, Buffer.alloc(100 * 1024))).toString(), 'bounded');
  assert.equal(received, 100 * 1024);
});

test('native socket accepts 32 KiB receipt and rejects excess without returning a prefix', native, async t => {
  let count = 0;
  const path = await socketFixture(t, socket => {
    socket.resume();
    socket.on('end', () => socket.end(Buffer.alloc(32 * 1024 + count++, 'x')));
  });
  assert.equal((await submit(path, Buffer.from('{}'))).length, 32 * 1024);
  await assert.rejects(submit(path, Buffer.from('{}')), /MANUAL_RECEIPT_INVALID/);
});

test('native socket timeout reports uncertainty and terminates the connection', native, async t => {
  const path = await socketFixture(t, socket => socket.resume());
  await assert.rejects(submit(path, Buffer.from('{}'), { timeoutMs: 25 }), /MANUAL_PUBLICATION_UNCERTAIN/);
});

test('client rejects unsafe internal socket paths and preserves unavailable transport', native, async t => {
  for (const path of ['relative.sock', '/tmp/../writer.sock', undefined]) {
    await assert.rejects(submit(path, Buffer.from('{}')), /MANUAL_SUBMISSION_INVALID/);
  }
  const root = await mkdtemp(join(tmpdir(), 'relay-manual-unavailable-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  await assert.rejects(submit(join(root, 'missing.sock'), Buffer.from('{}')), { code: 'ENOENT' });
});

test('fixed client CLI rejects extra arguments and oversized streamed input with only a public error', native, () => {
  const cli = fileURLToPath(new URL('../src/manual-outcome-client.mjs', import.meta.url));
  for (const [arguments_, input] of [[['operation=arbitrary'], 'private-input'], [[], Buffer.alloc(100 * 1024 + 1)]]) {
    const result = spawnSync(process.execPath, [cli, ...arguments_], { input, encoding: 'utf8',
      env: { PATH: '/usr/bin:/bin', RELAY_MANUAL_OUTCOME_SOCKET: '/nonexistent-fixed-fixture.sock' }, timeout: 5000 });
    assert.equal(result.status, 1);
    assert.equal(result.stderr, '');
    assert.deepEqual(JSON.parse(result.stdout), { error_code: 'MANUAL_PUBLICATION_UNCERTAIN' });
  }
});

test('manual root helper refuses a nonroot caller before Writer access', { skip: process.platform === 'win32' || process.getuid?.() === 0 }, () => {
  const helper = fileURLToPath(new URL('../src/manual-outcome-helper.mjs', import.meta.url));
  const config = fileURLToPath(new URL('../../consumer/fixtures/example.json', import.meta.url));
  for (const arguments_ of [[], ['arbitrary-operation']]) {
    const result = spawnSync(process.execPath, [helper, ...arguments_], { input: '{}', encoding: 'utf8',
      env: { PATH: '/usr/bin:/bin', RELAY_CONSUMER_CONFIG: config }, timeout: 5000 });
    assert.equal(result.status, 1);
    assert.equal(result.stderr, '');
    assert.deepEqual(JSON.parse(result.stdout), { error_code: 'FIXED_ROOT_BROKER_REQUIRED' });
  }
});
