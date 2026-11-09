# Task 229 — Step 2: retained native error observations

## Result and remaining boundary

This Step repairs a demonstrated Relay diagnostic loss. It does **not** establish
the cause of the original Shared Governance Codex exit, restore discarded events,
or complete Task #229. The original execution must not be replayed. The source
candidate requires independent exact-head assessment; installation and a fresh
consumer execution require their own authorized continuation.

Authority: [Relay Task #229](https://github.com/jresearchsoftware/codex-relay/issues/229),
manual attempt `run-42610236991`, admitted Step 2, branch `codex/task-229`, starting
head `e6a472f9c9b0149c9276407b5daf7a81f86b4274`. Accepted source guidance was frozen
at that revision (Shared Governance 7.0.1 and Relay Skill 5.0.0). The independent
worktree preserved other tasks. The title command succeeded, but native readback
returned an abbreviated title; exact full-title persistence was not verified.

## Observed original evidence

The original protected primary bundle, fallback capsule and attempt journal were
inspected read-only through existing owner access. No raw diagnostic text,
protected paths, credentials or session content is included here.

- Original identity: Shared Governance `run-42595428620`, slot `pool-2`.
- Primary bundle SHA-256:
  `9ed927568c8afc309c695569d202c3a8ee2bfc2f1c1cdc2a9832dcac92ee65c1`.
- Fallback capsule SHA-256:
  `e921d8231733a2ddb3ccdcb101c4fdf95e1458c9b0886d746929d35c86c87481`.
- Runtime interval: `2026-11-09T09:42:58.220Z` to
  `2026-11-09T10:35:23.526Z`. The bounded stderr observation is timestamped near
  startup at `09:43:08Z`; it reports an MCP transport HTTP authorization denial.
  The error is an observed access-policy refusal, not proof of an expired token
  or of the terminal CLI failure. The endpoint/server identity is unavailable
  from that retained observation.
- Inner child started, exited 1, no signal; stderr 343 bytes, not truncated.
  Primary mode was `normal`, with no stdout field. The native sandbox/session
  files have already been removed by successful cleanup. The journal records
  reaped containment, complete cleanup, stored primary/fallback diagnostics and
  no successful semantic result; it contains no terminal native error message.
- The [original Writer Outcome](https://github.com/jresearchsoftware/shared-governance/pull/97#issuecomment-6737903647)
  preserved useful source at `56f4f7cd4d834af865a554906476366f240d6cab`.
  [PR #97](https://github.com/jresearchsoftware/shared-governance/pull/97) was
  still open and Draft at that head during this investigation. Its committed
  validation and successful candidate CI do not explain the child exit.

## Supported interpretation

The installed product source reported by the original routing run was
`0aff32a6873262185f60364463f4e97ef330de89`, whose selected CLI is 0.167.0.
The launcher, classifier, isolation builder, runtime and primary diagnostic
builder are unchanged between that source and the admitted Relay starting head.
`CHILD_STDERR` is a catch-all classifier. The 343-byte preview fits its normal
bound, so this is not preview clipping or an unavailable-primary-store case.

The startup observation precedes the eventual exit by about 52 minutes. Useful
source work was performed afterward. Attributing the terminal exit to that
message would be unsupported. In exact official CLI 0.167.0, primary-thread
nonretry errors and failed/interrupted completion can select exit 1; the public
JSONL processor emits error observations separately from stderr. See the
[exec lifecycle](https://github.com/openai/codex/blob/rust-v0.167.0/codex-rs/exec/src/lib.rs),
[event definitions](https://github.com/openai/codex/blob/rust-v0.167.0/codex-rs/exec/src/exec_events.rs)
and [JSONL processor](https://github.com/openai/codex/blob/rust-v0.167.0/codex-rs/exec/src/event_processor_with_jsonl_output.rs).
The public `error` event omits retry disposition, so an individual observation
is not necessarily the fatal cause. No specific Shared Governance code, provider
failure, quota condition or credential defect has been established.

Faithful isolated counterexamples ran the real official CLI 0.167.0 with only
loopback Responses/MCP fixtures and no credentials or model call. An optional
MCP returning the same authorization-refusal class emitted the transport stderr
but allowed a successful turn/exit 0. With that same startup refusal and a later
synthetic provider failure, the CLI exited 1 and emitted distinct top-level
`error` and `turn.failed` messages. The actual normal diagnostic builder retained
those native messages without general stdout. This verifies the diagnostic
mechanism and disproves attributing an exit solely from the startup refusal;
it does not prove which late error occurred in the original run.

The demonstrated Relay defect is narrower: functional JSONL is already captured
in memory, but normal failure diagnostics discarded its native error messages
before sandbox cleanup. A retained, possibly incidental stderr message could
therefore be the only available text after an unrelated late failure. The safe
diagnostic path was not sufficient to distinguish those cases for this incident.

## Correction and authority

Task #229 explicitly includes evidenced diagnostic classification/handoff faults
and making the existing diagnostic path actionable. The correction keeps the
last four top-level `error.message` / `turn.failed.error.message` observations
in the existing protected primary bundle. Each uses the existing secret redactor
and 4096-byte UTF-8 bound. Omitted count, per-message clipping and source-capture
truncation remain explicit. A potentially incomplete truncated final record is
excluded. General stdout, agent/tool messages and arbitrary event fields remain
excluded in normal mode. Public snapshots explicitly omit the entire new field.

This adds no operator command, prerequisite, policy bypass, permission, new
store, lifecycle status or retry. Existing exit handling, semantic validation,
usage rules, containment and replay protection retain their behavior. The owning
runtime/controller contracts document the private evidence; the portable Skill's
existing protected-inspection workflow needs no new user action or release.

The routine CLI maintenance check on 2026-11-09 returned the same latest stable
`rust-v0.167.0`, published `2026-11-06T01:40:00Z`; the qualified pin is retained.
This is not a new capability review or installed-version assertion.

## Validation

Linux validation used a separate
native-filesystem copy and task-owned temporary/build resources, Node 22.20.0,
Rust/Cargo 1.90.0 and Python 3.11.2. The initial focused invocation encountered
an unwritable host `/tmp`; the corrected invocation uses the task's own TMPDIR
without changing host permissions. This was an execution setup failure, not a
product-test pass.

| Check | Result |
| --- | --- |
| Focused diagnostic/runtime/public-projection regressions | 45 passed |
| `npm test` | 1015 passed, 7 skipped, 0 failed |
| `python3 -m pytest -q deploy/tests deploy/ansible/tests` | 1884 passed, 732 skipped, 0 failed; 404.95 seconds |
| `cargo fmt --manifest-path reviewer/Cargo.toml --check` | PASS |
| `cargo test --manifest-path reviewer/Cargo.toml --locked` | 159 passed, 0 failed |
| `python3 scripts/qualify.py` | PASS; three synthetic consumers, real handlers and loopback mock GitHub |
| `python3 scripts/check-candidate.py` | PASS; staged intended additions included |
| `git diff --check` and staged diff check | PASS |
| Official CLI 0.167.0 `qualify_execution()` | 6/6 loopback cases passed, including optional MCP 401 and actual protected error projection |

The deployment suite's skips retain their privilege, Docker and opt-in boundaries;
they are not installed-runtime proof. Its one warning is the existing third-party
Passlib use of deprecated Python `crypt`, unrelated to this diagnostic change.
One implementation helper supplied source investigation and regression/qualifier
changes (requested `gpt-6.1-sol / high`); this is implementation evidence, not
independent acceptance. Actual model/effort values are unavailable from runtime
evidence and are not inferred from requested settings.

The source qualifier retains these two counterexamples beside its four existing
CLI cases. All six passed against the exact official distribution. An initial
temporary harness assertion expected the raw synthetic provider message; the CLI
normalizes it. The committed check compares the retained messages with the actual
native JSONL, rather than asserting an invented provider representation.

Native evidence acquisition for Shared Governance PR #97 verified the exact
head and complete supported API surfaces. The original routing check's warning
that the Task remains incomplete is still applicable. It is not disposed by
candidate CI or this diagnostic patch. UI-only service/pre-execution annotations
remain outside supported automatic acquisition. This Step's manual routing check
had no API annotations. Source validation does not qualify installed sudo,
credentials, ingress, isolation or a real provider; shared TEST was not acquired
and PROD was not changed.

## Safe next action

Preserve the original attempt and Shared Governance PR #97. Independent review
can assess this diagnostic correction but cannot accept historical root-cause
attribution that the evidence does not support. An owner with provider-side
retained terminal evidence may still correlate the original execution interval
privately. Without such evidence, the original terminal cause is unavailable.

Before any new consumer execution, its owner must select and authorize a fresh
continuation of the **full** Shared Governance Task #96 objective on its existing
PR/head, preserving saved work. Obtain prospective native terminal evidence
through an accepted corrected installation, or an explicitly authorized protected
debug capture. Verify the affected MCP identity and access policy privately;
do not blindly rotate credentials, disable MCP, weaken required-server policy or
infer that fixing the observed startup denial resolves the late exit. A new
failure must be attributed from its terminal observation before selecting the
owning-side remedy. This Relay Step does not authorize that consumer launch,
PROD Apply, access-policy mutation, merge, release or Issue closure.
