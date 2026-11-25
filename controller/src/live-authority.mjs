import { setTimeout as sleep } from 'node:timers/promises';
import { performance } from 'node:perf_hooks';
import { failureFacts } from './failure-report.mjs';
import { CONSUMER, CONSUMER_DIGEST } from '../../consumer/consumer.mjs';
import { REPOSITORY, OWNER, REVIEWER, VERSION, fail, requireCurrentProtocol, branchName, exactSha, positive, isAdmissionDomainBlock, DEFAULT_NATIVE_VALIDATIONS, NATIVE_VALIDATIONS, validateEnvelope } from './execution-contract.mjs';
import { dispatchRunName, labelRunCommandMatches, launchStep } from './launch-metadata.mjs';
import { labelNames, READY_LABELS } from './step-metadata.mjs';
import { findCurrentIssuePullRequest } from './publication-target.mjs';
import { readTaskAuthority } from './task-authority.mjs';
import { taskReferences } from './task-relationship.mjs';
import { authorityMode, createAdmissionSnapshot, validateAdmissionSnapshot, canonicalAuthorityJson } from '../../contracts/src/github-authority.mjs';
import { blockedCrContinuation } from './blocked-cr-continuation.mjs';
import { readPriorOutcomeContext, appendPriorOutcomeContext } from './prior-outcome-context.mjs';
import { rejectOwnerRun } from './owner-run-rejection.mjs';

const QUEUED_RUN_OBSERVATION_DELAYS_MS = [250, 500, 1000, 2000, 4000];
const QUEUED_RUN_OBSERVATION_BUDGET_MS = 10_000;

// Ordering is native identity, never API order or a prose reference to an older review.
export function currentReview(reviews) {
  const decisive = reviews.filter(r => r.user?.login === REVIEWER && ['CHANGES_REQUESTED', 'APPROVED', 'DISMISSED'].includes(r.state));
  const review = decisive.sort((a, b) => Number(a.id) - Number(b.id)).at(-1);
  if (!review || review.state !== 'CHANGES_REQUESTED' || !exactSha(review.commit_id)) fail('CURRENT_CHANGE_REQUEST_MISSING');
  return review;
}
export function linkedIssue(body) {
  const ids = taskReferences(body, REPOSITORY);
  if (ids.length !== 1) fail('CANONICAL_ISSUE_AMBIGUOUS');
  return ids[0];
}
export function assertPr(pr, number) {
  for (const [check, expected, observed, valid] of [
    ['pr.number', number, pr?.number, pr?.number === number],
    ['pr.state', 'open', pr?.state, pr?.state === 'open'],
    ['pr.merged', false, pr?.merged, !pr?.merged],
    ['pr.base.ref', CONSUMER.baseBranch, pr?.base?.ref, pr?.base?.ref === CONSUMER.baseBranch],
    ['pr.base.repository', REPOSITORY, pr?.base?.repo?.full_name, pr?.base?.repo?.full_name === REPOSITORY],
    ['pr.head.repository', REPOSITORY, pr?.head?.repo?.full_name, pr?.head?.repo?.full_name === REPOSITORY],
    ['pr.head.sha', 'exact 40-character commit SHA', pr?.head?.sha, exactSha(pr?.head?.sha)],
    ['pr.base.sha', 'exact 40-character commit SHA', pr?.base?.sha, exactSha(pr?.base?.sha)]
  ]) if (!valid) fail('PR_NOT_ADMITTED', { check, expected, observed: observed ?? null });
  branchName(pr.head.ref);
}

async function observeTaskBranchHead(api, branch) {
  const refs = await api.get(`/git/matching-refs/heads/${branchName(branch)}`);
  if (!Array.isArray(refs)) fail('STARTING_STATE_MISMATCH');
  const matches = refs.filter(ref => ref?.ref === `refs/heads/${branch}`);
  if (!matches.length) return null;
  if (matches.length !== 1 || !exactSha(matches[0].object?.sha)) fail('STARTING_STATE_MISMATCH');
  return matches[0].object.sha;
}

async function hasMergedPriorPullRequest(api, previousRecord, retainedHead) {
  const previous = previousRecord.envelope;
  const number = previousRecord.prNumber ?? previousRecord.outcome?.prNumber
    ?? (previous.target === 'pull_request' ? previous.number : null);
  if (!positive(number) || previousRecord.publicationIntent) return false;
  const pr = await api.get(`/pulls/${number}`);
  return pr?.number === number && pr.state === 'closed' && pr.merged === true
    && pr.base?.ref === CONSUMER.baseBranch && pr.base?.repo?.full_name === REPOSITORY
    && pr.head?.sha === retainedHead;
}

export function startsAtPublishedIssueBase(e) {
  return e.target === 'issue' && e.branch !== null
    && (!e.continuation || e.startHead === e.historicalBase && e.continuation.pullRequest === null);
}

function assertIssue(issue) {
  for (const [check, expected, observed, valid] of [
    ['issue.state', 'open', issue?.state, issue?.state === 'open'],
    ['issue.owner', OWNER, issue?.user?.login, issue?.user?.login === OWNER],
    ['issue.kind', 'issue', issue?.pull_request ? 'pull_request' : 'issue', !issue?.pull_request]
  ]) if (!valid) fail('ISSUE_NOT_ADMITTED', { check, expected, observed: observed ?? null });
}

export async function readAuthority(api, target, number, options = {}) {
  const pr = target === 'pull_request' ? await api.get(`/pulls/${number}`) : null;
  if (pr) assertPr(pr, number);
  const issueNumber = pr ? linkedIssue(pr.body) : number;
  const issue = await api.get(`/issues/${issueNumber}`);
  assertIssue(issue);
  if (authorityMode(issue.body) !== 'github-native-v1') requireCurrentProtocol();
  return resolveAuthority(api, { target, issueNumber, issue, pr }, { ...options, step: launchStep(options.step) });
}

async function resolveAuthority(api, { target, issueNumber, issue, pr }, { targetBase, step, route, runId, lineage, snapshot,
  previousRecord, resolution, publicationTarget, admitting = false }) {
  const typed = await readTaskAuthority(api, issue, pr, {
    route, purpose: resolution?.purpose ?? snapshot?.purpose ?? issue.title?.replace(/^Task\s+#?\d+\s*[-–—:·|]+\s*/i, '') ?? `Task ${issueNumber}`,
    projectDefaults: { model: CONSUMER.defaultProfile.cliModelId, effort: CONSUMER.defaultProfile.effort,
      subagents: true, validation: [...DEFAULT_NATIVE_VALIDATIONS] },
    startingState: { branch: `${CONSUMER.taskBranchPrefix}task-${issueNumber}`, base_sha: targetBase,
      starting_head: targetBase, existing_pr: null }, pullRequest: pr?.number,
    ...(snapshot ? { admittedAuthority: snapshot.authority, publicationTarget } : {}),
    ...(resolution ? { projectDefaults: resolution.project_defaults, startingState: resolution.starting_state } : {}),
  });
  const semantic = typed.request;
  if (pr && semantic.kind !== 'change-request') fail('CURRENT_CHANGE_REQUEST_MISSING');
  if (snapshot && ['purpose', 'scope', 'model', 'effort', 'subagents', 'validation', 'boundaries',
    'issue_closure_policy', 'continuation'].some(field => canonicalAuthorityJson(snapshot[field])
      !== canonicalAuthorityJson(typed.originalAuthority.request[field]))) fail('AUTHORITY_CHANGED');
  if (!pr && semantic.kind === 'change-request') fail('AUTHORITY_SOURCE_TARGET_MISMATCH');
  let continuationState;
  let observedBranchHead;
  let observedPullRequest;
  const priorCr = previousRecord?.envelope;
  const retainedCrProgress = pr && priorCr?.target === 'pull_request' && priorCr.number === pr.number
    && priorCr.reviewId === typed.reference.id
    && (previousRecord.publishedHead ?? previousRecord.outcome?.head ?? priorCr.startHead) !== semantic.starting_head;
  if (pr && !snapshot && (pr.head.sha !== semantic.starting_head || retainedCrProgress)) {
    continuationState = await blockedCrContinuation(api, { typed, pr, step, lineage, previousRecord, targetBase });
  }
  const priorAuthority = previousRecord?.envelope?.request?.authority;
  const newStartingPin = typed.decisions?.some(item => ['branch', 'base_sha', 'starting_head', 'existing_pr']
    .some(field => Object.hasOwn(item.decision.amendments, field))
    && !priorAuthority?.decisions.some(reference => canonicalAuthorityJson(reference) === canonicalAuthorityJson(item.reference)))
;
  if (!pr && !snapshot && semantic.branch !== null && !newStartingPin && previousRecord?.envelope?.branch === semantic.branch) {
    const retainedHead = previousRecord.publishedHead ?? previousRecord.outcome?.head;
    if (exactSha(retainedHead) && retainedHead !== semantic.base_sha) {
      observedBranchHead = await observeTaskBranchHead(api, semantic.branch);
      if (observedBranchHead === retainedHead) {
        observedPullRequest = await findCurrentIssuePullRequest(api, { issueNumber, branch: semantic.branch,
          continuation: { head: retainedHead } });
        if (previousRecord.prNumber && observedPullRequest?.number !== previousRecord.prNumber) {
          if (observedPullRequest || semantic.existing_pr !== null
            || !await hasMergedPriorPullRequest(api, previousRecord, retainedHead)) fail('PR_AUTHORITY_CHANGED');
        }
        if (observedPullRequest && observedPullRequest.head.sha !== retainedHead) fail('STARTING_STATE_MISMATCH');
        continuationState = { branch: semantic.branch, base_sha: semantic.base_sha,
          starting_head: retainedHead, existing_pr: observedPullRequest?.number ?? null };
      } else {
        // A merged predecessor is history once the old ref has gone away.
        // A re-created ref at the new authorized base is equivalent here.
        const freshStart = semantic.existing_pr === null && semantic.starting_head === semantic.base_sha
          && (observedBranchHead === null || observedBranchHead === semantic.starting_head);
        if (!freshStart || !await hasMergedPriorPullRequest(api, previousRecord, retainedHead))
          fail('STARTING_STATE_MISMATCH', { check: 'task-branch-head', expected: retainedHead, observed: observedBranchHead });
      }
    }
  }
  let priorOutcome = continuationState?.priorOutcome;
  let priorUnavailable = false;
  if (!snapshot && previousRecord && !priorOutcome) {
    try { priorOutcome = await readPriorOutcomeContext(api, previousRecord, lineage, issueNumber); }
    catch (error) {
      priorUnavailable = true;
      await api.recordFailure?.({ error, operation: 'prior-outcome-context', phase: 'authority', runId });
    }
  }
  const priorContext = appendPriorOutcomeContext(typed.input, priorOutcome, { unavailable: priorUnavailable });
  const q = snapshot ? validateAdmissionSnapshot(snapshot, { step, route, attempt: `run-${runId}` })
    : createAdmissionSnapshot(typed, { step, route, runId, attempt: `run-${runId}`, lineage, ...continuationState });
  const noSource = q.route === 'manual' && q.branch === null && q.base_sha === null && q.starting_head === null;
  if (!noSource && (!q.branch || !exactSha(q.base_sha) || !exactSha(q.starting_head))) fail('AUTHORITY_STARTING_STATE_INVALID');
  if (q.branch) branchName(q.branch);
  if (pr && pr.head.ref !== q.branch) fail('STARTING_STATE_MISMATCH');
  let continuation = !pr && (q.existing_pr !== null || q.starting_head !== q.base_sha)
    ? { head: q.starting_head, pullRequest: q.existing_pr } : null;
  const admittingIssueSource = admitting && target === 'issue' && !noSource;
  if (admittingIssueSource) {
    if (!continuation) await verifyPublishedBase(api, q.base_sha, targetBase);
    const observed = observedBranchHead === undefined ? await observeTaskBranchHead(api, q.branch) : observedBranchHead;
    const headCheck = { check: 'task-branch-head', expected: q.starting_head, observed };
    if (continuation) {
      if (observed === null) fail('TASK_BRANCH_MISSING', headCheck);
      if (observed !== q.starting_head) fail('STARTING_STATE_MISMATCH', headCheck);
    } else if (observed !== null) {
      if (observed !== q.starting_head) fail('TASK_BRANCH_ALREADY_EXISTS', headCheck);
      // Keep the accepted base in the snapshot and pin the ref for checkout
      // and publication without selecting a current PR.
      continuation = { head: q.starting_head, pullRequest: null };
    }
  }
  const thread = `Task ${issueNumber} — Step ${q.step} — ${semantic.kind === 'change-request' ? `${semantic.change_request_id} — ` : ''}${q.purpose}`;
  const execution = { issue, ...(pr ? { pr, review: { ...typed.record, commit_id: semantic.reviewed_head_sha } } : {}),
    issueNumber, branch: q.branch, historicalBase: q.base_sha, startHead: q.starting_head,
    profile: { cliModelId: q.model, effort: q.effort }, subagentsAllowed: q.subagents,
    thread, title: `Task ${issueNumber} · Step ${q.step}${semantic.kind === 'change-request' ? ` · ${semantic.change_request_id}` : ''} · ${q.purpose}`,
    // Execution cannot prove whole-Task completion. The trusted owner may
    // designate a final closing link only after independent acceptance and
    // verifying the effective policy and remaining completion conditions.
    closure: `Related to #${issueNumber}`,
    input: priorContext.input, validation: q.validation, request: q, requestReference: typed.reference,
    authorityDigest: typed.authorityDigest,
    ...(snapshot ? { currentRequest: semantic, authorityDrift: typed.authorityDrift,
      originalRequest: typed.originalAuthority.request } : {}),
    admission: { kind: 'github-native-admission', warnings: [
      ...typed.warnings.map(code => ({ code, field: 'closure', resolved: 'keep-open' })),
      ...priorContext.warnings.map(code => ({ code, field: 'context', resolved: 'bounded-prior-outcome',
        message: code === 'PRIOR_OUTCOME_CONTEXT_TRUNCATED' ? 'Prior Writer Outcome context was clipped to its bounded projection; inspect the exact native source for complete evidence.' : 'Prior Writer Outcome context could not be verified; no prior result or external effect is inferred.' }))] },
    ...(continuation ? { continuation } : {}) };
  if (continuation?.pullRequest) {
    execution.pr = observedPullRequest ?? await findCurrentIssuePullRequest(api, execution, continuation.pullRequest);
  } else if (admittingIssueSource && continuation && observedPullRequest === undefined
    && await findCurrentIssuePullRequest(api, execution)) fail('PR_AUTHORITY_CHANGED');
  return execution;
}
export async function admitEnvelope(api, { runId, target, number, route, issueNumber, step, transport }, { nextStep, lineage, previousRecord, recordFailure = async () => undefined } = {}) {
  if (!positive(number) || !positive(runId) || !['issue', 'pull_request'].includes(target)
    || !['auto', 'manual'].includes(route)) fail('ROUTE_INVALID');
  if (transport !== undefined && transport !== 'label') fail('ROUTE_INVALID');
  if (transport === 'label') {
    // Resolve Task through the linked canonical Issue after target binding.
    issueNumber = target === 'issue' ? number : null;
  } else {
    if (!positive(issueNumber) || (target === 'issue' && number !== issueNumber)) fail('ROUTE_INVALID');
    if (step !== null && step !== undefined) step = launchStep(step);
  }
  const eventName = transport === 'label' ? target === 'issue' ? 'issues' : 'pull_request_target' : 'workflow_dispatch';
  const label = { route, target, number };
  const expectedTitle = transport === 'label' ? label : dispatchRunName({ route, issueNumber, step, target, number });
  function checkOwnerRun(run) {
    if (run?.id !== runId) rejectOwnerRun('run_id', runId, run?.id);
    if (run.repository?.full_name !== REPOSITORY) rejectOwnerRun('repository', REPOSITORY, run.repository?.full_name);
    if (run.actor?.login !== OWNER) rejectOwnerRun('actor', OWNER, run.actor?.login);
    if (run.triggering_actor && run.triggering_actor.login !== OWNER) rejectOwnerRun('triggering_actor', OWNER, run.triggering_actor?.login);
    const queued = transport === 'label' && route === 'auto' && run.status === 'queued';
    if (run.status !== 'in_progress' && !queued) rejectOwnerRun('status', 'in_progress', run.status);
    if (run.path !== CONSUMER.routingWorkflow) rejectOwnerRun('workflow_path', CONSUMER.routingWorkflow, run.path);
    if (run.event !== eventName) rejectOwnerRun('event', eventName, run.event);
    if (eventName !== 'pull_request_target' && run.head_branch !== CONSUMER.baseBranch) rejectOwnerRun('head_branch', CONSUMER.baseBranch, run.head_branch);
    if (run.run_attempt !== 1) rejectOwnerRun('run_attempt', 1, run.run_attempt);
    if ((transport !== 'label' && run.display_title !== expectedTitle)
        || (queued && !labelRunCommandMatches(run.display_title, label))) {
      rejectOwnerRun('run_title', expectedTitle, run.display_title);
    }
    return queued;
  }
  let run = await api.getRun(runId);
  let queued = checkOwnerRun(run);
  // The job can reach its runner before GitHub's run status catches up.
  // Reobserve this exact run before allocating anything, without accepting queued.
  const deadline = performance.now() + QUEUED_RUN_OBSERVATION_BUDGET_MS;
  for (const delay of QUEUED_RUN_OBSERVATION_DELAYS_MS) {
    if (!queued || performance.now() + delay >= deadline) break;
    await sleep(delay);
    const deadlineMs = Math.floor(deadline - performance.now());
    if (deadlineMs <= 0) break;
    const observed = await api.getRun(runId, { deadlineMs });
    if (performance.now() >= deadline) break;
    run = observed;
    queued = checkOwnerRun(run);
  }
  if (queued) rejectOwnerRun('status', 'in_progress', run.status);
  let subject, command;
  if (transport === 'label') {
    // Establish the native target before any domain-block Outcome may be
    // published. A caller cannot borrow another target's owner run and point
    // an admission error at an unrelated Issue/PR with invalid authority.
    subject = await api.get(target === 'issue' ? `/issues/${number}` : `/pulls/${number}`);
    if (subject?.number !== number) rejectOwnerRun('subject_number', number, subject?.number);
    if (!labelRunCommandMatches(run.display_title, label)) rejectOwnerRun('run_title', expectedTitle, run.display_title);
    if (target === 'issue' && subject.pull_request) rejectOwnerRun('issue_kind', 'issue', 'pull_request');
    if (target === 'pull_request') {
      if (subject.base?.repo?.full_name !== REPOSITORY) rejectOwnerRun('pr_base_repository', REPOSITORY, subject.base?.repo?.full_name);
      if (subject.head?.repo?.full_name !== REPOSITORY) rejectOwnerRun('pr_head_repository', REPOSITORY, subject.head?.repo?.full_name);
      if (![CONSUMER.baseBranch, subject.head.ref].includes(run.head_branch)) rejectOwnerRun('pr_head_branch', [CONSUMER.baseBranch, subject.head.ref], run.head_branch);
    }
    // Unsafe/unbound/stale commands throw outside the domain-result boundary:
    // they authorize neither consumption nor an Outcome on this target.
    const event = await readReadyEvent(api, { number, route, run, subject, rejectAmbiguous: true });
    command = { transport, readyEventId: event.id, readyEventAt: event.created_at,
      readyLabel: event.label.name, runName: run.display_title };
  }
  const attemptId = `run-${runId}`;
  let targetBase;
  try {
    const pr = target === 'pull_request' ? subject ?? await api.get(`/pulls/${number}`) : null;
    const canonicalIssueNumber = pr ? linkedIssue(pr.body) : number;
    if (command) issueNumber = canonicalIssueNumber;
    const issue = target === 'issue' && subject ? subject : await api.get(`/issues/${canonicalIssueNumber}`);
    if (authorityMode(issue.body) !== 'github-native-v1') requireCurrentProtocol();
    const admittedStep = launchStep(nextStep);
    targetBase = (await api.get(`/git/ref/heads/${CONSUMER.baseBranch}`)).object?.sha;
    if (!exactSha(targetBase)) fail('TARGET_BASE_INVALID');
    if (pr) assertPr(pr, number);
    assertIssue(issue);
    const a = await resolveAuthority(api, { target, issueNumber: canonicalIssueNumber, issue, pr },
      { targetBase, step: admittedStep, route, runId, lineage, previousRecord, admitting: true });
    if (a.request && a.request.route !== route) fail('AUTHORITY_ROUTE_MISMATCH');
    if (a.issueNumber !== issueNumber) fail('CANONICAL_ISSUE_AMBIGUOUS');
    if (!a.validation.length || a.validation.some(name => !NATIVE_VALIDATIONS.has(name))) fail('REQUIRED_VALIDATION_UNSUPPORTED');
    if (a.pr && a.pr.head.sha !== a.startHead) fail('STARTING_STATE_MISMATCH', { check: 'pr.starting-head', expected: a.startHead, observed: a.pr.head.sha });
    return { version: VERSION, repository: REPOSITORY, consumerDigest: CONSUMER_DIGEST, attemptId, runId,
      target, number, issueNumber: a.issueNumber, route, step: admittedStep,
      ...command,
      branch: a.branch, startHead: a.startHead, historicalBase: a.historicalBase, targetBase,
      reviewId: a.review?.id ?? null, authorityDigest: a.authorityDigest,
      profile: a.profile, thread: a.thread, title: a.title, closure: a.closure,
      input: a.input, validation: a.validation, subagentsAllowed: a.subagentsAllowed,
      admission: a.admission, warnings: a.warnings, resolutions: a.resolutions,
      ...(a.request ? { request: a.request, requestReference: a.requestReference } : {}),
      ...(a.continuation ? { continuation: a.continuation } : {}) };
  } catch (error) {
    if (!isAdmissionDomainBlock(error)) throw error;
    let diagnosticStore;
    let diagnosticRecorderFailed = false;
    try { diagnosticStore = await recordFailure({ error, phase: 'authority', operation: 'admit-authority', runId, workerStarted: false }); }
    catch { diagnosticRecorderFailed = true; }
    // The event identity is known, but executable authority is not. Preserve
    // only safe structured blocker data; never manufacture a branch,
    // profile, or reviewed/remediation head for the terminal Outcome.
    return { blocked: true, version: VERSION, repository: REPOSITORY, consumerDigest: CONSUMER_DIGEST, attemptId, runId,
      target, number, issueNumber, route, step: null, targetBase, ...command,
      block: { ...failureFacts(error), diagnosticStore, ...(diagnosticRecorderFailed ? { diagnosticRecorderFailed } : {}), code: /^[A-Z][A-Z0-9_]{0,79}$/.test(error.code ?? '') ? error.code : 'ADMISSION_BLOCKED',
        ...(typeof error.details?.field === 'string' ? { field: error.details.field } : {}) } };
  }
}

export async function readyTransitions(api, number) {
  const events = (await api.list(`/issues/${number}/events`))
    .filter(e => ['labeled', 'unlabeled'].includes(e.event) && READY_LABELS.includes(e.label?.name));
  if (events.some(event => !positive(event.id))) fail('READY_EVENT_AMBIGUOUS');
  const unique = new Map();
  for (const event of events) {
    const previous = unique.get(event.id);
    if (previous && canonicalAuthorityJson(previous) !== canonicalAuthorityJson(event)) fail('READY_EVENT_AMBIGUOUS');
    unique.set(event.id, event);
  }
  return [...unique.values()].sort((a, b) => a.id - b.id);
}

function rejectReady(code, check, expected, observed) {
  const error = Object.assign(new Error(code), { code,
    observation: { check, expected, observed: observed ?? null, availability: observed === undefined ? 'unavailable' : 'available' } });
  error.details = { failureDiagnostic: { code, stage: 'authority', boundary: 'authority', workerStarted: false,
    childState: 'not_started', operation: 'ready-event-binding',
    preview: `${code}: ${check} failed. No worker started. Inspect the original native ready event and owner command before any fresh launch.` } };
  throw error;
}

async function readReadyEvent(api, { number, route, run, subject, rejectAmbiguous = false }) {
  const label = route === 'auto' ? READY_LABELS[0] : READY_LABELS[1];
  const ready = labelNames(subject.labels).filter(name => READY_LABELS.includes(name));
  if (ready.length !== 1 || ready[0] !== label) rejectReady('READY_LABEL_AMBIGUOUS', 'ready-label', [label], ready);
  const events = await readyTransitions(api, number);
  const event = events.at(-1);
  const age = Date.parse(run.created_at) - Date.parse(event?.created_at);
  // Bind the live native command to this first run, not a surviving old label.
  for (const [check, expected, observed, valid] of [
    ['ready-event-id', 'positive native event ID', event?.id, positive(event?.id)],
    ['ready-event-kind', 'labeled', event?.event, event?.event === 'labeled'],
    ['ready-event-label', label, event?.label?.name, event?.label?.name === label],
    ['ready-event-actor', OWNER, event?.actor?.login, event?.actor?.login === OWNER],
    ['ready-event-actor-type', 'User', event?.actor?.type, event?.actor?.type === 'User'],
    ['ready-event-age', '0..120000 milliseconds before run creation', Number.isFinite(age) ? age : null,
      Number.isFinite(age) && age >= 0 && age <= 120000]
  ]) if (!valid) rejectReady('READY_EVENT_STALE', check, expected, observed);
  // The run API timestamps have second precision and expose no triggering
  // timeline event ID. A same-second replacement cannot be attributed safely.
  if (rejectAmbiguous && events.some(other => other.id !== event.id && other.event === 'labeled'
    && other.created_at === event.created_at)) {
    const error = new Error('READY_EVENT_AMBIGUOUS'); error.code = error.message;
    error.details = { failureDiagnostic: { code: error.code, stage: 'authority', boundary: 'authority', workerStarted: false,
      preview: `Task command on #${number} has multiple ready events in one timestamp second. No command was consumed. Remove the ready label and apply the intended command again in a later second.` } };
    throw error;
  }
  return event;
}

export async function revalidateReadyEvent(api, e) {
  // Check immediately before reservation/consumption, including blocked
  // admission. Never remove a replacement command created during API reads.
  const subject = await api.get(`/issues/${e.number}`);
  if (subject?.number !== e.number) rejectOwnerRun('subject_number', e.number, subject?.number);
  const event = await readReadyEvent(api, { number: e.number, route: e.route,
    run: await api.getRun(e.runId), subject, rejectAmbiguous: true });
  if (event.id !== e.readyEventId || event.created_at !== e.readyEventAt) rejectReady('READY_EVENT_STALE', 'ready-event-revalidation',
    { id: e.readyEventId, created_at: e.readyEventAt }, { id: event.id, created_at: event.created_at });
}
export async function revalidateAuthority(api, e, { reporting = false, handoff = false, verifyStartingBase = false, publicationTarget } = {}) {
  validateEnvelope(e);
  // A missing authoring base was resolved once, before worker mutation. Main
  // advancement cannot silently rebind that immutable admission resolution.
  const a = await readAuthority(api, e.target, e.number, { targetBase: e.targetBase, step: e.step,
    route: e.route, runId: e.runId,
    lineage: e.request?.lineage, snapshot: e.request,
    resolution: e.request?.authority_resolution, publicationTarget });
  if (a.branch !== e.branch || a.startHead !== e.startHead
    || a.issueNumber !== e.issueNumber || (a.review?.id ?? null) !== e.reviewId) fail('AUTHORITY_CHANGED');
  if (a.request && a.request.route !== e.route) fail('AUTHORITY_CHANGED');
  // Keep exact source pins and explicit execution revocations. Boundary prose
  // and acceptance checks can change legitimately during source work: their
  // arrival is review evidence, not a deterministic revocation signal. This
  // never grants new protected effects or changes the admitted worker profile.
  // Reporting/contained source collection remains possible after revocation.
  const old = a.originalRequest; const current = a.currentRequest;
  if (!reporting && ['branch', 'base_sha', 'starting_head', 'existing_pr'].some(field =>
    canonicalAuthorityJson(old[field]) !== canonicalAuthorityJson(current[field]))) fail('AUTHORITY_CHANGED');
  // Preparing an already published result for independent review neither
  // executes amended scope nor accepts it. Keep exact artifact pins above;
  // current review/approval constraints still govern independent acceptance.
  if (!reporting && !handoff && (old.scope.some(value => !current.scope.includes(value))
    || e.route === 'manual' && (current.boundaries.some(value => !old.boundaries.includes(value))
      || current.validation.some(value => !old.validation.includes(value)))
    || current.continuation.hold && !old.continuation.hold)) fail('AUTHORITY_CHANGED');
  // This starting-state observation belongs only to active execution actions.
  // Exact retained result/recovery authority does not acquire a new main gate.
  if (verifyStartingBase && !reporting && startsAtPublishedIssueBase(e)) {
    const currentBase = (await api.get(`/git/ref/heads/${CONSUMER.baseBranch}`)).object?.sha;
    await verifyPublishedBase(api, e.historicalBase, currentBase);
    if (e.startHead !== e.historicalBase) await verifyPublishedBase(api, e.startHead, currentBase);
  }
  return a;
}

export async function revalidateIntegrationBase(api, e) {
  const current = (await api.get(`/git/ref/heads/${CONSUMER.baseBranch}`)).object?.sha;
  await verifyPublishedBase(api, e.targetBase, current);
}

// GitHub comparison binds two exact repository commits, not a moving branch.
// An immutable admitted base may precede current main, but never diverge from
// it or be replaced by an unverified worker-supplied object.
export async function verifyPublishedBase(api, base, current) {
  if (!exactSha(base) || !exactSha(current)) fail('STARTING_STATE_MISMATCH');
  if (base === current) return;
  let comparison;
  try { comparison = await api.get(`/compare/${base}...${current}?per_page=1`); }
  catch (cause) { if (cause.status === 404) throw Object.assign(new Error('STARTING_STATE_MISMATCH', { cause }), { code: 'STARTING_STATE_MISMATCH', observation: { check: 'published-base-comparison', expected: { base, current }, observed: { status: 404 } } }); throw cause; }
  if (comparison.status !== 'ahead' || comparison.base_commit?.sha !== base
    || comparison.merge_base_commit?.sha !== base) fail('STARTING_STATE_MISMATCH', { check: 'published-base-ancestry', expected: { status: 'ahead', base, mergeBase: base }, observed: { status: comparison.status, base: comparison.base_commit?.sha, mergeBase: comparison.merge_base_commit?.sha } });
}
