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
| Sandbox and network | New automatic launches select native `danger-full-access`, with approval `never`. The CLI no longer adds an inner filesystem/network sandbox; `.git` needs no extra writable root. Existing Unix permissions, managed requirements and applicable outer Bubblewrap remain independent. Serial/legacy launchers without slots do not gain outer isolation. Policy observation does not replace installed Unix/namespace proof. |
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

Task #96 Phase 1 changes only the native launch default, without a new Relay
permission profile, Task override engine, Unix identity or TEST capability.
Source acceptance does not upgrade installed launchers. Owner-controlled adoption
must preserve already-admitted attempts and qualify the actual host/launcher;
do not replay an old attempt with the new mode. Existing `workspace-write`
installations retain the root `.agents` limitation below until qualified adoption.
`danger-full-access` is the native sandbox option, not the separate
`--dangerously-bypass-approvals-and-sandbox` flag; managed restrictions remain
effective. See [native permissions](https://learn.chatgpt.com/docs/sandboxing).
The slot namespace mounts `/etc/codex/requirements.toml` and legacy
`managed_config.toml` read-only when present, so native administrator restrictions
are not hidden by outer isolation. No other `/etc/codex` content is mounted.

The optional installed permission qualifier is
`deploy/ansible/tests/qualify_installed_native_permissions.py`. On an explicitly
authorized Linux qualification host, invoke it as root with `--installation`
and `--consumer` paths. It runs inside private mount/PID namespaces, overlays
only the candidate native argv/isolation delta, replaces the token with a
synthetic value, and drives the actual installed CLI through a loopback provider.
It uses a source checkout at the actual configured work-root path, tests root
`.agents` present/absent, source/Git writes, runtime identity, outer isolation,
denied foreign/credential access and a managed policy refusal. It changes no
installed configuration or service and makes no model/GitHub call. This qualifies
that installed launch mechanism, not an adopted default, live model behavior or
an end-to-end admitted Relay execution. See [Task 96 evidence](../qualification/task-96-step-1.md).

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
also runs the official-release probe and targeted workflow, launcher and
diagnostic compatibility tests under an ordinary UID. The reusable disposable
installed-runtime proof remains separate; it requires an authorized capable
executor and never runs inside a governed worker. Neither it nor the full
deployment suite is a prerequisite of the CLI compatibility job. None of these
checks establishes production credentials, ingress, model access or deployment
readiness. Local success and native exact-head CI remain distinct evidence.

## Native filesystem probe

The optional credential-free probe exercises actual command filesystem access
with the exact installed CLI, under an ordinary Linux UID:

```sh
python3 scripts/qualify-worker-filesystem.py --codex /absolute/path/to/codex
```

It creates disposable fixtures and checks both default read-only and
`workspace-write` policy, with absent and existing root `.agents`. For pinned
0.160.0, ordinary writes and the explicit `.git` writable root succeed under
workspace-write; root `.agents` returns `EROFS` with a read-only mount, and
nested fixture projection paths remain writable. Original `.agents` bytes and
metadata are preserved. This is consistent with the documented
[protected-path policy](https://learn.chatgpt.com/docs/agent-approvals-security),
with the missing-path case established by the pinned executable probe.

The pinned `codex sandbox` subcommand takes its policy through `-c sandbox_mode`
and `sandbox_workspace_write.writable_roots`; passing only the outer `--sandbox`
flag does not select that subcommand's effective policy. The probe therefore
uses the effective legacy configuration equivalent to Relay's launcher policy
and a default read-only negative control. It never calls a provider or model.
This does not qualify outer Bubblewrap, native VibeVM projection, installed
Relay launch/collection/publication or a production deployment. Those require
their own actual evidence; see [Task 164 qualification](../qualification/task-164-step-1.md).

## Deferred capabilities

#42 owns any Relay migration to persistent app-server/daemon processes or
session ownership. Native internal CLI implementation details do not transfer
that lifecycle to Relay. Resume/fork continuation, native worktree ownership,
owner steering/instant interruption and changes to persistent config/state
remain deferred. Legacy adapter compatibility is retained rather than removing
an existing integration surface without authority.

#26 separately owns native exact-head CI waiting, feeding failures into an
implementation loop, retry/correction policy and readiness handoff. It also
owns reconciliation of repository-wide required validation with capable worker
and native executors. Task #43's former broad deployment gate exposed six
pre-existing deployment/lifecycle failures on its starting base; those findings
remain baseline debt, not Codex 0.160.0 regressions or Task #43 remediation.
The bounded compatibility job does not add #26 semantics to automatic execution
or change the repository's general validation policy.
#19, #20, #22 and #25 are not redesigned here; the observed
#25 nonzero exit is motivation for categorized evidence, not a diagnosed cause.
