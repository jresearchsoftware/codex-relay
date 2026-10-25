"""SERIAL evidence is preserved before an unsupported pool transition."""
import json
import os
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))

import managed_pool as pool
import pool_migration as migration
from test_pool_eligibility import contract, peer


def observe(root):
    return {str(path.relative_to(root)): (os.readlink(path) if path.is_symlink() else
            path.read_bytes() if path.is_file() else None)
            for path in root.rglob('*')}


def test_fresh_pool_has_no_serial_transition(tmp_path, contract):
    migration.reject_serial_transition(contract, root=tmp_path, owner_uid=os.getuid())


@pytest.mark.parametrize('state', ['inactive', 'active', 'unknown', 'interrupted'])
def test_existing_serial_state_blocks_without_opening_credentials_or_mutating_evidence(tmp_path, contract, state):
    legacy = tmp_path / 'opt' / contract['namespace'] / 'general-runner'
    legacy.mkdir(parents=True)
    (legacy / '.runner').write_text('{"agentId":44}')
    (legacy / '.credentials').write_text('synthetic private fixture')
    journal = tmp_path / 'var/lib' / contract['namespace'] / 'attempt.json'
    journal.parent.mkdir(parents=True)
    journal.write_text(json.dumps({'state': state, 'originalConsumerDigest': 'b' * 64}))
    before = observe(tmp_path)
    for _ in range(2):
        with pytest.raises(pool.PoolError, match='MANAGED_POOL_SERIAL_TRANSITION_REQUIRED'):
            migration.reject_serial_transition(contract, root=tmp_path, owner_uid=os.getuid())
        assert observe(tmp_path) == before


def test_original_serial_service_without_registration_is_also_preserved(tmp_path, contract):
    unit = tmp_path / 'etc/systemd/system' / (contract['namespace'] + '-general-runner.service')
    unit.parent.mkdir(parents=True)
    unit.write_text('[Service]\nExecStart=/original/general-runner/run.sh\n')
    before = observe(tmp_path)
    with pytest.raises(pool.PoolError, match='SERIAL_TRANSITION_REQUIRED'):
        migration.reject_serial_transition(contract, root=tmp_path, owner_uid=os.getuid())
    assert observe(tmp_path) == before


def test_protected_serial_snapshot_blocks_even_when_transport_was_already_stopped(tmp_path, contract):
    snapshot = peer(tmp_path, contract, namespace=contract['namespace'], repository=contract['repository']).snapshot
    value = json.loads(snapshot.read_text())
    value['consumer'].pop('generalRunnerPool')
    snapshot.write_text(json.dumps(value))
    before = observe(tmp_path)
    with pytest.raises(pool.PoolError, match='SERIAL_TRANSITION_REQUIRED'):
        migration.reject_serial_transition(contract, root=tmp_path, owner_uid=os.getuid())
    assert observe(tmp_path) == before


def test_verified_existing_pool_is_accepted_without_rewriting_its_binding(tmp_path, contract):
    peer(tmp_path, contract, namespace=contract['namespace'], repository=contract['repository'])
    before = observe(tmp_path)
    migration.reject_serial_transition(contract, root=tmp_path, owner_uid=os.getuid())
    assert observe(tmp_path) == before


def test_incomplete_or_unsafe_installed_state_never_becomes_a_fresh_install(tmp_path, contract):
    install = tmp_path / 'opt' / contract['namespace']
    install.mkdir(parents=True)
    (install / 'current').write_text('unproven current')
    before = observe(tmp_path)
    with pytest.raises(pool.PoolError, match='SERIAL_STATE_UNPROVEN'):
        migration.reject_serial_transition(contract, root=tmp_path, owner_uid=os.getuid())
    assert observe(tmp_path) == before


@pytest.mark.parametrize('snapshot', ['missing', 'tampered'])
def test_authenticated_managed_legacy_guard_never_reads_current_snapshot(tmp_path, contract, monkeypatch, snapshot):
    installed = peer(tmp_path, contract, namespace=contract['namespace'], repository=contract['repository'])
    if snapshot == 'missing':
        installed.snapshot.unlink()
    else:
        installed.snapshot.write_bytes(b'{unbound current snapshot')
    before = observe(tmp_path)
    original_open = os.open

    def guarded_open(path, *args, **kwargs):
        assert not isinstance(path, (str, Path)) or Path(path).name != 'deployment-config.json'
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(os, 'open', guarded_open)
    migration.reject_legacy_registration(contract, root=tmp_path, owner_uid=os.getuid())
    assert observe(tmp_path) == before


@pytest.mark.parametrize('kind', ['registration', 'service'])
def test_authenticated_managed_legacy_guard_preserves_original_artifacts(tmp_path, contract, kind):
    if kind == 'registration':
        path = tmp_path / 'opt' / contract['namespace'] / 'general-runner'
        path.mkdir(parents=True)
        (path / '.credentials').write_bytes(b'private legacy evidence, never opened by guard')
    else:
        path = tmp_path / 'etc/systemd/system' / (contract['namespace'] + '-general-runner.service')
        path.parent.mkdir(parents=True)
        path.write_text('[Service]\nExecStart=/original/run.sh\n')
    before = observe(tmp_path)
    with pytest.raises(pool.PoolError, match='SERIAL_TRANSITION_REQUIRED'):
        migration.reject_legacy_registration(contract, root=tmp_path, owner_uid=os.getuid())
    assert observe(tmp_path) == before


@pytest.mark.parametrize('unsafe', ['symlink', 'writable'])
def test_authenticated_managed_legacy_guard_keeps_protected_parent_boundary(tmp_path, contract, unsafe):
    if unsafe == 'symlink':
        target = tmp_path / 'elsewhere'
        target.mkdir()
        (tmp_path / 'opt').symlink_to(target)
    else:
        (tmp_path / 'opt').mkdir(mode=0o777)
        (tmp_path / 'opt').chmod(0o777)
    with pytest.raises((pool.PoolError, OSError)):
        migration.reject_legacy_registration(contract, root=tmp_path, owner_uid=os.getuid())
