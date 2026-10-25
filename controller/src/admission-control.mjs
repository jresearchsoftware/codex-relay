import { constants } from 'node:fs';
import { open, lstat, rename } from 'node:fs/promises';
import { dirname, join, isAbsolute } from 'node:path';
import { randomUUID } from 'node:crypto';
import { parseConsumerJson } from '../../consumer/consumer-config.mjs';
import { CONSUMER } from '../../consumer/consumer.mjs';
import { digest, exactSha, fail, positive, VERSION, REPOSITORY } from './execution-contract.mjs';
import { admissionBinding, canonicalAuthorityJson, validateAuthorityRecord } from '../../contracts/src/github-authority.mjs';

export const ADMISSION_STATE_BYTES = 4096;
const PHASES = new Set(['open', 'quiesced', 'drained', 'applying', 'verified', 'recovery-required']);
const operation = value => typeof value === 'string' && /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(value);
const fields = ['version', 'consumerDigest', 'phase', 'operationId', 'target', 'previousActive', 'verifiedRevision'];
const configDigest = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
function publishedTerminal(record, recoveredHandoff = false) {
  const outcome = record?.outcome;
  return outcome && ['BLOCKED', 'IMPLEMENTED_PENDING_FRESH_REVIEW'].includes(outcome.status)
    && positive(outcome.outcomeId) && configDigest(outcome.bodySha256)
    && (outcome.head === null || exactSha(outcome.head))
    && (outcome.prNumber === null || positive(outcome.prNumber))
    && !record.publicationIntent && !record.commentIntent && !record.lifecycleIntent
    && (recoveredHandoff || record.handoffComplete !== false);
}

// Manual execution deliberately has no worker journal. Its protected Writer
// submission and native publication receipts bind the original admission instead.
export function manualAdmissionComplete(record) {
  const e = record?.envelope;
  if (e?.route !== 'manual' || !publishedTerminal(record) || record.outcome.manual !== true
    || record.prIntent && record.prNumber !== record.outcome.prNumber) return false;
  const result = record.manualSubmission?.publishedResult;
  if (!result) return e.request?.schema_version === '3.0' && e.request.kind === 'task-request'
    && positive(record.manualResultAuthorization?.id) && configDigest(record.manualResultAuthorization.sha256)
    && configDigest(e.requestReference?.sha256);
  try {
    validateAuthorityRecord(result, { repository: e.repository, task: e.issueNumber });
    if (result.kind !== 'outcome' || result.attempt !== e.attemptId
      || !configDigest(record.manualSubmission.sha256)
      || canonicalAuthorityJson(result.parent) !== canonicalAuthorityJson(record.manualSubmission.parent)
      || record.outcome.prNumber !== (result.parent.kind === 'pull_request' ? result.parent.number : null)
      || record.outcome.head !== (exactSha(result.result.revision) ? result.result.revision : null)
      || record.outcome.status !== (result.status === 'implemented' ? 'IMPLEMENTED_PENDING_FRESH_REVIEW' : 'BLOCKED')) return false;
    if (result.schema_version === '4.0') return result.step === e.step
      && canonicalAuthorityJson(result.authority) === canonicalAuthorityJson(e.request.authority)
      && canonicalAuthorityJson(result.admission) === canonicalAuthorityJson(admissionBinding(e.request));
    return canonicalAuthorityJson(result.request) === canonicalAuthorityJson(e.requestReference);
  } catch { return false; }
}

export async function completedAdmissionRecord(record, journal) {
  const e = record?.envelope;
  if (!e || e.version !== VERSION || !configDigest(e.consumerDigest) || !positive(e.runId)) return false;
  if (e.route === 'manual') return manualAdmissionComplete(record);
  if (e.route !== 'auto' || !publishedTerminal(record, Boolean(record.prepublicationRecovery))
    || record.controllerLifecycle?.status === 'active') return false;
  const lifecycle = record.controllerLifecycle;
  if (lifecycle && (lifecycle.version !== 1 || lifecycle.status !== 'complete'
    || !['started', 'not_started'].includes(lifecycle.child)
    || !(lifecycle.containment === 'reaped'
      || lifecycle.child === 'not_started' && lifecycle.containment === 'not_required'))) return false;
  if (record.admissionBlock && !lifecycle && record.outcome.status === 'BLOCKED') return true;
  if (record.prepublicationRecovery) {
    const recovery = record.prepublicationRecovery;
    const saved = await journal.get(e.runId, e.repository);
    return Boolean(saved && saved.version === VERSION && digest(saved.envelope) === digest(e)
      && recovery.complete === true && recovery.handoffProven === true
      && recovery.binding?.terminal?.journalDigest === digest(saved)
      && recovery.binding.terminal.controllerDigest === digest(record.controllerLifecycle ?? null)
      && recovery.publication?.status === 'PUBLISHED'
      && recovery.publication.publishedHead === recovery.binding.head && exactSha(recovery.binding.head)
      && recovery.collection?.head === recovery.binding.head && recovery.collection.clean === true
      && recovery.outcome?.status === 'IMPLEMENTED_PENDING_FRESH_REVIEW'
      && recovery.outcome.head === recovery.binding.head && positive(recovery.outcome.outcomeId)
      && positive(recovery.outcome.prNumber) && record.prNumber === recovery.outcome.prNumber
      && !record.prIntent);
  }
  if (record.prIntent && !(positive(record.prNumber) && record.prNumber === record.outcome.prNumber)
    && !(record.prIntent === true && !Object.hasOwn(record, 'controllerLifecycle')
      && e.target === 'issue' && positive(record.outcome.prNumber) && exactSha(record.outcome.head)
      && record.publishedHead === record.outcome.head
      && (record.outcome.status === 'BLOCKED' ? record.finalHead === null : record.finalHead === record.outcome.head))) return false;
  const saved = await journal.get(e.runId, e.repository);
  if (!saved || saved.version !== VERSION || digest(saved.envelope) !== digest(e) || !saved.outcome
    || !['status', 'head', 'prNumber', 'outcomeId'].every(key => record.outcome[key] === saved.outcome[key])) return false;
  if (saved.execution === null) return true;
  const execution = saved.execution;
  return execution?.reserved === true && execution.returned === true
    && ['started', 'not_started'].includes(execution.child)
    && (execution.containment === 'reaped' || execution.child === 'not_started' && execution.containment === 'not_required');
}
function validServices(value) {
  // The primary service keeps the original `general` key. Additional activity
  // intent is complete only for this immutable installation topology; caller
  // JSON cannot invent or omit a runner that a lifecycle operation will touch.
  const names = ['reviewer', 'production', 'general',
    ...(CONSUMER.executionSlots ?? []).filter(slot => slot.id !== 'primary').map(slot => `slot-${slot.id}`)];
  if (value && Object.hasOwn(value, 'manualOutcome')) names.push('manualOutcome');
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
export function createAdmissionControl({ root, consumerDigest, store, journal, protectedRoot = true,
  stateName = 'admission-v1.json', supplementalInventory = null, supplementalVerify = null,
  supplementalManualInventory = null }) {
  if (!isAbsolute(root) || !/^[a-f0-9]{64}$/.test(consumerDigest ?? '')
    || !['admission-v1.json', 'admission-pool-v1.json'].includes(stateName)
    || (supplementalInventory !== null && typeof supplementalInventory !== 'function')
    || (supplementalVerify !== null && typeof supplementalVerify !== 'function')
    || (supplementalManualInventory !== null && typeof supplementalManualInventory !== 'function')) fail('ADMISSION_CONFIG_INVALID');
  const pathname = join(root, stateName);
  async function protect() {
    if (!protectedRoot) return;
    for (let at = root; ; at = dirname(at)) {
      const stat = await lstat(at);
      if (!stat.isDirectory() || stat.isSymbolicLink() || stat.uid !== 0 || (stat.mode & 0o022)) fail('ADMISSION_ROOT_UNSAFE');
      if (at === '/') return;
    }
  }
  function validate(value, previousDigest = null) {
    if (!value || Object.keys(value).length !== fields.length || fields.some(key => !Object.hasOwn(value, key))
      || value.version !== 1 || !PHASES.has(value.phase)
      || (value.previousActive !== null && !validServices(value.previousActive))
      || (value.phase === 'open' && value.previousActive !== null)
      || (value.phase === 'verified' ? !exactSha(value.verifiedRevision) || value.verifiedRevision !== value.target : value.verifiedRevision !== null)
      || (value.phase === 'open' ? value.operationId !== null || value.target !== null
        : !operation(value.operationId) || !exactSha(value.target))) fail('ADMISSION_STATE_INVALID');
    if (!configDigest(value.consumerDigest) || value.consumerDigest !== consumerDigest
      && value.consumerDigest !== previousDigest) fail('CONSUMER_CONFIG_CHANGED');
    return value;
  }
  async function read({ missing = false, previousDigest = null } = {}) {
    // The migration owner/source/gate binding is global. Historical execution
    // and publication state are inspected only for the resource being used,
    // or in full for a lifecycle drain.
    if (supplementalVerify) await supplementalVerify();
    else if (supplementalInventory) await inventory();
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
      return validate(value, previousDigest);
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
    const saved = await journal.get(e.runId, e.repository);
    if (!saved || saved.version !== VERSION || digest(saved.envelope) !== digest(e)) return null;
    if (!terminalMatches(record, saved) || record.publicationIntent || !prCreationResolved(record) || record.commentIntent) return null;
    if (saved.execution === null) return { child: 'not_started', containment: 'not_required' };
    const execution = saved.execution;
    if (execution?.reserved !== true || execution.returned !== true || !['started', 'not_started'].includes(execution.child)
      || !(execution.containment === 'reaped' || (execution.child === 'not_started' && execution.containment === 'not_required'))) return null;
    return { child: execution.child, containment: execution.containment };
  }
  async function resourceReleased(record) {
    const lifecycle = record.controllerLifecycle;
    if (lifecycle?.version === 1 && lifecycle.status === 'complete'
      && ['started', 'not_started'].includes(lifecycle.child)
      && (lifecycle.containment === 'reaped'
        || (lifecycle.child === 'not_started' && lifecycle.containment === 'not_required'))) return true;
    const e = record.envelope;
    const saved = await journal.get(e.runId, e.repository);
    if (!saved || saved.version !== VERSION || digest(saved.envelope) !== digest(e)) return false;
    const execution = saved.execution;
    // The collector persists this receipt before Writer publication. Work
    // remains in the original attempt checkout; publication uncertainty owns
    // its exact effect, rather than the physical runner slot.
    if (execution?.reserved === true && execution.returned === true
      && ['started', 'not_started'].includes(execution.child)
      && (execution.containment === 'reaped'
        || (execution.child === 'not_started' && execution.containment === 'not_required'))
      && saved.collection?.preserved === true && exactSha(saved.collection.head)
      && typeof saved.collection.clean === 'boolean') return true;
    // Retained receipts have no new preservation field. Keep their original
    // strong terminal evidence readable without backfilling historical bytes.
    return Boolean(await contained(record));
  }
  function validRecord(record) {
    const e = record?.envelope;
    if (!e || e.version !== VERSION || !positive(e.runId) || !['auto', 'manual'].includes(e.route)
      || !configDigest(e.consumerDigest)) throw Object.assign(new Error('ADMISSION_ATTEMPT_INVALID'), {
      code: 'ADMISSION_ATTEMPT_INVALID', details: { conflictingRunId: e?.runId, repository: e?.repository,
        resource: e?.executionSlot ?? 'primary' } });
    return e;
  }
  async function historicalComplete(record) {
    // A completed lifecycle flag alone cannot reinterpret a different config's
    // execution. Compare the original immutable envelope and terminal journal.
    return completedAdmissionRecord(record, journal);
  }
  async function currentInventory(task = null, slot = null, resourceOnly = false, includeManual = false) {
    const active = []; const unknown = [];
    const rows = store.scan ? await store.scan()
      : (await store.all()).map(record => ({ runId: record?.envelope?.runId, repository: record?.envelope?.repository, record }));
    for (const row of rows) {
      const record = row.record; const identity = record?.envelope ?? row.envelope;
      if (task !== null && row.repository !== undefined && row.repository !== REPOSITORY) continue;
      if (identity && task !== null && identity.issueNumber !== task) continue;
      if (identity && slot !== null && (identity.executionSlot ?? 'primary') !== slot) continue;
      if (row.error || !identity) {
        throw Object.assign(new Error('ADMISSION_ATTEMPT_INVALID'), { code: 'ADMISSION_ATTEMPT_INVALID',
          details: { conflictingRunId: row.runId, repository: row.repository, resource: slot, cause: row.error ?? 'ATTEMPT_ENVELOPE_MISSING' } });
      }
      // A handoff is not evidence of physical runner occupation.
      if (resourceOnly && identity.route === 'manual') continue;
      const e = validRecord(record);
      if (e.consumerDigest !== consumerDigest) {
        if (await historicalComplete(record)) continue;
        fail('ADMISSION_ATTEMPT_INVALID');
      }
      if (includeManual && e.route === 'manual') {
        if (!manualAdmissionComplete(record)) unknown.push(e.runId);
        continue;
      }
      if (includeManual && e.route === 'auto' && !await historicalComplete(record)) {
        unknown.push(e.runId);
        continue;
      }
      if (e.route !== 'auto' || record.admissionBlock) continue;
      if (resourceOnly) {
        let released;
        try { released = await resourceReleased(record); }
        catch (error) {
          throw Object.assign(new Error('ADMISSION_RESOURCE_EVIDENCE_UNREADABLE'), { code: 'ADMISSION_RESOURCE_EVIDENCE_UNREADABLE',
            details: { conflictingRunId: e.runId, repository: e.repository, resource: slot,
              cause: /^[A-Z][A-Z0-9_]{0,100}$/.test(error.code ?? '') ? error.code : 'JOURNAL_UNREADABLE' } });
        }
        if (!released) {
          if (record.controllerLifecycle?.version === 1 && record.controllerLifecycle.status === 'active' && !record.outcome) active.push(e.runId);
          else unknown.push(e.runId);
        }
        continue;
      }
      const recovery = record.prepublicationRecovery;
      if (recovery) {
        const saved = await journal.get(e.runId, e.repository);
        // The historic BLOCKED controller receipt cannot hide a pending or
        // uncertain new publication. Completion has its own exact evidence.
        if (recovery.complete !== true || recovery.handoffProven !== true
          || recovery.binding?.terminal?.journalDigest !== digest(saved)
          || recovery.binding.terminal.controllerDigest !== digest(record.controllerLifecycle ?? null)
          || recovery.publication?.status !== 'PUBLISHED'
          || recovery.publication.publishedHead !== recovery.binding.head
          || recovery.collection?.head !== recovery.binding.head || recovery.collection.clean !== true
          || recovery.outcome?.status !== 'IMPLEMENTED_PENDING_FRESH_REVIEW'
          || recovery.outcome.head !== recovery.binding.head || !positive(recovery.outcome.outcomeId)
          || !positive(recovery.outcome.prNumber) || record.prNumber !== recovery.outcome.prNumber
          || record.prIntent || record.commentIntent || record.lifecycleIntent) unknown.push(e.runId);
        continue;
      }
      const lifecycle = record.controllerLifecycle;
      if (lifecycle) {
        if (lifecycle.version !== 1 || !['active', 'complete'].includes(lifecycle.status)) fail('ADMISSION_ATTEMPT_INVALID');
        if (lifecycle.status === 'complete') {
          if (!['started', 'not_started'].includes(lifecycle.child)
            || !(lifecycle.containment === 'reaped' || (lifecycle.child === 'not_started' && lifecycle.containment === 'not_required'))
            || !record.outcome || record.publicationIntent || (record.prIntent && !positive(record.prNumber)) || record.commentIntent
            || record.lifecycleIntent || record.handoffComplete === false) unknown.push(e.runId);
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
  async function inventory(task = null, slot = null, resourceOnly = false, includeManual = false) {
    const current = await currentInventory(task, slot, resourceOnly, includeManual);
    if (includeManual && supplementalManualInventory) {
      const manual = await supplementalManualInventory();
      if (!Array.isArray(manual) || !manual.every(positive)) fail('ADMISSION_ATTEMPT_INVALID');
      current.unknown.push(...manual);
    }
    if (!supplementalInventory) return current;
    const supplemental = await supplementalInventory({ task, slot, resourceOnly });
    if (!supplemental || !['active', 'unknown'].every(key => Array.isArray(supplemental[key])
      && supplemental[key].every(positive))) fail('ADMISSION_ATTEMPT_INVALID');
    return Object.fromEntries(['active', 'unknown'].map(key =>
      [key, [...new Set([...current[key], ...supplemental[key]])].sort((a, b) => a - b)]));
  }
  return {
    async initialize() {
      const existing = await read({ missing: true });
      return existing ?? write({ version: 1, consumerDigest, phase: 'open', operationId: null, target: null, previousActive: null, verifiedRevision: null });
    },
    read,
    async assertOpen() { if ((await read()).phase !== 'open') fail('ADMISSION_QUIESCED'); },
    async assertTaskComplete(task) {
      if (!positive(task)) fail('AUTHORITY_ADMISSION_INVALID');
      const pending = await inventory(task);
      if (pending.active.length || pending.unknown.length) throw Object.assign(new Error('PRIOR_EXECUTION_UNRESOLVED'),
        { code: 'PRIOR_EXECUTION_UNRESOLVED', details: { task, ...pending } });
    },
    async assertSlotComplete(slot) {
      if (!/^[a-z][a-z0-9-]{0,31}$/.test(slot ?? '')) fail('EXECUTION_SLOT_INVALID');
      const pending = await inventory(null, slot, true);
      if (pending.active.length || pending.unknown.length) throw Object.assign(new Error('EXECUTION_SLOT_UNAVAILABLE'),
        { code: 'EXECUTION_SLOT_UNAVAILABLE', details: { resource: slot, ...pending } });
    },
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
    async checkConsumerTransition({ operationId, target }) {
      const state = bound(await read(), operationId);
      if (!exactSha(target) || state.target !== target) fail('ADMISSION_TARGET_MISMATCH');
      if (!['drained', 'applying'].includes(state.phase)) fail('ADMISSION_PHASE_INVALID');
      const pending = await inventory(null, null, false, true);
      if (pending.active.length || pending.unknown.length) fail('ADMISSION_NOT_DRAINED');
      return { operationId, target, previousDigest: state.consumerDigest };
    },
    async transitionConsumer({ operationId, previousDigest, target }) {
      if (!configDigest(previousDigest)) fail('ADMISSION_CONFIG_INVALID');
      const state = bound(await read({ previousDigest }), operationId);
      if (!exactSha(target) || state.target !== target) fail('ADMISSION_TARGET_MISMATCH');
      if (!['drained', 'applying'].includes(state.phase)) fail('ADMISSION_PHASE_INVALID');
      const pending = await inventory(null, null, false, true);
      if (pending.active.length || pending.unknown.length) fail('ADMISSION_NOT_DRAINED');
      // The caller holds the existing Writer mutex continuously from the old
      // precheck through consumer publication. Attempts and journals stay intact.
      return state.consumerDigest === consumerDigest ? state : write({ ...state, consumerDigest });
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
      if (supplementalVerify) await supplementalVerify();
      await protect();
      if (!positive(runId)) fail('RUN_ID_INVALID');
      const record = await store.get(runId); const e = validRecord(record);
      if (e.consumerDigest !== consumerDigest) fail('CONSUMER_CONFIG_CHANGED');
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
