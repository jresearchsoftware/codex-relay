import { CONSUMER, CONSUMER_DIGEST } from '../../consumer/consumer.mjs';
import { assertRootConsumer, parseConsumerJson } from '../../consumer/consumer-config.mjs';
import { realpathSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';
import { execFile } from 'node:child_process';
import { performance } from 'node:perf_hooks';
import { setTimeout } from 'node:timers/promises';
import { createAttemptStore } from './attempt-store.mjs';
import { createAdmissionControl, ADMISSION_STATE_BYTES } from './admission-control.mjs';
import { fail } from './execution-contract.mjs';

const exec = promisify(execFile);
const commands = {
  initialize: [], status: ['operation?'], quiesce: ['operation', 'target'],
  drain: ['operation', 'timeout'], 'drain-check': ['operation'],
  phase: ['operation', 'phase', 'revision?'], resume: ['operation'], snapshot: ['operation'],
  'recovery-target': ['operation', 'target']
};
export function parseAdmissionArguments(args) {
  const [command, ...values] = args; const allowed = commands[command];
  if (!allowed || values.length % 2) fail('ADMISSION_ARGUMENTS_INVALID');
  const options = {};
  for (let i = 0; i < values.length; i += 2) {
    const key = values[i].replace(/^--/, '');
    const storedKey = key === 'operation' ? 'operationId' : key;
    if (values[i] !== `--${key}` || !allowed.some(name => name.replace(/\?$/, '') === key) || Object.hasOwn(options, storedKey)) fail('ADMISSION_ARGUMENTS_INVALID');
    options[storedKey] = values[i + 1];
  }
  for (const name of allowed.filter(name => !name.endsWith('?'))) {
    if (options[name === 'operation' ? 'operationId' : name] === undefined) fail('ADMISSION_ARGUMENTS_INVALID');
  }
  if (command === 'drain') {
    if (!/^[1-9][0-9]{0,3}$/.test(options.timeout) || Number(options.timeout) > 3600) fail('ADMISSION_TIMEOUT_INVALID');
    options.timeout = Number(options.timeout);
  }
  return { command, options };
}
export function installedAdmissionControl() {
  return createAdmissionControl({ root: CONSUMER.paths.claimRoot, consumerDigest: CONSUMER_DIGEST,
    store: createAttemptStore(`${CONSUMER.paths.claimRoot}/publication-v2`),
    journal: createAttemptStore(CONSUMER.paths.attemptRoot) });
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
export async function main(args = process.argv.slice(2)) {
  if (process.getuid?.() !== 0) fail('FIXED_ROOT_ADMISSION_REQUIRED');
  assertRootConsumer(process.env.RELAY_CONSUMER_CONFIG);
  const { command, options } = parseAdmissionArguments(args);
  if (command === 'drain') {
    // Each snapshot has the same lock as admission and final Writer release.
    // Never hold that lock during the wait: admitted controllers must finish.
    return drainAdmission(options, {
      reportProgress: value => process.stderr.write(`ADMISSION_DRAIN_PROGRESS phase=${value.phase} active=${value.active ?? 'UNAVAILABLE'} unknown=${value.unknown ?? 'UNAVAILABLE'} elapsedSeconds=${value.elapsedSeconds}\n`),
      snapshot: async (operationId, remaining) => {
      try {
        const result = await exec('/usr/bin/flock', ['-w', '1', `${CONSUMER.paths.claimRoot}/publication-v2.lock`,
          '/usr/bin/node', fileURLToPath(import.meta.url), 'drain-check', '--operation', operationId],
        { env: { RELAY_CONSUMER_CONFIG: process.env.RELAY_CONSUMER_CONFIG, PATH: '/usr/bin:/bin', LANG: 'C', LC_ALL: 'C' },
          timeout: Math.min(5000, remaining), maxBuffer: 1024 * 1024 });
        return JSON.parse(result.stdout);
      } catch (error) {
        let payload;
        try { payload = JSON.parse(error.stderr); } catch { /* flock contention has no JSON */ }
        if (payload?.code) fail(payload.code);
        if (error.code === 1 && !error.stdout && !error.stderr) return { drained: false };
        fail('ADMISSION_DRAIN_STATUS_UNAVAILABLE');
      }
    } });
  }
  const admission = installedAdmissionControl();
  if (command === 'drain-check') return admission.drained(options);
  if (command === 'snapshot') return admission.snapshot({ ...options, services: await readAdmissionSnapshot() });
  if (command === 'recovery-target') return admission.recoveryTarget(options);
  return admission[command](options);
}
function isMain() { try { return realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url)); } catch { return false; } }
if (isMain()) main().then(value => process.stdout.write(JSON.stringify(value) + '\n')).catch(error => {
  process.stderr.write(JSON.stringify({ code: /^[A-Z][A-Z0-9_]{0,79}$/.test(error?.code ?? '') ? error.code : 'ADMISSION_FAILED' }) + '\n');
  process.exitCode = 1;
});
