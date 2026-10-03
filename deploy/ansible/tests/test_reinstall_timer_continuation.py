"""Native Ansible evaluation of the real reinstall timer continuation gate.

The systemd action is replaced by a constrained local command that records its
rendered options. This proves conditional routing, not live systemd behavior.
The rendered recovery helper is also exercised without host service access.
Native systemd-analyze checks the independently anchored timer configuration;
it does not prove scheduling. Two actual callbacks remain a live qualification.
"""
import configparser
import copy
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

import pytest
import yaml
from jinja2 import Environment, StrictUndefined

pytestmark = pytest.mark.skipif(os.name == 'nt', reason='native Linux qualification required')

ANSIBLE = Path(__file__).resolve().parents[1]
TEMPLATES = ANSIBLE / 'roles/relay_runtime/templates'
HEAD = 'a' * 40
DIGEST = 'b' * 64
TIMER = 'synthetic-reviewer-recovery.timer'


@pytest.mark.skipif(not shutil.which('ansible-playbook'), reason='native Ansible required')
@pytest.mark.parametrize('variables,check_mode,starts', [
    ({}, False, True),
    ({'relay_production_operation_recovery_required': True,
      'relay_production_operation_recovery_matching': True,
      'relay_clean_reinstall_journal_sha256': DIGEST}, False, True),
    ({'relay_production_operation_recovery_required': True}, False, False),
    ({'relay_production_operation_recovery_required': True,
      'relay_production_operation_recovery_matching': False,
      'relay_clean_reinstall_journal_sha256': DIGEST}, False, False),
    ({'relay_production_operation_recovery_required': True,
      'relay_production_operation_recovery_matching': True}, False, False),
    ({'relay_production_operation_recovery_required': True,
      'relay_production_operation_recovery_matching': True,
      'relay_clean_reinstall_journal_sha256': 'B' * 64}, False, False),
    ({'relay_production_operation_recovery_required': True,
      'relay_production_operation_recovery_matching': True,
      'relay_clean_reinstall_journal_sha256': 'b' * 63}, False, False),
    ({'relay_production_operation_recovery_required': True,
      'relay_production_operation_recovery_matching': True,
      'relay_clean_reinstall_journal_sha256': 'z' * 64}, False, False),
    ({'relay_production_operation_recovery_required': True,
      'relay_production_operation_recovery_matching': True,
      'relay_clean_reinstall_journal_sha256': DIGEST + '\n'}, False, False),
    ({'relay_production_operation_recovery_required': True,
      'relay_production_operation_recovery_matching': True,
      'relay_clean_reinstall_journal_sha256': DIGEST,
      'relay_production_operation_phase': 'activate'}, False, False),
    ({'relay_production_operation_recovery_required': True,
      'relay_production_operation_recovery_matching': True,
      'relay_clean_reinstall_journal_sha256': DIGEST,
      'relay_production_operation_phase': 'runner-enable'}, False, False),
    ({'relay_production_operation_recovery_required': True,
      'relay_production_operation_recovery_matching': True,
      'relay_clean_reinstall_journal_sha256': DIGEST,
      'relay_production_operation_phase': 'post-check'}, False, False),
    ({'relay_deployment_profile': 'development'}, False, False),
    ({}, True, False),
    ({'relay_production_operation_recovery_required': True,
      'relay_production_operation_recovery_matching': True,
      'relay_clean_reinstall_journal_sha256': DIGEST}, True, False),
])
def test_real_timer_task_only_starts_at_admitted_boundary(tmp_path, variables, check_mode, starts):
    tasks = yaml.safe_load((ANSIBLE / 'roles/relay_runtime/tasks/main.yml').read_text())
    task = copy.deepcopy(next(value for value in tasks if value.get('name') ==
                              'Keep the Reviewer recovery timer available without activating Reviewer'))
    options = task.pop('ansible.builtin.systemd')
    sentinel = tmp_path / 'timer-options.json'
    standin = tmp_path / 'systemd-standin.py'
    standin.write_text('import json, pathlib, sys\n'
                       'value = json.load(sys.stdin)\n'
                       'assert value == {"name": "synthetic-reviewer-recovery.timer", '
                       '"enabled": True, "state": "started", "daemon_reload": True}\n'
                       'pathlib.Path(sys.argv[1]).write_text(json.dumps(value, sort_keys=True))\n')
    task['ansible.builtin.command'] = {
        'argv': [sys.executable, str(standin), str(sentinel)],
        'stdin': '{{ fixture_timer_options | to_json }}'}
    # Command's own default check-mode skip must not conceal a broken source
    # condition. The original `when` still sees Ansible's play check mode.
    task['check_mode'] = False
    settings = {'ansible_connection': 'local', 'ansible_python_interpreter': sys.executable,
                'relay_deployment_profile': 'production', 'relay_production_operation_phase': 'apply',
                'relay_reviewer_recovery_timer_name': TIMER, 'fixture_timer_options': options,
                **variables}
    playbook = tmp_path / 'timer.yml'
    playbook.write_text(yaml.safe_dump([{'hosts': 'localhost', 'gather_facts': False,
                                       'vars': settings, 'tasks': [task]}]))
    command = ['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(playbook)]
    if check_mode:
        command.append('--check')
    result = subprocess.run(command, capture_output=True, text=True, timeout=60,
                            env={**os.environ, 'ANSIBLE_NOCOLOR': '1',
                                 'ANSIBLE_CONFIG': str(ANSIBLE / 'ansible.cfg')})
    assert result.returncode == 0, result.stdout + result.stderr
    assert sentinel.exists() is starts, result.stdout + result.stderr
    if starts:
        assert json.loads(sentinel.read_text())['name'] == TIMER


@pytest.mark.skipif(os.name == 'nt', reason='native Bash helper required')
def test_pending_apply_timer_callback_cannot_start_any_service(tmp_path):
    import grp
    import pwd

    record = tmp_path / 'operation.json'
    record.write_text(json.dumps({'schemaVersion': '1', 'state': 'RECOVERY_REQUIRED',
                                 'phase': 'apply', 'target_head': HEAD}))
    record.chmod(0o600)
    marker = tmp_path / 'activation-authorized'
    marker.write_text('authorized\n')
    marker.chmod(0o600)
    systemctl_calls = tmp_path / 'systemctl-calls'
    systemctl = tmp_path / 'systemctl'
    systemctl.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> ' + str(systemctl_calls)
                         + '\nexit 99\n')
    systemctl.chmod(0o700)
    variables = {'relay_production_operation_record_path': str(record),
                 'relay_production_operation_schema_version': '1',
                 'relay_reviewer_service_name': 'synthetic-reviewer.service',
                 'relay_reviewer_activation_marker': str(marker),
                 'relay_reviewer_recovery_off_marker': str(tmp_path / 'recovery-off'),
                 'relay_reviewer_bind_address': '127.0.0.1', 'relay_reviewer_bind_port': 12345,
                 'relay_deployment_profile': 'production',
                 'relay_production_runner_service_name': 'synthetic-runner.service',
                 'relay_runner_registration_marker': str(tmp_path / 'registration'),
                 'relay_runner_credentials_marker': str(tmp_path / 'credentials')}
    environment = Environment(undefined=StrictUndefined)
    verifier = tmp_path / 'operation-state'
    state_source = environment.from_string(
        (TEMPLATES / 'relay-production-operation-state.j2').read_text()).render(**variables)
    # Map only the root owner/group admission to this isolated fixture's owner;
    # the real record mode, JSON schema, phase/head and helper handling remain.
    owner = pwd.getpwuid(record.stat().st_uid).pw_name
    group = grp.getgrgid(record.stat().st_gid).gr_name
    state_source = state_source.replace('"$owner" != root', '"$owner" != ' + shlex.quote(owner))
    state_source = state_source.replace('"$group" != root', '"$group" != ' + shlex.quote(group))
    verifier.write_text(state_source)
    verifier.chmod(0o700)
    variables['relay_production_operation_state_path'] = str(verifier)
    helper = tmp_path / 'recovery'
    source = environment.from_string((TEMPLATES / 'relay-reviewer-recovery.j2').read_text()).render(**variables)
    helper.write_text(source.replace('/bin/systemctl', str(systemctl)))
    before = record.read_bytes(), marker.read_bytes()
    result = subprocess.run(['/bin/bash', str(helper)], capture_output=True, text=True, timeout=10)
    assert result.returncode == 30, result.stdout + result.stderr
    assert ('REVIEWER_RECOVERY_BLOCKED=RECOVERY_REQUIRED phase=apply target_head=' + HEAD
            in result.stdout + result.stderr)
    assert not systemctl_calls.exists()
    assert (record.read_bytes(), marker.read_bytes()) == before


@pytest.mark.skipif(not shutil.which('systemd-analyze'), reason='native systemd analyzer required')
@pytest.mark.parametrize('interval', ['7s', '2min 15s'])
def test_rendered_timer_has_independent_start_anchor_and_valid_fixed_unit(tmp_path, interval):
    service_name = TIMER.removesuffix('.timer') + '.service'
    timer = tmp_path / TIMER
    timer.write_text(Environment(undefined=StrictUndefined).from_string(
        (TEMPLATES / 'reviewer-mcp-recovery.timer.j2').read_text()).render(
            relay_reviewer_recovery_interval=interval,
            relay_reviewer_recovery_service_name=service_name))
    settings = configparser.ConfigParser(interpolation=None)
    settings.optionxform = str
    settings.read_string(timer.read_text())
    # OnActiveSec supplies the first future deadline even after the boot
    # deadline elapsed and the triggered service lost activation timestamps.
    assert settings['Timer']['OnActiveSec'] == interval
    assert settings['Timer']['OnBootSec'] == interval
    assert settings['Timer']['OnUnitActiveSec'] == interval
    assert settings['Timer']['Unit'] == service_name
    service = tmp_path / service_name
    service.write_text('[Unit]\nDescription=Non-executed timer configuration fixture\n'
                       '[Service]\nType=oneshot\nExecStart=/bin/true\n')
    runtime = tmp_path / 'analyzer-runtime'
    runtime.mkdir(mode=0o700)
    # User-mode offline analysis keeps runtime scratch state within this owned
    # fixture; it parses the same timer options without requiring host /run.
    result = subprocess.run(['systemd-analyze', '--user', 'verify', str(timer), str(service)],
                            capture_output=True, text=True, timeout=20,
                            env={**os.environ, 'SYSTEMD_LOG_COLOR': '0',
                                 'XDG_RUNTIME_DIR': str(runtime)})
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(not shutil.which('ansible-playbook'), reason='native Ansible required')
@pytest.mark.parametrize('active,enabled,schedule,show_rc,passes', [
    pytest.param('active', 'enabled', 'SubState=waiting\nNextElapseUSecMonotonic=1h 42min',
                 0, True, id='waiting-finite-deadline'),
    pytest.param('active', 'enabled', 'SubState=running\nNextElapseUSecMonotonic=infinity',
                 0, True, id='running-callback-pending'),
    pytest.param('active', 'enabled', 'SubState=elapsed\nNextElapseUSecMonotonic=infinity',
                 0, False, id='elapsed-inert-timer'),
    pytest.param('active', 'enabled', 'SubState=waiting\nNextElapseUSecMonotonic=infinity',
                 0, False, id='waiting-without-deadline'),
    pytest.param('active', 'enabled', 'SubState=waiting\nNextElapseUSecMonotonic=0',
                 0, False, id='waiting-zero-deadline'),
    pytest.param('active', 'enabled', 'SubState=unexpected\nNextElapseUSecMonotonic=123456789',
                 0, False, id='unknown-timer-substate'),
    pytest.param('active', 'enabled', 'SubState=waiting', 0, False, id='missing-deadline'),
    pytest.param('active', 'enabled', 'SubState=waiting\nNextElapseUSecMonotonic=123456789',
                 1, False, id='property-observation-failed'),
    pytest.param('inactive', 'disabled', 'SubState=dead\nNextElapseUSecMonotonic=infinity',
                 0, False, id='inactive-disabled'),
    pytest.param('active', 'disabled', 'SubState=waiting\nNextElapseUSecMonotonic=123456789',
                 0, False, id='active-disabled'),
    pytest.param('inactive', 'enabled', 'SubState=dead\nNextElapseUSecMonotonic=infinity',
                 0, False, id='inactive-enabled'),
])
def test_real_post_check_observes_timer_without_mutating_it(tmp_path, active, enabled, schedule, show_rc, passes):
    source = yaml.safe_load((ANSIBLE / 'site.yml').read_text())
    task_names = ['Inspect the recovery timer during production post-check',
                  'Inspect the next recovery timer deadline during production post-check',
                  'Require the normal recovery timer after production install']
    tasks = [copy.deepcopy(next(task for play in source for task in play.get('post_tasks', [])
                                if task.get('name') == name)) for name in task_names]
    bin_root = tmp_path / 'bin'
    bin_root.mkdir()
    calls = tmp_path / 'systemctl-calls.jsonl'
    fake = bin_root / 'systemctl'
    fake.write_text('#!' + sys.executable + '\n'
                    'import json, os, pathlib, sys\n'
                    'with pathlib.Path(os.environ["FAKE_SYSTEMCTL_CALLS"]).open("a") as stream:\n'
                    '    stream.write(json.dumps(sys.argv[1:]) + "\\n")\n'
                    'assert sys.argv[2] == "synthetic-reviewer-recovery.timer"\n'
                    'operation = sys.argv[1]\n'
                    'assert operation in ["is-active", "is-enabled", "show"], "mutating service-manager call"\n'
                    'if operation == "show":\n'
                    '    assert sys.argv[3:] == ["--property=SubState,NextElapseUSecMonotonic"]\n'
                    '    print(os.environ["FAKE_TIMER_SCHEDULE"])\n'
                    '    sys.exit(int(os.environ["FAKE_TIMER_SHOW_RC"]))\n'
                    'assert len(sys.argv) == 3\n'
                    'value = os.environ["FAKE_TIMER_ACTIVE" if operation == "is-active" else "FAKE_TIMER_ENABLED"]\n'
                    'print(value)\n'
                    'sys.exit(0 if value in ["active", "enabled"] else 3)\n')
    fake.chmod(0o700)
    fixture = tmp_path / 'post-check.yml'
    fixture.write_text(yaml.safe_dump([{
        'hosts': 'localhost', 'gather_facts': False,
        'vars': {'ansible_connection': 'local', 'ansible_python_interpreter': sys.executable,
                 'relay_deployment_profile': 'production', 'relay_production_operation_phase': 'post-check',
                 'relay_reviewer_recovery_timer_name': TIMER},
        'environment': {'PATH': str(bin_root) + ':/usr/bin:/bin',
                        'FAKE_SYSTEMCTL_CALLS': str(calls),
                        'FAKE_TIMER_ACTIVE': active, 'FAKE_TIMER_ENABLED': enabled,
                        'FAKE_TIMER_SCHEDULE': schedule, 'FAKE_TIMER_SHOW_RC': str(show_rc)},
        'tasks': tasks,
    }]))
    result = subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local',
                             '--check', str(fixture)], capture_output=True, text=True, timeout=60,
                            env={**os.environ, 'ANSIBLE_NOCOLOR': '1',
                                 'ANSIBLE_CONFIG': str(ANSIBLE / 'ansible.cfg')})
    assert (result.returncode == 0) is passes, result.stdout + result.stderr
    assert calls.exists(), result.stdout + result.stderr
    assert [json.loads(line) for line in calls.read_text().splitlines()] == [
        ['is-active', TIMER], ['is-enabled', TIMER],
        ['show', TIMER, '--property=SubState,NextElapseUSecMonotonic']]
