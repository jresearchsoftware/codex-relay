import { lstat } from 'node:fs/promises';
import { spawn } from 'node:child_process';
import { CONSUMER } from '../../consumer/consumer.mjs';
import { createBoundedUtf8Capture } from '../../controller/src/utf8-capture.mjs';

export async function captureSandboxIdentity(sandboxRoot) {
  const entry = await lstat(sandboxRoot, { bigint: true });
  if (!entry.isDirectory() || entry.isSymbolicLink()) throw Object.assign(new Error('SANDBOX_CLEANUP_IDENTITY_INVALID'), { code: 'SANDBOX_CLEANUP_IDENTITY_INVALID' });
  return { device: String(entry.dev), inode: String(entry.ino) };
}

// Call only after durable diagnostics and proven containment. The installed
// fixed helper validates the direct attempt checkout and original inode itself.
export async function cleanupCodexSandbox({ cwd, sandboxIdentity, spawnImpl = spawn, timeoutMs = 40000 } = {}) {
  if (!/^[0-9]{1,20}$/.test(sandboxIdentity?.device ?? '') || !/^[1-9][0-9]{0,19}$/.test(sandboxIdentity?.inode ?? '')) {
    throw Object.assign(new Error('SANDBOX_CLEANUP_IDENTITY_INVALID'), { code: 'SANDBOX_CLEANUP_IDENTITY_INVALID', cleanupContainment: 'not_required' });
  }
  if (!Number.isSafeInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > 40000) throw new Error('Invalid cleanup timeout');
  let child;
  try { child = spawnImpl('/usr/bin/sudo', ['-n', '-u', CONSUMER.runtimeUser, CONSUMER.paths.launcher,
    'cleanup', '--cwd', cwd, '--sandbox-identity', `${sandboxIdentity.device}:${sandboxIdentity.inode}`], {
    env: { PATH: '/usr/bin:/bin', LANG: 'C', LC_ALL: 'C' }, stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true
  }); } catch (error) { error.cleanupContainment = 'not_required'; throw error; }
  const stdout = createBoundedUtf8Capture(4096);
  child.stdout?.on('data', chunk => stdout.push(chunk));
  child.stderr?.on('data', () => {}); // Raw sudo errors are not publication input.
  const code = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      // A stuck helper must not stall the durable terminal result indefinitely.
      // Killing its launcher is best effort, not proof that a descendant reaped.
      try { child.kill('SIGKILL'); } catch { /* retain unknown cleanup containment */ }
      child.stdout?.destroy(); child.stderr?.destroy(); child.unref?.();
      reject(Object.assign(new Error('SANDBOX_CLEANUP_TIMEOUT'), { code: 'SANDBOX_CLEANUP_TIMEOUT',
        operation: 'cleanup-helper', path: '.codex-sandbox', cleanupContainment: 'unknown' }));
    }, timeoutMs);
    child.once('error', error => { clearTimeout(timer); error.cleanupContainment = child.pid ? 'unknown' : 'not_required'; reject(error); });
    child.once('close', value => { clearTimeout(timer); resolve(value); });
  });
  const output = stdout.finish();
  let receipt;
  try { if (!output.truncated) receipt = JSON.parse(output.value); } catch { /* bounded failure below */ }
  if (code === 0 && receipt?.schemaVersion === 1 && receipt.status === 'removed') return receipt;
  const safeCode = /^[A-Z][A-Z0-9_]{0,79}$/.test(receipt?.code ?? '') ? receipt.code : 'SANDBOX_CLEANUP_FAILED';
  const error = Object.assign(new Error(safeCode), { code: safeCode, cleanupContainment: Number.isInteger(code) ? 'reaped' : 'unknown' });
  // Helper emits fixed operation names and hashes arbitrary filenames.
  if (/^(?:open|stat|fstat|scandir|readdir|unlink|rmdir|fsync)$/.test(receipt?.syscall ?? '')) error.syscall = receipt.syscall;
  if (/^[a-z-]{1,40}$/.test(receipt?.operation ?? '')) error.operation = receipt.operation;
  if (/^\.codex-sandbox(?:\/(?:home|config|cache|data|state|tmp|arg0|task-input\.md|codex-result-schema\.json|<entry-[a-f0-9]{12}>)){0,8}$/.test(receipt?.path ?? '')) error.path = receipt.path;
  throw error;
}
