import { exactSha } from './execution-contract.mjs';
import { threadCorrelationIdentity } from './run-name.mjs';
import { normalizeCodexUsage } from './codex-usage.mjs';
import { boundedDiagnosticText, safeFailureDiagnosticReference, safeDiagnosticStoreReference, safeFallbackReference, safeLauncherDiagnosticSummary } from './diagnostics.mjs';
import { renderAuthorityRecord } from '../../contracts/src/github-authority.mjs';

const SAFE_CODE = /^[A-Z][A-Z0-9_]{0,79}$/;
const SAFE_BOUNDARY = /^[a-z][a-z0-9-]{0,39}$/;
const SAFE_ACTION = /^[a-z][a-z0-9-]{0,127}$/;
const SAFE_TEXT = /^[^\u0000-\u001f\u007f]{1,512}$/;

export function boundOutcomeBody(e, body, { pr, status = 'implemented', head, executionWarnings = [] } = {}) {
  if (!e.request || !e.requestReference) return body;
  const warningSources = [...(e.admission?.warnings ?? []).map(warning => warning.code), ...executionWarnings];
  const warnings = [...new Set(warningSources)].map(source => ({ source: `Attempt ${e.attemptId}: ${source}`,
    impact: source === 'UNCOMMITTED_WORK_REMAINS' ? 'Uncommitted checkout work requires reconciliation before acceptance.' : 'Admission selected a safe default; inspect the canonical authority before acceptance.',
    resolution: 'Unresolved at execution handoff.', next_action: 'Owner and independent reviewer must inspect and disposition this warning.', evidence_gaps: [] }));
  const record = { schema_version: '3.0', kind: 'outcome', repository: e.repository, task: e.issueNumber,
    parent: { kind: pr ? 'pull_request' : 'issue', number: pr?.number ?? e.issueNumber },
    charter_sha256: e.request.charter_sha256, request: e.requestReference, attempt: e.attemptId, status,
    result: { kind: exactSha(head) && head !== e.startHead ? 'git' : 'no-change',
      revision: exactSha(head) ? head : e.startHead, identities: [{ kind: 'github-actions-run', id: String(e.runId) }] },
    warnings, limitations: ['Native exact-head checks and independent acceptance remain separate.',
      'Execution and publication grant no deployment, credential, release, merge or Issue-closure authority.'],
    summary: status === 'implemented' ? 'The admitted execution completed; independent review remains required.' : 'The admitted execution stopped; useful durable work and its boundary are recorded above.' };
  return `${body}\n\nExecution request native ID: ${e.requestReference.id}\nExecution request digest: ${e.requestReference.sha256}\n\n${renderAuthorityRecord(record)}`;
}

// These are controller observations, separate from worker validation claims and
// admission defaults. Never infer that uncommitted bytes are disposable.
export function executionWarningSummary(warnings) {
  return Array.isArray(warnings) && warnings.includes('UNCOMMITTED_WORK_REMAINS')
    ? 'UNCOMMITTED_WORK_REMAINS: Uncommitted/non-ignored checkout residue was retained. The owner and independent reviewer must reconcile it with the worker claims and published diff before acceptance or another attempt; no cleanup, commit, publication or retry of that residue was performed.'
    : '';
}

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

export function usageOutcomeSummary(value) {
  const usage = normalizeCodexUsage(value);
  return [
    `Native token usage: source=${usage.source}; scope=${usage.scope}`,
    `Tokens: input=${usage.input_tokens}; cached input=${usage.cached_input_tokens}; cache write input=${usage.cache_write_input_tokens}; output=${usage.output_tokens}; reasoning output=${usage.reasoning_output_tokens}; total=${usage.total_tokens}`
  ].join('\n');
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
  const runtime = safeFailureDiagnosticReference(d.runtime) ?? {};
  const launcher = safeLauncherDiagnosticSummary(d.launcher) ?? {};
  const child = safeFailureDiagnosticReference({ childState: d.observed?.child, childExitCode: d.observed?.exitCode, signal: d.observed?.signal }) ?? {};
  const store = safeDiagnosticStoreReference(d.durable?.diagnosticStore);
  const fallback = safeFallbackReference(d.durable?.fallbackReference);
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
    usageOutcomeSummary(d.codexUsage),
    `Historical reviewed/starting head: ${exactSha(e?.startHead) ? e.startHead : 'UNAVAILABLE'}`,
    `Durable/published head: ${head}`,
    `Observed integration base: ${integrationBase}`,
    `Terminal code: ${safeCode(terminalCode)}`,
    `Classification: ${diagnosticCode(d)}`,
    `Last successful boundary: ${safeBoundary(d.lastSuccessfulBoundary)}`,
    `Failure boundary: ${safeBoundary(d.failureBoundary)}`,
    `Cause summary: ${cause}`,
    `Launcher diagnostic: ${safeCode(launcher.diagnosticCode)}; bytes: ${launcher.bytes ?? 'UNAVAILABLE'}; truncated: ${launcher.truncated === undefined ? 'UNAVAILABLE' : launcher.truncated}`,
    `Codex child: ${child.childState ?? 'unknown'}; exit code: ${child.childExitCode ?? 'UNAVAILABLE'}; signal: ${child.signal ?? 'UNAVAILABLE'}`,
    ...(runtime.operation ? [`Failed operation: ${runtime.operation}${runtime.syscall ? `; syscall: ${runtime.syscall}` : ''}${runtime.pathContext ? `; path context: ${runtime.pathContext}` : ''}`] : []),
    ...(runtime.cleanup || runtime.persistence || runtime.retention ? [`Runtime state: cleanup=${runtime.cleanup ?? 'unknown'}; diagnostics=${runtime.persistence ?? 'unknown'}; artifacts=${runtime.retention ?? 'unknown'}`] : []),
    ...(runtime.cleanupContainment ? [`Cleanup containment: ${runtime.cleanupContainment}`] : []),
    ...(store ? [`Primary diagnostics: ${store.status}; reference: ${store.executionId ?? 'UNAVAILABLE'}${store.storeCode ? `; store cause: ${store.storeCode}` : ''}`] : []),
    ...(fallback ? [`Fallback diagnostics: ${fallback.status}; reference: ${fallback.executionId ?? 'UNAVAILABLE'}${Number.isInteger(fallback.slot) ? `; slot: ${fallback.slot}` : ''}${fallback.code ? `; cause: ${fallback.code}` : ''}`] : []),
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
