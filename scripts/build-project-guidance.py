#!/usr/bin/env python3
"""Run the unchanged delivery builder independently of the project's Shared slot.

Relay 4.1.0 records the delivery builder's exact bytes in its provenance. Keep
that builder unchanged and supply its pinned Shared snapshot from the frozen
publisher closure in an isolated build root. The project's native dependency
graph and the generated delivery artifacts retain their separate identities.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def inventory(directory):
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError(f"Expected ordinary guidance directory: {directory}")
    files = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Symlink in guidance input: {path}")
        if path.is_file():
            files[path.relative_to(directory).as_posix()] = path.read_bytes()
        elif not path.is_dir():
            raise ValueError(f"Non-ordinary guidance input: {path}")
    return files


def read_file(root, relative):
    path = root
    for part in Path(relative).parts:
        path /= part
        if path.is_symlink():
            raise ValueError(f"Symlink in guidance input: {path}")
    if not path.is_file():
        raise ValueError(f"Missing ordinary guidance input: {path}")
    return path.read_bytes()


def materialize(files, destination):
    for name, data in files.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def assemble(root=ROOT):
    metadata = json.loads(read_file(root, "guidance/source.json"))
    slot = (Path("vibevm/vibedeps") / metadata["shared_coordinate"].replace("/", ".")
            / metadata["shared_version"])
    inputs = {name: read_file(root, name) for name in (
        "scripts/build-relay-guidance.py", "guidance/source.json", "guidance/project.py",
        "guidance/licenses.json", "LICENSE")}
    for relative in ("packages/codex-relay/skill", "guidance/dependency-closure"):
        inputs.update({str(Path(relative) / name): data
                       for name, data in inventory(root / relative).items()})
    inputs.update({str(slot / name): data for name, data in
                   inventory(root / "guidance/dependency-closure" / slot).items()})
    storage = root / ".vibe"
    if storage.is_symlink():
        raise ValueError(f"Symlink in guidance build storage: {storage}")
    storage.mkdir(exist_ok=True)
    # Stay inside the checkout so the unchanged builder's accepted Git-blob
    # reads discover the real repository without copying or modifying Git state.
    with tempfile.TemporaryDirectory(prefix="relay-guidance-build-", dir=storage) as temporary:
        fixture = Path(temporary)
        materialize(inputs, fixture)
        result = subprocess.run([sys.executable, str(fixture / "scripts/build-relay-guidance.py")],
                                cwd=fixture, capture_output=True, text=True)
        if result.returncode:
            raise ValueError("Frozen delivery builder failed:\n" + result.stdout + result.stderr)
        return inventory(fixture / "guidance/artifacts")


def build(root=ROOT, check=False):
    expected = assemble(root)
    output = root / "guidance/artifacts"
    actual = inventory(output) if output.exists() else {}
    changed = sorted(name for name in actual.keys() | expected.keys()
                     if actual.get(name) != expected.get(name))
    if not check:
        unknown = sorted(actual.keys() - expected.keys())
        if unknown:
            raise ValueError("Preserve unexpected guidance artifacts: " + ", ".join(unknown))
        materialize({name: expected[name] for name in changed}, output)
    return {"guidance": ("FAIL" if changed else "PASS") if check else "GENERATED",
            "changed": changed, "files": len(expected)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="compare committed artifacts without writing")
    args = parser.parse_args()
    try:
        report = build(check=args.check)
        print(json.dumps(report))
        return args.check and bool(report["changed"])
    except (ValueError, OSError, KeyError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
