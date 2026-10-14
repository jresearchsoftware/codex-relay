// Deterministic in-memory checks only. These records are not live evidence.
import assert from 'node:assert/strict';
import test from 'node:test';
import { charter, prepareDecision, TEST_REPOSITORIES, VARIANTS } from './prepare-smoke.mjs';
import { verifyCase, verifyOverlap } from './verify-smoke.mjs';
import { admissionBinding, createAdmissionSnapshot, renderAuthorityRecord,
  resolveTaskAuthority, sha256Body, nativeReference } from '../../../contracts/src/github-authority.mjs';

const writer = { id: 8001, login: 'jresearch-relay-test-writer[bot]', type: 'Bot' };
const reviewer = { id: 8002, login: 'jresearch-relay-test-reviewer[bot]', type: 'Bot' };
const owner = { id: 8003, login: 'fixture-owner', type: 'User' };
function input(variant = 'same-a', task = 101) {
  const repository = { full_name: VARIANTS[variant], id: TEST_REPOSITORIES[VARIANTS[variant]] };
  return { variant, repository, main: { sha: 'a'.repeat(40) }, issue: { id: task + 1000, number: task,
    repository_url: `https://api.github.com/repos/${repository.full_name}`, state: 'open', labels: [],
    title: `Parallel qualification smoke ${variant} for product Task 103`, body: charter(variant) } };
}
function mockCase(variant = 'same-a', task = 101, runId = 10001) {
  const prepared = input(variant, task);
  const { issue } = prepared;
  const repository = prepared.repository.full_name;
  const decision = prepareDecision(prepared).record;
  const parent = { kind: 'issue', number: task };
  const nativeDecision = { kind: 'issue-comment', repository, id: task + 2000, parent, body: renderAuthorityRecord(decision), author: reviewer };
  const resolved = resolveTaskAuthority([{ kind: 'issue-body', repository, id: issue.id, parent, body: issue.body, author: owner }, nativeDecision],
    { repository, task, charterId: issue.id, charterBody: issue.body, trustedAuthor: reviewer, route: 'auto',
      projectDefaults: { model: 'gpt-6.1-sol', effort: 'medium', subagents: false, validation: ['diff-check', 'secret-scan'] },
      purpose: issue.title, startingState: { branch: decision.amendments.branch, base_sha: prepared.main.sha,
        starting_head: prepared.main.sha, existing_pr: null } });
  const admission = createAdmissionSnapshot(resolved, { step: 1, attempt: `run-${runId}`, runId });
  const e = { repository, issueNumber: task, runId, attemptId: `run-${runId}`, route: 'auto', transport: 'label',
    runName: `Automatic fixture ${task}`, readyLabel: 'codex-ready-auto', readyEventId: task + 3000,
    readyEventAt: '2026-10-14T12:00:00Z', step: 1, request: admission, branch: admission.branch,
    startHead: admission.starting_head, profile: { cliModelId: admission.model, effort: admission.effort }, subagentsAllowed: false };
  const prNumber = task + 50;
  const record = { schema_version: '4.0', kind: 'outcome', repository, task, parent: { kind: 'pull_request', number: prNumber },
    charter_sha256: sha256Body(issue.body), step: 1, authority: admission.authority, admission: admissionBinding(admission),
    authority_resolution: admission.authority_resolution, attempt: e.attemptId, status: 'implemented',
    result: { kind: 'git', revision: 'b'.repeat(40), identities: [{ kind: 'github-actions-run', id: String(runId) }] },
    summary: 'Deterministic in-memory smoke verifier test.', warnings: [], limitations: ['Not live execution evidence.'] };
  const outcome = { id: task + 4000, user: writer, body: renderAuthorityRecord(record) + `\n<!-- relay:run-${runId}:outcome -->`,
    html_url: `https://github.com/${repository}/pull/${prNumber}#issuecomment-${task + 4000}`,
    performed_via_github_app: { id: 5213167, slug: 'jresearch-relay-test-writer' } };
  const receipt = { outcomeId: outcome.id, bodySha256: sha256Body(outcome.body), head: record.result.revision };
  const data = { issue, comments: [{ ...nativeDecision, user: reviewer,
    performed_via_github_app: { id: 5213202, slug: 'jresearch-relay-test-reviewer' } }, outcome],
    events: [{ id: e.readyEventId, event: 'labeled', label: { name: e.readyLabel }, actor: owner, created_at: e.readyEventAt,
      url: `https://api.github.com/repos/${repository}/issues/events/${e.readyEventId}` }],
    run: { id: runId, repository: { full_name: repository, id: prepared.repository.id }, event: 'issues', run_attempt: 1,
      path: '.github/workflows/test-routing.yml', head_branch: 'main',
      status: 'completed', conclusion: 'success', actor: owner, triggering_actor: owner, display_title: e.runName,
      created_at: '2026-10-14T12:00:02Z' },
    claim: { envelope: e, outcome: receipt, publishedHead: record.result.revision, prNumber },
    journal: { envelope: e, outcome: receipt, collection: { clean: true }, execution: { reserved: true, returned: true,
      child: 'started', containment: 'reaped', result: { status: 'success' },
      codexUsage: { source: 'codex-exec-turn-completed', scope: 'native-session-total', input_tokens: 100, output_tokens: 25 } } },
    pr: { number: prNumber, state: 'open', merged: false,
      head: { repo: prepared.repository, ref: e.branch, sha: record.result.revision }, base: { repo: prepared.repository },
      body: `Related to #${task}\nExecution admission digest: ${record.admission.sha256}` } };
  return { expected: { name: variant, repository, task, run_id: runId, owner: owner.login, writer_actor: writer, reviewer_actor: reviewer,
    routing_workflow: '.github/workflows/test-routing.yml', base_branch: 'main' }, data };
}
test('all four plans validate exact v4 Decision schema without allocating a Step', () => {
  for (const variant of Object.keys(VARIANTS)) {
    const prepared = prepareDecision(input(variant));
    assert.equal(prepared.record.schema_version, '4.0');
    assert.equal(prepared.record.amendments.effort, 'medium');
    assert(!Object.hasOwn(prepared.record, 'step'));
    assert(!Object.hasOwn(prepared.record, 'admission'));
  }
});
test('generation rejects wrong TEST native ID, changed charter, already-ready Issue and unbounded wait', () => {
  for (const mutate of [value => value.repository.id++, value => value.issue.body += 'changed',
    value => value.issue.labels.push({ name: 'codex-ready-auto' }), value => value.repository.full_name = 'jresearchsoftware/codex-relay']) {
    const value = input(); mutate(value); assert.throws(() => prepareDecision(value));
  }
  for (const duration of [0, 59, 181, 61]) assert.throws(() => charter('same-a', duration));
});
test('native/protected reconciliation rejects duplicate Outcome, forged Decision actor, stale digest, missing real usage and changed PR head', () => {
  const valid = mockCase();
  assert.equal(verifyCase(valid.expected, valid.data).run_id, 10001);
  for (const mutate of [data => data.comments.push(data.comments[1]), data => data.comments[0].user = writer,
    data => data.claim.outcome.bodySha256 = 'c'.repeat(64), data => data.journal.execution.codexUsage.output_tokens = 'UNAVAILABLE',
    data => data.claim.qualificationFixture = { synthetic: true }, data => data.run.run_attempt = 2,
    data => data.pr.head.sha = 'c'.repeat(40), data => data.events[0].actor.type = 'Bot']) {
    const value = structuredClone(valid); mutate(value.data); assert.throws(() => verifyCase(value.expected, value.data));
  }
});
function overlapFixture(cross = false) {
  const cases = [mockCase(cross ? 'cross-a' : 'same-a'), mockCase(cross ? 'cross-b' : 'same-b', 102, 10002)];
  const results = cases.map(value => verifyCase(value.expected, value.data));
  const observations = { source: 'trusted-host-procfs', complete_for_window: true, samples: results.flatMap((result, index) =>
    ['2026-10-14T12:00:10Z', '2026-10-14T12:00:20Z'].map(observed_at => ({ observed_at, repository: result.repository,
      run_id: result.run_id, attempt: result.attempt, pid: 200 + index, uid: 300 + index, proc_start_ticks: '12345',
      host: 'offline-test-host', executable: '/opt/codex/codex', command_role: 'codex-exec',
      cgroup: `/offline/run-${result.run_id}`, execution_slot: `slot-${index}`, process_state: 'S' }))) };
  const inventory = { complete_for_window: true, attempts: results.map(result => ({ ...result, child: 'started' })) };
  const pair = { kind: cross ? 'cross-repository' : 'same-repository', cases: results.map(result => result.name) };
  return { pair, results, observations, inventory };
}
test('same/cross repo observed overlap works; pending-run timestamps are not evidence', () => {
  for (const cross of [false, true]) {
    const value = overlapFixture(cross);
    assert.equal(verifyOverlap(value.pair, value.results, value.observations, value.inventory).observed_overlap_ms, 10000);
  }
  for (const mutate of [value => value.observations.samples = [], value => value.inventory.attempts.push(value.inventory.attempts[0]),
    value => value.inventory.complete_for_window = false,
    value => value.observations.samples.filter(sample => sample.run_id === 10002).forEach(sample => { sample.uid = 300; }),
    value => value.observations.samples.filter(sample => sample.run_id === 10002).forEach(sample => {
      sample.observed_at = sample.observed_at.replace('12:00:', '12:01:'); })]) {
    const value = overlapFixture(); mutate(value);
    assert.throws(() => verifyOverlap(value.pair, value.results, value.observations, value.inventory));
  }
});
