"""Real root Linux package staging in isolated paths and loopback transport."""
import functools
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import threading

import pytest
import yaml


ANSIBLE = Path(__file__).resolve().parents[1]
HELPER = ANSIBLE / 'roles/relay_runner/files/relay-intent-package.py'
OPERATION = '12345678-1234-1234-1234-123456789abc'
pytestmark = pytest.mark.skipif(os.name == 'nt' or os.geteuid() != 0 or not shutil.which('ansible-playbook'),
                                reason='root native Linux Ansible required')


def snapshot(root):
    result = {}
    for path in [root, *root.rglob('*')]:
        info = path.lstat()
        result[str(path.relative_to(root))] = (info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            os.readlink(path) if path.is_symlink() else path.read_bytes() if path.is_file() else None)
    return result


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *arguments):
        pass


@pytest.fixture
def package_fixture():
    with tempfile.TemporaryDirectory(prefix='relay-intent-packages-', dir='/run') as temporary:
        root = Path(temporary); root.chmod(0o755)
        live = root / 'live'; live.mkdir(mode=0o755)
        stage = root / 'stage'; stage.mkdir(mode=0o700)
        public = root / 'http'; public.mkdir()
        roles = root / 'roles'
        for name in ('relay_runner', 'relay_codex_runtime'):
            shutil.copytree(ANSIBLE / 'roles' / name, roles / name)
        server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(QuietHandler, directory=str(public)))
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            yield {'root': root, 'live': live, 'stage': stage, 'public': public, 'roles': roles,
                   'url': 'http://127.0.0.1:' + str(server.server_port)}
        finally:
            server.shutdown(); thread.join(timeout=5); server.server_close()


def runner_package(f, *, malformed=False, version='2.336.0'):
    archive = f['public'] / 'runner.tar.gz'
    live = f['live'] / 'runner'; live.mkdir()
    with tarfile.open(archive, 'w:gz') as output:
        for name, content in {'config.sh': '#!/bin/sh\nexit 0\n', 'run.sh': '#!/bin/sh\nexit 0\n',
                              'bin/Runner.Listener': '#!/bin/sh\nprintf "%s\\n" ' + version + '\n',
                              'externals/node24/bin/node': '#!/bin/sh\nexit 0\n'}.items():
            path = live / name; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content); path.chmod(0o755)
            if malformed and name == 'config.sh':
                continue
            member = tarfile.TarInfo(name); member.mode = 0o755
            raw = content.encode(); member.size = len(raw); output.addfile(member, io.BytesIO(raw))
    # Existing history and credentials must survive every staging failure.
    (live / '.runner').write_text('{"agentName":"synthetic"}')
    (live / '.credentials').write_text('synthetic retained credential reference')
    (f['live'] / 'consumer.json').write_text('{"accepted":"old"}')
    values = {'relay_intent_stage_root': str(f['stage']), 'relay_intent_stage_operation': OPERATION,
        'relay_runner_package_version': '2.336.0', 'relay_runner_package_platform': 'linux-x64',
        'relay_runner_package_url': f['url'] + '/runner.tar.gz',
        'relay_runner_package_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
        'relay_runner_package_archive': str(f['live'] / 'archive.tar.gz'), 'relay_runner_root': str(live),
        'relay_runner_user': 'nobody', 'relay_runner_service_name': 'synthetic-runner.service'}
    return values


def codex_package(f, *, version='0.160.0', escaping=False, fail=False):
    installer = f['public'] / 'install.sh'
    installer.write_text('#!/bin/sh\nset -eu\n' + ('exit 7\n' if fail else '') +
        'test "$#" = 2 && test "$1" = --release && test "$2" = 0.160.0\n'
        'test -z "${RELAY_SYNTHETIC_SECRET:-}"\n'
        'release="$HOME/packages/standalone/releases/0.160.0-linux-x64/bin"\n'
        'mkdir -p "$release" "$CODEX_INSTALL_DIR"\n'
        'printf \'#!/bin/sh\\nprintf "codex-cli ' + version + '\\\\n"\\n\' > "$release/codex"\n'
        'chmod 755 "$release/codex"\n'
        'printf payload > "$release/auxiliary"\n'
        'ln -s ' + ('/etc/passwd' if escaping else '"$release/auxiliary"') + ' "$release/resource"\n'
        'ln -s "$release/codex" "$CODEX_INSTALL_DIR/codex"\n')
    (f['live'] / 'consumer.json').write_text('{"accepted":"old"}')
    return {'relay_intent_stage_root': str(f['stage']), 'relay_intent_stage_operation': OPERATION,
        'relay_codex_cli_version': '0.160.0', 'relay_codex_installer_url': f['url'] + '/install.sh',
        'relay_codex_package_home': str(f['live'] / 'package-home'),
        'relay_codex_package_install_dir': str(f['live'] / 'package-bin'),
        'relay_codex_binary_path': str(f['live'] / 'bin/codex'),
        'relay_codex_installer_path': str(f['live'] / 'installer.sh')}


def run_stage(f, kind, values):
    role = 'relay_runner' if kind == 'runner' else 'relay_codex_runtime'
    path = f['roles'] / role / 'tasks/intent-stage-package.yml'
    tasks = yaml.safe_load(path.read_text())
    # Replace only the public transport/pin with this loopback package fixture;
    # actual download/checksum/validator/extraction/guard/version tasks run intact.
    assertions = tasks[0]['ansible.builtin.assert']['that']
    for index, assertion in enumerate(assertions):
        if '_url ==' in assertion:
            name = 'relay_runner_package_url' if kind == 'runner' else 'relay_codex_installer_url'
            assertions[index] = name + ' == ' + repr(values[name])
        if '_sha256 ==' in assertion:
            assertions[index] = 'relay_runner_package_sha256 == ' + repr(values['relay_runner_package_sha256'])
    path.write_text(yaml.safe_dump(tasks, sort_keys=False))
    play = f['root'] / 'stage.yml'
    play.write_text(yaml.safe_dump([{'hosts': 'localhost', 'connection': 'local', 'gather_facts': False,
        'vars': {**values, 'ansible_python_interpreter': '/usr/bin/python3'},
        'tasks': [{'ansible.builtin.include_role': {'name': str(f['roles'] / role),
                                                  'tasks_from': 'intent-stage-package.yml'}}]}], sort_keys=False))
    return subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(play)],
        env={**os.environ, 'ANSIBLE_NOCOLOR': '1', 'RELAY_SYNTHETIC_SECRET': 'must-not-reach-installer'},
        capture_output=True, text=True, timeout=120)


def guard(f, kind, action, values, *, operation=OPERATION):
    version = values['relay_runner_package_version' if kind == 'runner' else 'relay_codex_cli_version']
    checksum = values['relay_runner_package_sha256'] if kind == 'runner' else '-'
    live = ({'root': values['relay_runner_root'], 'archive': values['relay_runner_package_archive'],
             'user': values['relay_runner_user'], 'service': values['relay_runner_service_name'], 'packageVersion': version}
            if kind == 'runner' else {'home': values['relay_codex_package_home'],
                'installDir': values['relay_codex_package_install_dir'], 'binary': values['relay_codex_binary_path'],
                'installer': values['relay_codex_installer_path']})
    return subprocess.run(['/usr/bin/python3', '-I', str(HELPER), action, kind, str(f['stage']), operation,
                           version, checksum], input=json.dumps(live), capture_output=True, text=True, timeout=90)


@pytest.mark.parametrize('failure', ['download', 'checksum', 'layout', 'version', 'permissions'])
def test_runner_stage_failure_preserves_every_live_byte(package_fixture, failure):
    f = package_fixture; values = runner_package(f, malformed=failure == 'layout',
                                                 version='2.335.0' if failure == 'version' else '2.336.0')
    if failure == 'download': values['relay_runner_package_url'] += '.missing'
    if failure == 'checksum': values['relay_runner_package_sha256'] = '0' * 64
    if failure == 'permissions':
        archive = Path(values['relay_runner_package_archive']); archive.write_text('retained unsafe cache'); archive.chmod(0o666)
    before = snapshot(f['live'])
    result = run_stage(f, 'runner', values)
    assert result.returncode != 0, result.stdout + result.stderr
    # Transport/archive failures precede live-version validation. Do not demand
    # a registered-runtime repair diagnostic for a missing or corrupt download.
    diagnostics = {'download': 'HTTP Error 404', 'checksum': 'did not match',
                   'layout': 'RUNNER_ARCHIVE_INVALID code=REQUIRED_ENTRYPOINT_MISSING'}
    if failure in diagnostics:
        assert diagnostics[failure] in result.stdout + result.stderr
    else:
        assert ('RUNNER_REGISTERED_PACKAGE_REPAIR_REQUIRED' in result.stdout + result.stderr or
                'INTENT_RUNNER_NATIVE_LAYOUT_UNSAFE_STOPPED_REPAIR_REQUIRED' in result.stdout + result.stderr)
    assert snapshot(f['live']) == before
    assert not (f['stage'] / 'runner-package/manifest.json').exists()


def test_runner_stage_seal_and_tamper_rejection_preserve_live_distribution(package_fixture):
    f = package_fixture; values = runner_package(f); before = snapshot(f['live'])
    result = run_stage(f, 'runner', values)
    assert result.returncode == 0, result.stdout + result.stderr
    assert snapshot(f['live']) == before
    assert guard(f, 'runner', 'verify', values).returncode == 0
    assert guard(f, 'runner', 'verify', values, operation='12345678-1234-1234-1234-123456789abd').returncode != 0
    payload = f['stage'] / 'runner-package/payload/bin/Runner.Listener'
    payload.write_text('#!/bin/sh\nexit 0\n')
    assert guard(f, 'runner', 'verify', values).returncode != 0
    assert snapshot(f['live']) == before


@pytest.mark.parametrize('failure', ['download', 'installer', 'layout', 'version', 'permissions'])
def test_codex_stage_failure_preserves_every_live_byte(package_fixture, failure):
    f = package_fixture
    values = codex_package(f, version='0.159.0' if failure == 'version' else '0.160.0',
                            escaping=failure == 'layout', fail=failure == 'installer')
    if failure == 'download': values['relay_codex_installer_url'] += '.missing'
    if failure == 'permissions':
        home = Path(values['relay_codex_package_home']); home.mkdir(mode=0o777); home.chmod(0o777)
    before = snapshot(f['live'])
    result = run_stage(f, 'codex', values)
    assert result.returncode != 0, result.stdout + result.stderr
    assert snapshot(f['live']) == before
    assert not (f['stage'] / 'codex-package/manifest.json').exists()


def test_codex_sealed_distribution_consumes_without_installer_or_network_and_rebinds_links(package_fixture):
    f = package_fixture; values = codex_package(f); before = snapshot(f['live'])
    result = run_stage(f, 'codex', values)
    assert result.returncode == 0, result.stdout + result.stderr
    assert snapshot(f['live']) == before
    assert guard(f, 'codex', 'verify', values).returncode == 0
    install = Path(values['relay_codex_package_install_dir']); install.mkdir(mode=0o700)
    collision = install / 'codex'; collision.write_text('retained regular-file collision')
    collided = snapshot(f['live'])
    assert guard(f, 'codex', 'consume', values).returncode != 0
    assert snapshot(f['live']) == collided
    collision.unlink()
    # Removing the download endpoint proves consume uses only the sealed payload.
    (f['public'] / 'install.sh').unlink()
    consumed = guard(f, 'codex', 'consume', values)
    assert consumed.returncode == 0, consumed.stdout + consumed.stderr
    command = Path(values['relay_codex_package_install_dir']) / 'codex'
    binary = command.resolve(strict=True)
    assert binary.is_relative_to(Path(values['relay_codex_package_home']))
    assert subprocess.run([str(command), '--version'], capture_output=True, text=True, check=True).stdout.strip() == 'codex-cli 0.160.0'
    resource = binary.parent / 'resource'
    assert not os.path.isabs(os.readlink(resource))
    assert resource.read_bytes() == b'payload'
    assert (f['live'] / 'consumer.json').read_text() == '{"accepted":"old"}'
    assert not Path(values['relay_codex_installer_path']).exists()


def test_live_roles_gate_network_and_installer_only_for_the_staged_route():
    for role, name in [('relay_runner', 'Download the pinned official GitHub Actions Runner package'),
                       ('relay_codex_runtime', 'Download the official Codex installer'),
                       ('relay_codex_runtime', 'Install the pinned official Codex CLI into the relay namespace')]:
        tasks = yaml.safe_load((ANSIBLE / 'roles' / role / 'tasks/main.yml').read_text())
        task = next(item for item in tasks if item.get('name') == name)
        assert 'relay_intent_stage_root is not defined' in task['when']
        first_effect = next(index for index, item in enumerate(tasks)
                            if 'ansible.builtin.group' in item or 'ansible.builtin.file' in item)
        guard_index = next(index for index, item in enumerate(tasks)
                           if 'Verify the frozen isolated' in item.get('name', ''))
        assert guard_index < first_effect


@pytest.mark.parametrize('link_kind', ['absolute', 'relative'])
def test_staging_accepts_native_update_layout_and_probes_only_as_runner(package_fixture, link_kind):
    import pwd
    f = package_fixture; values = runner_package(f)
    root = Path(values['relay_runner_root']); user = pwd.getpwnam(values['relay_runner_user'])
    binary = root / 'bin.2.400.0'; (root / 'bin').rename(binary)
    (root / 'bin').symlink_to(binary if link_kind == 'absolute' else binary.name, target_is_directory=True)
    external = root / 'externals.2.400.0'; (root / 'externals').rename(external)
    (root / 'externals').symlink_to(external, target_is_directory=True)
    diagnostic = root / '_diag'; diagnostic.mkdir(mode=0o750)
    os.chown(diagnostic, user.pw_uid, user.pw_gid)
    command = binary / 'Runner.Listener'
    command.write_text('#!/bin/sh\nid -u > "' + str(diagnostic / 'live-probe') + '"\nprintf "2.400.0\\n"\n')
    before = snapshot(f['live'])
    result = run_stage(f, 'runner', values)
    assert result.returncode == 0, result.stdout + result.stderr
    assert guard(f, 'runner', 'verify', values).returncode == 0
    observed = diagnostic / 'live-probe'
    assert observed.read_text().strip() == str(user.pw_uid) and observed.stat().st_uid == user.pw_uid
    assert observed.stat().st_mode & 0o777 == 0o600
    after = snapshot(f['live'])
    assert {name: row for name, row in before.items() if not name.startswith('runner/_diag')} == {
        name: row for name, row in after.items() if not name.startswith('runner/_diag')}


def test_staging_rejects_registered_corrupt_version_without_bootstrap_replacement(package_fixture):
    f = package_fixture; values = runner_package(f)
    command = Path(values['relay_runner_root']) / 'bin/Runner.Listener'
    command.write_text('#!/bin/sh\necho 2.400.0-invalid\n')
    before = snapshot(f['live'])
    result = run_stage(f, 'runner', values)
    assert result.returncode != 0 and 'RUNNER_REGISTERED_PACKAGE_REPAIR_REQUIRED' in result.stdout
    assert snapshot(f['live']) == before
    assert not (f['stage'] / 'runner-package/manifest.json').exists()


@pytest.mark.parametrize('target', ['../foreign/bin.2.400.0', '/bin', 'bin.02.400.0'])
def test_staging_rejects_unsafe_or_ambiguous_native_binary_alias(package_fixture, target):
    f = package_fixture; values = runner_package(f)
    root = Path(values['relay_runner_root']); (root / 'bin').rename(root / 'bin.2.400.0')
    (root / 'bin').symlink_to(target, target_is_directory=True)
    before = snapshot(f['live'])
    result = run_stage(f, 'runner', values)
    assert result.returncode != 0 and 'INTENT_RUNNER_NATIVE_LAYOUT_UNSAFE' in result.stdout
    assert snapshot(f['live']) == before


@pytest.mark.parametrize('damage', ['missing', 'dangling', 'escape', 'empty', 'node-missing', 'node-alias', 'node-not-executable'])
def test_interrupted_relink_is_rejected_by_normal_staging_and_converges_after_stopped_repair(package_fixture, damage):
    f = package_fixture; values = runner_package(f)
    root = Path(values['relay_runner_root'])
    (root / 'bin').rename(root / 'bin.2.400.0')
    (root / 'bin').symlink_to('bin.2.400.0')
    (root / 'bin/Runner.Listener').write_text('#!/bin/sh\nprintf "2.400.0\\n"\n')
    external = root / 'externals.2.400.0'
    (root / 'externals').rename(external)
    if damage == 'dangling': (root / 'externals').symlink_to('externals.2.400.1')
    elif damage == 'escape': (root / 'externals').symlink_to('/tmp')
    elif damage != 'missing':
        (root / 'externals').symlink_to(external)
        if damage == 'empty': (external / 'node24').rename(root / 'retained-node')
        else:
            node = external / 'node24/bin/node'
            if damage == 'node-missing': node.unlink()
            elif damage == 'node-alias':
                node.unlink(); node.symlink_to('/bin/true')
            else: node.chmod(0o600)
    before = snapshot(f['live'])
    result = run_stage(f, 'runner', values)
    assert result.returncode != 0, result.stdout + result.stderr
    assert snapshot(f['live']) == before
    assert not (f['stage'] / 'runner-package/manifest.json').exists()
    # The stopped fixture has no service/processes. Repair only retained links
    # and the synthetic payload; preserve registration and the newer version.
    if (root / 'externals').is_symlink(): (root / 'externals').unlink()
    if (root / 'retained-node').exists(): (root / 'retained-node').rename(external / 'node24')
    node = external / 'node24/bin/node'
    if node.is_symlink(): node.unlink()
    node.write_text('#!/bin/sh\nexit 0\n'); node.chmod(0o755)
    (root / 'externals').symlink_to(external)
    if (f['stage'] / 'runner-package').exists(): shutil.rmtree(f['stage'] / 'runner-package')
    repaired = snapshot(f['live'])
    result = run_stage(f, 'runner', values)
    assert result.returncode == 0, result.stdout + result.stderr
    assert guard(f, 'runner', 'verify', values).returncode == 0
    assert snapshot(f['live']) == repaired
