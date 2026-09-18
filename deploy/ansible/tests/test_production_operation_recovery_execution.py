"""Execution-level regressions for the production interrupted-operation contract.

The fixture renders and executes the source-controlled production shell helpers
against a fake systemd/ss boundary.  It intentionally keeps the operation
record, activation marker, registration markers, and release manifest as real
files so the tests exercise the same durable evidence and restart guards as a
Debian host without touching a real service manager.
"""

import json
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest

from jinja2 import Environment, FileSystemLoader, StrictUndefined


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = ROOT / "roles" / "relay_runtime" / "templates"
HEAD_OLD = "8698d3f5ea74034f61eb83e425358192cd672d19"
HEAD_NEW = "c6ba2b22a97de5e03270e77190d144aca3c2c6ef"


def execution_fixture_available():
    return os.name != "nt" and shutil.which("bash") is not None and shutil.which("flock") is not None


def root_execution_fixture_available():
    return execution_fixture_available() and hasattr(os, "geteuid") and os.geteuid() == 0


class ProductionOperationFixture:
    def __init__(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.bin_root = self.root / "bin"
        self.bin_root.mkdir()
        self.state_file = self.root / "systemd-state.json"
        self.log_file = self.root / "systemd.log"
        self.record = self.root / "production-operation.json"
        self.operation_state = self.root / "relay-production-operation-state"
        self.operation_lock = self.root / "production-operation.lock"
        self.superseded_root = self.root / "superseded-operations"
        self.activation_marker = self.root / "reviewer-activation-authorized"
        self.recovery_off_marker = self.root / "reviewer-recovery-requires-activation"
        self.registration_marker = self.root / ".runner"
        self.credentials_marker = self.root / ".credentials"
        self.manifest = self.root / "current-artifact-manifest.json"
        self.release_root = self.root / "releases"
        self.install_root = self.root / "install"
        self.scripts = {}
        self._install_fake_commands()
        self._render_helpers()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.temporary_directory.cleanup()

    def _install_fake_commands(self):
        systemctl = self.bin_root / "systemctl"
        systemctl.write_text(
            textwrap.dedent(
                """
                #!/usr/bin/env python3
                import json
                import os
                import sys

                state_path = os.environ["FIXTURE_STATE"]
                log_path = os.environ["FIXTURE_LOG"]
                with open(state_path, encoding="utf-8") as stream:
                    state = json.load(stream)
                operation = sys.argv[1]
                unit = sys.argv[2] if len(sys.argv) > 2 else ""
                state.setdefault(unit, {"active": "inactive", "enabled": "disabled"})
                unit_state = state[unit]
                fail_start = operation == "start" and os.environ.get("FIXTURE_FAIL_START_UNIT") == unit
                interrupt_after_enable = operation == "enable" and os.environ.get("FIXTURE_INTERRUPT_AFTER_ENABLE_UNIT") == unit

                def log():
                    with open(log_path, "a", encoding="utf-8") as stream:
                        stream.write(f"{operation} {unit}\\n")

                if operation == "is-active":
                    print(unit_state["active"])
                    raise SystemExit(0 if unit_state["active"] == "active" else 3)
                if operation == "is-enabled":
                    print(unit_state["enabled"])
                    raise SystemExit(0 if unit_state["enabled"] in {"enabled", "enabled-runtime"} else 1)
                if operation == "reset-failed":
                    log()
                    if unit_state["active"] == "failed":
                        unit_state["active"] = "inactive"
                elif operation == "start":
                    log()
                    if fail_start:
                        raise SystemExit(42)
                    unit_state["active"] = "active"
                elif operation == "stop":
                    log()
                    unit_state["active"] = "inactive"
                elif operation == "enable":
                    log()
                    unit_state["enabled"] = "enabled"
                elif operation == "disable":
                    log()
                    unit_state["enabled"] = "disabled"
                elif operation == "try-restart":
                    log()
                elif operation == "daemon-reload":
                    log()
                else:
                    raise SystemExit(f"unsupported fake systemctl operation: {operation}")

                with open(state_path, "w", encoding="utf-8") as stream:
                    json.dump(state, stream)
                if interrupt_after_enable:
                    raise SystemExit(137)
                """
            ).lstrip(),
            encoding="utf-8",
        )
        systemctl.chmod(0o755)

        ss = self.bin_root / "ss"
        ss.write_text(
            textwrap.dedent(
                """
                #!/usr/bin/env python3
                import json
                import os

                with open(os.environ["FIXTURE_STATE"], encoding="utf-8") as stream:
                    state = json.load(stream)
                if state.get("reviewer-mcp.service", {}).get("active") == "active":
                    print("LISTEN 0 128 127.0.0.1:8787 0.0.0.0:*")
                """
            ).lstrip(),
            encoding="utf-8",
        )
        ss.chmod(0o755)

        fake_stat = self.bin_root / "stat"
        fake_stat.write_text(
            textwrap.dedent(
                """
                #!/usr/bin/env python3
                import sys

                format_string = sys.argv[2] if len(sys.argv) > 2 else ""
                print("root root 600" if "%G" in format_string else "root 600")
                """
            ).lstrip(),
            encoding="utf-8",
        )
        fake_stat.chmod(0o755)

        self.environment = os.environ.copy()
        self.environment.update(
            {
                "FIXTURE_STATE": str(self.state_file),
                "FIXTURE_LOG": str(self.log_file),
                "PATH": os.pathsep.join((str(self.bin_root), self.environment.get("PATH", ""))),
            }
        )
        self.state_file.write_text(
            json.dumps(
                {
                    "reviewer-mcp.service": {"active": "inactive", "enabled": "disabled"},
                    "relay-runner.service": {"active": "inactive", "enabled": "disabled"},
                }
            ),
            encoding="utf-8",
        )
        self.log_file.write_text("", encoding="utf-8")

    def _render_helpers(self):
        context = {
            "relay_deployment_profile": "production",
            "relay_reviewer_service_name": "reviewer-mcp.service",
            "relay_runner_service_name": "relay-runner.service",
            "relay_production_runner_service_name": "relay-runner.service",
            "relay_reviewer_activation_marker": str(self.activation_marker),
            "relay_reviewer_recovery_off_marker": str(self.recovery_off_marker),
            "relay_reviewer_bind_address": "127.0.0.1",
            "relay_reviewer_bind_port": 8787,
            "relay_production_operation_record_path": str(self.record),
            "relay_production_operation_schema_version": "1",
            "relay_production_operation_state_path": str(self.operation_state),
            "relay_production_operation_lock_path": str(self.operation_lock),
            "relay_production_operation_stale_disposition_path": str(self.root / "stale-disposition"),
            "relay_production_operation_superseded_root": str(self.superseded_root),
            "relay_production_operation_stale_phase": "activate",
            "relay_production_operation_stale_target_head": HEAD_OLD,
            "relay_production_operation_target_head": HEAD_NEW,
            "relay_reviewer_stop_runner_path": str(self.root / "reviewer_stop_runner"),
            "relay_runner_registration_marker": str(self.registration_marker),
            "relay_runner_credentials_marker": str(self.credentials_marker),
        }
        environment = Environment(
            loader=FileSystemLoader(str(TEMPLATE_ROOT)),
            undefined=StrictUndefined,
            keep_trailing_newline=True,
        )
        for name, filename in {
            "operation_state": "relay-production-operation-state.j2",
            "start_guard": "relay-reviewer-start-guard.j2",
            "readiness": "relay-reviewer-readiness.j2",
            "recovery": "relay-reviewer-recovery.j2",
            "activation_start": "relay-reviewer-activation-start.j2",
            "operation_restart": "relay-reviewer-operation-restart.j2",
            "runner_start": "relay-runner-enable-start.j2",
            "stale_disposition": "relay-production-operation-stale-disposition.j2",
            "reviewer_stop_runner": "relay-reviewer-stop-runner.j2",
        }.items():
            rendered = environment.get_template(filename).render(**context)
            rendered = rendered.replace("/bin/systemctl", str(self.bin_root / "systemctl"))
            rendered = rendered.replace("/bin/ss", str(self.bin_root / "ss"))
            rendered = rendered.replace("/usr/bin/stat", str(self.bin_root / "stat"))
            path = self.operation_state if name == "operation_state" else self.root / name
            path.write_text(rendered, encoding="utf-8")
            path.chmod(0o755)
            self.scripts[name] = path

    def render_stale_disposition(
        self,
        phase,
        stale_head=HEAD_OLD,
        superseding_head=HEAD_NEW,
        actual_completed_phase="",
        expected_state_hash="",
    ):
        context = {
            "relay_production_operation_record_path": str(self.record),
            "relay_production_operation_lock_path": str(self.operation_lock),
            "relay_production_operation_superseded_root": str(self.superseded_root),
            "relay_production_operation_stale_phase": phase,
            "relay_production_operation_stale_target_head": stale_head,
            "relay_production_operation_target_head": superseding_head,
            "relay_production_operation_stale_actual_completed_phase": actual_completed_phase,
            "relay_production_operation_stale_expected_state_hash": expected_state_hash,
            "relay_production_operation_schema_version": "1",
            "relay_release_root": str(self.release_root),
            "relay_install_root": str(self.install_root),
            "relay_group": "root",
            "relay_runner_user": "root",
            "relay_runner_group": "root",
            "relay_reviewer_service_name": "reviewer-mcp.service",
            "relay_runner_service_name": "relay-runner.service",
            "relay_production_runner_service_name": "relay-runner.service",
            "relay_reviewer_activation_marker": str(self.activation_marker),
            "relay_reviewer_recovery_off_marker": str(self.recovery_off_marker),
            "relay_runner_registration_marker": str(self.registration_marker),
            "relay_runner_credentials_marker": str(self.credentials_marker),
            "relay_reviewer_bind_address": "127.0.0.1",
            "relay_reviewer_bind_port": 8787,
        }
        environment = Environment(
            loader=FileSystemLoader(str(TEMPLATE_ROOT)),
            undefined=StrictUndefined,
            keep_trailing_newline=True,
        )
        rendered = environment.get_template(
            "relay-production-operation-stale-disposition.j2"
        ).render(**context)
        rendered = rendered.replace("/bin/systemctl", str(self.bin_root / "systemctl"))
        rendered = rendered.replace("/bin/ss", str(self.bin_root / "ss"))
        rendered = rendered.replace("/usr/bin/stat", str(self.bin_root / "stat"))
        path = self.root / "stale-disposition"
        path.write_text(rendered, encoding="utf-8")
        path.chmod(0o755)
        self.scripts["stale_disposition"] = path

    def run(self, script_name, expected=None, service_result=None, environment_updates=None):
        environment = self.environment.copy()
        if service_result is None:
            environment.pop("SERVICE_RESULT", None)
        else:
            environment["SERVICE_RESULT"] = service_result
        if environment_updates:
            environment.update(environment_updates)
        result = subprocess.run(
            ["bash", str(self.scripts[script_name])],
            cwd=self.root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if expected is not None:
            self.assert_return(result, expected)
        return result

    @staticmethod
    def assert_return(result, expected):
        if expected == "pass":
            assert result.returncode == 0, result.stderr or result.stdout
        else:
            assert result.returncode != 0, result.stdout

    def systemctl(self, *arguments):
        return subprocess.run(
            [str(self.bin_root / "systemctl"), *arguments],
            cwd=self.root,
            env=self.environment,
            capture_output=True,
            text=True,
            check=True,
        )

    def state(self):
        return json.loads(self.state_file.read_text(encoding="utf-8"))

    def write_record(self, phase, head=HEAD_OLD):
        self.record.write_text(
            json.dumps(
                {
                    "schemaVersion": "1",
                    "state": "RECOVERY_REQUIRED",
                    "phase": phase,
                    "target_head": head,
                }
            ),
            encoding="utf-8",
        )
        self.record.chmod(0o600)

    def write_marker(self):
        self.activation_marker.write_text("authorized", encoding="utf-8")
        self.activation_marker.chmod(0o600)

    def write_reactivation_requirement(self):
        self.recovery_off_marker.write_text("requires-activation", encoding="utf-8")
        self.recovery_off_marker.chmod(0o600)

    def write_registration(self):
        self.registration_marker.write_text("non-secret-registration-binding", encoding="utf-8")
        self.credentials_marker.write_text("non-secret-registration-credential-marker", encoding="utf-8")
        self.registration_marker.chmod(0o600)
        self.credentials_marker.chmod(0o600)

    def prepare_apply_release(self, head=HEAD_OLD):
        release = self.release_root / head
        release.mkdir(parents=True)
        (release / "artifact-manifest.json").write_text(
            json.dumps({"schemaVersion": "1.0", "commit": head}),
            encoding="utf-8",
        )
        self.install_root.mkdir(parents=True, exist_ok=True)
        current = self.install_root / "current"
        if current.exists() or current.is_symlink():
            current.unlink()
        current.symlink_to(release, target_is_directory=True)

    def apply_state_hash(self, head=HEAD_OLD):
        state = {
            "activationMarker": "authorized",
            "listenerPresent": True,
            "manifestCommit": head,
            "phase": "apply",
            "recoveryOffMarker": "absent",
            "registrationEvidence": True,
            "releaseLink": str(self.release_root / head),
            "reviewerActive": "active",
            "reviewerEnabled": "enabled",
            "runnerActive": "active",
            "runnerEnabled": "enabled",
        }
        canonical = json.dumps(state, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def set_runtime_state(self, reviewer=("inactive", "disabled"), runner=("inactive", "disabled")):
        state = self.state()
        state["reviewer-mcp.service"] = {"active": reviewer[0], "enabled": reviewer[1]}
        state["relay-runner.service"] = {"active": runner[0], "enabled": runner[1]}
        self.state_file.write_text(json.dumps(state), encoding="utf-8")

    def log_lines(self):
        return self.log_file.read_text(encoding="utf-8").splitlines()


@unittest.skipUnless(execution_fixture_available(), "Linux bash/flock are required for execution-level lifecycle fixtures")
class ProductionOperationRecoveryExecutionTests(unittest.TestCase):
    @unittest.skipUnless(root_execution_fixture_available(), 'root-owned operation evidence required')
    def test_apply_restart_preserves_only_an_already_active_runner(self):
        for active in (False, True):
            with self.subTest(active=active), ProductionOperationFixture() as fixture:
                fixture.write_marker()
                fixture.write_record('apply')
                fixture.set_runtime_state(reviewer=('active', 'enabled'), runner=('active' if active else 'inactive', 'enabled'))
                fixture.run('operation_restart', expected='pass')
                self.assertEqual(fixture.log_lines(), ['try-restart reviewer-mcp.service'] + (['start relay-runner.service'] if active else []))

    @unittest.skipUnless(root_execution_fixture_available(), 'root-owned operation evidence required')
    def test_apply_runner_readiness_requires_a_current_live_owner_lock(self):
        with ProductionOperationFixture() as fixture:
            fixture.write_marker()
            fixture.write_record('apply')
            fixture.set_runtime_state(reviewer=('active', 'enabled'))
            fixture.run('readiness', expected='fail')
            holder = subprocess.Popen(['flock', '--exclusive', str(fixture.operation_lock),
                                       'sh', '-c', 'printf ready; cat'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
            try:
                self.assertEqual(holder.stdout.read(5), b'ready')
                fixture.run('readiness', expected='pass')
            finally:
                holder.stdin.close()
                holder.wait(timeout=5)
            fixture.run('readiness', expected='fail')

    def test_ordinary_apply_interruption_preserves_authorized_runtime(self):
        with ProductionOperationFixture() as fixture:
            fixture.write_marker()
            fixture.write_registration()
            fixture.set_runtime_state(
                reviewer=("active", "enabled"),
                runner=("active", "enabled"),
            )
            fixture.write_record("apply", HEAD_OLD)
            before_state = fixture.state()
            before_log = fixture.log_lines()

            fixture.run("recovery", expected="fail")
            self.assertEqual(fixture.state(), before_state)
            self.assertEqual(fixture.log_lines(), before_log)
            self.assertTrue(fixture.registration_marker.exists())
            self.assertTrue(fixture.record.exists())

    def test_activation_replay_never_mutates_runner_through_partof_boundary(self):
        with ProductionOperationFixture() as fixture:
            fixture.write_record("activate")
            fixture.set_runtime_state(runner=("active", "enabled"))
            before_runner = fixture.state()["relay-runner.service"].copy()
            before = len(fixture.log_lines())

            fixture.run("activation_start", expected="pass")
            self.assertEqual(fixture.state()["reviewer-mcp.service"]["active"], "active")
            self.assertEqual(fixture.state()["reviewer-mcp.service"]["enabled"], "enabled")
            self.assertEqual(fixture.state()["relay-runner.service"], before_runner)
            self.assertNotIn("relay-runner.service", "\n".join(fixture.log_lines()[before:]))
            fixture.run("start_guard", expected="fail")
            fixture.run("recovery", expected="fail")
            self.assertFalse(fixture.activation_marker.exists())

    def test_activation_replay_recovers_enable_before_start_interruption(self):
        with ProductionOperationFixture() as fixture:
            fixture.write_record("activate")
            fixture.set_runtime_state(
                reviewer=("inactive", "disabled"),
                runner=("active", "enabled"),
            )
            before_runner = fixture.state()["relay-runner.service"].copy()

            fixture.run(
                "activation_start",
                expected="fail",
                environment_updates={
                    "FIXTURE_INTERRUPT_AFTER_ENABLE_UNIT": "reviewer-mcp.service",
                },
            )
            self.assertEqual(
                fixture.state()["reviewer-mcp.service"],
                {"active": "inactive", "enabled": "enabled"},
            )
            self.assertEqual(fixture.state()["relay-runner.service"], before_runner)
            self.assertFalse(fixture.activation_marker.exists())
            self.assertTrue(fixture.record.exists())

            fixture.run("activation_start", expected="pass")
            self.assertEqual(fixture.state()["reviewer-mcp.service"]["active"], "active")
            self.assertEqual(fixture.state()["reviewer-mcp.service"]["enabled"], "enabled")
            self.assertEqual(fixture.state()["relay-runner.service"], before_runner)
            self.assertFalse(fixture.activation_marker.exists())
            self.assertTrue(fixture.record.exists())

    def test_activation_replay_recovers_failed_start_with_enabled_reviewer(self):
        with ProductionOperationFixture() as fixture:
            fixture.write_record("activate")
            fixture.set_runtime_state(
                reviewer=("inactive", "disabled"),
                runner=("active", "enabled"),
            )
            before_runner = fixture.state()["relay-runner.service"].copy()

            fixture.run(
                "activation_start",
                expected="fail",
                environment_updates={"FIXTURE_FAIL_START_UNIT": "reviewer-mcp.service"},
            )
            self.assertEqual(
                fixture.state()["reviewer-mcp.service"],
                {"active": "inactive", "enabled": "enabled"},
            )
            self.assertEqual(fixture.state()["relay-runner.service"], before_runner)
            self.assertFalse(fixture.activation_marker.exists())
            self.assertTrue(fixture.record.exists())

            fixture.run("activation_start", expected="pass")
            self.assertEqual(fixture.state()["reviewer-mcp.service"]["active"], "active")
            self.assertEqual(fixture.state()["reviewer-mcp.service"]["enabled"], "enabled")
            self.assertEqual(fixture.state()["relay-runner.service"], before_runner)
            self.assertFalse(fixture.activation_marker.exists())
            self.assertTrue(fixture.record.exists())

    def test_runner_enable_replay_preserves_healthy_reviewer(self):
        with ProductionOperationFixture() as fixture:
            fixture.write_marker()
            fixture.write_registration()
            fixture.set_runtime_state(
                reviewer=("active", "enabled"),
                runner=("inactive", "disabled"),
            )
            fixture.write_record("runner-enable")
            before_reviewer = fixture.state()["reviewer-mcp.service"].copy()
            fixture.run("runner_start", expected="pass")
            self.assertEqual(fixture.state()["relay-runner.service"]["active"], "active")
            self.assertEqual(fixture.state()["reviewer-mcp.service"], before_reviewer)
            fixture.run("recovery", expected="fail")

            self.assertTrue(fixture.registration_marker.exists())

    def test_boot_and_start_paths_do_not_act_on_unfinished_evidence(self):
        with ProductionOperationFixture() as fixture:
            fixture.write_marker()
            fixture.write_record("apply")
            before = len(fixture.log_lines())
            for script in ("start_guard", "readiness", "recovery"):
                fixture.run(script, expected="fail")
            self.assertEqual(fixture.log_lines()[before:], [])

    def test_reviewer_failure_stop_hook_subordinates_runner_without_start_coupling(self):
        with ProductionOperationFixture() as fixture:
            fixture.write_marker()
            fixture.write_registration()
            fixture.systemctl("start", "reviewer-mcp.service")
            fixture.systemctl("start", "relay-runner.service")
            before = len(fixture.log_lines())

            fixture.run("reviewer_stop_runner", expected="pass", service_result="exit-code")

            self.assertEqual(fixture.state()["reviewer-mcp.service"]["active"], "active")
            self.assertEqual(fixture.state()["relay-runner.service"]["active"], "inactive")
            self.assertIn("stop relay-runner.service", fixture.log_lines()[before:])
            self.assertNotIn("start reviewer-mcp.service", fixture.log_lines()[before:])

    def test_planned_reviewer_stop_result_does_not_launch_runner_stop(self):
        with ProductionOperationFixture() as fixture:
            fixture.write_marker()
            fixture.write_registration()
            fixture.systemctl("start", "reviewer-mcp.service")
            fixture.systemctl("start", "relay-runner.service")
            before = len(fixture.log_lines())

            fixture.run("reviewer_stop_runner", expected="pass", service_result="success")

            self.assertEqual(fixture.state()["relay-runner.service"]["active"], "active")
            self.assertNotIn("stop relay-runner.service", fixture.log_lines()[before:])

    def test_fresh_pre_activation_boot_recovery_does_not_synthesize_authorization(self):
        with ProductionOperationFixture() as fixture:
            fixture.set_runtime_state()
            fixture.run("recovery", expected="pass")

            self.assertFalse(fixture.activation_marker.exists())
            self.assertFalse(fixture.recovery_off_marker.exists())
            self.assertEqual(fixture.state()["reviewer-mcp.service"]["active"], "inactive")
            self.assertEqual(fixture.state()["reviewer-mcp.service"]["enabled"], "disabled")
            self.assertEqual(fixture.state()["relay-runner.service"]["active"], "inactive")
            self.assertEqual(fixture.state()["relay-runner.service"]["enabled"], "disabled")
            self.assertFalse(fixture.record.exists())

    def test_recovery_interruption_is_idempotent_on_the_next_recovery_attempt(self):
        with ProductionOperationFixture() as fixture:
            fixture.write_marker()
            fixture.write_record("apply")
            fixture.set_runtime_state(reviewer=("active", "enabled"))
            before_state = fixture.state()
            before_log = fixture.log_lines()
            fixture.run("recovery", expected="fail")
            fixture.run("recovery", expected="fail")
            self.assertEqual(fixture.state(), before_state)
            self.assertEqual(fixture.log_lines(), before_log)
            self.assertTrue(fixture.record.exists())

    def test_clean_boot_after_fully_completed_authorization_recovers_authorized_runtime(self):
        with ProductionOperationFixture() as fixture:
            fixture.write_marker()
            fixture.write_registration()
            fixture.systemctl("enable", "reviewer-mcp.service")
            fixture.systemctl("enable", "relay-runner.service")
            fixture.run("recovery", expected="pass")
            self.assertEqual(fixture.state()["reviewer-mcp.service"]["active"], "active")
            self.assertEqual(fixture.state()["relay-runner.service"]["active"], "active")
            fixture.run("start_guard", expected="pass")
            fixture.run("readiness", expected="pass")

    def test_old_exact_record_cannot_be_replaced_by_a_new_phase_or_head(self):
        with ProductionOperationFixture() as fixture:
            fixture.write_record("apply", HEAD_OLD)
            original = fixture.record.read_text(encoding="utf-8")
            fixture.run("activation_start", expected="fail")
            self.assertEqual(fixture.record.read_text(encoding="utf-8"), original)

    @unittest.skipUnless(root_execution_fixture_available(), "root is required for root-owned stale-record execution")
    def test_cross_revision_activate_disposition_resets_only_reviewer_and_archives_record(self):
        with ProductionOperationFixture() as fixture:
            fixture.render_stale_disposition("activate")
            fixture.write_record("activate", HEAD_OLD)
            fixture.set_runtime_state(
                reviewer=("inactive", "enabled"),
                runner=("inactive", "disabled"),
            )

            fixture.run("stale_disposition", expected="pass")

            state = fixture.state()
            self.assertEqual(
                state["reviewer-mcp.service"],
                {"active": "inactive", "enabled": "disabled"},
            )
            self.assertEqual(
                state["relay-runner.service"],
                {"active": "inactive", "enabled": "disabled"},
            )
            self.assertFalse(fixture.record.exists())
            archive = fixture.superseded_root / f"activate-{HEAD_OLD}.json"
            self.assertTrue(archive.exists())
            self.assertEqual(
                json.loads(archive.read_text(encoding="utf-8"))["state"],
                "SUPERSEDED",
            )
            archived = json.loads(archive.read_text(encoding="utf-8"))
            self.assertEqual(archived["phase"], "activate")
            self.assertEqual(archived["target_head"], HEAD_OLD)
            self.assertEqual(archived["superseded_by_head"], HEAD_NEW)
            self.assertEqual(
                archived["disposition"],
                "STALE_ACTIVATE_PREACTIVATION_RESET",
            )
            self.assertIn("stop reviewer-mcp.service", fixture.log_lines())
            self.assertIn("disable reviewer-mcp.service", fixture.log_lines())
            self.assertNotIn("relay-runner.service", "\n".join(fixture.log_lines()))

    @unittest.skipUnless(root_execution_fixture_available(), "root is required for root-owned stale-record execution")
    def test_cross_revision_runner_enable_disposition_is_read_only_and_archives_record(self):
        with ProductionOperationFixture() as fixture:
            fixture.render_stale_disposition("runner-enable")
            fixture.write_record("runner-enable", HEAD_OLD)
            fixture.write_marker()
            fixture.write_registration()
            fixture.set_runtime_state(
                reviewer=("active", "enabled"),
                runner=("inactive", "disabled"),
            )
            before_state = fixture.state()
            before_log = fixture.log_lines()

            fixture.run("stale_disposition", expected="pass")

            self.assertEqual(fixture.state(), before_state)
            self.assertEqual(fixture.log_lines(), before_log)
            self.assertFalse(fixture.record.exists())
            archive = fixture.superseded_root / f"runner-enable-{HEAD_OLD}.json"
            self.assertTrue(archive.exists())
            archived = json.loads(archive.read_text(encoding="utf-8"))
            self.assertEqual(archived["state"], "SUPERSEDED")
            self.assertEqual(archived["phase"], "runner-enable")
            self.assertEqual(archived["superseded_by_head"], HEAD_NEW)
            self.assertEqual(
                archived["disposition"],
                "STALE_RUNNER_ENABLE_REPLAYABLE",
            )

    def test_cross_revision_apply_disposition_requires_fresh_owner_evidence(self):
        with ProductionOperationFixture() as fixture:
            fixture.render_stale_disposition("apply")
            fixture.write_record("apply", HEAD_OLD)
            original = fixture.record.read_text(encoding="utf-8")

            result = fixture.run("stale_disposition", expected="fail")

            self.assertIn(
                "PRODUCTION_STALE_APPLY_COMPLETED_PHASE_REQUIRED",
                result.stderr,
            )
            self.assertEqual(fixture.record.read_text(encoding="utf-8"), original)
            self.assertFalse(fixture.superseded_root.exists())

    @unittest.skipUnless(root_execution_fixture_available(), "root is required for root-owned stale-record execution")
    def test_cross_revision_partial_apply_disposition_archives_evidence_without_replay(self):
        with ProductionOperationFixture() as fixture:
            fixture.prepare_apply_release()
            fixture.write_marker()
            fixture.write_registration()
            fixture.set_runtime_state(
                reviewer=("active", "enabled"),
                runner=("active", "enabled"),
            )
            expected_hash = fixture.apply_state_hash()
            fixture.render_stale_disposition(
                "apply",
                actual_completed_phase="apply",
                expected_state_hash=expected_hash,
            )
            fixture.write_record("apply", HEAD_OLD)
            before_state = fixture.state()
            before_log = fixture.log_lines()

            fixture.run("stale_disposition", expected="pass")

            self.assertEqual(fixture.state(), before_state)
            self.assertEqual(fixture.log_lines(), before_log)
            self.assertFalse(fixture.record.exists())
            archive = fixture.superseded_root / f"apply-{HEAD_OLD}.json"
            self.assertTrue(archive.exists())
            archived = json.loads(archive.read_text(encoding="utf-8"))
            self.assertEqual(archived["state"], "SUPERSEDED")
            self.assertEqual(archived["phase"], "apply")
            self.assertEqual(archived["target_head"], HEAD_OLD)
            self.assertEqual(archived["superseded_by_head"], HEAD_NEW)
            self.assertEqual(
                archived["disposition"],
                "STALE_APPLY_PARTIAL_APPLY_OWNER_RECONCILIATION",
            )
            self.assertEqual(archived["actual_completed_phase"], "apply")
            self.assertEqual(archived["expected_state_hash"], expected_hash)
            self.assertEqual(archived["current_state_hash"], expected_hash)

    @unittest.skipUnless(root_execution_fixture_available(), "root is required for root-owned stale-record execution")
    def test_cross_revision_partial_apply_disposition_rejects_changed_live_state(self):
        with ProductionOperationFixture() as fixture:
            fixture.prepare_apply_release()
            fixture.write_marker()
            fixture.write_registration()
            fixture.set_runtime_state(
                reviewer=("active", "enabled"),
                runner=("active", "enabled"),
            )
            expected_hash = fixture.apply_state_hash()
            fixture.render_stale_disposition(
                "apply",
                actual_completed_phase="apply",
                expected_state_hash=expected_hash,
            )
            fixture.write_record("apply", HEAD_OLD)
            fixture.set_runtime_state(
                reviewer=("active", "enabled"),
                runner=("inactive", "enabled"),
            )
            original = fixture.record.read_text(encoding="utf-8")

            result = fixture.run("stale_disposition", expected="fail")

            self.assertIn("PRODUCTION_STALE_APPLY_RUNNER_STATE_UNSAFE", result.stderr)
            self.assertEqual(fixture.record.read_text(encoding="utf-8"), original)
            self.assertFalse(fixture.superseded_root.exists())

    def test_cross_revision_malformed_evidence_is_never_archived_or_removed(self):
        with ProductionOperationFixture() as fixture:
            fixture.render_stale_disposition("activate")
            fixture.record.write_text("{malformed", encoding="utf-8")
            fixture.record.chmod(0o600)

            result = fixture.run("stale_disposition", expected="fail")

            self.assertIn("PRODUCTION_STALE_DISPOSITION_UNSAFE_RECORD", result.stderr)
            self.assertTrue(fixture.record.exists())
            self.assertFalse(fixture.superseded_root.exists())

    def test_malformed_or_symlinked_operation_evidence_is_never_deleted(self):
        with ProductionOperationFixture() as fixture:
            fixture.record.write_text("{malformed", encoding="utf-8")
            fixture.record.chmod(0o600)
            fixture.run("operation_state", expected="fail")
            fixture.run("recovery", expected="fail")
            self.assertTrue(fixture.record.exists())

            fixture.record.unlink()
            target = fixture.root / "record-target"
            target.write_text("not-operation-evidence", encoding="utf-8")
            fixture.record.symlink_to(target)
            fixture.run("operation_state", expected="fail")
            self.assertTrue(fixture.record.is_symlink())


if __name__ == "__main__":
    unittest.main()
