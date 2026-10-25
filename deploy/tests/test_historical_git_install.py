"""Concrete accepted SERIAL metadata regression; no network or host mutation.

The exact historical modules/templates are read from Git objects. This proves
compatibility/planning against their real inputs, not execution of a modern
Git installer by the historical product or an installed-host qualification.
"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
from config import load, loads
import intent_install
import workflow_projection

OLD = 'f6947853079dc108d31b87e89da727206c7ce968'
TARGET = 'f6431d612d464c511fdda97e7dea64ace7f03ac7'


def git(root, *arguments, raw=False):
    result = subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=false',
                             '-C', str(root), *arguments], capture_output=True, check=True)
    return result.stdout if raw else result.stdout.decode().strip()


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


@pytest.fixture
def historical(tmp_path):
    try:
        git(ROOT, 'cat-file', '-e', intent_install.LEGACY_LIFECYCLE_BOUNDARY + '^{commit}')
    except subprocess.CalledProcessError:
        pytest.skip('historical local ancestry evidence unavailable; this regression never uses the network')
    paths = ['deploy/workflow_projection.py', 'deploy/workflows/contract.json',
             *['deploy/workflows/' + name + '.yml.in' for name in ['routing', 'recovery', 'production']]]
    roots = {}
    for revision in [OLD, TARGET]:
        root = tmp_path / revision
        for name in paths:
            try:
                data = git(ROOT, 'show', revision + ':' + name, raw=True)
            except subprocess.CalledProcessError:
                pytest.skip('exact historical Git objects unavailable in this source checkout')
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            path.chmod(0o644)
        roots[revision] = root
    old = module(roots[OLD] / 'deploy/workflow_projection.py', 'historical_installed_projection')
    target = module(roots[TARGET] / 'deploy/workflow_projection.py', 'historical_target_projection')
    config = load(ROOT / 'deploy/example.json', ROOT)
    consumer = tmp_path / 'consumer'
    consumer.mkdir()
    old.project(config, OLD, roots[OLD], consumer)
    return roots, old, target, config, consumer


def selected_git_config(tmp_path, config):
    desired = copy.deepcopy(config)
    desired['consumer']['defaultProfile'] = {'cliModelId': 'gpt-6.1-sol', 'effort': 'medium'}
    desired['environment']['reviewerRepositories'] = ['example/codex-relay', 'example/shared-governance']
    root = tmp_path / 'private-config-fixture'
    path = root / 'prod/relay.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(desired))
    git(root, 'init', '--quiet', '--template=', '--initial-branch=main')
    git(root, 'add', '.')
    git(root, '-c', 'user.name=fixture', '-c', 'user.email=fixture@example.invalid',
        'commit', '--quiet', '-m', 'accepted synthetic desired configuration')
    revision = git(root, 'rev-parse', 'HEAD^{commit}')
    raw = git(root, 'show', revision + ':prod/relay.json', raw=True)
    return loads(raw.decode(), ROOT), revision, raw


def test_real_old_validator_rejects_known_additive_target_but_target_interpreter_accepts(historical):
    roots, old, target, _, _ = historical
    assert old.contract(roots[OLD]) == 'relay-workflows-v3'
    assert json.loads((roots[TARGET] / 'deploy/workflows/contract.json').read_text()) == {
        'workflowContract': 'relay-workflows-v3', 'parallelWorkflowContract': 'relay-workflows-v4'}
    with pytest.raises(ValueError, match='workflow-contract'):
        old.contract(roots[TARGET])
    assert target.contract(roots[TARGET]) == 'relay-workflows-v3'
    assert target.contract(roots[TARGET], True) == 'relay-workflows-v4'


def test_exact_historical_transition_plans_upgrade_with_unchanged_v3_and_selected_git_config(historical, tmp_path):
    roots, _, _, config, consumer = historical
    before = {str(path.relative_to(consumer)): path.read_bytes() for path in consumer.rglob('*') if path.is_file()}
    desired, config_sha, raw = selected_git_config(tmp_path, config)
    # A stale external owner file is not consulted to choose desired values.
    (tmp_path / 'stale-owner.json').write_text(json.dumps(config))
    output = workflow_projection.integration(desired, TARGET, roots[TARGET], consumer, tmp_path / 'integration')
    assert output['compatibility'] in ['compatible', 'stale-compatible']
    assert all((Path(output['directory']) / name).is_file() for name in output['files'])
    assert before == {str(path.relative_to(consumer)): path.read_bytes() for path in consumer.rglob('*') if path.is_file()}
    plan = intent_install.plan({'blockers': [], 'installed': {'status': 'present', 'revision': OLD}}, TARGET,
        json.loads((ROOT / 'deploy/installation-contract.json').read_text()),
        root=ROOT, repository='jresearchsoftware/codex-relay',
        receipt={'config_sha': config_sha, 'config_sha256': hashlib.sha256(raw).hexdigest(), 'product_sha': TARGET})
    assert plan == {'strategy': 'upgrade', 'phase': 'upgrade', 'installed': OLD}
    assert desired['consumer']['defaultProfile'] == {'cliModelId': 'gpt-6.1-sol', 'effort': 'medium'}
    assert desired['environment']['reviewerRepositories'] == ['example/codex-relay', 'example/shared-governance']


def test_real_v3_drift_and_unrecognized_metadata_fail_before_a_host_plan(historical, tmp_path):
    roots, _, _, config, consumer = historical
    route = consumer / config['consumer']['routingWorkflow']
    original = route.read_bytes()
    route.write_bytes(original + b'\n# unreviewed managed edit\n')
    with pytest.raises(ValueError, match='workflow-drift'):
        workflow_projection.integration(config, TARGET, roots[TARGET], consumer, tmp_path / 'drift-output')
    route.write_bytes(original)
    contract = roots[TARGET] / 'deploy/workflows/contract.json'
    contract.write_text(json.dumps({'workflowContract': 'relay-workflows-v3',
        'parallelWorkflowContract': 'relay-workflows-v4', 'untrustedCapability': 'ignored'}))
    with pytest.raises(ValueError, match='workflow-contract'):
        workflow_projection.integration(config, TARGET, roots[TARGET], consumer, tmp_path / 'metadata-output')
    assert not (tmp_path / 'drift-output').exists()
    assert not (tmp_path / 'metadata-output').exists()


@pytest.mark.parametrize('installed', [{'status': 'invalid'},
    {'status': 'present', 'revision': OLD, 'deploymentContract': {'schemaVersion': 1, 'epoch': 2, 'capabilities': ['lifecycle-v1']}}])
def test_historical_missing_or_incompatible_installation_evidence_does_not_authorize_mutation(historical, installed):
    with pytest.raises(ValueError, match='INSTALLED_IDENTITY_UNPROVEN|TRANSITION_UNSUPPORTED'):
        intent_install.plan({'blockers': [], 'installed': installed}, TARGET,
            json.loads((ROOT / 'deploy/installation-contract.json').read_text()),
            root=ROOT, repository='jresearchsoftware/codex-relay')
