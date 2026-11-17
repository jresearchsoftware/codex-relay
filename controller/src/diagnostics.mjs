import { EXECUTION_CONSUMER as CONSUMER } from '../../consumer/consumer.mjs';
import { readFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { createBoundedUtf8Capture } from "./utf8-capture.mjs";
import { redactDiagnosticText, boundedDiagnosticText } from "./diagnostic-redaction.mjs";
export { redactDiagnosticText, boundedDiagnosticText } from "./diagnostic-redaction.mjs";

export const DIAGNOSTICS_CONFIG_PATH = CONSUMER.paths.diagnosticsConfig;
export const DIAGNOSTICS_STORE_PATH = CONSUMER.paths.diagnosticsStore;
export const MAX_NORMAL_DIAGNOSTIC_BYTES = 1024 * 1024;
export const MAX_DEBUG_DIAGNOSTIC_BYTES = 4 * 1024 * 1024;
// Covers the store's existing 30-second retention-lock wait and bounded write.
// A recorder must return control to the independent fallback on a quiet hang.
export const DIAGNOSTIC_STORE_TIMEOUT_MS = 60 * 1000;

const SAFE_DIAGNOSTIC_CODE = /^[A-Z0-9_]{1,80}$/;
const SAFE_DIAGNOSTIC_ID = /^[A-Za-z0-9_-]{1,128}$/;
const SAFE_SIGNAL = /^SIG[A-Z0-9]{1,29}$/;

export const FAILURE_DIAGNOSTIC_STAGES = Object.freeze([
  "authority",
  "claim",
  "dispatcher",
  "worker",
  "launcher",
  "codex-child",
  "result-parse",
  "preflight",
  "sandbox",
  "finalization",
  "cleanup",
  "diagnostic-capture",
  "diagnostic-persistence",
  "execution",
  "progress",
  "readiness",
  "writer-publication"
]);
export const FAILURE_DIAGNOSTIC_BOUNDARIES = FAILURE_DIAGNOSTIC_STAGES;

// An independent output surface is the final evidence-gap notice when neither
// filesystem recorder can prove retention. Only fixed fields leave this path.
export function emitDiagnosticUnavailable({ executionId, originalCode, storeCode, fallbackCode,
  operation, boundary = 'diagnostic-persistence' } = {}, write = text => process.stderr.write(text)) {
  const safeCode = value => typeof value === 'string' && SAFE_DIAGNOSTIC_CODE.test(value) ? value : 'UNCLASSIFIED_FAILURE';
  const result = { status: 'unavailable', code: 'DIAGNOSTICS_STORE_FAILED',
    ...(typeof executionId === 'string' && SAFE_DIAGNOSTIC_ID.test(executionId) ? { executionId } : {}),
    originalCode: safeCode(originalCode), storeCode: safeCode(storeCode), fallbackCode: safeCode(fallbackCode),
    recorderBoundary: FAILURE_DIAGNOSTIC_BOUNDARIES.includes(boundary) ? boundary : 'diagnostic-persistence',
    ...(typeof operation === 'string' && /^[a-z][a-z0-9-]{0,63}$/.test(operation) ? { operation } : {}),
    originalEvidence: 'observed_not_retained' };
  try { write(`RELAY_DIAGNOSTIC_UNAVAILABLE ${JSON.stringify(result)}\n`); } catch { /* output unavailable */ }
  return result;
}

const SAFE_ENV_VALUES = new Set(["PATH", "LANG", "LC_ALL", "TZ", "HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME", "TMP", "TEMP", "GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_TERMINAL_PROMPT", "GCM_INTERACTIVE", "GIT_OPTIONAL_LOCKS", "GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL", "GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_0", "GIT_CONFIG_VALUE_0", "CODEX_TASK_ROOT", "CODEX_SANDBOX_ROOT", "CODEX_ALLOWED_INPUT_ROOT"]);

// Protected causal evidence is deliberately separate from all public reference
// projections below. It records observations, not an inference that stderr (or
// a native error event) caused an exit. The compact form fits the independent
// fallback capsule even when the primary serializer/store fails.
export const MAX_CAUSAL_DIAGNOSTIC_BYTES = 64 * 1024;
export const MAX_COMPACT_CAUSAL_DIAGNOSTIC_BYTES = 8 * 1024;

function privateNativeValue(value, secrets, depth = 0, seen = new Set()) {
  if (value === null || typeof value === 'boolean' || (typeof value === 'number' && Number.isFinite(value))) return value;
  if (typeof value === 'string') return boundedDiagnosticText(value, 8192, secrets);
  if (!value || typeof value !== 'object' || seen.has(value) || depth >= 4) return '[UNAVAILABLE_OR_BOUNDED]';
  seen.add(value);
  if (Array.isArray(value)) return value.slice(0, 8).map(item => privateNativeValue(item, secrets, depth + 1, seen));
  const entries = Object.entries(value).slice(0, 16).map(([key, item]) => [
    boundedDiagnosticText(key, 80, secrets).text,
    /authorization|cookie|password|passwd|secret|token|api[_-]?key|private[_-]?key/i.test(key)
      ? '[REDACTED_SECRET]' : privateNativeValue(item, secrets, depth + 1, seen)
  ]);
  return Object.fromEntries(entries);
}

function exceptionObservation(error, secrets) {
  if (error === undefined || error === null) return undefined;
  const chain = []; const seen = new Set(); let current = error;
  while (current !== undefined && current !== null && !seen.has(current) && chain.length < 16) {
    seen.add(current);
    if (typeof current !== 'object') { chain.push({ message: boundedDiagnosticText(String(current), 8192, secrets).text }); break; }
    const item = {};
    for (const field of ['name', 'code', 'errno', 'syscall', 'path', 'dest', 'status', 'statusCode', 'type', 'requestId', 'exitCode', 'signal', 'message']) {
      if (current[field] !== undefined) item[field] = privateNativeValue(current[field], secrets);
    }
    // HTTP/SDK errors commonly keep their native body under these properties.
    for (const field of ['error', 'response', 'body', 'data', 'native', 'observation', 'causalEvidence', 'stdout', 'stderr']) if (current[field] !== undefined) item[field] = privateNativeValue(current[field], secrets);
    if (current.details?.failureDiagnostic) item.failureDiagnostic = privateNativeValue(current.details.failureDiagnostic, secrets);
    if (current.stack !== undefined) item.stack = privateNativeValue(current.stack, secrets);
    chain.push(item);
    current = current.runtimeCause !== current ? current.runtimeCause ?? current.cause : current.cause;
  }
  // The deepest observed original cause comes first so compact fallback
  // clipping cannot preferentially retain wrapper stacks and hide its cause.
  return JSON.stringify({ causeChainTruncated: (current !== undefined && current !== null) || chain.length > 4,
    chain: chain.reverse().slice(0, 4) });
}

function observedPrivateText(value, limit, secrets) {
  if (value === undefined || value === null) return { available: false, reason: 'not_observed' };
  const prior = typeof value === 'object' ? value : undefined;
  if (prior?.available === false) return { available: false, reason: 'not_observed' };
  const text = typeof prior?.text === 'string' ? prior.text : typeof prior?.value === 'string' ? prior.value : String(value);
  const bounded = boundedDiagnosticText(text, limit, { ...secrets, inputTruncated: prior?.truncated === true });
  return { available: prior?.available !== false, ...bounded,
    bytes: Math.max(bounded.bytes, Number.isSafeInteger(prior?.bytes) ? prior.bytes : Number.isSafeInteger(prior?.total) ? prior.total : 0),
    truncated: bounded.truncated || prior?.truncated === true };
}

export function normalizeCausalDiagnostic(value, { compact = false, secrets = {}, maxBytes } = {}) {
  if (!value || typeof value !== 'object') return undefined;
  const defaultCap = compact ? MAX_COMPACT_CAUSAL_DIAGNOSTIC_BYTES : MAX_CAUSAL_DIAGNOSTIC_BYTES;
  const cap = Number.isInteger(maxBytes) && maxBytes >= 1024 ? Math.min(maxBytes, defaultCap) : defaultCap;
  let scale = 1; let result;
  do {
    const text = (field, limit) => observedPrivateText(value[field], Math.max(32, Math.floor(limit * scale)), secrets);
    result = { schemaVersion: '1.0',
      ...(typeof value.executionId === 'string' && SAFE_DIAGNOSTIC_ID.test(value.executionId) ? { executionId: value.executionId } : {}),
      ...Object.fromEntries(['phase', 'operation'].filter(key => typeof value[key] === 'string' && /^[a-z][a-z0-9-]{0,63}$/.test(value[key])).map(key => [key, value[key]])),
      exception: text('exception', compact ? 2304 : 24 * 1024),
      native: text('native', compact ? 768 : 8 * 1024),
      stdout: text('stdout', compact ? 768 : 8 * 1024),
      stderr: text('stderr', compact ? 1536 : 8 * 1024),
      process: {
        exitCode: Number.isInteger(value.process?.exitCode) ? value.process.exitCode : null,
        signal: SAFE_SIGNAL.test(value.process?.signal ?? '') ? value.process.signal : null,
        observed: value.process?.observed === true
      } };
    scale /= 2;
  } while (Buffer.byteLength(JSON.stringify(result)) > cap);
  return result;
}

export function captureCausalDiagnostic({ error, executionId, phase, operation, stdout, stderr, exitCode, signal, native, secrets = {} } = {}, options = {}) {
  let source = error; const seen = new Set();
  while (source && typeof source === 'object' && !seen.has(source) && seen.size < 16) {
    seen.add(source);
    const stream = field => {
      const value = source[field];
      if (typeof value !== 'string') return value;
      const bytes = source[`${field}Bytes`];
      const knownBytes = Number.isSafeInteger(bytes) && bytes >= 0;
      return { text: value, ...(knownBytes ? { bytes } : {}),
        truncated: source[`${field}Truncated`] === true || (knownBytes ? bytes > Buffer.byteLength(value) : source.truncated === true) };
    };
    stdout ??= stream('stdout'); stderr ??= stream('stderr');
    exitCode ??= source.exitCode ?? (Number.isInteger(source.code) ? source.code : undefined);
    signal ??= source.signal;
    source = source.runtimeCause !== source ? source.runtimeCause ?? source.cause : source.cause;
  }
  return normalizeCausalDiagnostic({ executionId, phase, operation,
    exception: exceptionObservation(error, secrets),
    native: native === undefined ? undefined : JSON.stringify(privateNativeValue(native, secrets)),
    stdout, stderr, process: { exitCode, signal, observed: exitCode !== undefined || signal !== undefined } }, { ...options, secrets });
}

export function diagnosticEnvironmentSnapshot(env = {}) {
  return Object.fromEntries(Object.entries(env)
    .filter(([name]) => SAFE_ENV_VALUES.has(name) || name === "CODEX_ACCESS_TOKEN" || name === "GITHUB_TOKEN")
    .map(([name, value]) => [name, name === "CODEX_ACCESS_TOKEN" ? "[REDACTED_CODEX_ACCESS_TOKEN]" : name === "GITHUB_TOKEN" ? "[REDACTED_GITHUB_TOKEN]" : redactDiagnosticText(value)]));
}

export function safeDiagnosticStoreReference(value) {
  if (!value || typeof value !== "object" || Array.isArray(value) || !["stored", "unavailable"].includes(value.status)) return undefined;
  return {
    status: value.status,
    ...(typeof value.code === "string" && SAFE_DIAGNOSTIC_CODE.test(value.code) ? { code: value.code } : {}),
    ...(typeof value.storeCode === "string" && SAFE_DIAGNOSTIC_CODE.test(value.storeCode) ? { storeCode: value.storeCode } : {}),
    ...(typeof value.executionId === "string" && SAFE_DIAGNOSTIC_ID.test(value.executionId) ? { executionId: value.executionId } : {}),
    ...(value.mode === "normal" || value.mode === "debug" ? { mode: value.mode } : {})
  };
}

export function safeFallbackReference(value) {
  if (!value || typeof value !== "object" || Array.isArray(value) || !["stored", "unavailable", "released"].includes(value.status)) return undefined;
  return {
    status: value.status,
    ...(typeof value.executionId === "string" && SAFE_DIAGNOSTIC_ID.test(value.executionId) ? { executionId: value.executionId } : {}),
    ...(Number.isInteger(value.slot) && value.slot >= 0 && value.slot < 8 ? { slot: value.slot } : {}),
    ...(typeof value.code === "string" && SAFE_DIAGNOSTIC_CODE.test(value.code) ? { code: value.code } : {})
  };
}

// These labels describe governed objects, never worker-selected path text.
const PATH_CONTEXTS = new Set(["sandbox", "checkout", "input", "schema", "diagnostic-store", "fallback-store", "outside-sandbox", "unknown"]);
export function safeRuntimeLifecycle(value = {}) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return {
    ...(["pending", "complete", "failed", "retained", "not_required"].includes(value.cleanup) ? { cleanup: value.cleanup } : {}),
    ...(["pending", "stored", "failed", "not_required"].includes(value.persistence) ? { persistence: value.persistence } : {}),
    ...(["none", "retained", "unknown"].includes(value.retention) ? { retention: value.retention } : {}),
    ...(["reaped", "not_required", "unknown"].includes(value.containment) ? { containment: value.containment } : {}),
    ...(["reaped", "not_required", "unknown"].includes(value.cleanupContainment) ? { cleanupContainment: value.cleanupContainment } : {})
  };
}

function safeFailureDiagnosticCode(value) {
  return typeof value === "string" && SAFE_DIAGNOSTIC_CODE.test(value) ? value : undefined;
}

function safeFailureDiagnosticStage(value) {
  return typeof value === "string" && FAILURE_DIAGNOSTIC_STAGES.includes(value) ? value : undefined;
}

function safeFailureDiagnosticSignal(value) {
  return typeof value === "string" && SAFE_SIGNAL.test(value) ? value : undefined;
}

function firstInteger(values, { min = 0, max = MAX_DEBUG_DIAGNOSTIC_BYTES } = {}) {
  for (const value of values) {
    if (Number.isInteger(value) && value >= min && value <= max) return value;
  }
  return undefined;
}

export function safeFailureDiagnosticReference(value, { fallbackCode, fallbackStage, fallbackBoundary } = {}) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    value = {};
  }
  const result = {};
  const code = safeFailureDiagnosticCode(value.code) ?? safeFailureDiagnosticCode(value.diagnosticCode) ?? safeFailureDiagnosticCode(fallbackCode);
  if (code) result.code = code;
  const classification = safeFailureDiagnosticCode(value.classification);
  if (classification) result.classification = classification;
  const diagnosticCode = safeFailureDiagnosticCode(value.diagnosticCode);
  if (diagnosticCode) result.diagnosticCode = diagnosticCode;
  const stage = safeFailureDiagnosticStage(value.stage) ?? safeFailureDiagnosticStage(fallbackStage);
  if (stage) result.stage = stage;
  const boundary = safeFailureDiagnosticStage(value.boundary) ?? safeFailureDiagnosticStage(fallbackBoundary);
  if (boundary) result.boundary = boundary;
  if (typeof value.workerStarted === "boolean") result.workerStarted = value.workerStarted;
  const bytes = firstInteger([value.bytes, value.diagnosticBytes], { max: Number.MAX_SAFE_INTEGER });
  if (bytes !== undefined) result.bytes = bytes;
  const truncated = typeof value.truncated === "boolean" ? value.truncated : typeof value.diagnosticTruncated === "boolean" ? value.diagnosticTruncated : undefined;
  if (truncated !== undefined) result.truncated = truncated;
  const childExitCode = firstInteger([value.childExitCode], { max: 255 });
  if (childExitCode !== undefined) result.childExitCode = childExitCode;
  const dispatcherExitCode = firstInteger([value.dispatcherExitCode], { max: 255 });
  if (dispatcherExitCode !== undefined) result.dispatcherExitCode = dispatcherExitCode;
  const dispatcherSignal = safeFailureDiagnosticSignal(value.dispatcherSignal);
  if (dispatcherSignal) result.dispatcherSignal = dispatcherSignal;
  const gitExitCode = firstInteger([value.gitExitCode, value.publicationExitCode], { max: 255 });
  if (gitExitCode !== undefined) result.gitExitCode = gitExitCode;
  const signal = safeFailureDiagnosticSignal(value.signal);
  if (signal) result.signal = signal;
  if (["started", "not_started", "unknown"].includes(value.childState)) result.childState = value.childState;
  if (safeFailureDiagnosticCode(value.primaryCause)) result.primaryCause = value.primaryCause;
  if (typeof value.childStarted === "boolean") result.childStarted = value.childStarted;
  if (typeof value.operation === "string" && /^[a-z][a-z0-9-]{0,63}$/.test(value.operation)) result.operation = value.operation;
  if (typeof value.syscall === "string" && /^[a-z][a-z0-9_]{0,39}$/.test(value.syscall)) result.syscall = value.syscall;
  if (PATH_CONTEXTS.has(value.pathContext)) result.pathContext = value.pathContext;
  Object.assign(result, safeRuntimeLifecycle(value));
  if (typeof value.preview === "string") {
    const preview = boundedDiagnosticText(value.preview, 2048);
    if (preview.text) result.preview = preview.text;
    result.bytes = Math.max(bytes ?? 0, preview.bytes);
    result.truncated = truncated === true || preview.truncated;
  }
  const priorCause = safeFailureDiagnosticCode(value.priorCause);
  if (priorCause) result.priorCause = priorCause;
  const executionId = typeof value.executionId === "string"
    ? value.executionId
    : typeof value.diagnosticStore?.executionId === "string" ? value.diagnosticStore.executionId : undefined;
  if (executionId && SAFE_DIAGNOSTIC_ID.test(executionId)) result.executionId = executionId;
  const diagnosticStore = safeDiagnosticStoreReference(value.diagnosticStore);
  if (diagnosticStore) result.diagnosticStore = diagnosticStore;
  const fallbackReference = safeFallbackReference(value.fallbackReference);
  if (fallbackReference) result.fallbackReference = fallbackReference;
  return Object.keys(result).length > 0 ? result : undefined;
}

// A public projection of existing launcher evidence, never a stream preview.
// Keep it distinct from the outer terminal classification and process status.
export function safeLauncherDiagnosticSummary(value) {
  const safe = safeFailureDiagnosticReference({ diagnosticCode: value?.diagnosticCode, bytes: value?.bytes, truncated: value?.truncated });
  if (!safe?.diagnosticCode) return undefined;
  return {
    ...(safe.diagnosticCode ? { diagnosticCode: safe.diagnosticCode } : {}),
    ...(safe.bytes !== undefined ? { bytes: safe.bytes } : {}),
    ...(safe.truncated !== undefined ? { truncated: safe.truncated } : {})
  };
}

export function failureDiagnosticFromDetails(details, options = {}) {
  const source = details && typeof details === "object" && !Array.isArray(details) ? details : {};
  const nested = source.failureDiagnostic && typeof source.failureDiagnostic === "object" && !Array.isArray(source.failureDiagnostic)
    ? source.failureDiagnostic
    : {};
  const merged = { ...nested };
  const aliases = [
    ["code", "code"],
    ["diagnosticCode", "diagnosticCode"],
    ["diagnosticBytes", "bytes"],
    ["diagnosticTruncated", "truncated"],
    ["childExitCode", "childExitCode"],
    ["dispatcherExitCode", "dispatcherExitCode"],
    ["dispatcherSignal", "dispatcherSignal"],
    ["gitExitCode", "gitExitCode"],
    ["publicationExitCode", "gitExitCode"],
    ["signal", "signal"],
    ["childStarted", "childStarted"],
    ["childState", "childState"],
    ["primaryCause", "primaryCause"],
    ["executionId", "executionId"],
    ["diagnosticStore", "diagnosticStore"],
    ["stage", "stage"],
    ["boundary", "boundary"],
    ["classification", "classification"],
    ["operation", "operation"],
    ["syscall", "syscall"],
    ["pathContext", "pathContext"],
    ["cleanup", "cleanup"],
    ["persistence", "persistence"],
    ["retention", "retention"],
    ["containment", "containment"],
    ["cleanupContainment", "cleanupContainment"],
    ["fallbackReference", "fallbackReference"],
    ["preview", "preview"],
    ["priorCause", "priorCause"]
  ];
  for (const [sourceField, targetField] of aliases) {
    if (merged[targetField] === undefined && source[sourceField] !== undefined) merged[targetField] = source[sourceField];
  }
  const fallbackCode = safeFailureDiagnosticCode(options.fallbackCode);
  const diagnosticCode = safeFailureDiagnosticCode(merged.diagnosticCode);
  const nestedCode = safeFailureDiagnosticCode(merged.code);
  if (fallbackCode) {
    if (merged.classification === undefined) {
      const classification = diagnosticCode ?? (nestedCode !== fallbackCode ? nestedCode : undefined);
      if (classification) merged.classification = classification;
    }
    merged.code = fallbackCode;
  } else if (merged.code === undefined) {
    merged.code = diagnosticCode;
  }
  if (merged.executionId === undefined && merged.diagnosticStore?.executionId !== undefined) merged.executionId = merged.diagnosticStore.executionId;
  if (merged.workerStarted === undefined && options.fallbackStage === "worker") merged.workerStarted = true;
  return safeFailureDiagnosticReference(merged, options);
}

export async function readDiagnosticsConfig({ readFileImpl = readFile } = {}) {
  try {
    const value = JSON.parse(await readFileImpl(DIAGNOSTICS_CONFIG_PATH, "utf8"));
    if (!value || value.schemaVersion !== "1.0" || !["normal", "debug"].includes(value.mode)) {
      const error = new Error("Diagnostics configuration is outside the two-mode contract"); error.code = "DIAGNOSTICS_CONFIG_INVALID"; throw error;
    }
    return { mode: value.mode };
  } catch (error) {
    if (error?.code === "ENOENT") return { mode: "normal" };
    throw error;
  }
}

function safePath(value, secrets) { return typeof value === "string" ? boundedDiagnosticText(value, 1024, secrets).text : "[UNAVAILABLE]"; }

// Native failure details are JSONL stdout, independently of incidental stderr.
// Retain only observed top-level error messages, never agent/tool output. This
// is protected diagnostic evidence, not a replacement for the child exit code.
function codexErrorDiagnostics(stdout, stdoutTruncated, secrets, streamed) {
  if (streamed && Array.isArray(streamed.events)) return { source: 'codex-jsonl', stdoutTruncated: stdoutTruncated === true,
    omittedEvents: streamed.omittedEvents ?? 0, events: (streamed.events.length <= 4 ? streamed.events : [streamed.events[0], ...streamed.events.slice(-3)]).map(event => ({ type: event.type, ...(event.native ? { native: observedPrivateText(event.native, 4096, secrets) } : {}), message: typeof event.message === 'object' && typeof event.message?.text === 'string'
      ? { ...boundedDiagnosticText(event.message.text, 4096, secrets), bytes: event.message.bytes, truncated: event.message.truncated === true }
      : boundedDiagnosticText(event.message, 4096, secrets) })) };
  const events = [];
  let omittedEvents = 0;
  const lines = String(stdout ?? "").split(/\r?\n/);
  // A capture limit can cut a syntactically valid prefix from a larger record.
  if (stdoutTruncated) lines.pop();
  for (const line of lines) {
    let value;
    try { value = JSON.parse(line); } catch { continue; }
    const message = value?.type === 'error' ? value.message
      : value?.type === 'turn.failed' ? value.error?.message : undefined;
    if (typeof message !== 'string') continue;
    events.push({ type: value.type, message: boundedDiagnosticText(message, 4096, secrets) });
    if (events.length > 4) { events.splice(1, 1); omittedEvents += 1; }
  }
  return { source: 'codex-jsonl', stdoutTruncated: stdoutTruncated === true, omittedEvents, events };
}

export function createExecutionDiagnostic({ executionId = randomUUID(), mode, startedAt, endedAt, phase, phases = [], lifecycle = {}, pid, ppid, cwd, executable, argv, env, checkout, filesystem, input, schema, stdout, stdoutTruncated = false, codexErrorEvents, stderr, stderrTruncated = false, launcherDiagnostic, exitCode, signal, classification, runtimeFailure, error, causalEvidence, secrets = {} }) {
  const limit = mode === "debug" ? MAX_DEBUG_DIAGNOSTIC_BYTES : MAX_NORMAL_DIAGNOSTIC_BYTES;
  const output = {
    schemaVersion: "1.0",
    executionId,
    mode,
    startedAt,
    endedAt,
    phase,
    phases,
    lifecycle,
    process: { pid: Number.isInteger(pid) ? pid : null, ppid: Number.isInteger(ppid) ? ppid : null, exitCode: Number.isInteger(exitCode) ? exitCode : null, signal: signal ?? null },
    command: { cwd: safePath(cwd, secrets), executable: safePath(executable, secrets), argv: Array.isArray(argv) ? argv.map(item => safePath(item, secrets)) : [] },
    environment: env ?? {},
    checkout: safePath(checkout, secrets),
    filesystem: filesystem ?? {},
    input: input ?? {},
    schema: schema ?? {},
    classification: classification ?? null,
    launcherDiagnostic: launcherDiagnostic ?? null,
    stderr: { ...boundedDiagnosticText(stderr, limit, { ...secrets, inputTruncated: stderrTruncated }), ...(stderrTruncated ? { truncated: true } : {}) },
    codexErrors: codexErrorDiagnostics(stdout, stdoutTruncated, secrets, codexErrorEvents),
    causalEvidence: normalizeCausalDiagnostic(causalEvidence, { secrets }) ?? captureCausalDiagnostic({
      error: error ?? runtimeFailure, executionId, phase, operation: runtimeFailure?.operation ?? lifecycle.operation,
      stdout: stdout === undefined ? undefined : { text: stdout, truncated: stdoutTruncated }, stderr: stderr === undefined ? undefined : { text: stderr, truncated: stderrTruncated },
      exitCode, signal, native: launcherDiagnostic, secrets }),
  };
  if (runtimeFailure && typeof runtimeFailure === "object") {
    const safe = safeFailureDiagnosticReference(runtimeFailure) ?? {};
    delete safe.preview;
    output.runtimeFailure = { ...safe,
      ...(typeof runtimeFailure.path === "string" ? { path: boundedDiagnosticText(runtimeFailure.path, 1024, secrets).text } : {}),
      ...(typeof runtimeFailure.dest === "string" ? { dest: boundedDiagnosticText(runtimeFailure.dest, 1024, secrets).text } : {}) };
  }
  if (mode === "debug") output.stdout = { ...boundedDiagnosticText(stdout, limit, { ...secrets, inputTruncated: stdoutTruncated }), ...(stdoutTruncated ? { truncated: true } : {}) };
  return output;
}

function safeFailureCode(value, fallback) {
  return typeof value === "string" && SAFE_DIAGNOSTIC_CODE.test(value) ? value : fallback;
}

function safeInputValue(value) {
  return typeof value === "string" && value.length <= 1024 ? value : "[UNAVAILABLE]";
}

export async function persistControllerFailureDiagnostic({ error, failureCode, invocation = {}, mode = "normal", diagnosticStore, executionId = randomUUID(), now = () => new Date().toISOString(), cwd = process.cwd(), executable = process.argv[0], argv = process.argv.slice(1), env = process.env, secrets } = {}) {
  const effectiveMode = mode === "debug" ? "debug" : "normal";
  const code = safeFailureCode(failureCode ?? error?.code, "UNCLASSIFIED_CONTROLLER_FAILURE");
  const startedAt = now();
  const privateText = typeof error?.stack === "string"
    ? error.stack
    : `${error?.name ?? "Error"}: ${String(error?.message ?? error)}`;
  const diagnostic = createExecutionDiagnostic({
    executionId,
    mode: effectiveMode,
    startedAt,
    endedAt: now(),
    phase: "controller-terminal",
    phases: ["controller-start", "controller-terminal"],
    lifecycle: { controllerFailed: true, cleanupComplete: true },
    pid: process.pid,
    ppid: process.ppid,
    cwd,
    executable,
    argv,
    env: diagnosticEnvironmentSnapshot(env),
    checkout: env?.WRITER_SOURCE_REPO,
    filesystem: {},
    input: {
      kind: "controller-failure",
      repository: safeInputValue(invocation?.repository),
      pullRequest: Number.isInteger(invocation?.pullRequest) ? invocation.pullRequest : null,
      reviewId: Number.isInteger(invocation?.reviewId) ? invocation.reviewId : null,
      operation: safeInputValue(invocation?.operation)
    },
    schema: { failureEvidence: "private-bounded" },
    stderr: privateText,
    launcherDiagnostic: { code },
    classification: code,
    error,
    secrets: secrets ?? {
      codexAccessToken: typeof env?.CODEX_ACCESS_TOKEN === "string" ? env.CODEX_ACCESS_TOKEN : "",
      githubToken: typeof env?.GITHUB_TOKEN === "string" ? env.GITHUB_TOKEN : ""
    }
  });
  const store = typeof diagnosticStore === "function"
    ? diagnosticStore
    : async () => { throw Object.assign(new Error("No bounded private diagnostic store is available"), { code: "DIAGNOSTICS_STORE_UNAVAILABLE" }); };
  try {
    const result = await store(diagnostic);
    const reference = safeDiagnosticStoreReference(typeof result?.stdout === 'string' ? JSON.parse(result.stdout) : result);
    if (reference?.status === "unavailable") {
      return { status: "unavailable", code: "DIAGNOSTICS_STORE_FAILED", ...(reference.storeCode ? { storeCode: reference.storeCode } : reference.code ? { storeCode: reference.code } : {}), executionId, mode: effectiveMode };
    }
    if (reference?.status !== 'stored' || reference.executionId !== executionId || reference.mode !== effectiveMode) {
      throw Object.assign(new Error('Controller diagnostic storage is not proven'), { code: 'DIAGNOSTICS_STORE_RECEIPT_INVALID' });
    }
    return { status: "stored", code, executionId, mode: effectiveMode };
  } catch (storeError) {
    const storeCode = safeFailureCode(storeError?.storeDiagnosticCode ?? storeError?.code, "");
    return {
      status: "unavailable",
      code: "DIAGNOSTICS_STORE_FAILED",
      ...(storeCode ? { storeCode } : {}),
      executionId,
      mode: effectiveMode
    };
  }
}

function diagnosticStoreFailureCode(value) {
  const text = String(value ?? "");
  const match = text.match(/"code"\s*:\s*"([A-Z0-9_]+)"/);
  return match?.[1];
}

export async function persistExecutionDiagnostic(diagnostic, { spawnImpl = spawn, storePath = DIAGNOSTICS_STORE_PATH, timeoutMs = DIAGNOSTIC_STORE_TIMEOUT_MS } = {}) {
  if (!Number.isSafeInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > DIAGNOSTIC_STORE_TIMEOUT_MS) throw new Error('Invalid diagnostic store timeout');
  let child;
  try { child = spawnImpl("/usr/bin/sudo", ["-n", storePath], { env: { PATH: "/usr/bin:/bin", LANG: "C", LC_ALL: "C" }, stdio: ["pipe", "pipe", "pipe"] }); }
  catch (error) { throw Object.assign(new Error('Diagnostic store could not be started', { cause: error }), { code: 'DIAGNOSTICS_STORE_FAILED', storeDiagnosticCode: safeFailureCode(error?.code, 'DIAGNOSTICS_STORE_FAILED') }); }
  const stdoutCapture = createBoundedUtf8Capture(4096);
  const stderrCapture = createBoundedUtf8Capture(4096);
  let stdout = ""; let stderr = "";
  child.stdout?.on("data", chunk => { stdoutCapture.push(chunk); });
  child.stderr?.on("data", chunk => { stderrCapture.push(chunk); });
  const result = await new Promise((resolve, reject) => {
    let settled = false;
    const fail = (message, error, code, signal) => {
      if (settled) return;
      settled = true; clearTimeout(timer);
      const out = stdoutCapture.finish(); const err = stderrCapture.finish();
      const failure = Object.assign(new Error(message, error ? { cause: error } : undefined), {
        code: 'DIAGNOSTICS_STORE_FAILED', exitCode: code, signal,
        storeDiagnosticCode: safeFailureCode(error?.code, diagnosticStoreFailureCode(err.value) ?? diagnosticStoreFailureCode(out.value))
      });
      Object.defineProperties(failure, {
        stdout: { value: out, writable: true, configurable: true }, stderr: { value: err, writable: true, configurable: true },
        native: { value: { stdout: out, stderr: err, operation: 'diagnostic-store' }, writable: true, configurable: true }
      });
      reject(failure);
    };
    const timer = setTimeout(() => {
      let killError;
      try { child.kill?.('SIGTERM'); } catch (error) { killError = error; }
      fail('Diagnostic store exceeded its bounded invocation timeout', Object.assign(new Error('DIAGNOSTICS_STORE_TIMEOUT', { cause: killError }), { code: 'DIAGNOSTICS_STORE_TIMEOUT' }));
      child.stdin?.destroy?.(); child.stdout?.destroy?.(); child.stderr?.destroy?.(); child.unref?.();
    }, timeoutMs);
    child.once("error", error => fail('Diagnostic store could not be started', error));
    for (const stream of [child.stdin, child.stdout, child.stderr]) stream?.once('error', error => fail('Diagnostic store stream failed', error));
    child.once("close", (code, signal) => {
      if (settled) return;
      const out = stdoutCapture.finish(); const err = stderrCapture.finish();
      stdout = out.value; stderr = err.value;
      if (out.truncated || err.truncated) return fail('Diagnostic store output exceeded its bounded byte limit', Object.assign(new Error('DIAGNOSTICS_STORE_OUTPUT_TOO_LARGE'), { code: 'DIAGNOSTICS_STORE_OUTPUT_TOO_LARGE' }), code, signal);
      if (code === 0 && !signal) { settled = true; clearTimeout(timer); resolve({ stdout, stderr }); }
      else fail('Diagnostic store rejected the bounded bundle', undefined, code, signal);
    });
    try { child.stdin?.end(JSON.stringify({ ...diagnostic, repository: CONSUMER.repository }) + "\n"); }
    catch (error) { fail('Diagnostic store input could not be serialized or sent', error); }
  });
  return result;
}
