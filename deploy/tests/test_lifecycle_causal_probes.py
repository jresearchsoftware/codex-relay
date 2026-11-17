"""Native probe failures keep their original cause behind fixed public codes."""
import json
import importlib.util
import os
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import clean_reinstall
import installed_state
import lifecycle
import managed_pool
import pool_authorization
import partial_install_recovery
import serial_pool_installation
from test_managed_pool import inputs


@pytest.mark.parametrize('surface', ['systemctl', 'retained-reader', 'namespace-probe'])
def test_probe_failure_preserves_native_stderr_and_fixed_public_code(tmp_path, monkeypatch, surface):
    result = subprocess.CompletedProcess(['synthetic-probe'], 7, b'', b'native probe EACCES; token=private-fixture-value')
    if surface == 'systemctl':
        invoke = lambda: clean_reinstall.checked_systemctl(lambda *_args, **_kwargs: result, 'stop', 'synthetic.service')
        code = 'REINSTALL_SERVICE_TRANSITION_FAILED'
    elif surface == 'retained-reader':
        def execute(*_args, **kwargs):
            assert kwargs['stderr'] == subprocess.PIPE
            return result
        monkeypatch.setattr(serial_pool_installation.subprocess, 'run', execute)
        invoke = lambda: serial_pool_installation._node('/synthetic', '/synthetic/config.json', 'throw Error()')
        code = 'MANAGED_POOL_SERIAL_TRANSITION_ORIGINAL_READER_UNPROVEN'
    else:
        catalogue = {'schemaVersion': 1, 'recipeSha256': installed_state.RECIPE_SHA256,
                     'coverage': {'routeCount': 32}, 'requiredLiveChecks': [],
                     'entries': [], 'entryOwners': [],
                     'probes': [{'argv': ['synthetic-probe'], 'stdout': ''}] * 32}
        invoke = lambda: installed_state.audit_catalogue(catalogue, execute=lambda _argv: result, live_checks={})
        code = 'INSTALLED_NATIVE_PROBE_FAILED'
    with pytest.raises((ValueError, managed_pool.PoolError)) as caught:
        invoke()
    error = caught.value
    assert str(error) == code
    assert isinstance(error.__cause__, subprocess.CalledProcessError)
    assert error.__cause__.stderr == result.stderr
    assert 'native probe' not in str(error)
    # Restore subprocess.run before exercising the shared protected reporter.
    monkeypatch.undo()
    log = tmp_path / 'private.log'
    log.write_text(''); log.chmod(0o600)
    assert lifecycle.report_failure(error, 'probe-regression', private_log=log)['status'] == 'stored'
    evidence = json.loads(log.read_text().split('=', 1)[1])
    native = next(row for row in evidence['causes'] if row['type'] == 'CalledProcessError')
    assert native['exit'] == 7 and 'native probe EACCES' in native['stderr']
    assert 'private-fixture-value' not in log.read_text()


def test_target_signing_keeps_openssl_cause_without_exposing_key_or_signature(tmp_path, monkeypatch):
    config = inputs(1)
    key = tmp_path / 'synthetic-key'; key.write_text('synthetic-key-bytes'); key.chmod(0o600)
    config['environment']['generalRunner']['poolApp']['privateKeyFile'] = str(key)
    native_fstat = os.fstat
    def protected_stat(fd):
        values = list(native_fstat(fd)); values[4] = 0
        return os.stat_result(values)
    monkeypatch.setattr(pool_authorization.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(pool_authorization.os, 'fstat', protected_stat)
    def sign(*args, **kwargs):
        assert kwargs['stderr'] == subprocess.PIPE
        return subprocess.CompletedProcess(args[0], 1, b'never-retain-signature', b'OpenSSL native decoder failure')
    monkeypatch.setattr(pool_authorization.subprocess, 'run', sign)
    with pytest.raises(managed_pool.PoolError, match='OWNER_APP_SIGNING_FAILED') as caught:
        pool_authorization.installation_authorization(config)
    cause = caught.value.__cause__
    assert isinstance(cause, subprocess.CalledProcessError)
    assert cause.stderr == b'OpenSSL native decoder failure' and cause.stdout is None
    assert 'OpenSSL' not in str(caught.value) and 'synthetic-key' not in str(caught.value)


@pytest.mark.parametrize('kind', ['nonzero', 'timeout', 'invalid-json'])
def test_consumer_publication_keeps_native_cause_with_unchanged_public_diagnostic(tmp_path, kind):
    source = Path(__file__).resolve().parents[1] / 'ansible/scripts/publish_git_consumer.py'
    spec = importlib.util.spec_from_file_location('causal_consumer_publication', source)
    publication = importlib.util.module_from_spec(spec); spec.loader.exec_module(publication)
    script = tmp_path / 'controller.py'
    body = "import sys,time;sys.stderr.write('native consumer cause; token=private-fixture-value');sys.stderr.flush();"
    body += {'nonzero': 'sys.exit(7)', 'timeout': 'time.sleep(10)', 'invalid-json': "print('{invalid')"}[kind]
    script.write_text(body)
    with pytest.raises(publication.ConsumerPublicationError) as caught:
        publication._execute([sys.executable, str(script), 'consumer-transition'], {}, timeout=.5)
    error = caught.value
    assert str(error) == 'CONSUMER_PUBLICATION_CONTROLLER_FAILED'
    assert 'native consumer' not in json.dumps(error.controller_diagnostic)
    cause = error.__cause__
    if kind == 'invalid-json':
        assert isinstance(cause, json.JSONDecodeError)
    else:
        assert isinstance(cause, subprocess.CalledProcessError if kind == 'nonzero' else subprocess.TimeoutExpired)
        assert b'native consumer cause' in cause.stderr


@pytest.mark.parametrize('fetch_failure', [False, True])
def test_partial_recovery_retains_missing_object_cause_only_after_successful_fetch(tmp_path, monkeypatch, fetch_failure):
    accepted = 'a' * 40
    reports = []
    monkeypatch.setattr(lifecycle, 'report_failure', lambda error, phase: reports.append((error, phase)))
    def output(argv, **options):
        assert options['stderr'] == subprocess.PIPE
        return accepted + '\trefs/heads/main\n' if 'ls-remote' in argv else 'false\n'
    def run(argv, **options):
        assert options['stderr'] == subprocess.PIPE
        if 'fetch' in argv and fetch_failure:
            raise subprocess.CalledProcessError(128, argv, stderr=b'native fetch failed')
        return subprocess.CompletedProcess(argv, int('cat-file' in argv), b'', b'native object missing')
    monkeypatch.setattr(partial_install_recovery.subprocess, 'check_output', output)
    monkeypatch.setattr(partial_install_recovery.subprocess, 'run', run)
    binding = {'gitConfigReceipt': {'source_policy': 'accepted-ancestor', 'product_repository': 'example/product'}}
    if fetch_failure:
        with pytest.raises(subprocess.CalledProcessError) as caught:
            partial_install_recovery.accepted_controller(tmp_path, binding, 'b' * 40)
        assert caught.value.stderr == b'native fetch failed' and not reports
    else:
        assert partial_install_recovery.accepted_controller(tmp_path, binding, 'b' * 40)['acceptedMain'] == accepted
        assert len(reports) == 1
        cause, phase = reports[0]
        assert phase == 'partial-install-object-recovered'
        assert cause.stderr == b'native object missing'
        assert cause.observation == {'status': 'recovered', 'recovery': 'authenticated-object-fetch'}


def test_partial_remote_inspection_preserves_transport_failure_evidence(monkeypatch):
    monkeypatch.setattr(partial_install_recovery, 'run_target', lambda *_args, **_kwargs:
        subprocess.CompletedProcess(['fixed-target'], 1, 'native protected output',
            'native transport failure\nPARTIAL_INSTALL_PROOF_UNAVAILABLE\n'))
    with pytest.raises(ValueError, match='^PARTIAL_INSTALL_PROOF_UNAVAILABLE$') as caught:
        partial_install_recovery.remote_inspect({}, None, {}, 'operation', 'revision')
    cause = caught.value.__cause__
    assert isinstance(cause, subprocess.CalledProcessError)
    assert cause.stderr.startswith('native transport failure')
    assert 'native' not in str(caught.value)


def test_consumer_main_retains_safe_failure_when_reporter_acquisition_fails(tmp_path, monkeypatch, capsys):
    source = Path(__file__).resolve().parents[1] / 'ansible/scripts/publish_git_consumer.py'
    spec = importlib.util.spec_from_file_location('causal_consumer_publication_main', source)
    publication = importlib.util.module_from_spec(spec); spec.loader.exec_module(publication)
    monkeypatch.setattr(publication, '__file__', str(tmp_path / 'missing/ansible/scripts/publish_git_consumer.py'))
    monkeypatch.setattr(sys, 'argv', [str(source), *[item for name in
        ('source', 'config-root', 'desired', 'claim-root', 'repository', 'operation', 'revision')
        for item in ('--' + name, 'synthetic')]])
    def fail(**_kwargs):
        raise RuntimeError('native unexpected publication failure; token=private-fixture-value')
    monkeypatch.setattr(publication, 'publish', fail)
    with pytest.raises(SystemExit) as caught:
        publication.main()
    assert caught.value.code == 1
    output = capsys.readouterr()
    assert json.loads(output.out) == {'error_code': 'CONSUMER_PUBLICATION_FAILED'}
    assert 'HOST_REPORTER_UNAVAILABLE' in output.err
    assert 'private-fixture-value' not in output.out + output.err


def test_consumer_main_reports_native_cause_through_its_reviewed_source_sibling(tmp_path, monkeypatch, capsys):
    source = Path(__file__).resolve().parents[1] / 'ansible/scripts/publish_git_consumer.py'
    spec = importlib.util.spec_from_file_location('causal_consumer_publication_report', source)
    publication = importlib.util.module_from_spec(spec); spec.loader.exec_module(publication)
    deploy = tmp_path / 'reviewed-source/deploy'; deploy.mkdir(parents=True)
    log = tmp_path / 'private.log'; log.write_text(''); log.chmod(0o600)
    # Keep the real reporter and actual sibling acquisition; only its permitted
    # existing destination is selected by this isolated fixture.
    (deploy / 'lifecycle.py').write_text(Path(lifecycle.__file__).read_text() +
        '\n_native_report = report_failure\n'
        'def report_failure(error, phase):\n'
        ' return _native_report(error, phase, private_log=' + repr(str(log)) + ')\n')
    monkeypatch.setattr(publication, '__file__', str(deploy / 'ansible/scripts/publish_git_consumer.py'))
    monkeypatch.setattr(sys, 'argv', [str(source), *[item for name in
        ('source', 'config-root', 'desired', 'claim-root', 'repository', 'operation', 'revision')
        for item in ('--' + name, 'synthetic')]])
    def fail(**_kwargs):
        raise publication.ConsumerPublicationError('CONSUMER_PUBLICATION_CONTROLLER_FAILED') from subprocess.CalledProcessError(
            7, 'fixed-controller', stderr=b'native publication cause; token=private-fixture-value')
    monkeypatch.setattr(publication, 'publish', fail)
    with pytest.raises(SystemExit):
        publication.main()
    output = capsys.readouterr()
    assert json.loads(output.out) == {'error_code': 'CONSUMER_PUBLICATION_CONTROLLER_FAILED'}
    assert 'native publication cause' in log.read_text()
    assert 'native publication cause' not in output.out + output.err
    assert 'private-fixture-value' not in log.read_text() + output.out + output.err
