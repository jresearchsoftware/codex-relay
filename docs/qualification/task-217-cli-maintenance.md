# Task 217 — Step 3 Codex CLI maintenance

On 2026-11-08 UTC, this implementation cycle compared the selected **0.160.0**
dependency with the official stable release and froze **0.167.0** as its one
candidate. The [official OpenAI changelog](https://learn.chatgpt.com/docs/changelog)
listed Codex CLI 0.167.0 dated 2026-11-06. The anonymous
[upstream release API](https://api.github.com/repos/openai/codex/releases/latest)
returned `rust-v0.167.0`, `published_at=2026-11-06T01:40:00Z`,
`prerelease=false`, and `draft=false`. The version-bound
[release notes](https://github.com/openai/codex/releases/tag/rust-v0.167.0)
identify the selected release. No later release was sought after this freeze.

The selected dependency is now **0.160.0 -> 0.167.0** in
`relay_codex_cli_version`. Current runtime assertions and the disposable
installed-runtime substitute agree with the selected pin. Self-contained
package tests can still exercise older synthetic versions. This is routine
technical maintenance, not a complete periodic capability review; the
reviewed-through baseline remains unknown.

## Bounded compatibility assessment

Version-bound official source was compared at `rust-v0.160.0` and
`rust-v0.167.0`. The following links select the candidate source; replacing
the tag with `rust-v0.160.0` selects the compared baseline.

| Actual Relay surface | Assessment and evidence |
| --- | --- |
| Flags and task input | The [exec CLI](https://github.com/openai/codex/blob/rust-v0.167.0/codex-rs/exec/src/cli.rs) retains `exec --json --sandbox danger-full-access --output-schema --model -c model_reasoning_effort=... --cd ... -`. Its new Cyber access option is not requested. The real executable accepted production argv and received exact Unicode, newline and shell-metacharacter stdin as data. Resume/fork/worktree/ephemeral options remain unused. |
| Public events and identity | [Exec event definitions](https://github.com/openai/codex/blob/rust-v0.167.0/codex-rs/exec/src/exec_events.rs) are byte-identical to 0.160.0. The [JSONL processor](https://github.com/openai/codex/blob/rust-v0.167.0/codex-rs/exec/src/event_processor_with_jsonl_output.rs) changes internal item wrapping, retaining public agent-message mapping, thread identity and usage handling. The actual binary produced one native thread/turn and the expected final message. |
| Semantic result and usage | The strict Relay schema reached the loopback provider. Invalid semantic text still exited 0 at the CLI and was rejected by Relay's actual parser. Five native session-total usage counters matched the fixture; missing provider usage still became native zeros. Public events supplied neither authoritative actual model/effort nor total tokens. Relay's bounded normalizer and `UNAVAILABLE` rules remain necessary. |
| Model, effort and Subagents | The [effort resolver](https://github.com/openai/codex/blob/rust-v0.167.0/codex-rs/protocol/src/openai_models/reasoning_effort.rs) is byte-identical to 0.160.0. Requested model/effort remained explicit; the synthetic provider received `gpt-6-astra` and `xhigh`, including the fixture's native Ultra resolution. Native `multi_agent` remains enabled, including when task input says Off. Off remains an instruction boundary. No agent or model was invoked. |
| Defaults and native capabilities | The [feature definitions](https://github.com/openai/codex/blob/rust-v0.167.0/codex-rs/features/src/lib.rs) change defaults including API-key model discovery, reasoning-effort override, deferred/incremental tool state and interruption. Code-mode, OAuth refresh, plugin discovery, UI/onboarding and service-tier capabilities also evolve. Relay continues to pass the admitted profile and starts one fresh noninteractive execution; these changes do not adopt persistent sessions, owner steering, new providers or new Relay permissions. The real probe checks its effective request and policy rather than inferring compatibility from flag names. Native tool execution and every possible provider/catalog response are outside this probe. |
| Permissions and trust | The [configuration loader](https://github.com/openai/codex/blob/rust-v0.167.0/codex-rs/core/src/config/mod.rs) and [managed requirements](https://github.com/openai/codex/blob/rust-v0.167.0/codex-rs/config/src/config_requirements.rs) retain administrator constraints and add managed network behavior. In particular, `permissions.network` becomes reserved for shared constraints in requirements; previously authored managed profiles using that name need upstream-compatible migration. The selected probe uses no host managed-policy configuration and does not qualify all administrator policy combinations. Observed approval remained `never`, sandbox `danger-full-access`, and state stayed in the task-local home. Relay's UID, outer isolation, credential separation and Writer/Reviewer boundaries are unchanged. |
| Failure and lifecycle | The [exec lifecycle](https://github.com/openai/codex/blob/rust-v0.167.0/codex-rs/exec/src/lib.rs) remains a terminating CLI invocation with an in-process app-server. Paginated completion backfill and noninteractive MCP cancellation change internally. Synthetic provider failure emitted `turn.failed` and exited 1; success terminated with one `turn.completed`. Relay retains its own reservation, timeouts, process-group cleanup and bounded diagnostics; native exit does not prove containment. Launcher/result tests exercise these Relay boundaries with synthetic children. |

This establishes compatibility for the integration and fixture cases described
here. It does not establish arbitrary native tool behavior, every managed
configuration, live provider access or a complete upstream capability interval.
The optional `qualify_installed_native_permissions.py` retains its historical
Task 96 installed-0.160.0 argv-migration scope; it was neither relabelled as
0.167.0 proof nor run in this unprivileged worker.

## Executed qualification

The selected-pin official-release qualifier passed using the real upstream
installer and 0.167.0 Linux x64 musl distribution, downloaded into a disposable
`/tmp` home. Its four deterministic loopback Responses cases covered success,
missing usage, invalid semantic output and provider failure. It checked exact
binary version, release symlink topology, install umask 0077/package roots 0700,
parser options, actual JSONL, schema transmission and semantic parsing, native
identity/usage, stdin, model/effort transmission, isolated homes and effective
approval/sandbox policy. It made no model call and used no credentials.

Two initial attempts failed before installation: this minimal host has no `awk`
command, causing release-metadata parsing to fail, and the GitHub fallback
returned HTTP 504. After identifying that cause, a temporary copy of the
qualifier added only the task-local `awk` wrapper (executing installed
`/usr/bin/mawk`) to the installer's allowlisted PATH. The official installer and
release bytes were unchanged; runtime loopback cases kept their original
allowlisted environment. The candidate then passed, and the current selected-pin
source qualifier passed with the same installer-only accommodation. No system
alias, host installation or global configuration was changed.

The installer/binary warned that PATH helper aliases would not be created under
`/tmp`. Direct execution passed; helper aliases and native tool execution are
not claimed as qualified. This warning remains part of the evidence.

Affected validation passed:

- 33 Python workflow/runtime/launcher-binding/diagnostic contract tests.
- 35 Node launcher, diagnostics, runtime process and usage tests.
- The official selected-release qualifier described above.

The escaping-symlink launcher fixture previously assumed `/etc/hostname`
existed. On this host its absence reached `PATH_UNAVAILABLE` before the intended
escape check. The fixture now points at its own existing synthetic token file
outside the work root and still requires the exact `PATH_OUTSIDE_WORK_ROOT`
refusal before child start. An initial Node invocation also required a private
0600 synthetic consumer copy, as documented in Step 2. Final targeted tests
passed with those portable fixtures.

Task-local traces are under ignored `.codex-sandbox/task217/cli-*`, including
anonymous release/source bytes and initial/final probe and test logs. Source
selection and local compatibility evidence do not prove an installed-host
upgrade, installed namespace enforcement, credentials, production readiness,
native exact-head CI, independent acceptance, Apply or deployment. The worker
cannot inspect native GitHub annotations under its credential/publication
boundary, so warning absence is not established.
