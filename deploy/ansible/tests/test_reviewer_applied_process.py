"""Exercise real handler notification and detect a replaced-but-still-running binary."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import yaml

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
            for deferred in (False, True):
                with self.subTest(role=role, deferred=deferred), tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    calls = root / 'calls'
                    helper = root / 'restart'
                    helper.write_text('#!/bin/sh\nprintf called >> "' + str(calls) + '"\n')
                    helper.chmod(0o755)
                    result = self.run_play(root, {
                        'vars': {'relay_deployment_profile': 'production', 'relay_production_operation_record_present': True,
                                 'relay_production_operation_phase': 'apply', 'relay_production_operation_recovery_required': False,
                                 'relay_production_defer_lifecycle': deferred, 'relay_service_effective_enabled': True,
                                 'relay_reviewer_bind_post_activation_authorized': False,
                                 'relay_service_state_management': 'preserve', 'relay_reviewer_release_changed': True,
                                 'relay_reviewer_operation_restart_path': str(helper)},
                        'tasks': [{'ansible.builtin.command': '/bin/true', 'changed_when': True, 'notify': topic}],
                        'handlers': yaml.safe_load((ROOT / f'roles/{role}/handlers/main.yml').read_text()),
                    })
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertEqual(calls.read_text() if calls.exists() else '', '' if deferred else 'called')

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
