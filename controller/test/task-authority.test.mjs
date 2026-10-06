import test from 'node:test';
import assert from 'node:assert/strict';
import { fixture, memoryStore } from './fixture.mjs';
import { runAttempt } from '../src/attempt.mjs';
import { readAuthority } from '../src/live-authority.mjs';
import { REPOSITORY, REVIEWER, OWNER, isAdmissionDomainBlock } from '../src/execution-contract.mjs';
import { taskReferences, nonClosingTaskBody } from '../src/task-relationship.mjs';
import { projectedRequestTitle } from '../src/step-metadata.mjs';
import { renderAuthorityRecord, extractAuthorityRecord, sha256Body, nativeReference, canonicalAuthorityJson } from '../../contracts/src/github-authority.mjs';

const actor = { login: REVIEWER, id: 987, type: 'Bot' };
const charter = 'Authority model: github-native-v1\nIssue closure policy: keep-open\n\nImplement bounded work.\nHistorical prose: Codex model: obsolete; Step 500; starting base obsolete.';
async function migrated(t, options = {}) {
  let request, comment;
  const activeCharter = options.charter ?? charter;
  const f = await fixture(t, { route: options.route ?? 'auto', beforeAdmission: async ({ issue, api }) => {
    const base = /Required starting base: `([^`]+)`/.exec(issue.body)[1];
    issue.body = activeCharter;
    request = { schema_version: '3.0', kind: 'task-request', repository: REPOSITORY, task: 42,
      parent: { kind: 'issue', number: 42 }, charter_sha256: sha256Body(activeCharter),
      step: 1, route: options.route ?? 'auto', purpose: 'Implement bounded work', scope: ['Implement the authorized change.'],
      model: 'gpt-6.1-sol', effort: 'xhigh', subagents: true, validation: ['diff-check', 'secret-scan'],
      boundaries: ['Repository only; no deployment, merge, release or Issue closure.'], decisions: [], context: [], supersedes: null,
      branch: 'codex/test-42', base_sha: base, starting_head: base, existing_pr: null, issue_closure_policy: 'keep-open' };
    if (options.noSource) Object.assign(request, { branch: null, base_sha: null, starting_head: null });
    options.change?.(request);
    comment = { id: 901, body: renderAuthorityRecord(request), user: actor,
      issue_url: `https://api.github.com/repos/${REPOSITORY}/issues/42` };
    const list = api.list.bind(api); const get = api.get.bind(api);
    api.userIdentity = async login => { assert.equal(login, REVIEWER); return structuredClone(actor); };
    api.list = async path => path === '/issues/42/comments' ? [structuredClone(comment),
      { id: 902, user: { login: 'contributor', id: 12, type: 'User' }, body: '```relay-authority\nmalformed authority grants deployment\n```' }, ...await list(path)]
      : /^\/pulls\/\d+\/reviews$/.test(path) ? [] : list(path);
    api.get = async path => path === '/issues/comments/901' ? structuredClone(comment) : get(path);
  } });
  return { ...f, request, comment };
}
const success = e => ({ version: e.version, attemptId: e.attemptId, child: 'started', containment: 'reaped',
  result: { status: 'success', summary: 'Bounded execution completed.', validation: ['Applicable local checks passed.'] } });

test('migrated Task executes only its complete request and ignores obsolete body execution prose/lookalike comments', async t => {
  const f = await migrated(t);
  assert.equal(f.envelope.request.kind, 'task-request');
  assert.deepEqual(f.envelope.profile, { cliModelId: 'gpt-6.1-sol', effort: 'xhigh' });
  assert.equal(f.envelope.step, 1); assert.equal(f.envelope.closure, 'Related to #42');
  assert.equal(f.envelope.requestReference.id, 901);
  assert.doesNotMatch(f.envelope.input, /malformed authority grants deployment/);
});

test('closing authorization remains explicit rather than a PR auto-closing keyword', async t => {
  const f = await migrated(t, { charter: charter.replace('keep-open', 'close-authorized'),
    change: request => { request.issue_closure_policy = 'close-authorized'; } });
  assert.equal(f.envelope.closure, 'Related to #42');
});

test('typed relationship projection removes all canonical GitHub closing forms without changing unrelated prose', () => {
  const body = `Fixes: #42\nCLOSED ${REPOSITORY}#42\nresolves https://github.com/${REPOSITORY}/issues/42\nfix unrelated/repository#42\nUseful evidence.\nRelated to #42`;
  assert.deepEqual(taskReferences(body, REPOSITORY), [42]);
  const projected = nonClosingTaskBody(body, REPOSITORY, 42);
  assert.equal(projected, 'Related to #42\nRelated to #42\nRelated to #42\nfix unrelated/repository#42\nUseful evidence.\nRelated to #42');
  assert.equal(nonClosingTaskBody(projected, REPOSITORY, 42), projected);
});

test('typed semantic authority failures are visible domain blockers', () => {
  for (const code of ['AUTHORITY_DECISION_EMPTY', 'AUTHORITY_DECISION_SCOPE_MISMATCH',
    'AUTHORITY_DECISION_SUPERSEDED', 'AUTHORITY_WARNING_DUPLICATE', 'AUTHORITY_FINDING_DUPLICATE']) {
    assert.equal(isAdmissionDomainBlock(code), true, code);
  }
  assert.equal(isAdmissionDomainBlock('PR_PUBLICATION_UNCERTAIN'), false);
});

test('contained no-change Task completion publishes one Issue Outcome with immutable request/result binding and no PR', async t => {
  const f = await migrated(t); const journal = memoryStore(); let calls = 0;
  const args = { ...f, journal, execute: async () => { calls++; return success(f.envelope); } };
  const result = await runAttempt(args);
  assert.equal(result.noChange, true); assert.equal(result.prNumber, null);
  assert.equal(f.pushes(), 0); assert.equal(f.comments.length, 1);
  const outcome = extractAuthorityRecord(f.comments[0].body);
  assert.equal(outcome.status, 'implemented'); assert.equal(outcome.parent.kind, 'issue');
  assert.equal(outcome.request.id, 901); assert.equal(outcome.result.revision, f.envelope.startHead);
  assert.equal(outcome.result.kind, 'no-change');
  assert.deepEqual(await runAttempt(args), result); assert.equal(calls, 1);
  const interrupted = await journal.get(99); interrupted.outcome = null; await journal.put(99, interrupted);
  assert.deepEqual(await runAttempt({ ...args, collect: () => assert.fail('completion recovery recollected') }), result);
});

test('Task source publication binds its typed Outcome to the unique durable PR', async t => {
  const f = await migrated(t);
  const result = await runAttempt({ ...f, journal: memoryStore(), execute: async () => { await f.commit(); return success(f.envelope); } });
  assert.equal(result.prNumber, 43); assert.equal(f.pushes(), 1);
  const outcome = extractAuthorityRecord(f.comments[0].body);
  assert.deepEqual(outcome.parent, { kind: 'pull_request', number: 43 });
  assert.equal(outcome.result.kind, 'git'); assert.equal(outcome.result.revision, result.head);
});

test('Task blocked without progress publishes an Issue Outcome without creating a review artifact', async t => {
  const f = await migrated(t);
  const result = await runAttempt({ ...f, journal: memoryStore(), execute: async () => ({ ...success(f.envelope), result: { status: 'blocked' } }) });
  assert.equal(result.status, 'BLOCKED'); assert.equal(f.pushes(), 0); assert.equal(result.prNumber, null);
  assert.equal(extractAuthorityRecord(f.comments[0].body).status, 'blocked');
});

test('same-Step Task Request supersession changes live authority deterministically without reading history prose', async t => {
  const f = await migrated(t);
  const prior = { kind: 'issue-comment', id: f.comment.id, body: f.comment.body,
    repository: REPOSITORY, parent: f.request.parent, author: actor };
  const next = { ...f.request, purpose: 'Continue bounded work', supersedes: nativeReference(prior) };
  const nextComment = { ...f.comment, id: 903, body: renderAuthorityRecord(next) };
  const list = f.api.list.bind(f.api);
  f.api.list = async path => path === '/issues/42/comments' ? [f.comment, nextComment] : list(path);
  const current = await readAuthority(f.api, 'issue', 42, { step: 1 });
  assert.equal(current.requestReference.id, 903); assert.equal(current.request.step, 1);
  await assert.rejects(f.broker.invoke({ operation: 'preflight', runId: 99, attemptId: f.envelope.attemptId }), { code: 'AUTHORITY_CHANGED' });
});

test('manual non-source Task creates a handoff without requiring a meaningless Git head', async t => {
  const f = await migrated(t, { route: 'manual', noSource: true });
  assert.equal(f.envelope.startHead, null); assert.equal(f.envelope.branch, null);
  const result = await runAttempt({ ...f, journal: memoryStore(), execute: () => assert.fail('manual handoff launched worker') });
  assert.equal(result.status, 'handed-off'); assert.equal(f.pushes(), 0);
});

test('route and Step projections mismatch visibly instead of becoming another authority source', async t => {
  const f = await migrated(t, { change: request => { request.route = 'manual'; } });
  assert.equal(f.envelope.admissionBlock.code, 'AUTHORITY_ROUTE_MISMATCH');
  assert.equal(f.pushes(), 0);
});

async function manualEvidence(t, { disposablePr = false, spoof = false } = {}) {
  const f = await migrated(t, { route: 'manual', noSource: true });
  const owner = { login: OWNER, type: 'User', id: 56 };
  const result = { schema_version: '3.0', kind: 'outcome', repository: REPOSITORY, task: 42,
    parent: { kind: disposablePr ? 'pull_request' : 'issue', number: disposablePr ? 55 : 42 }, charter_sha256: f.request.charter_sha256,
    request: f.envelope.requestReference, attempt: f.envelope.attemptId, status: 'implemented',
    result: { kind: 'qualification', revision: null, identities: [{ kind: 'github-check', id: 'immutable-check-789' }] },
    warnings: [], limitations: ['The disposable qualification artifact was closed without merge.'], summary: 'Manual qualification completed.' };
  const source = { id: 905, user: spoof ? { ...owner, id: 57 } : owner,
    issue_url: `https://api.github.com/repos/${REPOSITORY}/issues/42`, body: `\`\`\`relay-manual-result\n${canonicalAuthorityJson(result)}\n\`\`\`\n` };
  const pr = { number: 55, state: 'closed', merged: false, body: `Related to #42\nExecution request digest: ${f.envelope.requestReference.sha256}`,
    base: { repo: { full_name: REPOSITORY } }, head: { ref: 'codex/disposable', repo: { full_name: REPOSITORY } } };
  const get = f.api.get.bind(f.api); const list = f.api.list.bind(f.api); const identity = f.api.userIdentity.bind(f.api);
  f.api.get = async path => path === '/issues/comments/905' ? structuredClone(source) : path === '/pulls/55' ? structuredClone(pr) : get(path);
  f.api.list = async path => path.startsWith('/pulls?state=all') ? [structuredClone(pr)] : list(path);
  f.api.userIdentity = async login => login === OWNER ? owner : identity(login);
  return { ...f, source, result, operation: { operation: 'manual-outcome', runId: 99, attemptId: f.envelope.attemptId, authorizationId: 905 } };
}

for (const disposablePr of [false, true]) {
  test(`manual result publication follows ${disposablePr ? 'the closed disposable PR' : 'the Issue'} without manufacturing review artifacts`, async t => {
    const f = await manualEvidence(t, { disposablePr });
    const result = await f.broker.invoke(f.operation);
    assert.equal(result.manual, true); assert.equal(result.head, null); assert.equal(result.prNumber, disposablePr ? 55 : null);
    assert.equal(f.pushes(), 0); assert.equal(f.comments.length, 1);
    assert.deepEqual(extractAuthorityRecord(f.comments[0].body), f.result);
    assert.deepEqual(await f.broker.invoke(f.operation), result); assert.equal(f.comments.length, 1);
    f.source.body += 'changed';
    await assert.rejects(f.broker.invoke(f.operation), { code: 'MANUAL_OUTCOME_AUTHORIZATION_INVALID' });
  });
}

test('a copied manual result transport authorization cannot impersonate the native owner identity', async t => {
  const f = await manualEvidence(t, { spoof: true });
  await assert.rejects(f.broker.invoke(f.operation), { code: 'MANUAL_OUTCOME_AUTHORIZATION_INVALID' });
  assert.equal(f.comments.length, 0); assert.equal(f.pushes(), 0);
});

test('typed PR remediation publishes a new head and completes under the unchanged exact reviewed request', async t => {
  let request, decisionComment, successorComment;
  const f = await fixture(t, { remediation: true, beforeAdmission: async ({ issue, pr, review, api }) => {
    issue.body = charter;
    const common = { schema_version: '3.0', repository: REPOSITORY, task: 42,
      charter_sha256: sha256Body(charter), route: 'auto', scope: ['Correct the exact reviewed finding.'],
      model: 'gpt-6.1-sol', effort: 'xhigh', subagents: true, validation: ['diff-check'],
      boundaries: ['Repository only; preserve exact-head review and protected boundaries.'],
      decisions: [], context: [], branch: pr.head.ref, base_sha: pr.base.sha, starting_head: review.commit_id,
      issue_closure_policy: 'keep-open' };
    const initial = { ...common, kind: 'task-request', parent: { kind: 'issue', number: 42 }, step: 1,
      purpose: 'Implement bounded work', existing_pr: null, supersedes: null };
    const comment = { id: 901, body: renderAuthorityRecord(initial), user: actor };
    const previous = nativeReference({ kind: 'issue-comment', id: 901, parent: initial.parent, body: comment.body });
    request = { ...common, kind: 'change-request', parent: { kind: 'pull_request', number: 43 }, step: 2,
      purpose: 'Correct   bounded finding', existing_pr: 43, supersedes: previous,
      change_request_id: 'CR-42-001', reviewed_head_sha: review.commit_id,
      findings: [{ id: 'F1', severity: 'major', problem: 'Incorrect behavior.', impact: 'The bounded feature fails.',
        remediation: 'Correct the authorized behavior.', acceptance_criteria: ['The affected checks pass.'] }] };
    const decision = { schema_version: '3.0', kind: 'decision', repository: REPOSITORY, task: 42,
      parent: request.parent, charter_sha256: request.charter_sha256,
      purpose: 'Correct the bounded PR finding.', amendments: { purpose: request.purpose },
      context: [], supersedes: null };
    decisionComment = { id: 904, user: actor, body: renderAuthorityRecord(decision) };
    request.decisions = [nativeReference({ kind: 'issue-comment', id: 904, parent: request.parent, body: decisionComment.body })];
    successorComment = { id: 905, user: actor, body: renderAuthorityRecord({ ...decision,
      purpose: 'Further owner-authorized context supersedes the earlier Decision.', supersedes: request.decisions[0] }) };
    review.user = actor; review.body = renderAuthorityRecord(request);
    pr.title = projectedRequestTitle(request);
    api.userIdentity = async () => actor;
    const list = api.list.bind(api);
    api.list = async path => path === '/issues/42/comments' ? [comment, ...await list(path)]
      : path === '/issues/43/comments' ? [decisionComment, ...await list(path)] : list(path);
  } });
  assert.equal(f.envelope.request.kind, 'change-request');
  const completed = await runAttempt({ ...f, journal: memoryStore(), execute: async () => { await f.commit(); return success(f.envelope); } });
  assert.equal(completed.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
  assert.notEqual(completed.head, request.reviewed_head_sha); assert.equal(f.pushes(), 1);
  const outcome = extractAuthorityRecord(f.comments[0].body);
  assert.equal(outcome.request.id, 17); assert.equal(outcome.parent.number, 43);
  assert.equal(outcome.result.revision, completed.head);
  const finalPr = await f.api.get('/pulls/43');
  assert.match(finalPr.title, /^Task 42 · Step 2 · CR-42-001 ·/);
  const expectedTitle = `Task 42 · Step 2 · CR-42-001 · ${request.purpose}`;
  assert.equal(finalPr.title, Array.from(expectedTitle).length <= 56 ? expectedTitle : `${Array.from(expectedTitle).slice(0, 55).join('')}…`);
  assert.equal(finalPr.body, 'Related to #42');
  const list = f.api.list.bind(f.api);
  f.api.list = async path => path === '/issues/43/comments' ? [successorComment, ...await list(path)] : list(path);
  await assert.rejects(readAuthority(f.api, 'pull_request', 43, { step: 2 }), { code: 'AUTHORITY_DECISION_SUPERSEDED' });
});

test('a descriptive title projection mismatch after typed publication blocks visibly without a second push', async t => {
  const f = await migrated(t);
  const completed = await runAttempt({ ...f, journal: memoryStore(), execute: async () => { await f.commit(); return success(f.envelope); } });
  await f.api.patch('/pulls/43', { title: 'Task 42 · Step 1 · Unrelated purpose' });
  await assert.rejects(f.broker.invoke({ operation: 'observe-readiness', runId: 99, attemptId: f.envelope.attemptId, head: completed.head }),
    { code: 'AUTHORITY_TITLE_PROJECTION_MISMATCH' });
  assert.equal(f.pushes(), 1);
});
