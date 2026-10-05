"""Archive-mode regressions; real root bootstrap proof needs native root CI."""
import ast
import copy
import grp
import os
from pathlib import Path
import pwd
import shutil
import stat
import subprocess
import tarfile
import tempfile

import pytest
import yaml

import installed_runtime_proof as proof

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
STAGE = ROOT / 'roles/relay_artifacts/tasks/stage-source.yml'
PARENTS = 'Protect owner lifecycle code substitution parents'
CLOSURE = 'Protect the fixed owner lifecycle Python dependency closure'


def archive(destination):
    subprocess.run(['git', '-C', str(REPO), '-c', 'tar.umask=0002', 'archive',
                    '--format=tar', '--output=' + str(destination), 'HEAD'], check=True)


def ansible(root, values, tasks, *, umask=0o077):
    playbook = root / 'install.yml'
    playbook.write_text(yaml.safe_dump([{'hosts': 'localhost', 'connection': 'local',
        'gather_facts': False, 'vars': values, 'tasks': tasks}]))
    environment = {**os.environ, 'ANSIBLE_NOCOLOR': '1', 'ANSIBLE_LOCALHOST_WARNING': 'False',
        'ANSIBLE_LOCAL_TEMP': str(root / 'local-tmp'), 'ANSIBLE_ROLES_PATH': str(ROOT / 'roles'),
        'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'}
    result = subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(playbook)],
                            env=environment, capture_output=True, text=True, timeout=90, umask=umask)
    assert result.returncode == 0, result.stdout + result.stderr
    return result, environment


def test_installed_normalization_matches_the_fixed_bootstrap_import_closure():
    template = (ROOT / 'roles/relay_runner/templates/relay-owner-lifecycle.j2').read_text()
    bootstrap = ast.parse(template.split("<<'PY'\n", 1)[1].split('\nPY\n', 1)[0])
    names = next(ast.literal_eval(node.iter) for node in ast.walk(bootstrap)
                 if isinstance(node, ast.For) and isinstance(node.target, ast.Name)
                 and node.target.id == 'name')
    # Only module-level imports execute before the protected coordinator can
    # acquire selected source. Its later workflow verifier comes from that source.
    modules, pending = set(), ['owner_lifecycle']
    while pending:
        name = pending.pop()
        if name in modules:
            continue
        modules.add(name)
        module = ast.parse((REPO / 'deploy' / (name + '.py')).read_text())
        for node in module.body:
            imports = ([node.module] if isinstance(node, ast.ImportFrom) else
                       [value.name for value in node.names] if isinstance(node, ast.Import) else [])
            pending.extend(imported for imported in imports
                           if (REPO / 'deploy' / (imported + '.py')).is_file())
    assert set(names) == {name + '.py' for name in modules}
    targets = proof.task(STAGE, CLOSURE)
    assert set(targets['loop']) == set(names)
    assert targets['ansible.builtin.file']['owner'] == 'root'
    assert targets['ansible.builtin.file']['group'] == 'root'


@pytest.mark.skipif(not shutil.which('ansible-playbook'), reason='Ansible required')
def test_unprivileged_archive_modes_are_repaired_without_changing_other_source(tmp_path):
    """Exercise actual mode tasks under our UID; this is not root trust proof."""
    source_archive = tmp_path / 'source.tar'
    archive(source_archive)
    release = tmp_path / 'release'
    source = release / 'reviewed-source'
    source.mkdir(parents=True)
    with tarfile.open(source_archive) as stream:
        # Only our own tracked Git object is extracted. Preserve its archive
        # modes as the production root unarchive does, even under umask 0077.
        stream.extractall(source)
    names = proof.task(STAGE, CLOSURE)['loop']
    assert stat.S_IMODE((source / 'deploy').stat().st_mode) == 0o775
    assert all(stat.S_IMODE((source / 'deploy' / name).stat().st_mode) == 0o664 for name in names)
    before = {path.relative_to(source): (path.lstat().st_mode, path.read_bytes()
              if path.is_file() else None) for path in source.rglob('*')}
    artifacts = ROOT / 'roles/relay_artifacts/tasks/main.yml'
    tasks = [copy.deepcopy(proof.task(artifacts,
             'Allow runtime traversal only to the reviewed release executable namespace')),
             *[copy.deepcopy(proof.task(STAGE, name)) for name in [PARENTS, CLOSURE]]]
    for entry in tasks:
        # Substitute only identity in this ordinary-UID test. Root ownership
        # and the unchanged fixed helper are exercised by the native proof.
        entry['ansible.builtin.file'].update(owner=pwd.getpwuid(os.getuid()).pw_name,
                                           group=grp.getgrgid(os.getgid()).gr_name)
    values = {'relay_release_path': str(release), 'relay_group': grp.getgrgid(os.getgid()).gr_name,
              'ansible_remote_tmp': str(tmp_path / 'remote-tmp')}
    ansible(tmp_path, values, tasks)
    allowed = {Path('deploy'), *[Path('deploy') / name for name in names]}
    for relative, (mode, content) in before.items():
        path = source / relative
        assert path.lstat().st_mode == (stat.S_IFDIR | 0o755 if relative == Path('deploy') else
            stat.S_IFREG | 0o644 if relative in allowed else mode), relative
        if content is not None:
            assert path.read_bytes() == content, relative
    assert stat.S_IMODE(source.stat().st_mode) == 0o751
    second, _ = ansible(tmp_path, values, tasks)
    assert 'changed=0' in second.stdout


@pytest.mark.skipif(os.geteuid() != 0 or not shutil.which('ansible-playbook'),
                    reason='native root filesystem and Ansible required')
def test_real_archive_install_reconcile_and_fixed_root_bootstrap():
    with tempfile.TemporaryDirectory(prefix='relay-owner-lifecycle-', dir='/run') as temporary:
        root = Path(temporary)
        source_archive = root / 'candidate.tar'
        archive(source_archive)
        head = subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip()
        install = root / 'relay'
        release = install / 'releases' / head
        source = release / 'reviewed-source'
        values = {'relay_install_root': str(install), 'relay_release_path': str(release),
            'relay_release_commit': head, 'relay_group': 'root', 'relay_compatibility_links': [],
            'relay_source_archive': str(source_archive), 'relay_source_identity': {'revision': head},
            'relay_release_manifest': {'stat': {'exists': False}},
            'ansible_remote_tmp': str(root / 'remote-tmp')}
        artifacts = ROOT / 'roles/relay_artifacts/tasks/main.yml'
        _, environment = ansible(root, values, [
            proof.task(artifacts, 'Allow runtime traversal only to the reviewed release executable namespace'),
            {'ansible.builtin.include_tasks': str(STAGE)},
        ])
        (install / 'current').symlink_to(release)
        proof.owner_lifecycle_trust_proof(root, values, environment, 0o077, source)
