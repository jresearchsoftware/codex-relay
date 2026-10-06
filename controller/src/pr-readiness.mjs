import { exactSha, fail } from './execution-contract.mjs';

// GitHub computes mergeability asynchronously. Null (including an omitted
// field) is an observation gap, never proof of a conflict.
export function prReadiness(pr, head) {
  if (!exactSha(head) || pr?.head?.sha !== head) fail('PR_HEAD_OBSERVATION_STALE');
  if (!exactSha(pr?.base?.sha)) fail('PR_BASE_OBSERVATION_INVALID');
  const status = pr.mergeable === false ? 'BLOCKED' : pr.mergeable === true ? 'READY' : 'PENDING';
  return { status, code: status === 'BLOCKED' ? 'MERGE_CONFLICT' : status === 'READY' ? 'MERGEABLE' : 'MERGEABILITY_UNRESOLVED',
    head, observedBase: pr.base.sha, mergeable: typeof pr.mergeable === 'boolean' ? pr.mergeable : null };
}

export function readinessOutcomeLines(readiness, draft) {
  return `Review readiness: ${readiness.status} (${readiness.code})\nReadiness observed head: ${readiness.head}\nObserved integration base: ${readiness.observedBase}\nNative PR draft: ${draft ? 'true' : 'false'}`;
}
