import { digest, positive, VERSION, fail } from './execution-contract.mjs';

const hash = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const reasons = new Set(['task-completed', 'task-not-planned', 'owner-withdrawal', 'route-switch']);
const effects = ['controllerLifecycle', 'outcome', 'manualSubmission', 'manualResultAuthorization',
  'publicationIntent', 'commentIntent', 'lifecycleIntent', 'relationshipIntent', 'prIntent',
  'publishedHead', 'finalHead', 'successOutcomeIntent', 'readinessIntent',
  'prepublicationRecovery', 'publicationRecoveries', 'collection', 'execution'];
const readyEffectPending = record => record.readyConsumption !== undefined && record.readyConsumption !== null
  && record.readyConsumption.status !== 'consumed';

function originalPullRequestBinding(record) {
  const e = record.envelope;
  const bindings = [e.target === 'pull_request' ? e.number : null,
    e.continuation?.pullRequest, e.request?.existing_pr].filter(value => value !== undefined && value !== null);
  if (!bindings.every(positive) || new Set(bindings).size > 1) return false;
  // Remembering an existing admitted PR is not a PR-creation reservation.
  // A result discovered or created later needs its original publication proof.
  return record.prNumber === undefined || record.prNumber === null
    || positive(record.prNumber) && bindings.length > 0 && bindings[0] === record.prNumber;
}

export async function manualAttemptHasConflictingActivity(record, { journal } = {}) {
  if (record?.envelope?.route !== 'manual') return false;
  if (['controllerLifecycle', 'publicationIntent', 'commentIntent', 'lifecycleIntent',
    'relationshipIntent', 'readinessIntent', 'successOutcomeIntent', 'prepublicationRecovery',
    'publicationRecoveries', 'collection', 'execution'].some(key => Boolean(record[key]))
    || record.handoffComplete === false || readyEffectPending(record)) return true;
  const e = record.envelope;
  return Boolean(journal && await journal.get(e.runId, e.repository));
}

// This is lifecycle evidence, never a substitute terminal execution receipt.
// An unfinished trusted publication or observed worker must retain its original
// reconciliation path even when the Task no longer authorizes the handoff.
export function manualAttemptHasNoPendingEffects(record) {
  const e = record?.envelope;
  if (!e || e.version !== VERSION || e.route !== 'manual' || !positive(e.runId)
    || !positive(e.issueNumber) || e.attemptId !== `run-${e.runId}`
    || typeof e.repository !== 'string' || !e.repository || !hash(e.consumerDigest)
    || !['issue', 'pull_request'].includes(e.target) || !positive(e.number)
    || effects.some(key => Boolean(record[key])) || record.handoffComplete === false || readyEffectPending(record)
    || !originalPullRequestBinding(record)) return false;
  if (record.commentBodies !== undefined && record.commentBodies !== null) {
    const bodies = record.commentBodies;
    if (typeof bodies !== 'object' || Array.isArray(bodies)
      || Object.keys(bodies).some(key => key !== 'handoff')) return false;
    const handoff = bodies.handoff;
    if (handoff && (!positive(handoff.number) || !hash(handoff.sha256)
      || handoff.rendererVersion !== 'human-v1'
      || handoff.number !== (e.target === 'pull_request' ? e.number : e.issueNumber))) return false;
  }
  return true;
}

export async function historicalManualAttemptDisposition(record, { journal, resolve } = {}) {
  if (!resolve || !manualAttemptHasNoPendingEffects(record)) return null;
  // Manual handoffs ordinarily have no worker journal at all. Any retained
  // journal is conflicting execution evidence, not absence of execution.
  const e = record.envelope;
  if (journal && await journal.get(e.runId, e.repository)) return null;
  const recordDigest = digest(record), envelopeDigest = digest(e);
  const observation = await resolve(record);
  if (observation === null || observation === undefined) return null;
  if (observation.disposition !== 'historical' || !reasons.has(observation.reason)
    || observation.repository !== e.repository || observation.issueNumber !== e.issueNumber
    || observation.runId !== e.runId || observation.attemptId !== e.attemptId
    || observation.consumerDigest !== e.consumerDigest || observation.envelopeDigest !== envelopeDigest
    || observation.recordDigest !== recordDigest || !hash(observation.evidenceDigest)
    || digest(record) !== recordDigest) fail('ADMISSION_MANUAL_DISPOSITION_INVALID');
  if (journal && await journal.get(e.runId, e.repository)) return null;
  return observation;
}
