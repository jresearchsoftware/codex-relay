import { CONSUMER } from '../../consumer/consumer.mjs';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { mkdtemp, mkdir, readFile, writeFile, readdir, lstat, copyFile, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { REPOSITORY, exactSha, fail, safePath, branchName } from './execution-contract.mjs';
import { boundedDiagnosticText } from './diagnostics.mjs';

const exec = promisify(execFile);
export const REMOTE = `https://github.com/${REPOSITORY}.git`;
const SECRET = /github_pat_[A-Za-z0-9_]{30,}|gh[pousr]_[A-Za-z0-9_]{20,}|-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----/;
const GIT_DIAGNOSTIC_BYTES = 2048;
const GIT_OPERATION_NAMES = new Set(['init', 'fetch', 'push', 'ls-remote', 'rev-parse', 'merge-base', 'update-ref', 'read-tree', 'diff', 'ls-files', 'bundle', 'cat-file', 'rev-list', 'show', 'diff-tree']);
export const secretFree = text => { if (SECRET.test(text)) fail('SECRET_PUBLICATION_SCAN_FAILED'); return text; };

function gitOperation(args) {
  return args.find(value => GIT_OPERATION_NAMES.has(value)) ?? 'git-command';
}

export function classifyGitFailure(error) {
  const text = String(error?.stderr ?? error?.message ?? '').toLowerCase();
  const code = error?.code;
  if (code === 'ETIMEDOUT' || error?.timedOut === true || error?.signal === 'SIGTERM' && error?.killed === true) return 'GIT_TIMEOUT';
  if (['ENOENT', 'EACCES', 'EPERM', 'EINVAL', 'ENOTDIR'].includes(code)) return 'GIT_LOCAL_FAILURE';
  if (/(authentication failed|permission denied|write access to .* not granted|could not read username|403 forbidden|not authorized|access denied)/.test(text)) return 'GIT_AUTHORIZATION_REJECTED';
  if (/(non-fast-forward|failed to push some refs|rejected|fetch first|remote rejected|cannot lock ref|would clobber|ref .*conflict)/.test(text)) return 'GIT_REF_CONFLICT';
  if (/(could not resolve host|network is unreachable|connection timed out|connection reset|connection refused|unable to access|curl|proxy|tls handshake|temporary failure in name resolution)/.test(text)) return 'GIT_TRANSPORT_FAILED';
  if (/(not a git repository|bad object|unknown option|invalid argument|no such file or directory|dubious ownership)/.test(text)) return 'GIT_LOCAL_FAILURE';
  return 'GIT_UNKNOWN_FAILURE';
}

function gitFailureDetails(error, args, token) {
  const raw = String(error?.stderr ?? error?.message ?? '');
  const preview = boundedDiagnosticText(raw, GIT_DIAGNOSTIC_BYTES, { githubToken: token ?? '' });
  return {
    code: 'TRUSTED_GIT_FAILED', classification: classifyGitFailure(error), primaryCause: classifyGitFailure(error),
    operation: gitOperation(args), ...(Number.isInteger(error?.code) ? { gitExitCode: error.code } : {}),
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
export async function git(cwd, args, { token, allowFailure = false } = {}) {
  try {
    // Fetch must be quiescent before checkout access is transferred or objects
    // are inspected. Detached maintenance can remove its lock during traversal.
    return (await exec('git', ['-c', 'core.hooksPath=/dev/null', '-c', 'credential.helper=', '-c', 'fetch.fsckObjects=true',
      '-c', 'protocol.file.allow=always', '-c', 'maintenance.auto=false', '-c', 'gc.auto=0', ...args],
      { cwd, env: gitEnvironment(token), maxBuffer: 100 * 1024 * 1024, timeout: 120000, windowsHide: true })).stdout;
  } catch (error) {
    if (allowFailure && Number.isInteger(error.code)) return null;
    const failure = new Error('TRUSTED_GIT_FAILED'); failure.code = 'TRUSTED_GIT_FAILED';
    failure.details = { failureDiagnostic: gitFailureDetails(error, args, token) };
    throw failure;
  }
}
export async function temporaryRepo(fn, { root = tmpdir(), remote = REMOTE, token } = {}) {
  const dir = await mkdtemp(join(root, 'relay-git-'));
  try {
    await git(dir, ['init', '--bare', '.']);
    await git(dir, ['fetch', '--no-tags', remote, `refs/heads/${CONSUMER.baseBranch}:refs/remotes/main`], { token });
    return await fn(dir);
  } finally { await rm(dir, { recursive: true, force: true, maxRetries: 3, retryDelay: 100 }); }
}
async function regular(path, max = 100 * 1024 * 1024) {
  const s = await lstat(path);
  if (!s.isFile() || s.isSymbolicLink() || s.nlink !== 1 || s.size > max) fail('UNTRUSTED_GIT_FILE_INVALID');
  return s;
}
async function directory(path) {
  const s = await lstat(path);
  if (!s.isDirectory() || s.isSymbolicLink()) fail('UNTRUSTED_GIT_DIRECTORY_INVALID');
}
export async function collectProgress(checkout, e, options = {}) {
  // Import only regular object bytes and a bounded ref. Model config, index,
  // hooks, alternates, replace refs, grafts, filters and remotes never cross.
  const metadata = join(checkout, '.git');
  await directory(checkout); await directory(metadata);
  const headFile = join(metadata, 'HEAD'); await regular(headFile, 1024);
  let head = (await readFile(headFile, 'utf8')).trim();
  if (head.startsWith('ref: ')) {
    if (head !== `ref: refs/heads/${e.branch}`) fail('WORKING_BRANCH_CHANGED');
    const parts = ['refs', 'heads', ...branchName(e.branch).split('/')];
    let at = metadata;
    for (const part of parts.slice(0, -1)) { at = join(at, part); await directory(at); }
    const ref = join(at, parts.at(-1)); await regular(ref, 1024);
    head = (await readFile(ref, 'utf8')).trim();
  }
  if (!exactSha(head)) fail('WORKING_HEAD_INVALID');
  return temporaryRepo(async dir => {
    if (e.target === 'pull_request') await git(dir, ['fetch', '--no-tags', options.remote ?? REMOTE, `refs/heads/${e.branch}:refs/remotes/task`], options);
    const objects = join(metadata, 'objects'); await directory(objects);
    let bytes = 0; let files = 0;
    for (const folder of await readdir(objects)) {
      if (!/^[a-f0-9]{2}$/.test(folder) && folder !== 'pack') continue;
      await directory(join(objects, folder));
      await mkdir(join(dir, 'objects', folder), { recursive: true });
      for (const name of await readdir(join(objects, folder))) {
        if (!(folder === 'pack' ? /^pack-[a-f0-9]{40}\.(pack|idx)$/.test(name) : /^[a-f0-9]{38}$/.test(name))) continue;
        const source = join(objects, folder, name); bytes += (await regular(source)).size;
        if (bytes > 100 * 1024 * 1024 || ++files > 50000) fail('OBJECT_IMPORT_TOO_LARGE');
        const destination = join(dir, 'objects', folder, name);
        // Preserve verified remote objects; never overwrite a trusted object.
        if (!(await lstat(destination).catch(() => null))) await copyFile(source, destination);
      }
    }
    await git(dir, ['cat-file', '-e', `${head}^{commit}`]);
    await git(dir, ['merge-base', '--is-ancestor', e.startHead, head]);
    await git(dir, ['update-ref', 'refs/heads/progress', head]);
    await git(dir, ['read-tree', head]);
    const dirty = await git(dir, [`--work-tree=${checkout}`, 'diff', '--no-ext-diff', '--no-textconv', '--exit-code', head], { allowFailure: true });
    const untracked = await git(dir, [`--work-tree=${checkout}`, 'ls-files', '--others', '--exclude-standard', '-z']);
    const clean = dirty !== null && !untracked.split('\0').some(p => p && !p.startsWith('.git/'));
    const bundle = join(dir, 'progress.bundle');
    if (head === e.startHead) return { head, bundle: null, clean };
    await git(dir, ['bundle', 'create', bundle, 'refs/heads/progress', `^${e.startHead}`]);
    return { head, bundle: (await readFile(bundle)).toString('base64'), clean };
  }, options);
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
