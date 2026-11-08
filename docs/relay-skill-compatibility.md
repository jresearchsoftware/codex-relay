# Relay Skill compatibility with Shared Governance

The native Relay Skill requires Shared Governance **`>=2.5.0`** for the actual
protocol layout and behavior it consumes. This is the first accepted version
providing all nine routed protocol files. It admits the assessed 2.5.0, 3.0.0,
4.0.0 and 5.0.0 contracts without an artificial next-major upper bound. It does not
promise compatibility with unknown future changes.

Shared Governance owns the complete reusable protocols. Relay owns its product
workflow, schemas, actors and bindings. The consumer owns deliberate dependency
selection, its reviewed `vibe.lock`, topic adoption and local policy. Neither a
new Shared release nor a package range automatically updates those decisions.


## Project update from 7.0.0 to 7.0.1

Task #199 deliberately selects Shared 7.0.1 through the exact root Git pin,
native schema-7 lock and materialized slot. The published annotated tag
`v7.0.1` (`dddb250d5eb133347f0b1712740a96be7a1d823b`) peels to distribution
`f9fcfa03dec8fb9e00398fc7e0cc7de92da687b9`, whose receipt identifies accepted
producer source `1110f10b996c2f81fa842e6339ab6d7c13111cd7`.
The [immutable diff](https://github.com/jrs-vibevm/org.jresearch.ai.development-governance/compare/v7.0.0...v7.0.1)
changes only Task Handoff among the nine adopted protocols; the other eight
protocols, conditional boot and ChatGPT generator are byte-identical. Changelog,
onboarding continuation example, version and publication receipt also change.

| Changed clause | Assessment and retained Relay binding |
| --- | --- |
| TH-010 | Reconstruct the effective Task objective from the charter and applicable owner Decisions. A blocker, failed check or short next-Step purpose does not narrow it. Deliberately bounded diagnostic/research/repair Steps remain legitimate under actual owner scope, accepted process or an execution/authority boundary. Writer admission still fixes the execution scope. |
| TH-013 | After removing an obstacle, continue remaining authorized work toward the agreed outcome or applicable review/handoff boundary. A local fix alone supplies no new stop rule. Existing scope, permission, protected-state and progress-bounded stops remain binding; no terminal-attempt replay is authorized. |
| TH-026 | A cleared blocker is not Task completion. Reassess the actual remaining work and completion conditions; preserve independent acceptance, protected continuation and the temporary legacy closure binding. No new closure mechanism is introduced. |

This clarification is compatible with repository governance: it preserves local
authority, native admission, exact-head review and product boundaries. It adds no
new topic, permission, mandatory owner approval, lower-bound incompatibility or
release obligation. The governance-only update leaves frozen Relay 4.1.1 and its
standalone Shared 5.0.0 snapshot unchanged. Task #199's separate supported Relay
workflow addition is classified as 4.2.0 MINOR under PV-018; that release keeps
the same standalone snapshot and native dependency floor. Shared 7.0.0 remains at
its original slot solely as immutable inactive history requested by Task #199.
The root lock, generated boot and native product routing select only 7.0.1;
missing selected state must fail, never fall back to retained history.

## Project migration from 5.0.0 through 7.0.0

Task #213 changes repository governance and its pinned VibeVM to 1.0.11. It
preserves the product Skill's `>=2.5.0` floor, standalone Shared 5.0.0 snapshot,
included publisher closure and every frozen package byte. The root exact pin is
an owner-selected reproducibility/policy constraint, not a claim that earlier
Shared interfaces are unusable. The 2.5.0 floor evidence below remains actual
layout/history evidence; no resolver exclusion or Shared major alone revises it.

The complete applicable evolution was compared release by release using the
[immutable 7.0.0 changelog](https://github.com/jrs-vibevm/org.jresearch.ai.development-governance/blob/77119c2aa93ac9b27ed68e2de8d12ea5d1e497b0/CHANGELOG.md),
full protocols, migration notes and Relay contracts. Accepted producer
`bee96f1715142fde598318e7db402168dcfabf5f`, annotated tag object
`a85505771b10fbd88d49185e6bf0545a7983b3a7`, peeled distribution
`77119c2aa93ac9b27ed68e2de8d12ea5d1e497b0`, receipt and complete payload agree.
The [native identity contract](vibevm.md#selected-immutable-identities) records
the distinct lock/tree identity. This assessment describes adoption; candidate
text does not authorize the session producing it.

| Evolution | Before → after; disposition and Relay binding |
| --- | --- |
| CL, CD, GH, IR, PC, SA | All six complete protocols are byte-identical from 5.0.0 through 7.0.0: **already satisfied**. Preserve topic triggers, stronger native actors/trust/security, independent review, protected effects and existing human contribution routes. No new settings audit or gate. |
| 5.1.0 TH-026 / RA-006 | Added owner-selected holds, completion evidence and preauthorized release through trusted Decisions. Its closure wording is **superseded by 7.0.0** for project policy; the product's earlier qualified mechanism survives only through the canonical [legacy exception](relay-guidance-ownership.md#temporary-legacy-closure-binding). Historical/admitted authority is preserved. |
| 5.2.0 Small Improvements / boot | **Optional, not adopted**. SI-001–008 and its guide are available; no scan, queue, label setup, automatic inclusion or additional consumer duty follows. The original nine topics retain their complete adoption. |
| 5.2.1 TH-029 / ChatGPT projector | **Adopted conditional semantics, inactive here**. Explicit application scope is no longer the sole trigger: intentional generated Project Instructions users must reconcile changed complete effective text after acceptance/integration. Full replacement and supported confirmation/readback, unchanged-text exception and surviving prior gaps remain. This repository has no authored generated Project Instructions integration; bundled helpers/optional bootstrap do not establish it. No live Settings operation or synchronization is claimed. The PATCH label was an explicit upstream one-Task exception, not proof of unchanged behavior. |
| 5.2.2 RA-006 | **Adopted** negative-constraint provenance: assistant preferences cannot create no-release/no-diagnostics/no-fixes restrictions. Task #213's actual owner-selected project-only/no-product-release boundary and protected permissions remain binding; the candidate cannot erase them. |
| 5.2.3 TH-001–007/010 | **Adopted; native binding retained**. Routine dispatch of agreed actionable work needs no redundant Decision certifying the same start; Issue openness starts nothing. Native authenticated command, Writer Step/profile snapshot, replay protection and actor separation remain. Standalone work outside adopted Task Handoff needs no synthetic Step/Outcome. |
| 6.0.0 PV-014 | **Adopted, already supported** by the accepted 2.5.0 floor history and missing ninth protocol at 2.4.0 below. Assess actually needed layout/interfaces/semantics; stricter prose is no invented interface failure. No automatic next-major cap or future-version promise. Root exact pin remains justified project policy. |
| 6.0.0 PV-015/017 | **Adopted; delivery identities separated**. Range, root lock, explicit adoption and bundled snapshot are distinct. Native routing uses selected root 7.0.0; standalone uses its attributed 5.0.0. Missing selected state is an error, never permission to load a fixed snapshot. |
| 6.0.0 PV-005/013/018 | **Adopted, already supported with build decoupling**. Inert included closure snapshots still need frozen integrity evidence. This root lock/toolchain update is outside delivered product bytes; no product release follows. Changing product guidance, requirements, bundled snapshot, shipped lock or packaging would need its own classified correction/release. The repository adapter preserves the existing generator and artifact identities. |
| 7.0.0 TH-026 / RA-006 | **Adopted project meaning; product implementation deferred to #194**. The single field selects completing-merge versus condition-verified later timing. The canonical legacy exception governs actual current product execution. No new field, discretionary closure approval, unsupported runtime closing link or source-adoption rollout is introduced. |

Important behavior and negative cases follow the same authority split:

| Case | Shared 7.0.0 meaning / current product disposition |
| --- | --- |
| Completing versus intermediate PR; abandoned PR | Only a genuinely completing default-branch merge closes under the new meaning; intermediate/nonmerged results do not. Implementing native linkage is #194. Current source/runtime keeps its qualified non-closing linkage and trusted continuation. |
| Delayed publication, required Apply, unmet/wrong-target condition | Outstanding real obligations keep the Task open. Source merge, optional future observation and a green Step are not proof. Task #213 has no product release or Apply deliverable; verification of accepted integration still remains required. |
| Preauthorized condition satisfied | Shared 7 needs no policy conversion or repeated discretionary confirmation. Current execution uses the bounded legacy trusted mechanism; do not invent a replacement approval. Genuine changed scope/authority still needs its actual Decision. |
| No PR, historical admissions, ambiguous metadata or uncertain mutation | Retain supported no-PR completion and original attempt authority; no synthetic PR, replay or old-body rewrite. Refuse unsafe closure, reconcile genuine missing intent and preserve reservations/readback instead of inventing an indefinite hold. #194 owns new/legacy runtime qualification. |
| Root route missing, corrupt or replaced with bundled 5.0.0 | Existing structural counterexamples reject it; complete selected 7.0.0 is required. Frozen 5.0.0 remains build/release evidence and standalone delivery only. |
| Changed frozen product snapshot/floor or merely newer Shared major | Artifact regeneration must preserve the current product exactly. A product-byte change cannot be reported as consumer-only; a newer Shared version alone creates no product release. |

Source/tool probes establish the root7 + unchanged Relay4.1 file-routing and
frozen-byte combination. Existing local legacy-authority/linkage/continuation
suites check the unchanged implementation. They do not qualify a newly installed
closure runtime. The accepted upstream Relay-only transition evidence covered
frozen Relay3.0.0, not every later artifact; neither that evidence nor the open
range is a blanket Shared7 product-compatibility promise. Actual installed
identity, exact-head CI, independent acceptance and integration remain separate
proofs. Runtime closure implementation, installed qualification and the new
Skill's justified introducing-version floor remain #194.

## Required protocol semantics

The Skill adopts these complete applicable topics for Relay product guidance.
The rule groups below retain the frozen product's 5.0.0 comparison addresses;
they are not minimum-version requirements or a selective subset
of an adopted protocol. Read the full relevant topic, including applicability,
exceptions and stronger local boundaries. Installing the Skill does not adopt
these topics for unrelated consumer work.

| Protocol | Rules used by Relay | Relay binding |
| --- | --- | --- |
| Context Loading | CL-001–008: accepted startup, triggered detail, completeness and mutable refresh | Accepted source is frozen independently of candidate guidance; live Task and result facts are refreshed. |
| Task Handoff | TH-001–013: charter, Decisions, Step, startable handoff, correction and recovery; TH-014–021: one attributable exact result and independent assessment; TH-022–027: acceptance and continuation; TH-028: Draft/Ready handoff; TH-029: conditional settings application | Trusted v4 Decisions and Writer admission implement current authority and Step; retained attempts keep their original bindings. Writer owns supported PR state transitions. Settings application requires separately authorized scope. |
| Independent Review | IR-001–011: full affected result and primary evidence; IR-012–016: finding provenance, obligation binding, classifications and rereview; IR-017–021: substantive independence and qualified publication | A separate qualified Reviewer, complete exact SHA, native checks, typed CR or Task Approval and protected owner continuation remain mandatory where the installed product contract requires them. |
| Contract and Decision Maintenance | CD-001–007: material contract authority, durable decisions and same-change guidance | Trusted owner Decisions or retained authority authorize material behavior; implementation/review preferences cannot supply that permission. |
| Proportional Controls | PC-001–012: concrete risk, operator cost, sufficient proof and protected requirements; PC-013: preserve scope before blockers and Task amendments | Existing execution safeguards and candidate checks remain; optional controls do not silently become remediation or new gates. |
| Requirement Authority | RA-001–006: accepted obligations versus revisable implementation choices, protected behavior, actual conflicts and initiative without silent obligation creation | Canonical Task scope and protected invariants bind work; comments, an implementer's plan or a CR cannot enlarge Task authority. |
| Package Versioning | PV-001–004: actual contract impact; PV-005–012: producer cadence, source freeze and immutable publication; PV-013–017: included closure, consumer requirements and lock | Relay owns its release and delivery; a consumer's compatible Shared update does not require a Relay release. |
| Producer Self-Adoption | SA-001–009: independently accepted guidance, candidate separation, native ready state and recovery | Source, lock, slots and generated routes travel together in one candidate; ordinary execution reads accepted committed files offline. |
| GitHub Repository Governance | GH-001–013: explicit adoption, actual writer/ref paths, proportionate protections and event-directed verification | Existing source PR, human contribution and publisher paths remain; guidance acquisition grants no settings or credential authority. |

Concrete product exceptions and mechanisms remain in
[the ownership binding](relay-guidance-ownership.md),
[the manual](../packages/codex-relay/skill/references/workflow.md) and
[retained-attempt compatibility](../packages/codex-relay/skill/references/compatibility.md).
Shared package versions are independent of Relay authority schema versions.

## Why the lower bound is 2.5.0

The accepted Shared source history supplies the following progression. Versions
come from each source commit's `packages/development-governance/vibe.toml`;
older semantic addresses are mapped by the
[4.0.0 changelog](https://github.com/jresearchsoftware/shared-governance/blob/99034dd708e5d0201060986b561ada4d2cffd453/packages/development-governance/CHANGELOG.md).

| First accepted Shared version | Relevant capability and source |
| --- | --- |
| 1.0.0 | Stable package lifecycle and the existing proportional-controls contract: [901186b](https://github.com/jresearchsoftware/shared-governance/commit/901186bdd1aabc9b7f1094eeb2cc294f96b688f7). |
| 1.1.0 | Requirement origin/authority and reassessment of agent-created friction: [129d452](https://github.com/jresearchsoftware/shared-governance/commit/129d452ddfa6b9ac1030ccc7803994793467ab2d). |
| 1.2.0 | Initial Task Handoff topic: [73798b9](https://github.com/jresearchsoftware/shared-governance/commit/73798b919efbd0d8b0ee1317bf84a6c48d7e99d1). |
| 1.3.0 | Producer self-adoption and conditional native ready-state guidance: [80318d0](https://github.com/jresearchsoftware/shared-governance/commit/80318d00ec14ee3bc49a1b94cbc24e859371f80f). |
| 2.0.0 | Execution-cycle Step, chronological charter/Decisions, result routing and Direct/Deliberative strategies: [1b97f0a](https://github.com/jresearchsoftware/shared-governance/commit/1b97f0aadcc769c04415d8f4855098cee35b9f3a). |
| 2.1.0 | Workflow-aware GitHub governance: [c3fbc8c](https://github.com/jresearchsoftware/shared-governance/commit/c3fbc8c2d10982889bea526161f810902def4289). |
| 2.2.0 | Separately adopted independent-review methodology: [15e8191](https://github.com/jresearchsoftware/shared-governance/commit/15e8191435a126e54b4d1739a73fab112e01c081). |
| 2.4.0 | Contract and Decision Maintenance: [9bd05c8](https://github.com/jresearchsoftware/shared-governance/commit/9bd05c89f15e6c83a3d84f68368d7a8ef50f3119). |
| 2.5.0 | Context Loading/JIT as the ninth separately adopted topic: [88a95f7](https://github.com/jresearchsoftware/shared-governance/commit/88a95f7604b2d81d7a3dd3f76f095beddb71bdab). |
| 3.0.0 | TH-028 executor Draft/Ready duties, PV-006/007 preparation/source freeze, and the explicit TH/IR methodology split: [9caedb8](https://github.com/jresearchsoftware/shared-governance/commit/9caedb8a073d030a5a9b4e721cfd8430b002debd). |
| 4.0.0 | New PC-013 and strengthened IR-012–015: [99034dd](https://github.com/jresearchsoftware/shared-governance/commit/99034dd708e5d0201060986b561ada4d2cffd453). |

The initial Step 1 rationale selected 4.0.0 from stricter review obligations.
[Owner Decision 6364617205](https://github.com/jresearchsoftware/codex-relay/issues/174#issuecomment-6364617205)
requires technical and behavioral compatibility instead. The stricter PC-013
and IR-012–015 wording does not prevent the Skill from consuming older selected
rules. Relay's project adoption selected 5.0.0 under Task #186 and selected 7.0.0 under Task #213 and now selects 7.0.1 under Task #199; it
does not impose that producer policy as every consumer's dependency floor.

| Accepted Shared version | Actual Skill compatibility |
| --- | --- |
| 2.4.0 | The immediately preceding release has eight protocol files and lacks `vibevm/vibespecs/protocols/context-loading.md`. The Skill's explicitly routed ninth topic would be missing. Its immutable distribution is `5b33f826f0a9dbba5f61f5524060027dba9e02de`. |
| 2.5.0 | First complete nine-file layout, including Context Loading. Task Handoff already supplies chronological authority, execution-cycle Step, canonical Outcome routing, Direct/Deliberative acceptance, warning disclosure and protected continuation. Independent Review already supplies evidence, provenance, rereview, independence and Deliberative judgment. Its immutable distribution is `d691c1b9ad8c1bdababbf15da4ec7c69399e1e02`. |
| 3.0.0 | Adds stable numeric anchors, TH-028 Draft/Ready duties, preparation-before-freeze and the TH/IR methodology split. Relay independently retains Writer-owned Draft/Ready and publication safeguards; adopting both complete TH and IR preserves the methodology. No missing implementation capability requires excluding 2.5.0. |
| 4.0.0 | Strengthens finding classification and scope preservation. These selected governance obligations require reading/application, not different Skill interfaces, layout or Relay schemas. |
| 5.0.0 | Retains the layout and required behavior; the scoped changes below need no Relay implementation change. |

The authored manual previously referred to numeric TH/IR clauses introduced in
3.0.0. It now names the existing sections of the complete selected protocols:
Task Handoff's "Stable charter and chronological authority", "Step as an
authorized execution cycle", "Canonical Outcome publication target", "Exact
result and independent assessment", "Result acceptance strategies" and
"Authorized continuation and completion", plus Independent Review's "Judgment,
independence and publication". These exact headings exist in every assessed
version from 2.5.0 through 5.0.0. No invented clause mapping, copied replacement
protocol, numeric-anchor lookup or newer-version fallback is needed.

This navigation correction changes no Relay v4 or retained v3/legacy behavior.
The Skill keeps the stronger explicit native actor, authority, exact-head,
Writer, review, protected-operation and publication bindings in its manual and
bundled product schemas. It reads each consumer-selected protocol completely,
including its applicability and exceptions. Later mandatory governance wording
does not make earlier package layouts technically unusable. The adjacent 2.4.0
file gap, rather than a resolver rejection caused by our own range, establishes
the lower boundary. Earlier releases cannot supply the ninth topic introduced
in 2.5.0. Candidate 3.0.0 may still change before its first independent source
acceptance; frozen 2.0.1 and earlier payloads remain unchanged.

The immutable 4.0.0 distribution is
[`f14da40725cd35fb3117ae84a506256505340787`](https://github.com/jrs-vibevm/org.jresearch.ai.development-governance/tree/f14da40725cd35fb3117ae84a506256505340787).
It remains in frozen Relay 3.1.0 and earlier releases. Relay 4.0.0 selects
Shared 5.0.0 for standalone and publisher closure evidence, independently of
the native minimum. Source history and native fixture
evidence are distinct: qualification exercises 2.5.0, 3.0.0, 4.0.0 and 5.0.0,
checks the shared section names used by the manual, and separately acquires
2.4.0 without Relay to prove the missing Context Loading file before checking
native range refusal. See [Step 2 qualification](qualification/task-174-step-2.md).

## Actual 4.0.0-to-5.0.0 impact

The complete protocol delta is in
[Shared source 99034dd to d0b3d67](https://github.com/jresearchsoftware/shared-governance/compare/99034dd708e5d0201060986b561ada4d2cffd453...d0b3d67ef94a5537ebd4a2bbf4a38e3a6629c0c9).
Six of the nine protocol files are unchanged. The three affected topics are:

| Change | Impact on Relay and required treatment |
| --- | --- |
| New RA-006 | Initiative and optional proposals remain welcome, but mandatory outcomes/proof must come from owner intent, accepted contracts/protected invariants or authorized Decisions. It explicitly bounds proof to the accountable deliverable, preserves real manifest/dependency/security/rights/interface defects and required integrations, and requires clear per-finding dispositions. Read and apply the complete selected Requirement Authority topic. This is compatible with Relay's existing scope, Decision and independent-review boundaries; do not add a native schema field, release gate or automatic scope classifier. |
| TH-002 and TH-026 now apply RA-006 | Use it when authoring completion criteria and considering continuation. Reconcile a proposed agent-authored obligation through the existing trusted Decision mechanism before treating it as mandatory. An apparent obligation cannot be silently discarded either. No new Step, migration, public Request or authority transport follows. |
| IR-013 now applies RA-006 | Classify findings and make consequential recommendations/dispositions explicit. A generic request to fix findings does not accept an obscured deferral or scope proposal. Existing native finding and Decision mechanisms suffice; the new reference does not grant a CR Task-wide scope authority. |
| New TH-029 | Only Tasks that actually include applying generated client settings require supported live comparison and application confirmation. Relay's optional ChatGPT bootstrap supplies text for owner use and does not claim settings synchronization. A dependency update acquires no application duty. If an owner separately includes application in a Task, honor the complete selected TH rule and the supported client binding; unavailable evidence stays visible. |

Shared 5.0.0 also changes its ChatGPT projection tools and receipt contract.
Relay's VibeVM Skill uses the selected package's protocols and ordinary native
Skill projection; it does not depend on those Shared ChatGPT projection tools
or their removed receipts. Native protocol consumption therefore requires no
adaptation. The complete standalone payload does ship that helper and its
documented interfaces: replacing it changes receipt generation, status schema
and handling of edited generated outputs. That whole-package change determines
Relay 4.0.0's [major classification](relay-guidance.md#version-and-provenance),
while Relay's own standalone projector receipts and native VibeVM slot receipts
retain their contracts. See the
[5.0.0 changelog](https://github.com/jresearchsoftware/shared-governance/blob/d0b3d67ef94a5537ebd4a2bbf4a38e3a6629c0c9/packages/development-governance/CHANGELOG.md).

The immutable 5.0.0 distribution is
[`30a23f467c30c41fec918204cbbf2ecfffd7bef5`](https://github.com/jrs-vibevm/org.jresearch.ai.development-governance/tree/30a23f467c30c41fec918204cbbf2ecfffd7bef5).
Its package-major classification is truthful for Shared's whole consumer
contract; it is not, by itself, a Relay compatibility failure.

## Delivery-specific protocol authority

The native VibeVM package declares a real `>=2.5.0` dependency. The consumer
provides supported explicit immutable source roots, resolves the graph and
commits its exact lock, slots and generated routes. The native Skill routes to
the consumer's resolved `org.jresearch.ai/development-governance` slot from that
lock. It must not route to a producer-fixed version path, a separate Skill protocol bundle,
the Relay producer's root policy or a moving network lookup. A missing or
inconsistent lock/slot is a maintenance error to reconcile through normal
reviewed installation, not permission to fall back to another protocol copy.

The standalone Codex Skill deliberately bundles an immutable attributed Shared
snapshot, so execution needs no VibeVM or network. Its provenance identifies
that snapshot and every projected file. This is one copied upstream protocol
source, not a second authored implementation. The two forms share the Relay
product contract and authored manual but may have different protocol routes,
inventories and provenance. Whole-tree byte identity is not their parity rule.

The current accepted Shared Publisher qualifies required dependency closure
using the schema-7 lock and matching frozen versioned slots committed beneath
the package source root at the exact accepted source SHA. Its
[supported tree-v1 interface](https://github.com/jresearchsoftware/shared-governance/blob/414077e956aa47b18ddc436f68c3245b508baf46/docs/shared-publisher.md#export-and-readiness)
permits this source-time evidence to remain outside the explicit export inventory.
Deliberate vendoring also remains supported: any exported slot must carry its
complete shipped inventory. Removing or relabeling a required dependency to
bypass closure qualification remains unsupported.

Relay's existing frozen distributions retain their nested producer lock and
Shared slot unchanged. The earlier mandatory-export statement describes the
historical publisher restriction, not the current interface. Omitting those
bytes from a future thin Relay package requires separately authorized packaging
work and an appropriately classified new version. The publisher integration
migration changes no frozen payload, native dependency requirement or protocol
selection. Retained nested evidence is neither a consumer lock nor an alternate
reading route. Qualification must establish one selected Shared identity in the
consumer graph and routes, no Shared bundle in the native Skill, and no active
route to the nested evidence. Disclose retained snapshot bytes explicitly.

Thin publication does not promise offline acquisition: native consumers need
configured registries or explicit Git roots, and offline use needs retained
consumer evidence/cache or a supported local source. VibeVM 1.0.7 still rejects
`dev-requires` and inline `optional=true`; source-time publisher qualification
does not establish broader native schema support.

## Deliberate updates and Relay versioning

On an intentional consumer Shared update, inspect the changes to the actually
used complete protocols, including applicability, exceptions, cross-references
and Relay bindings. Use the consumer's existing review and dependency workflow.
A compatible or irrelevant change needs only the consumer's chosen dependency,
lock/materialized state and any actually affected local adoption guidance.
It does not require a new Relay Skill version, a release from an unrelated
producer, new downstream configuration or another universal qualification gate.

If a used shared change materially requires different Relay behavior, guidance,
interfaces or packaging, reconcile it through Relay's normal authorized change
and issue an appropriately classified new Skill version. An open-ended lower
bound never authorizes silently changing those contracts. The consumer retains
its previously accepted exact lock while resolving an incompatibility, and can
roll back to its complete reviewed prior state. No runtime `latest` resolution
or rewriting of immutable releases is involved.

The delivery change from Relay 2.0.1 is classified **3.0.0 MAJOR** for this
implementation: the native form removes its published `references/shared/**`
paths and standalone `scripts/project.py` helper, replacing their supported
navigation/packaging contract with the consumer-locked protocol route. The
native install/update/rollback commands and v4/retained product authority remain
intact. The broader dependency range alone would be a compatible addition;
the removed native payload interfaces determine the higher category here under
PV-002/PV-004. PV-007 forbids changing frozen 2.0.1 bytes. Shared 5.0.0
availability alone justifies no Relay version increment.
