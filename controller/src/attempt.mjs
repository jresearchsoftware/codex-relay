import { VERSION, validateEnvelope, causalEvidence, fail, safeDomainTerminal, digest, positive } from './execution-contract.mjs';
import { isWriterTokenRequest, safeWriterFailure } from './failure-report.mjs';
import { safeOutcomePublication } from './outcome.mjs';
import { boundedDiagnosticText, captureCausalDiagnostic } from './diagnostics.mjs';
import { normalizeCodexUsage } from './codex-usage.mjs';

// One runner-owned journal records whether the potentially paid call happened.
// Publication may be resumed; a reserved/unknown child is never relaunched.
const blockedReceipt = record => ({ ...record.outcome, code: record.diagnostic.classification.code, diagnostic: record.diagnostic,
  runId: record.envelope.runId, target: { kind: record.outcome.prNumber ? 'pull_request' : record.envelope.target,
    number: record.outcome.prNumber ?? record.envelope.number } });

export async function runAttempt(options) {
  if (options.envelope.route === 'auto' && options.journal.withLock) {
    return options.journal.withLock(options.envelope.runId, () => runLockedAttempt(options));
  }
  return runLockedAttempt(options);
}

async function runLockedAttempt(options) {
  const outcome = await runContainedAttempt(options);
  if (options.envelope.route !== 'auto' || outcome.status !== 'IMPLEMENTED_PENDING_FRESH_REVIEW') return outcome;
  // Outside the execution catch: a failed/uncertain Ready transition retains
  // the successful durable Outcome and can resume without another model call.
  const { envelope, broker, journal } = options;
  try { return await broker.invoke({ operation: 'complete-handoff', runId: envelope.runId, attemptId: envelope.attemptId }); }
  catch (error) {
    error.details = { writerFailure: safeWriterFailure({ operation: 'complete-handoff' }), ...error.details };
    await describePostOutcomeFailure(error, envelope, journal, outcome);
    throw error;
  }
}

// An independent handoff failure cannot erase a previously returned Outcome.
// Where the journal is unreadable, keep the Outcome proof and leave the child
// observation unknown. This read authorizes no mutation or worker replay.
export async function describePostOutcomeFailure(error, envelope, journal, outcome) {
  if (!positive(outcome?.outcomeId)) return;
  let saved;
  try { saved = await journal.get(envelope.runId); }
  catch { /* The earlier Outcome receipt still supplies publication evidence. */ }
  const execution = saved?.envelope?.attemptId === envelope.attemptId && saved?.outcome?.outcomeId === outcome.outcomeId
    ? saved.execution : null;
  error.details = { ...error.details, executionId: envelope.attemptId, runId: envelope.runId,
    target: outcome.prNumber ? { kind: 'pull_request', number: outcome.prNumber } : { kind: envelope.target, number: envelope.number },
    lastSuccessfulBoundary: 'outcome-publication', outcomePublication: safeOutcomePublication(null, 'published') };
  error.details.diagnostic = causalEvidence(error, { child: execution?.child, containment: execution?.containment,
    publishedHead: outcome.noChange ? null : outcome.head, stage: 'finalization' });
}

async function runContainedAttempt({ envelope, broker, journal, prepare, execute, collect, admissionResumed = false,
  admissionUnstarted = false, persistFailure }) {
  const e = validateEnvelope(envelope);
  const invoke = async (operation, value = {}) => {
    try { return await broker.invoke({ operation, runId: e.runId, attemptId: e.attemptId, ...value }); }
    catch (error) {
      error.details = { writerFailure: safeWriterFailure({ operation }), ...error.details };
      throw error;
    }
  };
  if (e.route === 'manual') return invoke('handoff');
  let record = await journal.get(e.runId);
  if (admissionUnstarted && (!admissionResumed || e.route !== 'auto' || record))
    fail('JOURNAL_MISSING_EXECUTION_UNKNOWN');
  if (admissionResumed && !record && !admissionUnstarted) fail('JOURNAL_MISSING_EXECUTION_UNKNOWN');
  if (record && (record.version !== VERSION || !Object.hasOwn(record, 'execution'))) fail('JOURNAL_MISSING_EXECUTION_UNKNOWN');
  if (record && digest(record.envelope) !== digest(e)) fail('JOURNAL_BINDING_CHANGED');
  // A durable terminal receipt or recorded token refusal ends this attempt's
  // mutable-checkout lifetime. Replay must not recollect or republish anything.
  const deferredOutcome = !record?.outcome && record?.diagnostic?.outcomePublication?.status === 'deferred'
    && isWriterTokenRequest(record.diagnostic.githubFailure);
  if (record?.outcome || deferredOutcome) {
    if (deferredOutcome || record.outcome.status === 'BLOCKED' || record.diagnostic?.orchestration === 'FAILED') {
      const diagnostic = record.diagnostic;
      if (!diagnostic?.classification?.code) fail('TERMINAL_STATE_INVALID');
      const code = diagnostic.classification.code;
      if (!deferredOutcome && diagnostic.orchestration === 'COMPLETED'
        && safeDomainTerminal({ code }, record, diagnostic.classification.stage)) return blockedReceipt(record);
      throw Object.assign(new Error(code), { code, details: {
        childState: diagnostic.observed.child,
        ...(diagnostic.classification.stage === 'execution' ? { causal: record.execution?.diagnostic } : {}),
        primaryCause: diagnostic.primaryCause,
        executionId: e.attemptId, attemptId: e.attemptId,
        lastSuccessfulBoundary: diagnostic.lastSuccessfulBoundary,
        outcomePublication: deferredOutcome ? diagnostic.outcomePublication : safeOutcomePublication(null, 'published'), diagnostic,
        runId: e.runId, target: { kind: e.target, number: e.number }
      } });
    }
    return record.outcome;
  }
  if (!record) {
    record = { version: VERSION, envelope: e, execution: null, progress: null, outcome: null, diagnostic: null };
    if (journal.reserve) {
      if (!await journal.reserve(e.runId, record)) fail('EXECUTION_UNKNOWN_NO_RETRY');
    } else await journal.put(e.runId, record);
  }
  let stage = 'preflight';
  let lastSuccessfulBoundary = 'admission';
  try {
    if (record.execution?.reserved && !record.execution.returned) fail('EXECUTION_UNKNOWN_NO_RETRY');
    const preflight = await invoke('preflight');
    lastSuccessfulBoundary = 'preflight';
    if (preflight.finalHead) {
      // Writer may have durably finished before the runner saved its receipt.
      // Restore that exact receipt, including warnings, without recollection.
      if (preflight.outcome?.status !== 'IMPLEMENTED_PENDING_FRESH_REVIEW'
        || preflight.outcome.head !== preflight.finalHead) fail('TERMINAL_STATE_INVALID');
      record.outcome = preflight.outcome;
      record.diagnostic = null;
      await journal.put(e.runId, record);
      return record.outcome;
    }
    if (!record.execution) {
      await prepare(e);
      lastSuccessfulBoundary = 'checkout';
      stage = 'execution';
      record.execution = { reserved: true, returned: false, child: 'unknown', containment: 'unknown', result: null };
      await journal.put(e.runId, record);
      try {
        const returned = await execute(e);
        if (returned?.version !== VERSION || returned.attemptId !== e.attemptId) fail('CHILD_ENVELOPE_INVALID');
        record.execution = { reserved: true, returned: true, child: returned.child, containment: returned.containment, result: returned.result,
          codexUsage: normalizeCodexUsage(returned.codexUsage), runtimeLifecycle: returned.runtimeLifecycle,
          executionWarnings: returned.executionWarnings ?? [] };
      } catch (error) {
        record.execution = { ...record.execution, returned: true, child: error.details?.childState ?? 'unknown',
          causalEvidence: captureCausalDiagnostic({ error, executionId: e.attemptId, phase: 'execution', operation: 'dispatch',
            secrets: { githubToken: process.env.GITHUB_TOKEN ?? '' } }),
          containment: error.details?.containment ?? 'unknown', errorCode: error.code ?? 'EXECUTION_FAILED',
          codexUsage: normalizeCodexUsage(error.details?.codexUsage ?? error.details?.causal?.codexUsage),
          diagnostic: causalEvidence(error, { child: error.details?.childState ?? 'unknown', containment: error.details?.containment, stage: 'execution' }) };
      }
      await journal.put(e.runId, record);
    }
    if (record.execution.containment !== 'reaped' && !(record.execution.child === 'not_started' && record.execution.containment === 'not_required')) fail('CONTAINMENT_NOT_PROVEN');
    if (!['started', 'not_started'].includes(record.execution.child)) fail(record.execution.errorCode ?? 'EXECUTION_STATE_UNKNOWN');
    lastSuccessfulBoundary = 'contained-execution';
    stage = 'progress';
    const progress = await collect(e);
    if (typeof progress.clean !== 'boolean' && !(progress.clean === null && progress.worktreeObservation?.status === 'unknown')) fail('WORKTREE_STATE_UNKNOWN');
    const executionWarnings = [...(record.execution.executionWarnings ?? []),
      ...(progress.clean === null ? ['WORKTREE_OBSERVATION_INCOMPLETE'] : progress.clean ? [] : ['UNCOMMITTED_WORK_REMAINS'])];
    record.executionWarnings = executionWarnings;
    record.collection = { head: progress.head, clean: progress.clean, preserved: true, ...(progress.worktreeObservation ? { worktreeObservation: progress.worktreeObservation } : {}) };
    lastSuccessfulBoundary = 'collection';
    // Collection observes the complete retained checkout after containment.
    // Persist that physical-resource proof before any external publication;
    // an uncertain Writer response cannot turn it into unknown execution.
    await journal.put(e.runId, record);
    if (progress.bundle) {
      const published = await invoke('publish-progress', { bundle: progress.bundle });
      record.progress = { head: published.publishedHead, prNumber: published.prNumber, clean: progress.clean === true };
      lastSuccessfulBoundary = 'publication';
      await journal.put(e.runId, record);
    }
    stage = 'readiness';
    // Dirtiness alone is not an automation failure after known successful
    // execution. An incomplete worker still needs its unsaved work reconciled.
    if (!progress.clean && !record.execution.errorCode && record.execution.result?.status !== 'success') {
      fail(progress.clean === null ? 'WORKTREE_OBSERVATION_INCOMPLETE' : 'UNCOMMITTED_WORK_REMAINS');
    }
    if (record.execution.result?.status !== 'success') {
      if (record.execution.errorCode) stage = 'execution';
      const code = record.execution.errorCode ?? 'SEMANTIC_RESULT_BLOCKED';
      throw Object.assign(new Error(code), { code, details: { childState: record.execution.child,
        causal: record.execution.diagnostic, primaryCause: record.execution.diagnostic?.primaryCause ?? null } });
    }
    if (!record.progress && ['task-request', 'admission'].includes(e.request?.kind) && progress.clean !== false && progress.head === e.startHead) {
      record.outcome = await invoke('finish-no-change', { head: progress.head, executionWarnings,
        taskResult: { summary: record.execution.result.summary, validation: record.execution.result.validation } });
      record.diagnostic = null; await journal.put(e.runId, record);
      return record.outcome;
    }
    if (!record.progress) fail('NO_DURABLE_PROGRESS');
    if (record.progress.head !== progress.head) fail('PUBLISHED_HEAD_REQUIRED');
    record.outcome = await invoke('finish', { head: record.progress.head,
      codexUsage: normalizeCodexUsage(record.execution.codexUsage),
      executionWarnings,
      taskResult: { summary: record.execution.result.summary, validation: record.execution.result.validation } });
    record.diagnostic = null; await journal.put(e.runId, record);
    return record.outcome;
  } catch (error) {
    const primaryExecution = record.execution?.errorCode ? record.execution.diagnostic : null;
    error.native = { ...error.native, ...(record.execution?.causalEvidence ? { executionEvidence: record.execution.causalEvidence } : {}),
      ...(record.execution?.result ? { workerResult: record.execution.result } : {}) };
    error.details = { ...error.details,
      ...(stage === 'execution' ? { causal: error.details?.causal ?? record.execution?.diagnostic } : {}),
      childState: error.details?.childState ?? (record.execution ? record.execution.child ?? 'unknown' : 'not_started'),
      containment: error.details?.containment ?? (record.execution ? record.execution.containment ?? 'unknown' : 'not_required'),
      executionId: e.attemptId, codexUsage: normalizeCodexUsage(record.execution?.codexUsage) };
    if (!error.details.lastSuccessfulBoundary && !error.details.causal?.lastSuccessfulBoundary) error.details.lastSuccessfulBoundary = lastSuccessfulBoundary;
    // Preparation, collection and journal/finalization failures also need a
    // durable diagnostic. The runtime capsule is reused when it already exists.
    if (persistFailure) {
      try {
        const durable = await persistFailure({ executionId: e.attemptId, error, stage, lastSuccessfulBoundary });
        error.details = { ...error.details, ...durable };
      } catch { error.details.diagnosticRecorderFailed = true; }
    }
    record.diagnostic = causalEvidence(error, { child: record.execution ? (record.execution.child ?? 'unknown') : 'not_started',
      containment: record.execution?.containment ?? 'not_required', publishedHead: record.progress?.head, stage });
    if (primaryExecution?.classification?.code && primaryExecution.classification.code !== error.code) record.diagnostic.executionFailure = primaryExecution;
    if (record.collection?.head && record.collection.head !== e.startHead)
      record.diagnostic.durable.collectedHead = record.collection.head;
    const domain = !error.details.diagnosticRecorderFailed && safeDomainTerminal(error, record, stage);
    record.diagnostic.orchestration = domain ? 'COMPLETED' : 'FAILED';
    // Presentation sanitizes these bounded worker claims; they are never
    // authority for execution, publication, validation or a completion verdict.
    if (record.execution?.result) {
      const summary = boundedDiagnosticText(record.execution.result.summary ?? '', 16 * 1024);
      record.diagnostic.taskSummary = summary.text + (summary.truncated ? ' [TRUNCATED]' : '');
      record.diagnostic.validation = record.execution.result.validation;
      const blocker = boundedDiagnosticText(record.execution.result.blockedReason ?? '', 16 * 1024);
      record.diagnostic.blockerSummary = blocker.text + (blocker.truncated ? ' [TRUNCATED]' : '');
    }
    const saveTerminal = async () => {
      try { await journal.put(e.runId, record); }
      catch (journalError) {
        record.diagnostic.terminalJournalFailed = true;
        record.diagnostic.orchestration = 'FAILED';
        error.details = { ...error.details, attemptId: e.attemptId, diagnostic: record.diagnostic };
        if (persistFailure) {
          try { await persistFailure({ executionId: `${e.attemptId}-journal`, error: journalError, stage: 'finalization', lastSuccessfulBoundary }); }
          catch { record.diagnostic.diagnosticRecorderFailed = true; }
        }
        throw error;
      }
    };
    // A new Writer call would POST the same token request before it could
    // deliver an Outcome. Retain the original failure without that request.
    const deferOutcome = e.route === 'auto' && !record.outcome && isWriterTokenRequest(record.diagnostic.githubFailure);
    if (deferOutcome) {
      error.details.outcomePublication = { status: 'deferred' };
      record.diagnostic.outcomePublication = error.details.outcomePublication;
    }
    await saveTerminal();
    if (e.route === 'auto' && !record.outcome && !deferOutcome) {
      try {
        const outcome = await invoke('terminal-outcome', { status: 'blocked', terminalCode: error.code,
          diagnostic: record.diagnostic, executionWarnings: record.executionWarnings ?? record.execution?.executionWarnings ?? [], publishedHead: record.progress?.head ?? null,
          lastSuccessfulBoundary: record.diagnostic.lastSuccessfulBoundary,
          failureBoundary: record.diagnostic.failureBoundary });
        record.outcome = outcome;
        error.details.outcomePublication = safeOutcomePublication(null, 'published');
      } catch (publicationError) {
        // Preserve the independently observed publication cause before reducing
        // it to the public uncertainty classification. Never repeat the POST.
        if (persistFailure) {
          try { await persistFailure({ executionId: `${e.attemptId}-publication`, error: publicationError,
            stage: 'writer-publication', lastSuccessfulBoundary }); }
          catch { record.diagnostic.diagnosticRecorderFailed = true; }
        }
        record.outcomePublicationEvidence = captureCausalDiagnostic({ error: publicationError, executionId: e.attemptId,
          phase: 'writer-publication', operation: 'terminal-outcome', secrets: { githubToken: process.env.GITHUB_TOKEN ?? '' } });
        error.details.outcomePublication = safeOutcomePublication(publicationError);
        record.diagnostic = { ...record.diagnostic, orchestration: 'FAILED', outcomePublication: error.details.outcomePublication };
      }
      // A failed durable terminal write is a physical failure, even if GitHub
      // already accepted the Outcome. It must never be swallowed to turn green.
      await saveTerminal();
    }
    error.details = { ...(error.details ?? {}), attemptId: e.attemptId, diagnostic: record.diagnostic };
    // A safe semantic/authority decision is a successful controller outcome
    // once the single terminal Outcome has been durably published. Keep real
    // runtime, transport, containment, and publication failures exceptional.
    if (domain && record.diagnostic.orchestration === 'COMPLETED' && record.outcome?.status === 'BLOCKED') return blockedReceipt(record);
    throw error;
  }
}
