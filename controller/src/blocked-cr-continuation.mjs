import { CONSUMER_DIGEST } from '../../consumer/consumer.mjs';
import { REPOSITORY, WRITER, digest, exactSha, positive, fail, validateEnvelope } from './execution-contract.mjs';
import { admissionBinding, canonicalAuthorityJson, extractAuthorityRecord, sha256Body } from '../../contracts/src/github-authority.mjs';
import { revalidateAuthority } from './live-authority.mjs';

const equal = (left, right) => canonicalAuthorityJson(left) === canonicalAuthorityJson(right);
const invalid = () => fail('AUTHORITY_CONTINUATION_INVALID');

// Called only by trusted Writer while holding its existing admission lock.
// A moved PR ref, a worker claim or a public Outcome alone is never lineage.
export async function blockedCrContinuation(api, { typed, pr, step, lineage, previousRecord, targetBase }) {
  const prior = previousRecord;
  const e = prior?.envelope;
  if (!e || e.request?.kind !== 'admission' || e.request.schema_version !== '4.0') invalid();
  validateEnvelope(e);
  const q = typed.request;
  const head = prior.outcome?.head;
  if (!lineage || lineage.attempt !== e.attemptId || lineage.step !== e.step || lineage.sha256 !== digest(e)
    || step !== e.step + 1 || e.repository !== REPOSITORY || e.consumerDigest !== CONSUMER_DIGEST
    || e.target !== 'pull_request' || e.number !== pr.number || e.issueNumber !== q.task
    || e.branch !== q.branch || e.branch !== pr.head.ref || e.historicalBase !== q.base_sha
    || e.targetBase !== targetBase || pr.base.sha !== e.targetBase
    || e.reviewId !== typed.reference.id || !equal(e.request.authority.change_request, typed.authority.change_request)
    || e.request.change_request_id !== q.change_request_id || e.request.reviewed_head_sha !== q.reviewed_head_sha
    || prior.admissionBlock || prior.outcome?.status !== 'BLOCKED' || prior.outcome.prNumber !== pr.number
    || prior.prNumber != null && prior.prNumber !== pr.number
    || !positive(prior.outcome.outcomeId) || !exactSha(head)
    || prior.publicationIntent || prior.commentIntent || prior.lifecycleIntent || prior.relationshipIntent
    || prior.readinessIntent || prior.successOutcomeIntent || prior.prepublicationRecovery
    || prior.handoffComplete === false || prior.prIntent && prior.prNumber !== pr.number) invalid();
  if (pr.head.sha !== head) fail('STARTING_STATE_MISMATCH');
  if (e.route === 'auto' ? prior.publishedHead !== head : !prior.manualSubmission || prior.outcome.manual !== true) invalid();

  // Verify original source bodies as well as the current CR. Later Decisions
  // do not rewrite the delivered admission or its old publication receipts.
  await revalidateAuthority(api, e, { reporting: true });
  const writer = await api.userIdentity(WRITER);
  const native = await api.get(`/issues/comments/${prior.outcome.outcomeId}`);
  if (writer.login !== WRITER || writer.type !== 'Bot' || !positive(writer.id)
    || native.id !== prior.outcome.outcomeId || native.user?.login !== WRITER
    || native.user?.type !== 'Bot' || native.user?.id !== writer.id
    || native.issue_url !== `https://api.github.com/repos/${REPOSITORY}/issues/${pr.number}`
    || sha256Body(native.body ?? '') !== prior.outcome.bodySha256
    || !native.body.endsWith(`<!-- relay:${e.attemptId}:outcome -->`)) invalid();
  const outcome = extractAuthorityRecord(native.body);
  if (outcome?.schema_version !== '4.0' || outcome.kind !== 'outcome' || outcome.status !== 'blocked'
    || outcome.repository !== REPOSITORY || outcome.task !== q.task || outcome.step !== e.step
    || outcome.attempt !== e.attemptId || outcome.parent.kind !== 'pull_request' || outcome.parent.number !== pr.number
    || outcome.charter_sha256 !== e.request.charter_sha256 || !equal(outcome.authority, e.request.authority)
    || !equal(outcome.admission, admissionBinding(e.request))
    || !['git', 'no-change'].includes(outcome.result.kind) || outcome.result.revision !== head) invalid();
  if (e.route === 'manual') {
    const published = prior.manualSubmission.publishedResult ?? outcome;
    // Writer can add resolution/drift to the submitted claim. Match its
    // original digest against only those bounded optional additions.
    const originals = [outcome];
    if (prior.manualSubmission.publishedResult) for (const field of ['authority_resolution', 'authority_drift']) {
      for (const value of [...originals]) if (Object.hasOwn(value, field)) {
        const candidate = { ...value }; delete candidate[field]; originals.push(candidate);
      }
    }
    if (!equal(prior.manualSubmission.parent, outcome.parent) || !equal(published, outcome)
      || !originals.some(value => sha256Body(canonicalAuthorityJson(value))
      === prior.manualSubmission.sha256)) invalid();
  }
  const directions = typed.decisions.filter(({ reference, decision }) => decision.parent.kind === 'issue'
    && decision.parent.number === q.task && reference.id > native.id
    && !e.request.authority.decisions.some(previous => equal(previous, reference)));
  if (!directions.length) invalid();
  const amendments = Object.assign({}, ...typed.decisions.filter(({ reference }) =>
    !e.request.authority.decisions.some(previous => equal(previous, reference))).map(({ decision }) => decision.amendments));
  const pins = { branch: q.branch, base_sha: q.base_sha, starting_head: head, existing_pr: pr.number };
  if (Object.entries(pins).some(([field, expected]) => Object.hasOwn(amendments, field)
    && amendments[field] !== expected)) fail('STARTING_STATE_MISMATCH');
  const refs = await api.get(`/git/matching-refs/heads/${q.branch}`);
  const matches = Array.isArray(refs) ? refs.filter(ref => ref.ref === `refs/heads/${q.branch}`) : [];
  if (matches.length !== 1 || matches[0].object?.sha !== head) fail('STARTING_STATE_MISMATCH');
  // Manual source commits are owner-published; Writer attests their exact PR
  // result, not their authorship. Both routes retain a descendant Git chain.
  if (head !== e.startHead) {
    const comparison = await api.get(`/compare/${e.startHead}...${head}?per_page=1`);
    if (comparison.status !== 'ahead' || comparison.base_commit?.sha !== e.startHead
      || comparison.merge_base_commit?.sha !== e.startHead) fail('STARTING_STATE_MISMATCH');
  }
  return { branch: q.branch, base_sha: q.base_sha, starting_head: head, existing_pr: pr.number };
}
