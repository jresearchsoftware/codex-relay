import { CONSUMER } from '../../consumer/consumer.mjs';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { mkdtemp, mkdir, readFile, writeFile, opendir, lstat, open, readlink, rm } from 'node:fs/promises';
import { constants } from 'node:fs';
import { createHash } from 'node:crypto';
import { isAbsolute, join } from 'node:path';
import { tmpdir } from 'node:os';
import { REPOSITORY, exactSha, fail, safePath, branchName } from './execution-contract.mjs';
import { boundedDiagnosticText } from './diagnostics.mjs';

const exec = promisify(execFile);
export const REMOTE = `https://github.com/${REPOSITORY}.git`;
const SECRET = /github_pat_[A-Za-z0-9_]{30,}|gh[pousr]_[A-Za-z0-9_]{20,}|-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----/;
const GIT_DIAGNOSTIC_BYTES = 2048;
const GIT_OPERATION_NAMES = new Set(['init', 'fetch', 'push', 'ls-remote', 'rev-parse', 'merge-base', 'update-ref', 'read-tree', 'diff', 'ls-files', 'check-ignore', 'ls-tree', 'bundle', 'cat-file', 'rev-list', 'show', 'diff-tree']);
// Retain only trusted acquisition categories, never a worker-selected path or
// the filesystem error message. Inner snapshot writes take precedence over an
// enclosing source traversal when both share the same failure boundary.
const acquisitionContexts = new WeakMap();
const acquisitionFacts = new WeakMap();
async function acquire(context, action, facts) {
  try { return await action(); }
  catch (error) {
    if (error && typeof error === 'object' && !acquisitionContexts.has(error)) acquisitionContexts.set(error, context);
    if (error && typeof error === 'object' && facts && !acquisitionFacts.has(error)
      && acquisitionContexts.get(error) === context) acquisitionFacts.set(error, facts);
    throw error;
  }
}
export const secretFree = text => { if (SECRET.test(text)) fail('SECRET_PUBLICATION_SCAN_FAILED'); return text; };

function gitOperation(args) {
  return args.find(value => GIT_OPERATION_NAMES.has(value)) ?? 'git-command';
}

export function classifyGitFailure(error) {
  const text = String(error?.stderr ?? error?.message ?? '').toLowerCase();
  const code = error?.code;
  if (code === 'ETIMEDOUT' || error?.timedOut === true || error?.signal === 'SIGTERM' && error?.killed === true) return 'GIT_TIMEOUT';
  if (['ENOENT', 'EACCES', 'EPERM', 'EROFS', 'EINVAL', 'ENOTDIR'].includes(code)) return 'GIT_LOCAL_FAILURE';
  if (/(authentication failed|permission denied|write access to .* not granted|could not read username|403 forbidden|not authorized|access denied)/.test(text)) return 'GIT_AUTHORIZATION_REJECTED';
  if (/(non-fast-forward|failed to push some refs|rejected|fetch first|remote rejected|cannot lock ref|would clobber|ref .*conflict)/.test(text)) return 'GIT_REF_CONFLICT';
  if (/(could not resolve host|network is unreachable|connection timed out|connection reset|connection refused|unable to access|curl|proxy|tls handshake|temporary failure in name resolution)/.test(text)) return 'GIT_TRANSPORT_FAILED';
  if (/(not a git repository|bad object|unknown option|invalid argument|no such file or directory|dubious ownership)/.test(text)) return 'GIT_LOCAL_FAILURE';
  return 'GIT_UNKNOWN_FAILURE';
}

function gitFailureDetails(error, args, token) {
  const raw = String(error?.stderr ?? error?.message ?? '');
  const preview = boundedDiagnosticText(raw, GIT_DIAGNOSTIC_BYTES, { githubToken: token ?? '' });
  const operation = gitOperation(args);
  let classification = classifyGitFailure(error);
  // These checkout observations cannot contact a remote. Their permission
  // errors describe collector filesystem access, not GitHub authorization.
  if (['diff', 'ls-files'].includes(operation) && classification === 'GIT_AUTHORIZATION_REJECTED') classification = 'GIT_LOCAL_FAILURE';
  return {
    code: 'TRUSTED_GIT_FAILED', classification, primaryCause: classification,
    operation, ...(Number.isInteger(error?.code) ? { gitExitCode: error.code } : {}),
    ...(typeof error?.signal === 'string' ? { signal: error.signal } : {}), preview: preview.text,
    bytes: preview.bytes, truncated: preview.truncated
  };
}

export function gitEnvironment(token) {
  return { PATH: process.env.PATH, SYSTEMROOT: process.env.SYSTEMROOT, LANG: 'C', LC_ALL: 'C',
    GIT_CONFIG_NOSYSTEM: '1', GIT_CONFIG_GLOBAL: process.platform === 'win32' ? 'NUL' : '/dev/null',
    GIT_TERMINAL_PROMPT: '0', GCM_INTERACTIVE: 'Never', GIT_NO_REPLACE_OBJECTS: '1',
    ...(token ? { GIT_CONFIG_COUNT: '1', GIT_CONFIG_KEY_0: 'http.https://github.com/.extraHeader',
      GIT_CONFIG_VALUE_0: `Authorization: Basic ${Buffer.from(`x-access-token:${token}`).toString('base64')}` } : {}) };
}
// Call ONLY against a repository constructed by trusted code. Never point this
// helper at the model checkout, even for a supposedly read-only Git command.
export async function git(cwd, args, { token, allowFailure = false, allowedExitCodes = [], rejectStderr = false, input } = {}) {
  try {
    // Fetch must be quiescent before checkout access is transferred or objects
    // are inspected. Detached maintenance can remove its lock during traversal.
    const execution = exec('git', ['-c', 'core.hooksPath=/dev/null', '-c', 'credential.helper=', '-c', 'fetch.fsckObjects=true',
      '-c', 'protocol.file.allow=always', '-c', 'maintenance.auto=false', '-c', 'gc.auto=0', ...args],
      { cwd, env: gitEnvironment(token), maxBuffer: 100 * 1024 * 1024, timeout: 120000, windowsHide: true });
    let inputFailure;
    if (input !== undefined) {
      execution.child.stdin.on('error', error => { inputFailure = error; });
      execution.child.stdin.end(input);
    }
    const result = await execution;
    if (inputFailure) throw inputFailure;
    // ls-files can exit zero while warning that a directory was unreadable.
    // Such an observation cannot prove either a clean or a fully dirty tree.
    if (rejectStderr && result.stderr.trim()) throw Object.assign(new Error('GIT_OBSERVATION_INCOMPLETE'), { code: 0, stderr: result.stderr });
    return result.stdout;
  } catch (error) {
    if (Number.isInteger(error.code) && (allowFailure || allowedExitCodes.includes(error.code))
      && !(rejectStderr && String(error.stderr ?? '').trim())) return null;
    const failure = new Error('TRUSTED_GIT_FAILED'); failure.code = 'TRUSTED_GIT_FAILED';
    failure.details = { failureDiagnostic: gitFailureDetails(error, args, token) };
    throw failure;
  }
}
export async function temporaryRepo(fn, { root = tmpdir(), remote = REMOTE, token } = {}) {
  const dir = await acquire('snapshot-write', () => mkdtemp(join(root, 'relay-git-')));
  try {
    await git(dir, ['init', '--bare', '.']);
    await git(dir, ['fetch', '--no-tags', remote, `refs/heads/${CONSUMER.baseBranch}:refs/remotes/main`], { token });
    return await fn(dir);
  } finally { await acquire('snapshot-write', () => rm(dir, { recursive: true, force: true, maxRetries: 3, retryDelay: 100 })); }
}
function sameObservedFile(a, b) {
  return a.dev === b.dev && a.ino === b.ino && a.mode === b.mode && a.size === b.size
    && a.nlink === b.nlink && a.mtimeMs === b.mtimeMs && a.ctimeMs === b.ctimeMs;
}
function observationChanged() { throw new Error('WORKTREE_CHANGED_DURING_OBSERVATION'); }
// Linux's descriptor paths pin the source parent while O_NOFOLLOW protects
// the final component. Keep '/.' here: lstat of the descriptor link itself
// would inspect procfs rather than the already-open directory.
const pinnedPath = (handle, name = '.') => `/proc/self/fd/${handle.fd}/${name}`;
async function pinDirectory(path, device, expected) {
  const before = expected ?? await lstat(path);
  if (!before.isDirectory() || before.isSymbolicLink()) fail('UNTRUSTED_GIT_DIRECTORY_INVALID');
  if (device !== undefined && before.dev !== device) fail('UNTRUSTED_GIT_DEVICE_INVALID');
  const handle = await open(path, constants.O_RDONLY | constants.O_DIRECTORY | constants.O_NOFOLLOW);
  try {
    const after = await handle.stat();
    // Absolute ancestors can legitimately gain unrelated sibling entries.
    // Acquisition binds the inode and access mode; source traversal separately
    // checks directory contents/timestamps around its bounded observation.
    const sameIdentity = before.dev === after.dev && before.ino === after.ino
      && before.mode === after.mode && before.uid === after.uid && before.gid === after.gid;
    if (!sameIdentity || expected && !sameObservedFile(before, after)) observationChanged();
    return handle;
  } catch (error) { await handle.close(); throw error; }
}
async function pinCheckout(checkout) {
  if (process.platform !== 'linux') fail('COLLECTION_PLATFORM_UNSUPPORTED');
  const parts = checkout.split('/').slice(1);
  if (!isAbsolute(checkout) || parts.some(part => !part || part === '.' || part === '..')) fail('UNTRUSTED_GIT_DIRECTORY_INVALID');
  let handle = await pinDirectory('/');
  try {
    for (const part of parts) {
      const next = await pinDirectory(pinnedPath(handle, part));
      await handle.close(); handle = next;
    }
    return handle;
  } catch (error) { await handle.close(); throw error; }
}
function checkRegular(stat, device, max = 100 * 1024 * 1024) {
  if (!stat.isFile() || stat.isSymbolicLink() || stat.nlink !== 1 || stat.size > max) fail('UNTRUSTED_GIT_FILE_INVALID');
  if (stat.dev !== device) fail('UNTRUSTED_GIT_DEVICE_INVALID');
}
async function copyObservedFile(source, destination, expected, device, max = 100 * 1024 * 1024) {
  checkRegular(expected, device, max);
  // O_NONBLOCK also prevents an intervening FIFO from hanging collection.
  const handle = await open(source, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  let output;
  try {
    const before = await handle.stat();
    checkRegular(before, device, max);
    if (!sameObservedFile(before, expected)) observationChanged();
    if (destination) output = await acquire('snapshot-write', () => open(destination, 'wx', before.mode & 0o100 ? 0o700 : 0o600));
    const buffer = Buffer.alloc(64 * 1024); let bytes = 0;
    while (true) {
      const { bytesRead } = await handle.read(buffer, 0, buffer.length, null);
      if (!bytesRead) break;
      bytes += bytesRead;
      if (bytes > before.size) observationChanged();
      if (output) await acquire('snapshot-write', () => output.writeFile(buffer.subarray(0, bytesRead)));
    }
    if (bytes !== before.size || !sameObservedFile(before, await handle.stat())
      || !sameObservedFile(before, await lstat(source))) observationChanged();
  } finally { if (output) await acquire('snapshot-write', () => output.close()); await handle.close(); }
}
async function boundedSourceText(parent, name, device) {
  const path = pinnedPath(parent, name); const expected = await lstat(path);
  checkRegular(expected, device, 1024);
  const handle = await open(path, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  try {
    const before = await handle.stat(); checkRegular(before, device, 1024);
    if (!sameObservedFile(before, expected)) observationChanged();
    const bytes = Buffer.alloc(1025); let size = 0;
    while (size <= 1024) {
      const next = await handle.read(bytes, size, bytes.length - size, null);
      if (!next.bytesRead) break;
      size += next.bytesRead;
    }
    if (size !== before.size || !sameObservedFile(before, await handle.stat())
      || !sameObservedFile(before, await lstat(path))) observationChanged();
    return bytes.subarray(0, size).toString('utf8').trim();
  } finally { await handle.close(); }
}
function sourceFailure(error, operation, observedHead) {
  if (error.code === 'TRUSTED_GIT_FAILED' || error.code && !/^E[A-Z0-9]+$/.test(error.code)) throw error;
  const failure = new Error('TRUSTED_GIT_FAILED'); failure.code = 'TRUSTED_GIT_FAILED';
  const safeReasons = new Set(['WORKTREE_CHANGED_DURING_OBSERVATION', 'WORKTREE_OBSERVATION_TOO_LARGE',
    'WORKTREE_OBSERVATION_TOO_DEEP', 'WORKTREE_PATH_ENCODING_INVALID']);
  const reason = /^E[A-Z0-9]+$/.test(error.code ?? '') ? error.code
    : safeReasons.has(error.message) ? error.message : 'SOURCE_OBSERVATION_FAILED';
  const context = acquisitionContexts.get(error) ?? 'object-acquisition';
  const syscall = typeof error.syscall === 'string' && /^[a-z][a-z0-9_]{0,39}$/.test(error.syscall) ? error.syscall : undefined;
  const identity = [['collector-euid', process.geteuid?.()], ['collector-egid', process.getegid?.()]]
    .filter(([, value]) => Number.isInteger(value) && value >= 0).map(([name, value]) => `${name}=${value}`);
  // Only numeric lstat facts and a path fingerprint cross this boundary. The
  // path and its bytes may be private. A head read/import is a diagnostic lead,
  // never a validated candidate, clean observation or publication authority.
  const facts = acquisitionFacts.get(error);
  const frontier = [exactSha(observedHead) ? `observed-head-unaccepted=${observedHead}` : '',
    facts ? `source-facts=${JSON.stringify(facts)}` : ''].filter(Boolean).join('; ');
  const preview = boundedDiagnosticText(`${reason}: ${context}; syscall=${syscall ?? 'unavailable'}; ${identity.join('; ')}; complete checkout observation unavailable${frontier ? '; ' + frontier : ''}`, GIT_DIAGNOSTIC_BYTES);
  failure.details = { failureDiagnostic: { code: failure.code, classification: 'GIT_LOCAL_FAILURE',
    primaryCause: 'GIT_LOCAL_FAILURE', operation, pathContext: context === 'snapshot-write' ? 'unknown' : 'checkout',
    ...(/^E[A-Z0-9]+$/.test(error.code ?? '') ? { diagnosticCode: error.code } : {}),
    ...(syscall ? { syscall } : {}), preview: preview.text,
    bytes: preview.bytes, truncated: preview.truncated } };
  throw failure;
}
async function observeWorktree(dir, checkout, head, device) {
  const snapshot = join(dir, 'observed-worktree'); await acquire('snapshot-write', () => mkdir(snapshot));
  const tracked = new Map(); const trackedDirectories = new Set();
  for (const row of (await git(dir, ['ls-tree', '-r', '-z', head])).split('\0').filter(Boolean)) {
    const tab = row.indexOf('\t'); const [mode, , object] = row.slice(0, tab).split(' ');
    const path = row.slice(tab + 1); tracked.set(path, { mode, object });
    const parts = path.split('/');
    for (let i = 1; i < parts.length; i++) trackedDirectories.add(parts.slice(0, i).join('/'));
  }
  const matchingSymlinks = new Set(); let specialResidue = false;
  let bytes = 0; let entriesObserved = 0;
  function sourceFacts(path, stat) {
    return { path_sha256: createHash('sha256').update(path).digest('hex'),
      uid: stat.uid, gid: stat.gid, mode: stat.mode & 0o7777, dev: stat.dev, ino: stat.ino,
      tracked: tracked.has(path) || trackedDirectories.has(path) };
  }
  async function copySource(source, destination, stat, relative) {
    bytes += stat.size;
    if (bytes > 100 * 1024 * 1024) throw new Error('WORKTREE_OBSERVATION_TOO_LARGE');
    await acquire('source-read', () => copyObservedFile(source, destination, stat, device), sourceFacts(relative, stat));
  }
  async function visit(handle, relative = '', destination = join(snapshot, relative), metadataOnly = false) {
    if (relative.split('/').length > 128) throw new Error('WORKTREE_OBSERVATION_TOO_DEEP');
    const source = pinnedPath(handle);
    const before = await handle.stat();
    const entries = [];
    for await (const entry of await opendir(source, { encoding: 'buffer' })) {
      const nameBytes = entry.name;
      const name = nameBytes.toString('utf8');
      if (!Buffer.from(name).equals(nameBytes)) throw new Error('WORKTREE_PATH_ENCODING_INVALID');
      if (!relative && name === '.git') continue;
      if (++entriesObserved > 50000) throw new Error('WORKTREE_OBSERVATION_TOO_LARGE');
      const path = relative ? `${relative}/${name}` : name;
      entries.push({ name, path, stat: await lstat(pinnedPath(handle, name)) });
    }
    // Git sees only copies of regular ignore files; it never opens a worker
    // path or follows a worker-owned .gitignore symlink to decide exclusion.
    const ignore = entries.find(entry => entry.name === '.gitignore' && entry.stat.isFile());
    if (ignore) await copySource(pinnedPath(handle, ignore.name), join(destination, ignore.name), ignore.stat, ignore.path);
    const candidates = entries.map(entry => entry.path + (entry.stat.isDirectory() ? '/' : ''));
    const ignored = new Set(entries.length && !metadataOnly ? (await git(dir,
      [`--work-tree=${snapshot}`, 'check-ignore', '--no-index', '--stdin', '-z'],
      { input: `${candidates.join('\0')}\0`, allowedExitCodes: [1], rejectStderr: true }) ?? '').split('\0') : []);
    for (const entry of entries) {
      const candidate = entry.path + (entry.stat.isDirectory() ? '/' : '');
      if (ignored.has(candidate) && !tracked.has(entry.path) && !trackedDirectories.has(entry.path)) continue;
      const from = pinnedPath(handle, entry.name); const to = join(destination, entry.name);
      if (entry.stat.isDirectory()) {
        // Nested Git metadata is observed as raw bytes outside the observation
        // worktree, so Git cannot discover or interpret it as another repo.
        const child = await acquire('source-directory', () => pinDirectory(from, device, entry.stat), sourceFacts(entry.path, entry.stat));
        try {
          if (entry.name === '.git' && !metadataOnly) {
            specialResidue = true;
            await visit(child, entry.path, await acquire('snapshot-write', () => mkdtemp(join(dir, 'observed-metadata-'))), true);
          } else {
            await acquire('snapshot-write', () => mkdir(to));
            await visit(child, entry.path, to, metadataOnly);
          }
          if (!sameObservedFile(entry.stat, await lstat(from))) observationChanged();
        } finally { await child.close(); }
      } else if (entry.stat.isFile()) {
        if (entry.name === '.git' && !metadataOnly) {
          specialResidue = true;
          const retained = await acquire('snapshot-write', () => mkdtemp(join(dir, 'observed-metadata-')));
          await copySource(from, join(retained, 'gitfile'), entry.stat, entry.path);
        } else if (entry !== ignore) await copySource(from, to, entry.stat, entry.path);
      } else if (entry.stat.isSymbolicLink()) {
        const target = await readlink(from, { encoding: 'buffer' });
        if (!sameObservedFile(entry.stat, await lstat(from))) observationChanged();
        const expected = tracked.get(entry.path);
        const object = createHash('sha1').update(`blob ${target.length}\0`).update(target).digest('hex');
        if (expected?.mode === '120000' && expected.object === object) matchingSymlinks.add(entry.path);
        else specialResidue = true;
      } else {
        // Device/FIFO/socket presence is known residue; never open it or copy
        // it into the trusted repository. Such modes cannot enter a commit.
        if (!sameObservedFile(entry.stat, await lstat(from))) observationChanged();
        specialResidue = true;
      }
    }
    if (!sameObservedFile(before, await handle.stat())) observationChanged();
  }
  try {
    await acquire('source-directory', () => visit(checkout));
  } catch (error) {
    sourceFailure(error, 'worktree-observation', head);
  }
  // The snapshot is owned/readable by this collector. Attribute normalization
  // is preserved, with no worker config, hook, filter command, or metadata.
  const diff = await git(dir, [`--work-tree=${snapshot}`, 'diff', '--no-ext-diff', '--no-textconv', '--raw', '-z', head], { rejectStderr: true });
  const rows = diff.split('\0'); let dirty = specialResidue;
  for (let i = 0; i < rows.length - 1; i += 2) if (!matchingSymlinks.has(rows[i + 1])) dirty = true;
  const untracked = await git(dir, [`--work-tree=${snapshot}`, 'ls-files', '--others', '--exclude-standard', '-z'], { rejectStderr: true });
  return !dirty && !untracked.split('\0').some(Boolean);
}
export async function collectProgress(checkout, e, options = {}) {
  // Import only regular object bytes and a bounded ref. Model config, index,
  // hooks, alternates, replace refs, grafts, filters and remotes never cross.
  let source; let metadata;
  try {
    source = await acquire('source-directory', () => pinCheckout(checkout));
    const device = (await source.stat()).dev;
    metadata = await pinDirectory(pinnedPath(source, '.git'), device);
    const metadataStat = await metadata.stat();
    async function observedHead() {
      let head = await boundedSourceText(metadata, 'HEAD', device);
      if (head.startsWith('ref: ')) {
        if (head !== `ref: refs/heads/${e.branch}`) fail('WORKING_BRANCH_CHANGED');
        const parts = ['refs', 'heads', ...branchName(e.branch).split('/')];
        let at = metadata;
        try {
          for (const part of parts.slice(0, -1)) {
            const next = await pinDirectory(pinnedPath(at, part), device);
            if (at !== metadata) await at.close();
            at = next;
          }
          head = await boundedSourceText(at, parts.at(-1), device);
        } finally { if (at !== metadata) await at.close(); }
      }
      if (!exactSha(head)) fail('WORKING_HEAD_INVALID');
      return head;
    }
    const head = await observedHead();
    return await temporaryRepo(async dir => {
      if (e.target === 'pull_request' || e.continuation) await git(dir, ['fetch', '--no-tags', options.remote ?? REMOTE, `refs/heads/${e.branch}:refs/remotes/task`], options);
      const objects = await pinDirectory(pinnedPath(metadata, 'objects'), device);
      try {
        const objectsStat = await objects.stat();
        let bytes = 0; let files = 0; let entries = 0;
        for await (const folderEntry of await opendir(pinnedPath(objects))) {
          if (++entries > 50000) fail('OBJECT_IMPORT_TOO_LARGE');
          const folder = folderEntry.name;
          if (!/^[a-f0-9]{2}$/.test(folder) && folder !== 'pack') continue;
          const folderPath = pinnedPath(objects, folder);
          const objectsFolder = await pinDirectory(folderPath, device);
          try {
            const folderStat = await objectsFolder.stat();
            await acquire('snapshot-write', () => mkdir(join(dir, 'objects', folder), { recursive: true }));
            for await (const entry of await opendir(pinnedPath(objectsFolder))) {
              if (++entries > 50000) fail('OBJECT_IMPORT_TOO_LARGE');
              const name = entry.name;
              if (!(folder === 'pack' ? /^pack-[a-f0-9]{40}\.(pack|idx)$/.test(name) : /^[a-f0-9]{38}$/.test(name))) continue;
              const objectPath = pinnedPath(objectsFolder, name); const stat = await lstat(objectPath);
              checkRegular(stat, device); bytes += stat.size;
              if (bytes > 100 * 1024 * 1024 || ++files > 50000) fail('OBJECT_IMPORT_TOO_LARGE');
              const destination = join(dir, 'objects', folder, name);
              let exists = false;
              try { await lstat(destination); exists = true; }
              catch (error) { if (error.code !== 'ENOENT') throw error; }
              // Read even duplicate source objects completely, but never
              // overwrite a verified object fetched into the trusted repo.
              await copyObservedFile(objectPath, exists ? null : destination, stat, device);
            }
            if (!sameObservedFile(folderStat, await objectsFolder.stat())
              || !sameObservedFile(folderStat, await lstat(folderPath))) observationChanged();
          } finally { await objectsFolder.close(); }
        }
        if (!sameObservedFile(objectsStat, await objects.stat())
          || !sameObservedFile(objectsStat, await lstat(pinnedPath(metadata, 'objects')))) observationChanged();
      } finally { await objects.close(); }
      await git(dir, ['cat-file', '-e', `${head}^{commit}`]);
      await git(dir, ['merge-base', '--is-ancestor', e.startHead, head]);
      await git(dir, ['update-ref', 'refs/heads/progress', head]);
      await git(dir, ['read-tree', head]);
      const clean = await observeWorktree(dir, source, head, device);
      if (await observedHead() !== head
        || !sameObservedFile(metadataStat, await metadata.stat())
        || !sameObservedFile(metadataStat, await lstat(pinnedPath(source, '.git')))) observationChanged();
      const bundle = join(dir, 'progress.bundle');
      if (head === e.startHead) return { head, bundle: null, clean };
      await git(dir, ['bundle', 'create', bundle, 'refs/heads/progress', `^${e.startHead}`]);
      return { head, bundle: (await readFile(bundle)).toString('base64'), clean };
    }, options);
  } catch (error) { sourceFailure(error, 'object-import'); }
  finally { await metadata?.close(); await source?.close(); }
}
export async function validateCommits(dir, e, head) {
  await git(dir, ['merge-base', '--is-ancestor', e.startHead, head]);
  // Only the task's first-parent chain is worker-owned. An exact admitted main
  // may enter once as a second parent; its already-published authors are not bots.
  const commits = (await git(dir, ['rev-list', '--first-parent', '--reverse', `${e.startHead}..${head}`])).trim().split(/\r?\n/).filter(Boolean);
  if (commits.length > 128) fail('COMMIT_RANGE_TOO_LARGE');
  let previous = e.startHead;
  let integrationBase = null;
  for (const commit of commits) {
    const [parents, author, committer, authorEmail, committerEmail] = (await git(dir, ['show', '-s', '--format=%P%n%an%n%cn%n%ae%n%ce', commit])).trimEnd().split('\n');
    const { name: identity, email } = e.target === 'pull_request' ? CONSUMER.remediationIdentity : CONSUMER.writerIdentity;
    const parentList = parents.trim().split(' ');
    if (parentList[0] !== previous || author.trim() !== identity || committer.trim() !== identity
      || authorEmail.trim() !== email || committerEmail.trim() !== email) fail('COMMIT_OWNERSHIP_INVALID');
    if (parentList.length !== 1) {
      if (e.target !== 'pull_request' || integrationBase || parentList.length !== 2
        || parentList[1] !== e.targetBase) fail('COMMIT_OWNERSHIP_INVALID');
      if ((await git(dir, ['rev-parse', 'refs/remotes/main'])).trim() !== e.targetBase) fail('STARTING_STATE_MISMATCH');
      const bases = await git(dir, ['merge-base', '--all', previous, e.targetBase], { allowFailure: true });
      if (!bases || bases.trim().split(/\s+/).length !== 1 || bases.trim() === e.targetBase) fail('INTEGRATION_BASE_INVALID');
      integrationBase = e.targetBase;
    }
    // An explicit first-parent diff also scans merge resolutions and introduced
    // main blobs. Default diff-tree output would silently skip a merge commit.
    const paths = (await git(dir, ['diff-tree', '--no-commit-id', '--name-only', '-r', '-z', previous, commit])).split('\0').filter(Boolean);
    if (paths.some(path => !safePath(path))) fail('COMMIT_PATH_INVALID');
    secretFree(await git(dir, ['cat-file', 'commit', commit]));
    // Check every introduced blob, including transient secrets later deleted.
    const rows = (await git(dir, ['diff-tree', '--no-commit-id', '--raw', '-r', '--no-renames', '-z', previous, commit])).split('\0');
    for (let i = 0; i < rows.length - 1; i += 2) {
      const fields = rows[i].split(' '); const mode = fields[1]; const object = fields[3];
      if (mode === '000000') continue;
      if (!['100644', '100755'].includes(mode)) fail('COMMIT_FILE_MODE_INVALID');
      secretFree(await git(dir, ['cat-file', 'blob', object]));
    }
    previous = commit;
  }
  return { commits, integrationBase };
}
export function createGitPublisher({ remote = REMOTE, token, root = tmpdir() } = {}) {
  return {
    async inspect(e, encoded, fn) {
      if (typeof encoded !== 'string' || encoded.length > 140 * 1024 * 1024 || !/^[A-Za-z0-9+/]+={0,2}$/.test(encoded)) fail('BUNDLE_INVALID');
      return temporaryRepo(async dir => {
        const remoteOutput = await git(dir, ['ls-remote', remote, `refs/heads/${e.branch}`], { token });
        const remoteHead = remoteOutput.trim().split(/\s+/)[0] || null;
        if (remoteHead) await git(dir, ['fetch', '--no-tags', remote, `refs/heads/${e.branch}:refs/remotes/task`], { token });
        const bundle = join(dir, 'input.bundle'); await writeFile(bundle, Buffer.from(encoded, 'base64'));
        await git(dir, ['bundle', 'verify', bundle]);
        const refs = (await git(dir, ['bundle', 'list-heads', bundle])).trim().split(/\r?\n/);
        if (refs.length !== 1 || !/^[a-f0-9]{40} refs\/heads\/progress$/.test(refs[0])) fail('BUNDLE_REF_INVALID');
        await git(dir, ['fetch', '--no-tags', bundle, 'refs/heads/progress:refs/heads/progress']);
        const head = (await git(dir, ['rev-parse', 'refs/heads/progress'])).trim();
        const { commits, integrationBase } = await validateCommits(dir, e, head);
        const ancestor = async (a, b) => await git(dir, ['merge-base', '--is-ancestor', a, b], { allowFailure: true }) !== null;
        const observe = async () => (await git(dir, ['ls-remote', remote, `refs/heads/${e.branch}`], { token })).trim().split(/\s+/)[0] || null;
        return fn({ head, remoteHead, commits, integrationBase, ancestor, observe,
          push: () => git(dir, ['push', remote, `refs/heads/progress:refs/heads/${e.branch}`], { token }) });
      }, { root, remote, token });
    }
  };
}
