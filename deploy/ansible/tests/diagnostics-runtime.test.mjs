import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, readFile, stat, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { EventEmitter } from "node:events";
import { PassThrough } from "node:stream";
import { createExecutionDiagnostic, diagnosticEnvironmentSnapshot, persistControllerFailureDiagnostic, redactDiagnosticText } from "../../../controller/src/diagnostics.mjs";
import { normalizeDiagnosticRequest, writeDiagnosticBundle } from "../../../controller/src/diagnostic-store.mjs";
import { runGovernedCodexTask } from "../../../runtime/src/codex-runtime.mjs";
import { buildChildDiagnostic } from "../roles/relay_codex_runtime/files/relay-codex-diagnostic.mjs";
import { CONSUMER } from "../../../consumer/consumer.mjs";

test("persisted launcher diagnostics retain validated inner child evidence independently of the outer process exit", async t => {
  const cases = [
    { name: "missing-linker", childExitCode: 1, signal: null, launcherExitCode: 64, launcherSignal: null },
    { name: "child-exit-range-min", childExitCode: 0, signal: null, launcherExitCode: 64, launcherSignal: null },
    { name: "child-exit-range-max", childExitCode: 255, signal: null, launcherExitCode: 64, launcherSignal: null },
    { name: "child-signal", childExitCode: null, signal: "SIGTERM", launcherExitCode: 64, launcherSignal: null },
    { name: "launcher-signal", childExitCode: 101, signal: null, launcherExitCode: null, launcherSignal: "SIGKILL" },
    { name: "unknown-child-exit", childExitCode: null, signal: null, launcherExitCode: 64, launcherSignal: null },
    { name: "invalid-child-exit", childExitCode: null, signal: "SIGTERM", launcherExitCode: 64, launcherSignal: null, raw: { childExitCode: 256 } },
    { name: "invalid-child-signal", childExitCode: 101, signal: null, launcherExitCode: 64, launcherSignal: null, raw: { signal: "SIGTERM\n" } }
  ];
  for (const example of cases) await t.test(example.name, async t => {
    const root = await mkdtemp(join(tmpdir(), "relay-child-evidence-"));
    t.after(() => rm(root, { recursive: true, force: true }));
    const token = "codex-secret-fixture";
    const emitted = {
      ...buildChildDiagnostic({ code: "CHILD_STDERR", childStarted: true, exitCode: example.childExitCode, signal: example.signal,
        stderr: `RUST_DEVELOPMENT_PROOF_FAILED cargo-test exit=101 linker \`cc\` not found ${token}`, token }),
      ...example.raw
    };
    const evidence = {};
    const diagnosticRoot = join(root, "diagnostics");
    await assert.rejects(runGovernedCodexTask({
      operation: "review-remediation", attemptId: example.name, inputText: "bounded fixture input", cwd: root,
      buildArgs: () => [], env: { PATH: "/usr/bin:/bin" }, evidence,
      spawnImpl(command, args) {
        assert.equal(command, "/usr/bin/sudo");
        assert.deepEqual(args.slice(0, 3), ["-n", "-u", CONSUMER.runtimeUser]);
        const child = new EventEmitter();
        child.stdout = new PassThrough(); child.stderr = new PassThrough(); child.pid = 4242;
        setImmediate(() => {
          child.emit("spawn");
          child.stdout.end(); child.stderr.end(JSON.stringify(emitted) + "\n");
          child.emit("close", example.launcherExitCode, example.launcherSignal);
        });
        return child;
      },
      diagnosticStore: diagnostic => writeDiagnosticBundle(diagnostic, { root: diagnosticRoot })
    }), { code: "CODEX_NONZERO_EXIT" });
    assert.equal(evidence.diagnosticStore.status, "stored");
    const saved = await readFile(join(diagnosticRoot, `${example.name}.json`), "utf8");
    const parsed = JSON.parse(saved);
    assert.equal(parsed.launcherDiagnostic.childExitCode, example.childExitCode);
    assert.equal(parsed.launcherDiagnostic.signal, example.signal);
    assert.equal(parsed.launcherDiagnostic.childStarted, true);
    assert.equal(parsed.launcherDiagnostic.childState, "started");
    assert.equal(parsed.process.exitCode, example.launcherExitCode);
    assert.equal(parsed.process.signal, example.launcherSignal);
    assert.match(parsed.launcherDiagnostic.preview, /RUST_DEVELOPMENT_PROOF_FAILED cargo-test exit=101 linker `cc` not found/);
    assert.ok(Buffer.byteLength(parsed.launcherDiagnostic.preview, "utf8") <= 1024);
    assert.equal(saved.includes(token), false);
    assert.match(parsed.launcherDiagnostic.preview, /REDACTED_CODEX_ACCESS_TOKEN/);
  });
});

test("redacts exact Codex/GitHub credentials and boundary secret patterns", () => {
  const codex = "codex-secret-fixture";
  const github = "github-secret-fixture";
  const value = redactDiagnosticText(`codex=${codex} github=${github} Authorization: Bearer bearer-fixture`, { codexAccessToken: codex, githubToken: github });
  assert.doesNotMatch(value, /codex-secret-fixture|github-secret-fixture|bearer-fixture/);
  assert.match(value, /REDACTED_CODEX_ACCESS_TOKEN/);
  assert.match(value, /REDACTED_GITHUB_TOKEN/);
  assert.match(value, /REDACTED_BEARER/);
});

test("debug bundle persists bounded redacted streams and safe metadata only", async () => {
  const root = await mkdtemp(join(tmpdir(), "relay-diagnostics-"));
  const codex = "codex-secret-fixture";
  const github = "github-secret-fixture";
  try {
    const diagnostic = createExecutionDiagnostic({
      executionId: "debug-fixture-1",
      mode: "debug",
      startedAt: "2026-08-16T00:00:00.000Z",
      endedAt: "2026-08-16T00:00:01.000Z",
      phase: "child-closed",
      pid: 12,
      ppid: 11,
      cwd: "/var/lib/codex-relay/dispatch-work/run-fixture",
      executable: "/opt/codex-relay/relay-codex",
      argv: ["exec", "--json"],
      env: diagnosticEnvironmentSnapshot({ PATH: "/usr/bin:/bin", CODEX_ACCESS_TOKEN: codex, GITHUB_TOKEN: github }),
      checkout: "/var/lib/codex-relay/dispatch-work/run-fixture",
      filesystem: { checkout: { exists: true, mode: "2770", uid: 1001, gid: 1002 } },
      input: { exists: true, bytes: 10 },
      schema: { exists: true, bytes: 20 },
      stdout: `result token=${codex}`,
      stderr: `failure github=${github} Authorization: Bearer bearer-fixture`,
      exitCode: 64,
      classification: "CHILD_STDERR",
      secrets: { codexAccessToken: codex, githubToken: github }
    });
    const result = await writeDiagnosticBundle(diagnostic, { root, mode: "debug", retentionCount: 2 });
    assert.equal(result.status, "stored");
    const path = join(root, "debug-fixture-1.json");
    const saved = await readFile(path, "utf8");
    assert.doesNotMatch(saved, /codex-secret-fixture|github-secret-fixture|bearer-fixture/);
    assert.match(saved, /REDACTED_CODEX_ACCESS_TOKEN/);
    assert.match(saved, /REDACTED_GITHUB_TOKEN/);
    if (process.platform !== "win32") assert.equal((await stat(path)).mode & 0o077, 0);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("root store rejects a request whose operator mode differs from configured mode", () => {
  assert.throws(() => normalizeDiagnosticRequest({ schemaVersion: "1.0", executionId: "mode-fixture", mode: "debug" }, { mode: "normal" }), error => error.code === "DIAGNOSTIC_MODE_INVALID");
});

test("controller failure evidence stores a bounded redacted private stack and returns a safe reference", async () => {
  let stored;
  const error = Object.assign(new Error("controller detail token=private-fixture"), { code: "UNEXPECTED_CONTROLLER_FAILURE" });
  const reference = await persistControllerFailureDiagnostic({
    error,
    invocation: { repository: "example/relay-consumer", pullRequest: 185, reviewId: 5016032994, operation: "review-remediation" },
    executionId: "controller-fixture-1",
    mode: "debug",
    env: { PATH: "/usr/bin:/bin", GITHUB_TOKEN: "github-secret-fixture" },
    secrets: { githubToken: "github-secret-fixture" },
    diagnosticStore: async value => { stored = value; }
  });
  assert.deepEqual(reference, { status: "stored", code: "UNEXPECTED_CONTROLLER_FAILURE", executionId: "controller-fixture-1", mode: "debug" });
  assert.equal(stored.classification, "UNEXPECTED_CONTROLLER_FAILURE");
  assert.equal(stored.input.pullRequest, 185);
  assert.match(stored.stderr.text, /controller detail/);
  assert.doesNotMatch(stored.stderr.text, /private-fixture/);
  assert.doesNotMatch(JSON.stringify(reference), /controller detail|private-fixture/);
});

test("controller failure evidence reports a bounded store failure without exposing the private stack", async () => {
  const error = Object.assign(new Error("private controller detail"), { code: "UNEXPECTED_CONTROLLER_FAILURE" });
  const reference = await persistControllerFailureDiagnostic({
    error,
    executionId: "controller-store-failure-1",
    diagnosticStore: async () => { throw Object.assign(new Error("store unavailable"), { code: "DIAGNOSTICS_STORE_FAILED", storeDiagnosticCode: "EACCES" }); }
  });
  assert.deepEqual(reference, { status: "unavailable", code: "DIAGNOSTICS_STORE_FAILED", storeCode: "EACCES", executionId: "controller-store-failure-1", mode: "normal" });
});
