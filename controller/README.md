# Codex relay routing

Load an explicit [consumer configuration](../consumer/README.md) before execution.

For the ordinary human path, see the [Task workflow guide](../docs/task-workflow.md).
A Task marked `Authority model: github-native-v1` executes the complete current
trusted Task Request or native Change Request, with its explicit Step, route,
profile, scope and starting facts. Issue bodies are stable charters; labels and
titles are verified projections. Unmarked Tasks retain legacy Issue/CR parsing.
Use the [authority contract](../contracts/README.md#github-native-task-authority)
for migration, trust, supersession and selected context.

The owner launches fresh Issue work, explicitly authorized Issue implementation
continuation or applicable PR remediation by applying
`codex-ready-auto`; `codex-ready-manual` produces the existing copyable manual
handoff. These are first-class native commands. No Actions UI, dispatch inputs,
comment command or additional launch form is required. Owner `workflow_dispatch`
on the configured base branch remains an optional fallback with `task`, `step`, `route` and optional
`pull_request`; those inputs must match current metadata and the selected typed
Request or legacy Issue/CR authority. Labels do not select a different route
from a migrated Request's `route`.

The canonical Issue retains exactly one `step-N` label throughout its lifetime.
Fresh work uses `step-1`; a migrated successor Request explicitly advances N to
N+1 for a new phase. Legacy Tasks use owner new-phase metadata preparation.
Same-phase retry explicitly keeps Step. Writer copies the Issue Step to its
created PR, without incrementing or removing the Issue label. Step alone
never launches work and grants no authority. Missing, multiple, malformed or
mismatched labels block new admission. The `step` label namespace is reserved.

The trusted Writer verifies the owner actor and triggering actor, repository,
workflow path, first native run execution, native title binding, current command
event, canonical Issue and applicable starting-head/CR authority. Issue label events use `issues`;
PR label events use `pull_request_target` to run the default-branch workflow,
with read-only workflow permissions and a trusted configured-base checkout. PR branch
bytes are never executed by this routing job. Once the owner event, target and
ready command are safely bound, the Writer reserves that event in the existing
bounded attempt record and consumes the command exactly once, including when
Step or Issue/CR/head admission is rejected. Safe rejection publishes one
`BLOCKED_BEFORE_WORKER` Outcome on the bound target; no Codex worker starts.
Correct the metadata/authority and apply the ready label again for a fresh
event. An invalid event-time Step cannot become valid through a later label
repair. Unbound, unauthorized, stale, cross-target or replaced commands cause no
label mutation or unrelated publication. An uncertain consumption stays reserved
and is never blindly repeated. Step stays in place. `runId` / `run-<runId>`
uniquely identifies the attempt. Same-run replay cannot repeat a model call, and a fresh run cannot
reuse the consumed native command event. The event must be the latest ready
transition, authored by the owner, no more than two minutes before native run
creation, and after completion of any preceding admitted run for this task.
Stale commands and prewritten retries fail closed; no retry queue is created.

A new typed executable `REQUEST_CHANGES` carries the current Request's Step + 1;
a legacy CR uses N+1 from synchronized Issue/PR labels. After successful native
publication, the same Reviewer operation
synchronizes both labels and the existing bounded PR Task/Step/CR-ID title via the
[metadata procedure](../contracts/README.md#owner-step-metadata-procedure).
The Reviewer App owns verdict publication and that bounded post-CR projection.
Repeating publication or metadata repair retains the same native review ID and
authored Step; ordinary owner orchestration no longer writes post-CR metadata.
Legacy owner preparation is limited to a newly authorized implementation phase;
the typed publisher owns migrated successor Request projections.
Execution retries keep Step;
`APPROVE` does not increment it. New remediation must match the current CR's
required launch profile; Step display metadata never replaces that authority.
A historical published record without a Reviewer Step anchor may require
[explicit bounded migration recovery](../contracts/README.md#legacy-publication-migration-recovery)
on `LEGACY_STEP_BINDING_REQUIRED`; replay retains its native review ID and Step.
This is not a normal owner post-CR writer. There is no Step-history scan, counter,
registry, ledger or workflow engine.

Actions evaluates native metadata at run creation. Issue names use the Issue
number and native label projection, for example
`Auto implementation · Task 12 · step-5 · codex-ready-auto`. Unrelated Issue
labels also appear purely for display; adding, removing or reordering them
does not change launch authority. Admission binds only the ready command and
reserved Step metadata in the Issue label projection. PR names use the existing
synchronized bounded title, for example
`Auto remediation · PR #13 · Task 12 · Step 6 · CR purpose`; manual
names begin `Manual handoff`. Descriptive PR tails are bounded, and Task/Step
lead the title. A stale Task/Step or ready-command projection blocks new label
admission. Neither Issue prose nor arbitrary PR/CR prose is parsed to construct
the pre-start name.
This uses GitHub's native [run-name contexts](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#run-name)
and [label projection/join expressions](https://docs.github.com/en/actions/reference/workflows-and-actions/expressions#join).

Legacy fresh Issues use the exact configured base at admission and `<taskBranchPrefix>task-<issue-number>`
when base/branch fields are omitted, without warnings. A malformed or conflicting
explicit base blocks; the admitted exact base cannot move during execution.
Typed repository Requests include explicit `base_sha`, `starting_head` and
`branch`; admission does not fill these fields from old Issue-body prose.
The Issue template asks for an explicit closure decision. Missing or malformed
closure selects `keep-open` with an operator-visible warning.

## Issue-authorized implementation continuation

The fields in this section describe legacy Tasks. After explicit migration to
`github-native-v1`, a complete trusted Task Request supplies starting-state,
Step, route, profile, scope and permission bindings. Historical body execution
prose is not parsed. The publisher projects Step labels and the bounded PR
title; a projection mismatch is a visible blocker. Ordinary owner Step helpers
cannot become a competing writer for migrated Tasks. See the
[authority contract](../contracts/README.md#github-native-task-authority).

To continue implementation on an existing task branch, update the canonical
Issue's current goal and starting-state authority with these fields:

```text
Implementation continuation head: 0123456789abcdef0123456789abcdef01234567
Implementation branch: codex/task-42
Implementation pull request: #43
```

The head field opts in and must contain exactly one full 40-character SHA. The
existing branch must be explicit and valid; existing branch-field synonyms remain
recognized. The PR field is required when a current open PR exists and must name
that PR; omit it only when no open PR exists. Duplicate, malformed or conflicting
continuation head/PR fields, a PR field without a continuation head, or a missing
or invalid explicit branch block admission. Omitting continuation fields preserves
legacy fresh Issue admission. Existing base metadata keeps its fresh meaning and
is separate from the continuation task starting head.

Admission requires the exact live task-branch ref to match the Issue's starting
SHA. It counts open PRs for that branch across all bases before checking
compatibility: a current PR must be unique and match the configured repository
and base, canonical Issue linkage, exact starting head, Step label and bounded
Task/Step title. Closed and merged PRs remain history. The admitted current PR
number is pinned in the existing attempt record; closure, disappearance or
replacement cannot authorize another target or a replacement PR.

Apply `codex-ready-auto` to the canonical Issue using the existing owner launch
path; `codex-ready-manual` remains available for a copyable manual handoff. This
keeps Issue authority, the implementation operation and Writer commit identity.
It requires no Reviewer Change Request and grants no CR integration-merge
permission. An execution retry or continuation of the same unfinished phase
keeps Step. An explicitly owner-authorized new implementation phase advances N
to N+1 through the existing
[owner metadata procedure](../contracts/README.md#owner-step-metadata-procedure),
including the current PR when one exists. Step metadata alone grants no launch.

Before the first continuation push, Writer requires the remote at the admitted
starting head; after its own publication it requires `publishedHead`. It
revalidates live authority and the pinned PR, then reobserves the exact previous
Git ref before reserving the ordinary non-force push. Observed remote movement
blocks publication. Exact post-push observation and the existing uncertainty and
owner-authorized recovery rules remain in force. Ref observations and non-force
push do not provide atomic compare-and-swap against external ref changes. No new
service or state registry is introduced.

## Issue publication and worker handoff

For a migrated Task, authority parent and result surface are separate. Writer
records the native Request reference in the attempt and PR binding. It posts
the terminal typed Outcome on the unique durably known PR, or the Issue before
PR creation and for legitimate no-PR/no-change work. A pending PR creation
intent or ambiguous artifact blocks surface selection; it cannot fall back to
the Issue. No-change success requires a contained successful worker, complete
clean collection at the admitted source head and current authority; it performs
no push and creates no PR. The ordinary native `issue_comment` event on that
typed Outcome is the completion signal: automation verifies Writer identity,
Request, attempt and immutable result before acting. No additional label,
receipt comment, Check or parallel completion ledger is needed.

A manual non-source Request may omit branch/base/head and receives the same
minimal handoff. Manual results use the existing trusted Writer protocol's
bounded `manual-outcome` operation with the admitted `runId`, `attemptId` and
one native owner `authorizationId`. The source comment on the Task contains
only a canonical typed `outcome` object in a `relay-manual-result` fence. This
is authorization to publish that manual result, not execution authority or an
ordinary comment that changes scope. Writer verifies the owner native identity,
the current Request, charter and exact result bytes, reserves the source ID and
digest, re-reads it and publishes one typed Outcome. It does not import Git,
launch work, approve, deploy, merge or close anything. The manual result can
identify immutable checks/runs without inventing a Git head. A PR result must
be uniquely bound to the Task in the PR body, including a disposable PR already
closed without merge; Writer does not reopen it. When the Request has no
`existing_pr`, Reviewer discovers its artifact by branch and requires both
exact standalone binding lines in that body:

```text
Execution request native ID: <reference.id>
Execution request digest: <reference.sha256>
```

Copy both values from the trusted Task Request publisher's returned `reference`.
The digest covers the complete native Request comment, including publication
provenance, not only its JSON payload. Retain the ordinary `Related to #N` Task
linkage. Automatic Writer PR creation already emits both lines; an owner-created
manual PR needs the same binding for Reviewer discovery and Task Approval,
including after the disposable artifact has been closed.

For automatic Git publication, only an open PR for the admitted repository,
branch and configured base may receive publication. Closed and merged PRs using that branch remain
history: they neither block a fresh PR nor receive labels, readiness changes or
automatic terminal Outcomes. The manual-result exception above uses the exact
already-disposed artifact without changing its lifecycle. A single current PR
must retain the exact repository, branch
and Issue linkage; multiple current candidates fail closed. Before mutating a
resolved target, Writer records its PR number in the existing attempt receipt.
A missing or replaced target then blocks continuation rather than creating or
adopting another PR. With no current or previously resolved PR, a blocked Outcome
targets the admitted Issue. The same current-target resolution
applies to owner-authorized publication recovery, preserving its exact previous
head check. A reserved PR creation is never repeated merely because no open PR
is visible, including when the created PR has since closed. Before a PR number
has been observed, uncertain creation must reconcile a compatible current PR
carrying the same native attempt marker or stop without another POST.

The automatic worker follows [progress-bounded execution](../docs/execution-policy.md):
it may iteratively diagnose, correct and validate any repository file required
by the admitted goal. Writer identity, the task commit chain, safe Git paths and regular-file modes,
repository sandboxing, secret scanning/redaction, starting-head/branch identity,
and Writer/Reviewer authority separation remain enforced. It never publishes
directly. The Writer publishes one terminal Outcome, including bounded and
redacted worker summary/validation claims separately from observed Git metadata.
Actual model/effort remains `UNAVAILABLE` unless runtime evidence exposes it;
claims never establish native CI success. Native exact-head CI, independent
review, merge and Issue closure remain separate gates. Unavailable usage is reported
as unavailable; it never authorizes another model call.

Before returning, the governed worker reconciles task-owned changes under its
actual identity and permissions: preserve meaningful work in ordinary commits,
remove only confirmed disposable residue when safe, and report anything that
cannot be reconciled. Collection imports object bytes into a fresh repository;
it never runs trusted Git against worker metadata. Git observation failures,
including unreadable worktree paths, cannot stand in for a clean/dirty result.

After known terminal, contained success and durable PR/Outcome publication,
remaining uncommitted/non-ignored residue alone is a green
`COMPLETED_WITH_WARNINGS` handoff. `UNCOMMITTED_WORK_REMAINS` remains in the
terminal receipt, Outcome and workflow warning, including on terminal replay.
It requires reconciliation against the worker claims and published diff at the
next owner/review boundary. The controller does not classify arbitrary bytes as
generated, silently discard or commit them, publish them, or launch another
worker. Blocked execution with unreconciled work and unknown execution,
containment, collection, authority, evidence or publication remain failures.

Run `npm test` here and the affected runtime/contract suites. Consumer-owned
installed runtime/user/sudo proof requires its separate integration checks.

## Lifecycle admission and drain

The root-only, credential-free `relay-admission` helper controls automatic
Issue and CR admission. Its durable gate is
`paths.claimRoot/admission-v1.json`, outside runner and worker write access.
The gate and Writer share `publication-v2.lock`. New automatic admission checks
the gate and reserves `controllerLifecycle` in the existing Writer attempt
record under that same lock, before consuming the ready label. Quiesce closes
the gate under the lock, so it cannot race an admitted execution reservation.
A refused automatic launch reports `ADMISSION_QUIESCED`, starts no worker and
does not claim a terminal Outcome. Manual handoff and publication-only recovery
retain their existing authority and remain available.

An automatic reservation covers the complete controller invocation: checkout,
Codex execution and containment, collection, Writer publication, and durable
terminal receipts. An already admitted invocation may finish while admission
is quiesced. A model exit or an idle runner does not establish drain. The last
trusted controller operation asks root to release its reservation; root reads
the matching runner journal itself and requires known containment, matching
terminal receipts and no unresolved publication intent. Caller JSON cannot
assert that proof. Earlier attempts without `controllerLifecycle` require the
same existing terminal journal evidence. Missing, mismatched or unknown
execution and ambiguous publication fail closed.

Drain polls bounded snapshots and releases the Writer lock between snapshots,
allowing admitted controllers to finish. It emits only bounded active/unknown
counts and elapsed time on stderr every thirty seconds; stdout remains one JSON
receipt. Timeout, unreadable state or an unknown attempt preserves quiesce for
owner inspection. Drain neither relaunches Codex nor discards retained work or
diagnostics. Registered runners remain online; graceful stop disables new
automatic admission without stopping those runners.

The gate binds one lifecycle operation UUID, the exact selected target and the
consumer digest. Its phases are `open`, `quiesced`, `drained`, `applying`,
`verified` and `recovery-required`. A successful graceful stop retains
`drained`, which is still quiesced admission. Initial installation initializes a
missing gate but preserves existing state. Managed lifecycle installation only
reads the required gate; a missing gate fails closed. No restart, failed apply or recovery
implicitly reopens admission. Resume requires an explicitly verified installed
revision and no active or unknown attempts. The public deployment coordinator
owns deployment authority and same-operation verification; the helper stores
only lifecycle control state and reuses the existing attempt records.

During `applying`, the trusted backend records its original Reviewer,
production-runner and general-runner activity/enablement intent through
`snapshot --operation UUID` with bounded JSON on stdin. The gate stores the
first complete known snapshot in `previousActive` and returns that same intent
on subsequent calls for the operation. A failed activation therefore cannot
replace formerly active intent with the failure's current inactive state.
Recovery retains this snapshot; successful resume clears it. Unknown or
incomplete activity cannot establish a snapshot or deployment proof.

An explicitly owner-authorized recovery may select an exact accepted rollback
revision through the root-only `recovery-target --operation UUID --target SHA`
operation. It requires the bound `recovery-required` phase and no active or
unknown controller records. It changes only the target, retaining the original
service intent for the same operation. Ordinary apply cannot retarget its
admission; rollback still requires installed verification before resume.

## Reviewed base reconciliation

A dirty reviewed PR may enter remediation through the owner's ready label or optional dispatch.
Its current Change Request, linked Issue, branch and exact reviewed starting head
remain mandatory. The Writer observes the configured base once at admission and checks
that observation at preflight; trusted checkout fetches that exact base and proves
shared Git ancestry before the Codex child. A moved base, unrelated history or
changed authority blocks. Fresh Issue admission is unchanged.

When the admitted remediation requires integration, the worker may add one local
two-parent merge commit to its task branch. The first parent must be the previous
task head and the second exactly the admitted current base. Other task commits
remain linear. Every task commit, including the integration commit, must carry
the expected remediation bot identity. Already-published base ancestors retain
their original authors. No other merge parents, repeated integration, rebase,
amend, reset, history rewrite or force publication is admitted.

Writer validates each task commit against its first parent, including all paths,
file modes and blobs introduced by the merge resolution. Transient secrets in
task commits remain rejected. It reobserves admitted base before integration
publication or owner-authorized recovery and retains the ordinary fast-forward
push and exact remote-head checks. PR mergeability, native exact-head validation
and independent review remain separate completion gates; admission of a dirty
input never means its unresolved output is approved.

### Publication, execution handoff and integration readiness

Native PR Draft/Ready state projects Codex execution handoff only. Writer keeps
an active implementation/remediation PR Draft. Blocked, incomplete, failed and
unconfirmed execution stays Draft, including a domain `BLOCKED` Outcome and a
controller/journal failure after a successful worker return.

Successful `finish` publishes and reads back one successful exact-candidate
Outcome while the PR is still Draft. `complete-handoff` then reads the protected
runner journal: returned successful execution, containment, complete collection,
exact candidate and matching durable Outcome are required. Writer completes the
controller reservation, reserves the exact native lifecycle intent, revalidates
authority, marks that PR Ready and reads back the same open PR/head/state.
Ready means execution was durably handed off for independent review. It supplies
no review verdict, check proof, merge authority or integration proof.

A failed Ready mutation retains the successful Outcome and Draft. A lost response
or unavailable readback retains the exact pending intent; no Ready success is
claimed. Native state may be uncertain until a fresh read reconciles it. Same-run
replay, or the bounded Writer `complete-handoff` operation with the original
`runId`/`attemptId`, resumes this transition without another worker, push or
Outcome POST. A matching observed Ready state reconciles an accepted mutation;
a fresh observed Draft permits the same idempotent transition. Changed head,
PR, authority or Outcome stops recovery. Completed replay returns the stored
receipt. The runner's terminal receipt precedes Ready; the Writer's lifecycle
receipt records its verified native state. A pending transition prevents a
controller drain from claiming completion.

After successful native `REQUEST_CHANGES` publication, Reviewer returns the
bounded Writer lifecycle action in `structuredContent.pr_lifecycle`. The normal
production routing entrypoint consumes the equivalent action from the verified
current native CR during Writer admission, before reserving automatic execution
or consuming the ready command. Both label and workflow-dispatch routing follow
this path, for automatic and manual remediation. The action is bound to the
admitted CR's authority digest as well as its native review ID and exact head.
Manual handoff revalidates the same Draft transition before publication because
manual routing has no worker preflight.

An owner orchestration channel with the successful Reviewer response can also
complete the same idempotent transition directly:

```js
import { continueAfterChangeRequest } from './src/pr-lifecycle.mjs';
await continueAfterChangeRequest(reviewerPublicationResult, writerAdapter);
```

Writer's `begin-remediation` accepts only the PR number, native review ID and
exact head. It re-reads the current executable CR, canonical Task, Step and
trusted Reviewer Bot identity, reserves the transition in an atomic lifecycle
receipt keyed by that native review, converts the PR to Draft and verifies the
exact target again. This grants no launch, push, Outcome, review, merge or closure
permission. Failure/uncertainty stops remediation continuation; replay reconciles
that same current CR/head. An admission-time lifecycle failure leaves the ready
command and execution reservation untouched. A lost mutation response is
reconciled by exact native readback; an unavailable readback retains the lifecycle
intent for replay without republishing review authority or launching a worker.
Admission replay for an existing execution does not draft a completed candidate;
its protected attempt journal and normal preflight govern continuation.
Reviewer publishes review authority and projections,
never the Draft mutation. Preflight also verifies Draft before worker execution.
Draft is a valid remediation starting state, and publication recovery of the
same CR remains supported after Writer drafts it. Fresh review still requires
Ready. No new routing event, credential or App permission is introduced.

Manual results retain the existing owner-authorized `manual-outcome` operation.
An open PR requires the successful exact Git candidate and durable successful
Outcome before its verified Ready transition; blocked results draft it. Replay
reuses that Outcome. Disposed manual qualification artifacts retain their state.
No-PR results keep the canonical Outcome and existing notification path; they
create no additional completion signal.

Successful publication remains `IMPLEMENTED_PENDING_FRESH_REVIEW` independently
of integration readiness. Writer reports `readiness.status`: `PENDING` for
null/unavailable mergeability, `BLOCKED` for a proven conflict, or `READY` for
observed mergeability. Pending/conflicting candidates can be native Ready after
successful execution handoff. Checks, base movement and review/integration
problems do not draft a completed candidate. Further source work starts through
a new independent `REQUEST_CHANGES` and its verified Draft transition.

The bounded Writer `observe-readiness` operation revalidates the completed exact
candidate and current authority, observes mergeability/base and updates the same
Outcome's integration snapshot. It never mutates Draft/Ready, executes a worker,
pushes, polls, rebases or merges. Candidate validation and independent review
remain bound to the candidate commit, rather than a synthetic merge commit.
Public consumers retain `pull_request_target` label routing under the
[owner Actions event-policy procedure](../deploy/README.md#actions-event-policy-for-public-repositories).

## Writer publication recovery

Ordinary `publish-progress` replay still observes an existing publication intent
and refuses another push when the remote is not the candidate. Recovery is a
separate owner operation. It never prepares a checkout or launches Codex.

## Operator procedure

The consumer supplies the owner identity, recovery workflow, installed command
and configuration path. Inspect the preserved attempt, post its exact generated
authorization as a new unedited owner comment on the admitted target, then use
a fresh recovery invocation. The helper accepts bounded JSON on stdin and never
accepts caller-selected executable, checkout, credential or remote paths. Its
read-only workflow token and separate Writer credential boundary remain intact.

## Authority and receipts

The generated comment binds repository, target kind/number, canonical Issue,
branch, original run/attempt, admitted authority digest, previous remote SHA,
candidate SHA, and the previous consumed recovery authorization (or `null`).
Writer retrieves the comment directly from GitHub, verifies its owner, target,
native creation/edit timestamps and exact body, and checks that the admitted
owner routing run is completed. Recovery also binds the original
transport and Task/Step/phase/PR title; current label-run receipts retain the
consumed native event identity without requiring the command label to survive. The durable attempt identity remains
unchanged if that workflow was rerun; authorization must postdate its latest
completion. No label, workflow rerun,
free-form approval or caller-provided assertion substitutes for that comment.

Before reserving a push, Writer revalidates live Issue/PR/Reviewer authority,
checks the candidate through the same bundle importer and commit validator as
ordinary publication, proves the task's first-parent chain from the admitted and
previous heads (with only the bounded base reconciliation above), and observes
the remote again at exactly `publicationIntent.previous`.
Wrong or missing candidates, changed authority/heads, unsafe paths/modes,
incorrect commit identity or secret-bearing commits cause zero recovery pushes.

Under the existing root Writer lock, `publicationRecoveries` adds one bounded
intent/receipt per native comment to the existing atomic attempt record. The
reservation precedes the sole ordinary, non-force push. Space for bounded
failure diagnostics is reserved before mutation. The immediately following
remote observation determines publication; even a nonzero push exit is success
if the remote is observed at the exact candidate. A successful atomic write sets
`publishedHead`, clears `publicationIntent` and records the recovery receipt.

Replaying a consumed authorization returns its stored receipt (or fails closed
for an unfinished reservation) without another push. Failed receipts remain
durable. Another push needs a new owner comment, created after the preceding
recovery and explicitly naming its authorization ID. Prewritten approvals cannot
form a retry queue. There are no retry counters, loops, timers or schedulers.
If a push/observation or receipt write is ambiguous, stop and inspect the saved
intent, receipt and remote before a new owner decision. A remote other than the
recorded previous head blocks a new recovery push.

## Readiness and diagnostics

Migrated PRs use `Related to #Task` even when closure is authorized. Writer
projects a legacy canonical closing reference to this nonclosing relationship
during preflight, preserving other PR text and verifying the exact readback.
Native manually linked closing relationships are inspected by the trusted owner
continuation adapter before merge. Issue closure happens explicitly after
independent acceptance, Task completion and remaining-work checks; repository
auto-closing settings are not changed by this worker or Writer.

Successful recovery can continue the existing `finish` path without replaying
the original routing workflow. It retains the original execution receipt, checks
the exact checkout head and worktree state, observes the PR head, publishes and verifies its
successful Outcome before the protected execution handoff makes it Ready, and updates
the original Writer-owned blocked Outcome comment in place. A partially failed
finish can be resumed using the same successful publication receipt; it cannot
push again. Unresolved integration stays pending; proven conflict blocks
readiness while retaining successful publication. A blocked/unknown original
execution cannot claim readiness. Known
successful execution with residue retains the same actionable warning as normal
completion; collection failures remain red. Native exact-head validation, independent review, merge, deployment
and Issue closure retain their separate gates.

The durable recovery receipt preserves the trusted Git layer's sanitized push
and observation diagnostics, including classification, operation, exit/signal,
UTF-8-bounded preview, byte count and truncation flag. When both fail, the failed
push preview remains the primary recovery diagnostic and the observation failure
is retained separately; this does not assert that the remote stayed unchanged.
The helper wire and terminal JSON preserve that safe primary preview in
`diagnostic.publicationRecovery`. Raw stderr and protected diagnostics are never
copied.

## Runtime diagnostic retention

Governed runtime attempts reserve an independent diagnostic capsule under
`paths.attemptRoot/runtime-diagnostics` before launching the dispatcher. It is
outside the runtime user's mutable checkout and separate from the root-owned
primary diagnostic store. File and directory synchronization precede the stored
reference. Each capsule contains only bounded, allowlisted execution/lifecycle
fields, OS codes and syscalls, categorical path context, protected sandbox inode
identity and sanitized store references. Primary bundles may additionally retain
bounded redacted path context; Outcomes never include those paths or raw streams.

The automatic terminal Outcome projects the existing launcher diagnostic code,
bounded categorical primary cause, inner Codex started state/exit code/signal,
observed stderr byte count and truncation, and diagnostic-store availability.
Missing values stay explicitly unavailable. Launcher, dispatcher and Git exits
or signals never substitute for inner Codex observations. Diagnostic previews
and stream contents remain protected; this projection creates no new store.
Automatic Outcomes also preserve bounded native token counters from the original
execution through replay/recovery. Their
[native session-total semantics and limitations](../docs/codex/cli-integration.md#safe-automatic-evidence)
are independent of worker semantic claims and billing.

There are eight atomically reserved slots. A capsule and at most one interrupted
temporary write occupy each slot; unknown, failed or retained attempts are never
automatically evicted. A full store blocks admission before child launch. A
successful contained run marks its capsule released only after cleanup succeeds;
the tiny completion trace remains until a new reservation replaces it under an
exclusive reclamation claim. Interrupted reclamation also blocks slot reuse and
preserves both bounded records. Released capsules never imply retained sandbox
artifacts. A
failed diagnostic capture/store or cleanup retains the protected attempt artifacts
and its reference for owner inspection. Inspection and later disposal use the
execution ID and slot to correlate with the attempt journal and configured work
root; a separate owner-authorized operation must establish that useful evidence
has been preserved before removing retained artifacts and freeing that slot.
This retention policy grants no new arbitrary-delete or diagnostic-read authority.

Physical failures during checkout preparation, attempt journaling, collection and
terminal publication also use this independent evidence path. An existing runtime
cause is preserved while a bounded controller cause is appended. Primary-store
failure is itself recorded in the capsule; if the fallback filesystem is also
unavailable, terminal evidence reports both unavailable stores explicitly without
replacing the original exception or deleting attempt artifacts.

Run focused regressions from the repository root with:

```sh
node --import ./consumer/test-support/consumer-env.mjs --test controller/test/publication-recovery.test.mjs
```

The complete local candidate checks are in [development guidance](../AGENTS.md).
Consumer workflows supply native exact-head and installed-runtime checks.
