"""Public Reviewer target configuration, preflight and per-target App probes."""
import getpass
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap
import uuid

import pytest
import yaml
from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / 'deploy/ansible'
sys.path.insert(0, str(ROOT / 'deploy'))
import config

spec = importlib.util.spec_from_file_location('reviewer_repository_guard',
                                            BACKEND / 'scripts/verify_instance_identity.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
PRIMARY = 'example-org/sample-project'
SECOND = 'example-org/shared-governance'
RUNTIME = BACKEND / 'roles/relay_runtime/templates'


def inputs(repositories=None):
    public = json.loads((ROOT / 'deploy/example.json').read_text())
    if repositories is not None:
        public['environment']['reviewerRepositories'] = repositories
    config.validate(public, ROOT)
    return public


def values(public):
    return {**yaml.safe_load((BACKEND / 'group_vars/all.yml').read_text()),
            **config.compile_inputs(public), 'relay_release_commit': 'a' * 40,
            'relay_release_sha256': 'b' * 64}


def render(path, variables):
    return Templar(loader=DataLoader(), variables=variables).template(
        path.read_text(), convert_data=False)


@pytest.mark.parametrize('repositories,expected', [
    (None, {'repository': PRIMARY}),
    ([PRIMARY], {'repository': PRIMARY}),
    ([SECOND], {'repository': SECOND}),
    ([PRIMARY, PRIMARY], {'repository': PRIMARY}),
    ([SECOND, PRIMARY, SECOND], {'repositories': sorted([PRIMARY, SECOND])}),
])
def test_public_targets_render_compatible_config_without_changing_writer(repositories, expected):
    public = inputs(repositories)
    compiled = config.compile_inputs(public)
    legacy = config.compile_inputs(inputs())
    targets = compiled.pop('relay_reviewer_repositories')
    legacy.pop('relay_reviewer_repositories')
    assert compiled == legacy  # Only Reviewer targets change, including for a Reviewer-only target.
    assert targets == sorted(set(repositories or [PRIMARY]))
    variables = values(public)
    reviewer = json.loads(render(RUNTIME / 'reviewer-mcp.json.j2', variables))
    assert {key: reviewer[key] for key in ['repository', 'repositories'] if key in reviewer} == expected
    legacy_reviewer = json.loads(render(RUNTIME / 'reviewer-mcp.json.j2', values(inputs())))
    assert {key: value for key, value in reviewer.items() if key not in ['repository', 'repositories']} == {
        key: value for key, value in legacy_reviewer.items() if key != 'repository'}
    writer_snapshot = json.loads(render(BACKEND / 'roles/relay_controller/templates/consumer.json.j2', variables))
    assert writer_snapshot == public['consumer']
    writer_probe = render(BACKEND / 'roles/relay_controller/templates/relay-writer-app-qualification.j2', variables)
    assert f"RELAY_EXPECTED_REPOSITORY='{PRIMARY}'" in writer_probe
    assert SECOND not in writer_probe


@pytest.mark.parametrize('repositories', [
    [], None, PRIMARY, {}, [None], [True], [1], [''], ['foreign'], ['org/repo/extra'],
    ['-org/repo'], ['org-/repo'], ['org--name/repo'], ['org.name/repo'],
    ['a' * 40 + '/repo'], ['org/' + 'a' * 101], ['org/.'], ['org/..'],
    ["org/repo';exit 0;#"], ['org/repo\nother/repo'],
])
def test_invalid_public_targets_fail_before_backend(repositories):
    public = inputs()
    public['environment']['reviewerRepositories'] = repositories
    with pytest.raises(config.InvalidConfig, match='reviewerRepositories'):
        config.validate(public, ROOT)


@pytest.mark.parametrize('installed,expected', [
    ({'repository': PRIMARY}, [PRIMARY]),
    ({'repository': PRIMARY}, [PRIMARY, SECOND]),
    ({'repositories': [PRIMARY]}, [PRIMARY, SECOND]),
    ({'repositories': [SECOND, PRIMARY, SECOND]}, [PRIMARY, SECOND]),
    ({'repositories': [PRIMARY, SECOND]}, [PRIMARY, SECOND, 'example-org/third']),
])
def test_preflight_accepts_legacy_upgrade_and_normalized_repository_sets(tmp_path, installed, expected):
    path = tmp_path / 'reviewer-mcp.json'
    path.write_text(json.dumps(installed))
    before = path.read_bytes()
    guard.verify('/opt/fixture', str(tmp_path), expected, [], tmp_path)
    assert path.read_bytes() == before


@pytest.mark.parametrize('installed', [
    {'repository': 'foreign/repository'}, {'repositories': ['foreign/repository']},
    {'repositories': [PRIMARY, 'foreign/repository']}, {}, {'repositories': []},
    {'repository': PRIMARY, 'repositories': [PRIMARY, SECOND]},
    {'repositories': PRIMARY}, {'repositories': [PRIMARY, False]}, {'repository': ['org/repo']},
])
def test_preflight_rejects_foreign_or_ambiguous_installed_targets(tmp_path, installed):
    path = tmp_path / 'reviewer-mcp.json'
    path.write_text(json.dumps(installed))
    before = path.read_bytes()
    with pytest.raises(ValueError, match='REPOSITORIES_INVALID|REPOSITORY_COLLISION'):
        guard.verify('/opt/fixture', str(tmp_path), [PRIMARY, SECOND], [], tmp_path)
    assert path.read_bytes() == before


@pytest.mark.skipif(sys.platform != 'linux' or not shutil.which('ansible-playbook'),
                    reason='Linux localhost Ansible required')
@pytest.mark.parametrize('installed,accepted', [
    ({'repository': PRIMARY}, True),
    ({'repositories': [SECOND, PRIMARY]}, True),
    ({'repositories': [PRIMARY, 'foreign/repository']}, False),
])
def test_actual_preflight_then_config_render_supports_two_targets(tmp_path, installed, accepted):
    (tmp_path / 'scripts').mkdir()
    shutil.copyfile(BACKEND / 'scripts/verify_instance_identity.py',
                    tmp_path / 'scripts/verify_instance_identity.py')
    config_root = tmp_path / 'config'
    config_root.mkdir()
    path = config_root / 'reviewer-mcp.json'
    path.write_text(json.dumps(installed))
    before = path.read_bytes()
    variables = values(inputs([PRIMARY, SECOND]))
    variables.update(relay_config_root=str(config_root), relay_install_root=str(tmp_path / 'install'),
                     relay_reviewer_user='fixture-' + uuid.uuid4().hex[:12])
    for key in list(variables):
        if key.endswith('_service_name') or key == 'relay_reviewer_recovery_timer_name':
            variables[key] = variables['relay_reviewer_user'] + '-' + variables[key]
    preflight = yaml.safe_load((BACKEND / 'roles/relay_preflight/tasks/main.yml').read_text())[0]
    playbook = tmp_path / 'preflight.yml'
    playbook.write_text(yaml.safe_dump([{'hosts': 'localhost', 'gather_facts': False,
        'vars': variables, 'tasks': [preflight, {'ansible.builtin.template': {
            'src': str(RUNTIME / 'reviewer-mcp.json.j2'), 'dest': str(path), 'mode': '0640'}}]}]))
    result = subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(playbook)],
                            cwd=tmp_path, env={**os.environ, 'ANSIBLE_NOCOLOR': '1'},
                            capture_output=True, text=True, timeout=60)
    assert (result.returncode == 0) == accepted, result.stdout + result.stderr
    if accepted:
        assert json.loads(path.read_text())['repositories'] == sorted([PRIMARY, SECOND])
        assert 'repository' not in json.loads(path.read_text())
    else:
        assert 'RELAY_INSTANCE_IDENTITY_REJECTED' in result.stdout + result.stderr
        assert path.read_bytes() == before


@pytest.mark.parametrize('repositories,failing_target', [
    (None, None), ([PRIMARY, SECOND], None), ([PRIMARY, SECOND], SECOND),
    ([PRIMARY, SECOND], PRIMARY),
])
def test_rendered_reviewer_wrapper_probes_each_target_with_same_identity(tmp_path, repositories, failing_target):
    variables = values(inputs(repositories))
    variables.update(relay_install_root=str(tmp_path), relay_reviewer_user=getpass.getuser(),
                     relay_reviewer_credential_env_file=str(tmp_path / 'app.env'))
    (tmp_path / 'app.env').write_text(textwrap.dedent('''\
        GITHUB_APP_ID=102
        GITHUB_APP_INSTALLATION_ID=202
    '''))
    # Execute the real helper's qualification and output logic with synthetic
    # signing/transport. No root-owned key, live App or GitHub request is used.
    helper = BACKEND / 'roles/relay_runtime/files/relay-app-qualification.py'
    (tmp_path / 'relay-app-qualification.py').write_text(textwrap.dedent(f'''\
        import importlib.util
        import json
        import os
        from pathlib import Path
        spec = importlib.util.spec_from_file_location('app_probe', {str(helper)!r})
        probe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(probe)
        target = os.environ['RELAY_EXPECTED_REPOSITORY']
        config = {{'role': os.environ['RELAY_APP_ROLE'], 'app_id': os.environ['GITHUB_APP_ID'],
                   'installation_id': os.environ['GITHUB_APP_INSTALLATION_ID'],
                   'slug': os.environ['RELAY_EXPECTED_APP_SLUG'],
                   'expected_actor': os.environ['RELAY_EXPECTED_ACTOR'], 'repository': target}}
        permissions = probe.expected_installation_permissions(config)
        installation = {{'id': int(config['installation_id']), 'app_id': int(config['app_id']),
                         'app_slug': config['slug'], 'repository_selection': 'selected',
                         'permissions': permissions}}
        def request(method, endpoint, token, body=None):
            with Path({str(tmp_path / 'requests.jsonl')!r}).open('a') as log:
                log.write(json.dumps({{'method': method, 'endpoint': endpoint, 'body': body,
                                      'identity': config}}) + '\\n')
            if endpoint == '/app':
                return {{'id': int(config['app_id']), 'slug': config['slug']}}
            if endpoint == '/app/installations/' + config['installation_id']:
                return installation
            if endpoint == '/repos/' + target + '/installation':
                if target == {failing_target!r}:
                    return {{**installation, 'id': 999}}
                return installation
            if endpoint.endswith('/access_tokens'):
                return {{'token': 'synthetic-token', 'expires_at': 'synthetic-expiry',
                         'permissions': {{'metadata': 'read'}}}}
            if endpoint == '/repos/' + target:
                return {{'full_name': target}}
            raise AssertionError(endpoint)
        probe.validate_configuration = lambda: config
        probe.create_app_jwt = lambda config: 'synthetic-jwt'
        probe.parse_expiry = lambda value: 3600
        probe.request_json = request
        raise SystemExit(probe.main())
    '''))
    wrapper = tmp_path / 'qualify.sh'
    wrapper.write_text(render(RUNTIME / 'relay-reviewer-app-qualification.j2', variables))
    result = subprocess.run(['sh', str(wrapper)], capture_output=True, text=True, timeout=20)
    assert (result.returncode == 0) == (failing_target is None), result.stdout + result.stderr
    targets = sorted(repositories or [PRIMARY])
    visited = targets[:targets.index(failing_target) + 1] if failing_target else targets
    requests = [json.loads(row) for row in (tmp_path / 'requests.jsonl').read_text().splitlines()]
    assert {row['identity']['repository'] for row in requests} == set(visited)
    for target in visited:
        rows = [row for row in requests if row['identity']['repository'] == target]
        assert rows
        assert all(row['identity'] == {'repository': target, 'app_id': '102', 'installation_id': '202',
                    'slug': 'example-reviewer', 'expected_actor': 'example-reviewer[bot]', 'role': 'reviewer'} for row in rows)
        assert any(row['endpoint'] == '/repos/' + target + '/installation' for row in rows)
        if target != failing_target:
            assert rows[-1]['endpoint'] == '/repos/' + target
            token_request = next(row for row in rows if row['endpoint'].endswith('/access_tokens'))
            assert token_request['body'] == {'repositories': [target.split('/')[1]],
                                             'permissions': {'metadata': 'read'}}
            assert f'repository={target} ' in result.stdout
        else:
            assert rows[-1]['endpoint'] == '/repos/' + target + '/installation'
            assert f'repository={target} ' not in result.stdout
            assert 'APP_QUALIFICATION_FAIL code=REPOSITORY_INSTALLATION_INSTALLATION_MISMATCH' in result.stdout
