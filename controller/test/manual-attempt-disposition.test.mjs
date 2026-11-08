import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createAdmissionControl, manualAdmissionComplete } from '../src/admission-control.mjs';
import { createAttemptStore } from '../src/attempt-store.mjs';
import { digest, VERSION } from '../src/execution-contract.mjs';
import { historicalManualAttemptDisposition, manualAttemptHasNoPendingEffects } from '../src/manual-attempt-disposition.mjs';
import { admissionBinding, authoritySourceDigest, createAdmissionSnapshot, sha256Body } from '../../contracts/src/github-authority.mjs';

const oldDigest = 'a'.repeat(64), nextDigest = 'b'.repeat(64), target = 'c'.repeat(40);
const operationId = '12345678-1234-1234-1234-123456789abc';
const record = runId => ({ envelope: { version: VERSION, repository: 'example/sample',
  runId, attemptId: `run-${runId}`, consumerDigest: oldDigest, route: 'manual',
  issueNumber: 42, target: 'issue', number: 42 }, outcome: null });
const observation = (value, reason = 'task-completed') => ({ disposition: 'historical', reason,
  repository: value.envelope.repository, issueNumber: value.envelope.issueNumber,
  runId: value.envelope.runId, attemptId: value.envelope.attemptId,
  consumerDigest: value.envelope.consumerDigest, envelopeDigest: digest(value.envelope),
  recordDigest: digest(value), evidenceDigest: 'd'.repeat(64) });

async function fixture(t, resolve) {
  const root = await mkdtemp(join(tmpdir(), 'relay-manual-disposition-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const store = createAttemptStore(join(root, 'records'), { repository: 'example/sample' });
  const journal = createAttemptStore(join(root, 'journals'), { repository: 'example/sample' });
  const create = consumerDigest => createAdmissionControl({ root, consumerDigest, store, journal,
    protectedRoot: false, manualAttemptDisposition: resolve });
  const control = create(oldDigest); await control.initialize();
  return { root, store, journal, control, create };
}

test('historical disposition retains issued or unissued handoff bytes without fabricating completion', async t => {
  let reads = 0;
  const f = await fixture(t, async value => { reads++; return observation(value); });
  for (const runId of [71, 93]) {
    const value = record(runId);
    if (runId === 71) {
      value.commentBodies = { handoff: { number: 42, sha256: 'e'.repeat(64), rendererVersion: 'human-v1' } };
      value.handoffComplete = true;
      value.readyConsumption = { status: 'consumed', eventId: 100, removalEventId: 101 };
    }
    await f.store.put(runId, value);
  }
  const original = await Promise.all([71, 93].map(runId => readFile(join(f.root, 'records', `${runId}.json`))));
  const gate = await readFile(join(f.root, 'admission-v1.json'));
  const result = await f.control.preflightConsumerTransition({ desiredDigest: nextDigest });
  assert.equal(result.eligible, true); assert.deepEqual(result.unknown, []);
  assert.deepEqual(result.manualAttempts, { historical: [], actionable: [] });
  assert.equal(reads, 0);
  assert.deepEqual(await readFile(join(f.root, 'admission-v1.json')), gate);
  for (const [index, runId] of [71, 93].entries()) {
    const saved = await f.store.get(runId);
    assert.equal(saved.outcome, null); assert.equal(manualAdmissionComplete(saved), false);
    assert.deepEqual(await readFile(join(f.root, 'records', `${runId}.json`)), original[index]);
  }
});

test('status separates missing historical receipts from actionable attempts without inventing automatic activity', async t => {
  const f = await fixture(t, async value => value.envelope.runId === 71 ? observation(value, 'owner-withdrawal') : null);
  await f.store.put(71, record(71)); await f.store.put(93, record(93));
  const status = await f.control.status();
  assert.deepEqual(status.active, []); assert.deepEqual(status.unknown, []);
  assert.deepEqual(status.manualAttempts, { historical: [{ runId: 71, issueNumber: 42,
    reason: 'owner-withdrawal' }], actionable: [93] });
  const preflight = await f.control.preflightConsumerTransition({ desiredDigest: nextDigest });
  assert.equal(preflight.eligible, true); assert.deepEqual(preflight.unknown, []);
});

test('optional historical diagnosis does not become idle transition authority', async t => {
  let unavailable = true;
  const f = await fixture(t, async value => {
    if (unavailable) throw Object.assign(new Error('native unavailable'), { code: 'HISTORICAL_TASK_AUTHORITY_UNAVAILABLE' });
    return observation(value);
  });
  await f.store.put(71, record(71));
  const status = await f.control.status();
  assert.deepEqual(status.active, []); assert.deepEqual(status.unknown, []);
  assert.deepEqual(status.manualAttempts, { historical: [], actionable: [71], errors: [
    { runId: 71, code: 'HISTORICAL_TASK_AUTHORITY_UNAVAILABLE' }
  ] });
  assert.equal((await f.control.preflightConsumerTransition({ desiredDigest: oldDigest })).eligible, true);
  assert.equal((await f.control.preflightConsumerTransition({ desiredDigest: nextDigest })).eligible, true);
  await f.control.quiesce({ operationId, target });
  assert.equal((await f.control.drained({ operationId })).drained, true);
  await f.control.checkConsumerTransition({ operationId, target });
  unavailable = false;
  const next = f.create(nextDigest); await next.transitionConsumer({ operationId, previousDigest: oldDigest, target });
  unavailable = true;
  assert.deepEqual((await next.status()).unknown, []);
});

test('status does not suppress invalid authority, unsafe caches, invalid dispositions or unreadable journals', async t => {
  for (const code of ['HISTORICAL_TASK_AUTHORITY_INVALID', 'HISTORICAL_TASK_CACHE_UNSAFE',
    'ADMISSION_MANUAL_DISPOSITION_INVALID']) {
    const f = await fixture(t, async () => { throw Object.assign(new Error(code), { code }); });
    await f.store.put(71, record(71)); await assert.rejects(f.control.status(), { code });
  }
  const f = await fixture(t, async value => observation(value));
  await f.store.put(71, record(71));
  const control = createAdmissionControl({ root: f.root, consumerDigest: oldDigest, store: f.store,
    journal: { get: async () => { throw Object.assign(new Error('unreadable'), { code: 'JOURNAL_UNREADABLE' }); } },
    protectedRoot: false, manualAttemptDisposition: async value => observation(value) });
  await assert.rejects(control.status(), { code: 'JOURNAL_UNREADABLE' });
});

test('known original CR and Issue continuation PR identities do not imply unfinished creation or execution', async t => {
  const f = await fixture(t, async value => observation(value,
    value.envelope.target === 'pull_request' ? 'task-completed' : 'route-switch'));
  const cr = { ...record(71), envelope: { ...record(71).envelope, target: 'pull_request', number: 55,
    request: { kind: 'admission', existing_pr: 55 } }, prNumber: 55 };
  const continuation = { ...record(72), envelope: { ...record(72).envelope,
    continuation: { pullRequest: 56 }, request: { kind: 'admission', existing_pr: 56 } }, prNumber: 56 };
  await f.store.put(71, cr); await f.store.put(72, continuation);
  const result = await f.control.preflightConsumerTransition({ desiredDigest: nextDigest });
  assert.equal(result.eligible, true); assert.deepEqual(result.unknown, []);
  assert.deepEqual(result.manualAttempts.historical, []);
  assert.deepEqual(await f.store.get(71), cr); assert.deepEqual(await f.store.get(72), continuation);
  for (const fields of [
    { prNumber: 57 }, { prNumber: 0 }, { prIntent: true }, { publishedHead: target },
    { envelope: { ...cr.envelope, continuation: { pullRequest: 57 } } },
    { envelope: { ...cr.envelope, request: { existing_pr: 57 } } },
    { envelope: { ...cr.envelope, request: { existing_pr: 0 } } }
  ]) assert.equal(manualAttemptHasNoPendingEffects({ ...cr, ...fields }), false);
  assert.equal(manualAttemptHasNoPendingEffects({ ...record(73), prNumber: 55 }), false);
});

test('reopening historical Tasks cannot reacquire idle lifecycle resources', async t => {
  let historical = true, reads = 0;
  const f = await fixture(t, async value => { reads++; return historical ? observation(value, 'task-not-planned') : null; });
  await f.store.put(71, record(71));
  assert.equal((await f.control.preflightConsumerTransition({ desiredDigest: nextDigest })).eligible, true);
  await f.control.quiesce({ operationId, target }); await f.control.drained({ operationId });
  historical = false;
  await f.control.checkConsumerTransition({ operationId, target });
  historical = true; await f.control.checkConsumerTransition({ operationId, target });
  const next = f.create(nextDigest);
  await next.transitionConsumer({ operationId, previousDigest: oldDigest, target });
  assert.deepEqual((await next.status()).manualAttempts.actionable, []);
  assert.equal((await next.preflightConsumerTransition({ desiredDigest: 'f'.repeat(64) })).eligible, true);
  historical = false;
  assert.deepEqual((await next.status()).unknown, []);
  assert.equal(reads, 2);
  assert.deepEqual(await f.store.get(71), record(71));
});

test('worker evidence and every unfinished publication boundary override Task disposition', async t => {
  let calls = 0;
  const f = await fixture(t, async value => { calls++; return observation(value); });
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
  assert.equal(calls, 0);
});

test('completed manual receipt never hides contradictory live execution or pending publication', async t => {
  const f = await fixture(t, async value => observation(value));
  const complete = { ...record(71), envelope: { ...record(71).envelope,
    request: { schema_version: '3.0', kind: 'task-request' }, requestReference: { sha256: 'e'.repeat(64) } },
    outcome: { status: 'IMPLEMENTED_PENDING_FRESH_REVIEW', head: null, prNumber: null,
      outcomeId: 1071, manual: true }, manualResultAuthorization: { id: 2071, sha256: 'f'.repeat(64) } };
  assert.equal(manualAdmissionComplete(complete), true);
  for (const [index, fields] of [
    { controllerLifecycle: { version: 1, status: 'active' } },
    { relationshipIntent: { number: 45 } }, { prepublicationRecovery: { complete: false } }
  ].entries()) {
    const runId = index + 71;
    await f.store.put(runId, { ...complete, envelope: { ...complete.envelope, runId,
      attemptId: `run-${runId}` }, ...fields });
  }
  const withJournal = { ...complete, envelope: { ...complete.envelope, runId: 74, attemptId: 'run-74' } };
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

test('exact retained v3 and current v4 manual receipts release global drain despite recorded result progress', async t => {
  const f = await fixture(t);
  const retained = { ...record(71), envelope: { ...record(71).envelope,
    request: { schema_version: '3.0', kind: 'task-request' }, requestReference: { sha256: 'e'.repeat(64) } },
    outcome: { status: 'IMPLEMENTED_PENDING_FRESH_REVIEW', head: target, prNumber: 55,
      outcomeId: 1071, manual: true }, manualResultAuthorization: { id: 2071, sha256: 'f'.repeat(64) },
    prIntent: true, prNumber: 55, publishedHead: target, finalHead: target };
  const body = 'Authority model: github-native-v1\nIssue closure policy: keep-open';
  const parent = { kind: 'issue', number: 42 };
  const source = { charter: { kind: 'issue-body', id: 42, parent, sha256: sha256Body(body) },
    decisions: [], change_request: null, compatibility_request: null };
  const authority = { ...source, sha256: authoritySourceDigest(source) };
  const request = createAdmissionSnapshot({ authority, request: { repository: 'example/sample', task: 42,
    charter_sha256: sha256Body(body), purpose: 'Bounded qualification', scope: [], model: 'gpt-6.1-sol',
    effort: 'xhigh', subagents: false, validation: ['diff-check'], boundaries: [], branch: null,
    base_sha: null, starting_head: null, existing_pr: null, issue_closure_policy: 'keep-open',
    continuation: { hold: false, next: null }, route: 'manual' } }, { step: 1, attempt: 'run-72', runId: '72' });
  const result = { schema_version: '4.0', kind: 'outcome', repository: 'example/sample', task: 42,
    parent, charter_sha256: sha256Body(body), attempt: 'run-72', step: 1, status: 'implemented',
    result: { kind: 'qualification', revision: null, identities: [{ kind: 'github-actions-run', id: '72' }] },
    warnings: [], limitations: [], summary: 'Bounded result.', authority, admission: admissionBinding(request) };
  const current = { ...record(72), envelope: { ...record(72).envelope, step: 1, request },
    manualSubmission: { sha256: sha256Body(JSON.stringify(result)), parent, publishedResult: result },
    outcome: { manual: true, status: 'IMPLEMENTED_PENDING_FRESH_REVIEW', head: null, prNumber: null,
      outcomeId: 1072, bodySha256: 'e'.repeat(64) } };
  assert.equal(manualAdmissionComplete(retained), true); assert.equal(manualAdmissionComplete(current), true);
  await f.store.put(71, retained); await f.store.put(72, current);
  assert.deepEqual((await f.control.status()).unknown, []);
  await f.control.quiesce({ operationId, target });
  assert.equal((await f.control.drained({ operationId })).drained, true);
  assert.deepEqual(await f.store.get(71), retained); assert.deepEqual(await f.store.get(72), current);
});

test('activity appearing while authority is read invalidates an otherwise exact observation', async () => {
  let saved = null; const value = record(71);
  const result = await historicalManualAttemptDisposition(value, {
    journal: { get: async () => saved }, resolve: async input => {
      saved = { execution: { reserved: true } }; return observation(input);
    }
  });
  assert.equal(result, null);
});

test('foreign, stale or incomplete disposition evidence fails closed and cannot mutate its input', async () => {
  for (const fields of [{ repository: 'another/repository' }, { consumerDigest: nextDigest },
    { attemptId: 'run-72' }, { issueNumber: 43 }, { recordDigest: nextDigest },
    { envelopeDigest: nextDigest }, { evidenceDigest: null }, { disposition: 'completed' }]) {
    const value = record(71);
    await assert.rejects(historicalManualAttemptDisposition(value, { resolve: async input => ({ ...observation(input), ...fields }) }),
      { code: 'ADMISSION_MANUAL_DISPOSITION_INVALID' });
  }
  const value = record(71);
  await assert.rejects(historicalManualAttemptDisposition(value, { resolve: async input => {
    const result = observation(input); input.publicationIntent = { head: target }; return result;
  } }), { code: 'ADMISSION_MANUAL_DISPOSITION_INVALID' });
  assert.equal(manualAttemptHasNoPendingEffects(value), false);
});

test('supplemental historical evidence remains distinct from unresolved original-history runs', async t => {
  const f = await fixture(t, async value => observation(value));
  const control = createAdmissionControl({ root: f.root, consumerDigest: oldDigest, store: f.store,
    journal: f.journal, protectedRoot: false, manualAttemptDisposition: async value => observation(value),
    supplementalManualInventory: async () => ({ unknown: [88], manualAttempts: {
      historical: [{ runId: 77, issueNumber: 49, reason: 'route-switch' }], actionable: [88] } }) });
  const result = await control.preflightConsumerTransition({ desiredDigest: nextDigest });
  assert.deepEqual(result.unknown, [88]);
  assert.deepEqual(result.manualAttempts, { historical: [{ runId: 77, issueNumber: 49,
    reason: 'route-switch' }], actionable: [88] });
  const status = await control.status(); assert.deepEqual(status.unknown, []);
  assert.deepEqual(status.manualAttempts, result.manualAttempts);
});

test('supplemental optional diagnostics carry bounded source errors without weakening required checks', async t => {
  const f = await fixture(t, async value => observation(value));
  const control = createAdmissionControl({ root: f.root, consumerDigest: oldDigest, store: f.store,
    journal: f.journal, protectedRoot: false, manualAttemptDisposition: async value => observation(value),
    supplementalManualInventory: async ({ includeManual, manualDiagnostics }) => {
      if (includeManual) throw Object.assign(new Error('unavailable'), { code: 'HISTORICAL_TASK_AUTHORITY_UNAVAILABLE' });
      assert.equal(manualDiagnostics, true);
      return { unknown: [88], manualAttempts: { historical: [], actionable: [88], errors: [
        { runId: 88, code: 'HISTORICAL_TASK_AUTHORITY_UNAVAILABLE' }
      ] } };
    } });
  const status = await control.status(); assert.deepEqual(status.unknown, []);
  assert.deepEqual(status.manualAttempts.errors, [{ runId: 88, code: 'HISTORICAL_TASK_AUTHORITY_UNAVAILABLE' }]);
  await assert.rejects(control.preflightConsumerTransition({ desiredDigest: nextDigest }),
    { code: 'HISTORICAL_TASK_AUTHORITY_UNAVAILABLE' });
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
