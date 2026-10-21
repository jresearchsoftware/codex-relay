"""Source-only multi-repository installation and projection contracts."""
import copy
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest
import yaml
from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
import config
import managed_pool
import pool_eligibility
import workflow_projection
from test_managed_pool import inputs, MemoryState, Remote, Host
from test_execution_slots import inputs as explicit_inputs


def shared():
    value = inputs(repository='example-org/first')
    del value['consumer']['repository']
    value['consumer']['repositories'] = ['example-org/first', 'example-org/second']
    value['environment']['repository'] = 'example-org/first'
    return value


@pytest.mark.parametrize('work_group', [False, True])
def test_explicit_installation_anchor_and_shared_rendered_consumer(work_group):
    value = shared()
    if work_group:
        value['consumer']['workGroup'] = value['environment']['codexWorkGroup']
    value['consumer']['repositoryRuntimeUsers'] = {'example-org/second': 'second-runtime'}
    config.validate(value, ROOT)
    compiled = config.compile_inputs(value)
    assert compiled['relay_github_repository'] == 'example-org/first'
    assert compiled['relay_reviewer_repositories'] == value['consumer']['repositories']
    assert compiled['relay_additional_runtime_users'] == ['second-runtime']
    source = (ROOT / 'deploy/ansible/roles/relay_controller/templates/consumer.json.j2').read_text()
    rendered = Templar(loader=DataLoader(), variables=compiled).template(source, convert_data=False)
    assert json.loads(rendered) == value['consumer']
    assert compiled['relay_general_runner_pool']['desiredCapacity'] == 2
    assert len(compiled['relay_general_runner_pool']['members']) == 32
    for anchor in [None, 'foreign/repository']:
        broken = copy.deepcopy(value)
        if anchor is None:
            del broken['environment']['repository']
        else:
            broken['environment']['repository'] = anchor
        with pytest.raises(config.InvalidConfig, match='environment.repository'):
            config.validate(broken, ROOT)


def test_workflow_projection_selects_each_explicit_target_and_rejects_foreign(tmp_path):
    value = shared()
    head = 'a' * 40
    for repository in value['consumer']['repositories']:
        destination = tmp_path / repository.split('/')[1]
        destination.mkdir()
        manifest = workflow_projection.project(value, head, ROOT, destination, repository)
        assert manifest['consumerRepository'] == repository
        assert workflow_projection.verify(value, head, ROOT, destination, repository) == manifest
        routing = yaml.safe_load((destination / value['consumer']['routingWorkflow']).read_text())
        job = routing['jobs']['route']
        assert repository in job['if']
        assert job['steps'][0]['env']['RELAY_REPOSITORY'] == repository
        assert job['runs-on']['labels'][-1] == config.general_pool_label(value)
    with pytest.raises(config.InvalidConfig, match='environment.repository'):
        workflow_projection.render(value, head, ROOT, 'foreign/repository')
    with pytest.raises(config.InvalidConfig, match='workflow-projection-target-mismatch'):
        workflow_projection.verify(value, head, ROOT, tmp_path / 'first', 'example-org/second')


def test_reviewer_targets_are_independent_of_the_writer_pool_organization():
    value = shared()
    value['environment']['reviewerRepositories'] = ['another-org/review-only']
    config.validate(value, ROOT)
    assert config.compile_inputs(value)['relay_reviewer_repositories'] == ['another-org/review-only']
    assert config.compile_inputs(value)['relay_general_runner_pool']['repositories'] == value['consumer']['repositories']


def test_peer_repository_count_does_not_allocate_or_limit_pool_capacity():
    value = shared()
    value['consumer']['repositories'] = ['example-org/repository-' + str(index) for index in range(33)]
    value['environment']['repository'] = value['consumer']['repositories'][0]
    config.validate(value, ROOT)
    contract = managed_pool.pool_contract(value)
    workflows = pool_eligibility._peer_refs(value, value['environment']['namespace'], contract)
    assert set(workflows) == set(value['consumer']['repositories'])
    assert contract['desiredCapacity'] == 2


def test_pool_registers_all_writer_targets_with_one_capacity_and_trusted_refs(tmp_path):
    value = shared()
    contract = managed_pool.pool_contract(value)
    expected = {repository: [repository + '/' + value['consumer'][key] + '@refs/heads/main'
                             for key in ['routingWorkflow', 'recoveryWorkflow']]
                for repository in value['consumer']['repositories']}
    assert pool_eligibility.eligible_workflows(contract, root=tmp_path, owner_uid=tmp_path.stat().st_uid) == expected
    store, remote = MemoryState(), Remote()
    local = Host(remote, store)
    report = managed_pool.reconcile(contract, store, remote, local)
    assert report['capacity'] == 2
    assert set(store.value['consumers']) == set(expected)
    assert len(remote.values) == 2
    assert len({json.dumps(binding, sort_keys=True) for binding in store.value['consumers'].values()}) == 1


@pytest.mark.parametrize('singleton', [False, True])
def test_installed_owner_lifecycle_is_fixed_and_belongs_only_to_the_installation_anchor(tmp_path, singleton):
    value = shared()
    if singleton:
        value['consumer']['repository'] = value['consumer'].pop('repositories')[0]
        del value['environment']['repository']
    anchor = 'example-org/first'
    value['source'] = {'repository': 'https://github.com/' + anchor + '.git', 'revision': 'main'}
    value['environment']['localApply'] = {'source': 'installed'}
    config.validate(value, ROOT)
    contract = managed_pool.pool_contract(value)
    assert managed_pool.LIFECYCLE_WORKFLOW == workflow_projection.PRODUCTION
    expected = {repository: [repository + '/' + value['consumer'][key] + '@refs/heads/main'
                             for key in ['routingWorkflow', 'recoveryWorkflow']]
                for repository in contract['repositories']}
    expected[anchor].append(anchor + '/' + workflow_projection.PRODUCTION + '@refs/heads/main')
    assert contract['workflowRefs'] == expected[anchor]
    assert contract['workflowRefsByRepository'] == expected
    assert pool_eligibility.eligible_workflows(contract, root=tmp_path,
                                             owner_uid=tmp_path.stat().st_uid) == expected
    for repository in contract['repositories']:
        projected = workflow_projection.render(value, 'a' * 40, ROOT, repository)
        assert (workflow_projection.PRODUCTION in projected) == (repository == anchor)


def test_checkout_configuration_keeps_pair_only_contract_and_has_no_third_workflow_option():
    value = shared()
    contract = managed_pool.pool_contract(value)
    assert all(len(workflows) == 2 for workflows in contract['workflowRefsByRepository'].values())
    value['consumer']['lifecycleWorkflow'] = '.github/workflows/unknown.yml'
    with pytest.raises(config.InvalidConfig):
        config.validate(value, ROOT)


@pytest.mark.parametrize('topology', ['default', 'managed', 'independent'])
def test_rendered_launcher_keeps_repository_runtime_overrides_on_the_default_identity(topology):
    value = shared()
    if topology == 'independent':
        value = explicit_inputs()
        del value['consumer']['repository']
        value['consumer']['repositories'] = ['example-org/first', 'example-org/second']
        value['environment']['repository'] = 'example-org/first'
    value['consumer']['repositoryRuntimeUsers'] = {'example-org/second': 'second-runtime'}
    config.validate(value, ROOT)
    compiled = config.compile_inputs(value)
    variables = {**yaml.safe_load((ROOT / 'deploy/ansible/group_vars/all.yml').read_text()), **compiled}
    if topology != 'default':
        slot = compiled['relay_additional_execution_slots'][0]
        include, = yaml.safe_load((ROOT / 'deploy/ansible/tasks/execution-slot.yml').read_text())
        variables['relay_slot_inputs'] = slot
        variables.update(Templar(loader=DataLoader(), variables=variables).template(include['vars']))
        expected_map = {} if topology == 'independent' else value['consumer']['repositoryRuntimeUsers']
        assert variables['relay_repository_runtime_users'] == expected_map
        assert variables['relay_additional_runtime_users'] == ([] if topology == 'independent' else ['second-runtime'])
    template = (ROOT / 'deploy/ansible/roles/relay_codex_runtime/templates/relay-codex-launcher.mjs.j2').read_text()
    templar = Templar(loader=DataLoader(), variables=variables)
    launcher = templar.template(template, convert_data=False)
    profiles = re.search(r'const REPOSITORY_PROFILES = (\[[\s\S]*?\n\]);', launcher).group(1)
    rendered = json.loads(subprocess.check_output(
        ['node', '-e', 'const profiles=' + profiles + ';process.stdout.write(JSON.stringify(profiles));'], text=True))
    runtime = variables['relay_codex_user']
    assert {profile['repository']: profile['user'] for profile in rendered} == {
        'example-org/first': runtime,
        'example-org/second': runtime if topology == 'independent' else 'second-runtime',
    }
    assert {profile['root'] for profile in rendered} == {
        variables['relay_dispatch_work_root'] + '/repositories/' + repository
        for repository in value['consumer']['repositories']}
    sudoers = templar.template(
        (ROOT / 'deploy/ansible/roles/relay_codex_runtime/templates/relay-codex.sudoers.j2').read_text(),
        convert_data=False)
    if topology == 'independent':
        assert f'ALL=({runtime}:{variables["relay_codex_work_group"]})' in sudoers
        assert 'second-runtime' not in sudoers
        assert 'const TOKEN_FILE = "' + variables['relay_codex_access_token_file'] + '";' in launcher
    else:
        assert f'ALL=({runtime},second-runtime:{variables["relay_codex_work_group"]})' in sudoers


def test_repository_runtime_users_keep_all_explicit_slot_work_groups_separate():
    value = explicit_inputs()
    del value['consumer']['repository']
    value['consumer']['repositories'] = ['example-org/first', 'example-org/second']
    value['environment']['repository'] = 'example-org/first'
    value['consumer']['repositoryRuntimeUsers'] = {
        'example-org/second': value['consumer']['executionSlots'][1]['workGroup']}
    with pytest.raises(config.InvalidConfig, match='executionSlots.isolated-work-groups'):
        config.validate(value, ROOT)


@pytest.mark.parametrize('exists', [False, True])
def test_optional_repository_runtime_account_preserves_existing_owner_settings(exists):
    source = ROOT / 'deploy/ansible/roles/relay_codex_runtime/tasks/repository-runtime-user.yml'
    task = next(task for task in yaml.safe_load(source.read_text()) if task['name'] ==
                'Create the configured non-login runtime account with shared work access')
    account = {'second-runtime': ['x', 1201, 1301, 'owner account', '/owner/home', '/bin/bash']} if exists else {}
    variables = {'relay_repository_runtime_user': 'second-runtime', 'relay_state_root': '/var/lib/example',
                 'relay_codex_work_group': 'shared-work', 'omit': '__omit__',
                 'relay_repository_runtime_account': {'ansible_facts': {'getent_passwd': account}}}
    rendered = Templar(loader=DataLoader(), variables=variables).template(task['ansible.builtin.user'])
    assert rendered['append'] is True
    assert rendered['groups'] == ['shared-work']
    assert rendered['create_home'] is False
    assert {key: rendered[key] for key in ['group', 'home', 'shell']} == (
        {'group': '__omit__', 'home': '__omit__', 'shell': '__omit__'} if exists else
        {'group': 'second-runtime', 'home': '/var/lib/example/runtime-users/second-runtime', 'shell': '/usr/sbin/nologin'})


@pytest.mark.skipif(sys.platform != 'linux' or os.geteuid() == 0, reason='non-root native Linux runtime identity')
def test_installed_launcher_binds_actual_user_to_repository_before_credential_access(tmp_path):
    import grp
    value = shared()
    actual_user = subprocess.check_output(['/usr/bin/id', '-un'], text=True).strip()
    value['consumer']['repositoryRuntimeUsers'] = {'example-org/second': actual_user}
    compiled = yaml.safe_load((ROOT / 'deploy/ansible/group_vars/all.yml').read_text())
    compiled.update(config.compile_inputs(value))
    compiled.update(relay_dispatch_work_root=str(tmp_path / 'work'), relay_config_root=str(tmp_path / 'config'),
                    relay_codex_work_group=grp.getgrgid(os.getgid()).gr_name,
                    relay_diagnostics_config_path=str(tmp_path / 'diagnostics.json'),
                    relay_codex_diagnostic_path=str(ROOT / 'deploy/ansible/roles/relay_codex_runtime/files/relay-codex-diagnostic.mjs'))
    (tmp_path / 'diagnostics.json').write_text('{"schemaVersion":"1.0","mode":"normal"}')
    source = (ROOT / 'deploy/ansible/roles/relay_codex_runtime/templates/relay-codex-launcher.mjs.j2').read_text()
    rendered = Templar(loader=DataLoader(), variables=compiled).template(source, convert_data=False)
    launcher = tmp_path / 'launcher.mjs'
    launcher.write_text(rendered)
    (tmp_path / 'relay-codex-isolation.mjs').write_text(
        (ROOT / 'deploy/ansible/roles/relay_codex_runtime/files/relay-codex-isolation.mjs').read_text())
    for repository, expected in [('example-org/first', 'REPOSITORY_RUNTIME_BINDING_INVALID'),
                                 ('example-org/second', 'ACCESS_TOKEN_UNAVAILABLE')]:
        cwd = tmp_path / 'work/repositories' / repository / 'task'
        sandbox = cwd / '.codex-sandbox'
        sandbox.mkdir(parents=True)
        (cwd / '.git').mkdir()
        (sandbox / 'task-input.md').write_text('synthetic input')
        (sandbox / 'codex-result-schema.json').write_text('{"type":"object"}')
        result = subprocess.run(['node', str(launcher), 'exec', '--json', '--model', 'synthetic',
                                 '--effort', 'low', '--input-file', str(sandbox / 'task-input.md'),
                                 '--cwd', str(cwd), '--issue', '1'], capture_output=True, text=True)
        assert result.returncode == 64
        assert 'CODEX_LAUNCHER_' + expected in result.stderr
