import { CONSUMER } from '../../consumer/consumer.mjs';
import { realpathSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { createAttemptStore } from './attempt-store.mjs';
import { collectCheckout } from './attempt-runtime.mjs';
import { createLocalWriterAdapter } from './local-writer.mjs';
import { reportRoutingResult } from './entrypoint.mjs';
import { causalEvidence, digest, fail, positive, validateEnvelope } from './execution-contract.mjs';
import { failureDiagnosticFromDetails } from './diagnostics.mjs';

// An explicit operator entrypoint, never called by the router or ordinary replay.
// It has no prepare/execute callback: the original child receipt is mandatory.
export async function recoverAttemptPublication({ runId, attemptId, authorizationId, broker, journal, collect }) {
  if (!positive(runId) || !/^(?:event|run)-[1-9][0-9]*$/.test(attemptId ?? '') || !positive(authorizationId)) fail('RECOVERY_REQUEST_INVALID');
  const invoke = (operation, value = {}) => broker.invoke({ operation, runId, attemptId, ...value });
  const state = await invoke('publication-state', { authorizationId });
  const e = validateEnvelope(state.envelope);
  const record = await journal.get(runId);
  if (!record || record.version !== e.version || digest(record.envelope) !== digest(e)) fail('JOURNAL_BINDING_CHANGED');
  const execution = record.execution;
  if (execution?.reserved !== true || execution.returned !== true || execution.child !== 'started'
    || execution.containment !== 'reaped') fail('RECOVERY_EXECUTION_NOT_PROVEN');
  let progress;
  try {
    // A consumed authorization is replayed at the Writer before touching the
    // checkout. In particular, an uncertain/crashed recovery cannot recollect
    // a replacement candidate or accidentally push it.
    if (!state.recovery) {
      if (!state.publicationIntent || record.collection?.head !== state.publicationIntent.head) fail('RECOVERY_CANDIDATE_CHANGED');
      progress = await collect(e);
      if (progress.head !== state.publicationIntent.head) fail('RECOVERY_CANDIDATE_CHANGED');
    }
    const published = await invoke('recover-publication', { authorizationId, ...(progress ? { bundle: progress.bundle } : {}) });
    if (record.outcome?.status === 'IMPLEMENTED_PENDING_FRESH_REVIEW' && record.outcome.head === published.publishedHead) return record.outcome;
    record.progress = { head: published.publishedHead, clean: false };
    await journal.put(runId, record);
    progress ??= await collect(e);
    if (progress.head !== published.publishedHead) fail('RECOVERY_CANDIDATE_CHANGED');
    record.collection = { head: progress.head, clean: progress.clean === true };
    record.progress.clean = progress.clean === true;
    if (!progress.clean) fail('UNCOMMITTED_WORK_REMAINS');
    if (execution.result?.status !== 'success') fail(execution.errorCode ?? 'SEMANTIC_RESULT_BLOCKED');
    record.outcome = await invoke('finish', { head: published.publishedHead, recoveryAuthorizationId: authorizationId,
      taskResult: { summary: execution.result.summary, validation: execution.result.validation } });
    record.progress.prNumber = record.outcome.prNumber;
    record.diagnostic = null;
    await journal.put(runId, record);
    return record.outcome;
  } catch (error) {
    const failureDiagnostic = failureDiagnosticFromDetails(error?.details);
    record.diagnostic = { ...causalEvidence(error, { child: execution.child, containment: execution.containment,
      publishedHead: record.progress?.head, stage: 'writer-publication' }),
      orchestration: 'FAILED', ...(failureDiagnostic ? { publicationRecovery: failureDiagnostic } : {}) };
    await journal.put(runId, record);
    error.details = { ...error.details, diagnostic: record.diagnostic };
    throw error;
  }
}

export async function main() {
  if (process.argv.length !== 2) fail('RECOVERY_REQUEST_INVALID');
  let bytes = 0; const chunks = [];
  for await (const chunk of process.stdin) {
    bytes += chunk.length; if (bytes > 4096) fail('RECOVERY_REQUEST_INVALID'); chunks.push(chunk);
  }
  let request;
  try { request = JSON.parse(Buffer.concat(chunks).toString('utf8')); } catch { fail('RECOVERY_REQUEST_INVALID'); }
  if (!request || !positive(request.runId) || !/^(?:event|run)-[1-9][0-9]*$/.test(request.attemptId ?? '')) fail('RECOVERY_REQUEST_INVALID');
  const local = createLocalWriterAdapter();
  const broker = { invoke: value => local.invoke({ ...value, workflowReadToken: process.env.GITHUB_TOKEN }) };
  if (request.operation === 'inspect' && Object.keys(request).sort().join(',') === 'attemptId,operation,runId') {
    const state = await broker.invoke({ operation: 'publication-state', runId: request.runId, attemptId: request.attemptId });
    return { repository: state.repository, runId: request.runId, attemptId: request.attemptId,
      publicationIntent: state.publicationIntent, publishedHead: state.publishedHead, authorizationBody: state.authorizationBody };
  }
  if (Object.keys(request).sort().join(',') !== 'attemptId,authorizationId,runId') fail('RECOVERY_REQUEST_INVALID');
  return recoverAttemptPublication({ ...request, broker,
    journal: createAttemptStore(CONSUMER.paths.attemptRoot), collect: collectCheckout });
}

function isMain() { try { return realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url)); } catch { return false; } }
if (isMain()) reportRoutingResult(main).then(code => { process.exitCode = code; });
