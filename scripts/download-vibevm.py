#!/usr/bin/env python3
"""Acquire the pinned public release, verifying bytes before making it executable."""
import argparse
import hashlib
import http.client
import json
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
ATTEMPTS = 3
TIMEOUT = 30
TRANSIENT_STATUS = {408, 429, 500, 502, 503, 504}
TRANSPORT_ERRORS = (urllib.error.URLError, TimeoutError, ConnectionError, http.client.IncompleteRead)


def transient(error):
    if isinstance(error, urllib.error.HTTPError):
        return error.code in TRANSIENT_STATUS
    return isinstance(error, TRANSPORT_ERRORS)


def read_url(url, accept="application/octet-stream"):
    for attempt in range(ATTEMPTS):
        try:
            request = urllib.request.Request(url, headers={
                "Accept": accept,
                "User-Agent": "codex-relay-public-ci",
                "X-GitHub-Api-Version": "2022-11-28",
            })
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                return response.read()
        except TRANSPORT_ERRORS as error:
            if not transient(error) or attempt == ATTEMPTS - 1:
                raise
            print(f"VibeVM download retry {attempt + 1}: {error}", file=sys.stderr)
            time.sleep(attempt + 1)


def release_bytes(artifact):
    try:
        return read_url(artifact["url"])
    except TRANSPORT_ERRORS as error:
        if not transient(error):
            raise
        print(f"VibeVM browser download unavailable; trying public release API: {error}",
              file=sys.stderr)

    # Resolve the exact pinned browser URL, never latest or an alternate release.
    match = re.fullmatch(
        r"https://github\.com/([^/]+)/([^/]+)/releases/download/([^/]+)/([^/?#]+)",
        artifact["url"])
    if not match:
        raise ValueError("VibeVM pin is not a GitHub release asset URL")
    owner, repository, tag, name = match.groups()
    api = f"https://api.github.com/repos/{owner}/{repository}/releases"
    release = json.loads(read_url(f"{api}/tags/{tag}", "application/vnd.github+json"))
    assets = [asset for asset in release["assets"]
              if asset["name"] == name and asset["browser_download_url"] == artifact["url"]]
    if release["tag_name"] != tag or len(assets) != 1:
        raise ValueError("VibeVM API does not identify the exact pinned release asset")
    asset_id = assets[0]["id"]
    if type(asset_id) is not int or asset_id <= 0:
        raise ValueError("VibeVM API returned an invalid release asset ID")
    return read_url(f"{api}/assets/{asset_id}")


def download(artifact, destination):
    data = release_bytes(artifact)
    if hashlib.sha256(data).hexdigest() != artifact["sha256"]:
        raise ValueError("VibeVM release digest mismatch")
    destination.write_bytes(data)
    destination.chmod(0o700)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    pin = json.loads((ROOT / "toolchain/vibevm.json").read_text())
    download(pin["linux_x86_64_musl_binary"], args.destination)


if __name__ == "__main__":
    main()
