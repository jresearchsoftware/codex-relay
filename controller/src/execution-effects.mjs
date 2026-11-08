import { positive, VERSION } from './execution-contract.mjs';

const hash = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const effects = ['controllerLifecycle', 'outcome', 'manualSubmission', 'manualResultAuthorization',
  'publicationIntent', 'commentIntent', 'lifecycleIntent', 'relationshipIntent', 'prIntent',
  'publishedHead', 'finalHead', 'successOutcomeIntent', 'readinessIntent',
  'prepublicationRecovery', 'publicationRecoveries', 'collection', 'execution'];
const readyEffectPending = record => record.readyConsumption !== undefined && record.readyConsumption !== null
  && record.readyConsumption.status !== 'consumed';

// These are unresolved external effects, independent of Task status or digest.
// A known released physical runner slot is classified separately.
export function attemptHasPendingPublicationEffects(record) {
  return ['publicationIntent', 'commentIntent', 'lifecycleIntent', 'relationshipIntent',
    'readinessIntent', 'successOutcomeIntent'].some(key => Boolean(record[key])) || readyEffectPending(record);
}

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
  // Refusal precedes Task resolution. Its strict effect predicate also checks
  // the original journal; missing Task identity alone is not execution.
  if (record.admissionBlock) {
    const { preAdmissionRefusalHasNoPendingEffects, manualAdmissionComplete } = await import('./admission-control.mjs');
    if (await preAdmissionRefusalHasNoPendingEffects(record, { journal })) return false;
    if (!manualAdmissionComplete(record)) return true;
  }
  if (['controllerLifecycle', 'publicationIntent', 'commentIntent', 'lifecycleIntent',
    'relationshipIntent', 'readinessIntent', 'successOutcomeIntent', 'prepublicationRecovery',
    'publicationRecoveries', 'collection', 'execution'].some(key => Boolean(record[key]))
    || record.handoffComplete === false || readyEffectPending(record)) return true;
  const resultProgress = ['prIntent', 'manualSubmission', 'manualResultAuthorization',
    'outcome', 'publishedHead', 'finalHead'].some(key => Boolean(record[key]))
    || Boolean(record.commentBodies?.outcome) || !originalPullRequestBinding(record);
  if (resultProgress) {
    // A mere handoff does not occupy a worker or hold a code-only upgrade.
    // Once trusted result/publication progress exists, retain that boundary
    // until its exact native receipt proves completion. Lazy loading keeps
    // this lifecycle guard separate from the receipt predicate's own module.
    const { manualAdmissionComplete } = await import('./admission-control.mjs');
    if (!manualAdmissionComplete(record)) return true;
  }
  if (!resultProgress && !manualAttemptHasNoPendingEffects(record)) return true;
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
    || typeof e.repository !== 'string' || !/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(e.repository) || !hash(e.consumerDigest)
    || !['issue', 'pull_request'].includes(e.target) || !positive(e.number)
    || e.target === 'issue' && e.issueNumber !== e.number
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
