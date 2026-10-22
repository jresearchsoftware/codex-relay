# Relay consumer contract

One Relay artifact serves explicitly configured repositories, with one selected
repository per process and shared installation settings.
Set `RELAY_CONSUMER_CONFIG` to an absolute path to a deployment-owned JSON file
matching [the validator](consumer-config.mjs). There is no repository search or
implicit consumer fallback. [Example](fixtures/example.json) and
[isolated canary](fixtures/canary.json) are non-secret qualification inputs;
their paths and IDs do not authorize access to any deployed system.

Configure exactly one of the existing `repository` string or a nonempty unique
`repositories` list. All owner, App/installation, controller, profile and managed
pool settings remain shared. For example, replace the example's `repository`
field with:

```json
"repositories": ["example-org/project-a", "example-org/project-b"],
"repositoryRuntimeUsers": {"example-org/project-b": "relay-project-b"}
```

The optional `repositoryRuntimeUsers` map accepts only configured repositories
and valid non-root runtime names. Omitted entries use the shared
`runtimeUser`. It selects an execution identity without adding an access-control
model or changing owner, Writer or Reviewer authority. Explicit independent slot
runtime users remain unchanged; slots using the shared default use the selected
repository override.

Plural configuration requires an explicit `RELAY_REPOSITORY`; a trusted routing
process may use `GITHUB_REPOSITORY` when the former is absent. Either selection
must exactly match a configured target. There is no first-target fallback, even
for a one-element `repositories` list. Legacy `repository` configuration keeps
its implicit selection and ignores unrelated `GITHUB_REPOSITORY` values; an
explicit `RELAY_REPOSITORY` must still match it. Installed lifecycle commands
use their configured environment repository as an explicit anchor. Root Writer
checks the request's configured target before importing repository-bound code.

| Consumer input | Used by |
| --- | --- |
| `repository` or `repositories`, `owner`, `baseBranch` | Selected API paths, owner admission, PR binding, exact base observation and Git fetch/publication |
| Optional `repositoryRuntimeUsers` | Trusted runtime identity overrides within a plural installation |
| `taskBranchPrefix` | Task branch admission and omitted-branch derivation |
| `writerApp`, `reviewerApp` | Separate App slugs, numeric App/installation IDs and expected bot actors |
| `writerIdentity`, `remediationIdentity` | Worker commit author/committer and trusted object validation |
| `routingWorkflow`, `recoveryWorkflow`, `validationWorkflow` | Exact native workflow identity checks and lookups |
| `defaultProfile` | Required consumer-owned model; optional effort override for omitted authoring fields |
| `paths`, `runtimeUser` | Installed helpers, state/credential locations and non-root worker identity |
| Optional `workGroup` | Primary launch group for a serial worker; must match deployment `environment.codexWorkGroup` |
| Optional `validationNames` | Up to 32 unique bounded consumer check IDs; declare the same list in Reviewer config |
| Optional `executionSlots` | Bounded resource slots with checkout/journal/diagnostic roots and fixed helper bindings; explicit legacy slots keep independent identities |
| Optional `generalRunnerPool` | Managed physical `desiredCapacity` (1–32), with derived stable slots and shared trusted runner/default non-root runtime identity |

The complete installation configuration is loaded once, validated and frozen.
Its digest accompanies every admitted attempt independently of the selected
repository or slot. The selected process view retains one concrete `repository`.
A different or missing digest cannot resume publication,
including blocked-admission replay. Existing pre-configuration attempts retain
their original reviewed release and bindings; ordinary configuration replacement
requires reconciliation before cutover. The bounded
[SERIAL-to-pool transition](../docs/serial-pool-migration.md) instead seals and
preserves the complete original attempt set and readers. Do not invent a digest
or discard publication reservations. An admitted worker executes its
resolved explicit model/effort. Relay never reads a moving Model Landscape.
For a managed pool only, changing `generalRunnerPool.desiredCapacity` preserves
the execution digest. All repository, identity, path and security fields remain
bound, including the complete repository list and runtime-user map. Its internal
slot layout remains fixed across capacity changes. The single-repository digest
and paths retain their historical representation. Replacing `repository` with
`repositories` changes the installation digest, even for a one-element list.
That change alone does not migrate or rebind retained attempts. Reconcile them
under their original reviewed configuration/release before ordinary cutover, or
use the separately qualified bounded SERIAL-to-pool transition to preserve their
original context. New namespaced stores must not hide retained legacy records
or bypass their original admission and recovery bindings.

For plural configuration, the selected `workRoot`, `attemptRoot` and
`diagnosticsRoot` append `/repositories/<owner>/<repository>` to their configured
root, including those roots in every execution slot. Helpers, diagnostics
configuration/store executable, credentials and `claimRoot` remain shared.
Protected repository records are separated by repository beneath the shared
Writer state root so equal repository-local run or Task numbers cannot collide.
The publication lock, lifecycle admission state and physical pool occupancy
cover the entire installation.

`executionSlots`, when present, contains 1–32 entries with `id`, `runnerName`,
`runnerUser`, `runtimeUser`, `workGroup` and `paths`. Slot paths contain exactly
`workRoot`, `attemptRoot`, `dispatch`, `launcher`, `diagnosticsConfig`,
`diagnosticsStore` and `diagnosticsRoot`. The `primary` entry preserves the
existing top-level paths and runtime user. Each additional legacy explicit slot
has distinct Unix identities and group; all slots keep non-overlapping
roots/helpers. Managed slots may share runner/runtime users and work group.
Writer credentials,
the root publication lock and `claimRoot` belong to the installation and remain
outside every worker-writable root. Separate installations retain separate
namespaces, credentials and state. A plural installation shares its existing
Writer/Reviewer identities and App installations across configured repositories;
managed pool members share the General Runner identity and repository views may
select their own configured runtime user. A slot is a physical execution resource,
independent of repository selection; adding a repository does not add pool capacity.

Each slot's configured `workGroup` is also the worker process's primary group,
selected through the fixed `sudo -g` launch and cleanup interface. This leaves
the Unix account's primary group unchanged and preserves the installation digest
and slot authority. A serial configuration without slots may select the same
behavior with top-level `workGroup`; omission retains its old launch ABI and
digest. A top-level group with slots must match the primary slot. Changing a
serial group requires existing installation/admission reconciliation; it cannot
rebind retained attempts.

The complete installation configuration has one digest, independent of which
slot runs a Task. A fresh automatic admission verifies the configured runner
name and actual runner UID; the root wrapper independently binds its trusted
sudo caller UID. Writer saves the selected slot ID in the immutable protected
execution envelope. It derives retained journal/checkout paths from that record,
never caller paths. Omitted historical slot bindings use the preserved primary
locations. An active or unresolved slot cannot admit another worker. Per-Task
conflict checks and the global lifecycle drain cover the entire installation.
The public canonical authority schema and resolved Task profile remain unchanged.
For retained explicit slots, ordinary runner-side publication recovery uses the original execution slot;
a workflow arriving on another slot stops with `EXECUTION_SLOT_BINDING_CHANGED`
before reading or mutating its journal. Root-owned prepublication recovery can
read the original immutable slot through its separately authorized fixed path.
The parallel recovery projection supplies an optional `execution_slot` choice
with `primary` as its historical default, and targets a deterministic runner
label bound to repository, namespace and slot. The fixed workflow guard proves
that the selected slot, runner name and UID agree. Protected inspection reports
the retained slot without accepting a caller-selected journal or checkout path.
Actual native targeting and installed identities require TEST qualification;
source projection and deterministic tests alone do not establish that evidence.

Managed recovery uses any active physical pool member with the configured shared
runner identity. Trusted Writer supplies the original slot through the retained
claim before journal lookup; the caller cannot supply a journal path. Native
recovery authorization and reserve-before-publication remain binding. This
preserves recovery after a physical runner is retired and removes the managed
workflow's per-slot recovery choice. Pool names/labels and desired capacity are
shared across eligible repository configurations; capacity is never multiplied
by repository or runtime user. See the [Apply contract](../deploy/README.md#shared-managed-general-runner-pool).

With no explicit consumer effort override, the shared execution resolver uses
the schema representation of [AGENTS.md](../AGENTS.md#work-within-the-admitted-goal).
Omitted Subagents uses that same resolver. Explicit Task/CR values take priority.
The ordinary project profile is `gpt-6.1-sol` / `xhigh` / Subagents `On`.
This is Relay repository development policy, not a mandatory profile for every
consumer. Schema-v3 Requests contain the complete already-resolved profile;
legacy authoring defaults do not fill missing typed Request fields.
Consumer configuration still supplies the required model; the deployment
example and backend default use this project model. Explicit consumer profiles
and their digests are preserved, as are explicit live Task/CR overrides.

The privileged Writer receives its configuration path from the root-owned
`env -i` wrapper. It verifies root ownership and non-writable ancestors before
credential access. Request JSON cannot select configuration, executable paths,
or credentials; its explicit repository must be a configured target. Keep
configuration outside the worker checkout and worker-writable directories.
Writer credentials and shared protected state belong to one installation.
Installed wrappers and sudoers must bind the same reviewed paths.

Reviewer uses its deployment-owned `reviewer-mcp.json`: either `repository`
or `repositories`, plus `owner`, `baseBranch`, `reviewCheckName`, `writerActor`,
and `githubApp` are required. The two repository forms cannot be combined.
All other Reviewer settings and its App/installation remain shared; each MCP
operation selects an explicit configured repository. Consumer/Writer and Reviewer
configuration must cover the intended installation targets.
The deployment projects `owner` from the existing consumer owner; Reviewer
requires that human owner's canonical linked Issue before Step mutation.
Its App and installation IDs must match its credential environment; the live
App ID/slug, returned review actor and returned check slug must match the
configuration. Bind settings, operator-recorded artifact metadata and the separate Reviewer
database remain deployment inputs. The [integration reference](../docs/integration-reference.md)
lists the complete runtime config, environment and publication-mode contract.
The configuration must stay fixed for the
lifetime of that instance and its retained publication state.

Product invariants remain fixed: same-repository heads/bases (fork execution is
unsupported), exact heads, separate owner/Writer/Reviewer authority, bounded
payloads, secret redaction, safe Git paths and regular-file modes, non-force
publication and reservation-based duplicate suppression. `step-N`,
`codex-ready-auto`, `codex-ready-manual`, the historical CR validation tokens and
terminal status values are protocol vocabulary. The historical
`jresearchsoftware-reviewer-relay:v1` comment marker is a retained wire namespace
for duplicate recovery; it grants no organization or App authority. The local
`refs/remotes/main` import ref is a private alias for the configured base SHA.

On current v4 Tasks, Step labels project the protected Writer admission; retained
v3 attempts keep their exact trusted Request/CR Step. The stable Issue charter
replaces mutable body execution fields. A qualified v4 installation does not
start fresh legacy/unmarked or v3 Task/CR chains. Use current v4 authority or an
explicitly owner-authorized migration; retain old admitted attempts for safe
completion, Outcome publication and exact recovery. Use the [Task workflow guide](../docs/task-workflow.md) and
[authority/migration contract](../contracts/README.md#github-native-task-authority)
before opting in; a config example or typed comment alone does not migrate a Task.

The connected App must expose the tools/current input schemas needed for its
operation. Missing v4 authority or manual Writer submission capability is an
actionable installation/connection mismatch, not authority to select legacy/v3
publication or routing. Follow the
[current protocol capability contract](../reviewer/README.md#current-protocol-capabilities).
Source checks do not upgrade the connected App or prove its client-visible tools.

Consumers own runner labels/groups, effective model policy and deployment
decisions. Relay owns the canonical routing/recovery workflow templates and
their deterministic [installed projection](../deploy/README.md#workflow-projection-and-pinned-runtime).
The selected product revision is independent of the consumer commit processed
by those workflows. Consumer candidate validation remains consumer-owned.
Relay owns the deployment implementation. The [rendering examples](../examples/README.md)
are synthetic inputs; the [deployment interface](../deploy/README.md) implements
installation and owner-authorized lifecycle operations.

## Qualification

Run `python3 scripts/qualify.py` from the repository root with Cargo,
Node and Python available, plus OpenSSL for temporary fixture certificates. It builds one
production Reviewer binary, starts it for all three configurations with full
certificate verification and publication disabled, and verifies bound tool
schemas and rejection of missing identity/cross-repository input. It also
builds one Reviewer test executable, runs the real
handlers against loopback mock GitHub for all three consumers, roundtrips the actual
published CR bytes into Node, and exercises routing/Writer Git publication and
replay with the same unchanged modules. It records hashes of both executables
and the candidate source before/after. The inventory API consumer uses its own
Python/type/API check IDs through Reviewer schema/rendering and Node admission.
This is local contract qualification;
it does not assert production deployment, paid model execution or native CI.

Run root `npm test`, Reviewer `cargo fmt --check` and `cargo test --locked`,
and the [candidate checks](../AGENTS.md). A consumer must separately qualify
its installed wrappers, process isolation, trusted workflows and ingress.
