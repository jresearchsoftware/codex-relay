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

export function projectedRequestTitle(request) {
  const cr = request.kind === 'change-request' ? ` · ${request.change_request_id}` : '';
  const text = `Task ${request.task} · Step ${request.step}${cr} · ${request.purpose}`;
  const characters = Array.from(text);
  return characters.length <= RUN_NAME_IDENTITY_MAX_CHARS ? text
    : `${characters.slice(0, RUN_NAME_IDENTITY_MAX_CHARS - 1).join('')}…`;
}

// Same bounded native projection as Reviewer; CR identity is explicit even when
// the caller's descriptive thread title omitted it. Task comes from live linkage.
export function reviewStepTitle(contract, issueNumber) {
  if (!positive(issueNumber)) fail('ROUTE_INVALID');
  const step = changeRequestStep(contract);
  const id = contract.change_request_id;
  if (typeof id !== 'string' || !id || typeof contract.remediation_thread_title !== 'string') fail('STEP_DISPLAY_MISMATCH');
  const text = contract.remediation_thread_title.replace(/\s+/g, ' ').trim();
  let tail = text;
  if (text.startsWith('Task ')) {
    const at = text.indexOf('Step ');
    if (at >= 0) {
      const rest = text.slice(at + 5);
      const digits = /^[0-9]+/.exec(rest)?.[0];
      if (digits) tail = rest.slice(digits.length).replace(/^[\s\-–—:·|/]+/, '');
    }
  }
  if (tail.startsWith(id)) tail = tail.slice(id.length).replace(/^[\s\-–—:·|/]+/, '');
  const identity = `Task ${issueNumber} · Step ${step}`;
  if (Array.from(identity).length >= RUN_NAME_IDENTITY_MAX_CHARS) fail('LAUNCH_METADATA_TOO_LONG');
  const full = `${identity} · ${id} · ${tail}`;
  return Array.from(full).length <= RUN_NAME_IDENTITY_MAX_CHARS ? full
    : Array.from(full).slice(0, RUN_NAME_IDENTITY_MAX_CHARS - 1).join('') + '…';
}
