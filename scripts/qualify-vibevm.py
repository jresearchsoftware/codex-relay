#!/usr/bin/env python3
"""Opt-in, disposable qualification of Relay's dependency-free native VibeVM route."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
BOOT = Path("vibevm/vibespecs/boot")
AGENTS = ("AGENTS.md", "CLAUDE.md", "GEMINI.md")
SOURCES = ("00-core.md", "90-user.md")
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


def check_project(root):
    manifest = tomllib.loads((root / "vibe.toml").read_text())
    require(manifest == {"project": {"name": "codex-relay", "version": "0.0.0",
                                   "spec_format": "mixed"}},
            "Route must remain a project without requirements, registries or capabilities")
    lock = tomllib.loads((root / "vibe.lock").read_text())
    require(set(lock) == {"meta"} and set(lock["meta"]) == {
        "generated_by", "generated_at", "schema_version"}
        and lock["meta"]["generated_by"] == "vibe 1.0.7"
        and lock["meta"]["schema_version"] == 7, "Expected the empty v1.0.7 lock")
    index = tomllib.loads((root / BOOT / "INDEX.md").read_text())
    require(index == {"schema": 1, "entry": [
        {"path": str(BOOT / name).replace("\\", "/"), "kind": "static"} for name in SOURCES]},
        "Expected only the two bounded authored boot sources, in order")
    require({p.name for p in (root / BOOT).iterdir()} <= {
        "INDEX.md", *SOURCES, ".vibe-boot-artifacts.lock"}, "Unexpected boot content")
    for name in SOURCES:
        require((root / BOOT / name).is_file(), "Missing authored boot source: " + name)
    blocks = [managed((root / name).read_bytes())[0] for name in AGENTS]
    require(len(set(blocks)) == 1 and b"vibevm/vibespecs/boot/INDEX.md" in blocks[0],
            "Native redirects differ or do not name INDEX")
    require(not (root / "vibevm/vibedeps").exists(), "Route has no materialized packages")
    require(not any((root / "vibevm/vibespecs" / name).exists() for name in ("WAL.md", "WAL.xml")),
            "Route must not introduce a WAL")
    return sum((root / BOOT / name).stat().st_size for name in SOURCES)


def copy_tracked(destination):
    names = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    for name in filter(None, names):
        source = ROOT / name
        require(source.is_file() and not source.is_symlink(), "Expected ordinary tracked files: " + name)
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


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

        def run(project, label, *arguments, collision=False):
            result = subprocess.run([str(vibe), "--offline", "--json", *arguments], cwd=project, env=env,
                                    text=True, capture_output=True, timeout=120)
            if collision:
                require(result.returncode != 0 and 'malformed <vibevm> block' in result.stderr,
                        label + " did not refuse malformed markers")
                reports[label] = {"exit": result.returncode, "malformed_block_refused": True}
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
        boot_bytes = check_project(project)  # File reads need no executable, local state, HOME or cache.
        prompt_paths = [*AGENTS, *(str(BOOT / name) for name in ("INDEX.md", *SOURCES))]
        original = {name: (project / name).read_bytes() for name in ["vibe.toml", "vibe.lock", *prompt_paths]}

        def unchanged(expected):
            for name, data in expected.items():
                require((project / name).read_bytes() == data, "Authored/generated bytes drifted: " + name)

        run(project, "validate", "validate", "--path", ".", "--no-default-registry")
        run(project, "check", "check", "--path", ".")
        unchanged(original)
        for count in range(2):
            run(project, "reinstall-" + str(count + 1), "reinstall", ".", "--assume-yes")
            unchanged(original)  # Includes the generator's exact INDEX EOF bytes.
        run(project, "repeat-init", "init", ".", "--type", "project", "--name", "codex-relay",
            "--version", "0.0.0", "--no-registry", "--author", "Synthetic fixture")
        unchanged(original)

        # Existing user text before AND after every native block survives regeneration.
        for name in AGENTS:
            (project / name).write_bytes(b"Synthetic human prefix\n" + original[name] + b"Human suffix\n")
        overlays = {name: (project / name).read_bytes() for name in AGENTS}
        run(project, "overlay-regeneration", "reinstall", ".", "--assume-yes")
        unchanged(overlays)
        for name in AGENTS:
            (project / name).write_bytes(original[name])

        # File traversal detects missing INDEX even though upstream check accepts it.
        (project / BOOT / "INDEX.md").unlink()
        try:
            check_project(project)
        except FileNotFoundError:
            pass
        else:
            raise RuntimeError("Missing INDEX was not detected")
        run(project, "missing-index-upstream-check", "check", "--path", ".")
        (project / "GEMINI.md").unlink()
        run(project, "repair-generated-files", "reinstall", ".", "--assume-yes")
        unchanged(original)
        check_project(project)

        for label, data in [("duplicate-block", original["AGENTS.md"] + managed(original["AGENTS.md"])[0]),
                            ("unclosed-block", b"Human-owned text\n<vibevm>\n")]:
            (project / "AGENTS.md").write_bytes(data)
            before = {name: (project / name).read_bytes() for name in original}
            run(project, label, "reinstall", ".", "--assume-yes", collision=True)
            unchanged(before)
        (project / "AGENTS.md").write_bytes(original["AGENTS.md"])
        unchanged(original)
        print(json.dumps({"tool_probe": "PASS", "version": version, "boot_bytes": boot_bytes,
                          "offline_file_reads": "PASS", "exact_regeneration": "PASS",
                          "overlays_and_collisions": "PASS", "missing_index": "detected; upstream check misses it",
                          "model_behavior": "UNVERIFIED: no Codex/provider execution", "reports": reports}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vibe", type=Path, help="hash-pinned Linux x86_64 musl v1.0.7 binary")
    args = parser.parse_args()
    size = check_project(ROOT)
    print(json.dumps({"dependency_free_route": "PASS", "boot_bytes": size,
                      "tool_probe": "pending" if args.vibe else "not requested",
                      "model_behavior": "UNVERIFIED"}))
    if args.vibe:
        pin = json.loads((ROOT / "toolchain/vibevm.json").read_text())
        probe(args.vibe.resolve(), pin)


if __name__ == "__main__":
    main()
