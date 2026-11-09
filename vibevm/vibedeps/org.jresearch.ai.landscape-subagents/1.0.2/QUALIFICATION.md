# Development qualification

## Current version

Version **1.0.2** removes private producer provenance and keeps the accepted
passive delegation contract. Portable checks cover this version's manifest,
complete package inventory, conditional boot, policy/profile invariants, MIT
notice, package-local links and public citations. Producer-only qualification
retains full canonical source equivalence and private acceptance provenance.
Exact current validation results belong to the producer's review record; older
native evidence below does not qualify this version's different bytes.

## Historical source-candidate checks

The following is a sanitized historical record of the original **1.0.0** source
candidate qualified on **October 16, 2026** in an isolated checkout. Later source
versions include MIT licensing and different payload bytes. These results must
not be claimed for 1.0.2. Private Task, branch and source identities remain in
producer-only records.

### Source checks

`python -B packages/landscape-subagents/tests/check_package.py` passed all
**7 checks** on Windows Python 3.12. The checks cover the exact passive manifest,
short conditional boot, complete accepted policy/runtime projections after the
documented transport substitutions, all package-local Markdown targets, the
10-file payload allowlist and isolation of shared files from the accepted SHA.
`git diff --check` passed. Root policy, evidence, instructions, dependency files,
native materialization and workflows were unchanged.

A separate read-only helper compared the prose with the full accepted source
and linked adoption/runtime documents. It found no material semantic defect.
This was a contributor self-check, not owner or independent governance acceptance.
The runtime profile matrix was retained in full. General recommendation scope
was reconciled without a cross-package dependency or shared edit.

### Native local fixture

Executed the committed `tests/qualify_local.py` from Debian WSL, Python 3.11,
using the existing static Linux x86_64 VibeVM **1.0.7** musl binary. Its live
version and SHA-256 matched
`20d111df02eb28040ef4cb766bfcb0bde8ff4427b031f88f33eacb3711c3e240`.
No alternate binary was downloaded.

The script copies the candidate into an ordinary temporary local registry and
creates a separate consumer with an exact `=1.0.0` requirement. All native
commands use `--offline`; settings and user-config paths are invocation-local
inside the temporary fixture. No producer installation is performed.

| Check | Observed result |
| --- | --- |
| Offline local-registry install | `ok=true`, `complete=true`; exactly the intended flow materialized. |
| Installed bytes and lock | All 10 package files matched source SHA-256 values; the only additional slot file was native `.vibe-slot.toml`. Schema-7 lock retained exact coordinate, version, local-registry source and content identity, with no transitive dependency. |
| Root and boot route | Human-owned non-adoption/authority sentinel preserved; generated AGENTS/CLAUDE/GEMINI and INDEX route resolved to this slot's boot. No stock STATIC policy or native Skill appeared. |
| INDEX kind | Native 1.0.7 emitted **static**, despite declared `link = "dynamic"`. The short boot's explicit-adoption condition remains the JIT boundary. |
| Offline `validate` | Successful `validate` lifecycle step; zero contributions and notices. This is a passive no-op lifecycle, not execution of a behavioral test. |
| Native `check` | Zero errors, warnings, informational diagnostics and findings. Every stdout JSON document was parsed and its relevant success/completion fields checked. |
| Repeat install | `unchanged=true`; package identity, payload and human-owned instructions preserved. |
| Offline retained-slot `reinstall` | Successful, no hooks; identical payload, package identity, generated routes and human-owned authority after regeneration. Generated lock timestamps are not treated as stable payload. |
| Isolation | Consumer manifest and producer package bytes unchanged by native commands; temporary registry, settings and consumer removed at test completion. |

The fixture's native content hash depends on all candidate bytes, including
this evidence file and the test scripts. Its value is reported by the test and
in the producer-only exact-candidate record; it is not a distribution receipt or
an accepted/published artifact identity.

## Limits and owner handoff

No end-to-end model-visible instruction loading, actual client configuration,
observed child profiles, useful delegation, consumer adoption or runtime saving
was qualified. The retained Codex CLI 0.160.0 runtime evidence remains a dated
source inspection; its source tests were not executed here. Package source and
materialization checks do not establish any of those runtime claims.

Only Linux x86_64 native local-registry transport through Debian WSL was tested.
Native Windows/macOS, direct-path or Git/remote-registry package installation,
distribution layout and hosted immutability remain unqualified. These historical
checks did not qualify remote transport or publication.

For that historical candidate, license/rights, distribution destination and the
future separately authorized publication path remained owner decisions. No
publisher machinery, remote tag, release, distribution repository, consumer
update or merge was implemented.
The producer review record retains the exact source head and checks for owner
review. Passing checks and helper findings grant no merge or publishing authority.
