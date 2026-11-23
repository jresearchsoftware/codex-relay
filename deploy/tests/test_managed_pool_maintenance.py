"""Maintenance preserves native registrations and reconciles uncertain labels."""
import copy
import os
from pathlib import Path

import pytest

from test_managed_pool import setup, Host as ExistingHost
import managed_pool as pool


class Host(ExistingHost):
    def __init__(self, remote, state):
        super().__init__(remote, state)
        self.transport = None
        self.starts = []
        self.labels_at_start = []
        self.admission_observations = []
        self.closed_admissions = set()

    def service(self, member):
        active = member['id'] in self.services
        return {'ActiveState': 'active' if active else 'inactive',
                'MainPID': '100' if active else '0', 'ControlPID': '0',
                'ControlGroup': '/system.slice/' + member['service']}

    def owner_transport(self, member, pid):
        return self.transport if member['id'] == 'primary' else None

    def check_readiness(self):
        pass

    def admission_open(self, consumers):
        endpoints = {consumer['admission'] for consumer in consumers.values()}
        self.admission_observations.append(endpoints)
        return not endpoints & self.closed_admissions

    def start(self, member, *, enable=True):
        self.starts.append((member['id'], enable))
        self.labels_at_start.append(copy.deepcopy(self.remote.values[self.local[member['id']]]['labels'])
                                    if member['id'] in self.local else [])
        super().start(member)

    def stop_idle(self, member, remote_idle, *, disable=True):
        assert disable is False
        return super().stop_idle(member, remote_idle)


def fixture(capacity=2):
    contract, state, github, _ = setup(capacity)
    host = Host(github, state)
    pool.reconcile(contract, state, github, host)
    host.starts.clear()
    github.label_mutations.clear()
    return contract, state, github, host


def maintain(values, action, **kwargs):
    return pool.maintenance(*values, operation='synthetic-owner-operation', action=action, **kwargs)


def test_labels_withdraw_before_drain_preserving_ids_enablement_and_inactive_services():
    values = fixture()
    contract, state, github, host = values
    original_ids = copy.deepcopy(host.local)
    original_labels = {key: copy.deepcopy(value['labels']) for key, value in github.values.items()}
    host.services.remove('pool-2')
    assert maintain(values, 'pause')['paused'] == ['primary', 'pool-2']
    assert host.stops == [] and all(value['labels'] == [] for value in github.values.values())
    assert maintain(values, 'drain')['stopped'] == ['primary', 'pool-2']
    assert host.stops == ['primary']
    assert maintain(values, 'restart')['stopped'] == ['primary']
    assert host.starts == []
    assert all(value['labels'] == [] for value in github.values.values())
    maintain(values, 'resume')
    assert host.admission_observations == [{contract['admission']}]
    assert 'maintenance' not in state.value
    assert host.starts == [('primary', False)]
    assert host.labels_at_start[-1] == original_labels[original_ids['primary']]
    assert host.local == original_ids
    assert {key: value['labels'] for key, value in github.values.items()} == original_labels
    assert host.mutations == [('primary', False), ('pool-2', False)]


def test_busy_runner_and_unknown_local_children_are_never_stopped_on_timeout():
    values = fixture()
    _, state, github, host = values
    maintain(values, 'pause')
    github.values[host.local['primary']]['busy'] = True
    host.defer_stop = True
    with pytest.raises(pool.PoolError, match='MAINTENANCE_DRAIN_TIMEOUT') as error:
        maintain(values, 'drain', timeout=0)
    assert error.value.observation['busy'] == ['primary', 'pool-2']
    assert host.stops == [] and state.value['maintenance']['phase'] == 'draining'
    github.values[host.local['primary']]['busy'] = False
    host.defer_stop = False
    assert maintain(values, 'drain', timeout=0)['stopped'] == ['primary', 'pool-2']


def test_drain_waits_for_inflight_assignment_then_preserves_owner_apply_transport():
    values = fixture()
    _, state, github, host = values
    host.transport = {'pid': 123, 'started': '456', 'cgroup': '/system.slice/relay-general-pool-1.service'}
    maintain(values, 'pause', owner_pid=123)
    github.values[host.local['pool-2']]['busy'] = True
    clock = [0]

    def wait(seconds):
        clock[0] += seconds
        github.values[host.local['pool-2']]['busy'] = False

    report = maintain(values, 'drain', now=lambda: clock[0], wait=wait, timeout=1)
    assert clock[0] == 0.5 and report['preserved'] == ['primary']
    assert host.stops == ['pool-2'] and host.services == {'primary'}
    assert state.value['maintenance']['members']['primary']['phase'] == 'preserved'
    assert maintain(values, 'restart')['stopped'] == ['pool-2']
    assert host.starts == []
    maintain(values, 'resume')
    assert host.starts == [('pool-2', False)]


@pytest.mark.parametrize('mutation', ['identity', 'capacity', 'operation'])
def test_conflicting_binding_refuses_before_any_mutation(mutation):
    values = fixture()
    contract, state, github, host = values
    if mutation == 'identity':
        github.values[host.local['pool-2']]['name'] = 'foreign'
    elif mutation == 'capacity':
        contract['desiredCapacity'] = 1
    else:
        maintain(values, 'pause')
        state.value['maintenance']['operation'] = 'another-owner-operation'
        github.label_mutations.clear()
    with pytest.raises(pool.PoolError, match='MAINTENANCE_'):
        maintain(values, 'pause')
    assert github.label_mutations == [] and host.stops == []


def test_lost_pause_response_keeps_durable_original_labels_and_reconciles_exact_effect():
    values = fixture()
    _, state, github, _ = values
    github.lose_labels_response = True
    with pytest.raises(pool.PoolError, match='UNKNOWN_LABEL'):
        maintain(values, 'pause')
    saved = copy.deepcopy(state.value['maintenance']['members']['primary']['labels'])
    assert saved and state.value['maintenance']['phase'] == 'pausing'
    assert maintain(values, 'pause')['paused'] == ['primary', 'pool-2']
    assert state.value['maintenance']['members']['primary']['labels'] == saved
    assert len(github.label_mutations) == 2


def test_resume_requires_open_gate_and_observes_prior_partial_restoration_without_duplicate_put():
    values = fixture()
    _, state, github, host = values
    peer_admission = '/opt/relay-peer/relay-admission'
    state.value['consumers']['example/peer'] = {'namespace': 'relay-peer', 'admission': peer_admission}
    for action in ['pause', 'drain', 'restart']:
        maintain(values, action)
    host.closed_admissions.add(peer_admission)
    with pytest.raises(pool.PoolError, match='MAINTENANCE_ADMISSION_NOT_OPEN'):
        maintain(values, 'resume')
    assert all(value['labels'] == [] for value in github.values.values())
    assert peer_admission in host.admission_observations[-1]
    host.closed_admissions.clear()
    github.lose_labels_response = True
    with pytest.raises(pool.PoolError, match='UNKNOWN_LABEL'):
        maintain(values, 'resume')
    assert state.value['maintenance']['phase'] == 'restore-unverified'
    assert len([value for value in github.values.values() if value['labels']]) == 1
    before = len(github.label_mutations)
    maintain(values, 'resume')
    assert len(github.label_mutations) == before + 1 and 'maintenance' not in state.value


def test_interrupted_restoration_can_be_paused_again_before_another_drain():
    values = fixture()
    _, state, github, _ = values
    for action in ['pause', 'drain', 'restart']:
        maintain(values, action)
    github.lose_labels_response = True
    with pytest.raises(pool.PoolError):
        maintain(values, 'resume')
    maintain(values, 'pause')
    assert all(value['labels'] == [] for value in github.values.values())
    assert state.value['maintenance']['phase'] == 'paused'


def test_normal_reconciliation_does_not_reopen_or_retire_pool_during_maintenance():
    values = fixture()
    contract, state, github, host = values
    maintain(values, 'pause')
    before = len(github.label_mutations)
    assert pool.reconcile(contract, state, github, host)['draining'] == ['primary', 'pool-2']
    assert len(github.label_mutations) == before and not host.stops and not host.starts


def test_unowned_local_registration_is_not_skipped_before_pause():
    values = fixture(1)
    contract, _, github, host = values
    host.local[contract['members'][1]['id']] = 999
    with pytest.raises(pool.PoolError, match='MAINTENANCE_UNOWNED_MEMBER'):
        maintain(values, 'pause')
    assert github.label_mutations == []


def test_resume_preflights_all_members_before_restoring_any_eligibility():
    values = fixture()
    _, state, github, host = values
    for action in ['pause', 'drain', 'restart']:
        maintain(values, action)
    host.services.remove('pool-2')
    before = copy.deepcopy(github.label_mutations)
    with pytest.raises(pool.PoolError, match='MAINTENANCE_RESTART_UNPROVEN'):
        maintain(values, 'resume')
    assert github.label_mutations == before and state.value['maintenance']['phase'] == 'ready'


def test_changed_owner_transport_is_preserved_as_actionable_blocker():
    values = fixture()
    _, _, _, host = values
    host.transport = {'pid': 123, 'started': '456', 'cgroup': '/system.slice/relay-general-pool-1.service'}
    maintain(values, 'pause', owner_pid=123)
    host.transport = {**host.transport, 'started': '999'}
    with pytest.raises(pool.PoolError, match='MAINTENANCE_OWNER_TRANSPORT_CHANGED'):
        maintain(values, 'drain')
    assert host.stops == []


def test_bound_consumer_activity_prevents_pool_stop_even_when_runners_look_idle():
    values = fixture()
    _, state, _, host = values
    peer = {'namespace': 'relay-peer', 'admission': '/opt/relay-peer/relay-admission'}
    state.value['consumers']['example/peer'] = peer
    calls = []

    def attempts_idle(consumers):
        assert consumers['example/peer'] == peer
        calls.append(True)
        return len(calls) > 1

    host.attempts_idle = attempts_idle
    maintain(values, 'pause')
    with pytest.raises(pool.PoolError, match='MAINTENANCE_ADMISSION_DRAIN_TIMEOUT'):
        maintain(values, 'drain', timeout=0)
    assert host.stops == []
    assert maintain(values, 'drain', timeout=0)['stopped'] == ['primary', 'pool-2']


def test_admission_observation_reads_each_validated_endpoint_once(monkeypatch):
    host = object.__new__(pool.Host)
    checked = []
    monkeypatch.setattr(pool, 'protected', checked.append)
    primary = '/opt/relay-primary/relay-admission'
    peer = '/opt/relay-peer/relay-admission'
    host.command = lambda argv, **kwargs: {
        primary: '{"phase":"open","active":[],"unknown":[]}',
        peer: '{"phase":"quiesced","active":[],"unknown":[123]}'
    }[argv[0]]
    consumers = {
        'example/a': {'namespace': 'relay-primary', 'admission': primary},
        'example/b': {'namespace': 'relay-primary', 'admission': primary},
        'example/c': {'namespace': 'relay-peer', 'admission': peer},
    }
    assert not host.attempts_idle(consumers)
    assert checked == [peer]
    host.command = lambda argv, **kwargs: '{"phase":"open","active":[],"unknown":[]}'
    checked.clear()
    assert host.admission_open(consumers)
    assert checked == [peer, primary]
    consumers['example/c']['admission'] = primary
    with pytest.raises(pool.PoolError, match='MAINTENANCE_ADMISSION_BINDING_UNPROVEN'):
        host.attempts_idle(consumers)


def test_owner_transport_requires_current_ancestor_and_exact_service_cgroup(monkeypatch):
    host = object.__new__(pool.Host)
    member = {'service': 'synthetic.service'}
    original_stat = Path.read_text

    def read(path, *args, **kwargs):
        if str(path).endswith('/cgroup'):
            return '0::/system.slice/synthetic.service/nested\n'
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'read_text', read)
    host.service = lambda _: {'ActiveState': 'active', 'ControlGroup': '/system.slice/synthetic.service'}
    result = host.owner_transport(member, os.getpid())
    assert result['pid'] == os.getpid() and result['started'].isdigit()
    monkeypatch.setattr(Path, 'read_text', lambda path: '0::/system.slice/foreign.service\n'
                        if str(path).endswith('/cgroup') else original_stat(path))
    assert host.owner_transport(member, os.getpid()) is None
    with pytest.raises(pool.PoolError, match='OWNER_NOT_ANCESTOR'):
        host.owner_transport(member, 2147483647)
