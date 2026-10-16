"""Physical pool inventory must not invent 32 runner/token prerequisites."""
import copy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import inventory
import managed_pool
from test_inventory import target, write, observe, snapshot
from test_managed_pool_workflows import pool_configuration


def setup_pool(target, capacity=2):
    target.config = pool_configuration(capacity)
    contract = managed_pool.pool_contract(target.config)
    state = {'version': 1, 'binding': managed_pool.binding(contract),
             'ownerRepository': contract['repository'], 'desiredCapacity': capacity,
             'consumers': {}, 'members': {}}
    for number, member in enumerate(contract['members'][:capacity], 1):
        state['members'][member['id']] = {'phase': 'ready', 'runnerId': 100 + number}
        marker = {'gitHubUrl': 'https://github.com/' + contract['organization'],
                  'agentName': member['name'], 'agentId': 100 + number,
                  'workFolder': member['state'] + '/work', 'poolName': contract['group']}
        write(target, member['root'] + '/.runner', marker)
        write(target, member['root'] + '/.credentials', 'PRIVATE_METADATA_ONLY_FIXTURE')
    path = '/var/lib/codex-relay-pools/' + contract['name'] + '/pool.json'
    write(target, path, state)
    return state, path, contract


def test_one_pool_row_reports_physical_capacity_without_secret_reads(target, monkeypatch):
    setup_pool(target)
    before = snapshot(target.root)
    read = inventory.Probe.read
    def bounded_read(self, path, **kwargs):
        assert not path.endswith(('.credentials', '.credentials_rsaparams', 'access-token'))
        return read(self, path, **kwargs)
    monkeypatch.setattr(inventory.Probe, 'read', bounded_read)
    report = observe(target)
    assert set(report['runners']) == {'production', 'general'}
    pool = report['runners']['general']
    assert pool['status'] == 'reusable'
    assert pool['desiredCapacity'] == 2
    assert len(pool['members']) == 2
    assert pool['freshTokenRequired'] is False
    assert inventory._validate_report(report, target.config) == report
    assert snapshot(target.root) == before


def test_missing_managed_pool_uses_app_apply_without_manual_tokens(target):
    target.config = pool_configuration(15)
    report = observe(target)
    pool = report['runners']['general']
    assert pool['status'] == 'missing'
    assert pool['freshTokenRequired'] is False
    assert len(pool['members']) == 15
    inventory._validate_report(report, target.config)


@pytest.mark.parametrize('change', [
    lambda value: value['binding'].update(runnerUser='foreign'),
    lambda value: value['binding']['members'][0].update(root='/opt/foreign'),
    lambda value: value['members']['primary'].update(runnerId=999),
    lambda value: value['members']['primary'].update(phase='register'),
])
def test_drift_or_uncertain_mutation_is_visible_and_never_reused(target, change):
    state, path, _ = setup_pool(target)
    state = copy.deepcopy(state)
    change(state)
    write(target, path, state)
    report = observe(target)
    assert report['runners']['general']['status'] == 'invalid'
    assert 'runner-general-ambiguous' in report['blockers']


def test_contraction_keeps_surplus_draining_member_visible(target):
    state, path, _ = setup_pool(target, 2)
    target.config['consumer']['generalRunnerPool']['desiredCapacity'] = 1
    state['desiredCapacity'] = 1
    state['members']['pool-2']['phase'] = 'draining'
    write(target, path, state)
    pool = observe(target)['runners']['general']
    assert pool['status'] == 'reusable'
    assert pool['desiredCapacity'] == 1
    assert pool['members'][1]['phase'] == 'draining'
    assert pool['members'][1]['desired'] is False
