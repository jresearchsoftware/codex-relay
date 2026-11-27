import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, mkdtemp, writeFile, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { promisify } from 'node:util';
import { execFile } from 'node:child_process';
import { validateConsumer, consumerDigest, configuredRepositories, selectRepositoryConsumer,
  resolveExecutionConsumer, resolveAppServerTarget, EXECUTION_PATH_NAMES } from '../consumer-config.mjs';

const example = JSON.parse(await readFile(new URL('../fixtures/example.json', import.meta.url), 'utf8'));
const targets = ['example-org/project-a', 'example-org/project-b'];
function multiple() {
  const value = structuredClone(example);
  delete value.repository;
  value.repositories = [...targets];
  return value;
}
function withSlots({ managed = false } = {}) {
  const value = multiple();
  value.executionSlots = [{ id: 'primary', runnerName: 'pool-primary', runnerUser: 'relay-runner',
    runtimeUser: value.runtimeUser, workGroup: 'relay-work',
    paths: Object.fromEntries(EXECUTION_PATH_NAMES.map(name => [name, value.paths[name]])) },
  { id: 'second', runnerName: 'pool-second', runnerUser: managed ? 'relay-runner' : 'relay-runner-two',
    runtimeUser: managed ? value.runtimeUser : 'relay-worker-two', workGroup: managed ? 'relay-work' : 'relay-work-two',
    paths: Object.fromEntries(EXECUTION_PATH_NAMES.map(name => [name, `/var/lib/relay-second/${name}`])) }];
  if (managed) value.generalRunnerPool = { desiredCapacity: 2 };
  return value;
}

test('legacy consumer preserves its digest, implicit selection and exact resource paths', () => {
  const value = validateConsumer(example);
  assert.equal(consumerDigest(value), '4f567bf7c7ba0ccb541fbd79fd0621846016f9e49b5309c506a6822c090d8fca');
  assert.deepEqual(configuredRepositories(value), [example.repository]);
  assert.equal(selectRepositoryConsumer(value), value);
  assert.equal(selectRepositoryConsumer(value, example.repository), value);
  assert.throws(() => selectRepositoryConsumer(value, targets[0]), { code: 'CONSUMER_CONFIG_INVALID' });
});

test('plural configuration requires one explicit configured repository without first-target fallback', () => {
  const value = validateConsumer(multiple());
  assert.deepEqual(configuredRepositories(value), targets);
  assert.ok(Object.isFrozen(value.repositories));
  for (const repository of [undefined, null, '', 'foreign/project', 'EXAMPLE-ORG/project-a']) {
    assert.throws(() => selectRepositoryConsumer(value, repository), { code: 'CONSUMER_CONFIG_INVALID' });
  }
  for (const repository of targets) {
    const selected = selectRepositoryConsumer(value, repository);
    assert.equal(selected.repository, repository);
    assert.ok(Object.isFrozen(selected.paths));
    assert.equal(Object.hasOwn(selected, 'repositories'), false);
    assert.equal(Object.hasOwn(selected, 'repositoryRuntimeUsers'), false);
    assert.doesNotThrow(() => validateConsumer(selected));
  }
});

test('a one-target plural installation still requires selection and retains a distinct digest', () => {
  const input = multiple(); input.repositories = [example.repository];
  const value = validateConsumer(input);
  assert.throws(() => selectRepositoryConsumer(value), { code: 'CONSUMER_CONFIG_INVALID' });
  assert.notEqual(consumerDigest(value), consumerDigest(validateConsumer(example)));
  assert.equal(selectRepositoryConsumer(value, example.repository).paths.attemptRoot,
    `${example.paths.attemptRoot}/repositories/${example.repository}`);
});

test('repository views isolate run and diagnostic roots while sharing protected installation inputs', () => {
  const value = validateConsumer(withSlots({ managed: true }));
  const [a, b] = targets.map(repository => selectRepositoryConsumer(value, repository));
  for (const name of ['workRoot', 'attemptRoot', 'diagnosticsRoot']) {
    assert.equal(a.paths[name], `${value.paths[name]}/repositories/${targets[0]}`);
    assert.equal(b.paths[name], `${value.paths[name]}/repositories/${targets[1]}`);
    assert.notEqual(a.paths[name], b.paths[name]);
    for (const slot of value.executionSlots) {
      assert.equal(resolveExecutionConsumer(a, slot.id).paths[name], `${slot.paths[name]}/repositories/${targets[0]}`);
      assert.equal(resolveExecutionConsumer(b, slot.id).paths[name], `${slot.paths[name]}/repositories/${targets[1]}`);
    }
  }
  for (const name of ['claimRoot', 'writerHelper', 'credentialEnv', 'credentialKeyFile', 'dispatch',
    'launcher', 'diagnosticsConfig', 'diagnosticsStore']) assert.equal(a.paths[name], value.paths[name]);
  assert.deepEqual(a.executionSlots.map(slot => slot.runnerName), b.executionSlots.map(slot => slot.runnerName));
  assert.equal(a.executionSlots.length, value.executionSlots.length);
  assert.equal(value.paths.workRoot, example.paths.workRoot);
});

test('repository runtime overrides replace only the shared default runtime identity', () => {
  for (const managed of [false, true]) {
    const input = withSlots({ managed });
    input.repositoryRuntimeUsers = { [targets[1]]: 'relay-project-b' };
    const value = validateConsumer(input);
    const a = selectRepositoryConsumer(value, targets[0]);
    const b = selectRepositoryConsumer(value, targets[1]);
    assert.equal(a.runtimeUser, value.runtimeUser);
    assert.equal(b.runtimeUser, 'relay-project-b');
    assert.equal(resolveExecutionConsumer(b, 'primary').runtimeUser, 'relay-project-b');
    assert.equal(resolveExecutionConsumer(b, 'second').runtimeUser, managed ? 'relay-project-b' : 'relay-worker-two');
    assert.equal(value.executionSlots[0].runtimeUser, value.runtimeUser);
    assert.ok(Object.isFrozen(value.repositoryRuntimeUsers));
  }
});

test('App Server selects the configured target for the admitted repository', () => {
  const target = { socketPath: '/run/example-codex/app-server.sock', workspaceRoot: '/srv/project-b' };
  const legacy = validateConsumer(example);
  assert.equal(resolveAppServerTarget(legacy), undefined);
  const singleton = validateConsumer({ ...example, repositoryAppServerTargets: { [example.repository]: target } });
  assert.deepEqual(resolveAppServerTarget(singleton), target);
  assert.equal(resolveAppServerTarget(singleton, targets[1]), undefined);
  const input = withSlots({ managed: true });
  input.repositoryAppServerTargets = { [targets[1]]: target };
  const value = validateConsumer(input);
  const a = selectRepositoryConsumer(value, targets[0]);
  const b = selectRepositoryConsumer(value, targets[1]);
  assert.equal(resolveAppServerTarget(value), undefined);
  assert.equal(resolveAppServerTarget(value, targets[0]), undefined);
  assert.equal(resolveAppServerTarget(value, 'toString'), undefined);
  assert.equal(resolveAppServerTarget(a), undefined);
  assert.equal(resolveAppServerTarget(a, targets[1]), undefined);
  assert.deepEqual(resolveAppServerTarget(resolveExecutionConsumer(b, 'second')), target);
  assert.ok(Object.isFrozen(resolveAppServerTarget(b)));
  assert.doesNotThrow(() => validateConsumer(b));
});

test('App Server target validation rejects foreign, invalid or overlapping paths', () => {
  const target = { socketPath: '/run/example-codex/app-server.sock', workspaceRoot: '/srv/project-b' };
  for (const invalid of [
    null, [], { '*': target }, { 'foreign/project': target }, { [targets[1].toUpperCase()]: target },
    { [targets[1]]: { ...target, projectId: 'native-project' } },
    { [targets[1]]: { ...target, socketPath: 'ws://localhost' } },
    { [targets[1]]: { ...target, socketPath: '/' + 'a'.repeat(107) } },
    { [targets[1]]: { ...target, workspaceRoot: '/' } },
    { [targets[1]]: { ...target, workspaceRoot: '/srv/project-b/../other' } },
    { [targets[1]]: { ...target, workspaceRoot: '/run/example-codex' } }
  ]) {
    const value = { ...multiple(), repositoryAppServerTargets: invalid };
    assert.throws(() => validateConsumer(value), { code: 'CONSUMER_CONFIG_INVALID' });
  }
});

test('App Server socket and workspace changes alter the installation digest', () => {
  const input = multiple();
  const socketPath = '/run/example-codex/app-server.sock';
  const a = { socketPath, workspaceRoot: '/srv/project-a' };
  const b = { socketPath, workspaceRoot: '/srv/project-b' };
  input.repositoryAppServerTargets = { [targets[0]]: a, [targets[1]]: b };
  const digest = consumerDigest(validateConsumer(input));
  input.repositoryAppServerTargets = { [targets[1]]: { workspaceRoot: b.workspaceRoot, socketPath }, [targets[0]]: a };
  assert.equal(digest, consumerDigest(validateConsumer(input)));
  for (const delta of [{ socketPath: '/run/example-codex-2/app-server.sock' }, { workspaceRoot: '/srv/project-b-2' }]) {
    input.repositoryAppServerTargets[targets[1]] = { ...b, ...delta };
    assert.notEqual(digest, consumerDigest(validateConsumer(input)));
  }
});

test('plural config rejects ambiguous targets and unsafe or foreign runtime mappings', () => {
  for (const mutate of [
    c => { c.repository = example.repository; },
    c => { c.repositories = []; },
    c => { c.repositories = targets[0]; },
    c => { c.repositories = [targets[0], targets[0]]; },
    c => { c.repositories = [targets[0], targets[0].toUpperCase()]; },
    c => { c.repositories = ['owner/../project']; },
    c => { c.repositories = ['owner/..']; },
    c => { c.repositoryRuntimeUsers = null; },
    c => { c.repositoryRuntimeUsers = []; },
    c => { c.repositoryRuntimeUsers = { 'foreign/project': 'relay-worker' }; },
    c => { c.repositoryRuntimeUsers = { [targets[0]]: 'root' }; },
    c => { c.repositoryRuntimeUsers = { [targets[0]]: 'relay-runner' }; },
    c => { c.repositoryRuntimeUsers = { [targets[0]]: 'relay-worker-two' }; }
  ]) {
    const value = withSlots(); mutate(value);
    assert.throws(() => validateConsumer(value), { code: 'CONSUMER_CONFIG_INVALID' });
  }
  assert.throws(() => validateConsumer({ ...example, repositoryRuntimeUsers: {} }), { code: 'CONSUMER_CONFIG_INVALID' });
});

test('installation digest binds every target and runtime mapping while managed resize remains compatible', () => {
  const value = validateConsumer(withSlots({ managed: true }));
  const digest = consumerDigest(value);
  const resized = structuredClone(value); resized.generalRunnerPool.desiredCapacity = 1;
  assert.equal(consumerDigest(validateConsumer(resized)), digest);
  for (const mutate of [
    c => { c.repositories[1] = 'example-org/project-c'; },
    c => { c.repositoryRuntimeUsers = { [targets[1]]: 'relay-project-b' }; },
    c => { c.paths.claimRoot = '/var/lib/other-writer-claims'; }
  ]) {
    const changed = structuredClone(value); mutate(changed);
    assert.notEqual(consumerDigest(validateConsumer(changed)), digest);
  }
});

test('process bootstrap selects only trusted configured targets and hashes the full installation', async t => {
  const root = await mkdtemp(join(tmpdir(), 'relay-repository-config-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const pathname = join(root, 'consumer.json');
  const input = multiple();
  await writeFile(pathname, JSON.stringify(input), { mode: 0o644 });
  const env = { ...process.env, RELAY_CONSUMER_CONFIG: pathname };
  for (const name of ['RELAY_REPOSITORY', 'GITHUB_REPOSITORY', 'RELAY_EXECUTION_SLOT', 'RUNNER_NAME']) delete env[name];
  const source = `const m=await import(${JSON.stringify(new URL('../consumer.mjs', import.meta.url).href)});
    console.log(JSON.stringify({repository:m.CONSUMER.repository,digest:m.CONSUMER_DIGEST,
      repositories:m.INSTALLATION_CONSUMER.repositories,paths:m.CONSUMER.paths}));`;
  const run = async extra => JSON.parse((await promisify(execFile)(process.execPath,
    ['--input-type=module', '-e', source], { env: { ...env, ...extra } })).stdout);
  for (const repository of targets) {
    const result = await run({ RELAY_REPOSITORY: repository });
    assert.equal(result.repository, repository);
    assert.equal(result.digest, consumerDigest(validateConsumer(input)));
    assert.deepEqual(result.repositories, targets);
  }
  assert.equal((await run({ GITHUB_REPOSITORY: targets[1] })).repository, targets[1]);
  assert.equal((await run({ RELAY_REPOSITORY: targets[0], GITHUB_REPOSITORY: targets[1] })).repository, targets[0]);
  for (const extra of [{}, { RELAY_REPOSITORY: 'foreign/project' }, { GITHUB_REPOSITORY: 'foreign/project' }]) {
    await assert.rejects(run(extra), error => /CONSUMER_CONFIG_INVALID/.test(error.stderr));
  }
  await writeFile(pathname, JSON.stringify(example), { mode: 0o644 });
  const legacy = await run({ GITHUB_REPOSITORY: 'unrelated/ci-host' });
  assert.equal(legacy.repository, example.repository);
  assert.equal(legacy.paths.attemptRoot, example.paths.attemptRoot);
  await assert.rejects(run({ RELAY_REPOSITORY: 'foreign/project' }), error => /CONSUMER_CONFIG_INVALID/.test(error.stderr));
});
