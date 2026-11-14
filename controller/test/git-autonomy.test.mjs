import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdir, writeFile, open, rename, symlink } from 'node:fs/promises';
import { join } from 'node:path';
import { secretFree } from '../src/trusted-git.mjs';
import { fixture } from './fixture.mjs';

async function publish(f) {
  const progress = await f.collect(f.envelope);
  return f.broker.invoke({ operation: 'publish-progress', runId: 99,
    attemptId: f.envelope.attemptId, bundle: progress.bundle });
}

test('ordinary unpublished amend, cherry-pick and local branch merge preserve original authorship', async t => {
  const f = await fixture(t); await f.prepare(f.envelope);
  await f.commit('first.md', 'first\n');
  await f.command(f.cwd, ['commit', '--amend', '-m', 'amended unpublished work']);
  const first = await f.command(f.cwd, ['rev-parse', 'HEAD']);
  await f.command(f.cwd, ['switch', '-c', 'local-helper']);
  const helper = await f.commit('helper.md', 'helper\n');
  await f.command(f.cwd, ['switch', f.envelope.branch]);
  await f.command(f.cwd, ['cherry-pick', helper]);
  await f.command(f.cwd, ['switch', '-c', 'local-side', first]);
  await f.commit('side.md', 'side\n');
  await f.command(f.cwd, ['switch', f.envelope.branch]);
  await f.command(f.cwd, ['merge', '--no-ff', 'local-side', '-m', 'merge independent local work']);
  const head = await f.command(f.cwd, ['rev-parse', 'HEAD']);
  const result = await publish(f);
  assert.equal(result.publishedHead, head);
  assert.equal(await f.command(f.root, ['--git-dir=' + f.remote, 'show', '-s', '--format=%an', head]), 'owner');
  assert.equal((await f.command(f.root, ['--git-dir=' + f.remote, 'show', '-s', '--format=%P', head])).split(' ').length, 2);
});

for (const kind of ['secret', 'path', 'mode']) test(`side-branch transient ${kind} is scanned even when the final merge tree is safe`, async t => {
  const f = await fixture(t); await f.prepare(f.envelope);
  const base = f.envelope.startHead;
  await f.command(f.cwd, ['switch', '-c', 'local-side']);
  const path = kind === 'path' ? 'bad:name.md' : 'transient.md';
  if (kind === 'mode') {
    await symlink('/etc/hostname', join(f.cwd, path));
    await f.command(f.cwd, ['add', path]); await f.command(f.cwd, ['commit', '-m', 'transient unsafe mode']);
  } else await f.commit(path, kind === 'secret' ? `ghp_${'A'.repeat(30)}\n` : 'transient unsafe path\n');
  await f.command(f.cwd, ['rm', path]); await f.command(f.cwd, ['commit', '-m', 'remove transient content']);
  await f.command(f.cwd, ['switch', f.envelope.branch]);
  await f.commit('safe.md', 'safe\n');
  await f.command(f.cwd, ['merge', '--no-ff', 'local-side', '-m', 'final safe merge']);
  const progress = await f.collect(f.envelope);
  await assert.rejects(f.broker.invoke({ operation: 'publish-progress', runId: 99,
    attemptId: f.envelope.attemptId, bundle: progress.bundle }), {
    code: { secret: 'SECRET_PUBLICATION_SCAN_FAILED', path: 'COMMIT_PATH_INVALID', mode: 'COMMIT_FILE_MODE_INVALID' }[kind]
  });
  assert.equal(f.pushes(), 0); assert.equal(await f.command(f.cwd, ['merge-base', base, 'HEAD']), base);
});

test('packed branch refs and packed candidate objects are imported without worker metadata', async t => {
  const f = await fixture(t); await f.prepare(f.envelope);
  const head = await f.commit('packed.md', 'packed source\n');
  await f.command(f.cwd, ['pack-refs', '--all', '--prune']);
  await f.command(f.cwd, ['repack', '-ad']);
  const result = await publish(f);
  assert.equal(result.publishedHead, head); assert.equal(f.pushes(), 1);
});

test('unreachable oversized loose object residue cannot exhaust candidate acquisition', async t => {
  const f = await fixture(t); await f.prepare(f.envelope);
  const head = await f.commit();
  const directory = join(f.cwd, '.git', 'objects', '00'); await mkdir(directory, { recursive: true });
  const residue = await open(join(directory, '0'.repeat(38)), 'wx');
  await residue.truncate(101 * 1024 * 1024); await residue.close();
  const result = await publish(f);
  assert.equal(result.publishedHead, head); assert.equal(f.pushes(), 1);
});

test('unsafe object storage on the selected candidate path remains a hard boundary', async t => {
  const f = await fixture(t); await f.prepare(f.envelope);
  const head = await f.commit();
  const directory = join(f.cwd, '.git', 'objects', head.slice(0, 2));
  const retained = join(f.root, 'selected-object-directory');
  await rename(directory, retained); await symlink(retained, directory);
  await assert.rejects(f.collect(f.envelope), { code: 'UNTRUSTED_GIT_DIRECTORY_INVALID' });
  assert.equal(f.pushes(), 0);
});


test('PEM marker documentation is publishable while genuine and partial key material is blocked', () => {
  const header = '-----BEGIN ' + 'PRIVATE KEY-----';
  assert.equal(secretFree(`The key starts with \`${header}\`. No key is included.`),
    `The key starts with \`${header}\`. No key is included.`);
  assert.equal(secretFree(header), header);
  for (const prefix of ['', 'RSA ', 'EC ', 'OPENSSH ', 'ENCRYPTED ', 'DSA ']) {
    const body = Buffer.alloc(96, 17).toString('base64');
    const start = '-----BEGIN ' + prefix + 'PRIVATE KEY-----';
    const end = '-----END ' + prefix + 'PRIVATE KEY-----';
    for (const value of [`${start}\n${body}\n${end}`, `${start}\n${body.slice(0, 40)}`,
      `${start}\n${body.match(/.{1,8}/g).join('\n')}\n${end}`]) {
      assert.throws(() => secretFree(value), { code: 'SECRET_PUBLICATION_SCAN_FAILED' });
    }
  }
});


test('a useful small candidate may contain more than 128 commits within bounded object work', async t => {
  const f = await fixture(t); await f.prepare(f.envelope);
  const tree = await f.command(f.cwd, ['rev-parse', 'HEAD^{tree}']);
  let head = f.envelope.startHead;
  for (let i = 0; i < 129; i++) head = await f.command(f.cwd, ['commit-tree', tree, '-p', head, '-m', `small coherent change ${i}`]);
  await f.command(f.cwd, ['update-ref', `refs/heads/${f.envelope.branch}`, head]);
  const result = await publish(f);
  assert.equal(result.publishedHead, head); assert.equal(f.pushes(), 1);
});

test('local reset cannot discard already published task progress', async t => {
  const f = await fixture(t); await f.prepare(f.envelope);
  const published = await f.commit('published.md', 'published frontier\n'); await publish(f);
  await f.command(f.cwd, ['reset', '--hard', f.envelope.startHead]);
  await f.commit('replacement.md', 'unpublished replacement without the published frontier\n');
  await assert.rejects(publish(f), { code: 'REMOTE_HEAD_CHANGED' });
  assert.equal(await f.remoteHead(), published); assert.equal(f.pushes(), 1);
});
