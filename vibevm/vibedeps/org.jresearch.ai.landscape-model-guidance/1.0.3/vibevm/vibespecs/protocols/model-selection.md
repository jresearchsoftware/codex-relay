# General model and effort selection

Use this guidance when the consumer chooses this frozen reference for a new
selection or assessment. Apply the consumer's actual task, client and risk/cost
constraints. These are Landscape recommendations, not provider guarantees,
consumer allowlists or permanent access entitlements. Public evidence was checked
on **2026-11-02**; see [dated evidence and sources](../reference/evidence.md).

## Resolve under consumer authority

1. Identify the task's ambiguity, reasoning depth, scope, latency/cost needs and
   consequence of an incorrect answer. A research assignment can be retrieval
   or difficult synthesis; its job title alone does not select a profile.
2. For a new task, consider the dated starting recommendations below. Check the
   consumer's allowed models and the actual client/plan/workspace controls.
   Public API specifications and catalog release evidence do not prove access.
3. Apply consumer overrides and write the explicit model **and** reasoning
   effort into the consumer's admission/launch authority before execution.
   Record the package version/source baseline when the consumer requires it or
   reproducibility benefits from it. The resolved profile is execution authority.
4. Validate escalation on representative consumer work when warranted. Compare
   the same inputs, quality requirements and permitted runtime; higher effort
   is not a guaranteed coding improvement. Retain the lightest adequate profile.
5. Keep an admitted/running profile stable. A future package, changed benchmark
   or moving Landscape `main` never rebinds it. A change or unavailable admitted
   profile goes through the consumer's own authority and recovery path.

Relay executes the already resolved explicit model/effort. It must not consult
moving Landscape recommendations during execution. This package is no runtime
quota router, task ledger or automatic configuration service.

## Dated general recommendations

The following three general profiles retain the preceding guidance's choices,
without a new ranking or recommendation:

| Task class | Starting model / effort | Condition |
| --- | --- | --- |
| Complex coding, agentic and long-running work | `gpt-6.1-sol / xhigh` | General default, subject to consumer constraints |
| Sol escalation | `gpt-6.1-sol / max` | Validate a task-specific benefit over xhigh |
| Exceptional quality escalation | `gpt-6-astra / max` | Marginal quality justifies cost and consumer policy permits it |

The current Coding Agent Index v2.0 has no Sol/xhigh row. Its historical v1.5
advantage over Sol/max is dated evidence, not a comparison with current results.
Intelligence Index v5.0 measures a different task mix and cannot fill the coding
gap. Retain the accepted default pending comparable coding or consumer-task
evidence; max and Terra results do not measure Sol/xhigh. Neither index proves
which profile wins a particular task. Astra/max remains exceptional; its
historical CLI minimum is unconfirmed.

## Bounded assignment recommendations

These starting choices retain the preceding guidance's assignment-profile
semantics. They are project judgment, not an experimentally established optimum
for each task class. Use them for children only when delegation is authorized
by the consumer and permitted by the session/runtime. They do not change the
parent's selected profile, enable helpers or require Ultra.

| Assignment | Starting model / effort | Escalate when |
| --- | --- | --- |
| Locate symbols, inventory files, extract specified facts, check a known documentation option | `gpt-6-luna / high` | The answer requires causal reasoning, conflicting evidence or broad inference |
| Narrow, mechanical change with an explicit recipe and an objective local check | `gpt-6-luna / high` | Requirements or impact are uncertain; the change affects a sensitive boundary |
| Ordinary bounded implementation, test design, or synthesis of clear sources | `gpt-6.1-sol / medium` | Hidden dependencies, non-obvious failures or competing interpretations appear |
| Cross-component debugging, evidence reconciliation, substantive correctness or security review | `gpt-6.1-sol / high` | Deep causal analysis, concurrency, trust boundaries or architectural ambiguity dominate |
| Complex coding, architecture, difficult research synthesis or high-consequence analysis | `gpt-6.1-sol / xhigh` | A specific unresolved reasoning problem justifies further escalation |
| Exceptional escalation with a concrete remaining question and permission for the profile | `gpt-6.1-sol / max`, then optionally `gpt-6-astra / max` | Consumer policy and task evidence justify the marginal cost |

Use Sol when the task cannot be confidently bounded. A lightweight helper is
not the sole judge of an uncertain or consequential change. Preserve explicit
child profiles and effort ceilings; a task-wide restriction applies to children,
while a parent-only profile does not automatically prescribe each child.
Reassess each assignment and follow-up. Choose model and effort explicitly
where the interface supports them; report a material fallback or unsupported
profile selection. Do not silently substitute a locked profile, invent model
identifiers, change client configuration or launch another worker to circumvent
the session. Any permitted alternative remains the consumer's decision.

## Effort, speed and evidence boundaries

The checked Codex single-agent surface lists `low`, `medium`, `high`, `xhigh`
and `max`; supported controls vary by model, client, plan and workspace. Labels
are not equal compute budgets across generations. An API's `none` support for
some models is not a general Codex control guarantee. Sol 6.1's API supports
low through max and excludes `none` and `minimal`; its API default is medium,
which does not change the Landscape complex-work recommendation.

Ultra is a Codex selection associated with proactive delegation; clients
resolve inference effort and task conditions determine helper use. It is not
a max-equivalent benchmark result. Provider documentation says Luna does not
support Ultra. Ultrafast is a separate inference-speed control. Standard speed
is the default unless the user requests another speed; this flow configures
neither speed nor delegation.

Read a benchmark together with model generation, explicit effort, index version,
harness and components. Do not numerically mix Coding Agent Index v2.0 with
v1.5 or Intelligence Index v5.0 with v4.3.2, replace missing coding profiles
with Intelligence Index scores, or infer Codex access
from an external leaderboard. Intelligence Index numbers may change within a
version through evaluation/methodology changes. Provider claims are distinct
from independent measurements and consumer results.

API USD prices, Codex credit rates and included-plan allowances are separate
quantities. Benchmark API cost is not subscription usage or a project estimate;
agent wall time excludes startup, verification and judging. Speed billing
multipliers are not speed guarantees. This package includes no rate card,
account telemetry, per-account allowance or token-to-quota conversion. A
consumer may assess its own authorized measurements; this passive snapshot
does not fetch them or infer a universal quota formula.
