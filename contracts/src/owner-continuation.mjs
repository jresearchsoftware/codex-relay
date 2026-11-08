import { homedir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { lstat, mkdir } from 'node:fs/promises';
import { createAttemptStore } from '../../controller/src/attempt-store.mjs';
import { loadConsumer, parseConsumerJson, selectRepositoryConsumer } from '../../consumer/consumer-config.mjs';
import { canonicalAuthorityJson, sha256Body } from './github-authority.mjs';
import { continueAfterApproval } from './post-review-continuation.mjs';
import { createOwnerGithub, createOwnerNativeReader, reject, validateOwnerRequest } from './owner-native.mjs';

const same = (a, b) => canonicalAuthorityJson(a) === canonicalAuthorityJson(b);
const sha = value => typeof value === 'string' && /^[a-f0-9]{40}$/.test(value);

// This entrypoint belongs to the authenticated owner caller. The transient
// assessment records that caller's interpretation, bound to native authority;
// it is not a Decision, Task amendment, approval or worker result transport.
export async function runOwnerContinuation(request, { consumer, api = createOwnerGithub(),
  storeRoot = join(homedir(), '.codex', 'relay-owner-actions') } = {}) {
  validateOwnerRequest(request);
  if (!consumer || consumer.repository !== request.repository) reject('OWNER_REPOSITORY_NOT_CONFIGURED');
  // GitHub's squash endpoint offers an atomic head comparison, not an atomic
  // base comparison. Refuse a required exact-base guarantee before any intent
  // or external effect rather than detecting its violation after a merge.
  if (request.owner_assessment.exact_base_sha) reject('OWNER_EXACT_BASE_CAPABILITY_UNAVAILABLE');
  const reader = createOwnerNativeReader({ api, consumer, request });
  // Identity/authority refusal occurs before any local intent reservation.
  const initial = await reader.read();
  const directory = join(storeRoot, 'repositories', ...request.repository.split('/'));
  for (let path = resolve(directory); ; path = dirname(path)) {
    try {
      const info = await lstat(path);
      if (!info.isDirectory() || info.isSymbolicLink()) reject('OWNER_JOURNAL_UNSAFE');
    } catch (error) { if (error.code !== 'ENOENT') throw error; }
    if (dirname(path) === path) break;
  }
  await mkdir(directory, { recursive: true, mode: 0o700 });
  // The journal is owner-local and never a worker path. Reject redirected
  // records/namespaces before using the shared atomic-write/lock primitives.
  for (const path of [storeRoot, join(storeRoot, 'repositories'), join(storeRoot, 'repositories', request.repository.split('/')[0]), directory]) {
    const info = await lstat(path);
    if (!info.isDirectory() || info.isSymbolicLink()) reject('OWNER_JOURNAL_UNSAFE');
  }
  const store = createAttemptStore(storeRoot, { repository: request.repository, namespace: true });
  return store.withLock(request.approval.id, async () => {
    try {
      const info = await lstat(join(directory, `${request.approval.id}.json`));
      if (!info.isFile() || info.isSymbolicLink() || info.nlink !== 1 || info.size > 512 * 1024) reject('OWNER_JOURNAL_UNSAFE');
    } catch (error) { if (error.code !== 'ENOENT') throw error; }
    let journal = await store.get(request.approval.id);
    let persisted = journal !== null;
    const binding = { request, owner: consumer.owner };
    if (journal && (Object.keys(journal).length !== 2 || !journal.actions || Array.isArray(journal.actions)
      || typeof journal.actions !== 'object' || Object.keys(journal.actions).length > 1)) reject('OWNER_JOURNAL_INVALID');
    const retained = journal?.binding?.request;
    if (journal) {
      try { validateOwnerRequest(retained); } catch { reject('OWNER_JOURNAL_INVALID'); }
      if (retained.repository !== request.repository || retained.approval.id !== request.approval.id
        || journal.binding.owner !== consumer.owner) reject('OWNER_JOURNAL_INVALID');
    }
    for (const [operationId, entry] of Object.entries(journal?.actions ?? {})) {
      const action = entry?.action;
      if (!action || Object.keys(entry).length !== 2 || operationId !== sha256Body(canonicalAuthorityJson(action))
        || action.kind !== 'squash-merge' || action.repository !== retained.repository || action.task !== retained.task
        || action.pullRequest !== retained.pull_request || !same(action.approval, retained.approval)
        || action.expectedHeadSha !== retained.expected_head_sha || !sha(action.expectedBaseSha)
        || !['pending', 'uncertain', 'not-started', 'verified'].includes(entry.result?.status)
        || entry.result.status === 'verified' && !sha(entry.result.mergeCommitSha)) reject('OWNER_JOURNAL_INVALID');
    }
    const hasEffectIntent = Object.values(journal?.actions ?? {}).some(entry => entry.result.status !== 'not-started');
    if (journal && !same(journal.binding, binding)) {
      if (hasEffectIntent) reject('OWNER_ACTION_BINDING_CHANGED');
      journal = { binding, actions: {} };
    }
    if (initial.state.pr.merged && !hasEffectIntent) reject('OWNER_MERGE_INTENT_REQUIRED');
    journal ??= { binding, actions: {} };
    const save = async () => {
      if (persisted) return store.put(request.approval.id, journal);
      if (!await store.reserve(request.approval.id, journal)) reject('OWNER_ACTION_BUSY');
      persisted = true;
    };
    async function reconcile(action) {
      const fresh = await reader.read();
      if (fresh.state.pr.merged !== true) return null;
      const pr = await api(`${reader.prefix}/pulls/${request.pull_request}`);
      reader.checkTarget(pr);
      if (pr.merged !== true || !sha(pr.merge_commit_sha) || pr.merged_by?.login !== consumer.owner
        || pr.merged_by?.type !== 'User' || pr.merged_by?.id !== fresh.state.binding.trustedOwner.id) reject('OWNER_MERGE_UNVERIFIED');
      const commit = await api(`${reader.prefix}/commits/${pr.merge_commit_sha}`);
      if (commit.sha !== pr.merge_commit_sha || commit.parents?.length !== 1
        || commit.parents[0].sha !== action.expectedBaseSha) reject('OWNER_SQUASH_UNVERIFIED');
      return { status: 'verified', mergeCommitSha: pr.merge_commit_sha };
    }
    const ports = {
      readCanonicalState: async () => (await reader.read()).state,
      reserveAction: async ({ operationId, action }) => {
        if (action.kind !== 'squash-merge' || operationId !== sha256Body(canonicalAuthorityJson(action))) reject('OWNER_ACTION_INVALID');
        const existing = journal.actions[operationId];
        if (existing && !same(existing.action, action)) reject('OWNER_ACTION_BINDING_CHANGED');
        if (existing?.result?.status === 'verified') return { status: 'completed', operationId, result: existing.result };
        if (existing && existing.result?.status !== 'not-started') {
          const result = await reconcile(action);
          if (!result) return { status: 'uncertain', operationId };
          journal.actions[operationId].result = result;
          await save();
          return { status: 'completed', operationId, result };
        }
        // A preflight refusal proves there was no external effect. It needs no
        // growing local history when a later safe base/readiness is observed.
        for (const [key, entry] of Object.entries(journal.actions)) if (entry.result.status === 'not-started') delete journal.actions[key];
        journal.actions[operationId] = { action, result: { status: 'pending' } };
        await save();
        return { status: 'reserved', operationId };
      },
      recordActionResult: async ({ operationId, action, result }) => {
        if (!journal.actions[operationId] || !same(journal.actions[operationId].action, action)) reject('OWNER_ACTION_BINDING_CHANGED');
        journal.actions[operationId].result = result ?? { status: 'uncertain' };
        await save();
      },
      mergeSquash: async action => {
        // Reauthenticate and re-read the same native head/authority/checks at
        // the mutation boundary. The shared helper also checks after reservation.
        try {
          const fresh = await reader.read();
          if (fresh.state.task.hold || fresh.state.task.protectedBoundary || fresh.state.pr.baseSha !== action.expectedBaseSha
            || fresh.state.pr.merged !== false || fresh.state.pr.state !== 'open'
            || fresh.state.pr.closesTask !== false || fresh.state.pr.readiness !== 'ready' || fresh.state.pr.mergeability !== 'clean'
            || fresh.state.pr.requiredChecks.some(check => check.headSha !== action.expectedHeadSha
              || check.status !== 'completed' || !['success', 'neutral', 'skipped'].includes(check.conclusion))) reject('OWNER_MERGE_GUARD_CHANGED');
        } catch (error) { return { status: 'not-started', reason: error.code ?? 'OWNER_NATIVE_UNAVAILABLE' }; }
        try {
          const result = await api(`${reader.prefix}/pulls/${request.pull_request}/merge`, { method: 'PUT', body: {
            merge_method: 'squash', sha: action.expectedHeadSha, commit_title: action.commitTitle, commit_message: action.commitBody } });
          if (result.merged !== true || !sha(result.sha)) return { status: 'uncertain' };
          const observed = await reconcile(action);
          return observed?.mergeCommitSha === result.sha ? observed : { status: 'uncertain' };
        } catch {
          // A possibly accepted PUT is never repeated. The existing intent is
          // retained before bounded authoritative native reconciliation.
          return await reconcile(action) ?? { status: 'uncertain' };
        }
      }
    };
    // A prior lost response can leave the PR merged before the helper is
    // entered again. Reconcile the exact frozen intent before accepting that
    // native fact; never erase an unresolved old mutation with a fresh receipt.
    const recovered = [];
    for (const [operationId, entry] of Object.entries(journal.actions)) {
      if (entry.result?.status === 'not-started') continue;
      const result = await reconcile(entry.action);
      if (!result) return { status: 'stopped', reason: 'CONTINUATION_ACTION_UNCERTAIN', actions: [] };
      if (entry.result?.status === 'verified') {
        if (!same(entry.result, result)) reject('OWNER_MERGE_UNVERIFIED');
        continue;
      }
      entry.result = result; await save();
      recovered.push({ kind: entry.action.kind, operationId, status: 'already-completed', result });
    }
    const result = await continueAfterApproval(initial.receipt, ports, { mergeOnly: true });
    return { ...result, actions: [...recovered, ...result.actions],
      task_continuation: 'OWNER_INTERPRETATION_CAPABILITY_REQUIRED' };
  });
}

export async function ownerContinuationMain({ input = process.stdin, output = process.stdout } = {}) {
  if (process.argv.length !== 2) reject('OWNER_CONTINUATION_INPUT_INVALID');
  let raw = '';
  for await (const part of input) {
    raw += part;
    if (Buffer.byteLength(raw) > 16000) reject('OWNER_CONTINUATION_INPUT_INVALID');
  }
  let request;
  try { request = parseConsumerJson(raw); } catch { reject('OWNER_CONTINUATION_INPUT_INVALID'); }
  validateOwnerRequest(request);
  const installation = loadConsumer(process.env.RELAY_CONSUMER_CONFIG);
  const consumer = selectRepositoryConsumer(installation, request.repository);
  const result = await runOwnerContinuation(request, { consumer });
  output.write(JSON.stringify(result) + '\n');
  if (result.status !== 'complete') process.exitCode = 1;
  return result;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  ownerContinuationMain().catch(error => {
    process.stdout.write(JSON.stringify({ status: 'stopped', reason: /^[A-Z_]{1,100}$/.test(error?.code ?? '')
      ? error.code : 'OWNER_CONTINUATION_UNAVAILABLE', actions: [] }) + '\n');
    process.exitCode = 1;
  });
}
