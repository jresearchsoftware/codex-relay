import { CONSUMER } from '../../consumer/consumer.mjs';
import { join } from 'node:path';
import { openRuntimeDiagnostic } from '../../controller/src/diagnostic-fallback.mjs';
import { createExecutionDiagnostic, persistExecutionDiagnostic, safeFailureDiagnosticReference } from '../../controller/src/diagnostics.mjs';
import { cleanupCodexSandbox } from './sandbox-cleanup.mjs';
import { WriterBlockedError } from './contracts.mjs';

const safeCode = (error, fallback) => /^[A-Z][A-Z0-9_]{0,79}$/.test(error?.code ?? '') ? error.code : fallback;

// The caller owns and has reaped the dispatcher process group. Runtime code
// inside that group only prepares diagnostics; it cannot declare containment.
export async function finalizeRuntimeArtifacts({ executionId, containment, fallbackStore,
  failure, cleanupSandbox = cleanupCodexSandbox, diagnosticStore = persistExecutionDiagnostic,
  workRoot = CONSUMER.paths.workRoot } = {}) {
  const capsule = fallbackStore ?? await openRuntimeDiagnostic({ executionId });
  if (!capsule) throw new WriterBlockedError('RUNTIME_DIAGNOSTIC_MISSING', 'The runtime capsule is unavailable', {
    executionId, containment, cleanup: 'retained', retention: 'unknown', persistence: 'failed',
    fallbackReference: { status: 'unavailable', executionId, code: 'RUNTIME_DIAGNOSTIC_MISSING' } });
  let state;
  try { state = await capsule.read(); }
  catch (error) { throw new WriterBlockedError('RUNTIME_DIAGNOSTICS_FAILED', 'The runtime capsule cannot be read; artifacts are retained', {
    executionId, containment, cleanup: 'retained', retention: 'unknown', persistence: 'failed',
    primaryCause: safeCode(error, 'DIAGNOSTIC_FALLBACK_INVALID'), fallbackReference: capsule.reference }); }
  const dispatchObservation = safeFailureDiagnosticReference(failure) ?? {};
  state = { ...state, containment, fallbackReference: capsule.reference,
    ...(dispatchObservation.dispatcherExitCode !== undefined ? { dispatcherExitCode: dispatchObservation.dispatcherExitCode } : {}),
    ...(dispatchObservation.dispatcherSignal ? { dispatcherSignal: dispatchObservation.dispatcherSignal } : {}) };
  if (failure && !state.failureDiagnostic) {
    state.failureDiagnostic = safeFailureDiagnosticReference({ ...failure,
      stage: failure.stage ?? 'dispatcher', boundary: failure.boundary ?? 'dispatcher',
      operation: failure.operation ?? 'dispatch', primaryCause: failure.primaryCause ?? failure.code });
    state.primaryCause ??= state.failureDiagnostic?.primaryCause;
  }
  const details = () => ({ ...safeFailureDiagnosticReference(state), executionId,
    lastSuccessfulBoundary: state.lastSuccessfulBoundary, diagnosticStore: state.diagnosticStore,
    fallbackReference: capsule.reference, containment, cleanup: state.cleanup,
    persistence: state.persistence, retention: state.retention, failureDiagnostic: state.failureDiagnostic });
  const record = async () => {
    try { await capsule.write(state); }
    catch (error) { throw new WriterBlockedError('RUNTIME_DIAGNOSTICS_FAILED', 'Fallback update failed; inspect the preceding durable capsule', {
      ...details(), stage: 'diagnostic-persistence', boundary: 'diagnostic-persistence', operation: 'persist-fallback',
      primaryCause: safeCode(error, 'DIAGNOSTIC_FALLBACK_FAILED'), cleanup: 'retained', retention: 'unknown' }); }
  };
  // An unfinished runtime or failed diagnostic path leaves its evidence in
  // place. No assertion about a semantic result can override these states.
  if (!['reaped', 'not_required'].includes(containment) || !['stored', 'not_required'].includes(state.persistence)) {
    state.cleanup = 'retained'; state.retention = 'retained';
    await record();
    throw new WriterBlockedError(containment === 'unknown' ? 'CONTAINMENT_NOT_PROVEN' : 'RUNTIME_DIAGNOSTICS_FAILED',
      'Attempt artifacts require inspection before another launch', details());
  }
  if (state.sandboxCreated !== true || !state.sandboxIdentity) {
    // Preflight may have failed partway through mkdir, or encountered existing
    // artifacts. Without the pre-child inode, never delete by pathname alone.
    state.cleanup = 'retained'; state.retention = 'unknown';
    await record();
    return details();
  }
  state.cleanup = 'pending'; state.retention = 'unknown';
  state.stage = 'cleanup'; state.boundary = 'cleanup'; state.operation = 'sandbox-cleanup'; state.pathContext = 'sandbox';
  await record(); // Durable evidence BEFORE the first destructive operation.
  try {
    if (!/^(?:run|event)-[1-9][0-9]*$/.test(executionId)) throw Object.assign(new Error('Invalid attempt identity'), { code: 'SANDBOX_CLEANUP_IDENTITY_INVALID' });
    await cleanupSandbox({ cwd: join(workRoot, executionId), sandboxIdentity: state.sandboxIdentity });
  } catch (error) {
    const code = safeCode(error, 'SANDBOX_CLEANUP_FAILED');
    state.cleanup = 'failed'; state.retention = 'retained';
    state.cleanupContainment = ['reaped', 'not_required', 'unknown'].includes(error?.cleanupContainment) ? error.cleanupContainment : 'unknown';
    const cleanupFailure = safeFailureDiagnosticReference({ code, primaryCause: code, operation: 'sandbox-cleanup',
      syscall: error?.syscall, pathContext: 'sandbox', stage: 'cleanup', boundary: 'cleanup' });
    // Preserve the original cause in failureDiagnostic while recording the
    // independent cleanup failure at this final boundary.
    state.failureDiagnostic ??= cleanupFailure;
    state.primaryCause = code; state.syscall = cleanupFailure?.syscall;
    await record();
    try {
      const diagnosticId = `${executionId}-cleanup`;
      const diagnostic = createExecutionDiagnostic({ executionId: diagnosticId, mode: 'normal',
        startedAt: new Date().toISOString(), endedAt: new Date().toISOString(), phase: 'cleanup',
        phases: ['cleanup-start', 'cleanup-failed'], lifecycle: state, classification: code,
        runtimeFailure: { operation: 'sandbox-cleanup', code, syscall: error?.syscall, path: error?.path },
        exitCode: state.childExitCode, signal: state.signal });
      const result = await diagnosticStore(diagnostic);
      if (result?.status === 'unavailable') throw Object.assign(new Error('Store failed'), { code: result.storeCode ?? result.code });
      state.diagnosticStore = { status: 'stored', executionId: diagnosticId, mode: 'normal' };
    } catch (storeError) {
      // The capsule already records the cleanup cause independently.
      state.diagnosticStore = { status: 'unavailable', executionId: `${executionId}-cleanup`,
        code: 'DIAGNOSTICS_STORE_FAILED', storeCode: safeCode(storeError, 'DIAGNOSTICS_STORE_FAILED') };
    }
    await record();
    const finalDetails = details();
    throw new WriterBlockedError('SANDBOX_CLEANUP_FAILED', 'Attempt cleanup failed; inspect retained artifacts', {
      ...finalDetails, primaryCause: code, stage: 'cleanup', boundary: 'cleanup', operation: 'sandbox-cleanup',
      failureDiagnostic: safeFailureDiagnosticReference({ ...finalDetails, ...cleanupFailure,
        code: 'SANDBOX_CLEANUP_FAILED', primaryCause: code }) });
  }
  state.cleanup = 'complete'; state.cleanupContainment = 'reaped'; state.retention = 'none'; state.lastSuccessfulBoundary = 'cleanup';
  await record();
  // Keep failed-attempt capsules for bounded inspection. Ordinary successes
  // release their slot only after both cleanup and its durable receipt succeed.
  if (!failure && !state.failureDiagnostic) {
    try { await capsule.release(); }
    catch (error) { throw new WriterBlockedError('RUNTIME_DIAGNOSTICS_FAILED', 'Runtime diagnostic retirement failed', {
      ...details(), stage: 'finalization', boundary: 'finalization', operation: 'release-fallback',
      primaryCause: safeCode(error, 'DIAGNOSTIC_FALLBACK_FAILED') }); }
  }
  return details();
}
