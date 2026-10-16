// Offline reconciliation only. This never creates native or protected evidence.
import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
import { pathToFileURL } from 'node:url';
import { verifyCase } from '../task103-step3/verify-smoke.mjs';
import { TEST_REPOSITORIES } from '../task103-step3/prepare-smoke.mjs';
import { sha256Body } from '../../../contracts/src/github-authority.mjs';

const timestamp = value => { const n = Date.parse(value); assert(Number.isFinite(n), 'native timestamp'); return n; };
const id = value => assert(Number.isSafeInteger(value) && value > 0, 'positive native identity');
const keys = ['HOME', 'CODEX_HOME', 'XDG_CACHE_HOME', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_STATE_HOME', 'TMPDIR'];
const suffixes = { HOME: 'home', CODEX_HOME: 'home', XDG_CACHE_HOME: 'cache', XDG_CONFIG_HOME: 'config',
  XDG_DATA_HOME: 'data', XDG_STATE_HOME: 'state', TMPDIR: 'tmp' };

export function verifyNativeCase(expected, data, installed) {
  const result = verifyCase(expected, data); // Current v4 authority, exact actors/head, native usage and one terminal Outcome.
  assert.equal(data.jobs.total_count, data.jobs.jobs.length, 'all native job pages must be present');
  const jobs = data.jobs.jobs.filter(job => job.id === expected.job_id);
  assert.equal(jobs.length, 1, 'exact native automatic execution job');
  const job = jobs[0]; id(job.id); id(job.runner_id);
  assert.equal(job.run_id, result.run_id);
  assert.equal(job.run_attempt, 1);
  assert.equal(job.status, 'completed'); assert.equal(job.conclusion, 'success');
  const member = installed.pool.members.find(value => value.runner_name === job.runner_name);
  assert(member, 'job belongs to the physical shared pool');
  assert.equal(job.runner_id, member.runner_id, 'native registration identity, not a copied runner name');
  assert.equal(job.runner_group_id, installed.pool.runner_group_id);
  assert(timestamp(job.started_at) >= timestamp(data.run.created_at));
  assert(timestamp(job.completed_at) > timestamp(job.started_at));
  return { ...result, job_id: job.id, runner_id: job.runner_id, runner_name: job.runner_name,
    runner_group_id: job.runner_group_id, job_started_at: job.started_at, job_completed_at: job.completed_at };
}

export function verifyInstallation(installed, expectedCandidate, nativePool) {
  assert.match(expectedCandidate, /^[a-f0-9]{40}$/);
  assert.equal(installed.source, 'trusted-root-installed-readback');
  assert.equal(installed.candidate, expectedCandidate, 'exact candidate installed on TEST');
  assert.equal(installed.complete, true); assert.deepEqual(installed.gaps, []);
  assert.match(installed.pool_manifest_sha256, /^[a-f0-9]{64}$/, 'protected physical pool manifest readback');
  assert.equal(installed.configurations.length, 2, 'both exact protected repository configurations');
  assert.deepEqual(new Set(installed.configurations.map(value => value.repository)), new Set(Object.keys(TEST_REPOSITORIES)));
  for (const config of installed.configurations) {
    assert.equal(config.candidate, expectedCandidate);
    assert.match(config.sha256, /^[a-f0-9]{64}$/);
    assert.equal(config.pool_id, installed.pool.id, 'one pool across both repositories');
    id(config.runtime_uid);
    assert.deepEqual(config.execution_slots.map(slot => slot.id), ['primary', ...Array.from({ length: 31 }, (_, n) => `pool-${n + 2}`)]);
    for (const slot of config.execution_slots) {
      id(slot.runtime_uid); id(slot.runner_uid);
      assert(Number.isSafeInteger(slot.work_gid) && slot.work_gid >= 0);
      assert.notEqual(slot.runtime_uid, slot.runner_uid);
      assert.match(slot.work_group, /^[a-z_][a-z0-9_-]*$/);
    }
  }
  const { pool } = installed; id(pool.desired_capacity); id(pool.runner_group_id);
  assert(pool.desired_capacity >= 2 && pool.desired_capacity <= 32);
  assert.equal(pool.members.length, pool.desired_capacity, 'fixed qualified capacity, not per-repository multiplication');
  for (const key of ['id', 'runner_name', 'runner_id', 'unit'])
    assert.equal(new Set(pool.members.map(member => member[key])).size, pool.members.length, `unique physical member ${key}`);
  for (const member of pool.members) { id(member.runner_id); id(member.runner_uid); assert(member.unit.endsWith('.service')); }
  assert.equal(nativePool.native_reads_complete, true);
  assert.equal(nativePool.group.id, pool.runner_group_id);
  assert.equal(nativePool.group.visibility, 'selected');
  assert.equal(nativePool.group.allows_public_repositories, false);
  assert.equal(nativePool.group.restricted_to_workflows, true);
  assert.deepEqual(new Set(nativePool.repositories.map(repo => `${repo.full_name}:${repo.id}`)),
    new Set(Object.entries(TEST_REPOSITORIES).map(([name, number]) => `${name}:${number}`)));
  const trustedRefs = Object.keys(TEST_REPOSITORIES).flatMap(repo =>
    ['codex-relay-routing.yml', 'manual-writer-publication-recovery.yml'].map(name => `${repo}/.github/workflows/${name}@refs/heads/main`));
  assert.deepEqual(new Set(nativePool.group.selected_workflows), new Set(trustedRefs), 'exact trusted TEST main workflow refs');
  const poolLabel = `relay-pool-${sha256Body(pool.id).slice(0, 24)}`;
  const managedIds = new Set(pool.members.map(member => member.runner_id));
  // Preserve complete group inventory without forcing deletion of historical
  // registrations. An offline, unlabelled legacy member cannot add pool jobs.
  for (const runner of nativePool.runners.filter(value => !managedIds.has(value.id))) {
    assert.equal(runner.status, 'offline'); assert.equal(runner.busy, false);
    assert(!runner.name.startsWith(pool.id), 'no unaccounted managed physical member');
    assert(Array.isArray(runner.labels) && !runner.labels.some(label => label.name === poolLabel), 'legacy runner cannot receive pool jobs');
  }
  for (const member of pool.members) {
    const matches = nativePool.runners.filter(runner => runner.id === member.runner_id && runner.name === member.runner_name);
    assert.equal(matches.length, 1); assert.equal(matches[0].status, 'online');
  }
  return pool;
}

export function verifyOverlap(pair, results, observations, inventory, installed) {
  assert.equal(observations.source, 'trusted-host-procfs');
  assert.equal(observations.complete_for_window, true); assert.deepEqual(observations.gaps, []);
  assert.equal(inventory.complete_for_window, true); assert.deepEqual(inventory.gaps, []);
  assert.equal(observations.candidate, installed.candidate);
  assert.equal(pair.cases.length, 2);
  const selected = pair.cases.map(name => { const value = results.find(result => result.name === name); assert(value); return value; });
  assert.notEqual(`${selected[0].repository}#${selected[0].task}`, `${selected[1].repository}#${selected[1].task}`);
  if (pair.kind === 'same-repository') assert.equal(selected[0].repository, selected[1].repository);
  else { assert.equal(pair.kind, 'cross-repository'); assert.notEqual(selected[0].repository, selected[1].repository); }
  const streams = selected.map(result => {
    const attempts = inventory.attempts.filter(value => value.repository === result.repository && value.task === result.task
      && value.step === result.step && value.child === 'started');
    assert.equal(attempts.length, 1, 'one observed inference for original Task/Step');
    assert.equal(attempts[0].attempt, result.attempt);
    assert.equal(inventory.attempts.filter(value => value.repository === result.repository
      && value.ready_event_id === result.ready_event_id && value.child === 'started').length, 1, 'one inference for consumed event');
    const samples = observations.samples.filter(sample => sample.repository === result.repository && sample.run_id === result.run_id)
      .sort((a, b) => timestamp(a.observed_at) - timestamp(b.observed_at));
    assert(samples.length >= 2, 'two actual process observations required');
    const first = samples[0]; id(first.pid); id(first.uid);
    assert.equal(first.runner_name, result.runner_name); assert.equal(first.runner_id, result.runner_id);
    assert.equal(first.pool_id, installed.pool.id); assert.equal(first.host, installed.host);
    assert.match(String(first.proc_start_ticks), /^[0-9]+$/);
    assert(first.executable.endsWith('/codex')); assert.equal(first.command_role, 'codex-exec');
    const member = installed.pool.members.find(value => value.runner_id === first.runner_id);
    assert.equal(first.runner_service, member.unit);
    assert.equal(first.cgroup, member.cgroup, 'actual systemctl cgroup binding');
    const config = installed.configurations.find(value => value.repository === result.repository);
    const binding = config.execution_slots.find(value => value.id === result.execution_slot);
    assert(binding, 'original execution slot comes from protected consumer configuration');
    assert.equal(first.execution_slot, result.execution_slot);
    assert.equal(first.uid, binding.runtime_uid);
    assert.equal(member.runner_uid, binding.runner_uid);
    for (const sample of samples) {
      for (const key of ['pid', 'uid', 'proc_start_ticks', 'executable', 'cgroup', 'runner_id', 'runner_name', 'runner_service', 'checkout', 'execution_slot', 'process_gid'])
        assert.equal(sample[key], first[key], `stable process ${key}`);
      assert(Number.isSafeInteger(sample.process_gid) && sample.process_gid >= 0);
      assert(Array.isArray(sample.process_groups) && sample.process_groups.every(value => Number.isSafeInteger(value) && value >= 0));
      assert.deepEqual(sample.process_groups, first.process_groups, 'stable observed supplementary groups');
      const actualGroups = new Set([sample.process_gid, ...sample.process_groups]);
      const identities = new Map();
      assert.equal(sample.attempt, result.attempt); assert.equal(sample.host, installed.host);
      assert.notEqual(sample.process_state, 'Z');
      assert(timestamp(sample.observed_at) >= timestamp(result.job_started_at));
      assert(timestamp(sample.observed_at) <= timestamp(result.job_completed_at));
      for (const key of keys) {
        assert.equal(sample.environment_paths[key], `${sample.checkout}/.codex-sandbox/${suffixes[key]}`, `actual bounded ${key}`);
        const directory = sample.directory_metadata[key];
        assert([binding.runner_uid, binding.runtime_uid].includes(directory.uid), 'configured runner/runtime directory owner');
        assert.equal(directory.gid, binding.work_gid, 'protected execution slot work group');
        assert(['0o770', '0o2770'].includes(directory.mode), 'private owner/group writable sandbox directory');
        assert(directory.uid === sample.uid || actualGroups.has(directory.gid), 'observed process has owner or group rwx access');
        id(directory.inode); assert(Number.isInteger(directory.dev));
        const identity = `${directory.dev}:${directory.inode}`, path = sample.environment_paths[key];
        assert(!identities.has(identity) || identities.get(identity) === path, 'distinct sandbox paths cannot alias one inode');
        identities.set(identity, path);
      }
    }
    return samples;
  });
  const identityMode = pair.identity_mode ?? 'shared-default';
  if (identityMode === 'shared-default') assert.equal(streams[0][0].uid, streams[1][0].uid, 'shared default non-root Codex UID');
  else {
    assert.equal(identityMode, 'repository-override', 'explicit supported identity probe');
    assert.equal(pair.kind, 'cross-repository');
    assert.notEqual(streams[0][0].uid, streams[1][0].uid, 'observed protected repository UID override');
  }
  assert.notEqual(streams[0][0].pid, streams[1][0].pid);
  assert.notEqual(streams[0][0].runner_id, streams[1][0].runner_id);
  assert.notEqual(streams[0][0].cgroup, streams[1][0].cgroup);
  assert.notEqual(streams[0][0].checkout, streams[1][0].checkout);
  for (const key of keys) {
    assert.notEqual(streams[0][0].environment_paths[key], streams[1][0].environment_paths[key]);
    assert.notEqual(`${streams[0][0].directory_metadata[key].dev}:${streams[0][0].directory_metadata[key].inode}`,
      `${streams[1][0].directory_metadata[key].dev}:${streams[1][0].directory_metadata[key].inode}`, 'distinct actual directory inode');
  }
  const other = new Set(streams[1].map(sample => sample.observed_at));
  const shared = streams[0].filter(sample => other.has(sample.observed_at)).map(sample => sample.observed_at);
  assert(shared.length >= 2, 'same two bounded host scans contain both actual processes');
  for (let index = 1; index < shared.length; index++) assert(timestamp(shared[index]) - timestamp(shared[index - 1]) <= 5000, 'no unobserved interval bridged');
  const overlap = timestamp(shared.at(-1)) - timestamp(shared[0]); assert(overlap > 0);
  return { kind: pair.kind, identity_mode: identityMode, observed_overlap_ms: overlap, observed_from: shared[0], observed_to: shared.at(-1),
    uids: streams.map(samples => samples[0].uid), runner_ids: streams.map(samples => samples[0].runner_id) };
}

export function verifyOccupancy(observations, installed) {
  assert(observations.scan_counts.length >= 2);
  const times = new Set(observations.scan_counts.map(scan => scan.observed_at));
  assert.equal(times.size, observations.scan_counts.length, 'unique closed scan times');
  for (const sample of observations.samples) assert(times.has(sample.observed_at), 'every process sample counted globally');
  let peak = 0;
  for (const scan of observations.scan_counts) {
    const samples = observations.samples.filter(sample => sample.observed_at === scan.observed_at);
    assert.equal(scan.active_attributable_codex, samples.length);
    assert.equal(new Set(samples.map(sample => sample.runner_id)).size, samples.length, 'one model per physical runner');
    assert(samples.length <= installed.pool.desired_capacity, 'global cross-repository occupancy bound');
    for (const sample of samples) assert(installed.pool.members.some(member => member.runner_id === sample.runner_id), 'no unconfigured pool member');
    peak = Math.max(peak, samples.length);
  }
  assert(peak >= 2, 'real pool concurrency');
  return { peak_observed_models: peak, desired_capacity: installed.pool.desired_capacity, samples: observations.scan_counts.length };
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const [manifestPath, output] = process.argv.slice(2); assert(output, 'usage: verify-smoke.mjs MANIFEST.json RECEIPT.json');
  const root = dirname(resolve(manifestPath)), hashes = {};
  const read = async path => { const full = resolve(root, path), bytes = await readFile(full, 'utf8'); hashes[full] = sha256Body(bytes); return JSON.parse(bytes); };
  const manifest = await read(resolve(manifestPath));
  assert.equal(manifest.collected_by, 'owner-local-manual'); assert.equal(manifest.native_reads_complete, true);
  const installed = await read(manifest.installed), nativePool = await read(manifest.native_pool);
  verifyInstallation(installed, manifest.candidate, nativePool);
  const results = [];
  for (const expected of manifest.cases) {
    const data = {};
    for (const name of ['issue', 'events', 'run', 'claim', 'journal', 'pr', 'jobs']) data[name] = await read(expected.files[name]);
    data.comments = (await Promise.all(expected.files.comments.map(read))).flat(2);
    results.push(verifyNativeCase(expected, data, installed));
  }
  for (const field of ['run_id', 'outcome_id', 'job_id']) assert.equal(new Set(results.map(value => value[field])).size, results.length);
  const observations = await read(manifest.host_observations), inventory = await read(manifest.execution_inventory);
  const overlaps = manifest.pairs.map(pair => verifyOverlap(pair, results, observations, inventory, installed));
  assert(manifest.pairs.some(pair => pair.kind === 'same-repository')); assert(manifest.pairs.some(pair => pair.kind === 'cross-repository'));
  const occupancy = verifyOccupancy(observations, installed);
  const receipt = { status: 'PASS', candidate: manifest.candidate, observed_at: new Date().toISOString(), cases: results,
    overlaps, occupancy, input_sha256: hashes, limitations: [
      'Authenticated owner/root provenance and complete native pagination remain operator attestations.',
      'Discrete procfs observations bound observed occupancy; they do not measure simultaneous remote computation or account quota.',
      'TEST-private Node/bwrap overlays and historical host-visible bwrap target remain installation limitations.',
      'This overlap receipt does not qualify pool expansion/contraction, recovery, upgrade, PROD, acceptance, merge or closure.' ] };
  await writeFile(output, JSON.stringify(receipt, null, 2) + '\n', { flag: 'wx' });
  console.log(JSON.stringify(receipt));
}
