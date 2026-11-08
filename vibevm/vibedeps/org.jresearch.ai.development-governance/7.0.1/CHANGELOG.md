# Development Governance changelog

## 7.0.1

PATCH: clarifies the existing stable-charter and in-scope persistence meaning at
[TH-010](vibevm/vibespecs/protocols/task-handoff.md#TH-010),
[TH-013](vibevm/vibespecs/protocols/task-handoff.md#TH-013) and
[TH-026](vibevm/vibespecs/protocols/task-handoff.md#TH-026). Preparing and interpreting
post-result continuation preserves the effective Task objective, completion
criteria and remaining work from its charter and applicable owner Decisions.
A blocker, failed check, review finding or partial Outcome guides necessary
actions without becoming a replacement charter. Removing the obstacle alone
does not complete the Task; continue authorized remaining work to the agreed
outcome or applicable review/handoff boundary.

This makes the linkage between TH-002–004, TH-006–010, TH-012–013, TH-026 and
RA-006 explicit without changing their authority or adding mandatory operator
work. Owner-justified bounded Steps, accepted process and protected boundaries
remain valid. New goals, permissions, policy choices and completion changes
still require their authorized Decisions. Short navigation-first handoffs,
terminal execution/recovery identities, independent acceptance and separate
consumer adoption remain intact. No forms, gates, repeated approvals, automatic
resume or orchestration infrastructure are added. The
[continuation examples](vibevm/vibespecs/guides/onboarding-examples.md#10-continuation-preserves-the-task-objective)
illustrate the distinction without depending on a particular client runtime.
All other protocols, rule addresses, routing, client tools, public inventory
and license are preserved; frozen prior versions remain unchanged.

## 7.0.0

MAJOR: replaces the timing and hold-release meaning within existing
[TH-026](vibevm/vibespecs/protocols/task-handoff.md#TH-026). The single existing
`Issue closure policy` attribute has two values: `close-authorized` closes on
successful default-branch merge of the designated completing PR via `Closes #N`
or its supported native closing link; `keep-open` uses a non-closing reference
and closes after its adjacent human-readable condition is verified. Neither
value requires another discretionary owner confirmation. Condition satisfaction
uses the existing trusted closure path without a new policy-change Decision;
genuine changes in scope, conditions or authority still require one. RA-006's
closure reference is aligned with that distinction.

Compared with 6.0.0, adopters must reconcile PR closing linkage, final-versus-
intermediate PR designation and conditional later closure. A producer Task
including publication selects `keep-open` until verified publication of the
exact accepted revision/version. The old contract allowed separate closure
after completion under `close-authorized`, including post-merge obligations,
and a trusted policy-release Decision for `keep-open`. Replacing those supported
paths is incompatible even though it removes repeated permission friction.
This is neither PATCH nor an optional MINOR addition. Existing review/merge and
completion records carry the evidence; no new field, checker, registry, daemon,
test framework or approval stage is introduced.

Required exact-head acceptance, protected merge authority, actual completion,
no-PR results and historical/admitted authority remain intact. Closing an
unmerged PR does not close its Task; only a genuinely completing PR in a multi-PR
Task closes it. Missing metadata fails safe without inventing an owner-selected
hold. Frozen releases and old Issue/Step history are not rewritten or replayed.
Consumers separately reconcile their bindings and qualify runtime changes;
publishing this package does not implement them or grant a universal grace period.
The [bounded examples](vibevm/vibespecs/guides/onboarding-examples.md#9-single-field-task-closure)
exercise these cases without relying on a producer's product-specific rules.

TH-026 and RA-006 retain their addresses and semantic ownership; TH-026's earlier
closure timing/release wording is superseded in this version. No rule ID is
retired or reused. All other protocols, conditional topic routing, public
inventory, license, client tools and adoption boundaries are preserved.

## 6.0.0

MAJOR: extends existing Package Versioning with explicit compatibility-evidence
and delivery-authority obligations for its adopters. [PV-014](vibevm/vibespecs/protocols/package-versioning.md#PV-014)
requires a floor grounded in the actually used interfaces, layout, paths,
identifiers, semantics and behavior, relevant accepted history and proportionate
evidence. Constraint rationale distinguishes real incompatibility from an
authored resolver exclusion and preserves justified security, contract and
reproducibility pins/bounds. Neither open-ended ranges nor next-major caps are
universal; unknown future releases are not promised compatible.

[PV-015](vibevm/vibespecs/protocols/package-versioning.md#PV-015) distinguishes
range, consumer lock, explicit adoption and bundled snapshot. Resolved delivery
uses the selected consumer identity without a competing fixed-policy fallback;
self-contained delivery may use its deliberate attributed immutable snapshot.
PV-013 retains checks for every actually included dependency, even an inert
release-evidence snapshot. New [PV-018](vibevm/vibespecs/protocols/package-versioning.md#PV-018)
assesses deliberate updates against the used contract and local bindings.
PV-005 retains producer cadence: compatible or irrelevant upstream changes can
need only a reviewed consumer update; actual dependent-product behavior,
interfaces, guidance, packaging or shipped-byte changes need its own correction
and classified release. PV-017 connects the native lock/slot route to these rules.

Compared with 5.2.3's general actual-compatibility and lock/adoption guidance,
adopters must now supply the explicit floor/constraint rationale and check which
dependency source each delivery form uses. This tightens mandatory lifecycle
assessment and supported routing, so it is not classified as an editorial fix or
merely an optional addition. Use existing change/release review and focused
evidence; there is no new operator command, recurring compatibility matrix, cold
installation gate, attestation, registry or approval service. Consumers reconcile
these duties and their existing local bindings in their own reviewed update.
The [worked examples](vibevm/vibespecs/guides/onboarding-examples.md#8-package-consumer-compatibility-and-delivery-choices)
cover both failure kinds, compatible majors, real incompatibility and both
delivery forms without an additional normative topic.

All previous rule IDs remain resolvable; PV-018 is new and supersedes none.
The other nine protocols, topic adoption, source/publication authority, independent
review, security, license/redistribution, manifest and frozen-closure obligations
remain intact. No consumer is automatically migrated and no historical work is
retroactively judged under this extension. Frozen versions retain their bytes.

## 5.2.3

PATCH: TH-001–007/010 clarify ordinary Task dispatch without a redundant admission
Decision. An agreed, actionable open Task can wait and then start through a
deliberate owner handoff within current permissions. Readiness is not execution;
Issue openness alone dispatches nothing. This repairs the interpretation of the
existing routine-action exception in TH-005, adopted applicability in TH-001 and
execution-cycle meaning in TH-006, consistent with PC-010 and RA-006. It adds no
mandatory operator work, state, record, label or approval stage. Substantive
scope, policy, permission and material post-result choices still require their
applicable Decisions; existing explicit holds are not retrospectively waived.

Standalone work outside an adopted governed workflow needs no synthetic Step or
Outcome. Adopted Steps, terminal results, same-result recovery, independent review
and protected effects retain their meaning. Product-owned authenticated start,
Step/profile snapshots, Writer/Reviewer separation and anti-duplicate trust
controls remain intact. No existing Task is automatically started or accepted,
and no other consumer is migrated. Rule IDs, all other protocols, conditional
topic routing, PR Draft/Ready and effective-Instructions reconciliation remain
unchanged. Frozen versions retain their bytes and chronology.

## 5.2.2

PATCH: RA-006 clarifies that its existing requirement-provenance rule covers
negative constraints in Tasks, Change Requests, Decisions and execution prompts.
Agent preferences cannot prohibit ordinary operations covered by the selected
outcome and accepted governance. Material new restrictions need owner discussion
before publication as authority; accepted restrictions and protected boundaries
retain their existing Decision, review and exact-head requirements. This repairs
the interpretation of RA-002/005/006 and PC-004/013 without adding mandatory
operator work, a new permission ritual, reviewer gate or state machine. Other
protocols, applicability, publication and deliberate consumer adoption are unchanged.

## 5.2.1

PATCH by an explicit single-task owner exception to [PV-002](vibevm/vibespecs/protocols/package-versioning.md#PV-002).
The [Task 74 owner Decision](https://github.com/jresearchsoftware/shared-governance/issues/74#issuecomment-6386467528)
identifies this as repair of the originally intended requirement, narrowed during
translation into Task 62/PR 63. Accepted 5.2.0 visibly documented the narrower
explicit-application condition; this release changes the published workflow
obligation and would ordinarily require MAJOR under PV-002. The owner selects
5.2.0 -> 5.2.1 for this correction only. PV-002 remains the general rule; the PATCH
label does not claim unchanged consumer-facing behavior. Historical 5.0.0/5.2.0
acceptance, releases and Task records retain their meaning.

TH-029 replaces the explicit-application-scope exemption for adopting
projects intentionally using generated ChatGPT Project Instructions. A task changing
its complete effective desired text must reconcile live Settings after source
acceptance/integration and before completion, even without an application clause.
Present the full raw replacement in one markdown fence when different or unconfirmed;
the owner applies/reconciles unknown live rules and supplies supported readback or
attributable confirmation of live content. Keep unresolved verification visible.
Unchanged text, cache-only and SHA-only changes create no new application duty;
earlier mismatches/gaps remain. The projector reports this boundary without reading
live Settings or judging completion. RA-006 remains unchanged. Consumers must
intentionally update under their own authority and assess this changed obligation;
producer publication neither migrates them nor activates their live Settings.
No automatic Settings writes, recurring verification service or new approval loop.

## 5.2.0

MINOR: adds separately adopted [Small Improvements — SI-001–SI-008](vibevm/vibespecs/protocols/small-improvements.md)
and a [usage and consumer-migration guide](vibevm/vibespecs/guides/small-improvements.md).
The exact `small-improvement` Issue label is the discovery key; the title prefix
is optional. Adopters inspect open labeled Issues when preparing suitable
source-changing Tasks, first source-changing Steps or relevant CRs, notify the
owner with IDs/proposed inclusion, and implement only accepted receiving scope.
Combined implementation, normal tests and one independent PR review preserve
existing gates. Source Issues stay open until accepted integration, with explicit
deferral, cancellation, partial-work and supersession dispositions.

Availability does not activate SI, including for existing TH/CD/RA adopters.
The nine earlier protocols keep their accepted 5.1.0 bytes and applicability.
The compact boot adds only a conditional SI route. No label creation, consumer migration, bot,
controller, automatic injection, new per-item execution cycle or review stage
follows from an update. Separately authorized consumer adoption reconciles proven
duplicates while retaining broader local planning rules and native authority.
The existing onboarding guide's 2.6.0 catalog remains a dated nine-topic inventory;
its instruction to inventory later topics includes SI in this version.
All existing rule IDs remain; SI IDs are new and supersede none.

## 5.1.0

MINOR: TH-026 adds compatible guidance and examples for owner-selected temporary
keep-open holds, verified preauthorized release through existing trusted Task
Decisions, and resolving missing closure conditions in existing result review.
Accepted 5.0.0 already requires actual completion, hold reassessment, no repeated
authorization and no agent-invented gates. This addition preserves those duties
and local timing/mechanisms; it introduces no universal authoring field, new
review duty or completion gate. Close-authorized still waits for completion,
acceptance/integration and protected obligations. RA-006 applies its existing
obligation provenance rule to closure. Consumers retain their local authority and
separately reviewed adoption; no runtime/state-machine change, automatic policy
mutation, topic adoption or live settings application follows.

## 5.0.0

MAJOR: RA-006 prevents agent-authored obligation expansion across Task authoring,
acceptance, execution and continuation; TH-002/026 and IR-013 apply that principle.
TH-029 conditionally requires supported live settings reconciliation for Tasks
that include applying generated instructions. Existing topic adoption remains local.
ChatGPT projection receipts, ownership checks and receipt migration are removed.
Adoption removes the old tracked ChatGPT receipt in the consumer's ordinary PR;
native VibeVM slot receipts remain. Status schema 4 reports content changes and
conditional application meaning, without source inventory or maintenance_evidence.
Exact accepted-source/native validation remains; Git/invocation evidence owns
provenance. Same-output main/tool/source changes are NO_OP. Optional exact-source
caches retain their snapshot contract and can be disabled without ownership checks.
RA-006 adds no universal publication checklist; existing accepted obligations retain
their authority at their actual source.
No consumer adoption, live settings change or additional publication stage follows.


This file ships in the frozen distribution and installed package from 3.0.0.
Earlier entries are bounded reconstructions from committed manifests, protocols
and READMEs; they change no old payloads and assert no publication dates.
Source acceptance, remote publication and consumer adoption remain distinct.
Entries describe the version contract, not live Task status.

## 4.0.0

### Added

- [PC-013](vibevm/vibespecs/protocols/proportional-controls.md#PC-013): preserve
  scope before review blockers or proposed Task amendments. Assess old/new
  supported workflows and quantify contract/operational cost; doing nothing or
  accepting hypothetical risk can be legitimate. A security label cannot make
  an optional defense, history prerequisite or trust condition mandatory.

### Changed

- [IR-012–IR-015](vibevm/vibespecs/protocols/independent-review.md#IR-012): every
  blocker explicitly identifies the violated accepted Task requirement, supported
  contract or binding protected invariant, its authority and concrete evidence.
  Before negative reporting or amendment discussion, separate demonstrated
  violations, evidence gaps, baseline debt and **PROPOSED REQUIREMENT / OPTIONAL
  CHANGE**. Report new-risk severity, evidence, affected behavior, alternatives
  and cost for explicit owner scope disposition. A review/Change Request cannot
  admit its own proposed control or silently bind the next Step.

### Breaking changes and migration/adoption from 3.0.0

MAJOR because existing PC/IR adopters must now supply explicit per-blocker
obligation binding and prepublication requirement classification in their
existing reports. Earlier authority comparison and optional-improvement rules
remain, but did not require this explicit binding in every blocker. This is
mandatory reporting work, not a PATCH wording repair or an optional new topic
qualifying as MINOR. Reconcile adopted local finding/report methods under the
consumer's own authority. A dependency update does not adopt another topic.

There is no extra reviewer, checklist, ledger, service, security gate, waiting
period or universal per-PR owner reapproval. Genuine vulnerabilities/regressions,
required evidence and stronger local/specialist obligations remain enforceable.
A material unresolved new risk may justify an existing-authority discussion/hold
without being mislabeled an old defect. Later explicit owner ratification binds
subsequent work, not the earlier implementation retroactively. Task Handoff
retains Decisions, Step admission, verdict lifecycle and publication ownership.
Other seven protocols, boot/adoption conditions and client tool bytes retain
their 3.0.0 meaning. PC-001–PC-012 and all IR IDs remain; PC-013 is new and
supersedes no prior ID. Frozen 3.0.0 and older payloads remain unchanged.

## 3.0.0

### Added

- [TH-028](vibevm/vibespecs/protocols/task-handoff.md#TH-028): executor-to-review
  Draft/Ready lifecycle for applicable implementation/remediation PRs. Existing
  PRs enter verified Draft before newly admitted work; new PRs start Draft where
  supported. A successful durably published/read-back Outcome precedes verified
  Ready, before independent review. Blocked/uncertain PRs stay Draft. State-only
  recovery retains the same Outcome/Step/result. Automation ownership, per-PR
  readiness, local capability limits and non-GitHub/no-PR exceptions are preserved.
- Installed change history and stable rule anchors throughout the nine protocols,
  conditional boot and operator procedures. See [DG-001](README.md#DG-001)
  for address maintenance and the legacy mapping below.

### Changed

- [PV-006](vibevm/vibespecs/protocols/package-versioning.md#PV-006): include the
  actual public LICENSE, aligned metadata, approved redistribution rights,
  complete intended export and relevant source-time checks **before accepting
  frozen package source into main**. Publication transport cannot complete it later.
- [PV-007](vibevm/vibespecs/protocols/package-versioning.md#PV-007): freeze the
  first independently accepted source-main `(group, name, version)` payload,
  including notices and inventory, even without remote tags or infrastructure.
  Later repairs need a new version. Candidate refinement, producer-owned cadence,
  non-frozen snapshots and explicit owner exceptions remain.
- [TH-019–TH-021](vibevm/vibespecs/protocols/task-handoff.md#TH-019): retain
  independent assessment/result/actor lifecycle; detailed assessment methodology
  belongs to separately adopted Independent Review or local review rules.
- [IR-005](vibevm/vibespecs/protocols/independent-review.md#IR-005) and
  [IR-011–IR-016](vibevm/vibespecs/protocols/independent-review.md#IR-011): cover
  complete affected behavior/contract and material consumers, coupled paths,
  aggregated findings, evidence gaps versus contractual defects versus optional
  improvements, and risk-directed correction review. Compare blockers with actual
  accepted authority. Explain missed interactions before another patch request;
  correct/supersede unsupported classifications while preserving review history.
- [IR-013](vibevm/vibespecs/protocols/independent-review.md#IR-013): where the
  owner's workflow expects a prepublication report, give severity, supported
  provenance or explicit undetermined plus comparison gap, exact result/evidence,
  qualified impact, correction and closure evidence. Keep classifications
  consistent on authorized publication. No universal wait or approval is added.

### Removed

- Detailed finding/provenance, assessment/rerun and owner-report methodology
  from Task Handoff as an implicitly supplied method. Independent assessment,
  current authority, required checks, exact-result acceptance, Direct/Deliberative
  and publication/actor boundaries remain in Task Handoff.

### Breaking changes and migration/adoption from 2.7.0

MAJOR: Task Handoff adds mandatory executor Draft/Ready operations where supported
and authorized; Ready now denotes a verified executor handoff, independently of
review APPROVE, CI, conflicts, mergeability, merge authority or Task completion.
Consumers adopting this version must reconcile their local executor/automation
ownership and supported state operations. Keep qualified automation (including
Codex Relay Writer), stronger guarantees and existing recovery; do not add a
competing executor, credentials, CLI or PR to unsupported workflows. Missing
permission is a disclosed handoff limitation for owner disposition. Adoption
and any consumer implementation remain separately authorized. TH-001–TH-027
retain their IDs; TH-028 is new and supersedes no prior ID.

Package preparation also adds mandatory pre-acceptance work, and
Task-Handoff-only consumers no longer receive its former detailed assessment
method through that topic alone. Assess this under consumer-owned authority:
deliberately adopt Independent Review for the shared method, or keep the accepted
local assessment method. A reference or dependency update does not select it.
The owner-report detail added during the unaccepted 3.0.0 draft also belongs
only to Independent Review/local policy in this ownership split.

Shared Governance explicitly selects Independent Review in its own human-owned
root AGENTS, with full accepted materialized reading for relevant assessments.
This is producer-local adoption, not an obligation on other consumers. Its
ChatGPT negative-review publication rule is confined to producer-local
`chatgpt/custom.md` and generated Instructions, outside this package. The common
package adds no owner publication wait. Installation implies no consumer migration,
publisher activation, protected setting or product execution mechanism.
Other protocols retain their 2.7.0 normative meaning with new addresses.

### Material legacy addresses → stable rules

All 2.7.0 protocol headings remain valid navigation anchors. No 2.7.0 rule IDs
existed. These release mappings identify semantic owners, not a rule database:

| Previously unnumbered 2.7.0 location | 3.0.0 destination and disposition |
| --- | --- |
| Task Handoff: Stable charter; Step; Startable handoff; Outcome target | [TH-002–TH-017](vibevm/vibespecs/protocols/task-handoff.md#TH-002), meaning preserved. |
| Task Handoff: Exact result and independent assessment — executor report, independent result, single-account identity | [TH-018–TH-021](vibevm/vibespecs/protocols/task-handoff.md#TH-018), lifecycle retained; detailed method separately selected. |
| Same section — completeness/primary evidence, findings/provenance, correction/rerun scope and proof reuse | [IR-003–IR-016](vibevm/vibespecs/protocols/independent-review.md#IR-003), relocated/consolidated and clarified; no automatic adoption. |
| Task Handoff: Result acceptance strategies; Authorized continuation | [TH-022–TH-027](vibevm/vibespecs/protocols/task-handoff.md#TH-022), authority and exceptions preserved. |
| Independent Review: Establish; Verify; Findings; Judgment | [IR-003–IR-021](vibevm/vibespecs/protocols/independent-review.md#IR-003), preserved and clarified affected-path method; report content is IR-013. |
| Package Versioning: Contract; Source integration; Dependencies; VibeVM implementation | [PV-002–PV-017](vibevm/vibespecs/protocols/package-versioning.md#PV-002); new preparation/source-freeze duties are PV-006/PV-007. |
| Proportional Controls: risk/cost; Existing proof; Reassess friction | [PC-001–PC-012](vibevm/vibespecs/protocols/proportional-controls.md#PC-001), meaning preserved. |
| Requirement Authority: applicability, binding origin, protected behavior, correction/conflict | [RA-001–RA-005](vibevm/vibespecs/protocols/requirement-authority.md#RA-001), meaning preserved. |
| Self-adoption: Applicability; Native ready state; Candidate tests/recovery | [SA-001–SA-009](vibevm/vibespecs/protocols/self-adoption.md#SA-001), meaning preserved. |
| GitHub Governance: Working model; Protections; Enforcement; Timing/checklist | [GH-001–GH-013](vibevm/vibespecs/protocols/github-repository-governance.md#GH-001), meaning preserved. |
| Contract/Decision Maintenance: Contract changes; Durable decisions; Human guidance | [CD-001–CD-007](vibevm/vibespecs/protocols/contract-and-decision-maintenance.md#CD-001), meaning preserved. |
| Context Loading: Start; Triggered detail; Completeness; Refresh | [CL-001–CL-008](vibevm/vibespecs/protocols/context-loading.md#CL-001), meaning preserved. |

## 2.7.0

### Added

- Optional engineering-methods/FPF guide and conditional boot pointer. No new
  normative topic, mandatory FPF/MCP access or dependency. Nine topics, local
  authority and adoption choices preserved. Migration: none on update alone.

## 2.6.0

### Added

- Human-requested onboarding procedure and worked examples in the installed
  payload, with conditional boot discovery. No tenth topic or automatic adoption;
  nine protocols and client tools preserved. Migration: selected onboarding only.

## 2.5.0

### Added

- Separately adopted Context Loading/JIT topic. Eight earlier protocols and
  client tools preserved. Migration: explicit selection, no reading quota/service.

## 2.4.0

### Added

- Separately adopted Contract and Decision Maintenance topic. Seven earlier
  protocols and client tools preserved. Migration: explicit topic selection.

## 2.3.0

### Added

- Optional manually invoked governance-neutral ChatGPT base/projector assets
  in the native slot; consumer-owned custom/binding and generated Instructions.
  Migration: deliberate client-tool use; no protocol/live-settings activation.

## 2.2.0

### Added

- Independent Review as a separately adopted topic and conditional Task Handoff
  reference. Existing mandatory choices preserved. Migration: explicit adoption.

## 2.1.0

### Added

- Workflow-aware GitHub Repository Governance for explicit adoption. Five existing
  protocols preserved; no settings mutation on install/update.

## 2.0.0

### Changed / Breaking changes

- Task Handoff defines an authorized execution-cycle Step, chronological
  Decisions, canonical Outcome routing and Direct/Deliberative acceptance.
  Migration: reconcile earlier local Step, Outcome and approval conventions in
  separately reviewed adoption; no silent consumer authority transfer.

## 1.3.0

### Added

- Conditional Producer Self-adoption protocol and native producer ready state.
  Migration: explicit topic adoption by producers consuming their own guidance.

## 1.2.0

### Added

- Task Handoff protocol for explicit adoption; product execution and identity
  mechanisms stay local.

## 1.1.0

### Added / Changed

- Requirement Authority interpretation and proportional-control friction
  reassessment. Migration: retain applicability and real protected invariants.

## 1.0.0

### Added / Changed

- Stable whole-package SemVer and explicit Package Versioning topic; stable
  authoring root and guarded publication. Migration: deliberate versioning adoption;
  producer automation is not imposed on consumers.

## 0.1.0

### Changed / Removed

- Frozen passive Development Governance flow preserves proportional-controls
  semantics; the accepted flow export has no native Skill declaration.
  Historical experimental artifacts remain unchanged. Later migration requires
  separately reviewed source/package adoption.
