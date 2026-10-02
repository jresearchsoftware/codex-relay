# Governed Codex runtime and Issue authority

[The controller](../controller/README.md) owns ordinary Issue/remediation
orchestration. This component provides the governed Codex runtime, semantic
result schema, Issue parser and a small adapter for isolated runtime probes.
Run `npm test` here for the runtime contract tests.

The runtime uses the deployment-owned [consumer contract](../consumer/README.md)
for the model, explicit effort overrides, commit identities, runtime user and
paths. Omitted effort/Subagents uses the [shared contract resolver](../contracts/README.md).
The worker receives the exact resolved effort/Subagents from immutable admission.
Every governed invocation receives the shared
[progress-bounded policy](../docs/execution-policy.md); it can make evidence-based
corrections within the admitted goal without a fixed correction count. This
never authorizes a duplicate execution or broadens publication/credential scope.

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
`finalizeRuntimeArtifacts()`. A launcher exit alone is insufficient containment.
Direct runtime probes must also arrange containment before using the finalizer.
Existing sandboxes are retained, never adopted or permission-repaired as part
of a new invocation.

The fixed launcher cleanup ABI is
`cleanup --cwd CHECKOUT --sandbox-identity DEVICE:INODE`. It runs as the same
runtime user through the existing sudo rule and reads no credentials. Its fixed
Python helper permits only the `.codex-sandbox` of a direct `run-N`/`event-N`
checkout under the configured work root, matching the pre-child identity.
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
