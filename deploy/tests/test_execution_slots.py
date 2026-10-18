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


@pytest.mark.parametrize('topology', ['managed', 'explicit'])
def test_slot_journal_creation_preserves_final_runner_ownership(topology):
    from test_managed_pool import inputs as managed_inputs

    public = managed_inputs() if topology == 'managed' else inputs()
    config.validate(public, ROOT)
    compiled = config.compile_inputs(public)
    defaults = yaml.safe_load((ROOT / 'deploy/ansible/group_vars/all.yml').read_text())
    include, = yaml.safe_load((ROOT / 'deploy/ansible/tasks/execution-slot.yml').read_text())
    runtime = yaml.safe_load((ROOT / 'deploy/ansible/roles/relay_runner/tasks/general-runtime.yml').read_text())
    reconcile = next(task for task in include['block'] if task.get('ansible.builtin.include_role') ==
                     {'name': 'relay_runner', 'tasks_from': 'general-runtime.yml'})
    boundary = next(task for task in runtime if task['name'] ==
                    'Preserve the private routing and shared Codex work boundaries')
    identity = next(task for task in runtime if task['name'] ==
                    'Create the isolated general runner identity with only Codex work membership')
    ownership = next(task for task in runtime if task['name'] ==
                     'Assign existing generic dispatch journals to the general runner')
    assert runtime.index(identity) < runtime.index(boundary) < runtime.index(ownership)
    assert ownership['ansible.builtin.file']['recurse'] is True
    assert ownership['ansible.builtin.file']['follow'] is False
    assert 'mode' not in ownership['ansible.builtin.file']
    inspect = next(task for task in runtime if task['name'] ==
                   'Refuse aliased generic runtime roots')
    assert inspect['ansible.builtin.assert']['that'] == [
        'not item.stat.exists or (item.stat.isdir and not item.stat.islnk)']
    groups = next(task for task in include['block'] if task['name'] ==
                  'Create the private slot identities and work group')

    for slot in compiled['relay_additional_execution_slots']:
        values = {**defaults, **compiled, 'relay_slot_inputs': slot}
        templar = Templar(loader=DataLoader(), variables=values)
        values.update(templar.template(include['vars']))
        templar = Templar(loader=DataLoader(), variables=values)
        assert slot['relay_codex_work_group'] in templar.template(groups['loop'])
        journals = {values[key] for key in
                    ('relay_dispatch_state_root', 'relay_dispatch_home', 'relay_dispatch_evidence_root')}
        expected = {'state': 'directory', 'owner': slot['relay_runner_user'],
                    'group': slot['relay_runner_group'], 'mode': '0700'}
        assert expected['owner'] != slot['relay_codex_user']

        def rendered_files(task):
            for item in templar.template(task.get('loop', [None])):
                yield Templar(loader=DataLoader(), variables={**values, 'item': item}).template(
                    task['ansible.builtin.file'])

        final = {args['path']: args for args in rendered_files(boundary) if args['path'] in journals}
        assert set(final) == journals
        for args in final.values():
            assert args == {'path': args['path'], **expected}
        # A fresh explicit slot has no runner account until this role creates it.
        # Earlier creation must neither require that missing account nor undo the
        # established ownership on every subsequent check/apply.
        for task in include['block'][:include['block'].index(reconcile)]:
            if 'ansible.builtin.file' in task:
                assert all(args['path'] not in journals for args in rendered_files(task))


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


@pytest.mark.parametrize('topology', ['explicit', 'managed'])
def test_v4_parallel_projection_keeps_max_queue_and_separates_native_attempt_groups(topology):
    if topology == 'managed':
        from test_managed_pool import inputs as managed_inputs
        public = managed_inputs()
    else:
        public = inputs()
    config.validate(public, ROOT)
    rendered = projection.render(public, 'a' * 40, ROOT)
    route = yaml.safe_load(rendered[public['consumer']['routingWorkflow']])
    recovery = yaml.safe_load(rendered[public['consumer']['recoveryWorkflow']])
    assert route['concurrency']['queue'] == recovery['concurrency']['queue'] == 'max'
    assert route['concurrency']['cancel-in-progress'] is False
    assert route['concurrency']['group'] == 'codex-relay-control-${{ github.run_id }}'
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


def test_unknown_slot_stops_before_source_or_remote_transport(tmp_path):
    public = inputs()
    pathname = tmp_path / 'relay.json'
    pathname.write_text(json.dumps(public))
    result = subprocess.run([sys.executable, str(ROOT / 'deploy/relay-deploy.py'),
                             '--config', str(pathname), '--phase', 'general-runner-enable',
                             '--authorize-general-runner-enable', '--execution-slot', 'foreign'],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode != 0
    assert 'INVALID_DEPLOYMENT_CONFIG:execution-slot' in result.stderr
    assert 'source-identity' not in result.stderr


def test_slot_selector_and_native_label_bind_repository_namespace_and_fixed_paths():
    public = inputs()
    primary = config.select_execution_slot(public)
    extra = config.select_execution_slot(public, 'second')
    assert primary['relay_runner_root'] == '/opt/codex-relay/general-runner'
    assert extra['relay_runner_root'] == '/opt/codex-relay/slots/second/runner'
    assert extra['relay_codex_access_token_file'] == '/etc/codex-relay/slots/second/codex-credentials/access-token'
    assert primary['relay_runner_labels'][0] == extra['relay_runner_labels'][0]
    assert primary['relay_runner_labels'][1] != extra['relay_runner_labels'][1]
    original = config.execution_slot_label(public, public['consumer']['executionSlots'][1])
    public['consumer']['repository'] = 'another/consumer'
    assert config.execution_slot_label(public, public['consumer']['executionSlots'][1]) != original


def test_recovery_projection_targets_only_the_selected_fixed_slot():
    public = inputs()
    rendered = projection.render(public, 'a' * 40, ROOT)
    recovery = yaml.safe_load(rendered[public['consumer']['recoveryWorkflow']])
    event = recovery.get('on', recovery.get(True))
    selector = event['workflow_dispatch']['inputs']['execution_slot']
    assert selector == {'description': 'Original execution slot from the retained attempt; primary for historical attempts',
                        'required': False, 'type': 'choice', 'default': 'primary', 'options': ['primary', 'second']}
    job = recovery['jobs']['recover']
    assert "inputs.execution_slot || 'primary'" in job['runs-on']
    for slot in public['consumer']['executionSlots']:
        assert config.execution_slot_label(public, slot) in job['runs-on']
    step, = job['steps']
    assert step['env']['RECOVERY_SLOT'] == "${{ inputs.execution_slot || 'primary' }}"
    assert 'RELAY_RECOVERY_SLOT_IDENTITY_MISMATCH' in step['run']


def test_parallel_runtime_reconciliation_keeps_production_out_of_the_automatic_work_group():
    public = inputs()
    values = {**config.compile_inputs(public), 'relay_codex_work_group_planned': False,
              'relay_runner_group': public['environment']['runner']['user'],
              'relay_codex_user_planned': False, 'relay_codex_primary_group_planned': False,
              'relay_codex_runner_user_materialized': True, 'ansible_check_mode': False,
              'relay_production_slot_groups': {'stdout': public['environment']['runner']['user'] + ' ' +
                    public['environment']['codexWorkGroup'] + ' existing-approved-group'}}
    tasks = yaml.safe_load((ROOT / 'deploy/ansible/roles/relay_codex_runtime/tasks/main.yml').read_text())
    templar = Templar(loader=DataLoader(), variables=values)
    enabled = lambda task: all(templar.template('{{ ' + condition + ' }}') for condition in task['when'])
    legacy = next(task for task in tasks if task['name'] == 'Add the unprivileged relay runner to the shared Codex work group')
    assert not enabled(legacy)
    isolated = next(task for task in tasks if task['name'] == 'Reconcile only the primary runtime work membership for an isolated pool')
    assert enabled(isolated)
    assert templar.template(isolated['ansible.builtin.user'])['append'] is False
    production = next(task for task in tasks if task['name'] == 'Remove only automatic work access from the separate production runner')
    assert enabled(production)
    groups = templar.template(production['ansible.builtin.user']['groups'])
    assert groups == ['existing-approved-group']
    values.pop('relay_execution_slots')
    templar = Templar(loader=DataLoader(), variables=values)
    assert enabled(legacy)
    assert not enabled(isolated)
