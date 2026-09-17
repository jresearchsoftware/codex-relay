import { CONSUMER } from '../../consumer/consumer.mjs';
import { REPOSITORY, OWNER, positive, exactSha, fail } from './execution-contract.mjs';
import { revalidateAuthority, revalidateIntegrationBase, assertPr, linkedIssue } from './live-authority.mjs';
import { dispatchRunName } from './launch-metadata.mjs';
import { failureDiagnosticFromDetails } from './diagnostics.mjs';
import { ATTEMPT_RECORD_BYTES } from './attempt-store.mjs';

// A native owner comment authorizes one exact existing intent. Each subsequent
// decision must name the previous consumed authorization, not queue retries.
export function recoveryAuthorization(envelope, intent, afterAuthorizationId = null) {
  const e = envelope;
  return { operation: 'recover-publication', repository: REPOSITORY, target: e.target,
    number: e.number, issueNumber: e.issueNumber, branch: e.branch, runId: e.runId,
    attemptId: e.attemptId, authorityDigest: e.authorityDigest,
    previous: intent.previous, head: intent.head, afterAuthorizationId };
}

export const recoveryAuthorizationBody = binding =>
  `Authorize one Writer publication recovery:\n\n\`\`\`json\n${JSON.stringify(binding, null, 2)}\n\`\`\``;

async function authorize(api, e, authorizationId, binding, last) {
  if (!positive(authorizationId)) fail('RECOVERY_OWNER_AUTHORIZATION_REQUIRED');
  const run = await api.getRun(e.runId);
  const transportMatches = e.attemptId === `run-${e.runId}`
    ? e.transport === 'label'
      ? run.event === (e.target === 'issue' ? 'issues' : 'pull_request_target')
        && run.display_title === e.runName && positive(e.readyEventId)
        && (run.head_branch === CONSUMER.baseBranch || e.target === 'pull_request' && run.head_branch === e.branch)
      : run.event === 'workflow_dispatch' && run.head_branch === CONSUMER.baseBranch && run.display_title === dispatchRunName(e)
    : positive(e.eventId) && e.attemptId === `event-${e.eventId}` && run.event === (e.target === 'issue' ? 'issues' : 'pull_request');
  if (run.id !== e.runId || run.repository?.full_name !== REPOSITORY || run.actor?.login !== OWNER
    || (run.triggering_actor && run.triggering_actor.login !== OWNER) || run.status !== 'completed'
    || run.path !== CONSUMER.routingWorkflow || !positive(run.run_attempt)
    || !transportMatches) fail('RECOVERY_ORIGINAL_RUN_NOT_COMPLETED');
  const comment = await api.get(`/issues/comments/${authorizationId}`);
  const created = Date.parse(comment.created_at);
  const floor = Math.max(Date.parse(run.updated_at), last ? Date.parse(last.completedAt ?? last.reservedAt) : 0);
  if (comment.id !== authorizationId || comment.user?.login !== OWNER || comment.user?.type !== 'User'
    || comment.issue_url !== `https://api.github.com/repos/${REPOSITORY}/issues/${e.number}`
    || !Number.isFinite(created) || !Number.isFinite(floor) || created <= floor
    || comment.updated_at !== comment.created_at || (last && authorizationId <= last.authorizationId)
    || String(comment.body).replace(/\r\n/g, '\n').trim() !== recoveryAuthorizationBody(binding)) {
    fail('RECOVERY_OWNER_AUTHORIZATION_INVALID');
  }
  return comment.created_at;
}

function diagnostic(error, operation, fallback = 'GIT_UNKNOWN_FAILURE') {
  const d = failureDiagnosticFromDetails(error?.details) ?? {};
  return failureDiagnosticFromDetails({ failureDiagnostic: { ...d,
    classification: d.classification ?? d.primaryCause ?? fallback,
    primaryCause: d.primaryCause ?? d.classification ?? fallback, operation } },
  { fallbackCode: 'PUBLICATION_UNCERTAIN', fallbackStage: 'writer-publication', fallbackBoundary: 'writer-publication' });
}

function replay(recovery) {
  if (recovery.result?.status === 'PUBLISHED') return recovery.result;
  throw Object.assign(new Error('PUBLICATION_UNCERTAIN'), { code: 'PUBLICATION_UNCERTAIN', details: {
    failureDiagnostic: recovery.result?.failureDiagnostic ?? diagnostic(null, 'push', 'RECOVERY_AUTHORIZATION_CONSUMED')
  } });
}

// Runs under the existing root Writer flock. Reservations and receipts share
// the existing bounded atomic record; a crash after reservation consumes the
// authorization even if no push happened. No automatic mutation retry exists.
export async function recoverPublication({ api, store, publisher, record: r, request, now = () => new Date().toISOString() }) {
  const e = r.envelope;
  if (!positive(request.authorizationId)) fail('RECOVERY_OWNER_AUTHORIZATION_REQUIRED');
  const recoveries = r.publicationRecoveries ?? [];
  const consumed = recoveries.find(value => value.authorizationId === request.authorizationId);
  if (consumed) return replay(consumed);
  const intent = r.publicationIntent;
  if (e.route !== 'auto' || r.finalHead || !intent || !exactSha(intent.head)
    || (intent.previous !== null && !exactSha(intent.previous)) || intent.head === intent.previous
    || intent.previous !== (r.publishedHead ?? (e.target === 'pull_request' ? e.startHead : null))) fail('RECOVERY_INTENT_REQUIRED');
  const last = recoveries.at(-1);
  const binding = recoveryAuthorization(e, intent, last?.authorizationId ?? null);
  await authorize(api, e, request.authorizationId, binding, last);
  await revalidateAuthority(api, e);
  return publisher.inspect(e, request.bundle, async g => {
    if (g.head !== intent.head) fail('RECOVERY_CANDIDATE_CHANGED');
    if (g.remoteHead !== intent.previous) fail('REMOTE_HEAD_CHANGED');
    if (!g.commits.length || !(await g.ancestor(e.startHead, g.head))
      || (intent.previous && !(await g.ancestor(intent.previous, g.head)))) fail('RECOVERY_HISTORY_INVALID');
    const a = await revalidateAuthority(api, e);
    const prs = a.pr ? [a.pr] : await api.list(`/pulls?state=all&head=${CONSUMER.repository.split('/')[0]}:${encodeURIComponent(e.branch)}&base=${encodeURIComponent(CONSUMER.baseBranch)}`);
    if (prs.length > 1 || prs.some(pr => pr.head?.sha !== intent.previous)) fail('REMOTE_HEAD_CHANGED');
    for (const pr of prs) {
      assertPr(pr, e.target === 'pull_request' ? e.number : pr.number);
      if (pr.head.ref !== e.branch || linkedIssue(pr.body) !== e.issueNumber) fail('PR_AUTHORITY_CHANGED');
    }
    const authorizedAt = await authorize(api, e, request.authorizationId, binding, last);
    if (await g.observe() !== intent.previous) fail('REMOTE_HEAD_CHANGED');
    if (g.integrationBase) await revalidateIntegrationBase(api, e);
    const recovery = { authorizationId: request.authorizationId, binding, authorizedAt, reservedAt: now(), result: null };
    r.publicationRecoveries = [...recoveries, recovery];
    // Reserve room for the bounded push/observation diagnostics before mutation.
    if (Buffer.byteLength(JSON.stringify(r, null, 2)) + 16384 > ATTEMPT_RECORD_BYTES) fail('ATTEMPT_RECORD_TOO_LARGE');
    await store.put(e.runId, r);

    let pushDiagnostic = null;
    try { await g.push(); } catch (error) { pushDiagnostic = diagnostic(error, 'push'); }
    let observed = null; let observationDiagnostic = null;
    try { observed = await g.observe(); }
    catch (error) { observationDiagnostic = diagnostic(error, 'observe', 'GIT_OBSERVATION_UNAVAILABLE'); }
    const published = !observationDiagnostic && observed === intent.head;
    recovery.completedAt = now();
    recovery.result = { status: published ? 'PUBLISHED' : 'PUBLICATION_UNCERTAIN',
      recoveryAuthorizationId: request.authorizationId, publishedHead: published ? intent.head : null,
      observedHead: exactSha(observed) ? observed : null,
      ...(pushDiagnostic ? { pushDiagnostic } : {}), ...(observationDiagnostic ? { observationDiagnostic } : {}),
      ...(!published ? { failureDiagnostic: pushDiagnostic ?? observationDiagnostic
        ?? diagnostic(null, 'observe', observed === null ? 'GIT_OBSERVATION_UNCERTAIN' : 'GIT_REMOTE_HEAD_CONFLICT') } : {}) };
    if (published) { r.publishedHead = intent.head; r.publicationIntent = null; }
    await store.put(e.runId, r);
    return replay(recovery);
  });
}
