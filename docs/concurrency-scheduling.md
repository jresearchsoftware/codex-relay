# Relay control scheduling

Relay selects **SERIAL** scheduling: canonical routing and publication-recovery
workflows share the existing `<namespace>-control` concurrency group, with
`queue: max` and `cancel-in-progress: false`. One control invocation runs at a
time within one GitHub repository; newer independent work waits instead of replacing an earlier pending run
within GitHub's queue limit. This is native Actions scheduling, not a Relay
retry queue, execution reservation or Task admission.

GitHub documents a limit of 100 pending jobs or runs per concurrency group;
additional arrivals are canceled. Runs are ordered by when they start waiting
on the group, which need not be their dispatch order. See the current
[workflow concurrency syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#concurrency)
and the [May 7, 2026 release notice](https://github.blog/changelog/2026-05-07-github-actions-concurrency-groups-now-allow-larger-queues/).

## Alternatives and support

| Design | Scheduling and cost | Support boundary |
| --- | --- | --- |
| A: global group with the native default queue | One running and one pending invocation; a new arrival replaces the pending invocation. Model concurrency stays at one, but independent waiting work can be lost. | Historical projection behavior; existing evidence retains its original meaning. |
| B: global group with `queue: max` | One running invocation and up to 100 waiting invocations; no replacement merely because newer work arrives within that bound. Model concurrency stays at one. | Selected SERIAL source behavior; consumer projection and native TEST evidence establish adoption separately. |
| C: bounded parallel execution | Could improve throughput only with multiple qualified execution slots. It also permits overlapping collection, diagnostics and protected helper calls. | **NOT QUALIFIED**. The current single-runner deployment and shared runtime boundaries do not establish safe independent parallel execution. |

For an illustrative batch of three admitted executions taking the same time
`T`, one qualified slot needs about `3T`, excluding controller overhead and
external waits. B does not create speedup, extra model capacity or a lower
token cost per execution. It preserves waiting work that A could replace.
Queueing itself starts no model call. Relay does not infer account quota from
native token counters, automatically choose another profile or retry a model
failure; the admitted profile and existing failure boundary remain effective.

## Current runtime bounds

The source [deployment configuration](../deploy/config.py) has one general
runner and a separate production runner role. The routing and recovery
[templates](../deploy/workflows/) check the exact configured general runner name
and Unix user. They cannot use the production runner as a second task slot.
Task 103's TEST inventory observed that same one-general-runner layout with a
separate production role. Inventory establishes available roles, not qualified
parallel capacity; native TEST results and their limits belong in the existing
PR and Writer Outcome.

Attempts already have distinct `workRoot/<attemptId>` checkouts, task-local
HOME/CODEX_HOME/XDG/cache/tmp paths, diagnostic references, owned process groups
and unique trusted Git import repositories. Collection precedes publication
only after containment and observes bounded regular bytes rather than executing
worker-modified Git metadata. See [attempt preparation](../controller/src/attempt-runtime.mjs),
[the fixed launcher](../deploy/ansible/roles/relay_codex_runtime/templates/relay-codex-launcher.mjs.j2),
[process containment](../controller/src/github.mjs) and
[trusted collection](../controller/src/trusted-git.mjs).

Those separate paths are insufficient proof of parallel isolation. All model
attempts share one runtime UID and Codex work group. Runner journals use atomic
replacement with scheduling serialization rather than a concurrent same-run
reservation primitive. Primary diagnostic retention lists and evicts shared
records without a store-wide lock. The root Writer helper waits five seconds
for its lock while a Git operation inside it can have a two-minute timeout.
These are concrete reasons to retain SERIAL, not new controls or authority to
change Unix identities, runner registrations, credentials or external ACLs.
See [shared work permissions](../deploy/ansible/roles/relay_runner/tasks/general-runtime.yml),
[attempt storage](../controller/src/attempt-store.mjs),
[diagnostic storage](../controller/src/diagnostic-store.mjs) and
[the Writer wrapper](../deploy/ansible/roles/relay_controller/templates/relay-writer-controller.j2).

The runtime retains its existing 90-minute model and 100-minute dispatcher
timeouts; control jobs retain their 120-minute timeout. Capture, object import,
worktree observation, cleanup and eight diagnostic fallback slots have their
existing bounds. They are not CPU, RAM, filesystem or account-quota allocation
for multiple simultaneous workers. See the [runtime contract](../runtime/README.md)
and [diagnostic retention](../controller/README.md#runtime-diagnostic-retention).

## Authority while waiting and cancellation

The ready-event freshness check remains
`0 <= run.created_at - event.created_at <= 120 seconds`. It compares the native
run's creation with the owner event, not job start or the eventual admission
time. Waiting in the Actions concurrency queue does not age that comparison.
When the job starts, Writer still checks the latest ready transition, current
label, owner/run binding, effective authority, exact head and protected prior
attempts. Applying another ready transition can invalidate an older queued
command. A same-task command written before the preceding admitted run finishes
remains an invalid prewritten retry. See
[native command verification](../controller/src/live-authority.mjs) and
[prior-attempt verification](../controller/src/publication-broker.mjs).

Cancellation or overflow before the queued job enters the controller leaves an
owner-visible native canceled run and creates no Relay admission, Step, journal,
Writer Outcome or model call. Inspect that native run and the protected original
attempt state before deciding whether fresh work is safe. A fresh owner command
must satisfy the existing authority and prior-attempt checks; no background
retry, synthetic success or substituted Outcome is created. Cancellation after
controller entry retains the existing containment, durable evidence and unknown
execution rules. A canceled run alone is not proof that no attempt was admitted.

The root publication lock and
[lifecycle quiesce/drain](../controller/README.md#lifecycle-admission-and-drain)
remain unchanged. Quiesce closes admission, admitted controllers may complete,
and drain requires their containment/publication/terminal receipts. Native
waiting runs are not admitted controllers; a later job still encounters the
current gate. Stop and upgrade continue through their existing protected paths.

## Projection and qualification

`queue: max` changes managed workflow scheduling bytes, not the installed
routing/recovery invocation, inputs, environment meanings or protected helper
ABI. The workflow contract remains `relay-workflows-v3` under the existing
[compatibility rule](../deploy/README.md#workflow-projection-and-pinned-runtime).
An older accepted projection with the same v3 ABI retains its earlier queue
behavior. Historical admissions, Outcomes, evidence and recovery bindings are
not rewritten.

Project changed workflows from an exact accepted product source through the
public interface and review/merge the consumer diff through its normal owner
authority. A source change or local PASS does not update the installed
projection or qualify native scheduling. PROD adoption and deployment remain
separately authorized; Task 103 does not mutate PROD, runner-group ACLs,
credentials or shared resources, and does not expand Tasks 85/86.

Local scenarios cover independent Issues, same-task commands, Issue/PR number
collisions, foreign-repository numeric identity rejection within one configured
consumer, replay, unresolved attempts and quiesce/drain. Cross-repository
fixtures demonstrate identity separation only: current Writer remains bound to
one configured consumer per process. Native TEST observations must additionally
show multiple waiting runs surviving, serial worker entry and truthful terminal
state. Independent parallel execution and future many-repository scheduling
remain **NOT QUALIFIED**; native concurrency groups alone do not coordinate
different repositories or establish a multi-repository Writer.
