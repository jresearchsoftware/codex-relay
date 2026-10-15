"""Execute public deploy control flow with bounded mocked external capabilities."""
import json
import unittest

import test_deployment as deployment
import config
import workflow_projection


class PoolPreflightCliTests(unittest.TestCase):
    invoke = deployment.EntrypointTests.invoke

    @classmethod
    def setUpClass(cls):
        deployment.EntrypointTests.setUpClass.__func__(cls)
        cls.failure = cls.base / 'pool-preflight-failure'
        cls.preflights = cls.base / 'pool-preflight-calls'
        # Only external qualification/transport is replaced. The actual CLI
        # still resolves source, locks, lifecycle, backend and handoff ordering.
        (cls.product / 'deploy/managed_pool_transport.py').write_text(
            'from pathlib import Path\nfrom managed_pool import PoolError\n'
            'def preflight_pool(*args, **kwargs):\n'
            f'    Path({str(cls.preflights)!r}).write_text("inspected")\n'
            f'    marker = Path({str(cls.failure)!r})\n'
            '    if marker.exists(): raise PoolError(marker.read_text())\n'
            '    return "MANAGED_POOL_PREFLIGHT=PASS"\n'
            'def reconcile_pool(*args, **kwargs):\n'
            '    return \'MANAGED_POOL_RESULT={"capacity":2}\'\n')
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
        for path in [self.failure, self.preflights, self.base / 'admission-calls', self.capture]:
            path.unlink(missing_ok=True)

    def test_invalid_group_auth_or_serial_state_stops_before_lifecycle_and_backend(self):
        for code in ['MANAGED_POOL_GROUP_ELIGIBLE_REPOSITORIES_UNPROVEN',
                     'MANAGED_POOL_GROUP_UNTRUSTED_WORKFLOW_REF',
                     'MANAGED_POOL_API_UNPROVEN_INSPECT_BEFORE_RETRY',
                     'MANAGED_POOL_OWNER_APP_KEY_UNAVAILABLE_ON_OWNER_EXECUTION_HOST',
                     'MANAGED_POOL_SERIAL_TRANSITION_REQUIRED',
                     'MANAGED_POOL_HOST_GUARD_LOST_INSPECT_BEFORE_RETRY']:
            for phase in ['apply', 'upgrade']:
                with self.subTest(code=code, phase=phase):
                    self.failure.write_text(code)
                    extra = ['--authorize-upgrade'] if phase == 'upgrade' else []
                    result = self.invoke('--phase', phase, '--resolved-revision', self.revision, *extra)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(code, result.stderr)
                    self.assertTrue(self.preflights.exists())
                    self.assertFalse(self.capture.exists())
                    self.assertFalse((self.base / 'admission-calls').exists())

    def test_successful_preflight_allows_the_existing_owner_apply_path(self):
        result = self.invoke('--phase', 'apply', '--resolved-revision', self.revision)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.preflights.exists())
        self.assertTrue(self.capture.exists())
        self.assertIn('MANAGED_POOL_RESULT=', result.stdout)
