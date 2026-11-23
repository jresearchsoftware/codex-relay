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
    observation: { check: 'status', expected: 'in_progress', observed: 'queued' },
    details: { reason: 'status', observed: 'private native value', expected: 'private config' } });
  assert.deepEqual(wire, { code: 'OWNER_RUN_NOT_ADMITTED', reason: 'status',
    predicate: { check: 'status', expected: 'in_progress', observed: 'queued' } });
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
    persistFailure: async value => { assert.match(value.executionId, /^routing-/); assert.equal(value.error.details.childState, 'not_started'); return {}; }
  });
  assert.equal(await reportRoutingResult(run, { write: v => { output += v; }, writeError: v => { annotation += v; } }), 1);
  assert.deepEqual(operations, ['admit']);
  assert.deepEqual(JSON.parse(output), { status: 'BLOCKED', code: 'OWNER_RUN_NOT_ADMITTED', reason: 'status', phase: 'pre-worker-admission', worker: 'not_started', runId: 99,
    predicate: wire.predicate, writerFailure: { exit: 1, operation: 'admit' } });
  assert.match(annotation, /OWNER_RUN_NOT_ADMITTED \(status\)/);
  assert.match(annotation, /Expected GitHub run.status in_progress, observed queued/);
  assert.match(annotation, /Codex child did not start/);
  assert.match(annotation, /No target-bound Outcome was authorized/);
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

for (const [name, proven, writerStored] of [
  ['fresh reservation', true, true], ['replay without proof', false, true], ['controller fallback', true, false]
]) test(`Step authority failure preserves evidence and attempt identity for ${name}`, async () => {
  const diagnosticStore = { status: 'stored', mode: 'normal', executionId: writerStored ? 'host-99-fixture' : 'routing-99-fixture' };
  const wire = serializeWriterFailure({ code: 'AUTHORITY_SOURCE_MISMATCH', details: {
    ...(writerStored ? { diagnosticStore } : {}), admissionEffect: { step: 2, projection: 'unknown', ready: 'not-attempted' },
    failureDiagnostic: { stage: 'authority', boundary: 'writer-publication', operation: 'step-authority',
      executionId: 'run-99', ...(proven ? { workerStarted: false, childState: 'not_started', containment: 'not_required' } : {}) }
  } });
  const operations = [];
  let fallbackWrites = 0;
  let stderr = '', annotation = '';
  const writer = helper(wire);
  const run = () => main({
    env: { GITHUB_EVENT_PATH: 'synthetic', GITHUB_EVENT_NAME: 'issues',
      GITHUB_REF: `refs/heads/${CONSUMER.baseBranch}`, GITHUB_RUN_ID: '99' },
    readEvent: async () => JSON.stringify({ repository: { full_name: CONSUMER.repository },
      sender: { login: CONSUMER.owner }, action: 'labeled', label: { name: 'codex-ready-auto' }, issue: { number: 42 } }),
    resolveSlot: () => CONSUMER.executionSlots ? EXECUTION_SLOT : undefined,
    createWriter: () => ({ invoke: request => { operations.push(request.operation); return writer.invoke(request); } }),
    createDispatcher: () => ({ dispatch: () => assert.fail('worker must not start') }),
    createJournal: () => ({ put: () => assert.fail('journal must not be written') }),
    persistRoutingFailure: ({ error }) => {
      fallbackWrites++;
      return { failureDiagnostic: { ...error.details.failureDiagnostic, executionId: diagnosticStore.executionId },
        executionId: diagnosticStore.executionId, diagnosticStore };
    }
  });
  assert.equal(await reportRoutingResult(run, {
    write: () => assert.fail('unexpected success receipt'), writeError: value => { stderr += value; },
    writeAnnotation: value => { annotation += value; }
  }), 1);
  assert.deepEqual(operations, ['admit']);
  assert.equal(fallbackWrites, writerStored ? 0 : 1);
  const { code, diagnostic } = JSON.parse(stderr);
  assert.equal(code, 'AUTHORITY_SOURCE_MISMATCH');
  assert.equal(diagnostic.failureBoundary, 'writer-publication');
  assert.equal(diagnostic.publication.operation, 'step-authority');
  assert.equal(diagnostic.observed.child, proven ? 'not_started' : 'unknown');
  assert.equal(diagnostic.executionState, proven ? 'known-not-executed' : 'uncertain');
  assert.equal(diagnostic.containment, proven ? 'not_required' : 'unknown');
  assert.equal(diagnostic.executionId, 'run-99');
  assert.deepEqual(diagnostic.durable.diagnosticStore, diagnosticStore);
  assert.equal(diagnostic.durable.publishedHead, null);
  assert.match(annotation, /required native authority source could not be matched/);
  assert.match(annotation, /protected.*(?:Writer|publication)/i);
  assert.doesNotMatch(annotation, /Outcome was published|Writer confirmed a target-bound Outcome/);
});
