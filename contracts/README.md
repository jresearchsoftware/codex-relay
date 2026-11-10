# Task and Change Request authority

Start with the [Task workflow guide](../docs/task-workflow.md) for the human
path and [typed examples](../examples/task-authority.md) for current v4 and
retained v3 records.
[GitHub-native Task authority](#github-native-task-authority) governs explicitly
migrated Tasks. The CR2 and owner metadata procedures below describe supported
legacy compatibility for older qualified installations and historical/already
admitted attempts; they do not provide a fresh execution path on a qualified
v4 installation or a second execution path for a migrated Task.

Native Reviewer identity/head selection and common attempt orchestration live in
`../controller/src`. This directory owns shared Task/Decision/CR validation,
execution metadata and the repository secret scanner. Native review content
is authority; incidental Markdown and thread-title
dash style do not define a security boundary. Execution state and Outcome publication belong to the controller. Run `npm test`.

Legacy executable `REQUEST_CHANGES` records used contract `2.0`, rendered by
Reviewer from structured `change_request` input into a native review and its
`reviewer-executable-cr` block. Their [bounded definition](../reviewer/src/executable-cr-v2.json)
and immutable fixtures remain owned by the Rust Reviewer for exact reserved
publication recovery and already admitted result acceptance. The current Node
controller has no CR2/YAML parser or fresh legacy execution path. Recover an
original old attempt through its retained original runtime and bindings; do not
convert it into a new admission.

Fresh native reviews and admissions use the schema-v4 contract below. Model,
effort and Subagents defaults come from [AGENTS.md](../AGENTS.md#work-within-the-admitted-goal),
and explicit trusted overrides stay bound to the admission snapshot. A requested
validation identifier records a required check, not evidence that it ran.

Validation names are bounded identifiers, not proof that a check ran or that
this repository supplies a consumer's deployment checks:

| Contract name | Validation owner/surface |
| --- | --- |
| `routing-tests`, `diagnostics-tests` | `controller/` suites |
| `issue-writer-tests` | `runtime/` suite |
| `remediation-tests` | `contracts/` suite |
| `rust-reviewer-tests-format`, `rust-format` | `reviewer/` Cargo tests/format |
| `diff-check`, `secret-scan` | Git diff check and tracked credential scan |
| `dispatcher-worker-integration`, `workflow-static`, `ansible-tests`, `github-test-validate` | Consumer-supplied installed-runtime, workflow, deployment or native CI checks |

These historical names remain accepted. The optional deployment-owned
`validationNames` array adds up to 32 unique IDs matching
`[a-z][a-z0-9-]{0,63}` in both Node and Reviewer config. The tool advertises their
union with the table above; each CR still requests 1–12 unique names. Unknown or
undeclared IDs are rejected by both sides. No ID is interpreted as a shell command;
consumer validation code owns its meaning. See the
[integration contract](../docs/integration-reference.md#consumer-validation-identifiers).

The historical `2.0` representation and byte-for-byte fixtures remain unchanged.
The schema is shared historical evidence even though its physical JSON file
lives under `reviewer/src/` for Rust compilation. Current Node admission validates
schema-v4 snapshots and does not round-trip old executable CRs. Consumer native
exact-head CI and installed-runtime qualification remain separate evidence.

## Owner Step metadata procedure

Steps describe progress toward the Task's authorized goal; completing a Step
does not complete the Task. One Codex thread may span successive Steps. The
current v4 Writer allocates a new Step at execution admission from canonical
Issue position and successful prior admissions. Labels and bounded titles
project that admitted identity. Decisions, CR publication and metadata-only
changes allocate no Step. See the [current Step contract](#github-native-task-authority)
and [manual result PR procedure](../packages/codex-relay/skill/references/workflow.md#manual-result-pr-step-labels).

Historical legacy and schema-v3 attempts retain their original Issue/Request/CR,
Step, branch, head and native publication bindings. Their original qualified
runtime owns exact replay or recovery. Approval, a label repair or recovery of
that same operation never increments its Step or authorizes another execution.
The former Node owner metadata helpers and their `prepare`, `advance-phase`,
`keep-step` and `recover-legacy-review` CLI operations are retired from the
current product; they are not a migration or fresh-work interface.

### Legacy publication migration recovery

An uncertain original Reviewer publication resumes its existing reserved native
operation with the original payload and read-back checks. A missing historical
binding, changed reviewed head, malformed labels or ambiguous native effect
requires owner reconciliation within that operation's authority. Do not invent
a replacement review, attempt or metadata journal to recover it. A historical
SQLite publication without its original Step/title anchor may resume only when
the exact labels and canonical title are already synchronized and its authority
hashes still match. Otherwise `LEGACY_STEP_BINDING_REQUIRED` preserves the review
for explicitly authorized reconciliation of that original binding. Replay then
keeps the original native review ID, payload and Step; it grants no new review or
execution. This is native Reviewer publication recovery, not the retired owner
metadata CLI or a fresh legacy admission route.

Task producers preserve exactly one explicit `Issue closure policy` field in
the canonical Issue: `keep-open`, or `close-authorized` with owner authority.
Missing, malformed or conflicting closure metadata selects `keep-open` with a
visible warning. Step completion, approval and CR outcome tokens do not authorize
closure. Apply the [closure authoring guidance](#closure-policy-authoring) to
trusted v4 Decisions. Implementation branch, commit and PR flow remains governed
by [the Git handoff policy](../AGENTS.md#canonical-checkout-and-safe-git-handoff).

## GitHub-native Task authority

A Task explicitly opts into `github-native-v1` with exactly one canonical
`Authority model: github-native-v1` line in its Issue body. Missing that line
preserves the legacy Issue/CR authority model for historical reads and retained
attempts, including native CR `1.0` and `2.0`; it cannot initiate fresh work on a
qualified v4 installation. Typed comments alone never migrate a Task. An unknown,
malformed or multiple marker fails closed. Migration is an owner decision, not a publisher
or controller heuristic. The two models are never combined for execution.

### Streamlined schema 4.0 admissions

The qualified `relay-workflows-v4` controller/Writer pair resolves new native
admissions from the unchanged `github-native-v1` charter and trusted Task
Decisions. Schema version `4.0` explicitly distinguishes this path from retained
schema-v3 records; it requires no new charter marker or public Task Request.
An owner-authorized ready label supplies the native launch command and route.
Decisions can accumulate in backlog without assigning a Step. Writer assigns a
Step only when it durably admits a new execution under the existing lock.
Replay/recovery of that attempt retains its snapshot and Step; a genuinely new
execution after `BLOCKED` receives the next Step.

The qualified v4 pair rejects fresh unmarked Task admission with
`CURRENT_PROTOCOL_REQUIRED`. New work on an older Task requires current native
charter authority or explicitly owner-authorized migration; typed comments, Step
metadata and a ready label cannot migrate it. A current decisive remediation CR
must be schema v4. Fresh durable Decision/CR publication also uses v4; exact
reserved old publication recovery and old admitted-result acceptance retain their
original contract. Exact schema-v3/legacy execution completion and Outcome recovery
use the frozen original source, preserving bodies, source bindings and Step.
They cannot create another execution or qualify a component upgrade.

The shared [schema-v4 definition](src/github-authority-v4.json) has public
`decision`, `change-request`, `outcome`, `task-approval` and `task-review` records,
plus the internal `admission_schema`. Historical v3 Requests/CRs are opaque to
current Node admission: it selects no old Request, inherits no old execution
fields and imposes no new Decision requirement merely because that history exists.
Original old attempts retain their selector and exact replay/publication rules
through original source; native Reviewer keeps bounded old result acceptance.

A trusted historical schema-v3 Decision can remain a provenance reference. Exact
admitted v4 result handling verifies the original selected native identity and body
hash. Fresh admission is permitted when later active v4 Decisions already replace
every effective historical amendment field, without another Decision or formal
supersession. Still-effective unhandled v3 semantics stop with
`CURRENT_PROTOCOL_REQUIRED`; they are not silently dropped or used as a fresh
old-schema execution model. Retained snapshots keep original exact source
references and Step. A public complete Request is unnecessary. A qualified paired
upgrade remains required; standalone or partially upgraded components supply no
admission authority.

Trusted non-superseded Decisions are applied in ascending native comment-ID
order. Independent scoped amendments accumulate; an explicit `supersedes`
reference replaces the entire earlier Decision in its same scope. Missing or
edited predecessors, forks and invalid native identities fail closed. Ordinary
comments remain evidence. PR-scoped Decisions apply only to that exact Task
artifact. A Task-scoped Decision may explicitly change effective closure policy
in either direction without editing the original charter; a PR-scoped Decision
or native CR cannot change Task-wide closure policy.

Schema-v4 CRs remain independent native `CHANGES_REQUESTED` reviews bound to an
exact PR/head, branch/base and actionable findings. They have no preallocated
Step, superseding Task Request or mandatory complete profile copy. Each requested
profile field resolves from applicable CR overrides, trusted Decision amendments,
current project defaults, then supported system defaults. CR boundaries are
additive protection and do not enlarge charter scope. Requested profile values
do not prove actual runtime model or effort.

The CR's reviewed head A is immutable finding provenance, distinct from a later
remediation admission's starting head B. After a terminal `BLOCKED` result, a
trusted Task-scoped Decision newer than the canonical Writer Outcome may resolve
the blocker and permit a fresh owner ready event to admit the next Step on the
same PR and CR at exactly Writer-proven B. The preceding protected journal and
authentic native Writer Outcome must bind the same Task/PR/CR, branch/base and
attempt lineage. Automatic evidence includes verified `publishedHead`; manual
evidence includes protected `manualSubmission` and its original admission/claim
digest. Current refs/ancestry, native Bot identity, source/body digests and prior
terminal publication must verify. Arbitrary or unpublished movement cannot
replace the starting head, and unresolved prior attempts, stale CRs, replayed
events or unsafe route/profile changes cannot admit new work. A new CR merely
because Writer published B is unnecessary. Original authority, reviewed A and
old journal/Outcome bytes remain unchanged; retained schema-v3/legacy rules are
unaffected. See the [controller continuation contract](../controller/README.md#same-cr-continuation-after-a-blocked-result).

`resolveTaskAuthority(records, binding)` returns resolved semantic fields,
selected contextual evidence, active Decisions and a native authority source
binding. It requires the exact trusted-API Issue-body identity and separately
verified publisher Bot identity. The binding is
`{charter, decisions, change_request, compatibility_request, sha256}`; absent CR
or compatibility Request references are `null`. Its `sha256` is SHA-256 of UTF-8
`canonicalAuthorityJson({charter, decisions, change_request, compatibility_request})`.
Fresh v4 admission resolves without a compatibility Request; that field remains
in the shared binding for historical snapshots and exact-attempt verification.
Completion, result acceptance and owner continuation preserve that immutable
selection: a `null` compatibility binding remains `null` despite historical v3
Requests, while a retained reference keeps its exact original source/currentness
checks. Later verification must not silently reselect an old Request for a new
v4 result or discard a reference from an older admitted snapshot.
Each native reference hashes the complete original source body. Project-default
and exact starting-state resolution is captured in the protected snapshot, while
this source digest binds public authority independently of the result.

`createAdmissionSnapshot(resolved, {step, route, attempt, runId, lineage, ...})`
materializes the complete internal `kind: admission` snapshot. Writer may supply
exact current starting-state observations within the admitted charter and its
own verified publication lineage; these are trusted Writer inputs, not worker
or arbitrary caller overrides. The snapshot binds resolved profile, scope,
boundaries, validation, route, exact branch/PR/head/base, source references,
run/attempt and lineage. A charter-only snapshot may omit duplicate scope and
boundary arrays: the complete charter stays visible in the worker input and is
bound by its exact native hash. `validateAdmissionSnapshot` validates the internal
shape and binding; `admissionBinding(snapshot)` returns `{attempt, step, sha256}`
with the digest of the complete canonical snapshot. Only protected Writer
reservation/persistence makes that snapshot an admitted execution.

Schema-v4 Outcomes and Task acceptance records bind both `authority` and
`admission`, plus exact immutable results and native Outcome identity. They do
not require a public Request. `resolveOutcomeAuthority` retains the originating
exact CR as acceptance provenance after `APPROVE` or disposal of an artifact,
verifies the original charter/Decision source integrity, resolves current
trusted Task Decisions separately and rejects a newer applicable CR or changed
charter/compatibility source. Its result cannot create a new admission.
An Outcome keeps its admitted `authority` and `admission`. If valid later
Decisions change the source binding, Writer adds `authority_drift` with
`current_authority`, sorted `changed_fields` and `review_required`. The latter
signals a semantic difference or an explicitly reported comparison gap; a
provenance-only replacement can leave no changed fields. Optional bounded
`authority_resolution` is captured inside new immutable admission snapshots
and preserves nonsecret original resolution inputs, including consumer
profile/validation defaults and starting state. Writer exports that captured
value without changing the admission or retrofitting older snapshots. A
reviewer can therefore distinguish a real amendment from an explicit restatement
of nonstandard admitted defaults. Historical Outcomes without this evidence
expose sorted `comparison_gaps` for changed fields whose original defaults are
unknown, rather than inventing them. Visible Markdown exposes both digests,
known changed fields, comparison gaps and the review signal.
This report is not a claim that amended work was performed or permission to
exercise newly granted protected operations.

Task acceptance binds the current authority while preserving the exact
Outcome/admission and immutable result. The reviewer explicitly evaluates
admitted versus current requirements: missing work needs remediation, unused
expanded permission alone does not invalidate the work. An original admission
cannot supply revoked action permission. A material later authority change
invalidates acceptance for merge/closure continuation; original native source
tampering and changed result/identity bindings still fail closed.
No-PR Task Approval preserves every material Outcome warning and limitation;
implementation PR acceptance remains the native exact-head PR review.

Owner continuation uses effective Decision closure policy and verified canonical
Task completion/remaining-work/hold/protected-boundary facts. Schema-v4
continuation has only `hold` and an optional trusted next-direction reference;
it has no competing `task_complete` or future Step field. A completed `keep-open`
Task with no actual remaining condition requires owner disposition. An already
authorized next execution uses the existing owner ports without publishing a
new Request or allocating its Step before Writer admission. Reviewer acceptance
does not itself merge or close the Task.

### Retained schema 3.0 Requests and attempts

The following Request-specific rules describe historical schema-v3 publication
and already-admitted attempts. They remain operative for that compatibility
path, rather than becoming prerequisites or an alternative fresh execution path
for a qualified schema-v4 installation. The migration and new-Request authoring
steps below describe the retained v3 installation contract, not the current v4
launch path.

Migration uses the paired deployed Reviewer/controller with workflow contract
`relay-workflows-v2`. Existing Reviewer configurations default the new
`githubNativeAuthorityEnabled` capability to false; typed publication is
rejected before GitHub access until a qualified paired installation enables
it. The managed release enables it alongside the same source-revision Writer
and controller. The installed workflow guard rejects a mismatching runtime
contract; publish/review the generated v2 projections before activating typed
Tasks. Never migrate a charter while an old admitted execution is in flight.
Finish it under the old model or drain it, deploy/qualify the pair, publish a
complete first typed Request and verify projections before the next ready event.
Historical Issues, comments, reviews and CR2 bytes remain untouched. Current
legacy Reviewer CR publication refuses migrated charters instead of creating
another authority path; native PR approval remains available. Mixed standalone
component upgrades are unsupported for migrated Tasks.

For an opted-in Task, the Issue is the stable charter: problem, goal, scope,
protected boundaries and its explicit closure policy. One current complete
trusted Task Request or native Change Request is the executable snapshot.
Normal new work is a Task Request; PR-specific defects use a Change Request.
Task-scoped Decisions record substantive charter amendments, and each accepted amendment
used for execution is normalized into the snapshot's semantic fields and
identified by its native source reference. Publishing a Decision alone neither
launches execution nor silently rewrites a previously selected Request.
Selected discussion, previous Outcomes and review findings remain evidence.
They cannot supply omitted executable fields or grant implicit scope.

The retained [definition](src/github-authority-v1.json) is included by Rust
for exact old record validation; original runtime source owns old admitted
execution. Current Node treats old records as opaque historical evidence, apart
from an exact selected v3 Decision needed to read or recover an admitted v4
authority source. A later trusted v4 Decision may already replace every effective
historical field; that existing evidence permits fresh admission without another
Decision or formal supersession. Still-effective unhandled v3 semantics stop with
`CURRENT_PROTOCOL_REQUIRED`. These historical records use schema version `3.0` and one canonical
`relay-authority` JSON fence. The representation rejects unknown properties,
unsupported versions, duplicate JSON keys, multiple execution blocks and
legacy/new mixtures. Strings use bounded UTF-8 bytes and single-line NFC text.
The schema accepts bounded model and effort identifiers without replacing the
backend's capability truth. A complete Request contains resolved effort and
Subagents permission; no additional model or execution mode is inferred.

The typed records have these separate roles:

| Kind | Native surface and meaning |
| --- | --- |
| `decision` | Trusted Reviewer Task Issue or Task-linked PR comment with explicit scoped semantic amendments; no executable route or Step |
| `task-request` | Trusted Reviewer Issue comment with complete Task/Step, route, profile, scope, boundaries, validation, starting-state and selected-reference snapshot |
| `change-request` | Trusted Reviewer native `CHANGES_REQUESTED` review with the same complete snapshot plus exact reviewed head and stable findings |
| `outcome` | Trusted Writer Issue or durably bound PR comment with exact Request, attempt, status, immutable result identities, warnings and limitations |
| `task-approval` | Trusted Reviewer Issue comment accepting the current Task Request/Step and exact Outcome/result with explicit warning disposition |
| `task-review` | Trusted Reviewer Issue evidence comment containing reviewed Request/Step and `REQUEST_CHANGES` findings; no execution authority or route |

Every payload binds repository, canonical Task number, native parent and the
SHA-256 of the entire live Issue charter body, including its migration marker.
Native source references carry `{kind,id,parent,sha256}`. Their supported kinds
are `issue-body`, `issue-comment`, `review` and `review-comment`; the numeric ID
is GitHub's immutable native ID, not a guessed comment number. The digest covers
the exact native UTF-8 body, including publisher provenance markers. Repository
and native parent metadata must match the payload and reference. A body edit
invalidates a reference rather than becoming a new instruction implicitly.

Trusted API adapters supply native author `{login,id,type}`. Trusted authority
requires the configured publisher login, its positive immutable native user ID
and `type: Bot` together. A matching login in prose, a human using a similar
name, a different Bot ID or an untrusted copied block grants no authority.
The configured identity is resolved through trusted GitHub metadata rather
than through caller JSON. A Change Request additionally requires the current native
review state and `commit_id` to match its exact reviewed head. Superseded
historical CR predecessors may be dismissed; their exact author, body and
`commit_id` bindings remain mandatory. Writer identity
remains separate for Outcomes. Credentials and arbitrary API endpoints are
never fields in this contract.

Requests form one explicit linear native-reference supersession chain across
Task Requests and native Change Requests. Exactly one root and current terminal
record are permitted; forks, cycles, missing predecessors, duplicate native
records and changed predecessor bytes fail closed. Supersession, rather than
comment order or the greatest historical Step, selects currentness. A Task
Request can continue at the same Step or explicitly advance by one. A new
Change Request advances by one. A correction of the same CR may retain Step
only when its CR ID, exact reviewed head and native PR parent remain the same.
An explicit new snapshot can supersede a prior snapshot bound to an older
charter; only the selected current snapshot must match the current charter.

A Task Request always belongs to the canonical Issue, independent of an
optional result PR. Its branch, base and starting head are all present for
repository execution; all three may be null for a manual non-repository Task.
An automatic Request or Change Request requires all three. A Change Request
must have a PR, a predecessor and exact findings/head bindings. Branch and PR
native binding, execution reservation, retries, publication recovery and Step
projection remain the owning controller/publisher's responsibility.

Selected context is bounded and explicitly referenced. Node resolves only
those sources, checks their native IDs, parents and exact body digests, and
passes their text as selected evidence alongside the complete snapshot.
The worker does not need to reconstruct authority by crawling history. Selected
Decisions must be trusted Task Issue or Task-linked PR comment records, must match the charter, and their
amended fields must equal the normalized snapshot. A selected Decision with a trusted explicit native successor is superseded
even when that successor was not selected in the snapshot. Adapters supply
all relevant trusted Decision comments on the Task Issue and applicable PR;
selected-only source reads cannot establish Decision currentness. A selected
Decision and its superseding replacement cannot both remain active in one snapshot. PR-scoped
Decisions require that exact `existing_pr` binding on the snapshot, including
Task continuation. A disposed or unrelated PR Decision remains evidence unless
an explicit Task-scoped Decision accepts its Task amendment. Publisher and
controller adapters verify the native PR belongs to the canonical Task.

For retained schema 3.0 Requests, closure stays in the charter. A Decision's closure amendment cannot independently
override that charter decision; the next Request must preserve its current effective
`Issue closure policy`; it cannot independently expand closure authority.
Missing, malformed or conflicting closure metadata remains `keep-open` with a
visible warning. Task Approval, native PR acceptance, Step completion and an
Outcome do not grant Issue closure, deployment or release authority. A verified
native exact-head PR `APPROVE` authorizes the separately governed squash-only
continuation when current head, required checks, integration and boundaries
remain safe; a Task Approval creates no PR merge authority.
Task Approval has only `verdict: APPROVE` and no merge or close field.

Results identify an applicable immutable revision, a bounded named set of
immutable native run/check/result IDs, or both. There is no required PR: manual
qualification, deployment or evidence results and no-change completion can be
accepted through the canonical Issue. Git result revisions are exact full SHAs.
An approval binds the current Request and its explicit reviewed Step, a trusted
Writer's implemented Outcome and the exact result identity object. Its Step must
equal that Request's Step; approval never advances it. Every material Outcome warning source
and impact must remain present; the reviewer records resolution, next action,
evidence gaps and limitations, and may add independently discovered warnings.
PR-surfaced Outcomes can still receive Issue-scoped Task Approval. Task-scoped
findings are durable `task-review` evidence for the next Task Request, not a
fabricated PR or executable Change Request. Independent PR acceptance remains
its existing exact-head native review operation.

[`github-authority.mjs`](src/github-authority.mjs) exposes
`authorityMode`, `stableClosurePolicy`, `validateAuthorityRecord`,
`extractAuthorityRecord`, `renderAuthorityRecord`, `nativeReference`,
`resolveRequestContext` and `selectCurrentRequest`. Independent Task Approval
validation/publication belongs to the Rust Reviewer; there is no duplicate
Node acceptance validator or post-review execution engine.
The selector consumes bounded trusted API records and a trusted binding,
returns `{request,record,reference,selectedContext,decisions,warnings}`, and
returns `null` only for a legacy charter. It throws a bounded authority error
for ambiguous or incomplete opted-in authority. Publisher idempotence and
reservation-before-mutation use the existing native operation journal; this
contract creates no authority registry or parallel Task ledger.

### Closure policy authoring

Portable charter, chronological amendment and completion semantics belong to
pinned [Task Handoff TH-002, TH-003 and TH-026](../vibevm/vibedeps/org.jresearch.ai.development-governance/7.0.1/vibevm/vibespecs/protocols/task-handoff.md).
The following authoring procedure describes Relay's
[bounded legacy closure binding](../docs/relay-guidance-ownership.md#temporary-legacy-closure-binding),
not activation of the new Shared closure runtime. Relay binds one explicit
`Issue closure policy` field to the current
v4 charter/Task-scoped trusted Decision mechanism; a native CR cannot change
Task-wide closure semantics. Preserve retained schema-v3/legacy charter,
digest and successor-Request rules for already-admitted attempts.

For every new or materially revised Task, explain concrete human-readable Task
completion and closure conditions next to that field. Distinguish development,
independent exact-result acceptance, merge, any required explicitly authorized
installed Apply/deployment, original-operation evidence and unresolved owner
choices. Source acceptance does not establish installed or operational proof.

- Choose `close-authorized` at charter creation when the owner authorizes a
  finite Task and closure upon meeting its stated conditions, even if a later
  explicitly authorized Apply is required. Keep the Issue open until all those
  conditions pass. Successful verification then permits closure through the
  existing owner continuation without a second Decision or permission request.
- Choose `keep-open` only for concrete additional work, a closure hold or an
  unresolved owner decision outside the authorized completion path. Name that
  condition and needed owner disposition. A finite required Apply alone is a
  completion gate, not a reason to demand another closure permission.
- At each new authorized Step/Decision and meaningful completion transition,
  reassess the effective policy and remaining conditions. After first admitted
  execution, amend Task-wide completion/closure semantics only through a trusted
  Task-scoped Decision. No redundant per-Step Decision is needed when unchanged.
- If the owner defers, combines or cancels a previously required deployment,
  reconcile completion conditions and closure authorization through that trusted
  Decision. Do not claim an Apply occurred. Close only when the revised accepted
  Task has no remaining work/hold and all protected boundaries are satisfied.

`close-authorized` still requires trusted completion evidence and verified
independent exact-result acceptance before the authorized owner continuation.
Approval, merge or Step completion alone supplies no closure authority. This
binding adds no `Close when:` field, parser/validator gate, daemon, ledger,
separate workflow or retrospective rewrite of historical Issues.

### Continuation after changes requested

A successful native PR `REQUEST_CHANGES` begins the next remediation ownership
cycle. Both legacy and typed publication receipts carry a bounded
`pr_lifecycle` Writer action identifying only the PR, native CR review and exact
head. For native automatic remediation, the owner's `codex-ready-auto` command on
the existing PR routes through Writer, which derives and executes that action
from the verified current native CR before admission or worker reservation. No
second manual Draft operation is required. The owner orchestration channel can
also call the
[Writer lifecycle continuation](../controller/README.md#publication-execution-handoff-and-integration-readiness)
directly after publication, before launch or manual remediation handoff.
Writer independently re-reads current executable authority and verifies Draft
for that exact target. A failed/uncertain transition stops continuation and is
recoverable for the same current CR/head. Reviewer remains the review authority
publisher; neither its receipt nor Draft state grants execution authority.
For a verified schema-v4 same-CR BLOCKED continuation, admission instead records
a bounded Draft intent for Writer-proven B under its new `runId`, separate from
the original review-ID-keyed lifecycle receipt for A. Public `begin-remediation`
still accepts only the reviewed A; the old receipt and recovery are preserved.
Ready subsequently means a durable successful Codex execution handoff, regardless
of current checks, mergeability or independent review acceptance.

### Authorized continuation after independent acceptance

The ordinary owner orchestration uses the supported GitHub connector directly.
It interprets existing canonical authority and acts within that authority; there
is no Relay post-review engine, owner merge CLI, action-port interface or local
merge journal. The independent Reviewer publishes acceptance, the owner channel
performs authorized integration, and protected Writer continues to own admitted
execution and Outcome publication/recovery. Removing a continuation helper does
not transfer owner credentials or merge authority to Reviewer, Writer or workers.

For Direct work, verified independent native exact-head `APPROVE` may be followed
by the already-authorized integration without another ceremonial merge prompt.
For Deliberative work, first provide the substantive non-approving assessment,
conduct the intended owner discussion and record the required trusted Task
Decision. Only then may the independent evaluator publish formal approval of
the still-current exact result. Acceptance of report quality alone does not
adopt its recommendation or authorize implementation, integration or deployment.

The owner uses this bounded sequence through the existing connector:

1. Verify durable publication of the original independent native approval:
   trusted Reviewer identity, decisive state, exact reviewed head, effective
   Task authority and required native acceptance evidence. Resolve
   `PUBLICATION_UNCERTAIN` through replay/readback of the **original identical
   Reviewer operation**, including its intended body/operation identity. Never
   post another review or treat an uncertain response as approval.
2. Refresh the canonical Task and trusted Decisions, result provenance, exact
   PR repository/branch/head, approval, required native checks, Draft/Ready,
   mergeability, explicit holds and protected boundaries. Dispose of material
   warnings and visible evidence gaps. An amended authority needing fresh
   acceptance, moved head, incomplete/failing required check, unknown readiness
   or hold stops integration. Ordinary base movement is acceptable only under
   the applicable exact-head/readiness policy. A required exact-base guarantee
   needs a supported atomic capability; `expected_head_sha` alone cannot provide
   it. Missing connector permissions or native evidence remain explicit gaps.
3. Verify applicable closure restrictions before merging. The currently
   supported migrated-Task closure binding still requires verified non-closing
   PR linkage (`Related to #N`) and a neutral squash title/body. Neither helper
   retirement nor Shared Governance adoption implements Task #194, changes the
   Task's closure policy, or authorizes closing it. Resolve an implicit closing
   link before integration under existing owner authority.
4. Call the connector's `merge_pull_request` with `merge_method: "squash"` and
   `expected_head_sha` equal to the full independently approved/current SHA.
   Supply a neutral explicit `commit_title` and `commit_message` where required
   by that closure binding. GitHub rejects a moved head; do not omit the guard,
   enable unattended auto-merge or substitute another merge method.
5. Read back the same native PR and merge commit. Verify merged state, the
   approved head, destination/base repository, returned merge SHA and squash
   commit before any dependent action. If the response is lost or uncertain,
   inspect authoritative GitHub PR/commit records for that original operation.
   Do not blindly repeat a merge, declare failure/success from transport status
   alone, close the Task or launch follow-up while its effect is unresolved.

For example, after those gates are satisfied, the existing connector accepts:

```json
{
  "repository_full_name": "example-org/sample-project",
  "pr_number": 25,
  "merge_method": "squash",
  "expected_head_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "commit_title": "Implement the accepted change (#25)",
  "commit_message": "Related to #23"
}
```

This is an example tool argument, not an executable permission or a stored
receipt. Existing native GitHub records supply durable integration evidence;
no owner-local merge state is created or required. If readback cannot establish
whether a prior mutation happened, report the exact missing evidence and stop
dependent progress rather than attempting a replacement operation.

An owner-created standalone source PR retains its explicit standalone Task
permission, native owner/repository/branch/head provenance and independent
source-PR acceptance. It fabricates neither admission nor Writer Outcome. A
known admitted result retains its real Writer Outcome and publication recovery;
ordinary owner commentary cannot downgrade it to standalone work. Genuine
no-PR results use exact native Task Approval of their Writer result and require
no artificial PR or merge. Missing historical receipts do not undo separately
established owner acceptance by verified merge.

Integration, Issue closure, further admission, package release and deployment
remain distinct permissions and facts. After verified integration, reassess
actual completion, remaining work and current holds under the Task's supported
closure contract. Further work uses the existing authorized admission path;
there is no automatic launch, prepared successor Request or preallocated Step
from an approval. No extra owner-choice prompt is needed for an action already
clearly authorized, and no action may infer new authority from approval alone.
