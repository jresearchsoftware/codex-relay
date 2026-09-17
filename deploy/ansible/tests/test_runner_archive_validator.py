"""Deterministic archive/layout tests for the pinned qualification runner."""

import io
import os
import pathlib
import subprocess
import sys
import tarfile
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "roles" / "relay_runner" / "files" / "relay-runner-archive-check.py"


def archive(entries):
    handle = io.BytesIO()
    with tarfile.open(fileobj=handle, mode="w:gz") as tar:
        for name, kind in entries:
            item = tarfile.TarInfo(name)
            if kind == "file":
                item.size = 1
                item.mode = 0o755
                tar.addfile(item, io.BytesIO(b"x"))
            elif kind == "dir":
                item.type = tarfile.DIRTYPE
                item.mode = 0o755
                tar.addfile(item)
            elif kind == "link":
                item.type = tarfile.SYMTYPE
                item.linkname = "../outside"
                tar.addfile(item)
    return handle.getvalue()


class RunnerArchiveValidatorTests(unittest.TestCase):
    def run_validator(self, payload, version="2.336.0"):
        descriptor, name = tempfile.mkstemp(suffix=".tar.gz")
        os.close(descriptor)
        pathlib.Path(name).write_bytes(payload)
        try:
            return subprocess.run(
                [sys.executable, str(VALIDATOR), name, version],
                capture_output=True,
                text=True,
                check=False,
            )
        finally:
            pathlib.Path(name).unlink(missing_ok=True)

    def test_accepts_pinned_layout_and_version(self):
        result = self.run_validator(archive([("config.sh", "file"), ("run.sh", "file"), ("bin/Runner.Listener", "file")]))
        self.assertEqual(result.returncode, 0)
        self.assertIn("RUNNER_ARCHIVE_VALID version=2.336.0", result.stdout)

    def test_rejects_wrong_version_and_missing_entrypoint(self):
        self.assertNotEqual(self.run_validator(archive([("config.sh", "file"), ("run.sh", "file")])).returncode, 0)
        self.assertNotEqual(self.run_validator(archive([("config.sh", "file"), ("run.sh", "file"), ("bin/Runner.Listener", "file")]), "2.335.0").returncode, 0)

    def test_rejects_unsafe_paths_and_links(self):
        unsafe = archive([("config.sh", "file"), ("run.sh", "file"), ("bin/Runner.Listener", "file"), ("../escape", "file")])
        linked = archive([("config.sh", "file"), ("run.sh", "file"), ("bin/Runner.Listener", "file"), ("unsafe", "link")])
        self.assertIn("UNSAFE_MEMBER_PATH", self.run_validator(unsafe).stdout)
        self.assertIn("UNSAFE_LINK_TARGET", self.run_validator(linked).stdout)

    def test_reconciliation_package_cannot_replace_instance_registration_or_runtime_state(self):
        for name in ('.runner', '.credentials', '.credentials_rsaparams', '_diag/log', '.env'):
            payload = archive([('config.sh', 'file'), ('run.sh', 'file'),
                               ('bin/Runner.Listener', 'file'), (name, 'file')])
            self.assertIn('INSTANCE_STATE_IN_PACKAGE', self.run_validator(payload).stdout)
