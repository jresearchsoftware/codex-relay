import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { loadTemplate } from "./render-template.mjs";
const { readEffectiveMode, setEffectiveMode } = await loadTemplate("relay-diagnostics-control.mjs");

async function fixture() {
  const root = await mkdtemp(join(tmpdir(), "relay-diagnostics-control-"));
  const path = join(root, "diagnostics.json");
  await writeFile(path, JSON.stringify({ schemaVersion: "1.0", mode: "normal", retentionCount: 8 }) + "\n", "utf8");
  return { root, path };
}

test("reads and atomically switches only the two supported runtime modes", async () => {
  const { root, path } = await fixture();
  try {
    assert.equal(readEffectiveMode(path), "normal");
    assert.equal(setEffectiveMode("debug", path), "debug");
    assert.equal(readEffectiveMode(path), "debug");
    const saved = JSON.parse(await readFile(path, "utf8"));
    assert.deepEqual(saved, { schemaVersion: "1.0", mode: "debug", retentionCount: 8 });
    assert.equal(setEffectiveMode("normal", path), "normal");
    assert.equal(readEffectiveMode(path), "normal");
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("rejects invalid values and symlinked configuration paths", { skip: process.platform === "win32" }, async () => {
  const { root, path } = await fixture();
  const link = join(root, "link.json");
  try {
    assert.throws(() => setEffectiveMode("verbose", path), error => error.code === "DIAGNOSTICS_MODE_INVALID");
    await symlink(path, link);
    assert.throws(() => readEffectiveMode(link), error => error.code === "DIAGNOSTICS_CONFIG_UNSAFE");
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("does not accept an arbitrary configuration path through the command boundary", async () => {
  const { root, path } = await fixture();
  try {
    assert.equal(readEffectiveMode(path), "normal");
    assert.throws(() => setEffectiveMode("debug", join(root, "other.json")), error => error.code === "DIAGNOSTICS_CONFIG_MISSING");
    assert.equal(readEffectiveMode(path), "normal");
  } finally { await rm(root, { recursive: true, force: true }); }
});
