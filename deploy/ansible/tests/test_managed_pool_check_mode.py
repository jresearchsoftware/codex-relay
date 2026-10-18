"""Real Ansible member planning in a disposable filesystem; no services or API."""
import io
import os
from pathlib import Path
import pwd
import shutil
import stat
import subprocess
import tarfile

import pytest
import yaml

ANSIBLE = Path(__file__).resolve().parents[1]
MEMBER_TASKS = ANSIBLE / 'tasks/managed-pool-member.yml'
TEMPLATE = ANSIBLE / 'roles/relay_runner/templates/relay-managed-pool.service.j2'
VERSION = '2.336.0'

pytestmark = pytest.mark.skipif(os.name == 'nt' or not shutil.which('ansible-playbook'),
                                reason='native Linux Ansible required')


def snapshot(root):
    """Reads may change atime; retain identity, other metadata and all bytes."""
    result = {}
    for path in [root, *root.rglob('*')]:
        info = path.lstat()
        result[str(path.relative_to(root))] = (
            info.st_ino, info.st_mode, info.st_uid, info.st_gid, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            os.readlink(path) if path.is_symlink() else path.read_bytes() if path.is_file() else None,
        )
    return result


@pytest.fixture
def member(tmp_path):
    host = tmp_path / 'host'
    units = host / 'etc/systemd/system'
    units.mkdir(parents=True)
    # Existing SERIAL, Production, credentials and historical state are sentinels.
    for name in ['serial/.runner', 'serial/.credentials', 'production/run.sh',
                 'protected/attempts/original.json', 'protected/draft.json']:
        path = host / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('synthetic retained state\n')
        path.chmod(0o600)
    root = host / 'opt/pools/synthetic/runners/primary'
    state = host / 'var/lib/pools/synthetic/runners/primary'
    values = {
        'relay_general_runner_pool': {'name': 'synthetic', 'runnerUser': pwd.getpwuid(os.getuid()).pw_name},
        'relay_pool_member': {'id': 'primary', 'root': str(root), 'state': str(state),
                              'service': 'synthetic-pool-1.service'},
        'relay_pool_install_plan': {'members': {'primary': {
            'createDirectories': [str(path) for path in [root, state, state / 'home', state / 'work']],
            'installPackage': True, 'installUnit': True}}},
        'relay_runner_package_archive': str(tmp_path / 'pinned-runner.tar.gz'),
        'relay_runner_package_version': VERSION,
        'ansible_python_interpreter': '/usr/bin/python3',
        'ansible_remote_tmp': str(tmp_path / 'remote-tmp'),
    }
    tasks = yaml.safe_load(MEMBER_TASKS.read_text())
    # Only relocate the fixed unit destination/template and its root ownership.
    # All task ordering, conditions, modules and package verification stay real.
    unit = next(task['ansible.builtin.template'] for task in tasks if 'ansible.builtin.template' in task)
    unit.update(src=str(TEMPLATE), dest=str(units / 'synthetic-pool-1.service'),
                owner=os.getuid(), group=os.getgid())
    return host, root, state, values, tasks


def run_member(tmp_path, values, tasks, *, check=True):
    play = tmp_path / 'member.yml'
    play.write_text(yaml.safe_dump([{'hosts': 'localhost', 'connection': 'local',
        'gather_facts': False, 'vars': values, 'tasks': tasks}]))
    result = subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local',
        *(['--check'] if check else []), str(play)],
        env={**os.environ, 'ANSIBLE_NOCOLOR': '1', 'ANSIBLE_LOCAL_TEMP': str(tmp_path / 'local-tmp')},
        capture_output=True, text=True, timeout=90)
    return result.returncode, result.stdout + result.stderr


def package(values, *, version=VERSION, executable=True):
    """Synthetic verified input; a version probe would leave an observable write."""
    root = Path(values['relay_pool_member']['root'])
    with tarfile.open(values['relay_runner_package_archive'], 'w:gz') as archive:
        for name in ['config.sh', 'run.sh', 'bin/Runner.Listener']:
            entry = tarfile.TarInfo(name)
            entry.mode = 0o755 if executable else 0o644
            data = f'#!/bin/sh\ntouch "{root}/version-probed"\nprintf "%s\\n" "{version}"\n'.encode()
            entry.size = len(data)
            archive.addfile(entry, io.BytesIO(data))


@pytest.mark.parametrize('existing', ['absent', 'empty', 'complete', 'partial'])
def test_member_check_preserves_missing_roots_and_existing_installation(tmp_path, member, existing):
    host, root, state, values, tasks = member
    plan = values['relay_pool_install_plan']['members']['primary']
    if existing != 'absent':
        for path in [root, state, state / 'home', state / 'work']:
            path.mkdir(parents=True, mode=0o750)
        plan['createDirectories'] = []
        package(values)
    if existing in ['complete', 'partial']:
        with tarfile.open(values['relay_runner_package_archive']) as archive:
            archive.extractall(root)
        (root / '.runner').write_text('synthetic registration\n')
        (root / '.credentials').write_text('synthetic credential marker\n')
        plan['installPackage'] = existing == 'partial'
        if existing == 'partial':
            (root / 'config.sh').unlink()
        else:
            plan['installUnit'] = False
    before = snapshot(host)
    code, output = run_member(tmp_path, values, tasks)
    assert code == 0, output
    assert snapshot(host) == before
    if existing == 'complete':
        assert 'changed=0' in output
        assert 'MANAGED_POOL_CHECK_MODE_PACKAGE_PLAN=' not in output
    else:
        assert 'MANAGED_POOL_CHECK_MODE_PACKAGE_PLAN=extract_verify' in output
        assert 'changed=0' not in output
        if existing == 'absent':
            assert not root.exists() and not state.exists()
            assert not Path(values['relay_runner_package_archive']).exists()


@pytest.mark.parametrize('target', ['root', 'state'])
@pytest.mark.parametrize('kind', ['file', 'symlink'])
def test_member_check_still_rejects_unsafe_roots_without_mutation(tmp_path, member, target, kind):
    host, root, state, values, tasks = member
    path = root if target == 'root' else state
    path.parent.mkdir(parents=True)
    if kind == 'file':
        path.write_text('foreign object\n')
    else:
        path.symlink_to(host / 'protected', target_is_directory=True)
    before = snapshot(host)
    code, output = run_member(tmp_path, values, tasks)
    assert code != 0 and 'MANAGED_POOL_MEMBER_ROOT_UNSAFE' in output, output
    assert snapshot(host) == before


@pytest.mark.parametrize('damage', ['none', 'version', 'executable'])
def test_member_apply_still_extracts_and_verifies_package(tmp_path, member, damage):
    host, root, state, values, tasks = member
    retained = snapshot(host / 'protected')
    package(values, version='0.0.0' if damage == 'version' else VERSION,
            executable=damage != 'executable')
    code, output = run_member(tmp_path, values, tasks, check=False)
    assert snapshot(host / 'protected') == retained
    assert (root / 'bin/Runner.Listener').is_file()
    assert stat.S_IMODE(root.stat().st_mode) == 0o750
    assert 'MANAGED_POOL_CHECK_MODE_PACKAGE_PLAN=' not in output
    if damage == 'none':
        assert code == 0, output
        assert (root / 'version-probed').exists()
        assert (host / 'etc/systemd/system/synthetic-pool-1.service').is_file()
    else:
        assert code != 0, output
        assert not (host / 'etc/systemd/system/synthetic-pool-1.service').exists()
        if damage == 'executable':
            assert 'MANAGED_POOL_PACKAGE_UNPROVEN' in output
            assert not (root / 'version-probed').exists()
