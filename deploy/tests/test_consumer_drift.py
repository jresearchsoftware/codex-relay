"""Original-context repair owns real files/locks, never rewrites gate evidence."""
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
import consumer_drift as drift
from test_clean_reinstall import installation, SOURCE, TARGET

OPERATION = '12345678-1234-1234-1234-123456789abc'
digest = lambda raw: hashlib.sha256(json.dumps(json.loads(raw), sort_keys=True).encode()).hexdigest()


@pytest.fixture
def context(installation):
    value = installation
    value.config['consumer']['paths']['claimRoot'] = str(value.paths['state'] / 'writer-claims')
    claims = Path(value.config['consumer']['paths']['claimRoot'])
    claims.mkdir()
    lock = claims / 'publication-v2.lock'
    lock.write_bytes(b'')
    lock.chmod(0o600)
    desired = copy.deepcopy(value.config['consumer'])
    desired['defaultProfile']['effort'] = 'xhigh'
    value.config['consumer'] = copy.deepcopy(desired)
    actual = copy.deepcopy(desired)
    actual['defaultProfile']['effort'] = 'medium'
    consumer = value.paths['config'] / 'consumer.json'
    consumer.write_text(json.dumps(actual))
    consumer.chmod(0o644)
    release = value.paths['install'] / 'current'
    for name in ['controller/src/admission-cli.mjs', 'consumer/consumer-config.mjs']:
        path = release / 'reviewed-source' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('// installed fixture module\n')
    gate = {'version': 1, 'consumerDigest': digest(json.dumps(desired)), 'phase': 'open',
            'operationId': None, 'target': None, 'previousActive': None, 'verifiedRevision': None}
    gate_path = claims / 'admission-v1.json'
    gate_path.write_text(json.dumps(gate))
    gate_path.chmod(0o600)
    record = claims / 'original-attempt.json'
    record.write_bytes(b'original immutable attempt and publication evidence\n')
    record.chmod(0o600)
    value.consumer, value.desired, value.claims = consumer, desired, claims
    value.gate, value.gate_path, value.record, value.lock = gate, gate_path, record, lock
    value.bad = consumer.read_bytes()
    value.calls, value.fail, value.unknown = [], None, []
    return value


def execute(value, argv, env):
    with value.lock.open('rb') as stream:
        with pytest.raises(BlockingIOError):
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    assert env['RELAY_CONSUMER_CONFIG'] == str(value.consumer)
    value.calls.append(argv)
    if '--input-type=module' in argv:
        assert argv[-2].endswith('/consumer/consumer-config.mjs')
        return {'digest': digest(Path(argv[-1]).read_bytes())}
    assert argv[:5] == ['/usr/bin/unshare', '--mount', '--propagation', 'private', '--']
    assert argv[11] == str(value.consumer)
    staged = Path(argv[10])
    assert staged.parent == value.paths['config'] and stat.S_IMODE(staged.stat().st_mode) == 0o644
    assert value.consumer.read_bytes() == value.bad, 'host consumer must stay untouched during private-view CLI'
    assert value.record.read_bytes() == b'original immutable attempt and publication evidence\n'
    assert hashlib.sha256(staged.read_bytes()).hexdigest() == argv[12]
    arguments = argv[15:]
    if value.fail == arguments[0]:
        raise ValueError('CONSUMER_DRIFT_PRIVATE_MOUNT_VIEW_UNPROVEN')
    if arguments == ['status']:
        return {**value.gate, 'active': [], 'unknown': value.unknown}
    assert arguments == ['quiesce', '--operation', OPERATION, '--target', TARGET]
    value.gate.update(phase='quiesced', operationId=OPERATION, target=TARGET)
    value.gate_path.write_text(json.dumps(value.gate))
    return value.gate


def restore(value):
    return drift.restore(value.config, value.desired, TARGET, OPERATION, root=value.root,
        owner_uid=os.geteuid(), execute=lambda argv, env: execute(value, argv, env))


@pytest.mark.parametrize('migrated,private_umask', [(False, False), (True, False), (True, True)])
def test_original_context_quiesces_in_private_view_before_host_restore(context, migrated, private_umask):
    value = context
    if migrated:
        receipt = value.paths['config'] / 'serial-pool-compat-v1.json'
        receipt.write_bytes(b'unchanged original serial compatibility receipt\n')
        value.gate_path.rename(value.claims / 'admission-pool-v1.json')
        value.gate_path = value.claims / 'admission-pool-v1.json'
    before_record = value.record.read_bytes()
    previous = os.umask(0o077) if private_umask else None
    try:
        result = restore(value)
    finally:
        if previous is not None:
            os.umask(previous)
    assert result == {'status': 'restored', 'operationId': OPERATION}
    assert digest(value.consumer.read_bytes()) == value.gate['consumerDigest']
    assert value.gate['phase'] == 'quiesced' and value.gate['operationId'] == OPERATION
    backup = value.paths['config'] / ('consumer-drift-before-' + OPERATION + '.json')
    assert backup.read_bytes() == value.bad and stat.S_IMODE(backup.stat().st_mode) == 0o600
    assert stat.S_IMODE(value.consumer.stat().st_mode) == 0o644
    assert value.record.read_bytes() == before_record
    if migrated:
        assert receipt.read_bytes() == b'unchanged original serial compatibility receipt\n'
    assert [call[15] for call in value.calls if call[0] == '/usr/bin/unshare'] == ['status', 'quiesce']
    assert not list(value.paths['config'].glob('.consumer-drift-*.context.json'))


def test_healthy_current_context_allows_new_git_policy_without_namespace_or_digest_equality_gate(context):
    value = context
    value.consumer.write_text(json.dumps(value.desired))
    value.desired['defaultProfile']['effort'] = 'low'
    assert restore(value) == {'status': 'unchanged', 'operationId': None}
    assert not any(call[0] == '/usr/bin/unshare' for call in value.calls)
    assert not list(value.paths['config'].glob('consumer-drift-before-*'))


def test_future_policy_plus_unknown_drift_does_not_invent_original_context(context):
    value = context
    value.desired['defaultProfile']['effort'] = 'low'
    before = value.gate_path.read_bytes()
    with pytest.raises(ValueError, match='ORIGINAL_CONTEXT_UNPROVEN'):
        restore(value)
    assert value.consumer.read_bytes() == value.bad and value.gate_path.read_bytes() == before
    assert not any(call[0] == '/usr/bin/unshare' for call in value.calls)


@pytest.mark.parametrize('malformed', [False, True])
def test_known_protected_snapshot_restores_original_context_before_new_git_policy(context, malformed):
    value = context
    snapshot = copy.deepcopy(value.config)
    release = value.paths['install'] / 'current'
    raw = json.dumps(snapshot).encode()
    (release / 'deployment-config.json').write_bytes(raw)
    (release / 'deployment-config.json').chmod(0o600)
    manifest = release / 'artifact-manifest.json'
    metadata = json.loads(manifest.read_text())
    metadata['deploymentConfigSha256'] = hashlib.sha256(raw).hexdigest()
    manifest.write_text(json.dumps(metadata))
    value.desired['defaultProfile']['effort'] = 'low'
    value.config['consumer']['defaultProfile']['effort'] = 'low'
    if malformed:
        value.consumer.write_bytes(b'{broken manual JSON')
        value.bad = value.consumer.read_bytes()
    result = restore(value)
    assert result == {'status': 'restored', 'operationId': OPERATION}
    assert json.loads(value.consumer.read_bytes()) == snapshot['consumer']
    assert value.config['consumer']['defaultProfile']['effort'] == 'low'
    assert (release / 'deployment-config.json').read_bytes() == raw
    assert (value.paths['config'] / ('consumer-drift-before-' + OPERATION + '.json')).read_bytes() == value.bad


def test_existing_root_backup_can_prove_original_context_without_snapshot(context):
    value = context
    original = json.dumps(value.desired).encode()
    backup = value.paths['config'] / 'consumer-before-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa.json'
    backup.write_bytes(original)
    backup.chmod(0o600)
    value.desired['defaultProfile']['effort'] = 'low'
    value.config['consumer']['defaultProfile']['effort'] = 'low'
    assert restore(value)['status'] == 'restored'
    assert value.consumer.read_bytes() == original and backup.read_bytes() == original


def test_unbound_snapshot_is_evidence_only_and_cannot_supply_original_context(context):
    value = context
    snapshot = value.paths['install'] / 'current/deployment-config.json'
    snapshot.write_text(json.dumps(value.config))
    snapshot.chmod(0o600)
    value.desired['defaultProfile']['effort'] = 'low'
    before_gate = value.gate_path.read_bytes()
    with pytest.raises(ValueError, match='ORIGINAL_CONTEXT_UNPROVEN'):
        restore(value)
    assert value.consumer.read_bytes() == value.bad and value.gate_path.read_bytes() == before_gate


def test_original_source_renderer_preserves_owning_template_order():
    from managed_pool_transport import projected_consumer
    config = json.loads((ROOT / 'deploy/example.json').read_text())
    rendered = drift._render_original(config, ROOT)
    assert json.dumps(rendered) == json.dumps(projected_consumer(config, ROOT))


@pytest.mark.parametrize('explicit_defaults', [False, True])
def test_canonical_managed_snapshot_replays_owning_loader_before_template(explicit_defaults):
    """A real sorted deployment snapshot must reproduce the original Node ABI.

    The fresh Git entrypoint validates/rederives all 32 slots before compiling
    inventory, then independently writes a recursively sorted config snapshot.
    Rendering that snapshot as an already-compiled dict keeps every value but
    changes nested insertion order and therefore the authentic admission digest.
    """
    from config import loads
    from managed_pool_transport import consumer_digest, projected_consumer
    from test_managed_pool import inputs

    original = inputs(2)
    original['environment']['localApply'] = {
        'source': 'git', 'repository': 'example-org/private-deployment', 'configPath': 'test/relay.json'}
    original['environment']['reviewerRepositories'] = ['example-org/sample-project', 'example-org/another-project']
    if explicit_defaults:
        original['consumer']['defaultProfile']['effort'] = 'xhigh'
        original['consumer']['workGroup'] = original['environment']['codexWorkGroup']
    else:
        original['consumer']['defaultProfile'].pop('effort', None)
        original['consumer'].pop('workGroup', None)
    original = loads(json.dumps(original), ROOT)
    # The ordinary Git primitive repeats validation after canonicalizing input.
    original = loads(json.dumps(original, sort_keys=True, separators=(',', ':')), ROOT)
    assert len(original['consumer']['executionSlots']) == 32
    installed = projected_consumer(original, ROOT)  # Actual Ansible template.
    authentic_digest = consumer_digest(installed, ROOT)  # Actual owning Node validator/digest.
    canonical = json.dumps(original, sort_keys=True, separators=(',', ':'), ensure_ascii=False) + '\n'
    snapshot = json.loads(canonical)
    future = copy.deepcopy(original)
    future['consumer']['defaultProfile']['effort'] = 'medium'
    future['environment']['reviewerRepositories'] = ['example-org/sample-project']
    future_before = copy.deepcopy(future)

    direct = projected_consumer(snapshot, ROOT)
    assert direct == installed, 'the failure is order, not a changed resource or policy value'
    assert consumer_digest(direct, ROOT) != authentic_digest
    assert list(direct['executionSlots'][0]) != list(installed['executionSlots'][0])
    assert list(direct['executionSlots'][0]['paths']) != list(installed['executionSlots'][0]['paths'])

    restored = drift._render_original(snapshot, ROOT)
    assert json.dumps(restored) == json.dumps(installed)
    assert consumer_digest(restored, ROOT) == authentic_digest
    assert restored['defaultProfile'].get('effort', 'xhigh') == 'xhigh'
    assert snapshot == json.loads(canonical) and future == future_before
    requested = copy.deepcopy(installed)
    requested['defaultProfile']['effort'] = future['consumer']['defaultProfile']['effort']
    assert consumer_digest(requested, ROOT) != authentic_digest


def test_target_termination_reaps_private_child_process_group(tmp_path):
    child_pid = tmp_path / 'child-pid'
    child = ('import os,time;from pathlib import Path;'
             'Path(' + repr(str(child_pid)) + ').write_text(str(os.getpid()));time.sleep(60)')
    program = ('import sys;sys.path.insert(0,' + repr(str(ROOT / 'deploy')) + ');'
        'import consumer_drift as d;d.install_interrupt_handlers();'
        'd._execute(' + repr(['/usr/bin/python3', '-c', child]) + ',{"PATH":"/usr/bin:/bin"})')
    process = subprocess.Popen(['/usr/bin/python3', '-c', program],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
    try:
        deadline = time.monotonic() + 5
        while not child_pid.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert child_pid.exists(), process.communicate(timeout=5)
        process.send_signal(signal.SIGTERM)
        output, errors = process.communicate(timeout=5)
        assert process.returncode != 0 and b'CONSUMER_DRIFT_INTERRUPTED' in errors
        assert not Path('/proc/' + child_pid.read_text()).exists()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_prepare_transports_only_selected_bounded_source_and_same_operation(context, monkeypatch):
    import ansible_transport
    import managed_pool_transport
    guard = SimpleNamespace(poll=lambda: None)
    calls = []
    monkeypatch.setattr(managed_pool_transport, 'projected_consumer', lambda config: context.desired)
    class Process:
        returncode = 0
        def __init__(self, target, key, argv):
            assert target == {'connection': 'local'} and key == 'unused'
            assert argv[:3] == ['/usr/bin/python3', '-I', '-c']
            compile(argv[3], '<selected-bootstrap>', 'exec')
            assert 'install_interrupt_handlers()' in argv[3]
        def communicate(self, input, timeout):
            assert timeout == 1 and len(input.encode()) <= 524288
            value = json.loads(input)
            assert value['config'] == context.config and value['desired'] == context.desired
            assert value['operation'] == OPERATION and value['revision'] == TARGET
            assert set(value['sources']) == {'consumer_drift', 'clean_reinstall', 'publish_git_consumer'}
            for name, source in value['sources'].items():
                compile(source, name, 'exec')
            assert 'def prove_consumer_resources' in value['sources']['clean_reinstall']
            calls.append(value)
            return json.dumps({'status': 'unchanged', 'operationId': None}), ''
        def poll(self):
            return 0
    monkeypatch.setattr(ansible_transport, 'TargetProcess', Process)
    assert drift.prepare({'connection': 'local'}, 'unused', context.config, TARGET, OPERATION,
                         guard, guard) == {'status': 'unchanged', 'operationId': None}
    assert len(calls) == 1
    with pytest.raises(ValueError, match='HOST_MUTEX_LOST'):
        drift.prepare({'connection': 'local'}, 'unused', context.config, TARGET, OPERATION,
                      SimpleNamespace(poll=lambda: 1), guard)
    assert len(calls) == 1


@pytest.mark.parametrize('failure', ['status', 'quiesce', 'unknown', 'prior-operation', 'resource', 'alias'])
def test_unknown_or_failed_context_preserves_host_consumer_and_original_records(context, failure):
    value = context
    if failure in ['status', 'quiesce']:
        value.fail = failure
    elif failure == 'unknown':
        value.unknown = [17]
    elif failure == 'prior-operation':
        value.gate['phase'], value.gate['operationId'], value.gate['target'] = 'quiesced', OPERATION, TARGET
        value.gate_path.write_text(json.dumps(value.gate))
    elif failure == 'resource':
        value.config['consumer']['writerApp']['installationId'] = '999999'
    else:
        source = value.consumer.with_name('aliased-original.json')
        value.consumer.rename(source)
        value.consumer.symlink_to(source)
    before = value.record.read_bytes()
    with pytest.raises((ValueError, OSError)):
        restore(value)
    assert value.consumer.read_bytes() == value.bad and value.record.read_bytes() == before
    assert not list(value.paths['config'].glob('consumer-drift-before-*'))
    assert not list(value.paths['config'].glob('.consumer-drift-*.context.json'))


@pytest.mark.skipif(os.geteuid() != 0, reason='root private mount namespace qualification')
@pytest.mark.parametrize('child_failure', [False, True])
def test_real_private_mount_view_disappears_after_reaped_child_without_host_file_change(child_failure):
    probe = subprocess.run(['/usr/bin/unshare', '--mount', '--propagation', 'private', '/usr/bin/true'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if probe.returncode:
        pytest.skip('private mount namespaces unavailable in this Linux runtime')
    with tempfile.TemporaryDirectory(prefix='relay-drift-mount-', dir='/run') as temporary:
        root = Path(temporary)
        consumer, desired, gate, cli, child_pid = [root / name for name in [
            'consumer.json', 'desired.json', 'gate.json', 'cli.mjs', 'child-pid']]
        consumer.write_text('original-host-bytes')
        desired.write_text('selected-desired-bytes')
        cli.write_text('import{readFileSync,writeFileSync}from"node:fs";'
            + 'if(readFileSync(' + json.dumps(str(consumer)) + ',"utf8")!=="selected-desired-bytes")process.exit(41);'
            + 'if(readFileSync(' + json.dumps('/proc/' + str(os.getpid()) + '/root' + str(consumer))
            + ',"utf8")!=="original-host-bytes")process.exit(42);'
            + 'writeFileSync(' + json.dumps(str(child_pid)) + ',String(process.pid));'
            + ('process.exit(31);' if child_failure else '')
            + 'writeFileSync(' + json.dumps(str(gate)) + ',"quiesced-before-restore");'
            + 'console.log(JSON.stringify({phase:"quiesced",pid:process.pid}));')
        command = ['/usr/bin/unshare', '--mount', '--propagation', 'private', '--',
            '/usr/bin/python3', '-I', '-c', drift.PRIVATE_VIEW, os.readlink('/proc/self/ns/mnt'),
            str(desired), str(consumer), hashlib.sha256(desired.read_bytes()).hexdigest(),
            shutil.which('node'), str(cli), 'quiesce']
        if child_failure:
            with pytest.raises(ValueError, match='INSTALLED_CONTEXT_UNPROVEN'):
                drift._execute(command, {'PATH': '/usr/bin:/bin'})
            assert not gate.exists()
        else:
            result = drift._execute(command, {'PATH': '/usr/bin:/bin'})
            assert result['phase'] == 'quiesced' and gate.read_text() == 'quiesced-before-restore'
        assert consumer.read_text() == 'original-host-bytes'
        assert not Path('/proc/' + child_pid.read_text()).exists()
        assert str(consumer) not in Path('/proc/self/mountinfo').read_text()
