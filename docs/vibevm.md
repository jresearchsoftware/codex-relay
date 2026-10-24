# Pinned governance and first-party Skill consumption

Relay selects Shared Governance **5.0.0** for its project-wide adoption under
Task [#186](https://github.com/jresearchsoftware/codex-relay/issues/186).
Relay **4.0.0** also selects Shared 5.0.0 for its standalone snapshot and
publisher closure evidence. Native Shared compatibility remains **`>=2.5.0`**;
frozen Relay 3.1.0 and earlier packages retain their original bytes.
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
1.0.7, even when a package declares `boot_snippet.link = "dynamic"`. These
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

The [manifest](../vibe.toml) pins Shared `=5.0.0` by its anonymous public Git
source and exact commit. The native local registry supplies Relay `=4.0.0`,
whose supported Shared lower-bound edge resolves to that same explicit Git root.
The root exact selection is project policy; it is not imposed on other consumers
by Relay's lower bound. The schema-7
[lock](../vibe.lock), complete versioned slots, distribution receipt, generated
index and projected Skill belong to the same reviewable source change.

| Identity | Selected value |
| --- | --- |
| Shared accepted producer source | `jresearchsoftware/shared-governance` `d0b3d67ef94a5537ebd4a2bbf4a38e3a6629c0c9` |
| Shared public distribution | `jrs-vibevm/org.jresearch.ai.development-governance` `30a23f467c30c41fec918204cbbf2ecfffd7bef5` |
| Shared annotated tag | `v5.0.0`, tag object `bca9d83e969e6c489fc4474115134c9a8c7b1f24`, peels to the distribution above |
| Complete native distribution tree hash | `sha256:e686314f26c82f32f55958a242481d792e9fcd0d755a6eebf933431f3e0875d9` |
| Relay guidance product-contract baseline | `61bfe2be5bdf5632449cd7f544c6c5ba4d4146d4` |

The producer source and distribution commit are distinct identities. The
receipt's payload hashes and native tree hash use different recipes: the tree
also covers the receipt. Verify the complete file set and all payload bytes
against the accepted producer path `packages/development-governance`; a tag or
`frozen = true` alone proves neither transport identity nor drift refusal.
The enclosing accepted Relay commit identifies its guidance release; the
contract baseline does not claim that the candidate has already been accepted.

Guidance 4.0.0 clarifies the existing manual Step-label procedure and updates
the standalone snapshot; see its
[whole-package classification](relay-guidance.md#version-and-provenance). Guidance 3.1.0
added compatible explicit manual publication to accepted 3.0.0.
The earlier 3.0.0 was a major release because it removes the native
Skill's bundled Shared protocol paths and changes its packaging/routing
contract, independently of Shared version arithmetic. Frozen first-party
1.0.0, 2.0.0, 2.0.1, 3.0.0 and 3.1.0 registry payloads remain intact for historical identity
and rollback; they are not active requirements. The current exporter uses the
selected Shared 5.0.0 root slot. Earlier Shared selections remain in Git history
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

The complete frozen 4.0.0-to-5.0.0 protocol comparison and semantic disposition
are in that assessment: six topics are byte-identical; RA-006 and its TH-002/026
and IR-013 references preserve obligation provenance and explicit dispositions.
TH-029 applies only when a Task includes applying generated client settings.
Neither Task #186's consumer update nor Task #182's Skill release includes live
settings application. The optional bundled Shared ChatGPT projector changes
its receipt/status/update contract, which determines the new Relay package's
major version; native slot/Skill receipts and Relay's own standalone installer
retain their contracts. Task #186's consumer-only update had no package delta.
Task #182 prepares a new package for the existing automatic Shared Publisher
path after independent source acceptance; publication is verified separately.

The [tool pin](../toolchain/vibevm.json) remains VibeVM 1.0.7, source
`b6659978453f50e6d1d4d99626d70b980a2c5847`, Linux x86_64 musl binary SHA-256
`20d111df02eb28040ef4cb766bfcb0bde8ff4427b031f88f33eacb3711c3e240`.
No binary is committed or installed by Relay. Tool alpha/version metadata does
not replace the bounded local content verification.

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

The current standalone exporter and project lock select the same exact Shared
5.0.0 distribution. No retained unselected root slot or expected orphan warning
is needed. Native install prunes obsolete root slots without changing frozen
historical registry payloads. The verifier checks the standalone snapshot's
complete bytes against the accepted distribution and separately verifies native
consumer lock/slot routing. Report any actual native warning and its impact.

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
native maintenance, existing-slot offline reinstall, generated routes and
human-overlay behavior. Supplied source/distribution directories must first be
acquired at the selected immutable identities. These commands describe the
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
