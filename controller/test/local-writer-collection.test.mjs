import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createLocalWriterAdapter } from '../src/local-writer.mjs';
import { REPOSITORY } from '../src/execution-contract.mjs';

test('collection transport carries a bounded bundle above ordinary receipt size', async () => {
  const adapter = createLocalWriterAdapter({ spawnImpl: (_command, _args, options) => spawn(process.execPath,
    ['-e', `process.stdin.resume(); process.stdin.on('end', () => process.stdout.write(JSON.stringify({repository:${JSON.stringify(REPOSITORY)},bundle:'a'.repeat(2*1024*1024)})));`], options) });
  assert.equal((await adapter.invoke({ operation: 'collect-progress' })).bundle.length, 2 * 1024 * 1024);
  await assert.rejects(adapter.invoke({ operation: 'preflight' }), { code: 'WRITER_OUTPUT_TOO_LARGE' });
});
