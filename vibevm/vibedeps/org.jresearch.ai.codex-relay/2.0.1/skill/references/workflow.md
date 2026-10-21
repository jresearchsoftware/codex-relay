# Codex Relay user manual

Use the section relevant to the current action. This is the canonical authored
user manual for the Relay product workflow; [compatibility](compatibility.md),
[diagnostics](diagnostics.md) and [examples](examples.md) supply its conditional
detail. It describes the current schema-v4 source contract for a paired,
qualified Reviewer/controller installation, without claiming an installed
service or connected App has been upgraded or qualified. These are product
contract bindings. The complete applicable common topics are adopted by this
Skill and supplied after assembly under `shared/vibevm/vibespecs/protocols/`.
Read the full relevant protocol through the [Skill routes](../SKILL.md); below,
TH, IR, CD and CL refer respectively to `task-handoff.md`,
`independent-review.md`, `contract-and-decision-maintenance.md` and
`context-loading.md` in that pinned bundled directory. They own portable
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
source support does not qualify an installed Reviewer or owner adapter.

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

TH-002–TH-005 own stable-charter and chronological authority semantics. Relay
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

TH-006–TH-009 own execution-cycle and navigation semantics. Relay's protected
Writer allocates Step 1 at first admission and the next Step for each genuinely
new execution, including after BLOCKED. Same-attempt replay/recovery cannot
launch another worker. Approval, charter/Decision/CR publication and ready-label
display allocate no Step. Native titles and `step-N` labels project protected
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
The handoff retains `MANUAL_CODEX_HANDOFF_READY`; only its prompt fence may be
folded by default, after actual GitHub expand/copy usability is qualified.
Otherwise leave it open. Actions run names can show bounded Task/PR/route
information but do not preallocate Step.

A fresh native command may admit an independent source/research attempt before
an older Step has a terminal Outcome. Use an independent checkout and available
resource; a shared checkout, physical slot or exclusive environment remains
exclusive. Withdrawal revokes future authority without proving whether an
offline manual session started. There is no mandatory Start/Cancel handshake
or implicit cancellation of the older attempt. New attempts have their own
Steps and may duplicate computation; replay of one attempt never invokes the
model again.

## Execute and preserve progress

Use complete TH-012/TH-013 and CL for refresh, JIT completeness, correction and
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

## Change Request and remediation

Apply complete IR methodology to assessment and findings. A v4 native `CHANGES_REQUESTED`
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
TH-014–TH-017, not a multi-artifact publisher. A known multiple-source-artifact
result needs separately authorized product support; do not silently route it
through a no-PR Issue result. An uncertain PR-creation intent or ambiguous
artifact stops surface selection and never permits an Issue fallback.
A disposed qualification PR stays disposed.

TH-018 owns result disclosure and warning semantics. Relay binds results to an
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

Apply complete TH-022–TH-025 and IR-019. The evaluator resolves the applicable
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

The owner continuation path re-reads effective authority, exact acceptance/head,
required checks, readiness, completion, holds and protected boundaries. Only
already-authorized integration proceeds through that channel; v4 direction has
`hold` and optional trusted `next`, no competing `task_complete` or future Step.
Reviewer publishes acceptance and its bounded continuation policy; it performs
neither merge nor closure. A native `APPROVE` binds one reviewed head and
permits the separately authorized **squash-only** continuation when required
native checks are complete and passing, mergeability/readiness are verified,
and no hold or protected boundary applies. Unresolved checks, unknown readiness
or a moved candidate stop continuation. Ordinary base movement is allowed
where current exact-head checks and readiness remain safe; preserve any explicit
exact-base reconciliation policy.

Migrated PRs use `Related to #N`; trusted native `closesTask` must be explicitly
`false` before squash. `true` or unknown blocks the merge. The owner helper uses
neutral squash title/body rather than inheriting closing keywords. Explicit
Issue closure stays a separate action. Legacy linkage behavior retains its
original contract.

For an owner-created standalone source PR, Reviewer verifies the configured
owner's native User identity, same repository, branch and exact head, and binds
current canonical authority plus `source_pr` provenance in the native review.
This replaces only the execution-result binding; it fabricates no admission or
Writer Outcome. An exact retained manual Request may remain its compatibility
source. Unrelated historical Requests do not become current authority, and
fresh v4 work needs no fictitious Step or new v3 Request.

The existing trusted owner adapter separately verifies explicit standalone
permission in current canonical authority, no admitted Relay execution for that
result, and disposition of ordinary owner result warnings plus required native
evidence. Its internal `standaloneAuthorization` binds the exact
`authority_sha256`, `pullRequest` and `headSha`, with `authorized: true`,
`admittedExecution: false` and `warningsDispositioned: true`. Native owner,
head repository and branch must match the receipt; retained manual Requests
also bind Task/PR Step. These are adapter facts from existing evidence, not a
new owner prompt, public comment or registry. Missing, ambiguous or revoked
facts stop before mutation. An ordinary owner Outcome remains ordinary
evidence; it cannot become a Writer Outcome or Task Approval.

Known same-result Writer evidence or execution markers, including blocked or
stale results, retain their admitted result/recovery path. A source receipt
cannot downgrade an admitted result. Current migrated routes keep exact-head
checks, warning disposition, holds, neutral squash messages and closure boundaries;
only the explicitly supported standalone source path omits the admission/Writer
receipt. A retained Request naming only an old Request as its next action may
complete an authorized squash, then stops follow-up with
`CONTINUATION_NEXT_AUTHORITY_INVALID` until current v4 direction replaces or
clears that follow-up. Do not silently discard it or launch a fresh v3 chain.

Owner continuation reserves each operation before mutation, re-reads current
authority/facts after reservation and records/verifies the native result before
the next action. It reconciles already-completed operations without repeating
them. Uncertain approval, an ambiguous earlier mutation, missing readback,
changed authority or an uncertain response stops dependent progress and
preserves completed actions. Do not blindly retry merge, close or launch, fall
back to another verdict, or re-execute the accepted current Request as its own
next action. Already-authorized current v4 next direction can use existing
owner ports without a new public Request or preallocated Step.

## Decisions, closure and subsequent work

TH-002/TH-026 own completion and continuation semantics; Relay implements them
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

Installation is separately owner-authorized. Use the selected exact accepted
product revision and validated target configuration through Relay's public
deployment interface. For every explicitly owner-managed configured repository,
including inactive targets, authorized orchestration prepares and publishes a
separate reviewable routing/recovery workflow and manifest PR. A central product
PR, local projection or read-only proposal does not complete that publication.
Report missing access and the affected target rather than claiming completion.

Derive each proposal from that target's actual trusted branch, runner/pool
identities and installation namespace. Managed-pool projections use
`relay-workflows-v4`; a SERIAL v3 example does not qualify a managed installation.
The assembled `product/contract.json` records both supported workflow ABIs.
The target owner retains acceptance, merge, activation and governance; proposal
publication does not grant App access, runner ACLs or settings changes. Inactive
configured targets do not block a safe Apply, while enabling routing/recovery
requires the accepted configured refs and their separate operational proof.
