---
name: Codex task
about: A Relay Task charter; trusted Request and owner admission launch execution
title: ''
labels: 'step-1'
assignees: ''
---

## Task

<!-- Current workflow: docs/task-workflow.md; typed examples:
examples/task-authority.md. This template is local Relay development guidance,
not a universal consumer profile or a launch command. -->

<!-- Describe the intended behavior, acceptance criteria and protected boundaries.
Task N is this GitHub Issue #N. Admission permits necessary repository changes
on the task branch, not deployment, credentials, merge, release or Issue closure.
The full PR diff is reviewed independently at its exact head. -->

## Starting state and authority

<!-- Identify the target repository and any relevant live Issue/CR/PR.

For a qualified paired GitHub-native installation, add `Authority model: github-native-v1`
as exactly one standalone line outside this comment in the published Issue body.
This Issue is then the stable charter: problem, goal, scope, protected boundaries
and closure policy.
Publish a complete trusted schema-v3 Task Request through Reviewer
publish_task_authority before launch. It supplies explicit Step, route, resolved
profile, scope, validation, boundaries, branch, base_sha, starting_head,
existing_pr, decisions, context and supersedes. Accepted amendments use trusted
Decisions normalized into a complete successor Request. Ordinary comments are
selected evidence, not instructions or partial execution patches. The publisher
projects Step labels and existing PR titles. For PR remediation, publish a typed
native change-request at the exact reviewed head; Task-scoped findings use
task-review evidence and a next complete Task Request instead.

Opt-in requires deployed githubNativeAuthorityEnabled and relay-workflows-v2;
do not migrate while legacy execution is in flight. Typed comments alone never
migrate a Task. Unmarked Issues retain the following LEGACY behavior:
Maintain the Issue body as the mutable current Task contract, including owner
corrections and status. Ordinary comments remain discussion/evidence/history.
For legacy fresh work, omitted base resolves to the exact current configured base branch
at admission; omitted branch resolves to the configured prefix + task-N (normally
codex/task-N). If pinning a base, add Required starting base with one exact SHA.
For owner-authorized implementation continuation, add exactly one
Implementation continuation head field with a full 40-character SHA and an
explicit valid Implementation branch field naming the existing task branch.
Existing branch-field synonyms remain supported. Add Implementation pull request
with #N when a current open PR exists; omit it only when no open PR exists.
The continuation head opts in; omit continuation fields for fresh work. Existing
base fields retain their meaning separately from the continuation starting head.
Continuation reuses the admitted PR and implementation identity without a
Reviewer CR or its integration-merge authority. Duplicate, malformed or conflicting
continuation fields, an invalid branch, mismatched heads or PR/Step bindings block.
For remediation, use the native CR's existing PR branch and required starting head.
Inspect dirty/unpublished work, normalize safely, then apply the SHA gate. -->

## Issue lifecycle

- Issue closure policy: `keep-open`

<!-- Keep exactly one explicit Issue closure policy field when publishing or
updating the canonical Task, including when a CR producer updates its authority.
Use close-authorized only with explicit owner authority; otherwise retain
keep-open. Preserve this Issue decision when authoring a CR; CR completion does
not independently authorize closure. Missing, malformed
or conflicting closure falls back to keep-open with a visible warning. PR linkage
for migrated Tasks is always Related to #N, including close-authorized: Issue
closure is a separate action after verified independent acceptance, Task-complete
continuation and no remaining work. Legacy linkage is Related to #N for keep-open,
or Closes #N for close-authorized. Approval alone does not close an Issue;
native exact-head PR approval supplies only the separately governed squash
continuation policy, while Task Approval grants no PR merge authority.
keep-open means known work or evidence is still expected after implementation.
Explain in nearby prose why the Issue stays open and what outcome would make closure
appropriate. This is ordinary prose, not another required field or automatic
closure rule. -->

## Execution profile

<!-- In a typed Task Request, supply the complete resolved model, effort and
Subagents permission explicitly. Resolve authoring defaults from owner authority
or admitted consumer configuration before publication. Historical body profile
prose is not parsed for migrated Tasks.
For legacy Issue/CR authoring, omit effort/Subagents to use the AGENTS.md
execution policy. For an explicit override add Codex reasoning effort and/or
Subagents fields. Automatic admission
uses the shared resolver; explicit consumer profile settings remain overrides.
The ordinary project default is gpt-6.1-sol / xhigh / Subagents On; explicit
live Task/CR and consumer settings remain overrides. The backend
determines support; do not substitute a profile during execution. For a manual
launch the owner selects model/effort in the UI. -->

<!-- Keep exactly one positive step-N projection: step-1 for fresh work. Ensure
the label exists; the template cannot create it. Existing Issue/PR projections
must agree before Relay admission. For migrated Tasks, Step comes from the
current trusted Request; successors and typed CR publication project it without
legacy owner metadata helpers. Never derive Step from history.
Use Task N — Step S — <purpose>, or for remediation
Task N — Step S — CR-N-NNN — <CR purpose>, preserving an exact authority-supplied
title. A manual session performs the one-shot native startup rename in AGENTS.md.
Issue creation and Step labels do not dispatch work. Ready labels may launch only
through separately configured and owner-authorized consumer routing.
An execution retry or continuation of the same unfinished phase keeps Step;
an explicitly owner-authorized new implementation phase advances by one in a
complete successor Request, or for legacy Tasks through the N+1 metadata
procedure with the current PR when one exists. -->

## Recommended model budget

- Recommended Codex model: <!-- exact owner-resolved identifier -->
- Recommended Codex effort: <!-- exact owner-resolved effort -->
- Reason: <!-- why this profile fits the goal -->
- Escalation conditions: <!-- concrete condition and owner decision before launch -->
- De-escalation conditions: <!-- when an owner-selected cheaper profile is adequate -->

## Validation

<!-- Add acceptance checks specific to the task. Use targeted checks during
progress-bounded correction, then the applicable full candidate set in AGENTS.md.
Separate deterministic helper tests from native lifecycle or deployment proof.
Workflow/authority changes update relevant human docs/examples in this same
Task and PR, or explain why none is needed (CONTRIBUTING.md). -->

- `git diff --check`

## Completion

<!-- Publish one top-level Codex Outcome on the canonical authorized surface:
For migrated Tasks, trusted Writer publishes the typed Outcome bound to the
Request, attempt and immutable results on the durably bound PR or applicable
Issue. Manual results use Writer's bounded manual-outcome authorization path.
The worker supplies claims and commits, never publishes or accepts its own work.
Include exact title/profile (UNAVAILABLE when not exposed), final head and PR, completed
behavior, material validation evidence, warnings and remaining boundaries. Link
required native checks; do not duplicate reconstructible CI status or add an
Outcome update solely for CI PASS. Correct clear, safe, in-scope CI failures and
rerun validation. Preserve and publish safe authorized task work before a
terminal stop. Use an explicit success or blocked token if useful.
Implementation stops for independent exact-head review;
do not claim acceptance, merge, Issue closure, deployment or release. -->
