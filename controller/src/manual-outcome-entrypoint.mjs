import { readRepositoryRequest, entrypointFailure } from './repository-entrypoint.mjs';

try {
  if (process.argv.length !== 2 || process.getuid?.() !== 0) throw Object.assign(new Error('FIXED_ROOT_BROKER_REQUIRED'), { code: 'FIXED_ROOT_BROKER_REQUIRED' });
  const request = await readRepositoryRequest({ limit: 100 * 1024, protectedConfig: true,
    limitCode: 'MANUAL_SUBMISSION_INVALID', parseCode: 'MANUAL_SUBMISSION_INVALID' });
  const { main } = await import('./manual-outcome-helper.mjs');
  process.stdout.write(JSON.stringify(await main(request)) + '\n');
} catch (error) {
  process.stdout.write(JSON.stringify({ error_code: entrypointFailure(error, 'MANUAL_PUBLICATION_FAILED') }) + '\n'); process.exitCode = 1;
}
