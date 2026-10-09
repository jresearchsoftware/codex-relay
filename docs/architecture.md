# Architecture

Relay connects GitHub task authority to a contained Codex worker and back to
an exact PR head. One configured consumer is served per process. The
[consumer contract](../consumer/README.md) supplies repository identities,
workflow names, runtime paths, model and explicit effort overrides. Omitted
execution fields use the [shared contract resolver](../contracts/README.md),
which encodes the policy in `AGENTS.md`; reusable code chooses no model.

## Components and flow

Tasks explicitly migrated to `Authority model: github-native-v1` use the stable
Issue charter plus one complete trusted execution request. The shared
[authority contract](../contracts/README.md#github-native-task-authority) defines
native identity, publisher Bot identity, version, target binding, verified
source references and explicit linear supersession. Selected ordinary comments
are contextual evidence. The controller resolves records deterministically and
never asks the worker to reconstruct authority from discussion history.
Unmarked Tasks retain legacy Issue/CR parsing until they cross that explicit
migration boundary. The two authority parsers cannot govern the same launch.
The [Task workflow guide](task-workflow.md) explains the current human path.

| Component | Owns | Does not own |
| --- | --- | --- |
| Consumer/owner | Task scope, model/effort policy, launch commands, deployment, merge and release decisions | Reviewer verdict identity |
| Routing controller | Event binding, one execution reservation, attempt journal and terminal handoff | New task authority or retry permission |
| Lifecycle admission | Durable automatic admission gate and full controller drain under the Writer lock | Task authority, new executions, deployment acceptance or implicit resume |
| Codex runtime/worker | Isolated task checkout, local commits, semantic result and validation claims | GitHub credentials, publication or review acceptance |
| Trusted Writer | Live authority revalidation, imported Git objects, publication intents, PR execution Draft/Ready lifecycle and Outcome | Worker execution lifecycle or Reviewer verdicts |
| External ChatGPT review/caller | Reads the diff/result, authors substantive verdict/findings and supplies structured authority records | Writer implementation identity or automatic launch authority |
| Rust Reviewer publication service | Bounded exact-head GitHub evidence reads, native review/check publication, same-review Step-label/title synchronization and duplicate recovery | Substantive review authorship, implementation, launch commands, owner new-phase choice or merge |

The owner applies `codex-ready-auto` or `codex-ready-manual` to a canonical
Issue or remediation PR. The trusted workflow uses the configured base branch,
not PR-controlled code. Writer checks native owner/event/run identity, Task/Step,
current typed Request or legacy Issue/decisive native Change Request and exact
starting head/base.
It consumes the ready event after reservation. `step-N` is persistent display
and authority-binding metadata, never permission to execute on its own.
New executable CR publication synchronizes Issue/PR Step and bounded Task/Step/CR-ID PR title
inside the Reviewer operation; retry/repair retains the same native review ID
and authored Step. For migrated Tasks, an explicit successor Request advances
a new phase from N to N+1 and the typed publisher projects it. Legacy owner
new-phase preparation retains its separate N+1 procedure. Same-phase execution
retries preserve N.
The native review body remains sole CR authority, linked to the canonical Issue
for Task identity; no Step history or competing normal post-CR owner writer is introduced.
A legacy published record lacking its pre-publication Step anchor stops with
`LEGACY_STEP_BINDING_REQUIRED` unless its projection is already synchronized.
Explicit bounded owner migration repair preserves that review ID and Step before
replay of the original Reviewer payload; it does not launch execution.

A complete migrated Task Request, or legacy Issue-body fields, can explicitly
authorize implementation continuation from an existing task branch at one exact
starting head, binding its current PR when one exists
under the [controller contract](../controller/README.md#issue-authorized-implementation-continuation).
Admission checks the live branch ref and unique open PR, including repository,
base, Task, Step and title bindings, and pins the admitted PR number. This remains
Issue implementation with the Writer identity; it requires no Reviewer CR and
grants no remediation integration merge. Same-phase retries keep Step; a new
owner-authorized phase uses a successor Request or legacy N+1 procedure.
Legacy fresh Issue defaults and manual handoff remain available, using existing
attempt records and services.
Writer requires the admitted starting head, or its own later published head, as
the exact previous remote ref and reobserves it before continuation's non-force
push. Ref observations and the push do not provide atomic compare-and-swap against
external ref changes.

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
later readiness check failed. A successful contained result, complete worktree
observation, verified publication and observed exact PR head permit one successful terminal Outcome. After the protected controller
receipt proves execution handoff, Writer verifies native Ready for that exact
PR/head. Draft/Ready follows execution ownership; integration observations
never mutate it. Successful native Change Request publication supplies a bounded
Writer action that verifies Draft before remediation continuation. Production
routing consumes the same action from the verified current native CR during
admission, before execution reservation or ready-command consumption. Manual
handoff verifies it again before publication. A failed/uncertain transition
retains exact-CR/head lifecycle recovery without starting Codex or republishing
review authority. Remaining uncommitted/non-ignored residue
alone yields a successful handoff with `UNCOMMITTED_WORK_REMAINS`, retained in
the terminal receipt and Outcome and emitted as a workflow warning. Codex must
first reconcile task-owned work where safe. The controller never assumes residue
is disposable or cleans, commits, publishes or retries it. Unknown execution,
incomplete collection and failed/uncertain publication or evidence retention
remain automation failures. Material warnings must inform the next owner/review
decision. Candidate-head CI, mergeability and independent exact-head review
remain separate gates. Publication completion records a READY, PENDING or
BLOCKED integration observation without a second push or infrastructure failure.
The base SHA is an observation, never permission to rebase or test a synthetic
merge. A later bounded readiness observation updates the same Outcome.

Task Requests keep Issue authority independently of the result artifact. Writer
publishes a typed Outcome on the unique durably bound PR, or the Issue when no
PR exists. Known PR publication uncertainty prevents Issue fallback. Contained
no-change completion needs neither an empty commit nor an artificial PR.
Independent Task acceptance uses a trusted Issue Task Approval bound to the
current Request, Outcome and applicable immutable results, including when a
disposable PR was closed. Task findings are review evidence; further execution
requires a complete next Task Request. Genuine PR review remains native.

Manual routing publishes a copyable handoff and ends automatic ownership. The
owner-launched session follows its live authority and uses the owner-authorized
publication path. Writer availability is not a manual execution prerequisite.
Legacy manual publication retains its owner channel. Migrated manual results
reach the bounded trusted Writer operation before typed independent acceptance;
the Task Approval never treats an ordinary owner comment as a Writer Outcome.

## Durable state

| Owner | Record | Purpose |
| --- | --- | --- |
| GitHub/Git | Issue/CR, owner event/run, Step labels, commits/ref/PR, checks, reviews and Outcome | Authority, durable progress and acceptance truth |
| Runner | Configured `paths.attemptRoot/<run-id>.json` | Execution reservation, returned result, containment and causal diagnostic |
| Writer | Configured `paths.claimRoot/publication-v2/<run-id>.json` | Immutable admission, full automatic controller reservation/completion, pending mutation intent, verified head and recovery receipts |
| Writer | Configured `paths.claimRoot/pr-lifecycle-v1/<review-id>.json` | Exact native CR/head Draft intent and reconciliation before an execution run exists; no Task or launch authority |
| Root lifecycle admission | Configured `paths.claimRoot/admission-v1.json` | Automatic admission phase, operation/target/configuration binding, original service activity intent and verified installed revision |
| Reviewer | Configured SQLite database | Review/check publication operation identity and deduplication/recovery |

Configuration is validated once and frozen. A digest accompanies admission;
another configuration cannot resume the same attempt. Configuration/state
migrations require reconciliation under the original qualified revision.

The automatic gate and admission reservation share the root Writer lock.
Quiesce prevents new automatic Issue/CR execution while admitted controllers
finish through containment, collection, publication and durable terminal
receipts. Drain checks those existing attempt records and matching protected
runner journals; a model exit or an idle runner is insufficient. Its bounded
polls release the lock so active controllers can finish. Unknown execution,
missing containment or ambiguous publication fails closed and preserves
quiesce. The worker cannot write gate or Writer state. This lifecycle state
does not replace GitHub Task authority or add a task ledger.

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

The consumer supplies runner policy, App/ingress references and owner lifecycle
decisions and reviews the installed workflow projection. Relay owns canonical
workflow templates, deterministic projection and workflow concurrency, as well
as the root Writer
lock, fixed wrappers/sudo policy, worker isolation and deployment lifecycle. Caller JSON cannot select a credential, executable or repository.
Keep root-owned configuration and separate consumer state outside worker-writable
paths. Never execute PR/fork-controlled code on a persistent privileged runner.

Relay owns the [deployment interface](../deploy/README.md), source/build/install
mechanics, layout, wrappers, users/services, upgrade/rollback and verification.
Consumers own configuration, secret references, target properties, policy and
channel/revision selection. Ansible is a replaceable internal backend; it is
not a consumer API. A selector resolves once and the exact installed identity
is reported. Selecting a version does not grant deployment authority.

Product source revision, installed product revision, consumer authority revision
and latest accepted product revision are independent. Routing and recovery use
the exact installed revision with the reviewed workflow compatibility contract; advancing
either repository does not upgrade or invalidate it. An owner selects one exact
accepted target, reviews any changed generated workflow bytes, and uses the public upgrade
primitive to apply and verify that same target under the existing host lock.
The owner lifecycle coordinator quiesces and drains automatic admission before
applying that primitive. Registered runners remain online. Only explicit
same-operation verification of the installed revision permits resume; a
restart, failed or unknown transition retains quiesce and recovery evidence.
Graceful stop retains quiesced admission without stopping registered runners.
Manual handoff and publication-only recovery keep their existing authority.
Without authoritative latest-release information no update note is
emitted, and availability of a newer revision is never itself a warning or gate.

Fresh bootstrap derives workflow proposals from that exact accepted source and
one durable owner configuration. A missing projection is an explicit consumer
review/publication transition in the supported bootstrap UX, not a separate
pre-existing installation input. Read-only inventory distinguishes reusable
protected state, missing ephemeral inputs, invalid state and unavailable admin
verification. An authorized clean reinstall may retire a proven pre-current
runtime while retaining runner registrations, protected credentials and durable
publication/review state. Retirement, fresh apply and post-check share the host
deployment lock; uncertain transitions retain recovery evidence. Service
activation and external consumer qualification keep their separate authority.

The [Reviewer](../reviewer/README.md) is a narrow MCP HTTP service behind a
trusted mTLS terminator. It verifies forwarded client identity and binds every
GitHub request, review and check to an explicitly selected configured repository,
the shared App/installation and the exact head.
Writer and Reviewer credentials are separate. Raw credentials and diagnostic
streams never belong in an Outcome.

The evidence reader uses a read-only installation token and binds applicable
execution checks through exact-head Writer Outcomes on the reviewed PR and
canonical linked Issue. Mandatory completeness covers execution-time warnings
available through supported check/job/runtime APIs; unavailable, denied or
truncated required evidence prevents an absence claim. UI-only service-level or
pre-execution annotations/platform banners are explicitly excluded from that
automated contract and do not alone block review. No HTML or browser-session
fallback is used. Supported API completeness cannot prove absence of UI-only
warnings or replace independent warning disposition. See the
[evidence contract and API limitation](../reviewer/README.md).

Local qualification tests real modules/handlers against synthetic Git and
loopback GitHub. It does not test a consumer's installed wrappers, reverse proxy,
GitHub App permissions, paid model execution or production deployment.

The [integration reference](integration-reference.md) specifies launcher/sudo
environment recreation, public dogfood trust assumptions, configuration, App
permissions and bounded scan-policy differences. The Node directories and the
shared Rust/Node CR schema form one qualified product tree, not separate packages.
