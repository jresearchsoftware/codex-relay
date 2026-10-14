#!/usr/bin/env python3
"""Observable standalone install/update/rollback/removal and generated-byte tests."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("relay_project", ROOT / "guidance/project.py")
project = importlib.util.module_from_spec(spec)
spec.loader.exec_module(project)


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="relay-guidance-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.consumer = self.root / "consumer"
        self.consumer.mkdir()
        self.agents = b"# Consumer policy\r\nKeep my local approval convention.\r\n"
        (self.consumer / "AGENTS.md").write_bytes(self.agents)
        neighbor = self.consumer / ".agents/skills/local-skill/SKILL.md"
        neighbor.parent.mkdir(parents=True)
        neighbor.write_text("local skill")
        self.source = self.make_source("one", "0.1.0", "original")

    def make_source(self, directory, version, body, extra=None):
        source = self.root / directory
        files = {"SKILL.md": ("---\nname: codex-relay\ndescription: Relay tasks\n---\n" + body).encode(),
                 "scripts/project.py": (ROOT / "guidance/project.py").read_bytes()}
        files.update(extra or {})
        for name, data in files.items():
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        manifest = {"schema_version": 1, "name": "codex-relay", "version": version,
                    "files": {name: project.sha(data) for name, data in files.items()}}
        (source / "PROVENANCE.json").write_bytes(project.encoded(manifest))
        return source

    @property
    def destination(self):
        return self.consumer / ".agents/skills/codex-relay"

    def snapshot(self):
        return {path.relative_to(self.consumer).as_posix(): path.read_bytes()
                for path in self.consumer.rglob("*") if path.is_file()}

    def call(self, command="install", source=None, flags=(), success=True):
        completed = subprocess.run([sys.executable, str(ROOT / "guidance/project.py"), command,
            "--source", str(source or self.source), "--target", str(self.consumer), *flags],
            capture_output=True, text=True)
        self.assertEqual(completed.returncode == 0, success, completed.stdout + completed.stderr)
        return completed

    def install(self, **kwargs):
        return self.call(flags=("--apply", "--bootstrap"), **kwargs)

    def test_plan_has_diff_without_changing_any_bytes(self):
        before = self.snapshot()
        result = self.call(flags=("--bootstrap", "--diff"))
        self.assertIn("+original", result.stdout)
        self.assertEqual(before, self.snapshot())

    def test_install_repeat_update_rollback_remove_preserve_local_content(self):
        self.install()
        installed = self.snapshot()
        self.assertEqual(json.loads(self.install().stdout)["changes"], [])
        self.assertEqual(installed, self.snapshot())
        (self.destination / "local-overlay.md").write_text("local overlay")
        next_source = self.make_source("two", "0.2.0", "updated", {"references/new.md": b"new reference"})
        self.install(source=next_source)
        self.assertIn("updated", (self.destination / "SKILL.md").read_text())
        self.install()
        self.assertFalse((self.destination / "references/new.md").exists())
        self.assertEqual((self.destination / "local-overlay.md").read_text(), "local overlay")
        self.call("remove", flags=("--apply",))
        self.assertEqual((self.consumer / "AGENTS.md").read_bytes(), self.agents)
        self.assertEqual((self.destination / "local-overlay.md").read_text(), "local overlay")
        self.assertEqual((self.consumer / ".agents/skills/local-skill/SKILL.md").read_text(), "local skill")
        self.assertFalse((self.destination / "SKILL.md").exists())

    def test_managed_drift_stops_update_and_removal_before_mutation(self):
        self.install()
        (self.destination / "SKILL.md").write_text("my edit")
        before = self.snapshot()
        self.install(success=False)
        self.call("remove", flags=("--apply",), success=False)
        self.assertEqual(before, self.snapshot())

    def test_foreign_target_collision_preserves_everything(self):
        self.destination.mkdir()
        (self.destination / "SKILL.md").write_text("unmanaged")
        before = self.snapshot()
        self.install(success=False)
        self.assertEqual(before, self.snapshot())

    def test_duplicate_skill_name_at_other_local_path_is_preserved_and_refused(self):
        path = self.consumer / ".agents/skills/local-skill/SKILL.md"
        for name in ("codex-relay", "codex-relay # local adapter", '"codex-relay" # comment',
                     "'codex-relay' # comment", '"\\u0063odex-relay" # escaped scalar'):
            with self.subTest(name=name):
                path.write_text("---\nname: " + name + "\ndescription: my existing adapter\n---\nlocal")
                before = self.snapshot()
                self.install(success=False)
                self.assertEqual(before, self.snapshot())

    def test_corrupt_ownership_suffix_cannot_delete_user_agents(self):
        self.install()
        path = self.destination / project.RECEIPT
        receipt = json.loads(path.read_bytes())
        receipt["bootstrap_suffix_hex"] = (self.consumer / "AGENTS.md").read_bytes().hex()
        path.write_bytes(project.encoded(receipt))
        before = self.snapshot()
        self.call("remove", flags=("--apply",), success=False)
        self.assertEqual(before, self.snapshot())

    def test_new_version_cannot_overwrite_unowned_added_path(self):
        self.install()
        (self.destination / "new.md").write_text("local")
        next_source = self.make_source("two", "0.2.0", "updated", {"new.md": b"managed"})
        before = self.snapshot()
        self.install(source=next_source, success=False)
        self.assertEqual(before, self.snapshot())

    def test_corrupt_source_and_unsafe_manifest_cannot_write(self):
        (self.source / "SKILL.md").write_text("drift")
        before = self.snapshot()
        self.install(success=False)
        self.assertEqual(before, self.snapshot())
        for name in ("../outside", "/outside", "C:/outside", "x\\outside"):
            manifest = {"schema_version": 1, "name": "codex-relay", "version": "0.1.0", "files": {name: "0" * 64}}
            (self.source / "PROVENANCE.json").write_bytes(project.encoded(manifest))
            self.install(success=False)
            self.assertEqual(before, self.snapshot())

    def test_malformed_or_drifted_bootstrap_preserves_bytes(self):
        (self.consumer / "AGENTS.md").write_bytes(self.agents + project.START)
        before = self.snapshot()
        self.install(success=False)
        self.assertEqual(before, self.snapshot())
        (self.consumer / "AGENTS.md").write_bytes(self.agents)
        self.install()
        path = self.consumer / "AGENTS.md"
        path.write_bytes(path.read_bytes().replace(b"Live project", b"Local project"))
        before = self.snapshot()
        self.call("remove", flags=("--apply",), success=False)
        self.assertEqual(before, self.snapshot())

    def test_no_bootstrap_keeps_existing_agents_byte_identical(self):
        self.call(flags=("--apply",))
        self.assertEqual((self.consumer / "AGENTS.md").read_bytes(), self.agents)
        self.call("remove", flags=("--apply",))
        self.assertEqual((self.consumer / "AGENTS.md").read_bytes(), self.agents)

    def test_generated_agents_removed_only_when_owned_and_unchanged(self):
        (self.consumer / "AGENTS.md").unlink()
        self.install()
        self.call("remove", flags=("--apply",))
        self.assertFalse((self.consumer / "AGENTS.md").exists())

    def test_symlink_escape_is_refused_without_following_or_writing(self):
        outside = self.root / "outside"
        outside.mkdir()
        try:
            self.destination.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("This platform cannot create symlinks without additional privilege")
        self.install(success=False)
        self.assertEqual(list(outside.iterdir()), [])


class GeneratedTests(unittest.TestCase):
    def test_generated_forms_and_canonical_bytes_match(self):
        completed = subprocess.run([sys.executable, str(ROOT / "scripts/build-relay-guidance.py"), "--check"],
                                   capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        standalone = ROOT / "guidance/artifacts/standalone/codex-relay"
        package = ROOT / "guidance/artifacts/vpm/skill"
        _, files = project.manifest_files(standalone)
        _, native = project.manifest_files(package)
        self.assertEqual(files, native)
        for path in (ROOT / "packages/codex-relay/skill").rglob("*"):
            if path.is_file():
                self.assertEqual(path.read_bytes(), (standalone / path.relative_to(ROOT / "packages/codex-relay/skill")).read_bytes())


if __name__ == "__main__":
    unittest.main()
