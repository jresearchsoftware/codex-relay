import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, rename, rm, symlink, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { createCompatibilityStore, invokeOriginalReader } from '../src/serial-pool-compatibility.mjs';
import { historicalProgram } from '../src/serial-pool-program.mjs';
import { serialPoolFixture } from './serial-pool-fixture.mjs';

const linux = process.platform === 'linux';
async function fixture(t, options = {}) {
  const f = await serialPoolFixture(t, options); const compatibility = await f.load();
  const store = createCompatibilityStore({ compatibility, currentStore: f.currentStore, originalStore: f.originalStore });
  return { ...f, compatibility, store };
}

for (const damage of ['missing', 'corrupt', 'blocked-lifecycle']) {
  test(`sealed unrelated history does not block an independent managed attempt (${damage})`, { skip: !linux }, async t => {
    const f = await fixture(t); const original = join(f.compatibility.original.storeRoot, '99.json');
    const receipt = await readFile(f.receiptPath); const gate = await readFile(f.gatePath);
    if (damage === 'missing') await rm(original);
    if (damage === 'corrupt') await writeFile(original, '{ invalid');
    if (damage === 'blocked-lifecycle') await f.originalStore.put(99, { ...f.records[0], outcome: null,
      controllerLifecycle: { version: 1, status: 'unrecognized' } });
    assert.deepEqual(await f.store.get(200), f.current);
    await f.store.put(200, { ...f.current, collection: { clean: true } });
    const next = { envelope: { ...f.current.envelope, runId: 201, attemptId: 'run-201', executionSlot: 'pool-2' } };
    assert.equal(await f.store.reserve(201, next), true);
    assert.equal(await f.store.reserve(201, next), false);
    assert.deepEqual(await invokeOriginalReader(f.compatibility, { operation: 'inventory', slot: 'pool-2', resourceOnly: true }),
      { active: [], unknown: [] });
    await assert.rejects(invokeOriginalReader(f.compatibility, { operation: 'inventory', slot: 'primary' }));
    assert.deepEqual(await readFile(f.receiptPath), receipt); assert.deepEqual(await readFile(f.gatePath), gate);
    await assert.rejects(f.store.put(99, f.records[0]), { code: 'SERIAL_POOL_COMPATIBILITY_HISTORICAL_WRITE_FORBIDDEN' });
  });
}

test('scoped current operations preserve corrupt and incompatible unrelated rows for inspection', { skip: !linux }, async t => {
  const f = await fixture(t); const corrupt = join(f.compatibility.current.storeRoot, '201.json');
  await writeFile(corrupt, '{ invalid', { mode: 0o600 });
  await f.currentStore.put(202, { envelope: { ...f.current.envelope, runId: 202, attemptId: 'run-202', consumerDigest: 'f'.repeat(64) } });
  const before = await readFile(corrupt);
  assert.deepEqual(await f.store.get(200), f.current);
  await f.store.put(200, { ...f.current, collection: { clean: true } });
  const next = { envelope: { ...f.current.envelope, runId: 203, attemptId: 'run-203', executionSlot: 'pool-2' } };
  assert.equal(await f.store.reserve(203, next), true);
  const rows = await f.store.scan();
  assert.ok(rows.find(row => row.runId === 201).error);
  assert.equal(rows.find(row => row.runId === 202).error, 'SERIAL_POOL_COMPATIBILITY_CURRENT_CHANGED');
  await assert.rejects(f.store.get(201)); await assert.rejects(f.store.get(202)); await assert.rejects(f.store.all());
  assert.deepEqual(await readFile(corrupt), before);
});

test('current historical-program dispatch does not classify unrelated logical state', { skip: !linux }, async t => {
  const f = await fixture(t);
  await f.originalStore.put(99, { ...f.records[0], controllerLifecycle: { version: 1, status: 'unrecognized' } });
  const result = await historicalProgram({ kind: 'writer', request: { operation: 'preflight', runId: 200 },
    consumer: f.currentConsumer, consumerPath: f.consumerPath, load: async () => f.compatibility,
    invoke: async () => assert.fail('A current run must not invoke an original program') });
  assert.deepEqual(result, { handled: false });
});

test('unsealed original ownership remains a global migration boundary', { skip: !linux }, async t => {
  const f = await fixture(t); await f.originalStore.put(103, { envelope: f.envelope(103) });
  await assert.rejects(f.store.get(200), { code: 'SERIAL_POOL_COMPATIBILITY_RUN_SET_CHANGED' });
  await assert.rejects(invokeOriginalReader(f.compatibility, { operation: 'inventory', slot: 'pool-2' }),
    { code: 'SERIAL_POOL_COMPATIBILITY_RUN_SET_CHANGED' });
});

test('a missing sealed record may recover only immutable ownership from its exact original journal', { skip: !linux }, async t => {
  const f = await fixture(t); const original = join(f.compatibility.original.storeRoot, '102.json');
  await rm(original);
  const row = (await f.store.scan()).find(row => row.runId === 102);
  assert.equal(row.record, null); assert.equal(row.error, 'ATTEMPT_RECORD_MISSING');
  assert.deepEqual(row.envelope, f.records.find(record => record.envelope.runId === 102).envelope);
  assert.equal(row.outcome, undefined); assert.equal(row.admitted, undefined);
  const journal = await f.journal.get(102); journal.envelope.issueNumber = 85; await f.journal.put(102, journal);
  assert.equal((await f.store.scan()).find(row => row.runId === 102).envelope, undefined);
});

test('scoped plural lookup preserves the protected store-root boundary', { skip: !linux }, async t => {
  const f = await fixture(t, { repositories: ['example-org/sample-project', 'example-org/second'] });
  const original = f.compatibility.current.storeRoot; await rename(original, original + '-retained');
  await symlink(original + '-retained', original);
  await assert.rejects(f.store.get(200), { code: 'SERIAL_POOL_COMPATIBILITY_STORE_UNSAFE' });
});
