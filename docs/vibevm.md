# Optional VibeVM project

Relay has a dependency-free VibeVM v1.0.7 project prepared under
[Task #97](https://github.com/jresearchsoftware/codex-relay/issues/97), Phase 1.
It adds maintenance-time configuration without changing Relay execution.
Ordinary Codex sessions, tests and Relay workers need no VibeVM executable,
registry, cache, network access or additional owner action for this project.

The [manifest](../vibe.toml) declares only a project, with no package,
requirement, registry, hook, tool, MCP or Skill declaration. Its `0.0.0` version
is a scaffold identity, not a Relay release or governance package version.
The [lock](../vibe.lock) is the initializer's schema-7 empty lock; its timestamp
records creation, not a moving resolution input. The committed bytes are reused
unchanged. `spec_format = "mixed"` keeps future materialization byte-preserving
rather than opting into format conversion.

The only retained boot artifact is the generated
[empty index](../vibevm/vibespecs/boot/INDEX.md). It preserves the boot directory
required by the pinned tool in a clean clone, and names no content to load.
Its final blank line is omitted to satisfy Relay's existing whitespace check;
qualification compares regeneration after only that newline normalization.
There is no `STATIC` lane, authored boot snippet, WAL/checkpoint, managed agent
block, dependency slot or projected Skill. [AGENTS.md](../AGENTS.md), the live
Issue/CR/Task Request, Relay contracts, local policies and agent entrypoints
retain their existing authority and loading order. In particular,
[proportional controls](execution-policy.md#proportional-controls-and-operator-usability)
remain local and unchanged.

## Maintenance qualification

The [tool pin](../toolchain/vibevm.json) records upstream source commit
`b6659978453f50e6d1d4d99626d70b980a2c5847` and the exact musl binary hash
previously qualified by
[shared-governance](https://github.com/jresearchsoftware/shared-governance/blob/60704ce3e0f0243d157646989429c6e621fc8f04/toolchain/vibevm.json).
No binary is committed or installed by Relay. The GNU release's known
`GLIBC_2.39` prerequisite is avoided by this same-release musl pin; it does not
become a new Relay platform requirement. VibeVM remains alpha tooling with
version-specific manifest, lock and generation behavior.

The optional [qualification script](../scripts/qualify-vibevm.py) uses only
Python 3.11+'s standard library and Git. Stage intended new files first so its
tracked-files fixture includes them. It performs structural checks without a
VibeVM executable:

```sh
python3 scripts/qualify-vibevm.py
```

For an actual tool probe, download the musl binary from the exact URL in the
pin into a disposable directory, verify its SHA-256 and make that file
executable. Pass its absolute path; the script verifies the digest again before
running it:

```sh
python3 scripts/qualify-vibevm.py --vibe /absolute/temporary/path/vibe
```

All tool operations run on disposable copies with isolated home/settings/cache
and `--offline`. The probe inspects actual `init --no-registry` effects,
checks preservation of human-owned agent text, validates the prepared project,
requires zero `check` findings, and reproduces the empty index twice without
changing the manifest or lock. It also checks the retained scaffold with stock
agent redirects removed. No model call, package resolution or publication is
part of this probe. Structural checks alone do not establish tool compatibility
or actual client behavior; an unavailable tool is a qualification limitation.

Do not run stock `vibe init`, `install` or `reinstall` on Relay as a session
startup or routine repair step. Even dependency-free `init --no-registry`
creates `00-core.md`, `90-user.md`, unused spec directories, local state and
session redirects in `AGENTS.md`, `CLAUDE.md` and `GEMINI.md`. The stock core
requires WAL/checkpoint startup and `Human > Spec > Tests > Code` precedence.
`reinstall` also generates session redirects. These effects were inspected in
isolation and are deliberately excluded from the committed Relay scaffold;
the pinned checks accept their absence. Local `.vibe/` state and the persistent
boot transaction lock are ignored, not consumer policy or committed payload.

## Later dependency adoption

Phase 1 adopts no shared package and does not transfer semantic ownership.
The intended future package is `org.jresearch.ai/development-governance`,
with prospective distribution at
`jrs-vibevm/org.jresearch.ai.development-governance`. Neither the coordinate nor
candidate `=0.1.0` proves publication or immutable content. A separately
authorized successor Request must verify remote publication, accepted producer
SHA, distribution identity and complete hashes, and resolve a new exact Relay
starting head before any adoption.

That future reviewed change must commit the exact requirement, lock, passive
materialized bytes, native Skill and bounded routing together with removal or
reclassification of the reusable local duplicate, preserving Relay-specific
bindings and overlays. Resolution/update stays opt-in at maintenance time;
normal execution must read committed content offline. Compare the same bytes
with the Git/native-Skill baseline rather than assuming a VibeVM advantage.
Update this Phase 1 qualification for the admitted migration, verify rollback
through an ordinary Git revert, and obtain independent exact-head acceptance.
The [distribution design](vibevm-governance-design.md) supplies the earlier
comparison and known alpha limitations. Merging Phase 1 does not start Phase 2,
deploy anything or authorize Issue closure.
