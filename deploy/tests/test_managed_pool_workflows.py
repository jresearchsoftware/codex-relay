"""Source-only managed workflow guards and installed-runtime transports.

Synthetic installed state does not qualify an installed pool or concurrency.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
import config
import workflow_projection

HEAD = 'a' * 40
CONSUMER_HEAD = 'c' * 40
NODE = shutil.which('node')


def normalized(value):
    # Use the public file-loading boundary: pool slots and the v4 contract must
    # come from actual configuration normalization, never a raw singleton dict.
    with tempfile.TemporaryDirectory(prefix='relay-workflow-config-') as temporary:
        path = Path(temporary) / 'deploy.json'
        path.write_text(json.dumps(value))
        return config.load(path, ROOT)


def pool_configuration(capacity=6, repositories=None, installed=False):
    value = json.loads((ROOT / 'deploy/example.json').read_text())
    value['consumer']['generalRunnerPool'] = {'desiredCapacity': capacity}
    value['environment']['instance'] = {'reviewerPort': 18787, 'publicationEnabled': False}
    value['environment']['generalRunner'].update(
        scope='organization', group='sample-general-pool',
        poolApp={'appId': '123', 'installationId': '456',
                 'privateKeyFile': '/owner-private/runner-app.pem'})
    if repositories:
        del value['consumer']['repository']
        value['consumer']['repositories'] = repositories
        value['environment']['repository'] = repositories[0]
    if installed:
        anchor = config.deployment_repository(value)
        value['source']['repository'] = 'https://github.com/' + anchor + '.git'
        value['environment']['localApply'] = {'source': 'installed'}
    return normalized(value)


def workflows(value, repository=None):
    rendered = workflow_projection.render(value, HEAD, ROOT, repository)
    return {name: yaml.safe_load(raw) for name, raw in rendered.items()}


def step(workflow):
    job, = workflow['jobs'].values()
    selected, = job['steps']
    return selected


def calls(result):
    return [json.loads(line.split('=', 1)[1]) for line in result.stdout.splitlines()
            if line.startswith('FIXTURE_CALL=')]


@pytest.fixture
def installed_runtime(tmp_path):
    if not NODE or os.name == 'nt':
        pytest.skip('Full Bash and installed-path execution requires Linux and Node')
    install = tmp_path / 'installed'
    release = install / 'releases' / HEAD
    source = release / 'reviewed-source'
    (source / 'deploy/workflows').mkdir(parents=True)
    (release / 'bin').mkdir()
    (install / 'current').symlink_to(release, target_is_directory=True)
    (source / '.relay-source.json').write_text(json.dumps({'revision': HEAD}))
    compatibility = source / 'deploy/workflows/contract.json'
    shutil.copyfile(ROOT / 'deploy/workflows/contract.json', compatibility)
    (release / 'bin/relay-routing.mjs').write_text(
        'export async function main() {\n'
        'console.log("FIXTURE_CALL=" + JSON.stringify({kind: "routing",\n'
        'repository: process.env.RELAY_REPOSITORY, slot: process.env.RELAY_EXECUTION_SLOT})); }\n'
        'export async function reportRoutingResult(run) { await run(); return 0; }\n')
    (release / 'bin/relay-publication-recovery.mjs').write_text(
        'import { readFileSync } from "node:fs";\n'
        'console.log("FIXTURE_CALL=" + JSON.stringify({kind: "recovery",\n'
        'repository: process.env.RELAY_REPOSITORY, slot: process.env.RELAY_EXECUTION_SLOT,\n'
        'request: JSON.parse(readFileSync(0, "utf8"))}));\n')
    identity_stub = tmp_path / 'id-fixture'
    identity_stub.write_text('#!' + sys.executable + '\nimport os\nprint(os.environ["FIXTURE_USER"])\n')
    identity_stub.chmod(0o755)
    sudo_stub = tmp_path / 'sudo-fixture'
    sudo_stub.write_text('#!' + sys.executable + '\nimport json, os, sys\n'
                         'print("FIXTURE_CALL=" + json.dumps({"kind": "lifecycle",\n'
                         '"args": sys.argv[1:], "slot": os.environ.get("RELAY_EXECUTION_SLOT")}))\n'
                         'sys.exit(int(os.environ.get("FIXTURE_EXIT", "0")))\n')
    sudo_stub.chmod(0o755)

    def execute(selected, runner, user, **overrides):
        # Execute the entire rendered Bash guard and its real JS transport.
        # Redirect fixed installed paths/executables only; sudo is never run.
        code = (selected['run'].replace('/opt/codex-relay', str(install))
                .replace('/usr/bin/id', str(identity_stub))
                .replace('/usr/bin/sudo', str(sudo_stub))
                .replace('/usr/bin/node', NODE))
        environment = {key: value for key, value in selected['env'].items() if '${{' not in value}
        environment.update(RUNNER_NAME=runner, FIXTURE_USER=user, GITHUB_SHA=CONSUMER_HEAD,
                           GITHUB_TOKEN='', RELAY_LIFECYCLE_ACTION='apply',
                           RECOVERY_OPERATION='inspect', RECOVERY_RUN_ID='99',
                           RECOVERY_ATTEMPT_ID='run-99', RECOVERY_AUTHORIZATION_ID='', RECOVERY_HEAD='')
        environment.update(overrides)
        return subprocess.run(['bash', '--noprofile', '--norc', '-euo', 'pipefail', '-c', code],
                              env={**os.environ, **environment}, text=True, capture_output=True,
                              timeout=20)

    return execute, compatibility


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


def test_six_member_plural_self_consumer_projects_one_v4_general_pool_and_anchor_lifecycle():
    repositories = ['example-org/relay', 'example-org/second', 'example-org/inactive']
    value = pool_configuration(repositories=repositories, installed=True)
    assert value['consumer']['generalRunnerPool']['desiredCapacity'] == 6
    # Normalized stable routes outlive physical capacity changes.
    slots = value['consumer']['executionSlots']
    assert len(slots) == 32
    assert [slot['runnerName'] for slot in slots[:6]] == [
        'relay-general', *['relay-general-' + str(number) for number in range(2, 7)]]
    expected = {'group': 'sample-general-pool', 'labels': [
        'self-hosted', 'Linux', 'X64', config.general_pool_label(value)]}
    for repository in repositories:
        projected = workflows(value, repository)
        assert (workflow_projection.PRODUCTION in projected) == (repository == repositories[0])
        route = projected[value['consumer']['routingWorkflow']]
        recovery = projected[value['consumer']['recoveryWorkflow']]
        assert set(route[True]) == {'issues', 'pull_request_target', 'workflow_dispatch'}
        assert set(recovery[True]) == {'workflow_dispatch'}
        assert 'execution_slot' not in recovery[True]['workflow_dispatch']['inputs']
        guard = step(route)['run'].split('\nexec /usr/bin/node', 1)[0]
        assert guard.startswith('case "$RUNNER_NAME:$(/usr/bin/id -un)" in\n')
        assert 'pool-32' in guard
        for name, workflow in projected.items():
            job, = workflow['jobs'].values()
            selected = step(workflow)
            assert job['runs-on'] == expected
            assert value['environment']['runner']['group'] != job['runs-on']['group']
            assert value['environment']['runner']['labels'][0] not in job['runs-on']['labels']
            assert selected['env']['EXPECTED_WORKFLOW_CONTRACT'] == 'relay-workflows-v4'
            assert selected['run'].startswith(guard + '\n')
            assert '${{' not in selected['run']
            assert "github.repository == '" + repository + "'" in job['if']
            if name != workflow_projection.PRODUCTION:
                assert selected['env']['RELAY_REPOSITORY'] == repository
        assert 'RECOVERY_SLOT' not in step(recovery)['env']
        assert 'RECOVERY_SLOT' not in step(recovery)['run']


@pytest.mark.skipif(not NODE, reason='Node is required to evaluate native workflow conditions')
def test_plural_pool_conditions_preserve_owner_ref_event_and_fork_boundaries():
    repositories = ['example-org/relay', 'example-org/second']
    value = pool_configuration(repositories=repositories, installed=True)
    projected = []
    for repository in repositories:
        for name, workflow in workflows(value, repository).items():
            job, = workflow['jobs'].values()
            projected.append({'repository': repository, 'condition': job['if'],
                              'lifecycle': name == workflow_projection.PRODUCTION,
                              'routing': name == value['consumer']['routingWorkflow']})
    code = r'''
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
for (const item of JSON.parse(readFileSync(0, 'utf8'))) {
  const source = item.condition.trim().slice(3, -2);
  const evaluate = Function('github', `return (${source});`);
  const base = {repository: item.repository, actor: 'example-owner', triggering_actor: 'example-owner',
    ref: 'refs/heads/main', event_name: 'workflow_dispatch', event: {}};
  assert.equal(evaluate(base), true);
  for (const change of [{repository: 'foreign/repo'},
    {repository: item.repository === 'example-org/relay' ? 'example-org/second' : 'example-org/relay'},
    {actor: 'other'}, {triggering_actor: 'other'}, {ref: 'refs/heads/candidate'}, {ref: 'refs/tags/main'}]) {
    assert.equal(evaluate({...base, ...change}), false);
  }
  if (item.lifecycle) {
    for (const event_name of ['issues', 'pull_request', 'pull_request_target', 'push']) {
      assert.equal(evaluate({...base, event_name}), false);
    }
  }
  if (item.routing) {
    for (const name of ['codex-ready-auto', 'codex-ready-manual']) {
      const labeled = {...base, event_name: 'pull_request_target', event: {
        action: 'labeled', label: {name}, pull_request: {head: {repo: {full_name: item.repository}}}}};
      assert.equal(evaluate(labeled), true);
      assert.equal(evaluate({...labeled, event: {...labeled.event, label: {name: 'step-3'}}}), false);
      assert.equal(evaluate({...labeled, event: {...labeled.event, action: 'unlabeled'}}), false);
      assert.equal(evaluate({...labeled, event: {...labeled.event,
        pull_request: {head: {repo: {full_name: 'foreign/fork'}}}}}), false);
    }
  }
}
'''
    checked = subprocess.run([NODE, '--input-type=module', '-e', code], input=json.dumps(projected),
                             text=True, capture_output=True, timeout=20)
    assert checked.returncode == 0, checked.stderr


def test_all_six_general_members_execute_apply_stop_resume_transport(installed_runtime):
    execute, _ = installed_runtime
    value = pool_configuration(repositories=['example-org/relay', 'example-org/second'], installed=True)
    selected = step(workflows(value)[workflow_projection.PRODUCTION])
    for member in value['consumer']['executionSlots'][:6]:
        for action in ['apply', 'stop', 'resume']:
            result = execute(selected, member['runnerName'], member['runnerUser'], RELAY_LIFECYCLE_ACTION=action)
            assert result.returncode == 0, result.stderr
            assert calls(result) == [{'kind': 'lifecycle', 'slot': member['id'], 'args': [
                '-n', '/usr/local/sbin/codex-relay-owner-lifecycle', action + ':' + HEAD + ':' + CONSUMER_HEAD]}]


@pytest.mark.parametrize('capacity,members', [(6, [0, 1, 5]), (1, [0])])
def test_routing_and_recovery_transport_targets_survive_retired_original_member(
        installed_runtime, capacity, members):
    execute, _ = installed_runtime
    repositories = ['example-org/relay', 'example-org/second']
    value = pool_configuration(capacity, repositories=repositories, installed=True)
    for repository in repositories:
        projected = workflows(value, repository)
        for index in members:
            member = value['consumer']['executionSlots'][index]
            routed = execute(step(projected[value['consumer']['routingWorkflow']]),
                             member['runnerName'], member['runnerUser'])
            assert routed.returncode == 0, routed.stderr
            assert calls(routed) == [{'kind': 'routing', 'repository': repository, 'slot': member['id']}]
            for operation in ['inspect', 'recover', 'inspect-prepublication', 'recover-prepublication']:
                recovering = operation in ['recover', 'recover-prepublication']
                prepublication = operation in ['inspect-prepublication', 'recover-prepublication']
                result = execute(step(projected[value['consumer']['recoveryWorkflow']]),
                                 member['runnerName'], member['runnerUser'], RECOVERY_OPERATION=operation,
                                 RECOVERY_AUTHORIZATION_ID='123' if recovering else '',
                                 RECOVERY_HEAD=HEAD if prepublication else '',
                                 # The workflow must overwrite an inherited stale
                                 # execution identity and never select this slot.
                                 RELAY_EXECUTION_SLOT='pool-6', RECOVERY_SLOT='pool-6')
                assert result.returncode == 0, result.stderr
                request = {'runId': 99, 'attemptId': 'run-99'}
                if operation != 'recover':
                    request['operation'] = operation
                if recovering:
                    request['authorizationId'] = 123
                if prepublication:
                    request['head'] = HEAD
                assert calls(result) == [{'kind': 'recovery', 'repository': repository,
                                          'slot': member['id'], 'request': request}]


def test_pool_guards_reject_foreign_runner_and_wrong_user_before_transport(installed_runtime):
    execute, _ = installed_runtime
    value = pool_configuration(repositories=['example-org/relay', 'example-org/second'], installed=True)
    general = value['environment']['generalRunner']
    production = value['environment']['runner']
    for workflow in workflows(value).values():
        selected = step(workflow)
        for runner, user in [('foreign-runner', general['user']),
                             (general['name'] + '-33', general['user']),
                             (general['name'], 'foreign-user'),
                             (general['name'] + '-2', value['consumer']['runtimeUser']),
                             (production['name'], production['user'])]:
            result = execute(selected, runner, user)
            assert result.returncode != 0
            assert 'RELAY_RUNNER_SLOT_IDENTITY_MISMATCH' in result.stderr
            assert not calls(result)
            assert 'installedRelayHead' not in result.stdout


def test_normalized_v4_transports_reject_stale_installed_v3_contract(installed_runtime):
    execute, compatibility = installed_runtime
    value = pool_configuration(repositories=['example-org/relay', 'example-org/second'], installed=True)
    member = value['consumer']['executionSlots'][1]
    compatibility.write_text(json.dumps({'workflowContract': 'relay-workflows-v3'}))
    for workflow in workflows(value).values():
        result = execute(step(workflow), member['runnerName'], member['runnerUser'])
        assert result.returncode != 0
        assert 'INSTALLED_RELAY_IDENTITY_MISMATCH' in result.stderr
        assert not calls(result)


def test_normalized_serial_self_consumer_keeps_single_runner_v3_transport(installed_runtime):
    execute, _ = installed_runtime
    raw = json.loads((ROOT / 'deploy/example.json').read_text())
    raw['source']['repository'] = 'https://github.com/' + raw['consumer']['repository'] + '.git'
    raw['environment']['localApply'] = {'source': 'installed'}
    value = normalized(raw)
    assert 'executionSlots' not in value['consumer']
    general = value['environment']['generalRunner']
    for workflow in workflows(value).values():
        job, = workflow['jobs'].values()
        selected = step(workflow)
        assert job['runs-on'] == ['self-hosted', 'Linux', 'X64', 'relay']
        assert selected['env']['EXPECTED_WORKFLOW_CONTRACT'] == 'relay-workflows-v3'
        assert selected['run'].startswith('test "$RUNNER_NAME" = relay-general\n'
                                           'test "$(/usr/bin/id -un)" = relay-general-runner\n')
        result = execute(selected, general['name'], general['user'], RELAY_EXECUTION_SLOT='')
        assert result.returncode == 0, result.stderr
        assert len(calls(result)) == 1
        assert calls(result)[0]['slot'] == ''
        blocked = execute(selected, general['name'] + '-2', general['user'])
        assert blocked.returncode != 0
        assert not calls(blocked)
