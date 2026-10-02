import { join } from 'node:path';
import { CONSUMER } from '../../consumer/consumer.mjs';
import { reserveRuntimeDiagnostic, openRuntimeDiagnostic } from './diagnostic-fallback.mjs';
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
  let handle;
  let capsule;
  let fallbackReference = safeFallbackReference(supplied.fallbackReference ?? inherited.durable?.fallbackReference);
  let diagnosticStoreReference = safeDiagnosticStoreReference(supplied.diagnosticStore ?? inherited.durable?.diagnosticStore);
  let persistence = diagnosticStoreReference?.status === 'stored' ? 'stored' : 'pending';
  let cleanup = supplied.cleanup ?? inherited.runtime?.cleanup ?? 'retained';
  let retention = supplied.retention ?? inherited.runtime?.retention ?? 'unknown';
  let fallbackFailure;
  try {
    if (!identity) throw Object.assign(new Error('DIAGNOSTIC_ID_INVALID'), { code: 'DIAGNOSTIC_ID_INVALID' });
    handle = await fallbackOpen({ executionId: identity, ...(root ? { root } : {}), includeReleased: true });
    if (!handle) handle = await fallbackStore({ executionId: identity, ...(root ? { root } : {}) });
    capsule = await handle.read();
    fallbackReference = handle.reference;
    diagnosticStoreReference ??= safeDiagnosticStoreReference(capsule.diagnosticStore);
    if (diagnosticStoreReference?.status === 'stored') persistence = 'stored';
    cleanup = capsule.cleanup === 'complete' ? 'complete' : cleanup;
    retention = capsule.retention === 'none' && capsule.cleanup === 'complete' ? 'none' : capsule.sandboxCreated ? 'retained' : retention;
    // Preserve an earlier runtime cause; a later journal/publication failure
    // gets its own small record rather than overwriting that useful evidence.
    capsule = { ...capsule, ...(capsule.primaryCause ? {} : summary), released: false,
      lastSuccessfulBoundary: capsule.lastSuccessfulBoundary ?? lastSuccessfulBoundary,
      controllerFailure: summary, cleanup, retention, persistence };
    await handle.write(capsule);
  } catch (failure) {
    fallbackFailure = safeCode(failure?.code, 'DIAGNOSTIC_FALLBACK_FAILED');
    fallbackReference = { status: 'unavailable', ...(identity ? { executionId: identity } : {}), code: fallbackFailure,
      ...(Number.isInteger(handle?.reference?.slot) ? { slot: handle.reference.slot } : {}) };
  }
  if (persistence !== 'stored') {
    try {
      const config = await readConfig();
      const diagnostic = createExecutionDiagnostic({ executionId: identity, mode: config.mode,
        startedAt: now(), endedAt: now(), phase: stage, phases: [stage], lifecycle: { ...summary, cleanup, retention },
        checkout: identity ? join(CONSUMER.paths.workRoot, identity) : undefined,
        stderr: error?.stack ?? String(error?.message ?? code), classification: summary.primaryCause,
        runtimeFailure: { code, operation: summary.operation, syscall: error?.syscall, path: error?.path, dest: error?.dest }, secrets });
      const stored = await diagnosticStore(diagnostic);
      if (stored?.status === 'unavailable') throw Object.assign(new Error('DIAGNOSTICS_STORE_FAILED'), { code: stored.storeCode ?? stored.code });
      diagnosticStoreReference = { status: 'stored', ...(identity ? { executionId: identity } : {}), mode: config.mode };
      persistence = 'stored';
    } catch (failure) {
      persistence = 'failed';
      diagnosticStoreReference = { status: 'unavailable', code: 'DIAGNOSTICS_STORE_FAILED',
        storeCode: safeCode(failure?.storeDiagnosticCode ?? failure?.code, 'DIAGNOSTICS_STORE_FAILED'), ...(identity ? { executionId: identity } : {}) };
    }
  }
  if (handle && !fallbackFailure) {
    try {
      await handle.write({ ...capsule, persistence, diagnosticStore: diagnosticStoreReference,
        ...(persistence === 'failed' && cleanup !== 'complete' ? { cleanup: 'retained', retention } : {}) });
    } catch (failure) {
      fallbackReference = { ...handle.reference, status: 'unavailable', code: safeCode(failure?.code, 'DIAGNOSTIC_FALLBACK_FAILED') };
    }
  }
  return { ...summary, cleanup, retention, persistence, diagnosticStore: diagnosticStoreReference,
    fallbackReference, failureDiagnostic: { ...summary, cleanup, retention, persistence,
      diagnosticStore: diagnosticStoreReference, fallbackReference } };
}
