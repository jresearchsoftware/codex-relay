import { CONSUMER, EXECUTION_CONSUMER, EXECUTION_SLOT, executionConsumer, runnerExecutionSlot } from '../../consumer/consumer.mjs';
import { realpathSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { createAttemptStore } from './attempt-store.mjs';
import { collectCheckout } from './attempt-runtime.mjs';
import { createLocalWriterAdapter } from './local-writer.mjs';
import { reportRoutingResult } from './entrypoint.mjs';
import { causalEvidence, digest, fail, positive, validateEnvelope } from './execution-contract.mjs';
import { failureDiagnosticFromDetails } from './diagnostics.mjs';
import { normalizeCodexUsage } from './codex-usage.mjs';

export function parseRecoveryRequest(request) {
  if (!request || !positive(request.runId) || !/^(?:event|run)-[1-9][0-9]*$/.test(request.attemptId ?? '')) fail('RECOVERY_REQUEST_INVALID');
  const keys = Object.keys(request).sort().join(',');
  if (request.operation === 'inspect' && keys === 'attemptId,operation,runId') return request;
  if (keys === 'attemptId,authorizationId,runId' && positive(request.authorizationId)) return request;
  if (request.operation === 'inspect-prepublication' && keys === 'attemptId,head,operation,runId'
    && /^[a-f0-9]{40}$/.test(request.head ?? '')) return request;
  if (request.operation === 'recover-prepublication' && keys === 'attemptId,authorizationId,head,operation,runId'
    && positive(request.authorizationId) && /^[a-f0-9]{40}$/.test(request.head ?? '')) return request;
  fail('RECOVERY_REQUEST_INVALID');
}

// An explicit operator entrypoint, never called by the router or ordinary replay.
// It has no prepare/execute callback: the original child receipt is mandatory.
export async function recoverAttemptPublication(options) {
  // Ordinary replay and explicit recovery share the same private journal.
  // Serialize before reading it or obtaining a Writer recovery receipt; a
  // contender cannot overwrite the active controller's returned evidence.
  if (options.journal.withLock) {
    return options.journal.withLock(options.runId, () => recoverLockedPublication(options));
  }
  return recoverLockedPublication(options);
}

async function recoverLockedPublication(options) {
  const outcome = await recoverContainedPublication(options);
  return options.broker.invoke({ operation: 'complete-handoff', runId: options.runId, attemptId: options.attemptId });
}

async function recoverContainedPublication({ runId, attemptId, authorizationId, broker, journal, collect }) {
  if (!positive(runId) || !/^(?:event|run)-[1-9][0-9]*$/.test(attemptId ?? '') || !positive(authorizationId)) fail('RECOVERY_REQUEST_INVALID');
  const invoke = (operation, value = {}) => broker.invoke({ operation, runId, attemptId, ...value });
  const state = await invoke('publication-state', { authorizationId });
  const e = validateEnvelope(state.envelope);
  if (CONSUMER.executionSlots && (e.executionSlot ?? 'primary') !== EXECUTION_SLOT) {
    const original = CONSUMER.executionSlots.find(slot => slot.id === (e.executionSlot ?? 'primary'));
    const current = CONSUMER.executionSlots.find(slot => slot.id === EXECUTION_SLOT);
    if (!CONSUMER.generalRunnerPool || !original || !current || original.runnerUser !== current.runnerUser) fail('EXECUTION_SLOT_BINDING_CHANGED');
  }
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
    if (typeof progress.clean !== 'boolean') fail('WORKTREE_STATE_UNKNOWN');
    record.collection = { head: progress.head, clean: progress.clean === true };
    record.progress.clean = progress.clean === true;
    if (!progress.clean && execution.result?.status !== 'success') fail('UNCOMMITTED_WORK_REMAINS');
    if (execution.result?.status !== 'success') fail(execution.errorCode ?? 'SEMANTIC_RESULT_BLOCKED');
    record.outcome = await invoke('finish', { head: published.publishedHead, recoveryAuthorizationId: authorizationId,
      codexUsage: normalizeCodexUsage(execution.codexUsage),
      executionWarnings: progress.clean ? [] : ['UNCOMMITTED_WORK_REMAINS'],
      taskResult: { summary: execution.result.summary, validation: execution.result.validation } });
    record.progress.prNumber = record.outcome.prNumber;
    record.diagnostic = null;
    await journal.put(runId, record);
    return record.outcome;
  } catch (error) {
    const failureDiagnostic = failureDiagnosticFromDetails(error?.details);
    record.diagnostic = { ...causalEvidence(error, { child: execution.child, containment: execution.containment,
      publishedHead: record.progress?.head, stage: 'writer-publication' }),
      orchestration: 'FAILED', codexUsage: normalizeCodexUsage(execution.codexUsage),
      ...(failureDiagnostic ? { publicationRecovery: failureDiagnostic } : {}) };
    await journal.put(runId, record);
    error.details = { ...error.details, diagnostic: record.diagnostic };
    throw error;
  }
}

export async function publicationRecoveryJournal(request, broker, { createStore = createAttemptStore } = {}) {
  let journalRoot = EXECUTION_CONSUMER.paths.attemptRoot;
  if (CONSUMER.generalRunnerPool) {
    // Current physical runner capacity is independent of retained resource
    // slots. Obtain the original slot solely from protected Writer state.
    const state = await broker.invoke({ operation: 'publication-state', runId: request.runId,
      attemptId: request.attemptId, authorizationId: request.authorizationId });
    const original = validateEnvelope(state.envelope);
    journalRoot = executionConsumer(original.executionSlot).paths.attemptRoot;
  }
  return createStore(journalRoot);
}

export async function main() {
  if (process.argv.length !== 2) fail('RECOVERY_REQUEST_INVALID');
  let bytes = 0; const chunks = [];
  for await (const chunk of process.stdin) {
    bytes += chunk.length; if (bytes > 4096) fail('RECOVERY_REQUEST_INVALID'); chunks.push(chunk);
  }
  let request;
  try { request = JSON.parse(Buffer.concat(chunks).toString('utf8')); } catch { fail('RECOVERY_REQUEST_INVALID'); }
  parseRecoveryRequest(request);
  const local = createLocalWriterAdapter();
  const executionSlot = runnerExecutionSlot();
  const broker = { invoke: value => local.invoke({ ...value, ...(executionSlot ? { executionSlot } : {}), workflowReadToken: process.env.GITHUB_TOKEN }) };
  if (request.operation === 'inspect-prepublication') {
    return broker.invoke({ ...request, operation: 'prepublication-state' });
  }
  if (request.operation === 'recover-prepublication') return broker.invoke(request);
  if (request.operation === 'inspect' && Object.keys(request).sort().join(',') === 'attemptId,operation,runId') {
    const state = await broker.invoke({ operation: 'publication-state', runId: request.runId, attemptId: request.attemptId });
    return { repository: state.repository, runId: request.runId, attemptId: request.attemptId,
      ...(CONSUMER.executionSlots ? { executionSlot: state.envelope.executionSlot ?? 'primary' } : {}),
      publicationIntent: state.publicationIntent, publishedHead: state.publishedHead, authorizationBody: state.authorizationBody };
  }
  if (Object.keys(request).sort().join(',') !== 'attemptId,authorizationId,runId') fail('RECOVERY_REQUEST_INVALID');
  return recoverAttemptPublication({ ...request, broker,
    journal: await publicationRecoveryJournal(request, broker), collect: collectCheckout });
}

function isMain() { try { return realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url)); } catch { return false; } }
if (isMain()) reportRoutingResult(main).then(code => { process.exitCode = code; });
