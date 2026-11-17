"""Deployment native causes use existing protected channels; no root I/O."""
import errno
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lifecycle import report_failure, failure_reporting_source, public_log_reference
from host_preflight import require_probe, HostPreflightError


def causal_error():
    try:
        try:
            raise subprocess.CalledProcessError(7, ['fixed-helper'], stderr=b'loader: missing libssl.so\n{"access_token":"opaque-fixture"}\nAuthorization: Basic opaque-basic-fixture\n{"password":"two word credential"}\n')
        except subprocess.CalledProcessError as child:
            raise RuntimeError('HOST_PROBE_FAILED password=private-fixture') from child
    except RuntimeError as error:
        return error


def test_existing_journal_keeps_redacted_messages_stack_and_child_cause_without_public_leak(monkeypatch, capsys):
    monkeypatch.setattr(os, 'geteuid', lambda: 0)
    monkeypatch.setattr(os, 'getuid', lambda: 0)
    original_stat = os.stat
    monkeypatch.setattr(os, 'stat', lambda path, *args, **kwargs: SimpleNamespace(st_mode=stat.S_IFSOCK, st_uid=0)
        if path == '/run/systemd/journal/socket' else original_stat(path, *args, **kwargs))
    captured = []
    def logger(argv, **kwargs):
        captured.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, '', '')
    monkeypatch.setattr(subprocess, 'run', logger)
    error = causal_error()
    error.observation = {'mode': {'expected': 420, 'observed': 436}}
    error.__cause__.stderr += b"password='single quoted credential value'\n"
    evidence = report_failure(error, 'host-preflight')
    assert evidence['status'] == 'submitted' and evidence['destination'] == 'existing-host-journal'
    argv, request = captured[0]
    assert argv == ['/usr/bin/logger', '--journald']
    payload = json.loads(request['input'].split('MESSAGE=', 1)[1])
    assert payload['causes'][1]['exit'] == 7
    assert payload['causes'][0]['observation'] == {'mode': {'expected': 420, 'observed': 436}}
    assert 'loader: missing libssl.so' in payload['causes'][1]['stderr']
    assert 'CalledProcessError' in payload['stack']
    assert 'private-fixture' not in request['input'] and 'opaque-fixture' not in request['input']
    assert 'opaque-basic-fixture' not in request['input'] and 'two word credential' not in request['input']
    assert 'single quoted credential value' not in request['input']
    public = capsys.readouterr().err
    assert 'existing-host-journal' in public and 'libssl.so' not in public and 'HOST_PROBE_FAILED' not in public


def test_missing_recorder_preserves_original_errno_and_reports_independent_unavailability(monkeypatch, capsys):
    monkeypatch.setattr(os, 'geteuid', lambda: 0)
    monkeypatch.setattr(os, 'getuid', lambda: 0)
    original_stat = os.stat
    def absent(path, *args, **kwargs):
        if path == '/run/systemd/journal/socket':
            raise FileNotFoundError(errno.ENOENT, 'journal absent')
        return original_stat(path, *args, **kwargs)
    monkeypatch.setattr(os, 'stat', absent)
    original = PermissionError(errno.EACCES, 'private input unreadable', '/private/input')
    evidence = report_failure(original, 'owner-lifecycle')
    assert evidence['reason'] == 'HOST_JOURNAL_UNAVAILABLE'
    assert evidence['recorderFailure']['errno'] == 'ENOENT'
    assert original.errno == errno.EACCES
    public = capsys.readouterr().err
    assert 'private input' not in public and '/private/input' not in public


def test_embedded_reporter_runs_unprivileged_without_inventing_a_store_or_privilege(monkeypatch, capsys):
    monkeypatch.setattr(os, 'geteuid', lambda: 1234)
    namespace = {}
    exec(compile(failure_reporting_source(), '<frozen-reporter-fixture>', 'exec'), namespace)
    result = namespace['report_failure'](OSError('native cause retained in-process'), 'pre-configuration')
    assert result == {'phase': 'pre-configuration', 'status': 'unavailable', 'reason': 'NO_CONFIGURED_HOST_STORE'}
    assert 'NO_CONFIGURED_HOST_STORE' in capsys.readouterr().err


def test_host_probe_keeps_classification_and_the_original_actionable_child_stderr():
    child = subprocess.CompletedProcess(['fixed-host-probe'], 7, b'API failure body', b'loader: missing libssl.so')
    with pytest.raises(HostPreflightError) as caught:
        require_probe(child, False, 'HOST_TLS_MATERIAL_INVALID', 'tls-material')
    assert str(caught.value) == 'HOST_TLS_MATERIAL_INVALID'
    assert caught.value.__cause__.returncode == 7
    assert caught.value.__cause__.stderr == b'loader: missing libssl.so'


def test_public_log_reference_never_exposes_a_host_location():
    reference = public_log_reference('/var/log/private-host/owner-lifecycle/relay-aaaaaaaaaaaa-apply-random88.log')
    assert reference == 'protected-log/relay-aaaaaaaaaaaa-apply-random88.log'
    assert public_log_reference('/var/log/private-host/sensitive-configuration') == 'protected-deployment-log'


def test_fsync_failure_falls_back_to_journal_and_retains_the_primary_cause(tmp_path, monkeypatch, capsys):
    log = tmp_path / 'existing-private.log'
    log.write_text('')
    log.chmod(0o600)
    monkeypatch.setattr(os, 'geteuid', lambda: 0)
    monkeypatch.setattr(os, 'getuid', lambda: 0)
    real_fstat, real_stat = os.fstat, os.stat
    def root_metadata(fd):
        fields = list(real_fstat(fd)); fields[4] = fields[5] = 0
        return os.stat_result(fields)
    monkeypatch.setattr(os, 'fstat', root_metadata)
    monkeypatch.setattr(os, 'stat', lambda path, *args, **kwargs: SimpleNamespace(st_mode=stat.S_IFSOCK, st_uid=0)
        if path == '/run/systemd/journal/socket' else real_stat(path, *args, **kwargs))
    def failed_sync(fd):
        raise OSError(errno.EIO, 'cannot sync /private/log/location')
    monkeypatch.setattr(os, 'fsync', failed_sync)
    calls = []
    def logger(argv, **kwargs):
        calls.append(kwargs['input'])
        return subprocess.CompletedProcess(argv, 0, '', '')
    monkeypatch.setattr(subprocess, 'run', logger)
    result = report_failure(ValueError('original-operation-failure'), 'installer', private_log=log)
    assert result['destination'] == 'existing-host-journal' and result['status'] == 'submitted'
    assert result['recorderFailure']['errno'] == 'EIO'
    assert 'cannot sync /private/log/location' in calls[0]
    assert 'original-operation-failure' in calls[0]
    assert '/private/log/location' not in capsys.readouterr().err


def test_known_credential_is_redacted_before_clipping_the_causal_message(monkeypatch):
    monkeypatch.setattr(os, 'geteuid', lambda: 0)
    monkeypatch.setattr(os, 'getuid', lambda: 0)
    secret = 'synthetic-sensitive-value-across-boundary' + 'z' * 40000
    monkeypatch.setenv('FIXTURE_ACCESS_TOKEN', secret)
    real_stat = os.stat
    monkeypatch.setattr(os, 'stat', lambda path, *args, **kwargs: SimpleNamespace(st_mode=stat.S_IFSOCK, st_uid=0)
        if path == '/run/systemd/journal/socket' else real_stat(path, *args, **kwargs))
    calls = []
    def logger(argv, **kwargs):
        calls.append(kwargs['input'])
        return subprocess.CompletedProcess(argv, 0, '', '')
    monkeypatch.setattr(subprocess, 'run', logger)
    report_failure(ValueError('x' * 32700 + secret), 'installer')
    assert secret not in calls[0] and 'synthetic-sensitive-value' not in calls[0]


@pytest.mark.parametrize('channel', ['stdout', 'stderr'])
def test_timeout_retains_partial_output_counts_redaction_and_capture_state(monkeypatch, channel):
    monkeypatch.setattr(os, 'geteuid', lambda: 0)
    monkeypatch.setattr(os, 'getuid', lambda: 0)
    original_stat = os.stat
    monkeypatch.setattr(os, 'stat', lambda path, *args, **kwargs: SimpleNamespace(st_mode=stat.S_IFSOCK, st_uid=0)
        if path == '/run/systemd/journal/socket' else original_stat(path, *args, **kwargs))
    captured = []
    def logger(argv, **kwargs):
        captured.append(kwargs['input'])
        return subprocess.CompletedProcess(argv, 0, '', '')
    monkeypatch.setattr(subprocess, 'run', logger)
    partial = b'original loader failure\npassword=private-timeout-value\n' + b'x' * 10000
    error = subprocess.TimeoutExpired('fixed-child', 12, **{'output' if channel == 'stdout' else channel: partial})
    report_failure(error, 'source-preparation')
    cause = json.loads(captured[0].split('MESSAGE=', 1)[1])['causes'][0]
    assert cause['timeoutSeconds'] == 12
    assert cause[channel + 'Bytes'] == len(partial)
    assert cause[channel + 'Truncated']
    assert cause[channel + 'Availability'] == 'redacted'
    assert cause[('stderr' if channel == 'stdout' else 'stdout') + 'Availability'] == 'unavailable'
    assert 'original loader failure' in cause[channel]
    assert 'private-timeout-value' not in captured[0]
