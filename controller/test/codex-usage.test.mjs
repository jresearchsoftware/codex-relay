import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { fixture, memoryStore } from './fixture.mjs';
import { runAttempt } from '../src/attempt.mjs';
import { recoverAttemptPublication } from '../src/recover-attempt-publication.mjs';
import { normalizeCodexUsage } from '../src/codex-usage.mjs';
import { usageOutcomeSummary } from '../src/outcome.mjs';
import { createOnDemandDispatchAdapter } from '../src/github.mjs';

const usage = normalizeCodexUsage({ source: 'codex-exec-turn-completed', scope: 'native-session-total',
  input_tokens: 100, cached_input_tokens: 25, cache_write_input_tokens: 10, output_tokens: 30, reasoning_output_tokens: 20 });

for (const status of ['success', 'blocked', 'failed']) {
  test(`native usage survives ${status} execution, journal, Outcome and same-attempt replay`, async t => {
    const f = await fixture(t); const journal = f.journal; let executions = 0;
    const execute = async () => {
      executions++;
      await f.commit();
      if (status === 'failed') throw Object.assign(new Error('result missing'), { code: 'CODEX_RESULT_MISSING', details: {
        childState: 'started', containment: 'reaped', codexUsage: usage
      } });
      return { version: f.envelope.version, attemptId: f.envelope.attemptId, child: 'started', containment: 'reaped', codexUsage: usage,
        result: { status, summary: 'A bounded change', validation: [], blockedReason: status === 'blocked' ? 'needs decision' : '' } };
    };
    const result = await runAttempt({ ...f, journal, execute });
    const record = await journal.get(f.envelope.runId);
    assert.deepEqual(record.execution.codexUsage, usage);
    const outcomes = f.comments.filter(value => value.body.includes('## Codex Outcome'));
    assert.equal(outcomes.length, 1);
    assert.ok(outcomes[0].body.includes(usageOutcomeSummary(usage)));
    assert.match(outcomes[0].body, /Actual model\/effort: UNAVAILABLE/);
    assert.deepEqual(await runAttempt({ ...f, journal, execute }), result);
    assert.equal(executions, 1);
    assert.equal(f.comments.filter(value => value.body.includes('## Codex Outcome')).length, 1);
  });
}

test('worker result usage claims do not become runtime evidence in an Outcome', async t => {
  const f = await fixture(t); const journal = f.journal;
  await runAttempt({ ...f, journal, execute: async () => {
    await f.commit();
    return { version: f.envelope.version, attemptId: f.envelope.attemptId, child: 'started', containment: 'reaped',
      result: { status: 'success', summary: 'done', validation: [], codexUsage: usage } };
  } });
  assert.deepEqual((await journal.get(f.envelope.runId)).execution.codexUsage, normalizeCodexUsage());
  const body = f.comments.find(value => value.body.includes('## Codex Outcome')).body;
  assert.ok(body.includes(usageOutcomeSummary()));
  assert.ok(!body.includes('input=100'));
});

test('publication recovery reuses the original runtime usage without executing a worker', async t => {
  const f = await fixture(t); const journal = f.journal; const head = 'c'.repeat(40);
  await journal.put(f.envelope.runId, { version: f.envelope.version, envelope: f.envelope,
    execution: { reserved: true, returned: true, child: 'started', containment: 'reaped', codexUsage: usage,
      result: { status: 'success', summary: 'done', validation: [] } },
    collection: { head, clean: true } });
  let finish;
  const broker = { invoke: async request => {
    if (request.operation === 'publication-state') return { envelope: f.envelope, recovery: { result: { status: 'PUBLISHED' } } };
    if (request.operation === 'recover-publication') return { publishedHead: head };
    if (request.operation !== 'complete-handoff') { assert.equal(request.operation, 'finish'); finish = request; }
    return { status: 'IMPLEMENTED_PENDING_FRESH_REVIEW', head, prNumber: 43 };
  } };
  await recoverAttemptPublication({ runId: f.envelope.runId, attemptId: f.envelope.attemptId, authorizationId: 123,
    broker, journal, collect: async () => ({ head, clean: true }) });
  assert.deepEqual(finish.codexUsage, usage);
  assert.equal(finish.recoveryAuthorizationId, 123);
});

test('usage crosses the bounded dispatcher wire and survives a later cleanup failure', async t => {
  const f = await fixture(t);
  for (const status of ['success', 'failed', 'cleanup-failed']) {
    const payload = status === 'failed'
      ? { version: 2, status: 'blocked', code: 'CODEX_RESULT_MISSING', diagnostic: { codexUsage: usage, observed: { child: 'started' } } }
      : { version: 2, attemptId: f.envelope.attemptId, child: 'started', result: { status: 'success' }, codexUsage: usage };
    const adapter = createOnDemandDispatchAdapter({
      reserveDiagnostic: async () => ({ async write() {} }),
      finalizeArtifacts: async () => {
        if (status === 'cleanup-failed') throw Object.assign(new Error('cleanup failed'), { code: 'SANDBOX_CLEANUP_FAILED' });
        return { cleanup: 'complete' };
      },
      spawnImpl: (_command, _args, options) => spawn(process.execPath, ['-e',
        `require('node:fs').readFileSync(0); require('node:fs').writeSync(${status === 'failed' ? 2 : 1}, ${JSON.stringify(JSON.stringify(payload))}); process.exitCode=${status === 'failed' ? 1 : 0};`
      ], options)
    });
    if (status === 'success') assert.deepEqual((await adapter.dispatch(f.envelope)).codexUsage, usage);
    else await assert.rejects(adapter.dispatch(f.envelope), error => {
      assert.deepEqual(error.details.codexUsage, usage); return true;
    });
  }
});
