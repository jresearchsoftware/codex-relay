"""Render real launch boundaries; no sudo, account changes or model execution."""
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys

import pytest
import yaml
from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / 'deploy/ansible'
ROLE = BACKEND / 'roles/relay_codex_runtime'
sys.path.insert(0, str(ROOT / 'deploy'))
import config

pytestmark = pytest.mark.skipif(sys.platform != 'linux', reason='native Linux group boundary')


def deployment(topology, group, *, repository_users=False):
    value = json.loads((ROOT / 'deploy/example.json').read_text())
    environment, consumer = value['environment'], value['consumer']
    if topology in ['serial', 'legacy', 'primary']:
        environment['codexWorkGroup'] = group
    if topology == 'serial':
        consumer['workGroup'] = group
    if repository_users:
        repository = consumer.pop('repository')
        consumer['repositories'] = [repository, 'example-org/second']
        consumer['repositoryRuntimeUsers'] = {'example-org/second': 'sample-extra-runtime'}
        environment['repository'] = repository
    if topology in ['primary', 'secondary']:
        environment['instance'] = {'reviewerPort': 18787, 'publicationEnabled': False}
        fields = ['workRoot', 'attemptRoot', 'dispatch', 'launcher',
                  'diagnosticsConfig', 'diagnosticsStore', 'diagnosticsRoot']
        consumer['executionSlots'] = [
            {'id': 'primary', 'runnerName': environment['generalRunner']['name'],
             'runnerUser': environment['generalRunner']['user'],
             'runtimeUser': consumer['runtimeUser'], 'workGroup': environment['codexWorkGroup'],
             'paths': {field: consumer['paths'][field] for field in fields}},
            {'id': 'second', 'runnerName': 'sample-second', 'runnerUser': 'sample-second-runner',
             'runtimeUser': 'sample-second-codex',
             'workGroup': group if topology == 'secondary' else 'sample-second-work',
             'paths': config.execution_slot_paths(environment['namespace'], 'second')},
        ]
    config.validate(value, ROOT)
    return value


def compiled_variables(topology, group, *, repository_users=False):
    compiled = config.compile_inputs(deployment(topology, group, repository_users=repository_users))
    variables = {**yaml.safe_load((BACKEND / 'group_vars/all.yml').read_text()), **compiled}
    if topology == 'secondary':
        # The installed slot include overlays these compiler-produced bindings.
        variables.update(compiled['relay_additional_execution_slots'][0])
    return variables


def render(source, variables):
    return Templar(loader=DataLoader(), variables=variables).template(
        source.read_text(), convert_data=False)


def existing_other_group():
    import grp
    for group in grp.getgrall():
        if (group.gr_gid > 0 and group.gr_gid != os.getgid()
                and re.fullmatch(r'[a-z][a-z0-9-]{0,30}', group.gr_name)):
            return group.gr_name
    pytest.skip('an existing nonzero group different from the current primary GID is required')


def absent_group():
    import grp
    for suffix in range(100):
        name = f'relay-missing-{os.getpid()}-{suffix}'
        try:
            grp.getgrnam(name)
        except KeyError:
            return name
    pytest.fail('unable to choose an absent synthetic group')


def launcher_fixture(tmp_path, topology, group, *, token_fifo=True, diagnostics_fifo=False):
    variables = compiled_variables(topology, group)
    work = tmp_path / 'work'
    cwd = work / 'event-171'
    sandbox = cwd / '.codex-sandbox'
    sandbox.mkdir(parents=True)
    (cwd / '.git').mkdir()
    input_file = sandbox / 'task-input.md'
    input_file.write_text('Synthetic boundary input; no model execution.')
    (sandbox / 'codex-result-schema.json').write_text('{"type":"object"}')
    token = tmp_path / 'token-must-not-be-read'
    if token_fifo:
        # A premature token read blocks instead of returning a false-positive
        # error. The subprocess timeout makes this ordering regression fail.
        os.mkfifo(token)
    diagnostics = tmp_path / 'diagnostics.json'
    if diagnostics_fifo:
        os.mkfifo(diagnostics)
    else:
        diagnostics.write_text('{"schemaVersion":"1.0","mode":"normal"}')
    diagnostic_helper = tmp_path / 'relay-codex-diagnostic.mjs'
    shutil.copyfile(ROLE / 'files/relay-codex-diagnostic.mjs', diagnostic_helper)
    shutil.copyfile(ROLE / 'files/relay-codex-isolation.mjs', tmp_path / 'relay-codex-isolation.mjs')
    variables.update(
        relay_codex_binary_path=str(tmp_path / 'model-must-not-execute'),
        relay_codex_package_home=str(tmp_path / 'package-home'),
        relay_codex_access_token_file=str(token),
        relay_dispatch_work_root=str(work),
        relay_diagnostics_config_path=str(diagnostics),
        relay_codex_diagnostic_path=str(diagnostic_helper),
    )
    launcher = tmp_path / 'launcher.mjs'
    launcher.write_text(render(ROLE / 'templates/relay-codex-launcher.mjs.j2', variables))
    (tmp_path / 'relay-codex-cleanup.py').write_text(
        render(ROLE / 'templates/relay-codex-cleanup.py.j2', variables))
    args = ['exec', '--json', '--model', 'synthetic-model', '--effort', 'high',
            '--input-file', str(input_file), '--cwd', str(cwd), '--issue', '171']

    def invoke(arguments=None):
        node = shutil.which('node')
        assert node, 'Node is required for the native rendered-launcher boundary'
        return subprocess.run(
            [node, '--experimental-default-type=module', str(launcher),
             *(args if arguments is None else arguments)],
            env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'},
            stdin=subprocess.DEVNULL, text=True, capture_output=True, timeout=12)

    return invoke, token


@pytest.mark.parametrize('topology', ['serial', 'primary', 'secondary'])
@pytest.mark.parametrize('failure', ['mismatch', 'unavailable'])
def test_rendered_launcher_rejects_launch_group_before_token_read(tmp_path, topology, failure):
    group = existing_other_group() if failure == 'mismatch' else absent_group()
    invoke, token = launcher_fixture(tmp_path, topology, group)
    result = invoke()
    expected = 'CODEX_LAUNCHER_WORK_GROUP_' + failure.upper()
    assert result.returncode == 64, result.stderr
    assert expected in result.stderr.splitlines(), result.stderr
    assert 'ACCESS_TOKEN' not in result.stderr
    assert result.stdout == ''
    assert stat.S_ISFIFO(token.lstat().st_mode)


@pytest.mark.parametrize('topology', ['serial', 'primary', 'secondary'])
def test_rendered_launcher_accepts_actual_primary_group_before_token_boundary(tmp_path, topology):
    import grp
    group = grp.getgrgid(os.getgid()).gr_name
    if os.getgid() == 0 or not re.fullmatch(r'[a-z][a-z0-9-]{0,30}', group):
        pytest.skip('current nonzero primary group must fit deployment identity syntax')
    invoke, token = launcher_fixture(tmp_path, topology, group, token_fifo=False)
    result = invoke()
    assert result.returncode == 64, result.stderr
    assert 'CODEX_LAUNCHER_ACCESS_TOKEN_UNAVAILABLE' in result.stderr.splitlines()
    assert 'WORK_GROUP_' not in result.stderr
    assert not token.exists()


@pytest.mark.parametrize('topology', ['serial', 'primary', 'secondary'])
def test_rendered_runtime_probe_precedes_group_diagnostics_and_token_reads(tmp_path, topology):
    invoke, token = launcher_fixture(tmp_path, topology, absent_group(), diagnostics_fifo=True)
    result = invoke(['--check-runtime'])
    assert result.returncode == 0, result.stderr
    assert result.stdout == 'CODEX_LAUNCHER_RUNTIME_READY\n'
    assert result.stderr == ''
    assert stat.S_ISFIFO(token.lstat().st_mode)


def test_legacy_group_omission_keeps_launcher_and_sudoers_abi(tmp_path):
    group = absent_group()
    variables = compiled_variables('legacy', group)
    assert 'relay_codex_launch_work_group' not in variables
    assert 'relay_execution_slots' not in variables
    invoke, _ = launcher_fixture(tmp_path, 'legacy', group, token_fifo=False)
    result = invoke()
    assert result.returncode == 64, result.stderr
    assert 'CODEX_LAUNCHER_ACCESS_TOKEN_UNAVAILABLE' in result.stderr.splitlines()
    assert 'WORK_GROUP_' not in result.stderr
    sudoers = render(ROLE / 'templates/relay-codex.sudoers.j2', variables)
    assert sudoers.splitlines()[-1] == (
        f"{variables['relay_runner_user']} ALL=({variables['relay_codex_user']}) "
        f"NOPASSWD: {variables['relay_codex_launcher_path']}")


@pytest.mark.parametrize('topology', ['serial', 'primary', 'secondary'])
@pytest.mark.parametrize('repository_users', [False, True])
def test_rendered_sudoers_binds_only_configured_runtime_users_and_work_group(
        tmp_path, topology, repository_users):
    group = existing_other_group()
    variables = compiled_variables(topology, group, repository_users=repository_users)
    sudoers = render(ROLE / 'templates/relay-codex.sudoers.j2', variables)
    users = list(dict.fromkeys([variables['relay_codex_user'],
                              *variables.get('relay_additional_runtime_users', [])]))
    expected = [
        f"Defaults:{variables['relay_runner_user']} !setenv",
        f"{variables['relay_runner_user']} ALL=({','.join(users)}:{group}) "
        f"NOPASSWD: {variables['relay_codex_launcher_path']}",
    ]
    assert [line for line in sudoers.splitlines() if line and not line.startswith('#')] == expected
    assert 'root' not in users
    visudo = shutil.which('visudo')
    if visudo is None and Path('/usr/sbin/visudo').is_file():
        visudo = '/usr/sbin/visudo'
    if visudo:
        path = tmp_path / 'synthetic.sudoers'
        path.write_text(sudoers)
        result = subprocess.run([visudo, '-cf', str(path)], text=True, capture_output=True, timeout=10)
        assert result.returncode == 0, result.stderr
