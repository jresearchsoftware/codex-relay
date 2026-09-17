"""Regression checks for the Reviewer group/artifact dependency boundary."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def reviewer_artifact_action(check_mode, reviewer_group_materialized):
    """Model the ownership operation without invoking Ansible or a host."""
    if check_mode:
        return "PLAN_ONLY"
    return "APPLY" if reviewer_group_materialized else "BLOCK"


def normal_apply_reconciliation(group_exists_before_apply):
    """Model a fresh or partially reconciled apply without resetting state."""
    reviewer_group_materialized = True
    return {
        "group_created": not group_exists_before_apply,
        "artifact_action": reviewer_artifact_action(False, reviewer_group_materialized),
        "state_reset": False,
    }


class ReviewerGroupDependencyTests(unittest.TestCase):
    def setUp(self):
        self.site = (ROOT / "site.yml").read_text(encoding="utf-8")
        self.runtime = (ROOT / "roles" / "relay_runtime" / "tasks" / "main.yml").read_text(encoding="utf-8")
        self.artifacts = (ROOT / "roles" / "relay_artifacts" / "tasks" / "main.yml").read_text(encoding="utf-8")

    def test_full_site_orders_reviewer_group_before_artifact_ownership(self):
        self.assertLess(self.site.index("role: relay_runtime"), self.site.index("role: relay_artifacts"))
        self.assertIn("- name: Create the dedicated Reviewer credential group", self.runtime)
        self.assertIn("name: '{{ relay_reviewer_group }}'", self.runtime)
        self.assertLess(
            self.runtime.index("- name: Create the dedicated Reviewer credential group"),
            self.runtime.index("- name: Create the dedicated Reviewer service identity"),
        )
        self.assertIn("name: Install the built Reviewer executable into the release contract", self.artifacts)
        self.assertIn("group: '{{ relay_reviewer_group }}'", self.artifacts)

    def test_check_mode_plans_without_materializing_and_apply_handles_partial_state(self):
        self.assertEqual(reviewer_artifact_action(True, False), "PLAN_ONLY")
        self.assertEqual(reviewer_artifact_action(True, True), "PLAN_ONLY")
        partial = normal_apply_reconciliation(False)
        self.assertEqual(partial["group_created"], True)
        self.assertEqual(partial["artifact_action"], "APPLY")
        self.assertEqual(partial["state_reset"], False)



if __name__ == "__main__":
    unittest.main()
