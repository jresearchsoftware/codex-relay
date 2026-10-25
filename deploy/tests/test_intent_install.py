"""Ordinary Git desired-state installation and preserved strategy boundaries."""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
import intent_install as install
import inventory
import workflow_projection
import clean_reinstall
from test_clean_reinstall import installation, git_installation_snapshot


TARGET = 'b' * 40
PREVIOUS = 'a' * 40
CONTRACT = json.loads((ROOT / 'deploy/installation-contract.json').read_text())


class Guard:
    def __init__(self):
        self.stdin, self.closed, self.lost, self.releases = self, False, False, 0
    def poll(self):
        return 1 if self.lost else 0 if self.closed else None
    def close(self):
        self.closed, self.releases = True, self.releases + 1
    def wait(self, timeout):
        return 0


def fresh_report():
    return {'blockers': [], 'installed': {'status': 'missing'},
        'runners': {'production': {'status': 'reusable'}, 'general': {'status': 'reusable'}},
        'protectedState': [{'name': name, 'status': 'reusable-metadata'} for name in [
            'reviewer-installed-key', 'writer-installed-key', 'codex-installed-token',
            'openai-client-ca', 'tls-certificateFile', 'tls-privateKeyFile']]}


def observed(revision=PREVIOUS, metadata=None):
    installed = {'status': 'present', 'revision': revision}
    if metadata is not None:
        installed['deploymentContract'] = metadata
    return {'blockers': [], 'installed': installed, 'configuration': {'status': 'different'}}


def planned(report, legacy=lambda *_: 'upgrade'):
    return install.plan(report, TARGET, CONTRACT, root=ROOT,
                        repository='example/product', legacy=legacy)


def test_fresh_install_does_not_require_prior_projection_or_snapshot():
    result = planned({'blockers': [], 'installed': {'status': 'missing'}})
    assert result == {'strategy': 'fresh', 'phase': 'bootstrap', 'installed': 'none'}


def test_same_product_config_change_selects_reconciliation():
    assert planned(observed(TARGET))['strategy'] == 'reconcile'


@pytest.mark.parametrize('configuration', ['different', 'invalid', 'consumer-equivalent', 'unavailable'])
def test_effective_drift_or_missing_historical_snapshot_selects_reconcile(invocation, configuration):
    _, _, receipt, _ = invocation
    report = observed(TARGET, CONTRACT)
    report['installed']['gitConfigReceipt'] = copy.deepcopy(receipt)
    report['configuration']['status'] = configuration
    result = install.plan(report, TARGET, CONTRACT, root=ROOT, repository='example/product', receipt=receipt)
    assert result['strategy'] == 'reconcile' and result['phase'] == 'apply'


def test_new_config_commit_with_identical_content_is_a_new_git_pair(invocation):
    _, _, receipt, _ = invocation
    report = observed(TARGET, CONTRACT)
    report['configuration']['status'] = 'equivalent'
    report['installed']['gitConfigReceipt'] = copy.deepcopy(receipt)
    selected = {**receipt, 'config_sha': 'e' * 40}
    result = install.plan(report, TARGET, CONTRACT, root=ROOT, repository='example/product', receipt=selected)
    assert result['strategy'] == 'reconcile' and result['phase'] == 'apply'


def test_code_only_new_product_revision_still_selects_upgrade(invocation):
    _, _, receipt, _ = invocation
    report = observed(PREVIOUS, CONTRACT)
    report['configuration']['status'] = 'equivalent'
    report['installed']['gitConfigReceipt'] = {**receipt, 'product_sha': PREVIOUS}
    result = install.plan(report, TARGET, CONTRACT, root=ROOT, repository='example/product', receipt=receipt)
    assert result['strategy'] == 'upgrade' and result['phase'] == 'upgrade'


def test_epoch_metadata_selects_upgrade_without_per_commit_entries():
    assert planned(observed(metadata=CONTRACT))['strategy'] == 'upgrade'
    older = copy.deepcopy(CONTRACT)
    older['capabilities'].remove('lifecycle-v1')
    assert planned(observed(metadata=older))['strategy'] == 'reinstall'


@pytest.mark.parametrize('metadata', [
    {**CONTRACT, 'epoch': 2}, {**CONTRACT, 'epoch': True},
    {**CONTRACT, 'future': 'ignored'},
    {**CONTRACT, 'capabilities': [*CONTRACT['capabilities'], 'unknown-v1']},
    {**CONTRACT, 'capabilities': ['lifecycle-v1', 'lifecycle-v1']},
])
def test_unknown_or_tampered_metadata_never_selects_mutation(metadata):
    with pytest.raises(ValueError, match='COMPATIBILITY_METADATA_INVALID|TRANSITION_UNSUPPORTED'):
        planned(observed(TARGET, metadata))


@pytest.mark.parametrize('blocker', ['runner-general-ambiguous', 'configuration-invalid',
    'clean-reinstall-recovery-present;inspect-before-retry'])
def test_blocker_strings_are_not_recovery_proof(blocker):
    report = observed()
    report['blockers'].append(blocker)
    with pytest.raises(ValueError, match='TARGET_UNSAFE|RECOVERY_REQUIRES_DIAGNOSIS'):
        planned(report)


def test_invalid_effective_json_is_only_provisional_strategy_input():
    report = observed(TARGET, CONTRACT)
    report['blockers'] = ['installed-consumer-configuration-invalid']
    report['configuration'] = {'status': 'invalid', 'consumer': 'invalid'}
    original = copy.deepcopy(report)
    assert planned(report)['strategy'] == 'reconcile'
    assert report == original
    for additional in ['runner-general-ambiguous', 'installed-identity-invalid']:
        report['blockers'] = [*original['blockers'], additional]
        with pytest.raises(ValueError, match='TARGET_UNSAFE'):
            planned(report)
    report = {**original, 'installed': {'status': 'missing'}}
    with pytest.raises(ValueError, match='TARGET_UNSAFE'):
        planned(report)


def test_legacy_lineage_is_a_single_classifier_not_a_sha_pair_table():
    calls = []
    def legacy(root, repository, revision):
        calls.append((root, repository, revision))
        return 'reinstall'
    assert planned(observed(), legacy)['strategy'] == 'reinstall'
    assert calls == [(ROOT, 'example/product', PREVIOUS)]


@pytest.mark.parametrize('status,merge_base,expected', [
    ('ahead', install.LEGACY_LIFECYCLE_BOUNDARY, 'upgrade'), ('behind', PREVIOUS, 'reinstall')])
def test_legacy_compare_uses_metadata_page_without_unbounded_first_page_files(monkeypatch, status, merge_base, expected):
    requested = []
    monkeypatch.setattr(install.subprocess, 'run', lambda *_args, **_options: SimpleNamespace(returncode=1))
    class Response:
        status = 200
        def read(self, limit):
            assert limit == 1048577
            return json.dumps({'base_commit': {'sha': install.LEGACY_LIFECYCLE_BOUNDARY},
                'status': status, 'merge_base_commit': {'sha': merge_base}, 'files': []}).encode()
    class Connection:
        def request(self, method, url, headers):
            assert method == 'GET' and url.endswith('?per_page=1&page=2')
            requested.append(url)
        def getresponse(self):
            return Response()
        def close(self):
            pass
    monkeypatch.setattr(install.http.client, 'HTTPSConnection', lambda *_args, **_options: Connection())
    assert install.legacy_strategy(ROOT, 'example/product', PREVIOUS) == expected
    assert requested == ['/repos/example/product/compare/' + install.LEGACY_LIFECYCLE_BOUNDARY
                         + '...' + PREVIOUS + '?per_page=1&page=2']


@pytest.fixture
def invocation(tmp_path, monkeypatch):
    config = json.loads((ROOT / 'deploy/example.json').read_text())
    config['target']['connection'] = 'local'
    config['environment']['localApply'] = {'source': 'git', 'repository': 'example/deployment',
                                           'configPath': 'prod/relay.json'}
    raw = json.dumps(config).encode()
    path = tmp_path / 'relay.json'
    path.write_bytes(raw)
    receipt = {'config_repository': 'example/deployment', 'config_repository_id': 4,
        'config_sha': 'c' * 40, 'config_blob_sha': 'd' * 40, 'config_path': 'prod/relay.json',
        'config_sha256': hashlib.sha256(raw).hexdigest(), 'product_repository': 'example/codex-relay',
        'product_repository_id': 5, 'product_sha': TARGET, 'workflow_run_id': 7, 'action': 'apply',
        'source_policy': 'accepted-main'}
    assert install.source_repository(config) == receipt['product_repository']
    args = argparse.Namespace(config=path, resolved_revision=TARGET, git_intent=receipt,
        git_config_receipt=None, connection='local', consumer_root=tmp_path,
        projection_output=None, log_root=tmp_path, authorize_upgrade=False,
        authorize_bootstrap=False, authorize_reinstall=False)
    monkeypatch.setattr(install, 'qualify_target', lambda *_: None)
    monkeypatch.setattr(install, 'loads', lambda text, _: json.loads(text))
    import install_recovery
    monkeypatch.setattr(install_recovery, 'remote_probe', lambda *_args: None)
    artifact = {'directory': str(tmp_path / 'integration'), 'files': ['.github/workflows/route.yml'],
                'compatibility': 'missing'}
    monkeypatch.setattr(workflow_projection, 'integration', lambda *_: artifact, raising=False)
    args._test_guards, args._test_completed = [], False
    def holder(*_):
        guard = Guard()
        args._test_guards.append(guard)
        return guard
    monkeypatch.setattr(install, 'hold_install_guard', holder)
    def complete(*_):
        args._test_completed = True
        return {'schemaVersion': 1, 'stage': 'ready', 'pairSha256': install.pair_digest(receipt)}
    monkeypatch.setattr(install, 'complete_fresh', complete)
    return args, config, receipt, artifact


@pytest.mark.parametrize('old_revision', [None, PREVIOUS, TARGET])
def test_one_operation_binds_git_pair_and_produces_post_install_artifact(invocation, monkeypatch, capsys, old_revision):
    args, config, receipt, artifact = invocation
    before = (observed(old_revision, CONTRACT) if old_revision else
              fresh_report())
    after = observed(TARGET, CONTRACT)
    after['configuration']['status'] = 'equivalent'
    after['installed']['gitConfigReceipt'] = receipt
    initial = True
    def probe(*_args, **_kwargs):
        nonlocal initial
        if initial:
            initial = False
            return before
        if old_revision is None:
            after['installed']['installationState'] = {'schemaVersion': 1,
                'stage': 'ready' if args._test_completed else 'fresh-incomplete',
                'pairSha256': install.pair_digest(receipt)}
        return after
    monkeypatch.setattr(inventory, 'remote_inventory', probe)
    calls = []
    install.run(args, calls.append, ROOT, {'revision': TARGET})
    assert len(calls) == (10 if old_revision is None else 1)
    inner = calls[0]
    assert inner.git_intent == receipt and inner.intent_install
    assert inner.phase == ('bootstrap' if old_revision is None else 'apply' if old_revision == TARGET else 'upgrade')
    assert inner.intent_expected_installed_revision == (old_revision or 'none')
    assert all(guard.releases == 1 for guard in args._test_guards)
    if old_revision is not None:
        assert not args._test_completed
    output = capsys.readouterr().out
    assert 'RELAY_INSTALL_RESULT=' in output
    assert artifact['directory'] in output
    assert 'no installer rerun is required' in output


@pytest.mark.parametrize('old_revision', [PREVIOUS, TARGET])
@pytest.mark.parametrize('backend_record', [False, True])
def test_ordinary_install_uses_original_uuid_for_proven_same_target_recovery(
        invocation, monkeypatch, old_revision, backend_record):
    import install_recovery
    args, _, receipt, _ = invocation
    before = observed(old_revision, CONTRACT)
    if backend_record:
        before['blockers'] = [install_recovery.OPERATION_BLOCKER]
    after = observed(TARGET, CONTRACT)
    after['configuration']['status'] = 'equivalent'
    after['installed']['gitConfigReceipt'] = copy.deepcopy(receipt)
    calls = []
    monkeypatch.setattr(inventory, 'remote_inventory', lambda *_args, **_kwargs: after if calls else before)
    operation = '12345678-1234-4234-8234-123456789abc'
    def recovery_probe(_target, _key, _config, target, expected, guard, pool_guard):
        assert target == TARGET and expected == old_revision and guard.poll() is None
        assert pool_guard is None
        assert not calls, 'the held-lock proof must precede every mutation'
        return {'operationId': operation, 'target': target, 'installedRevision': expected}
    monkeypatch.setattr(install_recovery, 'remote_probe', recovery_probe)
    install.run(args, calls.append, ROOT, {'revision': TARGET})
    assert len(calls) == 1
    inner = calls[0]
    assert inner.phase == 'upgrade' and inner.authorize_upgrade
    assert inner.authorize_lifecycle_recovery and inner.lifecycle_recovery_operation == operation
    assert inner._intent_recovery_proof == {'operationId': operation, 'target': TARGET,
                                          'installedRevision': old_revision}
    assert before['blockers'] == ([install_recovery.OPERATION_BLOCKER] if backend_record else [])


def test_provisional_backend_record_without_locked_recovery_proof_stops(invocation, monkeypatch):
    import install_recovery
    args, _, _, _ = invocation
    before = observed(PREVIOUS, CONTRACT)
    before['blockers'] = [install_recovery.OPERATION_BLOCKER]
    monkeypatch.setattr(inventory, 'remote_inventory', lambda *_args, **_kwargs: before)
    calls = []
    with pytest.raises(RuntimeError, match='RELAY_INSTALL_FAILED;stage=lifecycle-recovery-proof;cause=RELAY_INSTALL_RECOVERY_REQUIRES_DIAGNOSIS'):
        install.run(args, calls.append, ROOT, {'revision': TARGET})
    assert not calls
    assert before['blockers'] == [install_recovery.OPERATION_BLOCKER]


@pytest.mark.parametrize('damage', ['product', 'bytes', 'repository', 'secret'])
def test_wrong_pair_fails_before_target_access(invocation, monkeypatch, capsys, damage):
    args, _, receipt, _ = invocation
    if damage == 'product':
        receipt['product_sha'] = PREVIOUS
    elif damage == 'bytes':
        args.config.write_text('{}')
    elif damage == 'repository':
        receipt['config_repository'] = 'foreign/private'
    else:
        receipt['token'] = 'must-never-appear-in-output'
    monkeypatch.setattr(install, 'qualify_target', lambda *_: pytest.fail('target access before pair verification'))
    with pytest.raises(RuntimeError, match='RELAY_INSTALL_FAILED'):
        install.run(args, lambda *_: pytest.fail('mutation'), ROOT, {'revision': TARGET})
    output = capsys.readouterr().out
    assert '"hostMutation": false' in output
    assert 'must-never-appear-in-output' not in output


def test_missing_post_apply_pair_proof_never_reports_success(invocation, monkeypatch, capsys):
    args, _, _, _ = invocation
    after = observed(TARGET, CONTRACT)
    after['configuration']['status'] = 'equivalent'
    reports = iter([observed(TARGET, CONTRACT), after])
    monkeypatch.setattr(inventory, 'remote_inventory', lambda *_args, **_kwargs: next(reports))
    def primitive(inner):
        inner._intent_mutation_started = True
        inner._intent_log_path = '/tmp/protected-install.log'
    with pytest.raises(RuntimeError, match='GIT_PAIR_READBACK_UNPROVEN'):
        install.run(args, primitive, ROOT, {'revision': TARGET})
    output = capsys.readouterr().out
    assert '"hostMutation": "unknown"' in output
    assert '"automaticRetrySafe": false' in output
    assert '/tmp/protected-install.log' in output
    assert 'RELAY_INSTALL_RESULT=' not in output


def test_planner_failure_retains_proven_installed_revision(invocation, monkeypatch, capsys):
    args, _, _, _ = invocation
    monkeypatch.setattr(inventory, 'remote_inventory', lambda *_args, **_options: observed(PREVIOUS))
    monkeypatch.setattr(install, 'plan', lambda *_args, **_options: (_ for _ in ()).throw(
        ValueError('RELAY_INSTALL_LEGACY_COMPATIBILITY_UNPROVEN')))
    with pytest.raises(RuntimeError, match='LEGACY_COMPATIBILITY_UNPROVEN'):
        install.run(args, lambda *_: pytest.fail('mutation before strategy proof'), ROOT, {'revision': TARGET})
    failure = json.loads(capsys.readouterr().out.split('RELAY_INSTALL_FAILURE=')[1])
    assert failure['installed'] == PREVIOUS and failure['hostMutation'] is False


def test_backend_failure_uses_runtime_cause_and_preserves_mutation_stage_log(invocation, monkeypatch, capsys):
    from config import InvalidConfig
    args, _, _, _ = invocation
    monkeypatch.setattr(inventory, 'remote_inventory', lambda *_args, **_options: observed(PREVIOUS, CONTRACT))
    def primitive(inner):
        inner._intent_mutation_started = True
        inner._intent_log_path = '/tmp/protected-upgrade.log'
        raise InvalidConfig('INVALID_DEPLOYMENT_CONFIG:upgrade-apply-failed')
    with pytest.raises(RuntimeError, match='RELAY_INSTALL_UPGRADE_APPLY_FAILED'):
        install.run(args, primitive, ROOT, {'revision': TARGET})
    failure = json.loads(capsys.readouterr().out.split('RELAY_INSTALL_FAILURE=')[1])
    assert failure['cause'] == 'RELAY_INSTALL_UPGRADE_APPLY_FAILED'
    assert failure['stage'] == 'upgrade' and failure['installed'] == PREVIOUS
    assert failure['hostMutation'] == 'unknown' and failure['log'] == '/tmp/protected-upgrade.log'


@pytest.mark.parametrize('health_failure', [False, True])
def test_identical_git_pair_verifies_read_only_and_retains_original_attestation(
        invocation, monkeypatch, capsys, health_failure):
    args, _, receipt, _ = invocation
    attested = {**receipt, 'workflow_run_id': 5, 'action': 'original-apply'}
    report = observed(TARGET, CONTRACT)
    report['configuration']['status'] = 'equivalent'
    report['installed']['gitConfigReceipt'] = attested
    original = copy.deepcopy(report)
    config_bytes = args.config.read_bytes()
    monkeypatch.setattr(inventory, 'remote_inventory', lambda *_args, **_kwargs: copy.deepcopy(report))
    calls = []
    def primitive(inner):
        calls.append(inner)
        assert inner.phase == 'post-check'
        assert inner.git_intent == attested
        assert inner._intent_host_guard.poll() is None
        assert not any(value for name, value in vars(inner).items() if name.startswith('authorize_'))
        if health_failure:
            raise RuntimeError('POST_CHECK_HEALTH_UNPROVEN')
    if health_failure:
        with pytest.raises(RuntimeError, match='POST_CHECK_HEALTH_UNPROVEN'):
            install.run(args, primitive, ROOT, {'revision': TARGET})
    else:
        install.run(args, primitive, ROOT, {'revision': TARGET})
    assert len(calls) == 1 and args.config.read_bytes() == config_bytes and report == original
    assert not args._test_completed and args._test_guards[0].releases == 1
    output = capsys.readouterr().out
    plan = json.loads(next(line.split('=', 1)[1] for line in output.splitlines()
                           if line.startswith('RELAY_INSTALL_PLAN=')))
    assert plan['strategy'] == 'verify' and plan['dispatch_run_id'] == 7 and plan['attested_run_id'] == 5
    if health_failure:
        failure = json.loads(output.split('RELAY_INSTALL_FAILURE=')[1])
        assert failure['hostMutation'] is False and 'RELAY_INSTALL_RESULT=' not in output


def test_historical_additive_product_metadata_does_not_change_active_serial_contract():
    """The actual historical sources are source evidence, not copied fixtures."""
    try:
        old = subprocess.run(['git', '-C', str(ROOT), 'show',
            'f6947853079dc108d31b87e89da727206c7ce968:deploy/workflows/contract.json'],
            check=True, capture_output=True, text=True).stdout
        target = subprocess.run(['git', '-C', str(ROOT), 'show',
            'f6431d612d464c511fdda97e7dea64ace7f03ac7:deploy/workflows/contract.json'],
            check=True, capture_output=True, text=True).stdout
    except subprocess.CalledProcessError:
        pytest.skip('historical accepted Git objects unavailable in this checkout')
    assert json.loads(old) == {'workflowContract': 'relay-workflows-v3'}
    assert json.loads(target) == {'workflowContract': 'relay-workflows-v3',
                                  'parallelWorkflowContract': 'relay-workflows-v4'}
    assert planned(observed('f6947853079dc108d31b87e89da727206c7ce968'),
                   legacy=lambda *_: 'upgrade')['strategy'] == 'upgrade'


def test_legacy_hardening_uses_selected_source_and_live_host_mutex(monkeypatch):
    config = {'environment': {'namespace': 'example'}}
    guard = SimpleNamespace(poll=lambda: None)
    calls = []
    def target(target, key, config, revision, **options):
        calls.append((target, key, config, revision, options))
        return {'state': 'PREPARED', 'namespace': 'example', 'hardened': True}
    monkeypatch.setattr(clean_reinstall, 'remote_action', target)
    assert install.prepare_target('target', 'key', config, TARGET, guard)
    assert calls == [('target', 'key', config, TARGET, {'action': 'prepare', 'guard': guard, 'git_desired': True})]
    with pytest.raises(ValueError, match='HOST_LOCK_LOST'):
        install.prepare_target('target', 'key', config, TARGET, SimpleNamespace(poll=lambda: 1))
    assert len(calls) == 1


def native_composition(invocation, monkeypatch, before=None):
    args, config, receipt, _ = invocation
    state = copy.deepcopy(before or fresh_report())
    calls = []
    fail = {'phase': None, 'after': None}
    def probe(*_args, **_options):
        return copy.deepcopy(state)
    def primitive(inner):
        assert inner._intent_host_guard.poll() is None
        assert inner.git_intent == args.git_intent
        calls.append(argparse.Namespace(**vars(inner)))
        if inner.phase == fail['phase']:
            raise RuntimeError('INJECTED_PHASE_FAILURE')
        if inner.phase in ['bootstrap', 'apply', 'upgrade']:
            inner._intent_mutation_started = True
            state.update(configuration={'status': 'equivalent'})
            state['installed'] = {'status': 'present', 'revision': TARGET,
                'deploymentContract': CONTRACT, 'gitConfigReceipt': copy.deepcopy(inner.git_intent)}
            if inner._intent_installation_state:
                state['installed']['installationState'] = copy.deepcopy(inner._intent_installation_state)
        if inner.phase.endswith('-credentials'):
            role = inner.phase.removesuffix('-credentials')
            name = role + ('-installed-token' if role == 'codex' else '-installed-key')
            state['protectedState'] = [row for row in state.get('protectedState', []) if row['name'] != name]
            state['protectedState'].append({'name': name, 'status': 'reusable-metadata'})
        if inner.phase == 'runner-register':
            state['runners']['production'] = {'status': 'reusable'}
        if inner.phase == 'general-runner-register':
            state['runners']['general'] = {'status': 'reusable'}
        if fail['after']:
            fail['after'](inner, state)
    def complete(_target, _key, _config, _revision, wanted, guard, pool_guard):
        assert guard.poll() is None
        ready = {'schemaVersion': 1, 'stage': 'ready', 'pairSha256': install.pair_digest(wanted)}
        state['installed']['installationState'] = ready
        return ready
    monkeypatch.setattr(inventory, 'remote_inventory', probe)
    monkeypatch.setattr(install, 'complete_fresh', complete)
    return state, calls, fail, primitive


def revise_config(invocation):
    args, config, receipt, _ = invocation
    raw = json.dumps(config).encode()
    args.config.write_bytes(raw)
    receipt['config_sha256'] = hashlib.sha256(raw).hexdigest()


def test_fresh_install_composes_all_configured_phases_and_isolates_optional_tokens(invocation, monkeypatch, capsys):
    args, config, receipt, _ = invocation
    for role in ['reviewer', 'writer', 'codex']:
        config['environment'][role + 'Credential'] = {
            'sourceTokenFile' if role == 'codex' else 'sourceKeyFile': '/private/' + role}
    config['environment']['tls'] = {'acme': {'email': 'owner@example.invalid',
        'challenge': 'webroot', 'webroot': '/srv/shared/acme'}}
    revise_config(invocation)
    before = fresh_report()
    before['protectedState'] = [{'name': role + '-source', 'status': 'reusable-metadata'}
                               for role in ['reviewer', 'writer', 'codex']]
    before['runners'] = {'production': {'status': 'missing'}, 'general': {'status': 'missing'}}
    args.runner_registration_token = 'ephemeral-production-value'
    args.general_runner_registration_token = 'ephemeral-general-value'
    state, calls, _, primitive = native_composition(invocation, monkeypatch, before)
    install.run(args, primitive, ROOT, {'revision': TARGET})
    assert [call.phase for call in calls] == ['bootstrap', 'reviewer-credentials', 'writer-credentials',
        'codex-credentials', 'apply', 'tls-prepare', 'tls-dry-run', 'tls-issue', 'tls-check',
        'ingress', 'activate', 'runner-register', 'runner-enable', 'general-runner-register',
        'general-runner-enable', 'post-check']
    for call in calls:
        enabled = {name for name, value in vars(call).items() if name.startswith('authorize_') and value}
        expected = {'activate': 'authorize_reviewer_activation'}.get(call.phase,
            'authorize_' + call.phase.replace('-', '_'))
        assert enabled == (set() if call.phase in ['apply', 'tls-check', 'post-check'] else {expected})
        assert call.git_intent == receipt and call.resolved_revision == TARGET
        assert call._intent_fresh_bootstrap == (call.phase == 'bootstrap')
        assert call.runner_registration_token == ('ephemeral-production-value' if call.phase == 'runner-register' else None)
        assert call.general_runner_registration_token == ('ephemeral-general-value' if call.phase == 'general-runner-register' else None)
    assert state['installed']['installationState']['stage'] == 'ready'
    assert all(guard.releases == 1 for guard in args._test_guards)
    output = capsys.readouterr().out
    assert 'ephemeral-production-value' not in output and 'ephemeral-general-value' not in output


def test_false_publication_still_activates_reviewer_and_reuses_validated_registrations(invocation, monkeypatch):
    args, config, _, _ = invocation
    config['environment']['instance'] = {'reviewerPort': 18787, 'publicationEnabled': False}
    revise_config(invocation)
    before = fresh_report()
    before['protectedState'] = [row for row in before['protectedState'] if row['name'] != 'writer-installed-key']
    args.runner_registration_token = 'unused-production-token'
    args.general_runner_registration_token = 'unused-general-token'
    _, calls, _, primitive = native_composition(invocation, monkeypatch, before)
    install.run(args, primitive, ROOT, {'revision': TARGET})
    assert 'activate' in [call.phase for call in calls]
    assert 'writer-credentials' not in [call.phase for call in calls]
    assert all(call.runner_registration_token is None and call.general_runner_registration_token is None for call in calls)
    assert config['environment']['instance']['publicationEnabled'] is False


def test_explicit_reviewer_only_needs_no_writer_codex_or_registration_inputs(invocation, monkeypatch, capsys):
    args, config, _, _ = invocation
    config['environment']['instance'] = {'reviewerPort': 18787, 'publicationEnabled': False}
    config['environment']['codexTokenRequired'] = False
    revise_config(invocation)
    before = fresh_report()
    before['protectedState'] = [row for row in before['protectedState']
        if row['name'] not in ['writer-installed-key', 'codex-installed-token']]
    before['runners'] = {'production': {'status': 'missing'}, 'general': {'status': 'missing'}}
    _, calls, _, primitive = native_composition(invocation, monkeypatch, before)
    install.run(args, primitive, ROOT, {'revision': TARGET})
    assert [call.phase for call in calls] == ['bootstrap', 'apply', 'tls-check', 'ingress', 'activate', 'post-check']
    result = json.loads(capsys.readouterr().out.split('RELAY_INSTALL_RESULT=')[1])
    assert result['readiness'] == 'reviewer-only'


@pytest.mark.parametrize('missing,code', [('reviewer-installed-key', 'REVIEWER_CREDENTIAL_REQUIRED'),
    ('writer-installed-key', 'WRITER_CREDENTIAL_REQUIRED'), ('codex-installed-token', 'CODEX_CREDENTIAL_REQUIRED'),
    ('tls-privateKeyFile', 'TLS_CERTIFICATE_REQUIRED')])
def test_missing_external_fresh_prerequisite_returns_one_precise_handoff_before_mutation(
        invocation, monkeypatch, capsys, missing, code):
    args, _, _, _ = invocation
    before = fresh_report()
    before['protectedState'] = [row for row in before['protectedState'] if row['name'] != missing]
    _, calls, _, primitive = native_composition(invocation, monkeypatch, before)
    with pytest.raises(RuntimeError, match=code):
        install.run(args, primitive, ROOT, {'revision': TARGET})
    assert calls == [] and args._test_guards == []
    failure = json.loads(capsys.readouterr().out.split('RELAY_INSTALL_FAILURE=')[1])
    assert failure['hostMutation'] is False and code in failure['cause']
    assert failure['next'].startswith('Provide the configured protected')


def test_failed_fresh_install_resumes_exact_pair_with_new_run_without_skipping_completion(invocation, monkeypatch):
    args, config, receipt, _ = invocation
    config['environment']['reviewerCredential'] = {'sourceKeyFile': '/private/reviewer'}
    revise_config(invocation)
    before = fresh_report()
    before['protectedState'] = [row for row in before['protectedState'] if row['name'] != 'reviewer-installed-key']
    before['protectedState'].append({'name': 'reviewer-source', 'status': 'reusable-metadata'})
    state, calls, fail, primitive = native_composition(invocation, monkeypatch, before)
    fail['phase'] = 'reviewer-credentials'
    with pytest.raises(RuntimeError, match='INJECTED_PHASE_FAILURE'):
        install.run(args, primitive, ROOT, {'revision': TARGET})
    pending = copy.deepcopy(state['installed']['installationState'])
    assert pending['stage'] == 'fresh-incomplete'
    receipt['workflow_run_id'] = 8
    fail['phase'] = None
    calls.clear()
    install.run(args, primitive, ROOT, {'revision': TARGET})
    assert calls[0].phase == 'reviewer-credentials'
    assert 'bootstrap' not in [call.phase for call in calls]
    assert 'activate' in [call.phase for call in calls] and calls[-1].phase == 'post-check'
    assert state['installed']['gitConfigReceipt']['workflow_run_id'] == 8
    assert state['installed']['installationState'] == {**pending, 'stage': 'ready'}
    assert all(guard.releases == 1 for guard in args._test_guards)


def test_incomplete_fresh_install_cannot_be_retargeted(invocation, monkeypatch):
    args, _, receipt, _ = invocation
    before = observed(TARGET, CONTRACT)
    before['installed']['installationState'] = {'schemaVersion': 1,
        'stage': 'fresh-incomplete', 'pairSha256': '0' * 64}
    _, calls, _, primitive = native_composition(invocation, monkeypatch, before)
    with pytest.raises(RuntimeError, match='INCOMPLETE_FRESH_GIT_PAIR_CHANGED'):
        install.run(args, primitive, ROOT, {'revision': TARGET})
    assert calls == [] and args._test_guards == []


def test_existing_same_pair_ready_marker_is_preserved_without_reactivation(invocation, monkeypatch):
    args, _, receipt, _ = invocation
    before = observed(TARGET, CONTRACT)
    ready = {'schemaVersion': 1, 'stage': 'ready', 'pairSha256': install.pair_digest(receipt)}
    before['installed']['installationState'] = ready
    state, calls, _, primitive = native_composition(invocation, monkeypatch, before)
    install.run(args, primitive, ROOT, {'revision': TARGET})
    assert [call.phase for call in calls] == ['apply']
    assert calls[0]._intent_installation_state == ready
    assert state['installed']['installationState'] == ready


def test_incomplete_fresh_continuation_can_replace_bad_historical_snapshot(invocation, monkeypatch):
    args, config, receipt, _ = invocation
    config['environment']['reviewerCredential'] = {'sourceKeyFile': '/private/reviewer'}
    revise_config(invocation)
    before = fresh_report()
    before['installed'] = {'status': 'present', 'revision': TARGET, 'gitConfigReceipt': copy.deepcopy(receipt),
        'installationState': {'schemaVersion': 1, 'stage': 'fresh-incomplete', 'pairSha256': install.pair_digest(receipt)}}
    before['configuration'] = {'status': 'invalid', 'consumer': 'equivalent', 'deployment': 'invalid'}
    before['protectedState'] = [row for row in before['protectedState'] if row['name'] != 'reviewer-installed-key']
    before['protectedState'].append({'name': 'reviewer-source', 'status': 'reusable-metadata'})
    state, calls, _, primitive = native_composition(invocation, monkeypatch, before)
    install.run(args, primitive, ROOT, {'revision': TARGET})
    assert [call.phase for call in calls[:2]] == ['reviewer-credentials', 'apply']
    assert state['installed']['installationState']['stage'] == 'ready'


@pytest.mark.parametrize('change', ['identity', 'config-bytes', 'guard-lost'])
def test_change_between_fresh_phases_stops_before_activation(invocation, monkeypatch, change):
    args, _, _, _ = invocation
    _, calls, fail, primitive = native_composition(invocation, monkeypatch)
    def damage(inner, state):
        if inner.phase != 'bootstrap':
            return
        if change == 'identity':
            state['installed']['revision'] = PREVIOUS
        elif change == 'config-bytes':
            args.config.write_text('{}')
        else:
            inner._intent_host_guard.lost = True
    fail['after'] = damage
    with pytest.raises(RuntimeError, match='READBACK_UNPROVEN|CONFIG_BYTES_CHANGED|HOST_LOCK_LOST'):
        install.run(args, primitive, ROOT, {'revision': TARGET})
    assert [call.phase for call in calls] == ['bootstrap']
    assert all(guard.releases == 1 for guard in args._test_guards)


def manifest_fixture(value):
    git_installation_snapshot(value)
    release = value.paths['install'] / 'current'
    snapshot = (release / 'deployment-config.json').read_bytes()
    receipt = {'product_repository': 'example/product', 'product_sha': PREVIOUS,
        'config_sha256': hashlib.sha256(snapshot).hexdigest(), 'config_repository': 'example/deployment',
        'config_sha': 'c' * 40, 'config_blob_sha': 'd' * 40, 'config_path': 'prod/relay.json'}
    marker = {'schemaVersion': 1, 'stage': 'fresh-incomplete', 'pairSha256': install.pair_digest(receipt)}
    path = release / 'artifact-manifest.json'
    manifest = json.loads(path.read_text())
    manifest.update(installedRevision=PREVIOUS, resolvedRevision=PREVIOUS,
                    gitConfigReceipt=receipt, installationState=marker, preserved='original-evidence')
    path.write_text(json.dumps(manifest))
    path.chmod(0o640)
    payload = {'namespace': value.config['environment']['namespace'], 'revision': PREVIOUS,
        'receipt': receipt, 'deploymentConfigSha256': hashlib.sha256(snapshot).hexdigest()}
    return path, payload


def test_actual_protected_manifest_completion_preserves_attestation_and_is_idempotent(installation):
    value = installation
    path, payload = manifest_fixture(value)
    before = path.stat()
    ready = install.finalize_fresh_manifest(payload, root=value.root, owner_uid=os.getuid())
    contents = json.loads(path.read_bytes())
    assert contents['preserved'] == 'original-evidence'
    assert contents['gitConfigReceipt'] == payload['receipt']
    assert contents['installationState'] == ready and ready['stage'] == 'ready'
    assert (path.stat().st_mode, path.stat().st_uid, path.stat().st_gid) == (before.st_mode, before.st_uid, before.st_gid)
    data, inode = path.read_bytes(), path.stat().st_ino
    assert install.finalize_fresh_manifest(payload, root=value.root, owner_uid=os.getuid()) == ready
    assert path.read_bytes() == data and path.stat().st_ino == inode


@pytest.mark.parametrize('damage', ['pair', 'snapshot', 'source-tree', 'manifest-link'])
def test_actual_manifest_completion_rejects_changed_identity_without_mutation(installation, damage):
    value = installation
    path, payload = manifest_fixture(value)
    if damage == 'pair':
        payload['receipt'] = {**payload['receipt'], 'config_sha': 'e' * 40}
    elif damage == 'snapshot':
        (path.parent / 'deployment-config.json').write_text('{}')
    elif damage == 'source-tree':
        (path.parent / 'reviewed-source/.relay-source.json').write_text(json.dumps({
            'revision': PREVIOUS, 'tree': '0' * 40}))
    else:
        original = path.with_name('retained-original-manifest.json')
        path.rename(original)
        path.symlink_to(original)
    before = path.read_bytes()
    with pytest.raises(ValueError):
        install.finalize_fresh_manifest(payload, root=value.root, owner_uid=os.getuid())
    assert path.read_bytes() == before
    assert not list(path.parent.glob('.fresh-ready-*'))


def test_selected_resource_proof_in_upgrade_preflight_allows_profile_delta_and_rejects_relocation(installation):
    import yaml
    from jinja2.nativetypes import NativeEnvironment
    value = installation
    git_installation_snapshot(value)
    manifest_path = value.paths['install'] / 'current/artifact-manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest.update(installedRevision=PREVIOUS, resolvedRevision=PREVIOUS)
    manifest_path.write_text(json.dumps(manifest))
    tasks = yaml.safe_load((ROOT / 'deploy/ansible/tasks/upgrade-preflight.yml').read_text())
    expression = tasks[0]['ansible.builtin.command']['argv']
    environment = NativeEnvironment()
    environment.filters['to_json'] = json.dumps
    environment.filters['bool'] = bool
    argv = environment.from_string(expression).render(
        lookup=lambda kind, path: Path(path).read_text(), playbook_dir=str(ROOT / 'deploy/ansible'),
        relay_git_desired_state=True, relay_install_root=str(value.paths['install']),
        relay_config_root=str(value.paths['config']), relay_production_operation_target_head=TARGET,
        relay_intent_expected_installed_revision=PREVIOUS)
    namespace = {'__name__': 'selected-source-proof-test'}
    exec(compile(argv[2], '<selected-resource-preflight>', 'exec'), namespace)
    desired = copy.deepcopy(value.config)
    desired['consumer']['defaultProfile']['effort'] = 'medium'
    assert namespace['verify_desired'](str(value.paths['install']), str(value.paths['config']), TARGET,
        PREVIOUS, owner_uid=os.getuid(), boundary=value.root, expected_config=desired) == PREVIOUS
    desired['consumer']['paths']['claimRoot'] += '-relocated'
    with pytest.raises(ValueError, match='RESOURCE_MIGRATION_UNSUPPORTED'):
        namespace['verify_desired'](str(value.paths['install']), str(value.paths['config']), TARGET,
            PREVIOUS, owner_uid=os.getuid(), boundary=value.root, expected_config=desired)
