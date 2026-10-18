import { cp, mkdir, mkdtemp, readFile, rm, symlink, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { consumerDigest, EXECUTION_PATH_NAMES, selectRepositoryConsumer, validateConsumer } from '../../consumer/consumer-config.mjs';
import { createAttemptStore } from '../src/attempt-store.mjs';
import { loadSerialPoolCompatibility, protectedSourceTreeSha256 } from '../src/serial-pool-compatibility.mjs';

const execute = promisify(execFile);
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const digest = value => hash(JSON.stringify(value));
const repositoryRoot = fileURLToPath(new URL('../..', import.meta.url));
const operationId = '12345678-1234-1234-1234-123456789abc';
export async function serialPoolFixture(t, { retained = true, sourceLinks = {}, repositories, repository, originalRevision = 'HEAD' } = {}) {
  const root = await mkdtemp(join(tmpdir(), 'relay-serial-compat-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const ownerUid = process.getuid(); const namespace = 'relay-compat';
  const currentUser = (await execute('/usr/bin/id', ['-un'])).stdout.trim();
  const user = currentUser === 'root' ? 'nobody' : currentUser;
  const runnerUid = Number((await execute('/usr/bin/id', ['-u', user])).stdout.trim());
  const revision = (await execute('/usr/bin/git', ['rev-parse', originalRevision], { cwd: repositoryRoot })).stdout.trim();
  const at = pathname => join(root, pathname.slice(1));
  const write = async (pathname, value, mode = 0o600) => {
    await mkdir(dirname(pathname), { recursive: true, mode: 0o755 });
    const bytes = typeof value === 'string' || Buffer.isBuffer(value) ? value : JSON.stringify(value) + '\n';
    await writeFile(pathname, bytes, { mode }); return hash(bytes);
  };
  const release = `/opt/${namespace}/${retained ? 'serial-compat-v1' : 'releases'}/${revision}`;
  const sourcePath = release + '/reviewed-source'; const sourceRoot = at(sourcePath);
  await mkdir(sourceRoot, { recursive: true, mode: 0o755 });
  // Export actual retained source, including its complete envelope validator.
  // The fixture never opens model Git metadata or substitutes a mock validator.
  const archive = await execute('/usr/bin/git', ['archive', '--format=tar', revision, 'consumer', 'controller/src',
    'runtime/src', 'contracts/src', 'reviewer/src/executable-cr-v2.json'], { cwd: repositoryRoot, encoding: 'buffer', maxBuffer: 32 * 1024 * 1024 });
  const extraction = execute('/usr/bin/tar', ['-xf', '-', '-C', sourceRoot]);
  extraction.child.stdin.end(archive.stdout); await extraction;
  await write(join(sourceRoot, '.relay-source.json'), { revision }, 0o644);
  const originalSourceRoot = `/opt/${namespace}/releases/${revision}/reviewed-source`;
  for (const component of new Set(Object.values(sourceLinks))) {
    if (retained) {
      await mkdir(dirname(at(originalSourceRoot + '/' + component)), { recursive: true, mode: 0o755 });
      await cp(join(sourceRoot, component), at(originalSourceRoot + '/' + component), { recursive: true });
    }
  }
  for (const [alias, component] of Object.entries(sourceLinks)) {
    await mkdir(dirname(join(sourceRoot, alias)), { recursive: true, mode: 0o755 });
    await symlink(originalSourceRoot + '/' + component, join(sourceRoot, alias));
  }
  const originalConsumer = validateConsumer(JSON.parse(await readFile(join(sourceRoot, 'consumer/fixtures/example.json'), 'utf8')));
  const oldDigest = consumerDigest(originalConsumer);
  const slots = [{ id: 'primary', runnerName: 'compat-pool', runnerUser: user, runtimeUser: originalConsumer.runtimeUser,
    workGroup: 'relay-work', paths: Object.fromEntries(EXECUTION_PATH_NAMES.map(name => [name, originalConsumer.paths[name]])) },
  { id: 'pool-2', runnerName: 'compat-pool-2', runnerUser: user, runtimeUser: originalConsumer.runtimeUser,
    workGroup: 'relay-work', paths: Object.fromEntries(EXECUTION_PATH_NAMES.map(name => [name, `/var/lib/relay-second/${name}`])) }];
  const target = { ...originalConsumer, generalRunnerPool: { desiredCapacity: 2 }, executionSlots: slots };
  if (repositories) { delete target.repository; target.repositories = repositories; }
  const installationConsumer = validateConsumer(target);
  const currentConsumer = selectRepositoryConsumer(installationConsumer, repository ?? originalConsumer.repository);
  const currentDigest = consumerDigest(installationConsumer);
  const consumerPath = at(`/etc/${namespace}/consumer.json`);
  await write(consumerPath, installationConsumer, 0o644);
  const oldConsumerPath = `/etc/${namespace}/serial-consumer-v1.json`;
  const consumerSha256 = await write(at(oldConsumerPath), originalConsumer, 0o644);
  const configPath = release + '/deployment-config.json';
  const configSha256 = await write(at(configPath), { consumer: originalConsumer,
    environment: { namespace, generalRunner: { user }, ...(Object.keys(sourceLinks).length ? { compatibilityLinks: sourceLinks } : {}) } });
  const manifestPath = release + '/artifact-manifest.json';
  const manifestSha256 = await write(at(manifestPath), { commit: revision, resolvedRevision: revision,
    installedRevision: revision, deploymentConfigSha256: configSha256 });
  const claimRoot = at(originalConsumer.paths.claimRoot);
  const service = { active: false, enabled: 'disabled', load: 'loaded' };
  const gatePath = join(claimRoot, 'admission-v1.json');
  const gateSha256 = await write(gatePath, { version: 1, consumerDigest: oldDigest, phase: 'applying', operationId,
    target: 'c'.repeat(40), verifiedRevision: null,
    previousActive: { reviewer: service, production: service, general: { active: true, enabled: 'enabled', load: 'loaded' } } });
  const envelope = (runId, overrides = {}) => ({ version: 2, repository: originalConsumer.repository, consumerDigest: oldDigest,
    runId, attemptId: `run-${runId}`, step: 1, target: 'issue', number: 42, issueNumber: 42, route: 'auto',
    branch: originalConsumer.taskBranchPrefix + 'test-42', startHead: 'a'.repeat(40), historicalBase: 'a'.repeat(40), targetBase: 'a'.repeat(40),
    authorityDigest: 'b'.repeat(64), profile: originalConsumer.defaultProfile, subagentsAllowed: false, validation: ['diff-check'], ...overrides });
  const outcome = { status: 'BLOCKED', head: null, prNumber: null, outcomeId: 17 };
  const terminal = { envelope: envelope(99), outcome,
    controllerLifecycle: { version: 1, status: 'complete', child: 'not_started', containment: 'not_required' } };
  const manual = { envelope: envelope(100, { route: 'manual' }) };
  const blocked = { envelope: { version: 2, repository: originalConsumer.repository, consumerDigest: oldDigest,
    runId: 101, attemptId: 'run-101', route: 'auto', issueNumber: 43 }, admissionBlock: { code: 'OWNER_DECISION_REQUIRED' } };
  const legacy = { envelope: envelope(102), outcome };
  const records = [terminal, manual, blocked, legacy];
  const originalStore = createAttemptStore(join(claimRoot, 'publication-v2'), { repository: originalConsumer.repository });
  for (const record of records) await originalStore.put(record.envelope.runId, record);
  const journal = createAttemptStore(at(originalConsumer.paths.attemptRoot), { repository: originalConsumer.repository });
  await journal.put(102, { version: 2, envelope: legacy.envelope, execution: null, outcome });
  const currentStore = createAttemptStore(join(claimRoot, 'publication-pool-v1'), {
    repository: currentConsumer.repository, repositories: repositories ?? [originalConsumer.repository], namespace: !!repositories });
  const current = { envelope: envelope(200, { repository: currentConsumer.repository,
    consumerDigest: currentDigest, executionSlot: 'primary', step: 2 }),
    controllerLifecycle: { version: 1, status: 'active' } };
  await currentStore.put(200, current);
  const receipt = { version: 1, repository: originalConsumer.repository, namespace, operationId,
    original: { revision, consumerPath: oldConsumerPath, consumerSha256, consumerDigest: oldDigest, sourceRoot: sourcePath,
      sourceTreeSha256: await protectedSourceTreeSha256(sourceRoot, { root, ownerUid, sourceLinks, originalSourceRoot }), manifestPath, manifestSha256,
      configPath, configSha256, gateSha256, runs: records.map(record => ({ runId: record.envelope.runId,
        attemptId: record.envelope.attemptId, envelopeSha256: digest(record.envelope) })), runnerUser: user, runnerUid,
      ...(Object.keys(sourceLinks).length ? { sourceLinks } : {}) },
    target: { consumerDigest: currentDigest } };
  const receiptPath = at(`/etc/${namespace}/serial-pool-compat-v1.json`);
  await write(receiptPath, receipt, 0o644);
  const options = { root, ownerUid, consumerPath, consumer: currentConsumer, privateChecks: true };
  const load = () => loadSerialPoolCompatibility(options);
  return { root, at, write, options, load, receipt, receiptPath, sourceRoot, gatePath, oldConsumerPath: at(oldConsumerPath),
    currentConsumer, installationConsumer, consumerPath, originalStore, currentStore, records, current, envelope, journal, originalSourceRoot };
}
