# Task 57, Step 2: evidence reconciliation

Date: 2026-11-13. Related to [Task 57](https://github.com/jresearchsoftware/codex-relay/issues/57)
and [PR 246](https://github.com/jresearchsoftware/codex-relay/pull/246).
This report continues the [Step 1 audit](task-57-step-1.md). Its nineteen-family
inventory and eight challenge cases remain the broad assessment; the changes
below refine its evidence and recommendations. This is decision preparation,
not a control change, acceptance verdict or deployment qualification.

## Result and remaining obligation

Source inspection confirms the smallest proposed correction: in an ordinary
full managed-pool site traversal with package management enabled, install
Bubblewrap once before reconciling slots, eliminating 31 duplicate APT module
calls. Retain every slot identity, namespace probe, protected acquisition,
publication reservation and final runtime assertion. The elapsed saving is
**unmeasured**. This correction requires separate implementation authority.

The natural Apply log is now independently read through the connected GitHub
tool. It confirms the phase baseline and narrows the long interval to an active
backend call, without exposing role/task durations. Step 2 did not obtain a
sanitized host timing extract through its inspected evidence surfaces. Its
earlier attribution of confirmation to the owner was unsupported. That access
gap does not prove that historical host timing data do not exist. The required causal breakdown and a defensible end-to-end latency target remain
**insufficient_evidence**. Neither the 31 duplicate calls nor Rust
compilation is established as the dominant cause. No measured improvement or
completion of that causal requirement is claimed.

## Exact scope and provenance

- Admitted attempt: `run-43497563559`, Task 57 / Step 2, manual route; starting
  PR head `12728eca1c5a9f98190b850d27dd03eff1f2e138`, branch `codex/task-57`,
  admitted base/runtime source `5df7e0093d93c5a55b996e34cc83359da6b22a3e`.
  Only audit Markdown changes in this continuation.
- The live charter and trusted Decision
  [6862381328](https://github.com/jresearchsoftware/codex-relay/issues/57#issuecomment-6862381328)
  retain the admitted SHA-256 values `ace0ebbfe3da78befebfca3e1fde240096b3f9735f9d266afbfc3cdc96827911`
  and `c0d0fd1febf0e2c46804e256370424a93b7b813da723774c7bfb3ddc1692695f`.
  The native [manual handoff](https://github.com/jresearchsoftware/codex-relay/issues/57#issuecomment-6863490570)
  supplies admission digest `d97fccceed0105f3c7c20ead4bafc8e6c3f844736082565d337ae35d9b6f539e`.
  Old Step 1 wording in the stable charter is not a new Step allocation.
- A new worktree and a separate native-ext4 Linux validation clone were created
  for this run. Existing checkouts, slots, installed environments and unrelated
  work were not reused or changed. Tests have separate temporary/build outputs.
- Accepted Shared Governance 7.0.1 PC/RA/CL/TH/IR/CD and the relevant repository,
  architecture, execution, consumer, controller/Writer, Reviewer, runtime,
  deployment and integration contracts remain the criteria. No candidate policy
  is adopted and no report recommendation becomes binding by appearing here.
- Step 2 selected two targeted read-only helper passes: `/root/latency_evidence`
  checked deployment assertions; `/root/audit_coverage` checked control coverage
  and finding support. They reviewed the existing report, so these are skeptical
  continuation checks, **not new blind audits**. Step 1's A/B discovery remains
  historical provenance. Requested parent/helpers: `gpt-6.1-sol / xhigh`;
  actual runtime model/effort: **UNAVAILABLE**. Subagents used: yes.
  No helper edited files or accessed a host, credentials or publication tools.
  No external/cloud evaluator or separate ChatGPT conversation was used.
  Native independent acceptance remains pending; deliberative report acceptance
  does not authorize its recommendations.
- The one startup rename call succeeded, but persisted readback returned
  `Task 57 — Step 2 — Audit proportionality of Relay security…`, rather than the
  full requested title. This nonblocking UI truncation changes no admitted identity.

## Primary natural-run evidence

Read-only GitHub access retrieved all returned log lines for existing
[run 43479023265, job 132070376138](https://github.com/jresearchsoftware/codex-relay-deployment/actions/runs/43479023265/job/132070376138).
The run has one successful lifecycle job and no uploaded artifacts. Only the
nonsecret markers and timings needed here are retained; no raw host log or
private configuration content was read or copied into this repository.

The log binds operation `f5360cf3-01b6-47ad-8b18-4920eff77ec3`, old product
`93a48523ac0dc6310171ae39945497b83b017d8a`, installed target
`5df7e0093d93c5a55b996e34cc83359da6b22a3e`, config
`dc17d8b9f904f6536d9d76568b94514ffd5afe87`, strategy `upgrade`, six ready pool
members, and successful same-operation verification/outer Git readback.
It contains no separate post-check step. These are historical run observations,
not readback of the host's present state.

| Logged UTC boundaries, 2026-11-13 | Seconds | Attribution limit |
| --- | ---: | --- |
| Plan 18:04:44.182 → source resolved 18:04:50.908 | 6.725 | Source-selection interval. |
| Source resolved → prepared 18:06:46.967 | 116.059 | Preparation aggregate; role/build/fact costs unavailable. |
| Prepared → QUIESCE 18:06:49.974 | 3.007 | Transition aggregate. |
| QUIESCE → DRAIN 18:06:57.256 | 7.282 | Gate/transport aggregate. |
| DRAIN → APPLY 18:07:17.429 | 20.174 | Includes transition work; not proof of waiting on an active worker. |
| APPLY → ACTIVATE/VERIFY 18:16:43.833 | 566.404 | Final revalidation, main backend and later pool reconciliation. |
| ACTIVATE/VERIFY → RESUME 18:16:44.950 | 1.116 | Phase transition. |
| RESUME → OPEN 18:16:46.067 | 1.117 | Verified reopening transition. |
| OPEN → deployment result 18:16:49.338 | 3.271 | Final result aggregate. |
| Deployment result → outer Git proof 18:16:49.642 | 0.305 | Bounded outer readback/output interval. |

Durations use the log's full timestamps before rounding; independently rounded
clock displays need not subtract to the last millisecond. The job step starts
at 18:04:36.788, so its start-to-outer-proof interval is 732.854 seconds. The
wrapper's own result reports 715 seconds. The earlier 742-second run baseline
also includes setup/teardown, using the owner's run-metadata report. Different
clock boundaries explain why these values must remain separately labeled.

During the APPLY interval a contiguous backend heartbeat series at
18:08:24.420 through 18:15:54.476 reports monotonic elapsed values 30, 60, ...,
480 seconds. [`run_backend`](../../deploy/relay-deploy.py#L183) starts that timer
for one subprocess and prints while it is running. Thus at least 480 seconds
were spent in a backend invocation, about 85% of the 566-second marker interval.
The matching ordinary-upgrade path calls the main backend at
[`relay-deploy.py:1098`](../../deploy/relay-deploy.py#L1098). This is source-based
attribution to that invocation, not per-task measurement. The missing next
heartbeat is not an exact end timestamp. No role, APT cost, fact cost, Cargo
reuse/rebuild, restart count or retry time can be inferred from that series.

The [Task 230 completion comment](https://github.com/jresearchsoftware/codex-relay/issues/230#issuecomment-6853749103)
was separately read: it reports 1,590 seconds Apply and 1,464 seconds post-check,
with nonfatal temporary-directory warnings. It has no phase-level profile.
Those 3,054 seconds remain operator-reported evidence for a different operation;
the newer run does not prove a reduction from that baseline or redundant work
in every part of Task 230's recovery/qualification.

## Reconciled source clarifications

Both targeted helpers and the parent found no basis to remove credential,
privileged-code, containment, exact-head, native-authority or publication
protections. The existing inventory explicitly covers all eight challenge
cases. The following precision changes matter for the next decision.

| Question | Reconciled observation and disposition |
| --- | --- |
| Is the duplicate APT count universal? | No. [`site.yml:117`](../../deploy/ansible/site.yml#L117) installs Bubblewrap before the additional-slot loop; [`execution-slot.yml:48`](../../deploy/ansible/tasks/execution-slot.yml#L48) repeats the same package/state. Managed configuration derives 32 fixed slots, hence 31 repeated calls in the ordinary full traversal when base-package management is enabled. Retained Reviewer-config publication continuation skips both paths; management-disabled paths install neither. Static call count is not proof those branches ran in the measured operation. **simplify_equivalent_control**, high source confidence; latency effect unmeasured. |
| What proves final Apply success? | [`site.yml:419–431`](../../deploy/ansible/site.yml#L419) clears the backend operation record and emits `PRODUCTION_APPLY_VALIDATED`; later [`reconcile_pool`](../../deploy/relay-deploy.py#L1112) produces pool proof, followed by wrapper validation and lifecycle verified/resume. The earlier backend marker alone does not attest later pool work. Preserve the complete aggregate success path and outer Git readback. **retain_preventive_control**, high. |
| Is Rust rebuilt for every product SHA? | No. Content-bound Reviewer source/build-contract/toolchain/binary reuse exists. Its broad source key includes Reviewer tests and its build-input key includes deployment roles; narrowing requires actual dependency-closure proof. Neither a code-only diff nor version equality proves reuse on this host. **simplify_equivalent_control** only after measured attribution; medium on savings. |
| Is immediate post-check mandatory after ordinary upgrade? | No. [`relay-deploy.py:1138`](../../deploy/relay-deploy.py#L1138) enters the extra backend `--check` for bootstrap/reinstall `install_flow`; ordinary upgrade reuses its final proof. Preserve the distinct later-drift, clean-install and recovery checks under [Task 25](https://github.com/jresearchsoftware/codex-relay/issues/25). No new single-pass runtime change is needed merely to remove a nonexistent mandatory upgrade pass. **retain_with_clearer_justification**, high. |
| Can Linux path/mode/link checks be removed together? | No. Native Linux boundary proof, root/untrusted acquisition and passive owner-local text reads protect different invariants. The earlier passive projection/mode proposals remain bounded optional changes; retain descriptor/no-follow/stability/byte limits and protected source/secret checks. Do not extrapolate from one ordinary text consumer to root collection. Workstation source ACLs remain outside the audit scope. **retain_preventive_control / simplify_equivalent_control**, high/medium as scoped in Step 1. |
| Does the Step 1 Python failure example establish a general cause? | No. Step 1's `consumer_drift.restore()` source-ancestry explanation was not accompanied by a primary failure trace. [`restore`](../../deploy/consumer_drift.py#L175) validates fixture/installed paths and root-owned namespace tools, with explicit fixture owner seams. Treat the old proposed cause as unverified historical diagnosis, not an explanation for all 157 failures. Fresh suite evidence below replaces it for this continuation. **insufficient_evidence** for that causal generalization. |

The helpers supplied checks of evidence, not additional acceptance votes.
The pool-proof distinction and Python attribution qualification refine wording;
neither establishes a new vulnerability. Step 1's historical counts are retained
as reported results, without silently relabeling them as current passing checks.

## Bounded next decision

1. If selected by canonical owner authority, implement the package deduplication
   in the existing site/slot tasks. Prove one shared installation before probes,
   missing-package/Apt-failure behavior, disabled-management behavior, all slot
   probes, fixed slot/recovery identity and retained-continuation behavior.
   The exact initial target is 31 fewer duplicate calls per eligible traversal.
2. In the same authorized follow-up, expose bounded elapsed task/phase values
   through the existing deployment output, excluding task arguments, environment,
   private payloads and paths. Existing Ansible configuration does not collect
   task timings; the existing profiling helper's log parser cannot manufacture
   them. Its command also runs a local operation-clear experiment, so do not
   present invoking it wholesale as a passive PROD-log reader.
3. Compare unchanged baseline/candidate disposable fixtures with the same input
   pair, capacity, cache/build state and tool versions, then reuse the next
   naturally authorized production measurement if available. Include no-op,
   code-only, config-only, combined and failure/recovery cases. Measure total
   Apply plus necessary qualification, each backend and removed calls. Choose
   the seconds target from observed removed cost/variance; no arbitrary SLA,
   benchmark-only PROD Apply, new ledger/cache or longer timeout is proposed.
4. Select further component reuse or traversal consolidation only from that
   attribution. Retain wrong-pair/corrupt-stage rejection, loaded process proof,
   pool readiness, original-operation recovery, lock/drain and unknown-effect
   barriers. Larger skip decisions remain separate from report acceptance.

## Warnings, validation and handoff limits

The connected `read_pr_review_evidence` inspected PR 246 at the exact starting
head. It returned `required_surfaces_complete=true`, `warning_observation=observed`
and one primary warning on [Step 1 route check 132106121498](https://github.com/jresearchsoftware/codex-relay/runs/132106121498):
the Task remains incomplete and its terminal Outcome must be reconciled before
another attempt. The [Writer Outcome](https://github.com/jresearchsoftware/codex-relay/pull/246#issuecomment-6862776535)
was read, its published progress preserved, and this fresh admitted independent
worktree continued from its exact head. Its missing causal profile remains
unresolved. Successful Actions status does not cancel that warning. UI-only
service/pre-execution annotations remain outside supported automated acquisition.
The current manual route check `132134558957` also completed successfully;
its annotations endpoint returned an empty array. Fresh final-head
warnings/checks must be inspected after publication.

Local checks used an isolated native-ext4 Debian clone, UID 1000, Node 22.20.0,
Rust/Cargo 1.90.0, Python 3.11.2, Git 2.39.5 and OpenSSL 3.0.18. No source,
system package or original-file permission changes were needed for the checks.
The executable source tree is unchanged from the starting head; its full test
results are reused with fresh final report/link/whitespace validation.

| Required check | Step 2 evidence |
| --- | --- |
| `npm test` | **1,168 passed, 0 failed, 7 skipped**; 1,175 tests. |
| `python3 -m pytest -q deploy/tests deploy/ansible/tests` | **1,965 passed, 808 skipped, 0 failed**, 1,013.50 seconds. One dependency deprecation warning: passlib imports `crypt`, deprecated for Python 3.13; this run uses Python 3.11.2. |
| `cargo fmt --manifest-path reviewer/Cargo.toml --check` | **PASS**. |
| `cargo test --manifest-path reviewer/Cargo.toml --locked` | **159 passed, 0 failed**. |
| `python3 scripts/qualify.py` | **THREE_CONSUMER_PASS**, actual handlers/modules and isolated Git/loopback mock GitHub. |
| `python3 scripts/check-candidate.py` | **PASS**, 1,450 tracked files; final link count recorded by the native candidate check. Intended report additions staged before scanning. |
| `git diff --check` and staged whitespace check | **PASS**. |

The earlier 157 Python failures did not reproduce in this qualified local shape;
that does not retrospectively diagnose every Step 1 failure. Installed/root-only
skips remain unavailable proof, not passed host qualification. The passlib warning
is nonblocking dependency debt for future Python compatibility; no runtime or
dependency change is included in this audit. Required native CI is read from
the final PR head after publication and remains distinct from local checks.

No production install, credentials, host raw diagnostics, ACL mutation, service
change, merge, release or Issue closure occurred. No attack experiment or
deployment benchmark was run. Independent native exact-head assessment and
owner disposition of recommendations remain separate from this execution.
