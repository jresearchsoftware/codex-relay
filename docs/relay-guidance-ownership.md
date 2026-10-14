# Relay guidance: semantic ownership and deduplication

This Task #91 candidate separates portable policy, Relay product bindings and
consumer/client choices. The source comparison is accepted Relay
`4847c368ae5ea956fd6370bee207c8e4a176e8e0`, including the accepted
[Task #108 analysis](task-handoff-methodology-analysis.md). That analysis pins
an older v3 reconstruction baseline; its historical examples do not override
the current v4 [workflow](task-workflow.md) and
[authority contract](../contracts/README.md#github-native-task-authority).

The adopted shared dependency is development-governance **2.1.0**, accepted
producer `c3fbc8c2d10982889bea526161f810902def4289`, published distribution
`4211f55dcaeb3077d6abdbfba53a42ed848351b2`. The distribution receipt records
payload SHA-256
`1d6e4098ee557319dc04d21defc33260aee1ce21e82b502f8e60726b2b68e955`.
These identities are provenance, not installation, acceptance of this candidate,
registry publication or consumer-adoption proof. The generated delivery receipt
records the complete selected source/dependency identity.

## Owners and adopted topics

| Semantic slice | Owner and routing |
| --- | --- |
| Portable Task authority chronology, execution-cycle Step, minimal handoff, bounded execution, one attributable result, independent assessment and authorized continuation | Shared Governance [task-handoff](../vibevm/vibedeps/org.jresearch.ai.development-governance/2.1.0/vibevm/vibespecs/protocols/task-handoff.md) is the accepted portable semantic source. Current Relay obligations remain in the product binding below; this candidate does not activate the complete topic or its additional material behavior. |
| Proportionate controls and reuse of existing proof | Shared Governance [proportional-controls](../vibevm/vibedeps/org.jresearch.ai.development-governance/2.1.0/vibevm/vibespecs/protocols/proportional-controls.md), retaining [Relay bindings](execution-policy.md#relay-bindings). |
| Whether earlier requirements bind newly authorized work | Shared Governance [requirement-authority](../vibevm/vibedeps/org.jresearch.ai.development-governance/2.1.0/vibevm/vibespecs/protocols/requirement-authority.md), within current Task/CR authority. |
| GitHub-native schemas, native identity/provenance, admission, labels, branch/result binding, Writer/Reviewer, public tools, recovery and deployment interface | Relay product contracts; shared prose supplies no replacement parser, actor, permission or API. |
| Effective model defaults, checks, credentials, runners, publication language, client tools, extra approval/integration policy and operations | Consumer accepted instructions and admitted authority. Relay's own AGENTS.md is a local development binding, not a universal consumer template. |
| Skill discovery, native client projection and optional ChatGPT bootstrap | Versioned Relay delivery adapter plus supported client behavior; no automatic external settings synchronization. |

Only proportional-controls and requirement-authority retain their existing
Relay topic adoption. Other files carried by the complete immutable shared
package remain conditional. Installation does not adopt task-handoff,
package-versioning, self-adoption or github-repository-governance, activate their
flows, change settings or authorize publication. Their separate adoption
requires the project's own reviewed authority and reconciliation of all
material clauses; this is not selective adoption of a topic. Shared files
included for offline dependency closure remain exact upstream bytes; Relay
does not maintain an editable fork.

## Mapping general rules to their Relay binding

The middle column identifies the common rule and its shared semantic source.
For the two already-adopted topics, replace duplicated general procedures with
pinned routing. For Task Handoff, consolidate repeated Relay prose into its
existing component contract and retain the narrow product binding: a reference
to the shared source is not authority to activate its additional clauses. The
final column identifies material meaning that must remain in Relay. A short
binding/routing sentence is useful repetition; a competing general procedure is
not.

This candidate replaces AGENTS.md's repeated bounded-progress summary with a
pointer to the existing execution policy. It also moves the complete finding
provenance text unchanged into
[Reviewer: Independent review and finding provenance](../reviewer/README.md#independent-review-and-finding-provenance),
leaving a stable AGENTS.md routing pointer. These are Relay-internal
consolidations; they do not activate the Task Handoff topic or remove its
material local bindings.

| Existing Relay surface at the comparison revision | Shared semantic owner / deduplicable meaning | Retained Relay binding and exceptions |
| --- | --- | --- |
| AGENTS: Context loading; Task identity. Workflow: Decisions and subsequent work. | Task Handoff: stable charter, chronological owner authority, discussion versus permission, targeted refresh. | Issue #N identity; explicit `github-native-v1`; trusted native Decision/supersession/body hashes; protected immutable admission. Retained legacy/v3 authority is selected separately. Load the complete relevant authority/frontier through trusted resolution and selected evidence, not an indiscriminate history crawl. |
| AGENTS: Task identity/startup rename. Workflow: admitted Step/handoff. | Task Handoff: one authorized execution cycle, next Step after terminal result, inner corrections/recovery retain identity; Task/Step/purpose navigation and truthful rename limits. | Writer alone allocates v4 Step at admission. No allocation by Decision, CR, approval or display label. Native `step-N`/title projections, remediation CR grammar, requested exact handoff title and the local one-shot rename procedure/readback remain explicit bindings. Old attempts retain their historical Step rules. |
| AGENTS: handoff/context paragraphs. Controller: manual handoff. | Task Handoff: small startable pointer with irreducible environment facts, subordinate bounded snapshot. | Preserve complete admitted manual prompt, exact profile, source/admission digests and native run/attempt. Preserve GitHub expand/copy qualification and existing presentation fallback. A short prompt is not a second Task contract. |
| AGENTS: Work within the admitted goal. Execution policy: progress and preservation. | Task Handoff: evidence-backed corrections, proportional stops, useful/unrelated-work preservation, no artificial commits/PRs. | One reserved execution and replay suppression; no nested Relay launch; canonical-branch/head normalization; automatic worker commits handed to Writer. Preserve TEST sandbox exceptions, unknown-containment stops, collection failures and visible residue warnings. |
| AGENTS: profile/delegation. | Task Handoff: capability honesty and delegation does not expand authority. | Resolve CR → Decisions → consumer → system profile at admission; no silent substitution; requested versus measured model/effort; actual unavailable evidence; parent profile and local subagent guidance. Repository development defaults stay local. |
| AGENTS: Independent review/finding provenance. | Task Handoff: exact-result independent assessment, introduced/pre-existing/newly blocking/undetermined findings, surviving-invariant explanation, current-scope remediation. | Independent native exact-head PR verdict, trusted Reviewer identity and credentials, source/current authority comparison, expected authority digest when required, no-PR Task Approval and non-executable Task findings. Preserve aggregate full-candidate review and material user/operator contract-change gate. |
| Workflow: CR/remediation. Contracts/controller: lifecycle continuation. | Task Handoff: actionable bounded correction and fresh review of changed result. | Native `CHANGES_REQUESTED`, exact CR/head/branch/base, stable ID/findings, no preallocated v4 Step or replacement Request; trusted Draft transition before admission; canonical branch/PR reuse. Draft/Ready is execution handoff, not acceptance or CI. |
| Workflow/controller: Outcome. | Task Handoff: one attributable complete result, exact artifact, checked evidence versus claims, correct single terminal target and no no-PR fabrication. | Separate trusted Writer; schema authority/admission/result/native Outcome identity; unique durable PR binding and publication intent; direct manual `submit_manual_outcome`; bounded Git object import/scanning/non-force publication; exact old transport retained only for old attempts. |
| Execution policy: warning disposition. Reviewer: evidence acquisition. | Task Handoff: warning source/impact/disposition/next action/gaps; unavailable proof is not absence. | Supported native job/check/controller/Outcome acquisition, exact attempt/run binding, evidence-reader budgets and source states. Preserve UI-only pre-execution exclusion and prohibition of cookie/HTML scraping fallback. Green status never disposes warnings. |
| Contracts/workflow: acceptance/continuation/closure. | Task Handoff: acceptance, integration, further work and closure differ; reassess remaining work and retain holds. | Effective v4 Task Decision closure versus retained v3 charter policy; `keep-open` warning/default; native exact-head acceptance; protected owner continuation, verified non-closing Task linkage, required checks/readiness, current authority and completion evidence. A CR cannot authorize Task closure. No new continuation engine. |
| AGENTS: Minimum sufficient ceremony. Execution policy: proportional controls. | Proportional Controls and Requirement Authority: concrete risk/cost, cheapest sufficient existing proof and earlier-requirement applicability. | Full required candidate set, exact-head independent review, same-Task workflow documentation, protected operations and broader material user/operator gate remain operative. Local diagnostics/hooks are conditional, not consumer gates. |

## Accepted policy versus product behavior

The shared execution-cycle Step rule agrees with the current v4 Relay source.
It must not retroactively renumber v3 attempts, rewrite historical bodies or
create an admission for an already-running old execution. A new qualified-v4
launch cannot select an old Request as a workaround. Installation qualification
and exact old-attempt completion are separate decisions.

Task Handoff's Outcome table can express known multiple PRs or a substantive
mixed Task result. Relay's current workflow binds one source PR/unique durable
artifact and rejects ambiguous mapping. Adopting the portable rule does not
introduce multi-PR orchestration, relax unique-artifact identity or permit an
Issue fallback after uncertain PR creation. Any future supported multi-result
runtime path needs explicit product authority and qualification.

Task Handoff's Direct/Deliberative acceptance strategy can change whether a
formal verdict may be published, rather than merely holding continuation after
APPROVE. The current established Relay implementation/review path corresponds
to the shared Direct case. This candidate preserves it and does not impose a
new Deliberative verdict prerequisite, strategy field or runtime classifier.
Unresolved owner policy choices remain subject to the existing material
user/operator contract-change gate. Full Task Handoff adoption needs explicit
owner disposition of acceptance-strategy behavior and result-routing coverage
before applying its entire topic; a package dependency update is insufficient.
That future disposition must retain independent exact-head identity, checks and
already-authorized continuation, and cannot substitute fake REQUEST_CHANGES or
a post-approval hold for a chosen Deliberative pre-verdict boundary. Source
guidance cannot claim to implement or qualify a missing runtime gate.

## One source and two deliveries

The canonical Relay Skill source is
[packages/codex-relay/skill](../packages/codex-relay/skill/SKILL.md): a small
entrypoint, JIT workflow/compatibility/diagnostic references and human examples.
Exact Relay schemas and the immutable accepted shared dependency closure are
generated into both forms. The standalone native Skill needs neither a Relay
checkout nor VibeVM/network at normal use. The VibeVM package declares its pinned
dependency and projects the same Relay semantics. Generation/provenance binds
both to the same source; generated copies are not separately edited.

Consumer installation/update/removal must preserve owned local instructions,
other Skills and overlays, detect collisions and managed drift, expose a
deterministic reviewable diff, and support explicit version choice/rollback.
Native discovery, VibeVM authoring/build, authentic client behavior, source
acceptance, external package publication and production installation remain
separate evidence. No Skill text can substitute for those qualifications.
