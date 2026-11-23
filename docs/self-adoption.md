# Native first-party guidance self-adoption

Relay authors and consumes its product Skill. Portable producer/candidate
semantics belong to the complete adopted pinned
[Self Adoption protocol](../vibevm/vibedeps/org.jresearch.ai.development-governance/12.5.0/vibevm/vibespecs/protocols/self-adoption.md).
This document supplies the native materialization, accepted-source binding and
recovery mechanics. [AGENTS](../AGENTS.md) and the
[ownership mapping](relay-guidance-ownership.md) bind the other adopted topics.

The first-party `org.jresearch.ai/codex-relay` **10.0.0** candidate uses the
native export. Registry, slot, lock, boot index and projected native Skill travel
together. Root [AGENTS](../AGENTS.md) adopts Shared **12.5.0**, independently
pinned at the exact Git identity in [the identity contract](vibevm.md#selected-immutable-identities).
The native product's `>=12.1.0` floor covers GH-014 and HC-001–003. Standalone
and publisher evidence include exact 12.1.0. The
[release classification](relay-guidance.md#version-and-provenance) explains
the MAJOR from accepted 9.0.0. Frozen 9.0.0 and earlier registry payloads
preserve their bytes. Source acceptance, publication, installed activation
and consumer adoption remain separate.

## Accepted-source binding and ordinary use

A clean accepted checkout provides plain committed files. Codex discovers
`.agents/skills/codex-relay/SKILL.md`; the boot index independently routes relevant
work to the compact package pointer and Skill. Unrelated work skips full
references. Ordinary use needs no materializer, Python, registry, cache, network
or additional owner command. Checkout/pull advances the accepted ready files.

Relay's execution binding identifies the independently accepted source commit,
separately from candidate root/nested AGENTS, boot and Skills. Task #199's execution freezes independently accepted Relay source
`512b2b5ea2867b92958580f17f6aee24c23b1fba` before candidate edits;
its historical Skill product-contract baseline was
`61bfe2be5bdf5632449cd7f544c6c5ba4d4146d4`. Task 57 froze its accepted execution guidance at
`cfeb633c86408327bf9941a5dfaaa41f98706ac1`. Task 194 freezes accepted guidance
at `4f0990c4b676a45f7e37d37ecb10fecc871b7a25`; its 7.0.0 artifact uses source-tree
input hashes and that accepted baseline as provenance context. Candidate schema bytes do not replace the
accepted guidance governing this execution. These are distinct identities, and the
candidate cannot replace its own execution/review authority. Task #266's
accepted 8.0.0 release froze independently accepted guidance at
`c8e990bef9aabefe9ec0bd74141afdba7d2dfde1`. The accepted 7.0.0 registry is immutable;
its Task #194 closure and Shared 10.0.0 behavior remains the baseline. Task #266
changes automatic prose-drift stopping while keeping conservative manual
predispatch, truthful reporting and actual permission/effect guards. Task and
Decision requirements govern work and acceptance; manual stop/control is direct
to Codex and automatic control uses native Actions cancellation/containment,
with structured holds retained as internal safety guards.
Task #244's 9.0.0 candidate freezes independently accepted guidance at
`7f95a60c485ccf40025dae78f652adc8df3b19ea`. Its accepted 8.0.0 registry remains
immutable. The candidate adds protected causal diagnostics and live lifecycle
progress, and changes terminal `BLOCKED` Actions results to fail visibly; it does
not activate that candidate guidance in the implementing session.

Task #273 freezes accepted PR #277's integrated guidance at
`95b374b9a575810b4253db46adbe1618b82afd89` before reading 12.1.0 candidate routes.
Its generated 10.0.0 package remains a candidate until independent acceptance
and integration. Historical and admitted guidance stay at their selected
revisions.

Task #295 freezes the independently accepted PR #291 integration
`3337e74b4a54846122eac9dc2111781b8a1056a7` with its Shared 12.1.0
development lock before editing candidate routes. Shared 12.5.0 is the proposed
development selection. The projected native Relay Skill still comes from the
same 10.0.0 package and reads the selected Shared slot through the root lock.

Use supported Git/file reads, for example
`git show <accepted-sha>:AGENTS.md`, then the accepted index and relevant routes.
An already supplied frozen accepted snapshot is equivalent. Preserve system/
developer instructions and current admitted Task authority. File qualification
proves neither actual model traversal nor isolation from arbitrary candidate code.

## Deliberate source maintenance

Author the Skill under `packages/codex-relay/skill` and select truthful immutable
identities in `guidance/source.json`. During admitted maintenance, use the
hash-checked executable from `toolchain/vibevm.json`:

```sh
python3 scripts/build-relay-guidance.py
python3 scripts/prepare-relay-self-adoption.py
/absolute/path/to/pinned/vibe --json install --no-default-registry --assume-yes
/absolute/path/to/pinned/vibe --offline --json skill install \
  --skill codex-relay --agent codex --scope project --yes
python3 scripts/prepare-relay-self-adoption.py --check
python3 scripts/qualify-vibevm.py
```

For a project-only Shared update or root Landscape flow integration, use the
existing frozen builder/registry `--check` modes; no Relay artifact generation
or version change is needed. The [Landscape integration](vibevm.md#landscape-flows-and-local-adoption)
is root development guidance outside the standalone Skill and release-evidence
closure. Its installed boot/AGENTS routes remain candidate data until accepted;
continue under the independently frozen admitted guidance. Native root install
produces its lock, complete slots/receipts and INDEX together without requiring
another Skill projection or startup command.
The single `build-relay-guidance.py` builder reads the pinned Shared 12.1.0
release-evidence slot directly under `guidance/dependency-closure`; it needs no
disposable input adapter or unselected root slot. This retains the accepted
builder provenance mechanism while preserving frozen older registry payloads. The active root policy graph selects Shared 12.5.0.
The verifier
compares the complete standalone snapshot with its own accepted distribution
and separately validates the root consumer lock/slot. Native install prunes retired active slots. Git and the frozen registry
retain the previous selected payloads.

`prepare-relay-self-adoption.py` stages/checks the selected deterministic VPM
export at `vibevm/vibepacks/org.jresearch.ai/codex-relay/v10.0.0`. It performs no
resolution or Skill installation and preserves/reports unknown files. It does
not rewrite frozen accepted `v1.0.0`, `v2.0.0`, `v2.0.1`, `v3.0.0`, `v3.1.0`, `v4.0.0`, `v4.1.0`, `v5.0.0`, `v6.0.0`, `v6.1.0`, `v7.0.0`, `v8.0.0` or `v9.0.0` bytes. Native VibeVM
owns slot, lock, index,
managed agent blocks and Skill receipt. Review generated and authored changes
in the same source candidate; [relay-guidance.md](relay-guidance.md) covers the
standalone export and external consumer instructions.

The root relative `[[registry]]` composes local first-party discovery with the
explicit anonymous Shared Git root. **Do not pass `--registry`**: The retained mixed-graph interface
bypasses Git-source composition in that mode and cannot resolve this mixed graph.
Initial acquisition may contact the pinned public commit; cold offline resolution
with an empty cache is not promised. Existing-slot reinstall, retained-file reads
and Skill projection are the bounded offline paths.

The first-party native `source_url` is generated absolute location metadata and
may name its generating checkout; it is not portable provenance or acceptance.
Use exact export/registry/slot/Skill comparison and the owning Git commit for
content identity. VibeVM 1.0.11's local-source freshness check nevertheless needs
that location to exist. For deliberate native maintenance after moving/copying
a checkout, run the supported `install --no-default-registry --assume-yes`
command there to resolve the relative registry and regenerate its lock location.
The qualification probe does this in disposable copies before offline checks,
verifying that only the local URL and generation timestamp change. It also moves
a generated checkout with its origin absent, observes the missing-source warning,
and verifies native repair. Ordinary offline file-reading startup needs no such
command. Shared and Landscape lock identities retain their public URLs, immutable revisions
and tree hashes. Do not hand-edit generated URLs or ignore freshness warnings.

## Qualification, failure and rollback

The structural verifier binds the exact project requirements, the native
Shared lower bound, selected Shared payload/receipt, first-party native
export/registry/slot equality, native metadata, boot order, managed blocks and
project Skill/receipt. It checks that native shared routing reads this project's
selected dependency rather than a standalone bundle. A native install/check exit
code alone cannot establish those invariants. Use the existing checks:

```sh
python3 scripts/test-qualify-vibevm.py
python3 scripts/qualify-vibevm.py --vibe /absolute/path/to/pinned/vibe
```

The optional native probe uses isolated disposable storage and preserves human
text around managed blocks. It sets `VIBE_NO_DEFAULT_REGISTRY=1` as well as
`--no-default-registry`: pinned VibeVM 1.0.11 can otherwise seed its user-global
GitHub/GitVerse registry during install. The probe verifies that no global
registry was created while retaining the project-local producer registry,
pinned Git sources, relocation repair and clean-install checks. `--project-root <complete-ready-copy>` qualifies a
complete fixture when the actual destination is unavailable; it does not prove
missing outputs exist in the governed checkout. The existing
`qualify-relay-guidance-vpm.py` covers delivery-specific content and shared
routing, product contract parity, selected-version update/rollback, repeated/
offline projection, drift, collisions and removal.
Actual results and limitations remain candidate evidence, not claims implied by
these instructions.

Recover missing/corrupt outputs from the frozen accepted Git revision. Native
`vibe --offline reinstall . --assume-yes` rebuilds boot from retained slots; it
does not promise fresh acquisition or changed same-version adoption. Deliberate
changes need a truthful selected version and source/generated comparison.

Rollback restores accepted authored inputs, registry, manifest, lock, slots,
boot and Skill together through Git. It needs no network or materializer.
Preserve local overlays and unrelated Skills; investigate drift/collisions.
If the actual native destination is inaccessible, report the missing projection
and preserve useful source work. Do not change protected permissions, switch
client scope or claim a fixture completed the actual checkout.

Pinned Codex 0.160.0 `workspace-write` protects the workspace-root `.agents`
path, even when absent. A projection `EROFS` there does not establish a read-only
checkout or collector failure. Until the owner-selected native Full Access
launcher is qualified and adopted on the installation, actual projection needs
an authorized manual checkout. Do not change a retained attempt's permissions
to bypass the failure. A nested disposable
fixture can qualify projection without claiming checkout adoption. Existing
projected guidance remains readable. The optional
[native filesystem probe](codex/cli-integration.md#native-filesystem-probe)
distinguishes these cases without a model call.

Intentional Shared dependency updates require assessment of the used protocol
semantics, applicability, exceptions and Relay bindings. Compatible or irrelevant
updates do not require a Relay Skill release; a new Shared major alone does not
change that. See the [compatibility assessment](relay-skill-compatibility.md) and
[delivery contract](relay-guidance.md).

Self-adoption machinery does not perform external publication, client-settings
updates, deployment, merge, independent approval or Issue closure.
