import { CONSUMER, EXECUTION_CONSUMER, EXECUTION_SLOT, runnerExecutionSlot } from '../../consumer/consumer.mjs';
import { readFile } from 'node:fs/promises';
import { realpathSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { createLocalWriterAdapter } from './local-writer.mjs';
import { createOnDemandDispatchAdapter } from './github.mjs';
import { createAttemptStore } from './attempt-store.mjs';
import { runAttempt } from './attempt.mjs';
import { prepareCheckout } from './attempt-runtime.mjs';
import { REPOSITORY, OWNER, causalEvidence, fail } from './execution-contract.mjs';
import { emitAdmissionWarnings, executionWarningSummary } from './outcome.mjs';
import { parseLaunchInputs, parseLabelLaunch } from './launch-metadata.mjs';
import { persistAttemptFailureDiagnostic } from './attempt-diagnostic.mjs';
import { ownerRunRejectionReason } from './owner-run-rejection.mjs';
import { randomUUID } from 'node:crypto';

export async function main(options = {}) {
  const cancellation = new AbortController();
  const progress = { workerPossible: false };
  const cancel = () => cancellation.abort();
  // Hold both native cancellation signals through the terminal Writer receipt,
  // not only until the dispatcher returns. A later force kill remains unknown.
  process.on('SIGINT', cancel); process.on('SIGTERM', cancel);
  try { return await runRouting({ ...options, signal: cancellation.signal, progress }); }
  catch (error) {
    if (!error.details?.diagnosticStore && !error.details?.fallbackReference) {
      const env = options.env ?? process.env;
      const run = /^[1-9][0-9]{0,15}$/.test(env.GITHUB_RUN_ID ?? '') ? env.GITHUB_RUN_ID : 'unknown';
      if (!progress.workerPossible) error.details = { ...error.details, childState: 'not_started', containment: 'not_required', cleanup: 'not_required', retention: 'none' };
      const durable = await (options.persistRoutingFailure ?? options.persistFailure ?? persistAttemptFailureDiagnostic)({
        executionId: `routing-${run}-${randomUUID()}`, error, stage: progress.workerPossible ? 'finalization' : 'authority',
        lastSuccessfulBoundary: progress.lastSuccessfulBoundary ?? 'controller-start' });
      error.details = { ...error.details, ...durable };
    }
    if (error.code === 'OWNER_EVENT_REQUIRED') return { status: 'BLOCKED', code: error.code,
      phase: 'pre-worker-admission', worker: 'not_started', reason: error.reason,
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
  const event = JSON.parse(rawEvent);
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
  const broker = { invoke: request => local.invoke({ ...request, ...(executionSlot ? { executionSlot } : {}), workflowReadToken: env.GITHUB_TOKEN }) };
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
        const durable = await persistFailure({ executionId: `routing-${randomUUID()}`, error, stage: 'authority', lastSuccessfulBoundary: 'owner-event' });
        error.details = { ...error.details, ...durable };
      }
      return { status: 'BLOCKED', code: error.code, phase: 'pre-worker-admission', worker: 'not_started',
        ...(Number.isSafeInteger(Number(env.GITHUB_RUN_ID)) && Number(env.GITHUB_RUN_ID) > 0 ? { runId: Number(env.GITHUB_RUN_ID) } : {}),
        diagnosticStore: error.details?.diagnosticStore, fallbackReference: error.details?.fallbackReference, ...(reason ? { reason } : {}) };
    }
    throw error;
  }
  progress.lastSuccessfulBoundary = 'admission';
  const warning = admitted.envelope?.admission?.warnings ?? admitted.envelope?.warnings;
  if (admitted.status === 'BLOCKED') { emitAdmissionWarnings(warning); return { ...admitted, phase: 'pre-worker-admission', worker: 'not_started' }; }
  let failure;
  let result;
  try {
    progress.workerPossible = true;
    result = await runAttempt({ envelope: admitted.envelope, admissionResumed: admitted.resumed === true,
      admissionUnstarted: admitted.admissionUnstarted === true, broker,
      journal, persistFailure,
      prepare, execute: e => dispatcher.dispatch(e), collect: collect ?? (e => broker.invoke({
        operation: 'collect-progress', runId: e.runId, attemptId: e.attemptId })) });
  } catch (error) {
    failure = error;
    // The contender never owned this attempt. Its error cannot mutate the
    // active controller's diagnostics or release its Writer reservation.
    // Includes a failed journal write before/inside the normal catch path.
    // Never rerun the operation just because its normal evidence store failed.
    if (error.code !== 'ATTEMPT_CONTROLLER_BUSY'
      && !error.details?.fallbackReference && !error.details?.causal?.durable?.fallbackReference) {
      const durable = await persistFailure({ executionId: admitted.envelope.attemptId,
        error, stage: 'finalization', lastSuccessfulBoundary: error.details?.lastSuccessfulBoundary ?? 'admission' });
      error.details = { ...error.details, ...durable };
    }
  } finally {
    if (admitted.envelope.route === 'auto' && failure?.code !== 'ATTEMPT_CONTROLLER_BUSY') {
      // This is the last trusted controller operation, after containment,
      // collection, publication and the durable terminal runner receipt.
      // Root reads that receipt itself; caller JSON cannot assert completion.
      try { await broker.invoke({ operation: 'complete-execution', runId: admitted.envelope.runId, attemptId: admitted.envelope.attemptId }); }
      catch (error) {
        const durable = await persistFailure({ executionId: `${admitted.envelope.attemptId}-completion`,
          error, stage: 'finalization', lastSuccessfulBoundary: 'terminal-handoff' });
        error.details = { ...error.details, ...durable };
        if (!failure) failure = error;
        else failure.details = { ...failure.details, admissionCompletion: { status: 'unknown', code: error.code ?? 'ADMISSION_COMPLETION_UNKNOWN' } };
      }
    }
  }
  try { emitAdmissionWarnings(warning); }
  catch (error) {
    if (!failure) throw error;
    failure.details = { ...failure.details, admissionWarnings: { status: 'unavailable', code: error.code ?? 'ADMISSION_WARNING_OUTPUT_FAILED' } };
  }
  if (failure) throw failure;
  return result;
}
export async function reportRoutingResult(run, options = {}) {
  const { write = value => process.stdout.write(value), writeError = value => process.stderr.write(value),
    writeAnnotation = options.write || options.writeError ? () => {} : value => process.stdout.write(value) } = options;
  try {
    const value = await run();
    if (value?.status === 'BLOCKED') {
      const code = value.code ?? value.envelope?.admissionBlock?.code;
      writeError(code === 'ADMISSION_QUIESCED'
        ? '::error title=Codex admission::Automatic admission is quiesced; no worker started. Inspect the lifecycle gate before another owner command.\n'
        : code === 'OWNER_RUN_NOT_ADMITTED'
          ? `::error title=Codex admission::OWNER_RUN_NOT_ADMITTED${ownerRunRejectionReason(code, value.reason) ? ` (${value.reason})` : ''}; no worker started and no target-bound Outcome was authorized. Inspect the original owner run and configured admission expectations before any fresh owner command.\n`
          : `::error title=Codex outcome::BLOCKED; task remains incomplete${/^[A-Z][A-Z0-9_]{0,79}$/.test(code ?? '') ? ` (${code})` : ''}. Inspect the diagnostic reference and reconcile the terminal Outcome when authorized before another attempt.\n`);
    }
    const warning = executionWarningSummary(value?.executionWarnings);
    if (warning) writeError(`::warning title=Codex execution::${warning}\n`);
    write(JSON.stringify(value) + '\n');
    return value?.status === 'BLOCKED' ? 1 : 0;
  } catch (error) {
    const code = /^[A-Z][A-Z0-9_]{0,79}$/.test(error?.code ?? '') ? error.code : 'ROUTING_FAILED';
    const diagnostic = error.details?.diagnostic ?? causalEvidence(error);
    const action = code.startsWith('GITHUB_')
      ? 'Inspect the retained native API response and configured actor access; reconcile any uncertain mutation before recovery.'
      : code.includes('CONFIG') || code.startsWith('EXECUTION_SLOT_')
        ? 'Inspect the selected consumer configuration and reported field through the authorized host reader before correcting the caller configuration.'
        : code === 'TRUSTED_GIT_FAILED'
          ? 'Inspect the original Git output and branch observations in protected diagnostics before selecting the supported correction.'
          : 'Inspect the protected diagnostic reference and original attempt before selecting a supported correction or recovery.';
    // Keep the exceptional stderr envelope parseable by existing collectors.
    // Actions consumes the separate stdout annotation command.
    writeAnnotation(`::error title=Relay routing::${code}; the requested operation did not complete. ${action}\n`);
    writeError(JSON.stringify({ status: 'blocked', orchestration: 'FAILED', code, diagnostic }) + '\n');
    return 1;
  }
}
function isMain() { try { return realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url)); } catch { return false; } }
if (isMain()) reportRoutingResult(main).then(code => { process.exitCode = code; });
