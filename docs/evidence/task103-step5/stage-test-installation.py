#!/usr/bin/env python3
"""Prepare only: exact-source, bounded adaptation of the Step 3 TEST stager.

No network, service command, secret-file read or remote operation occurs here.
The generated install requires stopped TEST services and an observed idle old
admission. It does not register/activate runners or claim public lifecycle proof.
"""
import argparse
import copy
import hashlib
import inspect
import json
from pathlib import Path
import re
import shutil
from types import SimpleNamespace

import yaml

HERE = Path(__file__).resolve().parent
PREVIOUS_PATH = HERE.parent / 'task103-step3/stage-test-installation.py'
POOL = 'relay-test-managed-pool'
RUNNER = 'relay-test-general-runner'
GROUP = 'codex-relay-test-general-runner'
RUNTIME_USERS = {'codex-relay-test': 'relay-test-codex', 'codex-relay-test-two': 'relay-test-two-codex'}


def require(value, code):
    if not value:
        raise ValueError(code)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def replace_once(source, old, new):
    require(source.count(old) == 1, 'PREVIOUS_STAGER_SOURCE_CHANGED_INSPECT_ADAPTATION')
    return source.replace(old, new, 1)


def prepared_config(previous, revision, key_path, app_id, installation_id, capacity):
    result = copy.deepcopy(previous)
    ns = result['environment']['namespace']
    require(ns in RUNTIME_USERS and result['consumer']['repository'] == {
        'codex-relay-test': 'jresearchsoftware/codex-relay-testbed',
        'codex-relay-test-two': 'jresearchsoftware/codex-relay-testbed-2'}[ns], 'EXACT_TEST_CONFIG_REQUIRED')
    require(result['target']['host'] == '195.201.83.241', 'EXACT_TEST_HOST_REQUIRED')
    require(result['consumer']['runtimeUser'] == RUNTIME_USERS[ns], 'ORIGINAL_NAMESPACE_RUNTIME_USER_REQUIRED')
    require(type(capacity) is int and 1 <= capacity <= 32, 'BOUNDED_POOL_CAPACITY_REQUIRED')
    require(re.fullmatch('[a-f0-9]{40}', revision) is not None, 'EXACT_CANDIDATE_REQUIRED')
    require(Path(key_path).is_absolute() and '/mnt/c/' in key_path and key_path.endswith('.pem'), 'OWNER_LOCAL_WINDOWS_PEM_PATH_REQUIRED')
    require(all(re.fullmatch('[1-9][0-9]*', value) for value in [app_id, installation_id]), 'OBSERVED_ADMIN_APP_IDENTITIES_REQUIRED')
    result['source']['revision'] = revision
    result['consumer'].pop('executionSlots', None)
    result['consumer']['generalRunnerPool'] = {'desiredCapacity': capacity}
    result['environment']['generalRunner'] = {'name': POOL, 'user': RUNNER, 'scope': 'organization', 'group': GROUP,
        'poolApp': {'appId': app_id, 'installationId': installation_id, 'privateKeyFile': key_path}}
    return result


def adapted_prepare(previous):
    """Require exact old invariants before changing only the two TEST choices."""
    source = inspect.getsource(previous.prepare)
    source = replace_once(source,
        "require([slot['id'] for slot in slots] == ['primary', 'second'], 'exact-primary-second-topology')",
        "require([slot['id'] for slot in slots] == ['primary'] + [f'pool-{n}' for n in range(2, 33)], 'exact-managed-pool-topology')")
    source = replace_once(source,
        "require(all(name.startswith(prefix) for name in names), 'TEST-identities-only')",
        "require(all(name.startswith(prefix) or name == 'relay-test-general-runner' for name in names), 'TEST-identities-only')")
    guard = previous.IDLE_GUARD
    guard = replace_once(guard,
        "units=[ns+x for x in ['.service','-reviewer.service','-reviewer-recovery.timer','-runner.service','-general-runner.service','-slot-second-runner.service','-relay-manual-outcome.socket']]",
        "units=[ns+x for x in ['.service','-reviewer.service','-reviewer-recovery.timer','-runner.service','-general-runner.service','-slot-second-runner.service','-relay-manual-outcome.socket']] + [f'relay-test-managed-pool-pool-{n}.service' for n in range(1,33)]")
    guard = replace_once(guard,
        "assert status['active']==[] and status['unknown']==[], 'original attempt is not idle'",
        "assert status['active']==[] and status['unknown']==[] and status['phase']=='open' and status['operationId'] is None and status['target'] is None, 'original attempt or lifecycle is not idle'")
    guard = guard.replace('task103-step3-retained-local-state', 'task103-step5-retained-local-state')
    guard = replace_once(guard, "os.rename(claim,archive/'claims'); claim.mkdir(mode=0o700)",
        """# Preserve completed original journal bytes/metadata before role ownership changes.
for slot in previous.get('executionSlots', []):
    old=Path(slot['paths']['attemptRoot']); slot_id=slot['id']
    assert re.fullmatch('[a-z][a-z0-9-]{0,31}',slot_id) and old.is_relative_to(state) and old.name=='attempts-v2'
    if old.exists() or old.is_symlink():
        for parent in [old,*old.parents]:
            info=parent.lstat(); assert stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode) and not info.st_mode&0o022
        os.rename(old,archive/('journal-'+slot_id))
os.rename(claim,archive/'claims'); claim.mkdir(mode=0o700)""")
    namespace = dict(vars(previous))
    namespace['IDLE_GUARD'] = guard
    exec(compile(source, str(PREVIOUS_PATH) + ':step5-bounded-adaptation', 'exec'), namespace)
    return namespace['prepare'], source, guard


def patch_bundle(output, source, capacity, transformed, guard):
    backend = output / 'ansible'
    for filename in ['managed_pool.py']:
        shutil.copyfile(source / 'deploy' / filename, output / filename)
    play_path = backend / 'stage.yml'
    play = yaml.safe_load(play_path.read_text())
    current = play[0]
    current['name'] = 'Task103 Step5 scoped managed-pool TEST installation; registration and activation are separate'
    # The inherited root-local play disabled task-level become_user, making
    # Runner.Listener version probes create root-owned private diagnostics.
    current['become'] = True
    current['post_tasks'] = [item for item in current['post_tasks'] if item['name'] not in {
        'Create only dedicated TEST service tool overlay directories',
        'Expose qualified private TEST tools inside only TEST service namespaces',
        'Reload installed dedicated TEST units without activating services'}]
    # The ordinary runner role above fetches/verifies the pinned package used
    # by the unchanged managed member role; no registration/activation occurs.
    current['post_tasks'].append({'name': 'Install the one shared physical TEST pool without registration or activation',
        'ansible.builtin.include_tasks': 'tasks/managed-pool.yml'})
    units = [f'{POOL}-pool-{number}.service' for number in range(1, capacity + 1)]
    current['post_tasks'].extend([
        {'name': 'Create dedicated shared TEST pool service overlay directories only', 'ansible.builtin.file': {
            'path': '/etc/systemd/system/{{ item }}.d', 'state': 'directory', 'owner': 'root', 'group': 'root', 'mode': '0755'}, 'loop': units},
        {'name': 'Expose existing private TEST tools in shared pool service mount namespaces only', 'ansible.builtin.copy': {
            'content': '[Service]\nBindReadOnlyPaths=/opt/codex-relay-test/node22/bin/node:/usr/bin/node\nBindReadOnlyPaths=/opt/codex-relay-test/tools/bwrap:/usr/bin/bwrap\n',
            'dest': '/etc/systemd/system/{{ item }}.d/task103-step5-qualification-tools.conf',
            'owner': 'root', 'group': 'root', 'mode': '0644'}, 'loop': units},
        {'name': 'Reload only installed TEST unit definitions without starting services', 'ansible.builtin.systemd': {'daemon_reload': True}}])
    play_path.write_text(yaml.safe_dump(play, sort_keys=False))
    plan_path = output / 'plan.json'
    plan = json.loads(plan_path.read_text())
    plan.update({'phase': 'Task103-Step5-preparation-only', 'physicalPool': POOL, 'desiredCapacity': capacity,
                 'previousPreparationSha256': sha(PREVIOUS_PATH), 'adaptedPreparationSha256': hashlib.sha256(transformed.encode()).hexdigest(),
                 'idleGuardSha256': hashlib.sha256(guard.encode()).hexdigest(), 'physicalPoolUnits': units})
    plan['adaptations'].append({'path': 'stage.yml', 'change': 'fixed32 internal routes; one shared physical pool; preserve task identity changes; pool-service-only tool overlays', 'stagedSha256': sha(play_path)})
    plan['adaptations'].append({'path': '../managed_pool.py', 'change': 'unchanged exact candidate helper for installed pool preflight', 'sourceSha256': sha(source / 'deploy/managed_pool.py'), 'stagedSha256': sha(output / 'managed_pool.py')})
    plan['limitations'].extend(['Existing completed TEST claims/journals are archived only after stopped services and open/idle original status; no original Outcome or recovery journal is rewritten.',
        'Windows private PEM path is an owner-side config binding only. This bundle contains no PEM/JWT/installation token.',
        'Namespace two retains its repository-specific Codex UID; cross-repository overlap is an explicit optional-identity probe unless a separate shared-default configuration is admitted.'])
    plan['prerequisites'] += ['Both namespaces and all existing shared TEST pool services must be stopped before initial staging; no live pool contraction/upgrade is qualified by this adapter.',
        'Existing /usr/bin/node and /usr/bin/bwrap targets must already be regular root-owned files; never let systemd create a missing host target.',
        'Run run-stage.sh only after independent current TEST isolation/idle checks and reviewing plan.json.']
    plan['execution'] = ['./run-stage.sh']
    namespace = plan['namespace']
    wrapper = RUN_STAGE.replace('@NAMESPACE@', namespace).replace('@REVISION@', plan['sourceRevision'][:12])
    (output / 'run-stage.sh').write_text(wrapper)
    (output / 'run-stage.sh').chmod(0o700)
    plan['runStageSha256'] = sha(output / 'run-stage.sh')
    plan_path.write_text(json.dumps(plan, indent=2) + '\n')


RUN_STAGE = '''#!/bin/sh
set -eu
cd -- "$(dirname -- "$0")"
test "$(id -u)" = 0
# Existence is checked BEFORE systemd mounts, so no host mount target is created.
/usr/bin/python3 -I - <<'PY'
import os,stat
for p in ['/usr/bin/node','/usr/bin/bwrap','/opt/codex-relay-test/node22/bin/node','/opt/codex-relay-test/tools/bwrap']:
 s=os.lstat(p)
 assert stat.S_ISREG(s.st_mode) and s.st_uid==0 and not s.st_mode&0o022
PY
exec /usr/bin/systemd-run --wait --collect --pipe --unit=@NAMESPACE@-task103-step5-stage-@REVISION@ \\
 --property=Type=exec --property=PrivateMounts=yes \\
 --property=BindReadOnlyPaths=/opt/codex-relay-test/node22/bin/node:/usr/bin/node \\
 --property=BindReadOnlyPaths=/opt/codex-relay-test/tools/bwrap:/usr/bin/bwrap \\
 --property="WorkingDirectory=$PWD/ansible" \\
 /usr/bin/ansible-playbook -i 195.201.83.241, stage.yml
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True, type=Path)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--consumer-revision', required=True)
    parser.add_argument('--prior-config', required=True, type=Path)
    parser.add_argument('--admin-key-file', required=True)
    parser.add_argument('--admin-app-id', required=True)
    parser.add_argument('--admin-installation-id', required=True)
    parser.add_argument('--capacity', type=int, default=2)
    parser.add_argument('--reviewer-binary', required=True, type=Path)
    parser.add_argument('--cargo-version', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    require(not args.output.exists(), 'NEW_PRIVATE_BUNDLE_REQUIRED')
    import importlib.util
    spec = importlib.util.spec_from_file_location('task103_step3_preparation', PREVIOUS_PATH)
    previous = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(previous)
    config = prepared_config(json.loads(args.prior_config.read_text()), args.revision, args.admin_key_file,
                             args.admin_app_id, args.admin_installation_id, args.capacity)
    # Keep this private input adjacent to the new bundle; it contains paths/IDs
    # only and is never staged in the product checkout.
    config_path = args.output.with_name(args.output.name + '.owner-config.json')
    require(not config_path.exists(), 'NEW_PRIVATE_OWNER_CONFIG_REQUIRED')
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open('x') as stream:
        json.dump(config, stream, sort_keys=True)
        stream.write('\n')
    config_path.chmod(0o600)
    prepare, transformed, guard = adapted_prepare(previous)
    prepare(SimpleNamespace(source_root=args.source_root, revision=args.revision, consumer_revision=args.consumer_revision,
        config=config_path, reviewer_binary=args.reviewer_binary, cargo_version=args.cargo_version,
        output=args.output, resume_partial_proof=None))
    patch_bundle(args.output, args.source_root, args.capacity, transformed, guard)
    print(json.dumps({'preparedOnly': True, 'bundle': str(args.output), 'ownerConfig': str(config_path),
                      'pool': POOL, 'sourceRevision': args.revision, 'remoteMutation': False}))


if __name__ == '__main__':
    main()
