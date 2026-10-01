# Public Relay consumer workflows

These workflows are the consumer wiring for `jresearchsoftware/codex-relay`.
They are not deployment templates for other consumers. The protected consumer
configuration remains `/etc/codex-relay/consumer.json`.

| Configured path | Execution boundary |
| --- | --- |
| [Routing](../.github/workflows/codex-relay-routing.yml) | Owner ready-label commands and optional owner dispatch on `main`; installed controller and fixed Writer/worker helpers |
| [Publication recovery](../.github/workflows/manual-writer-publication-recovery.yml) | Owner dispatch on `main`; inspect or recover one retained attempt using its exact owner authorization comment |
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
`reviewed-source/.relay-source.json` revision and release path to match the native
workflow SHA, and invoke the stable `bin/relay-routing.mjs` or
`bin/relay-publication-recovery.mjs` entrypoint from that resolved release. The
source identity is installed root-owned with mode `0644`; the general runner does
not need access to the restricted artifact manifest. Install and qualify the accepted `main` revision
before launch. A mismatch fails before Relay admission. Routing and recovery
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
