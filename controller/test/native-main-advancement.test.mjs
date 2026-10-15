import test from 'node:test';
import assert from 'node:assert/strict';
import { writeFile, readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { fixture } from './fixture.mjs';
import { runAttempt } from '../src/attempt.mjs';
import { verifyPublishedBase } from '../src/live-authority.mjs';
import { canonicalAuthorityJson, sha256Body } from '../../contracts/src/github-authority.mjs';
import { REPOSITORY, REVIEWER } from '../src/execution-contract.mjs';

const charter = 'Authority model: github-native-v1\n\nIssue closure policy: keep-open\n\nImplement independent source work.';
const native = (t, options = {}) => fixture(t, { issueBody: charter, labelLaunch: true, streamlinedAdmission: true, ...options });
async function advance(f) {
  await writeFile(join(f.source, `later-${Date.now()}.md`), 'independent main progress\n');
  await f.command(f.source, ['add', '.']); await f.command(f.source, ['commit', '-m', 'independent main advancement']);
  await f.command(f.source, ['push', f.remote, 'main']);
  return f.command(f.source, ['rev-parse', 'HEAD']);
}

test('native admission retains an explicitly authorized accepted ancestor when main moved before reserve', async t => {
  let original;
  const f = await native(t, { mainAdvance: true, beforeAdmission: async context => {
    original = await context.command(context.root, ['--git-dir=' + context.remote, 'rev-parse', 'main^']);
    const value = { schema_version: '4.0', kind: 'decision', repository: REPOSITORY, task: 42,
      parent: { kind: 'issue', number: 42 }, charter_sha256: sha256Body(charter),
      purpose: 'Keep the original accepted commit for independent implementation', supersedes: null, context: [],
      amendments: { base_sha: original, starting_head: original } };
    const comment = { id: 901, user: { login: REVIEWER, id: 701, type: 'Bot' },
      issue_url: `https://api.github.com/repos/${REPOSITORY}/issues/42`, body: '```relay-authority\n' + canonicalAuthorityJson(value) + '\n```\n' };
    const list = context.api.list.bind(context.api);
    context.api.list = path => path === '/issues/42/comments' ? [comment] : list(path);
  } });
  assert.notEqual(f.envelope.targetBase, original);
  assert.equal(f.envelope.startHead, original);
  await f.prepare(f.envelope);
  assert.equal(await f.command(f.cwd, ['rev-parse', 'HEAD']), original);
  assert.equal(await readFile(join(f.cwd, 'docs/work.md'), 'utf8'), 'baseline\n');
});

for (const boundary of ['before-preflight', 'before-checkout', 'before-publication']) {
  test(`native Issue tolerates independent main advancement ${boundary} and publishes the original task chain`, async t => {
    const f = await native(t); const original = f.envelope.startHead;
    if (boundary === 'before-preflight') await advance(f);
    const result = await runAttempt({ ...f,
      prepare: async e => { if (boundary === 'before-checkout') await advance(f); return f.prepare(e); },
      execute: async e => {
        assert.equal(await f.command(f.cwd, ['rev-parse', 'HEAD']), original);
        await f.commit('task.md', 'independent task progress\n');
        if (boundary === 'before-publication') await advance(f);
        return { version: 2, attemptId: e.attemptId, child: 'started', containment: 'reaped', result: { status: 'success', summary: 'Independent task retained.', validation: [] } };
      }
    });
    assert.equal(result.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
    assert.equal(await f.command(f.root, ['--git-dir=' + f.remote, 'show', '-s', '--format=%P', result.head]), original);
    assert.equal(f.pushes(), 1);
  });
}

test('native base proof rejects diverged, foreign or malformed commit observations', async () => {
  const base = 'a'.repeat(40); const current = 'b'.repeat(40);
  for (const value of [
    { status: 'diverged', base_commit: { sha: base }, merge_base_commit: { sha: base } },
    { status: 'ahead', base_commit: { sha: current }, merge_base_commit: { sha: base } },
    { status: 'ahead', base_commit: { sha: base }, merge_base_commit: { sha: current } }, {}
  ]) await assert.rejects(verifyPublishedBase({ get: async () => value }, base, current), { code: 'STARTING_STATE_MISMATCH' });
});

test('native Issue main rewrite blocks before inference', async t => {
  const f = await native(t);
  await f.command(f.source, ['switch', '--orphan', 'replacement']);
  await writeFile(join(f.source, 'replacement.md'), 'unrelated root\n');
  await f.command(f.source, ['add', '.']); await f.command(f.source, ['commit', '-m', 'replacement unrelated root']);
  const replacement = await f.command(f.source, ['rev-parse', 'HEAD']);
  await f.command(f.source, ['push', f.remote, 'replacement']);
  await f.command(f.root, ['--git-dir=' + f.remote, 'update-ref', 'refs/heads/main', replacement]);
  const result = await runAttempt({ ...f, execute: () => assert.fail('rewritten main inferred') });
  assert.equal(result.status, 'BLOCKED'); assert.equal(f.pushes(), 0);
});

test('native publication rejects external advancement of the task branch even while main advancement is allowed', async t => {
  const f = await native(t); await f.prepare(f.envelope); await f.commit('task.md', 'first worker progress\n');
  const publish = async () => {
    const progress = await f.collect(f.envelope);
    return f.broker.invoke({ operation: 'publish-progress', runId: 99, attemptId: f.envelope.attemptId, bundle: progress.bundle });
  };
  await publish();
  await f.command(f.source, ['fetch', f.remote, `refs/heads/${f.envelope.branch}`]);
  await f.command(f.source, ['switch', '-c', f.envelope.branch, 'FETCH_HEAD']);
  await writeFile(join(f.source, 'external.md'), 'external task branch progress\n');
  await f.command(f.source, ['add', '.']); await f.command(f.source, ['commit', '-m', 'external task writer']);
  await f.command(f.source, ['push', f.remote, f.envelope.branch]);
  const remote = await f.remoteHead();
  await f.commit('task.md', 'second worker progress\n');
  await assert.rejects(publish(), { code: 'REMOTE_HEAD_CHANGED' });
  assert.equal(await f.remoteHead(), remote); assert.equal(f.pushes(), 1);
});

test('native completed publication retains its exact candidate when later main movement changes mergeability', async t => {
  const f = await native(t); let executions = 0;
  const result = await runAttempt({ ...f, execute: async e => {
    executions++; await f.commit('task.md', 'independent task result\n');
    return { version: 2, attemptId: e.attemptId, child: 'started', containment: 'reaped',
      result: { status: 'success', summary: 'Independent candidate published.', validation: [] } };
  } });
  const laterBase = await advance(f);
  const get = f.api.get.bind(f.api);
  f.api.get = async path => {
    const value = await get(path);
    return path === '/pulls/43' ? { ...value, mergeable: false, base: { ...value.base, sha: laterBase } } : value;
  };
  const observed = await f.broker.invoke({ operation: 'observe-readiness', runId: f.envelope.runId,
    attemptId: f.envelope.attemptId, head: result.head });
  assert.equal(observed.readiness.status, 'BLOCKED');
  assert.equal(observed.readiness.observedBase, laterBase);
  assert.equal(observed.head, result.head); assert.equal(observed.outcomeId, result.outcomeId);
  assert.equal(await f.remoteHead(), result.head);
  assert.equal((await f.store.get(f.envelope.runId)).envelope.startHead, f.envelope.startHead);
  assert.equal(executions, 1); assert.equal(f.pushes(), 1); assert.equal(f.comments.length, 1);
});
