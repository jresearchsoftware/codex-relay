// Dedicated installed proof fixture, never part of the production runtime.
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync, mkdirSync, openSync, closeSync } from 'node:fs';
import { execFileSync } from 'node:child_process';

export function rustCommand(stage, command, args) {
  try {
    return execFileSync(command, args, { encoding: 'utf8', stdio: 'pipe', maxBuffer: 64 * 1024, timeout: 60000 }).trim();
  } catch (error) {
    // The caller redacts before logging. Preserve text, not the exec object's
    // raw buffers/argv/environment, so Cargo's actual cause is visible first.
    throw Object.assign(new Error('RUST_DEVELOPMENT_PROOF_FAILED'), { rustDiagnostic: {
      stage, exitCode: Number.isInteger(error.status) ? error.status : null,
      detail: String(error.stderr || error.message)
    } });
  }
}

export function qualifyRustDevelopment(cwd, rust) {
  assert.equal(process.env.PATH, `${rust.root}/bin:/usr/bin:/bin`);
  assert.equal(process.env.CARGO_HOME, `${cwd}/.codex-sandbox/cache/cargo`);
  assert.equal(process.env.RUSTUP_HOME, undefined);
  for (const name of ['cargo', 'rustc', 'rustfmt']) {
    assert.equal(rustCommand(`${name}-version`, name, ['--version']), rust.versions[name]);
    // Opening for write proves kernel denial without changing a binary.
    assert.throws(() => closeSync(openSync(`${rust.root}/bin/${name}`, 'r+')), { code: 'EACCES' });
  }
  for (const path of [rust.root, `${rust.root}/bin`, `${rust.root}/lib`, rust.buildCache, rust.release, rust.reviewerSource]) {
    assert.throws(() => writeFileSync(`${path}/codex-write-probe`, 'forbidden'), { code: 'EACCES' });
  }
  // Real compiler, formatter, linker, sysroot and task-private Cargo state;
  // no registry dependencies and no downloads in the private network namespace.
  const probe = `${cwd}/.codex-sandbox/rust-probe`;
  mkdirSync(process.env.CARGO_HOME, { recursive: true });
  mkdirSync(`${probe}/src`, { recursive: true });
  writeFileSync(`${probe}/Cargo.toml`, '[package]\nname = "runtime-probe"\nversion = "0.1.0"\nedition = "2021"\n');
  writeFileSync(`${probe}/src/lib.rs`, '#[test]\nfn managed_toolchain_runs() { assert_eq!(std::env::consts::OS, "linux"); }\n');
  rustCommand('rustfmt', 'rustfmt', [`${probe}/src/lib.rs`]);
  rustCommand('cargo-lockfile', 'cargo', ['generate-lockfile', '--offline', '--manifest-path', `${probe}/Cargo.toml`]);
  const lock = readFileSync(`${probe}/Cargo.lock`, 'utf8');
  rustCommand('cargo-test', 'cargo', ['test', '--locked', '--offline', '--manifest-path', `${probe}/Cargo.toml`]);
  assert.equal(readFileSync(`${probe}/Cargo.lock`, 'utf8'), lock);
  writeFileSync(`${process.env.CARGO_HOME}/cache-write-probe`, 'task-private');
}
