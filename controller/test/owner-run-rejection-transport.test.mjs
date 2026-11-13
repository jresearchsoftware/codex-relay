import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { main, reportRoutingResult } from '../src/entrypoint.mjs';
import { serializeWriterFailure } from '../src/privileged-writer-helper.mjs';
import { createLocalWriterAdapter } from '../src/local-writer.mjs';
import { CONSUMER, EXECUTION_SLOT } from '../../consumer/consumer.mjs';

function helper(payload) {
  return createLocalWriterAdapter({ spawnImpl: (_command, _args, options) => spawn(process.execPath,
    ['-e', `process.stdin.resume(); process.stdin.on('end', () => { process.stderr.write(${JSON.stringify(JSON.stringify(payload))}); process.exitCode = 1; });`], options) });
}

test('categorical rejection survives the real helper serialization and routing boundary without worker or Outcome', async () => {
  const wire = serializeWriterFailure({ code: 'OWNER_RUN_NOT_ADMITTED', message: 'private text',
    details: { reason: 'status', observed: 'private native value', expected: 'private config' } });
  assert.deepEqual(wire, { code: 'OWNER_RUN_NOT_ADMITTED', reason: 'status' });
  let operations = [], output = '', annotation = '';
  const writer = helper(wire);
  const run = () => main({
    env: { GITHUB_EVENT_PATH: 'synthetic', GITHUB_EVENT_NAME: 'issues',
      GITHUB_REF: `refs/heads/${CONSUMER.baseBranch}`, GITHUB_RUN_ID: '99' },
    readEvent: async () => JSON.stringify({ repository: { full_name: CONSUMER.repository },
      sender: { login: CONSUMER.owner }, action: 'labeled', label: { name: 'codex-ready-auto' }, issue: { number: 96 } }),
    resolveSlot: () => CONSUMER.executionSlots ? EXECUTION_SLOT : undefined,
    createWriter: () => ({ invoke: request => { operations.push(request.operation); return writer.invoke(request); } }),
    createDispatcher: () => ({ dispatch: () => assert.fail('worker must not start') }),
    createJournal: () => ({ put: () => assert.fail('journal must not be written') }),
    prepare: () => assert.fail('checkout must not be prepared'),
    persistFailure: () => assert.fail('unbound rejection must not publish a diagnostic capsule')
  });
  assert.equal(await reportRoutingResult(run, { write: v => { output += v; }, writeError: v => { annotation += v; } }), 0);
  assert.deepEqual(operations, ['admit']);
  assert.deepEqual(JSON.parse(output), { status: 'BLOCKED', code: 'OWNER_RUN_NOT_ADMITTED', reason: 'status' });
  assert.match(annotation, /OWNER_RUN_NOT_ADMITTED \(status\)/);
  assert.match(annotation, /no worker started and no target-bound Outcome was authorized/);
  assert.doesNotMatch(output + annotation, /private|Reconcile the terminal Outcome/);
});

test('old helper rejection without a reason remains supported; unknown or unrelated reasons never cross the boundary', async () => {
  for (const [code, reason] of [['OWNER_RUN_NOT_ADMITTED', undefined], ['OWNER_RUN_NOT_ADMITTED', 'private\n::error::injected'],
    ['OWNER_RUN_NOT_ADMITTED', { status: 'private' }], ['ADMISSION_QUIESCED', 'status']]) {
    const wire = serializeWriterFailure({ code, details: { reason } });
    assert.deepEqual(wire, { code });
    await assert.rejects(helper({ code, reason }).invoke({ operation: 'admit' }), error => {
      assert.equal(error.code, code);
      assert.equal(error.details.reason, undefined);
      assert.doesNotMatch(JSON.stringify(error.details), /private|injected/);
      return true;
    });
  }
});
