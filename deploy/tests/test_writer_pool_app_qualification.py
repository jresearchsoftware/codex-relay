"""Rendered protected Writer probe with synthetic GitHub, no live credentials."""
import copy
import json
import os
from pathlib import Path
import subprocess
import textwrap

import pytest
import yaml
from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar

from test_managed_pool import inputs
import config

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / 'deploy/ansible'
TEMPLATE = BACKEND / 'roles/relay_controller/templates/relay-writer-app-qualification.j2'
REPOSITORIES = ['example-org/relay', 'example-org/governance',
                'example-org/models', 'example-org/docs']
WRITER_PERMISSIONS = dict(metadata='read', contents='write', issues='write',
                          pull_requests='write', workflows='write')
RUNNERS = 'organization_self_hosted_runners'


def run_probe(tmp_path, case='valid', *, pool=True, plural=True):
    public = inputs(capacity=6, repository=REPOSITORIES[0]) if pool else json.loads(
        (ROOT / 'deploy/example.json').read_text())
    if plural:
        public['consumer'].pop('repository')
        public['consumer']['repositories'] = REPOSITORIES
        public['environment']['repository'] = REPOSITORIES[0]
    if case == 'separate-app':
        public['environment']['generalRunner']['poolApp'].update(appId='999', installationId='998')
    elif case == 'different-app':
        public['environment']['generalRunner']['poolApp']['appId'] = '999'
    elif case == 'different-installation':
        public['environment']['generalRunner']['poolApp']['installationId'] = '998'
    config.validate(public, ROOT)
    variables = config.compile_inputs(public)
    variables.update(relay_install_root=str(tmp_path), relay_writer_credential_env_file=str(tmp_path / 'app.env'))
    (tmp_path / 'app.env').write_text('GITHUB_APP_ID=101\nGITHUB_APP_INSTALLATION_ID=201\n')
    # Simulate root at the shell boundary only. Actual key ownership/signing and
    # live installation are outside this deterministic test's evidence.
    bin_path = tmp_path / 'bin'
    bin_path.mkdir()
    (bin_path / 'id').write_text('#!/bin/sh\necho ' + ('1000' if case == 'nonroot' else '0') + '\n')
    (bin_path / 'id').chmod(0o755)
    permissions = {**WRITER_PERMISSIONS, RUNNERS: 'write'}
    if case == 'separate-app-valid':
        public['environment']['generalRunner']['poolApp'].update(appId='999', installationId='998')
        variables['relay_general_runner_pool'].update(appId='999', installationId='998')
        permissions.pop(RUNNERS)
    if case == 'nonpool-valid':
        permissions.pop(RUNNERS)
    if case == 'missing-runner-permission':
        permissions.pop(RUNNERS)
    if case == 'weak-runner-permission':
        permissions[RUNNERS] = 'read'
    if case == 'foreign-write':
        permissions['administration'] = 'write'
    if case == 'foreign-admin':
        permissions['organization_administration'] = 'admin'
    if case == 'runner-admin':
        permissions[RUNNERS] = 'admin'
    installation = {'id': 201, 'app_id': 101, 'app_slug': 'example-writer',
                    'repository_selection': 'selected', 'permissions': permissions,
                    'account': {'login': 'example-org', 'type': 'Organization'}}
    repo_installation = copy.deepcopy(installation)
    if case == 'foreign-organization':
        installation['account']['login'] = 'foreign-org'
    if case == 'user-account':
        installation['account']['type'] = 'User'
    if case == 'missing-account':
        installation.pop('account')
    if case == 'repository-organization':
        repo_installation['account']['login'] = 'foreign-org'
    if case == 'repository-installation':
        repo_installation['id'] = 999
    if case == 'repository-app':
        repo_installation['app_id'] = 999
    if case == 'installation-app':
        installation['app_id'] = 999
    token_permissions = {'metadata': 'read'}
    if case == 'token-write':
        token_permissions[RUNNERS] = 'write'
    (tmp_path / 'relay-app-qualification.py').write_text(textwrap.dedent(f'''\
        import importlib.util
        import json
        import os
        from datetime import datetime, timedelta, timezone
        from pathlib import Path
        spec = importlib.util.spec_from_file_location('probe', {str(BACKEND / 'roles/relay_runtime/files/relay-app-qualification.py')!r})
        probe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(probe)
        target = os.environ['RELAY_EXPECTED_REPOSITORY']
        config = {{'role': os.environ['RELAY_APP_ROLE'], 'app_id': os.environ['GITHUB_APP_ID'],
                  'installation_id': os.environ['GITHUB_APP_INSTALLATION_ID'],
                  'slug': os.environ['RELAY_EXPECTED_APP_SLUG'],
                  'expected_actor': os.environ['RELAY_EXPECTED_ACTOR'], 'repository': target}}
        def request(method, endpoint, token, body=None):
            with Path({str(tmp_path / 'requests.jsonl')!r}).open('a') as log:
                log.write(json.dumps({{'method': method, 'endpoint': endpoint, 'body': body}}) + '\\n')
            if endpoint == '/app':
                return {{'id': {999 if case == 'app-identity' else 101}, 'slug': 'example-writer'}}
            if endpoint == '/app/installations/201':
                return {installation!r}
            if endpoint == '/repos/' + target + '/installation':
                return {repo_installation!r}
            if endpoint.endswith('/access_tokens'):
                return {{'token': 'synthetic-token', 'permissions': {token_permissions!r},
                        'expires_at': (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}}
            if endpoint == '/repos/' + target:
                return {{'full_name': {'"foreign-org/other"' if case == 'repository-probe' else 'target'}}}
            raise AssertionError(endpoint)
        probe.validate_configuration = lambda: config
        probe.create_app_jwt = lambda config: 'synthetic-jwt'
        probe.request_json = request
        raise SystemExit(probe.main())
    '''))
    wrapper = tmp_path / 'qualify.sh'
    wrapper.write_text(Templar(loader=DataLoader(), variables=variables).template(
        TEMPLATE.read_text(), convert_data=False))
    # Hostile inherited binding must never enable the singleton exception.
    inherited = json.dumps(dict(appId='101', installationId='201', organization='example-org',
                                repositories=REPOSITORIES))
    result = subprocess.run(['sh', str(wrapper)], capture_output=True, text=True, timeout=20,
                            env={**os.environ, 'PATH': str(bin_path) + ':' + os.environ['PATH'],
                                 'RELAY_MANAGED_POOL_BINDING': inherited})
    requests = tmp_path / 'requests.jsonl'
    return result, [json.loads(row) for row in requests.read_text().splitlines()] if requests.exists() else []


def test_plural_pool_writer_accepts_only_bound_runner_scope_with_read_only_tokens(tmp_path):
    result, requests = run_probe(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count('APP_QUALIFICATION_PASS') == 4
    for repository in REPOSITORIES:
        assert f'repository={repository} ' in result.stdout
    tokens = [row for row in requests if row['method'] == 'POST']
    assert [row['body'] for row in tokens] == [
        {'repositories': [repository.split('/')[1]], 'permissions': {'metadata': 'read'}}
        for repository in REPOSITORIES]
    assert all(row['endpoint'].endswith('/access_tokens') for row in tokens)
    assert 'synthetic-token' not in result.stdout + result.stderr
    assert 'synthetic-jwt' not in result.stdout + result.stderr


@pytest.mark.parametrize('case,code', [
    ('separate-app', 'PERMISSION_SCOPE_TOO_BROAD'),
    ('different-app', 'PERMISSION_SCOPE_TOO_BROAD'),
    ('different-installation', 'PERMISSION_SCOPE_TOO_BROAD'),
    ('foreign-write', 'PERMISSION_SCOPE_TOO_BROAD'),
    ('foreign-admin', 'PERMISSION_SCOPE_TOO_BROAD'),
    ('runner-admin', 'ADMIN_PERMISSION_FORBIDDEN'),
    ('missing-runner-permission', 'PERMISSION_INSUFFICIENT'),
    ('weak-runner-permission', 'PERMISSION_INSUFFICIENT'),
    ('foreign-organization', 'POOL_ORGANIZATION_MISMATCH'),
    ('user-account', 'POOL_ORGANIZATION_MISMATCH'),
    ('missing-account', 'ACCOUNT_INVALID'),
    ('repository-organization', 'POOL_ORGANIZATION_MISMATCH'),
    ('repository-installation', 'INSTALLATION_MISMATCH'),
    ('repository-app', 'APP_MISMATCH'),
    ('installation-app', 'APP_MISMATCH'),
    ('app-identity', 'APP_IDENTITY_MISMATCH'),
    ('repository-probe', 'REPOSITORY_PROBE_SCOPE_MISMATCH'),
    ('token-write', 'TOKEN_PERMISSION_SCOPE_TOO_BROAD'),
    ('nonroot', 'APP_QUALIFICATION_WRONG_BOUNDARY'),
])
def test_pool_writer_fails_closed(tmp_path, case, code):
    result, _ = run_probe(tmp_path, case)
    assert result.returncode != 0
    assert code in result.stdout, result.stdout + result.stderr
    assert 'APP_QUALIFICATION_PASS' not in result.stdout


@pytest.mark.parametrize('plural', [False, True])
def test_nonpool_writer_rejects_runner_scope_even_if_inherited(tmp_path, plural):
    result, _ = run_probe(tmp_path, pool=False, plural=plural)
    assert result.returncode != 0
    assert 'APP_INSTALLATION_PERMISSION_SCOPE_TOO_BROAD' in result.stdout


@pytest.mark.parametrize('case,pool', [('separate-app-valid', True), ('nonpool-valid', False)])
def test_ordinary_writer_and_separate_pool_app_keep_original_permissions(tmp_path, case, pool):
    result, _ = run_probe(tmp_path, case, pool=pool)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count('APP_QUALIFICATION_PASS') == 4


def test_wrapper_and_service_constraints_remain_protected():
    tasks = yaml.safe_load((BACKEND / 'roles/relay_controller/tasks/main.yml').read_text())
    task = next(task for task in tasks if task.get('ansible.builtin.template', {}).get('src') == TEMPLATE.name)
    assert {key: task['ansible.builtin.template'][key] for key in ['owner', 'group', 'mode']} == {
        'owner': 'root', 'group': 'root', 'mode': '0750'}
    assert 'id -u' in TEMPLATE.read_text()
    assert not any('restart' in task.get('name', '').lower() for task in tasks)
