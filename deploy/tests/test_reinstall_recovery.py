"""Explicit interrupted-reinstall disposition preserves evidence and authority."""
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_clean_reinstall import SOURCE, TARGET, installation, run
import clean_reinstall as reinstall


def snapshot(path):
    result = {}
    for entry in [path, *sorted(path.rglob('*'))]:
        info = entry.lstat()
        content = os.readlink(entry) if entry.is_symlink() else entry.read_bytes() if entry.is_file() else None
        result[str(entry.relative_to(path))] = (content, info.st_dev, info.st_ino, info.st_mode,
            info.st_uid, info.st_gid, info.st_nlink, info.st_mtime_ns)
    return result


def root_process_identity(process, monkeypatch):
    original = Path.stat
    def stat(path, *args, **kwargs):
        info = original(path, *args, **kwargs)
        if path == process:
            values = list(info)
            values[4] = 0
            return os.stat_result(values)
        return info
    monkeypatch.setattr(Path, 'stat', stat)


def partial(value):
    run(value)
    journal = json.loads(value.paths['journal'].read_bytes())
    value.archive = value.root / journal['archive'].lstrip('/')
    release = value.paths['install'] / 'releases' / TARGET
    (release / 'reviewed-source').mkdir(parents=True)
    config_raw = (json.dumps(value.config, sort_keys=True) + '\n').encode()
    (release / 'deployment-config.json').write_bytes(config_raw)
    (release / 'deployment-config.json').chmod(0o600)
    value.manifest = {key: TARGET for key in ['commit', 'installedRevision', 'resolvedRevision']}
    value.manifest.update(gitTree='d' * 40, deploymentConfigSha256=hashlib.sha256(config_raw).hexdigest())
    (release / 'artifact-manifest.json').write_text(json.dumps(value.manifest))
    (release / 'reviewed-source/.relay-source.json').write_text(json.dumps({'revision': TARGET, 'tree': 'd' * 40}))
    (value.paths['install'] / 'current').symlink_to(release)
    (value.paths['config'] / 'consumer.json').write_text(json.dumps(value.config['consumer']))
    (value.paths['install'] / 'relay-admission').write_text('synthetic read-only admission wrapper\n')
    value.systemd.units[reinstall.unit_names(value.config)[0]] = 'active'
    value.admission = {'phase': 'open', 'active': [], 'unknown': []}
    value.probes = 0
    return value


def recover(value, **kwargs):
    def probe():
        value.probes += 1
        return value.admission
    return reinstall.recover(value.config, TARGET, root=value.root, owner_uid=os.getuid(),
        owner_gid=os.getgid(), user_ids=value.user_ids, runner=value.systemd,
        admission_probe=probe, **kwargs)


def evidence(value):
    return value.paths['journal'].read_bytes(), value.paths['operation'].read_bytes()


def test_disposition_preserves_original_bytes_state_and_activation_authority(installation):
    value = partial(installation)
    journal_raw, operation_raw = evidence(value)
    old_runtime = snapshot(value.archive / 'runtime')
    registration = [snapshot(value.paths['install'] / name) for name in ['runner', 'general-runner']]
    config_state = snapshot(value.paths['config']), snapshot(value.paths['state'])
    value.systemd.calls.clear()
    result = recover(value)
    assert result == {'state': 'DISPOSITIONED', 'sourceRevision': SOURCE, 'targetRevision': TARGET,
        'archive': '/' + str(value.archive.relative_to(value.root)),
        'journalSha256': hashlib.sha256(journal_raw).hexdigest(),
        'operationSha256': hashlib.sha256(operation_raw).hexdigest(),
        'units': json.loads(journal_raw)['units'], 'activationMarkers': ['reviewer-activation-authorized'],
        'runners': ['runner', 'general-runner']}
    assert (value.archive / 'recovery-journal.json').read_bytes() == journal_raw
    assert (value.archive / 'failed-apply.json').read_bytes() == operation_raw
    assert not value.paths['journal'].exists() and not value.paths['operation'].exists()
    assert snapshot(value.archive / 'runtime') == old_runtime
    assert [snapshot(value.paths['install'] / name) for name in ['runner', 'general-runner']] == registration
    assert (snapshot(value.paths['config']), snapshot(value.paths['state'])) == config_state
    assert [(action, name) for action, name in value.systemd.calls if action != 'show'] == [
        ('stop', reinstall.unit_names(value.config)[0])]
    assert value.probes == 2
    assert value.admission == {'phase': 'open', 'active': [], 'unknown': []}
    assert reinstall.validate_remote_result(result, value.config, TARGET, None, 'recover') == result
    with pytest.raises(OSError):
        recover(value)


@pytest.mark.parametrize('damage', ['schema', 'stage', 'target', 'config', 'source', 'archive',
                                  'units', 'runners', 'markers', 'duplicate', 'oversize', 'extra'])
def test_invalid_journal_fails_before_service_mutation(installation, damage):
    value = partial(installation)
    journal = json.loads(value.paths['journal'].read_bytes())
    if damage == 'schema':
        journal['schemaVersion'] = True
    elif damage == 'stage':
        journal['stage'] = 'RUNTIME_RETIRED'
    elif damage == 'target':
        journal['targetRevision'] = 'e' * 40
    elif damage == 'config':
        journal['configurationSha256'] = '0' * 64
    elif damage == 'source':
        journal['sourceRevision'] = '../foreign'
    elif damage == 'archive':
        journal['archive'] = '/opt/foreign'
    elif damage == 'units':
        journal['units']['unrelated.service'] = 'inactive'
    elif damage == 'runners':
        journal['runners'] = ['runner', 'runner']
    elif damage == 'markers':
        journal['activationMarkers'] = ['foreign-marker']
    elif damage == 'extra':
        journal['serviceTransition'] = {'unit': 'foreign.service', 'action': 'stop'}
    raw = (b'{"stage":"DECOMMISSIONED","stage":"RESERVED"}' if damage == 'duplicate' else
           b'x' * (reinstall.RECOVERY_LIMIT + 1) if damage == 'oversize' else json.dumps(journal).encode())
    value.paths['journal'].write_bytes(raw)
    before = evidence(value)
    value.systemd.calls.clear()
    with pytest.raises((ValueError, OSError)):
        recover(value)
    assert evidence(value) == before
    assert not any(action == 'stop' for action, _ in value.systemd.calls)
    assert not (value.archive / 'recovery-journal.json').exists()


@pytest.mark.parametrize('damage', ['record', 'record-schema', 'record-extra', 'next', 'journal-mode',
                                  'operation-mode', 'hardlink', 'symlink', 'archive-collision',
                                  'manifest', 'source-identity', 'snapshot-hash', 'snapshot-config',
                                  'consumer', 'archive-identity', 'activation', 'runner-binding'])
def test_untrusted_or_changed_runtime_and_evidence_block_disposition(installation, damage):
    value = partial(installation)
    release = value.paths['install'] / 'releases' / TARGET
    if damage.startswith('record'):
        record = json.loads(value.paths['operation'].read_bytes())
        if damage == 'record':
            record['target_head'] = 'e' * 40
        elif damage == 'record-schema':
            record['schemaVersion'] = 1
        else:
            record['extra'] = True
        value.paths['operation'].write_text(json.dumps(record))
    elif damage == 'next':
        value.paths['journal'].with_name(value.paths['journal'].name + '.next').write_text('unknown transition')
    elif damage in ['journal-mode', 'operation-mode']:
        value.paths['journal' if damage == 'journal-mode' else 'operation'].chmod(0o644)
    elif damage == 'hardlink':
        os.link(value.paths['journal'], value.paths['journal'].with_name('alias'))
    elif damage == 'symlink':
        saved = value.paths['journal'].with_name('saved')
        value.paths['journal'].rename(saved)
        value.paths['journal'].symlink_to(saved)
    elif damage == 'archive-collision':
        (value.archive / 'failed-apply.json').write_text('prior evidence')
    elif damage == 'manifest':
        value.manifest['gitTree'] = 'e' * 40
        (release / 'artifact-manifest.json').write_text(json.dumps(value.manifest))
    elif damage == 'source-identity':
        (release / 'reviewed-source/.relay-source.json').write_text(json.dumps({'revision': 'e' * 40, 'tree': 'd' * 40}))
    elif damage in ['snapshot-hash', 'snapshot-config']:
        raw = json.dumps({**value.config, 'changed': True}).encode()
        (release / 'deployment-config.json').write_bytes(raw)
        if damage == 'snapshot-config':
            value.manifest['deploymentConfigSha256'] = hashlib.sha256(raw).hexdigest()
            (release / 'artifact-manifest.json').write_text(json.dumps(value.manifest))
    elif damage == 'consumer':
        (value.paths['config'] / 'consumer.json').write_text('{}')
    elif damage == 'archive-identity':
        (value.archive / 'runtime/releases' / SOURCE / 'reviewed-source/.relay-source.json').write_text('{}')
    elif damage == 'activation':
        marker = value.paths['config'] / 'reviewer-activation-authorized'
        marker.write_text('authorized\n')
        marker.chmod(0o600)
    else:
        (value.archive / 'runtime/runner').mkdir()
    before = evidence(value)
    value.systemd.calls.clear()
    with pytest.raises((ValueError, OSError, KeyError)):
        recover(value)
    assert evidence(value) == before
    assert not any(action == 'stop' for action, _ in value.systemd.calls)


@pytest.mark.parametrize('damage', ['admission-active', 'admission-unknown', 'admission-malformed',
                                  'active-service', 'root-cgroup-child', 'namespace-backend'])
def test_uncontained_execution_blocks_before_timer_stop(installation, damage, monkeypatch):
    value = partial(installation)
    if damage.startswith('admission'):
        value.admission = ({'phase': 'open', 'active': [1], 'unknown': []} if damage == 'admission-active' else
                           {'phase': 'open', 'active': [], 'unknown': [1]} if damage == 'admission-unknown' else {})
    elif damage == 'active-service':
        value.systemd.units[reinstall.unit_names(value.config)[2]] = 'active'
    else:
        process = value.root / 'proc/567'
        process.mkdir()
        (process / 'status').write_text('Uid:\t0\t0\t0\t0\n')
        (process / 'cgroup').write_text('0::/system.slice/' + (
            reinstall.unit_names(value.config)[2] + '/child' if damage == 'root-cgroup-child' else 'foreign.service') + '\n')
        (process / 'cmdline').write_bytes(b'/usr/bin/python3\0/opt/codex-relay/current/deploy/relay-deploy.py\0')
        (process / 'cwd').symlink_to('/root')
        (process / 'exe').symlink_to('/usr/bin/python3')
        root_process_identity(process, monkeypatch)
    before = evidence(value)
    value.systemd.calls.clear()
    with pytest.raises(ValueError):
        recover(value)
    assert evidence(value) == before
    assert not any(action == 'stop' for action, _ in value.systemd.calls)


def test_foreign_canary_prefix_and_service_are_preserved(installation, monkeypatch):
    value = partial(installation)
    process = value.root / 'proc/567'
    process.mkdir()
    (process / 'status').write_text('Uid:\t0\t0\t0\t0\n')
    (process / 'cgroup').write_text('0::/system.slice/codex-relay-canary-general-runner.service\n')
    (process / 'cmdline').write_bytes(b'/opt/codex-relay-canary/general-runner/bin/Runner.Listener\0run\0')
    (process / 'cwd').symlink_to('/opt/codex-relay-canary/general-runner')
    (process / 'exe').symlink_to('/opt/codex-relay-canary/general-runner/bin/Runner.Listener')
    root_process_identity(process, monkeypatch)
    before = snapshot(process)
    assert recover(value)['state'] == 'DISPOSITIONED'
    assert snapshot(process) == before


@pytest.mark.parametrize('failure', ['timer-stop', 'archive-write', 'archive-fsync', 'journal-retirement',
                                    'operation-retirement'])
def test_interruption_retains_durable_evidence_and_replay_is_fail_closed(installation, monkeypatch, failure):
    value = partial(installation)
    journal_raw, operation_raw = evidence(value)
    if failure == 'timer-stop':
        value.systemd.fail_stop = True
    elif failure == 'archive-write':
        original = reinstall._archive_recovery_bytes
        def interrupt(path, raw):
            if path.name == 'failed-apply.json':
                raise OSError('synthetic archive interruption')
            return original(path, raw)
        monkeypatch.setattr(reinstall, '_archive_recovery_bytes', interrupt)
    elif failure == 'archive-fsync':
        original = reinstall.fsync_dir
        def interrupt(path):
            if path == value.archive:
                raise OSError('synthetic archive fsync failure')
            return original(path)
        monkeypatch.setattr(reinstall, 'fsync_dir', interrupt)
    else:
        original = Path.unlink
        def interrupt(path, *args, **kwargs):
            if path == value.paths['journal' if failure == 'journal-retirement' else 'operation']:
                raise OSError('synthetic retirement interruption')
            return original(path, *args, **kwargs)
        monkeypatch.setattr(Path, 'unlink', interrupt)
    with pytest.raises((ValueError, OSError)):
        recover(value)
    assert value.paths['operation'].read_bytes() == operation_raw
    retained = value.paths['journal'] if value.paths['journal'].exists() else value.archive / 'recovery-journal.json'
    assert retained.read_bytes() == journal_raw
    with pytest.raises((ValueError, OSError)):
        recover(value)


def test_newer_reinstall_after_disposition_creates_separate_target_evidence(installation):
    value = partial(installation)
    original_journal, original_operation = evidence(value)
    recover(value)
    newer = 'e' * 40
    report = {'blockers': [], 'configuration': {'consumer': 'equivalent', 'deployment': 'equivalent'},
              'installed': {'status': 'present', 'revision': TARGET}}
    retired = reinstall.decommission(value.config, newer, report, root=value.root,
        owner_uid=os.getuid(), user_ids=value.user_ids, runner=value.systemd)
    assert retired['targetRevision'] == newer and retired['sourceRevision'] == TARGET
    assert json.loads(value.paths['journal'].read_bytes())['targetRevision'] == newer
    assert json.loads(value.paths['operation'].read_bytes())['target_head'] == newer
    assert (value.archive / 'recovery-journal.json').read_bytes() == original_journal
    assert (value.archive / 'failed-apply.json').read_bytes() == original_operation


def test_default_admission_helper_is_read_only_and_failure_blocks(installation):
    value = partial(installation)
    calls = []
    def runner(arguments, **kwargs):
        if arguments[0].endswith('/relay-admission'):
            calls.append(arguments)
            return SimpleNamespace(returncode=0, stdout=json.dumps(value.admission))
        return value.systemd(arguments, **kwargs)
    result = reinstall.recover(value.config, TARGET, root=value.root, owner_uid=os.getuid(),
        owner_gid=os.getgid(), user_ids=value.user_ids, runner=runner)
    assert result['state'] == 'DISPOSITIONED'
    assert calls == [[str(value.paths['install'] / 'relay-admission'), 'status']] * 2
