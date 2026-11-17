import { normalizeCodexSemanticResult, isBoundedCodexRuntimeIdentifier } from './codex-result-schema.mjs';
import { boundedDiagnosticText, captureCausalDiagnostic } from '../../controller/src/diagnostics.mjs';
import { WriterBlockedError } from './contracts.mjs';
import { normalizeCodexUsage, usageFromCodexJsonLines } from '../../controller/src/codex-usage.mjs';

// Bound individual records and retained state, not the lifetime event stream.
// A lengthy valid tool log must not hide a later small semantic result.
export const MAX_CODEX_JSONL_RECORD_BYTES = 16 * 1024 * 1024;
export function createCodexJsonlParser(evidence = {}, secrets = {}) {
  let buffer = Buffer.alloc(4096), bytes = 0, count = 0, invalid, invalidCause, invalidObservation;
  const append = fragment => {
    const required = bytes + fragment.length;
    if (required > buffer.length) {
      const grown = Buffer.alloc(Math.min(MAX_CODEX_JSONL_RECORD_BYTES, Math.max(required, buffer.length * 2)));
      buffer.copy(grown, 0, 0, bytes); buffer = grown;
    }
    fragment.copy(buffer, bytes); bytes = required;
  };
  let threadId, sessionId, semanticResult, semanticInvalid = false, semanticCause;
  let nativeAgentMessageCount = 0, nativeAgentMessageBytes = 0;
  const eventTypes = new Set(), usageEvents = [], usageCounts = new Map();
  const errorEvents = [];
  let omittedErrors = 0;
  const identifier = (event, names) => names.map(name => event[name]).find(value =>
    typeof value === 'string' && isBoundedCodexRuntimeIdentifier(value.trim()) &&
    !/^(?:unknown|pending|not[-_ ]?available)$/i.test(value.trim()))?.trim();
  const consume = record => {
    if (invalid || record.length === 0) return;
    let event;
    try { event = JSON.parse(record); } catch (error) { invalid = 'CODEX_JSON_INVALID'; invalidCause = error; return; }
    if (!event || typeof event !== 'object' || Array.isArray(event)) { invalid = 'CODEX_JSON_INVALID'; invalidObservation = { expected: 'JSON object event', observed: event === null ? 'null' : Array.isArray(event) ? 'array' : typeof event }; return; }
    count += 1;
    if (typeof event.type === 'string' && eventTypes.size < 64) eventTypes.add(event.type.slice(0, 256));
    threadId = identifier(event, ['threadId', 'thread_id']) ?? threadId;
    sessionId = identifier(event, ['sessionId', 'session_id']) ?? sessionId;
    if (['thread.started', 'turn.started', 'turn.completed', 'turn.failed', 'error'].includes(event.type)) {
      const n = usageCounts.get(event.type) ?? 0;
      usageCounts.set(event.type, n + 1);
      if (n < 2) usageEvents.push(event.type === 'turn.completed' ? { type: event.type, usage: event.usage && typeof event.usage === 'object' && !Array.isArray(event.usage) ? normalizeCodexUsage({ ...event.usage, source: 'codex-exec-turn-completed', scope: 'native-session-total' }) : undefined } : { type: event.type });
    }
    const message = event.type === 'error' ? event.message : event.type === 'turn.failed' ? event.error?.message : undefined;
    if (['error', 'turn.failed'].includes(event.type)) {
      // Redact before clipping so an incomplete retained key/token cannot
      // become visible merely because its closing delimiter was truncated.
      const native = Object.fromEntries(['code', 'status', 'statusCode', 'error', 'reason', 'details'].filter(key => event[key] !== undefined).map(key => [key, event[key]]));
      errorEvents.push({ type: event.type,
        ...(typeof message === 'string' ? { message: boundedDiagnosticText(message, 4096, secrets) } : {}),
        ...(Object.keys(native).length ? { native: captureCausalDiagnostic({ native, secrets }, { compact: true }).native } : {}) });
      if (errorEvents.length > 4) { errorEvents.splice(1, 1); omittedErrors += 1; }
    }
    let candidate;
    if (event.type === 'task_result' || event.kind === 'task_result') candidate = event.result ?? event;
    else if (['success', 'blocked'].includes(event.status) && Object.hasOwn(event, 'summary')) candidate = event;
    else if (event.type === 'item.completed' && event.item?.type === 'agent_message' && typeof event.item.text === 'string') {
      nativeAgentMessageCount += 1;
      nativeAgentMessageBytes += Buffer.byteLength(event.item.text, 'utf8');
      const text = event.item.text.trim();
      if (text.startsWith('{') && text.endsWith('}')) {
        try {
          const value = JSON.parse(text);
          if (value && typeof value === 'object' && !Array.isArray(value)) candidate = value.result ?? value;
        } catch { /* Plain prose is not a structured task result. */ }
      }
    }
    if (candidate !== undefined) {
      try { semanticResult = normalizeCodexSemanticResult(candidate); semanticInvalid = false; semanticCause = undefined; }
      catch (error) { semanticResult = undefined; semanticInvalid = true; semanticCause = error; }
    }
  };
  const finishRecord = () => {
    const record = buffer.subarray(0, bytes).toString('utf8').trim();
    bytes = 0; consume(record);
  };
  return {
    push(chunk) {
      if (invalid) return;
      const data = Buffer.isBuffer(chunk) ? chunk : Buffer.from(String(chunk), 'utf8');
      let start = 0;
      while (start < data.length) {
        const newline = data.indexOf(10, start);
        const end = newline < 0 ? data.length : newline;
        const fragment = data.subarray(start, end);
        if (bytes + fragment.length > MAX_CODEX_JSONL_RECORD_BYTES) { invalid = 'CODEX_OUTPUT_TOO_LARGE'; invalidObservation = { limit: MAX_CODEX_JSONL_RECORD_BYTES, observedBytes: bytes + fragment.length }; bytes = 0; buffer = Buffer.alloc(0); return; }
        if (fragment.length) append(fragment);
        if (newline < 0) break;
        finishRecord();
        start = newline + 1;
      }
    },
    diagnostics() { return { events: errorEvents, omittedEvents: omittedErrors }; },
    finish() {
      if (bytes) finishRecord();
      evidence.codexUsage = usageFromCodexJsonLines(usageEvents.map(event => JSON.stringify(event)).join('\n'), { truncated: !!invalid });
      evidence.codexEventCount = count;
      evidence.codexEventTypes = [...eventTypes].sort();
      evidence.codexNativeAgentMessageCount = nativeAgentMessageCount;
      evidence.codexNativeAgentMessageBytes = nativeAgentMessageBytes;
      if (invalid) throw Object.assign(new WriterBlockedError(invalid, invalid === 'CODEX_OUTPUT_TOO_LARGE' ? 'Codex JSONL record exceeded the bounded byte limit' : 'Codex emitted an invalid JSON event'), { cause: invalidCause, observation: invalidObservation });
      if (!count) throw new WriterBlockedError('CODEX_JSON_INVALID', 'Codex must return structured JSON events');
      if (semanticInvalid) throw Object.assign(new WriterBlockedError('CODEX_RESULT_INVALID', 'Codex semantic result does not match the unified result contract'), { cause: semanticCause });
      if (!semanticResult) throw new WriterBlockedError('CODEX_RESULT_MISSING', 'Codex did not emit a structured semantic task result');
      evidence.threadId = threadId ?? 'UNAVAILABLE';
      evidence.sessionId = sessionId ?? threadId ?? 'UNAVAILABLE';
      evidence.sessionIdSource = sessionId ? 'native-session' : threadId ? 'native-thread' : 'unavailable';
      return { ...semanticResult, threadId: evidence.threadId, sessionId: evidence.sessionId };
    }
  };
}
