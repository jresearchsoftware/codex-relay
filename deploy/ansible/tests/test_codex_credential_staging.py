"""Protected Linux files and opaque synthetic tokens; no real credentials."""
import fcntl
import grp
import importlib.util
import json
import os
from pathlib import Path
import pwd
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import yaml


TOOLS = Path(__file__).resolve().parents[1] / 'tools'
sys.path.insert(0, str(TOOLS))
try:
    SPEC = importlib.util.spec_from_file_location('codex_credential_stage', TOOLS / 'codex-credential-stage.py')
    stage = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(stage)
finally:
    sys.path.pop(0)


@unittest.skipUnless(os.name != 'nt' and os.geteuid() == 0, 'native root filesystem tests')
class CodexCredentialStagingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='relay-codex-credential-test-', dir='/run')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.user = pwd.getpwnam('nobody')
        self.group = grp.getgrgid(self.user.pw_gid)
        self.head = 'a' * 40
        self.install = self.root / 'install'
        self.release = self.install / 'releases' / self.head
        self.release.mkdir(parents=True, mode=0o750)
        self.manifest = self.release / 'artifact-manifest.json'
        self.manifest.write_text(json.dumps({'schemaVersion': '1.0', 'commit': self.head,
                                           'installedRevision': self.head}))
        self.manifest.chmod(0o640)
        (self.install / 'current').symlink_to(self.release)
        self.source = self.root / 'source-token'
        self.token = b'opaque-test-value-with-no-authentication-power\n'
        self.source.write_bytes(self.token)
        self.source.chmod(0o600)
        self.credentials = self.root / 'codex-credentials'
        self.credentials.mkdir(mode=0o700)
        os.chown(self.credentials, self.user.pw_uid, self.group.gr_gid)
        self.destination = self.credentials / 'access-token'
        self.lock = self.root / 'production-operation.lock'
        self.lock.touch(mode=0o644)
        self.lock.chmod(0o644)
        self.operation = self.root / 'production-operation.json'
        self.args = SimpleNamespace(source=str(self.source), destination=str(self.destination),
            config_root=str(self.root), user=self.user.pw_name, group=self.group.gr_name,
            lock_file=str(self.lock), operation_record=str(self.operation),
            manifest=str(self.install / 'current' / 'artifact-manifest.json'), exact_head=self.head,
            check=False)

    def run_stage(self):
        return stage.stage(self.args)

    def command(self):
        command = [sys.executable, str(TOOLS / 'codex-credential-stage.py')]
        for name, value in vars(self.args).items():
            if name != 'check':
                command.extend(['--' + name.replace('_', '-'), value])
        if self.args.check:
            command.append('--check')
        return command

    def write_destination(self, value=None):
        self.destination.write_bytes(self.token if value is None else value)
        self.destination.chmod(0o600)
        os.chown(self.destination, self.user.pw_uid, self.group.gr_gid)

    def assert_absent(self):
        self.assertFalse(self.destination.exists())
        self.assertEqual(list(self.credentials.iterdir()), [])
        self.assertFalse(list(self.root.glob('.codex-token-*')))

    def test_stage_preserves_source_and_other_credentials_and_identical_token_is_noop(self):
        before = stage.stamp(self.source.stat())
        unrelated = self.root / 'writer-app-key'
        unrelated.write_bytes(b'unrelated-opaque-fixture')
        result = self.run_stage()
        self.assertEqual(result['proof'], 'CODEX_CREDENTIAL_STAGE=PASS;head=' + self.head)
        self.assertTrue(result['changed'])
        info = self.destination.stat()
        self.assertEqual((info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode), info.st_nlink),
                         (self.user.pw_uid, self.group.gr_gid, 0o600, 1))
        self.assertEqual(self.destination.read_bytes(), self.token)
        self.assertEqual(stage.stamp(self.source.stat()), before)
        self.assertEqual(unrelated.read_bytes(), b'unrelated-opaque-fixture')
        self.assertFalse(self.run_stage()['changed'])
        self.assertEqual(stage.stamp(self.destination.stat()), stage.stamp(info))
        self.assertFalse(self.operation.exists())
        self.assertFalse(list(self.root.glob('.codex-token-*')))

    def test_check_validates_without_staging(self):
        self.args.check = True
        self.assertEqual(self.run_stage()['status'], 'CODEX_CREDENTIAL_STAGE_PLANNED')
        self.assert_absent()

    def test_existing_different_token_is_never_replaced(self):
        self.write_destination(b'another-opaque-fixture')
        before = stage.stamp(self.destination.stat())
        with self.assertRaisesRegex(ValueError, 'existing-credential-differs'):
            self.run_stage()
        self.assertEqual(stage.stamp(self.destination.stat()), before)
        self.assertEqual(self.destination.read_bytes(), b'another-opaque-fixture')

    def test_source_rejects_wrong_owner_group_mode_hardlink_and_fifo(self):
        for uid, gid, mode in [(0, 0, 0o640), (0, self.group.gr_gid, 0o600),
                               (self.user.pw_uid, self.group.gr_gid, 0o600)]:
            os.chown(self.source, uid, gid)
            self.source.chmod(mode)
            with self.assertRaisesRegex(ValueError, 'file-metadata'):
                self.run_stage()
            self.assert_absent()
        os.chown(self.source, 0, 0)
        alias = self.root / 'source-alias'
        os.link(self.source, alias)
        with self.assertRaisesRegex(ValueError, 'file-metadata'):
            self.run_stage()
        alias.unlink()
        self.source.unlink()
        os.mkfifo(self.source, 0o600)
        with self.assertRaisesRegex(ValueError, 'file-metadata'):
            self.run_stage()
        self.assert_absent()

    def test_existing_token_rejects_root_owner_wrong_mode_group_hardlink_and_fifo(self):
        for uid, gid, mode in [(0, 0, 0o600), (self.user.pw_uid, 0, 0o600),
                               (self.user.pw_uid, self.group.gr_gid, 0o640)]:
            self.write_destination()
            os.chown(self.destination, uid, gid)
            self.destination.chmod(mode)
            before = stage.stamp(self.destination.stat())
            with self.assertRaisesRegex(ValueError, 'file-metadata'):
                self.run_stage()
            self.assertEqual(stage.stamp(self.destination.stat()), before)
        self.write_destination()
        alias = self.credentials / 'token-alias'
        os.link(self.destination, alias)
        with self.assertRaisesRegex(ValueError, 'file-metadata'):
            self.run_stage()
        alias.unlink()
        self.destination.unlink()
        os.mkfifo(self.destination, 0o600)
        os.chown(self.destination, self.user.pw_uid, self.group.gr_gid)
        with self.assertRaisesRegex(ValueError, 'file-metadata'):
            self.run_stage()

    def test_source_destination_and_directory_symlinks_are_refused(self):
        actual = self.root / 'actual-source'
        self.source.rename(actual)
        self.source.symlink_to(actual)
        with self.assertRaises(OSError):
            self.run_stage()
        self.source.unlink()
        actual.rename(self.source)
        self.destination.symlink_to(self.source)
        with self.assertRaises(OSError):
            self.run_stage()
        self.destination.unlink()
        actual = self.root / 'actual-credentials'
        self.credentials.rename(actual)
        self.credentials.symlink_to(actual)
        with self.assertRaises(OSError):
            self.run_stage()
        self.assertFalse((actual / 'access-token').exists())

    def test_only_exact_runtime_owned_final_directory_is_admitted(self):
        for uid, gid, mode in [(0, 0, 0o700), (self.user.pw_uid, 0, 0o700),
                               (self.user.pw_uid, self.group.gr_gid, 0o750)]:
            os.chown(self.credentials, uid, gid)
            self.credentials.chmod(mode)
            with self.assertRaisesRegex(ValueError, 'credential-directory'):
                self.run_stage()
            self.assert_absent()
        os.chown(self.credentials, self.user.pw_uid, self.group.gr_gid)
        self.credentials.chmod(0o700)
        self.root.chmod(0o777)
        with self.assertRaisesRegex(ValueError, 'parent'):
            self.run_stage()
        self.root.chmod(0o700)
        # Shared protected source/manifest handling must remain root-only.
        with self.assertRaisesRegex(ValueError, 'parent'):
            with stage.ProtectedPath(str(self.destination)):
                pass
        self.args.destination = str(self.credentials / 'alternate-token')
        with self.assertRaisesRegex(ValueError, 'credential-layout'):
            self.run_stage()

    def test_token_format_limit_and_cli_output_are_bounded(self):
        for raw in [b'', b' ', b'value with space', b'first\nsecond', b'line\n\n',
                    b'opaque\x00value', b'\xffopaque', b'x' * (stage.MAX_TOKEN_BYTES + 1)]:
            self.source.write_bytes(raw)
            result = subprocess.run(self.command(), capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, b'')
            self.assertRegex(result.stderr.decode(), r'^CODEX_CREDENTIAL_STAGE_BLOCKED=(token-format|file-size)\n$')
            self.assert_absent()
        for raw in [b'opaque\r\n', b'x' * stage.MAX_TOKEN_BYTES]:
            self.source.write_bytes(raw)
            self.assertTrue(self.run_stage()['changed'])
            self.assertEqual(self.destination.read_bytes(), raw)
            self.destination.unlink()

    def test_source_change_after_validation_is_refused(self):
        validate = stage.validate_token
        def change(raw):
            validate(raw)
            replacement = self.root / 'replacement'
            replacement.write_bytes(b'another-opaque-fixture')
            replacement.chmod(0o600)
            replacement.replace(self.source)
        with patch.object(stage, 'validate_token', side_effect=change):
            with self.assertRaisesRegex(ValueError, 'file-changed'):
                self.run_stage()
        self.assert_absent()

    def test_runtime_controlled_destination_race_is_not_overwritten(self):
        publish = stage.publish_token
        def compete(source_fd, target_fd):
            self.write_destination(b'runtime-controlled-race-fixture')
            return publish(source_fd, target_fd)
        with patch.object(stage, 'publish_token', side_effect=compete):
            with self.assertRaises(FileExistsError):
                self.run_stage()
        self.assertEqual(self.destination.read_bytes(), b'runtime-controlled-race-fixture')
        self.assertFalse(list(self.root.glob('.codex-token-*')))

    def test_runtime_cannot_modify_staged_inode_before_publication(self):
        publish = stage.publish_token
        self.root.chmod(0o751)
        def verify_private(source_fd, target_fd):
            staged = Path(os.readlink('/proc/self/fd/' + str(source_fd))) / 'access-token'
            info = staged.parent.stat()
            self.assertEqual((info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)), (0, 0, 0o700))
            probe = subprocess.run(['/usr/sbin/runuser', '-u', self.user.pw_name, '--',
                                    '/usr/bin/test', '-r', str(staged)])
            self.assertEqual(probe.returncode, 1)
            self.assertEqual(staged.stat().st_uid, self.user.pw_uid)
            return publish(source_fd, target_fd)
        with patch.object(stage, 'publish_token', side_effect=verify_private):
            self.assertTrue(self.run_stage()['changed'])

    def test_directory_identity_change_before_publication_is_refused(self):
        original = stage.CodexTokenTarget.recheck_parents
        def exchange(target):
            if list(self.root.glob('.codex-token-*')):
                self.credentials.rename(self.root / 'retained-credentials')
                self.credentials.mkdir(mode=0o700)
                os.chown(self.credentials, self.user.pw_uid, self.group.gr_gid)
            return original(target)
        with patch.object(stage.CodexTokenTarget, 'recheck_parents', new=exchange):
            with self.assertRaisesRegex(ValueError, 'credential-directory-changed'):
                self.run_stage()
        self.assert_absent()
        self.assertFalse((self.root / 'retained-credentials' / 'access-token').exists())

    def test_active_operation_wrong_head_and_held_lock_refuse_staging(self):
        self.operation.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'operation-recovery-required'):
            self.run_stage()
        self.operation.unlink()
        original = self.manifest.read_bytes()
        self.manifest.write_text(json.dumps({'schemaVersion': '1.0', 'commit': 'b' * 40,
                                            'installedRevision': self.head}))
        with self.assertRaisesRegex(ValueError, 'installed-head'):
            self.run_stage()
        self.manifest.write_bytes(original)
        with self.lock.open('rb') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):
                self.run_stage()
        self.assert_absent()

    def test_pending_reinstall_refuses_token_staging_after_apply_record_clears(self):
        journal = self.operation.with_name(self.install.name + '-clean-reinstall.json')
        journal.write_text('{"stage":"DECOMMISSIONED"}')
        journal.chmod(0o600)
        self.assertFalse(self.operation.exists())
        with self.assertRaisesRegex(ValueError, 'reinstall-recovery-required'):
            self.run_stage()
        self.assert_absent()

    def test_abrupt_exit_after_publication_retries_as_identical_noop(self):
        harness = '''import os, runpy, stat, sys
destination = sys.argv.pop(1)
sys.argv.pop(0)
sys.path.insert(0, os.path.dirname(sys.argv[0]))
fsync = os.fsync
def interrupt(fd):
    fsync(fd)
    if stat.S_ISDIR(os.fstat(fd).st_mode) and os.path.exists(destination):
        os._exit(73)
os.fsync = interrupt
runpy.run_path(sys.argv[0], run_name='__main__')
'''
        command = self.command()
        stopped = subprocess.run([sys.executable, '-c', harness, str(self.destination)] + command[1:],
                                 capture_output=True, timeout=15)
        self.assertEqual(stopped.returncode, 73, stopped.stderr)
        self.assertEqual(stopped.stdout + stopped.stderr, b'')
        self.assertEqual(self.destination.stat().st_nlink, 1)
        before = stage.stamp(self.destination.stat())
        retried = subprocess.run(command, capture_output=True, timeout=15)
        self.assertEqual(retried.returncode, 0, retried.stderr)
        self.assertFalse(json.loads(retried.stdout)['changed'])
        self.assertEqual(stage.stamp(self.destination.stat()), before)
        self.assertEqual(self.destination.read_bytes(), self.token)
        # An interrupted operation can retain only an empty protected directory;
        # replay never scans/removes old names or creates a second token link.
        for retained in self.root.glob('.codex-token-*'):
            self.assertEqual(list(retained.iterdir()), [])
            self.assertEqual((retained.stat().st_uid, stat.S_IMODE(retained.stat().st_mode)), (0, 0o700))

    def test_actual_ansible_stage_tasks_and_check_mode_touch_only_codex_token(self):
        play = yaml.safe_load((TOOLS.parent / 'relay-codex-credentials.yml').read_text())
        variables = {
            'ansible_connection': 'local', 'ansible_python_interpreter': '/usr/bin/python3',
            'relay_state_root': str(self.root), 'relay_config_root': str(self.root),
            'relay_codex_credential_source_file': str(self.source),
            'relay_codex_access_token_file': str(self.destination),
            'relay_codex_user': self.user.pw_name, 'relay_codex_group': self.group.gr_name,
            'relay_production_operation_lock_path': str(self.lock),
            'relay_production_operation_record_path': str(self.operation),
            'relay_install_root': str(self.install), 'relay_production_exact_head': self.head,
        }
        fixture = self.root / 'stage.yml'
        fixture.write_text(yaml.safe_dump([{'hosts': 'localhost', 'gather_facts': False,
                                           'vars': variables, 'tasks': play[0]['tasks']}]))
        (self.root / 'tools').symlink_to(TOOLS)
        unrelated = {}
        for name in ['writer-app-key', 'reviewer-app-key', 'runner-credentials']:
            path = self.root / name
            path.write_bytes(b'opaque-fixture-' + name.encode())
            unrelated[name] = stage.stamp(path.stat())
        command = [str(Path(sys.executable).with_name('ansible-playbook')), '-i', 'localhost,', str(fixture)]
        environment = {**os.environ, 'ANSIBLE_NOCOLOR': '1', 'ANSIBLE_CONFIG': str(TOOLS.parent / 'ansible.cfg'),
                       'PYTHONDONTWRITEBYTECODE': '1'}
        for check in [True, False, False]:
            result = subprocess.run(command + (['--check'] if check else []), capture_output=True,
                                    text=True, env=environment, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('CODEX_CREDENTIAL_STAGE=' + ('PLANNED' if check else 'PASS'), result.stdout)
            self.assertNotIn(self.token.decode().strip(), result.stdout + result.stderr)
            if check:
                self.assert_absent()
            else:
                self.assertEqual(self.destination.read_bytes(), self.token)
            self.assertFalse(list(self.root.glob('.codex-credential-helper-*')))
            self.assertEqual(unrelated, {name: stage.stamp((self.root / name).stat()) for name in unrelated})


if __name__ == '__main__':
    unittest.main()
