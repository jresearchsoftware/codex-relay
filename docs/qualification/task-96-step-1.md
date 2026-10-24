# Task 96 Step 1: native Full Access default

Authority: [Task 96](https://github.com/jresearchsoftware/codex-relay/issues/96),
[Phase 1 Decision](https://github.com/jresearchsoftware/codex-relay/issues/96#issuecomment-6381931184),
manual admission `run-40077692705`, starting head
`266ff2a4e10ed12f58affd8204b546fb3356aa0e`.

## Source behavior

New automatic launcher invocations select native `danger-full-access` rather
than `workspace-write`; the native noninteractive approval policy remains
`never`. The obsolete extra `.git` writable root and workspace-only network
option are removed. No permission hierarchy, Task-selected Unix identity,
credential grant or TEST application capability is introduced.

Slots retain outer Bubblewrap and their configured non-root UID/primary work
GID. Its read-only mounts now include native administrator `requirements.toml`
and legacy `managed_config.toml` when present, without mounting the rest of
`/etc/codex`. This closes an existing policy-visibility gap exposed by the new
default. Serial/legacy consumers without execution slots still launch directly:
their existing Unix permissions remain the host boundary, without a checkout-only
namespace. No universal Bubblewrap guarantee is claimed.

## Installed native launch qualification

On 2026-10-24, the opt-in
[installed qualifier](../../deploy/ansible/tests/qualify_installed_native_permissions.py)
ran against the actual installed TEST wrapper, launcher, pinned distribution,
runtime UID **978** and primary work GID **973**. The installed TEST product was
`60fa9febe16fe46b521908848eac78a54716cabe`; this qualification did not upgrade it.
Private mount/PID namespaces overlaid only the candidate native argv and
isolation module, a synthetic token and a disposable work root. The real
installed wrapper still selected Bubblewrap and the normal sudo identity.
The source checkout occupied the configured repository work-root path; writes
targeted its root `.agents`, not a nested projection fixture.

A deterministic loopback Responses service drove native `exec_command` in the
real **Codex 0.160.0** binary. No model, GitHub or new Relay execution was invoked.

| Case | Observed result |
| --- | --- |
| Root `.agents` present | Root Skill file and ordinary source written; Git add/commit succeeded |
| Root `.agents` absent | Root Skill directory/file created; source/Git operations succeeded |
| Effective native policy | Both native rollouts recorded `danger-full-access`, approval `never` |
| Unix identity and isolation | UID 978/GID 973 retained; mount, PID and user namespaces differed from the outer qualifier |
| Foreign file and actual Writer/Reviewer key paths | Open attempts returned `ENOENT`; no secret bytes read |
| Protected `/etc/passwd` write and root sudo | `EACCES` and denied, respectively |
| Child GitHub credentials | None of the checked GitHub token/SSH-agent variables present |
| Managed requirement excludes Full Access | Native configuration refusal, launcher exit 1, no provider request or tool execution |
| Containment | `reaped` for both successful cases and managed refusal |

Retained qualification report SHA-256:
`f7c79510e38e4ee7a7c82f2b54da1ce0c6bba0b6b5889a6dc505235129fbeeb0`.
Qualified native argv line SHA-256:
`f0cd4ac0b77bd84a01d0863abf9f06e326fa6990359c3c8299b2ddcb586edeaf`.
Qualified candidate isolation module SHA-256:
`2076042b4d67e5750841935f04551de96c8dd09117ebc189c7e1b01083e43713`.
The installed launcher SHA-256 remained
`4cb9cdf4dec9e8da9f04087439267759058b8c0f3463d9fbd569eff6e68854b7`
after the namespace exited. Installed settings, services and real tokens were
not changed. The source qualifier supplies the reproducible command interface;
the full report remains in the Task-owned qualification evidence area.

## Validation and limits

Native Linux source checks passed: Node **1200 passed / 4 skipped**; deployment
pytest **1430 passed / 371 skipped**; Rust **159 passed** and formatting clean.
After the admin-policy mount correction, Node and the **30-test** launcher/group
subset passed again. The official-release CLI qualifier passed with effective
Full Access/never policy. Its temporary-home PATH-alias warning is the documented
installer limitation; the direct pinned binary worked. Pytest deprecation
warnings concern existing dependencies/templates. Skipped root/platform tests
are not claimed as operational proof.

This proves the tested installed launch mechanism with the candidate delta,
not persistent adoption of the new default, live provider/model behavior,
an end-to-end admitted automatic Task or all serial/legacy host permissions.
Existing installations and previously admitted attempts keep their original
launch identity until separately authorized lifecycle action. The previous
root `.agents` manual route remains applicable on unqualified/unupgraded
installations. Source acceptance, installed adoption, independent acceptance,
merge, PROD Apply and Issue closure are separate. Task #181 owns the deferred
TEST application/repository capabilities.
