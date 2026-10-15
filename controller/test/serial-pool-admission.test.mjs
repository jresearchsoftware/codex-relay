import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { CONSUMER_DIGEST } from '../../consumer/consumer.mjs';
import { createAdmissionControl } from '../src/admission-control.mjs';
import { createAttemptStore } from '../src/attempt-store.mjs';
import { REPOSITORY, VERSION } from '../src/execution-contract.mjs';

const operationId = '12345678-1234-1234-1234-123456789abc';
const target = 'a'.repeat(40);
const originalDigest = 'b'.repeat(64);

function record(runId, issueNumber, { digest = CONSUMER_DIGEST, status = 'active', slot } = {}) {
  return {
    envelope: { version: VERSION, repository: REPOSITORY, runId, attemptId: `run-${runId}`,
      consumerDigest: digest, route: 'auto', issueNumber, ...(slot ? { executionSlot: slot } : {}) },
    controllerLifecycle: { version: 1, status, ...(status === 'complete'
      ? { child: 'started', containment: 'reaped' } : {}) },
    ...(status === 'complete' ? { outcome: { status: 'BLOCKED', head: null, prNumber: null, outcomeId: runId } } : {})
  };
}

async function fixture(t) {
  const root = await mkdtemp(join(tmpdir(), 'relay-serial-pool-admission-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const originalStore = createAttemptStore(join(root, 'publication-v2'));
  const currentStore = createAttemptStore(join(root, 'publication-pool-v1'));
  const originalJournal = createAttemptStore(join(root, 'old-journals'));
  const currentJournal = createAttemptStore(join(root, 'new-journals'));
  const original = createAdmissionControl({ root, consumerDigest: originalDigest,
    store: originalStore, journal: originalJournal, protectedRoot: false });
  await original.initialize();
  await original.quiesce({ operationId, target });
  await original.drained({ operationId });
  await original.phase({ operationId, phase: 'applying' });
  const originalBytes = await readFile(join(root, 'admission-v1.json'));
  let inspections = 0;
  // The installed adapter delegates this inventory to the bound original
  // source/config in an isolated process. Here both real gates use durable
  // disjoint stores; complete original classification precedes every filter.
  const supplementalInventory = async ({ task = null, slot = null } = {}) => {
    inspections++;
    const complete = await original.status();
    const selected = new Set((await originalStore.all()).filter(({ envelope: e }) =>
      (task === null || e.issueNumber === task) && (slot === null || (e.executionSlot ?? 'primary') === slot))
      .map(({ envelope }) => envelope.runId));
    return { active: complete.active.filter(id => selected.has(id)), unknown: complete.unknown.filter(id => selected.has(id)) };
  };
  const options = { root, consumerDigest: CONSUMER_DIGEST, store: currentStore,
    journal: currentJournal, protectedRoot: false, stateName: 'admission-pool-v1.json', supplementalInventory };
  return { root, original, originalBytes, originalStore, currentStore, options,
    gate: createAdmissionControl(options), inspections: () => inspections };
}

test('new gate initialization and lifecycle preserve the sealed original gate and original records', async t => {
  const f = await fixture(t);
  const old = record(11, 41, { digest: originalDigest, status: 'complete' });
  await f.originalStore.put(11, old);
  const oldPath = join(f.root, 'publication-v2/11.json');
  const oldBytes = await readFile(oldPath);
  assert.equal((await f.gate.initialize()).phase, 'open');
  await f.gate.quiesce({ operationId, target });
  assert.equal((await f.gate.drained({ operationId })).drained, true);
  await f.gate.phase({ operationId, phase: 'verified', revision: target });
  await f.gate.resume({ operationId });
  assert.equal((await f.gate.read()).phase, 'open');
  assert.deepEqual(await readFile(join(f.root, 'admission-v1.json')), f.originalBytes);
  assert.deepEqual(await readFile(oldPath), oldBytes);
  assert.equal((await f.original.read()).phase, 'applying');
  assert.ok(f.inspections() >= 6);
});

test('both stores contribute pending Task and slot checks without conflating independent Tasks', async t => {
  const f = await fixture(t);
  await f.gate.initialize();
  await f.originalStore.put(11, record(11, 41, { digest: originalDigest }));
  await f.currentStore.put(22, record(22, 42, { slot: 'pool-2' }));
  assert.deepEqual((await f.gate.status()).active, [11, 22]);
  for (const task of [41, 42]) await assert.rejects(f.gate.assertTaskComplete(task), { code: 'PRIOR_EXECUTION_UNRESOLVED' });
  await f.gate.assertTaskComplete(43);
  for (const slot of ['primary', 'pool-2']) await assert.rejects(f.gate.assertSlotComplete(slot), { code: 'EXECUTION_SLOT_UNAVAILABLE' });
  await f.gate.assertSlotComplete('pool-3');
  await f.gate.quiesce({ operationId, target });
  assert.equal((await f.gate.drained({ operationId })).drained, false);
  await f.originalStore.put(11, record(11, 41, { digest: originalDigest, status: 'complete' }));
  await f.currentStore.put(22, record(22, 42, { slot: 'pool-2', status: 'complete' }));
  assert.equal((await f.gate.drained({ operationId })).drained, true);
});

test('unknown original containment remains visible and prevents drain or verified resume', async t => {
  const f = await fixture(t);
  await f.gate.initialize();
  const old = record(11, 41, { digest: originalDigest, status: 'complete' });
  old.controllerLifecycle.containment = 'unknown';
  await f.originalStore.put(11, old);
  assert.deepEqual((await f.gate.status()).unknown, [11]);
  await f.gate.quiesce({ operationId, target });
  await assert.rejects(f.gate.drained({ operationId }), { code: 'ADMISSION_DRAIN_UNKNOWN' });
  await f.gate.phase({ operationId, phase: 'recovery-required' });
  await f.gate.phase({ operationId, phase: 'applying' });
  await f.gate.phase({ operationId, phase: 'verified', revision: target });
  await assert.rejects(f.gate.resume({ operationId }), { code: 'ADMISSION_NOT_DRAINED' });
  assert.deepEqual(await readFile(join(f.root, 'admission-v1.json')), f.originalBytes);
});

test('unknown digest in either store fails complete classification before unrelated admission or gate reads', async t => {
  for (const old of [true, false]) await t.test(old ? 'original store' : 'current store', async t => {
    const f = await fixture(t);
    await f.gate.initialize();
    await (old ? f.originalStore : f.currentStore).put(33, record(33, 99, { digest: 'c'.repeat(64) }));
    for (const action of [() => f.gate.read(), () => f.gate.assertOpen(), () => f.gate.status(),
      () => f.gate.initialize(), () => f.gate.assertTaskComplete(41), () => f.gate.assertSlotComplete('primary'),
      () => f.gate.complete({ runId: 22, attemptId: 'run-22' })]) {
      await assert.rejects(action(), { code: 'ADMISSION_ATTEMPT_INVALID' });
    }
    assert.deepEqual(await readFile(join(f.root, 'admission-v1.json')), f.originalBytes);
  });
});

test('malformed unrelated current lifecycle cannot hide behind a filtered admission check', async t => {
  const f = await fixture(t);
  await f.gate.initialize();
  await f.currentStore.put(33, record(33, 99, { status: 'unrecognized' }));
  await assert.rejects(f.gate.assertTaskComplete(41), { code: 'ADMISSION_ATTEMPT_INVALID' });
  await assert.rejects(f.gate.assertSlotComplete('pool-2'), { code: 'ADMISSION_ATTEMPT_INVALID' });
});

test('compatibility verification failure precedes creation and mutation of a new gate', async t => {
  const f = await fixture(t);
  const gate = createAdmissionControl({ ...f.options, supplementalInventory: async () => {
    throw Object.assign(new Error('changed original record'), { code: 'SERIAL_POOL_ORIGINAL_RECORD_CHANGED' });
  } });
  await assert.rejects(gate.initialize(), { code: 'SERIAL_POOL_ORIGINAL_RECORD_CHANGED' });
  await assert.rejects(readFile(join(f.root, 'admission-pool-v1.json')), { code: 'ENOENT' });
  assert.deepEqual(await readFile(join(f.root, 'admission-v1.json')), f.originalBytes);
});

test('state selection is a fixed internal allowlist and legacy default retains its original file', async t => {
  const root = await mkdtemp(join(tmpdir(), 'relay-gate-state-name-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  await mkdir(join(root, 'records'));
  const options = { root, consumerDigest: CONSUMER_DIGEST,
    store: createAttemptStore(join(root, 'records')), journal: { get: async () => null }, protectedRoot: false };
  for (const stateName of ['../admission-v1.json', '/tmp/admission-v1.json', 'different.json', null]) {
    assert.throws(() => createAdmissionControl({ ...options, stateName }), { code: 'ADMISSION_CONFIG_INVALID' });
  }
  const gate = createAdmissionControl(options);
  await gate.initialize();
  assert.equal(JSON.parse(await readFile(join(root, 'admission-v1.json'), 'utf8')).consumerDigest, CONSUMER_DIGEST);
  await assert.rejects(readFile(join(root, 'admission-pool-v1.json')), { code: 'ENOENT' });
});
