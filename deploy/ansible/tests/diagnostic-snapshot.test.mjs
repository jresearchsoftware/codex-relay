import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { loadTemplate } from "./render-template.mjs";
const { buildSnapshot, safeRecord } = await loadTemplate("relay-qualification-diagnostic-snapshot.mjs");

test("safeRecord admits only field-specific bounded diagnostic values", () => {
  const record = safeRecord({
    claimId: "claim-1",
    claimKey: "issue:128:codex-ready-auto",
    operationKey: "issue:128:codex-ready-auto",
    executionId: "exec-1",
    target: "issue",
    route: "auto",
    phase: "cleanup-complete",
    failureCode: "CODEX_NONZERO_EXIT",
    classification: "CHILD_STDERR",
    dispatchStatus: "started",
    workerState: "failed",
    startedAt: "2026-08-16T13:00:00.000Z",
    recovery: "not_attempted"
  }, "claims.json");

  assert.equal(record.claimId, "claim-1");
  assert.equal(record.operationKey, "issue:128:codex-ready-auto");
  assert.equal(record.target, "issue");
  assert.equal(record.startedAt, "2026-08-16T13:00:00.000Z");
  assert.equal(record.recovery, "not_attempted");
});

test("safeRecord retains stable claimId while omitting an oversized PR operation key", () => {
  const operationKey = [
    "example/relay-consumer",
    "pr-185",
    "review-5016032994",
    "cr-099W-P7E-001",
    `head-${"a".repeat(40)}`,
    `prbody-${"c".repeat(64)}`,
    `reviewbody-${"d".repeat(64)}`,
    `contract-${"e".repeat(64)}`
  ].join(":");
  assert.ok(operationKey.length > 128);
  const record = safeRecord({
    claimId: "36609257d85bb5e25f075719",
    claimKey: operationKey,
    operationKey,
    target: "pull_request",
    phase: "failed",
    failureCode: "CODEX_DISPATCH_FAILED",
    executionConfirmed: false
  }, "claims.json");

  assert.equal(record.claimId, "36609257d85bb5e25f075719");
  assert.equal(record.claimKey, undefined);
  assert.equal(record.operationKey, undefined);
});

test("safeRecord rejects malformed, oversized, control, path-like, and secret-like strings", () => {
  const record = safeRecord({
    claimId: "../escape",
    claimKey: "issue/128",
    operationKey: "token=do-not-retain",
    executionId: "x\u0000y",
    target: "/etc/passwd",
    route: "manual\nsecret",
    phase: "x".repeat(129),
    failureCode: "CHILD-STDERR",
    classification: "PRIVATE_KEY",
    dispatchStatus: "Bearer-secret",
    workerState: "worker/state",
    startedAt: "not-a-timestamp",
    recovery: "credential_material"
  }, "claims.json");

  assert.equal(record, undefined);
});

test("grouped diagnostic snapshot correlates claim and execution without protected bodies", async () => {
  const root = await mkdtemp(join(tmpdir(), "relay-snapshot-"));
  const paths = {
    claimRoot: join(root, "claims"),
    dispatchRoot: join(root, "dispatch"),
    debugRoot: join(root, "debug"),
    diagnosticsConfig: join(root, "diagnostics.json")
  };
  try {
    await Promise.all([mkdir(paths.claimRoot), mkdir(paths.dispatchRoot), mkdir(paths.debugRoot)]);
    await writeFile(paths.diagnosticsConfig, JSON.stringify({ schemaVersion: "1.0", mode: "debug" }));
    await writeFile(join(paths.claimRoot, "claims.json"), JSON.stringify({ claims: [{ claimId: "claim-1", phase: "uncertain", failureCode: "CODEX_NONZERO_EXIT", failureDiagnostic: { code: "CHILD_STDERR", diagnosticStore: { status: "stored", executionId: "exec-1", mode: "debug" } } }] }));
    await writeFile(join(paths.dispatchRoot, "dispatch-1.json"), JSON.stringify({ claimId: "claim-1", executionId: "exec-1", workerState: "failed" }));
    await writeFile(join(paths.debugRoot, "exec-1.json"), JSON.stringify({ executionId: "exec-1", mode: "debug", phase: "cleanup-complete", classification: "CHILD_STDERR", stderr: "protected-body", stdout: "protected-body" }));

    const snapshot = await buildSnapshot({ claim: "claim-1" }, paths);
    const encoded = JSON.stringify(snapshot);
    assert.equal(snapshot.diagnosticsMode, "debug");
    assert.equal(snapshot.claimRecords.some(record => record.claimId === "claim-1"), true);
    assert.equal(snapshot.dispatchRecords.some(record => record.executionId === "exec-1"), true);
    assert.equal(snapshot.debugBundles[0].executionId, "exec-1");
    assert.equal(snapshot.debugBundles[0].classification, "CHILD_STDERR");
    assert.doesNotMatch(encoded, /protected-body|stderr|stdout/);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
