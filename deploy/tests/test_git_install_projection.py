"""Git deployment owns its dispatcher; consumer artifacts remain independent."""
import hashlib
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
from config import loads
import workflow_projection as workflows

HEAD = 'a' * 40


def git_config():
    config = json.loads((ROOT / 'deploy/example.json').read_text())
    config['environment']['localApply'] = {
        'source': 'git', 'repository': 'example-org/private-deployment', 'configPath': 'prod/relay.json'}
    return loads(json.dumps(config), ROOT)


def test_private_dispatcher_has_no_checkout_product_input_or_automatic_trigger():
    config = git_config()
    consumer = workflows.render(config, HEAD, ROOT)
    private = workflows.render_deployment(config, HEAD, ROOT)
    assert workflows.PRODUCTION not in consumer
    assert list(private) == [workflows.PRODUCTION]
    text = private[workflows.PRODUCTION].decode()
    assert "github.repository == 'example-org/private-deployment'" in text
    assert "github.ref == 'refs/heads/main'" in text
    assert 'workflow_dispatch:' in text and '  push:' not in text and 'pull_request:' not in text
    assert 'actions/checkout' not in text and 'uses:' not in text
    assert 'contents: read' in text and 'actions: read' in text
    assert 'git:${action}:${installed}:${sha}:${run}' in text
    assert 'child.stdin.end(process.env.RELAY_GIT_TOKEN' in text
    assert 'product_revision:' not in text and 'config_revision:' not in text


def test_missing_consumer_projection_produces_complete_artifact_without_rerun(tmp_path):
    consumer = tmp_path / 'consumer'
    consumer.mkdir()
    result = workflows.integration(git_config(), HEAD, ROOT, consumer, tmp_path / 'artifacts')
    assert result['compatibility'] == 'missing'
    assert not list(consumer.iterdir())
    assert (Path(result['directory']) / workflows.MANIFEST).is_file()
    assert (Path(result['deploymentDirectory']) / workflows.PRODUCTION).is_file()
    assert 'does not need another installer run' in result['next']


def test_drift_is_not_mislabeled_compatible(tmp_path):
    config = git_config()
    consumer = tmp_path / 'consumer'
    consumer.mkdir()
    workflows.project(config, HEAD, ROOT, consumer)
    routing = consumer / config['consumer']['routingWorkflow']
    routing.write_bytes(routing.read_bytes() + b'# unreviewed local edit\n')
    with pytest.raises(ValueError, match='workflow-drift'):
        workflows.integration(config, HEAD, ROOT, consumer, tmp_path / 'artifacts')


def test_known_abi_with_intact_older_baseline_is_stale_compatible(tmp_path):
    config = git_config()
    consumer = tmp_path / 'consumer'
    consumer.mkdir()
    workflows.project(config, HEAD, ROOT, consumer)
    path = config['consumer']['routingWorkflow']
    older = (consumer / path).read_bytes() + b'# accepted older projection fixture\n'
    (consumer / path).write_bytes(older)
    manifest = json.loads((consumer / workflows.MANIFEST).read_text())
    manifest['files'][path] = hashlib.sha256(older).hexdigest()
    (consumer / workflows.MANIFEST).write_text(json.dumps(manifest))
    result = workflows.integration(config, HEAD, ROOT, consumer, tmp_path / 'artifacts')
    assert result['compatibility'] == 'stale-compatible'


def test_invalid_target_contract_is_not_an_additive_compatibility_escape(tmp_path):
    source = tmp_path / 'source'
    (source / 'deploy/workflows').mkdir(parents=True)
    (source / 'deploy/workflows/contract.json').write_text(json.dumps({
        'workflowContract': 'relay-workflows-v3', 'unknownExecutablePolicy': 'ignored'}))
    with pytest.raises(ValueError, match='workflow-contract'):
        workflows.render(git_config(), HEAD, source)


@pytest.mark.parametrize('path', ['../prod/relay.json', '/prod/relay.json', 'prod/relay.sh'])
def test_git_config_paths_are_literal_json_paths(path):
    config = git_config()
    config['environment']['localApply']['configPath'] = path
    with pytest.raises(ValueError, match='localApply.git'):
        loads(json.dumps(config), ROOT)


def test_reviewed_reviewer_target_removal_retains_actual_unit_ownership_check(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location('git_instance_guard',
        ROOT / 'deploy/ansible/scripts/verify_instance_identity.py')
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    config_root, units = tmp_path / 'config', tmp_path / 'units'
    config_root.mkdir()
    units.mkdir()
    (config_root / 'reviewer-mcp.json').write_text(json.dumps({
        'repositories': ['example/first', 'example/second']}))
    with pytest.raises(ValueError, match='REPOSITORY_COLLISION'):
        guard.verify('/opt/fixture', config_root, ['example/first'], [], units)
    guard.verify('/opt/fixture', config_root, ['example/first'], [], units, git_desired=True)
    (units / 'fixture-reviewer.service').write_text('[Service]\nExecStart=/opt/foreign/reviewer-mcp-http\n')
    with pytest.raises(ValueError, match='UNIT_COLLISION'):
        guard.verify('/opt/fixture', config_root, ['example/first'], ['fixture-reviewer.service'],
                     units, git_desired=True)
