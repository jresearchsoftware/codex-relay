import { fail, positive } from './execution-contract.mjs';
import { RUN_NAME_IDENTITY_MAX_CHARS } from './run-name.mjs';

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

export function assertPrStepTitle(pr, issueNumber, step) {
  const prefix = `Task ${issueNumber} · Step ${step}`;
  if (pr.title !== prefix && !pr.title?.startsWith(`${prefix} · `)) fail('STEP_DISPLAY_MISMATCH');
}

export function projectedRequestTitle(request) {
  const cr = request.change_request_id ? ` · ${request.change_request_id}` : '';
  const text = `Task ${request.task} · Step ${request.step}${cr} · ${request.purpose}`;
  const characters = Array.from(text);
  return characters.length <= RUN_NAME_IDENTITY_MAX_CHARS ? text
    : `${characters.slice(0, RUN_NAME_IDENTITY_MAX_CHARS - 1).join('')}…`;
}
