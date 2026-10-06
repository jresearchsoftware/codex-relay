import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, rm, readFile, writeFile, symlink, chmod } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { promisify } from 'node:util';
import { execFile, spawn } from 'node:child_process';
import { once } from 'node:events';
import { setTimeout } from 'node:timers/promises';
import { CONSUMER_DIGEST } from '../../consumer/consumer.mjs';
import { createAdmissionControl } from '../src/admission-control.mjs';
import { createAttemptStore } from '../src/attempt-store.mjs';
import { parseAdmissionArguments, drainAdmission, readAdmissionSnapshot } from '../src/admission-cli.mjs';
import { runAttempt } from '../src/attempt.mjs';
import { reportRoutingResult } from '../src/entrypoint.mjs';
import { VERSION } from '../src/execution-contract.mjs';
import { fixture, memoryStore } from './fixture.mjs';

const operationId = '12345678-1234-1234-1234-123456789abc';
const otherOperation = '12345678-1234-1234-1234-123456789abd';
const target = 'a'.repeat(40);
const exec = promisify(execFile);
const serviceIntent = () => ({
  reviewer: { active: true, enabled: 'disabled', load: 'loaded' },
  production: { active: true, enabled: 'enabled', load: 'loaded' },
  general: { active: true, enabled: 'enabled-runtime', load: 'loaded' }
});
async function control(t, { store = memoryStore(), journal = memoryStore() } = {}) {
  const root = await mkdtemp(join(tmpdir(), 'relay-admission-')); t.after(() => rm(root, { recursive: true, force: true }));
  const admission = createAdmissionControl({ root, consumerDigest: CONSUMER_DIGEST, store, journal, protectedRoot: false });
  await admission.initialize();
  return { root, admission, store, journal };
}
async function fixtureWithGate(t, options = {}) {
  const f = await fixture(t, { ...options, createAdmission: async ({ root, store, journal }) => {
    const gateRoot = join(root, 'claims'); await mkdir(gateRoot, { mode: 0o700 });
    const admission = createAdmissionControl({ root: gateRoot, consumerDigest: CONSUMER_DIGEST, store, journal, protectedRoot: false });
    await admission.initialize(); return admission;
  } });
  return f;
}

test('a non-regular gate fails closed without waiting for a FIFO writer', { timeout: 2000 }, async t => {
  const { admission, root } = await control(t);
  const path = join(root, 'admission-v1.json');
  await rm(path);
  await exec('mkfifo', ['-m', '600', path]);
  await assert.rejects(admission.read(), { code: 'ADMISSION_STATE_UNSAFE' });
});

test('gate is durable, binds the owner operation and requires verified installed revision before reopening', async t => {
  const { admission, root } = await control(t);
  await admission.assertOpen();
  const state = await admission.quiesce({ operationId, target });
  assert.equal(state.phase, 'quiesced');
  assert.equal((await admission.initialize()).phase, 'quiesced');
  await assert.rejects(admission.assertOpen(), { code: 'ADMISSION_QUIESCED' });
  await assert.rejects(admission.quiesce({ operationId: otherOperation, target }), { code: 'ADMISSION_OPERATION_MISMATCH' });
  await assert.rejects(admission.quiesce({ operationId, target: 'b'.repeat(40) }), { code: 'ADMISSION_TARGET_MISMATCH' });
  assert.deepEqual(await admission.quiesce({ operationId, target }), state);
  await assert.rejects(admission.resume({ operationId }), { code: 'ADMISSION_VERIFICATION_REQUIRED' });
  assert.equal((await admission.drained({ operationId })).drained, true);
  await admission.phase({ operationId, phase: 'applying' });
  await admission.phase({ operationId, phase: 'recovery-required' });
  await assert.rejects(admission.resume({ operationId }), { code: 'ADMISSION_VERIFICATION_REQUIRED' });
  await admission.phase({ operationId, phase: 'applying' });
  await assert.rejects(admission.phase({ operationId, phase: 'verified' }), { code: 'ADMISSION_VERIFIED_REVISION_REQUIRED' });
  await assert.rejects(admission.phase({ operationId, phase: 'verified', revision: 'b'.repeat(40) }), { code: 'ADMISSION_TARGET_MISMATCH' });
  await admission.phase({ operationId, phase: 'verified', revision: target });
  assert.equal((await admission.read()).verifiedRevision, target);
  await admission.resume({ operationId });
  assert.equal(JSON.parse(await readFile(join(root, 'admission-v1.json'), 'utf8')).phase, 'open');
});

test('bound service activity snapshot survives failed activation and cannot be replaced by its resulting inactive state', async t => {
  const { admission, root, store, journal } = await control(t);
  const services = serviceIntent();
  await admission.quiesce({ operationId, target });
  await assert.rejects(admission.snapshot({ operationId, services }), { code: 'ADMISSION_PHASE_INVALID' });
  await admission.drained({ operationId });
  await admission.phase({ operationId, phase: 'applying' });
  const saved = await admission.snapshot({ operationId, services });
  assert.deepEqual(saved.previousActive, services);
  assert.deepEqual(JSON.parse(await readFile(join(root, 'admission-v1.json'), 'utf8')).previousActive, services);
  await admission.phase({ operationId, phase: 'recovery-required' });
  const reopened = createAdmissionControl({ root, consumerDigest: CONSUMER_DIGEST, store, journal, protectedRoot: false });
  assert.deepEqual((await reopened.initialize()).previousActive, services);
  const failedActivity = serviceIntent();
  failedActivity.reviewer.active = false; failedActivity.production.active = false;
  assert.deepEqual((await reopened.snapshot({ operationId, services: failedActivity })).previousActive, services);
  await reopened.phase({ operationId, phase: 'applying' });
  assert.deepEqual((await reopened.snapshot({ operationId, services: failedActivity })).previousActive, services);
  await assert.rejects(reopened.snapshot({ operationId: otherOperation, services }), { code: 'ADMISSION_OPERATION_MISMATCH' });
  await reopened.phase({ operationId, phase: 'verified', revision: target });
  await reopened.resume({ operationId });
  assert.equal((await reopened.read()).previousActive, null);
  await reopened.quiesce({ operationId: otherOperation, target });
  assert.equal((await reopened.read()).previousActive, null);
});

test('service snapshot rejects incomplete, unknown or inconsistent states and bounded CLI input rejects duplicate fields', async t => {
  const { admission } = await control(t);
  await admission.quiesce({ operationId, target }); await admission.drained({ operationId });
  await admission.phase({ operationId, phase: 'applying' });
  const incomplete = serviceIntent(); delete incomplete.general;
  const unknown = serviceIntent(); unknown.reviewer.enabled = 'unknown';
  const inconsistent = serviceIntent(); inconsistent.production.load = 'not-found';
  const extra = serviceIntent(); extra.general.secret = 'forbidden';
  for (const services of [incomplete, unknown, inconsistent, extra]) {
    await assert.rejects(admission.snapshot({ operationId, services }), { code: 'ADMISSION_SNAPSHOT_INVALID' });
    assert.equal((await admission.read()).previousActive, null);
  }
  const source = JSON.stringify(serviceIntent());
  assert.deepEqual(await readAdmissionSnapshot([Buffer.from(source)]), serviceIntent());
  await assert.rejects(readAdmissionSnapshot([Buffer.from(source.replace('"active":true', '"active":true,"active":false'))]),
    { code: 'ADMISSION_SNAPSHOT_INVALID' });
  await assert.rejects(readAdmissionSnapshot([Buffer.alloc(4097)]), { code: 'ADMISSION_SNAPSHOT_TOO_LARGE' });
});

test('explicit recovery target requires the bound recovery phase and drained records while retaining original service intent', async t => {
  const { admission, store, root } = await control(t);
  const rollback = 'b'.repeat(40);
  await admission.quiesce({ operationId, target });
  await assert.rejects(admission.recoveryTarget({ operationId, target: rollback }), { code: 'ADMISSION_PHASE_INVALID' });
  await admission.drained({ operationId }); await admission.phase({ operationId, phase: 'applying' });
  await admission.snapshot({ operationId, services: serviceIntent() });
  await assert.rejects(admission.recoveryTarget({ operationId, target: rollback }), { code: 'ADMISSION_PHASE_INVALID' });
  await admission.phase({ operationId, phase: 'recovery-required' });
  const pathname = join(root, 'admission-v1.json'); const saved = await readFile(pathname, 'utf8');
  await assert.rejects(admission.recoveryTarget({ operationId: otherOperation, target: rollback }), { code: 'ADMISSION_OPERATION_MISMATCH' });
  await assert.rejects(admission.recoveryTarget({ operationId, target: 'invalid' }), { code: 'ADMISSION_OPERATION_INVALID' });
  const record = { envelope: { version: VERSION, runId: 99, attemptId: 'run-99', route: 'auto', consumerDigest: CONSUMER_DIGEST },
    controllerLifecycle: { version: 1, status: 'active' } };
  await store.put(99, record);
  await assert.rejects(admission.recoveryTarget({ operationId, target: rollback }), { code: 'ADMISSION_NOT_DRAINED' });
  delete record.controllerLifecycle; await store.put(99, record);
  await assert.rejects(admission.recoveryTarget({ operationId, target: rollback }), { code: 'ADMISSION_NOT_DRAINED' });
  assert.equal(await readFile(pathname, 'utf8'), saved);
  record.controllerLifecycle = { version: 1, status: 'complete', child: 'not_started', containment: 'not_required' };
  record.outcome = { status: 'BLOCKED', head: null, prNumber: null, outcomeId: 12 };
  await store.put(99, record);
  const selected = await admission.recoveryTarget({ operationId, target: rollback });
  assert.equal(selected.target, rollback);
  assert.deepEqual(selected.previousActive, serviceIntent());
  await assert.rejects(admission.quiesce({ operationId, target }), { code: 'ADMISSION_TARGET_MISMATCH' });
  await admission.phase({ operationId, phase: 'applying' });
  await admission.phase({ operationId, phase: 'verified', revision: rollback });
  assert.equal((await admission.resume({ operationId })).phase, 'open');
});

test('quiesce denies new automatic admission before label consumption, journal reservation or GitHub mutation', async t => {
  let recordStore; let readyIssue;
  await assert.rejects(fixtureWithGate(t, { labelLaunch: true, beforeAdmission: async ({ admissionControl, store, issue }) => {
    recordStore = store; readyIssue = issue;
    await admissionControl.quiesce({ operationId, target });
  } }), { code: 'ADMISSION_QUIESCED' });
  assert.deepEqual(await recordStore.all(), []);
  assert.ok(readyIssue.labels.some(label => label.name === 'codex-ready-auto'));
});

test('quiesce allows the existing admitted automatic controller to finish through Writer publication and containment', async t => {
  const f = await fixtureWithGate(t); const gate = f.admissionControl;
  assert.deepEqual((await f.store.get(f.envelope.runId)).controllerLifecycle, { version: 1, status: 'active' });
  await gate.quiesce({ operationId, target });
  assert.deepEqual((await gate.status()).active, [f.envelope.runId]);
  assert.equal((await gate.drained({ operationId })).drained, false);
  const returned = await runAttempt({ ...f, execute: async () => {
    await f.commit(); return { version: VERSION, attemptId: f.envelope.attemptId,
      child: 'started', containment: 'reaped', result: { status: 'success', summary: 'completed', validation: [] } };
  } });
  assert.equal(returned.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
  // Ready is returned only after the durable journal and controller completion.
  assert.equal(returned.draft, false);
  assert.deepEqual((await gate.status()).active, []);
  await gate.complete({ runId: f.envelope.runId, attemptId: f.envelope.attemptId });
  assert.deepEqual((await gate.status()).active, []);
  assert.equal((await gate.drained({ operationId })).drained, true);
  assert.equal(f.pushes(), 1);
  await gate.complete({ runId: f.envelope.runId, attemptId: f.envelope.attemptId });
  assert.equal(f.pushes(), 1);
});

test('failed Ready handoff remains an unresolved drain boundary until exact transition recovery', async t => {
  const f = await fixtureWithGate(t); const gate = f.admissionControl; const ready = f.api.ready;
  f.api.ready = async () => { throw Object.assign(new Error('Ready failed'), { code: 'READY_MUTATION_FAILED' }); };
  const args = { ...f, execute: async () => {
    await f.commit(); return { version: VERSION, attemptId: f.envelope.attemptId,
      child: 'started', containment: 'reaped', result: { status: 'success' } };
  } };
  await assert.rejects(runAttempt(args), { code: 'READY_MUTATION_FAILED' });
  assert.deepEqual((await gate.status()).unknown, [99]);
  await gate.quiesce({ operationId, target });
  await assert.rejects(gate.drained({ operationId }), { code: 'ADMISSION_DRAIN_UNKNOWN' });
  f.api.ready = ready;
  assert.equal((await runAttempt(args)).draft, false);
  assert.equal((await gate.drained({ operationId })).drained, true);
  assert.equal(f.pushes(), 1); assert.equal(f.comments.length, 1);
});

test('manual handoff remains available while automatic admission is quiesced', async t => {
  const f = await fixtureWithGate(t, { route: 'manual', beforeAdmission: ({ admissionControl }) => admissionControl.quiesce({ operationId, target }) });
  assert.equal((await runAttempt({ ...f })).status, 'handed-off');
  assert.deepEqual((await f.admissionControl.status()).active, []);
  assert.equal(f.comments.length, 1);
});

test('unknown execution, missing legacy containment, and unresolved publication intents fail drain closed', async t => {
  const f = await fixtureWithGate(t); const gate = f.admissionControl;
  await gate.quiesce({ operationId, target });
  const record = await f.store.get(f.envelope.runId);
  record.outcome = { status: 'BLOCKED', head: null, prNumber: null, outcomeId: 12 };
  await f.store.put(f.envelope.runId, record);
  await f.journal.put(f.envelope.runId, { version: VERSION, envelope: f.envelope,
    execution: { reserved: true, returned: false, child: 'unknown', containment: 'unknown' }, outcome: record.outcome });
  await assert.rejects(gate.complete({ runId: f.envelope.runId, attemptId: f.envelope.attemptId }), { code: 'ADMISSION_COMPLETION_UNKNOWN' });
  await assert.rejects(gate.drained({ operationId }), { code: 'ADMISSION_DRAIN_UNKNOWN' });
  delete record.controllerLifecycle;
  await f.store.put(f.envelope.runId, record);
  await assert.rejects(gate.drained({ operationId }), { code: 'ADMISSION_DRAIN_UNKNOWN' });
  const saved = await f.journal.get(f.envelope.runId);
  saved.execution = { reserved: true, returned: true, child: 'started', containment: 'reaped' };
  await f.journal.put(f.envelope.runId, saved);
  assert.equal((await gate.drained({ operationId })).drained, true);
  await gate.complete({ runId: f.envelope.runId, attemptId: f.envelope.attemptId });
  assert.equal((await f.store.get(f.envelope.runId)).controllerLifecycle.status, 'complete');
  record.publicationIntent = { previous: null, head: target };
  await f.store.put(f.envelope.runId, record);
  await assert.rejects(gate.resume({ operationId }), { code: 'ADMISSION_VERIFICATION_REQUIRED' });
  // Even a root verified transition cannot reopen ambiguous prior publication.
  await gate.phase({ operationId, phase: 'verified', revision: target });
  await assert.rejects(gate.resume({ operationId }), { code: 'ADMISSION_NOT_DRAINED' });
});

test('contained pre-child terminal decisions release only after a matching terminal journal exists', async t => {
  const f = await fixtureWithGate(t); const gate = f.admissionControl;
  f.issue.body += '\nAccepted starting main: malformed';
  const outcome = await runAttempt({ ...f, execute: () => assert.fail('authority failure must not launch') });
  assert.equal(outcome.status, 'BLOCKED');
  await gate.complete({ runId: f.envelope.runId, attemptId: f.envelope.attemptId });
  assert.deepEqual((await f.store.get(f.envelope.runId)).controllerLifecycle,
    { version: 1, status: 'complete', child: 'not_started', containment: 'not_required' });
});

function legacyPublication() {
  const record = {
    envelope: { version: VERSION, runId: 99, attemptId: 'run-99', route: 'auto', consumerDigest: CONSUMER_DIGEST,
      target: 'issue', number: 27, issueNumber: 27 },
    prIntent: true, publicationIntent: null, commentIntent: null, publishedHead: target, finalHead: null,
    outcome: { status: 'BLOCKED', head: target, prNumber: 38, outcomeId: 12 }
  };
  const saved = { version: VERSION, envelope: structuredClone(record.envelope),
    execution: { reserved: true, returned: true, child: 'started', containment: 'reaped' },
    outcome: structuredClone(record.outcome) };
  return { record, saved };
}

test('legacy PR creation is resolved by matching terminal journal and exact published head without rewriting receipts', async t => {
  for (const status of ['BLOCKED', 'IMPLEMENTED_PENDING_FRESH_REVIEW']) {
    const { admission, store, journal } = await control(t);
    const { record, saved } = legacyPublication();
    record.outcome.status = saved.outcome.status = status;
    if (status === 'IMPLEMENTED_PENDING_FRESH_REVIEW') record.finalHead = target;
    await store.put(99, record); await journal.put(99, saved);
    assert.deepEqual((await admission.status()).unknown, []);
    assert.deepEqual(await store.get(99), record);
    assert.deepEqual(await journal.get(99), saved);
    await admission.quiesce({ operationId, target });
    assert.equal((await admission.drained({ operationId })).drained, true);
    await admission.complete({ runId: 99, attemptId: 'run-99' });
    assert.deepEqual((await admission.status()).unknown, []);
    assert.equal((await admission.drained({ operationId })).drained, true);
    assert.deepEqual(await store.get(99), record);
    assert.deepEqual(await journal.get(99), saved);
  }
});

test('legacy PR receipt compatibility does not resolve ambiguous publication, identity or containment', async t => {
  const cases = [
    ['missing terminal journal', (_, state) => { state.saved = null; }],
    ['different journal envelope', (_, state) => { state.saved.envelope.attemptId = 'run-100'; }],
    ['different terminal PR', (_, state) => { state.saved.outcome.prNumber = 39; }],
    ['different terminal head', (_, state) => { state.saved.outcome.head = 'b'.repeat(40); }],
    ['different terminal Outcome', (_, state) => { state.saved.outcome.outcomeId = 13; }],
    ['missing PR receipt', record => { record.outcome.prNumber = null; }],
    ['invalid Outcome receipt', record => { record.outcome.outcomeId = 0; }],
    ['missing published head', record => { record.publishedHead = null; }],
    ['different published head', record => { record.publishedHead = 'b'.repeat(40); }],
    ['invalid published head', record => { record.publishedHead = record.outcome.head = 'invalid'; }],
    ['conflicting resolved PR', record => { record.prNumber = 39; }],
    ['invalid resolved PR', record => { record.prNumber = 0; }],
    ['explicit unresolved PR', record => { record.prNumber = null; }],
    ['invalid PR intent', record => { record.prIntent = 'true'; }],
    ['new controller reservation', record => { record.controllerLifecycle = { version: 1, status: 'active' }; }],
    ['pending push', record => { record.publicationIntent = { previous: null, head: target }; }],
    ['pending comment', record => { record.commentIntent = { key: 'outcome', number: 38 }; }],
    ['inconsistent final head', record => { record.finalHead = target; }],
    ['missing successful final head', record => { record.outcome.status = 'IMPLEMENTED_PENDING_FRESH_REVIEW'; }],
    ['unknown child', (_, state) => { state.saved.execution.child = 'unknown'; }],
    ['unknown containment', (_, state) => { state.saved.execution.containment = 'unknown'; }],
    ['unreturned execution', (_, state) => { state.saved.execution.returned = false; }]
  ];
  for (const [name, mutate] of cases) {
    await t.test(name, async t => {
      const { admission, store, journal } = await control(t);
      const state = legacyPublication();
      mutate(state.record, state);
      // Changes to the Writer receipt alone remain mirrored unless the case
      // specifically exercises conflicting journal identity.
      if (state.saved && !name.startsWith('different terminal')) state.saved.outcome = structuredClone(state.record.outcome);
      await store.put(99, state.record);
      if (state.saved) await journal.put(99, state.saved);
      assert.deepEqual((await admission.status()).unknown, [99]);
      await admission.quiesce({ operationId, target });
      await assert.rejects(admission.drained({ operationId }), { code: 'ADMISSION_DRAIN_UNKNOWN' });
      await assert.rejects(admission.complete({ runId: 99, attemptId: 'run-99' }), { code: 'ADMISSION_COMPLETION_UNKNOWN' });
      assert.deepEqual(await store.get(99), state.record);
    });
  }
});

test('unsafe, malformed, missing or differently bound gate state never implies admission is open', async t => {
  const { admission, root } = await control(t);
  const pathname = join(root, 'admission-v1.json'); const source = await readFile(pathname, 'utf8');
  await writeFile(pathname, source.replace('"phase":"open"', '"phase":"open","phase":"open"'));
  await assert.rejects(admission.assertOpen(), { code: 'ADMISSION_STATE_INVALID' });
  await writeFile(pathname, source.replace(CONSUMER_DIGEST, 'b'.repeat(64)));
  await assert.rejects(admission.assertOpen(), { code: 'CONSUMER_CONFIG_CHANGED' });
  await writeFile(pathname, JSON.stringify({ ...JSON.parse(source), phase: 'verified', operationId, target, verifiedRevision: 'b'.repeat(40) }));
  await assert.rejects(admission.read(), { code: 'ADMISSION_STATE_INVALID' });
  await writeFile(pathname, source); await chmod(pathname, 0o666);
  await assert.rejects(admission.assertOpen(), { code: 'ADMISSION_STATE_UNSAFE' });
  await rm(pathname); await symlink('/dev/null', pathname);
  await assert.rejects(admission.assertOpen(), { code: 'ADMISSION_STATE_UNREADABLE' });
  await rm(pathname);
  await assert.rejects(admission.assertOpen(), { code: 'ADMISSION_STATE_MISSING' });
});

test('bounded drain releases its snapshot lock while waiting and cannot imply success on timeout', async () => {
  let clock = 0; let calls = 0;
  const snapshot = async () => ({ drained: ++calls === 3 });
  assert.equal((await drainAdmission({ operationId, timeout: 3 }, { snapshot, now: () => clock, wait: async ms => { clock += ms; } })).drained, true);
  clock = 0;
  await assert.rejects(drainAdmission({ operationId, timeout: 2 }, { snapshot: async () => ({ drained: false }),
    now: () => clock, wait: async ms => { clock += ms; } }), { code: 'ADMISSION_DRAIN_TIMEOUT' });
  assert.equal(clock, 2000);
});

test('long drain emits bounded counts every thirty seconds without exposing attempt identities or changing its result', async () => {
  let clock = 0; const progress = [];
  const value = await drainAdmission({ operationId, timeout: 70 }, {
    snapshot: async () => ({ drained: clock >= 65000, active: ['private-attempt-a', 'private-attempt-b'], unknown: [] }),
    now: () => clock, wait: async ms => { clock += ms; }, reportProgress: value => progress.push(value)
  });
  assert.equal(value.drained, true);
  assert.deepEqual(progress, [
    { phase: 'drain', active: 2, unknown: 0, elapsedSeconds: 30 },
    { phase: 'drain', active: 2, unknown: 0, elapsedSeconds: 60 }
  ]);
  assert.doesNotMatch(JSON.stringify(progress), /private-attempt|12345678/);
});

test('root lifecycle CLI accepts only bounded fixed command arguments', () => {
  assert.deepEqual(parseAdmissionArguments(['quiesce', '--operation', operationId, '--target', target]),
    { command: 'quiesce', options: { operationId, target } });
  assert.equal(parseAdmissionArguments(['drain', '--operation', operationId, '--timeout', '1800']).options.timeout, 1800);
  assert.deepEqual(parseAdmissionArguments(['snapshot', '--operation', operationId]), { command: 'snapshot', options: { operationId } });
  assert.deepEqual(parseAdmissionArguments(['recovery-target', '--operation', operationId, '--target', target]),
    { command: 'recovery-target', options: { operationId, target } });
  assert.throws(() => parseAdmissionArguments(['drain', '--operation', operationId, '--timeout', '0']), { code: 'ADMISSION_TIMEOUT_INVALID' });
  assert.throws(() => parseAdmissionArguments(['status', '--root', '/tmp/untrusted']), { code: 'ADMISSION_ARGUMENTS_INVALID' });
  assert.throws(() => parseAdmissionArguments(['resume', '--operation', operationId, '--operation', otherOperation]), { code: 'ADMISSION_ARGUMENTS_INVALID' });
});

test('quiesced routing warning reports known absence of a worker without inventing a terminal Outcome', async () => {
  const output = []; const warnings = [];
  assert.equal(await reportRoutingResult(async () => ({ status: 'BLOCKED', code: 'ADMISSION_QUIESCED' }),
    { write: value => output.push(value), writeError: value => warnings.push(value) }), 0);
  assert.match(warnings[0], /Automatic admission is quiesced; no worker started/);
  assert.doesNotMatch(warnings[0], /terminal Outcome/);
  assert.equal(JSON.parse(output[0]).code, 'ADMISSION_QUIESCED');
});

test('real shared flock serializes quiesce against automatic reservation before record mutation', async t => {
  const { root, admission } = await control(t);
  const module = new URL('../src/admission-control.mjs', import.meta.url).href;
  const attemptStore = new URL('../src/attempt-store.mjs', import.meta.url).href;
  const script = join(root, 'race.mjs'); const lock = join(root, 'publication-v2.lock');
  await writeFile(script, `import { createAdmissionControl } from ${JSON.stringify(module)};
import { createAttemptStore } from ${JSON.stringify(attemptStore)};
import { writeFile, access } from 'node:fs/promises';
import { setTimeout } from 'node:timers/promises';
const root = ${JSON.stringify(root)};
const store = createAttemptStore(root + '/publication-v2');
const gate = createAdmissionControl({ root, consumerDigest: ${JSON.stringify(CONSUMER_DIGEST)}, store, journal: createAttemptStore(root + '/journal'), protectedRoot: false });
if (process.argv[2] === 'reserve') {
  const controllerLifecycle = await gate.reserve();
  await writeFile(root + '/reserved-lock-held', 'yes');
  while (!await access(root + '/release-reservation').then(() => true, () => false)) await setTimeout(10);
  await store.put(99, { envelope: { version: 2, runId: 99, attemptId: 'run-99', consumerDigest: ${JSON.stringify(CONSUMER_DIGEST)}, route: 'auto' }, controllerLifecycle });
} else if (process.argv[2] === 'quiesce') {
  await gate.quiesce({ operationId: ${JSON.stringify(operationId)}, target: ${JSON.stringify(target)} });
} else {
  try { await gate.reserve(); process.exitCode = 20; } catch (error) { if (error.code !== 'ADMISSION_QUIESCED') throw error; }
}
`);
  const childEnv = { ...process.env };
  const first = spawn('/usr/bin/flock', [lock, process.execPath, script, 'reserve'], { env: childEnv, stdio: ['ignore', 'pipe', 'pipe'] });
  t.after(() => { if (first.exitCode === null) first.kill('SIGKILL'); });
  let ready = false;
  for (let i = 0; i < 200; i++) {
    ready = await readFile(join(root, 'reserved-lock-held'), 'utf8').then(() => true, () => false);
    if (ready) break;
    await setTimeout(10);
  }
  assert.equal(ready, true);
  const quiesce = exec('/usr/bin/flock', [lock, process.execPath, script, 'quiesce'], { env: childEnv });
  await setTimeout(40);
  assert.equal((await admission.read()).phase, 'open');
  const closed = once(first, 'close');
  await writeFile(join(root, 'release-reservation'), 'yes');
  assert.equal((await closed)[0], 0);
  await quiesce;
  const gate = createAdmissionControl({ root, consumerDigest: CONSUMER_DIGEST,
    store: createAttemptStore(join(root, 'publication-v2')), journal: memoryStore(), protectedRoot: false });
  assert.deepEqual((await gate.status()).active, [99]);
  await exec('/usr/bin/flock', [lock, process.execPath, script, 'denied'], { env: childEnv });
  assert.equal((await createAttemptStore(join(root, 'publication-v2')).all()).length, 1);
});
