#!/usr/bin/env python3
"""Opt-in, offline tool-only routing experiments; never changes the checkout."""
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


def snapshot(project, include_state=False):
    return {str(p.relative_to(project)): p.read_bytes()
            for p in project.rglob("*") if p.is_file() and
            (include_state or not str(p.relative_to(project)).startswith(".vibe/")
             or p.relative_to(project) == Path(".vibe/.gitignore"))}


def entries(project):
    return tomllib.loads((project / BOOT / "INDEX.md").read_text()).get("entry", [])


def read_route(project):
    """Literal file reachability, NOT a Codex implementation or model oracle."""
    paths = []
    if (project / BOOT / "STATIC.md").exists():
        paths.append(str(BOOT / "STATIC.md"))
    for entry in entries(project):
        require(entry["kind"] == "static" and "when" not in entry,
                "This no-dependency fixture only measures unconditional direct reads")
        relative = Path(entry["path"])
        require(not relative.is_absolute() and ".." not in relative.parts,
                "Unexpected fixture path")
        paths.append(str(relative))
    return paths, sum(len((project / path).read_bytes()) for path in paths)


def probe(vibe):
    pin = json.loads((ROOT / "toolchain/vibevm.json").read_text())
    require(hashlib.sha256(vibe.read_bytes()).hexdigest() ==
            pin["linux_x86_64_musl_binary"]["sha256"], "Binary differs from pin")
    with tempfile.TemporaryDirectory(prefix="relay-routing-") as temporary:
        root = Path(temporary)
        env = {key: value for key, value in os.environ.items()
               if key in {"PATH", "LANG", "LC_ALL"}}
        for key, relative in {"HOME": "home", "XDG_CONFIG_HOME": "config",
                              "XDG_CACHE_HOME": "cache", "VIBE_SETTINGS": "settings"}.items():
            env[key] = str(root / relative)
            (root / relative).mkdir()
        env["VIBEVM_USER_CONFIG"] = str(root / "settings/config.toml")
        facts, commands = {}, []

        def run(project, *args, expected=0):
            result = subprocess.run([str(vibe), "--offline", "--json", *args],
                                    cwd=project, env=env, text=True,
                                    capture_output=True, timeout=120)
            require(result.returncode == expected,
                    str(args) + " failed: " + result.stdout + result.stderr)
            require(not result.stderr.strip(), "Unexpected diagnostics: " + result.stderr)
            remaining, documents = result.stdout.strip(), []
            while remaining:
                document, end = json.JSONDecoder().raw_decode(remaining)
                documents.append(document)
                remaining = remaining[end:].lstrip()
            require(documents, "No machine-readable result")
            require(not any(document.get("ok") is False for document in documents),
                    "Command reported failure: " + result.stdout)
            commands.append({"args": list(args), "exit": result.returncode,
                             "results": documents})
            return documents

        def init(project):
            return run(project, "init", ".", "--type", "project", "--name", "routing-fixture",
                       "--version", "0.0.0", "--no-registry", "--author", "Synthetic fixture")

        def reinstall(project):
            return run(project, "reinstall", ".", "--assume-yes")

        def check(project):
            return run(project, "check", "--path", ".")[-1]

        version = subprocess.check_output([str(vibe), "--version"], env=env, text=True).strip()
        require(version == "vibe " + pin["version"], "Wrong version")
        stock = root / "stock"
        stock.mkdir()
        init(stock)
        original = snapshot(stock)
        require(set(tomllib.loads((stock / "vibe.toml").read_text())) == {"project"},
                "Unexpected package or registry declaration")
        require(set(tomllib.loads((stock / "vibe.lock").read_text())) == {"meta"},
                "Unexpected locked package")
        require(not (stock / "vibevm/vibedeps").exists(), "Unexpected dependencies")
        require(not (stock / "vibevm/vibespecs/WAL.xml").exists() and
                not (stock / "vibevm/vibespecs/WAL.md").exists(), "Unexpected WAL")
        require(not (stock / BOOT / "STATIC.md").exists(), "Unexpected STATIC lane")
        route, size = read_route(stock)
        require(route == [str(BOOT / "00-core.md"), str(BOOT / "90-user.md")], "Wrong stock route")
        require(len({(stock / name).read_bytes() for name in AGENTS}) == 1, "Redirects differ")
        facts["stock"] = {"files": {p: len(data) for p, data in
                                    sorted(snapshot(stock, include_state=True).items())},
                          "directories": sorted(str(p.relative_to(stock)) for p in stock.rglob("*")
                                                if p.is_dir()),
                          "entrypoints_identical": True, "route": route,
                          "boot_bytes": size, "wal_created": False, "packages": 0}
        require(check(stock)["summary"] == {"error": 0, "warning": 0, "info": 0},
                "Stock linter findings")
        require(snapshot(stock, include_state=True) == original, "Check changed project")
        run(stock, "validate", "--path", ".", "--no-default-registry")
        require(snapshot(stock) == original, "Validate changed authored/generated prompt bytes")
        facts["validate_state_writes"] = sorted(set(snapshot(stock, include_state=True)) - set(original))
        init(stock)
        require(snapshot(stock) == original, "Repeated init drift")
        for _ in range(2):
            reinstall(stock)
            require(snapshot(stock) == original, "Repeated reinstall drift")
        facts["stock_check_and_regeneration"] = "identical prompt bytes; missing WAL accepted"

        empty = root / "empty-boot"
        shutil.copytree(stock, empty)
        for name in ("00-core.md", "90-user.md"):
            (empty / BOOT / name).unlink()
        reinstall(empty)
        require(read_route(empty) == ([], 0), "Empty authored boot acquired content")
        facts["empty_authored_boot"] = {"route": [], "boot_bytes": 0,
                                        "redirects_remain": all((empty / name).exists() for name in AGENTS)}

        # Human text and authored policy remain separate from generated redirects.
        bounded = root / "bounded"
        shutil.copytree(stock, bounded)
        # This historical comparison fixture starts without the now-active native block.
        relay_agents = re.sub(rb"^<vibevm>\n.*?^</vibevm>\n", b"",
                             (ROOT / "AGENTS.md").read_bytes(), flags=re.M | re.S).rstrip(b"\n") + b"\n"
        (bounded / "AGENTS.md").write_bytes(relay_agents)
        core = b"# Fixture authority\nRead the existing Relay AGENTS.md and admitted Request.\n"
        user = b"# Fixture overrides\nLoad component contracts only when relevant to the task.\n"
        (bounded / BOOT / "00-core.md").write_bytes(core)
        (bounded / BOOT / "90-user.md").write_bytes(user)
        (bounded / BOOT / "20-relevant.md").write_text("# Synthetic relevant task\nConsult common/relevant.md for routing changes.\n")
        (bounded / BOOT / "30-irrelevant.md").write_text("# Synthetic unrelated task\nConsult modules/irrelevant.md for arithmetic.\n")
        for relative, text in [("common/relevant.md", "# Routing fixture\nSynthetic routing detail.\n"),
                               ("modules/irrelevant.md", "# Arithmetic fixture\nSynthetic unrelated detail.\n")]:
            (bounded / "vibevm/vibespecs" / relative).write_text(text)
        init(bounded)
        require((bounded / "AGENTS.md").read_bytes().startswith(relay_agents + b"\n<vibevm>\n"),
                "Human AGENTS content changed")
        custom = snapshot(bounded)
        for _ in range(2):
            reinstall(bounded)
            require(snapshot(bounded) == custom, "Authored policy or redirect drift")
        require((bounded / BOOT / "00-core.md").read_bytes() == core and
                (bounded / BOOT / "90-user.md").read_bytes() == user, "Policy replaced")
        paths, size = read_route(bounded)
        require(paths == [str(BOOT / name) for name in
                          ("00-core.md", "20-relevant.md", "30-irrelevant.md", "90-user.md")],
                "Unexpected filename order")
        sample_tasks = ["Explain this project's routing conventions", "Compute 2 + 2"]
        task_routes = {task: read_route(bounded)[0] for task in sample_tasks}
        require(all(route == paths for route in task_routes.values()), "Task-sensitive tool routing")
        facts["bounded"] = {"route": paths, "boot_bytes": size, "human_agents_preserved": True,
                            "authored_policy_preserved": True,
                            "sample_task_file_routes": task_routes,
                            "detail_selection": "instructions only; not model-tested"}

        # Deleting an authored file is distinct from repairing generated files.
        (bounded / BOOT / "00-core.md").unlink()
        (bounded / BOOT / "INDEX.md").unlink()
        (bounded / "GEMINI.md").unlink()
        reinstall(bounded)
        require(not (bounded / BOOT / "00-core.md").exists(), "Reinstall recreated core")
        require((bounded / "GEMINI.md").exists() and (bounded / BOOT / "INDEX.md").exists(),
                "Generated files not repaired")
        require(str(BOOT / "00-core.md") not in read_route(bounded)[0], "Stale core entry")
        facts["missing_files"] = "reinstall repaired INDEX/redirect, did not recreate authored core"
        init(bounded)
        require((bounded / BOOT / "00-core.md").read_bytes() == (stock / BOOT / "00-core.md").read_bytes(),
                "Init did not recreate missing stock core")
        facts["init_after_core_removal"] = "restores stock core; omission is not durable across init"

        # Probe a stale route without interpreting it as a model fallback.
        stale = root / "stale"
        shutil.copytree(stock, stale)
        (stale / BOOT / "00-core.md").unlink()
        facts["stale_index_check"] = check(stale)

        run(stock, "clean", "--path", ".")
        require((stock / BOOT / "00-core.md").exists() and (stock / BOOT / "90-user.md").exists(),
                "Clean removed authored policy")
        require(not (stock / BOOT / "INDEX.md").exists(), "Clean retained generated index")
        require(all((stock / name).read_bytes() == original[name] for name in AGENTS),
                "Clean unexpectedly changed redirect")
        facts["clean_dangling_index_check"] = check(stock)
        require((stock / "vibe.lock").read_bytes() == original["vibe.lock"], "Clean changed lock")
        reinstall(stock)
        require(snapshot(stock) == original, "Clean/reinstall roundtrip drift")
        facts["clean_roundtrip"] = ("authored files/lock/redirects retained; INDEX removed, so route "
                                    "temporarily dangling; reinstall reproduced original prompt bytes")

        # A clone with committed prompt bytes needs no HOME/cache to be readable.
        clone = root / "clone"
        shutil.copytree(stock, clone, ignore=shutil.ignore_patterns(".vibe", ".vibe-boot-*"))
        require(read_route(clone) == read_route(stock), "Clone prompt content missing")
        facts["offline_clone_file_read"] = "same route and bytes with local state omitted"
        facts["model_behavior"] = "UNVERIFIED: no Codex/provider execution"
        print(json.dumps({"tool_probe": "PASS", "version": version,
                          "facts": facts, "commands": commands}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vibe", required=True, type=Path,
                        help="disposable hash-pinned Linux musl v1.0.7 binary; never downloaded here")
    args = parser.parse_args()
    probe(args.vibe.resolve())


if __name__ == "__main__":
    main()
