"""Exercise real handler notification and detect a replaced-but-still-running binary."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import yaml
from jinja2 import Environment, StrictUndefined

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name != 'nt' and shutil.which('ansible-playbook'), 'Linux Ansible required')
class AppliedReviewerTests(unittest.TestCase):
    def run_play(self, directory, play):
        path = directory / 'play.yml'
        path.write_text(yaml.safe_dump([{'hosts': 'localhost', 'gather_facts': False, **play}]))
        return subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(path)], capture_output=True, text=True, timeout=45)

    def test_actual_notification_reaches_locked_handler_and_preserves_deferral(self):
        for role, topic in [('relay_runtime', 'Try-restart Reviewer after configuration transition'),
                            ('relay_artifacts', 'Try-restart Reviewer after release transition'),
                            ('relay_reviewer_bind', 'Try-restart Reviewer for validated bind mode')]:
            for deferred, managed in ((False, False), (True, False), (False, True)):
                with self.subTest(role=role, deferred=deferred, managed=managed), tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    calls = root / 'calls'
                    helper = root / 'restart'
                    helper.write_text('#!/bin/sh\nprintf called >> "' + str(calls) + '"\n')
                    helper.chmod(0o755)
                    result = self.run_play(root, {
                        'vars': {'relay_deployment_profile': 'production', 'relay_production_operation_record_present': True,
                                 'relay_production_operation_phase': 'apply', 'relay_production_operation_recovery_required': False,
                                 'relay_production_defer_lifecycle': deferred, 'relay_service_effective_enabled': True,
                                 'relay_upgrade_lifecycle_managed': managed,
                                 'relay_reviewer_bind_post_activation_authorized': False,
                                 'relay_service_state_management': 'preserve', 'relay_reviewer_release_changed': True,
                                 'relay_reviewer_operation_restart_path': str(helper)},
                        'tasks': [{'ansible.builtin.command': '/bin/true', 'changed_when': True, 'notify': topic}],
                        'handlers': yaml.safe_load((ROOT / f'roles/{role}/handlers/main.yml').read_text()),
                    })
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertEqual(calls.read_text() if calls.exists() else '', '' if deferred or managed else 'called')

    def test_process_proof_rejects_new_disk_binary_masking_old_running_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            binary = root / 'reviewer'
            shutil.copyfile('/bin/sleep', binary)
            binary.chmod(0o755)
            old_digest = hashlib.sha256(binary.read_bytes()).hexdigest()
            process = subprocess.Popen([str(binary), '40'])
            try:
                # Retain the real stat/assert proof; substitute only systemd's
                # MainPID lookup with the PID of our disposable real process.
                tasks = yaml.safe_load((ROOT / 'tasks/production-reviewer-process-validation.yml').read_text())[1:]
                def probe(digest):
                    return self.run_play(root, {'vars': {
                        'relay_production_reviewer_main_pid': {'stdout': str(process.pid)},
                        'relay_production_final_manifest': {'reviewerBinarySha256': digest}}, 'tasks': tasks})
                passed = probe(old_digest)
                self.assertEqual(passed.returncode, 0, passed.stdout + passed.stderr)
                replacement = root / 'replacement'
                shutil.copyfile('/bin/true', replacement)
                replacement.replace(binary)
                failed = probe(hashlib.sha256(binary.read_bytes()).hexdigest())
                self.assertNotEqual(failed.returncode, 0)
                self.assertIn('PRODUCTION_REVIEWER_RUNNING_ARTIFACT_MISMATCH', failed.stdout)
            finally:
                process.terminate()
                process.wait(timeout=5)

    def test_locked_restart_waits_for_readiness_before_restoring_only_active_runner(self):
        import pwd
        import shlex

        for runner_active, ready in ((False, False), (True, True), (True, False)):
            with self.subTest(runner_active=runner_active, ready=ready), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                marker = root / 'activation'
                marker.write_text('authorized\n')
                marker.chmod(0o600)
                trace = root / 'calls'
                systemctl = root / 'systemctl'
                systemctl.write_text(
                    '#!/usr/bin/python3\nimport sys\nfrom pathlib import Path\n'
                    f'with Path({str(trace)!r}).open("a") as stream: stream.write(" ".join(sys.argv[1:]) + "\\n")\n'
                    f'raise SystemExit(3 if sys.argv[1:] == ["is-active", "runner.service"] and not {runner_active!r} else 0)\n')
                systemctl.chmod(0o755)
                observations = root / 'observations'
                ss = root / 'ss'
                ss.write_text(
                    '#!/usr/bin/python3\nfrom pathlib import Path\n'
                    f'path=Path({str(observations)!r})\n'
                    'count=int(path.read_text()) + 1 if path.exists() else 1\npath.write_text(str(count))\n'
                    f'if {ready!r} and count > 1: print("LISTEN 0 16 127.0.0.1:8787 0.0.0.0:*")\n')
                ss.chmod(0o755)
                state = root / 'state'
                state.write_text('#!/bin/sh\nprintf "RECOVERY_REQUIRED phase=apply\\n"\nexit 10\n')
                state.chmod(0o755)
                variables = {
                    'relay_reviewer_service_name': 'reviewer.service', 'relay_runner_service_name': 'runner.service',
                    'relay_reviewer_activation_marker': str(marker),
                    'relay_reviewer_recovery_off_marker': str(root / 'off'),
                    'relay_production_operation_state_path': str(state),
                    'relay_production_operation_lock_path': str(root / 'lock'),
                    'relay_production_operation_record_path': str(root / 'operation.json'),
                    'relay_install_root': str(root),
                    'relay_reviewer_bind_address': '127.0.0.1', 'relay_reviewer_bind_port': 8787,
                }
                source = Environment(undefined=StrictUndefined).from_string(
                    (ROOT / 'roles/relay_runtime/templates/relay-reviewer-operation-restart.j2').read_text()).render(variables)
                # Map root ownership to the unprivileged fixture owner; keep
                # the actual marker mode, apply-state and flock proof intact.
                source = source.replace('"$marker_owner" == root',
                    '"$marker_owner" == ' + shlex.quote(pwd.getpwuid(os.geteuid()).pw_name))
                source = source.replace('/bin/systemctl', str(systemctl)).replace('ss -H -ltn', str(ss) + ' -H -ltn')
                source = source.replace('/bin/sleep 1', '/bin/sleep 0.01')
                helper = root / 'helper'
                helper.write_text(source)
                result = subprocess.run(['/bin/bash', str(helper)], capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 46 if runner_active and not ready else 0,
                                 result.stdout + result.stderr)
                calls = trace.read_text().splitlines()
                self.assertIn('try-restart reviewer.service', calls)
                self.assertEqual('start runner.service' in calls, runner_active and ready)
                if runner_active:
                    self.assertGreater(int(observations.read_text()), 1)
                else:
                    self.assertFalse(observations.exists())

    def test_explicit_recovery_starts_only_originally_active_bound_services(self):
        import json
        import pwd
        import shlex

        operation = '12345678-1234-1234-1234-123456789abc'
        for production_active, reviewer_active, target_matches in (
            (True, True, True), (False, True, True), (True, False, True), (True, True, False),
        ):
            with self.subTest(production_active=production_active, reviewer_active=reviewer_active,
                              target_matches=target_matches), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                marker = root / 'activation'
                marker.write_text('authorized\n')
                marker.chmod(0o600)
                record = root / 'operation.json'
                record.write_text(json.dumps({'target_head': 'a' * 40}))
                gate = {'operationId': operation, 'phase': 'applying',
                        'target': ('a' if target_matches else 'b') * 40,
                        'previousActive': {'reviewer': {'active': reviewer_active},
                                           'production': {'active': production_active}}}
                admission = root / 'relay-admission'
                admission.write_text('#!/usr/bin/python3\nimport sys,json\n'
                    f'assert sys.argv[1:]==["status","--operation",{operation!r}]\n'
                    f'print({json.dumps(gate)!r})\n')
                admission.chmod(0o755)
                trace, activity = root / 'calls', root / 'activity.json'
                activity.write_text(json.dumps({'reviewer.service': False, 'runner.service': False}))
                systemctl = root / 'systemctl'
                systemctl.write_text('#!/usr/bin/python3\nimport json,sys\nfrom pathlib import Path\n'
                    f'path=Path({str(activity)!r}); state=json.loads(path.read_text())\n'
                    f'with Path({str(trace)!r}).open("a") as stream: stream.write(" ".join(sys.argv[1:])+"\\n")\n'
                    'action,unit=sys.argv[1:]\n'
                    'if action=="is-active": raise SystemExit(0 if state[unit] else 3)\n'
                    'assert action in ["start","try-restart"]\n'
                    'if action=="start": state[unit]=True\n'
                    'path.write_text(json.dumps(state))\n')
                systemctl.chmod(0o755)
                ss = root / 'ss'
                ss.write_text('#!/bin/sh\nprintf "LISTEN 0 16 127.0.0.1:8787 0.0.0.0:*\\n"\n')
                ss.chmod(0o755)
                state = root / 'state'
                state.write_text('#!/bin/sh\nprintf "RECOVERY_REQUIRED phase=apply\\n"\nexit 10\n')
                state.chmod(0o755)
                variables = {'relay_install_root': str(root),
                    'relay_reviewer_service_name': 'reviewer.service', 'relay_runner_service_name': 'runner.service',
                    'relay_reviewer_activation_marker': str(marker), 'relay_reviewer_recovery_off_marker': str(root / 'off'),
                    'relay_production_operation_state_path': str(state),
                    'relay_production_operation_record_path': str(record),
                    'relay_production_operation_lock_path': str(root / 'lock'),
                    'relay_reviewer_bind_address': '127.0.0.1', 'relay_reviewer_bind_port': 8787}
                source = Environment(undefined=StrictUndefined).from_string(
                    (ROOT / 'roles/relay_runtime/templates/relay-reviewer-operation-restart.j2').read_text()).render(variables)
                source = source.replace('"$marker_owner" == root',
                    '"$marker_owner" == ' + shlex.quote(pwd.getpwuid(os.geteuid()).pw_name))
                source = source.replace('$(/usr/bin/id -u)', '0')
                source = source.replace('/bin/systemctl', str(systemctl)).replace('ss -H -ltn', str(ss) + ' -H -ltn')
                source = source.replace('/bin/sleep 1', '/bin/sleep 0.01')
                helper = root / 'helper'
                helper.write_text(source)
                result = subprocess.run(['/bin/bash', str(helper), '--recover-active', operation],
                                        capture_output=True, text=True, timeout=10)
                valid = reviewer_active and target_matches
                self.assertEqual(result.returncode == 0, valid, result.stdout + result.stderr)
                calls = trace.read_text().splitlines()
                self.assertEqual('start reviewer.service' in calls, valid)
                self.assertEqual('start runner.service' in calls, valid and production_active)
                if not valid:
                    self.assertIn('REVIEWER_OPERATION_RESTART_RECOVERY_INTENT_UNPROVEN', result.stderr)
