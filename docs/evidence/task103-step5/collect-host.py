#!/usr/bin/env python3
"""Read-only TEST collection. Writes only new root-private evidence outputs.

Reuse Step 3 no-follow record reads, bounded machine snapshots and original
claim/journal attribution. Only the listed sandbox path environment values are
retained; no raw environment, argv, credential file or transcript is exported.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import socket
import stat
import time

PREVIOUS = Path(__file__).resolve().parent.parent / 'task103-step3' / 'collect-host.py'
spec = importlib.util.spec_from_file_location('task103_step3_collector', PREVIOUS)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
require = base.require
PATHS = {'HOME': 'home', 'CODEX_HOME': 'home', 'XDG_CACHE_HOME': 'cache',
         'XDG_CONFIG_HOME': 'config', 'XDG_DATA_HOME': 'data', 'XDG_STATE_HOME': 'state', 'TMPDIR': 'tmp'}


def path_environment(raw, checkout):
    """Discard all non-path entries without decoding or returning their values."""
    require(len(raw) <= 256 * 1024, 'ENVIRONMENT_TOO_LARGE')
    selected = {}
    for entry in raw.split(b'\0'):
        name, sep, value = entry.partition(b'=')
        if sep and name in {key.encode() for key in PATHS}:
            key = name.decode('ascii')
            require(key not in selected, 'ENVIRONMENT_PATH_DUPLICATE')
            selected[key] = value.decode('utf-8', errors='strict')
    require(set(selected) == set(PATHS), 'ENVIRONMENT_PATH_MISSING')
    for key, suffix in PATHS.items():
        require(selected[key] == str(Path(checkout) / '.codex-sandbox' / suffix), 'ENVIRONMENT_PATH_OUTSIDE_ATTEMPT')
    return selected


def directory_metadata(pid, selected, uid):
    result = {}
    for key, value in selected.items():
        # Resolve inside the actual process mount namespace, not the host view.
        target = Path(f'/proc/{pid}/root') / value.lstrip('/')
        for node in [target.parent, target]:
            info = node.lstat()
            require(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode), 'SANDBOX_DIRECTORY_ALIAS')
        info = target.stat()
        require(info.st_uid == uid, 'SANDBOX_DIRECTORY_OWNER')
        result[key] = {'dev': info.st_dev, 'inode': info.st_ino, 'uid': info.st_uid, 'mode': oct(stat.S_IMODE(info.st_mode))}
    return result


def load_installation(candidate, native):
    require(re.fullmatch('[0-9a-f]{40}', candidate) is not None, 'EXACT_CANDIDATE_REQUIRED')
    require(native.get('native_reads_complete') is True, 'COMPLETE_NATIVE_POOL_READ_REQUIRED')
    slots, sources, configurations, pool = [], [], [], None
    for ns, (repository, repository_id) in base.TARGETS.items():
        root = Path('/opt') / ns
        link = root / 'current'
        meta = link.lstat()
        require(stat.S_ISLNK(meta.st_mode) and meta.st_uid == 0, 'CURRENT_BINDING_UNTRUSTED')
        release = link.resolve(strict=True)
        require(release == root / 'releases' / candidate, 'INSTALLED_CANDIDATE_MISMATCH')
        deployment, deployment_source = base.json_source(base.safe_path(release / 'deployment-config.json', root), {0})
        config, source = base.json_source(base.safe_path(f'/etc/{ns}/consumer.json', Path('/etc') / ns), {0})
        require(config.get('repository') == repository and deployment['consumer']['repository'] == repository,
                'TEST_REPOSITORY_MISMATCH')
        general = deployment['environment']['generalRunner']
        pool_id = general['name']
        require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}', pool_id) and pool_id.startswith('relay-test'), 'TEST_POOL_ID_REQUIRED')
        desired = config['generalRunnerPool']['desiredCapacity']
        require(type(desired) is int and 2 <= desired <= 32
                and deployment['consumer']['generalRunnerPool']['desiredCapacity'] == desired, 'POOL_CAPACITY_MISMATCH')
        require(general['scope'] == 'organization' and native['group']['name'] == general['group'], 'POOL_GROUP_MISMATCH')
        require(native['group']['restricted_to_workflows'] is True and native['group']['visibility'] == 'selected', 'RESTRICTED_TEST_GROUP_REQUIRED')
        configured = config['executionSlots']
        require([value['id'] for value in configured] == ['primary'] + [f'pool-{number}' for number in range(2, 33)],
                'FIXED_INTERNAL_POOL_TOPOLOGY_REQUIRED')
        if pool is None:
            pool = {'id': pool_id, 'desired_capacity': desired, 'runner_group_id': native['group']['id'], 'members': []}
        require(pool['id'] == pool_id and pool['desired_capacity'] == desired, 'ONE_PHYSICAL_POOL_REQUIRED')
        for index, value in enumerate(configured, 1):
            expected_name = pool_id if index == 1 else f'{pool_id}-{index}'
            require(value['runnerName'] == expected_name and value['runnerUser'] == general['user'], 'POOL_RUNNER_BINDING_MISMATCH')
            runner, runtime = pwd.getpwnam(value['runnerUser']), pwd.getpwnam(value['runtimeUser'])
            require(runner.pw_uid > 0 and runtime.pw_uid > 0 and runner.pw_uid != runtime.pw_uid, 'NONROOT_SEPARATE_TRUSTED_RUNNER_REQUIRED')
            unit = f'{pool_id}-pool-{index}.service'
            if index <= desired:
                matches = [item for item in native['runners'] if item['name'] == expected_name]
                require(len(matches) == 1 and matches[0]['status'] == 'online', 'EXACT_NATIVE_RUNNER_REQUIRED')
                binding = base.unit_binding(unit, value['runnerUser'])
                member = {'id': value['id'], 'runner_id': matches[0]['id'], 'runner_name': expected_name,
                          'runner_uid': runner.pw_uid, 'unit': unit, 'cgroup': binding['ControlGroup']}
                if ns == next(iter(base.TARGETS)):
                    pool['members'].append(member)
                else:
                    require(member == pool['members'][index - 1], 'CROSS_REPOSITORY_PHYSICAL_MEMBER_MISMATCH')
            else:
                # Retired/never provisioned slots remain part of complete journal
                # inventory; they cannot attribute a live physical process.
                binding = {'ControlGroup': f'/__inactive_task103_pool_member_{index}', 'FragmentPath': ''}
            state = Path('/var/lib') / ns
            work = base.safe_path(value['paths']['workRoot'], state)
            attempts = base.safe_path(value['paths']['attemptRoot'], state)
            claims = base.safe_path(Path(config['paths']['claimRoot']) / 'publication-v2', state)
            require(attempts.name == 'attempts-v2', 'ATTEMPT_ROOT_INVALID')
            slots.append({'namespace': ns, 'repository': repository, 'repository_id': repository_id, 'id': value['id'],
                          'uid': runtime.pw_uid, 'runner_uid': runner.pw_uid, 'work': work, 'attempts': attempts,
                          'claims': claims, 'state_root': state, 'unit': unit, 'cgroup': binding['ControlGroup'],
                          'unit_source': binding['FragmentPath'], 'runner_name': expected_name,
                          'runner_id': next((member['runner_id'] for member in pool['members'] if member['runner_name'] == expected_name), None),
                          'pool_id': pool_id})
        sources += [source, deployment_source]
        configurations.append({'namespace': ns, 'repository': repository, 'runtime_uid': pwd.getpwnam(config['runtimeUser']).pw_uid, 'sha256': source['sha256'],
                               'deployment_sha256': deployment_source['sha256'], 'candidate': candidate, 'pool_id': pool_id})
    managed_ids = {member['runner_id'] for member in pool['members']}
    pool_label = 'relay-pool-' + hashlib.sha256(pool['id'].encode()).hexdigest()[:24]
    for extra in [runner for runner in native['runners'] if runner['id'] not in managed_ids]:
        require(extra.get('status') == 'offline' and extra.get('busy') is False
                and not extra.get('name', '').startswith(pool['id'])
                and isinstance(extra.get('labels'), list)
                and all(label.get('name') != pool_label for label in extra['labels']),
                'EXTRA_ELIGIBLE_PHYSICAL_POOL_RUNNER')
    pool_root = Path('/var/lib/codex-relay-pools') / pool['id']
    manifest, manifest_source = base.json_source(base.safe_path(pool_root / 'pool.json', pool_root), {0}, 1024 * 1024)
    require(manifest.get('version') == 1 and manifest.get('desiredCapacity') == pool['desired_capacity']
            and manifest.get('ownerRepository') in {value[0] for value in base.TARGETS.values()}, 'POOL_MANIFEST_IDENTITY_MISMATCH')
    require(manifest['binding']['name'] == pool['id'] and manifest['binding']['runnerUser'] == general['user']
            and manifest['binding']['group'] == native['group']['name'], 'POOL_MANIFEST_BINDING_MISMATCH')
    expected_consumers = {repository: {'namespace': ns, 'admission': f'/opt/{ns}/relay-admission'}
                          for ns, (repository, _) in base.TARGETS.items()}
    require(manifest['consumers'] == expected_consumers, 'POOL_MANIFEST_CONSUMERS_MISMATCH')
    require(set(manifest['members']) == {member['id'] for member in pool['members']}, 'POOL_MANIFEST_EXTRA_OR_MISSING_MEMBER')
    for member in pool['members']:
        require(manifest['members'][member['id']] == {'phase': 'ready', 'runnerId': member['runner_id']}, 'POOL_MANIFEST_MEMBER_UNCERTAIN')
        physical = [item for item in manifest['binding']['members'] if item['id'] == member['id']]
        require(len(physical) == 1 and physical[0]['name'] == member['runner_name'] and physical[0]['service'] == member['unit'],
                'POOL_MANIFEST_PHYSICAL_MEMBER_MISMATCH')
    sources.append(manifest_source)
    return slots, sources, {'source': 'trusted-root-installed-readback', 'candidate': candidate, 'host': socket.gethostname(),
                            'complete': True, 'gaps': [], 'configurations': configurations, 'pool': pool,
                            'pool_manifest_sha256': manifest_source['sha256'],
                            'limitations': ['Private TEST Node/bwrap overlays; whole-host noninterference is not established.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['observe', 'snapshot'])
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--native-pool', type=Path, required=True)
    parser.add_argument('--duration', type=int, default=900)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--run', action='append', default=[])
    args = parser.parse_args()
    require(os.geteuid() == 0 and 1 <= args.duration <= 900, 'ROOT_BOUNDED_COLLECTION_REQUIRED')
    output = base.safe_path(args.output, Path('/root'))
    require(not output.exists() and output.parent.is_dir() and output.parent.stat().st_uid == 0
            and not output.parent.stat().st_mode & 0o077, 'NEW_ROOT_PRIVATE_OUTPUT_REQUIRED')
    native, native_source = base.json_source(base.safe_path(args.native_pool, Path('/root')), {0})
    slots, sources, installed = load_installation(args.candidate, native)
    output.mkdir(mode=0o700)
    records = base.Records(slots)
    samples, gaps, scans, inventory_window = [], [], [], {}
    start, deadline = base.utc(), time.monotonic() + args.duration
    requested = []
    for value in args.run:
        match = re.fullmatch(r'(codex-relay-test(?:-two)?):([1-9][0-9]*)', value)
        require(match is not None, 'EXACT_SNAPSHOT_RUN_REQUIRED')
        requested.append((base.TARGETS[match[1]][0], int(match[2]), match[1]))
    require(args.mode != 'snapshot' or requested, 'SNAPSHOT_RUN_REQUIRED')
    try:
        while True:
            observed = base.utc()
            inventory, pairs, errors, counts = records.scan()
            gaps.extend({**error, 'observed_at': observed} for error in errors)
            for attempt in inventory:
                identity = (attempt['repository'], attempt['run_id'])
                previous = inventory_window.get(identity)
                if previous and previous['child'] == 'started' and attempt['child'] != 'started':
                    gaps.append({'code': 'OBSERVED_CHILD_STATE_REGRESSION', 'run_id': attempt['run_id']})
                else:
                    inventory_window[identity] = attempt
            active = 0
            if args.mode == 'observe':
                for entry in Path('/proc').iterdir():
                    if not entry.name.isdigit():
                        continue
                    try:
                        process = base.proc(int(entry.name), slots)
                        if process is None:
                            continue
                        attributed = base.attribute(process, slots, pairs)
                        slot = next(value for value in slots if value['namespace'] == attributed['namespace'] and value['id'] == attributed['execution_slot'])
                        with (entry / 'environ').open('rb') as environment:
                            raw = environment.read(256 * 1024 + 1)
                        selected = path_environment(raw, attributed['checkout'])
                        del raw
                        directories = directory_metadata(int(entry.name), selected, process['uid'])
                        samples.append({'observed_at': observed, 'host': installed['host'], **attributed,
                                        **{key: process[key] for key in ('pid', 'uid', 'proc_start_ticks', 'process_state', 'executable', 'command_role')},
                                        'pool_id': slot['pool_id'], 'runner_name': slot['runner_name'], 'runner_id': slot['runner_id'],
                                        'environment_paths': selected, 'directory_metadata': directories})
                        active += 1
                    except (FileNotFoundError, ProcessLookupError):
                        continue
                    except (ValueError, PermissionError, KeyError, TypeError, UnicodeError):
                        gaps.append({'code': 'PROCESS_METADATA_OR_ATTRIBUTION_GAP', 'pid': int(entry.name), 'observed_at': observed})
            scans.append({'observed_at': observed, 'active_attributable_codex': active, **counts})
            if args.mode == 'snapshot':
                for repository, run_id, namespace in requested:
                    pair = pairs.get((repository, run_id))
                    require(pair and 'claim' in pair and 'journal' in pair
                            and pair['claim']['envelope'] == pair['journal']['envelope'], 'EXACT_ORIGINAL_PAIR_REQUIRED')
                    for kind in ['claim', 'journal']:
                        base.write_json(output, f'{namespace}-{run_id}.{kind}.json', base.snapshot(pair[kind]))
                break
            if len(scans) % 5 == 1:
                print(json.dumps({'samples': len(samples), 'active': active, 'gaps': len(gaps)}), flush=True)
            if time.monotonic() >= deadline:
                break
            time.sleep(min(2, deadline - time.monotonic()))
    except BaseException:
        gaps.append({'code': 'COLLECTION_INTERRUPTED_OR_FAILED', 'observed_at': base.utc()})
        raise
    finally:
        # Bind the complete window to unchanged configuration and source bytes.
        for source in sources:
            try:
                _, current = base.json_source(Path(source['path']), {0})
                require(current['sha256'] == source['sha256'], 'CONFIGURATION_CHANGED_DURING_WINDOW')
            except (ValueError, OSError):
                gaps.append({'code': 'CONFIGURATION_CHANGED_OR_UNREADABLE', 'path': source['path']})
        installed['complete'], installed['gaps'] = not gaps, gaps
        base.write_json(output, 'installed.json', installed)
        base.write_json(output, 'protected-host-observations.json', {'source': 'trusted-host-procfs', 'candidate': args.candidate,
                        'complete_for_window': not gaps, 'started_at': start, 'ended_at': base.utc(), 'sample_interval_seconds': 2,
                        'samples': samples, 'scan_counts': scans, 'gaps': gaps})
        base.write_json(output, 'protected-execution-inventory.json', {'complete_for_window': not gaps, 'started_at': start,
                        'ended_at': base.utc(), 'attempts': list(inventory_window.values()), 'gaps': gaps})
        base.write_json(output, 'protected-sources.json', {'configs': sources, 'native_pool_input': native_source,
                        'records': list(records.source_history.values()), 'directories': list(records.directories.values()),
                        'collector_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                        'reused_collector_sha256': hashlib.sha256(PREVIOUS.read_bytes()).hexdigest(), 'gaps': gaps})
    print(json.dumps({'output': str(output), 'samples': len(samples), 'gaps': len(gaps), 'complete_for_window': not gaps}))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError, UnicodeError) as error:
        print(json.dumps({'status': 'FAILED', 'code': base.safe_error_code(error)}))
        raise SystemExit(1)
