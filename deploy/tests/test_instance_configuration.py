"""Exercise compiled instance identities and the actual pre-mutation guard."""
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

import pytest
import yaml
from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
import config

BACKEND = ROOT / 'deploy/ansible'
spec = importlib.util.spec_from_file_location('instance_guard', BACKEND / 'scripts/verify_instance_identity.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def inputs():
    public = config.load(ROOT / 'deploy/example.json', ROOT)
    public['environment']['instance'] = {'reviewerPort': 18787, 'publicationEnabled': False}
    return public


def render(public, filename):
    config.validate(public, ROOT)
    values = {**yaml.safe_load((BACKEND / 'group_vars/all.yml').read_text()),
              **config.compile_inputs(public), 'relay_release_commit': 'a' * 40,
              'relay_release_sha256': 'b' * 64}
    return Templar(loader=DataLoader(), variables=values).template(
        (BACKEND / filename).read_text(), convert_data=False)


def test_legacy_identities_and_isolated_rendered_units_do_not_overlap():
    legacy = config.load(ROOT / 'deploy/example.json', ROOT)
    isolated = inputs()
    template = 'roles/relay_runtime/templates/'
    legacy_recovery = render(legacy, template + 'reviewer-mcp-recovery.timer.j2')
    isolated_recovery = render(isolated, template + 'reviewer-mcp-recovery.timer.j2')
    assert 'Unit=reviewer-mcp-recovery.service' in legacy_recovery
    assert 'Unit=codex-relay-reviewer-recovery.service' in isolated_recovery
    assert 'REVIEWER_RELAY_ENABLED=true' in render(legacy, template + 'relay.env.j2')
    assert 'REVIEWER_RELAY_ENABLED=false' in render(isolated, template + 'relay.env.j2')
    reviewer = json.loads(render(isolated, template + 'reviewer-mcp.json.j2'))
    assert reviewer['service']['bind_port'] == 18787
    assert reviewer['repository'] == isolated['consumer']['repository']
    assert reviewer['owner'] == isolated['consumer']['owner']
    assert 'mutation' not in reviewer
    for name in ['relay-reviewer-readiness.j2', 'relay-reviewer-recovery.j2',
                 'relay-runner-enable-start.j2', 'relay-production-operation-stale-disposition.j2']:
        helper = render(isolated, template + name)
        assert '127.0.0.1:18787' in helper
        assert 'reviewer-mcp.service' not in helper
        assert "runner_service='relay-runner.service'" not in helper


@pytest.mark.parametrize('change', [
    {'reviewerPort': True}, {'reviewerPort': 443}, {'reviewerPort': 65536},
    {'reviewerPort': '18787'}, {'publicationEnabled': 'false'}, {'serviceName': 'foreign.service'},
])
def test_invalid_instance_options_fail_before_backend(change):
    public = inputs()
    public['environment']['instance'].update(change)
    with pytest.raises(config.InvalidConfig):
        config.validate(public, ROOT)


def test_isolated_consumer_cannot_point_privileged_paths_at_another_namespace():
    public = inputs()
    public['consumer']['paths']['credentialEnv'] = '/etc/other-relay/writer-credentials/github-app.env'
    with pytest.raises(config.InvalidConfig, match='instance.paths'):
        config.validate(public, ROOT)


def test_existing_foreign_unit_is_rejected_without_changing_it(tmp_path):
    units = tmp_path / 'units'
    units.mkdir()
    unit = units / 'reviewer-mcp.service'
    content = 'ExecStart=/opt/first/current/bin/reviewer-mcp-http --config /etc/first/reviewer-mcp.json\n'
    unit.write_text(content)
    with pytest.raises(ValueError, match='UNIT_COLLISION'):
        guard.verify('/opt/second', str(tmp_path / 'second'), 'example/second', [unit.name], units)
    assert unit.read_text() == content
    guard.verify('/opt/first', str(tmp_path / 'first'), 'example/first', [unit.name], units)
    guard.verify('/opt/second', str(tmp_path / 'second'), 'example/second', ['second-reviewer.service'], units)


def shared_pool_fixture(tmp_path):
    from test_managed_pool import inputs as managed_inputs
    public = managed_inputs(1)
    values = {**yaml.safe_load((BACKEND / 'group_vars/all.yml').read_text()),
              **config.compile_inputs(public), 'playbook_dir': str(BACKEND),
              'relay_config_root': str(tmp_path / 'config')}
    pool = values['relay_general_runner_pool']
    member = pool['members'][0]
    content = Templar(loader=DataLoader(), variables={**values, 'relay_pool_member': member}).template(
        (BACKEND / 'roles/relay_runner/templates/relay-managed-pool.service.j2').read_text(), convert_data=False)
    unit = tmp_path / member['service']
    unit.write_text(content)
    proof = {'name': pool['name'], 'runnerUser': pool['runnerUser'],
             'root': member['root'], 'service': member['service']}
    return public, values, unit, content, proof


def test_compiled_pool_preflight_accepts_actual_shared_unit_without_a_legacy_allowlist(tmp_path):
    public, values, unit, content, expected_proof = shared_pool_fixture(tmp_path)
    legacy = tmp_path / (public['environment']['namespace'] + '-general-runner.service')
    legacy_content = 'ExecStart=' + values['relay_install_root'] + '/general-runner/run.sh\n'
    legacy.write_text(legacy_content)
    task = yaml.safe_load((BACKEND / 'roles/relay_preflight/tasks/main.yml').read_text())[0]
    argv = Templar(loader=DataLoader(), variables=values).template(task['ansible.builtin.command']['argv'])
    arguments = argv[7:]
    # On the old task no proof is passed, reproducing its exact namespace-prefix
    # collision against the real shared pool unit format before the fix.
    arguments, proof = guard.parse_pool_argument(arguments) if '--general-pool' in arguments else (arguments, None)
    kwargs = {'general_pool': proof} if proof is not None else {}
    guard.verify(argv[3], argv[4], json.loads(argv[5]), arguments, tmp_path,
                 reviewer_user=argv[6], **kwargs)
    assert proof == expected_proof
    assert legacy.name not in arguments
    assert unit.read_text() == content and legacy.read_text() == legacy_content


@pytest.mark.parametrize('field', ['User', 'Group', 'WorkingDirectory', 'ExecStart'])
def test_shared_pool_identity_rejects_foreign_or_duplicate_service_directives(tmp_path, field):
    public, values, unit, content, proof = shared_pool_fixture(tmp_path)
    identity_line = next(row for row in content.splitlines() if row.startswith(field + '='))
    for changed in [
        re.sub(r'(?m)^' + field + r'=.*$', field + '=foreign', content),
        content.replace('[Service]\n', '[Service]\n' + identity_line + '\n'),
        content.replace(identity_line + '\n', identity_line + '\n' + field + ' = foreign\n'),
    ]:
        unit.write_text(changed)
        with pytest.raises(ValueError, match='UNIT_COLLISION'):
            guard.verify(values['relay_install_root'], str(tmp_path / 'config'),
                         public['consumer']['repository'], [unit.name], tmp_path, general_pool=proof)
        assert unit.read_text() == changed


@pytest.mark.parametrize('changes', [
    {'name': '../foreign'}, {'runnerUser': 'root'}, {'runnerUser': 'foreign user'},
    {'root': '/opt/foreign/runners/primary'}, {'service': 'foreign.service'}, {'extra': 'foreign.service'},
])
def test_shared_pool_proof_cannot_allow_arbitrary_units_paths_or_users(tmp_path, changes):
    public, values, unit, content, proof = shared_pool_fixture(tmp_path)
    with pytest.raises(ValueError, match='POOL_BINDING_INVALID'):
        guard.verify(values['relay_install_root'], str(tmp_path / 'config'),
                     public['consumer']['repository'], [unit.name], tmp_path, general_pool={**proof, **changes})
    assert unit.read_text() == content


def test_shared_pool_proof_preserves_symlink_and_other_unit_rejection(tmp_path):
    public, values, unit, content, proof = shared_pool_fixture(tmp_path)
    args = (values['relay_install_root'], str(tmp_path / 'config'), public['consumer']['repository'])
    with pytest.raises(ValueError, match='UNIT_COLLISION'):
        guard.verify(*args, [unit.name], tmp_path)
    with pytest.raises(ValueError, match='POOL_BINDING_INVALID'):
        guard.verify(*args, [], tmp_path, general_pool=proof)
    foreign = tmp_path / 'foreign.service'
    foreign.write_text(content)
    with pytest.raises(ValueError, match='UNIT_COLLISION'):
        guard.verify(*args, [unit.name, foreign.name], tmp_path, general_pool=proof)
    unit.unlink()
    unit.symlink_to(foreign)
    with pytest.raises(ValueError, match='UNIT_UNSAFE'):
        guard.verify(*args, [unit.name], tmp_path, general_pool=proof)
    assert foreign.read_text() == content


@pytest.mark.parametrize('arguments', [
    ['--general-pool'], ['--general-pool', '{}', 'foreign.service'],
    ['--general-pool', '{}', '--general-pool', '{}'], ['--general-pool', 'invalid-json'],
])
def test_general_pool_argument_requires_one_complete_trailing_value(arguments):
    with pytest.raises(ValueError):
        guard.parse_pool_argument(arguments)


def test_general_pool_argument_preserves_legacy_invocation():
    names = ['legacy-reviewer.service', 'legacy-runner.service']
    assert guard.parse_pool_argument(names) == (names, None)
    assert guard.parse_pool_argument([*names, '--general-pool', 'null']) == (names, None)


def test_manual_outcome_units_bind_the_same_namespace_and_fixed_writer(tmp_path):
    socket = tmp_path / 'first-relay-manual-outcome.socket'
    template = tmp_path / 'first-relay-manual-outcome@.service'
    socket.write_text('ListenStream=/run/first-manual-outcome.sock\nAccept=yes\n')
    template.write_text('ExecStart=/opt/first/relay-manual-outcome-writer\nUser=root\n')
    names = [socket.name, template.name]
    guard.verify('/opt/first', str(tmp_path / 'config'), 'example/first', names, tmp_path)
    with pytest.raises(ValueError, match='UNIT_COLLISION'):
        guard.verify('/opt/other', str(tmp_path / 'config'), 'example/first', names, tmp_path)
    template.write_text('ExecStart=/opt/first/foreign-program\nUser=root\n')
    with pytest.raises(ValueError, match='UNIT_COLLISION'):
        guard.verify('/opt/first', str(tmp_path / 'config'), 'example/first', names, tmp_path)


def test_renamed_socket_cannot_hide_the_existing_namespace(tmp_path):
    (tmp_path / 'foreign.socket').write_text('ListenStream=/run/first-manual-outcome.sock\nAccept=yes\n')
    with pytest.raises(ValueError, match='UNIT_COLLISION'):
        guard.verify('/opt/first', str(tmp_path / 'config'), 'example/first',
                     ['first-relay-manual-outcome.socket'], tmp_path)


def test_same_namespace_cannot_repoint_repository(tmp_path):
    installed = tmp_path / 'reviewer-mcp.json'
    installed.write_text(json.dumps({'repository': 'example/first'}))
    with pytest.raises(ValueError, match='REPOSITORY_COLLISION'):
        guard.verify('/opt/first', str(tmp_path), 'example/second', [], tmp_path)
    assert json.loads(installed.read_text())['repository'] == 'example/first'


def test_unit_symlink_is_rejected(tmp_path):
    target = tmp_path / 'target'
    target.write_text('ExecStart=/opt/first/current/bin/reviewer-mcp-http\n')
    (tmp_path / 'first.service').symlink_to(target)
    with pytest.raises(ValueError, match='UNIT_UNSAFE'):
        guard.verify('/opt/first', str(tmp_path / 'config'), 'example/first', ['first.service'], tmp_path)


@pytest.mark.parametrize('root,user', [('/opt/first', 'second-reviewer'), ('/opt/second', 'first-reviewer')])
def test_implicit_unit_migration_and_shared_reviewer_account_are_rejected(tmp_path, root, user):
    (tmp_path / 'reviewer-mcp.service').write_text(
        'User=first-reviewer\nExecStart=/opt/first/current/bin/reviewer-mcp-http --config /etc/first/reviewer-mcp.json\n')
    with pytest.raises(ValueError, match='REVIEWER_IDENTITY_COLLISION'):
        guard.verify(root, str(tmp_path / 'config'), 'example/second', ['second-reviewer.service'],
                     tmp_path, reviewer_user=user)


@pytest.mark.skipif(sys.platform != 'linux' or not shutil.which('ansible-playbook'),
                    reason='Linux localhost Ansible required')
@pytest.mark.parametrize('installed_repository', ['example/first', 'example/second'])
def test_actual_first_preflight_task_binds_the_installed_repository(tmp_path, installed_repository):
    (tmp_path / 'scripts').mkdir()
    shutil.copyfile(BACKEND / 'scripts/verify_instance_identity.py',
                    tmp_path / 'scripts/verify_instance_identity.py')
    config_root = tmp_path / 'config'
    config_root.mkdir()
    (config_root / 'reviewer-mcp.json').write_text(json.dumps({'repository': installed_repository}))
    fixture = 'fixture-' + uuid.uuid4().hex[:12]
    values = {**yaml.safe_load((BACKEND / 'group_vars/all.yml').read_text()),
              **config.compile_inputs(inputs()), 'relay_github_repository': 'example/first',
              'relay_reviewer_repositories': ['example/first'],
              'relay_config_root': str(config_root), 'relay_install_root': str(tmp_path / 'install'),
              'relay_reviewer_user': fixture}
    for key in list(values):
        if key.endswith('_service_name') or key == 'relay_reviewer_recovery_timer_name':
            values[key] = fixture + '-' + values[key]
    task = yaml.safe_load((BACKEND / 'roles/relay_preflight/tasks/main.yml').read_text())[0]
    playbook = tmp_path / 'preflight.yml'
    playbook.write_text(yaml.safe_dump([{'hosts': 'localhost', 'gather_facts': False,
                                        'vars': values, 'tasks': [task]}]))
    result = subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local',
                             '--check', str(playbook)], cwd=tmp_path,
                            env={**os.environ, 'ANSIBLE_NOCOLOR': '1'}, capture_output=True, text=True)
    assert (result.returncode == 0) == (installed_repository == 'example/first'), result.stdout + result.stderr
    assert json.loads((config_root / 'reviewer-mcp.json').read_text())['repository'] == installed_repository


@pytest.mark.skipif(sys.platform != 'linux', reason='Linux lifecycle helper required')
@pytest.mark.parametrize('listener,healthy', [('127.0.0.1:1878', True),
                                           ('127.0.0.1:18787', False),
                                           ('127.0.0.2:1878', False)])
def test_readiness_cannot_accept_another_instances_similar_socket(tmp_path, listener, healthy):
    public = inputs()
    public['environment']['instance']['reviewerPort'] = 1878
    values = {**yaml.safe_load((BACKEND / 'group_vars/all.yml').read_text()),
              **config.compile_inputs(public), 'relay_production_operation_state_path': '/bin/true',
              'relay_reviewer_activation_marker': str(tmp_path / 'activation'),
              'relay_reviewer_recovery_off_marker': str(tmp_path / 'off')}
    (tmp_path / 'activation').write_text('authorized\n')
    binaries = tmp_path / 'bin'
    binaries.mkdir()
    for name, output in [('ss', f'LISTEN 0 128 {listener} 0.0.0.0:*'),
                         ('stat', 'root 600'), ('systemctl', 'active')]:
        executable = binaries / name
        executable.write_text('#!/bin/sh\nprintf \'%s\\n\' \'' + output + '\'\n')
        executable.chmod(0o755)
    source = (BACKEND / 'roles/relay_runtime/templates/relay-reviewer-readiness.j2').read_text()
    rendered = Templar(loader=DataLoader(), variables=values).template(source, convert_data=False)
    rendered = rendered.replace('/bin/systemctl', str(binaries / 'systemctl'))
    rendered = rendered.replace('/usr/bin/stat', str(binaries / 'stat'))
    script = tmp_path / 'readiness'
    script.write_text(rendered)
    result = subprocess.run(['bash', str(script)], capture_output=True, text=True,
                            env={**os.environ, 'PATH': str(binaries) + ':' + os.environ['PATH']})
    assert (result.returncode == 0) == healthy, result.stdout + result.stderr


@pytest.mark.skipif(sys.platform != 'linux', reason='Linux activation helper required')
@pytest.mark.parametrize('installed', ['absent', 'valid', 'partial', 'foreign', 'symlink', 'bad-readback'])
def test_existing_authorized_activate_handles_manual_socket_without_new_config(tmp_path, installed):
    calls = tmp_path / 'systemctl-calls'
    systemctl = tmp_path / 'systemctl'
    systemctl.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> ' + str(calls) + '\n'
                        'case "$1" in\n is-active) echo active;;\n'
                        ' is-enabled) echo ' + ('disabled' if installed == 'bad-readback' else 'enabled') + ';;\nesac\n')
    systemctl.chmod(0o755)
    stat = tmp_path / 'stat'
    stat.write_text('#!/bin/sh\necho "root root 644"\n')
    stat.chmod(0o755)
    operation = tmp_path / 'operation-state'
    operation.write_text('#!/bin/sh\necho phase=activate\nexit 10\n')
    operation.chmod(0o755)
    units = tmp_path / 'units'
    units.mkdir()
    values = {**yaml.safe_load((BACKEND / 'group_vars/all.yml').read_text()),
              **config.compile_inputs(inputs()), 'relay_production_operation_state_path': str(operation),
              'relay_production_operation_lock_path': str(tmp_path / 'operation.lock')}
    socket = values['relay_namespace'] + '-relay-manual-outcome.socket'
    template = values['relay_namespace'] + '-relay-manual-outcome@.service'
    if installed != 'absent':
        (units / socket).write_text('ListenStream=/run/' + values['relay_namespace'] + '-manual-outcome.sock\n'
                                   'Accept=yes\nSocketUser=root\nSocketGroup=' + values['relay_reviewer_group'] + '\nSocketMode=0660\n')
        if installed != 'partial':
            (units / template).write_text('ExecStart=' + values['relay_install_root'] + '/relay-manual-outcome-writer\nUser=root\n')
        if installed == 'foreign':
            (units / template).write_text('ExecStart=/opt/foreign/writer\nUser=root\n')
        elif installed == 'symlink':
            (units / socket).rename(units / 'socket-target')
            (units / socket).symlink_to(units / 'socket-target')
    source = (BACKEND / 'roles/relay_runtime/templates/relay-reviewer-activation-start.j2').read_text()
    rendered = Templar(loader=DataLoader(), variables=values).template(source, convert_data=False)
    rendered = rendered.replace('/etc/systemd/system/', str(units) + '/')
    rendered = rendered.replace('/bin/systemctl', str(systemctl)).replace('/usr/bin/stat', str(stat))
    helper = tmp_path / 'activate'
    helper.write_text(rendered)
    result = subprocess.run(['bash', str(helper)], capture_output=True, text=True)
    observed = calls.read_text().splitlines()
    assert (result.returncode == 0) == (installed in ['absent', 'valid']), result.stdout + result.stderr
    reviewer = values['relay_reviewer_service_name']
    if installed == 'absent':
        assert observed == ['daemon-reload', 'enable ' + reviewer, 'start ' + reviewer]
    elif installed in ['valid', 'bad-readback']:
        assert observed[:5] == ['daemon-reload', 'enable ' + socket, 'start ' + socket,
                               'is-active ' + socket, 'is-enabled ' + socket]
        assert observed[5:] == (['enable ' + reviewer, 'start ' + reviewer] if installed == 'valid' else [])
    else:
        assert observed == ['daemon-reload']
