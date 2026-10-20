# Relay Skill client qualification

The native discovery probe is an opt-in, credential-free maintenance check:

```sh
python3 scripts/qualify-relay-skill-client.py \
  --codex /absolute/path/to/codex \
  --skill guidance/artifacts/standalone/codex-relay
```

Use a native executable, including `codex.exe` on Windows, rather than an npm
shell launcher. The probe requires exactly `codex-cli 0.162.1`; it reports the
executable digest instead of treating a version string as supply-chain proof.
It does not install or upgrade Codex. VibeVM is unnecessary for this check.

The probe creates a disposable Git repository and copies the complete artifact
to `.agents/skills/codex-relay`. HOME, CODEX_HOME, XDG directories, temporary
directories, Git configuration and Codex settings are isolated. The child
environment does not inherit API keys or login credentials. Ordinary HTTP
proxies point at an unavailable loopback endpoint; this is not an operating
system network-containment test. No existing consumer checkout or user
configuration is modified; no existing user settings or auth files are copied
into the isolated environment.

It generates the pinned executable's app-server JSON schemas, checks the
required request/response fields, and uses the native stdio protocol:

1. `initialize`, checking the returned isolated `codexHome`.
2. `initialized` notification.
3. `skills/list` with `forceReload: true` for the repository root, a nested cwd
   and an unrelated directory.
4. A second `skills/list` after adding an intentionally malformed, separately
   named fixture, to verify that the real parser exposes an error while the
   valid Relay Skill remains discoverable.

Assertions cover one `codex-relay` entry, its exact SKILL.md path, unchanged
frontmatter description, enabled repository scope, no positive-case parse
errors, nested-cwd discovery and exclusion from an unrelated cwd. The probe
accepts the artifact's single-line frontmatter description; it does not claim
to implement general YAML validation. It sends only the three listed protocol
methods, starts no thread or turn, and checks that no auth file or model-session
transcript was created. App-server diagnostics and configuration warnings remain
visible in its JSON result.

The result includes an artifact digest: SHA-256 of UTF-8 lines sorted by relative
path, each `path + NUL + lowercase-file-SHA256 + LF`, over every artifact file.
Rerun against the final generated candidate after any content change.

## Observed Codex evidence

The final 1.0.0 continuation candidate was checked on Linux and Windows on
2026-10-20 with the same hash-verified 0.162.1 executables below. Both platforms
reported the identical 23-file artifact digest
`aa5a45590b847987a1ab5f1897a4d1b475e9e11366b638ad8653574d02fc1969`.
Root/nested discovery, unrelated-directory exclusion and malformed-fixture
reporting passed, with zero model calls. Windows returned no diagnostics or
warnings. Linux reported the bundled-bubblewrap fallback because bubblewrap
was absent from PATH; this metadata-only probe ran no sandboxed commands and
does not qualify process isolation. No host package or privileges were changed.
The fresh manual source checkout also completed actual native project Skill
projection and structural verification; the original blocked worker checkout
and its incomplete projection were preserved separately.

On 2026-10-14 the generated 20-file standalone artifact passed the native probe
with both binaries below. Root and nested discovery succeeded; the unrelated
directory excluded Relay; the deliberately malformed fixture produced its
expected native error. There were no model calls.

| Native target | Version | Executable SHA-256 | Material diagnostics |
| --- | --- | --- | --- |
| Debian WSL, Linux x86_64 musl | 0.162.1 | `628e35487d888a28f0427fc37501da529dd3d81fcbad7a2c3421c1e8670d92e1` | No bubblewrap on PATH; Codex reported its bundled fallback. |
| Windows x86_64 MSVC | 0.162.1 | `dd13bdb162a184fa04039488b234a8258ef9b76f84e926c505d5742b19249a6a` | No warnings or stderr diagnostics. |

The Linux fallback warning does not invalidate metadata discovery. No sandboxed
command was executed, so this check provides no sandbox/isolation qualification.
The binary digests identify observed executables, not a new deployment pin.
These checks concern CLI app-server discovery; they do not establish discovery
in a different desktop release or synchronization of ChatGPT Project settings.

Parser and native discovery evidence are distinct from model behavior. This
probe does not establish automatic Skill selection, JIT reference traversal,
reasoning quality or correct decisions about live Task authority. Meaningful
behavioral testing uses realistic requests with the Skill and minimum source
artifacts, without supplying the intended answer; its evidence must be reported
separately. Successful discovery does not qualify an installed Relay controller,
Writer or Reviewer, credentials, deployment, merge or closure.

Official documentation describes the [app-server handshake and generated
schemas](https://learn.chatgpt.com/docs/app-server) and the [Skill format and
discovery](https://learn.chatgpt.com/docs/build-skills). Those moving documents
are orientation; the generated 0.162.1 schema and observed native responses are
the version-specific evidence here.

## Forward workflow evaluation

For the 1.0.0 continuation, a separate read-only helper evaluated ten synthetic
requests using the Skill without the author's intended answers. Cases covered
approved standalone continuation, automatic Writer isolation, missing manual
transport, retained-v3 completion, candidate self-authorization, offline reads,
warnings, external publication, local collisions and stale exact-head approval.
The evaluation found one portable-entrypoint routing gap: producer guidance
changes needed an explicit accepted-source binding before candidate routes.
The Skill now states that conditional rule directly without adopting the whole
shared self-adoption protocol. The other nine cases preserved their authority
and provenance boundaries. This is bounded implementation evidence, not native
independent acceptance or automatic client-selection proof.

For the historical 0.1.0 qualification, a separate Codex helper received only the assembled Skill and eight synthetic
requests, without the author's intended answers or implementation/tests. It
read workflow, compatibility and diagnostics references as needed. Its returned
actions preserved these boundaries: labels without admission; unavailable v4
manual transport; exact retained-v3 completion; safe canonical-branch
normalization before a head gate; independent review and keep-open closure;
genuine no-PR result/Task Approval; ordinary contributor scope; and warning
disposition despite green status. No decision-changing defect was observed in
these cases. This is bounded guidance evaluation, not installed-client automatic
selection proof, a live Task execution or independent product acceptance.

## Observed VibeVM capabilities

The 1.0.0 candidate's generated two-root consumer graph and full native Skill
projection passed the existing update, rollback, repeat, fresh-cache offline
reinstall, drift, collision and removal probes. Standalone and VPM Skill bytes
matched. The native package tree hash was
`sha256:7a9f89990b3f4d6ce03990e514f18e010b8d844e98d95fa6ffec0bedc546b454`;
Shared Governance retained its exact 2.1.0 Git revision and tree hash.
The separate [producer self-adoption](self-adoption.md) probe resolved the
in-tree first-party flow with that unchanged Shared Git root and verified
offline regeneration and human-overlay preservation in a complete isolated
project. Actual source adoption still requires all committed ready files and
independent acceptance; fixture success cannot substitute a missing project
projection.

The repository's [tool pin](../toolchain/vibevm.json) identifies VibeVM 1.0.7,
source `b6659978453f50e6d1d4d99626d70b980a2c5847`, Linux x86_64 musl SHA-256
`20d111df02eb28040ef4cb766bfcb0bde8ff4427b031f88f33eacb3711c3e240`.
A hash-verified isolated binary reported `vibe 1.0.7`. No VibeVM executable was
available on the Windows or Debian PATH; the native VibeVM probes used Debian
WSL. Windows-native VibeVM execution was not qualified.

A package of kind `flow` can declare its native Codex Skill directly:

```toml
[[skill]]
name = "codex-relay"
path = "skill"
agents = ["codex"]
include = ["SKILL.md", "references/**"]
```

`references/**` copies nested references. The supported Codex project target is
`.agents/skills/codex-relay`. There is no need for an adapter that recreates
VibeVM's Skill renderer. A bounded generator is useful for assembling the exact
accepted shared reference closure and provenance into a self-contained artifact
and supplying the no-VibeVM install path. The VPM manifest separately declares
the exact accepted shared package dependency. Native `[[skill.resource]]`
selects immutable HTTPS Git `[[embedded_source]]` inputs; it does not directly
name another installed package's slot as a resource source.

The observed native commands are:

```sh
vibe --json install --no-default-registry --assume-yes
vibe --offline --json skill list
vibe --offline --json skill install \
  --skill codex-relay --agent codex --scope project --dry-run
vibe --offline --json skill install \
  --skill codex-relay --agent codex --scope project --yes
vibe --offline --json skill uninstall \
  --skill codex-relay --agent codex --scope project --yes
```

Bare `install` resolves package dependencies, writes the schema-7 lock and
versioned `vibevm/vibedeps/<group>.<name>/<version>` slots, and regenerates boot
artifacts. It does not project `[[skill]]`. `reinstall . --assume-yes` likewise
does not project the Skill. The explicit `skill install` discovers declarations
from installed slots and projects selected files. Ordinary install also adds
or refreshes native managed boot blocks in AGENTS/CLAUDE/GEMINI while preserving
human text; use disposable staging when these generated boot changes are not
part of the consumer's reviewed proposal.

Native standalone projection returned `created`, `unchanged` on repetition and
`updated` after a source change. Its sibling ownership receipt is
`.agents/skills/.codex-relay.vibe-skill-receipt.toml`, with relative owned paths
and file SHA-256 values. It refused a foreign existing Skill directory, refused
to overwrite or remove changed owned files, and preserved an added local file
when removing the owned projection. These observations are specific to
`vibe skill install/uninstall`.

`vibe package` is the default lifecycle through distributable assembly. Its
built-in package-Skill contribution automatically projects declared Skills.
An isolated negative probe showed that this lifecycle projection **overwrites
a changed receipt-owned SKILL.md**, reporting `updated`; the standalone
`skill install` command refused the same kind of drift. Use the explicit
standalone projection commands for consumer reconciliation. A successful
lifecycle result alone does not establish preservation of local edits.
The lifecycle verification status also reported `unavailable` for the simple
Skill-only fixture despite successful projection; do not promote this to
semantic verification evidence.

A synthetic two-package local-registry fixture resolved a Relay-like root
flow and a string-form exact `=2.1.0` transitive shared flow, recording
`root-edge` and `public-chain` lock provenance. A Git-table-form dependency
inside the actual generated package did **not** enter that native transitive
graph. The pinned resolver reads `manifest.requires.packages` for child edges;
Git declarations are held separately in `requires.git_packages`. Therefore
neither manifest syntax acceptance nor successful installation of the root
proves acquisition of an immutable Git child dependency. The consumer admission
must provide the accepted immutable shared source explicitly and verify the
complete resulting graph; the VPM qualification records the supported adapter
path and its limits. Do not silently treat an omitted child as a successful
dependency closure.

A separate fresh disposable project containing
only its manifest, lock, complete slots and generated boot files passed offline
reinstall, native Skill projection and `vibe check` with new empty HOME/cache/
settings. This proves reuse of committed local closure, not cold offline
acquisition of a remote Git dependency. Native checking remains supplemented by
the repository's accepted-source/receipt/inventory verifier; see
[VibeVM maintenance and limitations](vibevm.md).

Neither native package resolution nor Skill projection publishes a package.
An external VPM distribution tag/registry publication and consumer adoption
remain separate governed actions. Consumers that commit the standalone/native
files can read them without VibeVM, cache, registry or network during normal
agent use.
