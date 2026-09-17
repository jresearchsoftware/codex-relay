"""Regression checks for relay fresh-host systemd lifecycle gates."""

import os
import shutil
import subprocess
import unittest
from pathlib import Path

from jinja2 import Environment, StrictUndefined
import yaml


ROOT = Path(__file__).resolve().parents[1]
RUNNER_TASKS = ROOT / "roles" / "relay_runner" / "tasks" / "main.yml"
RUNNER_SERVICE = ROOT / "roles" / "relay_runner" / "templates" / "relay-runner.service.j2"
RUNNER_REGISTRATION = ROOT / "roles" / "relay_runner" / "templates" / "relay-runner-registration.j2"
RUNNER_ARCHIVE_CHECK = ROOT / "roles" / "relay_runner" / "files" / "relay-runner-archive-check.py"
CONTROLLER_TASKS = ROOT / "roles" / "relay_controller" / "tasks" / "main.yml"
WRITER_ENTRYPOINT_TASKS = ROOT / "roles" / "relay_controller" / "tasks" / "writer-entrypoint.yml"
RUNTIME_TASKS = ROOT / "roles" / "relay_runtime" / "tasks" / "main.yml"


def planned_service_action(check_mode, unit_exists):
    """Model the systemd boundary without invoking a live service manager."""
    if check_mode and not unit_exists:
        return "VALIDATE_PLAN_ONLY"
    return "ENFORCE_DESIRED_STATE"


class RunnerLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.lifecycle_tasks = {
            "runner": RUNNER_TASKS.read_text(encoding="utf-8"),
            "controller": "\n".join(
                (
                    CONTROLLER_TASKS.read_text(encoding="utf-8"),
                    WRITER_ENTRYPOINT_TASKS.read_text(encoding="utf-8"),
                )
            ),
            "runtime": RUNTIME_TASKS.read_text(encoding="utf-8"),
        }

    def test_fresh_absent_unit_check_mode_validates_plan_without_systemd_call(self):
        self.assertEqual(planned_service_action(True, False), "VALIDATE_PLAN_ONLY")
        for name, marker in (
            ("runner", "RUNNER_CHECK_MODE_PLANNED_STATE"),
            ("controller", "WRITER_HELPER_CHECK_MODE_PLAN"),
            ("runtime", "RUNTIME_CHECK_MODE_PLANNED_STATE"),
        ):
            with self.subTest(role=name):
                self.assertIn(marker, self.lifecycle_tasks[name])
                self.assertIn("ansible.builtin.stat", self.lifecycle_tasks[name])

    def test_post_apply_reconcile_check_mode_enforces_existing_unit_state(self):
        self.assertEqual(planned_service_action(True, True), "ENFORCE_DESIRED_STATE")
        self.assertIn("relay_runner_unit.stat.exists", self.lifecycle_tasks["runner"])
        self.assertIn("relay_controller_unit.stat.exists", self.lifecycle_tasks["controller"])
        self.assertIn("relay_runtime_unit.stat.exists", self.lifecycle_tasks["runtime"])
        self.assertNotIn("relay_runtime_units.results", self.lifecycle_tasks["runtime"])
        self.assertIn("relay_runner_service_enabled", self.lifecycle_tasks["runner"])
        self.assertIn("relay_writer_claim_root", self.lifecycle_tasks["controller"])
        self.assertIn("relay_service_enabled", self.lifecycle_tasks["runtime"])

    def test_registration_and_enablement_remain_gated(self):
        for marker in (
            "relay_runner_registration_authorized",
            "relay_runner_registration_completed",
            "relay_runner_repository == relay_github_repository",
        ):
            self.assertIn(marker, self.lifecycle_tasks["runner"])

    def test_pinned_package_and_mutable_state_are_source_controlled(self):
        tasks = self.lifecycle_tasks["runner"]
        for marker in (
            "relay_runner_package_version",
            "relay_runner_package_sha256",
            "relay_runner_package_url",
            "relay-runner-archive-check.py",
            "RUNNER_PACKAGE_ARCHIVE_INVALID",
            "RUNNER_INSTALLED_VERSION_MISMATCH",
            "relay_runner_root",
            "relay_runner_work_root",
        ):
            self.assertIn(marker, tasks)
        self.assertNotIn("current/bin/actions-runner", tasks)
        self.assertIn("ReadWritePaths={{ relay_runner_root }} {{ relay_runner_work_root }} {{ relay_runner_home }} {{ relay_log_root }} {{ relay_writer_claim_root }} {{ relay_diagnostics_root }} {{ relay_codex_home }} {{ relay_dispatch_state_root }} {{ relay_dispatch_work_root }} {{ relay_dispatch_home }}", RUNNER_SERVICE.read_text(encoding="utf-8"))

    def test_runner_diagnostics_are_mutable_runner_owned_state(self):
        tasks = self.lifecycle_tasks["runner"]
        for marker in (
            "{{ relay_runner_root }}/_diag",
            "relay_runner_diagnostic_files",
            "relay_runner_post_probe_diagnostic_files",
            "Enforce runner ownership of all diagnostic files after probes",
            "mode: '0750'",
            '"0600" if item.mode == "0600" else "0640"',
        ):
            self.assertIn(marker, tasks)
        self.assertIn("ReadWritePaths={{ relay_runner_root }} {{ relay_runner_work_root }} {{ relay_runner_home }} {{ relay_log_root }} {{ relay_writer_claim_root }} {{ relay_diagnostics_root }} {{ relay_codex_home }} {{ relay_dispatch_state_root }} {{ relay_dispatch_work_root }} {{ relay_dispatch_home }}", RUNNER_SERVICE.read_text(encoding="utf-8"))
        self.assertIn("relay_state_root }}', owner: root, group: '{{ relay_group }}', mode: '0755'", tasks)
        self.assertLess(tasks.index("Create runner diagnostic namespace"), tasks.index("Verify installed runner reports the pinned version"))
        self.assertIn("become_user: '{{ relay_runner_user }}'", tasks)
        self.assertLess(tasks.index("Enforce runner ownership of all diagnostic files after probes"), tasks.index("Install owner-mediated runner registration helper"))

    def test_registration_helper_never_places_token_in_argv_or_persists_it(self):
        helper = RUNNER_REGISTRATION.read_text(encoding="utf-8")
        for marker in ("ACTIONS_RUNNER_INPUT_TOKEN", "read -r -s", "--disableupdate", "RUNNER_REGISTRATION_PASS", "REGISTRATION_ALREADY_PRESENT", "normalize_diagnostics", "runuser --preserve-environment --user '{{ relay_runner_user }}'"):
            self.assertIn(marker, helper)
        self.assertNotIn("--token", helper)
        self.assertNotIn("GITHUB_APP", helper)
        self.assertIn("unset registration_value ACTIONS_RUNNER_INPUT_TOKEN", helper)

    def test_registration_targets_the_restricted_org_group_only_for_production(self):
        environment = Environment(undefined=StrictUndefined)
        template = environment.from_string(RUNNER_REGISTRATION.read_text(encoding="utf-8"))
        variables = yaml.safe_load((ROOT / "group_vars" / "all.yml").read_text(encoding="utf-8"))
        for profile, url, group_args in (
            ("production", "https://github.com/example",
             "registration_group_args=(--runnergroup 'relay-production')"),
            ("qualification", "https://github.com/example/relay-consumer",
             "registration_group_args=()"),
        ):
            with self.subTest(profile=profile):
                helper = template.render(
                    variables, relay_deployment_profile=profile,
                    relay_runner_registration_scope='organization' if profile == 'production' else 'repository',
                )
                if os.name != "nt" and shutil.which("bash"):
                    syntax = subprocess.run(["bash", "-n"], input=helper, text=True,
                                            capture_output=True, check=False)
                    self.assertEqual(syntax.returncode, 0, syntax.stderr)
                self.assertIn(f"--url '{url}'", helper)
                self.assertIn(group_args, helper)
                self.assertEqual(helper.count("exec ./config.sh"), 1)
                self.assertIn('"${registration_group_args[@]}"', helper)
                self.assertNotIn("--token", helper)
                self.assertIn("REGISTRATION_ALREADY_PRESENT", helper)
                if profile == "qualification":
                    self.assertNotIn("--runnergroup", helper)
                else:
                    self.assertNotIn("--url 'https://github.com/example/relay-consumer'", helper)

    def test_registration_binding_rejects_the_old_production_repository_scope(self):
        tasks = yaml.safe_load(self.lifecycle_tasks["runner"])
        binding = next(task for task in tasks if task["name"] ==
                       "Detect and validate factual runner registration completion")
        expressions = [Environment(undefined=StrictUndefined).compile_expression(expression)
                       for expression in binding["ansible.builtin.assert"]["that"]]
        for profile in ("production", "qualification"):
            expected_url = ("https://github.com/example" if profile == "production"
                            else "https://github.com/example/relay-consumer")
            for url in ("https://github.com/example",
                        "https://github.com/example/relay-consumer",
                        "https://github.com/untrusted"):
                for name, work in (("expected-runner", "/work"), ("wrong", "/work"),
                                   ("expected-runner", "/wrong")):
                    with self.subTest(profile=profile, url=url, name=name, work=work):
                        values = {
                            "relay_github_repository": "example/relay-consumer",
                            "relay_deployment_profile": profile,
                            "relay_runner_registration_scope": "organization" if profile == "production" else "repository",
                            "relay_runner_name": "expected-runner",
                            "relay_runner_work_root": "/work",
                            "relay_runner_registration_state": {
                                "gitHubUrl": url, "agentName": name, "workFolder": work,
                            },
                        }
                        self.assertEqual(all(expression(**values) for expression in expressions),
                                         url == expected_url and name == "expected-runner" and work == "/work")

    def test_archive_validator_rejects_links_and_path_traversal(self):
        validator = RUNNER_ARCHIVE_CHECK.read_text(encoding="utf-8")
        for marker in ("UNSAFE_MEMBER_PATH", "UNSAFE_LINK_TARGET", "MALFORMED_ARCHIVE", "REQUIRED_ENTRYPOINT_MISSING", "RUNNER_ARCHIVE_VALID version=2.336.0"):
            self.assertIn(marker, validator)


if __name__ == "__main__":
    unittest.main()
