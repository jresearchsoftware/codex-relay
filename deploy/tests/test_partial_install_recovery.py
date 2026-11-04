"""The precise post-rename frontier, with original protected bytes/processes."""
import copy
import json
from pathlib import Path
import sys

import pytest

from test_bounded_install_recovery import incident, BASELINE, OPERATION, write
import partial_install_recovery as partial

pytestmark = pytest.mark.skipif(sys.platform != 'linux', reason='native Linux filesystem proof')


def frontier(incident):
    proof = incident.helper('inspect')
    receipt = incident.helper('begin', proof)
    incident.native('recovery-target', options={'operationId': OPERATION, 'target': incident.revision})
    incident.native('phase', options={'operationId': OPERATION, 'phase': 'applying'})
    with pytest.raises(ValueError, match='TRANSITION_REQUIRES_RECOVERY'):
        incident.publish(interrupt=True)
    incident.final_artifacts()
    return receipt


def test_partial_frontier_proves_frozen_pair_and_preserves_old_gate_backend_history(incident):
    receipt = frontier(incident)
    before, history = incident.snapshot(), incident.history()
    value = partial.inspect(incident.config, OPERATION, BASELINE, root=incident.root)
    assert value['receipt'] == receipt
    assert value['gate']['phase'] == 'applying'
    assert value['gate']['consumerDigest'] != receipt['desiredDigest']
    assert value['sourceIdentity']['revision'] == receipt['binding']['desiredRevision']
    assert incident.snapshot() == before and incident.history() == history
    assert json.loads(incident.backend.read_bytes())['target_head'] == BASELINE


@pytest.mark.parametrize('change', ['backup', 'consumer', 'pair', 'backend', 'gate', 'operation', 'archive'])
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
    else:
        archive = incident.receipt.with_name(incident.receipt.name.removesuffix('.json') + '.original.json')
        write(archive, incident.backend.read_bytes())
    before, history = incident.snapshot(), incident.history()
    with pytest.raises((ValueError, FileNotFoundError)):
        partial.inspect(config, operation, BASELINE, root=incident.root)
    assert incident.snapshot() == before and incident.history() == history
