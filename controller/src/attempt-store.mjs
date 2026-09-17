import { mkdir, readFile, writeFile, rename, readdir } from 'node:fs/promises';
import { join } from 'node:path';
import { positive, fail } from './execution-contract.mjs';
export const ATTEMPT_RECORD_BYTES = 512 * 1024;

// Atomic replacement of one bounded record. Root broker uses an OS flock;
// runner orchestration uses GitHub concurrency. No recovery generations.
export function createAttemptStore(root) {
  const path = id => { if (!positive(id)) fail('RUN_ID_INVALID'); return join(root, `${id}.json`); };
  return {
    async get(id) {
      try { return JSON.parse(await readFile(path(id), 'utf8')); }
      catch (error) { if (error.code === 'ENOENT') return null; fail('ATTEMPT_RECORD_UNREADABLE'); }
    },
    async put(id, value) {
      const bytes = JSON.stringify(value, null, 2) + '\n';
      if (Buffer.byteLength(bytes) > ATTEMPT_RECORD_BYTES) fail('ATTEMPT_RECORD_TOO_LARGE');
      await mkdir(root, { recursive: true, mode: 0o700 });
      const temp = `${path(id)}.tmp-${process.pid}`;
      await writeFile(temp, bytes, { mode: 0o600 }); await rename(temp, path(id));
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
