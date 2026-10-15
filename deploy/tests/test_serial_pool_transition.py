"""Native protected files and bounded injected ownership-transition adapters."""
import copy
import json
import os
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
import config
import managed_pool
import serial_pool_transition as transition


OLD = '1' * 40
NEW = '2' * 40
OLD_DIGEST = 'a' * 64
NEW_DIGEST = 'b' * 64
OPERATION = '12345678-1234-4234-8234-123456789abc'


def write(root, logical, raw, mode=0o600):
    path = root / logical.lstrip('/')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    path.chmod(mode)
    return path


class Gate:
    def __init__(self, root, pathname):
        self.root, self.pathname, self.calls = root, pathname, []
        self.value = {'version': 1, 'consumerDigest': OLD_DIGEST, 'phase': 'open',
                      'operationId': None, 'target': None, 'previousActive': None,
                      'verifiedRevision': None}
        self.unknown, self.active = [], []
        self.persist()

    def persist(self):
        write(self.root, self.pathname, transition.encoded(self.value) + b'\n')

    def __call__(self, action, *arguments, services=None):
        self.calls.append(action)
        options = dict(zip(arguments[::2], arguments[1::2]))
        if action == 'quiesce':
            if self.value['phase'] == 'open':
                self.value.update(phase='quiesced', operationId=options['--operation'],
                                  target=options['--target'])
        elif action == 'drain':
            assert not self.active and not self.unknown
            if self.value['phase'] != 'applying':
                self.value['phase'] = 'drained'
        elif action == 'phase':
            self.value['phase'] = options['--phase']
        elif action == 'snapshot':
            assert self.value['phase'] == 'applying'
            assert set(services) == {'reviewer', 'production', 'general'}
            if self.value['previousActive'] is None:
                self.value['previousActive'] = copy.deepcopy(services)
        elif action != 'status':
            raise AssertionError(action)
        if action != 'status':
            self.persist()
        return {**copy.deepcopy(self.value), 'active': self.active, 'unknown': self.unknown}


class Host:
    def __init__(self, original, uid):
        values = config.compile_inputs(original)
        self.binding = {'runnerId': 47, 'runnerName': original['environment']['generalRunner']['name'],
                        'runnerUid': uid, 'scope': 'repository', 'ownWorker': False,
                        'service': values['relay_general_runner_service_name'],
                        'root': values['relay_install_root'] + '/general-runner',
                        'workFolder': values['relay_state_root'] + '/general-runner/work',
                        'registrationSha256': 'c' * 64, 'unitSha256': 'd' * 64}
        self.stopped, self.ready, self.stops = False, False, 0
        self.lose_stop = self.stop_has_no_effect = False

    def inspect_legacy(self, _config):
        return copy.deepcopy(self.binding)

    def legacy_stopped(self, _binding):
        return self.stopped

    def stop_legacy(self, _binding):
        self.stops += 1
        self.stopped = not self.stop_has_no_effect
        if self.lose_stop:
            raise RuntimeError('lost stop response')

    def pool_ready(self, _config):
        return self.ready


class GitHub:
    def __init__(self, host):
        self.remote = {'id': host.binding['runnerId'], 'name': host.binding['runnerName'], 'busy': False}
        self.removes = 0
        self.lose_remove = self.remove_has_no_effect = False

    def observe_legacy(self, _binding):
        return copy.deepcopy(self.remote)

    def remove_legacy(self, _binding):
        self.removes += 1
        if not self.remove_has_no_effect:
            self.remote = None
        if self.lose_remove:
            raise RuntimeError('lost remove response')


@pytest.fixture
def setup(tmp_path):
    original = json.loads((ROOT / 'deploy/example.json').read_text())
    original['source']['revision'] = OLD
    original['environment']['instance'] = {'reviewerPort': 18787, 'publicationEnabled': False}
    target = copy.deepcopy(original)
    target['source']['revision'] = NEW
    target['consumer']['generalRunnerPool'] = {'desiredCapacity': 1}
    target['environment']['generalRunner'].update(name='sample-managed', scope='organization',
        group='sample-general', poolApp={'appId': '101', 'installationId': '201',
                                       'privateKeyFile': '/owner-private/app.pem'})
    config.derive_managed_pool_slots(target)
    values = config.compile_inputs(original)
    claim = original['consumer']['paths']['claimRoot']
    release = values['relay_install_root'] + '/releases/' + OLD
    consumer_path = values['relay_config_root'] + '/consumer.json'
    consumer_raw = transition.encoded(original['consumer']) + b'\n'
    write(tmp_path, consumer_path, consumer_raw, 0o644)
    config_raw = transition.encoded(original) + b'\n'
    write(tmp_path, release + '/deployment-config.json', config_raw)
    manifest = {key: OLD for key in ['commit', 'installedRevision', 'resolvedRevision']}
    manifest['deploymentConfigSha256'] = transition.sha(config_raw)
    write(tmp_path, release + '/artifact-manifest.json', transition.encoded(manifest))
    write(tmp_path, release + '/reviewed-source/main.mjs', b'// protected original\n', 0o644)
    write(tmp_path, release + '/reviewed-source/empty', b'', 0o644)
    uid = os.getuid()
    evidence = {'revision': OLD, 'consumerDigest': OLD_DIGEST, 'consumerPath': consumer_path,
                'sourceRoot': release + '/reviewed-source', 'manifestPath': release + '/artifact-manifest.json',
                'configPath': release + '/deployment-config.json', 'runs': [], 'runnerUid': uid or 1001}
    (tmp_path / claim.lstrip('/') / 'publication-v2').mkdir(parents=True)
    host = Host(original, evidence['runnerUid'])
    github = GitHub(host)
    gate = Gate(tmp_path, claim + '/admission-v1.json')
    services = {name: {'active': True, 'enabled': 'enabled', 'load': 'loaded'}
                for name in ['reviewer', 'production', 'general']}
    common = {'host': host, 'github': github, 'gate': gate, 'root': tmp_path, 'owner_uid': uid}
    return {'root': tmp_path, 'original': original, 'target': target, 'evidence': evidence,
            'common': common, 'host': host, 'github': github, 'gate': gate, 'services': services,
            'consumer_raw': consumer_raw, 'claim': claim}


def prepare(fixture):
    return transition.prepare(fixture['original'], fixture['target'], fixture['evidence'],
        operation_id=OPERATION, target_revision=NEW, target_consumer_digest=NEW_DIGEST,
        services=fixture['services'], **fixture['common'])


def advance(fixture):
    return transition.advance(fixture['original'], fixture['target'], fixture['evidence'], **fixture['common'])


def state(fixture):
    return json.loads((fixture['root'] / fixture['claim'].lstrip('/') / transition.STATE_NAME).read_text())


@pytest.mark.parametrize('capacity', [1, 2])
def test_prepare_seals_original_three_component_snapshot_without_rewriting_history(setup, capacity):
    setup['target']['consumer']['generalRunnerPool']['desiredCapacity'] = capacity
    before_source = (setup['root'] / setup['evidence']['configPath'].lstrip('/')).read_bytes()
    saved = prepare(setup)
    assert saved['phase'] == 'prepared'
    assert setup['gate'].calls[-5:] == ['status', 'drain', 'status', 'phase', 'snapshot']
    assert setup['gate'].value['previousActive'] == setup['services']
    assert setup['gate'].value['consumerDigest'] == OLD_DIGEST
    assert (setup['root'] / setup['evidence']['configPath'].lstrip('/')).read_bytes() == before_source
    receipt = json.loads((setup['root'] / 'etc/codex-relay' / transition.RECEIPT_NAME).read_text())
    assert receipt['original']['consumerSha256'] == transition.sha(setup['consumer_raw'])
    assert receipt['original']['runnerUser'] == setup['original']['environment']['generalRunner']['user']
    assert receipt['target'] == {'consumerDigest': NEW_DIGEST}
    assert (setup['root'] / 'etc/codex-relay' / transition.CONSUMER_NAME).read_bytes() == setup['consumer_raw']
    assert stat_mode(setup['root'] / 'etc/codex-relay' / transition.RECEIPT_NAME) == 0o644
    assert stat_mode(setup['root'] / setup['claim'].lstrip('/') / transition.STATE_NAME) == 0o600
    assert prepare(setup) == saved


def stat_mode(path):
    return path.stat().st_mode & 0o777


@pytest.mark.parametrize('change', [
    lambda value: value['consumer'].update(runtimeUser='foreign-runtime'),
    lambda value: value['consumer']['paths'].update(workRoot='/var/lib/foreign'),
    lambda value: value['consumer']['defaultProfile'].update(cliModelId='foreign-model'),
    lambda value: value['environment'].update(namespace='foreign'),
    lambda value: value['environment']['generalRunner'].update(user='foreign-runner'),
    lambda value: value['target'].update(host='192.0.2.99'),
])
def test_unexpected_owner_delta_is_refused_before_any_mutation(setup, change):
    change(setup['target'])
    with pytest.raises((managed_pool.PoolError, config.InvalidConfig)):
        prepare(setup)
    assert setup['gate'].calls == []
    assert not (setup['root'] / setup['claim'].lstrip('/') / transition.STATE_NAME).exists()


def test_pending_external_manual_result_is_preserved_without_blocking_host_transition(setup):
    envelope = {'runId': 9, 'attemptId': 'original-attempt', 'route': 'manual', 'consumerDigest': OLD_DIGEST}
    record = {'envelope': envelope, 'manualSubmission': None}
    logical = setup['claim'] + '/publication-v2/9.json'
    raw = transition.encoded(record) + b'\n'
    path = write(setup['root'], logical, raw)
    setup['evidence']['runs'] = [{'runId': 9, 'attemptId': 'original-attempt',
                                   'envelopeSha256': transition.sha(transition.encoded(envelope))}]
    assert prepare(setup)['phase'] == 'prepared'
    assert path.read_bytes() == raw


@pytest.mark.parametrize('surface', ['ownWorker', 'unknown', 'changed-run-set', 'source-link', 'hardlink', 'writable-parent'])
def test_unproven_ownership_or_unsafe_originals_fail_before_mutation(setup, surface):
    if surface == 'ownWorker':
        setup['host'].binding['ownWorker'] = True
    elif surface == 'unknown':
        setup['gate'].unknown = [9]
    elif surface == 'changed-run-set':
        write(setup['root'], setup['claim'] + '/publication-v2/9.json',
              transition.encoded({'envelope': {'runId': 9, 'consumerDigest': OLD_DIGEST}}))
    elif surface == 'source-link':
        source = setup['root'] / setup['evidence']['sourceRoot'].lstrip('/')
        (source / 'alias').symlink_to(source / 'main.mjs')
    elif surface == 'hardlink':
        path = setup['root'] / setup['evidence']['configPath'].lstrip('/')
        os.link(path, path.with_name('config-alias'))
    else:
        (setup['root'] / 'etc/codex-relay').chmod(0o777)
    with pytest.raises((managed_pool.PoolError, OSError)):
        prepare(setup)
    assert setup['gate'].calls in ([], ['status'])
    assert setup['host'].stops == setup['github'].removes == 0


def test_stop_then_target_readiness_then_remote_removal_keep_old_gate_sealed(setup):
    prepare(setup)
    old_gate = (setup['root'] / setup['claim'].lstrip('/') / 'admission-v1.json').read_bytes()
    assert advance(setup)['phase'] == 'stopped'
    assert setup['host'].stops == 1 and setup['github'].removes == 0
    setup['host'].ready = True
    assert advance(setup)['phase'] == 'retired'
    assert advance(setup)['phase'] == 'retired'
    assert setup['host'].stops == setup['github'].removes == 1
    assert (setup['root'] / setup['claim'].lstrip('/') / 'admission-v1.json').read_bytes() == old_gate


@pytest.mark.parametrize('takes_effect', [False, True])
def test_lost_stop_response_observes_without_second_signal(setup, takes_effect):
    prepare(setup)
    setup['host'].lose_stop = True
    setup['host'].stop_has_no_effect = not takes_effect
    with pytest.raises(RuntimeError, match='lost stop'):
        advance(setup)
    assert state(setup)['phase'] == 'stop-intent'
    if takes_effect:
        assert advance(setup)['phase'] == 'stopped'
    else:
        with pytest.raises(managed_pool.PoolError, match='STOP_UNCERTAIN'):
            advance(setup)
    assert setup['host'].stops == 1


@pytest.mark.parametrize('takes_effect', [False, True])
def test_lost_remove_response_observes_exact_native_absence_without_retry(setup, takes_effect):
    prepare(setup)
    setup['host'].ready = True
    setup['github'].lose_remove = True
    setup['github'].remove_has_no_effect = not takes_effect
    with pytest.raises(RuntimeError, match='lost remove'):
        advance(setup)
    assert state(setup)['phase'] == 'remove-intent'
    if takes_effect:
        assert advance(setup)['phase'] == 'retired'
    else:
        with pytest.raises(managed_pool.PoolError, match='REMOVE_UNCERTAIN'):
            advance(setup)
    assert setup['github'].removes == 1


def target_services(setup):
    services = {name: copy.deepcopy(value) for name, value in setup['services'].items() if name != 'general'}
    services['general'] = {'active': False, 'enabled': 'disabled', 'load': 'not-found'}
    for slot in setup['target']['consumer']['executionSlots'][1:]:
        services['slot-' + slot['id']] = copy.deepcopy(services['general'])
    return services


@pytest.mark.parametrize('existing_shared_pool', [False, True])
def test_new_gate_is_separate_and_requires_complete_actual_target_snapshot(setup, existing_shared_pool):
    prepare(setup)
    services = target_services(setup)
    if existing_shared_pool:
        services['general'] = {'active': True, 'enabled': 'enabled', 'load': 'loaded'}
    kwargs = {'operation_id': OPERATION, 'target_revision': NEW, 'target_consumer_digest': NEW_DIGEST,
              'root': setup['root'], 'owner_uid': os.getuid()}
    created = transition.write_new_gate(setup['original'], setup['target'], setup['evidence'],
                                        services=services, **kwargs)
    assert created['phase'] == 'applying' and created['consumerDigest'] == NEW_DIGEST
    assert created['previousActive'] == services
    assert setup['gate'].value['previousActive'] == setup['services']
    assert transition.write_new_gate(setup['original'], setup['target'], setup['evidence'],
                                     services=services, **kwargs) == created
    services.pop('slot-pool-2')
    with pytest.raises(managed_pool.PoolError, match='TARGET_SNAPSHOT_INVALID'):
        transition.write_new_gate(setup['original'], setup['target'], setup['evidence'],
                                  services=services, **kwargs)


def test_gate_or_original_source_change_after_seal_blocks_advance(setup):
    prepare(setup)
    setup['gate'].value['phase'] = 'recovery-required'
    setup['gate'].persist()
    with pytest.raises(managed_pool.PoolError, match='ORIGINAL_GATE_CHANGED'):
        advance(setup)
    assert setup['host'].stops == setup['github'].removes == 0


def test_historical_source_change_after_seal_is_detected_before_service_stop(setup):
    prepare(setup)
    source = setup['root'] / state(setup)['plan']['original']['sourceRoot'].lstrip('/') / 'main.mjs'
    source.write_bytes(b'// altered historical source\n')
    with pytest.raises(managed_pool.PoolError, match='ORIGINAL_CONTEXT_CHANGED'):
        advance(setup)
    assert setup['host'].stops == setup['github'].removes == 0


def test_prepared_resume_uses_preserved_original_consumer_after_target_install(setup):
    saved = prepare(setup)
    write(setup['root'], setup['evidence']['consumerPath'], transition.encoded(setup['target']['consumer']), 0o644)
    assert prepare(setup) == saved
    assert advance(setup)['phase'] == 'stopped'


def test_remote_busy_or_native_id_change_never_stops_legacy_service(setup):
    prepare(setup)
    setup['github'].remote['busy'] = True
    with pytest.raises(managed_pool.PoolError, match='LEGACY_BUSY'):
        advance(setup)
    setup['github'].remote.update(busy=False, id=48)
    with pytest.raises(managed_pool.PoolError, match='REMOTE_BINDING_CHANGED'):
        advance(setup)
    assert setup['host'].stops == setup['github'].removes == 0


def test_actual_target_member_registration_name_collision_is_rejected(setup):
    target = setup['target']
    target['environment']['generalRunner']['name'] = setup['original']['environment']['generalRunner']['name']
    target['consumer'].pop('executionSlots')
    config.derive_managed_pool_slots(target)
    with pytest.raises(managed_pool.PoolError, match='REGISTRATION_NAME_COLLISION'):
        prepare(setup)
    assert setup['gate'].calls == []


def test_prepare_resumes_reserved_operation_after_snapshot_ack_loss_without_new_intent(setup):
    original_gate = setup['gate']
    class LostSnapshot:
        lost = False
        def __call__(self, *args, **kwargs):
            result = original_gate(*args, **kwargs)
            if args[0] == 'snapshot' and not self.lost:
                self.lost = True
                raise RuntimeError('lost snapshot response')
            return result
    setup['common']['gate'] = LostSnapshot()
    with pytest.raises(RuntimeError, match='lost snapshot'):
        prepare(setup)
    assert state(setup)['phase'] == 'reserved'
    assert prepare(setup)['phase'] == 'prepared'
    assert original_gate.value['operationId'] == OPERATION
    assert original_gate.value['previousActive'] == setup['services']
    assert original_gate.calls.count('drain') == 1


def test_new_gate_never_overwrites_existing_different_operation(setup):
    prepare(setup)
    path = write(setup['root'], setup['claim'] + '/admission-pool-v1.json', b'{"foreign":true}\n')
    before = path.read_bytes()
    with pytest.raises(managed_pool.PoolError, match='TARGET_GATE_CONFLICT'):
        transition.write_new_gate(setup['original'], setup['target'], setup['evidence'],
            operation_id=OPERATION, target_revision=NEW, target_consumer_digest=NEW_DIGEST,
            services=target_services(setup), root=setup['root'], owner_uid=os.getuid())
    assert path.read_bytes() == before


def test_public_compatibility_files_remain_readable_under_owner_private_umask(setup):
    previous = os.umask(0o077)
    try:
        prepare(setup)
    finally:
        os.umask(previous)
    for name in [transition.RECEIPT_NAME, transition.CONSUMER_NAME]:
        assert stat_mode(setup['root'] / 'etc/codex-relay' / name) == 0o644


def frozen_evidence(setup):
    plan = state(setup)['plan']
    return {**setup['evidence'], 'consumerPath': plan['paths']['consumer'],
            **{key: plan['original'][key] for key in ['sourceRoot', 'manifestPath', 'configPath']}}


def test_same_revision_backend_replacement_cannot_change_preserved_original_bundle(setup):
    setup['target']['source']['revision'] = setup['original']['source']['revision']
    prepare(setup)
    saved = state(setup)
    preserved = saved['plan']['original']
    assert '/serial-compat-v1/' in preserved['sourceRoot']
    source = setup['root'] / preserved['sourceRoot'].lstrip('/')
    before_source = {str(path.relative_to(source)): path.read_bytes()
                     for path in source.rglob('*') if path.is_file()}
    # A same-revision backend may reconcile these ordinary installed files.
    for key in ['configPath', 'manifestPath']:
        (setup['root'] / setup['evidence'][key].lstrip('/')).write_bytes(b'{"new":"pool"}\n')
    canonical = setup['root'] / setup['evidence']['sourceRoot'].lstrip('/') / 'main.mjs'
    canonical.write_bytes(b'// generated pool source bytes\n')
    write(setup['root'], setup['evidence']['consumerPath'], transition.encoded(setup['target']['consumer']), 0o644)
    assert advance(setup)['phase'] == 'stopped'
    assert {str(path.relative_to(source)): path.read_bytes()
            for path in source.rglob('*') if path.is_file()} == before_source
    assert transition.ProtectedFiles(setup['root'], os.getuid()).tree_sha256(preserved['sourceRoot']) == preserved['sourceTreeSha256']


def test_same_operation_new_gate_replay_retains_first_snapshot_after_pool_start(setup):
    prepare(setup)
    kwargs = {'operation_id': OPERATION, 'target_revision': NEW, 'target_consumer_digest': NEW_DIGEST,
              'root': setup['root'], 'owner_uid': os.getuid()}
    services = target_services(setup)
    first = transition.write_new_gate(setup['original'], setup['target'], setup['evidence'], services=services, **kwargs)
    services['general'] = {'active': True, 'enabled': 'enabled', 'load': 'loaded'}
    services['manualOutcome'] = {'active': False, 'enabled': 'disabled', 'load': 'loaded'}
    assert transition.write_new_gate(setup['original'], setup['target'], setup['evidence'], services=services, **kwargs) == first


def test_reserved_lost_delete_can_preflight_native_absence_but_fresh_absence_cannot(setup):
    setup['github'].remote = None
    with pytest.raises(managed_pool.PoolError, match='LEGACY_DISAPPEARED'):
        prepare(setup)
    setup['github'].remote = {'id': 47, 'name': setup['host'].binding['runnerName'], 'busy': False}
    prepare(setup)
    setup['host'].ready = True
    setup['github'].lose_remove = True
    with pytest.raises(RuntimeError, match='lost remove'):
        advance(setup)
    assert state(setup)['phase'] == 'remove-intent'
    result = transition.inspect(setup['original'], setup['target'], frozen_evidence(setup),
        target_consumer_digest=NEW_DIGEST, **setup['common'])
    assert result['binding']['runnerId'] == 47
    assert setup['github'].removes == 1
    path = setup['root'] / setup['claim'].lstrip('/') / transition.STATE_NAME
    damaged = state(setup)
    damaged['plan']['binding']['runnerId'] = 999
    path.write_bytes(transition.encoded(damaged))
    with pytest.raises(managed_pool.PoolError, match='REMOVAL_RESERVATION_UNPROVEN'):
        transition.inspect(setup['original'], setup['target'], frozen_evidence(setup),
            target_consumer_digest=NEW_DIGEST, **setup['common'])


def test_stopped_legacy_transport_cannot_restart_before_pool_forward_progress(setup):
    prepare(setup)
    assert advance(setup)['phase'] == 'stopped'
    setup['host'].stopped = False
    with pytest.raises(managed_pool.PoolError, match='LEGACY_STOP_STATE_CHANGED'):
        advance(setup)
    assert state(setup)['phase'] == 'stopped'
    assert setup['github'].removes == 0


def test_interrupted_preserved_copy_resumes_same_reserved_operation_and_closed_snapshot(setup, monkeypatch):
    original_write = transition.ProtectedFiles.write
    interrupted = False
    def copy_write(files, logical, raw, **kwargs):
        nonlocal interrupted
        if '/serial-compat-v1/' in logical and logical.endswith('/main.mjs') and not interrupted:
            interrupted = True
            raise RuntimeError('interrupted preserved source copy')
        return original_write(files, logical, raw, **kwargs)
    monkeypatch.setattr(transition.ProtectedFiles, 'write', copy_write)
    with pytest.raises(RuntimeError, match='interrupted preserved'):
        prepare(setup)
    assert state(setup)['phase'] == 'reserved'
    assert setup['gate'].value['phase'] == 'applying'
    assert prepare(setup)['phase'] == 'prepared'
    assert setup['gate'].calls.count('drain') == 1
    assert setup['gate'].value['previousActive'] == setup['services']


def configure_source_link(setup):
    links = {'legacy/controller': 'controller'}
    for value in [setup['original'], setup['target']]:
        value['environment']['compatibilityLinks'] = links.copy()
    raw = transition.encoded(setup['original']) + b'\n'
    write(setup['root'], setup['evidence']['configPath'], raw)
    manifest_path = setup['root'] / setup['evidence']['manifestPath'].lstrip('/')
    manifest = json.loads(manifest_path.read_text())
    manifest['deploymentConfigSha256'] = transition.sha(raw)
    manifest_path.write_bytes(transition.encoded(manifest))
    source = setup['evidence']['sourceRoot']
    write(setup['root'], source + '/controller/entry.mjs', b'// original component\n', 0o644)
    alias = setup['root'] / source.lstrip('/') / 'legacy/controller'
    alias.parent.mkdir(mode=0o755)
    alias.symlink_to(source + '/controller')
    return links, alias


def test_configured_source_alias_is_hashed_and_preserved_without_following_or_rewriting(setup):
    links, alias = configure_source_link(setup)
    prepare(setup)
    original = state(setup)['plan']['original']
    assert original['sourceLinks'] == links
    copy = setup['root'] / original['sourceRoot'].lstrip('/') / 'legacy/controller'
    assert copy.is_symlink() and os.readlink(copy) == os.readlink(alias)
    files = transition.ProtectedFiles(setup['root'], os.getuid())
    assert files.tree_sha256(original['sourceRoot'], source_links=links,
        original_source_root=setup['evidence']['sourceRoot']) == original['sourceTreeSha256']
    receipt = json.loads((setup['root'] / 'etc/codex-relay' / transition.RECEIPT_NAME).read_text())
    assert receipt['original']['sourceLinks'] == links
    assert advance(setup)['phase'] == 'stopped'


@pytest.mark.parametrize('damage', ['undeclared', 'changed-target', 'escape', 'missing'])
def test_unknown_changed_escaping_or_missing_source_alias_is_not_adopted(setup, damage):
    _, alias = configure_source_link(setup)
    if damage == 'undeclared':
        alias.with_name('unknown').symlink_to(setup['evidence']['sourceRoot'] + '/controller')
    else:
        alias.unlink()
        if damage != 'missing':
            alias.symlink_to('/tmp/foreign' if damage == 'escape' else
                setup['evidence']['sourceRoot'] + '/consumer')
    with pytest.raises(managed_pool.PoolError, match='SOURCE_LINK'):
        prepare(setup)
    assert setup['gate'].calls == []
