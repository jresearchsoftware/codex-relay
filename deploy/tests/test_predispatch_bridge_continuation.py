"""Read-only bridge continuation classifier on root/Linux with actual Node 22.

Protected evidence reads and original JSON.stringify digest run for real.
Installed admission/resource probes and remote continuation transport are
explicit fixture adapters; no GitHub, service or installation is mutated.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

from test_install_recovery import installed as ordinary_installed, OLD, TARGET, OPERATION
import install_recovery as recovery

ROOT = Path(__file__).resolve().parents[2]


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(value, ensure_ascii=False).encode() + b'\n')
    path.chmod(0o600)


def tree_state(root):
    return {str(path.relative_to(root)): (os.readlink(path) if path.is_symlink() else
        hashlib.sha256(path.read_bytes()).hexdigest(), path.lstat().st_mode,
        path.lstat().st_ino, path.lstat().st_mtime_ns, path.lstat().st_ctime_ns)
        for path in root.rglob('*') if path.is_symlink() or path.is_file()}


@pytest.fixture
def continuation(ordinary_installed):
    if os.geteuid() != 0 or not Path('/usr/bin/node').is_file():
        pytest.skip('actual root Linux with fixed Node executable required')
    f = ordinary_installed
    install = f['source'].parent.parent.parent
    stage = install / 'releases' / ('.stage-' + OPERATION)
    identity = {'revision': TARGET, 'tree': 'c' * 40, 'archiveSha256': 'a' * 64}
    receipt = {'sourceIdentity': identity, 'operationId': OPERATION}
    write(stage / 'receipt.json', receipt)
    f['record'] = Path(f['config']['consumer']['paths']['claimRoot']) / 'publication-v2/99.json'
    original = {'envelope': {'runId': 99, 'repository': 'example/repository',
        'consumerDigest': f['status']['consumerDigest']}, 'nativeAdmission': True,
        'originalReadyEvent': 71, 'note': 'é — исходная запись', 'small': 1e-7}
    write(f['record'], original)
    f['originalBinding'] = {'operation': 'finalize-predispatch', 'repository': 'example/repository',
        'runId': 99, 'attemptId': 'run-99', 'issueNumber': 42, 'step': 2,
        'head': OLD, 'authorityDigest': 'e' * 64,
        'recordDigest': recovery.original_record_digest(f['record'].read_bytes())}
    f['binding'] = {'version': 1, 'operationId': OPERATION, 'target': TARGET,
        'previousRevision': OLD, 'runId': 99, 'attemptId': 'run-99', 'authorizationId': 10000,
        'predispatchBinding': f['originalBinding'], 'sourceIdentity': identity,
        'stageReceiptSha256': hashlib.sha256((stage / 'receipt.json').read_bytes()).hexdigest(),
        'consumerSha256': 'a' * 64, 'writerWrapperSha256': 'b' * 64}
    f.update(install=install, stage=stage, snapshot=stage / 'old-installation.json',
        installedRevision=OLD, original=original)
    f['status'].update(phase='applying', active=[99], previousActive={'writer': True, 'reviewer': False})
    persist(f)
    return f


def persist(f):
    write(f['snapshot'], {'operationId': OPERATION, 'target': TARGET, 'predispatchBridge': f['binding']})
    write(f['gate_path'], {key: value for key, value in f['status'].items() if key not in ['active', 'unknown']})


def pointer(f, revision):
    destination = f['install'] / 'releases' / revision
    if not destination.exists():
        shutil.copytree(f['source'].parent, destination)
        write(destination / 'reviewed-source/.relay-source.json', {'revision': revision, 'tree': 'c' * 40})
        write(destination / 'artifact-manifest.json', {'commit': revision, 'installedRevision': revision,
            'resolvedRevision': revision, 'gitTree': 'c' * 40})
    current = f['install'] / 'current'
    current.unlink()
    current.symlink_to('releases/' + revision)
    f['installedRevision'] = revision


def finalized(f):
    value = copy.deepcopy(f['original'])
    value['predispatchRecovery'] = {'version': 1, 'status': 'finalized', 'authorizationId': 10000,
        'binding': copy.deepcopy(f['originalBinding']), 'authorizedAt': '2026-09-04T12:02:00Z',
        'completedAt': '2026-09-04T12:03:00Z'}
    write(f['record'], value)
    f['status']['active'] = []
    persist(f)


def probe(f):
    before = tree_state(f['root'])
    try:
        return recovery.inspect(f['config'], TARGET, f['installedRevision'], root=f['root'],
            owner_uid=os.geteuid(), runner=f['runner'], resource_probe=f['resource_probe'])
    finally:
        assert tree_state(f['root']) == before, 'classification must not mutate protected evidence'


@pytest.mark.parametrize('frontier', ['prepared-quiesced', 'before-pointer', 'after-pointer',
    'after-receipt', 'after-receipt-recovery-required'])
def test_classifier_keeps_exact_operation_at_every_durable_frontier(continuation, frontier):
    f = continuation
    if frontier == 'prepared-quiesced':
        f['status'].update(phase='quiesced', previousActive=None)
        persist(f)
    if frontier in ['after-pointer', 'after-receipt', 'after-receipt-recovery-required']:
        pointer(f, TARGET)
    if frontier in ['after-receipt', 'after-receipt-recovery-required']:
        finalized(f)
    if frontier == 'after-receipt-recovery-required':
        f['status']['phase'] = 'recovery-required'
        persist(f)
    expected = {'operationId': OPERATION, 'target': TARGET, 'installedRevision': f['installedRevision']}
    if frontier != 'after-receipt-recovery-required':
        expected['predispatchBridge'] = f['binding']
    assert probe(f) == expected
    assert f['seen'] == ['actual-resources', 'installed-reader']


@pytest.mark.parametrize('kind', ['uuid', 'target', 'source', 'record-digest', 'original-bytes',
    'consumer-digest', 'receipt-bytes', 'missing-record', 'duplicate-record', 'unknown', 'foreign-active',
    'mixed-active', 'finalized-active', 'finalized-authorization', 'finalized-binding', 'finalized-before-pointer'])
def test_classifier_refuses_mismatched_or_foreign_evidence_without_mutation(continuation, kind):
    f = continuation
    if kind.startswith('finalized'):
        if kind != 'finalized-before-pointer':
            pointer(f, TARGET)
        finalized(f)
    if kind == 'uuid':
        f['binding']['operationId'] = '22345678-1234-4234-8234-123456789abc'
    elif kind == 'target':
        f['binding']['target'] = 'f' * 40
    elif kind == 'source':
        f['binding']['sourceIdentity']['revision'] = 'f' * 40
    elif kind == 'record-digest':
        f['binding']['predispatchBinding']['recordDigest'] = 'f' * 64
    elif kind == 'original-bytes':
        write(f['record'], {**f['original'], 'originalReadyEvent': 72})
    elif kind == 'consumer-digest':
        f['status']['consumerDigest'] = 'f' * 64
    elif kind == 'receipt-bytes':
        (f['stage'] / 'receipt.json').write_bytes(b'{"changed":true}\n')
    elif kind == 'missing-record':
        f['record'].unlink()
    elif kind == 'duplicate-record':
        duplicate = f['record'].parent / 'repositories/example/repository/99.json'
        write(duplicate, f['original'])
    elif kind == 'unknown':
        f['status']['unknown'] = [100]
    elif kind in ['foreign-active', 'mixed-active', 'finalized-active']:
        f['status']['active'] = [100] if kind == 'foreign-active' else [99, 100] if kind == 'mixed-active' else [99]
    elif kind == 'finalized-authorization':
        value = json.loads(f['record'].read_bytes())
        value['predispatchRecovery']['authorizationId'] = 10001
        write(f['record'], value)
    elif kind == 'finalized-binding':
        value = json.loads(f['record'].read_bytes())
        value['predispatchRecovery']['binding']['head'] = 'f' * 40
        write(f['record'], value)
    persist(f)
    with pytest.raises(ValueError, match='PREDISPATCH_BRIDGE_'):
        probe(f)


def test_json_digest_uses_actual_javascript_unicode_key_order_and_number_formatting():
    if not Path('/usr/bin/node').is_file():
        pytest.skip('fixed Node executable required')
    raw = ('{"10":"д","2":"é","n":1e-7,"big":1e20,"negativeZero":-0,'
           '"small":0.000001,"predispatchRecovery":{"ignore":true}}').encode()
    expected = ('{"2":"é","10":"д","n":1e-7,"big":100000000000000000000,'
                '"negativeZero":0,"small":0.000001}').encode()
    assert recovery.original_record_digest(raw) == hashlib.sha256(expected).hexdigest()
    with pytest.raises(ValueError, match='ORIGINAL_UNPROVEN'):
        recovery.original_record_digest(b'{invalid-json')


def test_changed_current_or_source_identity_stops_before_continuation(continuation):
    f = continuation
    pointer(f, TARGET)
    f['installedRevision'] = OLD
    with pytest.raises(ValueError, match='CURRENT_CHANGED'):
        probe(f)
    f['installedRevision'] = TARGET
    write(f['install'] / 'releases' / TARGET / 'reviewed-source/.relay-source.json',
        {'revision': 'f' * 40, 'tree': 'c' * 40})
    with pytest.raises(ValueError, match='(?:RELAY_INSTALL_RECOVERY_|REINSTALL_)'):
        probe(f)


def request():
    return {'operation': 'finalize-predispatch', 'runId': 99, 'attemptId': 'run-99',
            'authorizationId': 10000, 'workflowReadToken': 'synthetic-stdin-only-token'}


@pytest.mark.parametrize('installed_revision', [OLD, TARGET])
def test_continuation_transport_keeps_original_uuid_and_exact_request_before_or_after_pointer(
        continuation, monkeypatch, installed_revision):
    import ansible_transport
    f = continuation
    if installed_revision == TARGET:
        pointer(f, TARGET)
    proof = probe(f)
    before = tree_state(f['root'])
    calls = []
    guard = SimpleNamespace(poll=lambda: None)
    def run_target(target, key, argv, **options):
        assert argv[:3] == ['/usr/bin/python3', '-I', '-c']
        compile(argv[3], '<fixed-bridge-continuation>', 'exec')
        assert 'synthetic-stdin-only-token' not in argv[3]
        assert '"verify",stage' in argv[3]
        assert 'continuation=True' in argv[3]
        assert 'prepared.release_writer()' in argv[3]
        payload = json.loads(options['input'])
        assert payload == {'proof': proof, 'request': request(), 'config': f['config']}
        calls.append(payload)
        return SimpleNamespace(returncode=0, stdout=json.dumps({'operationId': OPERATION,
            'target': TARGET, 'installedRevision': TARGET}), stderr='')
    monkeypatch.setattr(ansible_transport, 'run_target', run_target)
    assert recovery.resume_predispatch_bridge(proof, request(), {}, Path('/unused'), f['config'],
        guard, guard, source_root=ROOT) == {'operationId': OPERATION, 'target': TARGET, 'installedRevision': TARGET}
    assert len(calls) == 1
    assert tree_state(f['root']) == before


@pytest.mark.parametrize('changed', [{'authorizationId': 10001}, {'runId': 100},
    {'attemptId': 'run-100'}, {'operation': 'admit'}])
def test_mismatched_continuation_request_never_reaches_remote_transport(continuation, monkeypatch, changed):
    import ansible_transport
    f = continuation
    proof = probe(f)
    def forbidden(*_args, **_options):
        pytest.fail('mismatched request must not reach a remote process')
    monkeypatch.setattr(ansible_transport, 'run_target', forbidden)
    guard = SimpleNamespace(poll=lambda: None)
    before = tree_state(f['root'])
    with pytest.raises(ValueError, match='REQUEST_CHANGED'):
        recovery.resume_predispatch_bridge(proof, {**request(), **changed}, {}, Path('/unused'),
            f['config'], guard, source_root=ROOT)
    assert tree_state(f['root']) == before


def test_lost_host_guard_stops_before_continuation_transport(continuation, monkeypatch):
    import ansible_transport
    f = continuation
    proof = probe(f)
    monkeypatch.setattr(ansible_transport, 'run_target', lambda *_args, **_options: pytest.fail('lost host guard'))
    with pytest.raises(ValueError, match='HOST_LOCK_LOST'):
        recovery.resume_predispatch_bridge(proof, request(), {}, Path('/unused'), f['config'],
            SimpleNamespace(poll=lambda: 1), source_root=ROOT)
