import test from 'node:test';
import assert from 'node:assert/strict';
import { chmod, writeFile, readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { fixture } from './fixture.mjs';
import { runAttempt } from '../src/attempt.mjs';
import { main as routeAttempt } from '../src/entrypoint.mjs';
import { verifyPublishedBase } from '../src/live-authority.mjs';
import { canonicalAuthorityJson, sha256Body } from '../../contracts/src/github-authority.mjs';
import { REPOSITORY, REVIEWER, VERSION } from '../src/execution-contract.mjs';
import { CONSUMER } from '../../consumer/consumer.mjs';

const charter = 'Authority model: github-native-v1\n\nIssue closure policy: keep-open\n\nImplement independent source work.';
const native = (t, options = {}) => fixture(t, { issueBody: charter, labelLaunch: true, streamlinedAdmission: true, ...options });
const taskRef = `refs/heads/${CONSUMER.taskBranchPrefix}task-42`;
const precreate = ({ command, source, remote }) => command(source, ['push', remote, `HEAD:${taskRef}`]);
const push = (f, progress) => f.broker.invoke({ operation: 'publish-progress', runId: f.envelope.runId,
  attemptId: f.envelope.attemptId, bundle: progress.bundle });

async function advance(f) {
  await writeFile(join(f.source, `later-${Date.now()}.md`), 'independent main progress\n');
  await f.command(f.source, ['add', '.']); await f.command(f.source, ['commit', '-m', 'independent main advancement']);
  await f.command(f.source, ['push', f.remote, 'main']);
  return f.command(f.source, ['rev-parse', 'HEAD']);
}

async function replaceMain(f) {
  await f.command(f.source, ['switch', '--orphan', 'replacement']);
  await writeFile(join(f.source, 'replacement.md'), 'unrelated root\n');
  await f.command(f.source, ['add', '.']); await f.command(f.source, ['commit', '-m', 'replacement unrelated root']);
  const replacement = await f.command(f.source, ['rev-parse', 'HEAD']);
  await f.command(f.source, ['push', f.remote, 'replacement']);
  await f.command(f.root, ['--git-dir=' + f.remote, 'update-ref', 'refs/heads/main', replacement]);
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
  await replaceMain(f);
  const result = await runAttempt({ ...f, execute: () => assert.fail('rewritten main inferred') });
  assert.equal(result.status, 'BLOCKED'); assert.equal(f.pushes(), 0);
});

test('Git checkout and publication distinguish exact refs from slash-delimited suffix matches', async t => {
  const f = await native(t, { beforeAdmission: async ({ command, source, remote }) => {
    await command(source, ['push', remote, `HEAD:refs/heads/elsewhere/${taskRef}`,
      'HEAD:refs/heads/elsewhere/refs/heads/main']);
  } });
  assert.equal(f.envelope.continuation, undefined);
  const result = await runAttempt({ ...f, execute: async e => {
    assert.equal(await f.command(f.cwd, ['rev-parse', 'HEAD']), e.startHead);
    await f.commit();
    return { version: VERSION, attemptId: e.attemptId, child: 'started', containment: 'reaped', result: { status: 'success' } };
  } });
  assert.equal(result.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
  assert.equal(f.pushes(), 1);
  assert.equal(await f.command(f.root, ['--git-dir=' + f.remote, 'rev-parse', taskRef]), result.head);
  assert.equal(await f.command(f.root, ['--git-dir=' + f.remote, 'rev-parse', `refs/heads/elsewhere/${taskRef}`]), f.envelope.startHead);
});

test('a Git server refusal on a precreated Issue branch keeps the original cause and stops retries', async t => {
  const f = await native(t, { beforeAdmission: precreate });
  const hook = join(f.remote, 'hooks/pre-receive');
  await writeFile(hook, "#!/bin/sh\nprintf '%s\\n' 'permission denied by repository policy' >&2\nexit 1\n");
  await chmod(hook, 0o755);
  let executions = 0;
  const options = { ...f, execute: async e => {
    executions++;
    await f.commit();
    return { version: VERSION, attemptId: e.attemptId, child: 'started', containment: 'reaped', result: { status: 'success' } };
  } };
  const refusal = error => {
    assert.equal(error.code, 'PUBLICATION_UNCERTAIN');
    assert.equal(error.details.diagnostic.primaryCause, 'GIT_AUTHORIZATION_REJECTED');
    return true;
  };
  await assert.rejects(runAttempt(options), refusal);
  await assert.rejects(runAttempt({ ...options, admissionResumed: true }), refusal);
  const saved = await f.journal.get(f.envelope.runId);
  assert.deepEqual((await f.store.get(f.envelope.runId)).publicationIntent,
    { previous: f.envelope.startHead, head: saved.collection.head });
  assert.match(f.comments[0].body, /Cause summary: GIT_AUTHORIZATION_REJECTED/);
  assert.equal(await f.remoteHead(), f.envelope.startHead);
  assert.equal(f.pushes(), 1);
  assert.equal(executions, 1);
});

for (const phase of ['pending intent', 'recorded publication']) for (const changed of ['neither', 'remote ref', 'collected head']) {
  const evidence = changed === 'neither' ? 'matching evidence' : `a changed ${changed}`;
  test(`native replay of a ${phase} with ${evidence}`, async t => {
    const f = await native(t, { beforeAdmission: precreate });
    const e = f.envelope;
    const readyEvents = structuredClone(f.events);
    assert.deepEqual(e.continuation, { head: e.startHead, pullRequest: null });
    await f.prepare(e);
    await f.commit();
    const progress = await f.collect(e);
    // Simulate controller interruption after execution and collection, with
    // the remote push either pending readback or already recorded by Writer.
    const journal = { version: VERSION, envelope: e, outcome: null, progress: null, diagnostic: null,
      execution: { reserved: true, returned: true, child: 'started', containment: 'reaped', result: { status: 'success' } },
      collection: { head: progress.head, clean: true, preserved: true } };
    await f.journal.put(e.runId, journal);
    const recorded = phase === 'recorded publication';
    if (recorded) {
      const prior = await push(f, progress);
      assert.equal(prior.publishedHead, progress.head);
      assert.equal(prior.prNumber, 43);
    } else {
      const inspect = f.publisher.inspect.bind(f.publisher);
      f.publisher.inspect = (envelope, bundle, inspectCandidate) => inspect(envelope, bundle, g => inspectCandidate({
        ...g, push: async () => { await g.push(); f.stale(true); }
      }));
      await assert.rejects(push(f, progress), { code: 'PUBLICATION_UNCERTAIN' });
      f.stale(false);
    }
    assert.equal(await f.remoteHead(), progress.head);
    const publishedState = await f.store.get(e.runId);
    assert.equal(publishedState.publishedHead, recorded ? progress.head : null);
    assert.deepEqual(publishedState.publicationIntent, recorded ? null : { previous: e.startHead, head: progress.head });
    assert.equal(publishedState.outcome, null);
    if (changed === 'remote ref') await f.command(f.root, ['--git-dir=' + f.remote, 'update-ref', taskRef, e.startHead]);
    if (changed === 'collected head') {
      await f.commit('docs/work.md', 'different retained candidate\n');
      const different = await f.collect(e);
      await assert.rejects(f.broker.invoke({ operation: 'publish-progress', runId: e.runId,
        attemptId: e.attemptId, bundle: different.bundle, reconciliationHead: progress.head }),
      { code: 'PUBLICATION_RECONCILIATION_REQUIRED' });
    } else await replaceMain(f);
    const resume = () => f.broker.invoke(f.admissionRequest);
    await f.journal.put(e.runId, { ...journal, execution: null });
    await assert.rejects(resume(), { code: 'PREDISPATCH_ATTEMPT_FINALIZED' });
    await f.journal.put(e.runId, { ...journal, collection: { ...journal.collection, head: e.startHead } });
    await assert.rejects(resume(), { code: 'PREDISPATCH_ATTEMPT_FINALIZED' });
    await f.journal.put(e.runId, journal);
    const publicationRequests = [];
    const replay = () => routeAttempt({
      env: { GITHUB_EVENT_NAME: 'issues', GITHUB_REF: `refs/heads/${CONSUMER.baseBranch}`, GITHUB_RUN_ID: String(e.runId) },
      readEvent: async () => JSON.stringify({ action: 'labeled', label: { name: e.readyLabel },
        issue: { number: e.number }, repository: { full_name: REPOSITORY }, sender: { login: CONSUMER.owner } }),
      createWriter: () => ({ invoke: async ({ workflowReadToken, ...request }) => {
        if (request.operation === 'publish-progress') publicationRequests.push(request);
        const result = await f.broker.invoke(request);
        if (request.operation === 'admit') {
          assert.equal(result.resumed, true);
          assert.deepEqual(result.envelope, e);
        }
        return result;
      } }),
      createJournal: () => f.journal,
      createDispatcher: () => ({ dispatch: () => assert.fail('retained publication ran a second worker') }),
      prepare: () => assert.fail('retained publication prepared a new checkout'),
      collect: f.collect,
      persistFailure: async () => ({})
    });
    if (changed === 'neither') {
      const finished = await replay();
      assert.equal(finished.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
      assert.equal(finished.head, progress.head);
      assert.deepEqual(await replay(), finished);
      assert.equal((await f.store.get(e.runId)).publicationIntent, null);
    } else {
      const code = changed === 'remote ref'
        ? recorded ? 'REMOTE_HEAD_CHANGED' : 'PUBLICATION_UNCERTAIN'
        : 'PUBLICATION_RECONCILIATION_REQUIRED';
      await assert.rejects(replay, { code });
      const retained = await f.store.get(e.runId);
      assert.deepEqual(retained.publicationIntent, publishedState.publicationIntent);
      assert.equal(retained.publishedHead, publishedState.publishedHead);
      assert.equal((await f.journal.get(e.runId)).collection.head, progress.head);
    }
    assert.deepEqual(publicationRequests.map(request => request.reconciliationHead), changed === 'collected head' ? [] : [progress.head]);
    assert.equal(await f.remoteHead(), changed === 'remote ref' ? e.startHead : progress.head);
    assert.equal(f.pushes(), 1);
    assert.equal(f.comments.length, 1);
    assert.deepEqual(f.events, readyEvents);
  });
}

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
