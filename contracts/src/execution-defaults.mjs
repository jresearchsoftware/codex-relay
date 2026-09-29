import { readFileSync } from 'node:fs';

// Machine representation of AGENTS.md's execution policy. Rust uses the same
// schema defaults; admission resolves once and downstream preserves the values.
export const EXECUTION_DEFINITION = JSON.parse(readFileSync(new URL(
  '../../reviewer/src/executable-cr-v2.json', import.meta.url), 'utf8'));
const properties = EXECUTION_DEFINITION.input_schema.properties;
export const EXECUTION_DEFAULTS = Object.freeze({
  effort: properties.codex_effort.default,
  subagentsAllowed: properties.subagents_allowed.default
});

export function resolveExecutionDefaults({ effort, subagentsAllowed } = {}) {
  return {
    effort: effort === undefined ? EXECUTION_DEFAULTS.effort : effort,
    subagentsAllowed: subagentsAllowed === undefined ? EXECUTION_DEFAULTS.subagentsAllowed : subagentsAllowed
  };
}
