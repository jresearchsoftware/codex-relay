import test from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { PassThrough } from 'node:stream';
import { mkdtemp, mkdir, rm, symlink } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { CONSUMER } from '../../consumer/consumer.mjs';
import { captureSandboxIdentity, cleanupCodexSandbox } from '../src/sandbox-cleanup.mjs';

test('sandbox identity capture rejects redirected roots and preserves integer precision', async t => {
  const root = await mkdtemp(join(tmpdir(), 'sandbox-cleanup-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const sandbox = join(root, '.codex-sandbox');
  await mkdir(sandbox);
  const identity = await captureSandboxIdentity(sandbox);
  assert.match(identity.device, /^[0-9]+$/); assert.match(identity.inode, /^[1-9][0-9]*$/);
  await symlink(sandbox, join(root, 'redirect'));
  await assert.rejects(captureSandboxIdentity(join(root, 'redirect')), { code: 'SANDBOX_CLEANUP_IDENTITY_INVALID' });
});

test('hung cleanup force-settles without claiming descendant containment or retrying', async () => {
  let calls = 0; let killed = 0;
  await assert.rejects(cleanupCodexSandbox({ cwd: '/fixture/work/run-39',
    sandboxIdentity: { device: '1', inode: '2' }, timeoutMs: 5,
    spawnImpl() {
      calls++;
      const child = new EventEmitter(); child.stdout = new PassThrough(); child.stderr = new PassThrough();
      child.kill = signal => { assert.equal(signal, 'SIGKILL'); killed++; };
      // No close event: model a stuck sudo/launcher rather than a clean exit.
      return child;
    } }), error => {
    assert.equal(error.code, 'SANDBOX_CLEANUP_TIMEOUT');
    assert.equal(error.cleanupContainment, 'unknown');
    return true;
  });
  assert.equal(calls, 1); assert.equal(killed, 1);
});

test('cleanup crosses only the fixed runtime UID boundary with bounded sanitized failures', async () => {
  const cwd = '/fixture/work/run-39';
  const sandboxIdentity = { device: '123', inode: '9007199254740993' };
  const invoke = receipt => cleanupCodexSandbox({ cwd, sandboxIdentity, spawnImpl(command, args, options) {
    assert.equal(command, '/usr/bin/sudo');
    assert.deepEqual(args, ['-n', '-u', CONSUMER.runtimeUser, CONSUMER.paths.launcher,
      'cleanup', '--cwd', cwd, '--sandbox-identity', '123:9007199254740993']);
    assert.deepEqual(options.env, { PATH: '/usr/bin:/bin', LANG: 'C', LC_ALL: 'C' });
    const child = new EventEmitter(); child.stdout = new PassThrough(); child.stderr = new PassThrough();
    setImmediate(() => { child.stdout.end(JSON.stringify(receipt)); child.emit('close', receipt.status === 'removed' ? 0 : 1); });
    return child;
  } });
  assert.equal((await invoke({ schemaVersion: 1, status: 'removed' })).status, 'removed');
  await assert.rejects(invoke({ schemaVersion: 1, status: 'retained', code: 'EACCES', syscall: 'open', operation: 'open-directory', path: '.codex-sandbox/home/tmp/arg0' }), error => {
    assert.equal(error.code, 'EACCES'); assert.equal(error.syscall, 'open'); assert.equal(error.operation, 'open-directory'); assert.equal(error.path, '.codex-sandbox/home/tmp/arg0'); return true;
  });
  await assert.rejects(invoke({ code: 'secret\nvalue', operation: 'raw request body', path: '/outside/credential' }), error => {
    assert.equal(error.code, 'SANDBOX_CLEANUP_FAILED'); assert.equal(error.syscall, undefined); assert.equal(error.path, undefined); return true;
  });
  await assert.rejects(cleanupCodexSandbox({ cwd, sandboxIdentity: { device: '../escape', inode: '1' }, spawnImpl() { assert.fail('invalid identity started helper'); } }), { code: 'SANDBOX_CLEANUP_IDENTITY_INVALID' });
});
