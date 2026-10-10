# VibeVM methodology compared with Relay

Task [#102](https://github.com/jresearchsoftware/codex-relay/issues/102), Step 1.
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

Reject unconditional execution of a materially disputed specification and a
hierarchy that lets casual chat or boot text override a trusted Request. Do not
reject explicit specifications, useful recovery state or code-first discovery
merely because their upstream packaging differs. The owner choices and a
minimal proof path appear below.

## Evidence and attribution

### Revisions and accepted workflow evidence

The live Issue body retrieved anonymously through the GitHub API matched the
admitted charter SHA-256
`9947ad075577a4d27fbee250e011a7ac29b53e1aaeb55aa11c9737dda458b850`.
The complete [Request](https://github.com/jresearchsoftware/codex-relay/issues/102#issuecomment-6097671313)
had body digest
`aaa372b4d8ee93a026f5935803e42877c0608c27f17c906c31082efc7ae4e30a`,
the admitted branch/base/starting head, Step 1, and no selected Decisions.
Those digests bind the observed bytes; native comment URLs alone are mutable
evidence, not immutable content or permission to expand scope.

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
| Existing Relay authority tests within complete Node suite | 623 tests passed with an isolated synthetic consumer config on Node 24.19.0. | Confirms existing native binding/supersession/evidence rejection cases. Not comparative model trials or Node 22 qualification. |

The existing authority tests include edited selected evidence rejection,
supersession forks, untrusted copied authority and approval of blocked/stale
results [R1]. These are actual bounded tests of Relay invariants. The scenario
examples that follow are reasoned applications of those results and inspected
contracts, rather than eight recorded Codex sessions.

No token, latency, interruption-frequency, human-time or success-rate benchmark
was conducted. Actual parent/helper model and reasoning-effort telemetry:
**UNAVAILABLE**. Admitted parent profile was `gpt-6.1-sol`/xhigh; two read-only
helpers were requested at `gpt-6.1-sol` xhigh and high. They supplied source and
contract analysis, not independent governance acceptance. Real Codex adherence,
crash/compaction behavior and statistical comparative performance:
**UNVERIFIED**. No external model runs were launched.

The pinned optional WAL status skill still instructs reading `spec/WAL.md`,
whereas its XML boot flow names `vibevm/vibespecs/WAL.xml` [U7, U10]. This is a
source path discrepancy relevant to any future package trial; no installed
projection or model execution was used to determine its operational impact.
Likewise redbook/member WAL and wal-specspaces were inspected as distinct
optional conventions, not installed or concurrency-qualified [U13].

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

## Validation, provenance and warning disposition

Experiments ran as an unprivileged Linux x86_64 user with Python 3.11.2 and
PowerShell 7.6.5. The new probe and reproduced routing probe passed. The existing
checkpoint suite passed. The complete Node test invocation from `package.json`
passed 623 tests using an existing Node 24.19.0 binary and a temporary copy of
the synthetic consumer fixture with mode 0600. No host tools were installed or
consumer settings changed.

The ordinary `npm test` command was unavailable on default PATH; the existing
alternate npm launcher lacked its CLI module. Directly invoking the declared
Node test command provided the full test coverage, with the version limitation
above. An initial direct run rejected the tracked synthetic fixture's existing
group-writable mode (`CONSUMER_CONFIG_INVALID`); the documented qualification
pattern of a private temporary synthetic copy resolved it without changing
repository permissions. This is environment/fixture evidence, not a regression
from the report/probe. Candidate versus starting/base comparison for this
finding is supported by the unchanged fixture and loader; this change touches
neither. The final exact candidate identity belongs in the Writer's Outcome,
not a self-referential SHA inside this report.

`python3 -m pytest -q deploy/tests deploy/ansible/tests` could not start because
pytest is missing. Cargo fmt/tests could not start because Cargo is missing;
`scripts/qualify.py` consequently could not build its Reviewer fixture. These
are local environment gaps, not PASS or new product defects. Native exact-head
CI and any separately required installed-runtime proof remain pending Writer
publication; prior PR #100 checks do not close these gaps. No privileged
qualification, native lifecycle, consumer isolation/credentials, deployment,
merge, closure or release proof is claimed.

An anonymous current-attempt API read observed an in-progress Actions run and
its in-progress routing job with zero check annotations at that instant. This
is partial, changing evidence: the terminal Writer Outcome and complete
controller/runtime warning evidence do not yet exist or are not exposed to
this worker. Writer and independent review must acquire and disposition the
supported terminal surfaces. Historical reads and the partial zero count do
not establish that no execution warnings exist. Local limitations are:

| Source/limitation | Impact, scope and next disposition |
| --- | --- |
| Missing local Cargo/pytest and npm launcher gap | Normal validation incomplete locally despite full direct Node coverage. Native candidate checks after Writer publication and the applicable deployment suite must establish their own results; no authority to repair host tooling here. |
| Existing synthetic config mode | Initial Node startup rejected it. Resolved for tests with a private temporary synthetic copy; production permission checks and tracked modes unchanged. |
| CLI/protocol semantic gaps | Pinned upstream behavior, pre-existing outside Relay; not current-task regressions. Scope covers reporting them. Resolve in any later package/guard proposal rather than expanding this research into upstream remediation. |
| Unverified model/lifecycle/comparative performance | Recommendations remain source-grounded hypotheses. Owner may accept no migration or admit the bounded proof above. |
| Current primary warning acquisition gap | Partial in-progress job annotation read only; independent exact-head review must inspect complete terminal attempt/Outcome/check/runtime surfaces. Historical acceptance is insufficient. |

Whitespace, Python syntax and the tracked candidate scan are required for this
new report/fixture and are reported with the final local commit in the worker
handoff. Deterministic validation and read-only helper analysis do not constitute
independent acceptance. Useful work is committed on the admitted task branch;
the worker does not publish a PR/Outcome or issue a Reviewer verdict.

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
- [R1: Relay authority test evidence at the admitted base](https://github.com/jresearchsoftware/codex-relay/blob/4f0e0e38980854fcb09dc718841ade3102a8108f/contracts/test/github-authority.test.mjs), especially untrusted evidence, supersession, selected context and exact-result/warning acceptance cases.
- [Accepted routing assessment at the admitted base](https://github.com/jresearchsoftware/codex-relay/blob/4f0e0e38980854fcb09dc718841ade3102a8108f/docs/vibevm-routing-assessment.md), plus the [local copy](vibevm-routing-assessment.md).

The current Relay contracts linked throughout are repository-local navigation.
For this comparison their evidence revision is always
`4f0e0e38980854fcb09dc718841ade3102a8108f`; future edits do not silently update
the baseline studied here.
