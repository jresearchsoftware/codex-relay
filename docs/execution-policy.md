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

An owner may designate an isolated TEST environment for autonomous Codex
development and qualification. Record that designation and its concrete
environment/repository/configuration boundary in canonical Task authority and
the consumer's owner-controlled runbook. Within that boundary, standing owner
authorization covers the full TEST cycle: create/delete TEST resources, change
TEST repositories, configuration and workflows, create/review/merge TEST PRs,
install/upgrade Relay, recover state, run end-to-end qualification and correct
proven in-scope failures. Ordinary operations inside that authorized environment
do not require repeated owner confirmation or another execution phase.

The boundary is the environment, not the operation type. A prohibition on
product-source merge does not prohibit TEST repository merges. Use supported
public interfaces and existing qualified App permissions; verify exact targets,
ownership, isolation and known contained state. Preserve replay suppression,
safe non-force Git publication, recovery guards and truthful evidence. A TEST
review or merge qualifies the TEST change; it is not independent acceptance of
the product candidate. Automatic workers still delegate publication to Writer.
Within designated TEST, an exact Task-authorized development candidate may be
projected, installed or selected for supported recovery to qualify it before
independent product acceptance; product and PROD acceptance remain separate.

Standing TEST authority excludes PROD, product repositories outside the TEST
circuit, shared infrastructure, foreign resources and changes to external
permissions, App installations or credentials. Stop at those boundaries or an
unresolved isolation/state/mutation uncertainty, with the precise action needed.
An authorized TEST installation or activation uses the same public deployment
safety checks; it does not bypass them or authorize private backend operations.
Successful TEST proof does not establish PROD installation or acceptance.

Task #115's trusted owner clarification designates
`jresearchsoftware/codex-relay-testbed`, its `deploy/relay.json` and documented
isolated TEST deployment as the standing autonomous environment. The direct
owner authorization, recorded in
[Decision 6112655517](https://github.com/jresearchsoftware/codex-relay/issues/115#issuecomment-6112655517),
authorizes both current TEST actions and adoption of this section. This policy
cannot authorize its own adoption or designate an additional environment.
Other procedures reference this section rather than defining TEST exceptions.

## Proportional controls and operator usability

The complete reusable procedure now has one semantic owner: the committed
[development-governance 1.1.0 proportional-controls protocol](../vibevm/vibedeps/org.jresearch.ai.development-governance/1.1.0/vibevm/vibespecs/protocols/proportional-controls.md).
Read it in full for relevant controls, including behaviorally free hardening,
and use its existing-proof rule when considering another process step. For a
relevant requirement-origin decision, read its
[requirement-authority protocol](../vibevm/vibedeps/org.jresearch.ai.development-governance/1.1.0/vibevm/vibespecs/protocols/requirement-authority.md).
Root AGENTS adopts these topics; the bundled package-versioning procedure is
not adopted as Relay policy. Normal execution reads these committed files
without VibeVM, resolution, networking or another owner action.

### Relay bindings

The owning project's current scope and canonical owner authorization mean the
live Issue/CR and, for migrated Tasks, its trusted Decision and complete Task
Request. Shared guidance grants no Step, execution, publication, acceptance,
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
