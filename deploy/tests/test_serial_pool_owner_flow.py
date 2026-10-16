"""Public owner CLI ordering across saved SERIAL transition phases.

Only external pool/SSH/backend transports are substituted. The real deploy CLI
resolves source/configuration/projection, locks and same-operation completion.
These are control-flow regressions, not installed migration qualification.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import config
import test_deployment as deployment
import workflow_projection

OPERATION = '12345678-1234-1234-1234-123456789abc'


class SerialPoolOwnerFlowTests(unittest.TestCase):
    invoke = deployment.EntrypointTests.invoke

    @classmethod
    def setUpClass(cls):
        deployment.EntrypointTests.setUpClass.__func__(cls)
        cls.flow = cls.base / 'serial-flow.jsonl'
        cls.phase_file = cls.base / 'serial-phase'
        cls.operation_file = cls.base / 'serial-operation'
        cls.failure = cls.base / 'serial-failure'
        cls.gate_file = cls.base / 'serial-gate.json'
        common = ('import json\nfrom pathlib import Path\n'
                  f'flow=Path({str(cls.flow)!r}); failure=Path({str(cls.failure)!r})\n'
                  'def emit(event, **values):\n'
                  '    with flow.open("a") as stream: stream.write(json.dumps({"event":event, **values})+"\\n")\n'
                  'def fails(stage): return failure.exists() and failure.read_text()==stage\n')
        (cls.product / 'deploy/managed_pool_transport.py').write_text(common +
            'from types import SimpleNamespace\nfrom managed_pool import PoolError\n'
            f'operation_file=Path({str(cls.operation_file)!r}); phase_file=Path({str(cls.phase_file)!r})\n'
            'def preflight_pool(*args, **kwargs):\n'
            '    emit("preflight"); return SimpleNamespace(serial_transition=True, operation_id=operation_file.read_text() or None)\n'
            'def transition_pool(target,key,config,revision,operation_id,*args,action="begin",**kwargs):\n'
            '    emit(action, operation=operation_id, target=revision)\n'
            '    if fails(action): raise PoolError("MANAGED_POOL_FIXTURE_TRANSITION_FAILURE")\n'
            '    if action=="finish": phase_file.write_text("retired")\n'
            '    return {"phase":phase_file.read_text() if action=="begin" else "retired", "operationId":operation_id,"target":revision}\n'
            'def reconcile_pool(*args,**kwargs):\n'
            '    emit("reconcile")\n'
            '    if fails("reconcile"): raise PoolError("MANAGED_POOL_FIXTURE_RECONCILE_FAILURE")\n'
            '    return \'MANAGED_POOL_RESULT={"capacity":2}\'\n')
        backend = cls.bin / 'ansible-playbook'
        original = backend.read_text()
        # Retain the existing backend's complete native proof surface while
        # recording inventory and injecting failures at real CLI boundaries.
        hook = ('emit("backend-check" if "--check" in a else "backend-apply", '
                'operation=v.get("relay_admission_operation_id"), transition=v.get("relay_serial_pool_transition"), '
                'managed=v.get("relay_upgrade_lifecycle_managed"))\n'
                'if fails("post-check" if "--check" in a else "apply"): sys.exit(4)\n')
        original = original.replace('import json,sys\n', 'import json,sys\n' + common)
        original = original.replace("Path(" + repr(str(cls.capture)) + ").write_text(json.dumps(v))\n",
                                    "Path(" + repr(str(cls.capture)) + ").write_text(json.dumps(v))\n" + hook)
        original = original.replace("if v.get('relay_upgrade_lifecycle_managed'): print('RELAY_UPGRADE_ACTIVATION_VALIDATED='+head)",
                                    "if v.get('relay_upgrade_lifecycle_managed') and not fails('missing-activation'): print('RELAY_UPGRADE_ACTIVATION_VALIDATED='+head)")
        backend.write_text(original)
        (cls.bin / 'ssh').write_text('#!/usr/bin/python3\nimport sys\n' + common +
            f'gate_path=Path({str(cls.gate_file)!r})\n'
            'command=sys.argv[-1]\n'
            'if "DEPLOYMENT_LOCK_READY" in command:\n'
            '    print("DEPLOYMENT_LOCK_READY",flush=True);sys.stdin.read()\n'
            'elif "--hold" in command:\n'
            '    print("BOOTSTRAP_GUARD_READY",flush=True);sys.stdin.read()\n'
            'elif "/relay-admission" in command:\n'
            '    words=command.split(); action=words[1]; gate=json.loads(gate_path.read_text())\n'
            '    operation=words[words.index("--operation")+1] if "--operation" in words else None\n'
            '    phase=words[words.index("--phase")+1] if "--phase" in words else None\n'
            '    emit("gate-"+action, operation=operation, phase=phase)\n'
            '    if action=="phase": gate["phase"]=phase\n'
            '    elif action=="resume":\n'
            '        if fails("resume"): sys.exit(4)\n'
            '        gate["phase"]="open"\n'
            '    gate_path.write_text(json.dumps(gate)); print(json.dumps(gate))\n')
        cls.revision = deployment.commit(cls.product)
        value = json.loads(cls.config.read_text())
        value['consumer']['generalRunnerPool'] = {'desiredCapacity': 2}
        value['environment']['instance'] = {'reviewerPort': 18787, 'publicationEnabled': False}
        value['environment']['generalRunner'].update(scope='organization', group='shared-general',
            poolApp={'appId': '101', 'installationId': '201', 'privateKeyFile': '/synthetic/owner.pem'})
        value = config.loads(json.dumps(value), cls.product)
        cls.config.write_text(json.dumps(value))
        workflow_projection.project(value, cls.revision, cls.product, cls.consumer)
        cls.consumer_revision = deployment.commit(cls.consumer)

    @classmethod
    def tearDownClass(cls):
        deployment.EntrypointTests.tearDownClass.__func__(cls)

    def setUp(self):
        self.flow.unlink(missing_ok=True)
        self.failure.unlink(missing_ok=True)
        self.phase_file.write_text('installed')
        self.operation_file.write_text(OPERATION)
        self.gate_file.write_text(json.dumps({'phase': 'recovery-required', 'operationId': OPERATION,
                                              'target': self.revision, 'active': [], 'unknown': []}))

    def apply(self, *extra):
        return self.invoke('--phase', 'apply', '--resolved-revision', self.revision, *extra)

    def events(self):
        return [json.loads(row) for row in self.flow.read_text().splitlines()]

    def names(self):
        return [row['event'] for row in self.events()]

    def assertClosed(self):
        self.assertNotEqual(json.loads(self.gate_file.read_text())['phase'], 'open')
        self.assertNotIn('gate-resume', self.names())

    def test_installed_forward_reuses_saved_uuid_and_checks_before_original_registration_retirement(self):
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stderr)
        names = self.names()
        self.assertLess(names.index('begin'), names.index('reconcile'))
        self.assertLess(names.index('reconcile'), names.index('backend-check'))
        self.assertLess(names.index('backend-check'), names.index('finish'))
        self.assertLess(names.index('finish'), names.index('gate-resume'))
        self.assertNotIn('backend-apply', names)
        self.assertEqual([row['operation'] for row in self.events() if row.get('operation')],
                         [OPERATION] * len([row for row in self.events() if row.get('operation')]))
        backend = next(row for row in self.events() if row['event'] == 'backend-check')
        self.assertEqual(backend['operation'], OPERATION)
        self.assertFalse(backend['transition'])
        self.assertFalse(backend['managed'])
        self.assertEqual(json.loads(self.gate_file.read_text())['phase'], 'open')

    def test_retired_completion_checks_and_resumes_same_operation_without_reapply_reconcile_or_second_retirement(self):
        self.phase_file.write_text('retired')
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stderr)
        names = self.names()
        self.assertNotIn('backend-apply', names)
        self.assertNotIn('reconcile', names)
        self.assertNotIn('finish', names)
        self.assertLess(names.index('backend-check'), names.index('gate-phase'))
        self.assertLess(names.index('gate-phase'), names.index('gate-resume'))
        self.assertTrue(all(row.get('operation') in [None, OPERATION] for row in self.events()))
        self.assertEqual(json.loads(self.gate_file.read_text())['phase'], 'open')

    def test_reapply_after_final_acknowledgement_retains_uuid_and_does_not_repeat_retirement_or_resume(self):
        first = self.apply()
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self.apply()
        self.assertEqual(second.returncode, 0, second.stderr)
        names = self.names()
        self.assertEqual(names.count('begin'), 2)
        self.assertEqual(names.count('reconcile'), 1)
        self.assertEqual(names.count('finish'), 1)
        self.assertEqual(names.count('gate-resume'), 1)
        self.assertEqual(names.count('backend-check'), 2)
        self.assertNotIn('backend-apply', names)
        self.assertTrue(all(row.get('operation') in [None, OPERATION] for row in self.events()))

    def test_stopped_initial_install_proves_activation_before_retirement_and_resume(self):
        self.phase_file.write_text('stopped')
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stderr)
        names = self.names()
        self.assertLess(names.index('backend-apply'), names.index('reconcile'))
        self.assertLess(names.index('reconcile'), names.index('finish'))
        self.assertLess(names.index('finish'), names.index('gate-resume'))
        backend = next(row for row in self.events() if row['event'] == 'backend-apply')
        self.assertEqual(backend['operation'], OPERATION)
        self.assertTrue(backend['transition'])
        self.assertTrue(backend['managed'])

    def test_upgrade_preflight_retains_reserved_target_order_without_changing_canonical_snapshot(self):
        import yaml
        from ansible.parsing.dataloader import DataLoader
        from ansible.template import Templar
        from serial_pool_transition import encoded
        from test_upgrade import upgrade

        self.phase_file.write_text('stopped')
        result = self.invoke('--phase', 'upgrade', '--authorize-upgrade',
                             '--resolved-revision', self.revision)
        self.assertEqual(result.returncode, 0, result.stderr)
        values = json.loads(self.capture.read_text())
        target = config.load(self.config, self.product)
        canonical = json.dumps(target, sort_keys=True, separators=(',', ':'), ensure_ascii=False) + '\n'
        ordered = encoded(target)
        self.assertNotEqual(ordered, canonical.rstrip('\n').encode())
        self.assertEqual(values['relay_installed_deployment_config'], canonical)
        self.assertEqual(values['relay_installed_deployment_config_sha256'],
                         hashlib.sha256(canonical.encode()).hexdigest())
        task = yaml.safe_load((self.product / 'deploy/ansible/tasks/upgrade-preflight.yml').read_text())[0]
        stdin = Templar(loader=DataLoader(), variables=values).template(task['ansible.builtin.command']['stdin'])
        self.assertIsInstance(stdin, str)

        with tempfile.TemporaryDirectory(prefix='serial-upgrade-', dir=self.base) as temporary:
            boundary = Path(temporary)
            install, config_root, claim = boundary / 'install', boundary / 'config', boundary / 'claims'
            old_revision = 'a' * 40
            release = install / 'releases' / old_revision
            source = release / 'reviewed-source'
            source.mkdir(parents=True)
            config_root.mkdir()
            claim.mkdir()
            (install / 'current').symlink_to(release)
            original = copy.deepcopy(target)
            original['source']['revision'] = old_revision
            original['consumer'].pop('generalRunnerPool')
            original['consumer'].pop('executionSlots')
            original['environment']['generalRunner'].pop('poolApp')
            original['environment']['generalRunner']['name'] = 'legacy-general'
            snapshot = encoded(original) + b'\n'
            consumer = encoded(original['consumer']) + b'\n'
            receipt = encoded({'operationId': OPERATION,
                'namespace': original['environment']['namespace'],
                'repository': original['consumer']['repository'],
                'original': {'revision': old_revision,
                    'configSha256': hashlib.sha256(snapshot).hexdigest(),
                    'consumerSha256': hashlib.sha256(consumer).hexdigest()}}) + b'\n'
            evidence = {
                release / 'deployment-config.json': snapshot,
                config_root / 'consumer.json': consumer,
                source / '.relay-source.json': encoded({'revision': old_revision, 'tree': 'b' * 40}),
                release / 'artifact-manifest.json': encoded({'commit': old_revision,
                    'installedRevision': old_revision, 'resolvedRevision': old_revision,
                    'gitTree': 'b' * 40, 'deploymentConfigSha256': hashlib.sha256(snapshot).hexdigest()}),
                config_root / 'serial-pool-compat-v1.json': receipt,
                claim / 'serial-pool-transition-v1.json': encoded({'operationId': OPERATION,
                    'phase': 'stopped', 'targetRevision': self.revision,
                    'receiptSha256': hashlib.sha256(receipt).hexdigest(),
                    'plan': {'targetConfigSha256': hashlib.sha256(ordered).hexdigest()}}),
            }
            for path, raw in evidence.items():
                path.write_bytes(raw)
            for path in [boundary, *boundary.rglob('*')]:
                if not path.is_symlink():
                    path.chmod(0o700 if path.is_dir() else 0o600)
            # Rebase only filesystem access to the synthetic claim store. The
            # complete original/prospective owner objects and hashes stay intact.
            configured_claim = original['consumer']['paths']['claimRoot']
            def fixture_path(value):
                return claim if str(value) == configured_claim else Path(value)
            with patch.object(upgrade, 'Path', fixture_path):
                def verify(raw):
                    return upgrade.verify(install, config_root, json.loads(raw),
                                          owner_uid=os.getuid(), boundary=boundary)
                with self.assertRaisesRegex(ValueError, 'OWNER_INTENT_CHANGED'):
                    verify(canonical)
                self.assertEqual(verify(stdin), old_revision)
                self.assertEqual(values['relay_serial_pool_target_config'].encode(), ordered)
                tampered = json.loads(stdin)
                tampered['consumer']['generalRunnerPool']['desiredCapacity'] += 1
                with self.assertRaisesRegex(ValueError, 'OWNER_INTENT_CHANGED'):
                    verify(json.dumps(tampered))
            self.assertEqual({path: path.read_bytes() for path in evidence}, evidence)
        ordinary = {**values, 'relay_serial_pool_transition': False}
        self.assertEqual(Templar(loader=DataLoader(), variables=ordinary).template(
            task['ansible.builtin.command']['stdin']), canonical)

    def test_missing_initial_activation_proof_preserves_original_registration_and_closed_gate(self):
        self.phase_file.write_text('stopped')
        self.failure.write_text('missing-activation')
        result = self.apply()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('upgrade-same-operation-activation-proof', result.stderr)
        self.assertNotIn('finish', self.names())
        self.assertClosed()

    def test_forward_reconcile_or_readonly_check_failure_never_retires_or_resumes(self):
        for failure in ['reconcile', 'post-check']:
            with self.subTest(failure=failure):
                self.setUp()
                self.failure.write_text(failure)
                result = self.apply()
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('finish', self.names())
                self.assertClosed()

    def test_retirement_or_final_resume_failure_keeps_same_operation_closed(self):
        for failure in ['finish', 'resume']:
            with self.subTest(failure=failure):
                self.setUp()
                self.failure.write_text(failure)
                result = self.apply()
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(json.loads(self.gate_file.read_text())['phase'], 'recovery-required')
                self.assertEqual([row['operation'] for row in self.events() if row['event'] == 'begin'], [OPERATION])

    def test_conflicting_explicit_recovery_uuid_stops_before_begin_backend_or_retirement(self):
        other = '12345678-1234-1234-1234-123456789abd'
        result = self.invoke('--phase', 'upgrade', '--authorize-upgrade', '--resolved-revision', self.revision,
                             '--authorize-lifecycle-recovery', '--lifecycle-recovery-operation', other)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('SERIAL_TRANSITION_OPERATION_CONFLICT', result.stderr)
        self.assertEqual(self.names(), ['preflight'])
        self.assertClosed()
