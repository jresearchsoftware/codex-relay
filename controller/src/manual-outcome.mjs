import { REPOSITORY, WRITER, BASE_BRANCH, positive, exactSha, fail } from './execution-contract.mjs';
import { canonicalAuthorityJson, validateAuthorityRecord, extractAuthorityRecord, sha256Body, renderAuthorityRecord, admissionBinding } from '../../contracts/src/github-authority.mjs';
import { taskReferences } from './task-relationship.mjs';

// Only the protected, capability-specific transport calls this operation. The
// controller/worker Writer helper never accepts a caller's capability claim.
export function validateManualSubmission(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)
    || Object.keys(value).sort().join(',') !== 'repository,result,run_id,task'
    || value.repository !== REPOSITORY || !positive(value.task) || !positive(value.run_id)
    || !value.result || typeof value.result !== 'object' || Array.isArray(value.result)
    || Buffer.byteLength(JSON.stringify(value), 'utf8') > 100 * 1024) fail('MANUAL_SUBMISSION_INVALID');
  return value;
}

export async function assertManualPullRequestBinding(api, e, pr, { unique = true } = {}) {
  // The authenticated v4 call names its target. Admission binds the attempt,
  // not a manually copied PR-body token or the PR author's identity.
  if (e.request.kind === 'admission' && e.request.schema_version === '4.0') {
    if (pr.base?.repo?.full_name !== REPOSITORY || pr.head?.repo?.full_name !== REPOSITORY)
      fail('MANUAL_PR_REPOSITORY_MISMATCH');
    const number = e.request.existing_pr ?? (e.target === 'pull_request' ? e.number : e.continuation?.pullRequest);
    if (number && pr.number !== number) fail('MANUAL_PR_TARGET_MISMATCH');
    if (!e.branch || pr.head.ref !== e.branch) fail('MANUAL_PR_BRANCH_MISMATCH');
    if (pr.base.ref !== BASE_BRANCH) fail('MANUAL_PR_BASE_MISMATCH');
    const references = taskReferences(pr.body, REPOSITORY);
    if (references.length !== 1 || references[0] !== e.issueNumber) fail('MANUAL_PR_TASK_MISMATCH');
    if (!exactSha(pr.head.sha) || !exactSha(pr.base.sha)) fail('MANUAL_PR_HEAD_MISMATCH');
    return;
  }
  // Retained v3 discovery keeps its exact request marker and uniqueness rule.
  const references = taskReferences(pr.body, REPOSITORY);
  if (pr.base?.repo?.full_name !== REPOSITORY || pr.head?.repo?.full_name !== REPOSITORY
    || references.length !== 1 || references[0] !== e.issueNumber
    || (e.branch && pr.head.ref !== e.branch)) fail('PR_AUTHORITY_CHANGED');
  const marker = `Execution request digest: ${e.requestReference.sha256}`;
  if (!pr.body?.split(/\r?\n/).includes(marker)) fail('PR_AUTHORITY_CHANGED');
  if (!unique) return;
  const artifacts = (await api.list(`/pulls?state=all&head=${REPOSITORY.split('/')[0]}:${encodeURIComponent(pr.head.ref)}`))
    .filter(candidate => candidate.body?.split(/\r?\n/).includes(marker));
  if (artifacts.length !== 1 || artifacts[0].number !== pr.number) fail('PR_AMBIGUOUS');
}

export async function publishManualOutcome({ api, store, record: r, submission,
  commentOnce, rememberPullRequest, transitionManual, revalidate, existingPullRequest,
  historical = async () => false, checkPublication = async () => {} }) {
  validateManualSubmission(submission);
  const e = r.envelope; const result = submission.result;
  if (e.route !== 'manual' || e.issueNumber !== submission.task || e.runId !== submission.run_id
    || r.admissionBlock || !e.request) fail('MANUAL_OUTCOME_NOT_ADMITTED');
  const issue = await api.get(`/issues/${e.issueNumber}`);
  validateAuthorityRecord(result, { repository: REPOSITORY, task: e.issueNumber, charterBody: issue.body });
  if (result.kind !== 'outcome' || result.attempt !== e.attemptId
    || result.schema_version !== '3.0' && result.step !== e.step) fail('MANUAL_OUTCOME_BINDING_INVALID');
  if (result.schema_version === '3.0') {
    if (canonicalAuthorityJson(result.request) !== canonicalAuthorityJson(e.requestReference)) fail('MANUAL_OUTCOME_BINDING_INVALID');
  } else {
    if (canonicalAuthorityJson(result.authority) !== canonicalAuthorityJson(e.request.authority)
      || result.admission?.sha256 !== admissionBinding(e.request).sha256 || result.admission?.attempt !== e.attemptId
      || result.admission?.step !== e.step) fail('MANUAL_OUTCOME_BINDING_INVALID');
    if (result.authority_resolution && canonicalAuthorityJson(result.authority_resolution)
      !== canonicalAuthorityJson(e.request.authority_resolution)) fail('MANUAL_OUTCOME_BINDING_INVALID');
  }
  const resultDigest = sha256Body(canonicalAuthorityJson(result));
  if (r.manualSubmission && r.manualSubmission.sha256 !== resultDigest) fail('MANUAL_OUTCOME_CHANGED');
  const historicalResult = result.schema_version === '4.0' && await historical(e);
  let pr = null;
  if (result.parent.kind === 'pull_request') {
    pr = await api.get(`/pulls/${result.parent.number}`);
    if (pr.number !== result.parent.number || (r.prNumber && r.prNumber !== pr.number)) fail('MANUAL_PR_TARGET_MISMATCH');
    if (result.result.kind === 'git' && result.result.revision !== pr.head.sha && !historicalResult)
      fail('MANUAL_PR_HEAD_MISMATCH');
    await assertManualPullRequestBinding(api, e, pr);
    if (historicalResult && result.result.kind === 'git' && result.result.revision !== pr.head.sha) {
      const commit = await api.get(`/git/commits/${result.result.revision}`);
      if (commit.sha !== result.result.revision) fail('PUBLISHED_HEAD_REQUIRED');
    }
    // An open implementation PR can become Ready only at an exact Git head.
    // Reject this existing lifecycle incompatibility before reserving claims or
    // posting a successful Outcome that no replay could finish.
    if (result.status === 'implemented' && pr.state === 'open' && result.result.kind !== 'git') fail('PUBLISHED_HEAD_REQUIRED');
  } else if (result.parent.number !== e.issueNumber || r.prNumber || r.prIntent
    || (e.branch || historicalResult) && await existingPullRequest(r, { attemptOnly: historicalResult })) fail('PR_AUTHORITY_CHANGED');
  // Do not freeze a correctable target/head mistake or post before discovering
  // an unresolved sibling effect on this exact target.
  if (!historicalResult) await checkPublication(e, pr);
  const current = await revalidate(e);
  if (pr) await rememberPullRequest(r, pr);
  const writer = await api.userIdentity(WRITER);
  if (writer.login !== WRITER || writer.type !== 'Bot' || !positive(writer.id)) fail('WRITER_IDENTITY_CHANGED');
  if (r.outcome) {
    const durable = await api.get(`/issues/comments/${r.outcome.outcomeId}`);
    if (durable.user?.login !== WRITER || durable.user?.type !== 'Bot' || durable.user?.id !== writer.id
      || sha256Body(durable.body) !== r.outcome.bodySha256
      || canonicalAuthorityJson(extractAuthorityRecord(durable.body)) !== canonicalAuthorityJson(r.manualSubmission.publishedResult ?? result)) fail('COMMENT_CONTENT_CHANGED');
    if (result.status === 'implemented' && !historicalResult) await transitionManual(r, pr, result, false);
    return r.outcome;
  }
  r.manualSubmission = { ...r.manualSubmission, sha256: resultDigest, parent: result.parent, rendererVersion: 'human-v1' };
  await store.put(e.runId, r);
  const frozenResult = r.manualSubmission.publishedResult
    ?? (r.commentIntent?.key === 'outcome' && r.commentIntent.body ? extractAuthorityRecord(r.commentIntent.body) : null);
  let publishedResult = frozenResult ?? result;
  if (!frozenResult && result.schema_version === '4.0' && current?.authorityDrift) {
    const drift = current.authorityDrift;
    if (result.authority_drift && canonicalAuthorityJson(result.authority_drift) !== canonicalAuthorityJson(drift)) fail('MANUAL_OUTCOME_BINDING_INVALID');
    publishedResult = { ...result, ...(e.request.authority_resolution ? { authority_resolution: e.request.authority_resolution } : {}),
      ...(drift.current_authority.sha256 !== result.authority.sha256 ? { authority_drift: drift } : {}) };
    r.manualSubmission.publishedResult = publishedResult;
    await store.put(e.runId, r);
  }
  if (historicalResult && !frozenResult && !publishedResult.limitations.includes('Historical attempt report only; a later Step owns current projections. This Outcome grants no current-head acceptance.')) {
    publishedResult = { ...publishedResult, limitations: [...publishedResult.limitations,
      'Historical attempt report only; a later Step owns current projections. This Outcome grants no current-head acceptance.'] };
    r.manualSubmission.publishedResult = publishedResult; await store.put(e.runId, r);
  }
  if (!r.manualSubmission.publishedResult) {
    r.manualSubmission.publishedResult = publishedResult; await store.put(e.runId, r);
  }
  if (result.status !== 'implemented' && !historicalResult) await transitionManual(r, pr, result, true);
  const comment = await commentOnce(r, 'outcome', pr?.number ?? e.issueNumber, renderAuthorityRecord(publishedResult));
  const durable = await api.get(`/issues/comments/${comment.id}`);
  if (durable.body !== comment.body || durable.user?.login !== WRITER || durable.user?.type !== 'Bot'
    || durable.user?.id !== writer.id) fail('COMMENT_CONTENT_CHANGED');
  r.outcome = { status: result.status === 'implemented' ? 'IMPLEMENTED_PENDING_FRESH_REVIEW' : 'BLOCKED',
    head: exactSha(result.result.revision) ? result.result.revision : null, prNumber: pr?.number ?? null,
    outcomeId: durable.id, bodySha256: sha256Body(durable.body), manual: true };
  await store.put(e.runId, r);
  if (result.status === 'implemented' && !historicalResult) await transitionManual(r, pr, result, false);
  return r.outcome;
}
