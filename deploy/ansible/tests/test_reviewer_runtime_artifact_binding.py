"""Regression checks for artifact identity before Reviewer runtime rendering."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ReviewerRuntimeArtifactBindingTests(unittest.TestCase):
    def setUp(self):
        self.site = (ROOT / "site.yml").read_text(encoding="utf-8")
        self.reviewer_config = (
            ROOT / "roles" / "relay_runtime" / "templates" / "reviewer-mcp.json.j2"
        ).read_text(encoding="utf-8")
        self.docker_adapter = (ROOT / "relay-docker-nginx.yml").read_text(encoding="utf-8")
        self.docker_rollback = (ROOT / "relay-docker-nginx-rollback.yml").read_text(encoding="utf-8")

    def test_site_resolves_artifact_identity_before_runtime_role(self):
        runtime_play = self.site.split(
            "- name: Install namespaced relay prerequisites and runtime state", 1
        )[1]
        identity_include = (
            "ansible.builtin.include_tasks: "
            "roles/relay_artifacts/tasks/resolve-identities.yml"
        )
        self.assertIn(identity_include, runtime_play)
        self.assertLess(runtime_play.index(identity_include), runtime_play.index("roles:"))
        self.assertLess(runtime_play.index("role: relay_runtime"), runtime_play.index("role: relay_artifacts"))

    def test_reviewer_config_requires_resolved_artifact_identity(self):
        self.assertIn('"commit": "{{ relay_release_commit }}"', self.reviewer_config)
        self.assertIn('"sha256": "{{ relay_release_sha256 }}"', self.reviewer_config)
        self.assertNotIn("UNAVAILABLE_UNTIL_RELEASE_STAGING", self.reviewer_config)

    def test_docker_bind_entrypoints_resolve_identity_before_bind_role(self):
        identity_include = (
            "ansible.builtin.include_tasks: "
            "roles/relay_artifacts/tasks/resolve-identities.yml"
        )
        for entrypoint, role_marker in (
            (self.docker_adapter, "role: relay_reviewer_bind"),
            (self.docker_rollback, "role: relay_reviewer_bind"),
        ):
            self.assertIn("pre_tasks:", entrypoint)
            self.assertIn(identity_include, entrypoint)
            self.assertLess(entrypoint.index("pre_tasks:"), entrypoint.index("roles:"))
            self.assertLess(entrypoint.index(identity_include), entrypoint.index(role_marker))


if __name__ == "__main__":
    unittest.main()
