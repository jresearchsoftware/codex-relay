import { pathToFileURL } from 'node:url';
import { createGithubApi } from '../../controller/src/github-api.mjs';
import { OWNER, REVIEWER, fail, positive } from '../../controller/src/execution-contract.mjs';
import { assertPr, linkedIssue } from '../../controller/src/live-authority.mjs';
import { currentStep, labelNames, assertStep, changeRequestStep } from '../../controller/src/step-metadata.mjs';
import { remediationThreadTitle } from '../../controller/src/launch-metadata.mjs';
import { boundedThreadCorrelationIdentity } from '../../controller/src/run-name.mjs';
import { extractRemediationContract, validateRemediationContract } from './contracts.mjs';

async function owner(api) {
  const actor = await api.viewer();
  if (actor?.login !== OWNER || actor.type !== 'User') fail('OWNER_METADATA_ACTOR_REQUIRED');
}
async function task(api, number) {
  if (!positive(number)) fail('ROUTE_INVALID');
  const pr = await api.get(`/pulls/${number}`); assertPr(pr, number);
  const issueNumber = linkedIssue(pr.body);
  const issue = await api.get(`/issues/${issueNumber}`);
  if (issue.state !== 'open' || issue.user?.login !== OWNER || issue.pull_request) fail('ISSUE_NOT_ADMITTED');
  return { pr, issue, issueNumber };
}

// Ordinary owner orchestration calls this while authoring a NEW executable CR.
// The only arithmetic is N+1 from the two current, synchronized native labels.
export async function prepareReviewStep(api, number) {
  await owner(api);
  const { pr, issue, issueNumber } = await task(api, number);
  const step = currentStep(issue.labels); assertStep(pr.labels, step);
  if (!positive(step + 1)) fail('CHANGE_REQUEST_STEP_INVALID');
  return { issueNumber, pullRequest: number, reviewedHead: pr.head.sha, currentStep: step, step: step + 1 };
}

async function published(api, number, reviewId) {
  const state = await task(api, number);
  const review = (await api.list(`/pulls/${number}/reviews`))
    .filter(r => r.user?.login === REVIEWER && ['CHANGES_REQUESTED', 'APPROVED', 'DISMISSED'].includes(r.state))
    .sort((a, b) => Number(a.id) - Number(b.id)).at(-1);
  if (!positive(reviewId) || review?.id !== reviewId || review.commit_id !== state.pr.head.sha
    || !['CHANGES_REQUESTED', 'APPROVED'].includes(review.state)) fail('CURRENT_CHANGE_REQUEST_MISSING');
  return { ...state, review };
}

// Called only AFTER successful reserved native Reviewer publication. This
// function never publishes a review, launches work, or uses Reviewer credentials.
// Repeat the same publication tuple to repair partial metadata transport only.
export async function synchronizeReviewStep(api, number, reviewId) {
  await owner(api);
  const first = await published(api, number, reviewId);
  if (first.review.state === 'APPROVED') return { status: 'unchanged', step: currentStep(first.issue.labels) };
  const contract = validateRemediationContract(extractRemediationContract(first.review.body, { canonicalIssueBody: first.issue.body }),
    { pullRequest: number, reviewedHeadSha: first.pr.head.sha });
  const next = changeRequestStep(contract);
  if (next <= 1) fail('CHANGE_REQUEST_STEP_INVALID');
  function validate(state) {
    if (state.issueNumber !== first.issueNumber || state.pr.head.sha !== first.pr.head.sha
      || state.pr.head.ref !== first.pr.head.ref || state.review.body !== first.review.body
      || state.review.state !== first.review.state) fail('AUTHORITY_CHANGED');
    for (const subject of [state.issue, state.pr]) {
      if (![next - 1, next].includes(currentStep(subject.labels))) fail('STEP_LABEL_MISMATCH');
    }
  }
  validate(first);
  await api.ensureStepLabel(next);
  const title = boundedThreadCorrelationIdentity(remediationThreadTitle(contract.remediation_thread_title, first.issueNumber, next));
  for (const isPr of [false, true]) {
    const state = await published(api, number, reviewId); validate(state);
    const subject = isPr ? state.pr : state.issue;
    if (currentStep(subject.labels) !== next) {
      // One native replacement per target: never two current Step labels, and
      // preserve unrelated labels. GitHub has no cross-Issue/PR transaction;
      // a partial failure is visible and blocks launch until this CR is synced.
      const labels = labelNames(subject.labels).filter(name => name !== `step-${next - 1}`);
      await api.patch(`/issues/${isPr ? number : state.issueNumber}`, { labels: [...labels, `step-${next}`] });
    }
  }
  const beforeTitle = await published(api, number, reviewId); validate(beforeTitle);
  if (beforeTitle.pr.title !== title) await api.patch(`/pulls/${number}`, { title });
  const after = await published(api, number, reviewId); validate(after);
  assertStep(after.issue.labels, next); assertStep(after.pr.labels, next);
  if (after.pr.title !== title) fail('STEP_DISPLAY_MISMATCH');
  return { status: 'synchronized', issueNumber: after.issueNumber, pullRequest: number, reviewId, step: next };
}

// Optional native Linux adapter for the SAME owner-authenticated GitHub path.
// ChatGPT may perform the documented native reads/label/title updates directly;
// this adapter does not add a required human action or another launch surface.
export async function main() {
  let text = '';
  for await (const chunk of process.stdin) {
    text += chunk;
    if (Buffer.byteLength(text) > 2048) fail('REQUEST_TOO_LARGE');
  }
  const request = JSON.parse(text);
  const token = process.env.GITHUB_TOKEN;
  if (!token) fail('OWNER_METADATA_ACTOR_REQUIRED');
  const api = createGithubApi({ token });
  return request.operation === 'prepare' ? prepareReviewStep(api, request.pullRequest)
    : request.operation === 'synchronize' ? synchronizeReviewStep(api, request.pullRequest, request.reviewId)
      : fail('ROUTE_INVALID');
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().then(value => process.stdout.write(JSON.stringify(value) + '\n')).catch(error => {
    process.stderr.write(JSON.stringify({ status: 'blocked', code: /^[A-Z_]+$/.test(error.code ?? '') ? error.code : 'METADATA_SYNC_FAILED' }) + '\n');
    process.exitCode = 1;
  });
}
