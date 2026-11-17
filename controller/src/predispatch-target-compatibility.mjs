import { constants } from 'node:fs';
import { lstat, open, readdir, readlink } from 'node:fs/promises';
import { dirname, isAbsolute, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { createHash } from 'node:crypto';
import { parseConsumerJson } from '../../consumer/consumer-config.mjs';
import { exactSha, fail } from './execution-contract.mjs';

export const PREDISPATCH_RETENTION_CAPABILITY = 'predispatch-retention-v1';
const execute = promisify(execFile);
const ownSource = fileURLToPath(new URL('../../', import.meta.url));
const stamp = stat => ['dev', 'ino', 'mode', 'uid', 'gid', 'nlink', 'size', 'mtimeMs', 'ctimeMs'].map(key => stat[key]).join(':');
const reject = (check = 'target-compatibility', expected, observed, cause) => {
  throw Object.assign(new Error('PREDISPATCH_TARGET_INCOMPATIBLE', { cause }), {
    code: 'PREDISPATCH_TARGET_INCOMPATIBLE', observation: { check, expected, observed } });
};

async function protectedPath(pathname, { root, ownerUid }, directory = false) {
  if (!isAbsolute(pathname) || resolve(pathname) !== pathname
    || !(pathname === root || pathname.startsWith(root === '/' ? '/' : root + '/'))) reject('protected-path-root', root, pathname);
  for (let at = pathname; ; at = dirname(at)) {
    const info = await lstat(at);
    if (info.isSymbolicLink() || info.uid !== ownerUid || info.mode & 0o022
      || (at !== pathname || directory ? !info.isDirectory() : !info.isFile() || info.nlink !== 1)) reject('protected-path-entry',
        { ownerUid, writableByOthers: false, type: at !== pathname || directory ? 'directory' : 'single-link-file' },
        { path: at, uid: info.uid, mode: info.mode & 0o777, links: info.nlink, symlink: info.isSymbolicLink(), directory: info.isDirectory() });
    if (at === root) break;
    if (dirname(at) === at) reject('protected-path-ancestor', root, at);
  }
}
async function protectedRead(pathname, options) {
  await protectedPath(pathname, options);
  const file = await open(pathname, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  try {
    const before = await file.stat();
    if (!before.isFile() || before.nlink !== 1 || before.size < 1 || before.size > 65536) reject('protected-file-shape', 'single-link file of 1..65536 bytes', { path: pathname, bytes: before.size, links: before.nlink });
    const bytes = await file.readFile();
    if (bytes.length !== before.size || stamp(before) !== stamp(await file.stat())
      || stamp(before) !== stamp(await lstat(pathname))) reject('protected-file-stability', { stamp: stamp(before), bytes: before.size }, { bytes: bytes.length, path: pathname });
    await protectedPath(pathname, options);
    return bytes;
  } finally { await file.close(); }
}
async function protectedGit(root, options) {
  // Only the owner's fresh protected acquisition may supply Git metadata.
  // Never invoke trusted Git against a worker/model-writable checkout.
  let count = 0;
  async function visit(pathname) {
    const info = await lstat(pathname);
    await protectedPath(pathname, options, info.isDirectory());
    if (++count > 10000) reject('protected-git-entry-limit', 10000, count);
    if (info.isDirectory()) for (const entry of await readdir(pathname)) await visit(join(pathname, entry));
  }
  await visit(join(root, '.git'));
}
const consumerSmokeName = 'consumer-general-runner-smoke.mjs';
async function sourceGitTrees(sourceRoot, options) {
  let files = 0, total = 0;
  const object = (kind, bytes) => createHash('sha1').update(kind + ' ' + bytes.length + '\0').update(bytes).digest();
  const hashRows = rows => rows.length ? object('tree', Buffer.concat(rows.sort((a, b) => Buffer.compare(a.key, b.key))
    .flatMap(row => [Buffer.from(row.mode + ' ' + row.name + '\0'), row.hash]))) : null;
  async function tree(directory) {
    const rows = [], withoutConsumerSmoke = [];
    for (const name of await readdir(directory)) {
      if (directory === sourceRoot && name === '.relay-source.json') continue;
      const pathname = join(directory, name), before = await lstat(pathname);
      const consumerSmoke = directory === sourceRoot && name === consumerSmokeName;
      // The consumer renders this one root-owned ABI smoke into reviewed-source.
      // Validate it as protected, but allow its projection beside the exact product tree.
      if (consumerSmoke) await protectedPath(pathname, options);
      // Installed compatibility aliases are additions to a regular-file-only Git archive.
      if (before.isSymbolicLink()) continue;
      if (before.isDirectory()) {
        await protectedPath(pathname, options, true);
        const child = await tree(pathname);
        if (child.full) {
          const row = { key: Buffer.from(name + '/'), mode: '40000', name, hash: child.full };
          rows.push(row);
          withoutConsumerSmoke.push({ ...row, hash: child.withoutConsumerSmoke });
        }
      } else {
        await protectedPath(pathname, options);
        if (++files > 10000 || before.size > 32 * 1024 * 1024 || (total += before.size) > 256 * 1024 * 1024) reject('source-tree-size-limit', { files: 10000, fileBytes: 32 * 1024 * 1024, totalBytes: 256 * 1024 * 1024 }, { files, fileBytes: before.size, totalBytes: total });
        const file = await open(pathname, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
        let bytes;
        try {
          bytes = await file.readFile();
          if (bytes.length !== before.size || stamp(before) !== stamp(await file.stat())
            || stamp(before) !== stamp(await lstat(pathname))) reject('source-file-stability', { stamp: stamp(before), bytes: before.size }, { bytes: bytes.length, path: pathname });
        } finally { await file.close(); }
        const row = { key: Buffer.from(name), mode: before.mode & 0o111 ? '100755' : '100644',
          name, hash: object('blob', bytes) };
        rows.push(row);
        if (!consumerSmoke) withoutConsumerSmoke.push(row);
      }
    }
    return { full: hashRows(rows), withoutConsumerSmoke: hashRows(withoutConsumerSmoke) };
  }
  const trees = await tree(sourceRoot);
  return { full: trees.full?.toString('hex'), withoutConsumerSmoke: trees.withoutConsumerSmoke?.toString('hex') };
}
async function targetMetadata(sourceRoot, target, options) {
  await protectedPath(sourceRoot, options, true);
  const path = join(sourceRoot, 'deploy/installation-contract.json');
  const bytes = await protectedRead(path, options);
  let identity;
  try { identity = parseConsumerJson((await protectedRead(join(sourceRoot, '.relay-source.json'), options)).toString('utf8')); }
  catch (error) { if (error.code !== 'ENOENT') throw error; }
  if (identity) {
    if (identity.revision !== target || !exactSha(identity.tree)) reject('target-source-identity', { revision: target, tree: 'exact SHA' }, identity);
    const trees = await sourceGitTrees(sourceRoot, options);
    if (trees.full !== identity.tree && trees.withoutConsumerSmoke !== identity.tree) reject('target-source-tree', identity.tree, trees);
  } else {
    await protectedGit(sourceRoot, options);
    const git = async (...args) => (await execute('/usr/bin/git', ['--no-replace-objects', '-c', 'core.hooksPath=/dev/null',
      '-c', 'core.fsmonitor=false', '-C', sourceRoot, ...args], { timeout: 30000, maxBuffer: 1024 * 1024,
      env: { PATH: '/usr/bin:/bin', HOME: sourceRoot, XDG_CONFIG_HOME: sourceRoot + '/.xdg-unused',
        GIT_CONFIG_NOSYSTEM: '1', GIT_CONFIG_GLOBAL: '/dev/null', GIT_OPTIONAL_LOCKS: '0' } })).stdout;
    const smokePath = join(sourceRoot, consumerSmokeName);
    let smokePresent = false;
    try {
      const smoke = await lstat(smokePath);
      if (!smoke.isFile() || smoke.nlink !== 1 || smoke.size > 32 * 1024 * 1024) reject('consumer-smoke-file', 'single-link file <=32MiB', { bytes: smoke.size, links: smoke.nlink });
      await protectedPath(smokePath, options);
      smokePresent = true;
    } catch (error) { if (error.code !== 'ENOENT') throw error; }
    const smokeTracked = (await git('ls-tree', '-r', '--name-only', target, '--',
      ':(top,literal)' + consumerSmokeName)).trim();
    const statusArgs = ['status', '--porcelain', '--untracked-files=all'];
    if (smokePresent && !smokeTracked) statusArgs.push('--', '.', ':(top,exclude,literal)' + consumerSmokeName);
    const head = (await git('rev-parse', '--verify', 'HEAD^{commit}')).trim();
    if (head !== target) reject('target-source-head', target, head);
    const status = (await git(...statusArgs)).trim();
    if (status) reject('target-source-cleanliness', 'clean', status);
    if (await git('show', target + ':deploy/installation-contract.json') !== bytes.toString('utf8')) reject('target-contract-bytes', 'matching committed contract', 'different');
  }
  const metadata = parseConsumerJson(bytes.toString('utf8'));
  if (!metadata || metadata.schemaVersion !== 1 || !Number.isSafeInteger(metadata.epoch) || metadata.epoch < 1
    || !Array.isArray(metadata.capabilities) || metadata.capabilities.length > 64
    || !metadata.capabilities.includes(PREDISPATCH_RETENTION_CAPABILITY)) reject('target-retention-capability', PREDISPATCH_RETENTION_CAPABILITY, metadata);
}

// Caller holds the same Writer lock as admit. Repeat at applying/recovery/resume:
// a recovery receipt may be added while a quiesced installation is draining.
// No retained marker means no extra rollback restriction or metadata requirement.
export async function assertPredispatchTargetCompatible({ records, target, sourceRoot = null,
  root = '/', ownerUid = 0 }) {
  if (!records.some(record => Object.hasOwn(record, 'predispatchPending') || Object.hasOwn(record, 'predispatchRecovery'))) return;
  if (!exactSha(target)) reject('target-revision', 'exact SHA', target);
  try { await targetMetadata(sourceRoot ?? ownSource.replace(/\/$/, ''), target, { root: resolve(root), ownerUid }); }
  catch (cause) { reject('target-metadata', 'protected compatible target', { target, sourceRoot }, cause); }
}

// A staged recovery process cannot authorize itself as the installed fence.
// Inspect the actual public wrapper and actual current binding instead.
export async function assertCompatibleInstalledWriter({ consumer, consumerPath = process.env.RELAY_CONSUMER_CONFIG,
  root = '/', ownerUid = 0 }) {
  const rejectFence = (check = 'installed-writer-fence', observed, cause) => {
    throw Object.assign(new Error('PREDISPATCH_COMPATIBLE_WRITER_REQUIRED', { cause }), {
      code: 'PREDISPATCH_COMPATIBLE_WRITER_REQUIRED', observation: { check, observed } });
  };
  try {
    const options = { root: resolve(root), ownerUid };
    const helper = consumer.paths.writerHelper;
    const body = (await protectedRead(helper, options)).toString('utf8');
    const paths = [...body.matchAll(/^\s*\/usr\/bin\/node '([^'\r\n]+)\/current\/reviewed-source\/controller\/src\/privileged-writer-entrypoint[.]mjs'\s*$/gm)];
    if (paths.length !== 1) rejectFence('writer-wrapper-entrypoint-count', paths.length);
    const install = paths[0][1];
    await protectedPath(install, options, true);
    const current = join(install, 'current'), link = await lstat(current);
    if (!link.isSymbolicLink() || link.uid !== ownerUid) rejectFence('writer-current-link', { symlink: link.isSymbolicLink(), uid: link.uid, expectedUid: ownerUid });
    const release = await readlink(current), target = release.split('/').at(-1);
    if (!exactSha(target) || release !== join(install, 'releases', target)) rejectFence('writer-current-release', release);
    const sourceRoot = join(release, 'reviewed-source');
    await assertPredispatchTargetCompatible({ records: [{ predispatchPending: {} }], target, sourceRoot, ...options });
    const writerPath = join(install, 'current/reviewed-source/controller/src/privileged-writer-entrypoint.mjs');
    const bindings = { relay_consumer_config_path: consumerPath,
      relay_writer_credential_env_file: consumer.paths.credentialEnv,
      relay_writer_credential_key_file: consumer.paths.credentialKeyFile,
      relay_writer_claim_root: consumer.paths.claimRoot, relay_writer_helper_release_path: writerPath };
    const template = (await protectedRead(join(sourceRoot,
      'deploy/ansible/roles/relay_controller/templates/relay-writer-controller.j2'), options)).toString('utf8');
    const expected = template.replace(/\{\{\s*([a-z0-9_]+)\s*\}\}/g, (_match, key) => {
      if (typeof bindings[key] !== 'string') rejectFence('writer-template-binding', key);
      return bindings[key];
    });
    const lock = `/usr/bin/flock -w 300 '${consumer.paths.claimRoot}/publication-v2.lock'`;
    const writer = `/usr/bin/node '${writerPath}'`;
    if (body !== expected || body.indexOf(lock) < 0 || body.indexOf(writer) <= body.indexOf(lock)) rejectFence('writer-wrapper-order', { matchesTemplate: body === expected, lockIndex: body.indexOf(lock), writerIndex: body.indexOf(writer) });
    const after = await readlink(current);
    if (after !== release) rejectFence('writer-current-stability', { before: release, after });
  } catch (cause) { rejectFence('installed-writer-fence', undefined, cause); }
}
