"""Run the installed helper with an unprivileged synthetic runner package."""
import grp
import json
import os
from pathlib import Path
import pwd
import subprocess
import tempfile
import unittest

from jinja2 import Environment, StrictUndefined


TEMPLATE = Path(__file__).resolve().parents[1] / 'roles/relay_runner/templates/relay-runner-registration.j2'


@unittest.skipUnless(os.name == 'posix', 'Linux runner helper')
class RegistrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='relay-registration-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        # The managed worker's temporary parent may carry a collector setgid.
        # This fixture models a private runner group without inheriting it.
        self.root.chmod(0o700)
        self.runner = self.root / 'runner'
        self.runner.mkdir(mode=0o750)
        self.runner.chmod(0o750)
        self.state_root = self.root / 'state'
        self.state_root.mkdir(mode=0o755)
        self.pending = self.state_root / 'runner-registration-production-runner.pending'
        (self.runner / '_diag').mkdir()
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.executable(self.bin / 'id', '#!/bin/sh\necho 0\n')
        self.executable(self.bin / 'runuser', '''#!/bin/bash
while [[ "$1" != -- ]]; do
  case "$1" in --preserve-environment) shift;; --user) shift 2;; *) exit 2;; esac
done
shift
exec "$@"
''')
        (self.runner / 'bin').mkdir()
        self.executable(self.runner / 'bin/Runner.Listener', '#!/bin/sh\necho 2.336.0\n')
        self.executable(self.runner / 'run.sh', '#!/bin/sh\nexit 0\n')
        self.marker = {'agentId': 123, 'agentName': 'production-runner',
                       'gitHubUrl': 'https://github.com/example',
                       'poolName': 'production-group', 'workFolder': str(self.root / 'work')}
        self.executable(self.runner / 'config.sh', '''#!/usr/bin/python3
import json, os
from pathlib import Path
Path('calls').open('a').write('called\\n')
token = os.environ.get('ACTIONS_RUNNER_INPUT_TOKEN')
if token == 'expired-synthetic-token':
    print("Http response code: Unauthorized from 'POST https://api.github.com/actions/runner-registration' (Request Id: fixture)")
    print('Bad credentials ' + token)
    raise SystemExit(1)
if token in ('rejected-synthetic-token', 'forbidden-synthetic-token'):
    code = 'NotFound' if token == 'rejected-synthetic-token' else 'Forbidden'
    print("Http response code: " + code + " from 'POST https://api.github.com/actions/runner-registration' (Request Id: fixture)")
    raise SystemExit(1)
if token == 'ambiguous-synthetic-token':
    print('unexpected failure ' + token)
    raise SystemExit(1)
if token == 'later-unauthorized-synthetic-token':
    print('Http response code: Unauthorized: Bad credentials ' + token)
    raise SystemExit(1)
if token == 'retried-exchange-synthetic-token':
    print("Http response code: Unauthorized from 'POST https://api.github.com/actions/runner-registration' (Request Id: fixture)")
    print('Connected to GitHub')
    print('unexpected failure ' + token)
    raise SystemExit(1)
if token == 'rsa-residue-synthetic-token':
    Path('.credentials_rsaparams').write_text('PRIVATE_RSA_FIXTURE_NEVER_PRINT')
    Path('.credentials_rsaparams').chmod(0o600)
    print("Http response code: Unauthorized from 'POST https://api.github.com/actions/runner-registration' (Request Id: fixture)")
    raise SystemExit(1)
Path('.runner').write_text(%r)
Path('.credentials').write_text('{}')
Path('.runner').chmod(0o600)
Path('.credentials').chmod(0o600)
''' % json.dumps(self.marker))
        values = dict(relay_runner_root=str(self.runner), relay_runner_user=pwd.getpwuid(os.getuid()).pw_name,
                      relay_state_root=str(self.state_root),
                      relay_runner_group=grp.getgrgid(os.getgid()).gr_name,
                      relay_runner_repository='example/consumer', relay_github_repository='example/consumer',
                      relay_runner_name='production-runner', relay_runner_registration_scope='organization',
                      relay_runner_registration_group='production-group', relay_runner_labels=['production'],
                      relay_runner_registration_marker=str(self.runner / '.runner'),
                      relay_runner_credentials_marker=str(self.runner / '.credentials'),
                      relay_runner_home=str(self.root / 'home'), relay_runner_work_root=str(self.root / 'work'))
        self.helper = self.root / 'registration'
        self.executable(self.helper, Environment(undefined=StrictUndefined).from_string(TEMPLATE.read_text()).render(values))

    def executable(self, path, content):
        path.write_text(content)
        path.chmod(0o750)

    def run_helper(self, token='', *arguments):
        return subprocess.run(['bash', self.helper, *arguments], input=token + '\n', text=True, capture_output=True,
                              env={**os.environ, 'PATH': str(self.bin) + ':' + os.environ['PATH']})

    def registered(self, marker=None):
        for name, content in (('.runner', json.dumps(marker or self.marker)), ('.credentials', '{}')):
            (self.runner / name).write_text(content)
            (self.runner / name).chmod(0o600)

    def pending_registration(self, **changes):
        binding = ('url=https://github.com/example name=production-runner label=production '
                   'group=production-group work=' + str(self.root / 'work'))
        self.pending.write_text(json.dumps({'version': 1, 'binding': binding, **changes}))
        self.pending.chmod(0o600)

    def test_missing_token_is_actionable_and_never_attempts_registration(self):
        result = self.run_helper()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('fresh registration token required', result.stderr)
        self.assertFalse((self.runner / 'calls').exists())
        self.assertFalse(self.pending.exists())

    def test_pending_reinstall_blocks_direct_registration_and_preserves_evidence(self):
        journal = Path(str(self.state_root) + '-clean-reinstall.json')
        journal.write_text('{"stage":"DECOMMISSIONED"}')
        result = self.run_helper('fresh-synthetic-token')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('CLEAN_REINSTALL_RECOVERY_REQUIRED', result.stderr)
        self.assertNotIn('fresh-synthetic-token', result.stdout + result.stderr)
        self.assertFalse((self.runner / 'calls').exists())
        self.assertFalse(self.pending.exists())
        self.assertEqual(journal.read_text(), '{"stage":"DECOMMISSIONED"}')

    def test_changed_public_configuration_cannot_mutate_the_installed_runner(self):
        binding = ('url=https://github.com/example name=production-runner label=production '
                   'group=changed-group work=' + str(self.root / 'work'))
        result = self.run_helper('fresh-synthetic-token', '--expect-binding', binding)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('REGISTRATION_CONFIGURATION_MISMATCH', result.stderr)
        self.assertFalse((self.runner / 'calls').exists())

    def test_retry_after_expired_token_then_reuse_never_duplicates_registration(self):
        rejected = self.run_helper('expired-synthetic-token')
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn('FRESH_REGISTRATION_TOKEN_REQUIRED', rejected.stderr)
        self.assertNotIn('expired-synthetic-token', rejected.stdout + rejected.stderr)
        self.assertFalse(self.pending.exists())
        accepted = self.run_helper('fresh-synthetic-token')
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertIn('state=registered', accepted.stdout)
        self.assertFalse(self.pending.exists())
        for token in ('', 'expired-synthetic-token'):
            reused = self.run_helper(token)
            self.assertEqual(reused.returncode, 0, reused.stderr)
            self.assertIn('state=reused', reused.stdout)
        self.assertEqual((self.runner / 'calls').read_text(), 'called\ncalled\n')

    def test_unrecognized_failure_requires_diagnosis_before_retry(self):
        result = self.run_helper('ambiguous-synthetic-token')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('REGISTRATION_COMMAND_FAILED_INSPECT_BEFORE_RETRY', result.stderr)
        self.assertNotIn('ambiguous-synthetic-token', result.stdout + result.stderr)
        self.assertTrue(self.pending.exists())
        self.assertEqual(self.pending.stat().st_mode & 0o777, 0o600)
        self.assertNotIn('ambiguous-synthetic-token', self.pending.read_text())
        retried = self.run_helper('fresh-synthetic-token')
        self.assertNotEqual(retried.returncode, 0)
        self.assertIn('REGISTRATION_STATE_AMBIGUOUS', retried.stderr)
        self.assertEqual((self.runner / 'calls').read_text(), 'called\n')

    def test_only_complete_matching_registration_reconciles_interrupted_attempt(self):
        self.pending_registration()
        self.registered()
        result = self.run_helper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('state=reused', result.stdout)
        self.assertFalse(self.pending.exists())
        self.assertFalse((self.runner / 'calls').exists())

    def test_pending_without_registration_cannot_relaunch_after_interruption(self):
        self.pending_registration()
        result = self.run_helper('fresh-synthetic-token')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('REGISTRATION_STATE_AMBIGUOUS', result.stderr)
        self.assertTrue(self.pending.exists())
        self.assertFalse((self.runner / 'calls').exists())

    def test_mismatched_or_unsafe_pending_is_retained_even_with_complete_registration(self):
        self.registered()
        for changes in ({'version': 2}, {'binding': 'another runner'}, {'unexpected': True}):
            with self.subTest(changes=changes):
                self.pending_registration(**changes)
                result = self.run_helper()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('REGISTRATION_STATE_AMBIGUOUS', result.stderr)
                self.assertTrue(self.pending.exists())
        self.pending_registration()
        self.pending.chmod(0o644)
        result = self.run_helper()
        self.assertIn('REGISTRATION_STATE_AMBIGUOUS', result.stderr)
        self.pending.unlink()
        target = self.root / 'pending-target'
        target.write_text('preserve')
        self.pending.symlink_to(target)
        result = self.run_helper()
        self.assertIn('REGISTRATION_STATE_AMBIGUOUS', result.stderr)
        self.assertEqual(target.read_text(), 'preserve')
        self.assertFalse((self.runner / 'calls').exists())

    def test_authentication_error_after_possible_progress_is_not_retry_authority(self):
        for token in ('later-unauthorized-synthetic-token', 'retried-exchange-synthetic-token'):
            with self.subTest(token=token):
                result = self.run_helper(token)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('REGISTRATION_COMMAND_FAILED_INSPECT_BEFORE_RETRY', result.stderr)
                self.assertTrue(self.pending.exists())
                self.assertNotIn(token, result.stdout + result.stderr + self.pending.read_text())
                retried = self.run_helper('fresh-synthetic-token')
                self.assertIn('REGISTRATION_STATE_AMBIGUOUS', retried.stderr)
                # Each independent fixture scenario keeps its first unknown attempt.
                self.pending.unlink()
        self.assertEqual((self.runner / 'calls').read_text(), 'called\ncalled\n')

    def test_rejected_registration_exchange_requires_fresh_token(self):
        for token in ('rejected-synthetic-token', 'forbidden-synthetic-token'):
            with self.subTest(token=token):
                result = self.run_helper(token)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('FRESH_REGISTRATION_TOKEN_REQUIRED', result.stderr)
                self.assertNotIn(token, result.stdout + result.stderr)

    def test_mismatched_existing_identity_never_consumes_token_or_registers(self):
        for field in ('agentName', 'gitHubUrl', 'workFolder', 'poolName', 'agentId'):
            with self.subTest(field=field):
                self.registered({**self.marker, field: 'wrong'})
                result = self.run_helper('fresh-synthetic-token')
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('REGISTRATION_STATE_AMBIGUOUS', result.stderr)
                self.assertFalse((self.runner / 'calls').exists())

    def test_partial_registration_and_symlinks_require_reconciliation(self):
        (self.runner / '.runner').write_text('{}')
        result = self.run_helper('fresh-synthetic-token')
        self.assertIn('REGISTRATION_STATE_AMBIGUOUS', result.stderr)
        (self.runner / '.runner').unlink()
        (self.runner / '.runner').symlink_to(self.root / 'missing')
        result = self.run_helper('fresh-synthetic-token')
        self.assertIn('REGISTRATION_STATE_AMBIGUOUS', result.stderr)
        self.assertFalse((self.runner / 'calls').exists())

    def test_rsa_only_state_blocks_registration_and_preserves_existing_evidence(self):
        rsa = self.runner / '.credentials_rsaparams'
        for shape in ('regular', 'dangling'):
            with self.subTest(shape=shape):
                if shape == 'regular':
                    rsa.write_text('PRIVATE_RSA_FIXTURE_NEVER_PRINT')
                    rsa.chmod(0o600)
                else:
                    rsa.unlink()
                    rsa.symlink_to(self.root / 'missing-private-key')
                inode = rsa.lstat().st_ino
                result = self.run_helper('fresh-synthetic-token')
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('REGISTRATION_STATE_AMBIGUOUS', result.stderr)
                self.assertNotIn('fresh registration token required', result.stderr)
                self.assertNotIn('PRIVATE_RSA_FIXTURE', result.stdout + result.stderr)
                self.assertEqual(rsa.lstat().st_ino, inode)
                self.assertFalse((self.runner / 'calls').exists())
                self.assertFalse(self.pending.exists())

    def test_complete_registration_with_rsa_state_remains_reusable(self):
        self.registered()
        rsa = self.runner / '.credentials_rsaparams'
        rsa.write_text('PRIVATE_RSA_FIXTURE_NEVER_PRINT')
        rsa.chmod(0o600)
        inode = rsa.stat().st_ino
        result = self.run_helper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('state=reused', result.stdout)
        self.assertFalse((self.runner / 'calls').exists())
        self.assertEqual(rsa.stat().st_ino, inode)
        self.assertEqual(rsa.read_text(), 'PRIVATE_RSA_FIXTURE_NEVER_PRINT')

    def test_unauthorized_text_with_new_rsa_residue_cannot_clear_attempt_reservation(self):
        result = self.run_helper('rsa-residue-synthetic-token')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('REGISTRATION_STATE_AMBIGUOUS', result.stderr)
        self.assertNotIn('FRESH_REGISTRATION_TOKEN_REQUIRED', result.stderr)
        self.assertTrue(self.pending.exists())
        self.assertTrue((self.runner / '.credentials_rsaparams').exists())
        retry = self.run_helper('fresh-synthetic-token')
        self.assertIn('REGISTRATION_STATE_AMBIGUOUS', retry.stderr)
        self.assertEqual((self.runner / 'calls').read_text(), 'called\n')
        self.assertNotIn('rsa-residue-synthetic-token', result.stdout + result.stderr + self.pending.read_text())


if __name__ == '__main__':
    unittest.main()
