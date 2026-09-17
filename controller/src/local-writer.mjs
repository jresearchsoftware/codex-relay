import { CONSUMER } from '../../consumer/consumer.mjs';
import { spawn as nodeSpawn } from "node:child_process";
import { WriterBlockedError } from "../../runtime/src/contracts.mjs";
import { createBoundedUtf8Capture } from "./utf8-capture.mjs";
import { failureDiagnosticFromDetails } from "./diagnostics.mjs";

const DEFAULT_HELPER = CONSUMER.paths.writerHelper;
const INVOCATION_TIMEOUT_MS = 180000;

function requestError(error) {
  let payload;
  try { payload = JSON.parse(String(error.stderr ?? "")); } catch { payload = undefined; }
  const code = typeof payload?.code === "string" && /^[A-Z][A-Z0-9_]{0,79}$/.test(payload.code) ? payload.code : "WRITER_HELPER_FAILED";
  const failureDiagnostic = failureDiagnosticFromDetails(payload);
  return new WriterBlockedError(code, "The privileged Writer helper failed", failureDiagnostic ? { failureDiagnostic } : {});
}

export function createLocalWriterAdapter({ helperPath = DEFAULT_HELPER, sudo = "/usr/bin/sudo", spawnImpl = nodeSpawn } = {}) {
  if (helperPath !== DEFAULT_HELPER) throw new WriterBlockedError("WRITER_HELPER_PATH_INVALID", "Only the fixed relay Writer helper path is allowed");
  async function invoke(request) {
    let child;
    try { child = spawnImpl(sudo, ["-n", helperPath], { env: { PATH: "/usr/bin:/bin", LANG: "C", LC_ALL: "C" }, stdio: ["pipe", "pipe", "pipe"], windowsHide: true }); }
    catch (error) { throw requestError(error); }
    const stdoutCapture = createBoundedUtf8Capture(1024 * 1024);
    const stderrCapture = createBoundedUtf8Capture(1024 * 1024);
    let stdout = "";
    let stderr = "";
    let settled = false;
    const result = await new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        if (settled) return;
        settled = true;
        child.kill?.("SIGTERM");
        reject(new WriterBlockedError("WRITER_HELPER_TIMEOUT", "The privileged Writer helper exceeded its bounded invocation timeout"));
      }, INVOCATION_TIMEOUT_MS);
      child.stdout?.on("data", chunk => stdoutCapture.push(chunk));
      child.stderr?.on("data", chunk => stderrCapture.push(chunk));
      child.once("error", error => { clearTimeout(timer); if (!settled) { settled = true; reject(requestError(error)); } });
      child.once("close", (code, signal) => {
        clearTimeout(timer);
        if (settled) return;
        settled = true;
        const stdoutResult = stdoutCapture.finish();
        const stderrResult = stderrCapture.finish();
        stdout = stdoutResult.value;
        stderr = stderrResult.value;
        if (stdoutResult.truncated || stderrResult.truncated) { reject(new WriterBlockedError("WRITER_OUTPUT_TOO_LARGE", "The privileged Writer helper output exceeded the bounded byte limit")); return; }
        if (code !== 0) { const error = new Error(stderr); error.stderr = stderr; error.code = code ?? signal ?? "WRITER_HELPER_FAILED"; reject(requestError(error)); return; }
        try { resolve(JSON.parse(stdout)); } catch { reject(new WriterBlockedError("WRITER_RECEIPT_INVALID", "The privileged Writer helper did not return JSON")); }
      });
      child.stdin?.once?.("error", () => {});
      child.stdin?.end(JSON.stringify(request) + "\n");
    });
    if (!result || result.repository !== CONSUMER.repository) throw new WriterBlockedError("WRITER_RECEIPT_INVALID", "The privileged Writer receipt is not repository-bound");
    return result;
  }
  return { invoke };
}
