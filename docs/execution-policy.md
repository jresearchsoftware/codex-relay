# Progress-bounded execution

An admitted Codex execution may inspect, diagnose, make bounded corrections
and rerun relevant validation until its goal is complete, while each next
action has concrete evidence and remains within admitted authority. There is
no fixed correction-count default. Repeating the same failed action without
new evidence is not progress.

Stop and preserve useful work when:

- a human decision or additional authority is required;
- the next material correction is ambiguous or no justified next action remains;
- the same failure repeats without new evidence;
- prior execution state is unknown, prior execution is uncontained, or an
  external mutation has an ambiguous result;
- repository, credential, security or production authority is uncertain.

For state wholly inside an explicitly isolated disposable TEST sandbox, apply
[TEST Environment Authority](#test-environment-authority): uncertain or failed
TEST state may be deleted and rebuilt without forensic preservation or a
protected recovery procedure. Stop if the sandbox boundary or an effect outside
it is uncertain; disposable TEST authority does not resolve that uncertainty.

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
rights. Completion requires applicable validation;
report unavailable checks honestly and never replace independent acceptance
with a worker's success claim.

Before every terminal return, including BLOCKED, reconcile task-owned worktree
state when safe. Preserve useful changes in ordinary task commits and leave
unrelated work untouched. Remove only confirmed disposable generated residue;
ignore repeatable artifacts only when doing so does not hide useful work.
Determine the distinction from the actual work, ownership and permissions, not
from a filename or a clean status claim. The worker and collector can have
different filesystem access. Do not widen permissions, reset, blindly commit,
publish or retry arbitrary residue to make a check green. Report remaining
uncommitted/non-ignored work, its known cause and any reconciliation/access
boundary in the terminal summary. Automatic workers hand commits to trusted
Writer and retain no publication authority.

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

This policy applies inside one admitted invocation. Relay still reserves a
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

The complete reusable procedure now has one semantic owner: the committed
[development-governance 2.1.0 proportional-controls protocol](../vibevm/vibedeps/org.jresearch.ai.development-governance/2.1.0/vibevm/vibespecs/protocols/proportional-controls.md).
Read it in full for relevant controls, including behaviorally free hardening,
and use its existing-proof rule when considering another process step. For a
relevant requirement-origin decision, read its
[requirement-authority protocol](../vibevm/vibedeps/org.jresearch.ai.development-governance/2.1.0/vibevm/vibespecs/protocols/requirement-authority.md).
Root AGENTS adopts these two unchanged topics; other bundled procedures remain
unactivated references, as recorded in the [ownership mapping](relay-guidance-ownership.md).
Normal execution reads these committed files
without VibeVM, resolution, networking or another owner action.

### Relay bindings

The owning project's current scope and canonical owner authorization mean the
live Issue/CR and, for migrated Tasks, its trusted Decisions and protected
admission. Retained schema-v3 attempts keep their selected complete Request.
Shared guidance grants no Step, execution, publication, acceptance,
recovery, deployment, merge or closure permission. Keep worker, Writer and
independent Reviewer responsibilities separate and retain all existing
credential, trust, runtime and production boundaries.

The full [material user/operator contract-change gate](../AGENTS.md#material-useroperator-contract-change-gate)
remains operative and Relay-owned, including implementation-time safe
preservation/stop, comparison of changed surfaces before independent approval,
and prohibition of retrospective authority normalization. An unauthorized
material delta remains `OWNER_DECISION_REQUIRED` until canonical owner
amendment. The shared control protocol does not replace that broader gate.

Use Relay's existing Task/PR, native checks, independent exact-head review and
one Writer Outcome for evidence and disposition. Required full candidate
checks, warning acquisition below, finding provenance and the simplest
owner-facing path required by canonical authority remain binding. Existing
proof about an earlier head does not qualify a changed candidate.

[Consumer maintenance and rollback](vibevm.md) describe the reviewed source,
lock and slot identity path. A missing or drifted shared file is an evidence
and routing gap: preserve available Relay authority and restore reviewed Git
content; do not invent a substitute procedure or resolve policy at session time.

## Execution warning disposition

Execution warnings remain decision inputs even after a successful run. Before
review, continuation, merge, closure or an owner decision, inspect the primary
warning surfaces that are applicable to the execution and exposed through
supported GitHub/runtime APIs after actual job, check or runtime execution has
begun:

- Relay/Codex Outcomes, including explicit warning fields and
  `COMPLETED_WITH_WARNINGS`;
- GitHub job/check execution annotations; and
- Relay/controller/Actions execution annotations associated with the attempt.

Do not replace inspection of those primary surfaces with a text search for the
word `warning` in job logs. Compiler, test, installer, Git and similar warnings
are secondary unless they are surfaced as execution warnings or materially
affect authority, security, correctness, acceptance or operability.

Disposition every material warning with its source/provenance, impact, relation
to current scope, resolution or remaining limitation, next action/owner/deadline
when applicable, and effect on the current verdict or continuation decision.
Green status is not a disposition. If a required primary warning or annotation
surface cannot be inspected, state the evidence gap and do not claim that no
warnings were observed within the required supported scope.

GitHub service-level or pre-execution workflow annotations and platform policy
banners visible only in the UI are outside mandatory automated acquisition until
a supported API suitable for public and private repositories exists. Do not
scrape rendered HTML or use browser cookies/session state as a fallback. The
excluded surface alone does not block independent review or make supported
execution evidence incomplete. Completeness describes acquisition within the
required supported scope; `none_observed` means no warning was observed within
that scope. Neither proves that no UI-only warning exists. An out-of-scope
acquisition limit does not dispose of a material warning already known from
other evidence.

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
