import { exactSha } from './execution-contract.mjs';
import { threadCorrelationIdentity } from './run-name.mjs';
import { boundedDiagnosticText } from './diagnostics.mjs';

const SAFE_CODE = /^[A-Z][A-Z0-9_]{0,79}$/;
const SAFE_BOUNDARY = /^[a-z][a-z0-9-]{0,39}$/;
const SAFE_ACTION = /^[a-z][a-z0-9-]{0,127}$/;
const SAFE_TEXT = /^[^\u0000-\u001f\u007f]{1,512}$/;

function safeCode(value) {
  return typeof value === 'string' && SAFE_CODE.test(value) ? value : 'UNAVAILABLE';
}

function safeBoundary(value) {
  return typeof value === 'string' && SAFE_BOUNDARY.test(value) ? value : 'UNAVAILABLE';
}

function safeAction(value) {
  return typeof value === 'string' && SAFE_ACTION.test(value) ? value : 'UNAVAILABLE';
}

function safeText(value, fallback = 'UNAVAILABLE') {
  if (typeof value !== 'string') return fallback;
  const normalized = boundedDiagnosticText(value, 512).text.normalize('NFC').replace(/\s+/g, ' ').trim();
  return SAFE_TEXT.test(normalized) ? normalized : fallback;
}

function commandText(value) {
  return String(value).replace(/%/g, '%25').replace(/\r/g, '%0D').replace(/\n/g, '%0A');
}

export function admissionWarningSummary(warnings) {
  if (!Array.isArray(warnings)) return '';
  return warnings.map(warning => {
    const code = safeCode(warning?.code);
    const field = safeText(warning?.field, 'metadata');
    const resolved = safeText(warning?.resolved, 'UNAVAILABLE');
    return `${code} (${field} -> ${resolved})`;
  }).filter(value => value.startsWith('UNAVAILABLE') === false).slice(0, 16).join('; ').slice(0, 1800);
}

export function emitAdmissionWarnings(warnings, write = value => process.stderr.write(value)) {
  if (!Array.isArray(warnings) || typeof write !== 'function') return 0;
  const seen = new Set(); let emitted = 0;
  for (const warning of warnings) {
    const code = safeCode(warning?.code);
    const field = safeText(warning?.field, 'metadata');
    const resolved = safeText(warning?.resolved, 'UNAVAILABLE');
    const message = safeText(warning?.message, `${field} was normalized or defaulted`);
    const key = `${code}\0${field}\0${resolved}\0${message}`;
    if (seen.has(key)) continue;
    seen.add(key);
    write(`::warning title=Codex admission::${commandText(`${field}: ${message}; resolved to ${resolved}`)}\n`);
    emitted += 1;
  }
  return emitted;
}

export function blockedOutcomeToken(e) {
  // target is admitted structured state. The input contains raw Issue/CR
  // prose and must never be parsed by the presentation layer for authority.
  return e?.target === 'pull_request' ? 'REMEDIATION_BLOCKED' : 'IMPLEMENTATION_BLOCKED';
}

export function workerOutcomeClaims(result) {
  const claim = (value, maxBytes) => {
    if (typeof value !== 'string' || !value.trim()) return 'UNAVAILABLE';
    const bounded = boundedDiagnosticText(value, maxBytes);
    const escaped = bounded.text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/[\\`*_[\]]/g, '\\$&');
    const rendered = boundedDiagnosticText(escaped, maxBytes);
    return rendered.text + (bounded.truncated || rendered.truncated ? ' [TRUNCATED]' : '');
  };
  const validations = Array.isArray(result?.validation) ? result.validation.slice(0, 64) : [];
  return [
    `Worker summary (claim): ${claim(result?.summary, 16 * 1024)}`,
    '',
    'Worker validation (claims; independent native checks remain required):',
    '',
    ...(validations.length ? validations.map(value => `- ${claim(value, 512)}`) : ['- UNAVAILABLE'])
  ].join('\n');
}

function diagnosticCode(diagnostic) {
  return safeCode(diagnostic?.classification?.code ?? diagnostic?.classification);
}

export function terminalOutcomeBody(e, { publishedHead, pr, terminalCode, diagnostic } = {}) {
  const d = diagnostic && typeof diagnostic === 'object' ? diagnostic : {};
  const head = exactSha(publishedHead) ? publishedHead : 'NONE PUBLISHED';
  const integrationBase = exactSha(pr?.base?.sha) ? pr.base.sha : 'UNAVAILABLE';
  const cause = safeCode(d.primaryCause);
  const next = safeAction(d.nextAction);
  const profile = e?.profile && typeof e.profile === 'object' ? e.profile : {};
  const warnings = admissionWarningSummary(e?.admission?.warnings ?? e?.warnings);
  const admissionStatus = e?.admissionBlock ? 'BLOCKED_BEFORE_WORKER' : warnings ? 'COMPLETED_WITH_WARNINGS' : 'COMPLETED';
  return [
    '## Codex Outcome',
    '',
    'Status: BLOCKED',
    `Token: ${blockedOutcomeToken(e)}`,
    `Thread: ${safeText(e?.thread)}`,
    `Correlation: ${safeText(threadCorrelationIdentity(e?.thread))}`,
    `Attempt: ${safeText(e?.attemptId)}`,
    `Requested model: ${safeText(profile.cliModelId)}; effort: ${safeText(profile.effort)}`,
    'Actual model/effort: UNAVAILABLE',
    `Historical reviewed/starting head: ${exactSha(e?.startHead) ? e.startHead : 'UNAVAILABLE'}`,
    `Durable/published head: ${head}`,
    `Observed integration base: ${integrationBase}`,
    `Terminal code: ${safeCode(terminalCode)}`,
    `Classification: ${diagnosticCode(d)}`,
    `Last successful boundary: ${safeBoundary(d.lastSuccessfulBoundary)}`,
    `Failure boundary: ${safeBoundary(d.failureBoundary)}`,
    `Cause summary: ${cause}`,
    ...(d.taskSummary ? [`Worker summary (claim): ${safeText(d.taskSummary)}`] : []),
    ...(d.blockerSummary ? [`Worker blocker (claim): ${safeText(d.blockerSummary)}`] : []),
    `Result class: ${d.orchestration === 'COMPLETED' ? 'DOMAIN_BLOCKED (task remains incomplete)' : 'ORCHESTRATION_FAILURE_OR_UNCONFIRMED'}`,
    `Next action: ${next}`,
    `Admission status: ${admissionStatus}`,
    ...(warnings ? [`Warning summary: ${warnings}`] : []),
    'Validation: automatic execution terminated without a successful terminal completion; no readiness, review, merge, or production action is implied.',
    'Independent reconciliation and review remain required.'
  ].join('\n');
}

export function safeOutcomePublication(error, status = 'failed') {
  if (status === 'published') return { status: 'published' };
  const code = safeCode(error?.code);
  return { status, code: code === 'UNAVAILABLE' ? 'OUTCOME_PUBLICATION_FAILED' : code };
}
