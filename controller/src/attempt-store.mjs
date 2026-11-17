import { mkdir, readFile, open, rename, readdir } from 'node:fs/promises';
import { constants } from 'node:fs';
import { randomUUID } from 'node:crypto';
import { join } from 'node:path';
import { positive, fail, REPOSITORY } from './execution-contract.mjs';
import { withStoreLock } from './store-lock.mjs';
import { INSTALLATION_CONSUMER } from '../../consumer/consumer.mjs';
import { configuredRepositories } from '../../consumer/consumer-config.mjs';
import { recordEntrypointFailure } from './repository-entrypoint.mjs';
export const ATTEMPT_RECORD_BYTES = 512 * 1024;
const recordFailureError = (code, observation) => Object.assign(new Error(code), { code, observation });

// Root broker uses its repository lock; runner attempts claim their own run.
// Historical numeric filenames stay readable in separately scoped roots.
export function createAttemptStore(root, { repository = REPOSITORY, repositories = [repository], namespace = false,
  recordFailure = recordEntrypointFailure } = {}) {
  const targetRoot = target => {
    if (!repositories.includes(target)) throw recordFailureError('ATTEMPT_REPOSITORY_MISMATCH', { check: 'attempt-store-repository', expected: repositories, observed: target });
    return namespace ? join(root, 'repositories', ...target.split('/')) : root;
  };
  const path = (id, target = repository) => { if (!positive(id)) fail('RUN_ID_INVALID'); return join(targetRoot(target), `${id}.json`); };
  const validate = (value, target = repository) => {
    if (value?.envelope && value.envelope.repository !== target) throw recordFailureError('ATTEMPT_REPOSITORY_MISMATCH', { check: 'attempt-record-repository', expected: target, observed: value.envelope.repository });
    return value;
  };
  const encode = value => {
    const bytes = JSON.stringify(validate(value), null, 2) + '\n';
    if (Buffer.byteLength(bytes) > ATTEMPT_RECORD_BYTES) throw recordFailureError('ATTEMPT_RECORD_TOO_LARGE', { check: 'attempt-record-byte-limit', expected: ATTEMPT_RECORD_BYTES, observed: Buffer.byteLength(bytes) });
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
    catch (error) { if (error.code === 'ENOENT') return null;
      throw Object.assign(new Error('ATTEMPT_RECORD_UNREADABLE', { cause: error }), {
        code: 'ATTEMPT_RECORD_UNREADABLE', native: { operation: 'attempt-record-read', path: pathname, runId: id, repository: target } }); }
    return validate(value, target);
  }
  async function scan() {
    await assertNamespace();
    const rows = []; let observed = 0;
    for (const target of namespace ? repositories : [repository]) {
      let names; try { names = await readdir(targetRoot(target)); } catch (e) { if (e.code === 'ENOENT') continue; throw e; }
      observed += names.length;
      if (observed > 10000) fail('ATTEMPT_STORE_LIMIT');
      for (const name of names.filter(n => /^[1-9][0-9]*\.json$/.test(n))) {
        const runId = Number(name.slice(0, -5));
        try {
          const record = await readRecord(runId, target);
          const error = record === null ? 'ATTEMPT_RECORD_UNAVAILABLE'
            : !record?.envelope || record.envelope.runId !== runId ? 'ATTEMPT_RECORD_INVALID' : null;
          const row = { runId, repository: target, record, error };
          if (error) {
            const cause = Object.assign(new Error(error), { code: error, observation: {
              check: 'attempt-record-identity', expected: { runId, repository: target },
              observed: { exists: record !== null, runId: record?.envelope?.runId, repository: record?.envelope?.repository } } });
            Object.defineProperty(row, 'cause', { value: cause });
            const diagnosticStore = await recordFailure(cause, 'attempt-store-scan');
            if (diagnosticStore) row.diagnosticStore = diagnosticStore;
          }
          rows.push(row);
        } catch (error) {
          // Preserve the known namespace/run identity. Callers may scope a
          // check, but cannot silently turn an unreadable row into absence.
          const row = { runId, repository: target, record: null, error: error.code ?? 'ATTEMPT_RECORD_UNREADABLE' };
          const diagnosticStore = await recordFailure(error, 'attempt-store-scan');
          if (diagnosticStore) row.diagnosticStore = diagnosticStore;
          Object.defineProperty(row, 'cause', { value: error });
          rows.push(row);
        }
      }
    }
    return rows;
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
    scan,
    async all() {
      return (await scan()).map(row => { if (row.error) throw Object.assign(new Error(row.error, { cause: row.cause }), { code: row.error }); return row.record; });
    }
  };
}

// Publication and PR operation identifiers are repository-local. The shared
// installation lock and lifecycle gate stay outside these target namespaces.
export const createPublicationStore = root => createAttemptStore(root, {
  repositories: configuredRepositories(INSTALLATION_CONSUMER),
  namespace: Object.hasOwn(INSTALLATION_CONSUMER, 'repositories')
});
