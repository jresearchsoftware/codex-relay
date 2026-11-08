#!/usr/bin/env python3
"""Credential-free release acquisition failure and integrity counterexamples."""
import hashlib
import http.client
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

SPEC = importlib.util.spec_from_file_location("download", Path(__file__).with_name("download-vibevm.py"))
DOWNLOAD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DOWNLOAD)


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="relay-download-test-")
        self.addCleanup(self.temporary.cleanup)
        self.destination = Path(self.temporary.name) / "vibe"
        self.data = b"verified synthetic executable"
        self.url = "https://github.com/example/tool/releases/download/v1.0.11/bootstrap"
        self.artifact = {"url": self.url, "sha256": hashlib.sha256(self.data).hexdigest()}
        self.release = {"tag_name": "v1.0.11", "assets": [{
            "name": "bootstrap", "browser_download_url": self.url, "id": 123,
        }]}
        self.sleep = self.enterContext(patch.object(DOWNLOAD.time, "sleep"))
        self.enterContext(patch.object(DOWNLOAD.sys, "stderr", io.StringIO()))

    def http_error(self, status):
        return urllib.error.HTTPError(self.url, status, "synthetic error", {}, None)

    def acquire(self, responses):
        with patch.object(DOWNLOAD.urllib.request, "urlopen", side_effect=responses) as requests:
            DOWNLOAD.download(self.artifact, self.destination)
        return requests

    def test_direct_success_checks_digest_and_sets_private_executable_mode(self):
        requests = self.acquire([io.BytesIO(self.data)])
        self.assertEqual(self.destination.read_bytes(), self.data)
        self.assertEqual(self.destination.stat().st_mode & 0o777, 0o700)
        self.assertEqual(requests.call_args.args[0].full_url, self.url)
        self.assertEqual(requests.call_args.kwargs, {"timeout": 30})
        self.sleep.assert_not_called()

    def test_transient_http_and_transport_failures_retry_before_success(self):
        for error in (self.http_error(504), self.http_error(429),
                      urllib.error.URLError("connection reset"), TimeoutError(),
                      ConnectionResetError(),
                      http.client.IncompleteRead(b"partial")):
            with self.subTest(error=error):
                requests = self.acquire([error, io.BytesIO(self.data)])
                self.assertEqual(requests.call_count, 2)
                self.assertEqual(self.destination.read_bytes(), self.data)

    def test_interrupted_response_read_retries_without_publishing_partial_bytes(self):
        response = io.BytesIO(b"partial")
        with patch.object(response, "read", side_effect=http.client.IncompleteRead(b"partial")):
            requests = self.acquire([response, io.BytesIO(self.data)])
        self.assertEqual(requests.call_count, 2)
        self.assertEqual(self.destination.read_bytes(), self.data)

    def test_repeated_504_uses_exact_public_api_asset_without_credentials(self):
        requests = self.acquire([self.http_error(504) for _ in range(3)] + [
            io.BytesIO(json.dumps(self.release).encode()), io.BytesIO(self.data)])
        calls = [call.args[0] for call in requests.call_args_list]
        self.assertEqual([request.full_url for request in calls], [self.url] * 3 + [
            "https://api.github.com/repos/example/tool/releases/tags/v1.0.11",
            "https://api.github.com/repos/example/tool/releases/assets/123"])
        self.assertEqual(calls[-1].get_header("Accept"), "application/octet-stream")
        self.assertTrue(all(request.get_header("Authorization") is None for request in calls))
        self.assertEqual([call.args[0] for call in self.sleep.call_args_list], [1, 2])

    def test_nontransient_http_error_has_no_retry_or_fallback(self):
        for status in (401, 403, 404):
            with self.subTest(status=status):
                with patch.object(DOWNLOAD.urllib.request, "urlopen", side_effect=self.http_error(status)) as requests:
                    with self.assertRaises(urllib.error.HTTPError):
                        DOWNLOAD.download(self.artifact, self.destination)
                self.assertEqual(requests.call_count, 1)
                self.assertFalse(self.destination.exists())
        self.sleep.assert_not_called()

    def test_pinned_asset_id_avoids_unavailable_tag_metadata_and_checks_digest(self):
        self.artifact["asset_id"] = 123
        for data in (self.data, b"corrupt"):
            with self.subTest(valid=data == self.data):
                responses = [self.http_error(504) for _ in range(3)] + [io.BytesIO(data)]
                with patch.object(DOWNLOAD.urllib.request, "urlopen", side_effect=responses) as requests:
                    if data == self.data:
                        DOWNLOAD.download(self.artifact, self.destination)
                    else:
                        with self.assertRaisesRegex(ValueError, "digest mismatch"):
                            DOWNLOAD.download(self.artifact, self.destination)
                calls = [call.args[0] for call in requests.call_args_list]
                self.assertEqual([request.full_url for request in calls], [self.url] * 3 + [
                    "https://api.github.com/repos/example/tool/releases/assets/123"])
                self.assertTrue(all(request.get_header("Authorization") is None for request in calls))
                self.assertEqual(self.destination.read_bytes(), self.data)

    def test_invalid_pinned_asset_id_is_refused_before_api_access(self):
        for asset_id in (True, 0, -1, "123"):
            with self.subTest(asset_id=asset_id):
                self.artifact["asset_id"] = asset_id
                with patch.object(DOWNLOAD.urllib.request, "urlopen", side_effect=self.http_error(504)) as requests:
                    with self.assertRaisesRegex(ValueError, "invalid release asset ID"):
                        DOWNLOAD.download(self.artifact, self.destination)
                self.assertEqual(requests.call_count, 3)
                self.assertFalse(self.destination.exists())

    def test_api_transport_failure_has_bounded_attempts(self):
        with patch.object(DOWNLOAD.urllib.request, "urlopen", side_effect=self.http_error(504)) as requests:
            with self.assertRaises(urllib.error.HTTPError):
                DOWNLOAD.download(self.artifact, self.destination)
        self.assertEqual(requests.call_count, 6)
        self.assertFalse(self.destination.exists())

    def test_wrong_release_missing_duplicate_or_invalid_asset_fails_closed(self):
        variants = [dict(self.release, tag_name="v9"), dict(self.release, assets=[]),
                    dict(self.release, assets=self.release["assets"] * 2),
                    dict(self.release, assets=[dict(self.release["assets"][0], id="123")]),
                    dict(self.release, assets=[dict(self.release["assets"][0], browser_download_url="wrong")])]
        for release in variants:
            with self.subTest(release=release):
                responses = [self.http_error(504) for _ in range(3)] + [
                    io.BytesIO(json.dumps(release).encode())]
                with patch.object(DOWNLOAD.urllib.request, "urlopen", side_effect=responses) as requests:
                    with self.assertRaises(ValueError):
                        DOWNLOAD.download(self.artifact, self.destination)
                self.assertEqual(requests.call_count, 4)
                self.assertFalse(self.destination.exists())

    def test_digest_mismatch_never_writes_or_retries_direct_or_api_bytes(self):
        for fallback in (False, True):
            with self.subTest(fallback=fallback):
                self.destination.write_bytes(b"existing file")
                self.destination.chmod(0o600)
                responses = ([self.http_error(504) for _ in range(3)] + [
                    io.BytesIO(json.dumps(self.release).encode())] if fallback else [])
                with patch.object(DOWNLOAD.urllib.request, "urlopen", side_effect=responses + [io.BytesIO(b"corrupt")]) as requests:
                    with self.assertRaisesRegex(ValueError, "digest mismatch"):
                        DOWNLOAD.download(self.artifact, self.destination)
                self.assertEqual(requests.call_count, 5 if fallback else 1)
                self.assertEqual(self.destination.read_bytes(), b"existing file")
                self.assertEqual(self.destination.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
