"""Keep bounded recovery compatible with the installed credential contract."""
import json
import grp
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


@pytest.fixture
def runtime_credentials(tmp_path):
    if os.geteuid() != 0:
        pytest.skip('distinct installed runtime credential ownership requires root')
    account = pwd.getpwnam('daemon')
    group = grp.getgrnam(account.pw_name)
    config = {'environment': {'namespace': 'bounded-runtime-fixture'},
              'consumer': {'runtimeUser': account.pw_name, 'paths': {}}}
    directory = tmp_path / 'etc/bounded-runtime-fixture/codex-credentials'
    directory.mkdir(parents=True)
    path = directory / 'access-token'
    path.write_bytes(b'synthetic-runtime-token')
    directory.chmod(0o700)
    path.chmod(0o600)
    os.chown(directory, account.pw_uid, group.gr_gid)
    os.chown(path, account.pw_uid, group.gr_gid)
    return config, path, account, group


def test_installed_runtime_owned_token_and_private_parent_are_hash_bound(runtime_credentials, tmp_path):
    config, path, account, group = runtime_credentials
    first = recovery.credentials(config, tmp_path, 0)
    row = first[str(path.relative_to(tmp_path))]
    assert (row['uid'], row['gid'], row['mode']) == (account.pw_uid, group.gr_gid, 0o600)
    path.write_bytes(b'synthetic-runtime-token-changed')
    assert recovery.credentials(config, tmp_path, 0) != first
    assert 'synthetic-runtime-token' not in json.dumps(first)


@pytest.mark.parametrize('damage', ['root-owner', 'wrong-group', 'group-read'])
def test_runtime_token_requires_its_exact_installed_identity(runtime_credentials, tmp_path, damage):
    config, path, account, group = runtime_credentials
    if damage == 'root-owner':
        os.chown(path, 0, group.gr_gid)
    elif damage == 'wrong-group':
        os.chown(path, account.pw_uid, 0)
    else:
        path.chmod(0o640)
    with pytest.raises(ValueError, match='CREDENTIAL_UNSAFE'):
        recovery.credentials(config, tmp_path, 0)


def test_runtime_ownership_does_not_grant_writer_credential_ownership(runtime_credentials, tmp_path):
    config, path, account, group = runtime_credentials
    writer = path.parent.parent / 'writer-credentials'
    writer.mkdir()
    key = writer / 'github-app-private-key.pem'
    key.write_bytes(b'synthetic-writer-fixture')
    key.chmod(0o600)
    os.chown(key, account.pw_uid, group.gr_gid)
    with pytest.raises(ValueError, match='CREDENTIAL_UNSAFE'):
        recovery.credentials(config, tmp_path, 0)


@pytest.mark.parametrize('scope', ['repository', 'slot', 'slot-repository'])
def test_configured_repository_and_slot_tokens_retain_their_own_identity(runtime_credentials, tmp_path, scope):
    config, primary, account, group = runtime_credentials
    secondary = pwd.getpwnam('bin')
    secondary_group = grp.getgrnam(secondary.pw_name)
    config['consumer']['repositoryRuntimeUsers'] = {'example/other': secondary.pw_name}
    config['consumer']['executionSlots'] = [{'id': 'pool-2', 'runtimeUser': account.pw_name}]
    base = primary.parent.parent
    relative = {'repository': 'runtime-users/bin/codex-credentials/access-token',
        'slot': 'slots/pool-2/codex-credentials/access-token',
        'slot-repository': 'slots/pool-2/runtime-users/bin/codex-credentials/access-token'}[scope]
    path = base / relative
    path.parent.mkdir(parents=True)
    path.parent.chmod(0o700)
    path.write_bytes(b'synthetic-secondary-token')
    path.chmod(0o600)
    if scope == 'slot':
        os.chown(path.parent, account.pw_uid, group.gr_gid)
        os.chown(path, account.pw_uid, group.gr_gid)
    else:
        os.chown(path.parent, secondary.pw_uid, secondary_group.gr_gid)
        os.chown(path, secondary.pw_uid, secondary_group.gr_gid)
    first = recovery.credentials(config, tmp_path, 0)
    assert str(path.relative_to(tmp_path)) in first and first[str(path.relative_to(tmp_path))] is not None
    path.write_bytes(b'synthetic-secondary-token-changed')
    assert recovery.credentials(config, tmp_path, 0) != first


@pytest.mark.parametrize('name', ['_worker', 'relay_worker', 'r' * 32])
def test_runtime_identity_uses_the_canonical_unix_name_contract(runtime_credentials, tmp_path, monkeypatch, name):
    config, _path, account, group = runtime_credentials
    user_lookup, group_lookup = pwd.getpwnam, grp.getgrnam
    monkeypatch.setattr(pwd, 'getpwnam', lambda value: account if value == name else user_lookup(value))
    monkeypatch.setattr(grp, 'getgrnam', lambda value: group if value == name else group_lookup(value))
    config['consumer']['runtimeUser'] = name
    assert recovery.credentials(config, tmp_path, 0)


def test_maximum_length_slot_uses_its_configured_runtime_identity(runtime_credentials, tmp_path):
    config, primary, account, group = runtime_credentials
    slot_id = 's' * 32
    config['consumer']['executionSlots'] = [{'id': slot_id, 'runtimeUser': account.pw_name}]
    token = primary.parent.parent / 'slots' / slot_id / 'codex-credentials/access-token'
    token.parent.mkdir(parents=True)
    token.parent.chmod(0o700)
    token.write_bytes(b'synthetic-slot-token')
    token.chmod(0o600)
    os.chown(token.parent, account.pw_uid, group.gr_gid)
    os.chown(token, account.pw_uid, group.gr_gid)
    assert recovery.credentials(config, tmp_path, 0)[str(token.relative_to(tmp_path))]['uid'] == account.pw_uid


@pytest.mark.parametrize('mode', [0o600, 0o640])
def test_configured_writer_path_never_acquires_reviewer_credential_permissions(runtime_credentials, tmp_path, mode):
    config, primary, account, group = runtime_credentials
    config['environment']['reviewerUser'] = account.pw_name
    token = primary.parent.parent / 'reviewer-credentials/github-app-private-key.pem'
    token.parent.mkdir()
    token.write_bytes(b'synthetic-writer-key-in-reviewer-directory')
    token.chmod(mode)
    os.chown(token, account.pw_uid, group.gr_gid)
    config['consumer']['paths']['credentialKeyFile'] = str(token)
    with pytest.raises(ValueError, match='CREDENTIAL_UNSAFE'):
        recovery.credentials(config, tmp_path, 0)
