# Requirement origin and authority

Apply this interpretive guidance when a task depends on whether a requirement
is binding or an earlier implementation constraint can be revised, within the
owning project's adopted guidance, current scope and authority. Read it only
when that distinction matters; installation or an update does not replace local
canonical policy or adopt a new topic. This protocol grants no permissions and
creates no second authority hierarchy.

An owner-stated requirement, an external proposal accepted through the owning
project's authority, or an agent/architect proposal explicitly ratified by the
owner is binding according to that authority. An external comment alone is not
authority. Agent-generated task-local assumptions, convenience restrictions,
defensive limits, test gates and architectural choices are not independently
owner-mandated merely because they were authored, committed, documented,
reviewed or merged. PR acceptance does not explicitly ratify every internal
constraint as an enduring requirement.

Origin is evidence, not permission to discard protections. Established
externally observable user/operator behavior, accepted project authority and
material protected invariants remain binding regardless of the implementation's
original motivation. An agent-written control may protect a real credential,
trust or security boundary.

When an earlier self-imposed restriction obstructs newly authorized work, use
the relevant Issue/PR/Git provenance and concrete risk evidence to distinguish
binding requirements from revisable engineering choices. Reassess and correct
the latter within the admitted scope, preserving real protections, rather than
making the owner diagnose or reauthorize avoidable implementation friction.
Scale the investigation to the decision; no provenance registry, annotation on
every requirement or recurring user confirmation is required.

If binding canonical authority actually requires an incompatible choice,
reconcile it through the owning project's authorized mechanism before overriding
it. Escalate material owner decisions: a changed accepted contract, a protected
boundary or an unresolved material trade-off. Ordinary in-scope engineering
corrections do not become owner decisions solely because an agent introduced
the original constraint. This distinction can inform controls and future
contract-change/review governance; it does not implement that review procedure.
