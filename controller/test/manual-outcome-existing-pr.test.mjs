import test from 'node:test';
import assert from 'node:assert/strict';
import { writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { fixture } from './fixture.mjs';
import { runAttempt } from '../src/attempt.mjs';
import { createPublicationBroker } from '../src/publication-broker.mjs';
import { labelRunName } from '../src/launch-metadata.mjs';
import { REPOSITORY, REVIEWER, WRITER } from '../src/execution-contract.mjs';
import { CONSUMER } from '../../consumer/consumer.mjs';
import { admissionBinding, extractAuthorityRecord, renderAuthorityRecord, sha256Body } from '../../contracts/src/github-authority.mjs';

const copy = value => structuredClone(value);
const charter = 'Authority model: github-native-v1\nIssue closure policy: keep-open\nDeliver the bounded repository change and preserve independent exact-head acceptance.';
const reviewer = { login: REVIEWER, id: 701, type: 'Bot' };
const writer = { login: WRITER, id: 702, type: 'Bot' };

// The first admission, Git publication and PR provenance are produced by the
// real automatic broker. The second admission uses the real current v4 native
// CR or trusted Task Decision path. Only the GitHub transport is synthetic.
async function existingPr(t, route, race) {
  const f = await fixture(t, { issueBody: charter, labelLaunch: true, streamlinedAdmission: true });
  const automatic = await runAttempt({ ...f, execute: async () => {
    await f.commit();
    return { version: 2, attemptId: f.envelope.attemptId, child: 'started', containment: 'reaped',
      result: { status: 'success', summary: 'Initial implementation delivered.', validation: [] } };
  } });
  assert.equal(automatic.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
  const pr = await f.api.get('/pulls/43');
  const originalBody = pr.body;
  assert.ok(originalBody.includes(`Execution admission digest: ${admissionBinding(f.envelope.request).sha256}`));
  const reviews = []; const decisions = []; const duplicates = [];
  const get = f.api.get.bind(f.api); const list = f.api.list.bind(f.api);
  const post = f.api.post.bind(f.api); const patch = f.api.patch.bind(f.api); const put = f.store.put.bind(f.store);
  let posts = 0; let ready = 0; let changed = false;
  const change = () => { if (!changed) { changed = true; race?.mutate({ pr, reviews, duplicates, issue: f.issue }); } };
  f.api.userIdentity = async login => copy(login === WRITER ? writer : reviewer);
  f.api.get = async path => {
    if (path === '/pulls/43' || path === '/issues/43') return copy(pr);
    const decision = decisions.find(value => path === `/issues/comments/${value.id}`);
    return decision ? copy(decision) : get(path);
  };
  f.api.list = async path => {
    if (path === '/pulls/43/reviews') return copy(reviews);
    if (path.startsWith('/pulls?')) return copy([pr, ...duplicates]);
    const values = await list(path);
    return path === '/issues/42/comments' ? [...copy(decisions), ...values] : values;
  };
  f.api.patch = async (path, body) => {
    if (path === '/pulls/43') { Object.assign(pr, body); return copy(pr); }
    return patch(path, body);
  };
  f.api.post = async (path, body) => {
    if (path === '/issues/43/labels') {
      for (const name of body.labels) if (!pr.labels.some(label => label.name === name)) pr.labels.push({ name });
      return copy(pr.labels);
    }
    const value = await post(path, body);
    if (path === '/issues/43/comments') {
      posts++;
      value.user = copy(writer);
      f.comments.find(comment => comment.id === value.id).user = copy(writer);
      if (race?.when === 'after-outcome') change();
      if (race?.when === 'lost-response' && posts === 1)
        throw Object.assign(new Error('Lost manual Outcome POST response'), { code: 'POST_UNCERTAIN' });
    }
    return copy(value);
  };
  f.api.ready = async node => { assert.equal(node, pr.node_id); ready++; pr.draft = false; };
  f.api.draft = async node => { assert.equal(node, pr.node_id); pr.draft = true; };
  f.store.put = async (id, record) => {
    await put(id, record);
    if (race?.when === 'after-reservation' && record.lifecycleIntent && record.outcome) change();
  };
  const reviewed = copy(pr);
  if (route === 'cr') reviews.push({ id: 17, user: copy(reviewer), state: 'CHANGES_REQUESTED',
    commit_id: pr.head.sha, submitted_at: '2026-09-04T12:03:00Z',
    body: renderAuthorityRecord({ schema_version: '4.0', kind: 'change-request', repository: REPOSITORY,
      task: 42, parent: { kind: 'pull_request', number: pr.number }, charter_sha256: sha256Body(charter),
      purpose: 'Correct the exact reviewed source', branch: pr.head.ref, base_sha: pr.base.sha,
      reviewed_head_sha: pr.head.sha, change_request_id: 'CR-42-001', context: [],
      findings: [{ id: 'F1', severity: 'major', problem: 'The reviewed source needs correction.',
        impact: 'The requirement is incomplete.', remediation: 'Deliver the bounded correction.',
        acceptance_criteria: ['The exact corrected candidate passes independent review.'] }] }) });
  else decisions.push({ id: 901, user: copy(reviewer), created_at: '2026-09-04T12:03:00Z',
    issue_url: `https://api.github.com/repos/${REPOSITORY}/issues/42`,
    body: renderAuthorityRecord({ schema_version: '4.0', kind: 'decision', repository: REPOSITORY,
      task: 42, parent: { kind: 'issue', number: 42 }, charter_sha256: sha256Body(charter),
      purpose: 'Continue the existing implementation on its exact PR', context: [], supersedes: null,
      amendments: { branch: pr.head.ref, base_sha: pr.base.sha, starting_head: pr.head.sha,
        existing_pr: pr.number, scope: ['Complete the bounded implementation on the existing PR.'] } }) });
  const target = route === 'cr' ? 'pull_request' : 'issue';
  const number = target === 'pull_request' ? pr.number : 42;
  const subject = target === 'pull_request' ? pr : f.issue;
  subject.labels.push({ name: 'codex-ready-manual' });
  f.events.splice(0, f.events.length, { id: 74, event: 'labeled', actor: { login: CONSUMER.owner, type: 'User' },
    label: { name: 'codex-ready-manual' }, created_at: '2026-09-04T12:04:00Z' });
  const remove = f.api.delete.bind(f.api);
  f.api.delete = async path => {
    if (path.startsWith('/issues/43/labels/step-')) {
      pr.labels = pr.labels.filter(label => label.name !== decodeURIComponent(path.split('/').at(-1))); return;
    }
    if (path === `/issues/${number}/labels/codex-ready-manual`) {
      subject.labels = subject.labels.filter(label => label.name !== 'codex-ready-manual');
      f.events.push({ id: 75, event: 'unlabeled', actor: copy(writer), label: { name: 'codex-ready-manual' },
        created_at: '2026-09-04T12:04:01Z' }); return;
    }
    return remove(path);
  };
  f.api.getRun = async id => copy(id === 100 ? { ...f.run, id, event: target === 'pull_request' ? 'pull_request_target' : 'issues',
    created_at: '2026-09-04T12:04:01Z', display_title: labelRunName({ target, number, route: 'manual' }, subject) }
    : { ...f.run, status: 'completed', updated_at: '2026-09-04T12:02:00Z' });
  const broker = createPublicationBroker({ api: f.api, store: f.store, publisher: f.publisher, journal: f.journal,
    lifecycleStore: f.lifecycleStore, allowManualOutcome: true });
  const admitted = await broker.dispatch({ operation: 'admit', runId: 100, target, number, route: 'manual', transport: 'label' });
  assert.notEqual(admitted.status, 'BLOCKED');
  const e = admitted.envelope;
  assert.equal(e.step, 2); assert.equal(e.request.existing_pr, pr.number);
  assert.equal(pr.body, originalBody);
  assert.ok(!pr.body.includes(`Execution admission digest: ${admissionBinding(e.request).sha256}`));
  // Manual execution publishes source through its admitted owner channel.
  await f.command(f.source, ['fetch', f.remote, e.branch]);
  await f.command(f.source, ['switch', '-c', e.branch, e.startHead]);
  await writeFile(join(f.source, 'docs/work.md'), 'manual correction\n');
  await f.command(f.source, ['commit', '-am', 'manual correction']);
  await f.command(f.source, ['push', f.remote, e.branch]);
  pr.head.sha = await f.remoteHead(); pr.draft = true;
  const result = { schema_version: '4.0', kind: 'outcome', repository: REPOSITORY, task: 42,
    parent: { kind: 'pull_request', number: pr.number }, charter_sha256: sha256Body(charter), step: e.step,
    authority: copy(e.request.authority), admission: admissionBinding(e.request), attempt: e.attemptId,
    status: 'implemented', result: { kind: 'git', revision: pr.head.sha, identities: [] },
    summary: 'The admitted manual correction is complete at the exact candidate head.', warnings: [], limitations: [] };
  const invoke = () => broker.dispatch({ operation: 'manual-outcome-direct', runId: e.runId, attemptId: e.attemptId,
    submission: { repository: REPOSITORY, task: 42, run_id: e.runId, result } });
  return { ...f, pr, reviews, decisions, duplicates, result, invoke, envelope: e, originalBody, reviewed,
    posts: () => posts, ready: () => ready };
}

for (const route of ['cr', 'continuation']) {
  test(`real broker publishes a manual ${route} result on its immutable existing PR without replacing automatic provenance`, async t => {
    const f = await existingPr(t, route);
    const receipt = await f.invoke();
    assert.equal(receipt.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
    assert.equal(f.posts(), 1); assert.equal(f.ready(), 1); assert.equal(f.pr.draft, false);
    assert.equal(f.pr.body, f.originalBody);
    assert.deepEqual(extractAuthorityRecord(f.comments.at(-1).body), { ...f.result,
      authority_resolution: f.envelope.request.authority_resolution });
    assert.deepEqual(await f.invoke(), receipt);
    assert.equal(f.posts(), 1); assert.equal(f.ready(), 1);
  });
}

const invalid = [
  ['different result parent', f => {
    f.result.parent.number = 44;
    const get = f.api.get.bind(f.api);
    f.api.get = path => path === '/pulls/44' ? Promise.resolve({ ...copy(f.pr), number: 44,
      body: `Related to #42\nExecution admission digest: ${f.result.admission.sha256}` }) : get(path);
  }, ['PR_AUTHORITY_CHANGED']],
  ['different Task linkage', f => { f.pr.body = f.pr.body.replaceAll('#42', '#41').replaceAll('/issues/42', '/issues/41'); },
    ['CANONICAL_ISSUE_AMBIGUOUS', 'AUTHORITY_CHANGED', 'AUTHORITY_TARGET_MISMATCH', 'PR_AUTHORITY_CHANGED']],
  ['different branch', f => { f.pr.head.ref += '-other'; }, ['STARTING_STATE_MISMATCH', 'PR_AUTHORITY_CHANGED']],
  ['different base branch', f => { f.pr.base.ref = 'other'; }, ['PR_NOT_ADMITTED', 'PR_AUTHORITY_CHANGED']],
  ['foreign head repository', f => { f.pr.head.repo.full_name = 'foreign/repository'; }, ['PR_NOT_ADMITTED', 'PR_AUTHORITY_CHANGED']],
  ['foreign base repository', f => { f.pr.base.repo.full_name = 'foreign/repository'; }, ['PR_NOT_ADMITTED', 'PR_AUTHORITY_CHANGED']],
  ['different exact result head', f => { f.result.result.revision = f.envelope.startHead; }, ['PR_AUTHORITY_CHANGED']],
  ['different admission digest', f => { f.result.admission.sha256 = 'b'.repeat(64); }, ['MANUAL_OUTCOME_BINDING_INVALID']],
  ['different authority digest', f => { f.result.authority.sha256 = 'b'.repeat(64); },
    ['AUTHORITY_SOURCE_MISMATCH']],
  ['another open PR without the new admission marker', f => { f.duplicates.push({ ...copy(f.pr), number: 44 }); }, ['PR_AMBIGUOUS']],
  ['changed trusted CR source', f => { f.reviews[0].body += '\nChanged after admission.'; },
    ['AUTHORITY_SOURCE_MISMATCH', 'AUTHORITY_CHANGED']],
];

for (const [name, mutate, codes] of invalid) {
  test(`manual existing-PR binding rejects ${name} before publishing or marking Ready`, async t => {
    const f = await existingPr(t, 'cr');
    if (name === 'different Task linkage') {
      const get = f.api.get.bind(f.api);
      f.api.get = path => path === '/issues/41' ? Promise.resolve({ ...copy(f.issue), number: 41 }) : get(path);
    }
    mutate(f);
    await assert.rejects(f.invoke(), error => codes.includes(error.code), name);
    assert.equal(f.posts(), 0); assert.equal(f.ready(), 0); assert.equal(f.pr.draft, true);
    assert.equal((await f.store.get(f.envelope.runId)).manualSubmission, undefined);
  });
}

for (const when of ['after-outcome', 'after-reservation']) for (const [name, mutate, codes] of [
  ['changed exact PR head', ({ pr }) => { pr.head.sha = 'b'.repeat(40); }, ['PR_AUTHORITY_CHANGED', 'PR_HEAD_OBSERVATION_STALE']],
  ['changed branch', ({ pr }) => { pr.head.ref += '-other'; }, ['STARTING_STATE_MISMATCH', 'PR_AUTHORITY_CHANGED']],
  ['changed configured base', ({ pr }) => { pr.base.ref = 'other'; }, ['PR_NOT_ADMITTED', 'PR_AUTHORITY_CHANGED']],
  ['duplicate current PR', ({ pr, duplicates }) => { duplicates.push({ ...copy(pr), number: 44 }); }, ['PR_AMBIGUOUS']],
  ['changed CR source', ({ reviews }) => { reviews[0].body += '\nConcurrent source change.'; }, ['AUTHORITY_SOURCE_MISMATCH', 'AUTHORITY_CHANGED']],
]) {
  test(`manual existing-PR lifecycle rejects ${name} ${when} without a Ready mutation`, async t => {
    const f = await existingPr(t, 'cr', { when, mutate });
    await assert.rejects(f.invoke(), error => codes.includes(error.code), name);
    assert.equal(f.posts(), 1); assert.equal(f.ready(), 0); assert.equal(f.pr.draft, true);
    assert.equal((await f.store.get(f.envelope.runId)).outcome.outcomeId, f.comments.at(-1).id);
    await assert.rejects(f.invoke());
    assert.equal(f.posts(), 1); assert.equal(f.ready(), 0);
  });
}

test('lost manual existing-PR Outcome response recovers its exact original claim once', async t => {
  const f = await existingPr(t, 'cr', { when: 'lost-response' });
  await assert.rejects(f.invoke(), { code: 'POST_UNCERTAIN' });
  const original = f.comments.at(-1).body;
  const published = await f.invoke();
  assert.deepEqual(await f.invoke(), published);
  assert.equal(f.posts(), 1); assert.equal(f.ready(), 1);
  assert.equal(f.comments.at(-1).body, original); assert.equal(f.pr.body, f.originalBody);
});
