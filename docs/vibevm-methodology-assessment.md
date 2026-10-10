# VibeVM methodology compared with Relay

Task [#102](https://github.com/jresearchsoftware/codex-relay/issues/102), Step 2,
CR-102-001; remediation of research gaps F-104-01 and F-104-02 in the reviewed
Step 1 candidate `09f87c3ebf8462dd6a09a86ca5abe2b19d796439`.
Research against Relay `4f0e0e38980854fcb09dc718841ade3102a8108f` and VibeVM
1.0.7 `b6659978453f50e6d1d4d99626d70b980a2c5847`. This report proposes choices;
it changes no execution policy, routing, recovery or acceptance contract.
The Issue stays open for independent acceptance and owner disposition.

## Findings and decisions

**No methodology migration is justified yet.** The inspected source and small
offline experiments establish mechanisms and gaps, not comparative agent
performance. The most useful upstream ideas are a concise diagnostic handoff,
addressable rationale, and deliberate reconciliation when code leads its
documentation. Relay can adapt these within its existing Task evidence and
same-Task documentation process. A mandatory central WAL, second cold-resume
file, separate checkpoint commits and new approval rituals have not earned
their recurring cost in this repository.

That conclusion does not mean Relay already solves everything. Its optional
recovery notes are owned by one session, expire, and do not transfer private
unfinished reasoning to a different session. The optional upstream WAL package
explicitly designs for another machine, teammate or long gap. This is a genuine
structural advantage for cold handoffs, although neither its practical frequency
nor resulting correctness improvement has been measured here.

**Native routing option C can proceed conditionally with existing Relay policy.**
The accepted routing investigation and its reproduced probe show that the
native generator can route to user-authored, bounded Relay instructions without
installing the upstream methodology. Conditions remain: a separately admitted
Task #99 implementation, policy-preserving authored boot text, exact-head
validation and independent review, plus disposition of the generator's lifecycle
limits. This report neither activates that route nor assesses an unmerged Task
#99 successor. Methodology hybrid **C below is a different alternative from
routing option C**; neither implies adoption of the other.

**Principle-level Spec-first is compatible conditionally:** define Spec as
currently accepted formal requirements and Human as intent admitted through
trusted canonical authority. A personal objection to a clear, safe admitted
requirement does not itself require another approval. This interpretation does
not make every instruction in the pinned packages compatible: package inclusion,
boot delivery and linked protocol wording must also preserve Relay's stops,
scope and same-Task documentation behavior. The package feasibility and formal
Spec sections below distinguish these questions. No overlay is evidence that
an unchanged contradictory instruction has disappeared.

## Evidence and attribution

### Revisions and accepted workflow evidence

During Step 1, the live Issue body retrieved anonymously through the GitHub API matched the
admitted charter SHA-256
`9947ad075577a4d27fbee250e011a7ac29b53e1aaeb55aa11c9737dda458b850`.
The complete [Request](https://github.com/jresearchsoftware/codex-relay/issues/102#issuecomment-6097671313)
had body digest
`aaa372b4d8ee93a026f5935803e42877c0608c27f17c906c31082efc7ae4e30a`,
the admitted branch/base/starting head, Step 1, and no selected Decisions.
Those historical digests bind the observed bytes; native comment URLs alone are mutable
evidence, not immutable content or permission to expand scope.

Step 2 uses the supplied complete trusted CR-102-001 Request: Step 2, the same
base and reviewed head above, branch `codex/task-102`, no selected Decisions or
context, research-only scope and keep-open closure. The earlier Step 1 Request
is superseded, not current authority. Neither cached GitHub snapshots nor this
report can amend the current Request. The admitted base is already an ancestor
of the starting head; no integration merge or Task #99 successor is needed.

The previous [Writer Outcome](https://github.com/jresearchsoftware/codex-relay/pull/100#issuecomment-6097275516)
identifies candidate `4fb06b5ad925996d38fdf330bb655c67dce0e067`.
Its body digest at inspection was
`fd6ac0d70b10bcee85ce89b1f3ee74e48f4f622737d679ee66e5b448f53a8f53`.
The [independent review](https://github.com/jresearchsoftware/codex-relay/pull/100#pullrequestreview-5478964959)
accepted that exact candidate, separated source/tool results from unverified
model behavior, and disposed its available warning evidence. Its inspected
body digest was
`546753ebf8d2628c424f6dcebfcf45dde9d5e7a3422af51c7a95467503cfd122`.
PR #100's merge revision is this study's admitted base. These are actual
examples of Relay's evidence and acceptance separation, not trials showing
that one methodology outperforms another. Earlier review/CI does not validate
Task #102's new candidate.

Upstream was fetched as a source archive of the exact accepted commit, without
installing packages into a consumer. The retrieved archive SHA-256 was
`15f71c255a8b114183804142ad2e21014ea37b4c774c98471bc12425c3f18afb`;
the commit and individual file bytes, rather than archive packaging, identify
the source. The tool binary independently matched the
[existing pin](../toolchain/vibevm.json): SHA-256
`20d111df02eb28040ef4cb766bfcb0bde8ff4427b031f88f33eacb3711c3e240`,
69,220,496 bytes, version `vibe 1.0.7`.

### Four distinct upstream layers

| Layer | What is actually present | What it does not establish |
| --- | --- | --- |
| User-owned stock seed | `init` seeds `00-core.md` and `90-user.md`; existing authored files are preserved. Core prose describes startup, memory and precedence [U1, U2]. | A sentence is not an enforced model capability. Stock init creates neither WAL nor installed WAL package. |
| Generated router | Managed agent redirects, boot composition and INDEX deliver authored instructions [U3]. | Routing is not admission, semantic conflict resolution, a checkpoint writer or independent acceptance. Generator locking is not a lock on agent-written WAL state. |
| CLI WAL checks | Optional-file resolution, section checks, mtime freshness diagnostics and read-only project checking [U4, U5, U6]. | No verification of repository/Task/head ownership, claim truth, session read/write compliance, or a mandatory stale-state block. |
| Optional packages/presets | `org.vibevm.world/wal` 1.0.0 contains flow prose and a status skill [U7–U10]. Sync-from-Code and conflict-protocol are separate flows [U11, U12]. Redbook and wal-specspaces are further conventions [U13]. | Presence inside the upstream source tree does not mean installed in a fresh project or in Relay. `impl/done` annotations are source assertions, not observations of Codex compliance. |

All U references at the end point to immutable upstream source. The optional
package's own manifest declares a flow, a boot snippet and a skill; the inspected
WAL protocol is instruction content, not a demonstrated transaction/replay
engine. Its scope explicitly permits many WALs or none for multi-developer
projects and states that installing/uninstalling it does not create or overwrite
project WAL/CONTINUE files [U7, lines 57–70]. This exception matters: central-WAL
contention is not evidence that VibeVM requires an unsuitable universal design.

For byte-level reproduction, inspected file SHA-256 values are:

| File, relative to pinned upstream | SHA-256 |
| --- | --- |
| `crates/vibe-cli/templates/boot-00-core.md` | `977d29101ca2f881cd28854e4aae01eb1622f3733d370411c2648ab9c251d81b` |
| `crates/vibe-check/src/checks/wal_freshness.rs` | `d4b71f65cdc10b249cb211f90deeb851770711c5e93f342cd3f6b87d22b98c98` |
| `crates/vibe-check/src/checks/wal_wellformed.rs` | `091d6f3851e033643a0455dd242919c524ffc586047fee6d1876c954b9a91566` |
| `vibevm/vibepacks/org.vibevm.world/wal/v1.0.0/vibevm/vibespecs/flows/wal/WAL-PROTOCOL.xml` | `7cd00a7eb38fca3811449166dc86e5157312e16c5ee06ff0b797112e9cdbb898` |

## What the disciplines mean in practice

### Checkpoints, freshness and recovery

The stock seed treats WAL as current state rewritten per session, rather than
an append-only journal. It asks sessions to read boot material and WAL before
task-relevant specifications and to confirm old state before destructive work
[U1]. The optional WAL flow adds a richer repository handoff: current phase,
reasoned constraints, completed/open work, next action and known issues;
a subordinate `CONTINUE.md`; checkpointing at session end, before destructive
operations and when switching context; and a size target of 3,000 tokens
with a 5,000-token hard limit [U8]. These are potentially useful constraints on
handoff quality, but token budgets and claimed completion times are not measured
benefits in this Task.

The package's freshness instruction uses the embedded `_Updated:` timestamp
and calls for user confirmation before trusting stale claims [U7]. Its cold
resume process empirically checks Git facts and treats a recorded next action
as a candidate, then reports and waits for direction [U9]. It therefore should
not be portrayed as blindly executing whatever an old checkpoint says. The
WAL protocol also places the checkpoint below spec and empirical code/test
evidence in a disagreement [U8, lines 136–145]. This extends the seed's intent
hierarchy with a subordinate state checkpoint; “canonical WAL” means precedence
over its resume snapshot, not over intent or empirical evidence.

The executable CLI guard is weaker and different. It resolves either
`vibevm/vibespecs/WAL.xml` or `WAL.md`; no WAL is permitted; both forms produce
an error. It checks five headings and filesystem mtime, not the embedded date
or semantic consistency. Age is truncated to whole hours and warned only when
that value exceeds 24, so 24h30m is accepted. Future mtime produces information;
old mtime and missing headings produce warnings with exit 0 [U4–U6]. The
offline observations below confirmed this distinction. A fresh checkout or
touch can make old content look fresh to this check; that is a mechanism risk,
not a measured frequency of bad resumes.

Relay's durable continuity unit is the canonical Task and exact results:
stable charter, complete trusted Request/CR, accepted Decisions normalized into
it, selected evidence, Git/PR changes and Writer Outcomes. Outcomes do not
become another Request. Supersession and body digests select authority instead
of comment recency or remembered state. The
[GitHub-native contract](../contracts/README.md#github-native-task-authority)
documents these bindings and independent acceptance.

The [optional recovery helpers](../.codex/hooks/README.md#session-owned-checkpoint)
save only a bounded irreconstructible diagnostic frontier, validate before
atomic replacement, isolate sessions and expire notes/captures after 24 hours.
Missing, stale or malformed notes do not block work. Compaction captures an
already valid note and consumes only that session's capture; it cannot recover
reasoning never written down. A different session cannot read the foreign
note. Exact Git and mutable authority must be refreshed after recovery.

This separation protects authority and avoids central state contention, but
can lose an unfinished investigation's rationale across independent sessions.
Git preserves a patch, not why three hypotheses were ruled out. A compact
selected Outcome/finding can preserve that knowledge if someone records and
selects it; the current contract does not guarantee that all private frontiers
are captured. Upstream's shared handoff addresses this omission directly. Its
session-end ritual also cannot save a frontier from an abrupt crash before the
write. Neither approach demonstrates automatic recovery of unwritten thought.

### Intent, specifications, tests and code

The stock ordering is **Human > Spec > Tests > Code** [U1]. As a design
heuristic it encourages explicit intent and discourages rationalizing every
implementation as the desired behavior. A clear accepted contract can rightly
require changing a stale test. It cannot establish whether a particular human
utterance is current, authorized, scoped or consistent with protected limits.

Relay adds those distinctions. An admitted Request is executable authority;
ordinary discussion and historical results are evidence. The stable charter
and protected policy bound execution; affected component contracts are loaded
when relevant. A boot specification cannot override this chain. A fresh
"just change the timeout" message in a governed worker is not automatically a
complete trusted successor Request. This is an authorization distinction, not
a claim that human intent is unimportant or that tests outrank the owner.

Relay also does not reduce its authority chain to a globally ordered list of
documents. A genuine conflict between an accepted specification, the Request
and protected behavior requires reconciliation. Within clear admitted scope,
the implementer can repair an obsolete test oracle. Without clear authority,
it must preserve safe behavior and surface the decision. The
[material contract gate](../AGENTS.md#material-useroperator-contract-change-gate)
and [progress-bounded stops](execution-policy.md) protect this distinction.

The seed's disputed-spec instruction delays the report until after
implementation [U1]; separate conflict-protocol prose elaborates marker and
resolution practices [U12]. It also resists treating newer code as authority
and weakening tests to obtain a pass. Its analogy places tests beside the spec
as well as below it; its assertion that exactly one side of a conflict is wrong
does not cover a spec and test sharing a mistaken or underspecified oracle.
This can reduce interruption when the only
disagreement is an implementer's preference about an already authorized,
safe design. It is unsafe as a universal rule when the specification requires
an unauthorized operator change or the next material correction is genuinely
ambiguous. A review marker records disagreement but does not grant permission
or ensure that independent reviewers discover it. The executable aging check
ignores undated markers, while the seed's example has no date [U14]; the probe
confirmed that omission.

Calling code/tests regenerable artifacts is not a license to discard useful
evidence. A specification can be mistaken, a test can encode a real edge case,
and a passing suite can share the same wrong oracle as the code. The current
[independent review rules](../AGENTS.md#independent-review-and-finding-provenance)
require comparison with the starting/base state, exact SHAs and provenance:
introduced, baseline, newly exposed, or undetermined. Changing validation does
not retroactively make baseline debt a regression. The inspected VibeVM seed
does not supply an equivalent exact-head independent review/publication
boundary; the absence there is not proof that every optional package lacks it.

### Sync-from-Code and durable rationale

Sync-from-Code recognizes the useful inverse case: code changes before the
specification, and restoring code to stale prose can destroy an intended fix.
The optional flow collects an actual diff, reconstructs intent, drafts the
specification delta with value/reason/revisit trigger, and waits for human
approval. It excludes temporary experiments and mechanical changes; rejection
can mean restoring code or redrafting the proposal [U11, lines 42–68, 74–139].
The stock seed mentions a proposal, but does not by itself install that full
protocol. A diff proves what changed, not why, and does not prove the new
behavior is authorized. The example's quantitative rationale is upstream
illustration, not a measurement made in Relay.

Relay's [same-Task documentation rule](../CONTRIBUTING.md#keep-workflow-documentation-current)
already requires affected behavior, responsibilities, shell and recovery
documentation to stay synchronized. Accepted reusable decisions must move into
the existing canonical contracts through authorized work. Routine equivalent
fixes do not need a separate documentation approval process. The upstream
value/reason/revisit pattern can make these edits easier to assess; applying
its universal explicit-apply pause would add a workflow step that the owner
has not authorized. For a material behavior change, a trusted Decision and
complete successor Request are necessary before implementation; a retrospective
spec sync cannot legitimize a worker-originated change.

Addressable specifications help cross-project reuse and explain constraints.
Relay's existing Markdown anchors, component contracts and exact Git revisions
can provide this benefit without moving documents into PROP/FEAT files or
requiring `spec://` tooling. Shared packages could improve navigation and reduce
drift, but each repository still needs bounded authority and compatibility
acceptance. A producer's new pin is not a consumer's migration decision.

## Formal Spec interpretation v1 (research definition)

For this comparison, **Spec** means applicable currently accepted requirements
for one admitted execution, with their trust, scope and amendment provenance.
**Human** means owner intent admitted through Relay's canonical authority;
casual chat remains discussion unless the applicable authorized process admits
it. This is a versioned analytical vocabulary, not a new schema, file, registry,
operational gate or activated instruction. It preserves the existing
[authority contract](../contracts/README.md#github-native-task-authority).

| Source | Normative role | Provenance and precedence |
| --- | --- | --- |
| Stable charter | Task goal, scope, protected boundaries and closure decision | Canonical repository/Issue and observed body digest. Bounds the execution Request. |
| Current complete trusted Task Request/CR | Executable Step/profile/route/scope/validation/start snapshot; CR binds reviewed head and findings | Trusted publisher, native parent/body identity and digest, uniquely resolved explicit supersession chain. Neither comment recency nor largest Step selects it. |
| Applicable trusted Decisions | Durable semantic amendments normalized into the selected complete Request | Correct trust, binding, ancestry and selection; normalization must agree with Request. A Decision does not launch work or silently amend an existing Request. |
| Accepted reusable governance | Cross-task authority, security, publication, review and protected obligations | Accepted revision and applicable clause. Proposed candidate policy edits are not silently accepted policy. |
| Affected accepted component contracts | Applicable behavior and explicit extension points | Accepted revision/section and surface applicability. Specialization cannot weaken protected obligations. |
| Tests, code, Git facts, Outcomes, selected discussion | Empirical conformance, history and finding evidence | Exact candidate/comparison SHAs or verified evidence identity. These do not independently authorize execution. |

This is a conjunction of applicable requirements, **not a total document
ranking**. Resolve trust, applicability and explicitly authorized supersession
first. A complete authorized change can identify older component prose as stale;
newer code alone cannot. If accepted obligations still conflict, preserve safe
behavior and protected boundaries, identify contradictory clauses, and obtain
canonical reconciliation before the affected mutation. A passing suite, package
boot or newer human comment cannot choose the winner. Accepted discussion that
changes executable authority must enter the canonical amendment and complete
successor Request before related execution. Legacy Issue-body authority keeps
its existing role; this definition does not implicitly migrate legacy Tasks.

### Five formal-Spec edge cases

These are source-grounded scenario analyses, not five observed agent sessions.
The last column describes requirements for a possible adapter; the dependency
probe below decides whether current packages can actually deliver them.

| Case and authoritative trigger | Relay under formal Spec v1 | Literal pinned package instructions | Safe adaptation and remaining conflict |
| --- | --- | --- | --- |
| Accepted Spec A versus baseline stale test B | Diagnose the oracle against exact starting/base facts; repair within scope while preserving useful edge coverage. Record baseline versus introduced provenance. | Conflict protocol permits repairing yesterday's test, but also asserts one side must be wrong. Both may share a mistaken oracle or describe different underspecified cases [U12, U15]. | Intent-led diagnosis is compatible. Neither wholesale test weakening nor PASS alone proves correctness; retain independent exact-head review. |
| Stale component Spec B versus a current Request explicitly authorizing code-first fix A | Keep authorized A; reconcile affected docs in the same Task/PR. Diff proves what changed; canonical intent establishes why permitted. | Sync usefully prevents reverting intended code to stale prose, but main boot/protocol require same-session draft, separate explicit approval and prescribed docs commit [U16, U11]. | Value/reason/revisit explanation fits existing doc work. Mandatory extra apply/approval/commit ceremony requires an owner decision or a new compatible publisher version. Code recency itself grants no authority. |
| Implementer disputes a clear, safe accepted Spec A | Implement admitted A and record preference/disagreement in existing review context. Personal preference does not create a blocking ambiguity. | Implement-then-report overlaps here; REVIEW marker/lifecycle requirements also apply [U12, U15]. | Principle compatible in this bounded case. Marker use must not replace durable evidence or independent acceptance; new compulsory markers need owner disposition. |
| Ambiguity or unauthorized operator change would remove a command/add a gate/change actor responsibility | Preserve safe behavior and stop the affected mutation; surface the precise canonical owner decision. A retrospective doc sync cannot authorize it. | Main conflict boot prescribes implementation of disputed Spec and conservative continuation when silent. Linked uncertainty protocol requires stops for security, irreversible/external effects and expensive reversal [U12, U17]. | Preserve these useful upstream qualifications, plus every Relay protected/material-change stop. Neither a later override nor the narrower linked stop list removes the main boot conflict. |
| Two applicable accepted normative sources conflict, or Decision normalization disagrees with Request | Resolve explicit amendments/trust first. Invalid normalization/ambiguous ancestry fails admission; a remaining substantive conflict needs canonical reconciliation, not newest-text precedence. | Fixed hierarchy cannot resolve equal-layer Spec conflicts; linked failure-modes explicitly requires human reconciliation and correction of repeated clauses [U18]. | Compatible principle if ruling is formally admitted/normalized. A casual human ruling cannot execute on its own. Do not invent a worker-owned precedence rule. |

The actual upstream instruction sets need separate assessment. Main conflict
boot states the fixed hierarchy, disputed-Spec implementation and continuation
on silence without an inline Relay scope/uncertainty condition [U12, lines
12–40]. Its linked full protocol treats contrary human instruction as a pending
Spec change [U15, lines 49–91]; linked uncertainty and failure-mode documents
add important stops and equal-authority reconciliation [U17, lines 115–137;
U18, lines 113–149]. Thus it is inaccurate both to claim upstream has no
uncertainty handling and to claim formal Spec terminology makes all visible
instructions unconditionally safe.

Sync's main boot treats a direct code edit or imperative chat as evidence that
Spec is stale, then requires an exactly-once final-session proposal, no apply
before approval, and a prescribed commit [U16, lines 14–35]. Its full protocol
excludes temporary, mechanical and missing-section cases, while preserving the
explicit apply/approval requirement [U11, lines 50–69, 121–136]; its review
workflow adds a distinct stopping point [U19, lines 86–102]. A formal Spec
mapping can preserve authorized intent, but cannot silently remove these costs.

The `20a`/`35a` conditional WAL fragments identify WAL state when WAL is
installed. They do **not** guard the main Sync or conflict instructions [U20].
No instruction compliance, real model safety or statistically better outcome
has been demonstrated by this interpretation.

## Controlled observations and limits

The opt-in [probe](../scripts/research/vibevm-methodology/probe.py) runs the
hash-pinned binary on temporary projects, with isolated home/config/cache
paths, an environment limited to PATH/locale plus those fixture paths, and
`--offline` on every project command. It does not download dependencies,
install packages into Relay, alter active files or call a model. Check calls
preserved the fixture's regular-file bytes, modes and mtimes. All fixture
projects are removed. Reproduce after obtaining the pinned binary separately:

```sh
python3 scripts/research/vibevm-methodology/probe.py --vibe /absolute/disposable/path/vibe
python3 scripts/qualify-vibevm-routing.py --vibe /absolute/disposable/path/vibe
pwsh -NoProfile -NonInteractive -File .codex/hooks/test-long-session-checkpoint.ps1
```

| Observation | Actual result | Interpretation and limit |
| --- | --- | --- |
| Stock project, no WAL/packages | Init created no WAL or `vibedeps`; check exit 0, no findings. | Seed startup prose is not an enforced creation prerequisite. |
| Fresh mtime, date from 2000, foreign repository/superseded state, unverified PASS claim | Check exit 0, no findings. | The tool does not establish state provenance or truth. No agent was asked to consume it. |
| WAL mtime 24h30m old | Check exit 0, no findings. | Confirms the whole-hour threshold difference from the prose rule. |
| WAL mtime 25h01m old | One freshness warning, exit 0. | A warning mechanism, not a destructive-operation gate. |
| WAL mtime one hour in the future | One information finding, exit 0. | Clock skew is surfaced, not treated as validated freshness. |
| Four missing canonical headings | Four well-formedness warnings, exit 0. | Structural detection without mandatory repair or truth validation. |
| Both WAL serializations | One error, exit 1. | Rejects the pair before parsing it; this case does not qualify XML content parsing. |
| Two readers followed by full-file replacements A then B | A's frontier disappeared; resulting WAL passed check. | Controlled Python interleaving illustrates a singleton failure mode. It is not an observed VibeVM writer race or concurrency benchmark. |
| Undated disagreement marker versus old dated marker | Undated: zero findings. Dated `2000-01-01`: one aging warning, exit 0. | Marker presence alone does not establish follow-up enforcement. |
| Existing routing probe | PASS, 16 offline commands, stock boot sources 1,813 bytes; bounded replacements preserved. | Reproduces file routing/ownership, not task understanding or precedence obedience. |
| Existing Relay checkpoint suite | PASS on Linux x86_64, PowerShell 7.6.5: session isolation, atomic validation, corruption handling and bounded recovery. | Deterministic helper tests; no native Codex lifecycle or cross-session transfer proof. |
| Step 1 Relay authority tests within complete Node suite | 623 tests passed with an isolated synthetic consumer config on Node 24.19.0. | Historical native binding/supersession/evidence rejection evidence. Step 2 separately reran the complete suite on Node 22.20.0 below. Neither is a comparative model trial. |

The existing authority tests include edited selected evidence rejection,
supersession forks, untrusted copied authority and approval of blocked/stale
results [R1]. These are actual bounded tests of Relay invariants. The scenario
examples that follow are reasoned applications of those results and inspected
contracts, rather than eight recorded Codex sessions.

No token, latency, interruption-frequency, human-time or success-rate benchmark
was conducted. Actual parent/helper model and reasoning-effort telemetry:
**UNAVAILABLE**. Step 1 requested `gpt-6.1-sol`/xhigh. This remediation preserves
the explicitly admitted parent `gpt-6.1-sol`/**ultra**, Subagents On. Three
research helpers were requested at `gpt-6.1-sol` (two xhigh, one high), owning
formal-Spec analysis, isolated tool qualification and source interpretation.
Their work is research assistance, not independent governance acceptance. Real Codex adherence,
crash/compaction behavior and statistical comparative performance:
**UNVERIFIED**. No experimental provider/client/model runs were launched.

The pinned optional WAL status skill still instructs reading `spec/WAL.md`,
whereas its XML boot flow names `vibevm/vibespecs/WAL.xml` [U7, U10]. This is a
source path discrepancy relevant to package adoption. The new isolated probe
materializes this skill unchanged, but neither invokes it nor tests a model
following its path; its operational impact remains unqualified.
Likewise redbook/member WAL and wal-specspaces were inspected as distinct
optional conventions, not installed or concurrency-qualified [U13].

## Exact upstream dependencies versus a compatible policy subset

At VibeVM 1.0.7 `b6659978453f50e6d1d4d99626d70b980a2c5847`, a thin package adapter
cannot retain the unmodified `org.vibevm.world/wal`, `sync-from-code` and
`conflict-protocol` 1.0.0 dependencies while using the ordinary manifest/link
controls to remove individual conflicting rules from their main boot documents. The
package metadata supports selecting packages, linking whole boot contributions, and
author-controlled conditional fragments. It does not provide a consumer-side
sentence/fact exclusion selector or `link = "none"`. This is a bounded source
conclusion about the inspected release and interfaces, not proof that a custom
compiler extension could never implement filtering [D1–D5].

All three exact manifests declare `format = "normal"`, one unconditional main boot
source, and no `[features]` or `[requires]` entries. WAL additionally declares the
`wal-status` skill. Sync and Conflict each declare one separate fragment guarded by
`installed:org.vibevm.world/wal` [D6]. Consequently, the three packages do not
themselves hard-pull one another. Installing only Sync and/or Conflict avoids WAL's
main boot and, when WAL is absent from the complete resolution, their WAL fragments.
It does **not** remove Sync's explicit-apply/commit ritual or Conflict's
hierarchy/implement-anyway rule, which are part of their unconditional main sources
[D7–D9].

| Mechanism in the pinned release | What it controls | Limit for an adapter |
| --- | --- | --- |
| Exact dependency selection (`=1.0.0`, qualified identity, verified source/lock) | Which package versions enter the resolved graph | Selects whole packages; a version string alone does not establish immutable upstream file bytes. Keep source revision and content provenance with the trial. |
| `link = "static"` | Compiles the package boot contribution into the generated priority lane | Includes the declared main contribution; does not delete selected facts. These leaf packages have no `#use`/`#source` directives that expose an existing policy substitution seam. |
| `link = "dynamic"` (also the default) | Leaves a concrete boot path in INDEX | The generated redirect and INDEX instruct the agent to read every listed entry at boot. Dynamic is not a no-load/reference-only control [D3]. |
| `static-transitive` | Forces the target and its complete dependency closure into static loading | Broadens imported policy; a root static-transitive edge can force transitive entries static despite an adapter's ordinary dynamic hints [D4]. |
| `static-hard` | Keeps a static contribution local instead of soft-hoisting | Changes placement/deduplication, not policy text [D1]. |
| `link = "none"` | No such enum variant | Cannot be used to keep installed upstream packages solely as non-boot reference dependencies [D1]. |
| Features / no-default-features | Author-defined feature, optional-dependency and subskill activation | These three versions declare no features. The feature vocabulary contains no boot fact/sentence selector; disabling defaults does not remove unconditional main snippets [D5–D6]. |
| Main/fragment `when` | Package author selects `os:*` or `installed:*` conditions on a whole source file | These versions do not condition their main sources. An adapter cannot add a gate to an unmodified dependency's source using the consumer dependency entry [D2]. |
| `user-override` / later authored prose | Orders an additional policy contribution | Leaves the original conflicting rules and their full-document pointers reachable. It is semantic supersession by prose, not structural removal or evidence that a model obeys the chosen interpretation [D1, D7–D9]. |
| `[[override]]` source replacement | Redirects resolution to another package source/ref | A patched source is a fork/substitution even if it repeats version 1.0.0; it is not the exact unchanged upstream dependency [D10]. |
| Visibility `[override]`, `access`, `friend`, deep `exclude` | Package/edge visibility and resolution | Coordinate/edge controls, not paragraph selectors. Fresh resolution can prune a whole package; an existing lock behaved differently in the probe below. Boot generation has no paragraph-filter step for retained packages [D2, D4, D11]. |
| Normal-package `#use` / `#source` composition | Selects addressed sections in a document's own compile closure; source merges can override contract facts | Does not remove a dependency's separate main boot entry. The inspected three packages do not declare source overlays. An adapter's selective import would coexist with those entries unless an additional, separately qualified filtering/substitution mechanism were built [D4, D12]. |

### Measured disposable dependency composition

The opt-in [dependency probe](../scripts/research/vibevm-methodology/dependency_probe.py)
extracts only the three exact leaf package trees from the hash-verified upstream
archive. It constructs one visibly synthetic adapter and a local `file://`
registry inside a temporary directory. Package manifests have no dependencies,
features or executable lifecycle contributions; the adapter has three exact
requirements, empty author-defined feature lists and one short overlay. The
environment inherits no ambient credentials/configuration, PATH contains no
executables, every project invocation uses `--offline`, and no lifecycle or
inference command is invoked. The upstream source package bytes remain unchanged.
Everything is removed when the probe exits; nothing is installed in Relay.

Reproduce with separately obtained, hash-matching inputs:

```sh
python3 scripts/research/vibevm-methodology/dependency_probe.py \
  --vibe /absolute/disposable/path/vibe \
  --source-archive /absolute/disposable/path/vibevm-source.tar.gz
```

**Observed: PASS, 35 offline CLI commands, 24 captured states, two expected
schema rejections.** JSON preserves command argv, exit/stdout/stderr, full parsed
lock, source-file hashes, manifests, INDEX, separate priority STATIC lane,
ordered effective boot bodies, skills/full protocol bytes and deduplicated
UTF-8 content blobs. It does not simulate an agent reading those instructions.
The initial user-owned stock core/user seeds are also captured and remain
present in these fixtures. Package-specific XML markers establish attribution;
omitting WAL's package does not remove the stock seed's own WAL sentences.
The accepted bounded routing probe separately qualifies authored seed replacement.

| Configuration/lifecycle | Observed closure and client-visible instructions | Limit/consequence |
| --- | --- | --- |
| Independent direct WAL, Sync or conflict install | One corresponding 1.0.0 lock row each. Respective unconditional main snippet delivered via INDEX; no hard cross-package dependencies. | Whole independent packages are selectable; rules within their main snippets are not. |
| Sync + conflict without WAL | Two rows; neither conditional WAL fragment in INDEX. Both main conflict/approval rules remain. | No WAL fragment is not package-wide WAL-free semantics; linked documents still matter. |
| Add WAL, update exact composition, plain/forced reinstall | Three exact rows; both WAL bindings and all main rules remain visible. | Installed condition follows actual graph. Update tested a registry offering only the pinned version, not future fixes. |
| Uninstall WAL, plain/forced reinstall, then re-add | Removing the row removes both bindings; re-add restores them. Main Sync/conflict rules persist throughout. | Genuine conditional-file composition, not within-snippet filtering. No WAL/CONTINUE project state created or removed. |
| Thin adapter with `static-transitive` root, dynamic leaf edges | Four rows including adapter; compiled STATIC priority lane contains all upstream main rules, both bindings and overlay. INDEX also routes authored seeds. | Compiler executes no prose semantics. Adapter overlay coexists with original obligations. |
| Change adapter edge to `dynamic` | Four rows; dependency boot paths remain readable through INDEX, with all main rules and both bindings. | Dynamic delays no instructed read: redirect says to read priority and every entry. It is not policy exclusion. |
| Warm `--no-default-features`, `--all-features`; fresh `--no-default-features` | Warm lock retains adapter defaults; fresh no-default lock omits active feature metadata. In every case all unconditional upstream dependencies/boot rules survive. | Tests distinguish sticky metadata from real default disabling. These packages have no feature controlling policy facts. |
| Fragment-shaped `exclude = ["org.vibevm.world/wal#HONOUR-EVERY-CONSTRAINT-VERBATIM"]` | WAL and its verbatim-constraint marker, plus both bindings, remain in the warm adapter world. | Identity-shaped text is not a sentence selector. Source schema/compiler establishes the broader absence of such a selector. |
| Whole WAL exclude on an already installed adapter, then ordinary install, forced reinstall and `update --all` | Existing WAL lock row and both bindings survive all three operations. | An edited manifest is insufficient proof of effective absence. Cause beyond lock/resolution-path evidence is unqualified; no upstream repair is attempted. |
| Same whole-package exclusion in a fresh project, or after uninstall/re-add of adapter closure | Only adapter + Sync + conflict lock; WAL and both bindings absent. Overlay plus conflicting Sync/conflict main rules remain. | Package-level pruning is viable on fresh resolution, with a warm-lock lifecycle caveat. It still cannot retain WAL as a dependency while removing its individual obligations. |
| Proposed `rules = ["safe-only"]` dependency field; `link = "none"` | Both exit 1 with `RequiresPackageEntryWire` schema parse errors. | Generic diagnostics alone do not prove every imaginable selector impossible; inspected strict schema/link enum and full composition support this bounded negative conclusion. |

Stable observed package content hashes in the tool's lock are WAL
`58eccc204df7e63e78e8d15f9416b6fd528e786b74d9e0e5e2fcb859716ea0d0`, Sync
`c068ab0517275cc6c7d11ce0e77e20c8dc9f038c6e6e4ae0832902b063ce0fc5`, and conflict
`669fb4a23f0a822cff870f18e5e8f330f82e3c6315515b47c4a691700c7c21e3`.
Their dynamic main boot SHA-256 values are respectively
`c2507573c8122a8a2f5c09996f1efbe914f5c18be492f605e74cfa550395cc94`,
`39f99e5a30b6a5c8cc8bfda48404dd7411f6047cf272d4e41fc7577c5fb16285`, and
`c72fc8e006bc80b2284512a0925a0db7f954d172b4e8bea966ca2759449a9d82`.
Archive/binary pins bind origin; lock/generated-file hashes and full snapshots
bind the observations. Temporary registry URLs and generated timestamps are
run-local and are not expected to reproduce byte-for-byte. The script and this
report are the source-controlled evidence; raw JSON is reproducible temporary
output, not a new authority ledger or required artifact.

Only dynamic/static-transitive composition, the stated feature/exclude controls,
and selected install/update/uninstall/plain/forced-reinstall operations were
tool-tested. Ordinary static, static-hard, source overrides, friend/access
schemes and normal-document source merges are source-inspected alternatives,
not experimentally demonstrated adapters. A custom transform/fork and new
upstream content units are unbuilt proposals. Source/tool results do not qualify
Codex compliance, owner interruption rates, statistical benefit, registry
publication or production package activation.

### Conditional WAL does not mean package-wide decoupling

`installed_identities` is derived from the **whole unified resolution**, using
`(group, name)` identities; it is not a test for a WAL file, a direct requirement, a
particular WAL version, or whether WAL's boot was read. `active_snippet` resolves
main and fragments independently. An installed WAL introduced transitively or
elsewhere in that unified workspace resolution activates both Sync's
`20a-wal-binding.xml` and Conflict's `35a-wal-binding.xml` during generation. A
false predicate physically omits that fragment; a true one becomes unconditional. OS
conditions instead remain read-time INDEX conditions [D2, D4]. An
install/update/uninstall/reinstall must therefore be evaluated against the complete
resulting resolution, not just the adapter's manifest.

There is a narrower but important remaining coupling. The main snippets'
conditional-fragment repair does not rewrite every flow document in the package.
Sync's full `SYNC-PROTOCOL.xml` still describes `head → WAL → spec → code` (lines
12–14), requires recording skipped temporary work in WAL (53–54), and later
attributes checkpoint updates to the WAL flow (145–147). `when-to-apply.xml`
requires the WAL entry for temporary changes (41–46), while `review-workflow.xml`
records rejected work lessons in WAL (111–114). Conflict's full protocol still
displays the WAL ladder (43), treats human instructions as unwritten spec changes
(51), defines code wrong until a human rules otherwise (55), and repeats
implement-first/report-later (98–111). Its recovery document adds a human-only
stale-state reconstruction ritual (95–111) [D13–D15]. Thus an experiment may
truthfully establish **WAL fragment absent from generated boot**; it cannot infer
**the entire retained package is WAL-free or Relay-compatible**. The main boot
sources explicitly point to these full protocols and sibling documents [D8–D9].

WAL's own full surface likewise exceeds a concise checkpoint idea. Its main boot
calls for first-read, freshness confirmation, mandatory rewrites and an
unconditional resume/report/wait boundary. The full flow repeats those duties,
describes literal unattended WAL execution, separate checkpoint commits, a morning
human ritual and a weekly full-spec reread. Its shipped skill still reads
`spec/WAL.md`, while the boot/protocol use `vibevm/vibespecs/WAL.xml` [D7, D16–D18].
WAL does acknowledge multi-developer many/no-WAL schemes by not installing or
superseding the flow (main boot 65–70), and it says install/uninstall never
creates/deletes/overwrites project WAL/CONTINUE state (61–63). Those are valuable
explicit limits, but “superseding” does not add a structural consumer-side
rule-filter interface.

### Smallest maintainable architecture and next decision

The following compatibility/feasibility matrix separates **package granularity**
from **rule granularity**. "Unsafe" means unsuitable as unchanged active Relay
policy under current authority; it is not a claim that merely inspecting the
package executes its instructions or that the package is unsuitable everywhere.

| Consumption architecture | Real upstream version dependency retained? | Select only compatible rules? | Formal-Spec compatibility and feasibility | Maintenance/owner implication |
| --- | --- | --- | --- | --- |
| Direct `wal@1.0.0` | Yes, exact leaf package with no hard dependency on Sync/conflict | No consumer selector within its main boot/full protocols | Unsafe unchanged: mandatory first read/rewrite, stale-confirmation and resume/wait costs, separate state and skill-path discrepancy remain | Installing it is methodology adoption, requiring separately admitted state ownership/concurrency/recovery decisions. |
| Direct `sync-from-code@1.0.0` without WAL | Yes; no hard WAL dependency | No; absent WAL fragment does not remove main approval/commit rules or all linked WAL references | Useful code-first reconciliation, but unsafe unchanged as routine same-Task doc policy | New compatible publisher version or owner approval of extra interruptions/commit ritual; no retrospective authority creation. |
| Direct `conflict-protocol@1.0.0` without WAL | Yes; no hard WAL dependency | No; hierarchy/implement-anyway remain in main boot | Principle-level formal Spec is conditionally useful; complete current instruction set is unsafe as an unconditional Relay rule | Owner must retain protected stops; new compatible publisher version must qualify boot and linked uncertainty/recovery documents together. |
| Thin adapter requiring the three unchanged packages, plus Relay mapping/overlay | Yes, real transitive closure | No demonstrated structural removal; feature/link/visibility controls cannot select those facts | Technically composable, semantically conflicting. Calling it a safe dependency-backed hybrid is unsupported | Small manifest is maintainable but leaves contradictions; do not transfer interpretation burden to each agent/session. |
| Relay adapter with immutable upstream references outside active dependency graph | References, **not executing package dependencies** | Adapter authors only bounded Relay instructions, with source attribution | Viable minimal present recommendation for a separately admitted trial; preserves current formal Spec and gates | Small mapping, no copied upstream tree; consciously review reference pin updates. It does not satisfy a requirement for unchanged executing upstream dependencies. |
| Copy/fork selected policy, or source override to patched package | A fork can be versioned; neither is the unchanged upstream dependency | Yes by editing owned source, with attribution/license/provenance | Potentially compatible if all reachable text preserves admission/stops/docs; not qualified or activated here | Divergent maintenance and upstream-fix reconciliation belong to the fork owner. Fallback only if reference reuse is insufficient and publisher cooperation unavailable. |
| New upstream boot-free reusable units or supported author-controlled selectable rules, with thin Relay adapter | Could retain real upstream versioned dependencies | Possible only after publisher/tool implements and qualifies the seam | Preferred future dependency architecture; **not available as demonstrated in these exact versions** | Requires new exact versions and complete lifecycle/text re-review, then a separate owner Decision/Request for adoption. |

The viable choice **today** is a Relay-owned, policy-compatible adapter whose
instructions point to the existing trusted charter/Request, affected component
contracts and selected evidence. Keep these exact upstream packages as read-only,
revision-pinned research/reference inputs **outside the active VibeVM dependency
graph**; do not list them as executable `[requires.packages]` merely to make the
dependency relationship look real. The adapter can link immutable upstream rationale
and name the useful concepts without copying upstream package trees or claiming to
execute their full protocols. This is reference reuse and an honest narrow Relay
adaptation; it is not activation of a compatible subset of those three exact package
dependencies. An offline research fixture may install them solely to inspect
generated bytes, provided no agent consumes its policy and no lifecycle hook is
executed; that fixture is separate from consumer activation.

If the requirement is **real executing package dependencies with a structurally
compatible subset**, the pinned versions fail that requirement through these
standard interfaces. The least complex maintainable next architecture is
upstream-authored reuse seams: separate reusable rationale/protocol content from
policy boot packages; ship boot-free or explicitly selectable policy units; let a
small Relay adapter depend on the exact compatible units and own only the mapping to
Relay authority/evidence. That needs new package versions (and, if a consumer
boot-disable/selection syntax is chosen, a tool version implementing and qualifying
it). A new feature name alone is insufficient unless the tool and package actually
use it to control the unwanted boot text. Every reachable full protocol, sibling and
skill must share the same compatible semantics. Conditional WAL bindings remain
useful, but they only solve co-installation coupling.

A patched fork/source override or custom compiler transform is an alternative
engineering project with continuing content and upgrade ownership. It must be
identified as that, rather than an unchanged 1.0.0 dependency. A custom filter would
need exact source/content matching, fail-closed handling of changed rules, complete
boot/full-document reachability qualification and lifecycle proofs; it is more
machinery than the proposed reference adapter and is not demonstrated here. Merely
importing selected facts into an adapter while original dependency boot remains
listed, appending “Relay wins,” changing generated STATIC/INDEX by hand, or changing
`dynamic` to mean “do not read” cannot support the desired structural-absence claim.

Upgrade handling follows the chosen architecture. Immutable reference-only pins
preserve the reviewed meaning until deliberately updated; assess the new full
referenced surfaces when changing them. For a real package trial, review the tool,
manifests, complete resolved/transitive graph, both boot lanes and every reachable
protocol/skill after install, update, uninstall and both reinstall modes. The source
says update re-resolves/re-materialises and regenerates boot; uninstall preserves
still-required packages and regenerates from the remaining world; plain reinstall
regenerates from materialised slots without changing locked versions; forced
reinstall re-fetches/re-materialises locked content and regenerates [D19].
Hand-edited generated artifacts therefore cannot be the durable adaptation seam.
Source inspection here did not run lifecycle operations or models and supplies no
acceptance or model-compliance verdict.

## Representative scenarios and alternatives

**A** is the stock seeded WAL/spec-first discipline, with optional package
extensions identified explicitly rather than silently credited to stock.
**B** is accepted Relay at the admitted base. **C** is a proposed targeted hybrid:
retain B's authority, gates, targeted loading and review; improve existing
selected handoff evidence with a concise diagnostic frontier when useful; use
addressable rationale and a value/reason/revisit explanation for substantive
code/spec reconciliation. C adds no mandatory WAL, second file, new ledger,
blanket test requirement or default resume pause. It is an authoring proposal,
not activated policy, and its additional continuity benefit depends on capture
and selection actually happening.

### Scenario reasoning

1. **Interrupted implementation, another session/machine resumes.** A patch is
   committed, but the author had ruled out two parser hypotheses and was about
   to inspect a third. A repository checkpoint, and especially the optional
   package's CONTINUE, can preserve that orientation independently of the
   session. B reconstructs authority and committed work precisely; its foreign
   session cannot recover the private frontier through the helper. C preserves
   only the discriminating observation and ruled-out hypotheses in existing
   selected evidence. All three lose unwritten reasoning after an abrupt crash.
   Source design favors A for simple cold orientation; C may avoid duplicating
   reconstructible state. No measured recovery-time winner exists.

2. **Concurrent Tasks/PRs and a shared change across repositories.** One Task
   fixes parsing, another changes deployment docs, while a producer changes a
   shared contract. A singleton current-phase/next-action file can mix the
   Tasks or lose a stale writer's update; branch separation contains writes but
   creates divergent snapshots to reconcile on merge. The optional package
   acknowledges this and permits many/no WALs. wal-specspaces partitions
   registered subprojects, which is not automatically Task/PR isolation.
   B binds each Request/Outcome to repository/Task/head and protects publication,
   but has no cross-repo coordinated acceptance transaction. C adds pinned
   contract references and compatibility evidence within each admitted Task.
   None gains authority to mutate the producer or another consumer. A shared
   specification can reduce duplicated rationale without solving rollout.

3. **Stale or wrong WAL.** A recently copied checkpoint claims another branch's
   tests passed; alternatively a correct idle project's file is 48 hours old.
   The CLI misses the wrong-state case and warns on the old file; age alone
   cannot distinguish them. The optional flow's human/Git revalidation can
   catch them if followed, at an interruption cost. B validates current
   Request/evidence identities and rechecks mutable facts; it can still receive
   a false but correctly attributed claim. C keeps notes non-authoritative and
   labels observations versus hypotheses. Freshness helps triage but must not
   replace semantic provenance. No observed agent obeyed or resisted the note.

4. **Code-first fix with stale specification.** The admitted repair changes a
   synthetic parser to preserve whitespace; old prose says trim. A's seed
   recognizes the need for a proposal, and the optional Sync-from-Code protocol
   protects intent from a later mistaken rollback. B must update the affected
   documentation in the same Task; if the behavior delta is already authorized,
   another explicit-apply pause is unnecessary. C states the new behavior, why
   the old prose failed, and when to reconsider it in that same diff. If the
   code change was never authorized, all safe alternatives first resolve that
   decision; updating the spec to match code is not retroactive authorization.

5. **Accepted specification conflicts with tests.** The scoped contract says
   an empty input returns an empty result; a baseline test expects an error.
   A's ordering gives a clear oracle if acceptance is genuine. B can also fix
   that test within scope, but needs evidence that the contract is current and
   the test obsolete. C adds a small input/expected-behavior/contract/evidence
   explanation to the existing PR. If the test protects an omitted security
   invariant, none may simply delete it to get green. Compare starting and
   candidate states and mark whether the test defect is baseline or introduced.
   No semantic model trial or artificial failing product test was created here.

6. **Real ambiguity or unauthorized operator-contract change.** A specification
   calls for a new mandatory owner approval before every doc edit, while the
   current Request permits routine synchronized maintenance. Stock implement-
   then-report risks imposing the unapproved cost. B stops the material delta
   and asks for canonical owner disposition while preserving useful in-scope
   work. C can draft precise alternatives and their effects but keeps that stop.
   This necessary interruption protects correctness of authorization. An
   optional package's own stop-on-constraint and human-approval prose is useful,
   but does not identify Relay's trusted Request or override its protected gate.

7. **Fresh Task without historical state.** A small new report starts with a
   clear Request and no prior frontier. Stock init supplies policy but no WAL;
   the CLI accepts this. Following stock WAL startup literally needs a missing-
   state disposition, and adopting the optional flow adds recurring rewrites.
   B starts with the charter/Request and exact facts, then loads only necessary
   detail. C has nothing extra to capture yet. A becomes more attractive if the
   project actually lacks any other durable intent record; that is not this
   Task's starting condition. Neither B nor C should preload history to fill
   an empty checkpoint slot.

8. **Blocked/failed outcome, independent review and resumption.** A candidate
   is saved but a required check cannot run, or the reviewer finds a baseline
   defect newly exposed by validation. A's phase/known-issues/next-action and
   optional cold handoff make the state readable, but a marker or PASS sentence
   does not supply Relay's exact-head acceptance boundary. B preserves useful
   commits, publishes through Writer, records warnings/limitations and gives
   the independent reviewer provenance and applicable scope. Blocked results
   cannot become approval [R1]. C improves the finding/Outcome with the next
   safe discriminating observation and why a prior correction missed the
   invariant. An unchanged rerun adds evidence only when conditions changed;
   none of the alternatives justifies blind retry, a new Step or Issue closure.

### Qualitative score matrix

These are **reasoned ordinal judgments, not measurements or probability
estimates**. L/M/H mean low/moderate/high relative burden or capability for the
specific examples above; they are not global product grades. U means evidence
insufficient. Risk columns concern the stated failure paths, not general
correctness rates. No aggregate total is calculated because the owner must
choose the weights. A's stronger cold-resume ratings assume its optional flow,
as stated in scenario 1; the bare seed supplies less detail. C is untrialled.

| Scenario | Option | Traceability/correctness risk ↓ | Stale-state failure risk ↓ | Continuity ↑ | Review/recovery clarity ↑ | Operator interruptions ↓ | Maintenance/docs overhead ↓ | Complexity ↓ | Cross-repo scalability ↑ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1: cold handoff | A | M | M | H | M | M | M | M | M |
| 1: cold handoff | B | L | L | M | H | L | L | M | M |
| 1: cold handoff | C | L | L | H | H | L | M | M | M |
| 2: concurrency/shared contract | A central | H | H | M | M | M | H | M | L |
| 2: concurrency/shared contract | B | L | L | M | H | M | M | M | M |
| 2: concurrency/shared contract | C | L | L | M | H | M | M | M | M |
| 3: wrong/old state | A | M | H | M | M | H | M | M | M |
| 3: wrong/old state | B | L | L | M | H | L | L | M | M |
| 3: wrong/old state | C | L | L | M | H | L | M | M | M |
| 4: code-first fix | A + Sync flow | M | M | H | H | H | H | M | M |
| 4: code-first fix | B | L | M | M | H | L | M | M | M |
| 4: code-first fix | C | L | L | H | H | L | M | M | M |
| 5: spec/test conflict | A | M | M | M | M | L | M | L | M |
| 5: spec/test conflict | B | L | M | M | H | M | M | M | M |
| 5: spec/test conflict | C | L | M | H | H | M | M | M | M |
| 6: unauthorized change | A seed | H | M | M | L | L initially | H rework | L | L |
| 6: unauthorized change | B | L | L | M | H | H necessary | M | M | M |
| 6: unauthorized change | C | L | L | M | H | H necessary | M | M | M |
| 7: fresh Task | A | M | U absent | L | M | M | M | L | M |
| 7: fresh Task | B | L | L | H authority | H | L | L | M | M |
| 7: fresh Task | C | L | L | H authority | H | L | L | M | M |
| 8: blocked/review | A | M | M | H state | M | M | M | M | M |
| 8: blocked/review | B | L | L | H authority | H | M | M | M | M |
| 8: blocked/review | C | L | L | H authority/frontier | H | M | M | M | M |

B's low authority risk is conditional on its trusted boundary functioning and
people recording truthful evidence; the schema cannot validate semantic intent.
Its moderate complexity reflects typed publication, selected references and
exact-head review, real costs that A's simpler prose lacks. C's favorable
continuity/staleness cells are hypotheses about consistently applying the
authoring pattern, not a claim of measured improvement. Their advantage
disappears if nobody captures/selects the frontier or the added prose becomes
stale. Alternative multi-WAL upstream schemes could improve scenario 2 at a
partitioning/synchronization cost; their performance remains undetermined.

## Mechanism recommendations and owner choices

“Adopt” below means a useful practice to retain or endorse through normal
authorized work, not an instruction activating policy from this report.
“Adapt” preserves the idea but changes its authority/state placement. “Reject”
is scoped to the stated universal behavior in Relay. “Undetermined” identifies
the missing proof instead of choosing a rhetorical winner.

| Mechanism | Recommendation | Benefit, conflict and exact owner disposition needed |
| --- | --- | --- |
| Relevant specifications before changing behavior | **Adopt existing overlap** | Retain JIT affected-contract reads. No new mandatory taxonomy, full-spec preload or separate decision needed for existing behavior. |
| Durable addressable rationale, separated from ephemeral frontier/history | **Adapt** | Use existing component anchors and exact revisions. Promote accepted reusable semantics through authorized same-Task edits. A compulsory `spec://` migration needs a separate decision on format/tooling and proof that links survive maintenance. |
| Small current-state handoff with constraints, reasons and one next observation | **Adapt** | Place only useful irreconstructible frontier in existing Outcome/finding/selected evidence; keep next action subordinate to Request. Conditional use fits existing evidence surfaces. Owner must decide separately before making capture mandatory for every session or changing publication cadence. |
| Shared central WAL rewritten every session | **Undetermined; no adoption yet** | Could simplify single-person cold handoff, but duplicates Task/Git evidence and risks singleton contention. Owner must choose use cases, state owner, partitioning, bounds, stale handling and synchronization responsibilities before a trial or mandate. |
| WAL freshness check | **Adapt concept; reject as sufficient proof** | Revalidate claim provenance and mutable authority/Git facts, not age alone. A new always-on checker, human pause or hard age block is cost-bearing and needs a canonical owner decision plus false-positive/wrong-state trials. |
| CONTINUE and explicit cold-resume ritual | **Adapt orientation; defer second store** | Empirical revalidation and non-authoritative next action are valuable. Mandatory second file, separate checkpoint commit and unconditional resume-and-wait add actions: owner must authorize those exact costs and their interaction with already admitted work. |
| Compaction/session recovery | **Adopt existing overlap; broader transfer undetermined** | Keep optional session isolation and nonblocking missing notes. Cross-session transfer could help, but needs explicit identity/access/consumption choices. Neither source prose nor helper tests qualify native model lifecycle behavior. |
| Human > Spec > Tests > Code as executable authority | **Adapt intent heuristic; reject literal override** | Preserve authorized intent over accidental artifacts. Replacing trusted Request admission with chat/spec precedence requires an explicit governance migration, trusted-source/currentness design and negative authorization proofs; this Task authorizes none. |
| Implement disputed specification, report afterward | **Reject unconditional rule; adapt narrow case** | Continue a clear safe authorized choice despite personal design preference, with disagreement recorded in existing review context. Ambiguity or protected/material delta keeps the stop. Any broader continuation permission needs owner-defined admissible disputes and proof it cannot cross protected gates. |
| REVIEW markers | **Adapt as optional navigation** | A dated local marker can link a durable finding; never substitute for native review or leave the finding only in code. New mandatory markers/aging gates need owner authority. Pinned undated-example gap must be resolved in any proposed upstream package trial. |
| Sync-from-Code value/reason/revisit explanation | **Adapt** | Improve authorized same-Task doc reconciliation; classify experiments and unknown intent. A universal separate proposal/explicit-apply pause or mandated `docs(spec)` commit changes workflow and needs an owner decision. Material unauthorized behavior still requires Decision/Request first. |
| Tests/code as regenerable artifacts | **Adapt narrowly; reject evidence loss** | Contracts guide implementation, while baseline tests/diffs preserve empirical edge cases and provenance. Blanket regeneration/discarding or broader mandatory testing needs specific scope and an owner decision. |
| Redbook, conflict, Sync and wal-specspaces packages as a bundle | **Undetermined; do not install** | Separate useful concepts from package coupling and path inconsistencies. Any package trial needs exact pins, isolated source-only qualification, scope/activation ownership and separately authorized adoption. No benefit of one concept justifies importing the entire preset. |

A separate WAL is warranted only if a concrete continuity need cannot be met
cheaply by current Request/Outcome/Git plus a selected frontier, and the shared
store's net benefit survives concurrency, stale-state and maintenance trials.
This study establishes that such a need can exist, not that it warrants another
mandatory store. Accepting occasional frontier recapture is also a valid owner
choice; so is a small opt-in cold-handoff aid for unusually long investigations.

## Minimal integrated workflow and next proof

The proposed hybrid sketch, within existing authority, is:

1. Resolve the charter/current complete Request and exact checkout facts. Load
   selected evidence and the affected contract when needed; boot routing only
   points to these sources.
2. State the concrete intended behavior and its authority. Treat tests/code as
   evidence; diagnose conflicting or stale oracles against the starting state.
3. Make the clear authorized correction. For substantive doc reconciliation,
   explain behavior, reason and a useful revisit condition in the existing
   contract/PR. Preserve real ambiguity and material-change stops.
4. When a frontier would otherwise be lost, capture the established facts,
   eliminated hypotheses, unresolved invariant and next safe observation in
   the existing appropriate evidence surface. Select it for a later Request
   when useful; it never launches work or broadens scope.
5. Commit useful work, run applicable checks and hand results/warnings to Writer
   for the normal exact-head Outcome and independent review. On resume,
   revalidate mutable facts; do not replay mutation from a saved note.

For a later, separately admitted proof, begin with a paired synthetic handoff:
same small code/spec/test fixture and same authorized behavior, once with only
reconstructible Git/Request evidence and once adding a selected compact
frontier. Include a fresh session, changed head, wrong-repository note, edited
selected evidence, conflicting test oracle and two concurrent Tasks. First
verify deterministic reachability/isolation and preservation of existing
negative authority tests. If the owner wants real model trials, authorize the
client, calls, data and budget explicitly; record actual runtime profiles,
successful and failed recoveries, avoidable owner interruptions and operator
authoring time. Do not infer statistical superiority from one successful
resume. Predefine which failures would justify no change or a further bounded
trial; do not make experiment metrics into operational acceptance gates.

Only after evidence favors a particular mechanism should an owner Decision
name its exact behavior, scope and costs, be normalized into a complete new
Request, and authorize a minimal implementation with same-Task docs and
independent review. Broader cold transfer, new stores, universal spec-first
approval, package adoption and cross-repo rollout remain separate unresolved
choices. No later Step is allocated by completing this research.

The dependency qualification refines that sketch: **do not implement the hybrid
by requiring unchanged 1.0.0 flow packages and appending a Relay override**.
For a future bounded trial, the minimal present architecture is a small
Relay-owned mapping with immutable upstream rationale references outside its
active package graph. If real upstream dependencies are an owner requirement,
first request publisher-maintained boot-free reusable content units or genuinely
selectable policy units. A thin adapter would depend on their exact versions,
own only formal-Spec/Outcome placement, and retain Relay admission/stops/review.
Validate their reachable full protocols and skills, not just generated boot.
None of those future package versions or adapter installations is produced here.

| Unresolved owner choice | Exact prospective behavior change | Smallest migration/proof path |
| --- | --- | --- |
| Endorse formal Spec vocabulary without activating packages, or require a dependency-backed methodology | Clarifies admitted intent; dependency adoption additionally exposes upstream instructions and future upgrades | Accept/revise this research definition; if dependencies are required, obtain new compatible publisher seams/versions, then a complete separately admitted Request and opt-in negative authority proofs. |
| Reference reuse, publisher-maintained reusable units, or explicit fork | Chooses who owns policy changes and upstream fixes | Prefer references today; new upstream units for real dependencies later. Qualify exact source identity/lock/full effective text at every upgrade. A fork requires explicit divergence/license/update ownership. |
| Keep current doc synchronization or add Sync approval/commit ritual | Additional owner interruption and prescribed commit boundary for already authorized docs | Name triggers/exemptions, demonstrate simplest authorized code-first fix plus unauthorized counterexample, obtain owner Decision/Request before implementation. |
| Keep protected stops or broaden implementation of disputed/underspecified Spec | Changes which uncertainties may continue without owner reconciliation | Preserve current stops by default. Any broader continuation rule needs a bounded class of disputes and proofs of no protected/operator-contract bypass. |
| Optional selected frontier versus shared WAL/CONTINUE | New persistent state owner, session rituals, cold-transfer and concurrency burden | First test one need not met by Task/Outcome/Git/session note. Decide partitioning, provenance, stale behavior and consumption before adopting a store. Accepting no new store remains valid. |

No migration is justified merely by a package being installable. The safest
next outcome may remain **no methodology migration**, including after owner
acceptance of this report. Native route C's conditional feasibility remains
independent of every choice in this table.

## Validation, provenance and warning disposition

Step 2 research ran as an unprivileged Linux x86_64 worker (UID 983) on
October 10, 2026. The freshly fetched source archive and existing disposable
binary matched the accepted hashes above. Both the original WAL probe and new
dependency probe passed; the latter's final local result is 35 commands,
24 observed states and two expected schema rejections. The final script uses
actual Sync do-not-apply/approval-commit markers and the conflict
implement-anyway marker alongside the adapter overlay. No model was asked to
execute any fixture policy. Historical Step 1 routing/checkpoint observations
remain labeled evidence above; this remediation changes neither surface.

The default PATH has Node 18.20.4, no npm or Cargo, and system Python lacks
pytest. Existing disposable tools permitted the required unprivileged checks
without installation: Node 22.20.0/npm, Cargo/rustc 1.90.0,
rustfmt 1.8.0-stable, Python 3.11.2/pytest 9.1.1 and Ansible core 2.16.19.
The full `npm test` command passed **623 tests** with a temporary mode-0600
copy of the existing synthetic consumer fixture. Cargo fmt passed; locked
Cargo tests passed **85 tests** using the existing local dependency cache and
a task-owned temporary target directory. `scripts/qualify.py` reported
**THREE_CONSUMER_PASS** (isolated real handlers, mock GitHub and synthetic
credentials; no live publication). The final complete deployment suite passed
**865 tests and 317 subtests**, with **299 skipped and 19 warnings**. Warnings
were Ansible's Python `crypt` deprecation and Jinja's invalid-escape deprecation;
skipped tests remain unqualified. Whitespace, Python syntax and the staged tracked-file candidate scanner
are also recorded in the terminal handoff.

Initial environmental failures were diagnosed, not hidden or repaired in
product source. The synthetic tracked config is mode 0660 and was rejected by
the unchanged consumer permission check. A private temporary copy solved test
startup without changing repository modes. The first deployment invocation
used the inherited group-writable umask and unsuitable PATH/locale; protected
synthetic paths failed validation and Ansible was initially skipped/unavailable.
A private umask and existing tools corrected path prerequisites; the next run
had 796 passes, 88 failures, 299 skips, with the failing Ansible invocations
reporting non-UTF-8 locale. Setting process-local `LANG`/`LC_ALL=C.UTF-8`
resolved the previously failed set (69 tests and 16 subtests passed); a final
complete suite was run in that qualified environment. These changes affect
only disposable validation processes, not consumer configuration or host setup.

Provenance comparison for these environment findings is the reviewed starting
head `09f87c3ebf8462dd6a09a86ca5abe2b19d796439` against admitted base
`4f0e0e38980854fcb09dc718841ade3102a8108f`: test suites, synthetic fixture,
consumer loader, deployment sources and local-tool prerequisites are unchanged.
The candidate alters only this report and an opt-in research script. The
permission/locale prerequisites and tool gaps are pre-existing environment
conditions, not defects introduced by this remediation. The initial broad
failures are not described as regressions or added to research scope. Upstream
boot/filtering/lock/path limitations likewise pre-exist at the pinned upstream
revision; this CR authorizes analysis, not upstream fixes.

| Warning or limitation | Impact and required disposition |
| --- | --- |
| Initial tool/PATH/config-mode/umask/locale failures | Resolved locally with existing disposable tools and process-only synthetic-fixture settings. No host installation, repository permission repair or production-policy bypass. Final results do not erase the recorded prerequisites. |
| Deployment skips and dependency deprecations | Qualifies only tests actually executed under this ordinary UID. Ansible/Python/Jinja dependency warnings are pre-existing; root-only installed-runtime/containment/sudo/credential proofs remain native exact-head CI responsibilities after Writer publication. |
| Package granularity, warm-lock exclusion/features, retained main/linked rules and WAL skill path mismatch | Material owner/review inputs even though the probe passes. Do not infer effective removal from manifest changes or overlays; new package/adaptation work must test full resulting closure and visible text across fresh and existing states. |
| Version-upgrade/source-override/custom-filter/model gaps | No newer upstream release, executing fork, compiler filter, real Codex compliance, native compaction lifecycle or comparative success-rate trial was qualified. Actual parent/helper runtime model/effort telemetry is UNAVAILABLE. |
| Current primary execution-warning surface unavailable | This worker has no terminal Writer Outcome/complete controller-runtime warning acquisition or authorization to invoke Reviewer/use GitHub credentials. Step 1's partial in-progress annotations are historical evidence, not current warning clearance. Writer/independent review must inspect and disposition supported terminal attempt/Outcome/native annotation/runtime surfaces. No claim of “no execution warnings” is made. |

The local commit preserves task progress for trusted Writer. The worker does not
push, publish an Outcome/PR, invoke Reviewer, merge, close the Issue, activate
packages or allocate another Step. The exact final candidate head and native
check links belong in Writer's English top-level Outcome, with these material
limitations retained for independent review. Deterministic checks and research
helpers do not constitute independent acceptance. The Issue remains keep-open.

## Source references

Upstream references below all use the same accepted immutable commit. Where a
range is mentioned in the report it refers to the raw source at that revision.

- [U1: stock core seed](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-cli/templates/boot-00-core.md), lines 3–39.
- [U2: project init](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-cli/src/commands/init/mod.rs), lines 233–326; [seed helpers](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-cli/src/commands/init/helpers.rs), lines 132–175, 212–237.
- [U3: generated redirect](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-workspace/src/boot_artifacts/redirect.rs), lines 26–70; [boot artifact generation](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-workspace/src/boot_artifacts.rs); [generation transaction](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-workspace/src/boot_artifacts/transaction.rs).
- [U4: WAL resolution/headings](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-check/src/checks/wal_wellformed.rs), lines 12–127.
- [U5: WAL mtime freshness](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-check/src/checks/wal_freshness.rs), lines 24–84.
- [U6: check command and exit semantics](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-cli/src/commands/check.rs), lines 21–61.
- [U7: optional WAL boot flow](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.world/wal/v1.0.0/vibevm/vibespecs/boot/10-flow-wal.xml); [manifest](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.world/wal/v1.0.0/vibe.toml).
- [U8: optional WAL protocol](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.world/wal/v1.0.0/vibevm/vibespecs/flows/wal/WAL-PROTOCOL.xml), particularly lines 12–25, 61–84, 107–145.
- [U9: cold resume](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.world/wal/v1.0.0/vibevm/vibespecs/flows/wal/cold-resume.xml), lines 101–118; [session end](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.world/wal/v1.0.0/vibevm/vibespecs/flows/wal/session-end-hook.xml), lines 93–105.
- [U10: WAL status skill](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.world/wal/v1.0.0/vibevm/vibespecs/skills/wal-status/SKILL.md), lines 13–22.
- [U11: optional Sync-from-Code protocol](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.world/sync-from-code/v1.0.0/vibevm/vibespecs/flows/sync-from-code/SYNC-PROTOCOL.xml).
- [U12: optional conflict protocol](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.world/conflict-protocol/v1.0.0/vibevm/vibespecs/boot/35-flow-conflict-protocol.xml).
- [U13: optional wal-specspaces protocol](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.world/wal-specspaces/v1.0.0/vibevm/vibespecs/flows/wal-specspaces/SPECSPACES-PROTOCOL.xml); [optional redbook member convention](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.world/redbook/v1.0.0/vibevm/vibespecs/boot/03a-member-wal.xml).
- [U14: dated REVIEW aging check](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-check/src/checks/review_aging.rs), lines 34–110.
- [U15: full conflict protocol](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.world/conflict-protocol/v1.0.0/vibevm/vibespecs/flows/conflict-protocol/CONFLICT-PROTOCOL.xml).
- [U16: Sync main boot](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.world/sync-from-code/v1.0.0/vibevm/vibespecs/boot/20-flow-sync-from-code.xml).
- [U17: linked uncertainty protocol](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.world/conflict-protocol/v1.0.0/vibevm/vibespecs/flows/conflict-protocol/uncertainty-protocol.xml).
- [U18: linked conflict failure modes](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.world/conflict-protocol/v1.0.0/vibevm/vibespecs/flows/conflict-protocol/failure-modes.xml).
- [U19: Sync review workflow](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.world/sync-from-code/v1.0.0/vibevm/vibespecs/flows/sync-from-code/review-workflow.xml).
- [U20: conditional Sync WAL binding](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.world/sync-from-code/v1.0.0/vibevm/vibespecs/boot/20a-wal-binding.xml); [conditional conflict WAL binding](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.world/conflict-protocol/v1.0.0/vibevm/vibespecs/boot/35a-wal-binding.xml).
- [R1: Relay authority test evidence at the admitted base](https://github.com/jresearchsoftware/codex-relay/blob/4f0e0e38980854fcb09dc718841ade3102a8108f/contracts/test/github-authority.test.mjs), especially untrusted evidence, supersession, selected context and exact-result/warning acceptance cases.
- [Accepted routing assessment at the admitted base](https://github.com/jresearchsoftware/codex-relay/blob/4f0e0e38980854fcb09dc718841ade3102a8108f/docs/vibevm-routing-assessment.md), plus the [local copy](vibevm-routing-assessment.md).


All D references use the immutable VibeVM source revision `b6659978453f50e6d1d4d99626d70b980a2c5847`. Line ranges refer to that source, not later releases.

- D1: [link modes and boot category](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-core/src/manifest/package.rs), lines 368–454; [boot snippet schema](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-core/src/manifest/package.rs), lines 506–546.
- D2: [strict dependency entry schema](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-core/src/manifest/package/wire.rs), lines 336–365; [fragment schema](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-core/src/manifest/package/fragment.rs), lines 12–34; [condition resolution](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-workspace/src/install/bootgen/conditions.rs), lines 21–66; [when condition grammar](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-core/src/manifest/package/when.rs), lines 12–40.
- D3: [generated redirect](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-workspace/src/boot_artifacts/redirect.rs), lines 48–70; [INDEX read contract](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-workspace/src/boot_artifacts.rs), lines 111–121.
- D4: [complete dependency closure and contributions](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-workspace/src/install/bootgen.rs), lines 392–522; [static-transitive propagation](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-workspace/src/install/bootgen/transitive.rs), lines 12–37; [whole-contribution composition](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-workspace/src/boot.rs), lines 347–409.
- D5: [feature vocabulary](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-resolver/src/features.rs), lines 20–35, 121–171; [feature definitions](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-core/src/manifest/package/features.rs), lines 10–47.
- D6: [wal 1.0.0 manifest](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.world/wal/v1.0.0/vibe.toml), lines complete file; [sync-from-code 1.0.0 manifest](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.world/sync-from-code/v1.0.0/vibe.toml), lines complete file; [conflict-protocol 1.0.0 manifest](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.world/conflict-protocol/v1.0.0/vibe.toml), lines complete file.
- D7: [WAL boot](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.world/wal/v1.0.0/vibevm/vibespecs/boot/10-flow-wal.xml), lines 13–70.
- D8: [Sync boot](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.world/sync-from-code/v1.0.0/vibevm/vibespecs/boot/20-flow-sync-from-code.xml), lines 7–50.
- D9: [Conflict boot](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.world/conflict-protocol/v1.0.0/vibevm/vibespecs/boot/35-flow-conflict-protocol.xml), lines 11–56.
- D10: [source override](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-core/src/manifest/project.rs), lines 425–450.
- D11: [visibility overrides](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-core/src/manifest/package/visibility.rs), lines 90–176; [dependency visibility controls](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-core/src/manifest/package/capabilities.rs), lines 91–108.
- D12: [normal source/fact merging](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-spec/src/merge.rs), lines 12–42; [normal boot seed construction](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-workspace/src/boot_artifacts/inputs.rs), lines 81–104.
- D13: [full Sync protocol](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.world/sync-from-code/v1.0.0/vibevm/vibespecs/flows/sync-from-code/SYNC-PROTOCOL.xml), lines 12–14, 53–54, 74–139, 145–147; [when to apply](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.world/sync-from-code/v1.0.0/vibevm/vibespecs/flows/sync-from-code/when-to-apply.xml), lines 41–46; [review workflow](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.world/sync-from-code/v1.0.0/vibevm/vibespecs/flows/sync-from-code/review-workflow.xml), lines 86–114.
- D14: [full Conflict protocol](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.world/conflict-protocol/v1.0.0/vibevm/vibespecs/flows/conflict-protocol/CONFLICT-PROTOCOL.xml), lines 42–111; [uncertainty stop exceptions](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.world/conflict-protocol/v1.0.0/vibevm/vibespecs/flows/conflict-protocol/uncertainty-protocol.xml), lines 115–138.
- D15: [Conflict failure recovery](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.world/conflict-protocol/v1.0.0/vibevm/vibespecs/flows/conflict-protocol/failure-modes.xml), lines 57–72, 95–111, 130–149.
- D16: [full WAL protocol](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.world/wal/v1.0.0/vibevm/vibespecs/flows/wal/WAL-PROTOCOL.xml), lines 85–145; [session end](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.world/wal/v1.0.0/vibevm/vibespecs/flows/wal/session-end-hook.xml), lines 13–30, 93–105.
- D17: [morning routine](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.world/wal/v1.0.0/vibevm/vibespecs/flows/wal/morning-routine.xml), lines 14–32, 63–98; [cold resume](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.world/wal/v1.0.0/vibevm/vibespecs/flows/wal/cold-resume.xml), lines 95–145.
- D18: [WAL status skill](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/vibevm/vibepacks/org.vibevm.world/wal/v1.0.0/vibevm/vibespecs/skills/wal-status/SKILL.md), lines 13–22, 45.
- D19: [update modes](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-cli/src/commands/update.rs), lines 1–12; [uninstall regeneration](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-cli/src/commands/uninstall.rs), lines 1–5, 175–184; [reinstall modes](https://github.com/vibevm/vibevm/blob/b6659978453f50e6d1d4d99626d70b980a2c5847/crates/vibe-cli/src/commands/reinstall.rs), lines 1–25.

The current Relay contracts linked throughout are repository-local navigation.
For this comparison their evidence revision is always
`4f0e0e38980854fcb09dc718841ade3102a8108f`; future edits do not silently update
the baseline studied here.
