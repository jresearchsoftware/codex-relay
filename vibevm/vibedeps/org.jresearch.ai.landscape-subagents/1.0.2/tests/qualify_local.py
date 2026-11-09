"""Native VibeVM 1.0.7 checks in an ordinary disposable local registry/consumer."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
import tomllib


PACKAGE = Path(__file__).resolve().parents[1]
BINARY_SHA256 = "20d111df02eb28040ef4cb766bfcb0bde8ff4427b031f88f33eacb3711c3e240"
COORDINATE = "org.jresearch.ai/landscape-subagents"
SLOT = "vibevm/vibedeps/org.jresearch.ai.landscape-subagents/1.0.2"
BOOT = "vibevm/vibespecs/boot/landscape-subagents.md"
SENTINEL = (
    "# Disposable subagent-flow consumer\n\n"
    "Human-owned authority sentinel. This fixture does not adopt the installed flow.\n"
    "No delegation, configuration change or external action is authorized.\n"
)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def json_documents(text):
    """Vibe can emit multiple JSON envelopes on stdout; parse every document."""
    decoder = json.JSONDecoder()
    documents = []
    while text.strip():
        document, end = decoder.raw_decode(text.lstrip())
        documents.append(document)
        text = text.lstrip()[end:]
    require(bool(documents), "Native command returned no JSON evidence")
    return documents


def run(vibe, environment, *arguments):
    process = subprocess.run(
        [str(vibe), "--offline", "--json", *arguments],
        cwd=Path(environment["VIBE_SETTINGS"]).parent,
        env=environment, text=True, capture_output=True,
    )
    require(process.returncode == 0, f"{arguments}: {process.stdout}\n{process.stderr}")
    documents = json_documents(process.stdout)
    for document in documents:
        require(isinstance(document, dict), f"Unexpected envelope: {document}")
        for key in ("success", "ok", "complete"):
            require(document.get(key) is not False, f"Native failure: {document}")
    if arguments[0] in {"install", "reinstall"}:
        result = documents[-1]
        require(result.get("ok") is True and result.get("complete") is True,
                f"Unconfirmed native completion: {result}")
    elif arguments[0] == "validate":
        result = documents[-1]
        require(result.get("command") == "lifecycle" and result.get("ok") is True,
                f"Unconfirmed validation: {result}")
        require(result.get("steps") == [{"phase": "validate", "status": "ok"}],
                f"Unexpected validation steps: {result}")
        require(result.get("contributions") == [] and result.get("notices") == [],
                f"Unexpected executable contributions: {result}")
    elif arguments[0] == "check":
        require(len(documents) == 1, f"Unexpected check documents: {documents}")
        result = documents[0]
        require(result.get("ok") is True, f"Native check failed: {result}")
        require(result.get("summary") == {"error": 0, "warning": 0, "info": 0},
                f"Nonzero native diagnostics: {result}")
        require(result.get("findings") == [], f"Native findings: {result}")
    return documents


def hashes(root):
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts
    }


def verify_consumer(consumer, source_hashes):
    slot = consumer / SLOT
    require(set(hashes(slot)) == set(source_hashes) | {".vibe-slot.toml"},
            f"Unexpected installed inventory: {sorted(hashes(slot))}")
    for path, digest in source_hashes.items():
        require((slot / path).is_file(), f"Missing installed file: {path}")
        require(hashlib.sha256((slot / path).read_bytes()).hexdigest() == digest,
                f"Installed bytes differ: {path}")
    instructions = (consumer / "AGENTS.md").read_text(encoding="utf-8")
    require(instructions.startswith(SENTINEL), "Human-owned authority was replaced")
    require("vibevm/vibespecs/boot/INDEX.md" in instructions, "Missing native root route")
    index = tomllib.loads((consumer / "vibevm/vibespecs/boot/INDEX.md").read_text())
    entries = index.get("entry", [])
    require(len(entries) == 1, f"Unexpected eager boot entries: {entries}")
    require(entries[0]["path"] == f"{SLOT}/{BOOT}", f"Wrong boot route: {entries}")
    require(entries[0]["kind"] in {"static", "dynamic"}, f"Unknown route kind: {entries}")
    require((consumer / entries[0]["path"]).is_file(), "INDEX target is missing")
    require(not (consumer / "vibevm/vibespecs/boot/STATIC.md").exists(), "Unexpected stock boot")
    require(not (consumer / ".agents/skills").exists(), "Unexpected native Skill")
    lock = tomllib.loads((consumer / "vibe.lock").read_text())
    require(lock["meta"]["schema_version"] == 7, "Unexpected lock schema")
    require(lock["meta"]["root_dependencies"] == [f"{COORDINATE}@=1.0.2"],
            f"Unexpected dependencies: {lock}")
    packages = lock.get("package", [])
    require(len(packages) == 1, "Unexpected transitive package")
    selected = packages[0]
    for key, value in {"group": "org.jresearch.ai", "name": "landscape-subagents",
                       "version": "1.0.2", "kind": "flow", "files_written": []}.items():
        require(selected.get(key) == value, f"Unexpected lock field {key}: {selected}")
    require(selected["content_hash"].startswith("sha256:"), "Missing native content identity")
    require(selected.get("source_kind") == "registry", "Wrong fixture transport")
    require(selected.get("source_url") ==
            (consumer.parent / "registry" / COORDINATE / "v1.0.2").as_uri(),
            "Lock did not retain exact fixture source identity")
    require(selected.get("admitted_by") == "root-edge", "Wrong dependency admission")
    metadata = tomllib.loads((slot / ".vibe-slot.toml").read_text())
    require(metadata.get("source_hash") == selected["content_hash"],
            "Native slot and lock identities differ")
    require({entry["path"]: entry["sha256"] for entry in metadata.get("file", [])}
            == source_hashes, "Native slot metadata differs from source bytes")
    return {"entry_kind": entries[0]["kind"], "content_hash": selected["content_hash"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vibe", type=Path, required=True)
    options = parser.parse_args()
    require(platform.system() == "Linux" and platform.machine() in {"x86_64", "amd64"},
            "This fixture qualifies only Linux x86_64 (including Debian WSL)")
    vibe = options.vibe.resolve()
    require(hashlib.sha256(vibe.read_bytes()).hexdigest() == BINARY_SHA256,
            "VibeVM binary differs from the pinned 1.0.7 Linux musl asset")
    version = subprocess.check_output([str(vibe), "--version"], text=True).strip()
    require(version == "vibe 1.0.7", f"Unexpected VibeVM version: {version}")
    source_hashes = hashes(PACKAGE)
    with tempfile.TemporaryDirectory(prefix="landscape-subagents-") as directory:
        fixture = Path(directory)
        registry = fixture / "registry"
        shutil.copytree(PACKAGE, registry / COORDINATE / "v1.0.2",
                        ignore=shutil.ignore_patterns("__pycache__"))
        consumer = fixture / "consumer"
        consumer.mkdir()
        (consumer / "vibe.toml").write_text(
            '[project]\nname = "landscape-subagents-fixture"\nversion = "0.0.0"\n'
            'spec_format = "mixed"\n\n[requires.packages]\n'
            f'"{COORDINATE}" = "=1.0.2"\n', encoding="utf-8",
        )
        (consumer / "AGENTS.md").write_text(SENTINEL, encoding="utf-8")
        manifest_bytes = (consumer / "vibe.toml").read_bytes()
        environment = os.environ.copy()
        environment["VIBE_SETTINGS"] = str(fixture / "settings")
        environment["VIBEVM_USER_CONFIG"] = str(fixture / "settings/config.toml")
        common = ["--path", str(consumer), "--registry", str(registry),
                  "--no-default-registry", "--no-prefer-local", "--assume-yes"]
        results = {}
        results["install"] = run(vibe, environment, "install", *common)
        identity = verify_consumer(consumer, source_hashes)
        routes = {p: (consumer / p).read_bytes() for p in (
            "AGENTS.md", "CLAUDE.md", "GEMINI.md", "vibevm/vibespecs/boot/INDEX.md",
        )}
        results["validate"] = run(vibe, environment, "validate", *common)
        results["check"] = run(vibe, environment, "check", "--path", str(consumer))
        results["repeat_install"] = run(vibe, environment, "install", *common)
        require(results["repeat_install"][-1].get("unchanged") is True,
                "Repeat install was not a no-op")
        results["reinstall"] = run(vibe, environment, "reinstall", str(consumer))
        require(results["reinstall"][-1].get("hooks") == [], "Unexpected reinstall hook")
        require(verify_consumer(consumer, source_hashes) == identity,
                "Reinstall changed native package identity")
        for path, content in routes.items():
            require((consumer / path).read_bytes() == content, f"Native route changed: {path}")
        require((consumer / "vibe.toml").read_bytes() == manifest_bytes,
                "Native command changed consumer dependency authority")
        require(hashes(PACKAGE) == source_hashes, "Fixture changed producer package bytes")
        print(json.dumps({"version": version, "binary_sha256": BINARY_SHA256,
                          "package_files_compared": len(source_hashes),
                          "identity": identity, "commands": results}, indent=2))


if __name__ == "__main__":
    main()
