# Architecture

Relay connects GitHub task authority to a contained Codex worker and back to
an exact PR head. One configured consumer is served per process. The
[consumer contract](../consumer/README.md) supplies repository identities,
workflow names, runtime paths and effective profile defaults; reusable code
does not choose them.

## Components and flow

| Component | Owns | Does not own |
| --- | --- | --- |
| Consumer/owner | Task scope, model/effort policy, launch commands, deployment, merge and release decisions | Reviewer verdict identity |
| Routing controller | Event binding, one execution reservation, attempt journal and terminal handoff | New task authority or retry permission |
| Codex runtime/worker | Isolated task checkout, local commits, semantic result and validation claims | GitHub credentials, publication or review acceptance |
| Trusted Writer | Live authority revalidation, imported Git objects, publication intents, PR progress and Outcome | Worker execution lifecycle or Reviewer verdicts |
| External ChatGPT review/caller | Reads the diff, authors substantive verdict/findings and supplies structured CR | Writer implementation identity or automatic launch authority |
| Rust Reviewer publication service | Exact-head target check, native review/check publication and duplicate recovery | Substantive review authorship, implementation, launch commands, Step-label mutation or merge |

The owner applies `codex-ready-auto` or `codex-ready-manual` to a canonical
Issue or remediation PR. The trusted workflow uses the configured base branch,
not PR-controlled code. Writer checks native owner/event/run identity, Task/Step,
current Issue or decisive native Change Request and exact starting head/base.
It consumes the ready event after reservation. `step-N` is persistent display
and authority-binding metadata, never permission to execute on its own.

For automatic work, the runner creates the checkout, reserves execution once,
and invokes the fixed credential-free launcher. Codex makes ordinary task
commits and returns semantic status, summary, validation claims and a blocked
reason. Within that single invocation it follows the
[progress-bounded policy](execution-policy.md).

After containment, trusted code imports only bounded regular Git object bytes
and the admitted ref into a fresh repository. It never uses the worker's Git
config, hooks, filters, index, replacement refs or alternates. Writer validates
the task chain, expected identity, safe paths and regular modes, scans all
introduced blobs (including later-deleted secrets), rechecks live authority,
and performs an ordinary non-force push.

Useful task commits can be published even if execution returned blocked or a
later readiness check failed. A successful contained result, clean worktree,
verified publication and observed exact PR head permit a ready declaration and
one terminal Outcome. Native CI, mergeability, independent exact-head review
and the human merge decision remain separate gates.

Manual routing publishes a copyable handoff and ends automatic ownership. The
owner-launched session follows its live authority and uses the owner-authorized
publication path. Writer availability is not a manual publication prerequisite.

## Durable state

| Owner | Record | Purpose |
| --- | --- | --- |
| GitHub/Git | Issue/CR, owner event/run, Step labels, commits/ref/PR, checks, reviews and Outcome | Authority, durable progress and acceptance truth |
| Runner | Configured `paths.attemptRoot/<run-id>.json` | Execution reservation, returned result, containment and causal diagnostic |
| Writer | Configured `paths.claimRoot/publication-v2/<run-id>.json` | Immutable admission, pending mutation intent, verified head and recovery receipts |
| Reviewer | Configured SQLite database | Review/check publication operation identity and deduplication/recovery |

Configuration is validated once and frozen. A digest accompanies admission;
another configuration cannot resume the same attempt. Configuration/state
migrations require reconciliation under the original qualified revision.

Starting/reviewed head, local progress head, observed remote head and head
declared ready are distinct. A worker's claims do not establish any of these
Git facts or prove that CI passed.

## Failure and continuation

A reserved execution with no returned evidence is unknown and cannot relaunch.
A same-run replay may verify or publish an already returned execution; it
cannot repeat a model call. Progress inside one worker and Relay-level replay
are separate mechanisms.

Writer persists mutation intent before push or non-idempotent GitHub POST.
After an ambiguous push, observation of the exact candidate reconciles the
intent. Otherwise it stops. An uncertain comment/PR creation must be matched
to its exact native marker/binding before continuation. No force push or
automatic blind retry is provided.

[Publication recovery](../controller/README.md#writer-publication-recovery)
is a separate owner-authorized operation bound to the original attempt,
authority digest, previous/candidate heads and a fresh native authorization
comment. It never launches Codex. Unknown/uncontained execution cannot be
converted into success by recovering publication.

One exact admitted-base integration merge is allowed for applicable remediation
under the [Git reconciliation contract](../controller/README.md#reviewed-base-reconciliation).
That constraint protects commit provenance; it does not limit the number of
local diagnose/fix/validate iterations.

## Trust and deployment

The consumer supplies trusted workflows, workflow concurrency, App/ingress
references and owner lifecycle decisions. Relay implements the root Writer
lock, fixed wrappers/sudo policy, worker isolation and deployment lifecycle. Caller JSON cannot select a credential, executable or repository.
Keep root-owned configuration and separate consumer state outside worker-writable
paths. Never execute PR/fork-controlled code on a persistent privileged runner.

Relay owns the [deployment interface](../deploy/README.md), source/build/install
mechanics, layout, wrappers, users/services, upgrade/rollback and verification.
Consumers own configuration, secret references, target properties, policy and
channel/revision selection. Ansible is a replaceable internal backend; it is
not a consumer API. A selector resolves once and the exact installed identity
is reported. Selecting a version does not grant deployment authority.

The [Reviewer](../reviewer/README.md) is a narrow MCP HTTP service behind a
trusted mTLS terminator. It verifies forwarded client identity and binds every
GitHub request, review and check to the configured repository/App and exact head.
Writer and Reviewer credentials are separate. Raw credentials and diagnostic
streams never belong in an Outcome.

Local qualification tests real modules/handlers against synthetic Git and
loopback GitHub. It does not test a consumer's installed wrappers, reverse proxy,
GitHub App permissions, paid model execution or production deployment.

The [integration reference](integration-reference.md) specifies launcher/sudo
environment recreation, public dogfood trust assumptions, configuration, App
permissions and bounded scan-policy differences. The Node directories and the
shared Rust/Node CR schema form one qualified product tree, not separate packages.
