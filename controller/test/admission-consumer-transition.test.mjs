import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm, readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { createAdmissionControl } from '../src/admission-control.mjs';
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
