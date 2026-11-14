import test from 'node:test';
import assert from 'node:assert/strict';
import { access, chmod, lstat, mkdir, readFile, writeFile } from 'node:fs/promises';
import { constants } from 'node:fs';
import { join } from 'node:path';
import { fixture } from './fixture.mjs';
import { git } from '../src/trusted-git.mjs';

test('collection distinguishes ignored generated cache from tracked and non-ignored work without reconciling it', async t => {
  const f = await fixture(t); await f.prepare(f.envelope);
  const head = await f.commit('.gitignore', '.generated-cache/\n');
  await mkdir(join(f.cwd, '.generated-cache'));
  await writeFile(join(f.cwd, '.generated-cache', 'output'), 'repeatable output\n');
  const clean = await f.collect(f.envelope);
  assert.equal(clean.head, head); assert.equal(clean.clean, true); assert.ok(clean.bundle);

  await writeFile(join(f.cwd, 'generated-output.tmp'), 'generated but not ignored\n');
  const residue = await f.collect(f.envelope);
  assert.equal(residue.head, head); assert.equal(residue.clean, false); assert.ok(residue.bundle);
  assert.equal(await readFile(join(f.cwd, 'generated-output.tmp'), 'utf8'), 'generated but not ignored\n');
  assert.equal(await f.command(f.cwd, ['rev-parse', 'HEAD']), head);

  await f.commit('generated-output.tmp', 'reviewed task artifact\n');
  await writeFile(join(f.cwd, 'docs/work.md'), 'useful task work remains\n');
  const tracked = await f.collect(f.envelope);
  assert.equal(tracked.clean, false);
  assert.equal(await readFile(join(f.cwd, 'docs/work.md'), 'utf8'), 'useful task work remains\n');
  assert.equal(f.pushes(), 0);
});

// Exercise real access checks under the unprivileged test identity. No sudo,
// mocked permission result or root-mode assumption establishes collector access.
async function denyAccess(t, path, operation) {
  const originalMode = (await lstat(path)).mode & 0o7777;
  await chmod(path, 0o000);
  try {
    try {
      await access(path, constants.R_OK);
      t.skip('current identity can read mode-000 paths; unprivileged permission proof unavailable');
      return;
    } catch (error) { assert.equal(error.code, 'EACCES'); }
    await operation();
  } finally { await chmod(path, originalMode); }
}

async function assertCandidateWithUnknownObservation(f, head, denied) {
  const progress = await f.collect(f.envelope);
  assert.equal(progress.head, head);
  assert.ok(progress.bundle, 'the committed candidate remains available');
  assert.equal(progress.clean, null, 'incomplete observation must not claim clean or dirty');
  assert.equal(progress.worktreeObservation.status, 'unknown');
  assert.equal(progress.worktreeObservation.code, 'WORKTREE_OBSERVATION_INCOMPLETE');
  const diagnostic = progress.worktreeObservation.diagnostic;
  assert.equal(diagnostic.operation, 'worktree-observation');
  assert.equal(diagnostic.primaryCause, 'GIT_LOCAL_FAILURE');
  assert.match(diagnostic.preview, /EACCES/);
  assert.equal((await lstat(denied)).mode & 0o7777, 0o000, 'collection does not repair source permissions');
  assert.equal(await f.command(f.cwd, ['rev-parse', 'HEAD']), head);
}

test('an unreadable generated regular file preserves the candidate with unknown observation and unchanged bytes', async t => {
  const f = await fixture(t); await f.prepare(f.envelope); const head = await f.commit();
  const residue = join(f.cwd, 'generated-output.tmp');
  await writeFile(residue, 'repeatable generated output\n');
  await denyAccess(t, residue, async () => assertCandidateWithUnknownObservation(f, head, residue));
  assert.equal(await readFile(residue, 'utf8'), 'repeatable generated output\n');
  assert.equal(f.pushes(), 0);
});

test('an unreadable ignored cache is irrelevant while inaccessible non-ignored work preserves an unknown observation', async t => {
  const f = await fixture(t); await f.prepare(f.envelope);
  const head = await f.commit('.gitignore', '.generated-cache/\n');
  const cache = join(f.cwd, '.generated-cache'); await mkdir(cache);
  await writeFile(join(cache, 'output'), 'generated output\n');
  await denyAccess(t, cache, async () => assert.equal((await f.collect(f.envelope)).clean, true));
  const unknown = join(f.cwd, 'uncollected-work'); await mkdir(unknown);
  await writeFile(join(unknown, 'task.md'), 'potentially useful work\n');
  await denyAccess(t, unknown, async () => assertCandidateWithUnknownObservation(f, head, unknown));
  assert.equal(await readFile(join(unknown, 'task.md'), 'utf8'), 'potentially useful work\n');
  assert.equal(f.pushes(), 0);
});

test('tracked permission failures preserve the candidate without classifying unreadable changes as a diff', async t => {
  const f = await fixture(t); await f.prepare(f.envelope); const head = await f.commit();
  const tracked = join(f.cwd, 'docs/work.md');
  // Force content inspection even on filesystems with coarse timestamps.
  await writeFile(tracked, 'changed task work remains unreadable\n');
  await denyAccess(t, tracked, async () => assertCandidateWithUnknownObservation(f, head, tracked));
  assert.equal(await readFile(tracked, 'utf8'), 'changed task work remains unreadable\n');
  assert.equal(f.pushes(), 0);
});

test('an expected diff status never swallows a fatal trusted Git failure', async t => {
  const f = await fixture(t);
  await assert.rejects(git(f.source, ['diff', '--exit-code', 'missing-commit'], { allowedExitCodes: [1], rejectStderr: true }),
    error => error.code === 'TRUSTED_GIT_FAILED' && error.details.failureDiagnostic.gitExitCode === 128);
});
