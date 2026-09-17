import { CONSUMER, CONSUMER_DIGEST } from '../../consumer/consumer.mjs';
import { parseIssueAuthority } from '../../runtime/src/issue-authority.mjs';
import { extractRemediationContract, validateRemediationContract } from '../../contracts/src/contracts.mjs';
import { REPOSITORY, OWNER, REVIEWER, VERSION, fail, digest, branchName, exactSha, positive, isAdmissionDomainBlock, NATIVE_VALIDATIONS } from './execution-contract.mjs';
import { dispatchRunName, labelRunCommandMatches, labelRunMatches, launchStep, remediationThreadTitle } from './launch-metadata.mjs';
import { assertStep, currentStep, changeRequestStep, assertPrStepTitle, labelNames, READY_LABELS } from './step-metadata.mjs';

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
  const ids = [...new Set([...String(body).matchAll(/\b(?:Closes|Fixes|Resolves|Related to)\s+#([1-9][0-9]*)\b/gi)].map(m => Number(m[1])))];
  if (ids.length !== 1) fail('CANONICAL_ISSUE_AMBIGUOUS');
  return ids[0];
}
export function assertPr(pr, number) {
  if (pr?.number !== number || pr.state !== 'open' || pr.merged || pr.base?.ref !== CONSUMER.baseBranch
    || pr.base?.repo?.full_name !== REPOSITORY || pr.head?.repo?.full_name !== REPOSITORY
    || !exactSha(pr.head?.sha) || !exactSha(pr.base?.sha)) fail('PR_NOT_ADMITTED');
  branchName(pr.head.ref);
}
export async function readAuthority(api, target, number, { targetBase, step } = {}) {
  step = launchStep(step);
  const pr = target === 'pull_request' ? await api.get(`/pulls/${number}`) : null;
  if (pr) assertPr(pr, number);
  const issueNumber = pr ? linkedIssue(pr.body) : number;
  const issue = await api.get(`/issues/${issueNumber}`);
  if (issue.state !== 'open' || issue.user?.login !== OWNER || issue.pull_request) fail('ISSUE_NOT_ADMITTED');
  assertStep(issue.labels, step);
  if (pr) assertStep(pr.labels, step);
  if (!pr) {
    const a = parseIssueAuthority(issue.body, { issueNumber, repository: REPOSITORY, issueTitle: issue.title, targetBaseSha: targetBase, step });
    const execution = { issue, issueNumber, branch: a.branch, historicalBase: a.baseSha, startHead: a.baseSha,
      profile: a.profile, thread: a.threadTitle, title: a.prTitle,
      closure: a.closingReference, input: issue.body, validation: ['diff-check', 'secret-scan'],
      subagentsAllowed: a.subagentsAllowed, admission: a.admission,
      warnings: a.warnings, resolutions: a.resolutions };
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
export async function admitEnvelope(api, { runId, target, number, route, issueNumber, step, transport }) {
  if (!positive(number) || !positive(runId) || !['issue', 'pull_request'].includes(target)
    || !['auto', 'manual'].includes(route)) fail('ROUTE_INVALID');
  if (transport !== undefined && transport !== 'label') fail('ROUTE_INVALID');
  if (transport === 'label') {
    // Resolve Task through the linked canonical Issue after target binding.
    issueNumber = target === 'issue' ? number : null;
  } else {
    if (!positive(issueNumber) || (target === 'issue' && number !== issueNumber)) fail('ROUTE_INVALID');
    step = launchStep(step);
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
    const event = await readReadyEvent(api, { number, route, run, subject });
    command = { transport, readyEventId: event.id, readyEventAt: event.created_at,
      readyLabel: event.label.name, runName: run.display_title };
  }
  const attemptId = `run-${runId}`;
  let targetBase;
  try {
    if (command) {
      issueNumber = target === 'issue' ? number : linkedIssue(subject.body);
      const liveStep = currentStep(subject.labels);
      step = launchStep(step);
      if (liveStep !== step) fail('STEP_LABEL_MISMATCH');
      if (target === 'pull_request') assertPrStepTitle(subject, issueNumber, step);
      if (!labelRunMatches(run.display_title, { route, target, number }, subject)) fail('STEP_DISPLAY_MISMATCH');
    }
    targetBase = (await api.get(`/git/ref/heads/${CONSUMER.baseBranch}`)).object.sha;
    if (!exactSha(targetBase)) fail('TARGET_BASE_INVALID');
    const a = await readAuthority(api, target, number, { targetBase, step });
    if (a.issueNumber !== issueNumber) fail('CANONICAL_ISSUE_AMBIGUOUS');
    if (transport === 'label') {
      const subject = a.pr ?? a.issue;
      if (a.pr) assertPrStepTitle(a.pr, issueNumber, step);
      if (!labelRunMatches(run.display_title, { route, target, number }, subject)) fail('STEP_DISPLAY_MISMATCH');
    }
    if (!a.validation.length || a.validation.some(name => !NATIVE_VALIDATIONS.has(name))) fail('REQUIRED_VALIDATION_UNSUPPORTED');
    if ((target === 'issue' && targetBase !== a.startHead) || (a.pr && (a.pr.head.sha !== a.startHead || a.pr.draft))) fail('STARTING_STATE_MISMATCH');
    if (target === 'issue') {
      const refs = await api.get(`/git/matching-refs/heads/${a.branch}`);
      if (!Array.isArray(refs) || refs.some(r => r.ref === `refs/heads/${a.branch}`)) fail('TASK_BRANCH_ALREADY_EXISTS');
    }
    return { version: VERSION, repository: REPOSITORY, consumerDigest: CONSUMER_DIGEST, attemptId, runId,
      target, number, issueNumber: a.issueNumber, route, step,
      ...command,
      branch: a.branch, startHead: a.startHead, historicalBase: a.historicalBase, targetBase,
      reviewId: a.review?.id ?? null, authorityDigest: a.authorityDigest,
      profile: a.profile, thread: a.thread, title: a.title, closure: a.closure,
      input: a.input, validation: a.validation, subagentsAllowed: a.subagentsAllowed,
      admission: a.admission, warnings: a.warnings, resolutions: a.resolutions };
  } catch (error) {
    if (!isAdmissionDomainBlock(error)) throw error;
    // The event identity is known, but executable authority is not. Preserve
    // only safe structured blocker data; never manufacture a branch,
    // profile, or reviewed/remediation head for the terminal Outcome.
    return { blocked: true, version: VERSION, repository: REPOSITORY, consumerDigest: CONSUMER_DIGEST, attemptId, runId,
      target, number, issueNumber, route, step, targetBase, ...command,
      block: { code: /^[A-Z][A-Z0-9_]{0,79}$/.test(error.code ?? '') ? error.code : 'ADMISSION_BLOCKED',
        ...(typeof error.details?.field === 'string' ? { field: error.details.field } : {}) } };
  }
}

async function readReadyEvent(api, { number, route, run, subject }) {
  const label = route === 'auto' ? READY_LABELS[0] : READY_LABELS[1];
  const ready = labelNames(subject.labels).filter(name => READY_LABELS.includes(name));
  if (ready.length !== 1 || ready[0] !== label) fail('READY_LABEL_AMBIGUOUS');
  const events = (await api.list(`/issues/${number}/events`))
    .filter(e => ['labeled', 'unlabeled'].includes(e.event) && READY_LABELS.includes(e.label?.name));
  const event = events.sort((a, b) => Number(a.id) - Number(b.id)).at(-1);
  const age = Date.parse(run.created_at) - Date.parse(event?.created_at);
  // Bind the live native command to this first run, not a surviving old label.
  if (!positive(event?.id) || event.event !== 'labeled' || event.label.name !== label
    || event.actor?.login !== OWNER || event.actor?.type !== 'User'
    || !Number.isFinite(age) || age < 0 || age > 120000) fail('READY_EVENT_STALE');
  return event;
}

export async function revalidateReadyEvent(api, e) {
  // Check immediately before reservation/consumption, including blocked
  // admission. Never remove a replacement command created during API reads.
  const subject = await api.get(`/issues/${e.number}`);
  if (subject.number !== e.number) fail('OWNER_RUN_NOT_ADMITTED');
  const event = await readReadyEvent(api, { number: e.number, route: e.route,
    run: await api.getRun(e.runId), subject });
  if (event.id !== e.readyEventId || event.created_at !== e.readyEventAt) fail('READY_EVENT_STALE');
}
export async function revalidateAuthority(api, e) {
  // A missing authoring base was resolved once, before worker mutation. Main
  // advancement cannot silently rebind that immutable admission resolution.
  const a = await readAuthority(api, e.target, e.number, { targetBase: e.targetBase, step: e.step });
  if (a.authorityDigest !== e.authorityDigest || a.branch !== e.branch || a.startHead !== e.startHead
    || a.issueNumber !== e.issueNumber || (a.review?.id ?? null) !== e.reviewId) fail('AUTHORITY_CHANGED');
  return a;
}

export async function revalidateIntegrationBase(api, e) {
  if ((await api.get(`/git/ref/heads/${CONSUMER.baseBranch}`)).object?.sha !== e.targetBase) fail('STARTING_STATE_MISMATCH');
}
