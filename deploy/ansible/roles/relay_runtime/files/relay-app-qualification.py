#!/usr/bin/env python3
"""Bounded, read-only GitHub App qualification for the qualification host.

The caller supplies only the non-secret identity contract and a host-local PEM
path through the environment.  JWTs and installation tokens stay in this
process and are never printed.
"""

import base64
import datetime as dt
import json
import os
import pathlib
import re
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request


API = "https://api.github.com"
API_VERSION = "2022-11-28"
TOKEN_TTL_MIN_SECONDS = 60
TOKEN_TTL_MAX_SECONDS = 7200
PERMISSION_LEVELS = {"none": 0, "read": 1, "write": 2, "admin": 3}
SAFE_PERMISSION_LEVELS = {"read", "write"}
EXPECTED_WRITE_PERMISSION_NAMES = {
    "reviewer": {"pull_requests", "checks"},
    "writer": {"contents", "issues", "pull_requests", "workflows"},
}


class QualificationFailure(RuntimeError):
    pass


def fail(code):
    raise QualificationFailure(code)


def env_required(name):
    value = os.environ.get(name, "")
    if not value:
        fail(f"MISSING_{name}")
    return value


def require_numeric(value, field):
    if not re.fullmatch(r"[0-9]+", value):
        fail(f"INVALID_{field}")


def validate_configuration():
    role = env_required("RELAY_APP_ROLE")
    if role not in {"reviewer", "writer"}:
        fail("INVALID_APP_ROLE")
    app_id = env_required("GITHUB_APP_ID")
    installation_id = env_required("GITHUB_APP_INSTALLATION_ID")
    require_numeric(app_id, "APP_ID")
    require_numeric(installation_id, "INSTALLATION_ID")
    slug = env_required("RELAY_EXPECTED_APP_SLUG")
    expected_actor = env_required("RELAY_EXPECTED_ACTOR")
    if expected_actor != f"{slug}[bot]":
        fail("EXPECTED_ACTOR_MAPPING_INVALID")
    repository = env_required("RELAY_EXPECTED_REPOSITORY")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        fail("INVALID_REPOSITORY")
    key_path = pathlib.Path(env_required("GITHUB_APP_PRIVATE_KEY_FILE"))
    expected_mode = int(env_required("RELAY_EXPECTED_KEY_MODE"), 8)
    if key_path.is_symlink() or not key_path.is_file():
        fail("APP_KEY_NOT_REGULAR_FILE")
    key_stat = key_path.stat()
    if key_stat.st_uid != 0 or stat.S_IMODE(key_stat.st_mode) != expected_mode:
        fail("APP_KEY_OWNERSHIP_OR_MODE_INVALID")
    if not os.access(key_path, os.R_OK):
        fail("APP_KEY_UNREADABLE")
    if "GITHUB_REVIEWER_TOKEN" in os.environ or "GITHUB_WRITER_TOKEN" in os.environ:
        fail("PERSISTENT_TOKEN_VARIABLE_FORBIDDEN")
    return {
        "role": role,
        "app_id": app_id,
        "installation_id": installation_id,
        "slug": slug,
        "expected_actor": expected_actor,
        "repository": repository,
        "key_path": key_path,
    }


def b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def create_app_jwt(config):
    now = int(time.time())
    header = b64url(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = b64url(json.dumps({"iat": now - 60, "exp": now + 540, "iss": int(config["app_id"])}, separators=(",", ":")).encode())
    signing_input = f"{header}.{payload}".encode("ascii")
    signed = subprocess.run(
        ["/usr/bin/openssl", "dgst", "-sha256", "-sign", str(config["key_path"])],
        input=signing_input,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if signed.returncode != 0:
        fail("APP_JWT_MINT_FAILED")
    return f"{header}.{payload}.{b64url(signed.stdout)}"


def request_json(method, path, token, body=None):
    if method not in {"GET", "POST"}:
        fail("UNAUTHORIZED_HTTP_METHOD")
    data = None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "codex-relay-app-qualification/1.0",
        "X-GitHub-Api-Version": API_VERSION,
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(API + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
    except urllib.error.HTTPError as error:
        detail = ""
        try:
            payload = json.loads(error.read().decode("utf-8"))
            detail = str(payload.get("message", ""))
        except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            pass
        detail = re.sub(r"[^A-Za-z0-9 ._:/-]", "", " ".join(detail.split()))[:160]
        fail(f"GITHUB_HTTP_{error.code}" + (f"_{detail}" if detail else ""))
    except (urllib.error.URLError, TimeoutError, OSError):
        fail("GITHUB_NETWORK_FAILED")
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        fail("GITHUB_RESPONSE_INVALID")


def require_object(value, field):
    if not isinstance(value, dict):
        fail(f"{field}_INVALID")
    return value


def validate_app_identity(response, config):
    response = require_object(response, "APP_IDENTITY")
    if str(response.get("id", "")) != config["app_id"] or response.get("slug") != config["slug"]:
        fail("APP_IDENTITY_MISMATCH")


def validate_installation(response, config, field):
    response = require_object(response, field)
    if str(response.get("id", "")) != config["installation_id"]:
        fail(f"{field}_INSTALLATION_MISMATCH")
    if str(response.get("app_id", "")) != config["app_id"] or response.get("app_slug") != config["slug"]:
        fail(f"{field}_APP_MISMATCH")
    return response


def parse_permissions(value, field):
    if not isinstance(value, dict):
        fail(f"{field}_PERMISSIONS_MISSING")
    permissions = {}
    for name, level in value.items():
        if not isinstance(name, str) or level not in PERMISSION_LEVELS:
            fail(f"{field}_PERMISSIONS_INVALID")
        permissions[name] = level
    return permissions


def expected_installation_permissions(config):
    configured_names = set(env_required("RELAY_EXPECTED_WRITE_PERMISSION_NAMES").split(","))
    if configured_names != EXPECTED_WRITE_PERMISSION_NAMES[config["role"]]:
        fail("EXPECTED_WRITE_PERMISSION_NAMES_INVALID")
    result = {"metadata": "read"}
    for name in EXPECTED_WRITE_PERMISSION_NAMES[config["role"]]:
        result[name] = "write"
    return result


def token_permissions():
    raw = env_required("RELAY_TOKEN_PERMISSIONS")
    result = {}
    for pair in raw.split(","):
        name, separator, level = pair.partition(":")
        if not separator or level not in SAFE_PERMISSION_LEVELS:
            fail("TOKEN_PERMISSIONS_INVALID")
        result[name] = level
    if result != {"metadata": "read"}:
        fail("TOKEN_PERMISSIONS_NOT_READ_ONLY")
    return result


def repository_name(repository):
    return repository.split("/", 1)[1]


def validate_permissions(actual, required, field):
    actual = parse_permissions(actual, field)
    for name, level in required.items():
        if PERMISSION_LEVELS.get(actual.get(name, "none"), -1) < PERMISSION_LEVELS[level]:
            fail(f"{field}_PERMISSION_INSUFFICIENT")
    for name, level in actual.items():
        if level in {"write", "admin"} and name not in required:
            fail(f"{field}_PERMISSION_SCOPE_TOO_BROAD")
        if level == "admin":
            fail(f"{field}_ADMIN_PERMISSION_FORBIDDEN")
    return actual


def parse_expiry(value):
    if not isinstance(value, str):
        fail("TOKEN_EXPIRY_MISSING")
    try:
        expiry = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        fail("TOKEN_EXPIRY_INVALID")
    ttl = int(expiry.timestamp() - time.time())
    if ttl < TOKEN_TTL_MIN_SECONDS or ttl > TOKEN_TTL_MAX_SECONDS:
        fail("TOKEN_NOT_SHORT_LIVED")
    return ttl


def qualify(config):
    app_jwt = create_app_jwt(config)
    app = request_json("GET", "/app", app_jwt)
    validate_app_identity(app, config)

    installation = validate_installation(
        request_json("GET", f"/app/installations/{config['installation_id']}", app_jwt),
        config,
        "APP_INSTALLATION",
    )
    installation_permissions = expected_installation_permissions(config)
    validate_permissions(installation.get("permissions"), installation_permissions, "APP_INSTALLATION")

    repository_installation = validate_installation(
        request_json("GET", f"/repos/{config['repository']}/installation", app_jwt),
        config,
        "REPOSITORY_INSTALLATION",
    )
    selection = repository_installation.get("repository_selection")
    if selection not in {"selected", "all"}:
        fail("REPOSITORY_SCOPE_INVALID")

    requested_token_permissions = token_permissions()
    token_response = require_object(
        request_json(
            "POST",
            f"/app/installations/{config['installation_id']}/access_tokens",
            app_jwt,
            body={"repositories": [repository_name(config["repository"])], "permissions": requested_token_permissions},
        ),
        "TOKEN_RESPONSE",
    )
    token = token_response.get("token")
    if not isinstance(token, str) or not token:
        fail("TOKEN_MISSING")
    ttl = parse_expiry(token_response.get("expires_at"))
    effective = validate_permissions(token_response.get("permissions"), requested_token_permissions, "TOKEN")
    repository = require_object(
        request_json("GET", f"/repos/{config['repository']}", token),
        "REPOSITORY_PROBE",
    )
    if repository.get("full_name") != config["repository"]:
        fail("REPOSITORY_PROBE_SCOPE_MISMATCH")
    permission_text = ",".join(f"{name}:{effective[name]}" for name in sorted(effective))
    return {
        "role": config["role"],
        "app_slug": config["slug"],
        "app_id": config["app_id"],
        "installation_id": config["installation_id"],
        "repository": config["repository"],
        "repository_selection": selection,
        "installation_permissions": ",".join(f"{name}:{installation_permissions[name]}" for name in sorted(installation_permissions)),
        "token_permissions": permission_text,
        "token_ttl_seconds": ttl,
        "expected_actor": config["expected_actor"],
    }


def main():
    try:
        result = qualify(validate_configuration())
    except QualificationFailure as error:
        print(f"APP_QUALIFICATION_FAIL code={error}")
        return 1
    print(
        "APP_QUALIFICATION_PASS "
        + " ".join(
            [
                f"role={result['role']}",
                f"app_slug={result['app_slug']}",
                f"app_id={result['app_id']}",
                f"installation_id={result['installation_id']}",
                f"repository={result['repository']}",
                f"repository_selection={result['repository_selection']}",
                f"installation_permissions={result['installation_permissions']}",
                f"token_permissions={result['token_permissions']}",
                "token_ttl_class=short-lived",
                "read_only_probe=GET:/repos/{repository}".format(repository=result["repository"]),
                f"expected_actor={result['expected_actor']}",
            ]
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
