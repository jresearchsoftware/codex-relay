import { CONSUMER } from '../../consumer/consumer.mjs';
import { REPOSITORY, OWNER, WRITER, VERSION, digest, positive, exactSha, fail } from './execution-contract.mjs';
import { sha256Body, extractAuthorityRecord, canonicalAuthorityJson } from '../../contracts/src/github-authority.mjs';
import { revalidateAuthority } from './live-authority.mjs';
import { dispatchRunName } from './launch-metadata.mjs';
import { REMOTE } from './trusted-git.mjs';
import { ATTEMPT_RECORD_BYTES } from './attempt-store.mjs';
import { failureDiagnosticFromDetails } from './diagnostics.mjs';

export const prepublicationAuthorizationBody = binding =>
  `Authorize one terminal prepublication Writer recovery:\n\n\`\`\`json\n${JSON.stringify(binding, null, 2)}\n\`\`\``;

async function originalRun(api, e) {
  const run = await api.getRun(e.runId);
  const transport = e.transport === 'label'
    ? run.event === 'issues' && run.display_title === e.runName && positive(e.readyEventId)
      && run.head_branch === CONSUMER.baseBranch
    : run.event === 'workflow_dispatch' && run.head_branch === CONSUMER.baseBranch
      && run.display_title === dispatchRunName(e);
  if (e.attemptId !== `run-${e.runId}` || !transport || run.id !== e.runId
    || run.repository?.full_name !== REPOSITORY || run.actor?.login !== OWNER
    || (run.triggering_actor && run.triggering_actor.login !== OWNER)
    || run.status !== 'completed' || run.path !== CONSUMER.routingWorkflow
    // Admission permits only the first native run attempt. A later Actions
    // rerun is changed execution evidence, not the original sealed attempt.
    || run.run_attempt !== 1 || !Number.isFinite(Date.parse(run.updated_at))) fail('RECOVERY_ORIGINAL_RUN_NOT_COMPLETED');
  return run;
}

// This reads the protected original journal, never worker-supplied claims or a
// caller-selected checkout. The old terminal evidence is not rewritten.
export async function prepublicationState({ api, journal, record: r, head }) {
  const e = r.envelope;
  if (e.route !== 'auto' || e.target !== 'issue' || e.request?.kind !== 'task-request'
    || !e.requestReference || !exactSha(head) || head === e.startHead
    || r.admissionBlock || r.publicationIntent || r.publishedHead || r.finalHead
    || r.successOutcomeIntent || r.publicationRecoveries?.length
    || r.outcome?.status !== 'BLOCKED' || r.outcome.head !== null || r.outcome.prNumber !== null
    || !positive(r.outcome.outcomeId)) fail('PREPUBLICATION_RECOVERY_NOT_ADMITTED');
  if (!r.prepublicationRecovery && (r.prNumber || r.prIntent || r.commentIntent
    || r.lifecycleIntent || r.relationshipIntent || r.readinessIntent)) fail('PREPUBLICATION_RECOVERY_NOT_ADMITTED');
  const saved = await journal?.get(e.runId);
  if (!saved || saved.version !== VERSION || digest(saved.envelope) !== digest(e)) fail('JOURNAL_BINDING_CHANGED');
  const execution = saved.execution;
  if (execution?.reserved !== true || execution.returned !== true || execution.child !== 'started'
    || execution.containment !== 'reaped' || execution.result?.status !== 'success'
    || execution.errorCode || execution.diagnostic) fail('RECOVERY_EXECUTION_NOT_PROVEN');
  if (saved.collection || saved.progress || saved.outcome?.status !== 'BLOCKED'
    || !['status', 'head', 'prNumber', 'outcomeId'].every(key => saved.outcome[key] === r.outcome[key])
    || saved.diagnostic?.classification?.stage !== 'progress'
    || saved.diagnostic.lastSuccessfulBoundary !== 'contained-execution'
    || saved.diagnostic.observed?.child !== 'started' || saved.diagnostic.containment !== 'reaped'
    || saved.diagnostic.orchestration !== 'FAILED' || saved.diagnostic.durable?.publishedHead !== null) fail('RECOVERY_TERMINAL_STATE_NOT_PROVEN');
  const lifecycle = r.controllerLifecycle;
  if (lifecycle && (lifecycle.version !== 1 || lifecycle.status !== 'complete'
    || lifecycle.child !== 'started' || lifecycle.containment !== 'reaped')) fail('RECOVERY_CONTROLLER_NOT_COMPLETE');
  const run = await originalRun(api, e);
  const outcome = await api.get(`/issues/comments/${r.outcome.outcomeId}`);
  const writer = await api.userIdentity(WRITER);
  if (writer.login !== WRITER || writer.type !== 'Bot' || !positive(writer.id)
    || outcome.id !== r.outcome.outcomeId || outcome.user?.id !== writer.id
    || outcome.user?.login !== WRITER || outcome.user?.type !== 'Bot'
    || outcome.issue_url !== `https://api.github.com/repos/${REPOSITORY}/issues/${e.issueNumber}`
    || !outcome.body?.startsWith('## Codex Outcome\n\nStatus: BLOCKED\n')
    || !outcome.body.endsWith(`<!-- relay:${e.attemptId}:outcome -->`)
    || !Number.isFinite(Date.parse(outcome.created_at)) || !Number.isFinite(Date.parse(outcome.updated_at))) fail('RECOVERY_TERMINAL_OUTCOME_CHANGED');
  const typed = extractAuthorityRecord(outcome.body);
  if (typed?.kind !== 'outcome' || typed.status !== 'blocked' || typed.task !== e.issueNumber
    || typed.attempt !== e.attemptId || canonicalAuthorityJson(typed.request) !== canonicalAuthorityJson(e.requestReference)
    || typed.parent.kind !== 'issue' || typed.parent.number !== e.issueNumber) fail('RECOVERY_TERMINAL_OUTCOME_CHANGED');
  await revalidateAuthority(api, e);
  const binding = { operation: 'recover-prepublication', repository: REPOSITORY,
    task: e.issueNumber, step: e.step, request: e.requestReference, runId: e.runId,
    attemptId: e.attemptId, branch: e.branch, remote: REMOTE,
    previous: e.continuation ? e.startHead : null, head, startingHead: e.startHead,
    authorityDigest: e.authorityDigest, consumerDigest: e.consumerDigest,
    writer: { login: WRITER, id: writer.id, ...CONSUMER.writerIdentity },
    terminal: { outcome: r.outcome, bodySha256: sha256Body(outcome.body),
      journalDigest: digest(saved), controllerDigest: digest(lifecycle ?? null),
      runAttempt: run.run_attempt, runCompletedAt: run.updated_at,
      outcomeCreatedAt: outcome.created_at, outcomeUpdatedAt: outcome.updated_at } };
  if (r.prepublicationRecovery && digest(binding) !== digest(r.prepublicationRecovery.binding)) fail('RECOVERY_EVIDENCE_CHANGED');
  return { binding, saved, recovery: r.prepublicationRecovery ?? null,
    authorizationBody: prepublicationAuthorizationBody(binding) };
}

async function authorize(api, binding, authorizationId) {
  if (!positive(authorizationId)) fail('RECOVERY_OWNER_AUTHORIZATION_REQUIRED');
  const owner = await api.userIdentity(OWNER);
  const comment = await api.get(`/issues/comments/${authorizationId}`);
  const created = Date.parse(comment.created_at);
  const floor = Math.max(...['runCompletedAt', 'outcomeCreatedAt', 'outcomeUpdatedAt']
    .map(key => Date.parse(binding.terminal[key])));
  if (owner.login !== OWNER || owner.type !== 'User' || !positive(owner.id)
    || comment.id !== authorizationId || comment.user?.login !== OWNER
    || comment.user?.id !== owner.id || comment.user?.type !== 'User'
    || comment.issue_url !== `https://api.github.com/repos/${REPOSITORY}/issues/${binding.task}`
    || !Number.isFinite(created) || created <= floor || comment.updated_at !== comment.created_at
    || String(comment.body).replace(/\r\n/g, '\n').trim() !== prepublicationAuthorizationBody(binding)) fail('RECOVERY_OWNER_AUTHORIZATION_INVALID');
  return comment.created_at;
}

function publicationDiagnostic(error, operation, code = 'GIT_UNKNOWN_FAILURE') {
  const diagnostic = failureDiagnosticFromDetails(error?.details) ?? {};
  return failureDiagnosticFromDetails({ failureDiagnostic: { ...diagnostic, operation,
    classification: diagnostic.classification ?? code, primaryCause: diagnostic.primaryCause ?? code } },
  { fallbackCode: 'PUBLICATION_UNCERTAIN', fallbackStage: 'writer-publication', fallbackBoundary: 'writer-publication' });
}

// The fixed helper holds publication-v2.lock throughout observation, durable
// reservation, publication and receipt. No ordinary replay invokes this route.
export async function recoverPrepublication({ api, store, publisher, journal, collect, record: r, request,
  checkPullRequest, finish, now = () => new Date().toISOString() }) {
  const { binding } = await prepublicationState({ api, journal, record: r, head: request.head });
  await authorize(api, binding, request.authorizationId);
  const existing = r.prepublicationRecovery;
  if (existing) {
    if (existing.authorizationId !== request.authorizationId) fail('RECOVERY_AUTHORIZATION_CONSUMED');
    if (existing.complete) return existing.outcome;
    if (existing.publication?.status !== 'PUBLISHED' || existing.publication.publishedHead !== binding.head) fail('PUBLICATION_UNCERTAIN');
    return finish(existing);
  }
  const progress = await collect(r.envelope);
  if (progress.head !== binding.head || !progress.bundle) fail('RECOVERY_CANDIDATE_CHANGED');
  if (typeof progress.clean !== 'boolean') fail('WORKTREE_STATE_UNKNOWN');
  if (!progress.clean) fail('UNCOMMITTED_WORK_REMAINS');
  return publisher.inspect(r.envelope, progress.bundle, async g => {
    if (g.head !== binding.head) fail('RECOVERY_CANDIDATE_CHANGED');
    if (!g.commits.length || !await g.ancestor(binding.startingHead, g.head)
      || (binding.previous && !await g.ancestor(binding.previous, g.head))) fail('RECOVERY_HISTORY_INVALID');
    if (g.remoteHead !== binding.previous) fail('REMOTE_HEAD_CHANGED');
    await checkPullRequest(binding.previous);
    const refreshed = await prepublicationState({ api, journal, record: r, head: request.head });
    if (digest(refreshed.binding) !== digest(binding)) fail('RECOVERY_EVIDENCE_CHANGED');
    const authorizedAt = await authorize(api, binding, request.authorizationId);
    if (await g.observe() !== binding.previous) fail('REMOTE_HEAD_CHANGED');
    const recovery = { authorizationId: request.authorizationId, binding, authorizedAt,
      reservedAt: now(), collection: { head: progress.head, clean: progress.clean }, publication: null,
      outcome: null, complete: false };
    r.prepublicationRecovery = recovery;
    if (Buffer.byteLength(JSON.stringify(r, null, 2)) + 64 * 1024 > ATTEMPT_RECORD_BYTES) fail('ATTEMPT_RECORD_TOO_LARGE');
    await store.put(r.envelope.runId, r);
    let pushDiagnostic = null, observationDiagnostic = null, observed = null;
    try { await g.push(); } catch (error) { pushDiagnostic = publicationDiagnostic(error, 'push'); }
    try { observed = await g.observe(); }
    catch (error) { observationDiagnostic = publicationDiagnostic(error, 'observe', 'GIT_OBSERVATION_UNAVAILABLE'); }
    const published = !observationDiagnostic && observed === binding.head;
    recovery.publication = { status: published ? 'PUBLISHED' : 'PUBLICATION_UNCERTAIN',
      publishedHead: published ? binding.head : null, observedHead: exactSha(observed) ? observed : null,
      completedAt: now(), ...(pushDiagnostic ? { pushDiagnostic } : {}),
      ...(observationDiagnostic ? { observationDiagnostic } : {}) };
    await store.put(r.envelope.runId, r);
    if (!published) fail('PUBLICATION_UNCERTAIN');
    return finish(recovery);
  });
}
