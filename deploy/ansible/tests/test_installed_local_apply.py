"""Execute the installed helper's code admission with native protected fixtures."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from jinja2 import Environment, StrictUndefined
import pytest

ROOT = Path(__file__).resolve().parents[1]
HEAD = 'a' * 40
WORKFLOW_HEAD = 'b' * 40
CODE = ['deploy/relay-deploy.py', 'deploy/config.py', 'deploy/installed_config.py',
        'deploy/deployment_lock.py', 'consumer/consumer-config.mjs',
        'contracts/src/execution-defaults.mjs', 'reviewer/src/executable-cr-v2.json']


@pytest.fixture
def helper():
    if sys.platform != 'linux' or os.geteuid() != 0:
        pytest.skip('native root filesystem required')
    with tempfile.TemporaryDirectory(prefix='relay-installed-helper-', dir='/run') as temporary:
        root = Path(temporary)
        install = root / 'relay'
        release = install / 'releases' / HEAD
        deploy = release / 'reviewed-source/deploy'
        deploy.mkdir(parents=True)
        (install / 'current').symlink_to(release)
        marker = root / 'executed'
        for name in CODE:
            path = deploy.parent / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('')
            path.chmod(0o644)
        (deploy / 'relay-deploy.py').write_text(
            'import os,sys\nfrom pathlib import Path\n'
            'assert os.geteuid()==0 and os.environ["HOME"]=="/root"\n'
            f'assert sys.argv[1:] == ["--config", {str(release / "deployment-config.json")!r}, '
            f'"--phase", "apply", "--local-reconcile", "--expected-installed-head", {HEAD!r}, '
            f'"--workflow-consumer-revision", {WORKFLOW_HEAD!r}]\n'
            f'Path({str(marker)!r}).write_text("called")\n')
        template = (ROOT / 'roles/relay_runner/templates/relay-production-local-apply.j2').read_text()
        script = Environment(undefined=StrictUndefined).from_string(template).render(
            relay_local_apply_source='installed', relay_install_root=str(install))
        # This suite exercises the unmodified admission and fixed argv. The
        # mount-namespace transition is separately covered by the legacy helper
        # production-boundary fixture and requires host namespace capability.
        script = script.replace('/usr/bin/nsenter --mount=/proc/1/ns/mnt --', '/usr/bin/env')
        executable = root / 'helper'
        executable.write_text(script)
        executable.chmod(0o750)
        yield executable, deploy, marker


def test_installed_helper_uses_only_fixed_snapshot_and_exact_sha(helper):
    executable, _, marker = helper
    result = subprocess.run([str(executable), HEAD + ":" + WORKFLOW_HEAD], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert marker.read_text() == 'called'


@pytest.mark.parametrize('name', CODE)
@pytest.mark.parametrize('unsafe', ['writable', 'owner', 'symlink', 'hardlink'])
def test_unsafe_imported_code_is_rejected_before_execution(helper, name, unsafe):
    executable, deploy, marker = helper
    target = deploy.parent / name
    if unsafe == 'writable':
        target.chmod(0o664)
    elif unsafe == 'owner':
        os.chown(target, 65534, 65534)
    elif unsafe == 'symlink':
        original = target.with_suffix('.original')
        target.rename(original)
        target.symlink_to(original)
    else:
        os.link(target, target.with_suffix('.alias'))
    result = subprocess.run([str(executable), HEAD + ":" + WORKFLOW_HEAD], capture_output=True, text=True)
    assert result.returncode != 0
    assert 'INSTALLED_CODE_UNSAFE' in result.stderr
    assert not marker.exists()


@pytest.mark.parametrize('arguments', [[], [HEAD], [HEAD, '--authorize-apply-recovery'], ['main'],
                                       [HEAD + ':main'], ['c' * 40 + ':' + WORKFLOW_HEAD]])
def test_installed_helper_has_no_extra_argument_surface(helper, arguments):
    executable, _, marker = helper
    result = subprocess.run([str(executable), *arguments], capture_output=True, text=True)
    assert result.returncode != 0
    assert not marker.exists()
