"""Project accepted Relay workflow source into a consumer's reviewed Git tree.

The public deployment entrypoint validates the selected clean source and exact
revision before calling this module. Rendering never resolves a moving ref or
fetches anything. The manifest is a drift baseline, not acceptance authority.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import stat
import tempfile

from config import require, unique_object, execution_slot_label, general_pool_label, deployment_repository


MANIFEST = '.github/relay-workflows.json'
PRODUCTION = '.github/workflows/manual-main-production-deploy.yml'
WORKFLOW = re.compile(r'\.github/workflows/[A-Za-z0-9_-]+\.ya?ml')
REVISION = re.compile(r'[0-9a-f]{40}')
DIGEST = re.compile(r'[0-9a-f]{64}')
MAX_BYTES = 65536


def contract(source_root, parallel=False):
    value = json.loads(_read(Path(source_root) / 'deploy/workflows/contract.json'),
                       object_pairs_hook=unique_object)
    require(isinstance(value, dict) and set(value) in [{'workflowContract'}, {'workflowContract', 'parallelWorkflowContract'}]
            and all(isinstance(item, str) and re.fullmatch(r'relay-workflows-v[1-9][0-9]*', item)
                    for item in value.values()),
            'workflow-contract')
    key = 'parallelWorkflowContract' if parallel else 'workflowContract'
    require(key in value, 'parallel-workflow-contract-required')
    return value[key]


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def _json(value):
    return json.dumps(value, sort_keys=True, indent=2).encode() + b'\n'


def _directory(path):
    metadata = path.lstat()
    require(stat.S_ISDIR(metadata.st_mode), 'workflow-directory:' + str(path))


def _read(path):
    # Do not follow a file swapped for a symlink between inspection and read.
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as stream:
        metadata = os.fstat(stream.fileno())
        require(stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1
                and metadata.st_size <= MAX_BYTES and not metadata.st_mode & 0o111,
                'workflow-regular-file:' + str(path))
        content = stream.read(MAX_BYTES + 1)
        def stamp(info):
            return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode,
                    info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        require(len(content) <= MAX_BYTES and stamp(os.fstat(stream.fileno())) == stamp(metadata)
                and stamp(path.lstat()) == stamp(metadata), 'workflow-file-changed:' + str(path))
        return content


def _path(root, relative):
    require(relative == MANIFEST or WORKFLOW.fullmatch(relative), 'workflow-path')
    path = root / relative
    _directory(root)
    for parent in reversed(path.parents):
        if parent != root and root in parent.parents and parent.exists():
            _directory(parent)
        elif parent != root and root in parent.parents and parent.is_symlink():
            require(False, 'workflow-directory:' + str(parent))
    return path


def render(config, revision, source_root, repository=None, *, deployment=False):
    """Return deterministic managed bytes; config must have passed config.load."""
    require(isinstance(revision, str) and REVISION.fullmatch(revision), 'workflow-exact-revision')
    source_root = Path(source_root)
    consumer, environment = config['consumer'], config['environment']
    if deployment:
        require(environment['localApply'].get('source') == 'git' and repository is None,
                'deployment-workflow-source')
        repository = environment['localApply']['repository']
    else:
        repository = deployment_repository(config, repository)
    general, production = environment['generalRunner'], environment['runner']
    slots = consumer.get('executionSlots')
    managed_pool = consumer.get('generalRunnerPool')
    labels = ['self-hosted', 'Linux', 'X64', *production['labels']]
    general_labels = (['self-hosted', 'Linux', 'X64', general_pool_label(config)]
                      if managed_pool else labels)
    general_runs_on = ({'group': general['group'], 'labels': general_labels}
                       if general.get('scope', 'repository') == 'organization' else general_labels)
    values = {
        'WORKFLOW_CONTRACT': contract(source_root, bool(slots)),
        'REPOSITORY': repository, 'OWNER': consumer['owner'],
        'BASE_BRANCH': consumer['baseBranch'],
        'BASE_BRANCH_YAML': json.dumps(consumer['baseBranch']),
        'NAMESPACE': environment['namespace'],
        'CONTROL_GROUP_YAML': json.dumps(environment['namespace'] + '-control'),
        'RECOVERY_GROUP_YAML': json.dumps(environment['namespace'] + '-control'),
        'PRODUCTION_GROUP_YAML': json.dumps(environment['namespace'] + '-production'),
        'GENERAL_RUNS_ON_YAML': json.dumps(general_runs_on),
        'RECOVERY_RUNS_ON_YAML': json.dumps(general_runs_on),
        'RECOVERY_SLOT_INPUT': '',
        'RECOVERY_SLOT_ENV': '',
        'PRODUCTION_RUNS_ON_YAML': json.dumps({'group': production['group'], 'labels': labels}),
        'GENERAL_RUNNER_NAME': shlex.quote(general['name']),
        'GENERAL_RUNNER_USER': shlex.quote(general['user']),
        'GENERAL_RUNNER_GUARD': 'test "$RUNNER_NAME" = ' + shlex.quote(general['name']) + '\n'
                                '          test "$(/usr/bin/id -un)" = ' + shlex.quote(general['user']),
        'RECOVERY_RUNNER_GUARD': 'test "$RUNNER_NAME" = ' + shlex.quote(general['name']) + '\n'
                                 '          test "$(/usr/bin/id -un)" = ' + shlex.quote(general['user']),
        'PRODUCTION_RUNNER_NAME': shlex.quote(production['name']),
        'PRODUCTION_RUNNER_USER': shlex.quote(production['user']),
    }
    if slots:
        # Native groups are repository-local. The configured finite runner pool
        # bounds active controllers. Independent owner commands for the same
        # Task may overlap; trusted admission owns physical resource conflicts
        # and Writer owns exact publication targets and event deduplication.
        values['CONTROL_GROUP_YAML'] = json.dumps(environment['namespace'] + '-control-${{ github.run_id }}')
        values['RECOVERY_GROUP_YAML'] = json.dumps(environment['namespace'] + '-recovery-${{ inputs.run_id }}')
        lines = ['case "$RUNNER_NAME:$(/usr/bin/id -un)" in']
        lines.extend('            ' + shlex.quote(slot['runnerName'] + ':' + slot['runnerUser'])
                     + ') export RELAY_EXECUTION_SLOT=' + shlex.quote(slot['id']) + ' ;;' for slot in slots)
        lines.extend(['            *) echo RELAY_RUNNER_SLOT_IDENTITY_MISMATCH >&2; exit 1 ;;', '          esac'])
        values['GENERAL_RUNNER_GUARD'] = '\n'.join(lines)
        # The ordinary collector must run on the original immutable slot. A
        # general pool label could place recovery on a different runner, where
        # the original private journal and checkout are deliberately unreadable.
        recovery_targets = {}
        for slot in slots:
            slot_labels = [*labels, execution_slot_label(config, slot)]
            recovery_targets[slot['id']] = ({'group': general['group'], 'labels': slot_labels}
                                            if general.get('scope', 'repository') == 'organization'
                                            else slot_labels)
        targets = json.dumps(recovery_targets, separators=(',', ':'))
        values['RECOVERY_RUNS_ON_YAML'] = json.dumps("${{ fromJSON('" + targets + "')[inputs.execution_slot || 'primary'] }}")
        values['RECOVERY_SLOT_INPUT'] = '\n'.join([
            '      execution_slot:',
            '        description: Original execution slot from the retained attempt; primary for historical attempts',
            '        required: false', '        default: primary', '        type: choice',
            '        options: ' + json.dumps([slot['id'] for slot in slots]),
        ])
        values['RECOVERY_SLOT_ENV'] = '          RECOVERY_SLOT: ${{ inputs.execution_slot || \'primary\' }}'
        lines = ['case "$RECOVERY_SLOT:$RUNNER_NAME:$(/usr/bin/id -un)" in']
        lines.extend('            ' + shlex.quote(':'.join([slot['id'], slot['runnerName'], slot['runnerUser']]))
                     + ') export RELAY_EXECUTION_SLOT=' + shlex.quote(slot['id']) + ' ;;' for slot in slots)
        lines.extend(['            *) echo RELAY_RECOVERY_SLOT_IDENTITY_MISMATCH >&2; exit 1 ;;', '          esac'])
        values['RECOVERY_RUNNER_GUARD'] = '\n'.join(lines)
        if managed_pool:
            # Capacity contraction may retire the original physical runner.
            # Any active pool member can transport recovery; trusted Writer
            # resolves the immutable original execution slot from its claim.
            values['RECOVERY_RUNS_ON_YAML'] = json.dumps(general_runs_on)
            values['RECOVERY_SLOT_INPUT'] = ''
            values['RECOVERY_SLOT_ENV'] = ''
            values['RECOVERY_RUNNER_GUARD'] = values['GENERAL_RUNNER_GUARD']
    templates = {consumer['routingWorkflow']: 'routing', consumer['recoveryWorkflow']: 'recovery'}
    if deployment:
        templates = {PRODUCTION: 'deployment'}
    elif environment['localApply'].get('source') == 'installed' and repository == deployment_repository(config):
        require(PRODUCTION not in templates and PRODUCTION != consumer['validationWorkflow'],
                'workflow-production-path-conflict')
        templates[PRODUCTION] = 'production'
    result = {}
    for path, template in sorted(templates.items()):
        require(WORKFLOW.fullmatch(path), 'workflow-path')
        text = _read(source_root / 'deploy/workflows' / (template + '.yml.in')).decode('utf-8')
        tokens = set(re.findall(r'@@([A-Z_]+)@@', text))
        require(tokens <= values.keys(), 'workflow-template-token')
        for token in tokens:
            text = text.replace('@@' + token + '@@', values[token])
        require('@@' not in text, 'workflow-unresolved-token')
        result[path] = text.encode('utf-8')
    return result


def render_deployment(config, revision, source_root):
    return render(config, revision, source_root, deployment=True)


def integration(config, revision, source_root, consumer_root, output_root):
    """Produce a complete integration tree without gating host installation.

    Existing managed files must still match their own committed drift baseline.
    Compatibility is a supported ABI check; current template equality determines
    whether the owner should publish an updated artifact after installation.
    """
    root = Path(consumer_root)
    rendered = render(config, revision, source_root)
    expected = _manifest(config, source_root, rendered)
    previous, observed = _existing(root)
    if previous is None:
        compatibility = 'missing'
    else:
        require(previous['sourceRepository'] == expected['sourceRepository']
                and previous['consumerRepository'] == expected['consumerRepository'], 'workflow-consumer-binding')
        compatibility = ('incompatible' if previous.get('workflowContract') != expected['workflowContract'] else
                         'compatible' if previous == expected else 'stale-compatible')
    destination = Path(output_root).absolute()
    for checkout in [Path(source_root).resolve(), root.resolve()]:
        require(not destination.resolve().is_relative_to(checkout), 'projection-output-outside-checkouts')
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    for path, content in {**rendered, MANIFEST: _json(expected)}.items():
        target = _path(destination, path)
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if target.exists() or target.is_symlink():
            require(_read(target) == content, 'integration-artifact-changed')
        else:
            _write(target, content)
    deployment_directory = None
    if config['environment']['localApply'].get('source') == 'git':
        deployment_directory = destination.parent / (destination.name + '-deployment')
        deployment_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        for path, content in render_deployment(config, revision, source_root).items():
            target = _path(deployment_directory, path)
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if target.exists() or target.is_symlink():
                require(_read(target) == content, 'deployment-artifact-changed')
            else:
                _write(target, content)
    return {'directory': str(destination), 'files': [*rendered, MANIFEST], 'compatibility': compatibility,
            'deploymentDirectory': str(deployment_directory) if deployment_directory else None,
            'next': 'Publish the generated directory through the receiving repository normal change process. '
                    'The completed host installation does not need another installer run.'}


def _manifest(config, source_root, rendered, repository=None):
    # Digests retain an independent purpose: refuse edits to the previous
    # managed baseline before writing a new proposal. No product SHA pin.
    return {'schemaVersion': 2, 'workflowContract': contract(source_root, bool(config['consumer'].get('executionSlots'))),
            'sourceRepository': config['source']['repository'],
            'consumerRepository': deployment_repository(config, repository),
            'files': {path: sha256(data) for path, data in sorted(rendered.items())}}


def _existing(root):
    manifest_path = _path(root, MANIFEST)
    if not manifest_path.exists() and not manifest_path.is_symlink():
        return None, {}
    raw = _read(manifest_path)
    manifest = json.loads(raw, object_pairs_hook=unique_object)
    require(isinstance(manifest, dict), 'workflow-manifest-keys')
    legacy = type(manifest.get('schemaVersion')) is int and manifest['schemaVersion'] == 1
    identity = 'relayRevision' if legacy else 'workflowContract'
    require(set(manifest) == {
        'schemaVersion', identity, 'sourceRepository', 'consumerRepository', 'files'},
        'workflow-manifest-keys')
    require(type(manifest['schemaVersion']) is int and manifest['schemaVersion'] == (1 if legacy else 2)
            and isinstance(manifest[identity], str)
            and (REVISION.fullmatch(manifest[identity]) if legacy else
                 re.fullmatch(r'relay-workflows-v[1-9][0-9]*', manifest[identity])), 'workflow-manifest-version')
    files = manifest['files']
    require(isinstance(files, dict) and 2 <= len(files) <= 3, 'workflow-manifest-files')
    observed = {MANIFEST: raw}
    for path, expected in files.items():
        require(WORKFLOW.fullmatch(path) and isinstance(expected, str)
                and DIGEST.fullmatch(expected), 'workflow-manifest-file')
        destination = _path(root, path)
        require(destination.exists(), 'workflow-drift:' + path)
        content = _read(destination)
        require(sha256(content) == expected, 'workflow-drift:' + path)
        observed[path] = content
    return manifest, observed


def verify(config, revision, source_root, consumer_root, repository=None):
    """Verify committed consumer projection matches the selected target source."""
    rendered = render(config, revision, source_root, repository)
    expected = _manifest(config, source_root, rendered, repository)
    actual, observed = _existing(Path(consumer_root))
    require(actual == expected, 'workflow-projection-target-mismatch')
    require(all(observed[path] == content for path, content in rendered.items()),
            'workflow-projection-source-mismatch')
    return expected


def _write(path, content):
    descriptor, name = tempfile.mkstemp(prefix='.relay-workflow-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as target:
            target.write(content)
            target.flush()
            os.fsync(target.fileno())
            os.fchmod(target.fileno(), 0o644)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def project(config, revision, source_root, consumer_root, repository=None):
    """Write reviewable projection only after checking all previous managed bytes.

    Existing consumer files are never adopted implicitly. An interrupted write
    is visible as manifest drift and requires reconciliation; it is not silently
    completed or rolled back over potentially new consumer edits.
    """
    root = Path(consumer_root)
    rendered = render(config, revision, source_root, repository)
    expected = _manifest(config, source_root, rendered, repository)
    previous, observed = _existing(root)
    if previous:
        require(previous['consumerRepository'] == expected['consumerRepository']
                and previous['sourceRepository'] == expected['sourceRepository'], 'workflow-consumer-binding')
        require(set(previous['files']) == set(rendered), 'workflow-path-migration-required')
    else:
        for path in rendered:
            destination = _path(root, path)
            require(not destination.exists() and not destination.is_symlink(), 'workflow-unmanaged:' + path)

    changes = {**rendered, MANIFEST: _json(expected)}
    if all(observed.get(path) == content for path, content in changes.items()):
        return expected
    for path in changes:
        destination = _path(root, path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        _path(root, path)
    lock = root / '.github/.relay-workflows.lock'
    require(not lock.exists() and not lock.is_symlink(), 'workflow-projection-in-progress')
    lock.mkdir(mode=0o700)
    written = []
    try:
        # Recheck all files under the local projection lock, before the first
        # mutation. No remote operations, commits or publication happen here.
        for path in changes:
            destination = _path(root, path)
            current = _read(destination) if destination.exists() or destination.is_symlink() else None
            require(current == observed.get(path), 'workflow-concurrent-change:' + path)
        for path, content in changes.items():
            if observed.get(path) != content:
                destination = _path(root, path)
                current = _read(destination) if destination.exists() or destination.is_symlink() else None
                require(current == observed.get(path), 'workflow-concurrent-change:' + path)
                _write(root / path, content)
                written.append(path)
    except Exception as error:
        raise ValueError('WORKFLOW_PROJECTION_INCOMPLETE;written=' + ','.join(written)
                         + ';inspect-worktree-before-retry') from error
    finally:
        lock.rmdir()
    verify(config, revision, source_root, root, repository)
    return expected


def prepare(config, revision, source_root, consumer_root, output_root, repository=None):
    """Derive missing install artifacts without adopting consumer-owned files.

    A clean target needs no generated state. When consumer publication is still
    required, return a deterministic review directory and stop before any host
    mutation. Repeating the invocation after consumer review verifies the exact
    same source/configuration binding. Managed drift always remains an error.
    """
    consumer_root, output_root = Path(consumer_root), Path(output_root).absolute()
    rendered = render(config, revision, source_root, repository)
    expected = _manifest(config, source_root, rendered, repository)
    previous, observed = _existing(consumer_root)
    if previous == expected:
        verify(config, revision, source_root, consumer_root, repository)
        return {'state': 'ready', 'revision': revision}
    if previous:
        require(previous['consumerRepository'] == expected['consumerRepository']
                and previous['sourceRepository'] == expected['sourceRepository'], 'workflow-consumer-binding')
        require(set(previous['files']) == set(rendered), 'workflow-path-migration-required')
    for root in [Path(source_root).resolve(), consumer_root.resolve()]:
        require(not output_root.resolve().is_relative_to(root), 'projection-output-outside-checkouts')
    for parent in [*reversed(output_root.parents), output_root]:
        if parent.exists() or parent.is_symlink():
            _directory(parent)
        else:
            parent.mkdir(mode=0o700)
    manifest = output_root / MANIFEST
    if manifest.exists() or manifest.is_symlink():
        # Output is an immutable proposal for one target; do not overwrite a
        # previously edited or differently bound review directory.
        verify(config, revision, source_root, output_root, repository)
    else:
        project(config, revision, source_root, output_root, repository)
    return {'state': 'workflow-review-required', 'revision': revision,
            'directory': str(output_root), 'files': [*rendered, MANIFEST],
            'next': 'Review and publish these derived files through consumer authority, then rerun the same command.'}
