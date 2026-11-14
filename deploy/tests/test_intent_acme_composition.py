"""Fresh scheduler coupled to the real target TLS preflight on isolated Linux files."""
import copy
import os
import sys

import pytest

from test_host_preflight import target
from test_intent_install import (ROOT, TARGET, fresh_report, install, invocation,
                                 native_composition, revise_config)


pytestmark = pytest.mark.skipif(sys.platform != 'linux' or os.geteuid() != 0,
                                reason='root Linux metadata qualification required')


def acme_composition(invocation, monkeypatch, target):
    args, config, _, _ = invocation
    config['environment']['tls'] = {'acme': {'email': 'owner@example.invalid',
        'challenge': 'webroot', 'webroot': '/srv/shared/webroot'}}
    revise_config(invocation)
    before = fresh_report()
    before['protectedState'] = [row for row in before['protectedState']
        if row['name'] not in ['tls-certificateFile', 'tls-privateKeyFile', 'openai-client-ca']]
    state, calls, fail, primitive = native_composition(invocation, monkeypatch, before)
    values = target['values']
    values.update(relay_tls_acme_configured=True, relay_tls_acme_method='webroot',
        relay_tls_acme_webroot='/srv/shared/webroot', relay_tls_acme_email='owner@example.invalid',
        relay_tls_public_addresses=['192.0.2.10'])
    for name in ['relay_nginx_server_certificate_file', 'relay_nginx_server_private_key_file',
                 'relay_tls_client_ca_file']:
        target['path'](values[name]).unlink()
    probes = []
    def coupled(inner):
        if inner.phase in ['bootstrap', 'apply']:
            values['relay_intent_expected_installed_revision'] = inner.intent_expected_installed_revision
            result = target['inspect'](resolve_dns=lambda *_: [(2, 1, 6, '', ('192.0.2.10', 80))])
            probes.append((inner.phase, result['pendingProductMaterial']))
        primitive(inner)
        if inner.phase == 'tls-prepare':
            target['write'](values['relay_tls_client_ca_file'], b'synthetic public CA', 0o640)
        if inner.phase == 'tls-issue':
            target['write'](values['relay_nginx_server_certificate_file'], b'synthetic certificate', 0o644)
            target['write'](values['relay_nginx_server_private_key_file'], b'synthetic private key')
            state['protectedState'] += [{'name': name, 'status': 'reusable-metadata'}
                for name in ['tls-certificateFile', 'tls-privateKeyFile', 'openai-client-ca']]
    return state, calls, fail, coupled, probes


def test_unassisted_acme_scheduler_reaches_existing_install_preflight_with_issued_pair(
        invocation, monkeypatch, target):
    args, _, _, _ = invocation
    state, calls, _, primitive, probes = acme_composition(invocation, monkeypatch, target)
    install.run(args, primitive, ROOT, {'revision': TARGET})
    assert probes == [('bootstrap', ['tls-acme-issuance', 'client-ca-preparation']), ('apply', [])]
    assert [call.phase for call in calls] == ['bootstrap', 'tls-prepare', 'tls-dry-run', 'tls-issue',
        'apply', 'tls-check', 'ingress', 'activate', 'runner-register', 'runner-enable', 'post-check']
    assert state['installed']['installationState']['stage'] == 'ready'


@pytest.mark.parametrize('phase', ['tls-prepare', 'tls-dry-run', 'tls-issue', 'apply'])
def test_failed_acme_composition_retains_pair_and_resumes_before_activation(
        invocation, monkeypatch, target, phase):
    args, _, receipt, _ = invocation
    state, calls, fail, primitive, probes = acme_composition(invocation, monkeypatch, target)
    fail['phase'] = phase
    with pytest.raises(RuntimeError, match='INJECTED_PHASE_FAILURE'):
        install.run(args, primitive, ROOT, {'revision': TARGET})
    pending = copy.deepcopy(state['installed']['installationState'])
    assert pending == {'schemaVersion': 1, 'stage': 'fresh-incomplete',
                       'pairSha256': install.pair_digest(receipt)}
    assert 'activate' not in [call.phase for call in calls]
    assert all(guard.releases == 1 for guard in args._test_guards)
    fail['phase'] = None
    calls.clear()
    probes.clear()
    receipt['workflow_run_id'] += 1
    install.run(args, primitive, ROOT, {'revision': TARGET})
    assert all(call.phase != 'bootstrap' for call in calls)
    assert probes == [('apply', [])]
    assert state['installed']['installationState'] == {**pending, 'stage': 'ready'}


@pytest.mark.parametrize('damage,error', [('missing', 'HOST_TLS_ISSUANCE_STAGE_REQUIRED'),
    ('partial', 'HOST_TLS_MATERIAL_PARTIAL'), ('lost-lock', 'HOST_LOCK_LOST')])
def test_readiness_apply_does_not_accept_missing_issuance_proof_or_lost_lock(
        invocation, monkeypatch, target, damage, error):
    args, _, _, _ = invocation
    state, calls, _, primitive, _ = acme_composition(invocation, monkeypatch, target)
    def damaged(inner):
        primitive(inner)
        if inner.phase == 'tls-issue':
            if damage == 'lost-lock':
                inner._intent_host_guard.lost = True
            else:
                target['path'](target['values']['relay_nginx_server_certificate_file']).unlink()
                if damage == 'missing':
                    target['path'](target['values']['relay_nginx_server_private_key_file']).unlink()
    with pytest.raises(RuntimeError, match=error):
        install.run(args, damaged, ROOT, {'revision': TARGET})
    assert state['installed']['installationState']['stage'] == 'fresh-incomplete'
    assert 'apply' not in [call.phase for call in calls]
    assert 'activate' not in [call.phase for call in calls]
    assert all(guard.releases == 1 for guard in args._test_guards)


@pytest.mark.parametrize('retained', ['certificate', 'private-key'])
def test_existing_install_partial_tls_pair_refuses_even_with_acme_configured(target, retained):
    import host_preflight as host
    values = target['values']
    values.update(relay_intent_expected_installed_revision=TARGET, relay_tls_acme_configured=True)
    missing = ('relay_nginx_server_private_key_file' if retained == 'certificate'
               else 'relay_nginx_server_certificate_file')
    target['path'](values[missing]).unlink()
    with pytest.raises(host.HostPreflightError, match='HOST_TLS_MATERIAL_PARTIAL'):
        target['inspect']()
