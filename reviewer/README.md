# Reviewer MCP service

This is a deliberately minimal custom Streamable HTTP transport, using pinned `axum 0.7.9` rather than an MCP crate because the required wire protocol is small and version-sensitive. It implements the narrow request/response subset of the [MCP Streamable HTTP transport](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports): JSON-RPC POST, JSON/SSE `Accept` negotiation, origin rejection, and no SSE GET session. It exposes `check_pr_review_target`, `submit_pr_review`, `read_pr_review_evidence` and `publish_task_authority`, plus the separately enabled `submit_manual_outcome` Writer handoff capability.

It reads the admitted bind, repositories, base branch, check name and App settings
from `reviewer-mcp.json`. It publishes verdicts/findings authored by an external
ChatGPT review conversation; it does not perform the review itself. Current
ingress supports the OpenAI connector mTLS identity only. See the complete
[integration contract](../docs/integration-reference.md#reviewer-runtime-contract)
and [plain config](../examples/reviewer-mcp.json).

For credential-free local evaluation from the repository root, use:

```sh
python3 scripts/qualify.py
```

It generates temporary client certificates, config and SQLite state and exercises
the real binary with publication disabled, plus enabled mock-GitHub handlers.
An installed service is invoked as `reviewer-mcp-http --config /absolute/reviewer-mcp.json`
only after the consumer has supplied and qualified all required environment and
ingress. The source-controlled [deployment interface](../deploy/README.md)
installs and qualifies the service; no public release artifact exists yet.

Environment: `REVIEWER_MCP_CONFIG` (CLI alternative), `REVIEWER_CLIENT_CA_FILE`,
`GITHUB_APP_ID`, `GITHUB_APP_INSTALLATION_ID`, `GITHUB_APP_PRIVATE_KEY_FILE`,
`REVIEWER_RELAY_DB`, and `REVIEWER_RELAY_ENABLED`. Only exact `true` for the last
variable enables review/check publication; startup logs `publication_mode`.
The obsolete `mutation` config field is rejected, rather than implying an
enabled publisher is read-only. Disabled instances can still read GitHub targets
and initialize SQLite; they reject Reviewer publication with `RELAY_DISABLED`.
The manual Writer submission capability has its own installed configuration gate.
App/installation credential IDs must agree with config. Keep durable DB/WAL state
private across restarts. `artifact.commit`/`artifact.sha256` are operator-recorded,
shape-validated metadata, not verification by the running binary. The consumer
owns TLS termination; the service also verifies the forwarded client certificate.
Do not bind this binary publicly.

`publish_task_authority` implements the opted-in
[`github-native-v1` authority contract](../contracts/README.md#github-native-task-authority). Its input is
`repository` and one structured `record`: Task Decision, independent exact-head
PR Change Request, no-PR Task Approval or Task review findings. New publication
uses schema `4.0`; historical schema `3.0` Task Requests, Decisions, CRs and
acceptance records remain readable and recoverable. New Task work and
continuation require no public full Task Request. The stable charter marker
remains `Authority model: github-native-v1`; callers cannot choose an API path,
credential, native author, arbitrary GitHub body, labels or PR title. Writer
Outcomes remain a separate trusted Writer responsibility and this tool rejects
their publication.
See the [Task workflow guide](../docs/task-workflow.md) and
[complete synthetic authoring examples](../examples/task-authority.md). Publish
typed PR remediation through `publish_task_authority` with a `change-request`
record; the retained legacy installation path uses the CR2 `change_request`
input to `submit_pr_review`. It is not a fallback for new v4 work.
Native exact-head PR `APPROVE` continues through `submit_pr_review` in either
model. Task Approval and Task review findings use typed Issue records and do
not substitute for a genuine PR verdict.

Typed publication requires both the enabled publication mode and runtime
`githubNativeAuthorityEnabled: true`; the latter defaults to false for existing
configurations and rejects publication before any GitHub access. Managed source
deployment enables it only with the paired controller/workflow contract. Install
and qualify that same release and reviewed workflow projection before adding
the exact `Authority model: github-native-v1` line to an owner-authored Issue.
An old binary cannot recognize a new charter marker; manual mixing of old and
new components is unsupported. With the qualified native capability enabled,
fresh legacy CR2 or v3 Decision/Task Request/CR publication fails with
`CURRENT_PROTOCOL_REQUIRED`; use the current v4 path or explicit owner-authorized
migration. Historical reads, already-reserved exact publication recovery and
safe completion/Outcome publication of old admitted attempts retain their
original contract. Native PR `APPROVE` remains available for a genuine exact-head PR.
Reserved v3 Decisions retain exact-operation recovery; schema-v3 result
acceptance for an old admitted attempt remains supported.

## Independent review and finding provenance

Review the complete exact candidate head against the live canonical Issue and
applicable Change Request authority. Aggregate reasonably discoverable material
findings rather than stopping at the first blocker. Independent acceptance
remains bound to that exact head; deterministic checks alone do not establish it.

For each material finding, including a failing test/check or claimed regression,
compare the candidate with the reviewed starting/base state. Identify the exact
candidate and comparison SHAs, relevant evidence, and finding provenance:

- introduced by the current implementation or remediation;
- pre-existing on the baseline;
- pre-existing but newly exposed or made blocking by changed validation;
- undetermined, with the missing evidence stated explicitly.

Use `regression` only when evidence supports introduction by the current
implementation or remediation. A newly failing gate does not by itself prove a
newly introduced defect. Pre-existing baseline defects do not automatically
become current-task remediation unless current authority covers them or the
current change materially depends on, modifies, or newly includes them in its
authorized acceptance boundary. Explain that authority or dependency when
prescribing remediation; discovery alone does not expand scope.

On rereview after a Change Request, separately assess closure of prior findings,
behavior changed by remediation, adjacent regression risk, and genuinely new
findings. If a blocker survives remediation, explain why the previous review or
remediation missed the invariant before prescribing another correction; state
any remaining evidence gap rather than inventing a cause. Keep this reasoning in
the existing review/Change Request record without a new state machine, ledger,
or schema.

These Relay review obligations were relocated unchanged from root AGENTS to
keep one product reference. Shared methodology supplies their neutral context;
its additional topics do not alter native verdict, identity or routing behavior.

## Current protocol capabilities

`tools/list` advertises the current schema-v4 authority input and the separately
enabled `submit_manual_outcome` tool. A caller needing current Task Decisions,
CR publication, independent review or a manual Writer Outcome must use the
required current connected App/Reviewer/Writer capability. If the tool is absent
or its exposed schema is outdated, stop the affected native operation before mutation, identify the missing
tool/schema and the qualified installation/connection needed, and ask the owner
to correct that mismatch within existing installation authority. Ordinary
owner-authorized standalone/manual work follows the
[route policy](../docs/task-workflow.md#owner-acceptance-and-execution-routes),
without fabricating native records or replacing admitted-attempt recovery.
This distinction does not add an installed service capability. Never substitute
a v3 Decision/Task Request/CR, legacy CR2, old owner-result comment transport or alternate
legacy routing. Historical exact-attempt completion/recovery uses its preserved
contract; it does not initiate fresh work.

The installed service enforces its own native publication and manual-transport
configuration. Missing current native publication capability returns
`CURRENT_PROTOCOL_CAPABILITY_REQUIRED` before publication; manual Writer
transport retains its bounded disabled/unavailable errors with actionable
installed-capability guidance.
These checks cannot observe inaccessible client tools or a stale connected App
cache. Client-visible tools/schema verification belongs to the caller; source
version, a charter marker and configuration alone do not prove that connection
was upgraded or qualified. No new client handshake or mandatory probe is added.

## Native authority and publication

The service re-reads the owner-authored Issue and hashes its entire UTF-8 body,
including the marker, as the stable charter. It resolves configured owner,
Reviewer and Writer logins through GitHub to native user IDs and types. Typed
Decisions and Requests must carry the trusted Reviewer Bot identity; Outcomes
must carry the separate trusted Writer Bot identity. The configured App ID and
slug are also verified. Every selected SourceRef is fetched again by its native
ID, checked against the selected configured repository and native parent URL,
and compared with its exact body digest. Sources may be the canonical Issue body,
Issue comments, native PR reviews or review comments on a PR linked to that
Issue. Caller text cannot establish native identity or source provenance.

For new work, the original charter plus trusted, active Task Decisions supplies
current authority. Decisions accumulate without a Step; exact supersession
references remove the replaced Decision, and the remaining Decisions apply in
ascending native comment-ID order. Ordinary comments cannot amend the Task.
A Task-scoped Decision can explicitly change effective closure policy; a
PR-scoped Decision or CR cannot. A v4 PR CR is an independent native exact-head
review with actionable findings and bounded profile/validation/boundary
overrides. It requires no replacement Task Request, carries no Step and changes
no Step labels or PR title. Writer allocates Step only when admitting execution.
Fresh v4 CR publication binds `base_sha` to the observed native PR base SHA;
recovery retains the reserved original body/base after base movement.
The old complete Request chain, Step projection and exact body recovery remain
supported for schema-v3 histories and already admitted executions.

A v4 Task Approval or Task review binds current charter/Decision sources, the
protected Writer admission digest and Step, one trusted native Writer Outcome,
and identical immutable result identities. A carried v3 Request and originating
CR remain exact source references when applicable. Completion/acceptance and
continuation follow the immutable compatibility selection: `null` remains `null`
despite historical v3 Requests, and a retained reference keeps its exact source
and currentness checks. A later independent native
APPROVE does not erase the originating CR from the accepted Outcome's lineage;
a different newer active CR still stops acceptance. Valid trusted Task
Decisions added during execution do not suppress the original Outcome. Review
compares its immutable admitted authority with the effective current Task;
acceptance binds that current authority and requires disposition of amended
requirements. Missing work needs actionable remediation, while an unused
permission expansion alone does not invalidate the result. Material Task
changes after acceptance require fresh acceptance before protected
continuation. Native PR approval retains its acceptance-time authority binding
in the review; a receipt cannot silently attach an old approval to newer Task
semantics. Retained v3 currentness and exact source bindings remain unchanged.
Git results bind an exact SHA; deployment, qualification, evidence and no-change
results bind an immutable revision or native run/result identities. Approval
preserves every Outcome warning's source and impact, records disposition and
evidence gaps, and retains all limitations. An open implementation PR needs a
native exact-head PR verdict, rather than an additional Task Approval. Genuine
no-PR work can be approved on the Issue; a closed disposable PR can supply
context and Outcome without reopening. Reviewer creates no PR, merges no PR and
closes no Issue. Missing or conflicting charter closure metadata remains
`keep-open` with a visible warning.

Validated records render human-readable English substance before one collapsed
`Machine-readable authority (JSON)` details block. Findings, corrections,
acceptance criteria, warning impact/disposition/next action/evidence gaps and
limitations remain visible. Untrusted HTML, Markdown, links, mentions and
fences render as literal text. Canonical JSON bytes remain unchanged. If the
complete summary would exceed native size limits, canonical JSON opens with a
visible presentation-limit explanation; material facts are never truncated.
The shared Node/Rust fixtures cover both schema generations and malicious text.
GitHub is authoritative for completed publication. SQLite retains only the
original publication intent and the coordination that GitHub cannot supply.
Fresh databases contain six operation fields:

| Local state | Before | Retained purpose or replacement |
| --- | --- | --- |
| `operation_id` | Publication/deduplication key | Keep the historical deterministic identity and atomic primary-key reservation; native operation markers bind GitHub readback to that same operation. |
| `status` | Reservation plus local completion stages | Keep `RESERVED` and `RETRYABLE_FAILURE` only as decisive-POST permission. No local completion transition establishes or negates publication. Historical completed statuses never permit another decisive POST. |
| `publication_body` | Frozen rendered body | Keep exact original bytes for unresolved intent, renderer drift and historical verification. A missing old body uses its original legacy renderer. |
| `authority_binding` | Original authority/acceptance snapshot | Keep the acceptance-time authority, admission/Outcome lineage and immutable compatibility selection where a public review cannot reconstruct them. Changed authority stops resumed mutations. |
| `step_binding` | Legacy/v3 metadata anchor | Keep original Issue/PR binding and initial PR title for partial legacy/v3 projection; v4 publication allocates no Step and projects no Step metadata. |
| `check_intent` | Irreversible one-POST guard | Keep only a bounded possible-send budget: `0` before the first send, `1` after its reservation, `2` after the recovery-send reservation. Historical `NULL` receives one prospective recovery send to `2`, without inventing an earlier observation. |
| Review/native/check IDs, URLs and actor receipt fields | Mirrored GitHub receipts used as recovery gates | Remove active receipt storage and its vetoes. Discover and verify native identity, author, body, parent, state, exact SHA and check properties on GitHub. |
| `finding_digest`, `created_at`, `events` | Unused digest/timestamp mirrors and append-only event history | Remove new diagnostic journal writes. Existing columns, values and event rows remain intact; old required INSERT columns receive inert compatibility defaults. |

The short SQLite transaction and primary key elect one decisive publisher
across concurrent processes and restarts. They never span a network request or
hold unrelated operations. The original reservation survives an ambiguous
Review or authority-comment POST; neither missing readback nor a missing local
receipt authorizes another decisive POST. Complete, bounded native readback
must identify exactly one trusted original operation, including its body,
parent, actor and reviewed SHA. Re-read its native identity and current
authority before further mutations. Verified GitHub evidence recovers the
publication even when the local completion receipt is stale or absent.
Recovery with no local row retains an unknown Check history, allowing only one
prospective recovery send. Fresh v4 CR bodies carry the original effective
authority digest beside the operation marker. A historical CR missing both that
digest and its original protected authority binding may report already verified
Review/Check effects, but cannot create a missing Check using newer Decisions.

Acquire Check credentials and prepare its request before reserving a possible send.
A proven pre-POST failure or definite rejection atomically refunds exactly
that single-use send grant, preserving any concurrent sender; an already-sent request with an unknown outcome
retains its reservation and must reconcile against GitHub. Diagnostics identify
the failure phase without another durable event history. A local lock alone
does not replace the persistent decisive-POST reservation.

The auxiliary Check Run has a proportionate recovery policy. Bounded complete
paginated `filter=all` readback verifies the exact operation `external_id`, SHA,
configured App ID/slug, name, status and conclusion. Reuse an existing valid
check. When adequate readback finds none, allow at most the original possible
send and one identical recovery send, each reserved by the atomic budget. A late
first response may leave two distinct-ID identical checks: report that visible
duplicate warning and treat them as the same logical auxiliary effect. More
than two, conflicting properties, incomplete readback or exhausted send budget
fail safely with a concrete operator action. Check repair never republishes
the Review or typed authority record. Native publication is not a complete
review/check result while required check evidence remains unverified.

Partial legacy/v3 Step projection resumes the original native identity and
requires the reserved initial PR title or its canonical projection. Task
Request/CR Step labels and the bounded existing PR title remain deterministic
projections, preserving unrelated labels. Missing historical anchors retain
the existing bounded migration boundary. Recovery changes no original body or
authority, allocates no Step and launches no execution. Reviewer/Writer
identity separation, App authorization and exact-head/current-authority gates
remain binding. An unresolved operation holds only its own operation identity,
not independent Tasks, PRs or repositories.

The staged synthetic installation check is:

```sh
python3 scripts/qualify-reviewer-publication.py
```

It builds the actual service main with the explicit `synthetic-github` feature,
stages disposable configuration, fake App RSA material and a test mTLS chain,
and exercises publication, two-process concurrency and crash/restart against
loopback GitHub. That feature accepts only an explicit loopback fixture URL,
emits `SYNTHETIC_GITHUB_ONLY`, and is not a deployment artifact. Default builds
do not read the fixture override. Use `--binary` and `--default-binary` to reuse
separately built artifacts. This qualifies the staged installation-to-operation
path; it does not qualify root/Ansible/systemd, real GitHub/App permissions,
shared TEST or PROD. The ordinary candidate/qualification checks remain required.

Each source response is limited to 256 KiB and five seconds. Comments, reviews
and branch/base-filtered PR artifacts share a complete collection reader. It
starts with 100 records per page and reduces an oversized page to 50, 25, 5,
then 1. Each smaller size divides the previous size, so the next fixed GitHub
page starts at the same unread offset without restarting or changing native
order. Already acquired records are retained; duplicate native IDs and invalid
pages fail closed rather than being silently deduplicated. Server Link URLs are
never followed; a short page advertising a next page is incomplete evidence.

Each collection retains the intended 500-record capacity, with an empty
completion read after a full final page, and an 8 MiB aggregate response-body
transfer budget including oversized attempts. The reader performs at most 501
successful page reads and four size reductions. Each collection also has a
60-second deadline, including token acquisition, so callers outside the typed
publisher cannot accumulate unbounded time across smaller pages. The enclosing
typed operation still has its own 60-second deadline, and selected context
remains limited to 250 KiB.
The independent byte budget bounds repeated transfer and retained JSON without
reserving the pathological 128 MiB implied by 500 maximum-sized sources. It
allows the observed Task 84/109-sized histories and ordinary longer histories
whose aggregate bytes exceed the single-response limit. It is an internal
bounded acquisition policy, with no new owner input or prerequisite.

An individual record that cannot fit a one-record response fails with
`AUTHORITY_SOURCE_TOO_LARGE`; more than 500 records or a contradictory completion
page fails with `AUTHORITY_SOURCE_TRUNCATED`. Aggregate transfer exhaustion is
`AUTHORITY_COLLECTION_BUDGET_EXCEEDED`, malformed/duplicate data is
`AUTHORITY_SOURCE_INVALID`, and API or response-stream failure remains
`AUTHORITY_SOURCE_UNAVAILABLE`. Collection deadline exhaustion is
`AUTHORITY_COLLECTION_TIMEOUT`. No partial collection is accepted. Histories
exceeding the record, transfer or operation-time budgets, and individual native
responses over 256 KiB, remain unsupported even if their records are otherwise
legitimate; publication cannot infer authority from incomplete acquisition.

A native exact-head PR `APPROVE` also returns the bounded
`native-approve-exact-head-squash-v1` continuation policy. It authorizes automatic
continuation only for that reviewed head, squash merge, passing native required
checks and verified mergeability. Unresolved checks block continuation;
an explicit hold blocks continuation, and `keep-open`, an incomplete Task or
remaining Task work blocks Issue closure. Native next-request or selected Task
Decision references are re-read before publication. `execution_supported: false` makes explicit
that this Reviewer implementation publishes the policy and performs neither a
merge nor closure. Execution belongs to a separately authorized trusted owner
channel, never the worker. `REQUEST_CHANGES` requires an owner-authorized
publication after review preview; a preview alone grants no mutation authority.
Task Approval is independent acceptance of the bound result, not PR approval.
The v4 continuation receipt carries effective closure permission, hold/next,
exact source/admission/Outcome identities and a requirement for trusted owner
canonical completion evidence. It does not infer Task completion from an
implemented Step or absence of a next direction. Owner orchestration verifies
remaining work and applicable qualification conditions before conditional closure.

An owner-created standalone source PR can instead receive a `source_pr`
continuation binding without admission/Outcome. The service verifies native
owner ID/login/User type, repository, branch/head and current Task sources.
The native review includes the reserved
`jresearchsoftware-reviewer-source-pr:v1` marker alongside its authority digest;
callers cannot inject either marker. The existing review operation journal
retains this binding across retries. Exact retained manual Request acceptance
is supported without publishing a fresh v3 record; current v4 work needs no
Request or Step. Known same-result Writer evidence and execution markers retain
the admitted path, not source fallback.

`owner_authorization: explicit-standalone-required` makes the remaining trust
condition visible. The conditional `automatic_continuation_authorized` policy
does not assert that a missing Outcome proves no admission or that PR authorship
proves permission. The existing owner adapter must verify those semantic facts
from canonical authority and actual execution evidence, together with warning
disposition, before any effect. There is no additional review input, owner
confirmation or public result transport. Ordinary result comments never become
Writer Outcomes or Task Approvals. See the
[owner adapter contract](../contracts/README.md#authorized-continuation-after-independent-acceptance).
Synthetic publication/continuation tests do not qualify a live owner adapter,
App permissions, installed service or GitHub merge.

`submit_manual_outcome` accepts only `{repository, task, run_id, result}`;
`task` and `run_id` are positive safe integers, and `result` is the canonical
schema-v3 or schema-v4 Outcome claim for an already admitted manual attempt.
The optional installed `manualOutcomeEnabled` boolean defaults to false. When
false, the tool is not advertised and calls fail before contacting GitHub or
Writer. It is independent of Reviewer review-publication mode. The installed
`manualOutcomeClientPath` defaults to `/opt/codex-relay/relay-manual-outcome`;
it is a fixed absolute POSIX path with that basename, never a caller field.
Consumer deployment sets the namespace-specific protected client path.

The same qualified OpenAI mTLS route authenticates submission. Reviewer runs
the fixed nonprivileged client with a cleared environment, sending bounded JSON
on stdin and accepting only a normalized public Writer receipt. The client
uses the protected local UNIX socket and narrowly scoped root Writer service;
Reviewer retains `NoNewPrivileges`, receives no Writer GitHub credential and
cannot choose another Writer operation. Socket admission and Writer publication
are separate from Reviewer Bot credentials and SQLite review state. Foreign
repositories, invalid/currentness-changing authority, automatic/unadmitted
attempts, incorrect Step or result, duplicates and uncertain publication are
validated or recovered by Writer under its existing publication lock/journal.
There is no owner-authored manual-result precursor, identity-proof comment,
second dispatch transport or owner approval step for delivering the claim.

Submission arguments are limited to 60,000 UTF-8 JSON bytes within the existing
62,000-byte JSON-RPC body limit, public receipts to 32 KiB and the client wait to
60 seconds. Oversize input/response and unavailable or uncertain Writer state
remain explicit errors, without truncation, raw helper diagnostics or secret
output. A retry supplies the same admitted result and recovers its existing
Writer publication; it cannot launch another execution. The receipt names the
Writer actor, exact native Outcome ID/parent/body digest and URL. It records
Codex claims and verified binding, not proof that every claimed test ran or
independent acceptance. Old owner-authored manual-result and Writer Outcome
records remain immutable readable history. Source tests of this boundary do
not qualify an installed UNIX socket, service, mTLS ingress or credentials.
Late schema-v4 manual reports remain bound to their original immutable
admission. When a later Step owns current projections, an original hosted Git
commit may be reported on its bound PR without changing the current ref or
Draft/Ready state; it is historical evidence, not current-head acceptance.
Outcome bytes freeze before the original POST, so later Steps or Decisions
cannot change a lost-response readback into a different result. Retained
v3/legacy publication keeps its original bindings and cannot overwrite newer
native Step lifecycle projections.
Configure either the existing top-level `repository` string or a nonempty
`repositories` array of strings, never both. Both forms normalize to a repository
set; duplicate entries collapse. For example, replace the `repository` field in
the [plain config](../examples/reviewer-mcp.json) with:

```json
"repositories": ["example-org/sample-project", "example-org/second-project"]
```

All other settings remain shared, including owner, base branch, check name,
validation vocabulary, publication mode, database and App/installation identity.
One Reviewer installation can serve all configured repositories it already has
access to. Writer configuration remains single-repository and separate.

For the supported deployment interface, set the optional
[`environment.reviewerRepositories`](../deploy/README.md#inputs-and-invocation)
target list. Omission preserves the consumer's single repository. Deployment
renders the compatible runtime form and qualifies the same Reviewer
App/installation against every target.

Every tool requires an explicit `repository` target. Its schema uses `const`
for a singleton set and `enum` for multiple repositories. Calls must select an
exact member of that set before contacting GitHub; typed authority records must
also name the same selected repository. There is no repository default or
separate CLI/environment override. Configuration admission requires ASCII
`owner/repository`: owner length 1–39 with letters,
digits and single internal hyphens; repository length 1–100 with letters,
digits and `._-`, excluding `.` and `..`. Values are not trimmed, decoded or
case-normalized. Missing, wrongly typed, malformed or unconfigured caller values
fail closed.

The selected repository also reaches every installation-token request: its
repository name is the sole entry in GitHub's `repositories` restriction, and
the same `owner/repository` supplies subsequent GitHub API paths.

All GitHub REST requests use the shared stable `User-Agent: codex-relay-reviewer/0.1.0`.

`read_pr_review_evidence` accepts only `repository`, `pr_number` and
`expected_head_sha`. It works with publication disabled and makes no repository
mutation or model call. Its advertised output schema distinguishes `available`,
`absent`, `unavailable`, `permission_denied` and `truncated` for each source.
The reader verifies the PR binding before and after collection, returns native
check/suite/run identifiers and URLs, and projects exact-head Writer Outcomes
from the reviewed PR and canonical linked Issue, preserving the comment target
and native comment ID. An exact-head Writer Outcome's native
`Attempt: run-N` binds a relevant routing execution and its check-suite
annotations even when that workflow ran on the trusted base revision. Evidence
preserves the actual execution head separately from the reviewed candidate head.
Only allowlisted, bounded fields are returned;
raw logs, artifacts, annotation `raw_details` and protected diagnostics are
excluded. Text is bounded and known credential/protected-content markers are
redacted. Redaction is not proof that arbitrary private text is public.

The same sanitizer covers Outcome warning summaries, annotation paths, titles
and messages, and check/run names. It scans the full original and control-filtered
field before byte truncation, including the exact active Reader token/JWT, so
shortening cannot expose a credential fragment. Recognized secrets or protected
content suppress the whole field; mixed benign text does not exempt a secret.
Credential-shaped prefixes and assignment/header syntax remain protected,
while incidental word fragments such as `Task-authorized` and `task-local`
remain readable.

Plain references to `/etc/systemd/system/`, service unit filenames there, and
their `.service.d/*.conf` drop-in filenames remain readable. This narrow path
exception does not authorize returning unit contents: configuration sections,
assignment syntax and other protected markers still suppress the field.
Traversal, malformed paths and other `/etc/`, `/var/lib/`, `/run/` or `/home/`
references remain conservatively redacted. This deliberate limitation can still
hide a harmless protected-path description; treat it as an explicit evidence
gap for independent disposition, never as proof that no warning occurred. Do
not disclose configuration/diagnostics or add a second evidence channel to work
around it. Source tests do not establish adoption by an installed Reader.

Acquisition is limited to 256 KiB per response, 2 MiB aggregate transfer,
40 requests including authentication, three pages of 25 items per source,
250 annotations overall, five seconds per request and 30 seconds per read.
Every budget or source failure remains visible. No response URL, redirect,
caller-selected path or pagination cursor is followed.

Mandatory automated evidence covers warnings/annotations produced after actual
job, check or Relay/Reviewer runtime execution has begun and exposed through
supported GitHub/runtime APIs. The reader acquires supported
[check-run annotations](https://docs.github.com/en/rest/checks/runs#list-check-run-annotations),
exact-head check/run state, and bound Relay execution Outcome warning fields.
`required_surfaces_complete` reports completeness within that scope;
`warning_observation` is `observed`, `none_observed` or `unknown`.
A required in-scope source that is unavailable, permission-denied, redacted or
truncated prevents an absence claim. An empty successfully inspected source means absence
on that source; it does not establish absence on other sources.

GitHub service-level or pre-execution workflow annotations and platform policy
banners visible only in the UI are outside mandatory automated acquisition.
The `github_workflow_run_platform_annotations` source retains an explicit
`unavailable` limitation, native run links and `required_for_completeness=false`;
that excluded source alone does not make supported evidence incomplete or block
independent review. No rendered HTML scraping, browser cookies/session state or
public-repository fallback is used. API completeness or `none_observed` does not
prove that no UI-only warning exists. This exclusion can change only when GitHub
exposes a supported API suitable for public and private repositories. Evidence
completeness does not itself establish independent acceptance or warning disposition.

`submit_pr_review` has two action-specific inputs. `APPROVE` needs only the
target (`repository`, `pr_number`, `expected_head_sha`), action and a bounded
`review_body`; legacy non-executable `structured_findings` remain optional.
For schema-v4 work with a verified material difference between the delivered
Outcome's admitted Task and the current Task, or an unresolved comparison gap,
`APPROVE` additionally requires
`expected_task_authority_sha256` equal to the current authority digest exposed
by the review target. This binds the reviewer's current-requirement comparison
in the same review call; a stale or missing expectation stops before native
approval publication. Without it, the service could silently attach old review
prose to amended requirements the reviewer had not assessed. The conditional
digest adds no separate event or review phase; unchanged v4 and historical
v3 calls retain their existing inputs. New Writer Outcomes export bounded
`authority_resolution` captured under the original admission digest for their
actual resolver defaults; old admissions are never rewritten to add it.
For older Outcomes lacking it, unknown defaults are reported as comparison
gaps rather than a proven material change or an assumed profile.
`REQUEST_CHANGES` requires a structured `change_request` instead of either
`review_body` or `structured_findings`. The tool exposes ordinary top-level
properties with required `repository`, `pr_number`, `expected_head_sha` and
string-enum `action`, without a root conditional schema. Rust enforces the
action-specific requirements and rejects mixed payloads before GitHub access;
the nested executable CR schema retains v2 and binds its validation enum to the
configured vocabulary. Optional `validationNames` must match Node consumer
policy; undeclared names fail closed. Supply semantic findings,
remediation profile, Step, validation names,
starting-state requirements, completion requirements, boundaries and outcome
tokens/descriptions. Owner-policy reconciliation and finding evidence are
optional; omitted effort/Subagents use the shared execution defaults described
in the [CR contract](../contracts/README.md). No interactive ChatGPT model/effort
is required or recorded as governance metadata.

Reviewer validates the input before contacting GitHub, then renders a canonical
human-readable CR plus the version `2.0` execution data inside the same native
review. It checks the live PR binding and exact head, and verifies the returned
CR body and native review state. For a new executable CR, synchronized Issue/PR
Step N supplies N+1. After native publication, the same Reviewer operation
ensures the Step label, replaces both targets' Step labels while preserving
unrelated labels, updates the bounded canonical Task/Issue/Step/CR-ID PR title and
re-reads the binding, labels and title before reporting success. Partial failures
resume the same native review ID and authored Step through existing publication
recovery; approval changes no Step. Ordinary owner post-CR synchronization is
retired. Owner new-phase choice remains separate from this bounded projection.
The configured human owner must author the canonical linked Issue. Deployment
projects that identity from the existing consumer `owner`; no new owner input is
needed. The existing operation binding retains the exact initial PR title, and
recovery accepts only that title or the canonical projection of the same CR.
A historical published SQLite record without the pre-publication Step anchor or
its exact initial-title field may continue only when labels and canonical title
are already fully synchronized. An existing anchor's authority hashes must
still match before the same operation can acquire the title field.
Otherwise `LEGACY_STEP_BINDING_REQUIRED` preserves the existing review for
[explicit bounded owner migration recovery](../contracts/README.md#legacy-publication-migration-recovery),
then replay of the original payload and native review ID. That exception grants
no new review, Step, execution or normal owner post-CR writer.
Duplicate keys, unknown fields, malformed identifiers, duplicate finding IDs/validation,
invalid tokens/Step, unsafe text and payload/rendering overflow fail closed.
Operation identity binds the rendered body and all findings; repeated calls
retain existing duplicate suppression and uncertain-publication recovery.
Review operation IDs already include the selected repository, and typed
authority operation IDs bind the record's repository through its canonical
body. The shared SQLite journal and Step bindings therefore distinguish
overlapping Issue/PR numbers across repositories without changing existing IDs
or migrating retained publication state.

The minimum Reviewer installation permission set remains `metadata:read`,
`actions:read`, `issues:write`, `pull_requests:write` and `checks:write`:

| Permission | Supported purpose |
| --- | --- |
| `metadata:read` | Repository/installation identity and access qualification |
| `actions:read` | [List/get workflow runs](https://docs.github.com/en/rest/actions/workflow-runs), including run/check-suite/attempt binding for execution evidence in private repositories |
| `issues:write` | Typed Task authority comments and deterministic Issue/PR Step-label synchronization; read access also supplies linked Issue authority and Outcome comments |
| `pull_requests:write` | Native review publication and bounded PR-title synchronization; read access supplies PR/head and decisive-review binding |
| `checks:write` | Reviewer check publication; read access supplies check suites/runs and annotations |

Excluding UI-only warnings does not remove the supported Actions run-binding
requirement. No Actions write or additional permission is needed. Repository
tokens are restricted to the selected configured repository; the evidence
reader requests a separate token with only read permissions for `metadata`, `pull_requests`,
`checks`, `actions` and `issues`. The host-local App qualification checks the exact
installation permission set and uses a metadata-only probe token; it does not
prove live evidence endpoint access. Live App permission reconciliation and
deployment require separate owner authorization; source implementation does not
grant those actions.
The native review body remains sole executable PR CR authority, linked to the
canonical Issue for Task identity. Legacy native `1.0` read and `2.0` publication
remain compatible under the retained older installation/exact-operation
contract; fresh CR2 publication is refused by a qualified v4 installation.
Marked Issues use the shared `4.0` typed
envelope for new Decisions, CRs and acceptance, with retained `3.0` histories and
in-flight Request chains.

See the [producer/consumer contract and fixtures](../contracts/README.md)
for the semantic example, compatibility boundary and local checks. Cargo tests
invoke the real Node admission consumer against an intercepted mock publication.
Source implementation and CI do not deploy the Reviewer or authorize a canary.

The [Writer execution lifecycle](../controller/README.md#publication-execution-handoff-and-integration-readiness)
is separate from Reviewer publication. Successful native `REQUEST_CHANGES`
publication (including duplicate recovery) returns `structuredContent.pr_lifecycle`
with the bounded `begin-remediation` Writer action. Production routing derives
that same action from the verified current native CR and performs it during
Writer admission before automatic execution reservation or manual handoff.
Manual handoff revalidates the transition before publication. The owner
orchestration channel can also consume the returned action directly; a failed
or uncertain action stops continuation and retains same-CR/head recovery.
Reviewer performs no
Draft/Ready mutation and requires no new App permission. Recovery of the same
already-published CR is allowed after Writer drafts it; a fresh review or approval
still requires a Ready candidate.

Writer marks Ready only after durable exact-candidate publication, successful
Outcome readback and protected controller execution handoff. It revalidates and
reads back the same open PR/head and native state, retaining an idempotent pending
intent when mutation/readback fails. Mergeability, checks, base movement and
independent acceptance remain separate evidence and never control Draft/Ready.

GitHub App endpoints (`GET /app` and installation-token creation) use the short-lived App JWT. Repository endpoints use only the installation access token.

A consumer must expose only its trusted TLS terminator's exact `/mcp` location.
The consumer owns its reverse-proxy configuration. It must verify the OpenAI client certificate
chain, clear alternate caller-controlled client-certificate headers, overwrite
both `X-OpenAI-MTLS-Client-Cert` and `X-OpenAI-MTLS-Verified`, and forward to
the loopback Rust `/mcp` route. Rust requires exactly one verified marker and
one URL-encoded leaf certificate, then validates the exact SAN
`mtls.prod.connectors.openai.com` and client-auth EKU. Missing, duplicated,
malformed, spoofed, wrong-SAN, wrong-EKU, or oversized identity fails closed.
The Rust process accepts loopback or a deployment-validated private bridge
gateway (`private_gateway`, with `nexus_gateway` retained as a compatible mode
name). The network name is explicit configuration; public binds remain rejected.

The binary does not implement OAuth discovery, API-key authentication or
alternate public MCP routes. No secret or certificate material belongs in this
repository. The pinned client identity SAN above is a protocol boundary, not a
consumer hostname.
