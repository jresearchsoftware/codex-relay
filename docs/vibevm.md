# Pinned passive governance consumer

The Task [#91](https://github.com/jresearchsoftware/codex-relay/issues/91)
source proposal upgrades the exact `org.jresearch.ai/development-governance`
dependency from 1.1.0 to **2.1.0**, retaining the explicitly adopted
proportional-controls and relevant requirement-authority topics.
The [ownership mapping](relay-guidance-ownership.md) distinguishes shared meaning
from Relay's typed authority, admission, publication and independent review.
The full Relay material contract-change gate, native Task/Step/CR authority,
Writer/Reviewer separation, warning review and protected boundaries stay local.
Task-handoff, package-versioning, producer self-adoption and GitHub repository
governance are bundled but **not adopted** by installing this dependency.
Task-handoff is a pinned semantic reference for the ownership comparison, not a
partially activated protocol. Full topic adoption needs an explicit owner
disposition reconciling its Deliberative verdict prerequisite and multi-result
Outcome routing with Relay's accepted product contract. Conditional boot
paragraphs grant no new operation, approval, routing or settings authority.

Task [#97](https://github.com/jresearchsoftware/codex-relay/issues/97), Step 3,
previously adopted the first two topics at 1.1.0. Its
[semantic comparison](vibevm-adoption-assessment.md) remains historical evidence.
Candidate guidance does not govern its own implementation or review; those
remain bound to accepted Relay source at admission. Independent acceptance,
merge, external publication, consumer adoption and Issue closure remain separate.

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
                  |       +--> other four topics         unadopted; skip
                  +--> 90-user.md          local routing/adoption bindings
```

The package pointer is a short unconditional INDEX entry; the full protocols
are conditional Markdown reads. VibeVM 1.0.7 emits `kind = "static"` for this
pointer even though the package declares `boot_snippet.link = "dynamic"`.
Neither that declaration nor conditional reading selectively installs clauses.
Unrelated tasks skip the full protocols. No STATIC lane is generated.

Root [AGENTS](../AGENTS.md) selects the relevant topics and links
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

The [manifest](../vibe.toml) declares exact `=2.1.0`, the public distribution Git
URL and full immutable revision, with anonymous authentication. There is one
root dependency and no transitive dependency. The schema-7 [lock](../vibe.lock),
complete [slot](../vibevm/vibedeps/org.jresearch.ai.development-governance/2.1.0/README.md),
[DISTRIBUTION receipt](../vibevm/vibedeps/org.jresearch.ai.development-governance/2.1.0/DISTRIBUTION.json)
and native slot inventory are committed together. Project version `0.0.0` is
not a Relay release.

| Identity | Accepted value |
| --- | --- |
| Producer source | `jresearchsoftware/shared-governance` `c3fbc8c2d10982889bea526161f810902def4289` |
| Public distribution | `jrs-vibevm/org.jresearch.ai.development-governance` `4211f55dcaeb3077d6abdbfba53a42ed848351b2` |
| Observed annotated `v2.1.0` object | `8c920e57728b47f35cf671536b1d4dffc5488383`, peeling to that distribution commit |
| Receipt payload SHA-256 | `1d6e4098ee557319dc04d21defc33260aee1ce21e82b502f8e60726b2b68e955` |
| Receipt file SHA-256 | `a20f074a317f5e725d77b5b510e3e4c129f41fa266b5a9d3d4dae3ddf554dadc` |
| VibeVM complete distribution tree hash | `sha256:df90ef1a287c2ce5a70aff4443a0782410b628459722792ed326bde5aaf86ecc` |

The receipt hashes ten payload files, while the native tree hash also includes
the receipt. They use different recipes and must not be conflated. Anonymous
full-revision acquisition confirmed every payload byte against the accepted
producer path `packages/development-governance`, the complete distribution file
set and receipt hashes. Producer-only generated AGENTS/CLAUDE/GEMINI/INDEX routes
are excluded by the accepted exporter, rather than shipped as package payload.
The annotated tag is unsigned;
its observed object identity is not signature proof or a guarantee against
future tag mutation. The manifest pins the commit, not the tag alone.

The source acceptance chain is [Task #14 completion](https://github.com/jresearchsoftware/shared-governance/issues/14#issuecomment-6114995015)
for the original task-handoff topic, [Task #26 completion](https://github.com/jresearchsoftware/shared-governance/issues/26#issuecomment-6139463745)
for the 2.0.0 execution-cycle/chronology/acceptance/Outcome contract, and
[Task #13 owner acceptance](https://github.com/jresearchsoftware/shared-governance/issues/13#issuecomment-6149080652)
plus [completion/publication](https://github.com/jresearchsoftware/shared-governance/issues/13#issuecomment-6149144574)
for additive 2.1.0. Those shared reviews disclose owner-account advisory/project
acceptance rather than authenticated distinct-reviewer GitHub approval. Relay's
stronger native independent-review requirements are preserved.

The major task-handoff transition requires explicit adoption: one newly
authorized execution after a terminal result advances Step, even on the same PR;
the historical charter and chronological Decisions define current authority;
minimal handoffs navigate to it; Deliberative review withholds formal approval
until the necessary owner Decision; one canonical Outcome follows the complete
actual result. Those are shared protocol semantics, not newly activated Relay
behavior. The ownership mapping identifies matching existing principles and
retains Relay's accepted typed routing, verdict, exact-head, identity, replay
and protected-action guarantees. Incompatible additional shared obligations
await explicit owner disposition. The 2.1.0 GitHub topic adds no automatic
settings audit or mutation.

Historical 1.1.0 remains readable at accepted Relay
[source `4847c36`](https://github.com/jresearchsoftware/codex-relay/tree/4847c368ae5ea956fd6370bee207c8e4a176e8e0/vibevm/vibedeps/org.jresearch.ai.development-governance/1.1.0)
and public distribution
[`fa901b9`](https://github.com/jrs-vibevm/org.jresearch.ai.development-governance/tree/fa901b9e866ea0246b99bf9025ca00a0ca20267c).
The native maintenance install prunes the superseded active slot; this does not
rewrite either frozen release or historical source. Git revert restores the
previous manifest, lock, slot and routing as one source change.

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

The Task #91 dependency probe ran the pinned Linux musl tool with isolated
HOME/settings/cache and no inherited credentials against the exact public
revision. Its native 1.1.0 to 2.1.0 upgrade produced the committed lock, complete
slot and INDEX, and pruned the old active slot. Independent API readback compared
every published payload byte to accepted producer source and checked the complete
file set, receipt and native tree hash. Linux filesystem qualification then
passed all 13 focused verifier tests, acquired-source/public comparisons, two
existing-slot offline reinstalls, route repair and overlay/collision probes.
Slot and generated route bytes stayed identical; regeneration preserved human
prefixes/suffixes around all three managed blocks. These are tool/file proofs,
not model traversal or Relay installation evidence.

The prior [Task #97 baseline comparison](vibevm-adoption-assessment.md#same-content-baseline-and-evidence-limits)
records the 1.1.0 clean-clone reads, cold acquisition and removal experiment as
historical evidence. Do Linux mode/symlink probes on a Linux filesystem; Windows
mounted files can expose executable bits through the filesystem projection.
Copy candidate bytes with their Git modes into isolated Linux storage instead
of weakening passive-payload mode checks.

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

Rollback of the Task #91 dependency upgrade is an ordinary Git revert of the
reviewed source change, restoring the previous 1.1.0 manifest, lock, slot and
AGENTS/user pointers together. The older Task #97 adoption's removal restores its
previous local controls and empty graph/INDEX. Neither needs VibeVM, cache or
network. Do not remove
only the package while leaving adopted pointers behind. `vibe clean` is not
rollback: it can remove INDEX without restoring local policy. Updates require a
separately authorized reviewed source change; new package topics do not activate
by availability alone. No automatic package update, Phase continuation, merge,
deployment, release or Issue closure follows from this implementation.
