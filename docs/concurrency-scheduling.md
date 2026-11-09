# Relay control scheduling

Relay uses one managed General Runner pool with a configured physical capacity
from 1 to 32 across its eligible repositories. Capacity 1 is the same managed
model with one active runner. Current routing uses independent native run
groups, trusted reservation and scoped publication/resource locks; it does not
select a separate SERIAL execution or scheduling model.

## Shared managed pool

The required `consumer.generalRunnerPool.desiredCapacity` selects one fixed
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

Routing uses `<namespace>-control-${{ github.run_id }}` with
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
model retry. Current source projects the managed v4 contract. Historical v3
workflow bytes and validators retain their original meaning for already-admitted
attempts; they are not a fresh projection or installation option.

Source checks, synthetic same-UID process tests and live model observations
prove different things. Installed qualification must observe the actual shared
pool, simultaneous automatic model processes, bounded occupancy, attributable
terminal Outcomes, capacity reconciliation and original-run recovery. Earlier
distinct-UID TEST evidence does not establish these new properties. See the
[deployment contract](../deploy/README.md#shared-managed-general-runner-pool).

## Retained topology and queue evidence

Managed configuration derives a stable internal layout of 32 execution slots;
desired physical capacity does not redefine it. Current deployment input rejects
a separate caller-authored slot topology. Exact older slot/configuration and
SERIAL digests remain readable under the admitted original source when retained
history requires them. New installation, projection and native admission cannot
select those historical execution models.

Each automatic controller retains its lifetime kernel lock, exclusive initial
journal and bounded diagnostics-retention lock. Different run IDs can progress
independently. Writer's publication lock holds no model execution. Original
same-run replay, starting-head and exact-attempt recovery requirements remain
bound to the retained attempt.

The physical pool bounds active executions. GitHub owns native waiting,
overflow and cancellation evidence; pending runs do not create Relay admissions.
There is no separate Relay durable queue or automatic retry. GitHub's
[workflow concurrency contract](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#concurrency)
defines queue limits and ordering. Repository-local groups do not provide
installation-wide authorization or physical capacity by themselves.

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

## Historical runtime audit and current bounds

Historical SERIAL inventory, including Task 103's TEST evidence, described one
General Runner and a separate Production Runner. That old layout is retained
evidence, not the current deployment default or a supported fresh source model.
Current [configuration](../deploy/config.py) and
[templates](../deploy/workflows/) bind derived managed members; the separate
Production Runner cannot supply extra automatic capacity. Installed results and
their limits remain in their original PR/Writer Outcomes.

Attempts already have distinct `workRoot/<attemptId>` checkouts, task-local
HOME/CODEX_HOME/XDG/cache/tmp paths, diagnostic references, owned process groups
and unique trusted Git import repositories. Collection precedes publication
only after containment and observes bounded regular bytes rather than executing
worker-modified Git metadata. See [attempt preparation](../controller/src/attempt-runtime.mjs),
[the fixed launcher](../deploy/ansible/roles/relay_codex_runtime/templates/relay-codex-launcher.mjs.j2),
[process containment](../controller/src/github.mjs) and
[trusted collection](../controller/src/trusted-git.mjs).

Those separate paths were insufficient proof of parallel isolation. The
historical SERIAL topology shared one runtime UID and work group. Its audit
identified journal reservation, diagnostic eviction and a five-second Writer
lock wait against a two-minute Git operation as concrete race/capacity gaps.
The current source addresses those stores and waits above, but those changes
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
