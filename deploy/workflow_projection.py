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

from config import require, unique_object


MANIFEST = '.github/relay-workflows.json'
PRODUCTION = '.github/workflows/manual-main-production-deploy.yml'
WORKFLOW = re.compile(r'\.github/workflows/[A-Za-z0-9_-]+\.ya?ml')
REVISION = re.compile(r'[0-9a-f]{40}')
DIGEST = re.compile(r'[0-9a-f]{64}')
MAX_BYTES = 65536


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


def render(config, revision, source_root):
    """Return deterministic managed bytes; config must have passed config.load."""
    require(isinstance(revision, str) and REVISION.fullmatch(revision), 'workflow-exact-revision')
    source_root = Path(source_root)
    consumer, environment = config['consumer'], config['environment']
    general, production = environment['generalRunner'], environment['runner']
    labels = ['self-hosted', 'Linux', 'X64', *production['labels']]
    general_runs_on = ({'group': general['group'], 'labels': labels}
                       if general.get('scope', 'repository') == 'organization' else labels)
    values = {
        'REVISION': revision,
        'REPOSITORY': consumer['repository'], 'OWNER': consumer['owner'],
        'BASE_BRANCH': consumer['baseBranch'],
        'BASE_BRANCH_YAML': json.dumps(consumer['baseBranch']),
        'NAMESPACE': environment['namespace'],
        'CONTROL_GROUP_YAML': json.dumps(environment['namespace'] + '-control'),
        'PRODUCTION_GROUP_YAML': json.dumps(environment['namespace'] + '-production'),
        'GENERAL_RUNS_ON_YAML': json.dumps(general_runs_on),
        'PRODUCTION_RUNS_ON_YAML': json.dumps({'group': production['group'], 'labels': labels}),
        'GENERAL_RUNNER_NAME': shlex.quote(general['name']),
        'GENERAL_RUNNER_USER': shlex.quote(general['user']),
        'PRODUCTION_RUNNER_NAME': shlex.quote(production['name']),
        'PRODUCTION_RUNNER_USER': shlex.quote(production['user']),
    }
    templates = {consumer['routingWorkflow']: 'routing', consumer['recoveryWorkflow']: 'recovery'}
    if environment['localApply'].get('source') == 'installed':
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


def _manifest(config, revision, rendered):
    return {'schemaVersion': 1, 'relayRevision': revision,
            'sourceRepository': config['source']['repository'],
            'consumerRepository': config['consumer']['repository'],
            'files': {path: sha256(data) for path, data in sorted(rendered.items())}}


def _existing(root):
    manifest_path = _path(root, MANIFEST)
    if not manifest_path.exists() and not manifest_path.is_symlink():
        return None, {}
    raw = _read(manifest_path)
    manifest = json.loads(raw, object_pairs_hook=unique_object)
    require(isinstance(manifest, dict) and set(manifest) == {
        'schemaVersion', 'relayRevision', 'sourceRepository', 'consumerRepository', 'files'},
        'workflow-manifest-keys')
    require(type(manifest['schemaVersion']) is int and manifest['schemaVersion'] == 1
            and isinstance(manifest['relayRevision'], str)
            and REVISION.fullmatch(manifest['relayRevision']), 'workflow-manifest-version')
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


def verify(config, revision, source_root, consumer_root):
    """Verify committed consumer projection matches the selected target source."""
    rendered = render(config, revision, source_root)
    expected = _manifest(config, revision, rendered)
    actual, observed = _existing(Path(consumer_root))
    require(actual == expected, 'workflow-projection-target-mismatch')
    require(all(observed[path] == content for path, content in rendered.items()),
            'workflow-projection-source-mismatch')
    return expected


def _legacy(config, source_root, root, rendered):
    legacy = json.loads(_read(Path(source_root) / 'deploy/workflows/legacy.json'),
                        object_pairs_hook=unique_object)
    require(config['consumer']['repository'] == legacy['consumerRepository']
            and config['consumer']['owner'] == legacy['owner']
            and set(rendered) == set(legacy['files']), 'workflow-legacy-consumer')
    observed = {}
    for path, expected in legacy['files'].items():
        destination = _path(root, path)
        require(destination.exists(), 'workflow-legacy-missing:' + path)
        observed[path] = _read(destination)
        require(sha256(observed[path]) == expected, 'workflow-legacy-drift:' + path)
    return observed


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


def project(config, revision, source_root, consumer_root, *, adopt_legacy=False):
    """Write reviewable projection only after checking all previous managed bytes.

    Existing consumer files are never adopted implicitly. An interrupted write
    is visible as manifest drift and requires reconciliation; it is not silently
    completed or rolled back over potentially new consumer edits.
    """
    root = Path(consumer_root)
    rendered = render(config, revision, source_root)
    expected = _manifest(config, revision, rendered)
    previous, observed = _existing(root)
    require(not (adopt_legacy and previous), 'workflow-legacy-already-managed')
    if previous:
        require(previous['consumerRepository'] == expected['consumerRepository']
                and previous['sourceRepository'] == expected['sourceRepository'], 'workflow-consumer-binding')
        require(set(previous['files']) == set(rendered), 'workflow-path-migration-required')
    elif adopt_legacy:
        observed = _legacy(config, source_root, root, rendered)
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
    verify(config, revision, source_root, root)
    return expected
