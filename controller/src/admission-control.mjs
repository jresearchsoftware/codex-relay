import { constants } from 'node:fs';
import { open, lstat, rename } from 'node:fs/promises';
import { dirname, join, isAbsolute } from 'node:path';
import { randomUUID } from 'node:crypto';
import { parseConsumerJson } from '../../consumer/consumer-config.mjs';
import { digest, exactSha, fail, positive, VERSION } from './execution-contract.mjs';

export const ADMISSION_STATE_BYTES = 4096;
const PHASES = new Set(['open', 'quiesced', 'drained', 'applying', 'verified', 'recovery-required']);
const operation = value => typeof value === 'string' && /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(value);
const fields = ['version', 'consumerDigest', 'phase', 'operationId', 'target', 'previousActive', 'verifiedRevision'];
function validServices(value) {
  const names = ['reviewer', 'production', 'general'];
  return value && typeof value === 'object' && !Array.isArray(value)
    && Object.keys(value).length === names.length && names.every(name => {
      const service = value[name];
      return service && typeof service === 'object' && !Array.isArray(service) && Object.keys(service).length === 3
        && ['active', 'enabled', 'load'].every(key => Object.hasOwn(service, key))
        && typeof service.active === 'boolean'
        && ['enabled', 'enabled-runtime', 'disabled'].includes(service.enabled)
        && ['loaded', 'not-found'].includes(service.load)
        && (service.load !== 'not-found' || (!service.active && service.enabled === 'disabled'));
    });
}

// The fixed root entrypoints serialize every call with publication-v2.lock.
// The gate is the sole lifecycle admission state; active reservations stay in
// the existing Writer attempts, alongside their immutable admission.
export function createAdmissionControl({ root, consumerDigest, store, journal, protectedRoot = true }) {
  if (!isAbsolute(root) || !/^[a-f0-9]{64}$/.test(consumerDigest ?? '')) fail('ADMISSION_CONFIG_INVALID');
  const pathname = join(root, 'admission-v1.json');
  async function protect() {
    if (!protectedRoot) return;
    for (let at = root; ; at = dirname(at)) {
      const stat = await lstat(at);
      if (!stat.isDirectory() || stat.isSymbolicLink() || stat.uid !== 0 || (stat.mode & 0o022)) fail('ADMISSION_ROOT_UNSAFE');
      if (at === '/') return;
    }
  }
  function validate(value) {
    if (!value || Object.keys(value).length !== fields.length || fields.some(key => !Object.hasOwn(value, key))
      || value.version !== 1 || !PHASES.has(value.phase)
      || (value.previousActive !== null && !validServices(value.previousActive))
      || (value.phase === 'open' && value.previousActive !== null)
      || (value.phase === 'verified' ? !exactSha(value.verifiedRevision) || value.verifiedRevision !== value.target : value.verifiedRevision !== null)
      || (value.phase === 'open' ? value.operationId !== null || value.target !== null
        : !operation(value.operationId) || !exactSha(value.target))) fail('ADMISSION_STATE_INVALID');
    if (value.consumerDigest !== consumerDigest) fail('CONSUMER_CONFIG_CHANGED');
    return value;
  }
  async function read({ missing = false } = {}) {
    await protect();
    let file;
    try { file = await open(pathname, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK); }
    catch (error) { if (error.code === 'ENOENT' && missing) return null; fail(error.code === 'ENOENT' ? 'ADMISSION_STATE_MISSING' : 'ADMISSION_STATE_UNREADABLE'); }
    try {
      const stat = await file.stat();
      if (!stat.isFile() || stat.nlink !== 1 || stat.size > ADMISSION_STATE_BYTES || (stat.mode & 0o077)
        || (protectedRoot && stat.uid !== 0)) fail('ADMISSION_STATE_UNSAFE');
      let value;
      try { value = parseConsumerJson(await file.readFile('utf8')); } catch { fail('ADMISSION_STATE_INVALID'); }
      return validate(value);
    } finally { await file.close(); }
  }
  async function write(value) {
    validate(value); await protect();
    const temporary = `${pathname}.tmp-${randomUUID()}`;
    const file = await open(temporary, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | constants.O_NOFOLLOW, 0o600);
    try { await file.writeFile(JSON.stringify(value) + '\n'); await file.sync(); } finally { await file.close(); }
    await rename(temporary, pathname);
    const directory = await open(root, constants.O_RDONLY | constants.O_DIRECTORY | constants.O_NOFOLLOW);
    try { await directory.sync(); } finally { await directory.close(); }
    return value;
  }
  function bound(state, operationId) {
    if (!operation(operationId) || state.phase === 'open' || state.operationId !== operationId) fail('ADMISSION_OPERATION_MISMATCH');
    return state;
  }
  function terminalMatches(record, execution) {
    return record.outcome && execution?.outcome
      && ['BLOCKED', 'IMPLEMENTED_PENDING_FRESH_REVIEW'].includes(record.outcome.status) && positive(record.outcome.outcomeId)
      && ['status', 'head', 'prNumber', 'outcomeId'].every(key => record.outcome[key] === execution.outcome[key]);
  }
  function prCreationResolved(record) {
    if (record.prIntent === undefined || record.prIntent === null || record.prIntent === false) return true;
    if (record.prIntent !== true) return false;
    if (Object.hasOwn(record, 'prNumber')) return positive(record.prNumber) && record.prNumber === record.outcome?.prNumber;
    // Earlier Writer releases retained prIntent after creation and recorded
    // the observed PR only in the terminal Outcome. Matching terminal journal
    // evidence below, plus the exact published head, resolves that old receipt
    // without changing it or interpreting a pending current intent as complete.
    const outcome = record.outcome;
    return !Object.hasOwn(record, 'controllerLifecycle') && record.envelope.target === 'issue'
      && positive(outcome?.prNumber) && exactSha(outcome.head) && record.publishedHead === outcome.head
      && (outcome.status === 'BLOCKED' ? record.finalHead === null : record.finalHead === outcome.head);
  }
  async function contained(record) {
    const e = record.envelope;
    const saved = await journal.get(e.runId);
    if (!saved || saved.version !== VERSION || digest(saved.envelope) !== digest(e)) return null;
    if (!terminalMatches(record, saved) || record.publicationIntent || !prCreationResolved(record) || record.commentIntent) return null;
    if (saved.execution === null) return { child: 'not_started', containment: 'not_required' };
    const execution = saved.execution;
    if (execution?.reserved !== true || execution.returned !== true || !['started', 'not_started'].includes(execution.child)
      || !(execution.containment === 'reaped' || (execution.child === 'not_started' && execution.containment === 'not_required'))) return null;
    return { child: execution.child, containment: execution.containment };
  }
  function validRecord(record) {
    const e = record?.envelope;
    if (!e || e.version !== VERSION || !positive(e.runId) || !['auto', 'manual'].includes(e.route)
      || e.consumerDigest !== consumerDigest) fail('ADMISSION_ATTEMPT_INVALID');
    return e;
  }
  async function inventory() {
    const active = []; const unknown = [];
    for (const record of await store.all()) {
      const e = validRecord(record);
      if (e.route !== 'auto' || record.admissionBlock) continue;
      const lifecycle = record.controllerLifecycle;
      if (lifecycle) {
        if (lifecycle.version !== 1 || !['active', 'complete'].includes(lifecycle.status)) fail('ADMISSION_ATTEMPT_INVALID');
        if (lifecycle.status === 'complete') {
          if (!['started', 'not_started'].includes(lifecycle.child)
            || !(lifecycle.containment === 'reaped' || (lifecycle.child === 'not_started' && lifecycle.containment === 'not_required'))
            || !record.outcome || record.publicationIntent || (record.prIntent && !positive(record.prNumber)) || record.commentIntent) unknown.push(e.runId);
          continue;
        }
        // A terminal record with unknown containment or external mutation is
        // an immediate boundary. A live controller is allowed bounded drain.
        if (record.outcome && !await contained(record)) unknown.push(e.runId);
        else active.push(e.runId);
      } else if (!await contained(record)) {
        // Earlier releases did not record the full controller lifecycle. Only
        // their existing matching terminal journal can establish completion.
        unknown.push(e.runId);
      }
    }
    return { active: active.sort((a, b) => a - b), unknown: unknown.sort((a, b) => a - b) };
  }
  return {
    async initialize() {
      const existing = await read({ missing: true });
      return existing ?? write({ version: 1, consumerDigest, phase: 'open', operationId: null, target: null, previousActive: null, verifiedRevision: null });
    },
    read,
    async assertOpen() { if ((await read()).phase !== 'open') fail('ADMISSION_QUIESCED'); },
    async reserve() { await this.assertOpen(); return { version: 1, status: 'active' }; },
    async quiesce({ operationId, target }) {
      if (!operation(operationId) || !exactSha(target)) fail('ADMISSION_OPERATION_INVALID');
      const state = await read();
      if (state.phase !== 'open') {
        bound(state, operationId);
        if (state.target !== target) fail('ADMISSION_TARGET_MISMATCH');
        return state;
      }
      return write({ ...state, phase: 'quiesced', operationId, target, previousActive: null });
    },
    async status({ operationId } = {}) {
      const state = await read(); if (operationId !== undefined) bound(state, operationId);
      return { ...state, ...await inventory() };
    },
    async drained({ operationId }) {
      const state = bound(await read(), operationId);
      if (!['quiesced', 'drained'].includes(state.phase)) fail('ADMISSION_PHASE_INVALID');
      const pending = await inventory();
      if (pending.unknown.length) fail('ADMISSION_DRAIN_UNKNOWN');
      if (pending.active.length) return { ...state, ...pending, drained: false };
      return { ...await write({ ...state, phase: 'drained' }), ...pending, drained: true };
    },
    async phase({ operationId, phase, revision }) {
      const state = bound(await read(), operationId);
      if (phase === 'verified' && !exactSha(revision)) fail('ADMISSION_VERIFIED_REVISION_REQUIRED');
      if (phase === 'verified' && revision !== state.target) fail('ADMISSION_TARGET_MISMATCH');
      if (phase !== 'verified' && revision !== undefined) fail('ADMISSION_OPERATION_INVALID');
      if (phase === state.phase) {
        if (phase === 'verified' && revision !== state.verifiedRevision) fail('ADMISSION_TARGET_MISMATCH');
        return state;
      }
      if (!(phase === 'applying' && ['drained', 'recovery-required'].includes(state.phase))
        && !(phase === 'verified' && ['applying', 'drained'].includes(state.phase))
        && !(phase === 'recovery-required' && state.phase !== 'open')) fail('ADMISSION_PHASE_INVALID');
      return write({ ...state, phase, verifiedRevision: phase === 'verified' ? revision : null });
    },
    async snapshot({ operationId, services }) {
      const state = bound(await read(), operationId);
      if (!validServices(services)) fail('ADMISSION_SNAPSHOT_INVALID');
      // Recovery may observe a service that a failed activation stopped. Keep
      // the original intent instead of treating that failure as intentional.
      if (state.previousActive !== null) return state;
      if (state.phase !== 'applying') fail('ADMISSION_PHASE_INVALID');
      return write({ ...state, previousActive: structuredClone(services) });
    },
    async recoveryTarget({ operationId, target }) {
      const state = bound(await read(), operationId);
      if (state.phase !== 'recovery-required') fail('ADMISSION_PHASE_INVALID');
      if (!exactSha(target)) fail('ADMISSION_OPERATION_INVALID');
      const pending = await inventory();
      if (pending.active.length || pending.unknown.length) fail('ADMISSION_NOT_DRAINED');
      // Only an explicitly authorized root recovery may select an accepted
      // rollback revision. Preserve the operation's original activity intent.
      return state.target === target ? state : write({ ...state, target });
    },
    async resume({ operationId }) {
      const state = bound(await read(), operationId);
      if (state.phase !== 'verified') fail('ADMISSION_VERIFICATION_REQUIRED');
      const pending = await inventory();
      if (pending.active.length || pending.unknown.length) fail('ADMISSION_NOT_DRAINED');
      return write({ ...state, phase: 'open', operationId: null, target: null, previousActive: null, verifiedRevision: null });
    },
    async complete({ runId, attemptId }) {
      await protect();
      if (!positive(runId)) fail('RUN_ID_INVALID');
      const record = await store.get(runId); const e = validRecord(record);
      if (e.attemptId !== attemptId || e.route !== 'auto' || record.admissionBlock) fail('ATTEMPT_NOT_ADMITTED');
      const lifecycle = record.controllerLifecycle;
      if (lifecycle && (lifecycle.version !== 1 || !['active', 'complete'].includes(lifecycle.status))) fail('ADMISSION_ATTEMPT_INVALID');
      if (lifecycle?.status === 'complete') return { complete: true };
      const evidence = await contained(record);
      if (!evidence) fail('ADMISSION_COMPLETION_UNKNOWN');
      // This older receipt is already complete through its matching terminal
      // journal. Adding only lifecycle metadata would lose the legacy binding
      // on the next inventory; preserve both trusted receipts unchanged.
      if (!Object.hasOwn(record, 'controllerLifecycle') && record.prIntent === true && !Object.hasOwn(record, 'prNumber')) return { complete: true };
      record.controllerLifecycle = { version: 1, status: 'complete', ...evidence };
      await store.put(runId, record);
      return { complete: true };
    }
  };
}
