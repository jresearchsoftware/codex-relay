"""Exercise operation-bound persistent pause and authenticated process control."""
import contextlib
import io
import json
import os
from pathlib import Path
import pwd
import socket
import subprocess
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

from jinja2 import Environment, StrictUndefined

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / 'roles/relay_runtime/templates'
OPERATION = '12345678-1234-1234-1234-123456789abc'


class ReviewerMaintenanceTests(unittest.TestCase):
    def load(self, directory):
        source = Environment(undefined=StrictUndefined).from_string(
            (TEMPLATES / 'relay-reviewer-maintenance.j2').read_text()).render(
                relay_runtime_root=str(directory), relay_config_root=str(directory),
                relay_reviewer_service_name='test.service', relay_reviewer_user=pwd.getpwuid(os.geteuid()).pw_name,
                relay_reviewer_group=pwd.getpwuid(os.geteuid()).pw_name)
        module = types.ModuleType('maintenance_fixture')
        exec(compile(source, 'maintenance_fixture', 'exec'), module.__dict__)
        return module

    @unittest.skipUnless(os.geteuid() == 0, 'root marker ownership contract')
    def test_pause_survives_process_replacement_and_another_operation_cannot_resume(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            module = self.load(directory)
            calls = []
            def request(command):
                calls.append(command)
                return {'pid': 7, 'ready': True, 'writerAccepting': command == 'resume',
                        'resumeMarkerSupported': True}
            with patch.object(module, 'request', request), contextlib.redirect_stdout(io.StringIO()):
                with patch('sys.argv', ['maintenance', 'pause-writer', '--operation', OPERATION]):
                    module.main()
                record = json.loads(module.MARKER.read_bytes())
                self.assertEqual(record, {'schemaVersion': 1, 'command': 'pause-writer', 'operation': OPERATION})
                self.assertEqual(self.load(directory).marker_read(), record)
                with patch('sys.argv', ['maintenance', 'resume', '--operation', '00000000-0000-0000-0000-000000000000']):
                    with self.assertRaisesRegex(RuntimeError, 'OTHER_OPERATION'):
                        module.main()
                self.assertEqual(calls, ['pause-writer'])
                with patch('sys.argv', ['maintenance', 'pause', '--operation', OPERATION]):
                    module.main()
                with patch('sys.argv', ['maintenance', 'pause-writer', '--operation', OPERATION]):
                    module.main()
                self.assertEqual(calls[-1], 'pause')
                with patch('sys.argv', ['maintenance', 'resume', '--operation', OPERATION]):
                    module.main()
                self.assertFalse(module.MARKER.exists())

    @unittest.skipUnless(os.geteuid() == 0, 'root marker ownership contract')
    def test_resume_intent_survives_missing_or_unready_ack_and_is_removed_after_verified_retry(self):
        for incomplete_ack in (False, True):
            with self.subTest(incomplete_ack=incomplete_ack), tempfile.TemporaryDirectory() as temporary:
                module = self.load(Path(temporary))
                module.write_marker(OPERATION, 'pause-writer')
                replacement = {'pid': 8, 'ready': True, 'writerAccepting': True, 'resumeMarkerSupported': True}

                def missing_ack(command):
                    if command == 'status':
                        return {**replacement, 'pid': 7, 'writerAccepting': False}
                    self.assertEqual(command, 'resume')
                    self.assertEqual(module.marker_read()['command'], 'resume')
                    if incomplete_ack:
                        return {**replacement, 'writerAccepting': False}
                    raise OSError('Reviewer process replaced before acknowledgement')

                with patch.object(module, 'request', missing_ack), patch('sys.argv',
                        ['maintenance', 'resume', '--operation', OPERATION]):
                    with self.assertRaisesRegex((OSError, RuntimeError), 'replaced|RESUME_UNPROVEN'):
                        module.main()
                self.assertEqual(module.marker_read(), {'schemaVersion': 1, 'operation': OPERATION, 'command': 'resume'})

                calls = []
                def acknowledge(command):
                    self.assertEqual(module.marker_read()['operation'], OPERATION)
                    calls.append(command)
                    return replacement

                with patch.object(module, 'request', acknowledge), contextlib.redirect_stdout(io.StringIO()) as output:
                    with patch('sys.argv', ['maintenance', 'resume', '--operation', '00000000-0000-0000-0000-000000000000']):
                        with self.assertRaisesRegex(RuntimeError, 'OTHER_OPERATION'):
                            module.main()
                    with patch('sys.argv', ['maintenance', 'resume', '--operation', OPERATION]):
                        module.main()
                self.assertEqual(calls, ['status', 'resume'])
                self.assertIsNone(module.marker_read())
                self.assertIsNone(json.loads(output.getvalue())['operation'])

    @unittest.skipUnless(os.geteuid() == 0, 'root marker ownership contract')
    def test_older_process_keeps_original_pause_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            module = self.load(Path(temporary))
            module.write_marker(OPERATION, 'pause')
            original = module.MARKER.read_bytes()
            with patch.object(module, 'request', return_value={'pid': 7, 'ready': True}) as request:
                with patch('sys.argv', ['maintenance', 'resume', '--operation', OPERATION]):
                    with self.assertRaisesRegex(RuntimeError, 'DURABLE_RESUME_UNSUPPORTED'):
                        module.main()
            request.assert_called_once_with('status')
            self.assertEqual(module.MARKER.read_bytes(), original)

    def test_real_local_socket_requires_the_exact_systemd_process(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / 'reviewer-proof').mkdir()
            module = self.load(directory)
            with socket.socket(socket.AF_UNIX) as server:
                server.bind(module.CONTROL)
                server.listen(1)
                def reply():
                    client, _ = server.accept()
                    with client:
                        self.assertEqual(client.recv(32), b'status\n')
                        client.sendall(json.dumps({'schemaVersion': 1, 'pid': os.getpid()}).encode())
                thread = threading.Thread(target=reply)
                thread.start()
                result = types.SimpleNamespace(stdout=str(os.getpid()))
                with patch.object(module.subprocess, 'run', return_value=result):
                    self.assertEqual(module.request('status')['pid'], os.getpid())
                thread.join(timeout=3)
                self.assertFalse(thread.is_alive())
            with socket.socket(socket.AF_UNIX) as server:
                Path(module.CONTROL).unlink()
                server.bind(module.CONTROL)
                server.listen(1)
                other_pid = str(os.getpid() + 1)
                with patch.object(module.subprocess, 'run', return_value=types.SimpleNamespace(stdout=other_pid)):
                    with self.assertRaisesRegex(RuntimeError, 'PROCESS_UNPROVEN'):
                        module.request('status')

    def test_listener_unit_is_not_an_independent_activation_authority(self):
        unit = Environment(undefined=StrictUndefined).from_string(
            (TEMPLATES / 'reviewer-mcp.socket.j2').read_text()).render(
                relay_reviewer_bind_address='127.0.0.1', relay_reviewer_bind_port=8787,
                relay_reviewer_service_name='reviewer-mcp.service', relay_install_root='/opt/fixture')
        self.assertIn('ListenStream=127.0.0.1:8787', unit)
        self.assertIn('Accept=no', unit)
        self.assertIn('FlushPending=no', unit)
        self.assertNotIn('WantedBy=', unit)

    def test_socket_restart_refuses_unsupported_active_legacy_before_mutation(self):
        for supported in (False, True):
            with self.subTest(supported=supported), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                marker = directory / 'activated'
                marker.write_text('authorized')
                marker.chmod(0o600)
                calls = directory / 'calls'
                systemctl = directory / 'systemctl'
                systemctl.write_text('#!/usr/bin/python3\nimport sys\n'
                    f'with open({str(calls)!r}, "a") as stream: stream.write(" ".join(sys.argv[1:])+"\\n")\n'
                    'raise SystemExit(3 if sys.argv[1:] == ["is-active", "runner.service"] else 0)\n')
                systemctl.chmod(0o755)
                maintenance = directory / 'relay-reviewer-maintenance'
                maintenance.write_text('#!/usr/bin/python3\nimport json,sys\n'
                    f'with open({str(calls)!r}, "a") as stream: stream.write("maintenance "+" ".join(sys.argv[1:])+"\\n")\n'
                    f'if not {supported!r}: raise SystemExit(1)\n'
                    'print(json.dumps({"pid":33}))\n')
                maintenance.chmod(0o755)
                state = directory / 'operation-state'
                state.write_text('#!/bin/sh\necho phase=apply\nexit 10\n')
                state.chmod(0o755)
                (directory / 'reviewer-mcp.json').write_text(json.dumps({'artifact': {'commit': 'a' * 40}}))
                source = Environment(undefined=StrictUndefined).from_string(
                    (TEMPLATES / 'relay-reviewer-operation-restart.j2').read_text()).render(
                        relay_reviewer_service_name='reviewer.service', relay_runner_service_name='runner.service',
                        relay_reviewer_activation_marker=str(marker), relay_reviewer_recovery_off_marker=str(directory / 'off'),
                        relay_production_operation_state_path=str(state), relay_production_operation_lock_path=str(directory / 'operation.lock'),
                        relay_production_operation_record_path=str(directory / 'record.json'), relay_install_root=str(directory),
                        relay_config_root=str(directory), relay_reviewer_bind_address='127.0.0.1', relay_reviewer_bind_port=8787,
                        relay_reviewer_socket_activation=True)
                source = source.replace('/bin/systemctl', str(systemctl))
                source = source.replace('"$marker_owner" == root', '"$marker_owner" == ' + pwd.getpwuid(os.geteuid()).pw_name)
                helper = directory / 'restart'
                helper.write_text(source)
                result = subprocess.run(['/bin/bash', str(helper)], capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0 if supported else 50, result.stdout + result.stderr)
                trace = calls.read_text()
                if supported:
                    self.assertIn('--no-block try-restart reviewer.service', trace)
                    self.assertIn('--previous-pid 33', trace)
                    self.assertIn('maintenance ready --expected-commit ' + 'a' * 40, trace)
                else:
                    self.assertIn('REVIEWER_LEGACY_DRAIN_UNPROVEN', result.stderr)
                    self.assertNotIn('try-restart', trace)
                    self.assertNotIn('start ', trace)


if __name__ == '__main__':
    unittest.main()
