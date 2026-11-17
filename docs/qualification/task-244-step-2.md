# Task 244 Step 2: causal failure reconciliation and qualification

This report belongs to admitted manual attempt `run-44084929326`, continuing
PR #274 on `codex/task-244` from
`0562deca68f0548a501dcc01e576d0c78d77b6ca`. The accepted product comparison is
`7f95a60c485ccf40025dae78f652adc8df3b19ea`. Task #244 Decisions 6860804855,
6943093940 and 6948241034 retain the combined causal diagnostics, #270 progress,
#248 client guidance and #256 workflow presentation scope. This supplements the
[Step 1 boundary inventory](task-244-step-1.md), rather than replacing its
historical results.

## Original Step 1 evidence and disposition

Read-only inspection of the original protected runner journal and primary and
finalization diagnostic records establishes this sequence:

1. The returned execution records `CODEX_RUNTIME_TIMEOUT`, a started child,
   contained/reaped execution and the launcher's `EXECUTION_CANCELLED`/`SIGTERM`
   observations. The runtime's existing 90-minute timer initiates termination;
   the launcher's cancellation is subsequent evidence, not the timeout's cause.
2. Collection preserves published head `0562deca…`, but records `clean: null`
   and `WORKTREE_OBSERVATION_TOO_LARGE`. It explicitly lacks complete residue
   observation; it does not establish uncommitted source files.
3. The readiness guard overwrites the execution error with
   `UNCOMMITTED_WORK_REMAINS`. Finalization also lets an older capsule's unknown
   child observation obscure the journal's known started child. The immutable
   [original Outcome](https://github.com/jresearchsoftware/codex-relay/pull/274#issuecomment-6945086903)
   therefore reports the secondary preservation problem as its terminal cause.

The correction preserves the original execution code, known child observation
and signal. Only the specific known timeout/cancellation ordering changes its
cause summary to `CODEX_RUNTIME_TIMEOUT`; genuine cancellation and other native
causes retain their classifications. Dirty and incompletely observed work are
separate readable and canonical warning fields, including on blocked Outcomes.
Replay retains the original terminal publication and never starts another worker.
Protected capsule containment and retirement requirements remain unchanged.

Later read-only byte comparison of every original tracked path against the
published Git blobs found no unpublished tracked source delta. This comparison
uses trusted candidate Git objects and direct file reads, never Git against
worker-modified metadata. The remaining inspected extras are validation artifacts
and a boot lock. The retained unignored virtual environment currently occupies
131 MiB, exceeding the collector's existing 100 MiB acquisition bound. That is
consistent with incomplete observation on the retained checkout,
not contemporaneous proof of which original file crossed the bound. No original
journal, Outcome, capsule, checkout or installation was altered or reused.

The timeout is established; this evidence does not establish why every original
worker activity consumed its allotted time. The original stored native-error
summary has no events and marks stdout as truncated; no provider failure or
unobserved earlier error is inferred. Useful published work is retained
and continued in this new admitted attempt. No original execution replay or
blanket resource-release claim follows from this source repair.

## Completion of the candidate

Additional corrections preserve bounded child stdout/stderr through install,
promotion and admission wrappers, including partial timeout output and recorder
failure. Existing host reporting captures original cause chains, availability,
byte counts, truncation and redaction without exposing private text publicly.
Deployment mutex refusals reuse the existing host diagnostic mechanism. The
inline instance-identity preflight guard now preserves its exact safe check
reason, native errno or JSON parser position before its generic rejection code.
The existing protected backend log retains this record; raw exception,
configuration and path text are explicitly marked redacted. Guard decisions and
transport prerequisites are unchanged.

DRAIN forwarding now preserves unavailable counts and separate observed pending
changes that previously could be coalesced between transport polls. Its existing
ephemeral progress file has a 65 KB bounded history, explicit overflow warning,
and bounded duplicate suppression. Counts cover the whole observed inventory;
identity text is capped at 20 entries and 3,500 bytes. Configured repository and
explicit slot identities are included only when verified; absent historical
slots and foreign locations are omitted. Disappearance never claims success.

The publisher and DRAIN readers preserve the final safe native stop code when
independent recorder fallback lines or typed diagnostic references accompany it.
The singleton recovery generator closes the new admission-import dependencies
against its retained consumer exports, preserving the original configuration and
per-attempt slot reader rather than requiring a newer retained installation.

Stale native/fixture assertions now verify the enriched safe failure envelopes
and protected causal evidence, rather than rejecting intended diagnostics.
Installed rejection qualification reads the actual root-owned private archive
and original exception chain, in addition to checking its public receipt.

Frozen guidance 8.0.0 already existed in accepted source. Its registry bytes are
restored exactly, and the combined change is prepared as **9.0.0 MAJOR** because
the owner-authorized failed Actions status for terminal BLOCKED changes the
operator contract. Native materialization, exports, license metadata, locks and boot projections
are regenerated; builder regressions reject inconsistent license attribution
before generation; publication and installed adoption remain separate.

## Validation context and limits

Validation uses independent task-owned checkouts, caches and temporary resources.
The managed checkout under `/root` is inaccessible to numeric test identities;
a separate `/tmp` checkout supplies the same committed source without changing
host ancestor permissions. The host mounts `/run` with `noexec`, so tests that
execute synthetic helpers there run in a private mount namespace with a fresh
executable temporary `/run`. The host mount is unchanged. Initial exploratory
runs in the unsuitable contexts were interrupted and superseded; they are not
reported as passing validation.

The isolated installed consumer proof passed owner bootstrap, real Writer/sudo
admission, protected causal archive readback, Runner parent protection and final
parent-drift rejection. The full installed runtime lane (`--runtime-only`) also
passed, including the real Unix launcher, isolated homes, Git identity, original
Rust/child failure, dispatcher causal archive, finalization, containment, cleanup
and same-result replay. It intentionally did not repeat the separate Runner
package-metadata lane. These are actual candidate templates and Unix boundaries
with synthetic consumer state and transport. They do not establish live GitHub
permissions, real model execution, PROD deployment or shared TEST installation.
No shared TEST contour was claimed or reused.

The complete local Node suite passed 1,327 tests with five skips; the later
drain-envelope regression also passed its focused admission suite. Rust
formatting and all 184 Reviewer tests passed. The three-consumer qualifier
passed at the final functional source digest. The distinct-UID sandbox cleanup
proof passed. Guidance generation, registry integrity, frozen-version tampering
regressions, native VibeVM 1.0.11 materialization and the accepted publisher's
candidate-readiness check passed. The final handoff records full suite results
and any remaining qualification limits. Changes to both diagnostic scripts also
required refreshing the exact owned-recipe fingerprint. All 228 affected
catalogue, source-upgrade and package cases passed after that correction,
including actual Ansible rendering of all 32 routes and negative drift checks.
The single exact fingerprint gate remains in place; older differing recipes
retain their existing full-path/frozen-runtime behavior.

The routine upstream check on 2026-11-17 still identifies official stable
`rust-v0.169.0`, matching the unchanged qualified CLI pin. No model call was added
for progress or diagnostics. Requested parent profile remains
`gpt-6.1-sol / medium / Subagents On`; helpers supplied implementation evidence,
not independent acceptance. Actual model/effort telemetry is unavailable.

Supported primary GitHub evidence was read through the connected evidence reader
for the starting head, including original Writer Outcome and associated runtime
check annotations. It reported complete in-scope acquisition and no annotation
warnings. The original terminal failure above remains material despite its empty
warning array. UI-only/pre-execution banners remain outside that completeness
claim. Final-head CI, warning acquisition and independent native exact-head
acceptance retain their own boundaries.

Task #244 remains open. Accepted source integration, applicable package
publication, full effective ChatGPT Instructions reconciliation/readback and
separately authorized private workflow projection publication are distinct from
this source execution. #248 and #256 retain their pending source/client/projection
obligations. No source commit or test activates those settings or workflows.


## Separately actionable follow-up

The exact-head candidate CI subset passed at `c78b66e` while the required full
root deployment suite detected a stale recipe fingerprint in
`deploy/installed_state.py`. The affected Ansible scripts had changed while its
pin had not. This Task corrects the pin and adds drift regressions in its owning
test suite. As an optional later improvement, the owner could select an early
native-CI invocation of the existing fingerprint-coherence assertion to expose
this specific mismatch sooner. The impact is delayed diagnosis and wasted full
suite time, not a remaining recipe-integrity bypass. No new mandatory check,
workflow or additional Issue is introduced here; the owner can decide whether
to track this CI feedback improvement separately.
