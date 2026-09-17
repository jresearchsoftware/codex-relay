"""Static regression checks for the source-controlled APT metadata-only phase."""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_TASKS = ROOT / "roles" / "relay_apt_metadata" / "tasks" / "main.yml"
BOOTSTRAP_PLAYBOOK = ROOT / "apt-metadata-bootstrap.yml"


class AptMetadataBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.tasks = BOOTSTRAP_TASKS.read_text(encoding="utf-8")
        self.playbook = BOOTSTRAP_PLAYBOOK.read_text(encoding="utf-8")

    def test_refresh_is_cache_only_and_repeatable(self):
        self.assertIn("update_cache: true", self.tasks)
        self.assertIn("cache_valid_time", self.tasks)
        self.assertIn("cache_updated", self.tasks)
        self.assertIn("APT_METADATA_BOOTSTRAP=", self.tasks)

    def test_bootstrap_has_no_package_service_or_foreign_state_mutation(self):
        for forbidden in (
            "ansible.builtin.package",
            "ansible.builtin.apt_repository",
            "ansible.builtin.service",
            "ansible.builtin.systemd",
            "relay_base_packages",
            "relay_manage_docker",
            "/srv/nexus",
        ):
            self.assertNotIn(forbidden, self.tasks)

    def test_preflight_precedes_metadata_role(self):
        self.assertLess(self.playbook.index("relay_preflight"), self.playbook.index("relay_apt_metadata"))


if __name__ == "__main__":
    unittest.main()
