"""Scan tracked repository bytes for credential or private-key markers."""

import os
import pathlib
import re
import subprocess
import sys


MARKER = re.compile(
    rb"(github_pat_[A-Za-z0-9_]{30,}|gh[pousr]_[A-Za-z0-9_]{20,}|"
    rb"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    rb"x-access-token:gh[pousr]_[A-Za-z0-9_]{20,})"
)


def tracked_paths():
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        check=True,
        stdout=subprocess.PIPE,
    )
    return [os.fsdecode(raw) for raw in result.stdout.split(b"\0") if raw]


def main():
    findings = []
    for raw_path in tracked_paths():
        path = pathlib.Path(raw_path)
        if MARKER.search(path.read_bytes()):
            findings.append(path.as_posix())
    if findings:
        print(
            "SECRET_SCAN_FAILED in tracked paths: " + ", ".join(findings)
        )
        return 1
    print("SECRET_SCAN_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
