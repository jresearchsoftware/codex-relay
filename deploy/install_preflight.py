"""Private install staging, bounded revalidation and pre-cutover abort.

The existing host/pool mutexes remain the operation authority. A stage receipt
is disposable evidence, not an admission, installation record or recovery log.
Only a still-unmodified old installation can have its original open gate
restored. Once active installation starts, the original forward-recovery
contract applies instead.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import uuid


def require(value, code):
    if not value:
        raise RuntimeError('INSTALL_PREFLIGHT_' + code)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode() + b'\n'


def protected(path, *, root=Path('/'), owner_uid=0, directory=False, optional=False):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts, 'PATH_INVALID')
    actual = root / path.relative_to('/')
    try:
        info = actual.lstat()
    except FileNotFoundError:
        require(optional, 'PREREQUISITE_MISSING')
        # An absent destination still needs a safe existing parent.
        parent = actual.parent
        while not parent.exists():
            parent = parent.parent
        protected('/' + str(parent.relative_to(root)), root=root, owner_uid=owner_uid, directory=True)
        return actual, None
    for parent in [actual.parent, *actual.parent.parents]:
        if not parent.is_relative_to(root):
            break
        item = parent.lstat()
        require(stat.S_ISDIR(item.st_mode) and item.st_uid == owner_uid and not item.st_mode & 0o022,
                'PARENT_UNSAFE')
        if parent == root:
            break
    require(info.st_uid == owner_uid and not info.st_mode & 0o022
            and (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode) and info.st_nlink == 1),
            'RESOURCE_UNSAFE')
    return actual, info


def read(path, **options):
    actual, before = protected(path, **options)
    require(before.st_size <= 32 * 1024 * 1024, 'RESOURCE_SIZE')
    descriptor = os.open(actual, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        raw = b''
        while len(raw) <= before.st_size:
            part = os.read(descriptor, min(1024 * 1024, before.st_size + 1 - len(raw)))
            if not part:
                break
            raw += part
        after = os.fstat(descriptor)
        fields = ['st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns']
        require(len(raw) == before.st_size and all(getattr(before, key) == getattr(after, key)
                == getattr(actual.lstat(), key) for key in fields), 'INPUT_CHANGED')
        return raw
    finally:
        os.close(descriptor)


def write_private(path, raw, *, replace=False):
    temporary = path.with_name('.' + path.name + '-' + str(uuid.uuid4()))
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(descriptor, 'wb') as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        require(replace or not path.exists(), 'EVIDENCE_ALREADY_EXISTS')
        os.replace(temporary, path)
        descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def critical_state(values, *, root=Path('/'), owner_uid=0, consumer_restore_required=False):
    """Static old bindings only; normal attempt completion is intentionally allowed."""
    options = {'root': root, 'owner_uid': owner_uid}
    install = Path(values['relay_install_root'])
    config = Path(values['relay_config_root'])
    consumer = Path(values['relay_consumer_config_path'])
    result = {}

    def observe(path, *, metadata=False, directory=False, retained_metadata=False):
        actual = root / path.relative_to('/')
        if not actual.exists() and not actual.is_symlink():
            result[str(path)] = None
            return
        info = actual.lstat()
        if stat.S_ISLNK(info.st_mode):
            require(info.st_uid == owner_uid, 'LINK_UNSAFE')
            result[str(path)] = {'link': os.readlink(actual), 'uid': info.st_uid,
                                 'dev': info.st_dev, 'ino': info.st_ino}
        else:
            if not retained_metadata:
                _, info = protected(path, directory=directory, **options)
            result[str(path)] = {'mode': stat.S_IMODE(info.st_mode), 'uid': info.st_uid, 'gid': info.st_gid}
            # Only the canonical consumer may undergo the planned authenticated
            # repair. Pin every other old inode and private-file metadata without
            # reading credential bytes. Directory mtime changes are expected when
            # private stage/backup artifacts are created beside old bindings.
            planned_consumer_repair = path == consumer and consumer_restore_required
            if not planned_consumer_repair:
                result[str(path)].update(dev=info.st_dev, ino=info.st_ino)
                if not directory:
                    result[str(path)].update(size=info.st_size, mtimeNs=info.st_mtime_ns, ctimeNs=info.st_ctime_ns)
            if not directory and (not metadata or path == consumer and not planned_consumer_repair):
                result[str(path)]['sha256'] = hashlib.sha256(read(path, **options)).hexdigest()

    observe(install, metadata=True, directory=True)
    observe(config, metadata=True, directory=True)
    current = root / install.relative_to('/') / 'current'
    observe(install / 'current')
    if current.is_symlink():
        release = current.resolve(strict=True)
        release_logical = Path('/') / release.relative_to(root)
        require(release_logical.parent == install / 'releases' and re.fullmatch('[0-9a-f]{40}', release.name),
                'OLD_RELEASE_UNPROVEN')
        protected(release_logical, directory=True, **options)
        observe(release_logical, metadata=True, directory=True)
        for name in ['artifact-manifest.json', 'deployment-config.json', 'bin/reviewer-mcp-http',
                     'reviewed-source/.relay-source.json']:
            observe(release_logical / name)
        source = release / 'reviewed-source'
        observe(release_logical / 'reviewed-source', metadata=True, directory=True)
        count = 0
        for directory, dirs, files in os.walk(source, followlinks=False):
            for name in dirs[:]:
                path = Path(directory) / name
                if path.is_symlink():
                    observe(Path('/') / path.relative_to(root)); dirs.remove(name)
                else:
                    observe(Path('/') / path.relative_to(root), metadata=True, directory=True)
            for name in sorted(files):
                observe(Path('/') / (Path(directory) / name).relative_to(root))
                count += 1
                require(count <= 10000, 'OLD_SOURCE_SIZE')
    for path in sorted((root / install.relative_to('/')).glob('*')):
        if path.is_file() or path.is_symlink():
            observe(Path('/') / path.relative_to(root))
    config_actual = root / config.relative_to('/')
    if config_actual.exists():
        for path in sorted(config_actual.iterdir()):
            if re.match(r'consumer-(?:drift-)?before-|[.]', path.name):
                continue
            logical = Path('/') / path.relative_to(root)
            if path.is_dir() and not path.is_symlink():
                # Retained credential/TLS leaves may legitimately belong to the
                # runtime actor. Observe metadata only; owning preflight validates
                # their permissions and contents through its existing interfaces.
                observe(logical, metadata=True, directory=True, retained_metadata=True)
                count = 0
                for directory, dirs, files in os.walk(path, followlinks=False):
                    for name in [*dirs, *files]:
                        nested = Path(directory) / name
                        observe(Path('/') / nested.relative_to(root), metadata=True,
                                directory=nested.is_dir() and not nested.is_symlink(), retained_metadata=True)
                        count += 1
                        require(count <= 10000, 'OLD_CONFIG_SIZE')
                continue
            # Credential metadata is sufficient; never read secret material.
            secret = path.suffix in ['.pem', '.key', '.env'] or any(word in path.name for word in ['token', 'credential', 'secret'])
            observe(logical, metadata=secret or logical == consumer)
    namespace = values['relay_namespace']
    units = set()
    for name, value in values.items():
        if name.endswith(('_service_name', '_timer_name')) and isinstance(value, str):
            units.add(value)
    units.update([namespace + '-relay-manual-outcome.socket', namespace + '-relay-manual-outcome@.service'])
    system = root / 'etc/systemd/system'
    if system.exists():
        units.update(path.name for path in system.glob(namespace + '-*') if not path.is_dir())
    for unit in sorted(units):
        require(re.fullmatch('[A-Za-z0-9@_.-]+', unit), 'UNIT_INVALID')
        observe(Path('/etc/systemd/system') / unit)
    sudoers = root / 'etc/sudoers.d'
    if sudoers.exists():
        for path in sorted(sudoers.glob(namespace + '*')):
            observe(Path('/') / path.relative_to(root))
    return result


def observe_predispatch_service_intent(values, *, service_probe=None):
    """Read the bounded systemd activity shape retained by the admission snapshot."""
    namespace = values['relay_namespace']
    units = [('reviewer', values['relay_reviewer_service_name']),
             ('production', values['relay_production_runner_service_name']),
             ('general', values['relay_general_runner_service_name']),
             ('manualOutcome', namespace + '-relay-manual-outcome.socket')]
    slots = values.get('relay_additional_execution_slots', [])
    require(isinstance(slots, list), 'PREDISPATCH_BRIDGE_ABORT_ACTIVITY_UNPROVEN')
    for slot in slots:
        require(isinstance(slot, dict) and isinstance(slot.get('relay_execution_slot'), str)
                and re.fullmatch('[a-z][a-z0-9-]{0,31}', slot['relay_execution_slot'])
                and isinstance(slot.get('relay_runner_service_name'), str),
                'PREDISPATCH_BRIDGE_ABORT_ACTIVITY_UNPROVEN')
        units.append(('slot-' + slot['relay_execution_slot'], slot['relay_runner_service_name']))
    result = {}
    for name, unit in units:
        require(isinstance(unit, str) and re.fullmatch('[A-Za-z0-9@_.-]+', unit),
                'PREDISPATCH_BRIDGE_ABORT_ACTIVITY_UNPROVEN')
        try:
            process = (service_probe(unit) if service_probe else subprocess.run(
                ['/bin/systemctl', 'show', unit,
                 '--property=MainPID,ExecMainStartTimestampMonotonic,ActiveState,SubState,UnitFileState,LoadState,NeedDaemonReload'],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=30))
            require(type(process.returncode) is int and isinstance(process.stdout, str),
                    'PREDISPATCH_BRIDGE_ABORT_ACTIVITY_UNPROVEN')
            properties = dict(line.split('=', 1) for line in process.stdout.splitlines() if '=' in line)
            active, load, enabled = (properties.get('ActiveState'), properties.get('LoadState'),
                                     properties.get('UnitFileState', 'disabled'))
            require(active in ['active', 'inactive', 'failed'] and load in ['loaded', 'not-found']
                    and (load == 'not-found' or enabled in ['enabled', 'enabled-runtime', 'disabled']),
                    'PREDISPATCH_BRIDGE_ABORT_ACTIVITY_UNPROVEN')
            if active == 'active':
                require(process.returncode == 0
                        and properties.get('SubState') == ('listening' if name == 'manualOutcome' else 'running')
                        and (name == 'manualOutcome' or enabled in ['enabled', 'enabled-runtime']
                             and re.fullmatch('[1-9][0-9]*', properties.get('MainPID', ''))
                             and re.fullmatch('[1-9][0-9]*', properties.get('ExecMainStartTimestampMonotonic', ''))),
                        'PREDISPATCH_BRIDGE_ABORT_ACTIVITY_UNPROVEN')
            if name == 'manualOutcome' and load == 'not-found':
                require(active == 'inactive' and properties.get('SubState') == 'dead'
                        and enabled in ['not-found', 'disabled'], 'PREDISPATCH_BRIDGE_ABORT_ACTIVITY_UNPROVEN')
            result[name] = {'active': active == 'active',
                            'enabled': enabled if enabled in ['enabled', 'enabled-runtime', 'disabled'] else 'disabled',
                            'load': load}
        except (OSError, subprocess.SubprocessError, KeyError, TypeError, ValueError):
            require(False, 'PREDISPATCH_BRIDGE_ABORT_ACTIVITY_UNPROVEN')
    if result.get('manualOutcome') == {'active': False, 'enabled': 'disabled', 'load': 'not-found'}:
        del result['manualOutcome']
    return result


def verify_predispatch_bridge_abort(snapshot, request, values, *, operation, target, root=Path('/'), owner_uid=0,
                                    gate=None, service_probe=None):
    """Reopen the old gate only before switch and after retained service intent is revalidated."""
    bridge = snapshot.get('predispatchBridge')
    keys = {'version', 'operationId', 'target', 'previousRevision', 'runId', 'attemptId', 'authorizationId',
            'predispatchBinding', 'sourceIdentity', 'stageReceiptSha256', 'consumerSha256', 'writerWrapperSha256'}
    require(isinstance(bridge, dict) and bridge.keys() == keys and bridge['version'] == 1
            and bridge['operationId'] == operation and bridge['target'] == target
            and re.fullmatch('[a-f0-9]{40}', bridge.get('previousRevision', ''))
            and type(bridge.get('runId')) is int and bridge['runId'] > 0
            and bridge.get('attemptId') == 'run-' + str(bridge['runId'])
            and type(bridge.get('authorizationId')) is int and bridge['authorizationId'] > 0
            and bridge.get('sourceIdentity', {}).get('revision') == target
            and all(re.fullmatch('[a-f0-9]{64}', bridge.get(key, '') or '') for key in
                    ['stageReceiptSha256', 'consumerSha256', 'writerWrapperSha256']), 'PREDISPATCH_BRIDGE_ABORT_UNPROVEN')
    original = bridge['predispatchBinding']
    original_keys = {'operation', 'repository', 'runId', 'attemptId', 'issueNumber', 'step', 'executionSlot',
                     'readyEventId', 'branch', 'head', 'authorityDigest', 'recordDigest'}
    optional_binding_keys = {'readyRemovalEventId', 'outcomeCommentId', 'outcomeCommentNumber',
                             'outcomeBodySha256', 'outcomeWriterId', 'outcomeCommentCreatedAt'}
    require(isinstance(original, dict) and original_keys <= original.keys()
            and original.keys() <= original_keys | optional_binding_keys
            and request.get('predispatchBinding') == original
            and original.get('operation') == 'finalize-predispatch'
            and original.get('runId') == bridge['runId'] and original.get('attemptId') == bridge['attemptId']
            and re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', original.get('repository', ''))
            and all(type(original.get(key)) is int and original[key] > 0 for key in ['issueNumber', 'step', 'readyEventId'])
            and isinstance(original.get('executionSlot'), str)
            and re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', original['executionSlot'])
            and re.fullmatch('[a-f0-9]{40}', original.get('head', ''))
            and re.fullmatch('[a-f0-9]{64}', original.get('authorityDigest', ''))
            and re.fullmatch('[a-f0-9]{64}', original.get('recordDigest', '')), 'PREDISPATCH_BRIDGE_ABORT_UNPROVEN')
    install = Path(values['relay_install_root'])
    current = root / install.relative_to('/') / 'current'
    require(current.is_symlink() and Path(os.readlink(current)).name == bridge['previousRevision'],
            'PREDISPATCH_BRIDGE_ABORT_AFTER_SWITCH')
    require(isinstance(gate, dict) and (gate.get('previousActive') is None
            or isinstance(gate.get('previousActive'), dict)), 'PREDISPATCH_BRIDGE_ABORT_ACTIVITY_UNPROVEN')
    previous_active = gate['previousActive']
    if previous_active is not None:
        require(isinstance(previous_active, dict)
                and observe_predispatch_service_intent(values, service_probe=service_probe) == previous_active,
                'PREDISPATCH_BRIDGE_ABORT_ACTIVITY_UNPROVEN')
    stage = Path(request['stage'])
    receipt_raw = read(str(stage / 'receipt.json'), root=root, owner_uid=owner_uid)
    require(hashlib.sha256(receipt_raw).hexdigest() == bridge['stageReceiptSha256'], 'PREDISPATCH_BRIDGE_ABORT_UNPROVEN')
    repository = original['repository']
    run_id = bridge['runId']
    claim = Path(values['relay_writer_claim_root'])
    store = claim / 'publication-v2'
    paths = [store / (str(run_id) + '.json'), store / 'repositories' / repository / (str(run_id) + '.json')]
    options = {'root': root, 'owner_uid': owner_uid}
    records = []
    for path in paths:
        _, info = protected(str(path), optional=True, **options)
        if info is not None:
            records.append(read(str(path), **options))
    require(len(records) == 1, 'PREDISPATCH_BRIDGE_ABORT_ORIGINAL_CHANGED')
    raw = records[0]
    try:
        record = json.loads(raw)
    except (ValueError, TypeError):
        require(False, 'PREDISPATCH_BRIDGE_ABORT_ORIGINAL_CHANGED')
    envelope = record.get('envelope') if isinstance(record, dict) else None
    require(isinstance(envelope, dict) and 'predispatchRecovery' not in record
            and envelope.get('repository') == repository and envelope.get('runId') == run_id
            and envelope.get('attemptId') == bridge['attemptId'] and envelope.get('issueNumber') == original['issueNumber']
            and envelope.get('step') == original['step'] and envelope.get('executionSlot', 'primary') == original.get('executionSlot', 'primary')
            and envelope.get('readyEventId') == original['readyEventId'] and envelope.get('branch') == original['branch']
            and envelope.get('startHead') == original['head'] and envelope.get('authorityDigest') == original['authorityDigest']
            and envelope.get('consumerDigest') == json.loads(base64.b64decode(snapshot['gate'], validate=True)).get('consumerDigest')
            and record.get('readyConsumption', {}).get('status') == 'uncertain'
            and record.get('readyConsumption', {}).get('code') == 'READY_EVENT_REPLACED'
            and record.get('controllerLifecycle') == {'version': 1, 'status': 'complete',
                'child': 'not_started', 'containment': 'not_required'}
            and record.get('outcome', {}).get('status') == 'BLOCKED'
            and not record.get('publicationIntent') and not record.get('publishedHead') and not record.get('finalHead')
            and not record.get('execution'), 'PREDISPATCH_BRIDGE_ABORT_ORIGINAL_CHANGED')
    program = ('import{createHash}from"node:crypto";let raw="";for await(const chunk of process.stdin)raw+=chunk;'
               'const value=JSON.parse(raw);process.stdout.write(createHash("sha256").update(JSON.stringify(value)).digest("hex"));')
    try:
        checked = subprocess.run(['/usr/bin/node', '--input-type=module', '-e', program], input=raw,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=30,
            env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'})
        require(checked.returncode == 0 and checked.stdout.decode() == original['recordDigest'],
                'PREDISPATCH_BRIDGE_ABORT_ORIGINAL_CHANGED')
    except (OSError, UnicodeError, subprocess.SubprocessError):
        require(False, 'PREDISPATCH_BRIDGE_ABORT_ORIGINAL_CHANGED')


def remote(request, *, root=Path('/'), owner_uid=0, service_probe=None):
    values, action = request['values'], request['action']
    operation, target = request['operation'], request['target']
    require(str(uuid.UUID(operation)) == operation and re.fullmatch('[0-9a-f]{40}', target), 'BINDING_INVALID')
    stage = Path(request['stage'])
    reinstall = request.get('reinstall', False)
    require(type(reinstall) is bool, 'STAGE_BINDING_INVALID')
    stage_parent = (Path(values['relay_install_root']).parent / ('.' + values['relay_namespace'] + '-staging')
                    if reinstall else Path(values['relay_release_root']))
    require(stage == stage_parent / ('.stage-' + operation), 'STAGE_BINDING_INVALID')
    options = {'root': root, 'owner_uid': owner_uid}
    if action == 'create':
        parent, _ = protected(str(stage.parent), directory=True, optional=True, **options)
        # Fresh installations may lack both roots; only root-owned safe parents
        # are materialized, and current/active state is never created here.
        parent.mkdir(parents=True, exist_ok=True, mode=0o700 if reinstall else 0o755)
        protected(str(stage.parent), directory=True, **options)
        require(not reinstall or stat.S_IMODE(parent.stat().st_mode) & 0o077 == 0, 'STAGE_PARENT_NOT_PRIVATE')
        actual = root / stage.relative_to('/')
        preserved = False
        if actual.exists() or actual.is_symlink():
            _, previous = protected(str(stage), directory=True, **options)
            require(stat.S_IMODE(previous.st_mode) == 0o700, 'STAGE_UNSAFE')
            lease = actual / 'writer-lock.json'
            if lease.exists() or lease.is_symlink():
                _, info = protected(str(stage / lease.name), **options)
                require(stat.S_IMODE(info.st_mode) == 0o600 and info.st_gid == owner_uid
                        and info.st_size <= 4096, 'STAGE_WRITER_GUARD_UNPROVEN')

                def unique(pairs):
                    value = {}
                    for key, item in pairs:
                        require(key not in value, 'STAGE_WRITER_GUARD_UNPROVEN')
                        value[key] = item
                    return value

                try:
                    value = json.loads(read(str(stage / lease.name), **options), object_pairs_hook=unique)
                except ValueError:
                    require(False, 'STAGE_WRITER_GUARD_UNPROVEN')
                require(isinstance(value, dict) and set(value) == {'version', 'pid', 'startTicks', 'fd',
                    'lockDev', 'lockIno', 'lockMode', 'lockGid', 'operationId', 'target', 'consumerDigest'}
                    and type(value['version']) is int and value['version'] == 1
                    and all(type(value[key]) is int and value[key] > 0
                            for key in ['pid', 'startTicks', 'fd', 'lockIno'])
                    and all(type(value[key]) is int and value[key] >= 0
                            for key in ['lockDev', 'lockMode', 'lockGid'])
                    and value['operationId'] == operation and value['target'] == target
                    and isinstance(value['consumerDigest'], str)
                    and re.fullmatch('[a-f0-9]{64}', value['consumerDigest']), 'STAGE_WRITER_GUARD_UNPROVEN')
                process = Path('/proc') / str(value['pid'])
                try:
                    with (process / 'stat').open('rb') as stream:
                        raw = stream.read(4097)
                    require(len(raw) <= 4096 and process.stat().st_uid == owner_uid,
                            'STAGE_WRITER_GUARD_UNPROVEN')
                    fields = raw.rsplit(b')', 1)[1].split()
                    require(len(fields) > 19 and fields[19].isdigit(), 'STAGE_WRITER_GUARD_UNPROVEN')
                    require(int(fields[19]) != value['startTicks'] or fields[0] in [b'Z', b'X', b'x'],
                            'STAGE_WRITER_GUARD_LIVE')
                except FileNotFoundError:
                    require(not process.exists(), 'STAGE_WRITER_GUARD_UNPROVEN')
                # A dead PID alone cannot exclude an inherited flock. Inspect
                # the actual kernel lock table before moving its former source.
                with Path('/proc/locks').open('rb') as stream:
                    locks = stream.read(1024 * 1024 + 1)
                require(len(locks) <= 1024 * 1024, 'STAGE_WRITER_GUARD_UNPROVEN')
                for line in locks.splitlines():
                    match = re.fullmatch(rb'\d+:\s+(?:->\s+)?(?:POSIX|FLOCK|OFDLCK)\s+(?:ADVISORY|MANDATORY)\s+'
                        rb'(?:READ|WRITE)\s+-?\d+\s+([a-fA-F0-9]+):([a-fA-F0-9]+):(\d+)\s+\S+\s+\S+', line)
                    require(match is not None, 'STAGE_WRITER_GUARD_UNPROVEN')
                    major, minor, inode = match.groups()
                    require((int(major, 16), int(minor, 16), int(inode)) !=
                            (os.major(value['lockDev']), os.minor(value['lockDev']), value['lockIno']),
                            'STAGE_WRITER_GUARD_LIVE')
            final = actual.lstat()
            require(all(getattr(final, key) == getattr(previous, key) for key in
                        ['st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_mtime_ns', 'st_ctime_ns']),
                    'STAGE_CHANGED_BEFORE_PRESERVATION')
            prior = actual.with_name(actual.name + '.prior-' + str(uuid.uuid4()))
            require(not prior.exists() and not prior.is_symlink(), 'STAGE_PRESERVATION_COLLISION')
            os.rename(actual, prior)
            require((prior.lstat().st_dev, prior.lstat().st_ino) == (previous.st_dev, previous.st_ino),
                    'STAGE_CHANGED_DURING_PRESERVATION')
            descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            preserved = True
        actual.mkdir(mode=0o700, exist_ok=False)
        actual.chmod(0o700)
        descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return {'stage': str(stage), 'operationId': operation, 'preservedPrevious': preserved}
    actual, info = protected(str(stage), directory=True, **options)
    require(stat.S_IMODE(info.st_mode) == 0o700, 'STAGE_UNSAFE')
    evidence = actual / 'old-installation.json'
    if action == 'capture':
        claim = Path(request['claimRoot'])
        # The pool gate is authoritative when the compatibility pair exists.
        receipt = Path(values['relay_config_root']) / 'serial-pool-compat-v1.json'
        receipt_actual = root / receipt.relative_to('/')
        has_receipt = receipt_actual.exists() or receipt_actual.is_symlink()
        if has_receipt:
            read(str(receipt), **options)
        gate = claim / ('admission-pool-v1.json' if has_receipt else 'admission-v1.json')
        raw = read(str(gate), **options)
        value = json.loads(raw)
        require(value.keys() == {'version', 'consumerDigest', 'phase', 'operationId', 'target', 'previousActive', 'verifiedRevision'}
                and value['version'] == 1 and value['phase'] == 'open' and value['operationId'] is None
                and value['target'] is None and value['previousActive'] is None and value['verifiedRevision'] is None
                and value['consumerDigest'] == request['baselineDigest'], 'OLD_GATE_NOT_OPEN')
        consumer_restore_required = request.get('consumerRestoreRequired', False)
        require(type(consumer_restore_required) is bool, 'EVIDENCE_BINDING_CHANGED')
        snapshot = {'version': 1, 'operationId': operation, 'target': target, 'gatePath': str(gate),
                    'gate': base64.b64encode(raw).decode(), 'consumerRestoreRequired': consumer_restore_required,
                    'critical': critical_state(values, consumer_restore_required=consumer_restore_required, **options)}
        write_private(evidence, encoded(snapshot))
        return {'oldStateSha256': hashlib.sha256(encoded(snapshot['critical'])).hexdigest()}
    snapshot = json.loads(read(str(stage / evidence.name), **options))
    require(snapshot['operationId'] == operation and snapshot['target'] == target, 'EVIDENCE_BINDING_CHANGED')
    require(type(snapshot['consumerRestoreRequired']) is bool, 'EVIDENCE_BINDING_CHANGED')
    require(critical_state(values, consumer_restore_required=snapshot['consumerRestoreRequired'], **options)
            == snapshot['critical'], 'OLD_INSTALLATION_CHANGED')
    if action == 'verify':
        return {'oldStateSha256': hashlib.sha256(encoded(snapshot['critical'])).hexdigest()}
    require(action == 'abort', 'ACTION_INVALID')
    # The caller must hold the real Writer mutex. Verify the kernel holder here,
    # not merely a caller assertion, before restoring the exact old gate bytes.
    module = Path(request['source']) / 'deploy/writer_lock_lease.py'
    namespace = {'__name__': 'cutover_writer_lease', '__file__': str(root / module.relative_to('/'))}
    exec(compile(read(str(module), **options), namespace['__file__'], 'exec'), namespace)
    old_raw = base64.b64decode(snapshot['gate'], validate=True)
    old = json.loads(old_raw)
    namespace['verify'](root / Path(request['lease']).relative_to('/'),
        str(root / Path(snapshot['gatePath']).parent.relative_to('/') / 'publication-v2.lock'),
        operation=operation, target=target, consumer_digest=old['consumerDigest'])
    # Reprove the actual live consumer immediately before the only restoration
    # write. A private clone proving what could be restored is insufficient.
    consumer_path = values['relay_consumer_config_path']
    consumer_before = read(consumer_path, **options)
    validator = Path(request['source']) / 'consumer/consumer-config.mjs'
    protected(str(validator), **options)
    program = ('import{pathToFileURL}from"node:url";const m=await import(pathToFileURL(process.argv[1]));'
               'console.log(JSON.stringify({digest:m.consumerDigest(m.loadConsumer(process.argv[2]))}));')
    try:
        checked = subprocess.run(['/usr/bin/node', '--input-type=module', '-e', program,
            str(root / validator.relative_to('/')), str(root / Path(consumer_path).relative_to('/'))],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=30,
            env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'})
        require(checked.returncode == 0 and len(checked.stdout) <= 4096
                and json.loads(checked.stdout).get('digest') == old['consumerDigest']
                and read(consumer_path, **options) == consumer_before, 'ABORT_CONSUMER_UNPROVEN')
    except (OSError, ValueError, subprocess.SubprocessError):
        require(False, 'ABORT_CONSUMER_UNPROVEN')
    gate = json.loads(read(snapshot['gatePath'], **options))
    require(gate['phase'] in ['quiesced', 'drained', 'applying', 'recovery-required'] and gate['operationId'] == operation
            and gate['target'] == target and gate['consumerDigest'] == old['consumerDigest']
            and gate['verifiedRevision'] is None, 'ABORT_GATE_UNPROVEN')
    if snapshot.get('predispatchBridge'):
        require(gate['previousActive'] is None or isinstance(gate['previousActive'], dict),
                'PREDISPATCH_BRIDGE_ABORT_ACTIVITY_UNPROVEN')
        verify_predispatch_bridge_abort(snapshot, request, values, operation=operation, target=target,
                                        root=root, owner_uid=owner_uid, gate=gate, service_probe=service_probe)
    else:
        require(gate['previousActive'] is None, 'ABORT_GATE_UNPROVEN')
    write_private(root / Path(snapshot['gatePath']).relative_to('/'), old_raw, replace=True)
    require(read(snapshot['gatePath'], **options) == old_raw, 'ABORT_READBACK_FAILED')
    return {'status': 'old-open-restored', 'operationId': operation}


class PreparedInstall:
    def __init__(self, target, key, values, identity, operation, *, local=False, reinstall=False):
        self.target, self.key, self.values, self.identity = target, key, values, identity
        self.operation, self.local = operation, local
        require(type(reinstall) is bool, 'STAGE_BINDING_INVALID')
        self.reinstall = reinstall
        parent = (Path(values['relay_install_root']).parent / ('.' + values['relay_namespace'] + '-staging')
                  if reinstall else Path(values['relay_release_root']))
        self.stage = str(parent / ('.stage-' + operation))
        self.source = self.stage + '/release/reviewed-source'
        self.lease_path = self.stage + '/writer-lock.json'
        self.holder = None
        self.initial = None
        self.host_observation = None
        self.captured = False
        self.cutover_started = False
        self.predispatch_bridge_attempted = False
        self.predispatch_bridge_request = None
        self.predispatch_bridge_binding = None
        self.predispatch_bridge_proof = None
        self.stage_observation = None
        self.retained_proof = None

    def execute(self, argv, *, payload=None, timeout=180):
        from ansible_transport import run_target
        result = run_target(self.target, self.key, argv,
                            input=json.dumps(payload) if payload is not None else None,
                            timeout=timeout, local=self.local)
        if result.returncode:
            # Only a bounded code crosses the private transport, never its raw
            # input, command output, config, credential or filesystem details.
            codes = re.findall(r'\b(?:INSTALL_PREFLIGHT|PREDISPATCH_BRIDGE|PREDISPATCH|BOUNDED_RECOVERY|HOST|CONSUMER_PREFLIGHT|INTENT_STAGE|INTENT_PACKAGE|INTENT_RUNNER|RUNNER_ACTIVE|WRITER_LOCK)_[A-Z_]{1,100}\b', result.stderr)
            error = RuntimeError(codes[-1] if codes else 'INSTALL_PREFLIGHT_PREREQUISITE_UNPROVEN')
            error.next_action = ('Correct the named prerequisite using the existing installed version or its owner-supported '
                                 'credential/package procedure; retain the old entrypoint and retry the same frozen Git pair.')
            try:
                report = json.loads(result.stdout) if len(result.stdout.encode()) <= 4096 else None
            except (ValueError, TypeError):
                report = None
            if (isinstance(report, dict) and report.keys() == {'version', 'status', 'error_code', 'resource', 'next_action'}
                    and type(report['version']) is int and report['version'] == 1
                    and report['status'] == 'FAIL' and isinstance(report['error_code'], str)
                    and re.fullmatch(r'HOST_[A-Z_]{1,100}', report['error_code'])
                    and isinstance(report['resource'], str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', report['resource'])
                    and isinstance(report['next_action'], str) and re.fullmatch(r'[a-z0-9][a-z0-9-]{0,159}', report['next_action'])):
                error = RuntimeError(report['error_code'])
                error.resource = report['resource']
                error.next_action = report['next_action'] + '; resource=' + report['resource'] + '; keep the prior installation unchanged.'
            raise error
        try:
            return json.loads(result.stdout)
        except (ValueError, TypeError):
            require(False, 'RESULT_UNPROVEN')

    def action(self, action, **extra):
        return self.execute(['/usr/bin/python3', '-I', '-c', Path(__file__).read_text()], payload={
            'values': self.values, 'action': action, 'operation': self.operation,
            'target': self.identity['revision'], 'stage': self.stage, 'reinstall': self.reinstall, **extra})

    def create(self):
        return self.action('create')

    def consumer(self, *, final=False):
        argv = ['/usr/bin/node', self.source + '/controller/src/consumer-preflight-cli.mjs',
                '--config', self.values['relay_consumer_config_path'], '--install-root', self.values['relay_install_root'],
                '--stage-root', self.stage, '--desired-digest', self.desired_digest,
                '--repository', self.values['relay_github_repository']]
        if self.holder:
            argv += ['--writer-lock-lease', self.lease_path]
        receipt = self.execute(argv)
        require(receipt['eligible'], 'CONSUMER_HISTORY_REQUIRES_OLD_VERSION_RESOLUTION')
        if final:
            require(not receipt['consumerRestoreRequired'] and receipt['baselineDigest'] == self.initial['baselineDigest']
                    and receipt['claimRoot'] == self.initial['claimRoot'] and not receipt['active'] and not receipt['unknown'],
                    'FINAL_CONSUMER_STATE_CHANGED')
        elif self.initial is None:
            self.initial = receipt
        return receipt

    def consumer_retained(self, proof, *, final=False):
        """Read an already-authorized replacement without inventing current.

        The owning clean-reinstall continuation independently proves its exact
        archive, source, original operation and journal. That authority must be
        repeated before the final lock. This read only authenticates the real
        canonical consumer and full candidate history under that existing lock;
        it cannot restore a consumer, capture an open gate or authorize a retry.
        """
        require(self.reinstall and not self.captured and isinstance(proof, dict)
                and proof.keys() == {'state', 'sourceRevision', 'targetRevision', 'lifecycleOperation',
                                     'completed', 'journalSha256', 'allowedInventoryBlockers'}
                and proof['state'] == 'CONTINUATION_READY'
                and isinstance(proof['sourceRevision'], str) and re.fullmatch('[0-9a-f]{40}', proof['sourceRevision'])
                and proof['sourceRevision'] != self.identity['revision']
                and proof['targetRevision'] == self.identity['revision']
                and proof['lifecycleOperation'] == self.operation and type(proof['completed']) is bool
                and isinstance(proof['journalSha256'], str)
                and (proof['journalSha256'] == '' if proof['completed']
                     else re.fullmatch('[0-9a-f]{64}', proof['journalSha256']))
                and isinstance(proof['allowedInventoryBlockers'], list)
                and all(isinstance(item, str) for item in proof['allowedInventoryBlockers'])
                and set(proof['allowedInventoryBlockers']) <= {'clean-reinstall-recovery-present;inspect-before-retry',
                    'production-operation-recovery-present;inspect-before-retry', 'installed-identity-invalid'},
                'RETAINED_REPLACEMENT_AUTHORITY_UNPROVEN')
        retained = getattr(self, 'retained_proof', None)
        require(retained is None and self.initial is None or retained == proof,
                'RETAINED_REPLACEMENT_AUTHORITY_CHANGED')
        require(not final or self.holder is not None and self.holder.poll() is None, 'WRITER_LOCK_MISSING')
        # Derive claimRoot from the actual protected canonical consumer, never
        # from a caller-provided receipt. The parent and child observations must
        # see identical bytes, while the child reads under the real Writer lock.
        program = r'''
import {readFileSync,openSync,closeSync,fstatSync,lstatSync,constants} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {pathToFileURL} from 'node:url';
try {
  const [source,config,repository,desired,lease] = process.argv.slice(1);
  const m = await import(pathToFileURL(source + '/consumer/consumer-config.mjs'));
  m.assertRootConsumer(config);
  const before = readFileSync(config), consumer = m.loadConsumer(config);
  const currentDigest = m.consumerDigest(consumer), claimRoot = consumer.paths.claimRoot;
  const lockPath = claimRoot + '/publication-v2.lock';
  // Open the EXISTING inode ourselves: flock's ordinary pathname form could
  // otherwise create a missing file during this read-only observation.
  let descriptor, lock;
  if (lease === '-') {
    descriptor=openSync(lockPath,constants.O_RDWR|constants.O_NOFOLLOW|constants.O_NONBLOCK);
    lock=fstatSync(descriptor);
    const actual=lstatSync(lockPath);
    if(!lock.isFile() || lock.uid!==0 || lock.nlink!==1 || (lock.mode&0o022)
       || lock.dev!==actual.dev || lock.ino!==actual.ino) throw Error();
  }
  const prefix = lease === '-' ? ['/usr/bin/flock','-w','180','/proc/self/fd/3','/usr/bin/node',source+'/controller/src/admission-cli.mjs']
    : ['/usr/bin/python3','-I',source+'/deploy/writer_lock_lease.py','--exec-admission',lease,source,config,repository];
  const child = spawnSync(prefix[0],[...prefix.slice(1),'consumer-transition-preflight','--desired-digest',desired],
    {env:{PATH:'/usr/bin:/bin',LANG:'C',LC_ALL:'C',RELAY_CONSUMER_CONFIG:config,RELAY_REPOSITORY:repository},
     stdio:descriptor===undefined?['ignore','pipe','pipe']:['ignore','pipe','pipe',descriptor],
     encoding:'utf8',timeout:180000,maxBuffer:1024*1024,detached:true});
  if(child.error) {try {process.kill(-child.pid,'SIGKILL');} catch {}}
  if(descriptor!==undefined) {
    const after=lstatSync(lockPath); closeSync(descriptor);
    if(lock.dev!==after.dev || lock.ino!==after.ino || lock.mode!==after.mode || lock.gid!==after.gid) throw Error();
  }
  if (child.error || child.status !== 0 || !readFileSync(config).equals(before)) throw Error();
  m.assertRootConsumer(config);
  const result = JSON.parse(child.stdout);
  if (result.currentDigest !== currentDigest || result.desiredDigest !== desired) throw Error();
  console.log(JSON.stringify({...result,baselineDigest:currentDigest,claimRoot,lockPath,
    consumerRestoreRequired:false,actualDriftCategory:'none',effectiveConsumerPath:config}));
} catch {
  process.stderr.write('INSTALL_PREFLIGHT_RETAINED_CONSUMER_UNPROVEN\n'); process.exitCode=40;
}
'''
        receipt = self.execute(['/usr/bin/node', '--input-type=module', '-e', program, self.source,
            self.values['relay_consumer_config_path'], self.values['relay_github_repository'],
            self.desired_digest, self.lease_path if self.holder else '-'], timeout=210)
        require(isinstance(receipt, dict) and receipt.get('eligible') is True
                and receipt.get('consumerChange') is False
                and receipt.get('currentDigest') == receipt.get('desiredDigest') == self.desired_digest
                and receipt.get('phase') in ['applying', 'recovery-required', 'verified']
                and receipt.get('operationId') == self.operation and receipt.get('target') == self.identity['revision']
                and receipt.get('active') == [] and receipt.get('unknown') == [], 'RETAINED_REPLACEMENT_STATE_UNPROVEN')
        if retained is None:
            self.initial, self.retained_proof = receipt, json.loads(encoded(proof))
        else:
            require(receipt['currentDigest'] == self.initial['baselineDigest']
                    and receipt['claimRoot'] == self.initial['claimRoot']
                    and receipt['lockPath'] == self.initial['lockPath'], 'RETAINED_REPLACEMENT_STATE_CHANGED')
        return receipt

    def desired(self):
        code = ('import {readFileSync} from "node:fs";import {pathToFileURL} from "node:url";'
                'const m=await import(pathToFileURL(process.argv[1]));'
                'console.log(JSON.stringify(m.consumerDigest(m.validateConsumer(m.parseConsumerJson(readFileSync(process.argv[2],"utf8"))))));')
        self.desired_digest = self.execute(['/usr/bin/node', '--input-type=module', '-e', code,
            self.source + '/consumer/consumer-config.mjs', self.stage + '/consumer.json'])
        require(isinstance(self.desired_digest, str) and re.fullmatch('[0-9a-f]{64}', self.desired_digest), 'DESIRED_DIGEST_INVALID')

    def host(self, *, final=False):
        receipt = self.execute(['/usr/bin/python3', '-I', self.source + '/deploy/host_preflight.py', '--input'],
                               payload={'values': self.values, 'sourceRoot': self.source})
        require(receipt.get('status') == 'PASS', 'HOST_UNPROVEN')
        if final:
            require(receipt['observedSha256'] == self.host_observation['observedSha256'], 'HOST_PRECONDITION_CHANGED')
        else:
            self.host_observation = receipt
        return receipt

    def capture(self):
        result = self.action('capture', claimRoot=self.initial['claimRoot'], baselineDigest=self.initial['baselineDigest'],
                             consumerRestoreRequired=self.initial['consumerRestoreRequired'])
        self.captured = True
        return result

    def verify_stage(self):
        helper = Path(__file__).parent / 'ansible/roles/relay_artifacts/files/relay-intent-stage.py'
        receipt = self.execute(['/usr/bin/python3', '-I', '-c', helper.read_text(), 'verify', self.stage],
                               payload={'operationId': self.operation, 'sourceIdentity': self.identity})
        require(isinstance(receipt, dict) and isinstance(receipt.get('packages'), dict)
                and receipt['packages'].keys() == {'runner', 'codex'}, 'PACKAGE_RECEIPTS_UNPROVEN')
        from host_preflight import resolved
        values = resolved(self.values)
        package_helper = Path(__file__).parent / 'ansible/roles/relay_runner/files/relay-intent-package.py'
        for kind in ['runner', 'codex']:
            sealed = receipt['packages'][kind]
            require(isinstance(sealed, dict) and sealed.get('kind') == kind
                    and sealed.get('operationId') == self.operation
                    and isinstance(sealed.get('packageVersion'), str)
                    and isinstance(sealed.get('archiveSha256'), str)
                    and re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', sealed.get('packageVersion', ''))
                    and (re.fullmatch('[0-9a-f]{64}', sealed.get('archiveSha256', ''))
                         if kind == 'runner' else sealed.get('archiveSha256') == '-'), 'PACKAGE_RECEIPT_INVALID')
            if kind == 'runner':
                payload = {'root': values['relay_runner_root'],
                    'archive': values.get('relay_runner_package_archive', values['relay_runner_package_cache_root']
                                         + '/actions-runner-linux-x64-' + sealed['packageVersion'] + '.tar.gz'),
                    'user': values['relay_runner_user'], 'service': values['relay_runner_service_name'],
                    'packageVersion': sealed['packageVersion']}
            else:
                payload = {'home': values['relay_codex_package_home'], 'installDir': values['relay_codex_package_install_dir'],
                    'binary': values['relay_codex_binary_path'], 'installer': values.get('relay_codex_installer_path',
                        values['relay_runner_package_cache_root'] + '/codex-install.sh')}
            observed = self.execute(['/usr/bin/python3', '-I', '-c', package_helper.read_text(),
                'verify', kind, self.stage, self.operation, sealed['packageVersion'], sealed['archiveSha256']], payload=payload)
            require(observed == sealed, 'PACKAGE_RECEIPT_CHANGED')
        destination = self.values['relay_release_root'] + '/' + self.identity['revision']
        plan = self.execute(['/usr/bin/python3', '-I', '-c', helper.read_text(),
            'check-destination', self.stage, destination], payload={'operationId': self.operation,
                'sourceIdentity': self.identity, 'releaseRoot': self.values['relay_release_root'], 'reinstall': self.reinstall})
        require(isinstance(plan, dict) and plan.get('status') == 'DESTINATION_READY', 'DESTINATION_UNPROVEN')
        if self.stage_observation is None:
            self.stage_observation = json.loads(encoded(receipt))
        else:
            require(receipt == self.stage_observation, 'SEALED_STAGE_CHANGED')
        return receipt

    def lock_writer(self):
        from ansible_transport import hold_target
        require(self.holder is None and self.initial is not None, 'LOCK_SEQUENCE_INVALID')
        self.holder = hold_target(self.target, self.key, ['/usr/bin/python3', '-I',
            self.source + '/deploy/writer_lock_lease.py', '--hold', self.initial['lockPath'], self.lease_path,
            self.operation, self.identity['revision'], self.initial['baselineDigest']], 'WRITER_LOCK_READY')

    def drain_staged(self):
        """Drain with the sealed candidate reader, taking the Writer lock per poll.

        The installed reader may predate a valid administrative receipt.  The
        candidate was independently selected and sealed before quiescing; its
        normal drain CLI uses the same consumer, gate and Writer lock as the
        installed helper.  It does not hold the lock while controllers finish.
        """
        require(self.captured and self.initial is not None and self.holder is None,
                'STAGED_DRAIN_SEQUENCE_INVALID')
        self.verify_stage()
        result = self.execute(['/usr/bin/env', '-i', 'PATH=/usr/bin:/bin', 'LANG=C', 'LC_ALL=C',
            'RELAY_CONSUMER_CONFIG=' + self.values['relay_consumer_config_path'],
            'RELAY_REPOSITORY=' + self.values['relay_github_repository'],
            '/usr/bin/node', self.source + '/controller/src/admission-cli.mjs',
            'drain', '--operation', self.operation, '--timeout', '1800'], timeout=1860)
        require(result.get('drained') is True, 'STAGED_DRAIN_UNPROVEN')
        return result

    def release_writer(self):
        if self.holder is not None:
            holder, self.holder = self.holder, None
            holder.stdin.close()
            require(holder.wait(timeout=30) == 0, 'WRITER_LOCK_LOST_INSPECT_BEFORE_RETRY')

    def final(self, *, fresh=False):
        if not fresh:
            require(self.holder is not None and self.holder.poll() is None, 'WRITER_LOCK_MISSING')
            if getattr(self, 'retained_proof', None) is not None:
                self.consumer_retained(self.retained_proof, final=True)
            else:
                self.consumer(final=True)
        self.host(final=not bool(getattr(self, 'predispatch_bridge_proof', None)))
        self.verify_stage()
        if self.captured and not getattr(self, 'predispatch_bridge_proof', None):
            self.action('verify')

    def predispatch_recovery(self, request):
        require(self.holder is not None and self.holder.poll() is None, 'WRITER_LOCK_MISSING')
        return self.execute(['/usr/bin/python3', '-I', self.source + '/deploy/writer_lock_lease.py',
            '--exec-predispatch', self.lease_path, self.source, self.values['relay_consumer_config_path'],
            request.get('repository', self.values['relay_github_repository'])], payload=request)

    def bridge_predispatch(self, request, snapshot, *, continuation=False):
        """Keep the exact install UUID, original bytes and first service intent.

        The materialized compatible current is a durable replay fence BEFORE
        finalization. A lost process/lease therefore cannot reopen old code.
        """
        require(not self.reinstall and self.initial is not None and not self.initial['consumerChange']
                and not self.initial['consumerRestoreRequired']
                and request.get('operation') == 'finalize-predispatch'
                and type(request.get('authorizationId')) is int and request['authorizationId'] > 0
                and type(request.get('runId')) is int and request['runId'] > 0
                and request.get('attemptId') == 'run-' + str(request['runId']), 'PREDISPATCH_BRIDGE_BINDING_INVALID')
        if self.holder is None:
            self.lock_writer()
        inspect = {**request, 'operation': 'predispatch-authorization'}
        original = self.predispatch_recovery(inspect)
        binding = original.get('binding') or original.get('recovery', {}).get('binding')
        require(binding and binding['runId'] == request['runId'], 'PREDISPATCH_BRIDGE_ORIGINAL_UNPROVEN')
        self.predispatch_bridge_request = dict(request)
        self.predispatch_bridge_binding = binding
        self.consumer()
        if not continuation:
            self.host(final=True)
            self.verify_stage()
            self.action('verify')
        else:
            self.verify_stage()
        state = self.execute([*self.admission_prefix(), 'status', '--operation', self.operation])
        require(state['target'] == self.identity['revision'] and state['active'] in [[], [request['runId']]]
                and not state['unknown'], 'PREDISPATCH_BRIDGE_OTHER_EXECUTION_UNRESOLVED')
        previous = self.values['relay_intent_expected_installed_revision']
        if continuation:
            from predispatch_bridge import read_binding
            # This branch is used only by a local root caller. Remote
            # continuation authenticates the same protected snapshot remotely.
            previous = read_binding(self.stage, self.operation, self.identity['revision'])['previousRevision']
        data = {'values': self.values, 'identity': self.identity, 'operationId': self.operation,
            'stage': self.stage, 'lease': self.lease_path, 'consumerDigest': self.initial['baselineDigest'],
            'previousRevision': previous, 'runId': request['runId'], 'recoveryRequest': request}
        self.predispatch_bridge_attempted = True
        if not continuation:
            # Persist the exact authorized bridge binding before the first
            # lifecycle phase/snapshot mutation. Even a pre-snapshot crash then
            # has a bounded same-UUID continuation without guessing an orphan.
            self.execute(['/usr/bin/python3', '-I', self.source + '/deploy/predispatch_bridge.py'],
                         payload={**data, 'prepareOnly': True})
        self.cutover_started = True
        try:
            if state['phase'] != 'applying':
                if state['phase'] != 'recovery-required':
                    self.execute([*self.admission_prefix(), 'phase', '--operation', self.operation,
                                  '--phase', 'recovery-required'])
                self.execute([*self.admission_prefix(), 'phase', '--operation', self.operation, '--phase', 'applying'])
            if not continuation:
                snapshot()
            elif state.get('previousActive') is None:
                services = self.execute(['/usr/bin/python3', '-I', self.source + '/deploy/predispatch_bridge.py', '--snapshot'],
                                        payload={'values': self.values})
                self.execute([*self.admission_prefix(), 'snapshot', '--operation', self.operation], payload=services)
            self.predispatch_bridge_proof = self.execute(['/usr/bin/python3', '-I',
                self.source + '/deploy/predispatch_bridge.py'], payload=data)
            result = self.predispatch_recovery(request)
            require(result.get('recovery', {}).get('status') == 'finalized', 'PREDISPATCH_BRIDGE_FINALIZATION_UNPROVEN')
            state = self.execute([*self.admission_prefix(), 'status', '--operation', self.operation])
            require(not state['active'] and not state['unknown'], 'PREDISPATCH_BRIDGE_DRAIN_UNPROVEN')
            return self.predispatch_bridge_proof
        except Exception:
            try:
                self.execute([*self.admission_prefix(), 'phase', '--operation', self.operation,
                              '--phase', 'recovery-required'])
            except Exception:
                pass
            raise

    def abort(self):
        bridge_abort = self.predispatch_bridge_attempted and self.predispatch_bridge_proof is None
        require(self.captured and (not self.cutover_started or bridge_abort), 'ABORT_AFTER_CUTOVER_FORBIDDEN')
        if self.holder is None:
            self.lock_writer()
        require(self.holder.poll() is None, 'WRITER_LOCK_MISSING')
        if bridge_abort:
            require(self.predispatch_bridge_request and self.predispatch_bridge_binding,
                    'PREDISPATCH_BRIDGE_ABORT_UNPROVEN')
            observed = self.predispatch_recovery({**self.predispatch_bridge_request, 'operation': 'predispatch-state'})
            observed_binding = observed.get('binding') or observed.get('recovery', {}).get('binding')
            require(observed_binding == self.predispatch_bridge_binding, 'PREDISPATCH_BRIDGE_ABORT_ORIGINAL_CHANGED')
        # Authenticate the actual old consumer even if a new manual record is
        # the reason for abort. Eligibility is irrelevant to reopening OLD.
        desired = self.desired_digest
        self.desired_digest = self.initial['baselineDigest']
        try:
            receipt = self.consumer(final=False)
            require(not receipt['consumerRestoreRequired']
                    and receipt['currentDigest'] == receipt['baselineDigest'] == self.initial['baselineDigest']
                    and receipt['claimRoot'] == self.initial['claimRoot']
                    and receipt['lockPath'] == self.initial['lockPath'], 'ABORT_CONSUMER_UNPROVEN')
        finally:
            self.desired_digest = desired
        self.host(final=True)
        result = self.action('abort', source=self.source, lease=self.lease_path,
                             **({'predispatchBinding': self.predispatch_bridge_binding} if bridge_abort else {}))
        if bridge_abort:
            self.cutover_started = False
            self.predispatch_bridge_attempted = False
        return result

    def admission_prefix(self):
        return ['/usr/bin/python3', '-I', self.source + '/deploy/writer_lock_lease.py',
                '--exec-admission', self.lease_path, self.source, self.values['relay_consumer_config_path'],
                self.values['relay_github_repository']]

    def bounded_recovery(self, config, binding, proof, *, action='begin'):
        """Run the frozen controller's fixed recovery adapter under its Writer lease."""
        require(self.holder is not None and self.holder.poll() is None, 'WRITER_LOCK_MISSING')
        # The qualified controller supplies the corrected reader. The staged
        # product/source identity and original receipt remain independently frozen.
        program = ('scope={"__name__":"bounded_controller"};exec('
            + repr((Path(__file__).parent / 'bounded_recovery.py').read_text())
            + ',scope);import json,sys;print(json.dumps(scope["main"]([sys.argv[1]])))')
        return self.execute(['/usr/bin/python3', '-I', '-B', '-c', program, action],
            payload={'config': config, 'binding': binding, 'proof': proof, 'source': self.source,
                     'lease': self.lease_path, 'desiredDigest': self.desired_digest})

    def after_retirement(self):
        """Recheck the bounded lock gap after the owning replacement helper.

        Old services/helpers have deliberately retired, so their initial static
        availability snapshot is no longer an applicable rollback proof. The
        protected retirement journal owns this frontier; failures remain there.
        """
        require(self.reinstall and self.cutover_started and self.holder is not None
                and self.holder.poll() is None, 'RETIREMENT_SEQUENCE_INVALID')
        require(self.desired_digest == self.initial['baselineDigest'], 'REINSTALL_CONSUMER_REBIND_UNSUPPORTED')
        receipt = self.execute([*self.admission_prefix(), 'consumer-transition-preflight',
                                '--desired-digest', self.desired_digest])
        require(receipt.get('eligible') is True and receipt.get('consumerChange') is False
                and receipt.get('currentDigest') == self.initial['baselineDigest']
                and not receipt.get('active') and not receipt.get('unknown'), 'RETIRED_CONSUMER_STATE_CHANGED')
        self.host()
        self.verify_stage()


if __name__ == '__main__':
    try:
        require(os.geteuid() == 0, 'ROOT_REQUIRED')
        raw = sys.stdin.buffer.read(1024 * 1024 + 1)
        require(len(raw) <= 1024 * 1024, 'INPUT_SIZE')
        print(json.dumps(remote(json.loads(raw))))
    except Exception as error:
        code = str(error)
        print(code if re.fullmatch('INSTALL_PREFLIGHT_[A-Z_]{1,100}', code) else 'INSTALL_PREFLIGHT_UNPROVEN', file=sys.stderr)
        sys.exit(40)
