"""Run the actual lifecycle gates with compiled public inputs on localhost.

Only read-only task slices execute. Host service/network probes are substituted;
no registration, operation disposition or systemd mutation is performed.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / 'deploy/ansible'
pytestmark = pytest.mark.skipif(
    sys.platform != 'linux' or not shutil.which('ansible-playbook'),
    reason='Linux localhost Ansible required')


def run_gates(tmp_path, phase, mode, service, *, ingress_active=True, docker_active=True):
    public = config.load(ROOT / 'deploy/example.json', ROOT)
    public['environment']['reviewerBind'].update(mode=mode, network='shared-net', container='shared-proxy')
    public['environment']['ingress']['service'] = service
    config.validate(public, ROOT)
    values = {**yaml.safe_load((BACKEND / 'group_vars/all.yml').read_text()), **config.compile_inputs(public)}
    values.update(relay_deployment_profile='production', relay_production_host='localhost',
                  relay_production_runner_enable_reviewer_listener_before={'stdout': '127.0.0.1:8787'},
                  relay_production_runner_enable_reviewer_enabled={'stdout': 'enabled'})
    if mode == 'docker_gateway':
        values['relay_production_runner_enable_reviewer_listener_before']['stdout'] = '172.28.0.1:8787'
    playbook = ('relay-production-runner-enable.yml' if phase == 'runner-enable'
                else 'relay-production-operation-stale-disposition.yml')
    source = yaml.safe_load((BACKEND / playbook).read_text())[0]['pre_tasks']
    if phase == 'runner-enable':
        names = [
            'Resolve the validated Reviewer nexus gateway before runner readiness checks',
            'Inspect pre-enable service and protected runtime boundaries',
            'Classify the runner-enable prestate for idempotent replay',
            'Require the pre-enable runner and protected-service state',
        ]
        tasks = [next(task for task in source if task['name'] == name) for name in names]
    else:
        # Preserve both the real mode assertion and the real include-role guard.
        tasks = source[1:3]
    tasks.append(yaml.safe_load((BACKEND / 'tasks/production-reviewer-bind-state.yml').read_text())[0])
    probes = tmp_path / 'probes.jsonl'
    binaries = tmp_path / 'bin'
    binaries.mkdir()
    stub = '''#!/usr/bin/python3
import json,os,sys
from pathlib import Path
name=Path(sys.argv[0]).name
args=sys.argv[1:]
with open(os.environ['PROBE_LOG'],'a') as log: log.write(json.dumps([name,*args])+'\\n')
if name=='systemctl':
    operation,unit=args
    if unit==os.environ['INGRESS_SERVICE']: state='active' if os.environ['INGRESS_ACTIVE']=='1' else 'inactive'
    elif unit=='docker.service': state='active' if os.environ['DOCKER_ACTIVE']=='1' else 'inactive'
    elif unit=='reviewer-mcp.service': state='active' if operation=='is-active' else 'enabled'
    elif unit in ['relay-runner.service','relay-controller.service']: state='inactive' if operation=='is-active' else 'disabled'
    else: raise SystemExit(70)
    print(state)
    raise SystemExit(0 if state in ['active','enabled'] else 3)
if os.environ['BIND_MODE']=='loopback': raise SystemExit(71)
if name=='docker':
    if args==['network','inspect','shared-net']:
        print(json.dumps([{'Name':'shared-net','Id':'shared-id','Driver':'bridge','IPAM':{'Config':[{'Gateway':'172.28.0.1'}]}}]))
    elif args==['inspect','shared-proxy']:
        print(json.dumps([{'Name':'/shared-proxy','NetworkSettings':{'Networks':{'shared-net':{'NetworkID':'shared-id','Gateway':'172.28.0.1'}}}}]))
    else: raise SystemExit(72)
elif name=='ip':
    if args==['-o','-4','addr','show']: print('2: br-fixture inet 172.28.0.1/16 scope global br-fixture')
    elif args==['-4','route','get','172.28.0.1']: print('local 172.28.0.1 dev lo src 172.28.0.1')
    else: raise SystemExit(73)
else: raise SystemExit(74)
'''
    for name in ['systemctl', 'docker', 'ip']:
        executable = binaries / name
        executable.write_text(stub)
        executable.chmod(0o755)
    fixture = tmp_path / 'gates.yml'
    fixture.write_text(yaml.safe_dump([{'hosts': 'localhost', 'gather_facts': False,
        'vars': values, 'tasks': tasks}]))
    ansible_config = tmp_path / 'ansible.cfg'
    ansible_config.write_text('[defaults]\n')
    result = subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(fixture)],
        cwd=tmp_path, env={**os.environ, 'ANSIBLE_CONFIG': str(ansible_config),
            'ANSIBLE_ROLES_PATH': str(BACKEND / 'roles'), 'ANSIBLE_NOCOLOR': '1',
            'PATH': str(binaries) + os.pathsep + os.environ['PATH'], 'PROBE_LOG': str(probes),
            'INGRESS_SERVICE': service, 'INGRESS_ACTIVE': str(int(ingress_active)),
            'DOCKER_ACTIVE': str(int(docker_active)), 'BIND_MODE': mode},
        capture_output=True, text=True)
    calls = [json.loads(line) for line in probes.read_text().splitlines()] if probes.exists() else []
    return result, calls


@pytest.mark.parametrize('phase', ['runner-enable', 'stale-dispose'])
@pytest.mark.parametrize('mode', ['loopback', 'docker_gateway'])
def test_configured_service_and_bind_are_usable(tmp_path, phase, mode):
    result, calls = run_gates(tmp_path, phase, mode, 'shared-proxy.service', docker_active=mode != 'loopback')
    assert result.returncode == 0, result.stdout + result.stderr
    assert not any('nexus-docker.service' in call for call in calls)
    if phase == 'runner-enable':
        assert ['systemctl', 'is-active', 'shared-proxy.service'] in calls
    if mode == 'loopback':
        assert not any(call[0] in ['docker', 'ip'] for call in calls)
        assert ['systemctl', 'is-active', 'docker.service'] not in calls
    else:
        assert ['docker', 'network', 'inspect', 'shared-net'] in calls
        assert ['docker', 'inspect', 'shared-proxy'] in calls


@pytest.mark.parametrize('mode', ['loopback', 'docker_gateway'])
def test_configured_ingress_must_be_active(tmp_path, mode):
    result, calls = run_gates(tmp_path, 'runner-enable', mode, 'shared-proxy.service', ingress_active=False)
    assert result.returncode != 0
    assert 'PRODUCTION_RUNNER_ENABLE_PRESTATE_INVALID' in result.stdout
    assert ['systemctl', 'is-active', 'shared-proxy.service'] in calls


@pytest.mark.parametrize('docker_active', [True, False])
def test_existing_nexus_gateway_behavior_is_preserved(tmp_path, docker_active):
    result, calls = run_gates(tmp_path, 'runner-enable', 'docker_gateway',
                              'nexus-docker.service', docker_active=docker_active)
    assert (result.returncode == 0) == docker_active, result.stdout + result.stderr
    assert ['systemctl', 'is-active', 'nexus-docker.service'] in calls
    assert ['systemctl', 'is-active', 'docker.service'] in calls
    if not docker_active:
        assert 'PRODUCTION_RUNNER_ENABLE_PRESTATE_INVALID' in result.stdout
