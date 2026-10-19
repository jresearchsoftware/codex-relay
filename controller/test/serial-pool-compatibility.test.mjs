import test from 'node:test';
import assert from 'node:assert/strict';
import { chmod, lchown, link, mkdir, mkdtemp, readFile, readlink, rm, symlink, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { fileURLToPath } from 'node:url';
import { createAttemptStore } from '../src/attempt-store.mjs';
import { consumerDigest, selectRepositoryConsumer } from '../../consumer/consumer-config.mjs';
import { createCompatibilityStore, historicalOperationContext, invokeOriginalReader, loadSerialPoolCompatibility,
  protectedSourceTreeSha256, verifySerialPoolCompatibility } from '../src/serial-pool-compatibility.mjs';
import { serialPoolFixture as fixture } from './serial-pool-fixture.mjs';

const digest = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');
const linux = process.platform === 'linux';
const repositories = ['example-org/sample-project', 'example-org/second'];

test('plural migration binds raw installation digest and namespaces current records while retaining flat originals', { skip: !linux }, async t => {
  const f = await fixture(t, { repositories }); const ctx = await f.load();
  assert.equal(ctx.receipt.target.consumerDigest, consumerDigest(f.installationConsumer));
  assert.notEqual(ctx.receipt.target.consumerDigest, consumerDigest(f.currentConsumer));
  assert.equal(ctx.original.storeRoot, f.at(f.currentConsumer.paths.claimRoot + '/publication-v2'));
  assert.equal(ctx.current.gatePath, f.at(f.currentConsumer.paths.claimRoot + '/admission-pool-v1.json'));
  assert.ok(f.currentConsumer.paths.attemptRoot.endsWith('/repositories/' + repositories[0]));
  const before = await readFile(join(ctx.original.storeRoot, '99.json'));
  const otherStore = createAttemptStore(ctx.current.storeRoot, { repository: repositories[1], repositories, namespace: true });
  const other = { ...f.current, envelope: { ...f.current.envelope, repository: repositories[1], runId: 99, attemptId: 'run-99' } };
  await otherStore.put(99, other);
  const store = createCompatibilityStore({ compatibility: ctx, originalStore: f.originalStore, currentStore: f.currentStore });
  assert.equal((await store.all()).length, f.records.length + 2);
  assert.deepEqual((await store.get(99)).envelope, f.records[0].envelope);
  assert.deepEqual((await store.get(99, repositories[1])).envelope, other.envelope);
  const otherConsumer = selectRepositoryConsumer(f.installationConsumer, repositories[1]);
  const selected = await loadSerialPoolCompatibility({ ...f.options, consumer: otherConsumer });
  const otherComposite = createCompatibilityStore({ compatibility: selected, originalStore: f.originalStore, currentStore: otherStore });
  await otherComposite.put(99, { ...other, collection: { clean: true } });
  assert.equal((await otherComposite.get(99)).collection.clean, true);
  await assert.rejects(otherComposite.put(201, { envelope: { ...other.envelope, repository: repositories[0], runId: 201 } }));
  assert.deepEqual(await readFile(join(ctx.original.storeRoot, '99.json')), before);
  await assert.rejects(store.get(99, 'foreign/repository'), { code: 'ATTEMPT_REPOSITORY_MISMATCH' });
});

test('plural compatibility composes actual process-selected publication store for every configured repository', { skip: !linux }, async t => {
  const f = await fixture(t, { repositories });
  const moduleRoot = fileURLToPath(new URL('../..', import.meta.url));
  const driver = `
    import {pathToFileURL} from 'node:url';
    const input=JSON.parse(process.argv[1]);
    const {CONSUMER,CONSUMER_DIGEST}=await import(pathToFileURL(input.moduleRoot+'/consumer/consumer.mjs'));
    const {createAttemptStore,createPublicationStore}=await import(pathToFileURL(input.moduleRoot+'/controller/src/attempt-store.mjs'));
    const {loadSerialPoolCompatibility,createCompatibilityStore}=await import(pathToFileURL(input.moduleRoot+'/controller/src/serial-pool-compatibility.mjs'));
    const compatibility=await loadSerialPoolCompatibility({...input.options,consumer:CONSUMER});
    const store=createCompatibilityStore({compatibility,currentStore:createPublicationStore(compatibility.current.storeRoot),
      originalStore:createAttemptStore(compatibility.original.storeRoot,{repository:compatibility.receipt.repository})});
    await store.reserve(201,{envelope:{repository:CONSUMER.repository,consumerDigest:CONSUMER_DIGEST,runId:201,attemptId:'run-201'}});
    process.stdout.write(JSON.stringify({repository:(await store.get(201)).envelope.repository,count:(await store.all()).length}));`;
  for (const repository of repositories) {
    const output = await promisify(execFile)(process.execPath, ['--input-type=module', '-e', driver,
      JSON.stringify({ moduleRoot, options: { ...f.options, consumer: undefined } })], {
      env: { PATH: '/usr/bin:/bin', RELAY_CONSUMER_CONFIG: f.consumerPath, RELAY_REPOSITORY: repository } });
    assert.equal(JSON.parse(output.stdout).repository, repository);
    assert.ok(await readFile(join((await f.load()).current.storeRoot, 'repositories', repository, '201.json')));
  }
});

test('plural compatibility rejects hidden flat or unconfigured current records before a filtered lookup', { skip: !linux }, async t => {
  const f = await fixture(t, { repositories }); const ctx = await f.load();
  const store = createCompatibilityStore({ compatibility: ctx, originalStore: f.originalStore, currentStore: f.currentStore });
  await f.write(join(ctx.current.storeRoot, '202.json'), { envelope: { ...f.current.envelope, runId: 202 } });
  await assert.rejects(store.get(200), { code: 'SERIAL_POOL_COMPATIBILITY_CURRENT_CHANGED' });
  await rm(join(ctx.current.storeRoot, '202.json'));
  await f.write(join(ctx.current.storeRoot, 'repositories/foreign/repository/202.json'), { envelope: { ...f.current.envelope, runId: 202 } });
  await assert.rejects(store.get(200), { code: 'SERIAL_POOL_COMPATIBILITY_REPOSITORY_CHANGED' });
});

test('plural compatibility permits an empty new store but never a selected-view receipt digest', { skip: !linux }, async t => {
  const f = await fixture(t, { repositories }); const ctx = await f.load();
  await rm(ctx.current.storeRoot, { recursive: true });
  await mkdir(join(ctx.current.storeRoot, 'repositories'), { recursive: true, mode: 0o700 });
  const store = createCompatibilityStore({ compatibility: ctx, originalStore: f.originalStore, currentStore: f.currentStore });
  assert.equal((await store.all()).length, f.records.length);
  f.receipt.target.consumerDigest = consumerDigest(f.currentConsumer);
  await f.write(f.receiptPath, f.receipt, 0o644);
  await assert.rejects(f.load(), { code: 'SERIAL_POOL_COMPATIBILITY_RECEIPT_INVALID' });
});

test('plural migration does not accept changed runtime identity, trust fields or a missing original anchor', { skip: !linux }, async t => {
  const f = await fixture(t, { repositories });
  for (const change of [value => { value.runtimeUser = 'foreign-runtime'; },
    value => { value.writerApp.appId = '12345'; }, value => { value.paths.workRoot = '/var/lib/foreign'; },
    value => { value.repositoryRuntimeUsers = { [repositories[1]]: value.runtimeUser }; },
    value => { value.repositories = [repositories[1]]; }]) {
    const changed = structuredClone(f.installationConsumer); change(changed);
    await f.write(f.consumerPath, changed, 0o644);
    const receipt = structuredClone(f.receipt); receipt.target.consumerDigest = consumerDigest(changed);
    await f.write(f.receiptPath, receipt, 0o644);
    await assert.rejects(loadSerialPoolCompatibility({ ...f.options, consumer: undefined }));
  }
});
test('ordinary consumers without a compatibility receipt preserve existing path semantics', async t => {
  const root = await mkdtemp(join(tmpdir(), 'relay-no-compat-')); t.after(() => rm(root, { recursive: true, force: true }));
  assert.equal(await loadSerialPoolCompatibility({ consumerPath: join(root, 'test-consumer.json') }), null);
});

test('fixed retained bundle survives same-revision target snapshot changes and rejects mixed bundle paths', { skip: !linux }, async t => {
  const f = await fixture(t); const ctx = await f.load();
  assert.ok(ctx.original.sourceRoot.includes('/serial-compat-v1/'));
  await f.write(f.at(`/opt/${f.receipt.namespace}/releases/${f.receipt.original.revision}/deployment-config.json`), { consumer: f.currentConsumer });
  assert.deepEqual((await invokeOriginalReader(ctx, { operation: 'inventory' })).unknown, []);
  f.receipt.original.manifestPath = `/opt/${f.receipt.namespace}/releases/${f.receipt.original.revision}/artifact-manifest.json`;
  await f.write(f.receiptPath, f.receipt, 0o644);
  await assert.rejects(f.load(), { code: 'SERIAL_POOL_COMPATIBILITY_PATH_INVALID' });
});

test('previous canonical-release receipt paths remain readable through their exact original context', { skip: !linux }, async t => {
  const f = await fixture(t, { retained: false }); const ctx = await f.load();
  assert.ok(ctx.original.sourceRoot.includes('/releases/'));
  assert.deepEqual((await invokeOriginalReader(ctx, { operation: 'inventory' })).unknown, []);
});

test('configured deployment links retain exact canonical targets and original inventory', { skip: !linux }, async t => {
  const sourceLinks = { 'legacy/controller': 'controller', 'legacy/contracts': 'contracts' };
  const f = await fixture(t, { sourceLinks }); const ctx = await f.load();
  assert.deepEqual(ctx.receipt.original.sourceLinks, sourceLinks);
  assert.equal(await readlink(join(f.sourceRoot, 'legacy/controller')), f.originalSourceRoot + '/controller');
  assert.deepEqual((await invokeOriginalReader(ctx, { operation: 'inventory' })).unknown, []);
  assert.equal((await loadSerialPoolCompatibility({ ...f.options, privateChecks: false })).original.sourceRoot, f.sourceRoot);
  const before = await readFile(f.at(f.receipt.original.configPath));
  const config = JSON.parse(before); config.environment.compatibilityLinks = { 'legacy/controller': 'controller' };
  f.receipt.original.configSha256 = await f.write(f.at(f.receipt.original.configPath), config);
  const manifest = JSON.parse(await readFile(f.at(f.receipt.original.manifestPath)));
  manifest.deploymentConfigSha256 = f.receipt.original.configSha256;
  f.receipt.original.manifestSha256 = await f.write(f.at(f.receipt.original.manifestPath), manifest);
  await f.write(f.receiptPath, f.receipt, 0o644);
  assert.ok(await loadSerialPoolCompatibility({ ...f.options, privateChecks: false }));
  await assert.rejects(f.load(), { code: 'SERIAL_POOL_COMPATIBILITY_ORIGINAL_CHANGED' });
});

test('source tree hash uses distinct raw-target link rows and preserves the plain-file recipe', { skip: !linux }, async t => {
  const root = await mkdtemp(join(tmpdir(), 'relay-link-hash-')); t.after(() => rm(root, { recursive: true, force: true }));
  const sourceRoot = join(root, 'retained-source'); const ownerUid = process.getuid();
  const originalSourceRoot = '/opt/relay-compat/releases/' + 'a'.repeat(40) + '/reviewed-source';
  const target = originalSourceRoot + '/controller'; const bytes = Buffer.from('original bytes\n');
  await mkdir(join(sourceRoot, 'legacy'), { recursive: true, mode: 0o755 });
  await mkdir(join(root, target.slice(1)), { recursive: true, mode: 0o755 });
  await writeFile(join(sourceRoot, 'a.txt'), bytes, { mode: 0o644 });
  const hash = value => createHash('sha256').update(value).digest('hex');
  const plainRow = `a.txt\0${(0o644).toString(8)}\0${hash(bytes)}\n`;
  assert.equal(await protectedSourceTreeSha256(sourceRoot, { root, ownerUid }), hash(plainRow));
  await symlink(target, join(sourceRoot, 'legacy/controller'));
  const options = { root, ownerUid, sourceLinks: { 'legacy/controller': 'controller' }, originalSourceRoot };
  const linkRow = `legacy/controller\0symlink\0${hash(Buffer.from(target))}\n`;
  assert.equal(await protectedSourceTreeSha256(sourceRoot, options), hash(plainRow + linkRow));
  await assert.rejects(protectedSourceTreeSha256(sourceRoot, { root, ownerUid }),
    { code: 'SERIAL_POOL_COMPATIBILITY_SOURCE_LINK_INVALID' });
});

for (const change of ['changed-target', 'escape-target', 'relative-target', 'unknown-link', 'target-symlink', 'target-mode', 'missing-link']) {
  test(`configured source links reject ${change}`, { skip: !linux }, async t => {
    const f = await fixture(t, { sourceLinks: { 'legacy/controller': 'controller' } });
    const alias = join(f.sourceRoot, 'legacy/controller'); const target = f.at(f.originalSourceRoot + '/controller');
    if (change === 'changed-target') { await rm(alias); await symlink(f.originalSourceRoot + '/consumer', alias); }
    if (change === 'escape-target') { await rm(alias); await symlink('/etc', alias); }
    if (change === 'relative-target') { await rm(alias); await symlink('../controller', alias); }
    if (change === 'unknown-link') await symlink(f.originalSourceRoot + '/controller', join(f.sourceRoot, 'legacy/unknown'));
    if (change === 'target-symlink') { await rm(target, { recursive: true }); await symlink(join(f.sourceRoot, 'controller'), target); }
    if (change === 'target-mode') await chmod(target, 0o777);
    if (change === 'missing-link') await rm(alias);
    await assert.rejects(f.load());
  });
}

test('receipt link declarations use the exact bounded deployment alias contract', { skip: !linux }, async t => {
  const f = await fixture(t);
  for (const sourceLinks of [{}, [], null, { 'controller/alias': 'controller' }, { '/legacy/controller': 'controller' },
    { 'legacy/../controller': 'controller' }, { 'legacy//controller': 'controller' }, { 'legacy/controller/': 'controller' },
    { 'legacy': 'controller' }, { 'legacy/controller': 'deploy' }, { 'legacy/controller': '../controller' },
    Object.fromEntries(Array.from({ length: 9 }, (_, index) => [`legacy/alias-${index}`, 'controller']))]) {
    f.receipt.original.sourceLinks = sourceLinks; await f.write(f.receiptPath, f.receipt, 0o644);
    await assert.rejects(f.load(), { code: 'SERIAL_POOL_COMPATIBILITY_RECEIPT_INVALID' });
  }
});

test('declared aliases require the protected root owner even when target bytes match',
  { skip: !linux || process.getuid?.() !== 0 }, async t => {
    const root = await mkdtemp(join(tmpdir(), 'relay-link-owner-')); t.after(() => rm(root, { recursive: true, force: true }));
    const sourceRoot = join(root, 'source'); const originalSourceRoot = '/opt/relay-compat/releases/' + 'a'.repeat(40) + '/reviewed-source';
    await mkdir(join(sourceRoot, 'legacy'), { recursive: true, mode: 0o755 });
    await mkdir(join(root, originalSourceRoot.slice(1), 'controller'), { recursive: true, mode: 0o755 });
    await writeFile(join(sourceRoot, 'file'), 'original', { mode: 0o644 });
    await symlink(originalSourceRoot + '/controller', join(sourceRoot, 'legacy/controller'));
    const options = { root, ownerUid: 0, sourceLinks: { 'legacy/controller': 'controller' }, originalSourceRoot };
    assert.ok(await protectedSourceTreeSha256(sourceRoot, options));
    await lchown(join(sourceRoot, 'legacy/controller'), 65534, 65534);
    await assert.rejects(protectedSourceTreeSha256(sourceRoot, options), { code: 'SERIAL_POOL_COMPATIBILITY_SOURCE_LINK_INVALID' });
  });

test('original complete/legacy/manual/partial blocked records retain their exact context and bytes', { skip: !linux }, async t => {
  const f = await fixture(t); const before = await readFile(f.gatePath); const ctx = await f.load();
  const inventory = await invokeOriginalReader(ctx, { operation: 'inventory' });
  assert.deepEqual(inventory.active, []); assert.deepEqual(inventory.unknown, []);
  assert.equal(inventory.phase, 'applying'); assert.deepEqual(inventory.runs, f.receipt.original.runs);
  assert.deepEqual(await readFile(f.gatePath), before);
  const store = createCompatibilityStore({ compatibility: ctx, originalStore: f.originalStore, currentStore: f.currentStore });
  assert.deepEqual((await store.all()).map(record => record.envelope.runId), [99, 100, 101, 102, 200]);
  assert.deepEqual((await store.get(100)).envelope, f.records[1].envelope);
  assert.equal(historicalOperationContext(ctx, f.records[1], 'manual-outcome-direct').kind, 'original');
  assert.equal(historicalOperationContext(ctx, f.current, 'admit').kind, 'current');
  for (const operation of ['admit', 'preflight', 'publish-progress', 'handoff', 'dispatch', 'execute']) {
    assert.throws(() => historicalOperationContext(ctx, f.records[0], operation),
      { code: 'SERIAL_POOL_COMPATIBILITY_HISTORICAL_EXECUTION_FORBIDDEN' });
  }
  await assert.rejects(store.put(99, f.records[0]), { code: 'SERIAL_POOL_COMPATIBILITY_HISTORICAL_WRITE_FORBIDDEN' });
  await assert.rejects(store.reserve(99, f.records[0]), { code: 'SERIAL_POOL_COMPATIBILITY_HISTORICAL_EXECUTION_FORBIDDEN' });
  const filtered = createCompatibilityStore({ compatibility: ctx, originalStore: f.originalStore,
    currentStore: { ...f.currentStore, all: async () => [] } });
  await assert.rejects(filtered.all(), { code: 'SERIAL_POOL_COMPATIBILITY_STORE_VIEW_CHANGED' });
  await store.put(200, { ...f.current, collection: { clean: true } });
  assert.equal((await store.get(200)).collection.clean, true);
  const next = { envelope: f.envelope(201, { consumerDigest: ctx.receipt.target.consumerDigest, executionSlot: 'pool-2', step: 3 }) };
  assert.equal(await store.reserve(201, next), true);
  assert.equal(await store.reserve(201, next), false);
});

test('original validator rejects malformed sealed envelopes and missing legacy evidence remains unknown', { skip: !linux }, async t => {
  const f = await fixture(t); const ctx = await f.load();
  const changed = structuredClone(f.records[0]); changed.envelope.profile = { cliModelId: 'bad model', effort: 'high' };
  await f.originalStore.put(99, changed);
  f.receipt.original.runs[0].envelopeSha256 = digest(changed.envelope);
  await f.write(f.receiptPath, f.receipt, 0o644);
  const rebound = await f.load();
  await assert.rejects(invokeOriginalReader(rebound, { operation: 'inventory' }), { code: 'EXECUTION_ENVELOPE_INVALID' });
  // An adapter never manufactures a terminal journal to make drain pass.
  await f.originalStore.put(99, f.records[0]); f.receipt.original.runs[0].envelopeSha256 = digest(f.records[0].envelope);
  await f.write(f.receiptPath, f.receipt, 0o644);
  await rm(join(f.at(f.options.consumer.paths.attemptRoot), '102.json'));
  assert.deepEqual((await invokeOriginalReader(await f.load(), { operation: 'inventory' })).unknown, [102]);
  f.receipt.original.runs.reverse(); await f.write(f.receiptPath, f.receipt, 0o644);
  await assert.rejects(verifySerialPoolCompatibility(ctx), { code: 'SERIAL_POOL_COMPATIBILITY_RECEIPT_CHANGED' });
});

test('complete inventories reject extra, duplicate and altered historical/current identities', { skip: !linux }, async t => {
  const f = await fixture(t); const ctx = await f.load();
  const store = createCompatibilityStore({ compatibility: ctx, originalStore: f.originalStore, currentStore: f.currentStore });
  await f.originalStore.put(103, { envelope: f.envelope(103) });
  await assert.rejects(store.get(200), { code: 'SERIAL_POOL_COMPATIBILITY_RUN_SET_CHANGED' });
  await rm(join(ctx.original.storeRoot, '103.json'));
  await f.currentStore.put(99, { envelope: { ...f.current.envelope, runId: 99, attemptId: 'run-99' } });
  await assert.rejects(store.all(), { code: 'SERIAL_POOL_COMPATIBILITY_DUPLICATE_ATTEMPT' });
  await rm(join(ctx.current.storeRoot, '99.json'));
  await f.currentStore.put(200, { envelope: { ...f.current.envelope, consumerDigest: 'f'.repeat(64) } });
  await assert.rejects(store.all(), { code: 'SERIAL_POOL_COMPATIBILITY_CURRENT_CHANGED' });
  await f.currentStore.put(200, f.current);
  const changed = structuredClone(f.records[0]); changed.envelope.step = 9;
  await f.originalStore.put(99, changed);
  await assert.rejects(store.all(), { code: 'SERIAL_POOL_COMPATIBILITY_ENVELOPE_CHANGED' });
});

test('sealed ownership remains strict on primary while distinct managed resource ignores unrelated history', { skip: !linux }, async t => {
  const f = await fixture(t); const ctx = await f.load();
  const changed = structuredClone(f.records[0]); changed.envelope.issueNumber = 77;
  await f.originalStore.put(99, changed);
  assert.deepEqual(await invokeOriginalReader(ctx, { operation: 'inventory', task: 42, slot: 'pool-2' }), { active: [], unknown: [] });
  await assert.rejects(invokeOriginalReader(ctx, { operation: 'inventory', task: 42, slot: 'primary' }),
    { code: 'SERIAL_POOL_COMPATIBILITY_ENVELOPE_CHANGED' });
});

test('original active and unknown containment remain visible through the original classifier', { skip: !linux }, async t => {
  const f = await fixture(t); const ctx = await f.load(); const record = structuredClone(f.records[0]);
  record.controllerLifecycle = { version: 1, status: 'active' }; delete record.outcome;
  await f.originalStore.put(99, record);
  const active = await invokeOriginalReader(ctx, { operation: 'inventory', task: 42, slot: 'primary' });
  assert.deepEqual(active.active, [99]); assert.deepEqual(active.unknown, []);
  record.controllerLifecycle = { version: 1, status: 'complete', child: 'started', containment: 'unknown' };
  record.outcome = f.records[0].outcome; await f.originalStore.put(99, record);
  assert.deepEqual((await invokeOriginalReader(ctx, { operation: 'inventory' })).unknown, [99]);
});

test('source, configuration, original gate and target digest are independently immutable', { skip: !linux }, async t => {
  const f = await fixture(t);
  const sourcePath = join(f.sourceRoot, 'controller/src/execution-contract.mjs'); const sourceBytes = await readFile(sourcePath);
  await writeFile(sourcePath, Buffer.concat([sourceBytes, Buffer.from('\n// modified\n')]));
  await assert.rejects(f.load(), { code: 'SERIAL_POOL_COMPATIBILITY_SOURCE_CHANGED' });
  await writeFile(sourcePath, sourceBytes);
  const oldBytes = await readFile(f.oldConsumerPath); await writeFile(f.oldConsumerPath, Buffer.concat([oldBytes, Buffer.from('\n')]));
  await assert.rejects(f.load(), { code: 'SERIAL_POOL_COMPATIBILITY_CONSUMER_CHANGED' });
  await writeFile(f.oldConsumerPath, oldBytes);
  const gateBytes = await readFile(f.gatePath); await writeFile(f.gatePath, Buffer.concat([gateBytes, Buffer.from('\n')]));
  await assert.rejects(f.load(), { code: 'SERIAL_POOL_COMPATIBILITY_ORIGINAL_CHANGED' });
  await writeFile(f.gatePath, gateBytes);
  const changed = structuredClone(f.currentConsumer); changed.defaultProfile.effort = 'low';
  await f.write(f.consumerPath, changed, 0o644);
  await assert.rejects(f.load(), { code: 'SERIAL_POOL_COMPATIBILITY_CURRENT_CHANGED' });
});

test('public selection works without private checks; root publication revalidates private evidence', { skip: !linux }, async t => {
  const f = await fixture(t); const ctx = await loadSerialPoolCompatibility({ ...f.options, privateChecks: false });
  assert.equal(ctx.privateChecks, false);
  assert.equal(historicalOperationContext(ctx, f.records[0], 'publication-state').sourceRoot, f.sourceRoot);
  await writeFile(f.at(f.receipt.original.configPath), '{}\n');
  await assert.rejects(invokeOriginalReader(ctx, { operation: 'inventory' }), { code: 'SERIAL_POOL_COMPATIBILITY_ORIGINAL_CHANGED' });
});

test('capacity changes keep context while consumer identity changes remain blocked', { skip: !linux }, async t => {
  const f = await fixture(t); const resized = structuredClone(f.currentConsumer); resized.generalRunnerPool.desiredCapacity = 1;
  await f.write(f.consumerPath, resized, 0o644);
  assert.equal((await f.load()).receipt.target.consumerDigest, f.receipt.target.consumerDigest);
  f.receipt.original.runnerUid += 1; await f.write(f.receiptPath, f.receipt, 0o644);
  await assert.rejects(f.load(), { code: 'SERIAL_POOL_COMPATIBILITY_IDENTITY_CHANGED' });
});

for (const unsafe of ['receipt-mode', 'receipt-symlink', 'consumer-hardlink', 'source-symlink', 'store-symlink', 'parent-mode']) {
  test(`protected compatibility reads reject ${unsafe}`, { skip: !linux }, async t => {
    const f = await fixture(t);
    if (unsafe === 'receipt-mode') await chmod(f.receiptPath, 0o666);
    if (unsafe === 'receipt-symlink') { await rm(f.receiptPath); await symlink(f.consumerPath, f.receiptPath); }
    if (unsafe === 'consumer-hardlink') await link(f.oldConsumerPath, join(dirname(f.oldConsumerPath), 'alias'));
    if (unsafe === 'source-symlink') await symlink('/etc/passwd', join(f.sourceRoot, 'foreign'));
    if (unsafe === 'parent-mode') await chmod(dirname(f.receiptPath), 0o777);
    if (unsafe === 'store-symlink') {
      const ctx = await f.load(); const path = join(ctx.original.storeRoot, '99.json'); await rm(path);
      await symlink(join(ctx.original.storeRoot, '100.json'), path);
      await assert.rejects(invokeOriginalReader(ctx, { operation: 'inventory' })); return;
    }
    await assert.rejects(f.load());
  });
}
