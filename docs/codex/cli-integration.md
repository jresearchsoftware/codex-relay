# Governed Codex CLI integration

Relay qualifies an exact **0.160.0** installation, selected by the product
deployment contract. Installation still uses `--release` and verifies the exact
version. It does not follow latest or enable an automatic update policy.

## Established baseline

The available public history starts at
[`c0e0b5c`](https://github.com/jresearchsoftware/codex-relay/commit/c0e0b5ce3f52a311f473eca3a9f8694eb75c23f8).
That snapshot already pins 0.154.0 and contains the current one-shot launcher
shape: file-to-stdin task transport, `exec --json`, `--output-schema`, explicit
model/effort, workspace-write with network access and the checkout's `.git`
as an extra writable directory. The runtime already accepts native
`item.completed` agent messages and `thread.started` identifiers alongside
legacy `task_result` and flat-result adapter forms. This establishes the
available integration baseline, not the version on which a pre-public design
originated; that earlier provenance is unavailable in this repository.

[`24eef17`](https://github.com/jresearchsoftware/codex-relay/commit/24eef17ba402e9752d06f3fe2162f8ad8fa4793f)
added the independent diagnostic capsule and containment-gated sandbox cleanup;
[`48946e7`](https://github.com/jresearchsoftware/codex-relay/commit/48946e7bcabed73fa6f7809b266bf9f641ed71fc)
made successful residual work an explicit handoff warning. These are Relay
durability and ownership decisions, not workarounds to remove after a CLI bump.
All five usage counters are already present in the
[0.154.0 event definition](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/exec/src/exec_events.rs).
Their adoption is newly implemented Relay reporting, not a claim that 0.160.0
introduced those counters.

## Compatibility and ownership decisions

| Surface | Qualified behavior and retained boundary |
| --- | --- |
| JSON events | Real 0.160.0 emits `thread.started`, `turn.started`, `item.completed` with `agent_message.text`, and `turn.completed.usage`; a failed provider response emits `turn.failed` and exits nonzero. Legacy adapter result forms remain compatible but do not establish native usage. |
| Semantic result | `--output-schema` sends the strict schema upstream. A synthetic provider can still return invalid text with exit 0; Relay's local bounded semantic normalizer remains necessary for real execution. |
| Native identity | `thread.started.thread_id` supplies the native identifier. A separate session ID is absent in the qualified stream; existing session/thread correlation uses the native thread with its source recorded. No identity is extracted from model prose. |
| Model and effort | Relay passes the explicit admitted `--model` and `model_reasoning_effort` unchanged. Codex accepts `ultra` but resolves its provider-facing effort through model metadata; the local fixture resolves it to `xhigh`. The public event stream does not expose authoritative actual model/effort; requested values remain separate from `UNAVAILABLE` actual values. A mock provider does not prove account/backend model access. |
| Subagents | The resolved On/Off permission is in exact task input. Native `multi_agent` is enabled by default in 0.160.0, including when the input says Off. Off remains an instruction boundary, not a native tool-disable or OS containment claim. This upgrade does not change that contract or launch agents to qualify it. |
| Input | The launcher validates the bounded task/schema paths and sends the exact UTF-8 task through stdin. Unicode, newlines and shell metacharacters remain data. |
| Sandbox and network | Effective native policy remains workspace-write, approval never, the admitted checkout, `.git` writable, and network enabled. Policy observation does not replace the installed Unix/namespace containment proof. |
| Home/config/cache/state | The launcher recreates task-local HOME, CODEX_HOME, XDG and temporary paths after sudo. Native session files remain inside this disposable home. Native config/rule suppression and ephemeral mode are not substitutes for environment or filesystem isolation. |
| Git | Relay keeps checkout ownership, configured commit identity, bounded object import, every-introduced-blob scanning and ordinary non-force Writer publication. No native worktree is requested. |
| Lifecycle | Relay still reserves one execution, owns/reaps its process group, bounds capture/timeouts, persists diagnostics before cleanup and uses the fixed inode-bound cleanup helper. Native CLI process exit does not prove containment. |

The [0.160.0 event definition](https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/exec/src/exec_events.rs)
and [JSONL processor](https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/exec/src/event_processor_with_jsonl_output.rs)
are the version-specific references. The general
[non-interactive documentation](https://learn.chatgpt.com/docs/non-interactive-mode)
describes the supported public mode; the executable probe below checks this
exact release instead of relying on moving documentation alone.
The native [reasoning-effort resolver](https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/protocol/src/openai_models/reasoning_effort.rs)
owns the `ultra` resolution; Relay does not substitute a profile or assume the
fixture's resolved effort applies to a live provider/catalog.

## Safe automatic evidence

Terminal failure Outcomes project existing bounded diagnostic metadata:
launcher classification, categorized primary cause, inner child started state,
exit code or signal, observed diagnostic bytes and truncation, and diagnostic
store availability. An outer launcher exit must never become the inner Codex
exit. Missing inner observations remain `UNAVAILABLE`/unknown. Categories such
as process I/O, launch/permission, input/output and unclassified stderr help
direct inspection; they do not prove a specific provider or task failure cause.
Raw streams, prompt text, diagnostic previews and protected paths remain private.
There is no additional diagnostic store or recovery action.

Automatic success and failure Outcomes also carry the five safe integer counters
from one unambiguous native `turn.completed.usage`: input, cached input,
cache-write input, output and reasoning output tokens. They are labelled
`native-session-total`: the 0.160.0 JSONL processor copies its last native
session-total snapshot. Fresh one-shot invocation supplies the per-run scope;
Relay neither adds counters nor reconciles subagent consumption independently.
The CLI itself emits zero counters when it has received no usage update. Relay
preserves those native zeros; they are not proof of zero provider consumption.

Absent/invalid counters remain `UNAVAILABLE`. Missing, malformed, truncated,
failed or ambiguous multi-turn streams cannot establish a snapshot. Native
JSONL exposes neither total tokens nor actual model/effort, so those remain
`UNAVAILABLE`, even if the upstream fixture has a total or the requested profile
is known. Worker semantic output cannot supply usage. The existing attempt
receipt retains the bounded projection through publication recovery and replay,
without a model call or a separate telemetry store. This implements the bounded
reporting requested by #24; Issue closure remains an owner action. No billing,
rate-card equivalent or subscription allowance is inferred.

## Qualification and limits

`deploy/ansible/tests/qualify_codex_cli.py` downloads the exact official release
into temporary storage. It checks installer/version truth and parser flags,
then runs the real CLI against a credential-free loopback Responses fixture.
The probe verifies success, provider failure, schema transmission and local
semantic rejection, native events/identity/usage, missing-usage zeros, exact
task input, model/effort transmission, native Subagents availability and effective
sandbox/home policy. It reads only its own synthetic rollout for policy checks;
automatic reporting does not read or publish rollouts.

The public installer can warn that it will not create PATH helper aliases under
the qualifier's `/tmp` installation. Direct execution of the exact binary still
passes; this probe does not claim those aliases or native tool execution were
qualified. The installed-runtime proof retains its separate managed-path scope.

Local Node and deployment suites cover the launcher, redaction, timeout,
cleanup, trusted Git handoff and diagnostic/usage propagation. The existing
[exact-head CI workflow](../../.github/workflows/relay-exact-head-validation.yml)
also runs the official-release probe and the full disposable installed-runtime
proof with synthetic users and transport. Root-only proof runs in that hosted
CI boundary after Writer publication, never inside a governed worker. None of
these checks establishes production credentials, ingress, model access or
deployment readiness. Local success and pending native proof remain distinct.

## Deferred capabilities

#42 owns any Relay migration to persistent app-server/daemon processes or
session ownership. Native internal CLI implementation details do not transfer
that lifecycle to Relay. Resume/fork continuation, native worktree ownership,
owner steering/instant interruption and changes to persistent config/state
remain deferred. Legacy adapter compatibility is retained rather than removing
an existing integration surface without authority.

#26 separately owns native exact-head CI waiting, feeding failures into an
implementation loop, retry/correction policy and readiness handoff. Adding
qualification to the existing CI workflow does not add those semantics to
automatic execution. #19, #20, #22 and #25 are not redesigned here; the observed
#25 nonzero exit is motivation for categorized evidence, not a diagnosed cause.
