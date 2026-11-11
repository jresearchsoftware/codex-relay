"""Root/Linux old-state abort and independently verified package-stage boundaries."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import selectors
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
import install_preflight as preflight

OP = '12345678-1234-1234-1234-123456789abc'
OLD, TARGET = 'a' * 40, 'b' * 40


def protect_fixture_source(root):
    """Materialize only the copied root artifact, preserving external symlinks."""
    assert not root.is_symlink()
    for directory, dirs, files in os.walk(root, followlinks=False):
        Path(directory).chmod(0o755)
        dirs[:] = [name for name in dirs if not (Path(directory) / name).is_symlink()]
        for name in files:
            path = Path(directory) / name
            info = path.lstat()
            if stat.S_ISREG(info.st_mode):
                path.chmod(0o755 if info.st_mode & 0o111 else 0o644)


class LocalPrepared(preflight.PreparedInstall):
    """Only Ansible transport is substituted; Node, flock and file checks are real."""
    def __init__(self, fixture):
        self.fixture = fixture
        super().__init__(None, None, fixture.values, {'revision': TARGET}, OP, local=True)

    def execute(self, argv, *, payload=None, timeout=180):
        if payload and 'action' in payload:
            return preflight.remote(payload, root=self.fixture.root, service_probe=self.fixture.service_probe)
        if len(argv) > 2 and argv[2].endswith('/deploy/host_preflight.py'):
            return {'status': 'PASS', 'observedSha256': self.fixture.host_state}
        actual = [str(self.fixture.at(item)) if isinstance(item, str)
                  and item.startswith(('/opt/fixture', '/etc/fixture', '/var/lib/fixture')) else item
                  for item in argv]
        result = subprocess.run(actual, input=json.dumps(payload) if payload is not None else None,
                                text=True, capture_output=True, timeout=timeout)
        if result.returncode:
            raise RuntimeError('synthetic-local-transport-failure:' + result.stderr)
        value = json.loads(result.stdout)
        if isinstance(value, dict):
            for key in ['claimRoot', 'lockPath', 'effectiveConsumerPath']:
                if isinstance(value.get(key), str) and value[key].startswith(str(self.fixture.root) + '/'):
                    value[key] = '/' + str(Path(value[key]).relative_to(self.fixture.root))
        return value

    def lock_writer(self):
        self.holder = self.fixture.holder(self)


@unittest.skipUnless(sys.platform == 'linux' and os.geteuid() == 0, 'actual root Linux required')
class OldInstallationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='relay-install-preflight-', dir='/run')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.values = {'relay_namespace': 'fixture', 'relay_install_root': '/opt/fixture',
            'relay_release_root': '/opt/fixture/releases', 'relay_config_root': '/etc/fixture',
            'relay_state_root': '/var/lib/fixture', 'relay_writer_claim_root': '/var/lib/fixture/writer-claims',
            'relay_consumer_config_path': '/etc/fixture/consumer.json',
            'relay_github_repository': 'example/consumer', 'relay_reviewer_service_name': 'fixture-reviewer.service',
            'relay_production_runner_service_name': 'fixture-production.service',
            'relay_general_runner_service_name': 'fixture-general.service'}
        self.claim = '/var/lib/fixture/writer-claims'
        self.gate = self.at(self.claim + '/admission-v1.json')
        self.gate.parent.mkdir(parents=True)
        self.lock = self.gate.parent / 'publication-v2.lock'
        self.lock.write_bytes(b''); self.lock.chmod(0o644)
        self.configuration = self.at('/etc/fixture/consumer.json')
        self.configuration.parent.mkdir(parents=True)
        self.consumer = json.loads((ROOT / 'consumer/fixtures/example.json').read_text())
        for key in self.consumer['paths']:
            self.consumer['paths'][key] = str(self.root / 'configured' / key)
        self.consumer['paths']['claimRoot'] = str(self.gate.parent)
        self.consumer['repository'] = self.values['relay_github_repository']
        self.actual_consumer = json.dumps(self.consumer).encode()
        self.configuration.write_bytes(self.actual_consumer)
        self.configuration.chmod(0o644)
        digest_program = ('import{loadConsumer,consumerDigest}from'
            + json.dumps((ROOT / 'consumer/consumer-config.mjs').as_uri())
            + ';console.log(consumerDigest(loadConsumer(process.argv[1])));')
        self.digest = subprocess.check_output(['/usr/bin/node', '--input-type=module', '-e',
            digest_program, str(self.configuration)], text=True).strip()
        old_gate = {'version': 1, 'consumerDigest': self.digest, 'phase': 'open', 'operationId': None,
                    'target': None, 'previousActive': None, 'verifiedRevision': None}
        self.old_gate = (json.dumps(old_gate, indent=3) + '\n').encode()
        self.gate.write_bytes(self.old_gate); self.gate.chmod(0o600)
        release = self.at('/opt/fixture/releases/' + OLD)
        (release / 'reviewed-source').mkdir(parents=True)
        (release / 'reviewed-source/.relay-source.json').write_text(json.dumps({'revision': OLD}))
        snapshot = release / 'deployment-config.json'
        snapshot.write_text(json.dumps({'consumer': self.consumer, 'environment': {'namespace': 'fixture'}}))
        snapshot.chmod(0o600)
        (release / 'artifact-manifest.json').write_text(json.dumps({'commit': OLD, 'resolvedRevision': OLD,
            'installedRevision': OLD, 'deploymentConfigSha256': hashlib.sha256(snapshot.read_bytes()).hexdigest()}))
        (self.at('/opt/fixture') / 'current').symlink_to('releases/' + OLD)
        self.helper = self.at('/opt/fixture/relay-admission')
        self.helper.write_text('accepted old helper\n'); self.helper.chmod(0o750)
        self.unit = self.at('/etc/systemd/system/fixture-reviewer.service')
        self.unit.parent.mkdir(parents=True)
        self.unit.write_text('[Service]\nExecStart=/accepted/old\n')
        self.secret = self.at('/etc/fixture/writer-credentials/key.pem')
        self.secret.parent.mkdir(mode=0o700)
        self.secret.write_text('synthetic private credential bytes must never be read')
        self.secret.chmod(0o600)
        self.host_state = 'c' * 64
        self.service_states = {
            'fixture-reviewer.service': {'MainPID': '0', 'ExecMainStartTimestampMonotonic': '0',
                'ActiveState': 'inactive', 'SubState': 'dead', 'UnitFileState': 'enabled', 'LoadState': 'loaded'},
            'fixture-production.service': {'MainPID': '0', 'ExecMainStartTimestampMonotonic': '0',
                'ActiveState': 'inactive', 'SubState': 'dead', 'UnitFileState': 'enabled', 'LoadState': 'loaded'},
            'fixture-general.service': {'MainPID': '0', 'ExecMainStartTimestampMonotonic': '0',
                'ActiveState': 'inactive', 'SubState': 'dead', 'UnitFileState': 'enabled', 'LoadState': 'loaded'},
            'fixture-relay-manual-outcome.socket': {'ActiveState': 'inactive', 'SubState': 'dead',
                'UnitFileState': 'not-found', 'LoadState': 'not-found'}}
        self.prepared = LocalPrepared(self)
        self.prepared.create()
        source = self.at(self.prepared.source)
        for component in ['consumer', 'controller', 'contracts', 'runtime', 'reviewer/src']:
            shutil.copytree(ROOT / component, source / component,
                            symlinks=True, ignore=shutil.ignore_patterns('node_modules', 'target', '__pycache__'))
        (source / 'deploy').mkdir()
        shutil.copyfile(ROOT / 'deploy/writer_lock_lease.py', source / 'deploy/writer_lock_lease.py')
        (source / '.relay-source.json').write_text(json.dumps({'revision': TARGET}))
        protect_fixture_source(source)
        self.prepared.desired_digest = 'f' * 64

    def at(self, logical):
        return self.root / Path(logical).relative_to('/')

    def service_probe(self, unit):
        properties = self.service_states[unit]
        stdout = ''.join(key + '=' + value + '\n' for key, value in properties.items())
        return subprocess.CompletedProcess(['/bin/systemctl', 'show', unit], 0, stdout, '')

    def holder(self, prepared):
        source = Path(prepared.source)
        lease_path = Path(prepared.lease_path)
        if not source.is_relative_to(self.root): source = self.at(prepared.source)
        if not lease_path.is_relative_to(self.root): lease_path = self.at(prepared.lease_path)
        process = subprocess.Popen(['/usr/bin/python3', '-I', str(source / 'deploy/writer_lock_lease.py'),
            '--hold', str(self.lock), str(lease_path), OP, TARGET, self.digest],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        def close():
            if process.poll() is None:
                process.stdin.close()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=5)
            process.stdout.close(); process.stderr.close()
        self.addCleanup(close)
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            self.assertTrue(selector.select(5))
            self.assertEqual(process.stdout.readline(), 'WRITER_LOCK_READY\n')
        return process

    def capture_and_reserve(self):
        self.prepared.consumer()
        self.prepared.host()
        self.prepared.capture()
        gate = json.loads(self.old_gate)
        gate.update(phase='applying', operationId=OP, target=TARGET)
        self.gate.write_text(json.dumps(gate))

    def prepare_predispatch_bridge_abort(self):
        self.capture_and_reserve()
        run_id, issue, step, event = 71, 71, 2, 401
        envelope = {'version': 2, 'repository': self.consumer['repository'], 'consumerDigest': self.digest,
            'runId': run_id, 'attemptId': 'run-' + str(run_id), 'issueNumber': issue, 'step': step,
            'executionSlot': 'primary', 'readyEventId': event, 'branch': 'codex/task-230',
            'startHead': 'd' * 40, 'authorityDigest': 'e' * 64}
        record = {'envelope': envelope, 'readyConsumption': {'status': 'uncertain', 'code': 'READY_EVENT_REPLACED'},
            'controllerLifecycle': {'version': 1, 'status': 'complete', 'child': 'not_started',
                'containment': 'not_required'}, 'outcome': {'status': 'BLOCKED'},
            'publicationIntent': None, 'publishedHead': None, 'finalHead': None}
        claim_store = self.at(self.claim) / 'publication-v2'
        claim_store.mkdir(mode=0o700)
        record_path = claim_store / (str(run_id) + '.json')
        raw = json.dumps(record, separators=(',', ':')).encode() + b'\n'
        record_path.write_bytes(raw); record_path.chmod(0o600)
        program = ('import{createHash}from"node:crypto";import{readFileSync}from"node:fs";'
            'const value=JSON.parse(readFileSync(0));console.log(createHash("sha256").update(JSON.stringify(value)).digest("hex"));')
        record_digest = subprocess.check_output(['/usr/bin/node', '--input-type=module', '-e', program],
            input=raw, text=False).decode().strip()
        binding = {'operation': 'finalize-predispatch', 'repository': self.consumer['repository'],
            'runId': run_id, 'attemptId': envelope['attemptId'], 'issueNumber': issue, 'step': step,
            'executionSlot': 'primary', 'readyEventId': event, 'branch': envelope['branch'],
            'head': envelope['startHead'], 'authorityDigest': envelope['authorityDigest'], 'recordDigest': record_digest}
        receipt_raw = b'{"isolatedStage":true}\n'
        stage = self.at(self.prepared.stage)
        receipt_path = stage / 'receipt.json'
        receipt_path.write_bytes(receipt_raw); receipt_path.chmod(0o600)
        bridge = {'version': 1, 'operationId': OP, 'target': TARGET, 'previousRevision': OLD,
            'runId': run_id, 'attemptId': envelope['attemptId'], 'authorizationId': 9001,
            'predispatchBinding': binding, 'sourceIdentity': {'revision': TARGET, 'tree': 'f' * 40},
            'stageReceiptSha256': hashlib.sha256(receipt_raw).hexdigest(),
            'consumerSha256': hashlib.sha256(self.actual_consumer).hexdigest(),
            'writerWrapperSha256': hashlib.sha256(self.helper.read_bytes()).hexdigest()}
        snapshot_path = stage / 'old-installation.json'
        snapshot = json.loads(snapshot_path.read_bytes())
        snapshot['predispatchBridge'] = bridge
        snapshot_path.write_bytes(json.dumps(snapshot, sort_keys=True, separators=(',', ':')).encode() + b'\n')
        snapshot_path.chmod(0o600)
        self.prepared.predispatch_bridge_attempted = True
        self.prepared.predispatch_bridge_request = {'operation': 'finalize-predispatch',
            'repository': envelope['repository'], 'runId': run_id, 'attemptId': envelope['attemptId'],
            'authorizationId': bridge['authorizationId'], 'workflowReadToken': 'synthetic-never-persist-this-token'}
        self.prepared.predispatch_bridge_binding = binding
        self.prepared.cutover_started = True
        self.prepared.predispatch_recovery = lambda _request: {'binding': binding}
        self.prepared.consumer = lambda final=False: {**self.prepared.initial,
            'consumerRestoreRequired': False, 'currentDigest': self.prepared.initial['baselineDigest']}
        return record_path, record, binding

    def retain_predispatch_service_snapshot(self):
        previous = {name: {'active': False, 'enabled': 'enabled', 'load': 'loaded'}
                    for name in ['reviewer', 'production', 'general']}
        gate = json.loads(self.gate.read_bytes())
        gate['previousActive'] = previous
        self.gate.write_text(json.dumps(gate))
        return previous

    def test_prepared_predispatch_bridge_can_abort_before_writer_switch_with_unchanged_proof(self):
        record_path, record, _binding = self.prepare_predispatch_bridge_abort()
        before, inode = record_path.read_bytes(), record_path.stat().st_ino
        result = self.prepared.abort()
        self.assertEqual(result['status'], 'old-open-restored')
        self.assertEqual(self.gate.read_bytes(), self.old_gate)
        self.assertEqual(self.current_revision(), OLD)
        self.assertEqual((record_path.read_bytes(), record_path.stat().st_ino), (before, inode))
        self.assertEqual(json.loads(record_path.read_bytes()), record)
        self.assertFalse(self.prepared.predispatch_bridge_attempted)
        self.assertFalse(self.prepared.cutover_started)

    def test_prepared_predispatch_bridge_can_abort_after_snapshot_when_service_intent_matches(self):
        record_path, record, _binding = self.prepare_predispatch_bridge_abort()
        self.retain_predispatch_service_snapshot()
        before, inode = record_path.read_bytes(), record_path.stat().st_ino
        result = self.prepared.abort()
        self.assertEqual(result['status'], 'old-open-restored')
        self.assertEqual(self.gate.read_bytes(), self.old_gate)
        self.assertEqual(self.current_revision(), OLD)
        self.assertEqual((record_path.read_bytes(), record_path.stat().st_ino), (before, inode))
        self.assertEqual(json.loads(record_path.read_bytes()), record)

    def test_prepared_predispatch_bridge_abort_refuses_changed_service_intent(self):
        self.prepare_predispatch_bridge_abort()
        self.retain_predispatch_service_snapshot()
        self.service_states['fixture-reviewer.service'].update(MainPID='8123',
            ExecMainStartTimestampMonotonic='1200', ActiveState='active', SubState='running')
        before_gate = self.gate.read_bytes()
        with self.assertRaisesRegex(RuntimeError, 'PREDISPATCH_BRIDGE_ABORT_ACTIVITY_UNPROVEN'):
            self.prepared.abort()
        self.assertEqual(self.gate.read_bytes(), before_gate)
        self.assertEqual(self.current_revision(), OLD)

    def test_prepared_bridge_abort_refuses_changed_original_reservation(self):
        record_path, record, _binding = self.prepare_predispatch_bridge_abort()
        before_gate = self.gate.read_bytes()
        record['outcome']['status'] = 'SUCCESS'
        record_path.write_text(json.dumps(record)); record_path.chmod(0o600)
        with self.assertRaisesRegex(RuntimeError, 'PREDISPATCH_BRIDGE_ABORT_ORIGINAL_CHANGED'):
            self.prepared.abort()
        self.assertEqual(self.gate.read_bytes(), before_gate)
        self.assertEqual(self.current_revision(), OLD)

    def test_prepared_bridge_abort_refuses_after_current_writer_switch(self):
        _record_path, _record, binding = self.prepare_predispatch_bridge_abort()
        self.at('/opt/fixture/releases/' + TARGET).mkdir()
        current = self.at('/opt/fixture/current')
        current.unlink(); current.symlink_to('releases/' + TARGET)
        before_gate = self.gate.read_bytes()
        self.prepared.lock_writer()
        with self.assertRaisesRegex(RuntimeError, 'OLD_INSTALLATION_CHANGED'):
            self.prepared.action('abort', source=self.prepared.source, lease=self.prepared.lease_path,
                                 predispatchBinding=binding)
        self.assertEqual(self.gate.read_bytes(), before_gate)
        self.assertEqual(current.resolve(), self.at('/opt/fixture/releases/' + TARGET))

    def current_revision(self):
        return Path(os.readlink(self.at('/opt/fixture/current'))).name

    def test_abort_restores_exact_old_open_bytes_and_preserves_new_manual_history(self):
        self.capture_and_reserve()
        history = self.gate.parent / 'publication-v2'
        history.mkdir(mode=0o700)
        record = history / '71.json'
        record.write_text(json.dumps({'envelope': {'version': 2, 'repository': self.consumer['repository'],
            'consumerDigest': self.digest, 'runId': 71, 'attemptId': 'run-71', 'route': 'manual',
            'issueNumber': 71, 'target': 'issue', 'number': 71}, 'outcome': None}))
        record.chmod(0o600)
        before, inode = record.read_bytes(), record.stat().st_ino
        initial = copy.deepcopy(self.prepared.initial)
        result = self.prepared.abort()
        self.assertEqual(result['status'], 'old-open-restored')
        self.assertEqual(self.gate.read_bytes(), self.old_gate)
        self.assertEqual((record.read_bytes(), record.stat().st_ino), (before, inode))
        self.assertEqual(self.prepared.initial, initial)
        self.assertEqual(self.prepared.desired_digest, 'f' * 64)

    def test_invalid_actual_consumer_cannot_be_opened_using_only_a_restorable_private_clone(self):
        self.capture_and_reserve()
        self.configuration.write_bytes(b'{ invalid actual consumer')
        initial, before = copy.deepcopy(self.prepared.initial), self.gate.read_bytes()
        with self.assertRaisesRegex(RuntimeError, 'INSTALL_PREFLIGHT_ABORT_CONSUMER_UNPROVEN'):
            self.prepared.abort()
        self.assertEqual(self.gate.read_bytes(), before)
        self.assertEqual(self.prepared.initial, initial)
        self.assertEqual(self.configuration.read_bytes(), b'{ invalid actual consumer')

    def test_planned_consumer_repair_may_replace_inode_but_old_source_and_units_must_stay_exact(self):
        self.configuration.write_bytes(b'{ invalid prior consumer')
        self.capture_and_reserve()
        initial_inode = self.configuration.stat().st_ino
        replacement = self.configuration.with_name('planned-repair')
        replacement.write_bytes(self.actual_consumer); replacement.chmod(0o644)
        os.replace(replacement, self.configuration)
        self.assertNotEqual(self.configuration.stat().st_ino, initial_inode)
        self.prepared.abort()
        self.assertEqual(self.gate.read_bytes(), self.old_gate)
        self.assertTrue(self.prepared.initial['consumerRestoreRequired'])

    def test_changed_host_or_old_helper_keeps_the_reserved_gate_closed(self):
        self.capture_and_reserve()
        before = self.gate.read_bytes()
        self.host_state = 'd' * 64
        with self.assertRaisesRegex(RuntimeError, 'HOST_PRECONDITION_CHANGED'):
            self.prepared.abort()
        self.assertEqual(self.gate.read_bytes(), before)
        self.host_state = 'c' * 64
        self.helper.write_text('unexpected old helper mutation')
        with self.assertRaisesRegex(RuntimeError, 'OLD_INSTALLATION_CHANGED'):
            self.prepared.abort()
        self.assertEqual(self.gate.read_bytes(), before)

    def test_critical_state_reads_no_credential_bytes_and_detects_metadata_changes(self):
        original = preflight.read
        def no_secret(path, **kwargs):
            self.assertNotEqual(Path(path), Path('/etc/fixture/writer-credentials/key.pem'))
            return original(path, **kwargs)
        with patch.object(preflight, 'read', side_effect=no_secret):
            before = preflight.critical_state(self.values, root=self.root)
        self.secret.chmod(0o640)
        self.assertNotEqual(preflight.critical_state(self.values, root=self.root), before)

    def test_unplanned_consumer_inode_replacement_keeps_old_gate_closed(self):
        self.capture_and_reserve()
        before = self.gate.read_bytes()
        replacement = self.configuration.with_name('unplanned-replacement')
        replacement.write_bytes(self.actual_consumer); replacement.chmod(0o644)
        os.replace(replacement, self.configuration)
        with self.assertRaisesRegex(RuntimeError, 'OLD_INSTALLATION_CHANGED'):
            self.prepared.abort()
        self.assertEqual(self.gate.read_bytes(), before)

    def test_remote_abort_rechecks_actual_digest_and_actual_kernel_lease(self):
        # An authorized repair excludes only this consumer from the old-byte
        # snapshot, so the immediate actual-consumer proof is still necessary.
        self.configuration.write_bytes(b'invalid originally drifted consumer')
        self.capture_and_reserve()
        self.prepared.lock_writer()
        before = self.gate.read_bytes()
        self.configuration.write_bytes(b'invalid live bytes')
        with self.assertRaisesRegex(RuntimeError, 'ABORT_CONSUMER_UNPROVEN'):
            self.prepared.action('abort', source=self.prepared.source, lease=self.prepared.lease_path)
        self.assertEqual(self.gate.read_bytes(), before)
        self.configuration.write_bytes(self.actual_consumer)
        self.prepared.holder.kill(); self.prepared.holder.wait(timeout=5)
        with self.assertRaises((ValueError, OSError)):
            self.prepared.action('abort', source=self.prepared.source, lease=self.prepared.lease_path)
        self.assertEqual(self.gate.read_bytes(), before)

    def test_reinstall_stage_is_private_bound_and_survives_retirement_of_entire_install_root(self):
        prepared = preflight.PreparedInstall(None, None, self.values, {'revision': TARGET}, OP, reinstall=True)
        self.assertEqual(prepared.stage, '/opt/.fixture-staging/.stage-' + OP)
        request = {'values': self.values, 'action': 'create', 'operation': OP, 'target': TARGET,
                   'stage': prepared.stage, 'reinstall': True}
        preflight.remote(request, root=self.root)
        self.assertEqual(self.at('/opt/.fixture-staging').stat().st_mode & 0o777, 0o700)
        source = self.at(prepared.source)
        source.mkdir(parents=True)
        (source / 'retained-proof').write_text('staged candidate survives')
        self.at('/opt/fixture').rename(self.at('/opt/retired-fixture'))
        self.assertEqual((source / 'retained-proof').read_text(), 'staged candidate survives')
        self.assertIn(prepared.source, prepared.admission_prefix())
        invalid = {**request, 'stage': '/opt/.foreign-staging/.stage-' + OP}
        with self.assertRaisesRegex(RuntimeError, 'STAGE_BINDING_INVALID'):
            preflight.remote(invalid, root=self.root)

    def test_same_operation_retry_preserves_complete_failed_stage_and_creates_fresh_usable_root(self):
        stage = self.at(self.prepared.stage)
        evidence = stage / 'candidate-failure.json'
        evidence.write_bytes(b'{"failed":"synthetic-build","preserve":"all-bytes"}\n')
        evidence.chmod(0o600)
        alias = stage / 'preserved-evidence-alias'
        alias.symlink_to('candidate-failure.json')

        def snapshot(directory):
            return {str(path.relative_to(directory)): (path.lstat().st_ino, path.lstat().st_mode,
                    os.readlink(path) if path.is_symlink() else hashlib.sha256(path.read_bytes()).hexdigest()
                    if path.is_file() else None) for path in directory.rglob('*')}

        original, inode = snapshot(stage), stage.stat().st_ino
        old_gate, old_config = self.gate.read_bytes(), self.configuration.read_bytes()
        result = self.prepared.create()
        self.assertTrue(result['preservedPrevious'])
        self.assertEqual(set(result), {'stage', 'operationId', 'preservedPrevious'})
        preserved = list(stage.parent.glob(stage.name + '.prior-*'))
        self.assertEqual(len(preserved), 1)
        self.assertEqual(preserved[0].stat().st_ino, inode)
        self.assertEqual(snapshot(preserved[0]), original)
        self.assertNotEqual(stage.stat().st_ino, inode)
        self.assertEqual(stage.stat().st_mode & 0o777, 0o700)
        self.assertEqual(list(stage.iterdir()), [])
        fresh = stage / 'fresh-proof'
        with fresh.open('xb') as stream:
            stream.write(b'fresh usable operation stage')
        self.assertEqual(fresh.read_bytes(), b'fresh usable operation stage')
        self.assertEqual(self.gate.read_bytes(), old_gate)
        self.assertEqual(self.configuration.read_bytes(), old_config)

    def test_retry_rejects_alias_foreign_or_nonprivate_stage_without_renaming_it(self):
        stage = self.at(self.prepared.stage)
        original = stage.with_name('preserved-original-stage')
        stage.rename(original)
        stage.symlink_to(original, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, 'RESOURCE_UNSAFE'):
            self.prepared.create()
        self.assertTrue(stage.is_symlink())
        stage.unlink()
        original.rename(stage)
        for mode, owner in [(0o770, 0), (0o750, 0), (0o700, 65534)]:
            with self.subTest(mode=mode, owner=owner):
                stage.chmod(mode)
                os.chown(stage, owner, 0)
                try:
                    with self.assertRaisesRegex(RuntimeError, 'RESOURCE_UNSAFE|STAGE_UNSAFE'):
                        self.prepared.create()
                    self.assertTrue(stage.is_dir())
                    self.assertEqual(list(stage.parent.glob(stage.name + '.prior-*')), [])
                finally:
                    os.chown(stage, 0, 0)
                    stage.chmod(0o700)

    def test_same_operation_reinstall_retry_keeps_the_sibling_stage_and_old_runtime_separate(self):
        prepared = preflight.PreparedInstall(None, None, self.values, {'revision': TARGET}, OP, reinstall=True)
        request = {'values': self.values, 'action': 'create', 'operation': OP, 'target': TARGET,
                   'stage': prepared.stage, 'reinstall': True}
        first = preflight.remote(request, root=self.root)
        self.assertFalse(first['preservedPrevious'])
        stage = self.at(prepared.stage)
        evidence = stage / 'failed-preflight'
        evidence.write_bytes(b'preserve reinstall stage')
        inode = evidence.stat().st_ino
        old_current = self.at('/opt/fixture/current').lstat().st_ino
        self.assertTrue(preflight.remote(request, root=self.root)['preservedPrevious'])
        previous, = stage.parent.glob(stage.name + '.prior-*')
        self.assertEqual((previous / evidence.name).stat().st_ino, inode)
        self.assertEqual((previous / evidence.name).read_bytes(), b'preserve reinstall stage')
        self.assertEqual(self.at('/opt/fixture/current').lstat().st_ino, old_current)
        self.assertEqual(list(stage.iterdir()), [])

    def test_retry_never_rotates_a_live_actual_writer_holder_source_or_receipt(self):
        holder = self.holder(self.prepared)
        stage, lease = self.at(self.prepared.stage), self.at(self.prepared.lease_path)
        before = stage.stat().st_ino, lease.stat().st_ino, lease.read_bytes()
        with self.assertRaisesRegex(RuntimeError, 'STAGE_WRITER_GUARD_LIVE'):
            self.prepared.create()
        self.assertIsNone(holder.poll())
        self.assertEqual((stage.stat().st_ino, lease.stat().st_ino, lease.read_bytes()), before)
        self.assertEqual(list(stage.parent.glob(stage.name + '.prior-*')), [])

    def test_retry_preserves_proven_dead_writer_lease_bytes_and_inode(self):
        holder = self.holder(self.prepared)
        stage, lease = self.at(self.prepared.stage), self.at(self.prepared.lease_path)
        before = stage.stat().st_ino, lease.stat().st_ino, lease.read_bytes()
        holder.kill(); holder.wait(timeout=5); holder.stdin.close()
        self.assertTrue(lease.exists())
        result = self.prepared.create()
        self.assertTrue(result['preservedPrevious'])
        preserved, = stage.parent.glob(stage.name + '.prior-*')
        self.assertEqual((preserved.stat().st_ino, (preserved / lease.name).stat().st_ino,
                          (preserved / lease.name).read_bytes()), before)
        self.assertEqual(list(stage.iterdir()), [])

    def test_dead_lease_pid_cannot_hide_an_actual_kernel_guard_on_its_lock_inode(self):
        holder = self.holder(self.prepared)
        stage, lease = self.at(self.prepared.stage), self.at(self.prepared.lease_path)
        before = stage.stat().st_ino, lease.read_bytes()
        holder.kill(); holder.wait(timeout=5); holder.stdin.close()
        other = copy.copy(self.prepared)
        other.lease_path = str(Path(other.stage) / 'second-guard.json')
        replacement = self.holder(other)
        with self.assertRaisesRegex(RuntimeError, 'STAGE_WRITER_GUARD_LIVE'):
            self.prepared.create()
        self.assertIsNone(replacement.poll())
        self.assertEqual((stage.stat().st_ino, lease.read_bytes()), before)
        self.assertEqual(list(stage.parent.glob(stage.name + '.prior-*')), [])

    def test_unknown_or_aliased_writer_receipt_stops_retry_without_touching_evidence(self):
        stage, lease = self.at(self.prepared.stage), self.at(self.prepared.lease_path)
        lease.write_bytes(b'{ unknown partial writer receipt')
        lease.chmod(0o600)
        before = lease.stat().st_ino, lease.read_bytes()
        with self.assertRaisesRegex(RuntimeError, 'STAGE_WRITER_GUARD_UNPROVEN'):
            self.prepared.create()
        self.assertEqual((lease.stat().st_ino, lease.read_bytes()), before)
        lease.unlink()
        lease.symlink_to(self.lock)
        with self.assertRaisesRegex(RuntimeError, 'RESOURCE_UNSAFE'):
            self.prepared.create()
        self.assertTrue(lease.is_symlink())
        self.assertEqual(list(stage.parent.glob(stage.name + '.prior-*')), [])

    def retained_replacement(self):
        # The production branch obtains this authority from the independently
        # tested owning continuation adapter. Model its already-proved archive
        # here, with a real absent current and the real retained admission gate.
        candidate = self.root / 'retained-candidate'
        shutil.move(self.at(self.prepared.source), candidate)
        self.at('/opt/fixture').rename(self.at('/opt/.fixture-retired-' + OLD + '-' + TARGET))
        self.at('/opt/fixture').mkdir(mode=0o755)
        self.prepared.source = str(candidate)
        self.prepared.stage = str(self.root)
        self.prepared.lease_path = str(self.root / 'retained-writer-lease.json')
        self.prepared.reinstall = True
        self.prepared.desired_digest = self.digest
        gate = json.loads(self.old_gate)
        gate.update(phase='recovery-required', operationId=OP, target=TARGET)
        self.gate.write_text(json.dumps(gate))
        return {'state': 'CONTINUATION_READY', 'sourceRevision': OLD, 'targetRevision': TARGET,
            'lifecycleOperation': OP, 'completed': False, 'journalSha256': 'd' * 64,
            'allowedInventoryBlockers': ['clean-reinstall-recovery-present;inspect-before-retry',
                'production-operation-recovery-present;inspect-before-retry', 'installed-identity-invalid']}

    def test_retained_replacement_reads_missing_current_without_restoring_or_opening_it(self):
        proof = self.retained_replacement()
        before = self.gate.read_bytes(), self.configuration.read_bytes()
        receipt = self.prepared.consumer_retained(proof)
        self.assertEqual(receipt['phase'], 'recovery-required')
        self.assertFalse(receipt['consumerRestoreRequired'])
        self.assertEqual(receipt['currentDigest'], self.digest)
        self.assertEqual(self.prepared.retained_proof, proof)
        self.assertFalse(self.prepared.captured)
        self.assertFalse(self.at('/opt/fixture/current').exists())
        self.prepared.lock_writer()
        self.assertEqual(self.prepared.consumer_retained(proof, final=True), receipt)
        self.assertEqual((self.gate.read_bytes(), self.configuration.read_bytes()), before)
        self.assertFalse((self.root / 'old-installation.json').exists())
        with self.lock.open('rb') as stream:
            import fcntl
            with self.assertRaises(BlockingIOError):
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_retained_replacement_rejects_changed_authority_new_digest_and_open_gate(self):
        proof = self.retained_replacement()
        before = self.gate.read_bytes()
        for changed in [{**proof, 'lifecycleOperation': '22345678-1234-1234-1234-123456789abc'},
                        {**proof, 'targetRevision': 'c' * 40}, {**proof, 'journalSha256': 'invalid'}]:
            with self.assertRaisesRegex(RuntimeError, 'RETAINED_REPLACEMENT_AUTHORITY_UNPROVEN'):
                self.prepared.consumer_retained(changed)
        self.prepared.desired_digest = 'f' * 64
        with self.assertRaisesRegex(RuntimeError, 'RETAINED_REPLACEMENT_STATE_UNPROVEN'):
            self.prepared.consumer_retained(proof)
        self.assertIsNone(self.prepared.initial)
        self.prepared.desired_digest = self.digest
        self.gate.write_bytes(self.old_gate)
        with self.assertRaisesRegex(RuntimeError, 'RETAINED_REPLACEMENT_STATE_UNPROVEN'):
            self.prepared.consumer_retained(proof)
        self.assertEqual(self.gate.read_bytes(), self.old_gate)
        self.gate.write_bytes(before)
        self.prepared.consumer_retained(proof)
        with self.assertRaisesRegex(RuntimeError, 'RETAINED_REPLACEMENT_AUTHORITY_CHANGED'):
            self.prepared.consumer_retained({**proof, 'journalSha256': 'e' * 64})
        self.lock.unlink()
        with self.assertRaisesRegex(RuntimeError, 'RETAINED_CONSUMER_UNPROVEN'):
            self.prepared.consumer_retained(proof)
        self.assertFalse(self.lock.exists())

    def test_retained_final_requires_live_kernel_lease_and_reauthenticates_actual_consumer(self):
        proof = self.retained_replacement()
        self.prepared.consumer_retained(proof)
        with self.assertRaisesRegex(RuntimeError, 'WRITER_LOCK_MISSING'):
            self.prepared.consumer_retained(proof, final=True)
        self.prepared.lock_writer()
        initial, before = copy.deepcopy(self.prepared.initial), self.gate.read_bytes()
        self.configuration.write_bytes(b'invalid actual retained consumer')
        with self.assertRaisesRegex(RuntimeError, 'RETAINED_CONSUMER_UNPROVEN'):
            self.prepared.consumer_retained(proof, final=True)
        self.configuration.write_bytes(self.actual_consumer)
        self.prepared.holder.kill(); self.prepared.holder.wait(timeout=5)
        with self.assertRaisesRegex(RuntimeError, 'WRITER_LOCK_MISSING'):
            self.prepared.consumer_retained(proof, final=True)
        self.assertEqual(self.prepared.initial, initial)
        self.assertEqual(self.gate.read_bytes(), before)

    def test_retained_same_digest_keeps_manual_history_but_rejects_active_or_unknown_automatic_work(self):
        proof = self.retained_replacement()
        program = r'''
import {pathToFileURL} from 'node:url';
const [source,configuration,kind] = process.argv.slice(1);
const {loadConsumer,consumerDigest} = await import(pathToFileURL(source+'/consumer/consumer-config.mjs'));
const {createPublicationStore} = await import(pathToFileURL(source+'/controller/src/attempt-store.mjs'));
const consumer=loadConsumer(configuration), store=createPublicationStore(consumer.paths.claimRoot+'/publication-v2');
const runId=kind==='manual'?61:62;
const envelope={version:2,consumerDigest:consumerDigest(consumer),repository:consumer.repository,
  runId,attemptId:'run-'+runId,route:kind==='manual'?'manual':'auto',issueNumber:42,target:'issue',number:42};
await store.put(runId,{envelope,outcome:null,...(kind==='manual'?{}:
  {controllerLifecycle:{version:1,status:kind==='active'?'active':'complete'}})});
'''
        history = self.lock.parent / 'publication-v2'
        def seed(kind):
            result = subprocess.run(['/usr/bin/node', '--input-type=module', '-e', program,
                self.prepared.source, str(self.configuration), kind], text=True, capture_output=True, timeout=15,
                env={'PATH': '/usr/bin:/bin', 'RELAY_CONSUMER_CONFIG': str(self.configuration)})
            self.assertEqual(result.returncode, 0, result.stderr)
        def snapshot():
            return {path.name: (path.read_bytes(), path.stat().st_ino) for path in history.glob('*.json')}
        seed('manual')
        before = snapshot(), self.gate.read_bytes()
        self.prepared.consumer_retained(proof)
        self.assertEqual((snapshot(), self.gate.read_bytes()), before)
        for kind in ['active', 'unknown']:
            seed(kind)
            before = snapshot(), self.gate.read_bytes()
            with self.assertRaisesRegex(RuntimeError, 'RETAINED_REPLACEMENT_STATE_UNPROVEN'):
                self.prepared.consumer_retained(proof)
            self.assertEqual((snapshot(), self.gate.read_bytes()), before)


class PreparedProtocolTests(unittest.TestCase):
    def prepared(self):
        return preflight.PreparedInstall(None, None, {'relay_release_root': '/opt/fixture/releases'}, {'revision': TARGET}, OP)

    def test_safe_host_stdout_preserves_only_the_bounded_error_contract(self):
        prepared = self.prepared()
        report = {'version': 1, 'status': 'FAIL', 'error_code': 'HOST_TLS_ISSUANCE_STAGE_REQUIRED',
                  'resource': 'tls-certificate', 'next_action': 'prepare-product-owned-tls-material'}
        result = subprocess.CompletedProcess([], 1, json.dumps(report), '')
        with patch('ansible_transport.run_target', return_value=result):
            with self.assertRaisesRegex(RuntimeError, 'HOST_TLS_ISSUANCE_STAGE_REQUIRED') as caught:
                prepared.execute(['fixed-helper'])
        self.assertIn(report['next_action'], caught.exception.next_action)
        hostile = {**report, 'resource': '/private/path'}
        with patch('ansible_transport.run_target', return_value=subprocess.CompletedProcess([], 1, json.dumps(hostile), '')):
            with self.assertRaisesRegex(RuntimeError, '^INSTALL_PREFLIGHT_PREREQUISITE_UNPROVEN$') as caught:
                prepared.execute(['fixed-helper'])
        self.assertNotIn('/private/path', str(caught.exception))

    def test_native_runner_resource_keeps_its_code_without_exposing_unsafe_resources(self):
        prepared = self.prepared()
        report = {'version': 1, 'status': 'FAIL', 'error_code': 'HOST_DESTINATION_PARENT_UNSAFE',
                  'resource': 'member-primary-runner-bin-Runner.Listener',
                  'next_action': 'repair-prerequisite-on-existing-installation'}
        result = subprocess.CompletedProcess([], 1, json.dumps(report), '')
        with patch('ansible_transport.run_target', return_value=result):
            with self.assertRaisesRegex(RuntimeError, '^HOST_DESTINATION_PARENT_UNSAFE$') as caught:
                prepared.execute(['fixed-helper'])
        self.assertEqual(caught.exception.resource, report['resource'])
        for resource in ('/private/Runner.Listener', 'Runner Listener', 'Runner.Listener\nprivate', 'R' * 129):
            with self.subTest(resource=resource):
                hostile = {**report, 'resource': resource}
                result = subprocess.CompletedProcess([], 1, json.dumps(hostile), '')
                with patch('ansible_transport.run_target', return_value=result):
                    with self.assertRaisesRegex(RuntimeError, '^INSTALL_PREFLIGHT_PREREQUISITE_UNPROVEN$') as caught:
                        prepared.execute(['fixed-helper'])
                self.assertFalse(hasattr(caught.exception, 'resource'))
                self.assertNotIn(resource, caught.exception.next_action)

    def test_holder_uses_qualified_four_argument_transport_and_fresh_final_needs_no_initial_consumer(self):
        prepared = self.prepared()
        prepared.initial = {'lockPath': '/claims/publication-v2.lock', 'baselineDigest': 'a' * 64}
        holder = object()
        with patch('ansible_transport.hold_target', return_value=holder) as hold:
            prepared.lock_writer()
        self.assertEqual(len(hold.call_args.args), 4)
        self.assertEqual(hold.call_args.kwargs, {})
        prepared = self.prepared()
        calls = []
        prepared.host = lambda **kwargs: calls.append(('host', kwargs))
        prepared.verify_stage = lambda: calls.append(('stage', {}))
        prepared.final(fresh=True)
        self.assertEqual(calls, [('host', {'final': True}), ('stage', {})])


@unittest.skipUnless(sys.platform == 'linux' and os.geteuid() == 0, 'actual root Linux required')
class PackageRevalidationTests(unittest.TestCase):
    def setUp(self):
        path = ROOT / 'deploy/ansible/tests/test_intent_artifact_stage.py'
        spec = importlib.util.spec_from_file_location('install_preflight_artifact_fixture', path)
        artifact = importlib.util.module_from_spec(spec); spec.loader.exec_module(artifact)
        self.artifact = artifact
        fixture = artifact.IntentArtifactStageTests('test_exact_git_archive_and_modes_are_proved_before_private_materialization')
        fixture.setUp(); self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        receipt = fixture.prepare()
        package_path = ROOT / 'deploy/ansible/roles/relay_runner/files/relay-intent-package.py'
        package_spec = importlib.util.spec_from_file_location('install_preflight_package_fixture', package_path)
        package = importlib.util.module_from_spec(package_spec); package_spec.loader.exec_module(package)
        self.package = package
        # The live runner identity can traverse its namespace while the sealed
        # .stage subtree remains root-only for artifact revalidation.
        fixture.parent.chmod(0o755)
        live = fixture.parent / 'live'
        live.mkdir()
        runner = live / 'runner'
        runner.mkdir()
        cache = live / 'cache'; cache.mkdir()
        for kind in ['runner', 'codex']:
            root = fixture.root / (kind + '-package')
            root.mkdir(mode=0o700)
            if kind == 'runner':
                (root / 'archive.tar.gz').write_bytes(b'synthetic already-validated archive bytes')
                payload = root / 'payload'
                for name in ['config.sh', 'run.sh', 'bin/Runner.Listener', 'externals/node24/bin/node']:
                    path = payload / name; path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text('#!/bin/sh\nexit 0\n'); path.chmod(0o755)
                    target = runner / name; target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(path, target); target.chmod(0o755)
                    if name == 'bin/Runner.Listener':
                        target.write_text('#!/bin/sh\nprintf "2.336.0\\n"\n')
                digest = hashlib.sha256((root / 'archive.tar.gz').read_bytes()).hexdigest()
                version = '2.336.0'
            else:
                path = root / 'package-home/packages/release/codex'
                path.parent.mkdir(parents=True)
                path.write_text('synthetic sealed Codex payload')
                version, digest = '0.160.0', '-'
            manifest = {**package.binding(kind, OP, version, digest), 'treeSha256': package.tree(root, skip_manifest=True)}
            (root / 'manifest.json').write_text(json.dumps(manifest)); (root / 'manifest.json').chmod(0o600)
            receipt['packages'][kind] = manifest
        (fixture.root / 'receipt.json').write_text(json.dumps(receipt))
        self.values = {'relay_namespace': 'fixture', 'relay_install_root': str(live),
            'relay_release_root': str(fixture.parent), 'relay_config_root': str(live / 'config'),
            'relay_state_root': str(live / 'state'), 'relay_runner_user': 'nobody',
            'relay_general_runner_user': 'nobody', 'relay_reviewer_user': 'nobody', 'relay_codex_user': 'nobody',
            'relay_runner_root': str(runner), 'relay_runner_package_cache_root': str(cache),
            'relay_codex_package_home': str(live / 'codex-home'),
            'relay_codex_package_install_dir': str(live / 'codex-bin'),
            'relay_codex_binary_path': str(live / 'codex'), 'relay_runner_service_name': 'fixture-runner.service'}
        self.prepared = preflight.PreparedInstall(None, None, self.values, fixture.identity, OP)
        def execute(argv, *, payload=None, timeout=180):
            result = subprocess.run(argv, input=json.dumps(payload), text=True, capture_output=True, timeout=timeout)
            if result.returncode:
                raise RuntimeError(result.stderr.strip())
            return json.loads(result.stdout)
        self.prepared.execute = execute

    def test_both_package_payloads_are_verified_before_first_gate_effect_and_final_revalidation(self):
        receipt = self.prepared.verify_stage()
        self.assertEqual(receipt['packages'].keys(), {'runner', 'codex'})
        for kind, relative in [('runner', 'payload/config.sh'), ('codex', 'package-home/packages/release/codex')]:
            with self.subTest(kind=kind):
                path = self.fixture.root / (kind + '-package') / relative
                original = path.read_bytes(); path.write_bytes(original + b'tampered')
                with self.assertRaisesRegex(RuntimeError, 'INTENT_PACKAGE_STAGE_CHANGED'):
                    self.prepared.verify_stage()
                self.fixture.assert_old_available()
                path.write_bytes(original)

    def test_resealing_a_changed_package_cannot_replace_its_original_artifact_fact(self):
        self.prepared.verify_stage()
        root = self.fixture.root / 'codex-package'
        (root / 'package-home/packages/release/codex').write_text('resealed replacement')
        manifest_path = root / 'manifest.json'
        changed = json.loads(manifest_path.read_bytes())
        changed['treeSha256'] = self.package.tree(root, skip_manifest=True)
        manifest_path.write_text(json.dumps(changed))
        with self.assertRaisesRegex(RuntimeError, 'PACKAGE_RECEIPT_CHANGED'):
            self.prepared.verify_stage()
        self.fixture.assert_old_available()

    def test_unsafe_late_target_collision_is_rejected_without_first_destination_write(self):
        self.prepared.verify_stage()
        destination = self.fixture.parent / self.fixture.identity['revision']
        destination.mkdir()
        (destination / 'unexpected-link').symlink_to('/etc/passwd')
        before = sorted(path.name for path in destination.iterdir())
        with self.assertRaisesRegex(RuntimeError, 'INTENT_STAGE_'):
            self.prepared.verify_stage()
        self.assertEqual(sorted(path.name for path in destination.iterdir()), before)
        self.fixture.assert_old_available()


if __name__ == '__main__':
    unittest.main()
