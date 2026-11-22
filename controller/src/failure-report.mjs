// Public diagnostic facts are categorical. Response bodies, request paths,
// exception text, and configuration values stay in the protected evidence.
const endpoints = [
  [/^\/issues\/(?:[1-9]\d*\/comments|comments\/)/, 'Issue comments'],
  [/^\/issues\/[1-9]\d*\/events/, 'Issue events'],
  [/^\/issues\/[1-9]\d*\/labels/, 'Issue labels'],
  [/^\/issues(?:\/|$)/, 'Issues'],
  [/^\/pulls\/[1-9]\d*\/reviews/, 'pull request reviews'],
  [/^\/pulls(?:\/|$)/, 'pull requests'],
  [/^\/labels(?:\/|$)/, 'repository labels'],
  [/^\/actions\/runs\//, 'Actions runs'],
  [/^\/actions\/workflows\//, 'Actions workflow runs'],
  [/^\/git\/(?:matching-refs|ref)\//, 'Git refs'],
  [/^\/git\/commits\//, 'Git commits'],
  [/^\/compare\//, 'Git comparison'],
  [/^\/users?\b/, 'account identity'],
  [/^\/graphql$/, 'pull request GraphQL'],
  [/^\/app\/installations\/[1-9]\d*\/access_tokens$/, 'Writer installation token']
];
const endpointNames = new Set(['repository API', ...endpoints.map(([, name]) => name)]);
export function githubEndpoint(path) {
  return endpoints.find(([pattern]) => pattern.test(path.split('?')[0]))?.[1] ?? 'repository API';
}

export const networkCode = value => [
  'EAI_AGAIN', 'ECONNRESET', 'ECONNREFUSED', 'ETIMEDOUT', 'EPIPE', 'ENETDOWN', 'ENETUNREACH',
  'EHOSTUNREACH', 'UND_ERR_CONNECT_TIMEOUT', 'UND_ERR_HEADERS_TIMEOUT', 'UND_ERR_BODY_TIMEOUT', 'UND_ERR_SOCKET',
  'ENOTFOUND', 'CERT_HAS_EXPIRED', 'UNABLE_TO_VERIFY_LEAF_SIGNATURE', 'SELF_SIGNED_CERT_IN_CHAIN'
].includes(value) ? value : undefined;

export function safeGithubFailure(value) {
  if (!value || !['GET', 'POST', 'PATCH', 'DELETE', 'PUT'].includes(value.method)
    || !endpointNames.has(value.endpoint)
    || !['http', 'timeout', 'network', 'transport-unknown', 'invalid-response', 'graphql-error', 'rate-limit', 'cancelled'].includes(value.reason)
    || !['non-transient', 'attempt-limit', 'deadline', 'provider-delay', 'mutation', 'cancelled'].includes(value.stopped)
    || !Number.isInteger(value.attempts) || value.attempts < 0 || value.attempts > (value.method === 'GET' ? 3 : 1)) return undefined;
  const { method, endpoint, reason, stopped, attempts } = value;
  const status = Number.isInteger(value.status) && value.status >= 100 && value.status <= 599 ? value.status : undefined;
  const osCode = networkCode(value.osCode);
  const readback = ['not-observed', 'unavailable'].includes(value.readback) ? value.readback : undefined;
  return { method, endpoint, reason, stopped, attempts, ...(status ? { status } : {}), ...(osCode ? { osCode } : {}), ...(readback ? { readback } : {}) };
}

const runStatuses = ['requested', 'queued', 'pending', 'waiting', 'in_progress', 'completed'];
export function safeFailurePredicate(value) {
  if (value?.check === 'status' && value.expected === 'in_progress') {
    const observed = runStatuses.includes(value.observed) ? value.observed
      : ['missing', 'unrecognized'].includes(value.observed) ? value.observed : value.observed == null ? 'missing' : 'unrecognized';
    return { check: 'status', expected: 'in_progress', observed };
  }
  if (['run_id', 'run_attempt', 'subject_number'].includes(value?.check) && Number.isSafeInteger(value.expected) && value.expected > 0) {
    return { check: value.check, expected: value.expected,
      observed: Number.isSafeInteger(value.observed) && value.observed > 0 ? value.observed : value.observed == null ? 'missing' : 'unrecognized' };
  }
  if (['pr.starting-head', 'task-branch-head'].includes(value?.check) && typeof value.expected === 'string' && /^[a-f0-9]{40}$/.test(value.expected)) {
    const observed = Array.isArray(value.observed) && value.observed.length === 1 ? value.observed[0] : value.observed;
    return { check: value.check, expected: value.expected, observed: /^[a-f0-9]{40}$/.test(observed ?? '') ? observed : 'unavailable' };
  }
  const categories = {
    event: ['workflow_dispatch', 'issues', 'pull_request_target'],
    'inputs.route': ['auto', 'manual'], 'event.action': ['labeled', 'unlabeled', 'opened', 'closed', 'edited', 'reopened'],
    'event.label': ['codex-ready-auto', 'codex-ready-manual'], 'event.name': ['workflow_dispatch', 'issues', 'pull_request_target'],
    'event.subject.kind': ['issue', 'pull_request'], 'issue.kind': ['issue', 'pull_request'],
    'issue.state': ['open', 'closed'], 'pr.state': ['open', 'closed']
  };
  const values = Object.hasOwn(categories, value?.check ?? '') ? categories[value.check] : null;
  if (values) {
    const expected = Array.isArray(value.expected) ? value.expected.join(' or ') : value.expected;
    const allowed = [...values, values.join(' or '), 'issues or pull_request_target', 'auto or manual'];
    if (!allowed.includes(expected)) return undefined;
    return { check: value.check, expected,
      observed: values.includes(value.observed) ? value.observed
        : value.observed == null || value.observed === 'missing' ? 'missing' : 'unrecognized' };
  }
  return undefined;
}

const writerOperations = ['admit', 'preflight', 'collect-progress', 'publish-progress', 'finish', 'finish-no-change',
  'terminal-outcome', 'complete-handoff', 'complete-execution', 'handoff', 'observe-readiness', 'publication-state',
  'prepublication-state', 'recover-publication', 'recover-prepublication', 'predispatch-state', 'predispatch-authorization',
  'finalize-predispatch', 'begin-remediation', 'manual-outcome-direct'];
const signals = ['SIGTERM', 'SIGKILL', 'SIGINT', 'SIGABRT', 'SIGHUP', 'SIGPIPE', 'SIGSEGV'];
export function safeWriterFailure(value) {
  if (!writerOperations.includes(value?.operation)) return undefined;
  const exit = Number.isInteger(value.exit) && value.exit >= 0 && value.exit <= 255 ? value.exit : undefined;
  const signal = signals.includes(value.signal) ? value.signal : undefined;
  const osCode = ['ENOENT', 'EACCES', 'EPERM', 'EIO', 'EPIPE', 'EMFILE', 'ENOMEM'].includes(value.osCode) ? value.osCode : undefined;
  return { operation: value.operation, ...(exit !== undefined ? { exit } : {}), ...(signal ? { signal } : {}), ...(osCode ? { osCode } : {}) };
}

export function safeFailureFacts(value) {
  const githubFailure = safeGithubFailure(value?.githubFailure);
  const predicate = safeFailurePredicate(value?.predicate);
  const writerFailure = safeWriterFailure(value?.writerFailure);
  const admission = value?.admissionEffect;
  const admissionEffect = Number.isSafeInteger(admission?.step) && admission.step > 0
    && ['unknown', 'projected'].includes(admission.projection) && ['not-attempted', 'uncertain'].includes(admission.ready)
    ? { step: admission.step, projection: admission.projection, ready: admission.ready } : undefined;
  return { ...(githubFailure ? { githubFailure } : {}), ...(predicate ? { predicate } : {}), ...(writerFailure ? { writerFailure } : {}), ...(admissionEffect ? { admissionEffect } : {}) };
}

// Follow wrapper causes only for typed facts. A wrapper's own observation wins.
export function failureFacts(error) {
  let current = error;
  let facts = {};
  for (let depth = 0; current && depth < 5; depth++, current = current.cause) {
    facts = { ...safeFailureFacts({ predicate: current.observation, ...current.details }), ...facts };
  }
  return facts;
}

// Acknowledgement uncertainty only. Definite rejections need no readback.
export function ambiguousGithubWrite(error) {
  const facts = failureFacts(error).githubFailure;
  return facts?.method !== 'GET' && facts?.attempts === 1 &&
    !(facts.reason === 'http' && [400, 401, 403, 404, 405, 409, 422].includes(facts.status));
}

export function attachWriteReadback(error, readback, cause) {
  const githubFailure = failureFacts(error).githubFailure;
  if (githubFailure) error.details = { ...error.details, githubFailure: { ...githubFailure, readback } };
  if (cause) error.native = { ...error.native, readbackFailure: cause };
}

const phaseNames = {
  authority: 'owner admission', 'pre-worker-admission': 'owner admission', preflight: 'preflight',
  checkout: 'checkout preparation', execution: 'Codex execution', progress: 'collection or publication',
  finalization: 'terminal handoff', readiness: 'result and PR handoff', 'writer-publication': 'Writer publication',
  'result-parse': 'Codex result parsing', 'publication-recovery': 'publication recovery'
};
const predicateNames = {
  status: 'GitHub run.status', run_id: 'GitHub run ID', run_attempt: 'GitHub run attempt', subject_number: 'GitHub target number',
  'pr.starting-head': 'pull request starting head', 'task-branch-head': 'Task branch head', event: 'GitHub event type',
  'inputs.route': 'launch route', 'event.action': 'event action', 'event.label': 'ready label', 'event.name': 'event name',
  'event.subject.kind': 'event target kind', 'issue.kind': 'Task target kind', 'issue.state': 'Task state', 'pr.state': 'pull request state'
};
const admissionChecks = {
  run_id: 'run ID', repository: 'repository', actor: 'owner identity', triggering_actor: 'triggering owner identity',
  status: 'run status', workflow_path: 'workflow path', event: 'event type', head_branch: 'trusted base branch',
  run_attempt: 'run attempt', run_title: 'run title', subject_number: 'target number', issue_kind: 'target kind',
  pr_base_repository: 'pull request base repository', pr_head_repository: 'pull request head repository', pr_head_branch: 'pull request head branch'
};
const httpLabels = { 401: 'Unauthorized', 403: 'Forbidden', 404: 'Not Found', 408: 'Request Timeout',
  429: 'Too Many Requests', 500: 'Internal Server Error', 502: 'Bad Gateway', 503: 'Service Unavailable', 504: 'Gateway Timeout' };
const otherObservations = {
  EVENT_PAYLOAD_INVALID: 'The GitHub Actions event payload was not valid JSON.',
  GITHUB_LIST_INVALID: 'The GitHub API response did not contain the expected list.',
  GITHUB_VALIDATION_RUNS_INVALID: 'The GitHub API response did not contain the expected workflow run list.',
  CHILD_ENVELOPE_INVALID: 'The dispatcher returned a receipt that did not identify the original Codex attempt.',
  CHECKOUT_ALREADY_EXISTS: 'The checkout path already contains retained state.',
  CHECKOUT_DIRTY: 'The checkout has changes requiring reconciliation.',
  STARTING_STATE_MISMATCH: 'The live starting state failed the admitted head or ancestry check.',
  AUTHORITY_CHANGED: 'Live Task authority differs from the admitted authority.',
  ATTEMPT_CONTROLLER_BUSY: 'Another controller holds the attempt lock.',
  JOURNAL_MISSING_EXECUTION_UNKNOWN: 'The required execution receipt is missing or unusable.',
  EXECUTION_UNKNOWN_NO_RETRY: 'A prior execution reservation has no conclusive terminal receipt.',
  OWNER_EVENT_REQUIRED: 'The event did not match the configured owner command and trusted workflow binding.',
  OWNER_RUN_NOT_ADMITTED: 'GitHub workflow run evidence did not match the configured owner command.',
  ADMISSION_QUIESCED: 'The admission gate is closed for a lifecycle operation.',
  READY_EVENT_REPLACED: 'The original ready event could no longer be verified.',
  READY_CONSUMPTION_UNCERTAIN: 'Writer could not establish the effect of the reserved ready-label removal.',
  CURRENT_PROTOCOL_REQUIRED: 'The Task lacks current native authority for a new execution.',
  CODEX_JSON_INVALID: 'The Codex result could not be decoded as JSON.',
  CODEX_RESULT_INVALID: 'The Codex result did not meet the required schema.',
  CODEX_RESULT_MISSING: 'The runtime did not produce the required Codex result.',
  CODEX_NONZERO_EXIT: 'The Codex process reported an unsuccessful exit.',
  CODEX_OUTPUT_TOO_LARGE: 'The Codex result exceeded the bounded output limit.',
  CODEX_RUNTIME_TIMEOUT: 'The Codex execution reached its runtime deadline.',
  SEMANTIC_RESULT_BLOCKED: 'Codex returned a blocked Task result.',
  WORKFLOW_READ_TOKEN_REQUIRED: 'The required Actions-read credential was unavailable.',
  AUTHORITY_CHARTER_INVALID: 'The trusted Task charter failed the current native authority checks.',
  ISSUE_CLOSURE_POLICY_INVALID: 'The canonical Task does not have one valid Issue closure policy field.',
  CURRENT_CHANGE_REQUEST_MISSING: 'The pull request lacks the current trusted Change Request for this head.',
  WRITER_RECEIPT_INVALID: 'The privileged Writer returned a malformed or repository-unbound receipt.',
  WRITER_HELPER_TIMEOUT: 'The privileged Writer invocation exceeded its deadline.',
  WRITER_OUTPUT_TOO_LARGE: 'The privileged Writer response exceeded the capture limit.',
  CONTAINMENT_NOT_PROVEN: 'The controller could not verify execution containment.',
  COMMENT_PUBLICATION_UNCERTAIN: 'The reserved comment could not be matched to a native comment.',
  PR_PUBLICATION_UNCERTAIN: 'The reserved pull request could not be matched to a native pull request.',
  NO_DURABLE_PROGRESS: 'The controller could not establish a deliverable candidate from the retained checkout.'
};
const stopReasons = {
  'non-transient': 'the failure did not qualify for retry',
  'attempt-limit': 'the read attempt limit was reached',
  deadline: 'the request deadline left no time to retry',
  'provider-delay': 'the provider-directed wait exceeded the remaining read budget',
  mutation: 'Writer must verify the original effect before another write',
  cancelled: 'the request was cancelled'
};
const next = {
  credential: 'Have the host operator verify the configured Writer App installation and its token access before recovery.',
  gate: 'Have the host operator check admission status for the retained lifecycle operation before opening admission.',
  event: 'Compare the original Actions run with the configured workflow and authenticated owner command before issuing another command.',
  authority: 'Correct the named check in the canonical Task, trusted Decision, or Change Request before requesting fresh admission.',
  transport: 'Have the host operator check the Relay host’s DNS or TLS configuration for GitHub.',
  configuration: 'Have the host operator verify the selected consumer configuration and Writer credential binding.',
  current: 'Have the owner reconcile the Task charter and active schema-v4 Decision or Change Request through the current native authority workflow.',
  access: 'Verify that the configured GitHub credential has access to the selected repository and endpoint.',
  wait: 'Have the host operator verify the Relay runner can reach the selected GitHub API before pursuing recovery for this run.',
  waitRate: 'Check the rate-limit reset for the configured GitHub reader before making another request.',
  eventPayload: 'Verify that the configured routing workflow passed the original Actions event to Relay.',
  checkout: 'Have the host operator reconcile the retained checkout for the original attempt before another checkout is prepared.',
  write: 'Reconcile the original Writer reservation against its native target using Inspect in Relay recovery before another mutation.',
  projection: 'Run Relay recovery with Inspect for the original attempt before changing Step labels or the ready command.',
  ready: 'Reconcile the original ready-label event and Writer reservation before applying a fresh ready command.',
  result: 'Review the retained result and candidate for this attempt before requesting any further execution.',
  containment: 'Have the host operator verify containment for this attempt before reusing its execution resource.',
  diagnostic: 'Have the host operator read the retained diagnostic for this run through the supported protected diagnostics path before recovery.'
};

function githubObservation(github) {
  const result = github.status ? ` returned HTTP ${github.status}${httpLabels[github.status] ? ` ${httpLabels[github.status]}` : ''}` : '';
  const detail = { timeout: 'timed out', network: 'failed at the network boundary', 'transport-unknown': 'failed without a recognized transport cause',
    'invalid-response': 'returned a response that could not be decoded', 'graphql-error': 'did not return a successful GraphQL mutation result',
    'rate-limit': 'was rate-limited', cancelled: 'was cancelled' }[github.reason];
  return `GitHub ${github.method} (${github.endpoint})${result || (detail ? ` ${detail}` : ' failed')}${result && detail ? ` and ${detail}` : ''}${github.osCode ? ` (${github.osCode})` : ''}.`;
}

export function failureExplanation(code, diagnostic = {}, { runId, reason, target, outcome, knownUnbound = false } = {}) {
  const { githubFailure: github, predicate, writerFailure: writer, admissionEffect: admission } = safeFailureFacts(diagnostic);
  const stage = diagnostic.classification?.stage;
  const phase = [stage, diagnostic.failureBoundary].filter(value => Object.hasOwn(phaseNames, value))[0];
  const phaseName = phaseNames[phase] ?? 'routing';
  const operation = writer ? writer.operation === phase ? `Writer ${phaseName}` : `Writer ${writer.operation} during ${phaseName}`
    : diagnostic.runtime?.operation === 'checkout-prepare' ? 'checkout preparation' : phaseName;
  const run = Number.isSafeInteger(runId) && runId > 0 ? `run-${runId}` :
    /^run-[1-9][0-9]{0,19}$/.test(diagnostic.executionId ?? '') ? diagnostic.executionId : null;
  const subject = Number.isSafeInteger(target?.number) && target.number > 0
    && ['issue', 'pull_request'].includes(target.kind) ? `${target.kind === 'issue' ? 'Issue' : 'PR'} #${target.number}` : null;
  const context = [run, subject].filter(Boolean).join(', ');
  const failureCode = /^[A-Z][A-Z0-9_]{0,79}$/.test(code ?? '') ? code : 'UNCLASSIFIED_FAILURE';
  const check = Object.hasOwn(admissionChecks, reason ?? '') ? admissionChecks[reason] : undefined;
  const heading = `Relay ${operation} failed${context ? ` (${context})` : ''}. ${failureCode}${check ? ` (${check === 'run status' ? 'status' : check})` : ''}.`;
  const details = [];
  const originalCode = diagnostic.executionFailure?.classification?.code;
  if (/^[A-Z][A-Z0-9_]{0,79}$/.test(originalCode ?? '')) {
    details.push(`Codex execution originally failed (${originalCode}). ${otherObservations[originalCode] ?? 'The underlying execution cause is unconfirmed.'}`);
  }
  if (predicate) details.push(`Expected ${predicateNames[predicate.check]} ${predicate.expected}, observed ${predicate.observed}.`);
  else if (check) details.push(`The ${check} check failed. Comparable values are unavailable in the public result.`);
  else if (!github) details.push(Object.hasOwn(otherObservations, failureCode) ? otherObservations[failureCode]
    : `The underlying cause was not established at the ${phaseName} boundary.`);
  if (github) details.push(githubObservation(github),
    `${github.attempts} request attempt${github.attempts === 1 ? '' : 's'} (${Math.max(0, github.attempts - 1)} retries). Recovery stopped because ${stopReasons[github.stopped]}.`);
  else if (predicate || check) details.push('Relay stopped at the failed authority check without retrying it.');
  if (github?.readback) details.push(github.readback === 'not-observed'
    ? 'Native readback did not show the reserved effect. Writer did not repeat the write.'
    : 'Writer checked for the reserved effect, but native readback was inconclusive. Writer did not repeat the write.');
  if (writer?.osCode) details.push(`Writer transport reported ${writer.osCode}.`);
  if (!github && writer && (writer.exit !== undefined || writer.signal)) details.push(`Writer helper ${writer.signal ? `ended on ${writer.signal}` : `exited with code ${writer.exit}`}.`);
  const last = { 'contained-execution': 'child containment', checkout: 'checkout preparation', collection: 'candidate collection',
    publication: 'candidate publication', admission: 'Writer admission', 'outcome-publication': 'Outcome publication',
    'terminal-handoff': 'terminal handoff' }[diagnostic.lastSuccessfulBoundary];
  if (typeof last === 'string') details.push(`Last verified boundary was ${last}.`);
  const child = diagnostic.observed ?? {};
  details.push(child.child === 'not_started' ? 'The Codex child did not start.' : child.child === 'started'
    ? `The Codex child started${Number.isInteger(child.exitCode) && child.exitCode >= 0 && child.exitCode <= 255 ? ` and exited with code ${child.exitCode}` : signals.includes(child.signal) ? ` and ended on ${child.signal}` : ''}.`
    : 'Codex child state is unknown.');
  const gitExit = diagnostic.publication?.gitExitCode;
  if (Number.isInteger(gitExit) && gitExit >= 0 && gitExit <= 255) details.push(`Trusted Git exited with code ${gitExit}.`);
  if (signals.includes(diagnostic.publication?.signal)) details.push(`Trusted Git ended on ${diagnostic.publication.signal}.`);
  if (/^GIT_[A-Z_]{1,70}$/.test(diagnostic.publication?.priorCause ?? ''))
    details.push(`The preceding Git operation also reported ${diagnostic.publication.priorCause}.`);
  const os = diagnostic.runtime?.diagnosticCode ?? failureCode;
  if (['EACCES', 'EPERM', 'ENOENT', 'EIO', 'ENOSPC', 'EMFILE', 'EROFS'].includes(os)) details.push(`The runtime reported ${os}.`);
  const head = diagnostic.durable?.publishedHead;
  const collected = diagnostic.durable?.collectedHead;
  if (/^[a-f0-9]{40}$/.test(head ?? '')) details.push(`Verified published head ${head}.`);
  else if (/^[a-f0-9]{40}$/.test(collected ?? '')) details.push(`Writer collected candidate ${collected}. Publication is unconfirmed.`);
  else if (stage === 'preflight' && child.child === 'not_started') details.push('This preflight failure produced no new candidate.');
  if (admission) details.push(`Writer reserved Step ${admission.step}. Step label projection is ${admission.projection}. Ready command consumption was ${admission.ready === 'not-attempted' ? 'not attempted at this boundary' : 'not confirmed'}.`);
  if (knownUnbound) details.push('No target-bound Outcome was authorized.');
  if (diagnostic.diagnosticRecorderFailed === true) details.push('The diagnostic recorder also failed. Evidence retention is unconfirmed.');
  if (diagnostic.terminalJournalFailed === true) details.push('The terminal journal write also failed. Its durable state is unconfirmed.');
  const outcomeHttp = safeGithubFailure(outcome?.githubFailure);
  if (outcome?.status === 'published') details.push('Writer confirmed a target-bound Outcome.');
  if (outcome?.status === 'failed') details.push(`Outcome delivery also failed (${/^[A-Z][A-Z0-9_]{0,79}$/.test(outcome.code ?? '') ? outcome.code : 'OUTCOME_PUBLICATION_FAILED'}). Its publication is unconfirmed.`, ...(outcomeHttp ? [githubObservation(outcomeHttp), `Outcome delivery stopped after ${outcomeHttp.attempts} request attempt(s) because ${stopReasons[outcomeHttp.stopped]}.`,
      ...(outcomeHttp.readback ? ['Writer checked the original Outcome reservation without issuing another write.'] : [])] : []));
  const store = diagnostic.durable?.diagnosticStore;
  const fallback = diagnostic.durable?.fallbackReference;
  const ref = item => /^[A-Za-z0-9_-]{1,128}$/.test(item?.executionId ?? '') ? item.executionId : null;
  if (store?.status === 'stored' && ref(store)) details.push(`Protected diagnostics reference ${ref(store)}.`);
  else if (['reserved', 'released', 'retained', 'stored'].includes(fallback?.status) && ref(fallback)) details.push(`Protected fallback reference ${ref(fallback)}. Primary capture is unconfirmed.`);
  else if (store || fallback) details.push('Protected evidence retention is unconfirmed.');
  const secondaryWrite = outcome?.status === 'failed' && outcomeHttp?.method !== 'GET';
  const mutation = ambiguousGithubWrite({ details: { githubFailure: github } });
  const uncertainWrite = mutation || secondaryWrite || /PUBLICATION_UNCERTAIN|REF_OBSERVATION|PUSH_UNCERTAIN|GIT_REMOTE_STATE_UNKNOWN/.test(failureCode)
    || ['publish-progress', 'finish', 'complete-handoff', 'terminal-outcome'].includes(writer?.operation) && !github;
  if (uncertainWrite) details.push('An external effect may remain unverified.');
  const actions = [
    [github?.endpoint === 'Writer installation token', next.credential],
    [failureCode.startsWith('READY_'), next.ready],
    [admission?.projection === 'unknown', next.projection],
    [uncertainWrite, next.write],
    [/CONTAINMENT_NOT_PROVEN|EXECUTION_UNKNOWN|ATTEMPT_CONTROLLER_BUSY/.test(failureCode)
      || github?.stopped === 'cancelled' && child.child !== 'not_started', next.containment],
    [github?.reason === 'rate-limit', next.waitRate],
    [github && [401, 403, 404].includes(github.status), next.access],
    [github?.reason === 'network' && github.stopped === 'non-transient', next.transport],
    [github && ['attempt-limit', 'deadline', 'provider-delay'].includes(github.stopped), next.wait],
    [failureCode === 'ADMISSION_QUIESCED', next.gate],
    [/^OWNER_(RUN_NOT_ADMITTED|EVENT_REQUIRED)$/.test(failureCode), next.event],
    [failureCode === 'CURRENT_PROTOCOL_REQUIRED', next.current],
    [failureCode === 'EVENT_PAYLOAD_INVALID', next.eventPayload],
    [failureCode.startsWith('CHECKOUT_'), next.checkout],
    [/CONFIG|CREDENTIAL|EXECUTION_SLOT|WRITER_IDENTITY|WORKFLOW_READ_TOKEN/.test(failureCode), next.configuration],
    [/AUTHORITY|STARTING_STATE|STEP_LABEL|^ISSUE_/.test(failureCode), next.authority],
    [failureCode.startsWith('CODEX_') || failureCode === 'SEMANTIC_RESULT_BLOCKED', next.result]
  ];
  const action = actions.find(([matches]) => matches)?.[1] ?? next.diagnostic;
  return [heading, ...details, `Next action: ${action}`].join(' ');
}
