import { positive, fail, digest, REPOSITORY } from './execution-contract.mjs';
import { currentStep, labelNames, stepLike } from './step-metadata.mjs';

// Called under the existing publication lock. Allocation is independent of
// execution/publication completion; those guards own their actual resources.
// Successful durable Writer admissions prove execution, while the canonical
// Issue may also carry the owner's later standalone/manual numbering position.
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

export function nextAdmissionStep(records, task, labels = []) {
  const previous = latestAdmissionRecord(records, task);
  let position = 0;
  try { if (labelNames(labels).some(stepLike)) position = currentStep(labels); }
  catch (error) {
    if (!['STEP_LABEL_MULTIPLE', 'STEP_LABEL_INVALID'].includes(error.code)) throw error;
    error.message = `${error.code}: Task #${task} needs no Step label or exactly one valid step-N label. Reconcile the canonical Issue before applying a fresh owner command; no Step was allocated.`;
    throw error;
  }
  if (position && position < (previous?.envelope.step ?? 0))
    throw Object.assign(new Error(`STEP_LABEL_BEHIND_ADMISSION: Task #${task} label step-${position} is behind successful Writer Step ${previous.envelope.step}. Reconcile the Issue's authorized numbering position without rewriting admission history; no Step was allocated.`),
      { code: 'STEP_LABEL_BEHIND_ADMISSION' });
  const step = Math.max(position, previous?.envelope.step ?? 0) + 1;
  if (!positive(step)) throw Object.assign(new Error(`AUTHORITY_STEP_INVALID: Task #${task} cannot advance beyond the supported Step integer range. Reconcile numbering authority before a new launch; no Step was allocated.`),
    { code: 'AUTHORITY_STEP_INVALID' });
  return { step, lineage: previous ? { attempt: previous.envelope.attemptId, step: previous.envelope.step, sha256: digest(previous.envelope) } : null };
}
