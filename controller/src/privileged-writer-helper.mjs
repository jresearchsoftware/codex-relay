import { assertRootConsumer } from '../../consumer/consumer-config.mjs';
import { CONSUMER } from '../../consumer/consumer.mjs';
import { realpathSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { createPublicationBroker } from './publication-broker.mjs';
import { createAttemptStore } from './attempt-store.mjs';
import { createGithubApi } from './github-api.mjs';
import { createGitPublisher } from './trusted-git.mjs';
import { token } from './writer-auth.mjs';
import { fail } from './execution-contract.mjs';
import { failureDiagnosticFromDetails } from './diagnostics.mjs';

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
  const value = await token();
  return createPublicationBroker({ api: createGithubApi({ token: value, runToken: request.workflowReadToken }),
    store: createAttemptStore(`${deployment.claimRoot}/publication-v2`),
    publisher: createGitPublisher({ token: value, root: deployment.claimRoot }) }).dispatch(request);
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
