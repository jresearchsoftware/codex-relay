"""Deployment native causes use existing protected channels; no root I/O."""
import errno
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
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
    monkeypatch.setattr(tempfile, 'mkstemp', lambda **kwargs: (_ for _ in ()).throw(OSError(errno.ENOSPC, 'fixture full')))
    original = PermissionError(errno.EACCES, 'private input unreadable', '/private/input')
    evidence = report_failure(original, 'owner-lifecycle')
    assert evidence['reason'] == 'PRIVATE_LOG_FALLBACK_UNAVAILABLE'
    assert evidence['recorderFailure']['errno'] == 'ENOSPC'
    assert evidence['recorderFailure']['previous']['errno'] == 'ENOENT'
    assert original.errno == errno.EACCES
    public = capsys.readouterr().err
    assert 'private input' not in public and '/private/input' not in public


def test_embedded_reporter_reports_independent_unavailability_when_all_host_storage_fails(monkeypatch, capsys):
    monkeypatch.setattr(os, 'geteuid', lambda: 1234)
    monkeypatch.setattr(tempfile, 'mkstemp', lambda **kwargs: (_ for _ in ()).throw(OSError(errno.EACCES, 'fixture unavailable')))
    namespace = {}
    exec(compile(failure_reporting_source(), '<frozen-reporter-fixture>', 'exec'), namespace)
    result = namespace['report_failure'](OSError('native cause retained in-process'), 'pre-configuration')
    assert result['status'] == 'unavailable' and result['reason'] == 'PRIVATE_LOG_FALLBACK_UNAVAILABLE'
    assert result['recorderFailure']['errno'] == 'EACCES'
    assert 'PRIVATE_LOG_FALLBACK_UNAVAILABLE' in capsys.readouterr().err


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


def test_unprivileged_owned_private_log_is_durable_without_host_journal(tmp_path, capsys):
    log = tmp_path / 'failure.log'
    log.touch(mode=0o600)
    result = report_failure(ValueError('original owner-controller startup failure'),
                            'ansible-controller', private_log=log)
    assert result['status'] == 'stored'
    assert 'original owner-controller startup failure' in log.read_text()
    assert 'startup failure' not in capsys.readouterr().err


def test_exception_formatter_failure_does_not_destroy_original_type(tmp_path):
    class BrokenMessage(Exception):
        def __str__(self):
            raise ValueError('private formatter failure')
    log = tmp_path / 'failure.log'
    log.touch(mode=0o600)
    report_failure(BrokenMessage(), 'unexpected-exception', private_log=log)
    payload = json.loads(log.read_text().split('=', 1)[1])
    assert payload['causes'][0]['type'] == 'BrokenMessage'
    assert payload['causes'][0]['message'] == '[message unavailable: ValueError]'
    assert 'private formatter failure' not in log.read_text()


def test_stream_publication_failure_uses_independent_descriptor_without_masking_cause(tmp_path, monkeypatch):
    log = tmp_path / 'failure.log'; log.touch(mode=0o600)
    class BrokenStream:
        def write(self, value):
            raise OSError('cannot publish diagnostic summary')
    monkeypatch.setattr(sys, 'stderr', BrokenStream())
    published = []
    monkeypatch.setattr(os, 'write', lambda fd, value: published.append((fd, value)))
    result = report_failure(ValueError('original controller failure'), 'publication', private_log=log)
    assert result['status'] == 'stored' and 'original controller failure' in log.read_text()
    assert published and published[0][0] == 2
    assert b'original controller failure' not in published[0][1]


def test_preconfiguration_without_journal_reuses_durable_private_log(tmp_path, monkeypatch, capsys):
    original = tempfile.mkstemp
    created = []
    def local_log(**options):
        fd, path = original(dir=tmp_path, **options)
        created.append(path)
        return fd, path
    monkeypatch.setattr(tempfile, 'mkstemp', local_log)
    monkeypatch.setattr(os, 'geteuid', lambda: 1234)
    result = report_failure(ValueError('original preconfiguration failure password=private-value'), 'pre-configuration')
    assert result['status'] == 'stored' and result['destination'] == 'existing-private-deployment-log'
    log = Path(created[0])
    assert log.stat().st_mode & 0o777 == 0o600
    assert result['reference'] == 'protected-log/' + log.name
    assert 'original preconfiguration failure' in log.read_text()
    assert 'private-value' not in log.read_text() and str(tmp_path) not in capsys.readouterr().err


@pytest.mark.parametrize('fragment', ['synthetic-native-credential-pre', 'prefix-and-rest'])
def test_timeout_redacts_known_partial_credential_at_capture_edge(tmp_path, monkeypatch, fragment):
    secret = 'synthetic-native-credential-prefix-and-rest'
    monkeypatch.setenv('FIXTURE_ACCESS_TOKEN', secret)
    log = tmp_path / 'private.log'; log.touch(mode=0o600)
    text = 'upstream failed ' + fragment if fragment.startswith('synthetic') else fragment
    report_failure(subprocess.TimeoutExpired('fixed-child', 2, stderr=text), 'child-timeout', private_log=log)
    assert fragment not in log.read_text() and '[REDACTED PARTIAL]' in log.read_text()


def test_bounded_middle_capture_redacts_credential_at_both_omission_edges(tmp_path, monkeypatch):
    monkeypatch.setenv('FIXTURE_ACCESS_TOKEN', 'synthetic-native-credential-prefix-and-rest')
    log = tmp_path / 'private.log'; log.touch(mode=0o600)
    error = subprocess.CalledProcessError(7, 'fixed-child',
        stderr='first error synthetic-native-credential-pre\n[bounded child capture: middle omitted]\nprefix-and-rest')
    error.capture_bytes = {'stderr': 999999}
    report_failure(error, 'bounded-child', private_log=log)
    text = log.read_text()
    assert 'first error' in text and 'synthetic-native' not in text and 'prefix-and-rest' not in text
    assert json.loads(text.split('=', 1)[1])['causes'][0]['stderrTruncated']


def test_durable_record_preserves_first_and_last_actionable_child_output(tmp_path):
    log = tmp_path / 'private.log'; log.touch(mode=0o600)
    error = subprocess.CalledProcessError(7, 'fixed-build-child',
        stderr='FIRST_ERROR_E111\n' + 'x' * 300000 + '\nACTUAL_NATIVE_FAILURE_E999')
    report_failure(error, 'build-child', private_log=log)
    payload = json.loads(log.read_text().split('=', 1)[1])
    cause = payload['causes'][0]
    assert cause['stderr'].startswith('FIRST_ERROR_E111')
    assert cause['stderr'].endswith('ACTUAL_NATIVE_FAILURE_E999')
    assert len(cause['stderr']) == 8192 and cause['stderrTruncated']
    assert cause['stderrBytes'] == len(error.stderr)


def test_omission_marker_keeps_redaction_active_when_rendered_capture_exceeds_original_size(tmp_path, monkeypatch):
    # Original count exceeds capture limit by one byte; the separator is larger
    # than the omitted region. Byte-size comparison alone cannot prove complete.
    secret = 'synthetic-native-value-' + 'z' * 127950 + '-credential-end'
    monkeypatch.setenv('FIXTURE_ACCESS_TOKEN', secret)
    original = 'x' * 131070 + secret + 'y' * (262145 - 131070 - len(secret))
    retained = original[:131072] + '\n[bounded child capture: middle omitted]\n' + original[-131072:]
    assert len(retained) > len(original)
    error = subprocess.CalledProcessError(7, 'fixed-child', stderr=retained)
    error.capture_bytes = {'stderr': len(original)}
    log = tmp_path / 'private.log'; log.touch(mode=0o600)
    report_failure(error, 'bounded-edge', private_log=log)
    text = log.read_text()
    cause = json.loads(text.split('=', 1)[1])['causes'][0]
    assert cause['stderrTruncated'] and cause['stderrAvailability'] == 'redacted'
    assert 'z' * 128 not in text and '-credential-end' not in text
