#!/usr/bin/env python3
"""Opt-in, credential-free proof of the pinned native Codex filesystem sandbox.

Only disposable fixtures are written. This invokes `codex sandbox`, never a
provider or model, and does not qualify Relay's launcher or outer isolation.
"""

import argparse
import errno
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
PIN = ROOT / "deploy/ansible/group_vars/all.yml"
KINDS = ("ordinary", "git", "root_agents", "nested_fixture_agents")
PROBE = r'''
import errno
import json
import os
from pathlib import Path
import re

root = Path.cwd()

def mount_category(relative):
    target = str(root / relative)
    selected = None
    try:
        lines = Path("/proc/self/mountinfo").read_text().splitlines()
    except OSError:
        return "unavailable"
    for line in lines:
        fields = line.split(" - ", 1)[0].split()
        if len(fields) < 6:
            continue
        mount = re.sub(r"\\([0-7]{3})", lambda match: chr(int(match[1], 8)), fields[4])
        if target == mount or target.startswith(mount.rstrip("/") + "/"):
            if selected is None or len(mount) > len(selected[0]):
                selected = (mount, fields[5].split(","))
    if selected is None:
        return "unavailable"
    mount, options = selected
    scope = ("root-agents" if mount == str(root / ".agents") else
             "git" if mount == str(root / ".git") else
             "workspace" if mount == str(root) else
             "workspace-subpath" if mount.startswith(str(root) + "/") else "ancestor")
    access = "ro" if "ro" in options else "rw" if "rw" in options else "unknown"
    return scope + ":" + access

results = {}
for kind, relative in {
    "ordinary": "ordinary.txt",
    "git": ".git/probe",
    "root_agents": ".agents/skills/probe/SKILL.md",
    "nested_fixture_agents": "nested-fixture/.agents/skills/probe/SKILL.md",
}.items():
    path = root / relative
    operation = "mkdir"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        operation = "open-write"
        path.write_bytes(b"synthetic filesystem qualification\n")
        observed = {"result": "writable", "errno": None, "operation": operation}
    except OSError as error:
        observed = {"result": "denied", "errno": errno.errorcode.get(error.errno, "UNKNOWN"),
                    "operation": operation}
    observed["mount_category"] = mount_category(relative)
    results[kind] = observed
print(json.dumps({"uid": os.geteuid(), "gid": os.getegid(), "writes": results}, sort_keys=True))
'''


class QualificationError(Exception):
    def __init__(self, code, **evidence):
        self.code = code
        self.evidence = evidence


def require(condition, code, **evidence):
    if not condition:
        raise QualificationError(code, **evidence)


def pinned_version():
    matches = re.findall(r"^relay_codex_cli_version:\s*['\"]?(\d+\.\d+\.\d+)['\"]?\s*$",
                         PIN.read_text(encoding="utf-8"), re.M)
    require(len(matches) == 1, "SOURCE_VERSION_PIN_UNAVAILABLE")
    return matches[0]


def isolated_environment(root):
    env = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C", "TZ": "UTC",
           "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
           "GIT_CONFIG_SYSTEM": "/dev/null", "GIT_TERMINAL_PROMPT": "0",
           "GIT_SSH_COMMAND": "false", "RUST_LOG": "error"}
    locations = {"HOME": "home", "USERPROFILE": "home", "CODEX_HOME": "home",
                 "XDG_CONFIG_HOME": "config", "XDG_CACHE_HOME": "cache",
                 "XDG_DATA_HOME": "data", "XDG_STATE_HOME": "state",
                 "TMP": "tmp", "TEMP": "tmp", "TMPDIR": "tmp"}
    for key, name in locations.items():
        path = root / name
        path.mkdir(parents=True, exist_ok=True)
        env[key] = str(path)
    (root / "home/config.toml").write_text(
        "[analytics]\nenabled = false\n[feedback]\nenabled = false\n", encoding="utf-8")
    return env


def run(arguments, cwd, env):
    result = subprocess.run(arguments, cwd=cwd, env=env, capture_output=True, timeout=30)
    require(len(result.stdout) <= 16384 and len(result.stderr) <= 65536, "CODEX_OUTPUT_BOUND_EXCEEDED")
    require(result.returncode == 0, "CODEX_COMMAND_FAILED", exit_code=result.returncode,
            stdout_bytes=len(result.stdout), stderr_bytes=len(result.stderr))
    return result.stdout


def retained_agents(root):
    """Compare tiny fixture bytes and metadata, excluding read-induced atime."""
    path = root / ".agents"
    if not path.exists() and not path.is_symlink():
        return None
    entries = {}
    for entry in [path, *sorted(path.rglob("*"))]:
        info = entry.lstat()
        entries[entry.relative_to(root).as_posix()] = (
            info.st_mode, info.st_uid, info.st_gid, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns,
            entry.read_bytes() if stat.S_ISREG(info.st_mode) else None)
    return entries


def qualify_case(binary, root, profile, preexisting):
    work = root / "work"
    work.mkdir()
    (work / ".git").mkdir()
    if preexisting:
        skills = work / ".agents/skills"
        skills.mkdir(parents=True)
        (skills / "retained.txt").write_bytes(b"preserve existing fixture\n")
    before = retained_agents(work)
    probe = work / "probe.py"
    probe.write_text(PROBE, encoding="utf-8")
    env = isolated_environment(work / ".codex-sandbox")
    command = [str(binary), "sandbox"]
    if profile == "workspace-write":
        # `codex --sandbox workspace-write sandbox` does not select this
        # subcommand's policy in the pinned release. Keep the actual config ABI.
        command += ["-c", 'sandbox_mode="workspace-write"',
                    "-c", "sandbox_workspace_write.network_access=true",
                    "-c", "sandbox_workspace_write.writable_roots=" + json.dumps([str(work / ".git")])]
    command += ["--", "/usr/bin/python3", str(probe)]
    raw = run(command, work, env)
    try:
        observed = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise QualificationError("INVALID_NATIVE_PROBE_OUTPUT") from None
    require(isinstance(observed, dict) and set(observed) == {"uid", "gid", "writes"}, "INVALID_NATIVE_PROBE_OUTPUT")
    require(observed["uid"] == os.geteuid() and observed["gid"] == os.getegid(), "PROBE_IDENTITY_CHANGED")
    require(isinstance(observed["writes"], dict) and set(observed["writes"]) == set(KINDS), "INVALID_NATIVE_PROBE_OUTPUT")
    evidence = {}
    mismatches = []
    for kind in KINDS:
        row = observed["writes"][kind]
        require(isinstance(row, dict) and set(row) == {"result", "errno", "operation", "mount_category"}, "INVALID_NATIVE_PROBE_OUTPUT")
        require(isinstance(row["result"], str) and row["result"] in {"writable", "denied"}
                and isinstance(row["operation"], str) and row["operation"] in {"mkdir", "open-write"}, "INVALID_NATIVE_PROBE_OUTPUT")
        require(row["errno"] is None or isinstance(row["errno"], str) and row["errno"] in errno.errorcode.values(), "INVALID_NATIVE_PROBE_OUTPUT")
        require(isinstance(row["mount_category"], str) and (row["mount_category"] == "unavailable" or re.fullmatch(
            r"(?:root-agents|git|workspace|workspace-subpath|ancestor):(?:ro|rw|unknown)", row["mount_category"])), "INVALID_NATIVE_PROBE_OUTPUT")
        writable = profile == "workspace-write" and kind != "root_agents"
        expected = {"result": "writable" if writable else "denied", "errno": None if writable else "EROFS"}
        evidence[kind] = {"expected": expected, "observed": row}
        if any(row[key] != value for key, value in expected.items()):
            mismatches.append(kind)
    if profile == "workspace-write" and evidence["root_agents"]["observed"]["mount_category"] != "root-agents:ro":
        mismatches.append("root_agents_mount")
    unchanged = retained_agents(work) == before
    if not unchanged:
        mismatches.append("host_root_agents_changed")
    return {"profile": profile, "root_agents_initially": "preexisting" if preexisting else "absent",
            "uid": observed["uid"], "gid": observed["gid"], "writes": evidence,
            "host_root_agents_unchanged": unchanged, "mismatches": mismatches}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex", required=True, type=Path, help="absolute path to the exact installed Codex binary")
    parser.add_argument("--expected-version", help="exact version from the selected source configuration; defaults to this source pin")
    args = parser.parse_args()
    try:
        require(sys.platform == "linux", "NATIVE_LINUX_REQUIRED")
        require(os.geteuid() != 0, "NON_ROOT_REQUIRED")
        require(args.codex.is_absolute(), "ABSOLUTE_CODEX_PATH_REQUIRED")
        binary = args.codex.resolve(strict=True)
        require(binary.is_file() and os.access(binary, os.X_OK), "CODEX_BINARY_UNAVAILABLE")
        version = args.expected_version or pinned_version()
        require(re.fullmatch(r"\d+\.\d+\.\d+", version), "INVALID_EXPECTED_VERSION")
        require(Path("/usr/bin/python3").is_file(), "NATIVE_PYTHON_UNAVAILABLE")
        with tempfile.TemporaryDirectory(prefix="relay-worker-filesystem-") as temporary:
            root = Path(temporary)
            env = isolated_environment(root / "version-environment")
            actual = run([str(binary), "--version"], root, env).decode("utf-8").strip()
            require(actual == "codex-cli " + version, "CODEX_VERSION_MISMATCH", expected_version=version)
            cases = []
            for profile in ("workspace-write", "default-read-only"):
                for preexisting in (False, True):
                    case = root / f"case-{len(cases)}"
                    case.mkdir()
                    cases.append(qualify_case(binary, case, profile, preexisting))
            passed = not any(case["mismatches"] for case in cases)
            print(json.dumps({"status": "PASS" if passed else "FAIL", "scope": "native-codex-sandbox",
                              "codex_version": version, "expected_version": version, "observed_version": version,
                              "model_or_provider": "not-invoked", "cases": cases,
                              "limitations": ["synthetic-file-write-only", "native-vibevm-projection-not-tested",
                                              "outer-bwrap-not-tested", "installed-launcher-not-tested",
                                              "automatic-relay-execution-not-tested"]}, separators=(",", ":"), sort_keys=True))
            return 0 if passed else 1
    except QualificationError as error:
        print(json.dumps({"status": "FAIL", "code": error.code, **error.evidence}, separators=(",", ":"), sort_keys=True))
    except subprocess.TimeoutExpired:
        print(json.dumps({"status": "FAIL", "code": "CODEX_COMMAND_TIMEOUT"}))
    except (OSError, UnicodeError) as error:
        print(json.dumps({"status": "FAIL", "code": "QUALIFIER_OS_FAILURE",
                          "errno": errno.errorcode.get(getattr(error, "errno", None), "UNKNOWN")}))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
