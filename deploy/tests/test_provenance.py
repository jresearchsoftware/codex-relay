"""Real protected manifest promotion, failure atomicity and exact replay."""
import copy
import hashlib
import json
import os
from pathlib import Path
import stat
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
