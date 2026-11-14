# Requirement origin and authority

<a id="RA-001"></a>
**RA-001 — Applicability and authority.**

Apply this interpretive guidance when a task depends on whether a requirement
is binding or an earlier implementation constraint can be revised, within the
owning project's adopted guidance, current scope and authority. Read it only
when that distinction matters; installation or an update does not replace local
canonical policy or adopt a new topic. This protocol grants no permissions and
creates no second authority hierarchy.

<a id="RA-002"></a>
**RA-002 — Binding authority versus engineering choice.**

An owner-stated requirement, an external proposal accepted through the owning
project's authority, or an agent/architect proposal explicitly ratified by the
owner is binding according to that authority. An external comment alone is not
authority. Agent-generated task-local assumptions, convenience restrictions,
defensive limits, test gates and architectural choices are not independently
owner-mandated merely because they were authored, committed, documented,
reviewed or merged. PR acceptance does not explicitly ratify every internal
constraint as an enduring requirement.

<a id="RA-003"></a>
**RA-003 — Protected behavior survives origin analysis.**

Origin is evidence, not permission to discard protections. Established
externally observable user/operator behavior, accepted project authority and
material protected invariants remain binding regardless of the implementation's
original motivation. An agent-written control may protect a real credential,
trust or security boundary.

<a id="RA-004"></a>
**RA-004 — Proportionate provenance and correction.**

When an earlier self-imposed restriction obstructs newly authorized work, use
the relevant Issue/PR/Git provenance and concrete risk evidence to distinguish
binding requirements from revisable engineering choices. Reassess and correct
the latter within the admitted scope, preserving real protections, rather than
making the owner diagnose or reauthorize avoidable implementation friction.
Scale the investigation to the decision; no provenance registry, annotation on
every requirement or recurring user confirmation is required.

<a id="RA-005"></a>
**RA-005 — Resolve material authority conflicts.**

If binding canonical authority actually requires an incompatible choice,
reconcile it through the owning project's authorized mechanism before overriding
it. Escalate material owner decisions: a changed accepted contract, a protected
boundary or an unresolved material trade-off. Ordinary in-scope engineering
corrections do not become owner decisions solely because an agent introduced
the original constraint. This distinction can inform controls and future
contract-change/review governance; it does not implement that review procedure.

<a id="RA-006"></a>
**RA-006 — Initiative without silent obligation creation.**

When drafting/amending Tasks, defining acceptance or validation, assessing results
or planning continuation, derive mandatory outcomes, prerequisites and completion
gates from owner intent, accepted contracts/protected invariants or explicit scope
Decisions. A suggestion does not acquire authority by appearing in a Task, prompt,
review, plan or earlier response. Actively surface risks, defects, alternatives,
opportunities and optional validation, including beyond the request. Distinguish
in-contract defects/protected obligations, discretionary scope proposals and
routine implementation/testing choices within delegated scope. The last category
needs no separate permission; proposals remain optional until accepted.

Bound required proof to the deliverable and accountable component.
An unrelated tool's cold installation, downstream
application or consumer configuration is mandatory only within accepted scope or
when demonstrably necessary to establish the producer's promised contract. Invalid
required manifests/dependencies, missing agreed proof, supported-interface defects,
security/credential boundaries, rights failures and owner-required integration
tests retain their usual blocking effect. Do not relabel them as downstream.

Before adding a Step, blocker, CR or waiting condition, reconcile apparent
agent-authored obligations with their origin and current owner direction. Preserve
binding canonical authority until any material discrepancy is resolved through
existing owner Decision/contract mechanisms; neither silently ignore it nor
execute another cycle solely to satisfy an unratified suggestion.

Make consequential proposals and requested dispositions prominent and unambiguous:
state the exact recommended outcome for each finding, especially scope changes,
downgrades, waived checks and deferrals. Prefer one clear consolidated decision
over approvals of routine details. Clarify materially ambiguous owner responses;
a generic instruction to fix findings does not approve an obscured deferral.
Use existing Task/review records, with no provenance registry, universal checklist,
second approval, extra test gate or release ceremony.
