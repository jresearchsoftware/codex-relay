# Task 217 — Step 1 qualification

Authority: [Task 217](https://github.com/jresearchsoftware/codex-relay/issues/217),
admitted manual attempt `run-42464714069`. Starting accepted source:
`6fb8fc447fe56d9e5d67dd539d8aad289faf0666`. Source work uses the independent
`codex/task-217` worktree; native Linux validation uses a separate clone and
temporary resources dedicated to this run. No shared execution slot is reused.
Subagents were not used. Requested profile is `gpt-6.1-sol`, effort `medium`;
actual backend model/effort telemetry is unavailable.

## Scope and control cost

The concrete failure is concurrent or manually ambiguous ownership of one shared
TEST contour (Task 215). The accepted Task requires an atomic marker and explicit
busy/recovery behavior. One persistent file with short Linux `flock` operations
is sufficient: no lease process, queue, database, scheduling or controller
admission changes. Only TEST users claim and release; ordinary source Tasks
have no added action. Recovery retains an explicit stopped-holder and usable-TEST
confirmation because claim-command PID/age cannot establish execution completion.
The marker coordinates already authorized users; it adds no privileged transport.

## Bounded exercise on the existing shared TEST host

The existing Task 76 TEST configuration supplied the host and isolated
`codex-relay-test` namespace. Existing owner SSH transport was usable. The
exercise created only the shared marker and standalone candidate helper inside
that namespace and a run-specific temporary harness. It did not change TEST
services, credentials, configuration, installed source pointers, GitHub resources
or PROD resources. The pre-existing TEST Reviewer was active before and after.

The helper's SHA-256 is
`69028d127d426667bd1b2e196f6ef886971533c3615f42cfd5b009bce0f01e2d`.
The marker is the regular file
`/var/lib/codex-relay-test/test-environment.lock`, root/TEST-group, mode `0660`.
The reachable helper is
`/var/lib/codex-relay-test/test-environment-lock.py`, root/TEST-group, mode `0640`.
The exercise demonstrated:

- Task 217 first claim succeeded; a synthetic competing Task received BLOCKED
  with the same recorded holder.
- A foreign execution's unlock was refused and preserved the holder.
- Read-only TEST use and verified active Reviewer handback released ownership.
- Bounded work returning both 0 and 7 ran cleanup/health verification, released
  ownership, and preserved the work exit code.
- A subprocess that only claimed and exited left visible ownership. Since the
  harness knew it had launched no TEST work, stopped-holder confirmation and
  health verification supported exact-token recovery.
- The existing non-root TEST service identity could claim/run/release through
  the same shared file. Final status was FREE.

This is a real shared-marker exercise, not a real automatic Relay Task or proof
of broader automatic TEST access (Task 181). No new native admission was created.
Recovery relies on truthful execution/TEST evidence; age alone is never proof.
The candidate helper is available in TEST before product acceptance under the
standing sandbox authority; staging is not product integration or PROD Apply.

## Linux checks and execution environment

Focused tests cover separate-process contention, exact execution release,
stale-token recovery, killed-wrapper retention, old timestamps, handled work
and launch failures, failed/unavailable cleanup, and unsafe/damaged markers.
All 13 focused cases passed on native Linux.

The workstation WSL shared `/tmp` was root-owned `0755`, which prevented ordinary
UID temporary creation. The initial Node run failed for that environmental
reason; it passed with this run's own TMPDIR (1287 passed, 7 skipped). Some
deployment tests explicitly use `/tmp`, so their first run had the same EACCES
and was interrupted after diagnosis. Qualification was moved into a private
mount namespace with this run's own temporary directory mounted at `/tmp`;
the shared host directory and other Tasks were untouched. This environment
adjustment is test transport, not a product source change or repaired host state.
