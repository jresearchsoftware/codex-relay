"""Live lifecycle evidence uses local child fixtures and never host authority."""
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import threading
from types import SimpleNamespace
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
import ansible_transport
from lifecycle import drain_progress
from source_upgrade import failure_code
from install_preflight import PreparedInstall

LINE = ('ADMISSION_DRAIN_PROGRESS phase=drain active=1 unknown=0 elapsedSeconds=2'
        ' pending=Task-244/Step-1/run-123 reason=waiting-for-controllers')


def test_native_channel_reports_verified_drain_before_helper_exits(tmp_path, capsys):
    release = tmp_path / 'release-child'
    script = ('import sys,time,pathlib;sys.stderr.write(' + repr(LINE[:55]) + ');sys.stderr.flush();'
              'sys.stderr.write(' + repr(LINE[55:] + '\nprivate-config-value\n') + ');sys.stderr.flush();'
              'p=pathlib.Path(sys.argv[1]);'
              '\nwhile not p.exists(): time.sleep(.01)\n')
    child = subprocess.Popen([sys.executable, '-c', script, str(release)], stderr=subprocess.PIPE)
    transport = ansible_transport.TargetProcess(None, None, [])
    spool = io.BytesIO()
    reader = threading.Thread(target=transport.read_channel, args=(child.stderr, spool, True))
    transport.reader_errors = []
    reader.start()
    try:
        import time
        deadline = time.monotonic() + 5
        seen = ''
        while time.monotonic() < deadline and LINE not in seen:
            seen += capsys.readouterr().out
            time.sleep(.01)
        assert LINE in seen and 'private-config-value' not in seen
        assert child.poll() is None
    finally:
        release.touch()
        child.wait(timeout=5)
        reader.join(timeout=5)
    assert not reader.is_alive() and not transport.reader_errors
    assert b'private-config-value' in spool.getvalue()


@pytest.mark.parametrize('line', [LINE + ';private=secret', LINE.replace('Task-244', 'private-config-value'),
    LINE.replace('active=1', 'active=-1'), LINE.replace('unknown=0', 'unknown=unknown'),
    'PRIVATE_STDERR=private-config-value', 'x' * 9000 + LINE])
def test_unbounded_or_unverified_drain_text_stays_private(line, capsys):
    drain_progress(line)
    assert capsys.readouterr().out == ''


def test_backend_reports_component_and_failure_while_retaining_private_log(tmp_path, capsys):
    spec = importlib.util.spec_from_file_location('lifecycle_progress_deploy', ROOT / 'deploy/relay-deploy.py')
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    log_path = tmp_path / 'private-backend.log'
    program = ('import sys,time;print("TASK [relay_artifacts : Build reviewed artifacts] ******",flush=True);'
               'print("private-config-value",flush=True);time.sleep(.1);sys.exit(7)')
    with log_path.open('w') as log:
        assert cli.run_backend([sys.executable, '-c', program], ROOT, os.environ.copy(), log) == 7
    output = capsys.readouterr().out
    assert 'dependency=release-artifacts;state=running' in output
    assert 'state=failed;exit=7' in output
    assert 'state=completed' not in output and 'private-config-value' not in output
    assert 'private-config-value' in log_path.read_text()


def test_source_failure_keeps_specific_safe_cause_and_rejects_raw_diagnostics():
    assert failure_code(ValueError('SOURCE_UPGRADE_CODEX_REFERENCE_CHANGED')) == 'SOURCE_UPGRADE_CODEX_REFERENCE_CHANGED'
    for error in [OSError('/private/path'), ValueError('SOURCE_UPGRADE_PRIVATE token-value'),
                  ValueError('ADMISSION_UNKNOWN\nprivate-config-value')]:
        assert failure_code(error) == 'SOURCE_UPGRADE_UNPROVEN'


@pytest.mark.parametrize('holder', ['host', 'writer'])
def test_holder_cleanup_failure_cannot_replace_primary_operation_failure(holder, capsys):
    spec = importlib.util.spec_from_file_location('lifecycle_cleanup_deploy', ROOT / 'deploy/relay-deploy.py')
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    guard = SimpleNamespace(stdin=io.StringIO(), wait=lambda **kwargs: 1)
    prepared = PreparedInstall(None, None, {'relay_release_root': '/opt/fixture/releases'},
                               {'revision': 'a' * 40}, '12345678-1234-1234-1234-123456789abc')
    prepared.holder = guard
    def release():
        return cli.release_guard(guard) if holder == 'host' else prepared.release_writer()
    with pytest.raises(RuntimeError, match='original-apply-failed'):
        try:
            raise RuntimeError('original-apply-failed')
        finally:
            release()
    assert 'primary-failure-preserved;inspect-before-retry' in capsys.readouterr().err
    guard.stdin = io.StringIO()
    prepared.holder = guard
    with pytest.raises((RuntimeError, ValueError)):
        release()


@pytest.mark.skipif(not shutil.which('ansible-playbook'), reason='Ansible required for private remote adapter fixture')
@pytest.mark.parametrize('exit_code', [0, 7])
@pytest.mark.parametrize('connection', ['local', 'ssh'])
def test_ansible_adapter_reports_remote_progress_before_helper_completion_without_sudo(tmp_path, monkeypatch, capsys, exit_code, connection):
    """Use real Ansible transport with only a local unprivileged fixture target."""
    import time
    monkeypatch.setenv('LC_ALL', 'C.UTF-8')
    monkeypatch.setenv('LANG', 'C.UTF-8')
    calls = None
    if connection == 'ssh':
        from test_ansible_transport import synthetic_ssh_channel
        calls = synthetic_ssh_channel(tmp_path, monkeypatch)
    else:
        current_vars = ansible_transport.connection_vars
        def unprivileged_connection(target, key=None, *, local=False):
            return {**current_vars(target, key, local=True), 'ansible_become': False}
        monkeypatch.setattr(ansible_transport, 'connection_vars', unprivileged_connection)
    monkeypatch.setattr(ansible_transport, 'native_local_eligible', lambda *args, **kwargs: False)
    monkeypatch.setattr(ansible_transport, 'PROGRESS_ROOT', tmp_path)
    for name in ['DRAIN_PROGRESS_WRAPPER', 'DRAIN_PROGRESS_READ']:
        monkeypatch.setattr(ansible_transport, name, getattr(ansible_transport, name).replace(
            "pathlib.Path('/run')", 'pathlib.Path(' + repr(str(tmp_path)) + ')'))
    release = tmp_path / 'release-helper'
    effects = tmp_path / 'helper-launches'
    private = 'private-remote-evidence {{ preserved-literally }}'
    code = ('import sys,time,pathlib;effects=pathlib.Path(' + repr(str(effects)) + ');'
            'effects.write_text(effects.read_text()+"x" if effects.exists() else "x");'
            'data=sys.stdin.read();assert data==' + repr(private) + ';'
            'print(' + repr(LINE) + ',file=sys.stderr,flush=True);'
            'print(' + repr(private) + ',file=sys.stderr,flush=True);'
            'p=pathlib.Path(sys.argv[1]);'
            '\nwhile not p.exists(): time.sleep(.01)\n'
            'print(\'{"drained":true}\',flush=True);sys.exit(' + str(exit_code) + ')')
    process = ansible_transport.TargetProcess({'host': 'synthetic-ssh.invalid' if connection == 'ssh' else 'localhost',
        'user': 'fixture', 'connection': connection}, '/synthetic/key',
        ['/usr/bin/python3', '-c', code, str(release)], local=connection == 'local', progress=True)
    results, failures = [], []
    def run():
        try:
            results.append(process.communicate(input=private, timeout=45))
        except Exception as error:
            failures.append(error)
    reader = threading.Thread(target=run)
    reader.start()
    seen = ''
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and LINE not in seen and reader.is_alive():
            seen += capsys.readouterr().out
            time.sleep(.02)
        assert LINE in seen, (seen, failures, results)
        assert process.process.poll() is None
        assert private not in seen
    finally:
        release.touch()
        reader.join(timeout=30)
        if reader.is_alive():
            process.terminate()
            process.wait(timeout=10)
            reader.join(timeout=10)
    assert not failures and not reader.is_alive(), failures
    assert process.returncode == exit_code and results[0][0] == '{"drained":true}\n'
    assert private in results[0][1]
    assert effects.read_text() == 'x'
    assert not process.remote_progress.exists()
    if calls is not None:
        recorded = calls.read_text()
        assert 'StrictHostKeyChecking=yes' in recorded and 'IdentitiesOnly=yes' in recorded
        assert '/synthetic/key' in recorded and private not in recorded


def test_remote_progress_reader_refuses_aliases_without_returning_private_bytes(tmp_path):
    directory = tmp_path / ('relay-ansible-progress-' + 'a' * 32)
    directory.mkdir(mode=0o700)
    secret = tmp_path / 'private-fixture'
    secret.write_text('private-fixture-value')
    (directory / 'progress').symlink_to(secret)
    code = ansible_transport.DRAIN_PROGRESS_READ.replace("pathlib.Path('/run')", 'pathlib.Path(' + repr(str(tmp_path)) + ')')
    result = subprocess.run([sys.executable, '-I', '-c', code, str(directory)], text=True, capture_output=True)
    assert result.returncode != 0 and result.stdout == ''
    assert result.stderr == 'ANSIBLE_PROGRESS_CHANNEL_UNPROVEN\n'


@pytest.mark.parametrize('result', [subprocess.CompletedProcess([], 1, '', 'private-transport-detail'),
    subprocess.CompletedProcess([], 0, 'private-malformed-channel-value\n', '')])
def test_remote_progress_failures_report_a_bounded_warning_once(result, monkeypatch, capsys):
    process = ansible_transport.TargetProcess(None, None, [])
    process.remote_progress = '/run/relay-ansible-progress-' + 'b' * 32
    monkeypatch.setattr(ansible_transport, 'run_target', lambda *args, **kwargs: result)
    process.observe_remote_progress(1)
    process.observe_remote_progress(1)
    output = capsys.readouterr().out
    assert output == 'RELAY_LIFECYCLE_WARNING=remote-drain-progress-unproven;inspect-protected-transport-evidence\n'
    assert process.process is None


@pytest.mark.parametrize('active,unknown,reason', [('UNAVAILABLE', 'UNAVAILABLE', 'lock-or-inventory-unavailable'),
    ('0', '2', 'inventory-unknown')])
def test_unknown_inventory_observations_are_forwarded_without_claiming_drain(active, unknown, reason, capsys):
    line = (f'ADMISSION_DRAIN_PROGRESS phase=drain active={active} unknown={unknown}'
            f' elapsedSeconds=3 pending=none reason={reason}')
    assert drain_progress(line)
    assert capsys.readouterr().out == line + '\n'


def test_preflight_transport_retains_private_child_output_behind_safe_code(monkeypatch, capsys):
    result = subprocess.CompletedProcess([], 40, 'original-private-output',
        'original-private-error\nADMISSION_DRAIN_STATUS_UNAVAILABLE\n')
    monkeypatch.setattr(ansible_transport, 'run_target', lambda *args, **kwargs: result)
    prepared = PreparedInstall(None, None, {'relay_release_root': '/opt/fixture/releases'},
                               {'revision': 'a' * 40}, '12345678-1234-1234-1234-123456789abc')
    with pytest.raises(RuntimeError, match='^ADMISSION_DRAIN_STATUS_UNAVAILABLE$') as caught:
        prepared.execute(['fixed-helper'])
    assert caught.value.__cause__.stdout == result.stdout
    assert caught.value.__cause__.stderr == result.stderr
    assert capsys.readouterr().out == ''


def test_source_promotion_transport_retains_original_output_and_specific_code(monkeypatch):
    import source_upgrade as upgrade
    result = ('private-original-output', 'private-original-error\nSOURCE_UPGRADE_GENERAL_CHANGED\n')
    class Process:
        returncode = 40
        def __init__(self, *args, **kwargs): pass
        def start(self, payload): pass
        def poll(self): return self.returncode
        def communicate(self, **kwargs): return result
    monkeypatch.setattr(ansible_transport, 'TargetProcess', Process)
    holder = SimpleNamespace(poll=lambda: None)
    prepared = SimpleNamespace(target=None, key=None, source='/fixture', local=True,
        values={}, identity={}, operation='op', stage='/stage', lease_path='/stage/lease',
        admission_prefix=lambda: [])
    with pytest.raises(RuntimeError, match='^SOURCE_UPGRADE_GENERAL_CHANGED$') as caught:
        upgrade.guarded_promote(prepared, {}, [holder])
    assert caught.value.__cause__.stdout == result[0]
    assert caught.value.__cause__.stderr == result[1]


@pytest.mark.parametrize('active,unknown', [('UNAVAILABLE', 'UNAVAILABLE'), ('0', '2')])
def test_remote_channel_keeps_multiple_observed_pending_changes_and_unknowns(active, unknown, monkeypatch, capsys):
    process = ansible_transport.TargetProcess(None, None, [])
    process.remote_progress = '/run/relay-ansible-progress-' + 'b' * 32
    first = ('ADMISSION_DRAIN_PROGRESS phase=drain active=2 unknown=0 elapsedSeconds=0'
             ' pending=Task-244/Step-1/run-123,Task-245/Step-2/run-124 reason=waiting-for-controllers')
    second = LINE
    third = (f'ADMISSION_DRAIN_PROGRESS phase=drain active={active} unknown={unknown} elapsedSeconds=3'
             ' pending=none reason=inventory-unknown')
    result = subprocess.CompletedProcess([], 0, '\n'.join([first, second, third]) + '\n', '')
    monkeypatch.setattr(ansible_transport, 'run_target', lambda *args, **kwargs: result)
    process.observe_remote_progress(1)
    process.observe_remote_progress(1)
    assert capsys.readouterr().out.splitlines() == [first, second, third]


def test_remote_wrapper_keeps_rapid_changes_before_the_next_read(tmp_path):
    directory = tmp_path / ('relay-ansible-progress-' + 'a' * 32)
    observations = [LINE.replace('active=1', 'active=2'), LINE,
        LINE.replace('active=1', 'active=0').replace('reason=waiting-for-controllers', 'reason=drained')]
    marker = tmp_path / 'release-child'
    private = 'original-private-stderr'
    code = ('import sys,time,pathlib;print(' + repr('\n'.join(observations) + '\n' + private)
            + ',file=sys.stderr,flush=True);p=pathlib.Path(sys.argv[1]);'
            '\nwhile not p.exists(): time.sleep(.01)\n')
    wrapper = ansible_transport.DRAIN_PROGRESS_WRAPPER.replace("pathlib.Path('/run')", 'pathlib.Path(' + repr(str(tmp_path)) + ')')
    from lifecycle import DRAIN_PROGRESS_PATTERN
    process = subprocess.Popen([sys.executable, '-I', '-c', wrapper, str(directory), DRAIN_PROGRESS_PATTERN],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        import json, time
        process.stdin.write(json.dumps({'argv': [sys.executable, '-c', code, str(marker)], 'input': ''}))
        process.stdin.close()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if (directory / 'progress').exists() and (directory / 'progress').read_text().splitlines() == observations:
                break
            time.sleep(.01)
        assert process.poll() is None
        assert (directory / 'progress').read_text().splitlines() == observations
        assert private not in (directory / 'progress').read_text()
    finally:
        marker.touch()
        process.wait(timeout=5)
    assert private in process.stderr.read()
    assert not directory.exists()



def test_remote_admission_failure_keeps_cause_behind_the_existing_public_code(monkeypatch):
    spec = importlib.util.spec_from_file_location('lifecycle_admission_deploy', ROOT / 'deploy/relay-deploy.py')
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    result = subprocess.CompletedProcess([], 7, 'original-private-stdout',
        'original-private-stderr\nADMISSION_DRAIN_STATUS_UNAVAILABLE\n')
    monkeypatch.setattr(cli, 'run_target', lambda *args, **kwargs: result)
    with pytest.raises(ValueError, match='^ADMISSION_DRAIN_STATUS_UNAVAILABLE;inspect-before-recovery$') as caught:
        cli.remote_admission(None, None, 'fixture', 'drain')
    assert caught.value.__cause__.stdout == result.stdout
    assert caught.value.__cause__.stderr == result.stderr



def test_progress_dedup_history_is_bounded_and_preserves_the_recent_batch(capsys):
    process = ansible_transport.TargetProcess(None, None, [])
    for elapsed in range(2100):
        process.forward_progress(LINE.replace('elapsedSeconds=2', f'elapsedSeconds={elapsed}'))
    capsys.readouterr()
    process.forward_progress(LINE.replace('elapsedSeconds=2', 'elapsedSeconds=2099'))
    assert capsys.readouterr().out == ''
    assert len(process.forwarded_progress) <= 2048


def test_remote_progress_overflow_is_explicit_and_keeps_latest_observations(tmp_path):
    import json, time
    from lifecycle import DRAIN_PROGRESS_PATTERN
    directory = tmp_path / ('relay-ansible-progress-' + 'b' * 32)
    marker = tmp_path / 'release-overflow-child'
    code = ('import sys,time,pathlib;'
            '\nfor elapsed in range(700): print(' + repr(LINE)
            + '.replace("elapsedSeconds=2",f"elapsedSeconds={elapsed}"),file=sys.stderr,flush=True)'
            '\np=pathlib.Path(sys.argv[1])'
            '\nwhile not p.exists(): time.sleep(.01)\n')
    wrapper = ansible_transport.DRAIN_PROGRESS_WRAPPER.replace("pathlib.Path('/run')", 'pathlib.Path(' + repr(str(tmp_path)) + ')')
    with (tmp_path / 'private-overflow-stderr').open('w+') as private:
        process = subprocess.Popen([sys.executable, '-I', '-c', wrapper, str(directory), DRAIN_PROGRESS_PATTERN],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=private, text=True)
        try:
            process.stdin.write(json.dumps({'argv': [sys.executable, '-c', code, str(marker)], 'input': ''}))
            process.stdin.close()
            deadline = time.monotonic() + 5
            expected = LINE.replace('elapsedSeconds=2', 'elapsedSeconds=699')
            raw = ''
            while time.monotonic() < deadline:
                if (directory / 'progress').exists():
                    raw = (directory / 'progress').read_text()
                    if raw.endswith(expected + '\n'): break
                time.sleep(.01)
            assert process.poll() is None and raw.endswith(expected + '\n')
            assert raw.startswith('ANSIBLE_PROGRESS_CHANNEL_TRUNCATED\n')
            assert len(raw.encode()) <= 65536
            assert LINE.replace('elapsedSeconds=2', 'elapsedSeconds=0') + '\n' not in raw
        finally:
            marker.touch()
            process.wait(timeout=5)
        private.seek(0)
        assert private.read().count('ANSIBLE_PROGRESS_CHANNEL_TRUNCATED') == 1
    assert not directory.exists()



def test_final_receipt_does_not_replay_old_activity_after_dedup_eviction(tmp_path, capsys):
    import json
    process = ansible_transport.TargetProcess(None, None, [])
    process.remote_progress = '/run/relay-ansible-progress-' + 'a' * 32
    observations = [LINE.replace('elapsedSeconds=2', f'elapsedSeconds={elapsed}') for elapsed in range(2100)]
    for line in observations: process.forward_progress(line)
    capsys.readouterr()
    terminal = ('ADMISSION_DRAIN_PROGRESS phase=drain active=0 unknown=0 elapsedSeconds=2100'
                ' pending=none reason=drained')
    process.result_path = tmp_path / 'receipt.json'
    process.result_path.write_text(json.dumps({'rc': 0, 'stdout': '{}',
        'stderr': '\n'.join(observations + [terminal]) + '\n'}))
    process.process = SimpleNamespace(poll=lambda: 0, returncode=0)
    process.temporary = SimpleNamespace(cleanup=lambda: None)
    process.communicate()
    assert capsys.readouterr().out == terminal + '\n'



@pytest.mark.parametrize('suffix', ['[repository=example-org/sample-project;slot=primary]',
    '[repository=example-org/peer-project;slot=slot-2]', '[repository=example-org/sample-project]'])
def test_drain_forwards_bounded_native_repository_and_slot_locations(suffix, capsys):
    line = LINE.replace('/run-123', '/run-123' + suffix)
    assert drain_progress(line)
    assert capsys.readouterr().out == line + '\n'


@pytest.mark.parametrize('suffix', ['[repository=../../private;slot=primary]',
    '[repository=owner/repo;slot=private slot]', '[repository=owner/repo;slot=../private]',
    '[repository=owner/repo;slot=primary;private=value]', '[slot=primary]',
    '[repository=owner/repo]private-value'])
def test_drain_location_grammar_rejects_unbounded_or_arbitrary_fields(suffix, capsys):
    assert not drain_progress(LINE.replace('/run-123', '/run-123' + suffix))
    assert capsys.readouterr().out == ''


def test_deployment_unexpected_exception_retains_cause_without_public_path(monkeypatch, capsys):
    spec = importlib.util.spec_from_file_location('deployment_unexpected', ROOT / 'deploy/relay-deploy.py')
    cli = importlib.util.module_from_spec(spec); spec.loader.exec_module(cli)
    monkeypatch.setattr(cli, 'arguments', lambda: object())
    def fail(_args):
        raise AssertionError('private unexpected native cause /private/host/path')
    monkeypatch.setattr(cli, 'run', fail)
    captured = []
    monkeypatch.setattr(cli, 'report_failure', lambda error, phase: captured.append((error, phase)))
    assert cli.main() == 1
    assert isinstance(captured[0][0], AssertionError) and captured[0][1] == 'deployment-entrypoint'
    public = capsys.readouterr().err
    assert 'BLOCKED=AssertionError' in public and 'private' not in public


@pytest.mark.parametrize('code', ['inventory-blocked:private-observation', 'workflow-file-unavailable:/private/host/path;inspect-file-type-and-access', 'environment.repository'])
def test_deployment_domain_failure_keeps_safe_check_identity_and_protects_details(monkeypatch, capsys, code):
    spec = importlib.util.spec_from_file_location('deployment_domain', ROOT / 'deploy/relay-deploy.py')
    cli = importlib.util.module_from_spec(spec); spec.loader.exec_module(cli)
    monkeypatch.setattr(cli, 'arguments', lambda: object())
    def fail(_args):
        raise cli.InvalidConfig('INVALID_DEPLOYMENT_CONFIG:' + code)
    monkeypatch.setattr(cli, 'run', fail)
    captured = []
    monkeypatch.setattr(cli, 'report_failure', lambda error, phase: captured.append(error))
    assert cli.main() == 1
    text = capsys.readouterr().err
    assert 'INVALID_DEPLOYMENT_CONFIG:' + code.split(':', 1)[0] in text
    assert 'private-observation' not in text and '/private/' not in text
    assert code in str(captured[0])
