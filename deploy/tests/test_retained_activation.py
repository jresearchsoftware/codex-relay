"""Bounded owner intent and live-observation refusals, without external effects."""
import copy
import json
import os
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import retained_activation as activation
import bounded_recovery
from test_managed_pool import inputs

OPERATION = '12345678-1234-1234-1234-123456789abc'


def payload():
    config = inputs(6)
    identities, _ = activation.services(config)
    off = {'active': False, 'enabled': 'enabled', 'load': 'loaded'}
    previous = {name: dict(off) for name in identities}
    previous.update(reviewer={**off, 'active': True}, general={**off, 'active': True},
                    manualOutcome={'active': False, 'enabled': 'disabled', 'load': 'not-found'})
    observed = {name: dict(value) for name, value in previous.items()}
    restored = ['production', *('slot-pool-' + str(index) for index in range(2, 7))]
    runners = {name: {'runnerId': 55 if name == 'production' else 73 + int(name.removeprefix('slot-pool-')),
                      'runnerName': identities[name]['name']} for name in restored}
    for name in restored:
        observed[name]['active'] = True
    binding = {'operationId': OPERATION, 'retainedTarget': 'a' * 40, 'installedRevision': 'a' * 40,
               'controllerRevision': 'b' * 40, 'desiredRevision': 'b' * 40,
               'gitConfigReceipt': {'product_sha': 'b' * 40, 'config_sha': 'c' * 40,
                                    'config_blob_sha': 'd' * 40, 'config_sha256': 'e' * 64},
               'runnerMaintenance': {'operationId': OPERATION, 'retainedTarget': 'a' * 40, 'runners': runners}}
    return {'config': config, 'binding': binding, 'previous': previous, 'observed': observed}


class Evidence:
    """Explicit synthetic boundary for service/API observations only."""
    def __init__(self, value):
        self.value = value
        self.remote = [{**runner, 'id': runner['runnerId'], 'name': runner['runnerName'],
                        'status': 'online', 'busy': False}
                       for runner in value['binding']['runnerMaintenance']['runners'].values()]
        self.checks = 0
        self.reviewer_value = {'pid': '41', 'start': '4100', 'executable': 'a' * 64,
                               'config': 'b' * 64, 'unit': 'c' * 64}

    def authority(self):
        self.checks += 1

    def runners(self, _contract):
        return self.remote

    def runner(self, component, expected, identity, _contract):
        return {'service': identity['service'], 'runnerId': expected['runnerId'], 'version': '2.338.2'}

    def reviewer(self):
        return self.reviewer_value


def test_exact_six_owner_restored_runners_preserve_original_snapshot():
    value = payload()
    original = copy.deepcopy(value['previous'])
    native = Evidence(value)
    first = activation.prove(value, native)
    assert len(first['runners']) == 6
    assert value['previous'] == original
    value['before'] = first
    assert activation.prove(value, native) == first
    assert native.checks == 4


@pytest.mark.parametrize('damage,code', [
    ('no-declaration', 'OWNER_DECLARATION_REQUIRED'),
    ('wrong-operation', 'RUNNER_MAINTENANCE_INVALID'),
    ('wrong-target', 'RUNNER_MAINTENANCE_INVALID'),
    ('undeclared', 'DECLARED_ACTIVITY_MISMATCH'),
    ('not-restored', 'DECLARED_ACTIVITY_MISMATCH'),
    ('new-service', 'ORIGINAL_SERVICE_CHANGED'),
    ('changed-enable', 'ORIGINAL_SERVICE_CHANGED'),
    ('foreign-name', 'ORIGINAL_SERVICE_CHANGED'),
    ('reviewer-lost', 'REVIEWER_UNPROVEN'),
    ('remote-id', 'ONLINE_IDLE_REGISTRATION_UNPROVEN'),
    ('remote-offline', 'ONLINE_IDLE_REGISTRATION_UNPROVEN'),
    ('remote-busy', 'ONLINE_IDLE_REGISTRATION_UNPROVEN'),
    ('remote-unknown', 'ONLINE_IDLE_REGISTRATION_UNPROVEN'),
    ('remote-duplicate', 'ONLINE_IDLE_REGISTRATION_UNPROVEN'),
    ('reviewer-changed', 'MAINTAINED_RUNTIME_CHANGED'),
])
def test_unsafe_or_undeclared_activity_fails_closed(damage, code):
    value = payload()
    native = Evidence(value)
    runners = value['binding']['runnerMaintenance']['runners']
    if damage == 'no-declaration':
        del value['binding']['runnerMaintenance']
    elif damage == 'wrong-operation':
        value['binding']['runnerMaintenance']['operationId'] = '0' * 36
    elif damage == 'wrong-target':
        value['binding']['runnerMaintenance']['retainedTarget'] = 'f' * 40
    elif damage == 'undeclared':
        del runners['production']
    elif damage == 'not-restored':
        value['observed']['production']['active'] = False
    elif damage == 'new-service':
        value['previous']['production']['load'] = 'not-found'
    elif damage == 'changed-enable':
        value['observed']['production']['enabled'] = 'enabled-runtime'
    elif damage == 'foreign-name':
        runners['production']['runnerName'] = 'foreign-runner'
    elif damage == 'reviewer-lost':
        value['observed']['reviewer']['active'] = False
    elif damage == 'remote-id':
        native.remote[0]['id'] += 100
    elif damage == 'remote-offline':
        native.remote[0]['status'] = 'offline'
    elif damage == 'remote-busy':
        native.remote[0]['busy'] = True
    elif damage == 'remote-unknown':
        del native.remote[0]['busy']
    elif damage == 'remote-duplicate':
        native.remote.append(copy.deepcopy(native.remote[0]))
    elif damage == 'reviewer-changed':
        value['before'] = activation.prove(value, native)
        native.reviewer_value = {**native.reviewer_value, 'config': 'f' * 64}
    with pytest.raises(ValueError, match=code):
        activation.prove(value, native)


def test_recheck_authority_after_observations():
    value = payload()
    native = Evidence(value)
    def authority():
        native.checks += 1
        if native.checks == 2:
            raise ValueError('RELAY_RETAINED_ACTIVATION_WORK_OR_OPERATION_UNPROVEN')
    native.authority = authority
    with pytest.raises(ValueError, match='WORK_OR_OPERATION_UNPROVEN'):
        activation.prove(value, native)


def test_old_bounded_bindings_are_unchanged_and_declarations_are_exact():
    binding = payload()['binding']
    assert bounded_recovery.binding_valid(binding) == binding
    del binding['runnerMaintenance']
    assert bounded_recovery.binding_valid(binding) == binding
    binding['runnerMaintenance'] = {'operationId': OPERATION, 'retainedTarget': 'a' * 40, 'runners': {}}
    with pytest.raises(ValueError, match='RUNNER_MAINTENANCE_INVALID'):
        bounded_recovery.binding_valid(binding)


@pytest.mark.parametrize('damage,code', [(None, None), ('pool-id', 'ORIGINAL_RUNNER_ID_CHANGED'),
    ('flag', 'REGISTRATION_OR_UPDATE_SETTING_CHANGED'), ('work', 'REGISTRATION_OR_UPDATE_SETTING_CHANGED'),
    ('group', 'GROUP_MEMBERSHIP_UNPROVEN'), ('version', 'VERSION_UNPROVEN')])
def test_native_registration_proof_retains_protected_pool_id_and_effective_settings(monkeypatch, damage, code):
    from types import SimpleNamespace
    value = payload()
    identities, contract = activation.services(value['config'])
    identity = identities['slot-pool-2']
    expected = value['binding']['runnerMaintenance']['runners']['slot-pool-2']
    settings = {'agentName': expected['runnerName'], 'agentId': expected['runnerId'],
                'poolName': identity['group'], 'poolId': 7, 'workFolder': identity['work'],
                'gitHubUrl': 'https://github.com/' + contract['organization'], 'disableUpdate': False}
    migrated = {**settings, 'disableUpdate': damage == 'flag'}
    if damage == 'work':
        migrated['workFolder'] = '/foreign/work'
    inspected = {'serviceState': {'ActiveState': 'active', 'SubState': 'running',
        'MainPID': str(os.getpid()), 'ControlGroup': '/system.slice/' + identity['service']},
        'settings': [settings, migrated]}
    monkeypatch.setattr(activation.runner_self_update, 'inspect', lambda *_a: inspected)
    monkeypatch.setattr(activation.runner_self_update, 'runner_uid', lambda *_a: os.getuid())
    monkeypatch.setattr(activation.managed_pool, 'State', lambda *_a: SimpleNamespace(read=lambda: {
        'binding': activation.managed_pool.binding(contract),
        'members': {identity['id']: {'phase': 'ready', 'runnerId': 1000 if damage == 'pool-id' else expected['runnerId']}}}))
    monkeypatch.setattr(activation.retained, 'read', lambda *_a, **_k: b'protected unit')
    monkeypatch.setattr(activation, 'command', lambda *_a, **_k: b'unknown' if damage == 'version' else b'2.338.2\n')
    native = activation.Native(value)
    native.github = SimpleNamespace(in_group=lambda *_a: damage != 'group')
    native.pool_group = 7
    if code is None:
        assert native.runner('slot-pool-2', expected, identity, contract)['runnerId'] == expected['runnerId']
    else:
        with pytest.raises(ValueError, match=code):
            native.runner('slot-pool-2', expected, identity, contract)
