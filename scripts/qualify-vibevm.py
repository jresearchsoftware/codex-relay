#!/usr/bin/env python3
"""Opt-in qualification of Relay's committed passive VibeVM flow; never downloads tools."""
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
VERSION = "2.1.0"
SLOT = Path("vibevm/vibedeps/org.jresearch.ai.development-governance") / VERSION
PACKAGE_BOOT = "vibevm/vibespecs/boot/development-governance.md"
PROTOCOLS = tuple("vibevm/vibespecs/protocols/" + name + ".md" for name in
                  ("package-versioning", "proportional-controls", "requirement-authority",
                   "task-handoff", "self-adoption", "github-repository-governance"))
PAYLOAD = {"LICENSE", "README.md", "vibe.toml", PACKAGE_BOOT, *PROTOCOLS}
# Accepted producer exports omit only their generated local client routes.
SOURCE_ONLY = {"AGENTS.md", "CLAUDE.md", "GEMINI.md", "vibevm/vibespecs/boot/INDEX.md",
               "vibevm/vibespecs/boot/.vibe-boot-artifacts.lock"}
RECEIPT = "DISTRIBUTION.json"
MARKER = ".vibe-slot.toml"
DISTRIBUTION_REPOSITORY = "https://github.com/jrs-vibevm/org.jresearch.ai.development-governance.git"
DISTRIBUTION_REVISION = "4211f55dcaeb3077d6abdbfba53a42ed848351b2"
SOURCE_REPOSITORY = "https://github.com/jresearchsoftware/shared-governance"
SOURCE_REVISION = "c3fbc8c2d10982889bea526161f810902def4289"
PAYLOAD_HASH = "1d6e4098ee557319dc04d21defc33260aee1ce21e82b502f8e60726b2b68e955"
RECEIPT_HASH = "a20f074a317f5e725d77b5b510e3e4c129f41fa266b5a9d3d4dae3ddf554dadc"
TREE_HASH = "sha256:df90ef1a287c2ce5a70aff4443a0782410b628459722792ed326bde5aaf86ecc"
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
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), unquote(url.path)))
            require(resolved in materialized, "Missing or escaping passive reference: " + name)
    pointer = files[PACKAGE_BOOT].decode()
    require(all("../protocols/" + Path(name).name in pointer for name in PROTOCOLS)
            and "Unrelated tasks" in pointer and "explicitly adopted" in pointer,
            "Conditional full-procedure navigation is missing")
    return files


def check_project(root):
    manifest = tomllib.loads(read_file(root, "vibe.toml").decode())
    require(manifest == {"project": {"name": "codex-relay", "version": "0.0.0", "spec_format": "mixed"},
                         "requires": {"packages": {COORDINATE: {"version": "=" + VERSION,
                                     "git": DISTRIBUTION_REPOSITORY, "rev": DISTRIBUTION_REVISION,
                                     "auth": "none"}}}}, "Consumer must retain the exact anonymous Git requirement")
    files = check_package(root / SLOT)
    lock = tomllib.loads(read_file(root, "vibe.lock").decode())
    require(set(lock) == {"meta", "package"} and set(lock["meta"]) == {
        "generated_by", "generated_at", "schema_version", "root_dependencies"}
        and lock["meta"]["generated_by"] == "vibe 1.0.7"
        and type(lock["meta"]["schema_version"]) is int and lock["meta"]["schema_version"] == 7
        and isinstance(lock["meta"]["generated_at"], str)
        and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", lock["meta"]["generated_at"])
        and lock["meta"]["root_dependencies"] == [COORDINATE]
        and lock["package"] == [{"kind": "flow", "name": "development-governance", "group": "org.jresearch.ai",
                                 "version": VERSION, "source_url": DISTRIBUTION_REPOSITORY,
                                 "source_ref": DISTRIBUTION_REVISION, "content_hash": TREE_HASH,
                                 "files_written": [], "admitted_by": "root-edge", "source_kind": "git"}],
        "Schema-7 lock differs from the admitted graph/source/content identity")
    index = tomllib.loads(read_file(root, BOOT / "INDEX.md").decode())
    paths = [(BOOT / SOURCES[0]).as_posix(), (SLOT / PACKAGE_BOOT).as_posix(), (BOOT / SOURCES[1]).as_posix()]
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
        (SLOT.relative_to("vibevm/vibedeps") / name).as_posix() for name in files},
            "Unexpected materialized dependency graph")
    for relative in ("vibevm/vibespecs/WAL.md", "vibevm/vibespecs/WAL.xml",
                     ".agents/skills/proportional-controls", ".agents/skills/.proportional-controls.vibe-skill-receipt.toml"):
        require(not (root / relative).exists() and not (root / relative).is_symlink(),
                "Unexpected WAL or projected governance Skill: " + relative)
    return {"route": paths, "boot_bytes": sum(len(read_file(root, path)) for path in paths),
            "payload_files": len(PAYLOAD), "tree_hash": TREE_HASH, "payload_sha256": PAYLOAD_HASH,
            "source_revision": SOURCE_REVISION, "distribution_revision": DISTRIBUTION_REVISION}


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


def copy_tracked(destination):
    names = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    for name in filter(None, names):
        data = read_file(ROOT, name)
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def probe(vibe, pin):
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
                    require(document["summary"]["error"] == document["summary"]["warning"] == 0
                            and not document["findings"], label + " has findings: " + result.stdout)
            require(not result.stderr.strip(), label + " emitted diagnostics: " + result.stderr)
            reports[label] = documents

        version = subprocess.check_output([str(vibe), "--version"], cwd=root, env=env, text=True).strip()
        require(version == "vibe " + pin["version"], "Unexpected tool version")
        project = root / "project"
        copy_tracked(project)
        facts = check_project(project)
        route_paths = ["vibe.toml", "vibe.lock", *AGENTS, *(str(BOOT / name) for name in ("INDEX.md", *SOURCES))]
        route_paths += [(SLOT / name).as_posix() for name in PAYLOAD | {RECEIPT, MARKER}]
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
    parser.add_argument("--vibe", type=Path, help="already acquired, hash-pinned Linux x86_64 musl v1.0.7 binary")
    parser.add_argument("--source-dir", type=Path, help="optional accepted source package directory for whole-payload byte comparison")
    parser.add_argument("--distribution-dir", type=Path, help="optional acquired public distribution directory for whole-payload/receipt byte comparison")
    args = parser.parse_args()
    facts = check_project(ROOT)
    if args.source_dir or args.distribution_dir:
        compare_inputs(ROOT, args.source_dir, args.distribution_dir)
    print(json.dumps({"passive_package_route": "PASS", **facts,
                      "source_byte_comparison": "PASS" if args.source_dir else "not requested",
                      "distribution_byte_comparison": "PASS" if args.distribution_dir else "not requested",
                      "tool_probe": "pending" if args.vibe else "not requested", "model_behavior": "UNVERIFIED"}))
    if args.vibe:
        pin = json.loads((ROOT / "toolchain/vibevm.json").read_text())
        probe(args.vibe.resolve(), pin)


if __name__ == "__main__":
    main()
