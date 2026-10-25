import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { consumerDigest, selectRepositoryConsumer } from '../../consumer/consumer-config.mjs';
import { createCompatibilityStore, historicalOperationContext, loadSerialPoolCompatibility,
  verifySerialPoolCompatibility } from '../src/serial-pool-compatibility.mjs';
import { serialPoolFixture } from './serial-pool-fixture.mjs';

const linux = process.platform === 'linux';
const operationId = 'abcdef12-1234-1234-1234-123456789abc';
const target = 'd'.repeat(40);

async function changedFixture(t, { snapshot = true, gate = true } = {}) {
  const f = await serialPoolFixture(t);
  const frozen = await readFile(f.consumerPath);
  if (snapshot) await f.write(join(f.consumerPath, '..', 'serial-pool-target-consumer-v1.json'), frozen, 0o644);
  const desired = structuredClone(f.installationConsumer);
  desired.defaultProfile = { cliModelId: 'gpt-6.1-sol', effort: 'medium' };
  const currentDigest = consumerDigest(desired);
  await f.write(f.consumerPath, desired, 0o644);
  if (gate) await f.write(f.poolGatePath, { version: 1, consumerDigest: currentDigest, phase: 'open',
    operationId: null, target: null, previousActive: null, verifiedRevision: null });
  const options = { ...f.options, consumer: selectRepositoryConsumer(desired, f.currentConsumer.repository) };
  return { ...f, desired, currentDigest, options, load: () => loadSerialPoolCompatibility(options) };
}

async function completeCurrent(f, { mismatchedJournal = false } = {}) {
  const complete = { ...f.current,
    controllerLifecycle: { version: 1, status: 'complete', child: 'not_started', containment: 'not_required' },
    outcome: { status: 'BLOCKED', head: null, prNumber: null, outcomeId: 200, bodySha256: 'a'.repeat(64) } };
  await f.currentStore.put(200, complete);
  await f.journal.put(200, { version: 2, envelope: { ...complete.envelope,
    ...(mismatchedJournal ? { authorityDigest: 'f'.repeat(64) } : {}) }, execution: null, outcome: complete.outcome });
  return complete;
}

test('Git profile update preserves immutable SERIAL target and completed pool history while new rows use live digest',
  { skip: !linux }, async t => {
    const f = await changedFixture(t); const old = await completeCurrent(f); const context = await f.load();
    assert.equal(context.receipt.target.consumerDigest, consumerDigest(f.installationConsumer));
    assert.notEqual(context.currentConsumerDigest, context.receipt.target.consumerDigest);
    assert.equal(context.currentConsumerDigest, f.currentDigest);
    const before = await readFile(join(context.current.storeRoot, '200.json'));
    const store = createCompatibilityStore({ compatibility: context, currentStore: f.currentStore, originalStore: f.originalStore });
    assert.deepEqual((await store.get(200)).envelope, old.envelope);
    assert.equal((await store.all()).length, f.records.length + 1);
    assert.equal((await store.scan()).find(row => row.runId === 200).error, null);
    await assert.rejects(store.put(200, old), { code: 'SERIAL_POOL_COMPATIBILITY_HISTORICAL_WRITE_FORBIDDEN' });
    await assert.rejects(store.withLock(200, () => assert.fail('historical mutation')),
      { code: 'SERIAL_POOL_COMPATIBILITY_HISTORICAL_WRITE_FORBIDDEN' });
    const next = { envelope: f.envelope(201, { consumerDigest: f.currentDigest, executionSlot: 'primary',
      profile: f.desired.defaultProfile }) };
    assert.equal(await store.reserve(201, next), true);
    assert.equal(historicalOperationContext(context, next, 'admit').kind, 'current');
    assert.deepEqual(await readFile(join(context.current.storeRoot, '200.json')), before);
  });

test('old pool rows without exact terminal journal proof remain unresolved after config transition',
  { skip: !linux }, async t => {
    const f = await changedFixture(t); await completeCurrent(f, { mismatchedJournal: true });
    const context = await f.load();
    const store = createCompatibilityStore({ compatibility: context, currentStore: f.currentStore, originalStore: f.originalStore });
    await assert.rejects(store.get(200), { code: 'SERIAL_POOL_COMPATIBILITY_CURRENT_CHANGED' });
    await assert.rejects(store.all(), { code: 'SERIAL_POOL_COMPATIBILITY_CURRENT_CHANGED' });
  });

test('completed prior manual pool result remains readable without manufacturing a worker journal',
  { skip: !linux }, async t => {
    const f = await changedFixture(t); await completeCurrent(f);
    const record = { envelope: f.envelope(202, { route: 'manual', executionSlot: 'primary',
      consumerDigest: f.receipt.target.consumerDigest,
      request: { schema_version: '3.0', kind: 'task-request' }, requestReference: { sha256: 'a'.repeat(64) } }),
    outcome: { status: 'BLOCKED', head: null, prNumber: null, outcomeId: 202, bodySha256: 'b'.repeat(64), manual: true },
    manualResultAuthorization: { id: 203, sha256: 'c'.repeat(64) } };
    await f.currentStore.put(202, record);
    const context = await f.load();
    const store = createCompatibilityStore({ compatibility: context, currentStore: f.currentStore, originalStore: f.originalStore });
    assert.deepEqual(await store.get(202), record);
    await assert.rejects(store.put(202, record), { code: 'SERIAL_POOL_COMPATIBILITY_HISTORICAL_WRITE_FORBIDDEN' });
    const unresolved = structuredClone(record); delete unresolved.manualResultAuthorization;
    await f.currentStore.put(202, unresolved);
    await assert.rejects(store.get(202), { code: 'SERIAL_POOL_COMPATIBILITY_CURRENT_CHANGED' });
  });

test('changed Git config cannot replace the immutable receipt target or dispense with its frozen snapshot',
  { skip: !linux }, async t => {
    const f = await changedFixture(t, { snapshot: false });
    await assert.rejects(f.load(), { code: 'SERIAL_POOL_COMPATIBILITY_TARGET_SNAPSHOT_REQUIRED' });
    await f.write(join(f.consumerPath, '..', 'serial-pool-target-consumer-v1.json'), f.desired, 0o644);
    await assert.rejects(f.load(), { code: 'SERIAL_POOL_COMPATIBILITY_RECEIPT_INVALID' });
  });

test('ordinary root loading binds the live pool gate and allows old digest only inside exact transition operation',
  { skip: !linux }, async t => {
    const f = await changedFixture(t, { gate: false });
    await assert.rejects(f.load(), { code: 'SERIAL_POOL_COMPATIBILITY_CURRENT_CHANGED' });
    const previousDigest = f.receipt.target.consumerDigest;
    const state = { version: 1, consumerDigest: previousDigest, phase: 'applying', operationId,
      target, previousActive: null, verifiedRevision: null };
    await f.write(f.poolGatePath, state);
    const transition = { operationId, previousDigest, target };
    const context = await loadSerialPoolCompatibility({ ...f.options, consumerTransition: transition });
    assert.equal((await verifySerialPoolCompatibility(context)).currentConsumerDigest, f.currentDigest);
    await assert.rejects(loadSerialPoolCompatibility({ ...f.options,
      consumerTransition: { ...transition, operationId: f.receipt.operationId } }),
    { code: 'SERIAL_POOL_COMPATIBILITY_CURRENT_CHANGED' });
    await f.write(f.poolGatePath, { ...state, phase: 'recovery-required' });
    await assert.rejects(loadSerialPoolCompatibility({ ...f.options, consumerTransition: transition }),
      { code: 'SERIAL_POOL_COMPATIBILITY_CURRENT_CHANGED' });
    await f.write(f.poolGatePath, { ...state, consumerDigest: f.currentDigest });
    assert.ok(await f.load());
  });

test('frozen target does not authorize changes to live resource paths or Unix identities',
  { skip: !linux }, async t => {
    const f = await changedFixture(t);
    const desired = structuredClone(f.desired); desired.runtimeUser = 'foreign-runtime';
    desired.executionSlots.find(slot => slot.id === 'primary').runtimeUser = desired.runtimeUser;
    await f.write(f.consumerPath, desired, 0o644);
    await assert.rejects(loadSerialPoolCompatibility({ ...f.options, consumer: undefined }),
      { code: 'SERIAL_POOL_COMPATIBILITY_IDENTITY_CHANGED' });
  });
