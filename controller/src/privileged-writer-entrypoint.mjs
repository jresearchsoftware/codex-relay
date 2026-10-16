import { readRepositoryRequest, entrypointFailure } from './repository-entrypoint.mjs';

try {
  if (process.argv.length !== 2 || process.getuid?.() !== 0) throw Object.assign(new Error('FIXED_ROOT_BROKER_REQUIRED'), { code: 'FIXED_ROOT_BROKER_REQUIRED' });
  const request = await readRepositoryRequest({ limit: 145 * 1024 * 1024, protectedConfig: true });
  const { main, serializeWriterFailure } = await import('./privileged-writer-helper.mjs');
  try { process.stdout.write(JSON.stringify(await main(request)) + '\n'); }
  catch (error) { process.stderr.write(JSON.stringify(serializeWriterFailure(error)) + '\n'); process.exitCode = 1; }
} catch (error) {
  process.stderr.write(JSON.stringify({ code: entrypointFailure(error, 'WRITER_FAILED') }) + '\n'); process.exitCode = 1;
}
