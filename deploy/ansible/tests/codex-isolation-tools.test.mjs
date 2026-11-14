import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, realpathSync } from 'node:fs';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { spawnSync } from 'node:child_process';
import { isolatedCodexProcess } from '../roles/relay_codex_runtime/files/relay-codex-isolation.mjs';

test('isolated namespace reconstructs only fixed public alternatives with resolved OS targets', () => {
  const spec = isolatedCodexProcess({ binary: '/usr/bin/node', packageRoot: '/usr/share', cwd: '/synthetic', toolchainRoot: '/usr', args: [] });
  assert.ok(!spec.args.includes('--ro-bind-try /etc/alternatives'));
  for (const name of ['cc', 'c++', 'awk']) {
    if (!existsSync(`/usr/bin/${name}`)) continue;
    const target = realpathSync(`/usr/bin/${name}`);
    if (!target.startsWith('/usr/')) continue;
    const index = spec.args.indexOf(`/etc/alternatives/${name}`);
    assert.ok(index > 1);
    assert.equal(spec.args[index - 2], '--symlink');
    assert.equal(spec.args[index - 1], target);
  }
  assert.ok(!spec.args.includes('/etc/ssl/openssl.cnf'));
});

test('real isolated tools compile, process text and generate a task-local OpenSSL fixture', async t => {
  if (!existsSync('/usr/bin/bwrap')) return t.skip('Bubblewrap is unavailable');
  const root = await mkdtemp(join(tmpdir(), 'relay-isolated-tools-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const config = join(root, 'openssl.cnf');
  await writeFile(config, '[req]\ndistinguished_name = req_distinguished_name\n[req_distinguished_name]\n');
  const spec = args => isolatedCodexProcess({ binary: '/usr/bin/sh', packageRoot: '/usr/share', cwd: root, toolchainRoot: '/usr', args });
  const probe = spec(['-c', 'true']);
  const available = spawnSync(probe.command, probe.args, { encoding: 'utf8' });
  if (available.status !== 0 && /(?:namespace|Operation not permitted|Permission denied)/i.test(available.stderr)) return t.skip('Host forbids Bubblewrap namespace creation; installed TEST qualification is required');
  assert.equal(available.status, 0, available.stderr);
  await writeFile(join(root, 'fixture.c'), 'int main(void) { return 0; }\n');
  const process = spec(['-c', 'cc fixture.c -o fixture && ./fixture && printf "ok\\n" | awk \'{print $1}\' && openssl req -new -newkey rsa:2048 -nodes -subj /CN=relay-test.invalid -keyout key.pem -out request.pem']);
  const result = spawnSync(process.command, process.args, { env: { PATH: '/usr/bin:/bin', OPENSSL_CONF: config }, encoding: 'utf8', timeout: 15000 });
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /ok/);
});
