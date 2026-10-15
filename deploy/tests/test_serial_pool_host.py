"""Native synthetic ownership evidence and real idle-stop safeguards."""
import copy
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
import config
import managed_pool as pool
import serial_pool_host as adapter

pytestmark = pytest.mark.skipif(sys.platform != 'linux', reason='native Linux filesystem ownership')


class API:
    def __init__(self):
        self.rows = [{'id': 71, 'name': 'legacy-general', 'busy': False}]
        self.calls = []
        self.lost_delete = False

    def pages(self, path, field):
        self.calls.append(('GET', path))
        assert field == 'runners'
        return copy.deepcopy(self.rows)

    def request(self, method, path, body=None):
        self.calls.append((method, path))
        assert method == 'DELETE' and body is None
        self.rows = []
        if self.lost_delete:
            raise pool.PoolError('MANAGED_POOL_API_UNPROVEN_INSPECT_BEFORE_RETRY')
        return None


@pytest.fixture
def installation(tmp_path):
    value = config.load(ROOT / 'deploy/example.json', ROOT)
    value['environment']['instance'] = {'reviewerPort': 18787, 'publicationEnabled': False}
    value['environment']['generalRunner'].update(name='legacy-general', user='legacy-runner', scope='repository')
    ns = value['environment']['namespace']
    identity = SimpleNamespace(pw_uid=os.getuid() or 1001, pw_gid=os.getgid() or 1001)
    root = '/opt/' + ns + '/general-runner'
    state = '/var/lib/' + ns + '/general-runner'
    unit = '/etc/systemd/system/' + ns + '-general-runner.service'
    for logical in [root, state + '/work', state + '/home', '/etc/systemd/system']:
        (tmp_path / logical.lstrip('/')).mkdir(parents=True, exist_ok=True)
    mutable = [root, state + '/work', state + '/home']
    for logical in mutable:
        path = tmp_path / logical.lstrip('/')
        path.chmod(0o750)
        if os.getuid() == 0:
            os.chown(path, identity.pw_uid, identity.pw_gid)
    marker = {'agentId': 71, 'agentName': 'legacy-general',
              'gitHubUrl': 'https://github.com/' + value['consumer']['repository'], 'workFolder': state + '/work'}
    for name, raw in [('.runner', json.dumps(marker)), ('.credentials', 'synthetic private credentials')]:
        path = tmp_path / root.lstrip('/') / name
        path.write_text(raw)
        path.chmod(0o600)
        if os.getuid() == 0:
            os.chown(path, identity.pw_uid, identity.pw_gid)
    unit_path = tmp_path / unit.lstrip('/')
    unit_path.write_text('[Service]\nUser=legacy-runner\nGroup=legacy-runner\nWorkingDirectory=' + root + '\nExecStart=' + root + '/run.sh\n')
    unit_path.chmod(0o644)
    api = API()
    github = adapter.SerialPoolGitHub(api)
    native = object.__new__(pool.Host)
    native.contract = {'runnerUser': 'legacy-runner'}
    native.user = identity
    calls = []
    service = {'LoadState': 'loaded', 'ActiveState': 'inactive', 'MainPID': '0', 'ControlPID': '0',
               'ControlGroup': '', 'FragmentPath': unit}
    loaded = {'DropInPaths': '', 'NeedDaemonReload': 'no', 'User': 'legacy-runner', 'Group': 'legacy-runner', 'UnitFileState': 'disabled',
              'WorkingDirectory': root}
    native.service = lambda member: copy.deepcopy(service)
    def command(argv, **kwargs):
        calls.append(argv)
        if argv[1] == 'show':
            return '\n'.join(key + '=' + item for key, item in loaded.items())
        if argv[1] == 'freeze':
            (tmp_path / 'sys/fs/cgroup/system.slice' / (ns + '-general-runner.service') / 'cgroup.events').write_text('frozen 1\n')
        if argv[1] == 'disable':
            loaded['UnitFileState'] = 'disabled'
        if argv[1] == 'stop':
            service.update(ActiveState='inactive', MainPID='0', ControlGroup='')
            (tmp_path / 'sys/fs/cgroup/system.slice' / (ns + '-general-runner.service') / 'cgroup.procs').write_text('')
        return b''
    native.command = command
    host = adapter.SerialPoolHost(github, root=tmp_path, owner_uid=os.getuid(), identity=lambda user: identity,
                                  host_factory=lambda contract: native)
    return SimpleNamespace(config=value, root=tmp_path, runner_root=root, state=state, unit=unit,
                           marker=marker, identity=identity, api=api, github=github, host=host,
                           native=native, calls=calls, service=service, loaded=loaded)


def write_marker(value):
    path = value.root / value.runner_root.lstrip('/') / '.runner'
    path.write_text(json.dumps(value.marker))


def binding(value):
    return {key: item for key, item in value.host.inspect_legacy(value.config).items() if key != 'ownWorker'}


def activate(value, executable='Runner.Listener'):
    service_name = value.service['FragmentPath'].rsplit('/', 1)[-1]
    group = value.root / 'sys/fs/cgroup/system.slice' / service_name
    group.mkdir(parents=True)
    (group / 'cgroup.procs').write_text('8123\n')
    (group / 'cgroup.events').write_text('frozen 0\n')
    process = value.root / 'proc/8123'
    process.mkdir(parents=True)
    (process / 'cmdline').write_bytes((executable + '\0run\0').encode())
    payload = value.root / 'bin' / executable
    payload.parent.mkdir(exist_ok=True)
    payload.write_text('synthetic executable metadata')
    (process / 'exe').symlink_to(payload)
    value.service.update(ActiveState='active', MainPID='8123', ControlGroup='/system.slice/' + service_name)


@pytest.mark.parametrize('scope', ['repository', 'organization'])
def test_registered_owned_marker_uses_original_scope_and_preserves_private_credentials(installation, monkeypatch, scope):
    value = installation
    value.config['environment']['generalRunner'].update(scope=scope, group='trusted-general')
    if scope == 'organization':
        value.marker.update(gitHubUrl='https://github.com/' + value.config['consumer']['repository'].split('/')[0], poolName='trusted-general')
        write_marker(value)
    original = os.read
    def guarded_read(descriptor, size):
        assert not os.readlink('/proc/self/fd/' + str(descriptor)).endswith('/.credentials')
        return original(descriptor, size)
    monkeypatch.setattr(adapter.os, 'read', guarded_read)
    result = value.host.inspect_legacy(value.config)
    assert result['ownWorker'] is False and result['runnerId'] == 71
    assert result['runnerUid'] == value.identity.pw_uid
    assert value.github.observe_legacy(result) == {'id': 71, 'name': 'legacy-general', 'busy': False}
    prefix = '/repos/' + value.config['consumer']['repository'] if scope == 'repository' else '/orgs/' + result['organization']
    assert value.api.calls == [('GET', prefix + '/actions/runners')]
    assert len(result['registrationSha256']) == len(result['unitSha256']) == 64


@pytest.mark.parametrize('damage', ['name', 'url', 'work', 'id-bool', 'marker-mode', 'marker-symlink',
                                   'marker-hardlink', 'root-symlink', 'unit-user', 'unit-duplicate',
                                   'unit-mode', 'dropin', 'reload', 'fragment'])
def test_unsafe_or_mismatched_original_registration_unit_and_loaded_state_stop_before_mutation(installation, damage):
    value = installation
    marker = value.root / value.runner_root.lstrip('/') / '.runner'
    unit = value.root / value.unit.lstrip('/')
    if damage in ['name', 'url', 'work', 'id-bool']:
        field = {'name': 'agentName', 'url': 'gitHubUrl', 'work': 'workFolder', 'id-bool': 'agentId'}[damage]
        value.marker[field] = True if damage == 'id-bool' else 'foreign'
        write_marker(value)
    elif damage == 'marker-mode':
        marker.chmod(0o640)
    elif damage in ['marker-symlink', 'marker-hardlink']:
        other = marker.with_name('original-marker')
        marker.rename(other)
        marker.symlink_to(other) if damage == 'marker-symlink' else os.link(other, marker)
    elif damage == 'root-symlink':
        original = marker.parent
        other = original.with_name('other-root')
        original.rename(other)
        original.symlink_to(other)
    elif damage == 'unit-user':
        unit.write_text(unit.read_text().replace('User=legacy-runner', 'User=foreign'))
    elif damage == 'unit-duplicate':
        unit.write_text(unit.read_text() + 'ExecStart=/foreign\n')
    elif damage == 'unit-mode':
        unit.chmod(0o664)
    elif damage == 'dropin':
        value.loaded['DropInPaths'] = '/etc/systemd/system/override.conf'
    elif damage == 'reload':
        value.loaded['NeedDaemonReload'] = 'yes'
    else:
        value.service['FragmentPath'] = '/foreign.service'
    with pytest.raises((pool.PoolError, OSError)):
        value.host.inspect_legacy(value.config)
    assert not value.api.calls
    assert all(command[1] == 'show' for command in value.calls)


@pytest.mark.parametrize('rows', [[{'id': 71, 'name': 'foreign', 'busy': False}],
                                 [{'id': 72, 'name': 'legacy-general', 'busy': False}],
                                 [{'id': 71, 'name': 'legacy-general', 'busy': 'false'}],
                                 [{'id': 71, 'name': 'legacy-general', 'busy': False}] * 2])
def test_native_collision_rename_duplicate_and_unknown_busy_never_authorize_removal(installation, rows):
    value = installation
    saved = binding(value)
    value.api.rows = rows
    with pytest.raises(pool.PoolError):
        value.github.remove_legacy(saved)
    assert not any(method == 'DELETE' for method, path in value.api.calls)


def test_absent_or_busy_native_registration_never_authorizes_stop(installation):
    value = installation
    saved = binding(value)
    for rows in [[], [{'id': 71, 'name': 'legacy-general', 'busy': True}]]:
        value.api.rows = rows
        with pytest.raises(pool.PoolError, match='LEGACY_BUSY'):
            value.host.stop_legacy(saved)
    assert all(command[1] == 'show' for command in value.calls)


def test_real_idle_stop_freezes_before_signal_and_preserves_original_files(installation, monkeypatch):
    value = installation
    activate(value)
    saved = binding(value)
    original_path = pool.Path
    monkeypatch.setattr(pool, 'Path', lambda path: value.root / str(path).lstrip('/') if str(path).startswith(('/sys/', '/proc/')) else original_path(path))
    value.calls.clear()
    value.host.stop_legacy(saved)
    commands = [command[1] for command in value.calls if command[1] != 'show']
    assert commands == ['freeze', 'kill', 'disable', 'stop', 'thaw']
    assert value.host.legacy_stopped(saved) is True
    assert (value.root / value.runner_root.lstrip('/') / '.credentials').read_text() == 'synthetic private credentials'
    assert (value.root / value.unit.lstrip('/')).is_file()


def test_model_worker_prevents_any_stop_signal_even_when_native_runner_is_idle(installation, monkeypatch):
    value = installation
    saved = binding(value)
    activate(value, 'Runner.Worker')
    with pytest.raises(pool.PoolError, match='LEGACY_WORKER_PRESENT'):
        value.host.stop_legacy(saved)
    assert all(command[1] == 'show' for command in value.calls)


@pytest.mark.parametrize('enabled', ['enabled', 'enabled-runtime'])
def test_inactive_enabled_original_is_disabled_once_without_any_signal_or_local_file_change(installation, enabled):
    value = installation
    value.loaded['UnitFileState'] = enabled
    saved = binding(value)
    marker = value.root / value.runner_root.lstrip('/') / '.runner'
    credentials = marker.with_name('.credentials')
    before = marker.read_bytes(), credentials.read_bytes(), (value.root / value.unit.lstrip('/')).read_bytes()
    assert value.host.legacy_stopped(saved) is False
    value.host.stop_legacy(saved)
    assert value.host.legacy_stopped(saved) is True
    assert [command[1] for command in value.calls if command[1] != 'show'] == ['disable']
    value.host.stop_legacy(saved)
    assert [command[1] for command in value.calls if command[1] != 'show'] == ['disable']
    assert (marker.read_bytes(), credentials.read_bytes(), (value.root / value.unit.lstrip('/')).read_bytes()) == before


def test_restarted_legacy_listener_loses_stopped_proof_without_starting_any_pool(installation):
    value = installation
    saved = binding(value)
    assert value.host.legacy_stopped(saved) is True
    activate(value)
    assert value.host.legacy_stopped(saved) is False
    assert all(command[1] == 'show' for command in value.calls)


def test_failed_disable_acknowledgement_never_implies_stopped_or_sends_a_signal(installation):
    value = installation
    saved = binding(value)
    value.loaded['UnitFileState'] = 'enabled'
    command = value.native.command
    def lose_disable(argv, **kwargs):
        if argv[1] == 'disable':
            value.calls.append(argv)
            return b''  # No native state change despite a nominal success.
        return command(argv, **kwargs)
    value.native.command = lose_disable
    with pytest.raises(pool.PoolError, match='STOP_UNCERTAIN'):
        value.host.stop_legacy(saved)
    assert value.host.legacy_stopped(saved) is False
    assert [item[1] for item in value.calls if item[1] != 'show'] == ['disable']


def test_marker_replacement_after_binding_prevents_any_stop_or_signal(installation):
    value = installation
    saved = binding(value)
    value.marker['agentId'] = 72
    write_marker(value)
    with pytest.raises(pool.PoolError, match='LEGACY_BINDING_CHANGED'):
        value.host.stop_legacy(saved)
    assert all(command[1] == 'show' for command in value.calls)


def test_lost_delete_ack_is_reobserved_absent_without_another_remote_mutation_or_local_cleanup(installation):
    value = installation
    saved = binding(value)
    value.api.lost_delete = True
    with pytest.raises(pool.PoolError, match='API_UNPROVEN'):
        value.github.remove_legacy(saved)
    assert value.github.observe_legacy(saved) is None
    assert len([method for method, path in value.api.calls if method == 'DELETE']) == 1
    assert (value.root / value.runner_root.lstrip('/') / '.credentials').is_file()
    assert (value.root / value.runner_root.lstrip('/') / '.runner').is_file()


def test_target_readiness_requires_explicit_installed_proof_callback(installation):
    value = installation
    with pytest.raises(pool.PoolError, match='TARGET_READINESS_UNPROVEN'):
        value.host.pool_ready(value.config)
    value.host.readiness = lambda config: False
    assert value.host.pool_ready(value.config) is False
    value.host.readiness = lambda config: True
    assert value.host.pool_ready(value.config) is True
