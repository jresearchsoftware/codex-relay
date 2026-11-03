# Task 63 Step 5: Bounded recovery with independent controller revision

Date: 2026-11-03. Authority: the current owner Step 5 direction in
[Task 63](https://github.com/jresearchsoftware/codex-relay/issues/63), with the
existing standalone/manual continuity and preflight Decisions. This is an
ordinary standalone result, without native admission or a Writer Outcome.
Task 63 and private Deployment Task 2 remain open.

## Accepted starting point and supported change

The starting `main` was `4f94cfe654bc766a76e70b6842ecd3cd8d08f88c`.
PR #196 was independently approved at
`1354b98df79349000658d83465098885f85745dd` and merged as
`27fa6a65362745da8113425e39faf65ba83352bb`; PR #197 was approved at
`ccd8fc9e14108f666beac340e2fa7baba52d5801` and merged as the starting
`main`. Their accepted publication, historical-disposition and installation
evidence is reused. Source acceptance did not recover the retained operation.

The remaining mismatch was specific: the original installed/backend target
could not read the later historical-disposition contract, while the ordinary
same-target recovery adapter correctly rejected a newer target. Step 5 adds an
explicit bounded path through the existing public installer. It uses the
corrected, independently identified staged controller to authenticate original
state and current eligibility before ordinary installation effects.

The continuation binds three visible identities: retained target, controller
revision, and desired product/configuration Git pair. Its supported shape has
the original target already installed, the corrected controller equal to the
desired product revision, the recognized deployment epoch/capabilities, and
unchanged environment, physical consumer and credential identities. These are
checked constraints, not a hard-coded b6-to-one-candidate table. Other shapes
stop; generic Task 119 recovery architecture remains separate.

The operator interface is documented in
[Git-managed installation](../git-managed-installation.md#strategy-compatibility-and-recovery).
`--authorize-install-recovery`, `--install-recovery-operation` and
`--install-recovery-target` select this path explicitly. They do not authorize
PROD, accept a candidate, change credentials or enable a dispatcher. Ordinary
same-target recovery without these flags retains its original behavior.

## Protection and interruption behavior

Before reservation, protected reads authenticate the original installed
manifest, reviewed source graph, Git-config receipt, configuration snapshot,
actual current consumer, credential roles, backend bytes, gate and original
service intent. The original installation snapshot and live consumer are
independent contexts; neither substitutes for the other. Missing original
service intent is a precise stop. An absent consumer-before backup is permitted
only with the other authenticated contexts, not inferred from current desired
configuration.

Under the existing host/pool locks and actual Writer mutex, the current
controller checks native Task dispositions and local live/publication effects.
Open abandoned routes require the existing protected exact-attempt
acknowledgement; an earlier in-memory classification is insufficient. No Task
Decision, terminal receipt or execution history is fabricated. Reopened or
changed authority, incomplete publication, live/unknown effects, changed
credentials, source/config drift and conflicting operations fail closed.

A protected same-UUID continuation receipt preserves original backend/gate
bytes, hashes and all selected identities. The existing gate retarget is
explicit. The original backend target is not rewritten to the new product SHA.
The normal staged installation and service/readiness checks remain in force.
Only verified final installation/configuration permits a byte-exact original
backend archive and removal of its active name. Independent final Git-pair
readback and same-operation gate/receipt verification precede admission resume.

Reserved continuation can be revalidated only against the same frozen binding.
Partial receipt or archive completion requires diagnosis. In particular, an
archive present while the receipt is still reserved now stops at initial
inspection, including a dangling archive symlink. This closes the interruption
window after archive fsync but before the backend-complete receipt marker;
retry cannot repeat installation effects before discovering the archive.
No automatic journal repair, rollback or generic partial-upgrade replay is added.

## Source and process/filesystem qualification

Linux qualification uses Python 3.11.2, Node 22.20.0 and Rust/Cargo 1.90.0.
The complete deployment/Ansible suite at
`5ec66bff0dec2cc0bbc51fb40642ca275d4eda35` passed: 2,325 tests, eight
conditional skips and 19 existing deprecation warnings. Six UID-dependent
skipped cases separately passed as the ordinary Linux user. Two disposable
Docker/systemd cases remain unexecuted because that manager was unavailable.

The Node suite passed in complementary ordinary/root runs: 1,286 passed with
seven root-only skips, and 1,288 passed with five ordinary-only skips. Together
they cover all 1,293 cases. Rust formatting and all 159 locked tests passed.
Three-consumer qualification, tracked candidate scanning and `git diff --check`
passed. Node/Rust sources were unchanged by the later Python correction;
final-head native CI is linked from the standalone PR result.

The final executable code is
`81e4d4d313f72228286bf73eb84facda2e282766`. Its focused bounded recovery and
SERIAL composite process/filesystem run passed all 40 cases without skips.
The final report head may add documentation after this code revision.

New targeted evidence includes actual old b6 source and current controller
processes, protected filesystem gates/records, missing before-backups, separate
original/live consumers, real flock ownership, changed desired digests, history
bytes/inodes, source/config/credential conflicts and interrupted publication,
receipt reservation, archive creation and journal removal. Backend tests execute
the actual Ansible tasks against isolated protected files; service calls there
are synthetic and do not claim real service qualification.

A separate private mount/network/PID namespace test exercises the real retained
SERIAL reader and current composite admission CLI. Its migration receipt is an
explicit synthetic fixture built from actual source, envelope, configuration and
gate hashes. App signing is real; HTTP/native observations are fixtures and no
external network or model execution occurs. With both original consumer-before
and pool-target snapshots absent, the real publisher creates the required
snapshots, preserves original SERIAL/config/gate/receipt/history bytes and
inodes, changes the consumer digest, and retains the same UUID and original
backend target. This is realistic composite process/filesystem evidence, not a
claim of a live SERIAL service migration.

Early full-suite failures came from disposable qualification transport: a
private source parent, inherited Git archive umask, and overmounting `/opt`
hid test source or made UID-separated fixtures inaccessible. The source was
moved to a root-owned `/srv` qualification tree with ordinary archive modes and
a byte-identical Node executable at a reachable disposable path. Owner home and
product permissions were not widened. The failed runs are not counted as PASS.

## Genuine isolated TEST recovery

The designated TEST namespace was exclusively allocated for this Step. The
prepared host and existing dedicated pool were reused. No PROD operation was
performed. TEST inputs were frozen Git fixtures using `test-qualified-exact`
through direct owner qualification; this is not fresh-host bootstrap or a
GitHub workflow/runner-policy proof.

First the ordinary public installer genuinely installed b6 as fixture setup
(538.1 seconds). This setup is distinct from the recovery proof. Six explicitly
synthetic historical records were added to the four existing TEST records,
using real native closed Task authority, to reproduce the accepted eight
completed / one not-planned / one route-switch pattern. No ready event, new
native admission, model execution or fictional terminal Outcome was created.
The protected failure fixture used a real original service snapshot, one fixed
UUID, installed b6, backend `RECOVERY_REQUIRED`, gate `recovery-required`, changed
consumer, and no original operation consumer-before backup.

The first candidate stopped before reservation with `CREDENTIAL_UNSAFE`: its
new checker incorrectly assumed every credential was root/Reviewer-owned.
The owning deployment contract actually places Codex tokens under their
configured runtime UID. The correction validates exact per-role configured
UID/GID, private modes and parent ownership, retains root-only Writer precedence,
and does not chmod credentials or widen access. Primary, repository and slot
token cases have real UID/GID tests. Original gate/backend bytes and shared-pool
state remained unchanged during this failed attempt.

After that correction, the frozen real TEST pair was:

| Input | Exact identity |
| --- | --- |
| Original installed/backend target | `b6edaaf4982df5b7dd6d56fd68b7ce7e34ccd7a9` |
| Controller and desired product | `5ec66bff0dec2cc0bbc51fb40642ca275d4eda35` |
| Desired private TEST configuration | `7388693061332bccc8f803d876c674c0c1629db1` |
| Retained TEST operation | `f8648705-8003-4ef6-9779-f28cbfbc047e` |

A pending-publication negative through the ordinary public install interface
stopped in `preflight-history` with
`INSTALL_PREFLIGHT_CONSUMER_HISTORY_REQUIRES_OLD_VERSION_RESOLUTION`
(48.38 seconds), `hostMutation=false` and `recovery=not-started`. Original
gate/backend bytes, installed b6 and shared-pool state were unchanged; no
continuation was reserved. The pending fixture was then resolved and a fresh
positive history baseline was recorded, rather than retrying unchanged failure.

The full positive bounded public install passed in 915.75 seconds using the
same UUID. Before cutover, readback proved old installed b6 and original backend
bytes still present, admission closed, and the reserved binding pointed to the
frozen corrected controller/final pair. Final readback proved installed Git
pair, backend archive exactness, absence of the active backend record,
continuation `complete`, gate open, and all ten history records byte/inode
unchanged against the positive baseline. Shared-pool process/state differences
were empty. No completed execution was replayed.

An ordinary same-pair install without recovery flags then selected only
`verify` / `post-check` and passed in 378.23 seconds. It did not run another
Apply. Reviewer PID, installed manifest/current/configuration, admission gate,
shared-pool state and all ten history bytes/inodes remained unchanged.

After the ten-record proof, only the six newly added synthetic records were
archived inside TEST with their bytes/inodes preserved. The four original
records remained exact. A fresh installed native read reported open admission,
no active/unknown work, four historical and zero actionable manual attempts.
Actual Reviewer and runner services were active/enabled; the Reviewer process
executable matched the installed manifest. The manual socket was listening,
recovery timer waiting, and recovery service inactive. Credential bytes/metadata
and shared-pool PID/start identities were preserved. All host/pool/Writer locks
were free and the exclusive TEST allocation was released.

The sanitized primary summary was read back directly and its SHA-256 matched
`744ff45d1314373cbe94b1985d780903464bd22a7dd78a1ccd27b23375977030`.
The protected evidence manifest hash is
`b5b4c6b9305e17f586c4a3c8d53b8e1d7fadac0717fe011a01b6a8bc34f5fcac`;
warning evidence hash is
`69296151ae2eb5323fdd61be3579c492b2555dd8699530cafc95055c77b09ae1`;
allocation-release hash is
`e502500eb1f5130036da542aa003ef7efa37b34079287fc95ec33ccb459f2db7`.
These hashes identify preserved private TEST evidence, not a public config copy
or a second desired-state authority.

The actual TEST installation is the frozen product above. Later final-source
changes add the failure-only interrupted-archive guard, its filesystem tests,
the independent original/live-consumer test, and documentation. They are not
misreported as another installed product revision; the full operation's
successful path is unchanged.

The genuine TEST runtime uses the ordinary current admission store. Its real
installation/readback is complemented by the isolated retained-SERIAL composite
test above; it is not presented as live SERIAL migration evidence.

## Warnings and remaining authority

Existing Python `crypt` and Jinja escape deprecations remain secondary warnings.
Ansible's TEST identity probe encountered its known private temporary-directory
EACCES and successfully used the standard fallback; no permission widening was
used. The credential-free Codex CLI CI qualification warned that PATH aliases
could not be created beneath `/tmp`; its explicit executable invocation passed.
Supported exact-head check/job annotation evidence is acquired with the final
standalone result. UI-only service/pre-execution banners are outside that API
scope and are not claimed inspected.

The native chat rename was called once with the complete requested title. Its
response and persisted readback were truncated at `independent contro…`; exact
full-title persistence could not be verified. This is a nonblocking UI warning.
Three implementation helpers were used; their checks are implementation
evidence and do not supply independent governance acceptance.

Private Deployment Task 2 Step 2 remains the prior protected observation, not
fresh PROD verification by this Step. The prepared private Step 3 handoff must
first obtain independent acceptance of this source, exact accepted product and
private configuration selection, fresh protected original-operation evidence
and explicit owner authorization for its effects. It must persist any required
existing Task-disposition acknowledgement rather than relying on the earlier
in-memory diagnostic. Unknown state or missing original service intent remains
a stop. It cannot reset history, replace the operation or rewrite the backend
target to force eligibility.

Deployment Task 3 retains final Git-managed Apply and private-dispatcher cutover.
This Step does not mutate PROD, change runner/ACL/credential policy, activate
dispatchers, merge, release, approve its own work or close either Task. The source
candidate stops for independent exact-head review.
