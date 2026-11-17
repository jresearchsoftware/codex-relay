import { AsyncLocalStorage } from 'node:async_hooks';
import { performance } from 'node:perf_hooks';

// Only fixed counters and elapsed times leave this scope. No paths, Task IDs,
// credentials, HTTP bodies or command arguments enter operator diagnostics.
const scope = new AsyncLocalStorage();
const RUNTIME_OPERATIONS = new Set(['admit', 'handoff', 'preflight', 'checkout-prepare', 'governed-runtime',
  'collect-progress', 'publish-progress', 'finish', 'finish-no-change', 'terminal-outcome',
  'complete-handoff', 'complete-execution']);

// Report the actual orchestration operation across quiet waits. These fixed
// fields reveal no model narration, task payload, native output or credentials.
export async function traceRuntimeOperation(operation, action, { write = text => process.stderr.write(text), intervalMs = 30000 } = {}) {
  if (!RUNTIME_OPERATIONS.has(operation)) return action();
  const started = performance.now();
  const report = state => {
    try { write('RELAY_RUNTIME_PROGRESS ' + JSON.stringify({ operation, state,
      elapsedMs: Math.round(performance.now() - started) }) + '\n'); }
    catch { /* An unavailable output surface never repeats an operation. */ }
  };
  report('started');
  const timer = setInterval(() => report('waiting'), intervalMs); timer.unref();
  try { const result = await action(); report('completed'); return result; }
  catch (error) { report('failed'); throw error; }
  finally { clearInterval(timer); }
}

export async function timedTransitionPart(kind, action) {
  const state = scope.getStore();
  if (!state) return action();
  const started = performance.now();
  state[kind + 'Calls']++;
  try { return await action(); }
  finally { state[kind + 'Ms'] += Math.round(performance.now() - started); }
}
export async function traceConsumerTransition(action) {
  const started = performance.now();
  const state = { originalCalls: 0, originalMs: 0, nativeCalls: 0, nativeMs: 0,
    compositeCalls: 0, compositeMs: 0 };
  const report = () => process.stderr.write('RELAY_TRANSITION_TIMING ' + JSON.stringify({
    elapsedMs: Math.round(performance.now() - started), ...state }) + '\n');
  return scope.run(state, async () => {
    const timer = setInterval(report, 5000); timer.unref();
    try { return await action(); }
    finally { clearInterval(timer); report(); }
  });
}
