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
    def __init__(self, *, gate_only=False, reserve=True):
        self.gate_only = gate_only
        self.reserve_immediately = reserve

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
        if not self.gate_only:
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
        if self.reserve_immediately:
            self.reserve()
        return self

    def reserve(self):
        proof = recovery.inspect(self.config, self.binding)
        self.receipt = recovery.begin(self.config, self.binding, proof,
            admission_probe=lambda request: {**request, "currentDigest": self.gate["consumerDigest"],
                "phase": self.gate["phase"], "active": [], "unknown": [], "eligible": True,
                "desiredDigest": "f" * 64})
        self.gate.update(phase="applying", target=DESIRED)
        self.save_gate()

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

    def test_gate_only_preflight_begin_and_clear_preserve_absence_provenance(self):
        with BoundedBackendFixture(gate_only=True) as fixture:
            tasks = self.include("production-operation-state.yml")
            tasks += ("- ansible.builtin.assert:\n    that:\n"
                "      - not relay_production_operation_record_present | bool\n"
                "      - relay_production_operation_continuation.backendAbsent\n")
            tasks += self.include("production-operation-state-begin.yml")
            result = self.run_tasks(fixture, tasks)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(fixture.record.read_bytes()), {
                "schemaVersion": "1", "state": "RECOVERY_REQUIRED", "phase": "apply", "target_head": DESIRED})
            # A later inspection recognizes the created desired reservation while
            # retaining the original absence and original target in the receipt.
            result = self.run_tasks(fixture, self.include("production-operation-state.yml"))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            fixture.select_desired()
            variables = fixture.variables()
            variables["relay_production_operation_clear_head"] = DESIRED
            result = self.run_tasks(fixture, self.include("production-operation-state-clear.yml"), variables)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse(fixture.record.exists())
            receipt = json.loads(fixture.paths["receipt"].read_bytes())
            self.assertEqual(receipt["original"], fixture.receipt["original"])
            self.assertTrue(receipt["original"]["backendAbsent"])
            self.assertEqual(receipt["original"]["backendBytes"], "")
            self.assertFalse(fixture.paths["receipt"].with_name(fixture.paths["receipt"].stem + ".original.json").exists())

    def test_gate_only_preflight_rejects_unproven_original_binding(self):
        for damage in ("missing-gate", "changed-snapshot", "wrong-admission-uuid", "wrong-retained-target",
                       "wrong-selected-target", "missing-receipt", "missing-authorization", "lost-original-record"):
            with self.subTest(damage=damage), BoundedBackendFixture(gate_only=damage != "lost-original-record") as fixture:
                variables = fixture.variables()
                if damage == "missing-gate":
                    fixture.paths["gate"].unlink()
                elif damage == "changed-snapshot":
                    fixture.gate["previousActive"]["production"]["active"] = False
                    fixture.save_gate()
                elif damage == "wrong-admission-uuid":
                    variables["relay_admission_operation_id"] = "87654321-1234-1234-1234-123456789abc"
                elif damage == "wrong-retained-target":
                    variables["relay_bounded_recovery_binding"] = {**fixture.binding, "retainedTarget": "9" * 40}
                elif damage == "wrong-selected-target":
                    variables["relay_production_operation_target_head"] = "9" * 40
                elif damage == "missing-receipt":
                    fixture.paths["receipt"].unlink()
                elif damage == "missing-authorization":
                    variables["relay_admission_recovery_authorized"] = False
                else:
                    fixture.record.unlink()
                result = self.run_tasks(fixture, self.include("production-operation-state.yml") +
                    self.include("production-operation-state-begin.yml"), variables)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertFalse(fixture.record.exists())

    def test_gate_only_begin_rechecks_absence_gate_and_receipt_under_lock(self):
        for damage in ("gate-phase", "gate-snapshot", "receipt", "receipt-digest", "concurrent-record", "dangling-record"):
            with self.subTest(damage=damage), BoundedBackendFixture(gate_only=True) as fixture:
                tasks = self.include("production-operation-state.yml")
                if damage.startswith("gate-"):
                    value = {**fixture.gate}
                    if damage == "gate-phase":
                        value["phase"] = "recovery-required"
                    else:
                        value["previousActive"] = {}
                    path = fixture.paths["gate"]
                elif damage == "receipt":
                    value, path = {**fixture.receipt, "state": "complete"}, fixture.paths["receipt"]
                elif damage == "receipt-digest":
                    value, path = {**fixture.receipt, "desiredDigest": "9" * 64}, fixture.paths["receipt"]
                else:
                    value, path = {"schemaVersion": "1", "state": "RECOVERY_REQUIRED", "phase": "apply",
                                   "target_head": DESIRED}, fixture.record
                if damage == "dangling-record":
                    tasks += "- ansible.builtin.file:\n    state: link\n    force: true\n    src: /absent-relay-fixture\n    dest: " + json.dumps(str(path)) + "\n"
                else:
                    tasks += "- ansible.builtin.copy:\n    mode: '0600'\n    dest: " + json.dumps(str(path)) + "\n    content: " + json.dumps(json.dumps(value)) + "\n"
                tasks += self.include("production-operation-state-begin.yml")
                result = self.run_tasks(fixture, tasks)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertRegex(result.stdout + result.stderr, "BOUNDED_RECOVERY_|PRODUCTION_OPERATION_CONTINUATION_BINDING_INVALID")
                if damage not in ("concurrent-record", "dangling-record"):
                    self.assertFalse(fixture.record.exists())
                self.assertEqual(json.loads(fixture.paths["receipt"].read_bytes())["original"], fixture.receipt["original"])

    def test_actual_gate_only_ansible_path_restores_six_known_runners_and_opens_same_operation(self):
        from test_upgrade_lifecycle_activation import UpgradeActivationTests, service
        sys.path.insert(0, str(ROOT.parent / "tests"))
        from test_retained_activation import payload
        with BoundedBackendFixture(gate_only=True, reserve=False) as fixture:
            harness = UpgradeActivationTests()
            self.addCleanup(harness.doCleanups)
            original = {"reviewer.service": service(41, active=True, enabled="enabled"),
                        "production.service": service(enabled="enabled"),
                        "general.service": service(43, active=True, enabled="enabled"),
                        **{"pool-" + str(i) + ".service": service(enabled="enabled") for i in range(2, 7)}}
            maintenance = payload()["binding"]["runnerMaintenance"]
            fixture.binding["runnerMaintenance"] = {**maintenance, "retainedTarget": ORIGINAL}
            fixture.paths["gate"].unlink()
            tasks, values, _ = harness.maintained_fixture(fixture.work, original, original, False, backend=fixture)
            result = harness.run_play(fixture.work, tasks[:1], values)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            fixture.gate = json.loads(fixture.paths["gate"].read_bytes())
            saved = fixture.gate["previousActive"]
            fixture.gate["phase"] = "recovery-required"
            fixture.save_gate()
            fixture.reserve()
            repaired = {**original, "production.service": service(52, active=True, enabled="enabled"),
                        **{"pool-" + str(i) + ".service": service(60 + i, active=True, enabled="enabled") for i in range(2, 7)}}
            tasks, values, trace = harness.maintained_fixture(fixture.work, repaired, repaired, True, backend=fixture)
            values.update(fixture.variables())
            # The service adapter uses synthetic codex-relay unit names; all
            # protected backend paths still use the unique fixture namespace.
            values["relay_namespace"] = "codex-relay"
            tasks = [{"ansible.builtin.include_tasks": str(ROOT / "tasks/production-operation-state.yml")},
                     tasks[0], {"ansible.builtin.include_tasks": str(ROOT / "tasks/production-operation-state-begin.yml")},
                     *tasks[1:]]
            history = fixture.work / "history"
            history.write_bytes(b"immutable historical attempts")
            result = harness.run_play(fixture.work, tasks, values)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("RELAY_UPGRADE_ACTIVATION_VALIDATED=", result.stdout)
            self.assertFalse(trace.exists(), "healthy maintained processes must survive")
            fixture.select_desired()
            values["relay_production_operation_clear_head"] = DESIRED
            result = harness.run_play(fixture.work, [{"ansible.builtin.include_tasks": str(
                ROOT / "tasks/production-operation-state-clear.yml")}], values)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            helper = str(fixture.work / "relay-admission")
            for arguments in (["phase", "--operation", OPERATION, "--phase", "verified"],
                              ["resume", "--operation", OPERATION]):
                subprocess.run([helper, *arguments], check=True, capture_output=True)
                gate = json.loads(fixture.paths["gate"].read_bytes())
                if arguments[0] == "phase":
                    self.assertEqual((gate["operationId"], gate["phase"], gate["verifiedRevision"]),
                                     (OPERATION, "verified", DESIRED))
                    self.assertEqual(gate["previousActive"], saved)
            gate = json.loads(fixture.paths["gate"].read_bytes())
            self.assertEqual(gate["phase"], "open")
            self.assertEqual(history.read_bytes(), b"immutable historical attempts")
            self.assertFalse(fixture.record.exists())
            self.assertEqual(json.loads(fixture.paths["receipt"].read_bytes())["original"], fixture.receipt["original"])
            self.assertFalse(fixture.paths["receipt"].with_name(fixture.paths["receipt"].stem + ".original.json").exists())

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
