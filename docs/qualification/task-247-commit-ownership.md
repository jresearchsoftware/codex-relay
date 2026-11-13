# Task 247 Step 2: rejected local merge and preserved worker progress

## Established cause

[Task 247](https://github.com/jresearchsoftware/codex-relay/issues/247), manual
attempt `run-43499250589`, investigated Shared Governance Task 96 Step 2
[`run-43487871177`](https://github.com/jresearchsoftware/shared-governance/actions/runs/43487871177).
Accepted source and the required starting head were frozen at
`5df7e0093d93c5a55b996e34cc83359da6b22a3e`.

The rejection was **merge topology on the Issue implementation route**, not a
wrong author or committer. The protected original admission, runner journal,
primary diagnostic, fallback capsule, Writer reservation and surviving object
bytes were inspected through the existing owner-authorized WSL/SSH read-only
route. No original operation was replayed or changed. Raw diagnostic streams,
host details and credentials are excluded from this report.

| Fact | Primary observation |
| --- | --- |
| Admitted route | `target=issue`, automatic Issue implementation, Task 96 Step 2, existing PR 97 |
| Starting head | `56f4f7cd4d834af865a554906476366f240d6cab` |
| Admitted base | `0b72349f3ab0b2d88e836a6ba3d4fc675a87f75a` |
| First new commit | `c65d38160f3773cc7e2194713869a85b25b90e74` |
| Its parents, in order | starting head, admitted base (two parents) |
| Final new commit | `e4f554ea7872a55d404cc35192a21b6601c16ddd`, sole parent `c65d38160f3773cc7e2194713869a85b25b90e74` |
| Author and committer, both new commits | `jresearchsoftware-codex-writer`, `306851591+jresearchsoftware-codex-writer[bot]@users.noreply.github.com`, matching the installed Writer identity in all four fields |
| Worker return | successful semantic result; fallback records child exit 0, containment reaped, cleanup complete |
| Collection | final head above, `clean=true`, `preserved=true`; subsequent progress validation failed |
| Publication | no publication intent, published head or final head; immutable BLOCKED Outcome 6862278423 on PR 97 |

`validateCommits` walks the first-parent chain. The first commit passes identity
and first-parent continuity, then fails the existing
`e.target !== 'pull_request'` predicate in the multi-parent guard. The admitted
Issue route has no remediation integration-merge permission even though it binds
an existing PR and its Task Decision requests source reconciliation. The main
commit's human/GitHub identity is not the failed predicate: main ancestry is not
part of the worker-owned first-parent identity loop.

The current installed reviewed source reports the same `5df7e009...` revision;
the inspected validator has the same merge gate. This does not infer a runtime
identity from a requested model. The original parent profile was Terra/medium;
this investigation's requested profile is Sol/xhigh. Actual model/effort values
are unavailable from the inspected runtime observations.

## Preservation and independent local reproduction

Before running Git, bounded regular object bytes were copied read-only from the
original checkout into a private, execution-owned local snapshot. Seventy-two
object/pack files were preserved. No worker config, hooks, refs, index, alternates
or other executable Git metadata were imported. A fresh bare repository received
only those bytes; trusted Git disabled global/system config, hooks and replace
objects. `git fsck --full --no-reflogs` passed for the original tip; one dangling
tree was reported, with no missing or corrupt objects.

Evidence SHA-256 values:

- primary bundle: `b9396c528e5986004ee1461acf7e88ba8ba60606a49feefff19917c84beef8f0`;
- fallback capsule: `502d0d77215f02e85fa017b12529a1e17936ded2c14bff1b2df069a4b8b6c247`;
- runner journal: `3a96758620cd0d3b80abd5c0c81c6d544e6e599ee53657681bd179ff6d4b8191`;
- local bounded object snapshot: `1c9e075f08f87e3453c38b4387ce9973d3b7ead75a94ae202b6f0e5e219fa1ea`.

The actual unchanged validator reproduced `COMMIT_OWNERSHIP_INVALID` on the
original tip. A **local-only feasibility probe** used the exact original final
tree `40762e62d767aea224dd5a1f04a8f011bbffcb95`, the original starting head as its
sole parent and the correct Writer identity. It passed the same validator,
including all introduced-blob secret/path/mode checks, with one commit and no
integration base. Its tree was byte-identical to the original final tree. This
is recoverability evidence, not a published revision or an accepted consumer
result. Neither original commit was rewritten or pushed.

The worker's claim that useful commits exist is therefore verified. Its claimed
consumer test results and semantic correctness are not independently accepted by
this investigation. The journal's complete observation says the checkout was
clean at collection; the worker's earlier `.codex-sandbox` residue claim does not
override that later observation. No residue was removed during diagnosis.

## Small source correction

The guard correctly rejected the merge. The actionable Relay mismatch is that
the Issue worker instruction says not to merge PRs but does not explicitly
explain the local single-parent restriction, whereas remediation receives an
explicit local-merge exception. The correction states the already-enforced
Issue history contract, including existing-PR continuation: ordinary single-parent
commits from the admitted head, with accepted base changes reconciled as source
edits; no local merge, rebase, amend, reset or history rewrite. Unsafe source
reconciliation must preserve work and report its concrete boundary.

This adds no permission, control, operator action or status and changes no
ownership, collection, trusted import or publication validator. The owning
controller contract is updated in the same change. The existing user manual's
route/permission contract remains unchanged, so no product Skill release or
consumer projection change is required. General causal diagnostics remain
owned by Relay Task 244; earlier admission failure remains owned by Task 243.
The `small-improvement` scan found Issue 248, whose broader capability-discovery
scope is excluded from this incident correction.

Regression coverage couples `executeCodex` with real collection and Writer
publication on an existing PR: accepted main behavior is reconciled through two
ordinary commits without changing main. The negative incident-shaped fixture
uses divergent main, the exact allowed-identity merge shape and an ordinary tip;
it verifies all four identity fields match and that publication still rejects
with zero pushes. Existing foreign-identity, wrong-ancestry, hostile-metadata,
ambiguous-observation and remediation integration tests retain their gates.

Routine CLI maintenance checked the official latest stable release on
2026-11-13: `rust-v0.169.0`, published at `08:37:05Z`. It is the same candidate
already assessed in the accepted Task 243 maintenance section of
[CLI integration](../codex/cli-integration.md#task-243-routine-maintenance).
The unresolved project-trust compatibility change remains applicable; the
qualified pin stays at 0.167.2. No CLI upgrade or installed-runtime change is
claimed.

## Safe consumer continuation

The original operation is terminal: its journal has the immutable BLOCKED
Outcome, reaped containment and no reserved or successful source publication.
`runAttempt` returns/throws from that terminal record before any new collection
or publication. It must not be replayed to publish different objects, have its
Outcome replaced, or be treated as an unfinished push to recover. Live PR 97
readback still showed the original starting head and Draft/open state.

After independent disposition, the Shared Governance owner can authorize a
**genuinely new native Step 3** continuing the full Task 96 on the same PR 97 and
starting head. Its authority should explicitly permit reusing the preserved
Step 2 source snapshot as input. Import only bounded object bytes into a fresh
trusted repository, verify original identities and snapshot, review the source
delta and create ordinary linear task-owned commits from the live admitted head.
Revalidate current source/Task Decisions, all consumer qualification and exact
PR/ref state before publication. The local proof shows the previous work can
be reused without another full implementation replay; it does not waive those
checks or authorize this transfer/publication. Preserve the old commits,
reservation, Task Decisions, Step 1 result and Step 2 Outcome as provenance.

No consumer relaunch, consumer branch/PR mutation, original-operation recovery,
deployment, Apply, service change, shared TEST claim or Issue closure occurred.
Task 247 remains keep-open for independent source/incident disposition and
applicable consumer qualification. This Task does not grant the future consumer
admission or source-acceptance authority.

## Warnings and qualification limits

The original Writer Outcome, routing run/job and its complete check-suite
annotations were inspected through supported APIs. The sole check is `route`,
whose annotation reports process exit 1. The known orchestration failure and
unpublished result remain material; this source correction does not make the
original Outcome green. The original worker validation claims include a weak
GLIBC warning and skipped privileged installed-runtime proof, which must be
dispositioned during consumer qualification. This manual admission's routing
check had no annotations. UI-only service/pre-execution surfaces are outside the
supported automated scope.

Linux checks use an independent native-filesystem source copy, temporary root
and Cargo target belonging exclusively to this attempt. No active runner slot
or another Task's execution resources were reused. Source tests and the local
object probe do not qualify a new installed worker, sudo boundary, credentials,
provider, consumer semantics or production service. No live model call was made.
One implementation helper supplied source analysis and regression tests; it does
not supply independent acceptance. Native title readback is abbreviated, so exact
full-title persistence is unverified.
