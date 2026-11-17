import test from 'node:test';
import assert from 'node:assert/strict';
import { createCodexJsonlParser, MAX_CODEX_JSONL_RECORD_BYTES } from '../src/codex-jsonl.mjs';
import { spawnSync } from 'node:child_process';
import { EventEmitter } from 'node:events';
import { PassThrough } from 'node:stream';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { runGovernedCodexTask, resolvedCodexRuntimeTimeoutMs } from '../src/codex-runtime.mjs';
import { CODEX_RESULT_SCHEMA, normalizeCodexSemanticResult } from '../src/codex-result-schema.mjs';

const result = { status: 'success', summary: 'complete', validation: [], blockedReason: '' };
const frame = value => Buffer.from(JSON.stringify(value) + '\n');

test('long event streams retain a small late result and native usage without a lifetime capture limit', () => {
  const evidence = {}, parser = createCodexJsonlParser(evidence);
  parser.push(frame({ type: 'thread.started', thread_id: 'native-thread' }));
  const tool = frame({ type: 'item.updated', item: { text: 'x'.repeat(64 * 1024) } });
  for (let i = 0; i < 300; i++) parser.push(tool);
  const terminal = frame({ type: 'task_result', result });
  for (const byte of terminal) parser.push(Buffer.from([byte]));
  parser.push(frame({ type: 'turn.completed', usage: { input_tokens: 123, output_tokens: 7 } }));
  assert.equal(parser.finish().summary, 'complete');
  assert.equal(evidence.codexEventCount, 303);
  assert.equal(evidence.codexUsage.input_tokens, 123);
  assert.equal(evidence.codexUsage.output_tokens, 7);
});

test('record overflow and late malformed records fail without accepting an earlier good result', () => {
  for (const suffix of [Buffer.alloc(MAX_CODEX_JSONL_RECORD_BYTES + 1, 120), Buffer.from('{invalid\n')]) {
    const parser = createCodexJsonlParser(); parser.push(frame({ type: 'task_result', result })); parser.push(suffix);
    assert.throws(() => parser.finish(), { code: suffix.length > MAX_CODEX_JSONL_RECORD_BYTES ? 'CODEX_OUTPUT_TOO_LARGE' : 'CODEX_JSON_INVALID' });
  }
});

test('Unicode result limits use the same codepoint units as JSON Schema including split UTF-8', () => {
  const summary = '🧪'.repeat(CODEX_RESULT_SCHEMA.properties.summary.maxLength);
  assert.equal(normalizeCodexSemanticResult({ ...result, summary }).summary, summary);
  assert.throws(() => normalizeCodexSemanticResult({ ...result, summary: summary + '界' }));
  assert.equal(normalizeCodexSemanticResult({ ...result, validation: ['界'.repeat(512)] }).validation[0].length, 512);
  const parser = createCodexJsonlParser(), bytes = frame({ type: 'task_result', result: { ...result, summary: '界🧪' } });
  for (const byte of bytes) parser.push(Buffer.from([byte]));
  assert.equal(parser.finish().summary, '界🧪');
});

test('late diagnostic errors retain bounded redacted messages independently of tool output', () => {
  const parser = createCodexJsonlParser({}, { knownSecrets: ['synthetic-sensitive-value'] });
  for (let i = 0; i < 6; i++) parser.push(frame({ type: 'error', message: `failure ${i}: synthetic-sensitive-value; retry operation safely` }));
  const d = parser.diagnostics();
  assert.equal(d.omittedEvents, 2); assert.equal(d.events.length, 4);
  assert.match(d.events[0].message.text, /failure 0/);
  assert.match(d.events[1].message.text, /failure 3/);
  assert.match(d.events[3].message.text, /failure 5.*REDACTED_SECRET.*retry operation safely/);
});


test('governed runtime keeps semantic result and late diagnostic errors after capture clipping', async t => {
  const cwd = await mkdtemp(join(tmpdir(), 'relay-stream-runtime-'));
  t.after(() => rm(cwd, { recursive: true, force: true }));
  const evidence = {}; let diagnostic;
  const actual = await runGovernedCodexTask({ cwd, inputText: 'Complete the admitted task', evidence,
    env: { PATH: '/usr/bin:/bin' }, buildArgs: () => [],
    readDiagnosticConfig: async () => ({ mode: 'debug' }),
    fallbackStore: async () => ({ reference: { status: 'stored', executionId: 'stream-fixture', slot: 0 }, write: async () => undefined }),
    diagnosticStore: async value => { diagnostic = value; return { status: 'stored', executionId: value.executionId, mode: value.mode }; },
    spawnImpl() {
      const child = new EventEmitter(); child.stdout = new PassThrough(); child.stderr = new PassThrough();
      setImmediate(() => {
        child.emit('spawn');
        const tool = frame({ type: 'item.updated', text: 'x'.repeat(64 * 1024) });
        for (let i = 0; i < 300; i++) child.stdout.write(tool);
        child.stdout.write(frame({ type: 'error', message: 'late known failure; retry safely' }));
        child.stdout.end(frame({ type: 'task_result', result }));
        child.stderr.end(); child.emit('close', 0, null);
      });
      return child;
    }
  });
  assert.equal(actual.summary, 'complete');
  assert.equal(evidence.codexStdoutTruncated, true);
  assert.ok(evidence.codexStdoutBytes > 16 * 1024 * 1024);
  assert.equal(diagnostic.codexErrors.events[0].message.text, 'late known failure; retry safely');
  assert.equal(diagnostic.codexErrors.stdoutTruncated, true);
});


test('runtime budget resolution preserves supported overrides and safe defaults', () => {
  assert.equal(resolvedCodexRuntimeTimeoutMs(undefined), 90 * 60 * 1000);
  assert.equal(resolvedCodexRuntimeTimeoutMs('7200000'), 120 * 60 * 1000);
  assert.equal(resolvedCodexRuntimeTimeoutMs('1000'), 1000);
  for (const value of ['0', '-1', '7200001', 'invalid']) assert.equal(resolvedCodexRuntimeTimeoutMs(value), 90 * 60 * 1000);
});


test('a near-limit record in one-byte fragments keeps bounded retained heap', () => {
  const moduleUrl = new URL('../src/codex-jsonl.mjs', import.meta.url).href;
  const probe = spawnSync(process.execPath, ['--expose-gc', '--input-type=module', '-e', `
    import {createCodexJsonlParser,MAX_CODEX_JSONL_RECORD_BYTES} from ${JSON.stringify(moduleUrl)};
    const parser=createCodexJsonlParser();
    global.gc();const before=process.memoryUsage();
    parser.push(Buffer.from('{"type":"item.updated","text":"'));
    const byte=Buffer.from('x');
    for(let i=0;i<MAX_CODEX_JSONL_RECORD_BYTES-100;i++)parser.push(byte);
    global.gc();const after=process.memoryUsage();
    parser.push(Buffer.from('"}\\n'));
    parser.push(Buffer.from(JSON.stringify({type:'task_result',result:{status:'success',summary:'ok',validation:[],blockedReason:''}})+'\\n'));
    if(parser.finish().summary!=='ok')process.exit(2);
    process.stdout.write(JSON.stringify({heap:after.heapUsed-before.heapUsed,buffers:after.arrayBuffers-before.arrayBuffers}));
  `], { env: { ...process.env }, encoding: 'utf8', timeout: 30000, maxBuffer: 4096 });
  assert.equal(probe.status, 0, probe.stderr);
  const memory = JSON.parse(probe.stdout);
  assert.ok(memory.heap < 32 * 1024 * 1024, JSON.stringify(memory));
  assert.ok(memory.buffers <= 2 * MAX_CODEX_JSONL_RECORD_BYTES, JSON.stringify(memory));
});
