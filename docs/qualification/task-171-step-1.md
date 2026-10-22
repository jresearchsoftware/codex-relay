# Task 171: generated public package collection

Authority: [Task 171](https://github.com/jresearchsoftware/codex-relay/issues/171),
manual Step 1, `run-39598256223`, starting head
`1d69995364f371321369110253833507970075fc`.

## Incident evidence and its limit

Read-only inspection of the original consumer attempt confirmed a returned
worker, `child=started`, `containment=reaped`, no collected progress and
`TRUSTED_GIT_FAILED / GIT_LOCAL_FAILURE` at `worktree-observation`: syscall
`open`, OS code `EACCES`, operation category `source-directory`. The retained
diagnostic identifies collector effective UID 985 and GID 982. The installed
source is `61bfe2be5bdf5632449cd7f544c6c5ba4d4146d4`.

The installed worker account has UID 983, primary GID 980 and supplementary
work GID 979. The collector account has UID 985, primary GID 982 and
supplementary work GID 979. Checkout/repository ancestors are collector-owned,
group 979, mode `2770`. The launch implementation invokes `sudo -u` without
selecting the configured work group, then sets umask `0007`.

The public package subtree currently contains eight directories and 21 files,
all owned by worker UID 983 with work GID 979; directories are `2770` and files
`0660`. The owner has already corrected the incompatible group. No pre-repair
metadata inventory or historical creator syscall is available in this Task.
The charter's original incompatible-group observation is owner-supplied evidence;
the current metadata is not a reconstruction of those historical values. The
original generator's precise create/copy/rename sequence remains unavailable.
No original content, metadata, journal, Outcome or publication was repaired here.

## Reproduced defect and correction

A setgid checkout and a shared supplementary group do not guarantee the group
of imported inodes. A worker-created tree staged under a non-setgid parent uses
the worker's primary GID. Renaming that tree into a setgid checkout preserves
its inode, group and mode. With explicit `0770` directories and `0660` files,
the collector cannot traverse the runtime-private group. Umask cannot change
that group or repair a renamed tree.

An isolated Linux TEST reproduction uses actual worker UID 978, private primary
GID 974, work GID 973 and collector UID 980, private primary GID 976. It creates
eight directories and 21 files in staging, then renames the public tree into a
setgid destination. The old primary group reproduces collector `EACCES`;
selecting primary GID 973 makes the unchanged public modes collector-readable.
This proves the mechanism and the launch defect, not an unavailable historical
generator trace.

Execution and cleanup now share a fixed sudo specification. A slot's already
configured, digest-bound `workGroup` is selected as the process primary group
with `sudo -g`; the root-owned sudoers grants only its configured runtime users
and group. The launcher verifies the numeric primary group before reading its
token or starting Codex. Unix account settings are unchanged. This also supplies
the intended group to the isolated user namespace instead of relying on
supplementary membership alone.

Serial consumers without slots may explicitly select top-level `workGroup`,
equal to deployment `environment.codexWorkGroup`. Its omission preserves the
historical serial ABI and digest; adding it uses normal configuration/admission
reconciliation. Existing slot installation digests and immutable attempt
bindings are preserved. No collector elevation, permission sweep, world-readable
fallback, new recovery service or routine manual repair gate is introduced.

## Qualification and remaining boundaries

The new native root regression runs an actual unprivileged producer and the
real trusted collector under separate UID/primary/supplementary GID credentials.
It covers nested/bulk public package output, explicit modes, atomic replacement,
staging/rename, collector denial and successful observation, and unchanged
metadata after observation. Unknown non-ignored `0600` files and `0700`
directories still fail explicitly; ignored private caches stay excluded and
private. The original Task 164 tracked-`0600` and read-only-filesystem diagnostic
regressions remain intact and pass alongside it.

Rendered installed-launcher tests exercise real group lookup/mismatch before
credential reads, the credential-free runtime probe, exact sudoers grants,
serial omission and primary/secondary slot behavior. Genuine installed TEST
automatic execution/publication and complete final candidate validation are
reported through the canonical Outcome with their exact identities and limits.
These source tests alone establish neither operational end-to-end success nor
PROD installation.

Explicit private modes, externally imported foreign ownership, and deliberate
group changes remain outside default inode-group prevention. Non-ignored
unreadable content still blocks complete observation. The separate native root
`.agents` read-only boundary is unchanged. Original consumer recovery remains
independently owner-gated and is not replayed by this Task.

The latest [Task Decision](https://github.com/jresearchsoftware/codex-relay/issues/171#issuecomment-6322918653)
limits the incidental default-profile proposal to the two existing configuration
string replacements (`gpt-6.1-sol` and `medium`). The owner controls later Apply;
profile transition implementation and installed PROD readback are outside this
execution. This does not change an immutable admitted profile.

## Step 2 continuation qualification

Step 2, `run-39648905968`, starts from `c4963906a9ebc6017e8bb19140e0a4efaabc0b66`
on the same PR. Retained TEST run `39607717441` has a verified Writer published
head `60afec689134eede1b98a72827cf7714f20ee6b0`, no pending publication intent,
and a contained successful worker; its runner journal stopped before recording
progress. The historical generic `PR_AUTHORITY_CHANGED` diagnostic does not
retain the original list/detail operands, so their exact historical values
cannot be recovered from that record.

The post-push PR lookup required identical heads from independently propagating
GitHub list and detail responses. A real-Git broker regression reproduces the
failure with either response lagging at the exact predecessor after Writer's
single verified push. Both tests fail against the starting source and pass
with the bounded transition allowance. Foreign heads, base/identity/linkage
changes and Step/title disagreement remain blocked; Outcome and Ready retain
their exact published-head checks. The canonical Outcome records the installed
candidate and new genuine automatic TEST admission/publication evidence.

The previous executor also treated the disposable fixture's cross-mount rename
failure as requiring a new owner layout permission. Existing TEST authority
already allowed changing its owned fixture staging; no product sandbox change
was required. The subsequent stop on an undiagnosed post-push failure left safe
source diagnosis unfinished. These are execution-policy misapplications, not a
missing shared protocol or a demonstrated need for new governance machinery.
Historical attempts and Outcomes remain unchanged.
