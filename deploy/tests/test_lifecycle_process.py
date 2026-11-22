"""One real quiet child stays observable without exposing private output."""
import io
import importlib.util
from contextlib import nullcontext
import os
from pathlib import Path
import subprocess
import signal
import sys
import threading
import time
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import lifecycle_process as children
import lifecycle
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
    assert len(stopped.value.stdout) == children.CAPTURE_LIMIT + len(children.OMITTED)
    assert stopped.value.stdout.startswith('early-cause') and stopped.value.stdout.endswith('late-cause')
    assert stopped.value.capture_bytes == {'stdout': 300000, 'stderr': 13}
    public = capsys.readouterr().out
    assert 'private-cause' not in public and 'state=child-completed' not in public


@pytest.mark.parametrize('stdout,stderr,matched', [
    ([b'RELAY_', b'PROOF=PASS\n'], [], True),
    ([b'RELAY_PROOF=PASS'], [], True),
    ([b'prefix-RELAY_PROOF=PASS\n'], [], False),
    ([b'RELAY_PROOF=PASS-suffix\n'], [], False),
    ([b'RELAY_PROOF=PASS\r\n'], [], False),
    ([], [b'RELAY_PROOF=PASS\n'], False),
    ([b'x' * 9000, b'RELAY_PROOF=PASS\n'], [], False),
    ([b'x' * 9000, b'\nRELAY_PROOF=PASS\n'], [], True),
    ([b'RELAY_PROOF=FAIL\n'], [], False),
])
def test_exact_stdout_proof_recognition_is_independent_of_read_chunks_and_public_forwarding(
        monkeypatch, capsys, stdout, stderr, matched):
    class Stream(io.BytesIO):
        def __init__(self, chunks):
            super().__init__()
            self.chunks = iter(chunks)
        def read(self, _size):
            return next(self.chunks, b'')
    process = SimpleNamespace(returncode=0, poll=lambda: 0,
                              stdout=Stream(stdout), stderr=Stream(stderr))
    monkeypatch.setattr(children.subprocess, 'Popen', lambda *args, **kwargs: process)
    result = children.run(['fixed-child'], phase='owner-apply', dependency='public-deployment-primitive',
                          stdout_proofs=['RELAY_PROOF=PASS'])
    assert result.stdout_proofs == (frozenset(['RELAY_PROOF=PASS']) if matched else frozenset())
    assert result.capture_bytes == {'stdout': sum(map(len, stdout)), 'stderr': sum(map(len, stderr))}
    assert 'RELAY_PROOF=' not in capsys.readouterr().out


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


def test_incomplete_input_cannot_be_replaced_by_zero_child_exit():
    program = 'import os,sys,time;os.close(0);print("private-input-refused",file=sys.stderr,flush=True);time.sleep(.1)'
    with pytest.raises(RuntimeError, match='^lifecycle-child-channel-unproven$') as stopped:
        children.run([sys.executable, '-c', program], input=b'x' * 1000000,
            phase='owner-preflight', dependency='workflow-projection', timeout=5)
    assert isinstance(stopped.value.__cause__, BrokenPipeError)
    assert stopped.value.stderr == 'private-input-refused\n'


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


def test_owner_sigterm_preserves_interruption_and_stops_its_child_group(tmp_path):
    pid = tmp_path / 'child-pid'
    child = ('import os,pathlib,sys,time;pathlib.Path(sys.argv[1]).write_text(str(os.getpid()));'
        'print("private-child-cause",file=sys.stderr,flush=True);time.sleep(60)')
    program = ('import sys;sys.path.insert(0,sys.argv[1]);import owner_lifecycle as owner;'
        'owner.run=lambda request:owner.public_primitive([sys.executable,"-c",sys.argv[3],sys.argv[2]]);'
        'sys.exit(owner.main(["fixture"]))')
    process = subprocess.Popen([sys.executable, '-c', program, str(Path(owner.__file__).parent), str(pid), child],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic() + 5
        while not pid.exists() and time.monotonic() < deadline:
            time.sleep(.01)
        assert pid.exists()
        os.kill(process.pid, signal.SIGTERM)
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 1
        assert 'RELAY_OWNER_LIFECYCLE_BLOCKED=' in stderr
        assert 'private-child-cause' not in stdout + stderr
        status = Path('/proc/' + pid.read_text() + '/stat')
        assert not status.exists() or status.read_text().split()[2] == 'Z'
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_owner_preserves_custom_sigterm_handler_and_restores_default(monkeypatch):
    monkeypatch.setattr(owner, 'report_failure', lambda *args: None)
    observed = []
    monkeypatch.setattr(owner, 'run', lambda request: observed.append(signal.getsignal(signal.SIGTERM)))
    previous = signal.getsignal(signal.SIGTERM)
    try:
        custom = lambda *_args: None
        signal.signal(signal.SIGTERM, custom)
        assert owner.main(['fixture']) == 0 and observed[-1] is custom
        assert signal.getsignal(signal.SIGTERM) is custom
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        assert owner.main(['fixture']) == 0 and callable(observed[-1])
        assert signal.getsignal(signal.SIGTERM) == signal.SIG_DFL
    finally:
        signal.signal(signal.SIGTERM, previous)


def test_reader_startup_failure_still_stops_launched_child(monkeypatch):
    spawned = []
    real_spawn = subprocess.Popen
    def spawn(*args, **options):
        process = real_spawn(*args, **options)
        spawned.append(process)
        return process
    def fail_start(_thread):
        raise OSError('original-reader-start-failed')
    monkeypatch.setattr(children.subprocess, 'Popen', spawn)
    monkeypatch.setattr(children.threading.Thread, 'start', fail_start)
    with pytest.raises(OSError, match='original-reader-start-failed'):
        children.run([sys.executable, '-c', 'import time;time.sleep(60)'],
            phase='owner-apply', dependency='public-deployment-primitive')
    assert spawned[0].poll() is not None


@pytest.mark.parametrize('kind', [RuntimeError, AssertionError, ValueError])
def test_owner_unexpected_failure_keeps_private_cause_behind_safe_terminal(monkeypatch, capsys, kind):
    original = kind('private-unexpected-cause')
    recorded = []
    def fail(_request):
        raise original
    monkeypatch.setattr(owner, 'run', fail)
    monkeypatch.setattr(owner, 'report_failure', lambda error, phase: recorded.append((error, phase)))
    assert owner.main(['fixture']) == 1
    assert recorded == [(original, 'owner-lifecycle')]
    output = capsys.readouterr()
    assert 'Owner Relay lifecycle operation failed. Last verified boundary was input selection.' in output.err
    assert 'The cause at the failed boundary is unconfirmed.' in output.err
    assert 'RELAY_OWNER_LIFECYCLE_BLOCKED=input-or-io;inspect-state-and-protected-deployment-log' in output.err
    assert 'private-unexpected-cause' not in output.out + output.err


def test_owner_apply_reports_malformed_accepted_main_with_stable_code(monkeypatch, capsys):
    private = b'private-accepted-main-response'
    requests = []
    def github(method, path, _headers, **_options):
        requests.append((method, path))
        return private, 1
    def no_target_call(*args, **kwargs):
        pytest.fail('Apply touched the target after losing accepted main evidence')
    monkeypatch.setattr(owner.git_intent, 'github_response', github)
    monkeypatch.setattr(owner.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(owner, 'installed_config', lambda *_:
        ({'source': {'repository': 'https://github.com/example/product'}}, None, None))
    monkeypatch.setattr(owner, 'compile_inputs', lambda _:
        {'relay_install_root': '/fixture', 'relay_namespace': 'fixture'})
    monkeypatch.setattr(owner, 'deployment_repository', lambda _: 'example/product')
    monkeypatch.setattr(owner, 'acquire', lambda _: nullcontext())
    monkeypatch.setattr(owner, 'run_child', no_target_call)
    monkeypatch.setattr(owner, 'report_failure', lambda *_: {'status': 'unavailable'})

    assert owner.main(['apply:' + 'a' * 40 + ':' + 'b' * 40]) == 1
    assert requests == [('GET', '/repos/example/product/git/ref/heads/main')]
    output = capsys.readouterr()
    assert 'RELAY_OWNER_LIFECYCLE_BLOCKED=accepted-main-unavailable;' in output.err
    assert 'Last verified boundary was original installed identity.' in output.err
    assert 'GitHub GET (Git refs or objects)' in output.err and 'HTTP 200' in output.err
    assert '1 request attempt (0 retries)' in output.err
    assert 'Next action: Verify the selected repository’s trusted main commit through GitHub.' in output.err
    assert private.decode() not in output.out + output.err


@pytest.mark.parametrize(('error', 'code'), [
    (None, 'lifecycle-verification-unproven'),
    (ValueError('private-check-details'), 'ValueError'),
    (ValueError('INVALID_DEPLOYMENT_CONFIG:private-check-details'), 'ValueError'),
])
def test_deployment_terminal_keeps_typed_check_code_and_excludes_private_detail(monkeypatch, capsys, error, code):
    spec = importlib.util.spec_from_file_location('relay_deploy_terminal_test', Path(owner.__file__).with_name('relay-deploy.py'))
    deployment = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(deployment)
    calls = []
    def gate(action, *args):
        calls.append((action, *args))
        return {'drained': True} if action == 'drain' else {}
    def fail(_args):
        if error is None:
            lifecycle.execute(gate, 'a' * 40, lambda: calls.append(('apply',)), lambda *_: False)
            pytest.fail('unverified Apply reported success')
        lifecycle.observe_failure_state(boundary='drained', admission='closed')
        lifecycle.observe_target_mutation()
        raise error
    monkeypatch.setattr(deployment, 'arguments', lambda: SimpleNamespace(phase='apply'))
    monkeypatch.setattr(deployment, 'run', fail)
    monkeypatch.setattr(deployment, 'report_failure', lambda *_: {'status': 'unavailable'})

    assert deployment.main() == 1
    output = capsys.readouterr()
    assert f'RELAY_DEPLOYMENT_BLOCKED={code}\n' in output.err
    assert 'Last verified boundary was admission drain.' in output.err
    assert 'The last acknowledged gate state was closed.' in output.err
    assert 'Next action: Run the supported read-only deployment diagnostic for the same target' in output.err
    assert 'private-check-details' not in output.out + output.err
    if error is None:
        assert [call[0] for call in calls] == ['quiesce', 'drain', 'phase', 'apply', 'phase']
        assert calls[-1][-1] == 'recovery-required'


@pytest.mark.parametrize('kind', ['workflow', 'pool', 'source-admission', 'candidate-imports', 'selected-config'])
def test_zero_exit_malformed_proof_retains_original_channels(monkeypatch, kind):
    result = SimpleNamespace(returncode=0, stdout=b'private-malformed-proof', stderr=b'private-original-stderr')
    monkeypatch.setattr(subprocess, 'run', lambda *args, **kwargs: result)
    monkeypatch.setattr(owner, 'run_child', lambda *args, **kwargs: result)
    if kind == 'workflow':
        invoke = lambda: owner.projection_preflight(Path('/source'), 'a' * 40, Path('/consumer'), {})
    elif kind == 'pool':
        from contextlib import nullcontext
        monkeypatch.setattr(owner, 'acquire', lambda *args: nullcontext())
        invoke = lambda: owner.pool_preflight(Path('/source'), {'consumer': {'generalRunnerPool': {}},
            'environment': {'generalRunner': {'name': 'fixture'}}})
    elif kind == 'source-admission':
        invoke = lambda: upgrade.admission(['fixed-admission'], 'status')
    elif kind == 'selected-config':
        invoke = lambda: owner.selected_config(Path('/source'), b'{}')
    else:
        invoke = lambda: upgrade.candidate_checks(Path('/stage'), 'example/project')
    with pytest.raises((ValueError, RuntimeError)) as stopped:
        invoke()
    assert stopped.value.stdout == result.stdout and stopped.value.stderr == result.stderr
    assert stopped.value.capture_bytes == {'stdout': len(result.stdout), 'stderr': len(result.stderr)}
    assert stopped.value.observation['childExit'] == 0


def test_source_tree_semantic_reader_does_not_apply_diagnostic_capture_limit(monkeypatch):
    listing = '100644 blob ' + 'a' * 40 + '\tpath\n'
    expected = listing * 6000
    assert len(expected) > children.CAPTURE_LIMIT
    def read(argv, **options):
        assert 'ls-tree' in argv and options['check'] and options['capture_output']
        return subprocess.CompletedProcess(argv, 0, expected, '')
    monkeypatch.setattr(owner.subprocess, 'run', read)
    assert owner.git('/synthetic-source', 'ls-tree', '-r', 'a' * 40) == expected.strip()
