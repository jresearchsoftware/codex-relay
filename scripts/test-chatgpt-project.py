#!/usr/bin/env python3
"""Offline Relay consumer integration tests for the unchanged shared projector.

HEAD is captured once as a committed test snapshot, not inferred owner acceptance.
Candidate binding/custom/output are exercised against that explicit snapshot.
Fixtures and local commits stay in temporary directories; no network or live
ChatGPT Settings/Sources evidence is obtained by this suite.
"""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "vibevm/vibedeps/org.jresearch.ai.development-governance/7.0.0/tools/chatgpt/project.py"
SPEC = importlib.util.spec_from_file_location("shared_chatgpt_project", GENERATOR)
PROJECTOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROJECTOR)
ANCHOR = "https://github.com/jresearchsoftware/codex-relay/issues/101"


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


class RelayChatGPTProjectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.revision = git(ROOT, "rev-parse", "HEAD^{commit}").decode().strip()
        cls.binding = json.loads((ROOT / "chatgpt/binding.json").read_text())
        cls.custom = (ROOT / "chatgpt/custom.md").read_text()
        cls.instructions = (ROOT / "chatgpt/instructions.md").read_bytes()
        # Export only committed native/project inputs, excluding dirty candidates
        # and lifecycle state. No checkout, fetch or repository config is changed.
        cls.archive = git(ROOT, "archive", cls.revision, "AGENTS.md", "vibe.toml", "vibe.lock",
                          "vibevm/vibespecs/boot", "vibevm/vibedeps",
                          *cls.binding["local_sources"])

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="relay-chatgpt-test-")
        self.addCleanup(temporary.cleanup)
        self.temporary = Path(temporary.name)
        self.root = self.temporary / "consumer"
        self.directory = self.root / "chatgpt"
        self.directory.mkdir(parents=True)
        self.binding_path = self.directory / "binding.json"
        self.write_binding(self.binding)
        (self.directory / "custom.md").write_text(self.custom)
        (self.directory / "instructions.md").write_bytes(self.instructions)

    def write_binding(self, binding):
        self.binding_path.write_text(json.dumps(binding, indent=2) + "\n")

    def maintain(self, source=ROOT, revision=None, update=False):
        return PROJECTOR.maintain(self.root, self.binding_path, source,
                                  revision or self.revision, ANCHOR, update)

    def cli(self, action, *extra, source=ROOT, revision=None):
        command = [sys.executable, str(GENERATOR), action,
                   "--repository", str(self.root), "--binding", "chatgpt/binding.json"]
        if action != "compare":
            command += ["--source-repository", str(source), "--accepted-sha",
                        revision or self.revision, "--authority-anchor", ANCHOR]
        return subprocess.run(command + list(extra), stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True)

    def snapshot(self, name="source"):
        source = self.temporary / name
        source.mkdir()
        with tarfile.open(fileobj=io.BytesIO(self.archive)) as archive:
            for item in archive:
                if item.isfile():
                    path = source / item.name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(archive.extractfile(item).read())
        git(source, "init", "--quiet")
        revision = self.commit(source)
        self.assertEqual(git(source, "status", "--porcelain"), b"")
        self.assertFalse((source / ".vibe").exists())
        return source, revision

    def commit(self, source):
        git(source, "add", "--all")
        git(source, "-c", "user.name=Relay Test Fixture", "-c",
            "user.email=fixture@example.invalid", "-c", "commit.gpgsign=false",
            "-c", "core.hooksPath=/dev/null", "commit", "--quiet", "-m", "Test snapshot")
        return git(source, "rev-parse", "HEAD").decode().strip()

    def test_real_relay_binding_reproduces_complete_desired_output(self):
        self.assertEqual(self.binding["repository"], "jresearchsoftware/codex-relay")
        self.assertEqual(self.binding["native"], "materialized")
        self.assertFalse(self.binding["cache_enabled"])
        artifacts = PROJECTOR.project(ROOT, self.binding, self.custom, self.revision, ANCHOR)
        self.assertEqual(artifacts, {"instructions.md": self.instructions})
        text = self.instructions.decode()
        self.assertLess(len(text), self.binding["character_budget"])
        self.assertTrue(text.startswith(PROJECTOR.MARKER))
        self.assertIn("/blob/main/AGENTS.md", text)
        self.assertNotIn(self.revision, text)
        self.assertFalse((ROOT / "chatgpt/receipt.json").exists())

    def test_custom_edit_check_update_and_no_op_do_not_rewrite_unchanged_bytes(self):
        path = self.directory / "instructions.md"
        timestamp = 1_600_000_000_123_456_789
        os.utime(path, ns=(timestamp, timestamp))
        initial = path.stat().st_mtime_ns
        for action in ("check", "update"):
            result = self.cli(action)
            self.assertEqual(result.returncode, 0, result.stderr)
            status = json.loads(result.stdout)
            self.assertEqual(status["schema"], 4)
            self.assertEqual(status["effective_content"], "NO_OP")
            self.assertEqual(status["sources"], "DISABLED")
            self.assertFalse(status["live_settings_verified"])
            self.assertEqual(path.stat().st_mtime_ns, initial)
        custom = self.directory / "custom.md"
        custom.write_text(self.custom + "\nTemporary consumer instruction.\n")
        result = self.cli("check")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(json.loads(result.stdout)["instructions"], "CHANGED")
        self.assertEqual(path.read_bytes(), self.instructions)
        result = self.cli("update")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["instructions"], "CHANGED")
        self.assertIn(b"Temporary consumer instruction.", path.read_bytes())
        os.utime(path, ns=(timestamp, timestamp))
        result = self.cli("update")
        self.assertEqual(result.returncode, 0, result.stderr)
        status = json.loads(result.stdout)
        self.assertEqual(status["instructions"], "NO_OP")
        self.assertIn("earlier changed-text reconciliation obligation", status["application"])
        self.assertEqual(path.stat().st_mtime_ns, initial)

    def test_optional_sources_are_exact_snapshots_and_cache_only_changes(self):
        binding = dict(self.binding, cache_enabled=True, cache_selection=["AGENTS.md"])
        self.write_binding(binding)
        path = self.directory / "instructions.md"
        initial = path.stat().st_mtime_ns
        source = PROJECTOR.Snapshot(ROOT, self.revision)
        for selection in (["AGENTS.md"], ["AGENTS.md", self.binding["local_sources"][0]]):
            with self.subTest(selection=selection):
                binding["cache_selection"] = selection
                self.write_binding(binding)
                status, changed = self.maintain(update=True)
                self.assertTrue(changed)
                self.assertEqual(status["instructions"], "NO_OP")
                self.assertEqual(status["sources"], "CHANGED")
                self.assertFalse(status["live_settings_verified"])
                self.assertIn("unchanged Instructions require no new application", status["application"])
                self.assertEqual(path.stat().st_mtime_ns, initial)
                manifest = json.loads((self.directory / "sources-manifest.json").read_bytes())
                self.assertEqual(manifest["kind"], "optional-source-cache")
                self.assertEqual(manifest["accepted_sha"], self.revision)
                self.assertEqual(manifest["authority_anchor"], ANCHOR)
                self.assertEqual(manifest["files"], {
                    name: hashlib.sha256(source.read(name)).hexdigest() for name in selection})
                cache = (self.directory / "sources.md").read_bytes()
                for name in selection:
                    self.assertIn(source.read(name), cache)
                    self.assertIn(("/blob/" + self.revision + "/" + name).encode(), cache)
        # Disabling the optional cache only removes its two outputs.
        unrelated = self.directory / "owner-notes.md"
        unrelated.write_text("Preserve this owner file.\n")
        self.write_binding(self.binding)
        status, changed = self.maintain(update=True)
        self.assertTrue(changed)
        self.assertEqual(status["instructions"], "NO_OP")
        self.assertFalse((self.directory / "sources.md").exists())
        self.assertFalse((self.directory / "sources-manifest.json").exists())
        self.assertEqual(unrelated.read_text(), "Preserve this owner file.\n")
        self.assertEqual(path.stat().st_mtime_ns, initial)
        self.assertFalse(self.maintain()[1])

    def test_clean_native_snapshot_and_dirty_worktree_use_explicit_committed_revision(self):
        source, revision = self.snapshot()
        lock = tomllib.loads((source / "vibe.lock").read_text())
        packages = {package["name"]: package for package in lock["package"]}
        relay, shared = packages["codex-relay"], packages["development-governance"]
        # Inspect the materializer's recorded edge and selected routes; this is
        # not another version-range solver or a substitute for VibeVM qualification.
        self.assertIn("org.jresearch.ai/development-governance@=" + shared["version"],
                      relay["dependencies"])
        relay_slot = "vibevm/vibedeps/org.jresearch.ai.codex-relay/" + relay["version"]
        relay_manifest = tomllib.loads((source / relay_slot / "vibe.toml").read_text())
        self.assertIn("org.jresearch.ai/development-governance",
                      relay_manifest["requires"]["packages"])
        root_manifest = tomllib.loads((source / "vibe.toml").read_text())
        self.assertEqual(root_manifest["requires"]["packages"]
                         ["org.jresearch.ai/development-governance"]["version"],
                         "=" + shared["version"])
        routes = tomllib.loads((source / PROJECTOR.INDEX).read_text())["entry"]
        self.assertTrue(any(entry["path"].startswith(relay_slot + "/") for entry in routes))
        self.assertTrue(any(entry["path"].startswith(
            "vibevm/vibedeps/org.jresearch.ai.development-governance/" + shared["version"] + "/")
                            for entry in routes))
        status, changed = self.maintain(source, revision)
        self.assertFalse(changed)
        self.assertEqual(status["instructions"], "NO_OP")
        (source / "AGENTS.md").write_text("Uncommitted candidate guidance.\n")
        route = tomllib.loads((source / PROJECTOR.INDEX).read_text())["entry"][0]["path"]
        (source / route).unlink()
        self.assertTrue(git(source, "status", "--porcelain"))
        self.assertFalse(self.maintain(source, revision)[1])
        self.assertEqual(PROJECTOR.project(source, self.binding, self.custom, revision, ANCHOR),
                         {"instructions.md": self.instructions})

    def test_changed_committed_native_route_keeps_instructions_and_refreshes_selected_cache(self):
        source, previous = self.snapshot()
        route = "vibevm/vibespecs/boot/90-user.md"
        binding = dict(self.binding, cache_enabled=True, cache_selection=[route])
        self.write_binding(binding)
        self.maintain(source, previous, update=True)
        instructions = self.directory / "instructions.md"
        original_mtime = instructions.stat().st_mtime_ns
        old_cache = (self.directory / "sources.md").read_bytes()
        path = source / route
        path.write_bytes(path.read_bytes() + b"\nChanged native routing fixture.\n")
        current = self.commit(source)
        self.assertNotEqual(previous, current)
        # A source-only change validates against the new explicit snapshot even
        # when the effective Instructions remain unchanged.
        self.write_binding(self.binding)
        self.assertEqual(PROJECTOR.project(source, self.binding, self.custom, current, ANCHOR),
                         {"instructions.md": self.instructions})
        self.write_binding(binding)
        status, changed = self.maintain(source, current, update=True)
        self.assertTrue(changed)
        self.assertEqual(status["instructions"], "NO_OP")
        self.assertEqual(status["sources"], "CHANGED")
        self.assertFalse(status["live_settings_verified"])
        self.assertEqual(instructions.stat().st_mtime_ns, original_mtime)
        self.assertEqual(instructions.read_bytes(), self.instructions)
        self.assertNotEqual((self.directory / "sources.md").read_bytes(), old_cache)
        manifest = json.loads((self.directory / "sources-manifest.json").read_bytes())
        self.assertEqual(manifest["accepted_sha"], current)
        self.assertEqual(manifest["files"][route], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertFalse(self.maintain(source, current)[1])

    def test_committed_invalid_native_inputs_refuse_even_when_instructions_would_be_identical(self):
        mutations = ("lock-schema", "index-schema", "receipt-hash", "lock-identity", "missing-route")
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                source, _ = self.snapshot(mutation)
                index = tomllib.loads((source / PROJECTOR.INDEX).read_text())
                native_route = next(entry["path"] for entry in index["entry"]
                                    if entry["path"].startswith("vibevm/vibedeps/"))
                slot = "/".join(native_route.split("/")[:4])
                if mutation == "missing-route":
                    (source / native_route).unlink()
                    expected = "Missing accepted source"
                else:
                    if mutation == "lock-schema":
                        path, before, after = source / "vibe.lock", "schema_version = 7", "schema_version = 6"
                        expected = "Unsupported native lock schema"
                    elif mutation == "index-schema":
                        path, before, after = source / PROJECTOR.INDEX, "schema = 1", "schema = 2"
                        expected = "Unsupported native INDEX schema"
                    elif mutation == "lock-identity":
                        path = source / "vibe.lock"
                        before = tomllib.loads(path.read_text())["package"][0]["content_hash"]
                        after, expected = "sha256:" + "0" * 64, "Lock/slot identity mismatch"
                    else:
                        path = source / slot / ".vibe-slot.toml"
                        before = tomllib.loads(path.read_text())["file"][0]["sha256"]
                        after, expected = "0" * 64, "Materialized file differs from native receipt"
                    original = path.read_text()
                    self.assertIn(before, original)
                    path.write_text(original.replace(before, after, 1))
                revision = self.commit(source)
                with self.assertRaisesRegex(ValueError, expected):
                    self.maintain(source, revision, update=True)
                self.assertEqual((self.directory / "instructions.md").read_bytes(), self.instructions)
                if mutation == "missing-route":
                    result = self.cli("check", source=source, revision=revision)
                    self.assertEqual(result.returncode, 2)
                    self.assertIn(expected, result.stderr)

    def test_owner_export_comparison_is_exact_read_only_and_never_live_proof(self):
        path = self.directory / "instructions.md"
        before = path.stat().st_mtime_ns
        exported = self.temporary / "owner-export.md"
        for format_name in ("raw", "fenced"):
            with self.subTest(format=format_name):
                content = self.instructions
                if format_name == "fenced":
                    content = b"```markdown\n" + content + b"```\n"
                exported.write_bytes(content)
                result = self.cli("compare", "--live-export", str(exported),
                                  "--live-format", format_name)
                self.assertEqual(result.returncode, 0, result.stderr)
                status = json.loads(result.stdout)
                self.assertEqual(status["comparison"], "NO_OP")
                self.assertFalse(status["live_settings_verified"])
                self.assertEqual(status["baseline_provenance"], "owner-supplied export; UI unverified")
                self.assertEqual(exported.read_bytes(), content)
        exported.write_bytes(self.instructions + b"\nUnknown live owner rule.\n")
        result = self.cli("compare", "--live-export", str(exported))
        self.assertEqual(result.returncode, 0, result.stderr)
        status = json.loads(result.stdout)
        self.assertEqual(status["comparison"], "CHANGED")
        self.assertFalse(status["live_settings_verified"])
        self.assertIn("Unknown live owner rule.", status["diff"])
        self.assertEqual(path.read_bytes(), self.instructions)
        self.assertEqual(path.stat().st_mtime_ns, before)
        self.assertIn(b"Unknown live owner rule.", exported.read_bytes())


if __name__ == "__main__":
    unittest.main()
