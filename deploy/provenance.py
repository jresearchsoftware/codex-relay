"""Atomic provenance promotion after the ordinary locked full read-only check.

This reuses the installed manifest/snapshot; it creates no cache or journal.
Only a config Git commit and dispatch provenance may change. Runtime inputs,
product and validated config bytes remain identical.
"""
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile


def promote(payload, *, root=Path('/'), owner_uid=0):
    def require(value):
        if not value:
            raise ValueError('PROVENANCE_BINDING_UNPROVEN')

    def stamp(info):
        return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode,
                info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)

    def unique(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value)
            value[key] = item
        return value

    def protect(path, directory=False):
        require(path.is_relative_to(root))
        for current in [path, *path.parents]:
            info = current.lstat()
            require(info.st_uid == owner_uid and not info.st_mode & 0o022)
            require((stat.S_ISDIR(info.st_mode) if current != path or directory
                     else stat.S_ISREG(info.st_mode) and info.st_nlink == 1))
            if current == root:
                return
        require(False)

    def read(path, modes):
        protect(path)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            require(stat.S_IMODE(before.st_mode) in modes and before.st_size <= 65536)
            raw = stream.read(65537)
            require(len(raw) <= 65536 and stamp(before) == stamp(os.fstat(stream.fileno()))
                    == stamp(path.lstat()))
        return raw, before

    def digest(receipt):
        fields = ['product_repository', 'product_repository_id', 'product_sha',
                  'config_repository', 'config_repository_id', 'config_sha',
                  'config_blob_sha', 'config_path', 'config_sha256']
        pair = {key: receipt[key] for key in fields if key in receipt}
        return hashlib.sha256(json.dumps(pair, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

    namespace, revision = payload['namespace'], payload['revision']
    require(re.fullmatch('[a-z][a-z0-9-]{0,30}', namespace)
            and re.fullmatch('[0-9a-f]{40}', revision))
    old, new = payload['previous'], payload['receipt']
    stable = ['product_repository', 'product_sha',
              'config_repository', 'config_path',
              'config_blob_sha', 'config_sha256', 'source_policy']
    require(all(key in old and old[key] == new.get(key) for key in stable)
            and all(old.get(key) == new.get(key) and (key in old) == (key in new)
                    and (key not in old or (type(old[key]) is int and old[key] > 0
                         and type(new[key]) is int and new[key] > 0))
                    for key in ['product_repository_id', 'config_repository_id'])
            and old['product_sha'] == revision
            and re.fullmatch('[0-9a-f]{40}', new.get('config_sha', '')))
    install = root / 'opt' / namespace
    protect(install, True)
    current = install / 'current'
    link = current.lstat()
    release = install / 'releases' / revision
    require(stat.S_ISLNK(link.st_mode) and link.st_uid == owner_uid
            and current.resolve(strict=True) == release)
    manifest_path = release / 'artifact-manifest.json'
    raw, metadata = read(manifest_path, {0o600, 0o640, 0o644})
    manifest = json.loads(raw, object_pairs_hook=unique)
    snapshot, snapshot_info = read(release / 'deployment-config.json', {0o600})
    source_raw, source_info = read(release / 'reviewed-source/.relay-source.json', {0o600, 0o640, 0o644})
    source = json.loads(source_raw, object_pairs_hook=unique)
    require(all(manifest.get(key) == revision for key in ['commit', 'installedRevision', 'resolvedRevision'])
            and source.get('revision') == revision and source.get('tree') == manifest.get('gitTree')
            and re.fullmatch('[0-9a-f]{40}', manifest.get('gitTree', ''))
            and hashlib.sha256(snapshot).hexdigest() == manifest.get('deploymentConfigSha256')
            == payload['deploymentConfigSha256'])
    # Replay after an atomic commit is safe; a third pair is never adopted.
    actual = manifest.get('gitConfigReceipt')
    require(actual in [old, new])
    state = manifest.get('installationState')
    require('installationState' not in manifest
            or (isinstance(state, dict) and type(state.get('schemaVersion')) is int
                and state == {'schemaVersion': 1, 'stage': 'ready', 'pairSha256': digest(actual)}))
    if actual == new:
        directory = os.open(release, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        return
    manifest['gitConfigReceipt'] = new
    if 'installationState' in manifest:
        manifest['installationState']['pairSha256'] = digest(new)
    temporary = None
    directory = os.open(release, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        descriptor, temporary = tempfile.mkstemp(prefix='.provenance-', dir=release)
        with os.fdopen(descriptor, 'w') as stream:
            os.fchown(stream.fileno(), metadata.st_uid, metadata.st_gid)
            os.fchmod(stream.fileno(), stat.S_IMODE(metadata.st_mode))
            json.dump(manifest, stream, sort_keys=True)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        require(stamp(manifest_path.lstat()) == stamp(metadata)
                and stamp((release / 'deployment-config.json').lstat()) == stamp(snapshot_info)
                and stamp((release / 'reviewed-source/.relay-source.json').lstat()) == stamp(source_info)
                and stamp(current.lstat()) == stamp(link))
        os.replace(Path(temporary).name, manifest_path.name, src_dir_fd=directory, dst_dir_fd=directory)
        temporary = None
        os.fsync(directory)
    finally:
        if temporary is not None:
            Path(temporary).unlink()
        os.close(directory)


def promote_remote(target, key, config, revision, previous, receipt, guard, pool_guard):
    from ansible_transport import run_target

    def held():
        return guard.poll() is None and (pool_guard is None or pool_guard.poll() is None)

    if not held():
        raise ValueError('HOST_LOCK_LOST')
    canonical = (json.dumps(config, sort_keys=True, separators=(',', ':'), ensure_ascii=False) + '\n').encode()
    payload = {'namespace': config['environment']['namespace'], 'revision': revision,
               'previous': previous, 'receipt': receipt,
               'deploymentConfigSha256': hashlib.sha256(canonical).hexdigest()}
    program = ('import hashlib,json,os,re,stat,sys,tempfile\nfrom pathlib import Path\n'
               + inspect.getsource(promote)
               + '\ntry:\n promote(json.load(sys.stdin))\n print("PROVENANCE_PROMOTED")\n'
               'except Exception:\n print("PROVENANCE_BINDING_UNPROVEN",file=sys.stderr);sys.exit(1)\n')
    result = run_target(target, key, ['/usr/bin/python3', '-I', '-c', program],
                        input=json.dumps(payload), timeout=60)
    if result.returncode != 0 or result.stdout.strip() != 'PROVENANCE_PROMOTED' or not held():
        raise ValueError('PROVENANCE_PROMOTION_UNPROVEN')


def loaded_ready_target(payload, adoption, *, root=Path('/')):
    """Read loaded inputs without creating an applying admission operation."""
    def require(value):
        if not value:
            raise ValueError('PROVENANCE_TARGET_BINDING_CHANGED')

    def unique(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value)
            value[key] = item
        return value

    def binding():
        revision, namespace = payload['revision'], payload['namespace']
        require(re.fullmatch('[0-9a-f]{40}', revision)
                and re.fullmatch('[a-z][a-z0-9-]{0,30}', namespace))
        install = root / 'opt' / namespace
        release = install / 'releases' / revision
        for path in [release / 'reviewed-source', *(release / 'reviewed-source').parents]:
            meta = path.lstat()
            require(stat.S_ISDIR(meta.st_mode) and meta.st_uid == 0 and not meta.st_mode & 0o022)
            if path == root:
                break
        current = install / 'current'
        link = current.lstat()
        require(stat.S_ISLNK(link.st_mode) and link.st_uid == 0
                and current.resolve(strict=True) == release)
        paths = [release / 'artifact-manifest.json', release / 'reviewed-source/.relay-source.json']
        values, stamps = [], []
        for path in paths:
            before = path.lstat()
            raw = adoption['protected'](path)
            require(adoption['identity'](path.lstat()) == adoption['identity'](before))
            values.append(json.loads(raw, object_pairs_hook=unique))
            stamps.append((adoption['identity'](before), hashlib.sha256(raw).hexdigest()))
        manifest, source = values
        require(all(manifest.get(key) == revision for key in ['commit', 'installedRevision', 'resolvedRevision'])
                and source.get('revision') == revision and source.get('tree') == manifest.get('gitTree')
                and re.fullmatch('[0-9a-f]{40}', manifest.get('gitTree', '')))
        return adoption['identity'](link), stamps

    before = binding()
    ready = False
    try:
        result = subprocess.run(['/bin/systemctl', 'show', payload['productionUnit'],
            '--property=LoadState,ActiveState,SubState,MainPID,NeedDaemonReload'],
            capture_output=True, check=True, timeout=15,
            env={**os.environ, 'LC_ALL': 'C'})
        state = dict(line.split('=', 1) for line in result.stdout.decode().splitlines())
        if state == {'LoadState': 'loaded', 'ActiveState': 'inactive', 'SubState': 'dead',
                     'MainPID': '0', 'NeedDaemonReload': 'no'}:
            active = False
        else:
            if not (state.get('LoadState') == 'loaded' and state.get('ActiveState') == 'active'
                    and state.get('SubState') == 'running' and state.get('NeedDaemonReload') == 'no'
                    and re.fullmatch('[1-9][0-9]*', state.get('MainPID', ''))):
                raise ValueError('PROVENANCE_LOADED_UNAVAILABLE')
            active = True
        adoption['capture_inputs']({**payload, 'productionActive': active})
        ready = True
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, ImportError,
            StopIteration, subprocess.SubprocessError):
        # Missing/older capability or mismatched loaded input chooses the
        # existing reconcile path. The independent target binding still must
        # remain exact, even when this optional proof was unavailable.
        pass
    require(binding() == before)
    return 'PROVENANCE_LOADED_READY' if ready else 'PROVENANCE_LOADED_UNAVAILABLE'


def loaded_ready(target, key, config, revision, guard, pool_guard):
    from ansible_transport import run_target
    from config import compile_inputs

    def held():
        return guard is not None and guard.poll() is None and (pool_guard is None or pool_guard.poll() is None)

    if not held():
        raise ValueError('HOST_LOCK_LOST')
    values = compile_inputs(config)
    install, configuration = values['relay_install_root'], values['relay_config_root']
    payload = {'namespace': values['relay_namespace'], 'revision': revision,
        'reviewerUnit': values.get('relay_reviewer_service_name', 'reviewer-mcp.service'),
        'productionUnit': values.get('relay_production_runner_service_name', 'relay-runner.service'),
        'reviewerUser': values['relay_reviewer_user'],
        'productionUser': values['relay_production_runner_user'],
        'productionRoot': values.get('relay_runner_root', install + '/runner'),
        'socket': values['relay_runtime_root'] + '/reviewer-proof/loaded.sock',
        'environmentFiles': [configuration + '/relay.env', configuration + '/reviewer-credentials/github-app.env'],
        'config': configuration + '/reviewer-mcp.json', 'release': install + '/current'}
    source = Path(__file__).with_name('process_adoption.py').read_text()
    # Execute the exact component implementation in a separate module namespace;
    # its managed-Apply __main__/admission path is deliberately not entered.
    program = ('import hashlib,json,os,re,stat,subprocess,sys\nfrom pathlib import Path\n'
               'adoption={"__name__":"relay_provenance_loaded_inputs"}\n'
               + 'exec(' + repr(source) + ',adoption)\n'
               + inspect.getsource(loaded_ready_target)
               + '\ntry:\n print(loaded_ready_target(json.load(sys.stdin),adoption))\n'
               'except Exception:\n print("PROVENANCE_LOADED_BINDING_CHANGED")\n')
    result = run_target(target, key, ['/usr/bin/python3', '-I', '-B', '-c', program],
                        input=json.dumps(payload), timeout=180)
    if not held():
        raise ValueError('HOST_LOCK_LOST')
    if result.returncode != 0:
        raise ValueError('PROVENANCE_LOADED_PROOF_UNPROVEN')
    observed = result.stdout.strip()
    if observed == 'PROVENANCE_LOADED_BINDING_CHANGED':
        raise ValueError('PROVENANCE_TARGET_BINDING_CHANGED')
    if observed not in ['PROVENANCE_LOADED_READY', 'PROVENANCE_LOADED_UNAVAILABLE']:
        raise ValueError('PROVENANCE_LOADED_PROOF_UNPROVEN')
    return observed == 'PROVENANCE_LOADED_READY'
