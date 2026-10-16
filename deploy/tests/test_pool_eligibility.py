"""Native protected snapshot discovery without installed code or live calls."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
import pool_eligibility as eligibility
from managed_pool import GitHub, PoolError

pytestmark = pytest.mark.skipif(sys.platform != 'linux', reason='native Linux protected filesystem')
HEAD = 'a' * 40


@pytest.fixture
def contract():
    repository = 'example-org/current'
    return {'name': 'shared-general', 'runnerUser': 'relay-general',
            'organization': 'example-org', 'group': 'trusted-general',
            'appId': '101', 'installationId': '201', 'namespace': 'current-relay',
            'repository': repository, 'workflowRefs': [
                repository + '/.github/workflows/routing.yml@refs/heads/main',
                repository + '/.github/workflows/recovery.yml@refs/heads/main']}


def configuration(contract, namespace, repository):
    return {'schemaVersion': 1,
            'consumer': {'version': 1, 'repository': repository,
                         'baseBranch': 'trusted/base',
                         'routingWorkflow': '.github/workflows/peer-routing.yaml',
                         'recoveryWorkflow': '.github/workflows/peer-recovery.yaml',
                         'validationWorkflow': '.github/workflows/validation.yaml',
                         'generalRunnerPool': {'desiredCapacity': 2}},
            'environment': {'namespace': namespace, 'generalRunner': {
                'name': contract['name'], 'user': contract['runnerUser'],
                'scope': 'organization', 'group': contract['group'],
                'poolApp': {'appId': contract['appId'], 'installationId': contract['installationId'],
                            'privateKeyFile': '/owner-only/not-read.pem'}}}}


def write_json(path, value, mode):
    raw = (json.dumps(value, sort_keys=True) + '\n').encode()
    path.write_bytes(raw)
    path.chmod(mode)
    return raw


def peer(root, contract, namespace='peer-relay', repository='example-org/peer'):
    root.chmod(0o700)
    install = root / 'opt' / namespace
    release = install / 'releases' / HEAD
    source = release / 'reviewed-source'
    source.mkdir(parents=True)
    for directory in [root / 'opt', install, install / 'releases', release, source]:
        directory.chmod(0o755)
    current = install / 'current'
    current.symlink_to('/opt/' + namespace + '/releases/' + HEAD)
    config = configuration(contract, namespace, repository)
    snapshot = release / 'deployment-config.json'
    raw = write_json(snapshot, config, 0o600)
    identity = source / '.relay-source.json'
    write_json(identity, {'revision': HEAD, 'tree': 'e' * 40}, 0o644)
    manifest = release / 'artifact-manifest.json'
    write_json(manifest, {'commit': HEAD, 'resolvedRevision': HEAD, 'installedRevision': HEAD,
                          'gitTree': 'e' * 40,
                          'consumerRevision': 'b' * 40,
                          'deploymentConfigSha256': hashlib.sha256(raw).hexdigest()}, 0o600)
    return SimpleNamespace(install=install, release=release, source=source, current=current,
                           snapshot=snapshot, identity=identity, manifest=manifest, config=config)


def save(fixture):
    raw = write_json(fixture.snapshot, fixture.config, 0o600)
    manifest = json.loads(fixture.manifest.read_bytes())
    manifest['deploymentConfigSha256'] = hashlib.sha256(raw).hexdigest()
    write_json(fixture.manifest, manifest, 0o600)


def observe(root, contract):
    return eligibility.eligible_workflows(contract, root=root, owner_uid=os.getuid())


def refs(config):
    consumer = config['consumer']
    return [consumer['repository'] + '/' + consumer[key] + '@refs/heads/' + consumer['baseBranch']
            for key in ['routingWorkflow', 'recoveryWorkflow']]


def installed_lifecycle(config, repository):
    config['source'] = {'repository': 'https://github.com/' + repository + '.git', 'revision': 'main'}
    config['environment']['localApply'] = {'source': 'installed'}
    config['consumer']['baseBranch'] = 'main'


def lifecycle_ref(repository, branch='main'):
    return repository + '/.github/workflows/manual-main-production-deploy.yml@refs/heads/' + branch


def test_two_protected_peers_supply_exact_refs_without_schema_or_source_execution(tmp_path, contract):
    first = peer(tmp_path, contract)
    second = peer(tmp_path, contract, 'second-relay', 'example-org/second')
    second.config['consumer']['baseBranch'] = 'release/stable'
    second.config['consumer']['generalRunnerPool']['desiredCapacity'] = 15
    save(second)
    second.current.unlink()
    second.current.symlink_to('releases/' + HEAD)
    # Neither source module exists. A peer cannot supply executable validators.
    (first.source / 'consumer-config.mjs').write_text('throw new Error("must never execute")')
    result = observe(tmp_path, contract)
    assert result == {contract['repository']: contract['workflowRefs'],
                      first.config['consumer']['repository']: refs(first.config),
                      second.config['consumer']['repository']: refs(second.config)}
    assert 'validation' not in '\n'.join(result[first.config['consumer']['repository']])
    assert not (first.install / 'pool.json').exists()


def test_fresh_host_needs_only_prospective_configuration(tmp_path, contract):
    assert observe(tmp_path, contract) == {contract['repository']: contract['workflowRefs']}


@pytest.mark.parametrize('bad', ['path', 'branch', 'tag', 'repository', 'non-anchor', 'fourth'])
def test_optional_lifecycle_contract_is_fixed_to_the_installation_anchor(tmp_path, contract, bad):
    repository = contract['repository']
    lifecycle = repository + '/.github/workflows/manual-main-production-deploy.yml@refs/heads/main'
    contract['workflowRefs'].append(lifecycle)
    assert observe(tmp_path, contract)[repository] == contract['workflowRefs']
    if bad == 'path':
        contract['workflowRefs'][2] = lifecycle.replace('manual-main-production-deploy', 'unknown')
    elif bad == 'branch':
        contract['workflowRefs'][2] = lifecycle.replace('/main', '/candidate')
    elif bad == 'tag':
        contract['workflowRefs'][2] = lifecycle.replace('refs/heads/', 'refs/tags/')
    elif bad == 'repository':
        contract['workflowRefs'][2] = lifecycle.replace(repository, 'example-org/foreign')
    elif bad == 'non-anchor':
        other = 'example-org/other'
        contract['repositories'] = [repository, other]
        contract['workflowRefsByRepository'] = {
            repository: contract['workflowRefs'][:2],
            other: [value.replace(repository, other) for value in contract['workflowRefs']]}
    else:
        contract['workflowRefs'].append(repository + '/.github/workflows/extra.yml@refs/heads/main')
    with pytest.raises(PoolError, match='ELIGIBILITY_CONTRACT_INVALID'):
        observe(tmp_path, contract)


@pytest.mark.parametrize('anchor', [None, 'example-org/foreign', '../invalid'])
def test_protected_multi_repository_peer_requires_its_own_valid_lifecycle_anchor(tmp_path, contract, anchor):
    fixture = peer(tmp_path, contract)
    repository = fixture.config['consumer'].pop('repository')
    installed_lifecycle(fixture.config, repository)
    fixture.config['consumer']['repositories'] = [repository, 'example-org/another']
    if anchor is not None:
        fixture.config['environment']['repository'] = anchor
    save(fixture)
    with pytest.raises(PoolError, match='ELIGIBILITY_REPOSITORY_UNPROVEN'):
        observe(tmp_path, contract)


def test_protected_peer_lifecycle_is_only_for_its_anchor_and_keeps_snapshot_provenance(tmp_path, contract):
    fixture = peer(tmp_path, contract)
    repository = fixture.config['consumer'].pop('repository')
    another = 'example-org/another'
    fixture.config['consumer']['repositories'] = [repository, another]
    fixture.config['environment']['repository'] = another
    installed_lifecycle(fixture.config, another)
    save(fixture)
    observed = observe(tmp_path, contract)
    assert len(observed[repository]) == 2
    assert observed[another][-1] == lifecycle_ref(another)
    fixture.config['consumer']['generalRunnerPool']['desiredCapacity'] = 3
    write_json(fixture.snapshot, fixture.config, 0o600)  # No matching protected digest.
    with pytest.raises(PoolError, match='ELIGIBILITY_SNAPSHOT_BINDING_UNPROVEN'):
        observe(tmp_path, contract)


@pytest.mark.parametrize('bad', ['source-repository', 'source-revision', 'base-branch',
                               'routing-path', 'recovery-path', 'validation-path'])
def test_protected_lifecycle_requires_self_source_and_distinct_fixed_workflow(tmp_path, contract, bad):
    fixture = peer(tmp_path, contract)
    repository = fixture.config['consumer']['repository']
    installed_lifecycle(fixture.config, repository)
    if bad == 'source-repository':
        fixture.config['source']['repository'] = 'https://github.com/example-org/foreign.git'
    elif bad == 'source-revision':
        fixture.config['source']['revision'] = 'candidate'
    elif bad == 'base-branch':
        fixture.config['consumer']['baseBranch'] = 'candidate'
    else:
        key = {'routing-path': 'routingWorkflow', 'recovery-path': 'recoveryWorkflow',
               'validation-path': 'validationWorkflow'}[bad]
        fixture.config['consumer'][key] = '.github/workflows/manual-main-production-deploy.yml'
    save(fixture)
    with pytest.raises(PoolError, match='ELIGIBILITY_'):
        observe(tmp_path, contract)


def test_prospective_current_namespace_overrides_old_or_broken_installed_snapshot(tmp_path, contract):
    fixture = peer(tmp_path, contract, contract['namespace'], contract['repository'])
    fixture.snapshot.write_text('old and malformed snapshot')
    assert observe(tmp_path, contract) == {contract['repository']: contract['workflowRefs']}


def test_other_pool_does_not_impose_its_manifest_or_profile_on_this_pool(tmp_path, contract):
    fixture = peer(tmp_path, contract)
    fixture.config['environment']['generalRunner']['name'] = 'another-pool'
    fixture.config['environment']['generalRunner']['user'] = 'unrelated-user'
    save(fixture)
    fixture.manifest.unlink()
    assert observe(tmp_path, contract) == {contract['repository']: contract['workflowRefs']}


@pytest.mark.parametrize('field', ['user', 'group', 'scope', 'appId', 'installationId', 'organization'])
def test_matching_pool_name_cannot_supply_conflicting_profile(tmp_path, contract, field):
    fixture = peer(tmp_path, contract)
    general = fixture.config['environment']['generalRunner']
    if field in ['appId', 'installationId']:
        general['poolApp'][field] = '999'
    elif field == 'organization':
        fixture.config['consumer']['repository'] = 'another-org/peer'
    else:
        general[field] = 'repository' if field == 'scope' else 'other-value'
    save(fixture)
    with pytest.raises(PoolError, match='ELIGIBILITY_PROFILE_CONFLICT'):
        observe(tmp_path, contract)


@pytest.mark.parametrize('field', ['namespace', 'repository', 'baseBranch', 'routingWorkflow',
                                 'recoveryWorkflow', 'validationWorkflow', 'desiredCapacity'])
def test_matching_snapshot_requires_relevant_profile_and_ref_syntax(tmp_path, contract, field):
    fixture = peer(tmp_path, contract)
    if field == 'namespace':
        fixture.config['environment']['namespace'] = 'another-namespace'
    elif field == 'desiredCapacity':
        fixture.config['consumer']['generalRunnerPool']['desiredCapacity'] = True
    else:
        fixture.config['consumer'][field] = '../untrusted'
    save(fixture)
    with pytest.raises(PoolError, match='ELIGIBILITY_'):
        observe(tmp_path, contract)


@pytest.mark.parametrize('name,field', [('manifest', 'commit'), ('manifest', 'resolvedRevision'),
                                     ('manifest', 'installedRevision'), ('manifest', 'consumerRevision'),
                                     ('manifest', 'deploymentConfigSha256'), ('manifest', 'gitTree'),
                                     ('identity', 'revision'), ('identity', 'tree')])
def test_matching_peer_requires_revision_and_digest_binding(tmp_path, contract, name, field):
    fixture = peer(tmp_path, contract)
    path = getattr(fixture, name)
    value = json.loads(path.read_bytes())
    value[field] = 'invalid' if field == 'consumerRevision' else 'c' * 40
    write_json(path, value, 0o600)
    with pytest.raises(PoolError, match='ELIGIBILITY_SNAPSHOT_BINDING_UNPROVEN'):
        observe(tmp_path, contract)


@pytest.mark.parametrize('name', ['manifest', 'identity'])
def test_matched_peer_rejects_symlinked_identity_or_manifest(tmp_path, contract, name):
    fixture = peer(tmp_path, contract)
    path = getattr(fixture, name)
    target = path.with_name(path.name + '-other')
    path.rename(target)
    path.symlink_to(target.name)
    with pytest.raises(PoolError, match='ELIGIBILITY_SNAPSHOT_UNPROVEN'):
        observe(tmp_path, contract)


@pytest.mark.parametrize('damage', ['snapshot-symlink', 'snapshot-hardlink', 'snapshot-mode',
                                  'namespace-mode', 'namespace-symlink', 'release-parent-symlink',
                                  'current-traversal', 'current-foreign', 'current-regular'])
def test_unsafe_or_unbound_path_never_supplies_peer_eligibility(tmp_path, contract, damage):
    fixture = peer(tmp_path, contract)
    if damage in ['snapshot-symlink', 'snapshot-hardlink']:
        target = fixture.snapshot.with_name('other-config.json')
        if damage == 'snapshot-symlink':
            fixture.snapshot.rename(target)
            fixture.snapshot.symlink_to(target.name)
        else:
            os.link(fixture.snapshot, target)
    elif damage == 'snapshot-mode':
        fixture.snapshot.chmod(0o644)
    elif damage == 'namespace-mode':
        fixture.install.chmod(0o777)
    elif damage in ['namespace-symlink', 'release-parent-symlink']:
        path = fixture.install if damage == 'namespace-symlink' else fixture.install / 'releases'
        target = path.with_name(path.name + '-other')
        path.rename(target)
        path.symlink_to(target.name)
    else:
        fixture.current.unlink()
        if damage == 'current-regular':
            fixture.current.write_text('not a protected current symlink')
        else:
            fixture.current.symlink_to('releases/../releases/' + HEAD if damage == 'current-traversal'
                                       else '/opt/another-relay/releases/' + HEAD)
    assert observe(tmp_path, contract) == {contract['repository']: contract['workflowRefs']}


@pytest.mark.skipif(os.getuid() != 0 if hasattr(os, 'getuid') else True,
                    reason='native root ownership mutation fixture')
@pytest.mark.parametrize('name', ['snapshot', 'install', 'manifest', 'identity', 'snapshot-group'])
def test_foreign_peer_ownership_cannot_supply_eligibility(tmp_path, contract, name):
    fixture = peer(tmp_path, contract)
    path = fixture.snapshot if name == 'snapshot-group' else getattr(fixture, name)
    os.chown(path, 0 if name == 'snapshot-group' else 65534, 65534)
    if name in ['snapshot', 'install', 'snapshot-group']:
        assert observe(tmp_path, contract) == {contract['repository']: contract['workflowRefs']}
    else:
        with pytest.raises(PoolError, match='ELIGIBILITY_FILE_UNSAFE'):
            observe(tmp_path, contract)


def test_protected_duplicate_repository_cannot_union_conflicting_refs(tmp_path, contract):
    peer(tmp_path, contract)
    other = peer(tmp_path, contract, 'another-relay')
    other.config['consumer']['baseBranch'] = 'candidate'
    save(other)
    with pytest.raises(PoolError, match='ELIGIBILITY_REPOSITORY_AMBIGUOUS'):
        observe(tmp_path, contract)


def test_consistent_duplicate_repository_does_not_need_another_registry(tmp_path, contract):
    first = peer(tmp_path, contract)
    peer(tmp_path, contract, 'another-relay')
    assert observe(tmp_path, contract)[first.config['consumer']['repository']] == refs(first.config)


@pytest.mark.parametrize('anchor_first', [True, False])
def test_duplicate_peer_pair_preserves_proven_optional_lifecycle_in_either_discovery_order(
        tmp_path, contract, anchor_first):
    first = peer(tmp_path, contract, 'a-peer' if anchor_first else 'z-peer')
    installed_lifecycle(first.config, first.config['consumer']['repository'])
    save(first)
    second = peer(tmp_path, contract, 'z-peer' if anchor_first else 'a-peer')
    second.config['consumer']['baseBranch'] = 'main'
    repository = second.config['consumer'].pop('repository')
    second.config['consumer']['repositories'] = [repository, 'example-org/other']
    second.config['environment']['repository'] = 'example-org/other'
    save(second)
    assert observe(tmp_path, contract)[repository] == refs(first.config) + [lifecycle_ref(repository)]


def test_peer_namespace_cannot_replace_prospective_repository_refs(tmp_path, contract):
    peer(tmp_path, contract, repository=contract['repository'])
    with pytest.raises(PoolError, match='ELIGIBILITY_REPOSITORY_AMBIGUOUS'):
        observe(tmp_path, contract)


def test_discovery_limit_is_explicit_instead_of_returning_a_partial_map(tmp_path, contract, monkeypatch):
    peer(tmp_path, contract)
    (tmp_path / 'opt' / 'unrelated').mkdir()
    monkeypatch.setattr(eligibility, 'MAX_DISCOVERY', 1)
    with pytest.raises(PoolError, match='ELIGIBILITY_DISCOVERY_INCOMPLETE'):
        observe(tmp_path, contract)


def test_snapshot_size_is_bounded_before_parsing_or_following_config_data(tmp_path, contract, monkeypatch):
    peer(tmp_path, contract)
    monkeypatch.setattr(eligibility, 'MAX_SNAPSHOT', 10)
    assert observe(tmp_path, contract) == {contract['repository']: contract['workflowRefs']}


def test_current_prospective_contract_cannot_supply_foreign_workflow_claims(tmp_path, contract):
    bad = copy.deepcopy(contract)
    bad['workflowRefs'][0] = 'example-org/foreign/.github/workflows/routing.yml@refs/heads/main'
    with pytest.raises(PoolError, match='ELIGIBILITY_CONTRACT_INVALID'):
        observe(tmp_path, bad)


@pytest.mark.parametrize('name', ['snapshot', 'manifest', 'identity'])
def test_peer_evidence_is_rechecked_after_reading_all_snapshot_bytes(tmp_path, contract, monkeypatch, name):
    fixture = peer(tmp_path, contract)
    decode = eligibility._json
    calls = 0

    def change_after_final_read(raw):
        nonlocal calls
        value = decode(raw)
        calls += 1
        if calls == 3:
            path = getattr(fixture, name)
            path.write_bytes(path.read_bytes() + b' ')
        return value

    monkeypatch.setattr(eligibility, '_json', change_after_final_read)
    with pytest.raises(PoolError, match='ELIGIBILITY_FILE_CHANGED'):
        observe(tmp_path, contract)


def test_current_binding_is_rechecked_before_peer_becomes_eligible(tmp_path, contract, monkeypatch):
    fixture = peer(tmp_path, contract)
    decode = eligibility._json
    calls = 0

    def change_after_final_read(raw):
        nonlocal calls
        value = decode(raw)
        calls += 1
        if calls == 3:
            fixture.current.unlink()
            fixture.current.symlink_to('/opt/peer-relay/releases/' + 'd' * 40)
        return value

    monkeypatch.setattr(eligibility, '_json', change_after_final_read)
    with pytest.raises(PoolError, match='ELIGIBILITY_CURRENT_CHANGED'):
        observe(tmp_path, contract)


@pytest.mark.parametrize('name,field', [('manifest', 'gitTree'), ('identity', 'tree')])
@pytest.mark.parametrize('replacement', [None, 'invalid', 'e' * 39])
def test_peer_tree_proof_must_be_present_valid_and_consistent(tmp_path, contract, name, field, replacement):
    fixture = peer(tmp_path, contract)
    path = getattr(fixture, name)
    value = json.loads(path.read_bytes())
    if replacement is None:
        value.pop(field)
    else:
        value[field] = replacement
    write_json(path, value, 0o600)
    with pytest.raises(PoolError, match='ELIGIBILITY_SNAPSHOT_BINDING_UNPROVEN'):
        observe(tmp_path, contract)


def native_group(tmp_path, contract):
    first = peer(tmp_path, contract)
    second = peer(tmp_path, contract, 'another-relay', 'example-org/another')
    eligible = observe(tmp_path, contract)
    selected = [contract['repository'], first.config['consumer']['repository']]
    group = {'id': 7, 'name': contract['group'], 'visibility': 'selected',
             'restricted_to_workflows': True,
             'selected_workflows': [ref for repository in selected for ref in eligible[repository]]}
    calls = []
    github = GitHub('synthetic-token-never-transmitted', contract['organization'])
    base = '/orgs/' + contract['organization'] + '/actions/runner-groups'

    def request(method, path, body=None):
        calls.append((method, path, body))
        if path.startswith(base + '?'):
            return {'total_count': 1, 'runner_groups': [copy.deepcopy(group)]}
        if path == base + '/7':
            return copy.deepcopy(group)
        if path.startswith(base + '/7/repositories?'):
            return {'total_count': len(selected),
                    'repositories': [{'full_name': repository} for repository in selected]}
        raise AssertionError('unexpected API request')

    github.request = request
    return SimpleNamespace(first=first, second=second, eligible=eligible, selected=selected,
                           group=group, calls=calls, github=github)


def test_native_protected_two_repository_map_qualifies_without_acl_mutation(tmp_path, contract):
    fixture = native_group(tmp_path, contract)
    assert fixture.github.qualify(contract, fixture.eligible) == 7
    assert len(fixture.calls) == 3
    assert all(method == 'GET' and body is None for method, _, body in fixture.calls)


@pytest.mark.parametrize('active_count', [1, 2])
@pytest.mark.parametrize('select_inactive', [False, True])
def test_configured_repositories_need_not_be_active_or_have_workflow_files(
        tmp_path, contract, active_count, select_inactive):
    repository = contract['repository']
    targets = [repository, 'example-org/configured', 'example-org/inactive']
    contract['repositories'] = targets
    contract['workflowRefsByRepository'] = {
        target: [ref.replace(repository, target) for ref in contract['workflowRefs']]
        for target in targets}
    fixture = native_group(tmp_path, contract)
    fixture.selected[:] = targets[:active_count] + (targets[active_count:] if select_inactive else [])
    fixture.group['selected_workflows'] = [
        ref for target in targets[:active_count] for ref in fixture.eligible[target]]
    assert not list(tmp_path.rglob('*.yml')) and not list(tmp_path.rglob('*.yaml'))
    assert fixture.github.qualify(contract, fixture.eligible) == 7
    assert all(method == 'GET' and body is None for method, _, body in fixture.calls)


@pytest.mark.parametrize('active', ['lifecycle-only', 'automatic-only', 'both'])
def test_native_lifecycle_is_optional_and_does_not_require_automatic_adoption(tmp_path, contract, active):
    lifecycle = (contract['repository']
        + '/.github/workflows/manual-main-production-deploy.yml@refs/heads/main')
    contract['workflowRefs'].append(lifecycle)
    fixture = native_group(tmp_path, contract)
    fixture.group['selected_workflows'] = ([lifecycle] if active == 'lifecycle-only' else
                                           contract['workflowRefs'][:2] if active == 'automatic-only' else
                                           contract['workflowRefs'][:])
    assert fixture.github.qualify(contract, fixture.eligible) == 7
    assert all(method == 'GET' and body is None for method, _, body in fixture.calls)


@pytest.mark.parametrize('bad', ['candidate', 'tag', 'repository', 'path', 'unselected'])
def test_native_lifecycle_denies_every_ref_outside_the_trusted_selected_anchor(tmp_path, contract, bad):
    repository = contract['repository']
    lifecycle = lifecycle_ref(repository)
    contract['workflowRefs'].append(lifecycle)
    fixture = native_group(tmp_path, contract)
    if bad == 'candidate':
        lifecycle = lifecycle.replace('@refs/heads/main', '@refs/heads/candidate')
    elif bad == 'tag':
        lifecycle = lifecycle.replace('@refs/heads/', '@refs/tags/')
    elif bad == 'repository':
        lifecycle = lifecycle.replace(repository, fixture.first.config['consumer']['repository'])
    elif bad == 'path':
        lifecycle = lifecycle.replace('manual-main-production-deploy', 'unknown')
    else:
        fixture.selected.remove(repository)
    fixture.group['selected_workflows'] = [lifecycle]
    with pytest.raises(PoolError, match='GROUP_'):
        fixture.github.qualify(contract, fixture.eligible)
    assert all(method == 'GET' and body is None for method, _, body in fixture.calls)


@pytest.mark.parametrize('bad', ['unknown-repository', 'foreign-candidate', 'foreign-tag',
                               'foreign-validation', 'unselected-repository-workflow', 'missing-recovery',
                               'missing-routing', 'empty-workflows', 'empty-repositories',
                               'organization-wide', 'default-group', 'unrestricted',
                               'unknown-third', 'non-anchor-lifecycle'])
def test_native_group_rejects_every_untrusted_repository_or_workflow_without_acl_mutation(tmp_path, contract, bad):
    fixture = native_group(tmp_path, contract)
    workflows = fixture.group['selected_workflows']
    first_refs = refs(fixture.first.config)
    if bad == 'unknown-repository':
        fixture.selected.append('example-org/unknown')
    elif bad == 'foreign-candidate':
        workflows.append(first_refs[0].replace('@refs/heads/trusted/base', '@refs/heads/candidate'))
    elif bad == 'foreign-tag':
        workflows.append(first_refs[0].replace('@refs/heads/trusted/base', '@refs/tags/main'))
    elif bad == 'foreign-validation':
        workflows.append(first_refs[0].replace('peer-routing.yaml', 'validation.yaml'))
    elif bad == 'unselected-repository-workflow':
        workflows.append(refs(fixture.second.config)[0])
    elif bad == 'missing-recovery':
        workflows.remove(first_refs[1])
    elif bad == 'missing-routing':
        workflows.remove(first_refs[0])
    elif bad == 'empty-workflows':
        workflows.clear()
    elif bad == 'empty-repositories':
        fixture.selected.clear()
    elif bad == 'organization-wide':
        fixture.group['visibility'] = 'all'
    elif bad == 'default-group':
        fixture.group['name'] = 'Default'
    elif bad == 'unrestricted':
        fixture.group['restricted_to_workflows'] = False
    elif bad == 'unknown-third':
        workflows.append(first_refs[0].replace('peer-routing.yaml', 'unknown.yaml'))
    else:
        workflows.append(contract['repository']
            + '/.github/workflows/manual-main-production-deploy.yml@refs/heads/main')
    with pytest.raises(PoolError, match='GROUP_'):
        fixture.github.qualify(contract, fixture.eligible)
    assert fixture.calls
    assert all(method == 'GET' and body is None for method, _, body in fixture.calls)
