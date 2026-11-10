# Task handoff and continuation

<a id="TH-001"></a>
**TH-001 — Explicit lifecycle adoption.**

Apply this protocol to governed task execution, result handoff and continuation
only when the owning project has explicitly adopted it. Installation, a package
update or reading this file does not activate it or replace local authority.
Use the project's declared binding for its tracker, execution authorization,
retry/recovery mechanisms, conversation reuse, publication, review sufficiency
and protected actions. Those mechanisms implement the shared Step semantics
below; they do not silently redefine them.
This protocol works manually; it grants no execution, review, merge, release,
installation, consumer-adoption or closure permission.

## Stable charter and chronological authority

<a id="TH-002"></a>
**TH-002 — Canonical charter and pre-execution refinement.**

Apply [RA-006](requirement-authority.md#RA-006) when authoring the Task and its
acceptance/completion criteria; agent-written gates cannot authorize themselves.

Keep one current canonical Task reference: its goal, scope, completion conditions,
boundaries and authorized decisions. For governed GitHub-repository work, use
the Issue and its explicitly linked canonical records as the durable primary
reference. Another tracker needs an equally unambiguous project-owned binding.
Before first authorized execution, a placeholder or idea body may evolve into
an actionable charter. Proportionately choose body consolidation or a separate
Decision: consolidate when that improves clarity without hiding substantive
public discussion, contribution attribution or decision provenance. Preserve
or link meaningful earlier discussion as appropriate. Preliminary thoughts and
editorial refinements do not each need a formal Decision.

<a id="TH-003"></a>
**TH-003 — Historical charter and authorized amendments.**

From first authorized execution onward, keep the body as the stable historical
charter. Append substantive changes to scope, requirements, permissions,
completion/closure conditions or newly admitted work as explicit owner-authorized
Task Decision comments in chronological order. Another tracker needs equivalently
durable, clearly linked decision records. Do not prepend later directions or
rewrite the charter after Outcomes. Only narrowly non-semantic editorial body
corrections are permitted; they must not obscure changed authority.

<a id="TH-004"></a>
**TH-004 — Effective chronological authority.**

Completion or reopening preserves the original charter and historical execution
and acceptance. Append reasons, changes and new admissions as subsequent
Decisions; reopening resets neither Step numbering nor accepted history.
Resolve effective current authority from the original charter plus applicable
authorized Decisions, including explicit supersession or revocation. Neither
the latest body alone nor every conversational comment defines that authority.
Outcomes and reviews are evidence and assessment, not automatic scope permission;
historical discussion, prompt snapshots and upstream analysis supply none.

<a id="TH-005"></a>
**TH-005 — Readable owner Decisions.**

A Decision identifies what was decided, the relevant prior result/discussion
and resulting scope, authorization or Step direction concisely and readably.
Distinguish Task authority changes from PR-specific findings/remediation. Carry
substantive authorized amendments into effective authority before affected work.
No blanket JSON/typed publication or mechanical comment is required for routine
already-authorized actions.

## Step as an authorized execution cycle

<a id="TH-006"></a>
**TH-006 — Authorized execution cycle.**

Identify the Task, current work unit/Step and meaningful purpose explicitly.
A Step is one separately authorized architect/owner-to-executor work iteration:
hand off a bounded Task objective, investigate/implement, test and correct as
needed, then return a terminal execution result for assessment (an Outcome,
BLOCKED or another explicitly recognized terminal handoff).

<a id="TH-007"></a>
**TH-007 — Next Step after terminal result.**

The next newly authorized execution handoff after that terminal result allocates
the next Step, even for the same goal, findings, branch or PR. Internal
implementation/testing/corrections and ordinary clarifications during the active
execution retain its Step. Carry an admitted develop/test/fix cycle to a useful
result; do not invent separate coding, testing or research Steps as ceremony.

<a id="TH-008"></a>
**TH-008 — Recovery identity and Step boundaries.**

Retry, recovery or republication of the same execution/result without a fresh
execution cycle preserves identity. A genuinely new execution after BLOCKED
gets a new Step. Reconcile uncertain prior activity before deciding which case
applies. Review, discussion or a Decision alone allocates no Step; a Decision
may authorize the next execution, whose handoff starts that Step.
Step is not a PR, commit, conversation, transport attempt, test pass or formal
lifecycle phase. There is no fixed Step count or productivity measure, and a
terminal Step does not establish Task completion. Projects own authorization
and identity mechanisms, not an incompatible silent interpretation of this rule.

<a id="TH-009"></a>
**TH-009 — Task navigation and title limits.**

Use `Task N — Step S — <purpose>` for task-execution thread navigation in adopting
projects, with a concise purpose and the canonical Task link nearby to distinguish
projects with the same number. Number mappings for other trackers and any local
extensions belong to their declared binding. Rename when the client supports it;
verify the persisted title before claiming it changed. If rename or verification
is unavailable, disclose that limit and use a supported navigation aid. Title
limitations alone need not block useful authorized work. The title is navigation,
not authority, and specifies no labels, remediation identifiers or typed records.

## Startable handoff and bounded execution

<a id="TH-010"></a>
**TH-010 — Minimal startable handoff.**

The default execution prompt is a short navigation and start instruction:
Task, Step, short purpose, repository/canonical Task link, and a direction to
read the full Task chronology and linked authority, applicable accepted governance,
execute the admitted Step and publish its result for independent assessment.
Do not restate accessible goals, requirements, investigation steps, test matrices,
boundaries or publication contracts, even when duplication seems helpful.
Read the complete relevant discussion, Decisions, Outcomes/reviews and linked
records, not just the body. After an Outcome use a new small handoff and the
corresponding admission, not a rewritten charter.

<a id="TH-011"></a>
**TH-011 — Routing facts and delegation boundary.**

Add only irreducible handoff-specific routing/environment facts unavailable from
canonical authority, such as a starting worktree or material access limitation.
There is no universal model/effort field or extra ceremony. If a project needs
a bounded execution snapshot, identify its origin/freshness; it is subordinate
to canonical authority and does not replace this minimal default.
Requested model/client settings
are not proof of actual execution; disclose relevant unavailable capabilities or
evidence. Delegation does not expand authority.

<a id="TH-012"></a>
**TH-012 — Refresh and reconcile before mutation.**

Before starting or resuming, refresh current Task decisions, the applicable
accepted result/review frontier and mutable work facts. Load detail needed for
the next decision. Preserve useful and unrelated work, inspect uncertain prior
activity, and reconcile the canonical branch/artifact safely before comparing
identities or repeating a mutation. A real authority or result mismatch is a stop
condition, not permission to reset, replace or silently overwrite work.

<a id="TH-013"></a>
**TH-013 — In-scope persistence and stop conditions.**

Continue evidence-backed corrections inside the admitted goal without adding
approval stages for every local fix. Stop when scope/permission or prior external
mutation is uncertain, a material policy choice needs its owner, a protected
boundary is inaccessible, or repetition yields no new evidence. Preserve useful
results and disclose unreconciled work. A preferred new workflow or material
obligation needs the owning project's decision before implementation.

## Canonical Outcome publication target

<a id="TH-014"></a>
**TH-014 — Outcome target follows complete actual result.**

Select one canonical terminal Outcome target from the complete actual result of
that Step. Launch route, where execution was authorized, manual versus automated
execution and the number of PRs associated with the Task overall do not select
the target. Use the project's authorized publication mechanism and preserve its
required attribution, identity and trust boundaries.

For a GitHub binding:

| Complete Step result | One canonical Outcome target |
| --- | --- |
| Exclusively one clearly identified result PR | A top-level conversation comment on that PR, including when Issue admission led to creating it or the Task has other unrelated PRs. Ordinary checks, committed evidence and documentation supporting that PR do not create a separate Task-level result. |
| No PR, two or more known result PRs, or one PR plus a substantive independent Task-level result | The canonical Task Issue. For known multiple result PRs, identify each relevant PR, its exact result SHA/revision and pertinent status/limits. |

<a id="TH-015"></a>
**TH-015 — Unambiguous result binding.**

Another tracker needs equivalent, unambiguous Task/result surfaces in its local
binding. A known multi-PR result is a Task-level target, not an ambiguous binding.
If the intended result-to-PR mapping or required identity is missing, conflicting
or genuinely ambiguous, stop publication and reconcile it. Inability to resolve
a PR target is not permission to fall back to the Issue. A known no-PR result
needs no artificial PR, empty commit or fabricated SHA.

<a id="TH-016"></a>
**TH-016 — One attributable Outcome and replay.**

Publish exactly one attributable Outcome for the whole terminal result. Do not
duplicate, split, retrospectively relocate or republish the same Outcome across
Task and PR surfaces. On recovery/replay of the same execution/result, reconcile
prior publication first: retain an existing canonical Outcome; if none was
published, publish once at the resolved authorized target. An uncertain mutation
does not justify another copy or a different target.

<a id="TH-017"></a>
**TH-017 — Discoverability and per-result acceptance.**

Keep the Task-to-result/PR relationship discoverable through ordinary canonical
links and existing project navigation. No duplicate status comment, mandatory
synchronizer, multi-PR orchestrator, native structured record or Relay Writer
identity is required by this shared method. A Task-level Outcome does not accept
or integrate several PRs by implication: each PR still requires its independent
exact-head review and applicable acceptance/integration authority. Consumer-owned
stronger Writer/Reviewer/admission/merge guarantees remain intact.

## Executor-to-review artifact readiness

<a id="TH-028"></a>
**TH-028 — Verified executor handoff and PR Draft/Ready lifecycle.**

For applicable GitHub PR-backed implementation or remediation, Draft means
active, incomplete, blocked or unconfirmed execution handoff. Ready for review
means that the executor successfully completed, durably published and verified
the handoff of that identifiable result for independent review. It does not mean
reviewer APPROVE, passing CI, mergeability, integration readiness, merge authority,
Task completion or package adoption. A base conflict or red CI alone does not
require drafting a successfully handed-off result; required checks, review and
merge remain separate gates.

Preserve the owning project's qualified automation when it owns this transition;
do not create competing executor mutations. Otherwise the authorized executor,
including a manual executor, performs the state changes where available and
permitted by the local client/product binding. Do not silently pass that duty to
the owner or another client when the executor has the authorized capability.
This rule prescribes behavior, not a GitHub API, CLI, bot, privileged identity,
new credential or universal automation system. Preserve stronger product
security, branch-protection, admission/recovery and approval guarantees.

At the beginning of newly admitted implementation/remediation on an existing
open result PR, ensure Draft and verify the same PR and current head **before
substantive modification**. If already Draft, verify without a redundant mutation.
Create new implementation PRs as Draft where the project supports it. A new Step
on the same PR re-enters Draft, preserving its branch/PR identity, prior reviews
and historical acceptance. Review/discussion alone and no-PR analytical work
create neither a PR nor a Draft transition.

For a successful handoff, reconcile and push the authorized exact candidate,
publish the one canonical attributable Outcome under [TH-014](#TH-014) through
[TH-018](#TH-018), and verify durable publication. **Then** mark only successfully
completed result PRs Ready for review and read back the same PR number, exact
head and native state. This executor handoff precedes independent review; it
does not wait for APPROVE. With an Issue-level or multi-PR Outcome, judge each
PR's own completion/readiness; a completed sibling cannot make a blocked PR Ready.
An equivalent verified atomic/coordinated completion sequence is allowed if it
preserves these invariants.

Keep blocked, failed, incomplete or uncertain affected PRs Draft. If successful
Outcome publication is durable but the Ready mutation or readback fails, retain
that Outcome and the same Step/result identity. Report the exact observed state,
permission/capability or readback gap and needed authorized action; reconcile and
retry only the single idempotent lifecycle transition through the local authorized
mechanism. Never duplicate the Outcome, redo execution solely for this mutation,
claim Ready without readback or invent capability. Missing state permission is
an explicit handoff/readiness limitation for owner disposition, not by itself a
defect in successfully published code.

For non-GitHub workflows, apply equivalent *supported* local artifact states.
This rule requires no new Draft/Ready UI, CLI/account/permission setup or synthetic
PR where those states or a PR are absent. Shared publication changes no consumer
automation: consumers separately review and adopt the changed topic/version.

## Exact result and independent assessment

Where separately adopted, [independent-review methodology](independent-review.md)
substantiates this assessment. This reference does not activate that topic or
change the acceptance authority and strategies below.

<a id="TH-018"></a>
**TH-018 — Executor evidence and warning disclosure.**

Publish an attributable result through the project's authorized path, verify the
published target, and bind claims and evidence to the identifiable artifact or
immutable result under review. Report accomplished and blocked work, applicable
checks, remaining work, observations versus unverified claims, and material
limitations. For known material warnings, state source, impact, disposition,
next action and missing evidence; inaccessible evidence is a gap, not proof of
warning absence. A no-change, analytical or non-repository result needs no empty
commit, fabricated SHA or artificial PR. Use the existing Task/result records.

<a id="TH-019"></a>
**TH-019 — Independent result assessment under project rules.**

Require independent assessment of the identified result under the owning
project's review rules, sufficiency criteria and appropriate evaluator/result
identity. Tests and implementation helpers supply evidence, not independent
acceptance. Record who or what assessed which result. Merely opening another
chat or checking one's own work does not establish independence.

<a id="TH-020"></a>
**TH-020 — Actor attribution and native identity limits.**

A separate evaluator can provide an assessment outside GitHub, published with
honest attribution through one owner account. That publication does not prove
an authenticated distinct reviewer, create native GitHub approval, satisfy branch
protection or reproduce a product's enforced reviewer separation. A comment
headed `APPROVE` supplies none of those assurances. The adopting project's policy
decides sufficient acceptance evidence and native identity requirements; preserve
any stronger boundary. If only the implementer is available, disclose the gap and
leave independent acceptance pending.

<a id="TH-021"></a>
**TH-021 — Fresh-result review and methodology ownership.**

A changed result needs applicable fresh qualification and independent review;
old exact-result acceptance does not carry over. Assessment methods, including
primary evidence, affected-behavior completeness, finding provenance/severity,
owner-facing report content and rereview, belong to
[Independent Review](independent-review.md#findings-and-review-after-correction)
where separately adopted, otherwise to the project's local review rules.
This reference does not adopt that optional topic. Task-Handoff-only consumers
retain the lifecycle and independent assessment requirement, but this version
no longer supplies those detailed assessment/reporting methods through Task
Handoff alone. They must deliberately adopt Independent Review if they want its
shared methodology, or retain their existing local method. It creates no common
owner-wait or publication permission rule.

## Result acceptance strategies

<a id="TH-022"></a>
**TH-022 — Direct and Deliberative strategies.**

Select by the decision needed to accept the result, not whether it contains code
or documentation. The two shared standard strategies are:

| Strategy | When applicable | Positive independent review |
| --- | --- | --- |
| Direct | Fixes, implementation of agreed requirements or other work with an established desired result and criteria. | May publish formal exact-result APPROVE immediately once applicable evidence, checks and authority requirements are satisfied. Previously authorized post-approval continuation, including safe automatic merge, is unchanged. |
| Deliberative | Open research, architecture selection, methodology/policy proposals or other results needing owner judgment about alternatives, trade-offs or proposed commitments. | First supply a substantive non-approving assessment/preview with findings and warnings. Even a positive assessment must not publish formal APPROVE or trigger approval-driven merge before intended owner discussion and the necessary Decision. |

<a id="TH-023"></a>
**TH-023 — Strategy precedence and preserved boundaries.**

Resolve selection in order: (1) explicit owner-authorized strategy in the charter
or subsequent Task Decision; (2) applicable adopting-project rules, including
additional named strategies; (3) shared defaults: Direct for an already decided
result/requirements, Deliberative when the output itself requires architectural,
methodological or policy choice. Technical research can be Deliberative; a
correction to already accepted governance can be Direct. An authorized Decision
may revise the strategy before acceptance. Resolve material ambiguity about
needed owner deliberation before formal APPROVE. Customization cannot weaken
independent assessment, accepted owner/trust boundaries or required checks.

<a id="TH-024"></a>
**TH-024 — Deliberative acceptance sequence.**

For Deliberative acceptance:

1. The executor returns an attributable Outcome and reviewable immutable result.
   An independent evaluator substantively assesses that exact result, including
   findings/warnings, through the authorized project mechanism without approving.
   Record real defects as actionable findings; use a genuine change request when
   warranted, never a fake REQUEST_CHANGES solely to suppress approval/merge.
2. The architect/owner discusses and records an explicit Decision: accept, request
   corrections/new work, reject, or accept research-report quality without adopting
   its recommendation. Report acceptance does not authorize implementing,
   migrating, installing or releasing the proposed architecture/policy.
3. If the owner authorizes acceptance of the unchanged result, verify that the
   reviewed head and effective authority are still current, retain applicable
   checks/identity requirements, reuse sufficient independent evidence and publish
   the actual exact-result APPROVE. Do not require another complete review of
   the same head without a reason. A changed result needs fresh applicable review.
   Once genuine approval is published, existing authorized project continuation
   may proceed within its own boundaries.
4. Material rework or a new execution after terminal Outcome gets the next Step
   under the execution-cycle rule. Discussion and preliminary review alone do not.

<a id="TH-025"></a>
**TH-025 — Verdict publication and continuation authority.**

This strategy governs publication of the review verdict, not merely a hold on
post-approval merge. A post-approval continuation hold alone cannot prevent
premature APPROVE. Result-quality acceptance, owner selection of a recommendation,
PR integration, Task closure, deployment and publication remain distinct
permissions/events; an evaluator can value a report whose solution the owner rejects.

These are reusable defaults, not a universal schema, rigid Task classifier or
replacement for a product's Reviewer/Writer. Bind review publication locally;
future consumer automation must enforce the selected boundary before its native
verdict while preserving exact-head, identity and merge guarantees. Shared
authoring or publication does not authorize that consumer implementation,
installation or changed automation.

## Authorized continuation and completion

<a id="TH-026"></a>
**TH-026 — Authorized continuation and completion.**

Acceptance, integration, publication/installation, further execution and Task
closure are distinct. Continue only when current authority permits the next
action and applicable checks, acceptance and protected boundaries are satisfied.
Already authorized actions need no ceremonial reconfirmation; new scope needs
its owner. A completed or accepted Step does not prove the whole Task complete,
and accepted source does not prove deployment or release. Apply [RA-006](requirement-authority.md#RA-006) before admitting continuation;
reconcile apparent self-expansion through existing Decisions. Reassess concrete
completion conditions, remaining work and holds at meaningful transitions; do
not close with known remaining work or copy a stale disposition indefinitely.

<a id="TH-027"></a>
**TH-027 — Proportionate local bindings.**

Keep evidence and continuation proportionate in existing Issue/artifact/review
records. This protocol introduces no universal schema, registry, state machine,
automated gate, mandatory tooling or product execution mechanism. Technical
product fields can evolve without changing shared meaning; changes to authority,
warning disclosure or mandatory operator work need the applicable owner decision.
Shared-protocol adoption, a product upgrade and client-adapter compatibility are
separate project-owned decisions; none implies the others.

<a id="TH-029"></a>
**TH-029 — Conditional generated client settings reconciliation.**

When a Task includes applying changed generated client instructions, integration
of desired-state files alone does not complete that obligation. For ChatGPT
Project Instructions, compare the accepted desired complete text with live project
settings through supported evidence. If different, surface the complete updated
text for owner manual application, preserving/reconciling unknown live rules,
and obtain supported confirmation/readback before claiming application or closing
the Task. Disclose unavailable live reads or uncertain confirmation as an evidence
gap; source files, receipt metadata and merge never prove settings synchronization.
When effective text is unchanged and no application gap remains, no manual settings
action is needed. Tasks that do not include application acquire no such obligation.
Use the existing client binding and Task records; no automatic settings access,
new approval loop or recurring hash-only update is required.
