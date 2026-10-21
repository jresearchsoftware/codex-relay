# Pinned governance and first-party Skill consumption

Task [#166](https://github.com/jresearchsoftware/codex-relay/issues/166) selects
Shared Governance **4.0.0** and first-party Relay guidance **2.0.0** as one
consumer migration candidate. Human-owned [AGENTS](../AGENTS.md) adopts all nine
applicable complete shared topics. The
[ownership mapping](relay-guidance-ownership.md) identifies their Relay bindings;
package installation alone does not adopt topics for another consumer.
Candidate guidance remains proposal data until independently accepted.

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
The [native first-party route](self-adoption.md) supplies the same product Skill
as the standalone export. File-route checks prove reachability and content,
not actual model traversal or compliance.

## Selected immutable identities

The [manifest](../vibe.toml) pins Shared `=4.0.0` by its anonymous public Git
source and exact commit. The native local registry supplies Relay `=2.0.0`,
whose shared edge resolves to that same explicit Git root. The schema-7
[lock](../vibe.lock), complete versioned slots, distribution receipt, generated
index and projected Skill belong to the same reviewable source change.

| Identity | Selected value |
| --- | --- |
| Shared accepted producer source | `jresearchsoftware/shared-governance` `99034dd708e5d0201060986b561ada4d2cffd453` |
| Shared public distribution | `jrs-vibevm/org.jresearch.ai.development-governance` `f14da40725cd35fb3117ae84a506256505340787` |
| Complete native distribution tree hash | `sha256:d27a004b5f2dcc8ae0f7fd33289d97be1eab84ddbdf54d7e880cc6def7ad3746` |
| Relay guidance product-contract baseline | `61bfe2be5bdf5632449cd7f544c6c5ba4d4146d4` |

The producer source and distribution commit are distinct identities. The
receipt's payload hashes and native tree hash use different recipes: the tree
also covers the receipt. Verify the complete file set and all payload bytes
against the accepted producer path `packages/development-governance`; a tag or
`frozen = true` alone proves neither transport identity nor drift refusal.
The enclosing accepted Relay commit identifies its guidance release; the
contract baseline does not claim that the candidate has already been accepted.

Guidance 2.0.0 is a major source candidate because adopting the complete shared
contract changes guidance semantics. The frozen first-party 1.0.0 registry
payload remains intact for historical identity and rollback; it is not the
active requirement. Historical Shared versions remain in Git history, not
parallel active slots. Project version `0.0.0` does not identify a Relay release.

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
slot/receipt, first-party export/registry/slot/Skill equality and generated route.
Missing or corrupt files, counterfeit identities, graph changes and malformed
managed markers require diagnosis. Restore ordinary missing outputs from the
accepted Git revision; do not force generation over human text or introduce a
session-time resolver. Upstream `vibe check` alone does not establish these local
content and reachability invariants.

Committed ready files support offline reads and bounded existing-slot
reinstall. Cold offline acquisition of a remote dependency without a slot/cache
is not promised. Normal startup never resolves or upgrades packages.

Rollback restores the previous accepted manifest, lock, slot, authored routing,
first-party registry and projected Skill as one reviewed Git change. The frozen
1.0.0 registry bytes are preserved. Restore the corresponding accepted local
bindings as well as package files; `vibe clean` alone is not policy rollback.
Preserve human overlays and unrelated work. This maintenance path performs no
external publication, service deployment, client-settings change or protected
consumer operation.
