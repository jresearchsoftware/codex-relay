---
name: Codex task
about: An executable Relay development goal with explicit authority and validation
title: ''
labels: 'step-1'
assignees: ''
---

## Task

<!-- Describe the intended behavior, acceptance criteria and protected boundaries.
Task N is this GitHub Issue #N. Admission permits necessary repository changes
on the task branch, not deployment, credentials, merge, release or Issue closure.
The full PR diff is reviewed independently at its exact head. -->

## Starting state and authority

<!-- Identify the target repository and any relevant live Issue/CR/PR.
For fresh work, omitted base resolves to the exact current configured base branch
at admission; omitted branch resolves to the configured prefix + task-N (normally
codex/task-N). If pinning a base, add Required starting base with one exact SHA.
For remediation, use the native CR's existing PR branch and required starting head.
Inspect dirty/unpublished work, normalize safely, then apply the SHA gate. -->

## Issue lifecycle

- Issue closure policy: `keep-open`

<!-- Use close-authorized only with explicit owner authority. Missing, malformed
or conflicting closure falls back to keep-open with a visible warning. PR linkage
is Related to #N for keep-open, or Closes #N for close-authorized. Review approval
does not itself close an Issue or authorize merge. -->

## Execution profile

- Subagents: `Off`

<!-- Before launch, resolve the model/effort from owner authority. For an explicit
override add Codex model and Codex reasoning effort fields using exact identifiers.
Automatic admission resolves omitted fields from that consumer's configuration,
never from a private policy file or an invented repository default. The backend
determines support; do not substitute a profile during execution. For a manual
launch the owner selects model/effort in the UI. -->

<!-- Keep exactly one positive step-N label: step-1 for fresh work, or the owner's
explicit continuation Step. Ensure the label exists; the template cannot create
it. Existing Issue/PR labels must agree before Relay admission. Never derive Step
from body text or history. Use Task N — Step S — <purpose>, or for remediation
Task N — Step S — CR-N-NNN — <CR purpose>, preserving an exact authority-supplied
title. A manual session performs the one-shot native startup rename in AGENTS.md.
Issue creation and Step labels do not dispatch work. Ready labels may launch only
through separately configured and owner-authorized consumer routing. -->

## Recommended model budget

- Recommended Codex model: <!-- exact owner-resolved identifier -->
- Recommended Codex effort: <!-- exact owner-resolved effort -->
- Reason: <!-- why this profile fits the goal -->
- Escalation conditions: <!-- concrete condition and owner decision before launch -->
- De-escalation conditions: <!-- when an owner-selected cheaper profile is adequate -->

## Validation

<!-- Add acceptance checks specific to the task. Use targeted checks during
progress-bounded correction, then the applicable full candidate set in AGENTS.md.
Separate deterministic helper tests from native lifecycle or deployment proof. -->

- `git diff --check`

## Completion

<!-- Publish one top-level Codex Outcome on the canonical authorized surface:
exact title/profile (UNAVAILABLE when not exposed), final head and PR, completed
behavior, validation, material warnings and remaining boundaries. Preserve and
publish safe authorized task work before a terminal stop. Use an explicit success
or blocked token if useful. Implementation stops for independent exact-head review;
do not claim acceptance, merge, Issue closure, deployment or release. -->
