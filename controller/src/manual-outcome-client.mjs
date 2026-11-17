import { connect } from 'node:net';
import { realpath } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { createBoundedUtf8Capture } from './utf8-capture.mjs';

const clientError = code => Object.assign(new Error(code), { code });
function privateFailure(error, operation, receipt) {
  Object.defineProperty(error, 'native', { value: { operation, receipt }, configurable: true });
  return error;
}

// This fixed client deliberately has no consumer/credential configuration. Its
// stderr is retained by the Reviewer/protected service journal. A standalone
// redactor is unavailable here, so print native errno/syscall and byte metadata
// only; caller input, socket paths, raw receipt text and stacks stay private.
export function manualClientFailureSummary(error) {
  const code = value => typeof value === 'string' && /^[A-Z][A-Z0-9_]{0,79}$/.test(value) ? value : undefined;
  return { event: 'manual_outcome_transport_failure', code: code(error?.code) ?? 'MANUAL_PUBLICATION_UNCERTAIN',
    ...(Number.isInteger(error?.errno) ? { errno: error.errno } : {}),
    ...(typeof error?.syscall === 'string' && /^[a-z][a-z0-9_-]{0,39}$/.test(error.syscall) ? { syscall: error.syscall } : {}),
    ...(error?.native?.receipt ? { receiptBytes: error.native.receipt.total, receiptTruncated: error.native.receipt.truncated,
      receiptText: 'unavailable_without_standalone_redactor' } : {}) };
}

export async function submit(socketPath, bytes, { timeoutMs = 60000 } = {}) {
  if (!socketPath?.startsWith('/') || socketPath.includes('..') || bytes.length > 100 * 1024) throw clientError('MANUAL_SUBMISSION_INVALID');
  return new Promise((resolve, reject) => {
    const connection = connect(socketPath); const chunks = []; let size = 0;
    const capture = createBoundedUtf8Capture(4096);
    const timer = setTimeout(() => connection.destroy(clientError('MANUAL_PUBLICATION_UNCERTAIN')), timeoutMs);
    connection.on('connect', () => connection.end(bytes));
    connection.on('data', chunk => { capture.push(chunk); size += chunk.length; if (size > 32 * 1024) connection.destroy(clientError('MANUAL_RECEIPT_INVALID')); else chunks.push(chunk); });
    connection.on('error', error => reject(privateFailure(error, 'manual-outcome-socket', capture.finish())));
    connection.on('close', () => { clearTimeout(timer); resolve(Buffer.concat(chunks)); });
  });
}
async function main() {
  if (process.argv.length !== 2) throw clientError('MANUAL_SUBMISSION_INVALID');
  const chunks = []; let size = 0;
  for await (const chunk of process.stdin) {
    size += chunk.length; if (size > 100 * 1024) throw clientError('MANUAL_SUBMISSION_INVALID'); chunks.push(chunk);
  }
  const bytes = Buffer.concat(chunks);
  process.stdout.write(await submit(process.env.RELAY_MANUAL_OUTCOME_SOCKET, bytes));
}
if (process.argv[1] && await realpath(process.argv[1]).catch(() => null) === fileURLToPath(import.meta.url)) {
  main().catch(error => {
    process.stderr.write(JSON.stringify(manualClientFailureSummary(error)) + '\n');
    process.stdout.write('{"error_code":"MANUAL_PUBLICATION_UNCERTAIN"}\n'); process.exitCode = 1;
  });
}
