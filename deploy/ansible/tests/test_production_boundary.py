"""Deterministic checks for the bounded production operator boundary."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from jinja2 import Environment, StrictUndefined, meta
import yaml


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_HOST = "192.0.2.10"
PRODUCTION_RUNNER = "relay-production-relay"


def privileged_linux_fixture_available():
    if os.name == "nt" or shutil.which("bash") is None or shutil.which("sudo") is None:
        return False
    if subprocess.run(
        ["bash", "-c", '[[ "$(uname -s)" == "Linux" ]]'], check=False, capture_output=True
    ).returncode != 0:
        return False
    return (
        subprocess.run(["sudo", "-n", "true"], check=False, capture_output=True).returncode == 0
        and subprocess.run(["id", "nobody"], check=False, capture_output=True).returncode == 0
    )


def activation_invocation_allowed(phase, authorized, requested_head, reviewed_head, dirty, target_set, endpoint_overrides):
    return (
        phase == "activate"
        and authorized
        and not dirty
        and requested_head == reviewed_head
        and target_set == {PRODUCTION_HOST}
        and not endpoint_overrides
    )


class ProductionBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.group_vars = (ROOT / "group_vars" / "all.yml").read_text(encoding="utf-8")
        self.preflight = (ROOT / "roles" / "relay_preflight" / "tasks" / "main.yml").read_text(encoding="utf-8")
        self.site = (ROOT / "site.yml").read_text(encoding="utf-8")
        self.reviewer_bind = (ROOT / "roles" / "relay_reviewer_bind" / "tasks" / "main.yml").read_text(encoding="utf-8")
        self.reviewer_config = (ROOT / "roles" / "relay_runtime" / "templates" / "reviewer-mcp.json.j2").read_text(encoding="utf-8")
        self.reviewer_source = (ROOT.parents[1] / "reviewer" / "src" / "main.rs").read_text(encoding="utf-8")
        self.helper = (ROOT / "roles" / "relay_runtime" / "templates" / "relay-credential-provision.j2").read_text(encoding="utf-8")
        self.runner = (ROOT / "roles" / "relay_runner" / "tasks" / "main.yml").read_text(encoding="utf-8")
        self.local_apply = (ROOT / "roles" / "relay_runner" / "templates" / "relay-production-local-apply.j2").read_text(encoding="utf-8")
        self.local_apply_sudoers = (ROOT / "roles" / "relay_runner" / "templates" / "relay-production-local-apply.sudoers.j2").read_text(encoding="utf-8")
        self.local_apply_tasks = (ROOT / "roles" / "relay_runner" / "tasks" / "production-local-apply.yml").read_text(encoding="utf-8")



    def test_activation_phase_rejects_dirty_head_target_and_ssh_override_cases(self):
        admitted = dict(
            phase="activate",
            authorized=True,
            requested_head="a" * 40,
            reviewed_head="a" * 40,
            dirty=False,
            target_set={PRODUCTION_HOST},
            endpoint_overrides=False,
        )
        self.assertTrue(activation_invocation_allowed(**admitted))
        for mutation in (
            {"dirty": True},
            {"requested_head": "b" * 40},
            {"target_set": {"198.51.100.10"}},
            {"endpoint_overrides": True},
            {"authorized": False},
        ):
            case = {**admitted, **mutation}
            self.assertFalse(activation_invocation_allowed(**case), mutation)





    def render_runner_policy(self, profile):
        source = (ROOT / "roles/relay_runner/templates/relay-runner.service.j2").read_text(encoding="utf-8")
        if profile == "production":
            source += (ROOT / "roles/relay_runner/templates/relay-runner-production-local-apply.conf.j2").read_text(encoding="utf-8")
        environment = Environment(undefined=StrictUndefined)
        context = {
            name: f"/fixture/{name}" for name in meta.find_undeclared_variables(environment.parse(source))
        }
        context.update(relay_deployment_profile=profile, relay_runner_labels=["fixture"])
        return environment.from_string(source).render(context)

    def test_production_sandbox_adds_only_root_owned_staging(self):
        policies = {profile: self.render_runner_policy(profile) for profile in ("production", "qualification")}
        writable = {
            profile: set(" ".join(line.split("=", 1)[1] for line in policy.splitlines()
                                 if line.startswith("ReadWritePaths=")).split())
            for profile, policy in policies.items()
        }
        self.assertEqual(writable["production"] - writable["qualification"],
                         {"/fixture/relay_production_local_apply_stage_root"})
        self.assertTrue(writable["qualification"] <= writable["production"])
        for policy in policies.values():
            for directive in ("ProtectSystem=strict", "ProtectHome=true", "PrivateTmp=true",
                              "User=/fixture/relay_runner_user", "Group=/fixture/relay_runner_group",
                              "ReadOnlyPaths=/fixture/relay_writer_credential_root"):
                self.assertIn(directive, policy.splitlines())
        self.assertIn("mode: '0700'", self.local_apply_tasks)
        self.assertIn("owner: root\n    group: root\n    mode: '0700'", self.local_apply_tasks)

    def test_host_namespace_transition_is_fixed_and_after_root_staging(self):
        transition = "/usr/bin/nsenter --mount=/proc/1/ns/mnt --"
        self.assertEqual(self.local_apply.count(transition), 1)
        self.assertLess(self.local_apply.index("runner_git archive"), self.local_apply.index(transition))
        self.assertLess(self.local_apply.index("STAGED_HEAD_MARKER_INVALID"), self.local_apply.index(transition))
        self.assertIn("/usr/bin/env -i HOME=/root PATH=/usr/bin:/bin", self.local_apply)
        self.assertNotIn("nsenter", self.local_apply_sudoers)

    def test_apply_reconciles_runner_sandbox_without_restarting_its_job(self):
        template_name = "relay-runner-production-local-apply.conf.j2"
        self.assertIn(f"src: {template_name}", self.local_apply_tasks)
        self.assertLess(self.local_apply_tasks.index("mode: '0700'"),
                        self.local_apply_tasks.index(f"src: {template_name}"))
        unit = next(task for task in yaml.safe_load(self.local_apply_tasks)
                    if task.get("ansible.builtin.template", {}).get("src") == template_name)
        self.assertEqual(unit["ansible.builtin.template"]["dest"],
                         "/etc/systemd/system/relay-runner.service.d/production-local-apply.conf")
        handlers = yaml.safe_load((ROOT / "roles/relay_runner/handlers/main.yml").read_text(encoding="utf-8"))
        selected = [handler for handler in handlers if handler["name"] in unit["notify"]]
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["ansible.builtin.systemd"], {"daemon_reload": True})
        self.assertNotIn("try-restart", str(handlers))

    @unittest.skipUnless(
        privileged_linux_fixture_available(),
        "Linux passwordless sudo and the nobody identity are required for the privilege-boundary fixture",
    )
    def test_hostile_runner_git_config_never_executes_across_the_root_boundary(self):
        """A real root helper must stage as root without consulting runner Git metadata."""
        self.run_local_apply_fixture(sandbox=False)

    @unittest.skipUnless(privileged_linux_fixture_available(), "Linux passwordless sudo is required")
    def test_runner_mount_namespace_staging_and_privileged_host_apply(self):
        """Reproduce EROFS, expose just staging, retain DAC, then exercise the fixed helper."""
        self.run_local_apply_fixture(sandbox=True)

    def run_local_apply_fixture(self, *, sandbox):
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture_root = Path(temporary_directory)
            fixture_root.chmod(0o755)
            checkout_root = fixture_root / "checkout"
            stage_root = fixture_root / "stage"
            audit_root = fixture_root / "audit"
            checkout_root.mkdir()
            stage_root.mkdir()
            audit_root.mkdir()
            runner_script = checkout_root / "deploy" / "relay.json"
            runner_script.parent.mkdir(parents=True)
            runner_script.write_text('{}\n')
            product = fixture_root / 'product'
            (product / 'current/reviewed-source/deploy').mkdir(parents=True)
            probe = product / 'current/reviewed-source/deploy/relay-deploy.py'
            probe.write_text(
                'import os,sys,subprocess\n'
                'from pathlib import Path\n'
                'assert os.geteuid()==0 and os.environ["HOME"]=="/root" and os.environ["PATH"]=="/usr/bin:/bin"\n'
                'assert "ANSIBLE_CONFIG" not in os.environ\n'
                'head=sys.argv[-1]\n'
                'os.chdir(Path(sys.argv[sys.argv.index("--config")+1]).parent.parent)\n'
                'assert subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()==head\n'
                'assert subprocess.check_output(["git","rev-list","--count","HEAD"],text=True).strip()=="1"\n'
                'assert not subprocess.run(["git","config","--get","core.fsmonitor"],capture_output=True).stdout\n'
                'assert Path(".git/config").stat().st_uid==0 and not Path(".git/objects/info/alternates").exists()\n'
                f'Path({str(audit_root / "staged-execution-identity")!r}).write_text("root")\n'
                f'Path({str(audit_root / "staged-tree-identity")!r}).write_text(subprocess.check_output(["git","ls-tree","-r",head,"--","deploy/relay.json"],text=True))\n'
                'print("PRODUCTION_APPLY_VALIDATED="+head)\n')
            for command in (
                ["git", "init", "-q"],
                ["git", "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid", "commit", "--allow-empty", "-qm", "parent omitted from staging"],
                ["git", "add", "deploy/relay.json"],
                ["git", "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture"],
                ["git", "remote", "add", "origin", "https://github.com/example/relay-consumer.git"],
            ):
                subprocess.run(command, cwd=checkout_root, check=True)
            actual_head = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=checkout_root, capture_output=True, text=True, check=True
            ).stdout.strip()
            expected_tree = subprocess.run(
                ["git", "ls-tree", "-r", actual_head, "--", "deploy/relay.json"],
                cwd=checkout_root, capture_output=True, text=True, check=True,
            ).stdout
            helper = self.local_apply.replace("{{ relay_production_local_apply_checkout_root }}", str(checkout_root))
            helper = helper.replace("{{ relay_production_local_apply_stage_root }}", str(stage_root))
            helper = helper.replace("{{ relay_runner_user }}", "nobody")
            helper = helper.replace("{{ relay_github_repository }}", "example/relay-consumer")
            helper = helper.replace("{{ relay_consumer_deployment_config_relative }}", "deploy/relay.json")
            helper = helper.replace("{{ relay_install_root }}", str(product))
            helper_path = fixture_root / "relay-production-local-apply"
            helper_path.write_text(helper, encoding="utf-8")
            helper_path.chmod(0o750)
            sandbox_path = fixture_root / "sandbox.sh"
            sandbox_path.write_text(
                "#!/bin/bash\nset -euo pipefail\n"
                "fixture=$1; stage=$2; helper=$3; head=$4\n"
                "mount --make-rprivate /\n"
                "mount --bind \"$fixture\" \"$fixture\"\n"
                "mount --bind \"$stage\" \"$stage\"\n"
                "mount -o remount,bind,ro \"$fixture\"\n"
                "mount -o remount,bind,ro \"$stage\"\n"
                "set +e\noutput=$(\"$helper\" \"$head\" 2>&1); rc=$?\nset -e\n"
                "[[ $rc != 0 && $output == *'Read-only file system'* ]]\n"
                "printf 'ORIGINAL_STAGING_EROFS_REPRODUCED\\n'\n"
                "mount -o remount,bind,rw \"$stage\"\n"
                "if runuser -u nobody -- ls \"$stage\"; then exit 91; fi\n"
                "if runuser -u nobody -- mktemp -d \"$stage/runner.XXXXXXXX\"; then exit 92; fi\n"
                "[[ $(stat -c '%U:%G:%a' \"$stage\") == root:root:700 ]]\n"
                "if touch \"$fixture/audit/forbidden\"; then exit 93; fi\n"
                "printf 'RUNNER_DAC_AND_SIBLING_READ_ONLY_VALIDATED\\n'\n"
                "ANSIBLE_CONFIG=/untrusted \"$helper\" \"$head\"\n"
                "[[ -z $(ls -A \"$stage\") ]]\n"
                "if touch \"$fixture/audit/after-helper\"; then exit 94; fi\n",
                encoding="utf-8",
            )
            fsmonitor_identity = audit_root / "fsmonitor-identity"
            fsmonitor = fixture_root / "hostile-fsmonitor"
            fsmonitor.write_text("#!/bin/sh\n/usr/bin/id -u > " + str(fsmonitor_identity) + "\n", encoding="utf-8")
            fsmonitor.chmod(0o755)
            subprocess.run(["git", "config", "core.fsmonitor", str(fsmonitor)], cwd=checkout_root, check=True)
            try:
                subprocess.run(["sudo", "-n", "chown", "-R", "nobody:nogroup", str(checkout_root)], check=True)
                subprocess.run(["sudo", "-n", "chown", "root:root", str(stage_root)], check=True)
                subprocess.run(["sudo", "-n", "chmod", "0700", str(stage_root)], check=True)
                command = ["sudo", "-n", str(helper_path), actual_head]
                if sandbox:
                    command = ["sudo", "-n", "unshare", "--mount", "/bin/bash", str(sandbox_path),
                               str(fixture_root), str(stage_root), str(helper_path), actual_head]
                result = subprocess.run(command, capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
                self.assertIn(f"PRODUCTION_APPLY_VALIDATED={actual_head}", result.stdout)
                self.assertEqual(result.stdout.count(f"PRODUCTION_APPLY_VALIDATED={actual_head}"), 1)
                if sandbox:
                    self.assertIn("ORIGINAL_STAGING_EROFS_REPRODUCED", result.stdout)
                    self.assertIn("RUNNER_DAC_AND_SIBLING_READ_ONLY_VALIDATED", result.stdout)
                self.assertFalse(fsmonitor_identity.exists(), "runner Git config executed during the root helper path")
                # The staged root script inherits umask 077; keep its evidence private.
                identity = subprocess.run(
                    ["sudo", "-n", "cat", str(audit_root / "staged-execution-identity")],
                    capture_output=True, text=True, check=True,
                ).stdout
                self.assertEqual(identity, "root")
                tree_identity = subprocess.run(
                    ["sudo", "-n", "cat", str(audit_root / "staged-tree-identity")],
                    capture_output=True, text=True, check=True,
                ).stdout
                self.assertEqual(tree_identity, expected_tree)
            finally:
                # Reclaim checkout, audit, stage and any partial state before ordinary cleanup.
                subprocess.run(
                    ["sudo", "-n", "chown", "-R", "--no-dereference", f"{os.getuid()}:{os.getgid()}", str(fixture_root)],
                    check=True,
                )
                subprocess.run(
                    ["sudo", "-n", "chmod", "-R", "u+rwX", str(fixture_root)],
                    check=True,
                )


    def test_production_credential_gate_includes_codex_token_without_secret_channels(self):
        for marker in (
            "relay_deployment_profile }}' = 'production'",
            "relay_codex_access_token_file",
            "stty -echo </dev/tty",
            "CREDENTIAL_PROVISIONING_CODEX_TOKEN_EMPTY",
            "CREDENTIAL_PROVISIONING_CODEX_TOKEN_INPUT_FAILED",
            "CREDENTIAL_PROVISIONING_CODEX_TOKEN_READY",
            "CREDENTIAL_PROVISIONING_READY",
        ):
            self.assertIn(marker, self.helper)
        self.assertNotIn("--token", self.helper)
        self.assertNotIn("GITHUB_TOKEN=", self.helper)



    def test_retired_unix_transport_is_not_a_configurable_runtime_surface(self):
        for active_text in (self.group_vars, self.reviewer_bind, self.reviewer_config):
            for forbidden in (
                "relay_reviewer_socket_path",
                "REVIEWER_MCP_SOCKET",
                "mcp.sock",
                "a_only_unix_socket",
                "proxy_pass http://unix:",
            ):
                self.assertNotIn(forbidden, active_text)
        self.assertNotIn("UnixListener", self.reviewer_source)
        self.assertNotIn("REVIEWER_MCP_HOST", self.reviewer_source)
        self.assertIn("bind_socket", self.reviewer_source)


if __name__ == "__main__":
    unittest.main()
