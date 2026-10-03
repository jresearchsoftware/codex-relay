# Public Relay consumer workflows

The workflows under `.github/workflows/` are installed consumer artifacts for
`jresearchsoftware/codex-relay`. Relay-managed behavior comes from canonical
[product templates](../deploy/README.md#workflow-projection-and-pinned-runtime),
which are projected for both self-dogfood and external consumers. The protected
consumer configuration remains `/etc/codex-relay/consumer.json`. Candidate CI
remains specific to this repository.

The current SHA-bound projection is retained until the owner selects an accepted
product target, reconciles the derived workflow content, reviews and
merges any changed projection, then installs and qualifies that target. Editing
product templates does not silently rewrite or upgrade this installed consumer.
The contract below describes the new projected behavior; the retained legacy
projection still has its exact product SHA gate until migration through Task #44.

| Configured path | Execution boundary |
| --- | --- |
| [Routing](../.github/workflows/codex-relay-routing.yml) | Owner ready-label commands and optional owner dispatch on `main`; installed controller and fixed Writer/worker helpers |
| [Publication recovery](../.github/workflows/manual-writer-publication-recovery.yml) | Owner dispatch on `main`; inspect or recover one retained attempt using its exact owner authorization comment |
| [Production reconciliation](../.github/workflows/manual-main-production-deploy.yml) | Owner dispatch on `main`; one exact installed product SHA through the fixed production helper and protected deployment snapshot |
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
and
`jresearchsoftware/codex-relay/.github/workflows/manual-writer-publication-recovery.yml@refs/heads/main`.
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

## Public production workflow

`manual-main-production-deploy.yml` has no revision, target or other dispatch
inputs. It accepts only owner `foal` as both original and triggering actor,
`workflow_dispatch`, this repository and `refs/heads/main`. Scheduling explicitly
selects organization runner group `codex-relay-runner` plus the accepted runner
labels. There is no label-only fallback. Runner name and Unix user must both be
`codex-relay-runner`; these checks supplement the external scheduling restriction.

The owner must configure this production group's repository access to only
`jresearchsoftware/codex-relay` and its workflow access to only:

```text
jresearchsoftware/codex-relay/.github/workflows/manual-main-production-deploy.yml@refs/heads/main
```

Never allow routing, recovery, candidate CI or the private DocReview deployment
workflow into this group. Independently verify the saved external policy before
registration or enablement. Source publication or a passing workflow test does
not establish that policy.

The job performs no checkout and downloads no action or candidate executable.
It verifies the workflow contract and exact release path against the root-owned
installed source identity, then calls only the fixed helper:
`/usr/bin/sudo -n /opt/codex-relay/relay-production-local-apply <product-SHA>:<consumer-SHA>`.
The single typed argument binds both the resolved installed product and native dispatch
commit. The helper rechecks that exact installed product before executing its
code, preventing a concurrent installation switch from changing the target.
The accepted deployment must first opt into
[`localApply.source: installed`](../deploy/README.md#protected-self-dogfood-reconciliation)
through owner configuration and public owner apply. The helper validates the
private root-owned snapshot and rechecks the dispatched consumer commit against current `main`
immediately before
reservation under the existing transition lock. It retains the exact installed
product version and original consumer provenance. Failed or stale checks prevent
apply. No workflow step receives the configuration or credential material.

The workflow serializes production jobs without cancellation. The deployment
operation boundary also excludes conflicting owner operations and preserves live
services through reconciliation. Source upgrades and any deferred service
transition remain separately authorized owner actions. Deploy and qualify an
accepted main revision before dispatching that revision's workflow; a green
source candidate must never be installed merely to make the job runnable.
