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

## Required protocol semantics

The Skill adopts these complete applicable topics for Relay product guidance.
The rule groups below use the repository's adopted 5.0.0 addresses for comparison;
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
rules. Relay's own project-wide adoption now selects 5.0.0 under Task #186; it
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
It remains the deliberate standalone snapshot and producer release-closure
evidence, independently of the native minimum. Source history and native fixture
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
or their removed receipts. That unrelated tool change therefore requires no
Relay adaptation. Relay's standalone projector receipts and native VibeVM slot
receipts retain their own contracts. See the
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
lock. It must not route to a fixed 4.0.0 path, a separate Skill protocol bundle,
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
