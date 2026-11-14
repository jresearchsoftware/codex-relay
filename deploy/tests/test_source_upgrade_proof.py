"""Current source/receipt/readiness evidence refuses drift and moving authority."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import io
import marshal
import py_compile
import subprocess
import tarfile
import threading

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
import source_upgrade_proof as proof
from installed_state import NotEligible


@pytest.fixture
def parallel_proof(monkeypatch):
    import host_preflight
    import installed_state
    values = {'relay_source_reuse_consumer_digest': 'a' * 64}
    binding = {'revision': 'b' * 40}
    config = {'unchanged': True}
    events, completed = [], set()
    barrier = threading.Barrier(4, timeout=5)
    package_started = threading.Event()
    state = {'failure': None}
    loaded_value = {'production': {'identity': 'same-process'}}
    monkeypatch.setattr(host_preflight, 'resolved', lambda value: value)
    monkeypatch.setattr(proof, 'gateway_values', lambda value: value)
    monkeypatch.setattr(proof, 'read_binding', lambda value: (binding, {}, {}, config))
    monkeypatch.setattr(proof, 'normalized_config', lambda value: value)
    monkeypatch.setattr(proof, 'verify_source_tree', lambda *_args: events.append('source') or {'verified': True})
    def independent(name):
        assert events[0] == 'source'
        events.append(name + ':start')
        try:
            barrier.wait()
            assert package_started.wait(5), 'package checks did not overlap initial loaded capture'
            error = state.get('errors', {}).get(name)
            if error is not None:
                if name == 'loaded': package_started.set()
                raise error
            if state['failure'] == name:
                if name == 'loaded': package_started.set()
                raise NotEligible('INJECTED_' + name.upper())
            if name != 'loaded':
                assert package_started.wait(5), 'packages did not overlap host/pool qualification'
            return ({'status': 'PASS', 'pendingProductMaterial': [], 'identityPlan': {}}
                    if name == 'host' else loaded_value if name == 'loaded' else {'members': [1]})
        finally:
            completed.add(name)
    monkeypatch.setattr(host_preflight, 'inspect_inputs', lambda *_args: independent('host'))
    monkeypatch.setattr(proof, 'pool_proof', lambda *_args: independent('pool'))
    def loaded(_values):
        if threading.current_thread() is threading.main_thread():
            events.append('loaded:final')
            return loaded_value
        return independent('loaded')
    monkeypatch.setattr(proof, 'loaded_proof', loaded)
    def packages(_values, _source, observed, **_kwargs):
        events.append('packages:start')
        try:
            barrier.wait()
            assert 'loaded' not in completed, 'package checks waited for loaded capture'
            package_started.set()
            error = state.get('errors', {}).get('packages')
            if error is not None: raise error
            if state['failure'] == 'packages': raise NotEligible('INJECTED_PACKAGES')
            assert observed.result(timeout=5) is loaded_value
            return {'activeRunnerUnits': ['production.service']}
        finally:
            completed.add('packages')
    monkeypatch.setattr(proof, 'package_proof', packages)
    for name in ['readiness_proof', 'runtime_support_proof', 'prerequisite_proof', 'lifecycle_unit_proof']:
        monkeypatch.setattr(proof, name, lambda *_args, **_kwargs: {'unchanged': True})
    monkeypatch.setattr(proof, 'runtime_imports', lambda *_args: events.append('imports'))
    def audit(_catalogue, *, live_checks):
        assert completed == {'host', 'pool', 'loaded', 'packages'} and all(live_checks.values())
        events.append('audit')
        return {'eligible': True}
    monkeypatch.setattr(installed_state, 'audit_catalogue', audit)
    return values, config, binding, events, completed, state


def test_full_proof_overlaps_independent_checks_and_retains_final_frontier(parallel_proof):
    values, config, binding, events, completed, _state = parallel_proof
    result = proof.prove(values, config, '/source', {}, expected_binding=binding,
                         stage='/stage', operation='operation', package_reference={})
    assert result['host']['status'] == 'PASS' and result['pool'] == {'members': [1]}
    assert completed == {'host', 'pool', 'loaded', 'packages'}
    assert events.index('source') < events.index('packages:start') < events.index('audit') < events.index('loaded:final')


@pytest.mark.parametrize('failure', ['host', 'pool', 'loaded', 'packages'])
def test_any_parallel_failure_joins_owned_readers_and_prevents_acceptance(parallel_proof, failure):
    values, config, binding, events, completed, state = parallel_proof
    state['failure'] = failure
    with pytest.raises(NotEligible, match='INJECTED_' + failure.upper()):
        proof.prove(values, config, '/source', {}, expected_binding=binding,
                    stage='/stage', operation='operation', package_reference={})
    assert completed == {'host', 'pool', 'loaded', 'packages'}
    assert 'audit' not in events and 'loaded:final' not in events


@pytest.mark.parametrize('ordinary,hard', [('host', 'pool'), ('host', 'loaded'), ('host', 'packages'),
                                        ('loaded', 'pool'), ('packages', 'pool'), ('packages', 'loaded')])
def test_simultaneous_outer_boundary_failure_dominates_ordinary_fallback(parallel_proof, ordinary, hard):
    values, config, binding, events, completed, state = parallel_proof
    state['errors'] = {ordinary: NotEligible('ORDINARY_UNAVAILABLE'),
                       hard: RuntimeError('SOURCE_UPGRADE_BINDING_CHANGED')}
    with pytest.raises(RuntimeError, match='SOURCE_UPGRADE_BINDING_CHANGED'):
        proof.prove(values, config, '/source', {}, expected_binding=binding,
                    stage='/stage', operation='operation', package_reference={})
    assert completed == {'host', 'pool', 'loaded', 'packages'}
    assert 'audit' not in events and 'loaded:final' not in events


@pytest.mark.parametrize('failure', [None, 'codex', 'general-1', 'general-2', 'simultaneous', 'loaded-hard'])
def test_package_readers_overlap_only_after_all_runner_version_probes(monkeypatch, failure):
    import host_preflight
    import source_upgrade_packages
    rows = [{'label': label, 'root': '/' + label, 'user': 'runner', 'service': label + '.service'}
            for label in ['production', 'general-1', 'general-2', 'unused-capacity']]
    monkeypatch.setattr(host_preflight, 'runner_targets', lambda _values: rows)
    probed, completed, starts = [], set(), []
    package = SimpleNamespace(inspect_live=lambda *_args: None,
        runner_transition=lambda _stage, values: probed.append(values['root']))
    monkeypatch.setattr(proof, '_module', lambda *_args: package)
    monkeypatch.setattr(proof, 'recipe_rows', lambda *_args: [['recipe', 'same']])
    barrier = threading.Barrier(3, timeout=5)
    def reader(name):
        assert probed == ['/production', '/general-1', '/general-2']
        starts.append(name)
        try:
            barrier.wait()
            if failure == 'simultaneous':
                if name == 'codex': raise NotEligible('ORDINARY_CODEX_UNAVAILABLE')
                if name == 'general-1': raise RuntimeError('INJECTED_PROTECTED_BINDING_CHANGED')
            if failure == 'loaded-hard' and name == 'codex':
                raise NotEligible('ORDINARY_CODEX_UNAVAILABLE')
            if failure == name: raise NotEligible('INJECTED_PACKAGE_READER')
            return {'identity': name}
        finally:
            completed.add(name)
    monkeypatch.setattr(source_upgrade_packages, 'verify_packages', lambda *_args: reader('codex'))
    monkeypatch.setitem(sys.modules, 'source_upgrade_general',
                        SimpleNamespace(capture_general=lambda runner, _source: reader(runner['label'])))
    values = {'relay_general_runner_pool': {'desiredCapacity': 2}, 'relay_runner_package_archive': '/archive'}
    from concurrent.futures import Future
    class LoadedFuture(Future):
        def result(self, timeout=None):
            assert completed == {'codex', 'general-1', 'general-2'}
            return super().result(timeout=timeout)
    loaded = LoadedFuture()
    if failure == 'loaded-hard':
        loaded.set_exception(RuntimeError('INJECTED_PROTECTED_BINDING_CHANGED'))
    else:
        loaded.set_result({'production': {'identity': 'production'}})
    if failure in ['simultaneous', 'loaded-hard']:
        with pytest.raises(RuntimeError, match='INJECTED_PROTECTED_BINDING_CHANGED'):
            proof.package_proof(values, '/source', loaded, stage='/stage', operation='op', package_reference={})
    elif failure:
        with pytest.raises(NotEligible, match='INJECTED_PACKAGE_READER'):
            proof.package_proof(values, '/source', loaded, stage='/stage', operation='op', package_reference={})
    else:
        result = proof.package_proof(values, '/source', loaded, stage='/stage', operation='op', package_reference={})
        expected = [{'label': row['label'], 'proof': {'identity': row['label']}} for row in rows[:3]]
        assert result['runner']['treeSha256'] == hashlib.sha256(proof.canonical(expected)).hexdigest()
        assert result['activeRunnerUnits'] == [row['service'] for row in rows[:3]]
    assert completed == {'codex', 'general-1', 'general-2'}
    assert set(starts) == completed and len(starts) == 3


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(proof.canonical(value))
    path.chmod(0o600)


@pytest.fixture
def installed(tmp_path):
    revision = 'a' * 40
    release = tmp_path / 'opt/relay/releases' / revision
    snapshot = {'source': {'repository': 'https://github.com/example/relay.git', 'revision': revision},
                'environment': {'namespace': 'relay', 'localApply': {'source': 'owner-file'}}}
    identity = {'revision': revision, 'tree': 'b' * 40}
    manifest = {'schemaVersion': '1.0', 'commit': revision, 'resolvedRevision': revision, 'installedRevision': revision,
                'gitTree': identity['tree'],
                'deploymentConfigSha256': hashlib.sha256(proof.canonical(snapshot)).hexdigest(),
                'gitConfigReceipt': {'source': 'owner-file', 'product_repository': 'example/relay',
                    'product_sha': revision, 'config_sha256': 'c' * 64}}
    write(release / 'artifact-manifest.json', manifest)
    write(release / 'deployment-config.json', snapshot)
    write(release / 'reviewed-source/.relay-source.json', identity)
    (tmp_path / 'opt/relay/current').symlink_to('/opt/relay/releases/' + revision)
    values = {'relay_install_root': '/opt/relay', 'relay_release_root': '/opt/relay/releases',
              'relay_namespace': 'relay'}
    return tmp_path, release, values, manifest, snapshot


def binding(installed):
    root, _, values, _, _ = installed
    return proof.read_binding(values, root=root, owner_uid=os.getuid())


def test_binding_binds_actual_snapshot_and_source_bytes(installed):
    result, manifest, identity, snapshot = binding(installed)
    assert result['revision'] == identity['revision'] == manifest['commit']
    assert snapshot['environment']['namespace'] == 'relay'
    write(installed[1] / 'deployment-config.json', {**snapshot, 'drift': True})
    with pytest.raises(NotEligible, match='INSTALLED_BINDING'):
        binding(installed)


def test_installed_manifest_schema_and_duplicate_keys_cannot_nominate_fast_path(installed):
    path = installed[1] / 'artifact-manifest.json'
    manifest = installed[3]
    manifest['schemaVersion'] = 'unsupported'
    write(path, manifest)
    with pytest.raises(NotEligible, match='INSTALLED_BINDING'):
        binding(installed)
    manifest['schemaVersion'] = '1.0'
    raw = proof.canonical(manifest)
    path.write_bytes(raw[:-1] + b',"schemaVersion":"1.0"}')
    with pytest.raises(NotEligible, match='JSON_INVALID'):
        binding(installed)


@pytest.mark.parametrize('stage', ['pending', 'ready-corrupt'])
def test_incomplete_first_install_cannot_enter_fast_path(installed, stage):
    manifest = installed[3]
    manifest['installationState'] = {'schemaVersion': 1, 'stage': stage, 'pairSha256': 'f' * 64}
    write(installed[1] / 'artifact-manifest.json', manifest)
    with pytest.raises(NotEligible, match='PENDING_INSTALLATION'):
        binding(installed)


def test_ready_pair_uses_original_receipt_not_reencoded_config(installed):
    from intent_install import pair_digest
    manifest = installed[3]
    manifest['installationState'] = {'schemaVersion': 1, 'stage': 'ready',
                                    'pairSha256': pair_digest(manifest['gitConfigReceipt'])}
    write(installed[1] / 'artifact-manifest.json', manifest)
    assert binding(installed)[1]['installationState']['stage'] == 'ready'


def test_git_receipt_nullable_workflow_and_optional_ids_follow_owner_contract(installed):
    manifest = installed[3]
    receipt = manifest['gitConfigReceipt']
    receipt.update(source='owner-checkout', source_policy='test-qualified-exact',
                   config_sha='d' * 40, config_blob_sha='e' * 40, workflow_run_id=None)
    write(installed[1] / 'artifact-manifest.json', manifest)
    assert binding(installed)[1]['gitConfigReceipt']['workflow_run_id'] is None
    receipt['product_sha'] = 'f' * 40
    write(installed[1] / 'artifact-manifest.json', manifest)
    with pytest.raises(NotEligible, match='RECEIPT'):
        binding(installed)


@pytest.mark.parametrize('mutation', ['symlink', 'hardlink', 'writable'])
def test_protected_read_rejects_unsafe_file_shapes(tmp_path, mutation):
    path = tmp_path / 'record'
    path.write_bytes(b'private')
    path.chmod(0o600)
    if mutation == 'symlink':
        path.rename(tmp_path / 'target')
        path.symlink_to(tmp_path / 'target')
    elif mutation == 'hardlink':
        os.link(path, tmp_path / 'alias')
    else:
        path.chmod(0o622)
    with pytest.raises((NotEligible, OSError)):
        proof.protected_read(path, owner_uid=os.getuid(), boundary=tmp_path)


def test_normalization_omits_only_product_revision_selector():
    config = {'source': {'repository': 'example/relay', 'revision': 'main'},
              'environment': {'policy': 1}}
    other = copy.deepcopy(config)
    other['source']['revision'] = 'a' * 40
    assert proof.normalized_config(config) == proof.normalized_config(other)
    assert config['source']['revision'] == 'main'
    other['environment']['policy'] = 2
    assert proof.normalized_config(config) != proof.normalized_config(other)


def test_moving_binding_is_hard_boundary_not_full_path_fallback():
    with pytest.raises(RuntimeError, match='BINDING_CHANGED') as caught:
        proof.unchanged(False, 'SOURCE_UPGRADE_BINDING_CHANGED')
    assert not isinstance(caught.value, NotEligible)


@pytest.mark.parametrize('field,value', [('createDirectories', ['/missing']), ('installPackage', True),
                                        ('installUnit', True), ('retiring', True)])
def test_existing_pool_installation_plan_must_need_no_repairs(field, value):
    member = {'createDirectories': [], 'installPackage': False, 'installUnit': False, 'retiring': False}
    plan = {'status': 'PASS', 'createParents': [], 'members': {'runner-01': member}}
    proof.require_unchanged_pool_plan(plan)
    member[field] = value
    with pytest.raises(NotEligible, match='POOL_RECONCILIATION'):
        proof.require_unchanged_pool_plan(plan)


def test_runtime_support_requires_restart_readable_ca_and_enabled_timer(monkeypatch):
    values = {'relay_tls_client_ca_file': '/etc/relay/ca.pem', 'relay_reviewer_group': 'reviewer',
              'relay_reviewer_recovery_timer_name': 'reviewer-recovery.timer'}
    ca = [1, 2, 0o100640, 0, 17, 1, 30, 40, 50]
    monkeypatch.setattr(proof, 'protected_read', lambda *a, **k: (b'opaque-ca', ca))
    monkeypatch.setattr(proof.grp, 'getgrnam', lambda name: SimpleNamespace(gr_gid=17))
    state = {'LoadState': 'loaded', 'ActiveState': 'active', 'UnitFileState': 'enabled', 'NeedDaemonReload': 'no'}
    def execute(argv):
        return SimpleNamespace(stdout='\n'.join(key + '=' + value for key, value in state.items()).encode())
    assert proof.runtime_support_proof(values, execute=execute)['clientCa'] == ca
    ca[2] = 0o100600
    with pytest.raises(NotEligible, match='CLIENT_CA_METADATA'):
        proof.runtime_support_proof(values, execute=execute)
    ca[2] = 0o100640
    for key, value in [('ActiveState', 'inactive'), ('UnitFileState', 'disabled'), ('NeedDaemonReload', 'yes')]:
        before = state[key]
        state[key] = value
        with pytest.raises(NotEligible, match='RECOVERY_TIMER_DRIFT'):
            proof.runtime_support_proof(values, execute=execute)
        state[key] = before


def test_prerequisite_proof_does_not_promote_missing_git_or_bubblewrap():
    values = {'relay_manage_base_packages': True, 'relay_base_packages': ['git', 'python3']}
    rows = ['bubblewrap\tinstall ok installed', 'git\tinstall ok installed', 'python3\tinstall ok installed']
    def execute(argv):
        assert argv[0] == '/usr/bin/dpkg-query'
        return SimpleNamespace(stdout=('\n'.join(rows) + '\n').encode())
    assert proof.prerequisite_proof(values, execute=execute)['installed'] == ['bubblewrap', 'git', 'python3']
    rows[1] = 'git\tdeinstall ok config-files'
    with pytest.raises(NotEligible, match='PREREQUISITE_MISSING'):
        proof.prerequisite_proof(values, execute=execute)
    rows.pop(0)
    with pytest.raises(NotEligible, match='PREREQUISITE_MISSING'):
        proof.prerequisite_proof(values, execute=execute)


@pytest.mark.skipif(os.getuid() != 0, reason='installed bytecode evidence requires root-owned Linux fixture')
def test_derived_bytecode_must_be_exact_canonical_source_compilation(tmp_path, monkeypatch):
    source = tmp_path / 'source'
    source.mkdir(mode=0o755)
    original = source / 'example.py'
    raw = b'def answer():\n    return 42\n'
    original.write_bytes(raw)
    original.chmod(0o644)
    cached = Path(py_compile.compile(str(original), doraise=True))
    cached.parent.chmod(0o755)
    tracked = {'example.py': raw}
    assert proof.verify_derived_cache(cached, source, tracked)[0].endswith('.pyc')
    monkeypatch.setattr(sys, 'pycache_prefix', '/dev/null')
    assert proof.verify_derived_cache(cached, source, tracked)[0].endswith('.pyc')
    intact = cached.read_bytes()
    cached.write_bytes(intact[:16] + marshal.dumps(compile(b'raise RuntimeError("changed")\n', str(original), 'exec')))
    with pytest.raises(NotEligible, match='BYTECODE_UNPROVEN'):
        proof.verify_derived_cache(cached, source, tracked)
    cached.write_bytes(intact + b'trailing-unbound-bytes')
    with pytest.raises(NotEligible, match='BYTECODE_UNPROVEN'):
        proof.verify_derived_cache(cached, source, tracked)


def test_lifecycle_units_include_missing_logical_slots_and_pending_reload():
    values = {'relay_namespace': 'relay', 'relay_reviewer_service_name': 'reviewer.service',
              'relay_production_runner_service_name': 'production.service',
              'relay_general_runner_service_name': 'general.service',
              'relay_additional_execution_slots': [{'relay_runner_service_name': 'slot-02.service'}]}
    states = {}
    for unit in ['reviewer.service', 'production.service', 'relay-relay-manual-outcome.socket',
                 'general.service', 'slot-02.service']:
        logical = unit in ['general.service', 'slot-02.service']
        states[unit] = {'Id': unit, 'LoadState': 'not-found' if logical else 'loaded',
                        'ActiveState': 'inactive' if logical else 'active',
                        'SubState': 'dead' if logical else 'listening' if unit.endswith('.socket') else 'running',
                        'UnitFileState': '' if logical else 'enabled', 'NeedDaemonReload': 'no'}
    def execute(argv):
        return SimpleNamespace(returncode=1, stdout='\n\n'.join(
            '\n'.join(key + '=' + value for key, value in row.items()) for row in states.values()).encode())
    assert len(proof.lifecycle_unit_proof(values, execute=execute)) == 5
    states['general.service'].update(LoadState='loaded', ActiveState='active',
                                     SubState='running', UnitFileState='enabled')
    with pytest.raises(NotEligible, match='LOGICAL_RUNNER_ACTIVE'):
        proof.lifecycle_unit_proof(values, execute=execute)
    assert len(proof.lifecycle_unit_proof(values, execute=execute, active_runners=['general.service'])) == 5
    states['slot-02.service']['NeedDaemonReload'] = 'yes'
    with pytest.raises(NotEligible, match='DAEMON_RELOAD_REQUIRED'):
        proof.lifecycle_unit_proof(values, execute=execute, active_runners=['general.service'])
    states['slot-02.service']['NeedDaemonReload'] = 'no'
    states.pop('general.service')
    with pytest.raises(NotEligible, match='SERVICE_STATE_UNPROVEN'):
        proof.lifecycle_unit_proof(values, execute=execute)


@pytest.fixture
def readiness(tmp_path, monkeypatch):
    marker = tmp_path / 'authorized'
    marker.write_bytes(b'authorized\n')
    marker.chmod(0o600)
    values = {'relay_reviewer_activation_marker': str(marker),
              'relay_reviewer_recovery_off_marker': str(tmp_path / 'off'),
              'relay_reviewer_service_name': 'reviewer.service',
              'relay_reviewer_bind_address': '172.18.0.1', 'relay_reviewer_bind_port': 8443}
    read = proof.protected_read
    monkeypatch.setattr(proof, 'protected_read', lambda path: read(path, owner_uid=os.getuid(), boundary=tmp_path))
    outputs = {'enabled': b'enabled\n', 'pid': b'123\n',
               'ss': b'LISTEN 0 128 172.18.0.1:8443 0.0.0.0:* users:(("reviewer",pid=123,fd=9))\n'}
    def execute(argv):
        key = 'ss' if argv[0] == '/bin/ss' else 'enabled' if argv[1] == 'is-enabled' else 'pid'
        return SimpleNamespace(stdout=outputs[key])
    return values, outputs, execute


def test_readiness_binds_listener_to_actual_reviewer_main_pid(readiness):
    values, outputs, execute = readiness
    assert proof.readiness_proof(values, execute=execute)['pid'] == 123
    outputs['ss'] = outputs['ss'].replace(b'pid=123', b'pid=456')
    with pytest.raises(NotEligible, match='LISTENER'):
        proof.readiness_proof(values, execute=execute)


def test_disabled_or_recovery_off_reviewer_cannot_be_preserved(readiness):
    values, outputs, execute = readiness
    outputs['enabled'] = b'disabled\n'
    with pytest.raises(NotEligible, match='NOT_ENABLED'):
        proof.readiness_proof(values, execute=execute)
    outputs['enabled'] = b'enabled\n'
    Path(values['relay_reviewer_recovery_off_marker']).symlink_to('/missing')
    with pytest.raises(NotEligible, match='RECOVERY_PENDING'):
        proof.readiness_proof(values, execute=execute)


@pytest.mark.skipif(os.getuid() != 0, reason='installed source evidence requires root-owned Linux fixture')
def test_source_reconstruction_matches_real_git_tree_and_refuses_all_extra_bytes(tmp_path, monkeypatch):
    repository = Path(__file__).resolve().parents[2]
    monkeypatch.setenv('GIT_CONFIG_COUNT', '1')
    monkeypatch.setenv('GIT_CONFIG_KEY_0', 'safe.directory')
    monkeypatch.setenv('GIT_CONFIG_VALUE_0', str(repository))
    deploy = proof._module(repository, 'deploy/relay-deploy.py', 'proof_test_source_identity')
    revision = deploy.git(repository, 'rev-parse', 'HEAD')
    monkeypatch.setattr(deploy, 'clean_git', lambda root: revision)
    identity = deploy.source_identity(repository)
    archive = subprocess.run(['git', '-C', str(repository), 'archive', revision],
                             capture_output=True, check=True).stdout
    source = tmp_path / 'release/reviewed-source'
    source.mkdir(parents=True)
    # git archive is a locally selected, trusted fixture; this test never uses
    # Git on the installed source metadata under audit.
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for entry in tar:
            assert entry.isdir() or entry.isfile()
            target = source / entry.name
            if entry.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(tar.extractfile(entry).read())
                target.chmod(0o755 if entry.mode & 0o111 else 0o644)
    write(source / '.relay-source.json', identity)
    snapshot = {'environment': {'compatibilityLinks': {'custom-alias.mjs': 'consumer/consumer.mjs'}}}
    (source / 'custom-alias.mjs').symlink_to('consumer/consumer.mjs')
    generated = source / 'consumer-general-runner-smoke.mjs'
    generated.write_text('canonical generated fixture')
    generated.chmod(0o644)
    for directory, _, _ in os.walk(source):
        Path(directory).chmod(0o755)
    catalogue = {'entries': [{'path': str(generated)}]}
    args = ({'release': str(source.parent)}, identity, snapshot, catalogue, repository)
    proof.verify_source_tree(*args)
    candidate = source / 'deploy/intent_install.py'
    cache = Path(py_compile.compile(str(candidate), doraise=True))
    cache.parent.chmod(0o755)
    proof.verify_source_tree(*args)
    original = candidate.read_bytes()
    candidate.write_bytes(original + b'\n# changed\n')
    with pytest.raises(NotEligible, match='SOURCE_DRIFT'):
        proof.verify_source_tree(*args)
    candidate.write_bytes(original)
    extra = source / 'undeclared-input'
    extra.write_text('additional executable input')
    with pytest.raises(NotEligible, match='SOURCE_DRIFT'):
        proof.verify_source_tree(*args)
    extra.unlink()
    (source / 'custom-alias.mjs').unlink()
    (source / 'custom-alias.mjs').symlink_to('consumer/consumer-config.mjs')
    with pytest.raises(NotEligible, match='LINKS_UNPROVEN'):
        proof.verify_source_tree(*args)
