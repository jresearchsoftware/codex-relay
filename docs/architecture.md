# Architecture

Relay connects GitHub task authority to a contained Codex worker and back to
an exact PR head. One configured Writer installation serves an explicit
repository allowlist through the same App/installation and shared settings.
Each operation process selects one configured repository before loading its
repository-bound modules. The
[consumer contract](../consumer/README.md) supplies repository identities,
workflow names, runtime paths, model and explicit effort overrides. Omitted
execution fields use the [shared contract resolver](../contracts/README.md),
with applicable native CR overrides, trusted Decisions, project defaults and
supported system defaults resolved once at admission. Consumer policy remains
owner-controlled; publication does not infer actual runtime model/effort.

This document describes the current source design. It does not establish that
an existing paired runtime was upgraded or qualified. Already-admitted native
schema-v3 or legacy attempts retain their exact compatible completion,
publication and recovery paths. A paired, qualified v4 installation gates fresh
execution and new durable Decision/Request/CR publication to the current v4 path;
unmarked Tasks and fresh v3/legacy chains require explicit migration or stop.
Reserved old Decision publication and exact old admitted-result acceptance keep
their historical contract.

Task 115 Step 1 was initially admitted through exact schema-v3 Request
6109630038 and its current installed manual handoff. Implementing the future
contract did not replace that admission or authorize a paired live runtime
upgrade. Source implementation, checks and permitted isolated-TEST qualification
remain one admitted manual Step. Installation, credentials/ingress, release,
production mutation, product merge and closure outside disposable TEST remain
separate protected permissions. Operational control inside an explicitly
isolated disposable TEST sandbox follows
[TEST Environment Authority](execution-policy.md#test-environment-authority).

## Components and flow

Tasks explicitly migrated to `Authority model: github-native-v1` use the stable
original Issue charter plus the trusted, active, non-superseded Decision chain.
The shared
[authority contract](../contracts/README.md#github-native-task-authority) defines
native identity, publisher Bot identity, version, target binding, verified
source references and explicit deterministic supersession. Decisions can amend
durable semantics while the Task is in backlog without allocating a Step.
Selected ordinary comments are contextual evidence. The trusted controller/Writer
resolves effective authority at admission and stores one immutable execution
snapshot in existing protected records. New public complete Task Requests are
unnecessary; the worker never reconstructs authority from discussion history.
Unmarked Tasks retain legacy parsing for historical verification and exact
already-admitted attempts. Fresh work on them cannot enter the qualified v4
installation until the owner explicitly migrates authority. Native schema-v3
records remain valid historical/in-flight inputs; compatibility does not permit
fresh v3 execution chains or conflicting authority paths for one launch.
The [product user manual](../packages/codex-relay/skill/references/workflow.md)
explains the current human path.

| Component | Owns | Does not own |
| --- | --- | --- |
| Consumer/owner | Task scope, model/effort policy, launch commands, deployment, merge and release decisions | Reviewer verdict identity |
| Routing controller | Event binding, one execution reservation, attempt journal and terminal handoff | New task authority or retry permission |
| Lifecycle admission | Durable automatic admission gate and full controller drain under the Writer lock | Task authority, new executions, deployment acceptance or implicit resume |
| Codex runtime/worker | Isolated task checkout, local commits, semantic result and validation claims | GitHub credentials, publication or review acceptance |
| Trusted Writer | Current authority resolution/revalidation, immutable admission snapshot/Step, imported Git objects, publication intents, PR execution Draft/Ready lifecycle and canonical Outcome | Worker execution lifecycle or Reviewer verdicts |
| External ChatGPT review/caller | Reads the diff/result, authors substantive verdict/findings and supplies structured authority records | Writer implementation identity or automatic launch authority |
| Rust Reviewer publication service | Bounded exact-head GitHub evidence reads, trusted Decision/native review/check publication and duplicate recovery; narrow enabled manual-result transport to Writer | Substantive review authorship, implementation, Step allocation, launch commands, Writer credentials, merge or closure |

The owner applies `codex-ready-auto` or `codex-ready-manual` to a canonical
Issue or remediation PR. The trusted workflow uses the configured base branch,
not PR-controlled code. For fresh execution, Writer checks native owner/event/run
identity, current v4 charter/Decision authority with any applicable v4 CR,
selected route/profile and exact branch/PR/head/base. The native ready command
does not require a public Request copy. Under the existing publication lock,
Writer binds exact source digests, route/profile, scope/boundaries, run/attempt,
lineage and admitted Step in its protected execution snapshot. It consumes the
ready event after reservation. `step-N` is a display projection in the new path,
never launch permission or an independent execution authority.

Only admission of a genuinely new execution allocates the next Step. Issue
creation, Decision/review publication, ready-label application and Actions
routing allocate none. Iterative local corrections stay in the active attempt.
A new execution after terminal BLOCKED has a new Step; same-attempt publication
recovery/replay retains its Step and cannot execute again. Actions run names use
available bounded Task/PR/route purpose without preallocating Step. New native
CRs carry exact-head findings and bounded overrides; admission projects the
resulting execution Step/title. The native review body remains CR authority,
linked to the canonical Issue, without a competing full public Request.

For schema-v4 same-CR continuation after `BLOCKED`, the native CR keeps its
immutable reviewed head A. A newer trusted Task Decision can resolve the blocker;
a fresh native owner ready event admits the next Step at exact Writer-proven B.
Writer joins the prior protected admission/journal and authentic canonical native
Writer Outcome to the same Task/PR/CR, branch/base and attempt lineage, then
verifies live refs and ancestry. Automatic provenance requires verified
`publishedHead`; manual provenance requires protected `manualSubmission` and its
original admission/claim digest. Neither arbitrary PR movement nor caller JSON
supplies B. Unknown prior attempts, stale/tampered authority or publication,
changed branch/base and replayed events fail closed. Original CR, journal and
Outcome bytes remain unchanged; no new CR is needed solely for the published
blocked head. This path does not change retained v3/legacy admission semantics.

Retained schema-v3 Request/CRs keep their original Step projection and linear
Request supersession semantics. Legacy owner new-phase preparation retains its
separate N+1 procedure. Their review repair/recovery never retroactively acquires
new admission semantics.
A legacy published record lacking its pre-publication Step anchor stops with
`LEGACY_STEP_BINDING_REQUIRED` unless its projection is already synchronized.
Explicit bounded owner migration repair preserves that review ID and Step before
replay of the original Reviewer payload; it does not launch execution.

A trusted Task Decision/effective charter or compatible complete v3 Request,
or legacy Issue-body fields, can explicitly authorize implementation continuation
from an existing task branch at one exact
starting head, binding its current PR when one exists
under the [controller contract](../controller/README.md#issue-authorized-implementation-continuation).
Admission checks the live branch ref and unique open PR, including repository,
base, Task, Step and title bindings, and pins the admitted PR number. This remains
Issue implementation with the Writer identity; it requires no Reviewer CR and
grants no remediation integration merge. New source admissions allocate a fresh
Step for each genuinely new execution; compatible v3/legacy attempts retain
their admitted Step and applicable successor-Request/N+1 rules.
Legacy fresh Issue defaults and manual handoff remain available, using existing
attempt records and services.
Writer requires the admitted starting head, or its own later published head, as
the exact previous remote ref and reobserves it before continuation's non-force
push. Ref observations and the push do not provide atomic compare-and-swap against
external ref changes.

For automatic work, the runner creates the checkout, reserves execution once,
and invokes the fixed credential-free launcher. Codex makes ordinary task
commits and returns semantic status, summary, validation claims and a blocked
reason. Within that single invocation it follows the
[progress-bounded policy](execution-policy.md).

After containment, trusted code imports only bounded regular Git object bytes
and the admitted ref into a fresh repository. It never uses the worker's Git
config, hooks, filters, index, replacement refs or alternates. Writer validates
the task chain, expected identity, safe paths and regular modes, scans all
introduced blobs (including later-deleted secrets), rechecks live authority,
and performs an ordinary non-force push.

Useful task commits can be published even if execution returned blocked or a
later readiness check failed. A successful contained result, complete worktree
observation, verified publication and observed exact PR head permit one successful terminal Outcome. After the protected controller
receipt proves execution handoff, Writer verifies native Ready for that exact
PR/head. Draft/Ready follows execution ownership; integration observations
never mutate it. Successful native Change Request publication supplies a bounded
Writer action that verifies Draft before remediation continuation. Production
routing consumes the same action from the verified current native CR during
admission, before execution reservation or ready-command consumption. Manual
handoff verifies it again before publication. A failed/uncertain transition
retains exact-CR/head lifecycle recovery without starting Codex or republishing
review authority. Same-CR BLOCKED continuation uses a separate run-ID-keyed
admission lifecycle intent at proven B; the public review-ID action remains
bound to reviewed A. Remaining uncommitted/non-ignored residue
alone yields a successful handoff with `UNCOMMITTED_WORK_REMAINS`, retained in
the terminal receipt and Outcome and emitted as a workflow warning. Codex must
first reconcile task-owned work where safe. The controller never assumes residue
is disposable or cleans, commits, publishes or retries it. Unknown execution,
incomplete collection and failed/uncertain publication or evidence retention
remain automation failures. Material warnings must inform the next owner/review
decision. Candidate-head CI, mergeability and independent exact-head review
remain separate gates. Publication completion records a READY, PENDING or
BLOCKED integration observation without a second push or infrastructure failure.
The base SHA is an observation, never permission to rebase or test a synthetic
merge. A later bounded readiness observation updates the same Outcome.

Task authority remains independent of the result artifact. Writer
publishes a typed Outcome on the unique durably bound PR, or the Issue when no
PR exists. Known PR publication uncertainty prevents Issue fallback. Contained
no-change completion needs neither an empty commit nor an artificial PR.
Genuine implementation PR acceptance is native and bound to the exact head;
it does not require an extra Task Approval. Independent no-PR acceptance uses
one trusted Issue Task Approval bound to current authority/admission, the exact
Writer Outcome and identical immutable results, including when a disposable
artifact PR was closed. Task findings are review evidence; further execution
requires owner-authorized direction and a new admission, not a duplicate public
Request. Compatible v3 acceptance still binds its unchanged Request/Outcome.

Manual routing publishes a copyable handoff and ends automatic ownership. The
owner-launched session follows its live authority. Preserve the
`MANUAL_CODEX_HANDOFF_READY` header, identifiers, thread/profile, authority
reference and full prompt bytes. Fold only the existing copyable code fence when
real GitHub expansion/copy is convenient; otherwise leave it open. Handoffs do
not allocate a future Step. Writer availability is not a manual execution
prerequisite; a qualified result publication still precedes typed acceptance.

For the new manual-result path, an enabled narrow owner-connected MCP capability
passes structured result JSON to protected Writer. It is not a generic Writer
endpoint and does not accept caller assertions of privileged capability. Writer
checks admitted manual route/Task/Step, current effective authority/admission,
exact PR/head or immutable qualification identities, target, warnings/limitations
and replay state, then publishes one canonical Writer-Bot Outcome. It does not
require a preceding owner-authored `relay-manual-result` transport comment.
Claims and verified bindings remain separate from independent proof of the
claimed operations. The worker's ordinary broker cannot invoke this capability;
Reviewer never obtains Writer private credentials. Legacy/v3 transport stays
readable and recoverable without rewriting any old owner or Bot record.

Explicitly owner-authorized standalone source PRs use native source/review
binding instead of the admitted manual-result transport. Reviewer binds the
verified owner-created PR and exact current Task sources in its native approval;
the existing owner continuation adapter verifies standalone permission,
non-admitted provenance and warning disposition before exact-head squash.
Native authorship and missing Outcomes alone do not establish these facts.
No admission, Writer Outcome, Step, service or ordinary-comment authority is
invented. Admitted executions and no-PR Task acceptance keep their original
Writer and independent acceptance requirements.

Schema-v4 result reporting verifies the original immutable admission and its
native source integrity independently of current Task semantics. Valid later
trusted Decisions are recorded as authority drift in the same Writer Outcome;
they do not rewrite the execution or imply newly required work was performed.
Execution actions retain admitted/current permission boundaries. Independent
PR or no-PR acceptance compares the delivered result with current authority,
and later Task changes invalidate stale continuation acceptance. Historical
schema-v3 currentness remains strict.

Necessary native records show human-visible English substance, findings,
boundaries, warning disposition/evidence gaps, limitations and the next
acceptance boundary before one collapsed canonical JSON fence. Safe deterministic
presentation cannot inject HTML/Markdown/links or change canonical JSON bytes.
Size/integrity/copyability constraints may require an explicitly visible JSON
fallback. Renderer versions are publication intent, not new Task authority.
Typed Reviewer publication can resume a partially published authority operation
through its original review, metadata, exact-operation SHA-bound check and
journal completion. It revalidates native identity/body/head and current Task
before resumed mutations. Lost responses or ambiguous foreign records cannot
authorize another review POST or a new Step.

## Durable state

Fresh schema-v4 source/research admissions allocate a unique monotonic Step
without a prior-Outcome dependency. The bounded Writer lock protects immutable
admission/event allocation and exact publication operations, not the model call.
Independent attempts may overlap; physical slots, checkouts, exclusive environments
and unresolved external effects retain their own holds. A verified contained
execution with a preserved collection can release its physical slot while its
publication remains pending. Full lifecycle drain still verifies all ownership
and operations. Missing/corrupt evidence is scoped by trusted repository/resource
identity; genuinely unknown ownership remains an explicit blocking conflict.

The latest successful admission owns current Step/title projections. Sibling
candidates contend at their exact ref predecessor under Writer serialization;
non-force publication, original mutation intents and readback recovery remain
binding. Late original Outcomes preserve their admission and claims without
changing a newer Step's Draft/Ready state or granting current-head acceptance.
Historical unknown manual execution stays unknown: owner withdrawal revokes future
permission and does not create a cancellation or negative-execution receipt.

| Owner | Record | Purpose |
| --- | --- | --- |
| GitHub/Git | Original Issue charter, trusted Decisions/CR, owner event/run, Step display labels, commits/ref/PR, checks, reviews and Outcome; retained v3 Requests | Authority, durable progress and acceptance truth |
| Runner | Configured primary or immutable execution-slot `paths.attemptRoot/<run-id>.json` | Execution reservation, returned result, containment and causal diagnostic; repository binding and per-run controller lock |
| Writer | Configured `paths.claimRoot/publication-v2/<run-id>.json` | Immutable effective-authority/execution snapshot and Step lineage, controller reservation/completion, manual submission binding, frozen publication body/version, verified head and recovery receipts |
| Writer | Configured `paths.claimRoot/pr-lifecycle-v1/<review-id>.json` | Exact native CR/head Draft intent and reconciliation before an execution run exists; no Task or launch authority |
| Writer | Configured `paths.claimRoot/pr-lifecycle-admission-v1/<run-id>.json` | Draft intent for a verified same-CR BLOCKED continuation at its Writer-proven starting head; retains the original review-ID receipt |
| Root lifecycle admission | Configured `paths.claimRoot/admission-v1.json` | Automatic admission phase, operation/target/configuration binding, original service activity intent and verified installed revision |
| Reviewer | Configured SQLite database | Review/check publication operation identity and deduplication/recovery |

Plural Writer configurations namespace each protected publication/PR store as
`<store>/repositories/<owner>/<repository>/<id>.json`. Runner work, journals and
diagnostics use the corresponding selected repository roots. The installation
lock, lifecycle gate and pool slot inventory stay shared across every configured
target. Singleton records keep their original paths and digests; changing the
configuration cannot hide or rebind those retained records.

Configuration is validated once and frozen. A digest accompanies admission;
another configuration cannot resume the same attempt. Configuration/state
migrations require reconciliation under the original qualified revision.

An optional managed General Runner pool has one owner-controlled physical
capacity shared across eligible repository installations. Its registrations,
services and instance state are separate from repository-specific execution
resources. General Runner and non-root Codex identities may be reused across
attempts; checkout, environment, diagnostics, journal and process lifecycles
remain attempt-specific. Protected consumer configuration supplies each
repository's runtime identity; Task/PR content cannot select it. Writer and
Reviewer remain separate. A Writer invocation selects one configured repository
while pool capacity and controller settings belong to the whole installation.

Managed capacity is an operational setting: changing only desired capacity
preserves the execution digest and fixed internal resource-slot layout.
Identity/path/security changes retain the ordinary mismatch rule. Pool Apply
uses its protected binding and mutation intents to reconcile App-derived
registration/removal and idle retirement without terminating busy attempts.
Retained recovery chooses the original evidence slot from its immutable claim
and can run through another active pool member after physical retirement.
See the [pool contract](../deploy/README.md#shared-managed-general-runner-pool).

The automatic gate and admission reservation share the root Writer lock.
Quiesce prevents new automatic Issue/CR execution while admitted controllers
finish through containment, collection, publication and durable terminal
receipts. Drain checks those existing attempt records and matching protected
runner journals; a model exit or an idle runner is insufficient. Its bounded
polls release the lock so active controllers can finish. Unknown execution,
missing containment or ambiguous publication fails closed and preserves
quiesce. The worker cannot write gate or Writer state. This lifecycle state
does not replace GitHub Task authority or add a task ledger.

Starting/reviewed head, local progress head, observed remote head and head
declared ready are distinct. A worker's claims do not establish any of these
Git facts or prove that CI passed.

## Failure and continuation

A reserved execution with no returned evidence is unknown and cannot relaunch.
A same-run replay may verify or publish an already returned execution; it
cannot repeat a model call. Progress inside one worker and Relay-level replay
are separate mechanisms.

Writer persists mutation intent before push or non-idempotent GitHub POST.
After an ambiguous push, observation of the exact candidate reconciles the
intent. Otherwise it stops. An uncertain comment/PR creation must be matched
to its exact native marker/binding before continuation. No force push or
automatic blind retry is provided.

Native publication recovery freezes intended body/renderer bytes separately
from its stable operation identity. Historical reservations without new
presentation metadata retain their original body; a newer renderer cannot
republish a retained result or change its native body hash. Direct manual-result
delivery shares these immutable target/replay barriers and cannot authorize Git,
execution, review, merge or deployment operations.

Effective Task closure starts with the original charter and applies any trusted,
explicitly owner-authorized Task Decision changing `keep-open` or
`close-authorized`. A native PR CR cannot change it. Trusted owner continuation
re-reads current authority/acceptance, exact head/checks and completion evidence;
only verified Task completion with no remaining work, applicable qualification
and no hold/protected boundary permits conditional authorized closure. It must
surface a complete Task still held open without a genuine remaining condition
for owner disposition. An already-authorized acceptance-dependent closure does
not require another Decision, and an accepted Step is not itself Task completion.
Neither Reviewer nor worker merges or closes Issues.

[Publication recovery](../controller/README.md#writer-publication-recovery)
is a separate owner-authorized operation bound to the original attempt,
authority digest, previous/candidate heads and a fresh native authorization
comment. It never launches Codex. Unknown/uncontained execution cannot be
converted into success by recovering publication.

An additional, opt-in [terminal prepublication recovery](../controller/README.md#terminal-prepublication-recovery)
handles a native Task attempt that ended BLOCKED during collection, before any
collection receipt or publication intent. The fixed root Writer reads the
original protected journal and observes retained bytes only after a fresh native
owner authorization binds the exact attempt, original schema-v4 authority and
admission (or retained schema-v3 Request), candidate, configuration,
Writer identity and historical terminal evidence. Successful contained execution
is mandatory. The original native Writer identity, canonical Outcome binding,
terminal marker and persisted body digest survive the rendering cutover;
accepting a human-first header cannot relax that provenance. The ordinary
collector continues using its separate identity;
neither path changes worker permissions. Trusted Git observes a collector-owned
snapshot of readable worktree bytes rather than opening worker paths through
Git. Unreadable non-ignored bytes and incomplete observations fail closed.

The new recovery reservation and receipt live in the original Writer attempt
under its existing root lock. One non-force push requires the exact previous
remote head and the ordinary isolated object importer and validation gates.
The original journal, blocked Outcome and controller receipt remain unchanged;
a separately bound successor Outcome and recovery handoff receipt record the
result. Admission drain treats any unfinished recovery as unknown even if the
historic BLOCKED controller receipt was complete. No terminal replay launches
this operation. An ambiguous publication cannot authorize another push.
Installed root helper access, actual UID separation and containment of preserved
attempts require separately admitted host qualification and installation.

One exact admitted-base integration merge is allowed for applicable remediation
under the [Git reconciliation contract](../controller/README.md#reviewed-base-reconciliation).
That constraint protects commit provenance; it does not limit the number of
local diagnose/fix/validate iterations.

## Trust and deployment

The consumer supplies runner policy, App/ingress references and owner lifecycle
decisions and reviews the installed workflow projection. Relay owns canonical
workflow templates, deterministic projection and workflow concurrency, as well
as the root Writer
lock, fixed wrappers/sudo policy, worker isolation and deployment lifecycle.
Caller JSON may select a configured repository target; it cannot select a
credential, executable, configuration or unconfigured repository.
Keep root-owned configuration and separate consumer state outside worker-writable
paths. Never execute PR/fork-controlled code on a persistent privileged runner.

Default routing and publication recovery share the existing control group with native
`queue: max` and cancellation disabled. This preserves up to 100 waiting control
invocations while keeping SERIAL execution; the current one-general-runner
layout supplies no parallel speedup. See [control scheduling](concurrency-scheduling.md)
for runtime bounds, authority while waiting and the explicit NOT QUALIFIED
parallel/many-repository boundary. Root locks and lifecycle drain remain intact.

The optional parallel source candidate keeps one immutable consumer
configuration while resolving isolated runner/model identities and resource
paths from a protected execution-slot binding. Admission rejects occupied slots;
root drain reads each retained journal through the original protected envelope.
Per-run kernel locks exclude duplicate controller inference, and a short store
lock serializes diagnostic retention. Separate repository installations keep
their own namespaces and Writer locks. A candidate parallel workflow ABI and
finite runner pool do not prove actual worker overlap or external access policy.
Additional slots reuse the public registration and activation phases with an
allowlisted slot selector. Inventory, upgrade activity preservation and clean
reinstall use the same finite topology; drain retains every original attempt
binding. Ordinary publication recovery selects the original slot and shares
the controller's per-run journal lock. Source support still requires installed
identity/containment proof and actual automatic worker overlap before a host
can be considered qualified for parallel operation.

Relay owns the [deployment interface](../deploy/README.md), source/build/install
mechanics, layout, wrappers, users/services, upgrade/rollback and verification.
Consumers own configuration, secret references, target properties, policy and
channel/revision selection. Ansible is the configured target execution transport
behind the public deployment entrypoint, including inventory, guards and protected
helpers; internal playbooks are not a consumer API. Target-local Python owns pool
reconciliation and GitHub App authorization using the existing protected target PEM.
Keys and installation/runner tokens stay on the target; only bounded nonsecret
receipts return to the controller. Qualified SSH and Debian local connections
preserve their respective host identity and root authorization checks.
A selector resolves once and the exact installed identity
is reported. Selecting a version does not grant deployment authority.

Product source revision, installed product revision, consumer authority revision
and latest accepted product revision are independent. Routing and recovery use
the exact installed revision with the reviewed workflow compatibility contract; advancing
either repository does not upgrade or invalidate it. An owner selects one exact
accepted target, reviews any changed generated workflow bytes, and uses the public upgrade
primitive to apply and verify that same target under the existing host lock.
The owner lifecycle coordinator quiesces and drains automatic admission before
applying that primitive. Registered runners remain online. Only explicit
same-operation verification of the installed revision permits resume; a
restart, failed or unknown transition retains quiesce and recovery evidence.
Graceful stop retains quiesced admission without stopping registered runners.
Manual handoff and publication-only recovery keep their existing authority.
Without authoritative latest-release information no update note is
emitted, and availability of a newer revision is never itself a warning or gate.

Fresh bootstrap derives workflow proposals from that exact accepted source and
one durable owner configuration. A missing projection is an explicit consumer
review/publication transition in the supported bootstrap UX, not a separate
pre-existing installation input. Read-only inventory distinguishes reusable
protected state, missing ephemeral inputs, invalid state and unavailable admin
verification. An authorized clean reinstall may retire a proven pre-current
runtime while retaining runner registrations, protected credentials and durable
publication/review state. Retirement, fresh apply and post-check share the host
deployment lock; uncertain transitions retain recovery evidence. Service
activation and external consumer qualification keep their separate authority.

The [Reviewer](../reviewer/README.md) is a narrow MCP HTTP service behind a
trusted mTLS terminator. It verifies forwarded client identity and binds every
GitHub request, review and check to an explicitly selected configured repository,
the shared App/installation and the exact head.
Writer and Reviewer credentials are separate. Raw credentials and diagnostic
streams never belong in an Outcome.

Current MCP tool schemas advertise v4 authority inputs and the separately enabled
manual Writer transport. The caller must stop if its connected App lacks a
required current tool/schema; server-side installed capability gates reject
unsupported publication. Neither side substitutes a legacy/v3 launch or
publication path. Server checks cannot establish what an inaccessible App or
stale client-side tool cache exposes. See the
[capability contract](../reviewer/README.md#current-protocol-capabilities).

The evidence reader uses a read-only installation token and binds applicable
execution checks through exact-head Writer Outcomes on the reviewed PR and
canonical linked Issue. Mandatory completeness covers execution-time warnings
available through supported check/job/runtime APIs; unavailable, denied or
truncated required evidence prevents an absence claim. UI-only service-level or
pre-execution annotations/platform banners are explicitly excluded from that
automated contract and do not alone block review. No HTML or browser-session
fallback is used. Supported API completeness cannot prove absence of UI-only
warnings or replace independent warning disposition. See the
[evidence contract and API limitation](../reviewer/README.md).

Local qualification tests real modules/handlers against synthetic Git and
loopback GitHub. It does not test a consumer's installed wrappers, reverse proxy,
GitHub App permissions, paid model execution or production deployment.

The [integration reference](integration-reference.md) specifies launcher/sudo
environment recreation, public dogfood trust assumptions, configuration, App
permissions and bounded scan-policy differences. The Node directories and the
shared Rust/Node CR schema form one qualified product tree, not separate packages.
