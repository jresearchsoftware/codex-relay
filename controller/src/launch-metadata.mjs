// Native launch commands and their display metadata; runId owns the attempt.
import { fail, positive } from './execution-contract.mjs';
import { RUN_NAME_MAX_CHARS } from './run-name.mjs';
import { LAUNCH_ROUTES, READY_LABELS, readyLabel } from './step-metadata.mjs';

function positiveDecimal(value, code) {
  if (!['string', 'number'].includes(typeof value) || !positive(Number(value)) || String(Number(value)) !== String(value)) fail(code,
    { check: code.toLowerCase(), expected: 'canonical positive decimal integer', observed: value ?? null });
  return Number(value);
}

export const launchStep = value => positiveDecimal(value, 'LAUNCH_STEP_INVALID');

function launchPhase(route, target) {
  if (route === 'manual') return 'Manual handoff';
  const backend = route === 'app-server' ? 'App Server' : 'Auto';
  return `${backend} ${target === 'pull_request' ? 'remediation' : 'implementation'}`;
}

export function dispatchRunName({ route, issueNumber, step, target, number }) {
  const phase = launchPhase(route, target);
  const title = `${phase} · Task ${issueNumber}${step ? ` · Step ${step}` : ''}${target === 'pull_request' ? ` · PR #${number}` : ''}`;
  if (Array.from(title).length > RUN_NAME_MAX_CHARS) fail('LAUNCH_METADATA_TOO_LONG');
  return title;
}

export function parseLaunchInputs(inputs) {
  if (!LAUNCH_ROUTES.includes(inputs?.route)) fail('ROUTE_INVALID', { check: 'inputs.route', expected: LAUNCH_ROUTES, observed: inputs?.route ?? null });
  const issueNumber = positiveDecimal(inputs.task, 'LAUNCH_TASK_INVALID');
  const step = inputs.step === undefined || inputs.step === '' ? null : launchStep(inputs.step);
  const target = inputs.pull_request ? 'pull_request' : 'issue';
  const number = target === 'pull_request' ? positiveDecimal(inputs.pull_request, 'LAUNCH_PR_INVALID') : issueNumber;
  const launch = { route: inputs.route, issueNumber, step, target, number };
  dispatchRunName(launch);
  return launch;
}

// Mirrors the workflow expression. Issue titles/prose are never Step inputs.
// GitHub's native label projection also displays unrelated labels verbatim.
function labelRunPrefix({ route, target, number }) {
  const phase = launchPhase(route, target);
  return `${phase} · ${target === 'issue' ? `Task ${number}` : `PR #${number}`} · `;
}

export function labelRunName(launch, subject) {
  return labelRunPrefix(launch) + (launch.target === 'issue' ? readyLabel(launch.route) : subject.title);
}

export function labelRunCommandMatches(name, launch) {
  const prefix = labelRunPrefix(launch);
  if (typeof name !== 'string' || !name.startsWith(prefix)) return false;
  if (launch.target === 'pull_request') return true;
  const commands = name.slice(prefix.length).split(' · ').filter(value => READY_LABELS.includes(value));
  return commands.length === 1 && commands[0] === readyLabel(launch.route);
}

export function parseLabelLaunch(event, eventName) {
  for (const [check, expected, observed, valid] of [
    ['event.action', 'labeled', event.action, event.action === 'labeled'],
    ['event.label', READY_LABELS, event.label?.name, READY_LABELS.includes(event.label?.name)],
    ['event.name', ['issues', 'pull_request_target'], eventName, ['issues', 'pull_request_target'].includes(eventName)]
  ]) if (!valid) fail('READY_EVENT_REQUIRED', { check, expected, observed: observed ?? null });
  const target = eventName === 'issues' ? 'issue' : 'pull_request';
  const subject = target === 'issue' ? event.issue : event.pull_request;
  if (!positive(subject?.number)) fail('ROUTE_INVALID', { check: 'event.subject.number', expected: 'positive native target number', observed: subject?.number ?? null });
  if (target === 'issue' && subject.pull_request) fail('ROUTE_INVALID', { check: 'event.subject.kind', expected: 'issue', observed: 'pull_request' });
  // Routing authenticates the command; Writer resolves the canonical Issue's
  // numbering position under its existing serialization boundary.
  const route = LAUNCH_ROUTES.find(value => readyLabel(value) === event.label.name);
  return { target, number: subject.number, step: null, route, transport: 'label' };
}
