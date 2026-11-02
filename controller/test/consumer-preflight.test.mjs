import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readdir, readFile, lstat, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { createAdmissionControl } from '../src/admission-control.mjs';
import { createAttemptStore } from '../src/attempt-store.mjs';
import { installedAdmissionControl, parseAdmissionArguments } from '../src/admission-cli.mjs';
import { VERSION } from '../src/execution-contract.mjs';

const currentDigest = 'a'.repeat(64), desiredDigest = 'b'.repeat(64);
const operationId = '12345678-1234-1234-1234-123456789abc', target = 'c'.repeat(40);
const envelope = (runId, route = 'manual') => ({ version: VERSION, consumerDigest: currentDigest,
  repository: 'example/sample', runId, attemptId: `run-${runId}`, route, issueNumber: 42,
  target: 'issue', number: 42 });
const terminal = runId => ({ status: 'BLOCKED', head: null, prNumber: null,
  outcomeId: runId + 1000, bodySha256: 'd'.repeat(64) });

async function fixture(t, options = {}) {
  const root = await mkdtemp(join(tmpdir(), 'relay-consumer-preflight-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const store = createAttemptStore(join(root, 'records'), { repository: 'example/sample' });
  const journal = createAttemptStore(join(root, 'journals'), { repository: 'example/sample' });
  const admission = createAdmissionControl({ root, consumerDigest: currentDigest, store, journal,
    protectedRoot: false, ...options });
  await admission.initialize();
  return { root, store, journal, admission };
}

async function snapshot(root) {
  const values = {};
  async function visit(path) {
    for (const name of (await readdir(path)).sort()) {
      const pathname = join(path, name), stat = await lstat(pathname);
      if (stat.isDirectory()) await visit(pathname);
      else values[pathname] = { bytes: (await readFile(pathname)).toString('base64'),
        inode: stat.ino, mode: stat.mode, size: stat.size };
    }
  }
  await visit(root); return values;
}

function rejected(runId, sealed = false) {
  const admissionBlock = { code: 'STARTING_STATE_MISMATCH' };
  const record = { envelope: { ...envelope(runId), admissionBlock, request: null,
    authorityDigest: null, branch: null, startHead: null }, admissionBlock, outcome: terminal(runId) };
  if (sealed) {
    record.commentBodies = { outcome: { number: 42, sha256: record.outcome.bodySha256,
      rendererVersion: 'human-v1' } };
    delete record.outcome.bodySha256;
  }
  return record;
}

function completedManual(runId, direct = false) {
  const record = { envelope: { ...envelope(runId),
    request: { schema_version: '3.0', kind: 'task-request' },
    requestReference: { sha256: 'e'.repeat(64) } },
    outcome: { ...terminal(runId), status: 'IMPLEMENTED_PENDING_FRESH_REVIEW', manual: true } };
  if (direct) {
    record.manualSubmission = { sha256: 'f'.repeat(64), parent: { kind: 'issue', number: 42 },
      rendererVersion: 'human-v1' };
    record.commentBodies = { outcome: { number: 42, sha256: record.outcome.bodySha256,
      rendererVersion: 'human-v1' } };
  } else {
    delete record.outcome.bodySha256;
    record.manualResultAuthorization = { id: runId + 2000, sha256: 'f'.repeat(64) };
  }
  return record;
}

async function seedHistory(store) {
  for (let id = 1; id <= 8; id++) await store.put(id, rejected(id, id === 8));
  for (let id = 9; id <= 11; id++) await store.put(id, completedManual(id, id === 11));
  for (let id = 12; id <= 21; id++) await store.put(id, { envelope: { ...envelope(id),
    request: { schema_version: id < 17 ? '3.0' : '4.0', kind: id < 17 ? 'task-request' : 'admission' } },
    outcome: null, ...(id < 20 ? { commentBodies: { handoff: { number: 42,
      sha256: 'e'.repeat(64), rendererVersion: 'human-v1' } } } : {}) });
}

test('open-gate preflight recognizes eleven retained receipts and blocks ten unresolved manual attempts read-only', async t => {
  const f = await fixture(t); await seedHistory(f.store);
  const before = await snapshot(f.root);
  assert.deepEqual(await f.admission.preflightConsumerTransition({ desiredDigest }), {
    currentDigest, desiredDigest, consumerChange: true, phase: 'open', operationId: null, target: null,
    active: [], unknown: Array.from({ length: 10 }, (_, index) => index + 12), eligible: false });
  assert.deepEqual(await snapshot(f.root), before);
  assert.equal((await f.admission.status()).phase, 'open');
});

test('unchanged consumer digest retains manual handoffs without introducing a new barrier', async t => {
  const f = await fixture(t); await seedHistory(f.store);
  const before = await snapshot(f.root);
  const result = await f.admission.preflightConsumerTransition({ desiredDigest: currentDigest });
  assert.deepEqual(result, { currentDigest, desiredDigest: currentDigest, consumerChange: false,
    phase: 'open', operationId: null, target: null, active: [], unknown: [], eligible: true });
  assert.deepEqual(await snapshot(f.root), before);
});

test('active automatic controllers remain drainable while unknown containment and publication block preflight', async t => {
  const f = await fixture(t), active = { envelope: envelope(30, 'auto'),
    controllerLifecycle: { version: 1, status: 'active' } };
  await f.store.put(30, active);
  const before = await snapshot(f.root);
  for (const digest of [currentDigest, desiredDigest]) {
    const result = await f.admission.preflightConsumerTransition({ desiredDigest: digest });
    assert.deepEqual(result.active, [30]); assert.deepEqual(result.unknown, []);
    assert.equal(result.eligible, true);
  }
  assert.deepEqual(await snapshot(f.root), before);
  for (const fields of [
    { controllerLifecycle: { version: 1, status: 'complete', child: 'started', containment: 'unknown' } },
    { controllerLifecycle: { version: 1, status: 'complete', child: 'not_started', containment: 'not_required' },
      publicationIntent: { reserved: true } },
    { controllerLifecycle: { version: 1, status: 'active' } }
  ]) {
    await f.store.put(31, { envelope: envelope(31, 'auto'), outcome: terminal(31), ...fields });
    const observed = await snapshot(f.root);
    const result = await f.admission.preflightConsumerTransition({ desiredDigest });
    assert.deepEqual(result.active, [30]); assert.deepEqual(result.unknown, [31]);
    assert.equal(result.eligible, false); assert.deepEqual(await snapshot(f.root), observed);
  }
  await f.admission.quiesce({ operationId, target });
  await assert.rejects(f.admission.checkConsumerTransition({ operationId, target }), { code: 'ADMISSION_PHASE_INVALID' });
});

test('preflight preserves exact gate identity in every lifecycle phase and allocates no operation', async t => {
  const f = await fixture(t);
  const check = async phase => {
    const before = await snapshot(f.root);
    const result = await f.admission.preflightConsumerTransition({ desiredDigest });
    assert.equal(result.phase, phase); assert.equal(result.currentDigest, currentDigest);
    assert.equal(result.operationId, phase === 'open' ? null : operationId);
    assert.equal(result.target, phase === 'open' ? null : target);
    assert.equal(result.eligible, true); assert.deepEqual(await snapshot(f.root), before);
  };
  await check('open'); await f.admission.quiesce({ operationId, target }); await check('quiesced');
  await f.admission.drained({ operationId }); await check('drained');
  await f.admission.phase({ operationId, phase: 'applying' }); await check('applying');
  await f.admission.phase({ operationId, phase: 'recovery-required' }); await check('recovery-required');
  await f.admission.phase({ operationId, phase: 'applying' });
  await f.admission.phase({ operationId, phase: 'verified', revision: target }); await check('verified');
});

test('supplemental SERIAL automatic inventory and manual classifier remain separate and are deduplicated', async t => {
  let manualReads = 0;
  const f = await fixture(t, {
    supplementalVerify: async () => {},
    supplementalInventory: async input => {
      assert.deepEqual(input, { task: null, slot: null, resourceOnly: false });
      return { active: [41], unknown: [42] };
    },
    supplementalManualInventory: async () => { manualReads++; return [43, 43]; }
  });
  await f.store.put(43, { envelope: envelope(43), outcome: null });
  const before = await snapshot(f.root);
  const unchanged = await f.admission.preflightConsumerTransition({ desiredDigest: currentDigest });
  assert.deepEqual(unchanged.active, [41]); assert.deepEqual(unchanged.unknown, [42]);
  assert.equal(unchanged.eligible, false); assert.equal(manualReads, 0);
  const changed = await f.admission.preflightConsumerTransition({ desiredDigest });
  assert.deepEqual(changed.active, [41]); assert.deepEqual(changed.unknown, [42, 43]);
  assert.equal(changed.eligible, false); assert.equal(manualReads, 1);
  assert.deepEqual(await snapshot(f.root), before);
});

test('invalid digests, malformed attempts and invalid supplemental identities fail closed without writes', async t => {
  const f = await fixture(t); const before = await snapshot(f.root);
  for (const digest of [undefined, null, '', 'A'.repeat(64), 'a'.repeat(63), {}])
    await assert.rejects(f.admission.preflightConsumerTransition({ desiredDigest: digest }), { code: 'ADMISSION_CONFIG_INVALID' });
  assert.deepEqual(await snapshot(f.root), before);
  await f.store.put(50, { envelope: { ...envelope(50), version: VERSION + 1 } });
  const malformed = await snapshot(f.root);
  await assert.rejects(f.admission.preflightConsumerTransition({ desiredDigest }), { code: 'ADMISSION_ATTEMPT_INVALID' });
  assert.deepEqual(await snapshot(f.root), malformed);
  const extra = await fixture(t, { supplementalManualInventory: async () => ['private/path'] });
  const extraBefore = await snapshot(extra.root);
  await assert.rejects(extra.admission.preflightConsumerTransition({ desiredDigest }), { code: 'ADMISSION_ATTEMPT_INVALID' });
  assert.deepEqual(await snapshot(extra.root), extraBefore);
});

test('CLI advertises the read-only preflight and accepts exactly one canonical desired digest', () => {
  assert.equal(typeof installedAdmissionControl().preflightConsumerTransition, 'function');
  assert.deepEqual(parseAdmissionArguments(['consumer-transition-preflight', '--desired-digest', desiredDigest]),
    { command: 'consumer-transition-preflight', options: { desiredDigest } });
  for (const args of [[], ['--desired-digest'], ['--desired-digest', desiredDigest, '--desired-digest', desiredDigest],
    ['--desiredDigest', desiredDigest], ['--desired-digest', desiredDigest, '--operation', operationId]])
    assert.throws(() => parseAdmissionArguments(['consumer-transition-preflight', ...args]), { code: 'ADMISSION_ARGUMENTS_INVALID' });
  assert.throws(() => parseAdmissionArguments(['consumer-transition-preflight', '--desired-digest', 'invalid']),
    { code: 'ADMISSION_CONFIG_INVALID' });
});
