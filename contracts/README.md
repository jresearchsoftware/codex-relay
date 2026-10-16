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
post-review continuation and the repository secret scanner. Native review content
is authority; incidental Markdown and thread-title
dash style do not define a security boundary. Execution state and Outcome publication belong to the controller. Run `npm test`.

Legacy executable `REQUEST_CHANGES` uses contract `2.0`. The Reviewer caller sends
`change_request` as structured tool input; repository, PR and reviewed/starting
head come from the trusted top-level target fields. Reviewer validates the
complete input before any GitHub request and renders both the readable native
review and its `reviewer-executable-cr` JSON block. The native review is the
only Change Request authority. The caller does not author headings or YAML.

The shared [bounded definition](../reviewer/src/executable-cr-v2.json)
supplies the tool's typed schema, bounds and native validation names to Rust and
Node. It is included in both runtime source identities. Both validators support
only the keywords and formats in that checked-in definition. Text limits count
UTF-8 bytes; descriptions are single-line NFC text. Findings retain their supplied
stable IDs (a letter followed by letters, digits, `_` or `-`), up to 30 findings.
Validation is a nonempty set of supported native check names, independently of
repeated compatibility prose. Additional starting-state requirements may be
empty because the exact starting head is already bound. Effort and Subagents
may be omitted by authors. The shared schema encodes the execution defaults
from [AGENTS.md](../AGENTS.md#work-within-the-admitted-goal); Node admission and
Rust rendering use those same values. Reviewer renders resolved launch metadata;
downstream validation and worker launch preserve it, including explicit overrides.
Existing rendered reviews keep their explicit values; the historical fixture
still tests its intentional overrides. Authoring defaults affect unresolved
fields only. Use the paired Reviewer/Node revision for the new optional fields.
For legacy CRs, Step is a positive safe integer matching the current remediation
launch profile and persistent Issue/PR labels. A new CR uses current N+1; execution and CR
transport retries keep that CR's Step. History never supplies Step.
Model and effort remain bounded argument identifiers with backend capability
truth. Subagents permission is separate. There is no task path allowlist or
interactive review profile.

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

The `2.0` native representation, historical enum and byte-for-byte fixture are
preserved: configured vocabulary is an extension, not a new serialization.
Old binaries fail closed on extended config/custom IDs; deploy the paired
Reviewer/Node revision before opting in. Existing configs with no declarations
keep their behavior and consumer digest. A changed config requires attempt
reconciliation. The shared schema is a `contracts/` concern even though its
physical JSON file remains under `reviewer/src/` for Rust compilation.

Only request applicable checks. A consumer must supply its own checks and
report their results; this candidate does not include deployment roles or
pretend that local tests satisfy an installed-runtime proof.

The consumer checks the canonical JSON encoding, including duplicate keys,
version and target binding, and reads findings and validation directly from it.
Existing `1.0` YAML/native reviews remain readable through the historical parser;
the retained legacy Reviewer path publishes only `2.0` executable CRs. Current
qualified v4 publication uses typed schema-v4 native reviews; old schema-v3
reviews remain historical/in-flight inputs. Unknown versions,
multiple execution blocks and mixtures of old/new contracts fail closed.

The [semantic input fixture](test/fixtures/executable-cr-v2-input.json) and
[canonical native form](test/fixtures/executable-cr-v2.md) cover launch metadata
and native review authority admission. All identities and task numbers are synthetic. Node tests admit that form through the current routing
controller. Rust tests compare the rendered bytes, intercept the actual mock
GitHub publication and pipe it into that same consumer, and reject the shared
invalid corpus before any mock GitHub request. Run `npm test` here and
`cargo fmt --check && cargo test --locked` in `reviewer/`; Cargo tests
require Node for the cross-language checks. Consumer native exact-head CI must retain a separate installed-runtime proof
boundary; local tests do not qualify its deployment adapters.

## Owner Step metadata procedure

Steps decompose progress toward the Task's authorized goal and boundaries as
work evolves; completing a Step does not complete the Task. One Codex thread
may span successive Steps. Historical Task descriptions do not govern future
Step decomposition. See [Task identity and startup rename](../AGENTS.md#task-identity-and-startup-rename).
For legacy Tasks, the Issue body remains the current Task contract; the native
review body is the sole executable CR authority, with the canonical Issue linked
for Task identity.
Implementation branch, commit and PR flow remains Codex-owned under
[the Git handoff policy](../AGENTS.md#canonical-checkout-and-safe-git-handoff).

Owner `advance-phase` and `keep-step` procedures in this section describe the
retained legacy contract. They cannot admit fresh legacy work on a qualified v4
installation. Historical schema-v3 migrated Tasks resolve Step from their complete
trusted Request and advance through an explicit successor Request; their typed
publisher projects labels and the existing PR title. Current v4 admission instead
allocates Step in Writer. Legacy owner helpers reject migrated Tasks.
Both authority models retain same-CR publication recovery without an increment.

Task producers and updates preserve exactly one explicit `Issue closure policy`
field in the canonical Issue: `keep-open`, or `close-authorized` only with owner
authority. Approval, Step completion and CR outcome tokens do not authorize
closure. Missing, malformed or conflicting metadata selects `keep-open` with
a visible warning; record owner reconciliation in the Issue body.
`keep-open` means known work or evidence remains after implementation. Nearby
prose should explain why the Issue stays open and what outcome would make closure appropriate.
This adds no required structured field, parser gate or automatic closure rule.
For new Task Decisions and complete Task Requests, also apply the
[closure authoring guidance](#closure-policy-authoring); the canonical Issue
remains the closure authority.

### Executable CR publication and synchronization

1. For a **new** executable CR, read the current linked Issue and PR, requiring
   exactly one valid `step-N` on each, with equal N. Put N+1 in structured
   `change_request.step` and its launch thread title. Preserve exact reviewed
   head, findings, profile, validation and boundary authority. The optional owner
   `prepare` helper performs these authoring reads without mutating metadata.
2. Publish through the reserved Reviewer tool. The Reviewer validates the exact
   repository, linked Issue, PR and reviewed head before native publication.
   After verified publication, the same Reviewer operation ensures `step-(N+1)`
   exists, replaces each target's Step label while preserving unrelated labels,
   updates the bounded `Task <Issue> · Step <N+1> · <CR ID> · <CR purpose>` PR title and
   re-reads the targets. Successful `REQUEST_CHANGES` includes verified metadata
   synchronization; ordinary owner orchestration no longer performs post-CR writes.
3. A failed or uncertain review publication uses the existing duplicate/recovery
   path. Partial synchronization also resumes that **same native review ID** and
   authored Step, allowing only N or N+1, without another review or increment.
   Changed head/review/binding or malformed/multiple labels fails closed. Apply
   the ready label only after synchronization succeeds. `APPROVE` changes no Step.

The Reviewer App now needs `actions:read` for admission/active-work reads and
`issues:write` for bounded Step label synchronization, alongside existing
`metadata:read`, `pull_requests:write` and `checks:write`. Tokens remain restricted
to the configured repository. These source permissions do not approve a live
App permission update or deployment; an existing consumer requires separately
authorized permission reconciliation and upgrade. Native CR versions `1.0`
(readable) and `2.0` (published) remain unchanged.

### Explicit owner new-phase preparation

For an explicitly owner-authorized **new implementation phase** of the same Task,
including a reopened or split continuation, deterministic preparation reads the
canonical Issue's current Step N and advances precisely to N+1. An existing PR
is optional; when supplied it must link that exact Issue in the configured
repository and keep its branch, base and head binding. Preserve unrelated labels
and update only the bounded canonical Task/Issue/Step PR title. No phase is
inferred from history, prose, prior Outcomes or a largest-ever Step.

For [Issue-authorized implementation continuation](../controller/README.md#issue-authorized-implementation-continuation),
record the current goal and explicit starting head, existing branch and applicable
PR binding in the canonical Issue. An execution retry or continuation of the same
unfinished phase keeps the current Step. Only an explicitly owner-authorized new
implementation phase advances it through this procedure, including the existing
PR when one is present. This uses Issue authority without manufacturing a Reviewer
CR; metadata preparation alone grants no launch authority.

[`step-synchronization.mjs`](src/step-synchronization.mjs) verifies `/user` is the
configured human owner (`User`), rejecting Writer/Reviewer App identities. Its
bounded request accepts only the stated operation and fields:

- `{operation:"prepare",pullRequest}`: read-only N+1 authoring assistance for a new CR.
- `{operation:"advance-phase",issueNumber,currentStep,newPhaseAuthorized:true}`:
  explicit owner new-phase preparation. Optional `pullRequest` requires a
  single-line NFC `purpose` of 1–512 UTF-8 bytes; the helper constructs and bounds
  the title instead of accepting arbitrary titles or other metadata.
- `{operation:"keep-step",issueNumber,currentStep,pullRequest?}`: explicit read-only
  bypass for execution retries and continuation within the same phase. Never call
  `advance-phase` for those retries.
- `{operation:"recover-legacy-review",pullRequest,reviewId,legacyPublicationRecoveryAuthorized:true}`:
  exceptional, explicitly owner-authorized migration reconciliation only, as
  described below; it does not replace normal Reviewer post-CR synchronization.

`currentStep` binds the exact N to N+1 operation. A partial native label/title
failure can resume that same request with only N/N+1 labels; repeating it cannot
advance to N+2. Re-read verification exposes partial failures before launch.
Phase requests cannot supply labels, body changes, arbitrary metadata or review
IDs. The separate legacy recovery request accepts only the exact review ID and
explicit migration authorization, never a new CR or arbitrary metadata. The
former owner `synchronize` operation is retired; Reviewer publication is the sole normal post-CR metadata writer.

The optional Linux adapter uses the caller's ordinary owner `GITHUB_TOKEN`:

```sh
node contracts/src/step-synchronization.mjs < metadata-request.json
```

This helper grants no launch, review publication, merge, deployment or Issue-close
capability. Step labels alone never launch work. GitHub has no transaction across
an Issue and PR; serialize metadata operations and retain fail-closed admission
until labels, title and applicable authority agree.

### Legacy publication migration recovery

New Reviewer operations retain the exact Issue/PR Step binding and initial PR
title before native publication. A historical published SQLite record may lack
that binding or its initial-title field. The
Reviewer may accept such a record only when both labels and the canonical
explicit-CR-ID title are already synchronized; it never invents an old anchor
or silently mutates a newly linked Issue. Existing authority hashes must still
match when upgrading an older anchor. Otherwise it returns
`LEGACY_STEP_BINDING_REQUIRED` and preserves the original native review.

After this error, the owner can explicitly authorize the bounded
`recover-legacy-review` helper operation. It verifies the configured `/user`
human owner, exact current decisive Reviewer `CHANGES_REQUESTED` ID, repository,
PR, canonical linked Issue and unchanged reviewed head. Step comes solely from
that same executable review body. Only its N/N+1 metadata is eligible; unrelated
labels and current Task/CR authority are preserved. The helper re-reads binding,
review, labels and canonical title after updates. Repeating this migration repair
cannot author a review, infer a Step, advance again or launch work.

Then replay the **original Reviewer payload** through its existing
publication-recovery path, retaining the same native review ID and Step.
Changed authority, missing/malformed/multiple labels or ambiguous publication
needs owner reconciliation. Do not invoke this exception for current Reviewer
operations or normal post-CR synchronization; the former general `synchronize`
owner operation remains retired.

Remediation follows [progress-bounded execution](../docs/execution-policy.md)
inside the admitted worker. Contract counts and Step metadata bind authority;
they do not limit local correction iterations or authorize automatic retries.

## GitHub-native Task authority

A Task explicitly opts into `github-native-v1` with exactly one canonical
`Authority model: github-native-v1` line in its Issue body. Missing that line
preserves the legacy Issue/CR authority model for historical reads and retained
attempts, including native CR `1.0` and `2.0`; it cannot initiate fresh work on a
qualified v4 installation. Typed comments alone never migrate a Task. An unknown,
malformed or multiple marker fails closed. Migration is an owner decision, not a publisher
or controller heuristic. The two models are never combined for execution.

### Streamlined schema 4.0 admissions

The qualified `relay-workflows-v3` controller/Writer pair resolves new native
admissions from the unchanged `github-native-v1` charter and trusted Task
Decisions. Schema version `4.0` explicitly distinguishes this path from retained
schema-v3 records; it requires no new charter marker or public Task Request.
An owner-authorized ready label supplies the native launch command and route.
Decisions can accumulate in backlog without assigning a Step. Writer assigns a
Step only when it durably admits a new execution under the existing lock.
Replay/recovery of that attempt retains its snapshot and Step; a genuinely new
execution after `BLOCKED` receives the next Step.

The qualified v4 pair rejects fresh unmarked/legacy Task admission and new v3
Task Request/CR execution chains with `CURRENT_PROTOCOL_REQUIRED`. New work on
an older Task must resolve current v4 authority or stop for explicitly
owner-authorized migration; the gate cannot infer migration from typed comments,
Step metadata or a ready label. Fresh durable Decision/Request/CR publication
follows the same boundary, including new schema-v3 Decisions. Historical
parsing/verification and reserved exact-operation recovery remain available,
as do safe completion and Outcome publication for an
exact already-admitted old attempt. These operations preserve original bytes,
source bindings and Step and cannot create another execution. Result acceptance
remains available for exact old admitted attempts, including schema-v3 acceptance
records. Older qualified installations keep their reviewed contract;
this is not a general upgrade bridge
or a blanket historical support cutoff.

The shared [schema-v4 definition](src/github-authority-v4.json) has public
`decision`, `change-request`, `outcome`, `task-approval` and `task-review` records,
plus the internal `admission_schema`. Schema-v3 Task Requests and results remain
readable, and already-admitted schema-v3 attempts retain their original selector,
exact body digests and replay/publication rules. Fresh v4 admission does not
select a v3 Request as compatibility input or inherit its execution fields.
When a marked Task has v3 Request history, an active trusted Task-scoped v4
Decision newer than the latest v3 Request must explicitly amend purpose or scope
to establish current v4 direction. A closure/profile-only amendment is
insufficient. The latest applicable v3 CR also stops fresh admission; a current
v4 CR can become current while preserving historical records. This is current v4
authority selection, not automatic conversion or rewriting of old records.
Retained snapshots keep their original exact compatibility references and Step.
A public Request is not a new-work prerequisite. The qualified paired upgrade
is still required before the new contract is used; standalone or partially
upgraded components provide no
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

The shared [definition](src/github-authority-v1.json) is included by Rust and
read by Node. All records use schema version `3.0` and one canonical
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
`resolveRequestContext`, `selectCurrentRequest` and `validateTaskApproval`.
The selector consumes bounded trusted API records and a trusted binding,
returns `{request,record,reference,selectedContext,decisions,warnings}`, and
returns `null` only for a legacy charter. It throws a bounded authority error
for ambiguous or incomplete opted-in authority. Publisher idempotence and
reservation-before-mutation use the existing native operation journal; this
contract creates no authority registry or parallel Task ledger.

### Closure policy authoring

Before every new Task Decision or complete Task Request, consciously reassess
the known work or evidence expected after implementation that justifies
`keep-open`; do not carry it forward by habit. Use the stable charter, applicable
trusted Decisions and relevant current evidence within the existing authoring action.

- When work or evidence remains, retain `keep-open` and explain the concrete
  remaining condition and owner disposition in the existing charter or trusted
  Decision that supplies the effective policy.
- When that rationale no longer applies, seek explicit owner authorization, or
  apply existing explicit owner authorization. For schema 4.0, publish the
  Task-scoped trusted Decision changing effective policy to `close-authorized`;
  the stable charter needs no rewrite or complete successor Request. For retained
  schema 3.0 or legacy authority, reconcile the canonical charter and preserve
  its policy until then, using the existing digest and successor Request rules.
  A native CR cannot change Task closure policy in either model.

`close-authorized` permits closure only after Task completion, verified
independent acceptance and no remaining work through the existing authorized
continuation. Approval, merge and Step completion alone grant no closure
authority. This is prose authoring guidance: no additional structured field,
parser or validator gate, separate workflow or automation, and no blanket
rewriting of historical Issues.

### Continuation after changes requested

A successful native PR `REQUEST_CHANGES` begins the next remediation ownership
cycle. Both legacy and typed publication receipts carry a bounded
`pr_lifecycle` Writer action identifying only the PR, native CR review and exact
head. The owner orchestration channel calls the
[Writer lifecycle continuation](../controller/README.md#publication-execution-handoff-and-integration-readiness)
immediately after publication, before launch or manual remediation handoff.
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

The complete Request, authored Step and `task_complete` details below describe
the retained schema 3.0 path. Schema 4.0 uses the exact authority/admission/Outcome
binding, verified canonical completion and `{hold,next}` direction described in
[streamlined admissions](#streamlined-schema-40-admissions); its continuation
does not prepare another public Request or allocate a Step.

Retained Task Requests and Change Requests may include
`continuation: {hold,task_complete,next}`. All three fields are explicit when
present; absence means `hold: false`, `task_complete: false`, `next: null`.
`next` is null, `{task,request}` identifying an already-published exact current
Request in the same repository, or `{task,direction,step}` for bounded
after-acceptance preparation of the same Task. The direction is a selected
trusted Task Issue Decision already normalized into the complete accepted
snapshot. Its explicit Step is the same Step or precisely the next Step. Decisions may amend continuation
only when the next complete snapshot normalizes that amendment. Approval cannot
invent continuation, grant new scope, replace a Request or manufacture a PR.

The existing owner orchestration channel calls
[`continueAfterApproval`](src/post-review-continuation.mjs) immediately after a
verified independent native publication. It executes the already-authorized
operations through the owner's existing bounded native adapters; it does not
ask for another Publish/merge/continue confirmation. The Reviewer service
remains the publication actor, and the owner channel remains the merge/closure
and launch actor. The helper introduces no credentials, runtime service,
installation step, generic mutation endpoint, authority registry or new
owner input. It is never made available to the worker.

For native PR `APPROVE`, the helper re-reads the current decisive native verdict,
its trusted Bot author, the canonical Task/Request and charter, exact approved
head, live PR/Task binding, current mergeability/readiness and required check
completeness at that head. With no hold or protected boundary it performs an
exact-head squash merge, then verifies the native merged result. For migrated
Tasks, trusted native `closesTask` must be explicitly false before squash; true
or unknown blocks the merge. Typed PRs use a related reference and the helper
supplies a deterministic neutral squash title/body instead of inheriting
source closing keywords. Explicit Issue closure remains a separate action
after Task completion and closure authority. Legacy merge message/reference
behavior is preserved. Ordinary base
movement is allowed when current readiness and exact-head checks remain safe.
An explicitly required exact-base reconciliation policy is preserved; unknown
base/readiness state or changed facts after reservation stops the action.
No synthetic merge, stale-head approval or review fallback is supplied.

An implemented no-PR result follows the same path through trusted native Task
Approval and its exact Writer Outcome. Task Approval does not substitute for a
PR review or authorize merging an artifact PR. Closure occurs only under the
effective `close-authorized` policy, verified Task completion, no
remaining work and a verified native acceptance result. `keep-open` always
preserves the Issue and does not prevent a separately authorized next action.
The retained schema 3.0 path also requires its explicit `task_complete` flag.

A selected exact next Request routes to automatic launch or a manual handoff
without another owner prompt. The helper checks its own Task charter, current
native Request and protected boundaries, and rechecks it after action
reservation. The target can be another Task. Same-Task direction preparation invokes the
existing bounded `prepareNextAuthority` owner port only after acceptance and
verified merge, while the old Request is still current. It must preserve the
complete accepted purpose, scope, profile, validation and boundaries, use the
explicit target Step, supersede the accepted Request and consume continuation
to its inactive defaults. Git starting facts may be refreshed through trusted
owner preparation; material phase changes require a separately authorized
Request. PR-scoped Decision amendments require explicit equivalence in the
selected Task direction before carrying their semantics into Task scope.
Conflicting selected continuation amendments stop preparation; the helper
does not create another owner Decision to override them. It verifies the new
current native Request before launch and rechecks that exact prepared identity
after reservation. Publishing a superseding same-Task Request before merge
invalidates the accepted source and stops every action. The helper refuses
re-executing the accepted current Request as its own next action. A known
same-Task next phase keeps the Issue open.

The callable interface is:

```js
import { continueAfterApproval } from './contracts/src/post-review-continuation.mjs';
const result = await continueAfterApproval(verifiedPublicationReceipt, ownerNativePorts);
```

The publication receipt identifies repository, Task, exact native approval
reference and, for PR acceptance, reviewed head. Schema 4.0 binds exact authority
sources and execution admission; retained schema 3.0 binds the exact Request
reference and charter digest. Legacy native PR acceptance retains its existing canonical
`authority_digest` with a null typed Request reference; it does not migrate
implicitly. Required ports are `readCanonicalState`, `reserveAction` and
`recordActionResult`. The relevant bounded action ports are `mergeSquash`,
`closeIssue`, `readNextAuthority`, `prepareNextAuthority`, `launchRequest`,
schema 4.0 `launchAuthority`, and
`manualHandoff`.
`readCanonicalState` supplies trusted native records/binding, the current
native approval reference, exact PR/check facts and canonical remaining-work,
hold and protected-boundary decisions. For legacy work it supplies the existing
authority digest and accepted continuation, rather than inventing typed scope.
These facts come from the already-authorized owner channel, never worker JSON
or free-form instruction interpretation inside the helper.

Action ports use the existing caller publication-intent/native-receipt journal.
The helper reserves a deterministic operation identity before mutation,
re-reads authority after reservation, retains the native result before the next
action and reconciles already-completed actions without replay. A failed or
uncertain native approval, ambiguous existing mutation, uncertain mutation
response, missing native readback or changed authority returns a bounded
`{status:"stopped",reason,actions}` result. Known completed progress remains in
`actions`; no blind retry, fallback verdict or unrecorded scope advance occurs.
Qualification uses injected bounded native adapters to exercise actual merges,
closure and automatic/manual follow-up, including the no-PR acceptance path.
It does not claim live consumer credential, service or GitHub qualification.
