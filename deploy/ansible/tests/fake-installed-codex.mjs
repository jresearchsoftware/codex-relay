#!/usr/bin/node --experimental-default-type=module
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { qualifyRustDevelopment } from './rust-development-probe.mjs';
if (process.argv[2] === '--version') {
  process.stdout.write('codex-cli 0.154.0\n');
  process.exit(0);
}
const chunks = [];
for await (const chunk of process.stdin) chunks.push(chunk);
const input = Buffer.concat(chunks).toString('utf8');
const cwd = process.cwd();
const smoke = input.includes('Owner-authorized non-routing general runner smoke.');
if (!smoke) assert.match(input, /Маркер UTF-8/);
assert.equal(process.getuid(), 24002);
assert.equal(process.getgid(), 24002);
assert.ok(process.getgroups().includes(24000));
assert.equal(process.env.CODEX_ACCESS_TOKEN, 'fixture-only-credential');
for (const key of ['GITHUB_TOKEN', 'OPENAI_API_KEY', 'SSH_AUTH_SOCK', 'NODE_OPTIONS', 'workflowReadToken']) assert.equal(process.env[key], undefined);
assert.equal(process.env.CODEX_HOME, `${cwd}/.codex-sandbox/home`);
assert.equal(process.env.HOME, process.env.CODEX_HOME);
writeFileSync(`${process.env.HOME}/child-write-probe`, 'writable');
for (const [key, directory] of Object.entries({ XDG_CONFIG_HOME: 'config', XDG_CACHE_HOME: 'cache', XDG_DATA_HOME: 'data', XDG_STATE_HOME: 'state' })) {
  assert.equal(process.env[key], `${cwd}/.codex-sandbox/${directory}`);
  writeFileSync(`${process.env[key]}/child-write-probe`, 'writable');
}
assert.equal(process.env.TMPDIR, `${cwd}/.codex-sandbox/tmp`);
assert.equal(process.env.GIT_SSH_COMMAND, 'false');
const [, model = smoke ? 'gpt-6-astra' : 'gpt-5.6-luna', effort = smoke ? 'low' : 'high'] = input.match(/fixture-profile=([A-Za-z0-9._-]+)\/([A-Za-z0-9._-]+)/) ?? [];
assert.deepEqual(process.argv.slice(2), ['exec', '--json', '--sandbox', 'workspace-write', '--add-dir', `${cwd}/.git`,
  '--output-schema', `${cwd}/.codex-sandbox/codex-result-schema.json`, '--model', model, '-c', `model_reasoning_effort=${effort}`,
  '-c', 'sandbox_workspace_write.network_access=true', '--cd', cwd, '-']);
assert.equal(JSON.parse(readFileSync(`${cwd}/.codex-sandbox/codex-result-schema.json`)).properties.status.enum[0], 'success');
if (input.includes('fixture-mode=rust-development')) {
  try {
    qualifyRustDevelopment(cwd, JSON.parse(readFileSync('/run/managed-rust-proof.json', 'utf8')));
  } catch (error) {
    // Surface the actual command/stage and causal stderr, never Node's full
    // exec error object (which includes raw buffers). Use the installed redactor.
    const detail = error.rustDiagnostic ?? { stage: 'rust-contract', detail: error.message };
    const { sanitizeDiagnosticText } = await import('/opt/codex-relay/codex-runtime/relay-codex-diagnostic.mjs');
    process.stderr.write(`RUST_DEVELOPMENT_PROOF_FAILED ${sanitizeDiagnosticText(JSON.stringify(detail), process.env.CODEX_ACCESS_TOKEN)}\n`);
    process.exit(1);
  }
  process.stdout.write(JSON.stringify({ status: 'success', summary: 'managed-rust-development-qualified',
    validation: ['MANAGED_RUST_DEVELOPMENT_PROOF_PASS'], blockedReason: '' }) + '\n');
  process.exit(0);
}
if (smoke) {
  assert.equal(execFileSync('git', ['remote'], { encoding: 'utf8' }), '');
  assert.equal(execFileSync('git', ['config', 'protocol.allow'], { encoding: 'utf8' }).trim(), 'never');
  assert.equal(readFileSync('SMOKE.txt', 'utf8'), 'local non-routing smoke\n');
  // Even malicious backend stderr must not escape in the operator proof.
  process.stderr.write(`smoke backend diagnostic ${process.env.CODEX_ACCESS_TOKEN}\n`);
  process.stdout.write(JSON.stringify({ status: 'success', summary: 'general-runner-smoke-child-started', validation: [], blockedReason: '' }) + '\n');
  process.exit(0);
}
writeFileSync('docs/work.md', JSON.stringify({ uid: process.getuid(), input: true, umask: process.umask(), identity: process.env.GIT_AUTHOR_NAME, model, effort }) + '\n');
execFileSync('git', ['add', 'docs/work.md']);
execFileSync('git', ['commit', '-m', 'installed child task progress']);
if (input.includes('fixture-mode=child-failure')) {
  process.stderr.write(`controlled child failure ${process.env.CODEX_ACCESS_TOKEN}\n`);
  process.exitCode = 9;
} else if (input.includes('fixture-mode=invalid-result')) {
  process.stdout.write('{"type":"thread.started","thread_id":"fixture-thread"}\n');
} else {
  process.stdout.write(JSON.stringify({ status: 'success', summary: 'installed child progress', validation: ['fixture execution'], blockedReason: '' }) + '\n');
}
