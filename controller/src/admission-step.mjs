import { positive, fail, digest, REPOSITORY } from './execution-contract.mjs';

// Called under the existing publication lock. Only successful durable Writer
// admissions count; public labels, reviews and rejected routing never count.
export function nextAdmissionStep(records, task, { automaticCompletionVerified = false } = {}) {
  if (!Array.isArray(records) || !positive(task)) fail('AUTHORITY_ADMISSION_INVALID');
  const admitted = records.filter(record => record?.envelope?.issueNumber === task
    && (record.envelope.repository === undefined || record.envelope.repository === REPOSITORY) && !record.admissionBlock);
  if (admitted.some(record => !positive(record.envelope.step) || !positive(record.envelope.runId))) fail('PRIOR_ADMISSION_UNKNOWN');
  if (admitted.some(record => !record.outcome || record.commentIntent || record.lifecycleIntent
    || record.handoffComplete === false || record.publicationIntent
    || record.prIntent && !positive(record.prNumber)
    || record.envelope.route === 'auto' && !automaticCompletionVerified)) fail('PRIOR_EXECUTION_UNRESOLVED');
  const previous = admitted.sort((left, right) => left.envelope.step - right.envelope.step).at(-1);
  const step = (previous?.envelope.step ?? 0) + 1;
  if (!positive(step)) fail('AUTHORITY_STEP_INVALID');
  return { step, lineage: previous ? { attempt: previous.envelope.attemptId, step: previous.envelope.step, sha256: digest(previous.envelope) } : null };
}
