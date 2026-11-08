# Task 199 architectural simplification

Authority: [Task 199](https://github.com/jresearchsoftware/codex-relay/issues/199)
and [the owner architecture Decision](https://github.com/jresearchsoftware/codex-relay/issues/199#issuecomment-6725442593).
This assessment describes source and qualification, not a second Task contract.
The canonical Writer Outcome and exact-head native checks own final revisions,
results, warnings and limitations. The admitted starting head is
`3f4d4348cfb05866b2108eadcc35b7a17153ff14`; the independently accepted baseline is
`512b2b5ea2867b92958580f17f6aee24c23b1fba`.

## Components and responsibilities

| Before | After | Operational reason |
| --- | --- | --- |
| Two unused post-review engines, owner CLI/adapter and local squash journal | Authorized owner sequence through the GitHub connector | Verify native independent approval, authority, exact head/checks/readiness/holds, send the preauthorized expected-head squash and read back GitHub. |
| Duplicate Node Task Approval validator used only by those engines | Rust Reviewer remains the native acceptance validator/publisher | Preserve independent acceptance and original publication recovery without an unused duplicate model. |
| Historical Task reader, disposition resolver, withdrawal acknowledgement/cache and diagnostic hooks | One effect inventory for status, drain and consumer transition | Old Task status does not govern idle installation. Journals, unknown workers, incomplete submissions and uncertain publication remain blockers. |
| Fresh SERIAL installation/scheduling and SERIAL-to-pool engine | One managed pool, including capacity one | Actual consumers use the pool. Retain only bounded readers needed by sealed original operations. |
| Route-specific numbering based only on Writer history | Issue numbering position reconciled with durable successful admissions | Standalone owner iterations and routed Manual/Automatic work share one sequence. Rejection allocates nothing; replay keeps its Step. |
| Manual PR labeling workaround | Shared Writer projection after exact result binding | Ordinary contributors may create PRs. Writer validates Task/branch/head, projects admitted metadata and safely repairs missing same-Step projections. |
| Prompt omits admitted base/existing artifact | Existing renderer includes branch, exact base/start and source PR, or explicit source-free form | One copyable handoff exposes the trusted starting identity. |
| Literal source URL equality | Strict GitHub repository identity at ownership checks | Equivalent SSH/HTTPS locators can produce an ordinary managed workflow proposal; foreign/ambiguous identities and byte drift remain rejected. |
| Disposable-root wrapper around the guidance builder | One builder reads the immutable standalone release closure directly | Separate active Shared 7.0.1 from standalone Shared 5.0.0 without another copied build tree. |

## State and retained dependencies

GitHub remains the Task/Decision/PR/Outcome history. Existing Writer records keep
immutable admission, consumed-event and exact publication/recovery evidence.
Runner journals retain execution/containment and preserved source. PR lifecycle
intents protect Draft/Ready effects. Reviewer SQLite retains original publication
reservations and uncertain decisive-POST recovery. Installer operation/gate state
is separate. Unfinished Step projection uses bounded evidence in the existing
admission record, removed after verification; no new ledger or synchronizer exists.

Read-only inspection found all four PROD consumers on one managed pool (desired
capacity 6, 32 supported slots) and TEST on managed capacity 2. PROD has a sealed
compatibility receipt for 105 original runs, including original manual v3/legacy
handoffs without Outcomes. Its current pool contains 65 v4 admissions and four
terminal pre-admission refusals; no v4 admission selects a compatibility Request.
TEST's four inspected admissions are also v4 without compatibility Requests.
These are dated qualification observations, not permanent configuration defaults.

The current-v4 inventory also revealed an actual historical Decision dependency:
DocReview `jresearchsoftware/docs-evolution-review`, Task 329, PR 330, pending run
`39599176190` selects schema-v3 [Decision 6309559387](https://github.com/jresearchsoftware/docs-evolution-review/issues/329#issuecomment-6309559387),
body SHA-256 `faff815e7684736905d984638f0e547d3697f3b16b5584d782f7ea6f8696fea6`.
Later schema-v4 [Decision 6309787719](https://github.com/jresearchsoftware/docs-evolution-review/issues/329#issuecomment-6309787719)
replaces all eight scope entries; both have `supersedes: null`. The selected native
CR is schema-v4 review `5599549918`. Absence of compatibility Requests therefore
does not prove absence of historical Decision references. No Task 329 state was
mutated for this assessment.

The retained current reader is limited to trusted historical Decision meaning
and exact native identity/body hashes. An already-admitted v4 result can revalidate
its selected original Decision reference. Fresh admission can use existing later
active v4 authority when it fully replaces every effective old field, without a
new Decision or formal supersession; unhandled effective v3 fields fail with
`CURRENT_PROTOCOL_REQUIRED`. Historical Requests/CRs remain opaque to current
execution. This bounded source dependency does not restore an old Request
selector, legacy parser or fresh v3 execution model. Original sealed older
executions still run only through their frozen source.

Sealed original consumer/source/envelopes and actual pending-operation recovery
remain protected. An untouched old handoff proves neither execution nor absence
of execution. Without concrete current effects it owns no installer resource.
The current overlay removes an old classifier's manual `unknown` result only
after checking the exact record and original journal; it never clears `active`,
writes completion or cancels an attempt. Malformed identities/receipts and real
pending effects remain unresolved. Exact original operations use their frozen
source; historical records do not justify another current execution model.

Protected original state, historical GitHub records and accepted immutable
packages remain unchanged. Removed-feature suites disappear with their features;
tests of containment, replay, publication uncertainty, cross-consumer isolation,
TEST ownership and actual retained recovery remain.

## Delivery and evidence boundaries

Relay Skill 5.0.0 is MAJOR against accepted 4.1.1 because supported obsolete APIs
and operator paths are removed and Step-numbering semantics change. It replaces
the unaccepted 4.2.0 candidate. Both delivery forms are regenerated with source
provenance; accepted 4.1.1 and older payloads remain verified immutable. Root
Shared Governance 7.0.1 stays selected; inactive accepted 7.0.0 stays intact.

DocReview qualification uses intact baseline
`dff315d0f23c283d8c456a41acf964c042b7188f`, with Git blob identities and manifest
workflow hashes checked. The old projector reproduces the transport binding
refusal; the correction prepares a targeted workflow/manifest update and local
draft PR payload. Its validated synthetic configuration uses the same consumer
and pool selection. This is generation/preparation proof, not PROD Apply or
receiving-repository publication/acceptance.

The actual owner connector schema supports `expected_head_sha` and `squash`.
Installed TEST evidence and its limits belong in the Outcome. Fixture assessment
does not accept the product PR; independent exact-head product review remains.

Changed ChatGPT custom/complete desired instructions are generated as candidate
content using an identified committed test snapshot. They do not govern this
execution. Full-text live Project Instructions reconciliation remains required
after independent acceptance/integration. Generation or NO_OP does not establish
application; Task 199 remains open at that boundary.
