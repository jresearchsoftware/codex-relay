"""The precise post-rename frontier, with original protected bytes/processes."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from test_bounded_install_recovery import incident, BASELINE, OPERATION, write
import partial_install_recovery as partial

pytestmark = pytest.mark.skipif(sys.platform != 'linux' or os.geteuid() != 0,
    reason='root native Linux filesystem proof')


def test_old_runtime_observer_hashes_actual_proc_executable_and_refuses_another_product(monkeypatch):
    monkeypatch.setattr(partial.subprocess, 'check_output', lambda *a, **k: str(os.getpid()) + '\n')
    with Path('/proc/self/exe').open('rb') as stream:
        expected = hashlib.file_digest(stream, 'sha256').hexdigest()
    observed = partial.old_reviewer('synthetic-test-only', expected)
    assert observed['pid'] == os.getpid() and observed['startTicks'] > 0
    with pytest.raises(ValueError, match='OLD_REVIEWER_RUNTIME_UNPROVEN'):
        partial.old_reviewer('synthetic-test-only', '0' * 64)


def test_publication_failure_keeps_bounded_cause_and_removes_private_remote_details(monkeypatch):
    report = {'error_code': 'CONSUMER_PUBLICATION_TRANSITION_REQUIRES_RECOVERY',
        'controller_diagnostic': {'action': 'consumer-transition', 'failure': 'nonzero_exit',
            'code': 'ADMISSION_NOT_DRAINED', 'exit_code': 1, 'path': '/private/diagnostic',
            'message': 'private response body'}}
    monkeypatch.setattr(partial, 'run_target', lambda *a, **k:
        SimpleNamespace(returncode=1, stdout=json.dumps(report)))
    with pytest.raises(ValueError, match='CONSUMER_PUBLICATION_TRANSITION_REQUIRES_RECOVERY') as caught:
        partial.publish(SimpleNamespace(target={}, key=None), ['fixed-fixture-command'])
    assert caught.value.controller_diagnostic == {'action': 'consumer-transition', 'failure': 'nonzero_exit',
        'code': 'ADMISSION_NOT_DRAINED', 'exit_code': 1}


def test_controller_acceptance_uses_original_policy_and_native_public_main(monkeypatch, tmp_path):
    controller, accepted = 'a' * 40, 'b' * 40
    binding = {'gitConfigReceipt': {'source_policy': 'accepted-ancestor',
        'product_repository': 'example/product'}}
    requests = []
    def native(argv, **options):
        requests.append(argv)
        return (accepted + '\trefs/heads/main\n')
    monkeypatch.setattr(partial.subprocess, 'check_output', native)
    monkeypatch.setattr(partial.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=0))
    assert partial.accepted_controller(tmp_path, binding, controller)['acceptedMain'] == accepted
    assert requests[0][-3:] == ['--exit-code', 'https://github.com/example/product.git', 'refs/heads/main']
    monkeypatch.setattr(partial.subprocess, 'run', lambda argv, **k:
        SimpleNamespace(returncode=1 if 'merge-base' in argv else 0))
    with pytest.raises(ValueError, match='CONTROLLER_NOT_ACCEPTED'):
        partial.accepted_controller(tmp_path, binding, controller)
    requests.clear()
    binding['gitConfigReceipt']['source_policy'] = 'test-qualified-exact'
    assert partial.accepted_controller(tmp_path, binding, controller)['policy'] == 'test-qualified-exact'
    assert requests == []


def frontier(incident):
    path = incident.release / 'artifact-manifest.json'
    old = json.loads(path.read_bytes()); old['reviewerBinarySha256'] = 'a' * 64; write(path, old)
    proof = incident.helper('inspect')
    receipt = incident.helper('begin', proof)
    incident.native('recovery-target', options={'operationId': OPERATION, 'target': incident.revision})
    incident.native('phase', options={'operationId': OPERATION, 'phase': 'applying'})
    with pytest.raises(ValueError, match='TRANSITION_REQUIRES_RECOVERY'):
        incident.publish(interrupt=True)
    incident.final_artifacts()
    path = incident.install / 'releases' / incident.revision / 'artifact-manifest.json'
    desired = json.loads(path.read_bytes()); desired['reviewerBinarySha256'] = 'b' * 64; write(path, desired)
    return receipt


@pytest.mark.parametrize('digest_advanced', [False, True])
def test_partial_frontier_proves_frozen_pair_and_preserves_old_gate_backend_history(incident, digest_advanced):
    receipt = frontier(incident)
    if digest_advanced:
        gate = json.loads(incident.gate.read_bytes())
        gate['consumerDigest'] = receipt['desiredDigest']
        write(incident.gate, gate)
    before, history = incident.snapshot(), incident.history()
    value = partial.inspect(incident.config, OPERATION, BASELINE, root=incident.root)
    assert value['receipt'] == receipt
    assert value['gate']['phase'] == 'applying'
    assert (value['gate']['consumerDigest'] == receipt['desiredDigest']) is digest_advanced
    assert value['sourceIdentity']['revision'] == receipt['binding']['desiredRevision']
    assert incident.snapshot() == before and incident.history() == history
    assert json.loads(incident.backend.read_bytes())['target_head'] == BASELINE


@pytest.mark.parametrize('change', ['backup', 'consumer', 'pair', 'backend', 'gate', 'operation', 'archive', 'same-runtime'])
def test_partial_frontier_rejects_altered_or_ambiguous_evidence_before_effects(incident, change):
    frontier(incident)
    config = copy.deepcopy(incident.config)
    operation = OPERATION
    if change == 'backup':
        write(incident.backup, b'{}')
    elif change == 'consumer':
        # Same resource identity is insufficient to reinterpret unknown bytes.
        config['consumer']['defaultProfile']['effort'] = 'low'
    elif change == 'pair':
        manifest = incident.install / 'releases' / incident.revision / 'artifact-manifest.json'
        value = json.loads(manifest.read_bytes())
        value['gitConfigReceipt']['config_sha'] = 'd' * 40
        write(manifest, value)
    elif change == 'backend':
        write(incident.backend, b'{}')
    elif change == 'gate':
        value = json.loads(incident.gate.read_bytes()); value['phase'] = 'verified'
        value['verifiedRevision'] = incident.revision; write(incident.gate, value)
    elif change == 'operation':
        operation = '22345678-1234-4234-8234-123456789abc'
    elif change == 'archive':
        archive = incident.receipt.with_name(incident.receipt.name.removesuffix('.json') + '.original.json')
        write(archive, incident.backend.read_bytes())
    else:
        path = incident.install / 'releases' / incident.revision / 'artifact-manifest.json'
        value = json.loads(path.read_bytes()); value['reviewerBinarySha256'] = 'a' * 64; write(path, value)
    before, history = incident.snapshot(), incident.history()
    with pytest.raises((ValueError, FileNotFoundError)):
        partial.inspect(config, operation, BASELINE, root=incident.root)
    assert incident.snapshot() == before and incident.history() == history
