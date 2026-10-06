import { pathToFileURL } from 'node:url';
import { createGithubApi } from '../../controller/src/github-api.mjs';
import { OWNER, REVIEWER, fail, positive } from '../../controller/src/execution-contract.mjs';
import { assertPr, linkedIssue } from '../../controller/src/live-authority.mjs';
import { currentStep, labelNames, assertStep, changeRequestStep, reviewStepTitle } from '../../controller/src/step-metadata.mjs';
import { boundedThreadCorrelationIdentity } from '../../controller/src/run-name.mjs';
import { extractRemediationContract, validateRemediationContract } from './contracts.mjs';
import { authorityMode } from './github-authority.mjs';

async function owner(api) {
  const actor = await api.viewer();
  if (actor?.login !== OWNER || actor.type !== 'User') fail('OWNER_METADATA_ACTOR_REQUIRED');
}
async function canonicalTask(api, issueNumber, pullRequest) {
  if (!positive(issueNumber) || (pullRequest !== undefined && !positive(pullRequest))) fail('ROUTE_INVALID');
  const issue = await api.get(`/issues/${issueNumber}`);
  if (issue?.number !== issueNumber || issue.state !== 'open' || issue.user?.login !== OWNER || issue.pull_request) fail('ISSUE_NOT_ADMITTED');
  if (authorityMode(issue.body) !== 'legacy') fail('TYPED_REQUEST_PROJECTION_OWNED_BY_PUBLISHER');
  const pr = pullRequest === undefined ? null : await api.get(`/pulls/${pullRequest}`);
  if (pr) {
    assertPr(pr, pullRequest);
    if (linkedIssue(pr.body) !== issueNumber) fail('CANONICAL_ISSUE_AMBIGUOUS');
  }
  return { issue, pr, issueNumber };
}

// Read-only authoring assistance. Reviewer owns normal post-publication sync.
export async function prepareReviewStep(api, number) {
  await owner(api);
  if (!positive(number)) fail('ROUTE_INVALID');
  const pr = await api.get(`/pulls/${number}`); assertPr(pr, number);
  const state = await canonicalTask(api, linkedIssue(pr.body), number);
  if (state.pr.head.sha !== pr.head.sha || state.pr.body !== pr.body) fail('AUTHORITY_CHANGED');
  const step = currentStep(state.issue.labels); assertStep(state.pr.labels, step);
  if (!positive(step + 1)) fail('CHANGE_REQUEST_STEP_INVALID');
  return { issueNumber: state.issueNumber, pullRequest: number, reviewedHead: pr.head.sha, currentStep: step, step: step + 1 };
}

function strictRequest(request) {
  if (!request || typeof request !== 'object' || Array.isArray(request)) fail('ROUTE_INVALID');
  const allowed = request.operation === 'advance-phase'
    ? ['operation', 'issueNumber', 'currentStep', 'newPhaseAuthorized', 'pullRequest', 'purpose']
    : request.operation === 'keep-step' ? ['operation', 'issueNumber', 'currentStep', 'pullRequest']
      : request.operation === 'prepare' ? ['operation', 'pullRequest']
        : request.operation === 'recover-legacy-review' ? ['operation', 'pullRequest', 'reviewId', 'legacyPublicationRecoveryAuthorized'] : [];
  if (!allowed.length || Object.keys(request).some(key => !allowed.includes(key))) fail('ROUTE_INVALID');
  if (request.operation === 'recover-legacy-review') {
    if (!positive(request.pullRequest) || !positive(request.reviewId)) fail('ROUTE_INVALID');
    if (request.legacyPublicationRecoveryAuthorized !== true) fail('LEGACY_STEP_BINDING_REQUIRED');
    return;
  }
  if (request.operation === 'prepare') {
    if (!positive(request.pullRequest)) fail('ROUTE_INVALID');
    return;
  }
  if (!positive(request.issueNumber) || !positive(request.currentStep)
    || ('pullRequest' in request && !positive(request.pullRequest))) fail('ROUTE_INVALID');
  if (request.operation === 'advance-phase') {
    if (request.newPhaseAuthorized !== true) fail('NEW_PHASE_AUTHORITY_REQUIRED');
    if (!positive(request.currentStep + 1)) fail('CHANGE_REQUEST_STEP_INVALID');
    if ('purpose' in request && (typeof request.purpose !== 'string' || !request.purpose.trim()
      || request.purpose !== request.purpose.trim() || request.purpose !== request.purpose.normalize('NFC')
      || Buffer.byteLength(request.purpose) > 512 || /[\u0000-\u001f\u007f-\u009f]/.test(request.purpose))) fail('STEP_DISPLAY_MISMATCH');
    if (request.pullRequest !== undefined && !request.purpose) fail('STEP_DISPLAY_MISMATCH');
    if (request.pullRequest === undefined && 'purpose' in request) fail('ROUTE_INVALID');
  }
}

// Explicit owner NEW-phase preparation, never an execution or review retry.
// currentStep binds the exact N -> N+1 operation; repeating it can only finish
// that same projection. No review, history, counter or arbitrary metadata input.
export async function prepareOwnerPhase(api, request) {
  strictRequest(request);
  if (!['advance-phase', 'keep-step'].includes(request.operation)) fail('ROUTE_INVALID');
  await owner(api);
  const first = await canonicalTask(api, request.issueNumber, request.pullRequest);
  const next = request.currentStep + (request.operation === 'advance-phase' ? 1 : 0);
  const title = first.pr && request.operation === 'advance-phase'
    ? boundedThreadCorrelationIdentity(`Task ${request.issueNumber} · Step ${next} · ${request.purpose}`) : null;
  function validate(state) {
    if (state.issue.body !== first.issue.body || (state.pr && (state.pr.body !== first.pr.body
      || state.pr.head.sha !== first.pr.head.sha || state.pr.head.ref !== first.pr.head.ref
      || state.pr.base.sha !== first.pr.base.sha
      || ![first.pr.title, title].includes(state.pr.title)))) fail('AUTHORITY_CHANGED');
    for (const subject of [state.issue, state.pr].filter(Boolean)) {
      const step = currentStep(subject.labels);
      if (step !== next && (request.operation !== 'advance-phase' || step !== request.currentStep)) fail('STEP_LABEL_MISMATCH');
    }
  }
  validate(first);
  if (request.operation === 'keep-step') {
    validate(await canonicalTask(api, request.issueNumber, request.pullRequest));
    return { status: 'unchanged', issueNumber: request.issueNumber, ...(first.pr ? { pullRequest: request.pullRequest } : {}), step: next };
  }
  await api.ensureStepLabel(next);
  for (const isPr of first.pr ? [false, true] : [false]) {
    const state = await canonicalTask(api, request.issueNumber, request.pullRequest); validate(state);
    const subject = isPr ? state.pr : state.issue;
    if (currentStep(subject.labels) !== next) {
      const labels = labelNames(subject.labels).filter(name => name !== `step-${request.currentStep}`);
      await api.patch(`/issues/${isPr ? request.pullRequest : request.issueNumber}`, { labels: [...labels, `step-${next}`] });
    }
  }
  const beforeTitle = await canonicalTask(api, request.issueNumber, request.pullRequest); validate(beforeTitle);
  if (beforeTitle.pr && beforeTitle.pr.title !== title) await api.patch(`/pulls/${request.pullRequest}`, { title });
  const after = await canonicalTask(api, request.issueNumber, request.pullRequest); validate(after);
  assertStep(after.issue.labels, next);
  if (after.pr) { assertStep(after.pr.labels, next); if (after.pr.title !== title) fail('STEP_DISPLAY_MISMATCH'); }
  return { status: 'synchronized', issueNumber: request.issueNumber, ...(after.pr ? { pullRequest: request.pullRequest } : {}), step: next };
}

async function legacyPublication(api, number, reviewId) {
  const pr = await api.get(`/pulls/${number}`); assertPr(pr, number);
  const state = await canonicalTask(api, linkedIssue(pr.body), number);
  if (state.pr.head.sha !== pr.head.sha || state.pr.body !== pr.body) fail('AUTHORITY_CHANGED');
  const review = (await api.list(`/pulls/${number}/reviews`))
    .filter(r => r.user?.login === REVIEWER && ['CHANGES_REQUESTED', 'APPROVED', 'DISMISSED'].includes(r.state))
    .sort((a, b) => Number(a.id) - Number(b.id)).at(-1);
  if (review?.id !== reviewId || review.commit_id !== state.pr.head.sha || review.state !== 'CHANGES_REQUESTED') fail('CURRENT_CHANGE_REQUEST_MISSING');
  return { ...state, review };
}

// Exceptional owner-authorized migration of a legacy native publication whose
// old SQLite record cannot anchor normal Reviewer synchronization. Never call
// this for a current Reviewer operation, a new CR or an execution retry.
export async function recoverLegacyReviewStep(api, request) {
  strictRequest(request);
  if (request.operation !== 'recover-legacy-review') fail('ROUTE_INVALID');
  await owner(api);
  const first = await legacyPublication(api, request.pullRequest, request.reviewId);
  const contract = validateRemediationContract(extractRemediationContract(first.review.body, { canonicalIssueBody: first.issue.body }),
    { pullRequest: request.pullRequest, reviewedHeadSha: first.pr.head.sha });
  const next = changeRequestStep(contract);
  if (next <= 1) fail('CHANGE_REQUEST_STEP_INVALID');
  const title = reviewStepTitle(contract, first.issueNumber);
  function validate(state) {
    if (state.issueNumber !== first.issueNumber || state.issue.body !== first.issue.body
      || state.pr.body !== first.pr.body || state.pr.head.sha !== first.pr.head.sha
      || state.pr.head.ref !== first.pr.head.ref || state.pr.base.sha !== first.pr.base.sha
      || ![first.pr.title, title].includes(state.pr.title)
      || state.review.body !== first.review.body) fail('AUTHORITY_CHANGED');
    for (const subject of [state.issue, state.pr]) {
      if (![next - 1, next].includes(currentStep(subject.labels))) fail('STEP_LABEL_MISMATCH');
    }
  }
  validate(first);
  await api.ensureStepLabel(next);
  for (const isPr of [false, true]) {
    const state = await legacyPublication(api, request.pullRequest, request.reviewId); validate(state);
    const subject = isPr ? state.pr : state.issue;
    if (currentStep(subject.labels) !== next) {
      const labels = labelNames(subject.labels).filter(name => name !== `step-${next - 1}`);
      await api.patch(`/issues/${isPr ? request.pullRequest : state.issueNumber}`, { labels: [...labels, `step-${next}`] });
    }
  }
  const beforeTitle = await legacyPublication(api, request.pullRequest, request.reviewId); validate(beforeTitle);
  if (beforeTitle.pr.title !== title) await api.patch(`/pulls/${request.pullRequest}`, { title });
  const after = await legacyPublication(api, request.pullRequest, request.reviewId); validate(after);
  assertStep(after.issue.labels, next); assertStep(after.pr.labels, next);
  if (after.pr.title !== title) fail('STEP_DISPLAY_MISMATCH');
  return { status: 'synchronized', issueNumber: after.issueNumber, pullRequest: request.pullRequest, reviewId: request.reviewId, step: next };
}

export async function executeMetadataRequest(api, request) {
  strictRequest(request);
  return request.operation === 'prepare' ? prepareReviewStep(api, request.pullRequest)
    : request.operation === 'recover-legacy-review' ? recoverLegacyReviewStep(api, request) : prepareOwnerPhase(api, request);
}

// Optional ordinary owner-authenticated Linux adapter; no launch, deployment,
// merge, Issue closure or Reviewer-publication capability.
export async function main() {
  let text = '';
  for await (const chunk of process.stdin) {
    text += chunk;
    if (Buffer.byteLength(text) > 2048) fail('REQUEST_TOO_LARGE');
  }
  const request = JSON.parse(text);
  strictRequest(request);
  const token = process.env.GITHUB_TOKEN;
  if (!token) fail('OWNER_METADATA_ACTOR_REQUIRED');
  return executeMetadataRequest(createGithubApi({ token }), request);
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().then(value => process.stdout.write(JSON.stringify(value) + '\n')).catch(error => {
    process.stderr.write(JSON.stringify({ status: 'blocked', code: /^[A-Z_]+$/.test(error.code ?? '') ? error.code : 'METADATA_SYNC_FAILED' }) + '\n');
    process.exitCode = 1;
  });
}
