import { CONSUMER, EXECUTION_CONSUMER, EXECUTION_SLOT, runnerExecutionSlot } from '../../consumer/consumer.mjs';
import { readFile } from 'node:fs/promises';
import { realpathSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { createLocalWriterAdapter } from './local-writer.mjs';
import { createOnDemandDispatchAdapter } from './github.mjs';
import { createAttemptStore } from './attempt-store.mjs';
import { runAttempt, describePostOutcomeFailure } from './attempt.mjs';
import { prepareCheckout, executeCodex } from './attempt-runtime.mjs';
import { REPOSITORY, OWNER, causalEvidence, fail, positive } from './execution-contract.mjs';
import { emitAdmissionWarnings, executionWarningSummary } from './outcome.mjs';
import { parseLaunchInputs, parseLabelLaunch } from './launch-metadata.mjs';
import { persistAttemptFailureDiagnostic } from './attempt-diagnostic.mjs';
import { failureExplanation, failureFacts } from './failure-report.mjs';
import { ownerRunRejectionReason } from './owner-run-rejection.mjs';
import { randomUUID } from 'node:crypto';
import { traceRuntimeOperation } from './transition-timing.mjs';

export async function main(options = {}) {
  const cancellation = new AbortController();
  const progress = { workerPossible: false };
  const runId = Number((options.env ?? process.env).GITHUB_RUN_ID);
  const cancel = () => cancellation.abort();
  // Hold both native cancellation signals through the terminal Writer receipt,
  // not only until the dispatcher returns. A later force kill remains unknown.
  process.on('SIGINT', cancel); process.on('SIGTERM', cancel);
  try { return await runRouting({ ...options, signal: cancellation.signal, progress }); }
  catch (error) {
    // A failed Step projection can belong to a replay. This process did not
    // dispatch, but only Writer can report what it proved about that reservation.
    const failedProjection = error.details?.admissionEffect?.ready === 'not-attempted';
    error.details = { ...error.details,
      runId, target: error.details?.target ?? progress.target,
      routingStage: progress.workerPossible ? 'finalization' : 'authority',
      lastSuccessfulBoundary: error.details?.lastSuccessfulBoundary ?? progress.lastSuccessfulBoundary ?? 'controller-start',
      ...(!progress.workerPossible && !failedProjection
        ? { childState: 'not_started', containment: 'not_required', cleanup: 'not_required', retention: 'none' } : {}) };
    if (!error.details?.diagnosticStore && !error.details?.fallbackReference) {
      const env = options.env ?? process.env;
      const run = /^[1-9][0-9]{0,15}$/.test(env.GITHUB_RUN_ID ?? '') ? env.GITHUB_RUN_ID : 'unknown';
      const projectionAttempt = failedProjection ? error.details.failureDiagnostic?.executionId : undefined;
      try {
        const durable = await (options.persistRoutingFailure ?? options.persistFailure ?? persistAttemptFailureDiagnostic)({
          executionId: `routing-${run}-${randomUUID()}`, error, stage: error.details.routingStage,
          lastSuccessfulBoundary: error.details.lastSuccessfulBoundary });
        error.details = { ...error.details, ...durable, ...(projectionAttempt ? { executionId: projectionAttempt } : {}) };
      } catch { error.details.diagnosticRecorderFailed = true; }
    }
    if (error.code === 'OWNER_EVENT_REQUIRED') return { status: 'BLOCKED', code: error.code,
      phase: 'pre-worker-admission', worker: 'not_started', reason: error.reason, ...failureFacts(error),
      ...(Number.isSafeInteger(runId) && runId > 0 ? { runId } : {}),
      diagnosticStore: error.details?.diagnosticStore, fallbackReference: error.details?.fallbackReference };
    throw error;
  }
  finally { process.removeListener('SIGINT', cancel); process.removeListener('SIGTERM', cancel); }
}
async function runRouting({ env = process.env, readEvent = path => readFile(path, 'utf8'),
  createWriter = createLocalWriterAdapter, createDispatcher = createOnDemandDispatchAdapter,
  createJournal = () => createAttemptStore(EXECUTION_CONSUMER.paths.attemptRoot),
  resolveSlot = runnerExecutionSlot,
  persistFailure = persistAttemptFailureDiagnostic, prepare = prepareCheckout, collect, signal, progress = {} } = {}) {
  const rawEvent = await readEvent(env.GITHUB_EVENT_PATH);
  progress.lastSuccessfulBoundary = 'event-read';
  let event;
  try { event = JSON.parse(rawEvent); }
  catch (cause) { throw Object.assign(new Error('EVENT_PAYLOAD_INVALID', { cause }), { code: 'EVENT_PAYLOAD_INVALID' }); }
  progress.lastSuccessfulBoundary = 'event-parse';
  for (const [check, expected, observed, valid] of [
    ['repository', REPOSITORY, event?.repository?.full_name, event?.repository?.full_name === REPOSITORY],
    ['event', ['workflow_dispatch', 'issues', 'pull_request_target'], env.GITHUB_EVENT_NAME, ['workflow_dispatch', 'issues', 'pull_request_target'].includes(env.GITHUB_EVENT_NAME)],
    ['actor', OWNER, event?.sender?.login, event?.sender?.login === OWNER],
    ['head_branch', `refs/heads/${CONSUMER.baseBranch}`, env.GITHUB_REF, env.GITHUB_REF === `refs/heads/${CONSUMER.baseBranch}`]
  ]) if (!valid) throw Object.assign(new Error('OWNER_EVENT_REQUIRED'), { code: 'OWNER_EVENT_REQUIRED', reason: check,
    observation: { check, expected, observed: observed ?? null, availability: observed === undefined ? 'unavailable' : 'available' } });
  progress.lastSuccessfulBoundary = 'owner-event';
  const launch = env.GITHUB_EVENT_NAME === 'workflow_dispatch' ? parseLaunchInputs(event.inputs)
    : parseLabelLaunch(event, env.GITHUB_EVENT_NAME);
  progress.lastSuccessfulBoundary = 'route-parse';
  const executionSlot = resolveSlot({ runnerName: env.RUNNER_NAME });
  if (CONSUMER.executionSlots && executionSlot !== EXECUTION_SLOT) fail('EXECUTION_SLOT_IDENTITY_INVALID');
  const local = createWriter();
  // Construct inert adapters before admission so setup failures cannot strand
  // a consumed owner command without a controller or journal.
  const dispatcher = createDispatcher({ signal });
  const journal = createJournal();
  const broker = { invoke: request => traceRuntimeOperation(request.operation,
    () => local.invoke({ ...request, ...(executionSlot ? { executionSlot } : {}), workflowReadToken: env.GITHUB_TOKEN })) };
  let admitted;
  progress.lastSuccessfulBoundary = 'adapters-ready';
  try {
    admitted = await broker.invoke({ operation: 'admit', runId: Number(env.GITHUB_RUN_ID), workflowReadToken: env.GITHUB_TOKEN,
      ...launch });
  } catch (error) {
    // These live admission decisions prove no new execution was authorized.
    // The Actions warning is the safe surface when no Writer target is admitted.
    if (['OWNER_RUN_NOT_ADMITTED', 'ADMISSION_QUIESCED'].includes(error.code)) {
      const reason = ownerRunRejectionReason(error.code, error.details?.reason);
      if (!error.details?.diagnosticStore) {
        error.details = { ...error.details, childState: 'not_started', containment: 'not_required', cleanup: 'not_required', retention: 'none' };
        try {
          const durable = await persistFailure({ executionId: `routing-${randomUUID()}`, error, stage: 'authority', lastSuccessfulBoundary: 'owner-event' });
          error.details = { ...error.details, ...durable };
        } catch { error.details.diagnosticRecorderFailed = true; }
      }
      return { status: 'BLOCKED', code: error.code, phase: 'pre-worker-admission', worker: 'not_started',
        ...(Number.isSafeInteger(Number(env.GITHUB_RUN_ID)) && Number(env.GITHUB_RUN_ID) > 0 ? { runId: Number(env.GITHUB_RUN_ID) } : {}),
        diagnosticStore: error.details?.diagnosticStore, fallbackReference: error.details?.fallbackReference,
        ...failureFacts(error), ...(error.details?.diagnosticRecorderFailed ? { diagnosticRecorderFailed: true } : {}), ...(reason ? { reason } : {}) };
    }
    throw error;
  }
  progress.lastSuccessfulBoundary = 'admission';
  const envelope = admitted.envelope;
  progress.target = { kind: envelope?.target, number: envelope?.number };
  const warning = admitted.envelope?.admission?.warnings ?? admitted.envelope?.warnings;
  if (admitted.status === 'BLOCKED') { emitAdmissionWarnings(warning); return { ...admitted, runId: Number(env.GITHUB_RUN_ID), phase: 'pre-worker-admission', worker: 'not_started' }; }
  let failure;
  let result;
  try {
    progress.workerPossible = true;
    result = await runAttempt({ envelope: admitted.envelope, admissionResumed: admitted.resumed === true,
      admissionUnstarted: admitted.admissionUnstarted === true, broker,
      journal, persistFailure,
      prepare: e => traceRuntimeOperation('checkout-prepare', () => prepare(e)),
      execute: (e, lifecycle) => traceRuntimeOperation('governed-runtime', () => e.backend === 'app-server'
        ? executeCodex(e, { ...lifecycle, signal })
        : dispatcher.dispatch(e)),
      collect: collect ? e => traceRuntimeOperation('collect-progress', () => collect(e)) : (e => broker.invoke({
        operation: 'collect-progress', runId: e.runId, attemptId: e.attemptId })) });
  } catch (error) {
    failure = error;
    // The contender never owned this attempt. Its error cannot mutate the
    // active controller's diagnostics or release its Writer reservation.
    // Includes a failed journal write before/inside the normal catch path.
    // Never rerun the operation just because its normal evidence store failed.
    if (error.code !== 'ATTEMPT_CONTROLLER_BUSY'
      && !error.details?.fallbackReference && !error.details?.causal?.durable?.fallbackReference) {
      try {
        const durable = await persistFailure({ executionId: admitted.envelope.attemptId,
          error, stage: 'finalization', lastSuccessfulBoundary: error.details?.lastSuccessfulBoundary ?? 'admission' });
        error.details = { ...error.details, ...durable };
      } catch { error.details = { ...error.details, diagnosticRecorderFailed: true }; }
    }
  } finally {
    if (admitted.envelope.route === 'auto' && failure?.code !== 'ATTEMPT_CONTROLLER_BUSY') {
      // This is the last trusted controller operation, after containment,
      // collection, publication and the durable terminal runner receipt.
      // Root reads that receipt itself; caller JSON cannot assert completion.
      try { await broker.invoke({ operation: 'complete-execution', runId: admitted.envelope.runId, attemptId: admitted.envelope.attemptId }); }
      catch (error) {
        try {
          const durable = await persistFailure({ executionId: `${admitted.envelope.attemptId}-completion`,
            error, stage: 'finalization', lastSuccessfulBoundary: result ? 'outcome-publication'
              : failure?.details?.diagnostic?.lastSuccessfulBoundary ?? 'admission' });
          error.details = { ...error.details, ...durable };
        } catch { error.details = { ...error.details, diagnosticRecorderFailed: true }; }
        if (!failure && result?.status === 'BLOCKED' && result.diagnostic) {
          failure = Object.assign(new Error(result.code), { code: result.code, details: { diagnostic: result.diagnostic,
            outcomePublication: { status: 'published' }, target: result.target } });
        }
        if (failure) failure.details = { ...failure.details, admissionCompletion: { status: 'unknown', code: error.code ?? 'ADMISSION_COMPLETION_UNKNOWN' } };
        else {
          await describePostOutcomeFailure(error, envelope, journal, result);
          failure = error;
        }
      }
    }
  }
  try { emitAdmissionWarnings(warning); }
  catch (error) {
    if (!failure) throw error;
    failure.details = { ...failure.details, admissionWarnings: { status: 'unavailable', code: error.code ?? 'ADMISSION_WARNING_OUTPUT_FAILED' } };
  }
  if (failure) throw failure;
  return result?.status === 'BLOCKED'
    ? { ...result, runId: envelope.runId, target: result.target ?? progress.target }
    : result;
}
export async function reportRoutingResult(run, options = {}) {
  const { write = value => process.stdout.write(value), writeError = value => process.stderr.write(value),
    writeAnnotation = options.write || options.writeError ? () => {} : value => process.stdout.write(value) } = options;
  try {
    const value = await run();
    if (value?.status === 'BLOCKED') {
      const code = value.code ?? value.envelope?.admissionBlock?.code ?? value.diagnostic?.classification?.code;
      const admission = value.phase === 'pre-worker-admission' || ['OWNER_RUN_NOT_ADMITTED', 'OWNER_EVENT_REQUIRED', 'ADMISSION_QUIESCED'].includes(code);
      const diagnostic = value.diagnostic ?? { ...value, ...failureFacts({ details: value.envelope?.admissionBlock }), classification: { stage: admission ? 'authority' : 'finalization' },
        observed: { child: value.worker ?? (admission ? 'not_started' : 'unknown') }, durable: { diagnosticStore: value.diagnosticStore, fallbackReference: value.fallbackReference } };
      const target = value.target ?? (value.envelope ? { kind: value.envelope.target, number: value.envelope.number } : undefined);
      const knownUnbound = ['OWNER_EVENT_REQUIRED', 'OWNER_RUN_NOT_ADMITTED', 'ADMISSION_QUIESCED'].includes(code);
      const outcome = positive(value.outcomeId ?? value.outcome?.outcomeId) ? { status: 'published' } : undefined;
      const explanation = failureExplanation(code, diagnostic, { runId: value.runId, reason: value.reason, target, outcome, knownUnbound });
      writeError(annotation(admission ? 'Codex admission' : 'Codex outcome', explanation));
    }
    const warning = executionWarningSummary(value?.executionWarnings);
    if (warning) writeError(`::warning title=Codex execution::${warning}\n`);
    write(JSON.stringify(value?.diagnostic ? { ...value, diagnostic: routingDiagnostic(value.diagnostic) } : value) + '\n');
    return value?.status === 'BLOCKED' ? 1 : 0;
  } catch (error) {
    const code = /^[A-Z][A-Z0-9_]{0,79}$/.test(error?.code ?? '') ? error.code : 'ROUTING_FAILED';
    const detail = error.details ?? {};
    const diagnostic = detail.diagnostic ?? causalEvidence(error, {
      stage: detail.routingStage ?? 'authority', containment: detail.failureDiagnostic?.containment ?? detail.containment
    });
    const explanation = failureExplanation(code, diagnostic, { runId: detail.runId, reason: detail.reason,
      target: detail.target, outcome: detail.outcomePublication ?? diagnostic.outcomePublication });
    const secondary = detail.admissionCompletion ? ' Completion of the protected admission reservation is also unverified.' : '';
    // Keep exceptional stderr parseable. Actions consumes the stdout command.
    writeAnnotation(annotation('Relay routing', explanation + secondary));
    writeError(JSON.stringify({ status: 'blocked', orchestration: 'FAILED', code, diagnostic: routingDiagnostic(diagnostic) }) + '\n');
    return 1;
  }
}
function routingDiagnostic({ taskSummary, blockerSummary, validation, ...observation }) {
  // Task claims have their existing target-bound Outcome publication channel.
  return observation;
}

function annotation(title, explanation) {
  return `::error title=${title}::${explanation.replaceAll('%', '%25').replaceAll('\r', '%0D').replaceAll('\n', '%0A')}\n`;
}
function isMain() { try { return realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url)); } catch { return false; } }
if (isMain()) reportRoutingResult(main).then(code => { process.exitCode = code; });
