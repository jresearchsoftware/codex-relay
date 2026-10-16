import { readRepositoryRequest, entrypointFailure } from './repository-entrypoint.mjs';

try {
  const request = process.argv.length === 3 && process.argv[2] === '--check-runtime' ? undefined
    : await readRepositoryRequest({ limit: 512 * 1024 });
  const { main, serializeDispatchFailure } = await import('./codex-dispatch.mjs');
  try { process.stdout.write(JSON.stringify(await main(request)) + '\n'); }
  catch (error) { process.stderr.write(JSON.stringify(serializeDispatchFailure(error)) + '\n'); process.exitCode = 1; }
} catch (error) {
  process.stderr.write(JSON.stringify({ version: 2, status: 'blocked', code: entrypointFailure(error, 'EXECUTION_FAILED') }) + '\n'); process.exitCode = 1;
}
