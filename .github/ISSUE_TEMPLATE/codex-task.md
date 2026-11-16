---
name: Codex task
about: A current v4 Relay Task charter; owner ready command admits execution
title: ''
labels: ''
assignees: ''
---

## Task

<!-- Current workflow: packages/codex-relay/skill/references/workflow.md;
typed examples: examples/task-authority.md. This is local Relay development
guidance, not a universal consumer profile or a launch command.
Describe the problem, intended behavior, scope and acceptance criteria.
Task N is this GitHub Issue #N. -->

## Starting state and authority

Authority model: github-native-v1

<!-- Identify the repository, relevant Issue/CR/PR and any exact starting head.
The qualified relay-workflows-v4 controller/Writer pair uses this stable charter
and applicable trusted schema-v4 Decisions. Before first execution, consolidate
an actionable charter without hiding meaningful public history. After first
admission, change substantive Task authority through trusted Task-scoped
Decisions; do not rewrite the historical charter. Ordinary comments are evidence.

The owner applies codex-ready-auto or codex-ready-manual when execution is ready.
Writer creates the immutable admission snapshot and allocates Step at that time;
Issue creation, Decisions and ready labels alone do not preallocate a Step.
Do not add step-1 to a new charter. Writer projects admitted Step/title metadata.
Each genuinely new execution, including after BLOCKED, receives the next Step;
replay/recovery of the same attempt retains its original Step and bindings.
No complete public Task Request is required for new v4 work. PR remediation
uses the native v4 change-request bound to the reviewed head, without its own
Step. Fresh legacy/v3 execution on a qualified v4 installation stops for current
protocol authority; exact already-admitted old attempts retain compatibility.
See contracts/README.md#streamlined-schema-40-admissions and the Skill's
references/compatibility.md for those retained paths, not a new v3 authoring flow.

For continuation, identify the existing implementation branch/PR and exact head
in current authority. Preserve its implementation identity; inspect local work,
normalize safely and compare the refreshed canonical head before modification.
No reset, force-push or replacement PR to satisfy a gate. -->

## Issue lifecycle

Issue closure policy: <!-- choose keep-open or close-authorized with owner authority -->

<!-- Replace the comment above with exactly one policy value before publication.
Next to that field, write concrete human-readable Task completion and closure
conditions: development, independent exact-result review, merge where applicable,
any explicitly authorized installed Apply/deployment and original-operation
verification, and unresolved owner choices. These are ordinary prose, not a new
required field. Do not treat source acceptance as deployment evidence.

Choose close-authorized only when the final result PR's successful default-branch
merge will complete the Task. After exact-head independent acceptance and checks,
trusted owner continuation designates that final PR with Closes #N or a supported
native closing link. Intermediate PRs remain non-closing; abandoning a PR does
not close the Task.
Choose keep-open for actual remaining post-merge work, including an authorized
Apply, qualification or package publication. Use Related to #N and name the
preauthorized condition and sufficient evidence beside the policy. Once verified,
with required acceptance/integration and no remaining work/protected hold, trusted
owner continuation closes the Issue without another choice prompt, conversion to
close-authorized or Decision merely releasing the satisfied condition.
Reassess at meaningful transitions. After execution, actual changes to scope,
conditions or authority need a trusted Task-scoped Decision; verification of
unchanged conditions does not. A CR cannot change Task closure authority.
Missing/malformed/conflicting metadata prevents automatic closure with a visible
warning; reconcile genuinely missing intent without inventing a permanent hold.
Preserve historical/already-admitted Tasks and explicit holds. No-PR results use
the existing trusted completion path. See
contracts/README.md#closure-policy-authoring and shared Task Handoff TH-002/TH-026. -->

## Protected boundaries

<!-- State Task-specific exclusions and separately authorized protected actions.
Repository implementation authority does not itself permit deployment,
credentials, service/configuration changes, merge, release or Issue closure.
Preserve owner, executor, Writer and independent Reviewer responsibilities. -->

## Execution profile

<!-- Resolve model/effort/Subagents once at admission from explicit authority,
consumer configuration and project defaults. A charter need not duplicate the
complete resolved profile. Project defaults are gpt-6.1-sol / xhigh / Subagents On;
explicit live authority and consumer settings remain overrides. Do not silently
substitute profiles. A manual owner selects model/effort in the UI; requested
settings are not proof of actual runtime values.

The admitted handoff supplies Task N — Step S — <purpose>, or
Task N — Step S — CR-N-NNN — <CR purpose>. Preserve its exact title. A manual
session uses the one-shot native startup rename and truthful readback in AGENTS.md.
Issue creation and title/Step projections do not dispatch work. -->

## Recommended model budget

<!-- For Relay repository development, AGENTS.md#model-recommendation-references
routes the locked passive Landscape recommendation/evidence reference. Reading
it does not adopt defaults, change an allowlist or reselect an admitted profile.
Keep the existing project defaults unless explicit owner authority changes them. -->

- Recommended Codex model: <!-- exact owner-resolved identifier -->
- Recommended Codex effort: <!-- exact owner-resolved effort -->
- Reason: <!-- why this profile fits the goal -->
- Escalation conditions: <!-- concrete condition and owner decision before launch -->
- De-escalation conditions: <!-- when an owner-selected cheaper profile is adequate -->

## Validation

<!-- Add Task-specific acceptance checks. Use targeted checks during correction,
then the applicable full candidate set in AGENTS.md. Separate deterministic
source tests from native lifecycle/deployment proof. Update affected user docs
and examples within this same Task/PR (CONTRIBUTING.md). -->

- `git diff --check`

## Completion

<!-- Trusted Writer publishes one canonical Outcome bound to current authority,
admission and exact result on the authorized target. For a new v4 manual attempt,
submit structured results through submit_manual_outcome; do not replace it with
an owner-authored result copy. Include exact final head/PR, accomplished behavior,
validation, material warnings, limitations and remaining boundaries. Link native
checks; do not duplicate reconstructible CI status. Correct clear in-scope faults
and preserve/publish safe task-owned work before a terminal stop.
The executor's handoff leaves independent exact-head acceptance pending.
Select Direct or Deliberative acceptance through current authority and applicable
project bindings; Deliberative assessment precedes owner-authorized final verdict.
Do not claim approval, merge, closure, deployment or release from implementation. -->
