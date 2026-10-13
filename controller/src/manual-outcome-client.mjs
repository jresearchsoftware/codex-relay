import { connect } from 'node:net';
import { realpath } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

export async function submit(socketPath, bytes, { timeoutMs = 60000 } = {}) {
  if (!socketPath?.startsWith('/') || socketPath.includes('..') || bytes.length > 100 * 1024) throw new Error('MANUAL_SUBMISSION_INVALID');
  return new Promise((resolve, reject) => {
    const connection = connect(socketPath); const chunks = []; let size = 0;
    const timer = setTimeout(() => connection.destroy(new Error('MANUAL_PUBLICATION_UNCERTAIN')), timeoutMs);
    connection.on('connect', () => connection.end(bytes));
    connection.on('data', chunk => { size += chunk.length; if (size > 32 * 1024) connection.destroy(new Error('MANUAL_RECEIPT_INVALID')); else chunks.push(chunk); });
    connection.on('error', reject);
    connection.on('close', () => { clearTimeout(timer); resolve(Buffer.concat(chunks)); });
  });
}
async function main() {
  if (process.argv.length !== 2) throw new Error('MANUAL_SUBMISSION_INVALID');
  const chunks = []; let size = 0;
  for await (const chunk of process.stdin) {
    size += chunk.length; if (size > 100 * 1024) throw new Error('MANUAL_SUBMISSION_INVALID'); chunks.push(chunk);
  }
  const bytes = Buffer.concat(chunks);
  process.stdout.write(await submit(process.env.RELAY_MANUAL_OUTCOME_SOCKET, bytes));
}
if (process.argv[1] && await realpath(process.argv[1]).catch(() => null) === fileURLToPath(import.meta.url)) {
  main().catch(() => { process.stdout.write('{"error_code":"MANUAL_PUBLICATION_UNCERTAIN"}\n'); process.exitCode = 1; });
}
