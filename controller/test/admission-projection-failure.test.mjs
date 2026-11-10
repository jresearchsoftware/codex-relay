import test from 'node:test';
import assert from 'node:assert/strict';
import { fixture, memoryStore } from './fixture.mjs';
import { createPublicationBroker } from '../src/publication-broker.mjs';
import { serializeWriterFailure } from '../src/privileged-writer-helper.mjs';
import { admissionFailure } from '../src/admission-diagnostic.mjs';
import { createAdmissionControl } from '../src/admission-control.mjs';
import { pendingPredispatchRecord } from '../src/predispatch-recovery.mjs';
import { nextAdmissionStep } from '../src/admission-step.mjs';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const charter = 'Authority model: github-native-v1\nIssue closure policy: keep-open\nExercise bounded admission diagnostics and same-attempt replay.';
const privatePath = '/srv/relay/private/admission-source.mjs';
const syntheticToken = `ghp_${'S'.repeat(36)}`;

test('durable pre-dispatch marker releases only proven non-execution and retains numbering', async t => {
  const f = await failedProjection(t, new Error('projection failed'));
  const record = await f.store.get(f.admissionRequest.runId);
  const gateRoot = await mkdtemp(join(tmpdir(), 'projection-gate-'));
  t.after(() => rm(gateRoot, { recursive: true, force: true }));
  const gate = createAdmissionControl({ root: gateRoot, consumerDigest: record.envelope.consumerDigest,
    store: f.store, journal: f.journal, protectedRoot: false });
  await gate.initialize();
  assert.ok(pendingPredispatchRecord(record));
  assert.deepEqual((await gate.status()).active, []);
  assert.deepEqual((await gate.status()).unknown, []);
  await gate.assertSlotComplete('primary');
  assert.equal(nextAdmissionStep([record], record.envelope.issueNumber, [{ name: 'step-1' }]).step, 3);
  const deleting = structuredClone(record);
  deleting.readyConsumption = { status: 'deleting', eventId: record.envelope.readyEventId, label: record.envelope.readyLabel };
  assert.ok(pendingPredispatchRecord(deleting));
  deleting.readyConsumed = true;
  assert.equal(pendingPredispatchRecord(deleting), false);
  await f.journal.put(record.envelope.runId, { unexpected: true });
  assert.deepEqual((await gate.status()).unknown, [record.envelope.runId]);
});

for (const boundary of ['projection-receipt', 'ready-delete-intent']) {
  test(`interrupted Writer retains its pre-dispatch proof at ${boundary}`, async t => {
    let stopped = false;
    const f = await failedProjection(t, new Error('unused'), ({ api, store }) => {
      api.ensureStepLabel = async () => {};
      const put = store.put;
      store.put = async (id, record) => {
        await put(id, record);
        if (!stopped && (boundary === 'projection-receipt' ? record.stepProjected === true
          : record.readyConsumption?.status === 'deleting')) {
          stopped = true;
          throw Object.assign(new Error('simulated interruption after atomic write'), { code: 'EIO' });
        }
      };
    });
    assert.equal(stopped, true);
    const record = await f.store.get(f.admissionRequest.runId);
    assert.equal(pendingPredispatchRecord(record), true);
    assert.equal(record.readyConsumed, undefined);
    assert.equal(await f.journal.get(record.envelope.runId), null);
  });
}

async function failedProjection(t, cause, configure = () => {}) {
  let state;
  let failure;
  let mutations = 0;
  const journal = memoryStore();
  await assert.rejects(fixture(t, { issueBody: charter, labelLaunch: true, streamlinedAdmission: true,
    createJournal: () => journal,
    createAdmission: async () => ({ assertOpen: async () => {}, assertSlotComplete: async () => {},
      reserve: async () => ({ version: 1, status: 'active' }) }),
    beforeAdmission(value) {
      state = value;
      state.issue.labels = [{ name: 'step-1' }, { name: 'codex-ready-auto' }];
      for (const method of ['delete', 'post', 'patch']) {
        const original = state.api[method];
        state.api[method] = async (...args) => { mutations++; return original(...args); };
      }
      state.api.ensureStepLabel = async () => { mutations++; throw cause; };
      configure(state);
    }
  }), error => { failure = error; return true; });
  return { ...state, journal, failure, mutationCount: () => mutations,
    resetMutations: () => { mutations = 0; } };
}

test('uncoded Step projection failure retains a private redacted exception and exposes a bounded safe classification', async t => {
  const message = `Projection implementation failed at ${privatePath} with ${syntheticToken}`;
  const f = await failedProjection(t, new TypeError(message));
  const record = await f.store.get(f.admissionRequest.runId);
  assert.equal(f.failure.code, 'ADMISSION_STEP_PROJECTION_FAILED');
  assert.equal(record.envelope.step, 2);
  assert.deepEqual(record.stepProjectionFrom, ['step-1']);
  assert.equal(record.stepProjected, undefined);
  assert.equal(record.readyConsumption, undefined);
  assert.equal(record.readyConsumed, undefined);
  assert.deepEqual(record.controllerLifecycle, { version: 1, status: 'active' });
  assert.equal(record.admissionFailure.exception.name, 'TypeError');
  assert.match(record.admissionFailure.exception.text, /Projection implementation failed/);
  assert.ok(record.admissionFailure.exception.text.includes(privatePath));
  assert.ok(!record.admissionFailure.exception.text.includes(syntheticToken));
  assert.match(record.admissionFailure.exception.text, /\[REDACTED_GITHUB_TOKEN\]/);
  assert.ok(Buffer.byteLength(record.admissionFailure.exception.text, 'utf8') <= 8192);
  assert.equal(record.admissionFailure.diagnostic.operation, 'step-label-ensure');
  assert.equal(record.admissionFailure.diagnostic.code, 'ADMISSION_STEP_PROJECTION_FAILED');
  const wire = serializeWriterFailure(f.failure);
  assert.equal(wire.code, 'ADMISSION_STEP_PROJECTION_FAILED');
  assert.equal(wire.failureDiagnostic.operation, 'step-label-ensure');
  assert.match(wire.failureDiagnostic.preview, /TypeError/);
  const encoded = JSON.stringify(wire);
  assert.ok(!encoded.includes(privatePath));
  assert.ok(!encoded.includes(syntheticToken));
  assert.ok(!encoded.includes('Projection implementation failed'));
  assert.ok(!encoded.includes('exception'));
  assert.equal(f.mutationCount(), 1);
});

test('coded HTTP projection failure preserves its code and HTTP status separately from an uncoded exception', async t => {
  const f = await failedProjection(t, Object.assign(new Error(`Denied at ${privatePath}: ${syntheticToken}`),
    { code: 'GITHUB_REQUEST_FAILED', status: 403 }));
  const record = await f.store.get(f.admissionRequest.runId);
  assert.equal(f.failure.code, 'GITHUB_REQUEST_FAILED');
  assert.equal(record.admissionFailure.exception.name, 'Error');
  assert.equal(record.admissionFailure.exception.status, 403);
  assert.equal(record.admissionFailure.diagnostic.operation, 'step-label-ensure');
  const wire = serializeWriterFailure(f.failure);
  assert.equal(wire.code, 'GITHUB_REQUEST_FAILED');
  assert.match(wire.failureDiagnostic.preview, /HTTP 403/);
  assert.ok(!JSON.stringify(wire).includes(privatePath));
  assert.ok(!JSON.stringify(wire).includes(syntheticToken));
});

test('accepted Step label mutation with a lost response preserves partial native state without consuming the ready command', async t => {
  let readyDeletes = 0;
  let labelAdds = 0;
  const cause = Object.assign(new Error('Synthetic lost label response'), { code: 'ECONNRESET' });
  const f = await failedProjection(t, cause, ({ api }) => {
    api.ensureStepLabel = async () => {};
    const post = api.post;
    api.post = async (path, body) => {
      const result = await post(path, body);
      if (path === '/issues/42/labels' && body.labels.includes('step-2')) {
        labelAdds++;
        throw cause;
      }
      return result;
    };
    const remove = api.delete;
    api.delete = async path => {
      if (path.endsWith('/labels/codex-ready-auto')) readyDeletes++;
      return remove(path);
    };
  });
  const record = await f.store.get(f.admissionRequest.runId);
  assert.equal(f.failure.code, 'ECONNRESET');
  assert.equal(record.admissionFailure.diagnostic.operation, 'step-label-add');
  assert.deepEqual(f.issue.labels, [{ name: 'codex-ready-auto' }, { name: 'step-2' }]);
  assert.deepEqual(record.stepProjectionFrom, ['step-1']);
  assert.equal(record.stepProjected, undefined);
  assert.equal(record.readyConsumption, undefined);
  assert.equal(record.readyConsumed, undefined);
  assert.deepEqual(record.controllerLifecycle, { version: 1, status: 'active' });
  assert.equal(labelAdds, 1);
  assert.equal(readyDeletes, 0);
  const labels = structuredClone(f.issue.labels);
  f.resetMutations();
  const broker = createPublicationBroker({ api: f.api, store: f.store, publisher: {}, journal: f.journal });
  await assert.rejects(broker.dispatch(f.admissionRequest), { code: 'JOURNAL_MISSING_EXECUTION_UNKNOWN' });
  assert.equal(labelAdds, 1);
  assert.equal(readyDeletes, 0);
  assert.equal(f.mutationCount(), 0);
  assert.deepEqual(f.issue.labels, labels);
  assert.deepEqual(await f.store.get(record.envelope.runId), record);
});

test('failed private diagnostic retention preserves the primary projection error and reports retention as unverified', async t => {
  let writes = 0;
  const f = await failedProjection(t, new TypeError(`Original projection failure at ${privatePath}: ${syntheticToken}`), ({ store }) => {
    const put = store.put;
    store.put = async (...args) => {
      writes++;
      if (writes > 1) throw Object.assign(new Error('Synthetic protected store failure'), { code: 'EIO' });
      return put(...args);
    };
  });
  const record = await f.store.get(f.admissionRequest.runId);
  assert.equal(writes, 2);
  assert.equal(record.admissionFailure, undefined);
  assert.deepEqual(record.controllerLifecycle, { version: 1, status: 'active' });
  assert.equal(record.readyConsumption, undefined);
  assert.equal(record.readyConsumed, undefined);
  const wire = serializeWriterFailure(f.failure);
  assert.equal(f.failure.code, 'ADMISSION_STEP_PROJECTION_FAILED');
  assert.equal(wire.code, 'ADMISSION_STEP_PROJECTION_FAILED');
  assert.equal(wire.failureDiagnostic.operation, 'step-label-ensure');
  assert.match(wire.failureDiagnostic.preview, /TypeError/);
  assert.match(wire.failureDiagnostic.preview, /diagnostic write also failed; retention is unverified/);
  assert.ok(!JSON.stringify(wire).includes(privatePath));
  assert.ok(!JSON.stringify(wire).includes(syntheticToken));
  assert.ok(!JSON.stringify(wire).includes('EIO'));
});

test('known opaque secrets are redacted before private Unicode exception text is bounded by UTF-8 bytes', () => {
  const opaqueSecret = 'opaque-fixture-credential-123456789';
  const error = new TypeError('Synthetic long private stack');
  error.stack = `TypeError: credential ${opaqueSecret}\n${'😀漢'.repeat(6000)}`;
  const result = admissionFailure(error, 'step-label-ensure', 'run-99', [opaqueSecret]);
  assert.equal(result.exception.name, 'TypeError');
  assert.ok(!result.exception.text.includes(opaqueSecret));
  assert.match(result.exception.text, /\[REDACTED_SECRET\]/);
  assert.equal(result.exception.truncated, true);
  assert.ok(result.exception.bytes > 8192);
  assert.ok(Buffer.byteLength(result.exception.text, 'utf8') <= 8192);
  assert.ok(!result.exception.text.includes('\ufffd'));
  assert.equal(new TextDecoder('utf-8', { fatal: true }).decode(Buffer.from(result.exception.text)), result.exception.text);
  assert.equal(result.diagnostic.code, 'ADMISSION_STEP_PROJECTION_FAILED');
  assert.equal(result.diagnostic.operation, 'step-label-ensure');
  assert.equal(Object.hasOwn(result.diagnostic, 'workerStarted'), false);
  assert.equal(Object.hasOwn(result.diagnostic, 'childState'), false);
  assert.match(result.diagnostic.preview, /This admission call did not return launch authority/);
  assert.ok(!JSON.stringify(result.diagnostic).includes(opaqueSecret));
});

test('publication-state inspects a partial admission without returning its private exception or mutating native metadata', async t => {
  const f = await failedProjection(t, new TypeError(`Sensitive failure at ${privatePath}: ${syntheticToken}`));
  const record = await f.store.get(f.admissionRequest.runId);
  f.resetMutations();
  const broker = createPublicationBroker({ api: f.api, store: f.store, publisher: {}, journal: f.journal });
  const inspected = await broker.dispatch({ operation: 'publication-state', runId: record.envelope.runId,
    attemptId: record.envelope.attemptId });
  assert.deepEqual(inspected.envelope, record.envelope);
  assert.equal(inspected.admissionState.step, 2);
  assert.equal(inspected.admissionState.stepProjected, null);
  assert.deepEqual(inspected.admissionState.stepProjectionFrom, ['step-1']);
  assert.equal(inspected.admissionState.readyEventId, record.envelope.readyEventId);
  assert.equal(inspected.admissionState.readyConsumption, null);
  assert.equal(inspected.admissionState.readyConsumed, null);
  assert.deepEqual(inspected.admissionState.controllerLifecycle, { version: 1, status: 'active' });
  assert.equal(inspected.admissionState.failureDiagnostic.operation, 'step-label-ensure');
  const encoded = JSON.stringify(inspected);
  assert.ok(!encoded.includes('exception'));
  assert.ok(!encoded.includes(privatePath));
  assert.ok(!encoded.includes(syntheticToken));
  assert.equal(f.mutationCount(), 0);
  assert.deepEqual(await f.store.get(record.envelope.runId), record);
});

for (const [name, journalRecord, code] of [
  ['unavailable original journal reader', null, 'JOURNAL_MISSING_EXECUTION_UNKNOWN'],
  ['missing original journal', () => null, 'JOURNAL_MISSING_EXECUTION_UNKNOWN'],
  ['malformed original journal', envelope => ({ version: 2, envelope }), 'JOURNAL_MISSING_EXECUTION_UNKNOWN'],
  ['wrong journal version', envelope => ({ version: 1, envelope, execution: null }), 'JOURNAL_MISSING_EXECUTION_UNKNOWN'],
  ['mismatched original journal', envelope => ({ version: 2,
    envelope: { ...envelope, attemptId: 'run-100' }, execution: null }), 'JOURNAL_BINDING_CHANGED']
]) {
  test(`same-run partial admission replay rejects ${name} before Step or ready-label mutations`, async t => {
    const f = await failedProjection(t, new TypeError('Synthetic projection failure'));
    const original = await f.store.get(f.admissionRequest.runId);
    // Model the original installed incident, which predates the new diagnostic.
    delete original.admissionFailure;
    await f.store.put(original.envelope.runId, original);
    const labels = structuredClone(f.issue.labels);
    f.resetMutations();
    const broker = createPublicationBroker({ api: f.api, store: f.store, publisher: {},
      journal: journalRecord ? { get: async () => journalRecord(original.envelope) } : undefined });
    await assert.rejects(broker.dispatch(f.admissionRequest), { code });
    assert.equal(f.mutationCount(), 0);
    assert.deepEqual(f.issue.labels, labels);
    assert.deepEqual(await f.store.get(original.envelope.runId), original);
    assert.deepEqual(original.controllerLifecycle, { version: 1, status: 'active' });
    assert.equal(original.readyConsumption, undefined);
    assert.equal(original.readyConsumed, undefined);
  });
}
