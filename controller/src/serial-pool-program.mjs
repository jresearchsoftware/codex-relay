import { spawn } from 'node:child_process';
import { join } from 'node:path';
import { createAttemptStore } from './attempt-store.mjs';
import { configuredRepositories } from '../../consumer/consumer-config.mjs';
import { parseConsumerJson } from '../../consumer/consumer-config.mjs';
import { loadSerialPoolCompatibility, createCompatibilityStore,
  historicalOperationContext } from './serial-pool-compatibility.mjs';

const fail = code => { throw Object.assign(new Error(code), { code }); };
const programs = Object.freeze({
  writer: 'controller/src/privileged-writer-helper.mjs',
  'manual-outcome': 'controller/src/manual-outcome-helper.mjs',
  'publication-recovery': 'controller/src/recover-attempt-publication.mjs'
});

// A compatibility subprocess has one original consumer and one original module
// graph. Importing the old broker into the new process would reuse cached
// consumer bindings and would not preserve its original validation contract.
export async function originalProgram(context, kind, input, { env = process.env,
  execute = spawn, maxOutput = 1024 * 1024, timeoutMs = 450000 } = {}) {
  if (!Object.hasOwn(programs, kind)) fail('SERIAL_POOL_PROGRAM_INVALID');
  const childEnv = {
    PATH: '/usr/bin:/bin', LANG: 'C', LC_ALL: 'C', HOME: env.HOME ?? '/root',
    RELAY_CONSUMER_CONFIG: context.original.consumerPath
  };
  for (const key of ['RELAY_CALLER_UID', 'GITHUB_TOKEN', 'GITHUB_EVENT_PATH',
    'GITHUB_EVENT_NAME', 'GITHUB_REF', 'GITHUB_RUN_ID', 'RUNNER_NAME']) {
    if (env[key] !== undefined) childEnv[key] = env[key];
  }
  // Preserve the existing Writer budget, including lock contention and its
  // bounded Git operations. Overrides are internal test dependencies only.
  let child;
  try { child = execute('/usr/bin/node', [join(context.original.sourceRoot, programs[kind])],
    { env: childEnv, stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true }); }
  catch { fail('SERIAL_POOL_ORIGINAL_PROGRAM_UNAVAILABLE'); }
  return new Promise((resolve, reject) => {
    const output = []; const errors = []; let bytes = 0; let settled = false;
    const timer = setTimeout(() => stop('SERIAL_POOL_ORIGINAL_PROGRAM_UNAVAILABLE'), timeoutMs);
    function stop(code) {
      if (settled) return;
      settled = true; clearTimeout(timer);
      try { child.kill('SIGTERM'); } catch { /* no process diagnostics escape */ }
      reject(Object.assign(new Error(code), { code }));
    }
    const collect = chunks => chunk => {
      bytes += chunk.length;
      if (bytes > maxOutput) return stop('SERIAL_POOL_ORIGINAL_PROGRAM_UNAVAILABLE');
      chunks.push(chunk);
    };
    child.stdout.on('data', collect(output)); child.stderr.on('data', collect(errors));
    child.on('error', () => stop('SERIAL_POOL_ORIGINAL_PROGRAM_UNAVAILABLE'));
    child.stdin.on('error', () => stop('SERIAL_POOL_ORIGINAL_PROGRAM_UNAVAILABLE'));
    child.on('close', code => {
      if (settled) return;
      settled = true; clearTimeout(timer);
      let value;
      try { value = parseConsumerJson(Buffer.concat(output).toString('utf8')); } catch { /* no diagnostic streams escape */ }
      if (code === 0 && value && typeof value === 'object' && !Array.isArray(value)) return resolve(value);
      let error;
      try { error = JSON.parse(Buffer.concat(errors).toString('utf8')); } catch { /* fixed error below */ }
      const failure = error?.code ?? value?.error_code;
      const publicCode = /^[A-Z][A-Z0-9_]{0,79}$/.test(failure ?? '') ? failure : 'SERIAL_POOL_ORIGINAL_PROGRAM_UNAVAILABLE';
      reject(Object.assign(new Error(publicCode), { code: publicCode }));
    });
    child.stdin.end(JSON.stringify(input));
  });
}

export async function historicalProgram({ kind, request, consumer, consumerPath,
  env = process.env, load = loadSerialPoolCompatibility, invoke = originalProgram }) {
  if (!Object.hasOwn(programs, kind) || !request || typeof request !== 'object' || Array.isArray(request)) fail('SERIAL_POOL_PROGRAM_INVALID');
  if (kind === 'writer' && request.operation === 'manual-outcome-direct') fail('MANUAL_CAPABILITY_REQUIRED');
  const privateChecks = kind !== 'publication-recovery';
  const compatibility = await load({ consumer, consumerPath, privateChecks });
  if (!compatibility) return { handled: false };
  const runId = kind === 'manual-outcome' ? request.run_id : request.runId;
  const operation = kind === 'manual-outcome' ? 'manual-outcome-direct'
    : kind === 'publication-recovery' ? ({ inspect: 'publication-state',
      'inspect-prepublication': 'prepublication-state' }[request.operation] ?? request.operation ?? 'recover-publication') : request.operation;
  const selectedRepository = consumer?.repository ?? compatibility.selectedRepository;
  if (privateChecks) {
    const store = createCompatibilityStore({ compatibility,
      currentStore: createAttemptStore(compatibility.current.storeRoot, { repository: selectedRepository,
        repositories: configuredRepositories(compatibility.currentConsumer), namespace: !!compatibility.currentConsumer.repositories }),
      originalStore: createAttemptStore(compatibility.original.storeRoot, { repository: compatibility.receipt.repository }) });
    // Root classification is complete, even for a current run. A foreign
    // retained record cannot disappear through a per-run or terminal filter.
    await store.all();
    if (selectedRepository !== compatibility.receipt.repository) return { handled: false };
    if (!compatibility.receipt.original.runs.some(run => run.runId === runId)) return { handled: false };
    const record = await store.get(runId);
    historicalOperationContext(compatibility, record, operation);
    if (kind === 'manual-outcome' || operation === 'manual-outcome') {
      if (record.envelope.route !== 'manual') fail('MANUAL_OUTCOME_NOT_ADMITTED');
    } else if (kind === 'writer') {
      if (['finish-no-change', 'terminal-outcome', 'observe-readiness'].includes(operation)) fail('SERIAL_POOL_HISTORICAL_EXECUTION_FORBIDDEN');
      if (operation === 'finish') {
        const recovery = record.publicationRecoveries?.find(value => value.authorizationId === request.recoveryAuthorizationId);
        if (record.envelope.route !== 'auto' || !Number.isSafeInteger(request.recoveryAuthorizationId) || request.recoveryAuthorizationId < 1
          || record.publicationIntent || recovery?.result?.status !== 'PUBLISHED'
          || recovery.result.publishedHead !== record.publishedHead) fail('RECOVERED_OUTCOME_REQUIRED');
      }
    }
  } else {
    // The public sealed membership selects an immutable recovery program only.
    // It grants no record access or mutation: the original program obtains the
    // real envelope through the root Writer, which reclassifies both stores.
    if (selectedRepository !== compatibility.receipt.repository
      || !compatibility.receipt.original.runs.some(run => run.runId === runId)) return { handled: false };
    if (!['publication-state', 'recover-publication', 'prepublication-state', 'recover-prepublication'].includes(operation))
      fail('SERIAL_POOL_HISTORICAL_EXECUTION_FORBIDDEN');
  }
  if (kind !== 'manual-outcome') {
    const caller = kind === 'writer' ? Number(env.RELAY_CALLER_UID) : process.getuid?.();
    if (caller !== compatibility.original.runnerUid) fail('SERIAL_POOL_ORIGINAL_RUNNER_IDENTITY_REQUIRED');
  }
  const originalInput = { ...request };
  // The original SERIAL transport had no execution slot. Remove only the new
  // caller's resource selector; stored envelopes and authority stay untouched.
  delete originalInput.executionSlot;
  return { handled: true, value: await invoke(compatibility, kind, originalInput, { env }) };
}
