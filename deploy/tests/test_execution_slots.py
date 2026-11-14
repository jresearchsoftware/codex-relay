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
    return config.load(ROOT / 'deploy/example.json', ROOT)


def test_parallel_topology_compiles_fixed_identity_and_retains_one_consumer_digest():
    public = inputs()
    config.validate(public, ROOT)
    compiled = config.compile_inputs(public)
    assert compiled['relay_execution_slots'] == public['consumer']['executionSlots']
    assert compiled['relay_execution_slot'] == 'primary'
    assert compiled['relay_execution_slot_isolation'] is True
    assert len(compiled['relay_additional_execution_slots']) == 31
    extra = compiled['relay_additional_execution_slots'][0]
    assert extra['relay_runner_registration_scope'] == 'organization'
    assert extra['relay_runner_service_name'] == 'relay-general-pool-2.service'
    assert extra['relay_codex_user'] == 'relay-codex'
    assert extra['relay_dispatch_state_root'] == '/var/lib/codex-relay/slots/pool-2/dispatch'
    assert extra['relay_runner_registration_helper_path'] == '/opt/codex-relay/slots/pool-2/relay-runner-registration'
    values = {**yaml.safe_load((ROOT / 'deploy/ansible/group_vars/all.yml').read_text()), **compiled}
    source = (ROOT / 'deploy/ansible/roles/relay_controller/templates/consumer.json.j2').read_text()
    installed = json.loads(Templar(loader=DataLoader(), variables=values).template(source, convert_data=False))
    assert installed['executionSlots'] == public['consumer']['executionSlots']
    assert installed['paths']['claimRoot'] == public['consumer']['paths']['claimRoot']
    assert installed['runtimeUser'] == public['consumer']['runtimeUser']


def test_slot_journal_creation_preserves_final_runner_ownership():
    public = inputs()
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


@pytest.mark.parametrize('capacity', [1, 2, 32])
@pytest.mark.parametrize('manage_packages', [False, True])
@pytest.mark.parametrize('retained', [False, True])
def test_shared_slot_work_runs_once_without_removing_any_namespace_probe(capacity, manage_packages, retained):
    public = inputs()
    public['consumer']['generalRunnerPool']['desiredCapacity'] = capacity
    compiled = config.compile_inputs(public)
    defaults = yaml.safe_load((ROOT / 'deploy/ansible/group_vars/all.yml').read_text())
    site = yaml.safe_load((ROOT / 'deploy/ansible/site.yml').read_text())[1]['post_tasks']
    slot, = yaml.safe_load((ROOT / 'deploy/ansible/tasks/execution-slot.yml').read_text())
    shared = yaml.safe_load((ROOT / 'deploy/ansible/tasks/execution-slot-shared.yml').read_text())
    values = {**defaults, **compiled, 'ansible_check_mode': False,
              'relay_manage_base_packages': manage_packages,
              'relay_consumer_publication_continuation': retained,
              'relay_retained_reviewer_config_adoption': retained}

    def enabled(task, scope=values):
        conditions = task.get('when', [])
        if isinstance(conditions, str):
            conditions = [conditions]
        templar = Templar(loader=DataLoader(), variables=scope)
        return all(templar.template('{{ ' + condition + ' }}') for condition in conditions)

    package, = [task for task in site if task.get('ansible.builtin.apt', {}).get('name') == 'bubblewrap']
    primary = next(task for task in site if task['name'] ==
                   'Prove the primary runtime can enter its private process namespace')
    extra = next(task for task in site if task.get('ansible.builtin.include_tasks') == 'tasks/execution-slot.yml')
    shared_include = next(task for task in site if task.get('ansible.builtin.include_tasks') == 'tasks/execution-slot-shared.yml')
    assert site.index(package) < site.index(primary) < site.index(shared_include) < site.index(extra)
    assert enabled(package) == (manage_packages and not retained)
    assert enabled(shared_include) == enabled(extra) == (not retained)
    # A failed package operation retains Ansible's ordinary fatal failure; it
    # cannot reach a namespace probe with an ignored installation failure.
    assert 'ignore_errors' not in package and 'failed_when' not in package
    assert extra['vars']['relay_execution_slot_shared_prerequisites'] is True
    assert len(compiled['relay_additional_execution_slots']) == 31
    assert enabled(primary)
    for inputs_slot in compiled['relay_additional_execution_slots']:
        scope = {**values, 'relay_slot_inputs': inputs_slot, **extra['vars']}
        scope.update(Templar(loader=DataLoader(), variables=scope).template(slot['vars']))
        fallback = next(task for task in slot['block'] if 'ansible.builtin.apt' in task)
        probe = next(task for task in slot['block'] if task['name'] ==
                     'Prove that the optional runtime can enter its private process namespace')
        assert not enabled(fallback, scope)
        assert enabled(probe, scope)
        # Direct include callers retain the package fallback, including the
        # package-management-disabled contract.
        scope.pop('relay_execution_slot_shared_prerequisites')
        assert enabled(fallback, scope) == manage_packages
    groups = Templar(loader=DataLoader(), variables=values).template(shared[0]['loop'])
    expected = {slot[key] for slot in compiled['relay_additional_execution_slots']
                for key in ('relay_runner_group', 'relay_codex_group', 'relay_codex_work_group')}
    assert set(groups) == expected and len(groups) == len(expected)


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


@pytest.mark.parametrize('capacity', [1, 2])
def test_current_pool_projection_keeps_max_queue_and_separates_native_attempt_groups(capacity):
    public = inputs()
    public['consumer']['generalRunnerPool']['desiredCapacity'] = capacity
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




def test_parallel_projection_cannot_silently_accept_an_older_serial_runtime_contract(tmp_path):
    templates = tmp_path / 'deploy/workflows'
    templates.mkdir(parents=True)
    (templates / 'contract.json').write_text('{"workflowContract":"relay-workflows-v3"}')
    with pytest.raises(config.InvalidConfig, match='parallel-workflow-contract-required'):
        projection.render(inputs(), 'a' * 40, tmp_path)


def test_removed_slot_registration_selector_stops_before_source_or_remote_transport(tmp_path):
    public = inputs()
    pathname = tmp_path / 'relay.json'
    pathname.write_text(json.dumps(public))
    result = subprocess.run([sys.executable, str(ROOT / 'deploy/relay-deploy.py'),
                             '--config', str(pathname), '--phase', 'general-runner-enable',
                             '--authorize-general-runner-enable', '--execution-slot', 'foreign'],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode != 0
    assert 'invalid choice' in result.stderr or 'unrecognized arguments' in result.stderr
    assert 'source-identity' not in result.stderr






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
    # One managed runtime identity can be shared by qualified namespaces; keep
    # its existing memberships while adding this installation's work group.
    assert templar.template(isolated['ansible.builtin.user'])['append'] is True
    production = next(task for task in tasks if task['name'] == 'Remove only automatic work access from the separate production runner')
    assert enabled(production)
    groups = templar.template(production['ansible.builtin.user']['groups'])
    assert groups == ['existing-approved-group']


@pytest.mark.parametrize('surface', ['load', 'compile', 'projection'])
def test_fresh_serial_and_independent_slot_models_are_not_current_entrypoints(surface):
    public = inputs()
    public['consumer'].pop('generalRunnerPool')
    for explicit in [False, True]:
        selected = json.loads(json.dumps(public))
        if not explicit:
            selected['consumer'].pop('executionSlots')
        with pytest.raises(config.InvalidConfig, match='generalRunnerPool.required'):
            if surface == 'load':
                config.loads(json.dumps(selected), ROOT)
            elif surface == 'compile':
                config.compile_inputs(selected)
            else:
                projection.render(selected, 'a' * 40, ROOT)
