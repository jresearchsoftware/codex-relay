import { realpathSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { validateEnvelope, fail, VERSION, causalEvidence } from './execution-contract.mjs';
import { executeCodex } from './attempt-runtime.mjs';
import { CONSUMER, EXECUTION_SLOT, unixUserId } from '../../consumer/consumer.mjs';

export async function main() {
  if (process.argv.length === 3 && process.argv[2] === '--check-runtime') return { version: VERSION, status: 'RUNTIME_READY' };
  if (process.argv.length !== 2) fail('DISPATCH_ARGUMENTS_INVALID');
  const chunks = []; let size = 0;
  for await (const chunk of process.stdin) { size += chunk.length; if (size > 512 * 1024) fail('ENVELOPE_TOO_LARGE'); chunks.push(chunk); }
  const e = validateEnvelope(JSON.parse(Buffer.concat(chunks).toString('utf8')));
  if (CONSUMER.executionSlots) {
    const slot = CONSUMER.executionSlots.find(value => value.id === EXECUTION_SLOT);
    if (!slot || (e.executionSlot ?? 'primary') !== slot.id || process.getuid?.() !== unixUserId(slot.runnerUser)) fail('EXECUTION_SLOT_IDENTITY_INVALID');
  }
  return executeCodex(e);
}
function isMain() { try { return realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url)); } catch { return false; } }
if (isMain()) main().then(value => process.stdout.write(JSON.stringify(value) + '\n')).catch(error => {
  process.stderr.write(JSON.stringify({ version: VERSION, status: 'blocked', code: /^[A-Z][A-Z0-9_]{0,79}$/.test(error?.code ?? '') ? error.code : 'EXECUTION_FAILED', diagnostic: causalEvidence(error) }) + '\n'); process.exitCode = 1;
});
