from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import apt_preflight


@pytest.mark.parametrize('fail_at', [None, 0, 1])
def test_isolated_acquisition_preserves_live_lists_and_apt_integrity(tmp_path, fail_at):
    calls = []
    def runner(argv, **kwargs):
        calls.append(argv)
        assert kwargs['capture_output'] is True
        assert 'Acquire::AllowInsecureRepositories=false' in argv
        assert 'APT::Get::AllowUnauthenticated=false' in argv
        assert 'APT::Update::Error-Mode=any' in argv
        assert all('/var/lib/apt/lists' not in value for value in argv)
        return SimpleNamespace(returncode=1 if len(calls) - 1 == fail_at else 0)
    if fail_at is None:
        assert apt_preflight.verify(['python3', 'git'], runner=runner, parent=tmp_path)['status'] == 'PASS'
        assert calls[0][-1] == 'update'
        assert calls[1][-6:] == ['--download-only', '--no-upgrade', '--assume-yes', 'install', 'python3', 'git']
    else:
        with pytest.raises(ValueError, match='INTEGRITY_OR_ACQUISITION_UNPROVEN'):
            apt_preflight.verify(['python3'], runner=runner, parent=tmp_path)
        assert len(calls) == fail_at + 1
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('packages', [[], ['git;touch x'], ['--allow-unauthenticated'], ['../git'], 'git'])
def test_invalid_package_contract_cannot_reach_apt(packages, tmp_path):
    with pytest.raises(ValueError, match='PACKAGE_CONTRACT_INVALID'):
        apt_preflight.verify(packages, runner=lambda *_a, **_k: pytest.fail('unexpected APT'), parent=tmp_path)
