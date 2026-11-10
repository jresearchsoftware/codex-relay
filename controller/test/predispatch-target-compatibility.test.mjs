import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, readFile, rm, chmod, symlink, rename } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { promisify } from 'node:util';
import { execFile } from 'node:child_process';
import { assertPredispatchTargetCompatible, assertCompatibleInstalledWriter, PREDISPATCH_RETENTION_CAPABILITY } from '../src/predispatch-target-compatibility.mjs';
import { invokeTargetCheckedAdmission, parseAdmissionArguments } from '../src/admission-cli.mjs';
import { createAdmissionControl } from '../src/admission-control.mjs';
import { CONSUMER_DIGEST } from '../../consumer/consumer.mjs';
import { memoryStore } from './fixture.mjs';

const execute = promisify(execFile);
const operationId = '12345678-1234-4234-8234-123456789abc';
async function source(t, capable = true, staged = false) {
  const root = await mkdtemp(join(tmpdir(), 'predispatch-target-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const path = join(root, 'source');
  await mkdir(join(path, 'deploy'), { recursive: true });
  await writeFile(join(path, 'deploy/installation-contract.json'), JSON.stringify({ schemaVersion: 1, epoch: 1,
    capabilities: ['lifecycle-v1', ...(capable ? [PREDISPATCH_RETENTION_CAPABILITY] : [])] }));
  await writeFile(join(path, 'runtime.mjs'), 'export const value = 1;\n');
  const template = 'deploy/ansible/roles/relay_controller/templates/relay-writer-controller.j2';
  await mkdir(join(path, 'deploy/ansible/roles/relay_controller/templates'), { recursive: true });
  await writeFile(join(path, template), await readFile(new URL('../../' + template, import.meta.url)));
  const git = async (...args) => (await execute('/usr/bin/git', ['-c', 'core.hooksPath=/dev/null', '-C', path, ...args])).stdout.trim();
  await git('init', '--quiet', '--template='); await git('add', '.');
  await git('-c', 'user.name=fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '--quiet', '-m', 'fixture');
  const target = await git('rev-parse', 'HEAD'), tree = await git('rev-parse', 'HEAD^{tree}');
  if (staged) {
    await rm(join(path, '.git'), { recursive: true, force: true });
    await writeFile(join(path, '.relay-source.json'), JSON.stringify({ revision: target, tree }));
  }
  return { root, path, target, tree, options: { root, ownerUid: process.getuid() },
    check: records => assertPredispatchTargetCompatible({ records, target, sourceRoot: path, root, ownerUid: process.getuid() }) };
}
test('old target is still permitted without retained markers', async t => {
  const f = await source(t, false);
  await f.check([{}]);
  await assertPredispatchTargetCompatible({ records: [], target: f.target, sourceRoot: '/missing' });
  for (const key of ['predispatchPending', 'predispatchRecovery'])
    await assert.rejects(f.check([{ [key]: {} }]), { code: 'PREDISPATCH_TARGET_INCOMPATIBLE' });
});
for (const staged of [false, true]) test(`capability is bound to exact ${staged ? 'staged tree' : 'protected Git acquisition'}`, async t => {
  const f = await source(t, true, staged), records = [{ predispatchPending: {} }];
  await f.check(records);
  const file = join(f.path, 'runtime.mjs'), original = await readFile(file);
  await writeFile(file, 'export const value = 2;\n');
  await assert.rejects(f.check(records), { code: 'PREDISPATCH_TARGET_INCOMPATIBLE' });
  await writeFile(file, original); await f.check(records);
  await chmod(f.path, 0o777);
  await assert.rejects(f.check(records), { code: 'PREDISPATCH_TARGET_INCOMPATIBLE' });
  await chmod(f.path, 0o755);
  const metadata = join(f.path, 'deploy/installation-contract.json'), body = await readFile(metadata);
  await rm(metadata); await writeFile(join(f.root, 'foreign.json'), body); await symlink(join(f.root, 'foreign.json'), metadata);
  await assert.rejects(f.check(records), { code: 'PREDISPATCH_TARGET_INCOMPATIBLE' });
});
test('every lifecycle mutation checks fresh records and does not retarget the installed gate on refusal', async t => {
  const f = await source(t, false), store = memoryStore();
  await mkdir(join(f.root, 'claims'));
  const admission = createAdmissionControl({ root: join(f.root, 'claims'), consumerDigest: CONSUMER_DIGEST,
    store, journal: memoryStore(), protectedRoot: false });
  await admission.initialize(); let records = [];
  const invoke = (name, options) => invokeTargetCheckedAdmission(admission, name,
    [{ ...options, targetSource: f.path }], async () => records, f.options);
  await invoke('quiesce', { operationId, target: f.target });
  await admission.drained({ operationId });
  records = [{ predispatchRecovery: {} }];
  await assert.rejects(invoke('phase', { operationId, phase: 'applying' }), { code: 'PREDISPATCH_TARGET_INCOMPATIBLE' });
  assert.equal((await admission.read()).phase, 'drained');
  await admission.phase({ operationId, phase: 'recovery-required' });
  await assert.rejects(invoke('recoveryTarget', { operationId, target: 'b'.repeat(40) }), { code: 'PREDISPATCH_TARGET_INCOMPATIBLE' });
  assert.equal((await admission.read()).target, f.target);
  records = []; await invoke('phase', { operationId, phase: 'applying' });
  await invoke('phase', { operationId, phase: 'verified', revision: f.target });
  records = [{ predispatchPending: {} }];
  await assert.rejects(invoke('resume', { operationId }), { code: 'PREDISPATCH_TARGET_INCOMPATIBLE' });
  assert.equal((await admission.read()).phase, 'verified');
});
test('an old independent installer without a source proof is fenced before quiesce, while a proved target completes', async t => {
  const f = await source(t, true, true), store = memoryStore();
  await mkdir(join(f.root, 'claims'));
  const admission = createAdmissionControl({ root: join(f.root, 'claims'), consumerDigest: CONSUMER_DIGEST,
    store, journal: memoryStore(), protectedRoot: false });
  await admission.initialize();
  const records = async () => [{ predispatchRecovery: {} }];
  await assert.rejects(invokeTargetCheckedAdmission(admission, 'quiesce', [{ operationId, target: f.target }], records, f.options),
    { code: 'PREDISPATCH_TARGET_INCOMPATIBLE' });
  assert.equal((await admission.read()).phase, 'open');
  const invoke = (name, options) => invokeTargetCheckedAdmission(admission, name,
    [{ ...options, targetSource: f.path }], records, f.options);
  await invoke('quiesce', { operationId, target: f.target });
  await admission.drained({ operationId });
  await invoke('phase', { operationId, phase: 'applying' });
  await invoke('phase', { operationId, phase: 'verified', revision: f.target });
  await invoke('resume', { operationId });
  assert.equal((await admission.read()).phase, 'open');
});
test('root target proof is optional on the existing CLI and bounded to lifecycle mutations', () => {
  assert.deepEqual(parseAdmissionArguments(['quiesce', '--operation', operationId, '--target', 'a'.repeat(40),
    '--target-source', '/protected/source']).options, { operationId, target: 'a'.repeat(40), targetSource: '/protected/source' });
  assert.throws(() => parseAdmissionArguments(['status', '--target-source', '/protected/source']), { code: 'ADMISSION_ARGUMENTS_INVALID' });
});
test('finalization fence follows actual installed current and exact wrapper, never a staged claim', async t => {
  const f = await source(t, true, true), install = join(f.root, 'install');
  const release = join(install, 'releases', f.target), installedSource = join(release, 'reviewed-source');
  await mkdir(release, { recursive: true }); await rename(f.path, installedSource);
  await symlink(release, join(install, 'current'));
  const consumerPath = join(f.root, 'consumer.json');
  const consumer = { paths: { writerHelper: join(install, 'relay-writer-controller'),
    claimRoot: join(f.root, 'claims'), credentialEnv: join(f.root, 'writer.env'), credentialKeyFile: join(f.root, 'writer.pem') } };
  const bindings = { relay_consumer_config_path: consumerPath, relay_writer_claim_root: consumer.paths.claimRoot,
    relay_writer_credential_env_file: consumer.paths.credentialEnv, relay_writer_credential_key_file: consumer.paths.credentialKeyFile,
    relay_writer_helper_release_path: join(install, 'current/reviewed-source/controller/src/privileged-writer-entrypoint.mjs') };
  const template = await readFile(join(installedSource, 'deploy/ansible/roles/relay_controller/templates/relay-writer-controller.j2'), 'utf8');
  const wrapper = template.replace(/\{\{\s*([a-z0-9_]+)\s*\}\}/g, (_, key) => bindings[key]);
  await writeFile(consumer.paths.writerHelper, wrapper);
  const check = () => assertCompatibleInstalledWriter({ consumer, consumerPath, ...f.options });
  await check();
  await writeFile(consumer.paths.writerHelper, wrapper.replace('/current/reviewed-source/', `/releases/${'a'.repeat(40)}/reviewed-source/`));
  await assert.rejects(check(), { code: 'PREDISPATCH_COMPATIBLE_WRITER_REQUIRED' });
  await writeFile(consumer.paths.writerHelper, wrapper);
  await rm(join(install, 'current')); await symlink(join(install, 'releases', 'a'.repeat(40)), join(install, 'current'));
  await assert.rejects(check(), { code: 'PREDISPATCH_COMPATIBLE_WRITER_REQUIRED' });
});
