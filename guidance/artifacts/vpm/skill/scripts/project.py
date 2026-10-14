#!/usr/bin/env python3
"""Plan or apply a local standalone Relay Skill projection. Python 3.11+, no network."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import sys

RECEIPT = ".relay-guidance-installation.json"
START = b"<!-- codex-relay-guidance:start -->"
END = b"<!-- codex-relay-guidance:end -->"
BLOCK = START + b"\nFor Relay Task, Decision, Change Request, Outcome or independent review work,\nuse `.agents/skills/codex-relay/SKILL.md` and load its references as needed.\nLive project authority and local overlays retain their precedence; installing\nthis guidance grants no execution, publication, approval, merge or closure rights.\n" + END


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def ordinary(path):
    """Refuse link/reparse traversal before reading or replacing an owned file."""
    path = path.absolute()
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError(f"Link in projection path: {part}")
        if part.exists():
            info = part.lstat()
            if getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError(f"Reparse point in projection path: {part}")
            if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                raise ValueError(f"Non-regular projection path: {part}")
    return path


def relative(name):
    path = PurePosixPath(name)
    if (not name or path.is_absolute() or any(part in ("", ".", "..") for part in name.split("/"))
            or "\\" in name or ":" in name):
        raise ValueError(f"Unsafe manifest path: {name}")
    return Path(*path.parts)


def manifest_files(root):
    ordinary(root)
    manifest = ordinary(root / "PROVENANCE.json").read_bytes()
    info = json.loads(manifest)
    if info.get("schema_version") != 1 or info.get("name") != "codex-relay":
        raise ValueError("Unsupported guidance provenance")
    files, folded = {}, set()
    for name, expected in info["files"].items():
        if name.casefold() in folded or name in ("PROVENANCE.json", RECEIPT):
            raise ValueError("Colliding manifest paths")
        folded.add(name.casefold())
        data = ordinary(root / relative(name)).read_bytes()
        if sha(data) != expected:
            raise ValueError(f"Guidance source drift: {name}")
        files[name] = data
    if "SKILL.md" not in files or "scripts/project.py" not in files:
        raise ValueError("Incomplete standalone guidance")
    files["PROVENANCE.json"] = manifest
    return info, files


def owned_files(destination):
    receipt_path = ordinary(destination / RECEIPT)
    if not receipt_path.exists():
        if destination.exists():
            raise ValueError("Foreign Skill collision: target has no standalone ownership receipt")
        return None
    receipt = json.loads(receipt_path.read_bytes())
    if receipt.get("schema_version") != 1:
        raise ValueError("Unsupported standalone ownership receipt")
    if not isinstance(receipt.get("bootstrap"), bool) or not isinstance(receipt.get("agents_existed"), bool):
        raise ValueError("Malformed standalone ownership receipt")
    suffix = bytes.fromhex(receipt["bootstrap_suffix_hex"])
    if receipt["bootstrap"] and suffix not in (BLOCK + b"\n", b"\n" + BLOCK + b"\n", b"\n\n" + BLOCK + b"\n"):
        raise ValueError("Malformed bootstrap ownership suffix")
    if not receipt["bootstrap"] and suffix:
        raise ValueError("Unexpected bootstrap ownership suffix")
    folded = set()
    for name, expected in receipt["files"].items():
        if name.casefold() in folded or name == RECEIPT:
            raise ValueError("Colliding installation receipt paths")
        folded.add(name.casefold())
        path = ordinary(destination / relative(name))
        if not path.is_file() or sha(path.read_bytes()) != expected:
            raise ValueError(f"Managed drift: {name}; preserve edits and reconcile before updating/removing")
    return receipt


def bootstrap(data, old, enabled, removing):
    starts, ends = data.count(START), data.count(END)
    expected = old.get("bootstrap", False) if old else False
    if starts != ends or starts > 1:
        raise ValueError("Malformed or colliding AGENTS guidance block")
    if expected:
        if starts != 1:
            raise ValueError("Managed AGENTS block is missing")
        begin, finish = data.index(START), data.index(END) + len(END)
        if data[begin:finish] != BLOCK:
            raise ValueError("Managed AGENTS block drift; preserve local changes")
        if removing:
            # Receipt keeps the exact append suffix, preserving arbitrary user text elsewhere.
            suffix = bytes.fromhex(old["bootstrap_suffix_hex"])
            if data.endswith(suffix):
                return data[:-len(suffix)]
            return data[:begin] + data[finish:]
        return data
    if starts:
        raise ValueError("Foreign AGENTS guidance block; reconcile ownership explicitly")
    if enabled and not removing:
        separator = b"" if not data else (b"\n" if data.endswith(b"\n") else b"\n\n")
        return data + separator + BLOCK + b"\n"
    return data


def duplicate_names(target, destination):
    for base in (target / ".agents/skills", target / ".codex/skills"):
        ordinary(base)
        if not base.exists():
            continue
        for folder in base.iterdir():
            if folder == destination or not folder.is_dir():
                continue
            skill = ordinary(folder / "SKILL.md")
            if not skill.exists():
                continue
            text = skill.read_text(encoding="utf-8")
            match = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)", text, re.S)
            if match:
                # Read a single-line YAML scalar, including its optional trailing comment.
                # Codex owns general YAML parsing; this dependency-free check covers the
                # ordinary plain/quoted scalar name forms used by native Skill authors.
                name = re.search(r"^name:[ \t]*(.*)$", match.group(1), re.M)
                if name:
                    scalar = name.group(1).strip()
                    if scalar.startswith('"'):
                        token = re.match(r'"(?:[^"\\]|\\.)*"', scalar)
                        value = json.loads(token.group()) if token else None
                    elif scalar.startswith("'"):
                        token = re.match(r"'(?:[^']|'')*'", scalar)
                        value = token.group()[1:-1].replace("''", "'") if token else None
                    else:
                        value = re.split(r"[ \t]+#", scalar, maxsplit=1)[0].strip()
                    if value == "codex-relay":
                        raise ValueError(f"Duplicate codex-relay Skill name: {skill}; reconcile local ownership")


def run(args):
    target = ordinary(Path(args.target))
    if not target.is_dir():
        raise ValueError("Target repository directory must already exist")
    destination = ordinary(target / ".agents/skills/codex-relay")
    old = owned_files(destination)
    if args.command == "remove" and old is None:
        raise ValueError("No standalone installation to remove")
    files, info = {}, None
    if args.command != "remove":
        info, files = manifest_files(ordinary(Path(args.source)))
        duplicate_names(target, destination)
    changes = {}
    for name in set(old["files"] if old else {}) | set(files):
        path = ordinary(destination / relative(name))
        if path.exists() and name not in (old["files"] if old else {}):
            raise ValueError(f"New managed path collides with local content: {name}")
        before = path.read_bytes() if path.exists() else None
        after = files.get(name)
        if before != after:
            changes[path] = (before, after)
    old_names = {name.casefold(): name for name in old["files"]} if old else {}
    if any(name.casefold() in old_names and old_names[name.casefold()] != name for name in files):
        raise ValueError("Case-only managed rename needs explicit local reconciliation")
    agents = ordinary(target / "AGENTS.md")
    agents_before = agents.read_bytes() if agents.exists() else b""
    enabled = args.bootstrap or bool(old and old.get("bootstrap"))
    agents_after = bootstrap(agents_before, old, enabled, args.command == "remove")
    if agents_after != agents_before:
        changes[agents] = (agents_before if agents.exists() else None,
                           agents_after if agents_after or (old and old.get("agents_existed", True)) else None)
    receipt_path = destination / RECEIPT
    receipt = None
    if args.command != "remove":
        receipt = {
            "schema_version": 1, "version": info["version"],
            "files": {name: sha(data) for name, data in sorted(files.items())},
            "bootstrap": enabled,
            "agents_existed": old["agents_existed"] if old else agents.exists(),
            "bootstrap_suffix_hex": old["bootstrap_suffix_hex"] if old and old.get("bootstrap") else
                (agents_after[len(agents_before):].hex() if enabled else ""),
        }
    before_receipt = receipt_path.read_bytes() if receipt_path.exists() else None
    after_receipt = encoded(receipt) if receipt else None
    if before_receipt != after_receipt:
        changes[receipt_path] = (before_receipt, after_receipt)
    if args.diff:
        for path, (before, after) in sorted(changes.items()):
            try:
                print("".join(difflib.unified_diff((before or b"").decode().splitlines(True),
                      (after or b"").decode().splitlines(True),
                      fromfile=str(path) + " (before)", tofile=str(path) + " (after)")), end="")
            except UnicodeDecodeError:
                print(f"Binary change: {path}")
    print(json.dumps({"action": args.command, "apply": args.apply,
                      "version": info["version"] if info else old["version"],
                      "changes": [path.relative_to(target).as_posix() for path in sorted(changes)]}))
    if args.apply:
        # Validate everything before the first write; interrupted application remains visibly drifted.
        for path, (_, data) in sorted(changes.items(), key=lambda item: (item[0] == receipt_path, item[0])):
            if data is None:
                path.unlink()
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
        # Remove empty owned directories only; added local content and neighboring Skills survive.
        if destination.exists():
            directories = sorted((path for path in destination.rglob("*") if path.is_dir() and not path.is_symlink()),
                                 key=lambda path: len(path.parts), reverse=True)
            for path in [*directories, destination]:
                if path.is_dir() and not any(path.iterdir()):
                    path.rmdir()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("install", "remove"))
    parser.add_argument("--source", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--target", required=True)
    parser.add_argument("--bootstrap", action="store_true", help="append the small owned AGENTS routing block")
    parser.add_argument("--diff", action="store_true", help="show the complete reviewable text diff")
    parser.add_argument("--apply", action="store_true", help="apply the planned local changes")
    args = parser.parse_args()
    try:
        run(args)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
