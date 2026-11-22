import { failureFacts } from './failure-report.mjs';
import { readRepositoryRequest, entrypointFailure, recordEntrypointFailure } from './repository-entrypoint.mjs';

const cancellation = new AbortController();
const cancel = () => cancellation.abort();
process.on('SIGTERM', cancel);
process.on('SIGINT', cancel);
try {
  if (process.argv.length !== 2 || process.getuid?.() !== 0) throw Object.assign(new Error('FIXED_ROOT_BROKER_REQUIRED'), { code: 'FIXED_ROOT_BROKER_REQUIRED' });
  const request = await readRepositoryRequest({ limit: 145 * 1024 * 1024, protectedConfig: true });
  const { main, serializeWriterFailure } = await import('./privileged-writer-helper.mjs');
  try { process.stdout.write(JSON.stringify(await main(request, { signal: cancellation.signal })) + '\n'); }
  catch (error) {
    error.details = { ...error.details, diagnosticStore: await recordEntrypointFailure(error, request?.operation ?? 'writer-bootstrap') };
    process.stderr.write(JSON.stringify(serializeWriterFailure(error)) + '\n'); process.exitCode = 1; }
} catch (error) {
  const diagnosticStore = await recordEntrypointFailure(error, 'writer-bootstrap');
  process.stderr.write(JSON.stringify({ code: entrypointFailure(error, 'WRITER_FAILED'), ...failureFacts(error), diagnosticStore }) + '\n'); process.exitCode = 1;
}
finally { process.removeListener('SIGTERM', cancel); process.removeListener('SIGINT', cancel); }
