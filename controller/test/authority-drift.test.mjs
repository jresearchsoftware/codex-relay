import test from 'node:test';
import assert from 'node:assert/strict';
import { fixture } from './fixture.mjs';
import { runAttempt } from '../src/attempt.mjs';
import { createPublicationBroker } from '../src/publication-broker.mjs';
import { revalidateAuthority } from '../src/live-authority.mjs';
import { REPOSITORY, REVIEWER, WRITER } from '../src/execution-contract.mjs';
import { admissionBinding, canonicalAuthorityJson, extractAuthorityRecord, sha256Body } from '../../contracts/src/github-authority.mjs';

const charter = 'Authority model: github-native-v1\nIssue closure policy: keep-open\nImplement the admitted source and report the exact result.';
const originalScope = ['Original authorized source work'];
const originalBoundaries = ['No deployment', 'No release'];
const copy = value => structuredClone(value);
async function driftFixture(t, { manual = false } = {}) {
  const decisions = [];
  let sequence = 900;
  const amend = amendments => {
    const record = { schema_version: '4.0', kind: 'decision', repository: REPOSITORY, task: 42,
      parent: { kind: 'issue', number: 42 }, charter_sha256: sha256Body(charter), purpose: 'Apply trusted owner direction',
      amendments, supersedes: null, context: [] };
    const native = { id: sequence++, user: { login: REVIEWER, type: 'Bot', id: 701 },
      body: '```relay-authority\n' + canonicalAuthorityJson(record) + '\n```\n' };
    decisions.push(native); return native;
  };
  amend({ scope: originalScope, boundaries: originalBoundaries, validation: ['diff-check'] });
  const f = await fixture(t, { issueBody: charter, route: manual ? 'manual' : 'auto', labelLaunch: true,
    streamlinedAdmission: true, beforeAdmission: ({ api }) => {
      const list = api.list.bind(api);
      api.list = async path => path === '/issues/42/comments' ? [...decisions, ...await list(path)]
        : path === '/pulls/43/reviews' ? [] : list(path);
    } });
  const originalEnvelope = copy(f.envelope);
  const execute = async e => ({ version: 2, attemptId: e.attemptId, child: 'started', containment: 'reaped',
    result: { status: 'success', summary: 'Original admitted work delivered; amended work is independently assessed.', validation: [] } });
  return { ...f, decisions, amend, originalEnvelope, execute };
}

for (const changedWorkImplemented of [false, true]) {
  test(`automatic source completion after scope expansion reports original admission (${changedWorkImplemented ? 'amended work also implemented' : 'amended work remains'})`, async t => {
    const f = await driftFixture(t);
    const result = await runAttempt({ ...f, execute: async e => {
      await f.commit('docs/work.md', changedWorkImplemented ? 'Original and amended work implemented.\n' : 'Original work implemented.\n');
      f.amend({ scope: [...originalScope, 'Additional current requirement'] });
      return f.execute(e);
    } });
    assert.equal(result.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
    const outcomes = f.comments.map(c => extractAuthorityRecord(c.body)).filter(value => value?.kind === 'outcome');
    assert.equal(outcomes.length, 1);
    assert.deepEqual(outcomes[0].authority, f.originalEnvelope.request.authority);
    assert.deepEqual(outcomes[0].admission, admissionBinding(f.originalEnvelope.request));
    assert.deepEqual(outcomes[0].authority_resolution, f.originalEnvelope.request.authority_resolution);
    assert.deepEqual(outcomes[0].authority_drift.changed_fields, ['scope']);
    assert.equal(outcomes[0].authority_drift.review_required, true);
    assert.equal(outcomes[0].result.revision, await f.remoteHead());
    assert.deepEqual((await f.store.get(99)).envelope, f.originalEnvelope);
    assert.match(f.comments.find(c => c.body.includes('Current trusted authority digest:')).body, /Current-requirement review required: yes/);
    const replay = await runAttempt({ ...f, admissionResumed: true, execute: () => assert.fail('replay executed') });
    assert.deepEqual(replay, result);
    assert.equal(f.comments.map(c => extractAuthorityRecord(c.body)).filter(value => value?.kind === 'outcome').length, 1);
  });
}

test('unused expanded permissions preserve original restrictions and allow source publication', async t => {
  const f = await driftFixture(t);
  const result = await runAttempt({ ...f, execute: async e => {
    await f.commit();
    f.amend({ boundaries: ['No deployment'] });
    return f.execute(e);
  } });
  assert.equal(result.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
  const outcome = f.comments.map(c => extractAuthorityRecord(c.body)).find(value => value?.kind === 'outcome');
  assert.deepEqual(outcome.authority_drift.changed_fields, ['boundaries']);
  assert.deepEqual((await f.store.get(99)).envelope.request.boundaries, originalBoundaries);
});

for (const amendments of [{ boundaries: [...originalBoundaries, 'Source publication is revoked'] },
  { scope: ['Different replacement work'] }, { validation: ['diff-check', 'secret-scan'] }]) {
  test(`changed action-time constraint ${Object.keys(amendments)[0]} blocks source publication while one truthful Outcome remains available`, async t => {
    const f = await driftFixture(t);
    let localHead;
    await assert.rejects(runAttempt({ ...f, execute: async e => {
      localHead = await f.commit(); f.amend(amendments); return f.execute(e);
    } }), { code: 'AUTHORITY_CHANGED' });
    assert.equal((await f.store.get(99)).outcome.status, 'BLOCKED');
    assert.equal(await f.remoteHead(), null);
    assert.equal(await f.command(f.cwd, ['rev-parse', 'HEAD']), localHead);
    const outcome = f.comments.map(c => extractAuthorityRecord(c.body)).find(value => value?.kind === 'outcome');
    assert.equal(outcome.status, 'blocked');
    assert.equal(outcome.authority_drift.review_required, true);
    assert.deepEqual(outcome.authority, f.originalEnvelope.request.authority);
    assert.deepEqual((await f.store.get(99)).envelope, f.originalEnvelope);
  });
}

test('manual no-PR reporting accepts trusted Decision drift and preserves claims through later drift and replay', async t => {
  const f = await driftFixture(t, { manual: true });
  const e = f.envelope;
  const post = f.api.post.bind(f.api);
  const identity = f.api.userIdentity.bind(f.api);
  f.api.userIdentity = login => login === WRITER ? Promise.resolve({ login, id: 702, type: 'Bot' }) : identity(login);
  f.api.post = async (path, data) => {
    const comment = await post(path, data);
    if (path.endsWith('/comments')) {
      comment.user = { login: WRITER, id: 702, type: 'Bot' };
      f.comments.find(c => c.id === comment.id).user = copy(comment.user);
    }
    return comment;
  };
  const result = { schema_version: '4.0', kind: 'outcome', repository: REPOSITORY, task: 42,
    parent: { kind: 'issue', number: 42 }, charter_sha256: e.request.charter_sha256,
    authority: e.request.authority, admission: admissionBinding(e.request), step: e.step, attempt: e.attemptId,
    status: 'implemented', result: { kind: 'qualification', revision: 'qualification-99', identities: [{ kind: 'qualification', id: '99' }] },
    summary: 'Original qualification completed; current requirements await independent assessment.', warnings: [], limitations: [] };
  const broker = createPublicationBroker({ api: f.api, store: f.store, publisher: {}, journal: f.journal, allowManualOutcome: true });
  const invoke = value => broker.dispatch({ operation: 'manual-outcome-direct', runId: e.runId, attemptId: e.attemptId,
    submission: { repository: REPOSITORY, task: 42, run_id: e.runId, result: value ?? result } });
  f.amend({ boundaries: [...originalBoundaries, 'Protected action permission revoked'], scope: [...originalScope, 'New qualification evidence'] });
  const invented = copy(e.request.authority_resolution);
  invented.project_defaults.model = 'caller-invented-default';
  await assert.rejects(invoke({ ...result, authority_resolution: invented }), { code: 'MANUAL_OUTCOME_BINDING_INVALID' });
  assert.equal((await f.store.get(99)).manualSubmission, undefined);
  const receipt = await invoke();
  assert.equal(receipt.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
  const published = f.comments.find(c => extractAuthorityRecord(c.body)?.kind === 'outcome');
  const bytes = published.body;
  const outcome = extractAuthorityRecord(bytes);
  assert.deepEqual(outcome.authority_drift.changed_fields, ['boundaries', 'scope']);
  assert.deepEqual(outcome.authority, result.authority);
  assert.deepEqual(outcome.authority_resolution, e.request.authority_resolution);
  f.amend({ scope: [...originalScope, 'Another current requirement'] });
  assert.deepEqual(await invoke(), receipt);
  assert.equal(published.body, bytes);
  await assert.rejects(invoke({ ...result, summary: 'Replace original claims.' }), { code: 'MANUAL_OUTCOME_CHANGED' });
  assert.equal(f.comments.filter(c => extractAuthorityRecord(c.body)?.kind === 'outcome').length, 1);
});

test('reporting still rejects altered original source bytes, wrong trusted actor and execution identity', async t => {
  for (const change of ['bytes', 'actor', 'digest', 'snapshot-scope']) {
    const f = await driftFixture(t);
    if (change === 'bytes') f.decisions[0].body += '<!-- edited -->';
    if (change === 'actor') f.decisions[0].user.id++;
    if (change === 'digest') f.envelope.authorityDigest = 'f'.repeat(64);
    if (change === 'snapshot-scope') f.envelope.request.scope = ['Caller-expanded scope'];
    await assert.rejects(revalidateAuthority(f.api, f.envelope, { reporting: true }),
      { code: change === 'digest' ? 'EXECUTION_ENVELOPE_INVALID'
        : change === 'snapshot-scope' ? 'AUTHORITY_CHANGED' : 'AUTHORITY_SOURCE_MISMATCH' });
  }
});

test('late original reporting survives new starting pins while active effects remain bound to current authority', async t => {
  for (const amendments of [{ branch: 'codex/other' }, { base_sha: 'f'.repeat(40) }, { starting_head: 'f'.repeat(40) }]) {
    const f = await driftFixture(t);
    f.amend(amendments);
    const reported = await revalidateAuthority(f.api, f.envelope, { reporting: true });
    assert.equal(reported.authorityDrift.review_required, true);
    for (const field of Object.keys(amendments)) assert.ok(reported.authorityDrift.changed_fields.includes(field));
    await assert.rejects(revalidateAuthority(f.api, f.envelope), { code: 'AUTHORITY_CHANGED' });
    assert.deepEqual((await f.store.get(99)).envelope, f.originalEnvelope);
  }
});
