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
| C: bounded shared pool | One configured desired capacity bounds the physical General Runner pool across eligible repositories; per-run groups and trusted resource/publication critical sections allow independent attempts on the same Task. | Managed Apply, same-UID isolation, retained recovery and actual model overlap require source and installed qualification. |

For an illustrative batch of three admitted executions taking the same time
`T`, one qualified slot needs about `3T`, excluding controller overhead and
external waits. B does not create speedup, extra model capacity or a lower
token cost per execution. It preserves waiting work that A could replace.
Queueing itself starts no model call. Relay does not infer account quota from
native token counters, automatically choose another profile or retry a model
failure; the admitted profile and existing failure boundary remain effective.

## Shared managed pool

The optional `consumer.generalRunnerPool.desiredCapacity` selects one fixed
physical capacity (1–32), shared by all eligible repositories and Codex Unix
identities. The pool is identified by `environment.generalRunner.name`,
independently of repository namespaces. Each runner retains its unique
registration, service and instance state; the trusted General Runner account may
be shared. The separate Production Runner cannot consume this capacity.

One default non-root Codex `runtimeUser` can execute concurrent attempts.
Attempt paths, HOME/CODEX_HOME/XDG/cache/tmp, journal, diagnostics and process
lifecycles stay separate. A repository's protected consumer configuration can
select a different runtime user without allocating another pool. Task/PR data
does not select identities. This keeps the one-consumer-per-Writer contract
and leaves generalized Writer selection and final organization settings to
Tasks 85 and 86.

Owner Apply reconciles the desired physical registrations/services with an
installation App and short-lived API-derived registration/removal tokens.
Expansion creates only missing members; contraction removes work eligibility,
retains busy attempts and retires only safely idle members. Uncertain external
mutations are inspected before another operation. The shared protected pool
binding prevents a second repository from silently creating a duplicate pool
or applying a conflicting capacity.

The internal resource-slot layout stays stable across capacity changes. Only
the operational desired capacity is excluded from the execution configuration
digest; identities, protected paths and security configuration remain bound.
Original journals and claim envelopes survive physical retirement. Any active
pool member can transport recovery; trusted Writer selects the original slot
from the retained envelope before opening its evidence. The public managed
recovery path needs no per-slot owner choice.

Parallel routing uses `<namespace>-control-${{ github.run_id }}` with
`queue: max` and cancellation disabled. The `github` context, including the
native run ID, is supported in the workflow-level
[concurrency expression](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#concurrency).
Distinct owner-authorized runs on one Task can reach separate free slots while
the earlier run is still executing or publishing. Same-event deduplication and
same-attempt replay remain protected Writer responsibilities. Recovery retains
its original-run group `<namespace>-recovery-${{ inputs.run_id }}`. Shared
physical registrations bound simultaneous jobs across repositories, whereas
GitHub concurrency groups remain repository-local. Waiting, cancellation,
replay, protected admission/publication locks and lifecycle gates retain their
existing authority. There is no dynamic per-job autoscaling or automatic
model retry. Unconfigured consumers retain SERIAL v3; managed pool projections
use the qualified parallel v4 contract.

Source checks, synthetic same-UID process tests and live model observations
prove different things. Installed qualification must observe the actual shared
pool, simultaneous automatic model processes, bounded occupancy, attributable
terminal Outcomes, capacity reconciliation and original-run recovery. Earlier
distinct-UID TEST evidence does not establish these new properties. See the
[deployment contract](../deploy/README.md#shared-managed-general-runner-pool).

## Retained explicit-slot topology

The optional `consumer.executionSlots` installation snapshot declares one
`primary` slot retaining legacy locations and a finite set of additional slots.
Each slot has its own runner identity, model identity, work group, checkout,
journal, diagnostics and fixed launcher paths. Slot selection keeps the complete
installation digest stable and is bound to the configured runner name, actual
Unix UID and immutable protected attempt envelope. The root Writer selects
retained evidence through that stored envelope, never through a caller path.

The candidate parallel projection uses `relay-workflows-v4`; ordinary projections
retain `relay-workflows-v3` and the SERIAL group. Parallel native-run groups retain
`queue: max` and cancellation disabled. A finite qualified runner pool bounds
active jobs. GitHub groups are repository-local: independent consumer
installations sharing a host additionally need distinct namespaces, identities,
paths and capacity allocations. A multi-repository Writer selects only an
explicitly configured repository per operation process; native groups do not
provide that authorization or physical isolation.

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
waiting population. GitHub's limit of 100 pending runs applies to each
concurrency group; independent run groups can also wait for a runner. GitHub
owns runner waiting and queue
overflow/cancellation records. There is no Relay-wide durable queue or automatic
retry. Pending runs do not consume an admitted execution slot, and an overflow
or cancellation before controller entry creates no invented admission/Outcome.

## Independent attempts and scoped holds

Fresh schema-v4 native owner commands allocate monotonic unique Steps from
successful immutable admissions under the bounded trusted Writer lock. Earlier
attempts need not have terminal Outcomes or completed publication for an
independent Step on the same Task, or an independent Task, to be admitted.
Two manual handoffs, two automatic attempts or mixed routes retain separate
run/attempt lineage. A manual handoff is not evidence of physical slot occupation;
it does not assert whether the owner later launched the manual session.

Automatic attempts require a free bound slot and a distinct
`workRoot/<attemptId>` checkout. Checkout creation reserves the final directory
atomically; an existing checkout is preserved and rejected. Shared runtime UIDs
are allowed when attempt filesystem and process boundaries are isolated. An
unknown child holds the slot and resources it could affect; a missing unrelated
Outcome or an unreadable journal for a known different slot does not reserve
those resources. A record whose shared identity or migration ownership cannot
be attributed safely still fails closed and identifies the conflicting record.

After verified containment, complete collection durably saves an exact head,
known clean/dirty observation and `collection.preserved: true` before Writer
publication. That receipt proves that work remains in its retained attempt
checkout and permits physical slot reuse even if the original Outcome or
publication is pending. Existing strong terminal completion receipts keep their
original meaning. No old record is rewritten and no new model call is inferred.

Effects remain separate: pending or uncertain publication holds the exact shared
Git ref, PR or operation and requires its original read-back recovery. Independent
computation grants no right to replace a sibling's output, move an unexpected
remote head, restore an older Step/title, bypass current authority or repeat an
ambiguous push/POST. Full lifecycle Apply, quiesce/drain and protected pool
ownership still require their global evidence.

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
label, owner/run binding, effective authority, exact head and scoped physical
resource/effect conflicts. Applying another ready transition can invalidate an
older queued command. A distinct fresh schema-v4 native command may admit an
independent attempt before an earlier Task Step completes; it cannot reuse a
consumed event or retry that attempt. Retained v3/legacy prior-run ordering keeps
its original checks. See
[native command verification](../controller/src/live-authority.mjs) and
[prior-attempt verification](../controller/src/publication-broker.mjs).

Native timeline IDs order ready transitions, including within one timestamp
second. Initial commands with multiple distinct ready-label additions in that
second stop with `READY_EVENT_AMBIGUOUS`, because the run API cannot identify
which event triggered the run. Consumption reserves one DELETE, checks the
original event again immediately before it and reads back both labels and native
transitions. A replacement may occur inside GitHub's non-atomic DELETE interval
and may already have been erased. `READY_EVENT_REPLACED` or
`READY_CONSUMPTION_UNCERTAIN` retains the original attempt, starts no worker and
reports the affected original/later event IDs and a fresh-command path. The
operator inspects the target, removes any remaining ready label and reapplies
the intended command in a later second. No blind DELETE retry or automatic
replacement command is issued. Step-label projection uses individual mutations
to preserve later owner commands.

Cancellation or overflow before the queued job enters the controller leaves an
owner-visible native canceled run and creates no Relay admission, Step, journal,
Writer Outcome or model call. Inspect that native run and the protected original
attempt state before deciding whether shared resources are safe. A fresh owner
command must satisfy current authority and its scoped resource/effect checks; no background
retry, synthetic success or substituted Outcome is created. Cancellation after
controller entry retains the existing containment, durable evidence and unknown
execution rules. A canceled run alone is not proof that no attempt was admitted.

The root publication lock and
[lifecycle quiesce/drain](../controller/README.md#lifecycle-admission-and-drain)
remain unchanged. Quiesce closes admission, admitted controllers may complete,
and drain requires their containment/publication/terminal receipts even if a
physical slot has already been released. Native
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

Local scenarios cover independent Issues and same-Task attempts, manual/automatic
routes, shared-slot and checkout exclusion, same-UID process overlap, uncertain
publication, ready-event races, Issue/PR number collisions, foreign-repository
numeric identity rejection, replay, unresolved attempts and quiesce/drain.
Cross-repository fixtures use the configured repository selection and preserve
original attempt bindings; they do not qualify live routing. Native TEST observations must additionally
show multiple waiting runs surviving, serial worker entry and truthful terminal
state. Independent parallel execution and future many-repository scheduling
require native qualification; native concurrency groups alone do not coordinate
different repositories, establish installed isolation or authorize a Writer target.
