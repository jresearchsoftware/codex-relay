import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createAdmissionControl, manualAdmissionComplete } from '../src/admission-control.mjs';
import { createAttemptStore } from '../src/attempt-store.mjs';
import { digest, VERSION } from '../src/execution-contract.mjs';
import { manualAttemptHasNoPendingEffects, manualAttemptHasConflictingActivity } from '../src/execution-effects.mjs';
import { admissionBinding, authoritySourceDigest, createAdmissionSnapshot, sha256Body } from '../../contracts/src/github-authority.mjs';

const oldDigest = 'a'.repeat(64), nextDigest = 'b'.repeat(64), target = 'c'.repeat(40);
const operationId = '12345678-1234-1234-1234-123456789abc';
const record = runId => ({ envelope: { version: VERSION, repository: 'example/sample',
  runId, attemptId: `run-${runId}`, consumerDigest: oldDigest, route: 'manual',
  issueNumber: 42, target: 'issue', number: 42 }, outcome: null });
async function fixture(t) {
  const root = await mkdtemp(join(tmpdir(), 'relay-manual-disposition-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const store = createAttemptStore(join(root, 'records'), { repository: 'example/sample' });
  const journal = createAttemptStore(join(root, 'journals'), { repository: 'example/sample' });
  const create = consumerDigest => createAdmissionControl({ root, consumerDigest, store, journal,
    protectedRoot: false });
  const control = create(oldDigest); await control.initialize();
  return { root, store, journal, control, create };
}

function currentManualReceipt(runId) {
  const body = 'Authority model: github-native-v1\nIssue closure policy: keep-open';
  const parent = { kind: 'issue', number: 42 };
  const source = { charter: { kind: 'issue-body', id: 42, parent, sha256: sha256Body(body) },
    decisions: [], change_request: null, compatibility_request: null };
  const authority = { ...source, sha256: authoritySourceDigest(source) };
  const request = createAdmissionSnapshot({ authority, request: { repository: 'example/sample', task: 42,
    charter_sha256: sha256Body(body), purpose: 'Bounded qualification', scope: [], model: 'gpt-6.1-sol',
    effort: 'xhigh', subagents: false, validation: ['diff-check'], boundaries: [], branch: null,
    base_sha: null, starting_head: null, existing_pr: null, issue_closure_policy: 'keep-open',
    continuation: { hold: false, next: null }, route: 'manual' } }, { step: 1, attempt: `run-${runId}`, runId: String(runId) });
  const result = { schema_version: '4.0', kind: 'outcome', repository: 'example/sample', task: 42,
    parent, charter_sha256: sha256Body(body), attempt: `run-${runId}`, step: 1, status: 'implemented',
    result: { kind: 'qualification', revision: null, identities: [{ kind: 'github-actions-run', id: String(runId) }] },
    warnings: [], limitations: [], summary: 'Bounded result.', authority, admission: admissionBinding(request) };
  const current = { ...record(runId), envelope: { ...record(runId).envelope, step: 1, request },
    manualSubmission: { sha256: sha256Body(JSON.stringify(result)), parent, publishedResult: result },
    outcome: { manual: true, status: 'IMPLEMENTED_PENDING_FRESH_REVIEW', head: null, prNumber: null,
      outcomeId: runId + 1000, bodySha256: 'e'.repeat(64) } };
  return current;
}

test('known original CR and Issue continuation PR identities do not imply unfinished creation or execution', async t => {
  const f = await fixture(t);
  const cr = { ...record(71), envelope: { ...record(71).envelope, target: 'pull_request', number: 55,
    request: { kind: 'admission', existing_pr: 55 } }, prNumber: 55 };
  const continuation = { ...record(72), envelope: { ...record(72).envelope,
    continuation: { pullRequest: 56 }, request: { kind: 'admission', existing_pr: 56 } }, prNumber: 56 };
  await f.store.put(71, cr); await f.store.put(72, continuation);
  const result = await f.control.preflightConsumerTransition({ desiredDigest: nextDigest });
  assert.equal(result.eligible, true); assert.deepEqual(result.unknown, []);
  assert.equal(Object.hasOwn(result, 'manualAttempts'), false);
  assert.deepEqual(await f.store.get(71), cr); assert.deepEqual(await f.store.get(72), continuation);
  for (const fields of [
    { prNumber: 57 }, { prNumber: 0 }, { prIntent: true }, { publishedHead: target },
    { envelope: { ...cr.envelope, continuation: { pullRequest: 57 } } },
    { envelope: { ...cr.envelope, request: { existing_pr: 57 } } },
    { envelope: { ...cr.envelope, request: { existing_pr: 0 } } }
  ]) assert.equal(manualAttemptHasNoPendingEffects({ ...cr, ...fields }), false);
  assert.equal(manualAttemptHasNoPendingEffects({ ...record(73), prNumber: 55 }), false);
});

test('worker evidence and every unfinished publication boundary hold lifecycle without Task-history reads', async t => {
  const f = await fixture(t);
  const boundaries = [
    { controllerLifecycle: { version: 1, status: 'active' } },
    { publicationIntent: { head: target } }, { commentIntent: { key: 'handoff' } },
    { lifecycleIntent: { draft: true } }, { relationshipIntent: { number: 45 } },
    { prIntent: true }, { publishedHead: target }, { finalHead: target }, { prNumber: 45 },
    { successOutcomeIntent: { head: target } }, { readinessIntent: { head: target } },
    { prepublicationRecovery: { complete: false } }, { manualSubmission: { sha256: oldDigest } },
    { manualResultAuthorization: { id: 1, sha256: oldDigest } }, { outcome: { status: 'BLOCKED' } },
    { handoffComplete: false }, { commentBodies: { outcome: { number: 42 } } },
    { readyConsumption: { status: 'deleting' } }, { readyConsumption: { status: 'uncertain' } }
  ];
  for (const [index, fields] of boundaries.entries()) await f.store.put(index + 100, { ...record(index + 100), ...fields });
  await f.store.put(99, record(99)); await f.journal.put(99, { envelope: record(99).envelope,
    execution: { reserved: true, returned: false } });
  const result = await f.control.preflightConsumerTransition({ desiredDigest: nextDigest });
  assert.equal(result.eligible, false); assert.equal(result.unknown.length, boundaries.length + 1);
});

test('completed manual receipt never hides contradictory live execution or pending publication', async t => {
  const f = await fixture(t);
  const complete = currentManualReceipt(71);
  assert.equal(manualAdmissionComplete(complete), true);
  for (const [index, fields] of [
    { controllerLifecycle: { version: 1, status: 'active' } },
    { relationshipIntent: { number: 45 } }, { prepublicationRecovery: { complete: false } }
  ].entries()) {
    const runId = index + 71;
    await f.store.put(runId, { ...currentManualReceipt(runId), ...fields });
  }
  const withJournal = currentManualReceipt(74);
  await f.store.put(74, withJournal);
  await f.journal.put(74, { envelope: withJournal.envelope, execution: { reserved: true, returned: false } });
  const result = await f.control.preflightConsumerTransition({ desiredDigest: nextDigest });
  assert.equal(result.eligible, false); assert.deepEqual(result.unknown, [71, 72, 73, 74]);
});

test('global drain blocks incomplete trusted manual result progress without a disposition resolver', async t => {
  const f = await fixture(t);
  const handoff = record(70);
  const knownPr = { ...record(71), envelope: { ...record(71).envelope,
    continuation: { pullRequest: 55 } }, prNumber: 55 };
  await f.store.put(70, handoff); await f.store.put(71, knownPr);
  const progress = [
    { manualSubmission: { sha256: oldDigest } },
    { manualResultAuthorization: { id: 123, sha256: oldDigest } },
    { prIntent: true }, { outcome: { status: 'BLOCKED' } },
    { publishedHead: target }, { finalHead: target }, { prNumber: 55 },
    { commentBodies: { outcome: { number: 42, sha256: oldDigest, rendererVersion: 'human-v1' } } }
  ];
  for (const [index, fields] of progress.entries()) await f.store.put(index + 80, { ...record(index + 80), ...fields });
  const status = await f.control.status();
  assert.deepEqual(status.active, []);
  assert.deepEqual(status.unknown, progress.map((_, index) => index + 80));
  await f.control.quiesce({ operationId, target });
  await assert.rejects(f.control.drained({ operationId }), { code: 'ADMISSION_DRAIN_UNKNOWN' });
  assert.deepEqual(await f.store.get(70), handoff); assert.deepEqual(await f.store.get(71), knownPr);
});

test('exact current manual receipts release global drain despite their recorded result progress', async t => {
  const f = await fixture(t);
  const first = currentManualReceipt(71), second = currentManualReceipt(72);
  for (const value of [first, second]) {
    assert.equal(manualAdmissionComplete(value), true);
    await f.store.put(value.envelope.runId, value);
  }
  assert.deepEqual((await f.control.status()).unknown, []);
  await f.control.quiesce({ operationId, target });
  assert.equal((await f.control.drained({ operationId })).drained, true);
  assert.deepEqual(await f.store.get(71), first); assert.deepEqual(await f.store.get(72), second);
});

test('old-digest handoffs stay historical while malformed receipts and later worker effects still hold drain', async t => {
  const f = await fixture(t);
  const clean = record(71); clean.envelope.consumerDigest = nextDigest;
  await f.store.put(71, clean);
  const before = await readFile(join(f.root, 'records', '71.json'));
  assert.equal((await f.control.preflightConsumerTransition({ desiredDigest: nextDigest })).eligible, true);
  assert.deepEqual((await f.control.status()).unknown, []);
  const malformed = structuredClone(clean); malformed.commentBodies = { unsupported: {} };
  await f.store.put(71, malformed);
  assert.deepEqual((await f.control.status()).unknown, [71]);
  await f.store.put(71, clean);
  await f.journal.put(71, { envelope: clean.envelope, execution: { reserved: true, returned: false } });
  assert.deepEqual((await f.control.status()).unknown, [71]);
  assert.equal((await f.control.preflightConsumerTransition({ desiredDigest: nextDigest })).eligible, false);
  assert.deepEqual(await readFile(join(f.root, 'records', '71.json')), before);
  assert.equal((await f.store.get(71)).outcome, null);
});

test('unresolved-Task manual PR refusal is idle across status, drain and consumer transition', async t => {
  const f = await fixture(t), admissionBlock = { code: 'CANONICAL_ISSUE_AMBIGUOUS' };
  const refused = { envelope: { ...record(81).envelope, route: 'manual', target: 'pull_request',
    number: 55, issueNumber: null, request: null, branch: null, startHead: null, authorityDigest: null,
    admissionBlock }, admissionBlock };
  await assert.rejects(f.store.put(81, { ...refused, envelope: { ...refused.envelope, repository: null } }), { code: 'ATTEMPT_REPOSITORY_MISMATCH' });
  assert.equal(await manualAttemptHasConflictingActivity({ ...refused, envelope: { ...refused.envelope, repository: null } }, { journal: f.journal }), true);
  await f.store.put(81, refused);
  const before = await readFile(join(f.root, 'records', '81.json'));
  assert.deepEqual((await f.control.status()).unknown, []);
  assert.equal((await f.control.preflightConsumerTransition({ desiredDigest: nextDigest })).eligible, true);
  await f.control.quiesce({ operationId, target });
  assert.equal((await f.control.drained({ operationId })).drained, true);
  for (const change of [
    { commentIntent: { key: 'outcome' } }, { manualSubmission: { sha256: oldDigest } },
    { readyConsumption: { status: 'uncertain' } }, { publicationRecoveries: [{}] },
    { outcome: {} }, { execution: { reserved: true } },
    { envelope: { ...refused.envelope, attemptId: 'run-82' } },
    { envelope: { ...refused.envelope, issueNumber: 42, admissionBlock: { code: 'CHANGED' } } },
    { envelope: { ...refused.envelope, admissionBlock: { code: 'DIFFERENT' } } }
  ]) {
    await f.store.put(81, { ...refused, ...change });
    assert.deepEqual((await f.control.status()).unknown, [81]);
    assert.equal((await f.control.preflightConsumerTransition({ desiredDigest: nextDigest })).eligible, false);
  }
  await f.store.put(81, refused);
  await f.journal.put(81, { envelope: refused.envelope, execution: { reserved: true } });
  assert.deepEqual((await f.control.status()).unknown, [81]);
  assert.deepEqual(await readFile(join(f.root, 'records', '81.json')), before);
});
