# Contract changes and durable decisions

<a id="CD-001"></a>
**CD-001 — Explicit contract-maintenance adoption.**

Apply when materially changing a supported user/operator contract, carrying
accepted decisions into later work, or changing user/operator-visible behavior
or a Task/review/authorization workflow, only where the owning project explicitly
adopts this topic. Installation, update or a reference does not activate it.
Use the project's existing owner authority, Task/change and review mechanisms;
this guidance grants no execution, approval, merge, release or adoption authority.

<a id="CD-002"></a>
**CD-002 — Semantic ownership and local rules.**

This topic covers the contract/decision/documentation lifecycle. It does not
replace [requirement-authority](requirement-authority.md)'s distinction between
binding requirements and revisable engineering choices, or
[proportional-controls](proportional-controls.md)'s risk/cost and existing-proof
assessment. Those topics retain their own applicability. Where separately
adopted, [task-handoff](task-handoff.md) owns chronological Task authority and
result/acceptance semantics, and [independent-review](independent-review.md) owns
assessment methods. Otherwise retain the project's corresponding local rules;
these references adopt no additional topic.

## Preserve or authorize material contract changes

<a id="CD-003"></a>
**CD-003 — Authority for material contract changes.**

Before removing, replacing, renaming, disabling or otherwise materially changing
an existing supported capability or workflow, locate explicit owner authorization
in applicable canonical Task scope or Decisions. Material surfaces include
commands/entrypoints, required inputs, visible behavior, actor responsibilities,
manual/automatic transitions, added required actions, status/Outcome/recovery
behavior and supported client paths. Internal refactoring with equivalent
observable behavior needs no separate owner decision.

<a id="CD-004"></a>
**CD-004 — Preserve or reconcile unauthorized deltas.**

Implementation, security, test or reviewer preference does not independently
authorize a different contract. If preferable behavior emerges outside authorized
scope, preserve established behavior where safe or stop for an owner decision.
Do not normalize an implementation-originated delta into policy after the fact.
During independent assessment, compare material old/new behavior in every changed
surface against authorized functional and security requirements. An unauthorized
material delta remains non-approvable until the project's actual owner authority
records its disposition. Product-specific status names, schemas, actors and
remediation mechanisms remain local.

## Make accepted decisions durable

<a id="CD-005"></a>
**CD-005 — Promote durable accepted decisions.**

An owner-accepted reusable architecture, process, governance, security,
qualification or operational decision that affects later execution must not
remain chat-only. Before related work relying on changed executable Task
authority, carry that change into its canonical owner Decision through the project's existing
mechanism. Promote an independently reusable rule into the appropriate existing
policy, architecture, runbook or component contract through a suitable authorized
bounded change. A bounded reusable correction need not wait for the unrelated
remainder of a backlog item.

<a id="CD-006"></a>
**CD-006 — Durable policy versus task-local choices.**

Distinguish accepted durable policy from task-local choices or exceptions, temporary or
experimental choices and rejected ideas when later execution depends on that
distinction. Do not promote casual observations, unaccepted speculation or
one-off diagnostic facts. Promotion creates no authority by itself: retain the
owning project's acceptance and scope boundaries. Use existing records, without
a new decision ledger, automatic chat scraping or a mandatory extra Task solely
to record the decision.

## Keep human guidance consistent

<a id="CD-007"></a>
**CD-007 — Same-change human guidance.**

When a change or remediation actually changes user/operator-visible behavior or a
Task/review/authorization workflow, update affected human guidance and examples
in the same Task and PR where applicable (or equivalent project change), or explain there why none
needs updating. Check instructions against implementation and governing
contracts, including supported legacy behavior and local policy boundaries.
Use the existing change and review process; no separate documentation approval
gate, CI stage or standalone paperwork cycle is required.
