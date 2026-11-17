import test from 'node:test';
import assert from 'node:assert/strict';
import { join } from 'node:path';
import { mkdtemp, rm, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { runAttempt } from '../src/attempt.mjs';
import { persistAttemptFailureDiagnostic } from '../src/attempt-diagnostic.mjs';
import { openRuntimeDiagnostic, reserveRuntimeDiagnostic } from '../src/diagnostic-fallback.mjs';
import { createOnDemandDispatchAdapter } from '../src/github.mjs';
import { VERSION } from '../src/execution-contract.mjs';
import { fixture, memoryStore, currentEnvelope } from './fixture.mjs';

function unavailablePrimary(f) {
  const root = join(f.root, 'fallback');
  return {
    root,
    persistFailure: value => persistAttemptFailureDiagnostic({ ...value, root,
      readConfig: async () => ({ mode: 'normal' }),
      diagnosticStore: async () => { throw Object.assign(new Error('primary store unavailable'), { code: 'ENOSPC' }); } })
  };
}

test('unavailable runner recorders explicitly report the evidence gap without disclosing the original cause', async () => {
  const lines = [];
  const result = await persistAttemptFailureDiagnostic({ executionId: 'run-244', stage: 'preflight',
    error: Object.assign(new Error('private original checkout cause'), { code: 'EACCES' }),
    fallbackOpen: async () => { throw Object.assign(new Error('private fallback cause'), { code: 'EROFS' }); },
    readConfig: async () => ({ mode: 'normal' }),
    diagnosticStore: async () => { throw Object.assign(new Error('private primary cause'), { code: 'ENOSPC' }); },
    writeFallback: line => lines.push(line) });
  assert.equal(result.diagnosticStore.storeCode, 'ENOSPC'); assert.equal(result.fallbackReference.code, 'EROFS');
  assert.equal(lines.length, 1);
  assert.match(lines[0], /observed_not_retained/); assert.match(lines[0], /EACCES/);
  assert.match(lines[0], /diagnostic-persistence/);
  assert.doesNotMatch(lines[0], /private|checkout cause|primary cause|fallback cause/);
});

test('checkout failure and unavailable primary diagnostics retain a private capsule and sanitized Outcome reference', async t => {
  const f = await fixture(t);
  const journal = f.journal;
  const diagnostic = unavailablePrimary(f);
  const secret = 'private-fixture-value';
  await assert.rejects(runAttempt({ ...f, journal, persistFailure: diagnostic.persistFailure,
    prepare: async () => { throw Object.assign(new Error(`token=${secret}`), {
      code: 'EACCES', syscall: 'mkdir', path: `/private/${secret}` }); },
    execute: () => assert.fail('preparation failure must not execute'),
    collect: () => assert.fail('preparation failure must not collect') }), error => {
    assert.equal(error.code, 'EACCES');
    assert.equal(error.details.fallbackReference.status, 'stored');
    assert.equal(error.details.diagnosticStore.storeCode, 'ENOSPC');
    return true;
  });
  const capsule = await (await openRuntimeDiagnostic({ executionId: f.envelope.attemptId, root: diagnostic.root })).read();
  assert.equal(capsule.primaryCause, 'EACCES'); assert.equal(capsule.syscall, 'mkdir');
  assert.equal(capsule.operation, 'checkout-prepare'); assert.equal(capsule.persistence, 'failed');
  assert.equal(capsule.cleanup, 'retained');
  assert.equal(capsule.diagnosticStore.storeCode, 'ENOSPC');
  assert.ok(Buffer.byteLength(JSON.stringify(capsule)) < 16 * 1024);
  assert.match(JSON.stringify(capsule.causalEvidence), /\/private\//);
  assert.doesNotMatch(JSON.stringify(capsule), /token=private-fixture-value/);
  assert.match(JSON.stringify(capsule.recorderFailure), /primary store unavailable/);
  assert.equal(f.comments.length, 1);
  assert.match(f.comments[0].body, /Fallback diagnostics: stored; reference: run-99; slot: 0/);
  assert.match(f.comments[0].body, /EACCES/);
  assert.doesNotMatch(f.comments[0].body, /private-fixture-value|\/private\//);
  assert.equal(f.pushes(), 0);
});

test('a journal write failure after a returned child retains known child state and independent failure evidence', async t => {
  const f = await fixture(t);
  const backing = memoryStore();
  const diagnostic = unavailablePrimary(f);
  let failedWrite = false;
  const journal = { get: backing.get, async put(id, record) {
    if (!failedWrite && record.execution?.returned === true) {
      failedWrite = true;
      throw Object.assign(new Error('journal write failed'), { code: 'ENOSPC', syscall: 'write' });
    }
    return backing.put(id, record);
  } };
  await assert.rejects(runAttempt({ ...f, journal, persistFailure: diagnostic.persistFailure,
    execute: async () => ({ version: VERSION, attemptId: f.envelope.attemptId,
      child: 'started', containment: 'reaped', result: { status: 'success' } }),
    collect: () => assert.fail('failed execution journal must not continue publication') }), { code: 'ENOSPC' });
  const capsule = await (await openRuntimeDiagnostic({ executionId: f.envelope.attemptId, root: diagnostic.root })).read();
  assert.equal(capsule.primaryCause, 'ENOSPC'); assert.equal(capsule.syscall, 'write');
  assert.equal(capsule.childState, 'started'); assert.equal(capsule.containment, 'reaped');
  assert.equal(capsule.lastSuccessfulBoundary, 'checkout');
  assert.equal(capsule.persistence, 'failed');
  assert.equal(f.pushes(), 0); assert.equal(f.comments.length, 1);
  assert.match(f.comments[0].body, /Fallback diagnostics: stored/);
});

test('normal pre-execution domain decisions retain causal evidence and their domain classification', async t => {
  const f = await fixture(t);
  let recorded;
  const result = await runAttempt({ ...f, journal: f.journal,
    prepare: async () => { throw Object.assign(new Error('existing checkout'), { code: 'CHECKOUT_ALREADY_EXISTS' }); },
    execute: () => assert.fail('domain blocker must not execute'),
    persistFailure: async value => { recorded = value; return {}; } });
  assert.equal(result.status, 'BLOCKED'); assert.equal(f.comments.length, 1);
  assert.equal(recorded.error.message, 'existing checkout');
  assert.equal((await f.journal.get(99)).diagnostic.orchestration, 'COMPLETED');
  assert.match(f.comments[0].body, /CHECKOUT_ALREADY_EXISTS/);
  assert.doesNotMatch(f.comments[0].body, /Fallback diagnostics:/);
});

test('fallback reservation failure stays known-not-executed rather than becoming a containment failure', async t => {
  const f = await fixture(t);
  const diagnostic = unavailablePrimary(f);
  const dispatcher = createOnDemandDispatchAdapter({
    reserveDiagnostic: async () => { throw Object.assign(new Error('no diagnostic slot'), { code: 'DIAGNOSTIC_RETENTION_LIMIT' }); },
    spawnImpl: () => assert.fail('no child may start without a capsule'),
    finalizeArtifacts: () => assert.fail('unreserved runtime must not finalize') });
  await assert.rejects(runAttempt({ ...f, journal: f.journal, persistFailure: diagnostic.persistFailure,
    execute: value => dispatcher.dispatch(value) }), error => {
    assert.equal(error.code, 'DIAGNOSTIC_RETENTION_LIMIT');
    assert.equal(error.details.diagnostic.observed.child, 'not_started');
    assert.equal(error.details.diagnostic.containment, 'not_required');
    assert.equal(error.details.diagnostic.primaryCause, 'DIAGNOSTIC_RETENTION_LIMIT');
    return true;
  });
  assert.equal(f.comments.length, 1); assert.equal(f.pushes(), 0);
  assert.match(f.comments[0].body, /DIAGNOSTIC_RETENTION_LIMIT/);
  assert.doesNotMatch(f.comments[0].body, /CONTAINMENT_NOT_PROVEN/);
});

async function durableFixture(t) {
  const root = await mkdtemp(join(tmpdir(), 'relay-controller-retirement-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const fallbackRoot = join(root, 'fallback'); const primaryRoot = join(root, 'primary');
  const { writeDiagnosticBundle } = await import('../src/diagnostic-store.mjs');
  const store = value => writeDiagnosticBundle(value, { root: primaryRoot });
  const persist = value => persistAttemptFailureDiagnostic({ ...value, root: fallbackRoot,
    diagnosticStore: store, readConfig: async () => ({ mode: 'normal' }) });
  return { root, fallbackRoot, primaryRoot, store, persist };
}

test('more than eight known controller checkout failures archive and retire shared diagnostic capacity', async t => {
  const f = await durableFixture(t);
  for (let index = 0; index < 12; index++) {
    const envelope = currentEnvelope({ runId: 100 + index });
    const journal = memoryStore();
    const broker = { invoke: async request => request.operation === 'preflight' ? {} : {
      status: 'BLOCKED', head: null, prNumber: null, outcomeId: 1 } };
    await assert.rejects(runAttempt({ envelope, journal, broker, persistFailure: f.persist,
      prepare: async () => { throw Object.assign(new Error('checkout unavailable'), { code: 'EACCES', syscall: 'mkdir' }); },
      execute: () => assert.fail('no child may start'), collect: () => assert.fail('no checkout exists') }), error => {
      assert.equal(error.code, 'EACCES'); assert.equal(error.details.fallbackReference.status, 'released');
      assert.equal(error.details.diagnosticStore.executionId, `${envelope.attemptId}-finalization`); return true;
    });
    assert.equal(await openRuntimeDiagnostic({ executionId: envelope.attemptId, root: f.fallbackRoot }), null);
    const archive = JSON.parse(await readFile(join(f.primaryRoot, `${envelope.attemptId}-finalization.json`), 'utf8'));
    assert.equal(archive.lifecycle.controllerFailure.code, 'EACCES');
    assert.equal(archive.lifecycle.childState, 'not_started'); assert.equal(archive.lifecycle.containment, 'not_required');
    assert.equal(archive.lifecycle.cleanup, 'retained'); assert.equal(archive.lifecycle.retention, 'unknown');
    assert.equal(archive.lifecycle.diagnosticStore.executionId, envelope.attemptId);
  }
});

async function releasedRuntime(f, executionId, { primary = true } = {}) {
  const handle = await reserveRuntimeDiagnostic({ executionId, root: f.fallbackRoot });
  if (primary) await f.store({ schemaVersion: '1.0', executionId, mode: 'normal', originalRuntimeEvidence: 'preserved' });
  await handle.write({ childState: 'started', containment: 'reaped', cleanupContainment: 'reaped', cleanup: 'complete', retention: 'none',
    persistence: primary ? 'stored' : 'not_required', sandboxCreated: true, sandboxIdentity: { device: '123', inode: '456' },
    ...(primary ? { primaryCause: 'CODEX_NONZERO_EXIT', diagnosticStore: { status: 'stored', executionId, mode: 'normal' } } : {}) });
  await handle.release();
  return handle;
}
const controllerFailure = () => Object.assign(new Error('controller collection failed'), { code: 'EIO', syscall: 'read',
  details: { childState: 'started', containment: 'reaped' } });

test('a retired runtime failure refreshes final archive with controller facts and preserves original primary evidence', async t => {
  const f = await durableFixture(t); const handle = await releasedRuntime(f, 'run-39');
  const original = await readFile(join(f.primaryRoot, 'run-39.json'), 'utf8');
  const result = await f.persist({ executionId: 'run-39', error: controllerFailure(), stage: 'progress' });
  assert.equal(result.fallbackReference.status, 'released');
  assert.equal(result.diagnosticStore.executionId, 'run-39-finalization');
  assert.equal(await openRuntimeDiagnostic({ executionId: 'run-39', root: f.fallbackRoot }), null);
  const capsule = await handle.read();
  assert.equal(capsule.released, true); assert.equal(capsule.controllerFailure.code, 'EIO');
  assert.equal(capsule.diagnosticStore.executionId, 'run-39');
  assert.equal(capsule.primaryCause, 'CODEX_NONZERO_EXIT');
  const archive = JSON.parse(await readFile(join(f.primaryRoot, 'run-39-finalization.json'), 'utf8'));
  assert.equal(archive.lifecycle.controllerFailure.code, 'EIO');
  assert.equal(archive.lifecycle.diagnosticStore.executionId, 'run-39');
  assert.deepEqual(archive.lifecycle.sandboxIdentity, { device: '123', inode: '456' });
  assert.equal(await readFile(join(f.primaryRoot, 'run-39.json'), 'utf8'), original);
});

test('a retired successful runtime persists controller primary evidence before archiving and retiring again', async t => {
  const f = await durableFixture(t); const handle = await releasedRuntime(f, 'run-40', { primary: false });
  const result = await f.persist({ executionId: 'run-40', error: controllerFailure(), stage: 'progress' });
  assert.equal(result.fallbackReference.status, 'released');
  assert.equal(result.diagnosticStore.executionId, 'run-40-finalization');
  assert.equal((await handle.read()).diagnosticStore.executionId, 'run-40');
  const primary = JSON.parse(await readFile(join(f.primaryRoot, 'run-40.json'), 'utf8'));
  assert.equal(primary.runtimeFailure.code, 'EIO');
});

test('failed archive refresh retains the latest controller facts without claiming an old archive contains them', async t => {
  const f = await durableFixture(t); const handle = await releasedRuntime(f, 'run-41');
  await f.store({ schemaVersion: '1.0', executionId: 'run-41-finalization', mode: 'normal', oldArchiveOnly: true });
  const result = await persistAttemptFailureDiagnostic({ executionId: 'run-41', error: controllerFailure(), stage: 'progress', root: f.fallbackRoot,
    readConfig: async () => ({ mode: 'normal' }), diagnosticStore: async () => { throw Object.assign(new Error('disk full'), { code: 'ENOSPC' }); } });
  assert.equal(result.persistence, 'failed'); assert.equal(result.diagnosticStore.status, 'unavailable');
  assert.equal(result.diagnosticStore.executionId, 'run-41-finalization');
  assert.equal(result.fallbackReference.status, 'stored');
  const active = await openRuntimeDiagnostic({ executionId: 'run-41', root: f.fallbackRoot }); assert.ok(active);
  const capsule = await active.read(); assert.equal(capsule.released, undefined);
  assert.equal(capsule.controllerFailure.code, 'EIO'); assert.equal(capsule.diagnosticStore.executionId, 'run-41');
  assert.equal(capsule.terminalDiagnostic.status, 'unavailable');
  assert.equal(JSON.parse(await readFile(join(f.primaryRoot, 'run-41-finalization.json'), 'utf8')).oldArchiveOnly, true);
  await assert.rejects(handle.release(), { code: 'DIAGNOSTIC_FALLBACK_NOT_RELEASABLE' });
});

for (const protectedState of ['unknown-child', 'unknown-cleanup', 'pending-runtime', 'failed-runtime']) test(`${protectedState} remains protected after a controller report`, async t => {
  const f = await durableFixture(t);
  const handle = await reserveRuntimeDiagnostic({ executionId: 'run-50', root: f.fallbackRoot });
  const primaryStored = ['unknown-child', 'unknown-cleanup'].includes(protectedState);
  if (primaryStored) await f.store({ schemaVersion: '1.0', executionId: 'run-50', mode: 'normal', originalRuntimeEvidence: 'preserved' });
  await handle.write({ childState: protectedState === 'unknown-child' ? 'unknown' : 'started',
    containment: protectedState === 'unknown-child' ? 'unknown' : 'reaped',
    cleanupContainment: protectedState === 'unknown-cleanup' ? 'unknown' : 'reaped',
    cleanup: 'retained', retention: 'retained', sandboxCreated: true, sandboxIdentity: { device: '123', inode: '456' },
    persistence: primaryStored ? 'stored' : protectedState === 'failed-runtime' ? 'failed' : 'pending',
    ...(primaryStored ? { diagnosticStore: { status: 'stored', executionId: 'run-50', mode: 'normal' } } : {}) });
  const result = await f.persist({ executionId: 'run-50', error: controllerFailure(), stage: 'progress' });
  assert.notEqual(result.fallbackReference.status, 'released');
  if (protectedState === 'unknown-child') { assert.equal(result.childState, 'unknown'); assert.equal(result.containment, 'unknown'); }
  assert.ok(await openRuntimeDiagnostic({ executionId: 'run-50', root: f.fallbackRoot }));
  const state = await handle.read();
  assert.equal(state.persistence, primaryStored ? 'stored' : protectedState === 'failed-runtime' ? 'failed' : 'pending');
  await assert.rejects(handle.release(), { code: 'DIAGNOSTIC_FALLBACK_NOT_RELEASABLE' });
});

test('slot retirement failure preserves a successfully stored current archive reference', async t => {
  const f = await durableFixture(t); const handle = await releasedRuntime(f, 'run-60');
  const result = await persistAttemptFailureDiagnostic({ executionId: 'run-60', error: controllerFailure(), stage: 'progress', root: f.fallbackRoot,
    readConfig: async () => ({ mode: 'normal' }), diagnosticStore: f.store,
    fallbackOpen: async () => ({ ...handle, release: async () => { throw Object.assign(new Error('retirement denied'), { code: 'EACCES' }); } }) });
  assert.equal(result.persistence, 'stored'); assert.equal(result.diagnosticStore.status, 'stored');
  assert.equal(result.diagnosticStore.executionId, 'run-60-finalization');
  assert.equal(result.fallbackReference.status, 'unavailable'); assert.equal(result.fallbackReference.code, 'EACCES');
  const capsule = await handle.read(); assert.notEqual(capsule.released, true);
  assert.equal(capsule.terminalDiagnostic.status, 'stored');
  const archived = JSON.parse(await readFile(join(f.primaryRoot, 'run-60-finalization.json'), 'utf8'));
  assert.equal(archived.lifecycle.controllerFailure.code, 'EIO');
});
