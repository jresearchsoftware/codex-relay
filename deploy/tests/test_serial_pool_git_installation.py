"""Completed SERIAL history does not select a later Git desired configuration."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys

import pytest

pytest.importorskip('fcntl', reason='native Linux deployment contract')
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
import managed_pool
import serial_pool_installation as installation
import serial_pool_transition as transition

OLD = '1' * 40
CURRENT = '2' * 40
NEXT = '3' * 40
OPERATION = '12345678-1234-4234-8234-123456789abc'
LATER = '22345678-1234-4234-8234-123456789abc'
RECEIPT_DIGEST = 'a' * 64
CURRENT_DIGEST = 'b' * 64
DESIRED_DIGEST = 'c' * 64


@pytest.fixture
def retired(monkeypatch):
    namespace = 'relay-serial-git-fixture'
    claim = '/var/lib/' + namespace + '/claims'
    original = {'environment': {'namespace': namespace, 'compatibilityLinks': {}},
                'consumer': {'repository': 'example/consumer', 'paths': {'claimRoot': claim}}}
    desired = copy.deepcopy(original)
    desired['environment']['localApply'] = {'source': 'git', 'repository': 'example/private',
                                          'configPath': 'prod/relay.json'}
    desired['consumer']['defaultProfile'] = {'model': 'fixture', 'effort': 'medium'}
    source = '/opt/' + namespace + '/serial-compat-v1/' + OLD + '/reviewed-source'
    binding = {'runnerId': 71, 'runnerName': 'legacy-runner'}
    old_gate = b'original sealed gate\n'
    receipt = {'target': {'consumerDigest': RECEIPT_DIGEST}, 'original': {
        'sourceTreeSha256': 'd' * 64, 'gateSha256': hashlib.sha256(old_gate).hexdigest()}}
    raw = transition.encoded(receipt) + b'\n'
    state = {'phase': 'retired', 'operationId': OPERATION, 'targetRevision': CURRENT,
             'receiptSha256': hashlib.sha256(raw).hexdigest(), 'plan': {
                 'binding': binding, 'targetConfigSha256': hashlib.sha256(transition.encoded(desired)).hexdigest()}}
    gate = {'consumerDigest': CURRENT_DIGEST, 'phase': 'open', 'operationId': None, 'target': None}
    paths = {'/etc/' + namespace + '/serial-pool-compat-v1.json': raw,
             '/etc/' + namespace + '/consumer.json': b'{"generalRunnerPool":{"desiredCapacity":1}}',
             claim + '/serial-pool-transition-v1.json': transition.encoded(state),
             claim + '/admission-v1.json': old_gate,
             claim + '/admission-pool-v1.json': transition.encoded(gate)}

    class Files:
        def read(self, path, **_options):
            return paths[path]
        def tree_sha256(self, *_args, **_options):
            return 'd' * 64

    class Host:
        def __init__(self, *_args, **_options):
            pass
        def inspect_legacy(self, value):
            assert value == original
            return {**binding, 'ownWorker': False}
        def legacy_stopped(self, value):
            return value == binding

    class API:
        def observe_legacy(self, value):
            assert value == binding
            return None

    calls = []
    monkeypatch.setattr(installation, 'ProtectedFiles', Files)
    monkeypatch.setattr(installation, 'original_installation', lambda _config: (original, {
        'revision': OLD, 'sourceRoot': source}))
    monkeypatch.setattr(installation, 'original_gate', lambda *_args: None)
    monkeypatch.setattr(installation, 'SerialPoolHost', Host)
    monkeypatch.setattr(installation, 'SerialPoolGitHub', lambda value: value)
    monkeypatch.setattr(installation, 'current_source', lambda config, *, git_desired=False:
                        calls.append(('source', git_desired)) or '/protected/current-source')

    def reader(source_root, consumer_path, code, **options):
        assert source_root == '/protected/current-source'
        assert consumer_path == '/etc/' + namespace + '/consumer.json'
        assert 'installedAdmissionControl().read()' in code and 'CONSUMER_DIGEST' in code
        assert options['repository'] == 'example/consumer'
        calls.append(('reader', consumer_path))
        return {'gate': json.loads(paths[claim + '/admission-pool-v1.json']),
                'digest': current_digest[0], 'managed': True}

    current_digest = [CURRENT_DIGEST]
    monkeypatch.setattr(installation, '_node', reader)
    return {'desired': desired, 'api': API(), 'state': state, 'gate': gate, 'paths': paths,
            'claim': claim, 'calls': calls, 'current_digest': current_digest}


def update(retired, name):
    path = retired['claim'] + ('/serial-pool-transition-v1.json' if name == 'state' else '/admission-pool-v1.json')
    retired['paths'][path] = transition.encoded(retired[name])


@pytest.mark.parametrize('phase', ['open', 'quiesced'])
def test_completed_retirement_keeps_original_receipt_and_accepts_later_git_intent(retired, monkeypatch, phase):
    monkeypatch.setattr(transition, 'validate_delta', lambda *_args: pytest.fail('future intent is not original cutover'))
    if phase == 'quiesced':
        retired['gate'].update(phase=phase, operationId=LATER, target=NEXT)
        update(retired, 'gate')
    before = copy.deepcopy(retired['paths'])
    result = installation.preflight(retired['desired'], retired['api'], DESIRED_DIGEST)
    assert result == {'phase': 'retired', 'operationId': OPERATION,
                      'targetRevision': CURRENT, 'completionRequired': False}
    assert retired['paths'] == before
    assert retired['calls'][0] == ('source', True)


def test_original_incomplete_cutover_keeps_exact_config_and_digest(retired):
    retired['gate'].update(phase='applying', operationId=OPERATION, target=CURRENT,
                           consumerDigest=RECEIPT_DIGEST)
    update(retired, 'gate')
    retired['current_digest'][0] = RECEIPT_DIGEST
    assert installation.preflight(retired['desired'], retired['api'], RECEIPT_DIGEST)['completionRequired'] is True
    # A pending original cutover is not a later Git installation.
    with pytest.raises(managed_pool.PoolError, match='NEW_GATE_UNPROVEN'):
        installation.preflight(retired['desired'], retired['api'], DESIRED_DIGEST)
    changed = copy.deepcopy(retired['desired'])
    changed['consumer']['defaultProfile']['effort'] = 'high'
    with pytest.raises(managed_pool.PoolError, match='NEW_GATE_UNPROVEN'):
        installation.preflight(changed, retired['api'], RECEIPT_DIGEST)


def test_current_gate_must_bind_actual_current_consumer_even_when_desired_matches_it(retired):
    retired['gate']['consumerDigest'] = DESIRED_DIGEST
    update(retired, 'gate')
    with pytest.raises(managed_pool.PoolError, match='NEW_GATE_UNPROVEN'):
        installation.preflight(retired['desired'], retired['api'], DESIRED_DIGEST)


def test_retired_receipt_state_binding_is_not_relaxed(retired):
    retired['state']['receiptSha256'] = 'e' * 64
    update(retired, 'state')
    with pytest.raises(managed_pool.PoolError, match='RETIRED_BINDING_UNPROVEN'):
        installation.preflight(retired['desired'], retired['api'], DESIRED_DIGEST)
    assert not retired['calls']


def test_expert_route_retains_original_owner_delta_gate(retired, monkeypatch):
    retired['desired']['environment']['localApply'] = {'configPath': 'deploy/config.json'}
    def reject(*_args):
        raise managed_pool.PoolError('SERIAL_TRANSITION_OWNER_INTENT_CHANGED')
    monkeypatch.setattr(transition, 'validate_delta', reject)
    with pytest.raises(managed_pool.PoolError, match='OWNER_INTENT_CHANGED'):
        installation.preflight(retired['desired'], retired['api'], DESIRED_DIGEST)
    assert not retired['calls']


@pytest.mark.parametrize('managed', [True, False])
def test_no_receipt_git_managed_host_does_not_use_mutable_snapshot_as_original_history(tmp_path, monkeypatch, managed):
    namespace = 'relay-managed-fixture'
    current = tmp_path / namespace / 'current'
    current.mkdir(parents=True)
    desired = {'environment': {'namespace': namespace, 'localApply': {'source': 'git'}}}
    live = {'generalRunnerPool': {'desiredCapacity': 1}} if managed else {'repository': 'example/consumer'}
    class Files:
        def read(self, path, **_options):
            return None if path.endswith('serial-pool-compat-v1.json') else transition.encoded(live)
    monkeypatch.setattr(installation, 'ProtectedFiles', Files)
    monkeypatch.setattr(installation, 'Path', lambda _value: tmp_path)
    def original(_config):
        raise managed_pool.PoolError('EXACT_ORIGINAL_HISTORY_REQUIRED')
    monkeypatch.setattr(installation, 'original_installation', original)
    calls = []
    def actual(config, *, git_desired=False):
        calls.append((config, git_desired))
        return {'managed': True, 'digest': CURRENT_DIGEST, 'gate': {'consumerDigest': CURRENT_DIGEST}}
    monkeypatch.setattr(installation, '_current_admission', actual)
    monkeypatch.setattr(installation, 'pool_contract', lambda _config: {})
    import pool_migration
    monkeypatch.setattr(pool_migration, 'reject_serial_transition', lambda _contract: None)
    if managed:
        assert installation.preflight(desired, object(), DESIRED_DIGEST) is None
        assert calls == [(desired, True)]
    else:
        with pytest.raises(managed_pool.PoolError, match='EXACT_ORIGINAL_HISTORY_REQUIRED'):
            installation.preflight(desired, object(), DESIRED_DIGEST)
        assert not calls


@pytest.mark.skipif(sys.platform != 'linux' or os.geteuid() != 0, reason='native protected source boundary')
@pytest.mark.parametrize('snapshot', ['missing', 'tampered'])
def test_git_source_selection_uses_protected_code_not_mutable_config_snapshot(tmp_path, monkeypatch, snapshot):
    namespace = 'relay-serial-source-fixture'
    logical = '/opt/' + namespace + '/releases/' + CURRENT
    release = tmp_path / logical.lstrip('/')
    source = release / 'reviewed-source'
    (source / 'controller').mkdir(parents=True)
    (source / 'controller/module.mjs').write_text('// actual installed code\n')
    (source / '.relay-source.json').write_text(json.dumps({'revision': CURRENT, 'tree': 'f' * 40}))
    (source / 'legacy').mkdir()
    (source / 'legacy/controller').symlink_to(logical + '/reviewed-source/controller')
    manifest = {'commit': CURRENT, 'installedRevision': CURRENT, 'resolvedRevision': CURRENT,
                'gitTree': 'f' * 40, 'deploymentConfigSha256': '0' * 64}
    (release / 'artifact-manifest.json').write_text(json.dumps(manifest))
    (release.parent.parent / 'current').symlink_to(logical)
    if snapshot == 'tampered':
        (release / 'deployment-config.json').write_text('{malformed overwritten snapshot')
    for path in tmp_path.rglob('*'):
        if not path.is_symlink():
            path.chmod(0o755 if path.is_dir() else 0o600)
    files = transition.ProtectedFiles(tmp_path)
    monkeypatch.setattr(installation, 'ProtectedFiles', lambda: files)
    desired = {'environment': {'namespace': namespace}, 'consumer': {'repository': 'example/consumer'}}
    assert installation.current_source(desired, git_desired=True) == logical + '/reviewed-source'
    with pytest.raises((managed_pool.PoolError, FileNotFoundError, ValueError)):
        installation.current_source(desired)
    # Desired config cannot legitimize a foreign alias or an unsafe source.
    alias = source / 'legacy/controller'
    alias.unlink()
    alias.symlink_to('/opt/foreign/controller')
    with pytest.raises(managed_pool.PoolError, match='SOURCE_LINK_UNPROVEN'):
        installation.current_source(desired, git_desired=True)
