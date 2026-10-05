"""Deterministic tests for the host-local read-only GitHub App gate."""

import importlib.util
import os
import pathlib
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
HELPER = ROOT / "roles" / "relay_runtime" / "files" / "relay-app-qualification.py"


def load_helper():
    spec = importlib.util.spec_from_file_location("relay_app_qualification", HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AppQualificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.helper = load_helper()

    def test_wrong_app_identity_fails_closed(self):
        with self.assertRaises(self.helper.QualificationFailure):
            self.helper.validate_app_identity({"id": 1002, "slug": "wrong"}, {"app_id": "1001", "slug": "expected"})

    def test_wrong_installation_or_repository_app_fails_closed(self):
        config = {"app_id": "1001", "slug": "expected", "installation_id": "2001"}
        with self.assertRaises(self.helper.QualificationFailure):
            self.helper.validate_installation({"id": 1, "app_id": 1001, "app_slug": "expected"}, config, "REPOSITORY_INSTALLATION")
        with self.assertRaises(self.helper.QualificationFailure):
            self.helper.validate_installation({"id": 2001, "app_id": 1002, "app_slug": "other"}, config, "APP_INSTALLATION")

    def test_insufficient_and_broader_permissions_fail_closed(self):
        required = {"metadata": "read"}
        with self.assertRaises(self.helper.QualificationFailure):
            self.helper.validate_permissions({"metadata": "none"}, required, "TOKEN")
        with self.assertRaises(self.helper.QualificationFailure):
            self.helper.validate_permissions({"metadata": "read", "pull_requests": "write", "administration": "write"}, required, "TOKEN")
        with self.assertRaises(self.helper.QualificationFailure):
            self.helper.validate_permissions({"metadata": "read", "pull_requests": "admin"}, required, "TOKEN")

    def test_installation_token_repository_selector_uses_name_not_owner_name(self):
        self.assertEqual(self.helper.repository_name("example/relay-consumer"), "relay-consumer")

    def test_static_contract_has_no_mutation_endpoints_or_secret_output(self):
        source = HELPER.read_text(encoding="utf-8")
        self.assertIn('"GET"', source)
        self.assertIn('"POST"', source)
        self.assertIn("access_tokens", source)
        self.assertNotIn("/pulls/", source)
        self.assertNotIn("/check-runs", source)
        self.assertNotIn("/contents", source)
        self.assertNotIn("print(token", source)
        self.assertNotIn("print(app_jwt", source)
        self.assertIn("PERSISTENT_TOKEN_VARIABLE_FORBIDDEN", source)

    def test_wrappers_keep_separate_boundaries_and_read_only_contract(self):
        reviewer = (ROOT / "roles" / "relay_runtime" / "templates" / "relay-reviewer-app-qualification.j2").read_text(encoding="utf-8")
        writer = (ROOT / "roles" / "relay_controller" / "templates" / "relay-writer-app-qualification.j2").read_text(encoding="utf-8")
        self.assertIn("relay_reviewer_credential_env_file", reviewer)
        self.assertIn("relay_writer_credential_env_file", writer)
        self.assertIn("id -un", reviewer)
        self.assertIn("id -u", writer)
        self.assertIn("RELAY_EXPECTED_WRITE_PERMISSION_NAMES", reviewer)
        self.assertIn("RELAY_EXPECTED_WRITE_PERMISSION_NAMES", writer)
        self.assertIn("RELAY_TOKEN_PERMISSIONS='metadata:read'", reviewer)
        self.assertIn("RELAY_TOKEN_PERMISSIONS='metadata:read'", writer)
        self.assertNotIn("GITHUB_WRITER_TOKEN=", reviewer)
        self.assertNotIn("GITHUB_REVIEWER_TOKEN=", writer)

    def test_writer_contract_includes_only_admitted_routing_write_permissions(self):
        self.assertEqual(
            self.helper.EXPECTED_WRITE_PERMISSION_NAMES["writer"],
            {"contents", "issues", "pull_requests", "workflows"},
        )
        writer = (ROOT / "roles" / "relay_controller" / "templates" / "relay-writer-app-qualification.j2").read_text(encoding="utf-8")
        self.assertIn("RELAY_EXPECTED_WRITE_PERMISSION_NAMES='contents,issues,pull_requests,workflows'", writer)
        self.assertNotIn("RELAY_EXPECTED_WRITE_PERMISSION_NAMES='contents,issues,pull_requests'", writer)

    def reviewer_permissions(self):
        with mock.patch.dict(os.environ, {"RELAY_EXPECTED_WRITE_PERMISSION_NAMES": "pull_requests,checks,issues"}, clear=False):
            return self.helper.expected_installation_permissions({"role": "reviewer"})

    def test_reviewer_contract_requires_actions_read_and_issues_write(self):
        self.assertEqual(
            self.helper.EXPECTED_WRITE_PERMISSION_NAMES["reviewer"],
            {"pull_requests", "checks", "issues"},
        )
        self.assertEqual(
            self.helper.EXPECTED_READ_PERMISSION_NAMES["reviewer"],
            {"metadata", "actions"},
        )
        reviewer = (ROOT / "roles" / "relay_runtime" / "templates" / "relay-reviewer-app-qualification.j2").read_text(encoding="utf-8")
        self.assertIn("RELAY_EXPECTED_WRITE_PERMISSION_NAMES='pull_requests,checks,issues'", reviewer)
        required = self.reviewer_permissions()
        self.assertEqual(required, {
            "metadata": "read", "actions": "read", "pull_requests": "write",
            "checks": "write", "issues": "write",
        })
        self.assertEqual(self.helper.validate_permissions(required, required, "APP_INSTALLATION", exact=True), required)

    def test_reviewer_missing_or_weaker_permission_fails_closed(self):
        required = self.reviewer_permissions()
        for name, level in required.items():
            with self.subTest(name=name, case="missing"):
                actual = {key: value for key, value in required.items() if key != name}
                with self.assertRaisesRegex(self.helper.QualificationFailure, "PERMISSION_INSUFFICIENT"):
                    self.helper.validate_permissions(actual, required, "APP_INSTALLATION", exact=True)
            with self.subTest(name=name, case="weaker"):
                actual = {**required, name: "read" if level == "write" else "none"}
                with self.assertRaisesRegex(self.helper.QualificationFailure, "PERMISSION_INSUFFICIENT"):
                    self.helper.validate_permissions(actual, required, "APP_INSTALLATION", exact=True)

    def test_reviewer_unexpected_or_stronger_permission_fails_closed(self):
        required = self.reviewer_permissions()
        for name in ("contents", "workflows", "administration", "repository_projects"):
            for level in ("none", "read", "write", "admin"):
                with self.subTest(name=name, level=level):
                    with self.assertRaises(self.helper.QualificationFailure):
                        self.helper.validate_permissions({**required, name: level}, required, "APP_INSTALLATION", exact=True)
        for name in ("metadata", "actions"):
            with self.subTest(name=name, case="stronger"):
                with self.assertRaisesRegex(self.helper.QualificationFailure, "PERMISSION_SCOPE_TOO_BROAD"):
                    self.helper.validate_permissions({**required, name: "write"}, required, "APP_INSTALLATION", exact=True)

    def test_writer_additional_read_permission_remains_accepted(self):
        with mock.patch.dict(os.environ, {"RELAY_EXPECTED_WRITE_PERMISSION_NAMES": "contents,issues,pull_requests,workflows"}, clear=False):
            required = self.helper.expected_installation_permissions({"role": "writer"})
        actual = {**required, "actions": "read"}
        self.assertEqual(self.helper.validate_permissions(actual, required, "APP_INSTALLATION"), actual)

    def test_reviewer_qualification_checks_exact_installation_and_probe_permissions(self):
        required = self.reviewer_permissions()
        config = {"role": "reviewer", "app_id": "1001", "slug": "expected",
                  "installation_id": "2001", "repository": "example/relay-consumer",
                  "expected_actor": "expected[bot]"}
        installation = {"id": 2001, "app_id": 1001, "app_slug": "expected",
                        "repository_selection": "selected", "permissions": required}
        for unexpected_at in (None, "installation", "token"):
            with self.subTest(unexpected_at=unexpected_at):
                responses = [
                    {"id": 1001, "slug": "expected"},
                    {**installation, "permissions": {**required, "contents": "read"}} if unexpected_at == "installation" else installation,
                    installation,
                    {"token": "synthetic-token", "expires_at": "synthetic-expiry",
                     "permissions": {"metadata": "read", "actions": "read"} if unexpected_at == "token" else {"metadata": "read"}},
                    {"full_name": config["repository"]},
                ]
                with mock.patch.dict(os.environ, {
                    "RELAY_EXPECTED_WRITE_PERMISSION_NAMES": "pull_requests,checks,issues",
                    "RELAY_TOKEN_PERMISSIONS": "metadata:read",
                }, clear=False), mock.patch.object(self.helper, "create_app_jwt", return_value="synthetic-jwt"), \
                        mock.patch.object(self.helper, "parse_expiry", return_value=3600), \
                        mock.patch.object(self.helper, "request_json", side_effect=responses) as request:
                    if unexpected_at:
                        with self.assertRaisesRegex(self.helper.QualificationFailure, "PERMISSION_SCOPE_TOO_BROAD"):
                            self.helper.qualify(config)
                    else:
                        result = self.helper.qualify(config)
                        self.assertEqual(result["token_permissions"], "metadata:read")
                        self.assertEqual(request.call_args_list[3].kwargs["body"], {
                            "repositories": ["relay-consumer"], "permissions": {"metadata": "read"},
                        })
                        self.assertEqual(request.call_args_list[-1].args[:2], ("GET", "/repos/example/relay-consumer"))

    def test_writer_missing_workflow_permission_fails_closed(self):
        with mock.patch.dict(os.environ, {"RELAY_EXPECTED_WRITE_PERMISSION_NAMES": "contents,issues,pull_requests,workflows"}, clear=False):
            required = self.helper.expected_installation_permissions({"role": "writer"})
        self.assertEqual(
            required,
            {"metadata": "read", "contents": "write", "issues": "write", "pull_requests": "write", "workflows": "write"},
        )
        with self.assertRaises(self.helper.QualificationFailure):
            self.helper.validate_permissions(
                {"metadata": "read", "contents": "write", "issues": "write", "pull_requests": "write"},
                required,
                "APP_INSTALLATION",
            )


if __name__ == "__main__":
    unittest.main()
