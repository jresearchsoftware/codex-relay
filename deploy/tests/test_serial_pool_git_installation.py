"""Completed SERIAL history does not select a later Git desired configuration."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import pytest

pytest.importorskip('fcntl', reason='native Linux deployment contract')
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
import managed_pool
import serial_pool_installation as installation
import serial_pool_transition as transition

OLD = '1' * 40
CURRENT = '2' * 40
NEXT = '3' * 40
OPERATION = '12345678-1234-4234-8234-123456789abc'
LATER = '22345678-1234-4234-8234-123456789abc'
RECEIPT_DIGEST = 'a' * 64
CURRENT_DIGEST = 'b' * 64
DESIRED_DIGEST = 'c' * 64


@pytest.fixture
def retired(monkeypatch):
    namespace = 'relay-serial-git-fixture'
    claim = '/var/lib/' + namespace + '/claims'
    original = {'environment': {'namespace': namespace, 'compatibilityLinks': {}},
                'consumer': {'repository': 'example/consumer', 'paths': {'claimRoot': claim}}}
    desired = copy.deepcopy(original)
    desired['environment']['localApply'] = {'source': 'git', 'repository': 'example/private',
                                          'configPath': 'prod/relay.json'}
    desired['consumer']['defaultProfile'] = {'model': 'fixture', 'effort': 'medium'}
    source = '/opt/' + namespace + '/serial-compat-v1/' + OLD + '/reviewed-source'
    binding = {'runnerId': 71, 'runnerName': 'legacy-runner'}
    old_gate = b'original sealed gate\n'
    receipt = {'target': {'consumerDigest': RECEIPT_DIGEST}, 'original': {
        'sourceTreeSha256': 'd' * 64, 'gateSha256': hashlib.sha256(old_gate).hexdigest()}}
    raw = transition.encoded(receipt) + b'\n'
    state = {'phase': 'retired', 'operationId': OPERATION, 'targetRevision': CURRENT,
             'receiptSha256': hashlib.sha256(raw).hexdigest(), 'plan': {
                 'binding': binding, 'targetConfigSha256': hashlib.sha256(transition.encoded(desired)).hexdigest()}}
    gate = {'consumerDigest': CURRENT_DIGEST, 'phase': 'open', 'operationId': None, 'target': None}
    paths = {'/etc/' + namespace + '/serial-pool-compat-v1.json': raw,
             '/etc/' + namespace + '/consumer.json': b'{"generalRunnerPool":{"desiredCapacity":1}}',
             claim + '/serial-pool-transition-v1.json': transition.encoded(state),
             claim + '/admission-v1.json': old_gate,
             claim + '/admission-pool-v1.json': transition.encoded(gate)}

    class Files:
        def read(self, path, **_options):
            return paths[path]
        def tree_sha256(self, *_args, **_options):
            return 'd' * 64

    class Host:
        def __init__(self, *_args, **_options):
            pass
        def inspect_legacy(self, value):
            assert value == original
            return {**binding, 'ownWorker': False}
        def legacy_stopped(self, value):
            return value == binding

    class API:
        def observe_legacy(self, value):
            assert value == binding
            return None

    calls = []
    monkeypatch.setattr(installation, 'ProtectedFiles', Files)
    monkeypatch.setattr(installation, 'original_installation', lambda _config: (original, {
        'revision': OLD, 'sourceRoot': source}))
    monkeypatch.setattr(installation, 'original_gate', lambda *_args: None)
    monkeypatch.setattr(installation, 'SerialPoolHost', Host)
    monkeypatch.setattr(installation, 'SerialPoolGitHub', lambda value: value)
    monkeypatch.setattr(installation, 'current_source', lambda config, *, git_desired=False:
                        calls.append(('source', git_desired)) or '/protected/current-source')

    def reader(source_root, consumer_path, code, **options):
        assert source_root == '/protected/current-source'
        assert consumer_path == '/etc/' + namespace + '/consumer.json'
        assert 'installedAdmissionControl().read()' in code and 'CONSUMER_DIGEST' in code
        assert options['repository'] == 'example/consumer'
        calls.append(('reader', consumer_path))
        return {'gate': json.loads(paths[claim + '/admission-pool-v1.json']),
                'digest': current_digest[0], 'managed': True}

    current_digest = [CURRENT_DIGEST]
    monkeypatch.setattr(installation, '_node', reader)
    return {'desired': desired, 'api': API(), 'state': state, 'gate': gate, 'paths': paths,
            'claim': claim, 'calls': calls, 'current_digest': current_digest}


def update(retired, name):
    path = retired['claim'] + ('/serial-pool-transition-v1.json' if name == 'state' else '/admission-pool-v1.json')
    retired['paths'][path] = transition.encoded(retired[name])


@pytest.mark.parametrize('phase', ['open', 'quiesced'])
def test_completed_retirement_keeps_original_receipt_and_accepts_later_git_intent(retired, monkeypatch, phase):
    monkeypatch.setattr(transition, 'validate_delta', lambda *_args: pytest.fail('future intent is not original cutover'))
    if phase == 'quiesced':
        retired['gate'].update(phase=phase, operationId=LATER, target=NEXT)
        update(retired, 'gate')
    before = copy.deepcopy(retired['paths'])
    result = installation.preflight(retired['desired'], retired['api'], DESIRED_DIGEST)
    assert result == {'phase': 'retired', 'operationId': OPERATION,
                      'targetRevision': CURRENT, 'completionRequired': False}
    assert retired['paths'] == before
    assert retired['calls'][0] == ('source', True)


def test_original_incomplete_cutover_keeps_exact_config_and_digest(retired):
    retired['gate'].update(phase='applying', operationId=OPERATION, target=CURRENT,
                           consumerDigest=RECEIPT_DIGEST)
    update(retired, 'gate')
    retired['current_digest'][0] = RECEIPT_DIGEST
    assert installation.preflight(retired['desired'], retired['api'], RECEIPT_DIGEST)['completionRequired'] is True
    # A pending original cutover is not a later Git installation.
    with pytest.raises(managed_pool.PoolError, match='NEW_GATE_UNPROVEN'):
        installation.preflight(retired['desired'], retired['api'], DESIRED_DIGEST)
    changed = copy.deepcopy(retired['desired'])
    changed['consumer']['defaultProfile']['effort'] = 'high'
    with pytest.raises(managed_pool.PoolError, match='NEW_GATE_UNPROVEN'):
        installation.preflight(changed, retired['api'], RECEIPT_DIGEST)


def test_current_gate_must_bind_actual_current_consumer_even_when_desired_matches_it(retired):
    retired['gate']['consumerDigest'] = DESIRED_DIGEST
    update(retired, 'gate')
    with pytest.raises(managed_pool.PoolError, match='NEW_GATE_UNPROVEN'):
        installation.preflight(retired['desired'], retired['api'], DESIRED_DIGEST)


def test_retired_receipt_state_binding_is_not_relaxed(retired):
    retired['state']['receiptSha256'] = 'e' * 64
    update(retired, 'state')
    with pytest.raises(managed_pool.PoolError, match='RETIRED_BINDING_UNPROVEN'):
        installation.preflight(retired['desired'], retired['api'], DESIRED_DIGEST)
    assert not retired['calls']


def test_expert_route_retains_original_owner_delta_gate(retired, monkeypatch):
    retired['desired']['environment']['localApply'] = {'configPath': 'deploy/config.json'}
    def reject(*_args):
        raise managed_pool.PoolError('SERIAL_TRANSITION_OWNER_INTENT_CHANGED')
    monkeypatch.setattr(transition, 'validate_delta', reject)
    with pytest.raises(managed_pool.PoolError, match='OWNER_INTENT_CHANGED'):
        installation.preflight(retired['desired'], retired['api'], DESIRED_DIGEST)
    assert not retired['calls']


def test_no_receipt_unmanaged_git_host_keeps_exact_original_history(tmp_path, monkeypatch):
    namespace = 'relay-managed-fixture'
    current = tmp_path / namespace / 'current'
    current.mkdir(parents=True)
    desired = {'environment': {'namespace': namespace, 'localApply': {'source': 'git'}}}
    live = {'repository': 'example/consumer'}
    class Files:
        def read(self, path, **_options):
            return None if path.endswith('serial-pool-compat-v1.json') else transition.encoded(live)
    monkeypatch.setattr(installation, 'ProtectedFiles', Files)
    monkeypatch.setattr(installation, 'Path', lambda _value: tmp_path)
    def original(_config):
        raise managed_pool.PoolError('EXACT_ORIGINAL_HISTORY_REQUIRED')
    monkeypatch.setattr(installation, 'original_installation', original)
    calls = []
    def actual(config, *, git_desired=False):
        calls.append((config, git_desired))
        return {'managed': True, 'digest': CURRENT_DIGEST, 'gate': {'consumerDigest': CURRENT_DIGEST}}
    monkeypatch.setattr(installation, '_current_admission', actual)
    with pytest.raises(managed_pool.PoolError, match='EXACT_ORIGINAL_HISTORY_REQUIRED'):
        installation.preflight(desired, object(), DESIRED_DIGEST)
    assert not calls


@pytest.mark.skipif(sys.platform != 'linux' or os.geteuid() != 0, reason='native protected source boundary')
@pytest.mark.parametrize('snapshot', ['missing', 'tampered'])
def test_git_source_selection_uses_protected_code_not_mutable_config_snapshot(tmp_path, monkeypatch, snapshot):
    namespace = 'relay-serial-source-fixture'
    logical = '/opt/' + namespace + '/releases/' + CURRENT
    release = tmp_path / logical.lstrip('/')
    source = release / 'reviewed-source'
    (source / 'controller').mkdir(parents=True)
    (source / 'controller/module.mjs').write_text('// actual installed code\n')
    (source / '.relay-source.json').write_text(json.dumps({'revision': CURRENT, 'tree': 'f' * 40}))
    (source / 'legacy').mkdir()
    (source / 'legacy/controller').symlink_to(logical + '/reviewed-source/controller')
    manifest = {'commit': CURRENT, 'installedRevision': CURRENT, 'resolvedRevision': CURRENT,
                'gitTree': 'f' * 40, 'deploymentConfigSha256': '0' * 64}
    (release / 'artifact-manifest.json').write_text(json.dumps(manifest))
    (release.parent.parent / 'current').symlink_to(logical)
    if snapshot == 'tampered':
        (release / 'deployment-config.json').write_text('{malformed overwritten snapshot')
    for path in tmp_path.rglob('*'):
        if not path.is_symlink():
            path.chmod(0o755 if path.is_dir() else 0o600)
    files = transition.ProtectedFiles(tmp_path)
    monkeypatch.setattr(installation, 'ProtectedFiles', lambda: files)
    desired = {'environment': {'namespace': namespace}, 'consumer': {'repository': 'example/consumer'}}
    assert installation.current_source(desired, git_desired=True) == logical + '/reviewed-source'
    with pytest.raises((managed_pool.PoolError, FileNotFoundError, ValueError)):
        installation.current_source(desired)
    # Desired config cannot legitimize a foreign alias or an unsafe source.
    alias = source / 'legacy/controller'
    alias.unlink()
    alias.symlink_to('/opt/foreign/controller')
    with pytest.raises(managed_pool.PoolError, match='SOURCE_LINK_UNPROVEN'):
        installation.current_source(desired, git_desired=True)


MANAGED_PREFLIGHT = r'''import hashlib,json,os,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
fixture,product,namespace,revision,fault=sys.argv[1:]
for name in ['opt','etc','var/lib']:
    subprocess.run(['/usr/bin/mount','--bind',str(Path(fixture)/name),'/'+name],check=True)
sys.path.insert(0,str(Path(product)/'deploy'))
import serial_pool_installation as installation
payload=json.load(sys.stdin)
source=Path('/opt')/namespace/'releases'/revision/'reviewed-source'
consumer=Path('/etc')/namespace/'consumer.json'
claims=Path('/var/lib')/namespace/'writer-claims'
cli=source/'controller/src/admission-cli.mjs'
env={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','RELAY_CONSUMER_CONFIG':str(consumer),
     'RELAY_REPOSITORY':payload['desired']['consumer']['repository']}
initialized=subprocess.run(['/usr/bin/node',str(cli),'initialize'],env=env,text=True,capture_output=True)
if initialized.returncode:raise RuntimeError('actual Node initialize: '+initialized.stderr)
gate_path=claims/'admission-v1.json'
gate=json.loads(gate_path.read_bytes())
if fault=='gate-mismatch':
    gate['consumerDigest']='0'*64;gate_path.write_text(json.dumps(gate));gate_path.chmod(0o600)
elif fault=='unsafe-source':
    (source/'consumer/consumer-config.mjs').chmod(0o666)
elif fault=='unknown-source':
    current=Path('/opt')/namespace/'current';current.unlink();current.symlink_to('releases/'+'f'*40)
critical=[consumer,gate_path,source/'.relay-source.json',source.parent/'artifact-manifest.json']
snapshot=source.parent/'deployment-config.json'
if snapshot.exists():critical.append(snapshot)
def stamps():
    result={}
    for path in critical:
        s=path.lstat();result[str(path)]=(hashlib.sha256(path.read_bytes()).hexdigest(),s.st_mode,s.st_uid,s.st_gid,s.st_ino,s.st_ctime_ns)
    return result
before=stamps();opened=[];watch=[True]
def audit(event,args):
    if watch[0] and event=='open' and isinstance(args[0],str) and Path(args[0]).name in ['deployment-config.json','.credentials','not-read.pem']:
        opened.append(Path(args[0]).name)
sys.addaudithook(audit)
try:
    result=installation.preflight(payload['desired'],object(),payload['targetDigest'])
    observed=installation._current_admission(payload['desired'],git_desired=True)
    output={'status':'PASS','result':result,'actualAdmission':observed}
except Exception as error:
    output={'status':'BLOCKED','type':type(error).__name__,'code':str(error)}
watch[0]=False
output.update(opened=opened,unchanged=before==stamps(),initializedGate=json.loads(initialized.stdout))
print(json.dumps(output))
'''


@pytest.mark.skipif(sys.platform != 'linux' or os.geteuid() != 0, reason='root isolated managed installation')
@pytest.mark.parametrize('fault', ['missing', 'tampered', 'legacy-directory', 'legacy-service',
                                  'unsafe-source', 'unknown-source', 'gate-mismatch', 'unmanaged'])
def test_real_managed_git_preflight_uses_actual_node_and_legacy_guard_without_own_snapshot(fault):
    """Run the actual helper and installed graph in a private local FS view.

    No fake current-admission/guard proof, credential read, live API or system
    service is involved. The two snapshot cases reproduce the real repair seam.
    """
    from config import loads
    from managed_pool_transport import consumer_digest, projected_consumer
    from test_managed_pool import inputs

    probe = subprocess.run(['/usr/bin/unshare', '--mount', '--fork', '/usr/bin/true'], capture_output=True)
    if probe.returncode:
        pytest.skip('private mount namespace unavailable')
    namespace = 'relay-managed-git-test'
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    tree = subprocess.check_output(['git', 'rev-parse', 'HEAD^{tree}'], cwd=ROOT, text=True).strip()
    original = inputs(2, namespace=namespace)
    original['environment']['localApply'] = {
        'source': 'git', 'repository': 'example-org/private-deployment', 'configPath': 'test/relay.json'}
    original['consumer']['defaultProfile']['effort'] = 'xhigh'
    original = loads(json.dumps(original), ROOT)
    original = loads(json.dumps(original, sort_keys=True, separators=(',', ':')), ROOT)
    actual = projected_consumer(original, ROOT)
    assert len(actual['executionSlots']) == 32
    desired = copy.deepcopy(original)
    desired['consumer']['defaultProfile']['effort'] = 'medium'
    target_digest = consumer_digest(projected_consumer(desired, ROOT), ROOT)
    if fault == 'unmanaged':
        actual.pop('generalRunnerPool')
        actual.pop('executionSlots')
    with tempfile.TemporaryDirectory(prefix='relay-managed-preflight-', dir='/run') as temporary:
        root = Path(temporary)
        source = root / 'opt' / namespace / 'releases' / revision / 'reviewed-source'
        for component in ['consumer', 'controller', 'contracts', 'runtime', 'reviewer']:
            shutil.copytree(ROOT / component, source / component,
                ignore=shutil.ignore_patterns('__pycache__', 'node_modules', 'target'))
        for path in [root, *root.rglob('*')]:
            path.chmod(0o755 if path.is_dir() else 0o644)
        (source / '.relay-source.json').write_text(json.dumps({'revision': revision, 'tree': tree}))
        manifest = {'commit': revision, 'installedRevision': revision, 'resolvedRevision': revision,
                    'gitTree': tree, 'deploymentConfigSha256': '0' * 64}
        (source.parent / 'artifact-manifest.json').write_text(json.dumps(manifest))
        (source.parent / 'artifact-manifest.json').chmod(0o600)
        (root / 'opt' / namespace / 'current').symlink_to('releases/' + revision)
        config = root / 'etc' / namespace
        config.mkdir(parents=True)
        consumer = config / 'consumer.json'
        consumer.write_text(json.dumps(actual))
        consumer.chmod(0o644)
        claims = root / 'var/lib' / namespace / 'writer-claims'
        claims.mkdir(parents=True, mode=0o700)
        (root / 'etc/systemd/system').mkdir(parents=True)
        if fault == 'tampered':
            snapshot = source.parent / 'deployment-config.json'
            snapshot.write_bytes(b'{unbound current snapshot')
            snapshot.chmod(0o600)
        elif fault == 'legacy-directory':
            legacy = root / 'opt' / namespace / 'general-runner'
            legacy.mkdir()
            os.mkfifo(legacy / '.credentials', 0o600)  # Any attempted credential read would block.
        elif fault == 'legacy-service':
            (root / 'etc/systemd/system' / (namespace + '-general-runner.service')).write_text('[Service]\n')
        process = subprocess.run(['/usr/bin/unshare', '--mount', '--propagation', 'private', '--',
            '/usr/bin/python3', '-I', '-c', MANAGED_PREFLIGHT, str(root), str(ROOT), namespace, revision, fault],
            input=json.dumps({'desired': desired, 'targetDigest': target_digest}), capture_output=True,
            text=True, timeout=90)
        assert process.returncode == 0, process.stderr
        result = json.loads(process.stdout)
        assert result['unchanged'], result
        assert '.credentials' not in result['opened'] and 'not-read.pem' not in result['opened']
        if fault in ['missing', 'tampered']:
            assert result['status'] == 'PASS', result
            assert result['result'] is None and result['actualAdmission']['managed'] is True
            assert result['actualAdmission']['digest'] == result['initializedGate']['consumerDigest']
            assert result['actualAdmission']['digest'] != target_digest  # Future Git policy is permitted.
            assert result['opened'] == []
        else:
            assert result['status'] == 'BLOCKED', result
            if fault in ['legacy-directory', 'legacy-service']:
                assert 'SERIAL_TRANSITION_REQUIRED' in result['code']
            elif fault == 'gate-mismatch':
                assert 'ORIGINAL_READER_UNPROVEN' in result['code']
