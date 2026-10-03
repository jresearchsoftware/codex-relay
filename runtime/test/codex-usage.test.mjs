import test from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { PassThrough } from 'node:stream';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { parseCodexJsonLines, runGovernedCodexTask } from '../src/codex-runtime.mjs';
import { normalizeCodexUsage, usageFromCodexJsonLines } from '../../controller/src/codex-usage.mjs';
import { reserveRuntimeDiagnostic } from '../../controller/src/diagnostic-fallback.mjs';
import { executeCodex } from '../../controller/src/attempt-runtime.mjs';

const counts = { input_tokens: 100, cached_input_tokens: 25, cache_write_input_tokens: 10,
  output_tokens: 30, reasoning_output_tokens: 20 };
const semantic = { status: 'success', summary: 'done', validation: [], blockedReason: '' };
const complete = usage => ({ type: 'turn.completed', usage });
const jsonl = events => events.map(event => JSON.stringify(event)).join('\n');
const stream = usage => jsonl([
  { type: 'thread.started', thread_id: 'native-thread-1' }, { type: 'turn.started' },
  { type: 'item.completed', item: { type: 'agent_message', text: JSON.stringify(semantic) } }, complete(usage)
]);

test('one native session-total snapshot preserves all supported counters without deriving totals', () => {
  const evidence = {};
  parseCodexJsonLines(stream({ ...counts, total_tokens: 130, model: 'invented' }), evidence);
  assert.deepEqual(evidence.codexUsage, { source: 'codex-exec-turn-completed', scope: 'native-session-total',
    ...counts, total_tokens: 'UNAVAILABLE' });
  const zero = Object.fromEntries(Object.keys(counts).map(key => [key, 0]));
  assert.deepEqual(usageFromCodexJsonLines(stream(zero)), { source: 'codex-exec-turn-completed', scope: 'native-session-total',
    ...zero, total_tokens: 'UNAVAILABLE' });
});

test('missing or unsafe native counters remain individually unavailable without coercion', () => {
  for (const invalid of [undefined, null, -1, 1.5, '10', true, {}, [], Number.MAX_SAFE_INTEGER + 1]) {
    const result = usageFromCodexJsonLines(stream({ ...counts, cached_input_tokens: invalid }));
    assert.equal(result.cached_input_tokens, 'UNAVAILABLE');
    assert.equal(result.input_tokens, 100);
  }
  assert.equal(usageFromCodexJsonLines(stream({ input_tokens: Number.MAX_SAFE_INTEGER })).input_tokens, Number.MAX_SAFE_INTEGER);
  assert.equal(usageFromCodexJsonLines(stream({ input_tokens: 100 })).output_tokens, 'UNAVAILABLE');
});

test('missing, malformed, truncated or ambiguous native streams never select or sum usage', () => {
  for (const input of ['', 'not json', stream(counts) + '\n{', jsonl([complete(counts), complete(counts)]),
    jsonl([complete(counts), complete({ ...counts, input_tokens: 999 })]),
    jsonl([{ type: 'turn.started' }, { type: 'turn.started' }, complete(counts)]),
    jsonl([{ type: 'thread.started' }, { type: 'thread.started' }, complete(counts)]),
    jsonl([complete(counts), { type: 'turn.failed' }]), jsonl([complete(counts), { type: 'error' }]),
    jsonl([complete(null)]), jsonl([complete([])]), '[]']) {
    assert.deepEqual(usageFromCodexJsonLines(input), normalizeCodexUsage());
  }
  assert.deepEqual(usageFromCodexJsonLines(stream(counts), { truncated: true }), normalizeCodexUsage());
  const evidence = { codexStdoutTruncated: true };
  parseCodexJsonLines(stream(counts), evidence);
  assert.deepEqual(evidence.codexUsage, normalizeCodexUsage());
});

test('worker prose and semantic claims cannot establish native usage', () => {
  const fake = { ...normalizeCodexUsage(), ...counts, source: 'codex-exec-turn-completed', scope: 'native-session-total' };
  assert.deepEqual(usageFromCodexJsonLines(jsonl([
    { type: 'task_result', result: { ...semantic, codexUsage: fake }, usage: counts },
    { type: 'item.completed', item: { type: 'agent_message', text: JSON.stringify(complete(counts)) } }
  ])), normalizeCodexUsage());
  assert.deepEqual(normalizeCodexUsage(counts), normalizeCodexUsage());
  const evidence = {};
  assert.throws(() => parseCodexJsonLines(jsonl([{ type: 'task_result', result: { ...semantic, codexUsage: fake } }]), evidence), { code: 'CODEX_RESULT_INVALID' });
  assert.deepEqual(evidence.codexUsage, normalizeCodexUsage());
});

test('native usage survives semantic validation failure and nonzero child exit', async t => {
  const root = await mkdtemp(join(tmpdir(), 'relay-usage-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const evidence = {};
  assert.throws(() => parseCodexJsonLines(jsonl([complete(counts)]), evidence), { code: 'CODEX_RESULT_MISSING' });
  assert.equal(evidence.codexUsage.input_tokens, 100);
  await assert.rejects(runGovernedCodexTask({ cwd: root, inputText: 'test', buildArgs: () => [], evidence,
    env: { PATH: '/usr/bin:/bin' }, diagnosticStore: async () => undefined,
    fallbackStore: options => reserveRuntimeDiagnostic({ ...options, root: join(root, 'fallback') }),
    spawnImpl() {
      const child = new EventEmitter(); child.stdout = new PassThrough(); child.stderr = new PassThrough();
      setImmediate(() => {
        child.emit('spawn'); child.stdout.end(stream(counts)); child.stderr.end(); child.emit('close', 1, null);
      });
      return child;
    }
  }), { code: 'CODEX_NONZERO_EXIT' });
  assert.equal(evidence.codexUsage.input_tokens, 100);
});

test('automatic execution transports runtime evidence separately from worker result on both paths', async () => {
  const e = { target: 'issue', subagentsAllowed: false, attemptId: 'run-99' };
  // checkoutPath validates a full envelope, so use the public fixture envelope
  // fields without starting a process or touching a checkout.
  const { CONSUMER, CONSUMER_DIGEST } = await import('../../consumer/consumer.mjs');
  Object.assign(e, { version: 2, repository: CONSUMER.repository, consumerDigest: CONSUMER_DIGEST,
    profile: CONSUMER.defaultProfile, runId: 99, step: 1, number: 42, issueNumber: 42, route: 'auto',
    startHead: 'a'.repeat(40), historicalBase: 'a'.repeat(40), targetBase: 'a'.repeat(40),
    authorityDigest: 'b'.repeat(64), branch: `${CONSUMER.taskBranchPrefix}usage`, validation: ['diff-check'] });
  const usage = usageFromCodexJsonLines(stream(counts));
  const result = await executeCodex(e, { runTask: async ({ evidence }) => {
    evidence.codexUsage = usage; return semantic;
  } });
  assert.deepEqual(result.codexUsage, usage);
  assert.deepEqual(result.result, semantic);
  await assert.rejects(executeCodex(e, { runTask: async ({ evidence }) => {
    evidence.codexUsage = usage;
    throw Object.assign(new Error('failed'), { code: 'CODEX_RESULT_MISSING' });
  } }), error => { assert.deepEqual(error.details.codexUsage, usage); return true; });
});
