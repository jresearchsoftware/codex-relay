"""Run the protected coordinator over synthetic source and trusted capabilities."""
from contextlib import nullcontext, redirect_stdout
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
sys.path.insert(0, str(Path(__file__).parent))
import owner_lifecycle as owner
import workflow_projection as projection
from test_lifecycle import Gate, HEAD, OLD, OPERATION


class OwnerLifecycleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='relay-owner-fixture-', dir='/tmp')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = json.loads((ROOT / 'deploy/example.json').read_text())
        self.config['source']['repository'] = 'https://github.com/example-org/sample-project.git'
        self.config['environment']['localApply'] = {'source': 'installed'}
        self.values = {'relay_install_root': str(self.root / 'install'), 'relay_namespace': 'fixture',
                       'relay_production_local_apply_stage_root': str(self.root)}
        self.source = self.root / 'accepted-source'
        shutil.copytree(ROOT / 'deploy/workflows', self.source / 'deploy/workflows')
        projection.project(self.config, HEAD, self.source, self.source)
        self.gate = Gate()
        self.primitive = []
        self.sources = []
        self.remote_head = HEAD
        self.primitive_failure = False
        self.omit = None
        self.install_failure = False
        self.source_changes = None
        self.proof_calls = []
        self.public_reads = []
        self.root_reads = []

        def installed(root, expected):
            self.root_reads.append((Path(root), expected))
            return self.config, {}, {}

        def public_main(repository):
            self.public_reads.append(repository)
            return self.remote_head

        def source(directory, repository, revision):
            self.sources.append((repository, revision))
            shutil.copytree(self.source, directory)
            if self.source_changes:
                self.source_changes(directory)
            return directory

        def proof(config, revision):
            self.proof_calls.append(revision)
            if self.install_failure:
                raise ValueError('protected-installation-mismatch')
            return True

        def backend(argv, **kwargs):
            if argv[0].endswith('/relay-admission'):
                value = self.gate(argv[1], *argv[2:])
                return SimpleNamespace(stdout=json.dumps(value), stderr='', returncode=0)
            self.assertEqual(argv[0], '/usr/bin/python3')
            self.primitive.append((argv, kwargs))
            # Main moves after selection; no later observation may retarget.
            self.remote_head = 'd' * 40
            target = argv[argv.index('--resolved-revision') + 1]
            evidence = [f'RELAY_LIFECYCLE_VERIFIED={target}', f'installed_revision={target}',
                f'RELAY_WORKFLOW_PROJECTION=PASS;revision={target};consumer={HEAD}']
            if self.omit is not None:
                evidence.pop(self.omit)
            return SimpleNamespace(stdout='\n'.join(evidence) + '\n', returncode=1 if self.primitive_failure else 0)

        for target, value in [('ROOT', self.source), ('installed_config', installed),
                              ('compile_inputs', lambda config: self.values),
                              ('acquire', lambda path: nullcontext(77)), ('public_main', public_main),
                              ('acquire_source', source), ('installed_proof', proof)]:
            patched = patch.object(owner, target, value)
            patched.start()
            self.addCleanup(patched.stop)
        patched = patch.object(owner.os, 'geteuid', return_value=0)
        patched.start()
        self.addCleanup(patched.stop)
        patched = patch.object(owner.subprocess, 'run', side_effect=backend)
        patched.start()
        self.addCleanup(patched.stop)
        def spawn(argv, **kwargs):
            result = backend(argv, **kwargs)
            return SimpleNamespace(stdout=io.StringIO(result.stdout),
                wait=lambda **options: result.returncode, poll=lambda: result.returncode,
                terminate=Mock())
        patched = patch.object(owner.subprocess, 'Popen', side_effect=spawn)
        patched.start()
        self.addCleanup(patched.stop)

    def run_owner(self, action='apply', installed=OLD, consumer=HEAD):
        with redirect_stdout(io.StringIO()):
            owner.run(f'{action}:{installed}:{consumer}')

    def test_one_public_main_binding_and_one_existing_upgrade_survive_later_main_movement(self):
        self.run_owner()
        self.assertEqual(self.public_reads, ['example-org/sample-project'])
        self.assertEqual(self.sources, [('example-org/sample-project', HEAD)])
        self.assertEqual(len(self.primitive), 1)
        argv, options = self.primitive[0]
        self.assertEqual(argv[argv.index('--phase') + 1], 'upgrade')
        self.assertEqual(argv[argv.index('--resolved-revision') + 1], HEAD)
        self.assertEqual(argv[argv.index('--requested-revision') + 1], HEAD)
        self.assertIn('--authorize-upgrade', argv)
        self.assertIn('--local-lifecycle', argv)
        self.assertEqual(argv[argv.index('--lifecycle-operation') + 1], self.gate.operation)
        self.assertEqual(options['pass_fds'], (77,))
        self.assertEqual(self.proof_calls, [HEAD])
        self.assertEqual(self.gate.phase, 'open')
        self.assertEqual(len(self.root_reads), 2)

    def test_current_accepted_target_reconciles_once_without_upgrade_or_registration(self):
        self.run_owner(installed=HEAD)
        self.assertEqual(len(self.primitive), 1)
        argv, _ = self.primitive[0]
        self.assertEqual(argv[argv.index('--phase') + 1], 'apply')
        self.assertNotIn('--authorize-upgrade', argv)
        for forbidden in ['runner-register', '--runner-registration-token', '--authorize-activate']:
            self.assertNotIn(forbidden, argv)
        self.assertEqual(self.proof_calls, [HEAD])

    def test_projection_mismatch_stops_before_quiesce_or_any_install_mutation(self):
        def changed(directory):
            with (directory / 'deploy/workflows/production.yml.in').open('a') as stream:
                stream.write('# target workflow differs from reviewed consumer bytes\n')
        self.source_changes = changed
        with self.assertRaisesRegex(ValueError, 'WORKFLOW_REVIEW_REQUIRED'):
            self.run_owner()
        self.assertEqual(self.gate.phase, 'open')
        self.assertEqual(self.gate.calls, [])
        self.assertEqual(self.primitive, [])
        self.assertEqual(self.proof_calls, [])

    def test_malformed_input_and_nonroot_call_never_read_source_or_quiesce(self):
        for request in ['apply', f'upgrade:{OLD}:{HEAD}', f'apply:main:{HEAD}',
                        f'apply:{OLD}:{HEAD}:extra', f'apply:{OLD}:{HEAD};id']:
            with self.subTest(request=request), self.assertRaisesRegex(ValueError, 'argument-contract'):
                owner.run(request)
        with patch.object(owner.os, 'geteuid', return_value=1000):
            with self.assertRaisesRegex(ValueError, 'root-required'):
                owner.run(f'apply:{OLD}:{HEAD}')
        self.assertEqual(self.root_reads, [])
        self.assertEqual(self.public_reads, [])
        self.assertEqual(self.sources, [])
        self.assertEqual(self.gate.calls, [])

    def test_stale_dispatch_stops_before_source_or_quiesce(self):
        with self.assertRaisesRegex(ValueError, 'consumer-dispatch-stale'):
            self.run_owner(consumer=OLD)
        self.assertEqual(self.sources, [])
        self.assertEqual(self.gate.calls, [])

    def test_stop_retains_operation_without_source_checkout_or_apply(self):
        self.run_owner(action='stop')
        self.assertEqual(self.gate.phase, 'drained')
        self.assertEqual(self.gate.target, OLD)
        self.assertEqual(self.sources, [])
        self.assertEqual(self.primitive, [])
        self.assertNotIn('resume', [call[0] for call in self.gate.calls])

    def test_uncertain_recovery_is_not_graceful_resume(self):
        for phase in ['applying', 'recovery-required', 'verified']:
            with self.subTest(phase=phase):
                self.gate = Gate(phase, target=OLD)
                with self.assertRaisesRegex(ValueError, 'resume-recovery-requires-diagnosis'):
                    self.run_owner(action='resume')
                self.assertEqual(self.gate.phase, phase)
                self.assertEqual(self.primitive, [])
                self.assertEqual(self.sources, [])

    def test_graceful_resume_reuses_retained_operation_and_revalidates_without_install_apply(self):
        self.gate = Gate('drained', target=HEAD)
        self.run_owner(action='resume', installed=HEAD)
        self.assertEqual(len(self.primitive), 1)
        argv, options = self.primitive[0]
        self.assertEqual(argv[argv.index('--phase') + 1], 'post-check')
        self.assertNotIn('--authorize-upgrade', argv)
        self.assertEqual(argv[argv.index('--lifecycle-operation') + 1], OPERATION)
        self.assertEqual(options['pass_fds'], (77,))
        self.assertEqual(self.proof_calls, [HEAD])
        self.assertEqual(len(self.root_reads), 2)
        self.assertEqual(self.gate.phase, 'open')
        self.assertNotIn('quiesce', [call[0] for call in self.gate.calls])

    def test_graceful_resume_cannot_reopen_changed_installed_target(self):
        self.gate = Gate('drained', target=HEAD)
        with self.assertRaisesRegex(ValueError, 'resume-installed-target-mismatch'):
            self.run_owner(action='resume', installed=OLD)
        self.assertEqual(self.gate.phase, 'drained')
        self.assertEqual(self.sources, [])
        self.assertEqual(self.primitive, [])

    def test_graceful_resume_proof_failure_keeps_admission_closed(self):
        self.gate = Gate('drained', target=HEAD)
        self.install_failure = True
        with self.assertRaisesRegex(ValueError, 'protected-installation-mismatch'):
            self.run_owner(action='resume', installed=HEAD)
        self.assertEqual(self.gate.phase, 'recovery-required')
        self.assertNotIn('resume', [call[0] for call in self.gate.calls])

    def test_primitive_activation_projection_or_installed_proof_failure_keeps_closed(self):
        for failure in ['primitive', 'activation', 'installed-revision', 'projection', 'installed-proof']:
            with self.subTest(failure=failure):
                self.gate = Gate()
                self.remote_head = HEAD
                self.primitive_failure = failure == 'primitive'
                self.omit = {'activation': 0, 'installed-revision': 1, 'projection': 2}.get(failure)
                self.install_failure = failure == 'installed-proof'
                with self.assertRaises(ValueError):
                    self.run_owner()
                self.assertEqual(self.gate.phase, 'recovery-required')
                self.assertNotIn('resume', [call[0] for call in self.gate.calls])


class PublicMainTests(unittest.TestCase):
    def response(self, payload, status=200):
        connection = Mock()
        connection.getresponse.return_value = SimpleNamespace(status=status,
            read=lambda limit: payload[:limit])
        return connection

    def test_anonymous_exact_public_main_read_has_no_redirect_or_token_surface(self):
        body = json.dumps({'ref': 'refs/heads/main', 'object': {'type': 'commit', 'sha': HEAD}}).encode()
        connection = self.response(body)
        with patch.object(owner.http.client, 'HTTPSConnection', return_value=connection) as transport:
            self.assertEqual(owner.public_main('example-org/sample-project'), HEAD)
        transport.assert_called_once()
        self.assertEqual(transport.call_args.args, ('api.github.com',))
        connection.request.assert_called_once()
        self.assertEqual(connection.request.call_args.args,
                         ('GET', '/repos/example-org/sample-project/git/ref/heads/main'))
        self.assertNotIn('Authorization', connection.request.call_args.kwargs['headers'])
        connection.close.assert_called_once()

    def test_unavailable_redirect_oversized_or_noncommit_main_does_not_select_target(self):
        valid = {'ref': 'refs/heads/main', 'object': {'type': 'commit', 'sha': HEAD}}
        cases = [(valid, 302), (valid, 404),
                 ({**valid, 'ref': 'refs/heads/candidate'}, 200),
                 ({**valid, 'object': {'type': 'tag', 'sha': HEAD}}, 200),
                 ({**valid, 'object': {'type': 'commit', 'sha': 'main'}}, 200),
                 (b'x' * 8193, 200)]
        for payload, status in cases:
            with self.subTest(payload=payload if isinstance(payload, dict) else 'oversized', status=status):
                raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
                connection = self.response(raw, status)
                with patch.object(owner.http.client, 'HTTPSConnection', return_value=connection):
                    with self.assertRaises(ValueError):
                        owner.public_main('example-org/sample-project')
                connection.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
