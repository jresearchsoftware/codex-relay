import { CONSUMER } from '../../consumer/consumer.mjs';
import { constants } from 'node:fs';
import { lstat, mkdir, open, readdir, rename, unlink, rmdir } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { safeFailureDiagnosticReference, safeRuntimeLifecycle, safeDiagnosticStoreReference, safeFallbackReference } from './diagnostics.mjs';

export const RUNTIME_FALLBACK_LIMIT = 8;
export const RUNTIME_FALLBACK_BYTES = 16 * 1024;
const DEFAULT_ROOT = join(CONSUMER.paths.attemptRoot, 'runtime-diagnostics');
const validId = value => typeof value === 'string' && /^[A-Za-z0-9_-]{1,128}$/.test(value);
function fail(code) { throw Object.assign(new Error(code), { code }); }

async function protectedStat(path, directory) {
  const value = await lstat(path);
  if (value.isSymbolicLink() || (directory ? !value.isDirectory() : !value.isFile() || value.nlink !== 1)
      || (process.platform !== 'win32' && (value.uid !== process.getuid() || (value.mode & 0o077) !== 0))) fail('DIAGNOSTIC_FALLBACK_UNSAFE');
  return value;
}

async function syncDirectory(path) {
  // Directory fsync is unavailable on Windows; governed runtime uses Linux.
  if (process.platform === 'win32') return;
  const descriptor = await open(path, constants.O_RDONLY | constants.O_DIRECTORY | constants.O_NOFOLLOW);
  try { await descriptor.sync(); } finally { await descriptor.close(); }
}

export function normalizeRuntimeCapsule(value, executionId) {
  if (!validId(executionId) || !value || typeof value !== 'object' || Array.isArray(value)
      || (value.executionId !== undefined && value.executionId !== executionId)) fail('DIAGNOSTIC_FALLBACK_INVALID');
  const safe = safeFailureDiagnosticReference(value) ?? {};
  // A capsule is independent minimum evidence, never an output/stack channel.
  delete safe.preview; delete safe.bytes; delete safe.truncated;
  const boundary = field => typeof value[field] === 'string' && /^[a-z][a-z0-9-]{0,39}$/.test(value[field]) ? { [field]: value[field] } : {};
  const failure = safeFailureDiagnosticReference(value.failureDiagnostic);
  if (failure) { delete failure.preview; delete failure.bytes; delete failure.truncated; }
  const controllerFailure = safeFailureDiagnosticReference(value.controllerFailure);
  if (controllerFailure) { delete controllerFailure.preview; delete controllerFailure.bytes; delete controllerFailure.truncated; }
  const integer = item => (typeof item === 'string' && /^[0-9]{1,32}$/.test(item)) || (Number.isSafeInteger(item) && item >= 0);
  return { schemaVersion: '1.0', executionId, ...safe, ...safeRuntimeLifecycle(value),
    ...(value.released === true ? { released: true } : {}),
    ...boundary('lastSuccessfulBoundary'),
    ...(typeof value.sandboxCreated === 'boolean' ? { sandboxCreated: value.sandboxCreated } : {}),
    ...(typeof value.inputSchemaCreated === 'boolean' ? { inputSchemaCreated: value.inputSchemaCreated } : {}),
    ...(integer(value.sandboxIdentity?.device) && integer(value.sandboxIdentity?.inode)
      ? { sandboxIdentity: { device: String(value.sandboxIdentity.device), inode: String(value.sandboxIdentity.inode) } } : {}),
    ...(safeDiagnosticStoreReference(value.diagnosticStore) ? { diagnosticStore: safeDiagnosticStoreReference(value.diagnosticStore) } : {}),
    ...(safeFallbackReference(value.fallbackReference) ? { fallbackReference: safeFallbackReference(value.fallbackReference) } : {}),
    ...(failure ? { failureDiagnostic: failure } : {}),
    ...(controllerFailure ? { controllerFailure } : {}) };
}

async function prepareRoot(root, create) {
  if (create) await mkdir(root, { recursive: true, mode: 0o700 });
  await protectedStat(root, true);
  if (create) await syncDirectory(dirname(root));
}

function handleFor(root, slot, executionId) {
  const directory = join(root, String(slot));
  const path = join(directory, `${executionId}.json`);
  const reference = { status: 'stored', executionId, slot };
  async function validate() { await protectedStat(root, true); await protectedStat(directory, true); }
  return {
    reference,
    async read() {
      await validate();
      const descriptor = await open(path, constants.O_RDONLY | (constants.O_NOFOLLOW ?? 0));
      try {
        const value = await descriptor.stat();
        if (!value.isFile() || value.nlink !== 1 || value.size > RUNTIME_FALLBACK_BYTES
            || (process.platform !== 'win32' && (value.uid !== process.getuid() || (value.mode & 0o077) !== 0))) fail('DIAGNOSTIC_FALLBACK_UNSAFE');
        const buffer = Buffer.alloc(RUNTIME_FALLBACK_BYTES + 1);
        const { bytesRead } = await descriptor.read(buffer, 0, buffer.length, 0);
        if (bytesRead > RUNTIME_FALLBACK_BYTES) fail('DIAGNOSTIC_FALLBACK_TOO_LARGE');
        let decoded;
        try { decoded = JSON.parse(buffer.subarray(0, bytesRead).toString('utf8')); }
        catch { fail('DIAGNOSTIC_FALLBACK_INVALID'); }
        if (decoded?.schemaVersion !== '1.0') fail('DIAGNOSTIC_FALLBACK_INVALID');
        return normalizeRuntimeCapsule(decoded, executionId);
      } finally { await descriptor.close(); }
    },
    async write(capsule) {
      await validate();
      const safe = normalizeRuntimeCapsule(capsule, executionId);
      const encoded = JSON.stringify(safe) + '\n';
      if (Buffer.byteLength(encoded) > RUNTIME_FALLBACK_BYTES) fail('DIAGNOSTIC_FALLBACK_TOO_LARGE');
      const previous = await lstat(path).catch(error => { if (error.code !== 'ENOENT') throw error; return null; });
      if (previous) await protectedStat(path, false);
      const temporary = join(directory, '.pending');
      const descriptor = await open(temporary, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | (constants.O_NOFOLLOW ?? 0), 0o600);
      try { await descriptor.writeFile(encoded, 'utf8'); await descriptor.sync(); }
      finally { await descriptor.close(); }
      // Keep a failed write/rename's bounded residue. The occupied slot then
      // blocks another reservation instead of discarding the last evidence.
      await rename(temporary, path); await syncDirectory(directory); await syncDirectory(root);
      return reference;
    },
    async release() {
      await validate(); await protectedStat(path, false);
      const entries = await readdir(directory);
      if (entries.length !== 1 || entries[0] !== `${executionId}.json`) fail('DIAGNOSTIC_FALLBACK_RESIDUE');
      const capsule = await this.read();
      if (capsule.cleanup !== 'complete' || capsule.retention !== 'none' || !['stored', 'not_required'].includes(capsule.persistence)) fail('DIAGNOSTIC_FALLBACK_NOT_RELEASABLE');
      // A durable success tombstone avoids deleting the last evidence before
      // a possible release/fsync failure. Only an admitted new reservation may
      // replace it, under the exclusive per-slot reclamation claim below.
      await this.write({ ...capsule, released: true });
      return { status: 'released', executionId, slot };
    }
  };
}

export async function openRuntimeDiagnostic({ executionId, root = DEFAULT_ROOT, includeReleased = false } = {}) {
  if (!validId(executionId)) fail('DIAGNOSTIC_ID_INVALID');
  try { await prepareRoot(root, false); } catch (error) { if (error.code === 'ENOENT') return null; throw error; }
  let found;
  for (let slot = 0; slot < RUNTIME_FALLBACK_LIMIT; slot += 1) {
    const directory = join(root, String(slot));
    try { await protectedStat(directory, true); } catch (error) { if (error.code === 'ENOENT') continue; throw error; }
    const names = await readdir(directory);
    if (names.includes(`${executionId}.json`)) {
      if (found) fail('DIAGNOSTIC_FALLBACK_AMBIGUOUS');
      const candidate = handleFor(root, slot, executionId);
      const capsule = await candidate.read();
      if (!capsule.released || includeReleased) found = candidate;
    }
  }
  return found ?? null;
}

export async function reserveRuntimeDiagnostic({ executionId, root = DEFAULT_ROOT } = {}) {
  if (!validId(executionId)) fail('DIAGNOSTIC_ID_INVALID');
  await prepareRoot(root, true);
  if (await openRuntimeDiagnostic({ executionId, root, includeReleased: true })) fail('DIAGNOSTIC_FALLBACK_EXISTS');
  for (let slot = 0; slot < RUNTIME_FALLBACK_LIMIT; slot += 1) {
    const directory = join(root, String(slot));
    let reclaimed;
    try { await mkdir(join(root, String(slot)), { mode: 0o700 }); }
    catch (error) {
      if (error.code !== 'EEXIST') throw error;
      await protectedStat(directory, true);
      const entries = await readdir(directory);
      if (entries.length !== 1 || !/^[A-Za-z0-9_-]{1,128}\.json$/.test(entries[0])) continue;
      const previousId = entries[0].slice(0, -5);
      let previous;
      try { previous = await handleFor(root, slot, previousId).read(); }
      catch (readError) { if (readError.code === 'ENOENT') continue; throw readError; }
      if (previous.released !== true || previous.cleanup !== 'complete' || previous.retention !== 'none') continue;
      try { await mkdir(join(directory, '.reclaim'), { mode: 0o700 }); }
      catch (claimError) { if (claimError.code === 'EEXIST') continue; throw claimError; }
      // Revalidate under the claim: another reservation may have replaced the
      // observed success while we waited. A stale claim fails closed.
      const claimedEntries = await readdir(directory);
      if (claimedEntries.length !== 2 || !claimedEntries.includes(entries[0])) {
        await rmdir(join(directory, '.reclaim')); await syncDirectory(directory); continue;
      }
      const claimed = await handleFor(root, slot, previousId).read();
      if (claimed.released !== true) {
        await rmdir(join(directory, '.reclaim')); await syncDirectory(directory); continue;
      }
      reclaimed = entries[0];
    }
    await syncDirectory(root);
    const handle = handleFor(root, slot, executionId);
    await handle.write({ executionId, stage: 'preflight', childState: 'not_started', containment: 'not_required',
      cleanup: 'not_required', persistence: 'pending', retention: 'unknown', sandboxCreated: false, inputSchemaCreated: false });
    if (reclaimed) {
      await unlink(join(directory, reclaimed));
      await rmdir(join(directory, '.reclaim'));
      await syncDirectory(directory);
    }
    return handle;
  }
  fail('DIAGNOSTIC_RETENTION_LIMIT');
}
