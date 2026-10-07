# VibeVM governance distribution: Relay-side design

Task 59, Step 1 analysis, 2026-10-07.

**Recommendation: CONTINUE_EXPERIMENT.** Test passive, independently versioned
governance flows and Landscape's subagent guidance against Git vendoring plus
native Codex skills. VibeVM has relevant distribution primitives, but neither
their operational benefit nor their suitability for Relay has been demonstrated.
Keep normal execution on reviewed, committed context. Keep ChatGPT Project
Instructions as an owner-applied, project-local bootstrap with a Git-tracked
source proposed for a later authorized experiment.

This is a design proposal, not an adoption or a replacement policy. The current
[AGENTS.md](../AGENTS.md), [execution policy](execution-policy.md) and product
contracts continue to govern. No VibeVM installation, package publication,
consumer migration, new repository, other-project mutation, deployment, merge
or Issue closure is part of this change. Task 59 remains open. Follow-on work
requires owner admission; no later Step numbers are allocated here.

## Evidence and its limits

The Relay inventory was read at
`2cb84b4d0bd4bcbfbd0aa7d686c14aeaf59eba4a`. Its instruction surfaces are
classified below; this analysis does not inventory the live Documentation or
Landscape repositories. Likely consumers and cross-project reuse come from the
Task charter, not proof that those repositories have adopted these rules.

The external methodology baseline is **VibeVM v1.0.7**, upstream
[`vibevm/vibevm` release](https://github.com/vibevm/vibevm/releases/tag/v1.0.7),
published 2026-10-04. An unauthenticated release/tag API read on 2026-10-07
resolved the tag to **`b6659978453f50e6d1d4d99626d70b980a2c5847`**.
The source archive at that commit was read without installing or running VibeVM.
Its Cargo workspace also declares 1.0.7. The English manual is the
`org.vibevm.core/vibevm-docs/v1.0.0` package included in that exact source;
the manual's package version is distinct from the tool version.

Consulted upstream sources are linked to that commit, rather than moving
`main` or the website's `latest` route:

| Source | Design question |
| --- | --- |
| [README][up-readme], [alpha notes][up-alpha], [changelog][up-changelog] | Release identity, compatibility posture and update risks |
| [Package kinds][up-kinds], [flow authoring][up-flow], [manifest][up-manifest] | Native kinds, authoring shape, skills and executable declarations |
| [Boot lane][up-boot], [dependency visibility][up-visibility], [compiler contract][up-compiler] | Loading, edge semantics, contract/source and provisional compilation |
| [Lock format][up-lock], [versions][up-versions], [publishing][up-publish-doc] | Reproducibility and conflicting immutability descriptions |
| [Workspace setup][up-workspace], [private registry][up-private], [offline workflow][up-offline], [agent skills][up-skills] | Authoring versus distribution, maintenance and projection |
| [Version parser][up-version-parser], [package metadata][up-meta], [publisher][up-publisher] | Exact requirement syntax and mutable/frozen publication |
| [Boot generation][up-boot-code], [initializer template][up-core-template], [install record][up-record] | Actual default context, INDEX semantics and subskill recording |
| [Dependency placement][up-placement], [Codex paths][up-agent-paths], [skill declarations][up-skill-meta], [skill snapshot][up-snapshot], [managed redirect][up-redirect], [skill package phase][up-skill-phase] | Committed paths, copied projection, local preservation and explicit projection step |
| [Dependency sources][up-deps], [publication staging][up-staging], [locked acquisition][up-fetch], [registry fetch][up-drift], [install planning][up-plan], [slot verifier][up-verify], [apply][up-apply] | Workspace-to-package transport, source provenance and incomplete pin enforcement |

Source inspection is evidence about implementation, not exercised install,
update, rollback, offline, fresh-clone or consumer-runtime qualification.
OpenAI's [Projects documentation](https://learn.chatgpt.com/docs/projects) and
[skill documentation](https://learn.chatgpt.com/docs/build-skills), read on
2026-10-07, establish the client distinction and native skill discovery model.
They are moving provider references, not part of the VibeVM version pin.
The live owner's Project Instructions and primary Relay execution warning
surfaces are unavailable to this credential-free worker. No absence-of-drift
or absence-of-execution-warnings claim follows.

## Ownership inventory

Classes: **P** = Relay product/version contract; **L** = Relay-local development
overlay; **G** = candidate shared governance; **S** = specialist-owned guidance;
**D** = dynamic authority/evidence, excluded from the package graph.
Classification applies to semantic slices, not whole files.

| Existing surface and rule slice | Class and canonical owner | Distribution decision |
| --- | --- | --- |
| [AGENTS: context loading](../AGENTS.md#context-loading-and-governance-layering): small startup context, targeted reads, refresh mutable facts after recovery | G candidate; neutral owner still to be selected | Context-discipline flow; keep Relay paths and authority-model distinctions local |
| Same section: live legacy Issue body, native request authority, publication language | P for authority semantics; L for English publication convention; D for current records | No extraction of the current Task contract or GitHub state |
| [Task identity and startup rename](../AGENTS.md#task-identity-and-startup-rename): Task/Step, closure, labels, CR title synchronization, manual versus automatic title handling | P, Relay | Travel with Relay; titles, labels and closure decisions themselves are D |
| [Canonical checkout and safe Git handoff](../AGENTS.md#canonical-checkout-and-safe-git-handoff): exact starting head, continuation branch/PR binding, worker/Writer import | P, Relay | Product contract; branch, worktree, head and publication observations are D |
| [Execution context and shells](../AGENTS.md#execution-context-and-shells) and [CONTRIBUTING](../CONTRIBUTING.md) | L for local shell/toolchain/test recipes; P for protected-entrypoint boundary | Keep local; a general safer-transport principle alone does not justify another package |
| [Admitted goal](../AGENTS.md#work-within-the-admitted-goal) and [execution policy](execution-policy.md): evidence-driven correction, stop on missing authority or ambiguous mutation | G candidate for the general principle; P for reservation, replay, result and route mechanics | Do not extract the whole execution policy or its runtime prompt module |
| Same surfaces: default profile, manual/automatic route choice, parent admission stability | L for this repository's defaults; P for Relay admission behavior; D for resolved profile | Landscape may recommend; it cannot select or mutate an admitted profile |
| [Shared subagent workflow](../AGENTS.md#shared-subagent-workflow) and [adopted SUBAGENTS](codex/SUBAGENTS.md) | S, Model Landscape | First specialist package candidate; Relay adoption/permission and Writer boundaries stay local |
| [Material contract change gate](../AGENTS.md#material-useroperator-contract-change-gate): owner authorization for material workflow changes | G candidate principle; P for canonical Issue and OWNER_DECISION_REQUIRED enforcement | Include only general scope discipline in a future review flow; preserve existing Relay gate |
| [Independent review and finding provenance](../AGENTS.md#independent-review-and-finding-provenance): aggregate findings, compare baseline, distinguish introduced/pre-existing/unknown, avoid scope expansion | G candidate, neutral owner pending | Review-evidence flow candidate; exact candidate binding, CR closure and native verdict mechanics remain P/D |
| [Minimum sufficient ceremony](../AGENTS.md#minimum-sufficient-ceremony): control costs, simplest usable path, avoid duplicate truth/state | G candidate | Proportional-controls flow for control decisions; do not export Relay-specific checks/Outcome cadence |
| Same section: promote accepted reusable decisions, distinguish task-local/experimental decisions | G candidate | Separate decision-promotion candidate; no decision ledger |
| [Proportional controls and operator usability](execution-policy.md#proportional-controls-and-operator-usability) | G candidate; neutral canonical source requires owner selection | Strongest shared candidate, with reuse across projects explicitly identified by Task 59 |
| [Execution warning disposition](execution-policy.md#execution-warning-disposition) | P for supported API scope and Outcome/annotation surfaces; G candidate for evidence-based disposition | Keep whole procedure local; potential generic review guidance must not change warning acquisition or acceptance |
| [Developer stop evidence](execution-policy.md#developer-stop-evidence), [.codex hooks](../.codex/hooks/README.md), [hook registrations](../.codex/hooks.json) | L, Relay development | Optional recovery/diagnostic/Stop behavior stays local; no package hooks or required checkpoint |
| [Product boundaries](../AGENTS.md#preserve-the-product-boundaries), [architecture](architecture.md), [contracts](../contracts/README.md), [controller](../controller/README.md), [runtime](../runtime/README.md), [Reviewer](../reviewer/README.md) | P, Relay | Task/Step/CR, admission, identity, independent acceptance, safe Git import and publication stay product-owned |
| [Deployment](../deploy/README.md), [integration](integration-reference.md), [consumer](../consumer/README.md), [CLI integration](codex/cli-integration.md), [self-dogfood workflows](self-dogfood-workflows.md) | P for product interfaces; L for this repository's operations | No VibeVM runtime, deployment or credential role; installed consumer config and state are D |
| [Validation and handoff](../AGENTS.md#validate-and-hand-off), scripts/tests and [Issue template](../.github/ISSUE_TEMPLATE/codex-task.md) | L for candidate commands; P for launch/result schemas and Outcome semantics | Static product schemas/templates ship with Relay; instantiated Task/CR/check/Outcome records are D |
| [SECURITY](../SECURITY.md) | P/L, Relay | Reporting channels, scanning limits and consumer obligations stay local; no claimed shared security service |
| ChatGPT Project Instructions, outside Git | L for project orchestration/bootstrap; D for currently applied client configuration | Owner-applied local projection proposed below; current content not inspected |

The same paragraph can contain both a reusable principle and a Relay
enforcement mechanism. Extraction must preserve its qualifiers, examples and
exceptions, then leave a Relay-owned binding to the existing mechanism.
Lazy loading cannot make a package containing unrelated product rules coherent.

**Never package** live Issue/CR/PR bodies or decisions, Step/route/profile state,
reviewed/admitted/base/head SHAs, checks and reviews, Outcomes, warning receipts,
reservations/recovery state, credentials, installed host state or diagnostic
checkpoints. A package can explain a general evidence principle; it cannot
carry the evidence or authorize a launch, publication, review, merge or closure.
Relay version X must still supply its own semantics without VibeVM.

## Package and workspace candidates

VibeVM has eight kinds: `flow`, `feat`, `stack`, `tool`, `mcp`,
`lang`, `doc`, `app`. Working conventions fit **flow**. A skill is a
`[[skill]]` declaration inside a package, not a ninth package kind.
`doc` companions are read rather than installed; they are unsuitable as the
sole delivery vehicle for adopted instructions. Feature/technology/language
packages would misdescribe these slices. Executable kinds are unnecessary.
[Kinds][up-kinds] and [manifest][up-manifest] define these distinctions.

All coordinates below are illustrative, not registered namespaces or selected
repositories. The owner must choose the neutral source, publishers and release
authority. A reversed-domain group asserts a name, not authenticated ownership.

| Candidate coordinate | Owner, coherence and change cadence | Likely consumers and readiness |
| --- | --- | --- |
| `org.jresearch.governance/proportional-controls` | Neutral; one control-decision procedure covering concrete harm, cost, usability, prevention versus detection/recovery, supported environments and accepting risk. Change on accepted control-governance decisions. | Relay and Documentation; Landscape/future projects may selectively adopt. First neutral candidate because the Task identifies real shared reuse. |
| `org.jresearch.governance/context-discipline` | Neutral; startup/JIT loading, stable instructions versus mutable facts, bounded refresh and routing to canonical detail. Change when context-handling practice changes. | Relay and potentially both other projects. Second candidate, subject to checking their actual source rules before extraction. |
| `org.jresearch.governance/review-evidence` | Neutral; finding provenance, scope-aware prescriptions, independent judgment and material contract comparison. Change with accepted review methodology. | Relay and Documentation; Landscape only if useful to its evidence review. Defer release until cross-project examples establish the common subset. |
| `org.jresearch.governance/decision-promotion` | Neutral; deciding whether an accepted improvement is local or reusable and promoting it to its canonical owner. Change with promotion practice. | Potentially all three; defer until repeated use/sync pain warrants a separate dependency. It must not distribute current decisions. |
| `org.jresearch.landscape/subagent-workflow` | Landscape; delegation triggers, complete bounded assignments, per-assignment profile matrix, coordination and verification. Change on Landscape's accepted guidance updates. | Relay first, other projects selectively. First specialist candidate; retain its current profile matrix in this package initially. |
| `org.jresearch.landscape/model-selection` and optional `model-evidence-docs` | Landscape; selection flow and separately versioned doc evidence companion, if it later authorizes that split. Evidence changes more frequently than operating instructions. | Only consumers needing model-selection advice. Deferred; no moving model lookup or compulsory ratings corpus during admitted work. |

Initially use **simple, copy-materialized flows**, each with a short optional
boot pointer, one focused instruction-only Codex skill and ordinary references.
No package needs tools, MCP, apps, binaries, scripts, lifecycle extensions,
install hooks, credentials or capability-provider indirection. Package kind
alone does not guarantee passivity: declarations and the complete transitive
content must be reviewed.

A possible neutral authoring workspace follows VibeVM's own member layout:

```text
<owner-selected neutral Git source>/
  vibe.toml                         # [workspace], member selection
  vibevm/vibepacks/org.jresearch.governance/
    proportional-controls/v0.1.0/
      vibe.toml                     # [package], kind="flow", format="simple"
      README.md
      vibevm/vibespecs/
        boot/proportional-controls.md
        flows/proportional-controls/...
        skills/proportional-controls/SKILL.md
        skills/proportional-controls/references/...
    context-discipline/v0.1.0/...
```

This is an illustrative tree, not files created by this Step. A workspace
coordinates authoring; it does not make its members one universal package or
require a shared version line. Do not use a family bundle that forces unrelated
governance releases into version unison. Deferred candidates need not exist yet.
Landscape publishes from its own repository-local authority, not this workspace.

The Git registry documentation uses repositories named `group.name` and
version tags. Workspace authoring and per-package distribution are different
surfaces; a monorepo workspace is not proof that remote consumers can address
every nested member using one arbitrary Git URL. The later experiment must
verify the supported member/source/publishing path before creating repositories.
Local/path sources can test authoring without a private registry; private Git
sources are an option when separately authorized credentials are needed.
Do not invent an unsupported monorepo transport. [Workspace][up-workspace],
[private sources][up-private] and [publishing][up-publish-doc] describe the routes.

Dependency direction is consumer → selected neutral flow or Landscape flow.
Neutral flows initially have no inter-package dependencies. Landscape may adopt
neutral governance under its own authority, but unrelated governance must not
arrive accidentally through a subagent dependency. Neither publisher depends
on Relay contracts; Relay's product release is outside this context graph.
Consumers can intentionally remain on different versions. A new version in
the source is a proposal to adopt, not an execution-time policy change.

## Loading and layering

Package ownership, materialization, boot linkage and prompt loading are
separate decisions.

| Layer | Proposed content | VibeVM mapping and boundary |
| --- | --- | --- |
| Consumer startup | Existing local authority hierarchy and component routes; tiny shared invariant/pointer only when needed | Preserve human-owned AGENTS content. Consider a bounded managed block only in a later migration; no generation of the whole file. |
| Stable package boot | Short package-purpose and skill/reference route; no history, session IDs or current task state | Consumer-selected static edge may compile this into STATIC; keep it small and byte-stable across sessions. Do not claim measured cache savings. |
| Package boot references | Other short routes and supported conditional context | Default `link="dynamic"` references materialized snippets through INDEX. It does not imply a network fetch, dynamic authority, or that all unconditional text is deferred until useful. |
| Detail used for a task | Control procedure, review method, subagent assignments and examples | Native skill description selects full SKILL and references on demand. Materialize these eagerly at maintenance time, load them JIT from local files. |
| Local product detail | Relay contracts and component documents | Existing local routing; not package dependencies, compiled shared text or an externally replaceable source. |
| Mutable execution facts | Current authority, Git/check/runtime observations | Trusted admitted input and fresh bounded observations outside all boot/package content. |

[Boot generation][up-boot-code] distinguishes a manifest's linkage from INDEX's
serialized `kind`: unconditional dynamically linked references are emitted as
`static` entries, while conditional entries are `dynamic`. Read the
[boot contract][up-boot] as an ordered reading protocol, not a blanket promise
of lazy context. Measure actual startup reads in the later experiment.

Order stable cross-task instructions before more frequently changing project
detail and task observations, without encoding the latter into shared boot.
This mutation-frequency layering can reduce prefix churn; it confers no
authority precedence. VibeVM's graph/visibility controls govern content access,
not owner, worker or Reviewer permission. Use direct explicit dependencies
initially rather than friend/exclude overrides or abstract provider selection.
[Visibility][up-visibility] describes the separate access axis.

**Simple versus normal:** simple carries an ordinary readable tree; native
skills already provide JIT prompt loading. Normal separates a cheap
`contract/` interface from a heavier `source/` implementation and supports
use-directed compilation/tree shaking. That can be useful for a future large,
coherent package, but it is not needed for the first passive flows. The pinned
[compiler contract][up-compiler] marks structural/JIT loading and link tables
provisional; that JIT path still relies on an LLM following directives.
Deterministic ahead-of-time/static compilation is a separate implemented path.
Do not add a compiler requirement merely to split short prose,
or equate its tree shaking with qualified Codex progressive disclosure.

**Subskills:** the docs describe eager, lazy-push and lazy-pull delivery with
activation conditions. This is finer than package selection, but cannot justify
mixing different semantic owners. The pinned [install record][up-record] writes
an empty `subskills_active` list; end-to-end selective delivery is unqualified.
Start with eager local reference files. Later consider same-owner optional
examples/adapters as subskills only after exercising their activation and
offline behavior. Mandatory rules must never disappear behind an optional
activation description.

OpenAI documents native skill name/description discovery followed by loading
the full instructions when invoked. This is sufficient for the proposed Git
baseline too. VibeVM projection must be checked against Relay's qualified
Codex version rather than assuming moving provider documentation proves
compatibility with an installed consumer.

## Maintenance, identity and supply-chain constraints

The intended adoption transaction, to be exercised later, is:

1. In a bounded maintenance change, select the exact VibeVM tool release and
   inspect its changelog/source. Select owner-approved package releases.
2. Resolve exact requirements, inspect the entire graph and passive content,
   materialize it and project the required Codex skills.
3. Review and commit manifest, lock, dependency content, skill projection and
   bounded boot changes together. Verify all local overlays and links.
4. Normal execution reads that exact consumer revision. It does not run
   `vibe update`, resolve a moving branch, contact a policy service, initialize
   VibeVM or depend on the machine-global cache.

The proposed experiment tool pin is v1.0.7 at the upstream commit recorded
above. A later owner-approved upgrade changes that pin only after reviewing
the new release and its compatibility effects.

The live copy layout is
`vibevm/vibedeps/<group>.<name>/<version>/`, including slot metadata.
Codex project skills are copied to `.agents/skills/<skill-name>/`, rather than
read directly from the dependency slot. Declare `agents=["codex"]` and bounded
`include` selection to avoid unintended client projections. Project only the
required skill/reference files and commit the complete projection with its
dependency bytes. An ordinary install must not be assumed to perform this:
automatic declared-skill projection belongs to the package phase, and explicit
skill installation is another supported surface. Confirm the exact maintenance
command sequence later. [Placement][up-placement], [agent paths][up-agent-paths],
[skill metadata][up-skill-meta], [snapshot][up-snapshot] and
[package phase][up-skill-phase] establish these source facts.

The [managed redirect][up-redirect] preserves content outside its
`<vibevm>` block, but can replace a recognized old whole-generated redirect.
Compilation can expand includes, rewrite links and add framing; compiled boot
is not a byte-identical source copy. Review the actual authored and generated
diffs and retain citations to canonical source, not positions in STATIC.

For v1.0.7, **write `version="=0.1.0"`, not `"0.1.0"`** when an exact
requirement is intended. The [version parser][up-version-parser] treats bare
SemVer as a caret range. The [lock][up-lock] records content identity and source
information; the consumer's accepted Git commit and committed bytes remain the
normal execution truth. Do not add a provenance ledger duplicating the lock.

Published versions are **not inherently immutable**. Pinned docs conflict:
the versions page describes mutable snapshots but also refusal of changed
bytes at the same version; the lock/flow pages contain stronger immutability
claims. Source defaults `frozen` to false and the [publisher][up-publisher]
explicitly retags mutable releases. Source review found no publisher enforcement
of the frozen flag. Require an owner-approved frozen-release posture and
deliberate new versions as publisher governance; metadata alone does not prove
enforcement. Retain reviewed lock content hashes and resolved commits,
plus committed text, rather than relying on a version number alone. A moved tag
must not silently replace accepted consumer bytes. Whether a clean reinstall
rejects, retains or refreshes such bytes needs an actual test. Source passes the
locked hash into acquisition, but registry fetch returns its last mismatched
result when all sources disagree. Comments promise a caller ContentDrift error;
the inspected install path instead accepts the returned hash, uses it for slot
verification and rebuilds the lock from fetched results. This is a material
comment-to-code gap, not proof of enforced final pin refusal. Treat re-resolution
as potentially changing same-version bytes and scrutinize its diff.
[Acquisition][up-fetch], [registry fallback][up-drift], [planning][up-plan],
[slot verification][up-verify] and [apply][up-apply] supply the source evidence.
It is an upstream baseline limitation, not a defect introduced by this Relay
documentation change or authority to remediate VibeVM.

Content hashes identify bytes, not a publisher's authority. Git review/release
ownership and the consumer's adoption decision establish policy authorization.
No source may gain GitHub, deployment or review privileges through installation.
Review transitive declarations, projection collision behavior and authored file
preservation, not only the root package's README.

**Initialization needs special care.** The pinned [core template][up-core-template]
introduces a WAL-based boot procedure and its own Human/Spec/Tests/Code
precedence. Those defaults conflict with Relay's small/JIT startup and dynamic
GitHub authority model. They must not become Relay policy as an incidental
scaffold side effect. Later authoring should use only the necessary native
manifest/layout and an explicitly reviewed bounded projection. If the supported
path requires material operator-contract changes, return to the owner decision
boundary; do not patch around it with a private implementation.

The tool is closed alpha even though its release API says `prerelease=false`.
Upstream allows breaks without migrations. Its alpha recovery examples include
refreshing/reinitializing derived state; those are not approved Relay execution
or rollback procedures. Pin the tool itself and preserve readable Git artifacts.
Do not require a private registry or an installed VibeVM binary for Relay runtime.

**Fresh-clone/offline hypothesis:** copied dependencies and projected local
skills should be readable with no VibeVM binary or network, provided every
referenced file is committed and relative projection links are complete.
That is a source-informed hypothesis, not a passed test. Cache-based offline
installation is different: it still needs VibeVM and sufficient local sources,
such as a warmed store or local registry/mirror. Test a
fresh clone with empty home/cache and disabled network separately from
maintenance offline resolution. Reject or revise any path that secretly needs
boot-time materialization or a native `spec://` resolver. Preserve a plain-file
navigation path for native skills. [Offline documentation][up-offline] and
[agent projection documentation][up-skills] motivate these tests.

## ChatGPT Project Instructions operating model

Choose **manual, owner-applied instructions from a reviewed project-local Git
artifact**, with minimal bootstrap/continuation content. This is the proposed
PoC operating model, not a change to live settings in Step 1.

| Content | Canonical owner and placement |
| --- | --- |
| ChatGPT client navigation, how to continue discussion, preferred discussion style and routes to project sources | Local project owner; small Git-tracked Project Instructions source |
| Which actor handles implementation versus independent review | Relay product contract; local bootstrap points to the accepted product contract rather than restating Step/CR mechanics |
| Detailed Relay Task/Step/admission/Outcome/deployment rules | Relay product/repository version; never an independent shared package or a manually maintained second rule set |
| Reusable control/context/review principles | Selected neutral package versions; include only an essential short bootstrap excerpt if ChatGPT actually needs it before source access |
| Model/subagent recommendations | Landscape's deliberately adopted version; normally on-demand material rather than long always-loaded Project Instructions |
| Active Task, Step, PR, head, checks and current Outcome | Live canonical authority/evidence; excluded from durable Project Instructions |

The [official Projects page](https://learn.chatgpt.com/docs/projects) describes
shared client instructions and sources; Codex CLI does not expose that Project
view. Repository skill projection is therefore not Project settings mutation.
The consulted VibeVM surfaces project files and agent skills, not a qualified
ChatGPT Project Instructions setter. No supported, bounded settings update and
read-back path was established from the consulted provider documentation.
This is an evidence gap, not a universal claim that no such API can exist.
Do not use browser automation, credentials or another settings interface merely
to remove the manual handoff.

For a later admitted experiment, propose one local canonical source such as
`docs/chatgpt/project-instructions.md`. Its human-owned overlay survives
shared dependency updates. If a minimal shared excerpt is useful, render it
from committed pinned input during maintenance into the single ready-to-paste
artifact and review that diff with the overlay. Do not blindly concatenate
policies or import VibeVM's generic bootstrap. The source's Git commit identifies
the package selection and local overlay together.

The owner reviews the Git diff, selects an accepted artifact revision, and
applies its payload using the client's supported instructions editor. A short
source annotation may name repository/path, accepted commit and SHA-256 of the
payload. Define the payload as UTF-8 with LF line endings, excluding that
annotation; do not hash the annotation into itself. Git and the artifact suffice;
no settings registry, receipt database or adoption bot is needed.

Detect drift at update/review time, or when a discrepancy appears: the owner
copies the actual live instruction payload into a temporary local file and
compares it with the selected Git revision, normalizing line endings only.
A source marker alone does not prove matching content. Distinguish an intentional
older adoption from unexplained edits. Live content/read-back is untested here;
do not impose a new comparison ceremony on every normal task.

Keep local client instructions operationally stable during admitted execution.
They route to authoritative product and task sources, and shared excerpts are
derived copies with an explicit origin, never independently editable policy.
When live client guidance contradicts the admitted authority, surface the
conflict for owner disposition before dependent work; do not silently normalize
it into a new rule. Provider instruction precedence is not changed by this design.

Rejecting an update leaves both Git and the live Project at the prior adopted
payload. After a merged update is rejected operationally, revert the consumer
Git change through ordinary review and manually reapply the previous accepted
payload; compare the live result. Shared packages may advance while this
consumer stays pinned. A package rollback does not erase the local overlay.
No moving-latest fetch occurs in either repository execution or ChatGPT startup.

## Comparison and next experiment

The credible baseline is a shared Git source at an exact tag/commit, the same
instruction-only native skills, and a small bounded vendor/update script or
subtree adoption. Commit source identity and readable files; run updates only
during maintenance. This Step compares designs, not measured tool performance.
Do not credit VibeVM with JIT loading that native skills already provide.

| Criterion | Simple Git/native-Skill baseline | Later VibeVM experiment and evidence needed |
| --- | --- | --- |
| Ownership clarity | Separate source directories/repos and explicit owners | Same semantic owners; confirm coordinate/graph does not blur them |
| Cross-repo update effort | Select SHA, vendor files, review diff | Adopt one approved new version in two separately authorized consumers; count commands, manual edits and reconciliation time |
| Reviewability | Plain content and source-reference diff | Compare manifest/lock/materialization/skill/boot diff size and unrelated churn for the same policy change |
| Reproducibility | Exact Git source plus committed bytes | Recreate selected hash/commit; test republish/tag movement and refusal/refresh behavior |
| JIT/context size | Native skills plus short AGENTS routes | Measure startup and invoked-detail characters/reads on the same tasks; distinguish linkage from actual prompt loading |
| Offline/fresh clone | Committed plain files; no update script needed at execution | Empty home/store, no VibeVM, no network: exercise native discovery and every reference; separately test warmed-cache maintenance |
| Local overlay safety | Script confines writes to owned vendor paths | Test authored AGENTS, local skills and Project Instructions overlay preservation, collisions and removal ownership |
| No dual authority | Local product contracts and live task evidence remain canonical | Check default scaffold and all transitive context for competing hierarchy/state; test simplest owner path |
| Rollback/removal | Revert vendor commit; retain plain files or local routes | Revert complete dependency transaction, then remove tool/manifest/projection without stranding readers; test Project Instructions reapplication |
| Tooling cost | Git plus a small update script | Record binary/version/cache/lock/registry/projection maintenance, alpha recovery, failures and supply-chain review effort |

Static source-size baseline on the inventory revision: AGENTS.md is **23,422
bytes / 387 lines**; execution-policy.md **10,932 / 184**; SUBAGENTS.md
**10,455 / 174**. These are file sizes, not token usage or proof that all three
are loaded at startup. No reduced context or time saving has been measured.

The next owner-admitted phase should first select the neutral owner/source and
authorize a small passive authoring experiment: proportional-controls plus
context-discipline, with the Git/native-Skill baseline using identical prose.
Separately admit Landscape's subagent publishing experiment in Landscape.
Authorize each consumer adoption in its own repository, starting with one and
adding a second when its owner boundary is available. Avoid releasing the
deferred candidates until evidence supports extraction. This proposal creates
none of those sources or packages.

Continuation should resolve the observed version-doc conflict, init/projection
side effects, exact member transport, normal/subskill maturity and fresh-clone
requirements with bounded experiments. Keep tool/package updates deliberate.
Recommend ADOPT_BOUNDED only if observed synchronization savings outweigh the
extra tool/state/alpha cost while all ownership boundaries hold. Otherwise
retain the simpler baseline or recommend REJECT_FOR_NOW. Step 1 supplies the
design and test questions; package behavior and independent acceptance remain
unproved.

[up-readme]: https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/README.md
[up-alpha]: https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/docs-legacy/ALPHA-NOTES.md
[up-changelog]: https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/CHANGELOG.md
[up-kinds]: https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.core/vibevm-docs/v1.0.0/vibevm/vibespecs/model/packages-and-kinds.xml
[up-flow]: https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.core/vibevm-docs/v1.0.0/vibevm/vibespecs/authoring/write-a-flow.xml
[up-manifest]: https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.core/vibevm-docs/v1.0.0/vibevm/vibespecs/reference/manifest.xml
[up-boot]: https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.core/vibevm-docs/v1.0.0/vibevm/vibespecs/model/boot-lane.xml
[up-visibility]: https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.core/vibevm-docs/v1.0.0/vibevm/vibespecs/model/dependency-visibility.xml
[up-compiler]: https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibespecs/modules/vibe-workspace/PROP-035-spec-compiler.xml
[up-lock]: https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.core/vibevm-docs/v1.0.0/vibevm/vibespecs/reference/lock-file.xml
[up-versions]: https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.core/vibevm-docs/v1.0.0/vibevm/vibespecs/model/versions.xml
[up-publish-doc]: https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.core/vibevm-docs/v1.0.0/vibevm/vibespecs/howto/publish-a-package.xml
[up-workspace]: https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.core/vibevm-docs/v1.0.0/vibevm/vibespecs/howto/set-up-a-workspace.xml
[up-private]: https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.core/vibevm-docs/v1.0.0/vibevm/vibespecs/howto/use-a-private-registry.xml
[up-offline]: https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.core/vibevm-docs/v1.0.0/vibevm/vibespecs/howto/work-offline.xml
[up-skills]: https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.core/vibevm-docs/v1.0.0/vibevm/vibespecs/agent/give-your-agent-the-skill.xml#L57-L68
[up-version-parser]: https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-core/src/package_ref.rs
[up-meta]: https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-core/src/manifest/package/meta.rs
[up-publisher]: https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-publish/src/git_publish.rs
[up-boot-code]: https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-workspace/src/boot_artifacts.rs
[up-core-template]: https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-cli/templates/boot-00-core.md
[up-record]: https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-install/src/record.rs
[up-placement]: https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-workspace/src/vibedeps.rs
[up-agent-paths]: https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-agent-projection/src/agents/ambient_paths.rs
[up-skill-meta]: https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-core/src/manifest/package/skill.rs
[up-snapshot]: https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-agent-projection/src/pkgskill/snapshot.rs
[up-redirect]: https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-workspace/src/boot_artifacts/redirect.rs
[up-skill-phase]: https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-orchestrator/src/world/package_skill.rs
[up-deps]: https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-core/src/manifest/package/deps.rs
[up-staging]: https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-workspace/src/publish/staging.rs
[up-fetch]: https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-install/src/plan/fetch.rs
[up-drift]: https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-registry/src/git_package_registry/fetch.rs
[up-plan]: https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-install/src/plan.rs
[up-verify]: https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-install/src/slot_verify.rs
[up-apply]: https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-install/src/apply.rs
