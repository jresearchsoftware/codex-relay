# Codex relay routing

Load an explicit [consumer configuration](../consumer/README.md) before execution.

For owner acceptance and ordinary authorized standalone/manual work, see the
[Task workflow guide](../docs/task-workflow.md#owner-acceptance-and-execution-routes).
This contract describes native Relay routing, not a requirement to fabricate
native admission for the standalone route.
A Task marked `Authority model: github-native-v1` uses its current stable charter,
applicable trusted Decisions and an independent exact-head native Change Request
when remediation is needed. New schema `4.0` execution snapshots are created by
trusted Writer at admission; no complete public Task Request or authored Step is
required. Writer resolves route, profile, scope and starting facts and allocates
Step once in the protected attempt record. Labels and titles are projections.
The current Node runtime accepts schema-v4 admissions only; legacy Issue parsing,
complete v3 Request selection and CR2/YAML execution are retired. Exact already
admitted schema-v3/legacy operations complete, publish or recover through their
frozen original source and unchanged bindings. Fresh unmarked work fails with
`CURRENT_PROTOCOL_REQUIRED`; historical Requests are opaque evidence and supply
no execution fields or additional migration gate.

A trusted historical schema-v3 Decision can remain in native provenance. Exact
already-admitted v4 result handling verifies its selected native identity and body
hash. For fresh work, later active v4 Decisions must already replace every effective
historical amendment field; no extra Decision or formal supersession is required
when existing evidence does so. Still-effective unhandled v3 semantics stop with
`CURRENT_PROTOCOL_REQUIRED`. A current decisive PR remediation review must be v4;
old Request history does not establish a separate purpose/scope amendment gate.
Use the [authority contract](../contracts/README.md#github-native-task-authority)
for migration, trust, supersession and selected context.

The owner launches fresh Issue work, explicitly authorized Issue implementation
continuation or applicable PR remediation by applying
`codex-ready-auto`; `codex-ready-manual` produces the existing copyable manual
handoff. These are first-class native commands. No Actions UI, dispatch inputs,
comment command or additional launch form is required. Owner `workflow_dispatch`
on the configured base branch remains an optional fallback with `task`, `step`, `route` and optional
`pull_request`; compatibility inputs cannot replace current authority. For new
schema `4.0` admissions the ready command selects the route and Writer allocates
Step. Exact old replay/recovery stays on its original route and runtime; these
inputs cannot re-admit it through current code.
The dispatch fallback does not bypass the fresh-v4 protocol gate.

At a genuinely new routed admission, Writer reads the canonical Issue's single
valid `step-N` position under its existing serialization lock and compares it
with successful durable admissions. The next Step is N+1; without a label it is
last admitted Step+1, or 1 when neither exists. An owner-maintained position
above Writer history permits standalone iterations. A position below successful
history, malformed/conflicting labels, overflow or a concurrent position change
fails with an actionable diagnostic. Rejected launches allocate no Step;
same-attempt replay/recovery retains its Step. The label supplies numbering,
never execution or admission authority. Writer projects the position only after
durable admission and verifies the native result.
A fresh command may admit independent work while an earlier Outcome is missing;
physical resource, exact-ref and publication guards still apply. Writer projects
the admitted Step/title on the Issue and each validated bound manual/automatic
result PR through one shared path; delayed association and safe same-Step repair
reuse that path without author restrictions or historical synchronization.
Exact older attempts preserve their original Step and projection checks through
their frozen runtime; they supply no fresh-admission authority. The `step` namespace remains
reserved; Step alone never launches work.

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
`CURRENT_PROTOCOL_REQUIRED` is outside that domain-blocker path: it stops before
new admission reservation, ready-command consumption, Step projection, worker
launch or Writer Outcome. A protocol mismatch cannot fabricate an old-schema
BLOCKED chain; the visible diagnostic identifies the current-v4 correction.
Correct the metadata/authority and apply the ready label again for a fresh
event. A rejected compatibility Step cannot become valid through a later label
repair. New schema `4.0` admission binds the resolved protected snapshot instead.
Unbound, unauthorized, stale or cross-target commands cause no label mutation or
unrelated publication. Native v4 consumption reserves one DELETE of the original
ready label, revalidates immediately before it and checks native timeline IDs
afterward. GitHub has no atomic event-conditioned DELETE: a replacement in that
interval may already have been erased. `READY_EVENT_REPLACED` or
`READY_CONSUMPTION_UNCERTAIN` retains the original attempt, launches no worker
and emits an actionable owner diagnostic; the DELETE is never blindly repeated.
Inspect the target, remove any remaining ready label and apply the intended
command in a later second. `READY_EVENT_AMBIGUOUS` rejects multiple distinct
ready events in the same timestamp second before consumption; identical native
event deliveries deduplicate by ID. Individual Step-label operations preserve
new ready labels. Retained v3/legacy consumption and exact replay keep their
original contract. Step stays in place. `runId` / `run-<runId>`
identifies the attempt inside its configured repository and installation. Protected
records verify the explicit repository; separate installations retain separate
roots even when native numeric run IDs coincide. Each runner journal uses an
exclusive initial file reservation and a Linux kernel lock for that run across
checkout, inference, collection and handoff. A competing same-run controller
reports `ATTEMPT_CONTROLLER_BUSY` without touching the original controller's
diagnostics or completion receipt. Independent run locks do not serialize model
calls; process death releases the lock while retained execution state still
prevents unknown work from being inferred again. Same-run replay cannot repeat a model call, and a fresh run cannot
reuse the consumed native command event. The event must be the latest ready
transition, authored by the owner, no more than two minutes before native run
creation. A later distinct native owner command may request an independent
attempt before an earlier attempt completes; it cannot reuse the earlier event
or authorize another invocation of that attempt. Retained v3/legacy prior-run
ordering remains unchanged. Stale commands fail closed; no retry queue is created.

The default SERIAL projection uses native Actions `queue: max` in the shared
control group. An explicit bounded parallel projection retains that queue
guarantee for each native run, using `<namespace>-control-${{ github.run_id }}`,
with installed execution slots providing finite capacity and protected Writer
reservations guarding actual shared resources. Independent automatic or mixed
attempts on the same Task can overlap when those resources permit it.
The pool bounds active automatic controllers to the configured slot count;
`queue: max` bounds native waiting to 100 per concurrency group. Distinct run
groups can also wait for the finite runner pool, so this is not a single
installation-wide pending-count limit. Native overflow or owner cancellation
before admission leaves the ready command unconsumed and visible on its target;
inspect its native and original protected state before using any shared resource. Cancellation
after reservation preserves that attempt and cannot trigger new inference.
The routing workflow uses an `exec` controller launch so native SIGINT reaches
its cancellation handler. Cooperative cancellation waits for the model-UID
launcher's group-reaping acknowledgement before durable terminal routing. Caller
lifetime pipes also request cleanup when the controller or dispatcher dies;
an abruptly killed controller may leave no terminal receipt, which remains an
unresolved original attempt even after physical child exit. Its uncertainty
holds only the resources it can affect; missing logical completion alone does
not block an independent Task or Step. Neither native
`cancelled` nor successful group signalling proves containment by itself.
Native groups coordinate only their GitHub repository; distinct repository
installations need separate protected paths and qualified host identities.
The two-minute ready-event check compares
event time with native run creation, so later job waiting does not change that
comparison; current authority and protected prior attempts are still verified
at admission. Native scheduling does not reserve a Step or permit a retry.
See [control scheduling](../docs/concurrency-scheduling.md) for cancellation,
overflow, runtime bounds and qualification limits.

A schema `4.0` native `REQUEST_CHANGES` binds the exact repository, PR, branch,
base and reviewed head, findings and bounded execution overrides. It does not
contain Step, require a replacement Request or independently authorize Task
closure. Reviewer publishes the independent review; Writer allocates Step and
projects metadata only when remediation is admitted. Repeating publication
retains the same native review ID. `APPROVE` allocates no Step. Remediation must
match the applicable CR's execution requirements; display metadata never replaces
that authority. Reserved historical Reviewer publications retain their original
body, authored Step and projection anchor. A missing old anchor may return
`LEGACY_STEP_BINDING_REQUIRED`; reconcile the original binding under that
operation's authority and replay its original payload, preserving the native
review ID and Step. The removed owner metadata CLI is not a recovery interface.
There is no Step-history scan, counter, registry, ledger or workflow engine.

Actions evaluates native metadata at run creation. Issue names use the Issue
number and native label projection, for example
`Auto implementation · Task 12 · step-5 · codex-ready-auto`. Unrelated Issue
labels also appear purely for display; adding, removing or reordering them
does not change launch authority. Admission binds only the ready command and
Step display metadata in the Issue label projection; new schema `4.0` execution
uses the Step resolved by Writer. PR names use the existing
synchronized bounded title, for example
`Auto remediation · PR #13 · Task 12 · Step 6 · CR purpose`; manual
names begin `Manual handoff`. Descriptive PR tails are bounded, and Task/Step
lead the title. A stale ready command blocks admission; compatibility Task/Step
projection checks remain unchanged. Neither Issue prose nor arbitrary PR/CR prose is parsed to construct
the pre-start name.
This uses GitHub's native [run-name contexts](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#run-name)
and [label projection/join expressions](https://docs.github.com/en/actions/reference/workflows-and-actions/expressions#join).

Current schema-v4 admission resolves repository starting facts from the stable
charter's effective trusted Decisions, exact refs and any applicable CR. Omitted
facts use the configured base at admission and
`<taskBranchPrefix>task-<issue-number>`; they do not select old Issue execution
fields or a historical complete Request. Exact older attempts retain the facts
and validation rules of their frozen original runtime.
The Issue template asks for an explicit closure decision. Missing or malformed
closure selects `keep-open` with an operator-visible warning.

For new schema `4.0` Issue work, independent advancement of the configured base
does not replace the immutable admitted starting commit. Admission and preflight
verify exact GitHub commit ancestry; trusted checkout and publication verify it
again against fetched base objects. A fresh task branch starts at the original
commit, excluding unrelated later main content. A diverged/replaced base,
unavailable commit or moved task ref still blocks. Issue continuation keeps its
exact task head; PR remediation keeps its exact admitted integration-base gate.
Retained schema `3.0` and legacy attempts keep their historical checks.
These base observations apply to active admission, preflight, checkout and
ordinary progress publication. Exact-attempt publication and terminal
prepublication recovery retain their original evidence and authorization gates;
recovery does not acquire an additional current-main ancestry requirement.

## Same-CR continuation after a BLOCKED result

For schema-v4 PR remediation, the native CR's reviewed head **A** remains
immutable finding provenance. A later starting head **B** can be admitted for
the same Task, PR and CR only from the preceding protected Writer publication
lineage: a terminal `BLOCKED` Outcome, verified at its canonical native target,
must attest that exact result. Automatic attempts require the journal's verified
`publishedHead`; manual attempts require the protected `manualSubmission`, its
original admission/claim digest and the canonical Writer Outcome. A worker claim,
an arbitrary current PR head or a local unpublished commit cannot establish B.

A trusted, active Task-scoped Decision newer than that Outcome must resolve the
blocker. A genuine new owner ready event then admits the next Step at B; the
Decision alone neither allocates Step nor launches work. Writer verifies the
original admission, attempt, Task/PR/CR, branch/base, source digests, configured
native Reviewer/Writer Bot identities, exact native Outcome/body bindings and
Git ancestry/ref observations. The live CR must remain current and executable
with original reviewed head A, while the live PR/ref must match proven B.
Unresolved or unknown publication in that required predecessor lineage, moved or foreign heads,
changed base/branch, stale or missing CR, altered authority/publication evidence,
replayed ready events and unsafe route/profile changes stop admission. Ordinary
replay/recovery still keeps the original attempt and cannot run inference again.

Admission verifies Draft at B through a bounded lifecycle intent keyed by the
new `runId` in `pr-lifecycle-admission-v1`. This is separate from the existing
review-ID-keyed `pr-lifecycle-v1` receipt for A; original lifecycle, journal and
Outcome records are retained unchanged. The public `begin-remediation` operation
continues to accept only the original current CR's reviewed head A. The internal
continuation intent cannot turn an arbitrary head into review authority.

For a verified SERIAL-to-managed transition with plural repositories, the
review-ID lifecycle store coexists with preserved flat `pr-lifecycle-v1` receipts.
The existing protected transition receipt and original consumer identify the
flat records' anchor repository. Every operation validates the complete retained
and configured namespace tree before using a selected receipt; foreign, corrupt,
ambiguous, colliding or unresolved original intents fail closed. New receipts
are written only under `pr-lifecycle-v1/repositories/<owner>/<repository>/`.
Equal review IDs in different repositories remain independent. Completed flat
receipts remain byte-for-byte read-only: exact current-review/authority replay
can confirm an already-Draft PR, but cannot reserve another intent or change PR
state through that receipt. Current namespaced intents retain exact binding and
lost-response reconciliation. This adapter does not relax the generic attempt
or publication namespace guard, rewrite transition provenance or original state,
or qualify an installed release. A retained unresolved intent requires its own
original-authority disposition; the adapter never adopts it into a newer CR.

PR #134 and run `38813244210` exposed the old coupling of reviewed head and
continuation starting head. The transient Ready/new-current-head-CR bridge used
under that installed protocol was a temporary workaround. It is obsolete under
this corrected, qualified protocol: a new CR solely because trusted Writer
advanced the blocked result head is unnecessary. Historical PR/CR/Writer/review
evidence remains unchanged. This source contract and its tests do not establish
installed qualification or authorize deployment; retained schema-v3 and legacy
admissions keep their original contract.

## Issue-authorized implementation continuation

Current Issue implementation uses the stable charter and trusted Decisions to
resolve scope and repository starting facts. It does not parse the former
`Implementation continuation head/branch/pull request` prose fields or select an
old complete Request. A trusted current Decision can select these starting facts
through its bounded `amendments` object, for example:

```json
{
  "branch": "codex/task-42",
  "base_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "starting_head": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "existing_pr": 43
}
```

Use the actual complete commit identities and PR, with current purpose/scope and
existing permission boundaries. `existing_pr` is `null` only when the selected
branch has no current open PR. This example is part of a trusted schema-v4
Decision, not a standalone launch command. A new Decision is unnecessary when
existing effective authority already supplies the required direction and facts.
Writer can carry forward its exact previously published head on the same branch
when no new trusted starting pin replaces it; caller JSON or arbitrary PR
movement cannot supply that provenance. See the
[authority contract](../contracts/README.md#github-native-task-authority).

Admission requires the live task-branch ref to match the resolved starting SHA.
It counts open PRs for that branch across all bases before checking compatibility:
a current PR must be unique and match the configured repository/base, canonical
Issue linkage and exact head. Step labels and bounded Task title must be compatible
with the admitted projection; conflicting future-Step or foreign-Task metadata
stops admission. Writer pins the existing PR number in the attempt record and
projects its newly admitted Step/title. Closure, disappearance or replacement
cannot authorize another target or a replacement PR.

Apply `codex-ready-auto` to the canonical Issue; `codex-ready-manual` produces the
copyable manual handoff. This keeps Issue implementation and Writer commit
identity, needs no Reviewer CR and grants no CR integration-merge permission.
Each genuinely new admitted execution receives the next Step through the current
numbering procedure. Local corrections and exact replay/recovery keep the same
admission and Step. Exact already-admitted legacy/v3 operations keep their original
facts, Request/CR bindings and Step under their frozen source; no successor Request
or owner new-phase CLI is part of the current path.

Before the first continuation push, Writer requires the remote at the admitted
starting head; after its own publication it requires `publishedHead`. It
revalidates live authority and the pinned PR, then reobserves the exact previous
Git ref before reserving the ordinary non-force push. Observed remote movement
blocks publication. Exact post-push observation and the existing uncertainty and
owner-authorized recovery rules remain in force. Ref observations and non-force
push do not provide atomic compare-and-swap against external ref changes. No new
service or state registry is introduced.

## Issue publication and worker handoff

For a migrated Task, authority parent and result surface are separate. New
schema `4.0` attempts bind the exact charter, active Decisions and applicable CR
by native body hashes, together with the protected
admission digest, attempt and Step. Already admitted schema `3.0` attempts retain
the exact native Request reference; previously admitted snapshots preserve any
original compatibility Request binding. Writer posts
the terminal typed Outcome on the unique durably known PR, or the Issue before
PR creation and for legitimate no-PR/no-change work. A pending PR creation
intent or ambiguous artifact blocks surface selection; it cannot fall back to
the Issue. No-change success requires a contained successful worker, complete
clean collection at the admitted source head and current authority; it performs
no push and creates no PR. The ordinary native `issue_comment` event on that
typed Outcome is the completion signal: automation verifies Writer identity,
authority/admission or compatibility Request, attempt and immutable result before acting. No additional label,
receipt comment, Check or parallel completion ledger is needed.

A newly generated manual handoff keeps its copyable prompt to approximately
10–15 lines: Task/Step, repository, canonical authority, exact thread and requested
profile, admitted branch and required starting head when present, and the minimal
instruction to read `AGENTS.md`, current authority and referenced accepted
governance. It directs safe checkout normalization before the head gate, stops at
a real mismatch or protected boundary, and requires one canonical Writer Outcome.
Selected Decision links, integrity digests, scope/policy prose and the full
progress-bounded policy stay outside that prompt; protected admission and native
Outcome bindings retain their exact values. Retained v3 prompts still identify
their exact selected Request. Existing reserved or published historical handoff
bytes and rendering reservations remain immutable.

A manual non-source admission may omit branch/base/head and receives the same
minimal handoff. After an owner-admitted manual session, the owner-managed OpenAI
MCP tool `submit_manual_outcome` submits only `{repository, task, run_id, result}`;
Task and run ID are positive JSON integers and `result` is the complete canonical
schema `3.0` or `4.0` Outcome. No public owner manual-result comment, second
dispatch or approval is required. The qualified mTLS Reviewer ingress invokes a
fixed nonprivileged client and a protected socket-activated Writer capability.
Writer validates the exact admitted attempt, current authority, result and unique
artifact, reserves the result digest, publishes one Writer Bot Outcome and reads
back its identity and exact bytes. The submission remains an execution claim,
not independent acceptance. It does not import Git, launch work, approve, deploy,
merge or close anything. An immutable check/run result does not invent a Git head.

The installed historical `manual-outcome` protocol with owner `authorizationId`
and a canonical `relay-manual-result` source comment remains available for
compatible schema `3.0` callers. It is no longer a required precursor to the
narrow MCP submission. Existing in-flight attempts are not rewritten.

For schema-v4 completion, valid intervening trusted Task Decisions do not
invalidate the original execution's truthful result. Writer verifies the
original source bytes, native identities and immutable admission, resolves
current trusted Task authority separately, and records the difference in the
same Outcome for independent review. It never rewrites the admission or claims
that the executor satisfied requirements added later. This applies to manual
and automatic completion, including a blocked result when a later action is
no longer authorized.

A historical schema-v4 Issue-parent manual Outcome stays on its original Issue
when a later immutable admission owns the current PR on the same Task branch.
Writer checks the original attempt's PR bindings and publication effects without
adopting the sibling PR or changing its ref, metadata or readiness. An original
PR target, unresolved original effect or ambiguous PR ownership still blocks
Issue publication; only the exact original Issue Outcome POST may be recovered.
The late report remains attributable to its original admission and Step and
grants no acceptance of the current head.

Reporting a result grants no new operation permission. Source publication and
other execution actions remain bounded by both admitted and current protected
authority; uncertain or revoked permission stops the action while preserving
useful progress and allowing truthful result reporting. Independent exact-head
PR review or no-PR Task Approval evaluates the delivered result against current
requirements. Missing amended work needs normal remediation, and material Task changes
authority after approval requires fresh acceptance before merge or closure.
Native source tampering, changed charter/CR/compatibility identity, attempt or
PR/head mismatches and duplicate delivery still fail closed. Retained schema-v3
Requests and attempts keep their strict historical currentness and bindings;
neither ordinary recovery nor new source code rebinds them.

A schema-v4 manual result explicitly names its target PR in `result.parent`.
Writer checks the authenticated capability and protected admission, repository,
admitted branch, configured base, single Task link (for example `Related to #N`)
and exact Git result head. An existing-PR admission also fixes the PR number.
No PR-body admission digest or PR-author identity is required. Explicit target
publication reads that PR and its trusted authority records; unrelated open or
historical PRs on the same branch do not disqualify it. This is publication of
an execution claim, not a new admission or a judgment of work quality.

Wrong target, repository, Task link, branch, base or head returns respectively
`MANUAL_PR_TARGET_MISMATCH`, `MANUAL_PR_REPOSITORY_MISMATCH`,
`MANUAL_PR_TASK_MISMATCH`, `MANUAL_PR_BRANCH_MISMATCH`, `MANUAL_PR_BASE_MISMATCH`
or `MANUAL_PR_HEAD_MISMATCH` before freezing a new claim. Correct an unreserved
input and resubmit in the same attempt. After reservation the exact claim stays
immutable; duplicate delivery recovers the original Outcome or reports the
specific conflicting/uncertain effect. Relevant unresolved sibling effects
remain protected. Historical reporting does not mutate successor lifecycle.

Writer publishes and reads back one Bot Outcome before making the same exact
open PR Ready; BLOCKED keeps Draft and a disposed PR is never reopened.
Authority, head and target are rechecked at lifecycle boundaries. Source CI and
Writer publication do not establish independent exact-head acceptance or a
deployed capability. Implicit automatic PR discovery/recovery still reconciles
its own creation intents and native provenance; it is not a caller-selected
manual target.

Historical schema-v3 result artifacts retain their original `Execution request
native ID` and `Execution request digest` markers and Task relationship. The digest
covers the complete original native Request comment, including its provenance.
Exact old result discovery/acceptance and frozen-runtime recovery keep those
bindings without rewriting the artifact or publishing a fresh old Request.
Current manual results use the explicit schema-v4 target/admission binding above.

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

The root-only `relay-admission` helper controls automatic
Issue and CR admission. Its durable gate is
`paths.claimRoot/admission-v1.json`, outside runner and worker write access.
The gate and Writer share `publication-v2.lock`. New automatic admission checks
the gate and reserves `controllerLifecycle` in the existing Writer attempt
record under that same lock, before consuming the ready label. Quiesce closes
the gate under the lock, so it cannot race an admitted execution reservation.
A refused automatic launch reports `ADMISSION_QUIESCED`, starts no worker and
does not claim a terminal Outcome. Manual handoff and publication-only recovery
retain their existing authority and remain available.

Physical slot occupancy is separate from the complete controller lifecycle.
A manual handoff alone does not occupy an automatic slot. A matching retained
journal can release a slot once the returned child is verified reaped (or
verified not started with containment unnecessary) and complete collection has
durably recorded `collection.preserved: true`, an exact head and a known
clean/dirty observation. Collection writes that receipt before Writer publication;
all work remains in the original per-attempt checkout. Unknown children or
incomplete preservation hold the affected slot. Existing strong terminal
receipts remain valid without adding fields to historical records. An unrelated
known slot is excluded before its journal is read; unresolvable shared resource
or migration ownership still fails closed with the conflicting identity.
Pending publication retains its exact ref/PR/operation guard and original
read-back recovery, independently of physical slot availability.

The lifecycle reservation covers the complete controller invocation: checkout,
Codex execution and containment, collection, Writer publication, and durable
terminal receipts. An already admitted invocation may finish while admission
is quiesced. A model exit or an idle runner does not establish drain. The last
trusted controller operation asks root to complete this reservation; root reads
the matching runner journal itself and requires known containment, matching
terminal receipts and no unresolved publication intent. Caller JSON cannot
assert that proof. Earlier attempts without `controllerLifecycle` require the
same existing terminal journal evidence. Missing, mismatched or unknown
execution and ambiguous publication fail closed.

Drain polls bounded snapshots and releases the Writer lock between snapshots,
allowing admitted controllers to finish. Each snapshot allows
the protected retained-history inventory the remaining overall drain
deadline rather than a separate five-second subprocess limit. The one-second
lock acquisition wait remains unchanged; contention permits another observation
while the deadline remains. A slow inventory does not bypass any history checks.
Drain emits only bounded active/unknown
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

Changing the consumer digest uses the same current-effect inventory as drain.
An untouched manual handoff with structurally valid identity, no matching runner
journal and no result/publication progress does not reserve an execution or
installer resource. Its missing Outcome remains historical uncertainty; no
cancellation, execution completion, acknowledgement or replacement receipt is
created. Completed manual results retain their original v4 binding or v3
publication receipts, including earlier owner-authorization and sealed direct
formats. Old-digest records remain readable for lineage and effect checks;
fresh mutations of an old attempt under a new digest remain forbidden.

Matching runner journals, active/unknown execution, unresolved publication or
recovery, malformed receipts and conflicting identities still prevent drain or
a digest transition. A complete trusted controller lifecycle receipt proves its
own containment and terminal handoff without requiring the obsolete runner
journal again. Earlier records lacking that proof still need matching terminal
evidence. The original records remain unchanged. Historical Task-disposition adapters, native readers and acknowledgement caches
have been removed. Admission/status/transition use current effect evidence;
GitHub availability or reopening an old Task cannot block idle Apply.

A matched pre-admission refusal with no executable admission, journal, lifecycle,
result progress or native mutation intent is also idle without inventing an
Outcome. Writer reserves comment intent before POST, so absent terminal history
is distinct from an unresolved send. Existing native effects and contradictory
worker evidence retain their holds, including through the original SERIAL reader.

The root helper also exposes the read-only
`consumer-transition-preflight --desired-digest SHA256` observation. It works
independently of the current lifecycle phase and returns the current/desired
digests, operation/target, active and unknown runs, `eligible`, and separate
effect diagnostics. Valid active
automatic work may still drain; unknown work and unresolved trusted effects
make the proposed transition ineligible. This observation allocates no attempt,
changes no gate and does not replace the strict final transition check.

The Git installer authenticates the old consumer before importing that runtime.
A drifted file may be overlaid with independently proven old bytes only in a
private read-only mount view for preflight. The selected Git commit remains
the sole desired configuration. After preparation/drain, the actual canonical
consumer must be proven again; an available private old view alone cannot
authorize reopening admission.

During the short active install, a root holder can retain the existing Writer
mutex. Its private receipt is checked against the actual kernel flock, process
birth, descriptor/inode, operation and frozen target before the bounded admission
prefix or publisher reuses it. It creates no native admission or replacement
publication authority. Before any active effect, a failed final proof can
restore the exact original open gate only while the complete old-availability
proof remains valid. Attempt/history records are preserved. Post-mutation
failures retain their original forward-recovery boundary; see the
[installation preparation contract](../docs/git-managed-installation.md#preparation-before-cutover).

During `applying`, the trusted backend records its original Reviewer,
production-runner and general-runner activity/enablement intent through
`snapshot --operation UUID` with bounded JSON on stdin. Additional runner
intents use exactly `slot-<slot-id>` keys;
`primary` retains the `general` key. Snapshot keys must match the immutable
consumer topology bound by the existing digest, including all configured slots.
The previous three-component format and optional `manualOutcome` key remain
valid when no additional slots are configured. The gate stores the
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

Immediately after its verified non-force progress push, Writer tolerates PR
list/detail head propagation only between that exact predecessor and published
candidate, for the already bound PR. Branch, repository, base, linkage and
Step/title checks remain unchanged. Other reads retain strict observation
agreement, and successful Outcome/Ready handoff still requires the exact
published head. A stale PR read never authorizes another push or a new head.

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
this path, for automatic and manual remediation. A verified
[same-CR BLOCKED continuation](#same-cr-continuation-after-a-blocked-result)
instead binds the Draft transition to its protected admission and Writer-proven
starting head. The original review action remains bound to the
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

Manual results use the narrow `submit_manual_outcome` Writer capability or the
retained schema `3.0` owner-authorized `manual-outcome` protocol.
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
In a parallel projection, `execution_slot` selects the original slot recorded
by the Outcome or protected `inspect` result; historical unbound attempts use
`primary`. The projected choice list and unique repository/namespace/slot runner
label target the correct runner, and the fixed guard verifies slot, runner name
and UID. A mismatched ordinary recovery stops before accessing its private
journal. Inspection can return the original slot from any qualified slot;
root-owned prepublication recovery retains its separately authorized original
journal access. Ordinary recovery takes the same per-run journal lock as the
controller, so an overlapping replay/recovery cannot alter its retained receipt.

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

## Terminal prepublication recovery

The separate opt-in `inspect-prepublication` / `recover-prepublication` operations
cover only a native Issue Task attempt with a terminal BLOCKED collector failure
at `progress`, no collection/progress receipt, no publication intent or published
head, and no original PR. Ordinary replay and the existing `inspect` / `recover`
publication recovery behavior are unchanged. This is neither a generic terminal
salvage operation nor permission to rerun a worker.

Use the same accepted installed `relay-publication-recovery.mjs` entrypoint and
consumer-owned recovery workflow. Supply the original `run_id`, `attempt_id` and
exact `candidate_head`; select `inspect-prepublication`. The read-only inspection
returns the exact authorization body after checking the protected original
journal, live authority, completed original owner run and native Writer BLOCKED
Outcome. Post that body as a new unedited owner comment on the original Issue.
Schema-v4 inspection verifies the exact protected native body digest. New terminal
Outcomes retain it directly; older four-field Outcomes use only the original
`commentBodies.outcome` seal bound to that Issue. Missing or changed proof stops
inspection; the historical Outcome and journal are never backfilled.
Then select `recover-prepublication` with the same candidate and the new
`authorization_id`. The direct entrypoint's bounded stdin forms are:

```json
{"operation":"inspect-prepublication","runId":123,"attemptId":"run-123","head":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}
```

```json
{"operation":"recover-prepublication","runId":123,"attemptId":"run-123","head":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","authorizationId":456}
```

These synthetic values do not authorize an incident recovery. Additional paths,
bundles, executables or credential selections are rejected. The generated native
comment binds the original Task/Step, admission/native source references and authority digest,
run/attempt, branch and fixed remote, starting/previous/candidate heads,
configuration digest, Writer Git identity and native Bot ID, full protected
journal digest, original controller receipt digest and original BLOCKED Outcome
ID/body digest/timestamps. It must postdate both the latest original run
completion and that Outcome. The Writer verifies the owner's native User ID;
labels, lookalike comments, prewritten approvals and copied SHAs grant no recovery.
The native run must still be its originally admitted first attempt; a later
Actions rerun is changed evidence and is refused.

The fixed root helper verifies successful returned execution, `started` child
and `reaped` containment before reading the configured exact attempt. It reads
bounded retained regular Git object bytes and worktree state through the trusted
collector, using its own credential only for remote observations. It imports
objects into an isolated trusted repository and applies the ordinary first-parent,
identity, safe path/mode and every introduced/transient blob secret gates. The
candidate must exactly match authorization. Complete clean observation is
required here: unreadable bytes, concurrent changes, missing objects and
non-ignored residue all stop before publication. Nothing repairs permissions,
commits residue, cleans evidence or runs Git against worker metadata.

One new `prepublicationRecovery` intent is reserved in the original bounded
Writer record under `publication-v2.lock` before any publication or PR/Outcome
side effect. Authority, original journal/Outcome, authorization and the exact
previous remote ref are checked again before reservation. Writer performs one
ordinary non-force push and immediately observes the exact remote candidate.
The reservation consumes authorization even if a process crashes or receipt
storage is ambiguous. An unfinished/uncertain reservation never pushes again,
even with another comment; inspect its preserved intent/remote and obtain a
separately admitted disposition. There is no generic retry queue.

A verified publication receipt can resume native PR/Outcome/Ready reconciliation
without recollection or another push. The original protected admission and attempt bind
the PR, and a distinct typed successor Outcome on that PR links the original
BLOCKED Outcome. Both native publications must have the bound Writer Bot ID.
The historic Issue Outcome, runner journal, collection failure,
publication fields and controller receipt remain unchanged. New independently
verified handoff evidence permits Ready; the old completed BLOCKED receipt alone
does not. Drain treats pending/uncertain recovery as unknown. Completed replay
returns its durable receipt after original evidence/authority revalidation.
Independent exact-head review and checks remain mandatory; no merge, deployment,
release, Task retry or Issue closure follows automatically.

### Collector identity and separate host qualification

Automatic routing requests `collect-progress` through the existing fixed root
Writer. Writer reads the exact admitted runner journal and requires returned,
contained execution, matching admission and no terminal result before reading
the checkout derived from that admission. An existing publication intent permits
read-only recollection; publication still reconciles it without another push. Caller
paths, identity overrides and containment assertions are rejected. This reuses
the bounded retained-source collector rather than adding a privileged command
or modifying worker permissions. The runner receives a bounded bundle and
observation; ordinary publication still validates every introduced blob.
The observer copies non-ignored regular bytes into its own temporary snapshot
and only runs trusted Git there. Ignore syntax and attributes use that snapshot,
never worker config, hooks, index or filters. Ignored artifacts remain excluded;
an incomplete read still fails rather than claiming a clean/dirty result.
Linux acquisition pins directories and regular reads without following worker
symlinks; source permissions and ownership are unchanged. Snapshot traversal
and object import have explicit byte/entry/depth bounds. Paths in diagnostics
remain bounded and sanitized, not raw protected evidence for publication.

For worker UID 983 and collector UID 985 sharing GID 979, a worker-owned 0640 file
is readable through group access; 0600 is not. Git mode 100644 says nothing about
filesystem readability. This source adds no chmod/chown/ACL or world-readable
shortcut. Both automatic collection and explicitly authorized retained recovery
use the existing fixed root Writer as a bounded read-only observer, so it can
read 0600 files, 0700 directories and ACL-restricted task source without
transferring permissions or trusting a worker observation claim. Recovery keeps
its separate authorization and historical-attempt guards.

For new source work, the shared-group umask is insufficient when a tool writes
an explicit private mode. VibeVM's `.vibe-slot.toml` is one observed example:
its Git mode `100644` can coexist with worker-owned filesystem mode `0600`.
Private filesystem mode alone does not block authorized task-source collection.
Never skip tracked/non-ignored source or broaden its access. Symlinks are
observed without dereferencing their targets, hard links and cross-device reads
are rejected, and no worker-selected path can direct Writer to host credentials.
Ignored private caches remain excluded when they contain no tracked content.

Group inheritance also has a boundary: a package tree staged outside a setgid
parent and renamed into the checkout retains its original group. Slot workers
therefore launch with their configured work group as primary through the fixed
sudo interface, so ordinary new public inodes use the collector-readable group
even outside a setgid directory. Serial installations can select top-level
`workGroup` through the deployment contract. This does not override explicit
`0600`/`0700`, imported ownership or a tool's explicit group change. Those cases
are handled by bounded Writer reads; collection never changes their metadata.

Filesystem acquisition failures retain `TRUSTED_GIT_FAILED` /
`GIT_LOCAL_FAILURE`, plus allowlisted OS `diagnosticCode` and `syscall`. The
protected diagnostic preview distinguishes source reads, source directories,
Git-object acquisition and trusted snapshot writes, with the collector's
effective UID/GID. It contains no worker path or raw error message. The terminal
Outcome shows the operation, syscall and OS code; a collector error is never
presented as a Codex launcher observation. Snapshot write failures do not claim
that checkout reads failed. Missing historical detail stays unknown rather than
being reconstructed as a new fact about the original execution.

Local unprivileged checks do not qualify that protected access on an installed
consumer. Before incident use, separately admit exact accepted source installation
and disposable Linux qualification of the fixed wrapper/root lock, actual
983/985/979 separation, descriptor confinement, unavailable reads, successful
process containment, credential isolation and unchanged evidence permissions.
Qualification must also establish preservation and integrity of the original
retained attempt; historical inode continuity is not claimed by the source
journal. If safe access requires a live-host permission/helper change, stop for
that separate owner admission. This source Step does not inspect, alter or
publish the Task 97 retained candidate or mutate its original authority.

After a worktree acquisition failure, the protected preview also retains the
already imported `observed-head-unaccepted` and bounded numeric source facts
(UID/GID, mode, device/inode, tracked category and SHA-256 of the relative path).
The fingerprint lets an authorized host investigator locate the object without
publishing its path or contents. This is a diagnostic lead, not a clean-tree,
candidate-validation or recovery authorization. Public Outcome projections keep
excluding the preview. Original historical records are never backfilled.

For a durable successful manual Outcome, and automatic `complete-handoff`,
readiness revalidates authentic authority and exact artifact pins independently
of amended scope, validation and approval constraints. Such amendments still
govern source publication and independent acceptance. A Deliberative approval
hold therefore does not prevent preparing the already published result for
review. Changed starting pins, wrong target/head, sibling publication, altered
authority sources and superseded Steps retain their existing stops. BLOCKED
results remain Draft; replay retains the same Outcome bytes and result.
Manual Issue-based continuation also verifies the existing exact PR/head is
Draft before publishing its executable handoff. It cannot rely on worker
preflight, which the manual route does not run. Completed and superseded
attempts do not redraft a newer result on handoff replay.

## Runtime diagnostic retention

Primary diagnostic writes and oldest-record eviction share a short Linux kernel
lock for their configured store, including independent processes. The bounded
thirty-second acquisition wait covers persistence only; no model call runs under
this lock. Unique exclusive temporary filenames preserve complete records during
interleaving writes. Slots and separately configured repository installations
use their own diagnostic roots. A lock/store failure remains visible through the
independent fallback capsule and does not authorize another inference.

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
Normal primary bundles separately retain bounded, redacted top-level native
JSONL error observations as described in the [runtime contract](../runtime/README.md#durable-diagnostics-and-sandbox-finalization).
They are not exposed by the public projection or qualification snapshot and
do not reinterpret the observed child exit or establish a causal attribution.
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
