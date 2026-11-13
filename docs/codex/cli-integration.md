# Governed Codex CLI integration

Relay qualifies an exact **0.167.2** installation, selected by the product
deployment contract. Installation still uses `--release` and verifies the exact
version. Runtime and installation never follow a floating latest or self-update.
Routine source maintenance follows the separate development policy below.

## Relay development maintenance policy

This owner-approved policy applies to development of Relay itself, not arbitrary
downstream consumer repositories. When implementing a Relay product change that
will require a subsequent owner-controlled Apply after accepted merge, follow
the routine process below, even when Apply is not a Task completion action.
Documentation-only changes do not trigger this maintenance. Implementation,
independent source acceptance and owner-performed Apply remain separate; this
policy grants no deployment authority. No additional maintenance Issue, Step,
label, command or permission request is needed for a compatible bump. Source-controlled development instructions need no Apply,
package release or synthetic PROD job merely to take effect after acceptance.

### Routine technical version maintenance

Once per relevant implementation cycle, compare the exact selected CLI dependency
with the official upstream stable release in
[OpenAI Codex releases](https://github.com/openai/codex/releases). Freeze the
candidate for that cycle; do not chase newer releases on each commit. Reuse
`relay_codex_cli_version` in
[deployment variables](../../deploy/ansible/group_vars/all.yml) and the existing
[deployment contract](../../deploy/README.md#qualification), version assertions
and compatibility machinery; add no parallel version registry or updater.

Assess compatibility of the integration Relay actually uses: flags and
configuration, defaults affecting supported behavior, JSON events and result
handling, input, exit/failure and lifecycle behavior, and permission/trust
boundaries. Use version-bound official release notes/source and the applicable
existing [qualification](#qualification-and-limits), including the official CLI
probe and affected launcher/result tests. Unchanged flag names alone do not
establish compatibility. This bounded assessment preserves the existing
integration; it neither guarantees every possible upstream behavior nor counts
as the complete capability review below.

When a newer stable candidate preserves that integration and passes applicable
compatibility qualification, update the selected dependency and directly required
version references in the same Task and PR. Preserve reproducible exact pinning,
installation integrity and normal independent review of the exact result head.
Any later Apply uses its separately owner-authorized deployment path; do not
self-update an executing worker, autonomously mutate PROD or add an Apply to the
Task solely for maintenance.

If the candidate is incompatible, qualification is unavailable or checking
upstream fails, retain the previously qualified version and disclose the reason.
Continue the main Task unless the existing version itself is a real blocker;
do not weaken qualification or make an optional refresh an unrelated blocker.
Record a concise `old version -> new version` note and compatibility evidence
(or the retained version and reason) in the ordinary PR/Outcome, without a second
publication or approval ritual. An older capability-review baseline does not
block an otherwise compatible technical bump, and a bump does not advance it.

### Separate periodic capability review

The owner explicitly selects a review and target version through ordinary Task
authority. There is no recurring service/schedule and no required review after
every technical upgrade. Maintain these distinct facts in their existing owners:

| Fact | Current evidence and owner |
| --- | --- |
| Selected/qualified CLI dependency | Exact **0.167.2**, selected by `relay_codex_cli_version` in the deployment variables linked above; the historical integration evidence and qualification limits below describe what was checked. |
| Capabilities reviewed through version X | **Unknown / not yet established.** The accepted integration evidence below establishes bounded compatibility and selected capability decisions, not a complete historical review interval. No evidenced reviewed-through version or review date is established here. |
| Installed-host version | A separate observed fact from the specific host's installation/version evidence; neither source selection nor capability review proves it. |

Recover an initial capability-review boundary only from actual accepted evidence;
a qualified binary version is insufficient. If the boundary cannot be established,
keep it unknown and have the owner select the initial review interval explicitly.
Do not invent a baseline, backdate a review or treat this rules-only change as a
new upstream capability audit.

For a selected review with an evidenced baseline, examine the whole interval
after that baseline through the chosen target: new flags/configuration options,
relevant defaults, events and behavior changes, and native capabilities that
could simplify Relay. Use official release notes and source/docs pinned to the
relevant versions; today's moving documentation does not establish behavior in
every older release. Record concise dispositions for relevant changes here:

1. Not useful/applicable to Relay: briefly record why.
2. Useful and small enough for the admitted review/update scope: implement and
   validate in the same Task/PR.
3. Useful but requiring substantial refactoring, a material architecture, trust
   or behavior decision, or separate scope: create a dedicated GitHub Issue or
   link an existing equivalent Issue, with motivation and the required decision.
   Do not launch or implement that larger change as part of the review.

Once the interval is genuinely covered and decisions/follow-up links are recorded,
update the reviewed-through fact here with target version, review date,
version-bound official source evidence and concise decisions. Reviewed means
assessed, not that every feature is used. Advance the baseline even if no code
changed or larger improvements remain in linked, unimplemented Issues;
follow-up implementation is not a prerequisite to completing the review. Do not
advance it for an unexamined or materially incomplete interval. Retain factual
historical qualification and its limits when updating current facts.

## Task 217 routine maintenance

On 2026-11-08, one official stable comparison froze **0.167.0** (released
2026-11-06) against **0.160.0**. The bounded version-bound source assessment,
official installer/loopback CLI probe and affected launcher/result tests support
updating the exact selected dependency to 0.167.0 in the same PR. See the
[qualification evidence](../qualification/task-217-cli-maintenance.md) for the
exact sources, observed behavior, environment accommodations and limits.
This is routine compatibility maintenance, not a periodic capability audit;
the reviewed-through baseline remains unknown. Historical 0.160.0 evidence
below retains its original version binding. Source acceptance proves no installed
host update or Apply; those remain separately owner-controlled.

## Task 230 routine maintenance

On 2026-11-11, the selected stable CLI moved from **0.167.0** to **0.167.1**. The official [0.167.1 release](https://github.com/openai/codex/releases/tag/rust-v0.167.1) is dated 2026-11-10. The version-bound [0.167.0 to 0.167.1 comparison](https://github.com/openai/codex/compare/rust-v0.167.0...rust-v0.167.1) changes incremental Responses tools: its legacy mode is disabled by default and then restricted to Amazon Bedrock. Relay uses neither Bedrock nor that legacy option.

The exact official installer and credential-free loopback probe passed six deterministic cases covering success, missing usage, invalid semantic output, provider failure and optional MCP authorization refusal with successful and failed turns. It checked Relay's production argv, stdin, native event/result handling, requested model/effort, exit behavior, approval/sandbox policy and task-local state. No model call or credential was used. The historical 0.167.0 evidence below remains bound to its original candidate. This is routine compatibility maintenance, not a capability review; the reviewed-through baseline remains unknown.

On 2026-11-12, Step 21 froze **0.167.2** against **0.167.1** using the official [0.167.2 release](https://github.com/openai/codex/releases/tag/rust-v0.167.2), published 2026-11-11, and the complete version-bound [comparison](https://github.com/openai/codex/compare/rust-v0.167.1...rust-v0.167.2). The only runtime change adds the stable, default-enabled `incremental_tools_legacy_gcp` flag for GCP Responses and marks the existing default-disabled Bedrock legacy flag stable. Provider selection keeps both outside Relay's direct OpenAI path; CLI flags, event/result handling, input, failure/lifecycle and permission boundaries are unchanged in this interval.

The exact official 0.167.2 installer and all six credential-free loopback cases passed under an ordinary Linux UID. The probe checked exact release/symlink and restrictive installer umask, native JSONL events/identity/usage, schema transmission and local semantic rejection, stdin, requested model/effort, isolated home and sandbox policy, nonzero provider failure, and optional MCP 401 with both successful and failed turns. Debian WSL's existing `/tmp` was not writable by that UID, so the probe used an ephemeral `/tmp` mount in a private mount namespace without changing host permissions. The installer emitted its expected temporary-directory PATH-alias warning; direct execution of the exact binary passed. No credential or model call was used. This bounded maintenance does not advance the capability-review baseline or establish an installed-host update or Apply.

## Task 243 routine maintenance

On 2026-11-13, this implementation cycle froze the official stable candidate
[**0.169.0**](https://github.com/openai/codex/releases/tag/rust-v0.169.0), published
that day, against the selected **0.167.2**. The exact
[upstream comparison](https://github.com/openai/codex/compare/rust-v0.167.2...rust-v0.169.0)
includes [explicit project trust for non-interactive runs](https://github.com/openai/codex/pull/60041).
In the candidate's [version-bound exec implementation](https://github.com/openai/codex/blob/rust-v0.169.0/codex-rs/exec/src/lib.rs),
a writable sandbox no longer implicitly grants project trust: untrusted
project-local configuration and MCP servers remain disabled. The new `--trust`
option persists a grant, including with `--ephemeral`, refuses an explicitly
untrusted project and cannot be combined with `--ignore-user-config`.

Relay's launcher uses a fresh task-local `CODEX_HOME` and passes no `--trust`.
Its existing credential-free CLI qualifier injects the optional MCP fixture via
`-c`, without exercising project-local `.codex/config.toml` discovery. Those
cases therefore do not establish compatibility across this trust change.
The native exec event definitions are unchanged between these exact versions;
the JSONL processor's final-file binding change affects an output-file option
Relay does not use. These observations do not resolve the project-configuration
behavior difference or qualify the candidate as preserving Relay's integration.

The selected and previously qualified version remains **0.167.2** for this cycle
because that meaningful trust change remains unresolved. This bounded assessment
adds no validation gate or operator step, does not advance the capability-review
baseline and proves no installed-host update or Apply.

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
Normal protected bundles retain only bounded top-level JSONL error observations
under the [runtime diagnostic contract](../../runtime/README.md#durable-diagnostics-and-sandbox-finalization),
separately from stderr. The credential-free CLI qualifier exercises an optional
loopback MCP authorization refusal with both a successful turn and a distinct
provider failure. A transport stderr error alone cannot establish the terminal
cause; these observations never change exit handling or public evidence scope.
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
