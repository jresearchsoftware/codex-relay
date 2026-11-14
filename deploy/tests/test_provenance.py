"""Real protected manifest promotion, failure atomicity and exact replay."""
import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import provenance
from intent_install import pair_digest


@pytest.fixture
def pair(tmp_path):
    root = tmp_path / 'root'
    root.mkdir(mode=0o700)
    revision = 'a' * 40
    release = root / 'opt/test/releases' / revision
    (release / 'reviewed-source').mkdir(parents=True)
    old = {'product_repository': 'example/product', 'product_repository_id': 1,
           'product_sha': revision, 'config_repository': 'example/config',
           'config_repository_id': 2, 'config_path': 'test/relay.json',
           'config_sha': 'b' * 40, 'config_blob_sha': 'c' * 40,
           'config_sha256': 'd' * 64, 'source_policy': 'test-qualified-exact',
           'workflow_run_id': 1}
    new = {**old, 'config_sha': 'e' * 40, 'workflow_run_id': 2}
    snapshot = b'{"synthetic":"config"}\n'
    digest = hashlib.sha256(snapshot).hexdigest()
    manifest = {**{key: revision for key in ['commit', 'installedRevision', 'resolvedRevision']},
                'gitTree': 'f' * 40, 'gitConfigReceipt': old, 'deploymentConfigSha256': digest,
                'installationState': {'schemaVersion': 1, 'stage': 'ready', 'pairSha256': pair_digest(old)},
                'retained': {'unknown': 'preserved'}}
    (release / 'deployment-config.json').write_bytes(snapshot)
    (release / 'deployment-config.json').chmod(0o600)
    (release / 'reviewed-source/.relay-source.json').write_text(json.dumps({'revision': revision, 'tree': 'f' * 40}))
    path = release / 'artifact-manifest.json'
    path.write_text(json.dumps(manifest))
    path.chmod(0o640)
    (root / 'opt/test/current').symlink_to(release)
    payload = {'namespace': 'test', 'revision': revision, 'previous': old,
               'receipt': new, 'deploymentConfigSha256': digest}
    return root, path, payload


@pytest.mark.parametrize('repository_ids', [True, False])
@pytest.mark.parametrize('ready_marker', [True, False])
def test_atomic_promotion_and_exact_replay_preserve_runtime_snapshot_and_metadata(pair, repository_ids, ready_marker):
    root, path, payload = pair
    if not repository_ids:
        for receipt in [payload['previous'], payload['receipt']]:
            for key in ['product_repository_id', 'config_repository_id']:
                receipt.pop(key)
        value = json.loads(path.read_text())
        value['gitConfigReceipt'] = payload['previous']
        value['installationState']['pairSha256'] = pair_digest(payload['previous'])
        path.write_text(json.dumps(value))
    if not ready_marker:
        value = json.loads(path.read_text())
        value.pop('installationState')
        path.write_text(json.dumps(value))
    from intent_install import provenance_equivalent
    report = {'blockers': [], 'configuration': {'status': 'equivalent'}, 'installed': {
        key: value for key, value in json.loads(path.read_text()).items()
        if key in ['gitConfigReceipt', 'installationState']}}
    assert provenance_equivalent(report, payload['receipt'])
    snapshot = path.with_name('deployment-config.json')
    before = snapshot.stat(), snapshot.read_bytes()
    provenance.promote(payload, root=root, owner_uid=os.getuid())
    result = json.loads(path.read_text())
    assert result['gitConfigReceipt'] == payload['receipt']
    if ready_marker:
        assert result['installationState']['pairSha256'] == pair_digest(payload['receipt'])
    else:
        assert 'installationState' not in result
    assert result['retained'] == {'unknown': 'preserved'}
    assert path.stat().st_mode & 0o777 == 0o640
    assert (snapshot.stat(), snapshot.read_bytes()) == before
    inode = path.stat().st_ino
    provenance.promote(payload, root=root, owner_uid=os.getuid())
    assert path.stat().st_ino == inode


@pytest.mark.parametrize('damage', ['snapshot', 'pending', 'null-state', 'schema-type', 'third-pair', 'product', 'source', 'hardlink', 'mode'])
def test_corrupt_changed_or_interrupted_evidence_refuses_without_receipt_mutation(pair, damage):
    root, path, payload = pair
    value = json.loads(path.read_text())
    if damage == 'snapshot':
        path.with_name('deployment-config.json').write_text('{}')
    elif damage == 'pending':
        value['installationState']['stage'] = 'fresh-incomplete'
    elif damage == 'null-state':
        value['installationState'] = None
    elif damage == 'schema-type':
        value['installationState']['schemaVersion'] = True
    elif damage == 'third-pair':
        value['gitConfigReceipt']['config_sha'] = '0' * 40
    elif damage == 'product':
        payload['receipt']['product_sha'] = '0' * 40
    elif damage == 'source':
        (path.parent / 'reviewed-source/.relay-source.json').write_text('{}')
    elif damage == 'hardlink':
        os.link(path, path.with_name('alias'))
    elif damage == 'mode':
        path.chmod(0o666)
    if damage in ['pending', 'null-state', 'schema-type', 'third-pair']:
        path.write_text(json.dumps(value))
    before = path.read_bytes()
    with pytest.raises(ValueError, match='PROVENANCE_BINDING_UNPROVEN'):
        provenance.promote(payload, root=root, owner_uid=os.getuid())
    assert path.read_bytes() == before


def test_crash_before_replace_leaves_original_pair_and_removes_temporary(pair, monkeypatch):
    root, path, payload = pair
    before = path.read_bytes()
    monkeypatch.setattr(provenance.os, 'replace', lambda *_args, **_kw: (_ for _ in ()).throw(OSError('interrupted')))
    with pytest.raises(OSError):
        provenance.promote(payload, root=root, owner_uid=os.getuid())
    assert path.read_bytes() == before and not list(path.parent.glob('.provenance-*'))


@pytest.mark.parametrize('ready_marker', [True, False])
def test_replay_completes_directory_fsync_after_replace_succeeded(pair, monkeypatch, ready_marker):
    root, path, payload = pair
    if not ready_marker:
        value = json.loads(path.read_text())
        value.pop('installationState')
        path.write_text(json.dumps(value))
    real_fsync = provenance.os.fsync
    directory_calls = []

    def interrupted_fsync(descriptor):
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            directory_calls.append(descriptor)
            raise OSError('interrupted directory fsync')
        return real_fsync(descriptor)

    monkeypatch.setattr(provenance.os, 'fsync', interrupted_fsync)
    with pytest.raises(OSError, match='interrupted directory fsync'):
        provenance.promote(payload, root=root, owner_uid=os.getuid())
    assert len(directory_calls) == 1
    assert json.loads(path.read_text())['gitConfigReceipt'] == payload['receipt']
    inode = path.stat().st_ino

    def replay_fsync(descriptor):
        assert stat.S_ISDIR(os.fstat(descriptor).st_mode)
        directory_calls.append(descriptor)
        return real_fsync(descriptor)

    monkeypatch.setattr(provenance.os, 'fsync', replay_fsync)
    provenance.promote(payload, root=root, owner_uid=os.getuid())
    assert len(directory_calls) == 2 and path.stat().st_ino == inode
    assert ('installationState' in json.loads(path.read_text())) == ready_marker


@pytest.mark.parametrize('state', [None, {}, {'schemaVersion': True, 'stage': 'ready'},
                                  {'schemaVersion': 1, 'stage': 'fresh-incomplete'},
                                  {'schemaVersion': 1, 'stage': 'ready', 'pairSha256': '0' * 64}])
def test_present_unproven_state_is_not_treated_as_absent_for_nomination(pair, state):
    from intent_install import provenance_equivalent
    _root, _path, payload = pair
    report = {'blockers': [], 'configuration': {'status': 'equivalent'}, 'installed': {
        'gitConfigReceipt': payload['previous'], 'installationState': state}}
    assert not provenance_equivalent(report, payload['receipt'])


@pytest.mark.parametrize('invalid', [True, 1.0, '1', 0, -1])
def test_repository_identity_is_typed_even_when_python_numeric_equality_matches(pair, invalid):
    from intent_install import provenance_equivalent
    root, path, payload = pair
    payload['previous']['product_repository_id'] = invalid
    report = {'blockers': [], 'configuration': {'status': 'equivalent'}, 'installed': {
        'gitConfigReceipt': payload['previous'], 'installationState': {
            'schemaVersion': 1, 'stage': 'ready', 'pairSha256': pair_digest(payload['previous'])}}}
    assert not provenance_equivalent(report, payload['receipt'])
    before = path.read_bytes()
    with pytest.raises(ValueError, match='PROVENANCE_BINDING_UNPROVEN'):
        provenance.promote(payload, root=root, owner_uid=os.getuid())
    assert path.read_bytes() == before


def adoption_module(capture):
    import process_adoption
    return {'identity': process_adoption.identity, 'protected': process_adoption.protected,
            'capture_inputs': capture}


@pytest.mark.skipif(os.geteuid() != 0, reason='real root-owned installed binding')
@pytest.mark.parametrize('active', [True, False])
@pytest.mark.parametrize('capability', ['ready', 'missing', 'stale-policy', 'stale-ca'])
def test_provenance_loaded_frontier_checks_bound_target_and_discards_private_proof(pair, monkeypatch, active, capability):
    root, path, payload = pair
    payload = {**payload, 'productionUnit': 'test-runner.service'}
    state = {'LoadState': 'loaded', 'ActiveState': 'active' if active else 'inactive',
             'SubState': 'running' if active else 'dead', 'MainPID': '123' if active else '0',
             'NeedDaemonReload': 'no'}
    monkeypatch.setattr(provenance.subprocess, 'run', lambda *_a, **_kw:
        subprocess.CompletedProcess([], 0, '\n'.join(f'{key}={value}' for key, value in state.items()).encode()))
    calls = []

    def capture(received):
        assert received['productionActive'] is active
        assert 'operation' not in received and 'admission' not in received
        calls.append('capture')
        if capability == 'missing':
            raise FileNotFoundError('private socket path')
        if capability.startswith('stale'):
            raise ValueError('private cached input mismatch')
        return {'private-proof-must-not-leave-target': 'synthetic'}

    original = path.read_bytes()
    result = provenance.loaded_ready_target(payload, adoption_module(capture), root=root)
    assert result == ('PROVENANCE_LOADED_READY' if capability == 'ready' else 'PROVENANCE_LOADED_UNAVAILABLE')
    assert calls == ['capture'] and path.read_bytes() == original


@pytest.mark.skipif(os.geteuid() != 0, reason='real root-owned installed binding')
@pytest.mark.parametrize('changed', ['manifest', 'current', 'source'])
@pytest.mark.parametrize('capability', ['ready', 'missing'])
def test_loaded_frontier_target_movement_is_a_boundary_even_if_capability_unavailable(pair, monkeypatch, changed, capability):
    root, path, payload = pair
    payload = {**payload, 'productionUnit': 'test-runner.service'}
    state = b'LoadState=loaded\nActiveState=inactive\nSubState=dead\nMainPID=0\nNeedDaemonReload=no\n'
    monkeypatch.setattr(provenance.subprocess, 'run', lambda *_a, **_kw: subprocess.CompletedProcess([], 0, state))

    def capture(_received):
        if changed == 'manifest':
            value = json.loads(path.read_text()); value['consumerRevision'] = '0' * 40
            path.write_text(json.dumps(value))
        elif changed == 'current':
            link = root / 'opt/test/current'; link.unlink(); link.symlink_to(path.parent / 'foreign')
        else:
            (path.parent / 'reviewed-source/.relay-source.json').write_text('{}')
        if capability == 'missing':
            raise FileNotFoundError('missing capability')

    with pytest.raises((ValueError, OSError)):
        provenance.loaded_ready_target(payload, adoption_module(capture), root=root)


class LiveGuard:
    lost = False
    def poll(self):
        return 1 if self.lost else None


@pytest.mark.parametrize(('output', 'expected'), [
    ('PROVENANCE_LOADED_READY', True), ('PROVENANCE_LOADED_UNAVAILABLE', False),
    ('PROVENANCE_LOADED_BINDING_CHANGED', 'PROVENANCE_TARGET_BINDING_CHANGED'),
    ('private unexpected proof', 'PROVENANCE_LOADED_PROOF_UNPROVEN')])
@pytest.mark.parametrize('instance', [False, True])
def test_loaded_adapter_sends_only_fixed_component_payload_and_requires_exact_status(monkeypatch, output, expected, instance):
    import ansible_transport
    config = json.loads((Path(__file__).resolve().parents[2] / 'deploy/example.json').read_text())
    if instance:
        config['environment']['instance'] = {'reviewerPort': 18787, 'publicationEnabled': False}
    else:
        config['environment'].pop('instance', None)
    guard, pool_guard = LiveGuard(), LiveGuard()

    def target(target, key, argv, *, input, timeout):
        payload = json.loads(input)
        assert argv[:4] == ['/usr/bin/python3', '-I', '-B', '-c']
        assert '"__name__":"relay_provenance_loaded_inputs"' in argv[4]
        assert 'capture_inputs' in argv[4]
        assert timeout == 180
        assert payload['namespace'] == config['environment']['namespace']
        assert payload['productionRoot'] == '/opt/' + payload['namespace'] + '/runner'
        assert payload['reviewerUser'] == config['environment']['reviewerUser']
        assert payload['productionUser'] == config['environment']['runner']['user']
        assert payload['reviewerUnit'] == (payload['namespace'] + '-reviewer.service' if instance else 'reviewer-mcp.service')
        assert payload['productionUnit'] == (payload['namespace'] + '-runner.service' if instance else 'relay-runner.service')
        assert payload['environmentFiles'] == ['/etc/' + payload['namespace'] + suffix
            for suffix in ['/relay.env', '/reviewer-credentials/github-app.env']]
        assert set(payload) == {'namespace', 'revision', 'reviewerUnit', 'productionUnit', 'reviewerUser',
            'productionUser', 'productionRoot', 'socket', 'environmentFiles', 'config', 'release'}
        return subprocess.CompletedProcess(argv, 0, output, 'private diagnostics are not exposed')

    monkeypatch.setattr(ansible_transport, 'run_target', target)
    if isinstance(expected, bool):
        assert provenance.loaded_ready({}, None, config, 'a' * 40, guard, pool_guard) is expected
    else:
        with pytest.raises(ValueError, match=expected):
            provenance.loaded_ready({}, None, config, 'a' * 40, guard, pool_guard)


@pytest.mark.parametrize('when', ['before', 'after'])
@pytest.mark.parametrize('selected', ['host', 'pool'])
def test_loaded_adapter_lost_lock_stops_before_any_reconcile_fallback(monkeypatch, when, selected):
    import ansible_transport
    config = json.loads((Path(__file__).resolve().parents[2] / 'deploy/example.json').read_text())
    host, pool = LiveGuard(), LiveGuard()
    guard = host if selected == 'host' else pool
    if when == 'before':
        guard.lost = True
    calls = []
    def target(*_a, **_kw):
        calls.append('target')
        guard.lost = True
        return subprocess.CompletedProcess([], 0, 'PROVENANCE_LOADED_UNAVAILABLE')
    monkeypatch.setattr(ansible_transport, 'run_target', target)
    with pytest.raises(ValueError, match='HOST_LOCK_LOST'):
        provenance.loaded_ready({}, None, config, 'a' * 40, host, pool)
    assert calls == ([] if when == 'before' else ['target'])
