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


def diagnostic_repair_tasks(probe=None):
    tasks = []
    for scan, repair, label in [
        ('Inspect existing runner diagnostic files',
         'Normalize runner diagnostic file ownership before package probes', 'before'),
        ('Reconcile runner diagnostic ownership after all package probes',
         'Enforce runner ownership of all diagnostic files after probes', 'after'),
    ]:
        if label == 'after' and probe:
            tasks.append(probe)
        tasks.append(task('roles/relay_runner/tasks/main.yml', scan))
        repair_task = task('roles/relay_runner/tasks/main.yml', repair)
        repair_task['register'] = 'observed_repairs_' + label
        tasks.append(repair_task)
        tasks.append({'name': 'Verify selected repair calls ' + label,
                      'ansible.builtin.assert': {'that': [
                          'observed_repairs_' + label + '.results | length == expected_repairs_' + label]}})
    return tasks


@unittest.skipUnless(ANSIBLE, 'native Ansible required')
class DiagnosticRepairSelectionTests(unittest.TestCase):
    def test_many_compliant_private_and_group_logs_need_no_remote_repair_items(self):
        import grp
        import pwd
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            diagnostic = directory / 'runner/_diag'
            diagnostic.mkdir(parents=True, mode=0o750)
            for index in range(256):
                path = diagnostic / ('compliant-' + str(index) + '.log')
                path.write_text('Synthetic retained diagnostic.\n')
                path.chmod(0o600 if index % 2 else 0o640)
            before = {path: (path.read_bytes(), path.stat().st_ino, stat.S_IMODE(path.stat().st_mode))
                      for path in diagnostic.iterdir()}
            values = {'relay_runner_root': str(diagnostic.parent),
                      'relay_runner_user': pwd.getpwuid(os.geteuid()).pw_name,
                      'relay_runner_group': grp.getgrgid(os.getegid()).gr_name,
                      'relay_runner_installed_paths': {'results': [{'stat': {'exists': True}}] * 3},
                      'expected_repairs_before': 0, 'expected_repairs_after': 0}
            for check in [True, False, True]:
                result = run_play(directory, diagnostic_repair_tasks(), values, check=check)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertRegex(result.stdout, r'changed=0\s+unreachable=0\s+failed=0')
            self.assertEqual({path: (path.read_bytes(), path.stat().st_ino, stat.S_IMODE(path.stat().st_mode))
                              for path in diagnostic.iterdir()}, before)

    def test_unknown_owner_names_are_repaired_once_and_excess_mode_is_not_skipped(self):
        import grp
        import pwd
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            path = directory / 'unknown-owner-metadata.log'
            path.write_text('Synthetic diagnostic.\n')
            path.chmod(0o666)
            distinct_case = directory / 'UNKNOWN-OWNER-METADATA.log'
            distinct_case.write_text('Distinct Linux diagnostic.\n')
            distinct_case.chmod(0o666)
            repair = task('roles/relay_runner/tasks/main.yml',
                          'Normalize runner diagnostic file ownership before package probes')
            repair['register'] = 'repairs'
            tasks = [repair, {'ansible.builtin.assert': {'that': ['repairs.results | length == 2']}}]
            # The observed file may lack resolved NSS names. It still needs a
            # repair even if listed twice and selected by multiple drift fields.
            item = {'path': str(path), 'mode': '0666'}
            values = {'relay_runner_user': pwd.getpwuid(os.geteuid()).pw_name,
                      'relay_runner_group': grp.getgrgid(os.getegid()).gr_name,
                      'relay_runner_installed_paths': {'results': [{'stat': {'exists': True}}] * 3},
                      'relay_runner_diagnostic_files': {'files': [item, item, {'path': str(distinct_case), 'mode': '0666'}]}}
            checked = run_play(directory, tasks, values, check=True)
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o666)
            self.assertEqual(stat.S_IMODE(distinct_case.stat().st_mode), 0o666)
            applied = run_play(directory, tasks, values)
            self.assertEqual(applied.returncode, 0, applied.stdout + applied.stderr)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o640)
            self.assertEqual(stat.S_IMODE(distinct_case.stat().st_mode), 0o640)
            self.assertEqual(path.read_text(), 'Synthetic diagnostic.\n')
            self.assertEqual(distinct_case.read_text(), 'Distinct Linux diagnostic.\n')


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

    def test_runner_enable_probe_leaves_private_diagnostics_for_post_check(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            runner = directory / 'runner'
            (runner / 'bin').mkdir(parents=True)
            diagnostic = runner / '_diag'
            diagnostic.mkdir(mode=0o750)
            listener = runner / 'bin/Runner.Listener'
            listener.write_text('#!/bin/sh\n: > "$(dirname "$0")/../_diag/enable-probe-$$.log"\nprintf "2.336.0\\n"\n')
            listener.chmod(0o755)
            playbook = yaml.safe_load((ROOT / 'relay-production-runner-enable.yml').read_text())
            probe = next(t for t in playbook[0]['pre_tasks'] if t['name'] ==
                         'Verify the installed production runner version without replacing software')
            values = {'relay_runner_root': str(runner), 'relay_runner_user': 'root',
                      'relay_runner_group': 'root',
                      'relay_runner_installed_paths': {'results': [{'stat': {'exists': True}}] * 3}}
            inherited_umask = os.umask(0o022)
            try:
                result = run_play(directory, [probe], values)
            finally:
                os.umask(inherited_umask)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            logs = list(diagnostic.glob('enable-probe-*.log'))
            self.assertEqual(len(logs), 1)
            self.assertEqual(stat.S_IMODE(logs[0].stat().st_mode), 0o600)
            names = [
                'Inspect existing runner diagnostic files',
                'Normalize runner diagnostic file ownership before package probes',
                'Reconcile runner diagnostic ownership after all package probes',
                'Enforce runner ownership of all diagnostic files after probes',
            ]
            tasks = [task('roles/relay_runner/tasks/main.yml', name) for name in names]
            result = run_play(directory, tasks, values, check=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertRegex(result.stdout, r'changed=0\s+unreachable=0\s+failed=0')
            self.assertEqual(stat.S_IMODE(logs[0].stat().st_mode), 0o600)

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
                'Verify installed runner reports a valid native version',
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


    def test_owner_group_and_mode_drift_repair_once_and_post_probe_scan_catches_new_files(self):
        import grp
        import pwd
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            diagnostic = directory / 'runner/_diag'
            diagnostic.mkdir(parents=True, mode=0o750)
            runner = pwd.getpwnam('nobody')
            group = grp.getgrgid(runner.pw_gid).gr_name
            drift = {}
            for name, uid, gid, mode in [
                ('wrong-owner', 0, runner.pw_gid, 0o640),
                ('wrong-group', runner.pw_uid, 0, 0o640),
                ('multiple-drift', 0, 0, 0o666),
                ('private-owner-drift', 0, 0, 0o600),
            ]:
                path = diagnostic / (name + '.log')
                path.write_text('Preserved diagnostic.\n')
                os.chown(path, uid, gid)
                path.chmod(mode)
                drift[path] = (path.read_bytes(), path.stat().st_ino, uid, gid, mode)
            values = {'relay_runner_root': str(diagnostic.parent), 'relay_runner_user': runner.pw_name,
                      'relay_runner_group': group,
                      'relay_runner_installed_paths': {'results': [{'stat': {'exists': True}}] * 3}}
            checked = run_play(directory, diagnostic_repair_tasks(),
                               {**values, 'expected_repairs_before': 4, 'expected_repairs_after': 4}, check=True)
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            self.assertEqual({path: (path.read_bytes(), path.stat().st_ino, path.stat().st_uid,
                                    path.stat().st_gid, stat.S_IMODE(path.stat().st_mode))
                              for path in drift}, drift)
            applied = run_play(directory, diagnostic_repair_tasks(),
                               {**values, 'expected_repairs_before': 4, 'expected_repairs_after': 0})
            self.assertEqual(applied.returncode, 0, applied.stdout + applied.stderr)
            for path, (content, inode, _, _, mode) in drift.items():
                info = path.stat()
                self.assertEqual((path.read_bytes(), info.st_ino, info.st_uid, info.st_gid,
                                  stat.S_IMODE(info.st_mode)),
                                 (content, inode, runner.pw_uid, runner.pw_gid,
                                  0o600 if mode == 0o600 else 0o640))
            new_log = diagnostic / 'created-during-probe.log'
            probe = {'name': 'Synthetic package probe creates a diagnostic', 'ansible.builtin.copy': {
                'dest': str(new_log), 'content': 'New diagnostic.\n', 'owner': 'root', 'group': 'root', 'mode': '0666'}}
            after_probe = run_play(directory, diagnostic_repair_tasks(probe),
                                   {**values, 'expected_repairs_before': 0, 'expected_repairs_after': 1})
            self.assertEqual(after_probe.returncode, 0, after_probe.stdout + after_probe.stderr)
            self.assertEqual((new_log.stat().st_uid, new_log.stat().st_gid, stat.S_IMODE(new_log.stat().st_mode)),
                             (runner.pw_uid, runner.pw_gid, 0o640))
            converged = run_play(directory, diagnostic_repair_tasks(),
                                 {**values, 'expected_repairs_before': 0, 'expected_repairs_after': 0}, check=True)
            self.assertEqual(converged.returncode, 0, converged.stdout + converged.stderr)
            self.assertRegex(converged.stdout, r'changed=0\s+unreachable=0\s+failed=0')
