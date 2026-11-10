"""Execute the real public install primitive across injected cutover failures.

Transport/artifact work is bounded here; their root filesystem, real Node,
Ansible and package/build implementations have separate integration fixtures.
These tests ensure a failed prerequisite never falls through to old shutdown.
"""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
import ansible_transport
import consumer_drift
import intent_install
import inventory
import install_preflight

spec = importlib.util.spec_from_file_location('preflight_order_backend', ROOT / 'deploy/relay-deploy.py')
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)
TARGET, OLD, CONSUMER = 'b' * 40, 'a' * 40, 'c' * 40


@pytest.fixture
def invocation(tmp_path, monkeypatch):
    previous_umask = os.umask(0o022)
    os.umask(previous_umask)
    config = json.loads((ROOT / 'deploy/example.json').read_text())
    config['target']['connection'] = 'local'
    config['environment']['localApply'] = {'source': 'git', 'repository': 'example-org/deployment',
                                          'configPath': 'prod/relay.json'}
    path = tmp_path / 'desired.json'
    path.write_text(json.dumps(config))
    monkeypatch.setattr(sys, 'argv', ['relay-deploy', '--config', str(path), '--phase', 'upgrade',
        '--authorize-upgrade', '--resolved-revision', TARGET, '--consumer-root', str(tmp_path),
        '--log-root', str(tmp_path / 'logs'), '--connection', 'local'])
    args = backend.arguments()
    args.intent_install, args.intent_expected_installed_revision = True, OLD
    args.git_intent = {'product_repository': 'example/codex-relay', 'product_sha': TARGET,
        'config_repository': 'example-org/deployment', 'config_path': 'prod/relay.json',
        'config_sha': 'd' * 40, 'config_blob_sha': 'e' * 40,
        'config_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'source_policy': 'accepted-main', 'workflow_run_id': 7, 'action': 'apply'}
    guard = SimpleNamespace(poll=lambda: None)
    args._intent_host_guard, args._intent_pool_guard = guard, guard
    events, records = [], [{'runId': 7, 'terminal': True}]
    gate = {'phase': 'open', 'operation': None}
    state = {'failure': None, 'stage_calls': 0, 'preparation': None, 'consumer_change': False, 'installed': OLD}
    identity = {'revision': TARGET, 'tree': 'f' * 40}
    monkeypatch.setattr(backend, 'source_identity', lambda _: identity)
    monkeypatch.setattr(backend, 'clean_git', lambda _: CONSUMER)
    import managed_pool_transport
    monkeypatch.setattr(managed_pool_transport, 'preflight_pool',
                        lambda *_args, **_kwargs: 'MANAGED_POOL_PREFLIGHT=PASS')
    monkeypatch.setattr(managed_pool_transport, 'reconcile_pool',
                        lambda *_args, **_kwargs: 'MANAGED_POOL_RESULT={"capacity":1}')

    # The controller's invocation lock is private to this synthetic fixture,
    # including when the same suite is exercised by root and an ordinary UID.
    monkeypatch.setattr(backend.tempfile, 'gettempdir', lambda: str(tmp_path))
    monkeypatch.setattr(ansible_transport, 'qualify_target', lambda *_: None)
    monkeypatch.setattr(consumer_drift, 'prepare', lambda *_: {'status': 'unchanged'})
    monkeypatch.setattr(inventory, 'remote_inventory', lambda *_args, **_kwargs:
        {'blockers': [], 'installed': {'status': 'present', 'revision': state['installed']}
         if state['installed'] is not None else {'status': 'missing'}})
    monkeypatch.setattr(backend, 'git', lambda _root, *argv: Path(argv[2].removeprefix('--output=')).write_bytes(b'archive')
                        if argv[0] == 'archive' else '')

    def injected(name):
        events.append(name)
        if state['failure'] == name:
            raise RuntimeError('INSTALL_PREFLIGHT_INJECTED_' + name.upper().replace('-', '_'))

    class Preparation:
        def __init__(self, _target, _key, _values, _identity, operation, **_options):
            self.operation = operation
            self.reinstall = _options.get('reinstall', False)
            self.stage = '/opt/fixture/releases/.stage-' + operation
            self.source = self.stage + '/release/reviewed-source'
            self.lease_path = self.stage + '/writer-lock.json'
            self.initial, self.holder, self.captured, self.cutover_started = None, None, False, False
            self.retained_proof = None
            state['preparation'] = self
        def create(self):
            injected('create')
            root = state.get('inventory_root')
            if root is not None and not self.reinstall:
                releases = root / 'opt/codex-relay/releases'
                releases.mkdir(parents=True, exist_ok=True)
                releases.chmod(0o755)
                releases.parent.chmod(0o755)
                stage = releases / ('.stage-' + self.operation)
                stage.mkdir(mode=0o700)
                stage.chmod(0o700)
        def desired(self): injected('desired')
        def consumer(self, **_options):
            injected('history')
            self.initial = {'baselineDigest': '1' * 64, 'consumerChange': state['consumer_change'],
                            'consumerRestoreRequired': False}
        def host(self, **_options): injected('host')
        def capture(self): self.captured = True; injected('capture')
        def verify_stage(self): injected('seal')
        def drain_staged(self):
            injected('drain')
            gate['phase'] = 'drained'
            return {'drained': True}
        def execute(self, argv, **_options):
            if 'drain-check' in argv:
                injected('drain-check')
                assert self.holder is not None and gate['phase'] == 'drained'
                return {'drained': state['failure'] != 'drain-changed'}
            assert 'phase' in argv and argv[-1] == 'applying'
            events.append('phase:applying')
            gate['phase'] = 'applying'
            return copy.deepcopy(gate)
        def lock_writer(self):
            injected('writer-lock')
            self.holder = guard
        def final(self, **_options):
            injected('final')
            if state['failure'] == 'config-drift':
                path.write_text('{}')
            if state['failure'] == 'manual-during-drain':
                records.append({'runId': 8, 'manual': True})
                raise RuntimeError('INSTALL_PREFLIGHT_CONSUMER_HISTORY_REQUIRES_OLD_VERSION_RESOLUTION')
        def admission_prefix(self): return ['verified-private-admission']
        def after_retirement(self): injected('after-retirement')
        def release_writer(self):
            if self.holder is not None:
                events.append('writer-release')
                self.holder = None
        def abort(self):
            assert self.captured and not self.cutover_started
            events.append('abort')
            gate.update(phase='open', operation=None)
            return {'status': 'old-open-restored'}

    monkeypatch.setattr(install_preflight, 'PreparedInstall', Preparation)

    def admission(_target, _key, _namespace, command, *options):
        events.append(command + (':' + options[options.index('--phase') + 1] if '--phase' in options else ''))
        if '--operation' in options:
            operation = options[options.index('--operation') + 1]
            assert operation == state['preparation'].operation
        if command == 'quiesce':
            assert gate['phase'] == 'open'
            gate.update(phase='quiesced', operation=operation)
        elif command == 'drain':
            if state['failure'] == 'drain':
                raise RuntimeError('INJECTED_DRAIN_UNPROVEN')
            gate['phase'] = 'drained'
        elif command == 'phase': gate['phase'] = options[options.index('--phase') + 1]
        elif command == 'resume': gate.update(phase='open', operation=None)
        return copy.deepcopy(gate)

    def prepare_target(*_args):
        injected('prepare-target')
        return False

    def run_backend(argv, _cwd, _env, log, _guard=None, _extra=None):
        name = Path(argv[3]).name
        if name == 'relay-intent-stage.yml':
            state['stage_calls'] += 1
            event = 'source-stage' if state['stage_calls'] == 1 else 'build-stage'
            injected(event)
        elif name == 'relay-intent-preflight.yml': injected('compatibility')
        elif name == 'relay-intent-prerequisites.yml': injected('prerequisites')
        elif name == 'relay-intent-apt-preflight.yml': injected('apt-preflight')
        else:
            assert name == 'site.yml'
            installed_values = next(iter(json.loads(Path(argv[2]).read_text())['all']['children']['relay']['hosts'].values()))
            if '--check' in argv:
                assert not any(key.startswith('relay_intent_stage') or key == 'relay_intent_writer_lock_lease'
                               for key in installed_values)
            if '--check' not in argv:
                injected('backend')
                assert state['preparation'].holder is not None or args.intent_expected_installed_revision == 'none'
                assert state['preparation'].cutover_started
                if state['failure'] == 'backend-return':
                    log.write('failed=1\n')
                    return 2
        log.write('localhost : ok=1 changed=0 unreachable=0 failed=0\n'
                  + f'PRODUCTION_APPLY_VALIDATED={TARGET}\nRELAY_INSTALLED_REVISION={TARGET};consumer={CONSUMER};previous={OLD}\n'
                  + f'RELAY_UPGRADE_ACTIVATION_VALIDATED={TARGET}\n')
        return 0

    monkeypatch.setattr(backend, 'remote_admission', admission)
    monkeypatch.setattr(backend, 'run_backend', run_backend)
    monkeypatch.setattr(intent_install, 'prepare_target', prepare_target)
    try:
        yield args, events, gate, state, records
    finally:
        os.umask(previous_umask)


@pytest.mark.parametrize('failure', ['create', 'source-stage', 'desired', 'history', 'compatibility', 'host', 'apt-preflight', 'capture', 'build-stage', 'seal'])
def test_known_prerequisite_failure_keeps_old_entrypoint_open(invocation, failure):
    args, events, gate, state, records = invocation
    state['failure'] = failure
    with pytest.raises(RuntimeError, match='INJECTED'):
        backend.run(args)
    assert gate == {'phase': 'open', 'operation': None}
    assert not {'quiesce', 'prepare-target', 'backend', 'phase:recovery-required'}.intersection(events)
    assert records == [{'runId': 7, 'terminal': True}]


@pytest.mark.parametrize('failure', ['final', 'config-drift', 'manual-during-drain', 'drain', 'drain-check', 'drain-changed'])
def test_late_change_aborts_before_active_install_and_preserves_records(invocation, failure):
    args, events, gate, state, records = invocation
    state['failure'] = failure
    with pytest.raises((ValueError, RuntimeError)):
        backend.run(args)
    assert gate == {'phase': 'open', 'operation': None}
    assert 'abort' in events
    assert not {'prepare-target', 'backend', 'phase:recovery-required'}.intersection(events)
    assert records[0] == {'runId': 7, 'terminal': True}
    if failure == 'manual-during-drain':
        assert records[-1] == {'runId': 8, 'manual': True}
    assert args._intent_mutation_started is False


def test_post_mutation_failure_retains_same_operation_and_forward_recovery(invocation):
    args, events, gate, state, records = invocation
    state['failure'] = 'backend-return'
    with pytest.raises(ValueError, match='apply-failed'):
        backend.run(args)
    assert gate['phase'] == 'recovery-required'
    assert gate['operation'] == state['preparation'].operation
    assert 'abort' not in events and 'resume' not in events
    assert events.index('writer-release') < events.index('phase:recovery-required')
    assert records == [{'runId': 7, 'terminal': True}]


def test_success_keeps_writer_mutex_through_first_active_effect(invocation):
    args, events, gate, state, _records = invocation
    backend.run(args)
    assert gate == {'phase': 'open', 'operation': None}
    assert events.index('build-stage') < events.index('quiesce')
    assert events.index('apt-preflight') < events.index('capture') < events.index('quiesce')
    assert events.index('drain') < events.index('writer-lock') < events.index('drain-check') < events.index('final')
    assert events.index('final') < events.index('prepare-target') < events.index('backend')
    assert events.index('backend') < events.index('writer-release') < events.index('phase:verified') < events.index('resume')
    assert 'abort' not in events


def test_fresh_bootstrap_allows_only_its_prepared_stage_until_cutover(invocation, monkeypatch, tmp_path):
    args, _events, _gate, state, _records = invocation
    args.phase = 'bootstrap'
    args.authorize_upgrade = False
    args.authorize_bootstrap = True
    args.intent_expected_installed_revision = 'none'
    state['installed'] = None
    inventory_root = tmp_path / 'inventory-root'
    inventory_root.mkdir(mode=0o700)
    inventory_root.chmod(0o700)
    state['inventory_root'] = inventory_root
    config = json.loads((ROOT / 'deploy/example.json').read_text())
    user_ids = {name: (os.getuid(), os.getgid()) for name in [
        config['environment']['runner']['user'], config['environment']['generalRunner']['user'],
        config['consumer']['runtimeUser'], config['environment']['reviewerUser']]}
    calls = []

    def observe(_target, _key, selected_config, **options):
        calls.append(options.copy())
        return inventory.inspect(selected_config, root=inventory_root, owner_uid=os.getuid(),
            user_ids=user_ids, git_desired=options.get('git_desired', False),
            allowed_stage_operation=options.get('allowed_stage_operation'))

    monkeypatch.setattr(inventory, 'remote_inventory', observe)
    backend.run(args)

    operation = state['preparation'].operation
    assert [call.get('allowed_stage_operation') for call in calls] == [None, None, operation, operation]
    assert all(call.get('git_desired') is True for call in calls)


def test_capable_installed_gate_receives_sealed_target_source_before_quiesce(invocation, monkeypatch):
    args, _events, gate, state, _records = invocation
    observe, admission = inventory.remote_inventory, backend.remote_admission
    def compatible_inventory(*arguments, **options):
        report = observe(*arguments, **options)
        report['installed']['deploymentContract'] = {'capabilities': ['predispatch-retention-v1']}
        return report
    observed = []
    def checked_admission(target, key, namespace, command, *options):
        if command == 'quiesce':
            assert options[-2:] == ('--target-source', state['preparation'].source)
            observed.append(command)
        return admission(target, key, namespace, command, *options)
    monkeypatch.setattr(inventory, 'remote_inventory', compatible_inventory)
    monkeypatch.setattr(backend, 'remote_admission', checked_admission)
    backend.run(args)
    assert observed == ['quiesce']
    assert gate['phase'] == 'open'


def test_staged_drain_uses_sealed_candidate_and_original_consumer():
    preparation = install_preflight.PreparedInstall(None, None, {
        'relay_install_root': '/opt/relay', 'relay_release_root': '/opt/relay/releases',
        'relay_namespace': 'relay', 'relay_consumer_config_path': '/etc/relay/consumer.json',
        'relay_github_repository': 'example/consumer',
    }, {'revision': TARGET}, '12345678-1234-4234-8234-123456789abc')
    preparation.captured, preparation.initial = True, {'baselineDigest': CONSUMER}
    calls = []
    preparation.verify_stage = lambda: calls.append('verify')
    def execute(argv, **options):
        calls.append((argv, options))
        return {'drained': True}
    preparation.execute = execute
    assert preparation.drain_staged()['drained'] is True
    assert calls[0] == 'verify'
    argv, options = calls[1]
    assert 'RELAY_CONSUMER_CONFIG=/etc/relay/consumer.json' in argv
    assert 'RELAY_REPOSITORY=example/consumer' in argv
    assert preparation.source + '/controller/src/admission-cli.mjs' in argv
    assert argv[-5:] == ['drain', '--operation', preparation.operation, '--timeout', '1800']
    assert options['timeout'] == 1860
    preparation.execute = lambda *_args, **_kwargs: {'drained': False}
    with pytest.raises(RuntimeError, match='STAGED_DRAIN_UNPROVEN'):
        preparation.drain_staged()


@pytest.mark.parametrize('failure', [None, 'compatibility', 'final', 'backend-return', 'receipt-finalize'])
def test_bounded_recovery_uses_current_controller_and_final_pair_before_resume(invocation, monkeypatch, failure):
    """Exercise the public primitive's composition; host adapters remain synthetic here."""
    import bounded_recovery
    args, events, gate, state, records = invocation
    operation = '12345678-1234-4234-8234-123456789abc'
    binding = {'operationId': operation, 'retainedTarget': OLD, 'installedRevision': OLD,
               'controllerRevision': TARGET, 'desiredRevision': TARGET, 'gitConfigReceipt': args.git_intent}
    original_proof = {'binding': binding, 'original': 'protected-original-evidence'}
    reserved = {**original_proof, 'state': 'reserved'}
    args.authorize_lifecycle_recovery, args.lifecycle_recovery_operation = True, operation
    args._intent_bounded_recovery, args._intent_bounded_recovery_proof = binding, original_proof
    state['failure'] = failure
    gate.update(phase='recovery-required', operation=operation, operationId=operation,
                target=OLD, active=[], unknown=[])
    monkeypatch.setattr(bounded_recovery, 'remote_probe', lambda *_args: original_proof)
    base = install_preflight.PreparedInstall
    class RecoveryPreparation(base):
        def lock_writer(self):
            assert self.holder is None
            super().lock_writer()
        def execute(self, argv, **_options):
            assert self.holder is not None and argv[0] == 'verified-private-admission'
            command, options = argv[1], argv[2:]
            events.append('controller:' + command)
            if command == 'recovery-target': gate['target'] = options[options.index('--target') + 1]
            if command == 'phase': gate['phase'] = options[options.index('--phase') + 1]
            return copy.deepcopy(gate)
        def bounded_recovery(self, _config, selected, proof, *, action='begin'):
            assert self.holder is not None and selected == binding
            events.append('receipt:' + action)
            if action == 'begin': assert proof == original_proof
            else: assert proof == reserved
            if action == 'finalize' and failure == 'receipt-finalize':
                raise RuntimeError('BOUNDED_RECOVERY_FINAL_INSTALLATION_UNPROVEN')
            return reserved
    monkeypatch.setattr(install_preflight, 'PreparedInstall', RecoveryPreparation)
    def readback(report, revision, receipt, **_options):
        assert revision == TARGET and receipt == binding['gitConfigReceipt']
        assert report['installed']['status'] == 'present'
        events.append('final-git-pair-readback')
    monkeypatch.setattr(intent_install, 'readback', readback)
    if failure:
        with pytest.raises((ValueError, RuntimeError)):
            backend.run(args)
        assert gate['phase'] == 'recovery-required' and 'resume' not in events
    else:
        backend.run(args)
        assert gate['phase'] == 'open'
        assert events.index('receipt:begin') < events.index('controller:recovery-target') < events.index('compatibility')
        assert events.index('receipt:revalidate') < events.index('controller:phase') < events.index('backend')
        assert events.index('backend') < events.index('final-git-pair-readback') < events.index('phase:verified')
        assert events.index('phase:verified') < events.index('receipt:finalize') < events.index('resume')
    assert 'quiesce' not in events and 'abort' not in events
    assert state['preparation'].operation == operation and records == [{'runId': 7, 'terminal': True}]


@pytest.mark.parametrize('failure', [None, 'prerequisites', 'build-stage'])
def test_fresh_product_packages_precede_real_staging_without_fabricating_a_gate(invocation, failure):
    args, events, gate, state, records = invocation
    args.phase, args.authorize_upgrade, args.authorize_bootstrap = 'bootstrap', False, True
    args.intent_expected_installed_revision, state['installed'] = 'none', None
    args._intent_fresh_bootstrap = True
    state['failure'] = failure
    if failure:
        with pytest.raises(RuntimeError, match='INJECTED'):
            backend.run(args)
        assert 'backend' not in events
    else:
        backend.run(args)
        assert events.index('prerequisites') < events.index('source-stage') < events.index('build-stage') < events.index('backend')
    assert not {'quiesce', 'drain', 'abort', 'phase:recovery-required'}.intersection(events)
    assert args._intent_product_prerequisites is True
    assert records == [{'runId': 7, 'terminal': True}]


def test_unsupported_replacement_rebind_is_reported_before_old_retirement(invocation):
    args, events, gate, state, _records = invocation
    args.phase, args.authorize_upgrade, args.authorize_reinstall = 'reinstall', False, True
    state['consumer_change'] = True
    with pytest.raises(RuntimeError, match='REINSTALL_CONSUMER_REBIND_UNSUPPORTED') as failure:
        backend.run(args)
    assert 'original gate and history' in failure.value.next_action
    assert gate == {'phase': 'open', 'operation': None}
    assert not {'quiesce', 'prepare-target', 'backend', 'phase:recovery-required'}.intersection(events)


def test_same_consumer_replacement_releases_retirement_lock_and_checks_installed_state(invocation, monkeypatch):
    import clean_reinstall
    args, events, _gate, _state, _records = invocation
    args.phase, args.authorize_upgrade, args.authorize_reinstall = 'reinstall', False, True
    def retire(*_args, action, **_options):
        events.append(action)
        if action == 'decommission':
            assert events[-2] == 'writer-release'
        return {'journalSha256': '1' * 64}
    monkeypatch.setattr(clean_reinstall, 'remote_action', retire)
    backend.run(args)
    assert events.index('final') < events.index('decommission') < events.index('backend') < events.index('complete')
    assert events.count('writer-lock') == events.count('writer-release') == 2
    assert events.index('decommission') < events.index('after-retirement') < events.index('backend')
