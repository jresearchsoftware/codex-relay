"""Execute installed namespace tasks with the routing service's restrictive umask."""
import os
from pathlib import Path
import pwd
import grp
import stat
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
TASKS = ROOT / 'deploy/ansible/roles/relay_codex_runtime/tasks/repository-work-root.yml'

pytestmark = pytest.mark.skipif(sys.platform != 'linux', reason='native Linux directory modes')


def reconcile(tmp_path, work):
    play = [{'hosts': 'localhost', 'gather_facts': False, 'vars': {
        'relay_dispatch_work_root': str(work), 'relay_work_repository': 'example-org/project',
        'relay_dispatch_user': pwd.getpwuid(os.getuid()).pw_name,
        'relay_codex_work_group': grp.getgrgid(os.getgid()).gr_name,
    }, 'tasks': [{'ansible.builtin.include_tasks': str(TASKS)}]}]
    path = tmp_path / 'play.yml'
    path.write_text(yaml.safe_dump(play))
    return subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(path)],
                          capture_output=True, text=True,
                          env={**os.environ, 'ANSIBLE_NOCOLOR': '1'})


@pytest.mark.parametrize('slot', ['primary', 'second', 'pool-4'])
@pytest.mark.parametrize('existing', [False, True])
def test_install_and_upgrade_repair_only_repository_ancestors(tmp_path, slot, existing):
    work = tmp_path / slot / 'work'
    work.mkdir(parents=True, mode=0o2770)
    ancestors = [work / 'repositories', work / 'repositories/example-org',
                 work / 'repositories/example-org/project']
    retained = ancestors[-1] / 'run-1/private-evidence'
    if existing:
        previous = os.umask(0o077)
        try:
            retained.parent.mkdir(parents=True, mode=0o2770)
            retained.write_text('retained task bytes')
        finally:
            os.umask(previous)
        # This is the original failure: the recursive parents deny group traversal.
        assert all(stat.S_IMODE(path.stat().st_mode) & 0o070 == 0 for path in ancestors)
        before = retained.stat()
    result = reconcile(tmp_path, work)
    assert result.returncode == 0, result.stdout + result.stderr
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o2770 for path in ancestors)
    if existing:
        assert retained.stat() == before
        assert retained.read_text() == 'retained task bytes'
    result = reconcile(tmp_path, work)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'changed=0' in result.stdout


@pytest.mark.parametrize('depth', [0, 1, 2])
@pytest.mark.parametrize('alias', ['symlink', 'file'])
def test_repository_ancestor_aliases_fail_without_touching_target(tmp_path, depth, alias):
    work = tmp_path / 'work'
    target = tmp_path / 'foreign'
    target.mkdir(mode=0o700)
    before = target.stat()
    path = work.joinpath(*['repositories', 'example-org', 'project'][:depth + 1])
    path.parent.mkdir(parents=True)
    if alias == 'symlink':
        path.symlink_to(target, target_is_directory=True)
    else:
        path.write_text('not a directory')
    result = reconcile(tmp_path, work)
    assert result.returncode != 0
    assert ('CODEX_REPOSITORY_WORK_ROOT_UNSAFE' in result.stdout
            or (alias == 'file' and 'Not a directory' in result.stdout))
    assert 'changed=0' in result.stdout
    assert target.stat() == before
    assert list(target.iterdir()) == []


def test_every_slot_launcher_reconciliation_provisions_repository_roots():
    launcher = yaml.safe_load((TASKS.parent / 'launcher.yml').read_text())
    task, = [entry for entry in launcher if entry.get('ansible.builtin.include_tasks') == TASKS.name]
    assert task['loop'] == '{{ relay_github_repositories | default([]) }}'
    assert task['loop_control']['loop_var'] == 'relay_work_repository'
    slots = (ROOT / 'deploy/ansible/tasks/execution-slot.yml').read_text()
    assert 'tasks_from: launcher.yml' in slots
