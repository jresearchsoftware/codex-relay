import { CONSUMER } from '../../consumer/consumer.mjs';
import { spawn as nodeSpawn } from 'node:child_process';
import { createBoundedUtf8Capture } from './utf8-capture.mjs';
import { VERSION, validateEnvelope } from './execution-contract.mjs';
import { reserveRuntimeDiagnostic } from './diagnostic-fallback.mjs';
import { failureDiagnosticFromDetails } from './diagnostics.mjs';
import { finalizeRuntimeArtifacts } from '../../runtime/src/runtime-finalization.mjs';
import { normalizeCodexUsage } from './codex-usage.mjs';
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


export function createOnDemandDispatchAdapter({ spawnImpl = nodeSpawn, timeoutMs = 100 * 60 * 1000,
  reserveDiagnostic = reserveRuntimeDiagnostic, finalizeArtifacts = finalizeRuntimeArtifacts } = {}) {
  return {
    async dispatch(envelope) {
      validateEnvelope(envelope);
      // Reserve independent durable evidence before the process can create any
      // mutable attempt state. Failure to reserve must never launch a child.
      let fallbackStore;
      try { fallbackStore = await reserveDiagnostic({ executionId: envelope.attemptId }); }
      catch (error) {
        const code = /^[A-Z][A-Z0-9_]{0,79}$/.test(error?.code ?? '') ? error.code : 'DIAGNOSTIC_FALLBACK_FAILED';
        throw Object.assign(new Error(code), { code, details: {
          executionId: envelope.attemptId, childState: 'not_started', containment: 'not_required',
          primaryCause: code, stage: 'diagnostic-persistence', boundary: 'diagnostic-persistence',
          operation: 'reserve-fallback', persistence: 'failed', cleanup: 'not_required', retention: 'none',
          fallbackReference: { status: 'unavailable', executionId: envelope.attemptId, code } } });
      }
      let child;
      const stdout = createBoundedUtf8Capture(512 * 1024);
      const stderr = createBoundedUtf8Capture(64 * 1024);
      let closed = false; let timedOut = false; let cancelled = false; let termination; let spawnFailed = false;
      let value; let pendingError; let exit; let exitSignal; let processError; let runtimeLifecycle;
      let codexUsage = normalizeCodexUsage();
      let containment = 'not_required';
      const reap = () => termination ??= terminateProcessTree(child, [], () => closed);
      const onSignal = () => { cancelled = true; void reap(); };
      try {
        await fallbackStore.write({ stage: 'dispatcher', operation: 'dispatch', childState: 'unknown',
          containment: 'unknown', cleanup: 'pending', persistence: 'pending', retention: 'unknown' });
        try {
          child = spawnImpl(CONSUMER.paths.dispatch, [], {
            env: { PATH: '/usr/bin:/bin', LANG: 'C', LC_ALL: 'C' },
            stdio: ['pipe', 'pipe', 'pipe'], detached: process.platform !== 'win32', windowsHide: true });
        } catch (error) {
          processError = error;
          throw Object.assign(new Error('DISPATCH_NOT_STARTED'), { code: 'DISPATCH_NOT_STARTED',
            details: { childState: 'not_started', containment: 'not_required', primaryCause: error?.code,
              syscall: error?.syscall, operation: 'dispatch', boundary: 'dispatcher' } });
        }
        containment = 'unknown';
        process.once('SIGTERM', onSignal); process.once('SIGINT', onSignal);
        exit = await new Promise(resolve => {
          const timer = setTimeout(async () => { timedOut = true; await reap(); resolve(null); }, timeoutMs);
          child.stdout?.on('data', c => stdout.push(c)); child.stderr?.on('data', c => stderr.push(c));
          child.once('error', error => { processError = error; spawnFailed = !child.pid; clearTimeout(timer); resolve(null); });
          child.once('close', (code, signal) => { closed = true; exitSignal = signal; clearTimeout(timer); resolve(code); });
          child.stdin?.once('error', () => {}); child.stdin?.end(JSON.stringify(envelope));
        });
        const contained = await reap();
        containment = contained ? 'reaped' : 'unknown';
        const out = stdout.finish(); const err = stderr.finish();
        let diagnostic; let workerCode;
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
            codexUsage: normalizeCodexUsage(err.truncated ? undefined : diagnostic?.codexUsage),
            childState: spawnFailed ? 'not_started' : diagnostic?.observed?.child ?? 'unknown', containment,
            primaryCause: diagnostic?.primaryCause ?? processError?.code ?? null, syscall: processError?.syscall,
            operation: 'dispatch', boundary: diagnostic?.failureBoundary ?? 'dispatcher' } });
        }
        codexUsage = normalizeCodexUsage(value.codexUsage);
      } catch (error) { pendingError = error; }
      finally {
        process.removeListener('SIGTERM', onSignal); process.removeListener('SIGINT', onSignal);
        if (child && !termination) {
          try { containment = await reap() ? 'reaped' : 'unknown'; }
          catch { containment = 'unknown'; }
        }
        const failure = pendingError ? failureDiagnosticFromDetails({ ...pendingError.details,
          executionId: envelope.attemptId, code: pendingError.code, operation: 'dispatch', stage: 'dispatcher',
          childState: pendingError.details?.childState ?? (child ? 'unknown' : 'not_started'),
          childExitCode: pendingError.details?.causal?.observed?.exitCode,
          dispatcherExitCode: exit, dispatcherSignal: exitSignal, containment },
        { fallbackCode: pendingError.code ?? 'EXECUTION_FAILED' }) : undefined;
        let lifecycle;
        try {
          // The finalizer re-reads the runtime capsule. Do not replace its
          // primary evidence with the dispatcher's initial reservation state.
          lifecycle = await finalizeArtifacts({ executionId: envelope.attemptId, containment, fallbackStore, failure });
          runtimeLifecycle = lifecycle;
        } catch (error) {
          lifecycle = error.details ?? {};
          if (!pendingError) pendingError = error;
        }
        if (pendingError) {
          const original = pendingError.details ?? {};
          pendingError.details = { ...original, ...lifecycle, executionId: envelope.attemptId, containment,
            codexUsage: normalizeCodexUsage(original.codexUsage ?? codexUsage),
            childState: original.childState ?? (child ? value?.child ?? 'unknown' : 'not_started'),
            primaryCause: original.primaryCause ?? lifecycle?.primaryCause,
            ...(original.causal ? { causal: original.causal } : {}),
            failureDiagnostic: { ...lifecycle?.failureDiagnostic, ...original.failureDiagnostic, code: pendingError.code,
              ...(original.primaryCause ? { primaryCause: original.primaryCause,
                ...(original.boundary ? { boundary: original.boundary } : {}) } : {}) } };
        }
      }
      if (pendingError) throw pendingError;
      return { ...value, codexUsage: normalizeCodexUsage(value.codexUsage), containment: 'reaped', runtimeLifecycle };
    }
  };
}
