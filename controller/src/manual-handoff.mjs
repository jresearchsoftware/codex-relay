import { canonicalAuthorityJson } from '../../contracts/src/github-authority.mjs';
import { foldManualHandoff, safePublicationText } from '../../contracts/src/publication-rendering.mjs';

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

export function renderManualHandoff(e, authorityUrl, outcomeBinding) {
  const prompt = compactManualPrompt(e, authorityUrl);
  let width = 3;
  for (const match of prompt.matchAll(/`+/g)) width = Math.max(width, match[0].length + 1);
  const fence = '`'.repeat(width);
  const visible = [
    'MANUAL_CODEX_HANDOFF_READY',
    `Thread: ${safePublicationText(e.thread)}`,
    `Attempt: ${e.attemptId}`,
    `Model: ${e.profile.cliModelId}; effort: ${e.profile.effort}`,
    `Subagents: ${e.subagentsAllowed ? 'On' : 'Off'}`,
    `Canonical authority: ${authorityUrl}`,
    '',
    'Copyable prompt:',
    '',
    `${fence}text`,
    prompt,
    fence,
  ].join('\n');
  const description = '\n\nManual Outcome binding: copy these admitted values unchanged into `submit_manual_outcome`. Set the final parent to the Task-owned PR when one exists, and add the status, result, summary, warnings and limitations from verified execution evidence. This binding is not an execution result.';
  const binding = `\`\`\`json\n${canonicalAuthorityJson(outcomeBinding)}\n\`\`\``;
  return {
    body: `${visible}${description}\n\n<details>\n<summary>Manual Outcome binding (JSON)</summary>\n\n${binding}\n\n</details>`,
    // Match an exact already-published body if the old receipt is missing.
    previousBody: `${foldManualHandoff(visible)}${description}\n\n${binding}`,
  };
}
