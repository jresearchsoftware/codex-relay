import test from 'node:test';
import assert from 'node:assert/strict';
import { fixture } from './fixture.mjs';
import { OWNER, REPOSITORY } from '../src/execution-contract.mjs';
import { authorizeRecoveryCollection, recoveryAuthorization, recoveryAuthorizationBody } from '../src/publication-recovery.mjs';

async function authorized(t) {
  const f = await fixture(t, { remediation: true });
  f.run.status = 'completed'; f.run.updated_at = '2026-09-04T12:01:00Z';
  const record = await f.store.get(f.envelope.runId);
  const head = 'a'.repeat(40);
  record.publicationIntent = { previous: f.envelope.startHead, head };
  const binding = recoveryAuthorization(f.envelope, record.publicationIntent);
  const comment = { id: 10000, user: { login: OWNER, type: 'User' },
    issue_url: `https://api.github.com/repos/${REPOSITORY}/issues/${f.envelope.number}`,
    created_at: '2026-09-04T12:02:00Z', updated_at: '2026-09-04T12:02:00Z',
    body: recoveryAuthorizationBody(binding) };
  f.comments.push(comment);
  return { ...f, record, binding, comment, head, request: { api: f.api, record, authorizationId: comment.id } };
}

test('recovery collection validates the exact unconsumed authorization without mutation or reservation', async t => {
  const f = await authorized(t);
  const original = structuredClone(f.record);
  assert.equal(await authorizeRecoveryCollection(f.request), f.head);
  assert.equal(await authorizeRecoveryCollection(f.request), f.head);
  assert.deepEqual(f.record, original);
  assert.equal(f.pushes(), 0);
});

test('recovery collection retains native intent, owner, freshness and original-run gates', async t => {
  const f = await authorized(t);
  const original = structuredClone(f.comment);
  for (const change of [
    { user: { login: 'other', type: 'User' } },
    { created_at: f.run.updated_at, updated_at: f.run.updated_at },
    { body: recoveryAuthorizationBody({ ...f.binding, head: 'b'.repeat(40) }) }
  ]) {
    Object.assign(f.comment, original, change);
    await assert.rejects(authorizeRecoveryCollection(f.request), { code: 'RECOVERY_OWNER_AUTHORIZATION_INVALID' });
  }
  Object.assign(f.comment, original);
  f.run.status = 'in_progress';
  await assert.rejects(authorizeRecoveryCollection(f.request), { code: 'RECOVERY_ORIGINAL_RUN_NOT_COMPLETED' });
  f.run.status = 'completed';
  const intent = f.record.publicationIntent;
  for (const value of [null, { ...intent, previous: 'b'.repeat(40) }]) {
    f.record.publicationIntent = value;
    await assert.rejects(authorizeRecoveryCollection(f.request), { code: 'RECOVERY_INTENT_REQUIRED' });
  }
  f.record.publicationIntent = intent;
  await assert.rejects(authorizeRecoveryCollection({ ...f.request, authorizationId: null }), { code: 'RECOVERY_OWNER_AUTHORIZATION_REQUIRED' });
  assert.equal(f.record.publicationRecoveries, undefined);
  assert.equal(f.pushes(), 0);
});

test('consumed recovery permits collection only for its exact published binding and receipt', async t => {
  const f = await authorized(t);
  const consumed = { authorizationId: f.comment.id, binding: f.binding,
    reservedAt: '2026-09-04T12:03:00Z', completedAt: '2026-09-04T12:04:00Z',
    result: { status: 'PUBLISHED', recoveryAuthorizationId: f.comment.id, publishedHead: f.head } };
  f.record.publicationIntent = null; f.record.publishedHead = f.head;
  f.record.publicationRecoveries = [structuredClone(consumed)];
  const original = structuredClone(f.record);
  assert.equal(await authorizeRecoveryCollection(f.request), f.head);
  assert.deepEqual(f.record, original);
  for (const mutate of [
    r => { r.publishedHead = 'b'.repeat(40); },
    r => { r.publicationIntent = { previous: f.head, head: 'b'.repeat(40) }; },
    r => { r.publicationRecoveries[0].binding.attemptId = 'run-100'; },
    r => { r.publicationRecoveries[0].binding.afterAuthorizationId = 1; },
    r => { r.publicationRecoveries[0].result.recoveryAuthorizationId++; },
    r => { r.publicationRecoveries[0].result.publishedHead = 'b'.repeat(40); }
  ]) {
    Object.assign(f.record, structuredClone(original)); mutate(f.record);
    await assert.rejects(authorizeRecoveryCollection(f.request), { code: 'RECOVERY_CANDIDATE_CHANGED' });
  }
  Object.assign(f.record, structuredClone(original));
  for (const result of [null, { status: 'PUBLICATION_UNCERTAIN' }]) {
    f.record.publicationRecoveries[0].result = result;
    await assert.rejects(authorizeRecoveryCollection(f.request), { code: 'PUBLICATION_UNCERTAIN' });
  }
  assert.equal(f.pushes(), 0);
});
