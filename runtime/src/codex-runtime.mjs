import { CONSUMER } from '../../consumer/consumer.mjs';
import { resolveCodexProfile } from './codex-profile.mjs';
import { PROGRESS_BOUNDED_EXECUTION } from './execution-policy.mjs';
import { access, chmod, lstat, mkdir, readdir, rm, stat, unlink, writeFile } from "node:fs/promises";
import { constants as fsConstants } from "node:fs";
import { isAbsolute, join, relative, resolve, sep } from "node:path";
import { tmpdir } from "node:os";
import { spawn } from "node:child_process";
import { CODEX_RESULT_SCHEMA, isBoundedCodexRuntimeIdentifier, normalizeCodexSemanticResult } from "./codex-result-schema.mjs";
import { WriterBlockedError } from "./contracts.mjs";
import { createExecutionDiagnostic, diagnosticEnvironmentSnapshot, failureDiagnosticFromDetails, MAX_DEBUG_DIAGNOSTIC_BYTES, MAX_NORMAL_DIAGNOSTIC_BYTES, persistExecutionDiagnostic, readDiagnosticsConfig } from "../../controller/src/diagnostics.mjs";
import { createBoundedUtf8Capture } from "../../controller/src/utf8-capture.mjs";

export const CODEX_SUDO_PATH = "/usr/bin/sudo";
export const CODEX_RUNTIME_USER = CONSUMER.runtimeUser;
export const CODEX_LAUNCHER_PATH = CONSUMER.paths.launcher;
export const CODEX_SANDBOX_NAME = ".codex-sandbox";
export const CODEX_INPUT_NAME = "task-input.md";
export const CODEX_SCHEMA_NAME = "codex-result-schema.json";
export const DEFAULT_CODEX_RUNTIME_TIMEOUT_MS = 90 * 60 * 1000;
export const CODEX_TERMINATION_GRACE_MS = 5000;
// Functional JSONL is retained long enough to parse the native stream, while
// stderr remains on the smaller mode-specific diagnostic limit.
export const MAX_CODEX_FUNCTIONAL_STDOUT_BYTES = 16 * 1024 * 1024;
export { MAX_DEBUG_DIAGNOSTIC_BYTES, MAX_NORMAL_DIAGNOSTIC_BYTES };
export { createBoundedUtf8Capture } from "../../controller/src/utf8-capture.mjs";

export const CODEX_WRITER_IDENTITY = CONSUMER.writerIdentity;
export const CODEX_REMEDIATION_IDENTITY = CONSUMER.remediationIdentity;

const RUNTIME_DIRECTORIES = Object.freeze(["home", "config", "cache", "data", "state", "tmp"]);

export function buildCodexProcessSpec({ args, executable = CODEX_LAUNCHER_PATH } = {}) {
  if (executable !== CODEX_LAUNCHER_PATH) {
    throw new Error("Codex execution must use the fixed governed launcher");
  }
  if (!Array.isArray(args)) throw new Error("Codex process arguments are required");
  return {
    command: CODEX_SUDO_PATH,
    args: ["-n", "-u", CODEX_RUNTIME_USER, executable, ...args]
  };
}

function identityValues(identity = CODEX_WRITER_IDENTITY) {
  const value = typeof identity === "string" ? { name: identity, email: undefined } : identity;
  if (!value || typeof value.name !== "string" || value.name.trim() === "" || /[\r\n]/.test(value.name)) {
    throw new WriterBlockedError("GIT_IDENTITY_INVALID", "Codex runtime requires a bounded Git identity");
  }
  if (value.email !== undefined && (typeof value.email !== "string" || value.email.trim() === "" || /[\r\n]/.test(value.email))) {
    throw new WriterBlockedError("GIT_IDENTITY_INVALID", "Codex runtime requires a bounded Git email");
  }
  return { name: value.name, email: value.email ?? `${value.name}@users.noreply.github.com` };
}

export function buildCodexEnvironment(source = process.env, { sandboxRoot = join(tmpdir(), CODEX_SANDBOX_NAME), gitIdentity = CODEX_WRITER_IDENTITY } = {}) {
  const allowed = new Set(["PATH", "SystemRoot", "WINDIR", "ComSpec", "PATHEXT", "LANG", "LC_ALL", "TZ"]);
  const env = Object.fromEntries(Object.entries(source ?? {}).filter(([key]) => allowed.has(key)));
  const root = resolve(sandboxRoot);
  const home = join(root, "home");
  const config = join(root, "config");
  const cache = join(root, "cache");
  const data = join(root, "data");
  const state = join(root, "state");
  const temp = join(root, "tmp");
  env.HOME = home;
  env.USERPROFILE = home;
  env.CODEX_HOME = home;
  env.XDG_CONFIG_HOME = config;
  env.XDG_CACHE_HOME = cache;
  env.XDG_DATA_HOME = data;
  env.XDG_STATE_HOME = state;
  env.TMP = temp;
  env.TEMP = temp;
  env.TMPDIR = temp;
  env.CODEX_TASK_ROOT = process.cwd();
  env.CODEX_SANDBOX_ROOT = root;
  env.CODEX_ALLOWED_INPUT_ROOT = root;
  // Git must not consult system, user, credential-helper, or SSH-agent state.
  env.GIT_CONFIG_NOSYSTEM = "1";
  env.GIT_CONFIG_GLOBAL = process.platform === "win32" ? "NUL" : "/dev/null";
  env.GIT_CONFIG_SYSTEM = process.platform === "win32" ? "NUL" : "/dev/null";
  env.GIT_TERMINAL_PROMPT = "0";
  env.GCM_INTERACTIVE = "Never";
  env.GIT_OPTIONAL_LOCKS = "0";
  env.GIT_SSH_COMMAND = "false";
  const identity = identityValues(gitIdentity);
  env.GIT_AUTHOR_NAME = identity.name;
  env.GIT_AUTHOR_EMAIL = identity.email;
  env.GIT_COMMITTER_NAME = identity.name;
  env.GIT_COMMITTER_EMAIL = identity.email;
  return env;
}

export function buildCheckoutCodexEnvironment(source = process.env, { checkoutRoot, gitIdentity = CODEX_WRITER_IDENTITY } = {}) {
  if (typeof checkoutRoot !== "string" || checkoutRoot.trim() === "") {
    throw new WriterBlockedError("CODEX_PATH_PREFLIGHT_INVALID", "Codex checkout root is required");
  }
  const root = resolve(checkoutRoot);
  const sandboxRoot = join(root, CODEX_SANDBOX_NAME);
  const env = buildCodexEnvironment(source, { sandboxRoot, gitIdentity });
  env.CODEX_TASK_ROOT = root;
  env.CODEX_SANDBOX_ROOT = sandboxRoot;
  env.CODEX_ALLOWED_INPUT_ROOT = sandboxRoot;
  env.GIT_CONFIG_COUNT = "1";
  env.GIT_CONFIG_KEY_0 = "safe.directory";
  env.GIT_CONFIG_VALUE_0 = root;
  return env;
}

export async function grantSharedCheckoutAccess(root) {
  if (process.platform === "win32") return;
  const entry = await lstat(root);
  if (entry.isSymbolicLink()) return;
  if (entry.isDirectory()) {
    await chmod(root, (entry.mode & 0o7777) | 0o2770);
    for (const child of await readdir(root)) await grantSharedCheckoutAccess(join(root, child));
    return;
  }
  if (entry.isFile()) {
    const mode = entry.mode & 0o7777;
    await chmod(root, mode | 0o060 | ((mode & 0o100) ? 0o010 : 0));
  }
}

function inside(candidate, root) {
  const value = relative(root, candidate);
  return value !== "" && value !== ".." && !value.startsWith(`..${sep}`) && !isAbsolute(value);
}

async function assertWritableDirectory(directory, label) {
  const probe = join(directory, `.codex-write-probe-${process.pid}-${Date.now()}-${Math.random().toString(16).slice(2)}`);
  try {
    await access(directory, fsConstants.W_OK | fsConstants.X_OK);
    await writeFile(probe, "", { flag: "wx", mode: 0o660 });
  } catch (error) {
    throw new WriterBlockedError("CODEX_PATH_PREFLIGHT_FAILED", `Codex runtime path is not writable: ${label}`);
  } finally {
    await rm(probe, { force: true }).catch(() => undefined);
  }
}

async function assertNoSymlinkComponents(root, normalized) {
  if (normalized === ".") return;
  let current = root;
  for (const segment of normalized.split("/")) {
    current = join(current, segment);
    try {
      const entry = await lstat(current);
      if (entry.isSymbolicLink()) throw new WriterBlockedError("CODEX_PATH_PREFLIGHT_FAILED", `Runtime path contains a symlink: ${normalized}`);
    } catch (error) {
      if (error instanceof WriterBlockedError) throw error;
      if (error.code === "ENOENT" || error.code === "ENOTDIR") return;
      throw error;
    }
  }
}

export async function preflightCodexWorkspace({ cwd, sandboxRoot } = {}) {
  if (typeof cwd !== "string" || cwd.trim() === "") throw new WriterBlockedError("CODEX_PATH_PREFLIGHT_INVALID", "Codex checkout root is required");
  const checkoutRoot = resolve(cwd);
  const rootEntry = await lstat(checkoutRoot).catch(() => { throw new WriterBlockedError("CODEX_PATH_PREFLIGHT_FAILED", "Codex checkout root is unavailable"); });
  if (!rootEntry.isDirectory() || rootEntry.isSymbolicLink()) throw new WriterBlockedError("CODEX_PATH_PREFLIGHT_FAILED", "Codex checkout root must be a real directory");

  const runtimeRoot = resolve(sandboxRoot ?? join(checkoutRoot, CODEX_SANDBOX_NAME));
  if (!inside(runtimeRoot, checkoutRoot)) throw new WriterBlockedError("CODEX_PATH_PREFLIGHT_INVALID", "Codex sandbox must remain inside the checkout");
  await assertNoSymlinkComponents(checkoutRoot, relative(checkoutRoot, runtimeRoot));
  await mkdir(runtimeRoot, { recursive: true, mode: 0o2770 });
  const runtimeEntry = await lstat(runtimeRoot);
  if (runtimeEntry.isSymbolicLink() || !runtimeEntry.isDirectory()) throw new WriterBlockedError("CODEX_PATH_PREFLIGHT_FAILED", "Codex sandbox must be a real directory");
  for (const name of RUNTIME_DIRECTORIES) {
    const directory = join(runtimeRoot, name);
    await mkdir(directory, { recursive: true, mode: 0o2770 });
    const entry = await lstat(directory);
    if (entry.isSymbolicLink() || !entry.isDirectory()) throw new WriterBlockedError("CODEX_PATH_PREFLIGHT_FAILED", `Codex runtime directory is not a real directory: ${name}`);
  }
  await grantSharedCheckoutAccess(runtimeRoot);
  await assertWritableDirectory(runtimeRoot, CODEX_SANDBOX_NAME);
  for (const name of RUNTIME_DIRECTORIES) await assertWritableDirectory(join(runtimeRoot, name), `${CODEX_SANDBOX_NAME}/${name}`);

  await assertWritableDirectory(checkoutRoot, "repository checkout");
  return { checkoutRoot, sandboxRoot: runtimeRoot, directories: RUNTIME_DIRECTORIES.map(name => join(runtimeRoot, name)) };
}

export function parseLauncherDiagnostic(stderr, { truncated = false } = {}) {
  const lines = String(stderr ?? "").split(/\r?\n/).filter(Boolean);
  for (const line of lines.reverse()) {
    try {
      const value = JSON.parse(line);
      if (value?.source !== "relay-codex-launcher" || value?.schemaVersion !== 1) continue;
      if (typeof value.code !== "string" || !/^[A-Z0-9_]+$/.test(value.code)) continue;
      if (!Number.isInteger(value.bytes) || value.bytes < 0 || value.bytes > 1024 * 1024) continue;
      if (typeof value.preview !== "string" || Buffer.byteLength(value.preview, "utf8") > 1024) continue;
      if (/[\u0000-\u001f\u007f-\u009f]/.test(value.preview)) continue;
      const debug = value.debug && typeof value.debug === "object" && typeof value.debug.stderr === "string" && Buffer.byteLength(value.debug.stderr, "utf8") <= MAX_DEBUG_DIAGNOSTIC_BYTES
        ? { pid: Number.isInteger(value.debug.pid) ? value.debug.pid : null, ppid: Number.isInteger(value.debug.ppid) ? value.debug.ppid : null, stderr: value.debug.stderr }
        : undefined;
      return {
        code: value.code,
        bytes: value.bytes,
        truncated: value.truncated === true || truncated,
        preview: value.preview,
        childState: value.childState ?? (typeof value.childStarted === "boolean" ? (value.childStarted ? "started" : "not_started") : "unknown"),
        childStarted: typeof value.childStarted === "boolean" ? value.childStarted : null,
        // These describe the inner Codex child; process.exitCode/signal in the
        // persisted bundle describe the outer governed launcher process.
        childExitCode: Number.isInteger(value.childExitCode) && value.childExitCode >= 0 && value.childExitCode <= 255 ? value.childExitCode : null,
        signal: typeof value.signal === "string" && /^SIG[A-Z0-9]{1,29}$/.test(value.signal) ? value.signal : null,
        primaryCause: value.primaryCause ?? null,
        ...(debug ? { debug } : {})
      };
    } catch { /* Ignore non-diagnostic child output. */ }
  }
  return { code: "UNCLASSIFIED_CHILD_FAILURE", bytes: Buffer.byteLength(String(stderr ?? ""), "utf8"), truncated, preview: "", childStarted: null, childState: "unknown", childExitCode: null, signal: null, primaryCause: null };
}

function nativeIdentifier(event, names) {
  for (const name of names) {
    if (typeof event?.[name] !== "string") continue;
    const value = event[name].trim();
    if (value !== "" && value !== "UNAVAILABLE" && !/^(?:unknown|pending|not[-_ ]?available)$/i.test(value) && isBoundedCodexRuntimeIdentifier(value)) return value;
  }
  return undefined;
}

export function parseCodexJsonLines(stdout, evidence = {}) {
  const lines = String(stdout ?? "").split(/\r?\n/).map(line => line.trim()).filter(Boolean);
  if (lines.length === 0) throw new WriterBlockedError("CODEX_JSON_INVALID", "Codex must return structured JSON events");
  let threadId;
  let sessionId;
  let semanticResult;
  const eventTypes = new Set();
  let nativeAgentMessageCount = 0;
  let nativeAgentMessageBytes = 0;
  for (const line of lines) {
    let event;
    try { event = JSON.parse(line); } catch { throw new WriterBlockedError("CODEX_JSON_INVALID", "Codex emitted a non-JSON event"); }
    if (!event || typeof event !== "object" || Array.isArray(event)) throw new WriterBlockedError("CODEX_JSON_INVALID", "Codex emitted a non-object JSON event");
    if (typeof event.type === "string") eventTypes.add(event.type);
    threadId = nativeIdentifier(event, ["threadId", "thread_id"]) ?? threadId;
    sessionId = nativeIdentifier(event, ["sessionId", "session_id"]) ?? sessionId;
    if (event.type === "task_result" || event.kind === "task_result") semanticResult = event.result ?? event;
    else if (event.status === "success" && Object.hasOwn(event, "summary")) semanticResult = event;
    else if (event.type === "item.completed" && event.item?.type === "agent_message" && typeof event.item.text === "string") {
      nativeAgentMessageCount += 1;
      nativeAgentMessageBytes += Buffer.byteLength(event.item.text, "utf8");
      const text = event.item.text.trim();
      if (text.startsWith("{") && text.endsWith("}")) {
        try {
          const parsed = JSON.parse(text);
          if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) semanticResult = parsed.result ?? parsed;
        } catch { /* Plain agent prose is not a task result. */ }
      }
    }
  }
  evidence.codexEventCount = lines.length;
  evidence.codexEventTypes = [...eventTypes].sort();
  evidence.codexNativeAgentMessageCount = nativeAgentMessageCount;
  evidence.codexNativeAgentMessageBytes = nativeAgentMessageBytes;
  if (!semanticResult || typeof semanticResult !== "object") throw new WriterBlockedError("CODEX_RESULT_MISSING", "Codex did not emit a structured semantic task result");
  let normalized;
  try { normalized = normalizeCodexSemanticResult(semanticResult); }
  catch { throw new WriterBlockedError("CODEX_RESULT_INVALID", "Codex semantic result does not match the unified result contract"); }
  const nativeThreadId = threadId ?? "UNAVAILABLE";
  // Codex CLI's native JSONL currently exposes the execution identifier as
  // thread_id and may omit a separate session_id. A native thread identifier
  // is the CR's allowed session/thread evidence; it is not model-generated
  // prose and must not be downgraded to UNAVAILABLE.
  const nativeSessionId = sessionId ?? threadId ?? "UNAVAILABLE";
  evidence.threadId = nativeThreadId;
  evidence.sessionId = nativeSessionId;
  evidence.sessionIdSource = sessionId ? "native-session" : threadId ? "native-thread" : "unavailable";
  return { ...normalized, threadId: nativeThreadId, sessionId: nativeSessionId };
}

export function terminateCodexChild(child) {
  return new Promise(resolve => {
    if (!child || typeof child.kill !== "function" || typeof child.once !== "function") {
      resolve(false);
      return;
    }
    let timer;
    let settled = false;
    const finish = terminated => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      child.removeListener?.("close", onClose);
      resolve(terminated);
    };
    const onClose = () => finish(true);
    child.once("close", onClose);
    const force = () => {
      if (settled) return;
      clearTimeout(timer);
      try { child.kill("SIGKILL"); } catch { /* The outer process-group owner still owns final containment. */ }
      timer = setTimeout(() => finish(false), CODEX_TERMINATION_GRACE_MS);
    };
    timer = setTimeout(force, CODEX_TERMINATION_GRACE_MS);
    try {
      if (child.kill("SIGTERM") === false) force();
    } catch {
      force();
    }
  });
}

function filesystemSnapshot(paths) {
  return Promise.all(paths.map(async ([name, path]) => {
    try {
      const value = await stat(path);
      return [name, { exists: true, type: value.isDirectory() ? "directory" : value.isFile() ? "file" : "other", bytes: value.size, mode: (value.mode & 0o7777).toString(8), uid: value.uid, gid: value.gid }];
    } catch {
      return [name, { exists: false }];
    }
  })).then(entries => Object.fromEntries(entries));
}

function timeoutFrom(source) {
  const configured = Number(source?.CODEX_RUNTIME_TIMEOUT_MS ?? DEFAULT_CODEX_RUNTIME_TIMEOUT_MS);
  return Number.isInteger(configured) && configured >= 1000 && configured <= 2 * 60 * 60 * 1000 ? configured : DEFAULT_CODEX_RUNTIME_TIMEOUT_MS;
}

function addDiagnosticDetails(error, diagnostic, store, childExitCode, signal, childStarted) {
  if (!(error instanceof WriterBlockedError)) return;
  const details = error.details && typeof error.details === "object" ? error.details : {};
  const childActuallyStarted = diagnostic ? diagnostic.childStarted === true : childStarted === true;
  const resultParseFailure = ["CODEX_JSON_INVALID", "CODEX_RESULT_MISSING", "CODEX_RESULT_INVALID"].includes(error.code);
  const enriched = {
    ...details,
    ...(diagnostic ? { diagnosticCode: diagnostic.code, diagnosticBytes: diagnostic.bytes, diagnosticTruncated: diagnostic.truncated } : {}),
    ...(Number.isInteger(childExitCode) ? { childExitCode } : {}),
    ...(typeof signal === "string" ? { signal } : {}),
    ...(diagnostic || typeof childStarted === "boolean" ? { childStarted: diagnostic ? diagnostic.childStarted : childStarted, childState: diagnostic?.childState ?? (typeof childStarted === "boolean" ? (childStarted ? "started" : "not_started") : "unknown"), primaryCause: diagnostic?.primaryCause ?? details.primaryCause ?? null } : {}),
    ...(store ? { diagnosticStore: store } : {})
  };
  const failureDiagnostic = failureDiagnosticFromDetails(enriched, {
    fallbackCode: error.code,
    fallbackStage: resultParseFailure ? "result-parse" : childActuallyStarted ? "codex-child" : "launcher",
    fallbackBoundary: resultParseFailure ? "result-parse" : childActuallyStarted ? "codex-child" : "launcher"
  });
  error.details = {
    ...enriched,
    ...(failureDiagnostic ? { failureDiagnostic } : {})
  };
}

export async function runGovernedCodexTask({
  operation,
  attemptId,
  profile,
  inputText,
  cwd,
  targetNumber,
  buildArgs,
  executable = CODEX_LAUNCHER_PATH,
  env = process.env,
  gitIdentity = CODEX_WRITER_IDENTITY,
  spawnImpl = spawn,
  appServer,
  taskTitle,
  evidence = {},
  diagnosticStore = persistExecutionDiagnostic,
  resultSchema = CODEX_RESULT_SCHEMA
}) {
  profile = resolveCodexProfile(profile);
  if (typeof inputText !== "string" || inputText.length === 0) throw new WriterBlockedError("CODEX_INPUT_MISSING", "Codex requires the exact admitted task input");
  if (typeof buildArgs !== "function") throw new WriterBlockedError("CODEX_ARGUMENTS_MISSING", "Codex runtime requires a typed argument builder");
  buildCodexProcessSpec({ args: [], executable });

  if (typeof cwd !== "string" || cwd.trim() === "") throw new WriterBlockedError("CODEX_PATH_PREFLIGHT_INVALID", "Codex checkout root is required");
  const checkoutRoot = resolve(cwd);
  const stagingDir = join(checkoutRoot, CODEX_SANDBOX_NAME);
  const inputPath = join(stagingDir, CODEX_INPUT_NAME);
  const schemaPath = join(stagingDir, CODEX_SCHEMA_NAME);
  const diagnosticsConfig = await readDiagnosticsConfig();
  const diagnosticMode = diagnosticsConfig.mode;
  const executionId = attemptId ?? `codex-${operation ?? "task"}-${Date.now()}-${process.pid}-${targetNumber ?? "unknown"}`;
  const diagnosticStartedAt = new Date().toISOString();
  const diagnosticPhases = ["start"];
  const diagnosticLimit = diagnosticMode === "debug" ? MAX_DEBUG_DIAGNOSTIC_BYTES : MAX_NORMAL_DIAGNOSTIC_BYTES;
  const taskInput = `${inputText}\n\n${PROGRESS_BOUNDED_EXECUTION}\n`;
  const schemaText = `${JSON.stringify(resultSchema)}\n`;
  let child;
  let childEnv;
  let finalProcessSpec;
  let stdout = "";
  let stderr = "";
  let stdoutBytes = 0;
  let stderrBytes = 0;
  let childExitCode = null;
  let childSignal = null;
  let childLaunchError = false;
  let launcherDiagnostic;
  let pendingError;
  let runtimeStarted = false;
  const stdoutCapture = createBoundedUtf8Capture(MAX_CODEX_FUNCTIONAL_STDOUT_BYTES);
  const stderrCapture = createBoundedUtf8Capture(diagnosticLimit);
  let stdoutCapturedBytes = 0;
  let stderrCapturedBytes = 0;
  let stdoutTruncated = false;
  let stderrTruncated = false;
  let streamsFinalized = false;
  const finalizeStreams = () => {
    if (streamsFinalized) return;
    streamsFinalized = true;
    const stdoutResult = stdoutCapture.finish();
    const stderrResult = stderrCapture.finish();
    stdout = stdoutResult.value;
    stderr = stderrResult.value;
    stdoutBytes = stdoutResult.total;
    stderrBytes = stderrResult.total;
    stdoutCapturedBytes = stdoutResult.captured;
    stderrCapturedBytes = stderrResult.captured;
    stdoutTruncated = stdoutResult.truncated;
    stderrTruncated = stderrResult.truncated;
  };

  try {
    await preflightCodexWorkspace({ cwd: checkoutRoot, sandboxRoot: stagingDir });
    diagnosticPhases.push("sandbox-created", "path-preflight-passed");
    await writeFile(inputPath, taskInput, { mode: 0o660 });
    await writeFile(schemaPath, schemaText, { mode: 0o660 });
    if (process.platform !== "win32") {
      await chmod(inputPath, 0o660);
      await chmod(schemaPath, 0o660);
    }
    diagnosticPhases.push("input-schema-written");
    childEnv = buildCodexEnvironment(env, { sandboxRoot: stagingDir, gitIdentity });
    childEnv.CODEX_TASK_ROOT = checkoutRoot;
    childEnv.CODEX_SANDBOX_ROOT = stagingDir;
    childEnv.CODEX_ALLOWED_INPUT_ROOT = stagingDir;
    childEnv.GIT_CONFIG_COUNT = "1";
    childEnv.GIT_CONFIG_KEY_0 = "safe.directory";
    childEnv.GIT_CONFIG_VALUE_0 = checkoutRoot;
    const args = buildArgs({ inputPath, schemaPath, cwd: checkoutRoot, profile, operation, targetNumber });
    if (!Array.isArray(args) || args.some(value => typeof value !== "string")) throw new WriterBlockedError("CODEX_ARGUMENTS_INVALID", "Codex argument builder returned an invalid command shape");
    finalProcessSpec = buildCodexProcessSpec({ args, executable });
    evidence.codexCommand = [finalProcessSpec.command, ...finalProcessSpec.args.map(value => value === inputPath ? "[INPUT_PATH]" : value === schemaPath ? "[OUTPUT_SCHEMA]" : value)];
    runtimeStarted = true;
    // The on-demand dispatcher owns the outer process group. Both automatic
    // entry paths use this same bounded child lifecycle and termination path.
    try {
      child = spawnImpl(finalProcessSpec.command, finalProcessSpec.args, { cwd: checkoutRoot, env: childEnv, stdio: ["ignore", "pipe", "pipe"], detached: false, windowsHide: true });
    } catch (error) {
      childLaunchError = true;
      throw new WriterBlockedError("PROCESS_START_FAILED", "Codex launcher could not be started", { childStarted: false, primaryCause: error?.code, cause: error?.code });
    }
    evidence.codexChildStarted = null;
    child.once("spawn", () => {
      evidence.launcherStarted = true;
      diagnosticPhases.push("launcher-started");
    });
    child.stdout.on("data", chunk => stdoutCapture.push(chunk));
    child.stderr.on("data", chunk => stderrCapture.push(chunk));
    const timeoutMs = timeoutFrom(env);
    const exit = await new Promise((resolveExit, rejectExit) => {
      let settled = false;
      const timer = setTimeout(async () => {
        if (settled) return;
        evidence.codexTimeoutMs = timeoutMs;
        evidence.codexTerminationRequested = true;
        settled = true;
        const terminated = await terminateCodexChild(child);
        evidence.codexTerminationConfirmed = terminated;
        if (!terminated) {
          child.stdout?.destroy?.();
          child.stderr?.destroy?.();
          child.unref?.();
        }
        rejectExit(new WriterBlockedError("CODEX_RUNTIME_TIMEOUT", "Codex execution exceeded the bounded runtime; the owner must reap the governed execution group before terminal routing state is written"));
      }, timeoutMs);
      child.on("error", error => {
        childLaunchError = true;
        if (!child.pid) evidence.codexChildStarted = false;
        if (!settled) { settled = true; clearTimeout(timer); rejectExit(new WriterBlockedError("PROCESS_START_FAILED", "Codex launcher failed before completing", { childStarted: evidence.codexChildStarted, primaryCause: error?.code, cause: error?.code })); }
      });
      child.on("close", (code, signal) => {
        if (!settled) { settled = true; clearTimeout(timer); resolveExit({ code, signal }); }
      });
    });
    finalizeStreams();
    childExitCode = exit.code;
    childSignal = exit.signal;
    diagnosticPhases.push("child-closed");
    evidence.codexExitCode = childExitCode;
    evidence.codexStdoutBytes = stdoutBytes;
    evidence.codexStdoutCapturedBytes = stdoutCapturedBytes;
    evidence.codexStdoutTruncated = stdoutTruncated;
    if (childExitCode !== 0 || childSignal) {
      launcherDiagnostic = parseLauncherDiagnostic(stderr, { truncated: stderrTruncated });
      evidence.codexChildStarted = launcherDiagnostic.childStarted;
      evidence.codexStderrBytes = launcherDiagnostic.bytes;
      evidence.codexStderrCapturedBytes = stderrCapturedBytes;
      evidence.codexStderrTruncated = launcherDiagnostic.truncated || stderrTruncated;
      evidence.codexFailureClass = launcherDiagnostic.code;
      evidence.codexDiagnosticPreview = launcherDiagnostic.preview;
      evidence.codexDiagnosticTruncated = launcherDiagnostic.truncated;
      if (launcherDiagnostic.code === "CODEX_LAUNCHER_OUTPUT_TOO_LARGE" || stdoutTruncated) {
        throw new WriterBlockedError("CODEX_OUTPUT_TOO_LARGE", "Codex functional stdout exceeded the bounded byte limit", { outputBytes: stdoutBytes, outputCapturedBytes: stdoutCapturedBytes, outputLimit: MAX_CODEX_FUNCTIONAL_STDOUT_BYTES });
      }
      throw new WriterBlockedError("CODEX_NONZERO_EXIT", "Codex execution did not complete successfully", { childExitCode, diagnosticCode: launcherDiagnostic.code, diagnosticBytes: launcherDiagnostic.bytes, diagnosticTruncated: launcherDiagnostic.truncated, childStarted: evidence.codexChildStarted });
    }
    evidence.codexStderrBytes = stderrBytes;
    evidence.codexStderrCapturedBytes = stderrCapturedBytes;
    evidence.codexStderrTruncated = stderrTruncated;
    if (stdoutTruncated) {
      throw new WriterBlockedError("CODEX_OUTPUT_TOO_LARGE", "Codex functional stdout exceeded the bounded byte limit", { outputBytes: stdoutBytes, outputCapturedBytes: stdoutCapturedBytes, outputLimit: MAX_CODEX_FUNCTIONAL_STDOUT_BYTES });
    }
    launcherDiagnostic = parseLauncherDiagnostic(stderr, { truncated: stderrTruncated });
    evidence.codexChildStarted = launcherDiagnostic.childStarted;
    const result = parseCodexJsonLines(stdout, evidence);
    evidence.codexChildStarted = true;
    if (appServer?.setThreadName && result.threadId !== "UNAVAILABLE") {
      try { await appServer.setThreadName(result.threadId, taskTitle); }
      catch { evidence.threadNameWarning = true; }
    }
    return result;
  } catch (error) {
    pendingError = error;
    throw error;
  } finally {
    finalizeStreams();
    const filesystem = await filesystemSnapshot([["checkout", checkoutRoot], ["git", join(checkoutRoot, ".git")], ["sandbox", stagingDir], ["input", inputPath], ["schema", schemaPath]]);
    const shouldPersist = runtimeStarted && (diagnosticMode === "debug" || childLaunchError || childExitCode !== 0 || childSignal !== null || typeof pendingError?.code === "string");
    diagnosticPhases.push("cleanup-start");
    await rm(stagingDir, { recursive: true, force: true });
    diagnosticPhases.push("cleanup-complete");
    if (shouldPersist) {
      if (!launcherDiagnostic && !childLaunchError && (diagnosticMode === "debug" || childExitCode !== 0 || childSignal !== null)) {
        launcherDiagnostic = parseLauncherDiagnostic(stderr, { truncated: stderrTruncated });
        evidence.codexChildStarted = launcherDiagnostic.childStarted;
      }
      const diagnostic = createExecutionDiagnostic({
        executionId,
        mode: diagnosticMode,
        startedAt: diagnosticStartedAt,
        endedAt: new Date().toISOString(),
        phase: diagnosticPhases.at(-1),
        phases: diagnosticPhases,
        lifecycle: { sandboxCreated: true, inputSchemaCreated: true, childStarted: evidence.codexChildStarted, childClosed: childExitCode !== null || childSignal !== null, cleanupComplete: true, cleanupRequiredByOwner: childExitCode === null && childSignal === null },
        pid: child?.pid,
        ppid: process.ppid,
        cwd: checkoutRoot,
        executable: finalProcessSpec?.command ?? CODEX_LAUNCHER_PATH,
        argv: finalProcessSpec?.args ?? [],
        env: childEnv ? diagnosticEnvironmentSnapshot(childEnv) : {},
        checkout: checkoutRoot,
        filesystem,
        input: { path: inputPath, bytes: Buffer.byteLength(taskInput, "utf8"), exists: filesystem.input?.exists === true },
        schema: { path: schemaPath, bytes: Buffer.byteLength(schemaText, "utf8"), exists: filesystem.schema?.exists === true },
        stdout,
        stderr,
        launcherDiagnostic,
        exitCode: childExitCode,
        signal: childSignal,
        classification: launcherDiagnostic?.code ?? pendingError?.code ?? (childExitCode === 0 ? "CODEX_EXIT_OK" : "UNCLASSIFIED_CHILD_FAILURE")
      });
      let store;
      try { await diagnosticStore(diagnostic); store = { status: "stored", mode: diagnosticMode, executionId }; }
      catch (error) {
        store = {
          status: "unavailable",
          code: error?.code ?? "DIAGNOSTICS_STORE_FAILED",
          ...(typeof error?.storeDiagnosticCode === "string" && /^[A-Z0-9_]+$/.test(error.storeDiagnosticCode) ? { storeCode: error.storeDiagnosticCode } : {})
        };
      }
      addDiagnosticDetails(pendingError, launcherDiagnostic, store, childExitCode, childSignal, evidence.codexChildStarted);
      evidence.diagnosticStore = store;
    }
  }
}
