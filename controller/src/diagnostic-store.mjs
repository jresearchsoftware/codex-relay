#!/usr/bin/env node
import { CONSUMER } from '../../consumer/consumer.mjs';
import { chmod, mkdir, readdir, readFile, rename, rm, stat, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { realpathSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { DIAGNOSTICS_CONFIG_PATH } from "./diagnostics.mjs";

const STORE_ROOT = CONSUMER.paths.diagnosticsRoot;
const MAX_REQUEST_BYTES = 16 * 1024 * 1024;
const RETENTION_COUNT = 8;

function fail(code, message) { const error = new Error(message); error.code = code; throw error; }

export function normalizeDiagnosticRequest(value, { mode = "normal" } = {}) {
  if (!value || typeof value !== "object" || value.schemaVersion !== "1.0") fail("DIAGNOSTIC_REQUEST_INVALID", "Diagnostic request schema is invalid");
  if (value.mode !== mode || !["normal", "debug"].includes(value.mode)) fail("DIAGNOSTIC_MODE_INVALID", "Diagnostic request mode is not the governed mode");
  if (typeof value.executionId !== "string" || !/^[A-Za-z0-9_-]{1,128}$/.test(value.executionId)) fail("DIAGNOSTIC_ID_INVALID", "Diagnostic execution ID is invalid");
  const encoded = JSON.stringify(value);
  if (Buffer.byteLength(encoded, "utf8") > MAX_REQUEST_BYTES) fail("DIAGNOSTIC_REQUEST_TOO_LARGE", "Diagnostic request exceeds the bounded store size");
  const text = JSON.stringify(value);
  if (/-----BEGIN [^-]*PRIVATE KEY-----|authorization\s*:\s*bearer\s+(?!\[REDACTED_)[^\s,;]+|\bgithub_pat_(?!\[REDACTED_)|\bgh[pousr]_(?!\[REDACTED_)/i.test(text)) fail("DIAGNOSTIC_SECRET_PATTERN", "Diagnostic request contains an unredacted secret pattern");
  return value;
}

export async function writeDiagnosticBundle(value, { root = STORE_ROOT, retentionCount = RETENTION_COUNT, mode = value.mode } = {}) {
  await mkdir(root, { recursive: true, mode: 0o700 });
  await chmod(root, 0o700);
  const safe = normalizeDiagnosticRequest(value, { mode });
  const output = JSON.stringify(safe, null, 2) + "\n";
  const path = join(root, `${safe.executionId}.json`);
  const temporary = `${path}.tmp-${process.pid}`;
  await writeFile(temporary, output, { encoding: "utf8", mode: 0o600 });
  await chmod(temporary, 0o600);
  await rename(temporary, path);
  await chmod(path, 0o600);
  const entries = (await Promise.all((await readdir(root)).filter(name => name.endsWith(".json")).map(async name => ({ name, stat: await stat(join(root, name)) })))).sort((left, right) => left.stat.mtimeMs - right.stat.mtimeMs);
  for (const entry of entries.slice(0, Math.max(0, entries.length - retentionCount))) await rm(join(root, entry.name), { force: true });
  return { status: "stored", executionId: safe.executionId, mode: safe.mode, bytes: Buffer.byteLength(output, "utf8") };
}

async function readBoundedStdin() {
  const chunks = []; let bytes = 0;
  for await (const chunk of process.stdin) { bytes += chunk.length; if (bytes > MAX_REQUEST_BYTES) fail("DIAGNOSTIC_REQUEST_TOO_LARGE", "Diagnostic request exceeds the bounded store size"); chunks.push(Buffer.from(chunk)); }
  if (bytes === 0) fail("DIAGNOSTIC_REQUEST_EMPTY", "Diagnostic request is empty");
  try { return JSON.parse(Buffer.concat(chunks).toString("utf8")); } catch { fail("DIAGNOSTIC_REQUEST_INVALID", "Diagnostic request is not valid JSON"); }
}

async function main() {
  if (process.argv.length === 3 && process.argv[2] === '--check-runtime') {
    process.stdout.write('DIAGNOSTICS_RUNTIME_READY\n'); return;
  }
  const config = JSON.parse(await readFile(DIAGNOSTICS_CONFIG_PATH, "utf8"));
  if (config.schemaVersion !== "1.0" || !["normal", "debug"].includes(config.mode)) fail("DIAGNOSTICS_CONFIG_INVALID", "Diagnostics configuration is invalid");
  const result = await writeDiagnosticBundle(await readBoundedStdin(), { root: STORE_ROOT, retentionCount: Number(config.retentionCount) || RETENTION_COUNT, mode: config.mode });
  process.stdout.write(`${JSON.stringify(result)}\n`);
}

function isMainModule() { try { return Boolean(process.argv[1]) && realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url)); } catch { return false; } }
if (isMainModule()) main().catch(error => { process.stderr.write(`${JSON.stringify({ status: "blocked", code: error.code ?? "DIAGNOSTIC_STORE_FAILED", message: error.message })}\n`); process.exitCode = 1; });
