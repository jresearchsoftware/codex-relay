"""Native systemd lifecycle regression for the production Reviewer/runner units.

The test uses one disposable, locally named container. It renders the real
production unit and lifecycle-helper templates, installs distinct non-root
Reviewer and runner identities, and keeps the operation record and activation
marker root-owned mode-0600. The systemd manager then exercises the composed
activation, apply/restart, recovery, and runner-enable transitions. This is
intentionally stronger than a root-only unit or /bin/true preflight fixture:
the test fails if the bounded ExecStartPre=+... privilege gate is removed or
if either service is allowed to run as root.
"""

from pathlib import Path
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
import uuid

from jinja2 import Environment, FileSystemLoader, StrictUndefined


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = ROOT / "roles" / "relay_runtime" / "templates"
RUNNER_TEMPLATE_ROOT = ROOT / "roles" / "relay_runner" / "templates"


def docker_available():
    if shutil.which("docker") is None:
        return False
    try:
        result = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and bool(result.stdout.strip())


def _write_executable(path, content):
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
    path.chmod(0o755)


class DisposableSystemdLifecycle:
    """Own one disposable systemd container and its rendered unit files."""

    OPERATION_RECORD = "/run/lifecycle/operation-state.json"
    OPERATION_LOCK = "/run/lifecycle/production-operation.lock"
    ACTIVATION_MARKER = "/run/lifecycle/reviewer-activation-authorized"
    RECOVERY_OFF_MARKER = "/run/lifecycle/reviewer-recovery-requires-activation"
    REVIEWER_USER = "relay-reviewer"
    RUNNER_USER = "relay-runner"

    def __init__(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.name = f"relay-systemd-{uuid.uuid4().hex[:12]}"
        # The disposable install root is bind-mounted as /opt/lifecycle. It
        # must have production-like directory traversal for the non-root
        # credential preflight; protected lifecycle evidence is created later
        # as root-owned mode-0600 files inside /run.
        self.root.chmod(0o755)
        self._render_fixture()

    def __enter__(self):
        self._start_container()
        try:
            self._install_units()
            return self
        except Exception:
            self.close()
            raise

    def __exit__(self, *_args):
        self.close()

    def _render_fixture(self):
        _write_executable(
            self.root / "reviewer-process",
            """#!/usr/bin/python3
import os
import socket
import time

listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
listener.bind(("127.0.0.1", 8787))
listener.listen(1)
try:
    while not os.path.exists("/run/lifecycle/reviewer-fail"):
        time.sleep(0.1)
finally:
    listener.close()
""",
        )
        _write_executable(
            self.root / "runner-process",
            """#!/bin/sh
set -eu
while :; do
  sleep 1
done
""",
        )
        _write_executable(
            self.root / "relay-reviewer-credential-check",
            """#!/bin/sh
set -eu
exit 0
""",
        )
        (self.root / "relay.env").write_text("", encoding="utf-8")
        (self.root / "current").mkdir()

        context = {
            "relay_deployment_profile": "production",
            "relay_install_root": "/opt/lifecycle",
            "relay_config_root": "/opt/lifecycle",
            "relay_state_root": "/run/lifecycle/state",
            "relay_evidence_root": "/run/lifecycle/evidence",
            "relay_runtime_root": "/run/lifecycle/runtime",
            "relay_log_root": "/run/lifecycle/log",
            "relay_reviewer_service_name": "reviewer-mcp.service",
            "relay_runner_service_name": "relay-runner.service",
            "relay_reviewer_user": self.REVIEWER_USER,
            "relay_reviewer_group": self.REVIEWER_USER,
            "relay_reviewer_proxy_group": "www-data",
            "relay_runner_user": self.RUNNER_USER,
            "relay_runner_group": self.RUNNER_USER,
            "relay_runner_root": "/run/lifecycle/runner",
            "relay_runner_work_root": "/run/lifecycle/runner-work",
            "relay_runner_home": "/run/lifecycle/runner-home",
            "relay_writer_claim_root": "/run/lifecycle/writer-claims",
            "relay_diagnostics_root": "/run/lifecycle/diagnostics",
            "relay_codex_home": "/run/lifecycle/codex",
            "relay_dispatch_state_root": "/run/lifecycle/dispatch-state",
            "relay_dispatch_work_root": "/run/lifecycle/dispatch-work",
            "relay_dispatch_home": "/run/lifecycle/dispatch-home",
            "relay_dispatch_remediation_root": "/run/lifecycle/dispatch-remediation",
            "relay_dispatch_evidence_root": "/run/lifecycle/dispatch-evidence",
            "relay_writer_credential_root": "/opt/lifecycle",
            "relay_reviewer_credential_root": "/opt/lifecycle",
            "relay_reviewer_credential_env_file": "/opt/lifecycle/relay.env",
            "relay_reviewer_activation_marker": self.ACTIVATION_MARKER,
            "relay_reviewer_recovery_off_marker": self.RECOVERY_OFF_MARKER,
            "relay_reviewer_bind_address": "127.0.0.1",
            "relay_reviewer_start_guard_path": "/usr/local/libexec/relay-reviewer-start-guard",
            "relay_reviewer_readiness_path": "/usr/local/libexec/relay-reviewer-readiness",
            "relay_reviewer_activation_start_path": "/usr/local/libexec/relay-reviewer-activation-start",
            "relay_reviewer_operation_restart_path": "/usr/local/libexec/relay-reviewer-operation-restart",
            "relay_reviewer_stop_runner_path": "/usr/local/libexec/relay-reviewer-stop-runner",
            "relay_reviewer_exec_start": "/usr/local/libexec/reviewer-process",
            "relay_runner_exec_start": "/usr/local/libexec/runner-process",
            "relay_runner_labels": ["codex-relay"],
            "relay_runner_registration_marker": "/run/lifecycle/runner/.runner",
            "relay_runner_credentials_marker": "/run/lifecycle/runner/.credentials",
            "relay_runner_enable_start_path": "/usr/local/libexec/relay-runner-enable-start",
            "relay_production_operation_record_path": self.OPERATION_RECORD,
            "relay_production_operation_schema_version": "1",
            "relay_production_operation_state_path": "/usr/local/libexec/relay-production-operation-state",
            "relay_production_operation_lock_path": self.OPERATION_LOCK,
        }
        environment = Environment(
            loader=FileSystemLoader(str(TEMPLATE_ROOT)),
            undefined=StrictUndefined,
            keep_trailing_newline=True,
        )
        runner_environment = Environment(
            loader=FileSystemLoader(str(RUNNER_TEMPLATE_ROOT)),
            undefined=StrictUndefined,
            keep_trailing_newline=True,
        )
        (self.root / "reviewer-mcp.service").write_text(
            environment.get_template("reviewer-mcp.service.j2").render(**context),
            encoding="utf-8",
        )
        (self.root / "relay-runner.service").write_text(
            runner_environment.get_template("relay-runner.service.j2").render(**context),
            encoding="utf-8",
        )
        for template_name, output_name in {
            "relay-production-operation-state.j2": "relay-production-operation-state",
            "relay-reviewer-start-guard.j2": "relay-reviewer-start-guard",
            "relay-reviewer-readiness.j2": "relay-reviewer-readiness",
            "relay-reviewer-recovery.j2": "relay-reviewer-recovery",
            "relay-reviewer-operation-restart.j2": "relay-reviewer-operation-restart",
            "relay-reviewer-activation-start.j2": "relay-reviewer-activation-start",
            "relay-runner-enable-start.j2": "relay-runner-enable-start",
            "relay-reviewer-stop-runner.j2": "relay-reviewer-stop-runner",
        }.items():
            _write_executable(
                self.root / output_name,
                environment.get_template(template_name).render(**context),
            )

    def _run_docker(self, arguments, *, check=True, timeout=30):
        result = subprocess.run(
            ["docker", *arguments],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
        if check and result.returncode != 0:
            raise AssertionError(
                f"docker {' '.join(arguments)} failed with {result.returncode}:\n"
                f"stdout={result.stdout}\nstderr={result.stderr}"
            )
        return result

    def _exec_shell(self, script, *, check=True, timeout=30):
        return self._run_docker(
            ["exec", self.name, "bash", "-c", script],
            check=check,
            timeout=timeout,
        )

    def _start_container(self):
        self._run_docker(
            [
                "run",
                "--detach",
                "--privileged",
                "--cgroupns=host",
                "--name",
                self.name,
                "--tmpfs",
                "/run",
                "--tmpfs",
                "/run/lock",
                "--tmpfs",
                "/tmp",
                "--volume",
                f"{self.root}:/opt/lifecycle:ro",
                "--volume",
                "/sys/fs/cgroup:/sys/fs/cgroup:rw",
                "debian:12",
                "bash",
                "-c",
                "apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq systemd systemd-sysv dbus iproute2 passwd procps python3 && exec /lib/systemd/systemd",
            ],
            timeout=120,
        )
        deadline = time.monotonic() + 120
        last = ""
        while time.monotonic() < deadline:
            state = self._run_docker(
                ["inspect", "--format", "{{.State.Status}}", self.name],
                check=False,
            )
            last = state.stdout.strip() or state.stderr.strip()
            if state.returncode != 0 or last in {"exited", "dead"}:
                logs = self._run_docker(["logs", self.name], check=False).stdout
                raise AssertionError(f"disposable systemd container stopped ({last}):\n{logs}")
            private_socket = self._run_docker(
                ["exec", self.name, "test", "-S", "/run/systemd/private"],
                check=False,
            )
            if private_socket.returncode == 0:
                return
            time.sleep(0.5)
        logs = self._run_docker(["logs", self.name], check=False).stdout
        raise AssertionError(f"disposable systemd manager did not become ready ({last}):\n{logs}")

    def _install_units(self):
        helper_names = (
            "relay-production-operation-state",
            "relay-reviewer-start-guard",
            "relay-reviewer-readiness",
            "relay-reviewer-recovery",
            "relay-reviewer-operation-restart",
            "relay-reviewer-activation-start",
            "relay-runner-enable-start",
            "relay-reviewer-stop-runner",
            "relay-reviewer-credential-check",
            "reviewer-process",
            "runner-process",
        )
        helper_copy = " ".join(
            f"cp /opt/lifecycle/{name} /usr/local/libexec/{name}; "
            f"chown root:root /usr/local/libexec/{name}; "
            f"chmod 0755 /usr/local/libexec/{name};"
            for name in helper_names
        )
        self._exec_shell(
            "set -eu; "
            "groupadd --system relay-reviewer; "
            "groupadd --system relay-runner; "
            "useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin --gid relay-reviewer relay-reviewer; "
            "useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin --gid relay-runner relay-runner; "
            "mkdir -p /usr/local/libexec /etc/systemd/system "
            "/run/lifecycle/state/reviewer /run/lifecycle/evidence/reviewer "
            "/run/lifecycle/runtime /run/lifecycle/log "
            "/run/lifecycle/runner /run/lifecycle/runner-work /run/lifecycle/runner-home "
            "/run/lifecycle/writer-claims /run/lifecycle/diagnostics /run/lifecycle/codex "
            "/run/lifecycle/dispatch-state /run/lifecycle/dispatch-work "
            "/run/lifecycle/dispatch-home /run/lifecycle/dispatch-remediation "
            "/run/lifecycle/dispatch-evidence; "
            "chown relay-reviewer:relay-reviewer /run/lifecycle/state/reviewer /run/lifecycle/evidence/reviewer; "
            "chown relay-runner:relay-runner /run/lifecycle/runner /run/lifecycle/runner-work /run/lifecycle/runner-home; "
            "chmod 0755 /run/lifecycle; "
            f"{helper_copy} "
            "cp /opt/lifecycle/reviewer-mcp.service /etc/systemd/system/reviewer-mcp.service; "
            "cp /opt/lifecycle/relay-runner.service /etc/systemd/system/relay-runner.service; "
            "chown root:root /etc/systemd/system/reviewer-mcp.service /etc/systemd/system/relay-runner.service; "
            "systemctl daemon-reload",
            timeout=30,
        )
        self._run_docker(
            [
                "exec",
                self.name,
                "systemd-analyze",
                "verify",
                "/etc/systemd/system/reviewer-mcp.service",
                "/etc/systemd/system/relay-runner.service",
            ]
        )

    def systemctl(self, *arguments, check=True):
        return self._run_docker(["exec", self.name, "systemctl", *arguments], check=check)

    def run_helper(self, name, *, check=False):
        return self._run_docker(
            ["exec", self.name, f"/usr/local/libexec/{name}"],
            check=check,
            timeout=30,
        )

    def wait_for_state(self, unit, active, enabled, timeout=20):
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            active_result = self.systemctl("is-active", unit, check=False)
            enabled_result = self.systemctl("is-enabled", unit, check=False)
            state = (active_result.stdout.strip(), enabled_result.stdout.strip())
            last = state
            if state == (active, enabled):
                return
            time.sleep(0.25)
        raise AssertionError(f"{unit} did not reach {(active, enabled)}; last state={last}")

    def wait_for_listener(self, expected="127.0.0.1:8787", timeout=20):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = self._exec_shell(
                f"ss -H -ltn | grep -F -- {self._quote(expected)}",
                check=False,
            )
            if result.returncode == 0:
                return
            time.sleep(0.25)
        raise AssertionError(f"listener did not become ready: {expected}")

    def write_file(self, path, content, *, owner="root:root", mode="0600"):
        self._exec_shell(
            f"printf '%s' {self._quote(content)} > {self._quote(path)}; "
            f"chown {owner} {self._quote(path)}; chmod {mode} {self._quote(path)}"
        )

    def write_operation(self, phase):
        record = json.dumps(
            {
                "schemaVersion": "1",
                "state": "RECOVERY_REQUIRED",
                "phase": phase,
                "target_head": "a" * 40,
            },
            separators=(",", ":"),
        )
        self.write_file(self.OPERATION_RECORD, record + "\n")

    def write_malformed_operation(self):
        self.write_file(self.OPERATION_RECORD, "{malformed\n")

    def write_activation_marker(self, *, mode="0600"):
        self.write_file(self.ACTIVATION_MARKER, "authorized\n", mode=mode)

    def write_recovery_off_marker(self):
        self.write_file(self.RECOVERY_OFF_MARKER, "requires-activation\n")

    def write_registration_markers(self):
        self.write_file(
            "/run/lifecycle/runner/.runner",
            '{"fixture":"registered"}\n',
            owner="relay-runner:relay-runner",
        )
        self.write_file(
            "/run/lifecycle/runner/.credentials",
            '{"fixture":"credential-marker"}\n',
            owner="relay-runner:relay-runner",
        )

    def remove(self, path):
        self._exec_shell(f"rm -f -- {self._quote(path)}")

    def touch_failure(self):
        self._exec_shell("touch /run/lifecycle/reviewer-fail")

    def main_process_uid(self, unit):
        pid = self.systemctl("show", "--property=MainPID", "--value", unit).stdout.strip()
        if not pid.isdigit() or pid == "0":
            raise AssertionError(f"{unit} has no live MainPID: {pid!r}")
        return self._exec_shell(
            f"awk '/^Uid:/ {{print $2}}' /proc/{pid}/status"
        ).stdout.strip()

    def assert_root_only_evidence(self, *paths):
        for path in paths:
            metadata = self._exec_shell(
                f"stat -c '%U %G %a' {self._quote(path)}"
            ).stdout.strip()
            if metadata != "root root 600":
                raise AssertionError(f"unexpected protected evidence metadata for {path}: {metadata}")
            for user in (self.REVIEWER_USER, self.RUNNER_USER):
                readable = self._run_docker(
                    [
                        "exec",
                        self.name,
                        "/usr/sbin/runuser",
                        "-u",
                        user,
                        "--",
                        "test",
                        "-r",
                        path,
                    ],
                    check=False,
                )
                if readable.returncode == 0:
                    raise AssertionError(f"{user} can read root-only evidence {path}")

    def assert_fixed_helpers_root_owned(self):
        for name in (
            "relay-production-operation-state",
            "relay-reviewer-start-guard",
            "relay-reviewer-readiness",
        ):
            metadata = self._exec_shell(
                f"stat -c '%U %G %a' /usr/local/libexec/{name}"
            ).stdout.strip()
            if metadata != "root root 755":
                raise AssertionError(f"unexpected lifecycle helper metadata for {name}: {metadata}")

    @staticmethod
    def _quote(value):
        # All paths are fixed fixture paths; shell quoting protects JSON and
        # keeps this helper safe if the test content gains punctuation later.
        return "'" + value.replace("'", "'\\''") + "'"

    def close(self):
        self._run_docker(["rm", "--force", self.name], check=False, timeout=30)
        self.temporary_directory.cleanup()


class ReviewerRunnerNativeSystemdLifecycleTests(unittest.TestCase):
    def _require_docker(self):
        if not docker_available():
            if os.environ.get("CI", "").lower() == "true":
                self.fail("CI must provide Docker for the native systemd lifecycle regression")
            self.skipTest("a disposable Docker systemd manager is required")

    def test_real_privilege_topology_covers_authorized_lifecycle(self):
        self._require_docker()
        with DisposableSystemdLifecycle() as fixture:
            fixture.assert_fixed_helpers_root_owned()
            fixture.systemctl("enable", "reviewer-mcp.service", "relay-runner.service")

            # Fresh/pre-activation recovery and direct start cannot synthesize
            # authorization from the absence of the root-only marker.
            recovery = fixture.run_helper("relay-reviewer-recovery")
            self.assertEqual(recovery.returncode, 0, recovery.stderr)
            fixture.wait_for_state("reviewer-mcp.service", "inactive", "enabled")
            blocked = fixture.systemctl("start", "reviewer-mcp.service", check=False)
            self.assertNotEqual(blocked.returncode, 0)
            fixture.systemctl("reset-failed", "reviewer-mcp.service", check=False)

            # Explicit activate owns the operation lock while the real guard
            # consumes root-only RECOVERY_REQUIRED evidence. The marker is
            # intentionally absent during this transition, as in production.
            fixture.write_operation("activate")
            fixture.assert_root_only_evidence(fixture.OPERATION_RECORD)
            activation = fixture.run_helper("relay-reviewer-activation-start")
            self.assertEqual(activation.returncode, 0, activation.stderr)
            fixture.wait_for_state("reviewer-mcp.service", "active", "enabled")
            self.assertNotEqual(fixture.main_process_uid("reviewer-mcp.service"), "0")

            fixture.write_activation_marker()
            fixture.assert_root_only_evidence(fixture.ACTIVATION_MARKER)
            fixture.remove(fixture.OPERATION_RECORD)

            # Ordinary exact-head apply may legitimately try-restart an
            # authorized Reviewer. The real guard must read the root-only
            # marker and operation record through the bounded privileged gate.
            fixture.write_operation("apply")
            fixture.assert_root_only_evidence(
                fixture.OPERATION_RECORD,
                fixture.ACTIVATION_MARKER,
            )
            restart = fixture.run_helper("relay-reviewer-operation-restart")
            self.assertEqual(restart.returncode, 0, restart.stderr)
            fixture.wait_for_state("reviewer-mcp.service", "active", "enabled")
            fixture.remove(fixture.OPERATION_RECORD)

            # Unauthorized and unsafe runner starts are blocked by the real
            # readiness helper before the non-root runner process is launched.
            fixture.write_registration_markers()
            fixture.remove(fixture.ACTIVATION_MARKER)
            unauthorized_runner = fixture.systemctl(
                "start", "relay-runner.service", check=False
            )
            # systemd treats a failed ConditionPathExists as a successful
            # no-op, so assert the durable result rather than the client rc.
            self.assertEqual(unauthorized_runner.returncode, 0)
            fixture.wait_for_state("relay-runner.service", "inactive", "enabled")
            fixture.systemctl("reset-failed", "relay-runner.service", check=False)
            fixture.write_activation_marker()

            fixture.write_recovery_off_marker()
            blocked_off_runner = fixture.systemctl(
                "start", "relay-runner.service", check=False
            )
            self.assertNotEqual(blocked_off_runner.returncode, 0)
            fixture.systemctl("reset-failed", "relay-runner.service", check=False)
            fixture.remove(fixture.RECOVERY_OFF_MARKER)

            fixture.write_malformed_operation()
            unsafe_runner = fixture.systemctl(
                "start", "relay-runner.service", check=False
            )
            self.assertNotEqual(unsafe_runner.returncode, 0)
            fixture.assert_root_only_evidence(
                fixture.OPERATION_RECORD,
                fixture.ACTIVATION_MARKER,
            )
            fixture.systemctl("reset-failed", "relay-runner.service", check=False)
            fixture.remove(fixture.OPERATION_RECORD)

            # Only the explicit runner-enable transition starts the registered
            # runner. Its readiness gate is the real root-only preflight.
            fixture.write_operation("runner-enable")
            enable = fixture.run_helper("relay-runner-enable-start")
            self.assertEqual(enable.returncode, 0, enable.stderr)
            fixture.wait_for_state("relay-runner.service", "active", "enabled")
            self.assertNotEqual(fixture.main_process_uid("relay-runner.service"), "0")
            fixture.remove(fixture.OPERATION_RECORD)

            # Recovery rejects the deliberate authorized-off state, malformed
            # evidence, and wrong marker mode, then accepts only the valid
            # marker-authorized state. Registration markers let the same
            # recovery path prove runner readiness after Reviewer recovery.
            # A real apply restart must preserve an already active PartOf
            # runner while both start guards observe the held apply lock.
            old_pid = fixture.systemctl('show', '--property=MainPID', '--value', 'reviewer-mcp.service').stdout.strip()
            fixture.write_operation('apply')
            restart = fixture.run_helper('relay-reviewer-operation-restart')
            self.assertEqual(restart.returncode, 0, restart.stderr)
            fixture.wait_for_state('reviewer-mcp.service', 'active', 'enabled')
            fixture.wait_for_state('relay-runner.service', 'active', 'enabled')
            self.assertNotEqual(old_pid, fixture.systemctl('show', '--property=MainPID', '--value', 'reviewer-mcp.service').stdout.strip())
            fixture.remove(fixture.OPERATION_RECORD)

            fixture.systemctl("stop", "reviewer-mcp.service")
            fixture.wait_for_state("reviewer-mcp.service", "inactive", "enabled")
            fixture.wait_for_state("relay-runner.service", "inactive", "enabled")

            fixture.write_recovery_off_marker()
            blocked_off = fixture.run_helper("relay-reviewer-recovery")
            self.assertNotEqual(blocked_off.returncode, 0)
            fixture.wait_for_state("reviewer-mcp.service", "inactive", "enabled")
            fixture.remove(fixture.RECOVERY_OFF_MARKER)

            fixture.write_activation_marker(mode="0644")
            blocked_mode = fixture.run_helper("relay-reviewer-recovery")
            self.assertNotEqual(blocked_mode.returncode, 0)
            fixture.wait_for_state("reviewer-mcp.service", "inactive", "enabled")
            fixture.write_activation_marker()

            fixture.write_malformed_operation()
            blocked_unsafe = fixture.run_helper("relay-reviewer-recovery")
            self.assertNotEqual(blocked_unsafe.returncode, 0)
            fixture.assert_root_only_evidence(fixture.OPERATION_RECORD)
            fixture.wait_for_state("reviewer-mcp.service", "inactive", "enabled")
            fixture.remove(fixture.OPERATION_RECORD)

            recovered = fixture.run_helper("relay-reviewer-recovery")
            self.assertEqual(recovered.returncode, 0, recovered.stderr)
            fixture.wait_for_state("reviewer-mcp.service", "active", "enabled")
            # Type=simple reports Reviewer active when its process has exec'd,
            # before the TCP socket is necessarily bound. The production
            # recovery timer re-enters the same read-only helper after that
            # readiness boundary; model that bounded retry rather than making
            # the regression depend on a sleep race.
            fixture.wait_for_listener()
            recovery_retry = fixture.run_helper("relay-reviewer-recovery")
            self.assertEqual(recovery_retry.returncode, 0, recovery_retry.stderr)
            fixture.wait_for_state("relay-runner.service", "active", "enabled")
            self.assertNotEqual(fixture.main_process_uid("reviewer-mcp.service"), "0")
            self.assertNotEqual(fixture.main_process_uid("relay-runner.service"), "0")

    def test_normal_restart_explicit_stop_and_failure_stop_propagation(self):
        self._require_docker()
        with DisposableSystemdLifecycle() as fixture:
            fixture.write_activation_marker()
            fixture.systemctl("enable", "reviewer-mcp.service", "relay-runner.service")
            fixture.systemctl("start", "reviewer-mcp.service")
            fixture.systemctl("start", "relay-runner.service")
            fixture.wait_for_state("reviewer-mcp.service", "active", "enabled")
            fixture.wait_for_state("relay-runner.service", "active", "enabled")
            self.assertNotEqual(fixture.main_process_uid("reviewer-mcp.service"), "0")
            self.assertNotEqual(fixture.main_process_uid("relay-runner.service"), "0")

            # A planned restart is a stop+start transaction. SERVICE_RESULT
            # is success for that controlled stop, so the helper must not
            # enqueue a second runner stop while PartOf restarts the runner.
            fixture.systemctl("try-restart", "reviewer-mcp.service")
            fixture.wait_for_state("reviewer-mcp.service", "active", "enabled")
            fixture.wait_for_state("relay-runner.service", "active", "enabled")

            # Explicit Reviewer stop still propagates through PartOf.
            fixture.systemctl("stop", "reviewer-mcp.service")
            fixture.wait_for_state("reviewer-mcp.service", "inactive", "enabled")
            fixture.wait_for_state("relay-runner.service", "inactive", "enabled")

            fixture.systemctl("start", "reviewer-mcp.service")
            fixture.systemctl("start", "relay-runner.service")
            fixture.wait_for_state("reviewer-mcp.service", "active", "enabled")
            fixture.wait_for_state("relay-runner.service", "active", "enabled")

            # An unexpected process failure supplies a non-success result to
            # ExecStopPost and must stop the already-running runner promptly.
            fixture.systemctl(
                "kill",
                "--kill-who=main",
                "--signal=SIGKILL",
                "reviewer-mcp.service",
            )
            # Keep a Restart=on-failure retry from becoming healthy again after
            # the first failed process has already exercised ExecStopPost.
            fixture.touch_failure()
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                runner = fixture.systemctl("is-active", "relay-runner.service", check=False)
                if runner.stdout.strip() in {"inactive", "failed"}:
                    break
                time.sleep(0.25)
            else:
                self.fail("genuine Reviewer failure did not stop relay-runner.service")
            self.assertIn(
                fixture.systemctl("is-active", "relay-runner.service", check=False).stdout.strip(),
                {"inactive", "failed"},
            )


if __name__ == "__main__":
    unittest.main()
