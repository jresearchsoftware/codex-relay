# Development Governance

`org.jresearch.ai/development-governance` is one passive MIT-licensed VibeVM
flow. One manifest version covers its conditional boot, nine protocols, optional
operator guides and manually invoked [ChatGPT maintenance assets](tools/chatgpt/README.md).
It has no hooks, executable capabilities, dependencies or native Codex Skills.
Ordinary reading requires no Python, VibeVM command or external service.

The installed [CHANGELOG](CHANGELOG.md) describes version changes, breaking
obligations and migration, including the 2.7.0 → 3.0.0 transition. It is part of
the package payload. This README is the current overview; actual acceptance and
publication evidence remains in source Issues/PRs, workflows and distribution
tags. Frozen historical versions retain their original bytes.

Version 4.0.0 adds [PC-013](vibevm/vibespecs/protocols/proportional-controls.md#PC-013)
and tightens [IR-012–IR-015](vibevm/vibespecs/protocols/independent-review.md#IR-012):
bind each blocker to an existing obligation and separate proposed requirements
before negative reporting or Task-amendment discussion. Quantify workflow/cost
effects; preserve genuine security obligations and explicit owner scope authority.
Existing adopters must reconcile this mandatory report content. It adds no
approval/wait stage or topic adoption; see the 3.0.0 → 4.0.0 changelog entry.

| Topic and rule prefix | Conditional applicability |
| --- | --- |
| [Proportional controls — PC](vibevm/vibespecs/protocols/proportional-controls.md) | Proposed security, validation or operator controls, including behaviorally free hardening. |
| [Requirement authority — RA](vibevm/vibespecs/protocols/requirement-authority.md) | Binding requirements versus revisable engineering choices. |
| [Package versioning — PV](vibevm/vibespecs/protocols/package-versioning.md) | Explicitly adopted package lifecycle, preparation, versions and consumer updates. |
| [Task handoff — TH](vibevm/vibespecs/protocols/task-handoff.md) | Explicitly adopted Task/Step authority, Outcome, independent-review handoff, acceptance and continuation. |
| [Producer self-adoption — SA](vibevm/vibespecs/protocols/self-adoption.md) | Explicitly adopted use of guidance a producer authors, with accepted-source/candidate separation. |
| [GitHub repository governance — GH](vibevm/vibespecs/protocols/github-repository-governance.md) | Explicitly adopted workflow/protection decisions preserving PR, direct-main, distribution and mixed paths. |
| [Independent review — IR](vibevm/vibespecs/protocols/independent-review.md) | Explicitly adopted assessment methodology, evidence, complete affected behavior, findings and rereview. |
| [Contract and decision maintenance — CD](vibevm/vibespecs/protocols/contract-and-decision-maintenance.md) | Explicitly adopted material contract changes, durable decisions and same-change human guidance. |
| [Context loading — CL](vibevm/vibespecs/protocols/context-loading.md) | Explicitly adopted decision-relevant startup, triggered complete detail and targeted mutable refresh. |

Installing/updating the package and following a cross-topic reference do not
adopt a topic. Each consumer owns accepted human instructions, local authority,
review sufficiency/identity, protected actions, specialist methods and release
cadence. Existing local rules remain canonical until a separately reviewed
migration adopts shared content and removes genuine duplicates together.
Task Handoff requires independent assessment under project rules; consumers
select Independent Review separately for its shared methodology. That method
adds no universal owner-wait or publication permission rule.

For adopted Task Handoff, [TH-028](vibevm/vibespecs/protocols/task-handoff.md#TH-028)
adds executor-owned Draft/Ready handoff for applicable implementation PRs: Draft
before newly admitted work; verified successful Outcome before verified Ready
for independent review. Automation ownership and supported local capabilities
remain with each project. Ready grants no approval, merge or completion authority.
This mandatory lifecycle change requires deliberate consumer migration; updating
the dependency alone activates no new topic or tooling.

The [onboarding procedure](vibevm/vibespecs/guides/onboarding.md) and
[worked examples](vibevm/vibespecs/guides/onboarding-examples.md) are loaded on an
explicit human onboarding request. The optional
[engineering-methods guide](vibevm/vibespecs/guides/engineering-methods.md) offers
FPF as external advice only when useful; MCP/FPF access is not required. Guides
are operator aids, not additional normative topics or adoption mechanisms.

<a id="DG-001"></a>
**DG-001 — Stable rule addresses.**

An explicit anchor such as [TH-006](vibevm/vibespecs/protocols/task-handoff.md#TH-006)
names a meaningful obligation with its qualifiers and exceptions. Its following
text through the next labeled rule or section belongs to that rule. IDs identify
meaning, not paragraph order, headings or line numbers. Keep an ID when that
meaning remains stable; never reuse a retired ID. For a moved, replaced or split
rule, retain a resolvable old anchor with an unambiguous destination/supersession
note and record the mapping in the changelog. Existing heading links remain valid.
The 3.0.0 changelog maps material previously unnumbered 2.7.0 sections; there
were no earlier rule IDs to retire. Guide addresses ON/EM and boot DG-002 locate
conditional procedures/routes; they confer no topic adoption. Client maintenance
assets remain governance-neutral implementation aids. IDs require no database,
service or per-sentence attestation.

Canonical source is [shared-governance](https://github.com/jresearchsoftware/shared-governance).
[Distribution tags](https://github.com/jrs-vibevm/org.jresearch.ai.development-governance/tags)
retain version identity; `DISTRIBUTION.json` binds a public export to its exact
source. Copyright (c) 2026 shared-governance contributors; derived governance text
Copyright (c) 2026 Codex Relay contributors. See [LICENSE](LICENSE).
