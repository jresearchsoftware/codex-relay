"""Upgrade uses reviewed projection and existing apply/recovery boundaries."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest

import pytest

import test_deployment as deployment_tests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))

spec = importlib.util.spec_from_file_location('verify_upgrade', ROOT / 'deploy/ansible/scripts/verify_upgrade.py')
upgrade = importlib.util.module_from_spec(spec)
spec.loader.exec_module(upgrade)


class UpgradeCliTests(unittest.TestCase):
    invoke = deployment_tests.EntrypointTests.invoke

    @classmethod
    def setUpClass(cls):
        deployment_tests.EntrypointTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        deployment_tests.EntrypointTests.tearDownClass.__func__(cls)

    def upgrade(self, *extra):
        return self.invoke('--phase', 'upgrade', '--authorize-upgrade',
                           '--resolved-revision', self.revision, *extra)

    def test_upgrade_proves_lifecycle_once_without_equivalent_post_check(self):
        result = self.upgrade()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f'RELAY_UPGRADE_RESULT=PASS;installed={self.revision};projection={self.revision};verification=same-operation',
                      result.stdout)
        values = json.loads(self.capture.read_text())
        self.assertEqual(values['relay_production_operation_phase'], 'apply')
        self.assertFalse(values['_test_check_mode'])
        self.assertTrue(values['relay_upgrade_lifecycle_managed'])
        self.assertIn('RELAY_LIFECYCLE_PROGRESS=OPEN', result.stdout)
        self.assertFalse(values['relay_service_activation_authorized'])
        self.assertFalse(values['relay_runner_registration_authorized'])
        self.assertEqual(values['relay_runner_service_state_management'], 'preserve')
        self.assertEqual(json.loads(values['relay_installed_deployment_config']), json.loads(self.config.read_text()))

    def test_upgrade_requires_explicit_authority_and_target(self):
        for arguments in [('--phase', 'upgrade', '--resolved-revision', self.revision),
                          ('--phase', 'upgrade', '--authorize-upgrade'),
                          ('--phase', 'apply', '--authorize-upgrade')]:
            result = self.invoke(*arguments)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(self.capture.exists())

    def test_upgrade_missing_same_operation_activation_proof_stays_closed(self):
        backend = self.bin / 'ansible-playbook'
        original = backend.read_text()
        backend.write_text(original.replace("print('RELAY_UPGRADE_ACTIVATION_VALIDATED='+head)", 'pass'))
        try:
            result = self.upgrade()
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('upgrade-same-operation-activation-proof', result.stderr)
            self.assertNotIn('RELAY_UPGRADE_RESULT=PASS', result.stdout)
            self.assertNotIn('RELAY_LIFECYCLE_PROGRESS=RESUME', result.stdout)
        finally:
            backend.write_text(original)

    def test_upgrade_never_resumes_failed_apply(self):
        backend = self.bin / 'ansible-playbook'
        original = backend.read_text()
        backend.write_text(original + '\nsys.exit(4)\n')
        try:
            result = self.upgrade()
            self.assertNotEqual(result.returncode, 0)
            values = json.loads(self.capture.read_text())
            self.assertEqual(values['relay_production_operation_phase'], 'apply')
            self.assertTrue(values['relay_upgrade_requested'])
            self.assertFalse(values['_test_check_mode'])
            self.assertIn('diagnose-operation-before-retry', result.stderr)
            self.assertNotIn('RELAY_LIFECYCLE_PROGRESS=RESUME', result.stdout)
        finally:
            backend.write_text(original)

    def test_upgrade_cannot_apply_until_trusted_drain_passes(self):
        marker = self.base / 'drain-fail'
        marker.touch()
        try:
            result = self.upgrade()
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(self.capture.exists())
            self.assertNotIn('RELAY_LIFECYCLE_PROGRESS=APPLY', result.stdout)
        finally:
            marker.unlink()

    def test_explicit_supported_recovery_reuses_operation_and_verifies_before_resume(self):
        operation = '12345678-1234-1234-1234-123456789abc'
        calls = self.base / 'admission-calls'
        calls.unlink(missing_ok=True)
        result = self.upgrade('--authorize-lifecycle-recovery', '--lifecycle-recovery-operation', operation)
        self.assertEqual(result.returncode, 0, result.stderr)
        evidence = calls.read_text()
        self.assertNotIn(' quiesce ', evidence)
        self.assertNotIn(' drain ', evidence)
        self.assertIn(' status --operation ' + operation, evidence)
        self.assertIn('--phase verified --revision ' + self.revision, evidence)
        self.assertLess(evidence.index('--phase verified'), evidence.index(' resume '))

    def test_private_durable_config_can_name_separate_consumer_checkout(self):
        private = self.base / 'private-config.json'
        private.write_bytes(self.config.read_bytes())
        result = self.upgrade('--config', str(private), '--consumer-root', str(self.consumer))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('consumer_revision=' + self.consumer_revision, result.stdout)

    def test_workflow_verify_is_local_without_target_connection(self):
        self.calls.unlink(missing_ok=True)
        result = self.invoke('--phase', 'workflow-verify', '--resolved-revision', self.revision)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.calls.exists())
        self.assertFalse(self.capture.exists())

    def test_projection_publishes_reviewable_files_locally_before_apply(self):
        consumer = self.base / 'new-consumer'
        consumer.mkdir()
        (consumer / 'README').write_text('Consumer-owned repository\n')
        deployment_tests.commit(consumer)
        self.calls.unlink(missing_ok=True)
        result = self.invoke('--phase', 'workflow-project', '--authorize-workflow-projection',
                             '--resolved-revision', self.revision, '--consumer-root', str(consumer))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((consumer / '.github/relay-workflows.json').is_file())
        self.assertFalse(self.calls.exists())
        self.assertFalse(self.capture.exists())
        self.assertTrue(deployment_tests.git(consumer, 'status', '--porcelain'))

    def test_tokens_are_forbidden_outside_corresponding_registration(self):
        token = 'fixture-ephemeral-input'
        for flag in ['--runner-registration-token', '--general-runner-registration-token']:
            result = self.upgrade(flag, token)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn(token, result.stdout + result.stderr)
            self.assertFalse(self.capture.exists())


@pytest.fixture
def installation(tmp_path):
    revision = 'a' * 40
    config = json.loads((ROOT / 'deploy/example.json').read_text())
    install, config_root = tmp_path / 'install', tmp_path / 'config'
    release = install / 'releases' / revision
    source = release / 'reviewed-source'
    source.mkdir(parents=True)
    config_root.mkdir()
    (install / 'current').symlink_to(release)
    snapshot = json.dumps(config).encode()
    (release / 'deployment-config.json').write_bytes(snapshot)
    (release / 'deployment-config.json').chmod(0o600)
    (source / '.relay-source.json').write_text(json.dumps({'revision': revision, 'tree': 'b' * 40}))
    (release / 'artifact-manifest.json').write_text(json.dumps({
        'commit': revision, 'installedRevision': revision, 'resolvedRevision': revision,
        'gitTree': 'b' * 40, 'deploymentConfigSha256': hashlib.sha256(snapshot).hexdigest()}))
    (config_root / 'consumer.json').write_text(json.dumps(config['consumer']))
    for path in [tmp_path, *tmp_path.rglob('*')]:
        if not path.is_symlink():
            path.chmod(0o700 if path.is_dir() else 0o600)
    return install, config_root, release, config, tmp_path


def verify_fixture(installation, config=None):
    install, config_root, _, installed_config, boundary = installation
    return upgrade.verify(install, config_root, config or installed_config,
                          owner_uid=os.getuid(), boundary=boundary)


def test_upgrade_preflight_accepts_only_revision_selection_change(installation):
    config = copy.deepcopy(installation[3])
    config['source']['revision'] = 'new-accepted-tag'
    assert verify_fixture(installation, config) == 'a' * 40


@pytest.mark.parametrize('field', ['writerApp', 'reviewerApp', 'runtimeUser', 'paths'])
def test_upgrade_preflight_preserves_consumer_credential_and_runtime_intent(installation, field):
    config = copy.deepcopy(installation[3])
    config['consumer'][field] = 'changed'
    with pytest.raises(ValueError, match='OWNER_INTENT_CHANGED'):
        verify_fixture(installation, config)


@pytest.mark.parametrize('field', ['runner', 'generalRunner', 'tls', 'reviewerBind', 'ingress'])
def test_upgrade_preflight_preserves_registration_tls_and_service_intent(installation, field):
    config = copy.deepcopy(installation[3])
    config['environment'][field] = {'changed': True}
    with pytest.raises(ValueError, match='OWNER_INTENT_CHANGED'):
        verify_fixture(installation, config)


def test_upgrade_preflight_rejects_modified_missing_and_aliased_snapshots(installation):
    snapshot = installation[2] / 'deployment-config.json'
    snapshot.write_text('{}')
    with pytest.raises(ValueError, match='CONFIG_UNPROVEN'):
        verify_fixture(installation)
    snapshot.unlink()
    with pytest.raises(OSError):
        verify_fixture(installation)
    snapshot.symlink_to(installation[2] / 'artifact-manifest.json')
    with pytest.raises(ValueError, match='UNSAFE_PATH'):
        verify_fixture(installation)


def test_upgrade_preflight_rejects_ambiguous_installed_identity(installation):
    manifest = installation[2] / 'artifact-manifest.json'
    value = json.loads(manifest.read_text())
    value['installedRevision'] = 'c' * 40
    manifest.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='IDENTITY_UNPROVEN'):
        verify_fixture(installation)


def test_apply_cannot_bypass_owner_upgrade_and_accepts_first_install(installation):
    install, _, _, _, boundary = installation
    kwargs = {'owner_uid': os.getuid(), 'boundary': boundary}
    assert upgrade.verify_apply(install, 'a' * 40, **kwargs) == 'a' * 40
    with pytest.raises(ValueError, match='REQUIRES_EXPLICIT_UPGRADE'):
        upgrade.verify_apply(install, 'b' * 40, **kwargs)
    assert upgrade.verify_apply(boundary / 'fresh', 'b' * 40, **kwargs) == 'none'
