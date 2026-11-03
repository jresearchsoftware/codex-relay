"""Protected continuation evidence for an explicitly selected retained operation.

This module never opens admission, changes historical attempts or replaces the
backend journal. The owner installer supplies the frozen Git pair and the real
current-controller preflight under its existing Writer lock.
"""
import base64
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import sys

SHA = re.compile(r'[0-9a-f]{40}')
DIGEST = re.compile(r'[0-9a-f]{64}')
UUID = re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')
LIMIT = 512 * 1024


def require(condition, code):
    if not condition:
        raise ValueError('BOUNDED_RECOVERY_' + code)


def unique(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, 'DUPLICATE_FIELD')
        value[key] = item
    return value


def decode(raw):
    return json.loads(raw, object_pairs_hook=unique)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def stamp(info):
    return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def protect(path, root, owner_uid, *, directory=False):
    path, root = Path(path), Path(root)
    require(path.is_relative_to(root), 'PATH_UNSAFE')
    for at in [path, *path.parents]:
        info = at.lstat()
        require(info.st_uid == owner_uid and not info.st_mode & 0o022
                and (stat.S_ISDIR(info.st_mode) if at != path or directory
                     else stat.S_ISREG(info.st_mode) and info.st_nlink == 1), 'PATH_UNSAFE')
        if at == root:
            return info if at == path else path.lstat()
    require(False, 'PATH_UNSAFE')


def read(path, root, owner_uid, *, private=False):
    before = protect(path, root, owner_uid)
    require(before.st_size <= LIMIT and (not private or stat.S_IMODE(before.st_mode) == 0o600),
            'EVIDENCE_UNSAFE')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        opened = os.fstat(stream.fileno())
        raw = stream.read(LIMIT + 1)
        require(len(raw) <= LIMIT and stamp(before) == stamp(opened)
                == stamp(os.fstat(stream.fileno())) == stamp(Path(path).lstat()), 'EVIDENCE_CHANGED')
    return raw


def atomic(path, value, root, owner_uid, *, create=False):
    protect(path.parent, root, owner_uid, directory=True)
    temporary = path.with_name(path.name + '.next')
    require(not temporary.exists() and not temporary.is_symlink(), 'INTERRUPTED_RECEIPT')
    raw = (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()
    require(len(raw) <= LIMIT, 'RECEIPT_LIMIT')
    if create:
        require(not path.exists() and not path.is_symlink(), 'RECEIPT_EXISTS')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    sync_dir(path.parent)


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def binding_valid(binding):
    require(isinstance(binding, dict) and binding.keys() == {'operationId', 'retainedTarget',
            'installedRevision', 'controllerRevision', 'desiredRevision', 'gitConfigReceipt'}, 'BINDING_INVALID')
    require(UUID.fullmatch(binding.get('operationId', '')) and all(SHA.fullmatch(binding.get(key, ''))
            for key in ['retainedTarget', 'installedRevision', 'controllerRevision', 'desiredRevision'])
            and binding['controllerRevision'] == binding['desiredRevision'], 'BINDING_INVALID')
    receipt = binding['gitConfigReceipt']
    require(isinstance(receipt, dict) and receipt.get('product_sha') == binding['desiredRevision']
            and SHA.fullmatch(receipt.get('config_sha', ''))
            and SHA.fullmatch(receipt.get('config_blob_sha', ''))
            and DIGEST.fullmatch(receipt.get('config_sha256', '')), 'GIT_PAIR_INVALID')
    return binding


def paths(config, binding, root):
    namespace = config['environment']['namespace']
    require(isinstance(namespace, str) and re.fullmatch('[a-z][a-z0-9-]{0,30}', namespace), 'NAMESPACE_INVALID')
    install = root / 'opt' / namespace
    config_root = root / 'etc' / namespace
    claim = Path(config['consumer']['paths']['claimRoot'])
    if not claim.is_relative_to(root):
        claim = root / str(claim).lstrip('/')
    gate_name = 'admission-pool-v1.json' if (config_root / 'serial-pool-compat-v1.json').exists() else 'admission-v1.json'
    record = root / 'var/lib' / (namespace + '-production-operation.json')
    return {'install': install, 'config': config_root, 'gate': claim / gate_name,
            'record': record, 'receipt': record.with_name(record.stem + '.' + binding['operationId'] + '.continuation.json'),
            'journal': root / 'var/lib' / (namespace + '-clean-reinstall.json')}


def resource_identity(config):
    # Operational policy/profile may transition; these physical and credential
    # bindings may not be reinterpreted by the recovery flag.
    environment = {key: value for key, value in config['environment'].items()
                   if key not in {'localApply'}}
    consumer = {key: value for key, value in config['consumer'].items()
                if key in {'paths', 'runtimeUser', 'workGroup', 'writerApp', 'reviewerApp',
                           'owner', 'writerIdentity', 'remediationIdentity', 'repository', 'repositories',
                           'repositoryRuntimeUsers', 'executionSlots', 'generalRunnerPool'}}
    return sha(json.dumps({'environment': environment, 'consumer': consumer}, sort_keys=True).encode())


def credentials(config, root, owner_uid):
    """Observe configured host credentials without returning credential bytes."""
    namespace = config['environment']['namespace']
    candidates = {root / 'etc' / namespace / relative for relative in [
        'reviewer-credentials/github-app.env', 'reviewer-credentials/github-app-private-key.pem',
        'writer-credentials/github-app.env', 'writer-credentials/github-app-private-key.pem',
        'codex-credentials/access-token']}
    for key in ['credentialEnv', 'credentialKeyFile']:
        value = config['consumer']['paths'].get(key)
        if value:
            path = Path(value)
            candidates.add(path if path.is_relative_to(root) else root / str(path).lstrip('/'))
    allowed = {owner_uid}
    reviewer = config['environment'].get('reviewerUser')
    reviewer_gid = None
    if reviewer:
        try:
            allowed.add(pwd.getpwnam(reviewer).pw_uid)
            reviewer_gid = grp.getgrnam(reviewer).gr_gid
        except KeyError:
            pass
    result = {}
    for path in sorted(candidates):
        require(path.is_relative_to(root), 'CREDENTIAL_PATH_UNSAFE')
        if not path.exists() and not path.is_symlink():
            result[str(path.relative_to(root))] = None
            continue
        before = path.lstat()
        reviewer_file = path.is_relative_to(root / 'etc' / namespace / 'reviewer-credentials')
        mode = stat.S_IMODE(before.st_mode)
        accepted_mode = mode == 0o600 or (reviewer_file and mode == 0o640 and before.st_gid == reviewer_gid)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_uid in allowed
                and accepted_mode and before.st_size <= 65536, 'CREDENTIAL_UNSAFE')
        for parent in path.parents:
            info = parent.lstat()
            require(stat.S_ISDIR(info.st_mode) and info.st_uid in allowed and not info.st_mode & 0o022,
                    'CREDENTIAL_PATH_UNSAFE')
            if parent == root:
                break
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, 'rb') as stream:
            raw = stream.read(65537)
            require(len(raw) <= 65536 and stamp(before) == stamp(os.fstat(stream.fileno()))
                    == stamp(path.lstat()), 'CREDENTIAL_CHANGED')
        result[str(path.relative_to(root))] = {'uid': before.st_uid, 'gid': before.st_gid,
            'mode': stat.S_IMODE(before.st_mode), 'sha256': sha(raw)}
    return result


def installed(release, revision, root, owner_uid):
    manifest_raw = read(release / 'artifact-manifest.json', root, owner_uid)
    source_raw = read(release / 'reviewed-source/.relay-source.json', root, owner_uid)
    snapshot_raw = read(release / 'deployment-config.json', root, owner_uid, private=True)
    manifest, source, snapshot = map(decode, [manifest_raw, source_raw, snapshot_raw])
    require(all(manifest.get(key) == revision for key in ['commit', 'installedRevision', 'resolvedRevision'])
            and source.get('revision') == revision and SHA.fullmatch(manifest.get('gitTree', ''))
            and source.get('tree') == manifest['gitTree']
            and manifest.get('deploymentConfigSha256') == sha(snapshot_raw), 'INSTALLED_IDENTITY_UNPROVEN')
    metadata = manifest.get('deploymentContract')
    require(isinstance(metadata, dict) and metadata.get('schemaVersion') == 1
            and metadata.get('epoch') == 1 and isinstance(metadata.get('capabilities'), list)
            and set(metadata['capabilities']) == {'lifecycle-v1', 'git-desired-v1', 'integration-artifact-v1'},
            'COMPATIBILITY_UNPROVEN')
    receipt = manifest.get('gitConfigReceipt')
    require(isinstance(receipt, dict) and receipt.get('product_sha') == revision
            and SHA.fullmatch(receipt.get('config_sha', ''))
            and SHA.fullmatch(receipt.get('config_blob_sha', ''))
            and DIGEST.fullmatch(receipt.get('config_sha256', '')), 'ORIGINAL_GIT_PAIR_UNPROVEN')
    graph = hashlib.sha256()
    source_root = release / 'reviewed-source'
    count = total = 0
    for directory, directories, files in os.walk(source_root, followlinks=False):
        directories.sort()
        protect(Path(directory), root, owner_uid, directory=True)
        for name in sorted([*directories, *files]):
            path = Path(directory) / name
            info = path.lstat()
            count += 1
            total += info.st_size
            require(count <= 10000 and total <= 64 * 1024 * 1024, 'SOURCE_LIMIT')
            graph.update(str(path.relative_to(source_root)).encode() + b'\0')
            if stat.S_ISLNK(info.st_mode):
                target = os.readlink(path)
                canonical = '/opt/' + release.parent.parent.name + '/releases/' + revision + '/reviewed-source/'
                require(info.st_uid == owner_uid and info.st_nlink == 1
                        and target in [canonical + component for component in ['consumer', 'controller', 'contracts', 'runtime', 'reviewer']],
                        'SOURCE_ALIAS_UNPROVEN')
                graph.update(b'link\0' + target.encode())
            elif stat.S_ISDIR(info.st_mode):
                protect(path, root, owner_uid, directory=True)
                graph.update(b'directory\0')
            else:
                graph.update(b'file\0' + read(path, root, owner_uid))
            graph.update(b'\0')
    return manifest, snapshot, {'manifestSha256': sha(manifest_raw), 'sourceSha256': sha(source_raw),
        'snapshotSha256': sha(snapshot_raw), 'sourceGraphSha256': graph.hexdigest()}


def gate_value(raw, binding, *, final=False):
    gate = decode(raw)
    require(isinstance(gate, dict) and gate.keys() == {'version', 'consumerDigest', 'phase',
            'operationId', 'target', 'previousActive', 'verifiedRevision'} and type(gate['version']) is int
            and gate['version'] == 1 and DIGEST.fullmatch(gate.get('consumerDigest', ''))
            and gate.get('operationId') == binding['operationId'], 'GATE_UNPROVEN')
    require(isinstance(gate['previousActive'], dict), 'ORIGINAL_ACTIVITY_INTENT_UNPROVEN')
    if final:
        require(gate['phase'] == 'verified' and gate['target'] == binding['desiredRevision']
                and gate['verifiedRevision'] == binding['desiredRevision'], 'FINAL_GATE_UNPROVEN')
    else:
        require(gate['phase'] in ['recovery-required', 'applying']
                and gate['target'] in [binding['retainedTarget'], binding['desiredRevision']]
                and gate['verifiedRevision'] is None, 'GATE_UNPROVEN')
    return gate


def inspect(config, binding, *, root=Path('/'), owner_uid=0, admission_probe=None):
    binding_valid(binding)
    root = Path(root)
    p = paths(config, binding, root)
    require(binding['installedRevision'] == binding['retainedTarget'], 'RETAINED_INSTALLATION_REQUIRED')
    if p['receipt'].exists() or p['receipt'].is_symlink():
        receipt = load_receipt(p['receipt'], root, owner_uid)
        require(receipt['binding'] == binding and receipt['state'] == 'reserved'
                and receipt['desiredConfigSha256'] == sha(json.dumps(config, sort_keys=True).encode()),
                'RETAINED_RECEIPT_REQUIRES_DIAGNOSIS')
        old_release = p['install'] / 'releases' / binding['installedRevision']
        _, original_config, identity = installed(old_release, binding['installedRevision'], root, owner_uid)
        require(all(receipt['original'][key] == value for key, value in identity.items())
                and resource_identity(config) == receipt['original']['resourceSha256']
                and credentials(config, root, owner_uid) == receipt['original']['credentials']
                and read(p['record'], root, owner_uid, private=True) == base64.b64decode(receipt['original']['backendBytes']),
                'ORIGINAL_EVIDENCE_CHANGED')
        current = p['install'] / 'current'
        protect(p['install'], root, owner_uid, directory=True)
        info = current.lstat()
        require(stat.S_ISLNK(info.st_mode) and info.st_uid == owner_uid
                and os.readlink(current) in [prefix + revision for prefix in
                    ['releases/', '/opt/' + p['install'].name + '/releases/']
                    for revision in [binding['installedRevision'], binding['desiredRevision']]], 'CURRENT_CHANGED')
        if os.readlink(current).endswith(binding['desiredRevision']):
            final_installation(p['install'].name, receipt, root, owner_uid)
        gate = gate_value(read(p['gate'], root, owner_uid, private=True), binding)
        original_gate = decode(base64.b64decode(receipt['original']['gateBytes']))
        require(gate['previousActive'] == original_gate['previousActive']
                and gate['consumerDigest'] in [original_gate['consumerDigest'], receipt['desiredDigest']],
                'GATE_UNPROVEN')
        if admission_probe:
            result = observe(receipt, gate, admission_probe, 'inspect')
            require(result['desiredDigest'] == receipt['desiredDigest'], 'DESIRED_DIGEST_CHANGED')
        return receipt
    require(not p['journal'].exists() and not p['journal'].is_symlink()
            and not p['journal'].with_name(p['journal'].name + '.next').exists(), 'REINSTALL_REQUIRES_DIAGNOSIS')
    current = p['install'] / 'current'
    protect(p['install'], root, owner_uid, directory=True)
    info = current.lstat()
    release = p['install'] / 'releases' / binding['installedRevision']
    require(stat.S_ISLNK(info.st_mode) and info.st_uid == owner_uid
            and os.readlink(current) in ['releases/' + binding['installedRevision'],
                '/opt/' + p['install'].name + '/releases/' + binding['installedRevision']], 'CURRENT_CHANGED')
    manifest, original_config, identity = installed(release, binding['installedRevision'], root, owner_uid)
    require(resource_identity(config) == resource_identity(original_config), 'RESOURCE_IDENTITY_CHANGED')
    backend_raw = read(p['record'], root, owner_uid, private=True)
    require(decode(backend_raw) == {'schemaVersion': '1', 'state': 'RECOVERY_REQUIRED',
            'phase': 'apply', 'target_head': binding['retainedTarget']}, 'BACKEND_BINDING_CHANGED')
    gate_raw = read(p['gate'], root, owner_uid, private=True)
    gate = gate_value(gate_raw, binding)
    require(gate['phase'] == 'recovery-required' and gate['target'] == binding['retainedTarget'], 'ORIGINAL_GATE_CHANGED')
    consumer_raw = read(p['config'] / 'consumer.json', root, owner_uid)
    consumer = decode(consumer_raw)
    require(resource_identity({**original_config, 'consumer': consumer}) == resource_identity(original_config),
            'RESOURCE_IDENTITY_CHANGED')
    proof = {'schemaVersion': 1, 'binding': binding, 'original': {**identity,
        'resourceSha256': resource_identity(original_config), 'consumerSha256': sha(consumer_raw),
        'credentials': credentials(original_config, root, owner_uid),
        'consumer': consumer, 'originalConsumer': original_config['consumer'],
        'backendBytes': base64.b64encode(backend_raw).decode(), 'backendSha256': sha(backend_raw),
        'gateBytes': base64.b64encode(gate_raw).decode(), 'gateSha256': sha(gate_raw)},
        'desiredConfigSha256': sha(json.dumps(config, sort_keys=True).encode())}
    if admission_probe:
        observe(proof, gate, admission_probe, 'inspect')
    require(stamp(current.lstat()) == stamp(info) and read(p['record'], root, owner_uid, private=True) == backend_raw
            and read(p['gate'], root, owner_uid, private=True) == gate_raw
            and read(p['config'] / 'consumer.json', root, owner_uid) == consumer_raw, 'EVIDENCE_CHANGED')
    return proof


def observe(proof, gate, admission_probe, stage):
    require(callable(admission_probe), 'CURRENT_CONTROLLER_PROOF_REQUIRED')
    binding = proof['binding']
    result = admission_probe({'operationId': binding['operationId'], 'target': gate['target'],
        'consumerDigest': gate['consumerDigest'], 'originalConsumer': proof['original']['originalConsumer'],
        'currentConsumer': proof['original']['consumer'], 'desiredRevision': binding['desiredRevision'], 'stage': stage})
    require(isinstance(result, dict) and result.get('currentDigest') == gate['consumerDigest']
            and result.get('operationId') == binding['operationId'] and result.get('target') == gate['target']
            and result.get('phase') == gate['phase'] and result.get('active') == [] and result.get('unknown') == []
            and result.get('eligible') is True and DIGEST.fullmatch(result.get('desiredDigest', '')),
            'CURRENT_CONTROLLER_PROOF_UNPROVEN')
    return result


def begin(config, binding, proof, *, root=Path('/'), owner_uid=0, admission_probe=None):
    root = Path(root)
    require(proof == inspect(config, binding, root=root, owner_uid=owner_uid), 'ORIGINAL_EVIDENCE_CHANGED')
    p = paths(config, binding, root)
    if proof.get('state') == 'reserved':
        gate = gate_value(read(p['gate'], root, owner_uid, private=True), binding)
        result = observe(proof, gate, admission_probe, 'begin')
        require(result['desiredDigest'] == proof['desiredDigest'], 'DESIRED_DIGEST_CHANGED')
        return proof
    gate = gate_value(base64.b64decode(proof['original']['gateBytes']), binding)
    observed = observe(proof, gate, admission_probe, 'begin')
    require(proof == inspect(config, binding, root=root, owner_uid=owner_uid), 'ORIGINAL_EVIDENCE_CHANGED')
    receipt = {**proof, 'state': 'reserved', 'desiredDigest': observed['desiredDigest']}
    atomic(p['receipt'], receipt, root, owner_uid, create=True)
    return receipt


def load_receipt(path, root, owner_uid):
    require(not path.with_name(path.name + '.next').exists(), 'INTERRUPTED_RECEIPT')
    value = decode(read(path, root, owner_uid, private=True))
    require(isinstance(value, dict) and value.keys() == {'schemaVersion', 'binding', 'original',
            'desiredConfigSha256', 'state', 'desiredDigest'} and type(value['schemaVersion']) is int and value['schemaVersion'] == 1
            and value['state'] in ['reserved', 'backend-complete', 'complete']
            and DIGEST.fullmatch(value.get('desiredDigest', '')), 'RECEIPT_INVALID')
    binding_valid(value['binding'])
    original = value['original']
    require(isinstance(original, dict) and all(DIGEST.fullmatch(original.get(key, '')) for key in
        ['manifestSha256', 'sourceSha256', 'sourceGraphSha256', 'snapshotSha256', 'resourceSha256', 'consumerSha256', 'backendSha256', 'gateSha256'])
        and sha(base64.b64decode(original['backendBytes'], validate=True)) == original['backendSha256']
        and sha(base64.b64decode(original['gateBytes'], validate=True)) == original['gateSha256'], 'RECEIPT_INVALID')
    require(decode(base64.b64decode(original['backendBytes'])) == {'schemaVersion': '1', 'state': 'RECOVERY_REQUIRED',
        'phase': 'apply', 'target_head': value['binding']['retainedTarget']}, 'RECEIPT_INVALID')
    gate = gate_value(base64.b64decode(original['gateBytes']), value['binding'])
    require(gate['phase'] == 'recovery-required' and gate['target'] == value['binding']['retainedTarget'], 'RECEIPT_INVALID')
    return value


def revalidate(config, binding, proof, *, root=Path('/'), owner_uid=0, admission_probe=None):
    binding_valid(binding)
    root = Path(root)
    p = paths(config, binding, root)
    receipt = load_receipt(p['receipt'], root, owner_uid)
    require(receipt == proof and receipt['binding'] == binding and receipt['state'] == 'reserved', 'RECEIPT_CHANGED')
    manifest, original_config, identity = installed(p['install'] / 'releases' / binding['installedRevision'],
        binding['installedRevision'], root, owner_uid)
    require(all(receipt['original'][key] == value for key, value in identity.items())
            and resource_identity(config) == receipt['original']['resourceSha256']
            and sha(json.dumps(config, sort_keys=True).encode()) == receipt['desiredConfigSha256']
            and credentials(config, root, owner_uid) == receipt['original']['credentials']
            and read(p['record'], root, owner_uid, private=True) == base64.b64decode(receipt['original']['backendBytes']),
            'ORIGINAL_EVIDENCE_CHANGED')
    gate_raw = read(p['gate'], root, owner_uid, private=True)
    gate = gate_value(gate_raw, binding)
    require(gate['previousActive'] == decode(base64.b64decode(receipt['original']['gateBytes']))['previousActive'],
            'ACTIVATION_INTENT_CHANGED')
    result = observe(receipt, gate, admission_probe, 'revalidate')
    consumer_same = sha(read(p['config'] / 'consumer.json', root, owner_uid)) == receipt['original']['consumerSha256']
    require(result['desiredDigest'] == receipt['desiredDigest']
            and (consumer_same or result['currentDigest'] == receipt['desiredDigest']), 'DESIRED_DIGEST_CHANGED')
    require(read(p['gate'], root, owner_uid, private=True) == gate_raw
            and read(p['record'], root, owner_uid, private=True) == base64.b64decode(receipt['original']['backendBytes'])
            and credentials(config, root, owner_uid) == receipt['original']['credentials'], 'EVIDENCE_CHANGED')
    return receipt


def backend_paths(record_path, operation_id, root):
    record_path = Path(record_path)
    require(UUID.fullmatch(operation_id or '') and record_path.parent == root / 'var/lib'
            and re.fullmatch('[a-z][a-z0-9-]{0,30}-production-operation.json', record_path.name), 'BACKEND_PATH_INVALID')
    namespace = record_path.name.removesuffix('-production-operation.json')
    return namespace, record_path.with_name(record_path.stem + '.' + operation_id + '.continuation.json')


def backend_validate(record_path, desired_revision, operation_id, *, root=Path('/'), owner_uid=0, require_applying=False):
    root = Path(root)
    namespace, receipt_path = backend_paths(record_path, operation_id, root)
    receipt = load_receipt(receipt_path, root, owner_uid)
    binding = receipt['binding']
    require(receipt['state'] == 'reserved' and binding['operationId'] == operation_id
            and binding['desiredRevision'] == desired_revision
            and read(record_path, root, owner_uid, private=True) == base64.b64decode(receipt['original']['backendBytes']),
            'BACKEND_BINDING_CHANGED')
    _, original_config, identity = installed(root / 'opt' / namespace / 'releases' / binding['installedRevision'],
        binding['installedRevision'], root, owner_uid)
    require(all(receipt['original'][key] == value for key, value in identity.items())
            and resource_identity(original_config) == receipt['original']['resourceSha256']
            and credentials(original_config, root, owner_uid) == receipt['original']['credentials'],
            'ORIGINAL_EVIDENCE_CHANGED')
    p = paths({'environment': {'namespace': namespace}, 'consumer': receipt['original']['originalConsumer']}, binding, root)
    gate = gate_value(read(p['gate'], root, owner_uid, private=True), binding)
    old_gate = decode(base64.b64decode(receipt['original']['gateBytes']))
    require(gate['target'] == desired_revision and gate['phase'] in (['applying'] if require_applying else ['applying', 'recovery-required'])
            and gate['consumerDigest'] in [old_gate['consumerDigest'], receipt['desiredDigest']]
            and gate['previousActive'] == old_gate['previousActive'], 'BACKEND_GATE_CHANGED')
    return {'operationId': operation_id, 'originalTarget': binding['retainedTarget'],
            'desiredTarget': desired_revision, 'backendSha256': receipt['original']['backendSha256']}


def final_installation(namespace, receipt, root, owner_uid):
    binding = receipt['binding']
    install = root / 'opt' / namespace
    current = install / 'current'
    protect(install, root, owner_uid, directory=True)
    info = current.lstat()
    require(stat.S_ISLNK(info.st_mode) and info.st_uid == owner_uid and os.readlink(current) in [
        'releases/' + binding['desiredRevision'], '/opt/' + namespace + '/releases/' + binding['desiredRevision']],
        'FINAL_CURRENT_UNPROVEN')
    manifest, config, _ = installed(install / 'releases' / binding['desiredRevision'], binding['desiredRevision'], root, owner_uid)
    require(manifest.get('gitConfigReceipt') == binding['gitConfigReceipt']
            and sha(json.dumps(config, sort_keys=True).encode()) == receipt['desiredConfigSha256']
            and resource_identity(config) == receipt['original']['resourceSha256']
            and credentials(config, root, owner_uid) == receipt['original']['credentials'], 'FINAL_INSTALLATION_UNPROVEN')
    return config


def backend_finalize(record_path, desired_revision, operation_id, *, root=Path('/'), owner_uid=0):
    root = Path(root)
    result = backend_validate(record_path, desired_revision, operation_id, root=root, owner_uid=owner_uid, require_applying=True)
    namespace, receipt_path = backend_paths(record_path, operation_id, root)
    receipt = load_receipt(receipt_path, root, owner_uid)
    final_installation(namespace, receipt, root, owner_uid)
    archive = receipt_path.with_name(receipt_path.name.removesuffix('.json') + '.original.json')
    raw = base64.b64decode(receipt['original']['backendBytes'])
    descriptor = os.open(archive, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    sync_dir(archive.parent)
    require(read(archive, root, owner_uid, private=True) == raw, 'BACKEND_ARCHIVE_UNPROVEN')
    # Durable unchanged bytes precede removal of the active reservation. A
    # partial transition remains closed and is never replayed as a fresh apply.
    atomic(receipt_path, {**receipt, 'state': 'backend-complete'}, root, owner_uid)
    require(read(record_path, root, owner_uid, private=True) == base64.b64decode(receipt['original']['backendBytes']),
            'BACKEND_BINDING_CHANGED')
    Path(record_path).unlink()
    sync_dir(Path(record_path).parent)
    return result


def finalize(config, binding, proof, *, root=Path('/'), owner_uid=0, admission_probe=None):
    root = Path(root)
    p = paths(config, binding_valid(binding), root)
    receipt = load_receipt(p['receipt'], root, owner_uid)
    require(receipt == {**proof, 'state': 'backend-complete'} and receipt['binding'] == binding
            and not p['record'].exists() and not p['record'].is_symlink(), 'FINAL_RECEIPT_UNPROVEN')
    final_installation(p['install'].name, receipt, root, owner_uid)
    gate_raw = read(p['gate'], root, owner_uid, private=True)
    gate = gate_value(gate_raw, binding, final=True)
    require(gate['consumerDigest'] == receipt['desiredDigest']
            and gate['previousActive'] == decode(base64.b64decode(receipt['original']['gateBytes']))['previousActive'],
            'FINAL_GATE_UNPROVEN')
    result = observe(receipt, gate, admission_probe, 'finalize')
    require(result['desiredDigest'] == receipt['desiredDigest'], 'DESIRED_DIGEST_CHANGED')
    require(read(p['gate'], root, owner_uid, private=True) == gate_raw
            and not p['record'].exists() and not p['record'].is_symlink(), 'EVIDENCE_CHANGED')
    final_installation(p['install'].name, receipt, root, owner_uid)
    atomic(p['receipt'], {**receipt, 'state': 'complete'}, root, owner_uid)
    return {**receipt, 'state': 'complete'}


def fixed_probe(config, binding, source, lease, desired_digest):
    """Construct one current-source invocation; callers cannot select a command."""
    source, lease = Path(source), Path(lease)
    for path in [source, source / 'controller', source / 'controller/src', source / 'deploy']:
        protect(path, Path('/'), 0, directory=True)
    for path in [source / '.relay-source.json', source / 'controller/src/admission-cli.mjs',
                 source / 'deploy/writer_lock_lease.py', lease]:
        protect(path, Path('/'), 0)
    require(decode(read(source / '.relay-source.json', Path('/'), 0)).get('revision')
            == binding['controllerRevision'] and DIGEST.fullmatch(desired_digest or ''),
            'CONTROLLER_SOURCE_UNPROVEN')
    namespace = config['environment']['namespace']
    consumer = '/etc/' + namespace + '/consumer.json'
    repository = config['environment'].get('repository', config['consumer'].get('repository'))
    require(isinstance(repository, str) and re.fullmatch('[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository),
            'REPOSITORY_INVALID')
    prefix = ['/usr/bin/python3', '-I', str(source / 'deploy/writer_lock_lease.py'),
              '--exec-admission', str(lease), str(source), consumer, repository]
    def probe(_context):
        result = subprocess.run([*prefix, 'consumer-transition-preflight', '--desired-digest', desired_digest],
            capture_output=True, timeout=180,
            env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C', 'PYTHONDONTWRITEBYTECODE': '1'})
        require(result.returncode == 0 and len(result.stdout) <= 1024 * 1024,
                'CURRENT_CONTROLLER_PROOF_UNAVAILABLE')
        return decode(result.stdout)
    return probe


def remote_probe(target, key, config, binding, guard, pool_guard=None):
    """Transport static protected reads from this exact owner source."""
    from ansible_transport import run_target
    require(guard is not None and guard.poll() is None
            and (pool_guard is None or pool_guard.poll() is None), 'HOST_LOCK_LOST')
    program = ('context={"__name__":"relay_bounded_recovery"}\nexec(' + repr(Path(__file__).read_text()) + ',context)\n'
        'import json,sys,re\n'
        'try:\n p=json.load(sys.stdin);print(json.dumps(context["inspect"](p["config"],p["binding"])))\n'
        'except Exception as error:\n code=str(error);print(code if isinstance(error,ValueError) and '
        're.fullmatch(r"BOUNDED_RECOVERY_[A-Z_]{1,96}",code) else "BOUNDED_RECOVERY_UNPROVEN",file=sys.stderr);sys.exit(1)\n')
    result = run_target(target, key, ['/usr/bin/python3', '-I', '-c', program],
        input=json.dumps({'config': config, 'binding': binding}), timeout=120)
    require(guard.poll() is None and (pool_guard is None or pool_guard.poll() is None), 'HOST_LOCK_LOST')
    if result.returncode != 0:
        codes = re.findall(r'(?m)^BOUNDED_RECOVERY_[A-Z_]{1,96}$', result.stderr)
        if codes:
            raise ValueError(codes[-1])
        require(False, 'REMOTE_PROOF_UNAVAILABLE')
    require(len(result.stdout.encode()) <= LIMIT, 'REMOTE_PROOF_UNAVAILABLE')
    proof = decode(result.stdout)
    require(isinstance(proof, dict) and proof.get('binding') == binding, 'REMOTE_PROOF_CHANGED')
    return proof


def main(arguments=None):
    arguments = sys.argv[1:] if arguments is None else arguments
    if len(arguments) == 4 and arguments[0] in ['backend-validate', 'backend-validate-applying', 'backend-finalize']:
        if arguments[0] == 'backend-validate-applying':
            return backend_validate(Path(arguments[1]), arguments[2], arguments[3], require_applying=True)
        action = backend_validate if arguments[0] == 'backend-validate' else backend_finalize
        return action(Path(arguments[1]), arguments[2], arguments[3])
    if len(arguments) == 1 and arguments[0] in ['begin', 'revalidate', 'finalize']:
        raw = sys.stdin.buffer.read(LIMIT + 1)
        require(len(raw) <= LIMIT, 'INPUT_LIMIT')
        payload = decode(raw)
        require(isinstance(payload, dict) and payload.keys() == {'config', 'binding', 'proof',
                'source', 'lease', 'desiredDigest'}, 'INPUT_INVALID')
        probe = fixed_probe(payload['config'], binding_valid(payload['binding']), payload['source'],
                            payload['lease'], payload['desiredDigest'])
        return globals()[arguments[0]](payload['config'], payload['binding'], payload['proof'], admission_probe=probe)
    require(False, 'ARGUMENTS_INVALID')


if __name__ == '__main__':
    try:
        print(json.dumps(main(), sort_keys=True))
    except Exception as error:
        code = str(error)
        print(code if isinstance(error, ValueError) and re.fullmatch('BOUNDED_RECOVERY_[A-Z_]{1,96}', code)
              else 'BOUNDED_RECOVERY_UNPROVEN', file=sys.stderr)
        sys.exit(1)
