"""Protected metadata failures retain inputs without weakening the proof."""
import os
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import source_upgrade_general as general


@pytest.mark.parametrize('kind', ['file', 'directory'])
def test_metadata_stop_keeps_original_expected_and_observed_bits(tmp_path, kind):
    target = tmp_path / kind
    if kind == 'file':
        target.write_text('fixture')
        target.chmod(0o660)
        read = general._file
    else:
        target.mkdir()
        target.chmod(0o770)
        read = general._directory
    with pytest.raises(ValueError, match='^SOURCE_UPGRADE_GENERAL_CHANGED$') as stopped:
        read(target, os.getuid())
    observation = stopped.value.observation
    assert observation['check'] == f'source-{kind}-metadata'
    assert observation['expected']['writeBits'] == 0
    assert observation['observed']['writeBits'] == 0o020
    assert observation['observed']['uid'] == os.getuid()
    assert str(target) not in str(observation)


def test_valid_protected_file_and_directory_still_yield_the_existing_proof(tmp_path):
    tmp_path.chmod(0o700)
    target = tmp_path / 'safe'
    target.write_text('fixture')
    target.chmod(0o600)
    assert len(general._file(target, os.getuid())['sha256']) == 64
    assert general._directory(tmp_path, os.getuid())['entries'] == ['safe']


def test_private_recovery_metadata_stop_identifies_the_original_group(tmp_path):
    import clean_reinstall
    tmp_path.chmod(0o700)
    target = tmp_path / 'private.json'
    target.write_text('{}')
    target.chmod(0o600)
    with pytest.raises(ValueError, match='^REINSTALL_RECOVERY_EVIDENCE_UNSAFE$') as stopped:
        clean_reinstall._recovery_bytes(target, tmp_path, os.getuid(), os.getgid() + 1, private=True)
    observation = stopped.value.observation
    assert observation['expected']['gid'] == os.getgid() + 1
    assert observation['observed']['gid'] == os.getgid()
    assert observation['observed']['mode'] == 0o600
    assert str(target) not in str(observation)


def test_pool_owner_rejection_keeps_numeric_original_observation(tmp_path):
    import pool_eligibility
    tmp_path.chmod(0o700)
    with pytest.raises(RuntimeError, match='^MANAGED_POOL_ELIGIBILITY_PARENT_UNSAFE$') as stopped:
        pool_eligibility._directory(tmp_path.stat(), os.getuid() + 1)
    assert stopped.value.observation['expected']['uid'] == os.getuid() + 1
    assert stopped.value.observation['observed']['uid'] == os.getuid()


def test_consumer_publication_owner_rejection_keeps_original_stat(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location('causal_publication', Path(__file__).parents[1] / 'ansible/scripts/publish_git_consumer.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    target = tmp_path / 'proof'
    target.write_text('fixture')
    target.chmod(0o600)
    with pytest.raises(module.ConsumerPublicationError, match='^CONSUMER_PUBLICATION_PATH_UNSAFE$') as stopped:
        module._protected(target, owner_uid=os.getuid() + 1, boundary=tmp_path)
    assert stopped.value.observation['expected']['uid'] == os.getuid() + 1
    assert stopped.value.observation['observed']['uid'] == os.getuid()
    assert str(target) not in str(stopped.value.observation)
