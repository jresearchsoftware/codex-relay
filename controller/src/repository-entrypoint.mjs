import { assertRootConsumer, loadConsumer, selectRepositoryConsumer } from '../../consumer/consumer-config.mjs';

// Select only a configured target before loading modules with process-local
// repository constants. Each fixed helper invocation handles one request.
export async function readRepositoryRequest({ input = process.stdin, limit, protectedConfig = false,
  env = process.env, limitCode = 'REQUEST_TOO_LARGE', parseCode = 'REQUEST_INVALID',
  emptyCode = parseCode, targetCode } = {}) {
  const fail = (code, cause) => { const error = Object.assign(new Error(code), { code });
    if (cause) Object.defineProperty(error, 'runtimeCause', { value: cause });
    throw error; };
  const installation = loadConsumer(env.RELAY_CONSUMER_CONFIG);
  if (protectedConfig) {
    try { assertRootConsumer(env.RELAY_CONSUMER_CONFIG); } catch (cause) { fail('CONSUMER_CONFIG_INVALID', cause); }
  }
  let size = 0; const chunks = [];
  for await (const value of input) {
    const chunk = Buffer.from(value); size += chunk.length;
    if (size > limit) fail(limitCode);
    chunks.push(chunk);
  }
  let request;
  if (size === 0) fail(emptyCode);
  try { request = JSON.parse(Buffer.concat(chunks).toString('utf8')); }
  catch (cause) { fail(parseCode, cause); }
  let selected;
  try { selected = selectRepositoryConsumer(installation, request?.repository); }
  catch (error) { if (targetCode) fail(targetCode, error); throw error; }
  env.RELAY_REPOSITORY = selected.repository;
  return request;
}

export function entrypointFailure(error, fallback) {
  return /^[A-Z][A-Z0-9_]{0,79}$/.test(error?.code ?? '') ? error.code : fallback;
}

// Bootstrap cannot statically import repository-bound diagnostic modules before
// configuration/target selection. The independent stderr surface remains useful
// if that import or the configured host stores are themselves unavailable.
export async function recordEntrypointFailure(error, operation, { record, write = text => process.stderr.write(text), uid = process.getuid?.() } = {}) {
  if (error?.details?.diagnosticStore) return error.details.diagnosticStore;
  if (uid !== 0) return undefined;
  try {
    const recorder = record ?? (await import('./host-failure-diagnostic.mjs')).recordHostFailure;
    return await recorder({ error, operation, phase: 'authority' });
  } catch (failure) {
    const reference = { status: 'unavailable', code: 'DIAGNOSTICS_STORE_UNAVAILABLE',
      storeCode: entrypointFailure(failure, 'DIAGNOSTIC_MODULE_UNAVAILABLE') };
    try { write(`RELAY_DIAGNOSTIC_UNAVAILABLE ${JSON.stringify({ ...reference,
      originalCode: entrypointFailure(error, 'BOOTSTRAP_FAILED'), phase: 'bootstrap', originalEvidence: 'observed_not_retained' })}\n`); }
    catch { /* Process output and host storage are unavailable. */ }
    return reference;
  }
}
