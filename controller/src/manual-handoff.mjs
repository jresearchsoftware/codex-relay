// Presentation only: the caller supplies an already validated, admitted
// envelope. Protected authority, integrity bindings and publication reservations
// remain with Writer; this copyable prompt does not replace those records.
export function compactManualPrompt(e, authorityUrl) {
  const lines = [
    `Task: #${e.issueNumber}; Step: ${e.step}`,
    `Repository: ${e.repository}`,
    `Canonical authority: ${authorityUrl}`,
    `Thread: ${e.thread}`,
    `Codex model: ${e.profile.cliModelId}`,
    `Codex effort: ${e.profile.effort}`,
    `Subagents: ${e.subagentsAllowed ? 'On' : 'Off'}`
  ];
  if (e.branch) {
    const pr = e.request?.existing_pr ?? (e.target === 'pull_request' ? e.number : e.continuation?.pullRequest);
    lines.push(`Admitted branch: ${e.branch}; base SHA: ${e.historicalBase}; source PR: ${pr ? `https://github.com/${e.repository}/pull/${pr}` : 'none (new source work)'}`);
    lines.push(`Required starting head: ${e.startHead}`);
  } else lines.push('Admitted Git start: none (source-free manual work).');
  lines.push('Read AGENTS.md, the current canonical authority and its referenced accepted governance.');
  const source = e.branch;
  if (e.startHead) lines.push((source ? `Use an independent checkout/worktree and execution resources for ${e.attemptId ?? e.request.attempt ?? 'this admitted attempt'}. ` : '')
    + 'Safely normalize the canonical checkout to the admitted branch/head before applying the starting-head gate; preserve local work.');
  lines.push('Stop on an authority or starting-head mismatch, or a protected boundary.'
    + (source ? ' Do not reuse an active checkout/slot/exclusive environment. Before pushing, revalidate current authority and exact ref/PR head; stop on sibling progress or uncertain publication.' : ''),
    e.branch ? 'Complete the admitted work and validation; commit and push safe task-owned source work before handoff.'
      : 'Complete the admitted work and validation.',
    'Submit one canonical Outcome through submit_manual_outcome using the admitted binding.');
  return lines.join('\n');
}
