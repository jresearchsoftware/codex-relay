import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, open, readFile, writeFile, rm, symlink } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { safeModel, safeEffort } from '../../../runtime/src/codex-profile.mjs';

async function fixture(t) {
  const root = await mkdtemp(join(tmpdir(), 'task210-launcher-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const work = join(root, 'work'); const cwd = join(work, 'event-210');
  const sandbox = join(cwd, '.codex-sandbox');
  await mkdir(sandbox, { recursive: true }); await mkdir(join(cwd, '.git'));
  const input = join(sandbox, 'task-input.md'); const schema = join(sandbox, 'codex-result-schema.json');
  await writeFile(input, 'Complete the admitted task on its branch.');
  await writeFile(schema, '{"type":"object"}');
  const rust = join(root, 'managed-rust');
  await mkdir(join(rust, 'bin'), { recursive: true });
  for (const name of ['cargo', 'rustc', 'rustfmt']) {
    await writeFile(join(rust, 'bin', name), `#!/bin/sh\nprintf 'managed ${name}\\n'\n`, { mode: 0o755 });
  }
  const child = join(root, 'child.mjs'); const token = join(root, 'synthetic-token');
  const record = join(root, 'child-record.json');
  await writeFile(child, `#!${process.execPath}
import { readFileSync, writeFileSync, openSync, closeSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
const input = readFileSync(0, 'utf8');
const toolVersion = name => {
  const output = ${JSON.stringify(record)} + '-' + name;
  const fd = openSync(output, 'w');
  try { execFileSync(name, ['--version'], { stdio: ['ignore', fd, fd] }); }
  finally { closeSync(fd); }
  return readFileSync(output, 'utf8').trim();
};
writeFileSync(${JSON.stringify(record)}, JSON.stringify({
  args: process.argv.slice(2), input, cwd: process.cwd(), home: process.env.HOME,
  githubCredentialPresent: !!process.env.GITHUB_TOKEN,
  path: process.env.PATH, cargoHome: process.env.CARGO_HOME,
  tools: ['cargo', 'rustc', 'rustfmt'].map(toolVersion)
}));
`, { mode: 0o755 });
  await writeFile(token, 'synthetic-task210-token\n');
  const config = join(root, 'diagnostics.json');
  await writeFile(config, JSON.stringify({ schemaVersion: '1.0', mode: 'normal' }));
  const variables = {
    relay_codex_binary_path: child, relay_codex_access_token_file: token,
    relay_dispatch_work_root: work, relay_diagnostics_config_path: config,
    relay_rust_toolchain_root: rust,
    relay_writer_commit_name: "example-writer", relay_writer_commit_email: "writer@example.invalid",
    relay_remediation_commit_name: "example-remediation", relay_remediation_commit_email: "remediation@example.invalid",
    relay_codex_diagnostic_path: resolve('deploy/ansible/roles/relay_codex_runtime/files/relay-codex-diagnostic.mjs')
  };
  const template = await readFile(new URL('../roles/relay_codex_runtime/templates/relay-codex-launcher.mjs.j2', import.meta.url), 'utf8');
  const launcher = join(root, 'launcher.mjs');
  await writeFile(launcher, template.replace(/{{\s*(\w+)(\s*\|\s*to_json)?\s*}}/g, (_, key, json) => {
    assert.ok(variables[key], key); return json ? JSON.stringify(variables[key]) : variables[key];
  }));
  let invocation = 0;
  return { cwd, input, schema, sandbox, token, record, rust,
    run: async (model, effort, remediation = false, taskRoot = cwd) => {
      // Regular files also work in unprivileged sandboxes that restrict Node's
      // nested socket-backed stdio. The launched template and child are real.
      const outputPath = join(root, `stdout-${++invocation}`); const errorPath = join(root, `stderr-${invocation}`);
      const output = await open(outputPath, 'w'); const error = await open(errorPath, 'w');
      let code;
      try {
        const launched = spawn(process.execPath, [launcher,
      'exec', ...(remediation ? ['--operation', 'review-remediation'] : []), '--json',
      '--model', model, '--effort', effort, '--input-file', input, '--cwd', taskRoot,
      remediation ? '--pull-request' : '--issue', '210'], {
          env: { PATH: '/caller/untrusted/bin', CARGO_HOME: '/protected/build-cache', GITHUB_TOKEN: 'synthetic-should-not-cross' },
          stdio: ['ignore', output.fd, error.fd]
        });
        [code] = await once(launched, 'close');
      } finally { await output.close(); await error.close(); }
      const result = { stdout: await readFile(outputPath, 'utf8'), stderr: await readFile(errorPath, 'utf8') };
      if (code !== 0) throw Object.assign(new Error(`Fixture launcher failed: ${result.stderr}`), { code, ...result });
      return result;
    } };
}

test('rendered launcher passes unknown safe profiles and native efforts unchanged in both operations', async t => {
  const f = await fixture(t);
  for (const remediation of [false, true]) {
    for (const effort of ['low', 'medium', 'high', 'xhigh', 'max', 'ultra', 'Future-effort_9']) {
      const model = 'Future.Model-9';
      const result = await f.run(model, effort, remediation);
      const child = JSON.parse(await readFile(f.record, 'utf8'));
      assert.equal(child.args[child.args.indexOf('--model') + 1], model);
      assert.equal(child.args[child.args.indexOf('-c') + 1], `model_reasoning_effort=${effort}`);
      assert.equal(child.args[child.args.indexOf('--sandbox') + 1], 'workspace-write');
      assert.equal(child.args[child.args.indexOf('--add-dir') + 1], join(f.cwd, '.git'));
      assert.deepEqual(child.args.filter((_, i, args) => args[i - 1] === '-c'),
        [`model_reasoning_effort=${effort}`, 'sandbox_workspace_write.network_access=true']);
      assert.deepEqual(child.args.filter((_, i, args) => args[i - 1] === '--add-dir'), [join(f.cwd, '.git')]);
      assert.equal(child.path, `${f.rust}/bin:/usr/bin:/bin`);
      assert.equal(child.cargoHome, join(f.sandbox, 'cache/cargo'));
      assert.deepEqual(child.tools, ['managed cargo', 'managed rustc', 'managed rustfmt']);
      assert.equal(child.cwd, f.cwd);
      assert.equal(child.input, 'Complete the admitted task on its branch.');
      assert.equal(child.home, join(f.sandbox, 'home'));
      assert.equal(child.githubCredentialPresent, false);
      assert.doesNotMatch(result.stdout + result.stderr, /synthetic-task210-token|synthetic-should-not-cross/);
      assert.match(result.stderr, /"childStarted":true/);
    }
  }
});

test('rendered launcher rejects unsafe syntax before credential access or child start', async t => {
  const f = await fixture(t); await rm(f.token);
  for (const [model, effort] of [
    ['', 'high'], ['--flag', 'high'], ['../model', 'high'], ['model/escape', 'high'],
    ['model with spaces', 'high'], ['m'.repeat(129), 'high'], ['model', 'e'.repeat(65)],
    ['model', ''], ['model', 'max;echo'], ['model', 'max\nlow'], ['model', 'max\n'], ['model\r\n', 'high'], ['model', 'max="low"'],
    ['model\0suffix', 'high'], ['ghp_' + 'Z'.repeat(32), 'high']
  ]) {
    assert.ok(!safeModel(model) || !safeEffort(effort));
    // NUL is rejected by the OS argument API before a process can start.
    if (model.includes('\0')) continue;
    for (const remediation of [false, true]) await assert.rejects(f.run(model, effort, remediation), error => {
      assert.equal(error.code, 64);
      assert.match(error.stderr, /CODEX_LAUNCHER_ARGUMENT_VALUE_INVALID/);
      assert.match(error.stderr, /"childStarted":false/);
      assert.doesNotMatch(error.stderr, /ACCESS_TOKEN_UNAVAILABLE/);
      return true;
    });
  }
});

test('rendered launcher still rejects outside workspaces and escaping input symlinks', async t => {
  const f = await fixture(t);
  await assert.rejects(f.run('future-model', 'ultra', false, tmpdir()), error => {
    assert.match(error.stderr, /PATH_OUTSIDE_WORK_ROOT/); return true;
  });
  await rm(f.input); await symlink('/etc/hostname', f.input);
  await assert.rejects(f.run('future-model', 'ultra'), error => {
    assert.match(error.stderr, /PATH_OUTSIDE_WORK_ROOT/);
    assert.match(error.stderr, /"childStarted":false/); return true;
  });
});
