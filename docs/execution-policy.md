# Progress-bounded execution

The complete common execution-cycle, correction, preservation and stop semantics
are owned by the adopted pinned
[Shared Governance 5.0.0 Task Handoff protocol](../vibevm/vibedeps/org.jresearch.ai.development-governance/5.0.0/vibevm/vibespecs/protocols/task-handoff.md),
especially TH-006–TH-013 and TH-026. Read the complete protocol when executing,
handing off or continuing governed work. This document binds it to Relay's
admitted invocation and supported standalone/manual route.

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
[Independent Review methodology](../vibevm/vibedeps/org.jresearch.ai.development-governance/5.0.0/vibevm/vibespecs/protocols/independent-review.md)
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

The existing shared-group umask does not override a tool's explicit `0600`
file or `0700` directory mode, including an atomic replacement. Newly created,
known public task-owned source must remain readable through the existing work
group for ordinary collection. A worker may correct only those owned public
files within its admitted authority; unknown or private content requires an
explicit access disposition. This is source reconciliation, not permission to
recursively chmod a checkout or to run ordinary collection as root. An
unreadable tracked file still blocks complete observation. The
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
mandatory decision inputs at the next owner/review boundary. Incomplete
collection, uncertain publication, lost evidence and unknown containment remain
automation failures. No second worker pass or cleanup daemon is authorized.

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

Any manual or automatic Codex execution that owns an explicitly isolated
disposable TEST environment has full operational control inside that sandbox.
Its established owner authority identifies the concrete environment,
repositories, configuration and resources that form the boundary. This is a
general standing policy, not an exception for an individual Task. No new
per-operation approval, Task, Step or Relay attempt is required for operations
inside that boundary.

Routine reproduction, related fixes, checks, representative deployment and
original-operation qualification remain the same bounded repair in that owned
sandbox. Do not split these iterations into extra Tasks, Steps or owner prompts.
Use the supported interface when qualifying that interface and report actual
installed source/consumer identities and operation results. A realistic TEST
success must identify material differences from PROD; it does not qualify an
untested deployment or erase an external prerequisite. Fresh real Relay
executions still require genuine native admission and preserve original events.

A shared disposable TEST installation has at most one owner Task at a time.
Establish its allocation before use, return it to normal working TEST state
and release ownership on handback. Competing Tasks wait or report BLOCKED.
The owner Task may recreate its dedicated sandbox without preserving its
preexisting disposable state or requesting permission for each operation;
preserve evidence required by the qualification being performed. An atomic
lease or semaphore is unnecessary unless actual concurrent demand warrants it.

Within the sandbox, Codex may choose suitable tools and shells, manage services,
edit or remove filesystem state, delete and recreate resources, rebuild,
install, reinstall, upgrade, reset failed TEST state and run qualification.
The authority includes TEST repositories, configuration, workflows and TEST
PR creation, review and merge using already available permissions. A prohibition
on product-source merge does not prohibit TEST repository merges.

Established standing owner authority may also include dedicated TEST GitHub App
installations, selected TEST repository grants and TEST-only permissions, TEST
runner registration/removal, and TEST runner-group membership and access policy.
For each operation, verify the authenticated App/installation and actual API
permission, exact dedicated target names/IDs, selected TEST repository allowlist,
trusted workflow/ref restrictions and isolation from shared or production
resources. Keep runner groups restricted to the authorized TEST repositories
and trusted workflows; labels alone do not establish that boundary. Once these
facts and the operation's owner authority are established, no additional
per-operation approval is required. Do not assume that source policy creates an
unavailable credential or administrative capability.

An owner-authorized local manual Codex session may authenticate directly with
the dedicated TEST Admin App: keep its PEM in the owner's private local storage
outside Git checkouts, generate a short-lived JWT and installation access token
on demand, verify read-only API access, then perform the authorized TEST
operations. Organization runner administration can grant organization-wide
technical access. When the owner explicitly accepts that scope, TEST-only
enforcement rests on the verified targets and governance instructions, not an
assertion that the token excludes production. This path requires no separate
admin helper, broker or server. Keep credentials out of repositories, workers,
GitHub publications and logs; ambiguous targets or shared-host effects remain
stop conditions.

Production-safe public lifecycle interfaces are optional for disposable TEST
cleanup and rebuilding. Codex may clean or reconstruct sandbox state directly;
it need not preserve that state for forensics, prove ownership of individual
files or use production recovery procedures. Existing global worktree,
deployment and recovery preservation rules do not impose those requirements
on disposable TEST state. Evidence needed to support a qualification claim must
remain truthful and sufficient for that claim; rebuilding alone does not prove
the discarded state or the supported product lifecycle.

The hard boundary is the sandbox. This authority excludes PROD, shared
infrastructure, foreign resources, product repositories outside the sandbox,
and external App permissions, installations or credentials outside established
authority. It does not grant new credentials, privileges or tools that an
execution does not physically possess. If a target or effect cannot be confined
to the established sandbox, stop at that boundary. Do not turn an unavailable
capability into an invented approval requirement for otherwise authorized TEST
operations.

An exact Task-authorized development candidate may be installed or exercised
inside the sandbox before independent product acceptance. TEST operations do
not grant product-source merge, PROD deployment, release, Issue closure or
independent acceptance. Normal source checks and independent exact-head review
remain binding. Writer retains responsibility for actual product and ordinary
Relay publication; original admission, replay suppression, trusted Git import
and protected credential boundaries remain intact. Resetting disposable TEST
state does not authorize re-executing an admitted Relay attempt or rewriting its
native GitHub authority/publication history. Disposable local TEST journals and
state may still be removed. TEST proof establishes only the behavior actually tested;
it does not establish PROD installation or acceptance.

Consumer runbooks may identify concrete sandboxes and operational facts;
other procedures reference this section rather than adding TEST-only approval,
preservation or recovery requirements.

## Proportional controls and operator usability

The complete common control and requirement-origin procedures are the adopted
pinned [Shared Governance 5.0.0 Proportional Controls](../vibevm/vibedeps/org.jresearch.ai.development-governance/5.0.0/vibevm/vibespecs/protocols/proportional-controls.md)
and [Requirement Authority](../vibevm/vibedeps/org.jresearch.ai.development-governance/5.0.0/vibevm/vibespecs/protocols/requirement-authority.md)
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

The adopted [Contract and Decision Maintenance protocol](../vibevm/vibedeps/org.jresearch.ai.development-governance/5.0.0/vibevm/vibespecs/protocols/contract-and-decision-maintenance.md)
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

The adopted [Independent Review protocol, IR-008](../vibevm/vibedeps/org.jresearch.ai.development-governance/5.0.0/vibevm/vibespecs/protocols/independent-review.md#IR-008)
and [Task Handoff protocol, TH-018/TH-026](../vibevm/vibedeps/org.jresearch.ai.development-governance/5.0.0/vibevm/vibespecs/protocols/task-handoff.md#TH-018)
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
The optional [Stop helper](../.codex/hooks/README.md) checks that extra contract only for
an explicitly technical, `none_justified` classification. Protected boundaries,
starting-state mismatches and unknown classifications must not acquire new
mutation obligations. A reminder permits at most one bounded read-only diagnostic
pass and never launches a worker, retries an external mutation or authorizes a
protected action. Relay admission, execution and publication do not depend on
this developer helper or its textual summary checks.
