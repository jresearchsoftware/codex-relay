#!/usr/bin/env python3
"""Fail-closed validator for the pinned GitHub Actions Runner archive."""

import pathlib
import posixpath
import sys
import tarfile


REQUIRED = {"config.sh", "run.sh", "bin/Runner.Listener"}
INSTANCE_STATE = {".runner", ".credentials", ".credentials_rsaparams", ".service", ".env", ".path", "_diag", "_work"}


def fail(code):
    print(f"RUNNER_ARCHIVE_INVALID code={code}")
    raise SystemExit(1)


def main():
    if len(sys.argv) != 3:
        fail("ARGUMENTS")
    archive = pathlib.Path(sys.argv[1])
    if sys.argv[2] != "2.336.0":
        fail("VERSION_CONTRACT")
    try:
        with tarfile.open(archive, "r:gz") as handle:
            members = handle.getmembers()
            names = set()
            normalized_members = []
            for member in members:
                name = member.name
                normalized = posixpath.normpath(name)
                if normalized == ".":
                    continue
                if not name or name.startswith("/") or normalized == ".." or normalized.startswith("../"):
                    fail("UNSAFE_MEMBER_PATH")
                if normalized in names:
                    fail("DUPLICATE_MEMBER")
                if normalized.split('/')[0] in INSTANCE_STATE:
                    fail("INSTANCE_STATE_IN_PACKAGE")
                names.add(normalized)
                if member.islnk():
                    fail("HARDLINK_MEMBER")
                if not (member.isfile() or member.isdir() or member.issym()):
                    fail("UNEXPECTED_MEMBER_TYPE")
                normalized_members.append((member, normalized))
            for member, normalized in normalized_members:
                if member.issym():
                    if not member.linkname or member.linkname.startswith("/"):
                        fail("UNSAFE_LINK_TARGET")
                    target = posixpath.normpath(posixpath.join(posixpath.dirname(normalized), member.linkname))
                    if target == ".." or target.startswith("../") or target not in names:
                        fail("UNSAFE_LINK_TARGET")
                if normalized in REQUIRED and (not member.isfile() or not member.mode & 0o111):
                    fail("REQUIRED_ENTRYPOINT_NOT_EXECUTABLE")
            if not REQUIRED.issubset(names):
                fail("REQUIRED_ENTRYPOINT_MISSING")
    except (OSError, tarfile.TarError):
        fail("MALFORMED_ARCHIVE")
    print("RUNNER_ARCHIVE_VALID version=2.336.0 platform=linux-x64")


if __name__ == "__main__":
    main()
