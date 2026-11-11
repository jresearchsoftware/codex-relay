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
VERSION = "7.0.1"
SLOT = Path("vibevm/vibedeps/org.jresearch.ai.development-governance") / VERSION
SELF_COORDINATE = "org.jresearch.ai/codex-relay"
SELF_VERSION = "5.1.0"
SELF_SOURCE = Path("vibevm/vibepacks") / SELF_COORDINATE / ("v" + SELF_VERSION)
PREVIOUS_SELF_SOURCE = Path("vibevm/vibepacks/org.jresearch.ai/codex-relay/v5.0.0")
PREVIOUS_SELF_HASH = "sha256:e86a715fceac2364f154085c13a835541a9ba15f8bee8c35d34677abd212b55d"
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
           *PROTOCOLS, *GUIDES, "vibevm/vibespecs/protocols/small-improvements.md",
           "vibevm/vibespecs/guides/small-improvements.md"}
# Accepted producer exports omit only their generated local client routes.
SOURCE_ONLY = {"AGENTS.md", "CLAUDE.md", "GEMINI.md", "vibevm/vibespecs/boot/INDEX.md",
               "vibevm/vibespecs/boot/.vibe-boot-artifacts.lock"}
RECEIPT = "DISTRIBUTION.json"
MARKER = ".vibe-slot.toml"
DISTRIBUTION_REPOSITORY = "https://github.com/jrs-vibevm/org.jresearch.ai.development-governance.git"
DISTRIBUTION_REVISION = "f9fcfa03dec8fb9e00398fc7e0cc7de92da687b9"
SOURCE_REPOSITORY = "https://github.com/jresearchsoftware/shared-governance"
SOURCE_REVISION = "1110f10b996c2f81fa842e6339ab6d7c13111cd7"
PAYLOAD_HASH = "af758c7c375f54741e46b8c0bfa1ea5311d315839aeae385b3d0ffd468473c36"
RECEIPT_HASH = "f4a568278ba45cc6bd64280f4fae74a337de3d3c9384e0e72bd5912e74487c61"
TREE_HASH = "sha256:9dc1463bb4c130282e5ac332e0d7f4c18502d950b85e2015d04d5b9634589c3f"
# Admitted baseline 9c01c5d; native block also reproduced by the pinned generator.
CORE_HASH = "2251ff094522c58cfbfd1fc6833286c0eb02bc52eb35e3057e49b5709d6a2157"
NATIVE_BLOCK_HASH = "b6586c59ad7e755a7474c7917e2eeee1f5c09a9f5d1874775fd53675e5b18c1f"
BLOCK = re.compile(rb"^<vibevm>\n.*?^</vibevm>\n", re.M | re.S)
LOCAL_SUBAGENTS = Path("docs/codex/SUBAGENTS.md")
LOCAL_GOVERNANCE = Path("docs/relay-guidance-ownership.md")
# Root-consumer selections only: neither flow is added to the frozen Relay
# package, Skill projection or standalone delivery. Opaque public receipts do
# not assert a private producer source revision.
LANDSCAPE = (
    {"name": "landscape-model-guidance", "version": "1.0.3",
     "revision": "48432f00802f5aad106f3e1a9264e17c1edc354c",
     "payload_hash": "cd55c682497ee9724063c04d776e8ed9243129aa29de5c12b5d607980c8918ca",
     "receipt_hash": "2112fccf42acbf4b4ca6a228369e5779f961f27887f02941106e23e8ffff6d31",
     "tree_hash": "sha256:a64d829c0e50ac228d9bc39608db7e081e87c13d69e9cfeafc46720ec022f7f6",
     "description": "Passive, frozen general model and effort recommendations from accepted Landscape evidence.",
     "policy": "vibevm/vibespecs/protocols/model-selection.md",
     "payload": {"LICENSE", "README.md", "vibe.toml",
                 "vibevm/vibespecs/boot/landscape-model-guidance.md",
                 "vibevm/vibespecs/protocols/model-selection.md",
                 "vibevm/vibespecs/reference/evidence.md"}},
    {"name": "landscape-subagents", "version": "1.0.2",
     "revision": "042e92884278d748502157945301dbc3f3c8318c",
     "payload_hash": "01fd1e83a3e8b0458a872393a1fe70218e20b0ff4650a43721ec1bf74132ffb2",
     "receipt_hash": "8df45f25a3a134ae95c628ff5766b19b4ab4f549a689cce655e5ab1c9f994b31",
     "tree_hash": "sha256:58a76e39b4861f8205726930d89d4f16c320704cb21b146ce4c47c3d2b959e56",
     "description": "Passive, explicitly adopted subagent workflow and child-profile guidance.",
     "policy": "vibevm/vibespecs/protocols/subagents.md",
     "payload": {".gitattributes", "LICENSE", "QUALIFICATION.md", "README.md", "vibe.toml",
                 "tests/check_package.py", "tests/qualify_local.py",
                 "vibevm/vibespecs/boot/landscape-subagents.md",
                 "vibevm/vibespecs/protocols/subagents.md",
                 "vibevm/vibespecs/guides/adoption.md",
                 "vibevm/vibespecs/guides/runtime-evidence.md"}},
)
for _selection in LANDSCAPE:
    _selection["coordinate"] = "org.jresearch.ai/" + _selection["name"]
    _selection["repository"] = "https://github.com/jrs-vibevm/org.jresearch.ai." + _selection["name"] + ".git"
    _selection["slot"] = Path("vibevm/vibedeps/org.jresearch.ai." + _selection["name"]) / _selection["version"]
    _selection["boot"] = "vibevm/vibespecs/boot/" + _selection["name"] + ".md"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def check_repeat_lock(before, after):
    """Native install refreshes generated_at, not the resolved content identity."""
    previous, current = (tomllib.loads(data.decode()) for data in (before, after))
    for lock in (previous, current):
        timestamp = lock.get("meta", {}).get("generated_at")
        require(isinstance(timestamp, str) and
                re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", timestamp),
                "Repeat install has invalid generation timestamp")
        del lock["meta"]["generated_at"]
    require(previous == current, "Repeat install changed the resolved lock identity")


def check_relocation_lock(before, after, source, label):
    """Allow only native checkout metadata changes for the exact first-party package."""
    previous, current = (tomllib.loads(data.decode()) for data in (before, after))
    entries = []
    for lock in (previous, current):
        timestamp = lock.get("meta", {}).get("generated_at")
        require(isinstance(timestamp, str) and
                re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", timestamp),
                label + " has invalid generation timestamp")
        first = [entry for entry in lock.get("package", [])
                 if entry.get("group") == "org.jresearch.ai" and entry.get("name") == "codex-relay"]
        require(len(first) == 1, label + " has ambiguous first-party package identity")
        first = first[0]
        require(first.get("source_kind") in {"local", "registry"},
                label + " has unsupported first-party source kind")
        source_url = first.get("source_url", "")
        location = urlsplit(source_url) if isinstance(source_url, str) else None
        require(location is not None and location.scheme == "file" and not location.netloc
                and not location.query and not location.fragment and location.path.startswith("/")
                and unquote(location.path).endswith("/" + SELF_SOURCE.as_posix()),
                label + " has invalid first-party registry location")
        entries.append(first)
    require(entries[1]["source_url"] == source.as_uri(),
            label + " did not bind the relocated first-party source")
    previous["meta"]["generated_at"] = current["meta"]["generated_at"]
    entries[0]["source_url"] = entries[1]["source_url"]
    # Native 1.0.11 resolves an existing LocalRegistry entry as local, while the
    # committed/native-update lock may call that same in-tree source registry.
    # Version, hashes, source refs, graph and every other package field stay exact.
    entries[0]["source_kind"] = entries[1]["source_kind"]
    require(current == previous, label + " changed more than native checkout metadata/timestamp")


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
    """VibeVM's unchanged Linux legacy tree recipe, including the distribution receipt."""
    digest = hashlib.sha256()
    for name in sorted(files, key=lambda name: Path(name).parts):
        digest.update(name.encode() + b"\0" + files[name] + b"\0")
    return "sha256:" + digest.hexdigest()


def check_landscape_package(directory, selection):
    """Verify each selected public flow as immutable passive package bytes."""
    label = selection["name"]
    files = files_in(directory)
    payload = selection["payload"]
    require(set(files) == payload | {RECEIPT, MARKER}, label + " has unexpected or missing passive files")
    hashes = {name: hashlib.sha256(files[name]).hexdigest() for name in sorted(payload)}
    payload_hash = hashlib.sha256(json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    require(payload_hash == selection["payload_hash"], label + " differs from the selected whole-package identity")
    receipt = json.loads(files[RECEIPT])
    require(type(receipt.get("schema")) is int and receipt == {
        "schema": 1, "disclosure": "opaque", "package": selection["coordinate"],
        "version": selection["version"], "payload_sha256": selection["payload_hash"], "sha256": hashes},
        label + " receipt differs from the public distribution identity")
    require(hashlib.sha256(files[RECEIPT]).hexdigest() == selection["receipt_hash"], label + " receipt bytes differ")
    materialized = {name: data for name, data in files.items() if name != MARKER}
    require(tree_hash(materialized) == selection["tree_hash"], label + " tree differs from the locked identity")
    marker = tomllib.loads(files[MARKER].decode())
    require(type(marker.get("schema")) is int and marker == {
        "schema": 1, "source_hash": selection["tree_hash"], "spec_format": "mixed",
        "file": [{"path": name, "sha256": hashlib.sha256(data).hexdigest()}
                 for name, data in sorted(materialized.items())]}, label + " slot metadata differs")
    require(tomllib.loads(files["vibe.toml"].decode()) == {
        "package": {"group": "org.jresearch.ai", "name": label, "version": selection["version"],
                    "kind": "flow", "format": "simple", "epoch": 1, "publish": False, "frozen": True,
                    "description": selection["description"], "license": "MIT"},
        "boot_snippet": {"source": selection["boot"], "category": "flow", "link": "dynamic"}},
        label + " manifest changed or gained capabilities/dependencies")
    # The exact whole-package identity also protects conditional boot wording;
    # static native INDEX entries do not make the complete policies unconditional.
    for name, data in materialized.items():
        if not name.endswith(".md"):
            continue
        for target in re.findall(r"\[[^\]\n]*\]\(([^)\s]+)\)", data.decode()):
            url = urlsplit(target.strip("<>"))
            if url.scheme or url.netloc:
                continue
            resolved = (posixpath.normpath(posixpath.join(posixpath.dirname(name), unquote(url.path)))
                        if url.path else name)
            require(resolved in materialized, "Missing or escaping " + label + " reference: " + name)
    return files


def check_small_improvements_adoption(root):
    """Offline route/binding checks, not live discovery or model-compliance proof."""
    _, human = managed(read_file(root, "AGENTS.md"))
    human = " ".join(human.decode().split())
    policy = (SLOT / "vibevm/vibespecs/protocols/small-improvements.md").as_posix()
    require("Relay explicitly adopts all ten complete applicable Shared Governance **7.0.1** protocols" in human
            and "[Small improvements](" + policy + ")" in human,
            "Human-owned adoption must select the complete installed Small Improvements protocol")
    boot = " ".join(read_file(root, BOOT / "90-user.md").decode().split())
    require("Small Improvements is adopted" in boot
            and "analysis-only work skips the scan" in boot
            and LOCAL_GOVERNANCE.as_posix() in boot,
            "Small Improvements boot must preserve conditional discovery and its local binding")
    binding = read_file(root, LOCAL_GOVERNANCE).decode()
    match = re.search(r"^## Small Improvements binding\n(.*?)(?=^## |\Z)", binding, re.M | re.S)
    require(match is not None, "Missing Small Improvements local binding")
    binding = " ".join(match[1].split())
    require("(../" + policy + ")" in binding
            and "repo:jresearchsoftware/codex-relay is:issue is:open label:small-improvement" in binding,
            "Small Improvements binding must retain the selected protocol and exact-label repository lookup")
    require(all(phrase in binding for phrase in (
        "normal independent exact-head acceptance and integration of this adoption",
        "receiving Task's trusted Decisions and admission remain the source of scope authority",
        "one independent review assess the combined exact head",
        "Keep source Issues open and labelled while work remains pending",
        "Analysis-only Task | Skip the SI scan",
        "no cross-repository or periodic queue scan",
        "queue-empty gate or new mandatory CI gate")),
        "Small Improvements binding lost an activation, scope, review, discovery or closure boundary")


def check_landscape_adoption(root):
    """Bounded routing/authority regressions; this does not assess policy semantics."""
    _, human = managed(read_file(root, "AGENTS.md"))
    human = human.decode()
    defaults = re.search(r"the default model is\s+`([^`]+)`, the default reasoning effort is\s+`([^`]+)`"
                         r" and the default Subagents\s+permission is\s+`([^`]+)`", human)
    require(defaults is not None and defaults.groups() == ("gpt-6.1-sol", "xhigh", "On"),
            "Landscape integration must preserve Relay development defaults")

    def section(heading):
        match = re.search(r"^## " + re.escape(heading) + r"\n(.*?)(?=^## |\Z)", human, re.M | re.S)
        require(match is not None, "Missing human-owned Landscape section: " + heading)
        return " ".join(match[1].split())

    subagents, model = LANDSCAPE[1], LANDSCAPE[0]
    subagent_section = section("Shared subagent workflow")
    model_section = section("Model recommendation references")
    for selection, content in ((subagents, subagent_section), (model, model_section)):
        require("(" + (selection["slot"] / selection["policy"]).as_posix() + ")" in content,
                selection["name"] + " human-owned route must select the installed complete policy")
    require(all(phrase in subagent_section for phrase in (
        "Relay explicitly adopts the installed passive `org.jresearch.ai/landscape-subagents` **1.0.2** flow",
        "Task and runtime permit delegation", "Keep the adopted version and admitted profiles stable",
        "Local Task/CR authority, execution boundaries and Writer/Reviewer separation")),
        "Subagent adoption lost its explicit selection or local authority boundary")
    require(all(phrase in model_section for phrase in (
        "supplies advice for owner selection, not automatic adoption of recommendations",
        "Unrelated work skips that detail", "policy/default change requires distinct explicit owner authority",
        "Installation or reading never reselects an admitted parent or child")),
        "Model recommendation route lost its optional or admitted-profile boundary")
    binding = read_file(root, LOCAL_SUBAGENTS).decode()
    relative_policy = "../../" + (subagents["slot"] / subagents["policy"]).as_posix()
    require("(" + relative_policy + ")" in binding
            and "not another maintained copy" in " ".join(binding.split())
            and not any("## " + heading in binding for heading in (
                "When to delegate", "Select a profile for each assignment",
                "Give each helper a complete, bounded assignment", "Coordinate and verify")),
            "Local subagent binding must route to the sole installed reusable policy")


HISTORICAL_SLOT = Path("vibevm/vibedeps/org.jresearch.ai.development-governance/7.0.0")


def check_package(directory, *, standalone=False, historical=False):
    # Build/release evidence is a separate frozen delivery, never a policy fallback.
    version, source_revision, payload_hash_expected, receipt_hash, tree_hash_expected = (
        ("5.0.0", "d0b3d67ef94a5537ebd4a2bbf4a38e3a6629c0c9",
         "f4ad03a0137bd0d4c8cab58fa7d42ccbe0bb3aba2315cb9c96f5f93c7ea86275",
         "45f43dcdb48ff9dfcfc114284cd8c25bdeda3f870883633f08057504edf98bc9",
         "sha256:e686314f26c82f32f55958a242481d792e9fcd0d755a6eebf933431f3e0875d9")
        if standalone else (VERSION, SOURCE_REVISION, PAYLOAD_HASH, RECEIPT_HASH, TREE_HASH))
    if historical:
        require(not standalone, "Historical project evidence is not standalone delivery")
        version, source_revision, payload_hash_expected, receipt_hash, tree_hash_expected = (
            "7.0.0", "bee96f1715142fde598318e7db402168dcfabf5f",
            "3eff2ae300602e812b99539b18fe3d8232c92191ec1e5515c156a6754be51257",
            "bff287dbbdd7801b65d724eef0b0f34daed33157f1f90773cfd956471aecb47b",
            "sha256:fcb5afd9f08bad0a5115f1373ed215e91101407969ff0caf71ee856927510a07")
    payload = PAYLOAD - {"vibevm/vibespecs/protocols/small-improvements.md",
                         "vibevm/vibespecs/guides/small-improvements.md"} if standalone else PAYLOAD
    files = files_in(directory)
    require(set(files) == payload | {RECEIPT, MARKER}, "Unexpected or missing passive slot files")
    hashes = {name: hashlib.sha256(files[name]).hexdigest() for name in sorted(payload)}
    payload_hash = hashlib.sha256(json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    require(payload_hash == payload_hash_expected, "Payload differs from the accepted whole-package identity")
    receipt = json.loads(files[RECEIPT])
    require(receipt == {"package": COORDINATE, "payload_sha256": payload_hash_expected, "schema": 1,
                        "sha256": hashes, "source_path": "packages/development-governance",
                        "source_repository": SOURCE_REPOSITORY, "source_revision": source_revision,
                        "version": version}, "Receipt differs from accepted source/path/hash identity")
    require(hashlib.sha256(files[RECEIPT]).hexdigest() == receipt_hash, "Receipt bytes differ")
    materialized = {name: data for name, data in files.items() if name != MARKER}
    require(tree_hash(materialized) == tree_hash_expected, "Materialized tree differs from the locked identity")
    marker = tomllib.loads(files[MARKER].decode())
    require(type(marker.get("schema")) is int
            and marker == {"schema": 1, "source_hash": tree_hash_expected, "spec_format": "mixed",
                           "file": [{"path": name, "sha256": hashlib.sha256(data).hexdigest()}
                                    for name, data in sorted(materialized.items())]},
            "Slot metadata differs from the complete materialized payload")
    manifest = tomllib.loads(files["vibe.toml"].decode())
    require(manifest == {"package": {"group": "org.jresearch.ai", "name": "development-governance",
                                     "version": version, "kind": "flow", "format": "simple", "epoch": 1,
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
    installation = Path("vibevm/vibepacks/org.jresearch.ai/codex-relay/v4.1.0")
    installation_files = files_in(root / installation)
    require(tree_hash(installation_files) == "sha256:bd1c15a6f15246798eaa66fa434e843eb57db2a4ca084dc79420277d29979385",
            "Frozen accepted 4.1.0 registry changed")
    remediation = Path("vibevm/vibepacks/org.jresearch.ai/codex-relay/v4.1.1")
    remediation_files = files_in(root / remediation)
    require(tree_hash(remediation_files) == "sha256:d9e85f939816b7f048e77f0e5608720498272118a7fecc35cc973fb3c9934730",
            "Frozen accepted 4.1.1 registry changed")
    previous_self_files = files_in(root / PREVIOUS_SELF_SOURCE)
    require(tree_hash(previous_self_files) == PREVIOUS_SELF_HASH,
            "Frozen accepted Relay 5.0.0 registry changed")
    require(files_in(root / "vibevm/vibepacks") == {
        (package.relative_to("vibevm/vibepacks") / name).as_posix(): data
        for package, files in ((HISTORICAL_SELF_SOURCE, historical), (previous, previous_files), (released, released_files), (prior, prior_files), (manual, manual_files), (frozen, frozen_files), (installation, installation_files), (remediation, remediation_files), (PREVIOUS_SELF_SOURCE, previous_self_files), (SELF_SOURCE, expected))
        for name, data in files.items()},
        "Unexpected first-party registry package or file")


def check_standalone_snapshot(root):
    metadata = json.loads(read_file(root, "guidance/source.json"))
    require(metadata["shared_version"] == "5.0.0"
            and metadata["shared_source_revision"] == "d0b3d67ef94a5537ebd4a2bbf4a38e3a6629c0c9"
            and metadata["shared_distribution_revision"] == "30a23f467c30c41fec918204cbbf2ecfffd7bef5"
            and metadata["shared_distribution_tree_hash"] ==
                "sha256:e686314f26c82f32f55958a242481d792e9fcd0d755a6eebf933431f3e0875d9",
            "Standalone selection differs from the accepted immutable Shared snapshot")
    snapshot = Path("vibevm/vibedeps/org.jresearch.ai.development-governance/5.0.0")
    files = check_package(root / "guidance/artifacts/vpm" / snapshot, standalone=True)
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


def check_manual_handoff_contract(root):
    """Bind manual-client completion to original Writer evidence."""
    workflow = " ".join(read_file(root, "packages/codex-relay/skill/references/workflow.md").decode().split()).lower()
    required = ("return the complete, unmodified writer prompt",
                "the concrete terminal diagnostic",
                "report only the observed label, event, run and writer state",
                "do not report success without writer publication evidence",
                "an inferred step or pending run is not a terminal handoff",
                "through the original ready event and run")
    require(all(phrase in workflow for phrase in required),
            "Manual handoff wait must return the original Writer prompt or terminal diagnostic and preserve unresolved client-boundary status")


def check_project(root):
    manifest = tomllib.loads(read_file(root, "vibe.toml").decode())
    requirements = {COORDINATE: {"version": "=" + VERSION,
                    "git": DISTRIBUTION_REPOSITORY, "rev": DISTRIBUTION_REVISION, "auth": "none"},
                    "flow:" + SELF_COORDINATE: {"version": "=" + SELF_VERSION, "link": "dynamic"}}
    requirements.update({selection["coordinate"]: {
        "version": "=" + selection["version"], "git": selection["repository"],
        "rev": selection["revision"], "auth": "none"} for selection in LANDSCAPE})
    require(manifest == {"project": {"name": "codex-relay", "version": "0.0.0", "spec_format": "mixed"},
                         "requires": {"packages": requirements},
                         "registry": [{"name": "producer", "url": "vibevm/vibepacks", "auth": "none"}]},
            "Consumer must retain exact Shared/Landscape Git and native first-party requirements")
    files = check_package(root / SLOT)
    landscape_files = {selection["coordinate"]: check_landscape_package(root / selection["slot"], selection)
                       for selection in LANDSCAPE}
    check_landscape_adoption(root)
    check_small_improvements_adoption(root)
    check_manual_handoff_contract(root)
    first_party, source_hash = check_first_party(root)
    check_standalone_snapshot(root)
    lock = tomllib.loads(read_file(root, "vibe.lock").decode())
    packages = lock.get("package", [])
    require(len(packages) == 4, "Expected exactly Shared, Relay and both Landscape native packages")
    require({(entry.get("group"), entry.get("name")) for entry in packages} == {
        ("org.jresearch.ai", name) for name in ("development-governance", "codex-relay",
                                               *(selection["name"] for selection in LANDSCAPE))},
        "Duplicate or unexpected native package identity")
    shared = next((entry for entry in packages if entry.get("name") == "development-governance"), None)
    first = next((entry for entry in packages if entry.get("name") == "codex-relay"), None)
    require(set(lock) == {"meta", "package"} and set(lock["meta"]) == {
        "generated_by", "generated_at", "schema_version", "root_dependencies"}
        # Native install preserves the old meta header when updating an existing
        # schema-7 lock; a clean 1.0.11 install writes its actual new version.
        and lock["meta"]["generated_by"] in {"vibe 1.0.7", "vibe 1.0.11"}
        and type(lock["meta"]["schema_version"]) is int and lock["meta"]["schema_version"] == 7
        and isinstance(lock["meta"]["generated_at"], str)
        and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", lock["meta"]["generated_at"])
        and lock["meta"]["root_dependencies"] == ["flow:" + SELF_COORDINATE + "@=" + SELF_VERSION, COORDINATE,
                                                   *(selection["coordinate"] for selection in LANDSCAPE)]
        and shared == {"kind": "flow", "name": "development-governance", "group": "org.jresearch.ai",
                                 "version": VERSION, "source_url": DISTRIBUTION_REPOSITORY,
                                 "source_ref": DISTRIBUTION_REVISION, "content_hash": TREE_HASH,
                                 "files_written": [], "admitted_by": "root-edge", "source_kind": "git"},
        "Schema-7 lock differs from the admitted graph/source/content identity")
    for selection in LANDSCAPE:
        entry = next(entry for entry in packages if entry["name"] == selection["name"])
        require(entry == {"kind": "flow", "name": selection["name"], "group": "org.jresearch.ai",
                          "version": selection["version"], "source_url": selection["repository"],
                          "source_ref": selection["revision"], "content_hash": selection["tree_hash"],
                          "files_written": [], "admitted_by": "root-edge", "source_kind": "git"},
                selection["name"] + " lock differs from the selected passive root identity")
    require(first is not None, "Missing first-party native lock entry")
    # Native absolute location metadata can come from another supported checkout.
    # Exact export/registry/slot equality above supplies portable content identity.
    source_url = first.get("source_url", "")
    require(source_url.startswith("file://") and
            unquote(source_url).endswith("/" + SELF_SOURCE.as_posix()),
            "First-party source is not a generated in-tree registry location")
    first_kind = first.get("source_kind")
    require(first_kind in {"local", "registry"}, "First-party source kind is not native registry metadata")
    require(first == {"kind": "flow", "group": "org.jresearch.ai", "name": "codex-relay",
                      "version": SELF_VERSION, "source_url": source_url, "content_hash": source_hash,
                      "files_written": [], "dependencies": [COORDINATE + "@=" + VERSION],
                      "admitted_by": "root-edge", "source_kind": first_kind},
            "First-party lock differs from native content/dependency identity")
    index = tomllib.loads(read_file(root, BOOT / "INDEX.md").decode())
    paths = [(BOOT / SOURCES[0]).as_posix(), (SLOT / PACKAGE_BOOT).as_posix(),
             (SELF_SLOT / SELF_BOOT).as_posix(),
             *((selection["slot"] / selection["boot"]).as_posix() for selection in LANDSCAPE),
             (BOOT / SOURCES[1]).as_posix()]
    # Native v1.0.11 emits static here despite boot_snippet.link = "dynamic".
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
    # Task #199 preserves this exact accepted slot as inactive historical evidence.
    # Native maintenance may prune it; it never enters the selected graph or routes.
    historical_files = (check_package(root / HISTORICAL_SLOT, historical=True)
                        if (root / HISTORICAL_SLOT).exists() else {})
    require(set(files_in(root / "vibevm/vibedeps")) == {
        (SLOT.relative_to("vibevm/vibedeps") / name).as_posix() for name in files} | {
        (SELF_SLOT.relative_to("vibevm/vibedeps") / name).as_posix() for name in {*first_party, MARKER}} | {
        (HISTORICAL_SLOT.relative_to("vibevm/vibedeps") / name).as_posix() for name in historical_files} | {
        (selection["slot"].relative_to("vibevm/vibedeps") / name).as_posix()
        for selection in LANDSCAPE for name in landscape_files[selection["coordinate"]]},
            "Unexpected materialized dependency graph")
    for relative in ("vibevm/vibespecs/WAL.md", "vibevm/vibespecs/WAL.xml",
                     ".agents/skills/proportional-controls", ".agents/skills/.proportional-controls.vibe-skill-receipt.toml"):
        require(not (root / relative).exists() and not (root / relative).is_symlink(),
                "Unexpected WAL or projected governance Skill: " + relative)
    return {"route": paths, "boot_bytes": sum(len(read_file(root, path)) for path in paths),
            "payload_files": len(PAYLOAD), "tree_hash": TREE_HASH, "payload_sha256": PAYLOAD_HASH,
            "source_revision": SOURCE_REVISION, "distribution_revision": DISTRIBUTION_REVISION,
            "first_party_version": SELF_VERSION, "first_party_tree_hash": source_hash,
            "project_skill": "PASS", "standalone_snapshot": "5.0.0",
            "landscape": {selection["coordinate"]: {
                "version": selection["version"], "distribution_revision": selection["revision"],
                "tree_hash": selection["tree_hash"], "payload_files": len(selection["payload"]),
                "provenance": "opaque public distribution"} for selection in LANDSCAPE}}


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
        "vibe.toml", "vibe.lock", "guidance/source.json", *AGENTS, SKILL_RECEIPT,
        LOCAL_SUBAGENTS, LOCAL_GOVERNANCE, "packages/codex-relay/skill/references/workflow.md")}
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

        def run(project, label, *arguments, collision=False, incomplete=False, hash_mismatch=False, source_mismatch=False, offline=True):
            result = subprocess.run([str(vibe), *(["--offline"] if offline else []), "--json", *arguments], cwd=project, env=env,
                                    text=True, capture_output=True, timeout=120)
            if collision or incomplete or hash_mismatch or source_mismatch:
                evidence = ("malformed <vibevm> block" if collision else
                            "lock_slot_hash" if hash_mismatch else
                            "lock_hash_mismatch" if source_mismatch else "slot missing")
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
        route_paths = ["vibe.toml", "vibe.lock", *AGENTS, LOCAL_SUBAGENTS.as_posix(),
                       LOCAL_GOVERNANCE.as_posix(),
                       *(str(BOOT / name) for name in ("INDEX.md", *SOURCES))]
        route_paths += [(SLOT / name).as_posix() for name in PAYLOAD | {RECEIPT, MARKER}]
        route_paths += [(selection["slot"] / name).as_posix()
                        for selection in LANDSCAPE for name in selection["payload"] | {RECEIPT, MARKER}]
        route_paths += [(SELF_SLOT / name).as_posix() for name in files_in(project / SELF_SLOT)]
        route_paths += [(PROJECTION / name).as_posix() for name in files_in(project / PROJECTION)]
        route_paths += [SKILL_RECEIPT.as_posix()]
        original = {name: read_file(project, name) for name in route_paths}

        def unchanged(expected):
            for name, data in expected.items():
                require(read_file(project, name) == data, "Authored/generated bytes drifted: " + name)

        def rebind(project, label):
            # LocalRegistry deliberately serializes an absolute file:// source.
            # A copied checkout must resolve it again through native install;
            # never rewrite the lock or ignore local_source_freshness findings.
            check_project(project)
            before = {name: read_file(project, name) for name in route_paths}
            run(project, label, "install", "--no-default-registry", "--assume-yes", offline=False)
            check_relocation_lock(before["vibe.lock"], read_file(project, "vibe.lock"),
                                  project / SELF_SOURCE, label)
            for name, data in before.items():
                if name != "vibe.lock":
                    require(read_file(project, name) == data, label + " changed ready bytes: " + name)
            check_project(project)

        # Reproduce a real checkout move with its origin absent, not merely a
        # copy whose original local registry remains accessible on this host.
        origin = root / "origin"
        copy_project(project_root, origin)
        rebind(origin, "origin-install")
        relocated = root / "relocated"
        origin.rename(relocated)
        result = subprocess.run([str(vibe), "--offline", "--json", "check", "--path", "."],
                                cwd=relocated, env=env, text=True, capture_output=True, timeout=120)
        report = json.loads(result.stdout)
        require(result.returncode == 0 and not result.stderr.strip()
                and report["summary"] == {"error": 0, "warning": 1, "info": 0}
                and len(report["findings"]) == 1
                and report["findings"][0]["check"] == "local_source_freshness"
                and "no longer on disk" in report["findings"][0]["message"],
                "Moved checkout did not expose its missing original source: " + result.stdout + result.stderr)
        reports["relocation-before-install"] = report
        rebind(relocated, "relocation-install")
        run(relocated, "relocation-check", "check", "--path", ".")
        rebind(project, "checkout-install")
        original = {name: read_file(project, name) for name in route_paths}

        def rejected(label):
            try:
                check_project(project)
            except (RuntimeError, ValueError, OSError):
                reports[label] = {"local_verifier": "rejected"}
            else:
                raise RuntimeError(label + " was accepted by the local verifier")

        clean = root / "clean"
        copy_project(project_root, clean)
        (clean / "vibe.lock").unlink()
        import shutil
        shutil.rmtree(clean / "vibevm/vibedeps")
        run(clean, "clean-install", "install", "--no-default-registry", "--assume-yes", offline=False)
        check_project(clean)
        require(tomllib.loads((clean / "vibe.lock").read_text())["meta"]["generated_by"] == version,
                "Clean install did not record the verified tool version")
        clean_before = files_in(clean / "vibevm/vibedeps")
        clean_lock = (clean / "vibe.lock").read_bytes()
        run(clean, "repeat-install", "install", "--no-default-registry", "--assume-yes")
        require(files_in(clean / "vibevm/vibedeps") == clean_before,
                "Repeat install drifted from clean native generation")
        check_repeat_lock(clean_lock, (clean / "vibe.lock").read_bytes())
        check_project(clean)

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

        # 1.0.10+ must refuse changed same-version source before copying any slot.
        source_readme = project / SELF_SOURCE / "README.md"
        source_before = source_readme.read_bytes()
        source_readme.write_bytes(source_before + b"\nSynthetic same-version source drift\n")
        unchanged_before = {name: read_file(project, name) for name in original}
        run(project, "force-reinstall-source-drift", "reinstall", ".", "--force", "--assume-yes",
            source_mismatch=True)
        unchanged(unchanged_before)
        source_readme.write_bytes(source_before)
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
                run(project, label + "-upstream-check", "check", "--path", ".",
                    hash_mismatch=label == "corrupt-lock")
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
                          "upstream_check_limitations": "accepts missing INDEX/payload; rejects divergent remote lock/slot hash",
                          "upstream_acquisition_limitations": "offline reinstall needs an existing slot; upstream install/check is not accepted-source verification",
                          "model_behavior": "UNVERIFIED: no Codex/provider execution", "reports": reports}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=ROOT,
                        help="complete ready checkout/isolated fixture to verify (default: this checkout)")
    parser.add_argument("--vibe", type=Path, help="already acquired, hash-pinned Linux x86_64 musl v1.0.11 binary")
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
