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
