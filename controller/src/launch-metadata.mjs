// Native launch commands and their display metadata; runId owns the attempt.
import { fail, positive } from './execution-contract.mjs';
import { RUN_NAME_MAX_CHARS } from './run-name.mjs';
import { currentStep, labelNames, READY_LABELS, stepLike } from './step-metadata.mjs';

function positiveDecimal(value, code) {
  if (!['string', 'number'].includes(typeof value) || !positive(Number(value)) || String(Number(value)) !== String(value)) fail(code);
  return Number(value);
}

export const launchStep = value => positiveDecimal(value, 'LAUNCH_STEP_INVALID');

export function remediationThreadTitle(title, issueNumber, step) {
  // Reuse only the descriptive tail of old CR display metadata. Neither its
  // Task nor Step supplies identity or a sequencing check for this launch.
  const purpose = String(title).replace(/^Task\s+#?[0-9]+[A-Za-z]*\s*[-–—:·|]*\s*Step\s+[0-9]+\s*[-–—:·|]*\s*/i, '');
  return `Task ${issueNumber} — Step ${launchStep(step)} — ${purpose}`;
}

export function dispatchRunName({ route, issueNumber, step, target, number }) {
  const phase = route === 'manual' ? 'Manual handoff' : target === 'pull_request' ? 'Auto remediation' : 'Auto implementation';
  const title = `${phase} · Task ${issueNumber} · Step ${step}${target === 'pull_request' ? ` · PR #${number}` : ''}`;
  if (Array.from(title).length > RUN_NAME_MAX_CHARS) fail('LAUNCH_METADATA_TOO_LONG');
  return title;
}

export function parseLaunchInputs(inputs) {
  if (!inputs || !['auto', 'manual'].includes(inputs.route)) fail('ROUTE_INVALID');
  const issueNumber = positiveDecimal(inputs.task, 'LAUNCH_TASK_INVALID');
  const step = launchStep(inputs.step);
  const target = inputs.pull_request ? 'pull_request' : 'issue';
  const number = target === 'pull_request' ? positiveDecimal(inputs.pull_request, 'LAUNCH_PR_INVALID') : issueNumber;
  const launch = { route: inputs.route, issueNumber, step, target, number };
  dispatchRunName(launch);
  return launch;
}

// Mirrors the workflow expression. Issue titles/prose are never Step inputs.
// GitHub's native label projection also displays unrelated labels verbatim.
function labelRunPrefix({ route, target, number }) {
  const phase = route === 'manual' ? 'Manual handoff' : target === 'pull_request' ? 'Auto remediation' : 'Auto implementation';
  return `${phase} · ${target === 'issue' ? `Task ${number}` : `PR #${number}`} · `;
}

export function labelRunName(launch, subject) {
  return labelRunPrefix(launch) + (launch.target === 'issue' ? labelNames(subject.labels).join(' · ') : subject.title);
}

export function labelRunCommandMatches(name, launch) {
  const prefix = labelRunPrefix(launch);
  if (typeof name !== 'string' || !name.startsWith(prefix)) return false;
  if (launch.target === 'pull_request') return true;
  const commands = name.slice(prefix.length).split(' · ').filter(value => READY_LABELS.includes(value));
  return commands.length === 1 && commands[0] === `codex-ready-${launch.route}`;
}

export function labelRunMatches(name, launch, subject) {
  if (launch.target === 'pull_request') return name === labelRunName(launch, subject);
  const prefix = labelRunPrefix(launch);
  if (typeof name !== 'string' || !name.startsWith(prefix)) return false;
  // Unrelated labels are display-only, including additions/removals/reordering.
  // Only the reserved Step namespace and ready commands bind this projection.
  const coordinates = names => names.filter(value => stepLike(value) || READY_LABELS.includes(value)).sort();
  return JSON.stringify(coordinates(name.slice(prefix.length).split(' · ')))
    === JSON.stringify(coordinates(labelNames(subject.labels)));
}

export function parseLabelLaunch(event, eventName) {
  if (event.action !== 'labeled' || !READY_LABELS.includes(event.label?.name)
    || !['issues', 'pull_request_target'].includes(eventName)) fail('READY_EVENT_REQUIRED');
  const target = eventName === 'issues' ? 'issue' : 'pull_request';
  const subject = target === 'issue' ? event.issue : event.pull_request;
  if (!positive(subject?.number) || (target === 'issue' && subject.pull_request)) fail('ROUTE_INVALID');
  // Route without admitting. The Writer binds the native run/event/target
  // before validating Step and Issue/CR authority, including safe rejection.
  // An invalid event snapshot stays invalid even if labels are repaired before
  // admission. Null cannot become a Step default from a later REST read.
  let step = null;
  try { step = currentStep(subject.labels); }
  catch (error) { if (!['STEP_LABEL_MISSING', 'STEP_LABEL_MULTIPLE', 'STEP_LABEL_INVALID'].includes(error.code)) throw error; }
  return { target, number: subject.number, step,
    route: event.label.name === READY_LABELS[0] ? 'auto' : 'manual', transport: 'label' };
}
