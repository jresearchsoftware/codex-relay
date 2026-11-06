"""Real signed APT metadata/hash failure and safe same-operation resumption.

APT, protected files and the admission controller execute for real. Service and
GitHub observations use the explicit retained-activation adapter; this does not
claim a live systemd installation or real GitHub job acceptance.
"""
import os
from pathlib import Path
import shutil
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import apt_preflight
import pre_apply_recovery
import retained_activation
from test_bounded_install_recovery import incident, OPERATION, BASELINE, write
from test_retained_activation import payload, Evidence

pytestmark = pytest.mark.skipif(sys.platform != 'linux' or os.geteuid() != 0
    or not all(shutil.which(name) for name in ['apt-get', 'gpg', 'dpkg-deb']),
    reason='native Linux/root APT, GPG and Debian package tools required')


@pytest.fixture
def signed_repository(tmp_path):
    from apt_fixture import signed_repository as create_repository
    yield from create_repository(tmp_path)

def test_signed_metadata_mismatch_then_guarded_same_uuid_continuation(incident, signed_repository, tmp_path):
    name, index, original, runner = signed_repository
    incident.backend.unlink()
    receipt = incident.helper('begin', incident.helper('inspect'))
    incident.native('recovery-target', options={'operationId': OPERATION, 'target': incident.revision})
    incident.native('phase', options={'operationId': OPERATION, 'phase': 'applying'})
    # Exact Ansible Begin backend shape. A real signed-repository acquisition
    # fails after this boundary; APT must not be made to accept altered bytes.
    write(incident.backend, {'schemaVersion': '1', 'state': 'RECOVERY_REQUIRED',
                            'phase': 'apply', 'target_head': incident.revision})
    history, original_receipt = incident.history(), incident.receipt.read_bytes()
    index.write_bytes(original + b'interrupted mirror publication')
    with pytest.raises(ValueError, match='INTEGRITY_OR_ACQUISITION_UNPROVEN'):
        apt_preflight.verify([name], runner=runner, parent=tmp_path)
    assert any('unexpected size' in text or 'Hash Sum mismatch' in text for text in runner.diagnostics)
    incident.native('phase', options={'operationId': OPERATION, 'phase': 'recovery-required'})
    assert pre_apply_recovery.inspect(incident.config, OPERATION, BASELINE, root=incident.root)['receipt'] == receipt
    assert incident.history() == history and incident.receipt.read_bytes() == original_receipt
    # Repair only the disposable mirror fixture. No hash or trust bypass.
    index.write_bytes(original)
    assert apt_preflight.verify([name], runner=runner, parent=tmp_path)['status'] == 'PASS'
    current = payload(); current['observed']['production']['active'] = False
    evidence = Evidence(current); evidence.remote[0]['status'] = 'offline'
    proof = retained_activation.prove(current, evidence)
    assert evidence.events.count('restore-production') == 1
    current['before'] = proof
    assert retained_activation.prove(current, evidence) == proof
    assert evidence.events.count('restore-production') == 1
    incident.native('phase', options={'operationId': OPERATION, 'phase': 'applying'})
    assert incident.helper('revalidate', receipt) == receipt
    assert incident.history() == history and incident.receipt.read_bytes() == original_receipt
    assert incident.publish()['status'] == 'PUBLISHED'
    incident.final_artifacts()
    pre_apply_recovery.bounded.backend_finalize(incident.backend, incident.revision, OPERATION, root=incident.root)
    incident.native('phase', options={'operationId': OPERATION, 'phase': 'verified', 'revision': incident.revision})
    completed = incident.helper('finalize', receipt)
    assert completed['binding'] == receipt['binding'] and completed['original'] == receipt['original']
    incident.native('resume', options={'operationId': OPERATION})
    assert incident.native('status')['phase'] == 'open'
    assert incident.history() == history
