import test from 'node:test';
import assert from 'node:assert/strict';
import { publishManualOutcome, validateManualSubmission } from '../src/manual-outcome.mjs';
import { createPublicationBroker } from '../src/publication-broker.mjs';
import { REPOSITORY, WRITER } from '../src/execution-contract.mjs';
import { admissionBinding, authoritySourceDigest, canonicalAuthorityJson, createAdmissionSnapshot, extractAuthorityRecord, sha256Body } from '../../contracts/src/github-authority.mjs';

const copy = value => structuredClone(value);
const charter = 'Authority model: github-native-v1\nIssue closure policy: keep-open\nBounded manual qualification.';
const head = 'a'.repeat(40);
const parent = { kind: 'issue', number: 42 };
function fixture({ prState, resultKind = 'qualification', status = 'implemented', version = '4.0' } = {}) {
  const source = { charter: { kind: 'issue-body', id: 42, parent: copy(parent), sha256: sha256Body(charter) },
    decisions: [], change_request: null, compatibility_request: null };
  const authority = { ...source, sha256: authoritySourceDigest(source) };
  const q = { repository: REPOSITORY, task: 42, charter_sha256: sha256Body(charter), purpose: 'Bounded manual qualification',
    scope: ['Qualify the admitted source.'], model: 'gpt-6.1-sol', effort: 'xhigh', subagents: false,
    validation: ['diff-check'], boundaries: ['No deployment or closure.'], branch: 'codex/task-42',
    base_sha: head, starting_head: head, existing_pr: null, issue_closure_policy: 'keep-open',
    continuation: { hold: false, next: null }, route: 'manual' };
  const snapshot = createAdmissionSnapshot({ request: q, authority }, { step: 2, attempt: 'run-123', runId: '123' });
  const requestReference = { kind: 'issue-comment', id: 101, parent, sha256: 'b'.repeat(64) };
  const legacy = { ...q, schema_version: '3.0', kind: 'task-request', parent, step: 2,
    decisions: [], context: [], supersedes: null, continuation: { hold: false, next: null, task_complete: false } };
  const envelope = { route: 'manual', issueNumber: 42, runId: 123, attemptId: 'run-123', step: 2,
    branch: q.branch, request: version === '4.0' ? snapshot : legacy, requestReference };
  const marker = version === '4.0' ? `Execution admission digest: ${admissionBinding(snapshot).sha256}`
    : `Execution request digest: ${requestReference.sha256}`;
  const pr = prState ? { number: 55, state: prState, merged: false, draft: true,
    body: `Related to #42\n${marker}`, base: { repo: { full_name: REPOSITORY } },
    head: { ref: q.branch, sha: head, repo: { full_name: REPOSITORY } } } : null;
  const result = { schema_version: version, kind: 'outcome', repository: REPOSITORY, task: 42,
    parent: pr ? { kind: 'pull_request', number: 55 } : copy(parent), charter_sha256: sha256Body(charter),
    ...(version === '4.0' ? { step: 2, authority, admission: admissionBinding(snapshot) } : { request: requestReference }),
    attempt: 'run-123', status, result: { kind: resultKind, revision: resultKind === 'git' ? head : 'qualification-123',
      identities: [{ kind: 'github-actions-run', id: '123' }] }, summary: 'Manual evidence reported; independent acceptance remains required.',
    warnings: [{ source: 'qualification:123', impact: 'Native root proof is unavailable.', resolution: 'Unresolved.',
      next_action: 'Independent reviewer must inspect this limitation.', evidence_gaps: ['No root host mutation was performed.'] }],
    limitations: ['No source merge, installation or Issue closure is authorized.'] };
  let stored = { envelope, outcome: null };
  const calls = []; const comments = []; const transitions = []; let writes = 0; let posts = 0;
  let afterPostFailure = false; let beforePostFailure = false; let revalidationError = null;
  const store = { get: async () => copy(stored), put: async (run, r) => { assert.equal(run, 123); stored = copy(r); writes++; } };
  const api = {
    userIdentity: async login => ({ login, type: 'Bot', id: 8 }),
    async get(path) {
      calls.push(['get', path]);
      if (path === '/issues/42') return { number: 42, body: charter };
      if (path === '/pulls/55' && pr) return copy(pr);
      if (/^\/issues\/comments\/\d+$/.test(path)) {
        const comment = comments.find(c => c.id === Number(path.split('/').at(-1)));
        if (comment) return copy(comment);
      }
      assert.fail(`Unexpected source read ${path}`);
    },
    async list(path) {
      calls.push(['list', path]);
      if (path.startsWith('/pulls?')) return pr ? [copy(pr)] : [];
      if (/^\/issues\/\d+\/comments$/.test(path)) return copy(comments);
      assert.fail(`Unexpected list ${path}`);
    },
    async post(path, { body }) {
      posts++; calls.push(['post', path]);
      if (beforePostFailure) { beforePostFailure = false; throw Object.assign(new Error('Ambiguous POST'), { code: 'POST_UNCERTAIN' }); }
      const comment = { id: 200 + comments.length, body, user: { login: WRITER, type: 'Bot', id: 8 } };
      comments.push(comment);
      if (afterPostFailure) { afterPostFailure = false; throw Object.assign(new Error('Lost POST response'), { code: 'POST_UNCERTAIN' }); }
      return copy(comment);
    }
  };
  // The fake transport reserves before POST and reconciles by the immutable
  // native marker; its uncertain-delivery state is observable in each test.
  async function commentOnce(r, key, number, body) {
    const marker = `<!-- relay:${envelope.attemptId}:${key} -->`;
    const expected = `${body}\n\n${marker}`;
    const matches = (await api.list(`/issues/${number}/comments`)).filter(c => c.user.login === WRITER && c.body.includes(marker));
    assert.ok(matches.length <= 1);
    if (matches.length) {
      assert.equal(matches[0].body, expected); r.commentIntent = null; await store.put(123, r); return matches[0];
    }
    if (r.commentIntent) throw Object.assign(new Error('Uncertain native publication'), { code: 'COMMENT_PUBLICATION_UNCERTAIN' });
    r.commentIntent = { key, number }; await store.put(123, r);
    const comment = await api.post(`/issues/${number}/comments`, { body: expected });
    r.commentIntent = null; await store.put(123, r); return comment;
  }
  const invoke = async (value = result) => publishManualOutcome({ api, store, record: await store.get(123),
    submission: { repository: REPOSITORY, task: 42, run_id: 123, result: value }, commentOnce,
    rememberPullRequest: async (r, value) => { r.prNumber = value.number; await store.put(123, r); },
    existingPullRequest: async () => pr,
    revalidate: async () => { calls.push(['revalidate']); if (revalidationError) throw Object.assign(new Error(revalidationError), { code: revalidationError }); },
    transitionManual: async (r, value, submitted, draft) => {
      if (!value || value.state !== 'open') return;
      transitions.push({ number: value.number, draft, outcomeAlreadyDurable: Boolean(r.outcome), status: submitted.status });
    } });
  return { result, pr, api, invoke, comments, calls, transitions, store,
    posted: () => posts, written: () => writes,
    uncertain: where => { if (where === 'after') afterPostFailure = true; else beforePostFailure = true; },
    stale: code => { revalidationError = code; } };
}

for (const version of ['3.0', '4.0']) for (const prState of [undefined, 'closed']) {
  test(`direct manual ${version} ${prState ? 'closed disposable PR' : 'no-PR Issue'} publishes one Bot Outcome without an owner source comment`, async () => {
    const f = fixture({ version, prState });
    const published = await f.invoke();
    assert.equal(published.manual, true);
    assert.equal(published.prNumber, prState ? 55 : null);
    assert.equal(f.posted(), 1); assert.equal(f.comments.length, 1);
    assert.deepEqual(extractAuthorityRecord(f.comments[0].body), f.result);
    assert.equal(f.comments[0].user.type, 'Bot');
    assert.ok(!f.comments[0].body.includes('relay-manual-result'));
    assert.deepEqual(await f.invoke(), published);
    assert.equal(f.posted(), 1); assert.equal(f.transitions.length, 0);
    assert.deepEqual(f.calls.filter(([method, path]) => method === 'get' && path.startsWith('/issues/comments/'))
      .map(([, path]) => path), ['/issues/comments/200', '/issues/comments/200']);
  });
}

test('manual exact Git head is independently bound to the admitted PR before Outcome publication', async () => {
  const f = fixture({ prState: 'open', resultKind: 'git' });
  await f.invoke();
  assert.deepEqual(f.transitions, [{ number: 55, draft: false, outcomeAlreadyDurable: true, status: 'implemented' }]);
  assert.equal(f.posted(), 1);
  f.pr.head.sha = 'c'.repeat(40);
  await assert.rejects(f.invoke(), { code: 'PR_AUTHORITY_CHANGED' });
  assert.equal(f.posted(), 1);
});

test('blocked manual Git outcome drafts before publishing and never marks Ready', async () => {
  const f = fixture({ prState: 'open', resultKind: 'git', status: 'blocked' });
  const value = await f.invoke();
  assert.equal(value.status, 'BLOCKED');
  assert.deepEqual(f.transitions, [{ number: 55, draft: true, outcomeAlreadyDurable: false, status: 'blocked' }]);
});

test('an implemented non-Git result on an open PR is rejected before irreversible publication', async () => {
  for (const resultKind of ['qualification', 'evidence', 'no-change']) {
    const f = fixture({ prState: 'open', resultKind });
    await assert.rejects(f.invoke(), { code: 'PUBLISHED_HEAD_REQUIRED' });
    assert.equal(f.posted(), 0);
    assert.equal(f.written(), 0);
    assert.equal((await f.store.get(123)).manualSubmission, undefined);
    assert.deepEqual(f.transitions, []);
  }
});

test('submitting changed claims after durable or uncertain delivery cannot replace the result', async () => {
  for (const uncertain of [false, true]) {
    const f = fixture();
    if (uncertain) f.uncertain('after');
    if (uncertain) await assert.rejects(f.invoke(), { code: 'POST_UNCERTAIN' }); else await f.invoke();
    await assert.rejects(f.invoke({ ...f.result, summary: 'Changed result claim.' }), { code: 'MANUAL_OUTCOME_CHANGED' });
    assert.equal(f.posted(), 1); assert.equal(f.comments.length, 1);
  }
});

test('lost POST response reconciles the exact native Outcome without a second POST', async () => {
  const f = fixture(); f.uncertain('after');
  await assert.rejects(f.invoke(), { code: 'POST_UNCERTAIN' });
  assert.equal(f.comments.length, 1); assert.equal((await f.store.get(123)).commentIntent.key, 'outcome');
  const value = await f.invoke();
  assert.equal(value.outcomeId, 200); assert.equal(f.posted(), 1);
  assert.equal((await f.store.get(123)).commentIntent, null);
});

test('uncertain POST with no discoverable native record stops instead of repeating it', async () => {
  const f = fixture(); f.uncertain('before');
  await assert.rejects(f.invoke(), { code: 'POST_UNCERTAIN' });
  await assert.rejects(f.invoke(), { code: 'COMMENT_PUBLICATION_UNCERTAIN' });
  assert.equal(f.posted(), 1); assert.equal(f.comments.length, 0);
});

test('live authority failure before publication retains submission identity and publishes nothing', async () => {
  const f = fixture(); f.stale('AUTHORITY_SOURCE_MISMATCH');
  await assert.rejects(f.invoke(), { code: 'AUTHORITY_SOURCE_MISMATCH' });
  assert.equal(f.posted(), 0);
  assert.equal((await f.store.get(123)).manualSubmission.sha256, sha256Body(canonicalAuthorityJson(f.result)));
});

test('canonical result target, charter, attempt and admission bindings reject tampering before POST', async () => {
  for (const [change, code] of [
    [r => { r.repository = 'foreign/repository'; }, 'AUTHORITY_TARGET_MISMATCH'],
    [r => { r.task = 43; }, 'AUTHORITY_TARGET_MISMATCH'],
    [r => { r.charter_sha256 = 'c'.repeat(64); }, 'AUTHORITY_CHARTER_MISMATCH'],
    [r => { r.attempt = 'run-999'; }, 'AUTHORITY_ADMISSION_MISMATCH'],
    [r => { r.step = 3; }, 'AUTHORITY_ADMISSION_MISMATCH'],
    [r => { r.admission.sha256 = 'c'.repeat(64); }, 'MANUAL_OUTCOME_BINDING_INVALID'],
    [r => { r.parent.number = 43; }, 'PR_AUTHORITY_CHANGED']
  ]) {
    const f = fixture(); const result = copy(f.result); change(result);
    await assert.rejects(f.invoke(result), { code }); assert.equal(f.posted(), 0);
  }
});

test('durable native Outcome readback validates the Writer identity and complete body bytes', async () => {
  for (const mutate of [c => { c.user.login = 'owner'; }, c => { c.body += '\nChanged.'; }]) {
    const f = fixture(); await f.invoke(); mutate(f.comments[0]);
    await assert.rejects(f.invoke(), { code: 'COMMENT_CONTENT_CHANGED' }); assert.equal(f.posted(), 1);
  }
});

test('worker broker rejects a caller-supplied manual capability before any protected read', async () => {
  const touched = () => assert.fail('Worker request reached protected state');
  const broker = createPublicationBroker({ api: { get: touched, list: touched }, store: { get: touched }, publisher: {} });
  for (const extra of [{}, { capability: 'manual-outcome' }, { allowManualOutcome: true }, { actor: 'owner' }])
    await assert.rejects(broker.dispatch({ operation: 'manual-outcome-direct', runId: 123, attemptId: 'run-123', ...extra }),
      { code: 'MANUAL_CAPABILITY_REQUIRED' });
});

test('submission envelope is narrow and bounded rather than a generic Writer command', () => {
  const f = fixture(); const valid = { repository: REPOSITORY, task: 42, run_id: 123, result: f.result };
  assert.equal(validateManualSubmission(valid), valid);
  for (const delta of [{ operation: 'merge' }, { capability: 'owner' }, { repository: 'foreign/repository' },
    { run_id: 0 }, { task: -1 }, { result: null }, { result: { summary: 'x'.repeat(110 * 1024) } }])
    assert.throws(() => validateManualSubmission({ ...valid, ...delta }), { code: 'MANUAL_SUBMISSION_INVALID' });
});
