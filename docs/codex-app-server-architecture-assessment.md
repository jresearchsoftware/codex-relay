# Governed Codex execution: architecture assessment

Task #42, Step 1 — source-only research, 2026-10-11.

Step 1 is preserved below as historical evidence. The
[Step 2 addendum](#step-2-addendum-persistent-execution-service) evaluates a warm
service with fresh execution threads against a newer, explicitly pinned baseline.

## Recommendation and decision boundary

**Retain governed one-shot `codex exec` for the accepted runtime. Do not migrate
to a shared persistent daemon on the evidence available here.** If the owner
chooses further investigation, the smallest credible candidate is a bounded
hybrid: one task-scoped app-server process inside one admitted execution, with
Relay retaining admission, workspace ownership, containment, diagnostics,
collection and publication. Native conversation machinery could be reused
without making a native session the authority for a Task.

This is an architectural recommendation, not an owner decision or an
implementation admission. No runtime, deployment, service, credential, workflow
or authority contract changes accompany this report. Issue #42 remains
`keep-open` through the owner choice and any separately authorized migration
and qualification, or an explicit no-migration disposition. Report acceptance
alone does not close it or launch another Task.

The strongest prospective benefit is interaction during long work: structured
progress and a conversational continuation surface. The weakest justification
is eliminating all Relay lifecycle plumbing. The accepted runtime already
obtains native identity and usage, and its durability, process containment and
trusted Git import protect facts that a conversation service cannot establish.
Persistence introduces additional recovery and retention obligations before
those prospective benefits become dependable.

## Evidence, baseline and limits

All Relay observations below refer to the admitted accepted source revision
`66870385a60a787150c9b221bf830c013b2816e7`. The initial checkout was clean on
`codex/task-42-step-1` at that exact SHA. No fetch, rebase or merge with parallel
Task #115 / PR #118 was performed. Supplied trusted Task authority governs this
research; public backlog discussion is context only.

Evidence classes are deliberately distinct:

| Class | Meaning in this report |
| --- | --- |
| V — locally verified | Checkout/tool availability, source reads, and the local checks described below. |
| S — accepted source | Behavior encoded in the pinned Relay implementation/contracts, including recorded prior CLI qualification. A source read does not rerun that qualification or prove a live installation. |
| D — official documentation | Public OpenAI documentation fetched on 2026-10-11. These are moving pages, not proof of the behavior of the accepted 0.160.0 binary. |
| A — analysis | Proposed architecture, threat reasoning, cost estimates by formula and hypothetical failure walkthroughs. No simulated trace is presented as native observation. |
| U — unknown | Unmeasured or unavailable behavior requiring a later, separately admitted experiment or owner decision. |

No native app-server protocol probe, model call, daemon restart, credential read,
session connection or service activation was performed. `codex` was absent
from the worker's executable search path. Installing or downloading an executable
to manufacture that capability was outside this admission. No report fixture is
needed: inventing a mock server would establish the mock's semantics, not native
crash recovery. The scenario matrix is analysis; **no failure simulation was
executed**.

### Pinned Relay evidence

The following navigation links refer to repository files. The
[exact accepted tree](https://github.com/jresearchsoftware/codex-relay/tree/66870385a60a787150c9b221bf830c013b2816e7)
is the comparison authority if those files later change.

| ID | Source inspected at the pinned revision | Relevant fact or limit (S) |
| --- | --- | --- |
| R1 | [Architecture](architecture.md), [typed Task authority](../contracts/README.md#github-native-task-authority) | A complete trusted Request is the execution snapshot. Controller reservation precedes execution; GitHub/Git remain authority and acceptance truth. Native conversation state cannot supersede them. |
| R2 | [Runtime implementation](../runtime/src/codex-runtime.mjs), [fixed launcher template](../deploy/ansible/roles/relay_codex_runtime/templates/relay-codex-launcher.mjs.j2) | The fixed launcher receives bounded input/schema paths and exact profile; recreates task-local HOME/CODEX_HOME/XDG/temp; invokes `exec --json` with workspace-write, `.git` writable and network enabled. Inherited environment and Git credential mechanisms are constrained. |
| R3 | [CLI integration](codex/cli-integration.md), [official-release qualifier source](../deploy/ansible/tests/qualify_codex_cli.py) | Accepted CLI baseline is 0.160.0. Recorded loopback qualification covers native JSONL, schema transmission, invalid semantic output, failures, policy and usage. This Step did not run the real CLI qualifier. |
| R4 | [Usage parser](../controller/src/codex-usage.mjs), [runtime semantic parser](../runtime/src/codex-runtime.mjs) | One unambiguous native session-total usage snapshot is accepted; malformed, truncated, failed or ambiguous streams yield unavailable usage. Semantic output is independently normalized; native identity is not extracted from prose. |
| R5 | [Runtime durability contract](../runtime/README.md#durable-diagnostics-and-sandbox-finalization), [finalization implementation](../runtime/src/runtime-finalization.mjs), [diagnostic retention](../controller/README.md#runtime-diagnostic-retention) | Independent diagnostic reservation precedes launch. The dispatcher owns process-group containment; sandbox cleanup requires durable evidence and captured device/inode identity. Existing sandboxes are retained rather than adopted. |
| R6 | [Writer handoff](../controller/README.md#issue-publication-and-worker-handoff), [failure and continuation](architecture.md#failure-and-continuation) | Trusted code imports bounded Git object bytes into a fresh repository, validates the chain/paths/modes and scans every introduced blob. Writer revalidates live authority and publishes without force. Unknown execution cannot relaunch; publication recovery does not call the model. |
| R7 | [Admission and drain](../controller/README.md#lifecycle-admission-and-drain) | Drain covers the entire controller through containment, collection, publication and receipts. A model exit or an idle runner is insufficient. Same-operation installed verification and explicit resume retain separate authority. |
| R8 | [Validation](../CONTRIBUTING.md#local-validation), [warning disposition](execution-policy.md#execution-warning-disposition), [proportional controls](execution-policy.md#proportional-controls-and-operator-usability) | Local checks, native exact-head evidence, independent judgment and installed proof have distinct scopes. New cost-bearing controls need canonical authorization; existing sufficient proof should be reused. |

### Native capability digest

These compact claims are D, not locally observed native behavior:

- App-server documents bidirectional JSON-RPC over JSONL stdio, version-specific
  generated schemas, initialization and experimental opt-in. Thread start,
  resume, fork and read expose conversation identity/status; `sessionId` denotes
  the session-tree root. Turn/item events, `thread/status/changed`,
  `thread/tokenUsage/updated` and `contextCompaction` provide structured signals.
  `turn/interrupt` cancels; `turn/completed` can mean completed, failed or
  interrupted. Per-turn `outputSchema` does not persist. `thread/shellCommand`
  and experimental `process/*` run outside the thread sandbox. WebSocket
  transport is experimental; the page also warns that the app-server command
  is unsupported for production workloads. [App-server protocol](https://learn.chatgpt.com/docs/app-server).
- CLI reference describes app-server as development/debugging and subject to
  change. `remote-control start/stop` manages a local daemon for remote-control
  workflows; it is a distinct integration surface, not a substitute for a local
  protocol client. It does not establish Relay drain or crash-safe restart
  semantics. [Developer commands](https://learn.chatgpt.com/docs/developer-commands).
- One-shot execution itself supports JSON events, structured output and explicit
  session resumption. Process persistence is therefore not a prerequisite for
  native conversation persistence. [Non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode).
- Configuration exposes separate log and SQLite state locations, transcript
  persistence and raw-prompt telemetry settings. Their effective placement and
  permissions need verification for the exact binary/configuration.
  [Configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).
- Native sandboxing and approval policy are separate controls; defaults and
  execution surfaces vary. They do not establish Relay's installed Unix
  identity/containment boundary. [Agent approvals and security](https://learn.chatgpt.com/docs/agent-approvals-security).
- Native app worktrees share Git metadata with their source repository and
  provide a chat/code handoff workflow. That convenience is not a trusted
  worker-object import boundary. [Worktrees](https://learn.chatgpt.com/docs/environments/git-worktrees).

For reproducibility, the fetched Markdown bytes for the first four pages had
the following SHA-256 values. These identify consulted content; a hash without
an archived copy does not make a moving page retrievable or version-qualified.
Full documentation copies were kept only in disposable temporary storage.

| Page (`.md` variant of the linked URL) | SHA-256 |
| --- | --- |
| App-server | `14c29f997cffff66125e710c1746425c53262eb4e636eb0bbcd5c8b4ec7e4464` |
| Developer commands | `f6c6838212b1856da0facfe5d17a04fa6d1f0b7a37c2de1fcd49ec93d4ff83bd` |
| Non-interactive mode | `c83fe9259825a206d1d4f7a0ac669e5697d270ce2bebd28c5d36ad829c9a2a08` |
| Configuration reference | `ff9a198c4e39f191ec6d41141b3e867005a82dc1937c228b12197208585cba0b` |

There is no generated schema or executable result from 0.160.0 for app-server
in this evidence set. In particular, the moving documentation's methods,
identity shape and maturity labels must not be projected backward onto the
pinned binary. Successful `exec` qualification does not qualify app-server.

## Three alternatives and lifecycle ownership

**O — accepted one-shot:** one governed process invocation per admitted
execution. Codex performs its internal agent work; Relay contains it and hands
local progress to Writer. Native history normally resides in the disposable
sandbox and is removed on successful finalization. The accepted adapter does
not implement general pause/resume or incremental publication.

**P — persistent app-server:** a supervised long-lived service keeps sessions
between executions and accepts clients over a reconnectable local endpoint.
Evaluate a per-task instance as the safer variant; a shared consumer-wide
instance adds cross-task exposure and a shared failure domain. Neither variant
has been qualified here. Remote-control daemon commands are not assumed to
provide the required supervisor protocol.

**H — bounded hybrid:** the existing admitted worker owns one private app-server
child over stdio, one checkout and one task-local home. It can use multiple
inner turns within that admission if later authority permits. It ends and is
contained before ordinary collection. By default it retains no native session
across completed executions. Cross-admission resume would be a separate,
explicit extension; H must not quietly acquire P's persistent storage contract.

P and H in the following comparison are proposed designs (A), conditional on
exact-version proof of the D capabilities. They are not claims about an
installed server.

| Concern | O — current source behavior (S) | P — design consequence (A/U) | H — design consequence (A/U) |
| --- | --- | --- | --- |
| Admission and execution ownership | Controller reserves once, launches a fixed worker and tracks full handoff. | Supervisor/server health cannot grant admission. Each new turn or continuation needs binding to an authorized execution; stale clients must lose mutation access. | Keep the reservation and fixed entrypoint. Inner-turn policy belongs to the admitted execution, not a native Goal or automatic retry loop. |
| Session and thread isolation | Fresh task-local home bounds native state to the attempt. Native thread supplies correlation, not Task authority. | Bind repository, Task, Request digest, attempt, native thread and workspace. A thread ID is an identifier, not a capability or tenant ACL. A shared UID/home is not isolation. | One task/checkout/home/client per child avoids cross-task routing. Keep native thread, session-tree root and turn identities distinct if supported. |
| Exact-head, Writer and Reviewer | Contain, import object bytes, scan, revalidate and publish. Independent acceptance binds exact candidate. | Long-lived access to a reviewed checkout risks post-review writes. Detach and establish no remaining writers before capture; Writer and Reviewer remain separate. | Terminate/reap all writers before collection, then use the existing importer and exact-head flow. No native review result is independent Relay acceptance. |
| Progress and usage | JSONL and five native counters already exist; unavailable values stay explicit. Capture is bounded and terminal-oriented. | Translate live events into attempt-local observations, account for reconnect gaps and multi-turn attribution, and protect raw output. | Reuse structured events while the child is alive. Keep bounded terminal semantic normalization and protected diagnostics. |
| Owner pause/resume | Current adapter is not a durable suspension interface. Killing a process is not safe pause. | Need a settled mutation frontier, retained workspace/state and revalidated owner continuation. A dormant session still consumes retention/credential budget. | Cooperative stop at a safe inner boundary is plausible; durable cross-admission suspension is excluded from the minimal variant. |
| Compaction and crash recovery | Relay durability is outside the conversation; unknown execution cannot relaunch. | History may help reasoning, but cannot prove filesystem/tool effects or restore lost authority. Restart recovery needs containment and effect reconciliation. | Compaction stays inside the child. A crash retains diagnostics/progress under existing rules; no automatic new child to replay an uncertain turn. |
| Multi-task contention | Separate checkouts/attempts plus existing admission/concurrency policy. | Shared service adds scheduling, noisy-neighbor, catalog/config and event-routing interference. Per-task services reduce coupling but reduce pooling benefit. | Maintain current scheduling. Subagents remain within one admitted permission and containment domain; no fan-out into additional Relay attempts. |
| Git and workspace handling | Relay creates checkout and imports only bounded object bytes, never model-modified Git metadata. | Session affinity must not bypass starting-head checks, import safety or branch locks. Native worktree ownership would materially change the trust boundary. | Pass the Relay checkout explicitly. Native Git metadata and diff events remain evidence, not trusted Git input. |
| Security and protected data | Fixed runtime UID/entrypoint, task-local directories, constrained environment and separate Writer/Reviewer credentials. | Longer-lived inference credentials, rollouts, prompts, tool output and IPC become retained sensitive assets. Service-level operations may exceed a thread's policy. | Keep the fixed credential boundary and private pipes. A bounded adapter exposes only admitted operations; native state remains worker-controlled evidence. |
| Version compatibility | Exact 0.160.0 CLI deployment and bounded recorded qualifier. | Need exact client/schema/server/storage compatibility and a drainable supervisor; no moving-latest dependency. | Pin the child and adapter together. Smaller transport surface, but still a new protocol qualification obligation. |
| Migration and rollback | Accepted path remains available. | On-disk state upgrades can strand sessions; downgrade compatibility is unknown. Never replay to make rollback look successful. | Route only new, separately admitted attempts to H. Fall back before any turn submission, or after proven containment and reconciled effects under fresh authority. |
| Operator burden and cost | Per-run startup and duplicate context preparation; bounded disposal/retention. | Potential startup amortization, offset by idle resources, storage, renewal, supervision, incident handling and shared outages. | Less daemon administration; still an adapter and its tests, and usually still one startup per admission. Benefit must come from interaction quality rather than an assumed latency win. |

### Responsibilities that may move, and those that remain

Codex already owns model/tool orchestration and context management inside O.
Moving to P or H may expose more of that machinery through a direct protocol;
it does not eliminate duplicated functionality merely by renaming the process.
The potentially reusable implementation area is conversation loading,
compaction and structured progress/turn interaction. Even there, Relay still
needs a bounded adapter and terminal semantic contract.

Relay must retain R1/R5/R6/R7 responsibilities: live Task authority, one
reservation, admission/drain, configured identity and workspace, durable
pre-mutation diagnostics, timeouts, independent containment, safe cleanup,
exact Git facts, trusted object import and publication. Native completion
cannot assert that the worker stopped, a commit is publishable, checks passed,
or review accepted it. An app-server client must never receive Writer or
Reviewer GitHub credentials or a path to their protected state.

The accounting boundary should remain the existing attempt receipt and one
Writer Outcome. If later admitted, add only the native correlation and bounded
submission/terminal observations necessary to those records. A second Task
ledger, workflow engine or daemon-controlled authority store has no demonstrated
benefit. Conversation storage is a reasoning cache with sensitive contents,
not another canonical Request.

## Continuation, observability and upgrades

### Same conversation does not mean same authorization

For any future resume, re-read mutable canonical authority, current branch/base
and exact starting head, admitted profile/configuration and prior containment
evidence. Preserve useful Git progress and selected evidence even if native
history is missing. Never find a substitute session by a human title, latest
timestamp or “last session.” Treat corrupted/missing native state as an
explicit gap; it must not license a model retry.

A safe pause design would distinguish an interrupt request, a native terminal
observation, containment of background/subagent/tool processes, preservation
of useful commits/evidence, and an authorized continuation. An interrupt can
arrive after a command has changed bytes or affected an external system.
Waiting for a conversational status alone cannot establish a clean pause.
Holding an entire controller reservation across days of owner deliberation
would also obstruct R7 drain; changing that behavior needs an explicit
suspension contract, not a daemon timer.

Compaction can reduce context cost but may omit stale-versus-current authority
details or recovery facts. After compaction or restart, supply current trusted
Request context and independently observed execution/Git facts. A summary is
useful reasoning input, never proof that the earlier attempt had no side
effects. Host interruption and storage corruption remain fail-closed when that
frontier is unknown. Current evidence does **not** establish reliable
same-session continuation across crash/upgrade for #20 or #22.

### Event translation rather than a new status authority

The D capability digest suggests a useful adapter for #19. Its proposed rules
are: correlate events to the admitted attempt and native turn; show an unknown
or stale observation when the transport is lost; bound/redact output; preserve
terminal evidence separately from transient progress. A heartbeat, idle thread
or last item cannot be interpreted as successful handoff. Operator-visible
pause, waiting and progress semantics still need #19/#20/#22 authority.

R4's one-shot usage assumptions cannot simply be reused for multi-turn history.
A future adapter must prove whether native values are cumulative, per-turn or
replayed, their child-agent scope and their behavior after resume. Do not add
snapshots, subtract totals across an unproven reset, count cached/reasoning
subsets twice or equate tokens with billed costs. Missing attribution stays
`UNAVAILABLE`. Catalog/request profile values are not authoritative actual
execution values; native evidence must establish any actual-model/effort claim.
Persist only the safe projection needed by the original attempt/Outcome.

### Daemon lifecycle subordinate to Relay lifecycle

R7 already provides Relay-level quiesce/drain/apply/verify/resume. P would need
its service/client/turn inventory incorporated into that existing invariant,
not a parallel drain result. An idle server or stopped native daemon cannot
prove collection/publication complete. Unknown active clients or descendants
must retain quiesce. An automatic daemon restart cannot reopen admission or
restart a reserved model turn.

For a later accepted upgrade, the proposed ordering is: quiesce new admission;
let admitted work finish its complete handoff or enter explicitly authorized
suspension; establish containment and no unresolved publication; preserve the
necessary native state; apply one exact accepted version; verify the
client/server/state combination and original service intent; explicitly resume
Relay admission. Any uncertainty retains the current recovery boundary. There
is no demonstrated native crash-safe drain/update contract to replace it.
H can more easily finish/reap its child at the current terminal boundary,
reducing the service inventory that must survive an upgrade.

## Scenario and failure matrix

These are A walkthroughs, with U native details called out. They prescribe no
new runtime behavior in this Step. “Contain” always includes descendants;
“publish” always means trusted Writer validation/import and live revalidation.

| Scenario / failure frontier | O — accepted path or limitation | P — necessary handling / added hazard | H — necessary handling / added hazard |
| --- | --- | --- | --- |
| Short report completes with valid semantic JSON and one useful commit | Normalize result, contain, collect and publish; CI/review remain separate. | Bind terminal turn to reservation; detach all mutation access before collection. Service surviving the turn is an extra frontier. | Reap child and use the normal handoff. No benefit claim without measuring added protocol overhead. |
| Three-hour change crosses compaction, then owner asks for clarification | Git/diagnostics can preserve work; ordinary final result/handoff applies. General durable suspension is absent. | Preserve thread/workspace and settle effects; fresh owner continuation must resolve changed authority. History fidelity across restart is U. | Inner-turn clarification could fit one admission; waiting beyond its bounds requires the separately designed suspension path. |
| Client writes a turn request; connection dies before acknowledgement | Lost return after reservation remains unknown; cannot launch again. | Request may have executed. Read only bound state/effect evidence and contain; do not resend on timeout. Request IDs alone are not a proven durable idempotency key. | Same uncertainty despite private pipes. Do not replace the child and send the input again. |
| Client disappears but server still runs a shell tool or child agent | Dispatcher owns process group and final containment. | Lost client is not cancellation. Need independently observable task containment; shared-service kill could disrupt other Tasks. | Outer timeout/containment remains decisive; closing stdio is not assumed to reap descendants. |
| Server crashes after committing, before terminal result | Preserve local commits/diagnostics; unknown execution remains a boundary. | Reconcile native record, actual Git and tool effects. A plausible final transcript is insufficient. Restart is observation/recovery, not automatic permission to continue. | Preserve progress under current rules. No terminal result means no successful execution claim, even if useful commits can later be safely handed off. |
| Host loses power during compaction/state write | External capsule/Git facts may survive; missing durability/containment evidence remains unknown. | Torn native state or wrong recovery frontier is U. Preserve bytes; never “repair” by silently truncating history and replaying tools. | Disposable state limits cross-attempt dependence; controller still needs the original attempt evidence before a new execution. |
| Tool changes an external system just before interrupt | Unknown external mutation is a stop condition. | Neither resume nor fork can undo the effect. Require original effect evidence/owner disposition, not repeated mutation to regain context. | Same rule; no app-server probe or fallback may repeat the tool automatically. |
| Missing/malformed terminal JSON, event gap or exhausted output bound | Local normalizer/capture fails; retain available evidence, usage may be unavailable. | Persist gaps distinctly. Native successful status cannot fabricate semantic output or lost diagnostics. | Keep the same fail-closed normalizer and bounded capture; richer streaming does not waive limits. |
| Two Tasks contend for one daemon or one branch | Current attempt/checkouts and concurrency mechanisms apply. | Reject cross-binding and serialize owned workspace mutations. Shared routing bugs can expose prompts/state; concurrent branch publication still belongs to Writer. | Separate child/home/checkout for each permitted attempt; preserve existing scheduler rather than adding a pool. |
| Authority revoked, exact remote head changes, or old client reconnects | Writer/admission revalidation stops unsafe continuation/publication. | Invalidate mutation routing until fresh authorization; session affinity cannot override Git conflict or scope changes. | Current admission controls remain; inner progress cannot authorize a new Request or integration merge. |
| Inference credential expires while waiting for owner | Current launcher has per-attempt lifetime; authorization/access failures are recorded. | Renewal/rotation and stale in-memory secret handling become operational obligations. A session surviving authentication failure is not an access proof. | Keep credential handling inside the established fixed boundary; no client-side login or owner credential fallback. |
| Upgrade requested while worker done but Writer push is ambiguous | R7 drain stays quiesced; original publication recovery is separate. | Daemon reports idle but Relay is not drained. Do not update/retry until the original intent is reconciled. | A reaped child simplifies process inventory, but does not resolve publication ambiguity. |
| New binary cannot read old state; rollback requested | Exact accepted one-shot path remains available for new authorized attempts. | Preserve old bytes/version, prove no running effects, and use supported compatibility or explicit owner recovery. Native state downgrade safety is U. | Before submission, use O if routing permits. After submission, require containment/effect reconciliation and fresh authority; no transparent duplicate attempt. |
| #21 asks for an intermediate durable commit while tools remain active | Current importer expects containment; terminal safe progress is publishable. | Native commit notifications do not make a race-free snapshot. Separately qualify a bounded frozen snapshot/import boundary, not trusted Git on live worker metadata. | Same #21 requirement. Do not introduce concurrent collection merely because an inner turn ends. |
| #115 later advances accepted source/contracts under the report PR | Pinned assessment remains historical evidence; changed acceptance/base needs explicit reconciliation. | Future adapter must qualify against that accepted version; no speculative adoption now. | Report-only conflict can be reviewed and resolved under new authority; no automatic rebase, merge or force push. |

The uncertain-submission row is the decisive recovery distinction. A native
request acknowledgement, terminal record and filesystem effects can be lost at
different times. The consulted evidence does not establish exactly-once tool
effects, durable event replay or transactional request deduplication. The
cheapest safe choice is to preserve the original attempt and stop on unresolved
mutation, as R6 already requires, rather than add an unproven retry mechanism.

## Security, Git and operator tradeoffs

P lengthens the life of runtime credentials and untrusted native history.
Prompts and tool outputs can contain private repository material even when no
recognizable secret marker occurs. A common home/UID also allows a compromised
session or routing error to reach another Task's retained material. Per-thread
sandbox fields do not prove isolation of the server itself, IPC, config,
plugins, background tools or state storage.

For any later pilot, start from R2/R5 rather than the owner's desktop setup.
Keep service/client files and state within explicitly qualified locations;
verify actual UID/GID, modes, symlink/mount behavior and cleanup ownership.
Do not place privileged authority/diagnostic records in a worker-writable home.
Sensitive native history remains lower-trust input and must not cross to
GitHub or trusted execution as raw rollout/config bytes. State-database files,
journals, logs and caches must be inventoried rather than assuming CODEX_HOME
alone contains everything. Retention/disposal of persistent data would require
a new authorized lifecycle contract: R5's current successful sandbox deletion
cannot safely coexist with an untracked live session.

A fixed adapter is the proposed minimum privilege boundary. It maps a trusted
admitted envelope to necessary protocol calls and does not accept arbitrary
RPC, cwd, executable, account, permissions or tool settings from the model.
Avoid service-level shell/process control and remote listeners in the minimal
pilot; keep its experimental API disabled unless a specifically necessary
surface is separately accepted. An approval request unsupported by admission
must stop, not be automatically granted to keep a session alive. A required
feature available only experimentally is an unresolved owner decision.

For Git, a conversation/thread workspace hint or native diff cannot substitute
for independently observed SHAs. Reusing native app worktrees would couple
mutable worker Git metadata to another checkout and add a different handoff
workflow. Preserve Relay-owned isolated repositories and R6's fresh trusted
object importer. A session must lose all write access to the capture that
becomes the exact reviewed candidate. Subsequent authorized continuation
produces a new candidate whose acceptance must be assessed independently.

The following proposed controls are an R8 proportionality assessment, not
new mandatory gates:

| Concrete risk | Existing protection | Cheapest credible choice and cost |
| --- | --- | --- |
| A shared service exposes Task A's credential/history/workspace to Task B | O already creates separate attempt-local state and contains processes. | Retain O; if studying native interaction, use H's private child/home. This forgoes pooled startup savings but avoids a new shared tenancy/ACL service. |
| Client can invoke an out-of-scope process operation using the server UID | Fixed launcher currently restricts arguments and credential/environment recreation. | Extend the same fixed boundary with a small trusted adapter for H, under future authority. Costs protocol maintenance; cheaper than exposing all RPC then layering a general permission engine over it. |
| Timeout followed by resend repeats a tool effect | Existing reservation and unknown-execution stop prohibit blind retry. | Reuse that stop and original attempt evidence. Owner recovery may be slower, but avoids a distributed deduplication ledger and false exactly-once claims. |
| Native state/version ambiguity loses progress or secrets | Git commits, protected diagnostics and exact release selection already exist. | Preserve those proofs and retain native bytes only when useful and explicitly admitted. Accept loss of conversational convenience rather than making every Task operate a new backup service. |

No extra operator command, state machine or approval loop is proposed for the
research result. If a pilot creates frequent stuck-session work, forced manual
reconciliation, special filesystem prerequisites or pressure to bypass the
governed entrypoint, that friction counts against migration even if the normal
event path works.

## Ongoing cost and benefit model

No latency, memory, disk, model-token saving or price was measured. Numeric
performance promises would be invented. Compare with the same model/effort,
task mix, concurrency and accepted security boundaries in a later experiment.

For `N` admissions and `T` authorized turns, an illustrative local runtime cost
model (A) is:

- O: `N × process startup + context preparation + active execution + bounded
  finalization`.
- P: `service startup + idle resident cost × lifetime + T × protocol cost +
  active execution + retained storage + supervisor/recovery/upgrade work`.
- H: `N × process startup + T × protocol cost + active execution + bounded
  finalization + adapter maintenance`.

Persistence can amortize startup only if reuse outweighs idle and operational
cost. It does not establish lower provider usage: long history, compaction,
cache behavior and child-agent consumption can change either way. H intentionally
keeps per-admission startup, so its acceptance case should be better control or
observability with bounded complexity. O can receive observability improvements
without waiting for migration.

A later comparison should measure cold/warm time to first useful event,
end-to-end handoff time, idle/active RSS and CPU, bytes retained per task, token
attribution completeness, disconnect recovery effort and operator minutes per
incident/upgrade. Reuse existing diagnostics/check artifacts; no new telemetry
platform is needed merely to compare the alternatives. Owner-selected workload
and tolerances should decide whether the improvement is material. If there is
no meaningful gain beyond already available exec signals, prefer O.

## Relationship to backlog and parallel development

| Task | Connection and boundary |
| --- | --- |
| [#17](https://github.com/jresearchsoftware/codex-relay/issues/17) | Historical long-session/compaction motivation, as identified by the #42 charter. It supplies neither a native durability proof nor the architecture decision. No historical rollout/session was accessed. |
| [#19](https://github.com/jresearchsoftware/codex-relay/issues/19) | Progress observability remains an operator requirement. D signals are possible inputs; the comparison must include extending O before accepting daemon cost. No status/UI semantics are implemented here. |
| [#20](https://github.com/jresearchsoftware/codex-relay/issues/20) | Owner pause/resume needs explicit authority and a settled mutation frontier. A native session may retain reasoning; it cannot authorize continuation or waive current revalidation. |
| [#21](https://github.com/jresearchsoftware/codex-relay/issues/21) | Public Issue read anonymously on 2026-10-11; last update 2026-10-01T13:01:22Z, title “Planning — Durable incremental publication for long-running Codex work,” still planning/not admitted. Safe incremental Writer publication remains distinct from readiness. Neither P nor H establishes the concurrent snapshot/import proof. This public context grants no execution authority. |
| [#22](https://github.com/jresearchsoftware/codex-relay/issues/22) | Codex-initiated suspension/owner resolution requires the same authority and containment separation as #20. A native question or waiting event does not create a new Task Request or an indefinite worker lease. |
| [#25](https://github.com/jresearchsoftware/codex-relay/issues/25) | R7 already implements Relay-level admission/drain mechanics at this source baseline. Preserve their full controller scope; daemon health/restart cannot replace them. Installed behavior was not tested here. |
| [#24](https://github.com/jresearchsoftware/codex-relay/issues/24) | R3/R4 already record bounded usage reporting on O. App-server is not its prerequisite; multi-turn accounting would need new proof rather than reinterpret existing session-total values. No Issue closure claim is made. |
| [#115](https://github.com/jresearchsoftware/codex-relay/issues/115) / [PR #118](https://github.com/jresearchsoftware/codex-relay/pull/118) | Supplied authority identifies pending redesign across typed authority, Writer, Reviewer, controller, launch, workflows and deployment. Candidate details were not adopted or treated as accepted behavior. A future runtime adapter would need to accept the then-current trusted envelope/result and preserve its publication/acceptance boundaries. No schema, field, route or eventual compatibility is inferred. |

Only #21 needed an additional public backlog read to clarify its connection;
the other relationships use supplied #42 context and pinned source. A later
source-base change does not silently refresh this assessment's evidence. If it
materially affects recommendations or causes a report-PR conflict, seek bounded
authority reconciliation and review the changed report. Do not rebase onto an
unaccepted candidate or force publication to preserve the appearance of a clean
handoff.

## Smallest credible qualification and migration path

Everything in this section is **optional future work after explicit owner
admission**, not execution authorized by this report. Stop at the first stage
that removes the reason to migrate. Use ordinary Task/Request/PR/check/Outcome
records and one independent exact-head review for each admitted candidate,
without a separate architecture approval service.

1. **Resolve the decision and exact experimental target.** Owner chooses retain
   O, investigate H, or justify P. Name the precise accepted source and Codex
   release, task mix and desired interaction benefit. Resolve willingness to
   rely on any experimental/unsupported native surface. Retaining O is a
   complete valid choice; reconsider when maturity or measured needs change.
2. **Disposable credential-free protocol proof.** On an admitted capable
   executor, use an empty private home/environment and synthetic repository;
   generate schemas from that exact binary. Confirm initialization, exact
   prompt/profile/policy/schema mapping, native identity/status and terminal
   semantic normalization with a deterministic local provider, if supported.
   No existing credentials/sessions or global installation. Mock-provider
   results do not prove paid model access or model behavior.
3. **Targeted failure proof.** Exercise the matrix's uncertain submission,
   disconnect, descendant containment, interrupted tools, compaction/crash,
   output truncation and missing/corrupted-state cases. Record actual bytes/Git
   effects and surviving processes, not just a thread status. Test two isolated
   Tasks and rejected cross-binding. If native state recovery cannot establish
   the original mutation frontier, verify that the adapter stops without
   resend. Reuse R5/R6/R7 tests wherever the invariant is unchanged.
4. **One bounded H candidate, if warranted.** Map only the fixed admitted
   operation into the native protocol; preserve accepted result and collection
   interfaces and O routing. Qualify relevant unprivileged source checks and
   separately admitted disposable installed-runtime UID/sudo/isolation proof.
   Do not require a production/TEST installation merely to test source logic.
   Real model/credential or host proof needs its own explicit boundary; none is
   implied by local success. Independent review remains exact-head.
5. **Owner-authorized limited rollout and rollback proof.** Use Relay's public
   deployment/lifecycle interface only after source acceptance and separate
   installation authority. Route explicitly selected new attempts, measure
   benefit and warnings, and preserve a verified O revision. If P or
   cross-admission persistence is still needed, separately admit its retention,
   supervisor, client revocation, upgrade and suspension contract. Do not
   incrementally smuggle those into H.

The pre-submission fallback boundary is concrete: if no native turn could have
started and routing authority permits, O can be chosen for that new execution.
After submission, do not silently call O to rerun the task. Preserve the
attempt, establish containment and effect provenance, reconcile publication
separately, then obtain whatever fresh execution authority is necessary.
Rollback restores an exact accepted runtime for **new** authorized attempts;
it does not erase or repeat prior effects. Old native storage may need to remain
read-only under its original version until the owner resolves compatibility.

Residual decisions are the value of live interaction versus improving O;
native maturity tolerance; task-scoped versus shared lifetime; whether durable
cross-admission history is necessary; suspension/drain behavior; retention and
credential budgets; and workload/operating-cost tolerances. They belong in
canonical owner authority before implementation. There is no present evidence
that justifies a consumer-wide daemon as the simplest governed design.

## Local validation and handoff limitations

V environment: Linux x86_64, Python 3.11.2, Git 2.39.5 and Node 18.20.4.
`codex`, npm, Cargo/Rust and pytest were unavailable. Node is below the
repository's qualified minimum of 22; successful tests under 18 do not qualify
that toolchain for deployment.
Subagents were permitted but not used. The requested execution profile was
`gpt-6.1-sol` / `xhigh`; authoritative actual model/effort values were
`UNAVAILABLE` from the worker's local evidence.

The exact Node test command from `package.json` was invoked directly because
npm was missing. The first invocation could not load the checked-in synthetic
consumer fixture: its worker-checkout mode was `0660`, which the accepted loader
rejects as group-writable. The justified correction was to copy only that
synthetic JSON to a private disposable `0600` file and set
`RELAY_CONSUMER_CONFIG` for the test process. No repository permissions or live
consumer configuration changed. The corrected run passed **669 tests, zero
failures, one skip** (670 total). The skip explicitly requires root for
disposable worker/collector UID separation; no escalation was attempted.
Executable sources were unchanged throughout this report-only candidate.

This initial failure is an environment/fixture permission condition on the
unchanged pinned source, not a regression introduced by the report. npm's own
entrypoint, Python deployment pytest suites, Cargo formatting/tests and
`scripts/qualify.py` could not be run with the available capabilities. No
dependency or global tool installation was attempted. The recorded 0.160.0
qualifier was inspected, not executed, because it downloads/installs a binary
and the admitted probe boundary does not permit that action.

Local `git diff --check` (including the staged diff), the tracked candidate
JSON/link/credential-marker check and the dedicated tracked secret scan passed
for the report candidate. These are local validation claims for the trusted
Writer handoff, not a native CI verdict.
`github-test-validate` is a native/consumer-owned proof (R8), unavailable within
this credential-free worker. Required exact-head CI and any root-only
installed-runtime proof remain separate after Writer publication; this report
does not claim they passed.

Primary Relay/Codex Outcome and GitHub execution annotation surfaces for the
current attempt could not be inspected from this worker's permitted local
interface. That is a warning-evidence acquisition gap, not `none_observed`.
The toolchain gaps, initial fixture failure, its correction and root-only skip
are material execution limitations disclosed for the next owner/review
boundary. Trusted Writer and independent review must inspect applicable native
warning surfaces and disposition their actual evidence.

Useful progress is preserved in an ordinary local task-owned commit. The
automatic worker neither publishes a PR/Outcome nor self-approves, merges or
closes Issues. Trusted Writer owns publication and the exact candidate SHA;
independent acceptance remains outstanding. Only this report is added to the
repository; no disposable probe, documentation snapshot or runtime fixture is
made a product requirement.

## Step 2 addendum: persistent execution service

Task #42, Step 2 — source-only follow-up, 2026-10-11. **Retain one-shot execution;
evaluate a warm service separately from persistent Task conversations.** The
owner-proposed fourth option keeps the server alive but creates and retires an
independent thread per execution. It could amortize startup and offer structured
interaction without cross-execution history. Step 1's long-session objections
do not reject this design; preserving isolation and containment while the
process survives remains unresolved.

Address scheduling and multi-repository needs on one-shot exec under their own
admissions. If interaction or measured startup cost warrants further research,
qualify a per-execution adapter before testing service reuse. No linked Task
requires app-server. This recommendation selects no migration design, admits
no implementation and adds no acceptance gate. Issue #42 stays `keep-open`.

### Evidence and version boundary

The Step 2 baseline is the Request's accepted commit
[`9f825890a927a8e6678b2faf72abbb8f1df9539a`](https://github.com/jresearchsoftware/codex-relay/tree/9f825890a927a8e6678b2faf72abbb8f1df9539a),
including the merged Step 1 report. The checkout was clean at that starting head
on `codex/task-42-step-2`. The selected
[Decision](https://github.com/jresearchsoftware/codex-relay/issues/42#issuecomment-6114465621)
was read anonymously; its body digest matched the supplied Request reference.
The complete Step 2 Request governs execution; other Issues/documentation are
contextual evidence.

The accepted [CLI integration](codex/cli-integration.md) still pins 0.160.0.
The upstream annotated tag `rust-v0.160.0` resolved
to commit `a956835d020762cb2b570053af06f643a11c0ecc`. The **N** evidence below is
source inspection, not execution, generated schema qualification or Relay
acceptance. S/D/A/U retain their Step 1 meanings; V covers local checks. All
scenarios are A: no simulation, native probe or model call was performed.
`codex` is absent from the worker's search path. Public source text was fetched
to temporary storage; no executable was downloaded.

| Evidence | Exact source and conclusion |
| --- | --- |
| S2-1 | [Architecture](architecture.md), [consumer contract](../consumer/README.md), [runtime](../runtime/README.md#durable-diagnostics-and-sandbox-finalization), [launcher](../deploy/ansible/roles/relay_codex_runtime/templates/relay-codex-launcher.mjs.j2): one configured Writer/controller consumer per process, configured non-root `runtimeUser`, attempt-local HOME/CODEX_HOME/XDG/temp, recreated credential environment and outer process-group containment. Separate attempts do not imply a distinct UID for each attempt. |
| S2-2 | [Routing](../deploy/workflows/routing.yml.in), [recovery](../deploy/workflows/recovery.yml.in), [admission/drain](../controller/README.md#lifecycle-admission-and-drain): routing and publication recovery share the configured control group with `cancel-in-progress: false`; templates do not set `queue`. Root Writer lock and durable controller reservations remain separate from Actions scheduling. |
| S2-3 | [Reviewer contract](../reviewer/README.md), [configuration](../consumer/README.md): accepted Reviewer supports explicit configured repository selection; consumer/Writer configuration remains single-repository. Review publication remains independent and bound to the exact head. These facts are from the pinned tree, not inferred from Issue status. |
| N1 | [Thread parameters](https://github.com/openai/codex/blob/a956835d020762cb2b570053af06f643a11c0ecc/codex-rs/app-server-protocol/src/protocol/v2/thread.rs), [turn parameters](https://github.com/openai/codex/blob/a956835d020762cb2b570053af06f643a11c0ecc/codex-rs/app-server-protocol/src/protocol/v2/turn.rs): thread `cwd`, config, sandbox/approval overrides and `ephemeral` exist. Turn input supports model/effort, policy, cwd and output schema. `turn/steer` requires `expectedTurnId`; interrupt targets thread/turn IDs. These parameters provide no Unix `runtimeUser` selector. Several other fields, including environment selection and runtime workspace roots, are experimental. |
| N2 | [RPC dispatch](https://github.com/openai/codex/blob/a956835d020762cb2b570053af06f643a11c0ecc/codex-rs/app-server/src/message_processor.rs), [method definitions](https://github.com/openai/codex/blob/a956835d020762cb2b570053af06f643a11c0ecc/codex-rs/app-server-protocol/src/protocol/common.rs), [thread manager](https://github.com/openai/codex/blob/a956835d020762cb2b570053af06f643a11c0ecc/codex-rs/core/src/thread_manager.rs): thread-indexed runtimes and per-thread request serialization allow distinct threads to be managed independently. Authentication, thread store and services including environment, skills, plugins and MCP are shared. This is source support for multiplexing, not measured parallel throughput or tenant separation. |
| N3 | [Turn processor](https://github.com/openai/codex/blob/a956835d020762cb2b570053af06f643a11c0ecc/codex-rs/app-server/src/request_processors/turn_processor.rs), [thread processor](https://github.com/openai/codex/blob/a956835d020762cb2b570053af06f643a11c0ecc/codex-rs/app-server/src/request_processors/thread_processor.rs): `turn/start` calls `start_or_steer_turn`, so input to an active thread can steer rather than create another independent turn. Interrupt validates the target and responds on native abort. Connection closure removes subscriptions; it is not proof that all tools have stopped. |
| N4 | [Native event definitions](https://github.com/openai/codex/blob/a956835d020762cb2b570053af06f643a11c0ecc/codex-rs/app-server-protocol/src/protocol/common.rs), [usage types](https://github.com/openai/codex/blob/a956835d020762cb2b570053af06f643a11c0ecc/codex-rs/app-server-protocol/src/protocol/v2/thread.rs): thread status, turn/item lifecycle, deltas and usage notifications exist; usage carries thread/turn IDs with total/last breakdowns. Terminal status distinguishes completed, interrupted and failed. No end-to-end Relay replay, accounting or containment proof follows. |
| N5 | [Daemon lifecycle documentation](https://github.com/openai/codex/blob/a956835d020762cb2b570053af06f643a11c0ecc/codex-rs/app-server-daemon/README.md), [control socket](https://github.com/openai/codex/blob/a956835d020762cb2b570053af06f643a11c0ecc/codex-rs/app-server-transport/src/transport/unix_socket.rs): lifecycle is experimental; clients share the daemon's inherited environment. Managed latest-channel installations can update/restart automatically; explicit update selects latest stable. Stop/restart has a bounded grace period and can interrupt work. Unix socket code sets mode `0600` and validates parent ownership/modes. None was exercised here. |
| N6 | [Recovery snapshot](https://github.com/openai/codex/blob/a956835d020762cb2b570053af06f643a11c0ecc/codex-rs/app-server-transport/src/daemon_recovery.rs), [restoration](https://github.com/openai/codex/blob/a956835d020762cb2b570053af06f643a11c0ecc/codex-rs/app-server/src/daemon_thread_recovery.rs), [continuation](https://github.com/openai/codex/blob/a956835d020762cb2b570053af06f643a11c0ecc/codex-rs/app-server/src/request_processors/daemon_continuation.rs): managed recovery can start a new continuation turn for eligible interrupted persistent threads after checking recorded history, local environment and permission agreement. It does not revalidate Relay authority or prove prior tool effects. This is a material integration hazard, not observed exactly-once recovery. |

Moving [official OpenAI documentation](https://learn.chatgpt.com/docs/app-server)
was fetched on 2026-10-11 and marks app-server/WebSocket use experimental and
unsupported for production workloads (D). Exact-version conclusions use N
sources; neither moving documentation nor upstream source establishes Relay
production acceptance.

### Separate lifetimes and ownership

| Object | Lifetime in the proposed service | Owner and invariant |
| --- | --- | --- |
| Server | Across many executions, bounded by restart/upgrade | Native process manages protocol/runtimes; a future Relay supervisor would own exact version, identity, credentials, capacity and health. Its uptime grants no Task admission. |
| Thread | Fresh for one execution; optional native ephemeral history | Native conversation and child-thread ancestry. Relay binds it to the existing attempt, repository, Request/profile and checkout. Thread IDs are correlation, not Unix isolation or authority. |
| Turn | One active interaction in a thread; inner follow-ups only within admitted scope | Native generation/tool events. Relay controls authorized submission, steer/interrupt and semantic-result validation. N3 rules out treating concurrent inputs to one thread as independent executions. |
| Execution | Reservation through containment, collection, publication and durable receipts | Relay retains the existing attempt lifecycle. Several turns may fit one execution; terminal turn status does not terminate this lifecycle. |
| Task/Step | Canonical Issue/Request semantics across executions | GitHub authority, owner decisions and independent exact-head acceptance. Task lifetime neither requires a native persistent thread nor determines server lifetime. |

Proposed flow: trusted admission → adapter binding → fresh thread/turn → bounded
capture → execution containment → trusted object import → Writer → independent
review. The server may survive only if the execution loses all ability to
mutate its captured workspace. This is U, unproved by `turn/completed`,
unsubscribe, archive or RPC success. Extend existing attempt evidence rather
than create another Task registry or use a native queue as authority.

### Decision matrix

All projected benefits and costs are A/U, not benchmarks. **F** denotes the new
fresh-thread service; **P** retains Step 1's long-lived Task conversations.

| Criterion | O: governed one-shot exec | H: app-server per execution | F: warm server, fresh threads | P: long-lived Task sessions |
| --- | --- | --- | --- | --- |
| Startup/resource cost | Startup per execution; no idle server | Same startup cadence plus adapter | Startup amortized; idle RSS/CPU, caches and service operations added | F costs plus retained history and recovery work |
| Interaction/observability | JSONL identity/usage already accepted; enhancements possible | Native steer/interrupt and item streaming candidate | Same protocol benefits with service reuse | Also conversation continuity across executions |
| Parallel independent work | Multiple isolated processes possible after #103 proof | Multiple contained children possible after #103 proof | Separate threads are supported in source; capacity/fairness unmeasured | Also contend on persistent Task state; no scheduling advantage over F |
| Identity/environment | Per-attempt recreated environment under configured runtime user | Can preserve that launch boundary | One process shares UID, startup environment/auth/store; no per-thread Unix user | Same shared-process risks, extended history lifetime |
| Containment/failure scope | Reap attempt-owned group before collection | Whole child can be reaped per execution | Killing server can stop all tenants; selective tool/descendant revocation unqualified | Same risk plus suspended/orphaned sessions |
| Recovery/durability | Existing unknown-execution stop, Git progress and protected diagnostics | Retain existing stop; optional history within attempt | No Task-session recovery required; lost submission/events still require reconciliation | Compaction/versioned history and managed auto-continuation add hazards |
| Upgrade/rollback/operator work | Existing #25 lifecycle and pinned binary | Adapter/version qualification; attempt ends with child | Inventory all active attempts, IPC/state retention, credential renewal, capacity and service restart | Also history compatibility, abandoned sessions and longer owner waits |
| Decision now | Retain | Smallest optional protocol pilot | Credible subsequent comparison within a qualified identity boundary | Require an independently demonstrated continuity need |

F still needs fresh context; shared caches prove no provider-token savings.
Compare startup, first useful event, handoff time, RSS, retained bytes, usage
attribution and incident/upgrade operator minutes against O/H with the same
profile/workload. Warm state alone does not justify the service's added cost.

### Isolation risks and viable service boundaries

**One native process does not supply the different Unix Worker identities
requested by #86.** N1 offers policy/cwd/config selection, not identity switching;
N2/N5 show shared services/environment. Cwd/config overrides cannot partition
process memory, credentials, open descriptors or state. A privileged server
that switches users enlarges the trust boundary and conflicts with #67's
rootless direction; it is not recommended.

| Concrete exposure | Existing protection and smallest credible alternative | Cost / remaining proof |
| --- | --- | --- |
| B reaches A's checkout/history or shared auth/config | O/H retain attempt-local state and process lifetime. F could serve one effective UID/namespace through a bounded trusted adapter. | Same UID/cwd/sandbox writes do not prove read isolation, server-tool confinement or cleanup. Prove workspace access/revocation; otherwise retain O/H. |
| Repositories select different `runtimeUser` values | Native services partitioned by effective UID **and** namespace/credential domain behind one logical Relay configuration; equivalent repositories may share. | Added resident processes/drain inventory. No new Apps, repository ACL policy or Relay installation per repository is required. Per-UID services still need per-execution proof. |
| HOME/CODEX_HOME/XDG, logs, SQLite/WAL, telemetry/caches retain material | Keep bounded credentials/protected diagnostics; inventory process-state paths and disposal. N2's thread store is process-scoped. | New retention burden. `ephemeral` does not prove prompt/tool-output erasure from logs, caches or memory; config overrides cannot relocate protected state. |
| Socket clients invoke account/config/plugin, shell or process-wide RPC | Fixed trusted client exposes only needed operations; workers receive no raw endpoint/control. N5's private socket is host access control, not tenant ACLs. | Adapter/method-version maintenance. Reuse credential separation, without a general policy engine. |
| Children/tools outlive root turn; interrupt targets another Task | Bind parent/child/turn IDs to existing execution; preserve profile/Subagents admission and qualify descendants. | Accepted Off remains instructional, not OS isolation. Child threads grant no new Relay Task/capacity. Selective containment and complete child usage attribution are U. |

A per-execution process remains the simple containment unit retained by H.
Shared namespaces still share memory, credentials and failure fate. External
isolated executors could partition tool effects, but N1's experimental
environments do not prove that design. Qualification/complexity may exceed O/H;
this proposes no container/platform prerequisite. Accepting O's existing costs
is a valid cheaper response under proportional controls.

Keep Relay checkouts, trusted object import and authority/exact-head
revalidation. Native worktrees, Git metadata/diffs and conversation history
cannot establish the candidate SHA or a frozen snapshot. Trusted Git must
never use server/model-modified metadata. Independent Reviewer is not replaced
by native `review/start` or a thread in the implementation service.

### Cross-Task dependency and ownership matrix

Public Issue bodies were read anonymously on 2026-10-11 as context only.
Observed body update dates were #103: October 10, #85: October 7, #86: October 9,
#67: October 5, #84: October 9. S2 establishes accepted behavior; no linked
candidate implementation was adopted.

| Task / owner | Dependency or relationship | Can proceed on O? |
| --- | --- | --- |
| [#103](https://github.com/jresearchsoftware/codex-relay/issues/103): scheduling and safe parallel execution | Independent of #42. Owns pending replacement/event freshness, runners, duplicate/same-Task admission, publication/recovery contention and full drain. | Yes; reliable serial scheduling and bounded parallel processes need no app-server. Same-Task/workspace and Writer critical sections still require exclusion. |
| [#85](https://github.com/jresearchsoftware/codex-relay/issues/85): multi-repository Writer | Independent of #42; counterpart to #84. Explicit configured targets/repository-aware identities prevent overlapping Issue/PR/attempt IDs; preserve shared Writer identity and safe publication. | Yes; no conversation or native protocol dependency, and no new repository security policy. |
| [#86](https://github.com/jresearchsoftware/codex-relay/issues/86): organization configuration/Worker user | Explicit semantic dependency: #84 **and** #85 → #86. Owns shared defaults, sparse overrides and effective Unix user, not a new privilege/profile framework. | Yes; select effective user at existing launch. F must respect selection through eligible identity-bound services; Tasks cannot choose users. |
| [#84](https://github.com/jresearchsoftware/codex-relay/issues/84): accepted Reviewer | S2-3 is the independent exact-head review/publication boundary; native review cannot absorb it. | Already in accepted source; no #42 dependency. |
| [#67](https://github.com/jresearchsoftware/codex-relay/issues/67): rootless steady-state/multi-instance isolation | Independent privilege redesign; informs F supervisor/client/state permissions. Preserve namespaces without requiring VM/container or generic root/user-switch authority. | Yes. Future F host integration needs the qualified applicable privilege contract, not speculative #67 completion. |
| #19/#24, #20/#22, #21, #25, #17 | Step 1 maps observability/usage, pause/suspension, incremental publication, Relay lifecycle and compaction context. Fresh threads need no persistent Task-session recovery. Ending an owner-waiting execution and later admitting a fresh one is an option requiring owner workflow authority. | O can improve observability/usage and lifecycle. Server persistence grants no resume authority or concurrent publication proof. |

#115 candidate differences are interoperability context only; use the pinned
accepted tree without importing unaccepted behavior. Step 1's parallel-candidate
discussion is historical. A material later base change needs evidence/authority
reconciliation; no silent rebase, merge or forced integration.

### Capacity layers and failure scenarios

Scheduling, running jobs, native turns and publication are different capacity
layers. Each requires its own proof; raising one capacity cannot bypass another.

| Layer | Owner / bounded design question |
| --- | --- |
| Actions waiting runs | #103. S2-2 uses default pending replacement. Current [GitHub documentation](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency) offers `queue: max` for up to 100 pending runs, then cancellation; it conflicts with `cancel-in-progress: true` (D). Consider before a Relay queue, but qualify availability/freshness/recovery. No template change or app-server repair of dropped events follows. |
| Runner jobs | #103 / infrastructure. Native multi-thread capacity cannot make one runner execute multiple jobs. Qualify actual runner capacity, identities/labels and credential access. |
| Admission/controllers | Relay. Keep reservation, replay suppression, Task/PR exclusion and namespace/config binding; drain all controllers. Native goals/queues cannot admit executions. |
| Codex execution | Adapter/supervisor. Bound tools/children and host/provider capacity; measure fairness/backpressure. N2 proves no throughput quota or starvation protection. |
| Writer/recovery | Writer. Lock critical sections, not whole model execution; preserve repository-aware identities under #85. No casual lock sharding or lock held during model/owner waits. |
| Review/upgrades | Independent Reviewer / Relay lifecycle. Keep exact-head review and full #25 quiesce/drain/verify/resume. Native idle/health cannot reconcile unknown execution/publication. |

| Hypothetical scenario (A) | Required disposition / difference from O/H |
| --- | --- |
| A runs; C replaces pending B | #103 must resolve event loss; server persistence cannot recover an unadmitted event. Larger native queues still overflow. |
| Independent A/B run; duplicate A arrives | Qualify A/B isolation/capacity. Reject duplicate admission before RPC; do not append it to A's active thread. |
| Submission response is lost | Preserve original effects/attempt; no resend/fallback to O. RPC/thread/message IDs prove no transactional tool deduplication. Ephemeral history loss may worsen evidence. |
| Disconnect/backpressure loses A's events | Completion/usage may be unavailable. Server health proves no success. Qualify reconnect/read gaps and bounded capture without B's data; lossless replay is unproved. |
| Owner steers/interrupts A while B runs | Bind current authority/thread/turn and steer precondition. Abort proves no rollback/containment; test A's tools stop while B survives. Killing server affects both. |
| A's tools/children hang after apparent completion | No live import/cleanup. O/H reap their group; F needs selective containment/revocation or stops affected publication with shared impact disclosed. |
| Crash or managed restart | Reconcile all affected attempts. N6 can continue without Relay reauthorization. Prove a supervised service cannot reload/continue mutable work outside admission; ephemeral roots alone do not suffice. |
| Writer push uncertain; daemon idle | Keep quiesced; reconcile original Writer intent without model execution. Native idle/rollback cannot resolve or justify repeating effects. |
| Version/state incompatible; rollback | Keep exact O revision and diagnostics/Git progress. O fallback only before possible submission when routing permits; otherwise reconcile first. State downgrade is U; retain bytes inactive. |

### Bounded proof plan and owner decisions

Optional future work requires separate Requests, existing Task/PR/check/Outcome
evidence and independent exact-head review. No recurring operator step or
fixture is required here.

1. **Resolve need and target.** Owner names benefit, exact Relay/Codex revisions,
   profile, workload and cost tolerance. #103 is independent; #85 then #86 can
   advance on O. Coordinate #67's applicable identity/namespace boundary for
   host integration, without gating protocol research on unrelated backlog.
2. **Prove an isolated-child adapter.** On an admitted capable executor, use an
   available exact binary, private empty environment, synthetic checkout and
   credential-free loopback provider. Generate schemas; exercise initialization,
   fresh/ephemeral threads, exact profile/prompt/policy/output-schema mapping,
   events/usage and wrong-thread/turn rejection. Compare two threads with two O
   processes; test active-thread start/steer, interrupt and child agents. This
   needs no owner session/global installation and proves no real model access.
3. **Prove F before reuse.** Check actual UID/GID, environment/state locations,
   cross-checkout read/write restrictions, shared auth/config, sockets,
   descendants, retention and workspace revocation. Exercise slow clients,
   uncertain submission, A/B crash/restart, prevention of managed continuation,
   lost events and concurrent cleanup. Record surviving processes and actual
   Git/filesystem effects. Failed selective containment favors O/H. Installed
   UID/privilege proof requires its own admission.
4. **Decide on measured gain before implementation.** Compare O/H/F costs under
   equivalent isolation. If F wins, qualify one identity/namespace before
   multiple users, with no managed auto-update or unauthorized continuation.
   Preserve full Relay drain/publication and exact O fallback for new attempts.
   Upgrade, credentials and host rollout need separate authority. P requires a
   demonstrated continuity need; it is not F's prerequisite.

Owner decisions remain experimental maturity tolerance, benefit/cost threshold,
acceptable isolation/identity pooling, retention/credential lifetime and whether
pause/resume needs conversational continuity. Record them canonically before
material implementation. Step 2 performs no migration, linked-Task execution,
deployment, release, merge or Issue closure.

### Step 2 local validation and handoff limits

V: Linux x86_64, unprivileged worker, Node 18.20.4 and Python 3.11.2. `codex`,
npm, pytest and Cargo/Rust are unavailable; Node is below the repository's
qualified minimum of 22. No dependency/tool installation or escalation was
attempted. The accepted 0.160.0 exec qualifier was not rerun and does not qualify
app-server. Actual model/effort are `UNAVAILABLE` from local authoritative
evidence; admitted values remain `gpt-6.1-sol` / `xhigh`. Subagents were permitted
and not used.

The exact `package.json` Node script was run directly with its synthetic consumer
JSON copied to a disposable `0600` file: the checkout fixture is `0660`
(`nobody:nogroup`). Step 1's correction was reused without changing repository
modes/configuration. **669 passed, zero failed, one skipped** (670 total).
The root-only synthetic UID test was skipped. This proves local checks under
Node 18, not qualified toolchain/installed isolation. These environment
conditions pre-exist the report change.

Report whitespace, tracked candidate JSON/local-link/credential-marker checking
and the dedicated tracked secret scan passed.
`npm test` itself, deployment pytest suites, Cargo formatting/tests and
`scripts/qualify.py` cannot run with this toolchain. Native
`github-test-validate` / exact-head CI remains unavailable in this
credential-free worker and must be acquired after trusted Writer publication.
Pending native proof is separate from completing the local report.

Current-attempt Outcome/check/job/runtime warning surfaces are unavailable
through the permitted local interface: an acquisition gap, not `none_observed`.
Writer/review must inspect native warnings and disposition toolchain, root-only
test and native-probe limitations at the next decision boundary.

Only this report changes. Useful progress is preserved in a normal task-owned
local commit for trusted Writer to publish at its collected exact candidate
SHA. The worker makes no GitHub publication or self-review; independent
acceptance remains outstanding. Disposable public source/test files are outside
the repository and introduce no report fixture or product dependency.
