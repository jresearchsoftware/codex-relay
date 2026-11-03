"""Real task/helper integration for the protected same-operation continuation.

All persistent-looking paths use a unique synthetic namespace. No host service,
credential, existing installation or external API is used.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid

import test_production_operation_state_execution as state_execution
from test_production_operation_recovery_execution import ProductionOperationFixture


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
import bounded_recovery as recovery


ORIGINAL = "b" * 40
INSTALLED = ORIGINAL
DESIRED = "4" * 40
OPERATION = "12345678-1234-1234-1234-123456789abc"


def native_root_available():
    return (os.name != "nt" and getattr(os, "geteuid", lambda: 1)() == 0
            and shutil.which("ansible-playbook") is not None)


class BoundedBackendFixture:
    def __enter__(self):
        try:
            return self.initialize()
        except BaseException:
            self.__exit__()
            raise

    def initialize(self):
        install = Path("/opt") / ("relay-bound-" + uuid.uuid4().hex[:12])
        install.mkdir(mode=0o700)
        self.install = install
        self.namespace = self.install.name
        self.temporary = tempfile.TemporaryDirectory(prefix="relay-bound-", dir="/run")
        self.work = Path(self.temporary.name)
        self.claim = self.work / "claim"
        self.claim.mkdir()
        self.config = {"environment": {"namespace": self.namespace}, "consumer": {
            "repository": "example/consumer", "paths": {"claimRoot": str(self.claim)}}}
        config_raw = json.dumps(self.config, sort_keys=True).encode() + b"\n"
        self.git_receipt = {"product_sha": DESIRED, "config_sha": "c" * 40,
            "config_blob_sha": "d" * 40, "config_sha256": recovery.sha(config_raw)}
        self.binding = {"operationId": OPERATION, "retainedTarget": ORIGINAL,
            "installedRevision": INSTALLED, "controllerRevision": DESIRED,
            "desiredRevision": DESIRED, "gitConfigReceipt": self.git_receipt}
        self.paths = recovery.paths(self.config, self.binding, Path("/"))
        self.record = self.paths["record"]
        self.raw = (json.dumps({"schemaVersion": "1", "state": "RECOVERY_REQUIRED",
            "phase": "apply", "target_head": ORIGINAL}, indent=2) + "\n").encode()
        self.write(self.record, self.raw)
        config_root = Path("/etc") / self.namespace
        config_root.mkdir(mode=0o700)
        self.config_root = config_root
        self.write(config_root / "consumer.json", json.dumps(self.config["consumer"]).encode())
        self.release(INSTALLED)
        (self.install / "current").symlink_to("releases/" + INSTALLED)
        self.gate = {"version": 1, "consumerDigest": "e" * 64,
            "phase": "recovery-required", "operationId": OPERATION, "target": ORIGINAL,
            "previousActive": {"reviewer": {"active": True}, "production": {"active": True}},
            "verifiedRevision": None}
        self.save_gate()
        proof = recovery.inspect(self.config, self.binding)
        self.receipt = recovery.begin(self.config, self.binding, proof,
            admission_probe=lambda request: {**request, "currentDigest": self.gate["consumerDigest"],
                "phase": self.gate["phase"], "active": [], "unknown": [], "eligible": True,
                "desiredDigest": "f" * 64})
        self.gate.update(phase="applying", target=DESIRED)
        self.save_gate()
        return self

    def __exit__(self, *_):
        if hasattr(self, "paths"):
            for path in [self.record, self.paths["receipt"],
                         self.paths["receipt"].with_name(self.paths["receipt"].stem + ".original.json")]:
                if path.exists() or path.is_symlink():
                    path.unlink()
        if hasattr(self, "config_root"):
            shutil.rmtree(self.config_root)
        if hasattr(self, "temporary"):
            self.temporary.cleanup()
        if hasattr(self, "install"):
            shutil.rmtree(self.install)

    @staticmethod
    def write(path, raw):
        path.write_bytes(raw)
        path.chmod(0o600)

    def save_gate(self):
        self.write(self.paths["gate"], json.dumps(self.gate).encode())

    def release(self, revision, *, wrong_pair=False):
        release = self.install / "releases" / revision
        source = release / "reviewed-source"
        source.mkdir(parents=True)
        raw = json.dumps(self.config, sort_keys=True).encode() + b"\n"
        self.write(release / "deployment-config.json", raw)
        manifest = {"commit": revision, "installedRevision": revision,
            "resolvedRevision": revision, "gitTree": "a" * 40,
            "deploymentConfigSha256": recovery.sha(raw), "deploymentContract": {
                "schemaVersion": 1, "epoch": 1,
                "capabilities": ["lifecycle-v1", "git-desired-v1", "integration-artifact-v1"]}}
        manifest["gitConfigReceipt"] = {**self.git_receipt, "product_sha": revision}
        if wrong_pair:
            manifest["gitConfigReceipt"]["config_sha"] = "9" * 40
        self.write(release / "artifact-manifest.json", json.dumps(manifest).encode())
        self.write(source / ".relay-source.json", json.dumps({"revision": revision,
            "tree": "a" * 40}).encode())
        return release

    def select_desired(self, *, wrong_pair=False):
        release = self.release(DESIRED, wrong_pair=wrong_pair)
        (self.install / "current").unlink()
        (self.install / "current").symlink_to("releases/" + DESIRED)
        return release

    def variables(self):
        return {"relay_deployment_profile": "production", "relay_namespace": self.namespace,
            "relay_production_operation_phase": "apply", "relay_production_operation_target_head": DESIRED,
            "relay_production_operation_record_path": str(self.record),
            "relay_production_operation_lock_path": str(self.work / "operation.lock"),
            "relay_production_operation_schema_version": "1",
            "relay_bounded_recovery_binding": self.binding, "relay_admission_operation_id": OPERATION,
            "relay_upgrade_requested": True, "relay_admission_recovery_authorized": True,
            "relay_local_apply_source": "git", "relay_production_operation_clear_phase": "apply",
            "relay_production_operation_clear_head": ORIGINAL}


@unittest.skipUnless(native_root_available(), "root-capable native Ansible required")
class ProductionBoundedBackendExecutionTests(unittest.TestCase):
    def run_tasks(self, fixture, tasks, variables=None):
        harness = state_execution.ProductionOperationStateExecutionTests()
        play = fixture.work / "play.yml"
        harness._playbook(play, variables or fixture.variables(), tasks)
        return harness._run(play)

    @staticmethod
    def include(name):
        return "- ansible.builtin.include_tasks: " + json.dumps(str(ROOT / "tasks" / name)) + "\n"

    def test_new_target_retains_original_record_until_validated_archive_and_clear(self):
        with BoundedBackendFixture() as fixture:
            before = fixture.record.stat()
            tasks = self.include("production-operation-state.yml")
            tasks += ("- ansible.builtin.assert:\n    that:\n"
                "      - relay_production_operation_recovery_matching | bool\n"
                f"      - relay_production_operation_active_head == '{ORIGINAL}'\n")
            tasks += self.include("production-operation-state-begin.yml")
            result = self.run_tasks(fixture, tasks)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(fixture.record.read_bytes(), fixture.raw)
            self.assertEqual(fixture.record.stat().st_ino, before.st_ino)
            fixture.select_desired()
            result = self.run_tasks(fixture, self.include("production-operation-state-clear.yml"))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse(fixture.record.exists())
            archive = fixture.paths["receipt"].with_name(fixture.paths["receipt"].stem + ".original.json")
            self.assertEqual(archive.read_bytes(), fixture.raw)
            self.assertEqual(json.loads(fixture.paths["receipt"].read_text())["state"], "backend-complete")

    def test_plain_recovery_authority_does_not_bypass_original_target(self):
        with BoundedBackendFixture() as fixture:
            variables = fixture.variables()
            variables.pop("relay_bounded_recovery_binding")
            result = self.run_tasks(fixture, self.include("production-operation-state.yml"), variables)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("PRODUCTION_RECOVERY_PHASE_OR_HEAD_MISMATCH", result.stdout + result.stderr)
            self.assertEqual(fixture.record.read_bytes(), fixture.raw)

    def test_read_only_continuation_proof_does_not_start_a_recovery_phase(self):
        with BoundedBackendFixture() as fixture:
            fixture.gate["phase"] = "recovery-required"
            fixture.save_gate()
            tasks = self.include("production-operation-state.yml")
            result = self.run_tasks(fixture, tasks)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = self.run_tasks(fixture, tasks + self.include("production-operation-state-begin.yml"))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("BOUNDED_RECOVERY_BACKEND_GATE_CHANGED", result.stdout + result.stderr)
            self.assertEqual(fixture.record.read_bytes(), fixture.raw)
            self.assertEqual(json.loads(fixture.paths["gate"].read_text())["phase"], "recovery-required")

    def test_begin_revalidates_receipt_after_initial_inspection(self):
        with BoundedBackendFixture() as fixture:
            tasks = self.include("production-operation-state.yml")
            tasks += "- ansible.builtin.copy:\n"
            tasks += "    dest: " + json.dumps(str(fixture.paths["receipt"])) + "\n"
            tasks += "    mode: '0600'\n    content: " + json.dumps(json.dumps({
                **fixture.receipt, "state": "complete"})) + "\n"
            tasks += self.include("production-operation-state-begin.yml")
            result = self.run_tasks(fixture, tasks)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("BOUNDED_RECOVERY_BACKEND_BINDING_CHANGED", result.stdout + result.stderr)
            self.assertEqual(fixture.record.read_bytes(), fixture.raw)

    def test_same_product_wrong_final_git_pair_cannot_clear_original(self):
        with BoundedBackendFixture() as fixture:
            fixture.select_desired(wrong_pair=True)
            result = self.run_tasks(fixture, self.include("production-operation-state-clear.yml"))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("BOUNDED_RECOVERY_FINAL_INSTALLATION_UNPROVEN", result.stdout + result.stderr)
            self.assertEqual(fixture.record.read_bytes(), fixture.raw)
            self.assertEqual(json.loads(fixture.paths["receipt"].read_text())["state"], "reserved")

    def test_restart_new_target_requires_protected_continuation_and_original_activity(self):
        for valid in [True, False]:
            with self.subTest(valid=valid), BoundedBackendFixture() as fixture, ProductionOperationFixture() as services:
                release = fixture.select_desired()
                deploy = release / "reviewed-source" / "deploy"
                deploy.mkdir()
                shutil.copyfile(ROOT.parent / "bounded_recovery.py", deploy / "bounded_recovery.py")
                (deploy / "bounded_recovery.py").chmod(0o644)
                admission = fixture.install / "relay-admission"
                admission.write_text("#!/usr/bin/python3\nprint(" + repr(json.dumps(fixture.gate)) + ")\n")
                admission.chmod(0o755)
                services.install_root, services.record = fixture.install, fixture.record
                services._render_helpers()
                services.write_marker()
                services.set_runtime_state(reviewer=("inactive", "enabled"), runner=("inactive", "enabled"))
                if not valid:
                    fixture.paths["receipt"].chmod(0o644)
                result = subprocess.run(["/bin/bash", str(services.scripts["operation_restart"]),
                    "--recover-active", OPERATION], env=services.environment,
                    capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode == 0, valid, result.stdout + result.stderr)
                self.assertEqual("start reviewer-mcp.service" in services.log_lines(), valid)
                self.assertEqual("start relay-runner.service" in services.log_lines(), valid)
                if not valid:
                    self.assertIn("REVIEWER_OPERATION_RESTART_RECOVERY_INTENT_UNPROVEN", result.stderr)
                self.assertEqual(fixture.record.read_bytes(), fixture.raw)
