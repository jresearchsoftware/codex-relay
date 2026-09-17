import { VERSION, validateEnvelope, causalEvidence, fail, safeDomainTerminal, digest } from './execution-contract.mjs';
import { safeOutcomePublication } from './outcome.mjs';
import { boundedDiagnosticText } from './diagnostics.mjs';

// One runner-owned journal records whether the potentially paid call happened.
// Publication may be resumed; a reserved/unknown child is never relaunched.
export async function runAttempt({ envelope, broker, journal, prepare, execute, collect, admissionResumed = false }) {
  const e = validateEnvelope(envelope);
  const invoke = (operation, value = {}) => broker.invoke({ operation, runId: e.runId, attemptId: e.attemptId, ...value });
  if (e.route === 'manual') return invoke('handoff');
  let record = await journal.get(e.runId);
  if (admissionResumed && !record) fail('JOURNAL_MISSING_EXECUTION_UNKNOWN');
  if (record && (record.version !== VERSION || !Object.hasOwn(record, 'execution'))) fail('JOURNAL_MISSING_EXECUTION_UNKNOWN');
  if (record && digest(record.envelope) !== digest(e)) fail('JOURNAL_BINDING_CHANGED');
  // A durable terminal receipt ends this attempt's mutable-checkout lifetime.
  // Replay outside the catch path so it cannot recollect or republish anything.
  if (record?.outcome) {
    if (record.outcome.status === 'BLOCKED') {
      const diagnostic = record.diagnostic;
      if (!diagnostic?.classification?.code) fail('TERMINAL_STATE_INVALID');
      const code = diagnostic.classification.code;
      if (diagnostic.orchestration === 'COMPLETED' && safeDomainTerminal({ code }, record, diagnostic.classification.stage)) return record.outcome;
      throw Object.assign(new Error(code), { code, details: {
        childState: diagnostic.observed.child,
        ...(diagnostic.classification.stage === 'execution' ? { causal: record.execution?.diagnostic } : {}),
        primaryCause: diagnostic.primaryCause,
        executionId: e.attemptId, attemptId: e.attemptId,
        lastSuccessfulBoundary: diagnostic.lastSuccessfulBoundary,
        outcomePublication: safeOutcomePublication(null, 'published'), diagnostic
      } });
    }
    return record.outcome;
  }
  record ??= { version: VERSION, envelope: e, execution: null, progress: null, outcome: null, diagnostic: null };
  await journal.put(e.runId, record);
  let stage = 'preflight';
  let lastSuccessfulBoundary = 'admission';
  try {
    if (record.execution?.reserved && !record.execution.returned) fail('EXECUTION_UNKNOWN_NO_RETRY');
    const preflight = await invoke('preflight');
    lastSuccessfulBoundary = 'preflight';
    if (preflight.finalHead) return { status: 'IMPLEMENTED_PENDING_FRESH_REVIEW', head: preflight.finalHead };
    if (!record.execution) {
      await prepare(e);
      lastSuccessfulBoundary = 'checkout';
      stage = 'execution';
      record.execution = { reserved: true, returned: false, child: 'unknown', containment: 'unknown', result: null };
      await journal.put(e.runId, record);
      try {
        const returned = await execute(e);
        if (returned?.version !== VERSION || returned.attemptId !== e.attemptId) fail('CHILD_ENVELOPE_INVALID');
        record.execution = { reserved: true, returned: true, child: returned.child, containment: returned.containment, result: returned.result };
      } catch (error) {
        record.execution = { ...record.execution, returned: true, child: error.details?.childState ?? 'unknown',
          containment: error.details?.containment ?? 'unknown', errorCode: error.code ?? 'EXECUTION_FAILED',
          diagnostic: causalEvidence(error, { child: error.details?.childState ?? 'unknown', containment: error.details?.containment, stage: 'execution' }) };
      }
      await journal.put(e.runId, record);
    }
    if (record.execution.containment !== 'reaped' && !(record.execution.child === 'not_started' && record.execution.containment === 'not_required')) fail('CONTAINMENT_NOT_PROVEN');
    if (!['started', 'not_started'].includes(record.execution.child)) fail(record.execution.errorCode ?? 'EXECUTION_STATE_UNKNOWN');
    lastSuccessfulBoundary = 'contained-execution';
    stage = 'progress';
    const progress = await collect(e);
    record.collection = { head: progress.head, clean: progress.clean === true };
    lastSuccessfulBoundary = 'collection';
    if (progress.bundle) {
      const published = await invoke('publish-progress', { bundle: progress.bundle });
      record.progress = { head: published.publishedHead, prNumber: published.prNumber, clean: progress.clean === true };
      lastSuccessfulBoundary = 'publication';
      await journal.put(e.runId, record);
    }
    stage = 'readiness';
    if (!progress.clean) fail('UNCOMMITTED_WORK_REMAINS');
    if (record.execution.result?.status !== 'success') {
      if (record.execution.errorCode) stage = 'execution';
      const code = record.execution.errorCode ?? 'SEMANTIC_RESULT_BLOCKED';
      throw Object.assign(new Error(code), { code, details: { childState: record.execution.child,
        causal: record.execution.diagnostic, primaryCause: record.execution.diagnostic?.primaryCause ?? null } });
    }
    if (!record.progress) fail('NO_DURABLE_PROGRESS');
    record.outcome = await invoke('finish', { head: record.progress.head,
      taskResult: { summary: record.execution.result.summary, validation: record.execution.result.validation } });
    record.diagnostic = null; await journal.put(e.runId, record);
    return record.outcome;
  } catch (error) {
    error.details = { ...error.details,
      ...(stage === 'execution' ? { causal: error.details?.causal ?? record.execution?.diagnostic } : {}),
      executionId: e.attemptId };
    if (!error.details.lastSuccessfulBoundary && !error.details.causal?.lastSuccessfulBoundary) error.details.lastSuccessfulBoundary = lastSuccessfulBoundary;
    record.diagnostic = causalEvidence(error, { child: record.execution ? (record.execution.child ?? 'unknown') : 'not_started',
      containment: record.execution?.containment ?? 'not_required', publishedHead: record.progress?.head, stage });
    const domain = safeDomainTerminal(error, record, stage);
    record.diagnostic.orchestration = domain ? 'COMPLETED' : 'FAILED';
    // Presentation sanitizes these bounded worker claims; they are never
    // authority for execution, publication, validation or a completion verdict.
    if (record.execution?.result) {
      record.diagnostic.taskSummary = boundedDiagnosticText(record.execution.result.summary ?? '', 512).text;
      record.diagnostic.blockerSummary = boundedDiagnosticText(record.execution.result.blockedReason ?? '', 512).text;
    }
    await journal.put(e.runId, record);
    if (e.route === 'auto' && !record.outcome) {
      try {
        const outcome = await invoke('terminal-outcome', { status: 'blocked', terminalCode: error.code,
          diagnostic: record.diagnostic, publishedHead: record.progress?.head ?? null,
          lastSuccessfulBoundary: record.diagnostic.lastSuccessfulBoundary,
          failureBoundary: record.diagnostic.failureBoundary });
        record.outcome = outcome;
        error.details.outcomePublication = safeOutcomePublication(null, 'published');
      } catch (publicationError) {
        error.details.outcomePublication = safeOutcomePublication(publicationError);
        record.diagnostic = { ...record.diagnostic, orchestration: 'FAILED', outcomePublication: error.details.outcomePublication };
      }
      // A failed durable terminal write is a physical failure, even if GitHub
      // already accepted the Outcome. It must never be swallowed to turn green.
      await journal.put(e.runId, record);
    }
    error.details = { ...(error.details ?? {}), attemptId: e.attemptId, diagnostic: record.diagnostic };
    // A safe semantic/authority decision is a successful controller outcome
    // once the single terminal Outcome has been durably published. Keep real
    // runtime, transport, containment, and publication failures exceptional.
    if (domain && record.diagnostic.orchestration === 'COMPLETED' && record.outcome?.status === 'BLOCKED') return record.outcome;
    throw error;
  }
}
