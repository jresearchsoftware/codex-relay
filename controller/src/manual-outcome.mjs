import { REPOSITORY, WRITER, positive, exactSha, fail } from './execution-contract.mjs';
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

export async function publishManualOutcome({ api, store, record: r, submission,
  commentOnce, rememberPullRequest, transitionManual, revalidate, existingPullRequest }) {
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
  let pr = null;
  if (result.parent.kind === 'pull_request') {
    pr = await api.get(`/pulls/${result.parent.number}`);
    const marker = e.request.schema_version === '4.0'
      ? `Execution admission digest: ${admissionBinding(e.request).sha256}` : `Execution request digest: ${e.requestReference.sha256}`;
    if (pr.number !== result.parent.number || pr.base?.repo?.full_name !== REPOSITORY || pr.head?.repo?.full_name !== REPOSITORY
      || taskReferences(pr.body, REPOSITORY).length !== 1 || taskReferences(pr.body, REPOSITORY)[0] !== e.issueNumber
      || (e.branch && pr.head.ref !== e.branch) || (result.result.kind === 'git' && result.result.revision !== pr.head.sha)
      || !pr.body?.split(/\r?\n/).includes(marker) || (r.prNumber && r.prNumber !== pr.number)) fail('PR_AUTHORITY_CHANGED');
    const artifacts = (await api.list(`/pulls?state=all&head=${REPOSITORY.split('/')[0]}:${encodeURIComponent(pr.head.ref)}`))
      .filter(candidate => candidate.body?.split(/\r?\n/).includes(marker));
    if (artifacts.length !== 1 || artifacts[0].number !== pr.number) fail('PR_AMBIGUOUS');
    // An open implementation PR can become Ready only at an exact Git head.
    // Reject this existing lifecycle incompatibility before reserving claims or
    // posting a successful Outcome that no replay could finish.
    if (result.status === 'implemented' && pr.state === 'open' && result.result.kind !== 'git') fail('PUBLISHED_HEAD_REQUIRED');
    await rememberPullRequest(r, pr);
  } else if (result.parent.number !== e.issueNumber || r.prNumber || r.prIntent
    || e.branch && await existingPullRequest(r)) fail('PR_AUTHORITY_CHANGED');
  const writer = await api.userIdentity(WRITER);
  if (writer.login !== WRITER || writer.type !== 'Bot' || !positive(writer.id)) fail('WRITER_IDENTITY_CHANGED');
  if (r.outcome) {
    const durable = await api.get(`/issues/comments/${r.outcome.outcomeId}`);
    if (durable.user?.login !== WRITER || durable.user?.type !== 'Bot' || durable.user?.id !== writer.id
      || sha256Body(durable.body) !== r.outcome.bodySha256
      || canonicalAuthorityJson(extractAuthorityRecord(durable.body)) !== canonicalAuthorityJson(r.manualSubmission.publishedResult ?? result)) fail('COMMENT_CONTENT_CHANGED');
    if (result.status === 'implemented') await transitionManual(r, pr, result, false);
    return r.outcome;
  }
  r.manualSubmission = { ...r.manualSubmission, sha256: resultDigest, parent: result.parent, rendererVersion: 'human-v1' };
  await store.put(e.runId, r);
  const current = await revalidate(e);
  let publishedResult = r.manualSubmission.publishedResult ?? result;
  if (!r.manualSubmission.publishedResult && result.schema_version === '4.0' && current?.authorityDrift) {
    const drift = current.authorityDrift;
    if (result.authority_drift && canonicalAuthorityJson(result.authority_drift) !== canonicalAuthorityJson(drift)) fail('MANUAL_OUTCOME_BINDING_INVALID');
    publishedResult = { ...result, ...(e.request.authority_resolution ? { authority_resolution: e.request.authority_resolution } : {}),
      ...(drift.current_authority.sha256 !== result.authority.sha256 ? { authority_drift: drift } : {}) };
    r.manualSubmission.publishedResult = publishedResult;
    await store.put(e.runId, r);
  }
  if (result.status !== 'implemented') await transitionManual(r, pr, result, true);
  const comment = await commentOnce(r, 'outcome', pr?.number ?? e.issueNumber, renderAuthorityRecord(publishedResult));
  const durable = await api.get(`/issues/comments/${comment.id}`);
  if (durable.body !== comment.body || durable.user?.login !== WRITER || durable.user?.type !== 'Bot'
    || durable.user?.id !== writer.id) fail('COMMENT_CONTENT_CHANGED');
  r.outcome = { status: result.status === 'implemented' ? 'IMPLEMENTED_PENDING_FRESH_REVIEW' : 'BLOCKED',
    head: exactSha(result.result.revision) ? result.result.revision : null, prNumber: pr?.number ?? null,
    outcomeId: durable.id, bodySha256: sha256Body(durable.body), manual: true };
  await store.put(e.runId, r);
  if (result.status === 'implemented') await transitionManual(r, pr, result, false);
  return r.outcome;
}
