"""Actual Git archive/role publication cannot grant a runner code replacement."""
import grp
import os
from pathlib import Path
import shutil
import stat
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(os.name != 'posix' or os.geteuid() != 0,
                                reason='native isolated root fixture with real cross-UID access required')


def run(argv, **kwargs):
    result = subprocess.run(argv, text=True, capture_output=True, **kwargs)
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def test_actual_archive_export_and_retained_repair_preserve_bytes_modes_and_symlink_targets(tmp_path):
    if not shutil.which('ansible-playbook'):
        pytest.skip('requires actual Ansible artifact tasks')
    for parent in [tmp_path, tmp_path.parent, tmp_path.parent.parent]:
        parent.chmod(0o755)
    repository = tmp_path / 'repository'
    repository.mkdir()
    outside = tmp_path / 'outside'
    outside.write_text('unrelated target\n')
    os.chown(outside, 65534, 65534)
    outside.chmod(0o660)
    payload = {'controller/src/codex-dispatch.mjs': ('dispatch fixture\n', 0o644),
               'controller/src/diagnostic-store.mjs': ('diagnostic fixture\n', 0o644),
               'bin/executable': ('#!/bin/sh\nexit 0\n', 0o755)}
    for name in ['owner_lifecycle.py', 'lifecycle.py', 'config.py', 'installed_config.py', 'deployment_lock.py']:
        payload['deploy/' + name] = ('# dependency fixture\n', 0o644)
    for name, (body, mode) in payload.items():
        path = repository / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
        path.chmod(mode)
    (repository / 'external-alias').symlink_to(outside)
    run(['git', 'init', '-q', str(repository)])
    run(['git', '-C', str(repository), 'add', '.'])
    tree = run(['git', '-C', str(repository), 'write-tree']).stdout.strip()
    archive = tmp_path / 'source.tar'
    run(['git', '-C', str(repository), 'archive', '--format=tar', '--output=' + str(archive), tree])
    release = tmp_path / 'release'
    source = release / 'reviewed-source'
    source.mkdir(parents=True)
    (release / 'bin').mkdir()
    role = ROOT / 'roles/relay_artifacts'
    stage_tasks = yaml.safe_load((role / 'tasks/stage-source.yml').read_text())
    main_tasks = yaml.safe_load((role / 'tasks/main.yml').read_text())
    values = dict(relay_install_root=str(tmp_path), relay_release_path=str(release), relay_source_archive=str(archive),
                  relay_source_identity={'revision': 'a' * 40}, relay_compatibility_links=[],
                  relay_group=grp.getgrgid(65534).gr_name,
                  relay_production_defer_lifecycle=True,
                  relay_runner_group=grp.getgrgid(65534).gr_name)
    def apply(tasks, retained):
        play = tmp_path / 'install.yml'
        play.write_text(yaml.safe_dump([{'hosts': 'localhost', 'gather_facts': False,
            'vars': {**values, 'relay_release_manifest': {'stat': {'exists': retained}}}, 'tasks': tasks,
            'handlers': yaml.safe_load((role / 'handlers/main.yml').read_text())}]))
        return run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(play)])
    # Use the actual source transport/extraction tasks to expose real Git modes.
    apply(stage_tasks[:3], False)
    target = source / 'controller/src/codex-dispatch.mjs'
    assert stat.S_IMODE(target.stat().st_mode) == 0o664
    assert stat.S_IMODE(target.parent.stat().st_mode) == 0o775
    # Retain the actual previous deployment's runner/service group exposure.
    os.chown(target, 0, 65534)
    os.chown(target.parent, 0, 65534)
    before = {p: (p.read_bytes(), p.stat().st_ino, p.stat().st_mode & 0o111, p.stat().st_gid)
              for p in (source / name for name in payload)}
    outside_before = outside.stat()
    links = [t for t in main_tasks if t.get('name') in [
        'Stage the exact reviewed on-demand Codex dispatch artifact',
        'Stage the exact reviewed diagnostics store artifact',
        'Activate only the reviewed release binding']]
    release_group = release.stat().st_gid
    # Keep stable routing targets in this small complete export fixture.
    tasks = [t for t in stage_tasks if t.get('name') != 'Install stable Relay routing and recovery invocation paths'] + links
    apply(tasks, True)
    assert 'changed=0' in apply(tasks, True).stdout
    for path, (body, inode, execute, group) in before.items():
        assert (path.read_bytes(), path.stat().st_ino, path.stat().st_mode & 0o111) == (body, inode, execute)
        assert path.stat().st_uid == 0 and not path.stat().st_mode & 0o022
        assert path.stat().st_gid == group
    for directory, _, _ in os.walk(source, followlinks=False):
        assert not Path(directory).stat().st_mode & 0o022
    assert (outside.stat().st_uid, outside.stat().st_gid, outside.stat().st_mode) == (
        outside_before.st_uid, outside_before.st_gid, outside_before.st_mode)
    assert (release / 'bin/relay-codex-dispatch.mjs').lstat().st_gid == 65534
    assert target.stat().st_gid == 65534  # link creation does not retarget ownership
    assert release.stat().st_gid == release_group
    def runner():
        os.setgroups([])
        os.setgid(65534)
        os.setuid(65534)
    for operation in ['-w', '-r']:
        result = subprocess.run(['/usr/bin/test', operation, str(target)], preexec_fn=runner)
        assert result.returncode == (1 if operation == '-w' else 0)
    assert subprocess.run(['/usr/bin/test', '-w', str(target.parent)], preexec_fn=runner).returncode == 1
    # Fresh installation uses the same normalization without a retained manifest.
    apply(tasks, False)
    assert not target.stat().st_mode & 0o022 and not target.parent.stat().st_mode & 0o022
