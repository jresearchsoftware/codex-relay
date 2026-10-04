"""Public clean-install transitions with real Git/projection and synthetic SSH."""
import json
import shutil
import sys
import tempfile
from pathlib import Path
import unittest

import test_deployment as deployment_tests


@unittest.skipUnless(sys.platform == 'linux', 'Linux public deployment entrypoint')
class BootstrapCliTests(unittest.TestCase):
    invoke = deployment_tests.EntrypointTests.invoke

    @classmethod
    def setUpClass(cls):
        deployment_tests.EntrypointTests.setUpClass.__func__(cls)
        cls.history = cls.base / 'backend-history'
        cls.inventory_history = cls.base / 'inventory-history'
        cls.blocked = cls.base / 'inventory-blocked'
        cls.post_failure = cls.base / 'post-check-failure'
        cls.apply_failure = cls.base / 'apply-failure'
        cls.existing = cls.base / 'existing-installation'
        cls.guard_live = cls.base / 'active-host-guard'
        cls.events = cls.base / 'events'
        ssh = cls.bin / 'ssh'
        ssh.write_text('#!/usr/bin/python3\n' + f'''
import json, os, sys
from pathlib import Path
Path({str(cls.calls)!r}).write_text('strict-preflight')
guard = Path({str(cls.guard_live)!r})
def event(name):
    identity = guard.read_text() if guard.exists() else None
    Path({str(cls.events)!r}).open('a').write(json.dumps({{'event': name, 'guard': identity}}) + '\\n')
if 'DEPLOYMENT_LOCK_READY' in sys.argv[-1]:
    assert not guard.exists()
    guard.write_text(str(os.getpid()))
    event('guard-acquired')
    print('DEPLOYMENT_LOCK_READY', flush=True)
    sys.stdin.read()
    event('guard-released')
    guard.unlink()
elif '\\n    result = decommission(value["config"], value["revision"], current_report)\\n' in sys.argv[-1]:
    request = json.loads(sys.stdin.read())
    assert guard.exists(), 'decommission requires same live host mutex'
    event('decommission')
    print(json.dumps({{'state': 'DECOMMISSIONED', 'sourceRevision': 'b' * 40,
                      'targetRevision': request['revision'], 'journalSha256': 'd' * 64,
                      'recoveryPath': '/var/lib/' + request['config']['environment']['namespace']
                                      + '-clean-reinstall.json'}}))
elif '\\n    result = complete(value["config"], value["revision"])\\n' in sys.argv[-1]:
    request = json.loads(sys.stdin.read())
    assert guard.exists(), 'completion requires same live host mutex'
    event('complete')
    print(json.dumps({{'state': 'COMPLETE', 'installedRevision': request['revision'],
                      'archive': '/opt/.' + request['config']['environment']['namespace']
                                 + '-retired-' + 'b' * 40 + '-' + request['revision']}}))
elif 'result = recover(' in sys.argv[-1]:
    request = json.loads(sys.stdin.read())
    assert guard.exists(), 'recovery requires live host mutex'
    assert 'candidate_admission_probe' in sys.argv[-1] and 'prCreationResolved' in sys.argv[-1]
    event('recover')
    print(json.dumps({{'state': 'DISPOSITIONED', 'sourceRevision': 'a' * 40,
                      'targetRevision': request['revision'],
                      'archive': '/opt/.' + request['config']['environment']['namespace']
                                 + '-retired-' + 'a' * 40 + '-' + request['revision'],
                      'journalSha256': 'd' * 64, 'operationSha256': 'e' * 64,
                      'units': {{}}, 'activationMarkers': [], 'runners': []}}))
elif 'def remote_inventory(' in sys.argv[-1]:
    request = json.loads(sys.stdin.read())
    event('inventory')
    Path({str(cls.inventory_history)!r}).open('a').write('inventory\\n')
    blockers = ['runner-production-ambiguous'] if Path({str(cls.blocked)!r}).exists() else []
    existing = Path({str(cls.existing)!r}).exists()
    print(json.dumps({{'schemaVersion': 1, 'readOnly': True, 'mutationAuthorized': False,
        'status': 'blocked' if blockers else 'observed',
        'installed': {{'status': 'present', 'revision': 'b' * 40}} if existing else {{'status': 'missing'}},
        'configuration': {{'status': 'equivalent', 'consumer': 'equivalent', 'deployment': 'equivalent'}}
                         if existing else {{'status': 'missing', 'consumer': 'missing', 'deployment': 'unavailable'}},
        'runners': {{name: {{'status': 'reusable' if existing else 'missing', 'freshTokenRequired': not existing}}
                    for name in ['production', 'general']}},
        'protectedState': [], 'blockers': blockers,
        'ownerAdmin': [{{'name': name, 'status': 'unavailable', 'next': 'owner verification'}}
                       for name in ['github-app-installations-and-permissions',
                                    'github-runner-registration-and-policy', 'dns-and-ingress']]}}))
''')
        backend = cls.bin / 'ansible-playbook'
        backend.write_text(backend.read_text() + f'''
Path({str(cls.history)!r}).open('a').write(json.dumps({{
    'phase': v['relay_production_operation_phase'], 'check': '--check' in a,
    'activation': v['relay_service_activation_authorized'],
    'registration': v['relay_runner_registration_authorized'],
    'journal': v.get('relay_clean_reinstall_journal_sha256', '')}}) + '\\n')
guard = Path({str(cls.guard_live)!r})
assert guard.exists(), 'backend execution requires same live host mutex'
Path({str(cls.events)!r}).open('a').write(json.dumps({{
    'event': v['relay_production_operation_phase'], 'guard': guard.read_text()}}) + '\\n')
if '--check' not in a and Path({str(cls.apply_failure)!r}).exists():
    sys.exit(4)
if '--check' in a and Path({str(cls.post_failure)!r}).exists():
    print('192.0.2.10 : ok=1 changed=1 unreachable=0 failed=0')
''')

    @classmethod
    def tearDownClass(cls):
        deployment_tests.EntrypointTests.tearDownClass.__func__(cls)

    def setUp(self):
        for path in [self.history, self.inventory_history, self.blocked, self.post_failure,
                     self.apply_failure, self.existing, self.guard_live, self.events, self.calls]:
            path.unlink(missing_ok=True)

    def bootstrap(self, *arguments):
        return self.invoke('--phase', 'bootstrap', '--resolved-revision', self.revision, *arguments)

    def reinstall(self, *arguments):
        self.existing.touch()
        return self.invoke('--phase', 'reinstall', '--authorize-reinstall',
                           '--resolved-revision', self.revision, *arguments)

    def observed_events(self):
        return [json.loads(line) for line in self.events.read_text().splitlines()]

    def fresh_consumer(self):
        root = Path(tempfile.mkdtemp(prefix='fresh-consumer-', dir=self.base))
        config = root / 'relay.json'
        config.write_bytes(self.config.read_bytes())
        (root / 'README').write_text('Consumer authority; no generated installation files.\n')
        deployment_tests.commit(root)
        return root, config

    def proposal(self, result):
        line = next(value for value in result.stdout.splitlines()
                    if value.startswith('RELAY_BOOTSTRAP_PROJECTION='))
        return json.loads(line.split('=', 1)[1])

    def test_recovery_explicitly_binds_old_target_without_backend_or_retarget(self):
        old = 'c' * 40
        result = self.invoke('--phase', 'reinstall-recover', '--authorize-reinstall-recovery',
                             '--reinstall-recovery-target', old, '--resolved-revision', self.revision)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(next(line.split('=', 1)[1] for line in result.stdout.splitlines()
                                if line.startswith('RELAY_REINSTALL_RECOVERY=')))
        self.assertEqual(report['targetRevision'], old)
        self.assertIn('controller_revision=' + self.revision, result.stdout)
        self.assertFalse(self.history.exists())
        self.assertEqual([json.loads(line)['event'] for line in self.events.read_text().splitlines()],
                         ['guard-acquired', 'recover', 'guard-released'])

    def test_recovery_requires_authorization_and_exact_retained_target(self):
        for flags in [[], ['--authorize-reinstall-recovery'],
                      ['--reinstall-recovery-target', 'c' * 40],
                      ['--authorize-reinstall-recovery', '--reinstall-recovery-target', 'main']]:
            result = self.invoke('--phase', 'reinstall-recover', '--resolved-revision', self.revision, *flags)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('explicit-reinstall-recovery', result.stderr)
        for phase in ['inventory', 'apply']:
            result = self.invoke('--phase', phase, '--authorize-reinstall-recovery',
                                 '--reinstall-recovery-target', 'c' * 40)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('explicit-reinstall-recovery', result.stderr)
        self.assertFalse(self.events.exists())

    def test_fresh_config_derives_review_artifacts_without_host_mutation(self):
        root, config = self.fresh_consumer()
        before = deployment_tests.git(root, 'rev-parse', 'HEAD')
        result = self.bootstrap('--config', str(config), '--authorize-bootstrap')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('RELAY_DEPLOYMENT_PENDING=WORKFLOW_REVIEW_REQUIRED;target_unchanged=true', result.stdout)
        self.assertNotIn('RELAY_DEPLOYMENT_RESULT=PASS', result.stdout)
        proposed = self.proposal(result)
        self.assertEqual(proposed['state'], 'workflow-review-required')
        self.assertEqual(proposed['revision'], self.revision)
        for path in proposed['files']:
            self.assertTrue((Path(proposed['directory']) / path).is_file())
            self.assertFalse((root / path).exists())
        self.assertEqual(deployment_tests.git(root, 'rev-parse', 'HEAD'), before)
        self.assertFalse(deployment_tests.git(root, 'status', '--porcelain'))
        self.assertFalse(self.capture.exists())
        self.assertFalse(self.history.exists())
        self.assertEqual(self.inventory_history.read_text(), 'inventory\n')

    def test_reviewed_derived_artifacts_resume_install_and_clean_post_check(self):
        root, config = self.fresh_consumer()
        first = self.bootstrap('--config', str(config), '--authorize-bootstrap')
        self.assertEqual(first.returncode, 0, first.stderr)
        proposal = self.proposal(first)
        for path in proposal['files']:
            destination = root / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(Path(proposal['directory']) / path, destination)
        consumer_revision = deployment_tests.commit(root)
        resumed = self.bootstrap('--config', str(config), '--authorize-bootstrap')
        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        self.assertIn('consumer_revision=' + consumer_revision, resumed.stdout)
        self.assertIn('RELAY_BOOTSTRAP_RESULT=PASS;phase=bootstrap;installed=' + self.revision
                      + ';post_check=clean;activation=owner-required', resumed.stdout)
        self.assertEqual([json.loads(line) for line in self.history.read_text().splitlines()], [
            {'phase': 'apply', 'check': False, 'activation': False, 'registration': False, 'journal': ''},
            {'phase': 'post-check', 'check': True, 'activation': False, 'registration': False, 'journal': ''},
        ])
        self.assertEqual(self.inventory_history.read_text(), 'inventory\ninventory\ninventory\n')

    def test_changed_durable_config_derives_distinct_immutable_review_directory(self):
        root, config = self.fresh_consumer()
        first = self.bootstrap('--config', str(config))
        self.assertEqual(first.returncode, 0, first.stderr)
        before = self.proposal(first)
        original = {path: (Path(before['directory']) / path).read_bytes() for path in before['files']}
        value = json.loads(config.read_text())
        value['consumer']['baseBranch'] = 'stable/next'
        config.write_text(json.dumps(value))
        deployment_tests.commit(root)
        second = self.bootstrap('--config', str(config))
        self.assertEqual(second.returncode, 0, second.stderr)
        after = self.proposal(second)
        self.assertNotEqual(after['directory'], before['directory'])
        self.assertEqual(original, {path: (Path(before['directory']) / path).read_bytes()
                                    for path in before['files']})
        self.assertFalse(self.capture.exists())
        self.assertFalse(self.history.exists())

    def test_reviewed_consumer_drift_blocks_install_without_overwrite(self):
        root, config = self.fresh_consumer()
        first = self.bootstrap('--config', str(config))
        self.assertEqual(first.returncode, 0, first.stderr)
        proposal = self.proposal(first)
        for path in proposal['files']:
            destination = root / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(Path(proposal['directory']) / path, destination)
        workflow = root / next(path for path in proposal['files'] if path.endswith('.yml'))
        drifted = workflow.read_bytes() + b'# owner change requiring reconciliation\n'
        workflow.write_bytes(drifted)
        deployment_tests.commit(root)
        result = self.bootstrap('--config', str(config), '--authorize-bootstrap')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('workflow-drift', result.stderr)
        self.assertEqual(workflow.read_bytes(), drifted)
        self.assertFalse(self.capture.exists())
        self.assertFalse(self.history.exists())

    def test_ignored_untracked_projection_is_not_a_reviewed_consumer_revision(self):
        root, config = self.fresh_consumer()
        (root / '.gitignore').write_text('/.github/\n')
        deployment_tests.commit(root)
        first = self.bootstrap('--config', str(config))
        self.assertEqual(first.returncode, 0, first.stderr)
        proposal = self.proposal(first)
        for path in proposal['files']:
            destination = root / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(Path(proposal['directory']) / path, destination)
        self.assertFalse(deployment_tests.git(root, 'status', '--porcelain'))
        result = self.bootstrap('--config', str(config), '--authorize-bootstrap')
        self.assertFalse(self.capture.exists(), 'ignored local files do not prove consumer publication')
        self.assertFalse(self.history.exists())
        self.assertNotIn('RELAY_BOOTSTRAP_RESULT=PASS', result.stdout)
        self.assertNotIn('RELAY_DEPLOYMENT_RESULT=PASS', result.stdout)

    def test_ready_projection_still_requires_install_authority_and_exact_target(self):
        pending = self.bootstrap()
        self.assertEqual(pending.returncode, 0, pending.stderr)
        self.assertIn('RELAY_DEPLOYMENT_PENDING=INSTALL_AUTHORIZATION_REQUIRED', pending.stdout)
        self.assertFalse(self.capture.exists())
        for arguments in [('--phase', 'bootstrap', '--authorize-bootstrap'),
                          ('--phase', 'bootstrap', '--authorize-bootstrap', '--resolved-revision', 'f' * 40),
                          ('--phase', 'check', '--authorize-bootstrap')]:
            with self.subTest(arguments=arguments):
                self.calls.unlink(missing_ok=True)
                result = self.invoke(*arguments)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.capture.exists())
                self.assertFalse(self.calls.exists(), 'authority/head rejection precedes target contact')

    def test_inventory_blockers_and_post_check_drift_prevent_bootstrap_success(self):
        self.blocked.touch()
        blocked = self.bootstrap('--authorize-bootstrap')
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn('inventory-blocked', blocked.stderr)
        self.assertFalse(self.capture.exists())
        self.blocked.unlink()
        self.post_failure.touch()
        failed = self.bootstrap('--authorize-bootstrap')
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn('bootstrap-post-check-drift', failed.stderr)
        self.assertNotIn('RELAY_BOOTSTRAP_RESULT=PASS', failed.stdout)
        self.assertNotIn('RELAY_DEPLOYMENT_RESULT=PASS', failed.stdout)

    def test_inventory_accepts_private_config_without_consumer_git_checkout(self):
        private = self.base / 'owner-config'
        private.mkdir(exist_ok=True)
        config = private / 'relay.json'
        config.write_bytes(self.config.read_bytes())
        result = self.invoke('--phase', 'inventory', '--resolved-revision', self.revision,
                             '--config', str(config))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('RELAY_DEPLOYMENT_RESULT=PASS;phase=inventory;authority=read-only', result.stdout)
        self.assertFalse(self.capture.exists())
        self.assertFalse(self.history.exists())
        self.assertFalse((private / '.git').exists())

    def test_reinstall_composes_retirement_install_post_check_and_completion_under_one_guard(self):
        result = self.reinstall()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('RELAY_BOOTSTRAP_RESULT=PASS;phase=reinstall;installed=' + self.revision
                      + ';post_check=clean;activation=owner-required', result.stdout)
        self.assertEqual([json.loads(line) for line in self.history.read_text().splitlines()], [
            {'phase': 'apply', 'check': False, 'activation': False, 'registration': False, 'journal': 'd' * 64},
            {'phase': 'post-check', 'check': True, 'activation': False, 'registration': False, 'journal': 'd' * 64},
        ])
        events = self.observed_events()
        self.assertEqual([row['event'] for row in events], [
            'inventory', 'guard-acquired', 'inventory', 'decommission', 'apply', 'post-check',
            'complete', 'guard-released'])
        self.assertIsNone(events[0]['guard'])
        self.assertTrue(events[1]['guard'])
        self.assertEqual({row['guard'] for row in events[1:]}, {events[1]['guard']})
        self.assertFalse(self.guard_live.exists())

    def test_reinstall_without_review_never_decommissions_or_acquires_mutation_guard(self):
        root, config = self.fresh_consumer()
        result = self.reinstall('--config', str(config))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('RELAY_DEPLOYMENT_PENDING=WORKFLOW_REVIEW_REQUIRED', result.stdout)
        self.assertEqual([row['event'] for row in self.observed_events()], ['inventory'])
        self.assertFalse(self.capture.exists())
        self.assertFalse(self.history.exists())
        self.assertFalse(self.guard_live.exists())
        self.assertFalse((root / '.github').exists())

    def test_reinstall_requires_its_own_authority_and_exact_target_before_remote_contact(self):
        for arguments in [('--phase', 'reinstall', '--resolved-revision', self.revision),
                          ('--phase', 'reinstall', '--authorize-reinstall'),
                          ('--phase', 'reinstall', '--authorize-reinstall', '--resolved-revision', 'f' * 40),
                          ('--phase', 'bootstrap', '--authorize-reinstall', '--resolved-revision', self.revision)]:
            with self.subTest(arguments=arguments):
                result = self.invoke(*arguments)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.calls.exists())
                self.assertFalse(self.events.exists())
                self.assertFalse(self.capture.exists())

    def test_failed_reinstall_apply_or_post_check_never_completes_recovery_evidence(self):
        for failure, expected in [(self.apply_failure, 'reinstall-apply-failed'),
                                  (self.post_failure, 'reinstall-post-check-drift')]:
            with self.subTest(failure=expected):
                for path in [self.history, self.events]:
                    path.unlink(missing_ok=True)
                failure.touch()
                result = self.reinstall()
                failure.unlink()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stderr)
                events = [row['event'] for row in self.observed_events()]
                self.assertIn('decommission', events)
                self.assertIn('apply', events)
                self.assertNotIn('complete', events)
                self.assertEqual('post-check' in events, failure == self.post_failure)
                self.assertEqual(events[-1], 'guard-released')
                self.assertFalse(self.guard_live.exists())
                self.assertNotIn('RELAY_BOOTSTRAP_RESULT=PASS', result.stdout)
                self.assertNotIn('RELAY_DEPLOYMENT_RESULT=PASS', result.stdout)


if __name__ == '__main__':
    unittest.main()
