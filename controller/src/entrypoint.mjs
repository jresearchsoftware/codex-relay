import { CONSUMER } from '../../consumer/consumer.mjs';
import { readFile } from 'node:fs/promises';
import { realpathSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { createLocalWriterAdapter } from './local-writer.mjs';
import { createOnDemandDispatchAdapter } from './github.mjs';
import { createAttemptStore } from './attempt-store.mjs';
import { runAttempt } from './attempt.mjs';
import { prepareCheckout, collectCheckout } from './attempt-runtime.mjs';
import { REPOSITORY, OWNER, causalEvidence } from './execution-contract.mjs';
import { emitAdmissionWarnings } from './outcome.mjs';
import { parseLaunchInputs, parseLabelLaunch } from './launch-metadata.mjs';

export async function main() {
  const event = JSON.parse(await readFile(process.env.GITHUB_EVENT_PATH, 'utf8'));
  if (event.repository?.full_name !== REPOSITORY || !['workflow_dispatch', 'issues', 'pull_request_target'].includes(process.env.GITHUB_EVENT_NAME)
    || event.sender?.login !== OWNER || process.env.GITHUB_REF !== `refs/heads/${CONSUMER.baseBranch}`) return { status: 'BLOCKED', code: 'OWNER_EVENT_REQUIRED' };
  const launch = process.env.GITHUB_EVENT_NAME === 'workflow_dispatch' ? parseLaunchInputs(event.inputs)
    : parseLabelLaunch(event, process.env.GITHUB_EVENT_NAME);
  const local = createLocalWriterAdapter();
  const broker = { invoke: request => local.invoke({ ...request, workflowReadToken: process.env.GITHUB_TOKEN }) };
  let admitted;
  try {
    admitted = await broker.invoke({ operation: 'admit', runId: Number(process.env.GITHUB_RUN_ID), workflowReadToken: process.env.GITHUB_TOKEN,
      ...launch });
  } catch (error) {
    // These live admission decisions prove no new execution was authorized.
    // The Actions warning is the safe surface when no Writer target is admitted.
    if (error.code === 'OWNER_RUN_NOT_ADMITTED') return { status: 'BLOCKED', code: error.code };
    throw error;
  }
  emitAdmissionWarnings(admitted.envelope?.admission?.warnings ?? admitted.envelope?.warnings);
  if (admitted.status === 'BLOCKED') return admitted;
  const dispatcher = createOnDemandDispatchAdapter();
  return runAttempt({ envelope: admitted.envelope, admissionResumed: admitted.resumed === true, broker,
    journal: createAttemptStore(CONSUMER.paths.attemptRoot),
    prepare: prepareCheckout, execute: e => dispatcher.dispatch(e), collect: collectCheckout });
}
export async function reportRoutingResult(run, { write = value => process.stdout.write(value), writeError = value => process.stderr.write(value) } = {}) {
  try {
    const value = await run();
    if (value?.status === 'BLOCKED') {
      const code = value.code ?? value.envelope?.admissionBlock?.code;
      writeError(`::warning title=Codex outcome::BLOCKED; task remains incomplete${/^[A-Z][A-Z0-9_]{0,79}$/.test(code ?? '') ? ` (${code})` : ''}. Reconcile the terminal Outcome before another attempt.\n`);
    }
    write(JSON.stringify(value) + '\n');
    return 0;
  } catch (error) {
    writeError(JSON.stringify({ status: 'blocked', orchestration: 'FAILED', code: /^[A-Z][A-Z0-9_]{0,79}$/.test(error?.code ?? '') ? error.code : 'ROUTING_FAILED', diagnostic: error.details?.diagnostic ?? causalEvidence(error) }) + '\n');
    return 1;
  }
}
function isMain() { try { return realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url)); } catch { return false; } }
if (isMain()) reportRoutingResult(main).then(code => { process.exitCode = code; });
