import test from 'node:test';
import assert from 'node:assert/strict';
import { writeFile, symlink } from 'node:fs/promises';
import { join } from 'node:path';
import { fixture } from './fixture.mjs';
import { safePath, branchName } from '../src/execution-contract.mjs';

test('repository Git paths reject traversal, metadata escape and malformed components', () => {
  for (const path of ['', '.', './', './file', '..', '../file', 'docs/../file', '/tmp/file',
    '.git', '.GIT/config', 'docs/.git/config', 'docs//file', 'docs/./file', 'docs/',
    'C:/file', 'docs\\file', 'docs/file\0suffix', 'docs/file\n', 'docs/file\x7f']) {
    assert.equal(safePath(path), false, JSON.stringify(path));
  }
  for (const path of ['AGENTS.md', '.github/workflows/new.yml', 'automation/new.mjs',
    'new directory/新しい.md', 'admin/example.md', 'secrets/README.md', '.gitmodules']) {
    assert.equal(safePath(path), true, path);
  }
  for (const branch of ['main', 'other/task', 'codex/../main', 'codex//task', 'codex/task.lock']) {
    assert.throws(() => branchName(branch), { code: 'BRANCH_INVALID' });
  }
});

async function rejectProgress(f, code) {
  const progress = await f.collect(f.envelope);
  await assert.rejects(f.broker.invoke({ operation: 'publish-progress', runId: 99,
    attemptId: f.envelope.attemptId, bundle: progress.bundle }), { code });
  assert.equal(f.pushes(), 0);
}

for (const remediation of [false, true]) test(`Writer verifies bot identity for repository-wide changes, remediation=${remediation}`, async t => {
  const f = await fixture(t, { remediation }); await f.prepare(f.envelope);
  await writeFile(join(f.cwd, 'new-file.md'), 'task required\n');
  await f.command(f.cwd, ['add', 'new-file.md']);
  // The fixture command defaults to the owner, not the expected worker bot.
  await f.command(f.cwd, ['commit', '-m', 'incorrect identity']);
  await rejectProgress(f, 'COMMIT_OWNERSHIP_INVALID');
});

test('Writer rejects a non-linear task commit even with the expected bot identity', async t => {
  const f = await fixture(t); await f.prepare(f.envelope); await f.commit();
  const first = await f.command(f.cwd, ['rev-parse', 'HEAD']);
  const tree = await f.command(f.cwd, ['rev-parse', 'HEAD^{tree}']);
  const name = 'example-writer'; const email = 'example-writer@example.invalid';
  const merge = await f.command(f.cwd, ['commit-tree', tree, '-p', first, '-p', f.envelope.startHead, '-m', 'non-linear'], {
    GIT_AUTHOR_NAME: name, GIT_COMMITTER_NAME: name, GIT_AUTHOR_EMAIL: email, GIT_COMMITTER_EMAIL: email
  });
  await f.command(f.cwd, ['update-ref', `refs/heads/${f.envelope.branch}`, merge]);
  await rejectProgress(f, 'COMMIT_OWNERSHIP_INVALID');
});

test('Writer rejects symlink and gitlink file modes on any repository path', async t => {
  for (const gitlink of [false, true]) {
    const f = await fixture(t); await f.prepare(f.envelope);
    const name = 'example-writer'; const email = 'example-writer@example.invalid';
    if (gitlink) {
      await f.command(f.cwd, ['update-index', '--add', '--cacheinfo', `160000,${f.envelope.startHead},untrusted-module`]);
    } else {
      await symlink('/etc/hostname', join(f.cwd, 'untrusted-link'));
      await f.command(f.cwd, ['add', 'untrusted-link']);
    }
    await f.command(f.cwd, ['commit', '-m', 'unsafe mode'], {
      GIT_AUTHOR_NAME: name, GIT_COMMITTER_NAME: name, GIT_AUTHOR_EMAIL: email, GIT_COMMITTER_EMAIL: email
    });
    await rejectProgress(f, 'COMMIT_FILE_MODE_INVALID');
  }
});

test('Writer does not follow a symlink-style Git metadata handoff', async t => {
  const f = await fixture(t); await f.prepare(f.envelope); await f.commit();
  const { rename } = await import('node:fs/promises');
  await rename(join(f.cwd, '.git'), join(f.cwd, 'metadata'));
  await symlink(join(f.cwd, 'metadata'), join(f.cwd, '.git'));
  await assert.rejects(f.collect(f.envelope), { code: 'UNTRUSTED_GIT_DIRECTORY_INVALID' });
  assert.equal(f.pushes(), 0);
});

test('Writer cannot import a task checkout with a changed branch identity', async t => {
  const f = await fixture(t); await f.prepare(f.envelope); await f.commit();
  await f.command(f.cwd, ['switch', '-c', 'codex/other']);
  await assert.rejects(f.collect(f.envelope), { code: 'WORKING_BRANCH_CHANGED' });
  assert.equal(f.pushes(), 0);
});

test('Writer rejects malformed repository paths in imported commits', async t => {
  const f = await fixture(t); await f.prepare(f.envelope);
  await f.commit('malformed:name.md', 'task change\n');
  await rejectProgress(f, 'COMMIT_PATH_INVALID');
});
