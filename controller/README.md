# Codex relay routing

Load an explicit [consumer configuration](../consumer/README.md) before execution.

The owner launches fresh Issue work or applicable PR remediation by applying
`codex-ready-auto`; `codex-ready-manual` produces the existing copyable manual
handoff. These are first-class native commands. No Actions UI, dispatch inputs,
comment command or additional launch form is required. Owner `workflow_dispatch`
on the configured base branch remains an optional fallback with `task`, `step`, `route` and optional
`pull_request`; those inputs must match current metadata and CR authority.

The canonical Issue retains exactly one `step-N` label throughout its lifetime.
Fresh work uses `step-1`; the owner explicitly chooses a reopened continuation's
positive Step. Writer copies the Issue Step to
its created PR, without incrementing or removing the Issue label. Step alone
never launches work and grants no authority. Missing, multiple, malformed or
mismatched labels block new admission. The `step` label namespace is reserved.

The trusted Writer verifies the owner actor and triggering actor, repository,
workflow path, first native run execution, native title binding, current command
event, canonical Issue and exact CR/head. Issue label events use `issues`;
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
Issue/PR labels. After successful Reviewer-native publication, ordinary owner
orchestration synchronizes both labels and the existing PR Task/Step title via
the [metadata procedure](../contracts/README.md#owner-step-metadata-procedure).
The Reviewer App owns verdict publication only. Repeating the same authorized
CR publication or metadata repair keeps its Step. Execution retries keep Step;
`APPROVE` does not increment it. New remediation must match the current CR's
required launch profile; Step display metadata never replaces that authority.
There is no Step-history scan, counter, registry, ledger or workflow engine.

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

Run `npm test` here and the affected runtime/contract suites. Consumer-owned
installed runtime/user/sudo proof requires its separate integration checks.

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
the exact clean checkout, observes the PR head, marks the PR ready and updates
the original Writer-owned blocked Outcome comment in place. A partially failed
finish can be resumed using the same successful publication receipt; it cannot
push again. A blocked/unknown original execution or dirty checkout cannot claim
readiness. Native exact-head validation, independent review, merge, deployment
and Issue closure retain their separate gates.

The durable recovery receipt preserves the trusted Git layer's sanitized push
and observation diagnostics, including classification, operation, exit/signal,
UTF-8-bounded preview, byte count and truncation flag. When both fail, the failed
push preview remains the primary recovery diagnostic and the observation failure
is retained separately; this does not assert that the remote stayed unchanged.
The helper wire and terminal JSON preserve that safe primary preview in
`diagnostic.publicationRecovery`. Raw stderr and protected diagnostics are never
copied.

Run focused regressions from the repository root with:

```sh
node --import ./consumer/test-support/consumer-env.mjs --test controller/test/publication-recovery.test.mjs
```

The complete local candidate checks are in [development guidance](../AGENTS.md).
Consumer workflows supply native exact-head and installed-runtime checks.
