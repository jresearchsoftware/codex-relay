"""Root/Linux bridge regression in an isolated disposable filesystem.

Protected reads, lease-holder process, kernel flocks, snapshot writes, fsync and
atomic current replacement are real. Admission/API authorization and sealed
artifact preparation use the bridge's explicit in-process fixture seams; this
does not qualify a deployed service, real credentials or GitHub authorization.
"""
import copy
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import sys
import tempfile
import traceback
from types import SimpleNamespace
import uuid

import pytest
from jinja2 import Environment, StrictUndefined

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
spec = importlib.util.spec_from_file_location('predispatch_bridge_regression', ROOT / 'deploy/predispatch_bridge.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)
TARGET, PREVIOUS, DIGEST = 'b' * 40, 'a' * 40, 'c' * 64
OPERATION = '12345678-1234-4234-8234-123456789abc'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def put(path, value, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value if isinstance(value, bytes) else json.dumps(value, sort_keys=True).encode() + b'\n')
    path.chmod(mode)
    return path


class FixtureArtifacts:
    """Small sealed artifact stand-in; production artifact tests own its format."""
    def __init__(self, stage, identity, receipt):
        self.stage, self.identity, self.receipt = stage, identity, receipt
        self.calls = []

    @staticmethod
    def allowed_links(_acquisition):
        return []

    @staticmethod
    def tree_digest(root, _links):
        entries = []
        for path in sorted(root.rglob('*')):
            assert not path.is_symlink()
            if path.is_file():
                entries.append([str(path.relative_to(root)), sha(path.read_bytes())])
        return sha(json.dumps(entries, sort_keys=True).encode())

    def check_destination(self, candidate, destination, links):
        assert self.tree_digest(candidate, links) == self.tree_digest(destination, links)

    def run(self, operation, stage, options, destination=None):
        self.calls.append(operation)
        assert stage == self.stage
        assert options['operationId'] == OPERATION
        assert options['sourceIdentity'] == self.identity
        assert self.tree_digest(stage / 'release', []) == self.receipt['releaseTreeSha256']
        if operation == 'verify':
            return copy.deepcopy(self.receipt)
        assert operation == 'consume'
        destination = Path(destination)
        if not destination.exists():
            shutil.copytree(stage / 'release', destination)
        self.check_destination(stage / 'release', destination, [])
        return copy.deepcopy(self.receipt)


@pytest.fixture
def protected_bridge(monkeypatch):
    if sys.platform != 'linux' or os.geteuid() != 0:
        pytest.skip('actual root Linux filesystem and kernel flock required')
    with tempfile.TemporaryDirectory(prefix='relay-predispatch-bridge-', dir='/run') as temporary:
        root = Path(temporary)
        install, claims = root / 'install', root / 'claims'
        releases = install / 'releases'
        stage = releases / ('.stage-' + OPERATION)
        candidate = stage / 'release'
        staged_source = candidate / 'reviewed-source'
        old_release = releases / PREVIOUS
        old_source = old_release / 'reviewed-source'
        identity = {'revision': TARGET, 'tree': 'd' * 40}
        template_path = Path('deploy/ansible/roles/relay_controller/templates/relay-writer-controller.j2')
        template = (ROOT / template_path).read_bytes()
        put(old_source / template_path, template)
        put(staged_source / template_path, template)
        put(staged_source / '.relay-source.json', identity)
        put(staged_source / 'deploy/installation-contract.json', {'capabilities': [bridge.CAPABILITY]})
        deployment = put(candidate / 'deployment-config.json', {'fixture': 'isolated TEST'})
        binary = put(candidate / 'bin/reviewer-mcp-http', b'isolated synthetic reviewer\n', 0o750)
        receipt = {'reviewer': {'binarySha256': sha(binary.read_bytes())},
                   'toolchain': {'livePrefix': str(root / 'toolchain')}, 'sourceAcquisition': {}}
        put(candidate / 'artifact-manifest.json', {'commit': TARGET, 'installedRevision': TARGET,
            'resolvedRevision': TARGET, 'gitTree': identity['tree'], 'previousRevision': PREVIOUS,
            'deploymentConfigSha256': sha(deployment.read_bytes()),
            'reviewerBinarySha256': receipt['reviewer']['binarySha256']})
        receipt['releaseTreeSha256'] = FixtureArtifacts.tree_digest(candidate, [])
        put(stage / 'receipt.json', receipt)
        put(stage / 'old-installation.json', {'operationId': OPERATION, 'target': TARGET,
            'previousActive': {'writer': True, 'reviewer': False}})
        consumer = put(root / 'consumer.json', {'fixture': 'no credentials', 'repository': 'example/repository'})
        original = put(claims / 'publication-v2/99.json', {'runId': 99, 'attemptId': 'run-99',
            'controllerLifecycle': {'version': 1, 'status': 'active'}, 'originalReadyEvent': 71})
        lock = put(claims / 'publication-v2.lock', b'')
        current = install / 'current'
        current.symlink_to(old_release)
        namespace = 'relay-predispatch-test-' + uuid.uuid4().hex
        host_path = Path('/var/lib') / (namespace + '-deployment.lock')
        host_fd = os.open(host_path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        fcntl.flock(host_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        values = {'relay_install_root': str(install), 'relay_release_root': str(releases),
            'relay_writer_helper_path': str(install / 'relay-writer-controller'),
            'relay_writer_claim_root': str(claims), 'relay_consumer_config_path': str(consumer),
            'relay_writer_credential_env_file': str(root / 'never-read.env'),
            'relay_writer_credential_key_file': str(root / 'never-read.pem'),
            'relay_namespace': namespace, 'relay_reviewer_group': 'root',
            'relay_github_repository': 'example/repository'}
        context = {**values, 'relay_writer_helper_release_path': str(install / 'current/reviewed-source/controller/src/privileged-writer-entrypoint.mjs')}
        rendered = Environment(undefined=StrictUndefined, keep_trailing_newline=True).from_string(template.decode()).render(**context)
        wrapper = put(Path(values['relay_writer_helper_path']), rendered.encode(), 0o750)
        lease_path = root / 'writer-lease.json'
        holder = subprocess.Popen([sys.executable, '-I', str(ROOT / 'deploy/writer_lock_lease.py'),
            '--hold', str(lock), str(lease_path), OPERATION, TARGET, DIGEST],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(holder.stdout, selectors.EVENT_READ)
                assert selector.select(10), 'isolated Writer lease did not become ready'
                assert holder.stdout.readline() == 'WRITER_LOCK_READY\n'
            data = {'values': values, 'identity': identity, 'operationId': OPERATION, 'stage': str(stage),
                'lease': str(lease_path), 'consumerDigest': DIGEST, 'previousRevision': PREVIOUS,
                'runId': 99, 'hostLockFd': host_fd, 'recoveryRequest': {'operation': 'finalize-predispatch',
                    'repository': 'example/repository', 'runId': 99, 'attemptId': 'run-99',
                    'authorizationId': 10000, 'workflowReadToken': 'synthetic-never-persist-this-token'}}
            binding = {'operation': 'finalize-predispatch', 'repository': 'example/repository',
                'runId': 99, 'attemptId': 'run-99', 'recordDigest': sha(original.read_bytes())}
            f = SimpleNamespace(root=root, data=data, stage=stage, candidate=candidate,
                source=staged_source, old=old_release, destination=releases / TARGET, current=current,
                original=original, original_bytes=original.read_bytes(), consumer=consumer,
                consumer_bytes=consumer.read_bytes(), wrapper=wrapper, wrapper_bytes=wrapper.read_bytes(),
                lease=lease_path, holder=holder, lock=lock, host_fd=host_fd, host_path=host_path,
                artifacts=FixtureArtifacts(stage, identity, receipt), binding=binding,
                status={'phase': 'applying', 'target': TARGET, 'consumerDigest': DIGEST,
                        'active': [99], 'unknown': [], 'previousActive': {'writer': True}}, inspections=[])
            def inspect(selected):
                f.inspections.append(copy.deepcopy(selected['recoveryRequest']))
                if selected['recoveryRequest']['authorizationId'] != 10000:
                    raise ValueError('FIXTURE_NATIVE_AUTHORIZATION_INVALID')
                if sha(f.original.read_bytes()) != f.binding['recordDigest']:
                    raise ValueError('FIXTURE_ORIGINAL_RECORD_CHANGED')
                return copy.deepcopy(f.binding)
            f.inspect = inspect
            f.activate = lambda **options: bridge.activate(data, observe=lambda *_args: copy.deepcopy(f.status),
                inspect=f.inspect, artifacts=f.artifacts, **options)
            monkeypatch.setattr(bridge, 'SOURCE', staged_source)
            yield f
        finally:
            if holder.poll() is None:
                holder.stdin.close()
                try:
                    holder.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    holder.kill()
                    holder.wait(timeout=5)
            for stream in [holder.stdout, holder.stderr]:
                stream.close()
            os.close(host_fd)
            host_path.unlink(missing_ok=True)


def assert_original(f):
    assert f.original.read_bytes() == f.original_bytes
    assert f.consumer.read_bytes() == f.consumer_bytes
    assert f.wrapper.read_bytes() == f.wrapper_bytes


def test_isolated_python_refusal_does_not_write_bytecode_into_sealed_source():
    if sys.platform != 'linux' or os.geteuid() != 0:
        pytest.skip('root Linux sealed source and isolated Python required')
    with tempfile.TemporaryDirectory(prefix='relay-bridge-isolated-import-', dir='/run') as temporary:
        source = Path(temporary) / 'reviewed-source'
        deploy = source / 'deploy'
        deploy.mkdir(parents=True)
        for name in ['predispatch_bridge.py', 'install_preflight.py', 'writer_lock_lease.py']:
            shutil.copyfile(ROOT / 'deploy' / name, deploy / name)
            (deploy / name).chmod(0o644)
        put(source / '.relay-source.json', {'revision': TARGET})

        def sealed_tree():
            result = {}
            for path in [source, *sorted(source.rglob('*'))]:
                info = path.lstat()
                result[str(path.relative_to(source))] = (info.st_mode, info.st_size,
                    info.st_ino, info.st_mtime_ns, info.st_ctime_ns,
                    sha(path.read_bytes()) if path.is_file() else None)
            return result

        sealed = sealed_tree()
        # -I ignores PYTHONDONTWRITEBYTECODE. The real entrypoint must suppress
        # local import caches itself, even when it refuses before activation.
        for _attempt in range(2):
            result = subprocess.run(['/usr/bin/python3', '-I', str(deploy / 'predispatch_bridge.py')],
                input='{}\n', text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10,
                env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C', 'PYTHONDONTWRITEBYTECODE': '1'})
            assert result.returncode == 1
            assert result.stdout == ''
            assert result.stderr == ('PREDISPATCH_BRIDGE_UNPROVEN;'
                'preserve-current-and-use-same-operation-forward-recovery\n')
            assert not list(source.rglob('__pycache__'))
            assert not list(source.rglob('*.pyc'))
            assert sealed_tree() == sealed


def test_bridge_uses_real_root_lock_lease_and_preserves_exact_authorized_record(protected_bridge):
    f = protected_bridge
    with f.lock.open('rb') as contender:
        with pytest.raises(BlockingIOError):
            fcntl.flock(contender.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    result = f.activate()
    assert result == {'operationId': OPERATION, 'target': TARGET, 'previousRevision': PREVIOUS,
                      'phase': 'applying', 'writer': 'compatible', 'serviceSnapshot': 'retained'}
    assert f.current.resolve() == f.destination
    assert len(f.inspections) == 2
    saved = bridge.read_binding(f.stage, OPERATION, TARGET)
    assert saved['predispatchBinding'] == f.binding
    assert saved['authorizationId'] == 10000
    assert saved['writerWrapperSha256'] == sha(f.wrapper_bytes)
    assert 'synthetic-never-persist-this-token' not in (f.stage / 'old-installation.json').read_text()
    assert_original(f)


@pytest.mark.parametrize('boundary', ['before-switch', 'after-switch'])
def test_interrupted_bridge_continues_same_uuid_without_restoring_old_writer(protected_bridge, boundary):
    f = protected_bridge
    def crash(at):
        if at == boundary:
            # Exit the real helper process without Python unwinding or cleanup.
            os._exit(77)
    child = os.fork()
    if child == 0:
        try:
            f.activate(after=crash)
        except BaseException:
            traceback.print_exc()
            os._exit(78)
        os._exit(79)
    _pid, status = os.waitpid(child, 0)
    assert os.WIFEXITED(status) and os.WEXITSTATUS(status) == 77
    assert f.current.resolve() == (f.old if boundary == 'before-switch' else f.destination)
    frozen = (f.stage / 'old-installation.json').read_bytes()
    assert bridge.read_binding(f.stage, OPERATION, TARGET)['predispatchBinding'] == f.binding
    assert_original(f)
    assert f.activate()['operationId'] == OPERATION
    assert f.current.resolve() == f.destination
    assert (f.stage / 'old-installation.json').read_bytes() == frozen
    assert_original(f)


@pytest.mark.parametrize('field,value', [('active', [100]), ('active', [99, 100]), ('unknown', [100]), ('phase', 'open')])
def test_foreign_or_unknown_activity_blocks_before_pointer_and_record_mutation(protected_bridge, field, value):
    f = protected_bridge
    f.status[field] = value
    with pytest.raises(ValueError, match='OTHER_EXECUTION_UNRESOLVED'):
        f.activate()
    assert f.current.resolve() == f.old
    assert f.inspections == []
    assert 'consume' not in f.artifacts.calls
    assert_original(f)


def test_invalid_authorization_preserves_old_writer_and_original_bytes(protected_bridge):
    f = protected_bridge
    f.data['recoveryRequest']['authorizationId'] = 10001
    with pytest.raises(ValueError, match='AUTHORIZATION_INVALID'):
        f.activate()
    assert f.current.resolve() == f.old
    assert 'consume' not in f.artifacts.calls
    assert 'predispatchBridge' not in json.loads((f.stage / 'old-installation.json').read_bytes())
    assert_original(f)


def test_authorization_and_original_binding_are_rechecked_after_materialization(protected_bridge):
    f = protected_bridge
    inspect = f.inspect
    def changed(selected):
        value = inspect(selected)
        if len(f.inspections) == 2:
            value['recordDigest'] = 'f' * 64
        return value
    f.inspect = changed
    with pytest.raises(ValueError, match='ORIGINAL_EVIDENCE_CHANGED'):
        f.activate()
    assert f.current.resolve() == f.old
    assert 'consume' in f.artifacts.calls
    assert_original(f)


@pytest.mark.parametrize('field,value', [('operationId', '22345678-1234-4234-8234-123456789abc'),
    ('consumerDigest', 'e' * 64), ('runId', 100)])
def test_foreign_operation_or_attempt_cannot_reuse_a_lease(protected_bridge, field, value):
    f = protected_bridge
    f.data[field] = value
    with pytest.raises((ValueError, AssertionError)):
        f.activate()
    assert f.current.resolve() == f.old
    assert_original(f)


def test_dead_writer_lease_and_wrong_host_lock_descriptor_are_not_authority(protected_bridge):
    f = protected_bridge
    with f.original.open('rb') as foreign:
        f.data['hostLockFd'] = foreign.fileno()
        with pytest.raises(ValueError, match='HOST_LOCK_UNPROVEN'):
            f.activate()
    f.data['hostLockFd'] = f.host_fd
    f.holder.stdin.close()
    assert f.holder.wait(timeout=5) == 0
    with pytest.raises((ValueError, OSError, RuntimeError)):
        f.activate()
    assert f.current.resolve() == f.old
    assert_original(f)


def test_unprotected_source_and_pinned_old_writer_wrapper_fail_before_switch(protected_bridge):
    f = protected_bridge
    f.wrapper.chmod(0o666)
    with pytest.raises(RuntimeError, match='RESOURCE_UNSAFE'):
        f.activate()
    f.wrapper.chmod(0o750)
    f.wrapper.write_bytes(f.wrapper_bytes.replace(b'/current/reviewed-source/',
        ('/releases/' + PREVIOUS + '/reviewed-source/').encode()))
    with pytest.raises(ValueError, match='WRITER_WRAPPER_UNPROVEN'):
        f.activate()
    f.wrapper.write_bytes(f.wrapper_bytes)
    f.wrapper.chmod(0o750)
    assert f.current.resolve() == f.old
    assert_original(f)


def test_switched_pointer_without_exact_persisted_operation_binding_cannot_resume(protected_bridge):
    f = protected_bridge
    f.activate()
    snapshot_path = f.stage / 'old-installation.json'
    snapshot = json.loads(snapshot_path.read_bytes())
    snapshot['predispatchBridge']['authorizationId'] = 10001
    put(snapshot_path, snapshot)
    with pytest.raises(ValueError, match='OPERATION_BINDING_CHANGED'):
        f.activate()
    assert f.current.resolve() == f.destination
    assert_original(f)


def test_substituted_original_record_cannot_be_retired_on_same_uuid_continuation(protected_bridge):
    f = protected_bridge
    f.activate()
    snapshot = (f.stage / 'old-installation.json').read_bytes()
    # Only the fixture substitutes bytes; the bridge must neither accept nor
    # overwrite this foreign evidence to manufacture its old digest again.
    substituted = b'{"runId":99,"foreign":true}\n'
    f.original.write_bytes(substituted)
    with pytest.raises(ValueError, match='ORIGINAL_RECORD_CHANGED'):
        f.activate()
    assert f.original.read_bytes() == substituted
    assert f.current.resolve() == f.destination
    assert (f.stage / 'old-installation.json').read_bytes() == snapshot
    f.original.write_bytes(f.original_bytes)
    assert f.activate()['operationId'] == OPERATION
    assert_original(f)
