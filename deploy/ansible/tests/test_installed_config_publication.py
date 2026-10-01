"""Execute private snapshot publication against synthetic native files only."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
TASK = ROOT / 'roles/relay_artifacts/tasks/installed-config.yml'
HEAD = 'a' * 40
MARKER = 'fixture-private-deployment-content'
pytestmark = pytest.mark.skipif(
    os.name == 'nt' or getattr(os, 'geteuid', lambda: 1)() != 0 or not shutil.which('ansible-playbook'),
    reason='native root filesystem and Ansible required')


@pytest.fixture
def publication():
    with tempfile.TemporaryDirectory(prefix='relay-snapshot-test-', dir='/run') as temporary:
        root = Path(temporary)
        source = root / 'owner-input.json'
        raw = json.dumps({'fixture': MARKER, 'source': {'revision': 'main'}}, indent=2) + '\n'
        source.write_text(raw)
        source.chmod(0o600)
        release = root / 'releases' / HEAD
        yield {'root': root, 'source': source, 'raw': raw, 'release': release,
               'snapshot': release / 'deployment-config.json'}


def metadata(path):
    info = path.lstat()
    return tuple(getattr(info, field) for field in (
        'st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size',
        'st_mtime_ns', 'st_ctime_ns'))


def run_publication(fixture, *, check=False, variables=None, before=(), after=()):
    root = fixture['root']
    values = {
        'relay_release_path': str(fixture['release']),
        'relay_installed_deployment_config': fixture['raw'],
        'relay_installed_deployment_config_sha256': hashlib.sha256(fixture['raw'].encode()).hexdigest(),
        'ansible_remote_tmp': str(root / 'remote-tmp'),
    }
    values.update(variables or {})
    playbook = root / 'publication.yml'
    playbook.write_text(json.dumps([{
        'hosts': 'localhost', 'connection': 'local', 'gather_facts': False,
        'vars': values, 'tasks': [*before, {'ansible.builtin.include_tasks': str(TASK)}, *after],
    }], indent=2))
    playbook.chmod(0o600)
    environment = os.environ.copy()
    environment.update(ANSIBLE_NOCOLOR='1', ANSIBLE_LOCALHOST_WARNING='False',
                       ANSIBLE_LOCAL_TEMP=str(root / 'local-tmp'))
    result = subprocess.run(
        ['ansible-playbook', '-i', 'localhost,', '-c', 'local', '--diff',
         *(['--check'] if check else []), str(playbook)],
        cwd=ROOT, env=environment, capture_output=True, text=True, timeout=60)
    assert MARKER not in result.stdout + result.stderr
    assert fixture['raw'] not in result.stdout + result.stderr
    return result


def test_snapshot_is_exact_private_and_identical_republication_is_unchanged(publication):
    publication['release'].mkdir(parents=True)
    source_before = metadata(publication['source'])
    first = run_publication(publication)
    assert first.returncode == 0, first.stdout + first.stderr
    snapshot = publication['snapshot']
    assert snapshot.read_bytes() == publication['raw'].encode()
    info = snapshot.stat()
    assert info.st_uid == info.st_gid == 0
    assert stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1
    first_state = metadata(snapshot)
    second = run_publication(publication)
    assert second.returncode == 0, second.stdout + second.stderr
    assert re.search(r'localhost\s*:\s*ok=\d+\s+changed=0\b', second.stdout)
    assert metadata(snapshot) == first_state
    assert metadata(publication['source']) == source_before
    assert publication['source'].read_bytes() == publication['raw'].encode()


def test_check_mode_missing_release_reports_plan_without_publishing(publication):
    source_before = metadata(publication['source'])
    result = run_publication(publication, check=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'INSTALLED_DEPLOYMENT_CONFIG_CHECK_MODE_PLAN=protected-snapshot-pending' in result.stdout
    assert not publication['release'].exists()
    assert not publication['snapshot'].exists()
    assert metadata(publication['source']) == source_before


@pytest.mark.parametrize('alias', ['symlink', 'hardlink'])
def test_aliased_destination_is_rejected_without_residue_or_source_mutation(publication, alias):
    publication['release'].mkdir(parents=True)
    snapshot, source = publication['snapshot'], publication['source']
    if alias == 'symlink':
        snapshot.symlink_to(source)
    else:
        os.link(source, snapshot)
    source_before, snapshot_before = metadata(source), metadata(snapshot)
    children_before = sorted(path.name for path in publication['release'].iterdir())
    result = run_publication(publication)
    assert result.returncode != 0
    assert 'INSTALLED_DEPLOYMENT_CONFIG_FILE_UNSAFE' in result.stdout + result.stderr
    assert source.read_bytes() == publication['raw'].encode()
    assert metadata(source) == source_before
    assert metadata(snapshot) == snapshot_before
    assert sorted(path.name for path in publication['release'].iterdir()) == children_before


def test_input_digest_mismatch_publishes_nothing_and_hides_content(publication):
    publication['release'].mkdir(parents=True)
    result = run_publication(publication, variables={'relay_installed_deployment_config_sha256': '0' * 64})
    assert result.returncode != 0
    assert not publication['snapshot'].exists()
    assert list(publication['release'].iterdir()) == []


def test_interruption_after_snapshot_preserves_operation_record(publication):
    publication['release'].mkdir(parents=True)
    record = publication['root'] / 'operation.json'
    variables = {
        'relay_deployment_profile': 'production', 'relay_local_apply_source': 'installed',
        'relay_production_operation_phase': 'apply', 'relay_production_operation_target_head': HEAD,
        'relay_production_operation_active_phase': 'apply', 'relay_production_operation_active_head': HEAD,
        'relay_production_operation_recovery_required': False,
        'relay_production_operation_record_path': str(record),
        'relay_production_operation_lock_path': str(publication['root'] / 'operation.lock'),
        'relay_production_operation_schema_version': '1',
    }
    result = run_publication(publication, variables=variables,
        before=[{'ansible.builtin.include_tasks': str(ROOT / 'tasks/production-operation-state-begin.yml')}],
        after=[{'ansible.builtin.fail': {'msg': 'FIXTURE_INTERRUPTED_AFTER_SNAPSHOT'}}])
    assert result.returncode != 0
    assert 'FIXTURE_INTERRUPTED_AFTER_SNAPSHOT' in result.stdout + result.stderr
    assert publication['snapshot'].read_bytes() == publication['raw'].encode()
    assert json.loads(record.read_text()) == {
        'schemaVersion': '1', 'state': 'RECOVERY_REQUIRED', 'phase': 'apply', 'target_head': HEAD,
    }
    assert stat.S_IMODE(record.stat().st_mode) == 0o600
