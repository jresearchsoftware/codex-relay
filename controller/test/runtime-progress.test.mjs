import test from 'node:test';
import assert from 'node:assert/strict';
import { traceRuntimeOperation } from '../src/transition-timing.mjs';

test('quiet orchestration reports its real operation, periodic wait and terminal transition without payloads', async () => {
  const lines = [];
  const result = await traceRuntimeOperation('collect-progress', async () => {
    await new Promise(resolve => setTimeout(resolve, 25)); return { private: 'worker payload' };
  }, { intervalMs: 5, write: text => lines.push(text) });
  assert.equal(result.private, 'worker payload');
  const events = lines.map(line => JSON.parse(line.slice('RELAY_RUNTIME_PROGRESS '.length)));
  assert.equal(events[0].state, 'started'); assert.equal(events.at(-1).state, 'completed');
  assert.ok(events.some(event => event.state === 'waiting'));
  assert.ok(events.every(event => event.operation === 'collect-progress' && Number.isInteger(event.elapsedMs)));
  assert.doesNotMatch(lines.join(''), /worker payload|private/);
  const count = lines.length;
  await new Promise(resolve => setTimeout(resolve, 10)); assert.equal(lines.length, count);
});

test('failed orchestration reports failure, preserves original rejection and never serializes it', async () => {
  const lines = []; const original = new Error('native private cause');
  await assert.rejects(traceRuntimeOperation('publish-progress', async () => { throw original; }, {
    write: text => lines.push(text)
  }), error => error === original);
  assert.equal(JSON.parse(lines.at(-1).slice('RELAY_RUNTIME_PROGRESS '.length)).state, 'failed');
  assert.doesNotMatch(lines.join(''), /native private cause/);
  let calls = 0;
  assert.equal(await traceRuntimeOperation('untrusted secret operation', () => { calls++; return 42; }, {
    write: () => assert.fail('untrusted operation must not be emitted')
  }), 42);
  assert.equal(calls, 1);
});

test('an unavailable progress output surface cannot duplicate or replace an operation', async () => {
  let calls = 0;
  assert.equal(await traceRuntimeOperation('admit', () => { calls++; return 42; }, {
    write: () => { throw new Error('output unavailable'); }
  }), 42);
  assert.equal(calls, 1);
});
