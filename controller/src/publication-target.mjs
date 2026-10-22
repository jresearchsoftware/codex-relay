import { CONSUMER } from '../../consumer/consumer.mjs';
import { fail } from './execution-contract.mjs';
import { assertPr, linkedIssue } from './live-authority.mjs';
import { labelNames, stepLike } from './step-metadata.mjs';

// Branch reuse makes closed/merged PRs history, not current publication targets.
// Count current candidates before checking compatibility; never select one by
// silently discarding another open PR with conflicting authority.
export async function findCurrentIssuePullRequest(api, envelope, expectedNumber = null, publishedTransition = null) {
  // Continuation must also see wrong-base candidates rather than treating an
  // existing PR as absent and manufacturing a replacement.
  const base = envelope.continuation ? '' : `&base=${encodeURIComponent(CONSUMER.baseBranch)}`;
  const matches = await api.list(`/pulls?state=open&head=${CONSUMER.repository.split('/')[0]}:${encodeURIComponent(envelope.branch)}${base}`);
  if (matches.length > 1) fail('PR_AMBIGUOUS');
  if (matches.length === 0) {
    if (expectedNumber) fail(envelope.continuation ? 'PR_AUTHORITY_CHANGED' : 'PR_PUBLICATION_UNCERTAIN');
    return null;
  }
  const summary = matches[0];
  assertPr(summary, summary.number);
  if ((expectedNumber && summary.number !== expectedNumber)
    || summary.head.ref !== envelope.branch || linkedIssue(summary.body) !== envelope.issueNumber) fail('PR_AUTHORITY_CHANGED');
  // List responses omit mergeability. Read the same PR's current detail before
  // any readiness decision, without adopting movement between observations.
  const pr = await api.get(`/pulls/${summary.number}`);
  assertPr(pr, summary.number);
  // Only the immediate read following Writer's verified non-force push may
  // observe either end of that exact transition. List/detail propagation is
  // independent; neither response authorizes a new head or a Ready mutation.
  const knownTransition = publishedTransition && expectedNumber
    && [publishedTransition.previous, publishedTransition.head].every(head => /^[0-9a-f]{40}$/.test(head ?? ''))
    && [summary.head.sha, pr.head.sha].every(head => [publishedTransition.previous, publishedTransition.head].includes(head));
  if (pr.head.ref !== envelope.branch || linkedIssue(pr.body) !== envelope.issueNumber
    || pr.head.sha !== summary.head.sha && !knownTransition
    || pr.base.sha !== summary.base.sha) fail('PR_AUTHORITY_CHANGED');
  // Hydration must not erase a conflicting admission Step/title observation.
  if (pr.title !== summary.title) fail('STEP_DISPLAY_MISMATCH');
  if (JSON.stringify(labelNames(pr.labels).filter(stepLike).sort())
    !== JSON.stringify(labelNames(summary.labels).filter(stepLike).sort())) fail('STEP_LABEL_MISMATCH');
  return pr;
}
