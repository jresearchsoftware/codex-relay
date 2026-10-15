import { mkdir, readFile, open, rename, readdir } from 'node:fs/promises';
import { constants } from 'node:fs';
import { randomUUID } from 'node:crypto';
import { join } from 'node:path';
import { positive, fail, REPOSITORY } from './execution-contract.mjs';
import { withStoreLock } from './store-lock.mjs';
export const ATTEMPT_RECORD_BYTES = 512 * 1024;

// Root broker uses its repository lock; runner attempts claim their own run.
// Historical numeric filenames stay readable in separately scoped roots.
export function createAttemptStore(root, { repository = REPOSITORY } = {}) {
  const path = id => { if (!positive(id)) fail('RUN_ID_INVALID'); return join(root, `${id}.json`); };
  const validate = value => {
    if (value?.envelope && value.envelope.repository !== repository) fail('ATTEMPT_REPOSITORY_MISMATCH');
    return value;
  };
  const encode = value => {
    const bytes = JSON.stringify(validate(value), null, 2) + '\n';
    if (Buffer.byteLength(bytes) > ATTEMPT_RECORD_BYTES) fail('ATTEMPT_RECORD_TOO_LARGE');
    return bytes;
  };
  async function syncDirectory() {
    if (process.platform === 'win32') return;
    const directory = await open(root, 'r');
    try { await directory.sync(); } finally { await directory.close(); }
  }
  return {
    async get(id) {
      let value;
      try { value = JSON.parse(await readFile(path(id), 'utf8')); }
      catch (error) { if (error.code === 'ENOENT') return null; fail('ATTEMPT_RECORD_UNREADABLE'); }
      return validate(value);
    },
    async withLock(id, action) {
      await mkdir(root, { recursive: true, mode: 0o700 });
      return withStoreLock(`${path(id)}.controller-lock`, action, { busyCode: 'ATTEMPT_CONTROLLER_BUSY' });
    },
    async reserve(id, value) {
      const bytes = encode(value);
      await mkdir(root, { recursive: true, mode: 0o700 });
      let file;
      try { file = await open(path(id), constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | (constants.O_NOFOLLOW ?? 0), 0o600); }
      catch (error) { if (error.code === 'EEXIST') return false; throw error; }
      try { await file.writeFile(bytes); await file.sync(); } finally { await file.close(); }
      await syncDirectory();
      return true;
    },
    async put(id, value) {
      const bytes = encode(value);
      await mkdir(root, { recursive: true, mode: 0o700 });
      const temp = `${path(id)}.tmp-${randomUUID()}`;
      const file = await open(temp, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | (constants.O_NOFOLLOW ?? 0), 0o600);
      try { await file.writeFile(bytes); await file.sync(); } finally { await file.close(); }
      await rename(temp, path(id));
      await syncDirectory();
    },
    async all() {
      let names; try { names = await readdir(root); } catch (e) { if (e.code === 'ENOENT') return []; throw e; }
      if (names.length > 10000) fail('ATTEMPT_STORE_LIMIT');
      const records = [];
      for (const name of names.filter(n => /^[1-9][0-9]*\.json$/.test(n))) records.push(await this.get(Number(name.slice(0, -5))));
      return records;
    }
  };
}
