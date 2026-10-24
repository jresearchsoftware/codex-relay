# Native first-party guidance self-adoption

Relay authors and consumes its product Skill. Portable producer/candidate
semantics belong to the complete adopted pinned
[Self Adoption protocol](../vibevm/vibedeps/org.jresearch.ai.development-governance/4.0.0/vibevm/vibespecs/protocols/self-adoption.md).
This document supplies the native materialization, accepted-source binding and
recovery mechanics. [AGENTS](../AGENTS.md) and the
[ownership mapping](relay-guidance-ownership.md) bind the other adopted topics.

The first-party `org.jresearch.ai/codex-relay` **3.0.0** candidate uses the
native export. Its registry, slot, lock, boot index and projected native Skill
travel together. Its Shared dependency requirement is separate from the
standalone Skill's fixed snapshot. Root [AGENTS](../AGENTS.md) deliberately
continues to adopt Shared **4.0.0**, with the exact Git identity in
[the identity contract](vibevm.md#selected-immutable-identities); this delivery
change does not migrate the project to Shared 5.0.0.

The new major removes the native Skill's bundled Shared protocol paths and
changes dependency routing. Native readers use this project's reviewed lock
and selected Shared slot through `references/shared-protocols.md`. Standalone
retains a self-contained immutable Shared 4.0.0 snapshot, so the complete
Skill trees differ while retaining the same product contract. Frozen accepted
1.0.0, 2.0.0 and 2.0.1 registry payloads remain unchanged. Source acceptance does
not imply external publication or another consumer's adoption.

## Accepted-source binding and ordinary use

A clean accepted checkout provides plain committed files. Codex discovers
`.agents/skills/codex-relay/SKILL.md`; the boot index independently routes relevant
work to the compact package pointer and Skill. Unrelated work skips full
references. Ordinary use needs no materializer, Python, registry, cache, network
or additional owner command. Checkout/pull advances the accepted ready files.

Relay's execution binding identifies the independently accepted source commit,
separately from candidate root/nested AGENTS, boot and Skills. For this migration,
the product-contract baseline is
`61bfe2be5bdf5632449cd7f544c6c5ba4d4146d4`; the candidate cannot replace its own
execution/review authority. Use supported Git/file reads, for example
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

`prepare-relay-self-adoption.py` stages/checks the selected deterministic VPM
export at `vibevm/vibepacks/org.jresearch.ai/codex-relay/v3.0.0`. It performs no
resolution or Skill installation and preserves/reports unknown files. It does
not rewrite frozen accepted `v1.0.0`, `v2.0.0` or `v2.0.1` bytes. Native VibeVM
owns slot, lock, index,
managed agent blocks and Skill receipt. Review generated and authored changes
in the same source candidate; [relay-guidance.md](relay-guidance.md) covers the
standalone export and external consumer instructions.

The root relative `[[registry]]` composes local first-party discovery with the
explicit anonymous Shared Git root. **Do not pass `--registry`**: VibeVM 1.0.7
bypasses Git-source composition in that mode and cannot resolve this mixed graph.
Initial acquisition may contact the pinned public commit; cold offline resolution
with an empty cache is not promised. Existing-slot reinstall, retained-file reads
and Skill projection are the bounded offline paths.

The first-party native `source_url` is generated absolute location metadata and
may name its generating checkout; it is not portable provenance or acceptance.
Use exact export/registry/slot/Skill comparison and the owning Git commit for
content identity. Shared lock identity retains its public URL, immutable revision
and tree hash. Do not hand-edit generated URLs or change transport to make a
check pass.

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
text around managed blocks. `--project-root <complete-ready-copy>` qualifies a
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
