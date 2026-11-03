import { digest, positive, fail } from './execution-contract.mjs';
import { canonicalAuthorityJson, extractAuthorityRecord, sha256Body } from '../../contracts/src/github-authority.mjs';
import { manualAttemptHasNoPendingEffects } from './manual-attempt-disposition.mjs';

const same = (left, right) => canonicalAuthorityJson(left) === canonicalAuthorityJson(right);
const identity = value => value && positive(value.id) && typeof value.login === 'string'
  && value.login.length > 0 && value.login.length <= 140 && ['User', 'Bot'].includes(value.type);
const hash = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const reasons = new Set(['owner-withdrawal', 'route-switch']);
const sourceHash = value => sha256Body(canonicalAuthorityJson(value));

function recordBinding(record, repository) {
  if (!manualAttemptHasNoPendingEffects(record)) return null;
  const e = record.envelope;
  if (repository !== undefined && e.repository !== repository) return null;
  return { repository: e.repository, issueNumber: e.issueNumber, runId: e.runId,
    attemptId: e.attemptId, consumerDigest: e.consumerDigest,
    envelopeDigest: digest(e), recordDigest: digest(record) };
}

function validateTask(value, binding) {
  const issue = value?.issue;
  if (!value || value.repository !== binding.repository || value.task !== binding.issueNumber
    || !issue || !positive(issue.id) || issue.number !== binding.issueNumber
    || !['open', 'closed'].includes(issue.state)
    || ![null, 'completed', 'not_planned', 'reopened'].includes(issue.state_reason)
    || typeof issue.body !== 'string' || Buffer.byteLength(issue.body, 'utf8') > 100000
    || !identity(value.owner) || value.owner.type !== 'User'
    || issue.closed_by !== null && !identity(issue.closed_by)
    || !Array.isArray(value.lifecycle) || !Array.isArray(value.decisions)
    || value.decisions.length > 500
    || value.trustedClosers !== undefined && (!Array.isArray(value.trustedClosers)
      || !value.trustedClosers.every(identity))) fail('HISTORICAL_TASK_SOURCE_INVALID');
  let previousEvent = 0;
  for (const event of value.lifecycle) {
    if (!positive(event.id) || event.id <= previousEvent || !['closed', 'reopened'].includes(event.event)
      || !identity(event.actor) || typeof event.created_at !== 'string'
      || !Number.isFinite(Date.parse(event.created_at))) fail('HISTORICAL_TASK_SOURCE_INVALID');
    previousEvent = event.id;
  }
  const latestEvent = value.lifecycle.at(-1);
  if (issue.state === 'closed' && (!latestEvent || latestEvent.event !== 'closed'
    || !same(latestEvent.actor, issue.closed_by))
    || issue.state === 'open' && (issue.closed_by !== null || latestEvent?.event === 'closed')) {
    fail('HISTORICAL_TASK_SOURCE_INVALID');
  }
  let previousDecision = 0;
  for (const item of value.decisions) {
    const reference = item?.reference;
    if (!reference || reference.kind !== 'issue-comment' || !positive(reference.id)
      || reference.id <= previousDecision || reference.parent?.kind !== 'issue'
      || reference.parent.number !== binding.issueNumber || !hash(reference.sha256)
      || typeof item.body !== 'string' || sha256Body(item.body) !== reference.sha256) {
      fail('HISTORICAL_TASK_SOURCE_INVALID');
    }
    // This is historical evidence, not a fresh execution-authority resolution.
    // Preserve its original charter hash even if the current owner Issue body
    // differs; both exact byte sources remain bound by the snapshot fingerprint.
    const decision = extractAuthorityRecord(item.body, { repository: binding.repository,
      task: binding.issueNumber });
    if (decision?.kind !== 'decision' || !same(decision.parent, reference.parent)) fail('HISTORICAL_TASK_SOURCE_INVALID');
    previousDecision = reference.id;
  }
  return value;
}

function selectedSources(value, sources) {
  if (!Array.isArray(sources) || sources.length === 0 || sources.length > 500) fail('HISTORICAL_TASK_ACKNOWLEDGEMENT_INVALID');
  const keys = new Set();
  const selected = sources.map(source => {
    const active = value.decisions.find(item => same(item.reference, source));
    if (!active || keys.has(active.reference.id)) fail('HISTORICAL_TASK_ACKNOWLEDGEMENT_INVALID');
    keys.add(active.reference.id);
    return structuredClone(active.reference);
  });
  return selected.sort((left, right) => left.id - right.id);
}

const acknowledgementEvidence = value => sourceHash({ binding: value.binding, sourceDigest: value.sourceDigest,
  reason: value.reason, sources: value.sources });

// readTask is a trusted native adapter, not caller/worker JSON. It must read the
// complete closed/reopened timeline and active Task-scoped Decisions, verify the
// repository and native User/Bot identities, and validate Decision supersession.
// Every supplied field is fingerprinted; an adapter may include other verified
// authority records to invalidate acknowledgements when that authority changes.
// The protected cache records a semantic interpretation of existing authority;
// it does not create authority, terminate an attempt or supply an Outcome.
export function createHistoricalTaskDisposition({ readTask, cache = new Map(), repository,
  allowAcknowledgement = false } = {}) {
  if (typeof readTask !== 'function' || typeof cache?.get !== 'function'
    || typeof cache?.set !== 'function') fail('HISTORICAL_TASK_ADAPTER_INVALID');
  const key = binding => `${binding.repository}:${binding.runId}`;
  async function current(record) {
    const binding = recordBinding(record, repository);
    if (!binding) return null;
    const task = validateTask(await readTask(binding.repository, binding.issueNumber, record), binding);
    if (!same(binding, recordBinding(record, repository))) fail('HISTORICAL_TASK_RECORD_CHANGED');
    return { binding, task, sourceDigest: sourceHash(task) };
  }
  return {
    async resolve(record) {
      // Always read current GitHub facts, including when an acknowledgement is
      // cached. Failed or incomplete reads have no offline acceptance fallback.
      const observed = await current(record);
      if (!observed) return null;
      const { binding, task, sourceDigest } = observed;
      const closer = [task.owner, ...(task.trustedClosers ?? [])]
        .some(candidate => same(candidate, task.issue.closed_by));
      if (task.issue.state === 'closed' && closer
        && ['completed', 'not_planned'].includes(task.issue.state_reason)) {
        return { disposition: 'historical', reason: task.issue.state_reason === 'completed'
          ? 'task-completed' : 'task-not-planned', ...binding, evidenceDigest: sourceDigest };
      }
      if (task.issue.state !== 'open') return null;
      const acknowledgement = await cache.get(key(binding));
      if (!acknowledgement || acknowledgement.version !== 1 || !reasons.has(acknowledgement.reason)
        || !same(acknowledgement.binding, binding) || acknowledgement.sourceDigest !== sourceDigest
        || !hash(acknowledgement.evidenceDigest)
        || acknowledgement.evidenceDigest !== acknowledgementEvidence(acknowledgement)) return null;
      try { selectedSources(task, acknowledgement.sources); } catch { return null; }
      return { disposition: 'historical', reason: acknowledgement.reason, ...binding,
        evidenceDigest: acknowledgement.evidenceDigest };
    },
    async acknowledge(record, { reason, sources } = {}) {
      // Only a specifically enabled protected owner adapter may interpret prose
      // authority. No native admission, worker input or ordinary CLI enables it.
      if (allowAcknowledgement !== true) fail('HISTORICAL_TASK_ACKNOWLEDGEMENT_FORBIDDEN');
      if (!reasons.has(reason)) fail('HISTORICAL_TASK_ACKNOWLEDGEMENT_INVALID');
      const observed = await current(record);
      if (!observed || observed.task.issue.state !== 'open') fail('HISTORICAL_TASK_ACKNOWLEDGEMENT_INVALID');
      const acknowledgement = { version: 1, binding: observed.binding, sourceDigest: observed.sourceDigest,
        reason, sources: selectedSources(observed.task, sources) };
      acknowledgement.evidenceDigest = acknowledgementEvidence(acknowledgement);
      await cache.set(key(observed.binding), structuredClone(acknowledgement));
      return structuredClone(acknowledgement);
    }
  };
}
