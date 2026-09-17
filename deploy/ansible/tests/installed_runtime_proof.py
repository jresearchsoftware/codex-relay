#!/usr/bin/env python3
"""Run the real installed runtime in a disposable mount/PID/network namespace.

Requires root and unshare. Never installs users, paths or sudo rules on the
host: /etc, /opt, /var/lib, /var/log and /run are private mounts; no network is available.
Before entering the namespace, download and verify the source-pinned Rust
archive into temporary CI storage. The real artifact tasks install it privately.
The only substituted behavior is the external Codex distribution and GitHub transport. The
real Ansible tasks/templates, sudo user switch, dispatcher, launcher, result
parser, attempt journal and Git publication execute unchanged.
"""
import argparse
import hashlib
import json
import importlib.util
import os
import platform
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile

import yaml
from jinja2 import Environment, StrictUndefined

from test_production_install_current_main import RunnerPackageFixture

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]


def run(args, **kwargs):
    result = subprocess.run(args, text=True, **kwargs)
    if result.returncode:
        raise RuntimeError(f'{args}:\n{result.stdout or ""}\n{result.stderr or ""}')
    return result


def task(path, name):
    return next(t for t in yaml.safe_load(path.read_text()) if t.get('name') == name)


def consumer_trust_chain_proof(temp, values, env, deploy_umask, config, source):
    """Exercise the installed root Writer before credentials, in private mounts."""
    runtime = ROOT / 'roles/relay_runtime/tasks/main.yml'
    controller = ROOT / 'roles/relay_controller/tasks/main.yml'
    templates = [
        (runtime, 'Install secret-free relay environment contract'),
        (runtime, 'Install reviewer configuration contract'),
        (runtime, 'Record retention and health contract'),
        (controller, 'Install the root-readable on-demand Controller contract'),
    ]
    tasks = []
    for path, name in templates:
        entry = task(path, name)
        entry.pop('notify', None)  # This fixture never runs service handlers.
        entry['ansible.builtin.template']['src'] = str(path.parent.parent / 'templates' / entry['ansible.builtin.template']['src'])
        tasks.append(entry)
    playbook = temp / 'consumer-access.yml'
    playbook.write_text(yaml.safe_dump([{'hosts': 'localhost', 'gather_facts': False,
        'vars': {**values, 'relay_release_sha256': 'e' * 64}, 'tasks': tasks}]))
    run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(playbook)],
        env=env, capture_output=True, umask=deploy_umask)
    consumer = config / 'consumer.json'
    wrapper = Path(values['relay_install_root']) / 'relay-writer-controller'
    clean_env = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C',
                 'RELAY_CONSUMER_CONFIG': '/missing/caller-controlled-consumer.json'}

    def admission(expected):
        # Malformed stdin must reach REQUEST_INVALID only AFTER the real
        # assertRootConsumer gate, and BEFORE token()/any credential access.
        result = subprocess.run(['/usr/sbin/runuser', '-u', 'relay-runner', '--',
            'sudo', '-n', str(wrapper)], input='{', env=clean_env, text=True, capture_output=True, timeout=15)
        assert result.returncode == 1 and result.stdout == '', result
        assert result.stderr == json.dumps({'code': expected}, separators=(',', ':')) + '\n', result.stderr

    def ordinary_load():
        run(['/usr/sbin/runuser', '-u', 'relay-general-runner', '--', '/usr/bin/node',
             str(source / 'consumer/consumer.mjs')],
            env={**clean_env, 'RELAY_CONSUMER_CONFIG': str(consumer)}, capture_output=True)

    admission('REQUEST_INVALID')
    ordinary_load()
    for path in [consumer, *consumer.parents]:
        metadata = path.lstat()
        assert metadata.st_uid == 0 and not stat.S_ISLNK(metadata.st_mode) and not metadata.st_mode & 0o022, path
    assert (config.stat().st_gid, stat.S_IMODE(config.stat().st_mode)) == (0, 0o751)

    # Reproduce the incident: plain load succeeds despite a Relay-owned
    # parent. The fixed privileged entrypoint must still reject it.
    os.chown(config, 24004, 24004)
    try:
        ordinary_load()
        admission('CONSUMER_CONFIG_INVALID')
        reconciliation = temp / 'consumer-root-reconcile.yml'
        reconciliation.write_text(yaml.safe_dump([{'hosts': 'localhost', 'gather_facts': False,
            'vars': values, 'tasks': [task(runtime, 'Create namespaced relay directories')]}]))
        command = ['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(reconciliation)]
        run(command, env=env, capture_output=True, umask=deploy_umask)
        admission('REQUEST_INVALID')
        assert 'changed=0' in run(command, env=env, capture_output=True, umask=deploy_umask).stdout
        assert 'changed=0' in run([*command, '--check'], env=env, capture_output=True, umask=deploy_umask).stdout
    finally:
        os.chown(config, 0, 0)
    for mode in [0o0771, 0o0753]:
        config.chmod(mode)
        try:
            ordinary_load()
            admission('CONSUMER_CONFIG_INVALID')
        finally:
            config.chmod(0o751)
    os.chown(consumer, 24004, 24004)
    try:
        ordinary_load()
        admission('CONSUMER_CONFIG_INVALID')
    finally:
        os.chown(consumer, 0, 0)
    saved = config.with_name(config.name + '.saved')
    config.rename(saved)
    config.symlink_to(saved, target_is_directory=True)
    try:
        ordinary_load()
        admission('CONSUMER_CONFIG_INVALID')
    finally:
        config.unlink()
        saved.rename(config)
    admission('REQUEST_INVALID')

    identities = ['relay', 'relay-reviewer', 'relay-runner',
                  'relay-general-runner', 'relay-codex']

    def access(user, path, flag, allowed):
        result = subprocess.run(['/usr/sbin/runuser', '-u', user, '--', 'test', flag, str(path)], capture_output=True)
        assert result.returncode == (0 if allowed else 1), (user, path, flag, result.stderr)

    for user in identities:
        access(user, config, '-x', True)
        access(user, config, '-r', False)
        access(user, config, '-w', False)
        access(user, consumer, '-r', True)
        access(user, consumer, '-w', False)
    # Directory ownership remains independent of the shared root; these are
    # the actual deployed directories and rendered non-secret config files.
    boundaries = [
        ('certs', 24004, 24005, 0o750, {'relay', 'relay-reviewer'}, {'relay'}),
        ('reviewer-credentials', 0, 24005, 0o750, {'relay-reviewer'}, set()),
        ('writer-credentials', 0, 0, 0o700, set(), set()),
        ('codex-credentials', 24002, 24002, 0o700, {'relay-codex'}, {'relay-codex'}),
        ('reviewer-mcp.json', 0, 24005, 0o640, {'relay-reviewer'}, set()),
        ('relay.env', 0, 24005, 0o640, {'relay-reviewer'}, set()),
        ('retention-policy.yaml', 0, 24004, 0o640, {'relay'}, set()),
        ('controller.json', 0, 24001, 0o640, {'relay-runner'}, set()),
    ]
    for name, uid, gid, mode, readers, writers in boundaries:
        path = config / name
        metadata = path.lstat()
        assert (metadata.st_uid, metadata.st_gid, stat.S_IMODE(metadata.st_mode)) == (uid, gid, mode), name
        for user in identities:
            access(user, path, '-r', user in readers)
            access(user, path, '-w', user in writers)
            if path.is_dir():
                access(user, path, '-x', user in readers)
    token = config / 'codex-credentials/access-token'
    assert token.read_text() == 'fixture-only-credential\n'
    assert (token.stat().st_uid, stat.S_IMODE(token.stat().st_mode)) == (24002, 0o600)
    for user in identities:
        access(user, token, '-r', user == 'relay-codex')
        access(user, token, '-w', user == 'relay-codex')
    # No credentials or publication records were needed for admission.
    assert not (config / 'writer-credentials/github-app.env').exists()
    assert not (config / 'writer-credentials/github-app-private-key.pem').exists()
    assert not (Path('/var/lib/codex-relay/writer-claims') / 'publication-v2').exists()
    print('CONSUMER_TRUST_CHAIN_PROOF_PASS root-owned-parents;real-writer-sudo-admission;old-owner-rejected;'
          'writable-and-symlink-parents-rejected;reconcile-idempotent;child-access-preserved;no-credential-access', flush=True)


def restore_linker_alternative(etc, compiler):
    """Restore only cc's public executable link in the disposable /etc mount."""
    if not compiler.is_relative_to('/usr/bin') or not os.access(compiler, os.X_OK):
        raise RuntimeError('RUST_PROOF_LINKER_TARGET_UNSAFE')
    alternatives = etc / 'alternatives'
    alternatives.mkdir(exist_ok=True)
    (alternatives / 'cc').symlink_to(compiler)


def launcher_diagnostics_since(before):
    """Bounded projection of new, already-redacted fixture diagnostics only."""
    records = []
    for path in sorted(set(Path('/var/lib/codex-relay/debug').glob('*.json')) - before)[:8]:
        data = path.read_text()
        assert 'fixture-only-credential' not in data, 'FIXTURE_DIAGNOSTIC_SECRET_LEAK'
        diagnostic = json.loads(data).get('launcherDiagnostic') or {}
        record = {key: diagnostic.get(key) for key in ['code', 'childExitCode', 'childStarted']}
        record['preview'] = str(diagnostic.get('preview', '')).encode('utf8')[:1024].decode('utf8', errors='ignore')
        records.append(record)
        print('INSTALLED_CHILD_DIAGNOSTIC=' + json.dumps(record), flush=True)
    return records


def run_installed(args, **kwargs):
    before = set(Path('/var/lib/codex-relay/debug').glob('*.json'))
    try:
        return run(args, **kwargs)
    except RuntimeError:
        launcher_diagnostics_since(before)
        raise


def download_rust_archive(directory):
    """Acquire the existing source-controlled pin, without host installation."""
    values = yaml.safe_load((ROOT / 'group_vars/all.yml').read_text())
    templates = Environment(undefined=StrictUndefined)
    archive_name = templates.from_string(values['relay_rust_toolchain_archive']).render(values)
    url = templates.from_string(values['relay_rust_toolchain_url']).render({**values, 'relay_rust_toolchain_archive': archive_name})
    archive = directory / archive_name
    run(['/usr/bin/curl', '--fail', '--silent', '--show-error', '--location', '--max-time', '300',
         url, '--output', str(archive)], env={'PATH': '/usr/bin:/bin', 'HOME': str(directory)}, timeout=310)
    with archive.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    if digest != values['relay_rust_toolchain_archive_sha256']:
        raise RuntimeError('RUST_PROOF_ARCHIVE_CHECKSUM_MISMATCH')
    return archive


def rust_toolchain_proof(temp, values, env, deploy_umask, release):
    """Reconcile the actual Rust installation and prove reuse/Unix boundaries."""
    version = values['relay_rust_toolchain_version']
    rust = Path(Environment(undefined=StrictUndefined).from_string(values['relay_rust_toolchain_root']).render(values))
    binaries = {name: rust / 'bin' / name for name in ['cargo', 'rustc', 'rustfmt']}
    versions = {name: run(['/usr/sbin/runuser', '-u', 'relay-codex', '--', str(path), '--version'],
                          capture_output=True).stdout.strip() for name, path in binaries.items()}
    assert versions['cargo'].startswith(f'cargo {version} ')
    assert versions['rustc'].startswith(f'rustc {version} ')
    assert versions['rustfmt'].startswith('rustfmt ')
    before = {name: (path.stat().st_ino, path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest())
              for name, path in binaries.items()}
    # Reproduce the old traversal failure and restrictive installer modes,
    # then repair them through the same role with Reviewer reuse admitted.
    rust.parent.chmod(0o750)
    rust.chmod(0o700)
    assert subprocess.run(['runuser', '-u', 'relay-codex', '--', 'test', '-x', str(binaries['cargo'])]).returncode == 1
    build_cache = Path(values['relay_state_root']) / 'cargo-home'
    cache_marker = build_cache / 'reviewer-cache-sentinel'
    cache_marker.write_text('protected Reviewer build cache\n')
    cache_marker.chmod(0o600)
    rust_play = temp / 'rust-reconcile.yml'
    rust_play.write_text(yaml.safe_dump([{'hosts': 'localhost', 'gather_facts': False,
        'vars': {**values, 'relay_reviewer_reuse_verified': True, 'relay_rust_toolchain_url': 'file:///must-not-download-on-reuse'},
        'tasks': [{'ansible.builtin.include_role': {'name': 'relay_artifacts', 'tasks_from': 'rust-toolchain.yml'}}]}]))
    def reconcile(check=False):
        result = run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(rust_play), *(['--check'] if check else [])],
                     env=env, capture_output=True, umask=deploy_umask)
        return result.stdout
    reconcile()
    assert 'changed=0' in reconcile()
    assert 'changed=0' in reconcile(check=True)
    for name, path in binaries.items():
        assert (path.stat().st_ino, path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest()) == before[name]
    for path in [rust, *rust.rglob('*')]:
        info = path.lstat()
        assert info.st_uid == 0 and info.st_gid == 24004, path
        if not path.is_symlink():
            assert not stat.S_IMODE(info.st_mode) & 0o022, path
    assert (rust.parent.stat().st_uid, stat.S_IMODE(rust.parent.stat().st_mode)) == (0, 0o751)
    assert cache_marker.read_text() == 'protected Reviewer build cache\n'
    assert stat.S_IMODE(cache_marker.stat().st_mode) == 0o600
    for user in ['relay-codex', 'relay-runner', 'relay-general-runner']:
        assert subprocess.run(['runuser', '-u', user, '--', 'sudo', '-n', '-u', 'root', '/usr/bin/true'],
                              capture_output=True).returncode != 0, user
        for path in [rust.parent, rust, *binaries.values(), release, release / 'bin', release / 'reviewer-source', build_cache]:
            assert subprocess.run(['runuser', '-u', user, '--', 'test', '-w', str(path)]).returncode == 1, (user, path)
        for path in [build_cache, rust.parent / 'unpack', release / 'reviewer-source']:
            assert subprocess.run(['runuser', '-u', user, '--', 'test', '-r', str(path)]).returncode == 1, (user, path)
    expectations = Path('/run/managed-rust-proof.json')
    expectations.write_text(json.dumps({'root': str(rust), 'versions': versions, 'buildCache': str(build_cache),
                                       'release': str(release), 'reviewerSource': str(release / 'reviewer-source')}))
    expectations.chmod(0o644)
    print(f'MANAGED_RUST_UNIX_PROOF_PASS version={version};clean-install;reuse-without-download;reconcile;check-mode;root-owned;codex-read-execute;build-cache-private', flush=True)


def general_runner_proof(temp, values, env):
    """Reconcile the real second identity's state and grants beside production."""
    install = Path(values['relay_install_root'])
    state = Path('/var/lib/codex-relay')
    for path in [install / 'runner', state / 'runner']:
        path.mkdir()
        os.chown(path, 24001, 24001)
        path.chmod(0o750)
    for path in [Path('/etc/codex-relay/writer-credentials')]:
        path.mkdir(exist_ok=True)
        path.chmod(0o700)
    production_helper = install / 'relay-production-local-apply'
    # A sentinel detects any unauthorized execution, without applying anything.
    production_helper.write_text('#!/bin/sh\nprintf forbidden > /run/production-helper-executed\n')
    production_helper.chmod(0o750)
    journal = state / 'dispatch' / 'attempts-v2'
    journal.mkdir(parents=True)
    old_attempt = journal / 'preserved.json'
    old_attempt.write_text('{"status":"terminal"}\n')
    for path in [journal.parent, journal, old_attempt]:
        os.chown(path, 24001, 24001)
        path.chmod(0o700 if path.is_dir() else 0o600)
    old_checkout = state / 'dispatch-work' / 'worker-owned'
    old_checkout.mkdir()
    os.chown(old_checkout, 24002, 24000)
    old_checkout.chmod(0o2770)
    general = {
        **yaml.safe_load((ROOT / 'group_vars/all.yml').read_text()),
        **values,
        **yaml.safe_load((ROOT / 'vars/general-runner.yml').read_text()),
        'relay_deployment_profile': 'production',
        'relay_production_exact_head': 'c' * 40,
    }
    # Production's rule is rendered with its original identity, then the real
    # general role installs its three separately named rules and runtime state.
    tasks = [
        {'ansible.builtin.template': {
            'src': str(ROOT / 'roles/relay_runner/templates/relay-production-local-apply.sudoers.j2'),
            'dest': '/etc/sudoers.d/production-apply', 'mode': '0440'},
         'vars': {'relay_runner_user': 'relay-runner'}},
        {'ansible.builtin.template': {
            'src': str(ROOT / 'roles/relay_controller/templates/relay-writer-controller.j2'),
            'dest': '{{ relay_writer_helper_path }}', 'mode': '0750'}},
        {'ansible.builtin.include_role': {'name': 'relay_runner', 'tasks_from': 'general-runtime.yml'}},
        {'ansible.builtin.include_role': {'name': 'relay_runner', 'tasks_from': 'general-validation.yml'}},
    ]
    playbook = temp / 'general.yml'
    playbook.write_text(yaml.safe_dump([{'hosts': 'localhost', 'gather_facts': False, 'vars': general, 'tasks': tasks}]))
    result = subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(playbook)],
                            env=env, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    assert old_attempt.read_text() == '{"status":"terminal"}\n'
    assert old_attempt.stat().st_uid == 24003
    assert old_checkout.stat().st_uid == 24002
    assert (old_attempt.stat().st_mode & 0o777) == 0o600
    denied = subprocess.run(['runuser', '-u', 'relay-codex', '--', 'test', '-r', str(old_attempt)])
    assert denied.returncode == 1, 'worker must not gain access to the routing journal'
    denied = subprocess.run(['runuser', '-u', 'relay-general-runner', '--',
                             'sudo', '-n', str(production_helper), 'c' * 40], capture_output=True)
    assert denied.returncode != 0
    assert not Path('/run/production-helper-executed').exists()
    # The production account's original grant remains effective.
    run(['runuser', '-u', 'relay-runner', '--', 'sudo', '-n', str(production_helper), 'c' * 40], capture_output=True)
    assert Path('/run/production-helper-executed').read_text() == 'forbidden'
    smoke = subprocess.run(['runuser', '-u', 'relay-general-runner', '--',
                            'sudo', '-n', str(install / 'relay-writer-controller'), 'rejected-argument'],
                           capture_output=True)
    assert smoke.returncode == 40, 'general identity must reach the existing typed Writer wrapper'
    # The effective-policy gate must also catch a grant in a different file.
    excessive = Path('/etc/sudoers.d/unexpected-general-grant')
    validation = temp / 'general-policy-negative.yml'
    validation.write_text(yaml.safe_dump([{'hosts': 'localhost', 'gather_facts': False,
        'vars': general, 'tasks': [tasks[-1]]}]))
    try:
        for grant in ('ALL', '/bin/sh'):
            excessive.write_text(f'relay-general-runner ALL=(root) NOPASSWD: {grant}\n')
            excessive.chmod(0o440)
            failed = subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(validation)],
                                    env=env, text=True, capture_output=True)
            expected = 'failed_when_result' if grant == 'ALL' else 'GENERAL_RUNNER_SUDO_POLICY_UNEXPECTED'
            assert failed.returncode != 0 and expected in failed.stdout, failed.stdout
    finally:
        excessive.unlink()
    print('GENERAL_RUNNER_ISOLATION_PROOF_PASS', flush=True)


def runner_root_proof():
    """Extract/reconcile both real identities in the already private mounts."""
    proof_root = Path('/run/runner-root-proof')
    proof_root.mkdir(mode=0o755)
    for general, uid in ((False, 24001), (True, 24003)):
        directory = proof_root / ('general' if general else 'production')
        directory.mkdir(mode=0o755)
        values = {
            'relay_deployment_profile': 'production',
            'relay_install_root': '/opt/codex-relay',
            'relay_state_root': '/var/lib/codex-relay',
            'relay_runner_user': 'relay-runner', 'relay_runner_group': 'relay-runner',
            'relay_runner_root': '/opt/codex-relay/runner',
            'relay_runner_work_root': '/var/lib/codex-relay/runner/work',
            'relay_runner_home': '/var/lib/codex-relay/runner/home',
            'relay_runner_name': 'relay-production-relay',
            'relay_runner_registration_scope': 'organization',
        }
        if general:
            from ansible.parsing.dataloader import DataLoader
            from ansible.template import Templar
            overrides = yaml.safe_load((ROOT / 'vars/general-runner.yml').read_text())
            defaults = yaml.safe_load((ROOT / 'group_vars/all.yml').read_text())
            values.update(Templar(loader=DataLoader(), variables={**defaults, **values, **overrides}).template(overrides))
        # Only systemd I/O is substituted; namespace and identity guards stay real.
        values['relay_runner_service_unit_path'] = str(directory / 'units/runner.service')
        fixture = RunnerPackageFixture(directory, values)
        result = fixture.run()
        assert result.returncode == 0, result.stdout + result.stderr
        assert 'FIXTURE_PACKAGE_INSTALL_NEEDED=True' in result.stdout
        runner = fixture.runner
        metadata = runner.stat()
        assert (metadata.st_uid, metadata.st_gid, stat.S_IMODE(metadata.st_mode)) == (uid, uid, 0o750)
        assert not runner.is_symlink()
        helper_name = 'relay-general-runner-registration' if general else 'relay-runner-registration'
        helper = (Path(values['relay_install_root']) / helper_name).read_text()
        # Run the real helper's pre-credential gates only. The input prompt,
        # token handling and config.sh invocation are never reached or supplied.
        prefix, _ = helper.split('normalize_diagnostics() {', 1)
        assert 'read -r -s' not in prefix and 'exec ./config.sh' not in prefix
        probe = subprocess.run(['bash'], input=prefix, text=True, capture_output=True)
        assert probe.returncode == 0, probe.stdout + probe.stderr
        listener = runner / 'bin/Runner.Listener'
        before = listener.stat()
        runner.chmod(0o755)
        probe = subprocess.run(['bash'], input=prefix, text=True, capture_output=True)
        assert probe.returncode != 0 and 'RUNNER_ROOT_OWNERSHIP' in probe.stderr
        result = fixture.run()
        assert result.returncode == 0, result.stdout + result.stderr
        assert 'FIXTURE_PACKAGE_INSTALL_NEEDED=False' in result.stdout
        metadata = runner.stat()
        assert (metadata.st_uid, metadata.st_gid, stat.S_IMODE(metadata.st_mode)) == (uid, uid, 0o750)
        assert (listener.stat().st_ino, listener.stat().st_mtime_ns) == (before.st_ino, before.st_mtime_ns)
        probe = subprocess.run(['bash'], input=prefix, text=True, capture_output=True)
        assert probe.returncode == 0, probe.stdout + probe.stderr
        assert not (runner / '.runner').exists() and not (runner / '.credentials').exists()
        assert fixture.service_state.read_text() == 'inactive'
        assert 'lifecycle' not in fixture.trace.read_text()
        print(f'RUNNER_ROOT_METADATA_PROOF_PASS user={values["relay_runner_user"]};root={runner};mode=0750', flush=True)


def live_smoke_proof(install, release, env, token):
    """The installed owner mechanism, credential-free and network-isolated."""
    head = 'c' * 40
    manifest = release / 'artifact-manifest.json'
    manifest.write_text(json.dumps({'commit': head}))
    manifest.chmod(0o640)
    helper = install / 'relay-general-runner-smoke'
    command = [str(helper), '--approved-head', head]
    before = sorted(Path('/var/lib/codex-relay/dispatch-work').iterdir())
    sentinel = Path('/run/production-helper-executed').stat()
    # Intercept only Git's external-effect boundary during the smoke, while
    # every local Git operation still uses the actual installed binary.
    real_git = Path('/run/smoke-real-git')
    shutil.copyfile('/usr/bin/git', real_git)
    real_git.chmod(0o755)
    trace = Path('/run/smoke-git-effects')
    trace.write_text('')
    trace.chmod(0o666)
    git_guard = Path('/run/smoke-git-guard')
    git_guard.write_text('#!/bin/sh\ncase " $* " in *" push "*|*" fetch "*|*" clone "*|*" ls-remote "*) '
                         'printf "forbidden\\n" >> /run/smoke-git-effects; exit 97;; esac\n'
                         'printf "local\\n" >> /run/smoke-git-effects\nexec /run/smoke-real-git "$@"\n')
    git_guard.chmod(0o755)
    run(['mount', '--bind', str(git_guard), '/usr/bin/git'])

    def invoke(expected_child, expected_code):
        diagnostics_before = set(Path('/var/lib/codex-relay/debug').glob('*.json'))
        result = subprocess.run(command, env=env, text=True, capture_output=True)
        assert 'fixture-only-credential' not in result.stdout + result.stderr
        assert result.stderr == '', result.stderr
        prefix = 'GENERAL_RUNNER_SMOKE_RESULT='
        assert result.stdout.startswith(prefix), result.stdout
        proof = json.loads(result.stdout[len(prefix):])
        if proof['child'] != expected_child or proof['code'] != expected_code:
            launcher_diagnostics_since(diagnostics_before)
        assert proof['child'] == expected_child and proof['code'] == expected_code, proof
        assert proof['cleanup'] == 'cleaned', proof
        assert (result.returncode == 0) == (expected_code == 'GENERAL_RUNNER_SMOKE_PASS'), proof
        assert sorted(Path('/var/lib/codex-relay/dispatch-work').iterdir()) == before
        assert Path('/run/production-helper-executed').stat().st_mtime_ns == sentinel.st_mtime_ns
        print(result.stdout.strip(), flush=True)

    denied = subprocess.run(['/usr/sbin/runuser', '-u', 'relay-general-runner', '--', *command], capture_output=True)
    assert denied.returncode != 0
    # Directly loading the public module cannot bypass the owner transition.
    module = release / 'reviewed-source/consumer-general-runner-smoke.mjs'
    denied = subprocess.run(['/usr/sbin/runuser', '-u', 'relay-general-runner', '--', 'node', '-e',
        'const c=require("node:child_process").spawnSync("node",process.argv.slice(1),{stdio:"inherit"});process.exit(c.status)',
        str(module), '--approved-head', head], env=env, text=True, capture_output=True)
    assert denied.returncode != 0 and 'SMOKE_OWNER_TRANSITION_REQUIRED' in denied.stdout
    denied = subprocess.run([str(helper), '--approved-head', 'd' * 40], text=True, capture_output=True)
    assert denied.returncode != 0 and 'INSTALLED_HEAD_UNAVAILABLE' in denied.stderr
    invoke('started', 'GENERAL_RUNNER_SMOKE_PASS')
    saved = token.with_suffix('.smoke-saved')
    token.rename(saved)
    try:
        invoke('not_started', 'CODEX_NONZERO_EXIT')
    finally:
        saved.rename(token)
    dispatch = install / 'relay-codex-dispatch'
    saved_dispatch = dispatch.with_suffix('.smoke-saved')
    dispatch.rename(saved_dispatch)
    try:
        invoke('not_started', 'EXECUTION_FAILED')
    finally:
        saved_dispatch.rename(dispatch)
    assert trace.read_text() and set(trace.read_text().splitlines()) == {'local'}
    run(['umount', '/usr/bin/git'])
    print('OWNER_NON_ROUTING_SMOKE_DISPOSABLE_PROOF_PASS git-external-effects=none;production-helper=unchanged;live-production=not-executed', flush=True)


def runner_parent_trust_proof(temp, values, env, deploy_umask):
    """Run both later runner namespace passes without weakening product/cache parents."""
    namespace = task(ROOT / 'roles/relay_runner/tasks/main.yml',
                     'Create runner package cache and mutable namespaces')
    install, state = Path(values['relay_install_root']), Path(values['relay_state_root'])
    for name, user, uid in [('runner', 'relay-runner', 24001),
                            ('general-runner', 'relay-general-runner', 24003)]:
        instance = {**values, 'relay_runner_user': user, 'relay_runner_group': user,
                    'relay_runner_package_cache_root': str(temp / 'runner-cache'),
                    'relay_runner_root': str(install / 'parent-trust-proof' / name),
                    'relay_runner_work_root': str(state / 'parent-trust-proof' / name / 'work'),
                    'relay_runner_home': str(state / 'parent-trust-proof' / name / 'home')}
        playbook = temp / f'{name}-parent-trust.yml'
        playbook.write_text(yaml.safe_dump([{'hosts': 'localhost', 'gather_facts': False,
            'vars': instance, 'tasks': [namespace]}]))
        run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(playbook)],
            env=env, capture_output=True, umask=deploy_umask)
        for parent in [install, install / 'releases', state]:
            metadata = parent.lstat()
            assert metadata.st_uid == 0 and stat.S_ISDIR(metadata.st_mode) and not metadata.st_mode & 0o022, (
                f'{name} weakened protected parent {parent}: uid={metadata.st_uid}')
        for key in ['relay_runner_root', 'relay_runner_work_root', 'relay_runner_home']:
            metadata = Path(instance[key]).stat()
            assert (metadata.st_uid, stat.S_IMODE(metadata.st_mode)) == (uid, 0o750), key
    print('RUNNER_PARENT_TRUST_PROOF_PASS both-instances;root-owned-parents;runner-owned-children', flush=True)


def final_parent_gate_proof(temp, values, env, deploy_umask):
    """The final composed gate must catch a later role weakening a shared parent."""
    final = {**values, 'relay_consumer_revision': 'b' * 40,
             'relay_controller_source_tree_sha256': '1' * 64,
             'relay_reviewer_source_tree_sha256': '2' * 64,
             'relay_production_final_paths': {'results': [{'stat': {'lnk_source': values['relay_release_path']}}]},
             'relay_production_final_manifest': {
                 'installedRevision': values['relay_release_commit'],
                 'resolvedRevision': values['relay_release_commit'],
                 'gitTree': values['relay_source_identity']['tree'],
                 'consumerRevision': 'b' * 40, 'previousRevision': 'none',
                 'controllerSourceTreeSha256': '1' * 64, 'reviewerSourceTreeSha256': '2' * 64}}
    playbook = temp / 'final-parent-gate.yml'
    playbook.write_text(yaml.safe_dump([{'hosts': 'localhost', 'gather_facts': False,
        'vars': final, 'tasks': [{'ansible.builtin.include_tasks': str(ROOT / 'tasks/installed-identity.yml')}]}]))
    command = ['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(playbook)]
    valid = run(command, env=env, capture_output=True, umask=deploy_umask)
    assert 'RELAY_INSTALLED_REVISION=' in valid.stdout
    parent = Path(values['relay_state_root'])
    original = parent.stat()
    try:
        os.chown(parent, 24004, original.st_gid)
        invalid = subprocess.run(command, env=env, text=True, capture_output=True, umask=deploy_umask)
        assert invalid.returncode != 0 and 'RELAY_INSTALLED_PARENT_UNSAFE' in invalid.stdout
        assert 'RELAY_INSTALLED_REVISION=' not in invalid.stdout
    finally:
        os.chown(parent, original.st_uid, original.st_gid)
    print('FINAL_PARENT_GATE_PROOF_PASS late-owner-drift-rejected;no-success-receipt', flush=True)


def proof(runtime_only=False, rust_archive=None, consumer_only=False):
    # /usr/bin/cc on the CI host traverses /etc/alternatives/cc. Capture only
    # its public /usr executable target before replacing /etc; no host configs.
    compiler = Path('/usr/bin/cc').resolve(strict=True)
    assert Path('/usr/bin/cc').readlink() == Path('/etc/alternatives/cc'), 'RUST_PROOF_CC_TOPOLOGY_CHANGED'
    runner_service = (ROOT / 'roles/relay_runner/templates/relay-runner.service.j2').read_text()
    deploy_umask = int(next(line.split('=', 1)[1] for line in runner_service.splitlines() if line.startswith('UMask=')), 8)
    run(['mount', '--make-rprivate', '/'])
    run(['mount', '--bind', '/usr', '/usr'])
    run(['mount', '-o', 'remount,bind,ro', '/usr'])
    with tempfile.TemporaryDirectory(prefix='relay-installed-proof-') as temporary:
        temp = Path(temporary)
        for name, target in [('etc', '/etc'), ('opt', '/opt'), ('state', '/var/lib'), ('run', '/run'), ('logs', '/var/log')]:
            source = temp / name
            source.mkdir()
            run(['mount', '--bind', str(source), target])
        etc = Path('/etc')
        (etc / 'passwd').write_text('root:x:0:0:root:/root:/bin/sh\nrelay-runner:x:24001:24001:runner:/tmp:/bin/sh\nrelay-codex:x:24002:24002:codex:/var/lib/codex-relay/codex-home:/usr/sbin/nologin\nrelay-general-runner:x:24003:24003:general:/var/lib/codex-relay/general-runner/home:/usr/sbin/nologin\nrelay:x:24004:24004:relay:/nonexistent:/usr/sbin/nologin\nrelay-reviewer:x:24005:24005:reviewer:/nonexistent:/usr/sbin/nologin\n')
        (etc / 'group').write_text('root:x:0:\nrelay-runner:x:24001:\nrelay-codex:x:24002:\nrelay-general-runner:x:24003:\nrelay-codex-work:x:24000:relay-runner,relay-codex,relay-general-runner\nrelay:x:24004:\nrelay-reviewer:x:24005:\n')
        (etc / 'nsswitch.conf').write_text('passwd: files\ngroup: files\nshadow: files\nhosts: files\n')
        (etc / 'hosts').write_text(f'127.0.0.1 localhost {platform.node()}\n')
        (etc / 'sudoers').write_text('root ALL=(ALL) NOPASSWD: ALL\n@includedir /etc/sudoers.d\n')
        (etc / 'sudoers').chmod(0o440)
        (etc / 'sudoers.d').mkdir()
        (etc / 'pam.d').mkdir()
        for service in ['runuser', 'sudo']:
            (etc / 'pam.d' / service).write_text('auth sufficient pam_rootok.so\naccount required pam_permit.so\nsession required pam_permit.so\n')
        install = Path('/opt/codex-relay')
        release = install / 'releases' / ('c' * 40)
        source = release / 'reviewed-source'
        (release / 'bin').mkdir(parents=True)
        # Build an isolated index of the candidate working source, so local
        # fix/retry needs no commit and does not change the operator's index.
        # The real archive/extract tasks below preserve Git modes even on a
        # Windows checkout; never chmod the installed tree to public defaults.
        artifacts = ROOT / 'roles/relay_artifacts/tasks/main.yml'
        git_env = {'PATH': '/usr/bin:/bin', 'GIT_INDEX_FILE': str(temp / 'candidate-index'),
                   'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null'}
        git_command = ['git', '-c', f'safe.directory={REPO}', '-c', 'core.fileMode=false', '-C', str(REPO)]
        run([*git_command, 'read-tree', 'HEAD'], env=git_env, capture_output=True)
        run([*git_command, 'add', '--', '.'], env=git_env, capture_output=True)
        candidate_tree = run([*git_command, 'write-tree'], env=git_env, capture_output=True).stdout.strip()
        archive_path = temp / 'candidate-source.tar'
        run([*git_command, 'archive', '--format=tar', '--output=' + str(archive_path), candidate_tree], env=git_env, capture_output=True)
        install.joinpath('current').symlink_to(release)
        runtime = install / 'codex-runtime'
        shutil.copyfile(ROOT / 'tests/fake-installed-codex.mjs', '/run/fake-installed-codex.mjs')
        shutil.copyfile(ROOT / 'tests/rust-development-probe.mjs', '/run/rust-development-probe.mjs')
        config = etc / 'codex-relay'
        credentials = config / 'codex-credentials'
        credentials.mkdir(parents=True)
        os.chown(credentials, 24002, 24002)
        credentials.chmod(0o700)
        token = credentials / 'access-token'
        token.write_text('fixture-only-credential\n')
        os.chown(token, 24002, 24002)
        token.chmod(0o600)
        (config / 'diagnostics.json').write_text('{"schemaVersion":"1.0","mode":"normal","retentionCount":8}\n')
        work = Path('/var/lib/codex-relay/dispatch-work')
        work.mkdir(parents=True)
        os.chown(work, 24001, 24000)
        work.chmod(0o2770)
        values = {
            **yaml.safe_load((ROOT / 'group_vars/all.yml').read_text()),
            'relay_install_root': str(install), 'relay_release_path': str(release),
            'relay_codex_launcher_path': str(install / 'relay-codex'),
            'relay_codex_binary_path': str(runtime / 'bin/codex'),
            'relay_codex_diagnostic_path': str(runtime / 'relay-codex-diagnostic.mjs'),
            'relay_codex_access_token_file': str(token), 'relay_dispatch_work_root': str(work),
            'relay_diagnostics_config_path': str(config / 'diagnostics.json'),
            'relay_runner_user': 'relay-runner', 'relay_runner_group': 'relay-runner',
            'relay_codex_user': 'relay-codex',
            'relay_codex_dispatch_path': str(install / 'relay-codex-dispatch'),
            'relay_codex_dispatch_release_path': str(install / 'current/bin/relay-codex-dispatch.mjs'),
            'relay_diagnostics_store_path': str(install / 'relay-diagnostics-store'),
            'relay_diagnostics_store_release_path': str(release / 'bin/relay-diagnostics-store.mjs'),
            'relay_production_operation_phase': 'apply', 'relay_production_operation_target_head': 'c' * 40,
            'relay_codex_launcher_source_tree_sha256': 'd' * 64,
            'relay_production_final_manifest': {'commit': 'c' * 40, 'codexLauncherSourceTreeSha256': 'd' * 64},
            'relay_codex_installer_path': str(ROOT / 'tests/fake-codex-installer.sh'),
            'relay_codex_install_needed': True,
            'relay_review_root': str(REPO), 'relay_release_commit': 'c' * 40,
            'relay_exact_source_archive': {'path': str(temp / 'candidate-source.tar')},
            'relay_release_manifest': {'stat': {'exists': False}},
            'relay_source_archive': str(archive_path), 'relay_source_identity': {'revision': 'c'*40, 'tree': candidate_tree},
            'ansible_architecture': platform.machine(),
            'relay_rust_toolchain_url': Path(rust_archive).as_uri() if rust_archive else '',
        }
        # Execute actual install tasks, including the original module relocation
        # seam. The closure probe fails if it is replaced by a standalone copy.
        codex_tasks = ROOT / 'roles/relay_codex_runtime/tasks/main.yml'
        tasks = [
            task(ROOT / 'roles/relay_runtime/tasks/main.yml', 'Create namespaced relay directories'),
            task(artifacts, 'Create the exact relay release namespace'),
            task(artifacts, 'Allow runtime traversal only to the reviewed release executable namespace'),
            {'ansible.builtin.include_role': {'name': 'relay_artifacts', 'tasks_from': 'stage-source.yml'}},
            task(codex_tasks, 'Create the fixed Codex runtime and credential namespaces'),
            {'ansible.builtin.include_role': {'name': 'relay_controller', 'tasks_from': 'writer-entrypoint.yml'}},
        ]
        if not consumer_only:
            tasks.extend([
                {'ansible.builtin.include_role': {'name': 'relay_artifacts', 'tasks_from': 'rust-toolchain.yml'}},
                task(codex_tasks, 'Install the pinned official Codex CLI into the relay namespace'),
                {'ansible.builtin.include_role': {'name': 'relay_codex_runtime', 'tasks_from': 'runtime-namespace.yml'}},
                task(artifacts, 'Stage the exact reviewed on-demand Codex dispatch artifact'),
                {'ansible.builtin.include_role': {'name': 'relay_codex_runtime', 'tasks_from': 'launcher.yml'}},
                task(codex_tasks, 'Verify managed Rust tools through the Codex Unix identity without credentials'),
                {'ansible.builtin.template': {
                    'src': str(ROOT / 'roles/relay_codex_runtime/templates/relay-codex.sudoers.j2'),
                    'dest': '/etc/sudoers.d/codex', 'mode': '0440'}},
            ])
            tasks.append(task(artifacts, 'Stage the exact reviewed diagnostics store artifact'))
            tasks.append({'ansible.builtin.template': {'src': str(ROOT / 'roles/relay_controller/templates/relay-diagnostics.sudoers.j2'), 'dest': '/etc/sudoers.d/diagnostics', 'mode': '0440'}})
            tasks.append({'ansible.builtin.include_role': {'name': 'relay_codex_runtime', 'tasks_from': 'production-launcher-validation.yml'}})
        playbook = temp / 'install.yml'
        playbook.write_text(yaml.safe_dump([{'hosts': 'localhost', 'gather_facts': False, 'vars': values, 'tasks': tasks}]))
        env = {**os.environ, 'PATH': '/usr/bin:/bin', 'ANSIBLE_ROLES_PATH': str(ROOT / 'roles'), 'ANSIBLE_NOCOLOR': '1'}
        # Installed entrypoints must resolve their deployed snapshot even when
        # the source-workspace/workflow consumer environment is absent.
        env.pop('RELAY_CONSUMER_CONFIG', None)
        # This is the real production runner service's deploy umask. A normal
        # interactive root shell (0022) hides the installed-package EACCES.
        result = subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(playbook)], env=env, text=True, capture_output=True, umask=deploy_umask)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        consumer_config = config / 'consumer.json'
        metadata = consumer_config.lstat()
        assert stat.S_ISREG(metadata.st_mode)
        assert (metadata.st_uid, metadata.st_gid, stat.S_IMODE(metadata.st_mode)) == (0, 0, 0o644)
        consumer_trust_chain_proof(temp, values, env, deploy_umask, config, source)
        runner_parent_trust_proof(temp, values, env, deploy_umask)
        final_parent_gate_proof(temp, values, env, deploy_umask)
        if consumer_only:
            return
        rust_toolchain_proof(temp, values, env, deploy_umask, release)
        run(['visudo', '-cf', '/etc/sudoers'])
        for user, binary, expected in [('relay-codex', 'relay-codex', 'CODEX_LAUNCHER_RUNTIME_READY'), ('relay-runner', 'relay-codex-dispatch', 'RUNTIME_READY')]:
            output = run(['/usr/sbin/runuser', '-u', user, '--', str(install / binary), '--check-runtime'], capture_output=True).stdout
            assert expected in output, output
        spec = importlib.util.spec_from_file_location('production_diagnostic', ROOT / 'tools/production-diagnostic.py')
        diagnostic = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(diagnostic)
        assert diagnostic.worker_preflight(install / 'current')['status'] == 'passed'
        general_runner_proof(temp, values, env)
        if not runtime_only:
            runner_root_proof()
        package = Path('/var/lib/codex-relay/codex-home/packages')
        assert (package.stat().st_uid, stat.S_IMODE(package.stat().st_mode)) == (0, 0o700)
        assert (runtime / 'bin/codex').is_symlink()
        assert subprocess.run(['/usr/sbin/runuser', '-u', 'relay-codex', '--', 'test', '-x', str(package.parent)]).returncode == 0
        assert subprocess.run(['/usr/sbin/runuser', '-u', 'relay-codex', '--', 'test', '-x', str(package)]).returncode == 1
        print(f'CODEX_DENIED_TRAVERSAL user=relay-codex;path={package};operation=search;parent=accessible', flush=True)
        for path in [package, package / 'standalone', package / 'standalone/releases', (runtime / 'bin/codex').resolve().parents[1]]:
            info = path.stat()
            print(f'CODEX_PACKAGE_METADATA path={path};uid={info.st_uid};gid={info.st_gid};mode={stat.S_IMODE(info.st_mode):04o}', flush=True)
        env['RELAY_CONSUMER_CONFIG'] = str(consumer_config)
        env['INSTALLED_RUNNER_UID'] = '24003'
        tests = source / 'controller/test'
        tests.mkdir(exist_ok=True)
        shutil.copyfile(REPO / 'controller/test/fixture.mjs', tests / 'fixture.mjs')
        shutil.copyfile(ROOT / 'tests/installed-runtime.test.mjs', tests / 'installed-runtime.test.mjs')
        node_command = ['/usr/sbin/runuser', '-u', 'relay-general-runner', '--', 'node', '--test']
        test_path = str(tests / 'installed-runtime.test.mjs')
        run([*node_command, '--test-name-pattern=package-eacces', test_path],
            env={**env, 'INSTALLED_FIXTURE_EVENT_BASE': '900'}, umask=deploy_umask)
        package_playbook = temp / 'package-access.yml'
        reconciliation = task(codex_tasks, 'Reconcile installed Codex package traversal for its execution identity')
        package_tasks = [{'ansible.builtin.include_role': {'name': 'relay_codex_runtime',
                          'tasks_from': reconciliation['ansible.builtin.include_tasks']}, 'when': reconciliation['when']}]
        package_playbook.write_text(yaml.safe_dump([{'hosts': 'localhost', 'gather_facts': False, 'vars': values, 'tasks': package_tasks}]))
        payload = (runtime / 'bin/codex').resolve()
        payload_before = payload.stat()
        result = subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(package_playbook)],
                                env=env, text=True, capture_output=True, umask=0o077)
        assert result.returncode == 0, result.stdout + result.stderr
        payload_after = payload.stat()
        assert (payload_before.st_ino, payload_before.st_mode, payload_before.st_uid, payload_before.st_gid, payload_before.st_mtime_ns) == (
            payload_after.st_ino, payload_after.st_mode, payload_after.st_uid, payload_after.st_gid, payload_after.st_mtime_ns)
        for path in [package, package / 'standalone', package / 'standalone/releases', (runtime / 'bin/codex').resolve().parents[1]]:
            info = path.stat()
            assert (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) == (0, 24002, 0o750)
        for user in ['relay-runner', 'relay-general-runner']:
            assert subprocess.run(['runuser', '-u', user, '--', 'test', '-r', str(token)]).returncode == 1
            assert subprocess.run(['runuser', '-u', user, '--', 'test', '-x', str(package)]).returncode == 1
        # A redirected command must be rejected before permission mutation.
        visible = runtime / 'bin/codex'
        saved_link = runtime / 'bin/codex.saved'
        visible.rename(saved_link)
        try:
            visible.symlink_to('/run/fake-installed-codex.mjs')
            rejected = subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(package_playbook)],
                                      env=env, text=True, capture_output=True)
            assert rejected.returncode != 0 and 'CODEX_PACKAGE_LINK_UNSAFE' in rejected.stdout
        finally:
            visible.unlink()
            saved_link.rename(visible)
        live_smoke_proof(install, release, env, token)
        # Generic smoke must succeed even with the original missing linker.
        # Reproduce the Rust failure independently through the real launcher,
        # then repair only the fixture's alternative and require the same test.
        assert not Path('/usr/bin/cc').exists()
        diagnostics_before = set(Path('/var/lib/codex-relay/debug').glob('*.json'))
        rust_test = [*node_command, '--test-name-pattern=dedicated Rust development', test_path]
        run_installed(rust_test, env={**env, 'INSTALLED_RUST_LINKER': 'missing', 'INSTALLED_FIXTURE_EVENT_BASE': '960'}, umask=deploy_umask)
        records = launcher_diagnostics_since(diagnostics_before)
        assert len(records) == 1, 'RUST_PROOF_CAUSAL_DIAGNOSTIC_MISSING'
        assert records[0]['childStarted'] is True and records[0]['childExitCode'] == 1, records
        preview = records[0]['preview']
        assert 'RUST_DEVELOPMENT_PROOF_FAILED' in preview and 'cargo-test' in preview, records
        assert 'linker `cc` not found' in preview, records
        print('RUST_LINKER_FAILURE_REPRODUCED stage=cargo-test;cause=missing-cc-alternative;child=started;diagnostic=redacted', flush=True)
        restore_linker_alternative(etc, compiler)
        assert Path('/usr/bin/cc').resolve(strict=True) == compiler
        run_installed(rust_test, env={**env, 'INSTALLED_RUST_LINKER': 'ready', 'INSTALLED_FIXTURE_EVENT_BASE': '970'}, umask=deploy_umask)
        # The original production identity also traverses the composed path.
        run_installed(['/usr/sbin/runuser', '-u', 'relay-runner', '--', 'node', '--test',
             '--test-name-pattern=Issue gpt-6-astra/max', test_path],
            env={**env, 'INSTALLED_RUNNER_UID': '24001', 'INSTALLED_FIXTURE_EVENT_BASE': '950'}, umask=deploy_umask)
        # Distinct invocations keep protected failure setup root-owned.
        run_installed([*node_command, '--test-name-pattern=publication|profile rejection|checkout-ownership|invalid-result|child-failure', test_path], env={**env, 'INSTALLED_FIXTURE_EVENT_BASE': '1000'}, umask=deploy_umask)
        for offset, (mode, path) in enumerate([('missing-token', token), ('missing-binary', runtime / 'bin/codex'), ('missing-import', runtime / 'relay-codex-diagnostic.mjs')]):
            saved = path.with_suffix('.saved')
            path.rename(saved)
            try:
                run_installed([*node_command, f'--test-name-pattern={mode}', test_path], env={**env, 'INSTALLED_FAILURE_MODE': mode, 'INSTALLED_FIXTURE_EVENT_BASE': str(2000 + offset * 100)}, umask=deploy_umask)
            finally:
                saved.rename(path)
        # Missing transitive dependency in the staged dispatcher must fail
        # even though the source tree remains importable.
        dependency = source / 'controller/src/utf8-capture.mjs'
        dependency.unlink()
        failed = subprocess.run(['/usr/sbin/runuser', '-u', 'relay-runner', '--', str(install / 'relay-codex-dispatch'), '--check-runtime'], text=True, capture_output=True)
        assert failed.returncode != 0 and 'ERR_MODULE_NOT_FOUND' in failed.stderr
        assert diagnostic.worker_preflight(install / 'current')['code'] == 'MODULE_IMPORT_MISSING'
        print(f'INSTALLED_RUNTIME_COMPOSED_PROOF_PASS runner-package-metadata={"not-repeated" if runtime_only else "passed"}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inside', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--runtime-only', action='store_true', help='iterate the full runtime lane without repeating separate runner-package metadata tests')
    parser.add_argument('--consumer-only', action='store_true', help='qualify consumer ownership and installed Writer admission without Rust/Codex installation')
    parser.add_argument('--rust-archive', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit('root required for disposable namespace; use sudo on this test only')
    if not args.inside:
        if args.consumer_only:
            raise SystemExit(subprocess.call(['unshare', '--mount', '--pid', '--net', '--fork', '--mount-proc', sys.executable, str(Path(__file__).resolve()), *sys.argv[1:], '--inside']))
        with tempfile.TemporaryDirectory(prefix='relay-rust-proof-') as temporary:
            archive = download_rust_archive(Path(temporary))
            raise SystemExit(subprocess.call(['unshare', '--mount', '--pid', '--net', '--fork', '--mount-proc', sys.executable, str(Path(__file__).resolve()), *sys.argv[1:], '--inside', '--rust-archive', str(archive)]))
    if os.getpid() != 1:
        raise SystemExit('private PID namespace required; do not invoke --inside directly')
    proof(args.runtime_only, args.rust_archive, args.consumer_only)
