import { CONSUMER } from '../../consumer/consumer.mjs';
import { digest, positive, validateEnvelope, fail } from './execution-contract.mjs';
import { canonicalAuthorityJson, validateAdmissionSnapshot } from '../../contracts/src/github-authority.mjs';
import { authorizeRecovery, recoveryAuthorizationBody } from './publication-recovery.mjs';
import { revalidateAuthority, revalidateReadyEvent, assertPr, linkedIssue } from './live-authority.mjs';

// No ready-consumption intent means admit could not return to the controller.
// This is a durable ordering proof, not an inference from an absent process.
export function partialPredispatchRecord(r) {
  const e = r?.envelope;
  try { validateAdmissionSnapshot(e?.request, { repository: e?.repository, task: e?.issueNumber }); } catch { return false; }
  if (e.version !== 2 || !positive(e.runId) || !positive(e.step) || !positive(e.issueNumber)
    || !/^[a-f0-9]{64}$/.test(e.consumerDigest ?? '') || e.request.run_id !== String(e.runId)
    || e.request.attempt !== e.attemptId || e.request.step !== e.step || e.request.route !== e.route
    || e.request.branch !== e.branch || e.request.starting_head !== e.startHead
    || e.request.authority.sha256 !== e.authorityDigest) return false;
  const allowed = new Set(['envelope', 'nativeAdmission', 'stepProjectionFrom', 'controllerLifecycle',
    'prNumber', 'publicationIntent', 'publishedHead', 'finalHead', 'outcome', 'admissionFailure']);
  return e.request?.kind === 'admission' && e.route === 'auto' && e.transport === 'label'
    && e.attemptId === `run-${e.runId}` && positive(e.readyEventId) && r.nativeAdmission === true
    && canonicalAuthorityJson(r.controllerLifecycle) === canonicalAuthorityJson({ version: 1, status: 'active' })
    && Array.isArray(r.stepProjectionFrom) && r.stepProjectionFrom.length <= 1
    && r.stepProjectionFrom.every(label => /^step-[1-9][0-9]*$/.test(label))
    && Object.keys(r).every(key => allowed.has(key))
    && !r.publicationIntent && !r.publishedHead && !r.finalHead && !r.outcome
    && (r.prNumber === undefined || r.prNumber === e.continuation?.pullRequest);
}

export function predispatchBinding(r) {
  const e = r.envelope;
  return { operation: 'finalize-predispatch', repository: e.repository, runId: e.runId,
    attemptId: e.attemptId, issueNumber: e.issueNumber, step: e.step,
    executionSlot: e.executionSlot ?? 'primary', readyEventId: e.readyEventId,
    branch: e.branch, head: e.startHead, authorityDigest: e.authorityDigest,
    recordDigest: digest(r) };
}

// Preserve every original field, including the active historical lifecycle.
// This administrative receipt is neither a worker journal nor a Task Outcome.
export function completedPredispatchRecovery(record) {
  const { predispatchRecovery: recovery, ...original } = record ?? {};
  return partialPredispatchRecord(original) && recovery?.version === 1
    && recovery.status === 'finalized' && positive(recovery.authorizationId)
    && Number.isFinite(Date.parse(recovery.authorizedAt)) && Number.isFinite(Date.parse(recovery.completedAt))
    && Date.parse(recovery.completedAt) >= Date.parse(recovery.authorizedAt)
    && canonicalAuthorityJson(recovery.binding) === canonicalAuthorityJson(predispatchBinding(original));
}

export async function predispatchState({ api, journal, record: r, checkoutAbsent }) {
  if (!partialPredispatchRecord(r)) fail('PREDISPATCH_STATE_NOT_PROVEN');
  const e = validateEnvelope(r.envelope);
  const run = await api.getRun(e.runId);
  // A re-run could have entered an older runtime's replay path. Never infer its
  // behavior from the first run's retained partial record.
  if (run.status !== 'completed' || run.conclusion !== 'failure' || run.run_attempt !== 1)
    fail('PREDISPATCH_ORIGINAL_RUN_AMBIGUOUS');
  if (!journal || await journal.get(e.runId, e.repository) || !checkoutAbsent || !await checkoutAbsent(e))
    fail('PREDISPATCH_EXECUTION_EVIDENCE_CONFLICT');
  await revalidateAuthority(api, e);
  await revalidateReadyEvent(api, e);
  if ((await api.get(`/git/ref/heads/${e.branch}`)).object?.sha !== e.startHead)
    fail('REMOTE_HEAD_CHANGED');
  if (e.continuation?.pullRequest) {
    const pr = await api.get(`/pulls/${e.continuation.pullRequest}`);
    assertPr(pr, e.continuation.pullRequest);
    if (pr.head.sha !== e.startHead || pr.head.ref !== e.branch || pr.base.ref !== CONSUMER.baseBranch
      || linkedIssue(pr.body) !== e.issueNumber) fail('PR_AUTHORITY_CHANGED');
  }
  const binding = predispatchBinding(r);
  return { binding, authorizationBody: recoveryAuthorizationBody(binding) };
}

// Caller holds both the root Writer mutex and original controller lock. All
// external operations are GETs. One atomic record update is the only mutation.
export async function finalizePredispatch({ api, store, journal, record: r, request, checkoutAbsent,
  now = () => new Date().toISOString() }) {
  if (r.predispatchRecovery) {
    if (!completedPredispatchRecovery(r) || r.predispatchRecovery.authorizationId !== request.authorizationId)
      fail('PREDISPATCH_RECOVERY_BINDING_CHANGED');
    if (await journal.get(r.envelope.runId, r.envelope.repository) || !await checkoutAbsent(r.envelope))
      fail('PREDISPATCH_EXECUTION_EVIDENCE_CONFLICT');
    return r.predispatchRecovery;
  }
  const { binding } = await predispatchState({ api, journal, record: r, checkoutAbsent });
  const authorizedAt = await authorizeRecovery(api, r.envelope, request.authorizationId, binding);
  // Refresh the exact evidence after owner authorization reads, before commit.
  await predispatchState({ api, journal, record: r, checkoutAbsent });
  if (digest(await store.get(r.envelope.runId)) !== binding.recordDigest) fail('PREDISPATCH_RECOVERY_BINDING_CHANGED');
  r.predispatchRecovery = { version: 1, status: 'finalized', authorizationId: request.authorizationId,
    binding, authorizedAt, completedAt: now() };
  await store.put(r.envelope.runId, r);
  return r.predispatchRecovery;
}
