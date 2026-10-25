# Proportional controls

<a id="PC-001"></a>
**PC-001 — Applicability and decision scope.**

Apply this protocol when a proposed control
changes operator work, supported environments, validation, trust or recovery.
Apply it within the owning project's current task scope and authority.

Explain the concrete path to harm and impact, existing protection, proposed
control cost, and the cheapest acceptable alternative. Include acceptance of the
risk when reasonable. Preserve supported workflows and assess how friction may
encourage bypass or abandonment. Distinguish behaviorally free hardening from a
cost-bearing control before prescribing mandatory changes.

Scale the explanation to the decision. A short assessment is enough for a small
local change. This protocol does not require a new checklist, approval service,
state ledger or extra operator step. Use the owning project's existing decision
and independent review records; the package itself grants no permissions.

# Proportional controls and operator usability

<a id="PC-002"></a>
**PC-002 — Proportionate risk and cost.**

Mandatory controls must scale to a concrete accepted risk. A control is not
justified solely because it can prevent a defect or because a stricter pattern
exists. Prefer the cheapest mechanism that keeps the material risk acceptable.

<a id="PC-003"></a>
**PC-003 — Behaviorally free hardening.**

Behaviorally free hardening may be applied without a separate owner decision
when it preserves existing supported workflows and adds no material operator
work, platform restriction, prerequisite, gate, trust boundary, recovery burden
or false-positive surface. Examples include setting safe attributes on an
already-owned file, avoiding secret logging, or choosing an equivalently usable
safer API.

<a id="PC-004"></a>
**PC-004 — Cost-bearing control boundary.**

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

<a id="PC-005"></a>
**PC-005 — Decision-grade justification.**

Before proposing such a control, make the justification decision-grade: state
the attacker or failure capability, the concrete path to harm, the resulting
impact or privilege, why existing controls are insufficient, and the operator
and maintenance cost of the proposed control. Treat accepting the risk or doing
nothing as a valid option; a security or test preference is not authority.

<a id="PC-006"></a>
**PC-006 — Operator behavior.**

Evaluate human behavior as part of control effectiveness. Consider how often an
ordinary user will encounter the control, whether the compliant path is
materially harder than an obvious workaround, and whether friction is likely to
cause disabling, bypass, unsafe local storage, duplicated state or abandonment
of the product. A control that predictably drives users toward a simpler unsafe
workaround is not automatically a security improvement.

<a id="PC-007"></a>
**PC-007 — Detection and recovery.**

For visible, local, reversible failures that are cheap to diagnose and rerun,
prefer simple detection, warning and recovery over recurring preventive
machinery unless a concrete accepted risk requires blocking. Retain stronger
prevention for silent, propagating or irreversible failures and for material
credential, privacy/compliance, production, publication, merge or other
protected-boundary risks.

<a id="PC-008"></a>
**PC-008 — Supported environments.**

Common supported environments should work by default. A filesystem, platform,
permission shape, unrelated service or other unusual local condition is not by
itself a reason for a hard failure merely because a stricter configuration is
possible. Bind a hard block to a material accepted invariant and use a warning
or bounded recovery when that preserves the invariant with lower operator cost.

<a id="PC-009"></a>
**PC-009 — Control and workflow assessment.**

Independent review of a change that affects controls or operator workflow must
also exercise the simplest owner-facing black-box path required by canonical
authority. Review for unnecessary state, gates, authority coupling, prerequisites
and operator-visible actions in addition to implementation correctness. An
unauthorized material operator-contract change needs the owning project's
explicit owner disposition before acceptance.

## Existing proof before another step

<a id="PC-010"></a>
**PC-010 — Reuse sufficient proof.**

Before adding another mandatory or ceremonial commit, review pass, validation
gate, approval, state transition, handoff or recovery action, determine whether
existing evidence already proves the same invariant for the relevant candidate.
Require an independently justified purpose, new or changed candidate evidence,
a concrete accepted risk or explicit authority for an additional step. A cheap
repetition still needs a purpose; stricter ceremony alone is not justification.
Reuse sufficient evidence in the owning project's existing records.

This does not waive mandatory independent review, required checks or revalidation
of a changed head. Evidence about a different candidate or invariant cannot
prove the current one. Avoiding duplicate proof grants no acceptance, merge,
publication or recovery authority and does not skip a separately justified
protected-boundary check.

## Reassess self-imposed control friction

<a id="PC-011"></a>
**PC-011 — Reassess implementation friction.**

When an agent-created safety, resource, platform or validation limit breaks an
otherwise supported and authorized workflow, investigate its original failure
mode, practical risk, operator burden and less disruptive alternatives. When
provenance affects the decision, read [requirement-authority](requirement-authority.md)
to distinguish binding requirements from revisable implementation choices.
Documentation, previous review or merge alone does not make an internal limit
an enduring owner mandate.

Prefer the smallest safe repair within the current Task, preserving real
protections. For example, an internally chosen response-size cap that makes
large Issue/PR review fail may warrant bounded paginated or streamed handling
when the risk evidence supports it. The example grants no authority to change
any particular runtime or consumer. Do not require the owner to diagnose or
reauthorize an arbitrary historical engineering limit merely because an agent
introduced it.

<a id="PC-012"></a>
**PC-012 — Retain protected requirements.**

A genuine owner-controlled requirement, material change to observable supported
behavior, credential/trust/security boundary or unresolved material risk still
requires the owning project's authorized disposition. Do not automatically
remove a historical restriction because an agent invented it; preserve accepted
contracts and protected invariants whatever their implementation origin. Use
the existing authority mechanism, not a new approval loop or standing ledger.

## Preserve scope when reviewing controls

<a id="PC-013"></a>
**PC-013 — Review-driven scope preservation.**

Before presenting a review blocker or proposed Task amendment, distinguish a
violation of an accepted requirement, existing supported contract or already
binding protected invariant from a newly proposed defense. Calling an absent
control a security defect does not make a new guarantee, historical prerequisite,
trust condition, operator step or architecture mandatory. Apply this distinction
in the existing owner-facing finding report, before a negative assessment or
Change Request is published; follow [IR-012–IR-015](independent-review.md#IR-012)
where that methodology is separately adopted, otherwise the local review method.

Compare the old and proposed supported user/operator paths, especially when
sharing or replacing an already used component. Explicitly quantify the changed
contract and operational cost at decision-relevant scale: affected workflows,
added actions/prerequisites, frequency and maintenance/recovery burden. State
uncertainty rather than inventing numeric precision. Consider the cheapest
acceptable alternative, including doing nothing or accepting a hypothetical risk
when applicable. A newly imagined stronger assurance is a proposed requirement,
not a proven implementation defect merely because it would prevent possible harm.

For an important newly discovered risk, explain severity, evidence, affected
behavior and control cost, and request an explicit owner decision on any scope
amendment through existing canonical authority. Until resolved, preserve current
authority and protected boundaries; do not insert the proposed control into a
negative review's required remediation or the next Step as if already authorized.
A material unresolved risk can justify discussion or a hold under current
authority without fabricating an earlier obligation or approving unsafe behavior.
True vulnerabilities/regressions violating existing obligations, missing evidence,
baseline debt and optional new protection retain distinct dispositions. This rule
adds no universal per-PR reapproval, reviewer, checklist, service, ledger or wait;
applicable local/specialist rules and stronger safety obligations remain in force.
