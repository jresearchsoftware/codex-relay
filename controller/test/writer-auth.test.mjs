import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { WRITER_TOKEN_PERMISSIONS } from '../src/writer-auth.mjs';

const SOURCE = new URL('../src/writer-auth.mjs', import.meta.url);

test('Writer publication token requests exactly the admitted permissions plus workflow writes', async () => {
  assert.deepEqual(WRITER_TOKEN_PERMISSIONS, {
    metadata: 'read',
    contents: 'write',
    issues: 'write',
    pull_requests: 'write',
    workflows: 'write'
  });
  const source = await readFile(SOURCE, 'utf8');
  assert.match(source, /permissions:\s*WRITER_TOKEN_PERMISSIONS/);
});
