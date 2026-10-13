import test from 'node:test';
import assert from 'node:assert/strict';
import { nextAdmissionStep } from '../src/admission-step.mjs';
import { digest } from '../src/execution-contract.mjs';

const admitted = (step, options = {}) => ({ envelope: { issueNumber: 42, step, runId: step + 100,
  attemptId: `run-${step + 100}`, route: 'manual', ...options.envelope }, outcome: { status: 'BLOCKED' }, ...options });

test('a charter, Decision and ready label do not allocate a Step before durable admission', () => {
  const records = [{ kind: 'decision', task: 42 }, { issueNumber: 42, labels: ['codex-ready-manual', 'step-9'] }];
  assert.deepEqual(nextAdmissionStep(records, 42), { step: 1, lineage: null });
  assert.deepEqual(nextAdmissionStep([], 42), { step: 1, lineage: null });
  assert.equal(records.length, 2);
});

test('a new execution after BLOCKED receives a fresh Step bound to the prior admitted attempt', () => {
  const previous = admitted(3);
  assert.deepEqual(nextAdmissionStep([previous], 42), { step: 4,
    lineage: { attempt: previous.envelope.attemptId, step: previous.envelope.step, sha256: digest(previous.envelope) } });
  assert.equal(previous.envelope.step, 3); assert.equal(previous.outcome.status, 'BLOCKED');
});

test('accepted execution completion advances allocation, while rejected admission does not consume a Step', () => {
  const records = [admitted(1, { outcome: { status: 'IMPLEMENTED_PENDING_FRESH_REVIEW' } }),
    admitted(2, { admissionBlock: { code: 'AUTHORITY_SOURCE_MISMATCH' } })];
  assert.equal(nextAdmissionStep(records, 42).step, 2);
  assert.deepEqual(nextAdmissionStep([records[1]], 42), { step: 1, lineage: null });
});

test('active/uncertain publication and execution boundaries prevent concurrent fresh admission', () => {
  for (const pending of [{ outcome: null }, { commentIntent: { key: 'outcome' } }, { prIntent: true },
    { publicationIntent: { head: 'a'.repeat(40) }, publishedHead: null },
    { publicationIntent: { head: 'a'.repeat(40) }, publishedHead: 'a'.repeat(40) },
    { lifecycleIntent: {} }, { handoffComplete: false }])
    assert.throws(() => nextAdmissionStep([admitted(1, pending)], 42), { code: 'PRIOR_EXECUTION_UNRESOLVED' });
});

test('allocation only counts successfully admitted executions of the same Task', () => {
  const foreign = admitted(999, { envelope: { issueNumber: 43, step: 999, runId: 999, attemptId: 'run-999' }, outcome: null });
  const rejected = { envelope: { issueNumber: 42 }, admissionBlock: { code: 'ROUTE_INVALID' } };
  assert.deepEqual(nextAdmissionStep([foreign, rejected], 42), { step: 1, lineage: null });
});

test('allocation resolves retained execution order by Step without changing history or creating another ledger', () => {
  const records = [admitted(2), admitted(1), admitted(4)];
  const before = structuredClone(records);
  const first = nextAdmissionStep(records, 42);
  assert.equal(first.step, 5);
  assert.deepEqual(nextAdmissionStep(records, 42), first);
  assert.deepEqual(records, before);
});

test('unknown old Step/run and overflow fail closed instead of guessing execution lineage', () => {
  for (const envelope of [{ issueNumber: 42, step: null, runId: 123 }, { issueNumber: 42, step: 0, runId: 123 },
    { issueNumber: 42, step: 1, runId: null }])
    assert.throws(() => nextAdmissionStep([admitted(1, { envelope })], 42), { code: 'PRIOR_ADMISSION_UNKNOWN' });
  assert.throws(() => nextAdmissionStep([admitted(1, { envelope: { issueNumber: 42, step: Number.MAX_SAFE_INTEGER,
    runId: 123, attemptId: 'run-123' } })], 42), { code: 'AUTHORITY_STEP_INVALID' });
  for (const [records, task] of [[null, 42], [[], 0], [[], -1]])
    assert.throws(() => nextAdmissionStep(records, task), { code: 'AUTHORITY_ADMISSION_INVALID' });
});
