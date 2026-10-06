import { safeModel, safeEffort } from '../../runtime/src/codex-profile.mjs';
import { safeBranch as safeConsumerBranch } from '../../consumer/consumer-config.mjs';
import { CONSUMER, CONSUMER_DIGEST } from '../../consumer/consumer.mjs';
import { createHash } from 'node:crypto';
import { safeDiagnosticStoreReference, safeFailureDiagnosticReference, safeFallbackReference, safeRuntimeLifecycle, safeLauncherDiagnosticSummary } from './diagnostics.mjs';
import { NATIVE_CR_VALIDATIONS } from '../../contracts/src/executable-cr.mjs';
import { normalizeCodexUsage } from './codex-usage.mjs';
import { validateAuthorityRecord } from '../../contracts/src/github-authority.mjs';

export const REPOSITORY = CONSUMER.repository;
export const OWNER = CONSUMER.owner;
export const WRITER = CONSUMER.writerApp.expectedActor;
export const REVIEWER = CONSUMER.reviewerApp.expectedActor;
export const BASE_BRANCH = CONSUMER.baseBranch;
export const VERSION = 2;
// Consumer-owned validationWorkflow implements declared names. These IDs are
// validation obligations, never executable shell or proof that a check passed.
export const NATIVE_VALIDATIONS = new Set(NATIVE_CR_VALIDATIONS);
// These are authority or semantic decisions that the controller can expose as
// a truthful BLOCKED domain result without pretending that a worker ran or
// that a protected boundary was crossed. Runtime/transport failures are not in
// this set and remain genuine automation failures.
export const NORMAL_DOMAIN_BLOCK_CODES = new Set([
  'SEMANTIC_RESULT_BLOCKED',
  'STEP_LABEL_MISSING', 'STEP_LABEL_MULTIPLE', 'STEP_LABEL_INVALID', 'STEP_LABEL_MISMATCH', 'STEP_DISPLAY_MISMATCH',
  'CHANGE_REQUEST_STEP_INVALID', 'CHANGE_REQUEST_STEP_MISMATCH', 'READY_EVENT_STALE', 'READY_LABEL_AMBIGUOUS',
  'READY_EVENT_ALREADY_CONSUMED', 'READY_EVENT_QUEUED', 'READY_CONSUMPTION_UNCERTAIN',
  'ISSUE_AUTHORITY_MISSING', 'ISSUE_AUTHORITY_INVALID', 'ISSUE_AUTHORITY_AMBIGUOUS',
  'ISSUE_STARTING_HEAD_REQUIRED', 'ISSUE_STARTING_HEAD_INVALID',
  'ISSUE_CONTINUATION_INVALID', 'TASK_BRANCH_MISSING',
  'ISSUE_NOT_ADMITTED', 'SUBAGENTS_PERMISSION_INVALID',
  'CURRENT_CHANGE_REQUEST_MISSING', 'CURRENT_TASK_AUTHORITY_MISSING', 'CURRENT_METADATA_MISSING',
  'CURRENT_VALIDATION_MISSING', 'REVIEW_BODY_INVALID', 'MALFORMED_CONTRACT', 'CONTRACT_COUNT_INVALID', 'CONTRACT_YAML_INVALID',
  'EXECUTABLE_CR_INVALID',
  'CONTRACT_NESTING', 'CONTRACT_DUPLICATE_KEY', 'CONTRACT_VALUE_AMBIGUOUS', 'CONTRACT_BINDING_INVALID',
  'CONTRACT_HEAD_MISMATCH', 'CONTRACT_SET_INVALID', 'CONTRACT_TEXT_INVALID', 'CONTRACT_PLACEHOLDER',
  'CONTRACT_DUPLICATE_VALUE', 'MODEL_PROFILE_INVALID', 'PR_NOT_ADMITTED', 'PR_AMBIGUOUS', 'CANONICAL_ISSUE_AMBIGUOUS',
  'STARTING_STATE_MISMATCH', 'TASK_BRANCH_ALREADY_EXISTS', 'INTEGRATION_CONFLICT', 'INTEGRATION_BASE_INVALID',
  'AUTHORITY_CHANGED', 'PR_AUTHORITY_CHANGED', 'REMOTE_HEAD_CHANGED', 'PR_HEAD_OBSERVATION_STALE',
  'COMMIT_PATH_INVALID', 'COMMIT_OWNERSHIP_INVALID', 'COMMIT_FILE_MODE_INVALID', 'SECRET_PUBLICATION_SCAN_FAILED',
  'BRANCH_INVALID', 'ISSUE_PROFILE_INVALID', 'ISSUE_BRANCH_INVALID', 'ISSUE_CLOSURE_POLICY_INVALID', 'TARGET_BASE_INVALID',
  'LAUNCH_STEP_INVALID', 'LAUNCH_TASK_INVALID', 'LAUNCH_PR_INVALID', 'LAUNCH_METADATA_TOO_LONG',
  'CHECKOUT_ALREADY_EXISTS', 'CHECKOUT_DIRTY', 'CHECKOUT_UNPUBLISHED', 'CANONICAL_BRANCH_MISSING',
  'REQUIRED_VALIDATION_UNSUPPORTED', 'NO_DURABLE_PROGRESS',
  'AUTHORITY_MODEL_INVALID', 'AUTHORITY_CHARTER_INVALID', 'AUTHORITY_RECORD_INVALID', 'AUTHORITY_TARGET_MISMATCH',
  'AUTHORITY_PARENT_MISMATCH', 'AUTHORITY_STARTING_STATE_INVALID', 'AUTHORITY_CR_BINDING_INVALID',
  'AUTHORITY_VALIDATION_UNKNOWN', 'AUTHORITY_REFERENCE_DUPLICATE', 'AUTHORITY_RESULT_INVALID',
  'AUTHORITY_MIGRATION_REQUIRED', 'AUTHORITY_CHARTER_MISMATCH', 'AUTHORITY_CLOSURE_MISMATCH',
  'AUTHORITY_BODY_INVALID', 'AUTHORITY_BLOCK_AMBIGUOUS', 'AUTHORITY_JSON_INVALID', 'AUTHORITY_JSON_NONCANONICAL',
  'AUTHORITY_RECORDS_INVALID', 'AUTHORITY_NATIVE_RECORD_INVALID', 'AUTHORITY_NATIVE_RECORD_DUPLICATE',
  'AUTHORITY_SOURCE_MISMATCH', 'AUTHORITY_NATIVE_PARENT_MISMATCH', 'AUTHORITY_NATIVE_KIND_MISMATCH',
  'AUTHORITY_DECISION_UNTRUSTED', 'AUTHORITY_DECISION_MISMATCH', 'AUTHORITY_DECISION_SUPERSESSION_INVALID',
  'AUTHORITY_DECISION_NOT_NORMALIZED', 'AUTHORITY_DECISION_EMPTY', 'AUTHORITY_DECISION_SCOPE_MISMATCH',
  'AUTHORITY_DECISION_SUPERSEDED', 'AUTHORITY_WARNING_DUPLICATE', 'AUTHORITY_FINDING_DUPLICATE',
  'AUTHORITY_CONTEXT_TOO_LARGE', 'AUTHORITY_TRUST_BINDING_INVALID',
  'AUTHORITY_REQUEST_MISSING', 'AUTHORITY_SUPERSESSION_INVALID', 'AUTHORITY_SUPERSESSION_AMBIGUOUS',
  'AUTHORITY_STEP_INVALID', 'AUTHORITY_STEP_MISMATCH', 'AUTHORITY_REQUEST_TARGET_MISMATCH',
  'AUTHORITY_SOURCE_TARGET_MISMATCH', 'AUTHORITY_ROUTE_MISMATCH', 'AUTHORITY_REQUEST_SUPERSEDED',
  'AUTHORITY_CONTINUATION_INVALID', 'AUTHORITY_TITLE_PROJECTION_MISMATCH'
]);
export const isNormalDomainBlock = value => NORMAL_DOMAIN_BLOCK_CODES.has(typeof value === 'string' ? value : value?.code);
export const isAdmissionDomainBlock = value => {
  const code = typeof value === 'string' ? value : value?.code;
  return code !== 'SEMANTIC_RESULT_BLOCKED' && NORMAL_DOMAIN_BLOCK_CODES.has(code);
};

// Red-exit audit: admission/authority decisions are domain blockers before
// execution. After execution, classification additionally requires containment,
// complete collection and durable publication (or proven absence of progress).
// Worker semantic/format/nonzero results can be incomplete without breaking
// orchestration. Transport, helper/launcher, journal, object-import, credential,
// ambiguous mutation and unknown internal failures remain exceptional. Never
// classify by Error.name, message text, or a worker-supplied success flag alone.
const WORKER_DOMAIN_CODES = new Set(['CODEX_JSON_INVALID', 'CODEX_RESULT_MISSING', 'CODEX_RESULT_INVALID',
  'CODEX_NONZERO_EXIT', 'CODEX_OUTPUT_TOO_LARGE', 'CODEX_RUNTIME_TIMEOUT']);
export function safeDomainTerminal(error, record, stage) {
  const execution = record.execution;
  const lifecycle = safeRuntimeLifecycle(execution?.diagnostic?.runtime ?? error?.details?.failureDiagnostic ?? error?.details);
  if (lifecycle.persistence === 'failed' || ['failed', 'retained'].includes(lifecycle.cleanup)) return false;
  const domain = isNormalDomainBlock(error)
    || (stage === 'execution' && execution?.child === 'started' && WORKER_DOMAIN_CODES.has(error?.code));
  if (!domain) return false;
  if (!execution) return stage === 'preflight';
  if (execution.reserved !== true || execution.returned !== true || !['started', 'not_started'].includes(execution.child)
    || (execution.containment !== 'reaped' && !(execution.child === 'not_started' && execution.containment === 'not_required'))) return false;
  const collected = record.collection;
  return collected?.clean === true && exactSha(collected.head)
    && (collected.head === record.envelope.startHead || record.progress?.head === collected.head);
}
export const fail = code => { throw Object.assign(new Error(code), { code }); };
export const digest = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');
export const exactSha = value => typeof value === 'string' && /^[a-f0-9]{40}$/.test(value);
export const positive = value => Number.isSafeInteger(value) && value > 0;
export function branchName(value) {
  if (typeof value !== 'string' || !safeConsumerBranch(value) || !value.startsWith(CONSUMER.taskBranchPrefix)
    || value.includes('..') || value.includes('//') || value.endsWith('/') || value.endsWith('.lock')) fail('BRANCH_INVALID');
  return value;
}
export function safePath(value) {
  return typeof value === 'string' && value.length > 0 && value.length < 512
    && !/[\\\x00-\x1f\x7f:]/.test(value) && !value.startsWith('/')
    && !value.split('/').some(p => p === '' || p === '.' || p === '..' || p.toLowerCase() === '.git');
}
export function validateEnvelope(e) {
  // New dispatches are keyed by native run ID. Keep the former event envelope
  // readable for terminal replay and the separately authorized non-routing
  // smoke; neither path invents Step metadata for a new automatic admission.
  const nativeDispatch = e && positive(e.step) && e.attemptId === `run-${e.runId}`;
  const legacyEvent = e && positive(e.eventId) && e.attemptId === `event-${e.eventId}`;
  const manualNoSource = e?.route === 'manual' && e?.request?.kind === 'task-request'
    && e.branch === null && e.startHead === null && e.historicalBase === null;
  if (!e || e.version !== VERSION || e.repository !== REPOSITORY || e.consumerDigest !== CONSUMER_DIGEST
    || !safeModel(e.profile?.cliModelId) || !safeEffort(e.profile?.effort)
    || !positive(e.runId) || (!nativeDispatch && !legacyEvent)
    || !['issue', 'pull_request'].includes(e.target) || !positive(e.number) || !positive(e.issueNumber)
    || !['auto', 'manual'].includes(e.route) || (!manualNoSource && (!exactSha(e.startHead) || !exactSha(e.historicalBase)))
    || !exactSha(e.targetBase) || typeof e.authorityDigest !== 'string'
    || !/^[a-f0-9]{64}$/.test(e.authorityDigest)) fail('EXECUTION_ENVELOPE_INVALID');
  if (!manualNoSource) branchName(e.branch);
  if (e.request) {
    validateAuthorityRecord(e.request, { repository: REPOSITORY, task: e.issueNumber, validationNames: [...NATIVE_VALIDATIONS] });
    if (e.request.step !== e.step || e.request.route !== e.route || e.request.branch !== e.branch
      || e.request.starting_head !== e.startHead || e.request.base_sha !== e.historicalBase
      || e.request.model !== e.profile.cliModelId || e.request.effort !== e.profile.effort
      || e.request.subagents !== e.subagentsAllowed || !e.requestReference
      || !/^[a-f0-9]{64}$/.test(e.requestReference.sha256 ?? '')) fail('EXECUTION_ENVELOPE_INVALID');
  }
  if (e.continuation && (e.target !== 'issue' || !exactSha(e.continuation.head) || e.continuation.head !== e.startHead
    || (e.continuation.pullRequest !== null && !positive(e.continuation.pullRequest)))) fail('EXECUTION_ENVELOPE_INVALID');
  if (nativeDispatch && typeof e.subagentsAllowed !== 'boolean') fail('SUBAGENTS_PERMISSION_INVALID');
  if (!Array.isArray(e.validation) || !e.validation.length || e.validation.some(name => !NATIVE_VALIDATIONS.has(name))) fail('REQUIRED_VALIDATION_UNSUPPORTED');
  return e;
}

// One bounded, safe causal summary. Absence is never an observation of non-execution.
export function causalEvidence(error, { child = 'unknown', containment = 'unknown', publishedHead = null, stage = 'execution' } = {}) {
  const detail = error?.details ?? {};
  const inherited = detail.causal ?? {};
  const diagnostic = detail.failureDiagnostic ?? detail;
  const safeDiagnostic = { ...safeFailureDiagnosticReference(detail), ...safeFailureDiagnosticReference(diagnostic),
    // Parent finalization happens after the worker diagnostic was emitted.
    // Preserve its latest lifecycle observations alongside the original cause.
    ...safeRuntimeLifecycle(detail) };
  const inheritedPublication = safeFailureDiagnosticReference(inherited.publication) ?? {};
  const inheritedRuntime = safeFailureDiagnosticReference(inherited.runtime) ?? {};
  const launcher = { ...safeLauncherDiagnosticSummary(inherited.launcher), ...safeLauncherDiagnosticSummary(safeDiagnostic) };
  const observed = safeDiagnostic.childState ?? inherited.observed?.child ?? (typeof safeDiagnostic.childStarted === 'boolean' ? (safeDiagnostic.childStarted ? 'started' : 'not_started') : child);
  const code = /^[A-Z][A-Z0-9_]{0,79}$/.test(error?.code ?? '') ? error.code : 'UNCLASSIFIED_FAILURE';
  const parserFailure = ['CODEX_JSON_INVALID', 'CODEX_RESULT_INVALID', 'CODEX_RESULT_MISSING'].includes(code);
  const cause = safeDiagnostic.primaryCause ?? inherited.primaryCause;
  const primary = parserFailure ? code : /^[A-Z][A-Z0-9_]{0,79}$/.test(cause ?? '') ? cause : null;
  const boundary = value => /^[a-z][a-z-]{0,39}$/.test(value ?? '') ? value : null;
  const executionId = detail.executionId ?? safeDiagnostic.executionId ?? inherited.executionId;
  const exitCode = safeDiagnostic.childExitCode ?? inherited.observed?.exitCode;
  const operation = safeDiagnostic.operation ?? inheritedPublication.operation;
  const priorCause = safeDiagnostic.priorCause ?? inheritedPublication.priorCause;
  const gitExitCode = safeDiagnostic.gitExitCode ?? inheritedPublication.gitExitCode;
  const gitDiagnostic = safeDiagnostic.gitExitCode !== undefined || safeDiagnostic.classification?.startsWith('GIT_') === true;
  const childDiagnostic = safeDiagnostic.diagnosticCode !== undefined || safeDiagnostic.childExitCode !== undefined;
  const signal = (!gitDiagnostic && childDiagnostic ? safeDiagnostic.signal : undefined) ?? inherited.observed?.signal;
  const publicationSignal = (gitDiagnostic ? safeDiagnostic.signal : undefined) ?? inheritedPublication.signal;
  const runtime = {
    ...inheritedRuntime,
    ...(safeDiagnostic.syscall ? { syscall: safeDiagnostic.syscall } : {}),
    ...(safeDiagnostic.pathContext ? { pathContext: safeDiagnostic.pathContext } : {}),
    ...safeRuntimeLifecycle(safeDiagnostic)
  };
  if (Object.keys(runtime).length && safeDiagnostic.operation) runtime.operation = safeDiagnostic.operation;
  const publication = {
    ...(operation ? { operation } : {}),
    ...(priorCause ? { priorCause } : {}),
    ...(gitExitCode !== undefined ? { gitExitCode } : {}),
    ...(publicationSignal ? { signal: publicationSignal } : {})
  };
  return {
    codexUsage: normalizeCodexUsage(detail.codexUsage ?? inherited.codexUsage),
    observed: { child: ['started', 'not_started', 'unknown'].includes(observed) ? observed : 'unknown',
      exitCode: Number.isInteger(exitCode) && exitCode >= 0 && exitCode <= 255 ? exitCode : null,
      ...(/^SIG[A-Z0-9]{1,29}$/.test(signal ?? '') ? { signal } : {}) },
    executionState: observed === 'started' ? 'confirmed' : observed === 'not_started' ? 'known-not-executed' : 'uncertain',
    executionId: /^[A-Za-z0-9_-]{1,128}$/.test(executionId ?? '') ? executionId : null,
    lastSuccessfulBoundary: boundary(detail.lastSuccessfulBoundary ?? inherited.lastSuccessfulBoundary),
    failureBoundary: parserFailure ? 'result-parse' : boundary(safeDiagnostic.boundary ?? inherited.failureBoundary ?? stage),
    classification: { code, source: primary ? 'observed' : 'fallback', stage },
    primaryCause: primary,
    containment: ['reaped', 'not_required', 'unknown'].includes(containment) ? containment : 'unknown',
    terminal: 'blocked', durable: { publishedHead: exactSha(publishedHead) ? publishedHead : null,
      diagnosticStore: safeDiagnosticStoreReference(detail.diagnosticStore ?? diagnostic.diagnosticStore ?? inherited.durable?.diagnosticStore) ?? null,
      ...(safeFallbackReference(detail.fallbackReference ?? diagnostic.fallbackReference ?? inherited.durable?.fallbackReference)
        ? { fallbackReference: safeFallbackReference(detail.fallbackReference ?? diagnostic.fallbackReference ?? inherited.durable?.fallbackReference) } : {}) },
    ...(Object.keys(runtime).length > 0 ? { runtime } : {}),
    ...(Object.keys(launcher).length > 0 ? { launcher } : {}),
    ...(Object.keys(publication).length > 0 ? { publication } : {}),
    nextAction: publishedHead ? 'reconcile-published-progress-before-new-owner-attempt' : observed === 'not_started' ? 'correct-cause-before-new-owner-attempt' : 'inspect-attempt-before-new-owner-attempt'
  };
}
