import { assertPr, readAuthority } from './live-authority.mjs';
import { currentStep } from './step-metadata.mjs';
import { digest, exactSha, fail, positive, REVIEWER, REPOSITORY } from './execution-contract.mjs';

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

export async function beginRemediation({ api, store, request, authorityDigest }) {
  if (Object.keys(request).some(key => !['operation', 'prNumber', 'reviewId', 'head'].includes(key))
    || !positive(request.prNumber) || !positive(request.reviewId) || !exactSha(request.head)) fail('PR_LIFECYCLE_REQUEST_INVALID');
  const read = async () => {
    const pr = await api.get(`/pulls/${request.prNumber}`); assertPr(pr, request.prNumber);
    const authority = await readAuthority(api, 'pull_request', pr.number, { step: currentStep(pr.labels) });
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
  const record = await store.get(request.reviewId) ?? { binding };
  if (digest(record.binding) !== digest(binding)) fail('PR_LIFECYCLE_BINDING_CHANGED');
  const pr = await transitionPr({ api, store, key: request.reviewId, record, head: request.head, draft: true,
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
