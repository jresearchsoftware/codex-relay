import { CONSUMER } from '../../consumer/consumer.mjs';
import { readFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { createBoundedUtf8Capture } from "./utf8-capture.mjs";

export const DIAGNOSTICS_CONFIG_PATH = CONSUMER.paths.diagnosticsConfig;
export const DIAGNOSTICS_STORE_PATH = CONSUMER.paths.diagnosticsStore;
export const MAX_NORMAL_DIAGNOSTIC_BYTES = 1024 * 1024;
export const MAX_DEBUG_DIAGNOSTIC_BYTES = 4 * 1024 * 1024;

const SAFE_DIAGNOSTIC_CODE = /^[A-Z0-9_]{1,80}$/;
const SAFE_DIAGNOSTIC_ID = /^[A-Za-z0-9_-]{1,128}$/;
const SAFE_SIGNAL = /^SIG[A-Z0-9]+$/;

export const FAILURE_DIAGNOSTIC_STAGES = Object.freeze([
  "authority",
  "claim",
  "dispatcher",
  "worker",
  "launcher",
  "codex-child",
  "result-parse",
  "writer-publication"
]);
export const FAILURE_DIAGNOSTIC_BOUNDARIES = FAILURE_DIAGNOSTIC_STAGES;

const SAFE_ENV_VALUES = new Set(["PATH", "LANG", "LC_ALL", "TZ", "HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME", "TMP", "TEMP", "GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_TERMINAL_PROMPT", "GCM_INTERACTIVE", "GIT_OPTIONAL_LOCKS", "GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL", "GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_0", "GIT_CONFIG_VALUE_0", "CODEX_TASK_ROOT", "CODEX_SANDBOX_ROOT", "CODEX_ALLOWED_INPUT_ROOT"]);

function replaceExact(text, value, replacement) {
  if (typeof value !== "string" || value.length === 0) return text;
  return text.split(value).join(replacement);
}

export function redactDiagnosticText(value, { codexAccessToken = "", githubToken = "", knownSecrets = [] } = {}) {
  let text = String(value ?? "");
  text = replaceExact(text, codexAccessToken, "[REDACTED_CODEX_ACCESS_TOKEN]");
  text = replaceExact(text, githubToken, "[REDACTED_GITHUB_TOKEN]");
  for (const secret of knownSecrets) text = replaceExact(text, secret, "[REDACTED_SECRET]");
  text = text.replace(/-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?-----END [^-]*PRIVATE KEY-----/gi, "[REDACTED_PRIVATE_KEY]");
  text = text.replace(/\b(authorization\s*:\s*basic)\s+[^\s,;]+/gi, "$1 [REDACTED_BASIC_AUTH]");
  text = text.replace(/\b(?:authorization\s*:\s*bearer|bearer)\s+[^\s,;]+/gi, match => `${match.slice(0, match.toLowerCase().indexOf("bearer") + 6)} [REDACTED_BEARER]`);
  text = text.replace(/\b(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]+/g, "[REDACTED_GITHUB_TOKEN]");
  text = text.replace(/\b(?:password|passwd|secret|token|api[_-]?key|access[_-]?token)\b\s*[:=]\s*[^\s,;]+/gi, match => `${match.split(/[:=]/, 1)[0]}=[REDACTED_SECRET]`);
  return text.replace(/[\u0000-\u001f\u007f-\u009f]/g, " ");
}

export function boundedDiagnosticText(value, maxBytes, secrets = {}) {
  const redacted = redactDiagnosticText(value, secrets);
  const bytes = Buffer.byteLength(redacted, "utf8");
  const prefix = Buffer.from(redacted, "utf8").subarray(0, maxBytes);
  const fatal = new TextDecoder("utf-8", { fatal: true });
  let text;
  try { text = fatal.decode(prefix); }
  catch {
    text = "";
    for (let end = prefix.length - 1; end >= Math.max(0, prefix.length - 3); end -= 1) {
      try { text = fatal.decode(prefix.subarray(0, end)); break; } catch { /* Try the next safe prefix. */ }
    }
    if (text === "") text = new TextDecoder("utf-8").decode(prefix);
  }
  return { text, bytes, truncated: bytes > maxBytes };
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
  const gitExitCode = firstInteger([value.gitExitCode, value.publicationExitCode], { max: 255 });
  if (gitExitCode !== undefined) result.gitExitCode = gitExitCode;
  const signal = safeFailureDiagnosticSignal(value.signal);
  if (signal) result.signal = signal;
  if (["started", "not_started", "unknown"].includes(value.childState)) result.childState = value.childState;
  if (safeFailureDiagnosticCode(value.primaryCause)) result.primaryCause = value.primaryCause;
  if (typeof value.childStarted === "boolean") result.childStarted = value.childStarted;
  if (typeof value.operation === "string" && /^[a-z][a-z0-9-]{0,63}$/.test(value.operation)) result.operation = value.operation;
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
  return Object.keys(result).length > 0 ? result : undefined;
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

function safePath(value) { return typeof value === "string" && value.length <= 1024 ? value : "[UNAVAILABLE]"; }

export function createExecutionDiagnostic({ executionId = randomUUID(), mode, startedAt, endedAt, phase, phases = [], lifecycle = {}, pid, ppid, cwd, executable, argv, env, checkout, filesystem, input, schema, stdout, stderr, launcherDiagnostic, exitCode, signal, classification, secrets = {} }) {
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
    command: { cwd: safePath(cwd), executable: safePath(executable), argv: Array.isArray(argv) ? argv.map(item => safePath(item)) : [] },
    environment: env ?? {},
    checkout: safePath(checkout),
    filesystem: filesystem ?? {},
    input: input ?? {},
    schema: schema ?? {},
    classification: classification ?? null,
    launcherDiagnostic: launcherDiagnostic ?? null,
    stderr: boundedDiagnosticText(stderr, limit, secrets),
  };
  if (mode === "debug") output.stdout = boundedDiagnosticText(stdout, limit, secrets);
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
    const reference = safeDiagnosticStoreReference(result);
    if (reference?.status === "unavailable") {
      return { status: "unavailable", code: "DIAGNOSTICS_STORE_FAILED", ...(reference.storeCode ? { storeCode: reference.storeCode } : reference.code ? { storeCode: reference.code } : {}), executionId, mode: effectiveMode };
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

export async function persistExecutionDiagnostic(diagnostic, { spawnImpl = spawn, storePath = DIAGNOSTICS_STORE_PATH } = {}) {
  const child = spawnImpl("/usr/bin/sudo", ["-n", storePath], { env: { PATH: "/usr/bin:/bin", LANG: "C", LC_ALL: "C" }, stdio: ["pipe", "pipe", "pipe"] });
  const stdoutCapture = createBoundedUtf8Capture(4096);
  const stderrCapture = createBoundedUtf8Capture(4096);
  let stdout = ""; let stderr = "";
  child.stdout?.on("data", chunk => { stdoutCapture.push(chunk); });
  child.stderr?.on("data", chunk => { stderrCapture.push(chunk); });
  child.stdin?.once?.("error", () => {});
  child.stdin?.end(JSON.stringify(diagnostic) + "\n");
  const result = await new Promise((resolve, reject) => {
    child.once("error", error => reject(Object.assign(new Error("Diagnostic store could not be started"), {
      code: "DIAGNOSTICS_STORE_FAILED",
      storeDiagnosticCode: typeof error?.code === "string" && /^[A-Z0-9_]+$/.test(error.code) ? error.code : undefined
    })));
    child.once("close", code => {
      stdout = stdoutCapture.finish().value;
      stderr = stderrCapture.finish().value;
      if (code === 0) resolve({ stdout, stderr });
      else reject(Object.assign(new Error("Diagnostic store rejected the bounded bundle"), {
        code: "DIAGNOSTICS_STORE_FAILED",
        exitCode: code,
        storeDiagnosticCode: diagnosticStoreFailureCode(stderr) ?? diagnosticStoreFailureCode(stdout)
      }));
    });
  });
  return result;
}
