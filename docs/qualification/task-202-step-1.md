# Task 202 — standalone manual source qualification

Date: 2026-11-04. Authority: [Issue #202](https://github.com/jresearchsoftware/codex-relay/issues/202).
Accepted starting source: `3386298` (`main`). This is the owner's standalone
manual execution, not Relay admission, a native Step or a Writer Outcome.
The chat navigation title is `Task 202 — Step 1 — Runner self-updates` and its
persisted readback matched. Three implementation/research helpers were used;
they do not supply independent acceptance.

## Result and evidence scope

The product now uses one checksum-bound bootstrap distribution and leaves
ongoing software updates to GitHub. Registered/prepared numeric versions are
retained, including native versioned-directory links. New registrations omit
`--disableupdate`; existing registrations require the explicit stopped-only
settings migration. See the [operator runbook](../runner-self-updates.md).

The current public official release was `v2.338.2`, published 2026-10-26.
Its linux-x64 archive was actually downloaded into disposable WSL Debian
storage; SHA-256 matched
`baebf204307bac6193480852732f0aba2ae97b6c5597c244f4d5558390147c40`.
The source archive validator accepted it and its real non-root
`Runner.Listener --version` returned `2.338.2`.

The official upstream shell qualification used
`python3 scripts/qualify-runner-self-update.py` on native Linux as an ordinary
UID. It verifies four upstream source hashes before executing the exact
`update.sh`, `run.sh`, `run-helper.sh` and `safe_sleep.sh` shells. Seven synthetic
runner namespaces (six General and a distinct Production fixture) transitioned
from `2.336.0` to `2.338.2`; absolute versioned `bin`/`externals` links, wrapper
restart and a synthetic accepted-job marker were observed. Settings, credential
fixtures and prior work bytes stayed unchanged. Failure and SIGKILL at the
second link produced the expected incomplete frontier; explicit stopped-sandbox
link repair restored the wrapper/job path. Listener binaries, payloads and job
transport in this proof are synthetic. The real official archive/version proof
above is separate; neither proves a native GitHub server update negotiation.

## Seven real systemd migration boundaries

A separate one-off harness created a disposable local Debian 12 systemd
container with six General units sharing UID 996 and one Production unit under
UID 995. Docker was 29.8.1; systemd was 252.39. No credentials, host directories
or production services were mounted. The unmodified helper source SHA-256 was
`2d63b0e770ed6bd8300f8099963adec17aeee00f7c7b6a6e41e908d3ed339a20`.

The harness invoked the actual helper through subprocesses using real root,
systemctl, `/proc` and cgroups; none of these boundaries was monkeypatched:

- Migration of an active target failed with `RUNNER_SELF_UPDATE_STOP_REQUIRED`,
  preserving bytes and inodes.
- Each of seven targets was stopped and migrated while the six peers stayed
  active. Both `.runner` and `.runner_migrated` changed only `disableUpdate`.
- IDs, other settings fields, ownership/mode, credentials/RSA, configuration,
  work bytes and credential/work inodes were preserved. Same-identity replay
  was a no-op and left the target stopped; the helper never starts services.
- All seven fixtures were subsequently started and checked, then stopped.
  The container was removed and absence verified.

Service processes in this proof were `sleep infinity`, not GitHub Listeners.
The ordinary migration regression suite additionally injects failure between
the two settings replacements and proves same-identity completion without
credential replacement, plus malformed/conflicting settings and path/process
refusals. Ansible regressions exercise old/new native versions, active service
preservation, unsafe links, registered corruption and bootstrap validation.

## Read-only live observation and outstanding operations

PROD observation read service metadata, selected non-secret registration fields
and version lines from existing diagnostics. It did not invoke the Listener
version probe (which can write diagnostics), change files, stop/start services
or call mutating GitHub APIs. All seven services were active; existing diagnostic
version evidence was `2.336.0`, and both settings files had `disableUpdate=true`:

| Role | Registration name | GitHub runner ID |
| --- | --- | --- |
| General 1 | `codex-relay-general-runner-pool` | 74 |
| General 2 | `codex-relay-general-runner-pool-2` | 75 |
| General 3 | `codex-relay-general-runner-pool-3` | 76 |
| General 4 | `codex-relay-general-runner-pool-4` | 77 |
| General 5 | `codex-relay-general-runner-pool-5` | 78 |
| General 6 | `codex-relay-general-runner-pool-6` | 79 |
| Production | `codex-relay-runner` | 55 |

These are observations, not proof of idleness, current job acceptance or
supported running versions. Refresh them at the operational boundary.

Material evidence gaps and disposition:

- Organization runner-list/download APIs returned HTTP 403 with existing owner
  CLI credentials. No scopes were expanded. The installation-specific offered
  release, remote idle/job state and effective runner-group ACLs remain
  unverified in this session. Latest public release is not an offered-version
  receipt because rollout is progressive.
- The dedicated remote TEST hostname did not resolve and a bounded direct-IP
  SSH attempt timed out. Its allocation, App permissions and group/workflow
  bindings could not be inspected; no token was obtained and no remote TEST
  registration was changed. The real GitHub self-update/session proof remains
  outstanding. Local settings sufficiency is an upstream-code-backed inference,
  not observed server behavior.
- An interrupted upstream update can strand a missing link and leave the unit
  offline. There is no guaranteed automatic rollback. The runbook requires
  diagnosis and a stopped, provenance-bound software/link repair; an expired
  previous version is not an acceptable operational rollback target.

Required owner-controlled continuation: independent exact-head source review and
authorized merge; restore/verify the dedicated TEST boundary for real server
negotiation if needed before PROD; separately authorize and trigger the private
Git-managed PROD Apply for the accepted product and bounded sequential migration
maintenance. Finish the controlling Apply first, migrate another idle General
Runner while verified control-plane capacity remains, then the other General
Runners and separately Production. Preserve all workflow-ref/group restrictions.
Observe supported versions, both effective settings, services/registrations and
actual public routing/recovery and private lifecycle accepted-job handoff for all
seven. Do not stop or modify the active control job's runner. Source success
does not authorize those operations or satisfy Task closure. Issue #202 stays
open; Task #203 and unrelated Task #63 qualification are not gates here.
