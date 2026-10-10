# Frozen governance flow: Relay semantic coverage

Task #97, Step 2; source assessment, 2026-10-10. This is review evidence, not
operative policy, package adoption or acceptance of a methodology change.

**Both Task #15 candidates lack full equivalence in `development-governance`
0.1.0.** Its control procedure is preserved, but the explicit contract-decision
and existing-proof procedures are incomplete within that domain. Recommend
producer-owned correction and independent acceptance of a new immutable version
before transferring those reusable obligations. Relay's current rules remain
intact. This Step delivers the assessment; it does not perform the correction
or authorize migration. Task #97 remains keep-open.

## Baseline and content identity

The current Relay baseline is `4d49ff52a3747389f0b1e3e4e6c6add716cc3363`.
Anonymous GitHub API reads matched the admitted charter and selected Decision
body hashes (`f89c6dfed8ea9ef569193fdaf086dd3a35e02d701fc26ba4e5e648a7efa319a2`
and `a2d7a87c5a658e897fee8b6b485a429b9fb40377fc7df483b3e712fdf4a8ab94`).
The active Step boundaries restrict the enduring Decision's later adoption path
to source analysis and non-behavior-changing documentation here.

The independently read frozen public flow is at distribution commit
`2c0668ab6cd56409a5326c4ab56e8f0a7d26036a` in
`jrs-vibevm/org.jresearch.ai.development-governance`. The observed annotated
`v0.1.0` tag object `0098ff6f983bb02345b3c7d270497fc340006408` peels to that
commit; neither the tag nor the version is treated as an immutable guarantee.
[DISTRIBUTION.json][receipt] identifies producer source
`3fa243b83a630ccd4973114e5cad12e1351d1558` and payload SHA-256
`b53c64b793b80395a4e8958239e1414c4a56161ed38493ed299e1493114f62d0`.
The five payload files were read at both full commits and compared byte-for-byte
with the receipt's file hashes: manifest, README, LICENSE, conditional boot and
protocol. The distribution tree contains exactly those files plus the receipt.

The [whole protocol][protocol] is 4,494 bytes, SHA-256
`f747508ab8d936299478029f17be3891f877f0a5e5c302c1e606f9c1e51b99a0`.
It also equals the accepted producer's active ordinary protocol at
`d1683d097988d9c2c45b4d474a6531d13d4514a3`. [PR #16's exact-head
review][producer-review] accepted the semantic-completeness authoring rule and
explicitly left these two coverage candidates unresolved; its merge
`d6e369337c33df4b16e32ed229d9521d7cf3f3b3` and Task #15 closure do not repair
the package. The [producer Outcome][producer-outcome] is the handoff, not
additional execution authority.

## Complete control-domain coverage

R1 is the baseline [material contract gate][relay-gate]; R2 is
[minimum sufficient ceremony][relay-ceremony]; R3 is the full
[control procedure][relay-controls]. P line numbers refer to the complete
76-line frozen [protocol][protocol], not a keyword excerpt. B is its
[conditional boot][package-boot]. “Preserved” includes all listed qualifiers;
“equivalent” identifies a neutral replacement of a product binding. No row uses
remaining Relay rules to compensate for shared content.

| Material obligation, trigger or exception | Frozen shared evidence and verdict |
| --- | --- |
| New security, validation, privilege, platform/filesystem or operator controls require relevant assessment, including free hardening; unrelated tasks need no procedure read (R2; Relay JIT loading) | B lines 3–8 routes relevant work, explicitly includes free hardening, and skips unrelated tasks. P 3–5 stays within owning-project scope/authority. **Preserved** at the authored-text level; actual model traversal is a separate claim. |
| Concrete accepted risk; prevention or stricter alternatives alone do not justify controls; choose the cheapest acceptable mechanism (R3 65–67) | P 20–22: **preserved**. This does not alone express the existing-proof rule below. |
| Free hardening needs no separate owner decision only if workflows remain supported and there is no material operator work, restriction, prerequisite, gate, trust boundary, recovery burden or false-positive surface; safe-file/API/logging examples (R3 69–74) | P 24–29: **preserved**, including exclusions and examples. |
| Explicit owner authority before mandatory cost-bearing controls; all six cost classes (workflow narrowing; command/checkout/platform/admin/credential/recovery work; trust/privilege/sandbox/ACL/execution boundary; gate/validation expansion/unrelated debt; persistent state/sync/lifecycle/failure modes; time/maintenance/review/false positives/control defects) (R3 76–88) | P 31–43: **preserved**. Canonical owner authority remains required, rather than being granted by the package. |
| Before proposing such controls: attacker/failure capability, harm path, impact/privilege, insufficiency of existing controls and operator/maintenance cost; risk acceptance or doing nothing is valid; security/test preference grants no authority (R3 90–94) | P 45–49: **preserved**. |
| Encounter frequency, compliant path versus workaround, disabling/bypass/unsafe storage/duplicate state/abandonment; predictable unsafe workarounds do not automatically improve security (R3 96–101) | P 51–56: **preserved**. |
| Detection/warning/recovery for visible local reversible cheap failures unless accepted risk requires blocking; stronger prevention for silent/propagating/irreversible or credential/privacy/compliance/production/publication/merge/protected risks (R3 103–108) | P 58–63: **preserved**, including the blocking exception and stronger-prevention cases. |
| Common environments work by default; unusual filesystem/platform/permissions/service conditions alone do not justify failure; blocks bind to accepted invariants, lower-cost warning/recovery where sufficient (R3 110–114) | P 65–69: **preserved**. This does not authorize bypassing an existing protected boundary. |
| Independent review exercises the simplest authority-defined owner-facing black-box path and assesses unnecessary state/gates/authority coupling/prerequisites/actions (R3 116–119; R2) | P 71–74: **preserved**. Test success does not itself establish acceptance. |
| Unauthorized material operator-contract delta blocks acceptance until explicit owner disposition (R1; R3 119–121) | P 75–76: **equivalent** neutral disposition requirement. The literal `OWNER_DECISION_REQUIRED`, Issue/Decision/Request representation and native verdict mechanics are **Relay product-specific**, not required package vocabulary. |
| All material capability/workflow changes need prior authority; equivalent observable refactoring needs no separate decision; discoveries from implementation/security/tests/review/remediation preserve safe behavior or stop; compare every changed surface's old/new behavior before approval; never normalize implementation into policy retroactively (R1) | P 5, 9–11, 31–32, 49 and 71–76 cover scope, workflow preservation, cost-bearing authority and final disposition, but not the complete decision sequence or refactoring exception. **Shared omission within the control/operator-workflow domain: G1**, detailed below. Broader non-control contract review is not automatically owned by this package. |
| Least complex sufficient process; prefer existing source/check/review evidence; a separate packet needs an independent purpose; no redundant commit/review/gate/state transition when the same invariant is already proved; stronger controls need concrete risk or authority (R2 271–276) | P 13–16 rejects a required new checklist/service/ledger/operator step and uses existing records; P 20–22 prefers cheap controls. **Partial preservation, shared omission: G2**. It does not establish the specific existing-proof/independent-purpose tests. |

R2's same-Task documentation, targeted correction checks and avoiding duplicate
CI status publication support minimum ceremony. Their general evidence-reuse
aim is consistent with P 13–16; exact Relay suite, native CI cadence, one Writer
Outcome, Issue/PR records and publication channels are **Relay-owned bindings**.
Decision promotion, finding-provenance review and warning acquisition remain
their separate existing policy domains; this assessment neither transfers nor
reclassifies them as proportional-controls duplicates.

## Resolve the two candidates

**G1 — incomplete reusable decision procedure, not demonstrated equivalence.**
Within control changes, explicit owner disposition after detecting an
unauthorized delta is narrower than a procedure that preserves safe existing
behavior or stops while implementing, actively compares old/new behavior before
approval, and forbids making implementation its own retrospective authority.
The listed material surfaces include entrypoints/commands, inputs, visible
surfaces, actor roles, automatic/manual transitions, extra actions and
status/recovery behavior; those are portable operator-contract concepts.
ChatGPT/GitHub paths, exact Task/CR representation and native verdict publication
are Relay bindings. Preserving the existing rule does not require exporting
Relay's identifiers or changing the Reviewer service.

The [accepted design inventory][design] calls general contract discipline a
shared candidate for a future review flow. That is a distribution proposal, not
an accepted waiver of control-related guarantees or permission to remove them.
The narrower package can remain useful while incomplete for the proposed
whole-domain transfer. A broader review flow's eventual scope/ownership, or any
intentional reduction of these obligations, is **owner-decision required**.
No accepted intentional semantic weakening was found in the selected authority.

**G2 — incomplete existing-proof rule, not demonstrated equivalence.** A cheap,
optional extra review or commit can still duplicate sufficient proof; no-ledger
guidance does not decide whether it serves an independent purpose. R2 explicitly
tests existing proof of the same invariant before adding a commit, review pass,
gate or state transition. P never states that test. The specific Git/Relay
artifacts are examples/bindings; avoiding redundant proof and requiring an
independent purpose are reusable. The exception for concrete risk or authority
must travel with that rule. It does not waive required independent review or
authorize skipping required checks for a changed candidate.

These are source-level omissions relative to the accepted Relay control domain,
not evidence of a new regression introduced by Task #15, the ordinary-flow
conversion, or this assessment. [Provenance][producer-provenance] traces the
procedure to accepted Relay `9aad5bbc746c9ba0ff25534efca33eae3ef1e472` and
the original Skill at producer `fd609af8a1ea8ce015fda4652e5a8c444ca821c5`.
The original 3,584-byte procedure hash is
`cfa62afee0aa267aa58bb966faece0225cb717a82fbb93d3d3b4bf7b29704c6c`;
the flow retains it after the 910-byte adapted wrapper. Both gaps are already
absent there: the conversion did not newly delete them.

Bounded Relay history strengthens that finding: the existing-proof rule is
already in the [initial public AGENTS][initial]; the complete contract gate was
added in [accepted commit 18bb516][gate-origin], before proportional controls
were added in [fc559c1][controls-origin]. That later control section explicitly
binds back to the existing gate. Current canonical obligations, the extraction
baseline and those origin diffs were compared. The historical Documentation
split motivates not treating one paragraph as the domain; this Step does not
claim an exhaustive pre-split reconstruction or qualification of unrelated
rules. The direct, still-accepted Relay evidence suffices for these two findings.

**Producer-owner handoff:** separately admit correction of the control-relevant
G1 procedure/refactoring exception and G2 existing-proof/independent-purpose
rule, preserving their qualifiers and authority exceptions; independently review
the source and publish a new immutable package version. Task #15 is closed and
does not admit this correction. Do not rewrite `0.1.0`, silently compensate with
an undocumented Relay overlay, or broaden the package into all review governance
without owner disposition. If the owner chooses a different semantic boundary,
record that choice in canonical authority before any corresponding transfer.

## Live bindings and independent-consumer counterfactuals

Automatic and manual Codex reach root AGENTS and its relevant local-policy
pointer; Task #99's accepted native route reads committed INDEX, `00-core.md`
and `90-user.md` while preserving that authority once. The [local user
route][local-route] still points to the Relay procedure. The package manifest
declares an ordinary passive flow, no Skill/dependencies/executable capability;
its B pointer does not modify these consumer routes. Installing a Skill alone
would not change the worker prompt or owner-applied ChatGPT instructions.

The [runtime prompt module][prompt] supplies progress-bounded execution, not
either complete candidate procedure. [Runtime][runtime-input] appends it to
automatic input; the [manual handoff][manual-input] uses the same module and
repository/live-authority instruction. The optional [hook contract][hooks]
and inspected Stop helper only support bounded diagnosis/session recovery;
they do not supply approval comparisons or redundant-proof decisions. The
[Reviewer publication contract][reviewer] validates supplied verdict/CR and
exact-head publication; substantive independent judgment remains the reviewer's
responsibility. These product/developer bindings cannot prove package coverage
and stay unchanged.

Two text-level walkthroughs use only the frozen protocol and ordinary scenario
facts, without Relay residual instructions:

| Independent documentation consumer scenario | What the standalone package supplies; remaining gap |
| --- | --- |
| A proposed mandatory Linux checkout and credential step for routine Markdown edits; tests prefer the new path despite absent owner authorization | P classifies costs, requires prior owner authority, assesses supported environments and cheaper alternatives, and blocks acceptance of an unauthorized delta. It does not fully direct safe preservation/stop during implementation, old/new surface comparison before approval or prohibition of retrospective policy normalization: **G1 remains**. |
| The exact unchanged invariant already has sufficient independent proof; an agent proposes another commit, review pass or lifecycle state “for assurance” | P discourages costly machinery and requires no new ledger/step. It lacks the explicit same-invariant existing-proof and independent-purpose decision, even for inexpensive repetition: **G2 remains**. New evidence, a changed candidate or concrete accepted risk can justify further proof under the original rule. |

For Relay, the counterfactual deletion of the corresponding reusable R1/R2
slices likewise leaves G1/G2 unaccounted for. Keeping them currently protects
Relay but is not evidence that shared extraction succeeded. These walkthroughs
establish a coverage argument, not observed Codex compliance or failure.

## Safest later migration and evidence limits

Resolve producer coverage first, then obtain a complete successor consumer
Request with explicit owner routing/semantic disposition and exact starting
head. Reverify new accepted source, public full distribution commit/tag object,
receipt and complete hashes, with the existing VibeVM 1.0.7 pin. In one separately
reviewed consumer change, adopt pinned committed content and remove only proven
reusable duplicates, preserving product bindings/local overlays and one active
semantic owner. Assess supported ordinary-flow routing and the same-byte
Git/native baseline; no automatic Skill or methodology adoption is inferred.

That later qualification must distinguish static files, CLI behavior and actual
model traversal; exercise original and independent consumers without residual
rules, clean-clone/offline reads without a mandatory VibeVM executable/network,
repeatable update/removal and Git rollback. Existing Task #99 routing evidence
does not qualify package consumption. This Step adds no new mandatory gate,
owner action, worker injection, package graph or runtime command.

Anonymous full-SHA source reads, file/hash comparisons and the walkthroughs are
the semantic evidence here. No fresh package materialization, model behavior,
production/runtime deployment, native hook lifecycle or exhaustive historical
methodology qualification is claimed. Actual runtime model/effort telemetry is
UNAVAILABLE; no subagents were used. Local candidate checks are reported in the
worker handoff for trusted Writer's exact-head Outcome.

Validation used existing disposable Node 22.20.0, Rust 1.90.0 and Python/Ansible
tools under ordinary Linux UID 983. Initial Rustup routing, inherited shared-temp
ownership and Ansible's inaccessible default staging path were resolved with
process-local tool selection and task-owned temporary paths. A private copy of
the synthetic consumer config satisfied the unchanged permission contract.
A temporary validation-wrapper edit also caused a shell error after Node tests
passed; the final stable-wrapper run passed. None required a product correction
or host/permission repair: affected code, fixtures and tests are unchanged from
the baseline above. The final deployment suite's 299 skipped tests remain
unqualified; its 19 Ansible `crypt`/Jinja invalid-escape deprecation warnings are
dependency evidence, not introduced policy defects. Installed-runtime and
root-only proof remains the native exact-head CI responsibility.

The in-progress routing job's public check annotations were inspected and empty;
that observation cannot establish terminal warning completeness. The worker
cannot acquire the complete terminal Writer/controller warning evidence or
invoke Reviewer; independent review must inspect those primary supported
surfaces. No absence-of-execution-warnings claim follows from local checks.
Publication, independent acceptance, merge, deployment, Issue closure and any
successor execution remain separate.

[relay-gate]: https://github.com/jresearchsoftware/codex-relay/blob/4d49ff52a3747389f0b1e3e4e6c6add716cc3363/AGENTS.md#L201-L223
[relay-ceremony]: https://github.com/jresearchsoftware/codex-relay/blob/4d49ff52a3747389f0b1e3e4e6c6add716cc3363/AGENTS.md#L257-L289
[relay-controls]: https://github.com/jresearchsoftware/codex-relay/blob/4d49ff52a3747389f0b1e3e4e6c6add716cc3363/docs/execution-policy.md#L63-L121
[protocol]: https://github.com/jrs-vibevm/org.jresearch.ai.development-governance/blob/2c0668ab6cd56409a5326c4ab56e8f0a7d26036a/vibevm/vibespecs/protocols/proportional-controls.md
[package-boot]: https://github.com/jrs-vibevm/org.jresearch.ai.development-governance/blob/2c0668ab6cd56409a5326c4ab56e8f0a7d26036a/vibevm/vibespecs/boot/development-governance.md
[receipt]: https://github.com/jrs-vibevm/org.jresearch.ai.development-governance/blob/2c0668ab6cd56409a5326c4ab56e8f0a7d26036a/DISTRIBUTION.json
[producer-review]: https://github.com/jresearchsoftware/shared-governance/pull/16#pullrequestreview-5479283090
[producer-outcome]: https://github.com/jresearchsoftware/shared-governance/issues/15#issuecomment-6098329338
[producer-provenance]: https://github.com/jresearchsoftware/shared-governance/blob/d1683d097988d9c2c45b4d474a6531d13d4514a3/docs/provenance.md
[design]: https://github.com/jresearchsoftware/codex-relay/blob/9aad5bbc746c9ba0ff25534efca33eae3ef1e472/docs/vibevm-governance-design.md#ownership-inventory
[initial]: https://github.com/jresearchsoftware/codex-relay/blob/c0e0b5ce3f52a311f473eca3a9f8694eb75c23f8/AGENTS.md#minimum-sufficient-ceremony
[gate-origin]: https://github.com/jresearchsoftware/codex-relay/commit/18bb51630de85b4ea4f1a4dd7b30875c2676b507
[controls-origin]: https://github.com/jresearchsoftware/codex-relay/commit/fc559c107ada580c7abc0a8136f2dfa2c098ef5c
[local-route]: https://github.com/jresearchsoftware/codex-relay/blob/4d49ff52a3747389f0b1e3e4e6c6add716cc3363/vibevm/vibespecs/boot/90-user.md
[prompt]: https://github.com/jresearchsoftware/codex-relay/blob/4d49ff52a3747389f0b1e3e4e6c6add716cc3363/runtime/src/execution-policy.mjs
[runtime-input]: https://github.com/jresearchsoftware/codex-relay/blob/4d49ff52a3747389f0b1e3e4e6c6add716cc3363/runtime/src/codex-runtime.mjs#L442-L454
[manual-input]: https://github.com/jresearchsoftware/codex-relay/blob/4d49ff52a3747389f0b1e3e4e6c6add716cc3363/controller/src/publication-broker.mjs#L515-L516
[hooks]: https://github.com/jresearchsoftware/codex-relay/blob/4d49ff52a3747389f0b1e3e4e6c6add716cc3363/.codex/hooks/README.md
[reviewer]: https://github.com/jresearchsoftware/codex-relay/blob/4d49ff52a3747389f0b1e3e4e6c6add716cc3363/reviewer/README.md#L207-L231
