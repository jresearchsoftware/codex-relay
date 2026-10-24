# Independent review methodology and evidence

<a id="IR-001"></a>
**IR-001 — Explicit methodology adoption.**

Apply to independent assessment only when the owning project explicitly adopts
this topic. Installing/updating the package or reading a reference does not
activate it or replace local review policy. Use the project's canonical authority,
acceptance criteria, artifact-specific methods and authorized publication path.
This contract works manually, including for research and results without a PR.
It grants no execution, approval, merge, release, adoption or closure permission.

<a id="IR-002"></a>
**IR-002 — Lifecycle and stronger local boundaries.**

Where adopted, [task-handoff](task-handoff.md) owns result identity, Task/Step,
Decisions, Outcome routing and Direct/Deliberative acceptance. This protocol
substantiates the assessment; it creates no parallel acceptance authority.
Preserve stronger project-owned reviewer identity, checks and protected boundaries.

## Establish what is being assessed

<a id="IR-003"></a>
**IR-003 — Exact result and canonical criteria.**

Identify the complete actual result and its comparison baseline: exact commit
and substantive diff for a source PR, or the actual deliverable and identifiable
revision/evidence for a report, deployment, qualification or no-change result.
Do not invent a PR or SHA for a non-repository artifact. Refresh current canonical
requirements, authorized Decisions and applicable change requests. Independently
reconcile the result with the full goals, constraints and acceptance criteria,
including material omissions; the candidate's manifest or summary cannot decide
which requirements or source areas exist.

<a id="IR-004"></a>
**IR-004 — Primary evidence and operational surface.**

Inspect primary artifacts and relevant changed behavior. PR metadata, changed-file
names, an implementer's Outcome, an earlier PASS or green check summary are
navigation and claims, not proof that the substantive result was reviewed.
Read the complete substantive diff and affected source, generated output,
interfaces or analogous primary evidence needed to assess the result. For an
artifact consumed through a rendered or operational surface, inspect that surface
when it is part of the accepted contract; source shape alone cannot prove its
usability or observed behavior. Research review examines the actual argument,
source support, alternatives, tradeoffs and limitations against canonical goals.

<a id="IR-005"></a>
**IR-005 — Complete affected behavior and coupled paths.**

The first assessment covers the complete affected behavior and contract at that
exact result, not just altered lines. For a protocol change, inspect the entire
applicable protocol and material related clauses and consumers. For an algorithm,
trace the affected execution path, alternatives, boundaries and interactions.
For example, historical incompleteness and no-op tests in isolation do not prove
their coupled readiness/no-op path. Inspect the conditional path connecting them.

<a id="IR-006"></a>
**IR-006 — Material dependencies and disclosed scope.**

Bound investigation to the result and its material dependencies and risks.
Complete review does not mean reading every unrelated repository file or running
every possible experiment. Explain material uninspected or inaccessible surfaces
and how they limit the assessment; never describe a partial review as complete.

## Verify evidence and affected behavior

<a id="IR-007"></a>
**IR-007 — Exact-result validation and evidence reuse.**

Verify material validation through the primary records applicable to the exact
result: relevant test scope and outcomes, CI run/job/check identity and output,
annotations, artifact evidence or environment observations. Distinguish what was
independently inspected, rerun, reported by the implementer or unavailable.
Green but skipped, incomplete, stale or unrelated checks do not prove coverage.
Existing sufficient proof need not be rerun solely to be independent: inspect
its binding and substance. Required checks and human/owner confirmation remain
required; a deterministic validator proves only its mechanically checked facts.

<a id="IR-008"></a>
**IR-008 — Primary warning surfaces.**

Inspect applicable supported primary warning surfaces, including the Outcome
and execution/job/check/runtime annotations when those belong to the binding.
A log search for `warning` does not replace them. For every known material
warning retain source, impact, scope, disposition, next action and evidence gaps.
Unavailable required evidence is a gap, not absence of warnings. Unsupported
UI-only or pre-execution banners need no new acquisition workaround; that access
limit alone is not a defect, but a known material warning still needs disposition.

<a id="IR-009"></a>
**IR-009 — Authorized behavior and control impact.**

Assess correctness, omissions, security, compatibility, regressions and the
required user/operator workflow. Compare material old/new behavior in each
changed surface with authorized requirements; implementation or reviewer
preference cannot retroactively authorize a changed contract. An unauthorized
material delta requires the owning project's decision before acceptance.
For controls and operator-work changes, apply adopted
[proportional-controls](proportional-controls.md), including the simplest
authorized black-box path and unnecessary friction. Do not prescribe a protected
live action outside authority merely to obtain review evidence.

<a id="IR-010"></a>
**IR-010 — Cross-layer and active-reference closure.**

Follow coupled changes across relevant validators, consumers, alternate
entrypoints, generated projections, post-checks, regression coverage and active
operator guidance. Changed identifiers, endpoints or execution representations
need bounded active-reference closure, preserving valid alternate forms and
historical evidence. For cross-layer or lifecycle-sensitive behavior, trace
process/ownership boundaries and terminal or durable effects; helper ordering
alone is insufficient proof of the required end-to-end effect. Use appropriate
observations or explicitly identify the missing proof. This is risk-directed
analysis, not an unrelated cleanup or universal full-suite requirement.

## Findings and review after correction

<a id="IR-011"></a>
**IR-011 — Aggregate material first-assessment findings.**

The first assessment covers the complete affected result. Aggregate reasonably
discoverable material findings rather than stopping at the first easy blocker.
If access prevents completing that assessment, report both obtained findings
and the remaining scope. Do not claim exhaustive defect discovery.

<a id="IR-012"></a>
**IR-012 — Finding evidence and provenance.**

For an actionable finding identify the candidate/comparison, affected surface,
problem, impact/severity, evidence, required correction or invariant and acceptance
evidence. Compare material failures, including failed checks, with the starting
or reviewed baseline and classify their provenance:

- introduced by this implementation or remediation;
- pre-existing on the baseline;
- pre-existing but newly exposed or made blocking by changed behavior/validation;
- undetermined, with the missing comparison evidence stated.

For each blocking finding, explicitly identify the accepted Task requirement,
existing supported contract or already binding protected invariant that is
violated, its authoritative source, and concrete evidence of the violation.
Severity or a security label supplies no missing obligation. Keep the finding's
origin separate from its authority: a newly discovered failure may violate an
old obligation, while an imagined stronger guarantee may have no such binding.

<a id="IR-013"></a>
**IR-013 — Owner-facing report content and publication consistency.**

Where the owner's workflow expects a prepublication report, before publishing a
Change Request or negative assessment, give each actionable finding a concise
preview containing severity, origin, exact result/comparison and evidence,
qualified impact, required remediation/invariant and closure evidence. Give a
Step/commit origin when supported; distinguish confirmed behavior, analytical
risk and missing tests. An explicit `undetermined` origin plus the missing
comparison evidence is complete provenance; do not guess or investigate without
bound. Missing classification is an incomplete report. Retain these fields and
consistent classification in the published assessment, even after the preview.
This specifies that report's content, not another reviewer, approval,
waiting period or universal preview gate. Local publication permissions and
[Task Handoff's verdict lifecycle](task-handoff.md#result-acceptance-strategies)
remain unchanged.

Apply [RA-006](requirement-authority.md#RA-006) to finding classification, blocker
decisions and recommendations, preserving initiative and explicit per-finding
owner dispositions without turning proposals into obligations.

Before an owner receives a negative assessment or proposed Task amendment,
classify each finding under [IR-014](#IR-014) and include each blocker's binding
obligation and source from [IR-012](#IR-012). Label a newly proposed guarantee,
architecture or operator precondition **PROPOSED REQUIREMENT / OPTIONAL CHANGE**,
separately from defects and required remediation. Disclose its changed supported
behavior and operational cost, applying [PC-013](proportional-controls.md#PC-013)
where adopted. Preserve that separation in any expected preview and the published
report; an optional addition must not appear as defective already-required
security functionality. This is content for the existing report, not an added
publication approval or universal owner-preview/wait stage.

<a id="IR-014"></a>
**IR-014 — Defect versus gap versus optional improvement.**

Distinguish a proven contractual defect, an evidence gap and an optional
improvement. Before calling an actionable finding a blocker, compare it with
actual accepted authority and the promised boundary. A reviewer's desired
stronger guarantee is not an existing obligation: for example, an expressly
offline candidate check does not promise historical PR/CI acceptance. Preserve
its separate production gate; propose stronger pre-merge assurance as optional
unless canonical authority requires it. Missing evidence is not proof of a defect.

Keep four cases explicit: demonstrated violations of existing obligations
(including true vulnerabilities/regressions); missing evidence of required
behavior; pre-existing debt with its own scope/disposition; and optional new
protection. An evidence-based inability to justify acceptance may retain the
project's pending/hold disposition under [IR-018](#IR-018), but must name the
required evidence instead of asserting an unproved defect. Baseline debt is not
automatically a blocker, and optional protection is not mandatory remediation.

A credible material new risk outside existing obligations warrants explicit
owner discussion: explain severity, evidence and uncertainty, affected user
behavior, alternatives and operational cost; request a canonical owner decision
on any scope amendment. Preserve current authority/protected boundaries while
unresolved. A justified hold under existing authority does not turn that risk
into a pre-existing requirement, nor must demonstrated unsafe behavior receive
approval merely because a new control has not been selected. Existing local,
specialist and stronger safety obligations still apply. No universal owner
reapproval, new security gate or automatic Task expansion follows.

<a id="IR-015"></a>
**IR-015 — Supported origin and bounded remediation.**

Call a defect a regression only when introduction is supported. Baseline debt
does not automatically enter remediation: explain current authority or a material
dependency/changed acceptance boundary. Discovering it expands no Task scope.
Give proportional remediation guidance for non-local findings: the invariant,
coupled surfaces and useful correction sequence. Distinguish mandatory constraints
and acceptance evidence from suggested implementation choices; an equivalent
authorized solution is acceptable. New architecture or scope requires its owner.

A review recommendation or Change Request cannot authorize itself. Do not carry
an optional new guarantee into a correction Step as an accepted requirement
without the owning project's explicit canonical scope decision. A later genuine
owner ratification binds subsequent work; it does not retroactively prove that
the earlier implementation violated that newly selected requirement. Follow
adopted Task Handoff or local authority for amendments and execution admission.

<a id="IR-016"></a>
**IR-016 — Closure, adjacent risks and surviving interactions.**

On rereview, separately assess closure of prior findings, remediation-changed
behavior, adjacent coupled risks and genuinely new findings. A surviving blocker
needs an explanation of the invariant missed by prior review/remediation or an
explicit remaining evidence gap before another correction is prescribed. When
an interaction was missed, explain it and trace the whole relevant coupled path
before requesting another patch; do not invent a cause. Correct or explicitly
supersede unsupported earlier classifications in the next assessment, preserving
the original review as history. Preserve useful finding history in existing review records.
Changed artifacts stale affected tests and assessments. Reuse sufficient evidence
for unchanged invariants with an explained applicability/binding; obtain fresh
applicable evidence for changed ones. Old-head acceptance does not accept a new
head. Do not regenerate unchanged history or add ceremonial review rounds.

## Judgment, independence and publication

<a id="IR-017"></a>
**IR-017 — Substantive judgment and independence.**

Record the evaluator/role or review context, exact result and baseline, inspected
scope and primary inputs, substantive rationale/findings, material warnings,
unresolved evidence and their effect on the verdict. Distinguish exploratory,
pre-fix, stale and final evidence, and explain changes since prior assessment.
A generic PASS, another chat, model label, script or publication identity proves
neither sufficient review substance nor independence from implementation.
Use a genuinely separate evaluator or substantively separate review context as
allowed by project policy, with an honest independence rationale. Implementer
self-checks and helpers remain implementation evidence. If independent evaluation
is unavailable, leave independent acceptance pending.

<a id="IR-018"></a>
**IR-018 — Qualified verdict and explicit gaps.**

If evidence is insufficient to justify a positive conclusion, do not publish
PASS/APPROVE. Name the specific missing evidence and use the project's pending,
inconclusive or blocking disposition, with the next useful action. Distinguish
an access/assessment gap from an established defect; do not manufacture findings
or a Change Request merely to delay merge. Justified nonblocking gaps or exceptions
need explicit rationale under applicable authority; required evidence cannot be
silently waived. Absence of discovered defects alone does not justify PASS.

<a id="IR-019"></a>
**IR-019 — Lifecycle-compatible acceptance.**

A sufficiently evidenced Direct result may receive the locally authorized
positive verdict. A Deliberative result first receives substantive non-approving
assessment, even when its quality is good; preserve Task Handoff's owner
discussion/Decision before formal approval. Acceptance of report quality does
not adopt its recommendation. For later authorized acceptance of an unchanged
result, recheck current result/authority and reuse sufficient review evidence;
a changed result needs fresh applicable assessment.

<a id="IR-020"></a>
**IR-020 — Authorized publication and actor identity.**

Publish only through the owning project's authorized mechanism and verify the
record. An independent assessment copied through one owner account must name
its actual evaluator and publisher; it supplies no distinct authenticated native
reviewer identity, native GitHub APPROVE or branch-protection satisfaction.
Retain any stronger local requirement. Relay Reviewer/Writer, typed verdicts,
admission, schemas, check APIs and merge gates stay product-owned. Specialist
reader/source-completeness, code/test, environment and client methods stay with
their owners; they may strengthen this contract without replacing its substance.

<a id="IR-021"></a>
**IR-021 — Proportionate existing records.**

Keep evidence in existing Task/artifact/review records. This contract requires
substantive judgment, not a rigid universal checklist, packet, per-file attestation,
new service or technical publication gate. Optional aids cannot prove that review
occurred. Any proposed additional mandatory control needs its own unmet invariant,
risk/cost assessment and owner authority under applicable proportional guidance.
