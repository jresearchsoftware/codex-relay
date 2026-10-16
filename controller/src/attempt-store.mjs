import { mkdir, readFile, open, rename, readdir } from 'node:fs/promises';
import { constants } from 'node:fs';
import { randomUUID } from 'node:crypto';
import { join } from 'node:path';
import { positive, fail, REPOSITORY } from './execution-contract.mjs';
import { withStoreLock } from './store-lock.mjs';
import { INSTALLATION_CONSUMER } from '../../consumer/consumer.mjs';
import { configuredRepositories } from '../../consumer/consumer-config.mjs';
export const ATTEMPT_RECORD_BYTES = 512 * 1024;

// Root broker uses its repository lock; runner attempts claim their own run.
// Historical numeric filenames stay readable in separately scoped roots.
export function createAttemptStore(root, { repository = REPOSITORY, repositories = [repository], namespace = false } = {}) {
  const targetRoot = target => {
    if (!repositories.includes(target)) fail('ATTEMPT_REPOSITORY_MISMATCH');
    return namespace ? join(root, 'repositories', ...target.split('/')) : root;
  };
  const path = (id, target = repository) => { if (!positive(id)) fail('RUN_ID_INVALID'); return join(targetRoot(target), `${id}.json`); };
  const validate = (value, target = repository) => {
    if (value?.envelope && value.envelope.repository !== target) fail('ATTEMPT_REPOSITORY_MISMATCH');
    return value;
  };
  const encode = value => {
    const bytes = JSON.stringify(validate(value), null, 2) + '\n';
    if (Buffer.byteLength(bytes) > ATTEMPT_RECORD_BYTES) fail('ATTEMPT_RECORD_TOO_LARGE');
    return bytes;
  };
  async function syncDirectory() {
    if (process.platform === 'win32') return;
    const directory = await open(targetRoot(repository), 'r');
    try { await directory.sync(); } finally { await directory.close(); }
  }
  async function assertNamespace() {
    // Keep retained singleton records visible at every operation boundary,
    // including a PR lifecycle operation made before execution admission.
    if (!namespace) return;
    let names; try { names = await readdir(root); } catch (e) { if (e.code !== 'ENOENT') throw e; }
    if (names?.some(name => /^[1-9][0-9]*\.json$/.test(name))) fail('CONSUMER_CONFIG_CHANGED');
  }
  async function readRecord(id, target = repository) {
    const pathname = path(id, target);
    let value;
    try { value = JSON.parse(await readFile(pathname, 'utf8')); }
    catch (error) { if (error.code === 'ENOENT') return null; fail('ATTEMPT_RECORD_UNREADABLE'); }
    return validate(value, target);
  }
  return {
    async get(id, target = repository) {
      await assertNamespace();
      return readRecord(id, target);
    },
    async withLock(id, action) {
      await assertNamespace();
      await mkdir(targetRoot(repository), { recursive: true, mode: 0o700 });
      return withStoreLock(`${path(id)}.controller-lock`, action, { busyCode: 'ATTEMPT_CONTROLLER_BUSY' });
    },
    async reserve(id, value) {
      await assertNamespace();
      const bytes = encode(value);
      await mkdir(targetRoot(repository), { recursive: true, mode: 0o700 });
      let file;
      try { file = await open(path(id), constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | (constants.O_NOFOLLOW ?? 0), 0o600); }
      catch (error) { if (error.code === 'EEXIST') return false; throw error; }
      try { await file.writeFile(bytes); await file.sync(); } finally { await file.close(); }
      await syncDirectory();
      return true;
    },
    async put(id, value) {
      await assertNamespace();
      const bytes = encode(value);
      await mkdir(targetRoot(repository), { recursive: true, mode: 0o700 });
      const temp = `${path(id)}.tmp-${randomUUID()}`;
      const file = await open(temp, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | (constants.O_NOFOLLOW ?? 0), 0o600);
      try { await file.writeFile(bytes); await file.sync(); } finally { await file.close(); }
      await rename(temp, path(id));
      await syncDirectory();
    },
    async all() {
      await assertNamespace();
      const records = [];
      let observed = 0;
      for (const target of namespace ? repositories : [repository]) {
        let names; try { names = await readdir(targetRoot(target)); } catch (e) { if (e.code === 'ENOENT') continue; throw e; }
        observed += names.length;
        if (observed > 10000) fail('ATTEMPT_STORE_LIMIT');
        for (const name of names.filter(n => /^[1-9][0-9]*\.json$/.test(n))) records.push(await readRecord(Number(name.slice(0, -5)), target));
      }
      return records;
    }
  };
}

// Publication and PR operation identifiers are repository-local. The shared
// installation lock and lifecycle gate stay outside these target namespaces.
export const createPublicationStore = root => createAttemptStore(root, {
  repositories: configuredRepositories(INSTALLATION_CONSUMER),
  namespace: Object.hasOwn(INSTALLATION_CONSUMER, 'repositories')
});
