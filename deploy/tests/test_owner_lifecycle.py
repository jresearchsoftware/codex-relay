"""Run the protected coordinator over synthetic source and trusted capabilities."""
from contextlib import contextmanager, redirect_stderr, redirect_stdout
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
import lifecycle_process as children
import workflow_projection as projection
from config import loads
from test_lifecycle import Gate, HEAD, OLD, OPERATION


REAL_RUN = subprocess.run
REAL_POPEN = subprocess.Popen


def copy_projection_source(destination):
    shutil.copytree(ROOT / 'deploy/workflows', destination / 'deploy/workflows')
    for name in ['deploy/config.py', 'deploy/workflow_projection.py',
                 'consumer/consumer-config.mjs', 'contracts/src/execution-defaults.mjs',
                 'reviewer/src/executable-cr-v2.json']:
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, path)


class OwnerLifecycleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='relay-owner-fixture-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = json.loads((ROOT / 'deploy/example.json').read_text())
        self.config['source']['repository'] = 'https://github.com/example-org/sample-project.git'
        self.config['environment']['localApply'] = {'source': 'installed'}
        self.values = {'relay_install_root': str(self.root / 'install'), 'relay_namespace': 'fixture',
                       'relay_production_local_apply_stage_root': str(self.root)}
        self.source = self.root / 'accepted-source'
        copy_projection_source(self.source)
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
        self.preflights = []
        self.projection_preflights = []
        self.preflight_failure = None
        self.preflight_output = 'MANAGED_POOL_PREFLIGHT=PASS\n'
        self.active_locks = []
        self.events = []

        @contextmanager
        def lock(path):
            self.active_locks.append(path)
            try:
                yield 77
            finally:
                self.active_locks.remove(path)

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
            if argv[0] == 'node':
                return REAL_RUN(argv, **kwargs)
            if argv[0].endswith('/relay-admission'):
                self.events.append('gate-' + argv[1])
                value = self.gate(argv[1], *argv[2:])
                return SimpleNamespace(stdout=json.dumps(value), stderr='', returncode=0)
            self.assertEqual(argv[0], '/usr/bin/python3')
            if argv[1:4] == ['-I', '-c', owner.PROJECTION_PREFLIGHT_SCRIPT]:
                self.events.append('projection-preflight')
                self.projection_preflights.append((argv, kwargs, self.active_locks[:]))
                return REAL_RUN(argv, **kwargs)
            if argv[1:3] == ['-I', '-c']:
                self.events.append('pool-preflight')
                self.preflights.append((argv, kwargs, self.active_locks[:]))
                return SimpleNamespace(stdout=self.preflight_output,
                    stderr=(self.preflight_failure or '') + '\n',
                    returncode=1 if self.preflight_failure else 0)
            self.events.append('apply')
            self.assertFalse(any('/codex-relay-pool-' in path for path in self.active_locks))
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
                              ('acquire', lock), ('public_main', public_main),
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
            if argv[0] == 'node' or argv[1:4] == ['-I', '-c', owner.PROJECTION_PREFLIGHT_SCRIPT]:
                return REAL_POPEN(argv, **kwargs)
            result = backend(argv, **kwargs)
            return SimpleNamespace(stdout=io.StringIO(result.stdout),
                wait=lambda **options: result.returncode, poll=lambda: result.returncode,
                terminate=Mock())
        patched = patch.object(owner.subprocess, 'Popen', side_effect=spawn)
        patched.start()
        self.addCleanup(patched.stop)
        def child(argv, **options):
            proofs = options.pop('stdout_proofs', ())
            for key in ['phase', 'dependency', 'forward', 'interval']:
                options.pop(key, None)
            options.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            result = owner.subprocess.run(argv, **options)
            if result.returncode:
                raise subprocess.CalledProcessError(result.returncode, argv,
                    output=result.stdout, stderr=getattr(result, 'stderr', ''))
            result.stdout_proofs = frozenset(set(result.stdout.splitlines()) & set(proofs))
            return result
        patched = patch.object(owner, 'run_child', side_effect=child)
        patched.start()
        self.addCleanup(patched.stop)

    def run_owner(self, action='apply', installed=OLD, consumer=HEAD):
        with redirect_stdout(io.StringIO()):
            owner.run(f'{action}:{installed}:{consumer}')

    def configure_pool(self):
        self.config['consumer']['generalRunnerPool'] = {'desiredCapacity': 2}
        self.config['environment']['instance'] = {'reviewerPort': 18787, 'publicationEnabled': False}
        self.config['environment']['generalRunner'].update(scope='organization', group='sample-general',
            poolApp={'appId': '101', 'installationId': '201', 'privateKeyFile': '/owner-private/app.pem'})
        self.config = loads(json.dumps(self.config, sort_keys=True), self.source)
        projection.project(self.config, HEAD, self.source, self.source)

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

    def test_pool_preflight_uses_frozen_source_and_private_stdin_before_admission_under_both_locks(self):
        self.configure_pool()
        self.run_owner()
        self.assertEqual(len(self.preflights), 1)
        argv, options, locks = self.preflights[0]
        self.assertEqual(argv[:4], ['/usr/bin/python3', '-I', '-c', owner.POOL_PREFLIGHT_SCRIPT])
        self.assertTrue(argv[4].endswith('/product/deploy'))
        self.assertEqual(json.loads(options['input']), self.config)
        self.assertEqual(options['env'], owner.clean_environment())
        self.assertEqual(options['stderr'], subprocess.PIPE)
        self.assertFalse(options['check'])
        self.assertEqual(locks, ['/var/lib/fixture-deployment.lock',
            '/var/lib/codex-relay-pool-' + self.config['environment']['generalRunner']['name'] + '-deployment.lock'])
        self.assertEqual(self.events[:2], ['projection-preflight', 'pool-preflight'])
        self.assertLess(self.events.index('pool-preflight'), self.events.index('gate-quiesce'))
        self.assertEqual(self.gate.phase, 'open')
        self.assertEqual(self.active_locks, [])

    def test_invalid_pool_acl_key_or_api_access_never_mutates_admission_or_launches_apply(self):
        self.configure_pool()
        for code in ['MANAGED_POOL_GROUP_ELIGIBLE_REPOSITORIES_UNPROVEN',
                     'MANAGED_POOL_GROUP_UNTRUSTED_WORKFLOW_REF',
                     'MANAGED_POOL_OWNER_APP_KEY_UNAVAILABLE_ON_OWNER_EXECUTION_HOST',
                     'MANAGED_POOL_API_UNPROVEN_INSPECT_BEFORE_RETRY']:
            with self.subTest(code=code):
                self.preflight_failure = code
                with self.assertRaisesRegex(ValueError, '^' + code + '$'):
                    self.run_owner()
                self.assertEqual(self.gate.phase, 'open')
                self.assertEqual(self.gate.calls, [])
                self.assertEqual(self.primitive, [])
                self.assertEqual(self.proof_calls, [])
                self.assertEqual(self.active_locks, [])

    def test_unproven_pool_preflight_result_or_private_error_is_fixed_and_keeps_gate_open(self):
        self.configure_pool()
        for failure, output, expected in [
            ('synthetic private diagnostic', '', 'MANAGED_POOL_OWNER_PREFLIGHT_UNPROVEN'),
            (None, 'unexpected metadata\n', 'MANAGED_POOL_OWNER_PREFLIGHT_RESULT_UNPROVEN'),
        ]:
            with self.subTest(expected=expected):
                self.preflight_failure, self.preflight_output = failure, output
                with self.assertRaisesRegex(ValueError, '^' + expected + '$'):
                    self.run_owner()
                self.assertEqual(self.gate.calls, [])
                self.assertEqual(self.primitive, [])
                self.assertEqual(self.active_locks, [])

    def test_managed_apply_preflights_while_stop_and_resume_keep_existing_path(self):
        self.run_owner()
        self.assertEqual(len(self.preflights), 1)
        self.preflights.clear()
        self.remote_head = HEAD
        self.configure_pool()
        self.run_owner(action='stop')
        self.assertEqual(self.preflights, [])
        self.gate = Gate('drained', target=HEAD)
        self.run_owner(action='resume', installed=HEAD)
        self.assertEqual(self.preflights, [])

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

    def test_target_renderer_rejects_old_concurrency_bytes_before_quiesce(self):
        self.configure_pool()
        render = projection.render
        subject = "${{ github.event_name == 'workflow_dispatch' && format('issue-{0}', inputs.task) || github.event_name == 'issues' && format('issue-{0}', github.event.issue.number) || format('pull-{0}', github.event.pull_request.number) }}"
        group = self.config['environment']['namespace'] + '-control-'
        current = json.dumps(group + '${{ github.run_id }}').encode()
        previous = json.dumps(group + subject).encode()

        def installed_render(*args, **kwargs):
            # The 75f9 renderer used the Task/PR subject even when passed f323
            # templates. Reproduce those actual previous bytes and manifest.
            return {path: raw.replace(current, previous)
                    for path, raw in render(*args, **kwargs).items()}

        with patch.object(projection, 'render', side_effect=installed_render):
            projection.project(self.config, HEAD, self.source, self.source)
            projection.verify(self.config, HEAD, self.source, self.source)
        with self.assertRaisesRegex(ValueError, 'WORKFLOW_REVIEW_REQUIRED'):
            self.run_owner()
        self.assertEqual(self.gate.calls, [])
        self.assertEqual(self.primitive, [])
        self.assertEqual(self.preflights, [])

    def test_target_projection_acceptance_ignores_installed_renderer_and_uses_private_stdin(self):
        self.configure_pool()
        with patch.object(projection, 'verify', side_effect=AssertionError('installed verifier must not run')):
            self.run_owner()
        argv, options, locks = self.projection_preflights[0]
        self.assertEqual(argv[:4], ['/usr/bin/python3', '-I', '-c', owner.PROJECTION_PREFLIGHT_SCRIPT])
        self.assertTrue(argv[4].endswith('/product'))
        self.assertEqual(argv[5], HEAD)
        self.assertEqual(argv[6], argv[4])
        self.assertEqual(json.loads(options['input']), self.config)
        self.assertEqual(options['env'], owner.clean_environment())
        self.assertEqual(locks, ['/var/lib/fixture-deployment.lock'])
        self.assertLess(self.events.index('projection-preflight'), self.events.index('gate-quiesce'))
        self.assertEqual(self.gate.phase, 'open')

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

    def real_primitive(self, output, *, stderr='private-backend-evidence', exit_code=0):
        """Keep synthetic admission, but drain one actual deployment child."""
        adapter = owner.run_child.side_effect
        self.child_results = []
        self.child_calls = []
        def child(argv, **options):
            if len(argv) < 2 or not argv[1].endswith('/deploy/relay-deploy.py'):
                return adapter(argv, **options)
            self.child_calls.append(argv)
            # The fixture's synthetic lock FD is not an inherited OS descriptor.
            options.pop('pass_fds')
            program = ('import sys;sys.stdout.write(' + repr(output) + ');'
                       'sys.stderr.write(' + repr(stderr) + ');sys.exit(' + str(exit_code) + ')')
            # Large output travels on stdin, rather than exceeding argv limits.
            with patch.object(owner.subprocess, 'Popen', REAL_POPEN):
                result = children.run([sys.executable, '-c', 'import sys;exec(sys.stdin.read())'],
                                      input=program.encode(), **options)
            self.child_results.append(result)
            return result
        return patch.object(owner, 'run_child', side_effect=child)

    def long_apply_output(self, projection=None, verified=None, installed=None):
        projection = (f'RELAY_WORKFLOW_PROJECTION=PASS;revision={HEAD};consumer={HEAD}'
                      if projection is None else projection)
        verified = f'RELAY_LIFECYCLE_VERIFIED={HEAD}' if verified is None else verified
        installed = f'installed_revision={HEAD}' if installed is None else installed
        return 'early-private-output\n' + 'x' * 200000 + '\n' + projection + '\n' + 'y' * 200000 + '\n' + installed + '\n' + verified + '\n'

    def test_actual_long_successful_apply_keeps_middle_proof_and_reopens_only_after_installed_check(self):
        output = self.long_apply_output()
        with self.real_primitive(output), redirect_stdout(io.StringIO()) as public:
            owner.run(f'apply:{OLD}:{HEAD}')
        result, = self.child_results
        self.assertGreater(result.capture_bytes['stdout'], children.CAPTURE_LIMIT)
        self.assertNotIn('RELAY_WORKFLOW_PROJECTION=PASS', result.stdout)
        self.assertIn(children.OMITTED.decode(), result.stdout)
        self.assertLessEqual(len(result.stdout), children.CAPTURE_LIMIT + len(children.OMITTED))
        self.assertEqual(result.stderr, 'private-backend-evidence')
        self.assertEqual(len(result.stdout_proofs), 3)
        self.assertEqual(len(self.child_calls), 1)
        self.assertEqual(self.proof_calls, [HEAD])
        self.assertEqual(self.gate.phase, 'open')
        self.assertIn('RELAY_OWNER_LIFECYCLE_RESULT=OPEN', public.getvalue())
        self.assertNotIn('private-', public.getvalue())
        self.assertNotIn('RELAY_WORKFLOW_PROJECTION=PASS', public.getvalue())

    def test_actual_child_invalid_same_operation_proofs_keep_admission_closed_and_original_evidence(self):
        projection = f'RELAY_WORKFLOW_PROJECTION=PASS;revision={HEAD};consumer={HEAD}'
        cases = [
            {'projection': ''},
            {'projection': projection.replace('PASS', 'FAIL')},
            {'projection': projection.replace('revision=' + HEAD, 'revision=' + OLD)},
            {'projection': projection.replace('consumer=' + HEAD, 'consumer=' + OLD)},
            {'projection': 'prefix-' + projection},
            {'projection': projection + '-suffix'},
            {'verified': ''},
            {'verified': f'RELAY_LIFECYCLE_VERIFIED={OLD}'},
            {'installed': ''},
            {'installed': f'installed_revision={OLD}'},
        ]
        for changed in cases:
            with self.subTest(changed=changed):
                self.gate = Gate()
                self.remote_head = HEAD
                output = self.long_apply_output(**changed)
                with self.real_primitive(output), redirect_stdout(io.StringIO()) as public:
                    with self.assertRaisesRegex(ValueError, '^lifecycle-same-operation-proof-missing$') as stopped:
                        owner.run(f'apply:{OLD}:{HEAD}')
                self.assertEqual(len(self.child_calls), 1)
                self.assertEqual(self.proof_calls, [])
                self.assertEqual(self.gate.phase, 'recovery-required')
                self.assertNotIn('resume', [call[0] for call in self.gate.calls])
                self.assertNotIn('RELAY_OWNER_LIFECYCLE_RESULT=OPEN', public.getvalue())
                self.assertEqual(stopped.exception.stderr, 'private-backend-evidence')
                self.assertTrue(stopped.exception.stdout.startswith('early-private-output'))
                self.assertEqual(stopped.exception.capture_bytes['stdout'], len(output.encode()))
                self.assertEqual(stopped.exception.observation['childExit'], 0)
                self.assertTrue(stopped.exception.observation['missingStdoutProofs'])

    def test_actual_nonzero_child_with_all_proofs_still_keeps_admission_closed(self):
        with self.real_primitive(self.long_apply_output(), exit_code=7), redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, '^lifecycle-public-primitive-failed$') as stopped:
                owner.run(f'apply:{OLD}:{HEAD}')
        self.assertEqual(len(self.child_calls), 1)
        self.assertEqual(self.gate.phase, 'recovery-required')
        self.assertNotIn('resume', [call[0] for call in self.gate.calls])
        self.assertEqual(self.proof_calls, [])
        self.assertEqual(stopped.exception.__cause__.returncode, 7)
        self.assertEqual(stopped.exception.__cause__.stderr, 'private-backend-evidence')

    def test_actual_missing_proof_reaches_existing_private_causal_reporter(self):
        output = self.long_apply_output(projection='')
        with self.real_primitive(output, stderr='password=fixture-private-secret'), redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, '^lifecycle-same-operation-proof-missing$') as stopped:
                owner.run(f'apply:{OLD}:{HEAD}')
        log = self.root / 'causal.log'
        log.touch(mode=0o600)
        # The coordinator fixture models root; this readback exercises the
        # reporter's actual unprivileged private-log route, without root proof.
        with patch.object(owner.os, 'geteuid', return_value=owner.os.getuid()), redirect_stderr(io.StringIO()):
            receipt = owner.report_failure(stopped.exception, 'owner-lifecycle', private_log=log)
        self.assertEqual(receipt['status'], 'stored')
        record = json.loads(log.read_text().split('RELAY_DEPLOYMENT_CAUSAL_EVIDENCE=', 1)[1])
        cause = record['causes'][0]
        self.assertEqual(cause['message'], 'lifecycle-same-operation-proof-missing')
        self.assertEqual(cause['observation']['childExit'], 0)
        self.assertEqual(cause['observation']['missingStdoutProofs'],
            [f'RELAY_WORKFLOW_PROJECTION=PASS;revision={HEAD};consumer={HEAD}'])
        self.assertEqual(cause['stdoutBytes'], len(output.encode()))
        self.assertTrue(cause['stdoutTruncated'])
        self.assertEqual(cause['stderrAvailability'], 'redacted')
        self.assertNotIn('fixture-private-secret', log.read_text())


class PublicMainTests(unittest.TestCase):
    def response(self, payload, status=200):
        connection = Mock()
        connection.getresponse.return_value = SimpleNamespace(status=status, getheader=lambda _name: None,
            read=lambda limit: payload[:limit])
        return connection

    def test_anonymous_exact_public_main_read_has_no_redirect_or_token_surface(self):
        body = json.dumps({'ref': 'refs/heads/main', 'object': {'type': 'commit', 'sha': HEAD}}).encode()
        connection = self.response(body)
        with patch.object(owner.git_intent.http.client, 'HTTPSConnection', return_value=connection) as transport:
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
                with patch.object(owner.git_intent.http.client, 'HTTPSConnection', return_value=connection):
                    with self.assertRaises(ValueError):
                        owner.public_main('example-org/sample-project')
                connection.close.assert_called_once()


class OwnerPoolPreflightProcessTests(unittest.TestCase):
    def test_selected_source_preflight_process_preserves_private_stdin_and_fixed_errors(self):
        with tempfile.TemporaryDirectory(prefix='owner-preflight-process-') as temporary:
            source = Path(temporary)
            module = source / 'managed_pool_transport.py'
            for error, expected in [
                (None, None),
                ('MANAGED_POOL_GROUP_UNTRUSTED_WORKFLOW_REF', 'MANAGED_POOL_GROUP_UNTRUSTED_WORKFLOW_REF'),
                ('synthetic private diagnostic', 'MANAGED_POOL_OWNER_PREFLIGHT_UNPROVEN'),
            ]:
                with self.subTest(error=error):
                    module.write_text(
                        'def preflight_pool(target, key, config, *, local):\n'
                        '    assert target is None and key is None and local is True\n'
                        '    assert config == {"binding": "selected-source-private-input"}\n'
                        + (f'    raise ValueError({error!r})\n' if error else '    return "PASS"\n'))
                    result = subprocess.run([sys.executable, '-I', '-c', owner.POOL_PREFLIGHT_SCRIPT, str(source)],
                        input=json.dumps({'binding': 'selected-source-private-input'}),
                        env=owner.clean_environment(), text=True, capture_output=True, timeout=10)
                    if expected is None:
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(result.stdout, 'MANAGED_POOL_PREFLIGHT=PASS\n')
                        self.assertEqual(result.stderr, '')
                    else:
                        self.assertNotEqual(result.returncode, 0)
                        self.assertEqual(result.stdout, '')
                        self.assertTrue(result.stderr.endswith(expected + '\n'), result.stderr)
                    self.assertNotIn('selected-source-private-input', result.stdout + result.stderr)


class OwnerProjectionPreflightProcessTests(unittest.TestCase):
    def test_malformed_oversized_or_private_target_errors_are_fixed(self):
        with tempfile.TemporaryDirectory(prefix='owner-projection-process-') as temporary:
            source = Path(temporary)
            copy_projection_source(source)
            valid = (ROOT / 'deploy/example.json').read_text()
            for raw, private_error in [('{', False), ('x' * 262145, False), (valid, True)]:
                with self.subTest(oversized=len(raw) > 262144, private_error=private_error):
                    if private_error:
                        (source / 'deploy/workflow_projection.py').write_text(
                            'raise ValueError("synthetic private target diagnostic")\n')
                    result = subprocess.run([sys.executable, '-I', '-c', owner.PROJECTION_PREFLIGHT_SCRIPT,
                        str(source), HEAD, str(source)], input=raw,
                        env=owner.clean_environment(), text=True, capture_output=True, timeout=10)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(result.stdout, '')
                    self.assertTrue(result.stderr.endswith('WORKFLOW_REVIEW_REQUIRED\n'), result.stderr)
                    self.assertNotIn('synthetic private target diagnostic', result.stderr)


if __name__ == '__main__':
    unittest.main()
