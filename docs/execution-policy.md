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

Do not use nested workers, subagents or fan-out unless separately authorized.
Keep the admitted model/effort fixed. Completion requires applicable validation;
report unavailable checks honestly and never replace independent acceptance
with a worker's success claim.

This policy applies inside one admitted invocation. Relay still reserves a
single execution per attempt and refuses blind retries, including after a crash.
Replaying returned-result verification/publication does not re-execute Codex.
Fresh launch commands, publication recovery, merge and deployment retain their
own authority boundaries. Payload bounds, timeouts and Git-provenance limits
also remain in force.

The policy is supplied to the governed worker and manual handoff from the
shared [execution-policy module](../runtime/src/execution-policy.mjs). The
[routing contract](../controller/README.md) defines continuation mechanics.

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
