const SOURCE = 'codex-exec-turn-completed';
const SCOPE = 'native-session-total';
const TOKEN_FIELDS = Object.freeze([
  'input_tokens', 'cached_input_tokens', 'cache_write_input_tokens',
  'output_tokens', 'reasoning_output_tokens'
]);
const tokenCount = value => Number.isSafeInteger(value) && value >= 0 ? value : 'UNAVAILABLE';

// This is native runtime metadata, never part of the worker semantic result.
// Codex 0.160.0 emits a session-total snapshot (including its own zero fallback).
// Keep the native counters separate: cached/reasoning counts are not additions
// to input/output and exec JSONL does not expose a total_tokens counter.
export function normalizeCodexUsage(value) {
  const native = value?.source === SOURCE && value?.scope === SCOPE;
  return {
    source: native ? SOURCE : 'UNAVAILABLE',
    scope: native ? SCOPE : 'UNAVAILABLE',
    ...Object.fromEntries(TOKEN_FIELDS.map(field => [field, native ? tokenCount(value[field]) : 'UNAVAILABLE'])),
    total_tokens: 'UNAVAILABLE'
  };
}

export function usageFromCodexJsonLines(stdout, { truncated = false } = {}) {
  const unavailable = () => normalizeCodexUsage();
  if (truncated) return unavailable();
  let completed;
  let started = 0;
  let threads = 0;
  for (const line of String(stdout ?? '').split(/\r?\n/).filter(line => line.trim())) {
    let event;
    try { event = JSON.parse(line); } catch { return unavailable(); }
    if (!event || typeof event !== 'object' || Array.isArray(event)) return unavailable();
    if (event.type === 'thread.started' && (++threads > 1 || completed)) return unavailable();
    if (event.type === 'turn.started' && (++started > 1 || completed)) return unavailable();
    if (event.type === 'turn.failed' || event.type === 'error') return unavailable();
    if (event.type !== 'turn.completed') continue;
    // One-shot exec has one terminal snapshot. Duplicate/conflicting events
    // cannot establish a per-run figure and must never be summed or selected.
    if (completed) return unavailable();
    completed = event;
  }
  const usage = completed?.usage;
  if (!usage || typeof usage !== 'object' || Array.isArray(usage)) return unavailable();
  return normalizeCodexUsage({ ...usage, source: SOURCE, scope: SCOPE });
}
