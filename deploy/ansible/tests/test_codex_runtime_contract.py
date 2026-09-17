"""Static regressions for the governed qualification Codex runtime boundary."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def codex_membership_is_reconcilable_in_check_mode(
    check_mode, primary_group_planned, work_group_planned, codex_user_changed, codex_user_skipped
):
    """Model the Codex membership gate without touching a host."""
    codex_user_planned = primary_group_planned or codex_user_changed or codex_user_skipped
    return (not check_mode) or not any(
        (primary_group_planned, work_group_planned, codex_user_planned)
    )


def runner_membership_is_reconcilable_in_check_mode(
    check_mode, work_group_planned, getent_passwd, runner_user
):
    """Model the runner membership gate without touching a host."""
    return (not check_mode) or (
        not work_group_planned
        and runner_user_materialized_from_getent(getent_passwd, runner_user)
    )


def runner_user_materialized_from_getent(getent_passwd, runner_user):
    """Classify the actual Ansible getent passwd result shape."""
    return bool(getent_passwd.get(runner_user))


class CodexRuntimeContractTests(unittest.TestCase):
    def setUp(self):
        self.group_vars = (ROOT / "group_vars" / "all.yml").read_text(encoding="utf-8")
        self.role = (ROOT / "roles" / "relay_codex_runtime" / "tasks" / "main.yml").read_text(encoding="utf-8")
        self.runtime_namespace = (ROOT / "roles" / "relay_codex_runtime" / "tasks" / "runtime-namespace.yml").read_text(encoding="utf-8")
        self.token_role = (ROOT / "roles" / "relay_codex_runtime" / "tasks" / "token.yml").read_text(encoding="utf-8")
        self.launcher = (ROOT / "roles" / "relay_codex_runtime" / "templates" / "relay-codex-launcher.mjs.j2").read_text(encoding="utf-8")
        self.diagnostic = (ROOT / "roles" / "relay_codex_runtime" / "files" / "relay-codex-diagnostic.mjs").read_text(encoding="utf-8")
        self.sudoers = (ROOT / "roles" / "relay_codex_runtime" / "templates" / "relay-codex.sudoers.j2").read_text(encoding="utf-8")
        self.site = (ROOT / "site.yml").read_text(encoding="utf-8")
        self.writer_helper = (ROOT.parent.parent / "controller" / "src" / "privileged-writer-helper.mjs").read_text(encoding="utf-8")
        self.controller_role = (ROOT / "roles" / "relay_controller" / "tasks" / "main.yml").read_text(encoding="utf-8")
        self.writer_binding_validation = (ROOT / "tasks" / "production-writer-binding-validation.yml").read_text(encoding="utf-8")
        self.artifacts_role = (ROOT / "roles" / "relay_artifacts" / "tasks" / "main.yml").read_text(encoding="utf-8")
        self.diagnostics_sudoers = (ROOT / "roles" / "relay_controller" / "templates" / "relay-diagnostics.sudoers.j2").read_text(encoding="utf-8")
        self.diagnostics_wrapper = (ROOT / "roles" / "relay_controller" / "templates" / "relay-diagnostics-store.j2").read_text(encoding="utf-8")
        self.diagnostics_control = (ROOT / "roles" / "relay_controller" / "templates" / "relay-diagnostics-control.mjs.j2").read_text(encoding="utf-8")
        self.diagnostic_snapshot = (ROOT / "roles" / "relay_controller" / "templates" / "relay-qualification-diagnostic-snapshot.mjs.j2").read_text(encoding="utf-8")

    def test_runtime_is_pinned_and_governed_by_ansible(self):
        for marker in (
            "relay_codex_cli_version: '0.154.0'",
            "relay_codex_installer_url: https://chatgpt.com/codex/install.sh",
            "relay_codex_binary_path:",
            "relay_codex_launcher_path:",
            "relay_codex_access_token_file:",
            "CODEX_RUNTIME_CHECK_MODE_PLAN",
            "--release",
            "CODEX_NON_INTERACTIVE",
            "CODEX_RUNTIME_VERSION_MISMATCH",
            "CODEX_RUNTIME_PASS",
        ):
            self.assertIn(marker, self.group_vars + self.role)
        self.assertIn("role: relay_codex_runtime", self.site)

    def test_token_is_separate_and_rotatable_without_cli_reinstall(self):
        for marker in (
            "CODEX_ACCESS_TOKEN",
            "no_log: true",
            "mode: '0600'",
            "CODEX_TOKEN_ROTATION_PASS",
        ):
            self.assertIn(marker, self.token_role)
        self.assertNotIn("CODEX_ACCESS_TOKEN", self.group_vars)

    def test_launcher_restricts_arguments_paths_and_environment(self):
        self.assertTrue(self.launcher.startswith("#!/usr/bin/node --experimental-default-type=module\n"))
        for marker in (
            "CODEX_ACCESS_TOKEN",
            "ACCESS_TOKEN_UNAVAILABLE",
            "MAX_TOKEN_BYTES",
            "MAX_INPUT_BYTES",
            "ARGUMENT_CONTRACT_INVALID",
            "safeModel(model)",
            "safeEffort(effort)",
            "PATH_OUTSIDE_WORK_ROOT",
            "INPUT_PATH_INVALID",
            "INPUT_FILE_UNREADABLE",
            "INPUT_TOO_LARGE",
            "model_reasoning_effort=",
            '"--sandbox", "workspace-write"',
            '"sandbox_workspace_write.network_access=true"',
            'PATH: "{{ relay_rust_toolchain_root }}/bin:/usr/bin:/bin"',
            'CARGO_HOME: join(cache, "cargo")',
            '"--add-dir", gitRoot',
            '"--output-schema", schema',
            'join(cwd, ".git")',
            'const sandbox = ".codex-sandbox"',
            'const schemaName = "codex-result-schema.json"',
            'codex-result-schema.json',
            '"review-remediation"',
            '"--pull-request"',
            "GIT_METADATA_INVALID",
            "OUTPUT_SCHEMA_INVALID",
            "--cd",
            "child.stdin.end",
            "GIT_CONFIG_NOSYSTEM",
            "GIT_CONFIG_COUNT",
            "GIT_CONFIG_KEY_0",
            "GIT_CONFIG_VALUE_0: cwd",
            'GIT_AUTHOR_NAME: operation === "review-remediation"',
            'relay_writer_commit_name | to_json',
            'relay_remediation_commit_name | to_json',
            "stdio: [\"pipe\", \"pipe\", \"pipe\"]",
            "child.stderr.on(\"data\"",
            "child.stdout.on(\"data\"",
            "createStatefulSecretRedactor",
            "assertSecretFreePublication",
            "MAX_DIAGNOSTIC_CAPTURE_BYTES",
            "writeChildDiagnostic",
            "relay-codex-diagnostic.mjs",
            "process.umask(0o0007);",
            "let childStarted = false",
            'child.once("spawn", () => { childStarted = true; observedChildStarted = true; })',
        ):
            self.assertIn(marker, self.launcher)
        self.assertNotIn("const childStarted = true", self.launcher)
        for marker in ("[REDACTED_CODEX_ACCESS_TOKEN]", "[REDACTED_SECRET]", "MAX_DIAGNOSTIC_PREVIEW_BYTES", "truncated", "never log request content"):
            self.assertIn(marker, self.diagnostic.lower() if marker == "never log request content" else self.diagnostic)
        self.assertNotIn("GITHUB_TOKEN", self.launcher)
        self.assertNotIn("OPENAI_API_KEY", self.launcher)
        self.assertIn("!setenv", self.sudoers)
        self.assertIn(
            "ALL=({{ relay_codex_user }}) NOPASSWD: {{ relay_codex_launcher_path }}",
            self.sudoers,
        )
        self.assertNotIn("relay_writer_credential_root", self.launcher)
        self.assertNotIn("relay_reviewer_credential_root", self.launcher)
        self.assertNotIn("dangerously-bypass-approvals-and-sandbox", self.launcher)

    def test_codex_runtime_role_verifies_runtime_without_reading_token_contents(self):
        for marker in (
            "CODEX_RUNTIME_PIN_OR_BOUNDARY_INVALID",
            "relay_codex_binary_path",
            "relay_codex_access_token_file",
            "CODEX_RUNTIME_VERSION_MISMATCH",
            "without reading its contents",
        ):
            self.assertIn(marker, self.role)
        self.assertIn("relay_codex_work_group", self.role)
        self.assertIn("Add the unprivileged relay runner to the shared Codex work group", self.role)
        self.assertIn("relay_runner_codex_group_membership", self.role)
        self.assertIn("Restart the active relay runner through the governed service contract", self.role)
        self.assertIn("state: restarted", self.role)
        self.assertIn("packages/standalone/releases/' ~ relay_codex_cli_version ~ '-'", self.role)
        self.assertIn("/usr/sbin/runuser', '-u', '{{ relay_runner_user }}'", self.role)
        self.assertIn("2770", self.role)

    def test_full_site_codex_dependency_order_is_check_mode_safe(self):
        primary_group = self.role.index("name: Create the dedicated Codex primary group")
        work_group = self.role.index("name: Create the dedicated Codex work group")
        codex_user = self.role.index("name: Create the non-login Codex execution identity")
        codex_membership = self.role.index("name: Add the Codex execution identity to the shared Codex work group")
        runner_membership = self.role.index("name: Add the unprivileged relay runner to the shared Codex work group")
        self.assertLess(primary_group, work_group)
        self.assertLess(work_group, codex_user)
        self.assertLess(codex_user, codex_membership)
        self.assertLess(codex_membership, runner_membership)
        for marker in (
            "register: relay_codex_group_reconciliation",
            "register: relay_codex_work_group_reconciliation",
            "register: relay_codex_user_reconciliation",
            "CODEX_RUNTIME_CHECK_MODE_PLAN=official-standalone",
            "deferred_until_dependencies_exist",
            "planned_against_existing_dependencies",
            "mutation=none",
            "ansible.builtin.getent",
            "relay_codex_runner_user_state",
            "relay_codex_primary_group_planned",
            "relay_codex_work_group_planned",
            "relay_codex_user_skipped",
            "relay_codex_user_planned",
            "relay_codex_user_materialized",
            "relay_codex_runner_user_materialized",
            "get(relay_runner_user)",
            "default([], true)",
            "| length) > 0",
            "relay_codex_user_work_group_membership",
            "relay_runner_codex_group_membership",
        ):
            self.assertIn(marker, self.role)
        self.assertNotIn("relay_base_runner_user_reconciliation", self.role)
        identity_section = self.role[: self.role.index("name: Record the dependency-aware Codex runtime plan")]
        self.assertNotIn("check_mode: false", identity_section)
        self.assertIn("not ansible_check_mode | bool or not relay_codex_primary_group_planned | bool", self.role)
        self.assertIn("role: relay_codex_runtime", self.site)
        self.assertLess(self.site.index("role: relay_base"), self.site.index("role: relay_codex_runtime"))

    def test_check_mode_dependency_cases_are_non_mutating_and_apply_is_unchanged(self):
        runner_user = "relay-runner"
        matrix = (
            # fresh host: both groups are planned and the user task is skipped
            (True, True, True, False, True, {runner_user: None}, False, False),
            # fully existing dependencies
            (True, False, False, False, False, {runner_user: ["x", "x", "x"]}, True, True),
            # normal apply: dependencies are materialized in task order
            (False, True, True, True, False, {runner_user: ["x", "x", "x"]}, True, True),
            # mixed partial state: primary group planned, work group existing
            (True, True, False, False, True, {runner_user: ["x", "x", "x"]}, False, True),
            # existing primary group, Codex user only planned
            (True, False, False, True, False, {runner_user: ["x", "x", "x"]}, False, True),
            # mixed partial state: work group existing, runner result is present but None
            (True, False, False, False, False, {runner_user: None}, True, False),
        )
        for (
            check_mode,
            primary,
            work,
            user_changed,
            user_skipped,
            getent_passwd,
            codex_expected,
            runner_expected,
        ) in matrix:
            self.assertEqual(
                codex_membership_is_reconcilable_in_check_mode(
                    check_mode, primary, work, user_changed, user_skipped
                ),
                codex_expected,
            )
            self.assertEqual(
                runner_membership_is_reconcilable_in_check_mode(
                    check_mode, work, getent_passwd, runner_user
                ),
                runner_expected,
            )
        self.assertFalse(codex_membership_is_reconcilable_in_check_mode(True, True, False, False, True))
        self.assertFalse(codex_membership_is_reconcilable_in_check_mode(True, False, False, True, False))
        self.assertFalse(
            runner_membership_is_reconcilable_in_check_mode(
                True, False, {runner_user: None}, runner_user
            )
        )
        self.assertTrue(
            runner_membership_is_reconcilable_in_check_mode(
                True, False, {runner_user: ["x", "x", "x"]}, runner_user
            )
        )
        self.assertIn("not ansible_check_mode | bool or not relay_codex_work_group_planned | bool", self.role)
        self.assertIn("not ansible_check_mode | bool or relay_codex_runner_user_materialized | bool", self.role)
        self.assertIn("append: true", self.role)

    def test_runtime_avoids_deterministic_release_and_cli_replay(self):
        staging = (ROOT / 'roles/relay_artifacts/tasks/stage-source.yml').read_text()
        self.assertIn("relay_release_manifest", staging)
        self.assertIn("not relay_release_manifest.stat.exists", staging)
        self.assertIn("relay_codex_existing_version", self.role)
        self.assertIn("relay_codex_install_needed", self.role)
        self.assertIn("relay_codex_install_needed | bool", self.role)
        self.assertNotIn("- '{{ relay_release_path }}/reviewed-source'\n\n- name: Allow runtime traversal", self.artifacts_role)
        self.assertIn("- '{{ relay_release_path }}/reviewer-source'\n\n- name: Allow runtime traversal", self.artifacts_role)

    def test_codex_arg0_temp_root_is_reconciled_after_root_install(self):
        install = self.role.index("name: Install the pinned official Codex CLI into the relay namespace")
        arg0_reconciliation = self.role.index("include_tasks: runtime-namespace.yml")
        binary_inspection = self.role.index("name: Inspect the installed Codex binary without authentication")
        self.assertLess(install, arg0_reconciliation)
        self.assertLess(arg0_reconciliation, binary_inspection)
        for marker in (
            "name: Reconcile the Codex temporary roots for the runtime identity",
            "path: '{{ relay_codex_home }}/tmp'",
            "path: '{{ relay_codex_home }}/tmp/arg0'",
            "state: directory",
            "owner: '{{ relay_codex_user }}'",
            "group: '{{ relay_codex_group }}'",
            "mode: '0700'",
        ):
            self.assertIn(marker, self.runtime_namespace)
        roots = self.runtime_namespace.index("name: Reconcile the Codex temporary roots for the runtime identity")
        descendants = self.runtime_namespace.index("name: Reconcile ownership of stale Codex arg0 temporary descendants")
        self.assertLess(roots, descendants)
        descendants_task = self.runtime_namespace[descendants:]
        for marker in (
            "path: '{{ relay_codex_home }}/tmp/arg0'",
            "state: directory",
            "owner: '{{ relay_codex_user }}'",
            "group: '{{ relay_codex_group }}'",
            "recurse: true",
        ):
            self.assertIn(marker, descendants_task)
        self.assertNotIn("mode: '0700'", descendants_task)
        self.assertIn("when: not ansible_check_mode | bool", self.role)
        self.assertIn('role: relay_codex_runtime', self.site)
        self.assertIn('ansible.builtin.include_tasks: runtime-namespace.yml', self.role)
        self.assertNotIn('relay_production_reviewer_restore_only', self.site)

    def test_writer_helper_preserves_reviewed_source_import_topology(self):
        expected_path = "relay_writer_helper_release_path: '{{ relay_install_root }}/current/reviewed-source/controller/src/privileged-writer-helper.mjs'"
        self.assertIn(expected_path, self.group_vars)
        self.assertNotIn("relay_writer_helper_release_path: '{{ relay_release_path }}/bin/relay-writer-controller.mjs'", self.group_vars)
        self.assertIn(
            "relay_install_root ~ '/current/reviewed-source/controller/src/privileged-writer-helper.mjs'",
            self.writer_binding_validation,
        )
        self.assertIn("from './publication-broker.mjs'", self.writer_helper)
        self.assertIn("include_tasks: stage-source.yml", self.artifacts_role)

    def test_diagnostics_are_two_mode_operator_state_with_fixed_root_store(self):
        for marker in (
            "relay_diagnostics_mode: normal",
            "relay_diagnostics_root:",
            "relay_diagnostics_store_path:",
            "relay_diagnostics_control_path:",
            "relay_diagnostics_mode in ['normal', 'debug']",
            "relay_diagnostics_mode",
            "retentionCount",
            "mode: '0700'",
            "mode: '0644'",
            "visudo",
        ):
            self.assertIn(marker, self.group_vars + self.controller_role + self.artifacts_role)
        self.assertIn("NOPASSWD: {{ relay_diagnostics_store_path }}", self.diagnostics_sudoers)
        self.assertIn("test \"$#\" -eq 0", self.diagnostics_wrapper)
        self.assertIn("typed JSON", self.diagnostics_wrapper)
        for marker in (
            "DIAGNOSTICS_CONFIG_PATH = \"{{ relay_config_root }}/diagnostics.json\"",
            "new Set([\"normal\", \"debug\"])",
            "openSync(temporary, \"wx\"",
            "renameSync(temporary, configPath)",
            "Usage: relay-diagnostics-control get|set normal|debug",
        ):
            self.assertIn(marker, self.diagnostics_control)
        self.assertIn("not relay_diagnostics_config.stat.exists", self.controller_role)
        controller_config = (ROOT / "roles" / "relay_controller" / "templates" / "relay-controller.json.j2").read_text(encoding="utf-8")
        self.assertIn('"defaultMode": "{{ relay_diagnostics_mode }}"', controller_config)
        self.assertIn('"modeControl": "{{ relay_diagnostics_control_path }}"', controller_config)
        self.assertIn('"stateOwner": "trusted-production-operator"', controller_config)
        self.assertNotIn("trusted-stage-a-operator", controller_config)

    def test_grouped_qualification_snapshot_is_read_only_and_omits_protected_bodies(self):
        for marker in (
            "--claim", "--execution", "protectedBodies: \"omitted\"",
            "claimRecords", "dispatchRecords", "debugBundles", "diagnosticsMode",
            "relay-qualification-diagnostic-snapshot.mjs",
        ):
            self.assertIn(marker, self.diagnostic_snapshot + self.controller_role)
        for forbidden in ("value.stderr", "value.stdout", "value.environment", "value.argv", "value.body", "value.prBody"):
            self.assertNotIn(forbidden, self.diagnostic_snapshot)
        self.assertIn("mode: '0750'", self.controller_role)


if __name__ == "__main__":
    unittest.main()
