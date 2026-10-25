"""Native retained lifecycle evidence admits only the same target and UUID."""
import copy
import json
import os
from pathlib import Path
import sys
import shutil
import subprocess
import tempfile
from types import SimpleNamespace

import pytest

pytest.importorskip('fcntl', reason='native deployment recovery contract')
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
import install_recovery as recovery
from test_intent_install import invocation

OLD = 'a' * 40
TARGET = 'b' * 40
OPERATION = '12345678-1234-4234-8234-123456789abc'


@pytest.fixture
def installed(tmp_path):
    namespace = 'relay-recovery-fixture'
    release = tmp_path / 'opt' / namespace / 'releases' / OLD
    source = release / 'reviewed-source'
    source.mkdir(parents=True)
    (source / 'controller').mkdir()
    (source / 'controller/reader.mjs').write_text('// protected original installed reader\n')
    (source / '.relay-source.json').write_text(json.dumps({'revision': OLD, 'tree': 'c' * 40}))
    (release / 'artifact-manifest.json').write_text(json.dumps({
        'commit': OLD, 'installedRevision': OLD, 'resolvedRevision': OLD, 'gitTree': 'c' * 40}))
    install = release.parent.parent
    (install / 'current').symlink_to('/opt/' + namespace + '/releases/' + OLD)
    (install / 'relay-admission').write_text('#!/bin/sh\n# installed qualified reader\n')
    (tmp_path / 'var/lib').mkdir(parents=True)
    claims = tmp_path / 'var/lib' / namespace / 'claims'
    claims.mkdir(parents=True)
    config = {'environment': {'namespace': namespace}, 'consumer': {'paths': {'claimRoot': str(claims)}}}
    status = {'version': 1, 'phase': 'recovery-required', 'operationId': OPERATION,
              'target': TARGET, 'consumerDigest': 'd' * 64, 'active': [], 'unknown': [],
              'previousActive': None, 'verifiedRevision': None}
    gate_path = claims / 'admission-v1.json'
    gate_path.write_text(json.dumps({k: v for k, v in status.items() if k not in ['active', 'unknown']}))
    gate_path.chmod(0o600)
    seen = []
    def reader(argv, **options):
        assert argv == [str(install / 'relay-admission'), 'status']
        assert options['env']['PATH'] == '/usr/bin:/bin'
        seen.append('installed-reader')
        return SimpleNamespace(returncode=0, stdout=json.dumps(status), stderr='')
    def resource_probe(value, **options):
        assert value == config and options == {'root': tmp_path, 'owner_uid': os.geteuid()}
        seen.append('actual-resources')
    return {'root': tmp_path, 'config': config, 'status': status, 'seen': seen, 'source': source,
            'runner': reader, 'resource_probe': resource_probe, 'gate_path': gate_path,
            'operation': tmp_path / 'var/lib' / (namespace + '-production-operation.json'),
            'journal': tmp_path / 'var/lib' / (namespace + '-clean-reinstall.json')}


def probe(fixture):
    return recovery.inspect(fixture['config'], TARGET, OLD, root=fixture['root'], owner_uid=os.geteuid(),
                            runner=fixture['runner'], resource_probe=fixture['resource_probe'])


@pytest.mark.parametrize('backend', [False, True])
def test_same_target_retains_original_uuid_without_changing_evidence(installed, backend):
    if backend:
        installed['operation'].write_text(json.dumps({'schemaVersion': '1', 'state': 'RECOVERY_REQUIRED',
            'phase': 'apply', 'target_head': TARGET}))
        installed['operation'].chmod(0o600)
    original = copy.deepcopy(installed['status'])
    assert probe(installed) == {'operationId': OPERATION, 'target': TARGET, 'installedRevision': OLD}
    assert installed['status'] == original
    assert installed['seen'] == ['actual-resources', 'installed-reader']
    assert installed['operation'].exists() is backend
    assert not installed['journal'].exists()


@pytest.mark.parametrize('changed', [
    {'target': 'e' * 40}, {'phase': 'quiesced'}, {'operationId': 'not-a-uuid'},
    {'active': [11]}, {'unknown': [12]}, {'verifiedRevision': TARGET}, {'consumerDigest': 'invalid'}])
def test_unknown_or_conflicting_admission_is_not_recovery_authority(installed, changed):
    installed['status'].update(changed)
    with pytest.raises(ValueError, match='RELAY_INSTALL_RECOVERY_'):
        probe(installed)


@pytest.mark.parametrize('record', ['journal', 'journal-next', 'foreign-operation'])
def test_foreign_or_reinstall_records_require_their_own_classifier(installed, record):
    if record == 'foreign-operation':
        path = installed['operation']
        value = {'schemaVersion': '1', 'state': 'RECOVERY_REQUIRED', 'phase': 'activate', 'target_head': TARGET}
    else:
        path = installed['journal']
        if record == 'journal-next':
            path = path.with_name(path.name + '.next')
        value = {'unproven': True}
    path.write_text(json.dumps(value)); path.chmod(0o600)
    with pytest.raises(ValueError, match='RELAY_INSTALL_RECOVERY_'):
        probe(installed)
    assert not installed['seen']


def test_an_open_gate_does_not_create_recovery_authority(installed):
    installed['status'].update(phase='open', operationId=None, target=None)
    installed['gate_path'].write_text(json.dumps({k: v for k, v in installed['status'].items()
                                                if k not in ['active', 'unknown']}))
    assert probe(installed) is None
    assert installed['seen'] == ['actual-resources']


@pytest.mark.parametrize('blockers', [[recovery.OPERATION_BLOCKER],
    [recovery.OPERATION_BLOCKER, 'installed-identity-invalid'], ['clean-reinstall-recovery-present;inspect-before-retry']])
def test_only_the_exact_backend_blocker_can_await_the_locked_probe(blockers):
    report = {'installed': {'status': 'present', 'revision': OLD}, 'blockers': blockers[:]}
    candidate = recovery.provisional_inventory(report)
    assert candidate['blockers'] == ([] if blockers == [recovery.OPERATION_BLOCKER] else blockers)
    assert report['blockers'] == blockers


def test_provisional_backend_inventory_requires_an_exact_fresh_proof():
    report = {'installed': {'status': 'present', 'revision': OLD}, 'blockers': [recovery.OPERATION_BLOCKER]}
    proof = {'operationId': OPERATION, 'target': TARGET, 'installedRevision': OLD}
    assert recovery.proved_inventory(report, None, TARGET, OLD)['blockers'] == report['blockers']
    assert recovery.proved_inventory(report, proof, TARGET, OLD)['blockers'] == []
    with pytest.raises(ValueError, match='INVENTORY_BINDING_CHANGED'):
        recovery.proved_inventory(report, {**proof, 'target': 'e' * 40}, TARGET, OLD)
    assert report['blockers'] == [recovery.OPERATION_BLOCKER]


@pytest.mark.parametrize('damaged', ['identity', 'unsafe-code', 'foreign-alias'])
def test_current_source_is_proven_before_installed_code_executes(installed, damaged):
    if damaged == 'identity':
        (installed['source'] / '.relay-source.json').write_text(json.dumps({'revision': 'e' * 40, 'tree': 'c' * 40}))
    elif damaged == 'unsafe-code':
        (installed['source'] / 'controller/reader.mjs').chmod(0o666)
    else:
        (installed['source'] / 'legacy').mkdir()
        (installed['source'] / 'legacy/reader').symlink_to('/opt/foreign/controller')
    with pytest.raises(ValueError, match='(?:RELAY_INSTALL_RECOVERY_|REINSTALL_)'):
        probe(installed)
    assert not installed['seen']


@pytest.mark.parametrize('value', [None, {'operationId': OPERATION, 'target': TARGET, 'installedRevision': OLD}])
def test_owner_transport_requires_held_guards_and_a_bound_result(installed, monkeypatch, value):
    import ansible_transport
    guard = SimpleNamespace(poll=lambda: None)
    calls = []
    def run_target(target, key, argv, **options):
        assert argv[:3] == ['/usr/bin/python3', '-I', '-c']
        compile(argv[3], '<owner-recovery-transport>', 'exec')
        payload = json.loads(options['input'])
        assert payload == {'config': installed['config'], 'revision': TARGET, 'installed': OLD}
        calls.append('read-only-probe')
        return SimpleNamespace(returncode=0, stdout=json.dumps(value), stderr='')
    monkeypatch.setattr(ansible_transport, 'run_target', run_target)
    assert recovery.remote_probe({}, Path('/unused'), installed['config'], TARGET, OLD, guard, guard) == value
    assert calls == ['read-only-probe']
    with pytest.raises(ValueError, match='HOST_LOCK_LOST'):
        recovery.remote_probe({}, Path('/unused'), installed['config'], TARGET, OLD,
                              SimpleNamespace(poll=lambda: 1), guard)
    assert calls == ['read-only-probe']


@pytest.mark.parametrize('changed', [None, {'operationId': '22345678-1234-4234-8234-123456789abc'},
                                   {'target': 'e' * 40}, {'installedRevision': 'f' * 40}])
def test_inner_boundary_reproves_the_same_retained_operation(monkeypatch, changed):
    original = {'operationId': OPERATION, 'target': TARGET, 'installedRevision': OLD}
    observed = {**original, **changed} if changed is not None else None
    calls = []
    def remote(*arguments):
        calls.append(arguments)
        return observed
    monkeypatch.setattr(recovery, 'remote_probe', remote)
    with pytest.raises(ValueError, match='PROOF_CHANGED'):
        recovery.revalidate(original, 'target', 'key', {}, TARGET, OLD, 'host-guard', 'pool-guard')
    assert calls == [('target', 'key', {}, TARGET, OLD, 'host-guard', 'pool-guard')]
    monkeypatch.setattr(recovery, 'remote_probe', lambda *_arguments: original)
    assert recovery.revalidate(original, 'target', 'key', {}, TARGET, OLD, 'host-guard', 'pool-guard') == original


@pytest.mark.skipif(os.geteuid() != 0, reason='native authentic gate and private mount view require root')
@pytest.mark.parametrize('desired_effort', ['xhigh', 'high'])
def test_outer_install_allows_authenticated_open_gate_profile_drift_repair(invocation, monkeypatch, desired_effort):
    """A real old gate rejects live drift, yet outer planning reaches real repair."""
    import consumer_drift
    import intent_install
    import inventory
    from test_intent_install import observed, CONTRACT
    node = Path('/home/hortonolite/.nvm/versions/node/v22.20.0/bin/node')
    if not node.is_file():
        pytest.skip('qualified Node 22 is unavailable')
    namespace_probe = subprocess.run(['unshare', '--mount', '--fork', 'true'], capture_output=True)
    if namespace_probe.returncode:
        pytest.skip('private mount namespaces unavailable')
    args, config, receipt, _ = invocation
    with tempfile.TemporaryDirectory(prefix='relay-outer-valid-drift-', dir='/run') as temporary:
        root = Path(temporary)
        paths = recovery.retained.namespace_paths(config, root)
        for path in [paths['config'], paths['state']]:
            path.mkdir(parents=True)
        release = paths['install'] / 'releases' / OLD
        source = release / 'reviewed-source'
        source.mkdir(parents=True)
        for component in ['consumer', 'controller', 'contracts', 'runtime', 'reviewer']:
            shutil.copytree(ROOT / component, source / component,
                            ignore=shutil.ignore_patterns('__pycache__', 'node_modules', 'target'))
        for path in source.rglob('*'):
            path.chmod(0o755 if path.is_dir() else 0o644)
        (source / '.relay-source.json').write_text(json.dumps({'revision': OLD, 'tree': 'c' * 40}))
        (paths['install'] / 'current').symlink_to('releases/' + OLD)
        for key, value in config['consumer']['paths'].items():
            config['consumer']['paths'][key] = str(root / value.lstrip('/'))
        unit_root = root / 'etc/systemd/system'
        unit_root.mkdir(parents=True)
        names = recovery.retained.unit_names(config)
        identities = {names[2]: config['environment']['reviewerUser'],
                      **{unit: user for _, user, unit in recovery.retained.runner_specs(config)}}
        for unit, user in identities.items():
            (unit_root / unit).write_text('[Service]\nUser=' + user + '\n')
        config['consumer']['defaultProfile']['effort'] = 'xhigh'
        claims = Path(config['consumer']['paths']['claimRoot'])
        claims.mkdir(parents=True)
        (claims / 'publication-v2.lock').write_bytes(b'')
        (claims / 'publication-v2.lock').chmod(0o600)
        original = paths['config'] / 'consumer.json'
        original.write_text(json.dumps(config['consumer']))
        original.chmod(0o644)
        snapshot = (json.dumps(config, sort_keys=True, separators=(',', ':')) + '\n').encode()
        (release / 'deployment-config.json').write_bytes(snapshot)
        (release / 'deployment-config.json').chmod(0o600)
        (release / 'artifact-manifest.json').write_text(json.dumps({'commit': OLD,
            'installedRevision': OLD, 'resolvedRevision': OLD, 'gitTree': 'c' * 40,
            'deploymentConfigSha256': __import__('hashlib').sha256(snapshot).hexdigest()}))
        environment = {'PATH': '/usr/bin:/bin', 'RELAY_CONSUMER_CONFIG': str(original),
                       'RELAY_REPOSITORY': config['consumer']['repository']}
        cli = source / 'controller/src/admission-cli.mjs'
        initialized = subprocess.run([str(node), str(cli), 'initialize'], env=environment,
                                     text=True, capture_output=True, timeout=30)
        assert initialized.returncode == 0, initialized.stderr
        gate_path = claims / 'admission-v1.json'
        gate = gate_path.read_bytes()
        authentic_consumer = copy.deepcopy(config['consumer'])
        backup = paths['config'] / 'consumer-before-22345678-1234-4234-8234-123456789abc.json'
        backup.write_bytes(original.read_bytes())
        backup.chmod(0o600)
        drifted = copy.deepcopy(config['consumer'])
        drifted['defaultProfile']['effort'] = 'medium'
        original.write_text(json.dumps(drifted))
        rejected = subprocess.run([str(node), str(cli), 'status'], env=environment,
                                  text=True, capture_output=True, timeout=30)
        assert rejected.returncode != 0 and 'CONSUMER_CONFIG_CHANGED' in rejected.stderr
        config['consumer']['defaultProfile']['effort'] = desired_effort
        raw = json.dumps(config).encode()
        args.config.write_bytes(raw)
        receipt['config_sha256'] = __import__('hashlib').sha256(raw).hexdigest()
        before, after = observed(OLD, CONTRACT), observed(TARGET, CONTRACT)
        before['configuration'].update(status='different', consumer='different')
        after['configuration']['status'] = 'equivalent'
        after['installed']['gitConfigReceipt'] = copy.deepcopy(receipt)
        repaired = []
        monkeypatch.setattr(inventory, 'remote_inventory', lambda *_a, **_k: after if repaired else before)
        def probe(_target, _key, desired, target, installed, host_guard, pool_guard):
            assert host_guard.poll() is None and installed == OLD and target == TARGET
            return recovery.inspect(desired, target, installed, root=root,
                runner=lambda *_a, **_k: pytest.fail('open gate must reach authentic drift repair first'))
        monkeypatch.setattr(recovery, 'remote_probe', probe)
        def primitive(inner):
            assert not getattr(inner, 'authorize_lifecycle_recovery', False)
            result = consumer_drift.restore(config, config['consumer'], TARGET, OPERATION,
                                           root=root, node=str(node))
            assert result['status'] == 'restored'
            repaired.append(result)
        intent_install.run(args, primitive, ROOT, {'revision': TARGET})
        assert len(repaired) == 1
        assert json.loads(original.read_text()) == authentic_consumer
        current_gate = json.loads(gate_path.read_text())
        assert current_gate['phase'] == 'quiesced' and current_gate['operationId'] == OPERATION
        assert current_gate['consumerDigest'] == json.loads(gate)['consumerDigest']
