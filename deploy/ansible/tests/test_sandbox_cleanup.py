"""Native filesystem coverage of the fixed runtime-identity cleanup helper."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from jinja2 import Environment, StrictUndefined


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / 'roles/relay_codex_runtime/templates/relay-codex-cleanup.py.j2'


@unittest.skipIf(os.name != 'posix', 'descriptor-relative cleanup needs native Linux')
class SandboxCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.work = self.base / 'work'
        self.cwd = self.work / 'run-39'
        self.sandbox = self.cwd / '.codex-sandbox'
        self.private = self.sandbox / 'home/tmp/arg0'
        self.private.mkdir(parents=True)
        self.private.chmod(0o700)
        (self.private / 'private-state').write_text('protected attempt evidence')
        metadata = self.sandbox.stat()
        self.identity = f'{metadata.st_dev}:{metadata.st_ino}'
        self.helper = self.base / 'cleanup.py'
        self.helper.write_text(TEMPLATE.read_text().replace(
            '{{ relay_dispatch_work_root | to_json }}', json.dumps(str(self.work))))

    def invoke(self, cwd=None, identity=None):
        result = subprocess.run([sys.executable, '-I', '-S', str(self.helper),
            '--cwd', str(cwd or self.cwd), '--sandbox-identity', identity or self.identity],
            text=True, capture_output=True, timeout=10)
        self.assertEqual(result.stderr, '')
        return result.returncode, json.loads(result.stdout)

    def test_private_descendants_removed_without_mode_repair(self):
        self.assertEqual(self.private.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.invoke(), (0, {'schemaVersion': 1, 'status': 'removed'}))
        self.assertFalse(self.sandbox.exists())
        self.assertTrue(self.cwd.exists())

    def test_descendant_symlink_never_deletes_outside_artifacts(self):
        outside = self.base / 'outside'
        outside.mkdir()
        evidence = outside / 'evidence'
        evidence.write_text('must survive')
        (self.sandbox / 'escape').symlink_to(outside, target_is_directory=True)
        self.assertEqual(self.invoke()[0], 0)
        self.assertEqual(evidence.read_text(), 'must survive')

    def test_replacement_inode_is_retained_without_mutation(self):
        previous = self.cwd / 'previous'
        self.sandbox.rename(previous)
        self.sandbox.mkdir()
        marker = self.sandbox / 'replacement'
        marker.write_text('keep')
        status, receipt = self.invoke()
        self.assertEqual(status, 1)
        self.assertEqual(receipt['code'], 'SANDBOX_CLEANUP_IDENTITY_MISMATCH')
        self.assertEqual(marker.read_text(), 'keep')
        self.assertTrue((previous / 'home/tmp/arg0/private-state').exists())

    def test_symlink_checkout_and_sandbox_are_rejected(self):
        link = self.work / 'run-40'
        link.symlink_to(self.cwd, target_is_directory=True)
        self.assertEqual(self.invoke(cwd=link)[0], 1)
        saved = self.cwd / 'saved'
        self.sandbox.rename(saved)
        self.sandbox.symlink_to(saved, target_is_directory=True)
        self.assertEqual(self.invoke()[0], 1)
        self.assertTrue((saved / 'home/tmp/arg0/private-state').exists())

    def test_symlink_swap_between_stat_and_open_cannot_traverse_outside(self):
        outside = self.base / 'outside'
        outside.mkdir()
        evidence = outside / 'evidence'
        evidence.write_text('must survive')
        spec = importlib.util.spec_from_file_location('cleanup_fixture', self.helper)
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        original_open = os.open
        swapped = False

        def swap(path, flags, *args, **kwargs):
            nonlocal swapped
            if path == 'arg0' and not swapped:
                swapped = True
                self.private.rename(self.private.with_name('saved'))
                self.private.symlink_to(outside, target_is_directory=True)
            return original_open(path, flags, *args, **kwargs)

        with patch.object(helper.os, 'open', side_effect=swap):
            with self.assertRaises(OSError):
                helper.cleanup(['--cwd', str(self.cwd), '--sandbox-identity', self.identity])
        self.assertTrue(swapped)
        self.assertEqual(evidence.read_text(), 'must survive')
        self.assertTrue((self.private.with_name('saved') / 'private-state').exists())

    def test_arbitrary_and_nested_paths_are_rejected(self):
        for cwd in [self.work, self.cwd / 'nested', self.base / 'run-39',
                    self.work / 'unadmitted', self.work / 'run-039']:
            status, receipt = self.invoke(cwd=cwd)
            self.assertEqual(status, 1)
            self.assertEqual(receipt['code'], 'SANDBOX_CLEANUP_PATH_INVALID')
        self.assertTrue(self.private.exists())

    def test_replay_after_removal_does_not_mutate_checkout(self):
        self.assertEqual(self.invoke()[0], 0)
        marker = self.cwd / 'keep'
        marker.write_text('keep')
        status, receipt = self.invoke()
        self.assertEqual(status, 1)
        self.assertEqual(receipt['code'], 'ENOENT')
        self.assertEqual(marker.read_text(), 'keep')

    @unittest.skipIf(hasattr(os, 'geteuid') and os.geteuid() == 0, 'requires ordinary UID')
    def test_os_failure_has_bounded_safe_context_and_retains_private_artifact(self):
        self.private.chmod(0)
        try:
            status, receipt = self.invoke()
            self.assertEqual(status, 1)
            self.assertEqual(receipt['status'], 'retained')
            self.assertEqual(receipt['code'], 'EACCES')
            self.assertEqual(receipt['operation'], 'open-directory')
            self.assertEqual(receipt['syscall'], 'open')
            self.assertEqual(receipt['path'], '.codex-sandbox/home/tmp/arg0')
            self.assertNotIn(str(self.base), json.dumps(receipt))
            self.assertLess(len(json.dumps(receipt)), 512)
        finally:
            self.private.chmod(0o700)
        self.assertTrue((self.private / 'private-state').exists())

    def test_entry_bound_stops_and_retains_remaining_artifacts(self):
        self.helper.write_text(self.helper.read_text().replace('MAX_ENTRIES = 100000', 'MAX_ENTRIES = 1'))
        status, receipt = self.invoke()
        self.assertEqual(status, 1)
        self.assertEqual(receipt['code'], 'SANDBOX_CLEANUP_LIMIT_EXCEEDED')
        self.assertTrue((self.private / 'private-state').exists())

    @unittest.skipIf(hasattr(os, 'geteuid') and os.geteuid() == 0, 'requires ordinary UID')
    def test_parent_permissions_can_retain_empty_sandbox_with_exact_operation(self):
        self.cwd.chmod(0o500)
        try:
            status, receipt = self.invoke()
            self.assertEqual(status, 1)
            self.assertEqual(receipt['code'], 'EACCES')
            self.assertEqual(receipt['operation'], 'rmdir-sandbox')
            self.assertEqual(receipt['syscall'], 'rmdir')
            self.assertEqual(receipt['path'], '.codex-sandbox')
            self.assertTrue(self.sandbox.is_dir())
            self.assertEqual(list(self.sandbox.iterdir()), [])
            self.assertEqual(self.cwd.stat().st_mode & 0o777, 0o500)
        finally:
            self.cwd.chmod(0o700)

    @unittest.skipUnless(shutil.which('node'), 'requires Node for the actual launcher boundary')
    def test_launcher_cleanup_and_probe_do_not_require_credentials_or_diagnostic_store(self):
        self.helper.rename(self.base / 'relay-codex-cleanup.py')
        diagnostic = self.base / 'diagnostic.mjs'
        shutil.copyfile(ROOT / 'roles/relay_codex_runtime/files/relay-codex-diagnostic.mjs', diagnostic)
        values = {
            'relay_install_root': str(self.base), 'relay_dispatch_work_root': str(self.work),
            'relay_codex_diagnostic_path': str(diagnostic),
            'relay_codex_access_token_file': str(self.base / 'missing-token'),
            'relay_codex_binary_path': str(self.base / 'missing-binary'),
            'relay_diagnostics_config_path': str(self.base / 'missing-diagnostics'),
            'relay_rust_toolchain_root': '/missing-rust',
            'relay_writer_commit_name': 'fixture', 'relay_writer_commit_email': 'fixture@example.invalid',
            'relay_remediation_commit_name': 'fixture', 'relay_remediation_commit_email': 'fixture@example.invalid',
        }
        env = Environment(undefined=StrictUndefined)
        env.filters['to_json'] = json.dumps
        launcher = self.base / 'launcher.mjs'
        launcher.write_text(env.from_string((ROOT / 'roles/relay_codex_runtime/templates/relay-codex-launcher.mjs.j2').read_text()).render(values))
        clean_env = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'}
        probe = subprocess.run([shutil.which('node'), str(launcher), '--check-runtime'],
            env=clean_env, text=True, capture_output=True, timeout=10)
        self.assertEqual((probe.returncode, probe.stderr), (0, ''))
        self.assertEqual(probe.stdout, 'CODEX_LAUNCHER_RUNTIME_READY\n')
        result = subprocess.run([shutil.which('node'), str(launcher), 'cleanup', '--cwd', str(self.cwd),
            '--sandbox-identity', self.identity], env=clean_env, text=True, capture_output=True, timeout=10)
        self.assertEqual((result.returncode, result.stderr), (0, ''))
        self.assertEqual(json.loads(result.stdout), {'schemaVersion': 1, 'status': 'removed'})
        self.assertFalse(self.sandbox.exists())


if __name__ == '__main__':
    unittest.main()
