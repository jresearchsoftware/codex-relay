import { assertRootConsumer } from '../../consumer/consumer-config.mjs';
import { CONSUMER, unixUserId } from '../../consumer/consumer.mjs';
import { realpathSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { createPublicationBroker } from './publication-broker.mjs';
import { createAttemptStore } from './attempt-store.mjs';
import { createGithubApi } from './github-api.mjs';
import { createGitPublisher, collectProgress } from './trusted-git.mjs';
import { checkoutPath } from './attempt-runtime.mjs';
import { token } from './writer-auth.mjs';
import { fail } from './execution-contract.mjs';
import { failureDiagnosticFromDetails } from './diagnostics.mjs';
import { installedAdmissionControl } from './admission-cli.mjs';
import { REPOSITORY, VERSION } from './execution-contract.mjs';
import { createSlotJournal } from './slot-journal.mjs';

export function callerExecutionSlot({ uid, slotId, uidForUser = unixUserId } = {}) {
  if (!CONSUMER.executionSlots) return undefined;
  if (!Number.isSafeInteger(uid) || uid < 1) fail('EXECUTION_SLOT_IDENTITY_INVALID');
  // A shared trusted runner UID can own several managed instances. The bounded
  // slot identifies a configured resource, not a new worker/Writer identity.
  // Historical callers without a slot still need an unambiguous UID match.
  const matches = CONSUMER.executionSlots.filter(slot => (slotId === undefined || slot.id === slotId)
    && uidForUser(slot.runnerUser) === uid);
  if (matches.length !== 1) fail('EXECUTION_SLOT_IDENTITY_INVALID');
  return matches[0].id;
}
export async function assertWriterSlot(request, { callerUid = process.env.RELAY_CALLER_UID,
  store = createAttemptStore(`${CONSUMER.paths.claimRoot}/publication-v2`), resolveSlot = callerExecutionSlot } = {}) {
  if (!CONSUMER.executionSlots) {
    if (Object.hasOwn(request ?? {}, 'executionSlot')) fail('EXECUTION_SLOT_INVALID');
    return;
  }
  if (!/^[1-9][0-9]{0,9}$/.test(callerUid ?? '')) fail('EXECUTION_SLOT_IDENTITY_INVALID');
  const slot = resolveSlot({ uid: Number(callerUid), slotId: request.executionSlot });
  if (request.executionSlot !== slot) fail('EXECUTION_SLOT_IDENTITY_INVALID');
  if (request.operation === 'admit') return;
  const record = await store.get(request.runId);
  if (!record) fail('ATTEMPT_NOT_ADMITTED');
  // Inspection and root-owned retained collection can read the stored slot.
  // Ordinary runner-owned publication recovery still uses its original private
  // journal/collector identity, even with a fresh owner authorization.
  const recovery = ['publication-state', 'prepublication-state', 'recover-prepublication'].includes(request.operation);
  const originalSlot = record.envelope.executionSlot ?? 'primary';
  const poolRecovery = CONSUMER.generalRunnerPool && (['recover-publication', 'complete-handoff'].includes(request.operation)
    || (request.operation === 'finish' && request.recoveryAuthorizationId !== undefined));
  const original = CONSUMER.executionSlots.find(value => value.id === originalSlot);
  const current = CONSUMER.executionSlots.find(value => value.id === slot);
  // Managed runner retirement does not retire its attempt evidence. A current
  // member with the same trusted UID can finish explicitly authorized recovery;
  // the Writer still derives original paths from its protected envelope.
  if (!recovery && originalSlot !== slot && !(poolRecovery && original && current
    && original.runnerUser === current.runnerUser)) fail('EXECUTION_SLOT_BINDING_CHANGED');
}

export function resolveWriterDeploymentContract(env = process.env) {
  const profile = { credentialEnv: CONSUMER.paths.credentialEnv, credentialKeyFile: CONSUMER.paths.credentialKeyFile, claimRoot: CONSUMER.paths.claimRoot };
  for (const [variable, field] of [['RELAY_WRITER_CREDENTIAL_ENV', 'credentialEnv'], ['RELAY_WRITER_CREDENTIAL_KEY_FILE', 'credentialKeyFile'], ['RELAY_WRITER_CLAIM_ROOT', 'claimRoot']]) {
    if (env[variable] !== undefined && env[variable] !== profile[field]) fail('WRITER_DEPLOYMENT_CONTRACT_INVALID');
  }
  return profile;
}
export async function main() {
  if (process.argv.length !== 2 || process.getuid?.() !== 0) fail('FIXED_ROOT_BROKER_REQUIRED');
  assertRootConsumer(process.env.RELAY_CONSUMER_CONFIG);
  const deployment = resolveWriterDeploymentContract();
  let size = 0; const chunks = [];
  for await (const chunk of process.stdin) { size += chunk.length; if (size > 145 * 1024 * 1024) fail('REQUEST_TOO_LARGE'); chunks.push(chunk); }
  let request; try { request = JSON.parse(Buffer.concat(chunks).toString('utf8')); } catch { fail('REQUEST_INVALID'); }
  if (request?.operation === 'manual-outcome-direct') fail('MANUAL_CAPABILITY_REQUIRED');
  await assertWriterSlot(request);
  const admission = installedAdmissionControl();
  if (request?.operation === 'complete-execution') {
    return { version: VERSION, repository: REPOSITORY, ...await admission.complete(request) };
  }
  return (await protectedWriterBroker({ deployment, runToken: request.workflowReadToken, admission })).dispatch(request);
}
export async function protectedWriterBroker({ deployment = resolveWriterDeploymentContract(), runToken, admission = installedAdmissionControl(), allowManualOutcome = false } = {}) {
  if (process.getuid?.() !== 0) fail('FIXED_ROOT_BROKER_REQUIRED');
  const value = await token();
  const store = createAttemptStore(`${deployment.claimRoot}/publication-v2`);
  return createPublicationBroker({ api: createGithubApi({ token: value, runToken }),
    store,
    lifecycleStore: createAttemptStore(`${deployment.claimRoot}/pr-lifecycle-v1`),
    journal: createSlotJournal(store),
    publisher: createGitPublisher({ token: value, root: deployment.claimRoot }),
    // Fixed root helper, exact admitted attempt, original contained journal.
    // No caller path, permission repair or worker Git metadata is accepted.
    collectRetained: e => collectProgress(checkoutPath(e), e, { token: value, root: deployment.claimRoot }),
    admission, allowManualOutcome });
}
export function serializeWriterFailure(error) {
  const code = /^[A-Z][A-Z0-9_]{0,79}$/.test(error?.code ?? '') ? error.code : 'WRITER_FAILED';
  const failureDiagnostic = failureDiagnosticFromDetails(error?.details);
  return { code, ...(failureDiagnostic ? { failureDiagnostic } : {}) };
}
function isMain() { try { return realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url)); } catch { return false; } }
if (isMain()) main().then(value => process.stdout.write(JSON.stringify(value) + '\n')).catch(error => {
  process.stderr.write(JSON.stringify(serializeWriterFailure(error)) + '\n'); process.exitCode = 1;
});
