import test from 'node:test';
import assert from 'node:assert/strict';
import { join } from 'node:path';
import { runAttempt } from '../src/attempt.mjs';
import { persistAttemptFailureDiagnostic } from '../src/attempt-diagnostic.mjs';
import { openRuntimeDiagnostic } from '../src/diagnostic-fallback.mjs';
import { createOnDemandDispatchAdapter } from '../src/github.mjs';
import { VERSION } from '../src/execution-contract.mjs';
import { fixture, memoryStore } from './fixture.mjs';

function unavailablePrimary(f) {
  const root = join(f.root, 'fallback');
  return {
    root,
    persistFailure: value => persistAttemptFailureDiagnostic({ ...value, root,
      readConfig: async () => ({ mode: 'normal' }),
      diagnosticStore: async () => { throw Object.assign(new Error('primary store unavailable'), { code: 'ENOSPC' }); } })
  };
}

test('checkout failure and unavailable primary diagnostics retain a private capsule and sanitized Outcome reference', async t => {
  const f = await fixture(t);
  const journal = memoryStore();
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
  assert.doesNotMatch(JSON.stringify(capsule), /private-fixture-value|\/private\//);
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

test('normal pre-execution domain decisions still terminalize without creating physical failure capsules', async t => {
  const f = await fixture(t);
  const result = await runAttempt({ ...f, journal: memoryStore(),
    prepare: async () => { throw Object.assign(new Error('existing checkout'), { code: 'CHECKOUT_ALREADY_EXISTS' }); },
    execute: () => assert.fail('domain blocker must not execute'),
    persistFailure: () => assert.fail('normal domain blocker needs no physical failure capsule') });
  assert.equal(result.status, 'BLOCKED'); assert.equal(f.comments.length, 1);
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
  await assert.rejects(runAttempt({ ...f, journal: memoryStore(), persistFailure: diagnostic.persistFailure,
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
