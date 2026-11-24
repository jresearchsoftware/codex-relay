"""Source-backed installed commands must leave the complete source tree intact."""
import os
from pathlib import Path
import runpy
import shutil
import stat
import subprocess
import sys
import tempfile

from jinja2 import Environment, StrictUndefined
import pytest

ANSIBLE = Path(__file__).resolve().parents[1]
DEPLOY = ANSIBLE.parent
HEAD = 'a' * 40

pytestmark = pytest.mark.skipif(sys.platform != 'linux' or os.geteuid() != 0,
                               reason='installed helper requires a native root fixture')


def snapshot(root):
    return {path.relative_to(root).as_posix():
            (stat.S_IMODE(path.stat().st_mode), path.read_bytes() if path.is_file() else None)
            for path in root.rglob('*')}


def tree_sha(files):
    stage = runpy.run_path(str(ANSIBLE / 'roles/relay_artifacts/files/relay-intent-stage.py'))
    return stage['git_tree']((name, f'100{mode:o}', raw)
                             for name, (mode, raw) in files.items() if raw is not None)


@pytest.fixture
def installed_source():
    with tempfile.TemporaryDirectory(prefix='relay-bytecode-', dir='/run') as temporary:
        install = Path(temporary)
        release = install / 'releases' / HEAD
        source = release / 'reviewed-source'
        scripts = source / 'deploy'
        scripts.mkdir(parents=True)
        (install / 'current').symlink_to(release)
        for name in ('managed_pool.py', 'installed_config.py', 'config.py'):
            shutil.copyfile(DEPLOY / name, scripts / name)
            (scripts / name).chmod(0o644)
        yield install, source


@pytest.mark.parametrize('extra_args', [[], ['--recover-reservation', 'fixture-operation']])
def test_rendered_managed_pool_keeps_exact_source_tree(installed_source, extra_args):
    install, source = installed_source
    template = ANSIBLE / 'roles/relay_runner/templates/relay-managed-pool.j2'
    helper = install / 'relay-managed-pool'
    helper.write_text(Environment(undefined=StrictUndefined).from_string(template.read_text()).render(
        relay_install_root=str(install)))
    helper.chmod(0o750)

    before = snapshot(source)
    result = subprocess.run(['/bin/sh', str(helper), HEAD, *extra_args], input='{}', env={}, text=True,
                            capture_output=True, timeout=15)
    # The real entrypoint imports the installed config verifier before rejecting
    # the absent snapshot. The fixture never reaches GitHub or runner mutation.
    assert (result.returncode, result.stdout, result.stderr) == (
        1, '', 'MANAGED_POOL_FAILED;inspect-before-retry\n')
    after = snapshot(source)
    assert tree_sha(after) == tree_sha(before)
    assert after == before


def test_installed_config_checker_keeps_source_tree(installed_source):
    _, source = installed_source
    before = snapshot(source)
    result = subprocess.run(['/usr/bin/python3', str(source / 'deploy/installed_config.py'),
                             HEAD, 'b' * 64, 'c' * 40, 'd' * 40],
                            env={'PATH': '/usr/bin:/bin'}, capture_output=True, text=True, timeout=15)
    assert (result.returncode, result.stdout, result.stderr) == (
        1, '', 'INSTALLED_CONFIG_BLOCKED=invalid-input-or-io\n')
    assert snapshot(source) == before


def test_publication_failure_reports_without_caching_source_module(installed_source):
    _, source = installed_source
    publisher = source / 'deploy/ansible/scripts/publish_git_consumer.py'
    publisher.parent.mkdir(parents=True)
    shutil.copyfile(ANSIBLE / 'scripts/publish_git_consumer.py', publisher)
    # Keep the real failure and import path, with a fixture-only recorder.
    (source / 'deploy/lifecycle.py').write_text(
        'import sys\n'
        'def report_failure(error, phase): print(phase, file=sys.stderr)\n')
    before = snapshot(source)

    result = subprocess.run(['/usr/bin/python3', '-I', str(publisher),
                             '--source', str(source), '--config-root', str(source / 'missing-config'),
                             '--desired', str(source / 'missing-desired'),
                             '--claim-root', str(source / 'missing-claims'),
                             '--repository', 'example-org/sample-project',
                             '--operation', '12345678-1234-1234-1234-123456789abc',
                             '--revision', HEAD], env={'PATH': '/usr/bin:/bin'}, text=True,
                            capture_output=True, timeout=15)
    assert result.returncode == 1
    assert result.stdout == '{"error_code": "CONSUMER_PUBLICATION_FAILED"}\n'
    assert result.stderr == 'consumer-publication\n'
    assert snapshot(source) == before
