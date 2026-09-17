import { CONSUMER } from '../../consumer/consumer.mjs';
import { mkdir, lstat, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { git, collectProgress, REMOTE } from './trusted-git.mjs';
import { fail, validateEnvelope } from './execution-contract.mjs';
import { establishCanonicalCheckout } from './canonical-checkout.mjs';
import { grantSharedCheckoutAccess, runGovernedCodexTask, CODEX_WRITER_IDENTITY, CODEX_REMEDIATION_IDENTITY } from '../../runtime/src/codex-runtime.mjs';

export const WORK_ROOT = CONSUMER.paths.workRoot;
export const checkoutPath = (e, root = WORK_ROOT) => join(root, validateEnvelope(e).attemptId);
export async function prepareCheckout(e, { root = WORK_ROOT, remote = REMOTE, token = process.env.GITHUB_TOKEN } = {}) {
  const cwd = checkoutPath(e, root);
  // Existing work is evidence, not disposable scratch. Preparation failure is
  // visible and needs inspection instead of an automatic destructive retry.
  if (await lstat(cwd).catch(() => null)) fail('CHECKOUT_ALREADY_EXISTS');
  await mkdir(cwd, { recursive: true, mode: 0o2770 });
  await git(cwd, ['init']);
  await establishCanonicalCheckout(cwd, { branch: e.branch, startHead: e.startHead, freshIssue: e.target === 'issue' }, { remote, token });
  if (e.target === 'pull_request') {
    await git(cwd, ['fetch', '--no-tags', remote, `refs/heads/${CONSUMER.baseBranch}:refs/remotes/main`], { token });
    if ((await git(cwd, ['rev-parse', 'refs/remotes/main'])).trim() !== e.targetBase) fail('STARTING_STATE_MISMATCH');
    const bases = await git(cwd, ['merge-base', '--all', e.startHead, e.targetBase], { allowFailure: true });
    if (!bases || bases.trim().split(/\s+/).length !== 1) fail('INTEGRATION_BASE_INVALID');
  }
  // This is deliberately the *untrusted* Git repository in the task workspace.
  // Trusted publication never consumes its configuration or executes Git here.
  await grantSharedCheckoutAccess(cwd);
  return cwd;
}
export async function executeCodex(e, { runTask = runGovernedCodexTask } = {}) {
  const remediation = e.target === 'pull_request';
  const evidence = { codexChildStarted: false };
  try {
    const launchMetadata = e.step === undefined ? '' : `\n\nSupplied launch metadata (display only):\nTask: #${e.issueNumber}\nStep: ${e.step}\nThread name: ${e.thread}\nUse this supplied Task/Step title for this launch. Old titles do not override it; do not infer or cross-check Step history. This metadata grants no additional task authority.`;
    const integration = remediation ? `\n\nBounded base-branch reconciliation: the reviewed starting head is ${e.startHead}; the admitted current ${CONSUMER.baseBranch} is ${e.targetBase}, available as refs/remotes/main. If the admitted remediation needs integration, you may make at most one local two-parent merge commit on the task branch, with its previous task head first and exactly ${e.targetBase} second. Preserve both lines of work and resolve conflicts. All task commits, including that merge, must use the supplied remediation bot identity. No other merge parents, rebase, amend, reset, history rewrite or force publication. This exception permits only local integration into the task branch; PR merge and base-branch mutation remain forbidden.` : '';
    const result = await runTask({
    operation: remediation ? 'review-remediation' : 'issue-implementation', profile: e.profile,
    cwd: checkoutPath(e), targetNumber: e.number,
    taskTitle: e.thread, evidence, attemptId: e.attemptId,
    gitIdentity: remediation ? CODEX_REMEDIATION_IDENTITY : CODEX_WRITER_IDENTITY,
    inputText: `${e.input}${launchMetadata}\n\nTrusted execution boundary:\nWork only in the governed repository checkout and task branch. The admitted goal permits changes to any repository file necessary to complete it. Preserve repository, security, and authority boundaries. Make ordinary task-owned commits. Do not push, publish, merge PRs, close Issues, invoke a Reviewer, or use GitHub credentials. The local Git metadata is untrusted and will be imported as object bytes only. Do not modify hooks/config/remotes. Preserve useful commits even when blocked.${integration}\nCapability-owned validation: run applicable unprivileged local checks and report checks you cannot execute. Root/sudo-only installed-runtime proof belongs to native Exact-head CI after Writer publication; do not attempt privilege escalation or claim that proof passed. Pending native proof alone does not block an otherwise completed local implementation.\nSubagents: ${e.subagentsAllowed === true ? 'On, as explicitly authorized by task authority' : 'Off'}\nReturn only JSON with status (success or blocked), summary, validation (array of claims), and blockedReason. Do not reconstruct Git/publication metadata.`,
    buildArgs: ({ inputPath, cwd, profile }) => remediation
      ? ['exec', '--operation', 'review-remediation', '--json', '--model', profile.cliModelId, '--effort', profile.effort, '--input-file', inputPath, '--cwd', cwd, '--pull-request', String(e.number)]
      : ['exec', '--json', '--model', profile.cliModelId, '--effort', profile.effort, '--input-file', inputPath, '--cwd', cwd, '--issue', String(e.number)]
  });
    return { version: e.version, attemptId: e.attemptId, result, child: 'started' };
  } catch (error) {
    error.details = { ...error.details, executionId: e.attemptId,
      childState: error.details?.childState ?? (evidence.codexChildStarted === true ? 'started' : evidence.codexChildStarted === false ? 'not_started' : 'unknown'),
      lastSuccessfulBoundary: evidence.codexChildStarted === true ? 'codex-child'
        : evidence.codexFailureClass && evidence.codexFailureClass !== 'UNCLASSIFIED_CHILD_FAILURE' ? 'launcher'
        : evidence.launcherStarted ? 'privilege-process' : 'worker' };
    throw error;
  }
}
export const collectCheckout = e => collectProgress(checkoutPath(e), e, { token: process.env.GITHUB_TOKEN });
