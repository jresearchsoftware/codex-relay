# Codex Relay user manual

Use the section relevant to the current action. This is the canonical authored
user manual for the Relay product workflow; [compatibility](compatibility.md),
[diagnostics](diagnostics.md) and [examples](examples.md) supply its conditional
detail. It describes the current schema-v4 source contract for a paired,
qualified Reviewer/controller installation, without claiming an installed
service or connected App has been upgraded or qualified. These are product
contract bindings. The complete applicable common topics are adopted by this
Skill and reached through the assembled [shared protocol source](shared-protocols.md).
Read the full relevant protocol through the [Skill routes](../SKILL.md); below,
TH, IR, CD and CL refer respectively to `task-handoff.md`,
`independent-review.md`, `contract-and-decision-maintenance.md` and
`context-loading.md` in that selected source. They own portable
lifecycle, assessment, contract and context semantics; this manual owns Relay's
native mechanisms and supported paths. Read [compatibility](compatibility.md)
for retained old attempts rather than applying current rules retrospectively.

## Owner acceptance and execution routes

A verified owner or authorized-maintainer merge into accepted `main` is final
owner acceptance of that exact contribution, including when native `APPROVE`
or a Writer Outcome is absent. Verify the actor's authority and actual merged
contribution in GitHub/Git. Describe this as owner acceptance by merge; do not
demand retrospective receipts or report native approval or execution that did
not occur. Revoked acceptance, material new defects and changed candidates still
need their own disposition. A new assistant-controlled approval or merge
preserves independent exact-head review, required checks and owner authority.

Choose the route authorized by the owning project's policy and current Task:

| Route | Execution and result evidence |
| --- | --- |
| Relay automatic | Protected Writer admission and Step; isolated worker executes; Writer imports and publishes the result and one canonical Outcome. |
| Relay-admitted manual | Real Writer admission/Step and copyable handoff; manual executor submits the result through the admitted Writer transport. |
| Explicitly owner-authorized standalone/manual | Canonical Task/CR goal and boundaries, exact source/target identity, safe effects, validation, durable ordinary owner result and independent review. No fabricated native admission, Step, ready event or Writer Outcome. |

Standalone work publishes actual evidence through its owner-authorized channel
and states that provenance. It cannot replace an admitted attempt's publication
or recovery. An unavailable automation capability blocks the operation needing
it; it does not itself prohibit otherwise authorized standalone/manual work.
Changing routes does not resolve an uncertain process, conflicting ref,
ambiguous external mutation or protected effect. Reconcile those facts before
dependent work, retain original-attempt recovery protections and never replay
an admitted execution because automation is unavailable.

For an explicitly authorized standalone source PR, current native independent
`APPROVE` can lead to the already-authorized exact-head squash through the
existing owner continuation channel without another confirmation or a fabricated
Writer receipt. Explicit permission, absence of an admitted attempt for that
result and the continuation safeguards below must verify. Owner authorship or
a missing Writer Outcome alone grants no permission. Automatic and
Relay-admitted manual results retain their Writer requirements; genuine no-PR
results retain typed Task Approval.

Source acceptance, installation, deployment and release are separate facts and
permissions. A route choice adds no operational or credential authority, and
source support does not qualify installed Reviewer or GitHub connector permissions.

## Authority, actors and capabilities

The canonical Task is Issue #N. For current schema v4, the Issue has exactly one
standalone `Authority model: github-native-v1` line and remains the stable
charter. It states problem, goal, scope, protected boundaries and one initial
`Issue closure policy: keep-open` or `Issue closure policy: close-authorized`.
Missing, malformed or conflicting closure metadata means `keep-open` with a
visible warning. Next to that field state concrete human-readable completion
and closure conditions, separating development, independent acceptance, merge,
any required authorized Apply/deployment and original-operation proof, and
unresolved owner choices. Use the closure binding below; no additional field
or validator is required.
Issue creation does not admit or launch execution.

Task Handoff's "Stable charter and chronological authority" section owns those semantics. Relay
implements amendments through trusted, active Task Decisions. Independent amendments
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
the qualified Reviewer tools; new admitted manual results require the separately enabled
`submit_manual_outcome`. Missing/outdated capabilities are an actionable
installation/connection boundary. Source revision, a marker or configuration
alone does not prove qualification. Do not add a universal probe or work around
the boundary with legacy transport. Read [compatibility](compatibility.md).

Decisions, CRs/reviews, Outcomes, Task Approvals/findings and retained Requests
lead with concise human-readable substance in the owning project's publication
language. Keep material findings, corrections, warning dispositions, evidence
gaps and limitations visible before one collapsed `<details>` containing the
unchanged canonical `relay-authority` fence. Use a visible JSON fallback only
for an established rendering, integrity, size or copyability constraint. Native
rendering escapes untrusted text so it cannot inject links, misleading status,
Markdown/HTML or another authority fence. Presentation does not create authority.

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

At a genuinely new routed admission, Writer reads the canonical Issue's single
valid `step-N` position under its existing serialization lock and compares it
with successful durable admissions. The next Step is N+1; without a label it is
last admitted Step+1, or 1 when neither exists. An owner-maintained position
above Writer history permits standalone iterations. A position below successful
history, malformed/conflicting labels, overflow or a concurrent position change
fails with an actionable diagnostic. Rejected launches allocate no Step;
same-attempt replay/recovery retains its Step. The label supplies numbering,
never execution or admission authority. Writer projects the position only after
durable admission and verifies the native result.

Task Handoff's complete "Step as an authorized execution cycle" section owns
these numbering and replay invariants; this manual binds the native admission
and projection behavior.

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
After an owner-launched `codex-ready-manual` command, keep monitoring its original
routing run and canonical target until trusted Writer publishes
`MANUAL_CODEX_HANDOFF_READY` with the full copyable prompt and admitted identity
and snapshot, or a verified terminal error establishes why that original routing
attempt stopped. A successful label operation or scheduled/pending routing does
not establish a terminal result or a ready manual handoff. If the original event
or handoff publication is ambiguous, reconcile it by reading back the original
ready event, routing run and trusted Writer publication on the canonical target;
do not issue a duplicate ready command to resolve that ambiguity. Return the
complete, unmodified Writer prompt, or the concrete terminal diagnostic. If
the client cannot keep waiting, report only the observed label, event, run
and Writer state together with that client boundary; do not report success
without Writer publication evidence. An inferred Step or pending run is not
a terminal handoff. Reconcile any ambiguity through the original ready
event and run.
The handoff retains `MANUAL_CODEX_HANDOFF_READY`; only its prompt fence may be
folded by default, after actual GitHub expand/copy usability is qualified.
Otherwise leave it open. Actions run names can show bounded Task/PR/route
information but do not preallocate Step.

### Manual result PR Step labels

An ordinary authorized participant or Codex may create a manual result PR.
When Writer validates its exact repository, Task, admitted branch/head and base,
it uses the shared projection path to apply the already-admitted `step-S` label
and bounded canonical title. This covers admission-bound PRs, delayed result
association and same-Step repair of a missing projection. It allocates no Step
and does not restrict PR author identity or require Writer-created manual PRs.
A conflicting Step or Task title requires reconciliation; it is never silently
overwritten. Late original results cannot restore an older Step's projections.

This completes the interim manual labeling responsibility from Task #182 and
Task #177: manual executors supply an accurately bound result; Writer owns the
verified projection at binding/publication. There is no historical bulk relabel,
continuous synchronizer or additional owner gate. One canonical Outcome,
Draft/Ready ownership and independent exact-head acceptance remain unchanged.

This Writer responsibility applies to Relay-admitted results. Explicitly
authorized standalone/manual work keeps owner-maintained numbering and ordinary
GitHub metadata permissions, with no fabricated admission or Writer receipt.
Its Issue position can become the numbering input of a later genuine admission.

### Independent attempts

A fresh native command may admit an independent source/research attempt before
an older Step has a terminal Outcome. Use an independent checkout and available
resource; a shared checkout, physical slot or exclusive environment remains
exclusive. Withdrawal revokes future authority without proving whether an
offline manual session started. There is no mandatory Start/Cancel handshake
or implicit cancellation of the older attempt. New attempts have their own
Steps and may duplicate computation; replay of one attempt never invokes the
model again.

Routine lifecycle drain and consumer transitions classify current operational
effects. A clean manual handoff with no matching runner journal or pending
result/publication effect does not require a historical Outcome, Task closure
or withdrawal acknowledgement before an unrelated idle upgrade. Historical
execution remains unknown; no cancellation or completion receipt is invented.
Active/unknown workers, pending trusted publication/recovery, conflicting
ownership and the original attempt's replay bindings remain protected.

## Execute and preserve progress

Normally carry investigation, implementation, technical corrections and tests
through one substantive execution Step to a complete candidate and Outcome.
Ordinary test failures, retries and internal phases do not themselves require
another Step. After resolving a blocker or finding, return to the complete
effective Task goal and its remaining requirements. Stop at a real evidenced
capability, authority, policy, trust or safety boundary. A genuinely new
execution after a terminal result keeps the existing next-Step rule.

Use complete Task Handoff and Context Loading for refresh, JIT completeness, correction and
stop semantics. Relay's existing-PR starting-head gate inspects its
live repository/branch/base/required SHA and local checkout/worktrees, dirty
state and unpublished work. Safely fetch and normalize to the canonical branch
only with local work preserved, then compare local and remote heads. Never
reset, replace the branch/PR, force-push or absorb unrelated work to pass a gate.

Relay implements TH's useful-work preservation through substantive task commits
or the applicable durable artifact before terminal return, including BLOCKED;
the result reports local residue and publication boundaries. Unknown prior
worker execution/containment or an uncertain external mutation prevents
dependent execution or publication. Consumer-local component contracts bind
CD's material operator-change and durable-decision rules to canonical native
Task/Decision authority; candidate code or guidance cannot amend that authority.

Permission for every action must remain within admitted and current protected
boundaries. A later Decision may allow truthful reporting of the original work
without proving newly added requirements were performed or granting a revoked
operation. Consumer-specific TEST/PROD, deployment, credentials and recovery
authority must be explicit; the Skill creates none.

## Isolated disposable TEST qualification

The owning project's established authority must identify the concrete disposable
TEST environment and dedicated TEST repositories. A repository name containing
`test` alone establishes no boundary; this Skill designates no consumer resource.
Where that verified authority grants full standing TEST control, it includes
creation/modification of TEST-only Issues, branches, fixtures and trusted
Decisions/CRs, native positive and
negative independent reviews, workflow management/runs and creation, review and
squash integration of TEST PRs. Do not request a separate confirmation for each
of those already authorized operations. A preview rule for actual product
findings does not add a per-review prompt to in-scope TEST fixtures.

Preserve actual actor/tool permissions, Writer/Reviewer independence, genuine
native admission, exact head/checks, trusted publication, Issue closure policy
and recovery of the original uncertain operation. Claim shared TEST before use,
restore/verify usability and release only that execution's claim. This authority
does not extend to a product PR merge, PROD, external/ordinary consumer repositories outside the designated TEST boundary, or
App/credential/runner-ACL changes outside independently established authority.
An unavailable capability is a concrete boundary, not an invented approval stage.
The source project's [TEST policy](https://github.com/jresearchsoftware/codex-relay/blob/main/docs/execution-policy.md#test-environment-authority)
owns its concrete standing binding.

## Change Request and remediation

Apply complete IR methodology to assessment and findings. A v4 native `CHANGES_REQUESTED`
review/`change-request` binds repository, PR, branch/base, reviewed head, stable
CR ID and actionable findings with bounded overrides. It has no Step and needs
no successor public Task Request. Task-level `task-review` findings are evidence
for future owner direction, not an executable PR CR.

For native Relay-admitted automatic remediation, the owner applies
`codex-ready-auto` to the existing PR. The qualified routing path sends that
command through Writer, which derives the bounded `begin-remediation` action
from the verified current native CR, executes it and verifies Draft for the exact
CR/head before admitting or reserving worker execution. No second manual Draft
operation or direct Writer bypass is required. Reviewer publication returns
`structuredContent.pr_lifecycle`; that returned action alone does not prove
Writer executed it or changed the PR state.

Writer re-reads executable authority and the exact target. Missing lifecycle
capability, changed authority/head or a failed/uncertain transition stops
continuation before execution; retain the same CR/head for supported recovery.
The existing owner orchestration channel may also invoke the returned action
through Writer and verify its result. Relay-admitted manual routing uses Writer's
verified transition before publishing its handoff. Genuinely standalone/direct
manual execution follows its explicitly authorized channel and available native
PR capabilities; it cannot assume the automatic Writer transition or fabricate
admission. This clarification adds no standalone routing or qualification.

After successful preparation Writer admits and projects the new Step.
Preserve the branch/PR and exact starting-head gate. The corrected head needs
fresh independent review. Draft/Ready denotes execution handoff, not acceptance,
passing CI or merge permission.

If schema-v4 remediation safely publishes head B and reports terminal `BLOCKED`,
retain the CR and its original reviewed head A. A trusted Task-scoped Decision
after the canonical Writer Outcome resolves the blocker; a fresh owner ready
command on the same PR may then admit the next Step at Writer-proven B.
Writer verifies protected automatic publication or manual submission, authentic
native Writer Outcome, exact Task/PR/CR, branch/base/attempt lineage and current
refs. A Decision or current PR head alone neither launches work nor proves B.
Unresolved attempts, stale authority, foreign/moved/unpublished heads or replayed
commands stop admission. Do not replace the CR merely because Writer advanced
the blocked result. This current same-CR path does not rewrite historical
attempts or qualify an older installation.

## One canonical Outcome

Automatic workers hand commits and validation claims to Writer. An admitted manual session
submits `{repository, task, run_id, result}` through `submit_manual_outcome`, with
positive integer Task/run IDs and a complete compatible Outcome claim from the
admitted handoff/schema. No owner result-copy comment or second approval is
required merely to transport a new v4 result. It neither imports Git nor
launches, approves, deploys, merges or closes anything.

For a v4 PR result set `result.parent` to the intended PR and
`result.result.revision` to its exact published Git head. Keep one ordinary Task
link in the PR, such as `Related to #N`. Writer checks the admitted repository,
branch and configured base, and any admitted existing-PR number. No admission
digest line, PR-author restriction or scan of unrelated same-branch PRs is
required. Writer publishes one verified Outcome then makes that exact open PR
Ready for independent review. BLOCKED remains Draft; disposed PRs stay disposed.
A target input error can be corrected before claim reservation in the same
attempt. Once reserved, retry the same result for publication recovery; changed
claims cannot overwrite it. Retained v3 keeps its original request binding.


Competing candidates retain the canonical Task branch. The first authorized
publication may advance its exact predecessor; another candidate stops if that
predecessor changed. An unknown push/PR operation holds its publication target
until exact readback recovery. Late original reports do not roll back current
Step/title or Draft/Ready state or accept a newer head. A same-Task missing
Outcome is not a global admission dependency.

Writer verifies admission, native sources, Task/Step, exact result, unique
artifact, replay and current authority; reserves the digest; publishes one
Writer-Bot Outcome; and reads back its native identity and exact bytes. The
unique durably known result PR receives it; legitimate no-PR/no-change work
uses the Issue. This is Relay's supported single-artifact product binding of
Task Handoff's "Canonical Outcome publication target", not a multi-artifact publisher. A known multiple-source-artifact
result needs separately authorized product support; do not silently route it
through a no-PR Issue result. An uncertain PR-creation intent or ambiguous
artifact stops surface selection and never permits an Issue fallback.
A disposed qualification PR stays disposed.

Task Handoff's "Exact result and independent assessment" section owns result disclosure and warning semantics. Relay binds results to an
exact full Git SHA, immutable named native result/run/check identities, or both,
and separates checked bindings from executor claims. Keep material warnings,
limitations and unavailable proof visibly before one
folded canonical `relay-authority` block; never truncate material facts or
create another authority block. Use native checks for reconstructible CI
status instead of posting a PASS-only Outcome update.

Valid later Task Decisions remain separate from the immutable admission.
Writer reports authority drift, changed fields/comparison gaps and the review
signal without rewriting admission or retrofitting missing original defaults.
Native source tampering, wrong identity, conflicting CR, result/head mismatch
and duplicate delivery still fail closed.

## Independent acceptance and authorized continuation

The owner orchestration uses the supported GitHub connector directly for
already-authorized integration after genuine independent native approval. There
is no local owner merge command, post-review engine, action journal or background
service. Reviewer publishes acceptance; the owner channel performs integration;
protected Writer retains admitted execution and publication recovery.

After `PUBLICATION_UNCERTAIN`, reconcile the original identical Reviewer
operation through supported replay/readback, preserving its exact intended
body and operation identity. Do not post another review or treat an uncertain
response as approval. Reviewer `execution_supported: false` means that the
Reviewer itself performs no merge; it does not prevent authorized owner use of
the GitHub connector.

For an implementation PR, independent acceptance uses native exact-head
`APPROVE`; genuine remediation findings use `REQUEST_CHANGES`. Another Task
Approval for that PR is unnecessary. Genuine
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

The full IR protocol owns affected-result completeness, finding evidence and
provenance, binding-obligation sources, defect/gap/debt/optional-change
classification, and rereview. Relay binds its candidate/comparison identity to
the exact head and starting/base SHA, and publishes the assessment through
the qualified independent native Reviewer, with existing review/CR records.

### Direct and Deliberative acceptance

Apply Task Handoff's complete "Result acceptance strategies" section and
Independent Review's complete "Judgment, independence and publication" section.
The evaluator resolves the applicable
strategy from explicit owner-authorized Task/Decision selection, then the
adopting project's accepted rules, then TH's defaults. This is an assessment
binding; Relay adds no runtime classifier, admission field or new tool schema.

For Direct work, the qualified independent evaluator may publish the genuine
native exact-head verdict once authority, substantive assessment and applicable
checks permit it. For Deliberative work, the evaluator first provides a
substantive non-approving assessment with findings and warnings through the
existing owner discussion channel. Withhold native `APPROVE` and its dependent
continuation until the intended owner discussion and explicit trusted Task
Decision authorize final acceptance. Genuine defects may use the existing CR;
do not manufacture `REQUEST_CHANGES` merely to represent the deliberation hold.

If acceptance of the unchanged result is authorized, refresh effective native
authority and exact head, retain required checks/actor identity and reuse
sufficient independent evidence before the final verdict. Changed results need
fresh applicable review. Acceptance of research/report quality does not adopt
its recommendation or authorize implementation, deployment or release. Owner
discussion or a Decision alone does not allocate Step. After genuine approval,
only already-authorized continuation below may proceed.

### Owner integration through the GitHub connector

After durable genuine approval, complete the already-authorized owner sequence
without another ceremonial merge prompt:

1. Refresh effective canonical Task/Decision authority, native independent
   approval and the exact reviewed/current PR head, source provenance, required
   native checks, Draft/Ready, mergeability, warnings, explicit holds and
   protected boundaries. Changed authority requiring acceptance or a moved
   candidate needs fresh applicable review; incomplete/failing required checks,
   unknown readiness or a hold stop integration. Ordinary base movement is
   allowed only where current exact-head checks and readiness remain safe.
   Preserve an explicit exact-base requirement: the connector's atomic head
   comparison does not supply an atomic base comparison.
2. Verify closure restrictions. Under the current migrated-Task compatibility
   binding, use `Related to #N`, establish that the PR does not implicitly close
   the Task, and supply a neutral squash title/body. Removing the old helper
   does not implement Task #194 or authorize Issue closure.
3. Use the connector's `merge_pull_request` with `merge_method: "squash"`, the
   canonical repository/PR and `expected_head_sha` equal to the full approved
   SHA. Supply explicit neutral `commit_title`/`commit_message` where required
   by the closure binding. Do not omit the head guard or replace squash with
   another merge method or unattended auto-merge.
4. Read back the same PR and merge commit; verify merged state, approved head,
   destination and squash SHA before dependent work. A lost or uncertain merge
   response requires authoritative GitHub reconciliation of that original
   effect. Never blindly repeat it, switch verdict or launch/close while its
   effect is unknown. Report a missing permission or readback capability as the
   exact boundary; do not claim completion from a successful tool call alone.

The [component contract](https://github.com/jresearchsoftware/codex-relay/blob/main/contracts/README.md#authorized-continuation-after-independent-acceptance)
provides the connector argument example and detailed evidence boundaries.
GitHub records are the durable integration evidence; no owner-local merge
journal or replacement orchestration service is required.

For an explicitly permitted owner-created standalone source PR, Reviewer
verifies native owner, same repository, branch and exact head and binds current
canonical authority plus `source_pr` provenance. This supplies no admission or
Writer Outcome. The owner verifies standalone permission, absence of an admitted
execution for that result, warnings and the same integration gates through
existing evidence. An exact retained manual Request may remain a historical
compatibility source; fresh work creates no fictitious Step or v3 Request.

Known same-result Writer evidence or execution markers retain their admitted
result and recovery path, including blocked or stale results. An ordinary owner
comment cannot replace a Writer Outcome or Task Approval. Genuine no-PR results
keep their native Task Approval path and require no synthetic merge. Further
execution uses existing current admission authority rather than an old helper's
launch ports. Review, integration, Issue closure, further admission, release and
deployment remain distinct permissions. Reassess actual remaining work and
holds after verified integration under the supported closure contract.

## Decisions, closure and subsequent work

Task Handoff's "Stable charter and chronological authority" and "Authorized continuation and completion"
sections own completion and continuation semantics; Relay implements them
through its closure-policy field, native Task Decisions and owner continuation.
For an owner-authorized finite Task, choose `close-authorized` at charter
creation when closure is already authorized upon meeting its stated conditions,
including a later expressly authorized Apply. Keep the Issue open through
development, independent acceptance and merge until all required deployment
and verification conditions pass; a finite required Apply is a completion gate,
not itself a reason to request closure permission again.

Use `keep-open` when concrete additional work, an explicit hold or an unresolved
owner choice remains outside the authorized completion path. Name that condition
and its needed disposition. Reassess effective policy at new authorized
Steps/Decisions and meaningful completion transitions. After first admission,
change Task-wide closure conditions or authorization only through a trusted
Task-scoped v4 Decision; a CR cannot change them. Do not publish redundant
per-Step Decisions when nothing changed. If required deployment is deferred,
combined or cancelled by the owner, reconcile conditions and closure authority
through that Decision without claiming the original Apply occurred.

Closure requires effective `close-authorized`, trusted completion evidence,
independent exact-result acceptance, no remaining work/hold and satisfied
protected boundaries. The owner continuation can then close without another
permission request. If no work remains but `keep-open` persists, surface the
mismatch for canonical owner disposition. For retained v3/legacy work preserve
the original charter and successor-Request rules in [compatibility](compatibility.md).

Genuine no-PR acceptance remains typed independent Task Approval bound to its
exact Writer Outcome and immutable result. It does not authorize merging an
artifact PR. A known next phase or remaining qualification keeps the Task open.
Already-authorized conditional closure needs no repeated Decision, but still
requires current completion/acceptance and no remaining work or hold.

## Consumer policy boundary

Consumers own profile defaults, checks, credentials, runners, operational
permissions, publication language, optional client renaming and merge/approval
policy beyond Relay's mandatory native trust/exact-head boundaries. Preserve
explicit local material-contract-change bindings and protected operations under
complete CD. Relay development-only
test commands and optional hooks do not become consumer admission requirements.

## Prepare a Relay installation

Installation is separately owner-authorized. The ordinary public
`deploy/relay-deploy.py --phase install` selects fresh install, same-revision
reconciliation, compatible upgrade or supported protected replacement from
observed host state. Expert phases remain available. This 4.1.0 guidance
candidate describes Task #63 source support; installing the Skill alone does
not install or qualify the compatible product or activate a private PROD route.

For the owner's Git-managed installation, freeze accepted public product and
private desired-config Git commits together at Apply start. The private
configuration repository owns the single trusted owner `apply/stop/resume`
workflow; its `GITHUB_SHA` is the configuration SHA, while product source is
selected and verified independently. The scoped ephemeral workflow token reaches
the fixed protected helper through stdin, without private access for candidate
CI/workers or a new static credential. Merge alone does not deploy.

Git configuration is desired state for code-only, config-only and combined
changes. Previous installed intent is not an equality gate; snapshots/manifests
attest installation and recovery rather than select desired values. Actual
protected identity, schema, credential, runtime and external permissions still
apply. Other consumers retain their supported owner-file/checkout integrations.

The same operation returns complete repository-relative integration directories
for consumer routing/recovery and, in Git mode, the separate private lifecycle
workflow. Publish each directory's contents through its receiving repository's
normal change process; no fixed workflow count or second installer run is
required to finish the already-successful host installation. Compatible stale
workflows can continue; incompatible invocation fails with an actionable
outdated-integration diagnostic. Actual managed-workflow drift still fails
integrity validation. Separately authorized target-PR preparation/publication
remains distinct from installation.

Derive each proposal from that target's actual trusted branch, runner/pool
identities and installation namespace. Managed-pool projections use
`relay-workflows-v4`; a SERIAL v3 example does not qualify a managed installation.
The assembled `product/contract.json` records both supported workflow ABIs.
The target owner retains acceptance, merge, activation and governance; artifact
publication grants no App access, runner ACL or settings changes. Report precise
external prerequisites and retained recovery evidence instead of inventing
permissions or blind replay. Inactive configured targets do not block a safe
Apply; enabling routing/recovery requires accepted configured refs and their
separate operational proof. A private PROD cutover must qualify the replacement
and its external policy before retiring the working public entrypoint, with no
dual active privileged dispatcher. Source acceptance and TEST proof authorize no
live PROD Apply. The source repository's
[installation contract](https://github.com/jresearchsoftware/codex-relay/blob/main/docs/git-managed-installation.md)
provides the detailed strategy, readback and cutover procedure.
