// Root-only bootstrap: authenticate an old consumer before importing its runtime.
// A drifted live file is overlaid only in a private, read-only mount namespace.
import { constants } from 'node:fs';
import { lstat, open, realpath, readlink, mkdtemp } from 'node:fs/promises';
import { basename, dirname, isAbsolute, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { spawn } from 'node:child_process';
import { consumerDigest, configuredRepositories, parseConsumerJson, validateConsumer } from '../../consumer/consumer-config.mjs';
import { recordEntrypointFailure } from './repository-entrypoint.mjs';
import { createBoundedUtf8Capture } from './utf8-capture.mjs';

const sourceRoot = fileURLToPath(new URL('../..', import.meta.url));
const sha = value => createHash('sha256').update(value).digest('hex');
const digest = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const revision = value => typeof value === 'string' && /^[a-f0-9]{40}$/.test(value);
const fail = (code, cause, observation) => { throw Object.assign(new Error(code, { cause }), { code, ...(observation ? { observation } : {}) }); };
const require = (value, code, observation) => { if (!value) fail(code, undefined, observation); };
const stamp = info => ['dev', 'ino', 'mode', 'uid', 'gid', 'nlink', 'size', 'mtimeMs', 'ctimeMs']
  .map(key => info[key]).join(':');

async function protectedPath(path, directory = false) {
  require(isAbsolute(path) && normalize(path) === path, 'CONSUMER_PREFLIGHT_PATH_UNSAFE');
  for (let at = path; ; at = dirname(at)) {
    const info = await lstat(at);
    require(info.uid === 0 && !(info.mode & 0o022) && !info.isSymbolicLink()
      && (at === path && !directory ? info.isFile() && info.nlink === 1 : info.isDirectory()),
    'CONSUMER_PREFLIGHT_PATH_UNSAFE', { check: 'protected-path-entry', expected: { uid: 0, writableByOthers: false, type: at === path && !directory ? 'single-link-file' : 'directory' },
      observed: { path: at, uid: info.uid, mode: info.mode & 0o777, links: info.nlink, symlink: info.isSymbolicLink(), directory: info.isDirectory() } });
    if (at === '/') return lstat(path);
  }
}

async function readProtected(path, { privateFile = false, limit = 1024 * 1024 } = {}) {
  const before = await protectedPath(path);
  require(before.size <= limit && (!privateFile || (before.mode & 0o777) === 0o600),
    'CONSUMER_PREFLIGHT_FILE_UNSAFE', { check: 'protected-file-size-mode', expected: { limit, privateFile }, observed: { bytes: before.size, mode: before.mode & 0o777 } });
  const file = await open(path, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  try {
    const opened = await file.stat();
    require(stamp(opened) === stamp(before), 'CONSUMER_PREFLIGHT_INPUT_CHANGED', { check: 'protected-open-stability', expected: stamp(before), observed: stamp(opened) });
    const bytes = await file.readFile();
    require(bytes.length === before.size && stamp(await file.stat()) === stamp(before)
      && stamp(await lstat(path)) === stamp(before), 'CONSUMER_PREFLIGHT_INPUT_CHANGED');
    return bytes;
  } finally { await file.close(); }
}

async function exists(path) {
  try { await lstat(path); return true; } catch (error) { if (error.code === 'ENOENT') return false; throw error; }
}

async function installedIdentity(installRoot) {
  await protectedPath(installRoot, true);
  const current = join(installRoot, 'current'), before = await lstat(current);
  require(before.isSymbolicLink() && before.uid === 0, 'CONSUMER_PREFLIGHT_INSTALLED_IDENTITY_UNPROVEN');
  const release = await realpath(current);
  require(dirname(release) === join(installRoot, 'releases') && revision(basename(release)),
    'CONSUMER_PREFLIGHT_INSTALLED_IDENTITY_UNPROVEN', { check: 'installed-release-path', expected: join(installRoot, 'releases', '<revision>'), observed: release });
  const manifestPath = join(release, 'artifact-manifest.json'), identityPath = join(release, 'reviewed-source/.relay-source.json');
  const manifestBytes = await readProtected(manifestPath), identityBytes = await readProtected(identityPath);
  const manifest = parseConsumerJson(manifestBytes.toString()), identity = parseConsumerJson(identityBytes.toString());
  require(manifest && identity && ['commit', 'installedRevision', 'resolvedRevision'].every(key => manifest[key] === basename(release))
    && identity.revision === basename(release)
    && (manifest.gitTree === undefined && identity.tree === undefined
      || revision(manifest.gitTree) && manifest.gitTree === identity.tree),
  'CONSUMER_PREFLIGHT_INSTALLED_IDENTITY_UNPROVEN', { check: 'installed-manifest-identity', expected: basename(release),
    observed: { commit: manifest?.commit, installedRevision: manifest?.installedRevision, resolvedRevision: manifest?.resolvedRevision, revision: identity?.revision, gitTree: manifest?.gitTree, sourceTree: identity?.tree } });
  return { release, current, currentStamp: stamp(before), manifest, manifestPath, manifestBytes, identityPath, identityBytes };
}

async function gateFor(consumer, config) {
  const receipt = join(dirname(config), 'serial-pool-compat-v1.json');
  const hasReceipt = await exists(receipt);
  if (hasReceipt) await readProtected(receipt);
  const path = join(consumer.paths.claimRoot, hasReceipt ? 'admission-pool-v1.json' : 'admission-v1.json');
  let bytes, gate;
  try { bytes = await readProtected(path, { privateFile: true, limit: 4096 }); gate = parseConsumerJson(bytes.toString()); }
  catch (cause) { fail('CONSUMER_PREFLIGHT_GATE_UNPROVEN', cause); }
  const fields = ['version', 'consumerDigest', 'phase', 'operationId', 'target', 'previousActive', 'verifiedRevision'];
  require(gate && Object.keys(gate).length === fields.length && fields.every(key => Object.hasOwn(gate, key))
    && gate.version === 1 && digest(gate.consumerDigest)
    && ['open', 'quiesced', 'drained', 'applying', 'verified', 'recovery-required'].includes(gate.phase)
    && (gate.phase === 'open' ? gate.operationId === null && gate.target === null && gate.previousActive === null
      : typeof gate.operationId === 'string' && /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(gate.operationId) && revision(gate.target))
    && (gate.phase === 'verified' ? gate.verifiedRevision === gate.target : gate.verifiedRevision === null),
  'CONSUMER_PREFLIGHT_GATE_UNPROVEN', { check: 'retained-gate-schema', expected: fields,
    observed: gate && { keys: Object.keys(gate), version: gate.version, phase: gate.phase, operationId: gate.operationId, target: gate.target, verifiedRevision: gate.verifiedRevision } });
  return { path, bytes, gate, lockPath: join(consumer.paths.claimRoot, 'publication-v2.lock') };
}

export function runConsumerPreflightProgram(command, args, { input = '', environment, timeout = 180000, limit = 1024 * 1024, spawnImpl = spawn } = {}) {
  return new Promise((resolve, reject) => {
    let child;
    try { child = spawnImpl(command, args, { env: environment, stdio: ['pipe', 'pipe', 'pipe'], detached: true }); }
    catch (cause) { return reject(Object.assign(new Error('CONSUMER_PREFLIGHT_EXECUTION_UNAVAILABLE', { cause }), { code: 'CONSUMER_PREFLIGHT_EXECUTION_UNAVAILABLE', native: { operation: 'consumer-preflight-spawn', command } })); }
    const output = createBoundedUtf8Capture(limit), errors = createBoundedUtf8Capture(4096);
    let timedOut = false, oversized = false, settled = false, killFailure;
    const native = (code, signal) => ({ operation: 'consumer-preflight-program', command,
      stdout: output.finish(), stderr: errors.finish(), exitCode: code, signal,
      timedOut, oversized, limit, ...(killFailure ? { killFailure: { name: killFailure.name, code: killFailure.code, message: killFailure.message } } : {}) });
    const terminate = () => { try { process.kill(-child.pid, 'SIGKILL'); } catch (error) { if (error.code !== 'ESRCH') killFailure = error; } };
    const interrupted = () => terminate();
    for (const signal of ['SIGTERM', 'SIGINT']) process.once(signal, interrupted);
    const unwatch = () => { for (const signal of ['SIGTERM', 'SIGINT']) process.removeListener(signal, interrupted); };
    const timer = setTimeout(() => { timedOut = true; terminate(); }, timeout);
    let size = 0;
    child.stdout.on('data', bytes => { output.push(bytes); size += bytes.length; if (size > limit) { oversized = true; terminate(); } });
    child.stderr.on('data', bytes => errors.push(bytes));
    const rejectOriginal = cause => { if (settled) return; settled = true; clearTimeout(timer); unwatch();
      reject(Object.assign(new Error('CONSUMER_PREFLIGHT_EXECUTION_UNAVAILABLE', { cause }), { code: 'CONSUMER_PREFLIGHT_EXECUTION_UNAVAILABLE', native: native() })); };
    child.on('error', rejectOriginal);
    for (const stream of [child.stdin, child.stdout, child.stderr]) stream.on('error', rejectOriginal);
    child.on('close', (code, signal) => {
      clearTimeout(timer);
      unwatch();
      if (settled) return; settled = true;
      if (timedOut || oversized) return reject(Object.assign(new Error('CONSUMER_PREFLIGHT_OBSERVATION_LIMIT'), { code: 'CONSUMER_PREFLIGHT_OBSERVATION_LIMIT', native: native(code, signal) }));
      if (code !== 0) {
        const observed = errors.finish(), raw = observed.value;
        let receipt; try { if (!observed.truncated) receipt = JSON.parse(raw); } catch { /* native bytes remain protected below */ }
        const category = /^[A-Z][A-Z0-9_]{0,79}$/.test(receipt?.code ?? '') ? receipt.code : 'CONSUMER_PREFLIGHT_OBSERVATION_FAILED';
        return reject(Object.assign(new Error(category), { code: category, native: native(code, signal) }));
      }
      resolve(Buffer.from(output.finish().value));
    });
    child.stdin.end(input);
  });
}
const run = runConsumerPreflightProgram;

async function projectedBaseline(snapshot, installedSource, environment) {
  for (const name of ['deploy/config.py', 'deploy/managed_pool_transport.py', 'deploy/managed_pool.py',
    'deploy/ansible_transport.py', 'deploy/ansible/ansible.cfg', 'deploy/ansible/roles/relay_controller/templates/consumer.json.j2'])
    await protectedPath(join(installedSource, name));
  const program = 'import json,sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);'
    + 'from config import loads;from managed_pool_transport import projected_consumer;'
    + 'source=Path(sys.argv[1]).parent;snapshot=loads(sys.stdin.read(),source);'
    + 'print(json.dumps(projected_consumer(snapshot,source)))';
  const bytes = await run('/usr/bin/python3', ['-I', '-c', program, join(installedSource, 'deploy')], {
    input: JSON.stringify(snapshot), environment, timeout: 90000, limit: 128 * 1024 });
  return validateConsumer(parseConsumerJson(bytes.toString()));
}

// Paths and hashes below are supplied only by this root bootstrap after protected
// reads. There is no public execute mode, consumer-loader override or new admission.
const OBSERVE = String.raw`import fcntl,hashlib,json,os,stat,subprocess,sys,time,tempfile,traceback
def fail(code,evidence=None):
 value={'code':code}
 if evidence is not None:value['native']=evidence
 print(json.dumps(value,separators=(',',':')),file=sys.stderr);sys.exit(40)
try:
 p=json.load(sys.stdin)
 if os.geteuid()!=0:fail('CONSUMER_PREFLIGHT_ROOT_REQUIRED')
 if p['clone']:
  if os.readlink('/proc/self/ns/mnt')==p['parentNamespace']:fail('CONSUMER_PREFLIGHT_PRIVATE_NAMESPACE_UNAVAILABLE')
  for command in [ ['/usr/bin/mount','--bind',p['clone'],p['config']],
                   ['/usr/bin/mount','-o','remount,bind,ro',p['config']] ]:
   with tempfile.TemporaryFile() as errors:
    result=subprocess.run(command,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=errors)
    if result.returncode:
     errors.seek(0);data=errors.read(2049)
     fail('CONSUMER_PREFLIGHT_PRIVATE_VIEW_UNAVAILABLE',{'operation':'private-view-mount','exitCode':result.returncode,'stderr':data[:2048].decode('utf8','replace'),'truncated':len(data)>2048})
  a,b=os.stat(p['clone']),os.stat(p['config'])
  if (a.st_dev,a.st_ino)!=(b.st_dev,b.st_ino) or hashlib.sha256(open(p['config'],'rb').read()).hexdigest()!=p['cloneSha256']:fail('CONSUMER_PREFLIGHT_PRIVATE_VIEW_UNPROVEN')
 if p['lease']:
  module={'__name__':'relay_preflight_writer_lease','__file__':p['leaseModule']}
  exec(compile(open(p['leaseModule'],'rb').read(),p['leaseModule'],'exec'),module)
  module['verify'](p['lease'],p['lockPath'],operation=p['operationId'],target=p['target'],consumer_digest=p['baselineDigest'])
 else:
  fd=os.open(p['lockPath'],os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK)
  info=os.fstat(fd)
  if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022 or info.st_nlink!=1 or (info.st_dev,info.st_ino)!=(p['lockDev'],p['lockIno']):fail('CONSUMER_PREFLIGHT_WRITER_LOCK_UNPROVEN')
  deadline=time.monotonic()+60
  while True:
   try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);break
   except BlockingIOError:
    if time.monotonic()>=deadline:fail('CONSUMER_PREFLIGHT_WRITER_BUSY')
    time.sleep(.05)
  if (os.stat(p['lockPath']).st_dev,os.stat(p['lockPath']).st_ino)!=(info.st_dev,info.st_ino):fail('CONSUMER_PREFLIGHT_WRITER_LOCK_UNPROVEN')
  os.set_inheritable(fd,True)
 os.execve(p['node'],[p['node'],p['cli'],'consumer-transition-preflight','--desired-digest',p['desiredDigest']],os.environ)
except Exception as error:fail('CONSUMER_PREFLIGHT_OBSERVATION_FAILED',{'name':type(error).__name__,'message':str(error)[:512],'stack':traceback.format_exc()[-2048:],'errno':getattr(error,'errno',None)})
`;

export async function consumerPreflight({ config, installRoot, stageRoot, desiredDigest, repository, writerLockLease,
  recordFailure = recordEntrypointFailure }) {
  require(process.getuid?.() === 0, 'CONSUMER_PREFLIGHT_ROOT_REQUIRED');
  require(digest(desiredDigest), 'ADMISSION_CONFIG_INVALID');
  const namespace = basename(installRoot);
  require(/^[a-z][a-z0-9-]{0,30}$/.test(namespace) && basename(dirname(installRoot)) === 'opt'
    && config === join(dirname(dirname(installRoot)), 'etc', namespace, 'consumer.json'), 'CONSUMER_PREFLIGHT_NAMESPACE_INVALID');
  await protectedPath(stageRoot, true);
  await protectedPath(join(sourceRoot, 'controller/src/admission-cli.mjs'));
  const identity = await installedIdentity(installRoot), actualBytes = await readProtected(config, { limit: 128 * 1024 });
  let baseline, observed, actualDriftCategory = 'none';
  try { baseline = validateConsumer(parseConsumerJson(actualBytes.toString())); }
  catch (error) { actualDriftCategory = 'invalid-consumer'; await recordFailure(error, 'consumer-preflight-original-consumer'); }
  if (baseline) {
    observed = await gateFor(baseline, config);
    if (consumerDigest(baseline) !== observed.gate.consumerDigest) actualDriftCategory = 'digest-mismatch';
  }
  let snapshotPath, snapshotBytes;
  if (actualDriftCategory !== 'none') {
    snapshotPath = join(identity.release, 'deployment-config.json');
    try { snapshotBytes = await readProtected(snapshotPath, { privateFile: true }); }
    catch (cause) { fail('CONSUMER_PREFLIGHT_BASELINE_SNAPSHOT_UNPROVEN', cause); }
    require(sha(snapshotBytes) === identity.manifest.deploymentConfigSha256, 'CONSUMER_PREFLIGHT_BASELINE_SNAPSHOT_UNPROVEN');
    const snapshot = parseConsumerJson(snapshotBytes.toString());
    require(snapshot?.environment?.namespace === namespace, 'CONSUMER_PREFLIGHT_BASELINE_NAMESPACE_CHANGED');
    baseline = validateConsumer(snapshot.consumer); observed = await gateFor(baseline, config);
    if (consumerDigest(baseline) !== observed.gate.consumerDigest) {
      try {
        baseline = await projectedBaseline(snapshot, join(identity.release, 'reviewed-source'), {
          PATH: '/usr/local/bin:/usr/bin:/bin', LANG: 'C.UTF-8', LC_ALL: 'C.UTF-8', HOME: '/root', PYTHONDONTWRITEBYTECODE: '1' });
      } catch (cause) { fail('CONSUMER_PREFLIGHT_BASELINE_PROJECTION_UNAVAILABLE', cause); }
      observed = await gateFor(baseline, config);
    }
    require(consumerDigest(baseline) === observed.gate.consumerDigest, 'CONSUMER_PREFLIGHT_BASELINE_GATE_MISMATCH');
  }
  const baselineDigest = consumerDigest(baseline);
  repository ??= baseline.repository;
  require(configuredRepositories(baseline).includes(repository), 'CONSUMER_PREFLIGHT_REPOSITORY_REQUIRED');
  const lock = await protectedPath(observed.lockPath);
  let clone = null, cloneBytes;
  if (actualDriftCategory !== 'none') {
    const directory = await mkdtemp(join(stageRoot, 'consumer-context-'));
    clone = join(directory, 'consumer.json'); cloneBytes = Buffer.from(JSON.stringify(baseline) + '\n');
    const file = await open(clone, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | constants.O_NOFOLLOW, 0o644);
    try { await file.chmod(0o644); await file.writeFile(cloneBytes); await file.sync(); } finally { await file.close(); }
  }
  const leaseModule = join(sourceRoot, 'deploy/writer_lock_lease.py');
  if (writerLockLease) {
    await protectedPath(leaseModule);
    const candidate = parseConsumerJson((await readProtected(join(sourceRoot, '.relay-source.json'))).toString());
    require(candidate.revision === observed.gate.target, 'CONSUMER_PREFLIGHT_LEASE_TARGET_CHANGED');
  }
  const payload = { clone, cloneSha256: cloneBytes ? sha(cloneBytes) : null, parentNamespace: await readlink('/proc/self/ns/mnt'),
    config, node: process.execPath, cli: join(sourceRoot, 'controller/src/admission-cli.mjs'), desiredDigest: desiredDigest,
    lockPath: observed.lockPath, lockDev: lock.dev, lockIno: lock.ino, baselineDigest,
    lease: writerLockLease ?? null, leaseModule, operationId: observed.gate.operationId, target: observed.gate.target };
  const command = clone ? '/usr/bin/unshare' : '/usr/bin/python3';
  const args = clone ? ['--mount', '--propagation', 'private', '--', '/usr/bin/python3', '-I', '-c', OBSERVE] : ['-I', '-c', OBSERVE];
  const resultBytes = await run(command, args, { input: JSON.stringify(payload), environment: {
    PATH: '/usr/bin:/bin', LANG: 'C', LC_ALL: 'C', PYTHONDONTWRITEBYTECODE: '1', RELAY_CONSUMER_CONFIG: config,
    RELAY_REPOSITORY: repository } });
  let result;
  try { result = parseConsumerJson(resultBytes.toString()); }
  catch (error) { error.native = { operation: 'consumer-preflight-receipt-parse', stdout: resultBytes.toString() }; throw error; }
  require(result.currentDigest === baselineDigest && result.desiredDigest === desiredDigest
    && result.phase === observed.gate.phase && result.operationId === observed.gate.operationId
    && result.target === observed.gate.target && typeof result.eligible === 'boolean'
    && ['active', 'unknown'].every(key => Array.isArray(result[key]) && result[key].length <= 10000
      && result[key].every(id => Number.isSafeInteger(id) && id > 0)), 'CONSUMER_PREFLIGHT_RECEIPT_UNPROVEN', {
        check: 'preflight-receipt-binding', expected: { currentDigest: baselineDigest, desiredDigest, phase: observed.gate.phase, operationId: observed.gate.operationId, target: observed.gate.target },
        observed: result });
  require((await readProtected(config)).equals(actualBytes) && (await readProtected(observed.path)).equals(observed.bytes)
    && stamp(await lstat(identity.current)) === identity.currentStamp
    && await realpath(identity.current) === identity.release
    && (await readProtected(identity.manifestPath)).equals(identity.manifestBytes)
    && (await readProtected(identity.identityPath)).equals(identity.identityBytes)
    && (!snapshotPath || (await readProtected(snapshotPath)).equals(snapshotBytes)), 'CONSUMER_PREFLIGHT_INPUT_CHANGED');
  return { ...result,
    consumerRestoreRequired: clone !== null, actualDriftCategory, baselineDigest,
    effectiveConsumerPath: clone ?? config, claimRoot: baseline.paths.claimRoot, lockPath: observed.lockPath };
}

export function parseConsumerPreflightArguments(args) {
  const names = { config: 'config', 'install-root': 'installRoot', 'stage-root': 'stageRoot',
    'desired-digest': 'desiredDigest', repository: 'repository', 'writer-lock-lease': 'writerLockLease' };
  const options = {};
  for (let index = 0; index < args.length;) {
    const field = args[index].startsWith('--') && names[args[index].slice(2)];
    require(field && index + 1 < args.length && !Object.hasOwn(options, field), 'CONSUMER_PREFLIGHT_ARGUMENTS_INVALID');
    options[field] = args[index + 1]; index += 2;
  }
  require(['config', 'installRoot', 'stageRoot', 'desiredDigest'].every(key => typeof options[key] === 'string'),
    'CONSUMER_PREFLIGHT_ARGUMENTS_INVALID');
  return options;
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  Promise.resolve().then(() => consumerPreflight(parseConsumerPreflightArguments(process.argv.slice(2)))).then(value => {
    process.stdout.write(JSON.stringify(value) + '\n');
  }).catch(async error => {
    await recordEntrypointFailure(error, 'consumer-preflight');
    const code = /^[A-Z][A-Z0-9_]{0,79}$/.test(error?.code ?? '') ? error.code : 'CONSUMER_PREFLIGHT_UNPROVEN';
    const next = code.startsWith('CONSUMER_PREFLIGHT_BASELINE')
      ? 'Keep the prior installation unchanged. Qualify its original protected consumer snapshot/projection against the retained gate through supported owner repair; do not edit attempts, Outcomes or gate digests.'
      : code.includes('PRIVATE_') ? 'Keep the prior installation unchanged. Use the qualified root private-mount capability on the existing execution host before repeating this read-only preflight.'
        : 'Keep the prior installation unchanged. Inspect the reported prerequisite or exact unresolved attempt and use its existing supported completion/recovery path; unavailable old-version remediation requires a separately qualified compatible update.';
    process.stderr.write(JSON.stringify({ code, next }) + '\n');
    process.exitCode = 1;
  });
}
