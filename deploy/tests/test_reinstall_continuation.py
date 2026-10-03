"""Pending reinstall evidence cannot become an ordinary apply recovery."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'deploy/ansible/scripts/verify_reinstall_continuation.py'
spec = importlib.util.spec_from_file_location('verify_reinstall_continuation', SCRIPT)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
HEAD = 'a' * 40


@pytest.fixture
def pending(tmp_path):
    config = {'environment': {'namespace': 'sample-relay'}, 'source': {'revision': HEAD}}
    path = tmp_path / 'sample-relay-clean-reinstall.json'
    value = {'schemaVersion': 1, 'stage': 'DECOMMISSIONED', 'targetRevision': HEAD,
             'configurationSha256': hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()}
    path.write_text(json.dumps(value, sort_keys=True) + '\n')
    path.chmod(0o600)
    tmp_path.chmod(0o700)
    return path, config, value


def verify(pending, *, phase='apply', digest=None, config=None, head=HEAD):
    path, current, _ = pending
    if digest is None:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return gate.verify(path, head, phase, digest, json.dumps(config or current),
                       owner_uid=os.getuid(), owner_gid=os.getgid(), boundary=path.parent)


@pytest.mark.parametrize('phase', ['apply', 'post-check'])
def test_only_exact_current_continuation_passes_without_mutating_evidence(pending, phase):
    path = pending[0]
    before = path.read_bytes(), gate._stamp(path.stat())
    assert verify(pending, phase=phase) == HEAD
    assert (path.read_bytes(), gate._stamp(path.stat())) == before


@pytest.mark.parametrize('phase', ['apply', 'post-check', 'check', 'activate', 'runner-enable', 'stale-dispose'])
def test_ordinary_invocations_cannot_resume_retained_reinstall(pending, phase):
    with pytest.raises(ValueError, match='REINSTALL_CONTINUATION_BLOCKED'):
        verify(pending, phase=phase, digest='')


@pytest.mark.parametrize('phase', ['check', 'activate', 'runner-enable', 'stale-dispose'])
def test_continuation_digest_never_authorizes_another_phase(pending, phase):
    with pytest.raises(ValueError, match='REINSTALL_CONTINUATION_BLOCKED'):
        verify(pending, phase=phase)


@pytest.mark.parametrize('damage', ['digest', 'head', 'config', 'stage', 'schema', 'namespace', 'duplicate', 'oversize'])
def test_changed_or_partial_binding_is_blocked(pending, damage):
    path, config, value = pending
    kwargs = {}
    if damage == 'digest':
        kwargs['digest'] = '0' * 64
    elif damage == 'head':
        kwargs['head'] = 'b' * 40
    elif damage == 'config':
        kwargs['config'] = {**config, 'changed': True}
    elif damage in ['stage', 'schema', 'namespace']:
        if damage == 'namespace':
            config['environment']['namespace'] = 'foreign'
            value['configurationSha256'] = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
        else:
            value['stage' if damage == 'stage' else 'schemaVersion'] = 'RESERVED'
        path.write_text(json.dumps(value))
    else:
        path.write_text('{"stage":"DECOMMISSIONED","stage":"DECOMMISSIONED"}'
                        if damage == 'duplicate' else 'x' * (gate.LIMIT + 1))
    with pytest.raises(ValueError, match='REINSTALL_CONTINUATION_BLOCKED'):
        verify(pending, **kwargs)


@pytest.mark.parametrize('damage', ['mode', 'hardlink', 'symlink', 'next', 'parent-writable'])
def test_unprotected_or_interrupted_journal_fails_closed(pending, damage):
    path = pending[0]
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if damage == 'mode':
        path.chmod(0o644)
    elif damage == 'hardlink':
        os.link(path, path.with_name('alias'))
    elif damage == 'symlink':
        saved = path.with_name('saved')
        path.rename(saved)
        path.symlink_to(saved)
    elif damage == 'next':
        path.with_name(path.name + '.next').write_text('interrupted replacement')
    else:
        path.parent.chmod(0o777)
    with pytest.raises((ValueError, OSError)):
        verify(pending, digest=digest)


def test_normal_no_journal_path_does_not_require_snapshot_or_create_state(tmp_path):
    journal = tmp_path / 'sample-relay-clean-reinstall.json'
    assert gate.verify(journal, HEAD, 'apply') == 'none'
    assert list(tmp_path.iterdir()) == []
    with pytest.raises(ValueError):
        gate.verify(journal, HEAD, 'post-check', 'a' * 64)


def test_command_failure_does_not_disclose_configuration(tmp_path):
    result = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path / 'sample-relay-clean-reinstall.json'),
                             HEAD, 'apply', '0' * 64], input='PRIVATE_FIXTURE_NEVER_PRINT',
                            text=True, capture_output=True)
    assert result.returncode != 0
    assert result.stderr.strip() == 'REINSTALL_CONTINUATION_BLOCKED;inspect-retained-reinstall-evidence'
    assert 'PRIVATE_FIXTURE' not in result.stdout + result.stderr


@pytest.mark.skipif(os.geteuid() != 0 or not shutil.which('ansible-playbook'),
                    reason='root native Ansible required for protected synthetic task composition')
@pytest.mark.parametrize('source,digest_present', [('checkout', False), ('installed', False), ('installed', True)])
def test_real_backend_task_blocks_ordinary_apply_but_accepts_exact_continuation(source, digest_present):
    with tempfile.TemporaryDirectory(prefix='relay-reinstall-gate-', dir='/run') as temporary:
        root = Path(temporary)
        config = {'environment': {'namespace': 'sample-relay'}}
        journal = root / 'sample-relay-clean-reinstall.json'
        journal.write_text(json.dumps({'schemaVersion': 1, 'stage': 'DECOMMISSIONED', 'targetRevision': HEAD,
            'configurationSha256': hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()}))
        journal.chmod(0o600)
        operation = root / 'operation.json'
        operation.write_text(json.dumps({'schemaVersion': '1', 'state': 'RECOVERY_REQUIRED', 'phase': 'apply', 'target_head': HEAD}))
        operation.chmod(0o600)
        variables = {'relay_deployment_profile': 'production', 'relay_namespace': 'sample-relay',
            'relay_production_operation_phase': 'apply', 'relay_production_operation_target_head': HEAD,
            'relay_production_operation_record_path': str(operation), 'relay_production_operation_schema_version': '1',
            'relay_local_apply_source': source, 'relay_installed_config_recovery_authorized': True,
            'relay_clean_reinstall_journal_sha256': hashlib.sha256(journal.read_bytes()).hexdigest() if digest_present else '',
            'relay_installed_deployment_config': json.dumps(config)}
        reached = root / 'unreachable-mutation'
        playbook = root / 'fixture.yml'
        playbook.write_text(yaml.safe_dump([{'hosts': 'localhost', 'gather_facts': False, 'vars': variables, 'tasks': [
            {'ansible.builtin.include_tasks': str(ROOT / 'deploy/ansible/tasks/production-operation-state.yml')},
            {'ansible.builtin.copy': {'content': 'continued', 'dest': str(reached)}},
        ]}]))
        result = subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(playbook)],
                                 capture_output=True, text=True)
        assert (result.returncode == 0) == digest_present, result.stdout + result.stderr
        assert reached.exists() == digest_present
        assert operation.exists() and journal.exists()
