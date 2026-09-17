import { fail, positive } from './execution-contract.mjs';

export const READY_LABELS = ['codex-ready-auto', 'codex-ready-manual'];
export const labelNames = labels => (labels ?? []).map(label => typeof label === 'string' ? label : label.name);
export const stepLike = name => /^step/i.test(name ?? '');

// Read only current native metadata. No defaults, history or attempt arithmetic.
export function currentStep(labels) {
  const names = labelNames(labels).filter(stepLike);
  if (!names.length) fail('STEP_LABEL_MISSING');
  if (names.length !== 1) fail('STEP_LABEL_MULTIPLE');
  const match = /^step-([1-9][0-9]*)$/.exec(names[0]);
  if (!match || !positive(Number(match[1]))) fail('STEP_LABEL_INVALID');
  return Number(match[1]);
}

export function assertStep(labels, step) {
  if (currentStep(labels) !== step) fail('STEP_LABEL_MISMATCH');
}

export function changeRequestStep(contract) {
  // Historical v1 has an explicit required launch title instead of typed Step.
  // This reads that current CR's profile, never previous CRs or prose history.
  const value = contract.schema_version === '2.0' ? contract.step
    : Number(/^Task\s+#?[0-9]+\s*[-–—:·|]+\s*Step\s+([1-9][0-9]*)\b/i.exec(contract.remediation_thread_title)?.[1]);
  if (!positive(value)) fail('CHANGE_REQUEST_STEP_INVALID');
  return value;
}

export function assertPrStepTitle(pr, issueNumber, step) {
  const prefix = `Task ${issueNumber} · Step ${step}`;
  if (pr.title !== prefix && !pr.title?.startsWith(`${prefix} · `)) fail('STEP_DISPLAY_MISMATCH');
}
