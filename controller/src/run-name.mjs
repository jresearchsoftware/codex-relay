export const RUN_NAME_MAX_CHARS = 80;
// PR titles are the existing native metadata consumed by the routing and
// validation workflow run-name expressions. Leave room for the longest phase
// prefix so that the final displayed name, not just the metadata, is bounded.
export const RUN_NAME_IDENTITY_MAX_CHARS = RUN_NAME_MAX_CHARS - Array.from('Exact-head validation · ').length;

const SEPARATOR = ' · ';
const TASK_PATTERN = /\bTask\s+#?([0-9]+)\b/i;
const STEP_PATTERN = /\bStep\s+([0-9]+)\b/i;

function normalized(value) {
  return String(value ?? '').normalize('NFC').replace(/\s+/g, ' ').trim();
}

function codePoints(value) {
  return Array.from(value);
}

function take(value, count) {
  return codePoints(value).slice(0, count).join('');
}

function dropLeadingSeparators(value) {
  return value.replace(/^(?:[-–—:·|/]+|\s)+/, '').trim();
}

function threadParts(thread) {
  const text = normalized(thread);
  const task = text.match(TASK_PATTERN);
  const step = text.match(STEP_PATTERN);
  const identity = [task && `Task ${task[1]}`, step && `Step ${step[1]}`].filter(Boolean).join(SEPARATOR);
  const end = step?.index !== undefined
    ? step.index + step[0].length
    : task?.index !== undefined ? task.index + task[0].length : 0;
  const tail = dropLeadingSeparators(text.slice(end));
  return { text, identity: identity || text, tail };
}

function phaseText(phase) {
  const value = normalized(phase);
  if (!['Auto implementation', 'Auto remediation', 'Exact-head validation', 'Manual handoff'].includes(value)) {
    throw new TypeError('Unsupported run-name phase');
  }
  return value;
}

export function threadCorrelationIdentity(thread) {
  const parts = threadParts(thread);
  return parts.tail && parts.identity !== parts.text
    ? `${parts.identity}${SEPARATOR}${parts.tail}`
    : parts.identity;
}

function boundedIdentity(parts, limit) {
  const full = parts.tail && parts.identity !== parts.text
    ? `${parts.identity}${SEPARATOR}${parts.tail}`
    : parts.identity;
  if (codePoints(full).length <= limit) return full;
  const identityPrefix = parts.identity;
  if (!parts.tail || codePoints(identityPrefix).length >= limit) return take(identityPrefix, limit);
  const available = limit - codePoints(identityPrefix + SEPARATOR).length;
  if (available <= 0) return identityPrefix;
  if (codePoints(parts.tail).length <= available) return full;
  if (available === 1) return `${identityPrefix}${SEPARATOR}…`;
  return `${identityPrefix}${SEPARATOR}${take(parts.tail, available - 1)}…`;
}

export function boundedThreadCorrelationIdentity(thread) {
  return boundedIdentity(threadParts(thread), RUN_NAME_IDENTITY_MAX_CHARS);
}

export function formatRunName(phase, thread) {
  const prefix = `${phaseText(phase)}${SEPARATOR}`;
  const parts = threadParts(thread);
  const available = RUN_NAME_MAX_CHARS - codePoints(prefix).length;
  // Task and Step are the stable correlation fields. Only the descriptive
  // tail is shortened, so a long purpose can never hide the phase or IDs.
  if (available <= 0) return take(prefix, RUN_NAME_MAX_CHARS);
  return `${prefix}${boundedIdentity(parts, available)}`;
}

export function automaticRunName({ target, thread }) {
  return formatRunName(target === 'pull_request' ? 'Auto remediation' : 'Auto implementation', thread);
}

export function exactHeadValidationRunName(thread) {
  return formatRunName('Exact-head validation', thread);
}
