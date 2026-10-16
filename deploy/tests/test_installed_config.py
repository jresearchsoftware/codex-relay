"""Protected installed configuration with synthetic native filesystem fixtures."""
import hashlib
import importlib.util
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
import installed_config

HEAD = 'a' * 40
CONSUMER_HEAD = 'b' * 40
WORKFLOW_HEAD = 'c' * 40
PRIVATE_MARKER = 'fixture-private-config-marker'


@pytest.fixture
def installed():
    if sys.platform != 'linux' or os.geteuid() != 0 or not shutil.which('node'):
        pytest.skip('native root filesystem and Node required')
    with tempfile.TemporaryDirectory(prefix='relay-installed-config-test-', dir='/run') as temporary:
        base = Path(temporary)
        install = base / 'codex-relay'
        release = install / 'releases' / HEAD
        source = release / 'reviewed-source'
        source.mkdir(parents=True, mode=0o755)
        for path in [install, release.parent, release, source]:
            path.chmod(0o755)
        current = install / 'current'
        current.symlink_to(release)
        # Exercise the real consumer/schema validator, including its shared
        # execution defaults; no second validator or canned validation result.
        for name in ['consumer/consumer-config.mjs', 'contracts/src/execution-defaults.mjs',
                     'reviewer/src/executable-cr-v2.json', 'deploy/config.py',
                     'deploy/installed_config.py']:
            target = source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
            target.chmod(0o644)
        config = json.loads((ROOT / 'deploy/example.json').read_text())
        config['source'] = {'repository': 'https://github.com/example/codex-relay.git', 'revision': 'main'}
        config['consumer']['repository'] = 'example/codex-relay'
        config['target']['host'] = PRIVATE_MARKER + '.example.invalid'
        config['environment']['localApply'] = {'source': 'installed'}
        fixture = {
            'base': base, 'install': install, 'release': release, 'source': source,
            'current': current, 'config': config,
            'snapshot': release / 'deployment-config.json',
            'manifest_path': release / 'artifact-manifest.json',
            'source_identity': source / '.relay-source.json',
            'manifest': {'schemaVersion': '1.0', 'commit': HEAD, 'installedRevision': HEAD,
                         'resolvedRevision': HEAD, 'consumerRevision': CONSUMER_HEAD},
        }
        write_json(fixture['source_identity'], {'revision': HEAD}, 0o644)
        save_config(fixture)
        yield fixture


def write_json(path, value, mode):
    path.write_text(json.dumps(value) + '\n')
    path.chmod(mode)


def save_config(fixture):
    write_json(fixture['snapshot'], fixture['config'], 0o600)
    digest = hashlib.sha256(fixture['snapshot'].read_bytes()).hexdigest()
    fixture['manifest']['deploymentConfigSha256'] = digest
    write_json(fixture['manifest_path'], fixture['manifest'], 0o640)
    return digest


def assert_rejected(fixture, capsys, **kwargs):
    with pytest.raises((ValueError, OSError)) as error:
        installed_config.verify(fixture['source'], HEAD, **kwargs)
    assert PRIVATE_MARKER not in str(error.value)
    if isinstance(error.value, ValueError):
        assert len(str(error.value)) <= 120
        assert re.fullmatch('[a-z-]+', str(error.value))
    captured = capsys.readouterr()
    assert captured.out == captured.err == ''


def test_valid_snapshot_preserves_exact_consumer_revision_and_bytes(installed, capsys):
    original = installed['snapshot'].read_bytes()
    before = installed_config.stamp(installed['snapshot'].stat())
    with patch.object(installed_config, 'check_public_main') as remote:
        config, digest, consumer_revision = installed_config.verify(installed['source'], HEAD)
    assert config == installed['config']
    assert digest == hashlib.sha256(original).hexdigest()
    assert consumer_revision == CONSUMER_HEAD and consumer_revision != HEAD
    assert installed['snapshot'].read_bytes() == original
    assert installed_config.stamp(installed['snapshot'].stat()) == before
    remote.assert_not_called()
    assert capsys.readouterr().out == ''


@pytest.fixture
def external_pool_installed(installed):
    config = installed['config']
    config['consumer']['repository'] = 'example/consumer'
    config['consumer']['generalRunnerPool'] = {'desiredCapacity': 2}
    config['environment']['localApply'] = {'configPath': 'deploy/relay.json'}
    config['environment']['instance'] = {'reviewerPort': 18787, 'publicationEnabled': False}
    config['environment']['generalRunner'].update(scope='organization', group='example-general', poolApp={
        'appId': '101', 'installationId': '201', 'privateKeyFile': '/owner-private/app.pem'})
    save_config(installed)
    return installed


def test_external_pool_snapshot_requires_explicit_owner_helper_verification(external_pool_installed):
    fixture = external_pool_installed
    before = installed_config.stamp(fixture['snapshot'].stat())
    with pytest.raises(ValueError, match='^installed-config-binding$'):
        installed_config.verify(fixture['source'], HEAD)
    with patch.object(installed_config, 'check_public_main') as remote:
        config, digest, consumer = installed_config.verify(fixture['source'], HEAD, require_local_apply=False)
    assert config['consumer']['repository'] == 'example/consumer'
    assert config['consumer']['generalRunnerPool'] == {'desiredCapacity': 2}
    assert config['environment']['localApply'] == {'configPath': 'deploy/relay.json'}
    assert digest == fixture['manifest']['deploymentConfigSha256']
    assert consumer == CONSUMER_HEAD
    assert installed_config.stamp(fixture['snapshot'].stat()) == before
    remote.assert_not_called()


def test_owner_pool_entrypoint_verifies_external_snapshot_before_token_or_state_access(external_pool_installed, monkeypatch):
    import managed_pool
    fixture = external_pool_installed
    monkeypatch.setattr(managed_pool, '__file__', str(fixture['source'] / 'deploy/managed_pool.py'))

    def verified(config):
        assert config['consumer']['repository'] == 'example/consumer'
        assert config['environment']['localApply'] == {'configPath': 'deploy/relay.json'}
        raise RuntimeError('fixture-stopped-before-mutation')

    with patch.object(managed_pool, 'pool_contract', side_effect=verified), \
            patch.object(managed_pool.sys, 'stdin') as token_input, patch.object(managed_pool, 'State') as state:
        with pytest.raises(RuntimeError, match='^fixture-stopped-before-mutation$'):
            managed_pool.installed_main(HEAD)
    token_input.read.assert_not_called()
    state.assert_not_called()


@pytest.mark.parametrize('mutation', ['namespace', 'source-head', 'manifest-head', 'config-digest',
                                   'snapshot-mode', 'snapshot-owner', 'manifest-symlink', 'current', 'source-parent'])
def test_owner_pool_verification_preserves_all_snapshot_boundaries(external_pool_installed, capsys, mutation):
    fixture = external_pool_installed
    if mutation == 'namespace':
        fixture['config']['environment']['namespace'] = 'another-relay'
        save_config(fixture)
    elif mutation == 'source-head':
        write_json(fixture['source_identity'], {'revision': 'c' * 40}, 0o644)
    elif mutation == 'manifest-head':
        fixture['manifest']['installedRevision'] = 'c' * 40
        write_json(fixture['manifest_path'], fixture['manifest'], 0o640)
    elif mutation == 'config-digest':
        fixture['snapshot'].write_bytes(fixture['snapshot'].read_bytes() + b'\n')
    elif mutation == 'snapshot-mode':
        fixture['snapshot'].chmod(0o640)
    elif mutation == 'snapshot-owner':
        os.chown(fixture['snapshot'], 1, 0)
    elif mutation == 'manifest-symlink':
        original = fixture['manifest_path'].with_suffix('.original')
        fixture['manifest_path'].rename(original)
        fixture['manifest_path'].symlink_to(original)
    elif mutation == 'current':
        fixture['current'].unlink()
        fixture['current'].symlink_to(fixture['release'].with_name('c' * 40))
    else:
        fixture['source'].chmod(0o777)
    assert_rejected(fixture, capsys, require_local_apply=False)


def test_local_cli_keeps_consumer_provenance_and_emits_product_receipts(installed, capsys, monkeypatch):
    import deployment_lock
    spec = importlib.util.spec_from_file_location('installed_cli_fixture', ROOT / 'deploy/relay-deploy.py')
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    raw = json.dumps(installed['config'], sort_keys=True, separators=(',', ':'), ensure_ascii=False) + '\n'
    installed['snapshot'].write_text(raw)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    installed['manifest']['deploymentConfigSha256'] = digest
    write_json(installed['manifest_path'], installed['manifest'], 0o640)
    state = installed['base'] / 'state'
    state.mkdir()
    original_compile, original_acquire = cli.compile_inputs, deployment_lock.acquire

    def compile_fixture(config):
        values = original_compile(config)
        values.update(relay_release_root=str(installed['release'].parent), relay_state_root=str(state))
        return values

    def acquire_fixture(path):
        assert path == '/var/lib/codex-relay-deployment.lock'
        return original_acquire(installed['base'] / 'deployment.lock')

    def backend(argv, cwd, env, log, guard, pool_guard=None):
        assert pool_guard is None
        values = json.loads(Path(argv[argv.index('-i') + 1]).read_text())['all']['children']['relay']['hosts']
        values = next(iter(values.values()))
        assert values['ansible_connection'] == 'local'
        assert values['relay_consumer_revision'] == CONSUMER_HEAD != HEAD
        assert values['relay_workflow_consumer_revision'] == WORKFLOW_HEAD
        assert values['relay_installed_config_expected_sha256'] == digest
        assert not values['relay_installed_config_recovery_authorized']
        assert values['relay_installed_deployment_config'] == raw
        log.write(f'failed=0\nPRODUCTION_APPLY_VALIDATED={HEAD}\n'
                  f'RELAY_INSTALLED_REVISION={HEAD};consumer={CONSUMER_HEAD};previous=none\n'
                  f'PRODUCTION_LIFECYCLE_PRESERVED={HEAD};activation=owner-after-job\n')
        return 0

    monkeypatch.setattr(cli, 'ROOT', installed['source'])
    monkeypatch.setattr(cli, 'compile_inputs', compile_fixture)
    monkeypatch.setattr(cli, 'run_backend', backend)
    monkeypatch.setattr(deployment_lock, 'acquire', acquire_fixture)
    monkeypatch.setattr(sys, 'argv', ['relay-deploy', '--config', str(installed['snapshot']),
                        '--phase', 'apply', '--local-reconcile', '--expected-installed-head', HEAD,
                        '--workflow-consumer-revision', WORKFLOW_HEAD,
                        '--log-root', str(installed['base'] / 'logs')])
    # The public CLI normally exits its process with a restrictive mask. This
    # in-process adapter test must not change later native filesystem fixtures.
    previous_umask = os.umask(0o077)
    try:
        cli.run(cli.arguments())
    finally:
        os.umask(previous_umask)
    output = capsys.readouterr().out
    assert f'consumer_revision={CONSUMER_HEAD}' in output
    assert f'PRODUCTION_APPLY_VALIDATED={HEAD}' in output
    assert f'PRODUCTION_LIFECYCLE_PRESERVED={HEAD};' in output
    assert f'PRODUCTION_APPLY_VALIDATED={CONSUMER_HEAD}' not in output
    assert installed['snapshot'].read_text() == raw


def test_nonroot_caller_is_rejected_before_reading_inputs(installed, capsys):
    with patch.object(installed_config.os, 'geteuid', return_value=1):
        assert_rejected(installed, capsys)


@pytest.mark.parametrize('head', ['main', 'a' * 39, 'A' * 40, 'c' * 40])
def test_caller_cannot_select_another_revision(installed, head):
    with patch.object(installed_config, 'read_protected') as read:
        with pytest.raises(ValueError, match='^installed-(?:head|release-path)$'):
            installed_config.verify(installed['source'], head)
    read.assert_not_called()


@pytest.mark.parametrize('source', [
    {'repository': 'https://github.com/example/codex-relay.git'},
    {'repository': 'git@github.com:example/codex-relay.git', 'revision': 'main'},
])
def test_supported_repository_spelling_and_default_main(installed, source):
    installed['config']['source'] = source
    digest = save_config(installed)
    with patch.object(installed_config, 'check_public_main') as remote:
        config, observed, consumer = installed_config.verify(
            installed['source'], HEAD, expected_digest=digest,
            expected_consumer_revision=CONSUMER_HEAD, check_main=True, workflow_consumer_revision=WORKFLOW_HEAD)
    remote.assert_called_once_with('example/codex-relay', WORKFLOW_HEAD)
    assert config['source'] == source
    assert observed == digest and consumer == CONSUMER_HEAD


@pytest.mark.parametrize('mode', [0o400, 0o640, 0o644, 0o660, 0o666])
def test_snapshot_requires_exact_private_mode(installed, capsys, mode):
    installed['snapshot'].chmod(mode)
    assert_rejected(installed, capsys)


@pytest.mark.parametrize('uid,gid', [(1, 0), (0, 1), (1, 1)])
def test_snapshot_requires_root_owner_and_group(installed, capsys, uid, gid):
    os.chown(installed['snapshot'], uid, gid)
    assert_rejected(installed, capsys)


@pytest.mark.parametrize('name', ['snapshot', 'manifest_path', 'source_identity'])
@pytest.mark.parametrize('mutation', ['symlink', 'hardlink', 'owner', 'writable'])
def test_all_installed_inputs_require_protected_regular_files(installed, capsys, name, mutation):
    target = installed[name]
    if mutation == 'symlink':
        original = target.with_name(target.name + '.original')
        target.rename(original)
        target.symlink_to(original)
    elif mutation == 'hardlink':
        os.link(target, target.with_name(target.name + '.alias'))
    elif mutation == 'owner':
        os.chown(target, 1, 0)
    else:
        target.chmod(0o666)
    assert_rejected(installed, capsys)


@pytest.mark.parametrize('name', ['base', 'install', 'release', 'source'])
@pytest.mark.parametrize('mutation', ['writable', 'owner', 'symlink'])
def test_every_installed_ancestor_is_protected(installed, capsys, name, mutation):
    target = installed[name]
    if mutation == 'owner':
        os.chown(target, 1, 0)
    elif mutation == 'writable':
        target.chmod(0o775)
    else:
        original = target.with_name(target.name + '-original')
        target.rename(original)
        target.symlink_to(original)
        # Keep temporary fixture cleanup bounded even when its top directory
        # is the rejected symlink.
        if name == 'base':
            try:
                assert_rejected(installed, capsys)
            finally:
                target.unlink()
                original.rename(target)
            return
    assert_rejected(installed, capsys)


@pytest.mark.parametrize('mutation', ['other-release', 'relative', 'directory', 'owner'])
def test_current_must_be_root_owned_exact_absolute_release_link(installed, capsys, mutation):
    current = installed['current']
    if mutation == 'owner':
        os.lchown(current, 1, 0)
    else:
        current.unlink()
        if mutation == 'directory':
            current.mkdir()
        elif mutation == 'relative':
            current.symlink_to(Path('releases') / HEAD)
        else:
            current.symlink_to(installed['release'].with_name('c' * 40))
    assert_rejected(installed, capsys)


@pytest.mark.parametrize('field,value', [
    ('commit', 'c' * 40), ('installedRevision', 'c' * 40), ('resolvedRevision', 'c' * 40),
    ('consumerRevision', 'main'), ('consumerRevision', None),
    ('deploymentConfigSha256', 'd' * 64),
])
def test_manifest_binds_all_revisions_and_snapshot_digest(installed, capsys, field, value):
    installed['manifest'][field] = value
    write_json(installed['manifest_path'], installed['manifest'], 0o640)
    assert_rejected(installed, capsys)


def test_source_identity_must_match_installed_head(installed, capsys):
    write_json(installed['source_identity'], {'revision': 'c' * 40}, 0o644)
    assert_rejected(installed, capsys)


@pytest.mark.parametrize('binding', [
    {'expected_digest': 'd' * 64}, {'expected_consumer_revision': HEAD},
])
def test_revalidation_rejects_changed_admission_binding_before_remote_read(installed, capsys, binding):
    with patch.object(installed_config, 'check_public_main') as remote:
        assert_rejected(installed, capsys, check_main=True, workflow_consumer_revision=WORKFLOW_HEAD, **binding)
    remote.assert_not_called()


@pytest.mark.parametrize('section,field,value', [
    ('source', 'repository', 'https://github.com/example/other.git'),
    ('source', 'revision', HEAD), ('consumer', 'baseBranch', 'stable'),
    ('environment', 'namespace', 'another-relay'),
    ('environment', 'localApply', {'configPath': 'deploy/relay.json'}),
    ('environment', 'localApply', {'source': 'installed', 'configPath': 'deploy/relay.json'}),
    ('target', 'hostFingerprint', PRIVATE_MARKER),
])
def test_full_schema_and_self_dogfood_binding_are_enforced(installed, capsys, section, field, value):
    installed['config'][section][field] = value
    save_config(installed)
    assert_rejected(installed, capsys)


@pytest.mark.parametrize('name', ['snapshot', 'manifest_path', 'source_identity'])
def test_private_malformed_json_is_not_disclosed(installed, capsys, name):
    installed[name].write_text('{"invalid": ' + PRIVATE_MARKER)
    if name == 'snapshot':
        installed['manifest']['deploymentConfigSha256'] = hashlib.sha256(installed[name].read_bytes()).hexdigest()
        write_json(installed['manifest_path'], installed['manifest'], 0o640)
    assert_rejected(installed, capsys)


@pytest.mark.parametrize('name', ['snapshot', 'manifest_path', 'source_identity', 'current'])
def test_remote_read_cannot_hide_changed_local_inputs(installed, capsys, name):
    def replace_after_read(repository, head):
        assert (repository, head) == ('example/codex-relay', WORKFLOW_HEAD)
        target = installed[name]
        if name == 'current':
            target.unlink()
            target.symlink_to(installed['release'].with_name('c' * 40))
        else:
            target.write_bytes(target.read_bytes() + b'\n')
    with patch.object(installed_config, 'check_public_main', side_effect=replace_after_read):
        assert_rejected(installed, capsys, check_main=True, workflow_consumer_revision=WORKFLOW_HEAD)


@pytest.mark.parametrize('mutation', ['symlink', 'private-json'])
def test_cli_failure_is_bounded_and_never_discloses_snapshot(installed, mutation):
    snapshot = installed['snapshot']
    if mutation == 'symlink':
        snapshot.unlink()
        snapshot.symlink_to(installed['base'] / PRIVATE_MARKER)
    else:
        installed['config']['target']['hostFingerprint'] = PRIVATE_MARKER
        save_config(installed)
    completed = subprocess.run([
        sys.executable, str(installed['source'] / 'deploy/installed_config.py'), HEAD,
        installed['manifest']['deploymentConfigSha256'], CONSUMER_HEAD, WORKFLOW_HEAD,
    ], capture_output=True, text=True)
    assert completed.returncode == 1
    assert completed.stdout == ''
    assert re.fullmatch(r'INSTALLED_CONFIG_BLOCKED=[a-z-]+\n', completed.stderr)
    assert len(completed.stderr) < 160
    assert PRIVATE_MARKER not in completed.stderr


def main_response(head=HEAD):
    return {'ref': 'refs/heads/main', 'object': {'type': 'commit', 'sha': head}}


def remote_fixture(raw=None, status=200):
    response = MagicMock(status=status)
    response.read.return_value = json.dumps(main_response()).encode() if raw is None else raw
    connection = MagicMock()
    connection.getresponse.return_value = response
    return connection, response


def test_public_main_uses_fixed_anonymous_tls_request_and_bounded_response():
    connection, response = remote_fixture()
    with patch('http.client.HTTPSConnection', return_value=connection) as https:
        installed_config.check_public_main('example/codex-relay', HEAD)
    args, options = https.call_args
    assert args == ('api.github.com',)
    assert options['timeout'] == 15
    assert options['context'].verify_mode == ssl.CERT_REQUIRED
    assert options['context'].check_hostname
    args, options = connection.request.call_args
    assert args == ('GET', '/repos/example/codex-relay/git/ref/heads/main')
    assert 'authorization' not in {key.lower() for key in options['headers']}
    response.read.assert_called_once_with(8193)
    connection.close.assert_called_once()


@pytest.mark.parametrize('status', [301, 302, 401, 403, 404, 429, 500])
def test_public_main_rejects_errors_and_redirects_without_followup(status):
    connection, response = remote_fixture(status=status)
    with patch('http.client.HTTPSConnection', return_value=connection) as https:
        with pytest.raises(ValueError, match='^main-head-unavailable$'):
            installed_config.check_public_main('example/codex-relay', HEAD)
    https.assert_called_once()
    response.read.assert_not_called()
    connection.close.assert_called_once()


@pytest.mark.parametrize('value', [
    main_response('c' * 40), {'ref': 'refs/heads/other', 'object': main_response()['object']},
    {'ref': 'refs/heads/main', 'object': {'type': 'tag', 'sha': HEAD}},
    {'ref': 'refs/heads/main', 'object': None}, [], None,
])
def test_public_main_rejects_changed_head_and_invalid_native_identity(value):
    connection, _ = remote_fixture(json.dumps(value).encode())
    with patch('http.client.HTTPSConnection', return_value=connection):
        with pytest.raises(ValueError, match='^main-head-(?:unavailable|mismatch)$'):
            installed_config.check_public_main('example/codex-relay', HEAD)
    connection.close.assert_called_once()


@pytest.mark.parametrize('raw', [b'x' * 8193, b'{invalid', b'\xff'])
def test_public_main_rejects_oversize_and_malformed_responses(raw):
    connection, _ = remote_fixture(raw)
    with patch('http.client.HTTPSConnection', return_value=connection):
        with pytest.raises(ValueError, match='^main-head-unavailable$'):
            installed_config.check_public_main('example/codex-relay', HEAD)
    connection.close.assert_called_once()


@pytest.mark.parametrize('failure', [TimeoutError('fixture timeout'),
                                   ssl.SSLCertVerificationError('fixture TLS failure'),
                                   http.client.RemoteDisconnected('fixture disconnect')])
def test_public_main_network_failure_has_no_fallback(failure):
    connection, _ = remote_fixture()
    connection.getresponse.side_effect = failure
    with patch('http.client.HTTPSConnection', return_value=connection) as https:
        with pytest.raises(ValueError, match='^main-head-unavailable$'):
            installed_config.check_public_main('example/codex-relay', HEAD)
    https.assert_called_once()
    connection.close.assert_called_once()
