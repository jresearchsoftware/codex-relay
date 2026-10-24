import { CONSUMER, CONSUMER_DIGEST } from '../../consumer/consumer.mjs';
import { parseIssueAuthority } from '../../runtime/src/issue-authority.mjs';
import { extractRemediationContract, validateRemediationContract } from '../../contracts/src/contracts.mjs';
import { REPOSITORY, OWNER, REVIEWER, VERSION, fail, requireCurrentProtocol, digest, branchName, exactSha, positive, isAdmissionDomainBlock, NATIVE_VALIDATIONS, validateEnvelope } from './execution-contract.mjs';
import { dispatchRunName, labelRunCommandMatches, labelRunMatches, launchStep, remediationThreadTitle } from './launch-metadata.mjs';
import { assertStep, currentStep, changeRequestStep, assertPrStepTitle, projectedRequestTitle, labelNames, READY_LABELS } from './step-metadata.mjs';
import { findCurrentIssuePullRequest } from './publication-target.mjs';
import { readTaskAuthority } from './task-authority.mjs';
import { taskReferences } from './task-relationship.mjs';
import { authorityMode, createAdmissionSnapshot, validateAdmissionSnapshot, canonicalAuthorityJson } from '../../contracts/src/github-authority.mjs';
import { blockedCrContinuation } from './blocked-cr-continuation.mjs';

// Ordering is native identity, never API order or a prose reference to an older review.
export function currentReview(reviews) {
  const decisive = reviews.filter(r => r.user?.login === REVIEWER && ['CHANGES_REQUESTED', 'APPROVED', 'DISMISSED'].includes(r.state));
  const review = decisive.sort((a, b) => Number(a.id) - Number(b.id)).at(-1);
  if (!review || review.state !== 'CHANGES_REQUESTED' || !exactSha(review.commit_id)) fail('CURRENT_CHANGE_REQUEST_MISSING');
  return review;
}
const displayText = value => String(value ?? '').normalize('NFC').replace(/[\u2010-\u2015]/g, '-').replace(/\s+/g, ' ').trim();
function prose(value) {
  // Recognized formatting outside code is cosmetic. Literal code content is never passed
  // through emphasis, dash, Unicode or whitespace normalization.
  const text = String(value ?? ''); const parts = []; let end = 0;
  // Strip only simple paired emphasis at clear prose boundaries. Other stars,
  // including literal glob/operator and escaped stars, remain authoritative.
  const plain = part => displayText(part.replace(/^#{1,6}\s+/gm, '').replace(/^[ \t]*[-*+]\s+/gm, '')
    .replace(/(^|[\s([{])(\*{1,3})([^\s*\\](?:[^*\\\r\n]*[^\s*\\])?)\2(?=$|[\s.,;:!?)\]}])/g, '$1$3'));
  for (const match of text.matchAll(/(`+)([\s\S]*?)\1(?!`)/g)) {
    parts.push(plain(text.slice(end, match.index)), { code: match[2] });
    end = match.index + match[0].length;
  }
  parts.push(plain(text.slice(end)));
  return parts.filter(part => part !== '');
}
const sortedSet = values => [...values].sort();
function executableAuthority(a) {
  return { issueNumber: a.issueNumber, branch: a.branch, startHead: a.startHead,
    profile: { cliModelId: a.profile.cliModelId, effort: a.profile.effort },
    closure: a.closure, validation: sortedSet(a.validation),
    ...(a.continuation ? { continuation: a.continuation } : {}),
    ...(a.subagentsAllowed !== undefined ? { subagentsAllowed: a.subagentsAllowed } : {}) };
}
export function authorityFingerprint({ issue, review, contract, execution }) {
  // Parsed values bind execution/publication independently of cosmetic prose.
  // The current CR contract is retained; its display title and set ordering
  // are canonicalized. Retired metadata is removed during contract validation. A YAML contract is already represented by these values.
  const canonicalContract = contract ? Object.fromEntries(Object.entries(contract).map(([key, value]) => [key,
    ['finding_ids', 'required_validation'].includes(key) ? sortedSet(value)
      : key === 'remediation_thread_title' ? displayText(value) : value]).sort(([a], [b]) => a.localeCompare(b))) : null;
  const reviewInstructions = review?.body.replace(/```ya?ml\s*\n([\s\S]*?)\n```/gi,
    (block, content) => /(^|\n)\s*schema_version\s*:/m.test(content) ? '' : block);
  return digest({ execution: executableAuthority(execution), issue: prose(issue.body),
    review: review ? { id: review.id, head: review.commit_id, body: prose(reviewInstructions) } : null,
    contract: canonicalContract });
}
export function linkedIssue(body) {
  const ids = taskReferences(body, REPOSITORY);
  if (ids.length !== 1) fail('CANONICAL_ISSUE_AMBIGUOUS');
  return ids[0];
}
export function assertPr(pr, number) {
  if (pr?.number !== number || pr.state !== 'open' || pr.merged || pr.base?.ref !== CONSUMER.baseBranch
    || pr.base?.repo?.full_name !== REPOSITORY || pr.head?.repo?.full_name !== REPOSITORY
    || !exactSha(pr.head?.sha) || !exactSha(pr.base?.sha)) fail('PR_NOT_ADMITTED');
  branchName(pr.head.ref);
}
export async function readAuthority(api, target, number, { targetBase, step, streamlined = false, route, runId, lineage, snapshot, previousRecord, resolution, publicationTarget } = {}) {
  const pr = target === 'pull_request' ? await api.get(`/pulls/${number}`) : null;
  if (pr) assertPr(pr, number);
  const issueNumber = pr ? linkedIssue(pr.body) : number;
  const issue = await api.get(`/issues/${issueNumber}`);
  if (issue.state !== 'open' || issue.user?.login !== OWNER || issue.pull_request) fail('ISSUE_NOT_ADMITTED');
  const nativeAdmission = streamlined && authorityMode(issue.body) === 'github-native-v1';
  step = launchStep(step);
  if (!nativeAdmission) { assertStep(issue.labels, step); if (pr) assertStep(pr.labels, step); }
  const typed = await readTaskAuthority(api, issue, pr, step, nativeAdmission ? {
    streamlined: true, currentProtocol: !snapshot, route, purpose: resolution?.purpose ?? snapshot?.purpose ?? issue.title?.replace(/^Task\s+#?\d+\s*[-–—:·|]+\s*/i, '') ?? `Task ${issueNumber}`,
    projectDefaults: { model: CONSUMER.defaultProfile.cliModelId, effort: CONSUMER.defaultProfile.effort,
      subagents: true, validation: [...NATIVE_VALIDATIONS] },
    startingState: { branch: `${CONSUMER.taskBranchPrefix}task-${issueNumber}`, base_sha: targetBase,
      starting_head: targetBase, existing_pr: null }, pullRequest: pr?.number,
    ...(snapshot ? { admittedAuthority: snapshot.authority, publicationTarget } : {}),
    ...(resolution ? { projectDefaults: resolution.project_defaults, startingState: resolution.starting_state } : {}),
  } : {});
  if (typed) {
    const semantic = typed.request;
    if (snapshot && ['purpose', 'scope', 'model', 'effort', 'subagents', 'validation', 'boundaries',
      'issue_closure_policy', 'continuation'].some(field => canonicalAuthorityJson(snapshot[field])
        !== canonicalAuthorityJson(typed.originalAuthority.request[field]))) fail('AUTHORITY_CHANGED');
    if (nativeAdmission && !pr && semantic.kind === 'change-request') fail('AUTHORITY_SOURCE_TARGET_MISMATCH');
    let continuationState;
    const priorCr = previousRecord?.envelope;
    const retainedCrProgress = pr && priorCr?.target === 'pull_request' && priorCr.number === pr.number
      && priorCr.reviewId === typed.reference.id
      && (previousRecord.publishedHead ?? previousRecord.outcome?.head ?? priorCr.startHead) !== semantic.starting_head;
    if (nativeAdmission && pr && !snapshot && (pr.head.sha !== semantic.starting_head || retainedCrProgress)) {
      continuationState = await blockedCrContinuation(api, { typed, pr, step, lineage, previousRecord, targetBase });
    }
    const priorAuthority = previousRecord?.envelope?.request?.authority;
    const newStartingPin = typed.decisions?.some(item => ['branch', 'base_sha', 'starting_head', 'existing_pr']
      .some(field => Object.hasOwn(item.decision.amendments, field))
      && !priorAuthority?.decisions.some(reference => canonicalAuthorityJson(reference) === canonicalAuthorityJson(item.reference)))
      || typed.compatibilityRequest && previousRecord && canonicalAuthorityJson(typed.compatibilityRequest.reference)
        !== canonicalAuthorityJson(priorAuthority?.compatibility_request ?? previousRecord.envelope.requestReference);
    if (nativeAdmission && !pr && !snapshot && !newStartingPin && previousRecord?.envelope?.branch === semantic.branch) {
      const previous = previousRecord.envelope;
      const retainedHead = previousRecord.publishedHead ?? previousRecord.outcome?.head;
      if (exactSha(retainedHead) && retainedHead !== semantic.base_sha) {
        const refs = await api.get(`/git/matching-refs/heads/${semantic.branch}`);
        const matches = Array.isArray(refs) ? refs.filter(ref => ref.ref === `refs/heads/${semantic.branch}`) : [];
        if (matches.length !== 1 || matches[0].object?.sha !== retainedHead) fail('STARTING_STATE_MISMATCH');
        const existing = await findCurrentIssuePullRequest(api, { issueNumber, branch: semantic.branch,
          continuation: { head: retainedHead } }, previousRecord.prNumber ?? null);
        if (existing && existing.head.sha !== retainedHead) fail('STARTING_STATE_MISMATCH');
        continuationState = { branch: semantic.branch, base_sha: semantic.base_sha,
          starting_head: retainedHead, existing_pr: existing?.number ?? null };
      }
    }
    const q = snapshot ? validateAdmissionSnapshot(snapshot, { step, route, attempt: `run-${runId}` })
      : nativeAdmission ? createAdmissionSnapshot(typed, { step, route, runId, attempt: `run-${runId}`, lineage,
        ...continuationState }) : semantic;
    const noSource = q.route === 'manual' && q.branch === null && q.base_sha === null && q.starting_head === null;
    if (!noSource && (!q.branch || !exactSha(q.base_sha) || !exactSha(q.starting_head))) fail('AUTHORITY_STARTING_STATE_INVALID');
    if (q.branch) branchName(q.branch);
    if (pr && pr.head.ref !== q.branch) fail('STARTING_STATE_MISMATCH');
    const continuation = !pr && (q.existing_pr !== null || q.starting_head !== q.base_sha)
      ? { head: q.starting_head, pullRequest: q.existing_pr } : null;
    const thread = `Task ${issueNumber} — Step ${q.step} — ${semantic.kind === 'change-request' ? `${semantic.change_request_id} — ` : ''}${q.purpose}`;
    const execution = { issue, ...(pr ? { pr, review: { ...typed.record, commit_id: semantic.reviewed_head_sha } } : {}),
      issueNumber, branch: q.branch, historicalBase: q.base_sha, startHead: q.starting_head,
      profile: { cliModelId: q.model, effort: q.effort }, subagentsAllowed: q.subagents,
      thread, title: `Task ${issueNumber} · Step ${q.step}${semantic.kind === 'change-request' ? ` · ${semantic.change_request_id}` : ''} · ${q.purpose}`,
      // Typed acceptance closes the Issue explicitly after task_complete and
      // remaining-work checks. A PR closing keyword would bypass those checks.
      closure: `Related to #${issueNumber}`,
      input: typed.input, validation: q.validation, request: q, requestReference: typed.reference,
      authorityDigest: typed.authorityDigest,
      ...(snapshot ? { currentRequest: semantic, authorityDrift: typed.authorityDrift,
        originalRequest: typed.originalAuthority.request } : {}),
      admission: { kind: nativeAdmission ? 'github-native-admission' : 'github-native-request', warnings: typed.warnings.map(code => ({ code, field: 'closure', resolved: 'keep-open' })) },
      ...(continuation ? { continuation } : {}) };
    if (continuation?.pullRequest) {
      execution.pr = await findCurrentIssuePullRequest(api, execution, continuation.pullRequest);
      if (!nativeAdmission) { assertStep(execution.pr.labels, step); assertPrStepTitle(execution.pr, issueNumber, step); }
    }
    if (!nativeAdmission && execution.pr && execution.pr.title !== projectedRequestTitle(q)) fail('AUTHORITY_TITLE_PROJECTION_MISMATCH');
    return execution;
  }
  if (!pr) {
    const a = parseIssueAuthority(issue.body, { issueNumber, repository: REPOSITORY, issueTitle: issue.title, targetBaseSha: targetBase, step });
    const execution = { issue, issueNumber, branch: a.branch, historicalBase: a.baseSha, startHead: a.continuation?.head ?? a.baseSha,
      profile: a.profile, thread: a.threadTitle, title: a.prTitle,
      closure: a.closingReference, input: issue.body, validation: ['diff-check', 'secret-scan'],
      subagentsAllowed: a.subagentsAllowed, admission: a.admission,
      warnings: a.warnings, resolutions: a.resolutions,
      ...(a.continuation ? { continuation: a.continuation } : {}) };
    if (a.continuation?.pullRequest) {
      execution.pr = await findCurrentIssuePullRequest(api, execution, a.continuation.pullRequest);
      assertStep(execution.pr.labels, step);
      assertPrStepTitle(execution.pr, issueNumber, step);
    }
    return { ...execution, authorityDigest: authorityFingerprint({ issue, execution }) };
  }
  const review = currentReview(await api.list(`/pulls/${number}/reviews`));
  const contract = validateRemediationContract(extractRemediationContract(review.body, { canonicalIssueBody: issue.body }),
    { pullRequest: number, reviewedHeadSha: review.commit_id }, review.body);
  if (changeRequestStep(contract) !== step) fail('CHANGE_REQUEST_STEP_MISMATCH');
  const execution = { issue, pr, review, contract, issueNumber, branch: pr.head.ref, historicalBase: pr.base.sha,
    startHead: review.commit_id,
    profile: { cliModelId: contract.codex_model, effort: contract.codex_effort },
    // Task is the linked Issue; its current Step must match the current CR.
    thread: remediationThreadTitle(contract.remediation_thread_title, issueNumber, step),
    subagentsAllowed: contract.subagents_allowed, title: pr.title, closure: /\b(?:Closes|Fixes|Resolves)\s+#/i.test(pr.body) ? `Closes #${issueNumber}` : `Related to #${issueNumber}`,
    input: `${issue.body}\n\nNative Change Request #${review.id}:\n${review.body}`, validation: contract.required_validation };
  return { ...execution, authorityDigest: authorityFingerprint({ issue, review, contract, execution }) };
}
export async function admitEnvelope(api, { runId, target, number, route, issueNumber, step, transport }, { streamlined = false, nextStep, lineage, previousRecord } = {}) {
  if (!positive(number) || !positive(runId) || !['issue', 'pull_request'].includes(target)
    || !['auto', 'manual'].includes(route)) fail('ROUTE_INVALID');
  if (transport !== undefined && transport !== 'label') fail('ROUTE_INVALID');
  if (transport === 'label') {
    // Resolve Task through the linked canonical Issue after target binding.
    issueNumber = target === 'issue' ? number : null;
  } else {
    if (!positive(issueNumber) || (target === 'issue' && number !== issueNumber)) fail('ROUTE_INVALID');
    if (!streamlined || step !== null && step !== undefined) step = launchStep(step);
  }
  const run = await api.getRun(runId);
  const eventName = transport === 'label' ? target === 'issue' ? 'issues' : 'pull_request_target' : 'workflow_dispatch';
  if (run.id !== runId || run.repository?.full_name !== REPOSITORY || run.actor?.login !== OWNER
    || (run.triggering_actor && run.triggering_actor.login !== OWNER) || run.status !== 'in_progress'
    || run.path !== CONSUMER.routingWorkflow || run.event !== eventName
    || (eventName !== 'pull_request_target' && run.head_branch !== CONSUMER.baseBranch) || run.run_attempt !== 1
    || (transport !== 'label' && run.display_title !== dispatchRunName({ route, issueNumber, step, target, number }))) fail('OWNER_RUN_NOT_ADMITTED');
  let subject, command;
  if (transport === 'label') {
    // Establish the native target before any domain-block Outcome may be
    // published. A caller cannot borrow another target's owner run and point
    // an admission error at an unrelated Issue/PR with invalid authority.
    subject = await api.get(target === 'issue' ? `/issues/${number}` : `/pulls/${number}`);
    if (subject.number !== number || !labelRunCommandMatches(run.display_title, { route, target, number })
      || (target === 'issue' && subject.pull_request)
      || (target === 'pull_request' && (subject.base?.repo?.full_name !== REPOSITORY
        || subject.head?.repo?.full_name !== REPOSITORY || ![CONSUMER.baseBranch, subject.head.ref].includes(run.head_branch)))) fail('OWNER_RUN_NOT_ADMITTED');
    // Unsafe/unbound/stale commands throw outside the domain-result boundary:
    // they authorize neither consumption nor an Outcome on this target.
    const event = await readReadyEvent(api, { number, route, run, subject, rejectAmbiguous: streamlined });
    command = { transport, readyEventId: event.id, readyEventAt: event.created_at,
      readyLabel: event.label.name, runName: run.display_title };
  }
  const attemptId = `run-${runId}`;
  let targetBase, nativeAdmission = false;
  try {
    const admissionIssue = await api.get(`/issues/${target === 'issue' ? number : linkedIssue(subject?.body ?? (await api.get(`/pulls/${number}`)).body)}`);
    if (command) issueNumber = target === 'issue' ? number : linkedIssue(subject.body);
    nativeAdmission = streamlined && authorityMode(admissionIssue.body) === 'github-native-v1';
    // The installed protocol capability selects new execution semantics. A
    // missing charter marker cannot downgrade a current Writer to legacy.
    // Retained attempt replay returns its stored envelope before this path.
    if (streamlined && !nativeAdmission) requireCurrentProtocol();
    if (nativeAdmission) step = launchStep(nextStep);
    if (command) {
      if (!nativeAdmission) {
        const liveStep = currentStep(subject.labels); step = launchStep(step);
        if (liveStep !== step) fail('STEP_LABEL_MISMATCH');
        if (target === 'pull_request') assertPrStepTitle(subject, issueNumber, step);
        if (!labelRunMatches(run.display_title, { route, target, number }, subject)) fail('STEP_DISPLAY_MISMATCH');
      }
    }
    targetBase = (await api.get(`/git/ref/heads/${CONSUMER.baseBranch}`)).object.sha;
    if (!exactSha(targetBase)) fail('TARGET_BASE_INVALID');
    const a = await readAuthority(api, target, number, { targetBase, step, streamlined: nativeAdmission, route, runId, lineage, previousRecord });
    if (a.request && a.request.route !== route) fail('AUTHORITY_ROUTE_MISMATCH');
    if (a.issueNumber !== issueNumber) fail('CANONICAL_ISSUE_AMBIGUOUS');
    if (transport === 'label' && !nativeAdmission) {
      const subject = target === 'issue' ? a.issue : a.pr;
      if (a.pr) assertPrStepTitle(a.pr, issueNumber, step);
      if (!labelRunMatches(run.display_title, { route, target, number }, subject)) fail('STEP_DISPLAY_MISMATCH');
    }
    if (!a.validation.length || a.validation.some(name => !NATIVE_VALIDATIONS.has(name))) fail('REQUIRED_VALIDATION_UNSUPPORTED');
    const noSource = a.request?.route === 'manual' && a.branch === null;
    if (!noSource && target === 'issue' && !a.continuation) {
      if (nativeAdmission) {
        await verifyPublishedBase(api, a.historicalBase, targetBase);
        if (a.startHead !== a.historicalBase) await verifyPublishedBase(api, a.startHead, targetBase);
      } else if (targetBase !== a.historicalBase) fail('STARTING_STATE_MISMATCH');
    }
    if (a.pr && a.pr.head.sha !== a.startHead) fail('STARTING_STATE_MISMATCH');
    if (target === 'issue' && !noSource) {
      const refs = await api.get(`/git/matching-refs/heads/${a.branch}`);
      if (!Array.isArray(refs)) fail('STARTING_STATE_MISMATCH');
      const exact = refs.filter(r => r.ref === `refs/heads/${a.branch}`);
      if (a.continuation) {
        if (!exact.length) fail('TASK_BRANCH_MISSING');
        if (exact.length !== 1 || exact[0].object?.sha !== a.startHead) fail('STARTING_STATE_MISMATCH');
        if (!a.continuation.pullRequest && await findCurrentIssuePullRequest(api, a)) fail('PR_AUTHORITY_CHANGED');
      } else if (exact.length) fail('TASK_BRANCH_ALREADY_EXISTS');
    }
    return { version: VERSION, repository: REPOSITORY, consumerDigest: CONSUMER_DIGEST, attemptId, runId,
      target, number, issueNumber: a.issueNumber, route, step,
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
    // The event identity is known, but executable authority is not. Preserve
    // only safe structured blocker data; never manufacture a branch,
    // profile, or reviewed/remediation head for the terminal Outcome.
    return { blocked: true, version: VERSION, repository: REPOSITORY, consumerDigest: CONSUMER_DIGEST, attemptId, runId,
      target, number, issueNumber, route, step: nativeAdmission ? null : step, targetBase, ...command,
      block: { code: /^[A-Z][A-Z0-9_]{0,79}$/.test(error.code ?? '') ? error.code : 'ADMISSION_BLOCKED',
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

async function readReadyEvent(api, { number, route, run, subject, rejectAmbiguous = false }) {
  const label = route === 'auto' ? READY_LABELS[0] : READY_LABELS[1];
  const ready = labelNames(subject.labels).filter(name => READY_LABELS.includes(name));
  if (ready.length !== 1 || ready[0] !== label) fail('READY_LABEL_AMBIGUOUS');
  const events = await readyTransitions(api, number);
  const event = events.at(-1);
  const age = Date.parse(run.created_at) - Date.parse(event?.created_at);
  // Bind the live native command to this first run, not a surviving old label.
  if (!positive(event?.id) || event.event !== 'labeled' || event.label.name !== label
    || event.actor?.login !== OWNER || event.actor?.type !== 'User'
    || !Number.isFinite(age) || age < 0 || age > 120000) fail('READY_EVENT_STALE');
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
  if (subject.number !== e.number) fail('OWNER_RUN_NOT_ADMITTED');
  const event = await readReadyEvent(api, { number: e.number, route: e.route,
    run: await api.getRun(e.runId), subject, rejectAmbiguous: e.request?.kind === 'admission' });
  if (event.id !== e.readyEventId || event.created_at !== e.readyEventAt) fail('READY_EVENT_STALE');
}
export async function revalidateAuthority(api, e, { reporting = false, handoff = false, verifyStartingBase = false, publicationTarget } = {}) {
  if (e.request?.kind === 'admission') validateEnvelope(e);
  // A missing authoring base was resolved once, before worker mutation. Main
  // advancement cannot silently rebind that immutable admission resolution.
  const a = await readAuthority(api, e.target, e.number, { targetBase: e.targetBase, step: e.step,
    streamlined: e.request?.kind === 'admission', route: e.route, runId: e.runId,
    lineage: e.request?.lineage, snapshot: e.request?.kind === 'admission' ? e.request : undefined,
    resolution: e.request?.authority_resolution, publicationTarget });
  if ((e.request?.kind !== 'admission' && a.authorityDigest !== e.authorityDigest) || a.branch !== e.branch || a.startHead !== e.startHead
    || a.issueNumber !== e.issueNumber || (a.review?.id ?? null) !== e.reviewId) fail('AUTHORITY_CHANGED');
  if (a.request && a.request.route !== e.route) fail('AUTHORITY_CHANGED');
  if (e.request?.kind === 'admission') {
    // Source publication and lifecycle effects stay inside the admitted/live
    // intersection. Do not interpret permission prose or execute new scope.
    // Reporting remains possible after a revoked or ambiguous permission.
    const old = a.originalRequest; const current = a.currentRequest;
    if (!reporting && ['branch', 'base_sha', 'starting_head', 'existing_pr'].some(field =>
      canonicalAuthorityJson(old[field]) !== canonicalAuthorityJson(current[field]))) fail('AUTHORITY_CHANGED');
    // Preparing an already published result for independent review neither
    // executes amended scope nor accepts it. Keep exact artifact pins above;
    // current review/approval constraints still govern independent acceptance.
    if (!reporting && !handoff && (old.scope.some(value => !current.scope.includes(value))
      || current.boundaries.some(value => !old.boundaries.includes(value))
      || current.validation.some(value => !old.validation.includes(value))
      || current.continuation.hold && !old.continuation.hold)) fail('AUTHORITY_CHANGED');
  }
  // This starting-state observation belongs only to active execution actions.
  // Exact retained result/recovery authority does not acquire a new main gate.
  if (verifyStartingBase && !reporting && e.request?.kind === 'admission' && e.target === 'issue' && !e.continuation && e.branch !== null) {
    const currentBase = (await api.get(`/git/ref/heads/${CONSUMER.baseBranch}`)).object?.sha;
    await verifyPublishedBase(api, e.historicalBase, currentBase);
    if (e.startHead !== e.historicalBase) await verifyPublishedBase(api, e.startHead, currentBase);
  }
  return a;
}

export async function revalidateIntegrationBase(api, e) {
  if ((await api.get(`/git/ref/heads/${CONSUMER.baseBranch}`)).object?.sha !== e.targetBase) fail('STARTING_STATE_MISMATCH');
}

// GitHub comparison binds two exact repository commits, not a moving branch.
// An immutable admitted base may precede current main, but never diverge from
// it or be replaced by an unverified worker-supplied object.
export async function verifyPublishedBase(api, base, current) {
  if (!exactSha(base) || !exactSha(current)) fail('STARTING_STATE_MISMATCH');
  if (base === current) return;
  let comparison;
  try { comparison = await api.get(`/compare/${base}...${current}?per_page=1`); }
  catch (error) { if (error.status === 404) fail('STARTING_STATE_MISMATCH'); throw error; }
  if (comparison.status !== 'ahead' || comparison.base_commit?.sha !== base
    || comparison.merge_base_commit?.sha !== base) fail('STARTING_STATE_MISMATCH');
}
