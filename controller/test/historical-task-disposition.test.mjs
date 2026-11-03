import test from 'node:test';
import assert from 'node:assert/strict';
import { createHistoricalTaskDisposition } from '../src/historical-task-disposition.mjs';
import { digest } from '../src/execution-contract.mjs';
import { renderAuthorityRecord, sha256Body } from '../../contracts/src/github-authority.mjs';

const repository = 'example/relay';
const owner = { login: 'owner', id: 11, type: 'User' };
const reviewer = { login: 'reviewer[bot]', id: 12, type: 'Bot' };
const charter = 'Authority model: github-native-v1\nIssue closure policy: keep-open\nBounded work.';
const copy = value => structuredClone(value);
function record() {
  return { envelope: { version: 2, route: 'manual', repository, issueNumber: 42,
    runId: 91, attemptId: 'run-91', consumerDigest: 'a'.repeat(64),
    target: 'issue', number: 42, step: 1 }, outcome: null };
}
function decision(id = 100, purpose = 'The old profile handoff has not been executed.') {
  const body = renderAuthorityRecord({ schema_version: '4.0', kind: 'decision', repository, task: 42,
    parent: { kind: 'issue', number: 42 }, charter_sha256: sha256Body(charter), purpose,
    amendments: { effort: 'xhigh' }, supersedes: null, context: [] });
  return { reference: { kind: 'issue-comment', id, parent: { kind: 'issue', number: 42 },
    sha256: sha256Body(body) }, body };
}
function task() {
  return { repository, task: 42, owner: copy(owner),
    issue: { id: 200, number: 42, state: 'open', state_reason: null, body: charter, closed_by: null },
    lifecycle: [], decisions: [decision()] };
}
function event(id, action, actor = owner) {
  return { id, event: action, actor: copy(actor), created_at: '2026-01-01T00:00:00Z' };
}
function fixture(options = {}) {
  let current = task();
  let reads = 0;
  const cache = new Map();
  const factory = overrides => createHistoricalTaskDisposition({ repository,
    readTask: async (repo, number) => {
      assert.equal(repo, repository); assert.equal(number, 42); reads++;
      return copy(current);
    }, cache, ...options, ...overrides });
  return { cache, factory, current: () => current, reads: () => reads,
    set: value => { current = value; } };
}

for (const [stateReason, reason] of [['completed', 'task-completed'], ['not_planned', 'task-not-planned']]) {
  test(`native owner closure ${stateReason} supplies current lifecycle evidence without an acknowledgement`, async () => {
    const f = fixture(); const source = f.current();
    Object.assign(source.issue, { state: 'closed', state_reason: stateReason, closed_by: copy(owner) });
    source.lifecycle.push(event(501, 'closed'));
    const r = record(), before = copy(r), resolver = f.factory();
    const observed = await resolver.resolve(r);
    assert.deepEqual({ ...observed, evidenceDigest: undefined }, { disposition: 'historical', reason,
      repository, issueNumber: 42, runId: 91, attemptId: 'run-91', consumerDigest: 'a'.repeat(64),
      envelopeDigest: digest(r.envelope), recordDigest: digest(r), evidenceDigest: undefined });
    assert.match(observed.evidenceDigest, /^[a-f0-9]{64}$/);
    assert.equal(f.cache.size, 0); assert.deepEqual(r, before);
    assert.deepEqual(await resolver.resolve(r), observed); assert.equal(f.reads(), 2);
  });
}

test('unknown closure reason and untrusted closer preserve the barrier', async () => {
  const f = fixture(); const source = f.current();
  Object.assign(source.issue, { state: 'closed', state_reason: null, closed_by: copy(owner) });
  source.lifecycle.push(event(501, 'closed'));
  assert.equal(await f.factory().resolve(record()), null);
  source.issue.state_reason = 'completed';
  source.issue.closed_by = { login: 'foreign-user', id: 77, type: 'User' };
  source.lifecycle[0].actor = copy(source.issue.closed_by);
  assert.equal(await f.factory().resolve(record()), null);
});

test('an eligible configured native Bot may close a Task without another owner ceremony', async () => {
  const f = fixture(); const source = f.current(); source.trustedClosers = [copy(reviewer)];
  Object.assign(source.issue, { state: 'closed', state_reason: 'completed', closed_by: copy(reviewer) });
  source.lifecycle.push(event(501, 'closed', reviewer));
  assert.equal((await f.factory().resolve(record())).reason, 'task-completed');
});

test('trusted Decision prose alone grants no automatic withdrawal or route-switch', async () => {
  const f = fixture();
  f.current().decisions.push(decision(101, 'Stop native routing and use standalone manual execution.'));
  assert.equal(await f.factory().resolve(record()), null);
  await assert.rejects(f.factory().acknowledge(record(), { reason: 'owner-withdrawal',
    sources: [f.current().decisions[0].reference] }), { code: 'HISTORICAL_TASK_ACKNOWLEDGEMENT_FORBIDDEN' });
});

for (const reason of ['owner-withdrawal', 'route-switch']) {
  test(`protected ${reason} interpretation reuses exact existing authority and exact attempt only`, async () => {
    const f = fixture(); const r = record(), before = copy(r);
    const resolver = f.factory({ allowAcknowledgement: true });
    const acknowledgement = await resolver.acknowledge(r, { reason,
      sources: [copy(f.current().decisions[0].reference)] });
    assert.equal(f.cache.get(`${repository}:91`).sourceDigest, acknowledgement.sourceDigest);
    const observed = await resolver.resolve(r);
    assert.equal(observed.reason, reason); assert.equal(observed.evidenceDigest, acknowledgement.evidenceDigest);
    assert.equal(observed.recordDigest, digest(r)); assert.deepEqual(r, before);
    const different = copy(r); different.envelope.runId++; different.envelope.attemptId = 'run-92';
    assert.equal(await resolver.resolve(different), null);
    const changed = copy(r); changed.envelope.step++;
    assert.equal(await resolver.resolve(changed), null);
    assert.equal(f.reads(), 4);
  });
}

test('current Decision edits, added Decisions and removal invalidate a cached acknowledgement', async () => {
  for (const mutate of [source => { source.decisions[0] = decision(100, 'Changed owner direction.'); },
    source => { source.decisions.push(decision(101)); }, source => { source.decisions = []; }]) {
    const f = fixture(); const resolver = f.factory({ allowAcknowledgement: true });
    await resolver.acknowledge(record(), { reason: 'owner-withdrawal', sources: [f.current().decisions[0].reference] });
    mutate(f.current()); assert.equal(await resolver.resolve(record()), null);
  }
});

test('a closed/reopened cycle invalidates the acknowledgement even when current body and Decisions match', async () => {
  const f = fixture(); const resolver = f.factory({ allowAcknowledgement: true });
  await resolver.acknowledge(record(), { reason: 'route-switch', sources: [f.current().decisions[0].reference] });
  f.current().lifecycle.push(event(501, 'closed'), event(502, 'reopened'));
  f.current().issue.state_reason = 'reopened';
  assert.equal(await resolver.resolve(record()), null);
  f.current().issue.state_reason = null;
  assert.equal(await resolver.resolve(record()), null);
});

test('additional native authority fingerprints invalidate acknowledgements without interpreting their prose', async () => {
  const f = fixture(); f.current().authority = [copy(f.current().decisions[0])];
  const resolver = f.factory({ allowAcknowledgement: true });
  await resolver.acknowledge(record(), { reason: 'route-switch', sources: [f.current().decisions[0].reference] });
  f.current().authority.push({ reference: { kind: 'issue-comment', id: 102,
    parent: { kind: 'issue', number: 42 }, sha256: 'b'.repeat(64) }, body: 'New verified native authority.' });
  assert.equal(await resolver.resolve(record()), null);
});

test('historical Decision charter hashes remain unchanged when the current owner Issue body differs', async () => {
  const f = fixture(); const original = copy(f.current().decisions[0]);
  f.current().issue.body += '\nOwner-authorized current continuation.';
  const resolver = f.factory({ allowAcknowledgement: true });
  await resolver.acknowledge(record(), { reason: 'owner-withdrawal', sources: [original.reference] });
  assert.equal((await resolver.resolve(record())).reason, 'owner-withdrawal');
  assert.deepEqual(f.current().decisions[0], original);
  f.current().issue.body += '\nNew owner direction changes the current authority.';
  assert.equal(await resolver.resolve(record()), null);
});

test('native evidence read failure never falls back to a protected cached acknowledgement', async () => {
  const f = fixture(); const enabled = f.factory({ allowAcknowledgement: true });
  await enabled.acknowledge(record(), { reason: 'owner-withdrawal', sources: [f.current().decisions[0].reference] });
  const resolver = f.factory({ readTask: async () => { throw Object.assign(new Error('unavailable'), { code: 'NATIVE_UNAVAILABLE' }); } });
  await assert.rejects(resolver.resolve(record()), { code: 'NATIVE_UNAVAILABLE' });
});

test('acknowledgement accepts only exact active source references and its supported reasons', async () => {
  const f = fixture(); const resolver = f.factory({ allowAcknowledgement: true });
  const source = f.current().decisions[0].reference;
  for (const options of [{ reason: 'completed', sources: [source] }, { reason: 'owner-withdrawal', sources: [] },
    { reason: 'owner-withdrawal', sources: [{ ...source, sha256: 'b'.repeat(64) }] },
    { reason: 'route-switch', sources: [source, source] }]) {
    await assert.rejects(resolver.acknowledge(record(), options), { code: 'HISTORICAL_TASK_ACKNOWLEDGEMENT_INVALID' });
  }
  assert.equal(f.cache.size, 0);
});

test('pending effects cannot acquire or reuse a historical acknowledgement', async () => {
  const f = fixture(); const resolver = f.factory({ allowAcknowledgement: true });
  const r = record(); r.publicationIntent = { reserved: true };
  await assert.rejects(resolver.acknowledge(r, { reason: 'owner-withdrawal',
    sources: [f.current().decisions[0].reference] }), { code: 'HISTORICAL_TASK_ACKNOWLEDGEMENT_INVALID' });
  assert.equal(await resolver.resolve(r), null); assert.equal(f.reads(), 0);
});

test('malformed Decision bytes, lifecycle gaps and cross-Task identities fail closed', async () => {
  for (const mutate of [source => { source.decisions[0].body += '\nEdited.'; },
    source => { source.task++; }, source => { source.issue.number++; },
    source => { source.lifecycle.push(event(501, 'closed')); },
    source => { source.lifecycle.push(event(502, 'reopened'), event(501, 'reopened')); }]) {
    const f = fixture(); mutate(f.current());
    await assert.rejects(f.factory().resolve(record()), { code: 'HISTORICAL_TASK_SOURCE_INVALID' });
  }
});

test('async protected caches retain exact binding and corrupted receipts cannot accept an attempt', async () => {
  const f = fixture();
  const resolver = f.factory({ allowAcknowledgement: true, cache: {
    get: async key => copy(f.cache.get(key)), set: async (key, value) => { f.cache.set(key, copy(value)); }
  } });
  await resolver.acknowledge(record(), { reason: 'owner-withdrawal', sources: [f.current().decisions[0].reference] });
  assert.equal((await resolver.resolve(record())).reason, 'owner-withdrawal');
  f.cache.get(`${repository}:91`).reason = 'route-switch';
  assert.equal(await resolver.resolve(record()), null);
});

test('a changing retained record cannot receive a disposition from an earlier native read', async () => {
  const r = record();
  const resolver = createHistoricalTaskDisposition({ readTask: async () => {
    r.envelope.step++;
    return task();
  } });
  await assert.rejects(resolver.resolve(r), { code: 'HISTORICAL_TASK_RECORD_CHANGED' });
});

test('the trusted native reader receives the exact protected record for original artifact scope', async () => {
  const r = record();
  const resolver = createHistoricalTaskDisposition({ readTask: async (repo, number, protectedRecord) => {
    assert.equal(repo, repository); assert.equal(number, 42); assert.equal(protectedRecord, r);
    return task();
  } });
  assert.equal(await resolver.resolve(r), null);
});
