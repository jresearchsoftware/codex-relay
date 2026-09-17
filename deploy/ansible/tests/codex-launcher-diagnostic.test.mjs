import test from "node:test";
import assert from "node:assert/strict";
import { PassThrough } from "node:stream";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { buildChildDiagnostic, classifyChildStderr, createStatefulSecretRedactor, sanitizeStructuredOutput, writeChildDiagnostic } from "../roles/relay_codex_runtime/files/relay-codex-diagnostic.mjs";

test("preserves JSONL stdout delimiters while redacting the Codex token", () => {
  const token = "synthetic-CODEX_ACCESS_TOKEN-SECRET";
  const value = "{\"type\":\"thread.started\"}\n{\"type\":\"item.completed\",\"text\":\"payload:" + token + "\"}\n";
  const output = sanitizeStructuredOutput(value, token);
  assert.equal(output.split("\n").length, 3);
  assert.doesNotMatch(output, /synthetic-CODEX_ACCESS_TOKEN-SECRET/);
  assert.match(output, /REDACTED_CODEX_ACCESS_TOKEN/);
});

test("redacts synthetic child stderr before the launcher diagnostic leaves the boundary", async () => {
  const token = "synthetic-CODEX_ACCESS_TOKEN-SECRET";
  const child = spawn(process.execPath, ["-e", `require("node:fs").writeSync(2, ${JSON.stringify(`fatal token=${token}`)}); process.exitCode=9`], { stdio: ["ignore", "ignore", "pipe"] });
  const chunks = [];
  child.stderr.on("data", chunk => chunks.push(chunk));
  const [exitCode] = await once(child, "close");
  const raw = Buffer.concat(chunks).toString("utf8");
  const stream = new PassThrough();
  const output = [];
  stream.on("data", chunk => output.push(chunk));
  writeChildDiagnostic({ code: classifyChildStderr(raw), stderr: raw, stderrBytes: Buffer.byteLength(raw), token, exitCode, stream });
  const line = Buffer.concat(output).toString("utf8").trim();
  const diagnostic = JSON.parse(line);
  assert.equal(exitCode, 9);
  assert.equal(diagnostic.code, "CHILD_STDERR");
  assert.equal(line.includes(token), false);
  assert.match(diagnostic.preview, /\[REDACTED_(?:CODEX_ACCESS_TOKEN|SECRET)\]/);
  const privateKeyLike = ["-----BEGIN", "PRIVATE KEY----- secret -----END", "PRIVATE KEY-----"].join(" ");
  assert.deepEqual(buildChildDiagnostic({ code: "CHILD_STDERR", stderr: privateKeyLike, token }).preview, "[REDACTED_SECRET]");
});

test("normalizes newline-terminated tokens and redacts split JSONL records", () => {
  const token = "split-secret-token\n";
  const redactor = createStatefulSecretRedactor(token);
  const first = redactor.push('{"text":"split-secret-');
  const second = redactor.push('token"}\n');
  const output = first + second + redactor.flush();
  assert.equal(output.includes("split-secret-token"), false);
  assert.match(output, /REDACTED_CODEX_ACCESS_TOKEN/);
  assert.equal(sanitizeStructuredOutput(`prefix split-secret-token\n`, token).includes("split-secret-token"), false);
  assert.equal(buildChildDiagnostic({ code: "CHILD_STDERR", stderr: token, token, childStarted: false }).childStarted, false);
});
