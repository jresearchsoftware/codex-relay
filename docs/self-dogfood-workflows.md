# Public Relay consumer workflows

The workflows under `.github/workflows/` are installed consumer artifacts for
`jresearchsoftware/codex-relay`. Relay-managed behavior comes from canonical
[product templates](../deploy/README.md#workflow-projection-and-pinned-runtime),
which are projected for both self-dogfood and external consumers. The protected
consumer configuration remains `/etc/codex-relay/consumer.json`. Candidate CI
remains specific to this repository.

The schema-2 projection binds the workflow contract and deterministic file
digests instead of a product SHA. It is derived from an accepted exact product
source through the public workflow projection interface and remains subject to
consumer review/merge. Publishing this projection does not install or qualify
that product. The installed release must provide the matching workflow contract
before dispatch. The owner lifecycle workflow supplies explicit apply, stop or
resume authority; merely publishing its projection grants none of those actions.

Projection schema 2 is separate from schema-v3 Task authority. Migrated Tasks
require the paired `relay-workflows-v2` installation; labels and PR titles are
projections of their trusted Request, not Issue-body execution instructions.
See the [Task workflow guide](task-workflow.md) for usage and the
[migration contract](../contracts/README.md#github-native-task-authority) for cutover.

| Configured path | Execution boundary |
| --- | --- |
| [Routing](../.github/workflows/codex-relay-routing.yml) | Owner ready-label commands and optional owner dispatch on `main`; installed controller and fixed Writer/worker helpers |
| [Publication recovery](../.github/workflows/manual-writer-publication-recovery.yml) | Owner dispatch on `main`; inspect or recover one retained attempt using its exact owner authorization comment |
| [Owner lifecycle](../.github/workflows/manual-main-production-deploy.yml) | Owner dispatch on `main`; apply accepted Relay `main`, gracefully stop, or resume through the fixed protected lifecycle helper |
| [Exact-head validation](../.github/workflows/relay-exact-head-validation.yml) | Disposable GitHub-hosted candidate checks at the exact PR head or pushed `main` commit |

Routing uses the native names required by the
[controller](../controller/README.md), including the Issue label projection and
current PR title. Both control workflows use read-only Actions, contents, Issue
and PR permissions. Only the protected Writer helper obtains publication
credentials. Recovery never launches another worker; inspect returns the exact
authorization text to publish as a new owner comment before a recovery dispatch.
The original `run_id`, `attempt_id` and native comment `authorization_id` must
match the retained attempt. A workflow rerun does not grant fresh execution or
publication authority.

The control workflows perform no checkout and run no actions or candidate code.
They resolve the root-owned installed release once, require its public
`reviewed-source/.relay-source.json` revision and release path to match each other,
require its public `deploy/workflows/contract.json` identity to match the projected
workflow contract, and invoke the stable `bin/relay-routing.mjs` or
`bin/relay-publication-recovery.mjs` entrypoint from that resolved release. The
source identity is installed root-owned with mode `0644`; the general runner does
not need access to the restricted artifact manifest. Install and qualify the
accepted compatible product revision before launch. An unprovable or incompatible
installation fails before admission. The consumer workflow SHA may differ from
the installed product revision. A newer Relay `main` never forces an upgrade or
emits a warning; without authoritative release information no update note is
emitted. Routing and recovery
share one concurrency group with cancellation disabled; the existing root Writer
lock still serializes publication. Logs record the installed and workflow SHAs.

## Activation boundary

Workflow existence and passing source tests do not qualify activation. Before
registering/enabling the public persistent runners, independently prove the
[public dogfood trust conditions](integration-reference.md#public-dogfood-trust),
including controls **outside candidate-controlled YAML** that prevent untrusted
fork and same-repository candidate code from reaching those runners.

The accepted installation uses the `codex-relay` label for both runner instances.
The production organization's runner group must restrict repository and exact
trusted workflow/ref access so it cannot receive routing, recovery or candidate
jobs. The general runner requires its own proven external trust boundary. Its
default repository registration scope and labels are not workflow allowlists.
The public deployment interface also supports an explicit organization-scoped
general runner in a separate group restricted to this repository and exactly
`jresearchsoftware/codex-relay/.github/workflows/codex-relay-routing.yml@refs/heads/main`
`jresearchsoftware/codex-relay/.github/workflows/manual-writer-publication-recovery.yml@refs/heads/main`,
and
`jresearchsoftware/codex-relay/.github/workflows/manual-main-production-deploy.yml@refs/heads/main`.
This option requires owner acceptance of the registration scope and independent
qualification of the external group ACL; it does not migrate an existing runner
or establish that the public consumer has adopted the option. Candidate CI must
have no access to either persistent runner.
The control jobs' owner/ref conditions and checks for runner name and Unix user
`codex-relay-general-runner` are defensive consistency checks after scheduling;
they do not establish that boundary. If external restrictions are unavailable or
unproven, keep the runners inactive and do not apply launch labels.

Candidate validation stays on GitHub-hosted Ubuntu with read-only contents,
checkout credential persistence disabled and no Relay secrets or host access. Its
stable check name remains `Candidate checks`; native evidence must match the
exact candidate head. It does not qualify installed sudoers, process isolation,
credentials, ingress, runner restrictions or independent acceptance. See
[contributor validation](../CONTRIBUTING.md#local-validation) for its check set.

## Public owner lifecycle workflow

`manual-main-production-deploy.yml` has one action selector: `apply` (the
default), `stop`, or `resume`. There is no revision, target, config or executable
input. It accepts only owner `foal` as both original and triggering actor,
`workflow_dispatch`, this repository and `refs/heads/main`.

The job runs on the separate general runner, whose name and Unix user must both
be `codex-relay-general-runner`. Reviewer lifecycle changes can restart its
dependent production runner; the general runner keeps the owner operation's
transport alive. An organization-scoped general runner uses its configured
dedicated group with the trusted workflow/ref allowlist above. Repository-scoped
registration retains its separately qualified external trust boundary. Add the
owner lifecycle workflow to that boundary through owner administration before
dispatch; publishing YAML cannot update or prove the external policy. Candidate
CI must have no access to either persistent runner.

The job performs no checkout and downloads no action or candidate executable.
It verifies the workflow contract and exact release path against the root-owned
installed source identity, then calls only the fixed helper:
`/usr/bin/sudo -n /usr/local/sbin/codex-relay-owner-lifecycle <action>:<installed-product-SHA>:<consumer-SHA>`.
The single typed argument binds the action, resolved installed product and native
dispatch commit. The root-owned installed coordinator rechecks that installed
identity and uses the protected configuration snapshot. The accepted deployment
must first install this helper and opt into
[`localApply.source: installed`](../deploy/README.md#protected-self-dogfood-reconciliation)
through owner configuration and the public deployment interface. No workflow
step receives configuration or credential material. The older fixed
`relay-production-local-apply` reconciliation API remains available for its
existing compatibility and recovery paths.

For `apply`, the coordinator resolves accepted public Relay `main` once at the
start and freezes that exact product target. It obtains clean root-owned source
and consumer trees without a GitHub credential, verifies the reviewed consumer
projection against the selected target's exact templates and configuration, and
then quiesces admission and drains admitted work. If that product is already
installed, it reconciles and verifies it. Otherwise it uses the existing public
upgrade primitive for the same exact target. Apply, activation, verification and
resume belong to that one owner action. Logs identify the target and progress;
moving `main` later neither changes it nor starts another operation. A source
candidate does not become an accepted target solely because its CI passes.

Projection verification compares the exact rendered workflow bytes, contract,
repository bindings and digests. Schema 2 carries no product SHA, so unchanged
templates need no new consumer commit for every product revision. Changed
managed bytes require normal consumer review/publication: the operation reports
`WORKFLOW_REVIEW_REQUIRED` before quiescing or changing the host. It never pushes,
merges or substitutes an unreviewed projection. Publish the reviewed consumer
change through existing authority, then invoke the owner action again.

`stop` quiesces and drains gracefully; `resume` restores the retained qualified
state through the same protected lifecycle boundary. The workflow serializes
owner lifecycle jobs without cancellation; the host operation lock also excludes
conflicting owner transitions. Failure or uncertain execution retains recovery
evidence and keeps the installation quiesced for inspection rather than claiming
successful resume. This workflow's dispatch is lifecycle authority for these
actions; merge, Issue closure, credential provisioning and runner registration
retain their separate owner authority.
