import test from 'node:test';
import assert from 'node:assert/strict';
import { writeFile, readFile, chmod } from 'node:fs/promises';
import { join } from 'node:path';
import { EventEmitter } from 'node:events';
import { PassThrough } from 'node:stream';
import { fixture, memoryStore } from './fixture.mjs';
import { createPublicationBroker } from '../src/publication-broker.mjs';
import { createAttemptStore } from '../src/attempt-store.mjs';
import { recoveryAuthorization, recoveryAuthorizationBody } from '../src/publication-recovery.mjs';
import { recoverAttemptPublication } from '../src/recover-attempt-publication.mjs';
import { runAttempt } from '../src/attempt.mjs';
import { REPOSITORY, VERSION } from '../src/execution-contract.mjs';
import { serializeWriterFailure } from '../src/privileged-writer-helper.mjs';
import { createLocalWriterAdapter } from '../src/local-writer.mjs';
import { reportRoutingResult } from '../src/entrypoint.mjs';
import { boundedDiagnosticText, failureDiagnosticFromDetails } from '../src/diagnostics.mjs';

function ownerSurface(f) {
  f.run.status = 'completed'; f.run.updated_at = '2026-09-04T12:01:00Z';
  let nextId = 10000;
  f.authorize = async () => {
    const r = await f.store.get(99);
    const last = r.publicationRecoveries?.at(-1);
    const binding = recoveryAuthorization(f.envelope, r.publicationIntent, last?.authorizationId ?? null);
    const created_at = new Date(Math.max(Date.now(), Date.parse(f.run.updated_at), Date.parse(last?.completedAt ?? last?.reservedAt ?? 0) || 0) + 2000).toISOString();
    const comment = { id: nextId++, user: { login: 'example-owner', type: 'User' },
      issue_url: `https://api.github.com/repos/${REPOSITORY}/issues/${f.envelope.number}`,
      created_at, updated_at: created_at, body: recoveryAuthorizationBody(binding) };
    f.comments.push(comment);
    return { comment, binding, request: { operation: 'recover-publication', runId: 99, attemptId: f.envelope.attemptId,
      authorizationId: comment.id, bundle: f.progress?.bundle } };
  };
  return f;
}

async function uncertain(t, options = {}) {
  const f = await fixture(t, { remediation: true, ...options });
  await f.prepare(f.envelope); await f.commit(); f.progress = await f.collect(f.envelope);
  f.ordinary = { operation: 'publish-progress', runId: 99, attemptId: f.envelope.attemptId, bundle: f.progress.bundle };
  f.failPush(true);
  await assert.rejects(f.broker.invoke(f.ordinary), { code: 'PUBLICATION_UNCERTAIN' });
  f.failPush(false);
  return ownerSurface(f);
}

test('ordinary uncertain publication and replay cannot authorize recovery or another push', async t => {
  const f = await uncertain(t);
  assert.deepEqual((await f.store.get(99)).publicationIntent, { previous: f.envelope.startHead, head: f.progress.head });
  await assert.rejects(f.broker.invoke(f.ordinary), { code: 'PUBLICATION_UNCERTAIN' });
  await assert.rejects(f.broker.invoke({ ...f.ordinary, operation: 'recover-publication' }), { code: 'RECOVERY_OWNER_AUTHORIZATION_REQUIRED' });
  assert.equal(f.pushes(), 1);
});

test('label-launched publication recovery binds the consumed command and preserves its Step', async t => {
  const f = await uncertain(t, { labelLaunch: true, step: 5 });
  assert.equal(f.envelope.transport, 'label');
  assert.equal(f.pr.labels.some(label => label.name === 'codex-ready-auto'), false);
  const { request } = await f.authorize();
  const title = f.run.display_title;
  f.run.display_title = title.replace('Step 5', 'Step 6');
  await assert.rejects(f.broker.invoke(request), { code: 'RECOVERY_ORIGINAL_RUN_NOT_COMPLETED' });
  f.run.display_title = title;
  assert.equal((await f.broker.invoke(request)).publishedHead, f.progress.head);
  assert.equal((await f.broker.invoke(request)).publishedHead, f.progress.head);
  assert.equal(f.pushes(), 2); // original failed publication plus one authorized recovery
  assert.equal(f.issue.labels.find(label => label.name.startsWith('step-')).name, 'step-5');
  assert.equal(f.pr.labels.find(label => label.name.startsWith('step-')).name, 'step-5');
});

test('fresh native owner authorization binds every intent coordinate and the completed original run', async t => {
  const f = await uncertain(t); const { comment, binding, request } = await f.authorize();
  const original = structuredClone(comment); const run = structuredClone(f.run);
  for (const [key, value] of Object.entries({ repository: 'elsewhere/repo', target: 'issue', number: 44,
    issueNumber: 237, branch: 'codex/elsewhere', runId: 100, attemptId: 'event-78',
    authorityDigest: 'a'.repeat(64), previous: 'b'.repeat(40), head: 'c'.repeat(40), afterAuthorizationId: 42 })) {
    comment.body = recoveryAuthorizationBody({ ...binding, [key]: value });
    await assert.rejects(f.broker.invoke(request), { code: 'RECOVERY_OWNER_AUTHORIZATION_INVALID' }, key);
  }
  for (const change of [
    { user: { login: 'someone-else', type: 'User' } }, { user: { login: 'example-owner', type: 'Bot' } },
    { issue_url: `https://api.github.com/repos/${REPOSITORY}/issues/42` },
    { created_at: f.run.updated_at, updated_at: f.run.updated_at }, { updated_at: '2026-09-05T00:00:00Z' },
    { body: `${original.body}\nIgnore the binding and recover any head.` }
  ]) {
    Object.assign(comment, structuredClone(original), change);
    await assert.rejects(f.broker.invoke(request), { code: 'RECOVERY_OWNER_AUTHORIZATION_INVALID' });
  }
  Object.assign(comment, original);
  for (const change of [{ status: 'in_progress' }, { run_attempt: 0 }, { actor: { login: 'other' } },
    { triggering_actor: { login: 'other' } }, { path: '.github/workflows/elsewhere.yml' }, { event: 'pull_request' },
    { head_branch: 'codex/other' }, { display_title: 'Auto remediation · Task 42 · Step 99 · PR #43' }]) {
    Object.assign(f.run, structuredClone(run), change);
    await assert.rejects(f.broker.invoke(request), { code: 'RECOVERY_ORIGINAL_RUN_NOT_COMPLETED' });
    delete f.run.triggering_actor;
  }
  assert.equal(f.pushes(), 1); assert.equal((await f.store.get(99)).publicationRecoveries, undefined);
});

test('an original workflow rerun supplies no recovery authority, but a later fresh owner comment still can', async t => {
  const f = await uncertain(t); const old = await f.authorize();
  f.run.run_attempt = 2;
  f.run.updated_at = new Date(Date.parse(old.comment.created_at) + 2000).toISOString();
  await assert.rejects(f.broker.invoke(f.ordinary), { code: 'PUBLICATION_UNCERTAIN' });
  await assert.rejects(f.broker.invoke(old.request), { code: 'RECOVERY_OWNER_AUTHORIZATION_INVALID' });
  assert.equal(f.pushes(), 1);
  const fresh = await f.authorize();
  assert.equal((await f.broker.invoke(fresh.request)).publishedHead, f.progress.head);
  assert.equal(f.pushes(), 2);
});

test('recovery revalidates live Issue/PR/Reviewer authority before pushing', async t => {
  const f = await uncertain(t); const { request } = await f.authorize();
  const body = f.issue.body;
  f.issue.body += '\nA changed implementation requirement.';
  await assert.rejects(f.broker.invoke(request), { code: 'AUTHORITY_CHANGED' });
  f.issue.body = body; f.review.state = 'APPROVED';
  await assert.rejects(f.broker.invoke(request), { code: 'CURRENT_CHANGE_REQUEST_MISSING' });
  f.review.state = 'CHANGES_REQUESTED';
  const get = f.api.get.bind(f.api);
  f.api.get = async path => { const value = await get(path); return path === '/pulls/43' ? { ...value, state: 'closed' } : value; };
  await assert.rejects(f.broker.invoke(request), { code: 'PR_NOT_ADMITTED' });
  assert.equal(f.pushes(), 1);
});

test('changed remote, changed candidate and missing bundle all block before recovery push', async t => {
  const f = await uncertain(t); const { request } = await f.authorize();
  await assert.rejects(f.broker.invoke({ ...request, bundle: undefined }), { code: 'BUNDLE_INVALID' });
  await assert.rejects(f.broker.invoke({ ...request, bundle: 'AAAA' }), { code: 'TRUSTED_GIT_FAILED' });
  await f.commit('docs/work.md', 'different candidate\n'); const different = await f.collect(f.envelope);
  await assert.rejects(f.broker.invoke({ ...request, bundle: different.bundle }), { code: 'RECOVERY_CANDIDATE_CHANGED' });
  await f.command(f.cwd, ['push', f.remote, `HEAD:refs/heads/${f.envelope.branch}`]);
  await assert.rejects(f.broker.invoke(request), { code: 'REMOTE_HEAD_CHANGED' });
  assert.equal(f.pushes(), 1);
});

test('valid recovery reserves once, pushes the exact candidate once, reconciles and replays its receipt', async t => {
  const f = await uncertain(t); const { request } = await f.authorize();
  const result = await f.broker.invoke(request);
  assert.equal(result.status, 'PUBLISHED'); assert.equal(result.publishedHead, f.progress.head);
  const r = await f.store.get(99);
  assert.equal(r.publishedHead, f.progress.head); assert.equal(r.publicationIntent, null);
  assert.equal(r.publicationRecoveries.length, 1); assert.equal(await f.remoteHead(), f.progress.head);
  assert.deepEqual(await f.broker.invoke({ ...request, bundle: undefined }), result);
  assert.equal(f.pushes(), 2);
  assert.deepEqual(f.publicationOperations, ['push', 'observe', 'observe', 'push', 'observe']);
});

test('recovery does not push when the last authority/comment/ref observation changes or the reservation cannot be written', async t => {
  const f = await uncertain(t); const { request, comment } = await f.authorize();
  const wrap = modify => createPublicationBroker({ api: f.api, store: f.store,
    publisher: { inspect: (e, bundle, fn) => f.publisher.inspect(e, bundle, g => fn(modify(g))) } });
  const originalBody = f.issue.body;
  await assert.rejects(wrap(g => { f.issue.body += '\nChanged during inspection.'; return g; }).dispatch(request), { code: 'AUTHORITY_CHANGED' });
  f.issue.body = originalBody;
  const authorization = comment.body;
  await assert.rejects(wrap(g => { comment.body = 'Revoked'; return g; }).dispatch(request), { code: 'RECOVERY_OWNER_AUTHORIZATION_INVALID' });
  comment.body = authorization;
  await assert.rejects(wrap(g => ({ ...g, observe: async () => 'f'.repeat(40) })).dispatch(request), { code: 'REMOTE_HEAD_CHANGED' });
  const store = { ...f.store, put: async () => { throw Object.assign(new Error('reservation write failed'), { code: 'EIO' }); } };
  await assert.rejects(createPublicationBroker({ api: f.api, publisher: f.publisher, store }).dispatch(request), { code: 'EIO' });
  const r = await f.store.get(99); r.padding = 'x'.repeat(510 * 1024); await f.store.put(99, r);
  await assert.rejects(f.broker.invoke(request), { code: 'ATTEMPT_RECORD_TOO_LARGE' });
  assert.equal(f.pushes(), 1);
});

test('a valid linear candidate that does not descend from the recorded previous publication is blocked', async t => {
  const f = await fixture(t, { remediation: true }); await f.prepare(f.envelope);
  const previous = await f.commit(); const p = await f.collect(f.envelope);
  await f.broker.invoke({ operation: 'publish-progress', runId: 99, attemptId: f.envelope.attemptId, bundle: p.bundle });
  const tree = await f.command(f.cwd, ['rev-parse', 'HEAD^{tree}']);
  const sibling = await f.command(f.cwd, ['commit-tree', tree, '-p', f.envelope.startHead, '-m', 'a different linear candidate'], f.identity);
  // These refs belong exclusively to the temporary fixture, never a live task.
  await f.command(f.cwd, ['update-ref', `refs/heads/${f.envelope.branch}`, sibling]);
  f.progress = await f.collect(f.envelope); ownerSurface(f);
  const r = await f.store.get(99); r.publicationIntent = { previous, head: sibling }; await f.store.put(99, r);
  const { request } = await f.authorize();
  await assert.rejects(f.broker.invoke(request), { code: 'RECOVERY_HISTORY_INVALID' }); assert.equal(f.pushes(), 1);
});

test('a nonzero recovery push with an exact successful observation reconciles without another push', async t => {
  const f = await uncertain(t); const { request } = await f.authorize();
  f.failPush({ afterPush: true, error: { details: { failureDiagnostic: {
    classification: 'GIT_TRANSPORT_FAILED', primaryCause: 'GIT_TRANSPORT_FAILED', operation: 'push', gitExitCode: 1,
    preview: 'connection reset after acceptance', bytes: 33, truncated: false
  } } } });
  const result = await f.broker.invoke(request);
  assert.equal(result.publishedHead, f.progress.head); assert.match(result.pushDiagnostic.preview, /after acceptance/);
  await f.broker.invoke(request); assert.equal(f.pushes(), 2);
});

for (const failedPush of [false, true]) {
  test(`ambiguous observation after a ${failedPush ? 'failed' : 'successful'} recovery push retains diagnostics and cannot retry`, async t => {
    const f = await uncertain(t); const { request } = await f.authorize();
    if (failedPush) f.failPush({ details: { failureDiagnostic: { primaryCause: 'GIT_REF_CONFLICT',
      operation: 'push', gitExitCode: 1, preview: 'remote: recovery push rejected' } } });
    let attempted = false;
    const broker = createPublicationBroker({ api: f.api, store: f.store,
      publisher: { inspect: (e, bundle, fn) => f.publisher.inspect(e, bundle, g => fn({ ...g,
        push: async () => { attempted = true; return g.push(); },
        observe: async () => {
          if (!attempted) return g.observe();
          throw { details: { failureDiagnostic: { primaryCause: 'GIT_TRANSPORT_FAILED', operation: 'ls-remote',
            gitExitCode: 128, preview: 'observation connection reset' } } };
        }
      })) } });
    await assert.rejects(broker.dispatch(request), { code: 'PUBLICATION_UNCERTAIN' });
    const r = await f.store.get(99); const failure = r.publicationRecoveries[0].result;
    assert.equal(failure.publishedHead, null); assert.equal(r.publicationIntent.head, f.progress.head);
    assert.match(failure.observationDiagnostic.preview, /connection reset/);
    assert.match(failure.failureDiagnostic.preview, failedPush ? /push rejected/ : /connection reset/);
    await assert.rejects(broker.dispatch(request), { code: 'PUBLICATION_UNCERTAIN' }); assert.equal(f.pushes(), 2);
  });
}

test('a crash after reservation consumes the authorization before any Git mutation', async t => {
  const f = await uncertain(t); const { request, binding } = await f.authorize();
  const store = createAttemptStore(join(f.root, 'durable-writer'));
  await store.put(99, { ...await f.store.get(99), publicationRecoveries: [
    { authorizationId: request.authorizationId, binding, reservedAt: new Date().toISOString(), result: null }
  ] });
  const broker = createPublicationBroker({ api: f.api, publisher: { inspect: () => assert.fail('must not import or push on reserved replay') }, store });
  await assert.rejects(broker.dispatch(request), { code: 'PUBLICATION_UNCERTAIN' });
  await assert.rejects(broker.dispatch(request), { code: 'PUBLICATION_UNCERTAIN' });
  assert.equal(f.pushes(), 1);
});

test('failed recovery requires a new owner decision and never discards earlier durable failure receipts', async t => {
  const f = await uncertain(t); const { request } = await f.authorize();
  const safe = { classification: 'GIT_AUTHORIZATION_REJECTED', primaryCause: 'GIT_AUTHORIZATION_REJECTED',
    operation: 'push', gitExitCode: 128, signal: 'SIGTERM', preview: 'remote: write access not granted', bytes: 32, truncated: false };
  f.failPush({ details: { failureDiagnostic: safe } });
  await assert.rejects(f.broker.invoke(request), { code: 'PUBLICATION_UNCERTAIN' });
  const failed = await f.store.get(99);
  assert.equal(failed.publicationIntent.head, f.progress.head);
  assert.equal(failed.publicationRecoveries[0].result.failureDiagnostic.preview, safe.preview);
  f.failPush(false);
  await assert.rejects(f.broker.invoke(request), { code: 'PUBLICATION_UNCERTAIN' });
  await assert.rejects(f.broker.invoke(f.ordinary), { code: 'PUBLICATION_UNCERTAIN' });
  assert.equal(f.pushes(), 2);
  const next = await f.authorize();
  assert.equal(next.binding.afterAuthorizationId, request.authorizationId);
  const fresh = structuredClone(next.comment);
  next.comment.created_at = next.comment.updated_at = f.run.updated_at;
  await assert.rejects(f.broker.invoke(next.request), { code: 'RECOVERY_OWNER_AUTHORIZATION_INVALID' });
  Object.assign(next.comment, fresh);
  await f.broker.invoke(next.request);
  await assert.rejects(f.broker.invoke(request), { code: 'PUBLICATION_UNCERTAIN' });
  assert.equal(f.pushes(), 3);
  assert.deepEqual((await f.store.get(99)).publicationRecoveries[0], failed.publicationRecoveries[0]);
});

for (const kind of ['identity', 'path', 'file-mode', 'secret', 'merge']) {
  test(`recovery retains trusted ${kind} validation for the recorded exact candidate`, async t => {
    const f = ownerSurface(await fixture(t, { remediation: true })); await f.prepare(f.envelope);
    if (kind === 'identity') {
      await writeFile(join(f.cwd, 'docs/work.md'), 'wrong author\n');
      await f.command(f.cwd, ['add', '.']); await f.command(f.cwd, ['commit', '-m', 'unowned']);
    } else if (kind === 'path') await f.commit('malformed:name.md');
    else if (kind === 'file-mode') {
      const blob = await f.command(f.cwd, ['hash-object', '-w', 'docs/work.md']);
      await f.command(f.cwd, ['update-index', '--add', '--cacheinfo', `120000,${blob},docs/link`]);
      await f.commit();
    } else if (kind === 'secret') {
      await f.commit('docs/work.md', `ghp_${'A'.repeat(30)}\n`); await f.commit('docs/work.md', 'removed\n');
    } else {
      const child = await f.commit(); const tree = await f.command(f.cwd, ['rev-parse', 'HEAD^{tree}']);
      const merge = await f.command(f.cwd, ['commit-tree', tree, '-p', child, '-p', f.envelope.startHead, '-m', 'merge'], f.identity);
      await f.command(f.cwd, ['update-ref', `refs/heads/${f.envelope.branch}`, merge]);
    }
    f.progress = await f.collect(f.envelope);
    const r = await f.store.get(99); r.publicationIntent = { previous: f.envelope.startHead, head: f.progress.head }; await f.store.put(99, r);
    const { request } = await f.authorize();
    const code = { identity: 'COMMIT_OWNERSHIP_INVALID', path: 'COMMIT_PATH_INVALID', 'file-mode': 'COMMIT_FILE_MODE_INVALID',
      secret: 'SECRET_PUBLICATION_SCAN_FAILED', merge: 'INTEGRATION_BASE_INVALID' }[kind];
    await assert.rejects(f.broker.invoke(request), { code }); assert.equal(f.pushes(), 0);
  });
}

function helperFailureSpawn(payload) {
  return () => {
    const child = new EventEmitter(); child.stdin = new PassThrough(); child.stdout = new PassThrough(); child.stderr = new PassThrough();
    queueMicrotask(() => { child.stderr.write(JSON.stringify(payload)); child.emit('close', 1, null); });
    return child;
  };
}

for (const remediation of [false, true]) {
  test(`the explicit ${remediation ? 'PR' : 'Issue'} recovery command continues the original readiness/Outcome without a new Codex call`, async t => {
    const f = await fixture(t, { remediation }); const journal = memoryStore(); let executions = 0;
    const execute = async () => {
      executions++; await f.commit('unanticipated-required-file.md');
      return { version: VERSION, attemptId: f.envelope.attemptId, child: 'started', containment: 'reaped',
        result: { status: 'success', summary: 'Task-required repository change preserved.', validation: ['focused local checks passed'] } };
    };
    f.failPush(true);
    await assert.rejects(runAttempt({ ...f, journal, execute }), { code: 'PUBLICATION_UNCERTAIN' });
    ownerSurface(f); f.progress = await f.collect(f.envelope); const { request } = await f.authorize();
    const outcomeId = (await f.store.get(99)).outcome.outcomeId;
    f.failPush(false);
    const args = { ...request, broker: f.broker, journal, collect: f.collect };
    const result = await recoverAttemptPublication(args);
    assert.equal(result.head, f.progress.head); assert.equal(result.status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
    assert.equal(result.outcomeId, outcomeId);
    assert.equal(f.comments.filter(c => c.user.login.endsWith('[bot]')).length, 1);
    assert.match(f.comments.find(c => c.id === outcomeId).body, /Status: IMPLEMENTED_PENDING_FRESH_REVIEW/);
    assert.match(f.comments.find(c => c.id === outcomeId).body, /Task-required repository change preserved/);
    assert.match(f.comments.find(c => c.id === outcomeId).body, /focused local checks passed/);
    assert.equal((await f.api.get('/pulls/43')).draft, false);
    assert.deepEqual(await recoverAttemptPublication({ ...args, collect: () => assert.fail('receipt replay recollected') }), result);
    assert.equal((await runAttempt({ ...f, journal, execute })).head, result.head);
    assert.equal(executions, 1); assert.equal(f.pushes(), 2);
  });
}

test('an ambiguous Outcome update resumes by observation of the same comment without another push', async t => {
  const f = await fixture(t, { remediation: true }); const journal = memoryStore(); f.failPush(true);
  await assert.rejects(runAttempt({ ...f, journal, execute: async () => {
    await f.commit(); return { version: VERSION, attemptId: f.envelope.attemptId, child: 'started', containment: 'reaped', result: { status: 'success' } };
  } }), { code: 'PUBLICATION_UNCERTAIN' });
  ownerSurface(f); f.progress = await f.collect(f.envelope); const { request } = await f.authorize(); f.failPush(false);
  const patch = f.api.patch.bind(f.api); let patches = 0;
  f.api.patch = async (...args) => { patches++; await patch(...args); throw Object.assign(new Error('response lost'), { code: 'GITHUB_REQUEST_FAILED' }); };
  const args = { ...request, broker: f.broker, journal, collect: f.collect };
  await assert.rejects(recoverAttemptPublication(args), { code: 'GITHUB_REQUEST_FAILED' });
  assert.equal((await recoverAttemptPublication(args)).status, 'IMPLEMENTED_PENDING_FRESH_REVIEW');
  assert.equal(patches, 1); assert.equal(f.pushes(), 2);
});

test('recovery failure preview survives the durable store, helper wire and terminal JSON with explicit truncation', async t => {
  const f = await fixture(t, { remediation: true }); const journal = memoryStore(); f.failPush(true);
  await assert.rejects(runAttempt({ ...f, journal, execute: async () => {
    await f.commit(); return { version: VERSION, attemptId: f.envelope.attemptId, child: 'started', containment: 'reaped', result: { status: 'success' } };
  } }), { code: 'PUBLICATION_UNCERTAIN' });
  ownerSurface(f); f.progress = await f.collect(f.envelope); const { request } = await f.authorize();
  const store = createAttemptStore(join(f.root, 'durable-writer')); await store.put(99, await f.store.get(99));
  const real = createPublicationBroker({ api: f.api, publisher: f.publisher, store });
  const token = `ghp_${'Z'.repeat(35)}`;
  const basic = Buffer.from('x-access-token:synthetic-not-secret').toString('base64');
  const raw = `remote: permission denied; Authorization: Basic ${basic}; Bearer synthetic-value; token=${token}; ${'useful causal text é '.repeat(200)}`;
  const safe = boundedDiagnosticText(raw, 2048);
  f.failPush({ details: { failureDiagnostic: { classification: 'GIT_AUTHORIZATION_REJECTED', primaryCause: 'GIT_AUTHORIZATION_REJECTED',
    operation: 'push', gitExitCode: 128, signal: 'SIGTERM', preview: safe.text, bytes: safe.bytes, truncated: safe.truncated } } });
  f.failObserve(null);
  const broker = { invoke: async value => {
    try { return await real.dispatch(value); }
    catch (error) { return createLocalWriterAdapter({ spawnImpl: helperFailureSpawn(serializeWriterFailure(error)) }).invoke(value); }
  } };
  let terminal = '';
  const args = { ...request, broker, journal, collect: f.collect };
  assert.equal(await reportRoutingResult(() => recoverAttemptPublication(args), { write: text => { terminal += text; }, writeError: text => { terminal += text; } }), 1);
  const disk = JSON.parse(await readFile(join(f.root, 'durable-writer/99.json'), 'utf8'));
  const d = disk.publicationRecoveries[0].result.failureDiagnostic;
  assert.match(d.preview, /permission denied/); assert.match(d.preview, /useful causal text/);
  assert.equal(d.bytes, safe.bytes); assert.equal(d.truncated, true); assert.equal(d.signal, 'SIGTERM'); assert.equal(d.gitExitCode, 128);
  assert.ok(Buffer.byteLength(d.preview) <= 2048);
  assert.deepEqual(JSON.parse(terminal).diagnostic.publicationRecovery, d);
  for (const value of [token, basic, 'synthetic-value']) {
    assert.ok(!JSON.stringify(disk).includes(value)); assert.ok(!terminal.includes(value));
  }
  f.failPush(false);
  await assert.rejects(recoverAttemptPublication({ ...args, collect: () => assert.fail('consumed failure recollected') }), { code: 'PUBLICATION_UNCERTAIN' });
  assert.equal(f.pushes(), 2);
});

test('safe Git projection keeps UTF-8 byte bounds and the original truncation metadata across repeated projections', () => {
  const value = { code: 'TRUSTED_GIT_FAILED', operation: 'push', preview: 'é'.repeat(1500), bytes: 9000, truncated: true };
  const d = failureDiagnosticFromDetails({ failureDiagnostic: value });
  assert.equal(Buffer.byteLength(d.preview), 2048); assert.equal(d.bytes, 9000); assert.equal(d.truncated, true);
  assert.deepEqual(failureDiagnosticFromDetails({ failureDiagnostic: d }), d);
});

test('a real rejecting Git remote supplies the sanitized durable recovery preview', async t => {
  const f = await uncertain(t); const { request } = await f.authorize();
  const token = `ghp_${'S'.repeat(35)}`;
  const hook = join(f.remote, 'hooks/pre-receive');
  await writeFile(hook, `#!/bin/sh\nprintf '%s\\n' 'permission denied; token=${token}; ${'server policy detail '.repeat(200)}' >&2\nexit 1\n`);
  await chmod(hook, 0o755);
  await assert.rejects(f.broker.invoke(request), error => {
    assert.equal(error.code, 'PUBLICATION_UNCERTAIN');
    assert.equal(error.details.failureDiagnostic.primaryCause, 'GIT_AUTHORIZATION_REJECTED');
    return true;
  });
  const result = (await f.store.get(99)).publicationRecoveries[0].result;
  assert.match(result.failureDiagnostic.preview, /permission denied/);
  assert.match(result.failureDiagnostic.preview, /server policy detail/);
  assert.equal(result.failureDiagnostic.truncated, true);
  assert.equal(result.failureDiagnostic.gitExitCode, 1);
  assert.ok(!JSON.stringify(result).includes(token));
  assert.equal(await f.remoteHead(), f.envelope.startHead); assert.equal(f.pushes(), 2);
});

test('recovery cannot finish a blocked child or a changed/dirty checkout, and missing execution evidence cannot push', async t => {
  const f = await fixture(t, { remediation: true }); const journal = memoryStore(); f.failPush(true);
  await assert.rejects(runAttempt({ ...f, journal, execute: async () => {
    await f.commit(); return { version: VERSION, attemptId: f.envelope.attemptId, child: 'started', containment: 'reaped', result: { status: 'blocked' } };
  } }), { code: 'PUBLICATION_UNCERTAIN' });
  ownerSurface(f); f.progress = await f.collect(f.envelope); const { request } = await f.authorize(); f.failPush(false);
  const args = { ...request, broker: f.broker, journal, collect: f.collect };
  await assert.rejects(recoverAttemptPublication({ ...args, journal: memoryStore() }), { code: 'JOURNAL_BINDING_CHANGED' });
  const r = await journal.get(99); r.execution.containment = 'unknown'; await journal.put(99, r);
  await assert.rejects(recoverAttemptPublication(args), { code: 'RECOVERY_EXECUTION_NOT_PROVEN' }); assert.equal(f.pushes(), 1);
  r.execution.containment = 'reaped'; await journal.put(99, r);
  await assert.rejects(recoverAttemptPublication(args), { code: 'SEMANTIC_RESULT_BLOCKED' });
  assert.equal((await f.api.get('/pulls/43')).draft, true); assert.equal(f.pushes(), 2);
  await writeFile(join(f.cwd, 'docs/work.md'), 'uncommitted changes');
  await assert.rejects(recoverAttemptPublication(args), { code: 'UNCOMMITTED_WORK_REMAINS' });
  await f.commit('docs/work.md', 'new unauthorized candidate');
  await assert.rejects(recoverAttemptPublication(args), { code: 'RECOVERY_CANDIDATE_CHANGED' }); assert.equal(f.pushes(), 2);
});
