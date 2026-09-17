#!/usr/bin/env python3
"""Bounded, read-only production relay diagnostic.

The helper reads only the current production relay namespaces. It never reads
credential files, emits protected request bodies, or changes target state.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


REPOSITORY = "example/relay-consumer"
CLAIM_ROOT = Path("/var/lib/codex-relay/writer-claims")
DISPATCH_ROOT = Path("/var/lib/codex-relay/dispatch")
DEBUG_ROOT = Path("/var/lib/codex-relay/debug")
CONFIG_ROOT = Path("/etc/codex-relay")
INSTALL_ROOT = Path("/opt/codex-relay")
RUNNER_USER = "relay-runner"
MAX_JSON_BYTES = 16 * 1024 * 1024
SAFE_CODE = re.compile(r"^[A-Z0-9_]{1,128}$")
SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
SAFE_SHA = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)
SAFE_BRANCH = re.compile(r"^codex/[A-Za-z0-9][A-Za-z0-9._/-]*$")
SAFE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
SECRET_LIKE = re.compile(
    r"(?:secret|token|password|credential|private[_-]?key|bearer|github_pat_|sk-[A-Za-z0-9])",
    re.IGNORECASE,
)
# Admit codes only when they are attached to an explicit diagnostic field;
# arbitrary private stderr must never be treated as a code source.
CODE_IN_TEXT = re.compile(
    r"(?:\"(?:code|failureCode|blockedCode|storeCode)\"|\b(?:code|failureCode|blockedCode|storeCode))\s*[:=]\s*[\"']?([A-Z][A-Z0-9_]{1,127})",
)

SAFE_FIELDS = {
    "schemaVersion",
    "claimId",
    "target",
    "route",
    "issueNumber",
    "issueBodySha256",
    "phase",
    "status",
    "pullRequest",
    "prNumber",
    "reviewId",
    "reviewedHeadSha",
    "headSha",
    "newHeadSha",
    "oldHeadSha",
    "baseBranch",
    "baseBranchSha",
    "branch",
    "changeRequestId",
    "change_request_id",
    "failureCode",
    "blockedCode",
    "code",
    "classification",
    "dispatchStatus",
    "dispatchConfirmed",
    "dispatchContainment",
    "executionConfirmed",
    "recovery",
    "recoveryGeneration",
    "generation",
    "continuationGeneration",
    "attemptId",
    "attemptOperationKey",
    "recoveryAuthorized",
    "disposition",
    "operatorDecision",
    "executionPossibility",
    "rearmedFrom",
    "startedAt",
    "dispatchedAt",
    "completedAt",
    "authorizedAt",
    "consumedAt",
    "rearmedAt",
    "abandonedAt",
    "priorPhase",
    "priorFailureCode",
    "operation",
    "actorIdentity",
    "publicationMethod",
    "verified",
    "fastForwardOnly",
    "force",
    "idempotent",
    "model",
    "effort",
    "subagentsAllowed",
    "threadId",
    "sessionId",
    "reviewBodySha256",
    "pullRequestBodySha256",
    "contractSha256",
    "taskAuthoritySha256",
    "diagnosticCode",
    "boundary",
    "stage",
    "childStarted",
    "childExitCode",
    "signal",
    "bytes",
    "truncated",
    "executionId",
}
SAFE_NESTED_FIELDS = {
    "failureDiagnostic",
    "diagnosticStore",
    "dispatchReceipt",
    "continuation",
    "abandonedAttempt",
    "evidence",
    "priorReservation",
    "launcherDiagnostic",
    "authorityDigests",
}
OMITTED_FIELDS = {
    "argv",
    "body",
    "environment",
    "input",
    "prBody",
    "preview",
    "stderr",
    "stdout",
    "token",
    "privateKey",
    "credential",
}


def fail(message: str) -> None:
    print(f"PRODUCTION_DIAGNOSTIC_BLOCKED={message}", file=sys.stderr)
    raise SystemExit(1)


def safe_code(value: Any) -> str | None:
    if isinstance(value, str) and SAFE_CODE.fullmatch(value):
        return value
    return None


def safe_scalar(key: str, value: Any) -> Any:
    if key in {"pullRequest", "prNumber", "reviewId", "issueNumber", "recoveryGeneration", "generation", "continuationGeneration"}:
        return value if isinstance(value, int) and value >= 0 and (key not in {"pullRequest", "prNumber", "issueNumber", "reviewId"} or value > 0) else None
    if key in {"dispatchConfirmed", "executionConfirmed", "recoveryAuthorized", "verified", "fastForwardOnly", "force", "idempotent", "subagentsAllowed"}:
        return value if isinstance(value, bool) else None
    if key in {"reviewedHeadSha", "headSha", "newHeadSha", "oldHeadSha", "baseBranchSha"}:
        return value if isinstance(value, str) and SAFE_SHA.fullmatch(value) else None
    if key in {"issueBodySha256", "reviewBodySha256", "pullRequestBodySha256", "contractSha256", "taskAuthoritySha256"}:
        return value if isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value, re.IGNORECASE) else None
    if key in {"claimId", "threadId", "sessionId", "executionId"}:
        return value if isinstance(value, str) and SAFE_ID.fullmatch(value) else None
    if key in {"failureCode", "blockedCode", "code", "priorFailureCode", "diagnosticCode"}:
        return safe_code(value)
    if key in {"childStarted", "truncated"}:
        return value if isinstance(value, bool) else None
    if key in {"childExitCode", "bytes"}:
        return value if isinstance(value, int) and 0 <= value <= 16 * 1024 * 1024 else None
    if key in {"boundary", "stage", "signal"}:
        if not isinstance(value, str) or len(value) > 128 or SECRET_LIKE.search(value):
            return None
        return value if re.fullmatch(r"[A-Za-z0-9_-]+", value) else None
    if key == "blockedMessage":
        if not isinstance(value, str):
            return None
        return re.sub(
            r"(authorization|token|secret|private.?key|password)\s*[:=]\s*[^\s,}]+",
            r"\1=[REDACTED]",
            value,
            flags=re.IGNORECASE,
        )[:512]
    if key in {"phase", "status", "route", "target", "dispatchStatus", "dispatchContainment", "recovery", "operation", "model", "effort", "actorIdentity", "publicationMethod", "branch", "baseBranch", "operatorDecision", "executionPossibility", "disposition", "rearmedFrom", "priorPhase", "changeRequestId", "change_request_id", "classification"}:
        if not isinstance(value, str) or len(value) > 512 or SECRET_LIKE.search(value):
            return None
        return value if SAFE_TOKEN.fullmatch(value) or key in {"actorIdentity", "publicationMethod", "operatorDecision", "executionPossibility"} else None
    if key == "schemaVersion":
        return value if isinstance(value, str) and len(value) <= 32 else None
    if key.endswith("At"):
        return value if isinstance(value, str) and len(value) <= 64 else None
    return None


def safe_projection(value: Any, depth: int = 0) -> Any:
    if depth > 4:
        return None
    if isinstance(value, list):
        projected = [safe_projection(item, depth + 1) for item in value[:16]]
        return [item for item in projected if item is not None]
    if not isinstance(value, dict):
        return None
    result: dict[str, Any] = {}
    for key, child in value.items():
        if key in OMITTED_FIELDS:
            continue
        if key == "blockedMessage":
            scalar = safe_scalar(key, child)
            if scalar is not None:
                result[key] = scalar
        elif key in SAFE_FIELDS:
            scalar = safe_scalar(key, child)
            if scalar is not None:
                result[key] = scalar
        elif key == "process" and isinstance(child, dict):
            process = {}
            if isinstance(child.get("exitCode"), int) and 0 <= child["exitCode"] <= 255:
                process["exitCode"] = child["exitCode"]
            if child.get("signal") is None or isinstance(child.get("signal"), str):
                process["signal"] = child.get("signal")
            if process:
                result[key] = process
        elif key in SAFE_NESTED_FIELDS:
            nested = safe_projection(child, depth + 1)
            if nested not in (None, {}, []):
                result[key] = nested
    return result


def read_json(path: Path) -> tuple[Any | None, str]:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None, "absent"
    except OSError:
        return None, "unreadable"
    if not path.is_file():
        return None, "not-a-file"
    if stat.st_size > MAX_JSON_BYTES:
        return None, "too-large"
    try:
        with path.open("r", encoding="utf-8") as stream:
            return json.load(stream), "read"
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None, "invalid"


def first_present(value: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in value and value[key] is not None:
            return value[key]
    return None


def request_target(request: dict[str, Any]) -> str:
    if request.get("target") == "issue" or "issueNumber" in request:
        return "issue"
    return "pull_request"


def identity_matches(value: Any, request: dict[str, Any]) -> bool:
    if not isinstance(value, dict):
        return False
    if request_target(request) == "issue":
        return (
            first_present(value, "issueNumber", "issue_number") == request["issueNumber"]
            and (
                "issueBodySha256" not in request
                or first_present(value, "issueBodySha256", "issue_body_sha256") == request["issueBodySha256"]
            )
        )
    return (
        first_present(value, "pullRequest", "pull_request", "prNumber") == request["pullRequest"]
        and first_present(value, "reviewId", "review_id") == request["reviewId"]
        and first_present(value, "reviewedHeadSha", "reviewed_head_sha") == request["reviewedHeadSha"]
        and first_present(value, "changeRequestId", "change_request_id") == request["changeRequestId"]
    )


def near_identity_matches(value: Any, request: dict[str, Any]) -> bool:
    if not isinstance(value, dict):
        return False
    if request_target(request) == "issue":
        return False
    return (
        first_present(value, "pullRequest", "pull_request", "prNumber") == request["pullRequest"]
        and first_present(value, "reviewedHeadSha", "reviewed_head_sha") == request["reviewedHeadSha"]
    )


def collect_records(value: Any, source: str, request: dict[str, Any], output: list[dict[str, Any]], seen: set[int]) -> None:
    if not isinstance(value, (dict, list)) or id(value) in seen:
        return
    seen.add(id(value))
    if isinstance(value, dict):
        if identity_matches(value, request):
            match = "exact" if "issueBodySha256" in request else "issue-number"
            output.append({"source": source, "match": match, **safe_projection(value)})
        elif near_identity_matches(value, request):
            output.append({"source": source, "match": "pull-request-and-head", **safe_projection(value)})
        for key, child in value.items():
            if key not in OMITTED_FIELDS:
                collect_records(child, source, request, output, seen)
    else:
        for child in value:
            collect_records(child, source, request, output, seen)


def find_identity_record(value: Any, request: dict[str, Any], *, phase: str | None = None, seen: set[int] | None = None) -> dict[str, Any] | None:
    if not isinstance(value, (dict, list)):
        return None
    seen = seen if seen is not None else set()
    if id(value) in seen:
        return None
    seen.add(id(value))
    if isinstance(value, dict):
        if identity_matches(value, request) and (phase is None or value.get("phase") == phase):
            return value
        for key, child in value.items():
            if key not in OMITTED_FIELDS:
                found = find_identity_record(child, request, phase=phase, seen=seen)
                if found is not None:
                    return found
        return None
    for child in value:
        found = find_identity_record(child, request, phase=phase, seen=seen)
        if found is not None:
            return found
    return None


def continuation_state_check(state: Any, claim: Any, request: dict[str, Any]) -> dict[str, Any]:
    if request_target(request) == "issue":
        return {"status": "not-applicable", "target": "issue"}
    record = find_identity_record(state, request, phase="abandoned")
    if record is None:
        return {"status": "missing"}
    branch = request.get("branch")
    base_branch_sha = request.get("baseBranchSha")
    operation_key = f"{REPOSITORY}+pr-{request['pullRequest']}+head-{request['reviewedHeadSha']}+review-{request['reviewId']}+operation-review-to-remediation"
    cycle_key = f"{REPOSITORY}+pr-{request['pullRequest']}+branch-{branch}+operation-automatic-remediation"
    authority = claim.get("authorityDigests") if isinstance(claim, dict) else None
    expected = {
        "schemaVersion": "1.0",
        "operationKey": operation_key,
        "cycleKey": cycle_key,
        "repository": REPOSITORY,
        "pullRequest": request["pullRequest"],
        "reviewId": request["reviewId"],
        "reviewedHeadSha": request["reviewedHeadSha"],
        "branch": branch,
        "baseBranch": "main",
        "baseBranchSha": base_branch_sha,
        "changeRequestId": request["changeRequestId"],
        "reviewBodySha256": authority.get("reviewBodySha256") if isinstance(authority, dict) else None,
        "pullRequestBodySha256": authority.get("pullRequestBodySha256") if isinstance(authority, dict) else None,
        "contractSha256": authority.get("contractSha256") if isinstance(authority, dict) else None,
        "taskAuthoritySha256": authority.get("taskAuthoritySha256") if isinstance(authority, dict) else None,
        "retryPolicy": "no_automatic_retry",
        "phase": "abandoned",
    }
    mismatches = [field for field, value in expected.items() if value is None or record.get(field) != value]
    continuation = record.get("continuation")
    expected_continuation = {
        "schemaVersion": "1.0",
        "status": "ready",
        "generation": 1,
        "disposition": "execution-possible-remediation-blocked-attempt-abandoned-execution-not-disproved",
        "operatorDecision": "accept-execution-possible-and-abandon",
        "priorPhase": "blocked",
        "priorFailureCode": "GIT_COMMAND_FAILED",
        "executionPossibility": "accepted-not-disproved",
    }
    if not isinstance(continuation, dict):
        mismatches.append("continuation")
    else:
        mismatches.extend(f"continuation.{field}" for field, value in expected_continuation.items() if continuation.get(field) != value)
        if not isinstance(continuation.get("authorizedAt"), str) or not continuation["authorizedAt"]:
            mismatches.append("continuation.authorizedAt")
    abandoned = record.get("abandonedAttempt")
    if not isinstance(abandoned, dict) or abandoned.get("phase") != "blocked":
        mismatches.append("abandonedAttempt.phase")
    evidence = abandoned.get("evidence") if isinstance(abandoned, dict) else None
    if not isinstance(evidence, dict) or evidence.get("status") != "blocked" or evidence.get("blockedCode") != "GIT_COMMAND_FAILED":
        mismatches.append("abandonedAttempt.evidence")
    return {"status": "pass" if not mismatches else "mismatch", "mismatches": sorted(set(mismatches))}


def codes_in_text(value: Any) -> list[str]:
    if not isinstance(value, str):
        return []
    result: list[str] = []
    for match in CODE_IN_TEXT.finditer(value):
        code = safe_code(match.group(1))
        if code and code not in result:
            result.append(code)
    return result[:16]


def classify_private_stderr(value: Any) -> str | None:
    text = str(value or "")
    lowered = text.lower()
    if not text:
        return "NO_PRIVATE_STDERR"
    if "not in the sudoers" in lowered or "may not run sudo" in lowered:
        return "SUDO_POLICY_DENIED"
    if "a password is required" in lowered or "terminal is required" in lowered:
        return "SUDO_NONINTERACTIVE_AUTH_REQUIRED"
    if "permission denied" in lowered or "eacces" in lowered or "eperm" in lowered:
        return "LAUNCHER_PERMISSION_DENIED"
    if "no such file" in lowered or "not found" in lowered or "enoent" in lowered:
        return "LAUNCHER_PATH_UNAVAILABLE"
    if re.search(r"\b(referenceerror|typeerror|syntaxerror|rangeerror)\b", lowered):
        return "LAUNCHER_RUNTIME_EXCEPTION"
    if "invalid" in lowered or "malformed" in lowered or "json" in lowered or "parse" in lowered:
        return "LAUNCHER_INPUT_OR_DIAGNOSTIC_INVALID"
    if "unknown option" in lowered or "usage:" in lowered:
        return "LAUNCHER_ARGUMENT_REJECTED"
    if "sudo" in lowered:
        return "SUDO_LAUNCH_FAILED"
    if re.search(r"referenceerror|typeerror|syntaxerror|rangeerror|node:internal|file://|\berror:\s|\bat\s+\S+", lowered):
        return "LAUNCHER_RUNTIME_EXCEPTION"
    return "PRIVATE_STDERR_UNCLASSIFIED"


def classify_private_error_signature(value: Any) -> str | None:
    text = str(value or "")
    lowered = text.lower()
    signatures = (
        ("err_module_not_found", "MODULE_IMPORT_MISSING"),
        ("cannot find module", "MODULE_IMPORT_MISSING"),
        ("cannot find package", "MODULE_IMPORT_MISSING"),
        ("err_invalid_arg_type", "NODE_ARGUMENT_INVALID"),
        ("is not a function", "RUNTIME_API_MISMATCH"),
        ("is not defined", "RUNTIME_SYMBOL_MISSING"),
        ("unexpected token", "RUNTIME_SYNTAX_INVALID"),
        ("enoent", "RUNTIME_PATH_UNAVAILABLE"),
    )
    for marker, classification in signatures:
        if marker in lowered:
            return classification
    for error_type in ("ReferenceError", "TypeError", "SyntaxError", "RangeError", "Error"):
        if error_type.lower() in lowered:
            return f"NODE_{error_type.upper()}"
    return None


def syntax_error_location(value: Any) -> dict[str, int] | None:
    match = re.search(r"(?:\.m?js|relay-codex):(\d+)(?::(\d+))?", str(value or ""))
    if not match:
        return None
    location = {"line": int(match.group(1))}
    if match.group(2) is not None:
        location["column"] = int(match.group(2))
    return location


def safe_bundle(value: Any, source: str, allowed_execution_ids: set[str], *, match: str = "execution-id") -> dict[str, Any] | None:
    if not isinstance(value, dict) or not isinstance(value.get("executionId"), str) or not SAFE_ID.fullmatch(value["executionId"]):
        return None
    if value["executionId"] not in allowed_execution_ids:
        return None
    result: dict[str, Any] = {"source": source, "match": match, "executionId": value["executionId"]}
    for key in ("mode", "phase", "startedAt", "endedAt"):
        if isinstance(value.get(key), str) and len(value[key]) <= 128:
            result[key] = value[key]
    classification = value.get("classification")
    code = safe_code(classification)
    if code:
        result["classification"] = code
    process = safe_projection(value.get("process"))
    if process:
        result["process"] = process
    launcher = safe_projection(value.get("launcherDiagnostic"))
    if launcher:
        result["launcherDiagnostic"] = launcher
    stderr_codes = codes_in_text(value.get("stderr"))
    if stderr_codes:
        result["stderrCodeCandidates"] = stderr_codes
    stderr_classification = classify_private_stderr(value.get("stderr"))
    if stderr_classification:
        result["stderrClassification"] = stderr_classification
    error_signature = classify_private_error_signature(value.get("stderr"))
    if error_signature:
        result["stderrErrorSignature"] = error_signature
    return result


def execution_ids(value: Any, output: set[str]) -> None:
    if isinstance(value, dict):
        execution_id = value.get("executionId")
        if isinstance(execution_id, str) and SAFE_ID.fullmatch(execution_id):
            output.add(execution_id)
        for child in value.values():
            execution_ids(child, output)
    elif isinstance(value, list):
        for child in value:
            execution_ids(child, output)


def parsed_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or len(value) > 64:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else None


def claim_time_anchors(claim: Any) -> list[datetime]:
    if not isinstance(claim, dict):
        return []
    return [parsed for key in ("claimedAt", "consumedAt", "dispatchedAt") if (parsed := parsed_time(claim.get(key))) is not None]


def bundle_in_claim_window(value: Any, anchors: list[datetime]) -> bool:
    if not isinstance(value, dict) or not anchors:
        return False
    bundle_times = [parsed for key in ("startedAt", "endedAt") if (parsed := parsed_time(value.get(key))) is not None]
    window = timedelta(minutes=15)
    return any(abs(bundle_time - anchor) <= window for bundle_time in bundle_times for anchor in anchors)


def classify_worker_probe_output(stdout: str, stderr: str) -> str:
    combined = f"{stdout}\n{stderr}"
    if re.search(r"ERR_MODULE_NOT_FOUND|Cannot find module|module not found", combined, re.IGNORECASE):
        return "WORKER_IMPORT_FAILED"
    if re.search(r"SyntaxError|Unexpected token", combined, re.IGNORECASE):
        return "WORKER_SYNTAX_INVALID"
    if re.search(r"controller config", combined, re.IGNORECASE):
        return "CONTROLLER_CONFIG_INVALID"
    return "WORKER_PREFLIGHT_FAILED"


def worker_preflight(current: Path, *, consumer_config: Path | None = None) -> dict[str, Any]:
    consumer_config = consumer_config or CONFIG_ROOT / "consumer.json"
    worker = current / "bin" / "relay-codex-dispatch.mjs"
    if not worker.is_file():
        return {"status": "blocked", "code": "WORKER_PREFLIGHT_INPUT_MISSING"}
    try:
        completed = subprocess.run(
            ["/usr/sbin/runuser", "-u", RUNNER_USER, "--", "/usr/bin/node", str(worker), "--check-runtime"],
            cwd=str(current), env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C",
                                   "RELAY_CONSUMER_CONFIG": str(consumer_config)},
            input="", capture_output=True, text=True, timeout=30, check=False,
        )
    except subprocess.TimeoutExpired:
        return {"status": "blocked", "code": "WORKER_PREFLIGHT_TIMEOUT"}
    except OSError:
        return {"status": "blocked", "code": "WORKER_PREFLIGHT_UNAVAILABLE"}
    try:
        payload = json.loads(completed.stdout)
    except ValueError:
        payload = None
    if completed.returncode == 0 and isinstance(payload, dict) and payload.get("version") == 2 and payload.get("status") == "RUNTIME_READY":
        return {"status": "passed", "proof": "installed-import-closure", "exitCode": 0}
    return {"status": "blocked", "exitCode": completed.returncode,
            "code": classify_private_error_signature(completed.stderr) or "WORKER_IMPORT_CLOSURE_UNPROVEN"}

def launcher_preflight(install_root: Path) -> dict[str, Any]:
    launcher = install_root / "relay-codex"
    launcher_module = install_root / "relay-codex.mjs"
    diagnostic_helper = install_root / "codex-runtime" / "relay-codex-diagnostic.mjs"
    binary = install_root / "codex-runtime" / "bin" / "codex"
    result = {
        "launcher": "present" if launcher.is_file() else "absent",
        "launcherModule": "present" if launcher_module.is_file() else "absent",
        "diagnosticHelper": "present" if diagnostic_helper.is_file() else "absent",
        "binary": "present" if binary.is_file() else "absent",
    }
    if not launcher.is_file():
        result.update({"status": "blocked", "code": "LAUNCHER_FILE_MISSING"})
        return result
    if not launcher_module.is_file():
        result.update({"status": "blocked", "code": "LAUNCHER_MODULE_FILE_MISSING"})
        return result
    try:
        wrapper = launcher.read_text(encoding="utf-8")[:4096]
    except (OSError, UnicodeError):
        result.update({"status": "blocked", "code": "LAUNCHER_WRAPPER_READ_FAILED"})
        return result
    result["wrapperModuleInvocation"] = all(
        marker in wrapper
        for marker in (
            "#!/bin/sh",
            "exec /usr/bin/node --experimental-default-type=module",
            "/relay-codex.mjs",
        )
    )
    if not result["wrapperModuleInvocation"]:
        result.update({"status": "blocked", "code": "LAUNCHER_WRAPPER_CONTRACT_INVALID"})
        return result
    safe_env = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C", "HOME": str(DISPATCH_ROOT.parent / 'dispatch-home')}
    try:
        completed = subprocess.run(
            ["/usr/bin/node", "--experimental-default-type=module", "--check", str(launcher_module)],
            cwd=str(install_root),
            env=safe_env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired:
        result.update({"status": "blocked", "code": "LAUNCHER_SYNTAX_CHECK_TIMEOUT"})
        return result
    except OSError:
        result.update({"status": "blocked", "code": "LAUNCHER_SYNTAX_CHECK_UNAVAILABLE"})
        return result
    stdout = completed.stdout if isinstance(completed.stdout, str) else ""
    stderr = completed.stderr if isinstance(completed.stderr, str) else ""
    candidates = codes_in_text(stderr) + [code for code in codes_in_text(stdout) if code not in codes_in_text(stderr)]
    result.update({
        "status": "passed" if completed.returncode == 0 else "blocked",
        "exitCode": completed.returncode,
        "code": "LAUNCHER_SYNTAX_VALID" if completed.returncode == 0 else "LAUNCHER_SYNTAX_INVALID",
    })
    if completed.returncode != 0:
        error_signature = classify_private_error_signature(stderr)
        if error_signature:
            result["errorSignature"] = error_signature
        location = syntax_error_location(stderr)
        if location:
            result["errorLocation"] = location
    if candidates:
        result["codeCandidates"] = candidates[:8]
    return result


def safe_manifest(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    fields = {
        "schemaVersion",
        "commit", "resolvedRevision", "installedRevision", "previousRevision", "consumerRevision", "gitTree",
        "sha256",
        "controllerSourceTreeSha256",
        "releaseSourceTreeSha256",
        "codexLauncherSourceTreeSha256",
        "reviewerSourceTreeSha256",
        "reviewerBuildInputsTreeSha256",
        "reviewerBuildContractSha256",
        "reviewerBinarySha256",
    }
    result = {}
    for key in fields:
        item = value.get(key)
        if key in {"commit", "resolvedRevision", "installedRevision", "previousRevision", "consumerRevision", "gitTree"} and isinstance(item, str) and SAFE_SHA.fullmatch(item):
            result[key] = item
        elif key.endswith("Sha256") and isinstance(item, str) and re.fullmatch(r"[0-9a-f]{64}", item, re.IGNORECASE):
            result[key] = item
        elif key == "schemaVersion" and isinstance(item, str):
            result[key] = item
    dependency = value.get("relayDependency")
    if isinstance(dependency, dict):
        # Only immutable identities, never arbitrary nested manifest content.
        safe = {}
        if dependency.get("repository") == "example/codex-relay":
            safe["repository"] = dependency["repository"]
        for key in ("commit", "tree"):
            item = dependency.get(key)
            if isinstance(item, str) and SAFE_SHA.fullmatch(item):
                safe[key] = item
        item = dependency.get("archiveSha256")
        if isinstance(item, str) and re.fullmatch(r"[0-9a-f]{64}", item):
            safe["archiveSha256"] = item
        result["relayDependency"] = safe
    return result


def file_binding(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "exists": path.exists(),
        "isFile": path.is_file(),
        "isSymlink": path.is_symlink(),
    }
    if path.is_symlink():
        try:
            result["target"] = os.readlink(path)
        except OSError:
            result["target"] = "UNAVAILABLE"
    if not path.is_file():
        return result
    try:
        stat = path.stat()
        result["size"] = stat.st_size
        if stat.st_size > 8 * 1024 * 1024:
            result["sha256"] = "omitted-too-large"
            return result
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        result["sha256"] = digest.hexdigest()
    except OSError:
        result["sha256"] = "UNAVAILABLE"
    return result


def wrapper_exec_target(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        content = path.read_text(encoding="utf-8")[:4096]
    except (OSError, UnicodeError):
        return None
    match = re.search(r"\bexec\s+/usr/bin/node\s+['\"]([^'\"]+)['\"]", content)
    target = match.group(1) if match else None
    return target if isinstance(target, str) and target.startswith(str(INSTALL_ROOT) + "/") else None


def build_diagnostic(request: dict[str, Any], *, claim_root: Path | None = None, dispatch_root: Path | None = None, debug_root: Path | None = None, config_root: Path | None = None, install_root: Path | None = None) -> dict[str, Any]:
    claim_root, dispatch_root, debug_root = claim_root or CLAIM_ROOT, dispatch_root or DISPATCH_ROOT, debug_root or DEBUG_ROOT
    config_root, install_root = config_root or CONFIG_ROOT, install_root or INSTALL_ROOT
    result: dict[str, Any] = {
        "schemaVersion": "1.0",
        "repository": REPOSITORY,
        "target": request_target(request),
        "request": request,
        "protectedBodies": "omitted",
        "privateKeys": "omitted",
        "fileStatus": {},
        "claimRecords": [],
        "operationRecords": [],
        "remediationRecords": [],
        "dispatchRecords": [],
        "diagnosticBundles": [],
    }

    tracked = {
        "claims": claim_root / "claims.json",
        "operations": claim_root / "operations.json",
        "remediation": dispatch_root / "remediation" / "remediation-state.json",
        "remediationEvidence": dispatch_root / "evidence" / "remediation.json",
        "controllerConfig": config_root / "controller.json",
        "diagnosticsConfig": config_root / "diagnostics.json",
    }
    for name, path in tracked.items():
        value, status = read_json(path)
        result["fileStatus"][name] = status
        if name == "claims":
            collect_records(value, "claims.json", request, result["claimRecords"], set())
        elif name == "operations":
            collect_records(value, "operations.json", request, result["operationRecords"], set())
        elif name in {"remediation", "remediationEvidence"}:
            collect_records(value, name, request, result["remediationRecords"], set())
        elif name == "diagnosticsConfig" and isinstance(value, dict) and value.get("mode") in {"normal", "debug"}:
            result["diagnosticsMode"] = value["mode"]
        elif name == "controllerConfig" and isinstance(value, dict):
            result["controller"] = {
                key: value[key]
                for key in ("schemaVersion", "repository", "mutation")
                if key in value and isinstance(value[key], str)
            }
            if isinstance(value.get("artifact"), dict):
                result["controller"]["artifact"] = safe_manifest(value["artifact"])
            if isinstance(value.get("controller"), dict):
                nested = value["controller"]
                result["controller"]["runtimeMode"] = nested.get("runtimeMode") if isinstance(nested.get("runtimeMode"), str) else None
                result["controller"]["stateRoot"] = nested.get("stateRoot") if isinstance(nested.get("stateRoot"), str) else None
                result["controller"]["evidenceRoot"] = nested.get("evidenceRoot") if isinstance(nested.get("evidenceRoot"), str) else None

    claims_value, _ = read_json(tracked["claims"])
    remediation_value, _ = read_json(tracked["remediation"])
    claim = find_identity_record(claims_value, request)
    result["continuationStateCheck"] = continuation_state_check(remediation_value, claim, request)

    try:
        entries = sorted(dispatch_root.rglob("*.json"))
    except OSError:
        entries = []
    for path in entries[:128]:
        if path in tracked.values():
            continue
        value, status = read_json(path)
        if status != "read":
            continue
        collect_records(value, f"dispatch/{path.relative_to(dispatch_root).as_posix()}", request, result["dispatchRecords"], set())

    execution_id_allowlist: set[str] = set()
    for records in (result["claimRecords"], result["operationRecords"], result["remediationRecords"], result["dispatchRecords"]):
        execution_ids(records, execution_id_allowlist)

    try:
        bundles = sorted(debug_root.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    except OSError:
        bundles = []
    time_candidates: list[tuple[Any, str]] = []
    claim_anchors = claim_time_anchors(claim)
    for path in bundles[:8]:
        value, status = read_json(path)
        if status != "read" or not isinstance(value, dict):
            continue
        execution_id = value.get("executionId")
        if isinstance(execution_id, str) and execution_id in execution_id_allowlist:
            record = safe_bundle(value, "debug-bundle", execution_id_allowlist, match="execution-id")
            if record:
                result["diagnosticBundles"].append(record)
        elif request_target(request) == "issue" and "issueBodySha256" not in request and bundle_in_claim_window(value, claim_anchors):
            time_candidates.append((value, "debug-bundle"))

    if not execution_id_allowlist and len(time_candidates) == 1:
        value, source = time_candidates[0]
        record = safe_bundle(value, source, {value["executionId"]}, match="bounded-claim-window")
        if record:
            result["diagnosticBundles"].append(record)
        result["diagnosticCorrelation"] = {"status": "bounded-claim-window", "candidateCount": 1}
    elif not execution_id_allowlist and len(time_candidates) > 1:
        candidates = []
        for value, source in time_candidates:
            record = safe_bundle(value, source, {value["executionId"]}, match="ambiguous-claim-window-candidate")
            if record:
                candidates.append(record)
        result["diagnosticBundleCandidates"] = candidates
        result["diagnosticCorrelation"] = {"status": "ambiguous-claim-window", "candidateCount": len(candidates)}
    elif execution_id_allowlist:
        result["diagnosticCorrelation"] = {"status": "execution-id", "candidateCount": len(result["diagnosticBundles"])}
    else:
        result["diagnosticCorrelation"] = {"status": "not-found", "candidateCount": 0}

    current = install_root / "current"
    release: dict[str, Any] = {"exists": current.exists(), "isSymlink": current.is_symlink()}
    if current.is_symlink():
        try:
            release["target"] = os.readlink(current)
        except OSError:
            release["target"] = "UNAVAILABLE"
    manifest, manifest_status = read_json(current / "artifact-manifest.json")
    release["manifestStatus"] = manifest_status
    if manifest_status == "read":
        release["manifest"] = safe_manifest(manifest)
    result["currentRelease"] = release
    controller = current / 'reviewed-source/controller/src'
    if not controller.is_dir():  # read-only diagnosis of the pre-boundary installation
        controller = current / 'reviewed-source/automation/controllers/routing/src'
    runtime_paths = {
        "dispatchHelper": install_root / "relay-codex-dispatch",
        "attemptController": controller / "attempt.mjs",
        "routingEntrypoint": controller / "entrypoint.mjs",
        "attemptRuntime": controller / "attempt-runtime.mjs",
        "routingDispatch": controller / "codex-dispatch.mjs",
        "publicationBroker": controller / "publication-broker.mjs",
    }
    result["runtimeLayout"] = {name: "present" if path.is_file() else "absent" for name, path in runtime_paths.items()}
    dispatch_artifact = current / "bin" / "relay-codex-dispatch.mjs"
    result["dispatchBinding"] = {
        "fixedHelper": file_binding(runtime_paths["dispatchHelper"]),
        "fixedHelperExecTarget": wrapper_exec_target(runtime_paths["dispatchHelper"]),
        "releaseArtifact": file_binding(dispatch_artifact),
        "reviewedSource": file_binding(runtime_paths["routingDispatch"]),
        "releaseArtifactMatchesReviewedSource": (
            file_binding(dispatch_artifact).get("sha256") == file_binding(runtime_paths["routingDispatch"]).get("sha256")
            and isinstance(file_binding(dispatch_artifact).get("sha256"), str)
            and len(file_binding(dispatch_artifact).get("sha256", "")) == 64
        ),
    }
    result["workerPreflight"] = worker_preflight(current, consumer_config=config_root / "consumer.json")
    result["launcherPreflight"] = launcher_preflight(install_root)
    return result


def configure_paths(args):
    global REPOSITORY, INSTALL_ROOT, CONFIG_ROOT, CLAIM_ROOT, DISPATCH_ROOT, DEBUG_ROOT, RUNNER_USER
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', args.repository):
        fail('REPOSITORY_INVALID')
    for value in [args.install_root, args.config_root, args.state_root]:
        if not re.fullmatch(r'/[A-Za-z0-9_./-]+', value) or any(p in ('', '.', '..') for p in value.split('/')[1:]):
            fail('NAMESPACE_INVALID')
    REPOSITORY = args.repository
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,30}', args.runner_user):
        fail('RUNNER_IDENTITY_INVALID')
    RUNNER_USER = args.runner_user
    INSTALL_ROOT, CONFIG_ROOT = Path(args.install_root), Path(args.config_root)
    CLAIM_ROOT = Path(args.state_root) / 'writer-claims'
    DISPATCH_ROOT = Path(args.state_root) / 'dispatch'
    DEBUG_ROOT = Path(args.state_root) / 'debug'


def parse_args(argv: list[str]) -> dict[str, Any]:
    parser = argparse.ArgumentParser(add_help=False)
    target_group = parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument("--pull-request", type=int)
    target_group.add_argument("--issue-number", type=int)
    parser.add_argument("--issue-body-sha256")
    parser.add_argument("--review-id", type=int)
    parser.add_argument("--reviewed-head")
    parser.add_argument("--change-request-id")
    parser.add_argument("--branch")
    parser.add_argument("--base-branch-sha")
    parser.add_argument('--repository', default=REPOSITORY)
    parser.add_argument('--runner-user', default=RUNNER_USER)
    parser.add_argument('--install-root', default=str(INSTALL_ROOT))
    parser.add_argument('--config-root', default=str(CONFIG_ROOT))
    parser.add_argument('--state-root', default=str(CLAIM_ROOT.parent))
    args = parser.parse_args(argv)
    configure_paths(args)
    if args.issue_number is not None:
        if args.issue_number < 1:
            fail("ISSUE_IDENTITY_INVALID")
        if args.issue_body_sha256 is not None and not re.fullmatch(r"[0-9a-f]{64}", args.issue_body_sha256, re.IGNORECASE):
            fail("ISSUE_BODY_SHA256_INVALID")
        if any(value is not None for value in (args.review_id, args.change_request_id, args.branch, args.base_branch_sha)):
            fail("ISSUE_DIAGNOSTIC_FIELDS_INVALID")
        request = {
            "target": "issue",
            "issueNumber": args.issue_number,
        }
        if args.issue_body_sha256 is not None:
            request["issueBodySha256"] = args.issue_body_sha256.lower()
        return request
    if args.pull_request is None or args.review_id is None or args.pull_request < 1 or args.review_id < 1:
        fail("IDENTIFIER_INVALID")
    if not isinstance(args.reviewed_head, str) or not SAFE_SHA.fullmatch(args.reviewed_head):
        fail("REVIEWED_HEAD_INVALID")
    if not isinstance(args.change_request_id, str) or not re.fullmatch(r"CR-[A-Za-z0-9-]{1,96}", args.change_request_id):
        fail("CHANGE_REQUEST_ID_INVALID")
    if not isinstance(args.branch, str) or not SAFE_BRANCH.fullmatch(args.branch):
        fail("BRANCH_INVALID")
    if not isinstance(args.base_branch_sha, str) or not SAFE_SHA.fullmatch(args.base_branch_sha):
        fail("BASE_BRANCH_SHA_INVALID")
    return {
        "target": "pull_request",
        "pullRequest": args.pull_request,
        "reviewId": args.review_id,
        "reviewedHeadSha": args.reviewed_head,
        "changeRequestId": args.change_request_id,
        "branch": args.branch,
        "baseBranchSha": args.base_branch_sha,
    }


def main(argv: list[str] | None = None) -> int:
    request = parse_args(argv if argv is not None else sys.argv[1:])
    print(json.dumps(build_diagnostic(request), separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
