import { CONSUMER, CONSUMER_DIGEST } from '../../consumer/consumer.mjs';
import { assertRootConsumer, parseConsumerJson } from '../../consumer/consumer-config.mjs';
import { realpathSync } from 'node:fs';
import { lstat } from 'node:fs/promises';
import { checkoutPath } from './attempt-runtime.mjs';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';
import { execFile } from 'node:child_process';
import { performance } from 'node:perf_hooks';
import { setTimeout } from 'node:timers/promises';
import { createAttemptStore, createPublicationStore } from './attempt-store.mjs';
import { createAdmissionControl, terminalAdmissionOutcome, activeControllerReservation, preAdmissionRefusalHasNoPendingEffects, ADMISSION_STATE_BYTES } from './admission-control.mjs';
import { createSlotJournal } from './slot-journal.mjs';
import { manualAttemptHasNoPendingEffects, attemptHasPendingPublicationEffects } from './execution-effects.mjs';
import { fail } from './execution-contract.mjs';
import { traceConsumerTransition } from './transition-timing.mjs';
import { assertPredispatchTargetCompatible } from './predispatch-target-compatibility.mjs';

const exec = promisify(execFile);
const checkoutAbsent = async envelope => {
  try { await lstat(checkoutPath(envelope)); return false; }
  catch (error) { if (error.code === 'ENOENT') return true; throw error; }
};
const commands = {
  initialize: [], status: ['operation?'], quiesce: ['operation', 'target', 'target-source?'],
  drain: ['operation', 'timeout'], 'drain-check': ['operation'],
  phase: ['operation', 'phase', 'revision?', 'target-source?'], resume: ['operation', 'target-source?'], snapshot: ['operation'],
  'recovery-target': ['operation', 'target', 'target-source?'],
  'consumer-transition-preflight': ['desired-digest'],
  'consumer-transition-check': ['operation', 'revision'],
  'consumer-transition': ['operation', 'previous-digest', 'revision']
};
export function parseAdmissionArguments(args) {
  const [command, ...values] = args; const allowed = commands[command];
  if (!allowed || values.length % 2) fail('ADMISSION_ARGUMENTS_INVALID');
  const options = {};
  for (let i = 0; i < values.length; i += 2) {
    const key = values[i].replace(/^--/, '');
    const storedKey = key === 'target-source' ? 'targetSource' : key === 'operation' ? 'operationId' : key === 'previous-digest' ? 'previousDigest'
      : key === 'desired-digest' ? 'desiredDigest' : key;
    if (values[i] !== `--${key}` || !allowed.some(name => name.replace(/\?$/, '') === key) || Object.hasOwn(options, storedKey)) fail('ADMISSION_ARGUMENTS_INVALID');
    options[storedKey] = values[i + 1];
  }
  for (const name of allowed.filter(name => !name.endsWith('?'))) {
    if (options[name === 'operation' ? 'operationId' : name === 'previous-digest' ? 'previousDigest'
      : name === 'desired-digest' ? 'desiredDigest' : name] === undefined) fail('ADMISSION_ARGUMENTS_INVALID');
  }
  if (command === 'drain') {
    if (!/^[1-9][0-9]{0,3}$/.test(options.timeout) || Number(options.timeout) > 3600) fail('ADMISSION_TIMEOUT_INVALID');
    options.timeout = Number(options.timeout);
  }
  if (command === 'consumer-transition-preflight' && !/^[a-f0-9]{64}$/.test(options.desiredDigest)) fail('ADMISSION_CONFIG_INVALID');
  return { command, options };
}
// Retained runtimes own their original containment/source interpretation. This
// adds current publication-effect checks without changing that historical code.
export async function supplementOriginalInventory(inventory, records, { journal, task = null } = {}) {
  const unknown = new Set(inventory.unknown);
  for (const record of records) {
    const e = record.envelope;
    if (task !== null && e.issueNumber !== task) continue;
    if (e.route === 'manual') {
      // Original source owns original result semantics. Current source only
      // checks independent operational effects; it does not decode v3 again.
      const untouched = record.admissionBlock || e.admissionBlock
        ? await preAdmissionRefusalHasNoPendingEffects(record, { journal })
        : manualAttemptHasNoPendingEffects(record) && !await journal.get(e.runId, e.repository);
      if (untouched) unknown.delete(e.runId);
      else if (unknown.has(e.runId) || !terminalAdmissionOutcome(record)
        || attemptHasPendingPublicationEffects(record) || record.handoffComplete === false
        || ['controllerLifecycle', 'prepublicationRecovery', 'publicationRecoveries', 'collection', 'execution']
          .some(key => Boolean(record[key]))
        || await journal.get(e.runId, e.repository)) unknown.add(e.runId);
    } else if (e.route === 'auto' && (attemptHasPendingPublicationEffects(record) && !activeControllerReservation(record)
      || record.controllerLifecycle?.status === 'complete' && !terminalAdmissionOutcome(record))) unknown.add(e.runId);
  }
  return { ...inventory, unknown: [...unknown].sort((a, b) => a - b) };
}

export async function invokeTargetCheckedAdmission(admission, name, args, records, proofOptions = {}) {
  if (['quiesce', 'recoveryTarget', 'resume'].includes(name)
    || name === 'phase' && ['applying', 'verified'].includes(args[0]?.phase)) {
    const target = args[0]?.target ?? (await admission.read()).target;
    await assertPredispatchTargetCompatible({ records: await records(), target,
      sourceRoot: args[0]?.targetSource ?? null, ...proofOptions });
  }
  return admission[name](...args);
}
export function installedAdmissionControl() {
  // Keep the synchronous factory interface used by the protected Writer. Each
  // async action revalidates the protected migration context and whole stores;
  // a previously observed receipt cannot hide later changes before admission.
  const methods = ['initialize', 'read', 'assertOpen', 'assertTaskComplete', 'assertSlotComplete',
    'reserve', 'quiesce', 'status', 'drained', 'phase', 'snapshot', 'recoveryTarget', 'resume', 'complete',
    'preflightConsumerTransition', 'checkConsumerTransition', 'transitionConsumer'];
  return Object.fromEntries(methods.map(name => [name, async (...args) => {
    const invoke = (admission, records) => invokeTargetCheckedAdmission(admission, name, args, records);
    const { loadSerialPoolCompatibility, verifySerialPoolCompatibility, createCompatibilityStore, invokeOriginalReader } =
      await import('./serial-pool-compatibility.mjs');
    const compatibility = await loadSerialPoolCompatibility({ consumer: CONSUMER,
      ...(name === 'transitionConsumer' ? { consumerTransition: args[0] } : {}) });
    if (!compatibility) {
      const originalStore = createPublicationStore(`${CONSUMER.paths.claimRoot}/publication-v2`);
      const admission = createAdmissionControl({ root: CONSUMER.paths.claimRoot, consumerDigest: CONSUMER_DIGEST,
        store: originalStore, journal: createSlotJournal(originalStore), checkoutAbsent });
      return invoke(admission, () => originalStore.all());
    }
    const originalStore = createAttemptStore(compatibility.original.storeRoot, { repository: compatibility.receipt.repository });
    const currentStore = createPublicationStore(compatibility.current.storeRoot);
    const composite = createCompatibilityStore({ compatibility, currentStore, originalStore });
    let records;
    const compositeRecords = () => records ??= composite.all();
    const currentJournal = createSlotJournal(currentStore);
    const originalJournalRoot = compatibility.root === '/' ? compatibility.originalConsumer.paths.attemptRoot
      : `${compatibility.root}${compatibility.originalConsumer.paths.attemptRoot}`;
    const originalJournal = createAttemptStore(originalJournalRoot, { repository: compatibility.receipt.repository });
    const admission = createAdmissionControl({ root: CONSUMER.paths.claimRoot, consumerDigest: CONSUMER_DIGEST,
      stateName: 'admission-pool-v1.json', store: currentStore, journal: currentJournal, checkoutAbsent,
      supplementalVerify: async () => {
        await verifySerialPoolCompatibility(compatibility, { privateChecks: true });
      },
      supplementalInventory: async ({ task, slot, resourceOnly }) => {
        const records = task === null && slot === null ? await compositeRecords() : null;
        const inventory = await invokeOriginalReader(compatibility, { operation: 'inventory', task, slot, resourceOnly });
        if (task !== null && CONSUMER.repository !== compatibility.receipt.repository) return { active: [], unknown: [] };
        if (resourceOnly) return inventory;
        const originalRecords = (records ?? await compositeRecords()).filter(record =>
          record.envelope.repository === compatibility.receipt.repository
          && compatibility.receipt.original.runs.some(run => run.runId === record.envelope.runId));
        return supplementOriginalInventory(inventory, originalRecords, { journal: originalJournal, task });
      } });
    return invoke(admission, compositeRecords);
  }]));
}
export async function readAdmissionSnapshot(input = process.stdin) {
  let size = 0; const chunks = [];
  for await (const value of input) {
    const chunk = Buffer.from(value); size += chunk.length;
    if (size > ADMISSION_STATE_BYTES) fail('ADMISSION_SNAPSHOT_TOO_LARGE');
    chunks.push(chunk);
  }
  try { return parseConsumerJson(Buffer.concat(chunks).toString('utf8')); }
  catch { fail('ADMISSION_SNAPSHOT_INVALID'); }
}
export async function drainAdmission({ operationId, timeout }, { snapshot, wait = setTimeout,
  now = () => performance.now(), reportProgress = () => {} } = {}) {
  const started = now(); const deadline = started + timeout * 1000;
  let nextProgress = started + 30000;
  while (true) {
    const value = await snapshot(operationId, Math.max(1, Math.ceil(deadline - now())));
    if (value.drained === true) return value;
    if (now() >= nextProgress) {
      const count = values => Array.isArray(values) && values.length <= 10000 ? values.length : null;
      reportProgress({ phase: 'drain', active: count(value.active), unknown: count(value.unknown),
        elapsedSeconds: Math.min(timeout, Math.max(0, Math.floor((now() - started) / 1000))) });
      nextProgress = now() + 30000;
    }
    if (now() >= deadline) fail('ADMISSION_DRAIN_TIMEOUT');
    await wait(Math.min(1000, deadline - now()));
  }
}
export async function readDrainSnapshot(operationId, remaining, { execute = exec } = {}) {
  try {
    const result = await execute('/usr/bin/flock', ['-w', '1', `${CONSUMER.paths.claimRoot}/publication-v2.lock`,
      '/usr/bin/node', fileURLToPath(import.meta.url), 'drain-check', '--operation', operationId],
    { env: { RELAY_CONSUMER_CONFIG: process.env.RELAY_CONSUMER_CONFIG, RELAY_REPOSITORY: CONSUMER.repository, PATH: '/usr/bin:/bin', LANG: 'C', LC_ALL: 'C' },
      // A retained-history inventory can exceed five seconds. Bound the full
      // locked observation by the remaining drain deadline, not a shorter poll.
      timeout: remaining, maxBuffer: 1024 * 1024 });
    return JSON.parse(result.stdout);
  } catch (error) {
    let payload;
    try { payload = JSON.parse(error.stderr); } catch { /* flock contention has no JSON */ }
    if (payload?.code) fail(payload.code);
    if (error.code === 1 && !error.stdout && !error.stderr) return { drained: false };
    fail('ADMISSION_DRAIN_STATUS_UNAVAILABLE');
  }
}
export async function main(args = process.argv.slice(2)) {
  if (process.getuid?.() !== 0) fail('FIXED_ROOT_ADMISSION_REQUIRED');
  assertRootConsumer(process.env.RELAY_CONSUMER_CONFIG);
  const { command, options } = parseAdmissionArguments(args);
  if (command === 'drain') {
    // Each snapshot has the same lock as admission and final Writer release.
    // Never hold that lock during the wait: admitted controllers must finish.
    return drainAdmission(options, {
      reportProgress: value => process.stderr.write(`ADMISSION_DRAIN_PROGRESS phase=${value.phase} active=${value.active ?? 'UNAVAILABLE'} unknown=${value.unknown ?? 'UNAVAILABLE'} elapsedSeconds=${value.elapsedSeconds}\n`),
      snapshot: readDrainSnapshot });
  }
  const admission = installedAdmissionControl();
  // Preserve the existing one-envelope stderr contract for ordinary helper
  // callers. The trusted publisher opts into the bounded timing stream.
  const trace = action => process.env.RELAY_TRANSITION_TRACE === '1' ? traceConsumerTransition(action) : action();
  if (command === 'drain-check') return admission.drained(options);
  if (command === 'snapshot') return admission.snapshot({ ...options, services: await readAdmissionSnapshot() });
  if (command === 'recovery-target') return admission.recoveryTarget(options);
  if (command === 'consumer-transition-preflight') return trace(() => admission.preflightConsumerTransition(options));
  if (command === 'consumer-transition-check') return trace(() => admission.checkConsumerTransition({ operationId: options.operationId, target: options.revision }));
  if (command === 'consumer-transition') return trace(() => admission.transitionConsumer({
    operationId: options.operationId, previousDigest: options.previousDigest, target: options.revision }));
  return admission[command](options);
}
function isMain() { try { return realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url)); } catch { return false; } }
if (isMain()) main().then(value => process.stdout.write(JSON.stringify(value) + '\n')).catch(error => {
  process.stderr.write(JSON.stringify({ code: /^[A-Z][A-Z0-9_]{0,79}$/.test(error?.code ?? '') ? error.code : 'ADMISSION_FAILED' }) + '\n');
  process.exitCode = 1;
});
