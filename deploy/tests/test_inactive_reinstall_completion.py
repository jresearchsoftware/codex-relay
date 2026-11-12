"""Expert pool materialization must finish before explicit activation/Apply."""
import json
import sys
import unittest

import test_bootstrap_cli as bootstrap
import test_deployment as deployment
import config
import workflow_projection


@unittest.skipUnless(sys.platform == 'linux', 'Linux public deployment entrypoint')
class InactivePoolInstallTests(unittest.TestCase):
    invoke = deployment.EntrypointTests.invoke
    setUp = bootstrap.BootstrapCliTests.setUp
    tearDownClass = classmethod(deployment.EntrypointTests.tearDownClass.__func__)

    @classmethod
    def setUpClass(cls):
        bootstrap.BootstrapCliTests.setUpClass.__func__(cls)
        cls.reconciliations = cls.base / 'pool-reconciliations'
        (cls.product / 'deploy/managed_pool_transport.py').write_text(
            'from pathlib import Path\n'
            'def preflight_pool(*args, **kwargs): return "MANAGED_POOL_PREFLIGHT=PASS"\n'
            'def reconcile_pool(*args, **kwargs):\n'
            f'    Path({str(cls.reconciliations)!r}).write_text("called")\n'
            '    return \'MANAGED_POOL_RESULT={"capacity":6}\'\n')
        cls.revision = deployment.commit(cls.product)
        value = json.loads(cls.config.read_text())
        value['consumer']['generalRunnerPool'] = {'desiredCapacity': 6}
        value['environment']['generalRunner'].update(scope='organization', group='shared-general',
            poolApp={'appId': '101', 'installationId': '201', 'privateKeyFile': '/synthetic/owner.pem'})
        cls.config.write_text(json.dumps(config.loads(json.dumps(value), cls.product)))
        workflow_projection.project(json.loads(cls.config.read_text()), cls.revision, cls.product, cls.consumer)
        cls.consumer_revision = deployment.commit(cls.consumer)
        ssh = cls.bin / 'ssh'
        code = ssh.read_text()
        code = code.replace("guard = Path(",
            "if sys.argv[-1].startswith('/opt/') and '/relay-admission' in sys.argv[-1]:\n    print('{}');sys.exit(0)\nguard = Path(", 1)
        code = code.replace("'\\n    result = decommission(value[\"config\"], value[\"revision\"], current_report)\\n'",
                            "'\\n    result = decommission(value[\"config\"], value[\"revision\"], current_report, operation_id=value[\"operation_id\"], admission_probe=pool_admission_probe)\\n'")
        code = code.replace("'\\n    result = complete(value[\"config\"], value[\"revision\"])\\n'",
                            "'\\n    result = complete(value[\"config\"], value[\"revision\"], operation_id=value[\"operation_id\"], admission_probe=pool_admission_probe)\\n'")
        ssh.write_text(code)

    def test_expert_materialization_defers_pool_but_apply_still_reconciles(self):
        for phase in ['bootstrap', 'reinstall']:
            with self.subTest(phase=phase):
                self.setUp()
                self.reconciliations.unlink(missing_ok=True)
                if phase == 'reinstall':
                    self.existing.touch()
                result = self.invoke('--phase', phase, '--authorize-' + phase,
                                     '--resolved-revision', self.revision)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('post_check=clean;activation=owner-required', result.stdout)
                self.assertIn('RELAY_DEPLOYMENT_PENDING=ACTIVATION_AND_POOL_RECONCILIATION_REQUIRED', result.stdout)
                self.assertFalse(self.reconciliations.exists(), 'Inactive installation must not register/start pool runners')
                self.assertEqual([json.loads(row)['phase'] for row in self.history.read_text().splitlines()],
                                 ['apply', 'post-check'])
                applied = self.invoke('--phase', 'apply', '--resolved-revision', self.revision)
                self.assertEqual(applied.returncode, 0, applied.stderr)
                self.assertTrue(self.reconciliations.exists())
                self.assertIn('MANAGED_POOL_RESULT=', applied.stdout)
                self.assertNotIn('ACTIVATION_AND_POOL_RECONCILIATION_REQUIRED', applied.stdout)
