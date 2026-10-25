"""Read protected peer snapshots; never import or execute another installation.

The prospective owner contract supplies this namespace's authority. Peers are
discovered from the existing fixed installed layout, without an eligibility
registry or trust in workflow strings retained in pool mutation state.
"""
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from managed_pool import LIFECYCLE_WORKFLOW, PoolError, require


MAX_DISCOVERY = 1024
MAX_SNAPSHOT = 262144
NAMESPACE = re.compile(r'[a-z][a-z0-9-]{0,30}')
REVISION = re.compile(r'[0-9a-f]{40}')
WORKFLOW = re.compile(r'\.github/workflows/[A-Za-z0-9_-]+\.ya?ml')


def _stamp(info):
    return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _directory(info, owner_uid):
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == owner_uid
            and not info.st_mode & 0o022, 'ELIGIBILITY_PARENT_UNSAFE')


def _open_directory(parent, name, owner_uid, stack, checks):
    descriptor = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                         dir_fd=parent)
    stack.callback(os.close, descriptor)
    info = os.fstat(descriptor)
    _directory(info, owner_uid)
    checks.append((parent, name, descriptor, info))
    return descriptor


def _read(parent, name, modes, owner_uid, *, private=False):
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=parent)
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_uid == owner_uid
                and info.st_nlink == 1 and stat.S_IMODE(info.st_mode) in modes
                and (not private or owner_uid != 0 or info.st_gid == 0),
                'ELIGIBILITY_FILE_UNSAFE')
        require(0 < info.st_size <= MAX_SNAPSHOT, 'ELIGIBILITY_FILE_SIZE')
        raw = stream.read(MAX_SNAPSHOT + 1)
        require(0 < len(raw) <= MAX_SNAPSHOT
                and _stamp(info) == _stamp(os.fstat(stream.fileno()))
                and _stamp(info) == _stamp(os.stat(name, dir_fd=parent, follow_symlinks=False)),
                'ELIGIBILITY_FILE_CHANGED')
    return raw, _stamp(info)


def _json(raw):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, 'ELIGIBILITY_JSON_INVALID')
            value[key] = item
        return value

    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=unique)
        require(isinstance(value, dict), 'ELIGIBILITY_JSON_INVALID')
        return value
    except (UnicodeError, ValueError, RecursionError):
        raise PoolError('MANAGED_POOL_ELIGIBILITY_JSON_INVALID') from None


def _repository(value):
    if not isinstance(value, str) or len(value) > 140:
        return False
    parts = value.split('/')
    return (len(parts) == 2
            and re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?', parts[0]) is not None
            and '--' not in parts[0]
            and re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', parts[1]) is not None
            and parts[1] not in ['.', '..'])


def _branch(value):
    return (isinstance(value, str)
            and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]{0,239}', value) is not None
            and '..' not in value and not value.endswith('.')
            and all(part and not part.startswith('.') and not part.endswith('.lock')
                    for part in value.split('/')))


def _peer_refs(config, namespace, contract):
    """None denotes another pool; matching claims must prove their profile."""
    environment, consumer = config.get('environment'), config.get('consumer')
    if not isinstance(environment, dict) or not isinstance(consumer, dict):
        return None
    general = environment.get('generalRunner')
    if (not isinstance(general, dict) or general.get('name') != contract['name']
            or 'generalRunnerPool' not in consumer):
        return None
    pool, app = consumer['generalRunnerPool'], general.get('poolApp')
    require(type(config.get('schemaVersion')) is int and config['schemaVersion'] == 1
            and type(consumer.get('version')) is int and consumer['version'] == 1
            and environment.get('namespace') == namespace
            and isinstance(pool, dict) and set(pool) == {'desiredCapacity'}
            and type(pool['desiredCapacity']) is int and 1 <= pool['desiredCapacity'] <= 32
            and isinstance(app, dict), 'ELIGIBILITY_PROFILE_UNPROVEN')
    repositories = consumer.get('repositories', [consumer.get('repository')])
    require(isinstance(repositories, list) and bool(repositories)
            and all(_repository(value) for value in repositories)
            and len(set(repositories)) == len(repositories)
            and not ('repository' in consumer and 'repositories' in consumer),
            'ELIGIBILITY_REPOSITORY_UNPROVEN')
    require(general.get('scope') == 'organization'
            and general.get('user') == contract['runnerUser']
            and general.get('group') == contract['group']
            and all(repository.split('/')[0] == contract['organization'] for repository in repositories)
            and app.get('appId') == contract['appId']
            and app.get('installationId') == contract['installationId'],
            'ELIGIBILITY_PROFILE_CONFLICT')
    branch = consumer.get('baseBranch')
    workflows = [consumer.get(key) for key in
                 ['routingWorkflow', 'recoveryWorkflow', 'validationWorkflow']]
    require(_branch(branch) and all(isinstance(value, str) and WORKFLOW.fullmatch(value)
                                   for value in workflows)
            and len(set(workflows)) == 3, 'ELIGIBILITY_WORKFLOWS_UNPROVEN')
    anchor = environment.get('repository', consumer.get('repository'))
    require(isinstance(anchor, str) and anchor in repositories, 'ELIGIBILITY_REPOSITORY_UNPROVEN')
    result = {repository: [repository + '/' + workflow + '@refs/heads/' + branch
                           for workflow in workflows[:2]] for repository in repositories}
    local_apply = environment.get('localApply')
    if isinstance(local_apply, dict) and local_apply.get('source') == 'installed':
        source = config.get('source')
        require(set(local_apply) == {'source'} and isinstance(source, dict)
                and isinstance(source.get('repository'), str), 'ELIGIBILITY_WORKFLOWS_UNPROVEN')
        source_repository = source['repository'].removeprefix('https://github.com/').removeprefix(
            'git@github.com:').removesuffix('.git')
        require(source_repository == anchor and source.get('revision', 'main') == 'main'
                and branch == 'main' and LIFECYCLE_WORKFLOW not in workflows,
                'ELIGIBILITY_WORKFLOWS_UNPROVEN')
        result[anchor].append(anchor + '/' + LIFECYCLE_WORKFLOW + '@refs/heads/' + branch)
    elif isinstance(local_apply, dict) and local_apply.get('source') == 'git':
        deployment = local_apply.get('repository')
        require(set(local_apply) == {'source', 'repository', 'configPath'}
                and _repository(deployment) and deployment not in repositories
                and deployment.split('/')[0] == contract['organization'] and branch == 'main'
                and isinstance(local_apply.get('configPath'), str)
                and re.fullmatch(r'[A-Za-z0-9_./-]+\.json', local_apply['configPath'])
                and all(part not in ['', '.', '..'] for part in local_apply['configPath'].split('/')),
                'ELIGIBILITY_WORKFLOWS_UNPROVEN')
        result[deployment] = [deployment + '/' + LIFECYCLE_WORKFLOW + '@refs/heads/main']
    return result


def _peer(opt, namespace, contract, owner_uid):
    """Unproven paths provide no eligibility, without reading unsafe objects."""
    with ExitStack() as stack:
        checks = []
        try:
            install = _open_directory(opt, namespace, owner_uid, stack, checks)
            current = os.stat('current', dir_fd=install, follow_symlinks=False)
            require(stat.S_ISLNK(current.st_mode) and current.st_uid == owner_uid,
                    'ELIGIBILITY_CURRENT_UNSAFE')
            link = os.readlink('current', dir_fd=install)
            match = re.fullmatch('(?:/opt/' + re.escape(namespace) + r'/)?releases/([0-9a-f]{40})', link)
            require(match is not None, 'ELIGIBILITY_CURRENT_UNPROVEN')
            revision = match[1]
            releases = _open_directory(install, 'releases', owner_uid, stack, checks)
            release = _open_directory(releases, revision, owner_uid, stack, checks)
            config_raw, config_stamp = _read(release, 'deployment-config.json', {0o600},
                                             owner_uid, private=True)
            config = _json(config_raw)
        except (OSError, PoolError):
            # Nothing from an unreadable or unprotected snapshot can establish
            # eligibility. The ACL check still requires every selected repo to
            # have an independently verified entry in the returned map.
            return None
        result = _peer_refs(config, namespace, contract)
        if result is None:
            return None
        try:
            source = _open_directory(release, 'reviewed-source', owner_uid, stack, checks)
            source_raw, source_stamp = _read(source, '.relay-source.json', {0o644, 0o640, 0o600}, owner_uid)
            manifest_raw, manifest_stamp = _read(release, 'artifact-manifest.json', {0o640, 0o600}, owner_uid)
            identity, manifest = _json(source_raw), _json(manifest_raw)
            require(identity.get('revision') == revision
                    and isinstance(manifest.get('gitTree'), str)
                    and REVISION.fullmatch(manifest['gitTree'])
                    and identity.get('tree') == manifest['gitTree']
                    and all(manifest.get(key) == revision for key in
                            ['commit', 'resolvedRevision', 'installedRevision'])
                    and isinstance(manifest.get('consumerRevision'), str)
                    and REVISION.fullmatch(manifest['consumerRevision'])
                    and manifest.get('deploymentConfigSha256') == hashlib.sha256(config_raw).hexdigest(),
                    'ELIGIBILITY_SNAPSHOT_BINDING_UNPROVEN')
            require(_stamp(os.stat('current', dir_fd=install, follow_symlinks=False)) == _stamp(current)
                    and os.readlink('current', dir_fd=install) == link, 'ELIGIBILITY_CURRENT_CHANGED')
            for parent, name, expected in [(release, 'deployment-config.json', config_stamp),
                                           (source, '.relay-source.json', source_stamp),
                                           (release, 'artifact-manifest.json', manifest_stamp)]:
                require(_stamp(os.stat(name, dir_fd=parent, follow_symlinks=False)) == expected,
                        'ELIGIBILITY_FILE_CHANGED')
            for parent, name, descriptor, expected in checks:
                actual = os.stat(name, dir_fd=parent, follow_symlinks=False)
                _directory(actual, owner_uid)
                require((actual.st_dev, actual.st_ino) == (expected.st_dev, expected.st_ino)
                        and (actual.st_dev, actual.st_ino) ==
                        (os.fstat(descriptor).st_dev, os.fstat(descriptor).st_ino),
                        'ELIGIBILITY_PARENT_CHANGED')
        except OSError:
            raise PoolError('MANAGED_POOL_ELIGIBILITY_SNAPSHOT_UNPROVEN') from None
        return result


def eligible_workflows(contract, *, root=Path('/'), owner_uid=0):
    """Map configured candidates to permitted refs, without requiring adoption.

    The caller must compare *every* native selected repository/workflow with
    this map. Discovery alone grants no access and performs no mutation.
    ``root`` and ``owner_uid`` support native filesystem fixtures; production
    callers keep the fixed default root and root ownership.
    """
    require(NAMESPACE.fullmatch(contract['namespace']) is not None
            and _repository(contract['repository']), 'ELIGIBILITY_CONTRACT_INVALID')
    targets = contract.get('repositories', [contract['repository']])
    result = contract.get('workflowRefsByRepository', {contract['repository']: contract['workflowRefs']})
    deployment = contract.get('deploymentRepository')
    expected = set(targets) | ({deployment} if isinstance(deployment, str) else set())
    require(isinstance(targets, list) and targets and set(result) == expected
            and (deployment is None or _repository(deployment) and deployment not in targets)
            and contract['repository'] in result, 'ELIGIBILITY_CONTRACT_INVALID')
    for repository, refs in result.items():
        require(_repository(repository) and repository.split('/')[0] == contract['organization']
                and isinstance(refs, list) and len(refs) in ([1] if repository == deployment else [2, 3])
                and all(isinstance(value, str) for value in refs) and len(set(refs)) == len(refs),
                'ELIGIBILITY_CONTRACT_INVALID')
        branches = []
        for value in refs:
            prefix = repository + '/'
            require(value.startswith(prefix) and '@refs/heads/' in value,
                    'ELIGIBILITY_CONTRACT_INVALID')
            workflow, branch = value[len(prefix):].rsplit('@refs/heads/', 1)
            require(WORKFLOW.fullmatch(workflow) and _branch(branch), 'ELIGIBILITY_CONTRACT_INVALID')
            branches.append(branch)
        require(len(set(branches)) == 1, 'ELIGIBILITY_CONTRACT_INVALID')
        if repository == deployment:
            require(refs == [repository + '/' + LIFECYCLE_WORKFLOW + '@refs/heads/main'],
                    'ELIGIBILITY_CONTRACT_INVALID')
        if len(refs) == 3:
            require(repository == contract['repository']
                    and refs[2] == repository + '/' + LIFECYCLE_WORKFLOW + '@refs/heads/' + branches[0],
                    'ELIGIBILITY_CONTRACT_INVALID')
    result = {repository: refs[:] for repository, refs in result.items()}
    with ExitStack() as stack:
        descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        stack.callback(os.close, descriptor)
        _directory(os.fstat(descriptor), owner_uid)
        try:
            opt = os.open('opt', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
        except FileNotFoundError:
            return result
        stack.callback(os.close, opt)
        _directory(os.fstat(opt), owner_uid)
        names = []
        with os.scandir(opt) as entries:
            for entry in entries:
                require(len(names) < MAX_DISCOVERY, 'ELIGIBILITY_DISCOVERY_INCOMPLETE')
                names.append(entry.name)
        for namespace in sorted(names):
            if namespace == contract['namespace'] or NAMESPACE.fullmatch(namespace) is None:
                continue
            peer = _peer(opt, namespace, contract, owner_uid)
            if peer is None:
                continue
            for repository, workflows in peer.items():
                require(repository not in result or set(result[repository][:2]) == set(workflows[:2]),
                        'ELIGIBILITY_REPOSITORY_AMBIGUOUS')
                if repository in result and len(result[repository]) == 3:
                    workflows = result[repository]
                result[repository] = workflows
    return result
