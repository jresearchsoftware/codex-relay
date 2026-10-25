import { constants } from 'node:fs';
import { lstat, open, readdir, readlink } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { basename, dirname, isAbsolute, join, posix, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createAttemptStore } from './attempt-store.mjs';
import { configuredRepositories, consumerDigest, parseConsumerJson, resolveExecutionConsumer, selectRepositoryConsumer, validateConsumer } from '../../consumer/consumer-config.mjs';

const execute = promisify(execFile);
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const envelopeHash = value => hash(JSON.stringify(value));
const sha = value => /^[a-f0-9]{64}$/.test(value ?? '');
const revision = value => /^[a-f0-9]{40}$/.test(value ?? '');
const positive = value => Number.isSafeInteger(value) && value > 0;
const exactKeys = (value, keys) => value && typeof value === 'object' && !Array.isArray(value)
  && Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
const fail = code => { throw Object.assign(new Error(code), { code }); };
const require = (condition, code) => { if (!condition) fail(code); };
const settings = new WeakMap();
const MAX_RECEIPT = 2 * 1024 * 1024;
const historicalOperations = new Set(['publication-state', 'recover-publication', 'complete-handoff',
  'prepublication-state', 'recover-prepublication', 'finish', 'finish-no-change', 'manual-outcome',
  'manual-outcome-direct', 'terminal-outcome', 'observe-readiness', 'complete-execution', 'validate-envelope', 'inventory']);

function physical(root, pathname) {
  require(typeof pathname === 'string' && posix.isAbsolute(pathname) && posix.normalize(pathname) === pathname,
    'SERIAL_POOL_COMPATIBILITY_PATH_INVALID');
  return root === '/' ? pathname : join(root, pathname.slice(1));
}
function stamp(value) {
  return ['dev', 'ino', 'mode', 'uid', 'gid', 'nlink', 'size', 'mtimeMs', 'ctimeMs'].map(key => value[key]).join(':');
}
async function parents(pathname, { root, ownerUid }) {
  require(isAbsolute(pathname) && (pathname === root || pathname.startsWith(root === '/' ? '/' : root + '/')),
    'SERIAL_POOL_COMPATIBILITY_PATH_INVALID');
  for (let current = dirname(pathname); ; current = dirname(current)) {
    const info = await lstat(current);
    require(info.isDirectory() && !info.isSymbolicLink() && info.uid === ownerUid && !(info.mode & 0o022),
      'SERIAL_POOL_COMPATIBILITY_PARENT_UNSAFE');
    if (current === root) break;
    require(dirname(current) !== current, 'SERIAL_POOL_COMPATIBILITY_PATH_INVALID');
  }
}
async function protectedRead(pathname, options, modes, limit = MAX_RECEIPT) {
  await parents(pathname, options);
  const file = await open(pathname, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  try {
    const before = await file.stat();
    require(before.isFile() && before.nlink === 1 && before.uid === options.ownerUid
      && modes.includes(before.mode & 0o777) && before.size >= 0 && before.size <= limit,
    'SERIAL_POOL_COMPATIBILITY_FILE_UNSAFE');
    const bytes = await file.readFile();
    require(bytes.length === before.size && stamp(before) === stamp(await file.stat()),
      'SERIAL_POOL_COMPATIBILITY_FILE_CHANGED');
    await parents(pathname, options);
    require(stamp(before) === stamp(await lstat(pathname)), 'SERIAL_POOL_COMPATIBILITY_FILE_CHANGED');
    return bytes;
  } finally { await file.close(); }
}
function json(bytes) {
  try { return parseConsumerJson(bytes.toString('utf8')); }
  catch { fail('SERIAL_POOL_COMPATIBILITY_JSON_INVALID'); }
}
function frozen(value) {
  if (value && typeof value === 'object') { for (const child of Object.values(value)) frozen(child); Object.freeze(value); }
  return value;
}
function canonical(value) {
  return JSON.stringify(value, (_key, item) => item && typeof item === 'object' && !Array.isArray(item)
    ? Object.fromEntries(Object.keys(item).sort().map(key => [key, item[key]])) : item);
}
function resources(consumer) {
  return { paths: consumer.paths, runtimeUser: consumer.runtimeUser, workGroup: consumer.workGroup,
    executionSlots: consumer.executionSlots };
}
async function currentGate(context, options, transition) {
  const value = json(await protectedRead(context.current.gatePath, options, [0o600], 4096));
  const fields = ['version', 'consumerDigest', 'phase', 'operationId', 'target', 'previousActive', 'verifiedRevision'];
  require(exactKeys(value, fields) && value.version === 1 && sha(value.consumerDigest)
    && ['open', 'quiesced', 'drained', 'applying', 'verified', 'recovery-required'].includes(value.phase)
    && (value.phase === 'open' ? value.operationId === null && value.target === null && value.previousActive === null
      : /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(value.operationId ?? '') && revision(value.target))
    && (value.phase === 'verified' ? value.verifiedRevision === value.target : value.verifiedRevision === null),
  'SERIAL_POOL_COMPATIBILITY_CURRENT_GATE_INVALID');
  if (transition !== null) require(options.privateChecks
    && exactKeys(transition, ['operationId', 'previousDigest', 'target'])
    && /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(transition.operationId ?? '')
    && sha(transition.previousDigest) && revision(transition.target),
  'SERIAL_POOL_COMPATIBILITY_TRANSITION_INVALID');
  if (value.consumerDigest !== context.currentConsumerDigest) require(transition !== null
    && value.consumerDigest === transition.previousDigest && value.operationId === transition.operationId
    && value.target === transition.target && ['drained', 'applying'].includes(value.phase),
  'SERIAL_POOL_COMPATIBILITY_CURRENT_CHANGED');
}
function validSourceLinks(value, { nonempty = false } = {}) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const entries = Object.entries(value);
  return entries.length <= 8 && (!nonempty || entries.length > 0) && entries.every(([alias, component]) =>
    /^[A-Za-z0-9_./-]+$/.test(alias) && alias.includes('/')
    && alias.split('/').every(segment => segment && segment !== '.' && segment !== '..')
    && !['controller', 'consumer', 'contracts', 'runtime', 'reviewer', 'deploy'].includes(alias.split('/')[0])
    && ['controller', 'consumer', 'contracts', 'runtime', 'reviewer'].includes(component));
}

// Shared with the bounded transition author. Paths are POSIX, sorted by UTF-8
// bytes. This hashes installed bytes/modes, not a claimed Git tree identifier.
export async function protectedSourceTreeSha256(sourceRoot, { root = '/', ownerUid = 0, sourceLinks = {},
  originalSourceRoot } = {}) {
  const options = { root: resolve(root), ownerUid }; const rows = []; const seenLinks = new Set(); let total = 0;
  require(validSourceLinks(sourceLinks), 'SERIAL_POOL_COMPATIBILITY_SOURCE_LINK_INVALID');
  if (Object.keys(sourceLinks).length) require(typeof originalSourceRoot === 'string'
    && /^\/opt\/[a-z][a-z0-9-]{0,30}\/releases\/[a-f0-9]{40}\/reviewed-source$/.test(originalSourceRoot),
  'SERIAL_POOL_COMPATIBILITY_SOURCE_LINK_INVALID');
  async function visit(directory) {
    await parents(join(directory, '_'), options);
    const before = await lstat(directory);
    require(before.isDirectory() && !before.isSymbolicLink() && before.uid === ownerUid && !(before.mode & 0o022),
      'SERIAL_POOL_COMPATIBILITY_SOURCE_UNSAFE');
    for (const name of await readdir(directory)) {
      const pathname = join(directory, name); const info = await lstat(pathname);
      const relativeName = relative(sourceRoot, pathname).split('\\').join('/');
      require(!/[\0\r\n]/.test(relativeName), 'SERIAL_POOL_COMPATIBILITY_SOURCE_UNSAFE');
      if (info.isSymbolicLink()) {
        require(Object.hasOwn(sourceLinks, relativeName) && info.uid === ownerUid && info.nlink === 1,
          'SERIAL_POOL_COMPATIBILITY_SOURCE_LINK_INVALID');
        const target = originalSourceRoot + '/' + sourceLinks[relativeName];
        const rawTarget = await readlink(pathname, { encoding: 'buffer' });
        require(rawTarget.equals(Buffer.from(target)), 'SERIAL_POOL_COMPATIBILITY_SOURCE_LINK_INVALID');
        // The installed absolute link is retained byte-for-byte. Inspect its
        // fixed target through the internal fixture root without following it.
        await parents(join(physical(options.root, target), '_'), options);
        require(stamp(info) === stamp(await lstat(pathname))
          && rawTarget.equals(await readlink(pathname, { encoding: 'buffer' })),
        'SERIAL_POOL_COMPATIBILITY_SOURCE_CHANGED');
        seenLinks.add(relativeName); total += rawTarget.length;
        require(rows.length < 20000 && total <= 256 * 1024 * 1024, 'SERIAL_POOL_COMPATIBILITY_SOURCE_LIMIT');
        rows.push([relativeName, `${relativeName}\0symlink\0${hash(rawTarget)}\n`]);
      } else if (info.isDirectory()) {
        require(!Object.hasOwn(sourceLinks, relativeName), 'SERIAL_POOL_COMPATIBILITY_SOURCE_LINK_INVALID');
        await visit(pathname);
      }
      else {
        require(info.isFile() && !info.isSymbolicLink() && info.nlink === 1 && info.uid === ownerUid
          && !(info.mode & 0o022) && !Object.hasOwn(sourceLinks, relativeName), 'SERIAL_POOL_COMPATIBILITY_SOURCE_UNSAFE');
        const bytes = await protectedRead(pathname, options, [info.mode & 0o777], 32 * 1024 * 1024);
        total += bytes.length;
        require(rows.length < 20000 && total <= 256 * 1024 * 1024, 'SERIAL_POOL_COMPATIBILITY_SOURCE_LIMIT');
        rows.push([relativeName, `${relativeName}\0${(info.mode & 0o777).toString(8)}\0${hash(bytes)}\n`]);
      }
    }
    require(stamp(before) === stamp(await lstat(directory)), 'SERIAL_POOL_COMPATIBILITY_SOURCE_CHANGED');
  }
  await visit(sourceRoot);
  require(rows.length > 0 && seenLinks.size === Object.keys(sourceLinks).length, 'SERIAL_POOL_COMPATIBILITY_SOURCE_UNSAFE');
  rows.sort((left, right) => Buffer.compare(Buffer.from(left[0]), Buffer.from(right[0])));
  return hash(rows.map(row => row[1]).join(''));
}

const originalDriver = String.raw`
import {pathToFileURL} from 'node:url';
const chunks=[];for await(const chunk of process.stdin)chunks.push(chunk);
const request=JSON.parse(Buffer.concat(chunks));
const moduleAt=path=>import(pathToFileURL(request.sourceRoot+'/'+path).href);
const {CONSUMER,CONSUMER_DIGEST}=await moduleAt('consumer/consumer.mjs');
const contract=await moduleAt('controller/src/execution-contract.mjs');
if(CONSUMER_DIGEST!==request.consumerDigest)contract.fail('CONSUMER_CONFIG_CHANGED');
let result;
if(request.operation==='context')result={consumer:CONSUMER,consumerDigest:CONSUMER_DIGEST};
else if(request.operation==='validate-envelope')result=contract.validateEnvelope(request.envelope);
else if(request.operation==='inventory'){
  const {createAdmissionControl}=await moduleAt('controller/src/admission-control.mjs');
  const {createAttemptStore}=await moduleAt('controller/src/attempt-store.mjs');
  const store=createAttemptStore(request.storeRoot);
  const records=await store.all();
  const expected=new Map(request.runs.map(run=>[run.runId,run]));
  if(records.length!==expected.size)contract.fail('SERIAL_POOL_COMPATIBILITY_RUN_SET_CHANGED');
  for(const record of records){
    const e=record.envelope;const binding=expected.get(e?.runId);
    if(!binding||e.attemptId!==binding.attemptId||contract.digest(e)!==binding.envelopeSha256)
      contract.fail('SERIAL_POOL_COMPATIBILITY_ENVELOPE_CHANGED');
    if(!record.admissionBlock)contract.validateEnvelope(e);
  }
  const selected=records.filter(record=>(request.task===null||record.envelope.issueNumber===request.task)
    &&(request.slot===null||request.slot==='primary'));
  const gate=createAdmissionControl({root:request.gateRoot,consumerDigest:CONSUMER_DIGEST,
    store:{all:async()=>selected},journal:createAttemptStore(request.journalRoot),protectedRoot:request.protectedRoot});
  const state=await gate.status();
  if(state.phase==='open'||state.operationId!==request.operationId)contract.fail('SERIAL_POOL_COMPATIBILITY_GATE_CHANGED');
  let active=state.active,unknown=state.unknown;
  if(request.resourceOnly){
    const released=new Set();const journal=createAttemptStore(request.journalRoot);
    for(const record of selected){
      const lifecycle=record.controllerLifecycle;const e=record.envelope;
      if(e.route!=='auto'||record.admissionBlock)continue;
      const contained=value=>value&&['started','not_started'].includes(value.child)
        &&(value.containment==='reaped'||value.child==='not_started'&&value.containment==='not_required');
      if(lifecycle?.version===1&&lifecycle.status==='complete'&&contained(lifecycle)){released.add(e.runId);continue;}
      const saved=await journal.get(e.runId);
      if(saved?.version===contract.VERSION&&contract.digest(saved.envelope)===contract.digest(e)
        &&saved.execution?.reserved===true&&saved.execution.returned===true&&contained(saved.execution)
        &&saved.collection?.preserved===true&&contract.exactSha(saved.collection.head)
        &&typeof saved.collection.clean==='boolean')released.add(e.runId);
    }
    active=active.filter(id=>!released.has(id));unknown=unknown.filter(id=>!released.has(id));
  }
  result={active,unknown,phase:state.phase,
    runs:records.map(record=>({runId:record.envelope.runId,attemptId:record.envelope.attemptId,
      envelopeSha256:contract.digest(record.envelope)})).sort((left,right)=>left.runId-right.runId)};
}else contract.fail('SERIAL_POOL_COMPATIBILITY_READER_INVALID');
process.stdout.write(JSON.stringify(result));
`;
async function originalCall(context, request, options) {
  const rootPath = pathname => physical(options.root, pathname);
  const payload = { ...request, sourceRoot: context.original.sourceRoot,
    consumerDigest: context.receipt.original.consumerDigest, runs: context.receipt.original.runs,
    storeRoot: context.original.storeRoot, gateRoot: context.original.gatePath ? dirname(context.original.gatePath) : undefined,
    journalRoot: context.originalConsumer?.paths ? rootPath(context.originalConsumer.paths.attemptRoot) : undefined,
    operationId: context.receipt.operationId, protectedRoot: options.root === '/' && options.ownerUid === 0 };
  try {
    const pending = execute(process.execPath, ['--input-type=module', '-e', originalDriver], {
      env: { RELAY_CONSUMER_CONFIG: context.original.consumerPath, PATH: '/usr/bin:/bin',
        HOME: '/nonexistent', LANG: 'C', LC_ALL: 'C' }, timeout: 30000, maxBuffer: 4 * 1024 * 1024,
      windowsHide: true
    });
    pending.child.stdin.end(JSON.stringify(payload));
    return json(Buffer.from((await pending).stdout));
  } catch (error) {
    const code = /Error: ([A-Z][A-Z0-9_]{0,100})\r?\n/.exec(error.stderr ?? '')?.[1];
    fail(code ?? 'SERIAL_POOL_COMPATIBILITY_ORIGINAL_READER_FAILED');
  }
}

function validateReceipt(value, namespace, currentConsumer, { allowSerialSibling = false } = {}) {
  require(exactKeys(value, ['version', 'repository', 'namespace', 'operationId', 'original', 'target'])
    && value.version === 1 && configuredRepositories(currentConsumer).includes(value.repository) && value.namespace === namespace
    && /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(value.operationId ?? '')
    && exactKeys(value.target, ['consumerDigest']) && sha(value.target.consumerDigest)
    && (allowSerialSibling || value.target.consumerDigest === consumerDigest(currentConsumer)),
  'SERIAL_POOL_COMPATIBILITY_RECEIPT_INVALID');
  const old = value.original;
  require(exactKeys(old, ['revision', 'consumerPath', 'consumerSha256', 'consumerDigest', 'sourceRoot', 'sourceTreeSha256',
    'manifestPath', 'manifestSha256', 'configPath', 'configSha256', 'gateSha256', 'runs', 'runnerUser', 'runnerUid',
    ...(Object.hasOwn(old ?? {}, 'sourceLinks') ? ['sourceLinks'] : [])])
    && (!Object.hasOwn(old, 'sourceLinks') || validSourceLinks(old.sourceLinks, { nonempty: true }))
    && revision(old.revision) && ['consumerSha256', 'consumerDigest', 'sourceTreeSha256', 'manifestSha256', 'configSha256', 'gateSha256']
      .every(name => sha(old[name])) && old.consumerDigest !== value.target.consumerDigest
    && /^[a-z_][a-z0-9_-]{0,31}$/.test(old.runnerUser ?? '') && old.runnerUser !== 'root' && positive(old.runnerUid)
    && Array.isArray(old.runs) && old.runs.length <= 10000, 'SERIAL_POOL_COMPATIBILITY_RECEIPT_INVALID');
  const releases = [`/opt/${namespace}/releases/${old.revision}`, `/opt/${namespace}/serial-compat-v1/${old.revision}`];
  const release = releases.find(candidate => old.sourceRoot === candidate + '/reviewed-source');
  require(old.consumerPath === `/etc/${namespace}/serial-consumer-v1.json`
    && release && old.manifestPath === release + '/artifact-manifest.json'
    && old.configPath === release + '/deployment-config.json', 'SERIAL_POOL_COMPATIBILITY_PATH_INVALID');
  const ids = new Set(); const attempts = new Set();
  for (const run of old.runs) {
    require(exactKeys(run, ['runId', 'attemptId', 'envelopeSha256']) && positive(run.runId)
      && /^(run|event)-[1-9][0-9]*$/.test(run.attemptId ?? '') && sha(run.envelopeSha256)
      && !ids.has(run.runId) && !attempts.has(run.attemptId), 'SERIAL_POOL_COMPATIBILITY_RUN_SET_INVALID');
    ids.add(run.runId); attempts.add(run.attemptId);
  }
}

// Internal host/test options are never accepted from a worker/MCP request.
// Public loading permits recovery context selection. Root revalidates private
// original evidence before inventory or any publication operation.
export async function loadSerialPoolCompatibility({ consumerPath = process.env.RELAY_CONSUMER_CONFIG,
  consumer, root = '/', ownerUid = 0, privateChecks = process.getuid?.() === ownerUid,
  consumerTransition = null } = {}) {
  const options = { root: resolve(root), ownerUid, privateChecks, consumerPath, consumer,
    consumerTransition: consumerTransition === null ? null : structuredClone(consumerTransition) };
  require(isAbsolute(consumerPath ?? '') && Number.isSafeInteger(ownerUid) && ownerUid >= 0,
    'SERIAL_POOL_COMPATIBILITY_CONFIG_INVALID');
  const receiptPath = join(dirname(consumerPath), 'serial-pool-compat-v1.json');
  try { await lstat(receiptPath); } catch (error) { if (error.code === 'ENOENT') return null; throw error; }
  const namespace = basename(dirname(consumerPath));
  const historicalContext = basename(consumerPath) === 'serial-consumer-v1.json';
  require(/^[a-z][a-z0-9-]{0,30}$/.test(namespace)
    && consumerPath === physical(options.root, `/etc/${namespace}/${historicalContext ? 'serial-consumer-v1' : 'consumer'}.json`),
  'SERIAL_POOL_COMPATIBILITY_PATH_INVALID');
  const currentPath = physical(options.root, `/etc/${namespace}/consumer.json`);
  const currentBytes = await protectedRead(currentPath, options, [0o644]);
  const currentConsumer = validateConsumer(json(currentBytes));
  const selectedRepository = consumer?.repository ?? currentConsumer.repository;
  const selectedConsumer = selectedRepository === undefined ? null : selectRepositoryConsumer(currentConsumer, selectedRepository);
  require(historicalContext || consumer === undefined || consumerDigest(consumer) === consumerDigest(selectedConsumer),
    'SERIAL_POOL_COMPATIBILITY_CURRENT_CHANGED');
  require(currentConsumer.generalRunnerPool || historicalContext, 'SERIAL_POOL_COMPATIBILITY_CONFIG_INVALID');
  const receiptBytes = await protectedRead(receiptPath, options, [0o644]); const receipt = json(receiptBytes);
  const serialSibling = historicalContext && !currentConsumer.generalRunnerPool;
  const targetConsumerPath = physical(options.root, `/etc/${namespace}/serial-pool-target-consumer-v1.json`);
  let targetConsumer = currentConsumer;
  try { targetConsumer = validateConsumer(json(await protectedRead(targetConsumerPath, options, [0o644]))); }
  catch (error) {
    if (error.code !== 'ENOENT') throw error;
    // Old installations need no new artifact while their original target is
    // still live. The root publisher freezes it before its first Git update.
    require(serialSibling || receipt.target?.consumerDigest === consumerDigest(currentConsumer),
      'SERIAL_POOL_COMPATIBILITY_TARGET_SNAPSHOT_REQUIRED');
  }
  validateReceipt(receipt, namespace, targetConsumer, { allowSerialSibling: serialSibling });
  require(serialSibling || canonical(resources(currentConsumer)) === canonical(resources(targetConsumer)),
    'SERIAL_POOL_COMPATIBILITY_IDENTITY_CHANGED');
  const old = receipt.original;
  const oldConsumerPath = physical(options.root, old.consumerPath);
  const sourceRoot = physical(options.root, old.sourceRoot);
  // A release installed while SERIAL may already contain this adapter. Only
  // that exact sealed module graph may keep its original store/gate context;
  // an arbitrary caller-selected historical configuration cannot bypass the
  // current graph. Resolve locally to avoid recursively invoking this loader.
  if (historicalContext) require(fileURLToPath(import.meta.url) === join(sourceRoot, 'controller/src/serial-pool-compatibility.mjs'),
    'SERIAL_POOL_COMPATIBILITY_ORIGINAL_CONTEXT_INVALID');
  const originalBytes = await protectedRead(oldConsumerPath, options, [0o644]);
  require(hash(originalBytes) === old.consumerSha256, 'SERIAL_POOL_COMPATIBILITY_CONSUMER_CHANGED');
  require(await protectedSourceTreeSha256(sourceRoot, { ...options, sourceLinks: old.sourceLinks,
    originalSourceRoot: `/opt/${namespace}/releases/${old.revision}/reviewed-source` }) === old.sourceTreeSha256,
    'SERIAL_POOL_COMPATIBILITY_SOURCE_CHANGED');
  const source = json(await protectedRead(join(sourceRoot, '.relay-source.json'), options, [0o644, 0o640, 0o600]));
  require(source.revision === old.revision, 'SERIAL_POOL_COMPATIBILITY_SOURCE_CHANGED');
  const context = { receipt, consumerPath, receiptPath, currentConsumer, targetConsumer,
    currentConsumerDigest: consumerDigest(currentConsumer), selectedRepository: selectedRepository ?? receipt.repository,
    originalConsumer: json(originalBytes), root: options.root, ownerUid, privateChecks,
    original: { sourceRoot, consumerPath: oldConsumerPath, runnerUser: old.runnerUser, runnerUid: old.runnerUid } };
  // Original module/default resolution belongs to the original source process.
  const localConsumer = historicalContext ? validateConsumer(json(originalBytes)) : null;
  const resolved = historicalContext ? { consumer: localConsumer, consumerDigest: consumerDigest(localConsumer) }
    : await originalCall(context, { operation: 'context' }, options);
  require(resolved.consumerDigest === old.consumerDigest, 'SERIAL_POOL_COMPATIBILITY_CONSUMER_CHANGED');
  require(!historicalContext || consumer === undefined || consumerDigest(consumer) === old.consumerDigest,
    'SERIAL_POOL_COMPATIBILITY_CONSUMER_CHANGED');
  context.originalConsumer = resolved.consumer;
  const { generalRunnerPool, executionSlots, repositories, ...base } = targetConsumer;
  if (repositories) base.repository = receipt.repository;
  require(!resolved.consumer.generalRunnerPool && !resolved.consumer.executionSlots
    && canonical(base) === canonical(resolved.consumer), 'SERIAL_POOL_COMPATIBILITY_CONFIG_CHANGED');
  require(!serialSibling || !currentConsumer.executionSlots && consumerDigest(currentConsumer) === old.consumerDigest,
    'SERIAL_POOL_COMPATIBILITY_CONFIG_CHANGED');
  const claimRoot = physical(options.root, resolved.consumer.paths.claimRoot);
  context.original.gatePath = join(claimRoot, 'admission-v1.json');
  context.original.storeRoot = join(claimRoot, 'publication-v2');
  context.current = { gatePath: join(claimRoot, 'admission-pool-v1.json'), storeRoot: join(claimRoot, 'publication-pool-v1') };
  const uid = await execute('/usr/bin/id', ['-u', old.runnerUser], { env: { PATH: '/usr/bin:/bin', LANG: 'C', LC_ALL: 'C' }, timeout: 5000 });
  require(uid.stdout.trim() === String(old.runnerUid)
    && (currentConsumer.executionSlots ?? []).every(slot => slot.runnerUser === old.runnerUser), 'SERIAL_POOL_COMPATIBILITY_IDENTITY_CHANGED');
  if (privateChecks) {
    const manifestBytes = await protectedRead(physical(options.root, old.manifestPath), options, [0o600, 0o640]);
    const configBytes = await protectedRead(physical(options.root, old.configPath), options, [0o600]);
    const gateBytes = await protectedRead(context.original.gatePath, options, [0o600]);
    require(hash(manifestBytes) === old.manifestSha256 && hash(configBytes) === old.configSha256
      && hash(gateBytes) === old.gateSha256, 'SERIAL_POOL_COMPATIBILITY_ORIGINAL_CHANGED');
    const manifest = json(manifestBytes); const config = json(configBytes); const gate = json(gateBytes);
    require(['commit', 'resolvedRevision', 'installedRevision'].every(key => manifest[key] === old.revision)
      && manifest.deploymentConfigSha256 === old.configSha256 && config.consumer?.repository === receipt.repository
      && config.environment?.namespace === namespace && config.environment.generalRunner?.user === old.runnerUser
      && validSourceLinks(config.environment.compatibilityLinks ?? {})
      && canonical(config.environment.compatibilityLinks ?? {}) === canonical(old.sourceLinks ?? {}),
    'SERIAL_POOL_COMPATIBILITY_ORIGINAL_CHANGED');
    require(gate.consumerDigest === old.consumerDigest && gate.operationId === receipt.operationId && gate.phase !== 'open',
      'SERIAL_POOL_COMPATIBILITY_GATE_CHANGED');
    if (!historicalContext) await currentGate(context, options, options.consumerTransition);
  }
  require(consumerTransition === null || privateChecks, 'SERIAL_POOL_COMPATIBILITY_TRANSITION_INVALID');
  if (historicalContext) return null;
  const result = frozen(context); settings.set(result, { ...options, receiptSha256: hash(receiptBytes) }); return result;
}

export async function verifySerialPoolCompatibility(context, { privateChecks = context?.privateChecks } = {}) {
  const options = settings.get(context); require(options, 'SERIAL_POOL_COMPATIBILITY_CONTEXT_INVALID');
  const current = await loadSerialPoolCompatibility({ ...options, privateChecks });
  require(current && hash(await protectedRead(current.receiptPath, options, [0o644])) === options.receiptSha256,
    'SERIAL_POOL_COMPATIBILITY_RECEIPT_CHANGED');
  if (privateChecks) await verifyOriginalStoreOwnership(current);
  return current;
}

export function historicalOperationContext(context, record, operation) {
  require(settings.has(context), 'SERIAL_POOL_COMPATIBILITY_CONTEXT_INVALID');
  const e = record?.envelope;
  if (e?.consumerDigest === context.currentConsumerDigest) return { kind: 'current', ...context.current };
  const run = context.receipt.original.runs.find(run => run.runId === e?.runId);
  require(run && e.repository === context.receipt.repository
    && e.consumerDigest === context.receipt.original.consumerDigest && e.attemptId === run.attemptId
    && envelopeHash(e) === run.envelopeSha256, 'SERIAL_POOL_COMPATIBILITY_ENVELOPE_CHANGED');
  require(historicalOperations.has(operation), 'SERIAL_POOL_COMPATIBILITY_HISTORICAL_EXECUTION_FORBIDDEN');
  return { kind: 'original', ...context.original };
}

export async function invokeOriginalReader(context, { operation, envelope, task = null, slot = null, resourceOnly = false } = {}) {
  require(['validate-envelope', 'inventory'].includes(operation), 'SERIAL_POOL_COMPATIBILITY_READER_INVALID');
  const verified = await verifySerialPoolCompatibility(context, { privateChecks: true });
  require(task === null || positive(task), 'SERIAL_POOL_COMPATIBILITY_READER_INVALID');
  require(slot === null || /^[a-z][a-z0-9-]{0,31}$/.test(slot), 'SERIAL_POOL_COMPATIBILITY_READER_INVALID');
  if (operation === 'validate-envelope') historicalOperationContext(verified, { envelope }, operation);
  await verifyOriginalStoreOwnership(verified);
  // Every sealed SERIAL execution used the original primary resource. Its
  // retained journal cannot occupy a distinct managed slot merely because it
  // is unavailable or has unresolved logical publication.
  if (operation === 'inventory' && slot !== null && slot !== 'primary') return { active: [], unknown: [] };
  if (operation === 'inventory') await readProtectedStore(verified, verified.original.storeRoot);
  return originalCall(verified, { operation, envelope, task, slot, resourceOnly }, settings.get(verified));
}

async function verifyOriginalStoreOwnership(context) {
  const options = settings.get(context); const pathname = context.original.storeRoot;
  await parents(pathname, options);
  let names;
  try {
    const info = await lstat(pathname);
    require(info.isDirectory() && !info.isSymbolicLink() && info.uid === options.ownerUid
      && !(info.mode & 0o022), 'SERIAL_POOL_COMPATIBILITY_STORE_UNSAFE');
    names = await readdir(pathname);
  } catch (error) { if (error.code === 'ENOENT') return; throw error; }
  require(names.length <= 10000, 'SERIAL_POOL_COMPATIBILITY_STORE_LIMIT');
  const sealed = new Set(context.receipt.original.runs.map(run => `${run.runId}.json`));
  for (const name of names.filter(name => name.endsWith('.json'))) {
    require(sealed.has(name), 'SERIAL_POOL_COMPATIBILITY_RUN_SET_CHANGED');
    const info = await lstat(join(pathname, name));
    require(info.isFile() && !info.isSymbolicLink() && info.nlink === 1 && info.uid === options.ownerUid
      && !(info.mode & 0o077), 'SERIAL_POOL_COMPATIBILITY_STORE_UNSAFE');
  }
}

async function readProtectedStore(context, pathname, { runId = null, repository = null, scan = false } = {}) {
  const options = settings.get(context); let names;
  await parents(pathname, options);
  try {
    const directory = await lstat(pathname);
    require(directory.isDirectory() && !directory.isSymbolicLink() && directory.uid === options.ownerUid
      && !(directory.mode & 0o022), 'SERIAL_POOL_COMPATIBILITY_STORE_UNSAFE');
    names = await readdir(pathname);
  } catch (error) { if (error.code === 'ENOENT') return []; throw error; }
  require(names.length <= 10000, 'SERIAL_POOL_COMPATIBILITY_STORE_LIMIT');
  const records = [];
  for (const name of names) {
    if (!name.endsWith('.json')) continue;
    require(/^[1-9][0-9]*\.json$/.test(name), 'SERIAL_POOL_COMPATIBILITY_STORE_UNSAFE');
    const id = Number(name.slice(0, -5));
    if (runId !== null && runId !== id) continue;
    let record = null;
    try {
      record = json(await protectedRead(join(pathname, name), options, [0o600], 512 * 1024));
      require(record?.envelope?.runId === id, 'SERIAL_POOL_COMPATIBILITY_RUN_SET_CHANGED');
      records.push(scan ? { runId: id, repository, record, error: null } : record);
    } catch (error) {
      if (!scan) throw error;
      records.push({ runId: id, repository, record, error: error.code ?? 'SERIAL_POOL_COMPATIBILITY_RECORD_UNREADABLE' });
    }
  }
  return records;
}

async function readCurrentStore(context, selection = {}) {
  const root = context.current.storeRoot;
  const repositories = context.currentConsumer.repositories;
  if (!repositories) return readProtectedStore(context, root, { ...selection, repository: context.currentConsumer.repository });
  // A plural graph cannot hide flat records or another repository's tree.
  const options = settings.get(context); await parents(root, options);
  let flat;
  try {
    const info = await lstat(root);
    require(info.isDirectory() && !info.isSymbolicLink() && info.uid === options.ownerUid
      && !(info.mode & 0o022), 'SERIAL_POOL_COMPATIBILITY_STORE_UNSAFE');
    flat = await readdir(root);
  } catch (error) { if (error.code === 'ENOENT') return []; throw error; }
  require(!flat.some(name => name.endsWith('.json')), 'SERIAL_POOL_COMPATIBILITY_CURRENT_CHANGED');
  async function directories(pathname, allowed) {
    await parents(pathname, options);
    let entries;
    try { entries = await readdir(pathname, { withFileTypes: true }); }
    catch (error) { if (error.code === 'ENOENT') return []; throw error; }
    for (const entry of entries) {
      require((entry.isDirectory() || entry.isSymbolicLink()) && allowed.includes(entry.name),
        'SERIAL_POOL_COMPATIBILITY_REPOSITORY_CHANGED');
      const info = await lstat(join(pathname, entry.name));
      require(info.isDirectory() && !info.isSymbolicLink() && info.uid === options.ownerUid
        && !(info.mode & 0o022), 'SERIAL_POOL_COMPATIBILITY_STORE_UNSAFE');
    }
    return entries.filter(entry => entry.isDirectory()).map(entry => entry.name);
  }
  if (!(await directories(root, ['repositories'])).includes('repositories')) return [];
  const owners = [...new Set(repositories.map(repository => repository.split('/')[0]))];
  const records = [];
  for (const owner of await directories(join(root, 'repositories'), owners)) {
    for (const name of await directories(join(root, 'repositories', owner),
      repositories.filter(repository => repository.startsWith(owner + '/')).map(repository => repository.split('/')[1]))) {
      const repository = owner + '/' + name;
      if (selection.repository !== undefined && selection.repository !== repository) continue;
      const selected = await readProtectedStore(context, join(root, 'repositories', owner, name), { ...selection, repository });
      require(selected.every(row => selection.scan || row.envelope.repository === repository), 'SERIAL_POOL_COMPATIBILITY_REPOSITORY_CHANGED');
      records.push(...selected);
      require(records.length <= 10000, 'SERIAL_POOL_COMPATIBILITY_STORE_LIMIT');
    }
  }
  return records;
}

// A sealed envelope hash can recover ownership from the original runner
// journal when the publication record is unreadable. This is identity proof
// only: it supplies no admission disposition, containment or Outcome receipt.
async function sealedJournalEnvelope(context, binding) {
  const options = settings.get(context);
  const pathname = join(physical(options.root, context.originalConsumer.paths.attemptRoot), `${binding.runId}.json`);
  const owners = new Set([options.ownerUid, context.original.runnerUid]);
  try {
    for (let at = dirname(pathname); ; at = dirname(at)) {
      const info = await lstat(at);
      if (!info.isDirectory() || info.isSymbolicLink() || !owners.has(info.uid) || (info.mode & 0o022)) return null;
      if (at === options.root) break;
      if (dirname(at) === at) return null;
    }
    const file = await open(pathname, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
    try {
      const info = await file.stat();
      if (!info.isFile() || info.nlink !== 1 || !owners.has(info.uid) || (info.mode & 0o077) || info.size > 512 * 1024) return null;
      const bytes = await file.readFile();
      if (bytes.length !== info.size || stamp(info) !== stamp(await file.stat()) || stamp(info) !== stamp(await lstat(pathname))) return null;
      const e = json(bytes)?.envelope;
      if (e?.runId !== binding.runId || e.attemptId !== binding.attemptId || e.repository !== context.receipt.repository
        || envelopeHash(e) !== binding.envelopeSha256) return null;
      await originalCall(context, { operation: 'validate-envelope', envelope: e }, options);
      return e;
    } finally { await file.close(); }
  } catch { return null; }
}

// The public composite retains history for lineage/deduplication but cannot
// mutate it. Original Writer operations use their original store separately.
export function createCompatibilityStore({ compatibility, currentStore, originalStore }) {
  require(settings.has(compatibility), 'SERIAL_POOL_COMPATIBILITY_CONTEXT_INVALID');
  const sealed = compatibility.receipt.original.runs;
  const historical = (runId, repository) => repository === compatibility.receipt.repository
    && sealed.some(run => run.runId === runId);
  async function validateCurrent(record, runId, repository, { writing = false } = {}) {
    const e = record?.envelope;
    require(e && e.runId === runId && e.repository === repository && typeof e.attemptId === 'string'
      && sha(e.consumerDigest)
      && !historical(runId, repository), 'SERIAL_POOL_COMPATIBILITY_CURRENT_CHANGED');
    if (e.consumerDigest !== compatibility.currentConsumerDigest) {
      require(!writing, 'SERIAL_POOL_COMPATIBILITY_HISTORICAL_WRITE_FORBIDDEN');
      // Completion proof is needed only when reading a retained pool row.
      const { completedAdmissionRecord } = await import('./admission-control.mjs');
      const selected = resolveExecutionConsumer(selectRepositoryConsumer(compatibility.currentConsumer, e.repository),
        e.executionSlot);
      const journal = createAttemptStore(physical(compatibility.root, selected.paths.attemptRoot),
        { repository: e.repository });
      require(await completedAdmissionRecord(record, journal), 'SERIAL_POOL_COMPATIBILITY_CURRENT_CHANGED');
    }
    return record;
  }
  async function verifiedContext() {
    const verified = await verifySerialPoolCompatibility(compatibility, { privateChecks: true });
    return verified;
  }
  async function selected(runId, repository) {
    require(positive(runId), 'RUN_ID_INVALID');
    require(configuredRepositories(compatibility.currentConsumer).includes(repository), 'ATTEMPT_REPOSITORY_MISMATCH');
    const verified = await verifiedContext();
    const current = await readCurrentStore(verified, { runId, repository });
    const view = await currentStore.get(runId, repository);
    require(current.length <= 1 && envelopeHash(current[0] ?? null) === envelopeHash(view),
      'SERIAL_POOL_COMPATIBILITY_STORE_VIEW_CHANGED');
    if (!historical(runId, repository)) return current.length ? validateCurrent(current[0], runId, repository) : null;
    require(current.length === 0, 'SERIAL_POOL_COMPATIBILITY_DUPLICATE_ATTEMPT');
    const original = await readProtectedStore(verified, verified.original.storeRoot, { runId });
    require(original.length === 1, 'SERIAL_POOL_COMPATIBILITY_RUN_SET_CHANGED');
    require(envelopeHash(original[0]) === envelopeHash(await originalStore.get(runId, repository)),
      'SERIAL_POOL_COMPATIBILITY_STORE_VIEW_CHANGED');
    historicalOperationContext(compatibility, original[0], 'inventory');
    if (!original[0].admissionBlock) await originalCall(verified,
      { operation: 'validate-envelope', envelope: original[0].envelope }, settings.get(verified));
    return original[0];
  }
  async function classified() {
    const verified = await verifySerialPoolCompatibility(compatibility, { privateChecks: true });
    const [original, current] = await Promise.all([readProtectedStore(verified, verified.original.storeRoot), readCurrentStore(verified)]);
    const views = await Promise.all([originalStore.all(), currentStore.all()]);
    for (const [index, records] of [original, current].entries()) {
      const rows = values => values.map(value => [value?.envelope?.repository, value?.envelope?.runId, envelopeHash(value)])
        .sort((a, b) => a[0].localeCompare(b[0]) || a[1] - b[1]);
      require(JSON.stringify(rows(records)) === JSON.stringify(rows(views[index])), 'SERIAL_POOL_COMPATIBILITY_STORE_VIEW_CHANGED');
    }
    const runIds = new Set(); const attempts = new Set();
    require(original.length === sealed.length, 'SERIAL_POOL_COMPATIBILITY_RUN_SET_CHANGED');
    for (const [records, historical] of [[original, true], [current, false]]) for (const record of records) {
      const e = record?.envelope;
      const key = e && `${e.repository}:${e.runId}`; const attemptKey = e && `${e.repository}:${e.attemptId}`;
      require(e && positive(e.runId) && typeof e.attemptId === 'string' && !runIds.has(key) && !attempts.has(attemptKey),
        'SERIAL_POOL_COMPATIBILITY_DUPLICATE_ATTEMPT');
      require(historical ? e.repository === compatibility.receipt.repository
        : configuredRepositories(verified.currentConsumer).includes(e.repository), 'SERIAL_POOL_COMPATIBILITY_REPOSITORY_CHANGED');
      if (historical) historicalOperationContext(compatibility, record, 'inventory');
      else await validateCurrent(record, e.runId, e.repository);
      runIds.add(key); attempts.add(attemptKey);
    }
    // Full classification proves immutable ownership and envelope provenance.
    // Logical execution/publication completion belongs to an explicit drain,
    // not to every unrelated lookup or Writer mutation.
    for (const record of original.filter(record => !record.admissionBlock)) await originalCall(verified,
      { operation: 'validate-envelope', envelope: record.envelope }, settings.get(verified));
    return [...original, ...current].sort((left, right) => left.envelope.runId - right.envelope.runId);
  }
  return {
    all: classified,
    async scan() {
      const verified = await verifiedContext();
      const original = await readProtectedStore(verified, verified.original.storeRoot,
        { scan: true, repository: compatibility.receipt.repository });
      const current = await readCurrentStore(verified, { scan: true });
      for (const binding of sealed) if (!original.some(row => row.runId === binding.runId)) original.push({
        runId: binding.runId, repository: compatibility.receipt.repository, record: null, error: 'ATTEMPT_RECORD_MISSING' });
      for (const [rows, old] of [[original, true], [current, false]]) for (const row of rows) {
        if (row.error) {
          if (old) {
            const binding = sealed.find(run => run.runId === row.runId);
            if (binding) {
              const envelope = await sealedJournalEnvelope(verified, binding);
              if (envelope) row.envelope = envelope;
            }
          }
          continue;
        }
        try {
          if (old) {
            historicalOperationContext(compatibility, row.record, 'inventory');
            if (!row.record.admissionBlock) await originalCall(verified,
              { operation: 'validate-envelope', envelope: row.record.envelope }, settings.get(verified));
          } else await validateCurrent(row.record, row.runId, row.repository);
        } catch (error) {
          row.error = error.code ?? 'SERIAL_POOL_COMPATIBILITY_RECORD_UNREADABLE';
          if (old) {
            // A changed sealed envelope is not ownership evidence. Only the
            // original hash-bound journal can supply its identity fallback.
            row.record = null;
            const binding = sealed.find(run => run.runId === row.runId);
            const envelope = binding && await sealedJournalEnvelope(verified, binding);
            if (envelope) row.envelope = envelope;
          }
        }
      }
      return [...original, ...current].sort((left, right) => left.runId - right.runId);
    },
    async get(runId, repository = compatibility.selectedRepository) {
      return selected(runId, repository);
    },
    async put(runId, value) {
      require(positive(runId), 'RUN_ID_INVALID');
      require(compatibility.selectedRepository !== compatibility.receipt.repository
        || !compatibility.receipt.original.runs.some(run => run.runId === runId), 'SERIAL_POOL_COMPATIBILITY_HISTORICAL_WRITE_FORBIDDEN');
      const previous = await selected(runId, compatibility.selectedRepository);
      if (previous) await validateCurrent(previous, runId, compatibility.selectedRepository, { writing: true });
      await validateCurrent(value, runId, compatibility.selectedRepository, { writing: true });
      return currentStore.put(runId, value);
    },
    async reserve(runId, value) {
      require(positive(runId), 'RUN_ID_INVALID');
      require(compatibility.selectedRepository !== compatibility.receipt.repository
        || !compatibility.receipt.original.runs.some(run => run.runId === runId), 'SERIAL_POOL_COMPATIBILITY_HISTORICAL_EXECUTION_FORBIDDEN');
      const previous = await selected(runId, compatibility.selectedRepository);
      if (previous) await validateCurrent(previous, runId, compatibility.selectedRepository, { writing: true });
      await validateCurrent(value, runId, compatibility.selectedRepository, { writing: true });
      return currentStore.reserve(runId, value);
    },
    async withLock(runId, action) {
      const previous = await selected(runId, compatibility.selectedRepository);
      if (previous) await validateCurrent(previous, runId, compatibility.selectedRepository, { writing: true });
      return currentStore.withLock(runId, action);
    }
  };
}

// PR review IDs are repository-local, unlike the sealed execution run set.
// Only a verified SERIAL transition identifies the owner of the flat receipts.
// Keep those bytes in place and write new receipts solely in target namespaces.
export function createSerialPrLifecycleStore(compatibility) {
  require(settings.has(compatibility) && compatibility.currentConsumer.repositories,
    'SERIAL_POOL_COMPATIBILITY_CONTEXT_INVALID');
  const root = join(dirname(compatibility.original.storeRoot), 'pr-lifecycle-v1');
  const repository = compatibility.selectedRepository;
  const repositories = configuredRepositories(compatibility.currentConsumer);
  require(repositories.includes(repository), 'ATTEMPT_REPOSITORY_MISMATCH');
  const currentStore = createAttemptStore(join(root, 'repositories', ...repository.split('/')), { repository });
  const code = 'SERIAL_POOL_LIFECYCLE_INVALID';
  function validate(record, id, target, retained) {
    const b = record?.binding;
    require(exactKeys(record, ['binding', 'lifecycleIntent'])
      && exactKeys(b, ['repository', 'prNumber', 'reviewId', 'head', 'authorityDigest'])
      && b.repository === target && positive(b.prNumber) && b.reviewId === id
      && positive(id) && revision(b.head) && sha(b.authorityDigest), code);
    if (retained) require(record.lifecycleIntent === null, 'SERIAL_POOL_LIFECYCLE_UNRESOLVED');
    else require(record.lifecycleIntent === null || exactKeys(record.lifecycleIntent, ['number', 'head', 'draft'])
      && record.lifecycleIntent.number === b.prNumber && record.lifecycleIntent.head === b.head
      && record.lifecycleIntent.draft === true, code);
    return record;
  }
  async function classified() {
    const verified = await verifySerialPoolCompatibility(compatibility, { privateChecks: true });
    const options = settings.get(verified); const original = new Map(); const current = new Map();
    let count = 0;
    async function entries(pathname) {
      await parents(join(pathname, '_'), options).catch(error => { if (error.code !== 'ENOENT') throw error; });
      try {
        const info = await lstat(pathname);
        require(info.isDirectory() && !info.isSymbolicLink() && info.uid === options.ownerUid && !(info.mode & 0o022), code);
        const names = await readdir(pathname);
        count += names.length; require(count <= 10000, 'SERIAL_POOL_COMPATIBILITY_STORE_LIMIT');
        return names;
      } catch (error) { if (error.code === 'ENOENT') return []; throw error; }
    }
    async function record(pathname, name, target, retained) {
      require(/^[1-9][0-9]*\.json$/.test(name), code);
      const id = Number(name.slice(0, -5));
      const value = validate(json(await protectedRead(join(pathname, name), options, [0o600], 512 * 1024)), id, target, retained);
      const key = `${target}:${id}`;
      require(!original.has(key) && !current.has(key), 'SERIAL_POOL_LIFECYCLE_COLLISION');
      (retained ? original : current).set(key, value);
    }
    for (const name of await entries(root)) {
      if (name !== 'repositories') await record(root, name, compatibility.receipt.repository, true);
    }
    const targetRoot = join(root, 'repositories');
    for (const owner of await entries(targetRoot)) {
      require(repositories.some(target => target.split('/')[0] === owner), code);
      for (const name of await entries(join(targetRoot, owner))) {
        const target = `${owner}/${name}`; require(repositories.includes(target), code);
        const pathname = join(targetRoot, owner, name);
        for (const file of await entries(pathname)) await record(pathname, file, target, false);
      }
    }
    return { original, current };
  }
  return {
    async get(id) {
      require(positive(id), 'RUN_ID_INVALID');
      const { original, current } = await classified(); const key = `${repository}:${id}`;
      return original.get(key) ?? current.get(key) ?? null;
    },
    async isRetained(id) {
      return (await classified()).original.has(`${repository}:${id}`);
    },
    async put(id, value) {
      const { original, current } = await classified(); const key = `${repository}:${id}`;
      require(!original.has(key), 'SERIAL_POOL_COMPATIBILITY_HISTORICAL_WRITE_FORBIDDEN');
      validate(value, id, repository, false);
      const previous = current.get(key);
      require(!previous || canonical(previous.binding) === canonical(value.binding), 'PR_LIFECYCLE_BINDING_CHANGED');
      return currentStore.put(id, value);
    }
  };
}
