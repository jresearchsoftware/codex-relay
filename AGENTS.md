# Developing Codex Relay

These instructions govern **owner-admitted Relay/Codex development**. Ordinary
human contributors use [CONTRIBUTING.md](CONTRIBUTING.md); they do not need
Task/Step admission, an installed Relay consumer, Codex UI tools or these
optional developer hooks to propose a change.

## Context loading and governance layering

Start owner-admitted work with only this file, the live canonical Issue or
Change Request (including trusted Decisions and the immutable admitted snapshot
for a streamlined Task, or the selected Request for retained schema-v3 work),
the current PR when one exists, and the exact Git/check facts
needed for the current decision. The live authority identifies the active goal;
do not preload broad repository history, status documents, component manuals or
old task artifacts merely because they may become relevant.

Load detail just in time. Read [architecture](docs/architecture.md) before a
change to orchestration or a trust boundary, the affected component contract
before changing its API, [CONTRIBUTING.md](CONTRIBUTING.md) when environment or
validation detail is needed, and deployment/hook/subagent documentation only
when those surfaces are active. Prefer a targeted section, path, diff or exact
live fact over a broad reread.

Keep this file limited to durable cross-task invariants and stable routing
pointers. Component mechanics, platform detail, deployment procedures and tool
qualification belong in their canonical component documents. A lower-level
document may specialize an explicit extension point but cannot weaken Task/CR
authority, security, publication, review or protected-boundary rules.

After a mutation, recovery or compaction, refresh only mutable authority and
facts that could have changed. Do not restart broad discovery or treat cached
history as current truth.

For legacy Tasks, the live Issue body is the mutable canonical Task contract. Keep current
requirements, owner corrections, scope/boundary decisions and task status in
that body. Comments hold discussion, evidence, Outcomes, handoffs and history;
they must not become a competing current Task contract. Native Change Requests
retain their existing remediation authority.

All human-readable GitHub publication for this repository is in English,
including Issue and PR titles/bodies, Codex Outcomes and handoffs, ordinary
comments, and native Reviewer APPROVE / REQUEST_CHANGES bodies. Interactive
owner/ChatGPT discussion and review previews may use the owner's preferred
language; do not copy that language into GitHub publication. Literal evidence,
logs, identifiers and quoted external text may retain their original language
when necessary.

## Task identity and startup rename

`Task N` is canonical GitHub Issue `#N`, not a separately allocated number.
A Task/Issue defines the authorized goal, boundaries, and completion/closure
intent. Canonical Task producers must include exactly one explicit
`Issue closure policy: keep-open` or `Issue closure policy: close-authorized`
field in the live Issue body, using `close-authorized` only with owner authority.
CR producers preserve that Issue decision when updating canonical authority;
a CR does not independently authorize closure. Missing, malformed or conflicting
closure metadata remains `keep-open` with a visible warning.
`keep-open` means known work or evidence is still expected after implementation.
Nearby prose should explain why the Issue stays open and what outcome would make closure
appropriate. This is ordinary Task prose, not another required structured field
or an automatic closure rule.
Before every new Task Decision (or compatibility Task Request), consciously reassess
the known post-implementation work or evidence that justifies `keep-open`.
Retain it with adjacent concrete remaining conditions and the owner disposition
needed to change it, or seek or apply existing explicit owner authorization to
record `close-authorized` in a trusted owner-authorized Task Decision. For new
schema-v4 work, initial charter plus that Decision determines the effective
policy; a CR cannot independently authorize closure. Retained schema-v3 work
keeps its original charter/Request rules. Close only after trusted owner
completion evidence, verified independent acceptance at the exact result/head,
no remaining work or continuation hold, and satisfied protected boundaries.
An Outcome's completion claim alone is insufficient. Approval, merge or Step
completion alone grants no closure authority. Use the
[closure authoring guidance](contracts/README.md#closure-policy-authoring)
within the existing authoring action, without another field or workflow.
After an explicit `Authority model: github-native-v1` migration, the Issue is
the stable charter. In the current schema-v4 source contract, trusted Decisions
amend durable semantics and Writer creates the sole immutable
Step/profile/route/scope admission snapshot at execution. A new complete public
Request is unnecessary; ordinary comments remain selected evidence. Retained
schema-v3 admissions preserve their selected typed Request and original
bindings, Steps, bodies and replay/recovery behavior. Use the
[GitHub-native contract](contracts/README.md#github-native-task-authority) and
paired qualified Reviewer/controller. Source changes alone do not upgrade or
qualify an installation. Labels and bounded titles are projections,
not a second Step authority; legacy owner metadata helpers cannot write them.
On a paired, qualified schema-v4 installation, fresh Task work or remediation
must use the current v4 authority path. An unmarked/legacy Task or a new v3
Request/CR chain stops with an actionable protocol mismatch; use current v4
authority or an explicitly owner-authorized migration before a new admission.
Historical reads and safe completion, Outcome publication and recovery of an
exact already-admitted old attempt retain their original bindings. This is a
fresh-execution boundary, not a blanket support cutoff for older installations.
Fresh durable Decision/Request/CR publication also uses current v4 authority;
exact reserved old publication recovery and old admitted-result acceptance remain
supported without creating a new old-schema governance chain.
Steps are execution-time decomposition of progress toward that Task.
A Task does not predefine, own, or constrain the number, numbering, or scope of
its Steps. Steps may be introduced as work evolves; a Task may require one Step
or arbitrarily many. Completing a Step does not imply completing the Task.
Codex thread continuity is independent of Step boundaries: one physical thread
may execute multiple successive Steps when useful. Step descriptions embedded
in historical Task text are not authority over future Step decomposition.

Use these complete titles, with a concise purpose:

- Implementation: `Task N — Step S — <purpose>`.
- Remediation: `Task N — Step S — CR-N-NNN — <CR purpose>`.

Preserve an exact title supplied by live task/CR authority, including an
explicit phase qualifier. Step is a positive, explicitly resolved value.
For a new schema-v4 execution, the owner applies the native
`codex-ready-auto` or `codex-ready-manual` command on the canonical target;
Writer verifies and consumes that event and allocates Step in protected
admission state. Charter creation, Decisions, CR publication and labels do not
allocate Step. Fresh execution starts at Step 1; each genuinely new admitted
execution, including one after BLOCKED, receives the next Step. Inner
corrections, replay and recovery of the same attempt retain its Step and cannot
launch another execution. Titles and `step-S` labels project admitted state.
For legacy admission the Issue has exactly one `step-S` label and the existing
PR agrees. An explicitly owner-authorized new phase uses the
[owner metadata procedure](contracts/README.md#owner-step-metadata-procedure)
for legacy Tasks. Retained schema-v3 migrated Tasks keep the complete trusted
successor Request and synchronized CR Step/projection rules. A compatibility
retry or publication repair keeps that selected Step; approval does not
increment it. Never infer Step from prose, commits, labels or the largest
historical Step. Read the protected snapshot or retained selected Request.
Missing or conflicting admission metadata needs reconciliation. Step labels
alone do not launch work or grant authority. The
[Issue template](.github/ISSUE_TEMPLATE/codex-task.md) supplies
the authoring baseline; its creation is not admission or dispatch.

For an owner-launched manual session, rename the current Codex task at startup
to the exact title from the admitted snapshot/handoff, or selected legacy
Task/Change Request authority above. A backlog Decision or ready label alone
does not supply a future Step/title.
Use the native task-title tool once with only `title` (omit `threadId`); search
deferred tools if it is not initially visible. Recording the title only in a
prompt, PR or Outcome is insufficient. When the current native tool surface can
read back the persisted title, compare it with the exact requested title. A
successful rename call alone does not prove persisted state. Report the call
result and any read-back mismatch, truncation or unavailable verification
truthfully. An unavailable/failed rename or unverified exact title is
non-blocking; do not repeat the rename to chase a match. Preserve the supplied
Task/Step identity; never infer a new Step from history. Automatic runtime
execution already passes its resolved title to Codex and does not require a
worker to discover or invoke the UI rename tool.

## Canonical checkout and safe Git handoff

For repository changes assigned to Codex, Codex owns the implementation branch,
commit and PR flow. ChatGPT/owner orchestration must not create implementation
branches, commits or PRs unless the owner explicitly requests it. Automatic
workers still delegate GitHub publication to trusted Writer.

The canonical Task may authorize implementation continuation on an existing
task branch and its current PR when one exists through trusted Task Decisions
resolved into the admission snapshot, a retained complete typed Request, or
legacy Issue-body bindings, as described in
the [controller contract](controller/README.md#issue-authorized-implementation-continuation).
This preserves Issue authority and implementation identity without a Reviewer
CR or its integration-merge permission. Replay/recovery of an admitted attempt
keeps Step; a genuinely new schema-v4 execution receives a fresh admitted Step.
Retained schema-v3 and legacy phases preserve their successor Request or N+1
metadata procedure. Manual handoff retains its full copyable prompt and visible
canonical identity/pointer; folding changes presentation only.

Before applying an existing PR's starting-head gate, read its live repository,
branch, base and required SHA. Inspect the current checkout, worktrees, dirty
state and unpublished commits. Safely fetch the canonical branch and switch
to it only when local work is preserved; a clean branch that only lags can be
fast-forwarded. Then compare both local canonical HEAD and refreshed remote
head with the required SHA. An incidental initial branch is not a mismatch.
Never reset, force-push, discard, absorb unrelated work or replace the branch/PR
to satisfy a gate. A real mismatch or unsafe unpublished work is a concrete
boundary. Trusted normalization applies before worker access; a model-modified
worker checkout must still use the trusted import boundary below.

Before any terminal result, including BLOCKED, reconcile task-owned changes
and preserve useful progress in substantive commits. Publish safe, authorized
unpushed task commits to the existing task branch; automatic workers hand them
to Writer. Leave unrelated changes untouched. Remove only confirmed disposable
residue; use ignores for repeatable generated artifacts without hiding work.
State wholly inside an explicitly isolated disposable TEST sandbox follows
[TEST Environment Authority](docs/execution-policy.md#test-environment-authority);
cleanup there does not require individual-file ownership proof or preservation
of disposable state. Preserve useful product-source work and ordinary
worker/Writer collection and publication evidence.
If a safe commit/push or clean handoff is impossible, report exactly what stays
local and the authority, branch, permission or security boundary. Never create
empty or metadata-only commits merely to record status. Explain material
execution warnings even when the result is green.

## Execution context and shells

Identify the actual execution environment and use the shortest qualified
transport that preserves the admitted implementation and authority boundary.
Read the detailed [execution environment and shell routing](CONTRIBUTING.md#execution-environment-and-shell-routing)
rules just in time when command routing, WSL/native-filesystem behavior or
PowerShell/native failure propagation matters. A transport choice grants no
additional credential or production authority. Protected operations outside
disposable TEST retain their source-controlled entrypoints; shell and tool
choice inside its sandbox follows
[TEST Environment Authority](docs/execution-policy.md#test-environment-authority).

## Work within the admitted goal

Use the canonical [progress-bounded execution policy](docs/execution-policy.md)
for correction, stop, prior-state and work-preservation decisions.

Default ordinary repository-only implementation or remediation to automatic
Relay when its required unprivileged checks are available to the governed
worker. Use owner-launched manual/standalone Codex for required capabilities
unavailable to that worker, protected operations outside disposable TEST
authority, or genuine human judgment or choice. This includes protected root
qualification and live host/environment mutation outside that sandbox.
When implementation and protected/manual qualification are both required to
accept one Task objective, default to one owner-launched manual Codex Step
covering implementation, tests, fixes and disposable or explicitly authorized
qualification before one independent exact-head review. Preserve distinct owner,
source-acceptance, installation, credential and original-attempt native
authorization boundaries. Route selection never expands Task/CR authority or
overrides the progress-bounded execution stops above. Any manual or automatic
execution owning an explicitly isolated disposable TEST environment has full
operational control inside its sandbox under the standing
[TEST Environment Authority](docs/execution-policy.md#test-environment-authority)
without per-operation approvals or production recovery procedures. PROD,
shared/foreign resources and external permissions or credentials outside
established authority remain excluded.

For ordinary owner-admitted Relay/Codex work, the default model is
`gpt-6.1-sol`, the default reasoning effort is `xhigh` and the default Subagents
permission is `On`. Explicit live Task or Change Request values override these
defaults; explicit consumer configuration remains owner-controlled. Subagent use
remains discretionary and evidence-driven; permission does not weaken scope,
authority, exact-head, publication, production, credential or protected-boundary
rules. These defaults do not authorize nested Relay execution or retry loops.

## Shared subagent workflow

Upstream: `jresearchsoftware/codex-model-landscape`, `SUBAGENTS.md` from
`main`. When Subagents is On and useful delegation is allowed, read the
[adopted shared guidance](docs/codex/SUBAGENTS.md) just in time before the first
substantial delegation. There is no minimum helper count. Keep the parent's
admitted profile unchanged; local Task/CR authority, execution boundaries and
Writer/Reviewer separation override reusable delegation guidance. Delegation
never expands scope or external authority.

An inner correction does not itself need a new Issue, Step or execution.
A manual task may publish through its explicitly authorized owner channel;
an automatic worker delegates publication to Writer.

## Material User/Operator Contract Change Gate

Removing, replacing, renaming, disabling or materially changing an existing
user/operator capability or workflow requires explicit owner authorization in
canonical Task authority. Legacy Tasks record it in the live Issue body;
migrated schema-v4 Tasks use the stable charter and applicable trusted Decision
resolved into the next admission snapshot. Retained schema-v3 Tasks keep their
complete Request compatibility path. Preserve the charter's protected boundaries and
closure decision. Material surfaces include commands and entry points, required
inputs, visible surfaces, actor responsibilities, automated/manual transitions,
additional required actions, ChatGPT/GitHub paths, and material status, Outcome
or recovery behavior. Internal refactoring with equivalent observable behavior
needs no separate owner decision.

If implementation, security work, tests, Reviewer feedback or remediation
discovers preferable behavior outside that authority, preserve the existing
behavior when safe or stop and surface an owner decision. A technical, security
or test preference is not authorization for a material contract change.

Before independent `APPROVE`, compare the material old and new behavior in every
changed surface as well as the functional and security requirements. An
unauthorized material delta is `OWNER_DECISION_REQUIRED` and blocks approval
until canonical Task authority records explicit owner disposition. Never normalize
an implementation-originated behavior change into policy after the fact.

## Independent review and finding provenance

Before review, read the canonical [review and finding-provenance
contract](reviewer/README.md#independent-review-and-finding-provenance).
Independent native acceptance stays bound to the complete exact head and live
Task/CR authority; implementation helpers and deterministic checks supply evidence.
The material user/operator contract-change gate above remains binding.

## Minimum sufficient ceremony

Follow the [same-Task documentation-maintenance rule](CONTRIBUTING.md#keep-workflow-documentation-current)
when changing human-visible workflows or authority contracts. Use the existing
Task/PR and review; do not introduce a separate documentation approval process.

Before introducing or enforcing a new security, validation, privilege,
filesystem/platform, or operator gate, read
[the pinned proportional-controls protocol](vibevm/vibedeps/org.jresearch.ai.development-governance/2.1.0/vibevm/vibespecs/protocols/proportional-controls.md)
and its [Relay bindings](docs/execution-policy.md#proportional-controls-and-operator-usability).

Apply the shared protocol's [existing-proof rule](vibevm/vibedeps/org.jresearch.ai.development-governance/2.1.0/vibevm/vibespecs/protocols/proportional-controls.md#existing-proof-before-another-step)
when considering another process step. Relay's evidence stays in the live
Issue/CR, PR diff, exact Git facts, native checks and one Writer Outcome.
When deciding whether an earlier requirement binds newly authorized work, read
[requirement-authority](vibevm/vibedeps/org.jresearch.ai.development-governance/2.1.0/vibevm/vibespecs/protocols/requirement-authority.md)
on demand within the current Task/CR authority. These remain the only adopted
shared topics. The other bundled topics, including task-handoff's additional
acceptance strategies and multi-result routing, are references pending separate
owner reconciliation, not activated policy. See the
[ownership mapping](docs/relay-guidance-ownership.md). The full
material user/operator contract-change gate above remains Relay-owned.

Wait for required native CI, but leave reconstructible CI/status results in
their native records instead of posting another PASS comment or Outcome update.
If CI fails and the next correction is clear, safe and in scope, correct it and
rerun the relevant validation. Publish material evidence unavailable from those
records, blockers, authority/boundary changes and required handoff information.

Aggregate related findings, use targeted checks while correcting them, and run
the required full candidate set once before handoff unless a later change or
new failure justifies repetition. Close active references when moving an
entrypoint, identifier, shell or execution context. Deterministic PASS does not
replace independent judgment. Keep inner corrections within the admitted goal
and the progress-bounded stops above.

An accepted reusable architecture, process, governance, security,
qualification or operational decision from owner/ChatGPT discussion must not
remain chat-only. Before the next related execution, carry a decision that
changes executable authority into the live legacy Issue/CR or a trusted Decision
for a schema-v4 Task (plus the complete successor Request for retained schema-v3
work); promote an independently
reusable rule through the next suitable authorized bounded Task/CR into its
existing policy, architecture, runbook or component contract. If it is not
durable policy, classify it explicitly as task-local, temporary, experimental
or rejected when that distinction matters to later execution.

Do not promote casual observations, unaccepted speculation or one-off diagnostic
facts, and do not create a decision ledger or ceremony-only task. A bounded
reusable correction may be promoted without completing the unrelated remainder
of a later backlog item.

Optional [developer hooks](.codex/hooks/README.md) provide bounded diagnostic
reads, session-owned recovery and a bounded Stop reminder. They are not Relay
runtime authority. A missing checkpoint is silent and nonblocking. When useful,
write only the irreconstructible diagnostic frontier through the validated
atomic writer; never store secrets, transcripts or a parallel task ledger.
After recovery revalidate mutable authority and exact Git/runtime facts.

## Preserve the product boundaries

- Edit Relay-managed workflow behavior in `deploy/workflows/*.yml.in`, never
  the installed `.github/workflows/` projection as product source. Use the
  [public projection interface](deploy/README.md#workflow-projection-and-pinned-runtime)
  from an exact accepted product revision; generated consumer changes retain
  ordinary owner review/merge authority. Product CI remains consumer-owned.
- Keep consumer policy, model defaults, credentials, runner configuration and
  operations in consumer-owned configuration. Use synthetic examples here.
- Resolve model, reasoning effort and Subagents once at admission. Omitted
  effort/Subagents fields use the repository defaults above unless explicitly
  overridden by the live Task/CR; they need not be repeated in each admission
  or handoff. These are the execution-profile fields for launch cards, task
  metadata and handoffs;
  an effort identifier does not imply an additional capability switch. Do not
  silently substitute profiles or consult a moving external recommendation
  during execution. Record actual model/effort only when runtime evidence
  exposes them, otherwise `UNAVAILABLE`; requested values are not actual-value
  proof. Record whether subagents were used within the admitted permission.
- Keep owner, worker, Writer and Reviewer responsibilities separate. Review
  acceptance is independent and bound to the exact candidate head.
  Interactive ChatGPT review model/effort is not governance metadata: do not
  require or record it in CRs, handoffs, publication or Outcomes.
- Preserve reservation-before-mutation, replay suppression, non-force Git
  publication, safe paths/modes and scanning of every introduced blob.
- Never run trusted Git against model-modified metadata. Import bounded object
  bytes into a fresh trusted repository and validate them.
- Source changes and local tests do not authorize deployment, credentials,
  service changes, merge, Issue closure or release. Do not claim those proofs.
  Operational control inside an explicitly isolated disposable TEST sandbox is
  separately granted by the standing
  [TEST Environment Authority](docs/execution-policy.md#test-environment-authority).
- For product and ordinary consumer lifecycle operations, follow the
  [first-install/bootstrap and deployment contracts](deploy/README.md)
  just in time for install, upgrade, reinstall or activation work. Reuse only
  validated supported protected state; product-owned bootstrap must remain
  reachable through the public interface, and true external prerequisites stay
  owner-provided. A private-backend-only requirement is a source/interface
  defect, not authority to bypass the public path. Keep clean-environment
  qualification separately admitted when it needs distinct infrastructure;
  successful work on an already prepared host does not prove standalone
  bootstrap or retroactively gate an unrelated task. Disposable TEST cleanup
  and rebuilding follow TEST Environment Authority; public lifecycle interfaces
  and production recovery procedures are optional inside that sandbox.
- Prefer existing GitHub/Git records over a new ledger, registry or workflow
  engine. Add machinery only for a demonstrated product requirement.

## Validate and hand off

For newly admitted schema-v4 manual work, submit structured results through the
bounded owner-connected `submit_manual_outcome` MCP capability to protected
Writer. Writer publishes one canonical Outcome; a public owner result-copy
comment is unnecessary. Retained schema-v3 attempts keep their supported
publication/recovery path. No-PR qualification uses independent Task Approval;
source PRs require independent native exact-head review. Keep material findings,
warnings, evidence gaps and limitations visibly readable before one folded
canonical machine block. Preserve full handoff prompt bytes and historical body
hashes; rendering changes grant no execution or publication authority.

If the required connected App/Reviewer/Writer tool is missing or exposes an
outdated input schema, stop with the missing capability and qualified installation
needed to proceed. Never substitute legacy/v3 publication or routing for new v4
work. The caller checks its available tools; the server cannot observe a stale
client cache or an inaccessible connected App. See the
[capability contract](reviewer/README.md#current-protocol-capabilities).

Use Linux for the runtime and filesystem boundary tests. Run affected suites
during corrections and the complete candidate checks before handoff:

```sh
git diff --check
npm test
python3 -m pytest -q deploy/tests deploy/ansible/tests
cargo fmt --manifest-path reviewer/Cargo.toml --check
cargo test --manifest-path reviewer/Cargo.toml --locked
python3 scripts/qualify.py
python3 scripts/check-candidate.py
```

The candidate check scans tracked files; stage intended additions before using
it. Do not stage unrelated work. For hook changes also run the PowerShell Core
checks and state the platform evidence described in the
[hook contract](.codex/hooks/README.md#qualification). Local contract tests do
not qualify consumer sudo wrappers, process isolation, credentials, ingress or
a production service.
Native checks and independent review remain separate evidence.

Describe the problem and final behavior in the PR. Report the exact final head,
material validation evidence and limitations in one top-level Codex Outcome on
the canonical authority. Link required native checks instead of restating their
reconstructible status; do not add an Outcome update solely to announce CI PASS.
Distinguish implementation complete from independent acceptance. Do not post a
Reviewer verdict for your own work.

Material execution warnings remain mandatory decision inputs at the next owner
or independent review boundary, including when the durable handoff is green.
Inspect and disposition them under
[execution warning disposition](docs/execution-policy.md#execution-warning-disposition).
A successful orchestration status does not resolve a warning. If a required
primary warning or annotation surface cannot be inspected, state the evidence
gap and do not claim that no warnings were observed.

Future task files include `## Recommended model budget` with recommended model,
effort, rationale and escalation/de-escalation conditions. The task author
resolves the model explicitly or delegates it to the admitted consumer
configuration, using the ordinary project profile above unless overridden.
Omitted effort/Subagents fields inherit the repository defaults above; an explicit
live Task/CR may override either.
An interactive prompt cannot change the user's UI model/effort selection.
Keep task-specific authority and execution evidence in the live Issue/PR,
not a duplicate registry.

<vibevm>
<!-- Generated by vibe — do not edit inside this block; it is rewritten on `vibe install`. Text outside the <vibevm> markers is yours. -->

# Session boot

This project's boot sequence is computed by vibe (the PROP-009 loading
model). To begin a session, read these files in order:

1. `vibevm/vibespecs/boot/STATIC.md` — if it exists. The static (priority) lane: read it
   first and in full.
2. `vibevm/vibespecs/boot/INDEX.md` — a generated TOML manifest. Read every file named
   by its `[[entry]]` tables, in the listed order. A `kind = "static"`
   entry is read directly; a `kind = "dynamic"` entry is an INCLUDE
   resolved at boot, and one carrying a `when` condition is read only when
   that condition holds for the current session.

Boot is pure file-reading — there is nothing to execute.
</vibevm>
