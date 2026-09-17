# Consumer integration reference

This is the external ABI of one selected, qualified Relay tree for one consumer.
It is a specification, not an installer, production wrapper or deployable
workflow. Read the [architecture](architecture.md) and start with the plain
[consumer](../consumer/fixtures/example.json), [Reviewer](../examples/reviewer-mcp.json)
and [diagnostics](../examples/diagnostics.json) examples. All example identities,
paths and artifact hashes are synthetic; replace and independently qualify them.

Use the [deployment interface](../deploy/README.md) to select, acquire,
install and verify the complete product tree. Relay binds the entrypoints
below to the resolved immutable identity and manages configuration, mutable
state, Reviewer build outputs and activation in separate protected paths.

## Processes and identities

| Process / entrypoint | Invoker and identity | I/O and responsibility |
| --- | --- | --- |
| `controller/src/entrypoint.mjs` | Trusted consumer routing workflow, runner identity | Reads GitHub event file/environment; stdout terminal JSON, stderr bounded errors/Actions warnings; reserves and coordinates one attempt |
| `controller/src/codex-dispatch.mjs` | Fixed `paths.dispatch` wrapper, isolated dispatcher identity | No normal argv; stdin version-2 execution envelope (512 KiB); stdout JSON execution receipt, stderr bounded JSON failure; `--check-runtime` probes loading only |
| `controller/src/privileged-writer-helper.mjs` | Fixed `paths.writerHelper` via `/usr/bin/sudo -n`, uid 0 under consumer's Writer lock | No argv; stdin bounded broker JSON (145 MiB including imported bundle), stdout repository-bound receipt, stderr sanitized failure JSON; root-owned `env -i` wrapper supplies config |
| Consumer's `paths.launcher` | Dispatcher via `/usr/bin/sudo -n -u <runtimeUser>` | Fixed executable; translates the launcher ABI below to its governed Codex installation; worker has no Writer/Reviewer authority |
| `controller/src/diagnostic-store.mjs` | Fixed `paths.diagnosticsStore` wrapper, protected diagnostics identity | Stdin bounded diagnostic JSON (16 MiB); stdout store receipt, stderr failure JSON; `--check-runtime` probes loading only |
| `controller/src/recover-attempt-publication.mjs` | Separately owner-authorized recovery workflow/operator | No argv; stdin `{operation:"inspect",runId,attemptId}` or `{runId,attemptId,authorizationId}`; stdout result/stderr failure; never starts Codex |
| `contracts/src/step-synchronization.mjs` | Ordinary authenticated owner client | Stdin `{operation:"prepare",pullRequest}` or `{operation:"synchronize",pullRequest,reviewId}`; stdout JSON, stderr bounded failure; label/title metadata only |
| `reviewer-mcp-http` (`reviewer/src/main.rs`) | Dedicated Reviewer service identity behind trusted mTLS terminator | `--config /absolute/reviewer-mcp.json` (or `REVIEWER_MCP_CONFIG`); HTTP JSON-RPC on `/mcp`; startup logs expose effective publication mode |

`runtime/src/controller.mjs` is an Issue execution library entry, not another
deployment daemon. The Node directories are one qualified source tree, with
intentional cross-directory imports. Keep the Rust/Node shared CR definition
and all modules from the same revision.

## Consumer paths and environment

`RELAY_CONSUMER_CONFIG` is an explicit absolute JSON path for Node entrypoints.
No working-directory discovery or default consumer exists. The file must be
regular, non-symlink, at most 16 KiB, and not group/world writable. The root
Writer also verifies root ownership and safe ancestors. Config is frozen once
per process; its digest binds an attempt. Request JSON cannot select paths.

| `paths.*` key | Mapping / consumer obligation |
| --- | --- |
| `workRoot` | Dispatcher checkout parent; contains `<attemptId>`; isolated per consumer |
| `attemptRoot` | Runner attempt journals, outside worker-writable state |
| `dispatch` | Fixed wrapper for `controller/src/codex-dispatch.mjs`; recreates its trusted config/PATH |
| `writerHelper` | Fixed root wrapper for `controller/src/privileged-writer-helper.mjs`; holds the per-consumer serialization lock |
| `launcher` | Consumer-provided governed Codex launcher; no implementation is shipped here |
| `diagnosticsConfig` | Deployment-owned diagnostics JSON described below |
| `diagnosticsStore` | Fixed wrapper for `controller/src/diagnostic-store.mjs`; recreates trusted config/PATH |
| `diagnosticsRoot` | Protected diagnostic bundles; never worker/PR publication input |
| `credentialEnv` | Root-only Writer credential metadata file |
| `credentialKeyFile` | Root-only Writer App private-key file, exactly matched by credential metadata |
| `claimRoot` | Root Writer publication journals under `publication-v2/` and trusted temporary Git import |

The routing entrypoint reads `GITHUB_EVENT_PATH`, `GITHUB_EVENT_NAME`,
`GITHUB_REF`, `GITHUB_RUN_ID`, `GITHUB_TOKEN`, and `RELAY_CONSUMER_CONFIG`.
The token is a workflow read token (contents/Issues/PR/Actions reads as needed),
passed only to trusted authority/Git reads; it is not a worker token. Recovery
also uses `GITHUB_TOKEN` for workflow reads. Step synchronization instead needs
the configured human owner's ordinary token, including Issue/PR metadata writes.

Dispatch and Writer adapters start helpers with only `PATH=/usr/bin:/bin`,
`LANG=C`, `LC_ALL=C`; each fixed wrapper must recreate `RELAY_CONSUMER_CONFIG`
and pin its runtime executable. The optional Writer environment aliases
`RELAY_WRITER_CREDENTIAL_ENV`, `RELAY_WRITER_CREDENTIAL_KEY_FILE` and
`RELAY_WRITER_CLAIM_ROOT`, if present, must equal consumer config; they cannot
override it. `CODEX_RUNTIME_TIMEOUT_MS` is a trusted runtime input (1000–7200000
ms, default 5400000); it is not automatically forwarded to the worker.

Writer `credentialEnv` is literal `KEY=value`, one per line: `GITHUB_APP_ID`,
`GITHUB_APP_INSTALLATION_ID`, `GITHUB_APP_PRIVATE_KEY_FILE`. Blank lines and
lines starting `#` are allowed. No shell quoting, expansion or duplicate keys;
the three values must match consumer configuration. Both credential files must
be root-owned with no group/other permissions. Never place keys in this tree.

Diagnostics config is `{"schemaVersion":"1.0","mode":"normal"}` (or `debug`).
The store supports an optional positive `retentionCount` (default 8). Keep it
bounded by consumer policy. Normal/debug diagnostic capture is limited to
1/4 MiB; stored bundles are private, redacted and retained outside the checkout.

## Launcher ABI and sudo isolation

The following are **consumer launcher arguments**, not a promise that a raw
Codex CLI accepts these flags:

```text
exec --json --model MODEL --effort EFFORT --input-file INPUT --cwd CHECKOUT --issue N
exec --operation review-remediation --json --model MODEL --effort EFFORT --input-file INPUT --cwd CHECKOUT --pull-request N
```

There is no stdin prompt. The runtime writes exact task input plus execution
policy to `<checkout>/.codex-sandbox/task-input.md`, and the result schema to
`<checkout>/.codex-sandbox/codex-result-schema.json`. The automatic argv does
not pass a schema flag: the launcher must locate that fixed schema in the
validated sandbox, enforce it and adapt to its qualified Codex version.

Stdout must be JSONL only (16 MiB capture bound). The normal native form is
`item.completed` with `item.type="agent_message"` and JSON semantic result in
`item.text`; `task_result` with `result` is also accepted. The semantic result
has only `status` (`success`/`blocked`), `summary`, `validation` (claims), and
`blockedReason` (empty on success, nonempty on blocked). See the
[result schema](../runtime/src/codex-result-schema.mjs). Native `thread_id` and
`session_id`, when emitted, supply runtime identity; absent values stay unavailable.

Stderr carries bounded diagnostics, not functional results. A launcher diagnostic
is a JSON line with `source="relay-codex-launcher"`, `schemaVersion=1`, uppercase
`code`, integer `bytes` (0–1048576), and a control-free `preview` (at most 1024
bytes), plus `truncated`. Report inner `childStarted`/`childState`
(`started`/`not_started`/`unknown`), optional `childExitCode`, `signal`, and
`primaryCause` truthfully. Outer launcher exit is not evidence that Codex started.
Optional debug data is bounded by the runtime parser and must be redacted.

The runtime builds the following environment **before sudo**:

| Purpose | Values recreated for the worker |
| --- | --- |
| Narrow inherited locale/runtime inputs | `PATH`, `LANG`, `LC_ALL`, `TZ`; cross-platform builder also permits `SystemRoot`, `WINDIR`, `ComSpec`, `PATHEXT` |
| Isolated homes/state | `HOME`, `USERPROFILE`, `CODEX_HOME` = sandbox `home`; `XDG_CONFIG_HOME`, `XDG_CACHE_HOME`, `XDG_DATA_HOME`, `XDG_STATE_HOME` = sandbox `config`, `cache`, `data`, `state` |
| Temporary and input paths | `TMP`, `TEMP`, `TMPDIR` = sandbox `tmp`; `CODEX_TASK_ROOT` = checkout; `CODEX_SANDBOX_ROOT`, `CODEX_ALLOWED_INPUT_ROOT` = sandbox |
| Git isolation | `GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL=/dev/null`, `GIT_CONFIG_SYSTEM=/dev/null`, `GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=Never`, `GIT_OPTIONAL_LOCKS=0`, `GIT_SSH_COMMAND=false` |
| Git identity/config | Configured `GIT_AUTHOR_NAME`, `GIT_AUTHOR_EMAIL`, `GIT_COMMITTER_NAME`, `GIT_COMMITTER_EMAIL`; `GIT_CONFIG_COUNT=1`, `GIT_CONFIG_KEY_0=safe.directory`, `GIT_CONFIG_VALUE_0=<checkout>` |

The sudo invocation has **no `-E` or blanket preserve-env option**. sudo policy
may reset HOME and remove these variables. A passing pre-sudo environment test
therefore does not prove isolation inside the launcher. The consumer must
recreate this environment after sudo using trusted checkout/identity inputs
(the pinned `buildCheckoutCodexEnvironment` function expresses the contract),
or prove an equally narrow preservation policy. Do not pass through arbitrary
caller `GIT_CONFIG_*`, `NODE_OPTIONS`, shell startup variables, SSH agents,
GitHub tokens or host homes. Fix PATH to trusted runtime directories.

`security-contracts.test.mjs` drops the pre-sudo environment in a child process,
recreates it and proves synthetic host Git identity/credential-helper config is
not read. It does not invoke real sudo or qualify any installed wrapper.
The installation must repeat the observation **inside its actual launcher**
under its actual sudoers, including Git config/helper/SSH and credential access.
Codex authentication is a separately governed launcher responsibility; recreating
a sandbox HOME is not authentication provisioning. Writer/Reviewer credentials
must never become available to that model process.

The dispatcher owns the outer process group; the launcher and worker must stay
in it, forward termination and not detach background children. Return terminal
state only after the owned execution is reaped. Consumer OS/container policy
must prevent access to privileged state, other jobs, host sockets and credentials.
Environment filtering alone is not filesystem, process or network containment.

## Workflow and App contract

`routingWorkflow`, `recoveryWorkflow` and `validationWorkflow` are distinct
consumer-owned `.github/workflows/*.yml` or `.yaml` paths. The routing entrypoint
requires the configured owner's event on `refs/heads/<baseBranch>`. Live run
admission checks repository, owner actor/triggering actor, path, event, in-progress
status and first run attempt. It is not proof of the workflow code's safety.

| Routing event | Required run-name display |
| --- | --- |
| `workflow_dispatch`, inputs `route`, `task`, `step`, optional `pull_request` | `Auto implementation · Task N · Step S`, `Auto remediation · Task N · Step S · PR #P`, or `Manual handoff · Task N · Step S` (append ` · PR #P` for a PR) |
| `issues: labeled`, ready label | `<phase> · Task N · <all label names joined by ' · '>`; the Step/ready-label projection binds admission |
| `pull_request_target: labeled`, ready label | `<phase> · PR #P · <current PR title>`; Issue/PR Step labels and PR title must agree |

`<phase>` is `Auto implementation`, `Auto remediation` or `Manual handoff` as
applicable. Formats are implemented in
[launch-metadata.mjs](../controller/src/launch-metadata.mjs); do not derive Task
or Step from an arbitrary title. Ready labels are owner launch commands;
`step-N` alone grants no execution. Consumer workflow concurrency and the
root Writer lock serialize overlapping attempts. A rerun is not fresh authority.

The validation workflow must check the **candidate head SHA**, not silently a
synthetic merge or moving branch, and implement the applicable declared checks.
The optional API lookup selects `validationWorkflow` runs with that `head_sha`
and `event=pull_request`. Automatic completion does not call that lookup or
establish native CI/mergeability; the owner/reviewer must inspect exact-head
evidence independently. Passing candidate-controlled tests alone does not prove
that the tests themselves remained trustworthy.

Writer installation tokens request `metadata:read`, `contents:write`,
`issues:write`, `pull_requests:write`, `workflows:write`, restricted to the
configured repository. Reviewer tokens request `metadata:read`,
`pull_requests:write`, `checks:write`, also restricted to that repository.
Install separate Apps with the corresponding repository permissions; live App
slug/ID, returned actor/check identity and configured installation IDs are bound.
The workflow read token supplies Actions reads separately; do not broaden the
worker's permissions to satisfy trusted API reads.

## Public dogfood trust

The Writer permits task-owned `.github/workflows/` changes and has workflow-write
permission. A model-authored same-repository head remains untrusted code even
when the commit actor is the Writer. Synthetic qualification demonstrates that
such workflow bytes can be published without executing them or certifying CI.
GitHub App token writes can trigger workflows; do not rely on `GITHUB_TOKEN`
recursion suppression for Writer pushes. See [GitHub's token behavior](https://docs.github.com/en/actions/concepts/security/github_token).

Any later public dogfood installation must enforce these conditions **outside
candidate-controlled YAML**, before activation:

- Ordinary fork and same-repository candidate code runs only in disposable,
  unprivileged validation environments with no protected secrets, host access
  or persistent privileged runner reachability.
- Runner access must be restricted to an independently trusted workflow/ref and
  owner-controlled launch path. Labels or an `if` in a candidate-editable workflow
  are insufficient. If the available GitHub/host controls cannot enforce this,
  keep privileged public dogfood disabled.
- Trusted routing and fixed helpers come from the already qualified revision.
  PR code is confined to the worker sandbox; never check it out and execute it
  in a credentialed `pull_request_target`/`workflow_run` control job.
- Independent exact-head review examines workflow/test changes as well as
  implementation. Record which trusted workflow/tool revision produced results.
  A candidate cannot qualify and activate its own privileged successor; activation
  follows independent qualification and an owner decision.

These requirements are consistent with [GitHub's self-hosted runner and untrusted
checkout guidance](https://docs.github.com/en/actions/reference/security/secure-use).
Repository source checks cannot prove runner group/ref restrictions, organization
policy, ingress or installed containment. Deployment preserves owner-managed
registration and group policy while reconciling the runner's local installation.

## Reviewer runtime contract

The [plain config](../examples/reviewer-mcp.json) is validated by the real loader.
Required fields are `repository`, `baseBranch`, `reviewCheckName`, `writerActor`,
`githubApp.{slug,appId,installationId,expectedActor}`, `artifact.{commit,sha256}`,
and `service.{name,bind_mode,bind_address,bind_network,gateway_validated,bind_port,mount_path}`.
IDs are decimal strings. `service.name` is `reviewer-mcp`; `mount_path` is `/mcp`.
For `a_only_loopback`, use exactly `127.0.0.1`, empty network and `false` gateway
validation. `private_gateway` (historical alias `nexus_gateway`) requires a
non-loopback private IPv4 gateway, bounded network name and `gateway_validated=true`.
That flag is an operator assertion, not a network probe. Never bind publicly.

`artifact.commit` (40 lowercase hex) and `artifact.sha256` (64 lowercase hex)
are **operator-recorded evidence metadata**, shape-validated only. The running
binary does not verify itself against them. Example hashes prove no artifact.
Ansible-only descriptive fields such as `execBoundary`, `evidenceRoot`,
`credentials`, `rollback` and `schemaVersion` do not configure execution.

| Reviewer environment | Meaning |
| --- | --- |
| `REVIEWER_MCP_CONFIG` | Config path alternative to `--config`; CLI takes precedence |
| `REVIEWER_CLIENT_CA_FILE` | Required readable trusted OpenAI client CA PEM for certificate verification |
| `GITHUB_APP_ID`, `GITHUB_APP_INSTALLATION_ID` | Required at startup; must match Reviewer config |
| `GITHUB_APP_PRIVATE_KEY_FILE` | Reviewer App key required for GitHub API calls, including target reads |
| `REVIEWER_RELAY_ENABLED` | Only exact `true` enables review/check publication; absent, `false` or any other value disables it |
| `REVIEWER_RELAY_DB` | Protected persistent SQLite path; default is relative `reviewer-relay.sqlite3`, so installations should explicitly set an absolute path |

There is one publication switch. The obsolete `mutation` field is rejected at
startup, even when its value is `none`; remove it when upgrading this candidate.
Startup emits `publication_mode` with `enabled=true/false`. Disabled instances
still initialize durable state, list tools and can perform authenticated target
reads; `submit_pr_review` returns `RELAY_DISABLED` without GitHub publication.
It is not an offline/no-filesystem-write mode. Enabled instances validate the
external caller's supplied verdict/CR, target and identity before publication.

Ingress must strip spoofed identity headers, verify the client certificate chain
and forward `X-OpenAI-MTLS-Verified: 1` plus URL-encoded PEM in
`X-OpenAI-MTLS-Client-Cert`. The service validates that certificate against its
CA and the `mtls.prod.connectors.openai.com` SAN. TLS termination and network
exclusivity remain deployment obligations; localhost headers alone are not
client authentication. See [Reviewer transport](../reviewer/README.md).

SQLite WAL plus the main database holds reservation/publication/check recovery.
Use durable storage restricted to this consumer/Reviewer, retain it across
restarts and account for WAL sidecars in backups. Deleting/replacing state can
destroy deduplication evidence. Changing configuration under retained operations
requires reconciliation; there is no advertised automatic state migration plan.

## Consumer validation identifiers

Both Node consumer JSON and Reviewer JSON may declare the same optional
`validationNames` array: at most 32 unique IDs matching `[a-z][a-z0-9-]{0,63}`.
It extends the historical [v2 vocabulary](../contracts/README.md), with a maximum
of 12 unique required checks per CR unchanged. IDs are obligations, never shell
commands; trusted consumer code/workflows own their implementation and evidence.
Unknown names fail closed in Reviewer schema/rendering and Node admission.
The allowlist cannot arrive in a tool request or CR.

Example: the [inventory API](../consumer/fixtures/inventory.json) declares
`pytest-inventory`, `mypy-inventory`, `openapi-compatibility`; copy those declarations
into its Reviewer config too. Qualification follows actual rendered native review
bytes through Node admission for these names. Omitting declarations preserves
existing configs/v2 fixtures. Old binaries reject extended config/custom IDs:
upgrade the paired Reviewer and Node tree before using them. Adding declarations
changes the Node consumer digest; reconcile existing attempts under their
original config rather than silently resuming them under new policy.

## Secret-scanning policy

| Surface | Bytes checked | Bounded detection policy |
| --- | --- | --- |
| Writer publication (`trusted-git.mjs`) | Commit metadata and every introduced blob in the admitted first-parent chain, including transient/later-deleted content and merge resolutions | GitHub token and PEM private-key marker families |
| `contracts/src/secret-scan.py` | Tracked working-tree files | Same GitHub/private-key families |
| `scripts/check-candidate.py` | Tracked candidate working-tree files | Those families plus AWS access-key-ID and OpenAI-like key markers; also JSON/link checks |

This distinction is intentional: publication guards a commit chain with the
existing narrow hard rejection policy; candidate preparation adds broader tip
hygiene. The candidate scanner does not scan history. Synthetic tests pin both
policies, including transient rejection and the extra candidate-only classes.
No scanner detects every possible secret, arbitrary passwords, encoded values,
private source or business knowledge. A clean tree is not a confidentiality proof.
Operators must review publication content and configure consumer-specific controls
where these marker classes are insufficient; scan failures never print key bytes.

## Annotated synthetic scenario

1. The example owner admits Issue 24 at exact base A, with `step-1`, a resolved
   profile and allowed scope. A trusted routing run named
   `Auto implementation · Task 24 · Step 1` reserves `run-99`. The runner attempt
   journal and Writer `publication-v2/99.json` bind the immutable consumer digest.
2. The isolated worker implements within that authority, commits B and returns
   semantic JSONL. After the group is reaped, Writer imports object bytes into
   fresh trusted Git, validates the task chain and scans introduced blobs. It
   reserves publication intent before an ordinary push and observes B remotely.
3. The PR and one terminal Codex Outcome identify B as pending fresh independent
   review. Worker validation strings are claims; consumer exact-head checks and
   review remain separate. A blocked worker may still preserve useful commits;
   unknown/uncontained execution cannot be relabelled successful.
4. An external ChatGPT reviewer inspects B and supplies a structured CR. The Rust
   service validates and publishes `REQUEST_CHANGES` at B, with the readable
   findings plus canonical `reviewer-executable-cr` JSON, and a SHA-bound check.
   Its SQLite record supports duplicate/recovery handling.
5. The ordinary owner client synchronizes Issue/PR to the CR's `step-2`. A fresh
   owner launch `Auto remediation · Task 24 · Step 2 · PR #25` admits B exactly.
   The CR names declared checks, not command strings. Changed head, owner,
   repository, undeclared names or mismatched Step blocks admission.
6. Remediation produces C. Exact-head validation and external review repeat for
   C; approval on B cannot accept C. The owner decides merge/activation separately.
   An ambiguous publication uses the existing owner-authorized recovery path,
   never another blind model execution.

`scripts/qualify.py` exercises corresponding real handlers/modules against
synthetic Git and loopback GitHub for example, canary and inventory consumers.
It is local contract qualification, not a live installation, paid-model run,
runner security test or production acceptance.
