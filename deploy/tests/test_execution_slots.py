"""Finite installation topology and native projection; no installed-host claim."""
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml
from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
import config
import workflow_projection as projection


def inputs():
    value = config.load(ROOT / 'deploy/example.json', ROOT)
    e, c = value['environment'], value['consumer']
    e['instance'] = {'reviewerPort': 18787, 'publicationEnabled': False}
    path_names = ['workRoot', 'attemptRoot', 'dispatch', 'launcher',
                  'diagnosticsConfig', 'diagnosticsStore', 'diagnosticsRoot']
    c['executionSlots'] = [
        {'id': 'primary', 'runnerName': e['generalRunner']['name'],
         'runnerUser': e['generalRunner']['user'], 'runtimeUser': c['runtimeUser'],
         'workGroup': e['codexWorkGroup'], 'paths': {key: c['paths'][key] for key in path_names}},
        {'id': 'second', 'runnerName': 'sample-second', 'runnerUser': 'sample-second-runner',
         'runtimeUser': 'sample-second-codex', 'workGroup': 'sample-second-work',
         'paths': config.execution_slot_paths(e['namespace'], 'second')},
    ]
    return value


def test_parallel_topology_compiles_fixed_identity_and_retains_one_consumer_digest():
    public = inputs()
    config.validate(public, ROOT)
    compiled = config.compile_inputs(public)
    assert compiled['relay_execution_slots'] == public['consumer']['executionSlots']
    assert compiled['relay_execution_slot'] == 'primary'
    assert compiled['relay_execution_slot_isolation'] is True
    extra, = compiled['relay_additional_execution_slots']
    assert extra['relay_runner_registration_scope'] == 'repository'
    assert extra['relay_runner_service_name'] == 'codex-relay-slot-second-runner.service'
    assert extra['relay_codex_user'] == 'sample-second-codex'
    assert extra['relay_dispatch_state_root'] == '/var/lib/codex-relay/slots/second/dispatch'
    assert extra['relay_runner_registration_helper_path'] == '/opt/codex-relay/slots/second/relay-runner-registration'
    values = {**yaml.safe_load((ROOT / 'deploy/ansible/group_vars/all.yml').read_text()), **compiled}
    source = (ROOT / 'deploy/ansible/roles/relay_controller/templates/consumer.json.j2').read_text()
    installed = json.loads(Templar(loader=DataLoader(), variables=values).template(source, convert_data=False))
    assert installed['executionSlots'] == public['consumer']['executionSlots']
    assert installed['paths']['claimRoot'] == public['consumer']['paths']['claimRoot']
    assert installed['runtimeUser'] == public['consumer']['runtimeUser']


@pytest.mark.parametrize('mutate', [
    lambda v: v['environment'].pop('instance'),
    lambda v: v['consumer']['executionSlots'][0].update(runnerUser='foreign-runner'),
    lambda v: v['consumer']['executionSlots'][0].update(workGroup='foreign-work'),
    lambda v: v['consumer']['executionSlots'][1].update(runtimeUser=v['environment']['reviewerUser']),
    lambda v: v['consumer']['executionSlots'][1].update(runnerName=v['environment']['runner']['name']),
    lambda v: v['consumer']['executionSlots'][1].update(workGroup=v['environment']['serviceUser']),
    lambda v: v['consumer']['executionSlots'][1]['paths'].update(dispatch='/opt/codex-relay/arbitrary-dispatch'),
    lambda v: v['consumer']['executionSlots'][1]['paths'].update(workRoot='/var/lib/foreign/work'),
])
def test_parallel_configuration_rejects_ambiguous_authority_or_identity_before_backend(mutate):
    public = inputs()
    mutate(public)
    with pytest.raises(config.InvalidConfig):
        config.validate(public, ROOT)


def test_v4_parallel_projection_keeps_max_queue_and_separates_native_subject_groups():
    public = inputs()
    config.validate(public, ROOT)
    rendered = projection.render(public, 'a' * 40, ROOT)
    route = yaml.safe_load(rendered[public['consumer']['routingWorkflow']])
    recovery = yaml.safe_load(rendered[public['consumer']['recoveryWorkflow']])
    assert route['concurrency']['queue'] == recovery['concurrency']['queue'] == 'max'
    assert route['concurrency']['cancel-in-progress'] is False
    assert "format('issue-{0}', inputs.task)" in route['concurrency']['group']
    assert "format('pull-{0}', github.event.pull_request.number)" in route['concurrency']['group']
    assert recovery['concurrency']['group'] == 'codex-relay-recovery-${{ inputs.run_id }}'
    route_step, = route['jobs']['route']['steps']
    assert route_step['env']['EXPECTED_WORKFLOW_CONTRACT'] == 'relay-workflows-v4'
    assert 'parallelWorkflowContract' in route_step['run']
    for slot in public['consumer']['executionSlots']:
        assert slot['runnerName'] + ':' + slot['runnerUser'] in route_step['run']
        assert 'export RELAY_EXECUTION_SLOT=' + slot['id'] in route_step['run']
    assert 'RELAY_RUNNER_SLOT_IDENTITY_MISMATCH' in route_step['run']


def test_legacy_projection_keeps_serial_v3_and_primary_identity_checks():
    public = inputs()
    public['consumer'].pop('executionSlots')
    config.validate(public, ROOT)
    rendered = projection.render(public, 'a' * 40, ROOT)
    for path in [public['consumer']['routingWorkflow'], public['consumer']['recoveryWorkflow']]:
        workflow = yaml.safe_load(rendered[path])
        assert workflow['concurrency'] == {'group': 'codex-relay-control', 'cancel-in-progress': False, 'queue': 'max'}
        job, = workflow['jobs'].values()
        step, = job['steps']
        assert step['env']['EXPECTED_WORKFLOW_CONTRACT'] == 'relay-workflows-v3'
        assert 'RELAY_EXECUTION_SLOT' not in step['run']


def test_parallel_projection_cannot_silently_accept_an_older_serial_runtime_contract(tmp_path):
    templates = tmp_path / 'deploy/workflows'
    templates.mkdir(parents=True)
    (templates / 'contract.json').write_text('{"workflowContract":"relay-workflows-v3"}')
    with pytest.raises(config.InvalidConfig, match='parallel-workflow-contract-required'):
        projection.render(inputs(), 'a' * 40, tmp_path)


def test_unqualified_parallel_host_operation_stops_before_source_or_remote_transport(tmp_path):
    public = inputs()
    pathname = tmp_path / 'relay.json'
    pathname.write_text(json.dumps(public))
    result = subprocess.run([sys.executable, str(ROOT / 'deploy/relay-deploy.py'),
                             '--config', str(pathname), '--phase', 'apply'],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode != 0
    assert 'PARALLEL_INSTALLATION_NOT_QUALIFIED' in result.stderr
    assert 'source-identity' not in result.stderr
