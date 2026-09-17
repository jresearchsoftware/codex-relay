import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { fixture, memoryStore } from './fixture.mjs';
import { runAttempt } from '../src/attempt.mjs';
import { executeCodex } from '../src/attempt-runtime.mjs';
import { admitEnvelope } from '../src/live-authority.mjs';
import { recoveryAuthorization, recoveryAuthorizationBody } from '../src/publication-recovery.mjs';

const reviewed = (t, options = {}) => fixture(t, { remediation: true, mainAdvance: true, step: 3, ...options });
const publish = async f => {
  const progress = await f.collect(f.envelope);
  return f.broker.invoke({ operation: 'publish-progress', runId: f.envelope.runId,
    attemptId: f.envelope.attemptId, bundle: progress.bundle });
};
async function reconcile(f) {
  await assert.rejects(f.command(f.cwd, ['merge', '--no-ff', '--no-commit', f.envelope.targetBase], f.identity), error => error.code === 1);
  await writeFile(join(f.cwd, 'docs/work.md'), 'reviewed task behavior\nadvanced main behavior\n');
  await f.command(f.cwd, ['add', 'docs/work.md']);
  await f.command(f.cwd, ['commit', '-m', 'reconcile reviewed task with admitted main'], f.identity);
  return f.command(f.cwd, ['rev-parse', 'HEAD']);
}
async function advanceAgain(f) {
  await writeFile(join(f.source, 'later.md'), 'later main\n');
  await f.command(f.source, ['add', '.']); await f.command(f.source, ['commit', '-m', 'main moves again']);
  await f.command(f.source, ['push', f.remote, 'main']);
}

test('owner dispatch reaches one bounded Codex child from a truly dirty reviewed PR and publishes both behaviors', async t => {
  const f = await reviewed(t, { nativeReview: true }); const journal = memoryStore(); let children = 0; let merge;
  assert.equal(f.envelope.attemptId, 'run-99'); assert.equal(f.envelope.step, 3);
  assert.equal((await f.api.get('/pulls/43')).mergeable, false);
  const args = { ...f, journal, execute: async e => {
    const result = await executeCodex(e, { runTask: async request => {
      children++;
      assert.equal(await f.command(f.cwd, ['rev-parse', 'HEAD']), e.startHead);
      assert.equal(await f.command(f.cwd, ['rev-parse', 'refs/remotes/main']), e.targetBase);
      assert.match(request.inputText, /at most one local two-parent merge commit/);
      merge = await reconcile(f);
      await f.commit('unanticipated-required-file.md', 'complete remediation\n');
      return { status: 'success', summary: 'Both reviewed task and advanced main retained.', validation: ['local conflict resolution checked'] };
    } });
    return { ...result, containment: 'reaped' };
  } };
  const result = await runAttempt(args);
  assert.equal(result.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
  assert.equal(await f.command(f.cwd, ['show', '-s', '--format=%P', merge]), `${f.envelope.startHead} ${f.envelope.targetBase}`);
  assert.equal(await f.command(f.cwd, ['merge-base', result.head, f.envelope.targetBase]), f.envelope.targetBase);
  assert.equal(await readFile(join(f.cwd, 'main-feature.md'), 'utf8'), 'preserve main feature\n');
  assert.equal(await readFile(join(f.cwd, 'docs/work.md'), 'utf8'), 'reviewed task behavior\nadvanced main behavior\n');
  assert.equal(await f.remoteHead(), result.head);
  assert.equal(await f.command(f.root, ['--git-dir=' + f.remote, 'rev-parse', 'main']), f.envelope.targetBase);
  await runAttempt(args);
  assert.equal(children, 1); assert.equal(f.pushes(), 1);
  assert.equal(f.comments.filter(c => c.body.startsWith('## Codex Outcome')).length, 1);
});

test('dirty PR admission still binds owner transport and exact reviewed head', async t => {
  const f = await reviewed(t);
  for (const delta of [{ actor: { login: 'other' } }, { event: 'pull_request' },
    { head_branch: 'codex/other' }, { display_title: 'Auto remediation · Task 42 · Step 4 · PR #43' }]) {
    await assert.rejects(admitEnvelope({ ...f.api, getRun: async () => ({ ...f.run, ...delta }) }, f.admissionRequest),
      { code: 'OWNER_RUN_NOT_ADMITTED' });
  }
  const get = f.api.get.bind(f.api);
  const changedHead = { ...f.api, get: async path => {
    const value = await get(path);
    return path === '/pulls/43' ? { ...value, head: { ...value.head, sha: f.envelope.targetBase } } : value;
  } };
  assert.equal((await admitEnvelope(changedHead, f.admissionRequest)).block.code, 'STARTING_STATE_MISMATCH');
});

for (const change of ['goal', 'branch', 'repository', 'base-branch', 'linked-issue', 'head', 'review', 'main', 'unrelated-main']) {
  test(`dirty remediation blocks ${change} before any child or push`, async t => {
    const f = await reviewed(t, { unrelatedMain: change === 'unrelated-main' });
    let children = 0;
    if (change === 'goal') f.issue.body += '\nChanged authority.';
    if (change === 'branch') f.pr.head.ref = 'codex/other';
    if (change === 'repository') f.pr.head.repo.full_name = 'unrelated/repository';
    if (change === 'base-branch') f.pr.base.ref = 'other';
    if (change === 'linked-issue') f.pr.body = 'Closes #42\nRelated to #44';
    if (change === 'review') f.review.state = 'APPROVED';
    if (change === 'head') {
      const get = f.api.get.bind(f.api);
      f.api.get = async path => {
        const value = await get(path);
        return path === '/pulls/43' ? { ...value, head: { ...value.head, sha: f.envelope.targetBase } } : value;
      };
    }
    if (change === 'main') await advanceAgain(f);
    // Some changed PR identities also prevent publishing a terminal comment.
    // In every case, the security property is zero child and publication calls.
    await runAttempt({ ...f, journal: memoryStore(), execute: () => { children++; assert.fail('protected mismatch reached child'); } }).catch(error => {
      assert.ok(error.code);
    });
    assert.equal(children, 0); assert.equal(f.pushes(), 0);
  });
}

test('fresh implementation still rejects a stale explicitly admitted base', async t => {
  const f = await fixture(t, { mainAdvance: true });
  assert.equal(f.envelope.admissionBlock.code, 'STARTING_STATE_MISMATCH');
  assert.equal(f.pushes(), 0);
});

test('main movement between preflight and checkout cannot enter the child', async t => {
  const f = await reviewed(t);
  await f.broker.invoke({ operation: 'preflight', runId: 99, attemptId: f.envelope.attemptId });
  await advanceAgain(f);
  await assert.rejects(f.prepare(f.envelope), { code: 'STARTING_STATE_MISMATCH' });
});

test('main movement after reconciliation blocks publication of the stale integration', async t => {
  const f = await reviewed(t); await f.prepare(f.envelope); await reconcile(f); await advanceAgain(f);
  await assert.rejects(publish(f), { code: 'STARTING_STATE_MISMATCH' }); assert.equal(f.pushes(), 0);
});

for (const kind of ['wrong-parent', 'reversed-parents', 'octopus', 'second-merge', 'identity', 'path', 'mode', 'secret']) {
  test(`reconciliation publication rejects ${kind} without weakening Writer validation`, async t => {
    const f = await reviewed(t); await f.prepare(f.envelope);
    let previous = f.envelope.startHead;
    if (kind === 'second-merge') previous = await reconcile(f);
    if (kind === 'path') await writeFile(join(f.cwd, 'malformed:name.md'), 'unsafe path\n');
    if (kind === 'secret') await writeFile(join(f.cwd, 'docs/work.md'), `ghp_${'A'.repeat(30)}\n`);
    await f.command(f.cwd, ['add', '.']);
    if (kind === 'mode') {
      const blob = await f.command(f.cwd, ['hash-object', '-w', 'docs/work.md']);
      await f.command(f.cwd, ['update-index', '--add', '--cacheinfo', `120000,${blob},unsafe-link`]);
    }
    const tree = await f.command(f.cwd, ['write-tree']);
    let parents = [previous, f.envelope.targetBase];
    if (kind === 'wrong-parent') parents[1] = f.envelope.historicalBase;
    if (kind === 'reversed-parents') parents.reverse();
    if (kind === 'octopus') parents.push(f.envelope.historicalBase);
    const merge = await f.command(f.cwd, ['commit-tree', tree, ...parents.flatMap(p => ['-p', p]), '-m', 'candidate resolution'], kind === 'identity' ? {} : f.identity);
    await f.command(f.cwd, ['update-ref', `refs/heads/${f.envelope.branch}`, merge]);
    if (kind === 'secret') await f.commit('docs/work.md', 'removed later\n');
    const code = { path: 'COMMIT_PATH_INVALID', mode: 'COMMIT_FILE_MODE_INVALID', secret: 'SECRET_PUBLICATION_SCAN_FAILED' }[kind] ?? 'COMMIT_OWNERSHIP_INVALID';
    await assert.rejects(publish(f), { code }); assert.equal(f.pushes(), 0);
  });
}

test('a reconciled candidate retains one-shot owner-authorized Writer publication recovery', async t => {
  const f = await reviewed(t); await f.prepare(f.envelope); await reconcile(f);
  f.failPush(true); await assert.rejects(publish(f), { code: 'PUBLICATION_UNCERTAIN' });
  f.failPush(false); f.run.status = 'completed'; f.run.updated_at = '2026-09-04T12:01:00Z';
  const record = await f.store.get(99); const progress = await f.collect(f.envelope);
  const created = new Date().toISOString();
  f.comments.push({ id: 10000, user: { login: 'example-owner', type: 'User' },
    issue_url: 'https://api.github.com/repos/example-org/sample-project/issues/43',
    created_at: created, updated_at: created,
    body: recoveryAuthorizationBody(recoveryAuthorization(f.envelope, record.publicationIntent)) });
  const request = { operation: 'recover-publication', runId: 99, attemptId: f.envelope.attemptId,
    authorizationId: 10000, bundle: progress.bundle };
  assert.equal((await f.broker.invoke(request)).publishedHead, progress.head);
  await f.broker.invoke(request); assert.equal(f.pushes(), 2);
});
