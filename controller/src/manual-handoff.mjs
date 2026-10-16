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
  // Retained v3 attempts still select one exact complete native Request. New
  // admissions resolve their selected sources through protected v4 authority.
  if (e.request?.kind !== 'admission' && e.requestReference) {
    const ref = e.requestReference;
    lines.push(`Current execution request: https://github.com/${e.repository}/${ref.parent.kind === 'issue' ? 'issues' : 'pull'}/${ref.parent.number}#${ref.kind === 'review' ? 'pullrequestreview' : 'issuecomment'}-${ref.id}`);
  }
  if (e.branch) lines.push(`Admitted branch: ${e.branch}`);
  if (e.startHead) lines.push(`Required starting head: ${e.startHead}`);
  lines.push('Read AGENTS.md, the current canonical authority and its referenced accepted governance.');
  if (e.startHead) lines.push('Safely normalize the canonical checkout to the admitted branch/head before applying the starting-head gate; preserve local work.');
  lines.push('Stop on an authority or starting-head mismatch, or a protected boundary.',
    'Complete the admitted work and validation; commit and push safe task-owned source work before handoff.',
    e.request?.kind === 'admission'
      ? 'Submit one canonical Outcome through submit_manual_outcome using the admitted binding.'
      : 'Publish one canonical Outcome through the admitted Writer publication path.');
  return lines.join('\n');
}
