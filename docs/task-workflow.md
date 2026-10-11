# Task workflow

This guide describes the streamlined GitHub-native **source contract** for a
paired, qualified Reviewer/controller installation. It does not claim an
existing installation has been upgraded or qualified. Installed and in-flight
schema-v3 Tasks retain the compatibility path below. Consumer Skill/adapter
distribution remains separate Task #91. Detailed rules live in the
[authority](../contracts/README.md#github-native-task-authority),
[routing](../controller/README.md) and [Reviewer](../reviewer/README.md) contracts.

Owner-designated isolated TEST development and qualification follow
[TEST Environment Authority](execution-policy.md#test-environment-authority).

## From Task to completion

1. **Write the stable Issue charter.** Task N is GitHub Issue #N. State the
   problem, goal, scope, protected boundaries and exactly one initial closure
   field: `Issue closure policy: keep-open` or
   `Issue closure policy: close-authorized`. Explain concrete outstanding work
   when it remains open. Include exactly one standalone
   `Authority model: github-native-v1` line. Issue creation, Decisions and ready
   labels do not allocate a Step. The [Issue template](../.github/ISSUE_TEMPLATE/codex-task.md)
   supplies the authoring baseline; creation alone does not launch work.
2. **Publish only needed trusted Decisions.** An owner-authorized caller uses
   Reviewer `publish_task_authority` for a schema-v4 `decision` when durable Task
   semantics change. Multiple Decisions can accumulate in backlog without a
   Step or execution. Writer resolves the initial charter plus the active,
   trusted, non-superseded Decision chain; ordinary discussion cannot amend it.
   New work does not require a duplicate complete public Task Request.
3. **Launch with the native ready command.** Apply `codex-ready-auto` to the
   canonical Issue for automatic work or `codex-ready-manual` for an
   owner-launched manual session. An exact native PR Change Request may instead
   admit remediation on its bound existing PR. Trusted routing verifies the
   owner event/run and selects route, profile, branch/PR, head/base and current
   authority. Applicable CR overrides take precedence over trusted Decisions,
   then project defaults, then supported system defaults. Existing protected
   Writer records hold one immutable admission snapshot with source
   references/digests, attempt/run, lineage, boundaries and the admitted Step.
   The ready event is consumed once; a display label is not execution authority.
4. **Use the admitted Step and handoff.** Writer allocates the next Step only
   when a genuinely new execution is admitted. Iterative implementation, tests
   and corrections stay inside that attempt/Step. A new execution after BLOCKED
   gets a fresh Step and a fresh manual thread where applicable. Recovery or
   replay of the same admitted attempt keeps its Step and cannot launch again.
   Actions run names can show route/Task/PR and a bounded available purpose;
   they do not preallocate Step. Manual routing retains
   `MANUAL_CODEX_HANDOFF_READY`, its exact identity/profile/authority references
   and full copyable prompt. Only the prompt fence may be folded by default,
   after actual GitHub expand/copy usability is qualified; otherwise it stays
   open. The handoff does not allocate a future Step.
5. **Inspect the single Writer Outcome.** Automatic workers preserve task
   commits and report validation claims. Trusted Writer imports bounded objects
   into fresh Git, scans every introduced blob, revalidates authority and pushes
   without force. A manual Codex session submits structured result JSON through
   the narrow owner-connected `submit_manual_outcome` MCP capability to the
   protected Writer. No preceding public owner `relay-manual-result` comment or
   repeated approval is needed merely to transport a new result. Writer
   validates the admitted manual route/Task/Step, current authority, exact
   PR/head or immutable qualification identities, warnings/limitations, native
   target and replay state before publishing one canonical Writer-Bot Outcome.
   It records claims and verified bindings, not independent proof of every
   claimed test or operation.
6. **Review independently at the exact result.** Review the complete candidate
   against effective charter/Decisions and applicable native CR. Compare
   findings against the starting/base state and retain provenance. Implementation
   PRs use native exact-head `APPROVE` or `REQUEST_CHANGES`; an additional Task
   Approval for the same PR is unnecessary. Genuine no-PR work, including
   qualification with a closed disposable artifact PR, retains one independent
   Issue `task-approval` bound to the exact Writer Outcome, authority/admission
   and immutable result. Issue `task-review` findings are evidence for later
   owner-authorized direction, not an executable PR CR. Deterministic checks do
   not establish independent acceptance. Review and approval allocate no Step.
7. **Complete through trusted owner orchestration.** The
   [post-review continuation helper](../contracts/README.md#authorized-continuation-after-independent-acceptance)
   re-reads effective authority, acceptance, head, required checks, readiness,
   completion evidence and protected boundaries. A separately authorized exact
   squash merge proceeds through the owner channel. Reviewer publishes review
   evidence and performs neither merge nor Issue closure; the worker has neither
   capability. Conditional `close-authorized` closure proceeds only after the
   Task objective and applicable installation/qualification are complete,
   independent acceptance is verified, no work remains and no hold/protected
   boundary applies. Already-authorized conditional closure does not require
   repeating the Decision. Migrated PRs use `Related to #N`, preventing an
   automatic closing keyword from bypassing Task authority.

## Decisions, closure and subsequent work

The original Issue remains the stable charter. A trusted scoped Decision carries
the accepted semantic delta; do not rewrite the original charter or require a
replacement public Request to make a new Decision operative. Native references
bind kind, ID, parent and SHA-256 of the entire published body, including markers.
Worker prose and selected ordinary comments remain contextual evidence.
Supersession is explicit and deterministic; edited or superseded references
cannot stay active. PR-scoped decisions and CRs stay within that PR and the
Task's protected boundaries.

The effective closure policy starts with the charter. An explicitly
owner-authorized trusted **Task Decision** may change it to `keep-open` or
`close-authorized` in either direction. A PR Change Request cannot independently
change Task closure or enlarge Task authority. Before a substantive Decision,
reassess the concrete `keep-open` condition within the existing authoring action,
using [closure guidance](../contracts/README.md#closure-policy-authoring).
Completion evidence supplied through the trusted owner continuation boundary
distinguishes accepted Step from complete Task; it does not create another
competing Request/continuation closure policy.

If review/merge/qualification leaves no genuine Task work but effective policy
still says `keep-open`, surface that mismatch for owner disposition. Do not
silently close or indefinitely treat stale remaining-work prose as current truth.
Source completion, independent acceptance, merge, installation, closure and
release remain distinct facts and permissions.

## Native PR Change Requests

Review the exact candidate head and aggregate material findings before native
publication. The schema-v4 `change-request` records its PR parent, stable CR ID,
reviewed head, branch/base, findings and applicable bounded remediation overrides.
It does not allocate a Step or require a full replacement Task Request. The
native `CHANGES_REQUESTED` review remains independent exact-head authority.
It cannot manufacture an unrelated Task Decision or closure permission.

The bounded Writer lifecycle verifies Draft for that exact CR/head before
remediation. Owner orchestration may invoke it directly; admission also enforces
it. Apply the matching native ready command to the existing PR after the review
has been verified. Writer admits the new execution and projects its Step/title;
review publication itself is not Step allocation. Preserve the canonical branch,
PR and starting-head gate. A new candidate needs fresh exact-head review;
approval of an older head cannot accept it.

## Visible evidence, warnings and recovery

Necessary Decisions, CRs/reviews, Outcomes, Task Approvals/findings and retained
compatibility Requests lead with concise English substance. All material
findings, corrections, warning dispositions, evidence gaps and limitations stay
understandable before expanding JSON. One collapsed GitHub `<details>` normally
contains the single unchanged canonical `relay-authority` fence. Use a visible
JSON fallback only for an established rendering/integrity/size/copyability
constraint. Escaped untrusted text cannot inject Markdown/HTML, links, misleading
status or a second authority fence. Presentation never creates authority.

Before review, continuation, merge or closure, inspect supported native
execution-time check/job/controller/Outcome evidence. Preserve every material
warning's source, impact, disposition, next action and gaps. Unavailable required
evidence is a stated limitation; green status does not disposition warnings.
UI-only service/pre-execution banners remain outside mandatory automated
acquisition. See [warning policy](execution-policy.md#execution-warning-disposition)
and Reviewer `read_pr_review_evidence`.

A local in-scope correction can continue within the admitted attempt while its
next action is clear and authorized. Uncertain authority, containment, native
head or prior publication stops progress. Publication recovery reconciles exact
retained bytes/markers and frozen renderer intent through existing protected
operations; it never blindly repeats POST/push or launches Codex again.
Already-admitted v3 records keep their exact historical body/digest/Step.
Useful commits and unresolved warnings remain preserved. A genuinely new launch
after a terminal BLOCKED result is a new admitted Step.

## Installed and in-flight compatibility

Unmarked Issues retain their qualified legacy mutable-body, explicit Step-label
and CR1/CR2 paths. The `github-native-v1` marker is explicit opt-in, not proof
that a server supports schema v4. Existing schema-v3 native installations and
admitted attempts retain complete Request chains, selected references,
Request/CR Step projections and the old owner-result transport where required.
Do not rewrite history, fabricate new admission snapshots for old attempts or
use new source semantics to bypass an installed contract.

Task 115 Step 1 itself was admitted on the **then-current installed schema-v3**
path: exact trusted Request 6109630038, synchronized Step 1, manual route and
durable handoff. The future removal of public Request ceremony did not change
that initial admission. Its source implementation/tests/permitted isolated-TEST
qualification remain one admitted manual Step; this guide does not assert the
paired live runtime has been upgraded or qualified. Installation, ingress,
credentials, activation, release, production mutation, merge and Issue closure
retain their separately authorized boundaries.

Qualify the coordinated source/parser/renderer/publication path and compatible
workflow projection before enabling it on an installation. Preserve retained
reservations and original body/version during mixed-version recovery. The
product owns typed provenance, exact-head acceptance and actor separation;
consumers own effective profile, checks and operations. Local [AGENTS.md](../AGENTS.md)
adds English publication, development profile, candidate checks and manual title
renaming. Workflow changes follow the existing
[same-Task documentation rule](../CONTRIBUTING.md#keep-workflow-documentation-current).
