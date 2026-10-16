"""Root-owned synthetic migration snapshots with the strict installed old ABI.

All files live below a disposable /run tree. Only systemd/restart transport is
substituted; the actual Ansible lifecycle tasks and protected file reads run.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import test_upgrade_lifecycle_activation as ordinary
from test_upgrade_lifecycle_activation import ANSIBLE, HEAD, OPERATION, service, socket_state

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tests'))
from test_managed_pool_workflows import pool_configuration
import config


@unittest.skipUnless(ANSIBLE and os.geteuid() == 0, 'Linux root and Ansible required for private /run fixture')
class SerialPoolLifecycleTests(unittest.TestCase):
    run_play = ordinary.UpgradeActivationTests.run_play

    def fixture(self, root, *, capacity=2, slots=32, active_pool=False, missing_manual=True):
        target = pool_configuration(capacity)
        compiled = config.compile_inputs(target)
        additional = compiled['relay_additional_execution_slots'][:slots - 1]
        primary = compiled['relay_general_runner_service_name']
        inactive = service(loaded=False)
        initial = {'reviewer.service': service(41, active=True, enabled='enabled'),
                   'production.service': service(),
                   primary: service(61, active=True, enabled='enabled') if active_pool else inactive,
                   'codex-relay-relay-manual-outcome.socket': socket_state(loaded=not missing_manual)}
        for number, item in enumerate(additional, 2):
            initial[item['relay_runner_service_name']] = (
                service(60 + number, active=True, enabled='enabled') if active_pool and number <= capacity else inactive)
        final = {**initial, 'reviewer.service': service(51, active=True, enabled='enabled'),
                 'codex-relay-relay-manual-outcome.socket': socket_state()}
        tasks, values, trace = ordinary.UpgradeActivationTests.fixture(self, root, initial, final, legacy_snapshot=True)
        # The installed old helper keeps its old configuration and exact
        # three-component ABI throughout this fixture, even with 32 new slots.
        old_services = {'reviewer': {'active': True, 'enabled': 'enabled', 'load': 'loaded'},
                        'production': {'active': False, 'enabled': 'disabled', 'load': 'loaded'},
                        'general': {'active': True, 'enabled': 'enabled', 'load': 'loaded'}}
        subprocess.run([str(root / 'relay-admission'), 'snapshot', '--operation', OPERATION],
                       input=json.dumps(old_services), text=True, capture_output=True, check=True)
        old_gate = root / 'gate/admission-v1.json'
        old_bytes = old_gate.read_bytes()
        target_services = {'reviewer': old_services['reviewer'], 'production': old_services['production'],
                           'general': {'active': active_pool, 'enabled': 'enabled' if active_pool else 'disabled',
                                       'load': 'loaded' if active_pool else 'not-found'}}
        if not missing_manual:
            target_services['manualOutcome'] = {'active': False, 'enabled': 'disabled', 'load': 'loaded'}
        for number, item in enumerate(additional, 2):
            active = active_pool and number <= capacity
            target_services['slot-' + item['relay_execution_slot']] = {
                'active': active, 'enabled': 'enabled' if active else 'disabled', 'load': 'loaded' if active else 'not-found'}
        target_digest = 'b' * 64
        new_gate = root / 'gate/admission-pool-v1.json'
        new_gate.write_text(json.dumps({'version': 1, 'consumerDigest': target_digest, 'phase': 'applying',
            'operationId': OPERATION, 'target': HEAD, 'previousActive': target_services, 'verifiedRevision': None}))
        new_gate.chmod(0o600)
        configuration = root / 'configuration'
        configuration.mkdir(mode=0o700)
        receipt = {'version': 1, 'namespace': 'codex-relay', 'repository': target['consumer']['repository'],
                   'operationId': OPERATION, 'target': {'consumerDigest': target_digest},
                   'original': {'consumerDigest': 'a' * 64, 'gateSha256': hashlib.sha256(old_bytes).hexdigest()}}
        receipt_path = configuration / 'serial-pool-compat-v1.json'
        receipt_path.write_text(json.dumps(receipt))
        receipt_path.chmod(0o644)
        transition = {'version': 1, 'operationId': OPERATION, 'targetRevision': HEAD, 'phase': 'stopped',
                      'receiptSha256': hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
                      'plan': {'target': {'consumerDigest': target_digest}}}
        transition_path = root / 'gate/serial-pool-transition-v1.json'
        transition_path.write_text(json.dumps(transition))
        transition_path.chmod(0o600)
        values.update(relay_serial_pool_transition=True, relay_general_runner_service_name=primary,
                      relay_additional_execution_slots=additional,
                      relay_general_runner_pool=compiled['relay_general_runner_pool'],
                      relay_writer_claim_root=str(root / 'gate'), relay_config_root=str(configuration),
                      relay_github_repository=target['consumer']['repository'])
        return tasks, values, trace, old_gate, old_bytes, new_gate, initial, final

    def test_registered_serial_to_capacity_one_and_two_with_all_32_slots_preserves_old_abi_and_bytes(self):
        for capacity in [1, 2]:
            with self.subTest(capacity=capacity), tempfile.TemporaryDirectory(prefix='relay-pool-lifecycle-', dir='/run') as temporary:
                root = Path(temporary)
                tasks, values, trace, old_gate, old_bytes, new_gate, _, _ = self.fixture(root, capacity=capacity)
                target_bytes = new_gate.read_bytes()
                result = self.run_play(root, tasks, values)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('RELAY_UPGRADE_ACTIVATION_VALIDATED=' + HEAD, result.stdout)
                self.assertEqual(trace.read_text(), 'restart\n')
                self.assertEqual(old_gate.read_bytes(), old_bytes)
                self.assertEqual(new_gate.read_bytes(), target_bytes)
                self.assertEqual(len(json.loads(target_bytes)['previousActive']), 34)

    def test_existing_active_peer_pool_keeps_same_primary_and_additional_transport(self):
        with tempfile.TemporaryDirectory(prefix='relay-pool-active-', dir='/run') as temporary:
            root = Path(temporary)
            tasks, values, _, old_gate, old_bytes, _, _, _ = self.fixture(root, slots=2, active_pool=True)
            result = self.run_play(root, tasks, values)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(old_gate.read_bytes(), old_bytes)

    def test_replaced_active_peer_pool_transport_cannot_produce_same_operation_success(self):
        with tempfile.TemporaryDirectory(prefix='relay-pool-replaced-', dir='/run') as temporary:
            root = Path(temporary)
            tasks, values, _, old_gate, old_bytes, _, _, final = self.fixture(root, slots=2, active_pool=True)
            slot = values['relay_additional_execution_slots'][0]['relay_runner_service_name']
            final[slot] = service(999, active=True, enabled='enabled')
            # Preserve the real restart boundary but make its observed final
            # transport differ; validation must detect it without bypasses.
            restart = root / 'restart'
            restart.write_text('#!/usr/bin/python3\nimport json\nfrom pathlib import Path\n'
                               f'Path({str(root / "state.json")!r}).write_text({json.dumps(final)!r})\n')
            restart.chmod(0o755)
            result = self.run_play(root, tasks, values)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('RELAY_UPGRADE_SLOT_TRANSPORT_CHANGED', result.stdout)
            self.assertNotIn('RELAY_UPGRADE_ACTIVATION_VALIDATED=', result.stdout)
            self.assertEqual(old_gate.read_bytes(), old_bytes)

    def test_retained_target_intent_survives_failed_reviewer_activation_and_reapply(self):
        with tempfile.TemporaryDirectory(prefix='relay-pool-recovery-', dir='/run') as temporary:
            root = Path(temporary)
            tasks, values, _, old_gate, old_bytes, new_gate, initial, _ = self.fixture(root, slots=2)
            original = new_gate.read_bytes()
            initial['reviewer.service'] = service(enabled='enabled')
            (root / 'state.json').write_text(json.dumps(initial))
            first = self.run_play(root, tasks[:1], values)
            self.assertNotEqual(first.returncode, 0, first.stdout + first.stderr)
            self.assertIn('RELAY_UPGRADE_RETAINED_ACTIVITY_RECOVERY_REQUIRED', first.stdout)
            values['relay_admission_recovery_authorized'] = True
            recovered = self.run_play(root, tasks, values)
            self.assertEqual(recovered.returncode, 0, recovered.stdout + recovered.stderr)
            self.assertEqual(new_gate.read_bytes(), original)
            self.assertEqual(old_gate.read_bytes(), old_bytes)

    def test_wrong_operation_digest_target_and_modified_or_aliased_old_gate_stop_before_restart(self):
        for damage in ['operation', 'digest', 'target', 'original-bytes', 'original-symlink']:
            with self.subTest(damage=damage), tempfile.TemporaryDirectory(prefix='relay-pool-binding-', dir='/run') as temporary:
                root = Path(temporary)
                tasks, values, trace, old_gate, old_bytes, new_gate, _, _ = self.fixture(root, slots=1)
                if damage == 'original-bytes':
                    old_gate.write_bytes(old_bytes + b'\n')
                elif damage == 'original-symlink':
                    saved = old_gate.with_name('saved-original.json')
                    old_gate.rename(saved)
                    old_gate.symlink_to(saved)
                else:
                    data = json.loads(new_gate.read_text())
                    field = {'operation': 'operationId', 'digest': 'consumerDigest', 'target': 'target'}[damage]
                    data[field] = 'c' * 64 if damage == 'digest' else 'c' * 40 if damage == 'target' else '12345678-1234-1234-1234-123456789abd'
                    new_gate.write_text(json.dumps(data))
                result = self.run_play(root, tasks[:1], values)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('RELAY_UPGRADE_SERIAL_POOL_SNAPSHOT_UNPROVEN', result.stdout + result.stderr)
                self.assertFalse(trace.exists())
