import { CONSUMER } from '../../consumer/consumer.mjs';
import { readFile } from 'node:fs/promises';
import { realpathSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { createLocalWriterAdapter } from './local-writer.mjs';
import { createOnDemandDispatchAdapter } from './github.mjs';
import { createAttemptStore } from './attempt-store.mjs';
import { runAttempt } from './attempt.mjs';
import { prepareCheckout, collectCheckout } from './attempt-runtime.mjs';
import { REPOSITORY, OWNER, causalEvidence } from './execution-contract.mjs';
import { emitAdmissionWarnings, executionWarningSummary } from './outcome.mjs';
import { parseLaunchInputs, parseLabelLaunch } from './launch-metadata.mjs';
import { persistAttemptFailureDiagnostic } from './attempt-diagnostic.mjs';

export async function main({ env = process.env, readEvent = path => readFile(path, 'utf8'),
  createWriter = createLocalWriterAdapter, createDispatcher = createOnDemandDispatchAdapter,
  createJournal = () => createAttemptStore(CONSUMER.paths.attemptRoot),
  persistFailure = persistAttemptFailureDiagnostic, prepare = prepareCheckout, collect = collectCheckout } = {}) {
  const event = JSON.parse(await readEvent(env.GITHUB_EVENT_PATH));
  if (event.repository?.full_name !== REPOSITORY || !['workflow_dispatch', 'issues', 'pull_request_target'].includes(env.GITHUB_EVENT_NAME)
    || event.sender?.login !== OWNER || env.GITHUB_REF !== `refs/heads/${CONSUMER.baseBranch}`) return { status: 'BLOCKED', code: 'OWNER_EVENT_REQUIRED' };
  const launch = env.GITHUB_EVENT_NAME === 'workflow_dispatch' ? parseLaunchInputs(event.inputs)
    : parseLabelLaunch(event, env.GITHUB_EVENT_NAME);
  const local = createWriter();
  const broker = { invoke: request => local.invoke({ ...request, workflowReadToken: env.GITHUB_TOKEN }) };
  let admitted;
  try {
    admitted = await broker.invoke({ operation: 'admit', runId: Number(env.GITHUB_RUN_ID), workflowReadToken: env.GITHUB_TOKEN,
      ...launch });
  } catch (error) {
    // These live admission decisions prove no new execution was authorized.
    // The Actions warning is the safe surface when no Writer target is admitted.
    if (['OWNER_RUN_NOT_ADMITTED', 'ADMISSION_QUIESCED'].includes(error.code)) return { status: 'BLOCKED', code: error.code };
    throw error;
  }
  emitAdmissionWarnings(admitted.envelope?.admission?.warnings ?? admitted.envelope?.warnings);
  if (admitted.status === 'BLOCKED') return admitted;
  const dispatcher = createDispatcher();
  let failure;
  try {
    return await runAttempt({ envelope: admitted.envelope, admissionResumed: admitted.resumed === true, broker,
      journal: createJournal(), persistFailure,
      prepare, execute: e => dispatcher.dispatch(e), collect });
  } catch (error) {
    failure = error;
    // Includes a failed journal write before/inside the normal catch path.
    // Never rerun the operation just because its normal evidence store failed.
    if (!error.details?.fallbackReference && !error.details?.causal?.durable?.fallbackReference) {
      const durable = await persistFailure({ executionId: admitted.envelope.attemptId,
        error, stage: 'finalization', lastSuccessfulBoundary: error.details?.lastSuccessfulBoundary ?? 'admission' });
      error.details = { ...error.details, ...durable };
    }
    throw error;
  } finally {
    if (admitted.envelope.route === 'auto') {
      // This is the last trusted controller operation, after containment,
      // collection, publication and the durable terminal runner receipt.
      // Root reads that receipt itself; caller JSON cannot assert completion.
      try { await broker.invoke({ operation: 'complete-execution', runId: admitted.envelope.runId, attemptId: admitted.envelope.attemptId }); }
      catch (error) {
        if (!failure) throw error;
        failure.details = { ...failure.details, admissionCompletion: { status: 'unknown', code: error.code ?? 'ADMISSION_COMPLETION_UNKNOWN' } };
      }
    }
  }
}
export async function reportRoutingResult(run, { write = value => process.stdout.write(value), writeError = value => process.stderr.write(value) } = {}) {
  try {
    const value = await run();
    if (value?.status === 'BLOCKED') {
      const code = value.code ?? value.envelope?.admissionBlock?.code;
      writeError(code === 'ADMISSION_QUIESCED'
        ? '::warning title=Codex admission::Automatic admission is quiesced; no worker started.\n'
        : `::warning title=Codex outcome::BLOCKED; task remains incomplete${/^[A-Z][A-Z0-9_]{0,79}$/.test(code ?? '') ? ` (${code})` : ''}. Reconcile the terminal Outcome before another attempt.\n`);
    }
    const warning = executionWarningSummary(value?.executionWarnings);
    if (warning) writeError(`::warning title=Codex execution::${warning}\n`);
    write(JSON.stringify(value) + '\n');
    return 0;
  } catch (error) {
    writeError(JSON.stringify({ status: 'blocked', orchestration: 'FAILED', code: /^[A-Z][A-Z0-9_]{0,79}$/.test(error?.code ?? '') ? error.code : 'ROUTING_FAILED', diagnostic: error.details?.diagnostic ?? causalEvidence(error) }) + '\n');
    return 1;
  }
}
function isMain() { try { return realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url)); } catch { return false; } }
if (isMain()) reportRoutingResult(main).then(code => { process.exitCode = code; });
