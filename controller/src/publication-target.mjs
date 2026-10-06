import { CONSUMER } from '../../consumer/consumer.mjs';
import { fail } from './execution-contract.mjs';
import { assertPr, linkedIssue } from './live-authority.mjs';

// Branch reuse makes closed/merged PRs history, not current publication targets.
// Count current candidates before checking compatibility; never select one by
// silently discarding another open PR with conflicting authority.
export async function findCurrentIssuePullRequest(api, envelope, expectedNumber = null) {
  // Continuation must also see wrong-base candidates rather than treating an
  // existing PR as absent and manufacturing a replacement.
  const base = envelope.continuation ? '' : `&base=${encodeURIComponent(CONSUMER.baseBranch)}`;
  const matches = await api.list(`/pulls?state=open&head=${CONSUMER.repository.split('/')[0]}:${encodeURIComponent(envelope.branch)}${base}`);
  if (matches.length > 1) fail('PR_AMBIGUOUS');
  if (matches.length === 0) {
    if (expectedNumber) fail(envelope.continuation ? 'PR_AUTHORITY_CHANGED' : 'PR_PUBLICATION_UNCERTAIN');
    return null;
  }
  const pr = matches[0];
  assertPr(pr, pr.number);
  if ((expectedNumber && pr.number !== expectedNumber)
    || pr.head.ref !== envelope.branch || linkedIssue(pr.body) !== envelope.issueNumber) fail('PR_AUTHORITY_CHANGED');
  return pr;
}
