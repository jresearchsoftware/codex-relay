import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { CONSUMER } from '../consumer.mjs';
import { fixture, memoryStore } from '../../controller/test/fixture.mjs';
import { runAttempt } from '../../controller/src/attempt.mjs';
import { admitEnvelope } from '../../controller/src/live-authority.mjs';
import { secretFree } from '../../controller/src/trusted-git.mjs';
import { WRITER_TOKEN_PERMISSIONS } from '../../controller/src/writer-auth.mjs';
import { buildCheckoutCodexEnvironment, buildCodexProcessSpec } from '../../runtime/src/codex-runtime.mjs';

test('dogfood trust: Writer can publish workflow bytes; ready does not certify candidate CI', async t => {
  const f = await fixture(t);
  assert.equal(WRITER_TOKEN_PERMISSIONS.workflows, 'write');
  const result = await runAttempt({ ...f, journal: memoryStore(), execute: async () => {
    await mkdir(join(f.cwd, '.github/workflows'), { recursive: true });
    await f.commit('.github/workflows/model-authored.yml', 'on: push\njobs:\n  candidate:\n    runs-on: self-hosted\n    steps:\n      - run: echo synthetic\n');
    return { version: 2, attemptId: f.envelope.attemptId, child: 'started', containment: 'reaped',
      result: { status: 'success', summary: 'Synthetic workflow change', validation: ['local fixture'] } };
  } });
  assert.equal(result.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
  assert.equal(result.head, await f.remoteHead());
  assert.equal(f.pushes(), 1);
  assert.match(f.comments.at(-1).body, /Native exact-head CI and GitHub mergeability were not evaluated/);
  f.run.head_branch = f.envelope.branch;
  await assert.rejects(admitEnvelope(f.api, f.admissionRequest), { code: 'OWNER_RUN_NOT_ADMITTED' });
});

test('publication scans transient introduced secrets even when absent from the candidate tip', async t => {
  const f = await fixture(t); await f.prepare(f.envelope);
  await f.commit('transient.txt', 'gh' + 'p_' + 'x'.repeat(30));
  await f.command(f.cwd, ['rm', 'transient.txt']);
  await f.command(f.cwd, ['commit', '-m', 'remove synthetic marker'], f.identity);
  const progress = await f.collect(f.envelope);
  await assert.rejects(f.broker.invoke({ operation: 'publish-progress', runId: 99,
    attemptId: f.envelope.attemptId, bundle: progress.bundle }), { code: 'SECRET_PUBLICATION_SCAN_FAILED' });
  assert.equal(f.pushes(), 0);
});

test('publication and candidate marker policies intentionally have different bounded coverage', () => {
  const samples = ['gh' + 'p_' + 'x'.repeat(30), 'github_' + 'pat_' + 'x'.repeat(40),
    '-----BEGIN ' + 'PRIVATE KEY-----', 'AK' + 'IA' + 'A'.repeat(16),
    'sk-' + 'proj-' + 'x'.repeat(45), 'ordinary synthetic text', 'unrecognized-example-password'];
  const publication = samples.map(value => { try { secretFree(value); return false; } catch (e) {
    assert.equal(e.code, 'SECRET_PUBLICATION_SCAN_FAILED'); return true;
  } });
  const root = fileURLToPath(new URL('../../', import.meta.url));
  const result = spawnSync('python3', ['-c', `import json, runpy, sys
base = runpy.run_path('contracts/src/secret-scan.py')['MARKER']
extra = runpy.run_path('scripts/check-candidate.py')['CANDIDATE_EXTRA_MARKERS']
print(json.dumps([[bool(base.search(s.encode())), bool(base.search(s.encode()) or extra.search(s.encode()))] for s in json.load(sys.stdin)]))`],
  { cwd: root, input: JSON.stringify(samples), encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr);
  const rows = JSON.parse(result.stdout);
  assert.deepEqual(publication, [true, true, true, false, false, false, false]);
  assert.deepEqual(rows.map(row => row[0]), publication);
  assert.deepEqual(rows.map(row => row[1]), [true, true, true, true, true, false, false]);
});

test('launcher isolation can be recreated after an env-reset boundary, without inherited credentials', async t => {
  const root = await mkdtemp(join(tmpdir(), 'relay-launcher-isolation-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const hostHome = join(root, 'host-home'); await mkdir(hostHome);
  await writeFile(join(hostHome, '.gitconfig'), '[user]\nname = host-identity\n[credential]\nhelper = host-helper\n');
  const sandbox = join(root, 'checkout'); await mkdir(sandbox);
  const beforeSudo = buildCheckoutCodexEnvironment({ PATH: process.env.PATH,
    HOME: hostHome, GITHUB_TOKEN: 'synthetic', CODEX_ACCESS_TOKEN: 'synthetic', SSH_AUTH_SOCK: '/synthetic/agent',
    NODE_OPTIONS: '--require=untrusted', GIT_CONFIG_COUNT: '99' }, { checkoutRoot: sandbox });
  assert.equal(beforeSudo.GIT_CONFIG_COUNT, '1');
  assert.equal(beforeSudo.GITHUB_TOKEN, undefined);
  assert.deepEqual(buildCodexProcessSpec({ args: ['exec'] }).args,
    ['-n', '-u', CONSUMER.runtimeUser, CONSUMER.paths.launcher, 'exec']);
  // Synthetic reset, NOT a sudoers or installed-launcher proof. The fixture
  // launcher supplies trusted config/checkout/identity after all env is lost.
  const fixtureCode = `import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
assert.equal(process.env.GIT_CONFIG_NOSYSTEM, undefined);
process.env.RELAY_CONSUMER_CONFIG = ${JSON.stringify(process.env.RELAY_CONSUMER_CONFIG)};
const { buildCheckoutCodexEnvironment } = await import(${JSON.stringify(new URL('../../runtime/src/codex-runtime.mjs', import.meta.url).href)});
const env = buildCheckoutCodexEnvironment(process.env, { checkoutRoot: ${JSON.stringify(sandbox)}, gitIdentity: ${JSON.stringify(CONSUMER.writerIdentity)} });
for (const key of ['GITHUB_TOKEN', 'CODEX_ACCESS_TOKEN', 'SSH_AUTH_SOCK', 'NODE_OPTIONS', 'RELAY_CONSUMER_CONFIG']) assert.equal(env[key], undefined);
assert.equal(env.GIT_CONFIG_NOSYSTEM, '1');
assert.equal(env.GIT_CONFIG_GLOBAL, '/dev/null');
assert.equal(env.GIT_CONFIG_SYSTEM, '/dev/null');
assert.equal(env.GIT_SSH_COMMAND, 'false');
assert.equal(env.GIT_TERMINAL_PROMPT, '0');
assert.equal(env.GIT_CONFIG_VALUE_0, ${JSON.stringify(sandbox)});
assert.equal(env.GIT_AUTHOR_NAME, ${JSON.stringify(CONSUMER.writerIdentity.name)});
assert.equal(env.HOME, ${JSON.stringify(join(sandbox, '.codex-sandbox/home'))});
assert.equal(env.CODEX_HOME, env.HOME);
for (const name of ['user.name', 'credential.helper']) {
  const checked = spawnSync('git', ['config', '--get', name], { cwd: ${JSON.stringify(sandbox)}, env, encoding: 'utf8' });
  assert.equal(checked.status, 1, checked.stderr); assert.equal(checked.stdout, '');
}`;
  const checked = spawnSync(process.execPath, ['--input-type=module', '-e', fixtureCode], {
    cwd: sandbox, env: { PATH: process.env.PATH, HOME: hostHome }, encoding: 'utf8' });
  assert.equal(checked.status, 0, checked.stderr);
});
