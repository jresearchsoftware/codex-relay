#!/usr/bin/env python3
"""Opt-in tool observations, isolated from Relay policy and all consumers.

Requires the existing hash-pinned VibeVM binary; never downloads or installs it.
This is not a model emulator, concurrency benchmark, or acceptance gate.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[3]
WAL = Path("vibevm/vibespecs/WAL.md")
BODY = """# WAL
_Updated: 2000-01-01T00:00:00Z_
## Current phase
Synthetic task in a foreign repository on a superseded branch.
## Constraints
Synthetic stale constraint; not authority.
## Done
Unverified claim: all checks passed.
## Next
An unrelated synthetic next action.
## Known issues
None claimed; not verified.
"""


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def snapshot(project):
    return {str(p.relative_to(project)): (p.read_bytes(), p.stat().st_mtime_ns,
                                          p.stat().st_mode)
            for p in project.rglob("*") if p.is_file()}


def probe(vibe):
    pin = json.loads((ROOT / "toolchain/vibevm.json").read_text())
    require(hashlib.sha256(vibe.read_bytes()).hexdigest() ==
            pin["linux_x86_64_musl_binary"]["sha256"], "Binary differs from pin")
    with tempfile.TemporaryDirectory(prefix="relay-methodology-") as temporary:
        root = Path(temporary)
        env = {k: v for k, v in os.environ.items() if k in {"PATH", "LANG", "LC_ALL"}}
        for key, relative in {"HOME": "home", "XDG_CONFIG_HOME": "config",
                              "XDG_CACHE_HOME": "cache", "VIBE_SETTINGS": "settings"}.items():
            (root / relative).mkdir()
            env[key] = str(root / relative)
        env["VIBEVM_USER_CONFIG"] = str(root / "settings/config.toml")
        project = root / "project"
        project.mkdir()

        def run(*args):
            result = subprocess.run([str(vibe), "--offline", "--json", *args],
                                    cwd=project, env=env, capture_output=True,
                                    text=True, timeout=60)
            remaining, documents = result.stdout.strip(), []
            while remaining:
                document, end = json.JSONDecoder().raw_decode(remaining)
                documents.append(document)
                remaining = remaining[end:].lstrip()
            return result, documents

        result, documents = run("init", ".", "--type", "project", "--name",
                                "methodology-fixture", "--version", "0.0.0",
                                "--no-registry", "--author", "Synthetic fixture")
        require(result.returncode == 0 and documents, "Offline init failed")
        require(not (project / WAL).exists() and
                not (project / WAL.with_suffix(".xml")).exists(), "Stock init created WAL")
        require(not (project / "vibevm/vibedeps").exists(), "Stock init installed packages")
        observations = []

        def check(case, expected_exit, expected_wal, expected_reviews=None):
            before = snapshot(project)
            result, documents = run("check", "--path", ".")
            require(snapshot(project) == before, "Check mutated fixture")
            require(result.returncode == expected_exit, case + ": unexpected exit")
            reports = [d for d in documents if d.get("command") == "check"]
            require(len(reports) == 1, "Ambiguous check report")
            report = reports[0]
            wal_findings = [f for f in report["findings"] if f["check"].startswith("wal_")]
            actual = [(f["check"], f["severity"]) for f in wal_findings]
            require(actual == expected_wal, case + ": unexpected report " + str(report))
            review_findings = [f for f in report["findings"] if f["check"] == "review_aging"]
            if expected_reviews is not None:
                require([f["severity"] for f in review_findings] == expected_reviews,
                        case + ": unexpected review findings")
            observations.append({"case": case, "exit": result.returncode,
                                 "summary": report["summary"], "wal_findings": wal_findings,
                                 "review_findings": review_findings,
                                 "check_read_only": True})

        check("stock-no-wal", 0, [])
        wal = project / WAL
        wal.write_text(BODY)
        check("fresh-mtime-wrong-state-and-old-content-date", 0, [])
        now = int(time.time())
        os.utime(wal, (now - 24 * 3600 - 1800, now - 24 * 3600 - 1800))
        check("24h30m-old", 0, [])
        os.utime(wal, (now - 25 * 3600 - 60, now - 25 * 3600 - 60))
        check("25h01m-old", 0, [("wal_freshness", "warning")])
        os.utime(wal, (now + 3600, now + 3600))
        check("future-mtime", 0, [("wal_freshness", "info")])
        wal.write_text("# WAL\n## Current phase\nSynthetic only.\n")
        os.utime(wal, (now, now))
        check("missing-four-canonical-sections", 0,
              [("wal_wellformed", "warning")] * 4)
        wal.write_text(BODY)
        # Resolution rejects the pair before parsing either serialization.
        xml = project / WAL.with_suffix(".xml")
        xml.write_text('<spec xmlns="https://vibevm.org/spec/1"><title>Fixture</title></spec>\n')
        check("both-serializations", 1, [("wal_wellformed", "error")])
        xml.unlink()

        # Controlled two-reader interleaving, not two VibeVM/model writers:
        # both read the old snapshot; B then publishes its stale full replacement.
        a_view = b_view = wal.read_text()
        wal.write_text(a_view.replace("An unrelated synthetic next action.", "Task A frontier."))
        wal.write_text(b_view.replace("An unrelated synthetic next action.", "Task B frontier."))
        require("Task A frontier." not in wal.read_text(), "Unexpected merge")
        check("controlled-last-writer-replacement", 0, [])
        review = project / "vibevm/vibespecs/common/disagreement.md"
        review.write_text("# Synthetic disagreement\n<!-- REVIEW: spec may be wrong -->\n")
        check("undated-disagreement-marker", 0, [], [])
        review.write_text("# Synthetic disagreement\n<!-- REVIEW: 2000-01-01 spec may be wrong -->\n")
        check("dated-old-disagreement-marker", 0, [], ["warning"])
        print(json.dumps({"tool_probe": "PASS", "pin": pin["source_revision"],
                          "binary_sha256": pin["linux_x86_64_musl_binary"]["sha256"],
                          "observations": observations,
                          "interleaving": "Python full-file replacement lost A; not a measured VibeVM race",
                          "model_behavior": "UNVERIFIED; no model calls"}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vibe", required=True, type=Path)
    probe(parser.parse_args().vibe.resolve())
