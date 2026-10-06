import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import { CONSUMER, CONSUMER_DIGEST } from '../../consumer/consumer.mjs';
import { main } from '../src/entrypoint.mjs';
import { createAdmissionControl } from '../src/admission-control.mjs';
import { OWNER, REPOSITORY, REVIEWER } from '../src/execution-contract.mjs';
import { projectedRequestTitle } from '../src/step-metadata.mjs';
import { labelRunName } from '../src/launch-metadata.mjs';
import { renderAuthorityRecord, nativeReference, sha256Body } from '../../contracts/src/github-authority.mjs';
import { fixture } from './fixture.mjs';

const failure = code => Object.assign(new Error(code), { code });
const copy = value => structuredClone(value);
async function continuation(t, { route, labelLaunch = true, typed = true } = {}) {
  const f = await fixture(t, { remediation: true, deferAdmission: true, route, labelLaunch,
    createAdmission: async ({ root, store, journal }) => {
      const claims = join(root, 'claims'); await mkdir(claims);
      const admission = createAdmissionControl({ root: claims, store, journal, consumerDigest: CONSUMER_DIGEST, protectedRoot: false });
      await admission.initialize(); return admission;
    },
    beforeAdmission: ({ issue, pr, review, api, run }) => {
      if (!typed) return;
      issue.body = 'Authority model: github-native-v1\nIssue closure policy: keep-open\n\nCorrect the bounded PR finding.';
      const common = { schema_version: '3.0', repository: REPOSITORY, task: 42,
        charter_sha256: sha256Body(issue.body), route, scope: ['Correct the exact reviewed finding.'],
        model: 'gpt-6.1-sol', effort: 'xhigh', subagents: true, validation: ['diff-check'],
        boundaries: ['Repository only; preserve protected boundaries.'], decisions: [], context: [],
        branch: pr.head.ref, base_sha: pr.base.sha, starting_head: review.commit_id, issue_closure_policy: 'keep-open' };
      const initial = { ...common, kind: 'task-request', parent: { kind: 'issue', number: 42 }, step: 1,
        purpose: 'Implement bounded work', existing_pr: null, supersedes: null };
      const comment = { id: 901, body: renderAuthorityRecord(initial), user: copy(review.user) };
      const request = { ...common, kind: 'change-request', parent: { kind: 'pull_request', number: 43 }, step: 2,
        purpose: 'Correct bounded finding', existing_pr: 43,
        supersedes: nativeReference({ kind: 'issue-comment', id: comment.id, parent: initial.parent, body: comment.body }),
        change_request_id: 'CR-42-001', reviewed_head_sha: review.commit_id,
        findings: [{ id: 'F1', severity: 'major', problem: 'Incorrect behavior.', impact: 'The feature fails.',
          remediation: 'Correct the bounded behavior.', acceptance_criteria: ['The affected checks pass.'] }] };
      review.body = renderAuthorityRecord(request); pr.title = projectedRequestTitle(request);
      if (labelLaunch) run.display_title = labelRunName({ route, target: 'pull_request', number: 43 }, pr);
      const list = api.list.bind(api);
      api.list = async path => path === '/issues/42/comments' ? [copy(comment), ...await list(path)] : list(path);
    } });
  const event = { repository: { full_name: REPOSITORY }, sender: { login: OWNER },
    ...(labelLaunch ? { action: 'labeled', label: { name: `codex-ready-${route}` }, pull_request: copy(f.pr) }
      : { inputs: { route, task: '42', step: '2', pull_request: '43' } }) };
  let executions = 0; let preparations = 0; let handoffs = 0;
  const operations = [];
  const options = {
    env: { GITHUB_EVENT_NAME: labelLaunch ? 'pull_request_target' : 'workflow_dispatch',
      GITHUB_EVENT_PATH: 'fixture-event', GITHUB_REF: `refs/heads/${CONSUMER.baseBranch}`, GITHUB_RUN_ID: '99' },
    readEvent: async () => JSON.stringify(event),
    createWriter: () => ({ invoke: async request => {
      operations.push(request.operation);
      if (request.operation === 'handoff') handoffs++;
      if (request.operation === 'complete-execution') return f.admissionControl.complete(request);
      return f.broker.invoke(request);
    } }),
    createJournal: () => f.journal,
    createDispatcher: () => ({ dispatch: async e => {
      executions++;
      assert.equal(route, 'auto'); assert.equal((await f.api.get('/pulls/43')).draft, true);
      assert.equal((await f.api.get('/pulls/43')).head.sha, f.review.commit_id);
      await f.commit();
      return { version: e.version, attemptId: e.attemptId, child: 'started', containment: 'reaped',
        result: { status: 'success', summary: 'Bounded remediation completed.', validation: ['local checks'] } };
    } }),
    prepare: async e => { preparations++; assert.equal((await f.api.get('/pulls/43')).draft, true); await f.prepare(e); },
    collect: f.collect,
    persistFailure: () => assert.fail('unexpected post-admission failure')
  };
  return { ...f, options, operations, counts: () => ({ executions, preparations, handoffs }) };
}

for (const route of ['auto', 'manual']) {
  for (const typed of [false, true]) for (const labelLaunch of [false, true]) {
    test(`production ${route} ${typed ? 'typed' : 'legacy'} ${labelLaunch ? 'label' : 'dispatch'} verifies Draft before continuation`, async t => {
      const f = await continuation(t, { route, typed, labelLaunch });
      const original = copy(f.review); const draft = f.api.draft; let mutations = 0;
      f.api.draft = async id => {
        mutations++; assert.equal(id, 'PR_node'); assert.equal(await f.store.get(99), null);
        assert.deepEqual(f.counts(), { executions: 0, preparations: 0, handoffs: 0 });
        if (labelLaunch) assert.ok(f.pr.labels.some(l => l.name === `codex-ready-${route}`));
        await draft(id);
      };
      const result = await main(f.options);
      assert.equal(result.status, route === 'auto' ? 'IMPLEMENTED_PENDING_FRESH_REVIEW' : 'handed-off');
      assert.equal((await f.api.get('/pulls/43')).draft, route === 'manual');
      assert.equal(f.comments.length, 1); assert.deepEqual(f.review, original);
      assert.equal(mutations, 1); assert.equal(f.pushes(), route === 'auto' ? 1 : 0);
      if (route === 'auto') {
        assert.equal(result.head, await f.remoteHead());
        assert.equal((await f.store.get(99)).controllerLifecycle.status, 'complete');
      } else assert.match(f.comments[0].body, /MANUAL_CODEX_HANDOFF_READY/);
      assert.equal((await main(f.options)).status, result.status);
      assert.equal(mutations, 1); assert.equal(f.comments.length, 1);
      assert.equal(f.counts().executions, route === 'auto' ? 1 : 0);
    });
  }

  for (const mode of ['failed', 'unconfirmed', 'lost-readback', 'lost-response']) {
    test(`production ${route} Draft ${mode} stops or reconciles before continuation`, async t => {
      const f = await continuation(t, { route }); const review = copy(f.review);
      const draft = f.api.draft; const get = f.api.get.bind(f.api); let mutations = 0;
      f.api.draft = async id => {
        mutations++;
        if (mode === 'failed') throw failure('DRAFT_MUTATION_FAILED');
        if (mode === 'unconfirmed') return;
        await draft(id);
        if (mode === 'lost-readback') f.api.get = async path => {
          if (path === '/pulls/43') throw failure('READBACK_UNAVAILABLE');
          return get(path);
        };
        throw failure('GITHUB_REQUEST_FAILED');
      };
      if (mode !== 'lost-response') {
        await assert.rejects(main(f.options), { code: mode === 'failed' ? 'DRAFT_MUTATION_FAILED'
          : mode === 'unconfirmed' ? 'DRAFT_OBSERVATION_CHANGED' : 'READBACK_UNAVAILABLE' });
        assert.deepEqual(f.counts(), { executions: 0, preparations: 0, handoffs: 0 });
        assert.equal(await f.store.get(99), null); assert.equal(await f.journal.get(99), null);
        assert.ok((await f.lifecycleStore.get(f.review.id)).lifecycleIntent);
        assert.equal(f.comments.length, 0); assert.equal(f.pushes(), 0);
        assert.ok(f.pr.labels.some(l => l.name === `codex-ready-${route}`));
        f.api.get = get;
        f.api.draft = async id => { mutations++; await draft(id); };
      }
      assert.equal((await main(f.options)).status, route === 'auto' ? 'IMPLEMENTED_PENDING_FRESH_REVIEW' : 'handed-off');
      assert.equal(mutations, ['failed', 'unconfirmed'].includes(mode) ? 2 : 1);
      assert.equal((await f.lifecycleStore.get(f.review.id)).lifecycleIntent, null);
      assert.deepEqual(f.review, review); assert.equal(f.comments.length, 1);
      assert.equal((await main(f.options)).status, route === 'auto' ? 'IMPLEMENTED_PENDING_FRESH_REVIEW' : 'handed-off');
      assert.equal(f.counts().executions, route === 'auto' ? 1 : 0);
    });
  }

  test(`production ${route} binds the Draft transition to the admitted authority snapshot`, async t => {
    const f = await continuation(t, { route, typed: false });
    const get = f.lifecycleStore.get;
    f.lifecycleStore.get = async key => { f.issue.body += '\nChanged owner scope.'; return get(key); };
    f.api.draft = () => assert.fail('changed authority drafted');
    await assert.rejects(main(f.options), { code: 'AUTHORITY_CHANGED' });
    assert.deepEqual(f.counts(), { executions: 0, preparations: 0, handoffs: 0 });
    assert.equal(f.comments.length, 0); assert.equal(await f.store.get(99), null);
  });

  test(`production ${route} rejects an untrusted native Reviewer identity before Draft or continuation`, async t => {
    const f = await continuation(t, { route, typed: false });
    f.api.userIdentity = async () => ({ login: REVIEWER, id: 702, type: 'Bot' });
    f.api.draft = () => assert.fail('untrusted review drafted');
    await assert.rejects(main(f.options), { code: 'CURRENT_CHANGE_REQUEST_MISSING' });
    assert.deepEqual(f.counts(), { executions: 0, preparations: 0, handoffs: 0 });
    assert.equal(f.comments.length, 0); assert.equal(await f.store.get(99), null);
  });
}

test('production manual handoff rechecks Draft after admission and recovers without republishing authority', async t => {
  const f = await continuation(t, { route: 'manual' }); const createWriter = f.options.createWriter;
  const draft = f.api.draft; let failed = false;
  f.options.createWriter = () => {
    const writer = createWriter();
    return { invoke: async request => {
      if (request.operation === 'handoff' && !failed) {
        failed = true; f.pr.draft = false;
        f.api.draft = async () => { throw failure('DRAFT_MUTATION_FAILED'); };
      }
      return writer.invoke(request);
    } };
  };
  // This failure is after admission and uses the normal controller diagnostic.
  f.options.persistFailure = async () => ({ fallbackReference: 'fixture-diagnostic' });
  await assert.rejects(main(f.options), { code: 'DRAFT_MUTATION_FAILED' });
  assert.equal(f.comments.length, 0); assert.equal(f.counts().executions, 0);
  f.api.draft = draft;
  assert.equal((await main(f.options)).status, 'handed-off');
  assert.equal((await f.api.get('/pulls/43')).draft, true);
  assert.equal(f.comments.length, 1); assert.equal(f.pushes(), 0);
});
