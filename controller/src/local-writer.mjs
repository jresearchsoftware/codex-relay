import { CONSUMER } from '../../consumer/consumer.mjs';
import { spawn as nodeSpawn } from "node:child_process";
import { WriterBlockedError } from "../../runtime/src/contracts.mjs";
import { createBoundedUtf8Capture } from "./utf8-capture.mjs";
import { failureDiagnosticFromDetails, safeDiagnosticStoreReference, safeFallbackReference } from "./diagnostics.mjs";
import { ownerRunRejectionReason } from './owner-run-rejection.mjs';

const DEFAULT_HELPER = CONSUMER.paths.writerHelper;
// Includes the fixed wrapper's 300-second lock wait and a bounded 120-second
// trusted Git operation. Contention never authorizes another model invocation.
const INVOCATION_TIMEOUT_MS = 450000;

function requestError(error, operation) {
  let payload;
  try { payload = JSON.parse(String(error.stderr ?? "")); } catch { payload = undefined; }
  const code = typeof payload?.code === "string" && /^[A-Z][A-Z0-9_]{0,79}$/.test(payload.code) ? payload.code : "WRITER_HELPER_FAILED";
  const failureDiagnostic = failureDiagnosticFromDetails(payload);
  const reason = ownerRunRejectionReason(code, payload?.reason);
  const result = new WriterBlockedError(code, "The privileged Writer helper failed", {
    ...(reason ? { reason } : {}), ...(safeDiagnosticStoreReference(payload?.diagnosticStore) ? { diagnosticStore: safeDiagnosticStoreReference(payload.diagnosticStore) } : {}), ...(safeFallbackReference(payload?.fallbackReference) ? { fallbackReference: safeFallbackReference(payload.fallbackReference) } : {}), ...(failureDiagnostic ? { failureDiagnostic } : {})
  });
  Object.defineProperty(result, 'cause', { value: error });
  Object.defineProperty(result, 'native', { value: { operation, stderr: error.stderr, stdout: error.stdout, exitCode: error.exitCode, signal: error.signal,
    stderrBytes: error.stderrBytes, stdoutBytes: error.stdoutBytes, truncated: error.truncated } });
  return result;
}

export function createLocalWriterAdapter({ helperPath = DEFAULT_HELPER, sudo = "/usr/bin/sudo", spawnImpl = nodeSpawn } = {}) {
  if (helperPath !== DEFAULT_HELPER) throw new WriterBlockedError("WRITER_HELPER_PATH_INVALID", "Only the fixed relay Writer helper path is allowed");
  async function invoke(request) {
    if (request.repository !== undefined && request.repository !== CONSUMER.repository) throw new WriterBlockedError('WRITER_REPOSITORY_INVALID', 'The Writer target must match the selected configured repository');
    request = { ...request, repository: CONSUMER.repository };
    let child;
    try { child = spawnImpl(sudo, ["-n", helperPath], { env: { PATH: "/usr/bin:/bin", LANG: "C", LC_ALL: "C" }, stdio: ["pipe", "pipe", "pipe"], windowsHide: true }); }
    catch (error) { throw requestError(error, request.operation); }
    // Collection returns the same bounded base64 bundle accepted by Writer
    // publication. Ordinary receipts retain their existing small output limit.
    const stdoutCapture = createBoundedUtf8Capture(request.operation === 'collect-progress' ? 145 * 1024 * 1024 : 1024 * 1024);
    const stderrCapture = createBoundedUtf8Capture(1024 * 1024);
    let stdout = "";
    let stderr = "";
    let settled = false; let inputError;
    const result = await new Promise((resolve, reject) => {
      const rejectCaptured = error => {
        if (settled) return;
        settled = true; clearTimeout(timer);
        const out = stdoutCapture.finish(); const err = stderrCapture.finish();
        error.native = { ...error.native, operation: request.operation };
        Object.assign(error, { stdout: out.value, stderr: err.value, stdoutBytes: out.total, stderrBytes: err.total,
          truncated: out.truncated || err.truncated });
        reject(requestError(error, request.operation));
      };
      const timer = setTimeout(() => {
        if (settled) return;
        settled = true;
        let killFailure;
        try { child.kill?.("SIGTERM"); } catch (error) { killFailure = error; }
        const timeout = Object.assign(new Error("The privileged Writer helper exceeded its bounded invocation timeout", { cause: killFailure }), {
          stdout: stdoutCapture.finish().value, stderr: stderrCapture.finish().value });
        const wrapped = requestError(timeout, request.operation); wrapped.code = "WRITER_HELPER_TIMEOUT"; reject(wrapped);
      }, INVOCATION_TIMEOUT_MS);
      child.stdout?.on("data", chunk => stdoutCapture.push(chunk));
      child.stderr?.on("data", chunk => stderrCapture.push(chunk));
      child.once("error", rejectCaptured);
      child.stdout?.once?.("error", rejectCaptured);
      child.stderr?.once?.("error", rejectCaptured);
      child.once("close", (code, signal) => {
        clearTimeout(timer);
        if (settled) return;
        settled = true;
        const stdoutResult = stdoutCapture.finish();
        const stderrResult = stderrCapture.finish();
        stdout = stdoutResult.value;
        stderr = stderrResult.value;
        if (stdoutResult.truncated || stderrResult.truncated) { const error = Object.assign(new Error("The privileged Writer helper output exceeded the bounded byte limit"), {
          code: "WRITER_OUTPUT_TOO_LARGE", stdout, stderr, truncated: true, stdoutBytes: stdoutResult.total, stderrBytes: stderrResult.total });
          const wrapped = requestError(error, request.operation); wrapped.code = "WRITER_OUTPUT_TOO_LARGE"; reject(wrapped); return; }
        if (code !== 0) { const error = new Error(stderr, { cause: inputError }); error.stderr = stderr; error.stdout = stdout; error.stderrBytes = stderrResult.total; error.stdoutBytes = stdoutResult.total; error.exitCode = code; error.signal = signal; error.code = code ?? signal ?? "WRITER_HELPER_FAILED"; reject(requestError(error, request.operation)); return; }
        if (inputError) { settled = false; rejectCaptured(inputError); return; }
        try { resolve(JSON.parse(stdout)); } catch (cause) { const error = new Error("The privileged Writer helper did not return JSON", { cause });
          error.stdout = stdout; error.stderr = stderr; const wrapped = requestError(error, request.operation); wrapped.code = "WRITER_RECEIPT_INVALID"; reject(wrapped); }
      });
      child.stdin?.once?.("error", error => { inputError = error; });
      child.stdin?.end(JSON.stringify(request) + "\n");
    });
    if (!result || result.repository !== CONSUMER.repository) throw new WriterBlockedError("WRITER_RECEIPT_INVALID", "The privileged Writer receipt is not repository-bound");
    return result;
  }
  return { invoke };
}
