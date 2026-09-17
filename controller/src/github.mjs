import { CONSUMER } from '../../consumer/consumer.mjs';
import { spawn as nodeSpawn } from 'node:child_process';
import { createBoundedUtf8Capture } from './utf8-capture.mjs';
import { VERSION, validateEnvelope, fail } from './execution-contract.mjs';
const TERMINATION_GRACE_MS = 5000;
function signalProcessGroup(pid, signal) {
  if (process.platform === "win32" || !pid) return;
  try { process.kill(-pid, signal); } catch {}
}

function signalProcessTree(child, signal, nestedProcessGroupPids = []) {
  if (process.platform !== "win32") {
    signalProcessGroup(child.pid, signal);
    for (const pid of nestedProcessGroupPids) signalProcessGroup(pid, signal);
    return;
  }
  try { child.kill?.(signal); } catch {}
}

function processGroupGone(pid) {
  if (process.platform === "win32" || !pid) return true;
  try { process.kill(-pid, 0); return false; } catch (error) { return error.code === "ESRCH"; }
}

function waitForOwnedExecution(child, nestedProcessGroupPids, timeoutMs, isChildClosed) {
  return new Promise(resolve => {
    const deadline = Date.now() + timeoutMs;
    const poll = () => {
      const childGone = isChildClosed() || child.exitCode !== null || child.signalCode !== null;
      // The fixed helper is the process-group leader. Its real worker must
      // remain in that same group, so cleanup does not depend on receiving a
      // best-effort worker PID registration frame before cancellation.
      const ownerGroupGone = process.platform === "win32" || processGroupGone(child.pid);
      const groupsGone = ownerGroupGone && nestedProcessGroupPids.every(processGroupGone);
      if (childGone && groupsGone) return resolve(true);
      if (Date.now() >= deadline) return resolve(false);
      setTimeout(poll, 25);
    };
    poll();
  });
}

async function terminateProcessTree(child, nestedProcessGroupPids, isChildClosed) {
  signalProcessTree(child, "SIGTERM", nestedProcessGroupPids);
  if (await waitForOwnedExecution(child, nestedProcessGroupPids, TERMINATION_GRACE_MS, isChildClosed)) return true;
  signalProcessTree(child, "SIGKILL", nestedProcessGroupPids);
  return await waitForOwnedExecution(child, nestedProcessGroupPids, TERMINATION_GRACE_MS, isChildClosed);
}


export function createOnDemandDispatchAdapter({ spawnImpl = nodeSpawn, timeoutMs = 100 * 60 * 1000 } = {}) {
  return {
    async dispatch(envelope) {
      validateEnvelope(envelope);
      let child;
      try {
        child = spawnImpl(CONSUMER.paths.dispatch, [], {
          env: { PATH: '/usr/bin:/bin', LANG: 'C', LC_ALL: 'C' },
          stdio: ['pipe', 'pipe', 'pipe'], detached: process.platform !== 'win32', windowsHide: true });
      } catch { throw Object.assign(new Error('DISPATCH_NOT_STARTED'), { code: 'DISPATCH_NOT_STARTED', details: { childState: 'not_started', containment: 'not_required' } }); }
      const stdout = createBoundedUtf8Capture(512 * 1024);
      const stderr = createBoundedUtf8Capture(64 * 1024);
      let closed = false; let timedOut = false; let cancelled = false; let termination; let spawnFailed = false;
      const reap = () => termination ??= terminateProcessTree(child, [], () => closed);
      const onSignal = () => { cancelled = true; void reap(); };
      process.once('SIGTERM', onSignal); process.once('SIGINT', onSignal);
      let exit;
      try {
        exit = await new Promise(resolve => {
          const timer = setTimeout(async () => { timedOut = true; await reap(); resolve(null); }, timeoutMs);
          child.stdout?.on('data', c => stdout.push(c)); child.stderr?.on('data', c => stderr.push(c));
          child.once('error', () => { spawnFailed = !child.pid; clearTimeout(timer); resolve(null); });
          child.once('close', code => { closed = true; clearTimeout(timer); resolve(code); });
          child.stdin?.once('error', () => {}); child.stdin?.end(JSON.stringify(envelope));
        });
        const contained = await reap();
        const out = stdout.finish(); const err = stderr.finish();
        let value; let diagnostic; let workerCode;
        try { value = JSON.parse(out.value); } catch { /* unknown */ }
        try {
          const failure = JSON.parse(err.value);
          if (failure.version === VERSION && failure.status === 'blocked' && /^[A-Z][A-Z0-9_]{0,79}$/.test(failure.code ?? '')) {
            diagnostic = failure.diagnostic; workerCode = failure.code;
          }
        } catch { /* unknown */ }
        if (!contained || timedOut || cancelled || exit !== 0 || out.truncated || value?.version !== VERSION || value?.attemptId !== envelope.attemptId) {
          const code = !contained ? 'CONTAINMENT_NOT_PROVEN' : timedOut ? 'EXECUTION_TIMEOUT' : cancelled ? 'EXECUTION_CANCELLED' : (workerCode ?? 'EXECUTION_FAILED');
          throw Object.assign(new Error(code), { code, details: { causal: diagnostic, executionId: envelope.attemptId,
            childState: spawnFailed ? 'not_started' : diagnostic?.observed?.child ?? 'unknown', containment: contained ? 'reaped' : 'unknown', primaryCause: diagnostic?.primaryCause ?? null } });
        }
        return { ...value, containment: 'reaped' };
      } finally { process.removeListener('SIGTERM', onSignal); process.removeListener('SIGINT', onSignal); }
    }
  };
}
