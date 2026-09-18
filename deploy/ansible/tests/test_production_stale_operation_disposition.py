"""State-machine and contract regressions for cross-revision recovery."""

import os
import re
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest

import yaml



def linux_bash_available():
    import os,shutil
    return os.name != "nt" and shutil.which("bash") is not None

ROOT = Path(__file__).resolve().parents[1]
OLD_HEAD = "8698d3f5ea74034f61eb83e425358192cd672d19"
NEW_HEAD = "c6ba2b22a97de5e03270e77190d144aca3c2c6ef"


def stale_disposition_decision(
    phase,
    *,
    record_phase,
    record_head,
    requested_head,
    authorized,
    reviewer_marker=False,
    recovery_off=False,
    reviewer_active="inactive",
    reviewer_enabled="disabled",
    listener=False,
    registration=False,
    credentials=False,
    runner_active="inactive",
    runner_enabled="disabled",
    actual_completed_phase=None,
    expected_state_hash=None,
    current_state_hash=None,
    apply_state=False,
):
    """Mirror the bounded cross-revision transition without mutating a host."""
    if not authorized or phase != "stale-dispose":
        return "blocked-authority"
    if record_phase not in {"apply", "activate", "runner-enable"}:
        return "blocked-record"
    if record_head == requested_head or record_head != OLD_HEAD:
        return "blocked-head"
    if record_phase == "apply":
        if (
            actual_completed_phase != "apply"
            or not isinstance(expected_state_hash, str)
            or not re.fullmatch(r"[0-9a-f]{64}", expected_state_hash)
            or expected_state_hash != current_state_hash
            or not apply_state
        ):
            return "blocked-apply-evidence"
        return "fresh-owner-partial-apply-reconciliation"
    if record_phase == "activate":
        if (
            not reviewer_marker
            and not recovery_off
            and reviewer_active in {"inactive", "failed"}
            and reviewer_enabled in {"disabled", "enabled", "enabled-runtime"}
            and not listener
            and runner_active in {"inactive", "failed"}
            and runner_enabled in {"disabled", "enabled", "enabled-runtime"}
        ):
            return "reviewer-only-preactivation-reset"
        return "blocked-activate-evidence"
    if (
        reviewer_marker
        and not recovery_off
        and reviewer_active == "active"
        and reviewer_enabled in {"enabled", "enabled-runtime"}
        and listener
        and registration
        and credentials
        and runner_active in {"inactive", "failed", "active"}
        and runner_enabled in {"disabled", "enabled", "enabled-runtime"}
    ):
        return "runner-enable-read-only-replayable"
    return "blocked-runner-evidence"


def ansible_loader_available():
    if os.name == "nt" or shutil.which("ansible-playbook") is None:
        return False
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return True
    sudo = shutil.which("sudo")
    if sudo is None:
        return False
    return subprocess.run([sudo, "-n", "true"], capture_output=True, check=False).returncode == 0


def read_root_owned_text(path):
    path = Path(path)
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return path.read_text(encoding="utf-8")
    sudo = shutil.which("sudo")
    if sudo is None:
        raise AssertionError("passwordless sudo is required to inspect the root-owned rendered helper")
    result = subprocess.run(
        [sudo, "-n", "cat", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            "passwordless sudo could not inspect the root-owned rendered helper:\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )
    return result.stdout


class ProductionStaleOperationDispositionTests(unittest.TestCase):
    def setUp(self):
        self.state = (ROOT / "tasks" / "production-operation-state.yml").read_text(encoding="utf-8")
        self.stale_tasks = (ROOT / "tasks" / "production-operation-stale-disposition.yml").read_text(encoding="utf-8")
        self.runtime_stale_tasks = (
            ROOT / "roles" / "relay_runtime" / "tasks" / "production-operation-stale-disposition.yml"
        ).read_text(encoding="utf-8")
        self.runtime_tasks = (ROOT / "roles" / "relay_runtime" / "tasks" / "main.yml").read_text(encoding="utf-8")
        self.stale_playbook = (ROOT / "relay-production-operation-stale-disposition.yml").read_text(encoding="utf-8")
        self.stale_helper = (
            ROOT / "roles" / "relay_runtime" / "templates" / "relay-production-operation-stale-disposition.j2"
        ).read_text(encoding="utf-8")
        self.activation = (ROOT / "relay-reviewer-activation.yml").read_text(encoding="utf-8")
        self.runner_enable = (ROOT / "relay-production-runner-enable.yml").read_text(encoding="utf-8")

    def test_each_mutating_phase_has_an_explicit_cross_revision_decision(self):
        self.assertEqual(
            stale_disposition_decision(
                "stale-dispose",
                record_phase="apply",
                record_head=OLD_HEAD,
                requested_head=NEW_HEAD,
                authorized=True,
                actual_completed_phase="apply",
                expected_state_hash="a" * 64,
                current_state_hash="a" * 64,
                apply_state=True,
            ),
            "fresh-owner-partial-apply-reconciliation",
        )
        self.assertEqual(
            stale_disposition_decision(
                "stale-dispose",
                record_phase="activate",
                record_head=OLD_HEAD,
                requested_head=NEW_HEAD,
                authorized=True,
                reviewer_enabled="enabled",
            ),
            "reviewer-only-preactivation-reset",
        )
        self.assertEqual(
            stale_disposition_decision(
                "stale-dispose",
                record_phase="runner-enable",
                record_head=OLD_HEAD,
                requested_head=NEW_HEAD,
                authorized=True,
                reviewer_marker=True,
                reviewer_active="active",
                reviewer_enabled="enabled",
                listener=True,
                registration=True,
                credentials=True,
            ),
            "runner-enable-read-only-replayable",
        )

    def test_wrong_authority_and_sha_reclassification_are_blocked(self):
        self.assertEqual(
            stale_disposition_decision(
                "stale-dispose",
                record_phase="activate",
                record_head=OLD_HEAD,
                requested_head=NEW_HEAD,
                authorized=False,
            ),
            "blocked-authority",
        )
        self.assertEqual(
            stale_disposition_decision(
                "stale-dispose",
                record_phase="activate",
                record_head=NEW_HEAD,
                requested_head=NEW_HEAD,
                authorized=True,
            ),
            "blocked-head",
        )
        self.assertEqual(
            stale_disposition_decision(
                "activate",
                record_phase="activate",
                record_head=OLD_HEAD,
                requested_head=NEW_HEAD,
                authorized=True,
            ),
            "blocked-authority",
        )

    def test_stale_apply_requires_exact_completed_phase_and_matching_state_hash(self):
        self.assertEqual(
            stale_disposition_decision(
                "stale-dispose",
                record_phase="apply",
                record_head=OLD_HEAD,
                requested_head=NEW_HEAD,
                authorized=True,
            ),
            "blocked-apply-evidence",
        )
        self.assertEqual(
            stale_disposition_decision(
                "stale-dispose",
                record_phase="apply",
                record_head=OLD_HEAD,
                requested_head=NEW_HEAD,
                authorized=True,
                actual_completed_phase="apply",
                expected_state_hash="A" * 64,
                current_state_hash="A" * 64,
                apply_state=True,
            ),
            "blocked-apply-evidence",
        )
        self.assertEqual(
            stale_disposition_decision(
                "stale-dispose",
                record_phase="apply",
                record_head=OLD_HEAD,
                requested_head=NEW_HEAD,
                authorized=True,
                actual_completed_phase="apply",
                expected_state_hash="a" * 64,
                current_state_hash="b" * 64,
                apply_state=True,
            ),
            "blocked-apply-evidence",
        )


    def test_stale_dispose_uses_one_role_owned_helper_installation(self):
        self.assertIn("ansible.builtin.include_role", self.stale_tasks)
        self.assertIn("name: relay_runtime", self.stale_tasks)
        self.assertIn("tasks_from: production-operation-stale-disposition.yml", self.stale_tasks)
        self.assertIn("include_tasks: production-operation-stale-disposition.yml", self.runtime_tasks)
        self.assertIn("relay-production-operation-stale-disposition.j2", self.runtime_stale_tasks)
        self.assertNotIn("ansible.builtin.template:", self.stale_tasks)

    @unittest.skipUnless(ansible_loader_available(), "root-capable native Ansible is required for loader integration")
    def test_standalone_stale_dispose_renders_helper_with_actual_ansible_role_loader(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture_root = Path(temporary_directory)
            destination = fixture_root / "stale-disposition"
            context = {
                "relay_production_operation_stale_disposition_path": str(destination),
                "relay_production_operation_record_path": str(fixture_root / "operation.json"),
                "relay_production_operation_lock_path": str(fixture_root / "operation.lock"),
                "relay_production_operation_superseded_root": str(fixture_root / "superseded"),
                "relay_production_operation_stale_phase": "activate",
                "relay_production_operation_stale_target_head": "b" * 40,
                "relay_production_operation_target_head": "a" * 40,
                "relay_production_operation_schema_version": "1",
                "relay_reviewer_service_name": "reviewer-mcp.service",
                "relay_runner_service_name": "relay-runner.service",
                "relay_production_runner_service_name": "relay-runner.service",
                "relay_reviewer_activation_marker": str(fixture_root / "activation"),
                "relay_reviewer_recovery_off_marker": str(fixture_root / "recovery-off"),
                "relay_runner_registration_marker": str(fixture_root / "runner"),
                "relay_runner_credentials_marker": str(fixture_root / "credentials"),
                "relay_reviewer_bind_address": "127.0.0.1",
                "relay_reviewer_bind_port": 8787,
            }
            standalone_tasks = yaml.safe_load(self.stale_tasks)
            installation_task = next(
                task
                for task in standalone_tasks
                if task.get("name") == "Install the current source-controlled stale-disposition helper"
            )
            playbook_path = fixture_root / "stale-disposition-loader.yml"
            playbook_path.write_text(
                yaml.safe_dump(
                    [
                        {
                            "name": "Exercise standalone stale-dispose helper installation",
                            "hosts": "localhost",
                            "connection": "local",
                            "become": True,
                            "become_user": "root",
                            "gather_facts": False,
                            "vars": context,
                            "tasks": [installation_task],
                        }
                    ],
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            environment = os.environ.copy()
            environment.update(
                {
                    "ANSIBLE_NOCOLOR": "1",
                    "ANSIBLE_LOCALHOST_WARNING": "False",
                    "ANSIBLE_ROLES_PATH": str(ROOT / "roles"),
                }
            )
            result = subprocess.run(
                [
                    "ansible-playbook",
                    "-i",
                    "localhost,",
                    "-c",
                    "local",
                    str(playbook_path),
                ],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            output = result.stdout + result.stderr
            if result.returncode != 0:
                self.fail(
                    "actual Ansible role loader could not render the standalone helper:\n"
                    f"stdout={result.stdout}\nstderr={result.stderr}"
                )
            self.assertTrue(destination.is_file())
            metadata = destination.stat()
            self.assertEqual(metadata.st_uid, 0)
            self.assertEqual(metadata.st_gid, 0)
            self.assertEqual(stat.S_IMODE(metadata.st_mode), 0o750)
            rendered = read_root_owned_text(destination)
            self.assertIn(f"record='{context['relay_production_operation_record_path']}'", rendered)
            self.assertIn("STALE_ACTIVATE_PREACTIVATION_RESET", rendered)
            self.assertIn("Install the source-controlled stale-disposition helper", output)

    def test_archive_publication_and_record_retirement_are_directory_durable_in_order(self):
        helper = self.stale_helper
        markers = {
            "archive_root_parent_sync": (
                "fsync_directory(\n"
                "        archive_root_parent,\n"
                "        'PRODUCTION_STALE_DISPOSITION_ARCHIVE_ROOT_PARENT_UNAVAILABLE',\n"
                "    )"
            ),
            "archive_file_sync": "os.fsync(archive_fd)",
            "archive_directory_sync": (
                "fsync_directory(\n"
                "    archive_root,\n"
                "    'PRODUCTION_STALE_DISPOSITION_ARCHIVE_DIRECTORY_UNAVAILABLE',\n"
                ")"
            ),
            "record_recheck": "raw_after, _ = read_record(record_path)",
            "record_retirement": "os.unlink(record_path)",
            "record_directory_sync": (
                "fsync_directory(\n"
                "    record_parent,\n"
                "    'PRODUCTION_STALE_DISPOSITION_RECORD_DIRECTORY_UNAVAILABLE',\n"
                ")"
            ),
        }
        positions = {name: helper.index(marker) for name, marker in markers.items()}

        self.assertIn("directory_fd = os.open(path, flags)", helper)
        self.assertIn("os.fsync(directory_fd)", helper)
        self.assertLess(positions["archive_root_parent_sync"], helper.index("archive_path = os.path.join"))
        self.assertLess(positions["archive_file_sync"], positions["archive_directory_sync"])
        self.assertLess(positions["archive_directory_sync"], positions["record_recheck"])
        self.assertLess(positions["record_recheck"], positions["record_retirement"])
        self.assertLess(positions["record_retirement"], positions["record_directory_sync"])



if __name__ == "__main__":
    unittest.main()
