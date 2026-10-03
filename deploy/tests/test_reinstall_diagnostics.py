"""Execute the remote wrapper locally to qualify its diagnostic transport."""
import json
from pathlib import Path
import shlex
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
import clean_reinstall as reinstall

DEFAULT_HINT = 'inspect-retained-operation-and-reinstall-evidence'
TARGET = 'b' * 40
WARNING_SUFFIX = (';review-unit-provenance-and-writers;current-content-unrelated;'
                  'content-and-group-membership-can-change-after-inspection')
WARNING = {'unit': '/etc/systemd/system/synthetic-unrelated.service',
           'inspectedPath': '/usr/lib/systemd/system/synthetic-unrelated.service',
           'uid': 0, 'gid': 1000, 'mode': '0664', 'groupWriters': [1000],
           'groupLookup': 'listed-other-writers'}


def success_result(action):
    if action == 'decommission':
        return {'state': 'DECOMMISSIONED', 'sourceRevision': 'a' * 40,
                'targetRevision': TARGET,
                'recoveryPath': '/var/lib/codex-relay-clean-reinstall.json',
                'journalSha256': 'c' * 64}
    return {'state': 'COMPLETE', 'installedRevision': TARGET,
            'archive': '/opt/.codex-relay-retired-' + 'a' * 40 + '-' + TARGET}


def warning_line(warning):
    return 'REINSTALL_FOREIGN_UNIT_WARNING;' + json.dumps(warning, sort_keys=True) + WARNING_SUFFIX


@pytest.fixture
def local_remote(monkeypatch):
    """Replace SSH and lifecycle actions, retaining generated wrapper handling."""
    read_text = Path.read_text
    popen = subprocess.Popen
    calls = []

    def source(path, *args, **kwargs):
        content = read_text(path, *args, **kwargs)
        if path == Path(reinstall.__file__):
            content += '''
def diagnostic_action(config, *args):
    if config.get('testWarning') is not None:
        emit_foreign_unit_warning(config['testWarning'])
    if config.get('testRawStderr') is not None:
        import sys
        print(config['testRawStderr'], file=sys.stderr)
        if config.get('testRawExit'):
            raise SystemExit(1)
    error = config.get('testError')
    if error is not None:
        kinds = {name: value for name, value in [
            ('ValueError', ValueError), ('OSError', OSError),
            ('KeyError', KeyError), ('TypeError', TypeError),
            ('AttributeError', AttributeError)]}
        raise kinds[config['testErrorType']](error)
    return config['testResult']
decommission = complete = diagnostic_action
'''
        elif path == Path(reinstall.__file__).with_name('inventory.py'):
            content += '\ndef inspect(config):\n    return {}\n'
        return content

    def local_popen(command, **kwargs):
        assert command[:9] == ['ssh', '-o', 'BatchMode=yes', '-o',
                               'StrictHostKeyChecking=yes', '-o',
                               'IdentitiesOnly=yes', '-i', '/synthetic/ssh-key']
        assert command[9] == 'synthetic@host.invalid'
        python = shlex.split(command[10])
        assert python[:3] == ['/usr/bin/python3', '-I', '-c']
        calls.append(command)
        return popen([sys.executable, '-I', '-c', python[3]], **kwargs)

    monkeypatch.setattr(Path, 'read_text', source)
    monkeypatch.setattr(reinstall.subprocess, 'Popen', local_popen)

    def invoke(*, action, error=None, error_type='ValueError', result=None,
               warning=None, raw_stderr=None, raw_exit=False):
        config = {'environment': {'namespace': 'codex-relay'},
                  'testError': error, 'testErrorType': error_type,
                  'testResult': result, 'testWarning': warning,
                  'testRawStderr': raw_stderr, 'testRawExit': raw_exit}
        report = {'installed': {'status': 'present', 'revision': 'a' * 40}}
        try:
            return reinstall.remote_action({'user': 'synthetic', 'host': 'host.invalid'},
                                           '/synthetic/ssh-key', config, TARGET, report,
                                           action=action)
        finally:
            assert len(calls) == 1

    return invoke


@pytest.mark.parametrize('action', ['decommission', 'complete'])
@pytest.mark.parametrize('diagnostic', [
    'REINSTALL_UNKNOWN_UNIT_UNCLASSIFIABLE;inspect-top-level-systemd-service-links',
    'REINSTALL_HOST_LOCK_LOST;inspect-before-retry',
    'REINSTALL_SERVICE_TRANSITION_FAILED;' + DEFAULT_HINT,
])
def test_remote_wrapper_preserves_exact_actionable_diagnostic(local_remote, action, diagnostic):
    with pytest.raises(ValueError) as error:
        local_remote(action=action, error=diagnostic)
    assert str(error.value) == diagnostic


@pytest.mark.parametrize('action', ['decommission', 'complete'])
def test_code_only_diagnostic_retains_code_and_adds_recovery_hint(local_remote, action):
    with pytest.raises(ValueError) as error:
        local_remote(action=action, error='REINSTALL_SERVICE_TRANSITION_FAILED')
    assert str(error.value) == 'REINSTALL_SERVICE_TRANSITION_FAILED;' + DEFAULT_HINT


@pytest.mark.parametrize('action', ['decommission', 'complete'])
@pytest.mark.parametrize('error_type', ['ValueError', 'OSError', 'KeyError', 'TypeError',
                                       'AttributeError'])
def test_remote_wrapper_sanitizes_unexpected_exception_text(local_remote, action, error_type):
    with pytest.raises(ValueError) as error:
        local_remote(action=action, error_type=error_type,
                     error='/synthetic/protected/path synthetic-sensitive-value')
    assert str(error.value) == 'REINSTALL_BLOCKED;' + DEFAULT_HINT


@pytest.mark.parametrize('diagnostic', [
    'REINSTALL_UNSAFE_PATH;/synthetic/protected/path',
    'REINSTALL_UNSAFE_PATH;inspect-before-retry;synthetic-sensitive-value',
    'REINSTALL_UNSAFE_PATH;inspect-before-retry\nsynthetic-sensitive-value',
    'REINSTALL_UNSAFE_PATH;synthetic-sensitive-value=unexpected',
    'REINSTALL_UNSAFE_PATH;synthetic-sensitive-value',
    'REINSTALL_UNSAFE_PATH;inspect before retry',
])
def test_remote_wrapper_rejects_unsafe_diagnostic_hints(local_remote, diagnostic):
    with pytest.raises(ValueError) as error:
        local_remote(action='complete', error=diagnostic)
    assert str(error.value) == 'REINSTALL_BLOCKED;' + DEFAULT_HINT


@pytest.mark.parametrize('action', ['decommission', 'complete'])
def test_remote_wrapper_preserves_valid_success_result(local_remote, action):
    result = success_result(action)
    assert local_remote(action=action, result=result) == result


@pytest.mark.parametrize('action', ['decommission', 'complete'])
@pytest.mark.parametrize('fails', [False, True])
def test_safe_foreign_unit_warning_survives_success_and_actionable_failure(
        local_remote, capsys, action, fails):
    diagnostic = 'REINSTALL_UNKNOWN_UNIT_UNCLASSIFIABLE;inspect-top-level-systemd-service-links'
    if fails:
        with pytest.raises(ValueError) as error:
            local_remote(action=action, warning=WARNING, error=diagnostic)
        assert str(error.value) == diagnostic
    else:
        result = success_result(action)
        assert local_remote(action=action, warning=WARNING, result=result) == result
    captured = capsys.readouterr()
    assert captured.out == ''
    assert captured.err == warning_line(WARNING) + '\n'


@pytest.mark.parametrize('group_lookup', [
    'not-group-writable', 'no-other-listed-account', 'group-unavailable'])
def test_warning_forwards_supported_group_observation_states(local_remote, capsys, group_lookup):
    warning = dict(WARNING, groupLookup=group_lookup, groupWriters=[],
                   mode='0644' if group_lookup == 'not-group-writable' else '0664')
    result = success_result('complete')
    assert local_remote(action='complete', warning=warning, result=result) == result
    assert capsys.readouterr().err == warning_line(warning) + '\n'


def test_warning_with_printable_unicode_and_semicolon_unit_name(local_remote, capsys):
    warning = dict(WARNING, unit='/etc/systemd/system/synthetic-ž;unit.service',
                   inspectedPath='/usr/lib/systemd/system/synthetic-ž;unit.service')
    result = success_result('complete')
    assert local_remote(action='complete', warning=warning, result=result) == result
    assert capsys.readouterr().err == warning_line(warning) + '\n'


def test_warning_with_protected_nested_inspected_unit_path(local_remote, capsys):
    warning = dict(WARNING, inspectedPath='/usr/lib/systemd/system/synthetic/synthetic-unrelated.service')
    result = success_result('complete')
    assert local_remote(action='complete', warning=warning, result=result) == result
    assert capsys.readouterr().err == warning_line(warning) + '\n'


def test_valid_warning_survives_sanitized_unexpected_failure(local_remote, capsys):
    with pytest.raises(ValueError) as error:
        local_remote(action='decommission', warning=WARNING, error_type='OSError',
                     error='/synthetic/protected/path synthetic-sensitive-value')
    assert str(error.value) == 'REINSTALL_BLOCKED;' + DEFAULT_HINT
    assert capsys.readouterr().err == warning_line(WARNING) + '\n'


@pytest.mark.parametrize('change', [
    {'unit': '/synthetic/protected/path'},
    {'unit': '/etc/systemd/system/../synthetic.service'},
    {'inspectedPath': '/synthetic/protected/path'},
    {'uid': True},
    {'gid': -1},
    {'mode': '0668'},
    {'groupWriters': ['synthetic-sensitive-value']},
    {'groupWriters': [False]},
    {'groupLookup': 'synthetic-sensitive-value'},
    {'groupLookup': ['group-unavailable']},
    {'unexpected': 'synthetic-sensitive-value'},
])
def test_remote_transport_rejects_malformed_warning_metadata(local_remote, capsys, change):
    malformed = warning_line(dict(WARNING, **change))
    with pytest.raises(ValueError) as error:
        local_remote(action='complete', raw_stderr=malformed,
                     error='REINSTALL_SERVICE_TRANSITION_FAILED')
    assert str(error.value) == 'REINSTALL_SERVICE_TRANSITION_FAILED;' + DEFAULT_HINT
    assert capsys.readouterr().err == ''


def test_remote_transport_rejects_duplicate_warning_fields(local_remote, capsys):
    metadata = json.dumps(WARNING, sort_keys=True).removesuffix('}')
    malformed = ('REINSTALL_FOREIGN_UNIT_WARNING;' + metadata
                 + ', "uid": 1000}' + WARNING_SUFFIX)
    with pytest.raises(ValueError) as error:
        local_remote(action='complete', raw_stderr=malformed,
                     error='REINSTALL_SERVICE_TRANSITION_FAILED')
    assert str(error.value) == 'REINSTALL_SERVICE_TRANSITION_FAILED;' + DEFAULT_HINT
    assert capsys.readouterr().err == ''


def test_valid_warning_survives_rejected_untrusted_stderr(local_remote, capsys):
    with pytest.raises(ValueError) as error:
        local_remote(action='complete', warning=WARNING,
                     raw_stderr='synthetic-sensitive-value',
                     error='REINSTALL_SERVICE_TRANSITION_FAILED')
    assert str(error.value) == 'REINSTALL_SERVICE_TRANSITION_FAILED;' + DEFAULT_HINT
    assert capsys.readouterr().err == warning_line(WARNING) + '\n'


@pytest.mark.parametrize('stderr', [
    'synthetic-sensitive-value',
    'REINSTALL_SERVICE_TRANSITION_FAILED;inspect-before-retry',
    warning_line(WARNING) + ';synthetic-sensitive-value',
])
def test_success_preserves_existing_incidental_stderr_behavior(local_remote, capsys, stderr):
    result = success_result('complete')
    assert local_remote(action='complete', raw_stderr=stderr, result=result) == result
    assert capsys.readouterr().err == ''


def test_ssh_banner_and_warning_preserve_exact_actionable_failure(local_remote, capsys):
    diagnostic = 'REINSTALL_UNKNOWN_UNIT_UNCLASSIFIABLE;inspect-top-level-systemd-service-links'
    stderr = 'Synthetic SSH legal banner\n' + warning_line(WARNING)
    with pytest.raises(ValueError) as error:
        local_remote(action='decommission', raw_stderr=stderr, error=diagnostic)
    assert str(error.value) == diagnostic
    assert capsys.readouterr().err == warning_line(WARNING) + '\n'


def test_duplicate_terminal_diagnostics_remain_ambiguous(local_remote, capsys):
    with pytest.raises(ValueError) as error:
        local_remote(action='complete', raw_stderr='REINSTALL_UNSAFE_PATH;inspect-before-retry',
                     error='REINSTALL_SERVICE_TRANSITION_FAILED')
    assert str(error.value) == 'REINSTALL_REMOTE_ACTION_FAILED;' + DEFAULT_HINT
    assert capsys.readouterr().err == ''


@pytest.mark.parametrize('stderr', [
    '', 'synthetic-sensitive-value',
    'REINSTALL_UNSAFE_PATH;/synthetic/protected/path',
    'REINSTALL_UNSAFE_PATH;inspect-before-retry\nsynthetic-sensitive-value',
])
def test_missing_or_malformed_terminal_diagnostic_is_sanitized(local_remote, capsys, stderr):
    with pytest.raises(ValueError) as error:
        local_remote(action='complete', raw_stderr=stderr, raw_exit=True)
    assert str(error.value) == 'REINSTALL_REMOTE_ACTION_FAILED;' + DEFAULT_HINT
    assert capsys.readouterr().err == ''
