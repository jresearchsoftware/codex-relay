import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { recordHostFailure } from '../src/host-failure-diagnostic.mjs';
import { writeDiagnosticBundle } from '../src/diagnostic-store.mjs';
import { reserveRuntimeDiagnostic, openRuntimeDiagnostic } from '../src/diagnostic-fallback.mjs';
import { createPublicationBroker } from '../src/publication-broker.mjs';
import { createGithubApi } from '../src/github-api.mjs';
import { main, reportRoutingResult } from '../src/entrypoint.mjs';
import { fixture } from './fixture.mjs';
import { spawn } from 'node:child_process';
import { createLocalWriterAdapter } from '../src/local-writer.mjs';
import { captureCausalDiagnostic } from '../src/diagnostics.mjs';
import { recordEntrypointFailure } from '../src/repository-entrypoint.mjs';

const fail = (code, message = code) => Object.assign(new Error(message), { code });
async function stores(t) {
  const root = await mkdtemp(join(tmpdir(), 'relay-host-cause-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const primary = join(root, 'primary'); const fallback = join(root, 'fallback');
  return { primary, fallback,
    diagnosticStore: value => writeDiagnosticBundle(value, { root: primary }),
    fallbackStore: options => reserveRuntimeDiagnostic({ ...options, root: fallback }),
    readConfig: async () => ({ mode: 'normal' }) };
}

test('rejected native run has original expected/observed evidence without native effects', async t => {
  const f = await fixture(t, { labelLaunch: true, deferAdmission: true });
  const s = await stores(t); const refs = [];
  for (const [field, value] of [['status', 'queued'], ['actor', { login: 'foreign-owner' }], ['path', 'foreign-workflow']]) {
    const api = { ...f.api, getRun: async () => ({ ...f.run, [field]: value }) };
    for (const name of ['post', 'patch', 'delete', 'ensureStepLabel']) api[name] = () => assert.fail('untrusted event mutated native state');
    const broker = createPublicationBroker({ api, store: f.store,
      recordFailure: async options => { const ref = await recordHostFailure({ ...options, ...s }); refs.push(ref); return ref; } });
    await assert.rejects(broker.dispatch(f.admissionRequest), error => {
      assert.equal(error.code, 'OWNER_RUN_NOT_ADMITTED');
      assert.equal(error.details.diagnosticStore.status, 'stored');
      return true;
    });
    const saved = JSON.parse(await readFile(join(s.primary, `${refs.at(-1).executionId}.json`), 'utf8'));
    const evidence = JSON.stringify(saved.causalEvidence);
    assert.match(evidence, /observation/);
    assert.ok(evidence.includes(typeof value === 'object' ? value.login : value));
    assert.equal(saved.lifecycle.workerStarted, false);
  }
  assert.deepEqual(await f.store.all(), []);
  assert.deepEqual(f.comments, []);
  assert.equal(f.pushes(), 0);
});

test('primary diagnostic failure leaves original cause and recorder failure in independent capsule', async t => {
  const s = await stores(t); const executionId = 'host-fallback-test';
  const original = fail('NATIVE_API_FAILED', 'Original HTTP conflict for operation');
  original.native = { status: 409, response: 'native first actionable cause; token=private-value' };
  const ref = await recordHostFailure({ ...s, executionId, error: original, workerStarted: false, operation: 'admit',
    diagnosticStore: async () => { throw fail('ENOSPC', 'primary disk full'); } });
  assert.equal(ref.status, 'unavailable'); assert.equal(ref.storeCode, 'ENOSPC');
  const handle = await openRuntimeDiagnostic({ root: s.fallback, executionId });
  const capsule = await handle.read();
  assert.match(JSON.stringify(capsule.causalEvidence), /Original HTTP conflict/);
  assert.match(JSON.stringify(capsule.recorderFailure), /primary disk full/);
  assert.doesNotMatch(JSON.stringify(capsule), /private-value/);
  assert.doesNotMatch(JSON.stringify(ref), /Original HTTP|private-value|disk full/);
});

test('invalid primary receipt and unavailable fallback report both failures independently', async () => {
  const output = [];
  const result = await recordHostFailure({ error: fail('ORIGINAL_REJECTION'), executionId: 'host-both-failed',
    readConfig: async () => ({ mode: 'normal' }), diagnosticStore: async () => ({ status: 'stored' }),
    fallbackStore: async () => { throw fail('EROFS'); }, writeFallback: line => output.push(line) });
  assert.equal(result.storeCode, 'DIAGNOSTICS_STORE_RECEIPT_INVALID');
  assert.equal(result.fallbackCode, 'EROFS');
  assert.equal(result.originalEvidence, 'observed_not_retained');
  assert.match(output.join(''), /RELAY_DIAGNOSTIC_UNAVAILABLE/);
});

test('native API rejection retains bounded original body/status and network cause', async () => {
  const api = createGithubApi({ token: 'synthetic-token', fetchImpl: async () => new Response('repository access denied', { status: 403 }) });
  await assert.rejects(api.get('/issues/42'), error => {
    assert.equal(error.code, 'GITHUB_REQUEST_FAILED'); assert.equal(error.status, 403);
    assert.equal(error.native.response.text, 'repository access denied');
    assert.equal(error.native.response.truncated, false); return true;
  });
  const large = createGithubApi({ fetchImpl: async () => new Response('x'.repeat(20000), { status: 500 }) });
  await assert.rejects(large.get('/issues/42'), error => { assert.equal(error.native.response.truncated, true);
    assert.ok(Buffer.byteLength(error.native.response.text) <= 8192); return true; });
  const unavailable = createGithubApi({ fetchImpl: async () => { throw fail('ECONNRESET', 'socket reset at provider'); } });
  await assert.rejects(unavailable.get('/issues/42'), error => { assert.equal(error.code, 'GITHUB_REQUEST_FAILED');
    assert.equal(error.cause.code, 'ECONNRESET'); return true; });
});

test('malformed or foreign event is diagnosed before any adapter or journal is constructed', async () => {
  for (const event of ['{', JSON.stringify({ repository: { full_name: 'foreign/repository' } })]) {
    const recorded = [];
    const run = () => main({ env: { GITHUB_EVENT_PATH: 'fixture', GITHUB_RUN_ID: '123', GITHUB_EVENT_NAME: 'issues' },
      readEvent: async () => event, createWriter: () => assert.fail('Writer constructed'),
      createJournal: () => assert.fail('journal constructed'),
      persistRoutingFailure: async value => { recorded.push(value); return { diagnosticStore: { status: 'stored', executionId: 'fixture', mode: 'normal' } }; } });
    const output = []; const code = await reportRoutingResult(run, { write: x => output.push(x), writeError: x => output.push(x) });
    assert.equal(code, 1); assert.equal(recorded.length, 1);
    assert.equal(recorded[0].error.details.childState, 'not_started');
    assert.doesNotMatch(output.join(''), /foreign\/repository|SyntaxError/);
  }
});

test('real helper stderr, invalid receipt and exit/signal survive behind the safe public classification', async t => {
  for (const [name, script, code, signal] of [
    ['stderr', "process.stderr.write('native socket refused'); process.exitCode=7", 7, null],
    ['receipt', "process.stdout.write('invalid native receipt')", 0, null],
    ['signal', "process.stderr.write('native stop observed'); process.kill(process.pid,'SIGTERM')", null, 'SIGTERM']
  ]) await t.test(name, async () => {
    const adapter = createLocalWriterAdapter({ spawnImpl: (_cmd, _args, options) =>
      spawn(process.execPath, ['-e', `process.stdin.resume();process.stdin.on('end',()=>{${script}})`], options) });
    await assert.rejects(adapter.invoke({ operation: 'admit' }), error => {
      const evidence = captureCausalDiagnostic({ error, operation: 'admit' });
      assert.match(JSON.stringify(evidence), /native/);
      assert.equal(error.native.exitCode ?? error.cause.exitCode ?? null, code === 0 ? null : code);
      if (signal) assert.equal(error.native.signal, signal);
      assert.doesNotMatch(JSON.stringify(error), /socket refused|invalid native receipt|native stop observed/);
      return true;
    });
  });
});

test('bootstrap recorder failure reports its independent reason without replacing or disclosing the original', async () => {
  const output = [];
  const result = await recordEntrypointFailure(fail('CONSUMER_CONFIG_INVALID', 'private config text'), 'writer-bootstrap', {
    uid: 0, record: async () => { throw fail('DIAGNOSTIC_MODULE_UNAVAILABLE', 'private recorder text'); }, write: text => output.push(text) });
  assert.equal(result.status, 'unavailable'); assert.equal(result.storeCode, 'DIAGNOSTIC_MODULE_UNAVAILABLE');
  assert.match(output.join(''), /CONSUMER_CONFIG_INVALID/);
  assert.match(output.join(''), /observed_not_retained/);
  assert.doesNotMatch(output.join(''), /private/);
});
