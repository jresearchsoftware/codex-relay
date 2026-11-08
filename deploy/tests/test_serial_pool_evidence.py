"""Native read-only seals for completed cutovers; no migration engine."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
import managed_pool
import serial_pool_installation as installation
from serial_pool_transition import ProtectedFiles, encoded


@pytest.fixture
def sealed(tmp_path, monkeypatch):
    namespace, revision = 'relay-retained-fixture', '1' * 40
    release = '/opt/' + namespace + '/serial-compat-v1/' + revision
    source = release + '/reviewed-source'
    claim = '/var/lib/' + namespace + '/claims'
    config_root = '/etc/' + namespace
    files = ProtectedFiles(tmp_path, os.getuid())

    def write(logical, value, mode=0o600):
        path = tmp_path / logical.lstrip('/')
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = value if isinstance(value, bytes) else encoded(value) + b'\n'
        path.write_bytes(raw)
        path.chmod(mode)
        return raw

    original = {'consumer': {'repository': 'example/consumer', 'paths': {'claimRoot': claim}},
                'environment': {'namespace': namespace, 'generalRunner': {'user': 'nobody'}}}
    config_raw = write(release + '/deployment-config.json', original)
    write(source + '/.relay-source.json', {'revision': revision, 'tree': 'f' * 40}, 0o644)
    write(source + '/controller/reader.mjs', b'// retained original reader\n', 0o644)
    manifest_raw = write(release + '/artifact-manifest.json', {
        'commit': revision, 'installedRevision': revision, 'resolvedRevision': revision,
        'gitTree': 'f' * 40, 'deploymentConfigSha256': hashlib.sha256(config_raw).hexdigest()})
    consumer_raw = write(config_root + '/serial-consumer-v1.json', original['consumer'], 0o644)
    gate_raw = write(claim + '/admission-v1.json', {'phase': 'applying', 'original': True})
    retained = {'revision': revision, 'sourceRoot': source,
                'configPath': release + '/deployment-config.json',
                'manifestPath': release + '/artifact-manifest.json',
                'consumerPath': config_root + '/serial-consumer-v1.json',
                'sourceTreeSha256': files.tree_sha256(source),
                'configSha256': hashlib.sha256(config_raw).hexdigest(),
                'manifestSha256': hashlib.sha256(manifest_raw).hexdigest(),
                'consumerSha256': hashlib.sha256(consumer_raw).hexdigest()}
    receipt = {'version': 1, 'repository': 'example/consumer', 'namespace': namespace,
               'original': {**retained, 'gateSha256': hashlib.sha256(gate_raw).hexdigest()},
               'target': {'consumerDigest': 'b' * 64},
               'operationId': '12345678-1234-4234-8234-123456789abc'}
    receipt_raw = write(config_root + '/serial-pool-compat-v1.json', receipt, 0o644)
    state = {'phase': 'retired', 'operationId': receipt['operationId'],
             'plan': {key: copy.deepcopy(receipt[key]) for key in
                      ['version', 'repository', 'namespace', 'original', 'target']},
             'receiptSha256': hashlib.sha256(receipt_raw).hexdigest()}
    state['plan']['original'].pop('gateSha256')
    write(claim + '/serial-pool-transition-v1.json', state)
    calls = []

    def original_reader(*args, **kwargs):
        calls.append((args, kwargs))
        return {'consumerDigest': 'a' * 64, 'runs': []}

    monkeypatch.setattr(installation, 'ProtectedFiles', lambda: files)
    monkeypatch.setattr(installation, '_node', original_reader)
    return {'root': tmp_path, 'original': original, 'calls': calls, 'receipt': receipt,
            'source': source, 'claim': claim, 'configRoot': config_root, 'release': release}


def test_completed_cutover_is_read_without_publishing_or_rewriting_evidence(sealed):
    before = {str(path): path.read_bytes() for path in sealed['root'].rglob('*') if path.is_file()}
    original, evidence = installation.original_installation(sealed['original'])
    assert original == sealed['original']
    assert evidence['sourceRoot'] == sealed['source'] and evidence['runs'] == []
    assert len(sealed['calls']) == 1
    assert before == {str(path): path.read_bytes() for path in sealed['root'].rglob('*') if path.is_file()}
    assert not any(hasattr(ProtectedFiles, name) for name in ['write', 'directory', '_empty_copy', '_link_copy'])
    assert not any(hasattr(installation, name) for name in ['begin', 'finish', 'target_installed'])


@pytest.mark.parametrize('surface', ['source', 'config', 'manifest', 'consumer', 'gate', 'receipt'])
def test_changed_original_seal_blocks_before_any_original_code_executes(sealed, surface):
    paths = {'source': sealed['source'] + '/controller/reader.mjs',
             'config': sealed['release'] + '/deployment-config.json',
             'manifest': sealed['release'] + '/artifact-manifest.json',
             'consumer': sealed['configRoot'] + '/serial-consumer-v1.json',
             'gate': sealed['claim'] + '/admission-v1.json',
             'receipt': sealed['configRoot'] + '/serial-pool-compat-v1.json'}
    path = sealed['root'] / paths[surface].lstrip('/')
    path.write_bytes(path.read_bytes() + b'\n')
    with pytest.raises(managed_pool.PoolError):
        installation.original_installation(sealed['original'])
    assert not sealed['calls']


def test_unfinished_state_cannot_reactivate_the_original_reader(sealed):
    path = sealed['root'] / (sealed['claim'] + '/serial-pool-transition-v1.json').lstrip('/')
    value = json.loads(path.read_bytes())
    value['phase'] = 'reserved'
    path.write_bytes(encoded(value))
    with pytest.raises(managed_pool.PoolError, match='ORIGINAL_CONTEXT_CHANGED'):
        installation.original_installation(sealed['original'])
    assert not sealed['calls']
