"""Read-only bootstrap inventory against synthetic native Linux state."""
import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
import inventory


@pytest.fixture
def target(tmp_path):
    config = json.loads((ROOT / 'deploy/example.json').read_text())
    tmp_path.chmod(0o700)
    ids = {name: (os.getuid(), os.getgid()) for name in [
        config['environment']['runner']['user'], config['environment']['generalRunner']['user'],
        config['consumer']['runtimeUser'], config['environment']['reviewerUser']]}
    return SimpleNamespace(root=tmp_path, config=config, ids=ids)


def path(target, absolute):
    return target.root / absolute.lstrip('/')


def write(target, absolute, value, mode=0o600):
    destination = path(target, absolute)
    destination.parent.mkdir(parents=True, exist_ok=True)
    for parent in [destination.parent, *destination.parent.parents]:
        if parent.is_relative_to(target.root):
            parent.chmod(0o700)
    raw = json.dumps(value) if isinstance(value, dict) else value
    destination.write_text(raw)
    destination.chmod(mode)
    return destination


def installed(target, snapshot=True):
    revision = 'a' * 40
    release = '/opt/codex-relay/releases/' + revision
    write(target, '/etc/codex-relay/consumer.json', target.config['consumer'])
    write(target, release + '/reviewed-source/.relay-source.json', {'revision': revision, 'tree': 'b' * 40})
    manifest = {'commit': revision, 'installedRevision': revision, 'resolvedRevision': revision, 'gitTree': 'b' * 40}
    if snapshot:
        written = write(target, release + '/deployment-config.json', target.config)
        manifest['deploymentConfigSha256'] = hashlib.sha256(written.read_bytes()).hexdigest()
    write(target, release + '/artifact-manifest.json', manifest)
    path(target, '/opt/codex-relay/current').symlink_to('releases/' + revision)
    return release


def runner(target, general=False):
    suffix = 'general-runner' if general else 'runner'
    intent = target.config['environment']['generalRunner' if general else 'runner']
    scope = intent.get('scope', 'repository')
    repository = target.config['consumer']['repository']
    marker = {'gitHubUrl': 'https://github.com/' + (repository.split('/')[0] if scope == 'organization' else repository),
              'agentName': intent['name'], 'workFolder': '/var/lib/codex-relay/' + suffix + '/work',
              'agentId': 123, 'poolName': intent.get('group', 'Default')}
    marker_path = write(target, '/opt/codex-relay/' + suffix + '/.runner', marker)
    write(target, '/opt/codex-relay/' + suffix + '/.credentials', 'PRIVATE_FIXTURE_NEVER_READ')
    write(target, '/opt/codex-relay/' + suffix + '/.credentials_rsaparams', 'PRIVATE_RSA_FIXTURE_NEVER_READ')
    return marker_path


def observe(target, config=None):
    return inventory.inspect(config or target.config, root=target.root, owner_uid=os.getuid(), user_ids=target.ids)


def snapshot(root):
    return {str(p.relative_to(root)): (stat.S_IFMT(p.lstat().st_mode), p.lstat().st_mode,
            p.lstat().st_ino, p.lstat().st_mtime_ns, p.lstat().st_ctime_ns, p.lstat().st_size,
            os.readlink(p) if p.is_symlink() else p.read_bytes() if p.is_file() else None)
            for p in [root, *root.rglob('*')]}


def test_fresh_target_reports_missing_inputs_without_creating_anything(target):
    before = snapshot(target.root)
    report = observe(target)
    assert report['status'] == 'observed'
    assert report['installed'] == {'status': 'missing'}
    assert report['configuration']['status'] == 'missing'
    assert all(row['status'] == 'missing' and row['freshTokenRequired'] for row in report['runners'].values())
    assert report['readOnly'] and report['mutationAuthorized'] is False
    assert all(item['status'] == 'unavailable' and item['next'] for item in report['ownerAdmin'])
    assert snapshot(target.root) == before


def test_installed_equivalence_and_registered_runners_reuse_without_secret_reads(target, monkeypatch):
    installed(target)
    runner(target)
    runner(target, True)
    write(target, '/etc/codex-relay/writer-credentials/github-app-private-key.pem', 'PRIVATE_FIXTURE_NEVER_READ')
    before = snapshot(target.root)
    read = inventory.Probe.read

    def bounded_read(self, value, **kwargs):
        assert not value.endswith(('.credentials', '.credentials_rsaparams', 'private-key.pem', 'access-token'))
        return read(self, value, **kwargs)

    monkeypatch.setattr(inventory.Probe, 'read', bounded_read)
    report = observe(target)
    assert report['status'] == 'observed'
    assert report['configuration']['status'] == 'equivalent'
    assert all(row['status'] == 'reusable' and not row['freshTokenRequired'] for row in report['runners'].values())
    assert 'PRIVATE_FIXTURE' not in json.dumps(report)
    assert snapshot(target.root) == before


def test_old_snapshot_absence_is_visible_owner_handoff_not_fabricated_equivalence(target):
    installed(target, snapshot=False)
    report = observe(target)
    assert report['status'] == 'observed'
    assert report['configuration'] == {'status': 'consumer-equivalent', 'consumer': 'equivalent', 'deployment': 'unavailable'}
    assert any(row['name'] == 'installed-environment-intent' for row in report['ownerAdmin'])


def test_source_selector_and_explicit_default_effort_are_materially_equivalent(target):
    installed(target)
    config = copy.deepcopy(target.config)
    config['source']['revision'] = 'accepted-tag'
    config['consumer']['defaultProfile']['effort'] = 'ultra'
    assert observe(target, config)['configuration']['status'] == 'equivalent'


@pytest.mark.parametrize('section,key,value', [
    ('consumer', 'repository', 'different/project'),
    ('consumer', 'owner', 'different-owner'),
    ('environment', 'serviceUser', 'different-user'),
    ('target', 'host', '192.0.2.77'),
])
def test_material_configuration_change_is_blocked(target, section, key, value):
    installed(target)
    changed = copy.deepcopy(target.config)
    changed[section][key] = value
    report = observe(target, changed)
    assert report['configuration']['status'] == 'different'
    assert 'configuration-different' in report['blockers']


@pytest.mark.parametrize('damage', ['mode', 'hardlink', 'symlink', 'digest', 'duplicate', 'oversize'])
def test_unsafe_or_unbound_snapshot_fails_closed_without_content_disclosure(target, damage):
    release = installed(target)
    destination = path(target, release + '/deployment-config.json')
    if damage == 'mode':
        destination.chmod(0o644)
    elif damage == 'hardlink':
        os.link(destination, destination.with_name('alias'))
    elif damage == 'symlink':
        destination.unlink()
        destination.symlink_to(path(target, '/etc/codex-relay/consumer.json'))
    elif damage == 'digest':
        destination.write_text('PRIVATE_FIXTURE_NEVER_PRINT')
    else:
        raw = '{"source":{},"source":{}}' if damage == 'duplicate' else 'x' * (inventory.LIMIT + 1)
        destination.write_text(raw)
        manifest = path(target, release + '/artifact-manifest.json')
        content = json.loads(manifest.read_text())
        content['deploymentConfigSha256'] = hashlib.sha256(raw.encode()).hexdigest()
        manifest.write_text(json.dumps(content))
    report = observe(target)
    assert report['configuration']['status'] == 'invalid'
    assert report['status'] == 'blocked'
    assert 'PRIVATE_FIXTURE' not in json.dumps(report)


@pytest.mark.parametrize('damage', ['credentials-missing', 'marker-missing', 'wrong-name', 'wrong-url', 'wrong-work',
                                     'wrong-group', 'bad-agent-id', 'credentials-symlink', 'marker-mode', 'parent-link'])
def test_partial_or_foreign_runner_never_requests_a_replacement_token(target, damage):
    marker_path = runner(target)
    credentials = marker_path.with_name('.credentials')
    if damage == 'credentials-missing':
        credentials.unlink()
    elif damage == 'marker-missing':
        marker_path.unlink()
    elif damage == 'credentials-symlink':
        credentials.unlink()
        credentials.symlink_to(marker_path)
    elif damage == 'marker-mode':
        marker_path.chmod(0o644)
    elif damage == 'parent-link':
        directory = marker_path.parent
        moved = directory.with_name('aliased-runner')
        directory.rename(moved)
        directory.symlink_to(moved)
    else:
        marker = json.loads(marker_path.read_text())
        field = {'wrong-name': 'agentName', 'wrong-url': 'gitHubUrl', 'wrong-work': 'workFolder',
                 'wrong-group': 'poolName', 'bad-agent-id': 'agentId'}[damage]
        marker[field] = True if damage == 'bad-agent-id' else 'foreign'
        marker_path.write_text(json.dumps(marker))
    report = observe(target)
    assert report['runners']['production']['status'] == 'invalid'
    assert not report['runners']['production']['freshTokenRequired']
    assert 'runner-production-ambiguous' in report['blockers']


def test_missing_one_runner_requires_only_its_token(target):
    runner(target)
    report = observe(target)
    assert report['runners']['production']['status'] == 'reusable'
    assert not report['runners']['production']['freshTokenRequired']
    assert report['runners']['general']['status'] == 'missing'
    assert report['runners']['general']['freshTokenRequired']


def test_existing_unregistered_runner_package_is_missing_registration(target):
    write(target, '/opt/codex-relay/runner/config.sh', '# fixture')
    assert observe(target)['runners']['production']['status'] == 'missing'


@pytest.mark.parametrize('general', [False, True])
@pytest.mark.parametrize('shape', ['regular', 'dangling'])
def test_rsa_only_runner_state_is_preserved_as_ambiguous_without_secret_reads(target, monkeypatch, general, shape):
    suffix = 'general-runner' if general else 'runner'
    rsa = write(target, '/opt/codex-relay/' + suffix + '/.credentials_rsaparams', 'PRIVATE_RSA_FIXTURE_NEVER_READ')
    if shape == 'dangling':
        rsa.unlink()
        rsa.symlink_to(rsa.with_name('missing-private-key'))
    before = snapshot(target.root)
    read = inventory.Probe.read

    def bounded_read(self, value, **kwargs):
        assert not value.endswith('.credentials_rsaparams')
        return read(self, value, **kwargs)

    monkeypatch.setattr(inventory.Probe, 'read', bounded_read)
    report = observe(target)
    name = 'general' if general else 'production'
    assert report['runners'][name]['status'] == 'invalid'
    assert not report['runners'][name]['freshTokenRequired']
    assert 'runner-' + name + '-ambiguous' in report['blockers']
    assert 'PRIVATE_RSA_FIXTURE' not in json.dumps(report)
    assert snapshot(target.root) == before


def test_pending_registration_stays_ambiguous_even_with_complete_local_credentials(target):
    runner(target)
    write(target, '/var/lib/codex-relay/runner-registration-relay-production.pending', {'version': 1})
    report = observe(target)
    assert report['runners']['production']['reason'] == 'registration-pending'
    assert not report['runners']['production']['freshTokenRequired']


@pytest.mark.parametrize('name', ['clean-reinstall', 'production-operation'])
def test_interrupted_operation_requires_inspection(target, name):
    write(target, '/var/lib/codex-relay-' + name + '.json', {'status': 'unfinished'})
    report = observe(target)
    assert report['status'] == 'blocked'
    assert any(name + '-recovery-present' in code for code in report['blockers'])


@pytest.mark.parametrize('damage', ['dangling', 'foreign', 'missing-manifest', 'wrong-tree', 'install-symlink', 'residue'])
def test_unsupported_runtime_layout_is_not_fresh(target, damage):
    release = installed(target)
    current = path(target, '/opt/codex-relay/current')
    if damage in ['dangling', 'foreign']:
        current.unlink()
        current.symlink_to('releases/' + 'c' * 40 if damage == 'dangling' else '/opt/foreign/releases/' + 'a' * 40)
    elif damage == 'missing-manifest':
        path(target, release + '/artifact-manifest.json').unlink()
    elif damage == 'wrong-tree':
        write(target, release + '/reviewed-source/.relay-source.json', {'revision': 'a' * 40, 'tree': 'c' * 40})
    elif damage == 'residue':
        current.unlink()
    else:
        install_root = current.parent
        moved = install_root.with_name('foreign')
        install_root.rename(moved)
        install_root.symlink_to(moved)
    report = observe(target)
    assert report['installed']['status'] == 'invalid'
    assert 'installed-identity-invalid' in report['blockers']


def test_explicit_external_references_and_supported_tls_lineage_are_metadata_only(target):
    config = target.config
    config['environment']['writerCredential'] = {'sourceKeyFile': '/srv/owner/writer.pem'}
    source = write(target, '/srv/owner/writer.pem', 'PRIVATE_FIXTURE_NEVER_READ')
    host = config['environment']['ingress']['serverName']
    for kind, mode in [('fullchain', 0o644), ('privkey', 0o600)]:
        write(target, '/etc/letsencrypt/archive/' + host + '/' + kind + '1.pem', 'PRIVATE_FIXTURE_NEVER_READ', mode)
        live = path(target, '/etc/letsencrypt/live/' + host)
        live.mkdir(parents=True, exist_ok=True)
        (live / (kind + '.pem')).symlink_to('../../archive/' + host + '/' + kind + '1.pem')
    report = observe(target)
    items = {item['name']: item for item in report['protectedState']}
    assert items['writer-source']['status'] == 'reusable-metadata'
    assert items['tls-privateKeyFile']['status'] == 'reusable-metadata'
    assert items['tls-certificateFile']['status'] == 'reusable-metadata'
    assert all(item['validation'] == 'metadata-only' for item in items.values())
    assert 'PRIVATE_FIXTURE' not in json.dumps(report)
    source.chmod(0o644)
    assert observe(target)['status'] == 'blocked'


def test_remote_probe_is_read_only_standalone_source_without_installed_dependency(target, monkeypatch):
    report = observe(target)
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout=json.dumps(report), stderr='')

    monkeypatch.setattr(inventory.subprocess, 'run', run)
    assert inventory.remote_inventory(target.config['target'], '/owner/key', target.config) == report
    argv, options = calls[0]
    assert argv[:3] == ['ssh', '-o', 'BatchMode=yes']
    assert '/usr/bin/python3 -I -c' in argv[-1]
    assert 'def inspect(' in argv[-1]
    assert json.loads(options['input']) == target.config
    assert options['timeout'] == 45


def test_admin_handoff_binds_exact_consumer_workflow_refs_and_settings(target):
    target.config['consumer']['baseBranch'] = 'stable'
    target.config['consumer']['routingWorkflow'] = '.github/workflows/custom-routing.yml'
    target.config['environment']['generalRunner'].update(scope='organization', group='isolated-general')
    admin = {row['name']: row for row in observe(target)['ownerAdmin']}
    row = admin['github-runner-registration-and-policy']
    assert row['groupSettings'] == 'https://github.com/organizations/example-org/settings/actions/runner-groups'
    assert row['production']['onlyWorkflowRefs'] == [
        'example-org/sample-project/.github/workflows/manual-main-production-deploy.yml@refs/heads/stable']
    assert row['general']['onlyWorkflowRefs'] == [
        'example-org/sample-project/.github/workflows/custom-routing.yml@refs/heads/stable',
        'example-org/sample-project/.github/workflows/manual-writer-publication-recovery.yml@refs/heads/stable']
    assert row['general']['group'] == 'isolated-general'


def test_tls_source_group_readable_private_key_retains_supported_contract(target):
    target.config['environment']['tls'] = {'source': {
        'certificateFile': '/srv/owner/fullchain.pem', 'privateKeyFile': '/srv/owner/private-key.pem'}}
    write(target, '/srv/owner/fullchain.pem', 'public-fixture', 0o644)
    write(target, '/srv/owner/private-key.pem', 'PRIVATE_FIXTURE_NEVER_READ', 0o640)
    items = {row['name']: row for row in observe(target)['protectedState']}
    assert items['tls-privateKeyFile']['status'] == 'reusable-metadata'


@pytest.mark.parametrize('damage', ['missing-blockers', 'string-blockers', 'missing-runner', 'wrong-token-requirement',
                                     'missing-configuration', 'missing-installed-revision', 'status-inconsistent'])
def test_partial_remote_report_is_bounded_failure(target, monkeypatch, damage):
    report = observe(target)
    if damage == 'missing-blockers':
        del report['blockers']
    elif damage == 'string-blockers':
        report['blockers'] = 'PRIVATE_FIXTURE'
    elif damage == 'missing-runner':
        del report['runners']['general']
    elif damage == 'wrong-token-requirement':
        report['runners']['production']['freshTokenRequired'] = False
    elif damage == 'missing-configuration':
        report['configuration'] = {}
    elif damage == 'missing-installed-revision':
        report['installed'] = {'status': 'present'}
    else:
        report['status'] = 'blocked'
    monkeypatch.setattr(inventory.subprocess, 'run', lambda *args, **kwargs:
                        SimpleNamespace(returncode=0, stdout=json.dumps(report), stderr='PRIVATE_FIXTURE'))
    with pytest.raises(RuntimeError, match='RELAY_INVENTORY_UNAVAILABLE'):
        inventory.remote_inventory(target.config['target'], '/owner/key', target.config)


@pytest.mark.parametrize('failure', ['error', 'timeout', 'oversize', 'malformed', 'wrong-proof'])
def test_remote_failure_is_sanitized(target, monkeypatch, failure):
    def run(*args, **kwargs):
        if failure == 'timeout':
            raise subprocess.TimeoutExpired('ssh', 45, output='PRIVATE_FIXTURE', stderr='PRIVATE_FIXTURE')
        return SimpleNamespace(returncode=1 if failure == 'error' else 0,
                               stdout='x' * (inventory.LIMIT + 1) if failure == 'oversize' else
                               '{}' if failure == 'wrong-proof' else 'PRIVATE_FIXTURE', stderr='PRIVATE_FIXTURE')

    monkeypatch.setattr(inventory.subprocess, 'run', run)
    with pytest.raises(RuntimeError, match='RELAY_INVENTORY_UNAVAILABLE') as caught:
        inventory.remote_inventory(target.config['target'], '/owner/key', target.config)
    assert 'PRIVATE_FIXTURE' not in str(caught.value)
