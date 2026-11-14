"""The precise post-rename frontier, with original protected bytes/processes."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
from types import SimpleNamespace

import pytest

from test_bounded_install_recovery import incident, BASELINE, NODE, OPERATION, ROOT, write
import partial_install_recovery as partial

pytestmark = pytest.mark.skipif(sys.platform != 'linux' or os.geteuid() != 0,
    reason='root native Linux filesystem proof')


def test_old_runtime_observer_hashes_actual_proc_executable_and_refuses_another_product(monkeypatch):
    monkeypatch.setattr(partial.subprocess, 'check_output', lambda *a, **k: str(os.getpid()) + '\n')
    with Path('/proc/self/exe').open('rb') as stream:
        expected = hashlib.file_digest(stream, 'sha256').hexdigest()
    observed = partial.old_reviewer('synthetic-test-only', expected)
    assert observed['pid'] == os.getpid() and observed['startTicks'] > 0
    with pytest.raises(ValueError, match='OLD_REVIEWER_RUNTIME_UNPROVEN'):
        partial.old_reviewer('synthetic-test-only', '0' * 64)


def test_publication_failure_keeps_bounded_cause_and_removes_private_remote_details(monkeypatch):
    report = {'error_code': 'CONSUMER_PUBLICATION_TRANSITION_REQUIRES_RECOVERY',
        'controller_diagnostic': {'action': 'consumer-transition', 'failure': 'nonzero_exit',
            'code': 'ADMISSION_NOT_DRAINED', 'exit_code': 1, 'path': '/private/diagnostic',
            'message': 'private response body'}}
    monkeypatch.setattr(partial, 'run_target', lambda *a, **k:
        SimpleNamespace(returncode=1, stdout=json.dumps(report)))
    with pytest.raises(ValueError, match='CONSUMER_PUBLICATION_TRANSITION_REQUIRES_RECOVERY') as caught:
        partial.publish(SimpleNamespace(target={}, key=None), ['fixed-fixture-command'])
    assert caught.value.controller_diagnostic == {'action': 'consumer-transition', 'failure': 'nonzero_exit',
        'code': 'ADMISSION_NOT_DRAINED', 'exit_code': 1}


def test_controller_acceptance_uses_original_policy_and_native_public_main(monkeypatch, tmp_path):
    controller, accepted = 'a' * 40, 'b' * 40
    binding = {'gitConfigReceipt': {'source_policy': 'accepted-ancestor',
        'product_repository': 'example/product'}}
    requests = []
    def native(argv, **options):
        requests.append(argv)
        return (accepted + '\trefs/heads/main\n')
    monkeypatch.setattr(partial.subprocess, 'check_output', native)
    monkeypatch.setattr(partial.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=0))
    assert partial.accepted_controller(tmp_path, binding, controller)['acceptedMain'] == accepted
    assert requests[0][-3:] == ['--exit-code', 'https://github.com/example/product.git', 'refs/heads/main']
    monkeypatch.setattr(partial.subprocess, 'run', lambda argv, **k:
        SimpleNamespace(returncode=1 if 'merge-base' in argv else 0))
    with pytest.raises(ValueError, match='CONTROLLER_NOT_ACCEPTED'):
        partial.accepted_controller(tmp_path, binding, controller)
    requests.clear()
    binding['gitConfigReceipt']['source_policy'] = 'test-qualified-exact'
    assert partial.accepted_controller(tmp_path, binding, controller)['policy'] == 'test-qualified-exact'
    assert requests == []


def test_depth_one_owner_source_fetches_authenticated_ancestry_without_root_credentials(monkeypatch, tmp_path):
    controller = 'a' * 40
    calls = []
    def output(argv, **options):
        calls.append((argv, options))
        return controller + '\trefs/heads/main\n' if 'ls-remote' in argv else 'true\n'
    monkeypatch.setattr(partial.subprocess, 'check_output', output)
    def run(argv, **options):
        calls.append((argv, options))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(partial.subprocess, 'run', run)
    binding = {'gitConfigReceipt': {'product_repository': 'example/product', 'source_policy': 'accepted-main'}}
    assert partial.accepted_controller(tmp_path, binding, controller)['revision'] == controller
    fetched = [(argv, options) for argv, options in calls if '--unshallow' in argv]
    assert len(fetched) == 1
    argv, options = fetched[0]
    assert argv[-2:] == ['https://github.com/example/product.git', controller]
    assert options['env']['HOME'] == str(tmp_path)
    assert options['env']['GIT_CONFIG_GLOBAL'] == '/dev/null'


def frontier(incident):
    path = incident.release / 'artifact-manifest.json'
    old = json.loads(path.read_bytes()); old['reviewerBinarySha256'] = 'a' * 64; write(path, old)
    proof = incident.helper('inspect')
    receipt = incident.helper('begin', proof)
    incident.native('recovery-target', options={'operationId': OPERATION, 'target': incident.revision})
    incident.native('phase', options={'operationId': OPERATION, 'phase': 'applying'})
    with pytest.raises(ValueError, match='TRANSITION_REQUIRES_RECOVERY'):
        incident.publish(interrupt=True)
    incident.final_artifacts()
    path = incident.install / 'releases' / incident.revision / 'artifact-manifest.json'
    desired = json.loads(path.read_bytes()); desired['reviewerBinarySha256'] = 'b' * 64; write(path, desired)
    return receipt


@pytest.mark.parametrize('digest_advanced', [False, True])
def test_partial_frontier_proves_frozen_pair_and_preserves_old_gate_backend_history(incident, digest_advanced):
    receipt = frontier(incident)
    if digest_advanced:
        gate = json.loads(incident.gate.read_bytes())
        gate['consumerDigest'] = receipt['desiredDigest']
        write(incident.gate, gate)
    before, history = incident.snapshot(), incident.history()
    value = partial.inspect(incident.config, OPERATION, BASELINE, root=incident.root)
    assert value['receipt'] == receipt
    assert value['gate']['phase'] == 'applying'
    assert (value['gate']['consumerDigest'] == receipt['desiredDigest']) is digest_advanced
    assert value['sourceIdentity']['revision'] == receipt['binding']['desiredRevision']
    assert incident.snapshot() == before and incident.history() == history
    assert json.loads(incident.backend.read_bytes())['target_head'] == BASELINE


@pytest.mark.parametrize('change', ['backup', 'consumer', 'pair', 'backend', 'gate', 'operation', 'archive', 'same-runtime'])
def test_partial_frontier_rejects_altered_or_ambiguous_evidence_before_effects(incident, change):
    frontier(incident)
    config = copy.deepcopy(incident.config)
    operation = OPERATION
    if change == 'backup':
        write(incident.backup, b'{}')
    elif change == 'consumer':
        # Same resource identity is insufficient to reinterpret unknown bytes.
        config['consumer']['defaultProfile']['effort'] = 'low'
    elif change == 'pair':
        manifest = incident.install / 'releases' / incident.revision / 'artifact-manifest.json'
        value = json.loads(manifest.read_bytes())
        value['gitConfigReceipt']['config_sha'] = 'd' * 40
        write(manifest, value)
    elif change == 'backend':
        write(incident.backend, b'{}')
    elif change == 'gate':
        value = json.loads(incident.gate.read_bytes()); value['phase'] = 'verified'
        value['verifiedRevision'] = incident.revision; write(incident.gate, value)
    elif change == 'operation':
        operation = '22345678-1234-4234-8234-123456789abc'
    elif change == 'archive':
        archive = incident.receipt.with_name(incident.receipt.name.removesuffix('.json') + '.original.json')
        write(archive, incident.backend.read_bytes())
    else:
        path = incident.install / 'releases' / incident.revision / 'artifact-manifest.json'
        value = json.loads(path.read_bytes()); value['reviewerBinarySha256'] = 'a' * 64; write(path, value)
    before, history = incident.snapshot(), incident.history()
    with pytest.raises((ValueError, FileNotFoundError)):
        partial.inspect(config, operation, BASELINE, root=incident.root)
    assert incident.snapshot() == before and incident.history() == history


def maintained_frontier(incident, phase='recovery-required', *, unchanged_consumer=False):
    # Original gate-only evidence stays absent; Begin has since created the
    # exact desired Apply record. The original maintenance declaration is saved
    # by the existing reservation, never inferred from live activity.
    incident.backend.unlink()
    incident.binding['runnerMaintenance'] = {'operationId': OPERATION, 'retainedTarget': BASELINE,
        'runners': {'production': {'runnerId': 55, 'runnerName': 'fixture-production'}}}
    if unchanged_consumer:
        incident.config['consumer'] = copy.deepcopy(incident.original['consumer'])
        raw = (json.dumps(incident.config, sort_keys=True) + '\n').encode()
        incident.binding['gitConfigReceipt']['config_sha256'] = hashlib.sha256(raw).hexdigest()
        path = incident.release / 'artifact-manifest.json'
        manifest = json.loads(path.read_bytes()); manifest['reviewerBinarySha256'] = 'a' * 64
        write(path, manifest)
        receipt = incident.helper('begin', incident.helper('inspect'))
        incident.native('recovery-target', options={'operationId': OPERATION, 'target': incident.revision})
        incident.native('phase', options={'operationId': OPERATION, 'phase': 'applying'})
        incident.final_artifacts()
    else:
        receipt = frontier(incident)
    write(incident.backend, {'schemaVersion': '1', 'state': 'RECOVERY_REQUIRED',
        'phase': 'apply', 'target_head': incident.revision})
    publication = incident.publish()
    if unchanged_consumer:
        assert publication['status'] == 'UNCHANGED' and not incident.backup.exists()
        (incident.config_root / ('.consumer-' + OPERATION + '.desired.json')).unlink()
    path = incident.install / 'releases' / incident.revision / 'artifact-manifest.json'
    manifest = json.loads(path.read_bytes()); manifest['reviewerBinarySha256'] = 'a' * 64
    write(path, manifest)
    if phase != 'applying':
        incident.native('phase', options={'operationId': OPERATION, 'phase': phase})
    return receipt


@pytest.mark.parametrize('phase', ['recovery-required', 'applying'])
def test_same_artifact_maintenance_is_not_a_post_apply_configuration_transition(incident, phase):
    # Reserve a valid operation for the already installed exact artifact; do
    # not manufacture a transitioned receipt by rewriting protected history.
    incident.config = copy.deepcopy(incident.original)
    binding = incident.binding
    binding.update(controllerRevision=BASELINE, desiredRevision=BASELINE,
        runnerMaintenance={'operationId': OPERATION, 'retainedTarget': BASELINE,
            'runners': {'production': {'runnerId': 55, 'runnerName': 'fixture-production'}}})
    binding['gitConfigReceipt'].update(product_sha=BASELINE,
        config_sha256=hashlib.sha256((json.dumps(incident.config, sort_keys=True) + '\n').encode()).hexdigest())
    path = incident.release / 'artifact-manifest.json'
    manifest = json.loads(path.read_bytes())
    manifest.update(reviewerBinarySha256='a' * 64, gitConfigReceipt=binding['gitConfigReceipt'])
    write(path, manifest)
    receipt = incident.helper('begin', incident.helper('inspect'))
    if phase == 'applying':
        incident.native('phase', options={'operationId': OPERATION, 'phase': phase})
    assert incident.helper('inspect') == receipt
    before, history, reserved = incident.snapshot(), incident.history(), incident.receipt.read_bytes()
    with pytest.raises(ValueError, match='PARTIAL_INSTALL_RUNTIME_ADOPTION_AMBIGUOUS'):
        partial.inspect(incident.config, OPERATION, BASELINE, root=incident.root)
    assert incident.snapshot() == before and incident.history() == history
    assert incident.receipt.read_bytes() == reserved


@pytest.mark.parametrize('phase', ['recovery-required', 'applying'])
def test_noop_consumer_publication_needs_no_fabricated_backup_or_desired_file(incident, phase):
    receipt = maintained_frontier(incident, phase, unchanged_consumer=True)
    desired = incident.config_root / ('.consumer-' + OPERATION + '.desired.json')
    before, history, original = incident.snapshot(), incident.history(), incident.receipt.read_bytes()
    value = partial.inspect(incident.config, OPERATION, BASELINE, root=incident.root)
    assert value['reviewerConfigAdoption'] is True and value['consumerUnchanged'] is True
    assert value['consumerSha256'] == receipt['original']['consumerSha256']
    assert value['gate']['consumerDigest'] == receipt['desiredDigest']
    assert incident.receipt.read_bytes() == original and incident.snapshot() == before and incident.history() == history
    assert not incident.backup.exists() and not desired.exists()


@pytest.mark.parametrize('change', ['consumer', 'gate-digest', 'backup-symlink', 'desired-symlink'])
def test_noop_consumer_missing_evidence_exception_rejects_drift_and_dangling_links(incident, change):
    maintained_frontier(incident, unchanged_consumer=True)
    if change == 'consumer':
        consumer = json.loads(incident.consumer.read_bytes()); consumer['defaultProfile']['effort'] = 'low'
        write(incident.consumer, consumer, 0o644)
    elif change == 'gate-digest':
        gate = json.loads(incident.gate.read_bytes()); gate['consumerDigest'] = 'a' * 64
        write(incident.gate, gate)
    else:
        path = incident.backup if change == 'backup-symlink' else (
            incident.config_root / ('.consumer-' + OPERATION + '.desired.json'))
        path.symlink_to('missing-private-evidence')
    before, history, original = incident.snapshot(), incident.history(), incident.receipt.read_bytes()
    with pytest.raises((ValueError, OSError)):
        partial.inspect(incident.config, OPERATION, BASELINE, root=incident.root)
    assert incident.receipt.read_bytes() == original and incident.snapshot() == before and incident.history() == history


@pytest.mark.parametrize('phase', ['recovery-required', 'applying'])
def test_post_apply_maintained_frontier_keeps_original_absence_and_selects_config_adoption(incident, phase):
    receipt = maintained_frontier(incident, phase)
    before, history, reserved = incident.snapshot(), incident.history(), incident.receipt.read_bytes()
    value = partial.inspect(incident.config, OPERATION, BASELINE, root=incident.root)
    assert value['reviewerConfigAdoption'] is True and value['receipt'] == receipt
    assert value['gate']['phase'] == phase and value['gate']['consumerDigest'] == receipt['desiredDigest']
    assert value['receipt']['original']['backendAbsent'] is True
    assert value['originalReviewerSha256'] == value['manifest']['reviewerBinarySha256']
    assert incident.snapshot() == before and incident.history() == history
    assert incident.receipt.read_bytes() == reserved


@pytest.mark.parametrize('change', ['backend-absent', 'backend-target', 'gate-digest', 'current', 'consumer'])
def test_post_apply_config_adoption_refuses_incomplete_or_changed_frontier(incident, change):
    receipt = maintained_frontier(incident)
    if change == 'backend-absent':
        incident.backend.unlink()
    elif change == 'backend-target':
        record = json.loads(incident.backend.read_bytes()); record['target_head'] = BASELINE
        write(incident.backend, record)
    elif change == 'gate-digest':
        gate = json.loads(incident.gate.read_bytes()); gate['consumerDigest'] = incident.digest
        write(incident.gate, gate)
    elif change == 'current':
        current = incident.install / 'current'; current.unlink(); current.symlink_to('releases/' + BASELINE)
    else:
        consumer = json.loads(incident.consumer.read_bytes()); consumer['defaultProfile']['effort'] = 'low'
        write(incident.consumer, consumer, 0o644)
    before, history, reserved = incident.snapshot(), incident.history(), incident.receipt.read_bytes()
    with pytest.raises((ValueError, FileNotFoundError)):
        partial.inspect(incident.config, OPERATION, BASELINE, root=incident.root)
    assert incident.snapshot() == before and incident.history() == history
    assert incident.receipt.read_bytes() == reserved and receipt['original']['backendAbsent'] is True


@pytest.mark.parametrize(('unchanged_consumer', 'blocked'), [
    (False, None), (False, 'unknown-work'), (False, 'writer-lock-lost'),
    (True, None), (True, 'unknown-work'), (True, 'writer-lock-lost')])
def test_same_operation_apply_uses_live_writer_lease_and_current_native_admission(incident, monkeypatch, blocked, unchanged_consumer):
    receipt = maintained_frontier(incident, unchanged_consumer=unchanged_consumer)
    if blocked == 'unknown-work':
        for path in (incident.claims / 'publication-v2').rglob('*.json'):
            record = json.loads(path.read_bytes())
            if record.get('envelope', {}).get('route') == 'manual':
                record['publicationIntent'] = True
                write(path, record)
                break
        else:
            pytest.fail('missing fixture manual publication record')
    gate_before = incident.gate.read_bytes()
    original, history = incident.receipt.read_bytes(), incident.history()
    lease = incident.root / 'config-adoption-writer.json'
    holder = subprocess.Popen([sys.executable, '-I', str(ROOT / 'deploy/writer_lock_lease.py'),
        '--hold', str(incident.lock), str(lease), OPERATION, incident.revision, receipt['desiredDigest']],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        with selectors.DefaultSelector() as events:
            events.register(holder.stdout, selectors.EVENT_READ)
            assert events.select(5), 'Writer holder readiness timed out'
            assert holder.stdout.readline() == 'WRITER_LOCK_READY\n'
        # The current reader executes as a real Node process; only public GitHub
        # observations use the incident fixture's synthetic adapter.
        def probe(*_args, **_options):
            def read(_context):
                try:
                    value = incident.native('preflight',
                        desired=json.loads(json.dumps(incident.config['consumer'], sort_keys=True)))
                except AssertionError:
                    raise ValueError('BOUNDED_RECOVERY_CURRENT_CONTROLLER_PROOF_UNAVAILABLE') from None
                if blocked == 'writer-lock-lost':
                    holder.kill(); holder.wait(timeout=5)
                return value
            return read
        monkeypatch.setattr(partial.bounded, 'fixed_probe', probe)
        native_run = subprocess.run
        def run(argv, **options):
            return native_run([str(NODE), *argv[1:]] if argv[0] == '/usr/bin/node' else argv, **options)
        monkeypatch.setattr(partial.subprocess, 'run', run)
        if blocked:
            code = 'WRITER_LOCK_LEASE_UNPROVEN|/proc/' if blocked == 'writer-lock-lost' else 'CURRENT_CONTROLLER_PROOF_UN'
            with pytest.raises((ValueError, OSError), match=code):
                partial.admission(incident.config, incident.controller, lease, OPERATION, 'apply', root=incident.root)
            assert incident.gate.read_bytes() == gate_before
        else:
            result = partial.admission(incident.config, incident.controller, lease, OPERATION, 'apply', root=incident.root)
            assert result['phase'] == 'applying' and result['target'] == incident.revision
            assert result['operationId'] == OPERATION and result['consumerDigest'] == receipt['desiredDigest']
            assert result['previousActive'] == json.loads(gate_before)['previousActive']
            assert json.loads(incident.gate.read_bytes()) == result
        assert incident.receipt.read_bytes() == original and incident.history() == history
        assert json.loads(incident.backend.read_bytes())['target_head'] == incident.revision
    finally:
        holder.stdin.close()
        holder.wait(timeout=5)
        holder.stdout.close(); holder.stderr.close()


def test_saved_maintenance_cannot_be_replaced_by_continuation_input(incident, monkeypatch):
    """Unit maintenance gate after decoding the preserved historical input.

    This SERIAL incident is not a fresh current pool deployment. The current
    public loader/native authority have separate tests; only this unit's loader
    seam accepts the unchanged historical fixture bytes.
    """
    monkeypatch.setattr(partial, 'loads', lambda raw, _root: json.loads(raw))
    maintained_frontier(incident)
    observed = partial.inspect(incident.config, OPERATION, BASELINE, root=incident.root)
    config_path = incident.root / 'input.json'
    write(config_path, incident.config)
    changed = copy.deepcopy(observed['receipt']['binding']['runnerMaintenance'])
    changed['runners']['production']['runnerId'] += 1
    declaration = incident.root / 'new-maintenance.json'; write(declaration, changed)
    from test_intent_install import Guard
    args = SimpleNamespace(authorize_install_recovery=True, continue_install_recovery=True,
        resolved_revision=incident.revision, config=config_path, connection='local',
        log_root=incident.root / 'logs', install_recovery_operation=OPERATION,
        install_recovery_target=BASELINE, retained_runner_maintenance=declaration)
    import intent_install
    monkeypatch.setattr(intent_install, 'qualify_identity', lambda *_: None)
    native_output = partial.subprocess.check_output
    def output(argv, **options):
        if 'rev-parse' in argv and argv[-1] == 'HEAD':
            return incident.revision + '\n'
        if 'status' in argv:
            return ''
        return native_output(argv, **options)
    monkeypatch.setattr(partial.subprocess, 'check_output', output)
    monkeypatch.setattr(partial, 'remote_inspect', lambda *_: observed)
    monkeypatch.setattr(partial, 'accepted_controller', lambda *_: pytest.fail('changed declaration crossed authority gate'))
    before, history = incident.snapshot(), incident.history()
    with pytest.raises(ValueError, match='MAINTENANCE_DECLARATION_CHANGED'):
        partial._run(args, ROOT, {'revision': incident.revision}, guard_factory=lambda *_: Guard())
    assert incident.snapshot() == before and incident.history() == history


def test_post_apply_orchestration_keeps_writer_through_tail_and_never_republishes_consumer(incident, monkeypatch, capsys):
    """Exercise controller ordering with bounded transport/backend substitutes.

    Native gate/lease and real systemd behavior have separate process tests; this
    test proves the installer actually selects that route with the right inputs
    after the loader. A documented loader seam retains the original SERIAL
    incident without claiming the current public loader admits fresh SERIAL.
    """
    monkeypatch.setattr(partial, 'loads', lambda raw, _root: json.loads(raw))
    receipt = maintained_frontier(incident, unchanged_consumer=True)
    config_path = incident.root / 'input.json'; write(config_path, incident.config)
    observed = partial.inspect(incident.config, OPERATION, BASELINE, root=incident.root)
    observed['manifest']['consumerRevision'] = incident.revision
    from test_intent_install import Guard
    args = SimpleNamespace(authorize_install_recovery=True, continue_install_recovery=True,
        resolved_revision=incident.revision, config=config_path, connection='local',
        log_root=incident.root / 'logs', install_recovery_operation=OPERATION,
        install_recovery_target=BASELINE, retained_runner_maintenance=None,
        consumer_root=ROOT, projection_output=None)
    import install_preflight
    import intent_install
    import workflow_projection
    events, preparations = [], []
    class Preparation:
        def __init__(self, target, key, values, identity, operation):
            self.values, self.target, self.key = values, target, key
            self.stage = values['relay_release_root'] + '/.fixture-controller-stage'
            self.source, self.lease_path = self.stage + '/release/reviewed-source', self.stage + '/writer.json'
            self.holder, self.initial = None, None
            preparations.append(self)
        def create(self):
            events.append('create')
        def admission_prefix(self):
            return ['fixture-corrected-reader', self.lease_path, self.source]
        def lock_writer(self):
            assert self.holder is None
            self.holder = Guard(); events.append('lock')
        def release_writer(self):
            if self.holder is not None:
                self.holder = None; events.append('release')
        def execute(self, _argv, *, payload=None):
            assert self.holder is not None and self.holder.poll() is None
            if payload is None:
                assert _argv[-2:] == [self.values['relay_consumer_config_path']] * 2
                return [receipt['desiredDigest']] * 2
            command = payload.get('command', 'finalize')
            events.append(command)
            assert payload.get('operation', payload.get('binding', {}).get('operationId')) == OPERATION
            if command == 'status':
                return {'phase': 'open', 'consumerDigest': receipt['desiredDigest'], 'active': [], 'unknown': []}
            return {}
    monkeypatch.setattr(install_preflight, 'PreparedInstall', Preparation)
    monkeypatch.setattr(intent_install, 'qualify_identity', lambda *_: None)
    monkeypatch.setattr(workflow_projection, 'integration', lambda *_: {'next': 'fixture-independent-review'})
    # Only the already-substituted backend transport needs a current compiler
    # recipe. Keep the original config/receipt/history untouched: this clone is
    # a unit adapter, never new admitted authority or a deployment input.
    compilation = copy.deepcopy(incident.config)
    compilation['consumer']['generalRunnerPool'] = {'desiredCapacity': 1}
    compilation['consumer']['paths']['attemptRoot'] += '-v2'
    compiled = partial.compile_inputs(compilation)
    monkeypatch.setattr(partial, 'compile_inputs', lambda _: dict(compiled))
    monkeypatch.setattr(partial, 'remote_inspect', lambda *_: observed)
    monkeypatch.setattr(partial, 'publish', lambda *_: pytest.fail('already published consumer was republished'))
    native_output = partial.subprocess.check_output
    monkeypatch.setattr(partial.subprocess, 'check_output', lambda argv, **options:
        '' if 'status' in argv else native_output(argv, **options))
    def backend(argv, _root, _environment, log, host, extra):
        values = json.loads(Path(argv[argv.index('-i') + 1]).read_bytes())['all']['children']['relay']['hosts']
        values = next(iter(values.values()))
        name = Path(argv[argv.index('-i') + 2]).name
        events.append(name)
        if name == 'site.yml':
            preparation = preparations[0]
            assert preparation.holder is not None and host.poll() is None and extra.poll() is None
            assert values['relay_intent_stage_root'] == preparation.stage
            assert values['relay_intent_writer_lock_lease'] == preparation.lease_path
            assert values['relay_intent_admission_prefix'] == preparation.admission_prefix()
            assert values['relay_intent_staged_release'] == values['relay_install_root'] + '/releases/' + incident.revision
            assert values['relay_intent_staged_release'] != preparation.stage + '/release'
            assert values['relay_retained_reviewer_config_adoption'] is True
            assert values['relay_bounded_recovery_binding'] == receipt['binding']
        else:
            assert name == 'relay-intent-stage.yml'
        log.write('failed=0\nPRODUCTION_APPLY_VALIDATED=' + incident.revision + '\n')
        return 0
    monkeypatch.setattr(importlib.util, 'spec_from_file_location', lambda *_:
        SimpleNamespace(loader=SimpleNamespace(exec_module=lambda _: None)))
    monkeypatch.setattr(importlib.util, 'module_from_spec', lambda _: SimpleNamespace(run_backend=backend))
    partial._run(args, ROOT, {'revision': incident.revision}, guard_factory=lambda *_: Guard())
    assert events == ['create', 'relay-intent-stage.yml', 'lock', 'apply', 'site.yml',
        'verify', 'finalize', 'resume', 'status', 'release']
    report = json.loads(capsys.readouterr().out.split('RELAY_INSTALL_RESULT=')[-1])
    assert report['status'] == 'PASS' and report['strategy'] == 'maintained-reviewer-config-adoption'
    assert report['operationId'] == OPERATION and report['product'] == incident.revision
