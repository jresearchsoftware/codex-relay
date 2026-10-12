# Task 115 Step 2 remediation evidence

Canonical execution authority is the corrected native
[CR-115-001](https://github.com/jresearchsoftware/codex-relay/pull/118#pullrequestreview-5487214267),
complete native-body SHA-256
`0d79d88997613c03a726272998acf51f08a865335aee286fd6c20f2f7d0ad038`.
It selects trusted [Decision 6119068011](https://github.com/jresearchsoftware/codex-relay/issues/115#issuecomment-6119068011),
body SHA-256 `b90242f664f6ab8c5a8dffb0b0d38dadb322c213e0ffb6b4b19045cbfab9734c`,
and stable Task 115 charter SHA-256
`c36bf4e867ba254818d1e0807329ab50387c8e53eccdc2e751b9cbb5b87f646f`.
The native [Writer handoff](https://github.com/jresearchsoftware/codex-relay/pull/118#issuecomment-6119538323)
binds Step 2, attempt `run-38216521393`, requested `gpt-6.1-sol / ultra`,
Subagents On and the complete owner-supplied prompt.

The retained schema-v3 selector verified the live complete Request chain,
selected Decision normalization and supersession, native body hashes and
Reviewer Bot identity against complete paginated Issue/PR records. It selected
review `5487214267`, Step 2, with no selector warnings. Local HEAD, freshly
fetched remote branch and live PR head each matched required starting head
`9b6af337ee54d307e13aa2ddaee1ec41d261f559`; base was
`b4cb4943d52dd375d8c6800959b3264fad082cb8`. Work continued on the existing
`codex/task-115-step-1` branch and PR 118. The current native title tool accepted
the full supplied thread title, but read-back exposed a truncated title; exact
persisted title verification remains unavailable.

## Finding provenance and observed publication incident

F1 extends the inherited strict schema-v3 authority-currentness rule into new
schema-v4 semantics, where legitimate trusted Decisions may change during an
admitted execution. The original admission remains truthful. New v4 result
reporting must preserve it while distinguishing admitted and current authority;
independent acceptance evaluates the current requirements. Retained v3
bindings are not upgraded or rebound.

F2 is pre-existing on base `b4cb4943d52dd375d8c6800959b3264fad082cb8` and retained
at starting head `9b6af337ee54d307e13aa2ddaee1ec41d261f559`. The observed incident
had one trusted exact-head F1-only native review, matching Step 2 projections
and no corresponding new SHA-bound Reviewer check. Repeated publication
responses were `AUTHORITY_PUBLICATION_UNCERTAIN`. The protected PROD journal
was not inspected. Source and interruption tests can establish a recovery gap;
they do not prove the precise failed PROD phase. The corrected review preserves
the earlier review as immutable superseded history.

## Publication and protected boundaries

Original Task 115 Step 1 PROD admission, Request `6109630038`, publication journal
and PR execution markers remain unchanged. No original execution is retried,
rebound, backdated or fabricated. The historical missing-Outcome exception is
not owner-validated completion evidence. Independent review and owner-controlled
disposition of that anomaly remain required.

The retained historical manual-result publisher accepts Task Requests, while
this Step 2 admission is a Change Request. Its PR-binding transport also expects
the admitted Request markers; replacing the original Step 1 markers would
violate the current explicit boundary. The available TEST MCP capability cannot
substitute for the PROD admission. The Request permits a PR/committed-evidence
handoff when governed result publication is unavailable. Such a handoff is not
a Writer Outcome or proof of a Writer-verified Ready transition.

The earlier isolated TEST qualification remains historical evidence at its
recorded source/installed revisions. The fresh temporary qualification below
binds this remediation separately. No retiring PROD Reviewer repair, protected
journal change, product merge, Issue closure or unrelated execution is allowed.

## Final implementation

F1 separates immutable source/admission verification from current trusted Task
requirements for schema-v4 reporting. Manual results, automatic `finish` and
`finish-no-change`, and blocked results can report legitimate Decision drift
without pretending that the admitted work fulfilled later requirements. New
admissions capture the actual resolver inputs; Writer exports those captured
inputs and an optional current-authority/drift comparison. Legacy snapshots
without those inputs expose comparison gaps rather than guessed defaults.
Branch/head identity, source bytes, admission bindings, charter protection,
retained schema-v3 currentness and existing compatibility rules remain strict.
Publication/lifecycle actions use the conservative intersection of admitted
and current permission; reporting grants no new push or Ready permission.

Independent v4 acceptance assesses the current requirements. When material
drift or an unresolved comparison gap is present, the existing native review
call requires `expected_task_authority_sha256` for the reviewed current
authority. The same call records that exact acceptance binding. An absent,
wrong or stale digest blocks before review publication; a stale acceptance
cannot authorize continuation. Incomplete inspection of an identifiable
governed PR fails closed. Generic unlinked PR review remains available.

F2 resumes the same typed native Change Request operation across lost review
responses, authority publication, partial Step/title projection, check
publication/read-back and journal completion. Recovery verifies the exact
original native marker, body, trusted actor, target/head and current authority.
Check intent is reserved before a non-idempotent POST; uncertain responses are
resolved by exact native read-back without another POST. Duplicate, conflicting,
tampered or changed-authority state blocks recovery. Historical journal rows
with no recorded check intent can recover an already observed exact check;
an absent check remains `CHECK_PUBLICATION_UNCERTAIN`. This source correction
does not repair or prove recoverability of the historical PROD incident.

The component contracts, architecture, current workflow documentation and
historical Task115 report caveats were updated in the same PR. Runtime changes
are in commit `3ee5422bc21ab2ea5369cc167783f9f4d0af3a12`; the final test correction
is `3fff4140c57b993b9f006159529d9459ec9ace13`. Later evidence/consumer-documentation
commits do not change that tested or temporarily installed runtime identity.
The native PR and final handoff identify the complete evidence-carrying head.

## Source validation

Checks ran on native Debian Linux at
`/home/hortonolite/work/task115-step2-validation-01a12efc`, with Node `22.20.0`,
npm `11.19.1`, Python `3.11.2`, Rust/Cargo `1.90.0`, Git `2.39.5` and OpenSSL
`3.0.18`. Full logs are committed in [evidence/logs](evidence/task115-step2/logs).

| Required check | Observed result |
| --- | --- |
| `git diff --check` | PASS, including the committed starting-head comparison |
| `npm test` | 778 tests: 777 passed, 1 skipped, 0 failed |
| `python3 -m pytest -q deploy/tests deploy/ansible/tests` | 892 passed, 300 skipped, 19 warnings |
| `cargo fmt --manifest-path reviewer/Cargo.toml --check` | PASS |
| `cargo test --manifest-path reviewer/Cargo.toml --locked` | 120 passed, 0 failed |
| `python3 scripts/qualify.py` | `THREE_CONSUMER_PASS`, real handlers with isolated Git and loopback mock GitHub |
| `python3 scripts/check-candidate.py` | PASS at runtime head: 490 tracked files, 324 links; staged final evidence: 536 files, 326 links |
| `python3 scripts/qualify-sandbox-cleanup.py` as Linux root | PASS: distinct UIDs, private `0700`, collector `EACCES`, fixed cleanup helper, outside symlink, inode and replay checks |
| `cargo build --manifest-path reviewer/Cargo.toml --release --locked` | PASS; served TEST binary SHA-256 below |

The first full Node run had one obsolete tampering assertion: it expected
`AUTHORITY_CHANGED` for modified immutable charter bytes. F1 correctly reports
`AUTHORITY_SOURCE_MISMATCH`. The test was corrected with an explicit assertion
that no prepublication state was mutated; its focused five tests and the final
full Node suite passed. No product behavior was changed by that test correction.
The focused Rust Task-authority/interruption suite passed all 42 tests.

Three-consumer runtime source digest was
`222058dc8c69fa866532ee92374a04ef2a1ab9a2781d4b9fe5ff1e5eb0c380e9`.
Its debug Reviewer artifact digest was
`3fd5c8b6eb7499a0d684d35d525cfeb989c0be89666f49288a84494ae5f68256`;
test artifact digest was
`47a96ffe4b6f4991654cd690301ab75d227c07b6e98764696b53722e0d2b3107`.
These are local artifacts, distinct from the release binary served in TEST.
Native [Public CI at the runtime head](https://github.com/jresearchsoftware/codex-relay/actions/runs/38222724596)
passed Candidate checks and Codex CLI compatibility. Final carrying-head CI
remains in its native records and is linked in the PR handoff.

## Fresh installed TEST publication qualification

This execution temporarily installed exact published candidate
`3fff4140c57b993b9f006159529d9459ec9ace13` inside the existing isolated
`codex-relay-test` namespace. Existing App credentials, TLS, ingress, runner
registrations and private Node22 service overlay were reused unchanged. The
public read-only inventory observed equivalent configuration and no blockers;
administrative App/runner/ingress observations were metadata-only. Direct
temporary staging used the standing TEST authority; it is not a bootstrap,
upgrade, clean-install or production lifecycle receipt. TEST runners were
stopped during the candidate window; no ready/dispatch/model execution occurred.

The source archive SHA-256 was
`a68cee8f2bae7aefedf33f2627415e5209c25ec0e114c6699f7b11482fe059af`.
All 490 installed source files were independently compared with exact Git-tree
bytes. The release Reviewer binary, verified through the served process's
`/proc/.../exe`, had SHA-256
`0eb7a7bc6ad040de273bfe92a86914696357677a99c16a7fbd296117f1925145`.
The actual TEST Reviewer namespace reported Node `22.20.0`, its expected
nonroot service identity and `NoNewPrivileges`. The real fixed manual client,
socket and root Writer path were used; the shared host runtime was not changed.

Four original synthetic admission-shaped records were seeded before the trusted
[TEST scope Decision 6120864980](https://github.com/jresearchsoftware/codex-relay-testbed/issues/6#issuecomment-6120864980)
was published through the official connected TEST App. Both manual submissions
then traversed official OpenAI mTLS, the candidate Rust Reviewer, the real TEST
socket/root Writer, private Node22 and the TEST Writer App to native GitHub.
Automatic completion used the fixed TEST Writer through transient private
Node22 units. Its successful contained-execution, clean-collection and prior
publication fields were expressly synthetic expected-state inputs.

| Installed route / synthetic run | Native Writer publication |
| --- | --- |
| Manual, no PR / `9007115000401` | [Outcome 6120882274](https://github.com/jresearchsoftware/codex-relay-testbed/issues/6#issuecomment-6120882274) |
| Manual, PR7 / `9007115000402` | [Outcome 6120948158](https://github.com/jresearchsoftware/codex-relay-testbed/pull/7#issuecomment-6120948158) |
| Automatic `finish-no-change` / `9007115000403` | [Outcome 6121034785](https://github.com/jresearchsoftware/codex-relay-testbed/issues/6#issuecomment-6121034785) |
| Automatic `finish`, PR7 / `9007115000404` | [Outcome 6121131253](https://github.com/jresearchsoftware/codex-relay-testbed/pull/7#issuecomment-6121131253) |

Complete paginated native read-back verified the trusted Writer Bot identity
`338711029`, each exact body hash and exactly one Outcome per run. All four
preserved original authority/admission/captured resolver inputs and reported
current authority `b60350f300d2f48bd896b2c8bf6125a77342ce730718489262cc8ec1dd4b55f4`,
changed field `scope` and `review_required: true` visibly before the folded
machine block. Replays preserved IDs and bytes. Manual changed-claim, wrong
admission and changed-PR-marker negatives returned `MANUAL_OUTCOME_CHANGED`,
`MANUAL_OUTCOME_BINDING_INVALID` and `PR_AUTHORITY_CHANGED`. Manual PR publication
became Ready while explicitly requiring current-requirement review. Automatic
completion retained Draft despite `MERGEABLE`, because permission for automatic
lifecycle actions had changed. No independent acceptance was published.

The first automatic-PR fixture call stopped at
`AUTHORITY_TITLE_PROJECTION_MISMATCH`: the harness used an unbounded title.
After inspecting the protected synthetic claim and existing projection helper,
only the disposable PR title was corrected. The same synthetic admission then
published successfully. An initial fixture seed also stopped on a missing
TEST journal directory after three own claims were copied; exact own bytes
were checked before completing the seed. These were preparation defects,
not evidence of product regressions or authority to retry unknown executions.

Qualification proves these installed publication paths from synthetic inputs.
It does not prove real Writer admission, worker/model traversal, trusted Git
import/push, a real Relay Actions run, interrupted live native CR POST recovery,
global-host Node support, PROD installation or independent product acceptance.
F2 interruption/recovery proof is from the Rust suites with mock native GitHub;
no retiring PROD repair was required or attempted.

Cleanup restored exact original pointer
`/opt/codex-relay-test/releases/5699432e95440307fa799b0a3b8ac3150ffd574a`
and the original active state of Reviewer, both runners and manual socket.
Four own synthetic claims and two journals were archived for verification and
removed under the publication lock; the own empty journal directory, temporary
candidate and work area were removed. TEST Issue6/PR7 native Decision and Outcome
history was preserved. Original PR7 body/title/Draft and unchanged head
`36d4e73b8a0b3450f78b5a00d672f0079d7f8b18` were restored. The consumer's provisional
source selector was restored; its same-Task runbook correction is separately
published through the ordinary consumer PR flow. Older user checkouts were left
untouched. [Receipts and one-shot fixture scripts](evidence/task115-step2)
are committed for review; they are explicitly TEST evidence, not new product
operational interfaces or a task-state registry.

## Warnings, evidence limits and handoff

- The current API warning reader reported complete mandatory surfaces and zero
  observed check-annotation warnings at `3fff414...`. Original Step2 routing
  job [114702435234](https://github.com/jresearchsoftware/codex-relay/actions/runs/38216521393/job/114702435234)
  completed successfully at starting head `9b6af337...`; its native annotation
  collection was empty. UI-only GitHub service/pre-execution annotations are
  outside that reader's scope, so no global absence of GitHub warnings is claimed.
- Python retained 300 prerequisite/conditional skips and 19 dependency
  deprecation warnings (passlib `crypt`: one; Jinja escape `\s`: eighteen).
  Root cleanup was qualified separately; skipped cases are not claimed as PASS.
- Release build emitted four pre-existing Rust warnings: two unused mutable
  variables and unused `valid_task_identifier` / `valid_part_identifier`.
  Exact starting source already contains the same declarations. They do not
  establish an introduced regression and were not changed outside this scope.
- Global/shared-host Node `18.20.4` remains below declared Node `>=22`.
  Private TEST Node22 qualifies the Reviewer/manual publication paths only;
  global lifecycle/runner support and PROD remain separate owner boundaries.
- A TEST helper failed on model capacity before any external mutation;
  the parent completed that assignment without substituting another model.
  Requested parent profile is `gpt-6.1-sol / ultra`; actual model/effort are
  `UNAVAILABLE` because the runtime did not expose proof. Subagents were used
  within the admitted On permission, for Node, Rust, authority and documentation
  work. The exact persisted native chat title remains unverified as noted above.

Implementation and the bounded validations are complete for independent review.
The existing PR remains Draft under the protected publication boundary; this
permitted Step2 committed-evidence handoff is neither a Writer Outcome nor a
Writer-verified Ready transition. The original Step1 missing-Outcome anomaly,
historical journals and execution markers remain unchanged and require owner
disposition. Independent exact-head acceptance, product merge, PROD installation
and Issue closure remain unperformed; Task115 retains `keep-open`.
