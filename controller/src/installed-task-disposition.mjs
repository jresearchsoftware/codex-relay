import { constants } from 'node:fs';
import { lstat, open, mkdir } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { INSTALLATION_CONSUMER } from '../../consumer/consumer.mjs';
import { configuredRepositories } from '../../consumer/consumer-config.mjs';
import { extractAuthorityRecord, nativeReference, canonicalAuthorityJson } from '../../contracts/src/github-authority.mjs';
import { createAttemptStore } from './attempt-store.mjs';
import { createHistoricalTaskDisposition } from './historical-task-disposition.mjs';
import { taskReadToken } from './writer-auth.mjs';
import { fail } from './execution-contract.mjs';

const same = (a, b) => canonicalAuthorityJson(a) === canonicalAuthorityJson(b);
const positive = n => Number.isSafeInteger(n) && n > 0;
const identity = value => value && { login: value.login, id: value.id, type: value.type };

// Native reads use the existing protected Writer App, with repository-scoped
// metadata, Issue and PR read permissions only. The allowlist includes an original consumer only
// after the caller has authenticated its retained compatibility envelope.
export function createNativeTaskDispositionReader({ consumer = INSTALLATION_CONSUMER,
  historicalConsumer = null, fetchImpl = fetch, tokenFor = taskReadToken } = {}) {
  const repositories = [...new Set([...configuredRepositories(consumer),
    ...(historicalConsumer ? configuredRepositories(historicalConsumer) : [])])];
  const tokens = new Map();
  async function request(repository, path, global = false) {
    if (!repositories.includes(repository)) fail('HISTORICAL_TASK_REPOSITORY_MISMATCH');
    let response;
    try {
      if (!tokens.has(repository)) tokens.set(repository, await tokenFor(repository));
      response = await fetchImpl(`https://api.github.com/${global ? path : `repos/${repository}/${path}`}`, {
        headers: { accept: 'application/vnd.github+json', authorization: `Bearer ${tokens.get(repository)}`,
          'x-github-api-version': '2022-11-28' }, signal: AbortSignal.timeout(15000) });
    } catch { fail('HISTORICAL_TASK_AUTHORITY_UNAVAILABLE'); }
    if (!response.ok) fail('HISTORICAL_TASK_AUTHORITY_UNAVAILABLE');
    try { return await response.json(); } catch { fail('HISTORICAL_TASK_AUTHORITY_INVALID'); }
  }
  async function list(repository, path) {
    const rows = [];
    for (let page = 1; page <= 100; page++) {
      const next = await request(repository, `${path}?per_page=100&page=${page}`);
      if (!Array.isArray(next)) fail('HISTORICAL_TASK_AUTHORITY_INVALID');
      rows.push(...next);
      if (next.length < 100) return rows;
    }
    fail('HISTORICAL_TASK_AUTHORITY_INCOMPLETE');
  }
  return async (repository, task, record) => {
    if (!repositories.includes(repository) || !positive(task)) fail('HISTORICAL_TASK_REPOSITORY_MISMATCH');
    const policy = historicalConsumer && configuredRepositories(historicalConsumer).includes(repository)
      && !configuredRepositories(consumer).includes(repository) ? historicalConsumer : consumer;
    const issue = await request(repository, `issues/${task}`);
    if (issue.number !== task || !positive(issue.id) || issue.pull_request
      || issue.url !== `https://api.github.com/repos/${repository}/issues/${task}`
      || typeof issue.body !== 'string') fail('HISTORICAL_TASK_AUTHORITY_INVALID');
    const owner = identity(await request(repository, `users/${encodeURIComponent(policy.owner)}`, true));
    if (owner.login !== policy.owner || owner.type !== 'User' || !positive(owner.id)) fail('HISTORICAL_TASK_AUTHORITY_INVALID');
    const lifecycle = (await list(repository, `issues/${task}/events`))
      .filter(event => ['closed', 'reopened'].includes(event.event))
      .map(event => ({ id: event.id, event: event.event, actor: identity(event.actor), created_at: event.created_at }));
    const reviewer = identity(await request(repository, `users/${encodeURIComponent(policy.reviewerApp.expectedActor)}`, true));
    if (reviewer.login !== policy.reviewerApp.expectedActor || reviewer.type !== 'Bot' || !positive(reviewer.id))
      fail('HISTORICAL_TASK_AUTHORITY_INVALID');
    const decisions = [], authority = [], pullRequests = new Set();
    const envelope = record?.envelope;
    if (envelope && (envelope.repository !== repository || envelope.issueNumber !== task))
      fail('HISTORICAL_TASK_REPOSITORY_MISMATCH');
    if (envelope?.target === 'pull_request' && positive(envelope.number)) pullRequests.add(envelope.number);
    if (positive(envelope?.continuation?.pullRequest)) pullRequests.add(envelope.continuation.pullRequest);
    if (positive(envelope?.request?.existing_pr)) pullRequests.add(envelope.request.existing_pr);
    for (const comment of await list(repository, `issues/${task}/comments`)) {
      if (!same(identity(comment.user), reviewer) || !/^```relay-authority/m.test(comment.body ?? '')) continue;
      if (!positive(comment.id) || comment.issue_url !== issue.url) fail('HISTORICAL_TASK_AUTHORITY_INVALID');
      const payload = extractAuthorityRecord(comment.body, { repository, task });
      if (!payload || payload.parent.kind !== 'issue' || payload.parent.number !== task) continue;
      const native = { kind: 'issue-comment', id: comment.id, repository,
        parent: { kind: 'issue', number: task }, author: comment.user, body: comment.body };
      authority.push({ reference: nativeReference(native), body: comment.body });
      if (positive(payload.existing_pr)) pullRequests.add(payload.existing_pr);
      if (positive(payload.amendments?.existing_pr)) pullRequests.add(payload.amendments.existing_pr);
      if (payload.kind !== 'decision') continue;
      decisions.push({ reference: nativeReference(native), body: comment.body, payload });
    }
    const superseded = new Set();
    for (const item of decisions) if (item.payload.supersedes) {
      const previous = decisions.find(candidate => same(candidate.reference, item.payload.supersedes));
      if (!previous || previous.reference.id >= item.reference.id || superseded.has(previous.reference.id))
        fail('HISTORICAL_TASK_AUTHORITY_INVALID');
      superseded.add(previous.reference.id);
    }
    const artifacts = [];
    for (const number of [...pullRequests].sort((a, b) => a - b)) {
      const pr = await request(repository, `pulls/${number}`);
      if (pr.number !== number || pr.base?.repo?.full_name !== repository || pr.head?.repo?.full_name !== repository
        || typeof pr.head.sha !== 'string') fail('HISTORICAL_TASK_AUTHORITY_INVALID');
      const records = [];
      for (const [path, kind] of [[`issues/${number}/comments`, 'issue-comment'], [`pulls/${number}/reviews`, 'review']]) {
        for (const item of await list(repository, path)) {
          if (!same(identity(item.user), reviewer)) continue;
          const typed = /^```relay-authority/m.test(item.body ?? '');
          if (!typed && kind !== 'review') continue;
          if (typed) {
            const payload = extractAuthorityRecord(item.body, { repository, task });
            if (!payload || payload.parent.kind !== 'pull_request' || payload.parent.number !== number)
              fail('HISTORICAL_TASK_AUTHORITY_INVALID');
          }
          // Retained legacy CRs have no relay-authority fence. Native review
          // body/state/head are still exact authority evidence, including a
          // dismissal, even though this reader does not execute that old CR.
          const native = { kind, id: item.id, repository, parent: { kind: 'pull_request', number }, body: item.body ?? '' };
          records.push({ reference: nativeReference(native), body: item.body ?? '', state: item.state ?? null,
            commit_id: item.commit_id ?? null });
        }
      }
      artifacts.push({ number, state: pr.state, head: pr.head.sha, body: pr.body ?? '',
        baseRef: pr.base.ref ?? null, headRef: pr.head.ref ?? null,
        author: identity(pr.user) ?? null, records });
    }
    return { repository, task, owner, lifecycle, artifacts, authority: authority.sort((a, b) => a.reference.id - b.reference.id),
      issue: { id: issue.id, number: issue.number, state: issue.state, state_reason: issue.state_reason,
        body: issue.body, closed_by: identity(issue.closed_by) },
      decisions: decisions.filter(item => !superseded.has(item.reference.id)).sort((a, b) => a.reference.id - b.reference.id)
        .map(({ reference, body }) => ({ reference, body })) };
  };
}

export function createProtectedDispositionCache({ root, repositories, protectedRoot = true }) {
  const cacheRoot = join(root, 'historical-manual-dispositions-v1');
  function selection(key) {
    const split = key.lastIndexOf(':'); const repository = key.slice(0, split), runId = Number(key.slice(split + 1));
    if (!repositories.includes(repository) || !positive(runId)) fail('HISTORICAL_TASK_CACHE_INVALID');
    return { repository, runId, path: join(cacheRoot, 'repositories', ...repository.split('/'), `${runId}.json`),
      store: createAttemptStore(join(cacheRoot, 'repositories', ...repository.split('/')), { repository }) };
  }
  async function protect(path, file = false) {
    if (!protectedRoot) return;
    for (let at = path; ; at = dirname(at)) {
      const info = await lstat(at);
      if (info.isSymbolicLink() || info.uid !== 0 || info.mode & 0o022
        || (at === path && file ? !info.isFile() || info.nlink !== 1 || info.mode & 0o077 || info.size > 512 * 1024
          : !info.isDirectory())) fail('HISTORICAL_TASK_CACHE_UNSAFE');
      if (at === '/') return;
    }
  }
  return {
    async get(key) {
      const chosen = selection(key);
      try { await protect(chosen.path, true); }
      catch (error) { if (error.code === 'ENOENT') return null; throw error; }
      // Read through NOFOLLOW as well as validating the whole protected chain.
      let file;
      try { file = await open(chosen.path, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK); }
      catch (error) { if (error.code === 'ENOENT') return null; throw error; }
      try { return JSON.parse(await file.readFile('utf8')); }
      catch { fail('HISTORICAL_TASK_CACHE_INVALID'); }
      finally { await file.close(); }
    },
    async set(key, value) {
      const chosen = selection(key);
      await protect(root);
      // Parent directories are fixed descendants of the protected claim root.
      let at = root;
      for (const part of ['historical-manual-dispositions-v1', 'repositories', ...chosen.repository.split('/')]) {
        at = join(at, part); await mkdir(at, { mode: 0o700 }).catch(error => { if (error.code !== 'EEXIST') throw error; });
        await protect(at);
      }
      await chosen.store.put(chosen.runId, value);
    }
  };
}

export function createInstalledTaskDisposition({ consumer = INSTALLATION_CONSUMER, historicalConsumer = null,
  allowAcknowledgement = false, ...options } = {}) {
  if (allowAcknowledgement && process.getuid?.() !== 0) fail('HISTORICAL_TASK_ACKNOWLEDGEMENT_FORBIDDEN');
  const repositories = [...new Set([...configuredRepositories(consumer),
    ...(historicalConsumer ? configuredRepositories(historicalConsumer) : [])])];
  return createHistoricalTaskDisposition({
    readTask: createNativeTaskDispositionReader({ consumer, historicalConsumer, ...options }),
    cache: createProtectedDispositionCache({ root: consumer.paths.claimRoot, repositories }), allowAcknowledgement });
}
