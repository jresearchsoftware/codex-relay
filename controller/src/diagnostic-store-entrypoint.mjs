import { readRepositoryRequest, entrypointFailure } from './repository-entrypoint.mjs';

try {
  const request = process.argv.length === 3 && process.argv[2] === '--check-runtime' ? undefined
    : await readRepositoryRequest({ limit: 16 * 1024 * 1024, limitCode: 'DIAGNOSTIC_REQUEST_TOO_LARGE',
      parseCode: 'DIAGNOSTIC_REQUEST_INVALID', emptyCode: 'DIAGNOSTIC_REQUEST_EMPTY' });
  const { main } = await import('./diagnostic-store.mjs');
  await main(request);
} catch (error) {
  process.stderr.write(JSON.stringify({ status: 'blocked', code: entrypointFailure(error, 'DIAGNOSTIC_STORE_FAILED') }) + '\n');
  process.exitCode = 1;
}
