import { CONSUMER, EXECUTION_CONSUMER, executionConsumer } from '../../consumer/consumer.mjs';
import { mkdir } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { git, collectProgress, REMOTE } from './trusted-git.mjs';
import { fail, validateEnvelope } from './execution-contract.mjs';
import { establishCanonicalCheckout } from './canonical-checkout.mjs';
import { normalizeCodexUsage } from './codex-usage.mjs';
import { grantSharedCheckoutAccess, runGovernedCodexTask, CODEX_WRITER_IDENTITY, CODEX_REMEDIATION_IDENTITY } from '../../runtime/src/codex-runtime.mjs';

export const WORK_ROOT = EXECUTION_CONSUMER.paths.workRoot;
export const checkoutPath = (e, root) => join(root ?? executionConsumer(e.executionSlot).paths.workRoot, validateEnvelope(e).attemptId);
export async function prepareCheckout(e, { root, remote = REMOTE, token = process.env.GITHUB_TOKEN } = {}) {
  const cwd = checkoutPath(e, root);
  // Existing work is evidence, not disposable scratch. Preparation failure is
  // visible and needs inspection instead of an automatic destructive retry.
  await mkdir(dirname(cwd), { recursive: true, mode: 0o2770 });
  try { await mkdir(cwd, { mode: 0o2770 }); }
  catch (cause) { if (cause.code === 'EEXIST') throw Object.assign(new Error('CHECKOUT_ALREADY_EXISTS', { cause }), { code: 'CHECKOUT_ALREADY_EXISTS' }); throw cause; }
  await git(cwd, ['init']);
  await establishCanonicalCheckout(cwd, { branch: e.branch, startHead: e.startHead, freshIssue: e.target === 'issue' && !e.continuation,
    allowBaseAdvance: e.request?.kind === 'admission' }, { remote, token });
  if (e.target === 'pull_request') {
    await git(cwd, ['fetch', '--no-tags', remote, `refs/heads/${CONSUMER.baseBranch}:refs/remotes/main`], { token });
    const currentBase = (await git(cwd, ['rev-parse', 'refs/remotes/main'])).trim();
    if (currentBase !== e.targetBase && (await git(cwd, ['merge-base', e.targetBase, currentBase], { allowFailure: true }))?.trim() !== e.targetBase) fail('STARTING_STATE_MISMATCH');
    const bases = await git(cwd, ['merge-base', '--all', e.startHead, e.targetBase], { allowFailure: true });
    if (!bases || bases.trim().split(/\s+/).length !== 1) fail('INTEGRATION_BASE_INVALID');
  }
  // This is deliberately the *untrusted* Git repository in the task workspace.
  // Trusted publication never consumes its configuration or executes Git here.
  await grantSharedCheckoutAccess(cwd);
  return cwd;
}
export async function executeCodex(e, { runTask = runGovernedCodexTask, signal } = {}) {
  const remediation = e.target === 'pull_request';
  const evidence = { codexChildStarted: false };
  try {
    if (typeof e.subagentsAllowed !== 'boolean') fail('SUBAGENTS_PERMISSION_INVALID');
    const launchMetadata = e.step === undefined ? '' : `\n\nSupplied launch metadata (display only):\nTask: #${e.issueNumber}\nStep: ${e.step}\nThread name: ${e.thread}\nUse this supplied Task/Step title for this launch. Old titles do not override it; do not infer or cross-check Step history. This metadata grants no additional task authority.`;
    const integration = `\n\nTask-owned Git work: start from admitted head ${e.startHead}.${remediation ? ` The admitted ${CONSUMER.baseBranch} input is ${e.targetBase}; refs/remotes/main contains the verified current descendant available for integration.` : ''} Choose ordinary local commits, task branches, accepted-upstream merges and conflict resolution. You may amend, squash, cherry-pick, rebase or reset your own unpublished work while preserving the admitted published frontier and everyone else's work. Preserve original authorship when integrating existing commits; the supplied identity is the default for newly authored work, not authentication. Trusted Writer validates all newly published reachable objects, provenance and non-force publication. Return the candidate on the admitted task branch and preserve useful committed progress if blocked.`;
    const result = await runTask({
    operation: remediation ? 'review-remediation' : 'issue-implementation', profile: e.profile,
    cwd: checkoutPath(e), targetNumber: e.number,
    taskTitle: e.thread, evidence, attemptId: e.attemptId,
    existingFallback: true, signal,
    gitIdentity: remediation ? CODEX_REMEDIATION_IDENTITY : CODEX_WRITER_IDENTITY,
    inputText: `${e.input}${launchMetadata}\n\nTrusted execution boundary:\nWork in the governed repository checkout toward the admitted task-branch result. The admitted goal permits changes to any repository file necessary to complete it. Preserve repository, security, and authority boundaries. Use local tools and task dependency downloads within this checkout and its contained environment. GitHub publication, PR integration, Issue closure and independent review belong to trusted actors; hand the local candidate to Writer without using GitHub credentials. The local Git metadata is untrusted and will be imported as object bytes only. Keep hooks/config/remotes local and credential-free; trusted Writer does not execute them. Preserve useful commits even when blocked.${integration}\nCapability-owned validation: run applicable unprivileged local checks and report checks you cannot execute. Root/sudo-only installed-runtime proof belongs to native Exact-head CI after Writer publication; do not attempt privilege escalation or claim that proof passed. Pending native proof alone does not block an otherwise completed local implementation.\nSubagents: ${e.subagentsAllowed === true ? 'On, within the resolved execution permission; use is discretionary and evidence-driven' : 'Off'}\nReturn only JSON with status (success or blocked), summary, validation (array of claims), and blockedReason. Keep the summary concise and decision-bearing. Record substantive validation evidence and material limitations. Deliver any separately requested large artifact through the Task’s authorized route. Do not reconstruct Git/publication metadata.`,
    buildArgs: ({ inputPath, cwd, profile }) => remediation
      ? ['exec', '--operation', 'review-remediation', '--json', '--model', profile.cliModelId, '--effort', profile.effort, '--input-file', inputPath, '--cwd', cwd, '--pull-request', String(e.number)]
      : ['exec', '--json', '--model', profile.cliModelId, '--effort', profile.effort, '--input-file', inputPath, '--cwd', cwd, '--issue', String(e.number)]
  });
    return { version: e.version, attemptId: e.attemptId, result, child: 'started', containment: evidence.codexContainment ?? 'unknown', codexUsage: normalizeCodexUsage(evidence.codexUsage) };
  } catch (error) {
    error.details = { ...error.details, executionId: e.attemptId, containment: evidence.codexContainment ?? 'unknown', codexUsage: normalizeCodexUsage(evidence.codexUsage),
      childState: error.details?.childState ?? (evidence.codexChildStarted === true ? 'started' : evidence.codexChildStarted === false ? 'not_started' : 'unknown'),
      lastSuccessfulBoundary: error.details?.lastSuccessfulBoundary ?? (evidence.codexChildStarted === true ? 'codex-child'
        : evidence.codexFailureClass && evidence.codexFailureClass !== 'UNCLASSIFIED_CHILD_FAILURE' ? 'launcher'
        : evidence.launcherStarted ? 'privilege-process' : 'worker') };
    throw error;
  }
}
export const collectCheckout = e => collectProgress(checkoutPath(e), e, { token: process.env.GITHUB_TOKEN });
