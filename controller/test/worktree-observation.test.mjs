import test from 'node:test';
import assert from 'node:assert/strict';
import { chmod, chown, cp, link, lstat, mkdir, readFile, readdir, rename, symlink, writeFile } from 'node:fs/promises';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { fixture } from './fixture.mjs';
import { collectProgress } from '../src/trusted-git.mjs';

const exec = promisify(execFile);

test('same-UID mode-0600 tracked and untracked artifacts are fully observed without permission repair', async t => {
  const f = await fixture(t); await f.prepare(f.envelope);
  const tracked = join(f.cwd, 'package-lock.json');
  const content = '{"name":"synthetic-readable-artifact"}\n';
  const head = await f.commit('package-lock.json', content); await chmod(tracked, 0o600);
  const clean = await f.collect(f.envelope);
  assert.equal(clean.head, head); assert.equal(clean.clean, true);
  assert.equal((await lstat(tracked)).mode & 0o777, 0o600);
  assert.equal(await f.command(f.cwd, ['ls-tree', 'HEAD', 'package-lock.json']),
    `100644 blob ${await f.command(f.cwd, ['hash-object', 'package-lock.json'])}\tpackage-lock.json`);

  const untracked = join(f.cwd, 'private-output.tmp'); await writeFile(untracked, 'private bytes\n', { mode: 0o600 });
  assert.equal((await f.collect(f.envelope)).clean, false);
  assert.equal((await lstat(untracked)).mode & 0o777, 0o600);
  assert.equal(await readFile(untracked, 'utf8'), 'private bytes\n');
  assert.equal(f.pushes(), 0);
});

test('collection never invokes worker filters, fsmonitor, hooks, or copied nested metadata', async t => {
  const f = await fixture(t); await f.prepare(f.envelope);
  await f.commit('.gitattributes', 'docs/work.md filter=hostile diff=hostile\n');
  const sentinel = join(f.root, 'worker-metadata-executed');
  const script = join(f.cwd, '.git', 'hostile.cjs');
  await writeFile(script, `require('node:fs').writeFileSync(${JSON.stringify(sentinel)}, 'executed'); process.exit(91);\n`);
  const command = `${process.execPath} ${script}`;
  await f.command(f.cwd, ['config', 'filter.hostile.clean', command]);
  await f.command(f.cwd, ['config', 'filter.hostile.required', 'true']);
  await f.command(f.cwd, ['config', 'diff.hostile.command', command]);
  await f.command(f.cwd, ['config', 'core.fsmonitor', command]);
  await f.command(f.cwd, ['config', 'core.hooksPath', join(f.cwd, '.git', 'hooks')]);
  await writeFile(join(f.cwd, '.git', 'index'), 'untrusted broken index');
  await writeFile(join(f.cwd, '.git', 'info', 'exclude'), 'residue.txt\n');
  assert.equal((await f.collect(f.envelope)).clean, true);

  await writeFile(join(f.cwd, 'residue.txt'), 'worker-local excludes do not cross\n');
  await mkdir(join(f.cwd, 'nested', '.git'), { recursive: true });
  await writeFile(join(f.cwd, 'nested', '.git', 'config'), `[core]\n\tfsmonitor = ${command}\n`);
  assert.equal((await f.collect(f.envelope)).clean, false);
  await assert.rejects(lstat(sentinel), { code: 'ENOENT' });
  assert.equal(await readFile(join(f.cwd, '.git', 'index'), 'utf8'), 'untrusted broken index');
});

test('trusted ignore copies retain nested patterns, negation, and raw pathname handling', async t => {
  const f = await fixture(t); await f.prepare(f.envelope);
  await f.commit('.gitignore', 'cache/\n*.tmp\n!keep.tmp\n');
  await mkdir(join(f.cwd, 'nested')); await f.commit('nested/.gitignore', '*.log\n');
  await mkdir(join(f.cwd, 'cache')); await writeFile(join(f.cwd, 'cache', 'ignored'), 'ignored cache\n');
  await writeFile(join(f.cwd, 'discard.tmp'), 'ignored bytes\n');
  await writeFile(join(f.cwd, 'nested', 'ignored.log'), 'ignored log\n');
  assert.equal((await f.collect(f.envelope)).clean, true);
  await writeFile(join(f.cwd, 'keep.tmp'), 'included through negation\n');
  assert.equal((await f.collect(f.envelope)).clean, false);
  await f.commit('keep.tmp', 'included through negation\n');
  await writeFile(join(f.cwd, 'line\nbreak.tmp'), 'ignored newline name\n');
  assert.equal((await f.collect(f.envelope)).clean, true);
  await writeFile(join(f.cwd, 'line\nbreak.txt'), 'observed newline name\n');
  assert.equal((await f.collect(f.envelope)).clean, false);
});

test('copied attributes preserve safe line-ending normalization while raw source bytes stay intact', async t => {
  const f = await fixture(t); await f.prepare(f.envelope);
  await f.commit('.gitattributes', 'docs/work.md text eol=crlf\n');
  await writeFile(join(f.cwd, 'docs/work.md'), 'baseline\r\n');
  assert.equal((await f.collect(f.envelope)).clean, true);
  assert.equal(await readFile(join(f.cwd, 'docs/work.md'), 'utf8'), 'baseline\r\n');
});

test('ignored and non-ignored empty directories retain the existing clean-tree meaning', async t => {
  const f = await fixture(t); await f.prepare(f.envelope); await f.commit('.gitignore', 'ignored-empty/\n');
  await mkdir(join(f.cwd, 'ignored-empty')); await mkdir(join(f.cwd, 'ordinary-empty'));
  assert.equal((await f.collect(f.envelope)).clean, true);
});

test('checkout acquisition rejects symlinks in any absolute ancestor', async t => {
  const f = await fixture(t); await f.prepare(f.envelope);
  const alias = join(f.root, 'work-alias'); await symlink(join(f.root, 'work'), alias);
  await assert.rejects(collectProgress(join(alias, f.envelope.attemptId), f.envelope, { root: f.root, remote: f.remote }),
    { code: 'UNTRUSTED_GIT_DIRECTORY_INVALID' });
});

test('object import rejects metadata/ref directory symlinks and hardlinked object bytes', async t => {
  for (const surface of ['object-directory', 'ref-directory', 'object-file']) {
    const f = await fixture(t); await f.prepare(f.envelope); await f.commit();
    const outside = join(f.root, 'outside-source'); await mkdir(outside);
    if (surface === 'ref-directory') {
      const refs = join(f.cwd, '.git', 'refs', 'heads');
      await rename(refs, join(outside, 'heads')); await symlink(join(outside, 'heads'), refs);
      await assert.rejects(f.collect(f.envelope), { code: 'UNTRUSTED_GIT_DIRECTORY_INVALID' });
      continue;
    }
    const objects = join(f.cwd, '.git', 'objects'); const existing = new Set(await readdir(objects));
    const folder = Array.from({ length: 256 }, (_, i) => i.toString(16).padStart(2, '0')).find(value => !existing.has(value));
    assert.ok(folder);
    if (surface === 'object-directory') {
      await writeFile(join(outside, '0'.repeat(38)), 'outside object bytes must not be read\n');
      await symlink(outside, join(objects, folder));
      await assert.rejects(f.collect(f.envelope), { code: 'UNTRUSTED_GIT_DIRECTORY_INVALID' });
    } else {
      await mkdir(join(objects, folder));
      const bytes = join(outside, 'private'); await writeFile(bytes, 'outside hardlinked bytes\n', { mode: 0o600 });
      await link(bytes, join(objects, folder, '0'.repeat(38)));
      await assert.rejects(f.collect(f.envelope), { code: 'UNTRUSTED_GIT_FILE_INVALID' });
      assert.equal(await readFile(bytes, 'utf8'), 'outside hardlinked bytes\n');
    }
  }
});

test('worktree observation rejects hardlinks and sanitizes inaccessible-path failures', async t => {
  const f = await fixture(t); await f.prepare(f.envelope); await f.commit();
  const outside = join(f.root, 'outside-private'); await writeFile(outside, 'never copy a shared inode\n', { mode: 0o600 });
  await link(outside, join(f.cwd, 'untracked-hardlink'));
  await assert.rejects(f.collect(f.envelope), { code: 'UNTRUSTED_GIT_FILE_INVALID' });
  const other = await fixture(t); await other.prepare(other.envelope); await other.commit();
  const privatePath = join(other.cwd, 'private-filename-does-not-belong-in-outcome');
  await writeFile(privatePath, 'unreadable bytes\n'); await chmod(privatePath, 0o000);
  try {
    if (process.getuid?.() === 0) return;
    await assert.rejects(other.collect(other.envelope), error => {
      const diagnostic = error.details.failureDiagnostic;
      assert.equal(diagnostic.pathContext, 'checkout'); assert.match(diagnostic.preview, /EACCES/);
      assert.ok(!JSON.stringify(diagnostic).includes(other.cwd));
      assert.ok(!JSON.stringify(diagnostic).includes('private-filename'));
      return true;
    });
  } finally { await chmod(privatePath, 0o600); }
});

test('symlink residue is observed without opening its external target', async t => {
  const f = await fixture(t); await f.prepare(f.envelope); await f.commit();
  const outside = join(f.root, 'unreadable-outside'); await mkdir(outside);
  await writeFile(join(outside, 'private'), 'must never be opened\n'); await chmod(outside, 0o000);
  try {
    await symlink(outside, join(f.cwd, 'untracked-link'));
    assert.equal((await f.collect(f.envelope)).clean, false);
    assert.equal((await lstat(outside)).mode & 0o777, 0o000);
  } finally { await chmod(outside, 0o700); }
});

test('distinct Linux worker/collector UIDs share 0640 access; 0600 fails while scoped root observation preserves it', {
  skip: process.platform !== 'linux' || process.getuid?.() !== 0
    ? 'requires native root test identity for disposable synthetic UID separation; no escalation attempted' : false
}, async t => {
  const f = await fixture(t); await f.prepare(f.envelope);
  const artifact = join(f.cwd, 'package-lock.json');
  const head = await f.commit('package-lock.json', '{"synthetic":"cross-uid"}\n');
  const workerUid = 983; const collectorUid = 985; const sharedGid = 979;
  async function ownTree(path, uid) {
    const stat = await lstat(path);
    await chown(path, uid, sharedGid);
    if (stat.isDirectory()) {
      await chmod(path, 0o755);
      for (const name of await readdir(path)) await ownTree(join(path, name), uid);
    } else await chmod(path, 0o644);
  }
  await chmod(f.root, 0o755); await chmod(join(f.root, 'work'), 0o755);
  await ownTree(f.cwd, workerUid);
  const scratch = join(f.root, 'collector'); await mkdir(scratch); await chown(scratch, collectorUid, sharedGid);
  const remote = join(scratch, 'remote.git'); await cp(f.remote, remote, { recursive: true }); await ownTree(remote, collectorUid);
  const config = join(scratch, 'consumer.json');
  await writeFile(config, await readFile(fileURLToPath(new URL('../../consumer/fixtures/example.json', import.meta.url))), { mode: 0o600 });
  await chown(config, collectorUid, sharedGid);
  const script = join(scratch, 'observe.mjs');
  await writeFile(script, `import { collectProgress } from ${JSON.stringify(new URL('../src/trusted-git.mjs', import.meta.url).href)};
try { console.log(JSON.stringify({ progress: await collectProgress(${JSON.stringify(f.cwd)}, ${JSON.stringify(f.envelope)}, ${JSON.stringify({ root: scratch, remote })}) })); }
catch (error) { console.log(JSON.stringify({ error: { code: error.code, details: error.details } })); }
`, { mode: 0o600 });
  await chown(script, collectorUid, sharedGid);
  const observe = async () => JSON.parse((await exec(process.execPath, [script], {
    uid: collectorUid, gid: sharedGid, env: { PATH: process.env.PATH, RELAY_CONSUMER_CONFIG: config }
  })).stdout);
  await chmod(artifact, 0o640);
  assert.deepEqual((await observe()).progress, { head, bundle: (await f.collect(f.envelope)).bundle, clean: true });
  await chmod(artifact, 0o600);
  const denied = (await observe()).error;
  assert.equal(denied.code, 'TRUSTED_GIT_FAILED');
  assert.equal(denied.details.failureDiagnostic.operation, 'worktree-observation');
  assert.match(denied.details.failureDiagnostic.preview, /EACCES/);
  const before = await lstat(artifact);
  assert.equal((await f.collect(f.envelope)).clean, true);
  const after = await lstat(artifact);
  assert.equal(after.uid, workerUid); assert.equal(after.gid, sharedGid);
  assert.equal(after.mode & 0o777, 0o600); assert.equal(after.ctimeMs, before.ctimeMs);
});
