"""Small localhost composition regression for the production lifecycle.

The probe executes the source-controlled final validation task through
ansible-playbook with a secret-free localhost fact set.  The surrounding
assertions keep the operation-state creation, recovery reset, role/handler,
final-validation, and evidence-clear ordering tied to the real entrypoints.
It is intentionally not a production-host integration framework.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
HEAD = "c" * 40


def localhost_ansible_available():
    return os.name != "nt" and shutil.which("ansible-playbook") is not None


def _regular_root_stat():
    return {"exists": True, "isreg": True, "islnk": False, "pw_name": "root", "gr_name": "root", "mode": "0600"}


def _writer_wrapper_stat():
    return {"exists": True, "isreg": True, "islnk": False, "pw_name": "root", "gr_name": "root", "mode": "0750"}


def _writer_helper_stat():
    return {"exists": True, "isreg": True, "islnk": False, "pw_name": "root", "gr_name": "relay", "mode": "0644"}


def _final_facts(
    *,
    activation_marker=True,
    recovery_off_marker=True,
    reviewer_state=("inactive", "disabled"),
    runner_state=("inactive", "disabled"),
    initial_runner_state=None,
    recovery_phase="apply",
    reviewer_listener=None,
    restore_only=False,
    runner_unit_exists=True,
    writer_entrypoint=None,
):
    regular = _regular_root_stat()
    activation_stat = regular if activation_marker else {"exists": False}
    recovery_off_stat = regular if recovery_off_marker else {"exists": False}
    runner_unit_stat = regular if runner_unit_exists else {"exists": False}
    if reviewer_listener is None:
        reviewer_listener = "127.0.0.1:8787" if reviewer_state[0] == "active" else ""
    return {
        "relay_deployment_profile": "production",
        "relay_production_operation_phase": "apply",
        "relay_production_operation_target_head": HEAD,
        "relay_production_operation_recovery_phase": recovery_phase,
        "relay_production_reviewer_restore_only": restore_only,
        "relay_install_root": "/opt/codex-relay",
        "relay_release_root": "/opt/codex-relay/releases",
        "relay_reviewer_bind_address": "127.0.0.1",
        "relay_production_final_paths": {
            "results": [
                {"stat": {"exists": True, "islnk": True, "lnk_source": f"/opt/codex-relay/releases/{HEAD}", "pw_name": "root"}},
                {"stat": regular},
                {"stat": regular},
                {"stat": regular},
                {"stat": regular},
                {"stat": runner_unit_stat},
                {"stat": activation_stat},
                {"stat": recovery_off_stat},
                {"stat": _writer_wrapper_stat()},
                {"stat": _writer_helper_stat()},
            ]
        },
        "relay_production_final_manifest": {"schemaVersion": "1.0", "commit": HEAD},
        "relay_production_final_writer_entrypoint": writer_entrypoint
        or "\n".join(
            (
                "#!/bin/sh",
                "set -eu",
                'test "$#" -eq 0 || exit 40',
                "/usr/bin/env -i PATH=/usr/bin:/bin",
                "RELAY_WRITER_CLAIM_ROOT=/var/lib/codex-relay/writer-claims",
                "/usr/bin/node '/opt/codex-relay/current/reviewed-source/controller/src/privileged-writer-helper.mjs'",
            )
        ),
        "relay_production_final_services": {
            "results": [
                {"stdout": reviewer_state[0]},
                {"stdout": reviewer_state[1]},
                {"stdout": runner_state[0]},
                {"stdout": runner_state[1]},
            ]
        },
        "relay_production_final_listener": {"stdout": reviewer_listener},
        **(
            {
                "relay_runner_preserved_initial_active_state": {"stdout": initial_runner_state[0]},
                "relay_runner_preserved_initial_enabled_state": {"stdout": initial_runner_state[1]},
            }
            if initial_runner_state is not None
            else {}
        ),
    }


class ProductionComposedLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.site = (ROOT / "site.yml").read_text(encoding="utf-8")
        self.bind_state = (ROOT / "tasks" / "production-reviewer-bind-state.yml").read_text(encoding="utf-8")
        self.activation = (ROOT / "relay-reviewer-activation.yml").read_text(encoding="utf-8")
        self.runner_enable = (ROOT / "relay-production-runner-enable.yml").read_text(encoding="utf-8")
        self.operation_state = (ROOT / "tasks" / "production-operation-state.yml").read_text(encoding="utf-8")
        self.operation_begin = (ROOT / "tasks" / "production-operation-state-begin.yml").read_text(encoding="utf-8")
        self.recovery_classify = (ROOT / "tasks" / "production-operation-recovery-classify.yml").read_text(encoding="utf-8")
        self.recovery_reset = (ROOT / "tasks" / "production-operation-recovery-reset.yml").read_text(encoding="utf-8")
        self.final_validation = (ROOT / "tasks" / "production-final-validation.yml").read_text(encoding="utf-8")
        self.operation_clear = (ROOT / "tasks" / "production-operation-state-clear.yml").read_text(encoding="utf-8")
        self.runtime_handlers = (ROOT / "roles" / "relay_runtime" / "handlers" / "main.yml").read_text(encoding="utf-8")
        self.bind_handlers = (ROOT / "roles" / "relay_reviewer_bind" / "handlers" / "main.yml").read_text(encoding="utf-8")
        self.reviewer_unit = (ROOT / "roles" / "relay_runtime" / "templates" / "reviewer-mcp.service.j2").read_text(encoding="utf-8")
        self.runner_unit = (ROOT / "roles" / "relay_runner" / "templates" / "relay-runner.service.j2").read_text(encoding="utf-8")
        self.reviewer_stop_runner = (ROOT / "roles" / "relay_runtime" / "templates" / "relay-reviewer-stop-runner.j2").read_text(encoding="utf-8")

    def _run_final_validation(self, recovery_required, *, expect_success=True, **facts_overrides):
        if not localhost_ansible_available():
            self.skipTest("native Ansible is required for the composed localhost regression")

        facts = _final_facts(**facts_overrides)
        facts["relay_production_operation_recovery_required"] = recovery_required
        with tempfile.TemporaryDirectory() as temporary_directory:
            playbook_path = Path(temporary_directory) / "composed-final-validation.yml"
            include_path = (ROOT / "tasks" / "production-final-validation.yml").as_posix()
            variables = textwrap.indent(json.dumps(facts, indent=2), "    ")
            playbook_path.write_text(
                "---\n"
                "- name: Execute the source-controlled final validation composition\n"
                "  hosts: localhost\n"
                "  connection: local\n"
                "  gather_facts: false\n"
                "  vars:\n"
                f"{variables}\n"
                "  tasks:\n"
                f"    - ansible.builtin.include_tasks: '{include_path}'\n",
                encoding="utf-8",
            )
            environment = os.environ.copy()
            environment.update({"ANSIBLE_NOCOLOR": "1", "ANSIBLE_LOCALHOST_WARNING": "False"})
            result = subprocess.run(
                ["ansible-playbook", "-i", "localhost,", "-c", "local", str(playbook_path)],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            if expect_success and result.returncode != 0:
                self.fail(
                    f"source-controlled final validation rejected recovery_required={recovery_required}:\n"
                    f"stdout={result.stdout}\nstderr={result.stderr}"
                )
            if not expect_success and result.returncode == 0:
                self.fail(
                    f"source-controlled final validation unexpectedly accepted recovery_required={recovery_required}:\n"
                    f"stdout={result.stdout}\nstderr={result.stderr}"
                )

    def test_recovery_stable_off_then_second_apply_executes_real_final_assert(self):
        # The first invocation still carries the recovery fact; the second
        # ordinary apply has no record but must accept the retained off-marker.
        self._run_final_validation(recovery_required=True)
        self._run_final_validation(recovery_required=False)

    def test_fresh_pre_activation_recovery_with_no_authorization_marker_is_admitted(self):
        self._run_final_validation(
            recovery_required=True,
            activation_marker=False,
            recovery_off_marker=False,
        )

    def test_recovery_cannot_clear_evidence_with_mismatched_pre_activation_marker(self):
        self._run_final_validation(
            recovery_required=True,
            activation_marker=False,
            recovery_off_marker=True,
            expect_success=False,
        )

    def test_final_gate_rejects_loss_of_previously_active_authorized_runner(self):
        self._run_final_validation(
            recovery_required=False,
            runner_state=("inactive", "disabled"),
            initial_runner_state=("active", "enabled"),
            recovery_off_marker=False,
            expect_success=False,
        )

        self._run_final_validation(
            recovery_required=False,
            runner_state=("active", "enabled"),
            initial_runner_state=("active", "enabled"),
            recovery_off_marker=False,
        )

    def test_ordinary_apply_recovery_preserves_authorized_reviewer_and_runner(self):
        self._run_final_validation(
            recovery_required=True,
            reviewer_state=("active", "enabled"),
            runner_state=("active", "enabled"),
            initial_runner_state=("active", "enabled"),
            recovery_off_marker=False,
        )

        self._run_final_validation(
            recovery_required=True,
            reviewer_state=("active", "enabled"),
            runner_state=("inactive", "disabled"),
            initial_runner_state=("active", "enabled"),
            recovery_off_marker=False,
            expect_success=False,
        )

    def test_final_gate_rejects_active_reviewer_without_expected_listener(self):
        self._run_final_validation(
            recovery_required=False,
            reviewer_state=("active", "enabled"),
            recovery_off_marker=False,
            reviewer_listener="",
            expect_success=False,
        )

    def test_final_gate_requires_the_production_runner_unit_even_with_old_restore_flag(self):
        self._run_final_validation(
            recovery_required=False,
            reviewer_state=("active", "enabled"),
            runner_state=("unknown", "unknown"),
            recovery_off_marker=False,
            restore_only=True,
            runner_unit_exists=False,
            expect_success=False,
        )

    def test_final_gate_rejects_stale_writer_release_binding(self):
        self._run_final_validation(
            recovery_required=False,
            restore_only=True,
            writer_entrypoint=(
                "#!/bin/sh\n"
                "set -eu\n"
                'test "$#" -eq 0 || exit 40\n'
                "/usr/bin/env -i\n"
                "/usr/bin/node '/opt/codex-relay/releases/" + "b" * 40 + "/reviewed-source/controller/src/privileged-writer-helper.mjs'\n"
            ),
            expect_success=False,
        )

    def test_ordinary_production_scope_includes_all_installed_components(self):
        play = yaml.safe_load(self.site)[1]
        roles = {entry['role']: entry for entry in play['roles']}
        for name in ('relay_codex_runtime', 'relay_controller', 'relay_base', 'relay_runtime', 'relay_artifacts'):
            self.assertNotIn('when', roles[name])
        primary = next(task for task in play['post_tasks']
                       if task.get('ansible.builtin.include_role') == {'name': 'relay_runner'})
        self.assertNotIn('when', primary)
        self.assertIn('tasks/production-general-runner.yml', self.site)
        self.assertNotIn('relay_production_reviewer_restore_only', self.site)

    @unittest.skipUnless(localhost_ansible_available(), "native Ansible is required for the composed localhost regression")
    def test_entrypoint_order_keeps_record_reset_roles_validation_and_clear_composed(self):
        self.assertLess(self.site.index("tasks/production-operation-state.yml"), self.site.index("role: relay_runtime"))
        self.assertLess(self.site.index("tasks/production-operation-state-begin.yml"), self.site.index("role: relay_runtime"))
        self.assertLess(self.site.index("name: relay_docker_network_gateway"), self.site.index("tasks/production-operation-recovery-classify.yml"))
        self.assertLess(self.site.index("tasks/production-operation-recovery-classify.yml"), self.site.index("role: relay_runtime"))
        self.assertLess(self.site.index("tasks/production-reviewer-bind-state.yml"), self.site.index("Flush relay handlers"))
        identity_include = "roles/relay_artifacts/tasks/resolve-identities.yml"
        self.assertLess(self.activation.index(identity_include), self.activation.index("tasks/production-reviewer-bind-state.yml"))
        self.assertLess(self.runner_enable.index(identity_include), self.runner_enable.index("tasks/production-reviewer-bind-state.yml"))
        self.assertLess(self.activation.index("tasks/production-operation-state-begin.yml"), self.activation.index("tasks/production-reviewer-bind-state.yml"))
        self.assertLess(self.runner_enable.index("tasks/production-operation-state-begin.yml"), self.runner_enable.index("tasks/production-reviewer-bind-state.yml"))
        self.assertNotIn("tasks/production-operation-recovery-reset.yml", self.site)
        self.assertLess(self.site.index("tasks/production-final-validation.yml"), self.site.index("tasks/production-operation-state-clear.yml"))

        for entrypoint, transition, clear_marker, clear_phase in (
            (
                self.activation,
                "Enable and start Reviewer through the explicit activation transition window",
                "Clear activation recovery evidence after complete validation",
                "activate",
            ),
            (
                self.runner_enable,
                "Enable only the already installed registered production runner",
                "Clear runner-enable recovery evidence after complete validation",
                "runner-enable",
            ),
        ):
            self.assertLess(entrypoint.index("tasks/production-operation-state.yml"), entrypoint.index(transition))
            self.assertLess(entrypoint.index("tasks/production-operation-state-begin.yml"), entrypoint.index(transition))
            self.assertLess(entrypoint.index(transition), entrypoint.index(clear_marker))
            self.assertIn(clear_phase, entrypoint)
            self.assertIn("tasks/production-operation-recovery-reset.yml", entrypoint)

        self.assertIn("Require a matching phase and exact head for recovery", self.operation_state)
        self.assertIn("Begin or retain the exact production operation", self.operation_begin)
        self.assertIn("PRODUCTION_RECOVERY_CLASSIFICATION", self.recovery_classify)
        self.assertIn("Preserve the runner and leave Reviewer for activation replay", self.recovery_reset)
        self.assertIn("Stop and disable only the relay-owned runner", self.recovery_reset)
        self.assertNotIn("systemctl stop '{{ relay_reviewer_service_name }}'", self.recovery_reset)
        self.assertNotIn("systemctl disable '{{ relay_reviewer_service_name }}'", self.recovery_reset)
        self.assertNotIn("relay_production_operation_recovery_phase == 'apply'", self.recovery_reset)
        self.assertIn("requires-activation", self.recovery_reset)
        self.assertIn("REVIEWER_ACTIVATION_MARKER_INVALID", self.recovery_reset)
        self.assertIn("true pre-activation baseline", self.recovery_reset)
        self.assertIn("PRODUCTION_RECONCILIATION_FINAL_VALIDATION_FAILED", self.final_validation)
        self.assertIn("relay_production_final_listener.stdout", self.final_validation)
        self.assertIn("PRODUCTION_RECOVERY_EVIDENCE_MALFORMED", self.recovery_classify)
        self.assertIn("PRODUCTION_OPERATION_STATE_UNSAFE_RECORD", self.operation_state)
        self.assertIn("relay_production_final_pre_activation_recovery_baseline", self.final_validation)
        self.assertIn("Clear production recovery evidence under the transition lock", self.operation_clear)
        self.assertIn("PRODUCTION_OPERATION_STATE_CLEAR_LOCK_BUSY", self.operation_clear)
        self.assertIn("os.unlink(path)", self.operation_clear)
        self.assertIn("try-restart", self.runtime_handlers)
        self.assertIn("try-restart", self.bind_handlers)
        self.assertIn("relay_reviewer_bind_address", self.bind_state)
        self.assertIn("REVIEWER_BIND_STATE_STALE_OR_INVALID", self.bind_state)
        self.assertIn("REVIEWER_BIND_HELPER_STATE_STALE_OR_INVALID", self.bind_state)

    def test_reviewer_readiness_loss_stops_runner_without_start_dependency(self):
        self.assertIn("ExecStopPost=+{{ relay_reviewer_stop_runner_path }}", self.reviewer_unit)
        self.assertIn("SERVICE_RESULT", self.reviewer_stop_runner)
        self.assertIn("/bin/systemctl stop '{{ relay_runner_service_name }}'", self.reviewer_stop_runner)
        self.assertIn("PartOf={{ relay_reviewer_service_name }}", self.runner_unit)
        self.assertNotIn("Requires={{ relay_reviewer_service_name }}", self.runner_unit)
        self.assertNotIn("BindsTo={{ relay_reviewer_service_name }}", self.runner_unit)

    @unittest.skipUnless(localhost_ansible_available(), "native Ansible is required for recovery classification composition")
    def test_recovery_classifier_composes_real_tasks_for_expected_partial_states(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            bin_root = root / "bin"
            bin_root.mkdir()
            (bin_root / "systemctl").write_text(
                "#!/bin/sh\n"
                "case \"$1 $2\" in\n"
                "  'is-active reviewer-mcp.service') state=\"${FIXTURE_REVIEWER_ACTIVE:-inactive}\"; echo \"$state\"; [ \"$state\" = active ] && exit 0 || exit 3;;\n"
                "  'is-enabled reviewer-mcp.service') state=\"${FIXTURE_REVIEWER_ENABLED:-disabled}\"; echo \"$state\"; [ \"$state\" != disabled ] && exit 0 || exit 1;;\n"
                "  'is-active relay-runner.service') echo inactive; exit 3;;\n"
                "  'is-enabled relay-runner.service') echo disabled; exit 1;;\n"
                "  *) exit 1;;\n"
                "esac\n",
                encoding="utf-8",
            )
            (bin_root / "ss").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            for executable in (bin_root / "systemctl", bin_root / "ss"):
                executable.chmod(0o755)

            include_path = (ROOT / "tasks" / "production-operation-recovery-classify.yml").as_posix()
            for phase, expected_scope, reviewer_active, reviewer_enabled, should_pass in (
                ("activate", "reviewer-only", "inactive", "disabled", True),
                ("apply", "preserve-reviewer-and-runner", "inactive", "disabled", True),
                ("activate", "reviewer-only", "inactive", "enabled", True),
                ("activate", "reviewer-only", "failed", "enabled-runtime", True),
                ("apply", "preserve-reviewer-and-runner", "inactive", "enabled", False),
            ):
                playbook_path = root / f"classification-{phase}.yml"
                playbook_path.write_text(
                    "---\n"
                    "- name: Execute the source-controlled recovery classifier\n"
                    "  hosts: localhost\n"
                    "  connection: local\n"
                    "  gather_facts: false\n"
                    "  vars:\n"
                    "    relay_production_operation_recovery_phase: " + phase + "\n"
                    "    relay_production_operation_recovery_target_head: " + HEAD + "\n"
                    "    relay_reviewer_service_name: reviewer-mcp.service\n"
                    "    relay_runner_service_name: relay-runner.service\n"
                    f"    relay_reviewer_service_unit_path: '{(root / 'reviewer.service').as_posix()}'\n"
                    f"    relay_runner_service_unit_path: '{(root / 'runner.service').as_posix()}'\n"
                    f"    relay_reviewer_activation_marker: '{(root / 'activation').as_posix()}'\n"
                    f"    relay_reviewer_recovery_off_marker: '{(root / 'recovery-off').as_posix()}'\n"
                    f"    relay_runner_registration_marker: '{(root / 'runner').as_posix()}'\n"
                    f"    relay_runner_credentials_marker: '{(root / 'credentials').as_posix()}'\n"
                    "    relay_reviewer_bind_address: 127.0.0.1\n"
                    "    relay_runner_user: runner\n"
                    "    relay_runner_group: runner\n"
                    "    relay_production_runner_name: relay-production-relay\n"
                    f"    relay_runner_work_root: '{(root / 'runner-work').as_posix()}'\n"
                    "  tasks:\n"
                    f"    - ansible.builtin.include_tasks: '{include_path}'\n",
                    encoding="utf-8",
                )
                environment = os.environ.copy()
                environment.update({
                    "PATH": os.pathsep.join((str(bin_root), environment.get("PATH", ""))),
                    "ANSIBLE_NOCOLOR": "1",
                    "ANSIBLE_LOCALHOST_WARNING": "False",
                    "FIXTURE_REVIEWER_ACTIVE": reviewer_active,
                    "FIXTURE_REVIEWER_ENABLED": reviewer_enabled,
                })
                result = subprocess.run(
                    ["ansible-playbook", "-i", "localhost,", "-c", "local", str(playbook_path)],
                    cwd=ROOT,
                    env=environment,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if should_pass:
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("PRODUCTION_RECOVERY_CLASSIFICATION=", result.stdout)
                    self.assertIn(f"planned_scope={expected_scope}", result.stdout)
                    self.assertIn(
                        f"partial_activation={reviewer_active in {'inactive', 'failed'} and reviewer_enabled in {'enabled', 'enabled-runtime'}}",
                        result.stdout,
                    )
                    self.assertNotIn("REVIEWER_SERVICE_STATE_AMBIGUOUS", result.stdout)
                else:
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("PRODUCTION_RECOVERY_CLASSIFICATION_BLOCKED", result.stdout + result.stderr)

    @unittest.skipUnless(localhost_ansible_available(), "native Ansible is required for unsafe recovery classification composition")
    def test_recovery_classifier_blocks_active_runner_without_registration_evidence(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            bin_root = root / "bin"
            bin_root.mkdir()
            (bin_root / "systemctl").write_text(
                "#!/bin/sh\n"
                "case \"$1\" in\n"
                "  is-active) echo active; exit 0;;\n"
                "  is-enabled) echo enabled; exit 0;;\n"
                "  *) exit 1;;\n"
                "esac\n",
                encoding="utf-8",
            )
            (bin_root / "ss").write_text(
                "#!/bin/sh\n"
                "echo 'LISTEN 0 128 127.0.0.1:8787 0.0.0.0:*'\n",
                encoding="utf-8",
            )
            for executable in (bin_root / "systemctl", bin_root / "ss"):
                executable.chmod(0o755)

            include_path = (ROOT / "tasks" / "production-operation-recovery-classify.yml").as_posix()
            playbook_path = root / "unsafe-classification.yml"
            playbook_path.write_text(
                "---\n"
                "- name: Execute the source-controlled unsafe recovery classifier\n"
                "  hosts: localhost\n"
                "  connection: local\n"
                "  gather_facts: false\n"
                "  vars:\n"
                "    relay_production_operation_recovery_phase: apply\n"
                f"    relay_production_operation_recovery_target_head: {HEAD}\n"
                "    relay_reviewer_service_name: reviewer-mcp.service\n"
                "    relay_runner_service_name: relay-runner.service\n"
                f"    relay_reviewer_service_unit_path: '{(root / 'reviewer.service').as_posix()}'\n"
                f"    relay_runner_service_unit_path: '{(root / 'runner.service').as_posix()}'\n"
                f"    relay_reviewer_activation_marker: '{(root / 'activation').as_posix()}'\n"
                f"    relay_reviewer_recovery_off_marker: '{(root / 'recovery-off').as_posix()}'\n"
                f"    relay_runner_registration_marker: '{(root / 'runner').as_posix()}'\n"
                f"    relay_runner_credentials_marker: '{(root / 'credentials').as_posix()}'\n"
                "    relay_reviewer_bind_address: 127.0.0.1\n"
                "    relay_runner_user: runner\n"
                "    relay_runner_group: runner\n"
                "    relay_production_runner_name: relay-production-relay\n"
                f"    relay_runner_work_root: '{(root / 'runner-work').as_posix()}'\n"
                "  tasks:\n"
                f"    - ansible.builtin.include_tasks: '{include_path}'\n",
                encoding="utf-8",
            )
            environment = os.environ.copy()
            environment.update({
                "PATH": os.pathsep.join((str(bin_root), environment.get("PATH", ""))),
                "ANSIBLE_NOCOLOR": "1",
                "ANSIBLE_LOCALHOST_WARNING": "False",
            })
            result = subprocess.run(
                ["ansible-playbook", "-i", "localhost,", "-c", "local", str(playbook_path)],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PRODUCTION_RECOVERY_CLASSIFICATION_BLOCKED", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
