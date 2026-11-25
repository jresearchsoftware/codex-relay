"""Real local callback fixtures without installed service authority."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'deploy'))
from timing import public_ansible_timing

OP = '12345678-1234-1234-1234-123456789abc'
INV = '12345678-1234-1234-1234-123456789def'
PREFIX = f'RELAY_ANSIBLE_TIMING=operation={OP};invocation={INV};'


def test_privacy_overlap_and_partial_failure(monkeypatch):
    monkeypatch.setenv('RELAY_TIMING_OPERATION', OP)
    monkeypatch.setenv('RELAY_TIMING_INVOCATION', INV)
    spec = importlib.util.spec_from_file_location('relay_timing', ROOT / 'deploy/ansible/callback_plugins/relay_timing.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    value = module.CallbackModule()
    lines = []
    value.emit = lambda fields: lines.append(PREFIX + fields)
    host = SimpleNamespace(get_name=lambda: 'private-host')
    source = ROOT / 'deploy/ansible/roles/relay_runtime/tasks/main.yml'
    task = SimpleNamespace(_uuid='task-1', no_log=False, get_path=lambda: str(source) + ':1')
    assert value.identity(task, False)[1] == 'relay_runtime'
    clock = iter([10, 20, 30, 50, 80])
    value.now = lambda: next(clock)
    value.v2_runner_on_start(host, task)
    second = SimpleNamespace(_uuid='task-2', no_log=True, get_path=lambda: '/private/secret:10')
    value.v2_runner_on_start(host, second)
    value.v2_runner_on_failed(SimpleNamespace(_host=host, _task=task, _result={'stdout': 'private-secret'}))
    assert 'state=failed' in lines[0]  # Flushes before stats, including partial failures.
    value.v2_runner_on_ok(SimpleNamespace(_host=host, _task=second, _result={'_ansible_no_log': True}))
    value.v2_playbook_on_stats(None)
    assert 'task=redacted;role=redacted' in lines[1]
    assert 'observed_union_ms=40;gap_ms=40' in lines[-1]
    assert all(public_ansible_timing(line, OP) for line in lines)
    assert not any('private' in line or str(ROOT) in line for line in lines)


@pytest.mark.parametrize('suffix', [';secret=value', '\nsecret', ';role=private', ' '])
def test_grammar_rejects_extra_data(suffix):
    line = PREFIX + 'kind=backend;wall_ms=123'
    assert public_ansible_timing(line)
    assert not public_ansible_timing(line + suffix)
    assert not public_ansible_timing(line, INV)


@pytest.mark.skipif(not shutil.which('ansible-playbook'), reason='Ansible required')
@pytest.mark.parametrize('failed', [False, True])
def test_real_callback_preserves_execution(tmp_path, failed):
    (tmp_path / 'included.yml').write_text('- ansible.builtin.debug:\n    msg: included\n')
    play = tmp_path / 'play.yml'
    play.write_text('''- hosts: localhost
  gather_facts: false
  tasks:
    - name: Normal fixture
      ansible.builtin.debug:
        msg: normal
      changed_when: true
      notify: Fixture handler
    - name: Skipped fixture
      ansible.builtin.debug:
        msg: skipped
      when: false
    - name: Loop fixture
      ansible.builtin.debug:
        msg: "{{ item }}"
      loop: [one, two]
    - name: Retry fixture
      ansible.builtin.debug:
        msg: retry
      until: false
      retries: 1
      delay: 0
      ignore_errors: true
    - name: Included fixture
      ansible.builtin.include_tasks: included.yml
    - name: Private fixture
      ansible.builtin.debug:
        msg: private-secret-payload
      no_log: true
    - name: Run handlers
      ansible.builtin.meta: flush_handlers
''' + ('''    - name: Failure fixture
      ansible.builtin.fail:
        msg: expected-failure
''' if failed else '') + '''  handlers:
    - name: Fixture handler
      ansible.builtin.debug:
        msg: handler
''')
    env = dict(os.environ, ANSIBLE_NOCOLOR='1', ANSIBLE_LOCAL_TEMP=str(tmp_path / 'local'),
               ANSIBLE_REMOTE_TEMP=str(tmp_path / 'remote'), ANSIBLE_CONFIG=str(ROOT / 'deploy/ansible/ansible.cfg'),
               RELAY_TIMING_OPERATION=OP, RELAY_TIMING_INVOCATION=INV,
               ANSIBLE_CALLBACK_PLUGINS=str(ROOT / 'deploy/ansible/callback_plugins'))
    argv = ['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(play)]
    baseline = subprocess.run(argv, env=dict(env, ANSIBLE_CALLBACKS_ENABLED=''), capture_output=True, text=True)
    timed = subprocess.run(argv, env=dict(env, ANSIBLE_CALLBACKS_ENABLED='relay_timing'), capture_output=True, text=True)
    assert baseline.returncode == timed.returncode == (2 if failed else 0)
    records = [line for line in timed.stdout.splitlines() if line.startswith('RELAY_ANSIBLE_TIMING=')]
    assert records and all(public_ansible_timing(line, OP) for line in records)
    assert any('state=skipped' in line for line in records)
    assert any('task=redacted;role=redacted' in line for line in records)
    assert any('kind=summary;' in line and 'unfinished=0;' in line for line in records)
    if failed:
        assert any('state=failed' in line for line in records)
    assert 'private-secret-payload' not in timed.stdout + timed.stderr
    without = '\n'.join(line for line in timed.stdout.splitlines() if not line.startswith('RELAY_ANSIBLE_TIMING='))
    assert without.strip() == baseline.stdout.strip()


def test_backend_forwards_only_its_correlated_bounded_records(tmp_path, capsys):
    spec = importlib.util.spec_from_file_location('timing_deploy', ROOT / 'deploy/relay-deploy.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    program = '''import os
prefix='RELAY_ANSIBLE_TIMING=operation='+os.environ['RELAY_TIMING_OPERATION']+';invocation='+os.environ['RELAY_TIMING_INVOCATION']+';'
print(prefix+'kind=summary;wall_ms=10;observed_union_ms=6;gap_ms=4;unfinished=0;overlap=possible')
print(prefix+'kind=backend;wall_ms=1;private-secret-payload')
print('RELAY_ANSIBLE_TIMING=operation=12345678-1234-1234-1234-123456789def;invocation=12345678-1234-1234-1234-123456789def;kind=backend;wall_ms=2')
raise SystemExit(7)
'''
    log_path = tmp_path / 'backend.log'
    with log_path.open('w') as log:
        assert module.run_backend([sys.executable, '-c', program], ROOT,
            dict(os.environ, RELAY_TIMING_OPERATION=OP), log) == 7
    output = capsys.readouterr().out
    assert 'kind=summary;wall_ms=10' in output
    assert 'private-secret-payload' not in output
    assert f'operation={INV};' not in output
    assert 'private-secret-payload' in log_path.read_text()


def test_backend_forwards_summary_beyond_the_final_read_chunk(tmp_path, capsys, monkeypatch):
    spec = importlib.util.spec_from_file_location('timing_deploy_tail', ROOT / 'deploy/relay-deploy.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    popen = subprocess.Popen

    def completed_backend(*args, **kwargs):
        process = popen(*args, **kwargs)
        process.wait(timeout=10)
        return process

    # Model a backend that writes a large final burst and exits between
    # samples, without depending on the observer's polling schedule.
    monkeypatch.setattr(module.subprocess, 'Popen', completed_backend)
    program = '''import os
prefix='RELAY_ANSIBLE_TIMING=operation='+os.environ['RELAY_TIMING_OPERATION']+';invocation='+os.environ['RELAY_TIMING_INVOCATION']+';'
for _ in range(2048):
    print('private-backend-payload' * 32)
print(prefix+'kind=summary;wall_ms=50;observed_union_ms=31;gap_ms=19;unfinished=0;overlap=possible')
'''
    log_path = tmp_path / 'backend.log'
    with log_path.open('w') as log:
        assert module.run_backend([sys.executable, '-c', program], ROOT,
            dict(os.environ, RELAY_TIMING_OPERATION=OP), log) == 0
    output = capsys.readouterr().out
    assert output.count('kind=summary;wall_ms=50') == 1
    assert output.index('kind=summary;') < output.index('kind=backend;')
    assert 'private-backend-payload' not in output
    assert 'private-backend-payload' in log_path.read_text()
