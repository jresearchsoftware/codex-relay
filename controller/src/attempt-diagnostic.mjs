import { join } from 'node:path';
import { EXECUTION_CONSUMER as CONSUMER } from '../../consumer/consumer.mjs';
import { reserveRuntimeDiagnostic, openRuntimeDiagnostic, normalizeRuntimeCapsule } from './diagnostic-fallback.mjs';
import { createExecutionDiagnostic, persistExecutionDiagnostic, readDiagnosticsConfig,
  safeFailureDiagnosticReference, safeDiagnosticStoreReference, safeFallbackReference } from './diagnostics.mjs';

const safeCode = (value, fallback) => typeof value === 'string' && /^[A-Z][A-Z0-9_]{0,79}$/.test(value) ? value : fallback;
const operations = { preflight: 'checkout-prepare', progress: 'collect-progress', readiness: 'attempt-finalization',
  execution: 'attempt-execution', finalization: 'attempt-finalization' };

// This is a terminal evidence path, not a retry or cleanup path. In particular,
// failure of both stores must never replace the original execution exception.
export async function persistAttemptFailureDiagnostic({ executionId, error, stage = 'finalization', lastSuccessfulBoundary,
  root, diagnosticStore = persistExecutionDiagnostic, fallbackStore = reserveRuntimeDiagnostic,
  fallbackOpen = openRuntimeDiagnostic, readConfig = readDiagnosticsConfig,
  now = () => new Date().toISOString(), secrets = { githubToken: process.env.GITHUB_TOKEN ?? '', codexAccessToken: process.env.CODEX_ACCESS_TOKEN ?? '' } } = {}) {
  const identity = typeof executionId === 'string' && /^[A-Za-z0-9_-]{1,128}$/.test(executionId) ? executionId : undefined;
  const inherited = error?.details?.causal ?? error?.details?.diagnostic ?? {};
  const supplied = safeFailureDiagnosticReference(error?.details?.failureDiagnostic ?? error?.details) ?? {};
  const code = safeCode(error?.code, 'UNCLASSIFIED_ATTEMPT_FAILURE');
  const summary = safeFailureDiagnosticReference({ ...supplied, code,
    primaryCause: supplied.primaryCause ?? safeCode(inherited.primaryCause, code),
    stage: supplied.stage ?? stage, boundary: supplied.boundary ?? stage,
    operation: supplied.operation ?? operations[stage] ?? 'attempt-finalization', syscall: supplied.syscall ?? error?.syscall,
    pathContext: supplied.pathContext ?? (stage === 'preflight' ? 'checkout' : 'unknown'),
    executionId: identity });
  let handle; let capsule; let created = false; let originalPersistenceFailed = false; let originalRuntimePending = false; let primaryId = identity;
  let fallbackReference = safeFallbackReference(supplied.fallbackReference ?? inherited.durable?.fallbackReference);
  let diagnosticStoreReference = safeDiagnosticStoreReference(supplied.diagnosticStore ?? inherited.durable?.diagnosticStore);
  let persistence = diagnosticStoreReference?.status === 'stored' ? 'stored' : 'pending';
  let cleanup = supplied.cleanup ?? inherited.runtime?.cleanup ?? 'retained';
  let retention = supplied.retention ?? inherited.runtime?.retention ?? 'unknown';
  let fallbackFailure;
  try {
    if (!identity) throw Object.assign(new Error('DIAGNOSTIC_ID_INVALID'), { code: 'DIAGNOSTIC_ID_INVALID' });
    handle = await fallbackOpen({ executionId: identity, ...(root ? { root } : {}), includeReleased: true });
    if (!handle) { handle = await fallbackStore({ executionId: identity, ...(root ? { root } : {}) }); created = true; }
    capsule = await handle.read();
    originalPersistenceFailed = capsule.persistence === 'failed';
    originalRuntimePending = !created && capsule.persistence === 'pending';
    if (originalPersistenceFailed || originalRuntimePending || created && stage !== 'preflight') primaryId = `${identity}-controller`;
    fallbackReference = handle.reference;
    // A public finalization pointer must never replace the capsule's original
    // runtime diagnostic link. The new archive will contain both that link and
    // the newly observed controller failure.
    diagnosticStoreReference = safeDiagnosticStoreReference(capsule.diagnosticStore);
    persistence = originalPersistenceFailed ? 'failed' : diagnosticStoreReference?.status === 'stored' ? 'stored' : capsule.persistence;
    cleanup = capsule.cleanup === 'complete' ? 'complete' : cleanup;
    retention = capsule.cleanup === 'complete' && capsule.retention === 'none' ? 'none' : capsule.sandboxCreated ? 'retained' : retention;
    const controllerNoChild = created && stage === 'preflight'
      && summary.childState === 'not_started' && summary.containment === 'not_required'
      && capsule.sandboxCreated === false && capsule.inputSchemaCreated === false && !capsule.sandboxIdentity;
    capsule = { ...capsule, ...(capsule.primaryCause ? {} : summary), released: false, terminalDiagnostic: undefined,
      childState: created ? summary.childState ?? 'unknown' : capsule.childState ?? 'unknown',
      containment: created ? summary.containment ?? 'unknown' : capsule.containment ?? 'unknown',
      ...(controllerNoChild ? { cleanupContainment: 'not_required' } : {}),
      lastSuccessfulBoundary: capsule.lastSuccessfulBoundary ?? lastSuccessfulBoundary,
      controllerFailure: summary, cleanup, retention, persistence };
    await handle.write(capsule);
  } catch (failure) {
    fallbackFailure = safeCode(failure?.code, 'DIAGNOSTIC_FALLBACK_FAILED');
    fallbackReference = { status: 'unavailable', ...(identity ? { executionId: identity } : {}), code: fallbackFailure,
      ...(Number.isInteger(handle?.reference?.slot) ? { slot: handle.reference.slot } : {}) };
  }
  let configured;
  const mode = async () => {
    configured ??= await readConfig();
    if (!['normal', 'debug'].includes(configured?.mode)) throw Object.assign(new Error('Invalid diagnostic mode'), { code: 'DIAGNOSTICS_CONFIG_INVALID' });
    return configured.mode;
  };
  const storeExactly = async diagnostic => {
    const receipt = await diagnosticStore(diagnostic);
    const reference = safeDiagnosticStoreReference(typeof receipt?.stdout === 'string' ? JSON.parse(receipt.stdout) : receipt);
    if (reference?.status !== 'stored' || reference.executionId !== diagnostic.executionId || reference.mode !== diagnostic.mode) {
      throw Object.assign(new Error('Diagnostic storage is not proven'), { code: receipt?.storeCode ?? receipt?.code ?? 'DIAGNOSTICS_STORE_FAILED' });
    }
    return reference;
  };
  const unavailable = (failure, selectedId = identity) => ({ status: 'unavailable', code: 'DIAGNOSTICS_STORE_FAILED',
    storeCode: safeCode(failure?.storeDiagnosticCode ?? failure?.code, 'DIAGNOSTICS_STORE_FAILED'), ...(selectedId ? { executionId: selectedId } : {}) });
  if (diagnosticStoreReference?.status !== 'stored') {
    try {
      const diagnostic = createExecutionDiagnostic({ executionId: primaryId, mode: await mode(),
        startedAt: now(), endedAt: now(), phase: stage, phases: [stage], lifecycle: { ...summary, cleanup, retention },
        checkout: identity ? join(CONSUMER.paths.workRoot, identity) : undefined,
        stderr: error?.stack ?? String(error?.message ?? code), classification: summary.primaryCause,
        runtimeFailure: { code, operation: summary.operation, syscall: error?.syscall, path: error?.path, dest: error?.dest }, secrets });
      diagnosticStoreReference = await storeExactly(diagnostic);
      if (!originalPersistenceFailed && !originalRuntimePending) persistence = 'stored';
    } catch (failure) {
      persistence = 'failed'; diagnosticStoreReference = unavailable(failure);
    }
  }
  if (handle && !fallbackFailure) {
    try {
      // Failed original runtime persistence is not repaired by a controller-only
      // report. Its capsule and original diagnostic pointer remain protected.
      capsule = { ...capsule, persistence,
        ...(!originalPersistenceFailed && !originalRuntimePending ? { diagnosticStore: diagnosticStoreReference } : {}),
        ...(persistence === 'failed' && cleanup !== 'complete' ? { cleanup: 'retained', retention } : {}) };
      await handle.write(capsule);
      if (persistence === 'stored') {
        const diagnosticId = `${identity}-finalization`;
        let archive;
        try {
          const diagnostic = createExecutionDiagnostic({ executionId: diagnosticId, mode: diagnosticStoreReference?.mode ?? await mode(),
            startedAt: now(), endedAt: now(), phase: 'controller-terminal', phases: [stage, 'controller-terminal'],
            lifecycle: normalizeRuntimeCapsule(capsule, identity),
            checkout: join(CONSUMER.paths.workRoot, identity), stderr: error?.stack ?? String(error?.message ?? code),
            classification: summary.primaryCause,
            runtimeFailure: { code, operation: summary.operation, syscall: error?.syscall, path: error?.path, dest: error?.dest }, secrets });
          archive = await storeExactly(diagnostic);
        } catch (failure) {
          capsule.terminalDiagnostic = unavailable(failure, diagnosticId);
          await handle.write(capsule);
          diagnosticStoreReference = capsule.terminalDiagnostic;
          persistence = 'failed';
        }
        if (archive) {
          diagnosticStoreReference = archive;
          capsule.terminalDiagnostic = archive;
          await handle.write(capsule);
          const contained = ['started', 'not_started'].includes(capsule.childState)
            && ['reaped', 'not_required'].includes(capsule.containment)
            && ['reaped', 'not_required'].includes(capsule.cleanupContainment);
          if (contained) {
            try {
              await handle.release();
              fallbackReference = { ...handle.reference, status: 'released' };
            } catch (failure) {
              // The archive is still valid even if retiring its active slot
              // fails. Report that independent fallback boundary truthfully.
              fallbackReference = { ...handle.reference, status: 'unavailable', code: safeCode(failure?.code, 'DIAGNOSTIC_FALLBACK_FAILED') };
            }
          }
        }
      }
    } catch (failure) {
      fallbackReference = { ...handle.reference, status: 'unavailable', code: safeCode(failure?.code, 'DIAGNOSTIC_FALLBACK_FAILED') };
    }
  }
  const observed = capsule ? { childState: capsule.childState, containment: capsule.containment,
    ...(capsule.cleanupContainment ? { cleanupContainment: capsule.cleanupContainment } : {}) } : {};
  return { ...summary, ...observed, cleanup, retention, persistence, diagnosticStore: diagnosticStoreReference,
    fallbackReference, failureDiagnostic: { ...summary, ...observed, cleanup, retention, persistence,
      diagnosticStore: diagnosticStoreReference, fallbackReference } };
}
