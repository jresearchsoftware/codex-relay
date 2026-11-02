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
function manual() {
  const body = 'Authority model: github-native-v1\nIssue closure policy: keep-open';
  const parent = { kind: 'issue', number: 42 };
  const source = { charter: { kind: 'issue-body', id: 42, parent, sha256: sha256Body(body) },
    decisions: [], change_request: null, compatibility_request: null };
  const authority = { ...source, sha256: authoritySourceDigest(source) };
  const request = createAdmissionSnapshot({ authority, request: { repository: 'example/sample', task: 42,
    charter_sha256: sha256Body(body), purpose: 'Bounded qualification', scope: [], model: 'gpt-6.1-sol',
    effort: 'xhigh', subagents: false, validation: ['diff-check'], boundaries: [], branch: null,
    base_sha: null, starting_head: null, existing_pr: null, issue_closure_policy: 'keep-open',
    continuation: { hold: false, next: null }, route: 'manual' } }, { step: 1, attempt: 'run-32', runId: '32' });
  const result = { schema_version: '4.0', kind: 'outcome', repository: 'example/sample', task: 42,
    parent, charter_sha256: sha256Body(body), attempt: 'run-32', step: 1, status: 'implemented',
    result: { kind: 'qualification', revision: null, identities: [{ kind: 'github-actions-run', id: '32' }] },
    warnings: [], limitations: [], summary: 'Bounded result.', authority, admission: admissionBinding(request) };
  return { envelope: { version: VERSION, consumerDigest: oldDigest, runId: 32, attemptId: 'run-32', route: 'manual',
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

function retainedManual(runId = 34) {
  const record = manual();
  Object.assign(record.envelope, { runId, attemptId: `run-${runId}`,
    request: { schema_version: '3.0', kind: 'task-request' }, requestReference: { sha256: 'a'.repeat(64) } });
  delete record.manualSubmission; delete record.outcome.bodySha256;
  record.manualResultAuthorization = { id: runId + 1000, sha256: 'b'.repeat(64) };
  return record;
}

function retainedDirectManual(runId = 35) {
  const record = retainedManual(runId); delete record.manualResultAuthorization;
  record.outcome.bodySha256 = 'c'.repeat(64);
  record.manualSubmission = { sha256: 'd'.repeat(64), parent: { kind: 'issue', number: 42 }, rendererVersion: 'human-v1' };
  record.commentBodies = { outcome: { number: 42, sha256: record.outcome.bodySha256, rendererVersion: 'human-v1' } };
  return record;
}

function sealedRejectedManual(runId = 36) {
  const record = rejectedManual(runId); delete record.outcome.bodySha256;
  record.commentBodies = { outcome: { number: 42, sha256: 'e'.repeat(64), rendererVersion: 'human-v1' } };
  return record;
}

test('mixed rejected-before-handoff and retained manual receipts permit exact transition without rewriting history', async t => {
  const f = await setup(t); const auto = automatic();
  await f.store.put(31, auto.record); await f.journal.put(31, auto.saved);
  for (const record of [manual(), rejectedManual(), retainedManual(), retainedDirectManual(), sealedRejectedManual()]) {
    assert.equal(manualAdmissionComplete(record), true);
    await f.store.put(record.envelope.runId, record);
  }
  const before = JSON.stringify(await f.store.all()); const journalBefore = JSON.stringify(await f.journal.all());
  await f.old.checkConsumerTransition({ operationId, target });
  const transitioned = await f.next.transitionConsumer({ operationId, target, previousDigest: oldDigest });
  assert.deepEqual(await f.next.transitionConsumer({ operationId, target, previousDigest: oldDigest }), transitioned);
  assert.deepEqual((await f.next.status()).unknown, []);
  await assert.rejects(f.old.read(), { code: 'CONSUMER_CONFIG_CHANGED' });
  for (const runId of [32, 33, 34, 35, 36])
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
    await assert.rejects(f.next.transitionConsumer({ operationId, target, previousDigest: oldDigest }), { code: 'ADMISSION_ATTEMPT_INVALID' });
    assert.deepEqual(await readFile(gate), before);
    assert.equal(JSON.stringify(await f.store.all()), records);
    assert.deepEqual(await f.journal.all(), []);
  }
});

test('only original unextended v3 authorization may omit the published body hash', () => {
  assert.equal(manualAdmissionComplete(retainedManual()), true);
  const mutations = [r => { r.envelope.request.schema_version = '4.0'; },
    r => { r.envelope.request.kind = 'change-request'; }, r => { r.envelope.requestReference.sha256 = 'invalid'; },
    r => { r.manualResultAuthorization.id = 0; }, r => { r.manualResultAuthorization.sha256 = 'invalid'; },
    r => { r.manualSubmission = null; }, r => { r.commentBodies = {}; }, r => { r.outcome.extra = true; },
    r => { r.outcome.bodySha256 = null; }, r => { r.outcome.bodySha256 = 'invalid'; },
    r => { r.outcome.manual = false; }, r => { r.handoffComplete = false; },
    r => { r.commentIntent = { key: 'outcome' }; }, r => { delete r.outcome; }];
  for (const [index, mutate] of mutations.entries()) {
    const record = retainedManual(); mutate(record);
    assert.equal(manualAdmissionComplete(record), false, `authorization mutation ${index}`);
  }
  const incompleteModern = retainedManual(); incompleteModern.outcome.bodySha256 = 'e'.repeat(64);
  incompleteModern.manualSubmission = { publishedResult: null };
  assert.equal(manualAdmissionComplete(incompleteModern), false);
});

test('early direct-v3 result requires exact parent, body seal and human-v1 renderer and cannot substitute for v4', () => {
  assert.equal(manualAdmissionComplete(retainedDirectManual()), true);
  const pr = retainedDirectManual(); pr.outcome.prNumber = 43;
  pr.manualSubmission.parent = { kind: 'pull_request', number: 43 }; pr.commentBodies.outcome.number = 43;
  assert.equal(manualAdmissionComplete(pr), true);
  const mutations = [r => { r.envelope.request.schema_version = '4.0'; },
    r => { r.envelope.requestReference.sha256 = 'invalid'; }, r => { r.manualSubmission.sha256 = 'invalid'; },
    r => { r.manualSubmission.publishedResult = null; }, r => { r.manualSubmission.rendererVersion = 'human-v2'; },
    r => { r.manualSubmission.parent.number = 43; }, r => { r.manualSubmission.parent.kind = 'comment'; },
    r => { r.manualSubmission.extra = true; }, r => { r.manualSubmission.parent.extra = true; },
    r => { r.commentBodies.outcome.number = 43; }, r => { r.commentBodies.outcome.sha256 = 'e'.repeat(64); },
    r => { r.commentBodies.outcome.rendererVersion = 'human-v2'; }, r => { delete r.commentBodies; },
    r => { delete r.outcome.bodySha256; }, r => { r.outcome.manual = false; },
    r => { r.handoffComplete = false; }, r => { r.lifecycleIntent = {}; }];
  for (const [index, mutate] of mutations.entries()) {
    const record = retainedDirectManual(); mutate(record);
    assert.equal(manualAdmissionComplete(record), false, `direct-v3 mutation ${index}`);
  }
  const current = manual(); delete current.manualSubmission.publishedResult;
  current.manualSubmission.rendererVersion = 'human-v1';
  current.commentBodies = { outcome: { number: 42, sha256: current.outcome.bodySha256, rendererVersion: 'human-v1' } };
  assert.equal(manualAdmissionComplete(current), false);
});

test('eight refusals and three completed legacy receipts do not resolve ten genuine manual handoffs', async t => {
  const f = await setup(t);
  for (let id = 100; id < 107; id++) await f.store.put(id, rejectedManual(id));
  await f.store.put(107, sealedRejectedManual(107));
  for (let id = 108; id < 111; id++) await f.store.put(id, retainedManual(id));
  for (let id = 111; id < 121; id++) {
    const record = manual();
    Object.assign(record.envelope, { runId: id, attemptId: `run-${id}` });
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
  await assert.rejects(f.old.checkConsumerTransition({ operationId, target }), { code: 'ADMISSION_NOT_DRAINED' });
  await assert.rejects(f.next.transitionConsumer({ operationId, target, previousDigest: oldDigest }), { code: 'ADMISSION_ATTEMPT_INVALID' });
  assert.equal(JSON.stringify(await f.store.all()), before); assert.deepEqual(await f.journal.all(), []);
  assert.deepEqual(await readFile(join(f.root, 'admission-v1.json')), gate);
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

test('automatic completion cannot be manufactured by lifecycle flag, changed journal envelope or unresolved publication', async t => {
  const f = await setup(t);
  for (const mutate of [(r, j) => { delete j.outcome; }, (r, j) => { j.envelope = { ...j.envelope, consumerDigest: newDigest }; },
    r => { r.publicationIntent = { previous: target }; }, r => { r.handoffComplete = false; }]) {
    const { record, saved } = automatic(); mutate(record, saved); await f.store.put(31, record); await f.journal.put(31, saved);
    await assert.rejects(f.old.checkConsumerTransition({ operationId, target }), { code: 'ADMISSION_NOT_DRAINED' });
    await assert.rejects(f.next.transitionConsumer({ operationId, target, previousDigest: oldDigest }), { code: 'ADMISSION_ATTEMPT_INVALID' });
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
  await assert.rejects(f.next.status(), { code: 'ADMISSION_ATTEMPT_INVALID' });
});

test('CLI transition arguments are bounded and retain the selected operation/revision/digest', () => {
  assert.deepEqual(parseAdmissionArguments(['consumer-transition', '--operation', operationId, '--revision', target,
    '--previous-digest', oldDigest]), { command: 'consumer-transition', options: { operationId, revision: target, previousDigest: oldDigest } });
  for (const args of [['consumer-transition', '--operation', operationId, '--revision', target],
    ['consumer-transition-check', '--operation', operationId, '--revision', target, '--program', '/tmp/other']])
    assert.throws(() => parseAdmissionArguments(args), { code: 'ADMISSION_ARGUMENTS_INVALID' });
});
