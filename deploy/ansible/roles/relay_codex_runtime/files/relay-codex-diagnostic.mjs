const MAX_DIAGNOSTIC_PREVIEW_BYTES = 1024;
export const MAX_DIAGNOSTIC_CAPTURE_BYTES = 1024 * 1024;
export const MAX_DEBUG_CAPTURE_BYTES = 4 * 1024 * 1024;

const SECRET_PATTERNS = [
  /-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?-----END [^-]*PRIVATE KEY-----/gi,
  /\b(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]+/g,
  /\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}/g,
  /\b(?:password|passwd|secret|token|api[_-]?key|access[_-]?token)\b\s*[:=]\s*[^\s,;]+/gi,
  /\b(?:authorization\s*:\s*bearer|bearer|basic)\s+[^\s,;]+/gi
];

function normalizeSecret(value) {
  return typeof value === "string" ? value.trim() : "";
}

function redactSecrets(value, token = "") {
  let text = String(value ?? "");
  const normalizedToken = normalizeSecret(token);
  if (normalizedToken) text = text.split(normalizedToken).join("[REDACTED_CODEX_ACCESS_TOKEN]");
  for (const pattern of SECRET_PATTERNS) text = text.replace(pattern, "[REDACTED_SECRET]");
  return text;
}

export function createStatefulSecretRedactor(token = "") {
  const normalizedToken = normalizeSecret(token);
  let carry = "";
  return {
    push(value) {
      const input = carry + String(value ?? "");
      const boundary = input.lastIndexOf("\n") + 1;
      if (boundary === 0) {
        carry = input;
        return "";
      }
      carry = input.slice(boundary);
      return redactSecrets(input.slice(0, boundary), normalizedToken);
    },
    flush() {
      const safe = redactSecrets(carry, normalizedToken);
      carry = "";
      return safe;
    }
  };
}

export function decodeUtf8(value) {
  const bytes = Buffer.isBuffer(value) || value instanceof Uint8Array ? Buffer.from(value) : Buffer.from(String(value ?? ""), "utf8");
  const fatal = new TextDecoder("utf-8", { fatal: true });
  try { return fatal.decode(bytes); }
  catch {
    // A bounded byte prefix may end in a valid UTF-8 sequence's middle. Drop
    // only the incomplete suffix; do not manufacture U+FFFD in diagnostics.
    for (let end = bytes.length - 1; end >= Math.max(0, bytes.length - 3); end -= 1) {
      try { return fatal.decode(bytes.subarray(0, end)); } catch { /* Try the next safe prefix. */ }
    }
    return new TextDecoder("utf-8").decode(bytes);
  }
}

function boundedUtf8(value, maxBytes) {
  return decodeUtf8(Buffer.from(value, "utf8").subarray(0, maxBytes));
}

export function sanitizeDiagnosticText(value, token = "", maxBytes = MAX_DIAGNOSTIC_PREVIEW_BYTES) {
  // Never log request content, credentials, or tokens in a diagnostic preview.
  let text = redactSecrets(value, token);
  text = text.replace(/[\u0000-\u001f\u007f-\u009f]/g, " ");
  return boundedUtf8(text, maxBytes);
}

export function sanitizeStructuredOutput(value, token = "", maxBytes = MAX_DEBUG_CAPTURE_BYTES) {
  // Preserve JSONL record delimiters while redacting secrets before stdout
  // crosses from the trusted Codex identity back to the relay runner.
  let text = redactSecrets(value, token);
  text = text.replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f]/g, " ");
  return boundedUtf8(text, maxBytes);
}

export function assertSecretFreePublication(value, token = "") {
  const serialized = String(value ?? "");
  const normalizedToken = normalizeSecret(token);
  if (normalizedToken && serialized.includes(normalizedToken)) throw new Error("KNOWN_SECRET_PUBLICATION_BLOCKED");
  return serialized;
}

export function classifyChildStderr(value) {
  const text = String(value ?? "");
  if (text.length === 0) return "NO_STDERR";
  if (/\b(?:EACCES|EPERM|ENOENT|EPIPE|ECONNRESET|ETIMEDOUT)\b/.test(text)) return "PROCESS_IO_ERROR";
  if (/not found|cannot find|permission denied/i.test(text)) return "PROCESS_START_OR_PERMISSION";
  if (/invalid|malformed|json|parse/i.test(text)) return "OUTPUT_OR_INPUT_ERROR";
  return "CHILD_STDERR";
}

export function buildChildDiagnostic({ code, stderr = "", stderrBytes, token = "", exitCode = null, signal = null, debug = false, pid = null, ppid = process.ppid, childStarted = null, primaryCause = null } = {}) {
  const safeCode = /^[A-Z0-9_]+$/.test(String(code ?? "")) ? String(code) : "CHILD_STDERR";
  const bytes = Number.isInteger(stderrBytes) && stderrBytes >= 0 ? stderrBytes : Buffer.byteLength(String(stderr), "utf8");
  const safeSignal = typeof signal === "string" && /^SIG[A-Z0-9]+$/.test(signal) ? signal : null;
  return {
    source: "relay-codex-launcher",
    schemaVersion: 1,
    code: safeCode,
    childExitCode: Number.isInteger(exitCode) ? exitCode : null,
    signal: safeSignal,
    childStarted: typeof childStarted === "boolean" ? childStarted : null,
    childState: typeof childStarted === "boolean" ? (childStarted ? "started" : "not_started") : "unknown",
    primaryCause: /^[A-Z][A-Z0-9_]{0,79}$/.test(primaryCause ?? "") ? primaryCause : null,
    bytes,
    truncated: bytes > (debug ? MAX_DEBUG_CAPTURE_BYTES : MAX_DIAGNOSTIC_CAPTURE_BYTES),
    preview: sanitizeDiagnosticText(stderr, token),
    ...(debug ? { debug: { pid: Number.isInteger(pid) ? pid : null, ppid: Number.isInteger(ppid) ? ppid : null, stderr: sanitizeDiagnosticText(stderr, token, MAX_DEBUG_CAPTURE_BYTES) } } : {})
  };
}

export function writeChildDiagnostic({ code, stderr = "", stderrBytes, token = "", exitCode = null, signal = null, debug = false, pid = null, childStarted = null, primaryCause = null, stream = process.stderr } = {}) {
  const diagnostic = buildChildDiagnostic({ code, stderr, stderrBytes, token, exitCode, signal, debug, pid, childStarted, primaryCause });
  const output = JSON.stringify(diagnostic);
  assertSecretFreePublication(output, token);
  stream.write(output + "\n");
  return diagnostic;
}
