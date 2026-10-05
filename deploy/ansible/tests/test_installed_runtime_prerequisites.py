"""Unprivileged coverage of the proof's local Node prerequisite."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import installed_runtime_proof as proof


@unittest.skipUnless(os.name == 'posix', 'Unix executable fixture required')
class InstalledRuntimePrerequisiteTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='installed-node-')
        self.addCleanup(temporary.cleanup)
        self.node = Path(temporary.name) / 'node'
        patch = mock.patch.dict(os.environ, {'PATH': temporary.name})
        patch.start()
        self.addCleanup(patch.stop)

    def node_version(self, version, status=0):
        self.node.write_text(f'#!/bin/sh\nprintf "%s\\n" "{version}"\nexit {status}\n')
        self.node.chmod(0o700)

    def test_supported_node_versions_pass(self):
        for version in ['v22.0.0', 'v22.20.0', 'v24.1.0']:
            with self.subTest(version=version):
                self.node_version(version)
                proof.require_supported_node()

    def test_unsupported_node_stops_all_proof_modes_before_side_effects(self):
        for version in ['v18.20.4', 'v21.7.3']:
            self.node_version(version)
            for flags in [[], ['--runtime-only'], ['--consumer-only'], ['--inside']]:
                with self.subTest(version=version, flags=flags), \
                     mock.patch.object(proof.sys, 'argv', ['installed_runtime_proof.py', *flags]), \
                     mock.patch.object(proof.os, 'geteuid', return_value=0), \
                     mock.patch.object(proof, 'download_rust_archive') as download, \
                     mock.patch.object(proof.subprocess, 'call') as namespace, \
                     mock.patch.object(proof.tempfile, 'TemporaryDirectory') as fixture, \
                     mock.patch.object(proof, 'proof') as installed:
                    with self.assertRaisesRegex(SystemExit, f'Node >=22 required; active node reports {version}'):
                        proof.main()
                    download.assert_not_called()
                    namespace.assert_not_called()
                    fixture.assert_not_called()
                    installed.assert_not_called()

    def test_missing_or_unusable_node_is_rejected(self):
        with self.assertRaisesRegex(SystemExit, 'Node >=22 required; active node unavailable'):
            proof.require_supported_node()
        for version, status in [('v22.20.0', 1), ('', 0), ('not-a-version', 0)]:
            with self.subTest(version=version, status=status):
                self.node_version(version, status)
                with self.assertRaisesRegex(SystemExit, 'Node >=22 required; active node --version failed'):
                    proof.require_supported_node()
        self.node.chmod(0o600)
        with self.assertRaisesRegex(SystemExit, 'Node >=22 required; active node unavailable'):
            proof.require_supported_node()
        with mock.patch.object(proof.subprocess, 'run', side_effect=subprocess.TimeoutExpired(['node', '--version'], 10)):
            with self.assertRaisesRegex(SystemExit, 'Node >=22 required; active node unavailable'):
                proof.require_supported_node()


if __name__ == '__main__':
    unittest.main()
