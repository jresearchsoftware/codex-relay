#!/usr/bin/env python3
"""Opt-in qualification of Relay's committed native flows; never downloads tools."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import posixpath
import re
import stat
import subprocess
import tempfile
import tomllib
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
BOOT = Path("vibevm/vibespecs/boot")
AGENTS = ("AGENTS.md", "CLAUDE.md", "GEMINI.md")
SOURCES = ("00-core.md", "90-user.md")
COORDINATE = "org.jresearch.ai/development-governance"
VERSION = "5.0.0"
SLOT = Path("vibevm/vibedeps/org.jresearch.ai.development-governance") / VERSION
SELF_COORDINATE = "org.jresearch.ai/codex-relay"
SELF_VERSION = "4.1.0"
SELF_SOURCE = Path("vibevm/vibepacks") / SELF_COORDINATE / ("v" + SELF_VERSION)
HISTORICAL_SELF_SOURCE = Path("vibevm/vibepacks") / SELF_COORDINATE / "v1.0.0"
HISTORICAL_SELF_HASH = "sha256:7a9f89990b3f4d6ce03990e514f18e010b8d844e98d95fa6ffec0bedc546b454"
SELF_SLOT = Path("vibevm/vibedeps/org.jresearch.ai.codex-relay") / SELF_VERSION
SELF_BOOT = "vibevm/vibespecs/boot/codex-relay.md"
PROJECTION = Path(".agents/skills/codex-relay")
SKILL_RECEIPT = Path(".agents/skills/.codex-relay.vibe-skill-receipt.toml")
PACKAGE_BOOT = "vibevm/vibespecs/boot/development-governance.md"
PROTOCOLS = tuple("vibevm/vibespecs/protocols/" + name + ".md" for name in
                  ("package-versioning", "proportional-controls", "requirement-authority",
                   "task-handoff", "self-adoption", "github-repository-governance",
                   "independent-review", "contract-and-decision-maintenance", "context-loading"))
GUIDES = tuple("vibevm/vibespecs/guides/" + name + ".md" for name in
               ("engineering-methods", "onboarding", "onboarding-examples"))
PAYLOAD = {"LICENSE", "README.md", "CHANGELOG.md", "vibe.toml", PACKAGE_BOOT,
           "tools/chatgpt/README.md", "tools/chatgpt/base.md", "tools/chatgpt/project.py",
           *PROTOCOLS, *GUIDES}
# Accepted producer exports omit only their generated local client routes.
SOURCE_ONLY = {"AGENTS.md", "CLAUDE.md", "GEMINI.md", "vibevm/vibespecs/boot/INDEX.md",
               "vibevm/vibespecs/boot/.vibe-boot-artifacts.lock"}
RECEIPT = "DISTRIBUTION.json"
MARKER = ".vibe-slot.toml"
DISTRIBUTION_REPOSITORY = "https://github.com/jrs-vibevm/org.jresearch.ai.development-governance.git"
DISTRIBUTION_REVISION = "30a23f467c30c41fec918204cbbf2ecfffd7bef5"
SOURCE_REPOSITORY = "https://github.com/jresearchsoftware/shared-governance"
SOURCE_REVISION = "d0b3d67ef94a5537ebd4a2bbf4a38e3a6629c0c9"
PAYLOAD_HASH = "f4ad03a0137bd0d4c8cab58fa7d42ccbe0bb3aba2315cb9c96f5f93c7ea86275"
RECEIPT_HASH = "45f43dcdb48ff9dfcfc114284cd8c25bdeda3f870883633f08057504edf98bc9"
TREE_HASH = "sha256:e686314f26c82f32f55958a242481d792e9fcd0d755a6eebf933431f3e0875d9"
# Admitted baseline 9c01c5d; native block also reproduced by the pinned generator.
CORE_HASH = "2251ff094522c58cfbfd1fc6833286c0eb02bc52eb35e3057e49b5709d6a2157"
NATIVE_BLOCK_HASH = "b6586c59ad7e755a7474c7917e2eeee1f5c09a9f5d1874775fd53675e5b18c1f"
BLOCK = re.compile(rb"^<vibevm>\n.*?^</vibevm>\n", re.M | re.S)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def managed(data):
    require(len(re.findall(rb"^</?vibevm>$", data, re.M)) == 2,
            "Expected exactly one native managed block")
    matches = list(BLOCK.finditer(data))
    require(len(matches) == 1, "Missing or malformed native managed block")
    match = matches[0]
    return match.group(), data[:match.start()] + data[match.end():]


def read_file(root, relative):
    relative = Path(relative)
    require(not relative.is_absolute() and ".." not in relative.parts, "Unsafe relative path")
    require(root.is_dir() and not root.is_symlink(), "Expected ordinary project directory")
    path = root
    for part in relative.parts:
        path /= part
        require(not path.is_symlink(), "Symlink in route: " + relative.as_posix())
    require(path.is_file(), "Missing or non-ordinary route file: " + relative.as_posix())
    return path.read_bytes()


def files_in(directory, ignore_git=False):
    require(directory.is_dir() and not directory.is_symlink(), "Expected ordinary payload directory")
    result = {}
    for current, directories, files in os.walk(directory, followlinks=False):
        current = Path(current)
        if current == directory and ignore_git:
            directories[:] = [name for name in directories if name != ".git"]
            files = [name for name in files if name != ".git"]
        for name in [*directories, *files]:
            path = current / name
            relative = path.relative_to(directory).as_posix()
            require(not path.is_symlink(), "Symlink in passive payload: " + relative)
            require(path.is_dir() or path.is_file(), "Non-ordinary payload entry: " + relative)
            if path.is_file():
                require(not path.stat().st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH),
                        "Executable file in passive payload: " + relative)
                result[relative] = path.read_bytes()
    return result


def tree_hash(files):
    """VibeVM 1.0.7's Linux legacy tree recipe, including the distribution receipt."""
    digest = hashlib.sha256()
    for name in sorted(files, key=lambda name: Path(name).parts):
        digest.update(name.encode() + b"\0" + files[name] + b"\0")
    return "sha256:" + digest.hexdigest()


def check_package(directory):
    files = files_in(directory)
    require(set(files) == PAYLOAD | {RECEIPT, MARKER}, "Unexpected or missing passive slot files")
    hashes = {name: hashlib.sha256(files[name]).hexdigest() for name in sorted(PAYLOAD)}
    payload_hash = hashlib.sha256(json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    require(payload_hash == PAYLOAD_HASH, "Payload differs from the accepted whole-package identity")
    receipt = json.loads(files[RECEIPT])
    require(receipt == {"package": COORDINATE, "payload_sha256": PAYLOAD_HASH, "schema": 1,
                        "sha256": hashes, "source_path": "packages/development-governance",
                        "source_repository": SOURCE_REPOSITORY, "source_revision": SOURCE_REVISION,
                        "version": VERSION}, "Receipt differs from accepted source/path/hash identity")
    require(hashlib.sha256(files[RECEIPT]).hexdigest() == RECEIPT_HASH, "Receipt bytes differ")
    materialized = {name: data for name, data in files.items() if name != MARKER}
    require(tree_hash(materialized) == TREE_HASH, "Materialized tree differs from the locked identity")
    marker = tomllib.loads(files[MARKER].decode())
    require(type(marker.get("schema")) is int
            and marker == {"schema": 1, "source_hash": TREE_HASH, "spec_format": "mixed",
                           "file": [{"path": name, "sha256": hashlib.sha256(data).hexdigest()}
                                    for name, data in sorted(materialized.items())]},
            "Slot metadata differs from the complete materialized payload")
    manifest = tomllib.loads(files["vibe.toml"].decode())
    require(manifest == {"package": {"group": "org.jresearch.ai", "name": "development-governance",
                                     "version": VERSION, "kind": "flow", "format": "simple", "epoch": 1,
                                     "publish": False, "frozen": True,
                                     "description": "Passive cross-project AI-development governance flow protocol.",
                                     "license": "MIT"},
                         "boot_snippet": {"source": PACKAGE_BOOT, "category": "flow", "link": "dynamic"}},
            "Passive package manifest changed or gained capabilities/dependencies")
    # Ordinary Markdown navigation stays inside the verified passive slot.
    for name, data in materialized.items():
        if not name.endswith(".md"):
            continue
        for target in re.findall(r"\[[^\]\n]*\]\(([^)\s]+)\)", data.decode()):
            url = urlsplit(target.strip("<>"))
            if url.scheme or url.netloc:
                continue
            resolved = (posixpath.normpath(posixpath.join(posixpath.dirname(name), unquote(url.path)))
                        if url.path else name)
            require(resolved in materialized, "Missing or escaping passive reference: " + name)
    pointer = files[PACKAGE_BOOT].decode()
    require(all("../protocols/" + Path(name).name in pointer for name in PROTOCOLS)
            and "Unrelated tasks" in pointer and "explicitly adopted" in pointer,
            "Conditional full-procedure navigation is missing")
    return files


def check_first_party_registry(root, expected):
    historical = files_in(root / HISTORICAL_SELF_SOURCE)
    require(tree_hash(historical) == HISTORICAL_SELF_HASH,
            "Historical accepted first-party registry changed")
    previous = Path("vibevm/vibepacks/org.jresearch.ai/codex-relay/v2.0.0")
    previous_files = files_in(root / previous)
    require(tree_hash(previous_files) == "sha256:24c706e7ba74d830cc435d8381b77b03cce6d306a4bd28d7ab37982f6b5c2ff0",
            "Frozen accepted 2.0.0 registry changed")
    released = Path("vibevm/vibepacks/org.jresearch.ai/codex-relay/v2.0.1")
    released_files = files_in(root / released)
    require(tree_hash(released_files) == "sha256:9a39f5460c75947bc7c814786d170c2d3180380843c6bd2839e19e20102e53bc",
            "Frozen accepted 2.0.1 registry changed")
    prior = Path("vibevm/vibepacks/org.jresearch.ai/codex-relay/v3.0.0")
    prior_files = files_in(root / prior)
    require(tree_hash(prior_files) == "sha256:297afba0242ec3ae2cd77448ac6bec4b112b72d9b3f8d229e9029dda60cbaaa6",
            "Frozen accepted 3.0.0 registry changed")
    manual = Path("vibevm/vibepacks/org.jresearch.ai/codex-relay/v3.1.0")
    manual_files = files_in(root / manual)
    require(tree_hash(manual_files) == "sha256:5bd96c600aaecec732981b8c45c82854493d34fa2597a01fdabe033735aac772",
            "Frozen accepted 3.1.0 registry changed")
    frozen = Path("vibevm/vibepacks/org.jresearch.ai/codex-relay/v4.0.0")
    frozen_files = files_in(root / frozen)
    require(tree_hash(frozen_files) == "sha256:3e892b02e6f6d3b0b6a1a64840af96b1da91f2af136297cac1bf37b5f326baeb",
            "Frozen accepted 4.0.0 registry changed")
    require(files_in(root / "vibevm/vibepacks") == {
        (package.relative_to("vibevm/vibepacks") / name).as_posix(): data
        for package, files in ((HISTORICAL_SELF_SOURCE, historical), (previous, previous_files), (released, released_files), (prior, prior_files), (manual, manual_files), (frozen, frozen_files), (SELF_SOURCE, expected))
        for name, data in files.items()},
        "Unexpected first-party registry package or file")


def check_standalone_snapshot(root):
    metadata = json.loads(read_file(root, "guidance/source.json"))
    require(metadata["shared_version"] == VERSION
            and metadata["shared_source_revision"] == SOURCE_REVISION
            and metadata["shared_distribution_revision"] == DISTRIBUTION_REVISION
            and metadata["shared_distribution_tree_hash"] == TREE_HASH,
            "Standalone selection differs from the accepted immutable Shared snapshot")
    files = check_package(root / SLOT)
    files.pop(MARKER)
    standalone = files_in(root / "guidance/artifacts/standalone/codex-relay/references/shared")
    require(files == standalone, "Standalone payload differs from the accepted immutable Shared snapshot")


def check_first_party(root):
    metadata = json.loads(read_file(root, "guidance/source.json"))
    require(metadata["name"] == "codex-relay" and metadata["version"] == SELF_VERSION,
            "First-party source must retain owner-selected " + SELF_VERSION + " identity")
    expected = files_in(root / "guidance/artifacts/vpm")
    require(expected and files_in(root / SELF_SOURCE) == expected,
            "First-party registry differs from generated package export")
    check_first_party_registry(root, expected)
    require(tomllib.loads(expected["vibe.toml"].decode())["requires"]["packages"][COORDINATE]
            == metadata["shared_requirement"], "Native manifest must declare the semantic lower bound")
    installed = files_in(root / SELF_SLOT)
    require(MARKER in installed, "Missing first-party slot metadata")
    marker = tomllib.loads(installed.pop(MARKER).decode())
    source_hash = tree_hash(expected)
    require(installed == expected, "First-party slot differs from generated package export")
    require(type(marker.get("schema")) is int and marker == {
        "schema": 1, "source_hash": source_hash, "spec_format": "mixed",
        "file": [{"path": name, "sha256": hashlib.sha256(data).hexdigest()}
                 for name, data in sorted(expected.items())]}, "First-party slot metadata differs")
    skill = {name.removeprefix("skill/"): data for name, data in expected.items()
             if name.startswith("skill/")}
    standalone = files_in(root / "guidance/artifacts/standalone/codex-relay")
    require(not any(name.startswith("references/shared/") for name in skill),
            "Native Skill must route to consumer-selected protocols, not bundle them")
    require(all(data == standalone[name] for name, data in skill.items()
                if name not in {"PROVENANCE.json", "references/shared-protocols.md"}),
            "Delivery forms differ in Relay product contract bytes")
    require("consumer-vibe-lock" == json.loads(skill["PROVENANCE.json"])["protocol_source"],
            "Native provenance must identify consumer lock routing")
    require(files_in(root / PROJECTION) == skill, "Codex project Skill differs from native package")
    receipt = tomllib.loads(read_file(root, SKILL_RECEIPT).decode())
    require(type(receipt.get("schema")) is int and receipt == {
        "schema": 1, "skill": "codex-relay",
        "file": [{"path": name, "sha256": hashlib.sha256(data).hexdigest()}
                 for name, data in sorted(skill.items())]}, "Native Codex Skill receipt differs")
    return expected, source_hash


def check_project(root):
    manifest = tomllib.loads(read_file(root, "vibe.toml").decode())
    require(manifest == {"project": {"name": "codex-relay", "version": "0.0.0", "spec_format": "mixed"},
                         "requires": {"packages": {COORDINATE: {"version": "=" + VERSION,
                                     "git": DISTRIBUTION_REPOSITORY, "rev": DISTRIBUTION_REVISION,
                                     "auth": "none"}, "flow:" + SELF_COORDINATE: {
                                     "version": "=" + SELF_VERSION, "link": "dynamic"}}},
                         "registry": [{"name": "producer", "url": "vibevm/vibepacks", "auth": "none"}]},
            "Consumer must retain exact Shared Git and native first-party requirements")
    files = check_package(root / SLOT)
    first_party, source_hash = check_first_party(root)
    check_standalone_snapshot(root)
    lock = tomllib.loads(read_file(root, "vibe.lock").decode())
    packages = lock.get("package", [])
    require(len(packages) == 2, "Expected exactly Shared and first-party native packages")
    require(len({(entry.get("group"), entry.get("name")) for entry in packages}) == 2,
            "Duplicate native package identity")
    shared = next((entry for entry in packages if entry.get("name") == "development-governance"), None)
    first = next((entry for entry in packages if entry.get("name") == "codex-relay"), None)
    require(set(lock) == {"meta", "package"} and set(lock["meta"]) == {
        "generated_by", "generated_at", "schema_version", "root_dependencies"}
        and lock["meta"]["generated_by"] == "vibe 1.0.7"
        and type(lock["meta"]["schema_version"]) is int and lock["meta"]["schema_version"] == 7
        and isinstance(lock["meta"]["generated_at"], str)
        and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", lock["meta"]["generated_at"])
        and lock["meta"]["root_dependencies"] == ["flow:" + SELF_COORDINATE + "@=" + SELF_VERSION, COORDINATE]
        and shared == {"kind": "flow", "name": "development-governance", "group": "org.jresearch.ai",
                                 "version": VERSION, "source_url": DISTRIBUTION_REPOSITORY,
                                 "source_ref": DISTRIBUTION_REVISION, "content_hash": TREE_HASH,
                                 "files_written": [], "admitted_by": "root-edge", "source_kind": "git"},
        "Schema-7 lock differs from the admitted graph/source/content identity")
    require(first is not None, "Missing first-party native lock entry")
    # Native absolute location metadata can come from another supported checkout.
    # Exact export/registry/slot equality above supplies portable content identity.
    source_url = first.get("source_url", "")
    require(source_url.startswith("file://") and
            unquote(source_url).endswith("/" + SELF_SOURCE.as_posix()),
            "First-party source is not a generated in-tree registry location")
    require(first == {"kind": "flow", "group": "org.jresearch.ai", "name": "codex-relay",
                      "version": SELF_VERSION, "source_url": source_url, "content_hash": source_hash,
                      "files_written": [], "dependencies": [COORDINATE + "@=" + VERSION],
                      "admitted_by": "root-edge", "source_kind": "local"},
            "First-party lock differs from native content/dependency identity")
    index = tomllib.loads(read_file(root, BOOT / "INDEX.md").decode())
    paths = [(BOOT / SOURCES[0]).as_posix(), (SLOT / PACKAGE_BOOT).as_posix(),
             (SELF_SLOT / SELF_BOOT).as_posix(), (BOOT / SOURCES[1]).as_posix()]
    # Native v1.0.7 emits static here despite boot_snippet.link = "dynamic".
    require(type(index.get("schema")) is int
            and index == {"schema": 1, "entry": [{"path": name, "kind": "static"} for name in paths]},
            "Generated INDEX differs from the actual native route")
    require({p.name for p in (root / BOOT).iterdir()} <= {
        "INDEX.md", *SOURCES, ".vibe-boot-artifacts.lock"}, "Unexpected boot content")
    require(hashlib.sha256(read_file(root, BOOT / SOURCES[0])).hexdigest() == CORE_HASH,
            "Authored core differs from the admitted routing boundary")
    blocks = [managed(read_file(root, name))[0] for name in AGENTS]
    require(len(set(blocks)) == 1 and hashlib.sha256(blocks[0]).hexdigest() == NATIVE_BLOCK_HASH,
            "Native redirects differ from the accepted generated block")
    require(set(files_in(root / "vibevm/vibedeps")) == {
        (SLOT.relative_to("vibevm/vibedeps") / name).as_posix() for name in files} | {
        (SELF_SLOT.relative_to("vibevm/vibedeps") / name).as_posix() for name in {*first_party, MARKER}},
            "Unexpected materialized dependency graph")
    for relative in ("vibevm/vibespecs/WAL.md", "vibevm/vibespecs/WAL.xml",
                     ".agents/skills/proportional-controls", ".agents/skills/.proportional-controls.vibe-skill-receipt.toml"):
        require(not (root / relative).exists() and not (root / relative).is_symlink(),
                "Unexpected WAL or projected governance Skill: " + relative)
    return {"route": paths, "boot_bytes": sum(len(read_file(root, path)) for path in paths),
            "payload_files": len(PAYLOAD), "tree_hash": TREE_HASH, "payload_sha256": PAYLOAD_HASH,
            "source_revision": SOURCE_REVISION, "distribution_revision": DISTRIBUTION_REVISION,
            "first_party_version": SELF_VERSION, "first_party_tree_hash": source_hash,
            "project_skill": "PASS", "standalone_snapshot": VERSION}


def compare_inputs(root, source, distribution):
    files = check_package(root / SLOT)
    if source:
        source_files = {name: data for name, data in files_in(source, ignore_git=True).items()
                        if name not in SOURCE_ONLY}
        require(source_files == {name: files[name] for name in PAYLOAD},
                "Supplied accepted-source package differs from the committed whole payload")
    if distribution:
        require(files_in(distribution, ignore_git=True) == {name: data for name, data in files.items() if name != MARKER},
                "Supplied public distribution differs from the committed whole payload/receipt")


def copy_project(source, destination):
    """Copy only ordinary ready files, without credentials or lifecycle state."""
    files = {name: read_file(source, name) for name in (
        "vibe.toml", "vibe.lock", "guidance/source.json", *AGENTS, SKILL_RECEIPT)}
    for relative in ("guidance/artifacts", "vibevm/vibedeps", "vibevm/vibepacks",
                     "vibevm/vibespecs/boot", PROJECTION):
        files.update({str(Path(relative) / name): data
                      for name, data in files_in(source / relative).items()
                      if name != ".vibe-boot-artifacts.lock"})
    for name, data in files.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def probe(vibe, pin, project_root=ROOT):
    require(hashlib.sha256(vibe.read_bytes()).hexdigest() ==
            pin["linux_x86_64_musl_binary"]["sha256"], "VibeVM binary differs from the pinned release")
    with tempfile.TemporaryDirectory(prefix="relay-vibevm-") as temporary:
        root = Path(temporary)
        env = {key: value for key, value in os.environ.items() if key in {"PATH", "LANG", "LC_ALL"}}
        for key, relative in {"HOME": "home", "XDG_CONFIG_HOME": "config", "XDG_CACHE_HOME": "cache",
                              "VIBE_SETTINGS": "settings"}.items():
            env[key] = str(root / relative)
            (root / relative).mkdir()
        env["VIBEVM_USER_CONFIG"] = str(root / "settings/config.toml")
        reports = {}

        def run(project, label, *arguments, collision=False, incomplete=False):
            result = subprocess.run([str(vibe), "--offline", "--json", *arguments], cwd=project, env=env,
                                    text=True, capture_output=True, timeout=120)
            if collision or incomplete:
                evidence = "malformed <vibevm> block" if collision else "slot missing"
                require(result.returncode != 0 and evidence in result.stdout + result.stderr,
                        label + " did not refuse the expected malformed/incomplete state")
                reports[label] = {"exit": result.returncode, "refused": evidence}
                return
            require(result.returncode == 0, label + " failed:\n" + result.stdout + result.stderr)
            remaining, documents = result.stdout.strip(), []
            while remaining:
                document, end = json.JSONDecoder().raw_decode(remaining)
                documents.append(document)
                remaining = remaining[end:].lstrip()
            require(documents and not any(d.get("ok") is False for d in documents), label + " failed")
            for document in documents:
                if document.get("command") == "check":
                    require(document["summary"]["error"] == 0 and document["summary"]["warning"] == 0
                            and document["findings"] == [],
                            label + " has unexpected findings: " + result.stdout)
            require(not result.stderr.strip(), label + " emitted diagnostics: " + result.stderr)
            reports[label] = documents

        version = subprocess.check_output([str(vibe), "--version"], cwd=root, env=env, text=True).strip()
        require(version == "vibe " + pin["version"], "Unexpected tool version")
        project = root / "project"
        copy_project(project_root, project)
        facts = check_project(project)
        route_paths = ["vibe.toml", "vibe.lock", *AGENTS, *(str(BOOT / name) for name in ("INDEX.md", *SOURCES))]
        route_paths += [(SLOT / name).as_posix() for name in PAYLOAD | {RECEIPT, MARKER}]
        route_paths += [(SELF_SLOT / name).as_posix() for name in files_in(project / SELF_SLOT)]
        route_paths += [(PROJECTION / name).as_posix() for name in files_in(project / PROJECTION)]
        route_paths += [SKILL_RECEIPT.as_posix()]
        original = {name: read_file(project, name) for name in route_paths}

        def unchanged(expected):
            for name, data in expected.items():
                require(read_file(project, name) == data, "Authored/generated bytes drifted: " + name)

        def rejected(label):
            try:
                check_project(project)
            except (RuntimeError, ValueError, OSError):
                reports[label] = {"local_verifier": "rejected"}
            else:
                raise RuntimeError(label + " was accepted by the local verifier")

        run(project, "validate", "validate", "--path", ".", "--no-default-registry")
        run(project, "check", "check", "--path", ".")
        unchanged(original)
        for count in range(2):
            run(project, "reinstall-" + str(count + 1), "reinstall", ".", "--assume-yes")
            unchanged(original)
            check_project(project)
        run(project, "repeat-init", "init", ".", "--type", "project", "--name", "codex-relay",
            "--version", "0.0.0", "--no-registry", "--author", "Synthetic fixture")
        unchanged(original)

        for name in AGENTS:
            (project / name).write_bytes(b"Synthetic human prefix\n" + original[name] + b"Human suffix\n")
        overlays = {name: read_file(project, name) for name in AGENTS}
        run(project, "overlay-regeneration", "reinstall", ".", "--assume-yes")
        unchanged({**original, **overlays})
        for name in AGENTS:
            (project / name).write_bytes(original[name])

        index = project / BOOT / "INDEX.md"
        index.unlink()
        rejected("missing-index")
        run(project, "missing-index-upstream-check", "check", "--path", ".")
        (project / "GEMINI.md").unlink()
        run(project, "repair-generated-files", "reinstall", ".", "--assume-yes")
        unchanged(original)
        check_project(project)

        # Counterexamples bind local verification to admitted bytes, not upstream check.
        for label, name, data in [
                ("corrupt-payload", (SLOT / PROTOCOLS[1]).as_posix(), b"Altered passive protocol\n"),
                ("missing-payload", (SLOT / PROTOCOLS[1]).as_posix(), None),
                ("corrupt-receipt", (SLOT / RECEIPT).as_posix(), b"{}\n"),
                ("missing-receipt", (SLOT / RECEIPT).as_posix(), None),
                ("corrupt-slot-metadata", (SLOT / MARKER).as_posix(), b"schema = 1\n"),
                ("corrupt-lock", "vibe.lock", original["vibe.lock"].replace(TREE_HASH.encode(), b"sha256:" + b"0" * 64)),
                ("missing-lock", "vibe.lock", None)]:
            path = project / name
            path.unlink() if data is None else path.write_bytes(data)
            rejected(label)
            if label in {"missing-payload", "corrupt-lock"}:
                run(project, label + "-upstream-check", "check", "--path", ".")
            path.write_bytes(original[name])
        displaced = root / "displaced-slot"
        (project / SLOT).rename(displaced)
        rejected("missing-slot")
        run(project, "missing-slot-offline-reinstall", "reinstall", ".", "--assume-yes", incomplete=True)
        displaced.rename(project / SLOT)

        for label, data in [("duplicate-block", original["AGENTS.md"] + managed(original["AGENTS.md"])[0]),
                            ("unclosed-block", b"Human-owned text\n<vibevm>\n")]:
            (project / "AGENTS.md").write_bytes(data)
            rejected(label)
            before = {name: read_file(project, name) for name in original}
            run(project, label, "reinstall", ".", "--assume-yes", collision=True)
            unchanged(before)
        (project / "AGENTS.md").write_bytes(original["AGENTS.md"])
        unchanged(original)
        check_project(project)
        print(json.dumps({"tool_probe": "PASS", "version": version, **facts,
                          "offline_file_reads": "PASS", "exact_regeneration": "PASS",
                          "overlays_and_collisions": "PASS",
                          "upstream_check_limitations": "accepts missing INDEX/payload and divergent lock hash",
                          "upstream_acquisition_limitations": "offline reinstall needs an existing slot; upstream install/check is not accepted-source verification",
                          "model_behavior": "UNVERIFIED: no Codex/provider execution", "reports": reports}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=ROOT,
                        help="complete ready checkout/isolated fixture to verify (default: this checkout)")
    parser.add_argument("--vibe", type=Path, help="already acquired, hash-pinned Linux x86_64 musl v1.0.7 binary")
    parser.add_argument("--source-dir", type=Path, help="optional accepted source package directory for whole-payload byte comparison")
    parser.add_argument("--distribution-dir", type=Path, help="optional acquired public distribution directory for whole-payload/receipt byte comparison")
    args = parser.parse_args()
    project_root = args.project_root.resolve()
    facts = check_project(project_root)
    if args.source_dir or args.distribution_dir:
        compare_inputs(project_root, args.source_dir, args.distribution_dir)
    print(json.dumps({"passive_package_route": "PASS", **facts,
                      "source_byte_comparison": "PASS" if args.source_dir else "not requested",
                      "distribution_byte_comparison": "PASS" if args.distribution_dir else "not requested",
                      "tool_probe": "pending" if args.vibe else "not requested", "model_behavior": "UNVERIFIED"}))
    if args.vibe:
        pin = json.loads((ROOT / "toolchain/vibevm.json").read_text())
        probe(args.vibe.resolve(), pin, project_root)


if __name__ == "__main__":
    main()
