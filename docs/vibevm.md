# Bounded native VibeVM routing

Task [#99](https://github.com/jresearchsoftware/codex-relay/issues/99), Step 2,
selects bounded native route C through the
[owner Decision](https://github.com/jresearchsoftware/codex-relay/issues/99#issuecomment-6097679412)
and [manual Request](https://github.com/jresearchsoftware/codex-relay/issues/99#issuecomment-6097793473).
The source configuration uses VibeVM 1.0.7's native generator with two short
Relay-authored boot files. Independent exact-head acceptance and merge remain
separate from this implementation. The
[Step 1 assessment](vibevm-routing-assessment.md) records the historical stock,
direct and bounded-route comparison.

Ordinary Codex sessions, tests and Relay workers read committed files and need
no VibeVM executable, registry, cache, network or additional owner action.
Worker prompt construction, trusted execution authority and optional developer
hooks are unchanged. This route does not adopt stock WAL, specification
precedence or disputed-spec implementation policy. Their comparative study
remains separate under Task #102.

## Committed route and ownership

```text
AGENTS.md                   existing Relay policy + native managed block
CLAUDE.md / GEMINI.md        native managed blocks
             |
             v
vibevm/vibespecs/boot/INDEX.md   generated TOML, two static entries in order
             |
             +--> 00-core.md    authored authority/loading boundary
             +--> 90-user.md    authored local routing conventions
```

VibeVM owns only the managed `<vibevm>` blocks and generated
[INDEX](../vibevm/vibespecs/boot/INDEX.md). All pre-existing human-authored
[AGENTS.md](../AGENTS.md) bytes remain intact before its appended block. The
[core](../vibevm/vibespecs/boot/00-core.md) and
[user](../vibevm/vibespecs/boot/90-user.md) files are supported user-owned inputs,
not edits to generated content or a second routing engine. They identify the
existing canonical policy and direct relevant work to its existing pointers.
Component manuals stay outside mandatory boot. The combined authored boot
content is 1,451 UTF-8 bytes; this is not a token, latency or cost measurement.

Codex already reads root AGENTS instructions. For a client entering through
CLAUDE or GEMINI, core identifies the human-authored AGENTS policy and asks it
to apply that policy once without traversing the managed route again. Existing
client/global/local instruction precedence remains intact; repository prose
does not override it. These are instructions, not a runtime guard or proof of
actual client traversal. No private/global instruction files were modified.
The route introduces no per-task selection: both files are unconditional;
component loading remains the agent's existing just-in-time judgment.

There is no STATIC lane, WAL, dependency slot, projected Skill, hook, tool or
MCP declaration. The [manifest](../vibe.toml) still declares only the original
project, with `spec_format = "mixed"`. Its `0.0.0` identity is not a Relay
release. The [lock](../vibe.lock) remains the exact original schema-7 empty
lock, including its creation timestamp. No
`org.jresearch.ai/development-governance` requirement was added, installed,
resolved, locked or materialized. Local
[proportional controls](execution-policy.md#proportional-controls-and-operator-usability)
retain their canonical ownership and semantics.

Generated INDEX is committed exactly as emitted, including the pinned
serializer's blank EOF line. A file-specific
[Git attribute](../.gitattributes) disables only `blank-at-eof` for this artifact;
all other whitespace checks remain applicable. No generated block or INDEX is
hand-edited or normalized. Local `.vibe/` lifecycle state and the persistent
boot transaction lock remain ignored, outside the committed route.

## Optional maintenance qualification

The [tool pin](../toolchain/vibevm.json) selects upstream source revision
`b6659978453f50e6d1d4d99626d70b980a2c5847` and the exact Linux x86_64 musl
binary SHA-256
`20d111df02eb28040ef4cb766bfcb0bde8ff4427b031f88f33eacb3711c3e240`.
No binary is committed or installed by Relay. This avoids the same release's
GNU binary `GLIBC_2.39` prerequisite without imposing a new normal-session
platform requirement. Generation remains version-specific alpha-tool behavior.

The existing [qualification script](../scripts/qualify-vibevm.py) uses Python
3.11+'s standard library and Git. Its structural mode reads the committed
route without invoking VibeVM:

```sh
python3 scripts/qualify-vibevm.py
```

For actual tool qualification, obtain the exact binary from the pin in a
disposable directory, verify its SHA-256 and make that file executable. Stage
intended source additions so the tracked-file fixture includes them, then run:

```sh
python3 scripts/qualify-vibevm.py --vibe /absolute/disposable/path/vibe
python3 scripts/qualify-vibevm-routing.py --vibe /absolute/disposable/path/vibe
```

Both scripts recheck the binary digest. Tool operations use disposable projects,
isolated HOME/settings/cache and `--offline`, with no inherited authentication.
The first script now qualifies the actual bounded route. The second retains
the Step 1 stock/synthetic comparison; it removes the active managed block only
from its disposable comparison input. Neither script changes the checkout,
invokes a model, installs host dependencies or becomes a new required startup
command or acceptance gate.

The actual-route probe verifies:

- committed file reachability without local state or a VibeVM executable;
- unchanged manifest, lock, authored files and generated bytes after validation,
  two reinstalls and repeat init;
- human text before and after all three managed blocks surviving regeneration;
- duplicate and unclosed markers refused before changing route bytes;
- missing INDEX detected by file reads, and regeneration repairing missing INDEX
  and GEMINI without replacing authored policy.

The structural and pinned-tool probes passed on Linux. Upstream `vibe check`
reported no findings even with INDEX removed: it is not a reachability,
authority or acceptance check. Real Codex/Claude/Gemini traversal, semantic task
selection and model compliance remain **UNVERIFIED**. Pure file reads are the
simplest ordinary-session path tested; tool generation is separate evidence.

For an intentional maintenance change, author core/user inputs and regenerate
only in a disposable copy using the pinned tool:

```sh
/absolute/disposable/path/vibe --offline --json reinstall . --assume-yes
```

Review the resulting route and human overlays before copying the four generated
files back as an ordinary source proposal. Keep the empty manifest/lock graph
and bounded boot sources. Do not use stock init as session startup or a routine
repair: when an authored core is absent, init restores stock policy. Reinstall
preserves existing authored files but does not recreate a missing one.

## Missing files, collisions and rollback

If INDEX or an authored source is missing, file navigation is incomplete;
report the missing reference and retain the available canonical Relay authority.
Do not interpret a successful VibeVM check as recovery or invent boot policy.
Restore reviewed committed files through ordinary Git recovery. No automatic
CLI, network or hidden fallback is introduced. Auxiliary-client behavior when
their only route is broken remains unverified.

Malformed managed markers make the pinned generator fail with exit 3. Preserve
human text and reconcile the source proposal explicitly; do not force a
regeneration or overwrite overlays. The probe covers both duplicate pairs and
an unclosed block, and confirms all route bytes remain unchanged on refusal.

Rollback is an ordinary Git revert of the routing activation commit, restoring
the pre-activation AGENTS file, absent auxiliary redirects/core/user files and
empty INDEX. Revert does not need VibeVM or local lifecycle state. `vibe clean`
is not rollback: it deletes INDEX while retaining redirects and authored files.
The disposable Git revert is checked against the exact starting tree before
handoff; no production service or installed consumer is changed.

## Later package adoption

Shared-package adoption and migration/removal of local proportional-controls
remain separately admitted work under Task #97, after the owner-required
shared-governance Task #15 semantic completeness assessment/corrections.
A future complete Request must verify accepted producer/distribution identity,
content hashes, exact Relay starting head, semantic ownership, qualification and
rollback. This routing change grants no package adoption, deployment, release,
merge, Task approval or Issue closure authority.
