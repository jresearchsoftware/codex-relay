"""Native temporary-filesystem pool reinstall containment; no live services/API."""
import copy
import ast
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
from types import SimpleNamespace

import pytest

from test_clean_reinstall import SOURCE, TARGET, installation
from test_reinstall_recovery import snapshot
import clean_reinstall as reinstall
import ansible_transport

OPERATION = '11111111-2222-3333-4444-555555555555'


def pool(value, monkeypatch):
    value.config['consumer']['generalRunnerPool'] = {'desiredCapacity': 2}
    value.config['consumer']['executionSlots'] = [{'id': 'primary', 'runnerUser': value.config['environment']['generalRunner']['user'],
        'runtimeUser': value.config['consumer']['runtimeUser'], 'paths': value.config['consumer']['paths']}]
    value.user_ids[value.config['environment']['generalRunner']['user']] = 90000
    value.user_ids[value.config['consumer']['runtimeUser']] = 90001
    value.shared_root = value.root / 'opt/codex-relay-pools/shared-test/runners/primary'
    value.shared_root.mkdir(parents=True)
    (value.shared_root / '.runner').write_text('deterministic physical registration\n')
    (value.shared_root / '.credentials').write_text('deterministic physical registration fixture\n')
    value.pool_manifest = value.root / 'var/lib/codex-relay-pools/shared-test/pool.json'
    value.pool_manifest.parent.mkdir(parents=True)
    value.pool_manifest.write_text('{"members":{"primary":{"phase":"ready","runnerId":51}}}\n')
    value.systemd.process_root = value.root / 'proc'
    value.shared_processes = []
    for number, uid, cwd, executable, arguments in [
        (8123, 90000, '/opt/codex-relay-pools/shared-test/runners/primary',
         '/opt/codex-relay-pools/shared-test/runners/primary/bin/Runner.Listener', ['run']),
        (8124, 90001, '/var/lib/other-repository/work/run-123', '/opt/other-repository/codex-runtime/codex', ['exec'])]:
        process = value.root / 'proc' / str(number)
        process.mkdir()
        (process / 'cgroup').write_text('0::/system.slice/shared-test-pool-1.service\n')
        (process / 'status').write_text('Uid:\t' + '\t'.join([str(uid)] * 4) + '\nPPid:\t1\n')
        (process / 'cmdline').write_bytes(('\0'.join([executable, *arguments]) + '\0').encode())
        (process / 'cwd').symlink_to(cwd)
        (process / 'exe').symlink_to(executable)
        value.shared_processes.append(process)
    original_stat = Path.stat
    def stat(path, *args, **kwargs):
        info = original_stat(path, *args, **kwargs)
        if path in value.shared_processes:
            fields = list(info)
            fields[4] = 90000 if path.name == '8123' else 90001
            return os.stat_result(fields)
        return info
    monkeypatch.setattr(Path, 'stat', stat)
    (value.paths['config'] / 'consumer.json').write_text(json.dumps(value.config['consumer']))
    value.gate = {'phase': 'applying', 'operationId': OPERATION, 'target': TARGET, 'active': [], 'unknown': []}
    value.probes = []
    def probe(release, command, options):
        value.probes.append((release, command, options))
        return copy.deepcopy(value.gate)
    value.probe = probe
    return value


def retire(value, operation=OPERATION):
    return reinstall.decommission(value.config, TARGET, value.report, root=value.root, owner_uid=os.getuid(),
        user_ids=value.user_ids, runner=value.systemd, operation_id=operation, admission_probe=value.probe)


def continue_read(value, operation=OPERATION, config=None, revision=TARGET):
    return reinstall.continuation(config or value.config, revision, operation, root=value.root,
        owner_uid=os.getuid(), owner_gid=os.getgid(), admission_probe=value.probe)


def install_target(value):
    release = value.paths['install'] / 'releases' / TARGET
    (release / 'reviewed-source').mkdir(parents=True)
    (release / 'artifact-manifest.json').write_text(json.dumps({key: TARGET for key in ['commit', 'installedRevision', 'resolvedRevision']}
        | {'gitTree': 'd' * 40}))
    (release / 'reviewed-source/.relay-source.json').write_text(json.dumps({'revision': TARGET, 'tree': 'd' * 40}))
    (value.paths['install'] / 'current').symlink_to(release)


def test_namespace_reinstall_retains_shared_listener_registration_and_other_repository_model(installation, monkeypatch):
    value = pool(installation, monkeypatch)
    before = snapshot(value.shared_root), value.pool_manifest.read_bytes(), [snapshot(path) for path in value.shared_processes]
    result = retire(value)
    assert result['state'] == 'DECOMMISSIONED'
    assert (snapshot(value.shared_root), value.pool_manifest.read_bytes(), [snapshot(path) for path in value.shared_processes]) == before
    assert not any('shared-test' in name for action, name in value.systemd.calls)
    journal = json.loads(value.paths['journal'].read_bytes())
    assert journal['lifecycleOperation'] == OPERATION
    assert journal['runners'] == ['runner']
    assert all('pool-' not in name for name in journal['units'])
    assert len(value.probes) == 2


@pytest.mark.parametrize('damage', ['wrong-operation', 'open', 'active', 'unknown', 'target-process'])
def test_pool_retirement_refuses_unbound_gate_or_remaining_target_worker_before_mutation(installation, monkeypatch, damage):
    value = pool(installation, monkeypatch)
    if damage == 'wrong-operation':
        value.gate['operationId'] = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
    elif damage == 'open':
        value.gate['phase'] = 'open'
    elif damage in ['active', 'unknown']:
        value.gate[damage] = [123]
    else:
        process = value.shared_processes[1]
        (process / 'cwd').unlink()
        (process / 'cwd').symlink_to('/var/lib/codex-relay/work/run-123')
    with pytest.raises(ValueError):
        retire(value)
    assert not value.paths['journal'].exists() and not value.paths['operation'].exists()
    assert not any(action in ['stop', 'disable'] for action, _ in value.systemd.calls)


def test_exact_pending_continuation_preserves_journal_and_filters_only_original_records(installation, monkeypatch):
    value = pool(installation, monkeypatch)
    retire(value)
    value.gate['phase'] = 'recovery-required'
    before = value.paths['journal'].read_bytes(), value.paths['operation'].read_bytes()
    proof = continue_read(value)
    assert proof['completed'] is False
    assert proof['journalSha256'] == hashlib.sha256(before[0]).hexdigest()
    assert (value.paths['journal'].read_bytes(), value.paths['operation'].read_bytes()) == before
    report = {'blockers': [*proof['allowedInventoryBlockers'], 'runner-general-ambiguous', 'configuration-different']}
    filtered = reinstall.continuation_inventory(report, proof)
    assert filtered['blockers'] == ['runner-general-ambiguous', 'configuration-different']
    assert filtered['status'] == 'blocked' and len(report['blockers']) > len(filtered['blockers'])
    for operation, config, revision in [
        ('aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee', None, TARGET),
        (OPERATION, {**value.config, 'source': {'revision': 'c' * 40}}, TARGET), (OPERATION, None, 'e' * 40)]:
        with pytest.raises(ValueError):
            continue_read(value, operation, config, revision)


def test_completed_retirement_recovers_only_final_postcheck_resume_under_original_uuid(installation, monkeypatch):
    value = pool(installation, monkeypatch)
    retire(value)
    install_target(value)
    value.paths['operation'].unlink()  # normal successful apply retires its ordinary operation record
    value.gate.update(phase='verified', verifiedRevision=TARGET)
    result = reinstall.complete(value.config, TARGET, root=value.root, owner_uid=os.getuid(),
        operation_id=OPERATION, admission_probe=value.probe)
    assert result['state'] == 'COMPLETE'
    archive = value.root / result['archive'].lstrip('/')
    original = (archive / 'decommission.json').read_bytes()
    value.gate.update(phase='recovery-required', verifiedRevision=None)
    proof = continue_read(value)
    assert proof['completed'] is True and proof['journalSha256'] == '' and proof['allowedInventoryBlockers'] == []
    assert (archive / 'decommission.json').read_bytes() == original
    assert value.shared_root.exists() and all(path.exists() for path in value.shared_processes)
    with pytest.raises(ValueError):
        continue_read(value, 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee')


def test_pending_continuation_cannot_hide_surviving_target_process_behind_terminal_gate_records(installation, monkeypatch):
    value = pool(installation, monkeypatch)
    retire(value)
    value.gate['phase'] = 'recovery-required'
    process = value.shared_processes[1]
    (process / 'cwd').unlink()
    (process / 'cwd').symlink_to('/var/lib/codex-relay/work/run-123')
    before = value.paths['journal'].read_bytes()
    with pytest.raises(ValueError, match='NAMESPACE_PROCESS_PRESENT'):
        continue_read(value)
    assert value.paths['journal'].read_bytes() == before


def test_generated_pool_wrapper_and_admission_adapter_parse_without_execution(monkeypatch):
    captured = []
    class Prepared(Exception):
        pass
    def capture(_target, _key, command, **kwargs):
        captured.append(command[-1])
        raise Prepared
    config = {'consumer': {'generalRunnerPool': {'desiredCapacity': 2}, 'paths': {'claimRoot': '/var/lib/codex-relay/claims'}},
              'environment': {'namespace': 'codex-relay'}}
    with monkeypatch.context() as local:
        local.setattr(ansible_transport, 'TargetProcess', capture)
        for action in ['decommission', 'continuation', 'continue', 'complete']:
            with pytest.raises(Prepared):
                reinstall.remote_action({'user': 'owner', 'host': 'test.invalid'}, '/private/key', config, TARGET,
                                         action=action, operation_id=OPERATION)
            compile(captured[-1], '<generated-read-only-test>', 'exec')
    # Execute only the actual generated callback with a recording subprocess
    # capability. It builds JS but cannot read files, SSH or run a service.
    definition = next(node for node in ast.walk(ast.parse(captured[-1]))
                      if isinstance(node, ast.FunctionDef) and node.name == 'pool_admission_probe')
    calls = []
    def record(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout='{}')
    scope = {'value': {'config': config}, 'Path': Path, 'json': json,
             'subprocess': SimpleNamespace(run=record), 'require': reinstall.require,
             '_recovery_json': reinstall._recovery_json}
    exec(compile(ast.Module(body=[definition], type_ignores=[]), '<actual-generated-callback>', 'exec'), scope)
    scope['pool_admission_probe'](Path('/opt/retained-exact-release'), 'status', {'operationId': OPERATION})
    actual_js = calls[0][calls[0].index('-e') + 1]
    assert '__REINSTALL_SOURCE_BASE__' not in actual_js
    assert '/opt/retained-exact-release/reviewed-source/' in actual_js
    parsed = subprocess.run(['node', '--check', '--input-type=module'], input=actual_js, text=True, capture_output=True)
    assert parsed.returncode == 0, parsed.stderr
