import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { join } from 'node:path';
import { fixture } from './fixture.mjs';
import { git } from '../src/trusted-git.mjs';

test('trusted fetch finishes without detached maintenance before checkout access is transferred', { skip: process.platform === 'win32' }, async t => {
  const f = await fixture(t);
  const dir = join(f.root, 'trusted-prepare'); await mkdir(dir);
  await git(dir, ['init']);
  await git(dir, ['config', 'maintenance.auto', 'true']);
  const trace = join(f.root, 'git-events.jsonl');
  // Trace2 reads its destination before command-line/local config. A test-only
  // shim sets the trace after the production helper filters its environment.
  const executable = execFileSync('which', ['git'], { encoding: 'utf8' }).trim();
  const bin = join(f.root, 'bin'); await mkdir(bin);
  const quote = value => "'" + value.replaceAll("'", "'\\''") + "'";
  await writeFile(join(bin, 'git'), `#!/bin/sh\nexport GIT_TRACE2_EVENT=${quote(trace)}\nexec ${quote(executable)} "$@"\n`, { mode: 0o755 });
  const path = process.env.PATH;
  try {
    process.env.PATH = `${bin}:${path}`;
    await git(dir, ['fetch', '--no-tags', f.remote, 'refs/heads/main']);
  } finally { process.env.PATH = path; }
  assert.equal((await git(dir, ['rev-parse', 'FETCH_HEAD'])).trim(), f.envelope.startHead);
  const events = (await readFile(trace, 'utf8')).trim().split('\n').map(line => JSON.parse(line));
  assert.ok(events.some(event => event.event === 'child_start')); // Fetch transport was traced.
  assert.deepEqual(events.filter(event => event.event === 'child_start'
    && event.argv?.some(arg => arg === 'maintenance' || arg === 'gc')), []);
});
