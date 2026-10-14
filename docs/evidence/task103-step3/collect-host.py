#!/usr/bin/env python3
"""Bounded read-only TEST procfs/protected-record collector; no runtime control."""
import argparse
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import socket
import stat
import subprocess
import time

TARGETS = {
    "codex-relay-test": ("jresearchsoftware/codex-relay-testbed", 1407614568),
    "codex-relay-test-two": ("jresearchsoftware/codex-relay-testbed-2", 1409883950),
}
MAX_RECORD = 512 * 1024
SECRET = re.compile(r"(?:github_pat_|gh[pousr]_)[A-Za-z0-9_]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----")
ENVELOPE_KEYS = ("version", "repository", "consumerDigest", "runId", "attemptId", "target", "number",
                 "issueNumber", "route", "step", "executionSlot", "transport", "readyEventId", "readyEventAt",
                 "readyLabel", "runName", "branch", "startHead", "historicalBase", "targetBase", "reviewId",
                 "authorityDigest", "profile", "subagentsAllowed", "validation", "request", "requestReference")
RECEIPT_KEYS = ("status", "head", "prNumber", "outcomeId", "bodySha256", "noChange", "readiness", "draft")
ADMISSION_KEYS = {"schema_version", "kind", "repository", "task", "parent", "charter_sha256", "purpose", "scope",
                  "model", "effort", "subagents", "validation", "boundaries", "branch", "base_sha", "starting_head",
                  "existing_pr", "issue_closure_policy", "continuation", "authority", "route", "step", "attempt",
                  "run_id", "lineage", "authority_resolution", "change_request_id", "reviewed_head_sha"}


def require(condition, code):
    if not condition:
        raise ValueError(code)


def safe_error_code(error):
    text = str(error)
    return text if re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}", text) else "COLLECTION_REQUIREMENT_OR_SOURCE_UNAVAILABLE"


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def safe_path(path, root):
    value = Path(path)
    require(value.is_absolute() and ".." not in value.parts and value.is_relative_to(root), "PATH_SCOPE_INVALID")
    for ancestor in [*reversed(value.parents), value]:
        if ancestor.exists() or ancestor.is_symlink():
            require(not ancestor.is_symlink(), "SOURCE_SYMLINK")
    return value


def json_source(path, owners, limit=MAX_RECORD):
    """No-follow regular files only; source metadata and original byte digest."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        meta = os.fstat(fd)
        require(stat.S_ISREG(meta.st_mode) and meta.st_nlink == 1 and meta.st_uid in owners
                and not meta.st_mode & 0o022 and 0 < meta.st_size <= limit, "SOURCE_METADATA_INVALID")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(limit + 1)
        require(len(raw) <= limit, "SOURCE_TOO_LARGE")
        value = json.loads(raw)
        require(isinstance(value, dict), "SOURCE_JSON_OBJECT_REQUIRED")
        return value, {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
                       "uid": meta.st_uid, "gid": meta.st_gid, "mode": oct(stat.S_IMODE(meta.st_mode)),
                       "dev": meta.st_dev, "inode": meta.st_ino, "size": len(raw), "mtime_ns": meta.st_mtime_ns}
    finally:
        os.close(fd)


def snapshot(record):
    """Keep immutable machine authority; discard input, result prose, diagnostics/transcripts."""
    result = {"envelope": {key: copy.deepcopy(record["envelope"][key])
                           for key in ENVELOPE_KEYS if key in record["envelope"]}}
    admission = result["envelope"].get("request")
    require(isinstance(admission, dict) and admission.get("kind") == "admission"
            and admission.get("schema_version") == "4.0" and set(admission) <= ADMISSION_KEYS
            and len(json.dumps(admission).encode()) <= 60000, "CURRENT_BOUNDED_ADMISSION_REQUIRED")
    for key in ("publishedHead", "finalHead", "prNumber"):
        if key in record:
            result[key] = record[key]
    if record.get("outcome"):
        result["outcome"] = {key: record["outcome"][key] for key in RECEIPT_KEYS if key in record["outcome"]}
    if isinstance(record.get("collection"), dict):
        result["collection"] = {key: record["collection"][key] for key in ("head", "clean") if key in record["collection"]}
    if isinstance(record.get("execution"), dict):
        execution = record["execution"]
        result["execution"] = {key: execution[key] for key in ("reserved", "returned", "child", "containment") if key in execution}
        worker_result = execution.get("result")
        result["execution"]["result"] = {"status": worker_result.get("status") if isinstance(worker_result, dict) else None}
        usage = execution.get("codexUsage") or {}
        result["execution"]["codexUsage"] = {key: usage[key] for key in (
            "source", "scope", "input_tokens", "output_tokens", "cached_input_tokens",
            "cache_write_input_tokens", "reasoning_output_tokens", "total_tokens") if key in usage}
    for marker in ("qualificationFixture", "synthetic"):
        require(not record.get(marker), "SYNTHETIC_RECORD_EXCLUDED")
    require(not SECRET.search(json.dumps(result)), "SECRET_PATTERN_IN_MACHINE_SNAPSHOT")
    return result


def unit_binding(unit, runner_user):
    completed = subprocess.run(["systemctl", "show", unit, "--no-pager", "--property=User,ControlGroup,FragmentPath"],
                               check=True, capture_output=True, text=True, timeout=10)
    fields = dict(line.split("=", 1) for line in completed.stdout.splitlines() if "=" in line)
    require(fields.get("User") == runner_user and fields.get("ControlGroup", "").startswith("/"), "RUNNER_UNIT_BINDING_INVALID")
    fragment = safe_path(fields["FragmentPath"], Path("/etc/systemd/system"))
    meta = fragment.stat()
    require(meta.st_uid == 0 and stat.S_ISREG(meta.st_mode) and not meta.st_mode & 0o022, "RUNNER_UNIT_UNTRUSTED")
    return fields


def load_slots(namespaces):
    slots, sources = [], []
    for ns in namespaces:
        repository, repository_id = TARGETS[ns]
        path = safe_path(f"/etc/{ns}/consumer.json", Path(f"/etc/{ns}"))
        config, metadata = json_source(path, {0}, 128 * 1024)
        require(config.get("version") == 1 and config.get("repository") == repository, "CONSUMER_IDENTITY_CHANGED")
        require(config.get("writerApp", {}).get("appId") == "5213167"
                and config.get("writerApp", {}).get("installationId") == "168570509"
                and config.get("reviewerApp", {}).get("appId") == "5213202"
                and config.get("reviewerApp", {}).get("installationId") == "168571879", "TEST_APP_BINDING_CHANGED")
        sources.append(metadata)
        configured = config.get("executionSlots")
        require(isinstance(configured, list) and 1 <= len(configured) <= 32, "CONFIGURED_EXECUTION_SLOTS_REQUIRED")
        known = set()
        for value in configured:
            slot_id = value["id"]
            require(re.fullmatch(r"[a-z][a-z0-9-]{0,31}", slot_id) and slot_id not in known, "SLOT_ID_INVALID")
            known.add(slot_id)
            runtime = pwd.getpwnam(value["runtimeUser"])
            runner = pwd.getpwnam(value["runnerUser"])
            require(runtime.pw_uid > 0 and runner.pw_uid > 0 and runtime.pw_uid != runner.pw_uid, "SLOT_UID_INVALID")
            state = Path(f"/var/lib/{ns}")
            paths = value["paths"]
            work = safe_path(paths["workRoot"], state)
            attempts = safe_path(paths["attemptRoot"], state)
            claims = safe_path(config["paths"]["claimRoot"], state) / "publication-v2"
            safe_path(claims, state)
            require(attempts.name == "attempts-v2", "ATTEMPT_ROOT_INVALID")
            if slot_id == "primary":
                require(value["runtimeUser"] == config["runtimeUser"] and paths["workRoot"] == config["paths"]["workRoot"]
                        and paths["attemptRoot"] == config["paths"]["attemptRoot"], "PRIMARY_SLOT_CHANGED")
                unit = f"{ns}-general-runner.service"
            else:
                require(work == state / "slots" / slot_id / "work"
                        and attempts == state / "slots" / slot_id / "dispatch/attempts-v2", "ADDITIONAL_SLOT_PATH_CHANGED")
                unit = f"{ns}-slot-{slot_id}-runner.service"
            binding = unit_binding(unit, value["runnerUser"])
            slots.append({"namespace": ns, "repository": repository, "repository_id": repository_id, "id": slot_id,
                          "uid": runtime.pw_uid, "runner_uid": runner.pw_uid, "work": work, "attempts": attempts,
                          "claims": claims, "unit": unit, "cgroup": binding["ControlGroup"], "unit_source": binding["FragmentPath"]})
        directory = Path(f"/var/lib/{ns}/slots")
        if directory.exists():
            require(all(child.name in known and not child.is_symlink() for child in directory.iterdir()), "UNEXPECTED_INSTALLED_SLOT")
    require(len({slot["uid"] for slot in slots}) == len(slots), "CROSS_SLOT_RUNTIME_UID_SHARED")
    return slots, sources


def record_binding(record, slot, run_id):
    e = record.get("envelope") or {}
    require(e.get("repository") == slot["repository"] and e.get("runId") == run_id
            and e.get("attemptId") == f"run-{run_id}" and e.get("executionSlot", "primary") == slot["id"], "RECORD_BINDING_INVALID")
    return e


class Records:
    def __init__(self, slots):
        self.slots, self.cache, self.sources, self.source_history = slots, {}, {}, {}

    def read(self, path, owners):
        metadata = path.lstat()
        identity = (metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns)
        if path not in self.cache or self.cache[path][0] != identity:
            value, source = json_source(path, owners)
            self.cache[path] = (identity, value)
            self.sources[str(path)] = source
            self.source_history[(str(path), source["sha256"])] = source
        return self.cache[path][1]

    def scan(self):
        inventory, pairs, scanned_claims, gaps, counts = [], {}, {}, [], {"journals": 0, "claims": 0}
        for slot in self.slots:
            for kind, directory, owners in [("journal", slot["attempts"], {0, slot["runner_uid"]}),
                                             ("claim", slot["claims"], {0})]:
                if not directory.exists():
                    gaps.append({"code": "PROTECTED_DIRECTORY_MISSING", "namespace": slot["namespace"], "slot": slot["id"], "kind": kind})
                    continue
                meta = directory.lstat()
                require(stat.S_ISDIR(meta.st_mode) and meta.st_uid in owners and not meta.st_mode & 0o022, "PROTECTED_DIRECTORY_UNTRUSTED")
                if kind == "claim" and directory in scanned_claims:
                    continue
                if kind == "claim":
                    scanned_claims[directory] = True
                names = list(directory.iterdir())
                require(len(names) <= 10000, "PROTECTED_RECORD_COUNT_LIMIT")
                for path in names:
                    if not re.fullmatch(r"[1-9][0-9]*\.json", path.name):
                        continue  # canonical temporary/lock entries are not records
                    run_id = int(path.stem)
                    try:
                        value = self.read(path, owners)
                        assigned = slot
                        if kind == "claim":
                            slot_id = (value.get("envelope") or {}).get("executionSlot", "primary")
                            choices = [item for item in self.slots if item["namespace"] == slot["namespace"] and item["id"] == slot_id]
                            require(len(choices) == 1, "CLAIM_SLOT_UNCONFIGURED")
                            assigned = choices[0]
                        e = record_binding(value, assigned, run_id)
                        key = (assigned["repository"], run_id)
                        pair = pairs.setdefault(key, {"slot": assigned})
                        require(kind not in pair, "DUPLICATE_SLOT_JOURNAL")
                        pair[kind] = value
                        pair[kind + "_path"] = path
                        counts["journals" if kind == "journal" else "claims"] += 1
                        if kind == "journal":
                            inventory.append({"repository": e["repository"], "repository_id": assigned["repository_id"],
                                              "run_id": run_id, "task": e.get("issueNumber"), "step": e.get("step"),
                                              "attempt": e["attemptId"], "execution_slot": assigned["id"],
                                              "ready_event_id": e.get("readyEventId"),
                                              "child": (value.get("execution") or {}).get("child", "not_started"),
                                              "record_kind": "journal",
                                              "synthetic": bool(value.get("qualificationFixture") or value.get("synthetic")),
                                              "source_path": str(path), "source_sha256": self.sources[str(path)]["sha256"]})
                    except (ValueError, OSError, KeyError, TypeError):
                        gaps.append({"code": "PROTECTED_RECORD_READ_OR_BINDING_GAP", "namespace": slot["namespace"],
                                     "slot": slot["id"], "kind": kind, "run_id": run_id})
        for key, pair in pairs.items():
            if "journal" in pair and "claim" in pair:
                if pair["journal"]["envelope"] != pair["claim"]["envelope"]:
                    gaps.append({"code": "CLAIM_JOURNAL_ENVELOPE_MISMATCH", "repository": key[0], "run_id": key[1]})
            elif "claim" in pair:
                e = pair["claim"]["envelope"]
                inventory.append({"repository": key[0], "run_id": key[1], "task": e.get("issueNumber"), "step": e.get("step"),
                                  "attempt": e["attemptId"], "ready_event_id": e.get("readyEventId"),
                                  "child": (pair["claim"].get("controllerLifecycle") or {}).get("child", "unknown"),
                                  "record_kind": "claim",
                                  "source_path": str(pair["claim_path"])})
        return inventory, pairs, gaps, counts


def proc(pid, slots):
    root = Path("/proc") / str(pid)
    executable = os.readlink(root / "exe")
    if Path(executable).name != "codex":
        return None
    fields = (root / "stat").read_text().rsplit(")", 1)[1].split()
    status = (root / "status").read_text()
    uids = [int(value) for value in re.search(r"^Uid:\s+(.+)$", status, re.M).group(1).split()]
    uid = uids[0]
    cgroups = (root / "cgroup").read_text().splitlines()
    actual_cgroups = [line.split(":", 2)[2] for line in cgroups]
    relevant_uid = uid in {slot["uid"] for slot in slots}
    relevant_cgroup = any(group == slot["cgroup"] or group.startswith(slot["cgroup"] + "/")
                          for group in actual_cgroups for slot in slots)
    if not relevant_uid and not relevant_cgroup:
        return None  # never inspect foreign argv, environment or working directory
    require(all(value == uid for value in uids), "PROCESS_MIXED_UIDS")
    raw = (root / "cmdline").read_bytes()
    require(len(raw) <= 65536, "PROCESS_CMDLINE_LIMIT")
    args = raw.split(b"\0")
    if b"exec" not in args[1:4]:
        return None  # excludes app-server/other Codex roles; argv is never stored
    cwd_chain = []
    current = pid
    for _ in range(12):
        parent_root = Path("/proc") / str(current)
        try:
            cwd_chain.append(os.readlink(parent_root / "cwd"))
            parent_fields = (parent_root / "stat").read_text().rsplit(")", 1)[1].split()
            current = int(parent_fields[1])
            if current <= 1:
                break
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            break
    return {"pid": pid, "uid": uid, "proc_start_ticks": fields[19], "process_state": fields[0],
            "executable": executable, "command_role": "codex-exec", "cgroups": cgroups, "cwd_chain": cwd_chain}


def attribute(process, slots, pairs):
    matches = []
    for slot in slots:
        if process["uid"] != slot["uid"]:
            continue
        cgroups = [line.split(":", 2)[2] for line in process["cgroups"]]
        if not any(group == slot["cgroup"] or group.startswith(slot["cgroup"] + "/") for group in cgroups):
            continue
        for (repository, run_id), pair in pairs.items():
            if pair["slot"] != slot or "claim" not in pair or "journal" not in pair:
                continue
            if pair["claim"]["envelope"] != pair["journal"]["envelope"]:
                continue
            e = pair["claim"]["envelope"]
            if e.get("route") != "auto" or e.get("request", {}).get("kind") != "admission":
                continue
            if (pair["journal"].get("execution") or {}).get("reserved") is not True:
                continue
            checkout = slot["work"] / f"run-{run_id}"
            if any(Path(cwd) == checkout or Path(cwd).is_relative_to(checkout) for cwd in process["cwd_chain"]):
                matches.append({"repository": repository, "repository_id": slot["repository_id"], "run_id": run_id,
                                "attempt": e["attemptId"], "execution_slot": slot["id"], "namespace": slot["namespace"],
                                "cgroup": slot["cgroup"], "runner_service": slot["unit"], "checkout": str(checkout)})
    require(len(matches) == 1, "PROCESS_ATTRIBUTION_AMBIGUOUS_OR_MISSING")
    return matches[0]


def write_json(root, name, value):
    target = root / name
    temporary = root / (name + ".tmp")
    with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "w") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
    os.replace(temporary, target)


def self_test():
    import unittest

    class Checks(unittest.TestCase):
        def test_snapshot_excludes_input_prose_transcripts_and_secret_paths(self):
            value = {"envelope": {"runId": 1, "input": "private input", "request": {"kind": "admission", "schema_version": "4.0"}},
                     "execution": {"result": {"status": "success", "summary": "private summary"}, "diagnostic": "transcript"}}
            sanitized = snapshot(value)
            self.assertNotIn("private", json.dumps(sanitized))
            self.assertNotIn("transcript", json.dumps(sanitized))
            self.assertEqual(sanitized["envelope"]["request"], {"kind": "admission", "schema_version": "4.0"})
            with self.assertRaises(ValueError):
                snapshot({"envelope": {"request": {"kind": "admission", "schema_version": "4.0",
                                                    "scope": ["-----BEGIN PRIVATE KEY-----"]}}})
            with self.assertRaises(ValueError):
                snapshot({"envelope": {"request": {"kind": "admission", "schema_version": "4.0", "transcript": "forbidden"}}})

        def test_original_byte_digest_and_metadata_read_no_follow(self):
            import tempfile
            with tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "123.json"
                raw = b'{"envelope":{"runId":123}}\n'
                source.write_bytes(raw)
                source.chmod(0o600)
                value, metadata = json_source(source, {os.getuid()})
                self.assertEqual(value["envelope"]["runId"], 123)
                self.assertEqual(metadata["sha256"], hashlib.sha256(raw).hexdigest())
                linked = Path(directory) / "linked.json"
                linked.symlink_to(source)
                with self.assertRaises(OSError):
                    json_source(linked, {os.getuid()})
                source.chmod(0o666)
                with self.assertRaises(ValueError):
                    json_source(source, {os.getuid()})

        def test_attribution_requires_uid_exact_cgroup_cwd_and_original_pair(self):
            slot = {"uid": 123, "id": "primary", "work": Path("/var/lib/codex-relay-test/work"),
                    "cgroup": "/system.slice/test.service", "unit": "test.service", "namespace": "codex-relay-test",
                    "repository_id": 1407614568}
            e = {"route": "auto", "request": {"kind": "admission"}, "attemptId": "run-1"}
            pair = {"slot": slot, "claim": {"envelope": e}, "journal": {"envelope": copy.deepcopy(e), "execution": {"reserved": True}}}
            pairs = {("jresearchsoftware/codex-relay-testbed", 1): pair}
            process = {"uid": 123, "cgroups": ["0::/system.slice/test.service"],
                       "cwd_chain": ["/var/lib/codex-relay-test/work/run-1/src"]}
            self.assertEqual(attribute(process, [slot], pairs)["run_id"], 1)
            for changed in ({"uid": 0}, {"cgroups": ["0::/foreign"]}, {"cwd_chain": ["/foreign/run-1"]}):
                with self.assertRaises(ValueError):
                    attribute({**process, **changed}, [slot], pairs)
            pair["journal"]["envelope"]["attemptId"] = "run-2"
            with self.assertRaises(ValueError):
                attribute(process, [slot], pairs)

    require(unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(Checks)).wasSuccessful(), "OFFLINE_CHECK_FAILED")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", nargs="?", choices=["observe", "snapshot"])
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--namespace", action="append", choices=list(TARGETS))
    parser.add_argument("--duration", type=int, default=900)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--run", action="append", default=[], help="snapshot: exact namespace:run-ID")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    require(os.geteuid() == 0 and args.mode and args.output and args.namespace, "ROOT_AND_EXPLICIT_TARGETS_REQUIRED")
    require(1 <= args.duration <= 900 and len(args.namespace) == len(set(args.namespace)), "BOUNDED_WINDOW_REQUIRED")
    output = safe_path(args.output, Path("/root"))
    require(not output.exists() and output.parent.is_dir() and output.parent.stat().st_uid == 0
            and not output.parent.stat().st_mode & 0o077, "NEW_ROOT_PRIVATE_OUTPUT_REQUIRED")
    slots, config_sources = load_slots(args.namespace)
    output.mkdir(mode=0o700)
    records, samples, gaps, history, inventory_window = Records(slots), [], [], [], {}
    start, deadline, host = utc(), time.monotonic() + args.duration, socket.gethostname()
    requested = []
    for value in args.run:
        match = re.fullmatch(r"(codex-relay-test(?:-two)?):([1-9][0-9]*)", value)
        require(match and match[1] in args.namespace, "EXPLICIT_SNAPSHOT_RUN_INVALID")
        requested.append((TARGETS[match[1]][0], int(match[2]), match[1]))
    require(args.mode != "snapshot" or requested, "EXPLICIT_SNAPSHOT_RUNS_REQUIRED")
    try:
        while True:
            observed = utc()
            inventory, pairs, record_gaps, counts = records.scan()
            for attempt in inventory:
                if attempt["record_kind"] == "journal":
                    for identity, previous in list(inventory_window.items()):
                        if previous["record_kind"] == "claim" and previous["repository"] == attempt["repository"] \
                                and previous["run_id"] == attempt["run_id"]:
                            del inventory_window[identity]  # the same reservation now has its original journal
            for attempt in inventory:
                identity = (attempt["repository"], attempt["run_id"], attempt["source_path"])
                previous = inventory_window.get(identity)
                if previous and previous["child"] == "started" and attempt["child"] != "started":
                    gaps.append({"code": "OBSERVED_CHILD_STATE_REGRESSION", "repository": attempt["repository"],
                                 "run_id": attempt["run_id"], "observed_at": observed})
                else:
                    inventory_window[identity] = attempt
            if any(not Path(attempt["source_path"]).exists() for attempt in inventory_window.values()):
                gaps.append({"code": "OBSERVED_PROTECTED_RECORD_DISAPPEARED", "observed_at": observed})
            gaps.extend({**gap, "observed_at": observed} for gap in record_gaps)
            active = 0
            if args.mode == "observe":
                for entry in Path("/proc").iterdir():
                    if not entry.name.isdigit():
                        continue
                    try:
                        process = proc(int(entry.name), slots)
                        if process is None:
                            continue
                        # Foreign Codex processes are never read beyond minimal metadata or attributed.
                        attributed = attribute(process, slots, pairs)
                        samples.append({"observed_at": observed, "host": host, **attributed,
                                        **{key: process[key] for key in ("pid", "uid", "proc_start_ticks", "process_state", "executable", "command_role")}})
                        active += 1
                    except (FileNotFoundError, ProcessLookupError):
                        continue  # procfs exit race, never fabricated samples
                    except (PermissionError, ValueError, KeyError, TypeError):
                        gaps.append({"code": "PROCESS_METADATA_OR_ATTRIBUTION_GAP", "pid": int(entry.name), "observed_at": observed})
            history.append({"observed_at": observed, "active_attributable_codex": active, **counts, "inventory_count": len(inventory)})
            if args.mode == "snapshot":
                for repository, run_id, namespace in requested:
                    pair = pairs.get((repository, run_id))
                    require(pair and "claim" in pair and "journal" in pair, "SNAPSHOT_ORIGINAL_PAIR_MISSING")
                    require(pair["claim"]["envelope"] == pair["journal"]["envelope"], "SNAPSHOT_ORIGINAL_PAIR_MISMATCH")
                    for kind in ("claim", "journal"):
                        write_json(output, f"{namespace}-{run_id}.{kind}.json", snapshot(pair[kind]))
                break
            complete = not gaps
            write_json(output, "protected-host-observations.json", {"source": "trusted-host-procfs", "complete_for_window": complete,
                       "started_at": start, "collected_at": observed, "sample_interval_seconds": 2, "samples": samples, "gaps": gaps})
            if len(history) % 5 == 1:
                print(json.dumps({"observed_at": observed, "samples": len(samples), "active": active,
                                  "gaps": len(gaps), **counts}), flush=True)
            if time.monotonic() >= deadline:
                break
            time.sleep(min(2, max(0, deadline - time.monotonic())))
    except KeyboardInterrupt:
        gaps.append({"code": "COLLECTION_INTERRUPTED", "observed_at": utc()})
    except (ValueError, OSError, KeyError, TypeError) as error:
        gaps.append({"code": safe_error_code(error), "observed_at": utc()})
        raise
    finally:
        if args.mode == "observe":
            write_json(output, "protected-host-observations.json", {"source": "trusted-host-procfs", "complete_for_window": not gaps,
                       "started_at": start, "ended_at": utc(), "sample_interval_seconds": 2, "samples": samples, "gaps": gaps})
        write_json(output, "protected-execution-inventory.json", {"complete_for_window": not gaps, "started_at": start,
                   "ended_at": utc(), "attempts": list(inventory_window.values()), "scan_counts": history, "gaps": gaps})
        write_json(output, "protected-sources.json", {"configs": config_sources, "records": list(records.source_history.values()),
                   "slots": [{key: str(value) if isinstance(value, Path) else value for key, value in slot.items()} for slot in slots],
                   "collector_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "gaps": gaps})
    print(json.dumps({"output": str(output), "samples": len(samples), "gaps": len(gaps), "complete_for_window": not gaps}), flush=True)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as error:
        # Never print source bytes, raw command lines, subprocess stderr or exception payloads.
        print(json.dumps({"status": "FAILED", "code": safe_error_code(error)}), flush=True)
        raise SystemExit(1)
