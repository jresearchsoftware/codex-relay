"""Unprivileged regressions for the installed-proof fixture, not Unix identity proof."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import installed_runtime_proof as proof


class InstalledQualificationTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'posix' and Path('/usr/bin/cc').exists(), 'Unix C linker required')
    def test_empty_etc_breaks_cc_and_restoring_only_its_alternative_repairs_linking(self):
        compiler = Path('/usr/bin/cc').resolve(strict=True)
        with tempfile.TemporaryDirectory(prefix='installed-linker-') as directory:
            root = Path(directory)
            etc = root / 'etc'
            etc.mkdir()
            cc = root / 'cc'
            # Model the same dangling alternative without mounts or root.
            cc.symlink_to(etc / 'alternatives/cc')
            command = [str(cc), '-x', 'c', '-', '-o', str(root / 'linked-probe')]
            source = 'int main(void) { return 0; }\n'
            with self.assertRaises(FileNotFoundError):
                subprocess.run(command, input=source, text=True, capture_output=True, check=True)
            proof.restore_linker_alternative(etc, compiler)
            self.assertEqual(sorted(str(path.relative_to(etc)) for path in etc.rglob('*')), ['alternatives', 'alternatives/cc'])
            self.assertEqual(cc.resolve(strict=True), compiler)
            subprocess.run(command, input=source, text=True, capture_output=True, check=True)
            subprocess.run([str(root / 'linked-probe')], check=True)

    def test_linker_restore_rejects_targets_outside_public_system_binaries(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, 'RUST_PROOF_LINKER_TARGET_UNSAFE'):
                proof.restore_linker_alternative(Path(directory), Path('/tmp/untrusted-compiler'))
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_child_failure_projection_is_bounded_and_excludes_runtime_material(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for number in range(10):
                (root / f'{number}.json').write_text(json.dumps({
                    'environment': {'omitted': 'protected-runtime-material'},
                    'launcherDiagnostic': {'code': 'CHILD_STDERR', 'childExitCode': 1, 'childStarted': True,
                        'preview': 'RUST_DEVELOPMENT_PROOF_FAILED cargo-test linker `cc` not found [REDACTED] ' + 'я' * 2000,
                        'debug': {'omitted': 'protected-runtime-material'}}}))
            output = io.StringIO()
            with mock.patch.object(proof, 'Path', return_value=root), contextlib.redirect_stdout(output):
                records = proof.launcher_diagnostics_since({root / '0.json'})
            self.assertEqual(len(records), 8)
            self.assertNotIn('protected-runtime-material', output.getvalue())
            for record in records:
                self.assertEqual(set(record), {'code', 'childExitCode', 'childStarted', 'preview'})
                self.assertLessEqual(len(record['preview'].encode('utf8')), 1024)
                self.assertIn('cargo-test linker `cc` not found', record['preview'])
                self.assertNotIn('\ufffd', record['preview'])

    def test_child_failure_projection_refuses_unredacted_fixture_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'failure.json').write_text(json.dumps({'launcherDiagnostic': {'preview': 'fixture-only-credential'}}))
            output = io.StringIO()
            with mock.patch.object(proof, 'Path', return_value=root), contextlib.redirect_stdout(output):
                with self.assertRaisesRegex(AssertionError, 'FIXTURE_DIAGNOSTIC_SECRET_LEAK'):
                    proof.launcher_diagnostics_since(set())
            self.assertEqual(output.getvalue(), '')


if __name__ == '__main__':
    unittest.main()
