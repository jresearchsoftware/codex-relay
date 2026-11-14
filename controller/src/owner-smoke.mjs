// Fixed owner-local qualification, separate from native Task execution authority.
import { readFile, realpath, stat } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { CONSUMER, CONSUMER_DIGEST, executionConsumer } from '../../consumer/consumer.mjs';
import { VERSION, exactSha, fail } from './execution-contract.mjs';
import { CODEX_TERMINATION_GRACE_MS, runGovernedCodexTask } from '../../runtime/src/codex-runtime.mjs';
import { normalizeCodexUsage } from './codex-usage.mjs';

// Preserve the existing two-minute owner probe boundary and reserve the fixed
// forty-second cleanup and native termination allowances inside that boundary.
export const OWNER_SMOKE_TIMEOUT_MS = 120000;
const OWNER_SMOKE_EXECUTION_MS = OWNER_SMOKE_TIMEOUT_MS - 40000 - CODEX_TERMINATION_GRACE_MS;
export const OWNER_SMOKE_PROFILE = Object.freeze({ cliModelId: 'gpt-6-astra', effort: 'low' });
export const OWNER_SMOKE_INPUT = `Owner-authorized non-routing general runner smoke. Do not use tools,
run commands, modify files, create commits, access GitHub or any external service,
publish, push, invoke a Reviewer, or change production. Perform no external work.
Only return {"status":"success","summary":"general-runner-smoke-child-started","validation":[],"blockedReason":""}.
The scratch fixture is intentionally complete and requires no implementation.`;
const KEYS = ['approvedHead', 'attemptId', 'consumerDigest', 'kind', 'repository', 'version'].sort().join('\0');

export function validateOwnerSmokeRequest(value) {
  if (!value || Object.keys(value).sort().join('\0') !== KEYS || value.version !== VERSION
      || value.kind !== 'owner-smoke' || value.repository !== CONSUMER.repository
      || value.consumerDigest !== CONSUMER_DIGEST || !/^event-[1-9][0-9]{11,12}$/.test(value.attemptId ?? '')
      || !exactSha(value.approvedHead)) fail('OWNER_SMOKE_REQUEST_INVALID');
  return value;
}

// The public owner helper remains the sole producer. A mode name or JSON body
// is insufficient: verify the actual installed caller and its root transition.
export async function assertOwnerSmokeCaller(request, {
  parentPid = process.ppid, uid = process.getuid?.(),
  read = readFile, metadata = stat, canonical = realpath,
  modulePath = fileURLToPath(import.meta.url), load = url => import(url)
} = {}) {
  let operation = 'owner-smoke-request';
  try {
    validateOwnerSmokeRequest(request);
    const reviewed = resolve(dirname(modulePath), '../..');
    const producer = join(reviewed, 'consumer-general-runner-smoke.mjs');
    operation = 'owner-smoke-parent-command';
    const argv = (await read(`/proc/${parentPid}/cmdline`, 'utf8')).split('\0').filter(Boolean);
    if (argv.length !== 4 || argv[1] !== producer || argv[2] !== '--approved-head' || argv[3] !== request.approvedHead
        || (await metadata(`/proc/${parentPid}`)).uid !== uid) fail('SMOKE_OWNER_TRANSITION_REQUIRED');
    operation = 'owner-smoke-parent-identity';
    const status = await read(`/proc/${parentPid}/status`, 'utf8');
    const ancestor = /^PPid:\s+([1-9][0-9]*)$/m.exec(status)?.[1];
    if (!ancestor || (await metadata(`/proc/${ancestor}`)).uid !== 0
        || (await read(`/proc/${ancestor}/comm`, 'utf8')).trim() !== 'runuser') fail('SMOKE_OWNER_TRANSITION_REQUIRED');
    operation = 'owner-smoke-producer-binding';
    if ((await metadata(producer)).uid !== 0) fail('SMOKE_INSTALLED_HEAD_MISMATCH');
    const binding = await load(pathToFileURL(producer).href);
    operation = 'owner-smoke-root-command';
    const rootArgv = (await read(`/proc/${ancestor}/cmdline`, 'utf8')).split('\0').filter(Boolean);
    if (rootArgv.length !== 8 || rootArgv[0] !== '/usr/sbin/runuser' || rootArgv[1] !== '-u'
        || rootArgv[2] !== binding.OWNER_SMOKE_RUNNER_USER || rootArgv[3] !== '--'
        || rootArgv.slice(4).join('\0') !== argv.join('\0')) fail('SMOKE_OWNER_TRANSITION_REQUIRED');
    operation = 'owner-smoke-current-release';
    const release = join(binding.OWNER_SMOKE_RELEASE_ROOT, request.approvedHead);
    if (await canonical(binding.OWNER_SMOKE_CURRENT) !== release || dirname(reviewed) !== release) fail('SMOKE_INSTALLED_HEAD_MISMATCH');
    // The fixed root-only helper verified the protected manifest before this
    // exact runuser transition. Reuse that gate: the runner is deliberately
    // unable to read root:root 0640 installation metadata itself.
    operation = 'owner-smoke-scratch-binding';
    const root = executionConsumer().paths.workRoot;
    const cwd = join(root, request.attemptId);
    if (await canonical(root) !== root || await canonical(cwd) !== cwd || !(await metadata(cwd)).isDirectory()) fail('SMOKE_WORK_ROOT_UNSAFE');
    return cwd;
  } catch (error) {
    error.details = { ...error.details, operation, boundary: 'dispatcher',
      syscall: error.syscall, pathContext: 'owner-smoke-authorization' };
    throw error;
  }
}

export async function executeOwnerSmoke(request, { signal, runTask = runGovernedCodexTask } = {}) {
  validateOwnerSmokeRequest(request);
  const evidence = { codexChildStarted: false };
  try {
    const result = await runTask({ operation: 'owner-smoke', attemptId: request.attemptId,
      profile: OWNER_SMOKE_PROFILE, inputText: OWNER_SMOKE_INPUT,
      cwd: join(executionConsumer().paths.workRoot, request.attemptId),
      taskTitle: 'General runner non-routing smoke', evidence, existingFallback: true, signal,
      env: { ...process.env, CODEX_RUNTIME_TIMEOUT_MS: String(OWNER_SMOKE_EXECUTION_MS) },
      buildArgs: ({ inputPath, cwd, profile }) => ['exec', '--json', '--model', profile.cliModelId,
        '--effort', profile.effort, '--input-file', inputPath, '--cwd', cwd, '--owner-smoke'] });
    return { version: VERSION, attemptId: request.attemptId, result, child: 'started',
      containment: evidence.codexContainment ?? 'unknown', codexUsage: normalizeCodexUsage(evidence.codexUsage) };
  } catch (error) {
    error.details = { ...error.details, executionId: request.attemptId,
      containment: evidence.codexContainment ?? 'unknown', codexUsage: normalizeCodexUsage(evidence.codexUsage),
      childState: error.details?.childState ?? (evidence.codexChildStarted === true ? 'started'
        : evidence.codexChildStarted === false ? 'not_started' : 'unknown') };
    throw error;
  }
}
