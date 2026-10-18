import test from 'node:test';
import assert from 'node:assert/strict';
import { writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fixture, memoryStore } from './fixture.mjs';
import { createAdmissionControl } from '../src/admission-control.mjs';
import { createPublicationBroker } from '../src/publication-broker.mjs';
import { runAttempt } from '../src/attempt.mjs';
import { collectProgress } from '../src/trusted-git.mjs';
import { labelRunName } from '../src/launch-metadata.mjs';
import { digest, REPOSITORY, REVIEWER, WRITER } from '../src/execution-contract.mjs';
import { CONSUMER, CONSUMER_DIGEST } from '../../consumer/consumer.mjs';
import { admissionBinding, extractAuthorityRecord, renderAuthorityRecord, sha256Body } from '../../contracts/src/github-authority.mjs';

// Git, collection, protected attempt records and Writer publication are real.
// The native GitHub identity/event/comment transport below is a fixture, not
// evidence of a qualified installation or an external GitHub execution.
const copy = value => structuredClone(value);
const charter = 'Authority model: github-native-v1\nIssue closure policy: keep-open\n\nCorrect the reviewed source while preserving protected operations and independent acceptance.';
const reviewer = { login: REVIEWER, id: 701, type: 'Bot' };
const writer = { login: WRITER, id: 702, type: 'Bot' };
const apiRoot = `https://api.github.com/repos/${REPOSITORY}`;
const common = kind => ({ schema_version: '4.0', kind, repository: REPOSITORY, task: 42,
  parent: { kind: 'issue', number: 42 }, charter_sha256: sha256Body(charter) });
const direction = { scope: ['Continue the same reviewed remediation after the owner resolves its blocker.'],
  boundaries: ['Repository source only; no deployment, release, merge or Issue closure.'],
  model: 'owner-resolved-model', effort: 'xhigh', subagents: true };

function taskDecision(amendments = direction, { id = 901, parent = { kind: 'issue', number: 42 } } = {}) {
  return { id, user: copy(reviewer), issue_url: `${apiRoot}/issues/${parent.number}`,
    created_at: '2026-09-04T12:03:00Z', body: renderAuthorityRecord({ ...common('decision'), parent,
      purpose: 'Resolve the blocked remediation within the same Task and Change Request',
      amendments: copy(amendments), supersedes: null, context: [] }) };
}

async function admissionControl({ root, store, journal }) {
  const control = createAdmissionControl({ root, store, journal, consumerDigest: CONSUMER_DIGEST, protectedRoot: false });
  await control.initialize(); return control;
}

async function blockedContinuation(t, { resolvingDecision = true, initialAmendments, complete = true } = {}) {
  const decisions = initialAmendments ? [taskDecision(initialAmendments, { id: 700 })] : [];
  const commentMetadata = new Map();
  const f = await fixture(t, { remediation: true, issueBody: charter, labelLaunch: true,
    streamlinedAdmission: true, createAdmission: admissionControl,
    beforeAdmission: ({ api, review, pr, events, admissionRequest }) => {
      admissionRequest.step = null;
      review.submitted_at = '2026-09-04T11:59:00Z';
      review.body = renderAuthorityRecord({ ...common('change-request'), parent: { kind: 'pull_request', number: 43 },
        purpose: 'Correct the exact reviewed source', branch: pr.head.ref, base_sha: pr.base.sha,
        reviewed_head_sha: review.commit_id, change_request_id: 'CR-42-001', context: [],
        overrides: { boundaries: ['Preserve independent exact-head acceptance.'] },
        findings: [{ id: 'F1', severity: 'major', problem: 'The reviewed source lacks the required behavior.',
          impact: 'The bounded remediation cannot complete.', remediation: 'Implement the authorized correction.',
          acceptance_criteria: ['The affected behavior and required checks pass.'] }] });
      const identity = api.userIdentity.bind(api);
      api.userIdentity = login => login === WRITER ? Promise.resolve(copy(writer)) : identity(login);
      const remove = api.delete.bind(api);
      api.delete = async path => {
        if (path === '/issues/43/labels/codex-ready-manual') {
          pr.labels = pr.labels.filter(label => label.name !== 'codex-ready-manual');
          events.push({ id: Math.max(...events.map(event => event.id)) + 1, event: 'unlabeled',
            actor: copy(writer), label: { name: 'codex-ready-manual' }, created_at: '2026-09-04T12:04:01Z' }); return;
        }
        return remove(path);
      };
      const enrich = comment => ({ ...comment, ...(commentMetadata.get(comment.id) ?? {}) });
      const get = api.get.bind(api);
      api.get = async path => {
        if (/^\/issues\/comments\/[1-9][0-9]*$/.test(path)) {
          const decision = decisions.find(value => value.id === Number(path.split('/').at(-1)));
          if (decision) return copy(decision);
          return enrich(await get(path));
        }
        return get(path);
      };
      const list = api.list.bind(api);
      api.list = async path => {
        const records = await list(path);
        return path === '/issues/42/comments' ? [...copy(decisions.filter(value => value.issue_url.endsWith('/42'))), ...records.map(enrich)]
          : path === '/issues/43/comments' ? [...copy(decisions.filter(value => value.issue_url.endsWith('/43'))), ...records.map(enrich)] : records;
      };
      const post = api.post.bind(api);
      api.post = async (path, body) => {
        const result = await post(path, body);
        if (/^\/issues\/\d+\/comments$/.test(path)) {
          commentMetadata.set(result.id, { user: copy(writer), issue_url: `${apiRoot}${path.slice(0, -'/comments'.length)}`,
            created_at: '2026-09-04T12:01:00Z' });
          return enrich(result);
        }
        return result;
      };
    } });
  assert.notEqual(f.admission.status, 'BLOCKED');
  const admissionLifecycleStore = memoryStore();
  const broker = createPublicationBroker({ api: f.api, store: f.store, publisher: f.publisher,
    admission: f.admissionControl, journal: f.journal, lifecycleStore: f.lifecycleStore, admissionLifecycleStore,
    streamlinedAdmission: true });
  f.broker = { invoke: request => broker.dispatch(request) };
  const originalReview = copy(f.review);
  const result = await runAttempt({ ...f, execute: async e => {
    await f.commit();
    return { version: 2, attemptId: e.attemptId, child: 'started', containment: 'reaped',
      result: { status: 'blocked', summary: 'Writer preserves useful remediation progress before the owner decision.',
        validation: ['Fixture local source change'], blockedReason: 'A bounded owner direction is required before continuing.' } };
  } });
  assert.equal(result.status, 'BLOCKED');
  if (complete) await f.admissionControl.complete({ runId: 99, attemptId: f.envelope.attemptId });
  const prior = await f.store.get(99);
  const publishedHead = await f.remoteHead();
  assert.notEqual(publishedHead, originalReview.commit_id);
  assert.equal(prior.publishedHead, publishedHead);
  assert.equal(prior.outcome.head, publishedHead);
  assert.equal(prior.outcome.prNumber, 43);
  const originalComment = copy(f.comments.find(comment => comment.id === prior.outcome.outcomeId));
  const outcome = extractAuthorityRecord(originalComment.body);
  assert.equal(outcome.schema_version, '4.0');
  assert.equal(outcome.status, 'blocked');
  assert.equal(outcome.result.kind, 'git');
  assert.equal(outcome.result.revision, publishedHead);
  assert.deepEqual(outcome.admission, admissionBinding(f.envelope.request));
  const originalLifecycle = await f.lifecycleStore.get(f.review.id);
  const runs = new Map([[99, { ...copy(f.run), status: 'completed', updated_at: '2026-09-04T12:02:00Z' }]]);
  f.api.getRun = async id => copy(runs.get(id));
  const amend = amendments => { const decision = taskDecision(amendments); decisions.push(decision); return decision; };
  if (resolvingDecision) amend(direction);
  function nextReady({ route = 'auto', runId = 100, eventId = 72, at = '2026-09-04T12:04:00Z' } = {}) {
    f.pr.labels = [{ name: `step-${prior.envelope.step}` }, { name: `codex-ready-${route}` }];
    const request = { ...f.admissionRequest, route, runId, step: null };
    runs.set(runId, { ...copy(f.run), id: runId, status: 'in_progress', created_at: at.replace('00Z', '01Z'),
      display_title: labelRunName(request, f.pr) });
    f.events.splice(0, f.events.length, { id: eventId, event: 'labeled',
      actor: { login: CONSUMER.owner, type: 'User' }, label: { name: `codex-ready-${route}` }, created_at: at });
    return request;
  }
  return { ...f, decisions, commentMetadata, admissionLifecycleStore, originalReview, originalComment, originalLifecycle,
    prior, publishedHead, outcome, result, runs, amend, nextReady };
}

async function assertRefused(f, request, codes) {
  let code;
  try {
    const result = await f.broker.invoke(request);
    assert.equal(result.status, 'BLOCKED', 'unsafe continuation must not produce an executable admission');
    assert.equal(result.envelope.step, null, 'rejected admission must not allocate a Step');
    code = result.envelope.admissionBlock.code;
  } catch (error) {
    if (error.code === 'ERR_ASSERTION') throw error;
    code = error.code;
  }
  assert.ok(codes.includes(code), `expected ${codes.join(' or ')}, received ${code}`);
  const saved = await f.store.get(request.runId);
  assert.ok(!saved || saved.admissionBlock, 'no worker may be reserved for rejected continuation');
  assert.equal(f.pushes(), 1, 'refusal must not publish more Git progress');
}

for (const route of ['auto', 'manual']) test(`contained BLOCKED CR progress admits the same CR at Writer head with a fresh ${route} Step`, async t => {
  const f = await blockedContinuation(t);
  const request = f.nextReady({ route });
  const admitted = await f.broker.invoke(request);
  assert.notEqual(admitted.status, 'BLOCKED', JSON.stringify(admitted.envelope));
  const e = admitted.envelope;
  assert.equal(e.step, f.prior.envelope.step + 1);
  assert.equal(e.attemptId, 'run-100');
  assert.equal(e.route, route);
  assert.equal(e.number, 43);
  assert.equal(e.issueNumber, 42);
  assert.equal(e.reviewId, f.originalReview.id);
  assert.equal(e.branch, f.prior.envelope.branch);
  assert.equal(e.startHead, f.publishedHead);
  assert.equal(e.request.starting_head, f.publishedHead);
  assert.equal(e.request.reviewed_head_sha, f.originalReview.commit_id);
  assert.equal(e.request.existing_pr, 43);
  assert.equal(e.request.change_request_id, f.prior.envelope.request.change_request_id);
  assert.deepEqual(e.request.authority.change_request, f.prior.envelope.request.authority.change_request);
  assert.deepEqual(e.request.lineage, { attempt: f.prior.envelope.attemptId, step: f.prior.envelope.step,
    sha256: digest(f.prior.envelope) });
  assert.deepEqual(e.profile, { cliModelId: direction.model, effort: direction.effort });
  assert.equal(e.subagentsAllowed, direction.subagents);
  assert.deepEqual(e.request.scope, direction.scope);
  assert.ok(e.request.boundaries.includes(direction.boundaries[0]));
  assert.ok(e.request.boundaries.includes('Preserve independent exact-head acceptance.'));
  assert.notEqual(e.authorityDigest, f.prior.envelope.authorityDigest);
  assert.deepEqual(f.review, f.originalReview);
  assert.deepEqual(await f.store.get(99), f.prior);
  assert.deepEqual(f.comments.find(comment => comment.id === f.originalComment.id), f.originalComment);
  assert.deepEqual(await f.lifecycleStore.get(f.review.id), f.originalLifecycle);
  assert.ok(await f.admissionLifecycleStore.get(e.runId));
  assert.equal((await f.api.list('/pulls/43/reviews')).length, 1);
  assert.equal((await f.broker.invoke(request)).resumed, true);
  const cwd = join(dirname(f.cwd), e.attemptId);
  let calls = 0;
  const options = { ...f, envelope: e,
    collect: envelope => collectProgress(cwd, envelope, { root: f.root, remote: f.remote }),
    execute: async envelope => {
      calls++;
      assert.equal(await f.command(cwd, ['rev-parse', 'HEAD']), f.publishedHead);
      await writeFile(join(cwd, 'docs/continued.md'), 'Owner-resolved remediation completes the same Change Request.\n');
      await f.command(cwd, ['add', 'docs/continued.md']);
      await f.command(cwd, ['commit', '-m', 'complete owner-resolved remediation'], f.identity);
      return { version: 2, attemptId: envelope.attemptId, child: 'started', containment: 'reaped',
        result: { status: 'success', summary: 'Completed the authorized continuation.', validation: ['Fixture continuation check'] } };
    } };
  const completed = await runAttempt(options);
  assert.equal(completed.status, route === 'auto' ? 'IMPLEMENTED_PENDING_FRESH_REVIEW' : 'handed-off');
  assert.deepEqual(await runAttempt({ ...options, admissionResumed: true }), completed);
  assert.equal(calls, route === 'auto' ? 1 : 0);
  assert.equal(f.pushes(), route === 'auto' ? 2 : 1);
  assert.deepEqual(await f.store.get(99), f.prior);
  assert.deepEqual(f.comments.find(comment => comment.id === f.originalComment.id), f.originalComment);
  assert.deepEqual(f.review, f.originalReview);
  if (route === 'manual') {
    const handoff = f.comments.find(comment => comment.body.includes('MANUAL_CODEX_HANDOFF_READY'));
    assert.ok(handoff.body.includes(f.publishedHead));
    assert.ok(handoff.body.includes(`Task 42 — Step ${e.step}`));
    assert.equal((await f.api.get('/pulls/43')).draft, true);
  }
});

test('exact original BLOCKED replay preserves its Step, Outcome and already executed child', async t => {
  const f = await blockedContinuation(t);
  const replay = await f.broker.invoke(f.admissionRequest);
  assert.equal(replay.resumed, true);
  assert.deepEqual(replay.envelope, f.prior.envelope);
  assert.deepEqual(await runAttempt({ ...f, admissionResumed: true, execute: () => assert.fail('old child was relaunched') }), f.result);
  assert.deepEqual(await f.store.get(99), f.prior);
  assert.equal(f.comments.length, 1);
  assert.equal(f.pushes(), 1);
});

test('a trusted new profile-only Decision can resolve the owner blocker without changing CR direction', async t => {
  const f = await blockedContinuation(t, { resolvingDecision: false });
  const amendments = { model: 'owner-available-model', effort: 'high', subagents: false };
  f.amend(amendments);
  const admitted = await f.broker.invoke(f.nextReady());
  assert.notEqual(admitted.status, 'BLOCKED');
  assert.equal(admitted.envelope.step, 2);
  assert.equal(admitted.envelope.startHead, f.publishedHead);
  assert.equal(admitted.envelope.request.reviewed_head_sha, f.originalReview.commit_id);
  assert.deepEqual(admitted.envelope.profile, { cliModelId: amendments.model, effort: amendments.effort });
  assert.equal(admitted.envelope.subagentsAllowed, false);
  assert.deepEqual(admitted.envelope.request.scope, f.prior.envelope.request.scope);
  assert.deepEqual(admitted.envelope.request.boundaries, f.prior.envelope.request.boundaries);
  assert.deepEqual(await f.store.get(99), f.prior);
  assert.deepEqual(f.review, f.originalReview);
});

for (const mode of ['missing', 'stale', 'untrusted', 'PR-scoped']) {
  test(`${mode} Decision cannot promote a BLOCKED CR to a new Step`, async t => {
    const f = await blockedContinuation(t, { resolvingDecision: false });
    if (mode === 'stale') f.decisions.push(taskDecision(direction, { id: f.originalComment.id }));
    if (mode === 'untrusted') f.amend(direction).user.id = 999;
    if (mode === 'PR-scoped') f.decisions.push(taskDecision(direction, { parent: { kind: 'pull_request', number: 43 } }));
    await assertRefused(f, f.nextReady(), ['AUTHORITY_CONTINUATION_INVALID']);
    assert.deepEqual(await f.store.get(99), f.prior);
    assert.deepEqual(f.review, f.originalReview);
  });
}

for (const mode of ['body', 'identity', 'parent', 'missing', 'marker', 'typed-result']) {
  test(`${mode === 'missing' ? 'a missing native Writer Outcome' : `${mode} tampering of the native Writer Outcome`} cannot authorize CR continuation`, async t => {
    const f = await blockedContinuation(t);
    const comment = f.comments.find(value => value.id === f.originalComment.id);
    if (mode === 'body') comment.body += '\nEdited native source bytes.\n';
    if (mode === 'identity') f.commentMetadata.get(comment.id).user.id = 999;
    if (mode === 'parent') f.commentMetadata.get(comment.id).issue_url = `${apiRoot}/issues/44`;
    if (mode === 'missing') {
      const get = f.api.get.bind(f.api);
      f.api.get = path => path === `/issues/comments/${comment.id}`
        ? Promise.reject(Object.assign(new Error('Missing native Outcome'), { code: 'GITHUB_REQUEST_FAILED', status: 404 })) : get(path);
    }
    if (mode === 'marker' || mode === 'typed-result') {
      if (mode === 'marker') comment.body = comment.body.replace(`<!-- relay:${f.envelope.attemptId}:outcome -->`, '');
      else {
        const changed = copy(f.outcome); changed.result.revision = 'f'.repeat(40);
        comment.body = comment.body.replace(renderAuthorityRecord(f.outcome), renderAuthorityRecord(changed));
      }
      const prior = await f.store.get(99); prior.outcome.bodySha256 = sha256Body(comment.body); await f.store.put(99, prior);
    }
    await assertRefused(f, f.nextReady(), mode === 'missing'
      ? ['AUTHORITY_CONTINUATION_INVALID', 'GITHUB_REQUEST_FAILED'] : ['AUTHORITY_CONTINUATION_INVALID']);
  });
}

for (const mode of ['removed', 'edited']) test(`${mode} originally admitted Decision source blocks the fresh continuation`, async t => {
  const f = await blockedContinuation(t, { initialAmendments: { scope: ['Correct the reviewed behavior.'] } });
  if (mode === 'removed') f.decisions.splice(0, 1);
  else f.decisions[0].body += '\nEdited original authority bytes.\n';
  await assertRefused(f, f.nextReady(), ['AUTHORITY_CONTINUATION_INVALID', 'AUTHORITY_SOURCE_MISMATCH']);
});

test('reaped and preserved CR execution releases its slot before logical lifecycle completion', async t => {
  const f = await blockedContinuation(t, { complete: false });
  const original = await f.store.get(99);
  const next = await f.broker.invoke(f.nextReady());
  assert.equal(next.envelope.step, 2);
  assert.deepEqual(await f.store.get(99), original);
});

test('unknown prior physical containment cannot be hidden by its public BLOCKED Outcome', async t => {
  const f = await blockedContinuation(t, { complete: false });
  const record = await f.journal.get(99); record.execution.containment = 'unknown'; await f.journal.put(99, record);
  await assertRefused(f, f.nextReady(), ['EXECUTION_SLOT_UNAVAILABLE']);
  assert.equal(await f.store.get(100), null);
});

const changedBindingCodes = { 'arbitrary-head': ['STARTING_STATE_MISMATCH'], base: ['AUTHORITY_CONTINUATION_INVALID'],
  branch: ['AUTHORITY_CONTINUATION_INVALID'], 'foreign-repository': ['OWNER_RUN_NOT_ADMITTED'],
  Task: ['AUTHORITY_TARGET_MISMATCH'], CR: ['AUTHORITY_CONTINUATION_INVALID'] };
for (const mode of Object.keys(changedBindingCodes)) {
  test(`changed ${mode} cannot borrow the previous CR publication lineage`, async t => {
    const f = await blockedContinuation(t);
    if (mode === 'arbitrary-head') {
      const get = f.api.get.bind(f.api);
      f.api.get = async path => {
        const value = await get(path);
        return path === '/pulls/43' ? { ...value, head: { ...value.head, sha: 'f'.repeat(40) } } : value;
      };
    }
    if (mode === 'base') f.pr.base.sha = 'f'.repeat(40);
    if (mode === 'branch') f.pr.head.ref = `${CONSUMER.taskBranchPrefix}foreign-42`;
    if (mode === 'foreign-repository') f.pr.head.repo.full_name = 'foreign/fixture';
    if (mode === 'Task') {
      f.pr.body = 'Related to #44';
      const get = f.api.get.bind(f.api); const list = f.api.list.bind(f.api);
      f.api.get = path => path === '/issues/44' ? Promise.resolve({ ...copy(f.issue), number: 44 }) : get(path);
      f.api.list = path => path === '/issues/44/comments' ? Promise.resolve([]) : list(path);
    }
    if (mode === 'CR') {
      const changed = extractAuthorityRecord(f.review.body); changed.change_request_id = 'CR-42-002';
      f.review.body = renderAuthorityRecord(changed);
    }
    await assertRefused(f, f.nextReady(), changedBindingCodes[mode]);
  });
}

for (const mode of ['missing', 'APPROVED', 'newer-CR']) test(`${mode} current review cannot reuse the previous native CR lineage`, async t => {
  const f = await blockedContinuation(t);
  const list = f.api.list.bind(f.api);
  let reviews = [];
  if (mode === 'APPROVED') reviews = [copy(f.review), { ...copy(f.review), id: f.review.id + 1,
    state: 'APPROVED', body: 'Independent approval on the original reviewed source.' }];
  if (mode === 'newer-CR') {
    const payload = extractAuthorityRecord(f.review.body); payload.change_request_id = 'CR-42-002';
    reviews = [copy(f.review), { ...copy(f.review), id: f.review.id + 1, body: renderAuthorityRecord(payload) }];
  }
  f.api.list = path => path === '/pulls/43/reviews' ? Promise.resolve(copy(reviews)) : list(path);
  await assertRefused(f, f.nextReady(), ['AUTHORITY_CONTINUATION_INVALID']);
});

test('a public BLOCKED Outcome cannot supply a missing protected Writer publication head', async t => {
  const f = await blockedContinuation(t);
  const prior = await f.store.get(99); prior.publishedHead = null; await f.store.put(99, prior);
  await assertRefused(f, f.nextReady(), ['AUTHORITY_CONTINUATION_INVALID']);
});

for (const [field, value] of [['starting_head', 'f'.repeat(40)], ['base_sha', 'f'.repeat(40)],
  ['branch', `${CONSUMER.taskBranchPrefix}wrong-target`], ['existing_pr', 44]]) {
  test(`a new Decision cannot substitute a contradictory ${field} pin for Writer lineage`, async t => {
    const f = await blockedContinuation(t);
    const current = f.decisions.at(-1);
    const payload = extractAuthorityRecord(current.body); payload.amendments[field] = value;
    current.body = renderAuthorityRecord(payload);
    await assertRefused(f, f.nextReady(), ['STARTING_STATE_MISMATCH']);
  });
}

test('a real foreign branch commit beyond Writer B remains outside the continuation authority', async t => {
  const f = await blockedContinuation(t);
  await f.command(f.source, ['fetch', f.remote, f.envelope.branch]);
  await f.command(f.source, ['switch', '-c', 'external-progress', 'FETCH_HEAD']);
  await writeFile(join(f.source, 'docs/foreign.md'), 'External source progress must not become Writer lineage.\n');
  await f.command(f.source, ['add', 'docs/foreign.md']);
  await f.command(f.source, ['commit', '-m', 'external source progress']);
  await f.command(f.source, ['push', f.remote, `HEAD:refs/heads/${f.envelope.branch}`]);
  assert.notEqual(await f.remoteHead(), f.publishedHead);
  await assertRefused(f, f.nextReady(), ['STARTING_STATE_MISMATCH']);
});

test('an observed branch rollback to original CR A cannot bypass the retained Writer B lineage', async t => {
  const f = await blockedContinuation(t);
  const get = f.api.get.bind(f.api);
  f.api.get = async path => {
    const value = await get(path);
    if (path === '/pulls/43') return { ...value, head: { ...value.head, sha: f.originalReview.commit_id } };
    if (path === `/git/matching-refs/heads/${f.envelope.branch}`) {
      return value.map(ref => ({ ...ref, object: { ...ref.object, sha: f.originalReview.commit_id } }));
    }
    return value;
  };
  await assertRefused(f, f.nextReady(), ['STARTING_STATE_MISMATCH']);
  assert.equal(await f.remoteHead(), f.publishedHead, 'the native rollback observation is simulated without changing the remote');
});

test('caller unpublished-head and profile extras cannot override the admitted Writer head and trusted profile', async t => {
  const f = await blockedContinuation(t);
  const unpublished = await f.commit('docs/work.md', 'Unpublished worker residue after the terminal result.\n');
  assert.notEqual(unpublished, f.publishedHead);
  const request = { ...f.nextReady(), starting_head: unpublished, profile: { cliModelId: 'caller-model', effort: 'ultra' } };
  const admitted = await f.broker.invoke(request);
  assert.notEqual(admitted.status, 'BLOCKED');
  assert.equal(admitted.envelope.startHead, f.publishedHead);
  assert.deepEqual(admitted.envelope.profile, { cliModelId: direction.model, effort: direction.effort });
  assert.equal(await f.remoteHead(), f.publishedHead);
});

test('a route override without the matching owner ready command is refused', async t => {
  const f = await blockedContinuation(t);
  await assertRefused(f, { ...f.nextReady(), route: 'manual' }, ['OWNER_RUN_NOT_ADMITTED']);
  assert.equal(await f.store.get(100), null);
});

test('replaying an already consumed owner ready event cannot allocate another Step', async t => {
  const f = await blockedContinuation(t);
  await assertRefused(f, f.nextReady({ eventId: f.envelope.readyEventId }), ['READY_EVENT_ALREADY_CONSUMED']);
  assert.equal(await f.store.get(100), null);
  assert.deepEqual(await f.store.get(99), f.prior);
});

test('a fresh owner event cannot reuse the physical slot held by the active successor', async t => {
  const f = await blockedContinuation(t);
  const admitted = await f.broker.invoke(f.nextReady());
  assert.equal(admitted.envelope.step, 2);
  await assertRefused(f, f.nextReady({ runId: 101, eventId: 73, at: '2026-09-04T12:05:00Z' }), ['EXECUTION_SLOT_UNAVAILABLE']);
  assert.equal(await f.store.get(101), null);
  assert.deepEqual((await f.store.get(100)).envelope, admitted.envelope);
  assert.deepEqual(await f.store.get(99), f.prior);
});
