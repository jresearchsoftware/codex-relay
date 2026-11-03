"""Keep bounded recovery compatible with the installed credential contract."""
import json
import os
from pathlib import Path
import pwd
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bounded_recovery as recovery


@pytest.fixture
def credentials(tmp_path):
    namespace = 'bounded-credential-fixture'
    config = {'environment': {'namespace': namespace, 'reviewerUser': pwd.getpwuid(os.geteuid()).pw_name},
              'consumer': {'paths': {}}}
    directory = tmp_path / 'etc' / namespace / 'reviewer-credentials'
    directory.mkdir(parents=True)
    path = directory / 'github-app.env'
    path.write_bytes(b'SYNTHETIC_NON_SECRET=fixture\n')
    return config, path


def test_existing_reviewer_group_read_contract_is_hash_bound(credentials, tmp_path):
    config, path = credentials
    path.chmod(0o640)
    first = recovery.credentials(config, tmp_path, os.geteuid())
    row = first[str(path.relative_to(tmp_path))]
    assert row['mode'] == 0o640 and row['gid'] == path.stat().st_gid
    assert 'SYNTHETIC_NON_SECRET' not in json.dumps(first)
    path.write_bytes(b'SYNTHETIC_NON_SECRET=changed\n')
    assert recovery.credentials(config, tmp_path, os.geteuid()) != first


@pytest.mark.parametrize('mode', [0o644, 0o660])
def test_reviewer_world_read_or_group_write_remains_untrusted(credentials, tmp_path, mode):
    config, path = credentials
    path.chmod(mode)
    with pytest.raises(ValueError, match='CREDENTIAL_UNSAFE'):
        recovery.credentials(config, tmp_path, os.geteuid())


def test_reviewer_exception_does_not_broaden_writer_credentials(credentials, tmp_path):
    config, path = credentials
    path.chmod(0o600)
    writer = path.parent.parent / 'writer-credentials'
    writer.mkdir()
    key = writer / 'github-app-private-key.pem'
    key.write_bytes(b'synthetic-key-fixture')
    key.chmod(0o640)
    with pytest.raises(ValueError, match='CREDENTIAL_UNSAFE'):
        recovery.credentials(config, tmp_path, os.geteuid())


@pytest.mark.skipif(os.geteuid() != 0, reason='wrong owning group fixture needs root')
def test_reviewer_group_read_requires_its_configured_group(credentials, tmp_path):
    config, path = credentials
    path.chmod(0o640)
    os.chown(path, os.geteuid(), path.stat().st_gid + 1)
    with pytest.raises(ValueError, match='CREDENTIAL_UNSAFE'):
        recovery.credentials(config, tmp_path, os.geteuid())
