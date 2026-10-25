"""Preserve only proven TEST qualification through verify/replay/resume."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
import config as configuration
import installed_config
from git_source_locator import expected_locator, resume_receipt

spec = importlib.util.spec_from_file_location('locator_backend', ROOT / 'deploy/relay-deploy.py')
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)

HEAD, CONFIG_HEAD, BLOB = 'a' * 40, 'b' * 40, 'c' * 40
SNAPSHOT_DIGEST = 'd' * 64


@pytest.fixture
def pair():
    config = {'source': {'repository': 'https://github.com/example/product.git', 'revision': HEAD},
              'consumer': {'owner': 'Owner'}, 'environment': {'localApply': {
                  'source': 'git', 'repository': 'example/private-config', 'configPath': 'test/relay.json'}}}
    raw = (json.dumps(config, indent=2) + '\n').encode()
    receipt = {'product_repository': 'example/product', 'product_sha': HEAD,
               'config_repository': 'example/private-config', 'config_path': 'test/relay.json',
               'config_sha': CONFIG_HEAD, 'config_blob_sha': BLOB,
               'config_sha256': hashlib.sha256(raw).hexdigest(),
               'source_policy': 'test-qualified-exact', 'workflow_run_id': 123, 'action': 'apply'}
    manifest = {'commit': HEAD, 'resolvedRevision': HEAD, 'installedRevision': HEAD,
                'deploymentConfigSha256': SNAPSHOT_DIGEST, 'gitConfigReceipt': copy.deepcopy(receipt)}
    return config, raw, receipt, manifest


def test_exact_test_evidence_preserves_pin_without_mutating_input_or_receipt(pair):
    config, raw, receipt, _ = pair
    before = copy.deepcopy((config, receipt))
    locator = expected_locator(config, HEAD, receipt, raw)
    assert locator == {'repository': 'example/private-config', 'configPath': 'test/relay.json',
                       'owner': 'Owner', 'productRepository': 'example/product', 'qualificationProductSha': HEAD}
    assert (config, receipt) == before


@pytest.mark.parametrize('receipt', [None, {}, {'source': 'owner-file'},
    {'source_policy': 'accepted-main'}, {'source_policy': 'accepted-ancestor'}])
def test_ordinary_sources_never_create_pin(pair, receipt):
    config, raw, _, _ = pair
    assert 'qualificationProductSha' not in expected_locator(config, HEAD, receipt, raw)
    config['environment']['localApply'] = {'source': 'installed'}
    assert expected_locator(config, HEAD, receipt, raw) == {}


@pytest.mark.parametrize('field,value', [
    ('product_sha', 'e' * 40), ('product_repository', 'example/other'),
    ('config_repository', 'example/other'), ('config_path', '../test/relay.json'),
    ('config_sha256', 'e' * 64), ('config_sha', 'main'), ('config_blob_sha', 'refs/pull/1/head')])
def test_wrong_receipt_binding_fails_without_disclosing_values(pair, field, value):
    config, raw, receipt, _ = pair
    receipt[field] = value
    with pytest.raises(ValueError, match='^git-source-locator-receipt-binding$'):
        expected_locator(config, HEAD, receipt, raw)


def test_changed_raw_bytes_revision_or_non_git_source_cannot_retain_pin(pair):
    config, raw, receipt, _ = pair
    for revision, content in [(HEAD, raw + b' '), ('f' * 40, raw), ('main', raw), (HEAD, None)]:
        with pytest.raises(ValueError, match='^git-source-locator-receipt-binding$'):
            expected_locator(config, revision, receipt, content)
    for source_revision in ['main', 'refs/pull/1/head', 'f' * 40]:
        config['source']['revision'] = source_revision
        with pytest.raises(ValueError, match='^git-source-locator-receipt-binding$'):
            expected_locator(config, HEAD, receipt, raw)
    config['environment']['localApply'] = {'source': 'installed'}
    with pytest.raises(ValueError, match='^git-source-locator-receipt-binding$'):
        expected_locator(config, HEAD, receipt, raw)


@pytest.mark.parametrize('placement', ['localApply', 'source', 'root'])
def test_git_input_cannot_introduce_qualification_or_receipt_policy(placement):
    config = json.loads((ROOT / 'deploy/example.json').read_text())
    config['environment']['localApply'] = {'source': 'git', 'repository': 'example/private-config',
                                         'configPath': 'test/relay.json'}
    target = {'localApply': config['environment']['localApply'], 'source': config['source'], 'root': config}[placement]
    target['qualificationProductSha' if placement == 'localApply' else 'source_policy'] = (
        HEAD if placement == 'localApply' else 'test-qualified-exact')
    with pytest.raises(configuration.InvalidConfig):
        configuration.loads(json.dumps(config), ROOT)


def test_resume_uses_original_pair_and_distinct_snapshot_and_git_hashes(pair):
    config, raw, receipt, manifest = pair
    assert SNAPSHOT_DIGEST != receipt['config_sha256']
    original = resume_receipt(config, HEAD, manifest, SNAPSHOT_DIGEST, raw)
    assert original == receipt and original is not receipt
    assert expected_locator(config, HEAD, original, raw)['qualificationProductSha'] == HEAD
    original['workflow_run_id'] = 999
    assert manifest['gitConfigReceipt']['workflow_run_id'] == 123


@pytest.mark.parametrize('change', ['head', 'snapshot', 'raw', 'receipt', 'policy'])
def test_resume_rejects_unbound_installed_evidence(pair, change):
    config, raw, receipt, manifest = pair
    if change == 'head':
        manifest['resolvedRevision'] = 'e' * 40
    elif change == 'snapshot':
        manifest['deploymentConfigSha256'] = 'e' * 64
    elif change == 'raw':
        raw += b' '
    elif change == 'receipt':
        manifest['gitConfigReceipt']['config_repository'] = 'example/other'
    else:
        manifest['gitConfigReceipt']['source_policy'] = 'unverified'
    with pytest.raises(ValueError, match='^git-source-locator-receipt-binding$'):
        resume_receipt(config, HEAD, manifest, SNAPSHOT_DIGEST, raw)


def test_backend_reads_original_protected_manifest_only_after_installed_verification(pair, monkeypatch):
    config, raw, receipt, manifest = pair
    events = []
    source = Path('/opt/fixture/releases') / HEAD / 'reviewed-source'

    def verify(path, revision, **kwargs):
        assert path == source and revision == HEAD and kwargs == {'require_local_apply': False}
        events.append('verify')
        return copy.deepcopy(config), SNAPSHOT_DIGEST, 'e' * 40

    def read(path, modes):
        assert events == ['verify']
        assert path == source.parent / 'artifact-manifest.json' and modes == {0o640, 0o600}
        events.append('protected-manifest')
        return json.dumps(manifest).encode(), None

    monkeypatch.setattr(installed_config, 'verify', verify)
    monkeypatch.setattr(installed_config, 'read_protected', read)
    consumer, original = backend.resume_configuration(config, raw, HEAD, '/opt/fixture')
    assert consumer == 'e' * 40 and original == receipt
    assert events == ['verify', 'protected-manifest']


def test_backend_failed_verification_or_changed_installed_values_prevents_manifest_read(pair, monkeypatch):
    config, raw, _, _ = pair
    reads = []
    monkeypatch.setattr(installed_config, 'read_protected', lambda *args: reads.append(args))

    def blocked(*args, **kwargs):
        raise ValueError('installed-source-head')

    monkeypatch.setattr(installed_config, 'verify', blocked)
    with pytest.raises(ValueError, match='installed-source-head'):
        backend.resume_configuration(config, raw, HEAD, '/opt/fixture')
    monkeypatch.setattr(installed_config, 'verify', lambda *args, **kwargs: ({}, SNAPSHOT_DIGEST, 'e' * 40))
    with pytest.raises(configuration.InvalidConfig, match='git-resume-installed-config-binding'):
        backend.resume_configuration(config, raw, HEAD, '/opt/fixture')
    assert reads == []


def test_legacy_resume_keeps_existing_installed_policy_check_without_manifest_read(pair, monkeypatch):
    config, raw, _, _ = pair
    config['environment']['localApply'] = {'source': 'installed'}
    calls = []

    def verify(*args, **kwargs):
        calls.append(kwargs)
        return config, SNAPSHOT_DIGEST, 'e' * 40

    monkeypatch.setattr(installed_config, 'verify', verify)
    monkeypatch.setattr(installed_config, 'read_protected', lambda *args: pytest.fail('unexpected manifest read'))
    assert backend.resume_configuration(config, raw, HEAD, '/opt/fixture') == ('e' * 40, None)
    assert calls == [{}]


@pytest.mark.skipif(sys.platform != 'linux' or getattr(os, 'geteuid', lambda: 1)() != 0
                    or not shutil.which('ansible-playbook'), reason='native root localhost Ansible required')
@pytest.mark.parametrize('operation', ['no-op', 'replay', 'resume'])
def test_actual_locator_copy_check_mode_keeps_qualified_pair_unchanged(pair, tmp_path, operation):
    from ansible.plugins.filter.core import to_nice_json
    config, raw, receipt, manifest = pair
    actual = expected_locator(config, HEAD, receipt, raw)
    if operation == 'replay':
        receipt = {**receipt, 'workflow_run_id': 456}
    elif operation == 'resume':
        receipt = resume_receipt(config, HEAD, manifest, SNAPSHOT_DIGEST, raw)
    expected = expected_locator(config, HEAD, receipt, raw)
    target = tmp_path / 'deployment-source.json'
    target.write_text(to_nice_json(actual) + '\n')
    target.chmod(0o600)
    before = target.read_bytes()
    tasks = yaml.safe_load((ROOT / 'deploy/ansible/roles/relay_artifacts/tasks/installed-config.yml').read_text())
    task = next(t for t in tasks if t['name'] ==
                'Publish the protected Git source locator independently of installed desired values')
    play = tmp_path / 'play.yml'
    play.write_text(yaml.safe_dump([{'hosts': 'localhost', 'connection': 'local', 'gather_facts': False,
        'vars': {'relay_config_root': str(tmp_path), 'relay_deployment_source': expected,
                 'ansible_python_interpreter': '/usr/bin/python3', 'ansible_remote_tmp': str(tmp_path / 'remote')},
        'tasks': [task]}]))
    ansible_config = tmp_path / 'ansible.cfg'
    ansible_config.write_text('[defaults]\nretry_files_enabled=False\n')
    result = subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', '--check', str(play)],
        cwd=tmp_path, env={**os.environ, 'ANSIBLE_CONFIG': str(ansible_config), 'ANSIBLE_NOCOLOR': '1',
                          'ANSIBLE_LOCAL_TEMP': str(tmp_path / 'local'), 'HOME': str(tmp_path)},
        text=True, capture_output=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert re.search(r'localhost\s*:\s*ok=1\s+changed=0\s+unreachable=0\s+failed=0', result.stdout)
    assert target.read_bytes() == before
