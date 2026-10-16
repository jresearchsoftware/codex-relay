import { assertRootConsumer } from '../../consumer/consumer-config.mjs';
import { createAttemptStore, createPublicationStore } from './attempt-store.mjs';
import { protectedWriterBroker, resolveWriterDeploymentContract } from './privileged-writer-helper.mjs';
import { validateManualSubmission } from './manual-outcome.mjs';
import { fail, REPOSITORY, WRITER } from './execution-contract.mjs';
import { fileURLToPath } from 'node:url';
import { realpathSync } from 'node:fs';
import { CONSUMER } from '../../consumer/consumer.mjs';
import { historicalProgram } from './serial-pool-program.mjs';
import { loadSerialPoolCompatibility, createCompatibilityStore } from './serial-pool-compatibility.mjs';

// Socket-activated root entrypoint: no command, token, path or operation selector.
export async function main(selectedSubmission) {
  if (process.argv.length !== 2 || process.getuid?.() !== 0) fail('FIXED_ROOT_BROKER_REQUIRED');
  assertRootConsumer(process.env.RELAY_CONSUMER_CONFIG);
  let submission = selectedSubmission;
  if (submission === undefined) {
    const chunks = []; let bytes = 0;
    for await (const chunk of process.stdin) { bytes += chunk.length; if (bytes > 100 * 1024) fail('MANUAL_SUBMISSION_INVALID'); chunks.push(chunk); }
    try { submission = JSON.parse(Buffer.concat(chunks).toString('utf8')); } catch { fail('MANUAL_SUBMISSION_INVALID'); }
  }
  validateManualSubmission(submission);
  const historical = await historicalProgram({ kind: 'manual-outcome', request: submission,
    consumer: CONSUMER, consumerPath: process.env.RELAY_CONSUMER_CONFIG });
  if (historical.handled) return historical.value;
  const deployment = resolveWriterDeploymentContract();
  const compatibility = await loadSerialPoolCompatibility({ consumer: CONSUMER });
  const store = compatibility ? createCompatibilityStore({ compatibility,
    currentStore: createPublicationStore(compatibility.current.storeRoot),
    originalStore: createAttemptStore(compatibility.original.storeRoot) })
    : createPublicationStore(`${deployment.claimRoot}/publication-v2`);
  const record = await store.get(submission.run_id);
  if (!record || record.envelope?.issueNumber !== submission.task || record.envelope?.route !== 'manual') fail('MANUAL_OUTCOME_NOT_ADMITTED');
  const broker = await protectedWriterBroker({ deployment, allowManualOutcome: true });
  const receipt = await broker.dispatch({ operation: 'manual-outcome-direct', runId: submission.run_id,
    attemptId: record.envelope.attemptId, submission });
  const parent = submission.result.parent;
  return { status: record.outcome ? 'DUPLICATE_SUPPRESSED' : 'PUBLISHED', repository: REPOSITORY, task: submission.task, run_id: submission.run_id,
    writer_actor: WRITER, outcome: { id: receipt.outcomeId, sha256: receipt.bodySha256, parent,
      url: `https://github.com/${REPOSITORY}/${parent.kind === 'issue' ? 'issues' : 'pull'}/${parent.number}#issuecomment-${receipt.outcomeId}` } };
}
function isMain() { try { return realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url)); } catch { return false; } }
if (isMain()) main().then(value => process.stdout.write(JSON.stringify(value) + '\n')).catch(error => {
  process.stdout.write(JSON.stringify({ error_code: /^[A-Z][A-Z0-9_]{0,79}$/.test(error?.code ?? '') ? error.code : 'MANUAL_PUBLICATION_FAILED' }) + '\n');
  process.exitCode = 1;
});
