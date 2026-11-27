# Pinned development guidance and first-party Skill consumption

Relay selects Shared Governance **12.5.0** for project-wide adoption under
[Task #295](https://github.com/jresearchsoftware/codex-relay/issues/295).
Human-owned [AGENTS](../AGENTS.md) adopts all eleven complete topics and the
[ownership mapping](relay-guidance-ownership.md) retains native actors, trust
boundaries, local-only SI adoption and the qualified legacy transition.
Relay **11.1.0** has a native floor of **`>=12.1.0`** and carries exact 12.1.0
standalone and publisher evidence. The
[compatibility assessment](relay-skill-compatibility.md#task-295-shared-1210-through-1250)
explains this development dependency update. Candidate guidance remains
proposal data until independently accepted.

## Native route and conditional reading

```text
AGENTS.md                         human adoption and Relay-specific bindings
CLAUDE.md / GEMINI.md              native managed routes
                  |
                  v
vibevm/vibespecs/boot/INDEX.md      native generated index
                  |
                  +--> 00-core.md       Relay authority boundary
                  +--> Shared boot      complete relevant protocols, on demand
                  +--> Relay boot       product Skill, on relevant work
                  +--> Landscape model  recommendation/evidence, on selection work
                  +--> Landscape agents adopted policy, on permitted substantial work
                  +--> 90-user.md       local adoption and component routing
```

The Shared boot pointer routes proportional controls, requirement authority,
package versioning, Task handoff, producer self-adoption, GitHub repository
governance, independent review, contract/decision maintenance, context
loading, Small Improvements and human command interaction. Read each complete topic when its trigger applies; unrelated work
skips it. Shared meanings have one canonical owner. Native Task/Decision/CR,
admission, Writer/Reviewer publication, exact-result identity and protected
operations remain Relay product mechanisms.

VibeVM 1.0.12 emits `kind = "static"` for these short package pointers,
including packages that declare `boot_snippet.link = "dynamic"`. The pointers
route full-policy reading conditionally. Each root entrypoint preserves the
authored project-only scope over the generated optional personal, override and
memory routes, lane receipts and quiet clause. CLAUDE/GEMINI follow
[00-core](../vibevm/vibespecs/boot/00-core.md) to human AGENTS once. The authored
[user boot file](../vibevm/vibespecs/boot/90-user.md) carries product boundaries
and validation/handoff rules alongside local routing, keeping required policy
readable within the default Codex root instruction budget.

Ordinary manual Codex and automatic workers read committed plain files offline.
No VibeVM binary, registry, cache, network or new owner command is required.
The [native first-party route](self-adoption.md) supplies the same Relay product
contract as the standalone export. Native `references/shared-protocols.md` routes
to the reviewed consumer lock and its selected Shared slot; standalone carries
its own immutable attributed snapshot. Complete Skill trees need not match.
File-route checks prove reachability and content,
not actual model traversal or compliance.

## Landscape flows and local adoption

Root [AGENTS](../AGENTS.md#shared-subagent-workflow) explicitly adopts the passive
`org.jresearch.ai/landscape-subagents@1.1.0` flow for Relay's own development.
Its [complete installed policy](../vibevm/vibedeps/org.jresearch.ai.landscape-subagents/1.1.0/vibevm/vibespecs/protocols/subagents.md)
replaces the reusable text formerly maintained in `docs/codex/SUBAGENTS.md`.
That [local binding](codex/SUBAGENTS.md) now records the semantic migration and
only Relay-specific authority. Useful proactive delegation remains recommended
at every supported parent effort, with no helper quota or Ultra requirement.
The November 17 revision updates the advisory child matrix and retains the
criteria for useful parallel work, reassessment and zero-helper cases. The
existing permission, override and review boundaries continue to govern.

Native INDEX includes both short package boot pointers as `static`; conditional
Markdown reading supplies the relevant detail, not an executable loader:

| Work | Detail to read |
| --- | --- |
| Unrelated session or Subagents Off/prohibited | Short boot pointers only; skip delegation policy and detailed model evidence |
| Substantial Relay work, Subagents On, Task/runtime permit delegation | Complete adopted subagent policy before substantial work; setup/runtime notes only when assessing adoption/client support |
| Task model/effort recommendation or evidence assessment | [Selection guidance](../vibevm/vibedeps/org.jresearch.ai.landscape-model-guidance/1.1.0/vibevm/vibespecs/protocols/model-selection.md), then [dated evidence](../vibevm/vibedeps/org.jresearch.ai.landscape-model-guidance/1.1.0/vibevm/vibespecs/reference/evidence.md) when the factual basis matters |

The [task authoring route](task-workflow.md#relay-development-model-recommendations)
and root model reference make `landscape-model-guidance@1.1.0` available as
recommendation/evidence reading. This does not adopt new recommendations or change
`gpt-6.1-sol / xhigh / Subagents On`, explicit Task/CR profiles, allowlists,
consumer configuration or runtime selection. Actual policy/default changes need
distinct explicit owner authority. Neither package is a ChatGPT Skill, client
configuration, autonomous model router or service. Installation/presence alone
never activates delegation or reselects an admitted parent or child. Relay keeps
immutable admission, GitHub authority and owner/worker/Writer/Reviewer separation.

Both flows use an exact root constraint (`=1.1.0`),
with anonymous public Git sources pinned to the commits below. This is a reviewed
snapshot/reproducibility choice under PV-014, not evidence that earlier versions
are functionally incompatible or a promise about future releases. Both are frozen,
MIT-licensed flows with empty dependency closures. Their `publish = false`
producer manifests disable automatic enumeration; they do not invalidate the
explicit published annotated tags. Native VibeVM installed the full payloads,
including public `DISTRIBUTION.json` receipts and `.vibe-slot.toml` metadata.

| Published identity | Exact value |
| --- | --- |
| Model distribution repository | `jrs-vibevm/org.jresearch.ai.landscape-model-guidance` |
| Model `v1.1.0` annotated tag object | `230ed86a504fee3bac065958dc2e3ee18aefd1cf` |
| Model peeled distribution commit / root `rev` | `a810317f87fb4378be19edb04506444553f60148` |
| Model complete native tree hash | `sha256:f7245df4142fe6d9651f1050edc493dfe0b7078e0075211e7190440ff04cbd5d` |
| Subagents distribution repository | `jrs-vibevm/org.jresearch.ai.landscape-subagents` |
| Subagents `v1.1.0` annotated tag object | `9b3cd32fd2f710851740bdf806f3837388ee0663` |
| Subagents peeled distribution commit / root `rev` | `b3e9da5a10af2b258699e7d1667dc925d247ae8d` |
| Subagents complete native tree hash | `sha256:4ea4a61964e63d2fc91a6aa2ae486e6edc8231823266f6feefb83de6b615f1ae` |

The producer is `jresearchsoftware/codex-model-landscape`. The published
[model contract](../vibevm/vibedeps/org.jresearch.ai.landscape-model-guidance/1.1.0/README.md)
and [subagent contract](../vibevm/vibedeps/org.jresearch.ai.landscape-subagents/1.1.0/README.md)
are frozen distribution contracts. Their receipts intentionally declare
`disclosure = "opaque"`: payload hashes are public, exact private accepted-source
identities and source-equivalence machinery remain producer-only. Distribution
inspection must not be described as an independent comparison with that private
source. No private provenance or upstream publication authority is inferred.
The November 17 advisory profiles use `gpt-6.2-sol / medium` as a starting point
for new ordinary and complex work, with targeted escalation and a consumer-selected
`gpt-6.1-sol / medium` fallback for new work without 6.2 access. The model flow
cites public evidence checked November 22, 2026. Subagent runtime context retains
its October 9 source-inspection baseline. Source/routing checks leave actual
client traversal, child profiles, access and usefulness unverified.

### Deliverable, updates and rollback

Under PV-015/018 the accepted Landscape and project-only Small Improvements
integration stays outside the product's standalone snapshot and release-evidence
closure. That historical integration changed no product requirement or payload.
Task 194 separately changed the Relay product and prepared accepted 7.0.0;
Task 266 prepared accepted 8.0.0 from that baseline. Task 244 prepared 9.0.0; Task 273 prepares 10.0.0. Current source work publishes neither
Landscape nor Relay and authorizes no installed Apply.

During candidate development, freeze independently accepted source guidance via
the admitted Task binding before reading candidate AGENTS/INDEX/package routes.
Their presence cannot self-accept or alter the admitted worker/profile (SA-002/003).
After independent acceptance/integration, a clean checkout reads the committed
selected files offline; no ordinary-startup install is required.

For an intentional update, review the new published contract, semantic changes,
license, source identity and retained local bindings, then use the pinned native
maintenance command below. Review manifest, lock, complete slots/receipts, INDEX
and authored adoption routes together. Do not edit frozen slots or resolve moving
`main` at runtime. Reuse the existing structural/native/candidate qualification;
no extra ledger, recurring client probe or release gate is introduced. Restore
all those accepted files and local adoption bindings together through Git for
rollback. Restoring a package alone or running `vibe clean` does not roll back
policy; preserve overlays and unrelated work. Missing selected files require
repair from accepted Git, never fallback to the removed copy or a different slot.

## Selected immutable identities

The [manifest](../vibe.toml) pins Shared `=12.5.0` by anonymous public Git
source and exact commit. The local registry supplies Relay `=11.1.0`, whose
`>=12.1.0` edge resolves to that explicit root. The exact root selection is
project policy. The schema-7 [lock](../vibe.lock), complete slots, receipt,
boot index and projected Skill belong to the same reviewed source change.

| Identity | Selected value |
| --- | --- |
| Shared accepted producer source | `jresearchsoftware/shared-governance` `f51fd0ab22ff61fab48bd1e5af96918d77af1ec6` |
| Shared public distribution | `jrs-vibevm/org.jresearch.ai.development-governance` `e19ceeaa3ffe608fe078d37171ddd7cd5a940dda` |
| Shared annotated tag | `v12.5.0`, tag object `8e66c0af8179ce0c2ceb7479642e6718ed97208b`, peels to that distribution |
| Complete native distribution tree hash | `sha256:57792a91e04ccf0e40e22e8778e10304d93a408f23376ae5627b23df2bfd9258` |
| Relay guidance contract source | `source-tree`, actual input hashes in provenance, accepted baseline `275892d8c79469974259e48583ca1bd60f881970` |

The public receipt's payload digest and native tree hash use different recipes.
The native tree also covers the receipt. Verify the complete file set and all
payload bytes against the accepted producer path
`packages/development-governance`. The enclosing accepted Relay commit identifies
its guidance release. Frozen versioned registry payloads through 11.0.1 and the
historical Git revision preserve reproducible rollback. The project version
`0.0.0` identifies the VibeVM consumer, while the release package has its own
version.

Another consumer can deliberately select a compatible Shared version
with its own exact source root and reviewed lock. Assess changes to used
protocol semantics, applicability, exceptions and Relay bindings on intentional
updates. Compatible or irrelevant updates need no new Relay version or unrelated
producer release gate; material Relay behavior/interface/packaging changes do.
See the [compatibility assessment](relay-skill-compatibility.md). Native execution
reads locked committed files without resolving `latest`; an open-ended lower
bound does not guarantee arbitrary future compatibility.

The historical assessments in [compatibility](relay-skill-compatibility.md)
retain earlier migration evidence. Task 273 changes the product snapshot,
release-evidence lock, requirement and payload as well as root project policy. Accepted source, external publication and installed runtime qualification
remain separate.

The [development tool pin](../toolchain/vibevm-development.json) selects
VibeVM **1.0.12**. It records the tag's resolved source, mutable release ID,
distribution manifest and Linux x86_64 musl bootstrap asset. At adoption the
Git tag, verified manifest, platform bootstrap/component digests, release API
and actual binary agreed. This Linux bootstrap is the artifact used in Relay
development CI. The [existing product pin](../toolchain/vibevm.json) remains a
builder input and identifies the separately qualified VPM tool.
Keeping the development pin separate preserves the product provenance and
delivery bytes.

Public CI uses [the credential-free download helper](../scripts/download-vibevm.py).
It uses bounded retries for transient transport errors and falls back to the
pinned public asset ID when the browser download is unavailable. It checks the
exact digest before writing an executable. The distribution manifest anchors
the selected asset at deliberate adoption. Routine CI uses the pinned digest.

The root graph remains in lock schema 7 and the passive flows remain at epoch 1.
Native generation now records exact requirements on all four root edges and
`resolved_commit` for each Git package. The first-party development slot
preserves the frozen export's 12.1.0 publisher evidence. Its native Skill
follows the consumer's selected Shared slot. Native Skill content and the
portable Skill receipt stay the same.
The new tool migrates the portable seed to ignored schema-4 project activation
state when explicitly projecting the Skill. Keep the portable seed in Git.

The selected manifests use no `[hooks]` and Relay's qualification readers use
status and their actual report fields, so removal of the lifecycle JSON
`hooks` member needs no adapter. The tool also normalizes VibeVM-owned Git data
checkouts independently of user EOL settings. The selected LF bytes were
compared with native Linux acquisition. Windows and macOS were outside this
local qualification. Shared Governance's independent implementation report
supplies upstream context for the lock format, router, Skill migration, hooks
and Git normalization. [Shared Governance Task 139 qualification](https://github.com/jresearchsoftware/shared-governance/blob/b102245bcd99e8f20c8f3cce9487705c3fbe19cf/docs/task-139/step-1/README.md)

## Admitted maintenance and qualification

For an authorized update, acquire and hash-check the pinned tool and exact
producer/distribution revisions in disposable storage. Install in a disposable
consumer copy with isolated HOME/settings/cache and no inherited credentials:

```sh
/absolute/disposable/path/vibe --json install --no-default-registry --assume-yes
```

Native VibeVM generates the lock, slots, metadata and index; do not hand-edit
those outputs. Review them together with the manifest, authored routes and
native Skill, preserving human overlays. The file-specific
[Git attribute](../.gitattributes) preserves the index serializer's blank EOF
line. Ignored `.vibe/` state and the persistent boot transaction lock are not
runtime authority. Follow [self-adoption](self-adoption.md) for the first-party
export and projection commands.

The standalone exporter selects exact Shared 12.1.0. The project lock selects 12.5.0.
The single `build-relay-guidance.py` builder reads the immutable release closure
directly through the existing builder, preserving its source-tree input-hash
provenance mechanism. No unselected root 5.0.0 slot is needed; frozen accepted
registry payloads remain unchanged.
The verifier separately checks both complete immutable dependencies
and active consumer routing. Neither build input nor nested release evidence is
a runtime/policy fallback. Report actual native warnings and their impact.

Task #199 retains the exact accepted 7.0.0 slot, and Task #194 retains the
previous 7.0.1 slot, at their original paths as inactive history. They are absent from the root lock and generated boot;
native readers must
use selected 12.5.0. The verifier accepts only those exact historical bytes when
present and rejects a missing selected slot. Native `install` prunes inactive
slots in disposable copies; preserving this source evidence does not require
rewriting native output or making the historical slot a fallback. Preserve the
committed historical slot when importing deliberate maintenance outputs. Native
`check` may report these retained slots as orphaned; that warning describes inactive
evidence, not a second selected dependency. Do not suppress unrelated warnings.

Stage intended additions before structural qualification:

```sh
python3 scripts/qualify-vibevm.py
python3 scripts/qualify-vibevm.py --vibe /absolute/disposable/path/vibe \
  --source-dir /disposable/accepted-source/packages/development-governance \
  --distribution-dir /disposable/public-distribution
python3 scripts/test-qualify-vibevm.py
```

Structural mode reads committed inputs without a network or VibeVM. Optional
tool mode rechecks the binary digest and uses isolated projects to exercise
native clean/repeat install, relocation with the original source absent,
existing-slot offline reinstall, generated routes and human-overlay behavior.
Repeat install preserves the resolved graph, source locations, content hashes and
materialized slots. A relocated fixture exercises offline reinstall from retained
slots and then a fresh native solve for maintenance. Lock comparisons permit
generation timestamp and local location metadata changes where applicable. The
probe also exercises migration and repeat projection of the portable Skill seed.
See the [maintenance binding](self-adoption.md#deliberate-source-maintenance). Supplied
source/distribution directories must first be acquired at the selected immutable
identities. These commands describe the
qualification contract; actual candidate results and warnings belong in its
PR, native checks and Outcome. They do not qualify a model or Relay installation.
Use the existing complete candidate checks rather than new per-topic rituals.

Run mode/symlink probes on a Linux filesystem. Windows-mounted files can expose
executable bits through projection; copy Git bytes and modes into isolated
Linux storage instead of weakening passive-payload checks. The historical
[routing comparison](../scripts/qualify-vibevm-routing.py) and
[earlier adoption assessment](vibevm-adoption-assessment.md) remain bounded
historical evidence, not proof for this new candidate.

## Drift, missing files and rollback

The verifier compares the exact four-package graph, lock/tree identities, complete
Shared and Landscape slots/receipts, the standalone snapshot, export/registry
equality, the first-party native slot and projected Skill, local adoption
boundaries and generated routing.
Restore missing authored entrypoint bytes from the accepted Git revision. Native
reinstall can restore the generated router and INDEX. A refused marker collision
can leave native boot transaction files. After restoring the intended authored
entrypoint, native reinstall completes recovery and clears them. Upstream
`vibe check` alone does not establish Relay's content and reachability invariants.

Committed ready files support offline reads and bounded existing-slot
reinstall. Cold offline acquisition of a remote dependency without a slot/cache
is not promised. Normal startup never resolves or upgrades packages.

Rollback restores the previous accepted manifest, lock, slot, authored routing,
first-party registry and projected Skill as one reviewed Git change. Frozen
previous registry versions, including 2.0.1, are preserved. Restore the
corresponding accepted local bindings and complete generated Instructions
along with those files. Follow the client Settings handoff for
any effective text change. `vibe clean` alone is not policy rollback.
Preserve human overlays and unrelated work. This maintenance path performs no
external publication, service deployment, client-settings change or protected
consumer operation.

## ChatGPT Project consumer

Relay's [ChatGPT consumer binding](../chatgpt/README.md) reuses the selected
Shared Governance generator for human-owned custom text and complete desired
Instructions, with optional Sources. It consumes accepted committed native
closure; it does not run a second resolver or change live Project settings.
Review generated diffs with source changes, then perform owner-controlled live
reconciliation after acceptance/integration where required. Codex native boot
and the versioned Relay product bundle retain their existing owners.
