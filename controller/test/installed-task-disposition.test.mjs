import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { CONSUMER } from '../../consumer/consumer.mjs';
import { renderAuthorityRecord, sha256Body } from '../../contracts/src/github-authority.mjs';
import { createNativeTaskDispositionReader, createProtectedDispositionCache } from '../src/installed-task-disposition.mjs';

const repository = CONSUMER.repository;
const owner = { login: CONSUMER.owner, id: 100, type: 'User' };
const reviewer = { login: CONSUMER.reviewerApp.expectedActor, id: 101, type: 'Bot' };
const body = 'Authority model: github-native-v1\nIssue closure policy: keep-open';
const parent = { kind: 'issue', number: 42 };
function decision(id, supersedes = null) {
  const record = { schema_version: '4.0', kind: 'decision', repository, task: 42, parent,
    charter_sha256: sha256Body(body), purpose: 'Withdraw a particular abandoned manual route.',
    amendments: { boundaries: ['No relaunch or fabricated completion.'] }, context: [], supersedes };
  return { id, issue_url: `https://api.github.com/repos/${repository}/issues/42`, user: reviewer,
    body: renderAuthorityRecord(record) };
}
function fixture() {
  const issue = { id: 900, number: 42, body, state: 'closed', state_reason: 'completed', closed_by: owner,
    url: `https://api.github.com/repos/${repository}/issues/42` };
  const events = [{ id: 901, event: 'closed', actor: owner, created_at: '2026-11-03T10:00:00Z' }];
  const comments = [];
  const calls = [];
  const read = createNativeTaskDispositionReader({ tokenFor: async selected => {
    assert.equal(selected, repository); return 'synthetic-read-token';
  }, fetchImpl: async (url, options) => {
    calls.push(url); assert.equal(options.headers.authorization, 'Bearer synthetic-read-token');
    const path = new URL(url).pathname;
    const values = {
      [`/repos/${repository}/issues/42`]: issue,
      [`/repos/${repository}/issues/42/events`]: events,
      [`/repos/${repository}/issues/42/comments`]: comments,
      [`/users/${encodeURIComponent(owner.login)}`]: owner,
      [`/users/${encodeURIComponent(reviewer.login)}`]: reviewer
    };
    assert.ok(Object.hasOwn(values, path), path);
    return { ok: true, json: async () => structuredClone(values[path]) };
  } });
  return { read, issue, events, comments, calls };
}

test('native lifecycle reader binds repository, native owner, lifecycle and trusted active Decision bytes', async () => {
  const f = fixture(); const first = decision(903);
  const ref = { kind: 'issue-comment', id: 903, parent, sha256: sha256Body(first.body) };
  f.comments.push(first, decision(904, ref), { ...decision(905), user: { ...reviewer, id: 999 } });
  const value = await f.read(repository, 42);
  assert.deepEqual(value.owner, owner); assert.deepEqual(value.lifecycle, f.events);
  assert.deepEqual(value.decisions.map(item => item.reference.id), [904]);
  assert.deepEqual(value.authority.map(item => item.reference.id), [903, 904]);
  assert.equal(value.decisions[0].body, f.comments[1].body);
  f.issue.state = 'open'; f.issue.state_reason = 'reopened'; f.issue.closed_by = null;
  f.events.push({ id: 906, event: 'reopened', actor: owner, created_at: '2026-11-03T10:01:00Z' });
  assert.equal((await f.read(repository, 42)).issue.state, 'open');
});

test('native reader cannot expand the configured repository allowlist or accept a PR/wrong native Issue', async () => {
  const f = fixture();
  await assert.rejects(f.read('foreign/repository', 42), { code: 'HISTORICAL_TASK_REPOSITORY_MISMATCH' });
  assert.equal(f.calls.length, 0);
  f.issue.pull_request = {};
  await assert.rejects(f.read(repository, 42), { code: 'HISTORICAL_TASK_AUTHORITY_INVALID' });
  delete f.issue.pull_request; f.issue.url = 'https://api.github.com/repos/foreign/repository/issues/42';
  await assert.rejects(f.read(repository, 42), { code: 'HISTORICAL_TASK_AUTHORITY_INVALID' });
});

test('native reader rejects edited supersession bindings and ambiguous trusted forks', async () => {
  const f = fixture(); const first = decision(903);
  const ref = { kind: 'issue-comment', id: 903, parent, sha256: sha256Body(first.body) };
  f.comments.push(first, decision(904, ref), decision(905, ref));
  await assert.rejects(f.read(repository, 42), { code: 'HISTORICAL_TASK_AUTHORITY_INVALID' });
  f.comments.pop(); first.body += '\nEdited historical source';
  await assert.rejects(f.read(repository, 42), { code: 'HISTORICAL_TASK_AUTHORITY_INVALID' });
});

test('unavailable native status fails explicitly with no cached/offline bypass', async () => {
  const read = createNativeTaskDispositionReader({ tokenFor: async () => 'synthetic',
    fetchImpl: async () => ({ ok: false }) });
  await assert.rejects(read(repository, 42), { code: 'HISTORICAL_TASK_AUTHORITY_UNAVAILABLE' });
});

test('durable acknowledgement cache is repository/run scoped and keeps private files across a fresh adapter', async t => {
  const root = await mkdtemp(join(tmpdir(), 'relay-historical-cache-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const options = { root, repositories: [repository], protectedRoot: false };
  const key = `${repository}:32`, value = { version: 1, reason: 'route-switch', evidenceDigest: 'a'.repeat(64) };
  const cache = createProtectedDispositionCache(options);
  assert.equal(await cache.get(key), null);
  await cache.set(key, value);
  assert.deepEqual(await createProtectedDispositionCache(options).get(key), value);
  assert.deepEqual(JSON.parse(await readFile(join(root, 'historical-manual-dispositions-v1/repositories', repository, '32.json'))), value);
  await assert.rejects(cache.get('foreign/repository:32'), { code: 'HISTORICAL_TASK_CACHE_INVALID' });
});
