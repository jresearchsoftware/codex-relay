# Pinned governance and first-party Skill consumption

Relay selects Shared Governance **7.0.1** for its project-wide adoption under
Task [#199](https://github.com/jresearchsoftware/codex-relay/issues/199), following the accepted 7.0.0 adoption in Task #213.
Relay **4.2.0** retains Shared 5.0.0 for its standalone snapshot and
publisher closure evidence. Native Shared compatibility remains **`>=2.5.0`**;
frozen Relay 4.1.1 and earlier packages retain their original bytes.
Human-owned [AGENTS](../AGENTS.md) adopts
all nine applicable complete shared topics. The
[ownership mapping](relay-guidance-ownership.md)
identifies their Relay bindings; package installation alone does not adopt
topics for another consumer. Candidate guidance remains proposal data until
independently accepted.

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
                  +--> 90-user.md       local adoption and component routing
```

The Shared boot pointer routes proportional controls, requirement authority,
package versioning, Task handoff, producer self-adoption, GitHub repository
governance, independent review, contract/decision maintenance and context
loading. Read each complete topic when its trigger applies; unrelated work
skips it. Shared meanings have one canonical owner. Native Task/Decision/CR,
admission, Writer/Reviewer publication, exact-result identity and protected
operations remain Relay product mechanisms.

The generated index uses `kind = "static"` for package pointers with VibeVM
1.0.11, even when a package declares `boot_snippet.link = "dynamic"`. These
short pointers perform conditional Markdown routing; no executable resolver
runs during startup. A client entering through CLAUDE/GEMINI follows
[00-core](../vibevm/vibespecs/boot/00-core.md) to human AGENTS once, without a
managed-block traversal loop. The authored
[user route](../vibevm/vibespecs/boot/90-user.md) supplies local bindings.

Ordinary manual Codex and automatic workers read committed plain files offline.
No VibeVM binary, registry, cache, network or new owner command is required.
The [native first-party route](self-adoption.md) supplies the same Relay product
contract as the standalone export. Native `references/shared-protocols.md` routes
to the reviewed consumer lock and its selected Shared slot; standalone carries
its own immutable attributed snapshot. Complete Skill trees need not match.
File-route checks prove reachability and content,
not actual model traversal or compliance.

## Selected immutable identities

The [manifest](../vibe.toml) pins Shared `=7.0.1` by its anonymous public Git
source and exact commit. The native local registry supplies Relay `=4.2.0`,
whose supported Shared lower-bound edge resolves to that same explicit Git root.
The root exact selection is project policy; it is not imposed on other consumers
by Relay's lower bound. The schema-7
[lock](../vibe.lock), complete versioned slots, distribution receipt, generated
index and projected Skill belong to the same reviewable source change.

| Identity | Selected value |
| --- | --- |
| Shared accepted producer source | `jresearchsoftware/shared-governance` `1110f10b996c2f81fa842e6339ab6d7c13111cd7` |
| Shared public distribution | `jrs-vibevm/org.jresearch.ai.development-governance` `f9fcfa03dec8fb9e00398fc7e0cc7de92da687b9` |
| Shared annotated tag | `v7.0.1`, tag object `dddb250d5eb133347f0b1712740a96be7a1d823b`, peels to the distribution above |
| Complete native distribution tree hash | `sha256:9dc1463bb4c130282e5ac332e0d7f4c18502d950b85e2015d04d5b9634589c3f` |
| Relay guidance product-contract baseline | `61bfe2be5bdf5632449cd7f544c6c5ba4d4146d4` |

The producer source and distribution commit are distinct identities. The
receipt's payload hashes and native tree hash use different recipes: the tree
also covers the receipt. Verify the complete file set and all payload bytes
against the accepted producer path `packages/development-governance`; a tag or
`frozen = true` alone proves neither transport identity nor drift refusal.
The enclosing accepted Relay commit identifies its guidance release; the
contract baseline does not claim that the candidate has already been accepted.

Guidance 4.2.0 adds the bounded owner continuation command and compatible
execution/lifecycle simplification, independently of the Shared 7.0.1 patch.
Guidance 4.1.1 was a PATCH clarification of existing automatic Writer Draft
preparation before remediation, with no new owner operation or runtime route.
Accepted 4.1.0 added compatible ordinary Git-pair installer guidance and retained
expert/other-consumer paths; neither version establishes private PROD activation. Guidance 4.0.0 clarifies the existing manual Step-label procedure and updates
the standalone snapshot; see its
[whole-package classification](relay-guidance.md#version-and-provenance). Guidance 3.1.0
added compatible explicit manual publication to accepted 3.0.0.
The earlier 3.0.0 was a major release because it removes the native
Skill's bundled Shared protocol paths and changes its packaging/routing
contract, independently of Shared version arithmetic. Frozen first-party
1.0.0, 2.0.0, 2.0.1, 3.0.0, 3.1.0, 4.0.0 and 4.1.0 registry payloads remain intact for historical identity
and rollback; they are not active requirements. The frozen product exporter uses its
own Shared 5.0.0 release-evidence slot through the repository build adapter. Earlier Shared selections remain in Git history
and frozen historical Relay packages. Project version `0.0.0`
does not identify a Relay release.

Another consumer can deliberately select a compatible Shared version
with its own exact source root and reviewed lock. Assess changes to used
protocol semantics, applicability, exceptions and Relay bindings on intentional
updates. Compatible or irrelevant updates need no new Relay version or unrelated
producer release gate; material Relay behavior/interface/packaging changes do.
See the [compatibility assessment](relay-skill-compatibility.md). Native execution
reads locked committed files without resolving `latest`; an open-ended lower
bound does not guarantee arbitrary future compatibility.

The [7.0.0-to-7.0.1 assessment](relay-skill-compatibility.md#project-update-from-700-to-701)
records the actual TH-010/013/026 clarification and unchanged authority boundaries.
The complete [5.0.0-through-7.0.0 semantic assessment](relay-skill-compatibility.md#project-migration-from-500-through-700)
distinguishes current project policy, conditional settings duties, unselected
Small Improvements and the [bounded legacy runtime closure binding](relay-guidance-ownership.md#temporary-legacy-closure-binding).
The earlier 4.0.0-to-5.0.0 assessment remains historical product evidence.
The root update does not change the standalone snapshot, release-evidence lock,
Skill requirement, package bytes or installed runtime identity.

The [tool pin](../toolchain/vibevm.json) selects exact VibeVM **1.0.11**, lightweight
Git tag `v1.0.11`, source `5e470926ad0f34d61e37d387ce4b7c153356a804`.
The actual Linux x86_64 musl bootstrap binary SHA-256 is
`5fe5b3efeb2eab7c7c49a8dc864864ffacac08a9d7be3dc9df0bc0bb15a8bd58`.
Its upstream `DISTRIBUTIONS.json` SHA-256 is
`a11b0812d6ee675eeb58166a066500f5c1bf02705608d1de6725e087e9d713e6`;
manifest `source_commit`, bootstrap component digest, Git tag and actual
`vibe 1.0.11` output agree. Release assets are mutable upstream, so the exact
digest remains required. No binary is committed or installed by Relay.

Public CI uses [the credential-free download helper](../scripts/download-vibevm.py)
with three attempts per endpoint and a 30-second request timeout for transient
HTTP/transport failures. If the pinned browser download remains unavailable,
it uses reviewed release asset ID `704909893` through GitHub's anonymous API,
avoiding the separately observed tag-metadata HTTP 504. The asset ID was verified
against the exact 1.0.11 release, browser URL and digest. Pins without an asset ID
still resolve the exact tag and asset; no moving release or alternate host is used.
Both routes must match the unchanged pinned SHA-256 before writing an executable;
missing assets, permanent HTTP failures and digest mismatches fail validation.

For 1.0.7 → 1.0.11, the used install/reinstall/validate/check/Skill commands and
schema-7 lock/slot/boot layout remain compatible. 1.0.8 changes application
installer/launcher/index contracts and adds optional `required_by`; this passive
flow/Skill graph has no application packages or old user-application state to
migrate. Unrelated app features remain unused. 1.0.9's JSON-versus-human output
change requires selecting `--json` explicitly; probes already do. 1.0.10 adds
remote lock/slot hash rejection and refuses forced same-version drift; probes
now expect the remote hash error. 1.0.11 repairs GitHub/GitVerse Git-source cloning
regressed in 1.0.9/10; the anonymous pinned GitHub acquisition exercises that
path. Boot and Linux tree-hash recipes match the old source. Optional remap and
reverse-dependency lock fields are absent for this graph; no unrelated capability
is adopted. Native updating an existing lock preserves its historical
`generated_by = "vibe 1.0.7"` header; clean 1.0.11 generation records 1.0.11.
That retained header is not actual executable-version proof. Historical product
closure locks and shipped tool references remain frozen independently.

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

The standalone exporter retains Shared 5.0.0 while the project lock selects 7.0.1.
The repository-only `build-project-guidance.py` adapter provides frozen build
inputs to the unchanged product builder in disposable storage. It must reproduce
the same product bytes and provenance. No unselected root 5.0.0 slot or orphan
warning is required: native install prunes it without changing frozen registry
payloads. The verifier separately checks both complete immutable dependencies
and active consumer routing. Neither build input nor nested release evidence is
a runtime/policy fallback. Report actual native warnings and their impact.

Task #199 retains the exact accepted 7.0.0 slot at its original path as inactive
history. It is absent from the root lock and generated boot; native readers must
use selected 7.0.1. The verifier accepts only those exact historical bytes when
present and rejects a missing selected slot. Native `install` prunes inactive
slots in disposable copies; preserving this source evidence does not require
rewriting native output or making the historical slot a fallback. Preserve the
committed historical slot when importing deliberate maintenance outputs. Native
`check` may report this retained slot as orphaned; that warning describes inactive
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
Repeat install may refresh the native lock's `generated_at`; qualification allows
only that valid timestamp change and requires an identical resolved graph, source
locations, content hashes and materialized slots.
Local registry URLs are absolute native location metadata. Before checking a
relocated fixture, the probe re-resolves the relative registry through native
installation; it requires unchanged content hashes, dependency graph, source
revision, slots, routes and Skill bytes, allowing only the local source URL and
lock generation timestamp to change. The missing-origin warning must appear
before this repair and disappear afterward. See the
[maintenance binding](self-adoption.md#deliberate-source-maintenance). Supplied
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

The verifier compares the exact graph, lock/tree identities, complete Shared
slot/receipt, standalone snapshot, first-party export/registry/slot/Skill
equality and generated route.
Missing or corrupt files, counterfeit identities, graph changes and malformed
managed markers require diagnosis. Restore ordinary missing outputs from the
accepted Git revision; do not force generation over human text or introduce a
session-time resolver. Upstream `vibe check` alone does not establish these local
content and reachability invariants.

Committed ready files support offline reads and bounded existing-slot
reinstall. Cold offline acquisition of a remote dependency without a slot/cache
is not promised. Normal startup never resolves or upgrades packages.

Rollback restores the previous accepted manifest, lock, slot, authored routing,
first-party registry and projected Skill as one reviewed Git change. Frozen
previous registry versions, including 2.0.1, are preserved. Restore the
corresponding accepted local
bindings as well as package files; `vibe clean` alone is not policy rollback.
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
