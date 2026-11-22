"""Fault injection through the owner/CLI entrypoints without an installed host."""
import errno
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
import git_intent
import lifecycle
import owner_lifecycle
import repository_source

REVISION = 'a' * 40
SECRET = 'opaque-private-fixture-value'


class NativeResponses:
    def __init__(self, monkeypatch, responses):
        self.responses = iter(responses)
        self.calls = []
        self.waits = []
        self.closed = 0
        monkeypatch.setattr(git_intent.http.client, 'HTTPSConnection', lambda host, **_: self)
        monkeypatch.setattr(git_intent.time, 'sleep', self.waits.append)
        monkeypatch.setattr(git_intent.random, 'uniform', lambda *_: .25)

    def request(self, method, _url, **_kwargs):
        self.calls.append(method)

    def getresponse(self):
        item = next(self.responses)
        if isinstance(item, BaseException):
            raise item
        status, headers, body = item
        return SimpleNamespace(status=status, getheader=headers.get, read=lambda limit: body[:limit])

    def close(self):
        self.closed += 1


def owner_apply(monkeypatch, operation):
    def run(_request):
        lifecycle.observe_failure_state(phase='apply', requested=REVISION, run='281')
        operation()
    monkeypatch.setattr(owner_lifecycle, 'run', run)
    monkeypatch.setattr(owner_lifecycle, 'report_failure', lambda *_: {'status': 'unavailable'})
    return owner_lifecycle.main(['fixture'])


def test_owner_apply_read_recovery_keeps_original_invocation(monkeypatch, capsys):
    good = json.dumps({'ref': 'refs/heads/main', 'object': {'type': 'commit', 'sha': REVISION}}).encode()
    transport = NativeResponses(monkeypatch, [(504, {}, SECRET.encode()), (200, {}, good)])
    applies = []
    def operation():
        assert owner_lifecycle.public_main('example/repository') == REVISION
        applies.append(REVISION)
    assert owner_apply(monkeypatch, operation) == 0
    assert applies == [REVISION]
    assert transport.calls == ['GET', 'GET']
    assert transport.waits == [.25]
    assert capsys.readouterr().err == ''


@pytest.mark.parametrize('response, count, first, stopped, next_action', [
    ((504, {}, SECRET.encode()), 3, 'HTTP 504', 'read attempt limit', 'host can read the selected GitHub repository'),
    (TimeoutError(SECRET), 3, 'timed out', 'read attempt limit', 'host can read the selected GitHub repository'),
    ((403, {}, SECRET.encode()), 1, 'HTTP 403', 'did not qualify for retry', 'configured read credential'),
    ((429, {'Retry-After': '120'}, SECRET.encode()), 1, 'HTTP 429', 'provider-directed wait exceeded', 'GitHub rate-limit reset'),
])
def test_owner_apply_final_text_preserves_ordinary_http_cause(monkeypatch, capsys, response, count, first, stopped, next_action):
    transport = NativeResponses(monkeypatch, [response] * count)
    assert owner_apply(monkeypatch, lambda: owner_lifecycle.public_main('example/repository')) == 1
    public = capsys.readouterr().err
    assert 'Owner Relay lifecycle apply failed (Actions run 281)' in public
    assert 'GitHub GET (Git refs or objects)' in public and first in public
    assert f'{count} request attempt' in public and stopped in public
    assert 'did not enter a target installation or activation mutation' in public
    assert 'Protected evidence retention could not be verified' in public
    assert next_action in public and SECRET not in public
    assert transport.calls == ['GET'] * count and transport.closed == count
    assert len(transport.waits) == count - 1


def test_provider_retry_after_and_primary_reset_are_honored(monkeypatch):
    now = 1000
    monkeypatch.setattr(git_intent.time, 'time', lambda: now)
    transport = NativeResponses(monkeypatch, [
        (403, {'Retry-After': '1', 'X-RateLimit-Remaining': '0', 'X-RateLimit-Reset': '1003'}, b'{}'),
        (200, {}, b'{}')
    ])
    assert git_intent.github_api('/repos/example/repository') == {}
    assert transport.calls == ['GET', 'GET']
    assert transport.waits == [3.25]


def test_source_token_write_is_not_repeated_after_lost_response(monkeypatch):
    transport = NativeResponses(monkeypatch, [(504, {'Retry-After': '2'}, SECRET.encode())])
    with pytest.raises(repository_source.APIError) as caught:
        repository_source.github_api('POST', '/app/installations/1/access_tokens')
    assert caught.value.status == 504
    assert caught.value.__cause__.observation['stopped'] == 'mutation'
    assert transport.calls == ['POST'] and transport.waits == []


def test_failed_backend_reports_exit_and_unverified_lifecycle_at_real_cli_boundary(monkeypatch, tmp_path, capsys):
    definition = importlib.util.spec_from_file_location('relay_deploy', ROOT / 'deploy/relay-deploy.py')
    cli = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(cli)
    log_path = tmp_path / 'relay-aaaaaaaaaaaa-apply-fixture.log'
    monkeypatch.setattr(cli, 'arguments', lambda: SimpleNamespace(phase='apply'))
    monkeypatch.setattr(cli, 'report_failure', lambda *_args, **_kwargs: {'status': 'unavailable'})
    calls = []
    def run(_args):
        calls.append('apply')
        lifecycle.observe_failure_state(requested=REVISION, log=lifecycle.public_log_reference(log_path))
        lifecycle.observe_admission_result('quiesce')
        lifecycle.observe_admission_result('drain')
        with log_path.open('w') as log:
            code = cli.run_backend([sys.executable, '-c',
                f'import sys; print("TASK [relay_controller : private message] ***"); print("{SECRET}"); sys.exit(7)'],
                tmp_path, None, log)
        assert code == 7
        raise RuntimeError('BACKEND_FAILED')
    monkeypatch.setattr(cli, 'run', run)
    assert cli.main() == 1
    output = capsys.readouterr()
    assert 'Relay deployment apply failed. Last verified boundary was backend exit.' in output.err
    assert 'Ansible exited with code 7 while reporting controller-entrypoints' in output.err
    assert '1 backend invocation started' in output.err
    assert 'The installed product is unverified' in output.err
    assert 'Runtime activation is unverified' in output.err
    assert 'gate state was closed' in output.err
    assert 'protected-log/relay-aaaaaaaaaaaa-apply-fixture.log' in output.err
    assert 'Run the supported read-only deployment diagnostic' in output.err
    assert SECRET in log_path.read_text() and SECRET not in output.err + output.out
    assert str(tmp_path) not in output.err and calls == ['apply']


def test_verified_installation_and_unknown_resume_effect_stay_separate(monkeypatch, capsys):
    actions = []
    def operation():
        def gate(action, *_args):
            actions.append(action)
            if action == 'resume':
                raise PermissionError(errno.EACCES, SECRET)
            if action == 'phase' and 'recovery-required' in _args:
                raise RuntimeError('later recovery write failed')
        lifecycle.execute(gate, REVISION, lambda: True, lambda *_: True)
    monkeypatch.setattr(lifecycle, 'report_failure', lambda *_args, **_kwargs: {'status': 'unavailable'})
    assert owner_apply(monkeypatch, operation) == 1
    public = capsys.readouterr().err
    assert f'Last verified installed product was {REVISION}' in public
    assert 'Runtime activation was verified' in public
    assert 'Admission state is unverified' in public
    assert 'operating system reported EACCES' in public
    assert 'recovery-state-write-unproven' in public
    assert actions.count('resume') == 1 and SECRET not in public


def test_terminal_recorder_exception_does_not_replace_the_primary_os_cause(monkeypatch, capsys):
    def fail(_request):
        raise PermissionError(errno.EACCES, SECRET)
    def unavailable(*_args):
        raise OSError(errno.ENOSPC, 'secondary private failure')
    monkeypatch.setattr(owner_lifecycle, 'run', fail)
    monkeypatch.setattr(owner_lifecycle, 'report_failure', unavailable)
    assert owner_lifecycle.main(['fixture']) == 1
    public = capsys.readouterr().err
    assert 'EACCES' in public and 'Protected evidence retention could not be verified' in public
    assert SECRET not in public and 'secondary private' not in public


def test_owner_apply_names_drain_failure_and_safe_counts_from_the_gate_receipt(monkeypatch, capsys):
    def operation():
        def gate(action, *_args):
            if action == 'drain':
                child = subprocess.CalledProcessError(1, ['fixed-gate'], stderr=SECRET + '\n' + json.dumps({
                    'code': 'ADMISSION_DRAIN_TIMEOUT', 'drain': {'seconds': 45, 'active': 2, 'unknown': 1},
                    'details': {'private': SECRET}
                }))
                child.deployment_dependency = 'admission-gate'
                raise child
        lifecycle.execute(gate, REVISION, lambda: pytest.fail('Apply must not start'), lambda *_: False)
    assert owner_apply(monkeypatch, operation) == 1
    public = capsys.readouterr().err
    assert 'Last verified boundary was closed admission' in public
    assert 'Admission gate reported ADMISSION_DRAIN_TIMEOUT' in public
    assert 'The drain budget was 45 seconds' in public
    assert '2 active and 1 unresolved attempts' in public
    assert 'read relay-admission status for the retained operation' in public
    assert SECRET not in public
