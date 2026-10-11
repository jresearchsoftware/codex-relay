import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdir, symlink, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { CONSUMER, CONSUMER_DIGEST } from '../../consumer/consumer.mjs';
import { renderAuthorityRecord, extractAuthorityRecord, sha256Body } from '../../contracts/src/github-authority.mjs';
import { createAdmissionControl } from '../src/admission-control.mjs';
import { runAttempt } from '../src/attempt.mjs';
import { createPublicationBroker } from '../src/publication-broker.mjs';
import { prepublicationAuthorizationBody } from '../src/prepublication-recovery.mjs';
import { parseRecoveryRequest } from '../src/recover-attempt-publication.mjs';
import { OWNER, REPOSITORY, REVIEWER, WRITER, VERSION } from '../src/execution-contract.mjs';
import { fixture } from './fixture.mjs';

const owner = { login: OWNER, id: 56, type: 'User' };
const writer = { login: WRITER, id: 57, type: 'Bot' };
const reviewer = { login: REVIEWER, id: 987, type: 'Bot' };
const charter = 'Authority model: github-native-v1\nIssue closure policy: keep-open\n\nImplement bounded work.';
const terminalAt = '2026-09-04T12:01:30Z';
const completedAt = '2026-09-04T12:02:00Z';
const authorizedAt = '2026-09-04T12:03:00Z';
const collectedFailure = () => Object.assign(new Error('Collector observation incomplete'), {
  code: 'TRUSTED_GIT_FAILED', details: { failureDiagnostic: {
    classification: 'GIT_LOCAL_FAILURE', primaryCause: 'GIT_LOCAL_FAILURE', operation: 'diff',
    gitExitCode: 128, preview: 'Permission denied during worktree collection', bytes: 46, truncated: false
  } }
});
const returned = e => ({ version: VERSION, attemptId: e.attemptId, child: 'started', containment: 'reaped',
  result: { status: 'success', summary: 'Authorized source work completed.', validation: ['Focused local validation passed.'] } });

async function terminalFixture(t, options = {}) {
  let requestComment;
  const nativeComments = new Map();
  const f = await fixture(t, {
    continuation: options.continuation === true, continuationPr: false,
    createAdmission: async ({ root, store, journal }) => {
      await mkdir(join(root, 'gate'));
      const admission = createAdmissionControl({ root: join(root, 'gate'), consumerDigest: CONSUMER_DIGEST,
        store, journal, protectedRoot: false });
      await admission.initialize(); return admission;
    },
    beforeAdmission: async ({ issue, api, continuationHead }) => {
      const base = /Required starting base: `([^`]+)`/.exec(issue.body)[1];
      issue.body = charter;
      const request = { schema_version: '3.0', kind: 'task-request', repository: REPOSITORY, task: 42,
        parent: { kind: 'issue', number: 42 }, charter_sha256: sha256Body(charter), step: 1, route: 'auto',
        purpose: 'Implement bounded work', scope: ['Implement the authorized change.'],
        model: 'gpt-6.1-sol', effort: 'xhigh', subagents: true, validation: ['diff-check', 'secret-scan'],
        boundaries: ['No deployment, merge, release or Issue closure.'], decisions: [], context: [], supersedes: null,
        branch: `${CONSUMER.taskBranchPrefix}test-42`, base_sha: base, starting_head: continuationHead ?? base, existing_pr: null,
        issue_closure_policy: 'keep-open' };
      requestComment = { id: 901, user: reviewer, body: renderAuthorityRecord(request),
        issue_url: `https://api.github.com/repos/${REPOSITORY}/issues/42` };
      const list = api.list.bind(api); const get = api.get.bind(api); const post = api.post.bind(api);
      const patch = api.patch.bind(api);
      api.userIdentity = async login => {
        const user = [owner, writer, reviewer].find(candidate => candidate.login === login);
        assert.ok(user, `Unexpected identity ${login}`); return structuredClone(user);
      };
      api.get = async path => {
        if (path === '/issues/comments/901') return structuredClone(requestComment);
        const id = Number(/^\/issues\/comments\/(\d+)$/.exec(path)?.[1]);
        return nativeComments.has(id) ? structuredClone(nativeComments.get(id)) : get(path);
      };
      api.list = async path => {
        if (/^\/pulls\/\d+\/reviews$/.test(path)) return [];
        const rows = (await list(path)).map(comment => nativeComments.has(comment.id) ? structuredClone(nativeComments.get(comment.id)) : comment);
        if (!path.endsWith('/comments')) return rows;
        const target = `https://api.github.com/repos/${REPOSITORY}${path.slice(0, -'/comments'.length)}`;
        const relevant = rows.filter(comment => comment.issue_url === target);
        return path === '/issues/42/comments' ? [structuredClone(requestComment), ...relevant] : relevant;
      };
      api.post = async (path, body) => {
        const result = await post(path, body);
        if (!path.endsWith('/comments')) return result;
        Object.assign(result, { user: structuredClone(writer), issue_url: `https://api.github.com/repos/${REPOSITORY}${path.slice(0, -'/comments'.length)}`,
          created_at: terminalAt, updated_at: terminalAt });
        // Fixture native reads expose the same identity and target as POST.
        nativeComments.set(result.id, result);
        return result;
      };
      api.patch = async (path, body) => {
        const result = await patch(path, body);
        const id = Number(/^\/issues\/comments\/(\d+)$/.exec(path)?.[1]);
        if (nativeComments.has(id)) Object.assign(nativeComments.get(id), body);
        return nativeComments.has(id) ? structuredClone(nativeComments.get(id)) : result;
      };
    }
  });
  let head;
  await assert.rejects(runAttempt({ ...f, execute: async e => {
    head = options.commit ? await options.commit(f) : await f.commit();
    return returned(e);
  }, collect: async () => { throw collectedFailure(); } }), { code: 'TRUSTED_GIT_FAILED' });
  await f.admissionControl.complete({ runId: 99, attemptId: f.envelope.attemptId });
  f.run.status = 'completed'; f.run.updated_at = completedAt;
  let collections = 0;
  let collectRetained = e => f.collect(e);
  const makeBroker = (overrides = {}) => ({ invoke: value => createPublicationBroker({ api: f.api, store: f.store,
    publisher: f.publisher, admission: f.admissionControl, journal: f.journal, lifecycleStore: f.lifecycleStore,
    collectRetained: async e => { collections++; return collectRetained(e); }, ...overrides }).dispatch(value) });
  const broker = makeBroker();
  const operation = { operation: 'recover-prepublication', runId: 99, attemptId: f.envelope.attemptId, head };
  const original = { writer: await f.store.get(99), journal: await f.journal.get(99),
    comment: await f.api.get(`/issues/comments/${(await f.store.get(99)).outcome.outcomeId}`) };
  const authorize = async () => {
    const state = await broker.invoke({ ...operation, operation: 'prepublication-state' });
    const comment = { id: 10000, user: structuredClone(owner),
      issue_url: `https://api.github.com/repos/${REPOSITORY}/issues/42`, created_at: authorizedAt,
      updated_at: authorizedAt, body: prepublicationAuthorizationBody(state.binding) };
    assert.equal(comment.body, state.authorizationBody);
    f.comments.push(comment);
    return { comment, binding: state.binding, request: { ...operation, authorizationId: comment.id } };
  };
  return { ...f, broker, head, operation, original, requestComment, nativeComments, authorize, makeBroker,
    collections: () => collections, setCollect: value => { collectRetained = value; } };
}

async function assertHistorical(f) {
  assert.deepEqual(await f.journal.get(99), f.original.journal);
  const record = await f.store.get(99);
  for (const field of ['outcome', 'publicationIntent', 'publishedHead', 'finalHead', 'controllerLifecycle']) {
    assert.deepEqual(record[field], f.original.writer[field], `Historical ${field} changed`);
  }
  assert.deepEqual(await f.api.get(`/issues/comments/${f.original.comment.id}`), f.original.comment);
}

test('terminal prepublication recovery publishes one successor for the original native Request and preserves the blocked history', async t => {
  const f = await terminalFixture(t); const { request } = await f.authorize();
  const result = await f.broker.invoke(request);
  assert.equal(result.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
  assert.equal(result.head, f.head); assert.equal(result.prNumber, 43); assert.equal(result.draft, false);
  assert.notEqual(result.outcomeId, f.original.comment.id);
  assert.equal(f.pushes(), 1); assert.equal(await f.remoteHead(), f.head);
  const successor = await f.api.get(`/issues/comments/${result.outcomeId}`);
  const typed = extractAuthorityRecord(successor.body);
  assert.equal(typed.status, 'implemented'); assert.equal(typed.attempt, f.envelope.attemptId);
  assert.deepEqual(typed.request, f.envelope.requestReference);
  assert.deepEqual(typed.parent, { kind: 'pull_request', number: 43 });
  assert.equal(typed.result.revision, f.head);
  assert.deepEqual(typed.result.identities, [{ kind: 'github-actions-run', id: '99' }]);
  assert.match(successor.body, /Authorized source work completed/);
  assert.match(successor.body, /Focused local validation passed/);
  assert.match(successor.body, /Attempt: run-99/);
  assert.equal((successor.body.match(/^Latest durable candidate head: /gm) ?? []).length, 1);
  assert.equal((await f.store.get(99)).prepublicationRecovery.complete, true);
  const collected = f.collections();
  f.setCollect(() => assert.fail('Completed receipt replay recollected the checkout'));
  assert.deepEqual(await f.broker.invoke(request), result);
  assert.equal(f.collections(), collected); assert.equal(f.pushes(), 1);
  await assertHistorical(f);
  await assert.rejects(runAttempt({ ...f, execute: () => assert.fail('Recovery launched a second child'),
    collect: () => assert.fail('Ordinary terminal replay recollected') }), { code: 'TRUSTED_GIT_FAILED' });
  assert.deepEqual((await f.admissionControl.status()).unknown, []);
});

test('terminal prepublication continuation binds and fast-forwards its exact original previous branch head', async t => {
  const f = await terminalFixture(t, { continuation: true });
  assert.equal(await f.remoteHead(), f.envelope.startHead);
  const { request, binding } = await f.authorize();
  assert.equal(binding.previous, f.envelope.startHead);
  const result = await f.broker.invoke(request);
  assert.equal(result.head, f.head); assert.equal(f.pushes(), 1);
  assert.equal(await f.remoteHead(), f.head); await assertHistorical(f);
});

test('a later Actions rerun cannot stand in for the original sealed first attempt', async t => {
  const f = await terminalFixture(t); const { request } = await f.authorize();
  f.run.run_attempt = 2;
  f.run.updated_at = '2026-09-04T12:02:30Z';
  await assert.rejects(f.broker.invoke({ ...f.operation, operation: 'prepublication-state' }),
    { code: 'RECOVERY_ORIGINAL_RUN_NOT_COMPLETED' });
  await assert.rejects(f.broker.invoke(request), { code: 'RECOVERY_ORIGINAL_RUN_NOT_COMPLETED' });
  assert.equal(f.collections(), 0); assert.equal(f.pushes(), 0);
  assert.equal((await f.store.get(99)).prepublicationRecovery, undefined);
  await assertHistorical(f);
});

test('prepublication recovery requires a fresh exact owner-native comment and the original Writer Bot identity', async t => {
  const f = await terminalFixture(t); const { request, comment, binding } = await f.authorize();
  const original = structuredClone(comment);
  for (const change of [
    { user: { ...owner, id: owner.id + 1 } }, { user: { ...owner, type: 'Bot' } },
    { issue_url: `https://api.github.com/repos/${REPOSITORY}/issues/43` },
    { created_at: completedAt, updated_at: completedAt },
    { updated_at: '2026-09-04T12:04:00Z' },
    { body: `${original.body}\nPublish any candidate.` }
  ]) {
    Object.assign(comment, structuredClone(original), change);
    await assert.rejects(f.broker.invoke(request));
  }
  for (const key of Object.keys(binding)) {
    const value = binding[key];
    const replacement = typeof value === 'string' ? `${value}-changed` : typeof value === 'number' ? value + 1 : { changed: true };
    Object.assign(comment, structuredClone(original), { body: prepublicationAuthorizationBody({ ...binding, [key]: replacement }) });
    await assert.rejects(f.broker.invoke(request), `Changed ${key} authorization was accepted`);
  }
  Object.assign(comment, original);
  const identity = f.api.userIdentity;
  f.api.userIdentity = async login => login === WRITER ? { ...writer, id: writer.id + 1 } : identity(login);
  await assert.rejects(f.broker.invoke(request));
  assert.equal(f.pushes(), 0); assert.equal(f.collections(), 0);
  await assertHistorical(f);
});

for (const boundary of ['failed-result', 'unknown-containment', 'missing-journal', 'collection', 'progress', 'intent', 'controller']) {
  test(`prepublication recovery rejects ${boundary} before importing retained bytes`, async t => {
    const f = await terminalFixture(t); const { request } = await f.authorize();
    if (boundary === 'missing-journal') {
      const broker = f.makeBroker({ journal: { get: async () => null } });
      await assert.rejects(broker.invoke(request));
    } else if (['failed-result', 'unknown-containment', 'collection', 'progress'].includes(boundary)) {
      const record = await f.journal.get(99);
      if (boundary === 'failed-result') record.execution.result.status = 'blocked';
      if (boundary === 'unknown-containment') record.execution.containment = 'unknown';
      if (boundary === 'collection') record.collection = { head: f.head, clean: true };
      if (boundary === 'progress') record.progress = { head: f.head, clean: true };
      await f.journal.put(99, record);
      await assert.rejects(f.broker.invoke(request));
    } else {
      const record = await f.store.get(99);
      if (boundary === 'intent') record.publicationIntent = { previous: null, head: f.head };
      if (boundary === 'controller') record.controllerLifecycle = { version: 1, status: 'complete', child: 'not_started', containment: 'not_required' };
      await f.store.put(99, record);
      await assert.rejects(f.broker.invoke(request));
    }
    assert.equal(f.collections(), 0); assert.equal(f.pushes(), 0);
  });
}

for (const boundary of ['authority', 'request', 'remote', 'candidate', 'dirty', 'incomplete']) {
  test(`prepublication recovery rejects changed ${boundary} without a Writer push`, async t => {
    const f = await terminalFixture(t); const { request } = await f.authorize();
    if (boundary === 'authority') f.issue.body += '\nAnother required behavior.';
    if (boundary === 'request') f.requestComment.body = renderAuthorityRecord({
      ...extractAuthorityRecord(f.requestComment.body), purpose: 'Changed trusted Request purpose'
    });
    if (boundary === 'remote') await f.command(f.source, ['push', f.remote, `${CONSUMER.baseBranch}:refs/heads/${f.envelope.branch}`]);
    if (boundary === 'candidate') await f.commit('docs/work.md', 'Changed after owner authorization\n');
    if (boundary === 'dirty') await writeFile(join(f.cwd, 'docs/work.md'), 'Uncommitted task work\n');
    if (boundary === 'incomplete') f.setCollect(async () => { throw collectedFailure(); });
    await assert.rejects(f.broker.invoke(request));
    assert.equal(f.pushes(), 0);
    assert.equal((await f.store.get(99)).prepublicationRecovery, undefined);
    await assertHistorical(f);
  });
}

for (const boundary of ['identity', 'mode', 'transient-secret']) {
  test(`prepublication recovery applies the ordinary isolated importer to ${boundary}`, async t => {
    const f = await terminalFixture(t, { commit: async fixture => {
      if (boundary === 'identity') {
        await writeFile(join(fixture.cwd, 'docs/work.md'), 'Invalid task commit identity\n');
        await fixture.command(fixture.cwd, ['add', 'docs/work.md']);
        await fixture.command(fixture.cwd, ['commit', '-m', 'wrong identity']);
      } else if (boundary === 'mode') {
        await symlink('docs/work.md', join(fixture.cwd, 'unsupported-link'));
        await fixture.command(fixture.cwd, ['add', 'unsupported-link']);
        await fixture.command(fixture.cwd, ['commit', '-m', 'unsupported mode'], fixture.identity);
      } else {
        await fixture.commit('docs/work.md', `ghp_${'x'.repeat(40)}\n`);
        await fixture.commit('docs/work.md', 'Secret removed from final tree\n');
      }
      return fixture.command(fixture.cwd, ['rev-parse', 'HEAD']);
    } });
    const { request } = await f.authorize();
    await assert.rejects(f.broker.invoke(request), { code: boundary === 'identity' ? 'COMMIT_OWNERSHIP_INVALID'
      : boundary === 'mode' ? 'COMMIT_FILE_MODE_INVALID' : 'SECRET_PUBLICATION_SCAN_FAILED' });
    assert.equal(f.pushes(), 0); await assertHistorical(f);
  });
}

test('a failed prepublication push consumes its one durable authorization and remains visible to admission drain', async t => {
  const f = await terminalFixture(t); const { request, comment } = await f.authorize();
  f.failPush(true);
  await assert.rejects(f.broker.invoke(request));
  const record = await f.store.get(99);
  assert.ok(record.prepublicationRecovery); assert.equal(f.pushes(), 1);
  assert.notEqual(record.prepublicationRecovery.publication.status, 'PUBLISHED');
  f.failPush(false); f.setCollect(() => assert.fail('Uncertain recovery recollected'));
  await assert.rejects(f.broker.invoke(request));
  const second = { ...structuredClone(comment), id: 10001, created_at: '2026-09-04T12:04:00Z', updated_at: '2026-09-04T12:04:00Z' };
  f.comments.push(second);
  await assert.rejects(f.broker.invoke({ ...request, authorizationId: second.id }));
  assert.equal(f.pushes(), 1);
  assert.deepEqual((await f.admissionControl.status()).unknown, [99]);
  await assertHistorical(f);
});

test('publication reservation failure performs zero pushes and preserves the original terminal state', async t => {
  const f = await terminalFixture(t); const { request } = await f.authorize();
  const broker = f.makeBroker({ store: { ...f.store, put: async (id, record) => {
    if (record.prepublicationRecovery) throw Object.assign(new Error('Reservation storage failed'), { code: 'EIO' });
    return f.store.put(id, record);
  } } });
  await assert.rejects(broker.invoke(request), { code: 'EIO' });
  assert.equal(f.pushes(), 0); await assertHistorical(f);
});

test('a crash after reservation consumes the authorization without publishing or recollecting on replay', async t => {
  const f = await terminalFixture(t); const { request } = await f.authorize();
  const publisher = { inspect: (e, bundle, fn) => f.publisher.inspect(e, bundle, g => fn({ ...g,
    push: async () => { throw new Error('Synthetic stopped mutation'); }
  })) };
  const store = { ...f.store, put: async (id, record) => {
    if (record.prepublicationRecovery?.publication) throw Object.assign(new Error('Receipt storage failed'), { code: 'EIO' });
    return f.store.put(id, record);
  } };
  await assert.rejects(f.makeBroker({ store, publisher }).invoke(request), { code: 'EIO' });
  const reserved = await f.store.get(99);
  assert.equal(reserved.prepublicationRecovery.authorizationId, request.authorizationId);
  assert.equal(reserved.prepublicationRecovery.publication, null);
  f.setCollect(() => assert.fail('Unfinished reservation recollected on replay'));
  await assert.rejects(f.broker.invoke(request), { code: 'PUBLICATION_UNCERTAIN' });
  assert.equal(f.pushes(), 0);
  assert.deepEqual((await f.admissionControl.status()).unknown, [99]);
  await assertHistorical(f);
});

for (const boundary of ['journal', 'authorization', 'last-ref']) {
  test(`changed ${boundary} after object validation still blocks publication reservation`, async t => {
    const f = await terminalFixture(t); const { request, comment } = await f.authorize();
    const publisher = { inspect: (e, bundle, fn) => f.publisher.inspect(e, bundle, async g => {
      if (boundary === 'journal') {
        const saved = await f.journal.get(99); saved.execution.result.summary = 'Evidence changed during import';
        await f.journal.put(99, saved);
      }
      if (boundary === 'authorization') comment.body = 'Revoked';
      return fn(boundary === 'last-ref' ? { ...g, observe: async () => 'f'.repeat(40) } : g);
    }) };
    await assert.rejects(f.makeBroker({ publisher }).invoke(request));
    assert.equal(f.pushes(), 0);
    assert.equal((await f.store.get(99)).prepublicationRecovery, undefined);
  });
}

test('a lost successor Outcome response resumes native observation without another publication push', async t => {
  const f = await terminalFixture(t); const { request } = await f.authorize();
  const post = f.api.post; let lost = false; let posts = 0;
  f.api.post = async (path, body) => {
    const result = await post(path, body);
    if (path === '/issues/43/comments') {
      posts++;
      if (!lost) { lost = true; throw Object.assign(new Error('Outcome response lost'), { code: 'GITHUB_REQUEST_FAILED' }); }
    }
    return result;
  };
  await assert.rejects(f.broker.invoke(request));
  assert.equal((await f.store.get(99)).prepublicationRecovery.publication.status, 'PUBLISHED');
  f.setCollect(() => assert.fail('Verified publication recollected after Outcome response loss'));
  const result = await f.broker.invoke(request);
  assert.equal(result.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
  assert.equal(result.draft, false); assert.equal(f.pushes(), 1); assert.equal(posts, 1);
  await assertHistorical(f);
});

for (const boundary of ['wrong-id', 'wrong-type', 'wrong-parent']) {
  test(`successor Outcome rejects ${boundary} at receipt and Ready, then resumes its original publication`, async t => {
    const f = await terminalFixture(t); const { request } = await f.authorize();
    const get = f.api.get; const post = f.api.post;
    let stage = 'receipt'; let successorReads = 0; let posts = 0;
    f.api.post = async (path, body) => {
      if (path === '/issues/43/comments') posts++;
      return post(path, body);
    };
    f.api.get = async path => {
      const observed = await get(path);
      if (!/^\/issues\/comments\/\d+$/.test(path)
        || !observed.body?.endsWith(`<!-- relay:${f.envelope.attemptId}:prepublication-${request.authorizationId} -->`)) return observed;
      successorReads++;
      if (stage !== 'receipt' && !(stage === 'ready' && successorReads === 2)) return observed;
      if (boundary === 'wrong-id') observed.user.id++;
      if (boundary === 'wrong-type') observed.user.type = 'User';
      if (boundary === 'wrong-parent') observed.issue_url = `https://api.github.com/repos/${REPOSITORY}/issues/42`;
      return observed;
    };
    await assert.rejects(f.broker.invoke(request), { code: 'COMMENT_CONTENT_CHANGED' });
    const published = (await f.store.get(99)).prepublicationRecovery;
    assert.equal(published.publication.status, 'PUBLISHED');
    assert.equal(published.outcome, null); assert.equal(published.complete, false);
    assert.equal(f.collections(), 1); assert.equal(f.pushes(), 1); assert.equal(posts, 1);
    assert.equal(await f.remoteHead(), f.head); await assertHistorical(f);
    f.setCollect(() => assert.fail('Successor native observation recollected verified publication'));

    stage = 'ready'; successorReads = 0;
    await assert.rejects(f.broker.invoke(request), { code: 'COMMENT_CONTENT_CHANGED' });
    assert.equal(successorReads, 2);
    const pending = (await f.store.get(99)).prepublicationRecovery;
    assert.equal(pending.publication.status, 'PUBLISHED');
    assert.equal(pending.outcome.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
    assert.equal(pending.complete, false); assert.equal((await f.api.get('/pulls/43')).draft, true);
    assert.deepEqual((await f.admissionControl.status()).unknown, [99]);
    await assertHistorical(f);

    stage = 'valid';
    const result = await f.broker.invoke(request);
    assert.equal(result.outcomeId, pending.outcome.outcomeId); assert.equal(result.draft, false);
    assert.equal(f.collections(), 1); assert.equal(f.pushes(), 1); assert.equal(posts, 1);
    assert.deepEqual((await f.admissionControl.status()).unknown, []); await assertHistorical(f);
  });
}

test('failed recovered Ready retains the successor Outcome and resumes handoff without a push or recollection', async t => {
  const f = await terminalFixture(t); const { request } = await f.authorize();
  const ready = f.api.ready; let calls = 0;
  f.api.ready = async () => { calls++; throw Object.assign(new Error('Ready unavailable'), { code: 'GITHUB_REQUEST_FAILED' }); };
  await assert.rejects(f.broker.invoke(request), { code: 'GITHUB_REQUEST_FAILED' });
  const recovery = (await f.store.get(99)).prepublicationRecovery;
  assert.equal(recovery.publication.status, 'PUBLISHED');
  assert.equal(recovery.outcome.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
  assert.equal(recovery.complete, false); assert.equal((await f.api.get('/pulls/43')).draft, true);
  assert.deepEqual((await f.admissionControl.status()).unknown, [99]);
  f.setCollect(() => assert.fail('Ready recovery recollected the terminal checkout'));
  f.api.ready = async id => { calls++; await ready(id); };
  const result = await f.broker.invoke(request);
  assert.equal(result.outcomeId, recovery.outcome.outcomeId); assert.equal(result.draft, false);
  assert.equal(calls, 2); assert.equal(f.pushes(), 1);
  assert.deepEqual((await f.admissionControl.status()).unknown, []); await assertHistorical(f);
});

test('lost recovered Ready response is reconciled by exact native state without repeating the transition', async t => {
  const f = await terminalFixture(t); const { request } = await f.authorize();
  const ready = f.api.ready; let calls = 0;
  f.api.ready = async id => {
    calls++; await ready(id); throw Object.assign(new Error('Ready response lost'), { code: 'GITHUB_REQUEST_FAILED' });
  };
  const result = await f.broker.invoke(request);
  assert.equal(result.draft, false); assert.equal(calls, 1);
  f.setCollect(() => assert.fail('Completed Ready receipt recollected'));
  assert.deepEqual(await f.broker.invoke(request), result);
  assert.equal(calls, 1); assert.equal(f.pushes(), 1); await assertHistorical(f);
});

test('owner recovery input keeps existing requests and makes prepublication an explicit bounded opt-in', () => {
  const coordinates = { runId: 99, attemptId: 'run-99' };
  for (const request of [
    { ...coordinates, operation: 'inspect' },
    { ...coordinates, authorizationId: 10000 },
    { ...coordinates, operation: 'inspect-prepublication', head: 'a'.repeat(40) },
    { ...coordinates, operation: 'recover-prepublication', head: 'a'.repeat(40), authorizationId: 10000 }
  ]) assert.deepEqual(parseRecoveryRequest(request), request);
  const recovery = { ...coordinates, operation: 'recover-prepublication', head: 'a'.repeat(40), authorizationId: 10000 };
  for (const request of [
    { ...coordinates, head: recovery.head, authorizationId: 10000 },
    { ...recovery, operation: 'recover-publication' }, { ...recovery, operation: undefined },
    { ...recovery, head: 'main' }, { ...recovery, head: 'A'.repeat(40) },
    { ...recovery, head: undefined }, { ...recovery, authorizationId: 0 },
    { ...recovery, authorizationId: '10000' }, { ...recovery, runId: '99' },
    { ...recovery, attemptId: '../../other' },
    ...['bundle', 'checkout', 'remote', 'binding', 'journal', 'workflowReadToken'].map(field => ({ ...recovery, [field]: 'caller-selected' }))
  ]) assert.throws(() => parseRecoveryRequest(request), { code: 'RECOVERY_REQUEST_INVALID' });
});

test('owner recovery CLI rejects an implicit prepublication input before invoking the protected helper', async () => {
  const script = fileURLToPath(new URL('../src/recover-attempt-publication.mjs', import.meta.url));
  const child = spawn(process.execPath, [script], { env: { PATH: '/usr/bin:/bin',
    RELAY_CONSUMER_CONFIG: process.env.RELAY_CONSUMER_CONFIG }, stdio: ['pipe', 'pipe', 'pipe'] });
  let output = '';
  child.stdout.on('data', bytes => { output += bytes; });
  child.stderr.on('data', bytes => { output += bytes; });
  const completed = new Promise((resolve, reject) => { child.once('error', reject); child.once('close', resolve); });
  child.stdin.end(JSON.stringify({ runId: 99, attemptId: 'run-99', authorizationId: 10000, head: 'a'.repeat(40) }));
  assert.equal(await completed, 1);
  assert.match(output, /RECOVERY_REQUEST_INVALID/);
  assert.doesNotMatch(output, /WRITER_HELPER|FIXED_ROOT|sudo/);
});
