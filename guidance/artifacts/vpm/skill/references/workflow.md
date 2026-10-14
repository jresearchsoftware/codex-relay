# Relay workflow binding

Use the section relevant to the current action. These are product contract
rules, not a fixed number of execution Steps. After assembly, the bundled
portable semantic source is `shared/vibevm/vibespecs/protocols/task-handoff.md`;
this file
preserves the current Relay contract without newly activating that full topic.
Read [compatibility](compatibility.md) for
retained old attempts rather than applying current rules retrospectively.

## Authority, actors and capabilities

The canonical Task is Issue #N. For current schema v4, the Issue has exactly one
standalone `Authority model: github-native-v1` line and remains the stable
charter. It states problem, goal, scope, protected boundaries and one initial
`Issue closure policy: keep-open` or `Issue closure policy: close-authorized`.
Missing, malformed or conflicting closure metadata means `keep-open` with a
visible warning. Explain concrete remaining work near `keep-open`.

Trusted, active Task Decisions amend durable semantics. Independent amendments
accumulate in native comment-ID order; an explicit same-scope supersession
replaces its predecessor. Native references bind kind, ID, parent and the hash
of the entire original published body, including markers. Edited sources,
ambiguous chains or wrong native identities cannot become effective authority.
Ordinary comments are evidence. A PR-scoped Decision applies only to its exact
Task artifact; neither it nor a CR enlarges Task scope or changes Task closure.

The owner authorizes direction and native launch commands. A worker executes
within its admission and reports claims. Trusted Writer reserves admission,
imports bounded automatic-worker Git objects into a fresh trusted repository,
checks paths/modes and every introduced blob, publishes without force and
publishes Outcomes. Independent Reviewer publishes an external evaluator's
judgment using separate identity and credentials. Reviewer does not conduct the
assessment, merge a PR or close an Issue. Workers have no independent acceptance
or protected owner-continuation authority.

Before a connected operation, verify that its required tool and current input
schema are actually available to the caller. Current publication/review uses
the qualified Reviewer tools; new manual results require the separately enabled
`submit_manual_outcome`. Missing/outdated capabilities are an actionable
installation/connection boundary. Source revision, a marker or configuration
alone does not prove qualification. Do not add a universal probe or work around
the boundary with legacy transport. Read [compatibility](compatibility.md).

## Author and admit current work

Create the stable charter without guessing a future Step, branch, head or model.
Use owner-authorized Reviewer `publish_task_authority` with a v4 `decision` only
when durable semantics need amendment. A new complete public Task Request is
unnecessary. Before a substantive Decision, reassess concrete remaining work
and effective closure disposition within that authoring action.

The owner applies `codex-ready-auto` or `codex-ready-manual` on the canonical
Issue, or on the bound PR for current native CR remediation. These are native
commands; a displayed label alone grants no authority. Trusted routing verifies
the owner event and current authority. Writer consumes the event once and
durably creates the sole immutable admission snapshot, including sources,
profile, scope, boundaries, validation, exact starting state, route, attempt/run
and Step. Rejected routing does not allocate Step.

First execution is Step 1. Each genuinely new admitted execution, including
after terminal BLOCKED, gets the next Step. Inner corrections, tests, replay
and recovery of the same attempt retain its Step and never launch another
worker. Approval, charter/Decision/CR publication and ready-label display do
not allocate Step. Native Task/Step titles and `step-N` labels project protected
admission state; never infer identity from the largest historical number.

Profile resolution is applicable CR overrides, trusted Decisions, consumer
defaults, then supported system defaults. Resolve once at admission; no silent
model/effort substitution. Requested values are not measured backend telemetry;
actual values stay `UNAVAILABLE` unless runtime evidence exposes them. Subagent
permission does not authorize nested Relay execution or expand scope.

Manual routing preserves the exact admitted identity/profile, canonical source
pointers and full copyable prompt. A new manual execution after BLOCKED uses a
fresh manual thread where the route requires it. Thread navigation is not Step
authority. Consumer client instructions govern rename tools/readback; report
their actual result without inventing a new Step or blocking on naming alone.

## Execute and preserve progress

Refresh mutable authority and starting facts after interruption. Load affected
contracts just in time. Before an existing-PR starting-head gate, inspect its
live repository/branch/base/required SHA and local checkout/worktrees, dirty
state and unpublished work. Safely fetch and normalize to the canonical branch
only with local work preserved, then compare local and remote heads. Never
reset, replace the branch/PR, force-push or absorb unrelated work to pass a gate.

Continue evidence-backed correction within the admitted goal while each next
action is clear, safe and authorized. Stop for a material owner choice, missing
authority, unknown prior execution/containment or uncertain external mutation.
Preserve useful work even when blocked. Before a terminal return reconcile
task-owned changes into substantive commits or the applicable durable artifact;
leave unrelated work intact and disclose any local residue/publication boundary.
No empty commit or artificial PR is required for legitimate no-change work.

Permission for every action must remain within admitted and current protected
boundaries. A later Decision may allow truthful reporting of the original work
without proving newly added requirements were performed or granting a revoked
operation. Consumer-specific TEST/PROD, deployment, credentials and recovery
authority must be explicit; the Skill creates none.

## Change Request and remediation

Independently assess the complete exact candidate against effective Task
authority and aggregate material findings. A v4 native `CHANGES_REQUESTED`
review/`change-request` binds repository, PR, branch/base, reviewed head, stable
CR ID and actionable findings with bounded overrides. It has no Step and needs
no successor public Task Request. Task-level `task-review` findings are evidence
for future owner direction, not an executable PR CR.

After publication the existing owner channel invokes the bounded Writer
lifecycle action and verifies Draft for that exact CR/head before remediation.
An uncertain transition stops continuation. The owner applies the appropriate
ready command to the existing PR; Writer then admits and projects the new Step.
Preserve the branch/PR and exact starting-head gate. The corrected head needs
fresh independent review. Draft/Ready denotes execution handoff, not acceptance,
passing CI or merge permission.

## One canonical Outcome

Automatic workers hand commits and validation claims to Writer. A manual session
submits `{repository, task, run_id, result}` through `submit_manual_outcome`, with
positive integer Task/run IDs and a complete compatible Outcome claim from the
admitted handoff/schema. No owner result-copy comment or second approval is
required merely to transport a new v4 result. It neither imports Git nor
launches, approves, deploys, merges or closes anything.

Writer verifies admission, native sources, Task/Step, exact result, unique
artifact, replay and current authority; reserves the digest; publishes one
Writer-Bot Outcome; and reads back its native identity and exact bytes. The
unique durably known result PR receives it; legitimate no-PR/no-change work
uses the Issue. An uncertain PR-creation intent or ambiguous artifact stops
surface selection. Do not duplicate the report or invent a PR/SHA for a
non-source result. A disposed qualification PR stays disposed.

Results identify an exact full Git SHA, immutable named native result/run/check
identities, or both. Keep checked bindings distinct from executor claims.
Include material warnings, limitations and unavailable proof visibly before one
folded canonical `relay-authority` block; never truncate material facts or
create another authority block. Use native checks for reconstructible CI
status instead of posting a PASS-only Outcome update.

Valid later Task Decisions remain separate from the immutable admission.
Writer reports authority drift, changed fields/comparison gaps and the review
signal without rewriting admission or retrofitting missing original defaults.
Native source tampering, wrong identity, conflicting CR, result/head mismatch
and duplicate delivery still fail closed.

## Independent acceptance and authorized continuation

An open implementation PR requires native exact-head `APPROVE` or
`REQUEST_CHANGES`; another Task Approval for that PR is unnecessary. Genuine
no-PR work uses one Issue `task-approval` bound to the exact Writer Outcome,
authority/admission and immutable result. A closed disposable PR may supply
context without being reopened. A copied assessment, another thread or a
worker self-check does not establish Relay's independent native acceptance.

Compare admitted and current authority explicitly. Missing amended work needs
actionable remediation; unused expanded permission alone does not invalidate
delivered work. For material v4 authority drift or an explicit comparison gap,
bind the native approval to the current `expected_task_authority_sha256`.
Material authority changes after acceptance require fresh acceptance before
protected continuation. Dispose of every material warning and retain evidence
gaps; see [diagnostics](diagnostics.md).

Compare each material finding with the exact starting/base SHA. State whether
it was introduced, pre-existing, newly exposed/made blocking, or undetermined.
Only established introduction is a regression. Baseline debt needs current
scope or a material dependency before demanding remediation. On rereview assess
prior findings, changed behavior, adjacent risks and new findings together;
explain the missed invariant or evidence gap when a blocker survives.

The owner continuation path re-reads effective authority, exact acceptance/head,
required checks, readiness, completion, holds and protected boundaries. Only
already-authorized integration proceeds through that channel; v4 direction has
`hold` and optional trusted `next`, no competing `task_complete` or future Step.
Migrated PRs use `Related to #N` and require a verified non-closing linkage;
automatic closing keywords cannot bypass Task authority.

Closure requires effective `close-authorized`, trusted completion evidence,
independent exact-result acceptance, no remaining work/hold and satisfied
protected boundaries. A Task-scoped trusted v4 Decision can amend effective
closure in either direction; a CR cannot. If no work remains but `keep-open`
persists, surface the mismatch for owner disposition. Approval, merge, Step
completion, installation, deployment and release remain separate facts.

## Consumer policy boundary

Consumers own profile defaults, checks, credentials, runners, operational
permissions, publication language, optional client renaming and merge/approval
policy beyond Relay's mandatory native trust/exact-head boundaries. Preserve
explicit local material-contract-change gates and protected operations. New
user obligations or behavior outside authority need owner disposition; shared
guidance or this package cannot silently change them. Relay development-only
test commands and optional hooks do not become consumer admission requirements.
