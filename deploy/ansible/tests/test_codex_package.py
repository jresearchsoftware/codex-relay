"""Native proofs of immutable full-package publication and UID accessibility."""
import importlib.util
import os
from pathlib import Path
import shutil
import stat
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('package_guard', ROOT / 'roles/relay_codex_runtime/files/relay-codex-package-guard.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
pytestmark = pytest.mark.skipif(os.name != 'posix' or os.geteuid() != 0,
                                reason='native isolated root fixture and cross-UID execution required')


@pytest.fixture
def package(tmp_path):
    # Pytest's root-owned ancestors also need search permission for the two
    # throwaway numeric identities; no host account/group is created.
    tmp_path.parent.chmod(0o755)
    tmp_path.parent.parent.chmod(0o755)
    tmp_path.chmod(0o755)
    runtime = tmp_path / 'codex-runtime'
    runtime.mkdir(mode=0o755)
    home = runtime / 'package-home'
    home.mkdir(mode=0o700)
    release = home / 'packages/standalone/releases/0.160.0-x86_64-unknown-linux-musl'
    (release / 'bin').mkdir(parents=True)
    binary = release / 'bin/codex'
    shutil.copyfile('/bin/echo', binary)
    binary.chmod(0o755)
    os.chown(binary, 65534, 65534)
    (release / 'codex-resources/voice').mkdir(parents=True)
    auxiliary = release / 'codex-resources/voice/manifest.json'
    auxiliary.write_text('{"fixture":"whole-release"}\n')
    os.chown(auxiliary, 65534, 65534)
    (release / 'codex-path').mkdir()
    (release / 'codex-path/rg').symlink_to('../bin/codex')
    (home / 'packages/standalone/current').symlink_to(release)
    (runtime / 'bin').mkdir()
    command = runtime / 'bin/codex'
    command.symlink_to(home / 'packages/standalone/current/bin/codex')
    return tmp_path, home, release, command, binary, auxiliary


def as_uid(uid, argv):
    def identity():
        os.setgroups([])
        os.setgid(uid)
        os.setuid(uid)
    return subprocess.run(argv, text=True, capture_output=True, preexec_fn=identity)


def test_whole_payload_normalized_and_executable_by_both_slots_without_private_home_access(package):
    root, home, release, command, binary, auxiliary = package
    private = root / 'primary-home'
    private.mkdir(mode=0o700)
    token = private / 'token'
    token.write_text('synthetic fixture only\n')
    token.chmod(0o600)
    os.chown(private, 65534, 65534)
    os.chown(token, 65534, 65534)
    before = {path: (path.read_bytes(), path.stat().st_ino) for path in [binary, auxiliary]}
    with pytest.raises(PermissionError):
        as_uid(65533, [str(command), '--version'])
    receipt = guard.qualify(home, command, '0.160.0', normalize=True)
    assert receipt['binary'] == str(binary)
    for directory, dirs, files in os.walk(home / 'packages'):
        for path in [Path(directory), *(Path(directory) / name for name in dirs + files)]:
            info = path.lstat()
            assert info.st_uid == info.st_gid == 0
            if not path.is_symlink():
                assert stat.S_IMODE(info.st_mode) in [0o644, 0o755]
    for path, original in before.items():
        assert (path.read_bytes(), path.stat().st_ino) == original
    for uid in [65534, 65533]:
        result = as_uid(uid, [str(command), '--version'])
        assert result.returncode == 0, result.stderr
        assert as_uid(uid, ['/usr/bin/test', '-w', str(auxiliary)]).returncode == 1
        assert as_uid(uid, ['/usr/bin/test', '-r', str(auxiliary)]).returncode == 0
    assert as_uid(65533, ['/usr/bin/test', '-r', str(token)]).returncode == 1
    assert stat.S_IMODE(private.stat().st_mode) == 0o700
    assert stat.S_IMODE(token.stat().st_mode) == 0o600
    guard.qualify(home, command, '0.160.0')


@pytest.mark.parametrize('escape', ['home-sibling', 'outside', 'hardlink'])
def test_unqualified_auxiliary_bytes_rejected_before_any_metadata_mutation(package, escape):
    root, home, release, command, binary, auxiliary = package
    before = binary.stat()
    target = (home if escape == 'home-sibling' else root) / 'unchecked'
    target.write_text('unqualified fixture\n')
    os.chown(target, 65534, 65534)
    if escape == 'hardlink':
        os.link(target, release / 'alias')
    else:
        (release / 'alias').symlink_to(target)
    with pytest.raises(ValueError, match='CODEX_PACKAGE_LINK_UNSAFE'):
        guard.qualify(home, command, '0.160.0', normalize=True)
    after = binary.stat()
    assert (before.st_uid, before.st_gid, before.st_mode) == (after.st_uid, after.st_gid, after.st_mode)
    assert stat.S_IMODE(home.stat().st_mode) == 0o700


def test_root_probes_reject_mutated_payload(package):
    _, home, _, command, binary, auxiliary = package
    guard.qualify(home, command, '0.160.0', normalize=True)
    os.chown(auxiliary, 65534, 65534)
    with pytest.raises(ValueError, match='CODEX_PACKAGE_LINK_UNSAFE'):
        guard.qualify(home, command, '0.160.0')


def test_source_runtime_reconciliation_preserves_arg0_alias_targets_on_repeated_apply(package):
    if not shutil.which('ansible-playbook'):
        pytest.skip('requires Ansible for source task execution')
    root, home, release, command, binary, auxiliary = package
    private = root / 'runtime-home'
    private.mkdir(mode=0o700)
    os.chown(private, 65534, 65534)
    outsider = root / 'other-private-home'
    outsider.mkdir(mode=0o700)
    os.chown(outsider, 65533, 65533)
    outside_file = outsider / 'retained'
    outside_file.write_text('unrelated private fixture bytes\n')
    outside_file.chmod(0o600)
    os.chown(outside_file, 65533, 65533)
    binary.write_text('''#!/bin/sh
set -eu
: "${HOME:?HOME is mandatory}"
: "${CODEX_HOME:?CODEX_HOME is mandatory}"
[ "$CODEX_HOME" = "$TASK_FIXTURE_HOME" ]
if [ "$(id -u)" = 0 ]; then [ "$HOME" = "$TASK_FIXTURE_HOME" ]; fi
arg0="$CODEX_HOME/tmp/arg0/fixture"
mkdir -p "$arg0"
for alias in apply_patch applypatch codex-execve-wrapper codex-linux-sandbox; do
    ln -sfn "$(readlink -f "$0")" "$arg0/$alias"
done
ln -sfn "$TASK_FIXTURE_OUTSIDE" "$arg0/other-private-home"
ln -sfn "$TASK_FIXTURE_OUTSIDE/retained" "$arg0/other-private-file"
printf 'codex-cli 0.160.0\\n'
''')
    binary.chmod(0o755)
    guard.qualify(home, command, '0.160.0', normalize=True)
    watched = [binary, auxiliary, outsider, outside_file]
    before = {path: (path.stat().st_uid, path.stat().st_gid, path.stat().st_mode,
                     path.stat().st_ino, path.read_bytes() if path.is_file() else None) for path in watched}
    role = ROOT / 'roles/relay_codex_runtime'
    source_tasks = yaml.safe_load((role / 'tasks/main.yml').read_text())
    names = ['Inspect the existing Codex binary before installation',
             'Verify existing managed package metadata before any root CLI version probe',
             'Inspect the existing Codex CLI version before installation',
             'Determine whether the pinned Codex CLI needs installation']
    tasks = [next(item for item in source_tasks if item['name'] == name) for name in names]
    tasks += [{'ansible.builtin.include_tasks': str(role / 'tasks/runtime-namespace.yml')},
              {'block': yaml.safe_load((role / 'tasks/package-access.yml').read_text())}]
    values = dict(relay_codex_binary_path=str(command), relay_codex_install_dir=str(command.parent),
                  relay_codex_package_home=str(home), relay_codex_package_install_dir=str(root / 'unused-staging'),
                  relay_codex_cli_version='0.160.0', relay_codex_user='nobody', relay_codex_group='nogroup',
                  relay_codex_home=str(private), role_path=str(role))
    environment = {'HOME': str(private), 'CODEX_HOME': str(private), 'TASK_FIXTURE_HOME': str(private),
                   'TASK_FIXTURE_OUTSIDE': str(outsider)}
    play = root / 'arg0-reconciliation.yml'
    play.write_text(yaml.safe_dump([{'hosts': 'localhost', 'gather_facts': False, 'vars': values,
                                   'environment': environment, 'tasks': tasks}]))
    for _ in range(2):
        result = subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(play)],
                                text=True, capture_output=True)
        assert result.returncode == 0, result.stdout + result.stderr
        assert {path: (path.stat().st_uid, path.stat().st_gid, path.stat().st_mode,
                       path.stat().st_ino, path.read_bytes() if path.is_file() else None)
                for path in watched} == before
        for path in [private, private / 'tmp', private / 'tmp/arg0', private / 'tmp/arg0/fixture']:
            assert path.stat().st_uid == path.stat().st_gid == 65534
        for path in [private, private / 'tmp', private / 'tmp/arg0']:
            assert stat.S_IMODE(path.stat().st_mode) == 0o700
        for alias in ['apply_patch', 'applypatch', 'codex-execve-wrapper', 'codex-linux-sandbox']:
            link = private / 'tmp/arg0/fixture' / alias
            assert link.is_symlink() and link.resolve() == binary
            assert link.lstat().st_uid == link.lstat().st_gid == 65534
        for alias, target in [('other-private-home', outsider), ('other-private-file', outside_file)]:
            link = private / 'tmp/arg0/fixture' / alias
            assert link.is_symlink() and link.resolve() == target
            assert link.lstat().st_uid == link.lstat().st_gid == 65534
        guard.qualify(home, command, '0.160.0')


@pytest.mark.parametrize('root_alias', ['tmp', 'arg0'])
def test_runtime_namespace_rejects_symlink_roots_before_target_mutation(package, root_alias):
    if not shutil.which('ansible-playbook'):
        pytest.skip('requires Ansible for source task execution')
    root, home, _, command, binary, auxiliary = package
    guard.qualify(home, command, '0.160.0', normalize=True)
    private = root / 'runtime-home'
    private.mkdir(mode=0o700)
    os.chown(private, 65534, 65534)
    outsider = root / 'other-private-home'
    outsider.mkdir(mode=0o700)
    os.chown(outsider, 65533, 65533)
    descendant = outsider / 'arg0'
    descendant.mkdir(mode=0o700)
    os.chown(descendant, 65533, 65533)
    retained = descendant / 'retained'
    retained.write_text('unrelated private fixture bytes\n')
    retained.chmod(0o600)
    os.chown(retained, 65533, 65533)
    if root_alias == 'tmp':
        (private / 'tmp').symlink_to(outsider)
    else:
        (private / 'tmp').mkdir(mode=0o700)
        os.chown(private / 'tmp', 65534, 65534)
        (private / 'tmp/arg0').symlink_to(outsider)
    watched = [binary, auxiliary, outsider, descendant, retained]
    before = {path: (path.stat().st_uid, path.stat().st_gid, path.stat().st_mode,
                     path.stat().st_ino, path.read_bytes() if path.is_file() else None) for path in watched}
    role = ROOT / 'roles/relay_codex_runtime'
    play = root / 'root-alias-reconciliation.yml'
    play.write_text(yaml.safe_dump([{'hosts': 'localhost', 'gather_facts': False,
                                   'vars': {'relay_codex_home': str(private), 'relay_codex_user': 'nobody',
                                            'relay_codex_group': 'nogroup'},
                                   'tasks': [{'ansible.builtin.include_tasks':
                                              str(role / 'tasks/runtime-namespace.yml')}]}]))
    result = subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(play)],
                            text=True, capture_output=True)
    assert result.returncode != 0, result.stdout + result.stderr
    assert {path: (path.stat().st_uid, path.stat().st_gid, path.stat().st_mode,
                   path.stat().st_ino, path.read_bytes() if path.is_file() else None)
            for path in watched} == before
    guard.qualify(home, command, '0.160.0')


def test_legacy_migration_uses_source_installer_tasks_and_never_executes_old_binary(tmp_path):
    if not shutil.which('ansible-playbook'):
        pytest.skip('requires Ansible for source task execution')
    runtime = tmp_path / 'codex-runtime'
    (runtime / 'bin').mkdir(parents=True)
    private = tmp_path / 'private-home'
    private.mkdir(mode=0o700)
    old = private / 'codex'
    marker = tmp_path / 'legacy-executed'
    old.write_text(f'#!/bin/sh\ntouch "{marker}"\nexit 1\n')
    old.chmod(0o755)
    os.chown(old, 65534, 65534)
    (runtime / 'bin/codex').symlink_to(old)
    installer = tmp_path / 'installer.sh'
    installer.write_text('''#!/bin/sh
set -eu
release="$CODEX_HOME/packages/standalone/releases/$2-x86_64-unknown-linux-musl"
mkdir -p "$release/bin"
printf '#!/bin/sh\\nprintf "codex-cli 0.160.0\\\\n"\\n' > "$release/bin/codex"
chmod 0755 "$release/bin/codex"
chown 65534:65534 "$release/bin/codex"
ln -s "$release/bin/codex" "$CODEX_INSTALL_DIR/codex"
printf 'Codex CLI fixture installed\\n'
''')
    role = ROOT / 'roles/relay_codex_runtime'
    source_tasks = yaml.safe_load((role / 'tasks/main.yml').read_text())
    names = ['Inspect the existing Codex binary before installation',
             'Verify existing managed package metadata before any root CLI version probe',
             'Inspect the existing Codex CLI version before installation',
             'Determine whether the pinned Codex CLI needs installation',
             'Create the private immutable package staging namespace before official installation',
             'Install the pinned official Codex CLI into the relay namespace']
    values = dict(relay_codex_binary_path=str(runtime / 'bin/codex'),
                  relay_codex_install_dir=str(runtime / 'bin'), relay_codex_package_home=str(runtime / 'package-home'),
                  relay_codex_package_install_dir=str(runtime / 'package-bin'), relay_codex_installer_path=str(installer),
                  relay_codex_cli_version='0.160.0', relay_codex_user='root', relay_codex_home=str(private), role_path=str(role))
    tasks = [next(item for item in source_tasks if item['name'] == name) for name in names]
    tasks += [{'block': yaml.safe_load((role / 'tasks/package-access.yml').read_text()),
               'when': 'not ansible_check_mode | bool'}]
    tasks += [next(item for item in source_tasks if item['name'] == 'Inspect the installed Codex binary without authentication'),
              next(item for item in source_tasks if item['name'] == 'Verify the pinned Codex CLI version')]
    play = tmp_path / 'migration.yml'
    play.write_text(yaml.safe_dump([{'hosts': 'localhost', 'gather_facts': False, 'vars': values, 'tasks': tasks}]))
    # Check-mode on the old link is a plan; even its final root version task
    # must not execute private, model-owned legacy distribution bytes.
    for flags in [['--check'], [], []]:
        result = subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(play), *flags],
                                text=True, capture_output=True)
        assert result.returncode == 0, result.stdout + result.stderr
        assert not marker.exists()
    resolved = (runtime / 'bin/codex').resolve()
    assert resolved.is_relative_to(runtime / 'package-home/packages')
    assert resolved.stat().st_uid == resolved.stat().st_gid == 0
    assert private.stat().st_mode & 0o777 == 0o700
