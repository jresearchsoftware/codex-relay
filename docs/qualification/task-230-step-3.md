# Task 230 Step 3: bound pre-dispatch finalization

Authority: [Task 230](https://github.com/jresearchsoftware/codex-relay/issues/230),
[trusted owner correction](https://github.com/jresearchsoftware/codex-relay/issues/230#issuecomment-6741057122),
[continuation briefing](https://github.com/jresearchsoftware/codex-relay/issues/230#issuecomment-6741945328).
Attempt: `run-42630817086`; source PR: 233. Required starting head verified:
`a8710b6c939eec99492d54fd1b26a7655f968c94`; admitted base and frozen accepted
source guidance: `88126990b9c7b66d1255ab498294f5a5950f26df`.
The separate native Linux checkout and temporary resources belong to this run.
The incidental Windows checkout and earlier Task worktrees were left unchanged.

## Evidence and scope

Step 2's [protected inspection report](task-230-step-2.md) remains the evidence
for the original record. This Step did not independently re-read the host and
does not claim that its protected state is unchanged today. Current GitHub
readback confirms the original routing run `42608866374` is completed/failure,
`run_attempt=1`, with owner actor/triggering actor and the expected routing
workflow. The original inner exception remains unavailable: the failure boundary
was Step projection after reservation, before ready consumption; no particular
HTTP, network or JavaScript exception is claimed as the historical cause.

The remaining Relay-owned defect was the lack of a safe way to retire this
specific durable pre-dispatch reservation when no terminal runner journal could
exist on its normal path. Diagnostics alone did not repair it. Step 3 supplies
that mechanism, preserving the Step 2 exception capture and replay guards.

The finalizer uses the durable ordering of `admit`: the ready-consumption intent
and receipt precede its return, which precedes controller preparation/dispatch.
It accepts only a first-run failed native label admission with the exact partial
record and no projection-complete/consumption/execution/publication progress,
no journal or checkout, and matching live authority, event, ref and PR. It holds
the Writer mutex and original controller lock and rechecks before one atomic
record write. Absence of processes alone is never its proof.

A fresh owner comment binds the complete original record digest, original
authority digest, repository, run/attempt, Step, event, slot, branch and head.
The administrative receipt preserves every original field and explicitly does
not create worker execution, completed containment, terminal journal or Task
Outcome. Native metadata and the ready label are untouched. Repeated delivery
returns the same receipt; altered bindings and later contradictory evidence
fail closed. Inventory/drain recognizes this separate proof. A genuinely new
owner command retains the original reserved Step in history and allocates the
next Step without forced label repair or reusing the original event.

## Operator-ready original-attempt procedure

This is the concrete protected handoff, not evidence that recovery was executed.
The [owning recovery contract](../../controller/README.md#pre-dispatch-admission-finalization)
defines the reusable behavior and both supported entrypoints.

1. Obtain independent exact-source acceptance of this mechanism. Through the
   existing authorized root deployment channel, stage a verified root-owned copy
   of that exact accepted source. Keep the current protected consumer configuration
   and credentials on the host. Do not install an unaccepted candidate or bypass
   the unresolved reservation's lifecycle drain. The new root-only entrypoint
   runs accepted source without a service cutover and takes the normal Writer
   mutex itself; it does not need a new runner sudo grant or caller-UID override.
2. Re-read the original evidence before mutation: DocReview Task 339, attempt
   `run-42608866374`, reserved Step 2, slot `pool-4`, ready event `35562373605`,
   branch `codex/task-339`, PR 340 and starting head
   `81286d3dafa3d1deed26cfb9462f8e52bbd4b3ea`. Compare the original raw record hash
   with Step 2's observation; investigate any difference. The finalizer's
   `recordDigest` is canonical JSON, **not** the raw file SHA-256 reported in Step 2.
   A newly generated binding must be reviewed against these facts, never copied
   from an old report or filled with an invented digest.
3. As the authorized root operator, define `accepted_source` as that verified
   source directory and `protected_consumer` as the existing protected config.
   Run this read-only request (no private paths or credentials are shown here):

   ```sh
   /usr/bin/env -i PATH=/usr/bin:/bin HOME=/root LANG=C LC_ALL=C \
     RELAY_CONSUMER_CONFIG="$protected_consumer" \
     /usr/bin/node "$accepted_source/controller/src/predispatch-recovery-entrypoint.mjs" <<'JSON'
   {"repository":"jresearchsoftware/docs-evolution-review","operation":"predispatch-state","runId":42608866374,"attemptId":"run-42608866374"}
   JSON
   ```

   Expect `binding` and `authorizationBody`, with the exact facts above. If the
   record no longer qualifies, the original run was rerun, native authority or
   event changed, the PR/ref moved, a journal/checkout exists, or the original
   controller lock is held, stop and inspect that specific conflict. Do not
   manufacture evidence, clear labels or try a fresh worker to repair inspection.
4. The owner posts the **exact returned `authorizationBody`** as a fresh unedited
   comment on DocReview Issue 339. This reuses the existing authenticated native
   owner recovery model; a local JSON assertion is insufficient. The comment
   must be newer than the completed original run. Retain its native comment ID.
5. Run the same root command with this JSON, replacing the numeric authorization
   ID with that actual comment ID:

   ```json
   {"repository":"jresearchsoftware/docs-evolution-review","operation":"finalize-predispatch","runId":42608866374,"attemptId":"run-42608866374","authorizationId":123456789}
   ```

   Expect `recovery.status="finalized"` with that authorization ID and original
   binding. Read back using the Step 3 inspection command; it now returns the
   same `recovery` receipt. Confirm normal admission inventory no longer lists
   this attempt as active/unknown. The historical `controllerLifecycle` remains
   active by design; the separately verified administrative receipt is the new
   completion basis. Verify original fields and native PR/head/labels unchanged.
   If delivery is uncertain, inspect first; repeating the **same** authorized
   finalize returns the stored receipt. A new authorization is not a retry token.
6. The original lifecycle upgrade can now re-run its normal preflight/drain and
   proceed only under its existing deployment authority. After an accepted and
   qualified installation and consumer workflow adoption, the generated recovery
   workflow also offers `inspect-predispatch` / `finalize-predispatch` with
   `run_id=42608866374`, `attempt_id=run-42608866374`, original slot selection
   where configured, and empty `candidate_head`. Only finalization takes
   `authorization_id`. The pre-upgrade root route avoids depending on that rollout.
7. Only after verified original-operation reconciliation may DocReview's owner
   issue its next native command under DocReview's own current charter/Decisions
   and existing PR 340. The original ready event stays reserved and cannot launch
   again. The owner normally removes/reapplies the ready command for a genuinely
   new event; no manual `step-*` reset or replay of event 35562373605 is needed.
   With unchanged numbering authority the next admitted execution is Step 3.
   Relay Task 230 neither changes DocReview implementation nor accepts PR 340.

## Validation and limitations

Regression tests exercise the actual broker, native owner authorization reads,
administrative receipt, gate inventory/resource release, Step allocation and
fresh-event continuation in the same PR. Negative cases cover missing/malformed
or contradictory state, consumption/projection progress, journal/checkout,
rerun/in-progress original run, changed event/head/slot, altered record after
authorization, forged/edited owner comments, concurrent finalization, replay and
attempted old admission/publication. Workflow black-box tests verify JSON mapping;
operator-entrypoint tests verify root/argument checks and the exact flock/env
transport. These are implementation evidence, not independent acceptance.

Validation runs on native ext4 WSL Debian with Node 22.20.0, Rust/Cargo 1.90.0,
Python 3.11.2 and Git 2.39.5. A task-owned temporary directory is used; shared
temporary-directory permissions are not changed. Full candidate results belong
in the canonical Outcome and native CI. Local Ansible version/skips and test
warnings must be retained there. The Step 2 routine Codex CLI maintenance result
is reused within this implementation cycle; this patch does not change the CLI.

No original host record, service, installed runtime, ready label, DocReview source
or PR state was mutated in Step 3. No new DocReview worker was launched. Root
wrapper deployment, real credentials/API permissions, installed multi-UID locking
and original-attempt finalization remain protected qualification/operation work;
local tests do not establish them. Task 230 remains open and safe live readmission
is not claimed before that operation. The source PR remains Draft while the
overall admitted result is blocked on this protected frontier.

Requested parent profile: gpt-6.1-sol/medium; actual model/effort UNAVAILABLE.
No subagents were used. The rename call succeeded but persisted native title
readback is truncated; exact full-title verification is unavailable/nonblocking.
