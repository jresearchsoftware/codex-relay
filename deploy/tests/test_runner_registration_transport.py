"""Ephemeral transport and bounded-result behavior without SSH or credentials."""
import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock, patch


SPEC = importlib.util.spec_from_file_location('runner_registration', Path(__file__).resolve().parents[1] / 'runner_registration.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.values = {'relay_runner_name': 'production-runner',
                       'relay_production_runner_name': 'production-runner',
                       'relay_general_runner_name': 'general-runner',
                       'relay_general_runner_registration_scope': 'repository',
                       'relay_production_runner_registration_group': 'production-group',
                       'relay_runner_labels': ['production'],
                       'relay_github_repository': 'example/consumer',
                       'relay_install_root': '/opt/example-relay',
                       'relay_state_root': '/var/lib/example-relay'}
        self.target = {'user': 'root', 'host': 'deployment.example.invalid'}
        self.guard = Mock()
        self.guard.poll.return_value = None
        self.process = Mock(returncode=0)
        self.process.poll.return_value = 0
        self.process.communicate.return_value = ('RUNNER_REGISTRATION_PASS url=https://github.com/example '
                                                'name=production-runner label=production '
                                                'version=2.336.0 state=reused group=production-group '
                                                'work=/var/lib/example-relay/runner/work\n', '')

    def invoke(self, token=None):
        with patch.object(MODULE.subprocess, 'Popen', return_value=self.process) as popen:
            result = MODULE.register_runner(self.target, '/path/to/key', self.values, 'a' * 40, token, self.guard)
        return result, popen

    def test_token_only_reaches_stdin_and_is_not_in_ssh_command(self):
        proof, popen = self.invoke('synthetic-ephemeral-token')
        self.assertIn('state=reused', proof)
        self.assertNotIn('synthetic-ephemeral-token', str(popen.call_args))
        self.process.communicate.assert_called_once_with(input='synthetic-ephemeral-token\n', timeout=1)
        self.assertTrue(popen.call_args.args[0][-1].startswith('/opt/example-relay/relay-runner-registration --expect-binding '))
        self.assertIn('group=production-group', popen.call_args.args[0][-1])

    def test_missing_optional_token_still_invokes_reuse_check(self):
        self.invoke()
        self.process.communicate.assert_called_once_with(input='\n', timeout=1)

    def test_general_helper_and_repository_identity_are_selected(self):
        self.values['relay_runner_name'] = '{{ relay_general_runner_name }}'
        self.values['relay_runner_labels'] = ['general']
        self.process.communicate.return_value = ('RUNNER_REGISTRATION_PASS url=https://github.com/example/consumer '
                                                'name=general-runner label=general '
                                                'version=2.336.0 state=registered group=- '
                                                'work=/var/lib/example-relay/general-runner/work\n', '')
        _, popen = self.invoke()
        self.assertTrue(popen.call_args.args[0][-1].startswith('/opt/example-relay/relay-general-runner-registration --expect-binding '))

    def test_raw_errors_and_token_are_never_reemitted(self):
        self.process.returncode = 1
        self.process.communicate.return_value = ('sensitive runner output', 'secret input\nRUNNER_REGISTRATION_FAIL code=FRESH_REGISTRATION_TOKEN_REQUIRED\n')
        with self.assertRaisesRegex(RuntimeError, '^RUNNER_REGISTRATION_FAIL code=FRESH_REGISTRATION_TOKEN_REQUIRED;next=fresh registration token required$'):
            self.invoke('synthetic-ephemeral-token')

    def test_unknown_status_and_wrong_proof_fail_closed(self):
        self.process.returncode = 1
        self.process.communicate.return_value = ('', 'sensitive transport error')
        with self.assertRaisesRegex(RuntimeError, 'REGISTRATION_TRANSPORT_UNPROVEN'):
            self.invoke()
        self.process.returncode = 0
        self.process.communicate.return_value = ('RUNNER_REGISTRATION_PASS url=https://github.com/another '
                                                'name=production-runner label=production '
                                                'version=2.336.0 state=reused group=production-group '
                                                'work=/var/lib/example-relay/runner/work\n', '')
        with self.assertRaisesRegex(RuntimeError, 'proof-unproven'):
            self.invoke()

    def test_host_guard_loss_stops_registration_and_requires_diagnosis(self):
        self.guard.poll.side_effect = [None, None, 1]
        self.process.poll.return_value = None
        self.process.communicate.side_effect = subprocess.TimeoutExpired('ssh', 1)
        with self.assertRaisesRegex(RuntimeError, 'host-operation-guard-lost'):
            self.invoke()
        self.process.terminate.assert_called_once()

    def test_changed_group_requires_reapplying_installed_configuration(self):
        self.values['relay_production_runner_registration_group'] = 'new-group'
        with self.assertRaisesRegex(RuntimeError, 'proof-unproven'):
            self.invoke()

    def test_invalid_token_does_not_reach_ssh(self):
        for token in ('bad\ninput', 'bad\x00input', 'a' * 4097):
            with self.subTest(token_length=len(token)), patch.object(MODULE.subprocess, 'Popen') as popen:
                with self.assertRaisesRegex(RuntimeError, 'token-invalid-input'):
                    MODULE.register_runner(self.target, '/path/to/key', self.values, 'a' * 40, token, self.guard)
                popen.assert_not_called()


if __name__ == '__main__':
    unittest.main()
