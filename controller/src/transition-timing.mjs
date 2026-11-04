import { AsyncLocalStorage } from 'node:async_hooks';
import { performance } from 'node:perf_hooks';

// Only fixed counters and elapsed times leave this scope. No paths, Task IDs,
// credentials, HTTP bodies or command arguments enter operator diagnostics.
const scope = new AsyncLocalStorage();
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
