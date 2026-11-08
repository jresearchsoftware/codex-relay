import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm, readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { createAdmissionControl, manualAdmissionComplete } from '../src/admission-control.mjs';
import { parseAdmissionArguments } from '../src/admission-cli.mjs';
import { VERSION, digest } from '../src/execution-contract.mjs';
import { admissionBinding, authoritySourceDigest, createAdmissionSnapshot, sha256Body } from '../../contracts/src/github-authority.mjs';
import { memoryStore } from './fixture.mjs';

const oldDigest = 'a'.repeat(64); const newDigest = 'b'.repeat(64);
const target = 'c'.repeat(40); const operationId = '12345678-1234-1234-1234-123456789abc';
async function setup(t) {
  const root = await mkdtemp(join(tmpdir(), 'relay-consumer-transition-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const store = memoryStore(); const journal = memoryStore();
  const control = consumerDigest => createAdmissionControl({ root, consumerDigest, store, journal, protectedRoot: false });
  const old = control(oldDigest); await old.initialize();
  await old.quiesce({ operationId, target }); await old.drained({ operationId });
  await old.phase({ operationId, phase: 'applying' });
  return { root, store, journal, old, next: control(newDigest) };
}
function automatic(runId = 31) {
  const envelope = { version: VERSION, runId, attemptId: `run-${runId}`, route: 'auto', consumerDigest: oldDigest };
  const outcome = { status: 'BLOCKED', head: null, prNumber: null, outcomeId: 12, bodySha256: 'd'.repeat(64) };
  return { record: { envelope, outcome, controllerLifecycle: { version: 1, status: 'complete', child: 'not_started', containment: 'not_required' } },
    saved: { version: VERSION, envelope, outcome, execution: null } };
}
function manual(runId = 32) {
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
  return { envelope: { version: VERSION, consumerDigest: oldDigest, runId, attemptId: `run-${runId}`, route: 'manual',
    repository: 'example/sample', issueNumber: 42, step: 1, request },
    manualSubmission: { sha256: sha256Body(JSON.stringify(result)), parent, publishedResult: result },
    outcome: { manual: true, status: 'IMPLEMENTED_PENDING_FRESH_REVIEW', head: null, prNumber: null, outcomeId: 13, bodySha256: 'e'.repeat(64) } };
}

function rejectedManual(runId = 33) {
  const admissionBlock = { code: 'AUTHORITY_TASK_REQUEST_REQUIRED' };
  return { envelope: { version: VERSION, consumerDigest: oldDigest, runId, attemptId: `run-${runId}`,
    route: 'manual', repository: 'example/sample', issueNumber: 42, request: null,
    authorityDigest: null, branch: null, startHead: null, admissionBlock }, admissionBlock,
    outcome: { status: 'BLOCKED', head: null, prNumber: null, outcomeId: runId + 1000, bodySha256: 'd'.repeat(64) } };
}

function sealedRejectedManual(runId = 36) {
  const record = rejectedManual(runId); delete record.outcome.bodySha256;
  record.commentBodies = { outcome: { number: 42, sha256: 'e'.repeat(64), rendererVersion: 'human-v1' } };
  return record;
}

test('mixed current admitted and rejected-before-handoff manual receipts permit exact transition without rewriting history', async t => {
  const f = await setup(t); const auto = automatic();
  await f.store.put(31, auto.record); await f.journal.put(31, auto.saved);
  for (const record of [manual(), rejectedManual(), sealedRejectedManual()]) {
    assert.equal(manualAdmissionComplete(record), true);
    await f.store.put(record.envelope.runId, record);
  }
  const before = JSON.stringify(await f.store.all()); const journalBefore = JSON.stringify(await f.journal.all());
  await f.old.checkConsumerTransition({ operationId, target });
  const transitioned = await f.next.transitionConsumer({ operationId, target, previousDigest: oldDigest });
  assert.deepEqual(await f.next.transitionConsumer({ operationId, target, previousDigest: oldDigest }), transitioned);
  assert.deepEqual((await f.next.status()).unknown, []);
  await assert.rejects(f.old.read(), { code: 'CONSUMER_CONFIG_CHANGED' });
  for (const runId of [32, 33, 36])
    await assert.rejects(f.next.complete({ runId, attemptId: `run-${runId}` }), { code: 'CONSUMER_CONFIG_CHANGED' });
  assert.equal(JSON.stringify(await f.store.all()), before);
  assert.equal(JSON.stringify(await f.journal.all()), journalBefore);
});

test('early generic refusal requires its exact native body seal when the outcome predates bodySha256', () => {
  assert.equal(manualAdmissionComplete(sealedRejectedManual()), true);
  const pr = sealedRejectedManual(); pr.envelope.target = 'pull_request'; pr.envelope.number = 43;
  pr.commentBodies.outcome.number = 43;
  assert.equal(manualAdmissionComplete(pr), true);
  const mutations = [r => { r.commentBodies.outcome.number = 43; },
    r => { r.commentBodies.outcome.sha256 = 'invalid'; }, r => { r.commentBodies.outcome.rendererVersion = 'human-v2'; },
    r => { delete r.commentBodies; }, r => { r.outcome.bodySha256 = null; },
    r => { r.outcome.bodySha256 = 'invalid'; }, r => { r.outcome.manual = true; },
    r => { r.commentBodies.handoff = { number: 42 }; }, r => { r.handoffComplete = true; },
    r => { r.commentIntent = { key: 'outcome' }; }];
  for (const [index, mutate] of mutations.entries()) {
    const record = sealedRejectedManual(); mutate(record);
    assert.equal(manualAdmissionComplete(record), false, `generic refusal mutation ${index}`);
  }
});

test('rejected admission compatibility cannot hide a handoff, submitted result or uncertain effect', async t => {
  const f = await setup(t); const gate = join(f.root, 'admission-v1.json'); const before = await readFile(gate);
  const mutations = [r => { r.envelope.admissionBlock = { code: 'DIFFERENT_REFUSAL' }; },
    r => { r.admissionBlock.code = 'unsafe/path'; }, r => { r.envelope.request = { schema_version: '4.0' }; },
    r => { r.envelope.authorityDigest = 'a'.repeat(64); }, r => { r.envelope.branch = 'codex/task-42'; },
    r => { r.envelope.startHead = target; }, r => { r.handoffComplete = true; }, r => { r.handoffComplete = false; },
    r => { r.commentBodies = { handoff: { sha256: 'a'.repeat(64) } }; }, r => { r.manualSubmission = {}; },
    r => { r.manualResultAuthorization = {}; }, r => { r.controllerLifecycle = { status: 'complete' }; },
    r => { r.outcome.manual = true; r.outcome.status = 'IMPLEMENTED_PENDING_FRESH_REVIEW'; },
    r => { delete r.outcome.bodySha256; }, r => { r.outcome.head = target; }, r => { r.outcome.prNumber = 42; },
    ...['publicationIntent', 'commentIntent', 'lifecycleIntent', 'prIntent', 'successOutcomeIntent',
      'readinessIntent', 'prepublicationRecovery'].map(key => r => { r[key] = {}; }),
    ...['publishedHead', 'finalHead'].map(key => r => { r[key] = target; })];
  for (const [index, mutate] of mutations.entries()) {
    const record = rejectedManual(); mutate(record);
    assert.equal(manualAdmissionComplete(record), false, `rejection mutation ${index}`);
    await f.store.put(33, record); const records = JSON.stringify(await f.store.all());
    await assert.rejects(f.old.checkConsumerTransition({ operationId, target }), { code: 'ADMISSION_NOT_DRAINED' });
    await assert.rejects(f.next.transitionConsumer({ operationId, target, previousDigest: oldDigest }), { code: 'ADMISSION_NOT_DRAINED' });
    assert.deepEqual(await readFile(gate), before);
    assert.equal(JSON.stringify(await f.store.all()), records);
    assert.deepEqual(await f.journal.all(), []);
  }
});

test('current manual completion requires exact admission, complete result and durable native body proof', () => {
  assert.equal(manualAdmissionComplete(manual()), true);
  for (const mutate of [
    value => { delete value.outcome.bodySha256; }, value => { value.outcome.bodySha256 = 'invalid'; },
    value => { delete value.manualSubmission.publishedResult; }, value => { value.manualSubmission.publishedResult = null; },
    value => { value.manualSubmission.publishedResult.schema_version = '3.0'; },
    value => { value.manualSubmission.publishedResult.step = 2; },
    value => { value.manualSubmission.publishedResult.authority.sha256 = 'f'.repeat(64); },
    value => { value.manualSubmission.publishedResult.admission.sha256 = 'f'.repeat(64); },
    value => { value.outcome.manual = false; }, value => { value.handoffComplete = false; },
    value => { value.commentIntent = { key: 'outcome' }; }
  ]) { const value = manual(); mutate(value); assert.equal(manualAdmissionComplete(value), false); }
});

test('idle transition retains missing manual Outcomes without inventing completion or cancellation', async t => {
  const f = await setup(t);
  for (let id = 100; id < 107; id++) await f.store.put(id, rejectedManual(id));
  await f.store.put(107, sealedRejectedManual(107));
  for (let id = 108; id < 111; id++) await f.store.put(id, manual(id));
  for (let id = 111; id < 121; id++) {
    const record = manual();
    Object.assign(record.envelope, { runId: id, attemptId: `run-${id}`, target: 'issue', number: 42 });
    delete record.outcome; delete record.manualSubmission;
    record.handoffComplete = true;
    record.commentBodies = { handoff: { number: 42, sha256: 'a'.repeat(64), rendererVersion: 'human-v1' } };
    // A later owner withdrawal leaves this original handoff receipt unresolved;
    // it supplies no terminal Outcome or permission to mutate historical bytes.
    await f.store.put(id, record);
  }
  const before = JSON.stringify(await f.store.all()); const gate = await readFile(join(f.root, 'admission-v1.json'));
  const rows = await f.store.all();
  assert.equal(rows.filter(manualAdmissionComplete).length, 11);
  assert.deepEqual(rows.filter(record => !manualAdmissionComplete(record)).map(record => record.envelope.runId),
    Array.from({ length: 10 }, (_, index) => 111 + index));
  await f.old.checkConsumerTransition({ operationId, target });
  await f.next.transitionConsumer({ operationId, target, previousDigest: oldDigest });
  assert.deepEqual((await f.next.status()).unknown, []);
  assert.equal(JSON.stringify(await f.store.all()), before); assert.deepEqual(await f.journal.all(), []);
  assert.equal((await f.next.read()).consumerDigest, newDigest);
});

test('drained same-operation change preserves original automatic and manual receipts, supports replay and next admission', async t => {
  const f = await setup(t); const auto = automatic(); const handoff = manual();
  await f.store.put(31, auto.record); await f.journal.put(31, auto.saved); await f.store.put(32, handoff);
  const before = JSON.stringify(await f.store.all()); const journalBefore = JSON.stringify(await f.journal.all());
  assert.deepEqual(await f.old.checkConsumerTransition({ operationId, target }), { operationId, target, previousDigest: oldDigest });
  const migrated = await f.next.transitionConsumer({ operationId, target, previousDigest: oldDigest });
  assert.equal(migrated.consumerDigest, newDigest); assert.equal(migrated.phase, 'applying');
  assert.equal(migrated.operationId, operationId); assert.equal(migrated.target, target);
  assert.deepEqual(await f.next.transitionConsumer({ operationId, target, previousDigest: oldDigest }), migrated);
  assert.equal(JSON.stringify(await f.store.all()), before); assert.equal(JSON.stringify(await f.journal.all()), journalBefore);
  assert.deepEqual((await f.next.status()).unknown, []);
  await assert.rejects(f.old.read(), { code: 'CONSUMER_CONFIG_CHANGED' });
  await assert.rejects(f.next.complete({ runId: 31, attemptId: 'run-31' }), { code: 'CONSUMER_CONFIG_CHANGED' });
  await f.next.phase({ operationId, phase: 'verified', revision: target });
  await f.next.resume({ operationId }); assert.equal((await f.next.reserve()).status, 'active');
});

test('pending manual handoff and any unpublished/uncertain original effect block BEFORE consumer rewrite', async t => {
  const f = await setup(t);
  for (const mutate of [r => { delete r.outcome; }, r => { r.commentIntent = { key: 'outcome' }; },
    r => { r.lifecycleIntent = { draft: false }; }, r => { r.manualSubmission.publishedResult.admission.sha256 = 'f'.repeat(64); }]) {
    const record = manual(); mutate(record); await f.store.put(32, record);
    await assert.rejects(f.old.checkConsumerTransition({ operationId, target }), { code: 'ADMISSION_NOT_DRAINED' });
    assert.equal((await f.old.read()).consumerDigest, oldDigest);
  }
});

test('completed lifecycle history retains pending publication and handoff boundaries across consumer changes', async t => {
  const f = await setup(t);
  for (const mutate of [r => { r.publicationIntent = { previous: target }; }, r => { r.handoffComplete = false; }]) {
    const { record, saved } = automatic(); mutate(record, saved); await f.store.put(31, record); await f.journal.put(31, saved);
    await assert.rejects(f.old.checkConsumerTransition({ operationId, target }), { code: 'ADMISSION_NOT_DRAINED' });
    await assert.rejects(f.next.transitionConsumer({ operationId, target, previousDigest: oldDigest }), { code: 'ADMISSION_NOT_DRAINED' });
    assert.equal((await f.old.read()).consumerDigest, oldDigest);
  }
});

test('wrong operation, revision, previous digest and open gate never migrate', async t => {
  const f = await setup(t); const path = join(f.root, 'admission-v1.json'); const before = await readFile(path, 'utf8');
  await assert.rejects(f.next.transitionConsumer({ operationId, target, previousDigest: 'f'.repeat(64) }), { code: 'CONSUMER_CONFIG_CHANGED' });
  await assert.rejects(f.next.transitionConsumer({ operationId: '12345678-1234-1234-1234-123456789abd', target, previousDigest: oldDigest }), { code: 'ADMISSION_OPERATION_MISMATCH' });
  await assert.rejects(f.next.transitionConsumer({ operationId, target: 'd'.repeat(40), previousDigest: oldDigest }), { code: 'ADMISSION_TARGET_MISMATCH' });
  assert.equal(await readFile(path, 'utf8'), before);
  await f.old.phase({ operationId, phase: 'verified', revision: target }); await f.old.resume({ operationId });
  await assert.rejects(f.next.transitionConsumer({ operationId, target, previousDigest: oldDigest }), { code: 'ADMISSION_OPERATION_MISMATCH' });
});

test('completed original prepublication recovery keeps its own exact journal and handoff proof', async t => {
  const f = await setup(t); const { record, saved } = automatic();
  record.handoffComplete = false; record.prNumber = 55;
  record.prepublicationRecovery = { complete: true, handoffProven: true,
    binding: { head: target, terminal: { journalDigest: digest(saved), controllerDigest: digest(record.controllerLifecycle) } },
    publication: { status: 'PUBLISHED', publishedHead: target }, collection: { head: target, clean: true },
    outcome: { status: 'IMPLEMENTED_PENDING_FRESH_REVIEW', head: target, outcomeId: 14, prNumber: 55 } };
  await f.store.put(31, record); await f.journal.put(31, saved);
  await f.old.checkConsumerTransition({ operationId, target });
  await f.next.transitionConsumer({ operationId, target, previousDigest: oldDigest });
  assert.deepEqual((await f.next.status()).unknown, []);
  record.prepublicationRecovery.handoffProven = false; await f.store.put(31, record);
  assert.deepEqual((await f.next.status()).unknown, [31]);
  await assert.rejects(f.next.checkConsumerTransition({ operationId, target }), { code: 'ADMISSION_NOT_DRAINED' });
});

test('CLI transition arguments are bounded and retain the selected operation/revision/digest', () => {
  assert.deepEqual(parseAdmissionArguments(['consumer-transition', '--operation', operationId, '--revision', target,
    '--previous-digest', oldDigest]), { command: 'consumer-transition', options: { operationId, revision: target, previousDigest: oldDigest } });
  for (const args of [['consumer-transition', '--operation', operationId, '--revision', target],
    ['consumer-transition-check', '--operation', operationId, '--revision', target, '--program', '/tmp/other']])
    assert.throws(() => parseAdmissionArguments(args), { code: 'ADMISSION_ARGUMENTS_INVALID' });
});


test('completed lifecycle releases idle transition without rereading obsolete execution journals', async t => {
  const f = await setup(t); const { record } = automatic(); await f.store.put(31, record);
  const next = createAdmissionControl({ root: f.root, consumerDigest: newDigest, store: f.store,
    journal: { get: async () => assert.fail('completed lifecycle does not reacquire obsolete runner evidence') },
    protectedRoot: false, manualAttemptDisposition: async () => assert.fail('idle transition does not read historical GitHub authority') });
  await next.transitionConsumer({ operationId, target, previousDigest: oldDigest });
  assert.deepEqual((await next.status()).unknown, []);
  await assert.rejects(next.complete({ runId: 31, attemptId: 'run-31' }), { code: 'CONSUMER_CONFIG_CHANGED' });
  assert.deepEqual(await f.store.get(31), record);
});


test('completed old-digest automatic records cannot hide pending effects or unknown containment', async t => {
  const f = await setup(t);
  for (const fields of [
    { relationshipIntent: { number: 42 } }, { readinessIntent: { draft: false } },
    { successOutcomeIntent: { head: target } }, { readyConsumption: { status: 'uncertain' } },
    { prepublicationRecovery: { complete: false } },
    { controllerLifecycle: { version: 1, status: 'complete', child: 'started', containment: 'unknown' } }
  ]) {
    const { record } = automatic(); Object.assign(record, fields); await f.store.put(31, record);
    assert.deepEqual((await f.old.status()).unknown, [31]);
    await assert.rejects(f.next.transitionConsumer({ operationId, target, previousDigest: oldDigest }),
      { code: 'ADMISSION_NOT_DRAINED' });
    assert.equal((await f.old.read()).consumerDigest, oldDigest);
  }
});


test('malformed lifecycle terminal receipts cannot release either current or old-digest work', async t => {
  const f = await setup(t);
  for (const consumerDigest of [oldDigest, newDigest]) for (const mutate of [
    record => { record.outcome = {}; }, record => { record.outcome.status = 'unknown'; },
    record => { record.outcome.outcomeId = 0; }, record => { record.outcome.head = 'invalid'; },
    record => { record.outcome.prNumber = 0; }, record => { record.outcome.bodySha256 = 'invalid'; }
  ]) {
    const { record } = automatic(); record.envelope.consumerDigest = consumerDigest; mutate(record);
    await f.store.put(31, record);
    assert.deepEqual((await f.old.status()).unknown, [31]);
    assert.equal((await f.old.preflightConsumerTransition({ desiredDigest: newDigest })).eligible, false);
    await assert.rejects(f.next.transitionConsumer({ operationId, target, previousDigest: oldDigest }),
      { code: 'ADMISSION_NOT_DRAINED' });
  }
  const { record } = automatic(); delete record.outcome.bodySha256; await f.store.put(31, record);
  await f.old.checkConsumerTransition({ operationId, target });
});


test('an exact pre-admission refusal remains idle without an Outcome while real effect progress still blocks', async t => {
  const f = await setup(t), admissionBlock = { code: 'OWNER_DECISION_REQUIRED' };
  const refused = { envelope: { ...automatic().record.envelope, repository: 'example/sample', issueNumber: 42,
    target: 'issue', number: 42, request: null, branch: null, startHead: null, authorityDigest: null, admissionBlock },
    admissionBlock, outcome: null, readyConsumption: { status: 'consumed' } };
  await f.store.put(31, refused);
  assert.deepEqual((await f.old.status()).unknown, []); await f.old.checkConsumerTransition({ operationId, target });
  for (const fields of [
    { commentIntent: { key: 'outcome' } }, { prIntent: true }, { handoffComplete: false },
    { readyConsumption: { status: 'uncertain' } }, { outcome: {} },
    { controllerLifecycle: { version: 1, status: 'active' } },
    { envelope: { ...refused.envelope, admissionBlock: { code: 'DIFFERENT_REFUSAL' } } }
  ]) {
    await f.store.put(31, { ...refused, ...fields });
    assert.deepEqual((await f.old.status()).unknown, [31]);
    await assert.rejects(f.next.transitionConsumer({ operationId, target, previousDigest: oldDigest }),
      { code: 'ADMISSION_NOT_DRAINED' });
  }
  await f.store.put(31, refused);
  await f.next.transitionConsumer({ operationId, target, previousDigest: oldDigest });
  assert.deepEqual(await f.store.get(31), refused); assert.deepEqual(await f.journal.all(), []);
});
