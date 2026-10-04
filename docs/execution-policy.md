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


## Proportional controls and operator usability

Mandatory controls must scale to a concrete accepted risk. A control is not
justified solely because it can prevent a defect or because a stricter pattern
exists. Prefer the cheapest mechanism that keeps the material risk acceptable.

Behaviorally free hardening may be applied without a separate owner decision
when it preserves existing supported workflows and adds no material operator
work, platform restriction, prerequisite, gate, trust boundary, recovery burden
or false-positive surface. Examples include setting safe attributes on an
already-owned file, avoiding secret logging, or choosing an equivalently usable
safer API.

A cost-bearing security or validation control requires explicit canonical owner
authorization before it becomes mandatory. Treat a control as cost-bearing when
it does any of the following materially:

- blocks or narrows an existing or common supported workflow or environment;
- adds an operator command, separate checkout, platform/filesystem requirement,
  administrative prerequisite, credential step, or recovery step;
- introduces or tightens a trust, privilege, sandbox, ACL or execution boundary;
- adds a mandatory validation gate, broadens the required validation surface, or
  makes unrelated baseline debt block the current task;
- adds persistent state, synchronization, lifecycle or failure modes; or
- materially increases execution time, maintenance, review friction, false
  positives, or control-induced defects.

Before proposing such a control, make the justification decision-grade: state
the attacker or failure capability, the concrete path to harm, the resulting
impact or privilege, why existing controls are insufficient, and the operator
and maintenance cost of the proposed control. Treat accepting the risk or doing
nothing as a valid option; a security or test preference is not authority.

Evaluate human behavior as part of control effectiveness. Consider how often an
ordinary user will encounter the control, whether the compliant path is
materially harder than an obvious workaround, and whether friction is likely to
cause disabling, bypass, unsafe local storage, duplicated state or abandonment
of the product. A control that predictably drives users toward a simpler unsafe
workaround is not automatically a security improvement.

For visible, local, reversible failures that are cheap to diagnose and rerun,
prefer simple detection, warning and recovery over recurring preventive
machinery unless a concrete accepted risk requires blocking. Retain stronger
prevention for silent, propagating or irreversible failures and for material
credential, privacy/compliance, production, publication, merge or other
protected-boundary risks.

Common supported environments should work by default. A filesystem, platform,
permission shape, unrelated service or other unusual local condition is not by
itself a reason for a hard failure merely because a stricter configuration is
possible. Bind a hard block to a material accepted invariant and use a warning
or bounded recovery when that preserves the invariant with lower operator cost.

Independent review of a change that affects controls or operator workflow must
also exercise the simplest owner-facing black-box path required by canonical
authority. Review for unnecessary state, gates, authority coupling, prerequisites
and operator-visible actions in addition to implementation correctness. An
unauthorized material operator-contract delta remains
`OWNER_DECISION_REQUIRED` under the repository's existing contract-change gate.

## Execution warning disposition

Execution warnings remain decision inputs even after a successful run. Before
review, continuation, merge, closure or an owner decision, inspect the primary
warning surfaces that are applicable to the execution:

- Relay/Codex Outcomes, including explicit warning fields and
  `COMPLETED_WITH_WARNINGS`;
- GitHub workflow/run-level annotations and platform policy warnings; and
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
warnings were observed.

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
