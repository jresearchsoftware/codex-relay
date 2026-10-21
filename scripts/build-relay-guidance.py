#!/usr/bin/env python3
"""Deterministic offline assembly; VibeVM owns package resolution and Skill projection."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "guidance/artifacts"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def inventory(directory):
    result = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Symlink in guidance input: {path}")
        if path.is_file():
            result[path.relative_to(directory).as_posix()] = path.read_bytes()
    return result


def assemble():
    metadata = json.loads((ROOT / "guidance/source.json").read_text())
    name = metadata["name"]
    slot = ROOT / "vibevm/vibedeps" / metadata["shared_coordinate"].replace("/", ".") / metadata["shared_version"]
    shared = inventory(slot)
    shared.pop(".vibe-slot.toml", None)
    # Match the pinned tool's native Linux tree recipe, not receipt payload hashing.
    tree = hashlib.sha256()
    for path in sorted(shared, key=lambda path: Path(path).parts):
        tree.update(path.encode() + b"\0" + shared[path] + b"\0")
    if "sha256:" + tree.hexdigest() != metadata["shared_distribution_tree_hash"]:
        raise ValueError("Shared distribution bytes differ from the selected immutable dependency")
    receipt = json.loads(shared["DISTRIBUTION.json"])
    # Complete bytes and producer identity are also checked by qualify-vibevm.py.
    if metadata["shared_source_revision"] not in json.dumps(receipt):
        raise ValueError("Shared accepted producer revision is missing from receipt")
    skill = inventory(ROOT / "packages/codex-relay/skill")
    if "SKILL.md" not in skill:
        raise ValueError("Missing canonical native Skill source")
    skill["LICENSE"] = (ROOT / "LICENSE").read_bytes()
    source_files = {"packages/codex-relay/skill/" + key: digest(value) for key, value in skill.items()}
    for path in ("contracts/src/github-authority-v4.json", "contracts/src/github-authority-v1.json",
                 "deploy/workflows/contract.json", "toolchain/vibevm.json"):
        # Read accepted Git blob bytes, independent of Windows checkout newline conversion.
        data = subprocess.check_output(["git", "show", metadata["contract_revision"] + ":" + path], cwd=ROOT)
        skill["references/product/" + Path(path).name] = data
        source_files[path] = digest(data)
    workflow = json.loads(skill["references/product/contract.json"])
    if (metadata["workflow_contract"] != workflow["parallelWorkflowContract"] or
            metadata["serial_workflow_contract"] != workflow["workflowContract"]):
        raise ValueError("Workflow pins differ from the selected accepted Relay contract")
    # Exact vendoring is generated, attributed and never an independently edited policy fork.
    skill.update({"references/shared/" + path: data for path, data in shared.items()})
    installer = (ROOT / "guidance/project.py").read_bytes()
    skill["scripts/project.py"] = installer
    source_files["guidance/project.py"] = digest(installer)
    source_files["guidance/source.json"] = digest((ROOT / "guidance/source.json").read_bytes())
    source_files["scripts/build-relay-guidance.py"] = digest(Path(__file__).read_bytes())
    provenance = {
        **metadata,
        "generator": "scripts/build-relay-guidance.py",
        "source_files": source_files,
        "files": {path: digest(data) for path, data in sorted(skill.items())},
    }
    skill["PROVENANCE.json"] = json_bytes(provenance)
    expected = {"standalone/" + name + "/" + path: data for path, data in skill.items()}
    expected.update({"vpm/skill/" + path: data for path, data in skill.items()})
    expected["vpm/vibe.toml"] = f'''# Generated from guidance/source.json; candidate content, no external publication.
[package]
group = "org.jresearch.ai"
name = "{name}"
version = "{metadata['version']}"
kind = "flow"
frozen = true
license = "MIT"
epoch = 1
description = "Version-bound Codex Relay workflow Skill with offline shared references"

[boot_snippet]
source = "vibevm/vibespecs/boot/codex-relay.md"
category = "flow"
link = "dynamic"

[requires.packages]
"{metadata['shared_coordinate']}" = "={metadata['shared_version']}"

[[skill]]
name = "{name}"
path = "skill"
agents = ["codex"]
include = ["SKILL.md", "LICENSE", "PROVENANCE.json", "references/**", "scripts/**"]
'''.encode()
    expected["vpm/vibevm/vibespecs/boot/codex-relay.md"] = b'''# Codex Relay product guidance

For Relay Task authoring, execution, results, review or continuation, read the
versioned [Codex Relay Skill](../../../skill/SKILL.md) and only its relevant
references. Unrelated work skips it. This route grants no execution, publication,
review, merge, closure or deployment authority; preserve local instructions and
the live Task's admitted authority.

When changing or reviewing this producer's own guidance, use the independently
accepted main guidance frozen before reading candidate routes. Candidate Skill,
boot and AGENTS changes are proposals until independently accepted.
'''
    expected["vpm-consumer.toml.in"] = f'''# Generated example. Review and replace only the Relay distribution URL/revision.
# VibeVM 1.0.7 needs both explicit Git source roots; transitive Git tables are ignored.
[project]
name = "relay-guidance-consumer"
version = "0.0.0"
spec_format = "mixed"

[requires.packages]
"org.jresearch.ai/{name}" = {{ version = "={metadata['version']}", git = "REPLACE_WITH_SELECTED_RELAY_DISTRIBUTION_GIT_URL", rev = "REPLACE_WITH_IMMUTABLE_RELAY_DISTRIBUTION_COMMIT", auth = "none" }}
"{metadata['shared_coordinate']}" = {{ version = "={metadata['shared_version']}", git = "https://github.com/jrs-vibevm/org.jresearch.ai.development-governance.git", rev = "{metadata['shared_distribution_revision']}", auth = "none" }}
'''.encode()
    expected.update({"vpm/" + path: data for path, data in inventory(ROOT / "guidance/dependency-closure").items()})
    expected["vpm/LICENSES.json"] = (ROOT / "guidance/licenses.json").read_bytes()
    expected["vpm/LICENSE"] = (ROOT / "LICENSE").read_bytes()
    expected["vpm/README.md"] = f'''# Codex Relay {metadata['version']} guidance package

Generated source candidate for `org.jresearch.ai/{name}`. It describes accepted
Relay contract `{metadata['contract_revision']}` with the exact pinned shared
dependency. `skill/PROVENANCE.json` binds every projected byte and authoring input.
Acceptance, package publication and consumer adoption remain separate.

Acquire this package by an explicitly selected immutable revision through the
supported VibeVM 1.0.7 package interface. The generated sibling
`vpm-consumer.toml.in` shows both required immutable Git source roots; the native
package declares the shared version edge, while 1.0.7 ignores transitive Git
source tables. Then explicitly project its Skill with
`vibe skill install --skill codex-relay --agent codex --scope project --yes`.
Ordinary Codex use reads the resulting files offline. See the source repository's
`docs/relay-guidance.md` for install, drift, update, rollback and removal evidence.
'''.encode()
    return expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="compare committed artifacts without writing")
    args = parser.parse_args()
    expected = assemble()
    actual = inventory(OUTPUT) if OUTPUT.exists() else {}
    changed = sorted(path for path in set(actual) | set(expected) if actual.get(path) != expected.get(path))
    if args.check:
        print(json.dumps({"guidance": "FAIL" if changed else "PASS", "changed": changed, "files": len(expected)}))
        return bool(changed)
    # This command only owns generated artifacts, never consumer or authoring input files.
    for path in set(actual) - set(expected):
        (OUTPUT / path).unlink()
    for path, data in expected.items():
        target = OUTPUT / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    print(json.dumps({"guidance": "GENERATED", "files": len(expected), "changed": changed}))
    return False


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
