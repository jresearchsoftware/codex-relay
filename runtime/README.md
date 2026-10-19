# Governed Codex runtime and Issue authority

[The controller](../controller/README.md) owns ordinary Issue/remediation
orchestration. This component provides the governed Codex runtime, semantic
result schema, Issue parser and a small adapter for isolated runtime probes.
Run `npm test` here for the runtime contract tests.

The body-field Issue parser is the legacy authority path. Migrated Tasks receive
the complete trusted schema-v3 Request and explicitly selected evidence from
the controller; the worker does not rebuild authority from Issue discussion.
See the [Task workflow guide](../docs/task-workflow.md) and
[authority contract](../contracts/README.md#github-native-task-authority).

The [governed CLI integration](../docs/codex/cli-integration.md) records the exact
0.160.0 baseline, native event/usage semantics, compatibility decisions and
qualification limits.

The runtime uses the deployment-owned [consumer contract](../consumer/README.md)
for the model, explicit effort overrides, commit identities, runtime user and
paths. Omitted effort/Subagents uses the [shared contract resolver](../contracts/README.md).
The worker receives the exact resolved effort/Subagents from immutable admission.
Every governed invocation receives the shared
[progress-bounded policy](../docs/execution-policy.md); it can make evidence-based
corrections within the admitted goal without a fixed correction count. This
never authorizes a duplicate execution or broadens publication/credential scope.

When the consumer enables execution slots, each fixed launcher runs its Codex
child through Bubblewrap with private user/PID/IPC/UTS namespaces, private
`/proc`, `/dev`, `/tmp` and `/run`, read-only operating-system/managed toolchain
and pinned CLI files, and one writable admitted checkout. Network access remains
available for the model and task dependency downloads. Host credential directories,
other checkout roots and host sockets are not mounted. Managed General Runner
pool instances may share one trusted runner UID and one non-root runtime UID;
each attempt still has its own checkout, HOME/CODEX_HOME, XDG directories, cache,
temporary files, journal, diagnostics and process lifetime. Namespace boundaries
isolate concurrent workers even when their host UID is the same. Runner journals
and primary diagnostics live outside the worker checkout. Protected consumer
configuration binds a repository to its runtime user; Task and PR content cannot
select that identity or a launcher. The launcher marks an inner child
as unknown when Bubblewrap started but Codex execution has not been observed.
Legacy configurations retain their existing launcher behavior. Installed UID,
sudo, namespace, process containment and concurrent isolation require separate
host qualification; local source tests alone do not prove those properties.

## Durable diagnostics and sandbox finalization

The dispatcher reserves a protected, bounded diagnostic capsule before launching
the governed runtime. The runtime records each operation before crossing it,
including preflight, launcher spawn, result parsing and diagnostic persistence.
It records child observations separately from the outer dispatcher's exit. An
unexpected exception is normalized without publishing its message, stack or raw
path. Bounded, redacted OS fields and path context can be stored in the primary
protected diagnostic bundle; Writer receives only safe codes, lifecycle states
and references.

The capsule lives under the configured runner-owned `attemptRoot`, outside the
mutable checkout and Codex sandbox. File and directory fsync establish a durable
frontier before runtime mutation or cleanup. Primary capture/store failure leaves
its own failure code in this independent capsule. If an update itself fails, the
preceding operation remains inspectable and destructive cleanup is prohibited.
The initial reservation must succeed before a child can start; a full or
unavailable fallback store blocks admission rather than launching without it.

`runGovernedCodexTask()` never deletes the sandbox. It captures the sandbox's
device/inode before child launch and prepares diagnostic state. The outer
dispatcher then reaps its owned process group and invokes
`finalizeRuntimeArtifacts()`. The model-UID launcher separately reaps its own
child process group and reports bounded native containment evidence. A launcher
exit or a successful runner-UID group signal alone is insufficient containment.
Direct runtime probes must also arrange containment before using the finalizer.
Existing sandboxes are retained, never adopted or permission-repaired as part
of a new invocation.

Native cancellation reaches the routing controller directly through the workflow's
`exec` launch. The controller holds SIGINT/SIGTERM through terminal Writer routing;
its separate fd3 lifetime pipe aborts a detached dispatcher if that caller dies.
The runtime keeps launcher stdin open across sudo as a second lifetime pipe;
the task input still comes from the admitted file. EOF or a cancellation signal
asks the model-UID launcher to terminate its group, escalating to SIGKILL after
one second. Only the inner acknowledgement plus disappearance of the outer group
permits `reaped`. Missing acknowledgement stays `unknown` and retains artifacts.
Forced controller death can prevent its terminal journal/Writer receipt even
when these lifetime pipes clean up the model. That original attempt remains
unresolved; cleanup does not authorize a replay or historical record repair.

The fixed launcher cleanup ABI is
`cleanup --cwd CHECKOUT --sandbox-identity DEVICE:INODE`. It runs as the same
runtime user through the existing sudo rule and reads no credentials. Its fixed
Python helper permits only the `.codex-sandbox` of a direct `run-N`/`event-N`
checkout under the configured work root, matching the pre-child identity.
Plural installations select only the fixed repository roots and runtime users
from protected installation configuration, as execution does; flat legacy roots
retain their existing behavior, including retained flat attempts after plural
installation. Cleanup never adds a caller-selected root.
Descriptor-relative traversal uses `O_NOFOLLOW`, rejects filesystem transitions,
and unlinks symlinks without following them. It neither changes private modes nor
grants root or arbitrary-path deletion. Cleanup is bounded to 100,000 entries,
depth 128 and 30 seconds (with a bounded outer helper timeout).

Primary diagnostic failure, unknown containment or missing identity leaves the
attempt artifacts in place. Cleanup failure may have removed some entries; its
retained pointer means inspect the remaining artifacts, not that every original
byte survived. The pre-cleanup capsule is already durable, and cleanup errors
record operation, syscall, bounded path context and store status independently.
A successful ordinary run removes the sandbox and releases its fallback slot.
See the [controller retention contract](../controller/README.md#runtime-diagnostic-retention)
for the bounded inspection and disposal policy. These local contracts do not
claim production qualification or authorize a deployment.
