"""Compose the real recovery and deployment engines across two real Git objects.

Git checkout/archive, source identities, config parsing and deployment orchestration
execute for real. Host, Writer, admission, artifact and Ansible observations use
the existing isolated ordering adapters; this proves no live host or service.
"""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bounded_recovery
import install_preflight
import intent_install
import partial_install_recovery
import pre_apply_recovery as recovery
import test_install_preflight_ordering as ordering
from test_install_preflight_ordering import invocation
from test_intent_install import Guard


def product_repository(root):
    """Real engine/schema bytes; unexecuted component leaves are only identities."""
    actual = [
        'deploy/relay-deploy.py', 'deploy/installation-contract.json',
        'consumer/consumer.mjs', 'consumer/consumer-config.mjs',
        'contracts/src/execution-defaults.mjs', 'reviewer/src/executable-cr-v2.json',
        'deploy/ansible/site.yml', 'deploy/ansible/group_vars/all.yml',
        'deploy/ansible/roles/relay_codex_runtime/templates/relay-codex-launcher.mjs.j2',
        'deploy/ansible/roles/relay_codex_runtime/templates/relay-codex-cleanup.py.j2',
    ]
    for name in actual:
        destination = root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ordering.ROOT / name, destination)
    for name in ['controller/src/fixture.mjs', 'runtime/src/fixture.mjs',
                 'runtime/config/fixture.json']:
        destination = root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text('{}\n')
    (root / 'marker').write_text('original frozen product\n')
    command = ['git', '-C', str(root)]
    subprocess.run([*command, 'init', '-q', '--template='], check=True)

    def commit(message):
        subprocess.run([*command, 'add', '.'], check=True)
        subprocess.run([*command, '-c', 'user.name=Fixture',
            '-c', 'user.email=fixture@example.invalid', 'commit', '-q',
            '--no-gpg-sign', '-m', message], check=True)
        return subprocess.check_output([*command, 'rev-parse', 'HEAD'], text=True).strip()

    desired = commit('Original frozen product')
    (root / 'marker').write_text('separately accepted controller\n')
    with (root / 'deploy/relay-deploy.py').open('a') as stream:
        stream.write('\nRECOVERY_CONTROLLER_FIXTURE = True\n')
    controller = commit('Separate recovery controller identity')
    return desired, controller


@pytest.mark.parametrize('failure', [None, 'backend-return'])
def test_real_engine_keeps_frozen_product_and_original_operation(
        invocation, tmp_path, monkeypatch, capsys, failure):
    args, events, gate, state, history = invocation
    root = tmp_path / 'controller'
    desired, controller = product_repository(root)
    operation = '12345678-1234-4234-8234-123456789abc'
    # Existing transport adapters emit their evidence from these fixture IDs.
    monkeypatch.setattr(ordering, 'TARGET', desired)
    monkeypatch.setattr(ordering, 'CONSUMER', controller)
    args.phase, args.authorize_upgrade = 'install', False
    args.authorize_install_recovery = args.continue_install_recovery = True
    args.install_recovery_operation, args.install_recovery_target = operation, ordering.OLD
    args.resolved_revision, args.consumer_root = controller, root
    configuration = json.loads(args.config.read_text())
    configuration['source']['revision'] = desired
    args.config.write_text(json.dumps(configuration))
    args.git_intent.update(product_sha=desired, source_policy='test-qualified-exact',
        config_sha256=hashlib.sha256(args.config.read_bytes()).hexdigest())
    binding = {'operationId': operation, 'retainedTarget': ordering.OLD,
        'installedRevision': ordering.OLD, 'controllerRevision': desired,
        'desiredRevision': desired, 'gitConfigReceipt': copy.deepcopy(args.git_intent)}
    receipt = {'binding': binding, 'state': 'reserved', 'desiredDigest': '2' * 64,
               'original': {'fixture': 'immutable original evidence'}}
    original = copy.deepcopy(receipt)
    observed = {'receipt': receipt, 'gate': {'phase': 'recovery-required'},
                'receiptSha256': '3' * 64}
    gate.update(phase='recovery-required', operation=operation, operationId=operation,
                target=desired, active=[], unknown=[])
    state['failure'] = failure
    monkeypatch.setattr(intent_install, 'qualify_identity', lambda *_a: None)
    monkeypatch.setattr(recovery, 'remote_inspect', lambda *_a: copy.deepcopy(observed))
    monkeypatch.setattr(bounded_recovery, 'remote_probe', lambda *_a: copy.deepcopy(receipt))

    # TEST policy is already part of the reserved fixture receipt. No public
    # acceptance, credentials, SSH, Ansible or protected filesystem is contacted.
    accepted = partial_install_recovery.accepted_controller(root, binding, controller)
    assert accepted == {'policy': 'test-qualified-exact', 'revision': controller}
    base = install_preflight.PreparedInstall

    class RecoveryPreparation(base):
        def __init__(self, target, key, values, identity, selected_operation, **options):
            assert identity['revision'] == desired and selected_operation == operation
            super().__init__(target, key, values, identity, selected_operation, **options)

        def execute(self, argv, **_options):
            assert self.holder is not None and argv[0] == 'verified-private-admission'
            command, options = argv[1], argv[2:]
            events.append('controller:' + command)
            if command == 'recovery-target':
                gate['target'] = options[options.index('--target') + 1]
            elif command == 'phase':
                gate['phase'] = options[options.index('--phase') + 1]
            return copy.deepcopy(gate)

        def bounded_recovery(self, _config, selected, proof, *, action='begin'):
            assert self.holder is not None and selected == binding and proof == original
            events.append('receipt:' + action)
            return copy.deepcopy(receipt)

    monkeypatch.setattr(install_preflight, 'PreparedInstall', RecoveryPreparation)
    original_spec = recovery.importlib.util.spec_from_file_location
    engines, archives = [], []

    def engine_spec(name, location, *arguments, **options):
        spec = original_spec(name, location, *arguments, **options)
        if name != 'frozen_product_recovery':
            return spec
        execute = spec.loader.exec_module

        def execute_engine(engine):
            execute(engine)
            assert engine.RECOVERY_CONTROLLER_FIXTURE is True
            engines.append(engine)
            # Retain real run(), source_identity(), clean_git() and git(). Only
            # external operational adapters use the existing ordering fixture.
            engine.remote_admission = ordering.backend.remote_admission

            def backend(argv, cwd, environment, log, guard=None, extra_guard=None):
                assert engine.BACKEND == root / 'deploy/ansible'
                assert cwd == engine.BACKEND and Path(argv[3]).parent == engine.BACKEND
                assert engine.ROOT != root and engine.source_identity(engine.ROOT)['revision'] == desired
                values = next(iter(json.loads(Path(argv[2]).read_text())[
                    'all']['children']['relay']['hosts'].values()))
                assert values['relay_source_identity']['revision'] == desired
                assert values['relay_git_config_receipt'] == original['binding']['gitConfigReceipt']
                assert values['relay_admission_operation_id'] == operation
                with tarfile.open(values['relay_source_archive']) as archive:
                    assert archive.extractfile('marker').read() == b'original frozen product\n'
                    frozen_engine = archive.extractfile('deploy/relay-deploy.py').read()
                    assert frozen_engine == (ordering.ROOT / 'deploy/relay-deploy.py').read_bytes()
                    assert b'RECOVERY_CONTROLLER_FIXTURE' not in frozen_engine
                archives.append(values['relay_source_identity'])
                result = ordering.backend.run_backend(argv, cwd, environment, log, guard, extra_guard)
                if Path(argv[3]).name == 'site.yml' and result == 0:
                    state['installed'] = desired
                return result

            engine.run_backend = backend

        spec.loader.exec_module = execute_engine
        return spec

    monkeypatch.setattr(recovery.importlib.util, 'spec_from_file_location', engine_spec)

    def readback(report, revision, selected_receipt, **_options):
        assert report['installed']['revision'] == revision == desired
        assert selected_receipt == original['binding']['gitConfigReceipt']
        events.append('final-git-pair-readback')

    monkeypatch.setattr(intent_install, 'readback', readback)
    guard = Guard()
    if failure:
        with pytest.raises(ValueError):
            recovery.run(args, root, {'revision': controller}, guard_factory=lambda *_a: guard)
        output = capsys.readouterr().out
        result = json.loads(next(line.removeprefix('RELAY_INSTALL_FAILURE=')
            for line in output.splitlines() if line.startswith('RELAY_INSTALL_FAILURE=')))
        assert result['target'] == desired and result['controller'] == controller
        assert result['hostMutation'] == 'unknown' and result['automaticRetrySafe'] is False
        assert gate['phase'] == 'recovery-required'
        assert not {'resume', 'receipt:finalize', 'final-git-pair-readback'}.intersection(events)
    else:
        result = recovery.run(args, root, {'revision': controller}, guard_factory=lambda *_a: guard)
        assert result['product'] == desired and result['controller'] == controller
        assert gate['phase'] == 'open'
        assert events.index('receipt:begin') < events.index('controller:recovery-target')
        assert events.index('receipt:revalidate') < events.index('controller:phase') < events.index('backend')
        assert events.index('backend') < events.index('final-git-pair-readback') < events.index('phase:verified')
        assert events.index('phase:verified') < events.index('receipt:finalize') < events.index('resume')
    assert len(engines) == 1 and archives and guard.releases == 1
    assert receipt == original and history == [{'runId': 7, 'terminal': True}]
    assert 'quiesce' not in events and 'abort' not in events
    assert state['preparation'].operation == operation
