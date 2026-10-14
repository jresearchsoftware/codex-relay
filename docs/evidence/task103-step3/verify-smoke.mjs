// Offline readback reconciliation. Input must come from complete native reads
// and protected host collection; this script does not create execution evidence.
import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
import { pathToFileURL } from 'node:url';
import { admissionBinding, canonicalAuthorityJson, extractAuthorityRecord,
  sha256Body, validateAdmissionSnapshot } from '../../../contracts/src/github-authority.mjs';
import { TEST_REPOSITORIES } from './prepare-smoke.mjs';

const equal = (actual, expected, name) => assert.equal(canonicalAuthorityJson(actual), canonicalAuthorityJson(expected), name);
const pages = value => value.flat();
const time = value => { const result = Date.parse(value); assert(Number.isFinite(result), 'timestamp'); return result; };
const nativeId = value => { assert(Number.isSafeInteger(value) && value > 0, 'positive native ID'); return value; };

export function verifyCase(expected, data) {
  const { repository, task, run_id: runId, owner, writer_actor: writer, reviewer_actor: reviewer } = expected;
  const { issue, events, comments, run, claim, journal, pr } = data;
  assert(Object.hasOwn(TEST_REPOSITORIES, repository), 'only selected TEST repositories');
  nativeId(task); nativeId(runId); nativeId(writer.id);
  assert.equal(writer.login, 'jresearch-relay-test-writer[bot]');
  assert.equal(writer.type, 'Bot');
  nativeId(reviewer.id);
  assert.equal(reviewer.login, 'jresearch-relay-test-reviewer[bot]');
  assert.equal(reviewer.type, 'Bot');
  assert.equal(issue.repository_url, `https://api.github.com/repos/${repository}`);
  assert.equal(issue.number, task);
  assert.equal(run.id, runId);
  assert.equal(run.repository.full_name, repository);
  assert.equal(run.repository.id, TEST_REPOSITORIES[repository]);
  assert.equal(run.event, 'issues');
  assert.equal(run.path, expected.routing_workflow, 'configured trusted routing workflow');
  assert.equal(run.head_branch, expected.base_branch, 'trusted base-ref dispatch');
  assert.equal(run.run_attempt, 1, 'no Actions retry inference');
  assert.equal(run.status, 'completed');
  assert.equal(run.conclusion, 'success');
  assert.equal(run.actor.login, owner);
  assert.equal(run.triggering_actor.login, owner);
  assert(!claim.qualificationFixture && !journal.qualificationFixture && !claim.synthetic && !journal.synthetic,
    'synthetic protected state is excluded from real smoke proof');
  const e = claim.envelope;
  equal(journal.envelope, e, 'protected claim/journal envelope agreement');
  assert.equal(e.repository, repository);
  assert.equal(e.issueNumber, task);
  assert.equal(e.runId, runId);
  assert.equal(e.attemptId, `run-${runId}`);
  assert.equal(e.route, 'auto');
  assert.equal(e.transport, 'label');
  assert.equal(e.runName, run.display_title);
  assert.equal(e.readyLabel, 'codex-ready-auto');
  assert.equal(e.profile.cliModelId, 'gpt-6.1-sol');
  assert.equal(e.profile.effort, 'medium');
  assert.equal(e.subagentsAllowed, false);
  validateAdmissionSnapshot(e.request, { repository, task, route: 'auto', attempt: e.attemptId, step: e.step });
  assert.equal(e.request.run_id, String(runId));
  assert.equal(e.request.charter_sha256, sha256Body(issue.body));
  assert.equal(e.request.authority.charter.id, issue.id);
  assert.equal(e.request.authority.compatibility_request, null);
  assert.equal(e.request.authority.change_request, null, 'independent implementation smoke');
  for (const reference of e.request.authority.decisions) {
    const matches = pages(comments).filter(comment => comment.id === reference.id);
    assert.equal(matches.length, 1, 'each admitted Decision appears in complete native reads');
    const author = matches[0].user;
    equal({ id: author.id, login: author.login, type: author.type }, reviewer, 'trusted native Decision author');
    assert.equal(matches[0].performed_via_github_app.id, 5213202);
    assert.equal(matches[0].performed_via_github_app.slug, 'jresearch-relay-test-reviewer');
    assert.equal(sha256Body(matches[0].body), reference.sha256);
    const decision = extractAuthorityRecord(matches[0].body, { repository, task, charterBody: issue.body });
    assert.equal(decision.kind, 'decision');
    assert.equal(decision.schema_version, '4.0');
  }
  const ready = pages(events).filter(event => event.id === e.readyEventId);
  assert.equal(ready.length, 1, 'exact native ready event');
  assert.equal(ready[0].event, 'labeled');
  assert.equal(ready[0].label.name, 'codex-ready-auto');
  assert.equal(ready[0].actor.login, owner);
  assert.equal(ready[0].actor.type, 'User');
  assert.equal(ready[0].created_at, e.readyEventAt);
  assert.equal(ready[0].url, `https://api.github.com/repos/${repository}/issues/events/${e.readyEventId}`,
    'native event repository and ID; the complete read endpoint binds the Issue');
  const age = time(run.created_at) - time(e.readyEventAt);
  assert(age >= 0 && age <= 120000, 'ready event binds this first run');
  const execution = journal.execution;
  assert.equal(execution.reserved, true);
  assert.equal(execution.returned, true);
  assert.equal(execution.child, 'started');
  assert.equal(execution.containment, 'reaped');
  assert.equal(execution.result.status, 'success');
  assert.equal(execution.codexUsage.source, 'codex-exec-turn-completed');
  assert.equal(execution.codexUsage.scope, 'native-session-total');
  assert(Number.isSafeInteger(execution.codexUsage.input_tokens) && Number.isSafeInteger(execution.codexUsage.output_tokens)
    && execution.codexUsage.input_tokens > 0 && execution.codexUsage.output_tokens > 0,
    'observed native model usage, not requested-profile inference');
  assert.equal(journal.collection.clean, true);
  assert(claim.outcome && journal.outcome, 'separate terminal native publication receipts');
  assert.equal(claim.outcome.outcomeId, journal.outcome.outcomeId);
  const marker = `<!-- relay:run-${runId}:outcome -->`;
  const outcomes = pages(comments).filter(comment => comment.body?.includes(marker));
  assert.equal(outcomes.length, 1, 'exactly one Outcome across complete Issue/PR comment pages');
  const comment = outcomes[0];
  assert.equal(comment.id, claim.outcome.outcomeId);
  equal(comment.user && { id: comment.user.id, login: comment.user.login, type: comment.user.type }, writer, 'native Writer actor');
  assert.equal(comment.performed_via_github_app.id, 5213167);
  assert.equal(comment.performed_via_github_app.slug, 'jresearch-relay-test-writer');
  assert.equal(sha256Body(comment.body), claim.outcome.bodySha256);
  const result = extractAuthorityRecord(comment.body, { repository, task, charterBody: issue.body });
  assert.equal(result.kind, 'outcome');
  assert.equal(result.schema_version, '4.0');
  assert.equal(result.status, 'implemented');
  assert.equal(result.attempt, e.attemptId);
  assert.equal(result.step, e.step);
  equal(result.admission, admissionBinding(e.request), 'exact protected admission digest');
  equal(result.authority, e.request.authority, 'immutable authority source');
  equal(result.authority_resolution, e.request.authority_resolution, 'captured admission resolution');
  assert(result.result.identities.some(identity => identity.kind === 'github-actions-run' && identity.id === String(runId)));
  assert.equal(result.result.kind, 'git', 'one-file smoke produced a real result');
  assert.equal(result.result.revision, claim.publishedHead);
  assert.equal(result.result.revision, journal.outcome.head);
  assert.notEqual(result.result.revision, e.startHead);
  assert.equal(result.parent.kind, 'pull_request');
  assert.equal(result.parent.number, claim.prNumber);
  assert.equal(pr.number, claim.prNumber);
  assert.equal(pr.head.repo.full_name, repository);
  assert.equal(pr.head.repo.id, TEST_REPOSITORIES[repository]);
  assert.equal(pr.base.repo.full_name, repository);
  assert.equal(pr.base.repo.id, TEST_REPOSITORIES[repository]);
  assert.equal(pr.head.ref, e.branch);
  assert.equal(pr.head.sha, result.result.revision, 'exact live fixture PR result head');
  assert.equal(pr.state, 'open');
  assert.equal(pr.merged, false);
  assert(pr.body.includes(`Related to #${task}`));
  assert(pr.body.includes(`Execution admission digest: ${result.admission.sha256}`));
  return { name: expected.name, repository, task, run_id: runId, attempt: e.attemptId, step: e.step,
    ready_event_id: e.readyEventId, admission: result.admission, execution_slot: e.executionSlot ?? null,
    head: result.result.revision, outcome_id: comment.id, outcome_url: comment.html_url,
    outcome_body_sha256: sha256Body(comment.body), native_usage: execution.codexUsage,
    requested_profile: e.profile, actual_profile: 'UNAVAILABLE', warnings: result.warnings };
}

export function verifyOverlap(pair, results, observations, inventory) {
  assert.equal(observations.source, 'trusted-host-procfs');
  assert.equal(observations.complete_for_window, true);
  assert.equal(inventory.complete_for_window, true, 'complete protected execution inventory required');
  assert.equal(pair.cases.length, 2);
  const selected = pair.cases.map(name => { const item = results.find(result => result.name === name);
    assert(item, 'pair case exists'); return item; });
  assert.notEqual(`${selected[0].repository}#${selected[0].task}`, `${selected[1].repository}#${selected[1].task}`,
    'independent fixture Tasks');
  if (pair.kind === 'same-repository') assert.equal(selected[0].repository, selected[1].repository);
  else { assert.equal(pair.kind, 'cross-repository'); assert.notEqual(selected[0].repository, selected[1].repository); }
  const intervals = selected.map(result => {
    const attempts = inventory.attempts.filter(attempt => attempt.repository === result.repository
      && attempt.task === result.task && attempt.step === result.step && attempt.child === 'started');
    assert.equal(attempts.length, 1, 'one inference per admitted Task/Step across complete inventory');
    assert.equal(attempts[0].attempt, result.attempt);
    const events = inventory.attempts.filter(attempt => attempt.repository === result.repository
      && attempt.ready_event_id === result.ready_event_id && attempt.child === 'started');
    assert.equal(events.length, 1, 'one inference per consumed ready event');
    const samples = observations.samples.filter(sample => sample.repository === result.repository
      && sample.run_id === result.run_id).sort((a, b) => time(a.observed_at) - time(b.observed_at));
    assert(samples.length >= 2, 'two protected host observations of the actual Codex process');
    const first = samples[0];
    nativeId(first.pid); assert(first.uid > 0 && Number.isSafeInteger(first.uid));
    assert(/^[0-9]+$/.test(String(first.proc_start_ticks)));
    assert(first.executable.endsWith('/codex'), 'observed Codex executable, not launcher/Actions interval');
    assert.equal(first.command_role, 'codex-exec');
    assert(first.cgroup && first.host && first.execution_slot, 'host/cgroup/slot attribution');
    for (const sample of samples) {
      for (const key of ['pid', 'uid', 'proc_start_ticks', 'cgroup', 'host', 'executable', 'command_role', 'execution_slot'])
        assert.equal(sample[key], first[key], `stable observed process ${key}`);
      assert.equal(sample.attempt, result.attempt);
      assert.notEqual(sample.process_state, 'Z', 'live process, not zombie');
    }
    if (result.execution_slot) assert.equal(first.execution_slot, result.execution_slot);
    return { repository: result.repository, run_id: result.run_id, host: first.host,
      pid: first.pid, uid: first.uid, execution_slot: first.execution_slot, cgroup: first.cgroup,
      proc_start_ticks: first.proc_start_ticks, first_observed: first.observed_at, last_observed: samples.at(-1).observed_at };
  });
  assert.equal(intervals[0].host, intervals[1].host, 'shared physical TEST host');
  assert.notEqual(intervals[0].pid, intervals[1].pid);
  assert.notEqual(intervals[0].uid, intervals[1].uid, 'independent worker identity');
  assert.notEqual(intervals[0].cgroup, intervals[1].cgroup);
  assert.notEqual(`${intervals[0].repository}/${intervals[0].execution_slot}`, `${intervals[1].repository}/${intervals[1].execution_slot}`);
  const start = Math.max(...intervals.map(interval => time(interval.first_observed)));
  const end = Math.min(...intervals.map(interval => time(interval.last_observed)));
  assert(end > start, 'actual Codex process overlap must be observed');
  return { kind: pair.kind, observed_overlap_ms: end - start,
    observed_from: new Date(start).toISOString(), observed_to: new Date(end).toISOString(), intervals };
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const [manifestPath, output] = process.argv.slice(2);
  assert(output, 'usage: verify-smoke.mjs READBACK_MANIFEST.json OUTPUT.json');
  const root = dirname(resolve(manifestPath));
  const hashes = {};
  const read = async path => { const bytes = await readFile(resolve(root, path), 'utf8');
    hashes[path] = sha256Body(bytes); return JSON.parse(bytes); };
  const manifest = await read(manifestPath.startsWith(root) ? manifestPath : resolve(manifestPath));
  assert.equal(manifest.collected_by, 'owner-local-manual');
  assert.equal(manifest.native_reads_complete, true, 'all --paginate --slurp pages, including fixture PR comments');
  const results = [];
  for (const expected of manifest.cases) {
    const data = {};
    for (const name of ['issue', 'events', 'run', 'claim', 'journal', 'pr']) data[name] = await read(expected.files[name]);
    data.comments = (await Promise.all(expected.files.comments.map(read))).flatMap(pages);
    results.push(verifyCase(expected, data));
  }
  assert.equal(new Set(results.map(result => `${result.repository}/${result.run_id}`)).size, results.length);
  assert.equal(new Set(results.map(result => `${result.repository}/${result.outcome_id}`)).size, results.length);
  const observations = await read(manifest.host_observations);
  const inventory = await read(manifest.execution_inventory);
  const overlaps = manifest.pairs.map(pair => verifyOverlap(pair, results, observations, inventory));
  const receipt = { status: 'PASS', observed_at: new Date().toISOString(), cases: results, overlaps,
    input_sha256: hashes, limitations: ['Readback verification trusts the owner-local collector provenance and complete-window declarations.',
      'Live Codex process overlap plus protected native usage proves overlapping automatic model invocations; simultaneous GPU/network computation is not measured.',
      'Duplicate suppression is bounded to the collected ready-event/Task/Step window; independent acceptance, merge, PROD and closure are not asserted.'] };
  await writeFile(output, JSON.stringify(receipt, null, 2) + '\n');
  console.log(JSON.stringify(receipt));
}
