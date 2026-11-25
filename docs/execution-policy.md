# Progress-bounded execution

The complete common execution-cycle, correction, preservation and stop semantics
are owned by the adopted pinned
[Shared Governance 12.5.0 Task Handoff protocol](../vibevm/vibedeps/org.jresearch.ai.development-governance/12.5.0/vibevm/vibespecs/protocols/task-handoff.md),
especially TH-006–TH-013 and TH-026. Read the complete protocol when executing,
handing off or continuing governed work. This document binds it to Relay's
admitted invocation and supported standalone/manual route.

An ordinary Manual or Automatic Task should normally reach a complete candidate
and Outcome in one substantive Step. That execution owns investigation,
implementation, technical corrections and relevant tests; a failed check or an
internal phase does not itself justify a terminal handoff. Resolving a blocker
or finding returns execution to the complete effective Task goal, including
remaining requirements. A real boundary or a later independently authorized
execution still follows the Step rules in the shared protocol.

Execution completion, finding closure, bounded result acceptance and whole-Task
completion are separate judgments. A protected continuation outside an automatic
worker's capability does not turn completed local implementation into failure.
`BLOCKED` requires an actual obstruction to the required deliverable; stop affected
actions while continuing independent authorized work. For compound publication
and continuation, verify actual native admission/start or the complete manual
handoff before claiming the continuation occurred. Ready is not running.

Confirmed material residual defects need explicit evidence, outcome impact,
disposition and a discoverable existing/authorized tracker or owner risk decision.
Workers hand publication needs to Writer; they cannot create authority or publish
independently. Reuse an exact accepted correction from elsewhere only after
reconciling the affected source and any required installed revision. Operational
claims must identify actual versus modeled/source-only proof and evidence gaps;
this introduces no universal live-service or end-to-end validation prerequisite.

External context remains evidence under the owning project's authority. A link
to another project does not transfer its Task, settings, release or lifecycle
control into this execution. Explicit accepted multi-repository scope remains
valid, without an invented per-action approval requirement.

One bounded repair owns reproduction, directly related corrections, regression
checks, representative installed-to-target deployment and the original operation
through durable result publication. Keep the owner's original goal intact;
source-only checks do not complete a goal that requires installed operation.
Address material TEST/PROD differences and revalidate evidence affected by each
correction, without repeating unrelated historical proof. The
[deployment guide](../deploy/README.md) owns lifecycle interfaces; the
[Task workflow](task-workflow.md#owner-acceptance-and-execution-routes) owns
execution routes and owner acceptance. Deployment remains limited to the
environment and effects actually authorized.

For Relay's TH-012/TH-013 prior-state and authority checks, an uncontained worker,
unknown prior execution, ambiguous external mutation or uncertain repository,
credential, security or production authority remains a concrete stop boundary.

For state wholly inside an explicitly isolated disposable TEST sandbox, apply
[TEST Environment Authority](#test-environment-authority): uncertain or failed
TEST state may be deleted and rebuilt without forensic preservation or a
protected recovery procedure. Stop if the sandbox boundary or an effect outside
it is uncertain; disposable TEST authority does not resolve that uncertainty.

For fresh schema-v4 independent source/research attempts, the prior-state stops
apply to the concrete shared checkout, physical execution resource, exclusive
environment or external effect whose independence cannot be established. Missing
an unrelated older Outcome alone does not block an independent attempt. Unknown
older work remains unknown, without cancellation, negative-start proof, Step
reuse or another model call for that same attempt. Full lifecycle drain and
ownership reconciliation retain their global evidence requirements.

Subagent use is discretionary and evidence-driven within the resolved Subagents
permission. It does not authorize nested Relay workers or execution fan-out.
Keep the admitted parent model/effort fixed. Select each subagent's model and
effort independently based on its assignment's complexity and risk; they may
differ from the parent's. By default provide a separate self-contained assignment
with its goal, necessary facts/files, constraints and completion criteria, without
automatically passing full conversation or execution history. Include broader
history only when materially necessary, preserving relevant prior decisions,
constraints, prohibitions and protected boundaries. Delegation never expands
Task/CR scope, external authority, credential access, publication or production
rights. Validation and independent acceptance follow the adopted
[Independent Review methodology](../vibevm/vibedeps/org.jresearch.ai.development-governance/12.5.0/vibevm/vibespecs/protocols/independent-review.md)
and [native Reviewer binding](../reviewer/README.md#independent-review-and-finding-provenance).

Relay implements TH-012/TH-013 preservation through ordinary task commits and
terminal worktree reconciliation, including BLOCKED results. Its worker and
collector may have different filesystem access: classify residue from actual
work, ownership and permissions, rather than its filename or a clean-status
claim. Do not widen permissions, reset, blindly commit, publish or retry
arbitrary residue to make collection green. The terminal result identifies
remaining uncommitted/non-ignored work, cause and reconciliation/access boundary.
Automatic workers hand commits to trusted Writer and retain no publication
authority.

The shared-group umask does not override explicit `0600` files, `0700`
directories, ACLs or atomic replacement modes. Automatic collection therefore
uses the fixed trusted Writer after checking the exact admitted journal and
containment. Its bounded reader can read authorized task-owned checkout source
without broadening worker file permissions. The worker need not chmod generated
source to satisfy the collector. Missing bytes, unsafe paths, cross-device or
hard-link acquisition and truly inaccessible objects still fail complete
observation; private mode alone does not. The
[collector contract](../controller/README.md#collector-identity-and-separate-host-qualification)
explains the safe diagnostics and retained-evidence boundary.

These worktree reconciliation and ownership requirements protect useful source,
ordinary worker collection/publication and state outside disposable TEST.
Disposable TEST state follows [TEST Environment Authority](#test-environment-authority)
and needs no individual-file ownership proof before cleanup inside its known
sandbox boundary.

A successful, contained, durable Task PR/Outcome handoff can carry a visible
`UNCOMMITTED_WORK_REMAINS` warning when residue remains. That warning does not
prove the residue is disposable or accepted: material execution warnings remain
mandatory decision inputs at the next owner/review boundary. A safely imported candidate with incomplete residue observation carries
`WORKTREE_OBSERVATION_INCOMPLETE`; retained local state stays unknown. Candidate
validation, uncertain publication, lost evidence and unknown containment remain
automation failures. A contained cleanup failure may preserve a completed result
with `RUNTIME_CLEANUP_FAILED`, while its resource remains retained and unavailable
for reuse. No second worker pass or cleanup daemon is authorized.

This policy applies inside one authorized execution. For Relay this is one
admitted invocation; standalone work does not manufacture native records.
Relay still reserves a
single execution per attempt and refuses blind retries, including after a crash.
Replaying returned-result verification/publication does not re-execute Codex.
Fresh launch commands, publication recovery, merge and deployment retain their
own authority boundaries. Payload bounds, timeouts and Git-provenance limits
also remain in force.

The policy is supplied to the governed worker and manual handoff from the
shared [execution-policy module](../runtime/src/execution-policy.mjs). The
[routing contract](../controller/README.md) defines continuation mechanics.


## TEST Environment Authority

A manual or automatic Codex execution that owns disposable TEST has full
operational control over TEST effects within the owner's established
administrative authority. It may create, expand, reconfigure, replace, remove,
reset and rebuild TEST resources, including supporting services, repositories,
workflows and runners. The initial inventory is a starting point. Choose
suitable tools, shells, validation and recovery for the operation without
another Task, Step or per-operation owner approval.

The boundary is the effect of the operation. TEST-specific configuration of
shared infrastructure is within scope when the operation preserves PROD and
other non-TEST users, configuration, data, credentials and external effects.
For example, a TEST route or upstream may be changed through an authorized
shared nginx reload when the affected configuration and service behavior can be
confined appropriately. A separate instance, namespace or host is an option.
Keep other Tasks' resources and independently governed systems protected.
Use proportionate evidence for the target, authority and effects. Actual
provider constraints and established privileges apply, including App and
runner administration. A repository's name supplies no authority. Keep
credentials out of checkouts, workers, public records and logs.

For disposable TEST setup, fixtures and supporting repositories, choose direct
updates or PRs, merge methods, checks, review, publication and cleanup as
appropriate. Relay adds no blanket independent approval, squash, exact-head
merge guard, Draft/Ready, signing, Issue closure or Writer/Reviewer ceremony for
those operations. Synthetic and resettable records are valid fixture tools.
Genuine Relay qualification still uses its actual control: use native admission
to test real execution, trusted Writer or Reviewer and genuine independence to
test those publication or review guarantees, and the original-operation recovery
path to substantiate replay and uncertain external effects. Report exactly
which installed revisions, identities, interfaces and outcomes were exercised.

An execution may install or exercise its authorized product candidate in TEST
before product acceptance. Product-source acceptance still requires independent
exact-head review and the normal source checks. TEST authority supplies no
product merge, release, Task closure, PROD operation or new external privilege.
Preserve real admission, replay, trusted publication and credential boundaries,
and reconcile genuine uncertain effects before dependent operations. Retain
evidence needed for the claims being made. Suitable direct cleanup or rebuilding
may replace production recovery procedures for disposable TEST state.

Before using the shared TEST contour, atomically claim its
[host-local marker](test-environment-lock.md). Keep the claim through use,
verification and cleanup. Return usable TEST and release only the execution's
own claim after completion or handled failure. A competing claim prevents use
of that shared contour. Continue useful independent work, arrange authorized
independent TEST capacity or wait as appropriate. Interrupted ownership requires
confirmation that the holder has stopped and TEST is usable before recovering
the exact claim. Age alone grants no takeover.

## Proportional controls and operator usability

The complete common control and requirement-origin procedures are the adopted
pinned [Shared Governance 12.5.0 Proportional Controls](../vibevm/vibedeps/org.jresearch.ai.development-governance/12.5.0/vibevm/vibespecs/protocols/proportional-controls.md)
and [Requirement Authority](../vibevm/vibedeps/org.jresearch.ai.development-governance/12.5.0/vibevm/vibespecs/protocols/requirement-authority.md)
protocols. Read each complete topic when its trigger applies, through the
[root adoption and routing](../AGENTS.md). Ordinary execution reads committed
files offline; maintenance uses the pinned lock and materialized content.

### Relay bindings

The owning project's current scope and canonical owner authorization mean the
live Issue/CR and, for migrated Tasks, its trusted Decisions and protected
admission. Retained schema-v3 attempts keep their selected complete Request.
Shared guidance grants no Step, execution, publication, acceptance,
recovery, deployment, merge or closure permission. Keep worker, Writer and
independent Reviewer responsibilities separate and retain all existing
credential, trust, runtime and production boundaries.

The adopted [Contract and Decision Maintenance protocol](../vibevm/vibedeps/org.jresearch.ai.development-governance/12.5.0/vibevm/vibespecs/protocols/contract-and-decision-maintenance.md)
owns material contract-change and durable-decision semantics. Relay's
[Task/Decision binding](../AGENTS.md#material-useroperator-contract-change-gate)
retains `OWNER_DECISION_REQUIRED` until canonical owner amendment; consumer
adoption does not alter native authority or authorize a runtime change.

Use Relay's existing Task/PR, native checks, independent exact-head review and
one Writer Outcome for evidence and disposition. Required full candidate
checks and warning acquisition below remain product requirements. Shared IR
owns finding provenance and exact-result evidence; shared PC owns assessment
of the simplest authorized operator path.

[Consumer maintenance and rollback](vibevm.md) describe the reviewed source,
lock and slot identity path. A missing or drifted shared file is an evidence
and routing gap: preserve available Relay authority and restore reviewed Git
content; do not invent a substitute procedure or resolve policy at session time.

## Execution warning disposition

The adopted [Independent Review protocol, IR-008](../vibevm/vibedeps/org.jresearch.ai.development-governance/12.5.0/vibevm/vibespecs/protocols/independent-review.md#IR-008)
and [Task Handoff protocol, TH-018/TH-026](../vibevm/vibedeps/org.jresearch.ai.development-governance/12.5.0/vibevm/vibespecs/protocols/task-handoff.md#TH-018)
own common warning disclosure, evidence gaps and continuation semantics. Relay
requires that inspection before review, continuation, merge, closure or an owner
decision. Its supported primary acquisition surfaces, after actual job, check
or runtime execution has begun, are:

- Relay/Codex Outcomes, including explicit warning fields and
  `COMPLETED_WITH_WARNINGS`;
- GitHub job/check execution annotations; and
- Relay/controller/Actions execution annotations associated with the attempt.

Compiler, test, installer, Git and similar warnings
are secondary unless they are surfaced as execution warnings or materially
affect authority, security, correctness, acceptance or operability.

Relay's disposition also records the action's owner/deadline when applicable
and its effect on the current native verdict or continuation decision.

GitHub service-level or pre-execution workflow annotations and platform policy
banners visible only in the UI are outside mandatory automated acquisition until
a supported API suitable for public and private repositories exists. Do not
scrape rendered HTML or use browser cookies/session state as a fallback. The
acquisition scope defines the native completeness claim; `none_observed` means
no warning was observed within that supported scope. Apply IR-008 to known
warnings and excluded-surface limits.

## Developer stop evidence

During repository development, a terminal BLOCKED handoff states established
facts, eliminated material hypotheses, the diagnostic frontier, remaining safe
read-only actions, the exact evidence/authority/capability boundary and the next
human action. Continue useful authorized diagnosis before declaring a technical
blocker. A local unresolved observability gap is a same-goal defect when it can
be repaired safely. No diagnosis requirement overrides a protected boundary.

A technical BLOCKED handoff with no source delta includes a compact
`Technical Blocker Resolution Contract` with evidence-backed, nonempty fields:

- `root_cause_status`: established cause or exact remaining uncertainty.
- `reproduction_status`: safe reproduction performed and its result.
- `diagnosability_status`: whether another occurrence can be identified.
- `source_delta_status`: why no materially useful authorized correction remains.
- `cleanup_boundary_status`: preserved work, safe cleanup and protected next step.

This is conditional terminal evidence, not a new ledger or a debugging algorithm.
