import { readRepositoryRequest, entrypointFailure } from './repository-entrypoint.mjs';
import { realpathSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';

// Deployment-operator route for a blocked drain: use an independently accepted,
// root-owned source tree with the unchanged protected configuration. No service
// cutover or runner-UID impersonation is needed to finalize one old reservation.
export async function main({ uid = process.getuid?.(), argv = process.argv, input = process.stdin,
  execute = spawn, readRequest = readRepositoryRequest } = {}) {
  if (uid !== 0 || argv.length !== 2) throw Object.assign(new Error('ROOT_OPERATOR_REQUIRED'), { code: 'ROOT_OPERATOR_REQUIRED' });
  const request = await readRequest({ input, limit: 4096, protectedConfig: true });
  const operations = ['predispatch-state', 'finalize-predispatch'];
  const allowed = ['operation', 'repository', 'runId', 'attemptId', 'authorizationId'];
  if (!operations.includes(request.operation) || Object.keys(request).some(key => !allowed.includes(key)))
    throw Object.assign(new Error('RECOVERY_REQUEST_INVALID'), { code: 'RECOVERY_REQUEST_INVALID' });
  const { CONSUMER } = await import('../../consumer/consumer.mjs');
  // Match the installed wrapper's exact existing Writer mutex. Lock ownership
  // lasts through the child response and its atomic record write.
  const program = `import { protectedWriterBroker } from ${JSON.stringify(new URL('./privileged-writer-helper.mjs', import.meta.url).href)};
    const chunks=[];for await(const chunk of process.stdin) chunks.push(chunk);
    try { const request=JSON.parse(Buffer.concat(chunks));
      console.log(JSON.stringify(await (await protectedWriterBroker()).dispatch(request)));
    } catch(error) { console.error(JSON.stringify({code:/^[A-Z][A-Z0-9_]{0,79}$/.test(error.code??'')?error.code:'PREDISPATCH_RECOVERY_FAILED'}));process.exitCode=1; }`;
  const child = execute('/usr/bin/flock', ['-w', '60', `${CONSUMER.paths.claimRoot}/publication-v2.lock`,
    process.execPath, '--input-type=module', '-e', program],
  { env: { PATH: '/usr/bin:/bin', HOME: '/root', LANG: 'C', LC_ALL: 'C',
    RELAY_CONSUMER_CONFIG: process.env.RELAY_CONSUMER_CONFIG, RELAY_REPOSITORY: CONSUMER.repository },
    stdio: ['pipe', 'inherit', 'inherit'], windowsHide: true });
  return new Promise((resolve, reject) => {
    child.once('error', reject);
    child.stdin.on('error', () => {});
    child.once('exit', code => resolve(code ?? 1));
    child.stdin.end(JSON.stringify(request));
  });
}

function isMain() { try { return realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url)); } catch { return false; } }
if (isMain()) main().then(code => { process.exitCode = code; }).catch(error => {
  process.stderr.write(JSON.stringify({ code: entrypointFailure(error, 'PREDISPATCH_RECOVERY_FAILED') }) + '\n');
  process.exitCode = 1;
});
