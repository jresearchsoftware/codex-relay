# Shared subagent instructions

Reviewed: **October 3, 2026**.

This is reusable guidance for projects that explicitly adopt it in their
`AGENTS.md` or global Codex instructions. Adoption **highly recommends proactive
delegation when useful** at every supported parent effort, including low,
medium, high, xhigh and max; Ultra is not required. There is no minimum subagent
count. The consumer retains task, model, cost and permission authority. Read
this together with the consumer's applicable instructions.

## When to delegate

When Subagents is On and the session exposes subagent tools, **proactive
delegation is highly recommended where its expected benefit justifies the
overhead**. Consider useful independent assignments before a long investigation
or implementation, and reassess when new independent work appears. Use judgment
to decide whether to delegate; useful delegation needs no separate user request
or Ultra.

Prefer delegation when a bounded assignment can materially improve completion time,
evidence quality or the main agent's context management. Useful assignments
include code-path exploration, separate research questions, log diagnosis,
implementation in distinct components, and focused checks of a candidate change.
The parent should retain requirements, integration and the critical path.

- For substantial work, prefer starting useful independent helpers early.
  Indicative ranges are 1-2 helpers, or 2-4 for broader work, when justified by
  independent assignments and runtime capacity.
- These ranges are suggestions, with no minimum or quota. Zero helpers is a
  valid choice even when Subagents is On. Respect the actual concurrent limit,
  including whether it counts the parent. Reuse an existing helper for related
  follow-up work instead of repeatedly spawning replacements.
- Skip delegation for trivial edits, quick factual answers, tightly sequential
  work or assignments whose coordination cost exceeds their value. Complete
  such tasks directly without needing to turn Subagents Off or justify routine
  single-agent work.
- Batch simple independent tool calls directly when that is sufficient. A
  subagent should own a meaningful question or deliverable, not one search.
- Subagents Off, a task prohibition, unavailable tools or a higher-priority
  restriction prevents spawning. On alone does not override these constraints.
  Continue useful work yourself and report any consequential limitation.

## Select a profile for each assignment

Select the child model and effort independently of the parent's profile, within
the consumer's allowed choices. Use ambiguity, reasoning depth, scope and the
cost of an incorrect result. A research task may be simple retrieval or difficult
synthesis; a technical task may be mechanical or security-critical. Job titles
alone do not determine the profile.

These are **our starting recommendations**, not provider guarantees or a
benchmarked optimum for every subtask. They preserve Landscape's existing
Sol/xhigh recommendation for complex work. The source repository's
`current-model-landscape.yaml` supplies the supporting evidence; a copied policy
contains the recommendations needed for delegation without loading that file.

| Assignment | Starting model / effort | Escalate when |
| --- | --- | --- |
| Locate symbols, inventory files, extract specified facts, check a known documentation option | `gpt-6-luna / high` | The answer requires causal reasoning, conflicting evidence or broad inference |
| Narrow, mechanical change with an explicit recipe and an objective local check | `gpt-6-luna / high` | Requirements or impact are uncertain; the change affects a sensitive boundary |
| Ordinary bounded implementation, test design, or synthesis of clear sources | `gpt-6.1-sol / medium` | Hidden dependencies, non-obvious failures or competing interpretations appear |
| Cross-component debugging, evidence reconciliation, substantive correctness or security review | `gpt-6.1-sol / high` | Deep causal analysis, concurrency, trust boundaries or architectural ambiguity dominate |
| Complex coding, architecture, difficult research synthesis or high-consequence analysis | `gpt-6.1-sol / xhigh` | A specific unresolved reasoning problem justifies further escalation |
| Exceptional escalation with a concrete remaining question and permission for the profile | `gpt-6.1-sol / max`, then optionally `gpt-6-astra / max` | Consumer policy and task evidence justify the marginal cost |

Use Sol rather than Luna when you cannot bound the task confidently. Do not use
a lightweight helper as the sole judge of an uncertain or consequential change.
An explicit task-wide model restriction applies to children too; a profile
specified only for the parent does not by itself specify every child's profile.
Preserve explicit child profiles and effort ceilings.

Choose both model **and** effort explicitly when the spawning interface supports
them. Adoption of this policy requests these per-assignment selections; there
is no need to ask again for each permitted helper. Check the runtime's exposed
choices and consumer allowlist rather than treating an API capability list as
proof of Codex access. Keep the parent's selected model and effort unchanged.

If a preferred profile is unavailable, choose an allowed alternative with
adequate capability, or perform the work in the parent. State a material
substitution. If the interface cannot set child profiles, use supported
inheritance and disclose that limitation. Do not invent model identifiers,
change client configuration mid-task or launch a separate CLI/Relay worker to
circumvent the session. A profile explicitly locked by task authority cannot
be silently substituted.

Ultra is not required for delegation. Do not infer that subagents require Ultra
or automatically select it for children. Treat delegation capability separately
from consumer-defined model/effort values, and preserve explicit consumer or
task profile contracts.

Standard speed is the default unless the user requests another speed. More
helpers and higher effort can increase total usage; token prices and benchmark
API costs do not predict subscription allowance.

## Give each helper a complete, bounded assignment

Prefer a fresh child context with a self-contained assignment. Include:

1. The goal and the specific question or deliverable.
2. Relevant facts, source paths or URLs, and the required revision if applicable.
3. Applicable project instructions, decisions, prohibitions and authority limits.
4. Read-only or write scope, ownership of files, and coordination dependencies.
5. Completion criteria, relevant validation and a concise output format.

Pass wider history only when it is needed to preserve material context. If the
tool only supports model/effort overrides with a fresh or limited-history fork,
use that supported mode and put the essential context in the assignment.
Do not send secrets or unnecessary transcripts to a helper. Ask helpers to
report evidence, uncertainty and blockers promptly. Children should not create
their own agents unless the parent explicitly assigns a further decomposition
and accounts for its scope and concurrency.

Example assignment structure:

```text
Goal: <bounded question or deliverable>
Profile: <requested model / effort and short rationale>
Context: <facts, paths, revision and relevant prior decisions>
Instructions: <applicable guidance and constraints>
Scope: <read-only, or exclusively owned files>
Dependencies: <inputs needed and work that must wait>
Done when: <result and meaningful validation>
Return: <conclusion, evidence references, checks, uncertainties>
Do not spawn additional agents unless explicitly assigned by the parent.
```

## Coordinate and verify

When delegating, start independent helpers early and continue useful work while
they run. Do not duplicate an assignment unless independent reasoning is the
stated purpose.
Concurrent writers must own separate files or isolated worktrees; serialize
overlapping changes. Coordinate build outputs, caches and other mutable shared
resources as well as source files. Use the project's supported test/build tools.

Collect every result that is needed for completion. Check material claims against
the cited source, inspect edits, reconcile disagreements and run the appropriate
integrated validation. A helper's report is evidence to assess, not automatic
proof of success. Reuse or redirect helpers when new evidence changes the task;
avoid identical retries without new evidence. Stop unnecessary work and release
finished helpers when the interface supports it.

The parent owns the final result and a concise account of relevant checks and
limitations. State requested child profiles where useful; call them actual
profiles only when runtime evidence exposes those values. Do not create a new
task ledger merely to record delegation.

Delegation preserves the task's external-action, publication, credential,
production and review boundaries. A helper's focused review can improve the
candidate but does not supply independent governance acceptance required by the
consumer. Existing Writer/Reviewer responsibilities remain consumer-owned.

## Source and adoption boundary

The provider documents delegation triggers and profile configuration in
[Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents?surface=app).
Our workload matrix and delegation thresholds are project recommendations based
on that capability and the repository's model evidence, not provider mandates.
The existing [Relay guidance](https://github.com/jresearchsoftware/codex-relay/blob/main/AGENTS.md)
informs the bounded-context and authority rules.

Use the latest policy from Landscape `main` when integrating or updating a
consumer. Recording its source commit is optional unless the consumer requires
it. At task admission or session start, use the guidance available through the
adopted integration and keep it stable for that task. Dynamic selection means
choosing each child from that guidance, not re-reading moving Landscape
recommendations during execution. The parent's admitted profile remains fixed.
Relay still executes the profile resolved by its consumer; it gains no
model-routing role.

For global and portable project integration, see `docs/subagents-adoption.md`
in the source Landscape repository. That guide is for setup, not a prerequisite
for executing this policy in a consumer.
