"""Managed scheduling and retired-runner recovery projection contracts."""
import json
from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
import config
import workflow_projection


def pool_configuration(capacity=2):
    value = json.loads((ROOT / 'deploy/example.json').read_text())
    value['consumer']['generalRunnerPool'] = {'desiredCapacity': capacity}
    value['environment']['instance'] = {'reviewerPort': 18787, 'publicationEnabled': False}
    value['environment']['generalRunner'].update(
        scope='organization', group='sample-general-pool',
        poolApp={'appId': '123', 'installationId': '456',
                 'privateKeyFile': '/owner-private/runner-app.pem'})
    return config.loads(json.dumps(value), ROOT)


def workflows(value):
    rendered = workflow_projection.render(value, 'a' * 40, ROOT)
    return {name: yaml.safe_load(raw) for name, raw in rendered.items()}


def test_managed_recovery_uses_active_pool_and_original_claim_without_slot_input():
    value = pool_configuration()
    result = workflows(value)
    route = result[value['consumer']['routingWorkflow']]
    recovery = result[value['consumer']['recoveryWorkflow']]
    assert route['jobs']['route']['runs-on'] == recovery['jobs']['recover']['runs-on']
    assert 'execution_slot' not in recovery[True]['workflow_dispatch']['inputs']
    assert 'RECOVERY_SLOT' not in recovery['jobs']['recover']['steps'][0]['env']
    assert route['concurrency']['queue'] == recovery['concurrency']['queue'] == 'max'
    assert route['concurrency']['cancel-in-progress'] is False
    assert recovery['concurrency']['cancel-in-progress'] is False
    assert 'inputs.run_id' in recovery['concurrency']['group']
    assert recovery['jobs']['recover']['steps'][0]['env']['EXPECTED_WORKFLOW_CONTRACT'] == 'relay-workflows-v4'


def test_repositories_and_runtime_users_share_one_physical_pool_selector():
    first = pool_configuration(1)
    second = pool_configuration(15)
    second['consumer']['repository'] = 'example-org/another-project'
    second['consumer']['runtimeUser'] = 'another-codex-user'
    for slot in second['consumer']['executionSlots']:
        slot['runtimeUser'] = second['consumer']['runtimeUser']
    one = workflows(first)[first['consumer']['routingWorkflow']]['jobs']['route']
    two = workflows(second)[second['consumer']['routingWorkflow']]['jobs']['route']
    assert one['runs-on'] == two['runs-on']
    assert one['runs-on']['labels'] == [
        'self-hosted', 'Linux', 'X64', config.general_pool_label(first)]
    assert first['environment']['runner']['labels'][0] not in one['runs-on']['labels']
    assert first['environment']['runner']['group'] != one['runs-on']['group']
    assert first['consumer']['executionSlots'] == pool_configuration(32)['consumer']['executionSlots']
    assert one['steps'][0]['env']['RELAY_CONSUMER_CONFIG'] == '/etc/codex-relay/consumer.json'
    assert "github.repository == 'example-org/another-project'" in two['if']
