// Public admission diagnostics contain only a fixed predicate category. Never
// forward native API values, consumer configuration or arbitrary helper text.
const REASONS = new Set([
  'run_id', 'repository', 'actor', 'triggering_actor', 'status',
  'workflow_path', 'event', 'head_branch', 'run_attempt', 'run_title',
  'subject_number', 'issue_kind', 'pr_base_repository',
  'pr_head_repository', 'pr_head_branch'
]);

export function ownerRunRejectionReason(code, reason) {
  return code === 'OWNER_RUN_NOT_ADMITTED' && REASONS.has(reason) ? reason : undefined;
}

export function rejectOwnerRun(reason) {
  const error = new Error('OWNER_RUN_NOT_ADMITTED');
  error.code = error.message;
  error.details = { reason: ownerRunRejectionReason(error.code, reason) };
  throw error;
}
