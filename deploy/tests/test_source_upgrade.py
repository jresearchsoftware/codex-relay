"""Source promotion keeps exact recipes, original operation and real seal proof."""
import base64
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import py_compile
import selectors
import shutil
import subprocess
import sys
import unittest
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
OP = '12345678-1234-1234-1234-123456789abc'
sys.path.insert(0, str(ROOT / 'deploy'))
import source_upgrade as upgrade
from installed_state import NotEligible


class InstalledReuseReceiptTests(unittest.TestCase):
    def receipt(self):
        return {'sourceIdentity': {'revision': 'b' * 40}, 'toolchain': {'stagedPrefix': ''},
                'packages': {kind: {'mode': 'installed-reuse', 'kind': kind,
                    'sourceRevision': 'a' * 40, 'recipeSha256': 'c' * 64, 'treeSha256': 'd' * 64}
                    for kind in ['runner', 'codex']}}

    def test_reuse_is_distinct_from_staged_package_receipts(self):
        receipt = self.receipt()
        upgrade.verify_package_modes(receipt)
        receipt['packages']['runner']['operationId'] = OP
        with self.assertRaisesRegex(RuntimeError, 'PACKAGE_RECEIPT_INVALID'):
            upgrade.verify_package_modes(receipt)

    def test_partial_mixed_unknown_or_different_source_receipts_refuse(self):
        for mutate in [lambda value: value['packages'].pop('runner'),
                       lambda value: value['packages']['runner'].pop('mode'),
                       lambda value: value['packages']['runner'].update(mode='staged'),
                       lambda value: value['packages']['runner'].update(sourceRevision='e' * 40),
                       lambda value: value['packages']['runner'].update(treeSha256=True),
                       lambda value: value['sourceIdentity'].update(revision='a' * 40)]:
            receipt = self.receipt()
            mutate(receipt)
            with self.assertRaisesRegex(RuntimeError, 'PACKAGE_RECEIPT_INVALID'):
                upgrade.verify_package_modes(receipt)

    def test_reuse_never_stages_or_consumes_an_unrelated_toolchain(self):
        receipt = self.receipt()
        receipt['toolchain']['stagedPrefix'] = '/tmp/other'
        with self.assertRaisesRegex(RuntimeError, 'REUSE_TOOLCHAIN_INVALID'):
            upgrade.verify_package_modes(receipt)



def entry(path, commit, policy='same', sha256='c' * 64):
    raw = upgrade.canonical({'artifact': {'commit': commit, 'sha256': sha256}, 'policy': policy})
    return {'path': path, 'kind': 'file', 'owner': 'root', 'group': 'root', 'mode': 0o640,
            'sha256': hashlib.sha256(raw).hexdigest(), 'contentBase64': base64.b64encode(raw).decode()}


def test_catalogue_only_permits_owning_artifact_json_fields():
    old = {'commit': 'a' * 40, 'releaseSourceTreeSha256': 'c' * 64}
    new = {**old, 'commit': 'b' * 40}
    left = {'entries': [entry('/etc/relay/reviewer-mcp.json', old['commit'])], 'coverage': {'all': True}}
    right = {'entries': [entry('/etc/relay/reviewer-mcp.json', new['commit'])], 'coverage': {'all': True}}
    assert upgrade.catalogue_transition(left, right, old, new, '/etc/relay', '/opt/relay/releases') == right['entries']
    for mutate in [lambda value: value['coverage'].update(all=False),
                   lambda value: value['entries'][0].update(mode=0o600),
                   lambda value: value['entries'][0].update(path='/etc/relay/unowned.json'),
                   lambda value: value['entries'].__setitem__(0, entry('/etc/relay/reviewer-mcp.json', new['commit'], 'changed'))]:
        changed = copy.deepcopy(right)
        mutate(changed)
        with pytest.raises(NotEligible):
            upgrade.catalogue_transition(left, changed, old, new, '/etc/relay', '/opt/relay/releases')
    assert left['entries'][0] == entry('/etc/relay/reviewer-mcp.json', old['commit'])


def test_stale_disposition_rebind_is_exact_unique_assignment_for_canonical_owner():
    old = {'commit': 'a' * 40, 'releaseSourceTreeSha256': 'c' * 64}
    new = {**old, 'commit': 'b' * 40}
    owner = 'roles/relay_runtime/tasks/production-operation-stale-disposition.yml:Install the source-controlled stale-disposition helper'
    prefix = b"#!/bin/bash\nset -eu\nstale_head='retained-unchanged'\n"
    old_line = ("superseding_head='" + old['commit'] + "'\n").encode()
    new_line = ("superseding_head='" + new['commit'] + "'\n").encode()
    def catalogue(raw, actual_owner=owner):
        row = {'path': '/opt/relay/custom-stale-owner-helper', 'kind': 'file',
               'owner': 'root', 'group': 'root', 'mode': 0o750,
               'contentBase64': base64.b64encode(raw).decode(), 'sha256': hashlib.sha256(raw).hexdigest()}
        return {'entries': [row], 'entryOwners': [[actual_owner]]}
    before = catalogue(prefix + old_line + b'exit 0\n')
    after = catalogue(prefix + new_line + b'exit 0\n')
    assert upgrade.catalogue_transition(before, after, old, new, '/etc/relay', '/opt/relay/releases') == after['entries']
    for left, right in [
        (catalogue(prefix + old_line, 'foreign-owner'), catalogue(prefix + new_line, 'foreign-owner')),
        (before, catalogue(prefix + new_line + b'exit 1\n')),
        (catalogue(prefix + old_line + old_line), catalogue(prefix + new_line + new_line)),
        (catalogue(prefix + b"superseding_head=''\n"), catalogue(prefix + new_line)),
        (before, catalogue(prefix + ("superseding_head='" + 'd' * 40 + "'\n").encode() + b'exit 0\n')),
    ]:
        with pytest.raises(NotEligible):
            upgrade.catalogue_transition(left, right, old, new, '/etc/relay', '/opt/relay/releases')
    changed_mode = copy.deepcopy(after)
    changed_mode['entries'][0]['mode'] = 0o755
    with pytest.raises(NotEligible):
        upgrade.catalogue_transition(before, changed_mode, old, new, '/etc/relay', '/opt/relay/releases')


def test_component_comparison_never_ignores_changed_loaded_or_package_or_pool():
    before = {'loaded': {'pid': 1, 'identity': (3, 4)}, 'packages': {'runner': 'live'}, 'pool': {'ids': [2]}, 'host': 'old'}
    upgrade.preserve_proof(before, {**before, 'host': 'new'})
    upgrade.preserve_proof(json.loads(upgrade.canonical(before)), before)
    for key in ['loaded', 'packages', 'pool']:
        with pytest.raises(RuntimeError, match='COMPONENT_CHANGED'):
            upgrade.preserve_proof(before, {**before, key: None})


def test_actual_owned_catalogues_allow_source_identity_change_only():
    import config
    from installed_state import build_catalogue
    values = config.compile_inputs(json.loads((ROOT / 'deploy/example.json').read_text()))
    old = {'commit': 'a' * 40, 'releaseSourceTreeSha256': 'b' * 64,
           'controllerSourceTreeSha256': 'c' * 64, 'codexLauncherSourceTreeSha256': 'd' * 64,
           'consumerRevision': 'e' * 40}
    new = {**old, 'commit': 'f' * 40, 'releaseSourceTreeSha256': '1' * 64,
           'controllerSourceTreeSha256': '2' * 64}
    before = build_catalogue(ROOT, upgrade.artifact_values(values, old))
    after = build_catalogue(ROOT, upgrade.artifact_values(values, new))
    changes = upgrade.catalogue_transition(before, after, old, new, values['relay_config_root'], values['relay_release_root'])
    assert {Path(value['path']).name for value in changes} == {
        'reviewer-mcp.json', 'controller.json', 'consumer-general-runner-smoke.mjs',
        'relay-diagnostics-store', 'relay-production-operation-stale-disposition'}
    assert len(before['entries']) > 700


@pytest.mark.parametrize('host,pool,code', [(None, 0, 'HOST'), (1, 0, 'HOST'), (0, None, 'POOL'), (0, 1, 'POOL')])
def test_lost_guard_is_boundary_not_fallback(host, pool, code):
    wrap = lambda value: None if value is None else SimpleNamespace(poll=lambda: None if value == 0 else 1)
    with pytest.raises(RuntimeError, match=code + '_LOCK_LOST'):
        upgrade.guards(wrap(host), wrap(pool))


def test_candidate_checks_load_real_entrypoint_closure_with_no_inherited_credentials(monkeypatch):
    monkeypatch.setenv('GITHUB_TOKEN', 'must-not-be-inherited')
    calls = []
    def run(argv, **options):
        calls.append((argv, options))
        assert 'GITHUB_TOKEN' not in options['env']
        return SimpleNamespace(returncode=0, stdout=b'Usage: reviewer' if argv[-1] == '--help'
                               else b'INTENT_STAGE_IMPORTS_READY\n')
    monkeypatch.setattr(upgrade.subprocess, 'run', run)
    upgrade.candidate_checks(Path('/stage'), 'example/relay')
    assert calls[0][1]['env']['RELAY_REPOSITORY'] == 'example/relay'
    assert calls[0][0][-1] == '/stage/release/reviewed-source/controller/src/trusted-git.mjs'
    assert calls[1][0] == ['/stage/release/bin/reviewer-mcp-http', '--help']


def test_guard_loss_terminates_active_native_cutover_transport(monkeypatch):
    import ansible_transport
    calls = []
    class Process:
        def __init__(self, *_args, **_kwargs): self.finished = False
        def start(self, _payload): calls.append('start')
        def poll(self): return 1 if self.finished else None
        def terminate(self): calls.append('terminate'); self.finished = True
        def wait(self, **_kwargs): calls.append('wait'); return 1
        def communicate(self, **_kwargs): pytest.fail('lost guard cannot publish success')
    monkeypatch.setattr(ansible_transport, 'TargetProcess', Process)
    observations = iter([None, 1])
    holder = SimpleNamespace(poll=lambda: next(observations))
    prepared = SimpleNamespace(target=None, key=None, source='/stage/release/reviewed-source', local=True,
        values={}, identity={}, operation='op', stage='/stage', lease_path='/stage/writer-lock.json',
        admission_prefix=lambda: ['bound-admission'])
    with pytest.raises(RuntimeError, match='GUARD_LOST'):
        upgrade.guarded_promote(prepared, {}, [holder])
    assert calls == ['start', 'terminate', 'wait']


def test_isolated_root_entrypoint_never_writes_bytecode_into_source(tmp_path):
    script = tmp_path / 'source_upgrade.py'
    shutil.copyfile(ROOT / 'deploy/source_upgrade.py', script)
    (tmp_path / 'source_upgrade_proof.py').write_text('def describe(*args): return {"eligible": False}\n')
    (tmp_path / 'installed_state.py').write_text('class NotEligible(ValueError): pass\n')
    stage = tmp_path / ('.stage-' + OP)
    request = {'values': {'relay_release_root': str(tmp_path)}, 'stage': str(stage),
               'sourceRoot': str(stage / 'release/reviewed-source'), 'config': {}, 'identity': {}}
    if os.geteuid() != 0:
        pytest.skip('private entrypoint intentionally requires root')
    result = subprocess.run([sys.executable, '-I', str(script), 'describe'],
        input=json.dumps(request), capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {'eligible': False}
    assert not list(tmp_path.rglob('__pycache__'))


def test_real_entrypoint_ignores_accepted_poisoned_import_and_spec_loader_caches(tmp_path, monkeypatch):
    if os.geteuid() != 0:
        pytest.skip('private entrypoint intentionally requires root')
    script = tmp_path / 'source_upgrade.py'
    shutil.copyfile(ROOT / 'deploy/source_upgrade.py', script)
    stage = tmp_path / ('.stage-' + OP)
    source_root = stage / 'release/reviewed-source'
    helper = source_root / 'deploy/ansible/roles/relay_artifacts/files/relay-intent-stage.py'
    helper.parent.mkdir(parents=True)
    proof = tmp_path / 'source_upgrade_proof.py'
    proof_body = ('def describe(values,config,identity,source_root):\n'
                  ' from source_upgrade import stage_helper\n'
                  ' stage_helper(source_root)\n'
                  ' return {"eligible":False}\n')
    (tmp_path / 'installed_state.py').write_text('class NotEligible(ValueError): pass\n')
    sentinels, caches = [], []
    for index, (path, body) in enumerate([(proof, proof_body), (helper, 'VALUE="protected-source"\n')]):
        sentinel = tmp_path / ('poison-executed-' + str(index))
        poison = 'from pathlib import Path\nPath(' + repr(str(sentinel)) + ').write_text("executed")\n' + body
        path.write_text(poison)
        stamp = path.stat()
        with monkeypatch.context() as context:
            context.setattr(sys, 'pycache_prefix', None)
            cached = Path(importlib.util.cache_from_source(str(path)))
        cached.parent.mkdir(exist_ok=True)
        py_compile.compile(str(path), cfile=str(cached), doraise=True,
                           invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP)
        path.write_text(body + ' ' * (len(poison) - len(body)))
        os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        assert path.stat().st_size == len(poison)
        sentinels.append(sentinel)
        caches.append((cached, cached.read_bytes()))
    # Prove the malicious timestamp/size-matched caches are actually accepted
    # by normal -I -B loading. Its sentinels affect only this fixture directory.
    control = ('import sys,importlib.util;sys.path.insert(0,' + repr(str(tmp_path)) + ');'
               'import source_upgrade_proof;'
               'spec=importlib.util.spec_from_file_location("plain_loader",' + repr(str(helper)) + ');'
               'module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)')
    result = subprocess.run([sys.executable, '-I', '-B', '-c', control], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert all(path.read_text() == 'executed' for path in sentinels)
    for path in sentinels:
        path.unlink()
    request = {'values': {'relay_release_root': str(tmp_path)}, 'stage': str(stage),
               'sourceRoot': str(source_root), 'config': {}, 'identity': {}}
    result = subprocess.run([sys.executable, '-I', str(script), 'describe'],
                            input=json.dumps(request), capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {'eligible': False}
    assert not any(path.exists() for path in sentinels)
    assert all(path.read_bytes() == before for path, before in caches)


@pytest.fixture
def native_stage(monkeypatch):
    if sys.platform != 'linux' or os.geteuid() != 0:
        pytest.skip('actual protected root filesystem required')
    path = ROOT / 'deploy/ansible/tests/test_intent_artifact_stage.py'
    spec = importlib.util.spec_from_file_location('source_upgrade_artifact_fixture', path)
    fixture_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture_module)
    fixture = fixture_module.IntentArtifactStageTests()
    fixture.setUp()
    try:
        old = fixture.parent / ('a' * 40)
        fixture.old.rename(old)
        fixture.old = old
        (fixture.parent / 'current').unlink()
        (fixture.parent / 'current').symlink_to(old)
        (old / 'bin').mkdir()
        shutil.copyfile('/usr/bin/true', old / 'bin/reviewer-mcp-http')
        (old / 'bin/reviewer-mcp-http').chmod(0o750)
        toolchain = fixture.parent / 'rust'
        toolchain.mkdir()
        runtime = fixture.parent / 'runtime'
        runtime.mkdir()
        manifest = {'schemaVersion': '1.0', 'commit': 'a' * 40,
            'reviewerBinarySha256': hashlib.sha256(Path('/usr/bin/true').read_bytes()).hexdigest(),
            'reviewerBuildToolchain': {'cargoVersion': 'cargo 1.90.0', 'archiveSha256': 'd' * 64},
            'reviewerBuildContractSha256': 'e' * 64, 'consumerRevision': 'f' * 40,
            'releaseSourceTreeSha256': 'c' * 64}
        for key in ['controllerSourceTreeSha256', 'codexLauncherSourceTreeSha256',
                    'reviewerSourceTreeSha256', 'reviewerBuildInputsTreeSha256']:
            manifest[key] = fixture.identity[key]
        values = {'relay_install_root': str(fixture.parent), 'relay_release_root': str(fixture.parent),
            'relay_namespace': 'fixture', 'relay_state_root': str(fixture.parent),
            'relay_runtime_root': str(runtime), 'relay_requested_revision': fixture.revision,
            'relay_installed_deployment_config': '{}\n', 'relay_git_config_receipt': {},
            'relay_deployment_contract': {}, 'relay_consumer_revision': 'f' * 40,
            'relay_rust_toolchain_root': str(toolchain), 'relay_rust_toolchain_version': '1.90.0',
            'relay_production_operation_record_path': str(fixture.parent / 'operation.json'),
            'relay_production_operation_lock_path': str(runtime / 'production-operation.lock'),
            'relay_production_operation_schema_version': '1',
            'relay_consumer_config_path': str(fixture.parent / 'consumer.json'),
            'relay_github_repository': 'example/relay', 'relay_user': 'root', 'relay_reviewer_user': 'root',
            'relay_writer_repositories': ['example/relay'],
            'relay_runner_user': 'root', 'relay_general_runner_user': 'root', 'relay_codex_user': 'root',
            'relay_config_root': str(fixture.parent / 'config')}
        catalogue = {'entries': [], 'recipeSha256': 'c' * 64}
        context = {'binding': {'revision': 'a' * 40}, 'manifest': manifest, 'oldValues': values,
                   'sourceIdentity': {'revision': 'a' * 40}}
        reference_proof = {'codex': 'same-official-distribution', 'rust': 'same-runtime'}
        proof = {'binding': context['binding'], 'host': {'status': 'PASS', 'observedSha256': 'c' * 64},
                 'loaded': {'pid': 7, 'identity': (1, 2, 3)}, 'packages': {kind: {'recipeSha256': 'c' * 64, 'treeSha256': 'd' * 64} for kind in ['runner', 'codex']},
                 'pool': {'ids': [1]}}
        proof['packages']['codex']['treeSha256'] = hashlib.sha256(upgrade.canonical(reference_proof)).hexdigest()
        monkeypatch.setitem(sys.modules, 'source_upgrade_proof', SimpleNamespace(
            prove=lambda *_args, **_kwargs: copy.deepcopy(proof),
            read_binding=lambda *_args: (context['binding'], manifest, context['sourceIdentity'], {})))
        monkeypatch.setitem(sys.modules, 'source_upgrade_packages',
                            SimpleNamespace(prepare_reference=lambda *_args: {'operationId': fixture_module.OP},
                                            verify_packages=lambda *_args: reference_proof))
        monkeypatch.setattr(upgrade, 'stage_helper', lambda _source: fixture_module.stage)
        monkeypatch.setattr(upgrade, 'candidate_checks', lambda _root, _repository: None)
        data = {'values': values, 'identity': fixture.identity, 'operationId': fixture_module.OP,
            'stage': str(fixture.root), 'sourceRoot': str(fixture.root / 'release/reviewed-source'), 'config': {},
            'context': context, 'catalogueBefore': catalogue, 'catalogueAfter': catalogue, 'changes': [],
            'manifest': upgrade.desired_manifest(values, fixture.identity, manifest)}
        old_generated = old / 'reviewed-source/consumer-general-runner-smoke.mjs'
        old_generated.parent.mkdir()
        generated_raw = b'// Canonical generated smoke fixture; not a tracked Git blob.\n'
        old_generated.write_bytes(generated_raw)
        old_generated.chmod(0o644)
        old_entry = {'path': str(old_generated), 'kind': 'file', 'owner': 'root', 'group': 'root', 'mode': 0o644,
                     'contentBase64': base64.b64encode(generated_raw).decode(),
                     'sha256': hashlib.sha256(generated_raw).hexdigest()}
        new_entry = {**old_entry, 'path': str(fixture.parent / fixture.revision /
                                             'reviewed-source/consumer-general-runner-smoke.mjs')}
        data.update(catalogueBefore={**catalogue, 'entries': [old_entry]},
                    catalogueAfter={**catalogue, 'entries': [new_entry]}, changes=[new_entry])
        yield fixture, fixture_module.stage, data, proof
    finally:
        fixture.doCleanups()


def test_frontend_resolves_defaults_and_supplies_both_catalogues_before_nomination(native_stage, monkeypatch):
    _fixture, _helper, data, proof = native_stage
    module = sys.modules['source_upgrade_proof']
    monkeypatch.setattr(module, 'resolve_values', lambda values, _root: {**values, 'resolved': True}, raising=False)
    import installed_state
    catalogue = {'entries': [], 'recipeSha256': 'c' * 64}
    monkeypatch.setattr(installed_state, 'build_catalogue', lambda *_args: copy.deepcopy(catalogue))
    data['context']['oldValues']['relay_reviewer_gateway_validated'] = True
    prepared = SimpleNamespace(values=copy.deepcopy(data['values']), identity=data['identity'],
        desired_digest='f' * 64, host_observation=None)
    prepared.values['relay_reviewer_gateway_validated'] = False
    actions = []
    def invoke(_prepared, action, **payload):
        actions.append(action)
        assert _prepared.values['resolved'] is True
        assert _prepared.values['relay_source_reuse_consumer_digest'] == 'f' * 64
        if action == 'describe': return data['context']
        assert payload['catalogueBefore'] == payload['catalogueAfter'] == catalogue
        assert payload['manifest']['commit'] == data['identity']['revision']
        assert _prepared.values['relay_reviewer_gateway_validated'] is True
        return {'status': 'SOURCE_STAGE_READY', 'host': proof['host']}
    monkeypatch.setattr(upgrade, 'invoke', invoke)
    guard = SimpleNamespace(poll=lambda: None)
    assert upgrade.prepare(prepared, {}, guard, guard) is True
    assert actions == ['describe', 'prepare']
    assert prepared.host_observation == proof['host']


def test_native_prepare_seals_only_new_release_and_journal_and_detects_drift(native_stage):
    fixture, helper, data, _proof = native_stage
    result = upgrade.remote('prepare', data)
    assert result['status'] == 'SOURCE_STAGE_READY'
    journal = upgrade.read_journal(data, helper)
    assert (fixture.root / 'source-upgrade.json').stat().st_mode & 0o777 == 0o600
    assert journal['receipt']['packages']['runner']['mode'] == 'installed-reuse'
    assert not (fixture.root / 'packages').exists()
    assert not (fixture.parent / 'operation.json').exists()
    assert (fixture.parent / 'current').resolve() == fixture.old
    assert upgrade.remote('verify', data)['receipt'] == journal['receipt']
    (fixture.root / 'release/reviewed-source/source-proof.txt').write_text('changed')
    with pytest.raises(ValueError, match='PAYLOAD_CHANGED'):
        upgrade.remote('verify', data)


def test_stage_only_rechecks_binding_seal_and_reference_without_repeating_full_host_qualification(native_stage, monkeypatch):
    _fixture, helper, data, _proof = native_stage
    upgrade.remote('prepare', data)
    journal = upgrade.read_journal(data, helper)
    module = sys.modules['source_upgrade_proof']
    monkeypatch.setattr(module, 'prove', lambda *_args, **_kwargs: pytest.fail('full host qualification is reserved for cutover'))
    assert upgrade.root_verify(journal, helper) == journal['receipt']
    packages = sys.modules['source_upgrade_packages']
    monkeypatch.setattr(packages, 'verify_packages', lambda *_args: {'changed': True})
    with pytest.raises(RuntimeError, match='PACKAGE_CHANGED'):
        upgrade.root_verify(journal, helper)


def test_cutover_runs_one_full_current_proof_immediately_before_first_live_effect(native_stage, monkeypatch):
    fixture, helper, data, proof = native_stage
    observations = []
    module = sys.modules['source_upgrade_proof']
    def prove(*_args, **_kwargs):
        observations.append(('proof', (fixture.parent / 'operation.json').exists()))
        return copy.deepcopy(proof)
    monkeypatch.setattr(module, 'prove', prove)
    upgrade.remote('prepare', data)
    journal = upgrade.read_journal(data, helper)
    # The staged drain and frontend final rechecks must not repeat App/TLS/host
    # qualification. The full live proof is repeated inside promote_root.
    upgrade.root_verify(journal, helper)
    import install_preflight
    monkeypatch.setattr(install_preflight, 'remote', lambda _data: {})
    monkeypatch.setattr(install_preflight, 'observe_predispatch_service_intent', lambda _values: {})
    def admission(_prefix, command, *_args, **_kwargs):
        return {'previousActive': {}} if command == 'snapshot' else {
            'phase': 'applying', 'operationId': data['operationId'],
            'target': fixture.revision, 'active': [], 'unknown': []}
    monkeypatch.setattr(upgrade, 'admission', admission)
    original = helper.atomic
    def atomic(path, *args, **kwargs):
        if Path(path).name == 'operation.json': observations.append(('first-effect', len(observations)))
        return original(path, *args, **kwargs)
    monkeypatch.setattr(helper, 'atomic', atomic)
    values = data['values']
    lease = str(fixture.root / 'writer-lock.json')
    upgrade.promote_root(journal, {**data, 'lease': lease,
        'admissionPrefix': ['/usr/bin/python3', '-I', data['sourceRoot'] + '/deploy/writer_lock_lease.py',
            '--exec-admission', lease, data['sourceRoot'], values['relay_consumer_config_path'],
            values['relay_github_repository']]}, helper)
    assert observations == [('proof', False), ('proof', False), ('first-effect', 2), ('proof', True)]


def test_native_prepare_missing_proof_falls_back_before_live_effect(native_stage, monkeypatch):
    fixture, _helper, data, _proof = native_stage
    def missing(*_args, **_kwargs):
        raise NotEligible()
    monkeypatch.setitem(sys.modules, 'source_upgrade_proof', SimpleNamespace(prove=missing))
    assert upgrade.remote('prepare', data) == {'eligible': False}
    assert not (fixture.root / 'source-upgrade.json').exists()
    assert (fixture.parent / 'current').resolve() == fixture.old


@pytest.mark.parametrize('error', [ValueError('reference unavailable'), OSError('download unavailable')])
def test_reference_miss_falls_back_only_during_initial_preparation(native_stage, monkeypatch, error):
    fixture, _helper, data, _proof = native_stage
    def missing(*_args, **_kwargs):
        raise error
    monkeypatch.setattr(sys.modules['source_upgrade_packages'], 'prepare_reference', missing)
    assert upgrade.remote('prepare', data) == {'eligible': False}
    assert not (fixture.root / 'source-upgrade.json').exists()
    assert not (fixture.parent / 'operation.json').exists()
    assert (fixture.parent / 'current').resolve() == fixture.old


def test_moving_target_binding_is_never_downgraded_to_preparation_miss(native_stage, monkeypatch):
    _fixture, _helper, data, _proof = native_stage
    def moving(*_args, **_kwargs):
        raise RuntimeError('SOURCE_UPGRADE_BINDING_CHANGED')
    monkeypatch.setattr(sys.modules['source_upgrade_proof'], 'prove', moving)
    with pytest.raises(RuntimeError, match='BINDING_CHANGED'):
        upgrade.remote('prepare', data)


@pytest.mark.parametrize('failure', ['consume', 'midfile', 'postproof', None])
def test_native_promotion_uses_original_snapshot_and_retains_record_on_failure(native_stage, monkeypatch, failure):
    fixture, helper, data, proof = native_stage
    if failure == 'midfile':
        config = Path(data['values']['relay_config_root'])
        config.mkdir()
        left = [entry(str(config / name), 'a' * 40) for name in ['controller.json', 'reviewer-mcp.json']]
        right = [entry(str(config / name), fixture.revision, sha256=data['manifest']['releaseSourceTreeSha256'])
                 for name in ['controller.json', 'reviewer-mcp.json']]
        for row in left:
            path = Path(row['path'])
            path.write_bytes(base64.b64decode(row['contentBase64']))
            path.chmod(row['mode'])
        data.update(catalogueBefore={**data['catalogueBefore'], 'entries': [*left, *data['catalogueBefore']['entries']]},
                    catalogueAfter={**data['catalogueAfter'], 'entries': [*right, *data['catalogueAfter']['entries']]},
                    changes=[*right, *data['changes']])
    upgrade.remote('prepare', data)
    journal = upgrade.read_journal(data, helper)
    values = data['values']
    activity = {'reviewer': {'active': True, 'enabled': 'enabled', 'load': 'loaded'}}
    import install_preflight
    native_create = install_preflight.remote
    monkeypatch.setattr(install_preflight, 'observe_predispatch_service_intent', lambda _values: activity)
    monkeypatch.setattr(install_preflight, 'remote', lambda _data: {'status': 'VERIFIED'})
    calls = []
    def observe(_prefix, command, *arguments, payload=None):
        calls.append(command)
        assert arguments[-1] == data['operationId']
        if command == 'status':
            return {'phase': 'applying', 'operationId': data['operationId'],
                    'target': fixture.revision, 'active': [], 'unknown': []}
        assert command == 'snapshot' and payload == activity
        return {'previousActive': activity}
    monkeypatch.setattr(upgrade, 'admission', observe)
    original_run = helper.run
    def run(action, *args, **kwargs):
        if action == 'consume' and failure == 'consume':
            raise RuntimeError('injected consume failure')
        return original_run(action, *args, **kwargs)
    monkeypatch.setattr(helper, 'run', run)
    if failure == 'midfile':
        atomic = helper.atomic
        def fail_second_config(path, *args, **kwargs):
            if str(path) == str(Path(values['relay_config_root']) / 'reviewer-mcp.json'):
                raise RuntimeError('injected second config failure')
            return atomic(path, *args, **kwargs)
        monkeypatch.setattr(helper, 'atomic', fail_second_config)
    if failure == 'postproof':
        module = sys.modules['source_upgrade_proof']
        module.prove = lambda *_args, **_kwargs: ({**proof, 'loaded': {'pid': 8}}
            if (fixture.parent / 'current').resolve().name == fixture.revision else copy.deepcopy(proof))
    lease = str(fixture.root / 'writer-lock.json')
    request = {**data, 'lease': lease, 'admissionPrefix': ['/usr/bin/python3', '-I',
        data['sourceRoot'] + '/deploy/writer_lock_lease.py', '--exec-admission', lease,
        data['sourceRoot'], values['relay_consumer_config_path'], values['relay_github_repository']]}
    if failure:
        with pytest.raises(RuntimeError):
            upgrade.promote_root(journal, request, helper)
        record = json.loads((fixture.parent / 'operation.json').read_text())
        assert record == upgrade.operation_record(values, fixture.revision)
        if failure == 'midfile':
            assert (fixture.parent / 'current').resolve().name == fixture.revision
            assert json.loads((Path(values['relay_config_root']) / 'controller.json').read_text())['artifact']['commit'] == fixture.revision
            assert json.loads((Path(values['relay_config_root']) / 'reviewer-mcp.json').read_text())['artifact']['commit'] == 'a' * 40
        # Ordinary same-attempt recovery calls create before source-only
        # acquisition. Preserve the failed sealed stage; never extract over its
        # canonical generated file or overwrite its original private evidence.
        sealed = (fixture.root / 'receipt.json').read_bytes()
        evidence = (fixture.root / 'source-upgrade.json').read_bytes()
        current_before = (fixture.parent / 'current').resolve()
        with pytest.raises(ValueError, match='EXISTING_SOURCE_CHANGED'):
            helper.run('extract', fixture.root, fixture.expected, fixture.archive)
        lock = fixture.parent / 'publication.lock'
        lock.write_bytes(b'')
        lock.chmod(0o600)
        holder = subprocess.Popen([sys.executable, '-I', '-B', str(ROOT / 'deploy/writer_lock_lease.py'),
            '--hold', str(lock), lease, data['operationId'], fixture.revision, 'f' * 64],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            with selectors.DefaultSelector() as ready:
                ready.register(holder.stdout, selectors.EVENT_READ)
                assert ready.select(10), 'native Writer lease did not become ready'
            assert holder.stdout.readline() == 'WRITER_LOCK_READY\n'
            with pytest.raises(RuntimeError, match='STAGE_WRITER_GUARD_LIVE'):
                native_create({'values': values, 'action': 'create', 'operation': data['operationId'],
                               'target': fixture.revision, 'stage': data['stage'], 'reinstall': False})
            assert (fixture.root / 'source-upgrade.json').read_bytes() == evidence
        finally:
            # A dead holder with its original private lease file is the
            # interrupted-attempt boundary, rather than a fabricated PID.
            if holder.poll() is None:
                holder.kill()
            holder.wait(timeout=10)
            holder.stdin.close()
            holder.stdout.close()
            holder.stderr.close()
        assert Path(lease).is_file()
        created = native_create({'values': values, 'action': 'create', 'operation': data['operationId'],
                                 'target': fixture.revision, 'stage': data['stage'], 'reinstall': False})
        assert created['preservedPrevious'] is True and created['operationId'] == data['operationId']
        prior, = fixture.parent.glob(fixture.root.name + '.prior-*')
        assert (prior / 'receipt.json').read_bytes() == sealed
        assert (prior / 'source-upgrade.json').read_bytes() == evidence
        assert (prior / 'release/reviewed-source/consumer-general-runner-smoke.mjs').is_file()
        shutil.copyfile(prior / 'source.tar', fixture.archive)
        fixture.archive.chmod(0o600)
        acquired = helper.run('extract', fixture.root, fixture.expected, fixture.archive)
        assert acquired['sourceGitTree'] == fixture.identity['tree']
        assert not (fixture.root / 'receipt.json').exists()
        assert not (fixture.root / 'source-upgrade.json').exists()
        assert (fixture.parent / 'current').resolve() == current_before
        assert json.loads((fixture.parent / 'operation.json').read_text()) == record
    else:
        result = upgrade.promote_root(journal, request, helper)
        assert result == {'status': 'SOURCE_UPGRADE_READY', 'revision': fixture.revision,
            'consumerRevision': 'f' * 40, 'previousRevision': 'a' * 40}
        assert not (fixture.parent / 'operation.json').exists()
        assert (fixture.parent / 'current').resolve().name == fixture.revision
    assert calls[:2] == ['status', 'snapshot']
    assert all(command == 'status' for command in calls[2:])
