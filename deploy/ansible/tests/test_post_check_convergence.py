"""Production regressions: composed writers and mutable runner diagnostics."""
import os
from pathlib import Path
import shutil
import stat
import tempfile
import unittest

import yaml

from test_production_install_current_main import ANSIBLE, ROOT, run_play


def task(path, name):
    value = next(t for t in yaml.safe_load((ROOT / path).read_text()) if t['name'] == name)
    value.pop('notify', None)  # This fixture has no service manager.
    return value


@unittest.skipUnless(ANSIBLE and getattr(os, 'geteuid', lambda: 1)() == 0,
                     'root for isolated ownership fixtures')
class PostCheckConvergenceTests(unittest.TestCase):
    def test_shared_app_and_reviewer_writers_produce_identical_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            runtime = directory / 'roles/relay_runtime'
            shutil.copytree(ROOT / 'roles/relay_runtime', runtime)
            install, config = directory / 'install', directory / 'config'
            install.mkdir()
            config.mkdir()
            values = {'relay_install_root': str(install), 'relay_config_root': str(config),
                      'relay_reviewer_group': 'root', 'relay_release_commit': 'a' * 40,
                      'relay_release_sha256': 'b' * 64,
                      'relay_production_reviewer_bind_refresh': True}
            original = [
                task('roles/relay_runtime/tasks/main.yml',
                     'Install bounded read-only GitHub App qualification implementation'),
                task('roles/relay_runtime/tasks/main.yml', 'Install reviewer configuration contract'),
            ]
            original[0]['ansible.builtin.copy']['src'] = str(runtime / 'files/relay-app-qualification.py')
            original[1]['ansible.builtin.template']['src'] = str(runtime / 'templates/reviewer-mcp.json.j2')
            other_writers = [
                task('roles/relay_controller/tasks/main.yml',
                     'Install the shared App qualification implementation required by Writer'),
                task('roles/relay_reviewer_bind/tasks/main.yml',
                     'Render the Reviewer config for the validated bind mode'),
                task('tasks/production-reviewer-bind-state.yml',
                     'Refresh address-bound Reviewer artifacts from the current gateway'),
            ]
            other_writers[-1]['loop'] = other_writers[-1]['loop'][:1]
            first = run_play(directory, original, values)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            before = {p: p.read_bytes() for p in [install / 'relay-app-qualification.py', config / 'reviewer-mcp.json']}
            for check in [False, True]:
                result = run_play(directory, other_writers + original, values, check=check)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertRegex(result.stdout, r'changed=0\s+unreachable=0\s+failed=0')
                self.assertEqual({p: p.read_bytes() for p in before}, before)
            drift = config / 'reviewer-mcp.json'
            drift.write_text('{}\n')
            result = run_play(directory, original + other_writers, values, check=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertRegex(result.stdout, r'changed=[1-9][0-9]*')
            self.assertEqual(drift.read_text(), '{}\n', 'check must not repair drift')

    def test_runner_probes_preserve_private_logs_and_still_detect_excess_access(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            runner = directory / 'runner'
            (runner / 'bin').mkdir(parents=True)
            diagnostic = runner / '_diag'
            diagnostic.mkdir(mode=0o750)
            listener = runner / 'bin/Runner.Listener'
            listener.write_text('#!/bin/sh\n: > "$(dirname "$0")/../_diag/probe-$$.log"\nprintf "2.336.0\\n"\n')
            listener.chmod(0o755)
            private, group_read = diagnostic / 'private.log', diagnostic / 'group-read.log'
            for path, mode in [(private, 0o600), (group_read, 0o640)]:
                path.write_text('fixture\n')
                path.chmod(mode)
            names = [
                'Inspect the installed runner version before software reconciliation',
                'Inspect existing runner diagnostic files',
                'Normalize runner diagnostic file ownership before package probes',
                'Verify installed runner reports the pinned version',
                'Reconcile runner diagnostic ownership after all package probes',
                'Enforce runner ownership of all diagnostic files after probes',
            ]
            tasks = [task('roles/relay_runner/tasks/main.yml', name) for name in names]
            paths = {'results': [{'stat': {'exists': True}}] * 4}
            values = {'relay_runner_root': str(runner), 'relay_runner_user': 'root', 'relay_runner_group': 'root',
                      'relay_runner_initial_paths': paths, 'relay_runner_installed_paths': paths}
            for check in [False, True]:
                result = run_play(directory, tasks, values, check=check)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertRegex(result.stdout, r'changed=0\s+unreachable=0\s+failed=0')
                self.assertEqual(stat.S_IMODE(private.stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE(group_read.stat().st_mode), 0o640)
                for path in diagnostic.glob('probe-*.log'):
                    self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            private.chmod(0o666)
            result = run_play(directory, tasks, values, check=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertRegex(result.stdout, r'changed=[1-9][0-9]*')
            self.assertEqual(stat.S_IMODE(private.stat().st_mode), 0o666)
            result = run_play(directory, tasks, values)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(stat.S_IMODE(private.stat().st_mode), 0o640)
