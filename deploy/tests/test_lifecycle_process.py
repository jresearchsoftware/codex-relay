"""One real quiet child stays observable without exposing private output."""
import io
from pathlib import Path
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import lifecycle_process as children
import owner_lifecycle as owner
import source_upgrade as upgrade


def test_quiet_child_reports_elapsed_wait_before_it_completes(tmp_path, capsys):
    release = tmp_path / 'release'
    program = ('import pathlib,time,sys;print("private-child-output",flush=True);'
        'print("private-child-error",file=sys.stderr,flush=True);p=pathlib.Path(sys.argv[1]);'
        '\nwhile not p.exists(): time.sleep(.01)\n')
    results = []
    running = threading.Thread(target=lambda: results.append(children.run(
        [sys.executable, '-c', program, str(release)], phase='owner-apply',
        dependency='public-deployment-primitive', interval=.05)))
    running.start()
    seen = ''
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and 'state=waiting' not in seen:
            seen += capsys.readouterr().out
            time.sleep(.01)
        assert 'state=waiting;elapsed_seconds=' in seen and running.is_alive()
        assert 'private-child-' not in seen
    finally:
        release.touch()
        running.join(timeout=5)
    assert not running.is_alive()
    assert results[0].stdout == 'private-child-output\n'
    assert results[0].stderr == 'private-child-error\n'


def test_split_drain_line_is_forwarded_before_quiet_child_exits(tmp_path, capsys):
    release = tmp_path / 'release'
    line = ('ADMISSION_DRAIN_PROGRESS phase=drain active=1 unknown=0 elapsedSeconds=0'
        ' pending=Task-244/Step-4/run-123 reason=waiting-for-controllers')
    program = ('import sys,pathlib,time;sys.stderr.write(' + repr(line[:70]) + ');sys.stderr.flush();'
        'time.sleep(.05);sys.stderr.write(' + repr(line[70:] + '\nprivate-child-error\n')
        + ');sys.stderr.flush();p=pathlib.Path(sys.argv[1]);'
        '\nwhile not p.exists(): time.sleep(.01)\n')
    results = []
    running = threading.Thread(target=lambda: results.append(children.run(
        [sys.executable, '-c', program, str(release)], phase='owner-admission',
        dependency='admission-gate', forward=owner.child_progress)))
    running.start()
    seen = ''
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and line not in seen:
            seen += capsys.readouterr().out
            time.sleep(.01)
        assert line in seen and running.is_alive()
        assert 'private-child-error' not in seen
    finally:
        release.touch()
        running.join(timeout=5)
    assert 'private-child-error' in results[0].stderr


def test_nonzero_keeps_bounded_original_channels_and_exit(capsys):
    program = 'import sys;sys.stdout.write("early-cause"+"a"*299979+"late-cause");sys.stderr.write("private-cause");sys.exit(7)'
    with pytest.raises(subprocess.CalledProcessError) as stopped:
        children.run([sys.executable, '-c', program], phase='owner-apply', dependency='public-deployment-primitive')
    assert stopped.value.returncode == 7
    assert stopped.value.stderr == 'private-cause'
    assert len(stopped.value.stdout) == children.CAPTURE_LIMIT
    assert stopped.value.stdout.startswith('early-cause') and stopped.value.stdout.endswith('late-cause')
    assert stopped.value.capture_bytes == {'stdout': 300000, 'stderr': 13}
    public = capsys.readouterr().out
    assert 'private-cause' not in public and 'state=child-completed' not in public


def test_timeout_retains_partial_channels_and_reaps_child(tmp_path):
    pid = tmp_path / 'child-pid'
    program = ('import os,sys,pathlib,time;pathlib.Path(sys.argv[1]).write_text(str(os.getpid()));'
        'print("partial-out",flush=True);print("partial-error",file=sys.stderr,flush=True);time.sleep(60)')
    with pytest.raises(subprocess.TimeoutExpired) as stopped:
        children.run([sys.executable, '-c', program, str(pid)], phase='owner-apply',
            dependency='public-deployment-primitive', timeout=.25)
    assert stopped.value.stdout == 'partial-out\n'
    assert stopped.value.stderr == 'partial-error\n'
    assert not Path('/proc/' + pid.read_text()).exists()


def test_cancellation_preserves_original_when_cleanup_also_fails(monkeypatch, capsys):
    class Child:
        pid = 12345
        stdout = io.BytesIO(b'original-output')
        stderr = io.BytesIO(b'original-error')
        def poll(self): return None
    monkeypatch.setattr(children.subprocess, 'Popen', lambda *args, **kwargs: Child())
    monkeypatch.setattr(children.os, 'killpg', lambda *args: (_ for _ in ()).throw(OSError('private-cleanup-failure')))
    monkeypatch.setattr(children.time, 'sleep', lambda *_: (_ for _ in ()).throw(KeyboardInterrupt('original-cancel')))
    with pytest.raises(KeyboardInterrupt, match='original-cancel') as stopped:
        children.run(['fixed-child'], phase='owner-apply', dependency='public-deployment-primitive')
    assert stopped.value.stdout == 'original-output' and stopped.value.stderr == 'original-error'
    public = capsys.readouterr().err
    assert 'child-cleanup-unproven' in public and 'private-cleanup-failure' not in public


@pytest.mark.parametrize('kind', ['workflow', 'pool', 'source-admission'])
def test_safe_preflight_wrappers_keep_child_cause(monkeypatch, kind):
    result = SimpleNamespace(returncode=7, stdout='private-original-output', stderr='private-original-error')
    monkeypatch.setattr(subprocess, 'run', lambda *args, **kwargs: result)
    def failed_child(*args, **kwargs):
        raise subprocess.CalledProcessError(result.returncode, 'fixed-child', output=result.stdout, stderr=result.stderr)
    monkeypatch.setattr(owner, 'run_child', failed_child)
    if kind == 'workflow':
        invoke = lambda: owner.projection_preflight(Path('/source'), 'a' * 40, Path('/consumer'), {})
    elif kind == 'pool':
        from contextlib import nullcontext
        monkeypatch.setattr(owner, 'acquire', lambda *args: nullcontext())
        invoke = lambda: owner.pool_preflight(Path('/source'), {'consumer': {'generalRunnerPool': {}},
            'environment': {'generalRunner': {'name': 'fixture'}}})
    else:
        invoke = lambda: upgrade.admission(['fixed-admission'], 'status')
    with pytest.raises((ValueError, RuntimeError)) as stopped:
        invoke()
    assert stopped.value.__cause__.returncode == 7
    assert stopped.value.__cause__.stdout == result.stdout
    assert stopped.value.__cause__.stderr == result.stderr


def test_guard_cleanup_error_cannot_replace_source_promotion_failure(monkeypatch, capsys):
    import ansible_transport
    class Child:
        def __init__(self, *args, **kwargs): pass
        def poll(self): return None
        def terminate(self): raise OSError('private-cleanup-error')
    monkeypatch.setattr(ansible_transport, 'TargetProcess', Child)
    prepared = SimpleNamespace(target=None, key=None, source='/source', local=True,
        values={}, identity={}, operation='op', stage='/stage', lease_path='/lease', admission_prefix=lambda: [])
    with pytest.raises(RuntimeError, match='^SOURCE_UPGRADE_OPERATION_GUARD_LOST$'):
        upgrade.guarded_promote(prepared, {}, [None])
    assert 'source-promotion-cleanup-unproven' in capsys.readouterr().err


def test_stdin_and_large_early_stderr_are_drained_together():
    program = ('import sys;sys.stderr.write("early-cause"+"x"*300000);sys.stderr.flush();'
        'data=sys.stdin.buffer.read();print(len(data));sys.exit(7)')
    with pytest.raises(subprocess.CalledProcessError) as stopped:
        children.run([sys.executable, '-c', program], input=b'x' * 1000000,
            phase='owner-preflight', dependency='workflow-projection', timeout=5)
    assert stopped.value.stdout == '1000000\n'
    assert stopped.value.stderr.startswith('early-cause')
    assert stopped.value.capture_bytes['stderr'] == 300011


def test_failed_progress_callback_does_not_stop_private_pipe_drain():
    def broken(_line):
        raise OSError('private-display-error')
    with pytest.raises(RuntimeError, match='^lifecycle-child-channel-unproven$') as stopped:
        children.run([sys.executable, '-c', 'import sys;sys.stdout.write("line\\n"*100000)'],
            phase='owner-apply', dependency='public-deployment-primitive', timeout=5, forward=broken)
    assert stopped.value.capture_bytes['stdout'] == 500000
    assert isinstance(stopped.value.__cause__, OSError)


def test_exited_parent_with_inherited_pipe_is_refused_and_its_group_cleaned(tmp_path):
    pid = tmp_path / 'descendant-pid'
    child = ('import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(60)')
    parent = ('import subprocess,pathlib,sys;child=subprocess.Popen([sys.executable,"-c",sys.argv[2]]);'
        'pathlib.Path(sys.argv[1]).write_text(str(child.pid))')
    with pytest.raises(RuntimeError, match='^lifecycle-child-channel-unproven$'):
        children.run([sys.executable, '-c', parent, str(pid), child],
            phase='owner-apply', dependency='public-deployment-primitive')
    status = Path('/proc/' + pid.read_text() + '/stat')
    assert not status.exists() or status.read_text().split()[2] == 'Z'


@pytest.mark.parametrize('line', [
    'RELAY_DEPLOYMENT_PROGRESS=backend;dependency=private-secret;state=running',
    'RELAY_DEPLOYMENT_PROGRESS=private-secret;dependency=release-artifacts;state=waiting',
    'RELAY_DEPLOYMENT_WARNING=private-secret;inspect-before-retry',
    'RELAY_ANSIBLE_FAILURE=phase=private-secret;evidence=protected-transport/relay-ansible-operation-abcdefgh;effect=unknown;next=inspect-original-operation-and-private-transport-evidence-before-retry',
    'RELAY_ANSIBLE_FAILURE=phase=target-operation;evidence=/private/path;effect=unknown;next=inspect-original-operation-and-private-transport-evidence-before-retry',
    'RELAY_LIFECYCLE_PROGRESS=private-secret;target=' + 'a' * 40])
def test_progress_forwarder_rejects_unowned_identifiers(line, capsys):
    owner.child_progress(line)
    assert capsys.readouterr().out == ''


@pytest.mark.parametrize('line', [
    'RELAY_DEPLOYMENT_PROGRESS=backend-running;dependency=release-artifacts;elapsed_seconds=30',
    'RELAY_DEPLOYMENT_PROGRESS=backend;dependency=release-artifacts;state=failed;exit=7;elapsed_seconds=30',
    'RELAY_LIFECYCLE_PROGRESS=QUIESCE;target=' + 'a' * 40,
    'RELAY_ANSIBLE_FAILURE=phase=target-operation;evidence=protected-transport/relay-ansible-operation-abcdefgh;effect=unknown;next=inspect-original-operation-and-private-transport-evidence-before-retry',
    'RELAY_DEPLOYMENT_WARNING=writer-lock-release-unproven;primary-failure-preserved;inspect-before-retry'])
def test_progress_forwarder_preserves_existing_public_observations(line, capsys):
    owner.child_progress(line)
    assert capsys.readouterr().out == line + '\n'
