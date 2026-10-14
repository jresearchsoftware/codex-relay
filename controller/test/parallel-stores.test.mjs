import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readdir, readFile, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { createAttemptStore } from '../src/attempt-store.mjs';
import { withStoreLock } from '../src/store-lock.mjs';
import { writeDiagnosticBundle } from '../src/diagnostic-store.mjs';
import { runAttempt } from '../src/attempt.mjs';
import { fixture } from './fixture.mjs';
import { REPOSITORY } from '../src/execution-contract.mjs';

async function rootFixture(t) {
  const root = await mkdtemp(join(tmpdir(), 'relay-parallel-stores-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  return root;
}

test('concurrent same-run reservation writes exactly one immutable initial journal', async t => {
  const store = createAttemptStore(await rootFixture(t));
  const results = await Promise.all(Array.from({ length: 16 }, (_, index) =>
    store.reserve(99, { envelope: { repository: REPOSITORY }, index })));
  assert.equal(results.filter(Boolean).length, 1);
  const record = await store.get(99);
  assert.equal(results[record.index], true);
});

test('same-run controller contention cannot prepare or infer twice and replay retains returned result', async t => {
  const f = await fixture(t, { createJournal: root => createAttemptStore(join(root, 'journals')) });
  let calls = 0; let entered; let finish;
  const started = new Promise(resolve => { entered = resolve; });
  const pending = new Promise(resolve => { finish = resolve; });
  const options = { ...f, execute: async e => {
    calls++; entered(); await pending; await f.commit();
    return { version: 2, attemptId: e.attemptId, child: 'started', containment: 'reaped', result: { status: 'success', summary: 'Stored once.', validation: [] } };
  } };
  const first = runAttempt(options);
  await started;
  await assert.rejects(runAttempt({ ...options, admissionResumed: true, prepare: () => assert.fail('duplicate prepared'),
    execute: () => assert.fail('duplicate inferred') }), { code: 'ATTEMPT_CONTROLLER_BUSY' });
  finish();
  const result = await first;
  assert.equal(result.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
  assert.deepEqual(await runAttempt({ ...options, admissionResumed: true }), result);
  assert.equal(calls, 1); assert.equal(f.pushes(), 1);
});

test('independent runs and separately configured repositories may hold journal locks concurrently', async t => {
  const root = await rootFixture(t);
  const left = createAttemptStore(join(root, 'left'), { repository: 'owner/left' });
  const right = createAttemptStore(join(root, 'right'), { repository: 'owner/right' });
  const entered = [];
  await left.withLock(99, () => Promise.all([
    left.withLock(100, () => { entered.push('same-repository'); }),
    right.withLock(99, async () => {
      entered.push('other-repository');
      await right.reserve(99, { envelope: { repository: 'owner/right' } });
    })
  ]));
  assert.deepEqual(entered.sort(), ['other-repository', 'same-repository']);
  await assert.rejects(left.put(99, { envelope: { repository: 'owner/right' } }), { code: 'ATTEMPT_REPOSITORY_MISMATCH' });
});

test('controller death releases its kernel lock but unknown reserved execution never infers again', { skip: process.platform !== 'linux' }, async t => {
  const f = await fixture(t, { createJournal: root => createAttemptStore(join(root, 'journals')) });
  const root = join(f.root, 'journals');
  const program = `import { createAttemptStore } from ${JSON.stringify(new URL('../src/attempt-store.mjs', import.meta.url).href)};
const store = createAttemptStore(${JSON.stringify(root)});
await store.withLock(99, async () => {
  await store.reserve(99, ${JSON.stringify({ version: 2, envelope: f.envelope, execution: { reserved: true, returned: false, child: 'unknown', containment: 'unknown' }, progress: null, outcome: null, diagnostic: null })});
  process.stdout.write('reserved\\n');
  await new Promise(() => {});
});`;
  const child = spawn(process.execPath, ['--input-type=module', '-e', program], { env: process.env, stdio: ['ignore', 'pipe', 'pipe'] });
  t.after(() => { if (child.exitCode === null) child.kill('SIGKILL'); });
  const [marker] = await Promise.race([once(child.stdout, 'data'), once(child, 'close').then(() => { throw new Error('Synthetic controller failed before reservation'); })]);
  assert.equal(marker.toString(), 'reserved\n');
  const closed = once(child, 'close'); child.kill('SIGKILL'); await closed;
  await withStoreLock(join(root, '99.json.controller-lock'), () => f.journal.get(99), { waitSeconds: 5 });
  await assert.rejects(runAttempt({ ...f, admissionResumed: true,
    prepare: () => assert.fail('unknown execution prepared'), execute: () => assert.fail('unknown execution inferred') }), { code: 'EXECUTION_UNKNOWN_NO_RETRY' });
  assert.equal(f.pushes(), 0);
});

test('concurrent diagnostic persistence and retention stay bounded without deleting partial writes', async t => {
  const root = await rootFixture(t);
  const values = Array.from({ length: 32 }, (_, index) => ({ schemaVersion: '1.0', mode: 'normal', executionId: `run-${index + 1}`, index }));
  const results = await Promise.all(values.map(value => writeDiagnosticBundle(value, { root, retentionCount: 8 })));
  assert.ok(results.every(result => result.status === 'stored'));
  const names = (await readdir(root)).filter(name => name.endsWith('.json'));
  assert.equal(names.length, 8);
  for (const name of names) {
    const record = JSON.parse(await readFile(join(root, name), 'utf8'));
    assert.equal(name, `${record.executionId}.json`);
  }
  assert.equal((await readdir(root)).filter(name => name.includes('.tmp-')).length, 0);
});
