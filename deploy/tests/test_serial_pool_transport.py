"""Private stdin root transport, fixed public proofs and F1-before-transition."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
import managed_pool
import managed_pool_transport as transport
from test_managed_pool import inputs


REVISION = 'a' * 40
DIGEST = 'b' * 64
OPERATION = '12345678-1234-4234-8234-123456789abc'
TOKEN = 'synthetic-private-installation-token'


@pytest.fixture
def exchange(monkeypatch):
    config = inputs(1)
    authorization = {'organization': 'example-org', 'appId': '101',
                     'installationId': '201', 'installationToken': TOKEN}
    monkeypatch.setattr(transport, 'installation_authorization', Mock(return_value=authorization))
    monkeypatch.setattr(transport, 'consumer_digest', Mock(return_value=DIGEST))
    process = Mock(returncode=0)
    process.poll.return_value = 0
    process.communicate.return_value = (
        'MANAGED_POOL_PREFLIGHT=PASS\nMANAGED_POOL_SERIAL_TRANSITION=required\n', '')
    popen = Mock(return_value=process)
    monkeypatch.setattr(transport.subprocess, 'Popen', popen)
    guard = Mock()
    guard.poll.return_value = None
    return config, process, popen, guard


def preflight(exchange, **kwargs):
    config, _, _, guard = exchange
    return transport.preflight_pool({'user': 'root', 'host': 'test.invalid'}, '/private/owner-key',
                                    config, guard, **kwargs)


def transition(exchange, action='begin', **kwargs):
    config, _, _, guard = exchange
    return transport.transition_pool({'user': 'root', 'host': 'test.invalid'}, '/private/owner-key',
        config, REVISION, OPERATION, guard, action=action, **kwargs)


@pytest.mark.parametrize('state,required', [('required', True), ('retained', False), ('none', False)])
def test_original_pass_string_abi_exposes_separate_bounded_transition_facts(exchange, state, required):
    exchange[1].communicate.return_value = (
        'MANAGED_POOL_PREFLIGHT=PASS\nMANAGED_POOL_SERIAL_TRANSITION=' + state + '\n', '')
    result = preflight(exchange)
    assert result == 'MANAGED_POOL_PREFLIGHT=PASS'
    assert isinstance(result, str) and result.serial_transition is required
    assert result.transition_state == state and result.target_digest == DIGEST
    assert result.operation_id is None


@pytest.mark.parametrize('state', ['required', 'retained'])
def test_retained_operation_is_available_to_exact_same_apply_continuation(exchange, state):
    exchange[1].communicate.return_value = (
        'MANAGED_POOL_PREFLIGHT=PASS\nMANAGED_POOL_SERIAL_TRANSITION=' + state + '\n'
        'MANAGED_POOL_SERIAL_OPERATION=' + OPERATION + '\n', '')
    # Re-observation after a lost begin acknowledgement returns the original
    # protected operation, rather than allocating another transition UUID.
    first, repeated = preflight(exchange), preflight(exchange)
    assert first.operation_id == repeated.operation_id == OPERATION
    expected = {'phase': 'stopped', 'operationId': first.operation_id, 'target': REVISION}
    exchange[1].communicate.return_value = ('MANAGED_POOL_SERIAL_RESULT=' + json.dumps(expected) + '\n', '')
    config, process, _, guard = exchange
    assert transport.transition_pool({'user': 'root', 'host': 'test.invalid'}, '/private/owner-key',
        config, REVISION, repeated.operation_id, guard) == expected
    assert json.loads(process.communicate.call_args.kwargs['input'])['operationId'] == OPERATION


@pytest.mark.parametrize('state', ['required', 'retained', 'none'])
def test_fresh_or_completed_preflight_can_explicitly_report_no_retained_operation(exchange, state):
    exchange[1].communicate.return_value = (
        'MANAGED_POOL_PREFLIGHT=PASS\nMANAGED_POOL_SERIAL_TRANSITION=' + state + '\n'
        'MANAGED_POOL_SERIAL_OPERATION=none\n', '')
    assert preflight(exchange).operation_id is None


@pytest.mark.parametrize('suffix', [
    'MANAGED_POOL_SERIAL_OPERATION=\n',
    'MANAGED_POOL_SERIAL_OPERATION=latest\n',
    'MANAGED_POOL_SERIAL_OPERATION=' + OPERATION.upper() + '\n',
    'MANAGED_POOL_SERIAL_OPERATION=' + OPERATION + '\nMANAGED_POOL_SERIAL_OPERATION=' + OPERATION + '\n',
    'MANAGED_POOL_SERIAL_OPERATION=none\nMANAGED_POOL_SERIAL_OPERATION=' + OPERATION + '\n',
    'MANAGED_POOL_SERIAL_OPERATION=' + OPERATION + '\nprivate diagnostic\n',
    'MANAGED_POOL_SERIAL_OPERATION=' + OPERATION,
])
def test_malformed_ambiguous_or_unterminated_operation_marker_is_not_a_proof(exchange, suffix):
    exchange[1].communicate.return_value = (
        'MANAGED_POOL_PREFLIGHT=PASS\nMANAGED_POOL_SERIAL_TRANSITION=required\n' + suffix, '')
    with pytest.raises(managed_pool.PoolError, match='OWNER_PREFLIGHT_RESULT_UNPROVEN'):
        preflight(exchange)


def test_no_transition_cannot_claim_a_retained_operation(exchange):
    exchange[1].communicate.return_value = (
        'MANAGED_POOL_PREFLIGHT=PASS\nMANAGED_POOL_SERIAL_TRANSITION=none\n'
        'MANAGED_POOL_SERIAL_OPERATION=' + OPERATION + '\n', '')
    with pytest.raises(managed_pool.PoolError, match='OWNER_PREFLIGHT_RESULT_UNPROVEN'):
        preflight(exchange)


def test_full_config_sources_digest_and_token_only_travel_on_private_stdin(exchange):
    preflight(exchange)
    config, process, popen, _ = exchange
    command = popen.call_args.args[0]
    assert command[0] == 'ssh' and 'StrictHostKeyChecking=yes' in command
    assert TOKEN not in str(command) and '/owner-private/app.pem' not in str(command)
    payload = json.loads(process.communicate.call_args.kwargs['input'])
    assert payload['authorization']['installationToken'] == TOKEN
    assert payload['config'] == config and payload['targetDigest'] == DIGEST
    assert list(payload['sources']) == transport.OWNER_POOL_SOURCES
    assert list(payload['sources']).index('config') < list(payload['sources']).index('serial_pool_transition')
    assert len(process.communicate.call_args.kwargs['input'].encode()) <= transport.OWNER_POOL_INPUT_BYTES


def test_local_transport_has_no_ssh_and_no_caller_selected_installed_helper(exchange):
    preflight(exchange, local=True)
    command = exchange[2].call_args.args[0]
    assert command[:3] == ['/usr/bin/python3', '-I', '-c']
    assert command[3] == transport.OWNER_POOL_SCRIPT


@pytest.mark.parametrize('action,phase', [('begin', 'stopped'), ('begin', 'installed'), ('finish', 'retired')])
def test_transition_result_binds_phase_operation_and_exact_target(exchange, action, phase):
    expected = {'phase': phase, 'operationId': OPERATION, 'target': REVISION}
    exchange[1].communicate.return_value = ('MANAGED_POOL_SERIAL_RESULT=' + json.dumps(expected) + '\n', '')
    assert transition(exchange, action) == expected
    payload = json.loads(exchange[1].communicate.call_args.kwargs['input'])
    assert payload['action'] == action and payload['revision'] == REVISION and payload['operationId'] == OPERATION


@pytest.mark.parametrize('output', [
    'MANAGED_POOL_PREFLIGHT=PASS\n',
    'MANAGED_POOL_PREFLIGHT=PASS\nMANAGED_POOL_SERIAL_TRANSITION=maybe\n',
    'private diagnostic\nMANAGED_POOL_PREFLIGHT=PASS\nMANAGED_POOL_SERIAL_TRANSITION=none\n',
    'x' * (transport.OWNER_POOL_OUTPUT_BYTES + 1),
])
def test_incomplete_unexpected_or_oversized_preflight_output_is_not_a_proof(exchange, output):
    exchange[1].communicate.return_value = (output, '')
    with pytest.raises(managed_pool.PoolError) as error:
        preflight(exchange)
    assert 'private diagnostic' not in str(error.value)


@pytest.mark.parametrize('result', [
    {'phase': 'stopped', 'operationId': OPERATION, 'target': 'c' * 40},
    {'phase': 'stopped', 'operationId': '22345678-1234-4234-8234-123456789abc', 'target': REVISION},
    {'phase': 'applying', 'operationId': OPERATION, 'target': REVISION},
    {'phase': 'stopped', 'operationId': OPERATION, 'target': REVISION, 'private': TOKEN},
])
def test_transition_cannot_return_another_identity_phase_or_private_fields(exchange, result):
    exchange[1].communicate.return_value = ('MANAGED_POOL_SERIAL_RESULT=' + json.dumps(result) + '\n', '')
    with pytest.raises(managed_pool.PoolError, match='SERIAL_TRANSITION_RESULT_UNPROVEN'):
        transition(exchange)


def test_unknown_private_errors_are_sanitized_but_fixed_product_errors_survive(exchange):
    process = exchange[1]
    process.returncode = 1
    for errors, expected in [(TOKEN, 'OWNER_PREFLIGHT_UNPROVEN'),
                             (TOKEN + '\nMANAGED_POOL_GROUP_UNTRUSTED_WORKFLOW_REF\n',
                              'GROUP_UNTRUSTED_WORKFLOW_REF')]:
        process.communicate.return_value = ('private stdout ' + TOKEN, errors)
        with pytest.raises(managed_pool.PoolError, match=expected) as error:
            preflight(exchange)
        assert TOKEN not in str(error.value)


def test_timeout_continues_same_exchange_without_resending_token(exchange):
    process = exchange[1]
    process.communicate.side_effect = [subprocess.TimeoutExpired('ssh', 1),
        ('MANAGED_POOL_PREFLIGHT=PASS\nMANAGED_POOL_SERIAL_TRANSITION=none\n', '')]
    assert preflight(exchange).serial_transition is False
    assert TOKEN in process.communicate.call_args_list[0].kwargs['input']
    assert process.communicate.call_args_list[1].kwargs['input'] is None
    assert exchange[2].call_count == 1


@pytest.mark.parametrize('pool_guard', [False, True])
def test_guard_loss_terminates_one_exchange_without_retry_or_leaking_payload(exchange, pool_guard):
    process, guard = exchange[1], exchange[3]
    process.poll.return_value = None
    process.communicate.side_effect = subprocess.TimeoutExpired('ssh', 1)
    extra = Mock()
    extra.poll.return_value = None
    if pool_guard:
        extra.poll.side_effect = [None, None, 1]
    else:
        guard.poll.side_effect = [None, None, None, 1]
    with pytest.raises(managed_pool.PoolError, match='GUARD_LOST'):
        preflight(exchange, extra_guard=extra)
    process.terminate.assert_called_once()
    assert exchange[2].call_count == 1


def test_missing_guard_and_invalid_transition_identity_stop_before_token_or_process(exchange):
    config, _, popen, guard = exchange
    guard.poll.return_value = 1
    with pytest.raises(managed_pool.PoolError, match='HOST_GUARD_LOST'):
        preflight(exchange)
    with pytest.raises(managed_pool.PoolError, match='OPERATION_INVALID'):
        transport.transition_pool(None, None, config, 'main', OPERATION, local=True)
    transport.installation_authorization.assert_not_called()
    popen.assert_not_called()


def test_oversized_sources_stop_before_authorization_or_remote_invocation(exchange, monkeypatch):
    monkeypatch.setattr(transport.Path, 'read_text', lambda _path, **_kwargs: 'x' * transport.OWNER_POOL_INPUT_BYTES)
    with pytest.raises(managed_pool.PoolError, match='INPUT_SIZE'):
        preflight(exchange)
    transport.installation_authorization.assert_not_called()
    exchange[2].assert_not_called()


def script_payload(*, proof=None, action='preflight', bad_group=False, private_error=False, begin_phase='stopped'):
    contract = {'organization': 'example-org', 'appId': '101', 'installationId': '201', 'bad': bad_group}
    pool = '''QUALIFIED=False
def require(value, code):
    if not value: raise ValueError('MANAGED_POOL_'+code)
def pool_contract(config): return config['contract']
class GitHub:
    def __init__(self, token, organization): self.token=token
    def qualify(self, contract):
        global QUALIFIED
        require(not contract['bad'],'GROUP_UNTRUSTED_WORKFLOW_REF')
        QUALIFIED=True
'''
    installation = '''import managed_pool as pool
import config
assert config.LOADED
def preflight(config, github, digest):
    assert pool.QUALIFIED
    if config['privateError']: raise ValueError(github.token)
    return config['proof']
def begin(config, github, digest, operation, target):
    assert pool.QUALIFIED
    return {'phase':config['beginPhase'],'operationId':operation,'targetRevision':target,'private':github.token}
def finish(config, github):
    assert pool.QUALIFIED
    return {'phase':'retired','private':github.token}
'''
    sources = {name: '' for name in transport.OWNER_POOL_SOURCES}
    sources.update(managed_pool=pool, config='LOADED=True\n',
        serial_pool_transition='import config\nassert config.LOADED\n',
        serial_pool_installation=installation)
    return {'sources': sources, 'contract': contract,
            'config': {'contract': contract, 'proof': proof, 'privateError': private_error, 'beginPhase': begin_phase},
            'authorization': {'organization': 'example-org', 'appId': '101',
                              'installationId': '201', 'installationToken': TOKEN},
            'targetDigest': DIGEST, 'action': action, 'revision': REVISION, 'operationId': OPERATION}


def run_script(payload):
    return subprocess.run([sys.executable, '-I', '-c', transport.OWNER_POOL_SCRIPT],
        input=json.dumps(payload), text=True, capture_output=True, timeout=10)


@pytest.mark.skipif(os.geteuid() != 0, reason='production root guard is intentionally retained')
@pytest.mark.parametrize('proof,state,operation', [(None, 'none', 'none'), ({'original': {}}, 'required', 'none'),
    ({'phase': 'retired'}, 'retained', 'none'),
    ({'phase': 'stopped', 'operationId': OPERATION}, 'required', OPERATION),
    ({'phase': 'retired', 'operationId': OPERATION, 'completionRequired': True}, 'required', OPERATION)])
def test_native_script_qualifies_f1_then_reads_original_state_with_fixed_preflight_markers(proof, state, operation):
    result = run_script(script_payload(proof=proof))
    assert result.returncode == 0, result.stderr
    assert result.stdout == ('MANAGED_POOL_PREFLIGHT=PASS\nMANAGED_POOL_SERIAL_TRANSITION=' + state + '\n'
        'MANAGED_POOL_SERIAL_OPERATION=' + operation + '\n')
    assert result.stderr == '' and TOKEN not in result.stdout


@pytest.mark.skipif(os.geteuid() != 0, reason='production root guard is intentionally retained')
def test_native_script_does_not_publish_partial_markers_for_malformed_retained_operation():
    result = run_script(script_payload(proof={'phase': 'stopped', 'operationId': 'private diagnostic\n' + TOKEN}))
    assert result.returncode != 0 and result.stdout == ''
    assert result.stderr == 'MANAGED_POOL_SERIAL_TRANSITION_OPERATION_INVALID\n'
    assert TOKEN not in result.stderr


@pytest.mark.skipif(os.geteuid() != 0, reason='production root guard is intentionally retained')
def test_native_script_routes_retired_but_unacknowledged_completion_through_bounded_begin():
    result = run_script(script_payload(proof={'phase': 'retired', 'operationId': OPERATION,
                                             'completionRequired': True}, action='begin'))
    assert result.returncode == 0, result.stderr
    public = json.loads(result.stdout.removeprefix('MANAGED_POOL_SERIAL_RESULT='))
    # The mock begin returns stopped, unlike the preflight's retired record.
    # This proves completion-required was not short-circuited as retained.
    assert public == {'phase': 'stopped', 'operationId': OPERATION, 'target': REVISION}
    assert TOKEN not in result.stdout + result.stderr


@pytest.mark.skipif(os.geteuid() != 0, reason='production root guard is intentionally retained')
@pytest.mark.parametrize('action,phase', [('begin', 'stopped'), ('begin', 'installed'), ('finish', 'retired')])
def test_native_script_publishes_only_bounded_result_after_qualified_transition(action, phase):
    result = run_script(script_payload(proof={'original': {}}, action=action, begin_phase=phase if action == 'begin' else 'stopped'))
    assert result.returncode == 0, result.stderr
    public = json.loads(result.stdout.removeprefix('MANAGED_POOL_SERIAL_RESULT='))
    assert public == {'phase': phase, 'operationId': OPERATION, 'target': REVISION}
    assert TOKEN not in result.stdout + result.stderr


@pytest.mark.skipif(os.geteuid() != 0, reason='production root guard is intentionally retained')
def test_native_script_f1_denial_precedes_original_read_and_private_exception_is_hidden():
    result = run_script(script_payload(bad_group=True, private_error=True))
    assert result.returncode != 0 and result.stdout == ''
    assert result.stderr == 'MANAGED_POOL_GROUP_UNTRUSTED_WORKFLOW_REF\n'
    result = run_script(script_payload(private_error=True))
    assert result.returncode != 0 and result.stdout == ''
    assert result.stderr == 'MANAGED_POOL_PREFLIGHT_UNPROVEN_INSPECT_BEFORE_RETRY\n'
    assert TOKEN not in result.stderr


def test_native_script_rejects_oversized_payload_without_echoing_it():
    result = subprocess.run([sys.executable, '-I', '-c', transport.OWNER_POOL_SCRIPT],
        input=TOKEN + 'x' * transport.OWNER_POOL_INPUT_BYTES, text=True, capture_output=True, timeout=10)
    assert result.returncode != 0 and result.stdout == ''
    assert result.stderr == 'MANAGED_POOL_PREFLIGHT_UNPROVEN_INSPECT_BEFORE_RETRY\n'


def test_current_node_digest_resolves_defaults_and_preserves_capacity_only_digest():
    config = inputs(1)
    first = transport.consumer_digest(config['consumer'], ROOT)
    config['consumer']['generalRunnerPool']['desiredCapacity'] = 2
    assert transport.consumer_digest(config['consumer'], ROOT) == first
    assert len(first) == 64
    assert first != hashlib.sha256(json.dumps(config['consumer']).encode()).hexdigest()
