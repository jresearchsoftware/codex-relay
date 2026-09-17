"""Execution-level checks for the inspect/begin/clear operation-state boundary.

The tests invoke the source-controlled Ansible task files against temporary
state only.  They do not run a production role, systemd transition, or
credential-bearing helper.
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
HEAD = "d" * 40


def localhost_ansible_available():
    return os.name != "nt" and shutil.which("ansible-playbook") is not None


def privileged_localhost_ansible_available():
    return localhost_ansible_available() and getattr(os, "geteuid", lambda: 1)() == 0


class ProductionOperationStateExecutionTests(unittest.TestCase):
    def _variables(self, directory, *, phase="apply", head=HEAD, recovery_required=False):
        directory = Path(directory)
        return {
            "relay_deployment_profile": "production",
            "relay_production_operation_phase": phase,
            "relay_production_operation_target_head": head,
            "relay_production_operation_recovery_required": recovery_required,
            "relay_production_operation_active_phase": phase,
            "relay_production_operation_active_head": head,
            "relay_production_operation_record_path": str(directory / "operation.json"),
            "relay_production_operation_lock_path": str(directory / "operation.lock"),
            "relay_production_operation_schema_version": "1",
        }

    def _playbook(self, path, variables, tasks):
        path.write_text(
            "---\n"
            "- name: Execute the source-controlled operation-state composition\n"
            "  hosts: localhost\n"
            "  connection: local\n"
            "  gather_facts: false\n"
            "  vars:\n"
            f"{textwrap.indent(json.dumps(variables, indent=2), '    ')}\n"
            "  tasks:\n"
            f"{textwrap.indent(tasks, '    ')}\n",
            encoding="utf-8",
        )

    def _run(self, playbook, *arguments):
        environment = os.environ.copy()
        environment.update({
            "ANSIBLE_NOCOLOR": "1",
            "ANSIBLE_LOCALHOST_WARNING": "False",
        })
        return subprocess.run(
            ["ansible-playbook", "-i", "localhost,", "-c", "local", *arguments, str(playbook)],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

    @unittest.skipUnless(localhost_ansible_available(), "native Ansible is required for operation-state inspect checks")
    def test_inspect_without_record_is_read_only_and_supplies_begin_facts(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            include_path = (ROOT / "tasks" / "production-operation-state.yml").as_posix()
            playbook = directory / "inspect.yml"
            variables = self._variables(directory, phase="apply")
            self._playbook(
                playbook,
                variables,
                f"- ansible.builtin.include_tasks: {json.dumps(include_path)}\n"
                "- name: Verify the inspected fresh-host facts\n"
                "  ansible.builtin.assert:\n"
                "    that:\n"
                "      - not relay_production_operation_recovery_required | bool\n"
                "      - not relay_production_operation_record_present | bool\n"
                "      - relay_production_operation_active_phase == 'apply'\n"
                f"      - relay_production_operation_active_head == '{HEAD}'",
            )
            result = self._run(playbook)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse((directory / "operation.json").exists())

    @unittest.skipUnless(privileged_localhost_ansible_available(), "root-capable native Ansible is required for valid-record inspect checks")
    def test_valid_existing_record_is_inspected_read_only_with_stale_phase_and_head_facts(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            old_head = "a" * 40
            requested_head = "b" * 40
            original = {
                "schemaVersion": "1",
                "state": "RECOVERY_REQUIRED",
                "phase": "activate",
                "target_head": old_head,
            }
            record = directory / "operation.json"
            record.write_text(json.dumps(original), encoding="utf-8")
            os.chmod(record, 0o600)
            os.chown(record, 0, 0)

            playbook = directory / "stale-inspect.yml"
            variables = self._variables(
                directory,
                phase="check",
                head=requested_head,
            )
            include_path = (ROOT / "tasks" / "production-operation-state.yml").as_posix()
            self._playbook(
                playbook,
                variables,
                f"- ansible.builtin.include_tasks: {json.dumps(include_path)}\n"
                "- name: Verify trusted stale-record inspection facts\n"
                "  ansible.builtin.assert:\n"
                "    that:\n"
                "      - relay_production_operation_recovery_required | bool\n"
                "      - relay_production_operation_record_present | bool\n"
                "      - relay_production_operation_recovery_phase == 'activate'\n"
                "      - relay_production_operation_recovery_target_head == 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'\n"
                "      - not relay_production_operation_recovery_matching | bool\n"
                "      - relay_production_operation_active_phase == 'activate'\n"
                "      - relay_production_operation_active_head == 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'",
            )
            result = self._run(playbook)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(record.read_text(encoding="utf-8")), original)
            self.assertEqual(stat.S_IMODE(record.stat().st_mode), 0o600)

    @unittest.skipUnless(privileged_localhost_ansible_available(), "root-capable native Ansible is required for malformed-record checks")
    def test_malformed_record_fails_with_controlled_unsafe_evidence(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            record = directory / "operation.json"
            record.write_text('{"state":', encoding="utf-8")
            os.chmod(record, 0o600)
            if os.geteuid() == 0:
                os.chown(record, 0, 0)

            playbook = directory / "malformed.yml"
            self._playbook(
                playbook,
                self._variables(directory),
                f"- ansible.builtin.include_tasks: {json.dumps((ROOT / 'tasks' / 'production-operation-state.yml').as_posix())}",
            )
            result = self._run(playbook)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PRODUCTION_OPERATION_STATE_UNSAFE_RECORD", result.stdout + result.stderr)

    @unittest.skipUnless(localhost_ansible_available(), "native Ansible is required for operation-state execution checks")
    def test_pre_mutation_gate_failure_and_check_mode_create_no_record(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            record = directory / "operation.json"

            failed_playbook = directory / "pre-gate-failure.yml"
            self._playbook(
                failed_playbook,
                self._variables(directory),
                "- name: Fail before the begin boundary\n"
                "  ansible.builtin.assert:\n"
                "    that: false\n"
                "    fail_msg: PRE_MUTATION_GATE_FAILED\n"
                f"- ansible.builtin.include_tasks: {json.dumps((ROOT / 'tasks' / 'production-operation-state-begin.yml').as_posix())}",
            )
            result = self._run(failed_playbook)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse(record.exists())

            check_playbook = directory / "check-mode.yml"
            self._playbook(
                check_playbook,
                self._variables(directory),
                f"- ansible.builtin.include_tasks: {json.dumps((ROOT / 'tasks' / 'production-operation-state-begin.yml').as_posix())}",
            )
            result = self._run(check_playbook, "--check")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PRODUCTION_OPERATION_CHECK_MODE_PLAN=", result.stdout)
            self.assertFalse(record.exists())

    @unittest.skipUnless(privileged_localhost_ansible_available(), "root-capable native Ansible is required for durable record execution checks")
    def test_interruption_stages_leave_exact_record_until_locked_clear(self):
        stages = {
            "after_begin": "- name: Interrupt after begin\n  ansible.builtin.fail:\n    msg: INTERRUPTED_AFTER_BEGIN",
            "after_first_mutation": (
                "- name: Perform the first protected test mutation\n"
                "  ansible.builtin.shell: printf mutation > "
                "'{{ relay_production_operation_record_path }}.mutation'\n"
                "- name: Interrupt after first mutation\n"
                "  ansible.builtin.fail:\n"
                "    msg: INTERRUPTED_AFTER_FIRST_MUTATION"
            ),
            "before_final_validation": (
                "- name: Perform the protected test mutation\n"
                "  ansible.builtin.shell: printf mutation > "
                "'{{ relay_production_operation_record_path }}.mutation'\n"
                "- name: Mark final validation as not yet reached\n"
                "  ansible.builtin.shell: printf pending > "
                "'{{ relay_production_operation_record_path }}.validation'\n"
                "- name: Interrupt before final validation\n"
                "  ansible.builtin.fail:\n"
                "    msg: INTERRUPTED_BEFORE_FINAL_VALIDATION"
            ),
            "after_validation_before_clear": (
                "- name: Perform the protected test mutation\n"
                "  ansible.builtin.shell: printf mutation > "
                "'{{ relay_production_operation_record_path }}.mutation'\n"
                "- name: Complete final validation without clearing evidence\n"
                "  ansible.builtin.assert:\n"
                "    that: true\n"
                "- name: Interrupt after final validation before clear\n"
                "  ansible.builtin.fail:\n"
                "    msg: INTERRUPTED_BEFORE_CLEAR"
            ),
        }

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            for stage, stage_tasks in stages.items():
                directory = root / stage
                directory.mkdir()
                playbook = directory / "interruption.yml"
                tasks = (
                    f"- ansible.builtin.include_tasks: {json.dumps((ROOT / 'tasks' / 'production-operation-state-begin.yml').as_posix())}\n"
                    + stage_tasks
                )
                self._playbook(playbook, self._variables(directory), tasks)
                result = self._run(playbook)
                self.assertNotEqual(result.returncode, 0, f"{stage}: {result.stdout}\n{result.stderr}")

                record = directory / "operation.json"
                self.assertTrue(record.exists(), f"{stage}:\n{result.stdout}\n{result.stderr}")
                metadata = record.stat()
                self.assertEqual(stat.S_IMODE(metadata.st_mode), 0o600, stage)
                self.assertEqual(
                    json.loads(record.read_text(encoding="utf-8")),
                    {
                        "schemaVersion": "1",
                        "state": "RECOVERY_REQUIRED",
                        "phase": "apply",
                        "target_head": HEAD,
                    },
                    stage,
                )

                if stage == "after_validation_before_clear":
                    clear_playbook = directory / "clear.yml"
                    clear_include = (ROOT / "tasks" / "production-operation-state-clear.yml").as_posix()
                    clear_tasks = f"- ansible.builtin.include_tasks: {json.dumps(clear_include)}"
                    variables = self._variables(directory)
                    variables.update({
                        "relay_production_operation_clear_phase": "apply",
                        "relay_production_operation_clear_head": HEAD,
                    })
                    self._playbook(clear_playbook, variables, clear_tasks)
                    result = self._run(clear_playbook)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertFalse(record.exists())

    @unittest.skipUnless(privileged_localhost_ansible_available(), "root-capable native Ansible is required for exact-record retention checks")
    def test_matching_record_is_retained_and_mismatch_cannot_overwrite_it(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            record = directory / "operation.json"
            original = {
                "schemaVersion": "1",
                "state": "RECOVERY_REQUIRED",
                "phase": "activate",
                "target_head": HEAD,
            }
            record.write_text(json.dumps(original), encoding="utf-8")
            os.chmod(record, 0o600)
            if os.geteuid() == 0:
                os.chown(record, 0, 0)

            matching_playbook = directory / "matching.yml"
            matching_vars = self._variables(
                directory,
                phase="activate",
                head=HEAD,
                recovery_required=True,
            )
            self._playbook(
                matching_playbook,
                matching_vars,
                f"- ansible.builtin.include_tasks: {json.dumps((ROOT / 'tasks' / 'production-operation-state-begin.yml').as_posix())}",
            )
            result = self._run(matching_playbook)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(record.read_text(encoding="utf-8")), original)

            mismatch_playbook = directory / "mismatch.yml"
            mismatch_vars = self._variables(
                directory,
                phase="runner-enable",
                head="e" * 40,
                recovery_required=True,
            )
            self._playbook(
                mismatch_playbook,
                mismatch_vars,
                f"- ansible.builtin.include_tasks: {json.dumps((ROOT / 'tasks' / 'production-operation-state-begin.yml').as_posix())}",
            )
            result = self._run(mismatch_playbook)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PRODUCTION_OPERATION_BEGIN_RECORD_CHANGED", result.stdout + result.stderr)
            self.assertEqual(json.loads(record.read_text(encoding="utf-8")), original)


    @unittest.skipUnless(privileged_localhost_ansible_available(), "root-capable Ansible required")
    def test_locked_clear_alone_rejects_changed_unsafe_and_busy_evidence(self):
        import fcntl
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            variables = self._variables(root)
            variables.update(relay_production_operation_clear_phase="apply", relay_production_operation_clear_head=HEAD)
            play = root / "clear.yml"
            self._playbook(play, variables, f"- ansible.builtin.include_tasks: {json.dumps(str(ROOT / 'tasks/production-operation-state-clear.yml'))}")
            record = root / "operation.json"
            expected = {"schemaVersion": "1", "state": "RECOVERY_REQUIRED", "phase": "apply", "target_head": HEAD}
            for case in ["wrong-head", "unsafe-mode", "busy-lock"]:
                value = {**expected, "target_head": "e" * 40} if case == "wrong-head" else expected
                record.write_text(json.dumps(value))
                record.chmod(0o644 if case == "unsafe-mode" else 0o600)
                with (root / "operation.lock").open("w") as lock:
                    if case == "busy-lock":
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    result = self._run(play)
                self.assertNotEqual(result.returncode, 0, case)
                self.assertEqual(json.loads(record.read_text()), value, case)
                self.assertNotIn("PRODUCTION_RECONCILIATION_STATE=STABLE", result.stdout)


if __name__ == "__main__":
    unittest.main()
