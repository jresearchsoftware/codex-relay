"""Native-Ansible execution coverage for production recovery classification.

The fixture uses only non-secret markers and a fake read-only service-manager
boundary.  It exercises the real operation-state and recovery-classifier task
files without touching a host service or reading credential contents.
"""

import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
HEAD = "c" * 40


def native_ansible_available():
    return (
        os.name != "nt"
        and shutil.which("ansible-playbook") is not None
        and getattr(os, "geteuid", lambda: 1)() == 0
    )


@unittest.skipUnless(native_ansible_available(), "root-capable native Ansible is required for recovery-classifier execution checks")
class ProductionRecoveryClassifierExecutionTests(unittest.TestCase):
    def _playbook(self, path, variables, tasks):
        path.write_text(
            "---\n"
            "- name: Execute the source-controlled recovery classifier composition\n"
            "  hosts: localhost\n"
            "  connection: local\n"
            "  gather_facts: false\n"
            "  vars:\n"
            f"{textwrap.indent(json.dumps(variables, indent=2), '    ')}\n"
            "  tasks:\n"
            f"{textwrap.indent(tasks, '    ')}\n",
            encoding="utf-8",
        )

    def _run(self, playbook, bin_root):
        environment = os.environ.copy()
        environment.update(
            {
                "ANSIBLE_NOCOLOR": "1",
                "ANSIBLE_LOCALHOST_WARNING": "False",
                "PATH": os.pathsep.join((str(bin_root), environment.get("PATH", ""))),
            }
        )
        return subprocess.run(
            ["ansible-playbook", "-i", "localhost,", "-c", "local", str(playbook)],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

    def _run_classifier(
        self,
        registration_content,
        *,
        registration_kind="regular",
        registration_mode=0o600,
        registration_uid=0,
        registration_gid=0,
    ):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            bin_root = root / "bin"
            bin_root.mkdir()

            systemctl = bin_root / "systemctl"
            systemctl.write_text(
                textwrap.dedent(
                    """
                    #!/usr/bin/env python3
                    import sys

                    if sys.argv[1] == "is-active":
                        print("active")
                    elif sys.argv[1] == "is-enabled":
                        print("enabled")
                    else:
                        raise SystemExit(1)
                    """
                ).lstrip(),
                encoding="utf-8",
            )
            systemctl.chmod(0o755)

            ss = bin_root / "ss"
            ss.write_text(
                "#!/usr/bin/env python3\n"
                "print('LISTEN 0 128 127.0.0.1:8787 0.0.0.0:*')\n",
                encoding="utf-8",
            )
            ss.chmod(0o755)

            operation_record = root / "operation.json"
            operation_record.write_text(
                json.dumps(
                    {
                        "schemaVersion": "1",
                        "state": "RECOVERY_REQUIRED",
                        "phase": "runner-enable",
                        "target_head": HEAD,
                    }
                ),
                encoding="utf-8",
            )
            activation_marker = root / "activation"
            activation_marker.write_text("authorized", encoding="utf-8")
            registration_marker = root / ".runner"
            if registration_kind == "symlink":
                registration_target = root / "registration-target"
                registration_target.write_text(registration_content, encoding="utf-8")
                registration_target.chmod(0o600)
                os.chown(registration_target, 0, 0)
                registration_marker.symlink_to(registration_target)
            else:
                registration_marker.write_text(registration_content, encoding="utf-8")
            credentials_marker = root / ".credentials"
            credentials_marker.write_text("", encoding="utf-8")
            reviewer_unit = root / "reviewer.service"
            reviewer_unit.write_text("unit", encoding="utf-8")
            runner_unit = root / "runner.service"
            runner_unit.write_text("unit", encoding="utf-8")

            for path in (
                operation_record,
                activation_marker,
                credentials_marker,
            ):
                path.chmod(0o600)
                os.chown(path, 0, 0)
            if registration_kind != "symlink":
                registration_marker.chmod(registration_mode)
                os.chown(registration_marker, registration_uid, registration_gid)
            for path in (reviewer_unit, runner_unit):
                path.chmod(0o644)
                os.chown(path, 0, 0)

            work_root = "/tmp/production-test-runner-work"
            variables = {
                "relay_github_repository": "example/relay-consumer",
                "relay_deployment_profile": "production",
                "relay_production_operation_phase": "runner-enable",
                "relay_production_operation_target_head": HEAD,
                "relay_production_operation_record_path": str(operation_record),
                "relay_production_operation_lock_path": str(root / "operation.lock"),
                "relay_production_operation_schema_version": "1",
                "relay_reviewer_service_name": "reviewer-mcp.service",
                "relay_runner_service_name": "relay-runner.service",
                "relay_production_runner_service_name": "relay-runner.service",
                "relay_reviewer_service_unit_path": str(reviewer_unit),
                "relay_runner_service_unit_path": str(runner_unit),
                "relay_reviewer_activation_marker": str(activation_marker),
                "relay_reviewer_recovery_off_marker": str(root / "recovery-off"),
                "relay_runner_registration_marker": str(registration_marker),
                "relay_runner_credentials_marker": str(credentials_marker),
                "relay_reviewer_bind_address": "127.0.0.1",
                "relay_reviewer_bind_port": 8787,
                "relay_runner_user": "root",
                "relay_runner_group": "root",
                "relay_production_runner_name": "production-test-runner",
                "relay_runner_work_root": work_root,
            }
            playbook = root / "classifier.yml"
            tasks = (
                f"- ansible.builtin.include_tasks: {json.dumps((ROOT / 'tasks' / 'production-operation-state.yml').as_posix())}\n"
                f"- ansible.builtin.include_tasks: {json.dumps((ROOT / 'tasks' / 'production-operation-recovery-classify.yml').as_posix())}\n"
                "- name: Verify recovery classification completion\n"
                "  ansible.builtin.assert:\n"
                "    that:\n"
                "      - relay_production_recovery_check_classified | bool\n"
                "      - relay_production_recovery_registration_valid | bool\n"
                "      - relay_production_recovery_phase_classifiable | bool\n"
            )
            self._playbook(playbook, variables, tasks)
            result = self._run(playbook, bin_root)
            operation_mode = stat.S_IMODE(operation_record.stat().st_mode)
            registration_present = registration_marker.exists()
            return result, operation_mode, registration_present

    def test_valid_non_secret_registration_json_is_classified(self):
        registration = json.dumps(
            {
                "gitHubUrl": "https://github.com/example",
                "agentName": "production-test-runner",
                "workFolder": "/tmp/production-test-runner-work",
            }
        )
        result, operation_mode, registration_present = self._run_classifier(registration)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            "PRODUCTION_RECOVERY_CLASSIFICATION=phase=runner-enable",
            result.stdout,
        )
        self.assertEqual(operation_mode, 0o600)
        self.assertTrue(registration_present)

    def test_old_repository_scoped_production_registration_fails_closed(self):
        registration = json.dumps(
            {
                "gitHubUrl": "https://github.com/example/relay-consumer",
                "agentName": "production-test-runner",
                "workFolder": "/tmp/production-test-runner-work",
            }
        )
        result, operation_mode, registration_present = self._run_classifier(registration)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("PRODUCTION_RECOVERY_CLASSIFICATION=phase=runner-enable", result.stdout)
        self.assertEqual(operation_mode, 0o600)
        self.assertTrue(registration_present)

    def test_malformed_registration_json_fails_closed_without_disposition(self):
        result, operation_mode, registration_present = self._run_classifier("{malformed")

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PRODUCTION_RECOVERY_EVIDENCE_MALFORMED", result.stdout + result.stderr)
        self.assertEqual(operation_mode, 0o600)
        self.assertTrue(registration_present)

    def test_untrusted_registration_metadata_fails_before_content_access(self):
        registration = json.dumps(
            {
                "gitHubUrl": "https://github.com/example",
                "agentName": "production-test-runner",
                "workFolder": "/tmp/production-test-runner-work",
            }
        )
        cases = (
            ("symlink", {"registration_kind": "symlink"}),
            ("wrong-owner", {"registration_uid": 65534}),
            ("wrong-group", {"registration_gid": 65534}),
            ("wrong-mode", {"registration_mode": 0o640}),
        )

        for name, options in cases:
            with self.subTest(name=name):
                result, operation_mode, registration_present = self._run_classifier(
                    registration,
                    **options,
                )
                output = result.stdout + result.stderr
                self.assertNotEqual(result.returncode, 0, output)
                self.assertIn("PRODUCTION_RECOVERY_EVIDENCE_UNTRUSTED", output)
                self.assertNotIn(
                    "Validate non-secret runner registration JSON directly from the trusted host file",
                    output,
                )
                self.assertEqual(operation_mode, 0o600)
                self.assertTrue(registration_present)


class ProductionRecoveryClassifierContractTests(unittest.TestCase):
    def test_registration_read_binds_trust_and_content_to_one_file_object(self):
        source = (ROOT / "tasks" / "production-operation-recovery-classify.yml").read_text(
            encoding="utf-8"
        )

        for required in (
            "os.O_NOFOLLOW",
            "metadata = os.fstat(fd)",
            "with os.fdopen(fd, 'rb') as stream:",
            "record = json.loads(raw.decode('utf-8-sig'))",
            "'gitHubUrl': record.get('gitHubUrl')",
            "'agentName': record.get('agentName')",
            "'workFolder': record.get('workFolder')",
        ):
            self.assertIn(required, source)
        self.assertNotIn("with open(sys.argv[1]", source)
        self.assertNotIn("relay_production_recovery_evidence_raw.results[2]", source)
        self.assertNotIn(
            "- {name: registration_marker, path: '{{ relay_runner_registration_marker }}'}\n"
            "  register: relay_production_recovery_evidence_raw",
            source,
        )


if __name__ == "__main__":
    unittest.main()
