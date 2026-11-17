"""Exercise real Ansible Core connections against disposable synthetic targets."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ansible_transport as transport
import config
import deployment_lock


ROOT = Path(__file__).resolve().parents[2]
LOCAL = {'user': 'root', 'host': 'synthetic-target.invalid', 'connection': 'local'}


def test_only_qualified_connections_and_connection_specific_capabilities():
    ssh = transport.connection_vars({'host': 'synthetic.invalid', 'user': 'root'}, '/owner/key')
    assert ssh['ansible_connection'] == 'ssh'
    assert ssh['ansible_ssh_private_key_file'] == '/owner/key'
    assert 'StrictHostKeyChecking=yes' in ssh['ansible_ssh_common_args']
    local = transport.connection_vars(LOCAL)
    assert local['ansible_connection'] == 'local' and local['ansible_become'] is True
    assert not any('ssh' in key or 'key_file' in key for key in local)
    installed_local = transport.connection_vars({'host': 'synthetic.invalid', 'user': 'root'}, local=True)
    assert installed_local['ansible_connection'] == 'local' and 'ansible_become' not in installed_local
    assert not any('ssh' in key or 'key_file' in key for key in installed_local)
    for connection in ['paramiko', 'winrm', 'docker', 'auto']:
        with pytest.raises(ValueError, match='unsupported-ansible-connection'):
            transport.connection_vars({**LOCAL, 'connection': connection})


def test_local_configuration_needs_no_ssh_identity_and_retains_host_binding():
    value = json.loads((ROOT / 'deploy/example.json').read_text())
    value['target']['connection'] = 'local'
    del value['target']['identityFile'], value['target']['identityFingerprint']
    config.validate(value, ROOT)
    value['target']['hostFingerprint'] = 'unproven'
    with pytest.raises(config.InvalidConfig, match='hostFingerprint'):
        config.validate(value, ROOT)


@pytest.mark.parametrize('json_payload', [False, True])
def test_actual_local_ansible_keeps_source_and_stdin_literal_and_private(tmp_path, capfd, json_payload):
    marker = tmp_path / 'must-not-execute'
    literal = "{{ lookup('pipe', 'touch " + str(marker) + "') }}\nsynthetic-private-input\n"
    if json_payload:
        literal = json.dumps({'source': literal, 'authorization': False, 'array': [1, 2]})
    code = 'import sys; value=sys.stdin.read(); assert value==sys.argv[1]; print("PUBLIC_RECEIPT=PASS")'
    process = transport.TargetProcess(LOCAL, None, ['/usr/bin/python3', '-c', code, literal], local=True)
    output, errors = process.communicate(input=literal, timeout=45)
    assert process.returncode == 0 and output == 'PUBLIC_RECEIPT=PASS\n' and errors == ''
    assert not marker.exists()
    assert not Path(process.temporary.name).exists()
    assert 'synthetic-private-input' not in ''.join(capfd.readouterr())


def test_actual_ansible_timeout_observes_same_operation_without_replay(tmp_path):
    effects = tmp_path / 'effects'
    code = ('import pathlib,time; p=pathlib.Path(__import__("sys").argv[1]); '
            'p.write_text(p.read_text()+"x" if p.exists() else "x"); '
            'time.sleep(0.3); print("RECEIPT")')
    process = transport.TargetProcess(LOCAL, None, ['/usr/bin/python3', '-c', code, str(effects)], local=True)
    with pytest.raises(subprocess.TimeoutExpired):
        process.communicate(timeout=0.01)
    output, _ = process.communicate(timeout=45)
    assert process.returncode == 0 and output == 'RECEIPT\n' and effects.read_text() == 'x'


def test_installed_owner_preflight_keeps_its_targetless_local_interface():
    result = transport.run_target(None, None, ['/usr/bin/python3', '-c', 'print("LOCAL_RECEIPT=PASS")'],
                                  local=True, timeout=45)
    assert result.returncode == 0 and result.stdout == 'LOCAL_RECEIPT=PASS\n'


def test_failed_ansible_launch_is_not_retried_by_cleanup(monkeypatch, tmp_path):
    calls = []
    def unavailable(*args, **kwargs):
        calls.append(args)
        raise OSError('synthetic unavailable Ansible')
    monkeypatch.setattr(transport.subprocess, 'Popen', unavailable)
    with pytest.raises(OSError, match='unavailable Ansible'):
        transport.run_target(LOCAL, None, ['/usr/bin/true'], local=True)
    assert len(calls) == 1
    retained = Path(calls[0][0][2]).parent
    assert 'synthetic unavailable Ansible' in (retained / 'failure.log').read_text()
    shutil.rmtree(retained)


def synthetic_ssh_channel(tmp_path, monkeypatch):
    """Replace only SSH I/O, retaining actual Ansible connection/module execution."""
    executable = tmp_path / 'synthetic-ssh'
    calls = tmp_path / 'calls.jsonl'
    executable.write_text('#!/usr/bin/python3\nimport json,subprocess,sys\n'
        + 'with open(' + repr(str(calls)) + ',"a") as f: f.write(json.dumps(sys.argv[1:])+"\\n")\n'
        + 'raise SystemExit(subprocess.call(["/bin/sh","-c",sys.argv[-1]],stdin=sys.stdin.buffer))\n')
    executable.chmod(0o755)
    original = transport.connection_vars

    def selected(*args, **kwargs):
        return {**original(*args, **kwargs), 'ansible_ssh_executable': str(executable),
                'ansible_ssh_transfer_method': 'piped', 'ansible_pipelining': True,
                'ansible_ssh_use_tty': False, 'ansible_become': False}

    monkeypatch.setattr(transport, 'connection_vars', selected)
    return calls


def test_real_ansible_ssh_plugin_owns_the_channel_and_strict_options(tmp_path, monkeypatch):
    calls = synthetic_ssh_channel(tmp_path, monkeypatch)
    result = transport.run_target({'user': 'root', 'host': 'synthetic-ssh.invalid'}, '/synthetic/key',
        ['/usr/bin/python3', '-c', 'import sys; assert sys.stdin.read()=="synthetic-private-input"; print("SSH_RECEIPT=PASS")'],
        input='synthetic-private-input', timeout=45)
    assert result.returncode == 0 and result.stdout == 'SSH_RECEIPT=PASS\n'
    recorded = calls.read_text()
    assert 'StrictHostKeyChecking=yes' in recorded and 'IdentitiesOnly=yes' in recorded
    assert '/synthetic/key' in recorded and 'synthetic-ssh.invalid' in recorded
    assert 'synthetic-private-input' not in recorded


@pytest.mark.skipif(os.geteuid() != 0, reason='real root host mutex and protected /run fixture')
@pytest.mark.parametrize('connection', ['local', 'ssh'])
def test_real_ansible_holds_original_host_and_pool_locks_until_release(tmp_path, monkeypatch, connection):
    if connection == 'ssh':
        synthetic_ssh_channel(tmp_path, monkeypatch)
    target = {**LOCAL, 'connection': connection}
    with tempfile.TemporaryDirectory(prefix='relay-owner-lock-test-', dir='/run') as directory:
        paths = [Path(directory) / name for name in ['host.lock', 'pool.lock']]
        guards = []
        source = (ROOT / 'deploy/deployment_lock.py').read_text()
        try:
            for path in paths:
                guards.append(transport.hold_target(target, '/synthetic/key',
                    ['/usr/bin/python3', '-I', '-c', source, str(path)], 'DEPLOYMENT_LOCK_READY'))
            inodes = [path.stat().st_ino for path in paths]
            for path in paths:
                with pytest.raises(ValueError, match='deployment-lock-busy'):
                    with deployment_lock.acquire(path):
                        pass
        finally:
            for guard in reversed(guards):
                guard.stdin.close()
                assert guard.wait(timeout=45) == 0
                assert not Path(guard.directory).exists()
        assert [path.stat().st_ino for path in paths] == inodes
        for path in paths:
            with deployment_lock.acquire(path):
                pass


@pytest.mark.skipif(os.geteuid() != 0, reason='real root guard interruption and protected /run fixture')
@pytest.mark.parametrize('connection', ['local', 'ssh'])
def test_interrupted_ansible_channel_releases_kernel_lock_without_replaying_work(tmp_path, monkeypatch, connection):
    if connection == 'ssh':
        synthetic_ssh_channel(tmp_path, monkeypatch)
    target = {**LOCAL, 'connection': connection}
    with tempfile.TemporaryDirectory(prefix='relay-owner-interruption-test-', dir='/run') as directory:
        path = Path(directory) / 'host.lock'
        source = (ROOT / 'deploy/deployment_lock.py').read_text()
        guard = transport.hold_target(target, '/synthetic/key',
            ['/usr/bin/python3', '-I', '-c', source, str(path)], 'DEPLOYMENT_LOCK_READY')
        guard.process.terminate()
        assert guard.wait(timeout=45) != 0
        deadline = time.monotonic() + 10
        while True:
            try:
                with deployment_lock.acquire(path):
                    break
            except ValueError:
                assert time.monotonic() < deadline
                time.sleep(0.1)
        # A SIGKILL may leave only an ephemeral rendezvous directory. It has no
        # lock/recovery authority and is never adopted by another invocation.
        if Path(guard.directory).exists():
            shutil.rmtree(guard.directory)


def test_local_target_identity_cannot_be_replaced_by_hostname_or_transport_selection(monkeypatch, capsys):
    monkeypatch.setattr(sys, 'argv', ['target-proof', 'local', 'SHA256:' + 'A' * 43])
    import glob
    monkeypatch.setattr(glob, 'glob', lambda _pattern: [])
    with pytest.raises(SystemExit) as error:
        exec(transport.TARGET_PROOF, {'__name__': '__main__'})
    assert error.value.code == 1
    assert capsys.readouterr().err.endswith('RELAY_TARGET_IDENTITY_UNPROVEN\n')


@pytest.mark.skipif(os.geteuid() != 0, reason='actual root authorization and protected public host key')
def test_local_target_identity_checks_the_existing_public_host_key(tmp_path, monkeypatch, capsys):
    import glob
    key = tmp_path / 'synthetic-host'
    subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key)], check=True)
    public = key.with_suffix('.pub')
    fingerprint = subprocess.check_output(['ssh-keygen', '-lf', str(public)], text=True).split()[1]
    monkeypatch.setattr(glob, 'glob', lambda _pattern: [str(public)])
    monkeypatch.setattr(sys, 'argv', ['target-proof', 'local', fingerprint])
    exec(transport.TARGET_PROOF, {'__name__': '__main__'})
    assert capsys.readouterr().out == 'RELAY_TARGET_IDENTITY=PASS\n'
    monkeypatch.setattr(sys, 'argv', ['target-proof', 'local', 'SHA256:' + 'A' * 43])
    with pytest.raises(SystemExit):
        exec(transport.TARGET_PROOF, {'__name__': '__main__'})
    assert capsys.readouterr().err.endswith('RELAY_TARGET_IDENTITY_UNPROVEN\n')


@pytest.fixture
def native_target():
    if sys.platform != 'linux' or os.geteuid() != 0:
        pytest.skip('native root Debian target required')
    for public in Path('/etc/ssh').glob('ssh_host_*_key.pub'):
        fingerprint = subprocess.check_output(['/usr/bin/ssh-keygen', '-lf', str(public)], text=True).split()[1]
        target = {**LOCAL, 'hostFingerprint': fingerprint}
        if transport.native_local_eligible(target):
            transport.prove_native_local(target)
            return target
    pytest.skip('private TEST namespace must supply protected synthetic public host key')


@pytest.mark.parametrize('payload', ['literal {{ unsafe }}\n', '{"private":"literal"}', b'bytes\x00exact\n'])
def test_native_local_exact_stdin_eof_private_spools_and_real_exit(native_target, payload, capfd):
    expected = payload if isinstance(payload, bytes) else payload.encode()
    code = 'import sys; data=sys.stdin.buffer.read(); assert data.hex()==sys.argv[1]; print("READY"); print("PRIVATE",file=sys.stderr);sys.exit(7)'
    process = transport.TargetProcess(native_target, None, ['/usr/bin/python3', '-c', code, expected.hex()])
    output, errors = process.communicate(input=payload, timeout=5)
    assert process.native and process.returncode == 7 and output == 'READY\n' and errors == 'PRIVATE\n'
    assert Path(process.temporary.name).is_dir()
    public = ''.join(capfd.readouterr())
    assert 'PRIVATE' not in public and 'protected-transport/' in public
    process.temporary.cleanup()


def test_native_start_large_input_never_waits_for_helper_to_read(native_target, tmp_path):
    release = tmp_path / 'release'
    code = ('import pathlib,sys,time; p=pathlib.Path(sys.argv[1]); '
            'exec("while not p.exists(): time.sleep(0.01)"); '
            'print(len(sys.stdin.buffer.read()))')
    process = transport.TargetProcess(native_target, None, ['/usr/bin/python3', '-c', code, str(release)])
    payload = 'x' * (8 * 1024 * 1024)
    try:
        process.start(payload)
        assert process.poll() is None
        for name in ['input', 'stdout', 'stderr']:
            path = Path(process.temporary.name) / name
            assert path.stat().st_mode & 0o777 == 0o600
        assert (Path(process.temporary.name) / 'input').read_text() == payload
        release.touch()
        assert process.communicate(timeout=5) == (str(len(payload)) + '\n', '')
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_native_timeout_observes_same_operation_without_replay(native_target, tmp_path):
    effect = tmp_path / 'effect'
    code = 'import pathlib,sys,time; p=pathlib.Path(sys.argv[1]);p.write_text(p.read_text()+"x" if p.exists() else "x");time.sleep(.2);print("DONE")'
    process = transport.TargetProcess(native_target, None, ['/usr/bin/python3', '-c', code, str(effect)])
    with pytest.raises(subprocess.TimeoutExpired) as timeout:
        process.communicate(timeout=.01)
    assert str(effect) not in str(timeout.value) and timeout.value.cmd == 'relay-target-operation'
    assert process.communicate(timeout=5) == ('DONE\n', '')
    assert effect.read_text() == 'x'


@pytest.mark.parametrize('channel', ['stdout', 'stderr'])
def test_native_oversized_result_is_bounded_and_redacted(native_target, channel):
    code = 'import sys;sys.' + channel + '.write("private"*200000)'
    process = transport.TargetProcess(native_target, None, ['/usr/bin/python3', '-c', code])
    assert process.communicate(timeout=5) == ('', 'ANSIBLE_TARGET_OPERATION_UNPROVEN\n')
    assert process.returncode == 255 and Path(process.temporary.name).is_dir()
    assert (Path(process.temporary.name) / 'failure.log').exists()
    process.temporary.cleanup()


def test_native_bad_fingerprint_stops_before_helper_and_reproves_each_command(native_target, tmp_path, monkeypatch):
    calls = []
    original = transport.prove_native_local
    def prove(target):
        calls.append(target['hostFingerprint'])
        return original(target)
    monkeypatch.setattr(transport, 'prove_native_local', prove)
    for _ in range(2):
        assert transport.run_target(native_target, None, ['/usr/bin/true']).returncode == 0
    marker = tmp_path / 'must-not-run'
    target = {**native_target, 'hostFingerprint': 'SHA256:' + 'A' * 43}
    with pytest.raises(RuntimeError, match='target-identity'):
        transport.run_target(target, None, ['/usr/bin/touch', str(marker)])
    assert not marker.exists() and len(calls) == 3


def test_native_group_termination_stops_helper_descendant(native_target, tmp_path):
    child = tmp_path / 'pid'
    code = ('import pathlib,subprocess,sys,time; p=subprocess.Popen(["/usr/bin/python3","-c","import time;time.sleep(60)"]);'
            'pathlib.Path(sys.argv[1]).write_text(str(p.pid));time.sleep(60)')
    process = transport.TargetProcess(native_target, None, ['/usr/bin/python3', '-c', code, str(child)])
    process.start()
    try:
        deadline = time.monotonic() + 5
        while not child.exists():
            assert time.monotonic() < deadline
            time.sleep(.01)
        pid = int(child.read_text())
        process.terminate()
        assert process.wait(timeout=5) != 0
        deadline = time.monotonic() + 5
        while Path('/proc', str(pid), 'stat').exists():
            if Path('/proc', str(pid), 'stat').read_text().rsplit(')', 1)[1].split()[0] == 'Z':
                break
            assert time.monotonic() < deadline
            time.sleep(.01)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_native_original_guard_ready_eof_and_release_preserve_kernel_locks(native_target, tmp_path, monkeypatch):
    monkeypatch.setitem(globals(), 'LOCAL', native_target)
    test_real_ansible_holds_original_host_and_pool_locks_until_release(tmp_path, monkeypatch, 'local')


def test_native_interrupted_guard_channel_releases_original_kernel_lock(native_target, tmp_path, monkeypatch):
    monkeypatch.setitem(globals(), 'LOCAL', native_target)
    test_interrupted_ansible_channel_releases_kernel_lock_without_replaying_work(tmp_path, monkeypatch, 'local')


@pytest.mark.parametrize('change', ['ssh', 'nonroot', 'caller', 'fingerprint', 'platform'])
def test_native_eligibility_preserves_unsupported_ansible_routes(native_target, monkeypatch, change):
    target = dict(native_target)
    if change == 'ssh': target['connection'] = 'ssh'
    elif change == 'nonroot': target['user'] = 'ordinary'
    elif change == 'caller': monkeypatch.setattr(os, 'geteuid', lambda: 1000)
    elif change == 'fingerprint': target.pop('hostFingerprint')
    else: monkeypatch.setattr(sys, 'platform', 'win32')
    assert not transport.native_local_eligible(target)


@pytest.mark.parametrize('change', ['ssh', 'nonroot', 'caller'])
def test_unqualified_native_context_still_launches_original_ansible_adapter(native_target, monkeypatch, change):
    target = dict(native_target)
    if change == 'ssh': target['connection'] = 'ssh'
    elif change == 'nonroot': target['user'] = 'ordinary'
    else: monkeypatch.setattr(os, 'geteuid', lambda: 1000)
    calls = []
    def popen(argv, **kwargs):
        calls.append((argv, kwargs))
        return type('Completed', (), {'returncode': 0, 'stdout': __import__('io').BytesIO(),
                                      'stderr': __import__('io').BytesIO()})()
    monkeypatch.setattr(transport.subprocess, 'Popen', popen)
    process = transport.TargetProcess(target, '/synthetic/key', ['/usr/bin/true'])
    try:
        process.start()
        assert not process.native and len(calls) == 1
        assert calls[0][0][0] == 'ansible-playbook'
        inventory = json.loads((Path(process.temporary.name) / 'inventory.json').read_text())
        selected = inventory['all']['children']['relay']['hosts'][target['host']]
        assert selected['ansible_user'] == target['user']
        assert selected['ansible_connection'] == target['connection']
    finally:
        process.temporary.cleanup()


def test_native_failed_launch_never_retries_and_removes_private_work(native_target, monkeypatch):
    original = transport.subprocess.Popen
    helper = ['/usr/bin/true']
    calls = []
    def popen(argv, **kwargs):
        if argv == helper:
            calls.append(argv)
            raise OSError('synthetic unavailable helper')
        return original(argv, **kwargs)
    monkeypatch.setattr(transport.subprocess, 'Popen', popen)
    process = transport.TargetProcess(native_target, None, helper)
    with pytest.raises(OSError, match='unavailable helper'):
        process.start('private')
    assert 'synthetic unavailable helper' in (Path(process.temporary.name) / 'failure.log').read_text()
    process.temporary.cleanup()
    with pytest.raises(RuntimeError, match='launch-unproven'):
        process.start('private')
    assert len(calls) == 1


def test_native_does_not_inherit_protected_parent_file_descriptors(native_target, tmp_path):
    with (tmp_path / 'private').open('w+b') as private:
        os.set_inheritable(private.fileno(), True)
        code = ('import os,sys\nfd=int(sys.argv[1])\ntry: os.fstat(fd)\n'
                'except OSError: print("CLOSED")\nelse: raise SystemExit(1)')
        result = transport.run_target(native_target, None,
            ['/usr/bin/python3', '-c', code, str(private.fileno())], timeout=5)
        assert result.returncode == 0 and result.stdout == 'CLOSED\n'


def test_native_communicate_waits_for_descendant_channel_eof_on_same_process(native_target):
    child = 'import time;time.sleep(.3);print("LATE")'
    code = 'import subprocess;subprocess.Popen(["/usr/bin/python3","-c",' + repr(child) + '])'
    process = transport.TargetProcess(native_target, None, ['/usr/bin/python3', '-c', code])
    with pytest.raises(subprocess.TimeoutExpired):
        process.communicate(timeout=.05)
    pid = process.process.pid
    assert process.process.poll() == 0 and process.poll() is None and process.pending_output()
    assert process.communicate(timeout=5) == ('LATE\n', '')
    assert process.process.pid == pid and not process.pending_output()


def test_native_output_path_replacement_refuses_without_reading_symlink_target(native_target, tmp_path):
    release = tmp_path / 'release'
    code = 'import pathlib,sys,time; p=pathlib.Path(sys.argv[1]);exec("while not p.exists(): time.sleep(.01)");print("OWNED")'
    process = transport.TargetProcess(native_target, None, ['/usr/bin/python3', '-c', code, str(release)])
    process.start()
    private = tmp_path / 'must-not-read'
    private.write_text('PRIVATE')
    output = process.output_paths[0]
    output.unlink()
    output.symlink_to(private)
    release.touch()
    assert process.communicate(timeout=5) == ('', 'ANSIBLE_TARGET_OPERATION_UNPROVEN\n')
    assert process.returncode == 255 and private.read_text() == 'PRIVATE'
    assert (Path(process.temporary.name) / 'failure.log').exists()
    process.temporary.cleanup()


def test_run_target_timeout_kills_descendant_group_even_after_main_exits(native_target, tmp_path, monkeypatch):
    child = tmp_path / 'pid'
    code = ('import pathlib,subprocess,sys; p=subprocess.Popen(["/usr/bin/python3","-c","import time;time.sleep(60)"]);'
            'pathlib.Path(sys.argv[1]).write_text(str(p.pid))')
    instances = []
    original = transport.TargetProcess
    class Observed(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            instances.append(self)
    monkeypatch.setattr(transport, 'TargetProcess', Observed)
    with pytest.raises(subprocess.TimeoutExpired):
        transport.run_target(native_target, None, ['/usr/bin/python3', '-c', code, str(child)], timeout=.2)
    assert len(instances) == 1
    process = instances[0]
    assert not process.pending_output() and not Path(process.temporary.name).exists()
    pid = int(child.read_text())
    if Path('/proc', str(pid), 'stat').exists():
        assert Path('/proc', str(pid), 'stat').read_text().rsplit(')', 1)[1].split()[0] == 'Z'


def test_native_escaped_descendant_channel_loss_is_bounded_and_unknown(native_target, tmp_path, monkeypatch):
    import signal
    child = tmp_path / 'escaped-pid'
    code = ('import pathlib,subprocess,sys; p=subprocess.Popen(["/usr/bin/python3","-c","import time;time.sleep(60)"],start_new_session=True);'
            'pathlib.Path(sys.argv[1]).write_text(str(p.pid))')
    instances = []
    original = transport.TargetProcess
    class Observed(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            instances.append(self)
    monkeypatch.setattr(transport, 'TargetProcess', Observed)
    monkeypatch.setattr(transport, 'CHANNEL_CLEANUP_TIMEOUT', .1)
    started = time.monotonic()
    try:
        with pytest.raises(subprocess.TimeoutExpired):
            transport.run_target(native_target, None, ['/usr/bin/python3', '-c', code, str(child)], timeout=.2)
        assert time.monotonic() - started < 3
        assert len(instances) == 1 and instances[0].pending_output()
        assert Path(instances[0].temporary.name).is_dir()
    finally:
        if child.exists():
            os.killpg(int(child.read_text()), signal.SIGKILL)
        if instances:
            instances[0].wait(timeout=5)
    assert (Path(instances[0].temporary.name) / 'failure.log').exists()
    instances[0].temporary.cleanup()


@pytest.mark.parametrize('failure', ['guard', 'deadline'])
def test_existing_guarded_promote_monitors_parent_exit_until_channel_eof(native_target, tmp_path, monkeypatch, failure):
    import source_upgrade
    from types import SimpleNamespace
    child = tmp_path / 'child-pid'
    helper = tmp_path / 'source/deploy/source_upgrade.py'
    helper.parent.mkdir(parents=True)
    helper.write_text('import json,pathlib,subprocess,sys\njson.load(sys.stdin)\n'
        'p=subprocess.Popen(["/usr/bin/python3","-c","import time;time.sleep(60)"])\n'
        'pathlib.Path(' + repr(str(child)) + ').write_text(str(p.pid))\n')
    instances = []
    original = transport.TargetProcess
    class Observed(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            instances.append(self)
    monkeypatch.setattr(transport, 'TargetProcess', Observed)
    def child_started():
        return child.exists() and instances and instances[0].process.poll() == 0
    holder = SimpleNamespace(poll=lambda: 1 if failure == 'guard' and child_started() else None)
    if failure == 'deadline':
        calls = []
        def clock():
            calls.append(True)
            if len(calls) == 1:
                return 0
            deadline = time.monotonic() + 5
            while not child_started():
                assert time.monotonic() < deadline
                time.sleep(.01)
            return 181
        monkeypatch.setattr(source_upgrade, 'time', SimpleNamespace(monotonic=clock, sleep=time.sleep))
    prepared = SimpleNamespace(target=native_target, key=None, source=str(helper.parents[1]), local=True,
        values={}, identity={}, operation='op', stage='/stage', lease_path='/stage/writer-lock.json',
        admission_prefix=lambda: ['bound-admission'])
    with pytest.raises(RuntimeError, match='GUARD_LOST' if failure == 'guard' else 'OPERATION_TIMEOUT'):
        source_upgrade.guarded_promote(prepared, {}, [holder])
    assert child_started()
    process = instances[0]
    assert process.poll() == 0 and not process.pending_output()
    assert not Path(process.temporary.name).exists()
    pid = int(child.read_text())
    if Path('/proc', str(pid), 'stat').exists():
        assert Path('/proc', str(pid), 'stat').read_text().rsplit(')', 1)[1].split()[0] == 'Z'


def test_guarded_promote_cancelled_escaped_channel_has_bounded_unknown_wait(native_target, tmp_path, monkeypatch):
    import source_upgrade
    import signal
    from types import SimpleNamespace
    child = tmp_path / 'escaped-child'
    helper = tmp_path / 'source/deploy/source_upgrade.py'
    helper.parent.mkdir(parents=True)
    helper.write_text('import json,pathlib,subprocess,sys\njson.load(sys.stdin)\n'
        'p=subprocess.Popen(["/usr/bin/python3","-c","import time;time.sleep(60)"],start_new_session=True)\n'
        'pathlib.Path(' + repr(str(child)) + ').write_text(str(p.pid))\n')
    instances = []
    original = transport.TargetProcess
    class Observed(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            instances.append(self)
    monkeypatch.setattr(transport, 'TargetProcess', Observed)
    monkeypatch.setattr(transport, 'CHANNEL_CLEANUP_TIMEOUT', .1)
    holder = SimpleNamespace(poll=lambda: 1 if child.exists() else None)
    prepared = SimpleNamespace(target=native_target, key=None, source=str(helper.parents[1]), local=True,
        values={}, identity={}, operation='op', stage='/stage', lease_path='/stage/writer-lock.json',
        admission_prefix=lambda: ['bound-admission'])
    started = time.monotonic()
    try:
        with pytest.raises((RuntimeError, ValueError), match='SOURCE_UPGRADE_OPERATION_GUARD_LOST'):
            source_upgrade.guarded_promote(prepared, {}, [holder])
        assert time.monotonic() - started < 3
        assert instances[0].pending_output() and Path(instances[0].temporary.name).exists()
    finally:
        if child.exists():
            os.killpg(int(child.read_text()), signal.SIGKILL)
        if instances:
            instances[0].communicate(timeout=5)
    assert not instances[0].pending_output()
    if Path(instances[0].temporary.name).exists():
        assert (Path(instances[0].temporary.name) / 'failure.log').exists()
        instances[0].temporary.cleanup()
