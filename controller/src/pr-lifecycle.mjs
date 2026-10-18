import { assertPr, currentReview, linkedIssue, readAuthority, revalidateAuthority } from './live-authority.mjs';
import { currentStep } from './step-metadata.mjs';
import { digest, exactSha, fail, positive, validateEnvelope, NATIVE_VALIDATIONS, OWNER, REVIEWER, REPOSITORY } from './execution-contract.mjs';
import { CONSUMER } from '../../consumer/consumer.mjs';
import { authorityMode, extractAuthorityRecord } from '../../contracts/src/github-authority.mjs';
import { readTaskAuthority } from './task-authority.mjs';

// A reversible native transition still reserves its exact intent before
// mutation. A fresh GET reconciles a lost response; replay never probes by push.
export async function transitionPr({ api, store, key, record, readPr, head, draft }) {
  let pr = await readPr();
  const intent = { number: pr.number, head, draft };
  if (record.lifecycleIntent && digest(record.lifecycleIntent) !== digest(intent)) fail('PR_LIFECYCLE_BINDING_CHANGED');
  if (pr.head.sha !== head) fail('PR_HEAD_OBSERVATION_STALE');
  if (typeof pr.draft !== 'boolean' || typeof pr.node_id !== 'string' || !pr.node_id) fail('PR_STATE_UNAVAILABLE');
  record.lifecycleIntent = intent; await store.put(key, record);
  // Re-read after reservation as well as after the mutation.
  pr = await readPr();
  if (pr.head.sha !== head || pr.number !== intent.number) fail('PR_HEAD_OBSERVATION_STALE');
  if (typeof pr.draft !== 'boolean') fail('PR_STATE_UNAVAILABLE');
  if (pr.draft !== draft) {
    let mutationError;
    try { await api[draft ? 'draft' : 'ready'](pr.node_id); } catch (error) { mutationError = error; }
    pr = await readPr();
    if (pr.head.sha !== head || pr.number !== intent.number) fail('PR_HEAD_OBSERVATION_STALE');
    if (pr.draft !== draft) {
      if (mutationError) throw mutationError;
      fail(draft ? 'DRAFT_OBSERVATION_CHANGED' : 'READY_OBSERVATION_CHANGED');
    }
  }
  record.lifecycleIntent = null;
  await store.put(key, record);
  return pr;
}

export async function beginRemediation({ api, store, request, authorityDigest, admittedEnvelope }) {
  if (Object.keys(request).some(key => !['operation', 'prNumber', 'reviewId', 'head'].includes(key))
    || !positive(request.prNumber) || !positive(request.reviewId) || !exactSha(request.head)) fail('PR_LIFECYCLE_REQUEST_INVALID');
  const read = async () => {
    const pr = await api.get(`/pulls/${request.prNumber}`); assertPr(pr, request.prNumber);
    let authority;
    if (admittedEnvelope?.request?.kind === 'admission') {
      // Only the internal broker supplies this already-resolved admission.
      // Revalidate its immutable binding without allocating another Step.
      validateEnvelope(admittedEnvelope);
      if (admittedEnvelope.target !== 'pull_request' || admittedEnvelope.number !== request.prNumber
        || admittedEnvelope.reviewId !== request.reviewId || admittedEnvelope.startHead !== request.head) fail('PR_LIFECYCLE_BINDING_CHANGED');
      authority = await revalidateAuthority(api, admittedEnvelope);
    } else {
      const review = currentReview(await api.list(`/pulls/${pr.number}/reviews`));
      const payload = extractAuthorityRecord(review.body, { repository: REPOSITORY, task: linkedIssue(pr.body) });
      if (payload?.schema_version === '4.0') {
        const issue = await api.get(`/issues/${linkedIssue(pr.body)}`);
        if (issue.state !== 'open' || issue.user?.login !== OWNER || issue.pull_request
          || authorityMode(issue.body) !== 'github-native-v1') fail('ISSUE_NOT_ADMITTED');
        // Reviewer publication drafts the reviewed PR before any execution.
        // Resolve sources/profile directly: no Request, snapshot or Step exists.
        const typed = await readTaskAuthority(api, issue, pr, { streamlined: true,
          projectDefaults: { model: CONSUMER.defaultProfile.cliModelId, effort: CONSUMER.defaultProfile.effort,
            subagents: true, validation: [...NATIVE_VALIDATIONS] },
          startingState: { branch: pr.head.ref, base_sha: pr.base.sha, starting_head: pr.head.sha, existing_pr: pr.number } });
        if (typed.request.kind !== 'change-request' || typed.request.parent.number !== pr.number) fail('CURRENT_CHANGE_REQUEST_MISSING');
        if (typed.request.branch !== pr.head.ref) fail('STARTING_STATE_MISMATCH');
        authority = { ...typed, pr, review: typed.record, startHead: typed.request.reviewed_head_sha };
      } else authority = await readAuthority(api, 'pull_request', pr.number, { step: currentStep(pr.labels) });
    }
    const publisher = await api.userIdentity(REVIEWER);
    // Typed records retain the verified native publisher as `author`; legacy
    // GitHub review responses use `user`. Neither spelling grants authority.
    const author = authority.request ? authority.review?.author : authority.review?.user;
    if (publisher.login !== REVIEWER || publisher.type !== 'Bot' || !positive(publisher.id)
      || author?.id !== publisher.id || author?.type !== 'Bot'
      || authority.review.id !== request.reviewId || authority.startHead !== request.head
      || authority.pr.head.sha !== request.head) fail('CURRENT_CHANGE_REQUEST_MISSING');
    if (authorityDigest && authority.authorityDigest !== authorityDigest) fail('AUTHORITY_CHANGED');
    return authority;
  };
  const authority = await read();
  const binding = { repository: REPOSITORY, prNumber: request.prNumber, reviewId: request.reviewId,
    head: request.head, authorityDigest: authority.authorityDigest };
  // Only protected Writer can supply a retained admission at a later head.
  // Its lifecycle namespace is keyed by run, leaving the original review's
  // exact A/head/authority intent and recovery bytes untouched.
  const continuing = admittedEnvelope?.request?.kind === 'admission'
    && admittedEnvelope.startHead !== admittedEnvelope.request.reviewed_head_sha;
  const key = continuing ? admittedEnvelope.runId : request.reviewId;
  if (continuing) binding.admission = digest(admittedEnvelope);
  const record = await store.get(key) ?? { binding };
  if (digest(record.binding) !== digest(binding)) fail('PR_LIFECYCLE_BINDING_CHANGED');
  if (await store.isRetained?.(key)) {
    // Completed SERIAL receipts are read-only evidence, never a new intent.
    // Live authority above and below must still identify the exact old review.
    const fresh = await read();
    if (fresh.authorityDigest !== binding.authorityDigest) fail('AUTHORITY_CHANGED');
    if (record.lifecycleIntent !== null || fresh.pr.draft !== true) fail('SERIAL_POOL_LIFECYCLE_UNRESOLVED');
    return { repository: REPOSITORY, prNumber: fresh.pr.number, reviewId: request.reviewId, head: fresh.pr.head.sha, draft: true };
  }
  const pr = await transitionPr({ api, store, key, record, head: request.head, draft: true,
    readPr: async () => {
      const fresh = await read();
      if (fresh.authorityDigest !== binding.authorityDigest) fail('AUTHORITY_CHANGED');
      return fresh.pr;
    } });
  return { repository: REPOSITORY, prNumber: pr.number, reviewId: request.reviewId, head: pr.head.sha, draft: pr.draft };
}

// Owner orchestration calls this immediately after successful Reviewer
// publication, before any automatic launch or manual remediation handoff.
export async function continueAfterChangeRequest(publication, writer) {
  const action = publication?.structuredContent?.pr_lifecycle;
  if (publication?.isError || action?.operation !== 'begin-remediation') fail('CHANGE_REQUEST_PUBLICATION_REQUIRED');
  return writer.invoke(action);
}
