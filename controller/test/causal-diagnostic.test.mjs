import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { EventEmitter } from 'node:events';
import { PassThrough } from 'node:stream';
import { captureCausalDiagnostic, createExecutionDiagnostic, persistExecutionDiagnostic, safeFailureDiagnosticReference } from '../src/diagnostics.mjs';
import { normalizeRuntimeCapsule, reserveRuntimeDiagnostic, RUNTIME_FALLBACK_BYTES } from '../src/diagnostic-fallback.mjs';

test('protected causal evidence preserves original exception, HTTP fields and native observation while public references exclude them', () => {
  const original = Object.assign(new Error('upstream policy rejected request token=fixture-secret'), {
    status: 403, syscall: 'connect', native: { response: { error: { code: 'POLICY_DENIED', message: 'upstream denied', authorization: 'Bearer native-secret' } } }
  });
  const outer = Object.assign(new Error('operation failed', { cause: original }), {
    observation: { expected: 'permitted', observed: 'denied' }
  });
  const value = createExecutionDiagnostic({ executionId: 'run-244', mode: 'normal', phase: 'worker',
    error: outer, runtimeFailure: { operation: 'native-request' }, stdout: 'native stdout cause', stderr: 'native stderr cause', exitCode: 9,
    secrets: { knownSecrets: ['fixture-secret', 'native-secret'] } });
  const text = JSON.stringify(value.causalEvidence);
  assert.match(text, /upstream policy rejected|POLICY_DENIED|403|connect|denied/);
  assert.match(text, /causal-diagnostic.test.mjs/);
  assert.doesNotMatch(text, /fixture-secret|native-secret|Bearer native/);
  assert.equal(value.causalEvidence.stdout.available, true);
  assert.equal(value.causalEvidence.process.exitCode, 9);
  assert.deepEqual(safeFailureDiagnosticReference({ code: 'EXECUTION_FAILED', causalEvidence: value.causalEvidence }), { code: 'EXECUTION_FAILED' });
});

test('bounded causal observations retain clipping and unavailability through fallback reopen', async t => {
  const root = await mkdtemp(join(tmpdir(), 'relay-causal-bound-')); t.after(() => rm(root, { recursive: true, force: true }));
  const original = captureCausalDiagnostic({ executionId: 'run-244', phase: 'worker', operation: 'native-request',
    error: new Error('failure '.repeat(30000)), stdout: { value: '\\"😀'.repeat(30000), total: 999999, truncated: true },
    native: { error: { message: 'response '.repeat(30000), token: 'must-not-survive' } } });
  const recorder = captureCausalDiagnostic({ error: Object.assign(new Error('disk is full'), { code: 'ENOSPC' }), phase: 'diagnostic-persistence', operation: 'persist-primary' });
  const normalized = normalizeRuntimeCapsule({ causalEvidence: original, secondaryEvidence: original, recorderFailure: recorder }, 'run-244');
  assert.ok(Buffer.byteLength(JSON.stringify(normalized)) < RUNTIME_FALLBACK_BYTES);
  const capsule = await reserveRuntimeDiagnostic({ executionId: 'run-244', root });
  await capsule.write(normalized);
  const saved = await capsule.read();
  assert.equal(saved.causalEvidence.stdout.bytes, 999999);
  assert.equal(saved.causalEvidence.stdout.truncated, true);
  assert.deepEqual(saved.causalEvidence.stderr, { available: false, reason: 'not_observed' });
  assert.match(saved.recorderFailure.exception.text, /disk is full|ENOSPC/);
  assert.doesNotMatch(JSON.stringify(saved), /must-not-survive/);
});

test('diagnostic helper failure retains its own original stderr, signal and store cause', async () => {
  await assert.rejects(persistExecutionDiagnostic({ executionId: 'run-244', mode: 'normal' }, { spawnImpl() {
    const child = new EventEmitter(); child.stdout = new PassThrough(); child.stderr = new PassThrough(); child.stdin = new PassThrough();
    child.stdin.resume();
    setImmediate(() => {
      child.stderr.end('native store policy denied operation token=store-private');
      child.stdout.end('{"code":"EACCES"}'); child.emit('close', 9, 'SIGTERM');
    });
    return child;
  } }), error => {
    const cause = captureCausalDiagnostic({ error, executionId: 'run-244', phase: 'diagnostic-persistence', operation: 'persist-primary' });
    assert.match(cause.exception.text, /native store policy denied|EACCES/);
    assert.equal(cause.process.exitCode, 9); assert.equal(cause.process.signal, 'SIGTERM');
    assert.doesNotMatch(JSON.stringify(cause), /store-private/);
    return true;
  });
});

test('clipped captures redact a known partial credential and JSON secret values before persistence', () => {
  const value = createExecutionDiagnostic({ executionId: 'run-244', mode: 'debug', phase: 'worker',
    stdout: 'native output exact-credential-pre', stdoutTruncated: true,
    stderr: '{"token":"json-credential","authorization":"Bearer header-credential"}',
    secrets: { knownSecrets: ['exact-credential-prefix-and-rest'] } });
  assert.doesNotMatch(JSON.stringify(value), /exact-credential-pre|json-credential|header-credential/);
  assert.equal(value.stdout.truncated, true);
});
