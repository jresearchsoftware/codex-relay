import test from 'node:test';
import assert from 'node:assert/strict';
import { main } from '../src/predispatch-recovery-entrypoint.mjs';

test('deployment-operator entrypoint refuses unprivileged callers and arguments before reading configuration', async () => {
  await assert.rejects(main({ uid: 1000, argv: ['node', 'entrypoint'] }), { code: 'ROOT_OPERATOR_REQUIRED' });
  await assert.rejects(main({ uid: 0, argv: ['node', 'entrypoint', 'foreign-path'] }), { code: 'ROOT_OPERATOR_REQUIRED' });
});

import { EventEmitter } from 'node:events';
import { CONSUMER } from '../../consumer/consumer.mjs';

test('operator transport holds the existing Writer flock and passes only a bounded selected request', async () => {
  const request = { repository: CONSUMER.repository, operation: 'predispatch-state', runId: 99, attemptId: 'run-99' };
  let called = false;
  const code = await main({ uid: 0, argv: ['node', 'entrypoint'],
    readRequest: async options => {
      assert.equal(options.limit, 4096); assert.equal(options.protectedConfig, true); return request;
    },
    execute(command, args, options) {
      called = true;
      assert.equal(command, '/usr/bin/flock');
      assert.deepEqual(args.slice(0, 3), ['-w', '60', `${CONSUMER.paths.claimRoot}/publication-v2.lock`]);
      assert.equal(args[4], '--input-type=module');
      assert.equal(options.env.RELAY_REPOSITORY, CONSUMER.repository);
      assert.equal(options.env.RELAY_CALLER_UID, undefined);
      assert.equal(options.env.GITHUB_TOKEN, undefined);
      const child = new EventEmitter(); child.stdin = new EventEmitter();
      child.stdin.end = value => { assert.deepEqual(JSON.parse(value), request); queueMicrotask(() => child.emit('exit', 0)); };
      return child;
    } });
  assert.equal(code, 0); assert.ok(called);
  await assert.rejects(main({ uid: 0, argv: ['node', 'entrypoint'], readRequest: async () => ({ ...request, path: '/foreign' }) }),
    { code: 'RECOVERY_REQUEST_INVALID' });
});

import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createSlotJournal } from '../src/slot-journal.mjs';
import { createAttemptStore } from '../src/attempt-store.mjs';
import { memoryStore, currentEnvelope } from './fixture.mjs';

test('original slot journal lock uses protected envelope paths and real kernel exclusion without creating a journal', async t => {
  const root = await mkdtemp(join(tmpdir(), 'predispatch-lock-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const store = memoryStore(); await store.put(9, { envelope: currentEnvelope() });
  const journal = createSlotJournal(store, { createStore(path, options) {
    assert.equal(path, CONSUMER.paths.attemptRoot);
    return createAttemptStore(root, options);
  } });
  let started; const ready = new Promise(resolve => { started = resolve; });
  let release; const held = new Promise(resolve => { release = resolve; });
  const first = journal.withLock(9, async () => { started(); await held; });
  await ready;
  try {
    await assert.rejects(journal.withLock(9, async () => assert.fail('contending controller')), { code: 'ATTEMPT_CONTROLLER_BUSY' });
    assert.equal(await journal.get(9), null);
  } finally { release(); await first; }
  assert.equal(await journal.get(9), null);
});
