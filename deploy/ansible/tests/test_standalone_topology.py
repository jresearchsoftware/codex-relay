"""Regression tests for the standalone-relay and coexistence contract."""

import unittest


def classify_topology(existing_protected_paths):
    """Mirror the Ansible classification: absence is valid A-only state."""
    return (
        "A_ONLY_STANDALONE_NO_DOCKER_NO_NEXUS"
        if not existing_protected_paths
        else "FOREIGN_PROTECTED_DOCKER_OR_NEXUS_STATE_PRESENT"
    )


class StandaloneTopologyTests(unittest.TestCase):
    def test_docker_and_nexus_absence_is_valid_standalone_state(self):
        self.assertEqual(classify_topology([]), "A_ONLY_STANDALONE_NO_DOCKER_NO_NEXUS")

    def test_docker_or_nexus_presence_is_detected_as_foreign_state(self):
        self.assertEqual(
            classify_topology(["/var/run/docker.sock"]),
            "FOREIGN_PROTECTED_DOCKER_OR_NEXUS_STATE_PRESENT",
        )

    def test_nexus_path_presence_is_detected_as_foreign_state(self):
        self.assertEqual(
            classify_topology(["/srv/nexus"]),
            "FOREIGN_PROTECTED_DOCKER_OR_NEXUS_STATE_PRESENT",
        )


if __name__ == "__main__":
    unittest.main()
