// Deterministic inputs only. Passing these tests is not live qualification.
import assert from 'node:assert/strict';
import test from 'node:test';
import { verifyInstallation, verifyOverlap, verifyOccupancy, verifyNativeCase } from './verify-smoke.mjs';
import { charter, prepareDecision, purpose, TEST_REPOSITORIES } from './prepare-smoke.mjs';
import { admissionBinding, createAdmissionSnapshot, renderAuthorityRecord, resolveTaskAuthority, sha256Body } from '../../../contracts/src/github-authority.mjs';

const candidate = 'a'.repeat(40), repoA = Object.keys(TEST_REPOSITORIES)[0], repoB = Object.keys(TEST_REPOSITORIES)[1];
const writer = { id: 8001, login: 'jresearch-relay-test-writer[bot]', type: 'Bot' };
const reviewer = { id: 8002, login: 'jresearch-relay-test-reviewer[bot]', type: 'Bot' };
const owner = { id: 8003, login: 'fixture-owner', type: 'User' };
function nativeCase(variant, task, runId, runner) {
  const repository = { full_name: variant === 'cross-b' ? repoB : repoA, id: TEST_REPOSITORIES[variant === 'cross-b' ? repoB : repoA] };
  const issue = { id: task + 1000, number: task, title: purpose(variant), body: charter(variant), labels: [], state: 'open',
    repository_url: `https://api.github.com/repos/${repository.full_name}` };
  const decision = prepareDecision({ variant, repository, issue, main: { sha: candidate } }).record;
  const parent = { kind: 'issue', number: task };
  const nativeDecision = { kind: 'issue-comment', repository: repository.full_name, id: task + 2000,
    parent, body: renderAuthorityRecord(decision), author: reviewer };
  const resolved = resolveTaskAuthority([{ kind: 'issue-body', repository: repository.full_name, id: issue.id, parent, body: issue.body, author: owner }, nativeDecision],
    { repository: repository.full_name, task, charterId: issue.id, charterBody: issue.body, trustedAuthor: reviewer,
      route: 'auto', projectDefaults: { model: 'gpt-6.1-sol', effort: 'medium', subagents: false, validation: ['diff-check', 'secret-scan'] },
      purpose: issue.title, startingState: { branch: decision.amendments.branch, base_sha: candidate, starting_head: candidate, existing_pr: null } });
  const admission = createAdmissionSnapshot(resolved, { step: 1, attempt: `run-${runId}`, runId });
  const envelope = { repository: repository.full_name, issueNumber: task, runId, attemptId: `run-${runId}`, route: 'auto', transport: 'label',
    runName: `Automatic fixture ${task}`, executionSlot: runner.id, readyLabel: 'codex-ready-auto', readyEventId: task + 3000, readyEventAt: '2026-10-15T12:00:00Z',
    step: 1, request: admission, branch: admission.branch, startHead: candidate, profile: { cliModelId: 'gpt-6.1-sol', effort: 'medium' }, subagentsAllowed: false };
  const record = { schema_version: '4.0', kind: 'outcome', repository: repository.full_name, task, parent: { kind: 'pull_request', number: task + 50 },
    charter_sha256: sha256Body(issue.body), step: 1, authority: admission.authority, admission: admissionBinding(admission), authority_resolution: admission.authority_resolution,
    attempt: envelope.attemptId, status: 'implemented', result: { kind: 'git', revision: 'b'.repeat(40), identities: [{ kind: 'github-actions-run', id: String(runId) }] },
    summary: 'Deterministic verifier fixture.', warnings: [], limitations: ['Not real evidence.'] };
  const outcome = { id: task + 4000, user: writer, body: renderAuthorityRecord(record) + `\n<!-- relay:run-${runId}:outcome -->`,
    html_url: `https://github.com/${repository.full_name}/pull/${task + 50}#issuecomment-${task + 4000}`,
    performed_via_github_app: { id: 5213167, slug: 'jresearch-relay-test-writer' } };
  const receipt = { outcomeId: outcome.id, bodySha256: sha256Body(outcome.body), head: record.result.revision };
  const job = { id: runId + 9000, run_id: runId, run_attempt: 1, runner_id: runner.runner_id, runner_name: runner.runner_name,
    runner_group_id: 6, status: 'completed', conclusion: 'success', started_at: '2026-10-15T12:00:03Z', completed_at: '2026-10-15T12:01:00Z' };
  return { expected: { name: variant, repository: repository.full_name, task, run_id: runId, owner: owner.login, writer_actor: writer,
    reviewer_actor: reviewer, routing_workflow: '.github/workflows/test-routing.yml', base_branch: 'main', job_id: job.id },
  data: { issue, comments: [{ ...nativeDecision, user: reviewer, performed_via_github_app: { id: 5213202, slug: 'jresearch-relay-test-reviewer' } }, outcome],
    events: [{ id: envelope.readyEventId, event: 'labeled', label: { name: envelope.readyLabel }, actor: owner, created_at: envelope.readyEventAt,
      url: `https://api.github.com/repos/${repository.full_name}/issues/events/${envelope.readyEventId}` }],
    run: { id: runId, repository, event: 'issues', run_attempt: 1, path: '.github/workflows/test-routing.yml', head_branch: 'main', status: 'completed',
      conclusion: 'success', actor: owner, triggering_actor: owner, display_title: envelope.runName, created_at: '2026-10-15T12:00:02Z' },
    jobs: { total_count: 1, jobs: [job] }, claim: { envelope, outcome: receipt, publishedHead: record.result.revision, prNumber: task + 50 },
    journal: { envelope, outcome: receipt, collection: { clean: true }, execution: { reserved: true, returned: true, child: 'started', containment: 'reaped',
      result: { status: 'success' }, codexUsage: { source: 'codex-exec-turn-completed', scope: 'native-session-total', input_tokens: 100, output_tokens: 25 } } },
    pr: { number: task + 50, state: 'open', merged: false, head: { repo: repository, ref: envelope.branch, sha: record.result.revision }, base: { repo: repository },
      body: `Related to #${task}\nExecution admission digest: ${record.admission.sha256}` } } };
}
function fixture(cross = false) {
  const members = [1, 2].map(n => ({ id: n === 1 ? 'primary' : 'pool-2', runner_id: 50 + n, runner_name: `relay-test-pool-${n}`, runner_uid: 900, unit: `relay-test-pool-pool-${n}.service`, cgroup: `/offline/runner-${n - 1}` }));
  const installed = { source: 'trusted-root-installed-readback', candidate, host: 'offline-host', complete: true, gaps: [], pool_manifest_sha256: 'f'.repeat(64),
    configurations: [repoA, repoB].map(repository => ({ repository, runtime_uid: 300, candidate, pool_id: 'relay-test-pool', sha256: 'c'.repeat(64),
      execution_slots: Array.from({ length: 32 }, (_, n) => ({ id: n === 0 ? 'primary' : `pool-${n + 1}`,
        runtime_uid: 300, runner_uid: 900, work_group: 'fixture-work', work_gid: 700 })) })),
    pool: { id: 'relay-test-pool', desired_capacity: 2, runner_group_id: 6, members } };
  const native = { native_reads_complete: true, group: { id: 6, visibility: 'selected', allows_public_repositories: false,
    restricted_to_workflows: true, selected_workflows: [repoA, repoB].flatMap(repo =>
      ['codex-relay-routing.yml', 'manual-writer-publication-recovery.yml'].map(name => `${repo}/.github/workflows/${name}@refs/heads/main`)) },
    repositories: Object.entries(TEST_REPOSITORIES).map(([full_name, id]) => ({ full_name, id })), runners: members.map(value => ({ id: value.runner_id, name: value.runner_name, status: 'online' })) };
  const cases = [nativeCase(cross ? 'cross-a' : 'same-a', 101, 10001, members[0]), nativeCase(cross ? 'cross-b' : 'same-b', 102, 10002, members[1])];
  const results = cases.map(value => verifyNativeCase(value.expected, value.data, installed));
  const times = ['2026-10-15T12:00:10Z', '2026-10-15T12:00:12Z'];
  const observations = { source: 'trusted-host-procfs', complete_for_window: true, candidate, gaps: [], samples: results.flatMap((result, index) => times.map(observed_at => {
    const checkout = `/var/lib/codex-relay-test/work/${result.attempt}`, environment_paths = {}, directory_metadata = {};
    for (const [key, suffix] of Object.entries({ HOME: 'home', CODEX_HOME: 'home', XDG_CACHE_HOME: 'cache', XDG_CONFIG_HOME: 'config', XDG_DATA_HOME: 'data', XDG_STATE_HOME: 'state', TMPDIR: 'tmp' })) {
      environment_paths[key] = `${checkout}/.codex-sandbox/${suffix}`; directory_metadata[key] = { uid: 900, gid: 700, mode: '0o2770', dev: 1,
        inode: index * 100 + 10 + ['home', 'cache', 'config', 'data', 'state', 'tmp'].indexOf(suffix) };
    }
    return { observed_at, repository: result.repository, run_id: result.run_id, attempt: result.attempt, pid: 200 + index, uid: 300,
      proc_start_ticks: '12345', executable: '/opt/test/codex', command_role: 'codex-exec', process_state: 'S', cgroup: `/offline/runner-${index}`,
      host: installed.host, runner_name: result.runner_name, runner_id: result.runner_id, runner_service: members[index].unit, pool_id: installed.pool.id,
      execution_slot: result.execution_slot, process_gid: 300, process_groups: [700], checkout, environment_paths, directory_metadata };
  })), scan_counts: times.map(observed_at => ({ observed_at, active_attributable_codex: 2 })) };
  const inventory = { complete_for_window: true, gaps: [], attempts: results.map(result => ({ ...result, child: 'started' })) };
  return { installed, native, cases, results, observations, inventory, pair: { kind: cross ? 'cross-repository' : 'same-repository', cases: results.map(value => value.name) } };
}
test('exact protected candidate, native group and same/cross repository shared UID overlap', () => {
  for (const cross of [false, true]) {
    const f = fixture(cross); verifyInstallation(f.installed, candidate, f.native);
    assert.equal(verifyOverlap(f.pair, f.results, f.observations, f.inventory, f.installed).observed_overlap_ms, 2000);
    assert.equal(verifyOccupancy(f.observations, f.installed).peak_observed_models, 2);
  }
});

test('complete group inventory preserves offline legacy registrations without increasing pool capacity', () => {
  const f = fixture();
  f.native.runners.push({ id: 99, name: 'historical-test-runner', status: 'offline', busy: false,
    labels: [{ name: 'self-hosted' }, { name: 'legacy-test' }] });
  verifyInstallation(f.installed, candidate, f.native);
  for (const change of [runner => runner.status = 'online', runner => runner.busy = true,
    runner => runner.name = f.installed.pool.id + '-15',
    runner => runner.labels.push({ name: `relay-pool-${sha256Body(f.installed.pool.id).slice(0, 24)}` })]) {
    const value = structuredClone(f); change(value.native.runners.at(-1));
    assert.throws(() => verifyInstallation(value.installed, candidate, value.native));
  }
});
test('reject copied identities, stale candidate, extra physical pool members and widened native access', () => {
  for (const mutate of [f => f.installed.candidate = 'd'.repeat(40), f => f.installed.configurations[1].pool_id = 'other',
    f => f.native.runners.push({ id: 99, name: 'foreign', status: 'online' }), f => f.native.group.visibility = 'all',
    f => f.native.group.selected_workflows[0] = `${repoA}/.github/workflows/untrusted.yml@refs/heads/candidate`]) {
    const f = fixture(); mutate(f); assert.throws(() => verifyInstallation(f.installed, candidate, f.native));
  }
  for (const mutate of [f => f.data.jobs.jobs[0].runner_id++, f => f.data.jobs.total_count++, f => f.data.run.run_attempt++,
    f => f.data.journal.execution.codexUsage.output_tokens = 0, f => f.data.comments.push(f.data.comments[1]), f => f.data.pr.head.sha = 'e'.repeat(40)]) {
    const f = fixture(), value = structuredClone(f.cases[0]); mutate(value); assert.throws(() => verifyNativeCase(value.expected, value.data, f.installed));
  }
});
test('reject process gaps, distinct UID substitution, shared HOME inode, duplicate inference and hidden occupancy', () => {
  for (const mutate of [f => f.observations.complete_for_window = false, f => f.observations.samples = [],
    f => f.observations.samples.filter(v => v.run_id === 10002).forEach(v => v.uid++),
    f => f.observations.samples.filter(v => v.run_id === 10002).forEach(v => v.directory_metadata.HOME.inode = f.observations.samples[0].directory_metadata.HOME.inode),
    f => f.observations.samples[0].environment_paths.HOME = '/home/shared', f => f.inventory.attempts.push(f.inventory.attempts[0]),
    f => f.observations.samples.filter(v => v.run_id === 10002).forEach(v => v.observed_at = v.observed_at.replace('12:00:', '12:01:'))]) {
    const f = fixture(); mutate(f); assert.throws(() => verifyOverlap(f.pair, f.results, f.observations, f.inventory, f.installed));
  }
  const f = fixture(); f.observations.scan_counts[0].active_attributable_codex++; assert.throws(() => verifyOccupancy(f.observations, f.installed));
});
test('repository-specific UID probe is explicit and cannot be passed off as shared default', () => {
  const f = fixture(true);
  f.installed.configurations[1].runtime_uid = 301;
  f.installed.configurations[1].execution_slots.forEach(slot => slot.runtime_uid = 301);
  for (const sample of f.observations.samples.filter(value => value.repository === repoB)) {
    sample.uid = 301;
    for (const directory of Object.values(sample.directory_metadata)) directory.uid = 301;
  }
  assert.throws(() => verifyOverlap(f.pair, f.results, f.observations, f.inventory, f.installed));
  f.pair.identity_mode = 'repository-override';
  assert.equal(verifyOverlap(f.pair, f.results, f.observations, f.inventory, f.installed).identity_mode, 'repository-override');
});

test('directory evidence uses protected slot ownership and actual process groups', () => {
  const f = fixture();
  assert.equal(verifyOverlap(f.pair, f.results, f.observations, f.inventory, f.installed).observed_overlap_ms, 2000);
  for (const sample of f.observations.samples) for (const entry of Object.values(sample.directory_metadata)) entry.uid = sample.uid;
  assert.equal(verifyOverlap(f.pair, f.results, f.observations, f.inventory, f.installed).observed_overlap_ms, 2000);
  for (const change of [sample => sample.directory_metadata.HOME.uid = 1,
    sample => sample.directory_metadata.HOME.gid++, sample => sample.directory_metadata.HOME.mode = '0o777',
    sample => sample.process_groups = [], sample => sample.directory_metadata.XDG_CACHE_HOME.inode = sample.directory_metadata.HOME.inode,
    sample => sample.execution_slot = 'pool-32']) {
    const value = fixture(); change(value.observations.samples[0]);
    assert.throws(() => verifyOverlap(value.pair, value.results, value.observations, value.inventory, value.installed));
  }
});
