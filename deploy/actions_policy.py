"""Owner-only Actions event-policy proposal/read-back; never mutates GitHub.

The worker and runtime Apps do not receive administration permissions. The
owner runs this locally with an independently authenticated GitHub CLI.
"""
import argparse
import json
import re
import subprocess


EVENTS = ['issues', 'pull_request_target', 'workflow_dispatch']
API_VERSION = '2026-03-10'


class PolicyEvidenceUnavailable(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise PolicyEvidenceUnavailable(code)


def target(repository, workflow):
    require(isinstance(repository, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*', repository), 'repository-invalid')
    require(isinstance(workflow, str) and re.fullmatch(r'\.github/workflows/[A-Za-z0-9_-]+\.ya?ml', workflow), 'workflow-invalid')


def proposal(repository, workflow, organization=False):
    target(repository, workflow)
    conditions = {'workflow_path': {'include': [workflow], 'exclude': []}}
    if organization:
        conditions['repository_name'] = {'include': [repository.split('/')[1]], 'exclude': []}
    return {'name': 'Relay routing events', 'enforcement': 'active', 'conditions': conditions,
            'rules': [{'type': 'restrict_action_events', 'parameters': {'allowed_events': list(EVENTS)}}]}


def github_get(path):
    # Explicit GET prevents gh's parameter conventions from selecting POST.
    # stderr is intentionally not returned: external tooling may print secrets.
    try:
        result = subprocess.run(['gh', 'api', '--hostname', 'github.com', '--method', 'GET',
                                 '-H', 'Accept: application/vnd.github+json',
                                 '-H', 'X-GitHub-Api-Version: ' + API_VERSION, path],
                                capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise PolicyEvidenceUnavailable('github-policy-read-unavailable') from error
    require(result.returncode == 0 and len(result.stdout) <= 1024 * 1024, 'github-policy-read-unavailable')
    try:
        return json.loads(result.stdout)
    except (ValueError, UnicodeError) as error:
        raise PolicyEvidenceUnavailable('github-policy-response-invalid') from error


def workflow_applies(policy, workflow):
    conditions = policy.get('conditions')
    require(isinstance(conditions, dict), 'policy-conditions-invalid')
    scope = conditions.get('workflow_path')
    if scope is None:
        return True
    require(isinstance(scope, dict) and isinstance(scope.get('include'), list)
            and isinstance(scope.get('exclude'), list), 'workflow-scope-invalid')
    include, exclude = scope['include'], scope['exclude']
    require(all(isinstance(value, str) for value in include + exclude), 'workflow-scope-invalid')
    # Do not substitute Python glob semantics for GitHub policy semantics. The
    # minimal proposal uses an exact path; complex existing scopes need an
    # owner-admin read-back rather than a false qualification claim.
    require(all(value == '~ALL' or not any(char in value for char in '*?[]{}!')
                for value in include + exclude), 'workflow-pattern-owner-verification-required')
    return workflow not in exclude and (not include or '~ALL' in include or workflow in include)


def read_back(repository, workflow, get=github_get):
    target(repository, workflow)
    prefix = f'repos/{repository}/actions/policies'
    rows = []; expected = None
    for page in range(1, 11):
        value = get(f'{prefix}?has_parents=true&per_page=100&page={page}')
        require(isinstance(value, dict) and isinstance(value.get('policies'), list)
                and type(value.get('total_count')) is int, 'policy-list-invalid')
        expected = value['total_count'] if expected is None else expected
        require(expected == value['total_count'] and expected <= 1000, 'policy-list-changed-or-unbounded')
        rows.extend(value['policies'])
        if len(rows) >= expected:
            break
        require(len(value['policies']) == 100, 'policy-list-incomplete')
    require(len(rows) == expected, 'policy-list-incomplete')
    paths = set(); allowed = []; blocked = []; evaluated = []; actor_policies = []
    for row in rows:
        require(isinstance(row, dict) and type(row.get('id')) is int and row['id'] > 0, 'policy-summary-invalid')
        href = row.get('_links', {}).get('self', {}).get('href', '')
        match = re.fullmatch(r'https://api\.github\.com/((?:repos/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+|orgs/[A-Za-z0-9_.-]+|enterprises/[A-Za-z0-9_.-]+)/actions/policies/([1-9][0-9]*))', href)
        require(match is not None and int(match[2]) == row['id'], 'policy-detail-binding-invalid')
        path = match[1]
        require(not path.startswith('repos/') or path.startswith(prefix + '/'), 'policy-repository-binding-invalid')
        require(not path.startswith('orgs/') or path.startswith('orgs/' + repository.split('/')[0] + '/'), 'policy-organization-binding-invalid')
        require(path not in paths, 'policy-list-duplicate'); paths.add(path)
        detail = get(path)
        require(isinstance(detail, dict) and detail.get('id') == row['id']
                and detail.get('enforcement') == row.get('enforcement')
                and detail.get('source_type') == row.get('source_type')
                and detail.get('source') == row.get('source'), 'policy-detail-changed')
        require(detail.get('enforcement') in ['active', 'evaluate', 'disabled']
                and isinstance(detail.get('rules'), list), 'policy-detail-invalid')
        if detail['enforcement'] == 'disabled' or not workflow_applies(detail, workflow):
            continue
        for rule in detail['rules']:
            require(isinstance(rule, dict), 'policy-rule-invalid')
            if rule.get('type') == 'restrict_actions_actors':
                actor_policies.append(path)
            if rule.get('type') != 'restrict_action_events':
                continue
            events = rule.get('parameters', {}).get('allowed_events')
            require(isinstance(events, list) and all(isinstance(event, str) for event in events), 'policy-events-invalid')
            if detail['enforcement'] == 'evaluate':
                evaluated.append(path)
            elif set(EVENTS).issubset(events):
                allowed.append(path)
            else:
                blocked.append({'policy': path, 'missingEvents': sorted(set(EVENTS) - set(events))})
    return {'repository': repository, 'workflow': workflow,
            'eventPolicy': 'BLOCKED' if blocked else 'QUALIFIED' if allowed else 'UNVERIFIED',
            'activeAllowPolicies': allowed, 'blockingPolicies': blocked, 'evaluatePolicies': evaluated,
            'actorPoliciesRequireOwnerVerification': sorted(set(actor_policies)),
            'representativeOwnerLabelTrigger': 'REQUIRED_AFTER_INDEPENDENT_ACCEPTANCE',
            'scope': 'event-policy-read-back-only'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', required=True)
    parser.add_argument('--workflow', required=True)
    parser.add_argument('--proposal', action='store_true', help='Print proposal only; no GitHub request')
    parser.add_argument('--organization', action='store_true', help='Scope proposal to this organization repository')
    args = parser.parse_args()
    try:
        require(not args.organization or args.proposal, 'organization-is-proposal-only')
        result = proposal(args.repository, args.workflow, args.organization) if args.proposal else read_back(args.repository, args.workflow)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if args.proposal or result['eventPolicy'] == 'QUALIFIED' else 1
    except PolicyEvidenceUnavailable as error:
        print(json.dumps({'eventPolicy': 'UNVERIFIED', 'reason': str(error), 'ownerAdminHandoff': True}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
