"""Render, adopt and finally prove retained Reviewer config in real systemd.

Set RELAY_TEST_REVIEWER_BINARY to an ELF reviewer-mcp-http built from the
candidate source. Docker owns one uniquely named disposable TEST container.
GitHub/admission and Runner registration/executables are fixtures; Reviewer
observations, production template tasks, activation decisions, operation lock,
dependent service restart, and final retained proof execute the product code.
"""

import copy
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import unittest

import yaml

from test_reviewer_runner_systemd_lifecycle import DisposableSystemdLifecycle, docker_available


REPOSITORY = Path(__file__).resolve().parents[3]
SOURCE = Path('/opt/task202-step11-source')
STATE = Path('/run/lifecycle/retained-config-test.json')
ORIGINAL = 'a' * 40
DESIRED = 'b' * 40
OPERATION = '12345678-1234-1234-1234-123456789abc'


class RetainedReviewerSystemd(DisposableSystemdLifecycle):
    """Reuse production units/helpers but copy all inputs onto native Linux FS."""

    def __init__(self, binary):
        self.binary = Path(binary)
        super().__init__()
        self.name = self.name.replace('relay-systemd-', 'task202-step11-')

    def _render_fixture(self):
        super()._render_fixture()
        shutil.copyfile(self.binary, self.root / 'reviewer-binary')

    def _start_container(self):
        self._run_docker([
            'run', '--detach', '--privileged', '--cgroupns=host', '--name', self.name,
            '--tmpfs', '/run:exec', '--tmpfs', '/run/lock', '--tmpfs', '/tmp',
            '--volume', '/sys/fs/cgroup:/sys/fs/cgroup:rw', 'debian:12', 'bash', '-c',
            'apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq '
            'systemd systemd-sysv dbus iproute2 passwd procps python3 python3-yaml '
            'python3-jinja2 python3-pytest ansible-core ca-certificates && exec /lib/systemd/systemd',
        ], timeout=120)
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            if self._run_docker(['exec', self.name, 'test', '-S', '/run/systemd/private'], check=False).returncode == 0:
                break
            status = self._run_docker(['inspect', '--format', '{{.State.Status}}', self.name]).stdout.strip()
            if status in ('exited', 'dead'):
                raise AssertionError(self._run_docker(['logs', self.name]).stdout)
            time.sleep(.5)
        else:
            raise AssertionError('disposable TEST systemd did not start')
        self._run_docker(['cp', str(self.root), self.name + ':/opt/lifecycle'])
        self._exec_shell('mkdir -p /opt/task202-step11-source')
        self._run_docker(['cp', str(REPOSITORY / 'deploy'), self.name + ':' + (SOURCE / 'deploy').as_posix()])

    def inside(self, action, *, check=True):
        return self._run_docker([
            'exec', self.name, '/usr/bin/python3',
            (SOURCE / 'deploy/ansible/tests' / Path(__file__).name).as_posix(), '--inside', action,
        ], check=check, timeout=180)


def _command(argv):
    return subprocess.check_output(argv, text=True).strip()


def _service(unit):
    return dict(line.split('=', 1) for line in _command([
        '/bin/systemctl', 'show', unit,
        '--property=MainPID,ExecMainStartTimestampMonotonic,User,ActiveState,SubState,UnitFileState,LoadState',
    ]).splitlines())


def _write(path, raw, mode=0o600):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(raw)
    path.chmod(mode)


def _modules():
    sys.path[:0] = [str(SOURCE / 'deploy'), str(SOURCE / 'deploy/tests')]
    import retained_activation as activation
    from test_managed_pool import inputs
    return activation, inputs


def _boundary(activation, state):
    """Use fixture Runner registrations with real service/process/Unix users."""
    original_native = activation.Native

    class ExternalBoundary(original_native):
        def authority(self):
            current = json.loads(STATE.read_text())
            assert self.binding == current['binding']
            assert self.payload['previous'] == current['previous']
            assert current['operation'] == {'id': OPERATION, 'phase': 'applying', 'active': [], 'unknown': []}

        def runners(self, _contract):
            from types import SimpleNamespace
            values = [{'id': item['runnerId'], 'name': item['runnerName'], 'status': 'online', 'busy': False}
                      for item in state['binding']['runnerMaintenance']['runners'].values()]
            self.github = SimpleNamespace(runners=lambda: values)
            return values

        def runner(self, component, expected, identity, _contract, **_options):
            registration = json.loads(Path('/run/lifecycle/registrations.json').read_text())[component]
            assert registration == state['registrations'][component]
            assert registration['runnerId'] == expected['runnerId']
            assert registration['runnerName'] == expected['runnerName']
            assert registration['user'] == identity['user']
            assert registration['disableUpdate'] is False
            unit = state['units'][component]
            observed = _service(unit)
            assert observed['ActiveState'] == 'active' and observed['SubState'] == 'running'
            assert observed['User'] == registration['user']
            import pwd
            assert Path('/proc/' + observed['MainPID']).stat().st_uid == pwd.getpwnam(registration['user']).pw_uid
            ticks = Path('/proc/' + observed['MainPID'] + '/stat').read_text().rsplit(') ', 1)[1].split()[19]
            return {'service': unit, 'runnerId': expected['runnerId'], 'version': '2.338.2',
                    'pid': observed['MainPID'], 'startTicks': ticks}

        def primary(self, contract):
            identities, _ = activation.services(self.config)
            identity = identities['general']
            return self.runner('general', state['registrations']['general'], identity, contract)

    return ExternalBoundary


def _play(state, tasks, extra=None):
    values = {**state['variables'], **(extra or {})}
    play = SOURCE / 'deploy/ansible/retained-systemd-test.yml'
    play.write_text(yaml.safe_dump([{'hosts': 'localhost', 'connection': 'local', 'gather_facts': False,
        'vars': values, 'tasks': tasks, 'handlers': yaml.safe_load((
            SOURCE / 'deploy/ansible/roles/relay_runtime/handlers/main.yml').read_text())}], sort_keys=False))
    result = subprocess.run(['ansible-playbook', '-i', 'localhost,', str(play)],
        text=True, capture_output=True, timeout=150,
        env={**os.environ, 'ANSIBLE_NOCOLOR': '1', 'ANSIBLE_LOCALHOST_WARNING': 'False'})
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    return result.stdout


def _render_tasks():
    role = SOURCE / 'deploy/ansible/roles/relay_runtime'
    authored = yaml.safe_load((role / 'tasks/main.yml').read_text())
    tasks = []
    for name in ('Install secret-free relay environment contract', 'Install reviewer configuration contract'):
        task = copy.deepcopy(next(item for item in authored if item.get('name') == name))
        task['ansible.builtin.template']['src'] = str(role / 'templates' / task['ansible.builtin.template']['src'])
        tasks.append(task)
    return tasks


def _inside_setup():
    activation, inputs = _modules()
    config = inputs(6, namespace='lifecycle')
    del config['environment']['instance']
    config['environment']['reviewerUser'] = 'relay-reviewer'
    config['environment']['runner']['user'] = 'relay-runner'
    config['environment']['generalRunner']['user'] = 'relay-general-runner'
    from config import compile_inputs
    variables = {**yaml.safe_load((SOURCE / 'deploy/ansible/group_vars/all.yml').read_text()),
                 **compile_inputs(config)}
    variables.update(relay_config_root='/etc/lifecycle', relay_install_root='/opt/lifecycle',
        relay_state_root='/run/lifecycle/state', relay_evidence_root='/run/lifecycle/evidence',
        relay_runtime_root='/run/lifecycle/runtime', relay_log_root='/run/lifecycle/log',
        relay_reviewer_service_name='reviewer-mcp.service', relay_reviewer_group='relay-reviewer',
        relay_reviewer_bind_address='127.0.0.1', relay_reviewer_bind_port=8787,
        relay_reviewer_bind_mode='a_only_loopback', relay_reviewer_bind_network='',
        relay_reviewer_gateway_validated=False,
        relay_reviewer_exec_start='/opt/lifecycle/current/bin/reviewer-mcp-http --config /etc/lifecycle/reviewer-mcp.json',
        relay_reviewer_operation_restart_path='/usr/local/libexec/relay-reviewer-operation-restart',
        relay_reviewer_relay_enabled=False, relay_tls_client_ca_file='/etc/lifecycle/synthetic-ca.pem',
        relay_upgrade_lifecycle_managed=True, relay_production_defer_lifecycle=False,
        relay_production_runner_service_name='relay-runner.service',
        relay_general_runner_service_name='relay-general-runner.service',
        relay_namespace='lifecycle', relay_admission_operation_id=OPERATION,
        relay_admission_recovery_authorized=True, relay_production_operation_target_head=DESIRED,
        relay_retained_reviewer_config_adoption=True,
        relay_release_commit=ORIGINAL, relay_release_sha256='a' * 64)
    digest = hashlib.sha256(Path('/opt/lifecycle/reviewer-binary').read_bytes()).hexdigest()
    # Deliberate overlapping synthetic commit/tree strings also reject naive
    # global string replacement when reconstructing the original render.
    for revision, archive in ((ORIGINAL, 'a' * 64), (DESIRED, 'b' * 64)):
        release = Path('/opt/lifecycle/releases') / revision
        (release / 'bin').mkdir(parents=True)
        shutil.copyfile('/opt/lifecycle/reviewer-binary', release / 'bin/reviewer-mcp-http')
        (release / 'bin/reviewer-mcp-http').chmod(0o755)
        _write(release / 'artifact-manifest.json', json.dumps({'commit': revision,
            'releaseSourceTreeSha256': archive, 'reviewerBinarySha256': digest}), 0o644)
    shutil.rmtree('/opt/lifecycle/current')
    Path('/opt/lifecycle/current').symlink_to('releases/' + ORIGINAL)
    state = {'config': config, 'variables': variables}
    Path('/etc/lifecycle').mkdir(mode=0o755)
    _play(state, _render_tasks())
    original = Path('/etc/lifecycle/reviewer-mcp.json').read_text()
    _write('/etc/lifecycle/reviewer-activation-authorized', 'authorized\n')
    _write('/etc/lifecycle/synthetic-ca.pem', 'synthetic readable CA; no request is made\n', 0o644)
    _write('/opt/lifecycle/reviewer-app.env', 'GITHUB_APP_ID=' + str(variables['relay_reviewer_app_id']) +
        '\nGITHUB_APP_INSTALLATION_ID=' + str(variables['relay_reviewer_app_installation_id']) + '\n', 0o644)
    unit = Path('/etc/systemd/system/reviewer-mcp.service')
    text = unit.read_text().replace('EnvironmentFile=/opt/lifecycle/relay.env',
        'EnvironmentFile=/etc/lifecycle/relay.env\nEnvironmentFile=/opt/lifecycle/reviewer-app.env')
    text = text.replace('ExecStart=/usr/local/libexec/reviewer-process', 'ExecStart=' + variables['relay_reviewer_exec_start'])
    unit.write_text(text)
    _write('/etc/systemd/system/lifecycle-relay-manual-outcome.socket',
        '[Unit]\nDescription=Disposable inactive manual outcome socket\n[Socket]\n'
        'ListenStream=/run/lifecycle/manual.sock\n[Install]\nWantedBy=sockets.target\n', 0o644)
    subprocess.run(['/bin/systemctl', 'daemon-reload'], check=True)
    identities, _ = activation.services(config)
    units = {'production': 'relay-runner.service', 'general': 'relay-general-runner.service'}
    registrations = {}
    for index, (component, identity) in enumerate(identities.items(), 55):
        if component not in units:
            units[component] = identity['service']
            path = Path('/etc/systemd/system') / identity['service']
            path.write_text(Path('/etc/systemd/system/relay-general-runner.service').read_text())
        registrations[component] = {'runnerId': index, 'runnerName': identity['name'],
            'user': identity['user'], 'group': identity['group'], 'work': identity['work'], 'disableUpdate': False}
    subprocess.run(['/bin/systemctl', 'daemon-reload'], check=True)
    subprocess.run(['/bin/systemctl', 'enable', '--now', 'reviewer-mcp.service'], check=True)
    # Reviewer binds asynchronously. The real start gate checks its listener.
    deadline = time.monotonic() + 20
    while '127.0.0.1:8787' not in _command(['/usr/bin/ss', '-H', '-ltn']):
        if time.monotonic() >= deadline:
            raise AssertionError('real Reviewer listener did not start\n' + _command([
                '/bin/journalctl', '-u', 'reviewer-mcp.service', '--no-pager', '-n', '25']))
        time.sleep(.1)
    subprocess.run(['/bin/systemctl', 'enable', '--now', *units.values()], check=True)
    off = {'active': False, 'enabled': 'enabled', 'load': 'loaded'}
    previous = {component: dict(off) for component in identities}
    previous.update(reviewer={**off, 'active': True}, general={**off, 'active': True},
                    manualOutcome={'active': False, 'enabled': 'disabled', 'load': 'loaded'})
    observed = {key: {**item, 'active': key != 'manualOutcome'} for key, item in previous.items()}
    maintained = {key: {'runnerId': value['runnerId'], 'runnerName': value['runnerName']}
                  for key, value in registrations.items() if key != 'general'}
    binding = {'operationId': OPERATION, 'retainedTarget': ORIGINAL, 'installedRevision': ORIGINAL,
        'controllerRevision': DESIRED, 'desiredRevision': DESIRED,
        'gitConfigReceipt': {'product_sha': DESIRED, 'config_sha': 'c' * 40, 'config_blob_sha': 'd' * 40,
                             'config_sha256': 'e' * 64},
        'runnerMaintenance': {'operationId': OPERATION, 'retainedTarget': ORIGINAL, 'runners': maintained}}
    state.update(units=units, registrations=registrations, binding=binding, previous=previous, observed=observed,
                 original=original, operation={'id': OPERATION, 'phase': 'applying', 'active': [], 'unknown': []})
    _write('/run/lifecycle/registrations.json', json.dumps(registrations))
    _write(STATE, json.dumps(state))
    payload = _payload(state)
    before = activation.prove(payload, _boundary(activation, state)(payload))
    assert activation.prove({**payload, 'before': before}, _boundary(activation, state)(payload)) == before
    state['before'] = before
    state['primary'] = _service(units['general'])
    _write(STATE, json.dumps(state))
    # The production helper reads its real protected record and admission view.
    _write('/run/lifecycle/operation-state.json', json.dumps({'schemaVersion': '1',
        'state': 'RECOVERY_REQUIRED', 'phase': 'apply', 'target_head': DESIRED}))
    _write('/opt/lifecycle/relay-admission', '#!/bin/sh\ncat /run/lifecycle/admission.json\n', 0o755)
    _write('/run/lifecycle/admission.json', json.dumps({'operationId': OPERATION, 'target': DESIRED,
        'phase': 'applying', 'active': [], 'unknown': [], 'previousActive': previous}))
    gate = json.dumps({'version': 1, 'consumerDigest': 'a' * 64, 'operationId': OPERATION,
        'target': ORIGINAL, 'phase': 'recovery-required', 'previousActive': previous, 'verifiedRevision': None}).encode()
    backend = json.dumps({'schemaVersion': '1', 'state': 'RECOVERY_REQUIRED',
                          'phase': 'apply', 'target_head': ORIGINAL}).encode()
    receipt = {'schemaVersion': 1, 'binding': binding, 'state': 'reserved', 'desiredDigest': 'b' * 64,
        'desiredConfigSha256': hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
        'original': {**{key: 'a' * 64 for key in ('manifestSha256', 'sourceSha256', 'sourceGraphSha256',
            'snapshotSha256', 'resourceSha256', 'consumerSha256')},
            'backendBytes': base64.b64encode(backend).decode(), 'backendSha256': hashlib.sha256(backend).hexdigest(),
            'gateBytes': base64.b64encode(gate).decode(), 'gateSha256': hashlib.sha256(gate).hexdigest()}}
    receipt_path = '/run/lifecycle/operation-state.' + OPERATION + '.continuation.json'
    _write(receipt_path, json.dumps(receipt))
    activation.retained.load_receipt(Path(receipt_path), Path('/'), 0)
    state['receiptPath'] = receipt_path
    state['receiptBytes'] = Path(receipt_path).read_text()
    _write(STATE, json.dumps(state))
    for revision in (ORIGINAL, DESIRED):
        destination = Path('/opt/lifecycle/releases') / revision / 'reviewed-source/deploy'
        destination.parent.mkdir(parents=True)
        shutil.copytree(SOURCE / 'deploy', destination)
    Path('/opt/lifecycle/relay-reviewer-operation-restart').chmod(0o750)
    _write('/run/lifecycle/production-operation.lock', '')
    print('REAL_REVIEWER_RETAINED_SETUP_PASS')


def _payload(state):
    return {key: state[key] for key in ('config', 'binding', 'previous', 'observed')} | {
        'admission': ['/opt/lifecycle/relay-admission'],
        'release': '/opt/lifecycle/releases/' + DESIRED, 'listener': '127.0.0.1:8787'}


def _inside_proof():
    activation, _ = _modules()
    state = json.loads(STATE.read_text())
    activation.Native = _boundary(activation, state)
    activation.main()


def _inside_run():
    activation, _ = _modules()
    state = json.loads(STATE.read_text())
    before = state['before']
    original = state['original']
    variables = state['variables']
    variables.update(relay_release_commit=DESIRED, relay_release_sha256='b' * 64)
    _play(state, _render_tasks())
    desired = Path('/etc/lifecycle/reviewer-mcp.json').read_text()
    assert desired != original
    payload = _payload(state) | {'before': before}
    native = _boundary(activation, state)(payload)
    try:
        activation.prove(payload, native)
    except ValueError as error:
        assert 'MAINTAINED_RUNTIME_CHANGED' in str(error), str(error)
    else:
        raise AssertionError('the original strict final proof must detect real config drift')
    # Product APIs, not a fixed reviewer digest, govern this transition.
    payload.update(action='adopt-reviewer-config', reviewerConfigTransition={'original': original, 'desired': desired})
    foreign = json.loads(original)
    foreign['owner'] = 'foreign-owner'
    unauthorized = {**payload, 'reviewerConfigTransition': {'original': json.dumps(foreign), 'desired': desired}}
    try:
        activation.adopt_config(unauthorized, _boundary(activation, state)(unauthorized))
    except ValueError as error:
        assert 'CONFIG_ADOPTION_DELTA_UNSUPPORTED' in str(error), str(error)
    else:
        raise AssertionError('an unauthorized policy delta granted config adoption')
    assert native.reviewer()['pid'] == before['reviewer']['pid']
    # The production decision remains closed unless the specific owner choice
    # is supplied; rendering alone cannot grant the guarded restart.
    variables.update(relay_upgrade_lifecycle_previous_active=state['previous'],
        relay_upgrade_lifecycle_observed_activity=state['observed'],
        relay_upgrade_lifecycle_maintenance_proof=before,
        relay_upgrade_lifecycle_effective_active=state['observed'],
        relay_upgrade_lifecycle_reviewer_was_active=True,
        relay_upgrade_lifecycle_production_was_active=True,
        relay_upgrade_lifecycle_general_was_active=True,
        relay_installed_deployment_config=json.dumps(state['config']),
        relay_bounded_recovery_binding=state['binding'],
        relay_intent_admission_prefix=['/opt/lifecycle/relay-admission'],
        relay_intent_staged_release='/opt/lifecycle/releases/' + DESIRED,
        relay_intent_stage_root='/opt/lifecycle/releases/.stage-' + OPERATION,
        relay_additional_execution_slots=[{'relay_execution_slot': component.removeprefix('slot-'),
            'relay_runner_service_name': unit} for component, unit in state['units'].items() if component.startswith('slot-')],
        relay_reviewer_activation_marker='/run/lifecycle/reviewer-activation-authorized',
        relay_reviewer_recovery_off_marker='/run/lifecycle/reviewer-recovery-requires-activation',
        relay_production_operation_state_path='/usr/local/libexec/relay-production-operation-state',
        relay_production_operation_lock_path='/run/lifecycle/production-operation.lock',
        relay_production_operation_record_path='/run/lifecycle/operation-state.json',
        relay_runner_service_name='relay-runner.service')
    Path(variables['relay_intent_stage_root']).mkdir(mode=0o700)
    tasks_root = SOURCE / 'deploy/ansible/tasks'
    proof_argv = ['/usr/bin/python3', str(Path(__file__)), '--inside', 'proof']
    # Only the external transport adapter is injected. Both production task
    # bodies retain their real stdin contract, decision, renderer and checks.
    maintained = yaml.safe_load((tasks_root / 'upgrade-maintained-runners.yml').read_text())
    maintained[0]['ansible.builtin.command']['argv'] = proof_argv
    (tasks_root / 'retained-test-maintained.yml').write_text(yaml.safe_dump(maintained))
    adoption = yaml.safe_load((tasks_root / 'upgrade-reviewer-config-adoption.yml').read_text())
    next(task for task in adoption if 'ansible.builtin.command' in task)['ansible.builtin.command']['argv'] = proof_argv
    (tasks_root / 'retained-test-adoption.yml').write_text(yaml.safe_dump(adoption))
    activate = yaml.safe_load((tasks_root / 'upgrade-lifecycle-activate.yml').read_text())
    next(task for task in activate if task.get('ansible.builtin.include_tasks') ==
         'upgrade-reviewer-config-adoption.yml')['ansible.builtin.include_tasks'] = 'retained-test-adoption.yml'
    validation = yaml.safe_load((tasks_root / 'upgrade-lifecycle-validation.yml').read_text())
    validation[0]['ansible.builtin.include_tasks'] = 'retained-test-maintained.yml'
    (tasks_root / 'retained-test-activate.yml').write_text(yaml.safe_dump(activate))
    (tasks_root / 'retained-test-validation.yml').write_text(yaml.safe_dump(validation))
    sequence = [{'ansible.builtin.include_tasks': str(tasks_root / 'upgrade-lifecycle-observe.yml')},
        *_render_tasks(), {'ansible.builtin.meta': 'flush_handlers'},
        {'ansible.builtin.include_tasks': str(tasks_root / 'retained-test-activate.yml')},
        {'ansible.builtin.include_tasks': str(tasks_root / 'retained-test-validation.yml')}]
    try:
        _play(state, sequence, {'relay_retained_reviewer_config_adoption': False})
    except AssertionError as error:
        assert 'MAINTAINED_RUNTIME_CHANGED' in str(error), str(error)
    else:
        raise AssertionError('ordinary maintained decision silently allowed config adoption')
    assert native.reviewer()['pid'] == before['reviewer']['pid']
    output = _play(state, sequence + [{'ansible.builtin.copy': {
        'dest': '/run/lifecycle/adoption-result.json', 'mode': '0600',
        'content': '{{ relay_retained_reviewer_adoption.stdout }}'}}])
    assert 'RELAY_UPGRADE_ACTIVATION_VALIDATED=' in output
    result = json.loads(Path('/run/lifecycle/adoption-result.json').read_text())
    normalized = copy.deepcopy(before)
    normalized['reviewer']['config'] = hashlib.sha256(desired.encode()).hexdigest()
    assert result['before'] == normalized
    after = result['after']
    assert (after['reviewer']['pid'], after['reviewer']['start']) != (before['reviewer']['pid'], before['reviewer']['start'])
    assert after['reviewer']['config'] == hashlib.sha256(desired.encode()).hexdigest()
    assert after['reviewer']['executable'] == before['reviewer']['executable']
    assert b'--config\x00/etc/lifecycle/reviewer-mcp.json\x00' in Path(
        '/proc/' + after['reviewer']['pid'] + '/cmdline').read_bytes()
    assert after['runners']['production']['runnerId'] == before['runners']['production']['runnerId']
    assert after['runners']['production']['pid'] != before['runners']['production']['pid']
    assert _service(state['units']['general']) == state['primary']
    for component in after['runners']:
        if component != 'production':
            assert after['runners'][component] == before['runners'][component]
    payload['before'] = after
    assert activation.prove(payload, _boundary(activation, state)(payload)) == after
    assert json.loads(STATE.read_text())['previous'] == state['previous']
    assert Path(state['receiptPath']).read_text() == state['receiptBytes']
    assert json.loads(Path('/run/lifecycle/registrations.json').read_text()) == state['registrations']
    # Foreign bytes after adoption stay a refusal, even with valid config JSON.
    changed = json.loads(desired)
    changed['owner'] = 'foreign-owner'
    _write('/etc/lifecycle/reviewer-mcp.json', json.dumps(changed), 0o640)
    try:
        activation.prove(payload, _boundary(activation, state)(payload))
    except ValueError as error:
        assert 'MAINTAINED_RUNTIME_CHANGED' in str(error), str(error)
    else:
        raise AssertionError('foreign config drift was accepted')
    _write('/etc/lifecycle/reviewer-mcp.json', desired, 0o640)
    print('REAL_RENDER_ADOPTION_FINAL_PROOF_PASS')


class RetainedReviewerConfigSystemdTests(unittest.TestCase):
    def test_production_render_adopts_real_reviewer_and_preserves_retained_authority(self):
        binary = os.environ.get('RELAY_TEST_REVIEWER_BINARY')
        if not docker_available() or not binary:
            self.skipTest('Docker and candidate ELF RELAY_TEST_REVIEWER_BINARY are required')
        self.assertEqual(Path(binary).read_bytes()[:4], b'\x7fELF')
        with RetainedReviewerSystemd(binary) as fixture:
            fixture.write_activation_marker()
            fixture.write_registration_markers()
            self.assertIn('REAL_REVIEWER_RETAINED_SETUP_PASS', fixture.inside('setup').stdout)
            self.assertIn('REAL_RENDER_ADOPTION_FINAL_PROOF_PASS', fixture.inside('run').stdout)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--inside':
        {'setup': _inside_setup, 'run': _inside_run, 'proof': _inside_proof}[sys.argv[2]]()
    else:
        unittest.main()
