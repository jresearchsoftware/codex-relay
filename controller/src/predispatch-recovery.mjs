import { CONSUMER } from '../../consumer/consumer.mjs';
import { digest, positive, validateEnvelope, fail, OWNER, WRITER } from './execution-contract.mjs';
import { canonicalAuthorityJson, validateAdmissionSnapshot, sha256Body } from '../../contracts/src/github-authority.mjs';
import { PUBLICATION_RENDERER_VERSION } from '../../contracts/src/publication-rendering.mjs';
import { authorizeRecovery, recoveryAuthorizationBody } from './publication-recovery.mjs';
import { revalidateAuthority, revalidateReadyEvent, readyTransitions, assertPr, linkedIssue } from './live-authority.mjs';
import { labelNames, READY_LABELS } from './step-metadata.mjs';

const AUTHORITY_DRIFT_FIELDS = new Set(['purpose', 'scope', 'boundaries', 'validation', 'model', 'effort', 'subagents',
  'branch', 'base_sha', 'starting_head', 'existing_pr', 'issue_closure_policy', 'continuation']);

function validAuthorityDrift(drift) {
  if (drift === undefined) return true;
  if (!drift || typeof drift !== 'object' || Array.isArray(drift)
    || Object.keys(drift).sort().join(',') !== 'changed_fields,current_authority,review_required'
    || !drift.current_authority || typeof drift.current_authority !== 'object' || Array.isArray(drift.current_authority)
    || !Array.isArray(drift.changed_fields)
    || drift.changed_fields.some((field, index) => !AUTHORITY_DRIFT_FIELDS.has(field)
      || index > 0 && drift.changed_fields[index - 1] >= field)
    || drift.review_required !== (drift.changed_fields.length > 0)) return false;
  return true;
}

// No ready-consumption intent means admit could not return to the controller.
// This is a durable ordering proof, not an inference from an absent process.
export function partialPredispatchRecord(r) {
  const { authorityDrift, ...record } = r ?? {};
  const e = record.envelope;
  try { validateAdmissionSnapshot(e?.request, { repository: e?.repository, task: e?.issueNumber }); } catch { return false; }
  if (e.version !== 2 || !positive(e.runId) || !positive(e.step) || !positive(e.issueNumber)
    || !/^[a-f0-9]{64}$/.test(e.consumerDigest ?? '') || e.request.run_id !== String(e.runId)
    || e.request.attempt !== e.attemptId || e.request.step !== e.step || e.request.route !== e.route
    || e.request.branch !== e.branch || e.request.starting_head !== e.startHead
    || e.request.authority.sha256 !== e.authorityDigest) return false;
  const allowed = new Set(['envelope', 'nativeAdmission', 'stepProjectionFrom', 'controllerLifecycle',
    'prNumber', 'publicationIntent', 'publishedHead', 'finalHead', 'outcome', 'admissionFailure']);
  return validAuthorityDrift(authorityDrift)
    && e.request?.kind === 'admission' && e.route === 'auto' && e.transport === 'label'
    && e.attemptId === `run-${e.runId}` && positive(e.readyEventId) && record.nativeAdmission === true
    && (record.controllerLifecycle === undefined
      || canonicalAuthorityJson(record.controllerLifecycle) === canonicalAuthorityJson({ version: 1, status: 'active' }))
    && Array.isArray(record.stepProjectionFrom) && record.stepProjectionFrom.length <= 1
    && record.stepProjectionFrom.every(label => /^step-[1-9][0-9]*$/.test(label))
    && Object.keys(record).every(key => allowed.has(key))
    && !record.publicationIntent && !record.publishedHead && !record.finalHead && !record.outcome
    && (record.prNumber === undefined || record.prNumber === e.continuation?.pullRequest);
}

// A new Writer records this boundary before projection or command deletion.
// While it remains present, admit cannot have returned a launchable envelope.
// Callers must hold the Writer lock and check for a contradictory journal.
export function pendingPredispatchRecord(record) {
  const { predispatchPending: pending, stepProjected, stepProjectionSupersededBy,
    readyConsumption, ...original } = record ?? {};
  if (pending?.version !== 1 || Object.keys(pending).sort().join(',') !== 'projectionFrom,version'
    || !Array.isArray(pending.projectionFrom)
    || stepProjected !== undefined && stepProjected !== true
    || stepProjectionSupersededBy !== undefined && stepProjectionSupersededBy !== null
      && !/^run-[1-9][0-9]*$/.test(stepProjectionSupersededBy)
    || readyConsumption !== undefined && (readyConsumption?.status !== 'deleting'
      || readyConsumption.eventId !== original.envelope?.readyEventId
      || readyConsumption.label !== original.envelope?.readyLabel
      || Object.keys(readyConsumption).sort().join(',') !== 'eventId,label,status')) return false;
  if (original.stepProjectionFrom !== undefined
    && canonicalAuthorityJson(original.stepProjectionFrom) !== canonicalAuthorityJson(pending.projectionFrom)) return false;
  original.stepProjectionFrom = pending.projectionFrom;
  return partialPredispatchRecord(original);
}

// A successful ready-label removal may race a lost admit response. Validate
// the durable Writer marker independently from later execution/publication
// receipts so a terminal controller can retire the same reservation.
export function consumedPredispatchMarker(record) {
  const { predispatchPending: pending, stepProjected, stepProjectionFrom,
    stepProjectionSupersededBy, readyConsumption, readyConsumed } = record ?? {};
  if (pending?.version !== 1 || Object.keys(pending).sort().join(',') !== 'projectionFrom,version'
    || !Array.isArray(pending.projectionFrom) || pending.projectionFrom.length > 1
    || pending.projectionFrom.some(label => !/^step-[1-9][0-9]*$/.test(label)) || stepProjected !== true
    || stepProjectionFrom !== undefined || stepProjectionSupersededBy !== undefined && stepProjectionSupersededBy !== null
    || readyConsumed !== true || readyConsumption?.status !== 'consumed'
    || readyConsumption.eventId !== record?.envelope?.readyEventId
    || readyConsumption.label !== record?.envelope?.readyLabel
    || !positive(readyConsumption.removalEventId) || readyConsumption.removalEventId <= record?.envelope?.readyEventId
    || Object.keys(readyConsumption).sort().join(',') !== 'eventId,label,removalEventId,status') return false;
  return true;
}

// Before worker dispatch the full record must still be the original admission
// projection. This excludes any checkout, publication, or terminal receipt.
export function consumedPredispatchRecord(record) {
  if (!consumedPredispatchMarker(record)) return false;
  const original = { ...(record ?? {}) };
  const pending = original.predispatchPending;
  delete original.predispatchPending;
  delete original.stepProjected;
  delete original.stepProjectionFrom;
  delete original.stepProjectionSupersededBy;
  delete original.readyConsumption;
  delete original.readyConsumed;
  original.stepProjectionFrom = pending.projectionFrom;
  return partialPredispatchRecord(original);
}

// A failed DELETE or Outcome may leave native side effects uncertain, but the
// marker still proves that this Writer never handed out worker authority.
// This narrower predicate releases only the physical slot; it says nothing
// about whether the external command/comment needs reconciliation.
export function predispatchNoWorkerRecord(record) {
  if (pendingPredispatchRecord(record)) return true;
  const { readyConsumption, controllerLifecycle, outcome, commentIntent, commentBodies,
    lifecycleIntent, ...pending } = record ?? {};
  if (readyConsumption?.status !== 'uncertain'
    || readyConsumption.eventId !== pending.envelope?.readyEventId
    || readyConsumption.label !== pending.envelope?.readyLabel
    || canonicalAuthorityJson(controllerLifecycle) !== canonicalAuthorityJson({
      version: 1, status: 'complete', child: 'not_started', containment: 'not_required' })) return false;
  pending.controllerLifecycle = { version: 1, status: 'active' };
  pending.outcome = null;
  return pendingPredispatchRecord(pending);
}

// A verified replacement and sealed terminal Outcome preserve the prior
// ready race. A distinct, freshly revalidated event may then be admitted.
export function predispatchReadyReplacementReported(record) {
  return Boolean(replacementOutcomeCandidate(record));
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
  const comment = [3, 4].includes(recovery?.version) ? outcomeReconciliationCandidate(original) : null;
  const replacement = recovery?.version === 4 ? replacementOutcomeCandidate(original) : null;
  const base = recovery?.version === 4 ? Boolean(replacement)
    : recovery?.version === 3 ? Boolean(comment)
    : recovery?.version === 2 ? readyReconciliationCandidate(original) : partialPredispatchRecord(original);
  const expected = { ...predispatchBinding(original),
    ...([2, 3].includes(recovery?.version) ? { readyRemovalEventId: recovery.binding?.readyRemovalEventId } : {}),
    ...(comment ? { outcomeCommentId: recovery.binding?.outcomeCommentId,
      outcomeCommentNumber: comment.number, outcomeBodySha256: comment.sha256,
      outcomeWriterId: recovery.binding?.outcomeWriterId,
      ...(recovery.version === 4 ? {
        outcomeCommentCreatedAt: recovery.binding?.outcomeCommentCreatedAt,
        replacementRunId: recovery.binding?.replacementRunId,
        replacementAttemptId: recovery.binding?.replacementAttemptId,
        replacementIssueNumber: recovery.binding?.replacementIssueNumber,
        replacementTarget: recovery.binding?.replacementTarget,
        replacementNumber: recovery.binding?.replacementNumber,
        replacementStep: recovery.binding?.replacementStep,
        replacementReadyEventId: recovery.binding?.replacementReadyEventId,
        replacementReadyLabel: recovery.binding?.replacementReadyLabel,
        replacementReadyEventAt: recovery.binding?.replacementReadyEventAt,
        replacementAuthorityDigest: recovery.binding?.replacementAuthorityDigest,
        replacementEnvelopeDigest: recovery.binding?.replacementEnvelopeDigest
      } : {}) } : {}) };
  const removalReceipt = recovery?.version === 1
    || ([2, 3].includes(recovery?.version) && positive(recovery.binding?.readyRemovalEventId)
      && recovery.binding.readyRemovalEventId > original.envelope.readyEventId)
    || recovery?.version === 4;
  const outcomeReceipt = ![3, 4].includes(recovery?.version)
    || positive(recovery.binding?.outcomeCommentId) && positive(recovery.binding?.outcomeWriterId)
      && (!original.outcome || original.outcome.outcomeId === recovery.binding.outcomeCommentId);
  const replacementReceipt = recovery?.version !== 4 || recovery.authorizationKind === 'owner-ready-event'
    && recovery.authorizationId === recovery.binding?.replacementReadyEventId
    && Date.parse(recovery.authorizedAt) === Date.parse(recovery.binding?.replacementReadyEventAt)
    && Number.isFinite(Date.parse(recovery.binding?.outcomeCommentCreatedAt))
    && Date.parse(recovery.binding?.replacementReadyEventAt) > Date.parse(original.envelope.readyEventAt)
    && Date.parse(recovery.binding?.replacementReadyEventAt) > Date.parse(recovery.binding?.outcomeCommentCreatedAt)
    && positive(recovery.binding?.replacementRunId) && recovery.binding.replacementRunId !== original.envelope.runId
    && recovery.binding.replacementAttemptId === 'run-' + recovery.binding.replacementRunId
    && recovery.binding.replacementIssueNumber === original.envelope.issueNumber
    && ['issue', 'pull_request'].includes(recovery.binding.replacementTarget)
    && positive(recovery.binding?.replacementNumber)
    && positive(recovery.binding?.replacementStep) && recovery.binding.replacementStep > original.envelope.step
    && positive(recovery.binding?.replacementReadyEventId)
    && ((recovery.binding.replacementTarget !== original.envelope.target
      || recovery.binding.replacementNumber !== original.envelope.number)
      || recovery.binding.replacementReadyEventId > original.envelope.readyEventId)
    && READY_LABELS.includes(recovery.binding?.replacementReadyLabel)
    && /^[a-f0-9]{64}$/.test(recovery.binding?.replacementAuthorityDigest ?? '')
    && /^[a-f0-9]{64}$/.test(recovery.binding?.replacementEnvelopeDigest ?? '');
  const terminalReceipt = recovery?.status === 'finalized' && positive(recovery.authorizationId)
    && Number.isFinite(Date.parse(recovery.authorizedAt)) && Number.isFinite(Date.parse(recovery.completedAt))
    && Date.parse(recovery.completedAt) >= Date.parse(recovery.authorizedAt);
  return Boolean(base && removalReceipt && outcomeReceipt && replacementReceipt && terminalReceipt
    && canonicalAuthorityJson(recovery.binding) === canonicalAuthorityJson(expected));
}

// An uncertain comment POST is handled separately, using its exact retained
// body or seal and native read-back. Missing publication evidence stays blocking.
export function readyReconciliationCandidate(r) {
  const ready = r?.readyConsumption;
  const consumed = consumedPredispatchRecord(r);
  const uncertain = ready?.status === 'uncertain'
    && Object.keys(ready).sort().join(',') === 'code,diagnostic,eventId,label,laterEvents,status'
    && ['READY_CONSUMPTION_UNCERTAIN', 'READY_EVENT_REPLACED'].includes(ready.code)
    && Array.isArray(ready.laterEvents) && ready.laterEvents.every(positive)
    && typeof ready.diagnostic === 'string' && Buffer.byteLength(ready.diagnostic, 'utf8') <= 8192;
  return Boolean(r?.predispatchPending
    && (consumed || predispatchNoWorkerRecord(r) && (ready?.status === 'deleting' || uncertain))
    && !r.outcome && !r.commentIntent && !r.commentBodies && !r.lifecycleIntent
    && !r.publicationIntent && !r.publishedHead && !r.finalHead);
}

function outcomeReconciliationCandidate(r) {
  const { commentIntent: intent, commentBodies: bodies, outcome, ...pending } = r ?? {};
  if (r?.readyConsumption?.status !== 'uncertain' || !readyReconciliationCandidate(pending)
    || !intent && !bodies?.outcome && !outcome) return null;
  const e = r.envelope, seal = bodies?.outcome;
  const number = intent?.number ?? seal?.number ?? outcome?.prNumber ?? e.issueNumber;
  if (![e.issueNumber, e.continuation?.pullRequest].includes(number)
    || intent && (Object.keys(intent).sort().join(',') !== 'body,key,number,rendererVersion'
      || intent.key !== 'outcome' || intent.number !== number || intent.rendererVersion !== PUBLICATION_RENDERER_VERSION
      || typeof intent.body !== 'string' || Buffer.byteLength(intent.body, 'utf8') > 100000
      || !intent.body.startsWith('## Codex Outcome\n\nStatus: BLOCKED\n')
      || !intent.body.endsWith(`<!-- relay:${e.attemptId}:outcome -->`))
    || bodies && (Object.keys(bodies).join(',') !== 'outcome' || !seal
      || Object.keys(seal).sort().join(',') !== 'number,rendererVersion,sha256'
      || seal.number !== number || seal.rendererVersion !== PUBLICATION_RENDERER_VERSION)
    || outcome && (Object.keys(outcome).sort().join(',') !== 'bodySha256,head,outcomeId,prNumber,status'
      || outcome.status !== 'BLOCKED' || outcome.head !== null || !positive(outcome.outcomeId)
      || outcome.prNumber !== (number === e.issueNumber ? null : number))) return null;
  const sha256 = intent ? sha256Body(intent.body) : seal?.sha256 ?? outcome?.bodySha256;
  if (!/^[a-f0-9]{64}$/.test(sha256 ?? '') || seal && seal.sha256 !== sha256
    || outcome && outcome.bodySha256 !== sha256) return null;
  return { number, sha256, body: intent?.body };
}

function replacementOutcomeCandidate(record) {
  const ready = record?.readyConsumption;
  if (!predispatchNoWorkerRecord(record) || ready?.status !== 'uncertain'
    || ready.code !== 'READY_EVENT_REPLACED' || !Array.isArray(ready.laterEvents)
    || new Set(ready.laterEvents).size !== ready.laterEvents.length
    || ready.laterEvents.some(id => !positive(id) || id <= record.envelope.readyEventId)) return null;
  return outcomeReconciliationCandidate(record);
}

async function reconcileOutcomeComment(api, r, evidence, { includeTimes = false, requireUnedited = false } = {}) {
  const marker = `<!-- relay:${r.envelope.attemptId}:outcome -->`;
  const matches = (await api.list(`/issues/${evidence.number}/comments`))
    .filter(comment => comment.user?.login === WRITER && comment.body?.includes(marker));
  if (matches.length !== 1 || !positive(matches[0].id)) fail('PREDISPATCH_OUTCOME_RECONCILIATION_UNPROVEN');
  const comment = await api.get(`/issues/comments/${matches[0].id}`);
  const writer = await api.userIdentity(WRITER);
  if (writer?.login !== WRITER || writer.type !== 'Bot' || !positive(writer.id)
    || comment?.id !== matches[0].id || comment.user?.login !== WRITER || comment.user?.type !== 'Bot'
    || comment.user.id !== writer.id || matches[0].user?.id !== writer.id
    || comment.issue_url !== `https://api.github.com/repos/${r.envelope.repository}/issues/${evidence.number}`
    || typeof comment.body !== 'string' || !comment.body.startsWith('## Codex Outcome\n\nStatus: BLOCKED\n')
    || !comment.body.endsWith(marker) || comment.body !== matches[0].body
    || sha256Body(comment.body) !== evidence.sha256 || evidence.body && comment.body !== evidence.body
    || requireUnedited && (!Number.isFinite(Date.parse(comment.created_at))
      || comment.updated_at !== comment.created_at)
    || r.outcome && comment.id !== r.outcome.outcomeId) fail('PREDISPATCH_OUTCOME_RECONCILIATION_UNPROVEN');
  return { outcomeCommentId: comment.id, outcomeCommentNumber: evidence.number,
    outcomeBodySha256: evidence.sha256, outcomeWriterId: writer.id,
    ...(includeTimes ? { outcomeCommentCreatedAt: comment.created_at } : {}) };
}

// A fresh admitted owner event can retire only a sealed no-worker replacement
// predecessor. It does not change the event or any native Task metadata.
export async function predispatchReplacementState({ api, journal, record: r, replacement, checkoutAbsent }) {
  if (!predispatchReadyReplacementReported(r)) fail('PREDISPATCH_REPLACEMENT_RECONCILIATION_UNPROVEN');
  const e = validateEnvelope(r.envelope), next = validateEnvelope(replacement);
  if (next.issueNumber !== e.issueNumber || next.runId === e.runId
    || next.attemptId !== 'run-' + next.runId || next.transport !== 'label'
    || next.request?.kind !== 'admission' || next.step <= e.step) {
    fail('PREDISPATCH_REPLACEMENT_RECONCILIATION_UNPROVEN');
  }
  const run = await api.getRun(e.runId);
  const originalEventName = e.target === 'issue' ? 'issues' : 'pull_request_target';
  if (run.id !== e.runId || run.repository?.full_name !== e.repository
    || run.actor?.login !== OWNER || run.triggering_actor && run.triggering_actor.login !== OWNER
    || run.path !== CONSUMER.routingWorkflow || run.status !== 'completed'
    || run.conclusion !== 'failure' || run.run_attempt !== 1 || run.event !== originalEventName
    || run.display_title !== e.runName
    || !(run.head_branch === CONSUMER.baseBranch || e.target === 'pull_request' && run.head_branch === e.branch)
    || !Number.isFinite(Date.parse(run.updated_at))) fail('PREDISPATCH_ORIGINAL_RUN_AMBIGUOUS');
  if (!journal || await journal.get(e.runId, e.repository) || !checkoutAbsent
    || !await checkoutAbsent(e)) fail('PREDISPATCH_EXECUTION_EVIDENCE_CONFLICT');

  const originalTransitions = await readyTransitions(api, e.number);
  const originalEvent = originalTransitions.find(event => event.id === e.readyEventId);
  const laterOriginalEvents = originalTransitions.filter(event => event.id > e.readyEventId);
  if (originalEvent?.event !== 'labeled' || originalEvent.label?.name !== e.readyLabel
    || originalEvent.actor?.login !== OWNER || originalEvent.actor?.type !== 'User'
    || originalEvent.created_at !== e.readyEventAt || laterOriginalEvents.length === 0
    || r.readyConsumption.laterEvents.some(id => !laterOriginalEvents.some(event => event.id === id))) {
    fail('PREDISPATCH_REPLACEMENT_RECONCILIATION_UNPROVEN');
  }
  const originalSubject = await api.get('/issues/' + e.number);
  const originalReadyLabels = labelNames(originalSubject.labels).filter(name => READY_LABELS.includes(name));
  if (originalSubject.number !== e.number
    || e.target === next.target && e.number === next.number
      && (originalReadyLabels.length !== 1 || originalReadyLabels[0] !== next.readyLabel)
    || (e.target !== next.target || e.number !== next.number) && originalReadyLabels.length !== 0) {
    fail('PREDISPATCH_REPLACEMENT_RECONCILIATION_UNPROVEN');
  }

  const outcomeEvidence = outcomeReconciliationCandidate(r);
  const outcomeBinding = await reconcileOutcomeComment(api, r, outcomeEvidence,
    { includeTimes: true, requireUnedited: true });
  const replacementRun = await api.getRun(next.runId);
  const replacementEventName = next.target === 'issue' ? 'issues' : 'pull_request_target';
  if (replacementRun.id !== next.runId || replacementRun.repository?.full_name !== next.repository
    || replacementRun.actor?.login !== OWNER || replacementRun.triggering_actor
      && replacementRun.triggering_actor.login !== OWNER
    || replacementRun.path !== CONSUMER.routingWorkflow
    || !['in_progress', 'completed'].includes(replacementRun.status)
    || replacementRun.run_attempt !== 1 || replacementRun.event !== replacementEventName
    || replacementRun.display_title !== next.runName
    || !(replacementRun.head_branch === CONSUMER.baseBranch
      || next.target === 'pull_request' && replacementRun.head_branch === next.branch)
    || Date.parse(next.readyEventAt) <= Date.parse(outcomeBinding.outcomeCommentCreatedAt)) {
    fail('PREDISPATCH_REPLACEMENT_RECONCILIATION_UNPROVEN');
  }
  const nextTransitions = await readyTransitions(api, next.number);
  const nextEvent = nextTransitions.find(event => event.id === next.readyEventId);
  if (nextEvent?.event !== 'labeled' || nextEvent.label?.name !== next.readyLabel
    || nextEvent.actor?.login !== OWNER || nextEvent.actor?.type !== 'User'
    || nextEvent.created_at !== next.readyEventAt) fail('PREDISPATCH_REPLACEMENT_RECONCILIATION_UNPROVEN');
  await revalidateReadyEvent(api, next);
  if (await journal.get(e.runId, e.repository) || !await checkoutAbsent(e)) {
    fail('PREDISPATCH_EXECUTION_EVIDENCE_CONFLICT');
  }
  return { binding: { ...predispatchBinding(r),
    replacementRunId: next.runId, replacementAttemptId: next.attemptId,
    replacementIssueNumber: next.issueNumber, replacementTarget: next.target,
    replacementNumber: next.number, replacementStep: next.step,
    replacementReadyEventId: next.readyEventId, replacementReadyLabel: next.readyLabel,
    replacementReadyEventAt: next.readyEventAt, replacementAuthorityDigest: next.authorityDigest,
    replacementEnvelopeDigest: digest(next), ...outcomeBinding } };
}

// The Writer mutex is already held. Re-read every external proof after the
// replacement admission record is durable, then append one local receipt.
export async function finalizePredispatchReplacement({ api, store, journal, record: r, replacementRecord,
  checkoutAbsent, expectedBinding, now = () => new Date().toISOString() }) {
  const next = validateEnvelope(replacementRecord?.envelope);
  const { binding } = await predispatchReplacementState({ api, journal, record: r,
    replacement: next, checkoutAbsent });
  if (canonicalAuthorityJson(binding) !== canonicalAuthorityJson(expectedBinding)) {
    fail('PREDISPATCH_RECOVERY_BINDING_CHANGED');
  }
  const saved = await store.get(r.envelope.runId, r.envelope.repository);
  if (!saved) fail('PREDISPATCH_RECOVERY_BINDING_CHANGED');
  if (saved.predispatchRecovery) {
    if (!completedPredispatchRecovery(saved)
      || saved.predispatchRecovery.authorizationId !== next.readyEventId
      || saved.predispatchRecovery.binding.replacementEnvelopeDigest !== digest(next)) {
      fail('PREDISPATCH_RECOVERY_BINDING_CHANGED');
    }
    return saved.predispatchRecovery;
  }
  if (digest(saved) !== binding.recordDigest) fail('PREDISPATCH_RECOVERY_BINDING_CHANGED');
  const admitted = await store.get(next.runId, next.repository);
  if (!admitted || admitted.nativeAdmission !== true || admitted.admissionBlock
    || digest(admitted.envelope) !== digest(next)) fail('PREDISPATCH_REPLACEMENT_RECONCILIATION_UNPROVEN');
  if (await journal.get(r.envelope.runId, r.envelope.repository) || !await checkoutAbsent(r.envelope)) {
    fail('PREDISPATCH_EXECUTION_EVIDENCE_CONFLICT');
  }
  saved.predispatchRecovery = { version: 4, status: 'finalized',
    authorizationKind: 'owner-ready-event', authorizationId: next.readyEventId,
    binding, authorizedAt: next.readyEventAt, completedAt: now() };
  if (!completedPredispatchRecovery(saved)) fail('PREDISPATCH_RECOVERY_BINDING_CHANGED');
  await store.put(r.envelope.runId, saved);
  return saved.predispatchRecovery;
}

export async function predispatchState({ api, journal, record: r, checkoutAbsent }) {
  const reconcileOutcome = outcomeReconciliationCandidate(r);
  const reconcileReady = readyReconciliationCandidate(r) || Boolean(reconcileOutcome);
  if (!partialPredispatchRecord(r) && !reconcileReady) fail('PREDISPATCH_STATE_NOT_PROVEN');
  const e = validateEnvelope(r.envelope);
  const run = await api.getRun(e.runId);
  // A re-run could have entered an older runtime's replay path. Never infer its
  // behavior from the first run's retained partial record.
  if (run.status !== 'completed' || run.conclusion !== 'failure' || run.run_attempt !== 1)
    fail('PREDISPATCH_ORIGINAL_RUN_AMBIGUOUS');
  if (!journal || await journal.get(e.runId, e.repository) || !checkoutAbsent || !await checkoutAbsent(e))
    fail('PREDISPATCH_EXECUTION_EVIDENCE_CONFLICT');
  await revalidateAuthority(api, e);
  let readyRemovalEventId;
  if (reconcileReady) {
    // Require an observed removal after the original command, with no later
    // ready event and no live ready label. Never repeat the uncertain DELETE.
    const subject = await api.get(`/issues/${e.number}`);
    const events = await readyTransitions(api, e.number);
    const original = events.find(event => event.id === e.readyEventId);
    const later = events.filter(event => event.id > e.readyEventId);
    if (subject.number !== e.number || labelNames(subject.labels).some(name => READY_LABELS.includes(name))
      || original?.event !== 'labeled' || original.label?.name !== e.readyLabel
      || original.actor?.login !== OWNER || original.actor?.type !== 'User'
      || original.created_at !== e.readyEventAt || later.length !== 1
      || later[0].event !== 'unlabeled' || later[0].label?.name !== e.readyLabel)
      fail('READY_RECONCILIATION_UNPROVEN');
    if (consumedPredispatchRecord(r) && later[0].id !== r.readyConsumption.removalEventId)
      fail('READY_RECONCILIATION_CHANGED');
    readyRemovalEventId = later[0].id;
  } else await revalidateReadyEvent(api, e);
  if ((await api.get(`/git/ref/heads/${e.branch}`)).object?.sha !== e.startHead)
    fail('REMOTE_HEAD_CHANGED');
  if (e.continuation?.pullRequest) {
    const pr = await api.get(`/pulls/${e.continuation.pullRequest}`);
    assertPr(pr, e.continuation.pullRequest);
    if (pr.head.sha !== e.startHead || pr.head.ref !== e.branch || pr.base.ref !== CONSUMER.baseBranch
      || linkedIssue(pr.body) !== e.issueNumber) fail('PR_AUTHORITY_CHANGED');
  }
  const commentBinding = reconcileOutcome ? await reconcileOutcomeComment(api, r, reconcileOutcome) : {};
  const binding = { ...predispatchBinding(r), ...(reconcileReady ? { readyRemovalEventId } : {}), ...commentBinding };
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
  const refreshed = await predispatchState({ api, journal, record: r, checkoutAbsent });
  if (canonicalAuthorityJson(refreshed.binding) !== canonicalAuthorityJson(binding)) fail('PREDISPATCH_RECOVERY_BINDING_CHANGED');
  if (digest(await store.get(r.envelope.runId)) !== binding.recordDigest) fail('PREDISPATCH_RECOVERY_BINDING_CHANGED');
  r.predispatchRecovery = { version: outcomeReconciliationCandidate(r) ? 3 : readyReconciliationCandidate(r) ? 2 : 1, status: 'finalized', authorizationId: request.authorizationId,
    binding, authorizedAt, completedAt: now() };
  await store.put(r.envelope.runId, r);
  return r.predispatchRecovery;
}
