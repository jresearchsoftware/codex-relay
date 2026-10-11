# Governed Codex execution: architecture assessment

Task #42, Step 1 — source-only research, 2026-10-11.

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
