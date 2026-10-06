"""Bounded API read-back/proposal tests; no live admin or GitHub operation."""
import copy
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
import actions_policy as policy

REPOSITORY = 'example-owner/example-repo'
WORKFLOW = '.github/workflows/relay-routing.yml'


def reader(*details):
    rows = []
    responses = {}
    for index, detail in enumerate(details, start=1):
        detail = copy.deepcopy(detail)
        source = detail.pop('test_source', f'repos/{REPOSITORY}')
        detail.update(id=index, source_type='Repository' if source.startswith('repos/') else 'Organization', source='example-owner')
        path = f'{source}/actions/policies/{index}'
        rows.append({key: detail[key] for key in ['id', 'source_type', 'source', 'enforcement']})
        rows[-1]['_links'] = {'self': {'href': 'https://api.github.com/' + path}}
        responses[path] = detail
    responses[f'repos/{REPOSITORY}/actions/policies?has_parents=true&per_page=100&page=1'] = {'total_count': len(rows), 'policies': rows}
    calls = []
    def get(path):
        calls.append(path)
        return copy.deepcopy(responses[path])
    return get, calls, responses


def test_minimal_proposal_is_scoped_without_mutation_or_broader_events():
    result = policy.proposal(REPOSITORY, WORKFLOW)
    assert result['enforcement'] == 'active'
    assert result['conditions'] == {'workflow_path': {'include': [WORKFLOW], 'exclude': []}}
    assert result['rules'][0]['parameters']['allowed_events'] == ['issues', 'pull_request_target', 'workflow_dispatch']
    assert policy.proposal(REPOSITORY, WORKFLOW, True)['conditions']['repository_name']['include'] == ['example-repo']
    result = subprocess.run([sys.executable, str(ROOT / 'deploy/actions_policy.py'), '--repository', REPOSITORY,
                             '--workflow', WORKFLOW, '--proposal'], capture_output=True, text=True, check=True)
    assert json.loads(result.stdout) == policy.proposal(REPOSITORY, WORKFLOW)


def test_read_back_includes_inherited_rules_and_never_overrides_their_denial():
    inherited = policy.proposal(REPOSITORY, WORKFLOW)
    inherited['test_source'] = 'orgs/example-owner'
    inherited['rules'][0]['parameters']['allowed_events'].remove('pull_request_target')
    get, calls, _ = reader(policy.proposal(REPOSITORY, WORKFLOW), inherited)
    result = policy.read_back(REPOSITORY, WORKFLOW, get)
    assert result['eventPolicy'] == 'BLOCKED'
    assert result['blockingPolicies'][0]['missingEvents'] == ['pull_request_target']
    assert calls[0].endswith('has_parents=true&per_page=100&page=1')
    assert calls[-1] == 'orgs/example-owner/actions/policies/2'


@pytest.mark.parametrize('enforcement', ['disabled', 'evaluate'])
def test_non_active_allowance_does_not_prove_effective_policy(enforcement):
    proposal = policy.proposal(REPOSITORY, WORKFLOW); proposal['enforcement'] = enforcement
    get, _, _ = reader(proposal)
    assert policy.read_back(REPOSITORY, WORKFLOW, get)['eventPolicy'] == 'UNVERIFIED'


def test_qualified_events_still_require_representative_owner_trigger_and_actor_verification():
    proposal = policy.proposal(REPOSITORY, WORKFLOW)
    proposal['rules'].append({'type': 'restrict_actions_actors', 'parameters': {'allowed_actors': []}})
    get, _, _ = reader(proposal)
    result = policy.read_back(REPOSITORY, WORKFLOW, get)
    assert result['eventPolicy'] == 'QUALIFIED'
    assert result['representativeOwnerLabelTrigger'] == 'REQUIRED_AFTER_INDEPENDENT_ACCEPTANCE'
    assert result['actorPoliciesRequireOwnerVerification']


@pytest.mark.parametrize('change', ['foreign-url', 'wrong-id', 'changed-enforcement', 'missing-row', 'unsupported-glob'])
def test_incomplete_or_unbound_read_back_remains_unverified(change):
    get, _, responses = reader(policy.proposal(REPOSITORY, WORKFLOW))
    list_path = f'repos/{REPOSITORY}/actions/policies?has_parents=true&per_page=100&page=1'
    detail_path = f'repos/{REPOSITORY}/actions/policies/1'
    if change == 'foreign-url':
        responses[list_path]['policies'][0]['_links']['self']['href'] = 'https://foreign.example/actions/policies/1'
    elif change == 'wrong-id':
        responses[detail_path]['id'] = 5
    elif change == 'changed-enforcement':
        responses[detail_path]['enforcement'] = 'disabled'
    elif change == 'missing-row':
        responses[list_path]['total_count'] = 2
    else:
        responses[detail_path]['conditions']['workflow_path']['include'] = ['.github/workflows/*.yml']
    with pytest.raises(policy.PolicyEvidenceUnavailable):
        policy.read_back(REPOSITORY, WORKFLOW, get)


def test_authenticated_transport_can_only_issue_get_and_hides_external_error_stream():
    with patch.object(policy.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, b'{}', b'private')) as run:
        assert policy.github_get('repos/example-owner/example-repo/actions/policies') == {}
        assert run.call_args[0][0][4:6] == ['--method', 'GET']
    with patch.object(policy.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, b'', b'sensitive data')):
        with pytest.raises(policy.PolicyEvidenceUnavailable, match='github-policy-read-unavailable'):
            policy.github_get('repos/example-owner/example-repo/actions/policies')
