import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, writeFile, chmod, symlink, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { spawnSync } from 'node:child_process';
import { loadConsumer, validateConsumer, parseConsumerJson, selectRepositoryConsumer } from '../consumer-config.mjs';

const fixture = JSON.parse(await readFile(new URL('../fixtures/example.json', import.meta.url), 'utf8'));
const failure = action => { try { action(); assert.fail('expected rejection'); } catch (error) {
  assert.equal(error.code, 'CONSUMER_CONFIG_INVALID'); return error;
} };

test('configuration rejections identify deterministic checks without exposing raw values', () => {
  for (const [change, field, check] of [
    [{ version: 2 }, 'version', 'supported-version'],
    [{ runtimeUser: 'root' }, 'runtimeUser', 'non-root-unix-identity'],
    [{ baseBranch: '../private-source-value' }, 'baseBranch', 'safe-git-branch'],
    [{ writerApp: { ...fixture.writerApp, appId: 'private-source-value' } }, 'writerApp.appId', 'native-app-id'],
    [{ paths: { ...fixture.paths, credentialKeyFile: '/private-source-value;unsafe' } }, 'paths.credentialKeyFile', 'safe-absolute-path'],
    [{ validationNames: ['private-source-value;unsafe'] }, 'validationNames[0]', 'validation-name'],
  ]) {
    const error = failure(() => validateConsumer({ ...fixture, ...change }));
    assert.equal(error.observation.field, field);
    assert.equal(error.observation.check, check);
    assert.equal(typeof error.observation.expected, 'string');
    assert.ok(error.observation.observed.type);
    assert.ok(!JSON.stringify(error).includes('private-source-value'));
  }
  assert.deepEqual(failure(() => validateConsumer({ ...fixture, version: 2 })).observation.observed,
    { type: 'number', value: 2 });
  const duplicate = failure(() => parseConsumerJson('{"private-source-key":1,"private-source-key":2}'));
  assert.equal(duplicate.observation.check, 'unique-json-keys');
  assert.ok(!JSON.stringify(duplicate).includes('private-source-key'));
  assert.equal(failure(() => selectRepositoryConsumer(fixture, 'private-source-value')).observation.field, 'repositorySelection');
});

test('load retains original filesystem/parser causes only on the protected causal property', async t => {
  const root = await mkdtemp(join(tmpdir(), 'relay-consumer-causes-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const missing = join(root, 'private-missing-consumer.json');
  const absent = failure(() => loadConsumer(missing));
  assert.equal(absent.observation.check, 'config-lstat');
  assert.equal(absent.runtimeCause.code, 'ENOENT');
  assert.equal(absent.runtimeCause.path, missing);
  assert.ok(!Object.keys(absent).includes('runtimeCause'));
  assert.ok(!JSON.stringify(absent).includes(missing));
  const malformed = join(root, 'malformed.json');
  await writeFile(malformed, '{"private-source-value":', { mode: 0o600 });
  const invalid = failure(() => loadConsumer(malformed));
  assert.equal(invalid.observation.check, 'config-parse');
  assert.ok(invalid.runtimeCause instanceof SyntaxError);
  for (const pathname of [missing, malformed]) {
    const result = spawnSync(process.execPath, [new URL('../consumer.mjs', import.meta.url).pathname],
      { env: { ...process.env, RELAY_CONSUMER_CONFIG: pathname }, encoding: 'utf8' });
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /CONSUMER_CONFIG_INVALID/);
    for (const privateValue of [missing, 'private-source-value', 'runtimeCause']) assert.ok(!result.stderr.includes(privateValue), result.stderr);
  }
});

test('file protection and exact schema rules remain effective with diagnostic context', async t => {
  const root = await mkdtemp(join(tmpdir(), 'relay-consumer-mode-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const pathname = join(root, 'consumer.json');
  await writeFile(pathname, JSON.stringify(fixture), { mode: 0o600 });
  assert.deepEqual(loadConsumer(pathname), validateConsumer(fixture));
  await chmod(pathname, 0o620);
  assert.equal(failure(() => loadConsumer(pathname)).observation.check, 'protected-config-mode');
  const link = join(root, 'symlink.json'); await symlink(pathname, link);
  assert.equal(failure(() => loadConsumer(link)).observation.check, 'regular-config-file');
  const error = failure(() => validateConsumer({ ...fixture, unknown: 'private-source-value' }));
  assert.equal(error.observation.check, 'exact-fields');
  assert.equal(error.runtimeCause, undefined);
  assert.ok(!JSON.stringify(error).includes('private-source-value'));
});
