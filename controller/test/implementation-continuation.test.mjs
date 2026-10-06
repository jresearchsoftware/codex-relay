import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { fixture, memoryStore } from './fixture.mjs';
import { runAttempt } from '../src/attempt.mjs';
import { executeCodex } from '../src/attempt-runtime.mjs';
import { VERSION } from '../src/execution-contract.mjs';
import { CONSUMER } from '../../consumer/consumer.mjs';

const preflight = f => ({ operation: 'preflight', runId: 99, attemptId: f.envelope.attemptId });
const publication = (f, progress) => ({ operation: 'publish-progress', runId: 99,
  attemptId: f.envelope.attemptId, bundle: progress.bundle });
async function candidate(f) {
  await f.prepare(f.envelope); await f.commit(); return f.collect(f.envelope);
}

test('the normal Issue label path continues the exact implementation head and reuses its PR without a CR', async t => {
  const f = await fixture(t, { continuation: true, labelLaunch: true, step: 3 });
  assert.equal(f.envelope.target, 'issue');
  assert.equal(f.envelope.reviewId, null);
  assert.notEqual(f.envelope.startHead, f.envelope.targetBase);
  assert.equal(f.envelope.continuation.pullRequest, 43);
  assert.equal((await f.store.get(99)).prNumber, 43);
  const post = f.api.post.bind(f.api); const list = f.api.list.bind(f.api);
  f.api.post = (path, body) => { assert.notEqual(path, '/pulls'); return post(path, body); };
  f.api.list = path => { assert.ok(!path.endsWith('/reviews')); return list(path); };
  let executions = 0;
  const args = { ...f, journal: f.journal, execute: async () => {
    executions++;
    assert.equal(await f.command(f.cwd, ['rev-parse', 'HEAD']), f.envelope.startHead);
    assert.equal(await readFile(join(f.cwd, 'docs/prior.md'), 'utf8'), 'previous implementation progress\n');
    await f.commit();
    return { version: VERSION, attemptId: f.envelope.attemptId, child: 'started', containment: 'reaped', result: { status: 'success' } };
  } };
  const result = await runAttempt(args);
  assert.equal(result.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
  assert.equal(result.prNumber, 43);
  assert.equal(f.pushes(), 1);
  assert.equal(executions, 1);
  assert.equal((await f.api.get('/pulls/43')).draft, false);
  assert.equal(f.comments.length, 1);
  assert.match(f.comments[0].body, /Status: IMPLEMENTED_PENDING_FRESH_REVIEW/);
  assert.equal((await f.store.get(99)).publishedHead, await f.remoteHead());
  assert.deepEqual(await runAttempt(args), result);
  assert.equal(executions, 1);
  assert.equal(f.pushes(), 1);
});

test('continuation launches implementation with the Writer identity and no remediation integration exception', async t => {
  const f = await fixture(t, { continuation: true });
  await executeCodex(f.envelope, { runTask: async request => {
    assert.equal(request.operation, 'issue-implementation');
    assert.deepEqual(request.gitIdentity, CONSUMER.writerIdentity);
    assert.ok(!request.inputText.includes('Bounded base-branch reconciliation'));
    assert.ok(!request.inputText.includes('Native Change Request #'));
    return { status: 'success' };
  } });
});

test('an explicitly admitted existing branch without a PR can publish its first implementation PR', async t => {
  const f = await fixture(t, { continuation: true, continuationPr: false });
  assert.equal(f.envelope.continuation.pullRequest, null);
  await f.broker.invoke(preflight(f));
  const progress = await candidate(f);
  assert.equal((await f.broker.invoke(publication(f, progress))).prNumber, 43);
  assert.equal(f.pushes(), 1);
  assert.equal(await f.remoteHead(), progress.head);
  assert.equal((await f.store.get(99)).prNumber, 43);
});

for (const [name, mutate, code] of [
  ['different admitted SHA', f => { f.issue.body = f.issue.body.replace(f.continuationHead, 'b'.repeat(40)); }, 'STARTING_STATE_MISMATCH'],
  ['missing branch', async f => { await f.command(f.root, ['--git-dir=' + f.remote, 'update-ref', '-d', `refs/heads/${CONSUMER.taskBranchPrefix}test-42`]); }, 'TASK_BRANCH_MISSING'],
  ['missing declared PR', f => { const list = f.api.list.bind(f.api); f.api.list = path => path.startsWith('/pulls?') ? Promise.resolve([]) : list(path); }, 'PR_AUTHORITY_CHANGED'],
  ['wrong PR number', f => { f.issue.body = f.issue.body.replace('pull request: #43', 'pull request: #44'); }, 'PR_AUTHORITY_CHANGED'],
  ['unadmitted existing PR', f => { f.issue.body = f.issue.body.replace('\nImplementation pull request: #43', ''); }, 'PR_AUTHORITY_CHANGED'],
  ['wrong Task linkage', f => { f.pr.body = 'Related to #44'; }, 'PR_AUTHORITY_CHANGED'],
  ['ambiguous Task linkage', f => { f.pr.body = 'Related to #42\nRelated to #44'; }, 'CANONICAL_ISSUE_AMBIGUOUS'],
  ['wrong branch', f => { f.pr.head.ref = 'codex/foreign'; }, 'PR_AUTHORITY_CHANGED'],
  ['wrong base', f => { f.pr.base.ref = 'another-base'; }, 'PR_NOT_ADMITTED'],
  ['wrong head repository', f => { f.pr.head.repo.full_name = 'other/repo'; }, 'PR_NOT_ADMITTED'],
  ['wrong base repository', f => { f.pr.base.repo.full_name = 'other/repo'; }, 'PR_NOT_ADMITTED'],
  ['missing Step', f => { f.pr.labels = []; }, 'STEP_LABEL_MISSING'],
  ['multiple Steps', f => { f.pr.labels.push({ name: 'step-2' }); }, 'STEP_LABEL_MULTIPLE'],
  ['different Step', f => { f.pr.labels = [{ name: 'step-2' }]; }, 'STEP_LABEL_MISMATCH'],
  ['stale PR Step title', f => { f.pr.title = 'Task 42 · Step 2 · stale'; }, 'STEP_DISPLAY_MISMATCH'],
  ['closed PR', f => { f.pr.state = 'closed'; }, 'PR_NOT_ADMITTED'],
  ['merged PR', f => { f.pr.merged = true; }, 'PR_NOT_ADMITTED'],
  ['multiple PR candidates including wrong base', f => {
    const list = f.api.list.bind(f.api);
    f.api.list = async path => {
      const rows = await list(path);
      return path.startsWith('/pulls?') ? [...rows, { ...rows[0], number: 44, base: { ...rows[0].base, ref: 'other-base' } }] : rows;
    };
  }, 'PR_AMBIGUOUS'],
  ['stale PR head', f => {
    const list = f.api.list.bind(f.api);
    f.api.list = async path => (await list(path)).map(pr => path.startsWith('/pulls?') ? { ...pr, head: { ...pr.head, sha: 'b'.repeat(40) } } : pr);
  }, 'STARTING_STATE_MISMATCH']
]) {
  test(`continuation admission blocks ${name} before worker access`, async t => {
    const f = await fixture(t, { continuation: true, continuationPr: name !== 'missing branch', beforeAdmission: mutate });
    assert.equal(f.admission.status, 'BLOCKED');
    assert.equal(f.envelope.admissionBlock.code, code);
    assert.equal(f.pushes(), 0);
    assert.equal(f.comments.length, 1);
    assert.equal(f.comments[0].body.includes('BLOCKED_BEFORE_WORKER'), true);
  });
}

test('an existing branch without continuation authority still follows the fresh-task rejection', async t => {
  const f = await fixture(t, { continuation: true, beforeAdmission: ({ issue }) => {
    issue.body = issue.body.replace(/\nImplementation continuation head: [a-f0-9]+\nImplementation pull request: #43/, '');
  } });
  assert.equal(f.envelope.admissionBlock.code, 'TASK_BRANCH_ALREADY_EXISTS');
});

test('continuation remains available through the manual Issue handoff route', async t => {
  const f = await fixture(t, { continuation: true, route: 'manual' });
  const result = await runAttempt({ ...f, journal: f.journal, execute: () => assert.fail('manual route must not launch') });
  assert.equal(result.status, 'handed-off');
  assert.equal(f.pushes(), 0);
  assert.match(f.comments[0].body, /MANUAL_CODEX_HANDOFF_READY/);
  assert.ok(f.comments[0].body.includes(`/issues/${f.envelope.issueNumber}`));
});

test('branch movement after admission blocks preflight and trusted checkout before worker access', async t => {
  const f = await fixture(t, { continuation: true, continuationPr: false });
  await f.command(f.source, ['switch', f.envelope.branch]);
  await writeFile(join(f.source, 'concurrent.md'), 'external work\n');
  await f.command(f.source, ['add', 'concurrent.md']);
  await f.command(f.source, ['commit', '-m', 'external progress']);
  await f.command(f.source, ['push', f.remote, f.envelope.branch]);
  await assert.rejects(f.broker.invoke(preflight(f)), { code: 'REMOTE_HEAD_CHANGED' });
  await assert.rejects(f.prepare(f.envelope), { code: 'STARTING_STATE_MISMATCH' });
  assert.equal(f.pushes(), 0);
});

test('an advanced base does not grant continuation the remediation integration gate', async t => {
  const f = await fixture(t, { continuation: true, mainAdvance: true, beforeAdmission: ({ issue }) => {
    issue.body = issue.body.replace(/- Required starting base: `[^`]+`\n/, '');
  } });
  await f.broker.invoke(preflight(f));
  const progress = await candidate(f);
  assert.equal((await f.broker.invoke(publication(f, progress))).publishedHead, progress.head);
  assert.equal(f.pushes(), 1);
});

for (const changed of ['closed', 'replaced', 'step', 'authority']) {
  test(`continuation cannot publish after its admitted PR/authority is ${changed}`, async t => {
    const f = await fixture(t, { continuation: true });
    const progress = await candidate(f);
    if (changed === 'closed') f.pr.state = 'closed';
    if (changed === 'replaced') f.pr.number = 44;
    if (changed === 'step') f.pr.labels = [{ name: 'step-2' }];
    if (changed === 'authority') f.issue.body += '\nNew owner decision.';
    await assert.rejects(f.broker.invoke(publication(f, progress)), {
      code: changed === 'closed' ? 'PR_NOT_ADMITTED' : changed === 'step' ? 'STEP_LABEL_MISMATCH'
        : changed === 'authority' ? 'AUTHORITY_CHANGED' : 'PR_AUTHORITY_CHANGED'
    });
    assert.equal(f.pushes(), 0);
    assert.equal((await f.store.get(99)).publicationIntent, null);
  });
}

for (const changed of ['Step', 'title']) {
  test(`a ${changed} mismatch observed in the last continuation PR lookup blocks before push`, async t => {
    const f = await fixture(t, { continuation: true });
    const progress = await candidate(f);
    const list = f.api.list.bind(f.api); let lookups = 0;
    f.api.list = async path => {
      const rows = await list(path);
      if (!path.startsWith('/pulls?') || ++lookups < 3) return rows;
      return rows.map(pr => changed === 'Step' ? { ...pr, labels: [{ name: 'step-99' }] }
        : { ...pr, title: 'Task 42 · Step 99 · unexpected' });
    };
    await assert.rejects(f.broker.invoke(publication(f, progress)), {
      code: changed === 'Step' ? 'STEP_LABEL_MISMATCH' : 'STEP_DISPLAY_MISMATCH'
    });
    assert.equal(f.pushes(), 0);
    assert.equal((await f.store.get(99)).publicationIntent, null);
  });
}

test('a PR first created by branch-only continuation must retain its Step before subsequent progress', async t => {
  const f = await fixture(t, { continuation: true, continuationPr: false });
  const first = await candidate(f);
  await f.broker.invoke(publication(f, first));
  await f.commit('docs/work.md', 'next progress\n');
  const next = await f.collect(f.envelope);
  const list = f.api.list.bind(f.api);
  f.api.list = async path => (await list(path)).map(pr => path.startsWith('/pulls?')
    ? { ...pr, labels: [{ name: 'step-99' }] } : pr);
  await assert.rejects(f.broker.invoke(publication(f, next)), { code: 'STEP_LABEL_MISMATCH' });
  assert.equal(f.pushes(), 1);
  assert.equal(await f.remoteHead(), first.head);
});

test('remote movement to a candidate ancestor during authority revalidation blocks rather than being overwritten', async t => {
  const f = await fixture(t, { continuation: true, continuationPr: false });
  await f.prepare(f.envelope);
  const intermediate = await f.commit();
  await f.commit('docs/work.md', 'second task commit\n');
  const progress = await f.collect(f.envelope);
  await f.command(f.cwd, ['push', f.remote, `${intermediate}:refs/heads/race-fixture`]);
  let moved = false;
  // bound() revalidates before inspect; move during the later current-target
  // lookup so inspect's original exact-head observation has already succeeded.
  const list = f.api.list.bind(f.api);
  f.api.list = async path => {
    if (path.startsWith('/pulls?') && !moved) {
      moved = true;
      await f.command(f.root, ['--git-dir=' + f.remote, 'update-ref', `refs/heads/${f.envelope.branch}`, intermediate]);
    }
    return list(path);
  };
  await assert.rejects(f.broker.invoke(publication(f, progress)), { code: 'REMOTE_HEAD_CHANGED' });
  assert.equal(await f.remoteHead(), intermediate);
  assert.equal(f.pushes(), 0);
  assert.equal((await f.store.get(99)).publicationIntent, null);
});

test('ordinary non-force continuation push preserves a divergent external head that moves after the final observation', async t => {
  const f = await fixture(t, { continuation: true });
  const progress = await candidate(f);
  const inspect = f.publisher.inspect.bind(f.publisher); let external;
  f.publisher.inspect = (e, bundle, fn) => inspect(e, bundle, g => fn({ ...g, push: async () => {
    await f.command(f.source, ['switch', e.branch]);
    await writeFile(join(f.source, 'external.md'), 'concurrent external work\n');
    await f.command(f.source, ['add', 'external.md']);
    await f.command(f.source, ['commit', '-m', 'external progress']);
    external = await f.command(f.source, ['rev-parse', 'HEAD']);
    await f.command(f.source, ['push', f.remote, e.branch]);
    return g.push();
  } }));
  await assert.rejects(f.broker.invoke(publication(f, progress)), { code: 'PUBLICATION_UNCERTAIN' });
  assert.equal(await f.remoteHead(), external);
  assert.notEqual(external, progress.head);
  assert.equal(f.pushes(), 1);
  assert.deepEqual((await f.store.get(99)).publicationIntent, { previous: f.envelope.startHead, head: progress.head });
  await assert.rejects(f.broker.invoke(publication(f, progress)), { code: 'PUBLICATION_UNCERTAIN' });
  assert.equal(f.pushes(), 1);
});

test('continuation rejects transient introduced secrets before pushing', async t => {
  const f = await fixture(t, { continuation: true });
  await f.prepare(f.envelope);
  await f.commit('secret.txt', 'ghp_' + 'A'.repeat(32));
  await f.command(f.cwd, ['rm', 'secret.txt']);
  await f.command(f.cwd, ['commit', '-m', 'remove transient file'], f.identity);
  const progress = await f.collect(f.envelope);
  await assert.rejects(f.broker.invoke(publication(f, progress)), { code: 'SECRET_PUBLICATION_SCAN_FAILED' });
  assert.equal(f.pushes(), 0);
});

test('implementation continuation cannot use the remediation-only merge permission', async t => {
  const f = await fixture(t, { continuation: true });
  await f.prepare(f.envelope);
  const tree = await f.command(f.cwd, ['rev-parse', 'HEAD^{tree}']);
  const merge = await f.command(f.cwd, ['commit-tree', tree, '-p', f.envelope.startHead,
    '-p', f.envelope.targetBase, '-m', 'unauthorized integration'], f.identity);
  await f.command(f.cwd, ['update-ref', `refs/heads/${f.envelope.branch}`, merge]);
  const progress = await f.collect(f.envelope);
  await assert.rejects(f.broker.invoke(publication(f, progress)), { code: 'COMMIT_OWNERSHIP_INVALID' });
  assert.equal(f.pushes(), 0);
});
