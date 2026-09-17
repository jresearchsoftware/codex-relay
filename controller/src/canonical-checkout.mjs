import { CONSUMER } from '../../consumer/consumer.mjs';
import { git, REMOTE } from './trusted-git.mjs';
import { branchName, exactSha, fail } from './execution-contract.mjs';

// Trusted startup only, before granting a checkout to a worker. Never invoke
// Git against a model-owned checkout; attempt resumption uses object import.
// Also usable for an operator-owned project checkout with unambiguous live
// branch/head authority. No reset, force checkout, stash or replacement branch.
export async function establishCanonicalCheckout(cwd, { branch, startHead, freshIssue = false }, { remote = REMOTE, token } = {}) {
  branchName(branch);
  if (!exactSha(startHead)) fail('STARTING_STATE_MISMATCH');
  if ((await git(cwd, ['status', '--porcelain=v1', '--untracked-files=all'])).trim()) fail('CHECKOUT_DIRTY');
  const initial = (await git(cwd, ['rev-parse', '--verify', 'HEAD'], { allowFailure: true }))?.trim();
  const remoteBranch = freshIssue ? CONSUMER.baseBranch : branch;
  const observed = (await git(cwd, ['ls-remote', '--heads', remote, `refs/heads/${remoteBranch}`], { token })).trim().split(/\s+/);
  if (observed.length !== 2 || !exactSha(observed[0]) || observed[1] !== `refs/heads/${remoteBranch}`) fail('CANONICAL_BRANCH_MISSING');
  await git(cwd, ['fetch', '--no-tags', remote, `refs/heads/${remoteBranch}`], { token });
  const refreshed = (await git(cwd, ['rev-parse', 'FETCH_HEAD'])).trim();
  if (initial) {
    // Refresh the initial branch's publication evidence too. An unrelated
    // published branch is safe to leave; uncommitted/unpublished work is kept.
    const currentBranch = (await git(cwd, ['branch', '--show-current'])).trim();
    if (currentBranch && currentBranch !== remoteBranch) {
      const refs = (await git(cwd, ['ls-remote', '--heads', remote, `refs/heads/${currentBranch}`], { token })).trim();
      if (!refs) fail('CHECKOUT_UNPUBLISHED');
      await git(cwd, ['fetch', '--no-tags', remote, `refs/heads/${currentBranch}`], { token });
      if (await git(cwd, ['merge-base', '--is-ancestor', initial, 'FETCH_HEAD'], { allowFailure: true }) === null) fail('CHECKOUT_UNPUBLISHED');
    } else if (await git(cwd, ['merge-base', '--is-ancestor', initial, refreshed], { allowFailure: true }) === null) fail('CHECKOUT_UNPUBLISHED');
  }
  const local = (await git(cwd, ['rev-parse', '--verify', `refs/heads/${branch}`], { allowFailure: true }))?.trim();
  if (local && local !== refreshed && await git(cwd, ['merge-base', '--is-ancestor', local, refreshed], { allowFailure: true }) === null) fail('CHECKOUT_UNPUBLISHED');
  if (local) await git(cwd, ['switch', branch]);
  else await git(cwd, ['switch', '--create', branch, refreshed]);
  // Gate only the canonical branch after normalization, including its freshly
  // observed remote head. A real mismatch cannot be repaired by rewriting it.
  if (refreshed !== startHead) fail('STARTING_STATE_MISMATCH');
  if (local && local !== refreshed) await git(cwd, ['merge', '--ff-only', refreshed]);
  if ((await git(cwd, ['rev-parse', 'HEAD'])).trim() !== startHead) fail('STARTING_STATE_MISMATCH');
  return startHead;
}
