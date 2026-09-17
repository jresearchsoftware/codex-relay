"""Tests for the bounded current-production diagnostic path."""

import importlib.util
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "production-diagnostic.py"
SPEC = importlib.util.spec_from_file_location("production_diagnostic", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class ProductionDiagnosticTests(unittest.TestCase):
    def test_cli_uses_configured_paths_and_flat_installed_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            current = root / 'install/current'
            controller = current / 'reviewed-source/controller/src'
            controller.mkdir(parents=True)
            (controller / 'entrypoint.mjs').write_text('')
            (current / 'artifact-manifest.json').write_text(json.dumps({'commit': 'a' * 40}))
            result = subprocess.run(['python3', str(MODULE_PATH), '--issue-number', '293',
                '--repository', 'canary/consumer', '--runner-user', 'nobody',
                '--install-root', str(root / 'install'), '--config-root', str(root / 'config'),
                '--state-root', str(root / 'state')], text=True, capture_output=True, check=True)
            evidence = json.loads(result.stdout)
            self.assertEqual(evidence['repository'], 'canary/consumer')
            self.assertEqual(evidence['currentRelease']['manifest']['commit'], 'a' * 40)
            self.assertEqual(evidence['runtimeLayout']['routingEntrypoint'], 'present')

    def test_manifest_exposes_pinned_dependency_without_untrusted_nested_fields(self):
        lock = {'repository': 'example/codex-relay', 'commit': 'a' * 40, 'tree': 'b' * 40, 'archiveSha256': 'c' * 64}
        lock['credential'] = 'private-untrusted-value'
        manifest = MODULE.safe_manifest({'commit': 'c' * 40, 'relayDependency': lock})
        self.assertEqual(manifest['relayDependency'], {
            key: lock[key] for key in ('repository', 'commit', 'tree', 'archiveSha256')
        })
        self.assertNotIn('private-untrusted-value', json.dumps(manifest))
        lock.update(repository='untrusted-value', tree='not-a-sha', archiveSha256='untrusted-value')
        self.assertEqual(MODULE.safe_manifest({'relayDependency': lock})['relayDependency'], {'commit': lock['commit']})

    def test_issue_projection_is_exact_and_filters_unrelated_bundles(self):
        issue_body_sha256 = "b" * 64
        request = {
            "target": "issue",
            "issueNumber": 235,
            "issueBodySha256": issue_body_sha256,
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            claim_root = root / "claims"
            dispatch_root = root / "dispatch"
            debug_root = root / "debug"
            config_root = root / "config"
            install_root = root / "install"
            claim_root.mkdir()
            dispatch_root.mkdir()
            debug_root.mkdir()
            config_root.mkdir()
            (install_root / "current").mkdir(parents=True)
            (claim_root / "claims.json").write_text(json.dumps({
                "private-issue-operation-key": {
                    **request,
                    "claimId": "claim-235",
                    "attemptId": "attempt-235",
                    "phase": "failed",
                    "failureCode": "CODEX_NONZERO_EXIT",
                    "failureDiagnostic": {
                        "code": "CODEX_NONZERO_EXIT",
                        "boundary": "codex-child",
                        "childStarted": True,
                        "childExitCode": 1,
                        "diagnosticStore": {"code": "stored", "executionId": "exec-235"},
                    },
                    "body": "do-not-publish",
                },
                "foreign-operation": {
                    "target": "issue",
                    "issueNumber": 236,
                    "issueBodySha256": "c" * 64,
                    "claimId": "claim-236",
                    "failureCode": "FOREIGN_FAILURE",
                },
            }), encoding="utf-8")
            (debug_root / "matching.json").write_text(json.dumps({
                "executionId": "exec-235",
                "mode": "normal",
                "phase": "codex-child",
                "classification": "CODEX_NONZERO_EXIT",
                "process": {"exitCode": 1, "signal": None},
                "stderr": '{"code":"CODEX_LAUNCHER_ACCESS_TOKEN_INVALID","token":"MY_SECRET_TOKEN","credential":"INTERNAL_API_CREDENTIAL_ABC123","message":"do-not-publish"}',
            }), encoding="utf-8")
            (debug_root / "foreign.json").write_text(json.dumps({
                "executionId": "exec-236",
                "classification": "FOREIGN_FAILURE",
            }), encoding="utf-8")
            result = MODULE.build_diagnostic(
                request,
                claim_root=claim_root,
                dispatch_root=dispatch_root,
                debug_root=debug_root,
                config_root=config_root,
                install_root=install_root,
            )
            encoded = json.dumps(result)
            self.assertEqual(result["target"], "issue")
            self.assertEqual(result["continuationStateCheck"], {"status": "not-applicable", "target": "issue"})
            self.assertEqual(len(result["claimRecords"]), 1)
            self.assertIn("CODEX_NONZERO_EXIT", encoded)
            self.assertIn("exec-235", encoded)
            self.assertNotIn("FOREIGN_FAILURE", encoded)
            self.assertNotIn("do-not-publish", encoded)
            self.assertNotIn('"body"', encoded)
            self.assertEqual(len(result["diagnosticBundles"]), 1)
            self.assertEqual(
                result["diagnosticBundles"][0]["stderrCodeCandidates"],
                ["CODEX_LAUNCHER_ACCESS_TOKEN_INVALID"],
            )
            self.assertNotIn("MY_SECRET_TOKEN", encoded)
            self.assertNotIn("INTERNAL_API_CREDENTIAL_ABC123", encoded)

    def test_issue_parser_requires_exact_body_identity(self):
        digest = hashlib.sha256(b"issue").hexdigest()
        self.assertEqual(
            MODULE.parse_args(["--issue-number", "235", "--issue-body-sha256", digest]),
            {"target": "issue", "issueNumber": 235, "issueBodySha256": digest},
        )
        with self.assertRaises(SystemExit):
            MODULE.parse_args(["--issue-number", "235", "--issue-body-sha256", "not-a-digest"])

    def test_issue_number_fallback_marks_body_drift_without_broadening_to_other_issues(self):
        request = {"target": "issue", "issueNumber": 235}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            claim_root = root / "claims"
            debug_root = root / "debug"
            claim_root.mkdir()
            debug_root.mkdir()
            (claim_root / "claims.json").write_text(json.dumps({
                "issue-235": {"target": "issue", "issueNumber": 235, "issueBodySha256": "d" * 64, "failureCode": "CODEX_NONZERO_EXIT", "dispatchedAt": "2026-09-03T20:58:09Z"},
                "issue-236": {"target": "issue", "issueNumber": 236, "issueBodySha256": "e" * 64, "failureCode": "FOREIGN_FAILURE"},
            }), encoding="utf-8")
            (debug_root / "matching.json").write_text(json.dumps({
                "executionId": "exec-window",
                "startedAt": "2026-09-03T20:58:10Z",
                "classification": "CODEX_NONZERO_EXIT",
            }), encoding="utf-8")
            result = MODULE.build_diagnostic(
                request,
                claim_root=claim_root,
                dispatch_root=root / "dispatch",
                debug_root=debug_root,
                config_root=root / "config",
                install_root=root / "install",
            )
            encoded = json.dumps(result)
            self.assertEqual(len(result["claimRecords"]), 1)
            self.assertEqual(result["claimRecords"][0]["match"], "issue-number")
            self.assertIn("d" * 64, encoded)
            self.assertNotIn("FOREIGN_FAILURE", encoded)
            self.assertEqual(result["diagnosticCorrelation"], {"status": "bounded-claim-window", "candidateCount": 1})
            self.assertEqual(result["diagnosticBundles"][0]["match"], "bounded-claim-window")

    def test_private_stderr_classifier_returns_codes_only(self):
        self.assertEqual(MODULE.classify_private_stderr("sudo: unable to execute relay-codex: Permission denied"), "LAUNCHER_PERMISSION_DENIED")
        self.assertEqual(MODULE.classify_private_stderr("spawn /opt/relay-codex ENOENT"), "LAUNCHER_PATH_UNAVAILABLE")
        self.assertEqual(MODULE.codes_in_text('{"code":"CODEX_LAUNCHER_ACCESS_TOKEN_INVALID","token":"secret"}'), ["CODEX_LAUNCHER_ACCESS_TOKEN_INVALID"])
        self.assertEqual(MODULE.codes_in_text("launcher failed with MY_SECRET_TOKEN"), [])
        self.assertEqual(MODULE.codes_in_text("credential=INTERNAL_API_CREDENTIAL_ABC123"), [])
        self.assertEqual(MODULE.classify_private_error_signature("Error [ERR_MODULE_NOT_FOUND]"), "MODULE_IMPORT_MISSING")
        self.assertEqual(MODULE.classify_private_error_signature("TypeError: value is not a function"), "RUNTIME_API_MISMATCH")
        self.assertEqual(MODULE.syntax_error_location("file:///opt/relay-codex:123:45"), {"line": 123, "column": 45})

    def test_launcher_preflight_requires_the_wrapper_and_module_pair(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "relay-codex").write_text("#!/bin/sh\n", encoding="utf-8")
            result = MODULE.launcher_preflight(root)
            self.assertEqual(result["launcher"], "present")
            self.assertEqual(result["launcherModule"], "absent")
            self.assertEqual(result["code"], "LAUNCHER_MODULE_FILE_MISSING")

    def test_launcher_preflight_checks_module_mode_through_the_explicit_wrapper_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "relay-codex").write_text(
                "#!/bin/sh\nexec /usr/bin/node --experimental-default-type=module "
                "'/opt/codex-relay/relay-codex.mjs' \"$@\"\n",
                encoding="utf-8",
            )
            (root / "relay-codex.mjs").write_text("export {};\n", encoding="utf-8")
            completed = SimpleNamespace(returncode=0, stdout="", stderr="")
            with patch.object(MODULE.subprocess, "run", return_value=completed) as run:
                result = MODULE.launcher_preflight(root)

            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["code"], "LAUNCHER_SYNTAX_VALID")
            self.assertTrue(result["wrapperModuleInvocation"])
            self.assertEqual(
                run.call_args.args[0],
                [
                    "/usr/bin/node",
                    "--experimental-default-type=module",
                    "--check",
                    str(root / "relay-codex.mjs"),
                ],
            )

    @unittest.skipUnless(
        os.name != "nt"
        and Path("/bin/sh").is_file()
        and Path("/usr/bin/node").is_file(),
        "requires the POSIX Debian launcher runtime",
    )
    def test_production_wrapper_executes_esm_and_classifies_legacy_extensionless_failure(self):
        fixture_source = (
            'import { argv } from "node:process";\n'
            'process.stdout.write(argv.slice(2).join("|"));\n'
        )
        launcher_environment = {
            "PATH": "/usr/bin:/bin",
            "LANG": "C",
            "LC_ALL": "C",
            "HOME": "/tmp",
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            module = root / "relay-codex.mjs"
            legacy_launcher = root / "relay-codex-legacy"
            wrapper = root / "relay-codex"
            wrapper_template = (
                ROOT
                / "roles"
                / "relay_codex_runtime"
                / "templates"
                / "relay-codex-launcher-wrapper.sh.j2"
            ).read_text(encoding="utf-8")

            module.write_text(fixture_source, encoding="utf-8")
            legacy_launcher.write_text(
                "#!/usr/bin/node\n" + fixture_source,
                encoding="utf-8",
            )
            legacy_launcher.chmod(0o755)
            wrapper.write_text(
                wrapper_template.replace("{{ relay_install_root }}", str(root)),
                encoding="utf-8",
            )
            wrapper.chmod(0o755)

            legacy_result = subprocess.run(
                [str(legacy_launcher), "fixture-arg"],
                cwd=str(root),
                env=launcher_environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(legacy_result.returncode, 0)
            self.assertIn("SyntaxError", legacy_result.stderr)
            self.assertEqual(
                MODULE.classify_private_stderr(legacy_result.stderr),
                "LAUNCHER_RUNTIME_EXCEPTION",
            )
            error_signature = MODULE.classify_private_error_signature(
                legacy_result.stderr
            )
            self.assertIn(error_signature, {"RUNTIME_SYNTAX_INVALID", "NODE_SYNTAXERROR"})

            repaired_result = subprocess.run(
                [str(wrapper), "fixture-arg"],
                cwd=str(root),
                env=launcher_environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(repaired_result.returncode, 0, repaired_result.stderr)
            self.assertEqual(repaired_result.stdout, "fixture-arg")
            self.assertEqual(repaired_result.stderr, "")

            safe_diagnostic = json.dumps({
                "stage": "launcher",
                "classification": MODULE.classify_private_stderr(legacy_result.stderr),
                "errorSignature": error_signature,
            })
            self.assertNotIn(legacy_result.stderr, safe_diagnostic)
            self.assertNotIn(repaired_result.stdout, safe_diagnostic)

    def test_projection_keeps_failure_codes_and_omits_protected_content(self):
        request = {
            "pullRequest": 185,
            "reviewId": 5016032994,
            "reviewedHeadSha": "c457bee902601809e1afb8dba48346b18bcb4320",
            "changeRequestId": "CR-099W-P7E-001",
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            claim_root = root / "claims"
            dispatch_root = root / "dispatch"
            debug_root = root / "debug"
            config_root = root / "config"
            install_root = root / "install"
            claim_root.mkdir()
            (dispatch_root / "remediation").mkdir(parents=True)
            (dispatch_root / "evidence").mkdir(parents=True)
            debug_root.mkdir()
            config_root.mkdir()
            (install_root / "current").mkdir(parents=True)
            (claim_root / "claims.json").write_text(json.dumps({
                "private-operation-key": {
                    **request,
                    "claimId": "claim-185",
                    "target": "pull_request",
                    "phase": "failed",
                    "failureCode": "DISPATCH_WORKER_FAILED",
                    "executionConfirmed": False,
                    "body": "do-not-publish",
                    "failureDiagnostic": {"code": "DISPATCH_WORKER_FAILED", "childStarted": True, "diagnosticStore": {"executionId": "execution-185"}},
                    "blockedMessage": "token=do-not-publish",
                }
            }), encoding="utf-8")
            (dispatch_root / "remediation" / "remediation-state.json").write_text(json.dumps({
                "private-operation-key": {
                    **request,
                    "phase": "abandoned",
                    "continuation": {
                        "status": "ready",
                        "generation": 7,
                        "priorFailureCode": "GIT_COMMAND_FAILED",
                    },
                    "abandonedAttempt": {
                        "phase": "blocked",
                        "evidence": {"blockedCode": "GIT_COMMAND_FAILED"},
                    },
                }
            }), encoding="utf-8")
            (debug_root / "execution.json").write_text(json.dumps({
                "executionId": "execution-185",
                "mode": "normal",
                "phase": "worker",
                "classification": "ENTRYPOINT_FAILED",
                "process": {"exitCode": 1, "signal": None},
                "stderr": '{"code":"RESERVATION_CONTINUATION_INVALID","body":"omit"}',
                "stdout": "omit",
            }), encoding="utf-8")
            result = MODULE.build_diagnostic(
                request,
                claim_root=claim_root,
                dispatch_root=dispatch_root,
                debug_root=debug_root,
                config_root=config_root,
                install_root=install_root,
            )
            encoded = json.dumps(result)
            self.assertIn("DISPATCH_WORKER_FAILED", encoded)
            self.assertIn("RESERVATION_CONTINUATION_INVALID", encoded)
            self.assertNotIn("do-not-publish", encoded)
            self.assertNotIn('"body"', encoded)
            self.assertEqual(result["protectedBodies"], "omitted")
            self.assertEqual(result["workerPreflight"]["status"], "blocked")
            self.assertEqual(result["workerPreflight"]["code"], "WORKER_PREFLIGHT_INPUT_MISSING")
            self.assertEqual(result["launcherPreflight"]["status"], "blocked")
            self.assertEqual(result["launcherPreflight"]["code"], "LAUNCHER_FILE_MISSING")
            self.assertNotIn("do-not-publish", encoded)

    def test_empty_production_state_is_a_read_only_result_not_a_false_success(self):
        request = {
            "pullRequest": 185,
            "reviewId": 5016032994,
            "reviewedHeadSha": "c457bee902601809e1afb8dba48346b18bcb4320",
            "changeRequestId": "CR-099W-P7E-001",
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = MODULE.build_diagnostic(
                request,
                claim_root=root / "claims",
                dispatch_root=root / "dispatch",
                debug_root=root / "debug",
                config_root=root / "config",
                install_root=root / "install",
            )
            self.assertEqual(result["claimRecords"], [])
            self.assertEqual(result["remediationRecords"], [])
            self.assertIn(result["fileStatus"]["claims"], {"absent", "unreadable"})
            self.assertEqual(result["workerPreflight"]["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
