"""Real protected Linux files and synthetic PEMs; no credentials or network."""
import grp
import importlib.util
import json
import os
from pathlib import Path
import select
import shutil
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
    SPEC = importlib.util.spec_from_file_location('reviewer_credential_stage', TOOLS / 'reviewer-credential-stage.py')
    stage = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(stage)
finally:
    sys.path.pop(0)


@unittest.skipUnless(os.name != 'nt' and os.geteuid() == 0 and shutil.which('openssl'),
                     'native root filesystem and OpenSSL tests')
class ReviewerCredentialStagingTests(unittest.TestCase):
    ROLE = 'reviewer'
    GROUP = 'nogroup'
    MODE = 0o640

    @classmethod
    def setUpClass(cls):
        cls.keys = []
        for _ in range(2):
            result = subprocess.run(
                ['openssl', 'genpkey', '-algorithm', 'RSA', '-pkeyopt', 'rsa_keygen_bits:2048'],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True)
            cls.keys.append(result.stdout)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='relay-reviewer-credential-test-', dir='/run')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.group = grp.getgrnam(self.GROUP)
        self.head = 'a' * 40
        self.install = self.root / 'install'
        self.release = self.install / 'releases' / self.head
        self.release.mkdir(parents=True, mode=0o750)
        self.manifest = self.release / 'artifact-manifest.json'
        self.manifest.write_text(json.dumps({'schemaVersion': '1.0', 'commit': self.head,
                                           'installedRevision': self.head}))
        self.manifest.chmod(0o640)
        (self.install / 'current').symlink_to(self.release)
        self.source = self.root / 'source.pem'
        self.source.write_bytes(self.keys[0])
        self.source.chmod(0o600)
        self.credentials = self.root / (self.ROLE + '-credentials')
        self.credentials.mkdir(mode=0o750)
        os.chown(self.credentials, 0, self.group.gr_gid)
        self.destination = self.credentials / 'github-app-private-key.pem'
        self.env = self.credentials / 'github-app.env'
        self.env.write_text('# managed-by: codex-relay\n'
                            'GITHUB_APP_PRIVATE_KEY_FILE=' + str(self.destination) + '\n'
                            'GITHUB_APP_ID=1001\nGITHUB_APP_INSTALLATION_ID=2001\n')
        self.env.chmod(self.MODE)
        os.chown(self.env, 0, self.group.gr_gid)
        self.runtime = self.root / 'runtime'
        self.runtime.mkdir(mode=0o750)
        self.lock = self.runtime / 'production-operation.lock'
        self.lock.touch(mode=0o644)
        self.lock.chmod(0o644)
        self.operation = self.root / 'production-operation.json'
        self.args = SimpleNamespace(source=str(self.source), destination=str(self.destination),
            group=self.group.gr_name, env_file=str(self.env), app_id='1001', installation_id='2001',
            lock_file=str(self.lock), operation_record=str(self.operation),
            manifest=str(self.install / 'current' / 'artifact-manifest.json'), exact_head=self.head,
            check=False, role=self.ROLE)

    def run_stage(self):
        return stage.stage(self.args)

    def stage_command(self):
        command = [sys.executable, str(TOOLS / 'reviewer-credential-stage.py')]
        for name, value in vars(self.args).items():
            if name != 'check':
                command.extend(['--' + name.replace('_', '-'), value])
        if self.args.check:
            command.append('--check')
        return command

    def assert_absent(self):
        self.assertFalse(self.destination.exists())
        self.assertEqual(sorted(path.name for path in self.credentials.iterdir()), ['github-app.env'])

    def test_stages_only_selected_role_and_is_idempotent_without_changing_source(self):
        before = self.source.stat()
        other_role = 'reviewer' if self.ROLE == 'writer' else 'writer'
        unrelated = self.root / (other_role + '-key-do-not-touch')
        unrelated.write_bytes(b'unrelated-private-fixture')
        result = self.run_stage()
        self.assertTrue(result['changed'])
        self.assertEqual(result['proof'], self.ROLE.upper() + '_CREDENTIAL_STAGE=PASS;head=' + self.head)
        info = self.destination.stat()
        self.assertEqual((info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)),
                         (0, self.group.gr_gid, self.MODE))
        self.assertEqual(self.destination.read_bytes(), self.keys[0])
        self.assertEqual(self.source.read_bytes(), self.keys[0])
        self.assertEqual((before.st_ino, before.st_mtime_ns, before.st_ctime_ns),
                         (self.source.stat().st_ino, self.source.stat().st_mtime_ns, self.source.stat().st_ctime_ns))
        self.assertEqual(unrelated.read_bytes(), b'unrelated-private-fixture')
        self.assertFalse(self.run_stage()['changed'])
        after = self.destination.stat()
        self.assertEqual((after.st_ino, after.st_mtime_ns, after.st_ctime_ns),
                         (info.st_ino, info.st_mtime_ns, info.st_ctime_ns))
        self.assertFalse(self.operation.exists())

    def test_check_validates_but_does_not_stage(self):
        self.args.check = True
        self.assertEqual(self.run_stage()['status'], self.ROLE.upper() + '_CREDENTIAL_STAGE_PLANNED')
        self.assert_absent()

    def test_abrupt_exit_after_durable_publication_retries_without_cleanup(self):
        # Run the real CLI and kill the process immediately after its first
        # directory fsync with a published destination. os._exit deliberately
        # bypasses finally blocks, reproducing interruption between link and
        # temporary-name removal in the former implementation.
        harness = '''import os, runpy, stat, sys
destination = sys.argv.pop(1)
sys.argv.pop(0)
sys.path.insert(0, os.path.dirname(sys.argv[0]))
fsync = os.fsync
def interrupt_after_publication(fd):
    fsync(fd)
    if stat.S_ISDIR(os.fstat(fd).st_mode) and os.path.exists(destination):
        os._exit(73)
os.fsync = interrupt_after_publication
runpy.run_path(sys.argv[0], run_name='__main__')
'''
        command = self.stage_command()
        interrupted = subprocess.run(
            [sys.executable, '-c', harness, str(self.destination)] + command[1:],
            capture_output=True, timeout=30, check=False)
        self.assertEqual(interrupted.returncode, 73, interrupted.stderr)
        self.assertEqual(interrupted.stdout + interrupted.stderr, b'')
        self.assertEqual(self.destination.stat().st_nlink, 1)
        self.assertEqual(self.destination.read_bytes(), self.keys[0])
        self.assertFalse(list(self.credentials.glob('.' + self.ROLE + '-key-*')))
        before = self.destination.stat()

        retried = subprocess.run(command, capture_output=True, timeout=30, check=False)
        self.assertEqual(retried.returncode, 0, retried.stderr)
        self.assertEqual(json.loads(retried.stdout)['status'], self.ROLE.upper() + '_CREDENTIAL_UNCHANGED')
        self.assertFalse(json.loads(retried.stdout)['changed'])
        after = self.destination.stat()
        self.assertEqual((before.st_ino, before.st_mtime_ns, before.st_ctime_ns),
                         (after.st_ino, after.st_mtime_ns, after.st_ctime_ns))
        self.assertEqual(self.source.read_bytes(), self.keys[0])
        self.assertEqual(sorted(path.name for path in self.credentials.iterdir()),
                         ['github-app-private-key.pem', 'github-app.env'])
        self.assertFalse(self.operation.exists())

    def test_existing_different_key_is_never_replaced(self):
        self.destination.write_bytes(self.keys[1])
        self.destination.chmod(self.MODE)
        os.chown(self.destination, 0, self.group.gr_gid)
        with self.assertRaisesRegex(ValueError, 'existing-credential-differs'):
            self.run_stage()
        self.assertEqual(self.destination.read_bytes(), self.keys[1])

    def test_symlink_source_destination_or_parent_is_refused(self):
        real = self.root / 'real-source.pem'
        self.source.rename(real)
        self.source.symlink_to(real)
        with self.assertRaises(OSError):
            self.run_stage()
        self.assert_absent()
        self.source.unlink()
        real.rename(self.source)
        self.destination.symlink_to(self.source)
        with self.assertRaises(OSError):
            self.run_stage()
        self.destination.unlink()
        parent = self.root / 'real-credentials'
        self.credentials.rename(parent)
        self.credentials.symlink_to(parent)
        with self.assertRaises(OSError):
            self.run_stage()
        self.assertFalse((parent / self.destination.name).exists())

    def test_invalid_key_permissions_and_untrusted_owner_are_refused(self):
        for mode in [0o644, 0o660, 0o400]:
            with self.subTest(mode=mode):
                self.source.chmod(mode)
                with self.assertRaisesRegex(ValueError, 'file-metadata'):
                    self.run_stage()
                self.assert_absent()
        self.source.chmod(0o600)
        os.chown(self.source, 65534, self.group.gr_gid)
        with self.assertRaisesRegex(ValueError, 'file-metadata'):
            self.run_stage()

    def test_group_writable_source_or_lock_parent_is_refused(self):
        self.runtime.chmod(0o770)
        with self.assertRaisesRegex(ValueError, 'parent'):
            self.run_stage()
        self.runtime.chmod(0o750)
        self.root.chmod(0o770)
        with self.assertRaisesRegex(ValueError, 'parent'):
            self.run_stage()
        self.assert_absent()

    def test_env_identity_duplicates_and_extra_assignments_fail_before_write(self):
        original = self.env.read_text()
        for raw in [original.replace('1001', '1002'), original.replace(str(self.destination), str(self.source)),
                    original + 'GITHUB_APP_ID=1001\n', original + 'WRITER_TOKEN=unexpected\n']:
            with self.subTest(raw_kind=raw.splitlines()[-1].split('=')[0]):
                self.env.write_text(raw)
                with self.assertRaisesRegex(ValueError, 'app-env'):
                    self.run_stage()
                self.assert_absent()

    def test_invalid_private_material_has_bounded_output(self):
        marker = b'not-a-key-private-fixture-must-not-leak'
        generated_lines = self.keys[0].splitlines()
        self.source.write_bytes(b'\n'.join([generated_lines[0], marker, generated_lines[-1], b'']))
        command = [sys.executable, str(TOOLS / 'reviewer-credential-stage.py')]
        for name, value in vars(self.args).items():
            if name != 'check':
                command.extend(['--' + name.replace('_', '-'), value])
        result = subprocess.run(command, capture_output=True, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, b'')
        self.assertEqual(result.stderr, (self.ROLE.upper() + '_CREDENTIAL_STAGE_BLOCKED=private-key\n').encode())
        self.assertNotIn(marker, result.stdout + result.stderr)
        self.assert_absent()

    def test_non_rsa_and_encrypted_keys_are_refused_but_crlf_rsa_is_valid(self):
        ec = subprocess.run(['openssl', 'genpkey', '-algorithm', 'EC', '-pkeyopt', 'ec_paramgen_curve:P-256'],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True).stdout
        encrypted = subprocess.run(['openssl', 'pkey', '-aes-256-cbc', '-passout', 'pass:fixture-only'],
                                   input=self.keys[0], stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, check=True).stdout
        for raw in [ec, encrypted]:
            self.source.write_bytes(raw)
            with self.assertRaisesRegex(ValueError, 'private-key'):
                self.run_stage()
            self.assert_absent()
        self.source.write_bytes(self.keys[0].replace(b'\n', b'\r\n'))
        self.assertTrue(self.run_stage()['changed'])

    def test_existing_identical_key_with_wrong_owner_or_mode_is_not_repaired(self):
        self.destination.write_bytes(self.keys[0])
        self.destination.chmod(0o600 if self.MODE == 0o640 else 0o640)
        os.chown(self.destination, 0, self.group.gr_gid)
        with self.assertRaisesRegex(ValueError, 'file-metadata'):
            self.run_stage()
        self.assertEqual(stat.S_IMODE(self.destination.stat().st_mode),
                         0o600 if self.MODE == 0o640 else 0o640)
        self.destination.chmod(self.MODE)
        os.chown(self.destination, 65534, self.group.gr_gid)
        with self.assertRaisesRegex(ValueError, 'file-metadata'):
            self.run_stage()
        self.assertEqual(self.destination.stat().st_uid, 65534)

    def test_existing_hardlinks_are_rejected_even_with_helper_shaped_alias(self):
        for raw in self.keys:
            for alias_name in ['foreign-key-alias', '.' + self.ROLE + '-key-' + 'a' * 32]:
                with self.subTest(matching=raw == self.keys[0], alias=alias_name):
                    self.destination.write_bytes(raw)
                    self.destination.chmod(self.MODE)
                    os.chown(self.destination, 0, self.group.gr_gid)
                    alias = self.credentials / alias_name
                    os.link(self.destination, alias)
                    before = self.destination.stat()
                    with self.assertRaisesRegex(ValueError, 'file-metadata'):
                        self.run_stage()
                    self.assertEqual(self.destination.read_bytes(), raw)
                    self.assertEqual(alias.stat().st_ino, before.st_ino)
                    after = self.destination.stat()
                    self.assertEqual((after.st_ino, after.st_nlink, after.st_mtime_ns, after.st_ctime_ns),
                                     (before.st_ino, before.st_nlink, before.st_mtime_ns, before.st_ctime_ns))
                    alias.unlink()
                    self.destination.unlink()

    def test_source_hardlink_or_fifo_and_symlink_env_are_refused(self):
        os.link(self.source, self.root / 'source-alias.pem')
        with self.assertRaisesRegex(ValueError, 'file-metadata'):
            self.run_stage()
        (self.root / 'source-alias.pem').unlink()
        self.source.unlink()
        os.mkfifo(self.source, 0o600)
        with self.assertRaisesRegex(ValueError, 'file-metadata'):
            self.run_stage()
        self.source.unlink()
        self.source.write_bytes(self.keys[0])
        self.source.chmod(0o600)
        real_env = self.credentials / 'actual.env'
        self.env.rename(real_env)
        self.env.symlink_to(real_env)
        with self.assertRaises(OSError):
            self.run_stage()
        self.assertFalse(self.destination.exists())

    def test_source_changed_after_key_validation_fails_closed(self):
        validate = stage.validate_key
        def replace_after_validation(raw):
            validate(raw)
            replacement = self.root / 'replacement.pem'
            replacement.write_bytes(self.keys[1])
            replacement.chmod(0o600)
            replacement.replace(self.source)
        with patch.object(stage, 'validate_key', side_effect=replace_after_validation):
            with self.assertRaisesRegex(ValueError, 'file-changed'):
                self.run_stage()
        self.assert_absent()

    def test_destination_race_is_not_overwritten_and_staging_is_cleaned(self):
        publish = stage.publish_no_replace
        def compete(*args, **kwargs):
            self.destination.write_bytes(self.keys[1])
            self.destination.chmod(self.MODE)
            os.chown(self.destination, 0, self.group.gr_gid)
            return publish(*args, **kwargs)
        with patch.object(stage, 'publish_no_replace', side_effect=compete):
            with self.assertRaises(FileExistsError):
                self.run_stage()
        self.assertEqual(self.destination.read_bytes(), self.keys[1])
        self.assertFalse(list(self.credentials.glob('.' + self.ROLE + '-key-*')))

    def test_active_operation_or_wrong_installed_head_refuses_staging(self):
        self.operation.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'operation-recovery-required'):
            self.run_stage()
        self.operation.unlink()
        self.manifest.write_text(json.dumps({'schemaVersion': '1.0', 'commit': 'b' * 40,
                                            'installedRevision': self.head}))
        with self.assertRaisesRegex(ValueError, 'installed-head'):
            self.run_stage()
        self.assert_absent()

    def test_persistent_guard_serializes_until_controller_pipe_closes(self):
        command = [sys.executable, str(TOOLS / 'bootstrap_guard.py'), '--hold']
        for name in ['lock_file', 'operation_record', 'manifest', 'exact_head']:
            command.extend(['--' + name.replace('_', '-'), getattr(self.args, name)])
        guard = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            self.assertTrue(select.select([guard.stdout], [], [], 5)[0], 'guard ready timeout')
            self.assertEqual(guard.stdout.readline(), b'BOOTSTRAP_GUARD_READY\n')
            with self.assertRaises(BlockingIOError):
                self.run_stage()
            self.assert_absent()
            guard.stdin.close()
            self.assertEqual(guard.wait(timeout=5), 0)
            self.assertEqual(guard.stderr.read(), b'')
        finally:
            if guard.poll() is None:
                guard.kill()
                guard.wait(timeout=5)
            guard.stdout.close()
            guard.stderr.close()
            if not guard.stdin.closed:
                guard.stdin.close()
        self.assertTrue(self.run_stage()['changed'])

    def test_actual_ansible_stage_tasks_and_check_mode_preserve_unrelated_credentials(self):
        playbook = yaml.safe_load((TOOLS.parent / ('relay-' + self.ROLE + '-credentials.yml')).read_text())
        variables = {
            'ansible_connection': 'local', 'ansible_python_interpreter': '/usr/bin/python3',
            'relay_state_root': str(self.root), 'relay_' + self.ROLE + '_credential_source_file': str(self.source),
            'relay_' + self.ROLE + '_credential_key_file': str(self.destination),
            'relay_reviewer_group': self.group.gr_name, 'relay_' + self.ROLE + '_credential_env_file': str(self.env),
            'relay_' + self.ROLE + '_app_id': '1001', 'relay_' + self.ROLE + '_app_installation_id': '2001',
            'relay_production_operation_lock_path': str(self.lock),
            'relay_production_operation_record_path': str(self.operation),
            'relay_install_root': str(self.install), 'relay_production_exact_head': self.head,
        }
        fixture = self.root / 'stage.yml'
        fixture.write_text(yaml.safe_dump([{'hosts': 'localhost', 'gather_facts': False,
                                           'vars': variables, 'tasks': playbook[0]['tasks']}]))
        (self.root / 'tools').symlink_to(TOOLS)
        other_role = 'reviewer' if self.ROLE == 'writer' else 'writer'
        unrelated_names = [other_role + '-key', 'codex-token', 'runner-credentials']
        for name in unrelated_names:
            (self.root / name).write_bytes(b'private-fixture-' + name.encode())
        unrelated = {name: (self.root / name).read_bytes()
                     for name in unrelated_names}
        command = [str(Path(sys.executable).with_name('ansible-playbook')), '-i', 'localhost,', str(fixture)]
        environment = {**os.environ, 'ANSIBLE_NOCOLOR': '1', 'ANSIBLE_CONFIG': str(TOOLS.parent / 'ansible.cfg'),
                       'PYTHONDONTWRITEBYTECODE': '1'}
        for check in [True, False, False]:
            result = subprocess.run(command + (['--check'] if check else []),
                                    capture_output=True, text=True, env=environment, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(self.ROLE.upper() + '_CREDENTIAL_STAGE=' + ('PLANNED' if check else 'PASS'), result.stdout)
            if check:
                self.assertFalse(self.destination.exists())
            else:
                self.assertEqual(self.destination.read_bytes(), self.keys[0])
            self.assertFalse(list(self.root.glob('.' + self.ROLE + '-credential-helper-*')))
            self.assertEqual(unrelated, {name: (self.root / name).read_bytes() for name in unrelated})
class WriterCredentialStagingTests(ReviewerCredentialStagingTests):
    ROLE = 'writer'
    GROUP = 'root'
    MODE = 0o600

    def test_writer_rejects_reviewer_group_or_group_readable_destination(self):
        self.args.group = 'nogroup'
        with self.assertRaisesRegex(ValueError, 'writer-group'):
            self.run_stage()
        self.args.group = 'root'
        self.destination.write_bytes(self.keys[0])
        self.destination.chmod(0o640)
        with self.assertRaisesRegex(ValueError, 'file-metadata'):
            self.run_stage()
        self.destination.unlink()
        self.env.chmod(0o640)
        with self.assertRaisesRegex(ValueError, 'file-metadata'):
            self.run_stage()
        self.assert_absent()

if __name__ == '__main__':
    unittest.main()
