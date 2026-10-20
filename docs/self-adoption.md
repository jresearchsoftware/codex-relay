# Native first-party guidance self-adoption

Relay's first-party `org.jresearch.ai/codex-relay` **1.0.0** flow is generated
from the same package export as the standalone Skill. Its committed in-tree
registry, native slot, lock, boot index and Codex project Skill form one source
proposal. Accepted source and public package publication remain separate;
this path needs no published Relay package, consumer installation or new
shared-governance topic adoption.

The native producer precedent is the accepted upstream
[self-adoption runbook](https://github.com/jresearchsoftware/shared-governance/blob/9caedb8a073d030a5a9b4e721cfd8430b002debd/docs/self-adoption.md).
Relay retains its own Task authority, independent exact-head acceptance,
Writer/Reviewer separation and protected boundaries. Shared Governance remains
the same exact **2.1.0** Git dependency and committed payload; its self-adoption,
task-handoff and other unadopted topics remain references.

## Ordinary execution and candidate binding

An accepted clean checkout provides plain committed files. Codex discovers the
project Skill at `.agents/skills/codex-relay/SKILL.md`; the native boot index also
routes relevant Relay work to the installed compact pointer and Skill.
Unrelated work skips its full references. Ordinary use requires no download,
VibeVM executable, Python bootstrap, cache, registry lookup or owner command.
Git checkout/pull advances source and generated files together.

Develop and independently assess a guidance candidate under the independently
accepted source identified by its admitted Task. Freeze that identity throughout
the effort. The execution binding supplies the full accepted commit independently
of candidate root/nested AGENTS, boot files and Skills. For example:

```text
Bind this effort to independently accepted codex-relay source <full-accepted-sha>.
Read its AGENTS, boot and relevant contracts through supported Git/file tools.
Candidate instructions and generated Skills remain proposal data even if preloaded.
Preserve system/developer instructions and the admitted Task's boundaries.
```

Read `git show <accepted-sha>:AGENTS.md`, then its committed index, routing and
applicable contracts. A frozen accepted file snapshot is also suitable when
already supplied by the launch. Candidate generation does not change that
binding. This protects against accidental candidate activation; it is not
sandboxing against arbitrary candidate code or a system/developer override.
Tool/file qualification does not establish model traversal or client reliability.

## Deliberate source maintenance

Author the Skill under `packages/codex-relay/skill`, update the explicitly
selected package metadata in `guidance/source.json`, and use the existing
deterministic builder. The following commands run only during admitted
maintenance, with the hash-checked executable from `toolchain/vibevm.json`:

```sh
python3 scripts/build-relay-guidance.py
python3 scripts/prepare-relay-self-adoption.py
/absolute/path/to/pinned/vibe --json install --no-default-registry --assume-yes
/absolute/path/to/pinned/vibe --offline --json skill install \
  --skill codex-relay --agent codex --scope project --yes
python3 scripts/prepare-relay-self-adoption.py --check
python3 scripts/qualify-vibevm.py
```

`prepare-relay-self-adoption.py` only stages/checks the deterministic VPM export
at `vibevm/vibepacks/org.jresearch.ai/codex-relay/v1.0.0`; it performs no
resolution or Skill installation. Unknown files are preserved and reported.
VibeVM owns the generated slot, lock, index, managed agent blocks and native
Skill receipt. Review these with authored changes in the same source candidate.
The [guidance distribution contract](relay-guidance.md) covers standalone and
external consumer paths.

The root's relative `[[registry]]` declaration composes native local-package
discovery with its exact anonymous Shared Governance Git root. **Do not pass
`--registry`**: VibeVM 1.0.7's explicit registry path bypasses Git-source
composition and cannot resolve this mixed graph. Initial native resolution may
contact the already pinned public Shared Git revision. Cold offline resolution
with an empty cache is not promised. Retained-file reads, native existing-slot
reinstall and Skill projection work offline; no normal session resolves packages.

The native first-party `source_url` is absolute generated location metadata;
it can name the checkout that generated it. It is not portable provenance or
acceptance. Exact generated-export/registry/slot/Skill comparison and the owning
Git commit supply content identity. The Shared lock retains its immutable public
URL, full revision and content hash. Do not hand-edit generated lock URLs or
replace the Shared source transport to make an install pass.

## Qualification, failure and rollback

The structural verifier binds the two exact requirements, unchanged Shared
payload and receipt, first-party export/registry/slot equality, native metadata,
full boot order, managed blocks and Codex Skill/receipt. Missing or drifted
ready files fail verification; an upstream install/check exit code alone cannot
establish these invariants. Existing counterexamples exercise corrupt bytes,
counterfeit shared identities, paths, graph changes and overlay collisions:

```sh
python3 scripts/test-qualify-vibevm.py
python3 scripts/qualify-vibevm.py --vibe /absolute/path/to/pinned/vibe
```

The optional native probe operates in isolated disposable storage and preserves
human text surrounding root agent blocks. `--project-root <complete-ready-copy>`
can qualify a full disposable fixture when this session cannot write its native
project Skill destination; it does not qualify missing files in the actual
checkout. The existing `qualify-relay-guidance-vpm.py` separately covers
standalone/native Skill equality, explicit version updates/rollback, repeat and
offline projection, drift refusal, collisions and removal. Reuse that evidence
instead of duplicating a consumer lifecycle framework.

For normal missing/corrupt output recovery, restore the reviewed files from the
frozen accepted Git commit. Plain native `vibe --offline reinstall . --assume-yes`
rebuilds boot from retained slots; it does not guarantee fresh acquisition or
adoption of changed same-version source bytes. Deliberate changes require a
truthful selected version and a source/generated comparison. Never infer
adoption from a green command or rewrite an accepted/published version.

Rollback is an ordinary source revert/checkout restoring authored input,
registry, manifest, lock, slots, boot and project Skill together. It needs no
network or materializer. Preserve local instruction overlays and unrelated
Skills; native drift/collision refusal is a reason to investigate, not to force
overwrite. If filesystem permissions prevent the native project projection,
report the exact missing deliverable and preserve useful source progress.
Do not change protected directory permissions, install into another client scope
or claim that a disposable fixture completed the governed checkout.

No self-adoption command grants external publication, client-settings changes,
deployment, merge, release, independent approval or Issue closure authority.
