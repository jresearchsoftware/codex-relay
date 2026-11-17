import { constants } from 'node:fs';
import { mkdir, open, rmdir } from 'node:fs/promises';
import { spawn } from 'node:child_process';
import { createBoundedUtf8Capture } from './utf8-capture.mjs';

const failure = code => Object.assign(new Error(code), { code });

// The child owns a kernel lock until its stdin closes. Parent death closes the
// pipe too; no stale PID lease or recovery generation can authorize execution.
// Locks protect trusted stores only, never a worker-selected path.
export async function withStoreLock(path, action, { waitSeconds = 0, busyCode = 'STORE_LOCK_BUSY', spawnImpl = spawn } = {}) {
  if (!Number.isInteger(waitSeconds) || waitSeconds < 0 || waitSeconds > 60) throw failure('STORE_LOCK_WAIT_INVALID');
  if (process.platform === 'win32') {
    // Local Windows contract tests only. Runtime/storage boundaries use Linux.
    const end = Date.now() + waitSeconds * 1000;
    for (;;) {
      try { await mkdir(path, { mode: 0o700 }); break; }
      catch (error) {
        if (error.code !== 'EEXIST') throw error;
        if (Date.now() >= end) throw failure(busyCode);
        await new Promise(resolve => setTimeout(resolve, 10));
      }
    }
    try { return await action(); } finally { await rmdir(path); }
  }
  const descriptor = await open(path, constants.O_RDWR | constants.O_CREAT | constants.O_NOFOLLOW, 0o600);
  try {
    const stat = await descriptor.stat();
    if (!stat.isFile() || stat.nlink !== 1 || stat.uid !== process.getuid() || (stat.mode & 0o077)) throw Object.assign(failure('STORE_LOCK_UNSAFE'), {
      observation: { check: 'store-lock-file', expected: { type: 'file', links: 1, uid: process.getuid(), private: true },
        observed: { type: stat.isFile() ? 'file' : 'other', links: stat.nlink, uid: stat.uid, mode: stat.mode & 0o777 } } });
    const program = "process.stdin.resume();process.stdin.once('end',()=>process.exit(0));process.stdout.write('locked\\n');";
    const child = spawnImpl('/usr/bin/flock', ['-w', String(waitSeconds), '-E', '75', '/proc/self/fd/3', process.execPath, '-e', program],
      { env: { PATH: '/usr/bin:/bin', LANG: 'C', LC_ALL: 'C' }, stdio: ['pipe', 'pipe', 'pipe', descriptor.fd], windowsHide: true });
    const stdout = createBoundedUtf8Capture(4096), stderr = createBoundedUtf8Capture(4096);
    child.stdout.on('data', data => stdout.push(data)); child.stderr?.on('data', data => stderr.push(data));
    let streamError;
    const observedFailure = (code, cause, exit = {}) => {
      const error = Object.assign(new Error(code, { cause }), { code });
      Object.defineProperty(error, 'native', { value: { operation: 'store-lock', stdout: stdout.finish(), stderr: stderr.finish(),
        exitCode: exit.code, signal: exit.signal, waitSeconds,
        ...(streamError ? { streamError: { name: streamError.name, code: streamError.code, message: streamError.message, stack: streamError.stack } } : {}) }, writable: true, configurable: true });
      return error;
    };
    let ready = false;
    const closed = new Promise(resolve => child.once('close', (code, signal) => resolve({ code, signal })));
    await new Promise((resolve, reject) => {
      child.once('error', error => reject(observedFailure('STORE_LOCK_FAILED', error)));
      for (const stream of [child.stdin, child.stdout, child.stderr]) stream?.on('error', error => {
        streamError ??= error;
        if (!ready) reject(observedFailure('STORE_LOCK_FAILED', error));
      });
      child.stdout.once('data', data => {
        if (data.toString() !== 'locked\n') reject(observedFailure('STORE_LOCK_FAILED'));
        else { ready = true; resolve(); }
      });
      child.once('close', (code, signal) => { if (!ready) reject(observedFailure(code === 75 ? busyCode : 'STORE_LOCK_FAILED', streamError, { code, signal })); });
    });
    let actionError;
    try { return await action(); }
    catch (error) { actionError = error; throw error; }
    finally {
      child.stdin.end();
      const exit = await closed;
      if (exit.code !== 0 || streamError) throw observedFailure('STORE_LOCK_RELEASE_FAILED', actionError ?? streamError, exit);
    }
  } finally { await descriptor.close(); }
}
