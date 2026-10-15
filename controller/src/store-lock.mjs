import { constants } from 'node:fs';
import { mkdir, open, rmdir } from 'node:fs/promises';
import { spawn } from 'node:child_process';

const failure = code => Object.assign(new Error(code), { code });

// The child owns a kernel lock until its stdin closes. Parent death closes the
// pipe too; no stale PID lease or recovery generation can authorize execution.
// Locks protect trusted stores only, never a worker-selected path.
export async function withStoreLock(path, action, { waitSeconds = 0, busyCode = 'STORE_LOCK_BUSY' } = {}) {
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
    if (!stat.isFile() || stat.nlink !== 1 || stat.uid !== process.getuid() || (stat.mode & 0o077)) throw failure('STORE_LOCK_UNSAFE');
    const program = "process.stdin.resume();process.stdin.once('end',()=>process.exit(0));process.stdout.write('locked\\n');";
    const child = spawn('/usr/bin/flock', ['-w', String(waitSeconds), '-E', '75', '/proc/self/fd/3', process.execPath, '-e', program],
      { env: { PATH: '/usr/bin:/bin', LANG: 'C', LC_ALL: 'C' }, stdio: ['pipe', 'pipe', 'ignore', descriptor.fd], windowsHide: true });
    let ready = false;
    const closed = new Promise(resolve => child.once('close', code => resolve(code)));
    await new Promise((resolve, reject) => {
      child.once('error', () => reject(failure('STORE_LOCK_FAILED')));
      child.stdout.once('data', data => {
        if (data.toString() !== 'locked\n') reject(failure('STORE_LOCK_FAILED'));
        else { ready = true; resolve(); }
      });
      child.once('close', code => { if (!ready) reject(failure(code === 75 ? busyCode : 'STORE_LOCK_FAILED')); });
    });
    try { return await action(); }
    finally {
      child.stdin.end();
      if (await closed !== 0) throw failure('STORE_LOCK_RELEASE_FAILED');
    }
  } finally { await descriptor.close(); }
}
