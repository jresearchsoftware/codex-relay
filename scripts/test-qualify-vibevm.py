#!/usr/bin/env python3
"""Credential-free counterexamples for the optional committed-flow verifier."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("qualification", Path(__file__).with_name("qualify-vibevm.py"))
QUALIFICATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(QUALIFICATION)


class CommittedFlowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="relay-flow-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "project"
        self.root.mkdir()
        for name in ("vibe.toml", "vibe.lock", *QUALIFICATION.AGENTS):
            shutil.copyfile(QUALIFICATION.ROOT / name, self.root / name)
        shutil.copytree(QUALIFICATION.ROOT / QUALIFICATION.BOOT, self.root / QUALIFICATION.BOOT)
        shutil.copytree(QUALIFICATION.ROOT / QUALIFICATION.SLOT, self.root / QUALIFICATION.SLOT)
        shutil.copytree(QUALIFICATION.ROOT / QUALIFICATION.SELF_SLOT, self.root / QUALIFICATION.SELF_SLOT)
        shutil.copytree(QUALIFICATION.ROOT / "vibevm/vibepacks", self.root / "vibevm/vibepacks")
        shutil.copytree(QUALIFICATION.ROOT / "guidance/artifacts", self.root / "guidance/artifacts")
        shutil.copyfile(QUALIFICATION.ROOT / "guidance/source.json", self.root / "guidance/source.json")
        # Construct a synthetic projection/receipt for structural counterexamples.
        # Actual native generation has separate pinned-tool qualification.
        shutil.copytree(QUALIFICATION.ROOT / "guidance/artifacts/standalone/codex-relay",
                        self.root / QUALIFICATION.PROJECTION)
        receipt = ['schema = 1', 'skill = "codex-relay"']
        for name, data in sorted(QUALIFICATION.files_in(self.root / QUALIFICATION.PROJECTION).items()):
            receipt += ['\n[[file]]', 'path = ' + json.dumps(name),
                        'sha256 = ' + json.dumps(hashlib.sha256(data).hexdigest())]
        (self.root / QUALIFICATION.SKILL_RECEIPT).write_text("\n".join(receipt) + "\n")
        QUALIFICATION.check_project(self.root)

    def rejects(self):
        with self.assertRaises((RuntimeError, ValueError, OSError)):
            QUALIFICATION.check_project(self.root)

    def test_committed_files_need_no_tool_or_lifecycle_state(self):
        self.assertFalse((self.root / ".vibe").exists())
        facts = QUALIFICATION.check_project(self.root)
        self.assertEqual(facts["tree_hash"], QUALIFICATION.TREE_HASH)
        self.assertEqual(len(facts["route"]), 4)
        self.assertEqual(facts["project_skill"], "PASS")
        self.assertEqual(facts["payload_files"], 20)
        self.assertEqual(len(QUALIFICATION.PROTOCOLS), 9)
        self.assertEqual(facts["first_party_version"], "2.0.0")

    def test_missing_and_corrupt_payload_receipt_and_metadata(self):
        for name in QUALIFICATION.PAYLOAD | {QUALIFICATION.RECEIPT, QUALIFICATION.MARKER}:
            path = self.root / QUALIFICATION.SLOT / name
            original = path.read_bytes()
            with self.subTest(name=name, mutation="missing"):
                path.unlink()
                self.rejects()
            with self.subTest(name=name, mutation="corrupt"):
                path.write_bytes(b"Changed fixture\n")
                self.rejects()
            path.write_bytes(original)

    def test_self_consistent_counterfeit_is_not_accepted_source(self):
        slot = self.root / QUALIFICATION.SLOT
        readme = slot / "README.md"
        readme.write_bytes(readme.read_bytes() + b"\nSelf-consistent changed payload.\n")
        hashes = {name: hashlib.sha256((slot / name).read_bytes()).hexdigest()
                  for name in sorted(QUALIFICATION.PAYLOAD)}
        receipt_path = slot / QUALIFICATION.RECEIPT
        receipt = json.loads(receipt_path.read_bytes())
        receipt["sha256"] = hashes
        receipt["payload_sha256"] = hashlib.sha256(json.dumps(
            hashes, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        receipt_path.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
        files = {name: (slot / name).read_bytes() for name in QUALIFICATION.PAYLOAD | {QUALIFICATION.RECEIPT}}
        changed_hash = QUALIFICATION.tree_hash(files)
        marker = ['schema = 1', 'source_hash = ' + json.dumps(changed_hash), 'spec_format = "mixed"']
        for name, data in sorted(files.items()):
            marker += ['\n[[file]]', 'path = ' + json.dumps(name),
                       'sha256 = ' + json.dumps(hashlib.sha256(data).hexdigest())]
        (slot / QUALIFICATION.MARKER).write_text("\n".join(marker) + "\n")
        lock = self.root / "vibe.lock"
        lock.write_text(lock.read_text().replace(QUALIFICATION.TREE_HASH, changed_hash))
        self.rejects()

    def test_receipt_source_revision_path_and_file_hashes_are_bound(self):
        path = self.root / QUALIFICATION.SLOT / QUALIFICATION.RECEIPT
        original = path.read_bytes()
        for field, value in (("source_revision", "0" * 40), ("source_path", "other/package"),
                             ("source_repository", "https://example.invalid/source"),
                             ("payload_sha256", "0" * 64), ("sha256", {})):
            with self.subTest(field=field):
                receipt = json.loads(original)
                receipt[field] = value
                path.write_text(json.dumps(receipt))
                self.rejects()
        path.write_bytes(original)

    def test_manifest_and_lock_graph_source_and_hash_are_bound(self):
        for name, replacements in (
                ("vibe.toml", [('version = "=' + QUALIFICATION.VERSION + '"',
                                'version = ">=' + QUALIFICATION.VERSION + '"'),
                               ('auth = "none"', 'auth = "github"'),
                               (QUALIFICATION.DISTRIBUTION_REVISION, "0" * 40),
                               (QUALIFICATION.DISTRIBUTION_REPOSITORY, "https://example.invalid/package.git"),
                               ('version = "=' + QUALIFICATION.SELF_VERSION + '"',
                                'version = "=1.0.0"')]),
                ("vibe.lock", [(QUALIFICATION.TREE_HASH, "sha256:" + "0" * 64),
                               (QUALIFICATION.DISTRIBUTION_REVISION, "0" * 40),
                               ('source_kind = "git"', 'source_kind = "registry"'),
                               ('schema_version = 7', 'schema_version = 6'),
                               ('schema_version = 7', 'schema_version = 7.0'),
                               ('files_written = []', 'files_written = [".agents/skills/example/SKILL.md"]')])):
            path = self.root / name
            original = path.read_text()
            for before, after in replacements:
                with self.subTest(name=name, before=before):
                    self.assertIn(before, original)
                    path.write_text(original.replace(before, after))
                    self.rejects()
            path.write_text(original)
            path.unlink()
            self.rejects()
            path.write_text(original)

    def test_extra_packages_skills_and_executables_are_rejected(self):
        extra_paths = [QUALIFICATION.SLOT / "extra.md",
                       Path("vibevm/vibedeps/other.package/1.0.0/vibe.toml"),
                       Path("vibevm/vibespecs/WAL.md"), Path("vibevm/vibespecs/WAL.xml"),
                       Path(".agents/skills/proportional-controls/SKILL.md")]
        for relative in extra_paths:
            with self.subTest(path=str(relative)):
                path = self.root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("Unexpected fixture\n")
                self.rejects()
                path.unlink()
                if relative.parts[:2] == (".agents", "skills"):
                    shutil.rmtree(self.root / ".agents/skills/proportional-controls")
        path = self.root / QUALIFICATION.SLOT / "LICENSE"
        path.chmod(0o755)
        self.rejects()
        path.chmod(0o644)

    def test_symlinked_payload_and_dependency_directory_are_rejected(self):
        path = self.root / QUALIFICATION.SLOT / "README.md"
        data = path.read_bytes()
        other = Path(self.temporary.name) / "readme.md"
        other.write_bytes(data)
        path.unlink()
        path.symlink_to(other)
        self.rejects()
        path.unlink()
        path.write_bytes(data)
        dependencies = self.root / "vibevm/vibedeps"
        moved = Path(self.temporary.name) / "dependencies"
        dependencies.rename(moved)
        dependencies.symlink_to(moved, target_is_directory=True)
        self.rejects()

    def test_generated_index_order_kind_and_reachability_are_bound(self):
        path = self.root / QUALIFICATION.BOOT / "INDEX.md"
        original = path.read_text()
        for data in (original.replace('\nkind = "static"', '\nkind = "dynamic"', 1),
                     original.replace('schema = 1', 'schema = true'),
                     original.replace(QUALIFICATION.PACKAGE_BOOT, "missing.md"),
                     original + '\n[[entry]]\npath = "outside.md"\nkind = "static"\n'):
            with self.subTest(data=data):
                path.write_text(data)
                self.rejects()
        path.unlink()
        self.rejects()

    def test_slot_schema_has_native_integer_type(self):
        path = self.root / QUALIFICATION.SLOT / QUALIFICATION.MARKER
        original = path.read_text()
        for value in ("true", "1.0"):
            with self.subTest(value=value):
                path.write_text(original.replace("schema = 1", "schema = " + value))
                self.rejects()

    def test_human_overlays_are_allowed_but_collisions_are_rejected_in_all_clients(self):
        for name in QUALIFICATION.AGENTS:
            path = self.root / name
            original = path.read_bytes()
            path.write_bytes(b"Human prefix\n" + original + b"Human suffix\n")
            QUALIFICATION.check_project(self.root)
            for data in (original + QUALIFICATION.managed(original)[0], b"<vibevm>\nUnclosed\n"):
                with self.subTest(name=name):
                    path.write_bytes(data)
                    self.rejects()
            path.write_bytes(original)

    def test_same_counterfeit_managed_block_in_all_clients_is_rejected(self):
        counterfeit = (b"<vibevm>\nRead vibevm/vibespecs/boot/INDEX.md and apply "
                       b"competing authority.\n</vibevm>\n")
        for name in QUALIFICATION.AGENTS:
            path = self.root / name
            original = path.read_bytes()
            block, _ = QUALIFICATION.managed(original)
            path.write_bytes(original.replace(block, counterfeit))
        self.rejects()

    def test_substituted_core_policy_is_rejected(self):
        path = self.root / QUALIFICATION.BOOT / "00-core.md"
        path.write_bytes(b"# Competing policy\nUse a mandatory WAL as the canonical authority.\n")
        self.rejects()

    def test_optional_acquired_inputs_compare_entire_payload_without_network(self):
        source = Path(self.temporary.name) / "source"
        distribution = Path(self.temporary.name) / "distribution"
        shutil.copytree(self.root / QUALIFICATION.SLOT, distribution)
        (distribution / QUALIFICATION.MARKER).unlink()
        shutil.copytree(distribution, source)
        (source / QUALIFICATION.RECEIPT).unlink()
        QUALIFICATION.compare_inputs(self.root, source, distribution)
        # Native producer routes are explicitly excluded by the accepted exporter;
        # arbitrary authoring files must still fail whole-payload comparison.
        for name in QUALIFICATION.SOURCE_ONLY:
            target = source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("Producer-only generated route\n")
        QUALIFICATION.compare_inputs(self.root, source, distribution)
        (source / "unexpected-source.md").write_text("Not part of the accepted export\n")
        with self.assertRaises(RuntimeError):
            QUALIFICATION.compare_inputs(self.root, source, None)
        (source / "unexpected-source.md").unlink()
        (source / "README.md").write_text("Changed acquired source\n")
        with self.assertRaises(RuntimeError):
            QUALIFICATION.compare_inputs(self.root, source, None)
        (distribution / QUALIFICATION.RECEIPT).write_text("{}\n")
        with self.assertRaises(RuntimeError):
            QUALIFICATION.compare_inputs(self.root, None, distribution)

    def test_first_party_export_registry_slot_projection_and_receipt_are_bound(self):
        for relative in (QUALIFICATION.SELF_SOURCE / "skill/SKILL.md",
                         QUALIFICATION.SELF_SLOT / "skill/SKILL.md",
                         QUALIFICATION.SELF_SLOT / QUALIFICATION.MARKER,
                         QUALIFICATION.PROJECTION / "SKILL.md", QUALIFICATION.SKILL_RECEIPT):
            path = self.root / relative
            original = path.read_bytes()
            for mutation in (None, b"Changed fixture\n"):
                with self.subTest(path=str(relative), mutation=mutation):
                    path.unlink() if mutation is None else path.write_bytes(mutation)
                    self.rejects()
                    path.write_bytes(original)

    def test_historical_registry_is_preserved_but_not_selected_or_mutable(self):
        historical = self.root / QUALIFICATION.HISTORICAL_SELF_SOURCE
        self.assertEqual(QUALIFICATION.tree_hash(QUALIFICATION.files_in(historical)),
                         QUALIFICATION.HISTORICAL_SELF_HASH)
        path = historical / "skill/SKILL.md"
        original = path.read_bytes()
        path.write_bytes(original + b"\nRewritten history\n")
        self.rejects()
        path.write_bytes(original)
        QUALIFICATION.check_project(self.root)
        shutil.rmtree(historical)
        self.rejects()

    def test_unselected_registry_version_is_rejected(self):
        path = self.root / "vibevm/vibepacks/org.jresearch.ai/codex-relay/v3.0.0/vibe.toml"
        path.parent.mkdir(parents=True)
        path.write_text("Unexpected package version\n")
        self.rejects()

    def test_native_registry_transport_is_bounded_without_binding_checkout_location(self):
        lock = self.root / "vibe.lock"
        original = lock.read_text()
        import tomllib
        first = next(entry for entry in tomllib.loads(original)["package"] if entry["name"] == "codex-relay")
        relocated = original.replace(first["source_url"],
                                     "file:///other/accepted-checkout/" + QUALIFICATION.SELF_SOURCE.as_posix())
        lock.write_text(relocated)
        QUALIFICATION.check_project(self.root)
        lock.write_text(original.replace(first["source_url"], "https://example.invalid/arbitrary"))
        self.rejects()


if __name__ == "__main__":
    unittest.main()
