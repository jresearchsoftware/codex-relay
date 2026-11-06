import copy
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pre_apply_recovery as recovery
from test_bounded_install_recovery import incident, OPERATION, BASELINE, write


def frontier(incident):
    incident.backend.unlink()
    receipt = incident.helper('begin', incident.helper('inspect'))
    incident.native('recovery-target', options={'operationId': OPERATION, 'target': incident.revision})
    write(incident.backend, {'schemaVersion': '1', 'state': 'RECOVERY_REQUIRED',
                            'phase': 'apply', 'target_head': incident.revision})
    return receipt


def test_pre_apply_frontier_preserves_original_receipt_and_derived_backend(incident):
    receipt = frontier(incident)
    before, history = incident.snapshot(), incident.history()
    original = incident.receipt.read_bytes()
    result = recovery.inspect(incident.config, OPERATION, BASELINE, root=incident.root)
    assert result['receipt'] == receipt and result['receiptSha256'] == recovery.bounded.sha(original)
    assert incident.snapshot() == before and incident.history() == history
    assert incident.receipt.read_bytes() == original


@pytest.mark.parametrize('damage', [None, 'config_blob_sha', 'product_repository', 'declaration'])
def test_owner_dispatch_keeps_the_original_reserved_pair(incident, damage):
    import owner_lifecycle
    declaration = {'operationId': OPERATION, 'retainedTarget': BASELINE,
        'runners': {'production': {'runnerId': 55, 'runnerName': 'sample-production-runner'}}}
    incident.binding['runnerMaintenance'] = copy.deepcopy(declaration)
    receipt = frontier(incident)
    dispatch = {**receipt['binding']['gitConfigReceipt'], 'product_sha': 'f' * 40,
                'config_sha': 'e' * 40, 'workflow_run_id': 999}
    if damage == 'declaration':
        declaration['runners']['production']['runnerId'] += 1
    elif damage:
        dispatch[damage] = 'changed'
    before = incident.receipt.read_bytes()
    if damage:
        with pytest.raises(ValueError):
            owner_lifecycle.retained_recovery_binding(incident.install, declaration, dispatch,
                                                      filesystem_root=incident.root)
    else:
        assert owner_lifecycle.retained_recovery_binding(incident.install, declaration, dispatch,
            filesystem_root=incident.root) == receipt['binding']
    assert incident.receipt.read_bytes() == before


@pytest.mark.parametrize('damage', ['consumer', 'backend', 'target', 'uuid', 'backup', 'controller'])
def test_pre_apply_frontier_refuses_foreign_or_advanced_effects(incident, damage):
    frontier(incident)
    operation = OPERATION
    if damage == 'consumer':
        changed = copy.deepcopy(incident.original['consumer'])
        changed['defaultProfile']['effort'] = 'low'
        write(incident.consumer, changed, 0o644)
    elif damage == 'backend':
        write(incident.backend, {'schemaVersion': '1', 'state': 'RECOVERY_REQUIRED',
                                'phase': 'apply', 'target_head': 'f' * 40})
    elif damage == 'target':
        gate = recovery.bounded.decode(incident.gate.read_bytes()); gate['target'] = 'f' * 40
        write(incident.gate, gate)
    elif damage == 'uuid':
        operation = '22345678-1234-4234-8234-123456789abc'
    elif damage == 'backup':
        write(incident.backup, b'foreign')
    else:
        receipt = recovery.bounded.decode(incident.receipt.read_bytes())
        receipt['binding']['controllerRevision'] = 'f' * 40
        write(incident.receipt, receipt)
    before, original = incident.snapshot(), incident.receipt.read_bytes()
    with pytest.raises((ValueError, FileNotFoundError)):
        recovery.inspect(incident.config, operation, BASELINE, root=incident.root)
    assert incident.snapshot() == before and incident.receipt.read_bytes() == original


@pytest.mark.parametrize('damage', [None, 'config', 'frontier', 'template', 'reader', 'apply'])
def test_corrected_controller_executes_frozen_product_without_rebinding_receipt(tmp_path, monkeypatch, capsys, damage):
    import partial_install_recovery
    import intent_install
    from test_intent_install import Guard
    root = tmp_path / 'controller'; root.mkdir()
    command = ['git', '-C', str(root)]
    subprocess.run([*command, 'init', '-q'], check=True)
    (root / 'deploy').mkdir()
    (root / 'marker').write_text('frozen-product')
    # Explicit primitive boundary: Git acquisition/identity separation execute
    # for real; the actual installation engine has separate integration tests.
    (root / 'deploy/relay-deploy.py').write_text('''
from pathlib import Path
import json, subprocess
def run(args):
    selected = subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
    assert selected == args.resolved_revision == args._intent_bounded_recovery['desiredRevision']
    assert (ROOT/'marker').read_text() == 'frozen-product'
    assert BACKEND != ROOT/'deploy/ansible'
    assert args._intent_bounded_recovery['controllerRevision'] == selected
    assert args.authorize_lifecycle_recovery and not args.continue_install_recovery
    if (BACKEND.parent.parent/'fail-apply').exists():
        args._intent_mutation_started = True
        args._intent_failure_stage = 'activation-verification'
        args._intent_log_path = '/var/log/fixture-recovery.log'
        raise ValueError('RELAY_INSTALL_UPGRADE_APPLY_FAILED')
    (args.log_root/'primitive.json').write_text(json.dumps({'selected':selected}))
''')
    def commit(message):
        subprocess.run([*command, 'add', '.'], check=True)
        subprocess.run([*command, '-c', 'user.name=Fixture', '-c', 'user.email=test@example.invalid',
                        'commit', '-q', '--no-gpg-sign', '-m', message], check=True)
        return subprocess.check_output([*command, 'rev-parse', 'HEAD'], text=True).strip()
    desired = commit('original product')
    (root / 'marker').write_text('corrected-controller')
    if damage == 'template':
        changed = root / 'deploy/ansible/roles/relay_runtime/templates/foreign.j2'
        changed.parent.mkdir(parents=True); changed.write_text('unrelated installation change')
    elif damage == 'reader':
        (root / 'deploy/runner_self_update.py').write_text('changed reader contract')
    elif damage == 'apply':
        (root / 'fail-apply').touch()
    controller = commit('corrected controller')
    config = {'target': {'connection': 'local'}, 'environment': {'namespace': 'fixture'}, 'consumer': {}}
    config_path = tmp_path / 'desired.json'; config_path.write_text(json.dumps(config))
    receipt = {'state': 'reserved', 'binding': {'operationId': OPERATION, 'retainedTarget': BASELINE,
        'installedRevision': BASELINE, 'desiredRevision': desired, 'controllerRevision': desired,
        'gitConfigReceipt': {'config_sha256': hashlib.sha256(config_path.read_bytes()).hexdigest(),
                             'config_sha': 'a' * 40}}}
    observed = {'receipt': receipt, 'gate': {'phase': 'recovery-required'}, 'receiptSha256': 'b' * 64}
    args = argparse.Namespace(config=config_path, resolved_revision=controller,
        authorize_install_recovery=True, continue_install_recovery=True, connection='local',
        install_recovery_operation=OPERATION, install_recovery_target=BASELINE,
        retained_runner_maintenance=None, consumer_root=root, log_root=tmp_path)
    monkeypatch.setattr(recovery, 'loads', lambda raw, _root: json.loads(raw))
    monkeypatch.setattr(intent_install, 'qualify_identity', lambda *_a: None)
    monkeypatch.setattr(partial_install_recovery, 'accepted_controller',
                        lambda *_a: {'policy': 'test-qualified-exact', 'revision': controller})
    calls = []
    def inspect(*_args):
        calls.append(1)
        result = copy.deepcopy(observed)
        if damage == 'frontier' and len(calls) > 1:
            result['gate']['phase'] = 'applying'
        return result
    monkeypatch.setattr(recovery, 'remote_inspect', inspect)
    if damage == 'config':
        config_path.write_text(json.dumps({**config, 'foreign': True}))
    original = copy.deepcopy(receipt)
    if damage:
        with pytest.raises(ValueError):
            recovery.run(args, root, {'revision': controller}, guard_factory=lambda *_a: Guard())
        assert not (tmp_path / 'primitive.json').exists()
        if damage == 'apply':
            failure = json.loads(capsys.readouterr().out.split('RELAY_INSTALL_FAILURE=')[-1])
            assert failure['controller'] == controller and failure['target'] == desired
            assert failure['hostMutation'] == 'unknown' and failure['automaticRetrySafe'] is False
            assert failure['stage'] == 'activation-verification'
            assert failure['log'] == '/var/log/fixture-recovery.log'
    else:
        result = recovery.run(args, root, {'revision': controller}, guard_factory=lambda *_a: Guard())
        assert result['product'] == desired and result['controller'] == controller
        assert result['originalReceiptSha256'] == observed['receiptSha256']
        assert json.loads((tmp_path / 'primitive.json').read_text())['selected'] == desired
    assert receipt == original
