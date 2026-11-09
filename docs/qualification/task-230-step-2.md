# Task 230 Step 2: partial Writer admission

Authority: [Task 230](https://github.com/jresearchsoftware/codex-relay/issues/230),
[owner scope correction](https://github.com/jresearchsoftware/codex-relay/issues/230#issuecomment-6741057122).
Attempt: `run-42625222796`. Accepted starting source and independently frozen
development guidance: `88126990b9c7b66d1255ab498294f5a5950f26df`.

## Established incident facts

The original [DocReview routing run](https://github.com/jresearchsoftware/docs-evolution-review/actions/runs/42608866374)
failed on pool-4. Its job annotation reports only exit 1. The generic
`WRITER_FAILED` envelope does not identify the original inner exception.

The owner supplied [sanitized protected inspection evidence](https://github.com/jresearchsoftware/codex-relay/issues/230#issuecomment-6741157108).
This execution independently connected through the existing configured SSH
identity, verified the configured host fingerprint, and read the bound original
record. No credential material, protected paths or raw logs are reproduced here.

| Fact | Observation on 2026-11-09 |
| --- | --- |
| Installed source | `0aff32a6873262185f60364463f4e97ef330de89` |
| Original operation | DocReview Task 339, `run-42608866374`, slot `pool-4` |
| Reserved Step / event | 2 / `35562373605` |
| Existing implementation | PR 340, `codex/task-339`, `81286d3dafa3d1deed26cfb9462f8e52bbd4b3ea` |
| Partial admission | `stepProjectionFrom=["step-1"]`; no `stepProjected`, `readyConsumption` or `readyConsumed` fields |
| Controller lifecycle | `version=1`, `status=active`; no terminal Outcome |
| Publication | No publication intent or published head |
| Original journal / checkout | No matching entries found under the original configured slot roots |
| Process observation | No process command line correlated with this run at inspection time |
| Original record integrity | SHA-256 `ed5cbdfbecb380088390e9803903f3f3ae9a33616c6eebe41ca47e7de375c342`, identical before and after read |
| Consumer readback | Issue 339 retains `step-1` and `codex-ready-auto`; PR 340 remains open/Draft at the original head |

The installed `publication-broker`, privileged Writer helper, routing entrypoint
and GitHub adapter bytes matched their exact installed Git source blobs. Source
ordering localizes the original failure to Step projection after reservation and
before ready consumption; the normal controller dispatch follows a successful
`admit` return. This is a source-path inference, not a retrospectively created
completion or containment receipt. Missing processes/journal/checkout do not
finalize a protected reservation.

The original exception/stack was not retained in the inspected evidence described
by the owner. This execution did not recover it and does not claim a particular
GitHub status, network failure or JavaScript exception as the historical cause.

## Verified source defects and correction

1. Step projection had no durable admission-specific exception capture. It could
   leave an active reservation and lose the underlying exception before the
   controller's ordinary diagnostic/finalization scope began. Writer now records
   the exact projection suboperation and a bounded, redacted private exception in
   the existing protected record. The public helper wire preserves safe error
   code/type and HTTP status without exception text, stack, URLs or paths. A
   failed diagnostic write explicitly reports unverified retention. Generic
   projection diagnostics make no worker-start or containment assertion.
2. Existing automatic label-admission replay projected Step/PR metadata and
   consumed the ready event before `runAttempt` rejected a missing original
   journal. The existing journal version/structure/envelope checks now run before
   those native mutations. This moves an existing no-reexecution invariant; it
   adds no new launch command, permission gate or journal requirement. The
   existing uncertain ready-DELETE path remains publication-only and never
   repeats the DELETE. Manual handoff behavior is preserved.
3. Supported read-only inspection now returns a safe `admissionState` through the
   actual recovery entrypoint. Missing receipts are `null`, rather than evidence
   that GitHub metadata was unchanged. It distinguishes reserved Step, projection
   and command-consumption receipts, lifecycle and safe failure classification.
   Private exception text is excluded.

Regression coverage includes uncoded TypeError and coded HTTP failures,
accepted label mutation followed by lost response, failed diagnostic persistence,
UTF-8 bounds/opaque-secret redaction, read-only inspection, and missing,
malformed, wrong-version or mismatched original journal rejection before native
mutation. Existing ready-consumption and admission suites cover retained replay
and single-DELETE behavior.

## Original-operation recovery frontier

The original reservation remains unchanged and unresolved. These source changes
do not install themselves or authorize a live candidate on the protected host.
The remaining boundary is a missing supported original-operation finalization
capability/evidence, **not unavailable SSH access or a Task-specific ban on
credentials or private diagnostics**.

The authorized deployment operator can use the existing consumer recovery
workflow with `operation=inspect`, `run_id=42608866374`,
`attempt_id=run-42608866374`, original slot `pool-4`, and the configured trusted
base ref. Inspect requires no recovery authorization ID or candidate head. The
currently installed revision exposes only publication state; the new diagnostic
projection requires separately accepted/qualified installation. Protected direct
reads must select the original repository/slot from the retained envelope, as
the inspection above did, without copying credentials or raw state to GitHub.

Before any write, revalidate the original record digest, exact native ready-event
timeline, completed original Actions run, original journal/checkout/process state
and unchanged PR 340 head. Preserve the reserved Step/event and Step 1 source.
Use any recovered matching original terminal journal as input to the existing
protected `complete-execution` path; caller claims are not journal evidence.

With the state actually observed here, current supported operations have these
precise limits:

- `recover-publication` has no publication intent to reconcile.
- `recover-prepublication` requires returned successful worker/contained
  collection evidence and is inapplicable to this pre-return failure.
- `terminal-outcome` can report a truthful BLOCKED original attempt; it does not
  release lifecycle or establish containment.
- `complete-execution` requires matching terminal evidence and returns
  `ADMISSION_COMPLETION_UNKNOWN` when that evidence is absent. This result is
  established from the owning code; no live completion mutation was attempted.

The next protected action is original-operation reconciliation through the
normal authorized deployment recovery channel, using recovered trustworthy
evidence or a specifically qualified finalization mechanism. No such mechanism
for this missing-journal active reservation is claimed to exist in this patch.
Do not substitute a new owner launch, rerun, forced label reset, deletion of the
record, hand-written terminal journal or fabricated containment. This preserves
the Task's existing anti-duplicate/reconciliation obligation; it creates no new
Task-specific prohibition or approval flow. Safe DocReview readmission is not
claimed until that original operation is finalized and independently verified.

## Validation and limits

Validation uses an independent native ext4 checkout in WSL Debian, Node 22.20.0,
Rust/Cargo 1.90.0, Python 3.11.2, Git 2.39.5 and OpenSSL 3.0.18 under the ordinary
local user. A task-owned temporary directory avoids the local shared temporary
directory's unavailable write access; no shared permissions were changed.
Final validation results are recorded in the canonical Outcome and native CI.

Local synthetic suites do not qualify installed wrappers, process isolation,
credentials, ingress or a live PROD service. No protected record, label, source,
service, configuration or runner was changed during host inspection. No original
run was retried and no duplicate DocReview worker was launched. The source result
requires independent exact-head review; the incident Task remains open.

Routine CLI maintenance checked the official latest stable release once:
[`rust-v0.167.0`](https://github.com/openai/codex/releases/tag/rust-v0.167.0),
equal to the selected 0.167.0 dependency. No bump was needed.
The requested parent profile remains gpt-6.1-sol/medium; actual model/effort are
UNAVAILABLE without runtime telemetry. Subagents were used for source-path/test
analysis and isolated Linux validation; their work is implementation evidence,
not independent native acceptance. The native chat rename succeeded but persisted
readback truncates the complete admitted title; this is nonblocking.
