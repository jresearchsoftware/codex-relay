"""Exercise lifecycle ordering and failure containment without privileged actions."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
from lifecycle import execute

HEAD = 'a' * 40
OLD = 'b' * 40
OPERATION = '12345678-1234-1234-1234-123456789abc'


class Gate:
    """Capability fixture rejects reopening before independent proof."""
    def __init__(self, phase='open', target=HEAD):
        self.phase, self.target = phase, target
        self.operation = None if phase == 'open' else OPERATION
        self.calls = []
        self.unknown = []
        self.active = []
        self.verified = None

    def __call__(self, command, *arguments):
        self.calls.append((command, *arguments))
        options = dict(zip(arguments[::2], arguments[1::2]))
        if command != 'quiesce' and '--operation' in options and options['--operation'] != self.operation:
            raise ValueError('wrong-operation')
        if command == 'status':
            return {'phase': self.phase, 'target': self.target, 'operationId': self.operation,
                    'active': self.active, 'unknown': self.unknown}
        if command == 'quiesce':
            if self.phase != 'open':
                raise ValueError('retained-operation')
            self.phase, self.operation, self.target = 'quiesced', options['--operation'], options['--target']
        elif command == 'drain':
            if self.unknown:
                raise ValueError('unknown-execution')
            if self.phase not in ['quiesced', 'drained']:
                raise ValueError('invalid-drain-phase')
            self.phase = 'drained'
        elif command == 'phase':
            if options['--operation'] != self.operation:
                raise ValueError('wrong-operation')
            self.phase = options['--phase']
            self.verified = options.get('--revision')
        elif command == 'recovery-target':
            if self.phase != 'recovery-required' or self.active or self.unknown:
                raise ValueError('recovery-unproven')
            self.target = options['--target']
        elif command == 'resume':
            if self.phase != 'verified' or self.unknown:
                raise ValueError('unverified-resume')
            self.phase = 'open'
        else:
            raise AssertionError(command)
        return self.__call__('status')


class LifecycleTests(unittest.TestCase):
    def run_quiet(self, *arguments, **keywords):
        with redirect_stdout(io.StringIO()):
            return execute(*arguments, **keywords)

    def test_one_apply_and_same_operation_proof_precede_resume(self):
        gate = Gate()
        apply = Mock(return_value='independent-runtime-evidence')
        def verify(evidence, head):
            self.assertEqual(gate.phase, 'applying')
            self.assertEqual((evidence, head), ('independent-runtime-evidence', HEAD))
            return True
        operation = self.run_quiet(gate, HEAD, apply, verify, operation=OPERATION)
        self.assertEqual(operation, OPERATION)
        apply.assert_called_once_with()
        self.assertEqual(gate.phase, 'open')
        self.assertEqual(gate.verified, HEAD)
        commands = [call[0] for call in gate.calls if call[0] != 'status']
        self.assertEqual(commands, ['quiesce', 'drain', 'phase', 'phase', 'resume'])

    def test_stop_does_not_apply_verify_or_resume(self):
        gate, apply, verify = Gate(), Mock(), Mock()
        self.run_quiet(gate, HEAD, apply, verify, operation=OPERATION, stop=True)
        self.assertEqual(gate.phase, 'drained')
        apply.assert_not_called()
        verify.assert_not_called()
        self.assertNotIn('resume', [call[0] for call in gate.calls])

    def test_unknown_execution_stops_before_apply_and_keeps_admission_closed(self):
        gate, apply, verify = Gate(), Mock(), Mock()
        gate.unknown = [99]
        with self.assertRaisesRegex(ValueError, 'unknown-execution'):
            self.run_quiet(gate, HEAD, apply, verify, operation=OPERATION)
        self.assertEqual(gate.phase, 'quiesced')
        apply.assert_not_called()
        verify.assert_not_called()

    def test_apply_activation_and_proof_failures_never_resume(self):
        for failure in ['apply', 'activation', 'missing-proof', 'proof-read']:
            with self.subTest(failure=failure):
                gate = Gate()
                apply = Mock(side_effect=ValueError(failure)) if failure in ['apply', 'activation'] else Mock(return_value='evidence')
                verify = Mock(side_effect=OSError('proof-read')) if failure == 'proof-read' else Mock(return_value=False)
                with self.assertRaises((ValueError, OSError)):
                    self.run_quiet(gate, HEAD, apply, verify, operation=OPERATION)
                self.assertEqual(gate.phase, 'recovery-required')
                self.assertNotIn('resume', [call[0] for call in gate.calls])

    def test_failed_recovery_state_write_preserves_original_failure_and_closed_gate(self):
        gate = Gate()
        def capability(command, *arguments):
            if command == 'phase' and 'recovery-required' in arguments:
                raise OSError('state-write-failed')
            return gate(command, *arguments)
        with self.assertRaisesRegex(ValueError, 'original-apply-failure'):
            self.run_quiet(capability, HEAD, Mock(side_effect=ValueError('original-apply-failure')),
                           Mock(), operation=OPERATION)
        self.assertEqual(gate.phase, 'applying')
        self.assertNotIn('resume', [call[0] for call in gate.calls])

    def test_verified_rollback_uses_retained_operation_and_proves_old_target_before_resume(self):
        gate = Gate('recovery-required', target=HEAD)
        apply = Mock(return_value='accepted-old-release-runtime-proof')
        def verify(evidence, target):
            self.assertEqual((evidence, target), ('accepted-old-release-runtime-proof', OLD))
            self.assertEqual(gate.phase, 'applying')
            self.assertEqual(gate.operation, OPERATION)
            return True
        self.run_quiet(gate, OLD, apply, verify, operation=OPERATION,
                       already_quiesced=True, recovery=True)
        apply.assert_called_once_with()
        self.assertEqual(gate.verified, OLD)
        self.assertEqual(gate.phase, 'open')
        self.assertNotIn('quiesce', [call[0] for call in gate.calls])
        self.assertNotIn('drain', [call[0] for call in gate.calls])

    def test_recovery_cannot_apply_over_active_unknown_or_wrong_retained_operation(self):
        for boundary in ['active', 'unknown', 'wrong-operation', 'wrong-phase']:
            with self.subTest(boundary=boundary):
                gate = Gate('drained' if boundary == 'wrong-phase' else 'recovery-required')
                if boundary in ['active', 'unknown']:
                    setattr(gate, boundary, [99])
                apply, verify = Mock(), Mock()
                operation = '12345678-1234-1234-1234-123456789abd' if boundary == 'wrong-operation' else OPERATION
                with self.assertRaises(ValueError):
                    self.run_quiet(gate, OLD, apply, verify, operation=operation,
                                   already_quiesced=True, recovery=True)
                apply.assert_not_called()
                verify.assert_not_called()
                self.assertNotIn('resume', [call[0] for call in gate.calls])

    @unittest.skipUnless(shutil.which('node'), 'Node required for durable gate integration')
    def test_stop_survives_new_gate_process_without_privileged_filesystem_or_service_calls(self):
        # Exercise the actual atomic gate state, using its unprivileged test
        # boundary and empty attempt inventory. Each call creates a fresh Node
        # process, so retained quiescence cannot be an in-memory fixture claim.
        script = """
import { createAdmissionControl } from './controller/src/admission-control.mjs';
const [root, command, options] = JSON.parse(process.env.GATE_REQUEST);
const empty = { all: async () => [], get: async () => null };
const gate = createAdmissionControl({ root, consumerDigest: 'c'.repeat(64),
  store: empty, journal: empty, protectedRoot: false });
const value = command === 'drain' ? await gate.drained(options) : await gate[command](options);
console.log(JSON.stringify(value));
"""
        with tempfile.TemporaryDirectory(prefix='relay-durable-stop-', dir='/tmp') as directory:
            config = Path(directory) / 'consumer.json'
            shutil.copyfile(ROOT / 'consumer/fixtures/example.json', config)
            config.chmod(0o600)
            def gate(command, *arguments):
                options = dict(zip(arguments[::2], arguments[1::2]))
                options = {key.removeprefix('--'): value for key, value in options.items()}
                if 'operation' in options:
                    options['operationId'] = options.pop('operation')
                options.pop('timeout', None)
                result = subprocess.run([shutil.which('node'), '--import', './consumer/test-support/consumer-env.mjs',
                    '--input-type=module', '-e', script], cwd=ROOT, env={**os.environ,
                    'RELAY_CONSUMER_CONFIG': str(config),
                    'GATE_REQUEST': json.dumps([directory, command, options])}, text=True, capture_output=True, check=True)
                return json.loads(result.stdout)
            gate('initialize')
            self.run_quiet(gate, HEAD, Mock(), Mock(), operation=OPERATION, stop=True)
            self.assertEqual(gate('status')['phase'], 'drained')
            self.assertEqual(json.loads((Path(directory) / 'admission-v1.json').read_text())['operationId'], OPERATION)
            self.assertEqual((Path(directory) / 'admission-v1.json').stat().st_mode & 0o777, 0o600)


if __name__ == '__main__':
    unittest.main()
