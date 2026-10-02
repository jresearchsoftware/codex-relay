"""Exercise registration through the public CLI with synthetic SSH responses."""
import unittest

import test_deployment as deployment_tests


class RegistrationCliTests(unittest.TestCase):
    invoke = deployment_tests.EntrypointTests.invoke

    @classmethod
    def setUpClass(cls):
        deployment_tests.EntrypointTests.setUpClass.__func__(cls)
        ssh = cls.bin / 'ssh'
        ssh.write_text(ssh.read_text() + '''
elif '--expect-binding' in sys.argv[-1]:
    import shlex
    binding = shlex.split(sys.argv[-1])[-1]
    sys.stdin.read()
    print('RUNNER_REGISTRATION_PASS ' + binding.replace(' group=', ' version=2.336.0 state=reused group=', 1))
''')

    @classmethod
    def tearDownClass(cls):
        deployment_tests.EntrypointTests.tearDownClass.__func__(cls)

    def test_registration_phases_allow_missing_or_ephemeral_tokens_without_backend_or_log(self):
        for phase, flag in [('runner-register', '--runner-registration-token'),
                            ('general-runner-register', '--general-runner-registration-token')]:
            for token_arguments in [[], [flag, 'synthetic-ephemeral-input']]:
                with self.subTest(phase=phase, supplied=bool(token_arguments)):
                    before = self.config.read_bytes()
                    result = self.invoke('--phase', phase, '--authorize-' + phase, *token_arguments)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn('state=reused', result.stdout)
                    self.assertNotIn('synthetic-ephemeral-input', result.stdout + result.stderr)
                    self.assertFalse(self.capture.exists(), 'registration does not serialize an Ansible inventory')
                    self.assertFalse((self.base / 'logs').exists(), 'registration does not create normal deployment logs')
                    self.assertEqual(self.config.read_bytes(), before)

    def test_registration_requires_matching_authority_and_token_phase(self):
        for arguments in [('--phase', 'runner-register'),
                          ('--phase', 'runner-register', '--authorize-general-runner-register'),
                          ('--phase', 'runner-register', '--authorize-runner-register',
                           '--general-runner-registration-token', 'synthetic-ephemeral-input')]:
            with self.subTest(arguments=arguments):
                self.calls.unlink(missing_ok=True)
                result = self.invoke(*arguments)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('synthetic-ephemeral-input', result.stdout + result.stderr)
                self.assertFalse(self.calls.exists(), 'reject wrong authority before target contact')

    def test_registration_does_not_report_success_if_final_host_guard_fails(self):
        marker = self.base / 'guard-fail'
        marker.touch()
        try:
            result = self.invoke('--phase', 'runner-register', '--authorize-runner-register')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('host-operation-guard-final-check', result.stderr)
            self.assertNotIn('RELAY_DEPLOYMENT_RESULT=PASS', result.stdout)
        finally:
            marker.unlink()
