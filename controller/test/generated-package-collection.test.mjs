import test from 'node:test';
import assert from 'node:assert/strict';
import { chmod, chown, cp, lstat, mkdir, readFile, readdir, writeFile } from 'node:fs/promises';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const exec = promisify(execFile);
const workerUid = 983; const workerPrivateGid = 980;
const collectorUid = 985; const collectorPrivateGid = 982; const sharedGid = 979;
const directories = ['', 'boot', 'skill', 'skill/references', 'vibemodes', 'vibespecs', 'vibespecs/protocols', 'receipts'];
const files = ['vibe.toml', 'README.md', 'receipt.json', 'boot/start.md', 'boot/context.md',
  'skill/SKILL.md', 'skill/README.md', 'skill/references/workflow.md', 'skill/references/safety.md', 'skill/references/package.md',
  'vibemodes/default.md', 'vibemodes/worker.md', 'vibemodes/collector.md', 'vibespecs/contract.md', 'vibespecs/public.md',
  'vibespecs/protocols/task.md', 'vibespecs/protocols/review.md', 'vibespecs/protocols/execution.md',
  'receipts/manifest.json', 'receipts/index.json', 'receipts/payload.json'];

async function facts(path) {
  const stat = await lstat(path);
  return { uid: stat.uid, gid: stat.gid, mode: stat.mode & 0o7777, ino: stat.ino,
    dev: stat.dev, size: stat.size, ctimeMs: stat.ctimeMs };
}

function renameIdentity({ ctimeMs, ...identity }) { return identity; }

test('generated package staging and atomic replacement stay collectable across distinct Linux UIDs and primary groups', {
  skip: process.platform !== 'linux' || process.getuid?.() !== 0
    ? 'requires native Linux root for disposable numeric UID/GID separation; no escalation or account changes attempted' : false
}, async t => {
  const runAs = (uid, gid, args, options = {}) => exec('setpriv', [
    '--reuid', String(uid), '--regid', String(gid), '--groups', String(sharedGid), process.execPath, ...args
  ], { env: { PATH: process.env.PATH }, ...options });
  try {
    for (const [uid, gid] of [[workerUid, workerPrivateGid], [workerUid, sharedGid], [collectorUid, collectorPrivateGid]]) {
      const identity = JSON.parse((await runAs(uid, gid, ['--input-type=module', '-e',
        'console.log(JSON.stringify({uid:process.geteuid(),gid:process.getegid(),groups:process.getgroups()}))'])).stdout);
      assert.equal(identity.uid, uid); assert.equal(identity.gid, gid); assert.ok(identity.groups.includes(sharedGid));
    }
  } catch (error) {
    if (error.code === 'ENOENT' || /(?:Operation not permitted|setgroups failed|setresuid failed|setresgid failed)/.test(error.stderr ?? '')) {
      t.skip('setpriv numeric credential separation unavailable; no cross-UID collection proof claimed'); return;
    }
    throw error;
  }

  const { fixture } = await import('./fixture.mjs');
  const { safeFailureDiagnosticReference } = await import('../src/diagnostics.mjs');
  const f = await fixture(t); await f.prepare(f.envelope);
  const head = await f.commit('.gitignore', '.generated-cache/\n');
  // Only fixture infrastructure is initialized by root. Every generated public
  // or private artifact below is created by the real unprivileged producer.
  async function ownFixture(path, uid, gid, directoryMode, fileMode) {
    const stat = await lstat(path); await chown(path, uid, gid);
    await chmod(path, stat.isDirectory() ? directoryMode : fileMode);
    if (stat.isDirectory()) for (const name of await readdir(path)) await ownFixture(join(path, name), uid, gid, directoryMode, fileMode);
  }
  await chmod(f.root, 0o755); await chmod(join(f.root, 'work'), 0o755);
  await ownFixture(f.cwd, workerUid, sharedGid, 0o2770, 0o660);
  const stage = join(f.root, 'outside-checkout-stage'); await mkdir(stage);
  await chown(stage, workerUid, workerPrivateGid); await chmod(stage, 0o700);
  assert.equal((await lstat(stage)).mode & 0o2000, 0);
  assert.equal((await lstat(stage)).dev, (await lstat(f.cwd)).dev);

  const scratch = join(f.root, 'collector'); await mkdir(scratch);
  await chown(scratch, collectorUid, collectorPrivateGid); await chmod(scratch, 0o700);
  const remote = join(scratch, 'remote.git'); await cp(f.remote, remote, { recursive: true });
  await ownFixture(remote, collectorUid, collectorPrivateGid, 0o755, 0o644);
  const config = join(scratch, 'consumer.json');
  await writeFile(config, await readFile(fileURLToPath(new URL('../../consumer/fixtures/example.json', import.meta.url))));
  await chown(config, collectorUid, collectorPrivateGid); await chmod(config, 0o600);
  const observer = join(scratch, 'observe.mjs');
  await writeFile(observer, `import { collectProgress } from ${JSON.stringify(new URL('../src/trusted-git.mjs', import.meta.url).href)};
const identity = { uid: process.geteuid(), gid: process.getegid(), groups: process.getgroups() };
try { console.log(JSON.stringify({ identity, progress: await collectProgress(${JSON.stringify(f.cwd)}, ${JSON.stringify(f.envelope)}, ${JSON.stringify({ root: scratch, remote })}) })); }
catch (error) { console.log(JSON.stringify({ identity, error: { code: error.code, details: error.details } })); }
`);
  await chown(observer, collectorUid, collectorPrivateGid); await chmod(observer, 0o600);
  const observe = async () => {
    const result = JSON.parse((await runAs(collectorUid, collectorPrivateGid, [observer], {
      env: { PATH: process.env.PATH, RELAY_CONSUMER_CONFIG: config }
    })).stdout);
    assert.equal(result.identity.uid, collectorUid); assert.equal(result.identity.gid, collectorPrivateGid);
    assert.ok(result.identity.groups.includes(sharedGid)); assert.ok(!result.identity.groups.includes(workerPrivateGid));
    return result;
  };

  const producer = join(f.root, 'producer.mjs');
  const packageRoot = join(f.cwd, 'generated-package');
  await writeFile(producer, `import { chmod, lstat, mkdir, rename, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
const cwd = ${JSON.stringify(f.cwd)}; const stage = ${JSON.stringify(stage)}; const target = ${JSON.stringify(packageRoot)};
const directories = ${JSON.stringify(directories)}; const files = ${JSON.stringify(files)};
const mode = process.argv[2]; process.umask(0o007);
const describe = async path => { const s = await lstat(path); return { uid:s.uid, gid:s.gid, mode:s.mode & 0o7777, ino:s.ino, dev:s.dev, size:s.size, ctimeMs:s.ctimeMs }; };
if (mode === 'baseline' || mode === 'fixed') {
  const next = join(stage, mode);
  for (const directory of directories) await mkdir(join(next, directory), { mode: 0o770 });
  for (const file of files) await writeFile(join(next, file), file === 'receipts/payload.json'
    ? 'synthetic public package payload\\n'.repeat(8192) : 'synthetic public package: ' + file + '\\n', { mode: 0o660 });
  // Authored mode transition and atomic file replacement are producer actions,
  // not collector-side chmod/chgrp repair of an existing generated tree.
  const manifest = join(next, 'receipts/manifest.json'); await chmod(manifest, 0o600); await chmod(manifest, 0o660);
  const temporary = join(next, 'receipt.json.tmp'); await writeFile(temporary, 'atomically replaced public receipt\\n', { mode: 0o660 });
  await rename(temporary, join(next, 'receipt.json'));
  const staged = await describe(next);
  if (mode === 'fixed') await rename(target, join(stage, 'retained-baseline'));
  await rename(next, target);
  console.log(JSON.stringify({ uid:process.geteuid(), gid:process.getegid(), groups:process.getgroups(), staged, installed:await describe(target) }));
} else if (mode === 'private-file') {
  await writeFile(join(cwd, 'unknown-private-file'), 'private bytes remain protected\\n', { mode: 0o600 });
} else if (mode === 'private-directory') {
  const directory = join(stage, 'next-private-directory'); await mkdir(directory, { mode: 0o700 });
  await writeFile(join(directory, 'private'), 'private nested bytes\\n', { mode: 0o600 });
  await rename(directory, join(cwd, 'unknown-private-directory'));
} else if (mode === 'ignored-cache') {
  const cache = join(stage, 'next-private-cache'); await mkdir(cache, { mode: 0o700 });
  await writeFile(join(cache, '.gitignore'), '*\\n', { mode: 0o600 });
  await writeFile(join(cache, 'private'), 'ignored private bytes\\n', { mode: 0o600 });
  await rename(cache, join(cwd, '.generated-cache'));
} else if (mode === 'retain-private-file' || mode === 'retain-private-directory') {
  const name = mode === 'retain-private-file' ? 'unknown-private-file' : 'unknown-private-directory';
  await rename(join(cwd, name), join(stage, name));
} else throw new Error('unknown synthetic producer operation');
`, { mode: 0o644 });
  const produce = async (operation, gid = sharedGid) => runAs(workerUid, gid, [producer, operation]);
  const packageFacts = async () => Object.fromEntries(await Promise.all([...directories, ...files].map(async path =>
    [path, await facts(join(packageRoot, path))])));
  const assertPackage = async gid => {
    const all = await packageFacts(); assert.equal(Object.keys(all).length, 29);
    for (const directory of directories) assert.deepEqual(
      { uid: all[directory].uid, gid: all[directory].gid, mode: all[directory].mode }, { uid: workerUid, gid, mode: 0o770 });
    for (const file of files) assert.deepEqual(
      { uid: all[file].uid, gid: all[file].gid, mode: all[file].mode }, { uid: workerUid, gid, mode: 0o660 });
    assert.ok(all['receipts/payload.json'].size > 64 * 1024);
    assert.equal(await readFile(join(packageRoot, 'receipt.json'), 'utf8'), 'atomically replaced public receipt\n');
    return all;
  };
  const assertDenied = (result, context) => {
    assert.equal(result.progress, undefined); assert.equal(result.error.code, 'TRUSTED_GIT_FAILED');
    const diagnostic = result.error.details.failureDiagnostic;
    assert.equal(diagnostic.classification, 'GIT_LOCAL_FAILURE'); assert.equal(diagnostic.operation, 'worktree-observation');
    assert.equal(diagnostic.diagnosticCode, 'EACCES'); assert.equal(diagnostic.syscall, 'open'); assert.equal(diagnostic.pathContext, 'checkout');
    assert.match(diagnostic.preview, new RegExp(context + '; syscall=open; collector-euid=985; collector-egid=982'));
    assert.deepEqual(safeFailureDiagnosticReference(diagnostic), diagnostic);
    for (const sensitive of [f.root, 'generated-package', 'unknown-private', 'receipt.json']) assert.ok(!JSON.stringify(diagnostic).includes(sensitive));
  };

  const baseline = JSON.parse((await produce('baseline', workerPrivateGid)).stdout);
  assert.equal(baseline.uid, workerUid); assert.equal(baseline.gid, workerPrivateGid); assert.ok(baseline.groups.includes(sharedGid));
  assert.deepEqual(renameIdentity(baseline.installed), renameIdentity(baseline.staged)); // Rename preserved mode, group and inode despite the setgid destination.
  const beforeDenied = await assertPackage(workerPrivateGid);
  assertDenied(await observe(), 'source-directory');
  assert.deepEqual(await packageFacts(), beforeDenied);

  const fixed = JSON.parse((await produce('fixed')).stdout);
  assert.equal(fixed.uid, workerUid); assert.equal(fixed.gid, sharedGid);
  assert.deepEqual(renameIdentity(fixed.installed), renameIdentity(fixed.staged)); assert.notEqual(fixed.installed.ino, baseline.installed.ino);
  const beforeCollected = await assertPackage(sharedGid);
  const collected = await observe(); assert.equal(collected.error, undefined);
  assert.equal(collected.progress.head, head); assert.equal(collected.progress.clean, false); // Public package remains untracked work.
  assert.ok(collected.progress.bundle); assert.deepEqual(await packageFacts(), beforeCollected);

  await produce('ignored-cache');
  const cachePaths = ['.generated-cache', '.generated-cache/.gitignore', '.generated-cache/private'];
  const cacheFacts = await Promise.all(cachePaths.map(path => facts(join(f.cwd, path))));
  assert.deepEqual(cacheFacts.map(stat => stat.mode), [0o700, 0o600, 0o600]);
  assert.equal((await observe()).progress.clean, false);
  assert.deepEqual(await Promise.all(cachePaths.map(path => facts(join(f.cwd, path)))), cacheFacts);
  for (const [kind, context, expectedMode] of [['file', 'source-read', 0o600], ['directory', 'source-directory', 0o700]]) {
    await produce('private-' + kind);
    const path = join(f.cwd, 'unknown-private-' + kind); const before = await facts(path);
    assert.equal(before.uid, workerUid); assert.equal(before.mode, expectedMode);
    assertDenied(await observe(), context); assert.deepEqual(await facts(path), before);
    // Preserve private evidence outside the checkout using the producer's own
    // rename; the collector never broadens it to obtain a successful result.
    await produce('retain-private-' + kind);
    const retained = await facts(join(stage, 'unknown-private-' + kind));
    assert.equal(retained.ino, before.ino); assert.equal(retained.mode, expectedMode);
  }
  assert.equal((await observe()).progress.clean, false);
  assert.deepEqual(await Promise.all(cachePaths.map(path => facts(join(f.cwd, path)))), cacheFacts);
  assert.deepEqual(await packageFacts(), beforeCollected); assert.equal(f.pushes(), 0);
});
