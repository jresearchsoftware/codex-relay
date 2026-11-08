import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { consumerDigest, selectRepositoryConsumer } from '../../consumer/consumer-config.mjs';
import { createCompatibilityStore, historicalOperationContext, loadSerialPoolCompatibility,
  verifySerialPoolCompatibility } from '../src/serial-pool-compatibility.mjs';
import { serialPoolFixture } from './serial-pool-fixture.mjs';
import { createAdmissionControl, manualAdmissionComplete, completedAdmissionRecord } from '../src/admission-control.mjs';
import { manualAttemptHasConflictingActivity } from '../src/manual-attempt-disposition.mjs';
import { supplementOriginalInventory } from '../src/admission-cli.mjs';

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

test('old pool rows remain structurally readable without substituting for exact original terminal journal proof',
  { skip: !linux }, async t => {
    const f = await changedFixture(t); await completeCurrent(f, { mismatchedJournal: true });
    const context = await f.load();
    const store = createCompatibilityStore({ compatibility: context, currentStore: f.currentStore, originalStore: f.originalStore });
    const record = await store.get(200);
    assert.ok((await store.all()).some(row => row.envelope.runId === 200));
    assert.equal(await completedAdmissionRecord(record, f.journal), false);
    await assert.rejects(store.put(200, record), { code: 'SERIAL_POOL_COMPATIBILITY_HISTORICAL_WRITE_FORBIDDEN' });
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
    assert.deepEqual(await store.get(202), unresolved);
    assert.equal(await manualAttemptHasConflictingActivity(unresolved, { journal: f.journal }), true);
  });

test('retained pool refusals and both original v3 manual receipts remain read-only after a Git profile change',
  { skip: !linux }, async t => {
    const f = await changedFixture(t); await completeCurrent(f);
    const envelope = (runId, overrides = {}) => f.envelope(runId, { route: 'manual', executionSlot: 'primary',
      consumerDigest: f.receipt.target.consumerDigest, ...overrides });
    const outcome = runId => ({ status: 'BLOCKED', head: null, prNumber: null, outcomeId: runId + 1000,
      bodySha256: 'b'.repeat(64) });
    const admissionBlock = { code: 'AUTHORITY_TASK_REQUEST_REQUIRED' };
    const rejected = { envelope: envelope(203, { request: null, authorityDigest: null, branch: null, startHead: null,
      admissionBlock }), admissionBlock, outcome: outcome(203) };
    const authorized = { envelope: envelope(204, { request: { schema_version: '3.0', kind: 'task-request' },
      requestReference: { sha256: 'a'.repeat(64) } }), outcome: { ...outcome(204), manual: true },
    manualResultAuthorization: { id: 1204, sha256: 'c'.repeat(64) } };
    delete authorized.outcome.bodySha256;
    const direct = { envelope: envelope(205, { request: { schema_version: '3.0', kind: 'task-request' },
      requestReference: { sha256: 'a'.repeat(64) } }), outcome: { ...outcome(205), manual: true },
    manualSubmission: { sha256: 'd'.repeat(64), parent: { kind: 'issue', number: 42 }, rendererVersion: 'human-v1' },
    commentBodies: { outcome: { number: 42, sha256: 'b'.repeat(64), rendererVersion: 'human-v1' } } };
    const sealedRejection = structuredClone(rejected);
    Object.assign(sealedRejection.envelope, { runId: 206, attemptId: 'run-206' });
    delete sealedRejection.outcome.bodySha256;
    sealedRejection.commentBodies = { outcome: { number: 42, sha256: 'e'.repeat(64), rendererVersion: 'human-v1' } };
    const records = [rejected, authorized, direct, sealedRejection];
    for (const record of records) await f.currentStore.put(record.envelope.runId, record);
    const context = await f.load();
    const store = createCompatibilityStore({ compatibility: context, currentStore: f.currentStore, originalStore: f.originalStore });
    const path = id => join(context.current.storeRoot, `${id}.json`);
    const before = await Promise.all(records.map(record => readFile(path(record.envelope.runId))));
    const journalBefore = await readFile(join(f.at(f.currentConsumer.paths.attemptRoot), '200.json'));
    assert.equal((await store.all()).length, f.records.length + 5);
    const scanned = await store.scan();
    for (const [index, record] of records.entries()) {
      const id = record.envelope.runId;
      assert.deepEqual(await store.get(id), record);
      assert.equal(scanned.find(row => row.runId === id).error, null);
      assert.equal(await f.journal.get(id), null);
      await assert.rejects(store.put(id, record), { code: 'SERIAL_POOL_COMPATIBILITY_HISTORICAL_WRITE_FORBIDDEN' });
      await assert.rejects(store.reserve(id, record), { code: 'SERIAL_POOL_COMPATIBILITY_HISTORICAL_WRITE_FORBIDDEN' });
      await assert.rejects(store.withLock(id, () => assert.fail('historical manual mutation')),
        { code: 'SERIAL_POOL_COMPATIBILITY_HISTORICAL_WRITE_FORBIDDEN' });
      assert.deepEqual(await readFile(path(id)), before[index]);
    }
    assert.deepEqual(await readFile(join(f.at(f.currentConsumer.paths.attemptRoot), '200.json')), journalBefore);
    const malformed = [
      [rejected, record => { record.handoffComplete = true; }],
      [rejected, record => { record.envelope.admissionBlock = { code: 'OTHER_REFUSAL' }; }],
      [authorized, record => { record.commentBodies = {}; }],
      [authorized, record => { record.manualSubmission = null; }],
      [authorized, record => { record.envelope.request.schema_version = '4.0'; }],
      [direct, record => { record.manualSubmission.publishedResult = null; }],
      [direct, record => { record.commentBodies.outcome.sha256 = 'f'.repeat(64); }],
      [direct, record => { record.envelope.request.schema_version = '4.0'; }],
      [direct, record => { delete record.outcome; record.handoffComplete = true; }],
      [sealedRejection, record => { record.commentBodies.outcome.number = 43; }],
      [sealedRejection, record => { record.commentBodies.outcome.sha256 = 'invalid'; }],
      [sealedRejection, record => { record.outcome.bodySha256 = 'invalid'; }]
    ];
    for (const [original, mutate] of malformed) {
      const record = structuredClone(original); mutate(record); const id = record.envelope.runId;
      await f.currentStore.put(id, record); const observed = await readFile(path(id));
      assert.deepEqual(await store.get(id), record);
      assert.ok((await store.all()).some(row => row.envelope.runId === id));
      assert.equal((await store.scan()).find(row => row.runId === id).error, null);
      assert.equal(await manualAttemptHasConflictingActivity(record, { journal: f.journal }), true);
      await assert.rejects(store.put(id, record), { code: 'SERIAL_POOL_COMPATIBILITY_HISTORICAL_WRITE_FORBIDDEN' });
      assert.deepEqual(await readFile(path(id)), observed);
      assert.deepEqual(await readFile(join(f.at(f.currentConsumer.paths.attemptRoot), '200.json')), journalBefore);
      await f.currentStore.put(id, original);
    }
    // Effect classification is separate from historical result completeness.
    // The original manual handoff remains without an Outcome and holds no effect.
    const supplementalInventory = async () => supplementOriginalInventory({ active: [], unknown: [] },
      await store.all(), { journal: f.journal });
    assert.deepEqual((await supplementalInventory()).unknown, []);
    const admission = createAdmissionControl({ root: dirname(f.poolGatePath), stateName: 'admission-pool-v1.json',
      consumerDigest: f.currentDigest, store: { all: async () => [] }, journal: f.journal,
      protectedRoot: false, supplementalInventory });
    await admission.quiesce({ operationId, target }); await admission.drained({ operationId });
    await admission.phase({ operationId, phase: 'applying' });
    await admission.checkConsumerTransition({ operationId, target });
    assert.equal((await f.originalStore.get(100)).outcome, undefined);
    for (const [index, record] of records.entries())
      assert.deepEqual(await readFile(path(record.envelope.runId)), before[index]);
    assert.deepEqual(await readFile(join(f.at(f.currentConsumer.paths.attemptRoot), '200.json')), journalBefore);
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
