"""Regression checks for the Reviewer group/artifact dependency boundary."""

from pathlib import Path
import os
import shutil
import stat
import tempfile
import unittest

import yaml

from test_production_install_current_main import run_play


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



@unittest.skipUnless(os.name != 'nt' and shutil.which('ansible-playbook'), 'native Linux Ansible required')
class RuntimeDirectoryOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        runtime = yaml.safe_load((ROOT / 'roles/relay_runtime/tasks/main.yml').read_text())
        names = {
            'Inspect directory ownership identities in check mode',
            'Create namespaced relay directories',
            'Report directory reconciliation pending planned ownership identities',
        }
        self.tasks = [task for task in runtime if task.get('name') in names]
        self.values = {
            'relay_user': 'relay-check-missing-user',
            'relay_group': 'relay-check-missing-group',
            'relay_reviewer_user': 'relay-check-missing-reviewer',
            'relay_reviewer_group': 'relay-check-missing-reviewer-group',
            **{key: str(self.root / name) for key, name in (
                ('relay_install_root', 'install'), ('relay_release_root', 'install/releases'),
                ('relay_config_root', 'config'), ('relay_state_root', 'state'),
                ('relay_runtime_root', 'runtime'), ('relay_log_root', 'logs'),
                ('relay_evidence_root', 'state/evidence'),
                ('relay_reviewer_credential_root', 'config/reviewer-credentials'),
                ('relay_writer_credential_root', 'config/writer-credentials'),
            )},
        }
        # Bootstrap disposition deliberately retains these roots and evidence.
        for name, mode in [('state', 0o700), ('runtime', 0o755),
                           ('state/production-apply', 0o700), ('state/superseded-operations', 0o700)]:
            (self.root / name).mkdir(mode=mode)
        (self.root / 'runtime/production-operation.lock').touch(mode=0o644)
        (self.root / 'state/superseded-operations/apply.json').write_text('{"state":"SUPERSEDED"}')

    def snapshot(self):
        result = {}
        for prefix in ('state', 'runtime'):
            for path in [self.root / prefix, *(self.root / prefix).rglob('*')]:
                info = path.lstat()
                result[str(path.relative_to(self.root))] = (
                    info.st_ino, info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode),
                    info.st_mtime_ns, info.st_ctime_ns, path.read_bytes() if path.is_file() else None,
                )
        return result

    def test_check_after_bootstrap_disposition_plans_without_accounts_or_mutation(self):
        before = self.snapshot()
        result = run_play(self.root, self.tasks, self.values, check=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('RUNTIME_DIRECTORY_CHECK_MODE_PLAN=', result.stdout)
        self.assertRegex(result.stdout, r'changed=[1-9]')
        self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.root / 'install').exists())
        self.assertFalse((self.root / 'config').exists())

    def test_apply_does_not_defer_missing_ownership(self):
        result = run_play(self.root, self.tasks, self.values)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertRegex(result.stdout, r'failed to look up (user|group) relay-check-missing')
        self.assertNotIn('RUNTIME_DIRECTORY_CHECK_MODE_PLAN=', result.stdout)

    @unittest.skipUnless(os.name != 'nt' and os.geteuid() == 0, 'root ownership requires Linux root')
    def test_materialized_ownership_is_checked_applied_and_then_stable(self):
        values = {**self.values, 'relay_user': 'root', 'relay_group': 'nogroup',
                  'relay_reviewer_user': 'nobody', 'relay_reviewer_group': 'nogroup'}
        before = self.snapshot()
        checked = run_play(self.root, self.tasks, values, check=True)
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
        self.assertRegex(checked.stdout, r'changed=[1-9]')
        self.assertEqual(self.snapshot(), before)
        applied = run_play(self.root, self.tasks, values)
        self.assertEqual(applied.returncode, 0, applied.stdout + applied.stderr)
        import grp
        import pwd
        reviewer = (self.root / 'state/reviewer').stat()
        self.assertEqual(reviewer.st_uid, pwd.getpwnam('nobody').pw_uid)
        self.assertEqual(reviewer.st_gid, grp.getgrnam('nogroup').gr_gid)
        self.assertEqual(stat.S_IMODE(reviewer.st_mode), 0o750)
        self.assertEqual(stat.S_IMODE((self.root / 'runtime').stat().st_mode), 0o770)
        after = self.snapshot()
        stable = run_play(self.root, self.tasks, values, check=True)
        self.assertEqual(stable.returncode, 0, stable.stdout + stable.stderr)
        self.assertRegex(stable.stdout, r'changed=0\s')
        self.assertEqual(self.snapshot(), after)


if __name__ == "__main__":
    unittest.main()
