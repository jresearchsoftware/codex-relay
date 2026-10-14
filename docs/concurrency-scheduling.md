# Relay control scheduling

Relay defaults to **SERIAL** scheduling: canonical routing and publication-recovery
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
| C: bounded parallel execution | The optional source topology declares finite isolated execution slots and per-subject native queues, while keeping trusted Writer critical sections serialized. | Source lifecycle support requires installed qualification, real automatic model overlap and separate repository-installation proof. |

For an illustrative batch of three admitted executions taking the same time
`T`, one qualified slot needs about `3T`, excluding controller overhead and
external waits. B does not create speedup, extra model capacity or a lower
token cost per execution. It preserves waiting work that A could replace.
Queueing itself starts no model call. Relay does not infer account quota from
native token counters, automatically choose another profile or retry a model
failure; the admitted profile and existing failure boundary remain effective.

## Parallel source candidate

The optional `consumer.executionSlots` installation snapshot declares one
`primary` slot retaining legacy locations and a finite set of additional slots.
Each slot has its own runner identity, model identity, work group, checkout,
journal, diagnostics and fixed launcher paths. Slot selection keeps the complete
installation digest stable and is bound to the configured runner name, actual
Unix UID and immutable protected attempt envelope. The root Writer selects
retained evidence through that stored envelope, never through a caller path.

The candidate parallel projection uses `relay-workflows-v4`; ordinary projections
retain `relay-workflows-v3` and the SERIAL group. Parallel subject groups retain
`queue: max` and cancellation disabled. A finite qualified runner pool bounds
active jobs. GitHub groups are repository-local: independent consumer
installations sharing a host additionally need distinct namespaces, identities,
paths and capacity allocations. This does not implement one Writer selecting
multiple repositories.

Source corrections add a kernel lock for each automatic controller's complete
lifetime, exclusive initial journal creation and a short diagnostic-retention
lock. Different run IDs and separately scoped repositories can hold independent
locks. An overlapping same-run contender cannot overwrite the active controller's
diagnostic or completion receipt. The automatic Writer wrapper has a bounded
300-second lock wait and a 450-second outer helper timeout; it holds no model
execution inside the publication lock.

Native schema-v4 fresh Issue executions retain the immutable admitted commit
when main advances through ordinary descendant commits. Admission, preflight,
checkout and publication prove ancestry; moved task refs, unrelated main
rewrites and stale remediation integration remain blockers. Historical v3 and
legacy starting-state checks retain their original contract.

Additional slots reuse registration/activation with the public
`--execution-slot` selector. Inventory, upgrade and clean reinstall account for
each slot and preserve original activity/registration. Numeric UID/group and
cross-slot access checks validate installed topology. Recovery exposes and
targets the original slot, and explicit recovery takes the same journal lock
as its controller. These source paths require installed qualification; they
do not establish actual same-repository or cross-repository model overlap or
attributable terminal Outcomes. The accepted SERIAL projection remains the
supported fallback, and cannot satisfy an objective requiring real parallel
execution.

The finite pool bounds active executions, not the total installation-wide
waiting population. Each native subject group retains up to 100 pending runs;
independent subjects have separate groups. GitHub owns runner waiting and queue
overflow/cancellation records. There is no Relay-wide durable queue or automatic
retry. Pending runs do not consume an admitted execution slot, and an overflow
or cancellation before controller entry creates no invented admission/Outcome.

## Accepted SERIAL runtime bounds

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

Those separate paths were insufficient proof of parallel isolation. The
accepted SERIAL topology shares one runtime UID and work group. Its audit
identified journal reservation, diagnostic eviction and a five-second Writer
lock wait against a two-minute Git operation as concrete race/capacity gaps.
The source candidate addresses those stores and waits above, but these changes
do not qualify an existing installation or grant runner registrations,
credentials or external ACL changes.
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
require native qualification; native concurrency groups alone do not coordinate
different repositories or establish a multi-repository Writer.
