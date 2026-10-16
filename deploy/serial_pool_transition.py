"""Bounded SERIAL ownership transition; historical authority is never rewritten.

The caller holds the namespace/pool deployment locks and qualifies the
prospective pool's complete runner-group policy before calling this module.
Native runner/service observations are supplied by fixed owner adapters. No
worker input, credential bytes, source execution or arbitrary command is used.
The original gate adapter retains its own Writer-lock discipline.
"""
from contextlib import contextmanager
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import uuid

from managed_pool import require


STATE_NAME = 'serial-pool-transition-v1.json'
RECEIPT_NAME = 'serial-pool-compat-v1.json'
CONSUMER_NAME = 'serial-consumer-v1.json'
PHASES = {'reserved', 'prepared', 'stop-intent', 'stopped', 'target-ready',
          'remove-intent', 'retired'}
MAX_BYTES = 1024 * 1024
MAX_SOURCE_FILES = 10000
MAX_SOURCE_BYTES = 64 * 1024 * 1024
SHA = re.compile(r'[0-9a-f]{64}')
REVISION = re.compile(r'[0-9a-f]{40}')


def encoded(value):
    """Match JSON.stringify for the contract's JSON objects and integer IDs."""
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _json(raw):
    def unique(pairs):
        value = {}
        for name, item in pairs:
            require(name not in value, 'SERIAL_TRANSITION_JSON_INVALID')
            value[name] = item
        return value
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=unique)
    except (ValueError, UnicodeError, RecursionError):
        require(False, 'SERIAL_TRANSITION_JSON_INVALID')
    require(isinstance(value, dict), 'SERIAL_TRANSITION_JSON_INVALID')
    return value


def _stamp(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


class ProtectedFiles:
    """Descriptor-relative no-follow reads and durable exclusive publication."""
    def __init__(self, root=Path('/'), owner_uid=0):
        self.root, self.owner_uid = Path(root), owner_uid

    def _directory(self, info):
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == self.owner_uid
                and not info.st_mode & 0o022, 'SERIAL_TRANSITION_PARENT_UNSAFE')

    @contextmanager
    def parent(self, logical):
        path = PurePosixPath(logical)
        require(path.is_absolute() and str(path) == str(logical)
                and all(part not in ['', '.', '..'] for part in path.parts[1:]),
                'SERIAL_TRANSITION_PATH_UNSAFE')
        descriptors = []
        try:
            current = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            descriptors.append(current)
            self._directory(os.fstat(current))
            for part in path.parts[1:-1]:
                current = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                  dir_fd=current)
                descriptors.append(current)
                self._directory(os.fstat(current))
            yield current, path.name
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)

    def read(self, logical, *, modes=None, optional=False, allow_empty=False):
        try:
            with self.parent(logical) as (parent, name):
                descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                     dir_fd=parent)
                with os.fdopen(descriptor, 'rb') as stream:
                    info = os.fstat(stream.fileno())
                    require(stat.S_ISREG(info.st_mode) and info.st_uid == self.owner_uid
                            and info.st_nlink == 1 and not info.st_mode & 0o022
                            and (modes is None or stat.S_IMODE(info.st_mode) in modes)
                            and (allow_empty or info.st_size > 0) and info.st_size <= MAX_BYTES,
                            'SERIAL_TRANSITION_FILE_UNSAFE')
                    raw = stream.read(MAX_BYTES + 1)
                    require(len(raw) <= MAX_BYTES and _stamp(info) == _stamp(os.fstat(stream.fileno()))
                            and _stamp(info) == _stamp(os.stat(name, dir_fd=parent, follow_symlinks=False)),
                            'SERIAL_TRANSITION_FILE_CHANGED')
                    return raw
        except FileNotFoundError:
            if optional:
                return None
            raise

    def write(self, logical, raw, *, mode=0o600, replace=False):
        require(0 < len(raw) <= MAX_BYTES, 'SERIAL_TRANSITION_FILE_SIZE')
        existing = self.read(logical, modes={mode}, optional=True)
        if existing == raw:
            return
        require(existing is None or replace, 'SERIAL_TRANSITION_PUBLICATION_CONFLICT')
        with self.parent(logical) as (parent, name):
            temporary = '.serial-pool-' + str(uuid.uuid4())
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 mode, dir_fd=parent)
            try:
                with os.fdopen(descriptor, 'wb') as stream:
                    os.fchmod(stream.fileno(), mode)
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                if replace:
                    # The namespace deployment lock remains held by the caller.
                    require(self.read(logical, modes={mode}, optional=True) == existing,
                            'SERIAL_TRANSITION_FILE_CHANGED')
                    os.replace(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
                else:
                    os.link(temporary, name, src_dir_fd=parent, dst_dir_fd=parent,
                            follow_symlinks=False)
                    os.unlink(temporary, dir_fd=parent)
                os.fsync(parent)
            finally:
                try:
                    os.unlink(temporary, dir_fd=parent)
                except FileNotFoundError:
                    pass

    def directory(self, logical):
        """Create one fixed protected context directory, never adopt an alias."""
        with self.parent(logical) as (parent, name):
            try:
                os.mkdir(name, 0o755, dir_fd=parent)
                descriptor = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                try:
                    os.fchmod(descriptor, 0o755)
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
                os.fsync(parent)
            except FileExistsError:
                pass
            self._directory(os.stat(name, dir_fd=parent, follow_symlinks=False))

    def tree_sha256(self, logical, *, copy_to=None, source_links=None, original_source_root=None):
        rows = []
        total_bytes = 0
        links = {} if source_links is None else source_links
        components = {'controller', 'consumer', 'contracts', 'runtime', 'reviewer'}
        require(isinstance(links, dict) and len(links) <= 8 and all(
            isinstance(alias, str) and re.fullmatch(r'[A-Za-z0-9_./-]+', alias)
            and '/' in alias and all(part and part not in ['.', '..'] for part in alias.split('/'))
            and alias.split('/')[0] not in components | {'deploy'}
            and isinstance(component, str) and component in components
            for alias, component in links.items()), 'SERIAL_TRANSITION_SOURCE_LINKS_INVALID')
        if links:
            require(isinstance(original_source_root, str) and re.fullmatch(
                r'/opt/[a-z][a-z0-9-]{0,30}/releases/[0-9a-f]{40}/reviewed-source', original_source_root),
                'SERIAL_TRANSITION_SOURCE_LINKS_INVALID')
        observed_links = set()
        if copy_to is not None:
            self.directory(copy_to)
        with self.parent(logical + '/.tree-boundary') as (root, _):
            def visit(directory, prefix):
                nonlocal total_bytes
                before = _stamp(os.fstat(directory))
                for name in os.listdir(directory):
                    relative = prefix + name
                    info = os.stat(name, dir_fd=directory, follow_symlinks=False)
                    if stat.S_ISLNK(info.st_mode):
                        require(relative in links and info.st_uid == self.owner_uid and info.st_nlink == 1,
                                'SERIAL_TRANSITION_SOURCE_LINK_UNPROVEN')
                        target = os.readlink(name, dir_fd=directory)
                        require(target == original_source_root + '/' + links[relative],
                                'SERIAL_TRANSITION_SOURCE_LINK_CHANGED')
                        with self.parent(target + '/.link-target-boundary'):
                            pass  # The fixed canonical component directory is protected.
                        require(_stamp(info) == _stamp(os.stat(name, dir_fd=directory, follow_symlinks=False))
                                and os.readlink(name, dir_fd=directory) == target,
                                'SERIAL_TRANSITION_SOURCE_LINK_CHANGED')
                        total_bytes += len(target.encode('utf-8'))
                        require(len(rows) < MAX_SOURCE_FILES and total_bytes <= MAX_SOURCE_BYTES,
                                'SERIAL_TRANSITION_SOURCE_LIMIT')
                        if copy_to is not None:
                            self._link_copy(copy_to + '/' + relative, target)
                        rows.append((relative.encode(), f'{relative}\0symlink\0{sha(target.encode())}\n'.encode()))
                        observed_links.add(relative)
                    elif stat.S_ISDIR(info.st_mode):
                        child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                        dir_fd=directory)
                        try:
                            self._directory(os.fstat(child))
                            if copy_to is not None:
                                self.directory(copy_to + '/' + relative)
                            visit(child, relative + '/')
                            require(_stamp(info) == _stamp(os.fstat(child)),
                                    'SERIAL_TRANSITION_SOURCE_CHANGED')
                        finally:
                            os.close(child)
                    else:
                        raw = self.read(logical + '/' + relative, allow_empty=True)
                        total_bytes += len(raw)
                        require(len(rows) < MAX_SOURCE_FILES and total_bytes <= MAX_SOURCE_BYTES,
                                'SERIAL_TRANSITION_SOURCE_LIMIT')
                        require(_stamp(info) == _stamp(os.stat(name, dir_fd=directory, follow_symlinks=False)),
                                'SERIAL_TRANSITION_SOURCE_CHANGED')
                        if copy_to is not None:
                            # A partial prior copy can only gain missing exact
                            # bytes. Existing differing files never get replaced.
                            if raw:
                                self.write(copy_to + '/' + relative, raw, mode=info.st_mode & 0o777)
                            else:
                                self._empty_copy(copy_to + '/' + relative, info.st_mode & 0o777)
                        rows.append((relative.encode(), f'{relative}\0{info.st_mode & 0o777:o}\0{sha(raw)}\n'.encode()))
                require(before == _stamp(os.fstat(directory)), 'SERIAL_TRANSITION_SOURCE_CHANGED')
            visit(root, '')
        require(observed_links == set(links), 'SERIAL_TRANSITION_SOURCE_LINK_MISSING')
        require(rows, 'SERIAL_TRANSITION_SOURCE_EMPTY')
        return sha(b''.join(row for _, row in sorted(rows)))

    def _empty_copy(self, logical, mode):
        existing = self.read(logical, modes={mode}, optional=True, allow_empty=True)
        if existing is not None:
            require(existing == b'', 'SERIAL_TRANSITION_PUBLICATION_CONFLICT')
            return
        with self.parent(logical) as (parent, name):
            descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode, dir_fd=parent)
            try:
                os.fchmod(descriptor, mode)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            os.fsync(parent)

    def _link_copy(self, logical, target):
        with self.parent(logical) as (parent, name):
            try:
                os.symlink(target, name, dir_fd=parent)
                os.fsync(parent)
            except FileExistsError:
                pass
            info = os.stat(name, dir_fd=parent, follow_symlinks=False)
            require(stat.S_ISLNK(info.st_mode) and info.st_uid == self.owner_uid and info.st_nlink == 1
                    and os.readlink(name, dir_fd=parent) == target,
                    'SERIAL_TRANSITION_SOURCE_LINK_COPY_CONFLICT')


def validate_delta(original, target):
    """Only the explicitly selected source and General Runner pool may change."""
    from config import derive_managed_pool_slots
    old, new = copy.deepcopy(original), copy.deepcopy(target)
    require('generalRunnerPool' not in old['consumer'] and 'executionSlots' not in old['consumer'],
            'SERIAL_TRANSITION_ORIGINAL_NOT_SERIAL')
    pool = new['consumer'].get('generalRunnerPool')
    require(isinstance(pool, dict) and set(pool) == {'desiredCapacity'}
            and type(pool['desiredCapacity']) is int and 1 <= pool['desiredCapacity'] <= 32,
            'SERIAL_TRANSITION_TARGET_NOT_POOL')
    # The normal deployment validator still validates both full configurations.
    # This comparison adds a narrow compatibility boundary, not another schema.
    derive_managed_pool_slots(new)
    require(original['environment']['generalRunner']['name'] not in {
        slot['runnerName'] for slot in new['consumer']['executionSlots']},
        'SERIAL_TRANSITION_REGISTRATION_NAME_COLLISION')
    new['consumer'].pop('generalRunnerPool')
    new['consumer'].pop('executionSlots')
    for value in (old, new):
        value['source'].pop('revision', None)
        general = value['environment']['generalRunner']
        for key in ['name', 'scope', 'group', 'poolApp']:
            general.pop(key, None)
    require(old == new, 'SERIAL_TRANSITION_OWNER_INTENT_CHANGED')
    require(original['environment']['generalRunner']['user'] == target['environment']['generalRunner']['user'],
            'SERIAL_TRANSITION_RUNNER_IDENTITY_CHANGED')
    return True


def _paths(config, evidence):
    claim = config['consumer']['paths']['claimRoot']
    parent = str(PurePosixPath(evidence['consumerPath']).parent)
    return {'state': claim + '/' + STATE_NAME, 'gate': claim + '/admission-v1.json',
            'claims': claim + '/publication-v2', 'receipt': parent + '/' + RECEIPT_NAME,
            'consumer': parent + '/' + CONSUMER_NAME}


def _context(files, config, evidence, paths):
    from config import compile_inputs
    required = {'revision', 'consumerDigest', 'consumerPath', 'sourceRoot', 'manifestPath',
                'configPath', 'runs', 'runnerUid'}
    require(set(evidence) == required and REVISION.fullmatch(evidence['revision'])
            and SHA.fullmatch(evidence['consumerDigest']) and type(evidence['runnerUid']) is int
            and evidence['runnerUid'] > 0, 'SERIAL_TRANSITION_ORIGINAL_CONTEXT_INVALID')
    values = compile_inputs(config)
    roots = [values['relay_install_root'] + prefix + evidence['revision']
             for prefix in ['/releases/', '/serial-compat-v1/']]
    require(any(evidence['sourceRoot'] == release + '/reviewed-source'
                and evidence['manifestPath'] == release + '/artifact-manifest.json'
                and evidence['configPath'] == release + '/deployment-config.json' for release in roots)
            and evidence['consumerPath'] in [values['relay_config_root'] + '/consumer.json', paths['consumer']],
            'SERIAL_TRANSITION_ORIGINAL_PATH_BINDING_INVALID')
    consumer = files.read(evidence['consumerPath'], modes={0o644, 0o640, 0o600})
    config_raw = files.read(evidence['configPath'], modes={0o600})
    require(_json(config_raw) == config, 'SERIAL_TRANSITION_ORIGINAL_CONFIG_CHANGED')
    manifest_raw = files.read(evidence['manifestPath'], modes={0o640, 0o600})
    manifest = _json(manifest_raw)
    require(manifest.get('deploymentConfigSha256') == sha(config_raw)
            and all(manifest.get(key) == evidence['revision'] for key in
                    ['commit', 'installedRevision', 'resolvedRevision']),
            'SERIAL_TRANSITION_ORIGINAL_MANIFEST_INVALID')
    original = {key: evidence[key] for key in ['revision', 'consumerDigest', 'sourceRoot',
                                               'manifestPath', 'configPath', 'runs', 'runnerUid']}
    links = config['environment'].get('compatibilityLinks', {})
    require(isinstance(links, dict), 'SERIAL_TRANSITION_SOURCE_LINKS_INVALID')
    original.update(consumerPath=paths['consumer'], consumerSha256=sha(consumer),
                    sourceTreeSha256=files.tree_sha256(evidence['sourceRoot'], source_links=links,
                        original_source_root=roots[0] + '/reviewed-source'),
                    manifestSha256=sha(manifest_raw), configSha256=sha(config_raw),
                    runnerUser=config['environment']['generalRunner']['user'])
    if links:
        original['sourceLinks'] = copy.deepcopy(links)
    claims = {}
    with files.parent(paths['claims'] + '/.claims-boundary') as (directory, _):
        for name in os.listdir(directory):
            require(re.fullmatch(r'[1-9][0-9]*\.json', name), 'SERIAL_TRANSITION_CLAIM_UNPROVEN')
            record = _json(files.read(paths['claims'] + '/' + name, modes={0o600}))
            envelope = record.get('envelope', {})
            run_id = envelope.get('runId')
            require(type(run_id) is int and run_id > 0 and name == f'{run_id}.json'
                    and envelope.get('consumerDigest') == evidence['consumerDigest'],
                    'SERIAL_TRANSITION_CLAIM_UNPROVEN')
            claims[run_id] = {'runId': run_id, 'attemptId': envelope.get('attemptId'),
                              'envelopeSha256': sha(encoded(envelope))}
            # Pending owner-local manual work is outside managed-host lifecycle.
            # Caller validates its original envelope and preserves its intents;
            # it is not a reason to invent host execution or a terminal Outcome.
    require(isinstance(evidence['runs'], list)
            and sorted(claims.values(), key=lambda run: run['runId']) == evidence['runs'],
            'SERIAL_TRANSITION_ORIGINAL_RUN_SET_CHANGED')
    return original, consumer


def _preserved_evidence(evidence, plan):
    return {**evidence, 'consumerPath': plan['paths']['consumer'],
            **{key: plan['original'][key] for key in ['sourceRoot', 'manifestPath', 'configPath']}}


def _freeze(files, original_config, original):
    """Preserve exact original runtime bytes before a same-SHA backend apply."""
    install = '/opt/' + original_config['environment']['namespace']
    parent = install + '/serial-compat-v1'
    destination = parent + '/' + original['revision']
    files.directory(parent)
    files.directory(destination)
    source = destination + '/reviewed-source'
    options = {'source_links': original.get('sourceLinks', {}),
               'original_source_root': install + '/releases/' + original['revision'] + '/reviewed-source'}
    if original['sourceRoot'] != source:
        copied = files.tree_sha256(original['sourceRoot'], copy_to=source, **options)
        require(copied == original['sourceTreeSha256'], 'SERIAL_TRANSITION_SOURCE_CHANGED')
    require(files.tree_sha256(source, **options) == original['sourceTreeSha256'],
            'SERIAL_TRANSITION_PRESERVED_SOURCE_CHANGED')
    paths = {'sourceRoot': source, 'manifestPath': destination + '/artifact-manifest.json',
             'configPath': destination + '/deployment-config.json'}
    for key in ['manifestPath', 'configPath']:
        raw = files.read(original[key], modes={0o600, 0o640})
        files.write(paths[key], raw, mode=0o600)
    return {**original, **paths}


def _binding(config, evidence, host):
    from config import compile_inputs
    values = compile_inputs(config)
    binding = host.inspect_legacy(config)
    require(isinstance(binding, dict) and binding.get('ownWorker') is False
            and type(binding.get('runnerId')) is int and binding['runnerId'] > 0
            and binding.get('runnerName') == config['environment']['generalRunner']['name']
            and binding.get('runnerUid') == evidence['runnerUid']
            and binding.get('scope') == config['environment']['generalRunner'].get('scope', 'repository')
            and binding.get('service') == values.get('relay_general_runner_service_name', 'relay-general-runner.service')
            and binding.get('root') == values['relay_install_root'] + '/general-runner'
            and binding.get('workFolder') == values['relay_state_root'] + '/general-runner/work'
            and SHA.fullmatch(binding.get('registrationSha256', ''))
            and SHA.fullmatch(binding.get('unitSha256', '')),
            'SERIAL_TRANSITION_LEGACY_OWNERSHIP_UNPROVEN')
    return {key: value for key, value in binding.items() if key != 'ownWorker'}


def _remote(github, binding, *, absent=False, idle=False):
    remote = github.observe_legacy(binding)
    if remote is None:
        require(absent, 'SERIAL_TRANSITION_LEGACY_DISAPPEARED')
        return None
    require(remote.get('id') == binding['runnerId'] and remote.get('name') == binding['runnerName'],
            'SERIAL_TRANSITION_REMOTE_BINDING_CHANGED')
    require(not idle or remote.get('busy') is False, 'SERIAL_TRANSITION_LEGACY_BUSY')
    return remote


def inspect(original_config, target_config, evidence, *, target_consumer_digest, host, github, gate,
            root=Path('/'), owner_uid=0):
    """Read-only preflight. Original envelope validation is performed by caller."""
    require(isinstance(target_consumer_digest, str) and SHA.fullmatch(target_consumer_digest),
            'SERIAL_TRANSITION_TARGET_DIGEST_INVALID')
    validate_delta(original_config, target_config)
    files = ProtectedFiles(root, owner_uid)
    paths = _paths(original_config, evidence)
    original, _ = _context(files, original_config, evidence, paths)
    binding = _binding(original_config, evidence, host)
    retained_raw = files.read(paths['state'], modes={0o600}, optional=True)
    retained = _json(retained_raw) if retained_raw is not None else None
    reserved_removal = retained is not None and retained.get('phase') in ['remove-intent', 'retired']
    if reserved_removal:
        receipt_raw = files.read(paths['receipt'], modes={0o644})
        receipt = _json(receipt_raw)
        require(retained.get('version') == 1
                and retained['plan']['binding'] == binding and retained['plan']['original'] == original
                and retained['plan']['target'] == {'consumerDigest': target_consumer_digest}
                and retained['plan']['targetConfigSha256'] == sha(encoded(target_config))
                and sha(receipt_raw) == retained.get('receiptSha256')
                and receipt.get('operationId') == retained.get('operationId')
                and receipt.get('repository') == original_config['consumer']['repository']
                and receipt.get('namespace') == original_config['environment']['namespace']
                and {key: value for key, value in receipt['original'].items() if key != 'gateSha256'} == original
                and receipt.get('target') == {'consumerDigest': target_consumer_digest}
                and sha(files.read(paths['gate'], modes={0o600})) == receipt['original']['gateSha256'],
                'SERIAL_TRANSITION_REMOVAL_RESERVATION_UNPROVEN')
    _remote(github, binding, absent=reserved_removal)
    status = gate('status')
    require(status.get('phase') in ['open', 'quiesced', 'drained', 'applying']
            and status.get('unknown') == [], 'SERIAL_TRANSITION_ADMISSION_UNPROVEN')
    return {'version': 1, 'repository': original_config['consumer']['repository'],
            'namespace': original_config['environment']['namespace'], 'original': original,
            'target': {'consumerDigest': target_consumer_digest},
            'binding': binding, 'paths': paths,
            'targetConfigSha256': sha(encoded(target_config))}


def prepare(original_config, target_config, evidence, *, operation_id, target_revision,
            target_consumer_digest, services, host, github, gate, root=Path('/'), owner_uid=0):
    """Reserve, drain and snapshot OLD context; publish immutable compatibility."""
    require(str(uuid.UUID(operation_id)) == operation_id and REVISION.fullmatch(target_revision),
            'SERIAL_TRANSITION_OPERATION_INVALID')
    files = ProtectedFiles(root, owner_uid)
    state_path = _paths(original_config, evidence)['state']
    raw = files.read(state_path, modes={0o600}, optional=True)
    state = _json(raw) if raw is not None else None
    if state and state.get('phase') in PHASES - {'reserved'}:
        require(state.get('operationId') == operation_id and state.get('targetRevision') == target_revision
                and state.get('services') == services
                and state['plan']['targetConfigSha256'] == sha(encoded(target_config))
                and state['plan']['target']['consumerDigest'] == target_consumer_digest,
                'SERIAL_TRANSITION_OPERATION_CONFLICT')
        saved_evidence = _preserved_evidence(evidence, state['plan'])
        original, _ = _context(files, original_config, saved_evidence, state['plan']['paths'])
        require(original == state['plan']['original'], 'SERIAL_TRANSITION_ORIGINAL_CONTEXT_CHANGED')
        require(sha(files.read(state['plan']['paths']['receipt'], modes={0o644})) == state['receiptSha256'],
                'SERIAL_TRANSITION_RECEIPT_CHANGED')
        return state
    effective_evidence = (_preserved_evidence(evidence, state['plan'])
                          if state and '/serial-compat-v1/' in state['plan']['original']['sourceRoot'] else evidence)
    plan = inspect(original_config, target_config, effective_evidence, target_consumer_digest=target_consumer_digest,
                   host=host, github=github,
                   gate=gate, root=root, owner_uid=owner_uid)
    if state:
        require(state.get('operationId') == operation_id and state.get('plan') == plan
                and state.get('targetRevision') == target_revision and state.get('services') == services
                and state.get('phase') in PHASES, 'SERIAL_TRANSITION_OPERATION_CONFLICT')
    else:
        require(gate('status').get('phase') == 'open', 'SERIAL_TRANSITION_EXISTING_GATE_CLOSED')
        state = {'version': 1, 'operationId': operation_id, 'targetRevision': target_revision,
                 'phase': 'reserved', 'plan': plan, 'services': copy.deepcopy(services)}
        files.write(state_path, encoded(state) + b'\n')
    status = gate('status')
    if status.get('phase') == 'open':
        gate('quiesce', '--operation', operation_id, '--target', target_revision)
        status = gate('status', '--operation', operation_id)
    require(status.get('operationId') == operation_id and status.get('target') == target_revision,
            'SERIAL_TRANSITION_OPERATION_CONFLICT')
    if status.get('phase') != 'applying':
        gate('drain', '--operation', operation_id, '--timeout', '1800')
        status = gate('status', '--operation', operation_id)
    require(status.get('active') == [] and status.get('unknown') == [],
            'SERIAL_TRANSITION_NOT_DRAINED')
    if status.get('phase') != 'applying':
        gate('phase', '--operation', operation_id, '--phase', 'applying')
    gate('snapshot', '--operation', operation_id, services=services)
    original, consumer = _context(files, original_config, effective_evidence, plan['paths'])
    require(original == plan['original'], 'SERIAL_TRANSITION_ORIGINAL_CONTEXT_CHANGED')
    files.write(plan['paths']['consumer'], consumer, mode=0o644)
    frozen_original = _freeze(files, original_config, original)
    # Only this new migration metadata changes paths. Historical snapshots,
    # admissions, envelopes, journals and digest bytes stay untouched.
    state.setdefault('observedOriginal', copy.deepcopy(original))
    plan['original'] = frozen_original
    state['plan'] = plan
    files.write(state_path, encoded(state) + b'\n', replace=True)
    receipt = {key: copy.deepcopy(plan[key]) for key in ['version', 'repository', 'namespace', 'original', 'target']}
    receipt['operationId'] = operation_id
    receipt['original']['gateSha256'] = sha(files.read(plan['paths']['gate'], modes={0o600}))
    files.write(plan['paths']['receipt'], encoded(receipt) + b'\n', mode=0o644)
    state['phase'] = 'prepared'
    state['receiptSha256'] = sha(encoded(receipt) + b'\n')
    files.write(state_path, encoded(state) + b'\n', replace=True)
    return state


def advance(original_config, target_config, evidence, *, host, github, gate,
            root=Path('/'), owner_uid=0):
    """Stop an idle owned legacy runner; remove remotely only after target-ready.

    Parent installs/reconciles the new distinct pool while this returns stopped.
    An interrupted stop/remove is observed, never blindly invoked a second time.
    Both native adapters must recheck their exact retained binding themselves.
    """
    files = ProtectedFiles(root, owner_uid)
    paths = _paths(original_config, evidence)
    state = _json(files.read(paths['state'], modes={0o600}))
    validate_delta(original_config, target_config)
    require(state.get('phase') in PHASES - {'reserved'} and state.get('version') == 1
            and state['plan']['targetConfigSha256'] == sha(encoded(target_config)),
            'SERIAL_TRANSITION_OPERATION_UNPROVEN')
    require(sha(files.read(paths['receipt'], modes={0o644})) == state['receiptSha256'],
            'SERIAL_TRANSITION_RECEIPT_CHANGED')
    receipt = _json(files.read(paths['receipt'], modes={0o644}))
    require(sha(files.read(paths['gate'], modes={0o600})) == receipt['original']['gateSha256'],
            'SERIAL_TRANSITION_ORIGINAL_GATE_CHANGED')
    saved_evidence = _preserved_evidence(evidence, state['plan'])
    original, _ = _context(files, original_config, saved_evidence, paths)
    require(original == state['plan']['original'], 'SERIAL_TRANSITION_ORIGINAL_CONTEXT_CHANGED')
    status = gate('status', '--operation', state['operationId'])
    require(status.get('phase') == 'applying' and status.get('active') == []
            and status.get('unknown') == [], 'SERIAL_TRANSITION_NOT_DRAINED')
    binding = state['plan']['binding']
    require(_binding(original_config, evidence, host) == binding,
            'SERIAL_TRANSITION_LEGACY_BINDING_CHANGED')
    if state['phase'] in ['stopped', 'target-ready', 'remove-intent', 'retired']:
        require(host.legacy_stopped(binding), 'SERIAL_TRANSITION_LEGACY_STOP_STATE_CHANGED')

    def save(phase):
        state['phase'] = phase
        files.write(paths['state'], encoded(state) + b'\n', replace=True)

    if state['phase'] in ['prepared', 'stop-intent']:
        _remote(github, binding, idle=True)
        if not host.legacy_stopped(binding):
            require(state['phase'] == 'prepared', 'SERIAL_TRANSITION_STOP_UNCERTAIN_INSPECT_BEFORE_RETRY')
            save('stop-intent')
            host.stop_legacy(binding)
        require(host.legacy_stopped(binding), 'SERIAL_TRANSITION_STOP_UNCERTAIN_INSPECT_BEFORE_RETRY')
        save('stopped')
    if state['phase'] == 'stopped':
        if not host.pool_ready(target_config):
            return state
        save('target-ready')
    if state['phase'] in ['target-ready', 'remove-intent']:
        require(host.legacy_stopped(binding) and host.pool_ready(target_config),
                'SERIAL_TRANSITION_TARGET_READINESS_LOST')
        remote = _remote(github, binding, absent=state['phase'] == 'remove-intent', idle=True)
        if remote is not None:
            require(state['phase'] == 'target-ready', 'SERIAL_TRANSITION_REMOVE_UNCERTAIN_INSPECT_BEFORE_RETRY')
            save('remove-intent')
            github.remove_legacy(binding)
            require(_remote(github, binding, absent=True) is None,
                    'SERIAL_TRANSITION_REMOVE_UNCERTAIN_INSPECT_BEFORE_RETRY')
        save('retired')
    return state


def write_new_gate(original_config, target_config, evidence, *, operation_id, target_revision,
                   target_consumer_digest, services, root=Path('/'), owner_uid=0):
    """Create the separate target gate from actual target service observations.

    This is a new execution context, not a conversion of the original snapshot.
    The caller observes services under the host operation lock.
    """
    validate_delta(original_config, target_config)
    require(str(uuid.UUID(operation_id)) == operation_id and REVISION.fullmatch(target_revision)
            and SHA.fullmatch(target_consumer_digest), 'SERIAL_TRANSITION_OPERATION_INVALID')
    files = ProtectedFiles(root, owner_uid)
    paths = _paths(original_config, evidence)
    state = _json(files.read(paths['state'], modes={0o600}))
    require(state.get('operationId') == operation_id and state.get('targetRevision') == target_revision
            and state.get('phase') in PHASES - {'reserved'}
            and state['plan']['targetConfigSha256'] == sha(encoded(target_config))
            and state['plan']['target']['consumerDigest'] == target_consumer_digest,
            'SERIAL_TRANSITION_OPERATION_UNPROVEN')
    receipt_raw = files.read(paths['receipt'], modes={0o644})
    require(sha(receipt_raw) == state['receiptSha256'], 'SERIAL_TRANSITION_RECEIPT_CHANGED')
    require(sha(files.read(paths['gate'], modes={0o600})) == _json(receipt_raw)['original']['gateSha256'],
            'SERIAL_TRANSITION_ORIGINAL_GATE_CHANGED')
    names = {'reviewer', 'production', 'general'} | {
        'slot-' + slot['id'] for slot in target_config['consumer']['executionSlots'] if slot['id'] != 'primary'}
    require(isinstance(services, dict), 'SERIAL_TRANSITION_TARGET_SNAPSHOT_INVALID')
    if 'manualOutcome' in services:
        names.add('manualOutcome')
    require(set(services) == names, 'SERIAL_TRANSITION_TARGET_SNAPSHOT_INVALID')
    for name, service in services.items():
        require(isinstance(service, dict) and set(service) == {'active', 'enabled', 'load'}
                and type(service['active']) is bool
                and service['enabled'] in ['enabled', 'enabled-runtime', 'disabled']
                and service['load'] in ['loaded', 'not-found']
                and (service['load'] != 'not-found' or
                     service == {'active': False, 'enabled': 'disabled', 'load': 'not-found'}),
                'SERIAL_TRANSITION_TARGET_SNAPSHOT_INVALID')
    gate = {'version': 1, 'consumerDigest': target_consumer_digest, 'phase': 'applying',
            'operationId': operation_id, 'target': target_revision,
            'previousActive': copy.deepcopy(services), 'verifiedRevision': None}
    gate_path = original_config['consumer']['paths']['claimRoot'] + '/admission-pool-v1.json'
    existing = files.read(gate_path, modes={0o600}, optional=True)
    if existing is not None:
        retained = _json(existing)
        require(set(retained) == set(gate) and retained.get('version') == 1
                and retained.get('consumerDigest') == target_consumer_digest
                and retained.get('phase') == 'applying' and retained.get('operationId') == operation_id
                and retained.get('target') == target_revision and retained.get('verifiedRevision') is None,
                'SERIAL_TRANSITION_TARGET_GATE_CONFLICT')
        # Validate the retained wire shape using the normal snapshot rules
        # without replacing its first activation intent with later observations.
        retained_services = retained.get('previousActive')
        retained_names = names - {'manualOutcome'}
        if isinstance(retained_services, dict) and 'manualOutcome' in retained_services:
            retained_names.add('manualOutcome')
        require(isinstance(retained_services, dict) and set(retained_services) == retained_names,
                'SERIAL_TRANSITION_TARGET_SNAPSHOT_INVALID')
        for service in retained_services.values():
            require(isinstance(service, dict) and set(service) == {'active', 'enabled', 'load'}
                    and type(service['active']) is bool
                    and service['enabled'] in ['enabled', 'enabled-runtime', 'disabled']
                    and service['load'] in ['loaded', 'not-found']
                    and (service['load'] != 'not-found' or
                         service == {'active': False, 'enabled': 'disabled', 'load': 'not-found'}),
                    'SERIAL_TRANSITION_TARGET_SNAPSHOT_INVALID')
        return retained
    files.write(gate_path, encoded(gate) + b'\n')
    return gate
