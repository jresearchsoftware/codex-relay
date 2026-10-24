#!/usr/bin/env python3
"""Exercise the selected Shared Publisher against exact Relay Git bytes.

Only disposable fixture repositories are written. Synthetic GitHub responses
qualify integration behavior, never live CI, credentials or publication. The
upstream CLI entrypoint and report writer run unchanged in process; only its
read-only API transport is replaced. Native staging has separate qualification.
"""
import argparse
from contextlib import ExitStack, redirect_stdout
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[1]
P = None
SOURCE_SHA = None
PUBLISHER_SHA = None
BINDING = None
SOURCE_FILES = None
PUBLISHER_WORKFLOW = None


def git(root, *arguments):
    return subprocess.check_output(
        ["git", "-C", str(root), *map(str, arguments)], stderr=subprocess.PIPE
    )


def full_sha(value):
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise argparse.ArgumentTypeError("a full lowercase commit SHA is required")
    return value


class RelayPublisherTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="relay-publisher-integration-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.source = self.directory / "source"
        self.source.mkdir()
        # No inherited tokens, credential helpers, hooks or network Git protocols.
        environment = {
            key: value for key, value in os.environ.items()
            if key in ("PATH", "SYSTEMROOT", "TMP", "TEMP", "LANG", "LC_ALL")
        }
        environment.update(
            GIT_CONFIG_NOSYSTEM="1",
            GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0",
            GIT_ALLOW_PROTOCOL="file", GIT_AUTHOR_NAME="Disposable fixture",
            GIT_AUTHOR_EMAIL="fixture@example.invalid",
            GIT_COMMITTER_NAME="Disposable fixture",
            GIT_COMMITTER_EMAIL="fixture@example.invalid",
            GITHUB_EVENT_NAME="workflow_run",
            # The managed worker checkout can be owned by another UID. Scope
            # this read-only source exception to process environment only.
            GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="safe.directory",
            GIT_CONFIG_VALUE_0=str(SOURCE),
        )
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, environment, clear=True).start()
        git(self.source, "init", "-q", "-b", "main")
        self.binding = copy.deepcopy(BINDING)
        self.package = self.binding["packages"][0]
        self.root = self.source / self.package["root"]
        for relative, contents in SOURCE_FILES.items():
            path = self.source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)
        self.baseline = self.commit()
        self.calls = []
        self.run_change = lambda run: run
        self.trigger_change = lambda run: run
        self.event = self.directory / "event.json"
        self.event.write_text(json.dumps({"workflow_run": {"id": 721}}))
        os.environ["GITHUB_EVENT_PATH"] = str(self.event)

    def commit(self):
        git(self.source, "add", ".")
        git(self.source, "commit", "-qm", "Disposable integration fixture")
        return git(self.source, "rev-parse", "HEAD").decode().strip()

    def changed_version(self):
        manifest = self.root / "vibe.toml"
        old = tomllib.loads(manifest.read_text())["package"]["version"]
        major, minor, patch_number = map(int, old.split("."))
        new = f"{major}.{minor}.{patch_number + 1}"
        contents, count = re.subn(
            r'(?m)^version = "' + re.escape(old) + r'"$',
            f'version = "{new}"', manifest.read_text(),
        )
        self.assertEqual(count, 1)
        manifest.write_text(contents)
        return new

    def ci_get(self, api, path):
        self.assertEqual(api.repository, self.binding["repository"])
        self.assertIsNone(api.token)
        self.calls.append(path)
        run = self.run_change({
            "id": 721, "head_sha": self.selected_sha, "event": "push",
            "head_branch": self.binding["branch"], "status": "completed",
            "conclusion": "success", "workflow_id": 835,
            "path": self.binding["ci_workflow"],
            "head_repository": {"id": self.binding["repository_id"]},
            "repository": {"id": self.binding["repository_id"]},
            "html_url": "https://github.com/fixture/disposable/actions/runs/721",
        })
        if path == "actions/runs/721":
            return self.trigger_change(run)
        self.assertEqual(
            path, f"actions/runs?head_sha={self.selected_sha}&event=push&per_page=100&page=1"
        )
        return {"workflow_runs": [run]}

    def cli(self, revision, operation="plan", expect=0, ci=False):
        self.selected_sha = revision
        self.calls = []
        report_path = self.directory / "report.json"
        report_path.unlink(missing_ok=True)
        staging = self.directory / "must-not-stage"
        arguments = [
            str(P.__file__), operation, "--source", str(self.source),
            "--source-sha", revision, "--main", "main",
            "--binding", "vibe-publisher.json", "--package", self.package["coordinate"],
            "--report", str(report_path),
        ]
        if operation == "stage":
            arguments += ["--vibe", str(self.directory / "absent-native-binary"),
                          "--directory", str(staging)]
        if operation == "check":
            # Candidate checks compare against the supplied exact accepted base.
            git(self.source, "update-ref", "refs/heads/accepted", self.baseline)
            arguments[arguments.index("--main") + 1] = "accepted"
            arguments += ["--base", self.baseline]
        with ExitStack() as stack:
            stack.enter_context(patch.object(sys, "argv", arguments))
            stack.enter_context(redirect_stdout(io.StringIO()))
            for name in ("remote_refs", "DestinationAPI", "native_environment"):
                stack.enter_context(patch.object(P, name, side_effect=AssertionError(
                    "destination/native access is forbidden in planning and no-op staging"
                )))
            stack.enter_context(patch.object(P.urllib.request, "urlopen", side_effect=AssertionError("no network")))
            stack.enter_context(patch.object(P.urllib.request, "build_opener", side_effect=AssertionError("no network")))
            stack.enter_context(patch.object(
                P.GitHub, "get", autospec=True,
                side_effect=self.ci_get if ci else AssertionError("no API for this transition"),
            ))
            self.assertEqual(P.main(), expect)
        report = json.loads(report_path.read_text())
        self.assertEqual(report["publisher"], {
            "repository": "jresearchsoftware/shared-governance", "sha": PUBLISHER_SHA,
        })
        self.assertEqual(report["source_sha"], revision)
        self.assertEqual(len(report["packages"]), 1)
        self.assertEqual(report["packages"][0]["source_sha"], revision)
        self.assertEqual(report["packages"][0]["destination"], self.package["destination"])
        self.assertFalse(staging.exists())
        return report["packages"][0]

    def test_exact_relay_export_and_vendored_snapshot(self):
        files, receipt = P.snapshot(SOURCE, SOURCE_SHA, BINDING["packages"][0])
        copied, copied_receipt = P.snapshot(self.source, self.baseline, self.package)
        self.assertEqual(receipt["source_revision"], SOURCE_SHA)
        self.assertEqual(receipt["payload_sha256"], copied_receipt["payload_sha256"])
        self.assertEqual(set(files), {*self.package["files"], "DISTRIBUTION.json"})
        vendored = [name for name in self.package["files"] if name.startswith("vibevm/vibedeps/")]
        self.assertTrue(vendored, "the actual Relay export must include its approved vendored snapshot")
        for name in self.package["files"]:
            self.assertEqual(files[name], copied[name], name)
            self.assertEqual(files[name], SOURCE_FILES[self.package["root"] + "/" + name], name)

    def test_selected_reusable_workflow_keeps_independent_immutable_checkouts(self):
        # Inspect the caller-selected upstream workflow, not a copied local fixture.
        # Step IDs, directory names and shell commands remain upstream-owned.
        def context_value(key, expression):
            return (r"(?m)^\s*" + key + r":\s*['\"]?\$\{\{\s*"
                    + re.escape(expression) + r"\s*\}\}['\"]?\s*$")

        steps = re.split(r"(?m)^\s+- ", PUBLISHER_WORKFLOW)
        publisher_step = next(step for step in steps
                              if re.search(context_value("repository", "job.workflow_repository"), step))
        producer_step = next(step for step in steps
                             if re.search(context_value("ref", "inputs.source_sha"), step))
        self.assertNotEqual(publisher_step, producer_step)
        for step in (publisher_step, producer_step):
            self.assertRegex(step, r"(?m)^\s*uses: actions/checkout@[0-9a-f]{40}\b")
            self.assertRegex(step, r"(?m)^\s*persist-credentials: false\s*$")
        self.assertRegex(publisher_step, context_value("ref", "job.workflow_sha"))
        inputs = PUBLISHER_WORKFLOW.split("    inputs:\n", 1)[1].split("    secrets:\n", 1)[0]
        self.assertNotRegex(inputs, r"(?m)^      (publisher_sha|policy_sha):")

    def test_non_package_transition_never_queries_or_stages(self):
        (self.source / "outside-package.txt").write_text("Synthetic repository-only change.\n")
        revision = self.commit()
        for operation in ("plan", "check", "stage"):
            with self.subTest(operation=operation):
                self.assertEqual(self.cli(revision, operation)["status"], "NO_PACKAGE_CHANGE")
                self.assertEqual(self.calls, [])
        # A later factual commit must not opportunistically publish an earlier
        # package bump whose release may still be pending.
        self.changed_version()
        self.commit()
        (self.source / "outside-package.txt").write_text("Later repository-only change.\n")
        self.assertEqual(self.cli(self.commit(), "stage")["status"], "NO_PACKAGE_CHANGE")
        self.assertEqual(self.calls, [])
        binding = copy.deepcopy(self.binding)
        binding["packages"][0]["redistribution"]["status"] = "unresolved"
        (self.source / "vibe-publisher.json").write_text(json.dumps(binding))
        self.assertEqual(self.cli(self.commit(), "stage")["status"], "NO_PACKAGE_CHANGE")
        self.assertEqual(self.calls, [])

    def test_same_version_payload_mutation_is_blocked_without_ci(self):
        readme = self.root / "README.md"
        readme.write_text(readme.read_text() + "\nSynthetic changed payload.\n")
        row = self.cli(self.commit(), expect=1)
        self.assertEqual(row["reason_code"], "PACKAGE_VERSION_REUSE")

    def test_exact_source_survives_later_head_and_dirty_worktree(self):
        version = self.changed_version()
        selected = self.commit()
        expected = P.snapshot(self.source, selected, self.package)[1]
        (self.root / "README.md").write_text("Later committed payload must not be selected.\n")
        self.commit()
        (self.root / "vibe.toml").write_text("invalid dirty manifest must not be read")
        (self.source / "vibe-publisher.json").write_text("invalid dirty binding must not be read")
        row = self.cli(selected, ci=True)
        self.assertEqual(row["status"], "READY")
        self.assertEqual(row["version"], version)
        self.assertEqual(row["payload_sha256"], expected["payload_sha256"])
        self.assertEqual(row["acceptance"][0]["source_sha"], selected)
        self.assertIn("actions/runs/721", self.calls)

    def test_new_version_qualifies_exact_ci_and_rejects_identity_mismatches(self):
        self.changed_version()
        revision = self.commit()
        self.assertEqual(self.cli(revision, "check")["status"], "CANDIDATE_VALID")
        self.assertEqual(self.calls, [])
        self.assertEqual(self.cli(revision, ci=True)["status"], "READY")
        for field, wrong in (
            ("head_sha", "0" * 40), ("head_branch", "other"),
            ("path", ".github/workflows/other.yml"),
            ("head_repository", {"id": self.binding["repository_id"] + 1}),
            ("repository", {"id": self.binding["repository_id"] + 1}),
            ("event", "pull_request"), ("status", "in_progress"),
            ("conclusion", "failure"),
        ):
            with self.subTest(field=field):
                self.run_change = lambda run, field=field, wrong=wrong: {**run, field: wrong}
                row = self.cli(revision, expect=1, ci=True)
                self.assertEqual(row["reason_code"], "MATCHING_SOURCE_CI_MISSING")
                self.assertNotIn("actions/runs/721", self.calls)

    def test_workflow_run_checks_actual_trigger_identity(self):
        self.changed_version()
        revision = self.commit()
        self.trigger_change = lambda run: {**run, "head_sha": self.baseline}
        with self.assertRaises(P.AuthorizationError) as failure:
            self.cli(revision, ci=True)
        self.assertEqual(failure.exception.code, "TRIGGER_RUN_MISMATCH")
        self.assertIn("actions/runs/721", self.calls)

    def test_changed_package_requires_approved_rights_frozen_identity_and_complete_vendor(self):
        self.changed_version()
        original_manifest = (self.root / "vibe.toml").read_text()
        original_binding = (self.source / "vibe-publisher.json").read_bytes()
        original_license = (self.root / "LICENSE").read_bytes()
        vendor = next(name for name in self.package["files"]
                      if name.startswith("vibevm/vibedeps/") and name.endswith("README.md"))
        original_vendor = (self.root / vendor).read_bytes()
        cases = (
            ("rights", "REDISTRIBUTION_UNRESOLVED"),
            ("frozen", "PACKAGE_IDENTITY_MISMATCH"),
            ("identity", "PACKAGE_IDENTITY_MISMATCH"),
            ("vendor", "DEPENDENCY_CLOSURE_UNQUALIFIED"),
            ("vendor_inventory", "DEPENDENCY_CLOSURE_UNQUALIFIED"),
            ("license", "PUBLIC_EXPORT_INCOMPLETE"),
        )
        for change, reason in cases:
            with self.subTest(change=change):
                # Each case branches from the valid baseline in this disposable
                # fixture; a prior invalid source cannot become its baseline.
                git(self.source, "update-ref", "refs/heads/main", self.baseline)
                (self.root / "vibe.toml").write_text(original_manifest)
                (self.source / "vibe-publisher.json").write_bytes(original_binding)
                (self.root / vendor).write_bytes(original_vendor)
                (self.root / "LICENSE").write_bytes(original_license)
                if change == "rights":
                    binding = copy.deepcopy(self.binding)
                    binding["packages"][0]["redistribution"]["status"] = "unresolved"
                    (self.source / "vibe-publisher.json").write_text(json.dumps(binding))
                elif change == "vendor":
                    (self.root / vendor).write_text("Unmatched vendored bytes.\n")
                elif change == "vendor_inventory":
                    binding = copy.deepcopy(self.binding)
                    binding["packages"][0]["files"].remove(vendor)
                    (self.source / "vibe-publisher.json").write_text(json.dumps(binding))
                elif change == "license":
                    (self.root / "LICENSE").write_text("")
                else:
                    before, after = (("frozen = true", "frozen = false") if change == "frozen"
                                     else ('name = "codex-relay"', 'name = "other"'))
                    self.assertIn(before, original_manifest)
                    (self.root / "vibe.toml").write_text(original_manifest.replace(before, after, 1))
                row = self.cli(self.commit(), expect=1)
                self.assertEqual(row["reason_code"], reason)


def main():
    global P, SOURCE_SHA, PUBLISHER_SHA, BINDING, SOURCE_FILES, PUBLISHER_WORKFLOW
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publisher", type=Path, required=True)
    parser.add_argument("--publisher-sha", type=full_sha, required=True,
                        help="Assert the caller-selected publisher checkout SHA; does not select code")
    parser.add_argument("--source-sha", type=full_sha, required=True,
                        help="Exact Relay Git commit supplying binding and package fixture bytes")
    args = parser.parse_args()
    publisher = args.publisher.resolve()
    PUBLISHER_SHA = git(publisher, "rev-parse", "HEAD").decode().strip()
    if PUBLISHER_SHA != args.publisher_sha:
        parser.error("publisher checkout differs from the asserted executing workflow SHA")
    if git(publisher, "status", "--porcelain", "--", "tooling/vibe-publisher", "scripts/prepare-distribution.py", "toolchain/vibevm.json", ".github/workflows/vibe-publisher.yml"):
        parser.error("selected publisher implementation has local changes")
    PUBLISHER_WORKFLOW = git(publisher, "show", PUBLISHER_SHA + ":.github/workflows/vibe-publisher.yml").decode()
    SOURCE_SHA = args.source_sha
    if git(SOURCE, "rev-parse", "--verify", SOURCE_SHA + "^{commit}").decode().strip() != SOURCE_SHA:
        parser.error("exact producer source commit is unavailable")
    BINDING = json.loads(git(SOURCE, "show", SOURCE_SHA + ":vibe-publisher.json"))
    if len(BINDING["packages"]) != 1 or BINDING["packages"][0]["coordinate"] != "org.jresearch.ai/codex-relay":
        parser.error("expected the Relay package binding")
    root = BINDING["packages"][0]["root"]
    paths = git(SOURCE, "ls-tree", "-rz", "--name-only", SOURCE_SHA, "--", root).split(b"\0")
    SOURCE_FILES = {path.decode(): git(SOURCE, "show", SOURCE_SHA + ":" + path.decode())
                    for path in paths if path}
    SOURCE_FILES["vibe-publisher.json"] = git(SOURCE, "show", SOURCE_SHA + ":vibe-publisher.json")
    spec = importlib.util.spec_from_file_location("selected_shared_publisher", publisher / "tooling/vibe-publisher/publisher.py")
    P = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(P)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(RelayPublisherTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({
        "qualification": "LOCAL_SYNTHETIC_CI_NO_NETWORK_OR_PUBLICATION",
        "publisher": {"repository": "jresearchsoftware/shared-governance", "sha": PUBLISHER_SHA},
        "producer": {"repository": BINDING["repository"], "source_sha": SOURCE_SHA},
        "tests": result.testsRun, "successful": result.wasSuccessful(),
    }, indent=2))
    return int(not result.wasSuccessful())


if __name__ == "__main__":
    raise SystemExit(main())
