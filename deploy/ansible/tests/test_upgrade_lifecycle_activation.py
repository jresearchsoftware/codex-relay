"""Run managed activation tasks locally without changing host services or users."""
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import tempfile
import unittest

from jinja2 import Environment, StrictUndefined
import yaml

from test_general_runner import instance


ROOT = Path(__file__).resolve().parents[1]
ANSIBLE = os.name != 'nt' and shutil.which('ansible-playbook') is not None
HEAD = 'a' * 40
OPERATION = '12345678-1234-1234-1234-123456789abc'


def service(pid=0, *, active=False, enabled='disabled', loaded=True):
    return '\n'.join((
        f'MainPID={pid}', 'ActiveState=' + ('active' if active else 'inactive'),
        f'ExecMainStartTimestampMonotonic={pid * 100}',
        'SubState=' + ('running' if active else 'dead'), f'UnitFileState={enabled}',
        'LoadState=' + ('loaded' if loaded else 'not-found'), 'NeedDaemonReload=no',
    ))


@unittest.skipUnless(ANSIBLE, 'Linux Ansible required')
class UpgradeActivationTests(unittest.TestCase):
    def run_play(self, root, tasks, values, *, handlers=None):
        play = root / 'play.yml'
        play.write_text(yaml.safe_dump([{
            'hosts': 'localhost', 'connection': 'local', 'gather_facts': False,
            'vars': values, 'tasks': tasks, **({'handlers': handlers} if handlers else {}),
        }], sort_keys=False))
        env = {**os.environ, 'ANSIBLE_NOCOLOR': '1', 'ANSIBLE_LOCALHOST_WARNING': 'False',
               'ANSIBLE_ROLES_PATH': str(root / 'roles')}
        return subprocess.run(['ansible-playbook', '-i', 'localhost,', str(play)],
                              env=env, text=True, capture_output=True, timeout=75)

    def fixture(self, root, initial, final):
        state = root / 'state.json'
        state.write_text(json.dumps(initial))
        trace = root / 'calls'
        systemctl = root / 'systemctl'
        systemctl.write_text(
            '#!/usr/bin/python3\nimport json,sys\nfrom pathlib import Path\n'
            f'states=json.loads(Path({str(state)!r}).read_text())\n'
            'print(states[sys.argv[2]])\n'
        )
        systemctl.chmod(0o755)
        restart = root / 'restart'
        restart.write_text(
            '#!/usr/bin/python3\nfrom pathlib import Path\n'
            f'Path({str(trace)!r}).write_text("restart\\n")\n'
            f'Path({str(state)!r}).write_text({json.dumps(final)!r})\n'
        )
        restart.chmod(0o755)
        gate_root = root / 'gate'
        gate_root.mkdir(exist_ok=True, mode=0o700)
        admission = root / 'admission.mjs'
        admission.write_text(
            'import { createAdmissionControl } from ' + json.dumps(
                (ROOT.parents[1] / 'controller/src/admission-control.mjs').as_uri()) + ';\n'
            'import { readFile, access } from "node:fs/promises";\n'
            f'const root={json.dumps(str(gate_root))};\n'
            'const gate=createAdmissionControl({root,consumerDigest:"a".repeat(64),'
            'protectedRoot:false,store:{all:async()=>[]},journal:{}});\n'
            'const [action,flag,operationId,phaseFlag,phase]=process.argv.slice(2);\n'
            'if(flag!=="--operation") throw Error("fixture operation missing");\n'
            'try {await access(root+"/admission-v1.json");} catch {\n'
            'await gate.initialize(); await gate.quiesce({operationId,target:"a".repeat(40)});'
            'await gate.drained({operationId}); await gate.phase({operationId,phase:"applying"});}\n'
            'let output; if(action==="snapshot") {let input=""; for await(const chunk of process.stdin) input+=chunk;'
            'output=await gate.snapshot({operationId,services:JSON.parse(input)});}\n'
            'else if(action==="phase" && phaseFlag==="--phase") output=await gate.phase({operationId,phase});\n'
            'else throw Error("fixture action invalid");\nconsole.log(JSON.stringify(output));\n')
        gate_helper = root / 'relay-admission'
        consumer_fixture = root / 'consumer.json'
        shutil.copyfile(ROOT.parents[1] / 'consumer/fixtures/example.json', consumer_fixture)
        consumer_fixture.chmod(0o600)
        gate_helper.write_text('#!/bin/sh\nexport RELAY_CONSUMER_CONFIG=' + shlex.quote(str(
            consumer_fixture)) + '\nexec ' + shlex.quote(shutil.which('node')) + ' '
                               + shlex.quote(str(admission)) + ' "$@"\n')
        gate_helper.chmod(0o755)
        tasks = []
        for name in ('snapshot', 'activate', 'validation'):
            source = (ROOT / f'tasks/upgrade-lifecycle-{name}.yml').read_text()
            path = root / f'{name}.yml'
            path.write_text(source.replace('/bin/systemctl', str(systemctl))
                           .replace('retries: 30', 'retries: 1').replace('delay: 1', 'delay: 0'))
            tasks.append({'ansible.builtin.include_tasks': str(path)})
        # The private listener remains the production health boundary. Use a
        # temporary local TCP listener so the real wait_for executes too.
        import socket
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen(16)
        self.addCleanup(listener.close)
        values = {
            'relay_reviewer_service_name': 'reviewer.service',
            'relay_production_runner_service_name': 'production.service',
            'relay_general_runner_service_name': 'general.service',
            'relay_reviewer_operation_restart_path': str(restart),
            'relay_reviewer_bind_address': '127.0.0.1',
            'relay_reviewer_bind_port': listener.getsockname()[1],
            'relay_production_operation_target_head': HEAD,
            'relay_install_root': str(root), 'relay_admission_operation_id': OPERATION,
        }
        return tasks, values, trace

    def test_active_reviewer_adopts_target_and_preserves_general_transport(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            initial = {'reviewer.service': service(41, active=True, enabled='enabled'),
                       'production.service': service(42, active=True, enabled='enabled'),
                       'general.service': service(43, active=True, enabled='enabled')}
            final = {**initial, 'reviewer.service': service(51, active=True, enabled='enabled'),
                     'production.service': service(52, active=True, enabled='enabled')}
            tasks, values, trace = self.fixture(root, initial, final)
            result = self.run_play(root, tasks, values)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(trace.read_text(), 'restart\n')
            self.assertIn('RELAY_UPGRADE_ACTIVATION_VALIDATED=' + HEAD, result.stdout)

    def test_inactive_and_unregistered_components_remain_off(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            initial = {'reviewer.service': service(), 'production.service': service(),
                       'general.service': service(43, active=True, enabled='enabled')}
            tasks, values, trace = self.fixture(root, initial, initial)
            result = self.run_play(root, tasks, values)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse(trace.exists())

    def test_lost_health_enablement_or_transport_never_yields_activation_proof(self):
        initial = {'reviewer.service': service(41, active=True, enabled='enabled'),
                   'production.service': service(42, active=True, enabled='enabled'),
                   'general.service': service(43, active=True, enabled='enabled')}
        final = {**initial, 'reviewer.service': service(51, active=True, enabled='enabled'),
                 'production.service': service(52, active=True, enabled='enabled')}
        for unit, changed, error in (
            ('production.service', service(), 'Require previously active services to become healthy in the same operation'),
            ('production.service', service(52, active=True), 'RELAY_UPGRADE_SERVICE_ACTIVATION_UNPROVEN'),
            ('general.service', service(53, active=True, enabled='enabled'), 'RELAY_UPGRADE_GENERAL_TRANSPORT_CHANGED'),
        ):
            with self.subTest(unit=unit), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                tasks, values, _trace = self.fixture(root, initial, {**final, unit: changed})
                result = self.run_play(root, tasks, values)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(error, result.stdout)
                self.assertNotIn('RELAY_UPGRADE_ACTIVATION_VALIDATED=', result.stdout)

    def test_unauthorized_activation_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            initial = {'reviewer.service': service(41, active=True, enabled='enabled'),
                       'production.service': service(), 'general.service': service()}
            final = {**initial, 'production.service': service(52, active=True, enabled='enabled')}
            tasks, values, _trace = self.fixture(root, initial, final)
            result = self.run_play(root, tasks, values)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('RELAY_UPGRADE_SERVICE_ACTIVATION_UNPROVEN', result.stdout)

    def test_successful_noop_restart_helper_cannot_claim_process_adoption(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            initial = {'reviewer.service': service(41, active=True, enabled='enabled'),
                       'production.service': service(), 'general.service': service()}
            tasks, values, _trace = self.fixture(root, initial, initial)
            result = self.run_play(root, tasks, values)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('RELAY_UPGRADE_ACTIVE_PROCESS_NOT_REPLACED', result.stdout)
            self.assertNotIn('RELAY_UPGRADE_ACTIVATION_VALIDATED=', result.stdout)

    def test_failed_activation_recovers_original_activity_and_never_starts_originally_off_runner(self):
        for production_active in (True, False):
            with self.subTest(production_active=production_active), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                original = {'reviewer.service': service(41, active=True, enabled='enabled'),
                            'production.service': service(42, active=True, enabled='enabled') if production_active else service(),
                            'general.service': service(43, active=True, enabled='enabled')}
                failed = {**original, 'reviewer.service': service(enabled='enabled'),
                          'production.service': service(enabled='enabled') if production_active else service()}
                tasks, values, _trace = self.fixture(root, original, failed)
                rejected = self.run_play(root, tasks, values)
                self.assertNotEqual(rejected.returncode, 0, rejected.stdout + rejected.stderr)
                saved = json.loads((root / 'gate/admission-v1.json').read_text())['previousActive']
                self.assertTrue(saved['reviewer']['active'])
                self.assertEqual(saved['production']['active'], production_active)
                helper = root / 'relay-admission'
                for phase in ('recovery-required', 'applying'):
                    subprocess.run([str(helper), 'phase', '--operation', OPERATION, '--phase', phase],
                                   check=True, text=True, capture_output=True)
                recovered = {**original, 'reviewer.service': service(51, active=True, enabled='enabled'),
                             'production.service': service(52, active=True, enabled='enabled') if production_active else service()}
                tasks, values, trace = self.fixture(root, failed, recovered)
                # Observed failed state cannot supply new activation authority.
                unauthorized = self.run_play(root, tasks, values)
                self.assertNotEqual(unauthorized.returncode, 0, unauthorized.stdout + unauthorized.stderr)
                self.assertIn('RELAY_UPGRADE_RETAINED_ACTIVITY_RECOVERY_REQUIRED', unauthorized.stdout)
                self.assertEqual(json.loads((root / 'gate/admission-v1.json').read_text())['previousActive'], saved)
                values['relay_admission_recovery_authorized'] = True
                accepted = self.run_play(root, tasks, values)
                self.assertEqual(accepted.returncode, 0, accepted.stdout + accepted.stderr)
                self.assertEqual(trace.read_text(), 'restart\n')
                self.assertEqual(json.loads((root / 'gate/admission-v1.json').read_text())['previousActive'], saved)
                self.assertIn('RELAY_UPGRADE_ACTIVATION_VALIDATED=' + HEAD, accepted.stdout)

    def test_recovery_never_restarts_a_lost_general_transport(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = {'reviewer.service': service(), 'production.service': service(),
                        'general.service': service(43, active=True, enabled='enabled')}
            tasks, values, _trace = self.fixture(root, original, original)
            first = self.run_play(root, tasks[:1], values)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            failed = {**original, 'general.service': service(enabled='enabled')}
            tasks, values, trace = self.fixture(root, failed, original)
            values['relay_admission_recovery_authorized'] = True
            result = self.run_play(root, tasks, values)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('RELAY_UPGRADE_RETAINED_ACTIVITY_RECOVERY_REQUIRED', result.stdout)
            self.assertFalse(trace.exists())

    def test_active_general_unit_allows_live_partof_removal_and_refuses_other_drift(self):
        source = yaml.safe_load((ROOT / 'roles/relay_runner/tasks/main.yml').read_text())
        selected = [task for task in source if task['name'] in (
            'Read the active general transport unit before managed reconciliation',
            'Refuse general transport changes that require process replacement',
        )]
        for drift in (False, True):
            with self.subTest(drift=drift), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                role = root / 'roles/relay_runner'
                (role / 'tasks').mkdir(parents=True)
                (role / 'templates').mkdir()
                (role / 'tasks/main.yml').write_text(yaml.safe_dump(selected, sort_keys=False))
                shutil.copy(ROOT / 'roles/relay_runner/templates/relay-runner.service.j2', role / 'templates')
                values = instance(True)
                values.update(relay_upgrade_lifecycle_managed=True,
                              relay_upgrade_lifecycle_general_was_active=True,
                              relay_runner_service_unit_path=str(root / 'general.service'))
                template = Environment(undefined=StrictUndefined, trim_blocks=True,
                                       keep_trailing_newline=True).from_string(
                    (role / 'templates/relay-runner.service.j2').read_text())
                candidate = template.render(values)
                old = candidate.replace('After=network-online.target reviewer-mcp.service\n',
                    'After=network-online.target reviewer-mcp.service\nPartOf=reviewer-mcp.service\n')
                if drift:
                    old = old.replace('Restart=on-failure', 'Restart=always')
                (root / 'general.service').write_text(old)
                result = self.run_play(root, [{'ansible.builtin.include_role': {'name': 'relay_runner'}}], values)
                self.assertEqual(result.returncode == 0, not drift, result.stdout + result.stderr)
                if drift:
                    self.assertIn('RELAY_UPGRADE_GENERAL_TRANSPORT_RESTART_REQUIRED', result.stdout)

    def test_commit_point_follows_installed_identity_and_transport_proof(self):
        site = (ROOT / 'site.yml').read_text()
        ordering = (
            'tasks/upgrade-lifecycle-snapshot.yml', 'tasks/production-operation-state-begin.yml',
            'ansible.builtin.meta: flush_handlers', 'tasks/upgrade-lifecycle-activate.yml',
            'tasks/production-reviewer-process-validation.yml', 'tasks/installed-identity.yml',
            'tasks/upgrade-lifecycle-validation.yml', 'tasks/production-operation-state-clear.yml',
            'PRODUCTION_APPLY_VALIDATED=',
        )
        positions = [site.index(marker) for marker in ordering]
        self.assertEqual(positions, sorted(positions))

    def test_live_general_identity_change_requires_recovery_instead_of_success(self):
        source = yaml.safe_load((ROOT / 'roles/relay_runner/tasks/general-runtime.yml').read_text())
        guard = next(task for task in source if task['name'] ==
                     'Refuse stale identity or supplementary groups in the live general transport')
        for active, changed in ((True, False), (True, True), (False, True)):
            with self.subTest(active=active, changed=changed), tempfile.TemporaryDirectory() as temporary:
                result = self.run_play(Path(temporary), [guard], {
                    'relay_upgrade_lifecycle_managed': True,
                    'relay_upgrade_lifecycle_general_was_active': active,
                    'relay_general_runtime_identity': {'changed': changed},
                })
                self.assertEqual(result.returncode == 0, not (active and changed), result.stdout + result.stderr)
                if active and changed:
                    self.assertIn('RELAY_UPGRADE_GENERAL_TRANSPORT_IDENTITY_RESTART_REQUIRED', result.stdout)
