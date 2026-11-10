#!/usr/bin/env python3
"""Run existing native lifecycle proof inside an already isolated TEST container.

The production unit/helper templates and actual systemd are unchanged. The
existing fixture explicitly substitutes the Reviewer/runner business processes
and credential-readiness check. This script never claims a complete public
installer or GitHub registration proof. It needs no network or credentials.
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'deploy/ansible/tests'))
import test_reviewer_runner_systemd_lifecycle as native


class ExistingIsolatedSystemd(native.DisposableSystemdLifecycle):
    """Replace only Docker provisioning/transport with local TEST execution."""
    def _run_docker(self, arguments, *, check=True, timeout=30):
        if arguments[:2] != ['exec', self.name]:
            raise AssertionError('Only local execution inside the assigned TEST container is allowed')
        result = subprocess.run(arguments[2:], capture_output=True, text=True, timeout=timeout)
        if check and result.returncode:
            raise AssertionError(f'Local TEST command failed: {arguments[2:]}\n{result.stdout}\n{result.stderr}')
        return result

    def _start_container(self):
        assert os.geteuid() == 0 and Path('/.dockerenv').exists()
        assert set(path.name for path in Path('/sys/class/net').iterdir()) == {'lo'}, 'TEST must be offline'
        assert subprocess.run(['systemctl', 'is-system-running'], capture_output=True,
                              text=True).stdout.strip() == 'running'
        destination = Path('/opt/lifecycle')
        assert not destination.exists(), 'Do not reuse another fixture installation'
        destination.mkdir()
        subprocess.run(['mount', '--bind', str(self.root), str(destination)], check=True)
        # The assigned container mounts /tmp noexec. Only this fixture's
        # production-like /opt bind needs executable, read-only traversal.
        subprocess.run(['mount', '-o', 'remount,bind,ro,exec', str(destination)], check=True)

    def close(self):
        units = ['reviewer-mcp.service', 'relay-runner.service', 'relay-general-runner.service']
        subprocess.run(['systemctl', 'stop', *units], capture_output=True)
        subprocess.run(['systemctl', 'disable', *units], capture_output=True)
        for unit in units:
            (Path('/etc/systemd/system') / unit).unlink(missing_ok=True)
        subprocess.run(['systemctl', 'daemon-reload'], capture_output=True)
        subprocess.run(['systemctl', 'reset-failed'], capture_output=True)
        for user in [self.REVIEWER_USER, self.RUNNER_USER, self.GENERAL_RUNNER_USER]:
            subprocess.run(['userdel', user], capture_output=True)
            subprocess.run(['groupdel', user], capture_output=True)
        subprocess.run(['umount', '/opt/lifecycle'], check=True)
        Path('/opt/lifecycle').rmdir()
        # Everything under this exact root was created by the native fixture.
        root = Path('/run/lifecycle')
        assert root.resolve() == Path('/run/lifecycle') and not root.is_symlink()
        shutil.rmtree(root, ignore_errors=True)
        self.temporary_directory.cleanup()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--isolated-disposable-container', action='store_true', required=True)
    args = parser.parse_args()
    assert args.isolated_disposable_container
    with patch.object(native, 'DisposableSystemdLifecycle', ExistingIsolatedSystemd), \
         patch.object(native, 'docker_available', return_value=True):
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(native.ReviewerRunnerNativeSystemdLifecycleTests)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.wasSuccessful():
        print('TASK230_NATIVE_SYSTEMD_LIFECYCLE=PASS;network=none;backend=real-systemd;'
              'substitutions=reviewer-process,runner-process,credential-readiness-check', flush=True)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
