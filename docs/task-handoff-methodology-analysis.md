# Task work and handoff: methodology and semantic ownership

Task #108, Step 1. **Analytical evidence, not an adopted protocol or a change of
authority.** Normative reconstruction uses the accepted Relay source at
`b4cb4943d52dd375d8c6800959b3264fad082cb8`. Source keys below pin that revision;
historical and live Issue evidence have separate provenance. This report is one
integrated reconstruction/classification for independent exact-head review.

## The method, usable by people without an automation product

A Task gives work a durable identity and an authorized goal. Its current
canonical record tells people what problem to solve, what success means, which
boundaries must remain intact, and who can authorize changes or completion.
Discussion, plans and observations help explain the work but do not silently
change its authority. An accepted owner decision must reach the designated
canonical record before affected execution. A person can maintain this in an
Issue and explicitly linked decisions; a project using another tracker needs
an equally unambiguous reference and amendment procedure.

Work is organized into explicitly identified Steps: meaningful units of
execution toward the Task. The Task's goal does not prescribe their eventual
number. Investigation, implementation, tests and corrections can belong to one
Step when they form one authorized effort; uncertainty can justify later work.
A completed Step can leave the Task incomplete. A conversation is a workspace,
not the unit that defines progress: it may cover more than one Step where the
project permits. People must know the current Task, Step and purpose rather than
infer them from a long transcript. Exact allocation and retry rules need an
explicit project binding; the stage/attempt distinction is examined below.

A handoff makes the next person's work startable. It points to current
authority, states Task/Step/purpose, the relevant starting result or work state,
permission and environment limits, and the next authorized objective. Use the
canonical reference and necessary hints rather than a second editable copy of
the entire Task. A bounded execution snapshot can be useful, but its origin and
freshness must be verifiable; it cannot silently override current authority.
A short prompt is navigation. Before continuing after interruption, refresh
authority and mutable work facts, then load detail needed for the next decision.

Execute while evidence supports a clear, safe action within the admitted goal.
Diagnose and correct local failures without inventing additional approval
stages for each fix. Stop when scope, permission, prior activity or an external
mutation is uncertain, a material choice needs its owner, or repetition produces
no new evidence. Preserve useful work, leave unrelated work intact, and disclose
what cannot safely be reconciled. A result says what was accomplished, identifies
the exact artifact or immutable evidence available for review, reports checks and limitations,
and distinguishes observations from claims. Blocked work can contain useful
results. No-change or non-code work needs neither an empty commit nor a fictional
change proposal.

Independent review evaluates that exact result against current authority,
acceptance criteria and affected behavior. Passing tests are evidence for this
judgment, not its substitute. Review findings explain the problem, impact,
provenance, correction and acceptance evidence; compare with the starting state
before calling a defect a regression. An actionable request for changes keeps
correction inside authorized scope. A newly preferred user workflow or a
material new obligation needs an owner decision, not retrospective justification
by the implementer. Correct the work and review the new result, addressing prior
findings, changed behavior, adjacent risks and genuinely new findings together.

Acceptance, integration, further execution and Task closure are distinct.
Continue only when current authority authorizes the next action and applicable
checks, acceptance and protected boundaries are satisfied. Already authorized
actions need no repeated ceremonial confirmation. New scope needs its owner.
Known remaining work keeps the Task open; reassess its concrete completion
conditions instead of copying a stale disposition forever. An accepted Step
does not prove the whole Task complete, and source acceptance does not prove
installation, deployment or release. Use existing Task, artifact, check and
review records where they suffice; a universal state machine or parallel ledger
is unnecessary.

## What manual operation and one publishing account can prove

One owner account can maintain an Issue, authorize work, publish commits and a
PR where permitted, and copy an attributed review report into the Task. A
different evaluator can inspect the exact diff and requirements outside GitHub,
or an independent review session can assess the candidate. Record who or what
performed that assessment, which result it covered and which evidence was
available. Merely starting another thread or checking one's own implementation
does not establish independent acceptance.

This can provide substantive review evidence, with disclosed limits on
independence and attribution. Publishing its text through the owner's account
does **not** authenticate a separate reviewer identity, create a native approving
review, satisfy protected-branch requirements, or reproduce Relay's separate
Writer/Reviewer capabilities. GitHub distinguishes comments from approving
reviews and does not let a PR author approve their own PR ([G1], [G2]). A comment
headed `APPROVE` changes none of those facts. If the project's policy requires
native approval from a separate identity, wait for that capability; do not
rename a copied assessment as equivalent proof. If only the implementer is
available, report the independent-review gap and leave acceptance pending.

Relay's current stronger definition includes a separate review session,
publication identity and credentials from the worker/Writer, with exact-head
binding [R]. Its Rust service publishes an external caller's substantive
judgment; it does not conduct the review [V]. That identity boundary does not
guarantee judgment quality or a different human/vendor. Conversely, a manual
project can use an independent evaluator without installing Relay, while
truthfully lacking its machine-verified identity and publication assurances.
What evidence suffices for such a project's acceptance remains an owner policy
choice, not permission to weaken Relay's accepted boundary.

## Ownership by semantic slice

The allocations below are recommendations for downstream authoring, not imports
of authority. **Neutral** identifies portable obligations; **Convention** a
deliberately shared human navigation format; **Product** Relay's versioned
implementation; **Local** a project/client adaptation. Each row splits meaning
from its mechanism rather than assigning a whole source document to one owner.

| Obligation and user problem | Portable meaning, trigger and limit | Current binding and credible manual path |
| --- | --- | --- |
| Task identity and authority: duplicated prompts obscure the actual goal [A], [C], [T]. | **Neutral:** one canonical Task reference, owner-controlled scope and identifiable current amendments. Applies before execution/continuation. Evidence cannot fill missing permission. | **Product:** Task N equals Issue #N; legacy mutable Issue-body authority or explicit `github-native-v1` stable charter plus current trusted snapshot, never both. **Local/manual:** maintain the designated Issue/linked decision records; non-GitHub work needs another identified authority surface. |
| Decisions and currentness: an old instruction survives a correction [A], [C], [T]. | **Neutral:** carry substantive accepted changes into effective authority; distinguish decision, evidence and execution instruction. Refresh changed authority. Historical discussion is not a standing mandate. | **Product:** trusted scoped Decisions normalized into complete schema-v3 successor Requests; digested native references and linear supersession select currentness. Edited source bodies invalidate references; ambiguous/mixed authority stops execution. **Manual:** owner updates canonical requirements or explicitly linked accepted decisions and supersedes stale instructions. No universal digest or JSON requirement. |
| Steps and continuation identity: work stages, sessions and retries get conflated [A], [C]. | **Neutral:** explicitly identify the work unit, distinguish Step completion from Task completion, and preserve continuity without deriving identity from history. Internal test/fix iterations need no separate Step. Counting units is unresolved below. | **Product at baseline:** fresh Step 1, same-phase retry keeps Step, new phase/CR advances by one; one thread may span Steps. Explicit authority supplies Step; labels project it. **Manual:** owner identifies the next work stage using the project's declared rule. #115 proposes a different allocation rule [I115]. |
| Thread navigation: collaborators cannot locate related execution [A], [I14]. | **Convention:** exact `Task N — Step S — <purpose>` for adopting projects, with concise purpose and a canonical Task reference nearby. No requirement for global numbering. | **Product:** Relay's remediation title adds `CR-N-NNN`; this identifier grammar is not necessary to the neutral convention. **Local:** client rename tool, discovery, one-shot call and readback. If unavailable/mismatched, disclose it and use a supported navigation aid; do not claim a persisted rename or block useful work solely on it. |
| Startable handoff: stale copies and missing environment facts misdirect work [T], [W], [A]. | **Neutral:** identify authority, current work unit, starting facts, relevant limits and authorized objective. Load context needed now; refresh mutable facts after recovery. A snapshot is subordinate to its authority, not a second contract. | **Product:** typed request selection, bounded evidence resolution, manual handoff and exact starting-head/PR bindings. **Local/manual:** short prompt with Task link and necessary routing hints; preserve local work and safely normalize the canonical branch before comparing its head. A real mismatch stops work, without reset or branch/PR replacement. Literal headers and client tools stay with adapters. |
| Profile and capabilities: a requested setting is mistaken for actual execution proof [A], [W]. | **Neutral:** communicate relevant limits and report unavailable evidence honestly; delegation never expands authority. | **Product:** admission resolves profile and capabilities once; no silent substitution, requested model/effort is not actual telemetry. **Local:** model defaults, UI selection, Subagents permission and supported clients. **Manual:** state relevant choices/limitations without pretending a prompt changed the UI. No universal model or mandatory helper count. |
| Progress and safe preservation: a failure loses work or causes uncontrolled repeats [A], [E]. | **Neutral:** continue evidence-backed in-scope correction; stop on ambiguity, human choice or unknown prior mutation. Preserve useful work and disclose unreconciled residue. Applies also to blocked results. | **Product:** one execution reservation, replay suppression, retained-attempt recovery without another worker. **Local/manual:** substantive commits or appropriate durable artifacts; inspect ownership before cleanup, preserve unrelated work, and reconcile uncertain actions before repeating them. Retry permission is explicit. |
| Safe publication: proposed bytes are confused with authorized durable results [A], [W]. | **Neutral:** keep execution, publication and acceptance responsibilities clear; preserve work provenance, verify the published target and disclose uncertainty. Scope grants no implicit credential or production permission. | **Product:** credential-free worker; trusted Writer imports bounded objects into fresh Git, scans every introduced blob, validates paths/modes and pushes without force. **Manual:** authorized publisher preserves the branch/result and checks readback. One account lacks Relay's enforced actor isolation; that limitation cannot excuse bypassing its protections. |
| Result versus status: success hides missing proof or warnings [E], [W], [T]. | **Neutral:** bind claims/evidence to the exact result, distinguish completed/blocked work and acceptance, retain material warnings and their impact. Legitimate no-change/non-repository results are exceptions to a PR expectation. | **Product:** one trusted Writer Outcome with Request/attempt/result binding, native IDs or SHA; Draft/Ready projects execution handoff, not CI or acceptance. **Manual:** one result report with artifact identity, checked facts, unverified claims, remaining work and review boundary. No fabricated SHA for a non-code result. |
| Warning disposition: a green run is treated as risk resolution [E], [T], [V]. | **Neutral:** known material warnings need source, impact, disposition, next action and missing evidence before acceptance/continuation. Unavailable evidence is a gap, not absence of warnings. | **Product:** supported Outcome/job/check/controller annotation acquisition; UI-only pre-execution banners are outside mandatory automated acquisition, but a known material warning remains relevant. **Manual:** inspect available primary records and document access limits. Log word searches do not replace the required surfaces. |
| Independent review and finding provenance: self-checks pass for acceptance; baseline debt becomes alleged regression [A], [T], [C]. | **Neutral:** independent substantive judgment of the complete exact result; distinguish introduced, pre-existing, newly exposed/blocking and undetermined findings. Remediation covers baseline defects only through scope or a material dependency. | **Product:** trusted native exact-head PR verdict, or Issue Task Approval for eligible Task results; Task review evidence is not an executable PR CR. **Manual:** separate assessment of an identified revision/result, with evidence limits as above; no artificial PR to obtain a review format. |
| Requests for changes: defect correction becomes an unauthorized redesign [A], [C], [T]. | **Neutral:** actionable findings identify candidate/comparison, impact, correction and acceptance evidence. A surviving blocker needs explanation of the missed invariant or an explicit evidence gap; a new preferred behavior needs owner authority. | **Product:** native PR `CHANGES_REQUESTED`, typed CR, stable findings/head, existing branch/PR and remediation lifecycle. **Manual:** attributed correction request linked to exact result, then authorized correction and fresh review. A task-level finding can instead inform the next work instruction. |
| Material changes and reusable decisions: a technical preference becomes hidden policy [A], [Q], [O]. | **Neutral candidate:** owner-controlled scope and explicit disposition of material behavior/obligation changes; accepted reusable rationale must not stay chat-only. Internal equivalent corrections need no new owner choice. | **Local/Relay governance:** the full material user/operator contract-change gate, protected surfaces and `OWNER_DECISION_REQUIRED` remain operative here. **Manual:** amend canonical Task authority before the material change; promote reusable rules through separately authorized maintenance. #14 does not automatically inherit the whole gate or a new review protocol. |
| Acceptance, continuation and closure: merging a Step falsely completes a Task [A], [C], [T]. | **Neutral:** result acceptance grants only the actions authorized by current policy; check remaining work, holds and protected boundaries. Reassess concrete closure conditions at meaningful authoring transitions. Unknown mutation stops continuation. | **Product at baseline:** native exact-head approval feeds separately governed owner squash continuation; Task Approval grants no PR merge. Charter closure and `continuation` fields, checks/readback and typed related-PR linkage prevent premature closure; missing/malformed/conflicting closure defaults to `keep-open` with a warning. **Manual:** owner performs only authorized integration/next work/closure after checking conditions; no automatic closing reference that bypasses them. |
| Proportionate proof and local delivery: ceremony and tooling crowd out useful work [A], [E], [Q], [D], [I91]. | **Neutral:** reuse evidence for the same invariant/candidate; preserve separately justified checks and independent review. A control needs concrete risk and cost justification. | **Already adopted shared:** proportional-controls and requirement-authority 1.1.0 [Q], [O]. **Local:** English publication, Linux/test commands, shell routing, optional hooks, permissions. **Product:** workflow templates/projection and paired version compatibility. **Manual:** use the project's applicable checks and existing records; ordinary contributors need no owner-admission tooling. Proposed #91 Skill distribution is separate, not implemented at baseline. |

## Syntax, interoperability and the moving product boundary

Precise shared syntax is useful where people recognize the same thing across
projects. For example:

```text
Task 42 — Step 2 — Validate export recovery
```

The ordered Task/Step/purpose and em dashes are the shared visible convention
requested by [I14]. The Task's project/Issue link disambiguates `42`; the title
is neither authority nor a machine security boundary [C]. A client must not
claim a title is persisted merely because its prompt contains it. The tool call
and verification procedure are local; Relay-specific CR suffixes and Actions/PR
title projections need not become universal thread formats.

In contrast, Relay currently renders the product header `## Codex Outcome`
[W2] and a canonical `relay-authority` JSON fence. This **non-executable excerpt**
illustrates field ownership; a real record requires the complete schema [S]:

```json
{
  "schema_version": "3.0",
  "kind": "outcome",
  "task": 42,
  "status": "implemented"
}
```

The neutral meaning is an attributable result bound to work and exact evidence,
with truthful status, warnings and limits. It does not require this heading,
field spelling, version, fence, Bot ID, hash shape or native review enum.
Relay can evolve those together with its parser/publisher contract. Additional
technical fields do not automatically change shared meaning. A field that
changes who may approve, suppresses material warnings, or adds a required owner
action is a semantic change requiring the applicable owner/governance process;
calling it technical does not avoid that boundary.

Three compatibility questions stay distinct: which shared protocol a project
has accepted/adopted; which Relay revision implements its product contract; and
which client/local adapter can expose it correctly. Existing accepted
obligations remain in force until a separately authorized change. #91 proposes
guidance from an accepted pinned product version, with local overlays and no
mandatory VibeVM or automatic ChatGPT settings mutation [I91]. A product upgrade
does not automatically adopt a new shared protocol or update a consumer [D].

The live #115 owner direction is future behavior to implement, **not accepted
source behavior at this report's baseline** [I115]. Its candidate is not a
dependency of this analysis:

| Surface | Accepted baseline [C], [W], [T] | Owner-selected #115 target [I115]; re-map only after acceptance |
| --- | --- | --- |
| Execution authority | Stable charter, trusted Decisions normalized into a complete current public Request/CR snapshot. | Resolve charter/Decisions/CR; remove mandatory public Task Requests; Writer retains immutable admission snapshot. |
| Step and thread | Pre-resolved Step and projections; same-phase retry keeps Step; thread can span successive Steps. | Allocate Step per newly admitted execution attempt; fresh execution after blocked gets a new Step; publication replay retains Step; fresh manual thread for a new attempt. |
| Manual result | Owner authorization comment with `relay-manual-result`, then trusted Writer Outcome. | Narrow MCP submission directly to Writer, one Outcome, separate Writer/Reviewer capabilities. |
| Closure/continuation | Charter closure policy plus Task-complete continuation and verified acceptance/no remaining work. | Effective trusted closure decision with completion reconciliation; avoid contradictory completion policy while retaining necessary acceptance distinction. |
| Presentation | Current canonical blocks, headers, handoff and projections. | Readable summaries, folded machine detail and presentation-only handoff folding when usable; preserve canonical provenance and substantive limits. |

The Request, result transport and rendering rows are product bindings. Step
allocation exposes a genuine conceptual choice, not just different field names.
Closure changes also need verification that owner permission and actual
completion remain distinct. #91 should rebase these mappings onto the newly
accepted exact product revision, validate old/in-flight compatibility, and state
which revision its adapter supports. Nothing here adopts the #115 candidate.

## Reconstruction refined by classification; unresolved questions

Comparing the Step slice to #115 reopened the initial stage model. A meaningful
stage, a fresh execution attempt, a publication replay and a conversation are
four different concepts. At baseline, more than one attempt can retain a Step
and one conversation can span Steps. The proposed product rule instead makes
admitted attempts allocate Steps. Both retain bounded iteration inside an
execution and distinguish replay from new work. Therefore the defensible common
core is explicit Task/work-unit identity, declared allocation semantics and
truthful continuity; stage counts are not a productivity or completion measure.
This refinement does not change this admitted Step or infer future numbering.

| Residual question | Evidence and bounded recommendation |
| --- | --- |
| Must shared `Step` always mean a semantic stage, or may an adapter define it as an admitted attempt? | [A], [C] versus [I115]. Ask #14's owner to decide before declaring a universal counter rule. Recommend leaving allocation/retry/thread-reuse rules explicit in the versioned binding, while requiring meaningful purpose, stable identity during inner corrections and no advancement on approval/replay. If a universal stage concept is desired, first explain its relation to attempt-numbered Steps; do not invent another counter here. |
| What qualifies as independent acceptance with one publishing account? | [R], [V], [G1], [G2] establish Relay's stronger assurances and the native platform limit. Recommend shared guidance require substantive independence, attribution and disclosed identity-proof gaps; let each owner specify sufficient acceptance evidence. Whether an external assessment published by the owner suffices is a material policy choice. It cannot substitute for Relay's mandatory native identity boundary. |
| How far does exact title syntax extend? | [I14] selects Task/Step/purpose, while [A] adds a Relay CR grammar. Recommend the selected common title for adopting projects, nearby project/Task reference for collisions, and a disclosed fallback when rename is unavailable. Leave non-numeric trackers and universal remediation-title grammar for explicit owner disposition; do not generalize the Relay CR identifier without evidence of cross-project need. |
| Can the pre-Relay historical origin be verified? | The earliest available Relay policy [H1] already contains identity/title, bounded execution, independent exact-head review and minimum ceremony. [H2] strengthens persisted-title verification. Anonymous lookup of `jresearchsoftware/docs-evolution-review` returned 404; public repository search found no matching repository. That does not prove absence. No pre-Relay source was inspected and no historical-origin claim is proven. Current authority and user-problem reasoning support the reconstruction; provide an exact source/reference later if an origin dispute materially affects acceptance. |

The gap about independence also deepened the conceptual result model: reviewed
content, attributed reviewer judgment, authenticated publication identity and
authorization to integrate are separate evidence claims. Neither a Bot verdict
nor a copied manual verdict proves all four. These refinements stay in this one
report; they introduce no extra analysis Step, ledger or approval gate.

## Acceptance walks

These are desk-based semantic checks of the proposed allocation, not claims of
live client, Skill, deployment or downstream-protocol qualification.

1. **Manual project, no Relay, one publishing account.** The owner defines Issue
   #42, authorized export-recovery work and remaining qualification. The handoff
   links the Issue and names Step 1. The implementer preserves a candidate
   revision and reports local checks plus unavailable environment proof. A
   separate evaluator reviews that revision against the Issue; the owner
   publishes the attributed assessment and limitations. Pass: Task/result/review
   are traceable without product schemas. Native separate-identity approval is
   still absent; if required by policy, acceptance/integration waits. If no
   independent evaluator/session is available, report that gap. Do not close
   while the stated qualification remains.
2. **Project with a version-compatible Relay Skill.** This is a future #91
   acceptance scenario: separately accept/adopt applicable shared guidance,
   select an accepted product revision and qualify its supported Skill/client
   mapping. For the baseline described here, the Skill routes to a stable charter,
   complete trusted schema-v3 Request, matching projections and chosen ready
   command. Worker commits reach Writer; one bound Outcome reaches independent
   native exact-head review. Pass: human conventions agree, product authority
   stays singular, local checks/profile remain local, and incompatible guidance
   stops before launch. A Skill is neither credentials nor reviewer acceptance;
   #115 requires a freshly verified mapping after its acceptance, not these old
   Request instructions. No such Skill was installed/tested by this analysis.
3. **Renamed and continued multi-stage work.** Step 1 implements export recovery;
   owner-authorized Step 2 qualifies it. Under baseline rules the canonical next
   instruction advances the Step and can reuse the conversation. Update its
   visible name to `Task 42 — Step 2 — Validate export recovery` where supported;
   retain links to Step 1's result and current authority. Pass: the new title
   locates work but does not authorize it, inner fixes/approval do not increment
   Step, and Step 2 completion alone cannot close the Task. If rename/readback
   fails, disclose the actual state and use the canonical reference. The #115
   attempt/thread rule, if accepted, changes this adapter path explicitly.
4. **New product field, unchanged shared meaning.** A future accepted Relay
   version adds a diagnostic `trace_id` to a result. Current schema [S] rejects
   unknown properties, so implement and qualify the product schema/parser/
   publisher/guidance change together; do not append the field to today's
   record. Pass: exact result, warnings, reviewer independence and permissions
   are preserved, product compatibility is explicit, and shared governance
   needs no release merely for the field. A required extra owner action or
   altered approval authority would instead trigger a semantic decision.
5. **Classification requires deeper theory.** A proposed shared rule says every
   retry must reuse Step because Step means stage; an attempt-based adapter
   allocates a fresh Step after blocked execution. Before prescribing either,
   reconstruct whether retry means an inner correction, new admitted execution
   or uncertain publication replay, and what navigation/completion problem the
   number solves. Pass: inner work and replay preserve identity, fresh execution
   has explicit authorization, uncertain mutation is reconciled, and the owner
   chooses the remaining stage/attempt policy. The resulting boundary changes
   only that slice of this analysis; it does not launch a second analytical Step.

## Evidence handoff for the two downstream owners

**Shared Governance #14:** use the conceptual narrative, manual limitations,
Neutral/Convention slices, acceptance walks and residual questions as evidence
for separately authorized neutral protocol authoring. Preserve the selected
visible thread convention, but decide Step semantics and manual acceptance
assurance explicitly. Do not copy Relay fields, native identities, transport or
the full local contract-change gate. The already adopted [Q], [O] protocols keep
their own authority/version; acceptance of this report does not release or adopt
a new one. Challenges can revisit the identified slice and its pinned source
without repeating the inventory.

**Relay #91:** use the Product/Local slices and syntax/compatibility section for
separately authorized human guidance and native Skill work. Start from [T], [C], [W], [V], [S], [D], the applicable separately accepted shared protocol and the selected
accepted product revision. Reconcile the #115 rows if it has been accepted;
qualify native-client discovery, prompt/title behavior, local overlays and
versioned update/rollback in that Task. A Skill must not imply automatic
ChatGPT settings synchronization, new authority or identity proof. Report
acceptance does not authorize distribution, installation or consumer mutation.

Independent review of this report should assess semantic completeness,
preservation of material triggers/exceptions, source provenance, manual-path
honesty and the unresolved boundaries. Writer's exact published candidate and
Outcome identify the review target; source links identify the reconstruction
baseline, not acceptance of this report. #108 remains keep-open pending its
independent acceptance and separately governed downstream handoffs or explicit
owner disposition. Local checks cannot prove those events.

## Source references and evidence limits

Current repository links below use the exact accepted baseline above; H1/H2
are explicitly historical. Section names identify the relevant slices. These
references remain evidence if product source subsequently changes.

| Key | Exact source and relevant section |
| --- | --- |
| A | [AGENTS.md][A]: Task identity and startup rename; Canonical checkout and safe Git handoff; Work within the admitted goal; Material User/Operator Contract Change Gate; Independent review and finding provenance; Validate and hand off. |
| R | [README.md][R]: opening definition of independent review and responsibilities. |
| C | [contracts/README.md][C]: GitHub-native Task authority; Closure policy authoring; Continuation after changes requested; Authorized continuation after independent acceptance; legacy compatibility introduction. |
| T | [docs/task-workflow.md][T]: From Task to completion; Decisions and subsequent work; When PR review requests changes; Warnings, blockers and continuation; Compatibility and local policy. |
| W | [controller/README.md][W]: Issue-authorized implementation continuation; Issue publication and worker handoff; Publication, execution handoff and integration readiness; Writer publication recovery. |
| W2 | [controller/src/outcome.mjs][W2]: `boundOutcomeBody`, `workerOutcomeClaims`, `terminalOutcomeBody`: typed result, claim separation and `## Codex Outcome` header. |
| V | [reviewer/README.md][V]: opening external review authorship; typed publication/Task Approval; bounded warning evidence. |
| S | [contracts/src/github-authority-v1.json][S] and [examples/task-authority.md][X]: schema-v3 records and complete synthetic authoring examples. |
| E | [docs/execution-policy.md][E]: progress-bounded stops, preservation, warning disposition and conditional developer stop evidence. |
| D | [deploy/README.md][D]: Workflow projection and pinned runtime; [workflow contract][F] is `relay-workflows-v2`. |
| L | [CONTRIBUTING.md][L]: ordinary contributors; Keep workflow documentation current; Execution environment and shell routing; Local validation. |
| Q/O | Adopted development-governance 1.1.0 [proportional-controls][Q], especially Existing proof before another step, and [requirement-authority][O]. These adopted topics are not a Task Handoff protocol. |
| H1/H2 | Historical only: [initial Relay AGENTS.md at `c0e0b5ce3f52a311f473eca3a9f8694eb75c23f8`][H1]; [persisted-title clarification at `0530452ac6d5b9d309ba9395415669062e34fadb`][H2]. Read selectively to test continuity and naming rationale; neither supersedes A. |
| I108 | [Live Task #108][I108], anonymously read 2026-10-11: charter body SHA-256 `fa601dedfd20c47cc270a74ce380e6608105037f148dd139ca8a86c31c573f50`, matching admitted authority. The supplied trusted Request governs this execution. |
| I14/I91 | [Shared Governance #14][I14], body SHA-256 `c08666ba78f7a80561c3ec8da7560cc7a0b9bde285dcdc8b37dbe711724a1442`; [Relay #91][I91], `12b32267eac1fb6edcb64c1359b64a6f58f7540d1fe927a10b9afde040245cc0`, anonymously read 2026-10-11. Backlog authoring directions/evidence, not active implementation or adoption authority. |
| I115 | [Live Task #115][I115], anonymously read 2026-10-11: body SHA-256 `c36bf4e867ba254818d1e0807329ab50387c8e53eccdc2e751b9cbb5b87f646f`. Owner-selected future behavior, treated as unaccepted implementation per this Task's Request; no candidate source or acceptance verdict was used. |
| G1/G2 | GitHub's [review decision types][G1] and [review submission/self-approval limits][G2], read 2026-10-11. Platform facts only, not Relay Task authority. |

Issue URLs are mutable; the observed full-body digests identify the evidence
read, not immutable policy or permission to act. Earlier `docs-evolution-review`
history remains unavailable, so the reconstruction of its motivation is an
inference, not an archival finding. Live PR acceptance, installed-runtime proof,
Skill/client behavior and downstream adoption were not qualified. Execution job,
check and controller primary warning annotations were not inspected: no trusted
attempt/job/check evidence target was supplied to this credential-free worker,
and Reviewer invocation is prohibited here. The owner/reviewer must inspect
supported surfaces for the actual attempt and published candidate. No
absence-of-warnings claim is made.

[A]: https://github.com/jresearchsoftware/codex-relay/blob/b4cb4943d52dd375d8c6800959b3264fad082cb8/AGENTS.md
[R]: https://github.com/jresearchsoftware/codex-relay/blob/b4cb4943d52dd375d8c6800959b3264fad082cb8/README.md
[C]: https://github.com/jresearchsoftware/codex-relay/blob/b4cb4943d52dd375d8c6800959b3264fad082cb8/contracts/README.md
[T]: https://github.com/jresearchsoftware/codex-relay/blob/b4cb4943d52dd375d8c6800959b3264fad082cb8/docs/task-workflow.md
[W]: https://github.com/jresearchsoftware/codex-relay/blob/b4cb4943d52dd375d8c6800959b3264fad082cb8/controller/README.md
[W2]: https://github.com/jresearchsoftware/codex-relay/blob/b4cb4943d52dd375d8c6800959b3264fad082cb8/controller/src/outcome.mjs
[V]: https://github.com/jresearchsoftware/codex-relay/blob/b4cb4943d52dd375d8c6800959b3264fad082cb8/reviewer/README.md
[S]: https://github.com/jresearchsoftware/codex-relay/blob/b4cb4943d52dd375d8c6800959b3264fad082cb8/contracts/src/github-authority-v1.json
[X]: https://github.com/jresearchsoftware/codex-relay/blob/b4cb4943d52dd375d8c6800959b3264fad082cb8/examples/task-authority.md
[E]: https://github.com/jresearchsoftware/codex-relay/blob/b4cb4943d52dd375d8c6800959b3264fad082cb8/docs/execution-policy.md
[D]: https://github.com/jresearchsoftware/codex-relay/blob/b4cb4943d52dd375d8c6800959b3264fad082cb8/deploy/README.md
[F]: https://github.com/jresearchsoftware/codex-relay/blob/b4cb4943d52dd375d8c6800959b3264fad082cb8/deploy/workflows/contract.json
[L]: https://github.com/jresearchsoftware/codex-relay/blob/b4cb4943d52dd375d8c6800959b3264fad082cb8/CONTRIBUTING.md
[Q]: https://github.com/jresearchsoftware/codex-relay/blob/b4cb4943d52dd375d8c6800959b3264fad082cb8/vibevm/vibedeps/org.jresearch.ai.development-governance/1.1.0/vibevm/vibespecs/protocols/proportional-controls.md
[O]: https://github.com/jresearchsoftware/codex-relay/blob/b4cb4943d52dd375d8c6800959b3264fad082cb8/vibevm/vibedeps/org.jresearch.ai.development-governance/1.1.0/vibevm/vibespecs/protocols/requirement-authority.md
[H1]: https://github.com/jresearchsoftware/codex-relay/blob/c0e0b5ce3f52a311f473eca3a9f8694eb75c23f8/AGENTS.md
[H2]: https://github.com/jresearchsoftware/codex-relay/commit/0530452ac6d5b9d309ba9395415669062e34fadb
[I108]: https://github.com/jresearchsoftware/codex-relay/issues/108
[I14]: https://github.com/jresearchsoftware/shared-governance/issues/14
[I91]: https://github.com/jresearchsoftware/codex-relay/issues/91
[I115]: https://github.com/jresearchsoftware/codex-relay/issues/115
[G1]: https://docs.github.com/en/pull-requests/reference/pull-request-reviews#review-decision-types
[G2]: https://docs.github.com/en/pull-requests/how-tos/review-pull-requests/reviewing-proposed-changes-in-a-pull-request#submitting-your-review
