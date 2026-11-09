# Runtime context for shared subagent guidance

Reviewed: **October 9, 2026**. Source baseline: **Codex CLI 0.160.0**, commit
`a956835d020762cb2b570053af06f643a11c0ecc`. This is an inspected implementation,
not a claim that it is the latest release or that every desktop/server path uses
the same configuration.

## What the inspected source establishes

Codex has separate developer-mode instructions for proactive delegation and for
delegation requested by the user or applicable project/skill instructions. The
[bundled mode texts](https://github.com/openai/codex/blob/a956835d020762cb2b570053af06f643a11c0ecc/codex-rs/prompts/src/model_messages/multi_agent.rs#L46)
make useful parallel work the positive trigger in proactive mode. They specify
no minimum helper count.

With MultiAgent V2 and no custom hint or catalog replacement,
[mode selection](https://github.com/openai/codex/blob/a956835d020762cb2b570053af06f643a11c0ecc/codex-rs/core/src/session/multi_agents.rs#L77)
chooses proactive mode for Ultra and explicit-request-only for other efforts,
including xhigh and max. The latter accepts an explicit delegation request from
applicable `AGENTS.md` or skill instructions. The
[renderer](https://github.com/openai/codex/blob/a956835d020762cb2b570053af06f643a11c0ecc/codex-rs/core/src/context/multi_agent_mode_instructions.rs#L31)
inserts the selected text as a developer message. Custom hints and model-catalog
messages can change these defaults.

Ultra is also a client selection whose ordinary inference effort is
[resolved through model metadata](https://github.com/openai/codex/blob/a956835d020762cb2b570053af06f643a11c0ecc/codex-rs/protocol/src/openai_models/reasoning_effort.rs#L9).
The inspected
[Sol 6.1 catalog entry](https://github.com/openai/codex/blob/a956835d020762cb2b570053af06f643a11c0ecc/codex-rs/models-manager/models.json#L178)
sets that effort to xhigh. This does not define every client's effort surface,
prove a larger inference budget, or make Ultra a max-equivalent benchmark run.
Consumers such as Relay retain their own explicit model/effort contracts.

## What changes in our recommendation

The provider's [subagent documentation](https://learn.chatgpt.com/docs/agent-configuration/subagents?surface=app)
describes delegation requested through project instructions. Its
[multi-agent guidance](https://developers.openai.com/api/docs/guides/responses-multi-agent)
also describes developer instructions that encourage useful parallel work.
The shared policy applies that principle through explicit consumer adoption:
identify useful independent branches, strongly prefer concurrent assignments
and reconsider the available work at meaningful transitions.

This is a project recommendation, not a copy of the full runtime prompt or a
replacement for higher-priority instructions. It deliberately retains zero
helpers for trivial, sequential or otherwise unsuitable work. Reuse preserves
useful context; it does not cap parallelism for other independent questions.
Child model/effort choices still depend on each assignment.

Neither session duration nor spawn count measures useful delegation. One helper
can complete several follow-ups; long tests or deployments can dominate elapsed
time without offering useful parallel work. Assess bounded results, integrated
findings and overlapping independent work. No controlled comparison here proves
that the revised policy improves runtime behavior or consumption.

## Optional client-level configuration

The inspected source exposes `multi_agent_mode_hint_text` under
`[features.multi_agent_v2]` as a
[configuration field](https://github.com/openai/codex/blob/a956835d020762cb2b570053af06f643a11c0ecc/codex-rs/features/src/feature_configs.rs#L259).
It replaces the mode text; it is not a `proactive = true` setting. The
[mode-override test](https://github.com/openai/codex/blob/a956835d020762cb2b570053af06f643a11c0ecc/codex-rs/core/tests/suite/multi_agent_mode.rs#L167)
checks that a custom hint takes precedence over the built-in effort-dependent
texts. These source tests were inspected, not executed as part of this note.

A consumer may assess this option separately when instruction adoption is
insufficient. Verify support, active configuration, delegation permissions and
effect in the actual client before changing it. A text replacement must preserve
user intent and task limits. The shared policy does not require this override,
silently install it or change a running task's configuration.

See the [adoption guide](adoption.md) for integration choices and checks
in a fresh session. This note is setup evidence, not an additional runtime
dependency of a copied `SUBAGENTS.md`.
