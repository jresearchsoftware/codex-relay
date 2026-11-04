"""Native Linux runner software reconciliation without systemd or network effects."""
import grp
import hashlib
import io
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import tarfile
import tempfile

import pytest
import yaml


ANSIBLE = Path(__file__).resolve().parents[1]
ROLE = ANSIBLE / 'roles/relay_runner'
VERSION = '2.338.2'
pytestmark = pytest.mark.skipif(os.name == 'nt' or os.geteuid() != 0 or not shutil.which('ansible-playbook'),
                                reason='root native Linux Ansible required')


def listener(version):
    return ('#!/bin/sh\nmkdir -p "$(dirname "$0")/../_diag"\n'
            'id -u > "$(dirname "$0")/../_diag/probe-$$"\n'
            'printf "%s\\n" ' + repr(version) + '\n').encode()


@pytest.fixture
def host():
    user = pwd.getpwnam('nobody')
    group = grp.getgrgid(user.pw_gid).gr_name
    with tempfile.TemporaryDirectory(prefix='relay-native-software-', dir='/run') as temporary:
        base = Path(temporary); base.chmod(0o755)
        root = base / 'runner'; root.mkdir(mode=0o750)
        os.chown(root, user.pw_uid, user.pw_gid)
        frozen = base / 'frozen/runner-package'; frozen.mkdir(parents=True)
        archive = frozen / 'archive.tar.gz'
        with tarfile.open(archive, 'w:gz') as output:
            for name, content in {'config.sh': b'#!/bin/sh\nexit 0\n', 'run.sh': b'#!/bin/sh\nexit 0\n',
                                  'bin/Runner.Listener': listener(VERSION)}.items():
                member = tarfile.TarInfo(name); member.mode = 0o755; member.size = len(content)
                output.addfile(member, io.BytesIO(content))
        values = {'relay_runner_root': str(root), 'relay_runner_user': user.pw_name,
            'relay_runner_group': group, 'relay_runner_service_name': 'synthetic-native-runner.service',
            'relay_runner_registration_marker': str(root / '.runner'),
            'relay_runner_credentials_marker': str(root / '.credentials'),
            'relay_runner_package_archive': str(base / 'cache.tar.gz'),
            'relay_runner_package_version': VERSION, 'relay_runner_package_platform': 'linux-x64',
            'relay_runner_package_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
            'relay_runner_package_url': 'https://example.invalid/must-not-download',
            'relay_intent_stage_root': str(base / 'frozen'), 'relay_install_root': str(base),
            'ansible_python_interpreter': '/usr/bin/python3'}
        tasks = yaml.safe_load((ROLE / 'tasks/main.yml').read_text())
        start = next(index for index, task in enumerate(tasks) if task.get('name') ==
                     'Inspect runner root and registration markers before package reconciliation')
        end = next(index for index, task in enumerate(tasks) if task.get('name') ==
                   'Converge runner root metadata after package reconciliation')
        tasks = tasks[start:end]
        for task in tasks:
            if task.get('name') == 'Install runner archive safety validator':
                task['ansible.builtin.copy']['src'] = str(ROLE / 'files/relay-runner-archive-check.py')
            if task.get('name') == 'Inspect runner activity before replacing software files':
                task['ansible.builtin.command']['argv'] = ['/usr/bin/python3', '-c',
                    'from pathlib import Path; import sys; Path(' + repr(str(base / 'activity-probed')) +
                    ').write_text("probed"); print("' + 'inactive' + '"); sys.exit(3)']
        yield base, root, user, values, tasks


def install(host, version, *, registered=True, native_link=False):
    base, root, user, values, tasks = host
    binary = root / ('bin.' + version if native_link else 'bin')
    binary.mkdir()
    if native_link:
        (root / 'bin').symlink_to(binary, target_is_directory=True)
    for name, content in {'config.sh': b'#!/bin/sh\nexit 0\n', 'run.sh': b'#!/bin/sh\nexit 0\n',
                          str(binary.relative_to(root) / 'Runner.Listener'): listener(version)}.items():
        path = root / name; path.write_bytes(content); path.chmod(0o755)
        os.chown(path, user.pw_uid, user.pw_gid)
    for path in (binary, root / '_diag'):
        path.mkdir(mode=0o750, exist_ok=True); os.chown(path, user.pw_uid, user.pw_gid)
    if registered:
        (root / '.runner').write_text('synthetic registration identity')
        (root / '.credentials').write_text('synthetic credential reference')
    (root / 'current-job').write_text('synthetic running job: preserve bytes')


def software(root):
    return {str(path.relative_to(root)): (path.lstat().st_ino, path.lstat().st_mode,
            os.readlink(path) if path.is_symlink() else path.read_bytes())
            for path in root.rglob('*') if '_diag' not in path.relative_to(root).parts and
            (path.is_file() or path.is_symlink())}


def reconcile(host, *, check=False):
    base, root, user, values, tasks = host
    play = base / 'play.yml'
    play.write_text(yaml.safe_dump([{'hosts': 'localhost', 'connection': 'local', 'gather_facts': False, 'become': True,
        'vars': values, 'tasks': tasks}], sort_keys=False))
    return subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local',
        *(['--check'] if check else []), str(play)], capture_output=True, text=True, timeout=120,
        env={**os.environ, 'ANSIBLE_NOCOLOR': '1'})


@pytest.mark.parametrize('version,native_link', [('2.335.0', False), (VERSION, False), ('2.400.0', True)])
@pytest.mark.parametrize('check', [False, True])
def test_registered_native_version_never_requests_replacement_or_active_transition(host, version, native_link, check):
    install(host, version, native_link=native_link)
    base, root, user, values, tasks = host
    before = software(root)
    result = reconcile(host, check=check)
    assert result.returncode == 0, result.stdout + result.stderr
    assert software(root) == before
    assert not (base / 'activity-probed').exists()
    assert not Path(values['relay_runner_package_archive']).exists()
    assert 'RUNNER_NATIVE_SOFTWARE version=' + version in result.stdout
    assert 'health=version-probe-only' in result.stdout
    assert all(path.read_text().strip() == str(user.pw_uid) and path.stat().st_uid == user.pw_uid
               and path.stat().st_mode & 0o777 == 0o600 for path in (root / '_diag').iterdir())


@pytest.mark.parametrize('damage', ['malformed', 'failed', 'missing'])
def test_registered_corruption_requires_explicit_repair_without_replacing_software(host, damage):
    install(host, '2.400.0')
    base, root, user, values, tasks = host
    command = root / 'bin/Runner.Listener'
    if damage == 'missing':
        (root / 'config.sh').unlink()
    else:
        command.write_text('#!/bin/sh\n' + ('exit 7\n' if damage == 'failed' else 'echo 2.400.0-invalid\n'))
    before = software(root)
    result = reconcile(host)
    assert result.returncode != 0 and 'RUNNER_REGISTERED_PACKAGE_REPAIR_REQUIRED' in result.stdout
    assert software(root) == before
    assert not (base / 'activity-probed').exists()
    assert not Path(values['relay_runner_package_archive']).exists()


def test_fresh_bootstrap_extracts_verified_distribution_as_runner_and_checks_exact_version(host):
    base, root, user, values, tasks = host
    result = reconcile(host)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (base / 'activity-probed').exists()
    assert (root / 'bin/Runner.Listener').stat().st_uid == user.pw_uid
    assert 'RUNNER_NATIVE_SOFTWARE version=' + VERSION in result.stdout
    assert not (root / '.runner').exists() and not (root / '.credentials').exists()


@pytest.mark.parametrize('version', ['2.335.0', '2.400.0'])
def test_prepared_runnable_installation_is_preserved_without_a_version_floor(host, version):
    install(host, version, registered=False)
    base, root, user, values, tasks = host
    before = software(root)
    result = reconcile(host)
    assert result.returncode == 0, result.stdout + result.stderr
    assert software(root) == before and not (base / 'activity-probed').exists()
    assert not Path(values['relay_runner_package_archive']).exists()


@pytest.mark.parametrize('version,expected', [('2.335.0', 0), ('2.400.0', 0), ('2.400.0suffix', 2)])
def test_production_enable_validates_native_version_without_a_bootstrap_floor(host, version, expected):
    install(host, version)
    base, root, user, values, tasks = host
    production = yaml.safe_load((ANSIBLE / 'relay-production-runner-enable.yml').read_text())
    probe = next(task for task in production[0]['pre_tasks'] if task.get('name') ==
                 'Verify the installed production runner version without replacing software')
    tasks[:] = [probe]
    before = software(root)
    result = reconcile(host)
    assert result.returncode == expected, result.stdout + result.stderr
    assert software(root) == before and not (base / 'activity-probed').exists()


@pytest.mark.parametrize('name', ['bin', 'externals'])
@pytest.mark.parametrize('link_kind', ['escape', 'chained'])
def test_main_role_rejects_unsafe_native_directory_links_before_live_probe(host, name, link_kind):
    install(host, '2.400.0')
    base, root, user, values, tasks = host
    if (root / name).exists():
        (root / name).rename(root / (name + '.2.400.0'))
    else:
        (root / (name + '.2.400.0')).mkdir()
    if link_kind == 'escape':
        (root / name).symlink_to(base / (name + '.2.400.0'), target_is_directory=True)
    else:
        (root / (name + '.2.400.0')).rename(root / (name + '.2.400.1'))
        (root / (name + '.2.400.0')).symlink_to(name + '.2.400.1', target_is_directory=True)
        (root / name).symlink_to(name + '.2.400.0', target_is_directory=True)
    before = software(root)
    result = reconcile(host)
    assert result.returncode != 0 and 'RUNNER_NATIVE_LAYOUT_UNSAFE' in result.stdout + result.stderr
    assert software(root) == before
    assert not list((root / '_diag').iterdir())
