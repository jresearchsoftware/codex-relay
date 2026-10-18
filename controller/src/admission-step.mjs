import { positive, fail, digest, REPOSITORY } from './execution-contract.mjs';

// Called under the existing publication lock. Allocation is independent of
// execution/publication completion; those guards own their actual resources.
// Only successful durable Writer admissions count, never public projections.
export function latestAdmissionRecord(records, task) {
  if (!Array.isArray(records) || !positive(task)) fail('AUTHORITY_ADMISSION_INVALID');
  const admitted = records.filter(record => record?.envelope?.issueNumber === task
    && (record.envelope.repository === undefined || record.envelope.repository === REPOSITORY) && !record.admissionBlock);
  if (admitted.some(record => !positive(record.envelope.step) || !positive(record.envelope.runId)
    || record.envelope.attemptId !== `run-${record.envelope.runId}`)) fail('PRIOR_ADMISSION_UNKNOWN');
  const native = record => record.nativeAdmission || record.envelope.request?.kind === 'admission';
  const steps = new Map(); const runs = new Set();
  for (const record of admitted) {
    const previous = steps.get(record.envelope.step);
    if (previous && (native(record) || native(previous)) || runs.has(record.envelope.runId)) fail('PRIOR_ADMISSION_CONFLICT');
    steps.set(record.envelope.step, record); runs.add(record.envelope.runId);
  }
  return admitted.sort((left, right) => left.envelope.step - right.envelope.step).at(-1) ?? null;
}

export function nextAdmissionStep(records, task) {
  const previous = latestAdmissionRecord(records, task);
  const step = (previous?.envelope.step ?? 0) + 1;
  if (!positive(step)) fail('AUTHORITY_STEP_INVALID');
  return { step, lineage: previous ? { attempt: previous.envelope.attemptId, step: previous.envelope.step, sha256: digest(previous.envelope) } : null };
}
