#!/usr/bin/env python3
"""Stage/check generated native registry inputs; VibeVM owns resolution/projection.

This is deliberate source maintenance, never a startup/bootstrap operation. It
copies the existing deterministic first-party package export into the ordinary
in-tree VibeVM registry. The exact Shared Governance Git root stays unchanged.
No network, Git configuration,
client settings, package selection, or external publication is performed.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = Path("vibevm/vibepacks")
SELF_COORDINATE = "org.jresearch.ai/codex-relay"
SELF_VERSION = "3.1.1"
SELF_SOURCE = REGISTRY / SELF_COORDINATE / ("v" + SELF_VERSION)
SELF_SLOT = Path("vibevm/vibedeps/org.jresearch.ai.codex-relay") / SELF_VERSION
PROJECTION = Path(".agents/skills/codex-relay")
SKILL_RECEIPT = Path(".agents/skills/.codex-relay.vibe-skill-receipt.toml")


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"),
                                                Path(__file__).with_name(name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def expected(root=ROOT):
    qualification = load("qualify-vibevm")
    metadata = json.loads(qualification.read_file(root, "guidance/source.json"))
    qualification.require(metadata["name"] == "codex-relay" and metadata["version"] == SELF_VERSION,
                          "Self-adoption requires the owner-selected first-party " + SELF_VERSION + " identity")
    qualification.check_package(root / qualification.SLOT)
    artifact = qualification.files_in(root / "guidance/artifacts/vpm")
    qualification.require(artifact, "Build Relay guidance artifacts before native source staging")
    return {SELF_SOURCE: artifact}


def stage(root=ROOT, check=False):
    qualification = load("qualify-vibevm")
    packages = expected(root)
    expected_files = {str(package.relative_to(REGISTRY) / name): data
                      for package, files in packages.items() for name, data in files.items()}
    if check:
        qualification.check_first_party_registry(root, packages[SELF_SOURCE])
        return {"native_registry": "PASS", "files": len(expected_files)}
    # Do not delete unknown files or version history to make a candidate pass.
    # Repeated edits of this unpublished candidate may replace known export files.
    for package, files in packages.items():
        target = root / package
        qualification.require(not target.is_symlink(), "Native registry target is a symlink")
        for ancestor in target.parents:
            qualification.require(not ancestor.is_symlink(), "Native registry parent is a symlink")
            if ancestor == root:
                break
        if target.exists():
            actual = qualification.files_in(target)
            qualification.require(set(actual) <= set(files),
                                  "Preserve unexpected native registry content for diagnosis")
    for package, files in packages.items():
        for name, data in files.items():
            target = root / package / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists() or target.read_bytes() != data:
                target.write_bytes(data)
    return {"native_registry": "STAGED", "files": len(expected_files),
            "next": "Use pinned native install without --registry, then project the Codex project Skill"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="compare generated registry inputs without writing")
    args = parser.parse_args()
    try:
        print(json.dumps(stage(check=args.check), sort_keys=True))
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
