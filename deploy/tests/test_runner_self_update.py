"""Identity-bound stopped migration, filesystem safety and interruption recovery."""
import copy
import hashlib
import json
import os
from pathlib import Path
import pwd
import stat
import subprocess
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import runner_self_update as update


@pytest.fixture
def installation(tmp_path, monkeypatch):
    uid = os.getuid()
    user = pwd.getpwuid(uid).pw_name
    root = tmp_path / 'runner'
    root.mkdir(mode=0o750)
    value = {'agentId': 74, 'agentName': 'general-1', 'poolId': 7,
             'poolName': 'General', 'gitHubUrl': 'https://github.com/example-org',
             'workFolder': '/var/lib/example-general-1/work', 'disableUpdate': True,
             'serverUrl': 'https://runner.example.invalid/',
             'futureSetting': {'arbitrary': [1, 'preserve', False]}}
    for name in update.SETTINGS:
        (root / name).write_text(json.dumps(value))
        (root / name).chmod(0o600)
    for name in ['.credentials', '.credentials_rsaparams', '.credentials_migrated']:
        (root / name).write_bytes(b'opaque-private-fixture\x00bytes')
        (root / name).chmod(0o600)
    service = {'LoadState': 'loaded', 'ActiveState': 'inactive', 'SubState': 'dead',
               'MainPID': '0', 'ControlPID': '0', 'ControlGroup': '',
               'WorkingDirectory': str(root), 'User': user, 'Restart': 'on-failure'}
    calls = []

    def command(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout=''.join(f'{key}={val}\n'
                               for key, val in service.items()))

    monkeypatch.setattr(update, 'runner_uid', lambda actual: uid if actual == user else -1)
    monkeypatch.setattr(update.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(update.subprocess, 'run', command)
    # Unit fixtures own a native Linux directory. Real /proc matching is tested
    # separately without pretending a fake systemd unit controls this process.
    monkeypatch.setattr(update, 'assert_no_runner_processes', lambda root: None)
    return SimpleNamespace(root=root, user=user, uid=uid, value=value, state=service,
                           service='example-general-1.service', calls=calls,
                           process_check=update.assert_no_runner_processes)


def migrate(item):
    return update.migrate(str(item.root), item.service, item.user, 74, 'general-1')


def snapshots(root):
    return {path.name: (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_ino,
                        stat.S_IMODE(path.stat().st_mode), path.stat().st_uid,
                        path.stat().st_gid) for path in root.iterdir()}


def test_inspect_is_read_only_and_reports_migrated_preference(installation):
    item = installation
    before = snapshots(item.root)
    result = update.inspect(str(item.root), item.service, item.user)
    assert result['preferredSettings'] == '.runner_migrated'
    assert [entry['file'] for entry in result['settings']] == list(update.SETTINGS)
    assert result['settings'][0]['workFolder'] == item.value['workFolder']
    assert result['settings'][0]['poolName'] == 'General'
    assert snapshots(item.root) == before
    assert all(command[:2] == ['/usr/bin/systemctl', 'show'] for command in item.calls)


def test_enable_preserves_identity_fields_credentials_and_modes(installation):
    item = installation
    before = snapshots(item.root)
    result = migrate(item)
    assert result['changed'] == list(update.SETTINGS)
    for name in update.SETTINGS:
        assert json.loads((item.root / name).read_text()) == dict(item.value, disableUpdate=False)
        assert snapshots(item.root)[name][2:] == before[name][2:]
    for name in ['.credentials', '.credentials_rsaparams', '.credentials_migrated']:
        assert snapshots(item.root)[name] == before[name]
    after = snapshots(item.root)
    assert migrate(item)['changed'] == []
    assert snapshots(item.root) == after
    assert all(command[:2] == ['/usr/bin/systemctl', 'show'] for command in item.calls)


@pytest.mark.parametrize('state', [
    {'ActiveState': 'active'}, {'ActiveState': 'activating'}, {'MainPID': '123'},
    {'ControlPID': '123'}, {'ControlGroup': '/unexpected.slice/unit'},
    {'WorkingDirectory': '/another/runner'}, {'User': 'another-user'},
    {'LoadState': 'not-found'}, {'Restart': 'no'},
])
def test_refuses_running_or_unbound_service_before_writing(installation, state):
    item = installation
    before = snapshots(item.root)
    item.state.update(state)
    with pytest.raises(update.UpdateError):
        migrate(item)
    assert snapshots(item.root) == before


@pytest.mark.parametrize('change', [
    {'agentId': 75}, {'agentName': 'general-2'}, {'disableUpdate': 'false'},
    {'agentId': True}, {'gitHubUrl': 'https://github.com/another-org'},
    {'poolId': 8}, {'poolName': 'Production'}, {'workFolder': '/another/work'},
])
def test_all_files_are_validated_before_any_write(installation, change):
    item = installation
    (item.root / '.runner_migrated').write_text(json.dumps(dict(item.value, **change)))
    before = snapshots(item.root)
    with pytest.raises(update.UpdateError):
        migrate(item)
    assert snapshots(item.root) == before


def test_wrong_expected_identity_never_reconfigures(installation):
    item = installation
    before = snapshots(item.root)
    with pytest.raises(update.UpdateError, match='IDENTITY_MISMATCH'):
        update.migrate(str(item.root), item.service, item.user, 999, 'general-1')
    assert snapshots(item.root) == before


@pytest.mark.parametrize('name', update.SETTINGS)
def test_settings_symlink_and_hardlink_rejected(installation, name):
    item = installation
    outside = item.root.parent / 'outside'
    outside.write_text(json.dumps(item.value))
    outside.chmod(0o600)
    original = outside.read_bytes()
    (item.root / name).unlink()
    (item.root / name).symlink_to(outside)
    with pytest.raises(OSError):
        migrate(item)
    assert outside.read_bytes() == original
    (item.root / name).unlink()
    os.link(outside, item.root / name)
    with pytest.raises(update.UpdateError, match='SETTINGS_UNSAFE'):
        migrate(item)
    assert outside.read_bytes() == original


def test_ancestor_symlink_and_writable_root_rejected(installation):
    item = installation
    link = item.root.parent / 'alias'
    link.symlink_to(item.root.parent, target_is_directory=True)
    with pytest.raises(OSError):
        update.inspect(str(link / 'runner'), item.service, item.user)
    item.root.chmod(0o770)
    with pytest.raises(update.UpdateError, match='ROOT_UNSAFE'):
        migrate(item)


def test_duplicate_case_insensitive_settings_are_ambiguous(installation):
    item = installation
    (item.root / '.runner_migrated').write_text(
        '{"agentId":74,"agentName":"general-1","disableUpdate":true,"DisableUpdate":false}')
    before = snapshots(item.root)
    with pytest.raises(update.UpdateError, match='SETTINGS_DUPLICATE_KEY'):
        migrate(item)
    assert snapshots(item.root) == before


@pytest.mark.parametrize('key', [*update.PUBLIC_SETTINGS, 'disableUpdate'])
def test_lone_noncanonical_case_is_rejected(installation, key):
    item = installation
    value = dict(item.value)
    value[key[0].upper() + key[1:]] = value.pop(key)
    (item.root / '.runner_migrated').write_text(json.dumps(value))
    before = snapshots(item.root)
    with pytest.raises(update.UpdateError, match='SETTINGS_NONCANONICAL_KEY'):
        migrate(item)
    assert snapshots(item.root) == before


def test_migrated_transport_url_can_differ(installation):
    item = installation
    value = dict(item.value, serverUrl='https://broker.example.invalid/', useV2Flow=True)
    (item.root / '.runner_migrated').write_text(json.dumps(value))
    migrate(item)
    assert json.loads((item.root / '.runner_migrated').read_text()) == dict(value, disableUpdate=False)


def test_legacy_single_file_and_missing_flag_are_supported(installation):
    item = installation
    (item.root / '.runner_migrated').unlink()
    assert migrate(item)['changed'] == ['.runner']
    value = copy.deepcopy(item.value)
    del value['disableUpdate']
    (item.root / '.runner').write_text(json.dumps(value))
    before = snapshots(item.root)
    assert migrate(item)['changed'] == []
    assert snapshots(item.root) == before


def test_interrupted_between_replacements_resumes_without_credentials(installation, monkeypatch):
    item = installation
    before = snapshots(item.root)
    replace = update.os.replace
    calls = []

    def interrupted(source, target, **kwargs):
        calls.append(target)
        if len(calls) == 2:
            raise OSError('synthetic interruption')
        return replace(source, target, **kwargs)

    monkeypatch.setattr(update.os, 'replace', interrupted)
    with pytest.raises(OSError):
        migrate(item)
    assert json.loads((item.root / '.runner').read_text())['disableUpdate'] is False
    assert json.loads((item.root / '.runner_migrated').read_text())['disableUpdate'] is True
    assert sorted(path.name for path in item.root.iterdir()) == sorted(before)
    monkeypatch.setattr(update.os, 'replace', replace)
    assert migrate(item)['changed'] == ['.runner_migrated']
    assert migrate(item)['changed'] == []
    for name in ['.credentials', '.credentials_rsaparams', '.credentials_migrated']:
        assert snapshots(item.root)[name] == before[name]


def test_running_service_recheck_prevents_second_write(installation, monkeypatch):
    item = installation
    replacement = update.replace_settings

    def starts_after_first(directory, entry):
        replacement(directory, entry)
        item.state['MainPID'] = '123'

    monkeypatch.setattr(update, 'replace_settings', starts_after_first)
    with pytest.raises(update.UpdateError, match='STOP_REQUIRED'):
        migrate(item)
    assert json.loads((item.root / '.runner_migrated').read_text())['disableUpdate'] is True


def test_migrate_requires_root(installation, monkeypatch):
    monkeypatch.setattr(update.os, 'geteuid', lambda: 1000)
    with pytest.raises(update.UpdateError, match='ROOT_REQUIRED'):
        migrate(installation)


def test_cli_requires_expected_identity_and_hides_malformed_settings(installation, capsys):
    item = installation
    arguments = ['migrate', '--root', str(item.root), '--service', item.service, '--user', item.user]
    with pytest.raises(SystemExit) as result:
        update.main(arguments)
    assert result.value.code == 2
    capsys.readouterr()
    (item.root / '.runner').write_text('private malformed fixture')
    assert update.main(arguments + ['--agent-id', '74', '--agent-name', 'general-1']) == 1
    output = capsys.readouterr()
    assert 'private malformed fixture' not in output.err + output.out
    assert 'UNPROVEN' in output.err


def test_process_matching_is_per_root_and_catches_external_launcher(tmp_path, monkeypatch):
    root = tmp_path / 'runner'
    root.mkdir()
    # Real Linux /proc is used here. The child has this root as cwd but its
    # executable is outside it; another runner's UID is deliberately irrelevant.
    child = subprocess.Popen(['/bin/sleep', '30'], cwd=root)
    iterate = Path.iterdir
    monkeypatch.setattr(Path, 'iterdir', lambda path: iter([Path('/proc') / str(child.pid)])
                        if path == Path('/proc') else iterate(path))
    try:
        with pytest.raises(update.UpdateError, match='PROCESS_PRESENT'):
            update.assert_no_runner_processes(str(root))
        update.assert_no_runner_processes(str(tmp_path / 'different-runner'))
    finally:
        child.terminate()
        child.wait(timeout=5)
