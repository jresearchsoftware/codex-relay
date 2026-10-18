import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { CONSUMER_DIGEST } from '../../consumer/consumer.mjs';
import { createAdmissionControl } from '../src/admission-control.mjs';
import { createAttemptStore } from '../src/attempt-store.mjs';
import { REPOSITORY, VERSION } from '../src/execution-contract.mjs';

const operationId = '12345678-1234-1234-1234-123456789abc';
const head = 'a'.repeat(40);
const attempt = (runId, executionSlot = 'primary') => ({ envelope: { version: VERSION,
  repository: REPOSITORY, consumerDigest: CONSUMER_DIGEST, runId, attemptId: `run-${runId}`,
  route: 'auto', issueNumber: 85, executionSlot }, controllerLifecycle: { version: 1, status: 'active' } });
async function fixture(t) {
  const root = await mkdtemp(join(tmpdir(), 'relay-resource-isolation-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const store = createAttemptStore(join(root, 'records')); const journal = createAttemptStore(join(root, 'journal'));
  const gate = createAdmissionControl({ root, consumerDigest: CONSUMER_DIGEST, store, journal, protectedRoot: false });
  await gate.initialize(); return { root, store, journal, gate };
}

test('known malformed unrelated records hold only their Task and physical slot', async t => {
  const f = await fixture(t); const old = attempt(99);
  old.controllerLifecycle.status = 'unrecognized'; old.envelope.consumerDigest = 'f'.repeat(64);
  await f.store.put(99, old);
  await f.gate.assertOpen(); await f.gate.assertTaskComplete(141); await f.gate.assertSlotComplete('pool-2');
  await assert.rejects(f.gate.assertSlotComplete('primary'), { code: 'ADMISSION_ATTEMPT_INVALID' });
  await assert.rejects(f.gate.status(), { code: 'ADMISSION_ATTEMPT_INVALID' });
});

for (const clean of [true, false]) test(`contained preserved work releases its slot before publication (clean=${clean})`, async t => {
  const f = await fixture(t); const old = attempt(99);
  old.publicationIntent = { previous: null, head };
  await f.store.put(99, old);
  await f.journal.put(99, { version: VERSION, envelope: old.envelope,
    execution: { reserved: true, returned: true, child: 'started', containment: 'reaped' },
    collection: { head, clean, preserved: true } });
  await f.gate.assertSlotComplete('primary'); await f.gate.assertSlotComplete('pool-2');
  assert.deepEqual((await f.gate.status()).active, [99]);
  await f.gate.quiesce({ operationId, target: head });
  assert.equal((await f.gate.drained({ operationId })).drained, false);
  assert.equal((await f.store.get(99)).outcome, undefined);
  assert.deepEqual((await f.store.get(99)).publicationIntent, old.publicationIntent);
});

for (const failure of ['unknown-child', 'unknown-containment', 'no-preservation', 'different-envelope']) {
  test(`unproven resource release remains scoped (${failure})`, async t => {
    const f = await fixture(t); const old = attempt(99); await f.store.put(99, old);
    const saved = { version: VERSION, envelope: structuredClone(old.envelope),
      execution: { reserved: true, returned: true, child: 'started', containment: 'reaped' },
      collection: { head, clean: true, preserved: true } };
    if (failure === 'unknown-child') saved.execution.child = 'unknown';
    if (failure === 'unknown-containment') saved.execution.containment = 'unknown';
    if (failure === 'no-preservation') delete saved.collection.preserved;
    if (failure === 'different-envelope') saved.envelope.attemptId = 'run-100';
    await f.journal.put(99, saved);
    await f.gate.assertSlotComplete('pool-2');
    await assert.rejects(f.gate.assertSlotComplete('primary'), error => {
      assert.equal(error.code, 'EXECUTION_SLOT_UNAVAILABLE');
      assert.equal(error.details.resource, 'primary'); assert.deepEqual(error.details.active, [99]); return true;
    });
  });
}

test('manual handoff does not reserve a physical slot and trusted legacy completion needs no new journal field', async t => {
  const f = await fixture(t); const manual = attempt(99); manual.envelope.route = 'manual';
  const old = attempt(100); old.controllerLifecycle = { version: 1, status: 'complete', child: 'started', containment: 'reaped' };
  await f.store.put(99, manual); await f.store.put(100, old);
  await f.gate.assertSlotComplete('primary');
  assert.deepEqual(await f.store.get(100), old);
});

test('scanning preserves corrupt identities and unidentifiable records cannot be assumed to use another slot', async t => {
  const f = await fixture(t); await mkdir(join(f.root, 'records'), { recursive: true });
  await writeFile(join(f.root, 'records/99.json'), '{ broken');
  const rows = await f.store.scan();
  assert.deepEqual(rows, [{ runId: 99, repository: REPOSITORY, record: null, error: 'ATTEMPT_RECORD_UNREADABLE' }]);
  await assert.rejects(f.store.all(), { code: 'ATTEMPT_RECORD_UNREADABLE' });
  await assert.rejects(f.gate.assertSlotComplete('pool-2'), error => {
    assert.equal(error.code, 'ADMISSION_ATTEMPT_INVALID'); assert.equal(error.details.conflictingRunId, 99); return true;
  });
});

test('an unreadable journal reports the exact held resource and does not affect another slot', async t => {
  const f = await fixture(t); await f.store.put(99, attempt(99));
  await mkdir(join(f.root, 'journal'), { recursive: true }); await writeFile(join(f.root, 'journal/99.json'), '{ broken');
  await f.gate.assertSlotComplete('pool-2');
  await assert.rejects(f.gate.assertSlotComplete('primary'), error => {
    assert.equal(error.code, 'ADMISSION_RESOURCE_EVIDENCE_UNREADABLE');
    assert.deepEqual(error.details, { conflictingRunId: 99, repository: REPOSITORY,
      resource: 'primary', cause: 'ATTEMPT_RECORD_UNREADABLE' }); return true;
  });
});

test('parseable records without an execution identity remain explicit uncertainty', async t => {
  const f = await fixture(t); await mkdir(join(f.root, 'records'), { recursive: true });
  await writeFile(join(f.root, 'records/99.json'), '{}');
  assert.equal((await f.store.scan())[0].error, 'ATTEMPT_RECORD_INVALID');
  await assert.rejects(f.gate.assertSlotComplete('pool-2'), error => {
    assert.equal(error.code, 'ADMISSION_ATTEMPT_INVALID'); assert.equal(error.details.conflictingRunId, 99); return true;
  });
});

test('a corrupt other-repository namespace does not block a known independent Task check', async t => {
  const f = await fixture(t); const other = 'example-org/another';
  const store = createAttemptStore(join(f.root, 'namespaced'), { repositories: [REPOSITORY, other], namespace: true });
  const otherRoot = join(f.root, 'namespaced/repositories', other); await mkdir(otherRoot, { recursive: true });
  await writeFile(join(otherRoot, '99.json'), '{ broken');
  const gate = createAdmissionControl({ root: f.root, consumerDigest: CONSUMER_DIGEST, store, journal: f.journal, protectedRoot: false });
  await gate.assertTaskComplete(141);
  await assert.rejects(gate.assertSlotComplete('primary'), { code: 'ADMISSION_ATTEMPT_INVALID' });
});
