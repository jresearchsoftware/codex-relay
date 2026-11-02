"""Read-only target prerequisites against real isolated Linux filesystem state."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


DEPLOY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEPLOY))
import config
import host_preflight as host

pytestmark = pytest.mark.skipif(sys.platform != 'linux' or os.geteuid() != 0,
                                reason='root Linux metadata qualification required')


def snapshot(root):
    result = {}
    for path in [root, *root.rglob('*')]:
        info = path.lstat()
        result[str(path.relative_to(root))] = (info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            os.readlink(path) if path.is_symlink() else path.read_bytes() if path.is_file() else None)
    return result


@pytest.fixture
def target(tmp_path):
    root = tmp_path / 'target'; root.mkdir(mode=0o755)
    desired = json.loads((DEPLOY / 'example.json').read_text())
    values = host.resolved(config.compile_inputs(desired))
    values['relay_writer_repositories'] = ['example-org/sample-project', 'example-org/second-project']
    values['relay_reviewer_repositories'] = list(values['relay_writer_repositories'])
    users = {}
    groups = {values['relay_codex_work_group']: 3000}
    names = [values[key] for key in ['relay_user', 'relay_reviewer_user', 'relay_runner_user',
                                     'relay_general_runner_user', 'relay_codex_user']]
    for index, name in enumerate(names, 2001):
        users[name] = {'uid': index, 'gid': index, 'shell': '/usr/sbin/nologin',
                       'home': '/nonexistent', 'groups': [index, 3000]}
        groups[name] = index
    users[values['relay_general_runner_user']]['home'] = values['relay_state_root'] + '/general-runner/home'
    users[values['relay_codex_user']]['home'] = values['relay_codex_home']
    def path(logical): return root / str(logical).lstrip('/')
    def write(logical, raw=b'protected synthetic input', mode=0o600):
        destination = path(logical); destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw); destination.chmod(mode); return destination
    generated = tmp_path / 'fixture-key.pem'
    subprocess.run(['/usr/bin/openssl', 'genpkey', '-algorithm', 'RSA', '-pkeyopt', 'rsa_keygen_bits:2048',
                    '-out', str(generated)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    for role in ['reviewer', 'writer']:
        write(values['relay_' + role + '_credential_key_file'], generated.read_bytes(), 0o640 if role == 'reviewer' else 0o600)
    token = write(values['relay_codex_access_token_file'], b'synthetic-private-canary-token')
    runtime = users[values['relay_codex_user']]
    os.chown(token, runtime['uid'], runtime['gid'])
    write(values['relay_nginx_server_certificate_file'], b'synthetic certificate', 0o644)
    write(values['relay_nginx_server_private_key_file'], b'synthetic private key')
    write(values['relay_tls_client_ca_file'], b'synthetic public CA', 0o640)
    for relative in ['deploy/ansible/roles/relay_runtime/files/relay-app-qualification.py',
                     'deploy/ansible/tools/tls-source-validate.py', 'deploy/ansible/tools/tls-webroot-bootstrap.py',
                     'deploy/ansible/tools/bootstrap_guard.py', 'deploy/managed_pool.py',
                     'deploy/ansible/roles/relay_runner/templates/relay-managed-pool.service.j2']:
        source = DEPLOY.parent / relative
        write('/candidate/' + relative, source.read_bytes(), 0o644)
    write('/proc/17/stat', b'17 (synthetic process) S ' + b'0 ' * 18 + b'731 0\n', 0o644)
    observed, services = [], {}
    def execute(argv, *, env=None):
        if argv[0] == '/usr/bin/openssl': return host._execute(argv, env=env)
        assert argv[:2] == ['systemctl', 'show']
        unit = argv[-1]
        external = unit in (values['relay_docker_nginx_service_name'], 'docker.service')
        state = {'LoadState': 'loaded' if external else 'not-found',
                 'ActiveState': 'active' if external else 'inactive', 'SubState': 'running' if external else 'dead',
                 'UnitFileState': 'enabled' if external else '', 'MainPID': '17' if external else '0',
                 'User': '', 'Group': '', 'FragmentPath': '', 'DropInPaths': ''}
        state.update(services.get(unit, {}))
        return subprocess.CompletedProcess(argv, 0, '\n'.join(key + '=' + value for key, value in state.items()).encode(), b'')
    def app_qualifier(source, settings, *, execute):
        observed.append(copy.deepcopy(settings))
    def tls_qualifier(*arguments, **keywords):
        pass
    def inspect(**changes):
        arguments = {'root': root, 'users': users, 'groups': groups, 'execute': execute,
                     'app_qualifier': app_qualifier, 'tls_qualifier': tls_qualifier,
                     'ca_qualifier': lambda *arguments, **keywords: None,
                     'acme_qualifier': lambda *arguments, **keywords: {'container': 'synthetic', 'certbotGlobalConfig': 'absent'},
                     'pool_qualifier': lambda *arguments, **keywords: {'status': 'PASS', 'createParents': [], 'members': {}}}
        arguments.update(changes)
        return host.inspect_inputs(values, '/candidate', **arguments)
    return {'root': root, 'values': values, 'users': users, 'groups': groups, 'path': path, 'write': write,
            'inspect': inspect, 'apps': observed, 'services': services, 'execute': execute}


def test_all_selected_app_repositories_and_readonly_stable_receipt(target):
    f = target
    f['path']('/var/lib/codex-relay/dispatch/attempts-v2').mkdir(parents=True)
    before = snapshot(f['root'])
    first = f['inspect'](); second = f['inspect']()
    assert first == second
    assert first['checks']['appRepositories'] == 4
    assert {(row['role'], row['repository']) for row in f['apps']} == {
        (role, repository) for role in ['writer', 'reviewer'] for repository in f['values']['relay_writer_repositories']}
    assert snapshot(f['root']) == before
    serialized = json.dumps(first)
    assert 'PRIVATE KEY' not in serialized and 'synthetic-private-canary-token' not in serialized
    assert str(f['root']) not in serialized and f['values']['relay_writer_credential_key_file'] not in serialized
    # Attempt/log activity is outside the snapshot; it must not invalidate a
    # prerequisite receipt while the old Relay finishes valid admitted work.
    f['write']('/var/lib/codex-relay/dispatch/attempts-v2/999.json', b'valid ongoing work')
    assert f['inspect']()['observedSha256'] == first['observedSha256']


@pytest.mark.parametrize('spelling', ['usr/lib', '/usr/lib'])
def test_loaded_distro_unit_uses_only_standard_usrmerge_alias_and_stable_readonly_receipt(target, spelling):
    f = target
    f['write']('/usr/lib/systemd/system/docker.service', b'[Service]\nExecStart=/usr/bin/dockerd\n', 0o644)
    f['path']('/lib').symlink_to(spelling, target_is_directory=True)
    f['services']['docker.service'] = {'FragmentPath': '/lib/systemd/system/docker.service'}
    before = snapshot(f['root'])
    first, second = f['inspect'](), f['inspect']()
    assert first['observedSha256'] == second['observedSha256']
    assert snapshot(f['root']) == before
    # This exception belongs only to reads of loaded distro units. A managed
    # destination under the same alias still receives the ordinary strict gate.
    with pytest.raises(host.HostPreflightError, match='HOST_DESTINATION_PARENT_UNSAFE'):
        host.Probe(f['root'], 0).inspect('managed-destination', '/lib/systemd/system/docker.service', protected=True)


def test_loaded_unit_alias_replacement_changes_receipt_and_unknown_alias_is_rejected(target):
    f = target
    f['write']('/usr/lib/systemd/system/docker.service', b'[Service]\nExecStart=/usr/bin/dockerd\n', 0o644)
    alias = f['path']('/lib'); alias.symlink_to('usr/lib', target_is_directory=True)
    f['services']['docker.service'] = {'FragmentPath': '/lib/systemd/system/docker.service'}
    first = f['inspect']()['observedSha256']
    alias.unlink(); alias.symlink_to('/usr/lib', target_is_directory=True)
    assert f['inspect']()['observedSha256'] != first
    alias.unlink(); alias.symlink_to('../usr/lib', target_is_directory=True)
    with pytest.raises(host.HostPreflightError, match='HOST_LOADED_UNIT_ALIAS_UNSAFE'):
        f['inspect']()


def test_loaded_distro_unit_and_canonical_parents_still_reject_group_write(target):
    f = target
    unit = f['write']('/usr/lib/systemd/system/docker.service', b'[Service]\nExecStart=/usr/bin/dockerd\n', 0o644)
    f['path']('/lib').symlink_to('usr/lib', target_is_directory=True)
    f['services']['docker.service'] = {'FragmentPath': '/lib/systemd/system/docker.service'}
    unit.chmod(0o664)
    before = snapshot(f['root'])
    with pytest.raises(host.HostPreflightError, match='HOST_DESTINATION_METADATA_UNSAFE'):
        f['inspect']()
    assert snapshot(f['root']) == before
    unit.chmod(0o644)
    unit.parent.chmod(0o775)
    with pytest.raises(host.HostPreflightError, match='HOST_DESTINATION_PARENT_UNSAFE'):
        f['inspect']()


def test_foreign_distro_alias_owner_and_aliased_canonical_directory_are_rejected(target):
    f = target
    f['write']('/usr/lib/systemd/system/docker.service', b'[Service]\nExecStart=/usr/bin/dockerd\n', 0o644)
    alias = f['path']('/lib'); alias.symlink_to('usr/lib', target_is_directory=True)
    f['services']['docker.service'] = {'FragmentPath': '/lib/systemd/system/docker.service'}
    os.chown(alias, 65534, 0, follow_symlinks=False)
    with pytest.raises(host.HostPreflightError, match='HOST_LOADED_UNIT_ALIAS_UNSAFE'):
        f['inspect']()
    os.chown(alias, 0, 0, follow_symlinks=False)
    canonical = f['path']('/usr/lib')
    canonical.rename(canonical.with_name('retained-lib'))
    canonical.symlink_to('retained-lib', target_is_directory=True)
    with pytest.raises(host.HostPreflightError, match='HOST_DESTINATION_PARENT_UNSAFE'):
        f['inspect']()


@pytest.mark.parametrize('kind', ['production', 'general', 'slot', 'member'])
def test_every_runner_destination_collision_fails_before_any_mutation(target, kind):
    f = target; v = f['values']
    if kind == 'slot':
        slot = {'relay_execution_slot': 'pool-2', 'relay_runner_root': '/opt/codex-relay/slots/pool-2/runner',
                'relay_runner_work_root': '/var/lib/codex-relay/slots/pool-2/runner/work',
                'relay_runner_home': '/var/lib/codex-relay/slots/pool-2/runner/home',
                'relay_runner_user': 'synthetic-slot-runner', 'relay_runner_service_name': 'codex-relay-slot-pool-2-runner.service',
                'relay_codex_user': 'synthetic-slot-runtime', 'relay_codex_group': 'synthetic-slot-runtime',
                'relay_codex_home': '/var/lib/codex-relay/slots/pool-2/codex-home',
                'relay_codex_access_token_file': '/etc/codex-relay/slots/pool-2/codex-credentials/access-token',
                'relay_codex_work_group': 'synthetic-slot-work',
                'relay_execution_slot_install_root': '/opt/codex-relay/slots/pool-2',
                'relay_dispatch_state_root': '/var/lib/codex-relay/slots/pool-2/dispatch',
                'relay_dispatch_home': '/var/lib/codex-relay/slots/pool-2/dispatch-home',
                'relay_dispatch_evidence_root': '/var/lib/codex-relay/slots/pool-2/dispatch/evidence',
                'relay_dispatch_work_root': '/var/lib/codex-relay/slots/pool-2/work',
                'relay_diagnostics_root': '/var/lib/codex-relay/slots/pool-2/debug',
                'relay_codex_launcher_path': '/opt/codex-relay/slots/pool-2/relay-codex',
                'relay_codex_dispatch_path': '/opt/codex-relay/slots/pool-2/relay-codex-dispatch',
                'relay_diagnostics_config_path': '/etc/codex-relay/slots/pool-2/diagnostics.json',
                'relay_diagnostics_store_path': '/opt/codex-relay/slots/pool-2/relay-diagnostics-store'}
        v['relay_additional_execution_slots'] = [slot]
    if kind == 'member':
        v['relay_general_runner_pool'] = {'runnerUser': v['relay_general_runner_user'], 'members': [
            {'id': 'primary', 'root': '/opt/codex-relay-pools/example/runners/primary',
             'state': '/var/lib/codex-relay-pools/example/runners/primary', 'service': 'example-pool-1.service'}]}
    rows = host.runner_targets(v)
    chosen = next(row for row in rows if row['label'] == kind or row['label'].startswith(kind + '-'))
    f['write'](chosen['root'], b'retained non-directory collision')
    before = snapshot(f['root'])
    with pytest.raises(host.HostPreflightError, match='HOST_DESTINATION_COLLISION'):
        f['inspect']()
    assert snapshot(f['root']) == before
    assert f['apps'] == []


@pytest.mark.parametrize('location', ['helper', 'config', 'unit', 'codex-tmp', 'parent'])
def test_aliased_or_wrong_type_destinations_are_not_silently_repaired(target, location):
    f = target
    paths = {'helper': '/opt/codex-relay/relay-admission', 'config': '/etc/codex-relay/consumer.json',
             'unit': '/etc/systemd/system/relay-runner.service',
             'codex-tmp': '/var/lib/codex-relay/codex-home/tmp', 'parent': '/opt/codex-relay/runner'}
    path = f['path'](paths[location]); path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to('/unrelated-private-input')
    before = snapshot(f['root'])
    with pytest.raises(host.HostPreflightError): f['inspect']()
    assert snapshot(f['root']) == before


def test_partial_registration_and_privileged_or_aliased_identities_fail_early(target):
    f = target
    marker = f['write']('/opt/codex-relay/general-runner/.runner', b'original registration')
    before = snapshot(f['root'])
    with pytest.raises(host.HostPreflightError, match='HOST_RUNNER_REGISTRATION_AMBIGUOUS'): f['inspect']()
    assert snapshot(f['root']) == before
    marker.unlink()
    f['users'][f['values']['relay_general_runner_user']]['uid'] = 0
    with pytest.raises(host.HostPreflightError, match='HOST_PRIVILEGED_IDENTITY_COLLISION'): f['inspect']()
    f['users'][f['values']['relay_general_runner_user']]['uid'] = f['users'][f['values']['relay_reviewer_user']]['uid']
    with pytest.raises(host.HostPreflightError, match='HOST_IDENTITY_ALIAS_COLLISION'): f['inspect']()


def test_projected_reviewer_key_group_cannot_expose_it_to_general_transport(target):
    f = target; v = f['values']
    f['users'][v['relay_general_runner_user']]['groups'].append(f['groups'][v['relay_reviewer_group']])
    before = snapshot(f['root'])
    with pytest.raises(host.HostPreflightError, match='HOST_PROTECTED_CREDENTIAL_GROUP_COLLISION'): f['inspect']()
    assert snapshot(f['root']) == before


def test_active_general_transport_does_not_surprise_restart_for_planned_identity_change(target):
    f = target; v = f['values']
    f['services'][v['relay_general_runner_service_name']] = {
        'LoadState': 'loaded', 'ActiveState': 'active', 'SubState': 'running', 'MainPID': '17', 'UnitFileState': 'enabled'}
    before = snapshot(f['root']); first = f['inspect']()
    assert first['identityPlan']['homeShellChanges'] == 0
    f['users'][v['relay_general_runner_user']]['groups'].remove(3000)
    with pytest.raises(host.HostPreflightError, match='HOST_ACTIVE_TRANSPORT_IDENTITY_CHANGED'): f['inspect']()
    assert snapshot(f['root']) == before
    f['users'][v['relay_general_runner_user']]['groups'].extend([3000, 6000])
    with pytest.raises(host.HostPreflightError, match='HOST_ACTIVE_TRANSPORT_IDENTITY_CHANGED'): f['inspect']()
    f['services'][v['relay_general_runner_service_name']]['ActiveState'] = 'inactive'
    f['services'][v['relay_general_runner_service_name']]['MainPID'] = '0'
    assert f['inspect']()['status'] == 'PASS'


def test_managed_pool_preserves_existing_owner_managed_home_shell_and_primary_gid(target):
    f = target; v = f['values']
    v['relay_general_runner_pool'] = {'runnerUser': v['relay_general_runner_user'],
        'appId': '999', 'installationId': '888', 'organization': 'example-org',
        'repositories': v['relay_writer_repositories'], 'members': [
        {'id': 'primary', 'root': '/opt/codex-relay-pools/example/runners/primary',
         'state': '/var/lib/codex-relay-pools/example/runners/primary', 'service': 'example-pool-1.service'}]}
    account = f['users'][v['relay_general_runner_user']]
    account.update(home='/home/owner-managed', shell='/bin/bash', gid=4000)
    account['groups'].append(6000)
    f['services']['example-pool-1.service'] = {'LoadState': 'loaded', 'ActiveState': 'active',
        'SubState': 'running', 'MainPID': '17', 'UnitFileState': 'enabled'}
    before = snapshot(f['root'])
    assert f['inspect']()['status'] == 'PASS'
    assert snapshot(f['root']) == before


@pytest.mark.parametrize('failure', ['missing', 'mode', 'malformed'])
def test_key_prerequisites_fail_without_printing_private_material(target, failure):
    f = target; path = f['path'](f['values']['relay_reviewer_credential_key_file'])
    if failure == 'missing': path.unlink()
    if failure == 'mode': path.chmod(0o666)
    if failure == 'malformed': path.write_bytes(b'PRIVATE KEY synthetic-private-canary-malformed')
    before = snapshot(f['root'])
    with pytest.raises(host.HostPreflightError) as caught: f['inspect']()
    assert 'synthetic-private-canary' not in str(caught.value)
    assert snapshot(f['root']) == before


def test_selected_source_key_is_qualified_before_its_live_destination_exists(target):
    f = target; v = f['values']
    key = f['path'](v['relay_reviewer_credential_key_file']); raw = key.read_bytes(); key.unlink()
    v['relay_reviewer_credential_source_file'] = '/owner/selected-reviewer.pem'
    f['write'](v['relay_reviewer_credential_source_file'], raw)
    before = snapshot(f['root'])
    assert f['inspect']()['status'] == 'PASS'
    assert all(row['key'].endswith('/owner/selected-reviewer.pem') for row in f['apps'] if row['role'] == 'reviewer')
    assert not key.exists() and snapshot(f['root']) == before


def test_service_process_unit_or_credential_rotation_changes_only_the_receipt(target):
    f = target; first = f['inspect']()['observedSha256']
    f['write']('/proc/17/stat', b'17 (synthetic process) S ' + b'0 ' * 18 + b'732 0\n', 0o644)
    assert f['inspect']()['observedSha256'] != first
    unit = f['write']('/etc/systemd/system/example.service', b'[Service]\nUser=example\n', 0o644)
    f['services'].setdefault(f['values']['relay_docker_nginx_service_name'], {})['FragmentPath'] = '/etc/systemd/system/example.service'
    second = f['inspect']()['observedSha256']; unit.write_bytes(b'[Service]\nUser=changed\n')
    assert f['inspect']()['observedSha256'] != second
    before = f['inspect']()['observedSha256']
    token = f['path'](f['values']['relay_codex_access_token_file']); token.write_bytes(b'synthetic changed token')
    assert f['inspect']()['observedSha256'] != before


def test_unknown_or_unavailable_external_service_is_an_actionable_precutover_failure(target):
    f = target; unit = f['values']['relay_docker_nginx_service_name']
    f['services'][unit] = {'ActiveState': 'inactive', 'MainPID': '0'}
    with pytest.raises(host.HostPreflightError, match='HOST_EXTERNAL_SERVICE_UNAVAILABLE'): f['inspect']()
    f['services'][unit] = {'ActiveState': 'activating'}
    with pytest.raises(host.HostPreflightError, match='HOST_SERVICE_STATE_AMBIGUOUS'): f['inspect']()


def test_existing_upgrade_missing_tls_does_not_claim_fresh_issuance_proof(target):
    f = target; v = f['values']
    for name in ['relay_nginx_server_certificate_file', 'relay_nginx_server_private_key_file']:
        f['path'](v[name]).unlink()
    v['relay_tls_acme_configured'] = True
    with pytest.raises(host.HostPreflightError, match='HOST_TLS_ISSUANCE_STAGE_REQUIRED'): f['inspect']()


def test_fresh_inactive_bootstrap_preserves_supported_product_owned_tls_schedule(target):
    f = target; v = f['values']
    for name in ['relay_nginx_server_certificate_file', 'relay_nginx_server_private_key_file']:
        f['path'](v[name]).unlink()
    v.update(relay_intent_expected_installed_revision='none', relay_tls_acme_configured=True,
             relay_tls_acme_method='webroot', relay_tls_acme_webroot='/srv/shared/webroot',
             relay_tls_acme_email='owner@example.invalid', relay_tls_public_addresses=['192.0.2.10'])
    before = snapshot(f['root'])
    result = f['inspect'](resolve_dns=lambda *arguments: [(2, 1, 6, '', ('192.0.2.10', 80))])
    assert result['pendingProductMaterial'] == ['tls-acme-issuance']
    assert snapshot(f['root']) == before
    with pytest.raises(host.HostPreflightError, match='HOST_TLS_PUBLIC_DNS_MISMATCH'):
        f['inspect'](resolve_dns=lambda *arguments: [(2, 1, 6, '', ('192.0.2.11', 80))])


def test_only_canonical_consumer_replacement_is_excluded_from_volatile_fingerprint(target):
    f = target; logical = f['values']['relay_config_root'] + '/consumer.json'
    path = f['write'](logical, b'invalid retained JSON', 0o644)
    first = f['inspect']()['observedSha256']
    replacement = path.with_name('safe-replacement.json'); replacement.write_text('{"authenticated":"baseline"}')
    replacement.chmod(0o644); os.replace(replacement, path)
    assert f['inspect']()['observedSha256'] == first
    path.chmod(0o600)
    assert f['inspect']()['observedSha256'] != first


def test_verified_old_serial_service_is_observed_after_desired_pool_selection(target):
    f = target; v = f['values']; revision = 'a' * 40
    old = json.loads((DEPLOY / 'example.json').read_text())
    raw = json.dumps(old).encode()
    f['write']('/opt/codex-relay/releases/' + revision + '/deployment-config.json', raw)
    manifest = {'commit': revision, 'deploymentConfigSha256': hashlib.sha256(raw).hexdigest()}
    f['write']('/opt/codex-relay/releases/' + revision + '/artifact-manifest.json', json.dumps(manifest).encode(), 0o640)
    f['path']('/opt/codex-relay/current').symlink_to('releases/' + revision)
    v['relay_general_runner_pool'] = {'runnerUser': v['relay_general_runner_user'],
        'appId': '999', 'installationId': '888', 'organization': 'example-org',
        'repositories': v['relay_writer_repositories'], 'members': [
        {'id': 'primary', 'root': '/opt/codex-relay-pools/example/runners/primary',
         'state': '/var/lib/codex-relay-pools/example/runners/primary', 'service': 'example-pool-1.service'}]}
    before = snapshot(f['root']); first = f['inspect']()['observedSha256']
    f['services']['relay-general-runner.service'] = {'LoadState': 'loaded', 'ActiveState': 'active',
        'SubState': 'running', 'MainPID': '17', 'UnitFileState': 'enabled'}
    assert f['inspect']()['observedSha256'] != first
    assert snapshot(f['root']) == before
    f['users'][v['relay_general_runner_user']]['groups'].remove(3000)
    with pytest.raises(host.HostPreflightError, match='HOST_ACTIVE_TRANSPORT_IDENTITY_CHANGED'): f['inspect']()


def test_tampered_retained_config_is_not_a_service_scope_authority(target):
    f = target; revision = 'b' * 40
    f['write']('/opt/codex-relay/releases/' + revision + '/deployment-config.json', b'{"private":"canary"}')
    manifest = {'commit': revision, 'deploymentConfigSha256': '0' * 64}
    f['write']('/opt/codex-relay/releases/' + revision + '/artifact-manifest.json', json.dumps(manifest).encode(), 0o640)
    f['path']('/opt/codex-relay/current').symlink_to('releases/' + revision)
    with pytest.raises(host.HostPreflightError, match='HOST_PREVIOUS_CONFIG_BINDING_INVALID'): f['inspect']()


def test_existing_ca_is_required_and_fresh_preparation_remains_explicitly_pending(target):
    f = target; v = f['values']; f['path'](v['relay_tls_client_ca_file']).unlink()
    with pytest.raises(host.HostPreflightError, match='HOST_CLIENT_CA_MISSING'): f['inspect']()
    v['relay_intent_expected_installed_revision'] = 'none'
    assert f['inspect']()['pendingProductMaterial'] == ['client-ca-preparation']
    v['relay_intent_preflight_installed_revision'] = 'a' * 40
    with pytest.raises(host.HostPreflightError, match='HOST_CLIENT_CA_MISSING'): f['inspect']()


def test_original_app_qualifier_uses_only_desired_identity_and_sanitized_metadata_token_probe():
    seen = []
    settings = {'role': 'writer', 'appId': '101', 'installationId': '201', 'slug': 'synthetic-writer',
                'actor': 'synthetic-writer[bot]', 'repository': 'example-org/sample', 'key': '/protected/key.pem', 'mode': '0600'}
    def execute(argv, *, env):
        seen.append((argv, env))
        return subprocess.CompletedProcess(argv, 0, b'APP_QUALIFICATION_PASS role=writer\n', b'')
    host.qualify_app('/candidate', settings, execute=execute)
    assert seen[0][1]['RELAY_TOKEN_PERMISSIONS'] == 'metadata:read'
    assert set(seen[0][1]) <= {'PATH', 'LANG', 'LC_ALL', 'OPENSSL_CONF', 'RELAY_APP_ROLE', 'GITHUB_APP_ID',
        'GITHUB_APP_INSTALLATION_ID', 'RELAY_EXPECTED_APP_SLUG', 'RELAY_EXPECTED_ACTOR', 'RELAY_EXPECTED_REPOSITORY',
        'GITHUB_APP_PRIVATE_KEY_FILE', 'RELAY_EXPECTED_KEY_MODE', 'RELAY_EXPECTED_WRITE_PERMISSION_NAMES', 'RELAY_TOKEN_PERMISSIONS'}
    assert seen[0][0][-1].endswith('/relay-app-qualification.py')


def test_client_ca_material_uses_owning_source_pins_and_rejects_credential_residue(tmp_path):
    key, certificate = tmp_path / 'ca-key.pem', tmp_path / 'ca.pem'
    subprocess.run(['/usr/bin/openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
        '-subj', '/CN=Synthetic CA', '-addext', 'basicConstraints=critical,CA:TRUE',
        '-keyout', str(key), '-out', str(certificate)], check=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    output = subprocess.run(['/usr/bin/openssl', 'x509', '-in', str(certificate), '-noout', '-fingerprint', '-sha256'],
                            capture_output=True, check=True).stdout.decode()
    fingerprint = output.strip().split('=')[1].replace(':', '').upper()
    source = tmp_path / 'candidate/deploy/ansible/tools/tls-webroot-bootstrap.py'
    source.parent.mkdir(parents=True)
    source.write_text('OPENAI_CAS = (("synthetic.pem", "https://example.invalid/unused", "' + fingerprint + '"),)\n')
    host.qualify_ca(tmp_path / 'candidate', certificate)
    certificate.write_bytes(certificate.read_bytes() + b'PRIVATE KEY synthetic-private-canary\n')
    with pytest.raises(host.HostPreflightError, match='HOST_CLIENT_CA_INVALID'):
        host.qualify_ca(tmp_path / 'candidate', certificate)


def test_pool_bridge_uses_actual_source_cli_and_exact_service_template(tmp_path):
    source = tmp_path / 'candidate'
    template = source / 'deploy/ansible/roles/relay_runner/templates/relay-managed-pool.service.j2'
    template.parent.mkdir(parents=True); template.write_text('literal selected template\n')
    seen = []
    def execute(argv, *, input):
        seen.append((argv, json.loads(input)))
        return subprocess.CompletedProcess(argv, 0, b'{"status":"PASS","createParents":[],"members":{}}', b'')
    result = host.qualify_pool(source, {'version': 1}, execute=execute)
    assert result['status'] == 'PASS'
    assert seen[0][0] == ['/usr/bin/python3', '-I', '-B', str(source / 'deploy/managed_pool.py'), '--preflight']
    assert seen[0][1] == {'contract': {'version': 1}, 'unitTemplate': 'literal selected template\n'}


def test_actual_owning_pool_installation_plan_blocks_unowned_registration_and_binds_plan_changes(target):
    from test_managed_pool import install_fixture, fixture_file, pool
    f = target; contract, template, arguments, member = install_fixture(f['root'])
    v = f['values']; v['relay_general_runner_pool'] = contract
    account = f['users'][v['relay_general_runner_user']]
    account.update(uid=arguments['runner_uid'], gid=arguments['runner_uid'], groups=[arguments['runner_uid'], 3000])
    f['groups'][v['relay_general_runner_user']] = arguments['runner_uid']
    def owning_plan(source, actual_contract, *, execute):
        assert actual_contract == contract
        return pool.installation_plan(actual_contract, template, **arguments)
    before = snapshot(f['root'])
    first = f['inspect'](pool_qualifier=owning_plan)
    assert snapshot(f['root']) == before
    # A changed but valid owning plan is part of the final prerequisite binding.
    (f['path'](member['state']) / 'home').rmdir()
    assert f['inspect'](pool_qualifier=owning_plan)['observedSha256'] != first['observedSha256']
    fixture_file(f['root'], member['root'] + '/.runner', '{}', arguments['runner_uid'])
    fixture_file(f['root'], member['root'] + '/.credentials', 'synthetic private reference', arguments['runner_uid'])
    before = snapshot(f['root'])
    with pytest.raises(pool.PoolError, match='INSTALL_UNOWNED_REGISTRATION'):
        f['inspect'](pool_qualifier=owning_plan)
    assert snapshot(f['root']) == before


def test_cli_failure_is_one_bounded_json_without_raw_input_or_traceback():
    for raw in [b'{"values":{"private":"synthetic-private-canary"},"sourceRoot":"/private/candidate"}',
                b'{' + b'x' * (host.MAX_INPUT + 1)]:
        result = subprocess.run(['/usr/bin/python3', '-I', str(DEPLOY / 'host_preflight.py'), '--input'],
            input=raw, capture_output=True, check=False, timeout=30)
        assert result.returncode == 1
        assert result.stderr == b'' and len(result.stdout.splitlines()) == 1 and len(result.stdout) < 1024
        assert json.loads(result.stdout)['status'] == 'FAIL'
        assert b'synthetic-private-canary' not in result.stdout and b'/private/candidate' not in result.stdout
