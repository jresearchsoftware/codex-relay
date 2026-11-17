import { randomUUID } from 'node:crypto';
import { join } from 'node:path';
import { CONSUMER } from '../../consumer/consumer.mjs';
import { createExecutionDiagnostic, readDiagnosticsConfig, safeDiagnosticStoreReference, captureCausalDiagnostic, redactDiagnosticText } from './diagnostics.mjs';
import { writeDiagnosticBundle } from './diagnostic-store.mjs';
import { reserveRuntimeDiagnostic } from './diagnostic-fallback.mjs';

const codeOf = error => typeof error?.code === 'string' && /^[A-Z][A-Z0-9_]{0,79}$/.test(error.code) ? error.code : 'UNCLASSIFIED_FAILURE';

// Used at trusted host boundaries, including rejection before target binding.
// This writes diagnostics only: never an attempt reservation or native Outcome.
export async function recordHostFailure({ error, operation = 'unknown', phase = 'authority', runId, workerStarted,
  secrets = {}, diagnosticStore = writeDiagnosticBundle, fallbackStore = reserveRuntimeDiagnostic,
  readConfig = readDiagnosticsConfig, writeFallback = text => process.stderr.write(text),
  executionId = `host-${Number.isSafeInteger(runId) && runId > 0 ? runId : 'unknown'}-${randomUUID()}` } = {}) {
  const code = codeOf(error);
  operation = typeof operation === 'string' && /^[a-z][a-z0-9-]{0,63}$/.test(operation) ? redactDiagnosticText(operation, secrets) : 'unknown';
  phase = typeof phase === 'string' && /^[a-z][a-z0-9-]{0,39}$/.test(phase) ? phase : 'authority';
  let bundle;
  let primaryFailure;
  try {
    const config = await readConfig();
    bundle = createExecutionDiagnostic({ executionId, mode: config.mode, startedAt: new Date().toISOString(),
      endedAt: new Date().toISOString(), phase, phases: [phase], classification: code,
      lifecycle: { operation, runId: Number.isSafeInteger(runId) ? runId : null,
        ...(typeof workerStarted === 'boolean' ? { workerStarted } : {}) },
      input: { kind: 'host-failure', operation, runId: Number.isSafeInteger(runId) ? runId : null },
      error, stderr: error?.stack ?? String(error?.message ?? code), secrets });
    const result = safeDiagnosticStoreReference(await diagnosticStore(bundle));
    if (result?.status !== 'stored' || result.executionId !== executionId || result.mode !== config.mode)
      throw Object.assign(new Error('Diagnostic durability receipt is invalid'), { code: 'DIAGNOSTICS_STORE_RECEIPT_INVALID' });
    return result;
  } catch (failure) { primaryFailure = failure; }
  // Independent existing capsule survives primary configuration/store failures.
  // Neither failure is permission to repeat the original operation.
  try {
    const fallback = await fallbackStore({ executionId, root: join(CONSUMER.paths.claimRoot, 'runtime-diagnostics') });
    await fallback.write({ ...(await fallback.read()), primaryCause: code, childState: workerStarted === false ? 'not_started' : workerStarted === true ? 'started' : 'unknown',
      containment: workerStarted === false ? 'not_required' : 'unknown', cleanupContainment: 'not_required', cleanup: 'not_required', retention: 'unknown', persistence: 'failed',
      causalEvidence: bundle?.causalEvidence ?? captureCausalDiagnostic({ error, executionId, phase, operation, secrets }, { compact: true }),
      recorderFailure: captureCausalDiagnostic({ error: primaryFailure, executionId, phase: 'diagnostic-persistence', operation: 'store-diagnostic', secrets }, { compact: true }) });
    return { status: 'unavailable', executionId, code: 'DIAGNOSTICS_STORE_FAILED', storeCode: codeOf(primaryFailure),
      fallbackReference: fallback.reference };
  } catch (failure) {
    // Service journal/Actions stderr is independent of both filesystem recorders.
    // Fixed fields only: raw exception, event, paths and request bodies stay private.
    const result = { status: 'unavailable', executionId, code: 'DIAGNOSTICS_STORE_FAILED',
      storeCode: codeOf(primaryFailure), fallbackCode: codeOf(failure), originalCode: code, originalEvidence: 'observed_not_retained',
      fallbackReference: { status: 'unavailable', executionId, code: codeOf(failure) } };
    try { writeFallback(`RELAY_DIAGNOSTIC_UNAVAILABLE ${JSON.stringify(result)}\n`); } catch { /* host/output unavailable */ }
    return result;
  }
}
