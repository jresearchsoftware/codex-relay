"""Focused regressions for the production root Codex launcher binding."""

import hashlib
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


def launcher_contract_is_current(source):
    """Model the non-secret launcher contract gate without starting Codex."""
    return all(
        marker in source
        for marker in (
            "const issueMode = argv.length === 12",
            "const remediationMode = argv.length === 14",
            'argv[2] === "review-remediation"',
            'argv[12] === "--pull-request"',
            'if (!issueMode && !remediationMode) fail("ARGUMENT_CONTRACT_INVALID");',
        )
    )


def artifact_hash_matches(source, expected_sha256):
    """Model the exact byte binding used by the production post-check."""
    return hashlib.sha256(source.encode("utf-8")).hexdigest() == expected_sha256


class ProductionCodexLauncherBindingTests(unittest.TestCase):
    def setUp(self):
        self.site = (ROOT / "site.yml").read_text(encoding="utf-8")
        self.launcher_tasks = (
            ROOT / "roles" / "relay_codex_runtime" / "tasks" / "launcher.yml"
        ).read_text(encoding="utf-8")
        self.launcher_validation = (
            ROOT
            / "roles"
            / "relay_codex_runtime"
            / "tasks"
            / "production-launcher-validation.yml"
        ).read_text(encoding="utf-8")
        self.runtime_tasks = (
            ROOT / "roles" / "relay_codex_runtime" / "tasks" / "main.yml"
        ).read_text(encoding="utf-8")
        self.launcher = (
            ROOT
            / "roles"
            / "relay_codex_runtime"
            / "templates"
            / "relay-codex-launcher.mjs.j2"
        ).read_text(encoding="utf-8")
        self.launcher_wrapper = (
            ROOT
            / "roles"
            / "relay_codex_runtime"
            / "templates"
            / "relay-codex-launcher-wrapper.sh.j2"
        ).read_text(encoding="utf-8")
        self.identities = (
            ROOT / "roles" / "relay_artifacts" / "tasks" / "resolve-identities.yml"
        ).read_text(encoding="utf-8")
        self.manifest = (
            ROOT
            / "roles"
            / "relay_artifacts"
            / "templates"
            / "artifact-manifest.json.j2"
        ).read_text(encoding="utf-8")
        self.adapter = (
            ROOT.parent.parent
            / "controller"
            / "src"
            / "attempt-runtime.mjs"
        ).read_text(encoding="utf-8")
        self.dispatcher = (
            ROOT.parent.parent
            / "controller"
            / "src"
            / "codex-dispatch.mjs"
        ).read_text(encoding="utf-8")
        self.group_vars = (ROOT / "group_vars" / "all.yml").read_text(
            encoding="utf-8"
        )

    def test_full_runtime_role_reconciles_the_shared_launcher_and_namespaces(self):
        role = next(entry for entry in yaml.safe_load(self.site)[1]['roles']
                    if entry['role'] == 'relay_codex_runtime')
        self.assertNotIn('when', role)
        self.assertIn('ansible.builtin.include_tasks: launcher.yml', self.runtime_tasks)
        self.assertIn('ansible.builtin.include_tasks: runtime-namespace.yml', self.runtime_tasks)

    def test_exact_candidate_identity_and_rendered_artifact_are_bound(self):
        source_path = (
            "deploy/ansible/roles/relay_codex_runtime/templates/"
            "relay-codex-launcher.mjs.j2"
        )
        for marker in (
            "git",
            "ls-tree",
            source_path,
            "relay_codex_launcher_source_tree_sha256",
            "codexLauncherSourceTreeSha256",
        ):
            self.assertIn(marker, self.identities + self.manifest + (ROOT.parent / "relay-deploy.py").read_text())

        for marker in (
            "lookup('template', 'relay-codex-launcher.mjs.j2')",
            "relay_production_expected_codex_launcher_sha256",
            "lookup('template', 'relay-codex-launcher-wrapper.sh.j2')",
            "relay_production_expected_codex_launcher_wrapper_sha256",
            "relay_production_final_codex_launcher_raw.content | default('') | b64decode | hash('sha256') == relay_production_expected_codex_launcher_wrapper_sha256",
            "PRODUCTION_CODEX_LAUNCHER_BINDING_INVALID",
            "relay_production_final_manifest.commit",
            "relay_production_final_manifest.codexLauncherSourceTreeSha256",
            "relay_production_operation_target_head",
            "'argv[2] === \"review-remediation\"' in",
            "'argv[12] === \"--pull-request\"' in",
            "follow: false",
            "mode | default('') == '0755'",
            "relay-codex.mjs",
            "relay_production_final_codex_launcher_module",
        ):
            self.assertIn(marker, self.launcher_validation)

        self.assertIn("#!/bin/sh", self.launcher_wrapper)
        self.assertIn(
            "exec /usr/bin/node --experimental-default-type=module",
            self.launcher_wrapper,
        )
        self.assertIn("relay-codex.mjs", self.launcher_wrapper)

    def test_wrapper_byte_drift_is_rejected_even_when_all_markers_remain(self):
        expected_sha256 = hashlib.sha256(
            self.launcher_wrapper.encode("utf-8")
        ).hexdigest()
        self.assertTrue(artifact_hash_matches(self.launcher_wrapper, expected_sha256))

        drifted_wrapper = self.launcher_wrapper.replace(
            "#!/bin/sh\n",
            "#!/bin/sh\n# marker-preserving drift\n",
            1,
        )
        for marker in (
            "#!/bin/sh",
            "exec /usr/bin/node --experimental-default-type=module",
            "relay-codex.mjs",
        ):
            self.assertIn(marker, drifted_wrapper)
        self.assertFalse(artifact_hash_matches(drifted_wrapper, expected_sha256))

    def test_drift_is_rejected_before_child_start_and_existing_gates_remain(self):
        stale_launcher = (
            'if (argv.length !== 12 || argv[0] !== "exec" || '
            'argv[10] !== "--issue") fail("ARGUMENT_CONTRACT_INVALID");'
        )
        self.assertFalse(launcher_contract_is_current(stale_launcher))
        for marker in (
            "childStarted: observedChildStarted",
            'if (!issueMode && !remediationMode) fail("ARGUMENT_CONTRACT_INVALID");',
            "PRODUCTION_CODEX_LAUNCHER_BINDING_INVALID",
            "CODEX_LAUNCHER_CHECK_MODE_PLAN",
        ):
            self.assertIn(
                marker,
                self.launcher + self.launcher_wrapper + self.launcher_tasks + self.launcher_validation,
            )
        for marker in (
            "production-operation-state.yml",
            "production-writer-binding-validation.yml",
            "production-final-validation.yml",
            "production-operation-state-clear.yml",
            "relay_production_operation_phase",
        ):
            self.assertIn(marker, self.site)
        for forbidden in (
            "codex-ready-auto",
            "codex-ready-manual",
        ):
            self.assertNotIn(forbidden, self.launcher_validation)
        for forbidden in (
            "GITHUB_TOKEN",
            "OPENAI_API_KEY",
            "dangerously-bypass-approvals-and-sandbox",
        ):
            self.assertNotIn(forbidden, self.launcher)


if __name__ == "__main__":
    unittest.main()
