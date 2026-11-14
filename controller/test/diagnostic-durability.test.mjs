import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, readdir, rm, symlink, link, chmod, writeFile, stat } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { reserveRuntimeDiagnostic, openRuntimeDiagnostic, RUNTIME_FALLBACK_LIMIT, RUNTIME_FALLBACK_BYTES } from '../src/diagnostic-fallback.mjs';
import { safeFailureDiagnosticReference, createExecutionDiagnostic } from '../src/diagnostics.mjs';
import { causalEvidence, safeDomainTerminal } from '../src/execution-contract.mjs';
import { terminalOutcomeBody } from '../src/outcome.mjs';
import { createOnDemandDispatchAdapter } from '../src/github.mjs';
import { currentEnvelope } from './fixture.mjs';
import { finalizeRuntimeArtifacts } from '../../runtime/src/runtime-finalization.mjs';
import { writeDiagnosticBundle } from '../src/diagnostic-store.mjs';

async function fixture(t) {
  const root = await mkdtemp(join(tmpdir(), 'relay-fallback-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  return root;
}

test('independent capsule survives reopening and primary store failure without raw paths or secrets', async t => {
  const root = await fixture(t);
  const handle = await reserveRuntimeDiagnostic({ executionId: 'run-39', root });
  await handle.write({ executionId: 'run-39', stage: 'diagnostic-persistence', operation: 'write-diagnostic',
    primaryCause: 'EACCES', syscall: 'open', pathContext: 'diagnostic-store',
    childState: 'started', childExitCode: 0, containment: 'reaped', cleanup: 'retained', persistence: 'failed', retention: 'retained',
    lastSuccessfulBoundary: 'result-parse', sandboxCreated: true, inputSchemaCreated: true,
    sandboxIdentity: { device: '1234', inode: '9876' },
    diagnosticStore: { status: 'unavailable', executionId: 'run-39', code: 'DIAGNOSTICS_STORE_FAILED', storeCode: 'EACCES', path: '/private/secret' },
    failureDiagnostic: { code: 'EACCES', syscall: 'open', preview: 'token=private-fixture', path: '/private/secret' },
    path: '/private/secret', preview: 'private stdout '.repeat(10000), stack: 'private stack' });
  const reopened = await openRuntimeDiagnostic({ executionId: 'run-39', root });
  const saved = await reopened.read();
  assert.deepEqual(reopened.reference, { status: 'stored', executionId: 'run-39', slot: 0 });
  assert.equal(saved.primaryCause, 'EACCES'); assert.equal(saved.retention, 'retained');
  assert.deepEqual(saved.sandboxIdentity, { device: '1234', inode: '9876' });
  assert.equal(saved.diagnosticStore.storeCode, 'EACCES');
  const text = await readFile(join(root, '0', 'run-39.json'), 'utf8');
  assert.ok(Buffer.byteLength(text) <= RUNTIME_FALLBACK_BYTES);
  assert.doesNotMatch(text, /private|secret|stdout|stack/);
  if (process.platform !== 'win32') assert.equal((await stat(join(root, '0', 'run-39.json'))).mode & 0o777, 0o600);
});

test('occupied unknown and retained slots impose a concurrent hard bound instead of evicting evidence', async t => {
  const root = await fixture(t);
  const results = await Promise.allSettled(Array.from({ length: RUNTIME_FALLBACK_LIMIT + 4 }, (_, index) =>
    reserveRuntimeDiagnostic({ executionId: `run-${index + 1}`, root })));
  assert.equal(results.filter(value => value.status === 'fulfilled').length, RUNTIME_FALLBACK_LIMIT);
  for (const result of results.filter(value => value.status === 'rejected')) assert.equal(result.reason.code, 'DIAGNOSTIC_RETENTION_LIMIT');
  assert.equal((await readdir(root)).length, RUNTIME_FALLBACK_LIMIT);
  const first = results.find(value => value.status === 'fulfilled').value;
  await first.write({ cleanup: 'complete', persistence: 'not_required', retention: 'none' });
  await first.release();
  assert.equal(await openRuntimeDiagnostic({ executionId: first.reference.executionId, root }), null);
  await reserveRuntimeDiagnostic({ executionId: 'run-replacement', root });
  assert.equal((await readdir(root)).length, RUNTIME_FALLBACK_LIMIT);
});

test('successful cleanup releases a durable bounded tombstone; residue remains inspectable', async t => {
  const root = await fixture(t);
  const handle = await reserveRuntimeDiagnostic({ executionId: 'run-success', root });
  await handle.write({ cleanup: 'complete', persistence: 'not_required', retention: 'none' });
  await handle.release(); assert.deepEqual(await readdir(root), ['0']);
  assert.equal(await openRuntimeDiagnostic({ executionId: 'run-success', root }), null);
  const tombstone = await openRuntimeDiagnostic({ executionId: 'run-success', root, includeReleased: true });
  assert.equal((await tombstone.read()).released, true);
  const retained = await reserveRuntimeDiagnostic({ executionId: 'run-retained', root });
  await writeFile(join(root, '0', '.pending'), 'protected evidence', { mode: 0o600 });
  await assert.rejects(retained.release(), { code: 'DIAGNOSTIC_FALLBACK_RESIDUE' });
  assert.equal((await retained.read()).executionId, 'run-retained');
});

test('released slots are reclaimed at most once under concurrent reservation and interrupted claims stay bounded', async t => {
  const root = await fixture(t);
  const handles = [];
  for (let index = 0; index < RUNTIME_FALLBACK_LIMIT; index += 1) handles.push(await reserveRuntimeDiagnostic({ executionId: `done-${index}`, root }));
  for (const handle of handles) {
    await handle.write({ cleanup: 'complete', persistence: 'not_required', retention: 'none' });
    await handle.release();
  }
  const results = await Promise.allSettled(Array.from({ length: RUNTIME_FALLBACK_LIMIT + 4 }, (_, index) => reserveRuntimeDiagnostic({ executionId: `next-${index}`, root })));
  assert.equal(results.filter(value => value.status === 'fulfilled').length, RUNTIME_FALLBACK_LIMIT);
  for (const result of results.filter(value => value.status === 'rejected')) assert.equal(result.reason.code, 'DIAGNOSTIC_RETENTION_LIMIT');
  for (const name of await readdir(root)) assert.equal((await readdir(join(root, name))).length, 1);
});

test('fallback rejects foreign execution IDs, symlinks, hardlinks and unsafe modes', { skip: process.platform === 'win32' }, async t => {
  const root = await fixture(t);
  await assert.rejects(reserveRuntimeDiagnostic({ executionId: '../outside', root }), { code: 'DIAGNOSTIC_ID_INVALID' });
  const handle = await reserveRuntimeDiagnostic({ executionId: 'run-safe', root });
  await assert.rejects(handle.write({ executionId: 'different' }), { code: 'DIAGNOSTIC_FALLBACK_INVALID' });
  await assert.rejects(reserveRuntimeDiagnostic({ executionId: 'run-safe', root }), { code: 'DIAGNOSTIC_FALLBACK_EXISTS' });
  const path = join(root, '0', 'run-safe.json');
  await link(path, join(root, 'linked'));
  await assert.rejects(handle.read(), { code: 'DIAGNOSTIC_FALLBACK_UNSAFE' });
  await rm(join(root, 'linked'));
  await chmod(path, 0o644);
  await assert.rejects(handle.write({ cleanup: 'complete' }), { code: 'DIAGNOSTIC_FALLBACK_UNSAFE' });
  await chmod(path, 0o600);
  const alias = join(root, 'alias'); await symlink(join(root, '0'), alias);
  await assert.rejects(reserveRuntimeDiagnostic({ executionId: 'run-link', root: alias }), { code: 'DIAGNOSTIC_FALLBACK_UNSAFE' });
});

test('cleanup evidence and safe references survive repeated causal boundaries and sanitized Outcome publication', () => {
  const source = { primaryCause: 'EPERM', stage: 'cleanup', boundary: 'cleanup', operation: 'sandbox-cleanup', syscall: 'rmdir',
    pathContext: 'sandbox', childState: 'started', childExitCode: 0, signal: 'SIGTERM',
    cleanup: 'failed', persistence: 'stored', retention: 'retained', containment: 'reaped',
    diagnosticStore: { status: 'stored', executionId: 'run-39', mode: 'normal', path: '/private/secret' },
    fallbackReference: { status: 'stored', executionId: 'run-39', slot: 2, path: '/private/secret' },
    path: '/private/secret', preview: 'token=private-fixture' };
  const first = causalEvidence({ code: 'EPERM', details: { failureDiagnostic: source, lastSuccessfulBoundary: 'result-parse' } }, { containment: 'reaped' });
  const final = causalEvidence({ code: 'EPERM', details: { causal: first } }, { containment: 'reaped' });
  assert.equal(final.primaryCause, 'EPERM'); assert.equal(final.failureBoundary, 'cleanup');
  assert.equal(final.runtime.syscall, 'rmdir'); assert.equal(final.runtime.retention, 'retained');
  assert.equal(final.observed.signal, 'SIGTERM'); assert.equal(final.durable.fallbackReference.slot, 2);
  const outcome = terminalOutcomeBody({ attemptId: 'run-39', thread: 'Task 39' }, { terminalCode: 'EPERM', diagnostic: final });
  assert.match(outcome, /Failed operation: sandbox-cleanup; syscall: rmdir; path context: sandbox/);
  assert.match(outcome, /artifacts=retained/); assert.match(outcome, /Fallback diagnostics: stored; reference: run-39; slot: 2/);
  assert.doesNotMatch(outcome, /private|secret/);
  const hostile = safeFailureDiagnosticReference({ ...source, syscall: 'open /private', pathContext: '/private', cleanup: 'delete-everything', fallbackReference: { status: 'stored', executionId: '../../private', slot: 999 } });
  assert.equal(hostile.syscall, undefined); assert.equal(hostile.pathContext, undefined); assert.equal(hostile.cleanup, undefined);
  assert.deepEqual(hostile.fallbackReference, { status: 'stored' });
});

test('richer protected runtime failure paths stay bounded and redact known credentials', () => {
  const diagnostic = createExecutionDiagnostic({ executionId: 'run-39', mode: 'normal',
    runtimeFailure: { code: 'EACCES', operation: 'sandbox-cleanup', syscall: 'scandir', path: `/tmp/token=credential-fixture/${'x'.repeat(4096)}`,
      dest: '/home/credential-fixture/tmp', preview: 'private output' }, secrets: { knownSecrets: ['credential-fixture'] } });
  assert.equal(diagnostic.runtimeFailure.code, 'EACCES'); assert.equal(diagnostic.runtimeFailure.syscall, 'scandir');
  assert.ok(Buffer.byteLength(diagnostic.runtimeFailure.path) <= 1024);
  assert.doesNotMatch(JSON.stringify(diagnostic), /credential-fixture|private output/);
});

test('known worker domain results cannot hide physical cleanup or diagnostic failure', () => {
  const head = 'a'.repeat(40);
  const record = { envelope: { startHead: head }, collection: { clean: true, head },
    execution: { child: 'started', containment: 'reaped', reserved: true, returned: true, diagnostic: {} } };
  const failure = { code: 'CODEX_RESULT_INVALID' };
  assert.equal(safeDomainTerminal(failure, record, 'execution'), true);
  for (const runtime of [{ cleanup: 'failed' }, { cleanup: 'retained' }, { persistence: 'failed' }]) {
    record.execution.diagnostic.runtime = runtime;
    assert.equal(safeDomainTerminal(failure, record, 'execution'), false);
  }
  record.execution.diagnostic.runtime = { cleanup: 'complete', persistence: 'stored' };
  assert.equal(safeDomainTerminal(failure, record, 'execution'), true);
});

test('retained-resource capsules retire only with exact independent final diagnostic and containment proof', async t => {
  for (const missing of ['none', 'archive', 'archive-identity', 'child', 'cleanup-process', 'persistence']) await t.test(missing, async t => {
    const root = await fixture(t);
    const handle = await reserveRuntimeDiagnostic({ executionId: 'run-39', root });
    const state = { cleanup: 'failed', retention: 'retained', persistence: 'stored', childState: 'started',
      containment: 'reaped', cleanupContainment: 'reaped', sandboxCreated: true, sandboxIdentity: { device: '123', inode: '456' },
      terminalDiagnostic: { status: 'stored', executionId: 'run-39-finalization', mode: 'normal' } };
    if (missing === 'archive') delete state.terminalDiagnostic;
    if (missing === 'archive-identity') state.terminalDiagnostic.executionId = 'run-38-finalization';
    if (missing === 'child') state.containment = 'unknown';
    if (missing === 'cleanup-process') state.cleanupContainment = 'unknown';
    if (missing === 'persistence') state.persistence = 'failed';
    await handle.write(state);
    if (missing !== 'none') {
      await assert.rejects(handle.release(), { code: 'DIAGNOSTIC_FALLBACK_NOT_RELEASABLE' });
      assert.ok(await openRuntimeDiagnostic({ executionId: 'run-39', root })); return;
    }
    await handle.release();
    assert.equal(await openRuntimeDiagnostic({ executionId: 'run-39', root }), null);
    const released = await handle.read();
    assert.equal(released.cleanup, 'failed'); assert.equal(released.retention, 'retained');
    assert.deepEqual(released.sandboxIdentity, state.sandboxIdentity);
    const next = await reserveRuntimeDiagnostic({ executionId: 'run-40', root });
    assert.equal(next.reference.slot, handle.reference.slot);
    assert.equal((await next.read()).executionId, 'run-40');
  });
});

test('repeated native dispatcher spawn failures archive their proven no-child state and reuse bounded slots', async t => {
  const root = await fixture(t); const fallbackRoot = join(root, 'fallback'); const primaryRoot = join(root, 'primary');
  let spawns = 0;
  const adapter = createOnDemandDispatchAdapter({
    reserveDiagnostic: ({ executionId }) => reserveRuntimeDiagnostic({ executionId, root: fallbackRoot }),
    spawnImpl: () => { spawns++; throw Object.assign(new Error('dispatch could not start'), { code: 'EACCES', syscall: 'spawn' }); },
    finalizeArtifacts: options => finalizeRuntimeArtifacts({ ...options,
      diagnosticStore: value => writeDiagnosticBundle(value, { root: primaryRoot }),
      cleanupSandbox: () => assert.fail('no runtime mutation occurred') }) });
  for (let index = 0; index < 12; index++) {
    const envelope = currentEnvelope({ runId: 300 + index });
    await assert.rejects(adapter.dispatch(envelope), error => {
      assert.equal(error.code, 'DISPATCH_NOT_STARTED');
      assert.equal(error.details.childState, 'not_started'); assert.equal(error.details.containment, 'not_required');
      assert.equal(error.details.fallbackReference.status, 'released');
      assert.equal(error.details.diagnosticStore.executionId, `${envelope.attemptId}-finalization`);
      return true;
    });
    const archive = JSON.parse(await readFile(join(primaryRoot, `${envelope.attemptId}-finalization.json`), 'utf8'));
    assert.equal(archive.lifecycle.childState, 'not_started'); assert.equal(archive.lifecycle.primaryCause, 'EACCES');
    assert.equal(archive.lifecycle.persistence, 'not_required'); assert.equal(archive.lifecycle.cleanup, 'not_required');
    assert.equal(await openRuntimeDiagnostic({ executionId: envelope.attemptId, root: fallbackRoot }), null);
  }
  assert.equal(spawns, 12); assert.equal((await readdir(fallbackRoot)).length, 1);
});

test('proven no-runtime dispatch archive follows the existing debug diagnostics configuration', async t => {
  const root = await fixture(t); const fallbackRoot = join(root, 'fallback'); const primaryRoot = join(root, 'primary');
  const envelope = currentEnvelope({ runId: 900 });
  const adapter = createOnDemandDispatchAdapter({
    reserveDiagnostic: ({ executionId }) => reserveRuntimeDiagnostic({ executionId, root: fallbackRoot }),
    spawnImpl: () => { throw Object.assign(new Error('dispatch could not start'), { code: 'EACCES', syscall: 'spawn' }); },
    finalizeArtifacts: options => finalizeRuntimeArtifacts({ ...options, readDiagnosticConfig: async () => ({ mode: 'debug' }),
      diagnosticStore: value => writeDiagnosticBundle(value, { root: primaryRoot, mode: 'debug' }),
      cleanupSandbox: () => assert.fail('no runtime mutation occurred') }) });
  await assert.rejects(adapter.dispatch(envelope), error => {
    assert.equal(error.code, 'DISPATCH_NOT_STARTED'); assert.equal(error.details.fallbackReference.status, 'released');
    assert.equal(error.details.diagnosticStore.mode, 'debug'); return true;
  });
  const archived = JSON.parse(await readFile(join(primaryRoot, 'run-900-finalization.json'), 'utf8'));
  assert.equal(archived.mode, 'debug');
});
