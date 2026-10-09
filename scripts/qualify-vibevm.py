#!/usr/bin/env python3
"""Opt-in, disposable qualification of Relay's dependency-free VibeVM project."""
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


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def check_project(root):
    manifest = tomllib.loads((root / "vibe.toml").read_text())
    require(manifest == {"project": {"name": "codex-relay", "version": "0.0.0",
                                   "spec_format": "mixed"}},
            "Phase 1 must remain a project without requirements, registries or capabilities")
    lock = tomllib.loads((root / "vibe.lock").read_text())
    require(set(lock) == {"meta"} and set(lock["meta"]) == {
        "generated_by", "generated_at", "schema_version"}
        and lock["meta"]["generated_by"] == "vibe 1.0.7"
        and lock["meta"]["schema_version"] == 7, "Expected the empty v1.0.7 lock")
    index = tomllib.loads((root / BOOT / "INDEX.md").read_text())
    require(index == {"schema": 1}, "Phase 1 boot index must have no entries or static lane")
    require({p.name for p in (root / BOOT).iterdir()} == {"INDEX.md"},
            "Unexpected Phase 1 boot scaffolding")
    for name in AGENTS:
        path = root / name
        if path.exists():
            require(not re.search(rb"^\s*</?vibevm>\s*$", path.read_bytes(), re.M),
                    "Phase 1 does not add a VibeVM session redirect")
    require(not (root / "vibevm/vibedeps").exists(), "Phase 1 has no materialized packages")


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

        def run(label, *arguments):
            result = subprocess.run([str(vibe), "--offline", "--json", *arguments], cwd=root, env=env,
                                    text=True, capture_output=True, timeout=120)
            require(result.returncode == 0, label + " failed:\n" + result.stdout + result.stderr)
            # Lifecycle commands can emit several consecutive JSON envelopes.
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
        project, stock = root / "project", root / "stock-init"
        copy_tracked(project)
        check_project(project)
        agents_before = {name: (project / name).read_bytes() if (project / name).exists() else None
                         for name in AGENTS}
        stock.mkdir()
        for name in AGENTS:
            (stock / name).write_bytes(agents_before[name] or b"Human-owned overlay\n")
        run("init", "init", str(stock), "--type", "project", "--name", "codex-relay",
            "--version", "0.0.0", "--no-registry", "--author", "Synthetic fixture")
        for name in AGENTS:
            before = agents_before[name] or b"Human-owned overlay\n"
            after = (stock / name).read_bytes()
            separator = b"\n" if before.endswith(b"\n") else b"\n\n"
            require(after.startswith(before + separator + b"<vibevm>\n") and after.endswith(b"</vibevm>\n"),
                    "Initializer changed human-owned agent content: " + name)
        require(tomllib.loads((stock / "vibe.lock").read_text()).keys() == {"meta"},
                "Initializer unexpectedly locked packages")
        run("validate", "validate", "--path", str(project), "--no-default-registry")
        run("check", "check", "--path", str(project))
        for name, before in agents_before.items():
            require(((project / name).read_bytes() if (project / name).exists() else None) == before,
                    "Read-only checks changed an agent entrypoint: " + name)
        original = {name: (project / name).read_bytes() for name in
                    ("vibe.toml", "vibe.lock", str(BOOT / "INDEX.md"))}
        # Regeneration is exercised only here: upstream also writes stock session redirects.
        for count in range(2):
            run("reinstall-" + str(count + 1), "reinstall", str(project), "--assume-yes")
            for name, before in original.items():
                after = (project / name).read_bytes()
                if name == str(BOOT / "INDEX.md"):
                    # The upstream serializer adds a blank EOF line; Relay's diff check forbids it.
                    after = after.rstrip(b"\n") + b"\n"
                require(after == before, "Regeneration drifted: " + name)
        # Retain only the empty generated index, as in the real project. Absent blocks are supported.
        for name, before in agents_before.items():
            if before is None:
                (project / name).unlink()
            else:
                (project / name).write_bytes(before)
        (project / BOOT / ".vibe-boot-artifacts.lock").unlink(missing_ok=True)
        (project / BOOT / "INDEX.md").write_bytes(original[str(BOOT / "INDEX.md")])
        check_project(project)
        run("check-retained-scaffold", "check", "--path", str(project))
        print(json.dumps({"tool_probe": "PASS", "version": version, "reports": reports}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vibe", type=Path, help="hash-pinned Linux x86_64 musl v1.0.7 binary")
    args = parser.parse_args()
    check_project(ROOT)
    print(json.dumps({"dependency_free_scaffold": "PASS", "tool_probe": "pending" if args.vibe else "not requested"}))
    if args.vibe:
        pin = json.loads((ROOT / "toolchain/vibevm.json").read_text())
        probe(args.vibe.resolve(), pin)


if __name__ == "__main__":
    main()
