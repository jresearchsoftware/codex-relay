# Small improvements in a future suitable change

<a id="SI-001"></a>
**SI-001 — Separate opt-in adoption.**

Apply this topic only when the owning project explicitly adopts it in accepted
human-owned AGENTS or equivalent guidance. Package installation, version updates,
Task Handoff adoption and cross-topic references do not activate it. It covers
small source-change follow-ups in ordinary GitHub Issues in the repository that
owns the correction. It grants no execution, scope expansion, review, merge,
release, label/settings mutation, consumer-adoption or closure authority.
Retain existing local rules until separately reviewed adoption reconciles them.

<a id="SI-002"></a>
**SI-002 — Existing semantic owners.**

This topic owns candidate capture, discovery, proposed inclusion and disposition.
[Contract and decision maintenance](contract-and-decision-maintenance.md#CD-005)
retains accepted reusable-decision promotion and same-change human guidance;
[Task Handoff](task-handoff.md) retains chronological authority, results,
independent acceptance and continuation;
[Requirement Authority](requirement-authority.md) retains proposed versus binding
requirements. References adopt none of those topics. Where not adopted, use the
project's corresponding local rules. Preserve stronger native admission,
Writer/Reviewer identity, protected actions and review requirements.

<a id="SI-003"></a>
**SI-003 — Capture a bounded candidate.**

Record an independently actionable deferred correction promptly as an ordinary
Issue in its owning repository, reusing an existing Issue when appropriate.
Apply the exact label `small-improvement` as the mandatory discovery key through
the project's authorized tracker path. The optional title prefix
`Small improvement:` helps readers but is never a lookup dependency. An Issue
without that label is not discoverable through this mechanism; report unavailable
label capability and use the owner's existing tracker process rather than claim
it is queued. Creating the label itself needs local authority.

Keep enough evidence to understand the problem, intended correction, affected
surface, discovery provenance, why it is deferred and proportionate validation.
Use the Issue body/discussion; no new form, ledger, bot or controller is required.
A label records a candidate, not an accepted requirement or execution admission.
Routine corrections already inside admitted scope need no extra Issue or cycle.

<a id="SI-004"></a>
**SI-004 — Eligibility is semantic.**

Select only a bounded, understandable correction relevant to the receiving
change, in the same owning repository, that can be implemented and reviewed
with it without obscuring its purpose. Size is risk and contract impact, not
line count. Check dependencies, conflicts and ownership before proposing it.
Urgent incidents, substantial features, unresolved architectural or material
operator-contract choices, protected credential/production work and corrections
with unresolved dependencies or ownership need their ordinary authorized path.
Reassess candidates that grow or become urgent; do not delay required work
indefinitely for a convenient PR. Small package edits still need normal version
classification and release authority.

<a id="SI-005"></a>
**SI-005 — Discover at a suitable source-changing opportunity.**

When preparing a suitable code/source-changing Task, its first source-changing
Step if earlier work was analytical, or a relevant Change Request (CR), inspect
open Issues with the exact `small-improvement` label in that repository. Filter
for relevant eligible candidates and explicitly notify the owner with their IDs
and proposed inclusion in the receiving scope. No suitable candidate is a valid
result; it does not block unrelated work or require batching.

Analysis-only work need not scan under this topic. Do not rescan on every inner
correction or subsequent Step solely as ceremony; refresh on materially changed
receiving scope or new relevant information. There is no cross-repository scan,
periodic audit, queue-empty gate or automatic Task injection. A project's broader
separately accepted discovery rule still applies until explicitly reconciled.

<a id="SI-006"></a>
**SI-006 — Authorize receiving scope before implementation.**

Proposed inclusion must be accepted through the receiving project's existing
Task/CR authority before execution. State the selected Issue IDs and bounded
corrections in that authority; do not silently extend scope from a search result,
label, source Issue or review suggestion. For material post-admission Task scope
changes, use the existing owner Task Decision mechanism and supported admission
path. A PR-specific CR cannot grant Task-wide scope authority it does not own.
Already delegated in-scope corrections need no new approval ritual.

Do not disturb an already approved PR solely to add unrelated minor work. Record
it for a future suitable change. A genuine required or urgent correction follows
existing authority and fresh-result review rules, not this deferral shortcut.

<a id="SI-007"></a>
**SI-007 — Integrate and assess the combined result.**

Link each accepted candidate to the receiving Task and PR and retain the source
Issue's provenance and authorship. Identify the included correction and any
excluded remainder. Implement together, run normal tests for the changed behavior
and coupled paths, and use one independent PR review of the combined exact
result. No separate execution cycle, PR, approval or ceremony-only commit is
required for each tiny Issue. Applicable checks, changed-head rereview, package
versioning, Draft/Ready and protected boundaries retain their existing meaning.

The receiving result records what was delivered, checks, warnings and remaining
work. Selection, scheduling, a pushed commit or successful tests do not prove
accepted integration. Preserve the project's normal merge and closure ownership;
links or automatic closing keywords cannot bypass it.

<a id="SI-008"></a>
**SI-008 — Keep unfinished work discoverable.**

Keep the source Issue open and traceable until actual accepted integration is
evidenced, then reconcile it through authorized closure with the receiving PR
and integrated revision. Scheduling or transfer alone does not close it as fixed.
Retain the discovery label while work remains pending, including while scheduled,
unless separately accepted local tracker rules require a different label lifecycle;
that binding must preserve discovery of unfinished work through explicit links.

For deferral, record the reason and retain discoverability. If the receiver is
cancelled, drops the correction or delivers only part, record what happened,
retain or restore pending discovery and identify exactly what remains. Do not
mark a partially delivered Issue fixed. If a candidate is duplicate, superseded
or no longer needed, record evidence and the surviving reference or reason, and
use the project's authorized tracker disposition without claiming a fix occurred.
Age alone never closes or executes it. No suitable opportunity can leave it
pending; urgency or increased scope routes it to ordinary authorized work.

The [usage guide](../guides/small-improvements.md) illustrates adoption, lookup
and separately owned consumer migration. It adds no automatic behavior.
