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
export const SYSTEM_EXECUTION_DEFAULTS = Object.freeze({ model: 'gpt-6.1-sol',
  effort: EXECUTION_DEFAULTS.effort, subagents: EXECUTION_DEFAULTS.subagentsAllowed });

// Resolve each field once at admission. These are requested values; no layer
// establishes which model or effort actually ran.
export function resolveExecutionProfile({ changeRequest = {}, decisions = {}, project = {}, system = SYSTEM_EXECUTION_DEFAULTS } = {}) {
  const layers = [changeRequest, decisions, project, system];
  const pick = field => layers.find(layer => layer[field] !== undefined)?.[field];
  const subagents = layers.map(layer => layer.subagents === undefined ? layer.subagentsAllowed : layer.subagents)
    .find(value => value !== undefined);
  const resolved = { model: pick('model'), effort: pick('effort'), subagents };
  if (typeof resolved.model !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(resolved.model)
    || typeof resolved.effort !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(resolved.effort)
    || typeof resolved.subagents !== 'boolean') throw Object.assign(new Error('Invalid execution profile'), { code: 'AUTHORITY_PROFILE_INVALID' });
  return resolved;
}

export function resolveExecutionDefaults({ effort, subagentsAllowed } = {}) {
  return {
    effort: effort === undefined ? EXECUTION_DEFAULTS.effort : effort,
    subagentsAllowed: subagentsAllowed === undefined ? EXECUTION_DEFAULTS.subagentsAllowed : subagentsAllowed
  };
}
