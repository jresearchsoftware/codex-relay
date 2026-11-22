import { exactSha, fail } from './execution-contract.mjs';
import { threadCorrelationIdentity } from './run-name.mjs';
import { normalizeCodexUsage } from './codex-usage.mjs';
import { boundedDiagnosticText, safeFailureDiagnosticReference, safeDiagnosticStoreReference, safeFallbackReference, safeLauncherDiagnosticSummary } from './diagnostics.mjs';
import { admissionBinding, renderAuthorityRecord } from '../../contracts/src/github-authority.mjs';
import { safePublicationText } from '../../contracts/src/publication-rendering.mjs';
import { redactDiagnosticText } from './diagnostic-redaction.mjs';

const SAFE_CODE = /^[A-Z][A-Z0-9_]{0,79}$/;
const SAFE_BOUNDARY = /^[a-z][a-z0-9-]{0,39}$/;
const SAFE_ACTION = /^[a-z][a-z0-9-]{0,127}$/;
const SAFE_TEXT = /^[^\u0000-\u001f\u007f]{1,512}$/;
const OUTCOME_BYTES = 60 * 1024;
const SUMMARY_BYTES = 48 * 1024;
const CLAIMS_LIMITATION = 'Worker claims were shortened for publication. Use the published result and primary evidence for review.';
const CLAIMS_OMITTED = 'Publication warning: Worker summary and validation claims omitted to fit the Outcome.';

export function boundOutcomeBody(e, body, { pr, status = 'implemented', head, executionWarnings = [], authorityDrift, shortenedClaims } = {}) {
  if (!e.request || !e.requestReference) return body;
  const warningSources = [...(e.admission?.warnings ?? []).map(warning => warning.code), ...executionWarnings];
  const warnings = [...new Set(warningSources)].map(source => ({ source: `Attempt ${e.attemptId}: ${source}`,
    impact: executionWarningSummary([source]) || 'Admission selected a safe default; inspect the canonical authority before acceptance.',
    resolution: 'Unresolved at execution handoff.', next_action: 'Owner and independent reviewer must inspect and disposition this warning.', evidence_gaps: [] }));
  const record = { schema_version: '4.0', kind: 'outcome', repository: e.repository, task: e.issueNumber,
    parent: { kind: pr ? 'pull_request' : 'issue', number: pr?.number ?? e.issueNumber },
    charter_sha256: e.request.charter_sha256,
    authority: e.request.authority, admission: admissionBinding(e.request), step: e.step,
      ...(e.request.authority_resolution ? { authority_resolution: e.request.authority_resolution } : {}),
      ...(authorityDrift && authorityDrift.current_authority.sha256 !== e.request.authority.sha256
        ? { authority_drift: authorityDrift } : {}), attempt: e.attemptId, status,
    result: { kind: exactSha(head) && head !== e.startHead ? 'git' : 'no-change',
      revision: exactSha(head) ? head : e.startHead, identities: [{ kind: 'github-actions-run', id: String(e.runId) }] },
    warnings, limitations: ['Native exact-head checks and independent acceptance remain separate.',
      'Execution and publication grant no deployment, credential, release, merge or Issue-closure authority.',
      ...(shortenedClaims ? [CLAIMS_LIMITATION] : [])],
    summary: status === 'implemented' ? 'The admitted execution completed; independent review remains required.' : 'The admitted execution stopped; useful durable work and its boundary are recorded above.' };
  const source = `Authority source native ID: ${e.requestReference.id}\nAuthority digest: ${e.request.authority.sha256}\nAdmission digest: ${record.admission.sha256}`;
  return `${body}\n\n${e.executionSlot ? `Execution slot: ${e.executionSlot}\n\n` : ''}${source}\n\n${renderAuthorityRecord(record)}`;
}

// These are controller observations, separate from worker validation claims and
// admission defaults. Never infer that uncommitted bytes are disposable.
export function executionWarningSummary(warnings) {
  const descriptions = {
    PRIOR_OUTCOME_CONTEXT_TRUNCATED: 'Prior Writer Outcome context was clipped; its exact native source remains the complete evidence. Clipping grants no new authority.',
    PRIOR_OUTCOME_CONTEXT_UNAVAILABLE: 'The exact prior Writer Outcome could not be verified as continuation context; no prior result or external effect was inferred.',
    PRESENTATION_REPAIR_UNAVAILABLE: 'The native result binding is verified, but derived PR title/Step presentation could not be repaired. Inspect and correct the display without changing admitted identity.',
    UNCOMMITTED_WORK_REMAINS: 'Uncommitted checkout work requires reconciliation before acceptance. Uncommitted/non-ignored checkout residue was retained; the owner and independent reviewer must reconcile it before acceptance or another attempt.',
    WORKTREE_OBSERVATION_INCOMPLETE: 'The committed candidate was safely collected, but checkout residue could not be completely observed. Retain local work and inspect the collection diagnostic; no clean-checkout claim is made.',
    RUNTIME_CLEANUP_FAILED: 'The contained execution returned its result, but sandbox cleanup failed. Artifacts and durable diagnostics remain retained; inspect the affected resource before reuse.'
  };
  return (Array.isArray(warnings) ? warnings : []).filter(code => descriptions[code])
    .map(code => `${code}: ${descriptions[code]}`).join(' ');
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

function publicationClaim(value, maxBytes, secrets) {
  const redacted = typeof value === 'string' && value.trim()
    ? redactDiagnosticText(redactDiagnosticText(value, secrets), secrets) : 'UNAVAILABLE';
  const escaped = safePublicationText(redacted);
  if (Buffer.byteLength(escaped) <= maxBytes) return { text: escaped, shortened: false };
  let text = '';
  let bytes = 0;
  // Keep each original code point and its Markdown escape/entity together.
  for (const character of redacted) {
    const part = safePublicationText(character);
    bytes += Buffer.byteLength(part);
    if (bytes > maxBytes) break;
    text += part;
  }
  return { text, shortened: true };
}

export function workerOutcomeClaims(result, { maxBytes = OUTCOME_BYTES, summaryBytes = SUMMARY_BYTES, secrets } = {}) {
  const summaryLabel = 'Worker summary (claim): ';
  const summaryNotice = '\n\nPublication warning: Worker summary shortened to fit the Outcome. The complete summary is not included.';
  const validationHeading = '\n\nWorker validation (claims; independent native checks remain required):\n';
  const validationNotice = '\n- Additional worker validation claims omitted to fit the Outcome.';
  const claimSuffix = ' [TRUNCATED]';
  const overhead = Buffer.byteLength(summaryLabel + summaryNotice + validationHeading + validationNotice + '\n- UNAVAILABLE');
  const summary = publicationClaim(result?.summary, Math.min(summaryBytes, Math.max(0, maxBytes - overhead)), secrets);
  const validations = Array.isArray(result?.validation) ? result.validation.slice(0, 64) : [];
  let text = summaryLabel + summary.text + (summary.shortened ? summaryNotice : '') + validationHeading;
  let available = maxBytes - Buffer.byteLength(text + validationNotice);
  let shortened = summary.shortened;
  for (const value of validations.length ? validations : ['UNAVAILABLE']) {
    let claim = publicationClaim(value, 512, secrets);
    if (claim.shortened) claim = publicationClaim(value, 512 - claimSuffix.length, secrets);
    const line = `\n- ${claim.text}${claim.shortened ? claimSuffix : ''}`;
    const bytes = Buffer.byteLength(line);
    if (bytes > available) return { text: text + validationNotice, shortened: true };
    text += line;
    available -= bytes;
    shortened ||= claim.shortened;
  }
  return { text, shortened };
}

export function automaticOutcomeBody(e, before, after, { taskResult, secrets, summaryBytes, markerKey = 'outcome', ...binding } = {}) {
  // Leave room for the native attempt marker and a later PR readiness refresh.
  const limit = OUTCOME_BYTES - Buffer.byteLength(`\n\n<!-- relay:${e.attemptId}:${markerKey} -->`) - (binding.pr ? 128 : 0);
  let suffix = boundOutcomeBody(e, after, binding);
  const claimsBudget = () => limit - Buffer.byteLength(before + suffix);
  let claims = taskResult ? workerOutcomeClaims(taskResult, { maxBytes: claimsBudget(), summaryBytes, secrets }) : { text: '' };
  if (claims.shortened) {
    suffix = boundOutcomeBody(e, after, { ...binding, shortenedClaims: true });
    claims = workerOutcomeClaims(taskResult, { maxBytes: claimsBudget(), summaryBytes, secrets });
  }
  const body = before + (Buffer.byteLength(claims.text) <= claimsBudget() ? claims.text : CLAIMS_OMITTED) + suffix;
  if (Buffer.byteLength(body) > limit) fail('OUTCOME_BODY_BUDGET_EXCEEDED');
  return body;
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

export function terminalOutcomeBody(e, { publishedHead, pr, terminalCode, diagnostic, executionWarnings = [], authorityDrift, secrets } = {}) {
  const d = diagnostic && typeof diagnostic === 'object' ? diagnostic : {};
  const head = exactSha(publishedHead) ? publishedHead : 'NONE PUBLISHED';
  const integrationBase = exactSha(pr?.base?.sha) ? pr.base.sha : 'UNAVAILABLE';
  const cause = safeCode(d.primaryCause);
  const next = safeAction(d.nextAction);
  const profile = e?.profile && typeof e.profile === 'object' ? e.profile : {};
  const warnings = [admissionWarningSummary(e?.admission?.warnings ?? e?.warnings),
    executionWarningSummary(executionWarnings)].filter(Boolean).join('; ');
  const admissionStatus = e?.admissionBlock ? 'BLOCKED_BEFORE_WORKER' : warnings ? 'COMPLETED_WITH_WARNINGS' : 'COMPLETED';
  const runtime = safeFailureDiagnosticReference(d.runtime) ?? {};
  const launcher = safeLauncherDiagnosticSummary(d.launcher) ?? {};
  const child = safeFailureDiagnosticReference({ childState: d.observed?.child, childExitCode: d.observed?.exitCode, signal: d.observed?.signal }) ?? {};
  const store = safeDiagnosticStoreReference(d.durable?.diagnosticStore);
  const fallback = safeFallbackReference(d.durable?.fallbackReference);
  const before = [
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
    ...(d.admissionSummary ? [`Admission diagnostic: ${safeText(d.admissionSummary)}`] : []),
    `Classification: ${diagnosticCode(d)}`,
    `Last successful boundary: ${safeBoundary(d.lastSuccessfulBoundary)}`,
    `Failure boundary: ${safeBoundary(d.failureBoundary)}`,
    `Cause summary: ${cause}`,
    `Launcher diagnostic: ${safeCode(launcher.diagnosticCode)}; bytes: ${launcher.bytes ?? 'UNAVAILABLE'}; truncated: ${launcher.truncated === undefined ? 'UNAVAILABLE' : launcher.truncated}`,
    `Codex child: ${child.childState ?? 'unknown'}; exit code: ${child.childExitCode ?? 'UNAVAILABLE'}; signal: ${child.signal ?? 'UNAVAILABLE'}`,
    ...(runtime.operation ? [`Failed operation: ${runtime.operation}${runtime.syscall ? `; syscall: ${runtime.syscall}` : ''}${runtime.pathContext ? `; path context: ${runtime.pathContext}` : ''}${runtime.diagnosticCode ? `; OS code: ${runtime.diagnosticCode}` : ''}`] : []),
    ...(runtime.cleanup || runtime.persistence || runtime.retention ? [`Runtime state: cleanup=${runtime.cleanup ?? 'unknown'}; diagnostics=${runtime.persistence ?? 'unknown'}; artifacts=${runtime.retention ?? 'unknown'}`] : []),
    ...(runtime.cleanupContainment ? [`Cleanup containment: ${runtime.cleanupContainment}`] : []),
    ...(store ? [`Primary diagnostics: ${store.status}; reference: ${store.executionId ?? 'UNAVAILABLE'}${store.storeCode ? `; store cause: ${store.storeCode}` : ''}`] : []),
    ...(fallback ? [`Fallback diagnostics: ${fallback.status}; reference: ${fallback.executionId ?? 'UNAVAILABLE'}${Number.isInteger(fallback.slot) ? `; slot: ${fallback.slot}` : ''}${fallback.code ? `; cause: ${fallback.code}` : ''}`] : []),
  ];
  const after = [
    ...(d.blockerSummary ? [`Worker blocker (claim): ${publicationClaim(d.blockerSummary, 16 * 1024, secrets).text}`] : []),
    `Result class: ${d.orchestration === 'COMPLETED' ? 'DOMAIN_BLOCKED (task remains incomplete)' : 'ORCHESTRATION_FAILURE_OR_UNCONFIRMED'}`,
    `Next action: ${next}`,
    `Admission status: ${admissionStatus}`,
    ...(warnings ? [`Warning summary: ${warnings}`] : []),
    'Validation: automatic execution terminated without a successful terminal completion; no readiness, review, merge, or production action is implied.',
    'Independent reconciliation and review remain required.'
  ];
  const taskResult = d.taskSummary || d.validation ? { summary: d.taskSummary, validation: d.validation } : undefined;
  return automaticOutcomeBody(e, before.join('\n') + '\n', (taskResult ? '\n' : '') + after.join('\n'),
    { taskResult, summaryBytes: 16 * 1024, pr, status: 'blocked', head: publishedHead, executionWarnings, authorityDrift, secrets });
}

export function safeOutcomePublication(error, status = 'failed') {
  if (status === 'published') return { status: 'published' };
  const code = safeCode(error?.code);
  return { status, code: code === 'UNAVAILABLE' ? 'OUTCOME_PUBLICATION_FAILED' : code };
}
