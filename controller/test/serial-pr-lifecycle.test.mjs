import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, rm, symlink } from 'node:fs/promises';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { createAttemptStore, createPublicationStore } from '../src/attempt-store.mjs';
import { createSerialPrLifecycleStore, createCompatibilityStore, invokeOriginalReader,
  loadSerialPoolCompatibility } from '../src/serial-pool-compatibility.mjs';
import { serialPoolFixture } from './serial-pool-fixture.mjs';
import { beginRemediation } from '../src/pr-lifecycle.mjs';
import { createPublicationBroker } from '../src/publication-broker.mjs';
import { OWNER, REPOSITORY, REVIEWER } from '../src/execution-contract.mjs';
import { renderAuthorityRecord, sha256Body } from '../../contracts/src/github-authority.mjs';
import { selectRepositoryConsumer } from '../../consumer/consumer-config.mjs';

const repositories = [REPOSITORY, 'example-org/governance', 'example-org/models', 'other-org/docs'];
const linux = process.platform === 'linux';
const head = 'a'.repeat(40);
const receipt = (reviewId, repository = REPOSITORY) => ({ binding: {
  repository, prNumber: 152, reviewId, head, authorityDigest: 'b'.repeat(64)
}, lifecycleIntent: null });

async function fixture(t) {
  const f = await serialPoolFixture(t, { repositories });
  const ctx = await f.load(); const root = join(dirname(ctx.original.storeRoot), 'pr-lifecycle-v1');
  const before = new Map();
  for (let id = 17; id < 24; id++) {
    const path = join(root, `${id}.json`); await f.write(path, receipt(id)); before.set(path, await readFile(path));
  }
  for (const path of [f.gatePath, join(ctx.original.storeRoot, '99.json'), f.receiptPath]) before.set(path, await readFile(path));
  return { ...f, ctx, root, store: createSerialPrLifecycleStore(ctx),
    unchanged: async () => { for (const [path, bytes] of before) assert.deepEqual(await readFile(path), bytes, path); } };
}

// Native identities and v4 authority resolution are real code; all GitHub
// transport is deterministic and synthetic. These IDs reproduce the blocked
// Task 140 / PR 152 path without accessing or changing the live PR or review.
function nativeApi() {
  const user = { login: REVIEWER, id: 701, type: 'Bot' };
  const issue = { number: 140, state: 'open', user: { login: OWNER },
    body: 'Authority model: github-native-v1\nIssue closure policy: keep-open\n\nCorrect the bounded reviewed source.' };
  const pr = { number: 152, state: 'open', merged: false, draft: false, node_id: 'PR_fixture', body: 'Closes #140',
    base: { ref: 'main', sha: 'c'.repeat(40), repo: { full_name: REPOSITORY } },
    head: { ref: 'codex/task-140', sha: head, repo: { full_name: REPOSITORY } } };
  const review = { id: 5565218236, user, state: 'CHANGES_REQUESTED', commit_id: head };
  const render = () => { review.body = renderAuthorityRecord({ schema_version: '4.0', kind: 'change-request',
    repository: REPOSITORY, task: 140, parent: { kind: 'pull_request', number: 152 },
    charter_sha256: sha256Body(issue.body), purpose: 'Correct the bounded source defect',
    branch: pr.head.ref, base_sha: pr.base.sha, reviewed_head_sha: review.commit_id,
    change_request_id: 'CR-140-001', context: [], overrides: {},
    findings: [{ id: 'F1', severity: 'major', problem: 'Incorrect bounded behavior.', impact: 'Remediation is blocked.',
      remediation: 'Correct the source.', acceptance_criteria: ['The regression passes.'] }] }); };
  render(); let calls = 0; let lost = false; let reject = false;
  const api = {
    userIdentity: async () => structuredClone(user),
    get: async path => structuredClone(path === '/pulls/152' ? pr : path === '/issues/140' ? issue : assert.fail(path)),
    list: async path => path === '/pulls/152/reviews' ? [structuredClone(review)]
      : ['/issues/140/comments', '/issues/152/comments'].includes(path) ? [] : assert.fail(path),
    draft: async id => {
      assert.equal(id, pr.node_id); calls++;
      if (reject) throw new Error('DRAFT_FAILED');
      pr.draft = true; if (lost) throw new Error('RESPONSE_LOST');
    }
  };
  return { api, pr, review, issue, render, calls: () => calls,
    loseResponse: () => { lost = true; }, rejectMutation: value => { reject = value; },
    request: () => ({ operation: 'begin-remediation', prNumber: pr.number, reviewId: review.id, head: review.commit_id }) };
}

test('seven retained SERIAL receipts allow v4 CR-140-001 Draft, exact replay and lost response without altering history', { skip: !linux }, async t => {
  const f = await fixture(t); const n = nativeApi(); n.loseResponse();
  const broker = createPublicationBroker({ api: n.api, lifecycleStore: f.store });
  assert.equal((await broker.dispatch(n.request())).draft, true);
  assert.equal((await broker.dispatch(n.request())).draft, true); assert.equal(n.calls(), 1);
  assert.equal((await f.store.get(n.review.id)).lifecycleIntent, null);
  const current = join(f.root, 'repositories', REPOSITORY, `${n.review.id}.json`);
  const saved = await readFile(current);
  // A newer review for the same PR gets its own receipt, never the old one.
  n.review.id++; n.pr.draft = false;
  assert.equal((await broker.dispatch(n.request())).draft, true);
  assert.deepEqual(await readFile(current), saved);
  await assert.rejects(broker.dispatch({ ...n.request(), reviewId: n.review.id - 1 }), { code: 'CURRENT_CHANGE_REQUEST_MISSING' });
  const composite = createCompatibilityStore({ compatibility: f.ctx, originalStore: f.originalStore, currentStore: f.currentStore });
  assert.equal((await composite.all()).length, f.records.length + 1);
  assert.deepEqual((await invokeOriginalReader(f.ctx, { operation: 'inventory' })).unknown, []);
  // The unmodified generic publication namespace guard still rejects flat IDs.
  await assert.rejects(createAttemptStore(f.root, { repository: REPOSITORY, repositories, namespace: true }).get(n.review.id),
    { code: 'CONSUMER_CONFIG_CHANGED' });
  assert.equal(await createPublicationStore(join(f.root, 'unrelated')).get(1), null);
  await f.unchanged();
});

test('current uncertain intent resumes only the exact binding; retained completed replay is read-only', { skip: !linux }, async t => {
  const f = await fixture(t); const n = nativeApi(); n.rejectMutation(true);
  await assert.rejects(beginRemediation({ api: n.api, store: f.store, request: n.request() }), /DRAFT_FAILED/);
  assert.equal((await f.store.get(n.review.id)).lifecycleIntent.draft, true);
  await assert.rejects(f.store.put(n.review.id, { ...receipt(n.review.id), binding: { ...receipt(n.review.id).binding, head: 'd'.repeat(40) } }),
    { code: 'PR_LIFECYCLE_BINDING_CHANGED' });
  n.rejectMutation(false);
  await beginRemediation({ api: n.api, store: f.store, request: n.request() });
  const current = join(f.root, 'repositories', REPOSITORY, `${n.review.id}.json`);
  const old = join(f.root, `${n.review.id}.json`); const bytes = await readFile(current);
  // Build an original completed receipt fixture, not a production migration.
  await rm(current); await f.write(old, bytes);
  const calls = n.calls();
  assert.equal((await beginRemediation({ api: n.api, store: f.store, request: n.request() })).draft, true);
  assert.equal(n.calls(), calls); assert.deepEqual(await readFile(old), bytes);
  n.pr.draft = false;
  await assert.rejects(beginRemediation({ api: n.api, store: f.store, request: n.request() }), { code: 'SERIAL_POOL_LIFECYCLE_UNRESOLVED' });
  n.pr.draft = true; n.pr.head.ref = 'codex/changed'; n.render();
  await assert.rejects(beginRemediation({ api: n.api, store: f.store, request: n.request() }), { code: 'PR_LIFECYCLE_BINDING_CHANGED' });
  await assert.rejects(f.store.put(n.review.id, receipt(n.review.id)), { code: 'SERIAL_POOL_COMPATIBILITY_HISTORICAL_WRITE_FORBIDDEN' });
  assert.deepEqual(await readFile(old), bytes); await f.unchanged();
});

test('four configured repositories isolate equal review IDs and retain flat ownership at the anchor', { skip: !linux }, async t => {
  const f = await fixture(t);
  for (const repository of repositories) {
    const context = await loadSerialPoolCompatibility({ ...f.options,
      consumer: selectRepositoryConsumer(f.installationConsumer, repository) });
    const store = createSerialPrLifecycleStore(context);
    await store.put(900, receipt(900, repository));
    assert.equal((await store.get(900)).binding.repository, repository);
    if (repository === REPOSITORY) assert.equal((await store.get(17)).binding.repository, REPOSITORY);
    else { assert.equal(await store.get(17), null); await store.put(17, receipt(17, repository)); }
  }
  await f.unchanged();
  const moduleRoot = fileURLToPath(new URL('../..', import.meta.url));
  const driver = `
    import {pathToFileURL} from 'node:url';
    const input=JSON.parse(process.argv[1]);
    const {CONSUMER}=await import(pathToFileURL(input.moduleRoot+'/consumer/consumer.mjs'));
    const {loadSerialPoolCompatibility,createSerialPrLifecycleStore}=await import(pathToFileURL(input.moduleRoot+'/controller/src/serial-pool-compatibility.mjs'));
    const context=await loadSerialPoolCompatibility({...input.options,consumer:CONSUMER});
    const store=createSerialPrLifecycleStore(context);
    process.stdout.write(JSON.stringify((await store.get(900)).binding.repository));`;
  for (const repository of repositories) {
    const output = await promisify(execFile)(process.execPath, ['--input-type=module', '-e', driver,
      JSON.stringify({ moduleRoot, options: { ...f.options, consumer: undefined } })], {
      env: { PATH: '/usr/bin:/bin', RELAY_CONSUMER_CONFIG: f.consumerPath, RELAY_REPOSITORY: repository } });
    assert.equal(JSON.parse(output.stdout), repository);
  }
  const originalDriver = `
    import {pathToFileURL} from 'node:url';
    const input=JSON.parse(process.argv[1]);
    const {createPublicationStore}=await import(pathToFileURL(input.source+'/controller/src/attempt-store.mjs'));
    process.stdout.write(JSON.stringify(await createPublicationStore(input.root).get(17)));`;
  const original = await promisify(execFile)(process.execPath, ['--input-type=module', '-e', originalDriver,
    JSON.stringify({ source: f.ctx.original.sourceRoot, root: f.root })], {
    env: { PATH: '/usr/bin:/bin', RELAY_CONSUMER_CONFIG: f.oldConsumerPath } });
  assert.deepEqual(JSON.parse(original.stdout), receipt(17));
  await f.unchanged();
  assert.throws(() => createSerialPrLifecycleStore({ ...f.ctx }), { code: 'SERIAL_POOL_COMPATIBILITY_CONTEXT_INVALID' });
  await rm(f.receiptPath);
  await assert.rejects(f.store.get(900));
});

test('unknown ownership, unresolved old intent, corrupt/foreign/mixed records and collisions fail before Draft', { skip: !linux }, async t => {
  const f = await fixture(t); const n = nativeApi(); const old = join(f.root, '17.json'); const oldBytes = await readFile(old);
  const cases = [
    ['foreign original', old, receipt(17, repositories[1])],
    ['wrong original ID', old, receipt(18)],
    ['unknown original binding', old, { binding: { reviewId: 17 }, lifecycleIntent: null }],
    ['active original intent', old, { ...receipt(17), lifecycleIntent: { number: 152, head, draft: true } }],
    ['uncertain original intent', old, { ...receipt(17), lifecycleIntent: undefined }],
    ['corrupt original', old, '{'],
    ['mixed envelope', old, { ...receipt(17), envelope: f.records[0].envelope }],
    ['anchor collision', join(f.root, 'repositories', REPOSITORY, '17.json'), receipt(17)],
    ['foreign namespace', join(f.root, 'repositories/foreign/repo/900.json'), receipt(900, 'foreign/repo')],
    ['wrong namespace binding', join(f.root, 'repositories', repositories[1], '900.json'), receipt(900)],
    ['nonnumeric file', join(f.root, 'unknown.json'), receipt(900)]
  ];
  for (const [name, path, value] of cases) await t.test(name, async () => {
    await f.write(path, value);
    await assert.rejects(beginRemediation({ api: n.api, store: f.store, request: n.request() }),
      error => /^SERIAL_POOL_/.test(error.code));
    assert.equal(n.calls(), 0);
    if (path === old) await f.write(old, oldBytes);
    else if (path.includes('/foreign/')) await rm(join(f.root, 'repositories/foreign'), { recursive: true });
    else await rm(path);
  });
  await rm(old); await symlink(join(f.root, '18.json'), old);
  await assert.rejects(f.store.get(n.review.id));
  await rm(old); await f.write(old, oldBytes);
  await f.unchanged();
});
