"""Live lifecycle evidence uses local child fixtures and never host authority."""
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import threading
from types import SimpleNamespace

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
