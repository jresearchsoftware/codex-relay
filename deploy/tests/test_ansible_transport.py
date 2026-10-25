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
    assert not Path(calls[0][0][2]).parent.exists()


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
    assert capsys.readouterr().err == 'RELAY_TARGET_IDENTITY_UNPROVEN\n'


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
    assert capsys.readouterr().err == 'RELAY_TARGET_IDENTITY_UNPROVEN\n'
