#!/usr/bin/env python3
"""Credential-free counterexamples for the optional committed-flow verifier."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import tempfile
import tomllib
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
        for selection in QUALIFICATION.LANDSCAPE:
            shutil.copytree(QUALIFICATION.ROOT / selection["slot"], self.root / selection["slot"])
        binding = self.root / QUALIFICATION.LOCAL_SUBAGENTS
        binding.parent.mkdir(parents=True)
        shutil.copyfile(QUALIFICATION.ROOT / QUALIFICATION.LOCAL_SUBAGENTS, binding)
        shutil.copyfile(QUALIFICATION.ROOT / QUALIFICATION.LOCAL_GOVERNANCE,
                        self.root / QUALIFICATION.LOCAL_GOVERNANCE)
        shutil.copytree(QUALIFICATION.ROOT / QUALIFICATION.SELF_SLOT, self.root / QUALIFICATION.SELF_SLOT)
        shutil.copytree(QUALIFICATION.ROOT / "vibevm/vibepacks", self.root / "vibevm/vibepacks")
        shutil.copytree(QUALIFICATION.ROOT / "guidance/artifacts", self.root / "guidance/artifacts")
        shutil.copyfile(QUALIFICATION.ROOT / "guidance/source.json", self.root / "guidance/source.json")
        # Construct a synthetic projection/receipt for structural counterexamples.
        # Actual native generation has separate pinned-tool qualification.
        shutil.copytree(QUALIFICATION.ROOT / "guidance/artifacts/vpm/skill",
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

    def test_repeat_install_only_allows_valid_generation_timestamp_changes(self):
        original = (self.root / "vibe.lock").read_bytes()
        metadata = tomllib.loads(original.decode())["meta"]
        timestamp = metadata["generated_at"].encode()
        refreshed = original.replace(timestamp, b"2030-01-02T03:04:05Z")
        QUALIFICATION.check_repeat_lock(original, original)
        QUALIFICATION.check_repeat_lock(original, refreshed)
        for before, after in ((timestamp, b"invalid"),
                              (QUALIFICATION.TREE_HASH.encode(), b"sha256:" + b"0" * 64),
                              (QUALIFICATION.DISTRIBUTION_REVISION.encode(), b"0" * 40),
                              (metadata["generated_by"].encode(), b"other"),
                              (b'@=7.0.1', b'@=6.0.0'),
                              (b'file://', b'file:///changed/')):
            with self.subTest(field=before):
                self.assertIn(before, original)
                with self.assertRaises(RuntimeError):
                    QUALIFICATION.check_repeat_lock(original, original.replace(before, after))

    def test_relocated_install_only_normalizes_native_first_party_checkout_metadata(self):
        original = (self.root / "vibe.lock").read_bytes()
        lock = tomllib.loads(original.decode())
        first = next(entry for entry in lock["package"] if entry["name"] == "codex-relay")
        source = self.root / QUALIFICATION.SELF_SOURCE
        relocated = original.replace(first["source_url"].encode(), source.as_uri().encode())
        relocated = relocated.replace(lock["meta"]["generated_at"].encode(), b"2030-01-02T03:04:05Z")
        first_kind = ('source_kind = "' + first["source_kind"] + '"').encode()
        native = relocated.replace(first_kind, b'source_kind = "local"', 1)
        QUALIFICATION.check_relocation_lock(original, relocated, source, "native-registry")
        QUALIFICATION.check_relocation_lock(original, native, source, "native-local")
        QUALIFICATION.check_relocation_lock(native, native, source, "repeat-local")
        for before, after in ((b'source_kind = "local"', b'source_kind = "git"'),
                              (b'source_kind = "local"', b'source_kind = "arbitrary"'),
                              (first["content_hash"].encode(), b"sha256:" + b"0" * 64),
                              (QUALIFICATION.TREE_HASH.encode(), b"sha256:" + b"0" * 64),
                              (QUALIFICATION.DISTRIBUTION_REVISION.encode(), b"0" * 40),
                              (b'@=7.0.1', b'@=6.0.0'),
                              (b'version = "5.1.0"', b'version = "5.0.0"'),
                              (lock["meta"]["generated_by"].encode(), b'other'),
                              (b'file://', b'file:///foreign/')):
            with self.subTest(field=before):
                self.assertIn(before, native)
                with self.assertRaises(RuntimeError):
                    QUALIFICATION.check_relocation_lock(original, native.replace(before, after), source, "changed")
        for old in (original.replace(first_kind, b'source_kind = "arbitrary"', 1),
                    original.replace(b'file:///', b'file://foreign/'),
                    original.replace(lock["meta"]["generated_at"].encode(), b"invalid")):
            with self.subTest(original=old):
                with self.assertRaises(RuntimeError):
                    QUALIFICATION.check_relocation_lock(old, native, source, "invalid-original")

    def test_committed_files_need_no_tool_or_lifecycle_state(self):
        self.assertFalse((self.root / ".vibe").exists())
        facts = QUALIFICATION.check_project(self.root)
        self.assertEqual(facts["tree_hash"], QUALIFICATION.TREE_HASH)
        self.assertEqual(len(facts["route"]), 6)
        self.assertEqual(facts["project_skill"], "PASS")
        self.assertEqual(facts["payload_files"], 22)
        self.assertEqual(len(QUALIFICATION.PROTOCOLS), 9)
        self.assertEqual(facts["first_party_version"], "5.1.0")
        self.assertEqual(facts["standalone_snapshot"], "5.0.0")
        self.assertEqual({name: value["version"] for name, value in facts["landscape"].items()}, {
            "org.jresearch.ai/landscape-model-guidance": "1.0.3",
            "org.jresearch.ai/landscape-subagents": "1.0.2"})

    def test_historical_slot_is_immutable_and_never_a_missing_selected_fallback(self):
        historical = QUALIFICATION.ROOT / QUALIFICATION.HISTORICAL_SLOT
        if historical.exists():
            shutil.copytree(historical, self.root / QUALIFICATION.HISTORICAL_SLOT)
            QUALIFICATION.check_project(self.root)
            history = self.root / QUALIFICATION.HISTORICAL_SLOT / "README.md"
            original = history.read_bytes()
            history.write_bytes(original + b"Changed historical evidence\n")
            self.rejects()
            history.write_bytes(original)
        shutil.rmtree(self.root / QUALIFICATION.SLOT)
        self.rejects()

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

    def test_landscape_missing_or_corrupt_public_payload_receipts_and_slot_manifests(self):
        for selection in QUALIFICATION.LANDSCAPE:
            slot = self.root / selection["slot"]
            for name in selection["payload"] | {QUALIFICATION.RECEIPT, QUALIFICATION.MARKER}:
                path = slot / name
                original = path.read_bytes()
                for mutation in (None, b"Changed fixture\n"):
                    with self.subTest(package=selection["name"], name=name, mutation=mutation):
                        path.unlink() if mutation is None else path.write_bytes(mutation)
                        with self.assertRaises((RuntimeError, ValueError, OSError)):
                            QUALIFICATION.check_landscape_package(slot, selection)
                path.write_bytes(original)
            shutil.rmtree(slot)
            self.rejects()
            shutil.copytree(QUALIFICATION.ROOT / selection["slot"], slot)

    def test_landscape_self_consistent_counterfeit_cannot_replace_public_distribution(self):
        lock_path = self.root / "vibe.lock"
        original_lock = lock_path.read_bytes()
        for selection in QUALIFICATION.LANDSCAPE:
            slot = self.root / selection["slot"]
            readme = slot / "README.md"
            readme.write_bytes(readme.read_bytes() + b"\nSelf-consistent substitute.\n")
            hashes = {name: hashlib.sha256((slot / name).read_bytes()).hexdigest()
                      for name in sorted(selection["payload"])}
            receipt_path = slot / QUALIFICATION.RECEIPT
            receipt = json.loads(receipt_path.read_bytes())
            receipt["sha256"] = hashes
            receipt["payload_sha256"] = hashlib.sha256(json.dumps(
                hashes, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            receipt_path.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
            files = {name: (slot / name).read_bytes()
                     for name in selection["payload"] | {QUALIFICATION.RECEIPT}}
            changed_hash = QUALIFICATION.tree_hash(files)
            marker = ['schema = 1', 'source_hash = ' + json.dumps(changed_hash), 'spec_format = "mixed"']
            for name, data in sorted(files.items()):
                marker += ['\n[[file]]', 'path = ' + json.dumps(name),
                           'sha256 = ' + json.dumps(hashlib.sha256(data).hexdigest())]
            (slot / QUALIFICATION.MARKER).write_text("\n".join(marker) + "\n")
            lock_path.write_bytes(original_lock.replace(selection["tree_hash"].encode(), changed_hash.encode()))
            with self.subTest(package=selection["name"]):
                self.rejects()
            shutil.rmtree(slot)
            shutil.copytree(QUALIFICATION.ROOT / selection["slot"], slot)
            lock_path.write_bytes(original_lock)

    def test_landscape_opaque_receipts_do_not_gain_invented_source_provenance(self):
        for selection in QUALIFICATION.LANDSCAPE:
            path = self.root / selection["slot"] / QUALIFICATION.RECEIPT
            original = path.read_bytes()
            for field, value in (("disclosure", "source"), ("source_revision", "0" * 40),
                                 ("source_repository", "https://example.invalid/private"),
                                 ("package", "org.jresearch.ai/other"), ("schema", True)):
                receipt = json.loads(original)
                receipt[field] = value
                path.write_text(json.dumps(receipt))
                with self.subTest(package=selection["name"], field=field):
                    with self.assertRaises(RuntimeError):
                        QUALIFICATION.check_landscape_package(self.root / selection["slot"], selection)
            path.write_bytes(original)

    def test_landscape_requirements_and_lock_are_root_only_exact_anonymous_selections(self):
        for selection in QUALIFICATION.LANDSCAPE:
            for name, changes in (
                    ("vibe.toml", [('version = "=' + selection["version"] + '"',
                                    'version = ">=' + selection["version"] + '"'),
                                   (selection["repository"], "https://example.invalid/other.git"),
                                   (selection["revision"], "0" * 40)]),
                    ("vibe.lock", [(selection["tree_hash"], "sha256:" + "0" * 64),
                                   (selection["revision"], "0" * 40),
                                   ('name = "' + selection["name"] + '"', 'name = "development-governance"'),
                                   ('name = "' + selection["name"] + '"',
                                    'name = "' + selection["name"] + '"\ndependencies = ["org.jresearch.ai/codex-relay@=5.1.0"]')])):
                path = self.root / name
                original = path.read_text()
                for before, after in changes:
                    with self.subTest(package=selection["name"], name=name, field=before):
                        self.assertIn(before, original)
                        path.write_text(original.replace(before, after))
                        self.rejects()
                path.write_text(original)
            # A selected flow cannot be replaced with an arbitrary projected Skill
            # or a transitive admission by a counterfeit lock field.
            path = self.root / "vibe.lock"
            original = path.read_text()
            package = original.split('name = "' + selection["name"] + '"', 1)
            for before, after in (('admitted_by = "root-edge"', 'admitted_by = "dependency"'),
                                  ('files_written = []', 'files_written = [".agents/skills/landscape/SKILL.md"]')):
                path.write_text(package[0] + 'name = "' + selection["name"] + '"' + package[1].replace(before, after, 1))
                self.rejects()
            path.write_text(original)

    def test_landscape_passive_slots_reject_extra_code_executables_and_symlinks(self):
        for selection in QUALIFICATION.LANDSCAPE:
            slot = self.root / selection["slot"]
            extra = slot / "tools/unexpected.py"
            extra.parent.mkdir()
            extra.write_text("print('unexpected runtime capability')\n")
            with self.subTest(package=selection["name"], mutation="extra-capability"):
                self.rejects()
            shutil.rmtree(extra.parent)
            path = slot / "LICENSE"
            path.chmod(0o755)
            with self.subTest(package=selection["name"], mutation="executable"):
                self.rejects()
            path.chmod(0o644)
            data = path.read_bytes()
            other = Path(self.temporary.name) / "license.md"
            other.write_bytes(data)
            path.unlink()
            path.symlink_to(other)
            with self.subTest(package=selection["name"], mutation="symlink"):
                self.rejects()
            path.unlink()
            path.write_bytes(data)

    def test_landscape_adoption_remains_human_owned_conditional_and_profile_stable(self):
        path = self.root / "AGENTS.md"
        original = path.read_text()
        changes = [('Relay explicitly adopts the installed passive', 'Relay merely discovers the installed passive'),
                   ('Task and runtime permit delegation', 'installation permits delegation'),
                   ('Keep the adopted version and admitted profiles stable', 'Reselect profiles during execution'),
                   ('supplies advice for owner selection, not automatic adoption of recommendations',
                    'automatically adopts recommendations'),
                   ('policy/default change requires distinct explicit owner authority',
                    'policy/default change follows installation'),
                   ('default model is\n`gpt-6.1-sol`', 'default model is\n`gpt-6-astra`')]
        for selection in QUALIFICATION.LANDSCAPE:
            changes.append(((selection["slot"] / selection["policy"]).as_posix(),
                            "https://example.invalid/moving-policy.md"))
        for before, after in changes:
            with self.subTest(boundary=before):
                pattern = r"\s+".join(re.escape(word) for word in before.split())
                self.assertRegex(original, pattern)
                path.write_text(re.sub(pattern, lambda _: after, original, count=1))
                self.rejects()
        path.write_text(original)
        binding = self.root / QUALIFICATION.LOCAL_SUBAGENTS
        binding.write_text(binding.read_text() + "\n## When to delegate\nCompeting copied policy.\n")
        self.rejects()

    def test_small_improvements_routes_cannot_use_unselected_or_bundled_protocols(self):
        policy = (QUALIFICATION.SLOT / "vibevm/vibespecs/protocols/small-improvements.md").as_posix()
        for name, before, after in (
                ("AGENTS.md", policy, policy.replace("/7.0.1/", "/7.0.0/")),
                ("AGENTS.md", "Relay explicitly adopts all ten", "Relay merely installs all ten"),
                (QUALIFICATION.LOCAL_GOVERNANCE, "../" + policy,
                 "../guidance/artifacts/standalone/codex-relay/references/shared/small-improvements.md"),
                (QUALIFICATION.BOOT / "90-user.md", "Small Improvements is adopted",
                 "Small Improvements remains unselected")):
            path = self.root / name
            original = path.read_text()
            with self.subTest(route=str(name), before=before):
                self.assertIn(before, original)
                path.write_text(original.replace(before, after, 1))
                self.rejects()
            path.write_text(original)

    def test_small_improvements_preserve_analysis_scope_review_and_pending_item_boundaries(self):
        name = QUALIFICATION.LOCAL_GOVERNANCE
        for before, after in (
                ("label:small-improvement", "in:title Small improvement"),
                ("Analysis-only Task | Skip the SI scan", "Analysis-only Task | Require the SI scan"),
                ("trusted Decisions and admission remain the source of scope",
                 "label and scheduling become the source of scope"),
                ("one independent review assess the combined exact head",
                 "successful tests accept the combined result"),
                ("Keep source Issues open and labelled while work remains pending",
                 "Close source Issues and remove their label upon scheduling"),
                ("queue-empty gate or new mandatory CI gate", "a mandatory queue-empty CI gate")):
            path = self.root / name
            original = path.read_text()
            pattern = r"\s+".join(re.escape(word) for word in before.split())
            with self.subTest(boundary=before):
                self.assertRegex(original, pattern)
                path.write_text(re.sub(pattern, lambda _: after, original, count=1))
                self.rejects()
            path.write_text(original)

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

    def test_landscape_boot_is_conditional_navigation_and_cannot_be_replaced_by_full_policy(self):
        index = self.root / QUALIFICATION.BOOT / "INDEX.md"
        original = index.read_text()
        for selection in QUALIFICATION.LANDSCAPE:
            boot = (selection["slot"] / selection["boot"]).as_posix()
            policy = (selection["slot"] / selection["policy"]).as_posix()
            for changed in (original.replace(boot, policy),
                            original.replace('path = "' + boot + '"\nkind = "static"\n', ""),
                            original.replace('path = "' + boot + '"', 'path = "' + boot + '"\nwhen = "os:windows"')):
                with self.subTest(package=selection["name"], route=changed):
                    index.write_text(changed)
                    self.rejects()
            index.write_text(original)
            path = self.root / boot
            data = path.read_bytes()
            path.write_text("Load the full policy unconditionally; installation grants delegation and reselects profiles.\n")
            with self.subTest(package=selection["name"], mutation="unconditional-boot"):
                self.rejects()
            path.write_bytes(data)

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

    def test_frozen_5_0_0_registry_is_immutable_and_retained(self):
        frozen = self.root / QUALIFICATION.PREVIOUS_SELF_SOURCE
        self.assertEqual(QUALIFICATION.tree_hash(QUALIFICATION.files_in(frozen)),
                         QUALIFICATION.PREVIOUS_SELF_HASH)
        path = frozen / "skill/references/workflow.md"
        original = path.read_bytes()
        path.write_bytes(original + b"\nchanged frozen package\n")
        self.rejects()
        path.write_bytes(original)
        QUALIFICATION.check_project(self.root)
        shutil.rmtree(frozen)
        self.rejects()

    def test_standalone_snapshot_cannot_drift_or_become_an_active_native_route(self):
        snapshot = Path("guidance/artifacts/standalone/codex-relay/references/shared")
        path = self.root / snapshot / "vibevm/vibespecs/protocols/task-handoff.md"
        original = path.read_bytes()
        path.write_bytes(original + b"\nChanged standalone snapshot\n")
        self.rejects()
        path.write_bytes(original)
        QUALIFICATION.check_project(self.root)
        path.unlink()
        self.rejects()
        path.write_bytes(original)
        index = self.root / QUALIFICATION.BOOT / "INDEX.md"
        index.write_text(index.read_text().replace(QUALIFICATION.SLOT.as_posix(),
                                                   snapshot.as_posix()))
        self.rejects()

    def test_unselected_registry_version_is_rejected(self):
        path = self.root / "vibevm/vibepacks/org.jresearch.ai/codex-relay/v99.0.0/vibe.toml"
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
