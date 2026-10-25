"""Real archived SERIAL parser/gate -> current installed pool in private namespaces.

Only GitHub responses and systemctl observations are synthetic. The production
installation, transition, ownership, original Node gate and compatibility readers
execute unchanged against native root-owned fixture files. No network or real
service command is available to this harness.
"""
import copy
import io
import json
import os
from pathlib import Path, PurePosixPath
import pwd
import shutil
import subprocess
import sys
import tarfile
import tempfile
from unittest.mock import patch

import pytest


ROOT = Path(__file__).resolve().parents[2]
ORIGINAL_REVISION = '34fa46144b57f3c9dd3b971a35379947ff6d3d54'
TARGET_REVISION = 'd' * 40
OPERATION = '12345678-1234-4234-8234-123456789abc'
QUALIFIED_NODE = Path(os.environ.get('RELAY_QUALIFIED_NODE',
    '/home/hortonolite/.nvm/versions/node/v22.20.0/bin/node'))
pytestmark = pytest.mark.skipif(sys.platform != 'linux' or os.geteuid() != 0,
    reason='private native Linux mount/network/PID namespace qualification requires root')


def native_write(path, value, mode=0o600, owner=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = value if isinstance(value, bytes) else json.dumps(value, separators=(',', ':')).encode() + b'\n'
    path.write_bytes(raw)
    path.chmod(mode)
    if owner:
        os.chown(path, owner.pw_uid, owner.pw_gid)
    return raw


def normalized_copy(source, target):
    shutil.copytree(source, target, ignore=shutil.ignore_patterns(
        '__pycache__', '.pytest_cache', 'node_modules', 'target'))
    for path in [target, *target.rglob('*')]:
        assert not path.is_symlink(), 'fixture sources must contain only regular files/directories'
        path.chmod(0o755 if path.is_dir() or path.stat().st_mode & 0o111 else 0o644)


def archive_original(destination):
    archive = subprocess.check_output(['git', '-c', 'safe.directory=' + str(ROOT),
        '-C', str(ROOT), 'archive', '--format=tar', ORIGINAL_REVISION])
    tree = subprocess.check_output(['git', '-c', 'safe.directory=' + str(ROOT),
        '-C', str(ROOT), 'rev-parse', ORIGINAL_REVISION + '^{tree}'], text=True).strip()
    destination.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as source:
        for member in source:
            path = PurePosixPath(member.name)
            assert not path.is_absolute() and '..' not in path.parts
            target = destination / member.name
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                target.chmod(0o755)
            else:
                assert member.isfile(), 'original trusted archive must not contain aliases/special files'
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.extractfile(member).read())
                target.chmod(member.mode & 0o755)
    return tree


@pytest.fixture(scope='module')
def source_bundle():
    if not QUALIFIED_NODE.is_file():
        pytest.skip('set RELAY_QUALIFIED_NODE to the qualified Node 22 executable')
    assert subprocess.check_output([str(QUALIFIED_NODE), '--version'], text=True).strip().startswith('v22.')
    probe = subprocess.run(['unshare', '--mount', '--net', '--pid', '--fork', '--kill-child', 'true'],
        capture_output=True, text=True, timeout=10)
    if probe.returncode:
        pytest.skip('private mount/network/PID namespaces unavailable')
    with tempfile.TemporaryDirectory(prefix='relay-serial-pool-source-', dir='/run') as temporary:
        bundle = Path(temporary)
        tree = archive_original(bundle / 'original')
        current = bundle / 'current'
        current.mkdir(mode=0o755)
        for component in ['consumer', 'controller', 'contracts', 'runtime', 'deploy', 'reviewer']:
            normalized_copy(ROOT / component, current / component)
        yield bundle, tree


@pytest.mark.parametrize('capacity,same_revision,source_links',
                         [(1, False, False), (2, False, False), (1, True, False), (2, True, True)])
def test_real_original_installation_transition_replay_and_retained_recovery(source_bundle, capacity, same_revision, source_links):
    bundle, tree = source_bundle
    with tempfile.TemporaryDirectory(prefix='relay-serial-pool-installed-', dir='/run') as temporary:
        fixture = Path(temporary)
        environment = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
        command = ['unshare', '--mount', '--net', '--pid', '--fork', '--kill-child', '--mount-proc',
            sys.executable, str(bundle / 'current/deploy/tests/test_serial_pool_installation.py'),
            '--installed-harness', str(fixture), str(bundle), tree, str(capacity),
            'same-revision-links' if source_links else 'same-revision' if same_revision else 'lifecycle',
            str(QUALIFIED_NODE)]
        result = subprocess.run(command, env=environment, text=True, capture_output=True, timeout=120)
        assert result.returncode == 0, result.stdout + result.stderr
        proof = json.loads(result.stdout)
        assert proof == {'capacity': capacity, 'originalGate': 'applying', 'newGate': 'open',
                         'retainedRuns': [11, 12, 13], 'removed': 1, 'networkIsolated': True}


def test_real_original_to_four_repository_six_runner_transition(source_bundle):
    bundle, tree = source_bundle
    with tempfile.TemporaryDirectory(prefix='relay-serial-plural-installed-', dir='/run') as temporary:
        command = ['unshare', '--mount', '--net', '--pid', '--fork', '--kill-child', '--mount-proc',
            sys.executable, str(bundle / 'current/deploy/tests/test_serial_pool_installation.py'),
            '--installed-harness', temporary, str(bundle), tree, '6', 'plural', str(QUALIFIED_NODE)]
        result = subprocess.run(command, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'},
                                text=True, capture_output=True, timeout=120)
        assert result.returncode == 0, result.stdout + result.stderr
        assert json.loads(result.stdout) == {'capacity': 6, 'originalGate': 'applying', 'newGate': 'open',
            'retainedRuns': [11, 12, 13], 'removed': 1, 'networkIsolated': True}


@pytest.mark.parametrize('boundary', ['unknown-original', 'owner-policy-change'])
def test_integrated_original_unknown_execution_and_owner_policy_delta_stop_before_transition(source_bundle, boundary):
    bundle, tree = source_bundle
    with tempfile.TemporaryDirectory(prefix='relay-serial-pool-boundary-', dir='/run') as temporary:
        command = ['unshare', '--mount', '--net', '--pid', '--fork', '--kill-child', '--mount-proc',
            sys.executable, str(bundle / 'current/deploy/tests/test_serial_pool_installation.py'),
            '--installed-harness', temporary, str(bundle), tree, '1', boundary, str(QUALIFIED_NODE)]
        result = subprocess.run(command, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'},
                                text=True, capture_output=True, timeout=120)
        assert result.returncode == 0, result.stdout + result.stderr
        assert json.loads(result.stdout) == {'blocked': boundary, 'originalGate': 'open', 'removed': 0}


def test_retained_original_tamper_stops_before_executing_its_source(source_bundle):
    bundle, tree = source_bundle
    with tempfile.TemporaryDirectory(prefix='relay-serial-pool-retained-boundary-', dir='/run') as temporary:
        command = ['unshare', '--mount', '--net', '--pid', '--fork', '--kill-child', '--mount-proc',
            sys.executable, str(bundle / 'current/deploy/tests/test_serial_pool_installation.py'),
            '--installed-harness', temporary, str(bundle), tree, '1', 'retained-context-tamper', str(QUALIFIED_NODE)]
        result = subprocess.run(command, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'},
                                text=True, capture_output=True, timeout=120)
        assert result.returncode == 0, result.stdout + result.stderr
        assert json.loads(result.stdout) == {'blockedBeforeExecution': [
            'source', 'config', 'manifest', 'consumer', 'gate', 'receipt'],
            'currentRejectedBeforeExecution': ['foreign-target', 'manifest', 'config', 'source-identity', 'unsafe-source'],
            'reservedReceiptReplay': True, 'originalGate': 'applying', 'removed': 0}


def test_retired_serial_git_intent_and_current_snapshot_drift_use_live_protected_graph(source_bundle):
    bundle, tree = source_bundle
    with tempfile.TemporaryDirectory(prefix='relay-serial-retired-git-', dir='/run') as temporary:
        command = ['unshare', '--mount', '--net', '--pid', '--fork', '--kill-child', '--mount-proc',
            sys.executable, str(bundle / 'current/deploy/tests/test_serial_pool_installation.py'),
            '--installed-harness', temporary, str(bundle), tree, '1', 'retired-git', str(QUALIFIED_NODE)]
        result = subprocess.run(command, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'},
                                text=True, capture_output=True, timeout=120)
        assert result.returncode == 0, result.stdout + result.stderr
        assert json.loads(result.stdout) == {'gitIntent': 'retained', 'snapshotDrift': ['missing', 'tampered'],
            'currentDigestMismatch': 'blocked', 'frozenOriginalTamper': 'blocked',
            'receiptUnchanged': True, 'networkIsolated': True}


def installed_harness(fixture, bundle, source_tree, capacity, scenario, qualified_node):
    """Called only as a child of root unshare; all mounts disappear on exit."""
    real_run = subprocess.run
    real_run(['mount', '--make-rprivate', '/'], check=True)
    namespace = 'relay-migrate-fixture'
    target_revision = ORIGINAL_REVISION if scenario.startswith('same-revision') else TARGET_REVISION
    # Hide complete host configuration/state trees instead of creating mount
    # targets on the host. Copy only public native identity lookup inputs.
    for relative in ['opt', 'etc', 'var/lib', 'sys']:
        (fixture / relative).mkdir(parents=True, mode=0o755, exist_ok=True)
    for filename in ['passwd', 'group', 'nsswitch.conf', 'ld.so.cache']:
        source = Path('/etc') / filename
        if source.is_file():
            shutil.copyfile(source, fixture / 'etc' / filename)
            (fixture / 'etc' / filename).chmod(0o644)
    for relative, target in [('opt', '/opt'), ('etc', '/etc'), ('var/lib', '/var/lib'), ('sys', '/sys')]:
        real_run(['mount', '--bind', str(fixture / relative), target], check=True)
    real_run(['mount', '--bind', str(qualified_node), '/usr/bin/node'], check=True)
    assert subprocess.check_output(['/usr/bin/node', '--version'], text=True).startswith('v22.')
    # The private network namespace contains no external interface/routes.
    assert all(row.split()[0] == 'Iface' or row.split()[0] == 'lo'
               for row in Path('/proc/net/route').read_text().splitlines())

    current_source = bundle / 'current'
    sys.path.insert(0, str(current_source / 'deploy'))
    import config
    import managed_pool
    import serial_pool_installation as installation
    import serial_pool_transition as transition

    identity = pwd.getpwnam('nobody')
    original = json.loads((bundle / 'original/deploy/example.json').read_text())
    original['source']['revision'] = ORIGINAL_REVISION
    original['environment']['namespace'] = namespace
    original['environment']['instance'] = {'reviewerPort': 18787, 'publicationEnabled': False}
    original['environment']['generalRunner'].update(user='nobody', name='legacy-general',
                                                    scope='organization', group='fixture-general')
    if scenario == 'same-revision-links':
        original['environment']['compatibilityLinks'] = {'legacy/controller': 'controller'}
    for key, path in original['consumer']['paths'].items():
        original['consumer']['paths'][key] = path.replace('/codex-relay/', '/' + namespace + '/')
    target = copy.deepcopy(original)
    target['source']['revision'] = target_revision
    target['consumer']['generalRunnerPool'] = {'desiredCapacity': capacity}
    target['environment']['generalRunner'].update(name='fixture-managed', poolApp={
        'appId': '101', 'installationId': '201', 'privateKeyFile': '/unavailable/fixture-only.pem'})
    if scenario == 'plural':
        anchor = target['consumer'].pop('repository')
        target['consumer']['repositories'] = [anchor, 'example-org/governance',
                                               'example-org/landscape', 'example-org/doc-review']
        target['environment']['repository'] = anchor
        target['environment']['reviewerRepositories'] = target['consumer']['repositories'][:]
    config.derive_managed_pool_slots(target)
    values = config.compile_inputs(original)
    release = Path('/opt') / namespace / 'releases' / ORIGINAL_REVISION
    release.mkdir(parents=True)
    shutil.copytree(bundle / 'original', release / 'reviewed-source')
    native_write(release / 'reviewed-source/.relay-source.json',
                 {'revision': ORIGINAL_REVISION, 'tree': source_tree}, 0o644)
    native_write(release / 'reviewed-source/consumer-general-runner-smoke.mjs',
                 b'// original generated SERIAL smoke\n', 0o644)
    if scenario == 'same-revision-links':
        alias = release / 'reviewed-source/legacy/controller'
        alias.parent.mkdir(mode=0o755)
        alias.symlink_to(release / 'reviewed-source/controller')
    config_raw = native_write(release / 'deployment-config.json', original)
    native_write(release / 'artifact-manifest.json', {
        'commit': ORIGINAL_REVISION, 'installedRevision': ORIGINAL_REVISION,
        'resolvedRevision': ORIGINAL_REVISION, 'gitTree': source_tree,
        'deploymentConfigSha256': transition.sha(config_raw)})
    (release.parent.parent / 'current').symlink_to(release)
    consumer_path = Path('/etc') / namespace / 'consumer.json'
    original_consumer_raw = native_write(consumer_path, original['consumer'], 0o644)
    claim = Path(original['consumer']['paths']['claimRoot'])
    (claim / 'publication-v2').mkdir(parents=True)
    Path(original['consumer']['paths']['attemptRoot']).mkdir(parents=True)
    original_digest = installation.consumer_digest(original['consumer'], release / 'reviewed-source')
    target_digest = installation.consumer_digest(target['consumer'], current_source)

    def envelope(run_id, route='auto'):
        return {'version': 2, 'repository': original['consumer']['repository'], 'runId': run_id,
            'attemptId': 'run-' + str(run_id), 'step': run_id - 10, 'target': 'issue', 'number': 103,
            'issueNumber': 103, 'route': route, 'profile': {'cliModelId': 'gpt-6.1-sol', 'effort': 'xhigh'},
            'consumerDigest': original_digest, 'startHead': ORIGINAL_REVISION,
            'historicalBase': ORIGINAL_REVISION, 'targetBase': ORIGINAL_REVISION,
            'authorityDigest': 'a' * 64, 'branch': 'codex/task-103', 'subagentsAllowed': False,
            'validation': ['diff-check']}

    old_records = {}
    for run_id, route in [(11, 'auto'), (12, 'manual'), (13, 'auto')]:
        e = envelope(run_id, route)
        outcome = {'status': 'BLOCKED', 'head': ORIGINAL_REVISION if run_id == 13 else None,
                   'prNumber': 77 if run_id == 13 else None, 'outcomeId': 101 + run_id}
        record = {'envelope': e}
        if run_id == 11:
            record.update(controllerLifecycle={'version': 1, 'status': 'complete',
                'child': 'started', 'containment': 'reaped'}, outcome=outcome)
        elif run_id == 12:
            record['manualSubmission'] = None
        else:
            record.update(outcome=outcome, prIntent=True, publishedHead=ORIGINAL_REVISION, finalHead=None)
        old_records[run_id] = record
        native_write(claim / 'publication-v2' / f'{run_id}.json', record)
        if route == 'auto':
            native_write(Path(original['consumer']['paths']['attemptRoot']) / f'{run_id}.json',
                {'version': 2, 'envelope': e, 'outcome': outcome,
                 'execution': {'reserved': True, 'returned': True, 'child': 'started', 'containment': 'reaped'}})
    original_manifest = (release / 'artifact-manifest.json').read_bytes()
    old_paths = [*list((claim / 'publication-v2').glob('*.json')),
                 *list(Path(original['consumer']['paths']['attemptRoot']).glob('*.json'))]
    old_bytes = {str(path): path.read_bytes() for path in old_paths}
    gate_environment = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C',
                        'RELAY_CONSUMER_CONFIG': str(consumer_path)}
    result = real_run(['/usr/bin/node', str(release / 'reviewed-source/controller/src/admission-cli.mjs'), 'initialize'],
                      env=gate_environment, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr

    runner_root = Path('/opt') / namespace / 'general-runner'
    runner_state = Path('/var/lib') / namespace / 'general-runner'
    for path in [runner_root, runner_state / 'work', runner_state / 'home']:
        path.mkdir(parents=True, exist_ok=True)
        path.chmod(0o750)
        os.chown(path, identity.pw_uid, identity.pw_gid)
    native_write(runner_root / '.runner', {'agentId': 71, 'agentName': 'legacy-general',
        'gitHubUrl': 'https://github.com/' + original['consumer']['repository'].split('/')[0],
        'poolName': 'fixture-general', 'workFolder': str(runner_state / 'work')}, owner=identity)
    credentials_raw = native_write(runner_root / '.credentials', b'synthetic private credentials', owner=identity)
    unit = Path('/etc/systemd/system') / (namespace + '-general-runner.service')
    native_write(unit, ('[Service]\nUser=nobody\nGroup=nobody\nWorkingDirectory=' + str(runner_root)
                       + '\nExecStart=' + str(runner_root / 'run.sh') + '\n').encode(), 0o644)
    ready_units = set()
    contract = managed_pool.pool_contract(target)

    class API:
        def __init__(self):
            self.old = {'id': 71, 'name': 'legacy-general', 'busy': False}
            self.pool = []
            self.deletes = 0
            self.lose_delete = False
        def pages(self, path, field):
            assert path == '/orgs/example-org/actions/runners' and field == 'runners'
            return copy.deepcopy(([self.old] if self.old else []) + self.pool)
        def runners(self):
            return self.pages('/orgs/example-org/actions/runners', 'runners')
        def request(self, method, path, body=None):
            assert method == 'DELETE' and path == '/orgs/example-org/actions/runners/71' and body is None
            self.deletes += 1
            self.old = None
            if self.lose_delete:
                self.lose_delete = False
                raise managed_pool.PoolError('MANAGED_POOL_API_UNPROVEN_INSPECT_BEFORE_RETRY')
            return None
    api = API()

    def boundary(argv, *args, **kwargs):
        if Path(argv[0]).name != 'systemctl':
            return real_run(argv, *args, **kwargs)
        assert argv[1] == 'show', 'the inactive legacy fixture permits no signal/start/service mutation'
        service = argv[2]
        is_old = service == unit.name
        active = service in ready_units
        rows = {'LoadState': 'loaded' if is_old or active else 'not-found',
            'ActiveState': 'active' if active else 'inactive', 'SubState': 'running' if active else 'dead',
            'UnitFileState': 'enabled' if active else 'disabled', 'MainPID': '12345' if active else '0',
            'ExecMainStartTimestampMonotonic': '4567' if active else '0', 'ControlPID': '0',
            'ControlGroup': '/system.slice/' + service if active else '',
            'FragmentPath': str(unit) if is_old else '/etc/systemd/system/' + service,
            'DropInPaths': '', 'NeedDaemonReload': 'no', 'User': 'nobody', 'Group': 'nobody',
            'WorkingDirectory': str(runner_root) if is_old else '/unused'}
        output = '\n'.join(key + '=' + value for key, value in rows.items()) + '\n'
        return subprocess.CompletedProcess(argv, 0 if is_old or active else 4,
            output if kwargs.get('text') else output.encode(), '' if kwargs.get('text') else b'')

    with patch('subprocess.run', side_effect=boundary):
        recovered_original, evidence = installation.original_installation(target)
        assert recovered_original == original and [run['runId'] for run in evidence['runs']] == [11, 12, 13]
        if scenario not in ['lifecycle', 'plural', 'same-revision', 'same-revision-links',
                            'retained-context-tamper', 'retired-git']:
            if scenario == 'unknown-original':
                damaged = copy.deepcopy(old_records[11])
                damaged['controllerLifecycle']['containment'] = 'unknown'
                native_write(claim / 'publication-v2/11.json', damaged)
            else:
                target['consumer']['owner'] = 'foreign-owner'
            with pytest.raises(managed_pool.PoolError):
                installation.preflight(target, api, target_digest)
            assert not (claim / transition.STATE_NAME).exists() and api.deletes == 0
            assert json.loads((claim / 'admission-v1.json').read_text())['phase'] == 'open'
            print(json.dumps({'blocked': scenario, 'originalGate': 'open', 'removed': 0}))
            return
        assert installation.preflight(target, api, target_digest)['original']['consumerDigest'] == original_digest
        assert installation.begin(target, api, target_digest, OPERATION, target_revision)['phase'] == 'stopped'
        old_gate = (claim / 'admission-v1.json').read_bytes()
        new_gate = (claim / 'admission-pool-v1.json').read_bytes()
        if scenario == 'retained-context-tamper':
            receipt_path = Path('/etc') / namespace / transition.RECEIPT_NAME
            retained = json.loads(receipt_path.read_bytes())['original']
            candidates = {'source': Path(retained['sourceRoot']) / 'controller/src/admission-cli.mjs',
                'config': Path(retained['configPath']), 'manifest': Path(retained['manifestPath']),
                'consumer': Path(retained['consumerPath']), 'gate': claim / 'admission-v1.json', 'receipt': receipt_path}
            for kind, path in candidates.items():
                before = path.read_bytes()
                path.write_bytes(before + b'\n')
                try:
                    with patch.object(installation, '_node', side_effect=AssertionError(
                            'tampered original graph must never execute')) as original_reader:
                        with pytest.raises(managed_pool.PoolError, match='ORIGINAL_(INSTALLATION_UNPROVEN|CONTEXT_CHANGED)'):
                            installation.original_installation(target)
                        original_reader.assert_not_called()
                finally:
                    path.write_bytes(before)
            assert installation.original_installation(target)[0] == original
            state_path = claim / transition.STATE_NAME
            state_raw = state_path.read_bytes()
            interrupted = json.loads(state_raw)
            interrupted['phase'] = 'reserved'
            interrupted.pop('receiptSha256')
            native_write(state_path, interrupted)
            receipt_raw = receipt_path.read_bytes()
            try:
                # Receipt publication can succeed before its final state ack.
                # The exact reserved plan still binds the original reader.
                assert installation.original_installation(target)[0] == original
                receipt_path.write_bytes(receipt_raw + b'\n')
                with patch.object(installation, '_node', side_effect=AssertionError(
                        'an altered unacknowledged receipt must never execute')) as original_reader:
                    with pytest.raises(managed_pool.PoolError, match='ORIGINAL_CONTEXT_CHANGED'):
                        installation.original_installation(target)
                    original_reader.assert_not_called()
            finally:
                receipt_path.write_bytes(receipt_raw)
                state_path.write_bytes(state_raw)

            current_link = release.parent.parent / 'current'
            assert installation.current_source(target) == str(release / 'reviewed-source')
            current_link.unlink()
            current_link.symlink_to('releases/' + ORIGINAL_REVISION)
            assert installation.current_source(target) == str(release / 'reviewed-source')
            current_link.unlink()
            current_link.symlink_to(release)

            def reject_current_before_execution():
                with patch.object(installation, '_node', side_effect=AssertionError(
                        'an unproven current graph must never execute')) as current_reader:
                    with pytest.raises(managed_pool.PoolError):
                        installation._node(installation.current_source(target), str(consumer_path), 'unreachable')
                    current_reader.assert_not_called()

            foreign_release = Path('/opt/foreign-graph/releases') / ORIGINAL_REVISION
            shutil.copytree(release, foreign_release)
            current_link.unlink()
            current_link.symlink_to(foreign_release)
            try:
                reject_current_before_execution()
            finally:
                current_link.unlink()
                current_link.symlink_to(release)
            current_rejected = ['foreign-target']
            for kind, path in {'manifest': release / 'artifact-manifest.json', 'config': release / 'deployment-config.json',
                    'source-identity': release / 'reviewed-source/.relay-source.json',
                    'unsafe-source': release / 'reviewed-source/consumer-general-runner-smoke.mjs'}.items():
                before = path.read_bytes()
                mode = path.stat().st_mode & 0o777
                if kind == 'unsafe-source':
                    path.chmod(0o666)
                elif kind == 'config':
                    path.write_bytes(before + b'\n')
                else:
                    changed = json.loads(before)
                    changed['gitTree' if kind == 'manifest' else 'revision'] = '1' * 40
                    native_write(path, changed, mode)
                try:
                    reject_current_before_execution()
                    current_rejected.append(kind)
                finally:
                    path.write_bytes(before)
                    path.chmod(mode)
            assert installation.current_source(target) == str(release / 'reviewed-source')
            assert (claim / 'admission-v1.json').read_bytes() == old_gate
            assert api.deletes == 0 and all(Path(path).read_bytes() == raw for path, raw in old_bytes.items())
            print(json.dumps({'blockedBeforeExecution': list(candidates), 'currentRejectedBeforeExecution': current_rejected,
                             'reservedReceiptReplay': True, 'originalGate': 'applying', 'removed': 0}))
            return
        assert set(json.loads(old_gate)['previousActive']) == {'reviewer', 'production', 'general'}
        assert len(json.loads(new_gate)['previousActive']) == 34
        assert installation.begin(target, api, target_digest, OPERATION, target_revision)['phase'] == 'stopped'

        # Model the native backend's published current snapshot, then its
        # already-qualified pool registrations and observed active transports.
        new_release = release.parent / target_revision
        new_release.mkdir(exist_ok=True)
        shutil.copytree(current_source, new_release / 'reviewed-source', dirs_exist_ok=True)
        native_write(new_release / 'reviewed-source/consumer-general-runner-smoke.mjs',
                     b'// replacement generated POOL smoke\n', 0o644)
        target_config_raw = native_write(new_release / 'deployment-config.json', target)
        native_write(new_release / 'reviewed-source/.relay-source.json',
                     {'revision': target_revision, 'tree': 'f' * 40}, 0o644)
        native_write(new_release / 'artifact-manifest.json', {'commit': target_revision,
            'installedRevision': target_revision, 'resolvedRevision': target_revision,
            'gitTree': 'f' * 40, 'deploymentConfigSha256': transition.sha(target_config_raw)})
        native_write(consumer_path, target['consumer'], 0o644)
        (release.parent.parent / 'current').unlink()
        (release.parent.parent / 'current').symlink_to(new_release)
        (claim / 'publication-pool-v1').mkdir()
        pool_root = Path('/var/lib/codex-relay-pools') / contract['name']
        pool_root.mkdir(parents=True)
        managed_pool.State(pool_root).write({'version': 1, 'binding': managed_pool.binding(contract)})
        for number, member in enumerate(contract['members'][:capacity], 1):
            root = Path(member['root'])
            root.mkdir(parents=True)
            native_write(root / '.runner', {'agentId': 100 + number, 'agentName': member['name'],
                'gitHubUrl': 'https://github.com/' + contract['organization'], 'poolName': contract['group'],
                'workFolder': member['state'] + '/work'}, owner=identity)
            native_write(root / '.credentials', b'synthetic pool credentials', owner=identity)
            api.pool.append({'id': 100 + number, 'name': member['name'], 'status': 'online', 'busy': False})
            ready_units.add(member['service'])
        # Same-operation reapply must retain the FIRST target snapshot even
        # after the target transport has become active.
        assert installation.begin(target, api, target_digest, OPERATION, target_revision)['phase'] == 'installed'
        assert (claim / 'admission-pool-v1.json').read_bytes() == new_gate
        api.lose_delete = True
        with pytest.raises(managed_pool.PoolError, match='API_UNPROVEN'):
            installation.finish(target, api)
        assert json.loads((claim / transition.STATE_NAME).read_text())['phase'] == 'remove-intent'
        assert installation.preflight(target, api, target_digest)['phase'] == 'remove-intent'
        assert installation.finish(target, api)['phase'] == 'retired'
        assert installation.preflight(target, api, target_digest)['phase'] == 'retired'
        assert api.deletes == 1
        assert (claim / 'admission-v1.json').read_bytes() == old_gate
        assert json.loads(old_gate)['phase'] == 'applying'
        assert (Path('/etc') / namespace / transition.CONSUMER_NAME).read_bytes() == original_consumer_raw
        assert (runner_root / '.credentials').read_bytes() == credentials_raw
        assert all(Path(path).read_bytes() == raw for path, raw in old_bytes.items())
        receipt = json.loads((Path('/etc') / namespace / transition.RECEIPT_NAME).read_text())
        assert '/serial-compat-v1/' in receipt['original']['sourceRoot']
        if scenario == 'same-revision-links':
            assert receipt['original']['sourceLinks'] == {'legacy/controller': 'controller'}
            alias = Path(receipt['original']['sourceRoot']) / 'legacy/controller'
            assert alias.is_symlink() and os.readlink(alias) == str(release / 'reviewed-source/controller')
        assert Path(receipt['original']['configPath']).read_bytes() == config_raw
        assert Path(receipt['original']['manifestPath']).read_bytes() == original_manifest
        assert (Path(receipt['original']['sourceRoot']) / 'consumer-general-runner-smoke.mjs').read_bytes() == b'// original generated SERIAL smoke\n'

        # Real current reader selects original immutable context for both
        # pending manual completion and partial blocked publication recovery.
        reader = '''import assert from 'node:assert/strict';
import {CONSUMER} from './consumer/consumer.mjs';
import {loadSerialPoolCompatibility,createCompatibilityStore,invokeOriginalReader,historicalOperationContext}
 from './controller/src/serial-pool-compatibility.mjs';
import {createAttemptStore,createPublicationStore} from './controller/src/attempt-store.mjs';
import {installedAdmissionControl} from './controller/src/admission-cli.mjs';
const c=await loadSerialPoolCompatibility({consumer:CONSUMER});
const store=createCompatibilityStore({compatibility:c,currentStore:createPublicationStore(c.current.storeRoot),
 originalStore:createAttemptStore(c.original.storeRoot,{repository:c.receipt.repository})});
const records=await store.all();assert.deepEqual(records.map(r=>r.envelope.runId),[11,12,13]);
assert.equal(historicalOperationContext(c,records[1],'manual-outcome-direct').kind,'original');
assert.equal(historicalOperationContext(c,records[2],'recover-prepublication').kind,'original');
for(const record of records)await invokeOriginalReader(c,{operation:'validate-envelope',envelope:record.envelope});
const oldInventory=await invokeOriginalReader(c,{operation:'inventory'});
assert.deepEqual(oldInventory.active,[]);assert.deepEqual(oldInventory.unknown,[]);
assert.equal(oldInventory.phase,'applying');assert.deepEqual(oldInventory.runs.map(r=>r.runId),[11,12,13]);
const currentEnvelope={...records[0].envelope,runId:44,attemptId:'run-44',
 consumerDigest:c.receipt.target.consumerDigest,executionSlot:'@@CURRENT_SLOT@@'};
await store.put(44,{envelope:currentEnvelope,controllerLifecycle:{version:1,status:'complete',child:'started',containment:'reaped'},
 outcome:{status:'BLOCKED',head:null,prNumber:null,outcomeId:244}});
assert.deepEqual((await store.all()).map(r=>r.envelope.runId),[11,12,13,44]);
const gate=installedAdmissionControl();
await gate.phase({operationId:'12345678-1234-4234-8234-123456789abc',phase:'verified',revision:'@@TARGET_REVISION@@'});
await gate.resume({operationId:'12345678-1234-4234-8234-123456789abc'});
assert.equal((await gate.status()).phase,'open');console.log(JSON.stringify({ok:true}));'''
        reader = reader.replace('@@TARGET_REVISION@@', target_revision).replace('@@CURRENT_SLOT@@',
            'pool-2' if capacity == 2 else 'primary')
        response = real_run(['/usr/bin/node', '--input-type=module', '-e', reader],
            cwd=new_release / 'reviewed-source', env={**gate_environment, 'RELAY_CONSUMER_CONFIG': str(consumer_path),
                'RELAY_REPOSITORY': config.deployment_repository(target)},
            text=True, capture_output=True, timeout=60)
        assert response.returncode == 0, response.stdout + response.stderr
        if scenario == 'retired-git':
            desired = copy.deepcopy(target)
            desired['environment']['localApply'] = {'source': 'git', 'repository': 'example-org/deployment',
                                                   'configPath': 'prod/relay.json'}
            desired['environment']['reviewerRepositories'] = [config.deployment_repository(target)]
            desired['consumer']['defaultProfile']['effort'] = 'medium'
            desired_digest = installation.consumer_digest(desired['consumer'], new_release / 'reviewed-source')
            assert desired_digest != target_digest
            retained_receipt = (Path('/etc') / namespace / transition.RECEIPT_NAME).read_bytes()
            current_gate_path = claim / 'admission-pool-v1.json'
            retained_gate = current_gate_path.read_bytes()
            expected = {'phase': 'retired', 'operationId': OPERATION,
                        'targetRevision': target_revision, 'completionRequired': False}
            assert installation.preflight(desired, api, desired_digest) == expected
            snapshot = new_release / 'deployment-config.json'
            snapshot.unlink()
            assert installation.preflight(desired, api, desired_digest) == expected
            native_write(snapshot, b'{overwritten malformed current snapshot')
            assert installation.preflight(desired, api, desired_digest) == expected
            # A new desired digest never legitimizes a live gate mismatch.
            damaged_gate = json.loads(retained_gate)
            damaged_gate['consumerDigest'] = desired_digest
            native_write(current_gate_path, damaged_gate)
            with pytest.raises(managed_pool.PoolError):
                installation.preflight(desired, api, desired_digest)
            current_gate_path.write_bytes(retained_gate)
            frozen = Path(receipt['original']['configPath'])
            frozen_raw = frozen.read_bytes()
            frozen.write_bytes(frozen_raw + b'\n')
            with pytest.raises(managed_pool.PoolError, match='ORIGINAL_INSTALLATION_UNPROVEN'):
                installation.preflight(desired, api, desired_digest)
            frozen.write_bytes(frozen_raw)
            assert (Path('/etc') / namespace / transition.RECEIPT_NAME).read_bytes() == retained_receipt
            assert all(Path(path).read_bytes() == raw for path, raw in old_bytes.items())
            assert (claim / 'admission-v1.json').read_bytes() == old_gate
            print(json.dumps({'gitIntent': 'retained', 'snapshotDrift': ['missing', 'tampered'],
                'currentDigestMismatch': 'blocked', 'frozenOriginalTamper': 'blocked',
                'receiptUnchanged': True, 'networkIsolated': True}))
            return
        assert all(Path(path).read_bytes() == raw for path, raw in old_bytes.items())
        assert (claim / 'admission-v1.json').read_bytes() == old_gate
        print(json.dumps({'capacity': capacity, 'originalGate': 'applying', 'newGate': 'open',
                          'retainedRuns': [11, 12, 13], 'removed': api.deletes, 'networkIsolated': True}))


if __name__ == '__main__' and len(sys.argv) == 8 and sys.argv[1] == '--installed-harness':
    installed_harness(Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4], int(sys.argv[5]),
                      sys.argv[6], Path(sys.argv[7]))
