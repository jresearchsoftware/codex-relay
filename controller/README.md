# Codex relay routing

Load an explicit [consumer configuration](../consumer/README.md) before execution.

The owner launches fresh Issue work, explicitly authorized Issue implementation
continuation or applicable PR remediation by applying
`codex-ready-auto`; `codex-ready-manual` produces the existing copyable manual
handoff. These are first-class native commands. No Actions UI, dispatch inputs,
comment command or additional launch form is required. Owner `workflow_dispatch`
on the configured base branch remains an optional fallback with `task`, `step`, `route` and optional
`pull_request`; those inputs must match current metadata and applicable Issue/CR authority.

The canonical Issue retains exactly one `step-N` label throughout its lifetime.
Fresh work uses `step-1`; explicit owner new-phase preparation advances current
N to N+1 for a reopened or split continuation. Same-phase retry explicitly keeps
Step. Writer copies the Issue Step to
its created PR, without incrementing or removing the Issue label. Step alone
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

A new executable `REQUEST_CHANGES` carries N+1 from the current synchronized
Issue/PR labels. After successful native publication, the same Reviewer operation
synchronizes both labels and the existing bounded PR Task/Step/CR-ID title via the
[metadata procedure](../contracts/README.md#owner-step-metadata-procedure).
The Reviewer App owns verdict publication and that bounded post-CR projection.
Repeating publication or metadata repair retains the same native review ID and
authored Step; ordinary owner orchestration no longer writes post-CR metadata.
Explicit owner preparation is limited to a newly authorized implementation phase.
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

Fresh Issues use the exact configured base at admission and `<taskBranchPrefix>task-<issue-number>`
when base/branch fields are omitted, without warnings. A malformed or conflicting
explicit base blocks; the admitted exact base cannot move during execution.
The Issue template asks for an explicit closure decision. Missing or malformed
closure selects `keep-open` with an operator-visible warning.

## Issue-authorized implementation continuation

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

Only an open PR for the admitted repository, branch and configured base may
receive Issue publication. Closed and merged PRs using that branch remain
history: they neither block a fresh PR nor receive labels, readiness changes or
terminal Outcomes. A single current PR must retain the exact repository, branch
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

Successful recovery can continue the existing `finish` path without replaying
the original routing workflow. It retains the original execution receipt, checks
the exact checkout head and worktree state, observes the PR head, marks the PR ready and updates
the original Writer-owned blocked Outcome comment in place. A partially failed
finish can be resumed using the same successful publication receipt; it cannot
push again. A blocked/unknown original execution cannot claim readiness. Known
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
