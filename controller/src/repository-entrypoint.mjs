import { assertRootConsumer, loadConsumer, selectRepositoryConsumer } from '../../consumer/consumer-config.mjs';

// Select only a configured target before loading modules with process-local
// repository constants. Each fixed helper invocation handles one request.
export async function readRepositoryRequest({ input = process.stdin, limit, protectedConfig = false,
  env = process.env, limitCode = 'REQUEST_TOO_LARGE', parseCode = 'REQUEST_INVALID',
  emptyCode = parseCode, targetCode } = {}) {
  const fail = code => { throw Object.assign(new Error(code), { code }); };
  const installation = loadConsumer(env.RELAY_CONSUMER_CONFIG);
  if (protectedConfig) {
    try { assertRootConsumer(env.RELAY_CONSUMER_CONFIG); } catch { fail('CONSUMER_CONFIG_INVALID'); }
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
  catch { fail(parseCode); }
  let selected;
  try { selected = selectRepositoryConsumer(installation, request?.repository); }
  catch (error) { if (targetCode) fail(targetCode); throw error; }
  env.RELAY_REPOSITORY = selected.repository;
  return request;
}

export function entrypointFailure(error, fallback) {
  return /^[A-Z][A-Z0-9_]{0,79}$/.test(error?.code ?? '') ? error.code : fallback;
}
