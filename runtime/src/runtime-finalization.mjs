import { EXECUTION_CONSUMER as CONSUMER } from '../../consumer/consumer.mjs';
import { join } from 'node:path';
import { openRuntimeDiagnostic, normalizeRuntimeCapsule } from '../../controller/src/diagnostic-fallback.mjs';
import { createExecutionDiagnostic, persistExecutionDiagnostic, safeFailureDiagnosticReference, safeDiagnosticStoreReference, readDiagnosticsConfig } from '../../controller/src/diagnostics.mjs';
import { cleanupCodexSandbox } from './sandbox-cleanup.mjs';
import { WriterBlockedError } from './contracts.mjs';

const safeCode = (error, fallback) => /^[A-Z][A-Z0-9_]{0,79}$/.test(error?.code ?? '') ? error.code : fallback;

// The caller combines the native model-UID launcher's inner-group receipt with
// its own outer dispatcher-group check. Runtime parsing alone cannot declare
// whole-execution containment or authorize this cleanup.
export async function finalizeRuntimeArtifacts({ executionId, containment, fallbackStore,
  failure, cleanupSandbox = cleanupCodexSandbox, diagnosticStore = persistExecutionDiagnostic,
  readDiagnosticConfig = readDiagnosticsConfig,
  workRoot = CONSUMER.paths.workRoot } = {}) {
  const capsule = fallbackStore ?? await openRuntimeDiagnostic({ executionId });
  if (!capsule) throw new WriterBlockedError('RUNTIME_DIAGNOSTIC_MISSING', 'The runtime capsule is unavailable', {
    executionId, containment, cleanup: 'retained', retention: 'unknown', persistence: 'failed',
    fallbackReference: { status: 'unavailable', executionId, code: 'RUNTIME_DIAGNOSTIC_MISSING' } });
  let state; let released = false;
  try { state = await capsule.read(); }
  catch (error) { throw new WriterBlockedError('RUNTIME_DIAGNOSTICS_FAILED', 'The runtime capsule cannot be read; artifacts are retained', {
    executionId, containment, cleanup: 'retained', retention: 'unknown', persistence: 'failed',
    primaryCause: safeCode(error, 'DIAGNOSTIC_FALLBACK_INVALID'), fallbackReference: capsule.reference }); }
  let diagnosticMode = state.diagnosticStore?.mode === 'debug' ? 'debug' : 'normal';
  const dispatchObservation = safeFailureDiagnosticReference(failure) ?? {};
  // Only the trusted dispatcher's proven no-child observation may
  // complete its untouched initial capsule. Pending actual runtime diagnostics
  // and known runtime observations retain their original persistence boundary.
  const dispatchNeverStarted = failure?.code === 'DISPATCH_NOT_STARTED'
    && dispatchObservation.operation === 'dispatch' && dispatchObservation.childState === 'not_started'
    && dispatchObservation.containment === 'not_required' && containment === 'not_required'
    && state.stage === 'dispatcher' && state.operation === 'dispatch' && state.childState === 'unknown'
    && state.persistence === 'pending' && state.sandboxCreated === false && state.inputSchemaCreated === false
    && !state.sandboxIdentity && !state.failureDiagnostic && !state.diagnosticStore;
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
    lastSuccessfulBoundary: state.lastSuccessfulBoundary,
    diagnosticStore: state.terminalDiagnostic?.status === 'stored' ? state.terminalDiagnostic : state.diagnosticStore,
    fallbackReference: { ...capsule.reference, ...(released ? { status: 'released' } : {}) },
    terminalDiagnostic: state.terminalDiagnostic, containment, cleanup: state.cleanup,
    persistence: state.persistence, retention: state.retention, failureDiagnostic: state.failureDiagnostic });
  const record = async () => {
    try { await capsule.write(state); }
    catch (error) { throw new WriterBlockedError('RUNTIME_DIAGNOSTICS_FAILED', 'Fallback update failed; inspect the preceding durable capsule', {
      ...details(), stage: 'diagnostic-persistence', boundary: 'diagnostic-persistence', operation: 'persist-fallback',
      primaryCause: safeCode(error, 'DIAGNOSTIC_FALLBACK_FAILED'), cleanup: 'retained', retention: 'unknown' }); }
  };
  const retire = async ({ cleanupError } = {}) => {
    const contained = ['started', 'not_started'].includes(state.childState)
      && ['reaped', 'not_required'].includes(containment)
      && ['reaped', 'not_required'].includes(state.cleanupContainment);
    if (!contained) return;
    const ordinarySuccess = !failure && !state.failureDiagnostic && state.cleanup === 'complete';
    if (!ordinarySuccess) {
      // Preserve the complete safe final capsule (including the inode and old
      // primary diagnostic pointer) before releasing only the capacity slot.
      const diagnosticId = `${executionId}-finalization`;
      try {
        if (dispatchNeverStarted) {
          // No runtime ran to read the existing diagnostics mode. Use that
          // same configuration so the protected store can accept the archive.
          const configured = await readDiagnosticConfig();
          if (!['normal', 'debug'].includes(configured?.mode)) throw Object.assign(new Error('Invalid diagnostic mode'), { code: 'DIAGNOSTICS_CONFIG_INVALID' });
          diagnosticMode = configured.mode;
        }
        const diagnostic = createExecutionDiagnostic({ executionId: diagnosticId, mode: diagnosticMode,
          startedAt: new Date().toISOString(), endedAt: new Date().toISOString(), phase: 'finalization',
          phases: ['contained-terminal', 'diagnostic-retirement'],
          lifecycle: normalizeRuntimeCapsule(state, executionId), classification: state.primaryCause,
          runtimeFailure: cleanupError ? { code: safeCode(cleanupError, 'SANDBOX_CLEANUP_FAILED'),
            operation: 'sandbox-cleanup', syscall: cleanupError.syscall, path: cleanupError.path } : undefined,
          exitCode: state.childExitCode, signal: state.signal });
        const receipt = await diagnosticStore(diagnostic);
        const reference = safeDiagnosticStoreReference(typeof receipt?.stdout === 'string'
          ? JSON.parse(receipt.stdout) : receipt);
        if (reference?.status !== 'stored' || reference.executionId !== diagnosticId || reference.mode !== diagnosticMode) {
          throw Object.assign(new Error('Final diagnostic storage is not proven'), { code: receipt?.storeCode ?? receipt?.code ?? 'DIAGNOSTICS_STORE_FAILED' });
        }
        state.terminalDiagnostic = reference;
      } catch (error) {
        state.terminalDiagnostic = { status: 'unavailable', executionId: diagnosticId,
          code: 'DIAGNOSTICS_STORE_FAILED', storeCode: safeCode(error, 'DIAGNOSTICS_STORE_FAILED') };
        await record();
        throw new WriterBlockedError('RUNTIME_DIAGNOSTICS_FAILED', 'Final diagnostics were not durably archived; the active capsule is retained', {
          ...details(), stage: 'diagnostic-persistence', boundary: 'diagnostic-persistence', operation: 'persist-fallback',
          primaryCause: state.terminalDiagnostic.storeCode });
      }
      await record();
    }
    try { await capsule.release(); released = true; }
    catch (error) { throw new WriterBlockedError('RUNTIME_DIAGNOSTICS_FAILED', 'Runtime diagnostic retirement failed', {
      ...details(), stage: 'finalization', boundary: 'finalization', operation: 'release-fallback',
      primaryCause: safeCode(error, 'DIAGNOSTIC_FALLBACK_FAILED') }); }
  };
  if (dispatchNeverStarted) {
    // No runtime streams or mutation existed. The full safe dispatch failure
    // itself still needs an independently durable final diagnostic.
    state.childState = 'not_started'; state.persistence = 'not_required';
    state.cleanup = 'not_required'; state.cleanupContainment = 'not_required'; state.retention = 'none';
    await record();
    await retire();
    return details();
  }
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
    state.cleanup = 'retained'; state.retention = 'unknown'; state.cleanupContainment = 'not_required';
    await record();
    await retire();
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
      const diagnostic = createExecutionDiagnostic({ executionId: diagnosticId, mode: diagnosticMode,
        startedAt: new Date().toISOString(), endedAt: new Date().toISOString(), phase: 'cleanup',
        phases: ['cleanup-start', 'cleanup-failed'], lifecycle: state, classification: code,
        runtimeFailure: { operation: 'sandbox-cleanup', code, syscall: error?.syscall, path: error?.path },
        exitCode: state.childExitCode, signal: state.signal });
      const result = await diagnosticStore(diagnostic);
      if (result?.status === 'unavailable') throw Object.assign(new Error('Store failed'), { code: result.storeCode ?? result.code });
      state.diagnosticStore = { status: 'stored', executionId: diagnosticId, mode: diagnosticMode };
    } catch (storeError) {
      // The capsule already records the cleanup cause independently.
      state.diagnosticStore = { status: 'unavailable', executionId: `${executionId}-cleanup`,
        code: 'DIAGNOSTICS_STORE_FAILED', storeCode: safeCode(storeError, 'DIAGNOSTICS_STORE_FAILED') };
    }
    await record();
    // Even when cleanup failed, its process may be known reaped. Preserve the
    // resource and archive the final facts without occupying launch capacity.
    try { await retire({ cleanupError: error }); }
    catch { /* The original cleanup failure remains primary; capsule retains the archive gap. */ }
    const finalDetails = details();
    throw new WriterBlockedError('SANDBOX_CLEANUP_FAILED', 'Attempt cleanup failed; inspect retained artifacts', {
      ...finalDetails, primaryCause: code, stage: 'cleanup', boundary: 'cleanup', operation: 'sandbox-cleanup',
      failureDiagnostic: safeFailureDiagnosticReference({ ...finalDetails, ...cleanupFailure,
        code: 'SANDBOX_CLEANUP_FAILED', primaryCause: code }) });
  }
  state.cleanup = 'complete'; state.cleanupContainment = 'reaped'; state.retention = 'none'; state.lastSuccessfulBoundary = 'cleanup';
  await record();
  await retire();
  return details();
}
