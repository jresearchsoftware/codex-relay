"""Native filesystem qualification of retirement and interruption containment."""
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace

import pytest
import yaml
from jinja2 import Environment

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
import clean_reinstall as reinstall

SOURCE, TARGET = 'a' * 40, 'b' * 40


class Systemd:
    def __init__(self, config):
        self.units = {name: 'inactive' for name in reinstall.unit_names(config)}
        self.units[reinstall.unit_names(config)[2]] = 'active'
        self.calls = []
        self.fail_stop = False

    def __call__(self, arguments, **kwargs):
        _, operation, name, *_ = arguments
        self.calls.append((operation, name))
        if operation == 'show':
            return SimpleNamespace(returncode=0, stdout='\n'.join([
                'LoadState=loaded', 'ActiveState=' + self.units[name],
                'MainPID=' + ('42' if self.units[name] == 'active' else '0'),
                'ControlPID=0', 'FragmentPath=/etc/systemd/system/' + name, 'DropInPaths=']))
        if operation == 'stop':
            if self.fail_stop:
                return SimpleNamespace(returncode=1, stdout='')
            self.units[name] = 'inactive'
        return SimpleNamespace(returncode=0, stdout='')


@pytest.fixture
def installation(tmp_path, request):
    config = json.loads((ROOT / 'deploy/example.json').read_text())
    root = tmp_path
    if os.getuid() == 0:
        directory = tempfile.TemporaryDirectory(prefix='relay-reinstall-test-', dir='/run')
        request.addfinalizer(directory.cleanup)
        root = Path(directory.name)
    paths = reinstall.namespace_paths(config, root)
    for path in [paths['install'], paths['config'], paths['state'], paths['lock'].parent,
                 root / 'etc/systemd/system', root / 'proc']:
        path.mkdir(parents=True)
    release = paths['install'] / 'releases' / SOURCE
    release.mkdir(parents=True)
    (release / 'artifact-manifest.json').write_text(json.dumps({'commit': SOURCE, 'gitTree': 'c' * 40}))
    (release / 'reviewed-source').mkdir()
    (release / 'reviewed-source/.relay-source.json').write_text(json.dumps({'revision': SOURCE, 'tree': 'c' * 40}))
    (paths['install'] / 'current').symlink_to(release)
    (paths['install'] / 'relay-writer-controller').write_text('old managed wrapper\n')
    for name in ['runner', 'general-runner']:
        runner = paths['install'] / name
        runner.mkdir()
        (runner / '.runner').write_text('synthetic intended registration\n')
        (runner / '.credentials').write_text('synthetic protected registration credential\n')
        (runner / 'bin').mkdir()
        (runner / 'bin/Runner.Listener').write_text('synthetic retained runner\n')
    (paths['config'] / 'writer-private-key').write_text('synthetic external protected key\n')
    (paths['state'] / 'publication-v2.json').write_text('synthetic publication reservation\n')
    marker = paths['config'] / 'reviewer-activation-authorized'
    marker.write_text('authorized\n')
    marker.chmod(0o600)
    for name in reinstall.unit_names(config):
        content = ('Unit=' + name.removesuffix('.timer') + '.service' if name.endswith('.timer')
                   else 'ExecStart=/opt/codex-relay/current/bin/synthetic')
        identities = dict(zip(reinstall.unit_names(config)[2:5], [config['environment']['reviewerUser'],
                             config['environment']['runner']['user'], config['environment']['generalRunner']['user']]))
        if name in identities:
            content += '\nUser=' + identities[name]
        (root / 'etc/systemd/system' / name).write_text(content + '\n')
    user_ids = {name: os.getuid() for name in [config['consumer']['runtimeUser'],
                 config['environment']['runner']['user'], config['environment']['generalRunner']['user']]}
    # Tests normally run as the native Linux development user. Root can create
    # an equivalent isolated fixture without borrowing any host service user.
    if os.getuid() == 0:
        user_ids = {name: 65534 for name in user_ids}
        for name in ['runner', 'general-runner']:
            os.chown(paths['install'] / name, 65534, 65534)
    report = {'blockers': [], 'configuration': {'consumer': 'equivalent', 'deployment': 'equivalent'},
              'installed': {'status': 'present', 'revision': SOURCE}}
    return SimpleNamespace(config=config, root=root, paths=paths, report=report,
                           user_ids=user_ids, systemd=Systemd(config))


def run(value):
    return reinstall.decommission(value.config, TARGET, value.report, root=value.root,
                                 owner_uid=os.getuid(), user_ids=value.user_ids, runner=value.systemd)


def snapshot(path):
    metadata = path.stat()
    return path.read_bytes(), (metadata.st_dev, metadata.st_ino, metadata.st_mode,
                               metadata.st_uid, metadata.st_gid, metadata.st_mtime_ns)


def test_retirement_preserves_registration_credentials_and_durable_records(installation):
    value = installation
    preserved = [value.paths['config'] / 'writer-private-key', value.paths['state'] / 'publication-v2.json']
    preserved += [value.paths['install'] / name / leaf for name in ['runner', 'general-runner']
                  for leaf in ['.runner', '.credentials', 'bin/Runner.Listener']]
    before = {path: snapshot(path) for path in preserved}
    result = run(value)
    assert result['state'] == 'DECOMMISSIONED'
    assert result['journalSha256'] == hashlib.sha256(value.paths['journal'].read_bytes()).hexdigest()
    assert reinstall.validate_remote_result(result, value.config, TARGET, value.report, 'decommission') == result
    assert not (value.paths['install'] / 'current').exists()
    assert {path: snapshot(path) for path in preserved} == before
    journal = json.loads(value.paths['journal'].read_text())
    archive = value.root / journal['archive'].lstrip('/')
    assert (archive / 'runtime/releases' / SOURCE / 'artifact-manifest.json').is_file()
    assert (archive / 'runtime/relay-writer-controller').read_text() == 'old managed wrapper\n'
    assert (archive / 'reviewer-activation-authorized').read_text() == 'authorized\n'
    assert not (value.paths['config'] / 'reviewer-activation-authorized').exists()
    assert stat.S_IMODE(archive.stat().st_mode) == 0o700
    assert json.loads(value.paths['operation'].read_text()) == {
        'schemaVersion': '1', 'state': 'RECOVERY_REQUIRED', 'phase': 'apply', 'target_head': TARGET}


@pytest.mark.parametrize('change', ['consumer', 'deployment', 'blocker'])
def test_inventory_is_not_destruction_authority_when_intent_unproven(installation, change):
    value = installation
    if change == 'blocker':
        value.report['blockers'] = ['ambiguous-runner']
    else:
        value.report['configuration'][change] = 'different'
    with pytest.raises(ValueError, match='INVENTORY_NOT_PROVEN'):
        run(value)
    assert not value.paths['journal'].exists()
    assert (value.paths['install'] / 'current').is_symlink()
    assert not value.systemd.calls


def test_pre_current_snapshot_absence_uses_owner_config_with_visible_comparison_gap(installation):
    value = installation
    value.report['configuration']['deployment'] = 'unavailable'
    result = run(value)
    assert result['state'] == 'DECOMMISSIONED'
    assert json.loads(value.paths['journal'].read_text())['previousEnvironmentComparison'] == 'unavailable'


def test_new_unit_names_cannot_hide_old_namespace_services_without_snapshot(installation):
    value = installation
    value.report['configuration']['deployment'] = 'unavailable'
    value.config['environment']['instance'] = {'reviewerPort': 18787, 'publicationEnabled': False}
    with pytest.raises(ValueError, match='UNSUPPORTED_RUNTIME_UNIT'):
        run(value)
    assert not value.paths['journal'].exists()


def test_unknown_indirect_service_runtime_reference_blocks_retirement(installation):
    value = installation
    unit = value.root / 'etc/systemd/system/owner-sidecar.service'
    unit.write_text('ExecStart=/usr/bin/node /opt/codex-relay/current/sidecar.mjs\n')
    with pytest.raises(ValueError, match='UNSUPPORTED_RUNTIME_UNIT'):
        run(value)
    assert not value.paths['journal'].exists()


@pytest.mark.parametrize('unit_root', ['etc/systemd/system', 'usr/lib/systemd/system',
                                      'lib/systemd/system'])
@pytest.mark.parametrize('binding', ['ExecStart=/opt/codex-relay/current/sidecar',
                                   'ExecStart=/usr/bin/node /opt/codex-relay/current/sidecar'])
def test_unknown_symlinked_runtime_service_blocks_before_mutation(installation, unit_root, binding):
    value = installation
    target = value.root / unit_root / 'vendor.service'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(binding + '\n')
    link = value.root / 'etc/systemd/system/owner-sidecar.service'
    link.symlink_to('/' + str(target.relative_to(value.root)))
    with pytest.raises(ValueError, match='UNSUPPORTED_RUNTIME_UNIT'):
        run(value)
    assert not value.paths['journal'].exists()
    assert not value.systemd.calls


@pytest.mark.parametrize('usr_merge', [False, True])
def test_unrelated_symlink_chain_is_classified_without_retiring_it(installation, usr_merge):
    value = installation
    vendor = value.root / 'usr/lib/systemd/system'
    vendor.mkdir(parents=True)
    target = vendor / 'vendor.service'
    target.write_text('# /opt/codex-relay/comment\n; /opt/codex-relay/comment\nExecStart=/usr/bin/true\n')
    if usr_merge:
        (value.root / 'lib').symlink_to('usr/lib')
    alias = vendor / 'alias.service'
    alias.symlink_to('vendor.service')
    link = value.root / 'etc/systemd/system/owner-sidecar.service'
    link.symlink_to('/lib/systemd/system/alias.service' if usr_merge else '../../..//usr/lib/systemd/system/alias.service')
    result = run(value)
    assert result['state'] == 'DECOMMISSIONED'
    assert link.is_symlink() and target.exists()
    assert not any(name == link.name for _, name in value.systemd.calls)


@pytest.mark.parametrize('shape', ['dangling', 'outside', 'writable', 'directory', 'fifo',
                                  'cycle', 'directory-link', 'writable-directory', 'hardlink',
                                  'wrong-owner', 'wrong-link-owner'])
def test_unclassifiable_unknown_symlink_fails_closed_without_reading_target(installation, shape, monkeypatch):
    value = installation
    base = value.root / 'usr/lib/systemd/system'
    base.mkdir(parents=True)
    target = base / 'vendor.service'
    target.write_text('ExecStart=/opt/codex-relay/current/sidecar\n')
    link = value.root / 'etc/systemd/system/owner-sidecar.service'
    if shape == 'dangling':
        target.unlink()
    elif shape == 'outside':
        target = value.paths['config'] / 'writer-private-key'
    elif shape == 'writable':
        target.chmod(0o666)
    elif shape in ['directory', 'fifo']:
        target.unlink()
        target.mkdir() if shape == 'directory' else os.mkfifo(target)
    elif shape == 'cycle':
        target.unlink()
        target.symlink_to('vendor.service')
    elif shape == 'directory-link':
        alias = base / 'redirect'
        alias.symlink_to(base, target_is_directory=True)
        target = alias / 'vendor.service'
    elif shape == 'writable-directory':
        base.chmod(0o777)
    elif shape == 'hardlink':
        os.link(target, base / 'duplicate.service')
    link.symlink_to('/' + str(target.relative_to(value.root)))
    if shape in ['wrong-owner', 'wrong-link-owner']:
        original = Path.lstat
        invalid = target if shape == 'wrong-owner' else link
        def lstat(path, *args, **kwargs):
            result = original(path, *args, **kwargs)
            if path == invalid:
                values = list(result)
                values[4] = os.getuid() + 1
                return os.stat_result(values)
            return result
        monkeypatch.setattr(Path, 'lstat', lstat)
    original_open = os.open
    def guarded_open(path, *args, **kwargs):
        assert Path(path) != target, 'unsafe target was opened'
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(os, 'open', guarded_open)
    with pytest.raises(ValueError, match='UNKNOWN_UNIT_UNCLASSIFIABLE;inspect-top-level-systemd-service-links'):
        run(value)
    assert not value.paths['journal'].exists()
    assert not value.systemd.calls


@pytest.mark.skipif(os.geteuid() != 0, reason='synthetic device identity requires root')
def test_unknown_mask_is_classified_without_opening_device(installation, monkeypatch):
    value = installation
    device = value.root / 'dev/null'
    device.parent.mkdir()
    os.mknod(device, stat.S_IFCHR | 0o666, os.makedev(1, 3))
    link = value.root / 'etc/systemd/system/owner-mask.service'
    link.symlink_to('/dev/null')
    original_open = os.open
    def guarded_open(path, *args, **kwargs):
        assert Path(path) != device, 'mask device was opened'
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(os, 'open', guarded_open)
    assert run(value)['state'] == 'DECOMMISSIONED'
    assert link.is_symlink()


def test_missing_snapshot_never_admits_mismatched_source_identity(installation):
    value = installation
    value.report['configuration']['deployment'] = 'unavailable'
    identity = value.paths['install'] / 'releases' / SOURCE / 'reviewed-source/.relay-source.json'
    identity.write_text(json.dumps({'revision': TARGET, 'tree': 'c' * 40}))
    with pytest.raises(ValueError, match='INSTALLED_IDENTITY_UNPROVEN'):
        run(value)
    assert not value.paths['journal'].exists()


def test_existing_operation_or_journal_is_never_reset(installation):
    value = installation
    for path in [value.paths['operation'], value.paths['journal']]:
        path.write_text('unknown prior mutation\n')
        with pytest.raises(ValueError, match='RECOVERY_REQUIRED'):
            run(value)
        assert path.read_text() == 'unknown prior mutation\n'
        path.unlink()


def test_active_runner_blocks_before_any_mutation(installation):
    value = installation
    value.systemd.units[reinstall.unit_names(value.config)[3]] = 'active'
    with pytest.raises(ValueError, match='WORKERS_NOT_QUIESCENT'):
        run(value)
    assert not value.paths['journal'].exists()
    assert not any(operation == 'stop' for operation, _ in value.systemd.calls)


def test_surviving_worker_process_blocks_before_mutation(installation):
    value = installation
    process = value.root / 'proc/123'
    process.mkdir()
    if os.getuid() == 0:
        os.chown(process, 65534, 65534)
    with pytest.raises(ValueError, match='WORKERS_NOT_QUIESCENT'):
        run(value)
    assert not value.paths['journal'].exists()


def test_service_stop_failure_retains_durable_reservation_and_cannot_replay(installation):
    value = installation
    value.systemd.fail_stop = True
    with pytest.raises(ValueError, match='SERVICE_TRANSITION_FAILED'):
        run(value)
    assert value.paths['operation'].is_file()
    assert json.loads(value.paths['journal'].read_text())['stage'] == 'RESERVED'
    assert (value.paths['install'] / 'current').is_symlink()
    with pytest.raises(ValueError, match='RECOVERY_REQUIRED'):
        run(value)


def test_interruption_after_runtime_retirement_retains_all_bytes(installation, monkeypatch):
    value = installation
    original = reinstall.os.rename

    def interrupt(source, target):
        if source.name == 'runner':
            raise OSError('synthetic interrupt before runner restore')
        return original(source, target)

    monkeypatch.setattr(reinstall.os, 'rename', interrupt)
    with pytest.raises(OSError, match='synthetic interrupt'):
        run(value)
    journal = json.loads(value.paths['journal'].read_text())
    assert journal['stage'] == 'RUNTIME_RETIRED'
    archive = value.root / journal['archive'].lstrip('/')
    assert (archive / 'runtime/runner/.credentials').is_file()
    assert value.paths['operation'].is_file()
    with pytest.raises(ValueError, match='RECOVERY_REQUIRED'):
        run(value)


def test_busy_production_lock_prevents_reservation(installation):
    value = installation
    with value.paths['lock'].open('w') as lock:
        value.paths['lock'].chmod(0o600)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match='OPERATION_BUSY'):
            run(value)
    assert not value.paths['journal'].exists()


def test_protected_inputs_under_retired_runtime_are_rejected(installation):
    value = installation
    value.config['consumer']['paths']['credentialKeyFile'] = '/opt/codex-relay/private/key'
    with pytest.raises(ValueError, match='PROTECTED_STATE_OVERLAPS_RUNTIME'):
        run(value)
    assert not value.paths['journal'].exists()


def test_foreign_or_symlinked_unit_cannot_be_stopped(installation):
    value = installation
    unit = value.root / 'etc/systemd/system' / reinstall.unit_names(value.config)[2]
    unit.write_text('ExecStart=/opt/other/current/service\n')
    with pytest.raises(ValueError, match='UNIT_IDENTITY_UNPROVEN'):
        run(value)
    assert not value.paths['journal'].exists()
    unit.unlink()
    unit.symlink_to(value.paths['config'] / 'writer-private-key')
    with pytest.raises(ValueError, match='UNSAFE_PATH'):
        run(value)


def test_complete_needs_exact_fresh_install_and_cleared_operation(installation):
    value = installation
    run(value)
    with pytest.raises(ValueError, match='OPERATION_STILL_PENDING'):
        reinstall.complete(value.config, TARGET, root=value.root, owner_uid=os.getuid())
    value.paths['operation'].unlink()
    with pytest.raises(ValueError, match='FINAL_IDENTITY_UNPROVEN'):
        reinstall.complete(value.config, TARGET, root=value.root, owner_uid=os.getuid())
    release = value.paths['install'] / 'releases' / TARGET
    release.mkdir(parents=True)
    (release / 'artifact-manifest.json').write_text(json.dumps({key: TARGET for key in [
        'commit', 'installedRevision', 'resolvedRevision']}))
    (value.paths['install'] / 'current').symlink_to(release)
    result = reinstall.complete(value.config, TARGET, root=value.root, owner_uid=os.getuid())
    assert result['state'] == 'COMPLETE'
    assert not value.paths['journal'].exists()
    archive = value.root / result['archive'].lstrip('/')
    assert json.loads((archive / 'decommission.json').read_text())['stage'] == 'COMPLETE'


def test_retired_tree_is_admitted_as_fresh_by_existing_apply_gate(installation):
    value = installation
    run(value)
    spec = importlib.util.spec_from_file_location('reinstall_upgrade_gate',
             ROOT / 'deploy/ansible/scripts/verify_upgrade.py')
    upgrade = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(upgrade)
    assert upgrade.verify_apply(value.paths['install'], TARGET,
                                owner_uid=os.getuid(), boundary=value.root) == 'none'
    assert (value.paths['install'] / 'runner/.credentials').is_file()


@pytest.mark.skipif(os.geteuid() != 0 or not shutil.which('ansible-playbook'),
                    reason='root native Ansible required for protected operation-record composition')
def test_actual_operation_inspection_and_begin_accept_reinstall_reservation(installation):
    value = installation
    retired = run(value)
    before = snapshot(value.paths['operation'])
    variables = {
        'relay_deployment_profile': 'production',
        'relay_production_operation_phase': 'apply',
        'relay_production_operation_target_head': TARGET,
        'relay_production_operation_record_path': str(value.paths['operation']),
        'relay_production_operation_lock_path': str(value.paths['lock']),
        'relay_production_operation_schema_version': '1',
        'relay_local_apply_source': 'installed',
        'relay_installed_config_recovery_authorized': True,
        'relay_installed_config_reconcile': False,
        'relay_clean_reinstall_journal_sha256': retired['journalSha256'],
        'relay_installed_deployment_config': json.dumps(value.config),
        'relay_state_root': str(value.paths['state']),
    }
    tasks = [
        {'ansible.builtin.include_tasks': str(ROOT / 'deploy/ansible/tasks/production-operation-state.yml')},
        {'ansible.builtin.include_tasks': str(ROOT / 'deploy/ansible/tasks/production-operation-state-begin.yml')},
        {'ansible.builtin.assert': {'that': [
            'relay_production_operation_recovery_matching | bool',
            "relay_production_operation_active_phase == 'apply'",
            "relay_production_operation_active_head == '" + TARGET + "'",
        ]}},
    ]
    playbook = value.root / 'reinstall-apply-operation.yml'
    playbook.write_text(yaml.safe_dump([{'hosts': 'localhost', 'connection': 'local',
                         'gather_facts': False, 'vars': variables, 'tasks': tasks}]))
    result = subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(playbook)],
                            cwd=ROOT / 'deploy/ansible', capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert snapshot(value.paths['operation']) == before
    assert (value.paths['install'] / 'runner/.credentials').is_file()


def test_unknown_runtime_contents_are_retained_and_block_retirement(installation):
    value = installation
    unknown = value.paths['install'] / 'owner-state'
    unknown.mkdir()
    with pytest.raises(ValueError, match='UNSUPPORTED_RUNTIME_ENTRY'):
        run(value)
    assert unknown.is_dir()
    assert not value.paths['journal'].exists()


@pytest.mark.parametrize('field,replacement', [
    ('sourceRevision', 'c' * 40), ('targetRevision', SOURCE), ('journalSha256', 'A' * 64),
    ('journalSha256', ''), ('recoveryPath', '/var/lib/other-clean-reinstall.json'),
])
def test_transport_result_cannot_substitute_another_retirement(installation, field, replacement):
    value = installation
    result = run(value)
    result[field] = replacement
    with pytest.raises(ValueError, match='REMOTE_RESULT_INVALID'):
        reinstall.validate_remote_result(result, value.config, TARGET, value.report, 'decommission')


def test_transport_completion_must_bind_exact_installed_head_and_archive(installation):
    value = installation
    result = {'state': 'COMPLETE', 'installedRevision': TARGET,
              'archive': '/opt/.codex-relay-retired-' + SOURCE + '-' + TARGET}
    assert reinstall.validate_remote_result(result, value.config, TARGET, value.report, 'complete') == result
    for field, replacement in [('installedRevision', SOURCE), ('archive', '/opt/foreign')]:
        altered = {**result, field: replacement}
        with pytest.raises(ValueError, match='REMOTE_RESULT_INVALID'):
            reinstall.validate_remote_result(altered, value.config, TARGET, value.report, 'complete')


@pytest.mark.skipif(os.geteuid() != 0, reason='native root helper check')
def test_direct_credential_helper_refuses_pending_reinstall_before_creating_files(installation):
    value = installation
    value.paths['journal'].write_text('{"stage":"DECOMMISSIONED"}')
    template = ROOT / 'deploy/ansible/roles/relay_runtime/templates/relay-credential-provision.j2'
    helper = value.root / 'credential-helper.sh'
    helper.write_text(Environment().from_string(template.read_text()).render(
                      relay_state_root=str(value.paths['state']), relay_deployment_profile='production'))
    before = sorted(value.root.rglob('*'))
    result = subprocess.run(['/bin/sh', str(helper)], capture_output=True, text=True)
    assert result.returncode == 51
    assert 'CREDENTIAL_PROVISIONING_REINSTALL_RECOVERY_REQUIRED' in result.stdout
    assert sorted(value.root.rglob('*')) == before


@pytest.mark.skipif(not shutil.which('ansible-playbook'), reason='native Ansible required')
@pytest.mark.parametrize('shape', ['regular', 'symlink'])
def test_general_runner_gate_prevents_activation_after_apply_clears_its_record(installation, shape):
    value = installation
    if shape == 'regular':
        value.paths['journal'].write_text('{"stage":"DECOMMISSIONED"}')
    else:
        value.paths['journal'].symlink_to(value.root / 'missing-journal')
    source = yaml.safe_load((ROOT / 'deploy/ansible/relay-general-runner.yml').read_text())[0]['tasks']
    names = ['Inspect the outer clean-reinstall recovery boundary before general activation',
             'Refuse activation while clean reinstall still requires recovery']
    tasks = [next(task for task in source if task['name'] == name) for name in names]
    activated = value.root / 'activation-mutation'
    tasks.append({'ansible.builtin.file': {'path': str(activated), 'state': 'touch'}})
    playbook = value.root / 'general-runner-guard.yml'
    playbook.write_text(yaml.safe_dump([{'hosts': 'localhost', 'connection': 'local', 'gather_facts': False,
                         'vars': {'relay_state_root': str(value.paths['state'])}, 'tasks': tasks}]))
    result = subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(playbook)],
                            capture_output=True, text=True)
    assert result.returncode != 0
    assert 'GENERAL_RUNNER_CLEAN_REINSTALL_PENDING' in result.stdout
    assert not activated.exists()
