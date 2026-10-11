# Pinned passive governance consumer

Task [#97](https://github.com/jresearchsoftware/codex-relay/issues/97), Step 3,
adopts the proportional-controls and relevant requirement-authority topics from
`org.jresearch.ai/development-governance` 1.1.0. The
[semantic comparison](vibevm-adoption-assessment.md) explains the transfer and
its limits. The full Relay material contract-change gate, Task/Step/CR authority,
Writer/Reviewer separation, warning review and protected boundaries stay local.
Package-versioning is bundled but **not adopted** as Relay policy. Independent
exact-head acceptance, merge and Issue closure remain separate; #97 stays open.

Ordinary manual Codex and automatic Relay workers read committed plain files.
They need no VibeVM binary, network, registry, cache, resolution or new owner
command. Worker prompts, optional hooks and client instruction precedence are
unchanged. This is an ordinary passive flow, with no native Skill projection,
WAL, executable capability, stock specification precedence or new boot hierarchy.

## Route and semantic ownership

```text
AGENTS.md                         human Relay authority + unchanged managed block
CLAUDE.md / GEMINI.md              unchanged native managed blocks
                  |
                  v
vibevm/vibespecs/boot/INDEX.md      native generated file
                  |
                  +--> 00-core.md          unchanged Relay authority boundary
                  +--> installed package boot pointer
                  |       +--> proportional-controls     when relevant
                  |       +--> requirement-authority     when relevant
                  |       +--> package-versioning        unadopted; skip
                  +--> 90-user.md          local routing/adoption bindings
```

The package pointer is a short unconditional INDEX entry; the full protocols
are conditional Markdown reads. VibeVM 1.0.7 emits `kind = "static"` for this
pointer even though the package declares `boot_snippet.link = "dynamic"`.
Neither that declaration nor conditional reading selectively installs clauses.
Unrelated tasks skip the full protocols. No STATIC lane is generated.

Root [AGENTS](../AGENTS.md) explicitly adopts the two relevant topics and links
directly to their slot files for JIT access. Its existing
[Relay policy anchor](execution-policy.md#proportional-controls-and-operator-usability)
now holds only routing and product bindings, replacing the proven portable
control duplicate. The shared existing-proof rule replaces the corresponding
minimum-ceremony duplicate; Relay's native evidence/check/Outcome cadence stays
local. The [Step 2 report](vibevm-semantic-coverage.md) is historical assessment,
not another active policy. G1 remains fully operative in AGENTS.

Codex already reads root AGENTS. A client entering through CLAUDE/GEMINI follows
[00-core](../vibevm/vibespecs/boot/00-core.md) to apply human AGENTS policy once,
without traversing the managed block again. The
[user input](../vibevm/vibespecs/boot/90-user.md) selects the adopted topics and
local bindings. All human text outside the narrowly reviewed AGENTS changes,
all three managed blocks, core and unrelated local overlays are preserved.
File-route checks do not prove actual model traversal or compliance.

## Reviewed identity

The [manifest](../vibe.toml) declares exact `=1.1.0`, the public distribution Git
URL and full immutable revision, with anonymous authentication. There is one
root dependency and no transitive dependency. The schema-7 [lock](../vibe.lock),
complete [slot](../vibevm/vibedeps/org.jresearch.ai.development-governance/1.1.0/README.md),
[DISTRIBUTION receipt](../vibevm/vibedeps/org.jresearch.ai.development-governance/1.1.0/DISTRIBUTION.json)
and native slot inventory are committed together. Project version `0.0.0` is
not a Relay release.

| Identity | Accepted value |
| --- | --- |
| Producer source | `jresearchsoftware/shared-governance` `129d452ddfa6b9ac1030ccc7803994793467ab2d` |
| Public distribution | `jrs-vibevm/org.jresearch.ai.development-governance` `fa901b9e866ea0246b99bf9025ca00a0ca20267c` |
| Observed annotated `v1.1.0` object | `f33ffaf4f8a95faeea24f5acf4a37ef9c9f0ece9`, peeling to that distribution commit |
| Receipt payload SHA-256 | `4393a4e44c20a33a4b8c26437de77467e162ebd2ae74922ea56c9c83dc29173d` |
| VibeVM complete distribution tree hash | `sha256:1bac72e869c1766d794a108f9c876d680d83844a7a29ed40bab3be1ce3a869bd` |

The receipt hashes seven payload files, while the native tree hash also includes
the receipt. They use different recipes and must not be conflated. Anonymous
full-revision acquisition confirmed every payload byte against the accepted
producer path `packages/development-governance`, the complete distribution file
set and receipt hashes before consumer deletion. The annotated tag is unsigned;
its observed object identity is not signature proof or a guarantee against
future tag mutation. The manifest pins the commit, not the tag alone.

The unchanged [tool pin](../toolchain/vibevm.json) is VibeVM 1.0.7, source
`b6659978453f50e6d1d4d99626d70b980a2c5847`, Linux x86_64 musl binary SHA-256
`20d111df02eb28040ef4cb766bfcb0bde8ff4427b031f88f33eacb3711c3e240`.
No binary is committed or installed by Relay. Upstream is alpha and allows
breaking changes; version/tag metadata and `frozen = true` do not by themselves
prove immutable transport or drift rejection.

## Deliberate maintenance and qualification

Normal startup never runs these commands. For an admitted update, obtain and
hash-check the pinned binary and accepted producer/public bytes in disposable
storage, author the exact requirement under local authority, and install in a
disposable copy of the consumer with isolated HOME/settings/cache and no
inherited credentials:

```sh
/absolute/disposable/path/vibe --json install --no-default-registry --assume-yes
```

Review and copy the manifest, lock, entire slot/receipt and generated INDEX as
one ordinary source change, preserving managed-block human overlays and authored
core/user semantics. Do not hand-edit generated INDEX or slot metadata. The
existing file-specific [Git attribute](../.gitattributes) preserves the native
INDEX serializer's blank EOF line. Local `.vibe/` state and the persistent boot
transaction lock remain ignored, outside normal execution truth.

Stage intended additions, then use the opt-in
[consumer qualification script](../scripts/qualify-vibevm.py):

```sh
python3 scripts/qualify-vibevm.py
python3 scripts/qualify-vibevm.py --vibe /absolute/disposable/path/vibe \
  --source-dir /disposable/accepted-source/packages/development-governance \
  --distribution-dir /disposable/public-distribution
python3 scripts/test-qualify-vibevm.py
```

Structural mode reads files without VibeVM or a network. Tool mode rechecks the
binary digest and probes disposable isolated projects, including repeated
offline reinstall of the committed slot. Supplied directories are compared to
committed identities; callers must first acquire them at the accepted immutable
revisions. The script does not download, deploy, invoke a model or become a new
runtime/owner gate. Full Relay candidate checks remain the existing AGENTS set.
The optional standard-library tests exercise missing/corrupt bytes, counterfeit
collocated identities, paths/modes, graph changes and managed-block collisions.
Exact native managed-block and admitted core digests are bounded qualification
expectations. An authorized tool/core change updates those expectations in the
same reviewed source proposal; human overlays and authored user input stay free.
The historical [routing comparison script](../scripts/qualify-vibevm-routing.py)
remains a separate stock/synthetic experiment, not package-consumer proof.

Linux probes passed accepted-source/public byte comparison, an independent
cold anonymous full-commit install, two repeat maintenance installs and two
existing-slot offline reinstalls. Slot and generated route bytes remained
identical; a cold install refreshed only the lock's generation timestamp.
Regeneration preserved human prefixes/suffixes around all three managed blocks.
The [baseline comparison](vibevm-adoption-assessment.md#same-content-baseline-and-evidence-limits)
records clean-clone file reads and disposable Git revert/removal separately.

## Drift, missing files and recovery

The local verifier checks the exact graph, source/lock/tree hashes, complete
passive slot inventory, receipt and generated file route. Refuse a source
proposal with drift or a collision; preserve reviewed overlays and investigate.
Malformed managed markers are refused by the pinned generator. Ordinary missing
file recovery restores accepted Git content; do not bootstrap stock core policy,
force regeneration over human text or introduce a hidden session-time resolver.

Upstream `vibe check` does not establish file reachability or authority: probes
showed it accepts a missing INDEX, a missing procedure and a divergent lock hash.
The local verifier refused each state. Upstream same-version drift
handling is not a sufficient final pin guarantee; lock/slot equality and accepted
source comparison remain maintenance evidence. Offline reads from a clean clone
are distinct from cold offline CLI acquisition, which is not promised for a
remote Git dependency. Existing-slot offline reinstall is the bounded probe.

Rollback or removal is an ordinary Git revert of this atomic migration,
restoring the previous local controls, AGENTS/user pointers and empty graph/INDEX
along with removing the slot. It needs no VibeVM, cache or network. Do not remove
only the package while leaving adopted pointers behind. `vibe clean` is not
rollback: it can remove INDEX without restoring local policy. Updates require a
separately authorized reviewed source change; new package topics do not activate
by availability alone. No automatic package update, Phase continuation, merge,
deployment, release or Issue closure follows from this implementation.
