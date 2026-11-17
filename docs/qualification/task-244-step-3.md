# Task 244 Step 3: Reviewer diagnostic capture regression

This source follow-up starts at accepted main
`d2056912954de816dfc64ecfde90f577d2730bc3`, after merged PR #274. It implements
Decisions [6957530603](https://github.com/jresearchsoftware/codex-relay/issues/244#issuecomment-6957530603)
and [6957604592](https://github.com/jresearchsoftware/codex-relay/issues/244#issuecomment-6957604592).
The earlier source result and immutable Outcomes remain unchanged. The receiving
Decision already assessed Small Improvements and selected none for this follow-up.

## Original observations

The GitHub log reader retrieved the original attempt separately from its later
successful rerun. These are observations, not root-cause assertions:

| Native source | Observation |
| --- | --- |
| [Main push 44128382893, attempt 1, job 134198357158](https://github.com/jresearchsoftware/codex-relay/actions/runs/44128382893/job/134198357158) | Reviewer: 183 passed, one failed. `definite_rejection_classification_does_not_wait_for_diagnostic_body` reached line 360 and failed `journal.contains("native_response_capture=pending")`. It had already passed HTTP 422 and safe-to-retry assertions. |
| [Earlier PR run 44097043136, job 134086804522](https://github.com/jresearchsoftware/codex-relay/actions/runs/44097043136/job/134086804522) | The same test passed; all 184 Reviewer tests passed. |
| [Main push rerun, job 134277680773](https://github.com/jresearchsoftware/codex-relay/actions/runs/44128382893/job/134277680773) | The same test and all 184 Reviewer tests passed. This does not establish a correction. |

The exact decoded Reviewer-step intervals are preserved as
[original failure](task-244-step-3-ci-failure.txt) and
[earlier success](task-244-step-3-ci-prior-pass.txt), including timestamps,
compilation output, individual tests and the original assertion. These are
contiguous extracts, without retiming or reconstructed journal content. Their
SHA-256 values are respectively
`37caa99d52c73603a241aba29f59e270512409a563b636202a24f8427d5af3ff`
and `1763105165c431c5be08e5cce6c62cafdf106745a116d9f2bf2fa8e90a3f89a8`.
The native jobs retain the full Actions logs; the extracts omit unrelated steps.

## Reproduction and correction

The pending record in `rejected_mutation_response` is synchronous, before
`tokio::spawn`. Waiting longer for the detached response body cannot repair its
absence. Production already propagates the current subscriber to that task.

The locked `tracing-core` 0.1.36 callsite implementation has a single-Dispatch
optimization: first registration consults the emitting thread's current default.
`WithSubscriber` constructs its Dispatch before polling the future. An unscoped
test can therefore register the diagnostic callsite in the gap, caching
`Interest::never` despite another test owning a capture Dispatch. Re-entering
that same Dispatch does not rebuild the callsite cache.

A fresh-process regression deliberately constructs the sole capture Dispatch,
emits the first observation outside its scope, then emits a diagnostic inside
that same scope. Before the correction it deterministically fails with an empty
journal (`missing original cause:`), reproducing the missing-record symptom.
The subprocess is necessary because other test captures can hide this initial
state. Its parent also checks that one test actually executed.

The correction retains one disabled, sink-backed Dispatch in the existing
`#[cfg(test)]` capture helper. Before any real capture the global maximum level
stays OFF; while a capture exists, two live registrars force interest calculation
across registered subscribers. It installs no global default, serializes no tests,
and changes no production diagnostic, API, retry, reservation or publication code.

Additional regressions exercise eight concurrent captures across async polls,
checking all 32 records per capture, isolation and redaction. The HTTP 422 fixture
now withholds its body until classification and the synchronous pending record
are verified. It then releases original native output after the caller's scope
ends and requires the detached reader to retain it, redact the actual request
credential and labelled secret, record clean bounded-read metadata, and keep
native text out of public diagnostics. Existing status, uncertain-send and
malformed-response regressions remain in place.

This establishes a concrete harness defect and a deterministic correction. The
original CI log does not expose its callsite-registration interleaving or captured
journal bytes, so it cannot prove that precise historical scheduling sequence.
No production journal-loss defect was established by this investigation.

## Separate finding for owner disposition

Deployment validation exposed an independently reproducible Ansible-adapter
cause-loss path, outside the selected Reviewer journal-test correction.
`deploy/ansible_transport.py` starts `ansible-playbook` with both outer streams
set to `DEVNULL`; missing/invalid receipt handling returns
`ANSIBLE_TARGET_OPERATION_UNPROVEN` and removes its temporary directory.
An Ansible controller startup error can therefore lose its only actionable output.

In this worker, with `LC_ALL=C`, the harmless local transport invocation
`run_target(None, None, ['/usr/bin/python3', '-c', 'print("LOCAL_RECEIPT=PASS")'], local=True)`
returned code 255, empty stdout and only `ANSIBLE_TARGET_OPERATION_UNPROVEN`.
Running Ansible directly on the local `/usr/bin/true` fixture exposed the original
message: `ERROR: Ansible requires the locale encoding to be UTF-8; Detected None.`
The same direct fixture succeeded with `LC_ALL=C.UTF-8`. No remote target,
credentials or escalation was used. This is a prospective reproducible example,
not a reconstructed cause for an earlier owner operation.

The affected required outcome is retaining the original cause at the Ansible
controller boundary, independently of a target receipt. This follow-up leaves
that adapter unchanged. Writer/owner should retain this finding in Task 244's
Outcome/chronology and decide on a separate source correction/Issue: capture
bounded, redacted controller stderr/stdout through an existing protected/fallback
surface and preserve the missing-receipt reason before cleanup. Do not infer that
the transport failure proves a remote command did not execute, or recommend a
blind rerun. This finding does not prevent assessment of the bounded test fix,
but prevents a claim that every Task 244 diagnostic path is now qualified.

## Validation and boundaries

| Check | Observed result |
| --- | --- |
| Deterministic isolated reproduction | Failed with an empty journal before the anchor; passes after it. |
| Focused diagnostics/mutations | 3 diagnostics and 9 mutation tests passed; 100 repetitions of each suite passed with 16 test threads, including fresh subprocesses. The uncorrected mutation suite had also passed 500 repetitions, so repetition alone was insufficient evidence. |
| Reviewer | `cargo fmt --manifest-path reviewer/Cargo.toml --check` and `cargo test --manifest-path reviewer/Cargo.toml --locked`: all 186 tests passed on final Rust sources. |
| Node | `npm test` in a disposable local Git checkout with ordinary checkout modes and identical candidate Rust bytes: 1,326 passed, seven skipped, zero failed. |
| Three consumers | `python3 scripts/qualify.py`: `THREE_CONSUMER_PASS` on final Rust sources, sequentially after other builds. Source digest `5ac059c9097bfe56162b07cee79150ca0bc2d70b8cc08a6be730e3732b768593`. |
| Deployment pytest | Full unprivileged run in that disposable checkout: 2,373 passed, 1,010 skipped, 487 subtests passed, **35 failed**. A focused UTF-8 rerun of those 35 failures still failed all 35; the suite is not qualified here. |
| Candidate and whitespace | `python3 scripts/check-candidate.py`, `git diff --check` and staged whitespace checks passed. Exact CI log extracts have a narrowly scoped trailing-blank allowance in `.gitattributes` to preserve their original bytes. |

The worker checkout initially had group-writable tracked fixtures and a long
temporary path. Ordinary source checks refused those fixture modes, and a Unix
socket could not bind under the long path. Source permissions were preserved;
the disposable checkout and `TMPDIR=/tmp` supplied suitable fixture conditions.
Pytest/Ansible dependencies were installed only under the ignored execution
sandbox. Validation used Node 22.23.3, Cargo 1.90.0, Python 3.11.2, pytest 9.2.0
and Ansible Core 2.17.14; this is distinct from the pinned native CI environment.

Remaining deployment failures exercise root/protected ownership and host
filesystem assumptions: consumer drift/recovery, managed-pool parents, general
runner files expected to belong to UID 0 or 65534 rather than this worker's
UID 990, and default ACL creation rejected by the private temporary filesystem
with `EINVAL`. The initial in-place run was also unsuccessful (193 failures);
neither it nor the improved disposable run is claimed green. Native qualified
host/root checks remain the continuation boundary; no ownership/security check
was weakened or privilege escalation attempted. One concurrent qualification run
reported `Qualification candidate changed`; its result was discarded and the
sequential final run passed. It does not supply additional qualification proof.

Tests use synthetic data, local processes and loopback GitHub fixtures; they make
no model calls or authenticated GitHub mutations. One helper supplied read-only
analysis and diff inspection under Subagents On (requested
`gpt-6.1-sol/high`); it supplies no independent native acceptance. Actual
model/effort telemetry is UNAVAILABLE. New-result native checks/annotations and
Writer Outcome remain pending trusted publication/inspection at this local
handoff, so this report makes no warning-absence claim about those surfaces. Preserve prior immutable Outcome
warnings and their recorded evidence gaps.

The production build excludes every changed Rust section. Operator behavior and
the existing [protected journal contract](../../reviewer/README.md) are unchanged,
so no user-manual, CLI dependency or frozen Skill package change is needed.
Skill 9.0.0 stays immutable and its separate publication is unaffected.

Installed root/runtime proof, native exact-head CI, independent acceptance and
Writer publication remain separate. This worker performs no privilege escalation,
PROD/shared TEST operation, deployment, release, original-incident replay or Issue
closure. Task 244 and the distinct #248/#256 receiving-client/projection obligations
remain open under their existing authority.
