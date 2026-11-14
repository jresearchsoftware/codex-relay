"""Atomic provenance promotion after sufficient locked current read-only proof.

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
import sys
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
    expected_binding = payload.get('currentBinding')
    if expected_binding is not None:
        def proof_stamp(info):
            return [info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
                    info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns]
        require(isinstance(expected_binding, dict)
                and expected_binding.get('revision') == revision
                and expected_binding.get('release') == '/opt/' + namespace + '/releases/' + revision
                and expected_binding.get('current') == proof_stamp(link)
                and expected_binding.get('manifestSha256') == hashlib.sha256(raw).hexdigest()
                and expected_binding.get('snapshotSha256') == hashlib.sha256(snapshot).hexdigest()
                and expected_binding.get('sourceSha256') == hashlib.sha256(source_raw).hexdigest()
                and expected_binding.get('files') == [proof_stamp(info) for info in [metadata, snapshot_info, source_info]])
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


def promote_remote(target, key, config, revision, previous, receipt, guard, pool_guard, *, current_binding=None):
    from ansible_transport import run_target

    def held():
        return guard.poll() is None and (pool_guard is None or pool_guard.poll() is None)

    if not held():
        raise ValueError('HOST_LOCK_LOST')
    canonical = (json.dumps(config, sort_keys=True, separators=(',', ':'), ensure_ascii=False) + '\n').encode()
    payload = {'namespace': config['environment']['namespace'], 'revision': revision,
               'previous': previous, 'receipt': receipt,
               'deploymentConfigSha256': hashlib.sha256(canonical).hexdigest()}
    if current_binding is not None:
        payload['currentBinding'] = current_binding
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


def native_context_target(payload):
    """Describe canonical desired state using the qualified installed product."""
    import source_upgrade_proof as proof
    values = dict(payload['values'])
    source = Path(values['relay_install_root']) / 'releases' / payload['revision'] / 'reviewed-source'
    binding, manifest, identity, _ = proof.read_binding(values)
    if binding['revision'] != payload['revision']:
        raise ValueError('PROVENANCE_TARGET_BINDING_CHANGED')
    context = proof.describe(values, payload['config'], identity, source)
    return {'eligible': True, 'binding': binding, 'values': context['oldValues'], 'manifest': manifest}


def native_prove_target(payload):
    """One complete current proof; only its own private package reference mutates."""
    import base64
    import shutil
    import uuid
    import source_upgrade_proof as proof
    from source_upgrade import stage_helper
    from source_upgrade_packages import prepare_reference
    values = dict(payload['context']['values'])
    source = Path(values['relay_install_root']) / 'releases' / payload['revision'] / 'reviewed-source'
    binding = proof.read_binding(values)[0]
    if binding != payload['context']['binding'] or binding['revision'] != payload['revision']:
        raise ValueError('PROVENANCE_TARGET_BINDING_CHANGED')
    catalogue = payload['catalogue']
    consumer = next(row for row in catalogue['entries'] if row['path'] == values['relay_consumer_config_path'])
    raw = base64.b64decode(consumer['contentBase64'], validate=True)
    # The same native consumer parser/digest as PreparedInstall.desired().
    program = ('import {readFileSync} from "node:fs";import {pathToFileURL} from "node:url";'
               'const m=await import(pathToFileURL(process.argv[1]));'
               'console.log(JSON.stringify(m.consumerDigest(m.validateConsumer(m.parseConsumerJson(readFileSync(0,"utf8"))))));')
    result = subprocess.run(['/usr/bin/node', '--input-type=module', '-e', program,
                             str(source / 'consumer/consumer-config.mjs')], input=raw,
                            capture_output=True, timeout=20, check=True,
                            env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'})
    digest = json.loads(result.stdout)
    if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
        raise ValueError('PROVENANCE_NATIVE_PROOF_UNAVAILABLE')
    values['relay_source_reuse_consumer_digest'] = digest
    helper = stage_helper(source)
    parent = Path(values['relay_release_root'])
    helper.protected(parent, directory=True)
    operation = str(uuid.uuid4())
    stage = parent / ('.stage-' + operation)
    stage.mkdir(mode=0o700)
    created = stage.lstat()
    try:
        reference = prepare_reference(stage, operation, values, source)
        live = proof.prove(values, payload['config'], source, catalogue,
                           expected_binding=binding, stage=stage, operation=operation,
                           package_reference=reference)
        return {'eligible': True, 'binding': live['binding'],
                'liveProofSha256': hashlib.sha256(json.dumps(live, sort_keys=True, separators=(',', ':')).encode()).hexdigest()}
    finally:
        # This call created the stage exclusively for one reconstructible
        # reference. An unexpected entry or replaced root is preserved/refused.
        helper.stage_root(stage, operation)
        current = stage.lstat()
        if (current.st_dev, current.st_ino) != (created.st_dev, created.st_ino) or any(
                child.name != 'codex-proof-reference' for child in stage.iterdir()):
            raise ValueError('PROVENANCE_NATIVE_STAGE_CHANGED')
        shutil.rmtree(stage)


def _native_dispatch(action, payload, *, root=Path('/')):
    """Protected same-product capability lookup; older installations fall back."""
    null = os.lstat('/dev/null')
    if not stat.S_ISCHR(null.st_mode):
        raise ValueError('PROVENANCE_TARGET_BINDING_CHANGED')
    # -B alone still reads installed caches. Standard SourceFileLoader honors
    # this prefix for reads too; a character device cannot contain cache files.
    previous_prefix, previous_writes = sys.pycache_prefix, sys.dont_write_bytecode
    try:
        sys.pycache_prefix = '/dev/null'
        sys.dont_write_bytecode = True
        return _native_dispatch_installed(action, payload, root=root)
    finally:
        sys.pycache_prefix, sys.dont_write_bytecode = previous_prefix, previous_writes


def _native_dispatch_installed(action, payload, *, root=Path('/')):
    """Run the complete installed proof while cache reads remain redirected."""
    import importlib.util
    if action not in ['context', 'prove']:
        raise ValueError('PROVENANCE_TARGET_BINDING_CHANGED')
    namespace, revision = payload['namespace'], payload['revision']
    if not re.fullmatch('[a-z][a-z0-9-]{0,30}', namespace) or not re.fullmatch('[0-9a-f]{40}', revision):
        raise ValueError('PROVENANCE_TARGET_BINDING_CHANGED')
    install = root / 'opt' / namespace
    if (payload['values'].get('relay_install_root') != str(install)
            or payload['values'].get('relay_release_root') != str(install / 'releases')
            or payload['config'].get('environment', {}).get('namespace') != namespace):
        raise ValueError('PROVENANCE_TARGET_BINDING_CHANGED')
    release = install / 'releases' / revision
    current = install / 'current'
    for path in [release / 'reviewed-source', *(release / 'reviewed-source').parents]:
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('PROVENANCE_TARGET_BINDING_CHANGED')
    link = current.lstat()
    if not stat.S_ISLNK(link.st_mode) or link.st_uid != 0 or os.readlink(current) != str(release):
        raise ValueError('PROVENANCE_TARGET_BINDING_CHANGED')
    source = release / 'reviewed-source'
    def record(path):
        before = path.lstat()
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != 0 or before.st_mode & 0o022
                or before.st_nlink != 1 or before.st_size > 65536):
            raise ValueError('PROVENANCE_TARGET_BINDING_CHANGED')
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as stream:
            opened = os.fstat(stream.fileno())
            if (opened.st_dev, opened.st_ino, opened.st_ctime_ns, opened.st_size) != (
                    before.st_dev, before.st_ino, before.st_ctime_ns, before.st_size):
                raise ValueError('PROVENANCE_TARGET_BINDING_CHANGED')
            raw = stream.read(65537)
            finished = os.fstat(stream.fileno())
            if (finished.st_dev, finished.st_ino, finished.st_ctime_ns, finished.st_size) != (
                    before.st_dev, before.st_ino, before.st_ctime_ns, before.st_size):
                raise ValueError('PROVENANCE_TARGET_BINDING_CHANGED')
        after = path.lstat()
        if (len(raw) != before.st_size or (before.st_dev, before.st_ino, before.st_ctime_ns)
                != (after.st_dev, after.st_ino, after.st_ctime_ns)):
            raise ValueError('PROVENANCE_TARGET_BINDING_CHANGED')
        return json.loads(raw)
    manifest = record(release / 'artifact-manifest.json')
    identity = record(source / '.relay-source.json')
    if (any(manifest.get(key) != revision for key in ['commit', 'installedRevision', 'resolvedRevision'])
            or identity.get('revision') != revision or identity.get('tree') != manifest.get('gitTree')):
        raise ValueError('PROVENANCE_TARGET_BINDING_CHANGED')
    deployment = source / 'deploy'
    directory = deployment.lstat()
    if not stat.S_ISDIR(directory.st_mode) or directory.st_uid != 0 or directory.st_mode & 0o022:
        raise ValueError('PROVENANCE_TARGET_BINDING_CHANGED')
    entry = deployment / 'provenance.py'
    if not os.path.lexists(entry):
        return {'eligible': False}
    meta = entry.lstat()
    if not stat.S_ISREG(meta.st_mode) or meta.st_uid != 0 or meta.st_mode & 0o022 or meta.st_nlink != 1:
        raise ValueError('PROVENANCE_TARGET_BINDING_CHANGED')
    # Python imports this installed closure before the full source identity
    # proof can run. Preserve the ordinary root-only source import boundary.
    for index, path in enumerate([deployment, *deployment.rglob('*')]):
        info = path.lstat()
        if (index > 20000 or info.st_uid != 0 or info.st_mode & 0o022
                or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode))):
            raise ValueError('PROVENANCE_TARGET_BINDING_CHANGED')
    sys.path.insert(0, str(source / 'deploy'))
    spec = importlib.util.spec_from_file_location('relay_installed_native_provenance', entry)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    function = getattr(module, 'native_context_target' if action == 'context' else 'native_prove_target', None)
    if not callable(function):
        return {'eligible': False}
    try:
        return function(payload)
    except (ValueError, OSError, RuntimeError, ImportError, KeyError, TypeError, StopIteration,
            subprocess.SubprocessError) as error:
        code = str(error)
        if code in ['PROVENANCE_TARGET_BINDING_CHANGED', 'SOURCE_UPGRADE_BINDING_CHANGED',
                    'SOURCE_UPGRADE_INSTALLED_BINDING_UNPROVEN', 'SOURCE_UPGRADE_CONFIG_CHANGED',
                    'PROVENANCE_NATIVE_STAGE_CHANGED', 'SOURCE_UPGRADE_PARENT_UNSAFE',
                    'SOURCE_UPGRADE_FILE_UNSAFE', 'SOURCE_UPGRADE_FILE_MOVED',
                    'SOURCE_UPGRADE_CURRENT_UNSAFE', 'SOURCE_UPGRADE_BINDING_INVALID',
                    'SOURCE_UPGRADE_RECEIPT_UNPROVEN', 'SOURCE_UPGRADE_PENDING_INSTALLATION']:
            raise ValueError('PROVENANCE_TARGET_BINDING_CHANGED') from None
        return {'eligible': False}


def native_ready(target, key, config, revision, guard, pool_guard):
    """Sufficient native same-product proof, or None for the ordinary full path."""
    from ansible_transport import run_target
    from config import compile_inputs
    from installed_state import build_catalogue, NotEligible
    from source_upgrade import artifact_values
    from source_upgrade_proof import resolve_values

    def held():
        pool_required = 'generalRunnerPool' in config.get('consumer', {})
        if (guard is None or guard.poll() is not None or pool_required and pool_guard is None
                or pool_guard is not None and pool_guard.poll() is not None):
            raise ValueError('HOST_LOCK_LOST')

    held()
    source = Path(__file__).resolve().parents[1]
    try:
        values = resolve_values({**compile_inputs(config), 'relay_deployment_profile': 'production'}, source)
    except (NotEligible, ValueError, OSError, ImportError):
        return None
    payload = {'namespace': config['environment']['namespace'], 'revision': revision,
               'values': values, 'config': config}
    program = ('import hashlib,json,os,re,stat,subprocess,sys\nfrom pathlib import Path\n'
               + inspect.getsource(_native_dispatch_installed) + '\n' + inspect.getsource(_native_dispatch)
               + '\ntry:\n print(json.dumps(_native_dispatch(sys.argv[1],json.load(sys.stdin))))\n'
               'except Exception:\n print(json.dumps({"bindingChanged":True}))\n')

    def invoke(action):
        held()
        result = run_target(target, key, ['/usr/bin/python3', '-I', '-B', '-c', program, action],
                            input=json.dumps(payload), timeout=180)
        held()
        if result.returncode != 0:
            raise ValueError('PROVENANCE_NATIVE_TRANSPORT_UNPROVEN')
        observed = json.loads(result.stdout)
        if observed.get('bindingChanged'):
            raise ValueError('PROVENANCE_TARGET_BINDING_CHANGED')
        return observed

    context = invoke('context')
    if context.get('eligible') is not True:
        return None
    try:
        catalogue = build_catalogue(source, artifact_values(context['values'], context['manifest']))
    except (NotEligible, ValueError, OSError, ImportError):
        return None
    payload.update(context=context, catalogue=catalogue)
    observed = invoke('prove')
    if observed.get('eligible') is not True:
        return None
    if observed.get('binding') != context['binding'] or not re.fullmatch('[0-9a-f]{64}', observed.get('liveProofSha256', '')):
        raise ValueError('PROVENANCE_TARGET_BINDING_CHANGED')
    return {'binding': observed['binding'], 'liveProofSha256': observed['liveProofSha256']}
