"""Real owner-holder/local acquisition contention on a protected host mutex."""
from contextlib import contextmanager
import importlib.util
import os
from pathlib import Path
import selectors
import stat
import subprocess
import sys
import tempfile
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
if sys.platform == 'linux':
    import deployment_lock

pytestmark = pytest.mark.skipif(sys.platform != 'linux' or os.geteuid() != 0,
                                reason='native root filesystem and flock required')


@pytest.fixture
def lock_path():
    with tempfile.TemporaryDirectory(prefix='relay-deployment-lock-test-', dir='/run') as temporary:
        parent = Path(temporary) / 'locks'
        parent.mkdir(mode=0o700)
        yield parent / 'deployment.lock'


def invocation(path):
    return [sys.executable, str(ROOT / 'deploy/deployment_lock.py'), str(path)]


@contextmanager
def owner_holder(path):
    # This stdin holder is the same lifetime contract used by the fixed owner
    # transport. Tests keep the process local and never contact an SSH target.
    process = subprocess.Popen(invocation(path), stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        with selectors.DefaultSelector() as ready:
            ready.register(process.stdout, selectors.EVENT_READ)
            assert ready.select(timeout=5), 'deployment holder did not become ready'
        assert process.stdout.readline() == 'DEPLOYMENT_LOCK_READY\n'
        assert process.poll() is None
        yield process
    finally:
        if process.stdin and not process.stdin.closed:
            process.stdin.close()
        if process.poll() is None:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        process.stdout.close()
        process.stderr.close()


def assert_cli_rejected(path, cwd=None):
    result = subprocess.run(invocation(path), input='', text=True, capture_output=True, timeout=5, cwd=cwd)
    assert result.returncode != 0
    assert result.stdout == ''
    assert len(result.stderr) < 160
    assert result.stderr == 'DEPLOYMENT_LOCK_BLOCKED\n'


def test_owner_holder_excludes_local_apply_until_eof(lock_path):
    with owner_holder(lock_path) as holder:
        with pytest.raises((OSError, ValueError)):
            with deployment_lock.acquire(lock_path):
                pytest.fail('local apply acquired an owner-held deployment lock')
        assert holder.poll() is None
        holder.stdin.close()
        assert holder.wait(timeout=5) == 0
        assert holder.stdout.read() == '' and holder.stderr.read() == ''
    with deployment_lock.acquire(lock_path) as fd:
        assert os.fstat(fd).st_ino == lock_path.stat().st_ino


def test_local_apply_excludes_owner_holder_until_context_exit(lock_path):
    with deployment_lock.acquire(lock_path):
        assert_cli_rejected(lock_path)
    with owner_holder(lock_path) as holder:
        assert holder.poll() is None


def test_killed_holder_releases_kernel_lock_without_success_output(lock_path):
    with owner_holder(lock_path) as holder:
        holder.kill()
        assert holder.wait(timeout=5) < 0
        assert holder.stdout.read() == ''
    with deployment_lock.acquire(lock_path):
        pass


def test_lock_creation_is_private_and_reuses_same_inode(lock_path):
    with deployment_lock.acquire(lock_path) as fd:
        info = os.fstat(fd)
        assert stat.S_ISREG(info.st_mode)
        assert info.st_uid == info.st_gid == 0
        assert stat.S_IMODE(info.st_mode) == 0o600
        assert info.st_nlink == 1
    with deployment_lock.acquire(lock_path) as fd:
        assert os.fstat(fd).st_ino == info.st_ino


@pytest.mark.parametrize('mutation', ['mode', 'group', 'owner', 'hardlink', 'symlink', 'directory'])
def test_unsafe_existing_lock_is_rejected_by_both_entry_paths(lock_path, mutation):
    lock_path.write_text('fixture-lock')
    lock_path.chmod(0o600)
    if mutation == 'mode':
        lock_path.chmod(0o640)
    elif mutation == 'group':
        os.chown(lock_path, 0, 1)
    elif mutation == 'owner':
        os.chown(lock_path, 1, 0)
    elif mutation == 'hardlink':
        os.link(lock_path, lock_path.with_name('lock-alias'))
    elif mutation == 'symlink':
        original = lock_path.with_name('original-lock')
        lock_path.rename(original)
        lock_path.symlink_to(original)
    else:
        lock_path.unlink()
        lock_path.mkdir()
    before = lock_path.lstat()
    with pytest.raises((OSError, ValueError)):
        with deployment_lock.acquire(lock_path):
            pytest.fail('unsafe deployment lock accepted')
    assert_cli_rejected(lock_path)
    after = lock_path.lstat()
    assert (after.st_ino, after.st_mode, after.st_uid, after.st_gid, after.st_nlink) == (
        before.st_ino, before.st_mode, before.st_uid, before.st_gid, before.st_nlink)


@pytest.mark.parametrize('mutation', ['writable', 'owner', 'symlink'])
def test_unsafe_ancestor_is_rejected_before_lock_creation(lock_path, mutation):
    parent = lock_path.parent
    if mutation == 'writable':
        parent.chmod(0o770)
    elif mutation == 'owner':
        os.chown(parent, 1, 0)
    else:
        original = parent.with_name('original-parent')
        parent.rename(original)
        parent.symlink_to(original)
    with pytest.raises((OSError, ValueError)):
        with deployment_lock.acquire(lock_path):
            pytest.fail('unsafe deployment lock parent accepted')
    assert_cli_rejected(lock_path)
    assert not lock_path.exists()


def test_nonroot_acquisition_cannot_create_lock(lock_path):
    with patch.object(deployment_lock.os, 'geteuid', return_value=1):
        with pytest.raises(ValueError):
            with deployment_lock.acquire(lock_path):
                pytest.fail('nonroot deployment lock acquired')
    assert not lock_path.exists()


def test_relative_lock_path_is_rejected_without_creating_state(lock_path, monkeypatch):
    monkeypatch.chdir(lock_path.parent)
    with pytest.raises((OSError, ValueError)):
        with deployment_lock.acquire(Path('relative-deployment.lock')):
            pytest.fail('relative deployment lock accepted')
    assert_cli_rejected('relative-deployment.lock', cwd=lock_path.parent)
    assert not lock_path.exists()
    assert not Path('relative-deployment.lock').exists()


@pytest.mark.parametrize('backend_code', ['import time; time.sleep(120)', 'pass'])
def test_guard_loss_terminates_backend_and_cannot_report_success(lock_path, backend_code):
    spec = importlib.util.spec_from_file_location('relay_deploy_lock_test', ROOT / 'deploy/relay-deploy.py')
    deploy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(deploy)
    native_popen = subprocess.Popen
    children = []
    with owner_holder(lock_path) as holder:
        def start_backend(*args, **kwargs):
            child = native_popen(*args, **kwargs)
            children.append(child)
            holder.kill()
            holder.wait(timeout=5)
            return child
        with (lock_path.parent / 'backend.log').open('w') as log:
            with patch.object(deploy.subprocess, 'Popen', side_effect=start_backend):
                with pytest.raises(RuntimeError, match='guard-lost'):
                    deploy.run_backend([sys.executable, '-c', backend_code],
                                       ROOT, os.environ.copy(), log, holder)
    assert len(children) == 1
    assert children[0].poll() is not None
    with deployment_lock.acquire(lock_path):
        pass
