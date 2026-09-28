"""Real protected files, flock and archive durability; fake read-only systemd I/O."""
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import stat
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('bootstrap_recovery', ROOT / 'tools/production-bootstrap-recovery.py')
recovery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recovery)


@unittest.skipUnless(os.name != 'nt' and os.geteuid() == 0, 'native root filesystem tests')
class BootstrapRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='relay-bootstrap-test-', dir='/run')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.systemd_roots = [self.root / 'persistent-systemd', self.root / 'runtime-systemd']
        for directory in self.systemd_roots:
            directory.mkdir(mode=0o755)
        self.units = ['relay-bootstrap-test-' + name for name in (
            'reviewer.service', 'runner.service', 'recovery.service', 'recovery.timer',
            'general.service', 'controller.service', 'proxy.service')]
        dropin_root = self.systemd_roots[0] / (self.units[1] + '.d')
        dropin_root.mkdir(mode=0o755)
        roots_patch = patch.object(recovery, 'SYSTEMD_ROOTS', tuple(map(str, self.systemd_roots)))
        roots_patch.start()
        self.addCleanup(roots_patch.stop)
        for name, mode in [('state', 0o700), ('state/production-apply', 0o700), ('runtime', 0o755)]:
            (self.root / name).mkdir(mode=mode)
        self.record = self.root / 'operation.json'
        self.raw = json.dumps({'schemaVersion': '1', 'state': 'RECOVERY_REQUIRED',
                               'phase': 'apply', 'target_head': 'a' * 40}).encode()
        self.record.write_bytes(self.raw)
        self.record.chmod(0o600)
        self.lock = self.root / 'runtime/production-operation.lock'
        self.lock.touch(mode=0o644)
        self.dropin = dropin_root / 'production-local-apply.conf'
        self.dropin.write_text('[Service]\nReadWritePaths=' + str(self.root / 'state/production-apply') + '\n')
        self.dropin.chmod(0o644)
        self.inputs = {
            'repository': 'fixture/consumer', 'schemaVersion': '1', 'head': 'b' * 40, 'staleHead': 'a' * 40,
            'record': str(self.record), 'lock': str(self.lock),
            'stateRoot': str(self.root / 'state'), 'runtimeRoot': str(self.root / 'runtime'),
            'stageRoot': str(self.root / 'state/production-apply'),
            'archiveRoot': str(self.root / 'state/superseded-operations'),
            'dropinRoot': str(self.dropin.parent), 'dropinContent': self.dropin.read_text(),
            'productionRunnerUnit': self.units[1],
            'absentPaths': [str(self.root / p) for p in ('install', 'config', 'logs', 'sudoers')],
            'users': ['relay-missing-test-user'], 'groups': ['relay-missing-test-group'],
            'units': self.units,
            'port': 28788, 'authorized': True,
        }
        self.boundary = patch.object(recovery, 'command', side_effect=self.query)
        self.commands = self.boundary.start()
        self.addCleanup(self.boundary.stop)

    def query(self, argv):
        if argv == ['/usr/bin/ss', '-ltnH']:
            return 'LISTEN 0 128 127.0.0.1:8787 0.0.0.0:*\n'
        self.assertEqual(argv[:2], ['/bin/systemctl', 'show'])
        self.assertIn('DropInPaths', argv[3].split(','))
        return 'LoadState=not-found\nActiveState=inactive\nSubState=dead\nUnitFileState=\nMainPID=0\nFragmentPath=\nDropInPaths=\n'

    def inspect(self):
        return recovery.execute(self.inputs, 'inspect')

    def authorize_hash(self):
        self.inputs['expectedStateHash'] = self.inspect()['stateHash']

    def archive(self):
        return Path(self.inputs['archiveRoot']) / ('apply-' + 'a' * 40 + '.json')

    def assert_inspect_and_dispose_rejected(self):
        before = self.record.stat()
        for mode in ('inspect', 'dispose'):
            with self.assertRaises(ValueError, msg=mode):
                recovery.execute(self.inputs, mode)
            self.assertEqual(self.record.read_bytes(), self.raw)
            self.assertEqual(self.record.stat(), before)
            self.assertFalse(self.archive().parent.exists())

    def test_orphan_dropins_for_every_governed_unit_block_inspect_and_dispose(self):
        self.authorize_hash()
        for root in self.systemd_roots:
            for unit in self.units:
                with self.subTest(root=root.name, unit=unit):
                    self.assertFalse((root / unit).exists())
                    directory = root / (unit + '.d')
                    existed = directory.exists()
                    directory.mkdir(mode=0o755, exist_ok=True)
                    orphan = directory / 'override.conf'
                    orphan.write_text('[Service]\nEnvironment=ORPHAN=1\n')
                    try:
                        self.assert_inspect_and_dispose_rejected()
                        self.assertTrue(orphan.is_file())
                    finally:
                        orphan.unlink()
                        if not existed:
                            directory.rmdir()

    def test_unrecognized_dropin_contents_and_untrusted_directories_fail_closed(self):
        self.authorize_hash()
        for root in self.systemd_roots:
            for kind in ('non-conf', 'hidden', 'directory', 'symlink', 'directory-symlink', 'unsafe-mode'):
                with self.subTest(root=root.name, kind=kind):
                    directory = root / (self.units[0] + '.d')
                    if kind == 'directory-symlink':
                        directory.symlink_to(self.dropin.parent, target_is_directory=True)
                    else:
                        directory.mkdir(mode=0o755)
                        entry = directory / ('.hidden' if kind == 'hidden' else 'unknown')
                        if kind == 'directory':
                            entry.mkdir()
                        elif kind == 'symlink':
                            entry.symlink_to(self.root / 'missing')
                        elif kind == 'unsafe-mode':
                            directory.chmod(0o777)
                        else:
                            entry.touch()
                    try:
                        self.assert_inspect_and_dispose_rejected()
                    finally:
                        if directory.is_symlink():
                            directory.unlink()
                        else:
                            shutil.rmtree(directory)

    def test_systemd_reported_dropins_fail_closed_even_without_local_files(self):
        self.authorize_hash()
        for unit in self.units:
            for value in (None, '/usr/lib/systemd/system/' + unit + '.d/override.conf',
                          str(self.dropin) + ' /run/systemd/system/foreign.conf'):
                with self.subTest(unit=unit, value=value):
                    def query(argv):
                        output = self.query(argv)
                        if argv[:3] == ['/bin/systemctl', 'show', unit]:
                            output = output.replace('DropInPaths=\n', '' if value is None else 'DropInPaths=' + value + '\n')
                        return output
                    self.commands.side_effect = query
                    self.assert_inspect_and_dispose_rejected()
        self.commands.side_effect = self.query

    def test_exact_dropin_is_admitted_only_for_the_persistent_production_runner(self):
        self.authorize_hash()
        original = self.dropin.read_bytes()
        for root, unit in ((self.systemd_roots[1], self.units[1]),
                           (self.systemd_roots[0], self.units[0])):
            with self.subTest(root=root.name, unit=unit):
                directory = root / (unit + '.d')
                directory.mkdir(mode=0o755)
                copied = directory / self.dropin.name
                copied.write_bytes(original)
                copied.chmod(0o644)
                try:
                    self.assert_inspect_and_dispose_rejected()
                finally:
                    copied.unlink()
                    directory.rmdir()

    def test_changed_observed_dropin_paths_invalidate_hash_then_exact_runner_passes(self):
        self.authorize_hash()
        def query(argv):
            output = self.query(argv)
            if argv[:3] == ['/bin/systemctl', 'show', self.inputs['productionRunnerUnit']]:
                output = output.replace('DropInPaths=\n', 'DropInPaths=' + str(self.dropin) + '\n')
            return output
        self.commands.side_effect = query
        changed = self.inspect()['stateHash']
        self.assertNotEqual(changed, self.inputs['expectedStateHash'])
        with self.assertRaisesRegex(ValueError, 'state-changed'):
            recovery.execute(self.inputs, 'dispose')
        self.assertEqual(self.record.read_bytes(), self.raw)
        self.assertFalse(self.archive().parent.exists())
        self.inputs['expectedStateHash'] = changed
        recovery.execute(self.inputs, 'dispose')
        self.assertFalse(self.record.exists())
        self.assertTrue(self.archive().is_file())
        self.assertEqual(self.dropin.read_text(), self.inputs['dropinContent'])

    def test_dropin_content_metadata_and_empty_directory_evidence_invalidate_hash(self):
        for change in ('content', 'file-inode', 'directory-inode', 'persistent-empty', 'runtime-empty'):
            with self.subTest(change=change):
                self.authorize_hash()
                if change == 'content':
                    self.inputs['dropinContent'] += '# new owner-compiled content\n'
                    self.dropin.write_text(self.inputs['dropinContent'])
                elif change == 'file-inode':
                    self.dropin.rename(self.root / 'old-dropin')
                    self.dropin.write_text(self.inputs['dropinContent'])
                    self.dropin.chmod(0o644)
                elif change == 'directory-inode':
                    self.dropin.parent.rename(self.root / 'old-dropin-directory')
                    self.dropin.parent.mkdir(mode=0o755)
                    (self.root / 'old-dropin-directory' / self.dropin.name).rename(self.dropin)
                else:
                    root = self.systemd_roots[change == 'runtime-empty']
                    (root / (self.units[0] + '.d')).mkdir(mode=0o755)
                self.assertNotEqual(self.inspect()['stateHash'], self.inputs['expectedStateHash'])
                with self.assertRaisesRegex(ValueError, 'state-changed'):
                    recovery.execute(self.inputs, 'dispose')
                self.assertEqual(self.record.read_bytes(), self.raw)
                self.assertFalse(self.archive().parent.exists())

    def test_read_only_inspection_then_durable_disposition_preserves_bootstrap(self):
        before = {str(p): (p.stat().st_mode, p.read_bytes() if p.is_file() else None)
                  for p in self.root.rglob('*')}
        observed = self.inspect()
        after = {str(p): (p.stat().st_mode, p.read_bytes() if p.is_file() else None)
                 for p in self.root.rglob('*')}
        self.assertEqual(before, after)
        self.inputs['expectedStateHash'] = observed['stateHash']
        result = recovery.execute(self.inputs, 'dispose')
        self.assertEqual(result['stateHash'], observed['stateHash'])
        self.assertFalse(self.record.exists())
        archived = json.loads(self.archive().read_text())
        self.assertEqual(archived['disposition'], 'STALE_APPLY_BOOTSTRAP_ONLY')
        self.assertEqual(archived['source_record_sha256'], recovery.digest(self.raw))
        self.assertEqual(archived['superseded_by_head'], 'b' * 40)
        self.assertEqual(stat.S_IMODE(self.archive().stat().st_mode), 0o600)
        self.assertEqual(self.dropin.read_text(), self.inputs['dropinContent'])
        self.assertTrue(self.lock.is_file())
        self.assertFalse(any(Path(p).exists() for p in self.inputs['absentPaths']))
        self.assertEqual(list((self.root / 'state/production-apply').iterdir()), [])

    def test_unsafe_or_ambiguous_shape_retains_record(self):
        cases = ('install', 'config', 'logs', 'sudoers', 'staging-file', 'unknown-state',
                 'dropin', 'account', 'group', 'listener', 'unit', 'record-mode',
                 'record-head', 'record-phase', 'symlink-parent', 'hardlink', 'empty-service-response')
        for case in cases:
            with self.subTest(case=case):
                # Independent protected fixtures keep every negative case meaningful.
                fixture = BootstrapRecoveryTests('test_read_only_inspection_then_durable_disposition_preserves_bootstrap')
                fixture.setUp()
                try:
                    if case in ('install', 'config', 'logs', 'sudoers'):
                        (fixture.root / case).touch()
                    elif case == 'staging-file':
                        (fixture.root / 'state/production-apply/unknown').touch()
                    elif case == 'unknown-state':
                        (fixture.root / 'state/credentials').mkdir()
                    elif case == 'dropin':
                        fixture.dropin.write_text('foreign')
                    elif case == 'account':
                        fixture.inputs['users'] = ['root']
                    elif case == 'group':
                        fixture.inputs['groups'] = ['root']
                    elif case == 'listener':
                        fixture.commands.side_effect = lambda argv: ('LISTEN 0 128 [::]:28788 [::]:*\n'
                            if argv[0].endswith('/ss') else fixture.query(argv))
                    elif case == 'unit':
                        fixture.commands.side_effect = lambda argv: 'LoadState=loaded\nActiveState=active\nMainPID=123\n'
                    elif case == 'empty-service-response':
                        fixture.commands.side_effect = lambda argv: ''
                    elif case == 'record-mode':
                        fixture.record.chmod(0o644)
                    elif case in ('record-head', 'record-phase'):
                        record = json.loads(fixture.raw)
                        record['target_head' if case == 'record-head' else 'phase'] = 'foreign'
                        fixture.record.write_text(json.dumps(record))
                    elif case == 'symlink-parent':
                        (fixture.root / 'config-target').mkdir()
                        (fixture.root / 'config').symlink_to(fixture.root / 'config-target', target_is_directory=True)
                    elif case == 'hardlink':
                        os.link(fixture.record, fixture.root / 'record-link')
                    with fixture.assertRaises((ValueError, OSError)):
                        fixture.inspect()
                    fixture.assertTrue(fixture.record.exists())
                    fixture.assertFalse(fixture.archive().exists())
                finally:
                    fixture.doCleanups()

    def test_exact_hash_head_and_owner_authorization_are_required(self):
        self.authorize_hash()
        for update in ({'authorized': False}, {'expectedStateHash': '0' * 64},
                       {'head': 'a' * 40}, {'head': 'c' * 40}, {'port': 28789},
                       {'repository': 'other/consumer'}):
            with self.subTest(update=update):
                inputs = {**self.inputs, **update}
                with self.assertRaises(ValueError):
                    recovery.execute(inputs, 'dispose')
                self.assertTrue(self.record.exists())
                self.assertFalse(self.archive().exists())

    def test_busy_lock_never_changes_or_archives_evidence(self):
        self.authorize_hash()
        with self.lock.open('r') as owner:
            fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):
                recovery.execute(self.inputs, 'dispose')
        self.assertEqual(self.record.read_bytes(), self.raw)
        self.assertFalse(self.archive().exists())

    def test_archive_conflict_is_not_overwritten(self):
        self.authorize_hash()
        self.archive().parent.mkdir(mode=0o700)
        self.archive().write_text('{}')
        self.archive().chmod(0o600)
        with self.assertRaisesRegex(ValueError, 'archive-conflict'):
            recovery.execute(self.inputs, 'dispose')
        self.assertEqual(self.record.read_bytes(), self.raw)
        self.assertEqual(self.archive().read_text(), '{}')

    def test_failed_archive_directory_sync_keeps_record_and_supports_exact_retry(self):
        self.authorize_hash()
        real_sync = recovery.sync_directory
        def fail_archive_sync(path):
            if Path(path) == self.archive().parent:
                raise OSError('fixture fsync failure')
            real_sync(path)
        with patch.object(recovery, 'sync_directory', side_effect=fail_archive_sync):
            with self.assertRaises(OSError):
                recovery.execute(self.inputs, 'dispose')
        self.assertEqual(self.record.read_bytes(), self.raw)
        self.assertTrue(self.archive().exists())
        recovery.execute(self.inputs, 'dispose')
        self.assertFalse(self.record.exists())

    def test_state_change_after_archive_commit_retains_both_records(self):
        self.authorize_hash()
        real_sync = recovery.sync_directory
        def change_after_archive(path):
            real_sync(path)
            if Path(path) == self.archive().parent:
                (self.root / 'state/production-apply/unexpected').touch()
        with patch.object(recovery, 'sync_directory', side_effect=change_after_archive):
            with self.assertRaises(ValueError):
                recovery.execute(self.inputs, 'dispose')
        self.assertEqual(self.record.read_bytes(), self.raw)
        self.assertTrue(self.archive().exists())

    @unittest.skipUnless(shutil.which('ansible-playbook'), 'native Ansible required')
    def test_native_classification_reproduces_old_failure_then_archives_without_installing(self):
        from test_production_install_current_main import run_play
        # Copy real tasks and templates, substituting only host filesystem and
        # service-manager I/O. The public CLI's separate flag routing is tested
        # in deploy/tests; this executes the target-side contract end to end.
        for name in ('tasks', 'tools', 'roles/relay_runner/templates'):
            (self.root / name).mkdir(parents=True)
        for name in ('production-bootstrap-recovery.yml', 'production-bootstrap-probe.yml',
                     'production-operation-state.yml'):
            source = (ROOT / 'tasks' / name).read_text()
            source = source.replace('/etc/systemd/system/', str(self.systemd_roots[0]) + '/')
            (self.root / 'tasks' / name).write_text(source)
        shutil.copy(ROOT / 'roles/relay_runner/templates/relay-runner-production-local-apply.conf.j2',
                    self.root / 'roles/relay_runner/templates')
        stub = self.root / 'systemctl'
        stub.write_text('#!/usr/bin/python3\nimport sys\n'
                        'op=sys.argv[1]\n'
                        'if op=="show": print("LoadState=not-found\\nActiveState=inactive\\nSubState=dead\\nUnitFileState=\\nMainPID=0\\nFragmentPath=\\nDropInPaths=")\n'
                        'elif op=="is-active": print("inactive"); sys.exit(3)\n'
                        'elif op=="is-enabled": sys.exit(1)\n'
                        'else: raise RuntimeError("mutating systemctl operation")\n')
        stub.chmod(0o755)
        ss = self.root / 'ss'
        ss.write_text('#!/usr/bin/python3\n')
        ss.chmod(0o755)
        source = (ROOT / 'tools/production-bootstrap-recovery.py').read_text()
        source = source.replace('/etc/systemd/system', str(self.systemd_roots[0])).replace(
            '/run/systemd/system', str(self.systemd_roots[1]))
        (self.root / 'tools/production-bootstrap-recovery.py').write_text(source.replace(
            '/bin/systemctl', str(stub)).replace('/usr/bin/ss', str(ss)))
        controller = self.root / 'controller'
        subprocess.run(['git', 'init', '--quiet', '--template=', '--initial-branch=main', str(controller)], check=True)
        (controller / 'fixture').write_text('trusted owner source fixture\n')
        subprocess.run(['git', '-C', str(controller), 'add', 'fixture'], check=True)
        subprocess.run(['git', '-C', str(controller), '-c', 'user.name=fixture', '-c',
                        'user.email=fixture@example.invalid', 'commit', '--quiet', '-m', 'fixture'], check=True)
        head = subprocess.check_output(['git', '-C', str(controller), 'rev-parse', 'HEAD'], text=True).strip()
        values = {
            'relay_review_root': str(controller), 'relay_deployment_profile': 'production',
            'relay_production_host': 'localhost', 'relay_production_operation_phase': 'check',
            'relay_production_operation_target_head': head,
            'relay_production_operation_record_path': str(self.record),
            'relay_install_root': str(self.root / 'install'), 'relay_config_root': str(self.root / 'config'),
            'relay_state_root': self.inputs['stateRoot'], 'relay_log_root': str(self.root / 'logs'),
            'relay_runtime_root': self.inputs['runtimeRoot'], 'relay_github_repository': 'fixture/consumer',
            'relay_production_local_apply_sudoers_file': str(self.root / 'sudoers'),
            'relay_reviewer_service_name': self.inputs['units'][0],
            'relay_runner_service_name': self.inputs['units'][1],
            'relay_production_runner_service_name': self.inputs['units'][1],
            'relay_reviewer_recovery_service_name': 'relay-bootstrap-test-recovery.service',
            'relay_reviewer_recovery_timer_name': 'relay-bootstrap-test-recovery.timer',
            'relay_general_runner_service_name': 'relay-bootstrap-test-general.service',
            'relay_controller_service_name': 'relay-bootstrap-test-controller.service',
            'relay_superseded_proxy_service_name': 'relay-bootstrap-test-proxy.service',
        }
        for name in ('relay_user', 'relay_group', 'relay_reviewer_user', 'relay_reviewer_group',
                     'relay_codex_user', 'relay_codex_group', 'relay_codex_work_group',
                     'relay_runner_user', 'relay_runner_group', 'relay_general_runner_user'):
            values[name] = 'relay-missing-test-identity'
        from jinja2 import Template
        self.dropin.write_text(Template((ROOT / 'roles/relay_runner/templates/relay-runner-production-local-apply.conf.j2').read_text(),
                                       keep_trailing_newline=True).render(relay_production_local_apply_stage_root=self.inputs['stageRoot']))
        original_record = self.record.read_bytes()
        state_task = {'ansible.builtin.include_tasks': str(ROOT / 'tasks/production-operation-state.yml')}
        with patch.dict(os.environ, {'PATH': str(self.root) + ':' + os.environ['PATH']}):
            old = run_play(self.root, [state_task, {'ansible.builtin.include_tasks': str(
                ROOT / 'tasks/production-operation-recovery-classify.yml')}], values, check=True)
            self.assertNotEqual(old.returncode, 0)
            self.assertIn('PRODUCTION_RECOVERY_CLASSIFICATION_BLOCKED', old.stdout)
            classified = run_play(self.root, [state_task, {'ansible.builtin.include_tasks': str(
                self.root / 'tasks/production-bootstrap-recovery.yml')}], values, check=True)
        self.assertEqual(classified.returncode, 0, classified.stdout + classified.stderr)
        self.assertRegex(classified.stdout, r'changed=0\s')
        state_hash = re.search(r'apply_state_hash=([0-9a-f]{64})', classified.stdout).group(1)
        self.assertEqual(self.record.read_bytes(), original_record)
        self.assertFalse((self.root / 'install').exists())
        self.assertFalse(self.archive().exists())
        values.update(relay_production_operation_phase='stale-dispose',
                      relay_production_operation_stale_authorized=True,
                      relay_production_operation_stale_phase='apply',
                      relay_production_operation_stale_target_head='a' * 40,
                      relay_production_operation_stale_apply_shape='bootstrap-only',
                      relay_production_operation_stale_expected_state_hash=state_hash)
        tasks = yaml.safe_load((ROOT / 'relay-production-bootstrap-disposition.yml').read_text())[0]['tasks']
        wrong = run_play(self.root, tasks, {**values, 'relay_production_operation_stale_expected_state_hash': '0' * 64})
        self.assertNotEqual(wrong.returncode, 0)
        self.assertTrue(self.record.exists())
        self.assertFalse(self.archive().exists())
        # Exercise the compiled inventory through real Ansible in both modes,
        # with an absent main unit and an otherwise valid, already bound hash.
        for root, unit in ((self.systemd_roots[0], self.units[0]),
                           (self.systemd_roots[1], self.units[4])):
            with self.subTest(root=root.name, unit=unit):
                directory = root / (unit + '.d')
                directory.mkdir(mode=0o755)
                orphan = directory / 'override.conf'
                orphan.write_text('[Service]\nEnvironment=ORPHAN=1\n')
                try:
                    inspected = run_play(self.root, [state_task, {'ansible.builtin.include_tasks': str(
                        self.root / 'tasks/production-bootstrap-recovery.yml')}],
                        {**values, 'relay_production_operation_phase': 'check'}, check=True)
                    rejected = run_play(self.root, tasks, values)
                    for result in (inspected, rejected):
                        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                        self.assertIn('PRODUCTION_BOOTSTRAP_RECOVERY_BLOCKED=dropin-contents', result.stdout + result.stderr)
                    self.assertEqual(self.record.read_bytes(), original_record)
                    self.assertFalse(self.archive().parent.exists())
                    self.assertTrue(orphan.is_file())
                finally:
                    orphan.unlink()
                    directory.rmdir()
        disposed = run_play(self.root, tasks, values)
        self.assertEqual(disposed.returncode, 0, disposed.stdout + disposed.stderr)
        self.assertIn('PRODUCTION_BOOTSTRAP_DISPOSITION_PASS=' + head, disposed.stdout)
        self.assertFalse(self.record.exists())
        self.assertTrue(self.archive().exists())
        self.assertFalse((self.root / 'install').exists())
        self.assertTrue(self.dropin.exists())


if __name__ == '__main__':
    unittest.main()
