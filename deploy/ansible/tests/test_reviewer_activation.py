"""Regression checks for the credential-gated Reviewer activation boundary."""

from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]


def activation_shell_command(activation):
    """Extract the actual folded shell body from the activation task."""
    lines = activation.splitlines()
    start = next(
        index
        for index, line in enumerate(lines)
        if line.strip() == "ansible.builtin.shell: >-"
    )
    body = []
    for line in lines[start + 1 :]:
        if not line.startswith("        "):
            break
        body.append(line.strip())
    if not body:
        raise AssertionError("activation credential shell body is missing")
    return " ".join(body)


def run_activation_fixture(activation, *, parent_exports_credential, require_user, credential_present):
    """Run the source-controlled activation shell against a secret-free fixture."""
    shell = shutil.which("sh")
    if shell is None:
        raise unittest.SkipTest("POSIX sh is required for the activation subprocess fixture")

    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        install_root = root / "install"
        bin_root = root / "bin"
        install_root.mkdir()
        bin_root.mkdir()

        (root / "reviewer.env").write_text(
            "FIXTURE_CREDENTIAL=valid\n" if credential_present else "",
            encoding="utf-8",
        )
        checker = install_root / "relay-reviewer-credential-check"
        checker.write_text(
            textwrap.dedent(
                """
                #!/bin/sh
                set -eu
                test "${FIXTURE_CREDENTIAL:-}" = valid
                if test "${FIXTURE_REQUIRE_USER:-}" = 1; then
                  test "${FIXTURE_EFFECTIVE_USER:-}" = reviewer
                fi
                """
            ).lstrip(),
            encoding="utf-8",
        )
        checker.chmod(0o755)

        # This is a local stand-in for runuser. It makes the requested identity
        # observable without requiring a privileged account or real credentials.
        runuser = bin_root / "runuser"
        runuser.write_text(
            textwrap.dedent(
                """
                #!/bin/sh
                set -eu
                test "$1" = -u
                effective_user=$2
                shift 2
                test "$1" = --preserve-environment
                shift
                FIXTURE_EFFECTIVE_USER=$effective_user
                export FIXTURE_EFFECTIVE_USER
                exec "$@"
                """
            ).lstrip(),
            encoding="utf-8",
        )
        runuser.chmod(0o755)

        command = activation_shell_command(activation)
        for placeholder, value in (
            ("{{ relay_reviewer_credential_env_file }}", "./reviewer.env"),
            ("{{ relay_install_root }}", "./install"),
            ("{{ relay_reviewer_user }}", "reviewer"),
        ):
            command = command.replace(placeholder, value)

        environment = os.environ.copy()
        environment["PATH"] = os.pathsep.join(
            (str(bin_root), environment.get("PATH", ""))
        )
        for name in (
            "FIXTURE_CREDENTIAL",
            "FIXTURE_EFFECTIVE_USER",
            "FIXTURE_REQUIRE_USER",
        ):
            environment.pop(name, None)
        if parent_exports_credential:
            environment["FIXTURE_CREDENTIAL"] = "valid"
        if require_user:
            environment["FIXTURE_REQUIRE_USER"] = "1"

        return subprocess.run(
            [shell, "-c", command],
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )


def bind_restart_operation(
    requested,
    activation_authorized,
    post_activation_authorized,
    service_active_at_mutation,
    check_mode=False,
):
    if check_mode or not (
        requested and activation_authorized and post_activation_authorized
    ):
        return "no-op"
    return "try-restart" if service_active_at_mutation else "no-start"


class ReviewerActivationTests(unittest.TestCase):
    def setUp(self):
        self.group_vars = (ROOT / "group_vars" / "all.yml").read_text(encoding="utf-8")
        self.runtime = (ROOT / "roles" / "relay_runtime" / "tasks" / "main.yml").read_text(encoding="utf-8")
        self.runtime_handler = (ROOT / "roles" / "relay_runtime" / "handlers" / "main.yml").read_text(encoding="utf-8")
        self.bind_handler = (ROOT / "roles" / "relay_reviewer_bind" / "handlers" / "main.yml").read_text(encoding="utf-8")
        self.bind_tasks = (ROOT / "roles" / "relay_reviewer_bind" / "tasks" / "main.yml").read_text(encoding="utf-8")
        self.bind_playbook = (ROOT / "relay-docker-nginx.yml").read_text(encoding="utf-8")
        self.activation = (ROOT / "relay-reviewer-activation.yml").read_text(encoding="utf-8")
        self.reviewer_service = (
            ROOT / "roles" / "relay_runtime" / "templates" / "reviewer-mcp.service.j2"
        ).read_text(encoding="utf-8")


    def test_activation_path_checks_exact_head_and_credentials_before_systemd(self):
        for marker in (
            "REVIEWER_ACTIVATION_AUTHORIZATION_REQUIRED",
            "REVIEWER_ACTIVATION_CHECKOUT_HEAD_MISMATCH",
            "relay-reviewer-credential-check",
            "REVIEWER_ACTIVATION_CREDENTIAL_GATE_FAILED",
            "relay_reviewer_activation_start_path",
            "production-operation-state.yml",
            "no_log: true",
        ):
            self.assertIn(marker, self.activation)
        self.assertLess(
            self.activation.index("Require the owner-provisioned Reviewer credential gate"),
            self.activation.index("Enable and start Reviewer through the explicit activation transition window"),
        )
        self.assertIn("check_mode: false", self.activation)
        self.assertIn("failed_when: false", self.activation)
        self.assertIn("set -a;", self.activation)
        self.assertIn(
            "runuser -u '{{ relay_reviewer_user }}' --preserve-environment",
            self.activation,
        )
        self.assertIn(
            "EnvironmentFile=-{{ relay_reviewer_credential_env_file }}",
            self.reviewer_service,
        )
        self.assertIn(
            "ExecStartPre={{ relay_install_root }}/relay-reviewer-credential-check",
            self.reviewer_service,
        )
        self.assertIn(
            "ExecStartPre=+{{ relay_reviewer_start_guard_path }}",
            self.reviewer_service,
        )

    @unittest.skipUnless(shutil.which("sh"), "POSIX sh is required for the subprocess fixture")
    def test_activation_exports_sourced_assignments_to_child_checker(self):
        result = run_activation_fixture(
            self.activation,
            parent_exports_credential=False,
            require_user=False,
            credential_present=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    @unittest.skipUnless(shutil.which("sh"), "POSIX sh is required for the subprocess fixture")
    def test_activation_runs_checker_as_reviewer_identity(self):
        result = run_activation_fixture(
            self.activation,
            # Keep the environment contract satisfied so this test isolates
            # execution identity rather than export behavior.
            parent_exports_credential=True,
            require_user=True,
            credential_present=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    @unittest.skipUnless(shutil.which("sh"), "POSIX sh is required for the subprocess fixture")
    def test_activation_checker_fails_closed_when_credential_assignment_is_missing(self):
        result = run_activation_fixture(
            self.activation,
            parent_exports_credential=False,
            require_user=False,
            credential_present=False,
        )
        self.assertNotEqual(result.returncode, 0)


    def test_docker_nginx_bind_chain_uses_shared_activation_contract(self):
        self.assertIn("role: relay_reviewer_bind", self.bind_playbook)
        self.assertNotIn("role: relay_runtime", self.bind_playbook)
        self.assertIn("notify: Try-restart Reviewer for validated bind mode", self.bind_tasks)
        self.assertIn("relay_service_effective_enabled | bool", self.bind_handler)
        self.assertNotIn("relay_service_effective_enabled | default(false)", self.bind_handler)
        self.assertIn("relay_service_effective_enabled: >-", self.group_vars)
        self.assertIn(
            "relay_service_enabled | bool and relay_service_activation_authorized | bool",
            self.group_vars.replace("\n", " "),
        )
        self.assertIn("relay_reviewer_bind_post_activation_authorized: false", self.group_vars)
        self.assertIn("relay_reviewer_bind_post_activation_authorized | bool", self.bind_handler)
        self.assertIn("/bin/systemctl", self.bind_handler)
        self.assertIn("try-restart", self.bind_handler)
        self.assertNotIn("state: restarted", self.bind_handler)
        self.assertEqual(bind_restart_operation(True, True, True, True), "try-restart")
        self.assertEqual(bind_restart_operation(True, True, True, False), "no-start")
        self.assertEqual(bind_restart_operation(True, True, False, True), "no-op")
        self.assertEqual(bind_restart_operation(True, True, True, True, check_mode=True), "no-op")

    def test_try_restart_uses_mutation_time_state_not_a_stale_snapshot(self):
        # The service was running during an earlier observation but stopped before
        # the handler mutation. try-restart must not turn that stale observation
        # into an unintended Reviewer start.
        self.assertEqual(bind_restart_operation(True, True, True, False), "no-start")
        self.assertIn("try-restart", self.bind_handler)
        self.assertNotIn("relay_reviewer_bind_service_active", self.bind_handler)



if __name__ == "__main__":
    unittest.main()
