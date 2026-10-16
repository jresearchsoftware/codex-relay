import { assertRootConsumer, loadConsumer, selectRepositoryConsumer } from '../../consumer/consumer-config.mjs';

// Select only a configured target before loading modules with process-local
// repository constants. Each fixed helper invocation handles one request.
export async function readRepositoryRequest({ input = process.stdin, limit, protectedConfig = false,
  env = process.env } = {}) {
  if (protectedConfig) assertRootConsumer(env.RELAY_CONSUMER_CONFIG);
  const installation = loadConsumer(env.RELAY_CONSUMER_CONFIG);
  let size = 0; const chunks = [];
  for await (const value of input) {
    const chunk = Buffer.from(value); size += chunk.length;
    if (size > limit) throw Object.assign(new Error('REQUEST_TOO_LARGE'), { code: 'REQUEST_TOO_LARGE' });
    chunks.push(chunk);
  }
  let request;
  try { request = JSON.parse(Buffer.concat(chunks).toString('utf8')); }
  catch { throw Object.assign(new Error('REQUEST_INVALID'), { code: 'REQUEST_INVALID' }); }
  const selected = selectRepositoryConsumer(installation, request?.repository);
  env.RELAY_REPOSITORY = selected.repository;
  return request;
}

export function entrypointFailure(error, fallback) {
  return /^[A-Z][A-Z0-9_]{0,79}$/.test(error?.code ?? '') ? error.code : fallback;
}
