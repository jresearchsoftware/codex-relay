# Task 164: automatic worker filesystem and collection diagnosis

Authority: [Task 164](https://github.com/jresearchsoftware/codex-relay/issues/164),
manual Step 1, `run-39444134832`, starting head
`1c7d57287fadac236bfaa3d2be6276956510705e`.

## Retained original evidence

Read-only inspection of Task 106 automatic `run-39419663028` confirmed the
original journal, primary/fallback diagnostics and Writer record still match
their previously acquired SHA-256 values:

| Record | SHA-256 |
| --- | --- |
| Journal | `13885e406651ecd0f55584b3cbf94714d897aea3a7a086d5c2ad2c94c91f23a5` |
| Primary diagnostic | `487ce962a0e0cfbb7c9a0d9df2e4d1b86caebf87f730f6c8340b315d23c938e0` |
| Fallback diagnostic | `c1cb64ef382db1b0a747fc8a2fcc41235f09acc2d75b4e50a242a44e83d9278f` |
| Writer record | `38722711f2377857d370f73b7128ea17e3560fca7fcac3a77e9c46345aba8cc2` |

The journal records returned worker status `blocked`, child `started` and
containment `reaped`. Progress and publication intent are absent; no head was
published. The original Outcome remains
[BLOCKED](https://github.com/jresearchsoftware/codex-relay/issues/106#issuecomment-6290883522).
The later [read-only recovery inspection](https://github.com/jresearchsoftware/codex-relay/actions/runs/39433416801)
correctly returned `RECOVERY_EXECUTION_NOT_PROVEN`. No replay or recovery was
performed here, and Task 106's separately completed source result is unchanged.

Raw Git-object inspection, without running Git against worker metadata,
confirmed the retained ref and hash-valid commit
`5ba30450d68c302ba7d2534a6dc1d5723786399f`, root tree
`61002bb7fa07a7933100653c402bf49aa45f3f6c` and first-party slot marker blob
`4854dc8a3f02130d7ea3f67b5860434fa09e4e49`. The marker's worktree bytes match
that blob. These are surviving source objects, not Writer execution provenance
or proof of all original validation claims.

## Two distinct failures

The retained tracked first-party `.vibe-slot.toml` has Git mode `100644`, but
filesystem mode `0600`, worker UID 983 and shared GID 979. Actual collector UID
985, primary GID 982 and supplementary groups 979/982 cannot open it:
`open` returns `EACCES`. Running the original accepted collector read-only under
that identity reproduces `TRUSTED_GIT_FAILED` / `GIT_LOCAL_FAILURE` at
`worktree-observation`. It writes only a disposable trusted snapshot inside the
Task-owned TEST evidence area. Original bytes, metadata, refs and records are
not repaired. The historical diagnostic did not retain a filename, so the
specific historical first failing syscall is unavailable; current tracked-byte
access failure and reproduction establish the collection fault boundary.

The worker's `.agents` `EROFS` claim has a separate native sandbox explanation.
TEST's actual installed Codex 0.160.0, under its ordinary runtime UID, permits
ordinary checkout and explicitly allowed `.git` writes while the root `.agents`
path has a read-only mount and returns `EROFS`. A nested disposable fixture
path remains writable. The Relay outer mount binds the checkout writable;
the inner native policy imposes the protected path. Historical per-command
worker mount evidence was cleaned with its private home and is unavailable;
the pinned TEST reproduction does not invent that original observation.

[Task 109](https://github.com/jresearchsoftware/codex-relay/issues/109) is a
related cross-UID/private-file precedent, with a different original attempt and
file. It does not supply authority to publish this candidate. Other managed
runners using distinct worker/collector UIDs and explicit private source modes
are vulnerable to the same access failure. Their individual retained runs were
not inspected; no fleet-wide failure or remediation is claimed.

## Remediation and qualification scope

Collector acquisition now preserves OS code/syscall and a safe operation-side
category, including effective collector UID/GID in protected diagnostics.
Snapshot-write failures are distinguished from checkout reads. Terminal
Outcomes display the OS code without presenting collector evidence as launcher
evidence. Complete observation, source permissions, ignore handling, trusted
object import, replay suppression and Writer provenance remain unchanged.

Worker instructions explain reconciliation of known public task-owned files
through the existing shared group, because explicit tool modes defeat umask.
Operator guidance documents root `.agents` as a supported sandbox boundary and
the authorized manual maintenance path. No sandbox bypass, recursive permission
repair, privileged ordinary collector or new owner gate was introduced.

Targeted native Linux checks passed: 119 tests with two root-only skips; the
separate disposable root fixture passed all 11 observation tests, including
actual cross-UID access and a private read-only bind mount. The optional
`scripts/qualify-worker-filesystem.py` provides a credential-free pinned CLI
probe. Installed-to-target, automatic publication and complete candidate checks
are separate evidence recorded by the canonical Task Outcome after execution.

## Remaining boundary

This repair does not grant an automatic worker write access to the protected
root `.agents` path. Changing that sandbox boundary requires separate owner
authority. A nested fixture proves only that fixture; normal automatic work
can read already prepared project guidance. Source/TEST proof does not qualify
PROD installation, service restoration, independent acceptance, merge or closure.
Task 164 remains open for its stated independent review and owner disposition.
