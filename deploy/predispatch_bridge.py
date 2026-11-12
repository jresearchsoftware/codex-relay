"""Select a fully sealed compatible Writer before retiring an old reservation.

This is the first active effect of the SAME admitted install operation. The
existing gate retains its original service snapshot. Once current changes,
only forward recovery may continue; no branch restores the old Writer.
"""
import hashlib
import grp
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import uuid

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from install_preflight import protected, read, write_private
from writer_lock_lease import verify as verify_lease

SOURCE = Path(__file__).resolve().parents[1]
CAPABILITY = 'predispatch-retention-v1'


def require(condition, code):
    if not condition:
        raise ValueError('PREDISPATCH_BRIDGE_' + code)


def _stage():
    path = SOURCE / 'deploy/ansible/roles/relay_artifacts/files/relay-intent-stage.py'
    protected(str(path))
    spec = importlib.util.spec_from_file_location('predispatch_bridge_artifacts', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prove_wrapper(values, old_source):
    """Queued old wrappers must resolve current only AFTER the shared flock."""
    from jinja2 import Environment, StrictUndefined
    wrapper, template = (Path(values['relay_writer_helper_path']),
                         old_source / 'deploy/ansible/roles/relay_controller/templates/relay-writer-controller.j2')
    raw = read(str(wrapper))
    body = read(str(template)).decode()
    context = {**values, 'relay_writer_helper_release_path': values['relay_install_root']
               + '/current/reviewed-source/controller/src/privileged-writer-entrypoint.mjs'}
    recognized = [Environment(undefined=StrictUndefined, keep_trailing_newline=True, trim_blocks=trim)
                  .from_string(body).render(**context).encode() for trim in [False, True]]
    require(raw in recognized, 'WRITER_WRAPPER_UNPROVEN')
    expected_lock = ("/usr/bin/flock -w 300 '" + values['relay_writer_claim_root'] + "/publication-v2.lock'").encode()
    expected_writer = ("/usr/bin/node '" + context['relay_writer_helper_release_path'] + "'").encode()
    require(raw.count(expected_lock) == 1 and raw.count(expected_writer) == 1
            and raw.index(expected_lock) < raw.index(expected_writer), 'WRITER_WRAPPER_UNPROVEN')
    return hashlib.sha256(raw).hexdigest()


def admission(data, *arguments, payload=None):
    argv = ['/usr/bin/python3', '-I', str(SOURCE / 'deploy/writer_lock_lease.py'), '--exec-admission',
            data['lease'], str(SOURCE), data['values']['relay_consumer_config_path'],
            data['values']['relay_github_repository'], *arguments]
    result = subprocess.run(argv, input=json.dumps(payload) if payload is not None else None,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180,
        env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C', 'PYTHONDONTWRITEBYTECODE': '1'})
    require(result.returncode == 0 and len(result.stdout) <= 1024 * 1024, 'ADMISSION_UNPROVEN')
    return json.loads(result.stdout)


def prove_host_lock(values, descriptor=None):
    lock = Path('/var/lib/' + values['relay_namespace'] + '-deployment.lock')
    protected(str(lock))
    current = lock.lstat()
    require(stat.S_IMODE(current.st_mode) == 0o600 and current.st_uid == current.st_gid == 0,
            'HOST_LOCK_UNPROVEN')
    if descriptor is not None:
        held = os.fstat(descriptor)
        require((held.st_dev, held.st_ino) == (current.st_dev, current.st_ino), 'HOST_LOCK_UNPROVEN')
        import fcntl
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return
    # Public SSH/local install already owns and monitors a separate fixed host
    # lock guardian. Authenticate the actual kernel lock, not a caller flag.
    with open('/proc/locks', 'rb') as stream:
        table = stream.read(1024 * 1024 + 1)
    require(len(table) <= 1024 * 1024, 'HOST_LOCK_UNPROVEN')
    holders = []
    for line in table.splitlines():
        match = re.fullmatch(rb'\d+: FLOCK  ADVISORY  WRITE (\d+) ([0-9a-f]+):([0-9a-f]+):(\d+) 0 EOF', line)
        if not match:
            continue
        pid, major, minor, inode = match.groups()
        if (int(major, 16), int(minor, 16), int(inode)) == (os.major(current.st_dev), os.minor(current.st_dev), current.st_ino):
            holders.append(int(pid))
    require(len(holders) == 1 and holders[0] > 0, 'HOST_LOCK_UNPROVEN')
    status = Path('/proc') / str(holders[0]) / 'status'
    require(re.search(rb'(?m)^Uid:\s+0\s+0\s+0\s+0\s*$', status.read_bytes()), 'HOST_LOCK_UNPROVEN')


def inspect_predispatch(data):
    original = data['recoveryRequest']
    request = {**original, 'operation': 'predispatch-authorization'}
    result = subprocess.run(['/usr/bin/python3', '-I', str(SOURCE / 'deploy/writer_lock_lease.py'),
        '--exec-predispatch', data['lease'], str(SOURCE), data['values']['relay_consumer_config_path'],
        request.get('repository', data['values']['relay_github_repository'])], input=json.dumps(request), text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180,
        env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C', 'PYTHONDONTWRITEBYTECODE': '1'})
    require(result.returncode == 0 and len(result.stdout) <= 65536, 'ORIGINAL_EVIDENCE_UNPROVEN')
    value = json.loads(result.stdout)
    binding = value.get('binding') or value.get('recovery', {}).get('binding')
    require(isinstance(binding, dict) and binding.get('operation') == 'finalize-predispatch'
            and binding.get('runId') == data['runId'] and binding.get('attemptId') == original['attemptId']
            and binding.get('repository') == request.get('repository', data['values']['relay_github_repository'])
            and re.fullmatch('[a-f0-9]{64}', binding.get('recordDigest', ''))
            and value.get('authorization', {}).get('id') == original['authorizationId'], 'ORIGINAL_EVIDENCE_UNPROVEN')
    return binding


def read_binding(stage, operation, target, *, options=None):
    """Read the existing private operation snapshot; no credential is retained."""
    snapshot = json.loads(read(str(Path(stage) / 'old-installation.json'), **(options or {})))
    value = snapshot.get('predispatchBridge')
    keys = {'version', 'operationId', 'target', 'previousRevision', 'runId', 'attemptId', 'authorizationId',
            'predispatchBinding', 'sourceIdentity', 'stageReceiptSha256', 'consumerSha256', 'writerWrapperSha256'}
    require(snapshot.get('operationId') == operation and snapshot.get('target') == target
            and isinstance(value, dict) and value.keys() == keys and value['version'] == 1
            and value['operationId'] == operation and value['target'] == target
            and re.fullmatch('[a-f0-9]{40}', value['previousRevision'])
            and type(value['runId']) is int and value['runId'] > 0 and value['attemptId'] == 'run-' + str(value['runId'])
            and type(value['authorizationId']) is int and value['authorizationId'] > 0
            and value['sourceIdentity'].get('revision') == target
            and value['predispatchBinding'].get('runId') == value['runId']
            and value['predispatchBinding'].get('attemptId') == value['attemptId']
            and all(re.fullmatch('[a-f0-9]{64}', value[key] or '')
                    for key in ['stageReceiptSha256', 'consumerSha256', 'writerWrapperSha256']), 'BINDING_UNPROVEN')
    require(hashlib.sha256(read(str(Path(stage) / 'receipt.json'), **(options or {}))).hexdigest()
            == value['stageReceiptSha256'], 'STAGE_RECEIPT_CHANGED')
    return value


def sync_directories(root):
    for directory, directories, _files in os.walk(root, topdown=False, followlinks=False):
        for name in directories:
            path = Path(directory) / name
            if path.is_symlink():
                continue
            descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def activate(data, *, observe=admission, inspect=inspect_predispatch, artifacts=None, after=None):
    """Root-only fixed install operation, called under host AND Writer locks.

    observe/artifacts/after are in-process fixture seams, unavailable to CLI.
    The exact pre-dispatch API/authorization proof precedes this operation;
    actual finalize runs afterwards through the still-held same Writer lease.
    """
    require(os.geteuid() == 0, 'ROOT_REQUIRED')
    values, identity = data['values'], data['identity']
    operation, target, run_id = data['operationId'], identity['revision'], data['runId']
    require(re.fullmatch(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', operation or '')
            and re.fullmatch('[a-f0-9]{40}', target or '') and type(run_id) is int and run_id > 0,
            'BINDING_INVALID')
    install, stage = Path(values['relay_install_root']), Path(data['stage'])
    require(stage == Path(values['relay_release_root']) / ('.stage-' + operation)
            and SOURCE == stage / 'release/reviewed-source', 'SOURCE_BINDING_INVALID')
    verify_lease(data['lease'], Path(values['relay_writer_claim_root']) / 'publication-v2.lock',
                 operation=operation, target=target, consumer_digest=data['consumerDigest'])
    prove_host_lock(values, data.get('hostLockFd'))
    consumer_before = read(values['relay_consumer_config_path'])
    current = install / 'current'
    protected(str(install), directory=True)
    before = current.lstat()
    old_release = Path(os.readlink(current))
    resumed = old_release.name == target
    require(stat.S_ISLNK(before.st_mode) and before.st_uid == 0 and old_release.parent == install / 'releases'
            and old_release.name in [data['previousRevision'], target],
            'CURRENT_UNPROVEN')
    wrapper_sha = prove_wrapper(values, old_release / 'reviewed-source')
    selected = artifacts or _stage()
    receipt = selected.run('verify', stage, {'operationId': operation, 'sourceIdentity': identity})
    candidate = stage / 'release'
    manifest = json.loads(read(str(candidate / 'artifact-manifest.json')))
    snapshot = read(str(candidate / 'deployment-config.json'))
    metadata = json.loads(read(str(candidate / 'reviewed-source/deploy/installation-contract.json')))
    require(CAPABILITY in metadata.get('capabilities', [])
            and all(manifest.get(key) == target for key in ['commit', 'installedRevision', 'resolvedRevision'])
            and manifest.get('gitTree') == identity['tree']
            and manifest.get('previousRevision') == data['previousRevision']
            and manifest.get('deploymentConfigSha256') == hashlib.sha256(snapshot).hexdigest()
            and manifest.get('reviewerBinarySha256') == receipt['reviewer']['binarySha256'],
            'CANDIDATE_IDENTITY_UNPROVEN')
    status = observe(data, 'status', '--operation', operation)
    preparing = data.get('prepareOnly', False)
    require(type(preparing) is bool, 'BINDING_INVALID')
    require(status['phase'] in (['quiesced', 'recovery-required', 'applying'] if preparing else ['applying']) and status['target'] == target
            and status['consumerDigest'] == data['consumerDigest']
            and status['active'] in [[], [run_id]] and status['unknown'] == []
            and (preparing or isinstance(status.get('previousActive'), dict)), 'OTHER_EXECUTION_UNRESOLVED')
    original_binding = inspect(data)
    destination = install / 'releases' / target
    if not resumed:
        selected.run('consume', stage, {'operationId': operation, 'sourceIdentity': identity,
            'expectedToolchainPrefix': receipt['toolchain']['livePrefix'],
            'releaseRoot': str(install / 'releases'), 'reinstall': False}, str(destination))
    # Full consumed identity, config and binary bytes must still match the seal.
    selected.check_destination(candidate, destination, selected.allowed_links(receipt['sourceAcquisition']))
    require(selected.tree_digest(destination, selected.allowed_links(receipt['sourceAcquisition'])) == receipt['releaseTreeSha256']
            and read(str(destination / 'artifact-manifest.json')) == read(str(candidate / 'artifact-manifest.json'))
            and read(str(destination / 'deployment-config.json')) == snapshot
            and read(str(destination / 'reviewed-source/.relay-source.json'))
                == read(str(candidate / 'reviewed-source/.relay-source.json'))
            and hashlib.sha256(read(str(destination / 'bin/reviewer-mcp-http'))).hexdigest()
                == receipt['reviewer']['binarySha256'], 'MATERIALIZATION_CHANGED')
    if not resumed:
        os.chown(destination / 'bin/reviewer-mcp-http', 0, grp.getgrnam(values['relay_reviewer_group']).gr_gid)
    require(read(values['relay_consumer_config_path']) == consumer_before
            and prove_wrapper(values, old_release / 'reviewed-source') == wrapper_sha
            and os.readlink(current) == str(old_release), 'LIVE_BINDING_CHANGED')
    verify_lease(data['lease'], Path(values['relay_writer_claim_root']) / 'publication-v2.lock',
                 operation=operation, target=target, consumer_digest=data['consumerDigest'])
    prove_host_lock(values, data.get('hostLockFd'))
    require(inspect(data) == original_binding, 'ORIGINAL_EVIDENCE_CHANGED')
    snapshot_path = stage / 'old-installation.json'
    snapshot = json.loads(read(str(snapshot_path)))
    expected = {'version': 1, 'operationId': operation, 'target': target,
        'previousRevision': data['previousRevision'], 'runId': run_id,
        'attemptId': data['recoveryRequest']['attemptId'], 'authorizationId': data['recoveryRequest']['authorizationId'],
        'predispatchBinding': original_binding, 'sourceIdentity': identity,
        'stageReceiptSha256': hashlib.sha256(read(str(stage / 'receipt.json'))).hexdigest(),
        'consumerSha256': hashlib.sha256(consumer_before).hexdigest(), 'writerWrapperSha256': wrapper_sha}
    require(snapshot.get('operationId') == operation and snapshot.get('target') == target, 'OPERATION_BINDING_CHANGED')
    if 'predispatchBridge' in snapshot:
        require(read_binding(stage, operation, target) == expected, 'OPERATION_BINDING_CHANGED')
    else:
        require(not resumed, 'OPERATION_BINDING_MISSING')
        snapshot['predispatchBridge'] = expected
        write_private(snapshot_path, json.dumps(snapshot, sort_keys=True).encode() + b'\n', replace=True)
    sync_directories(destination)
    for path in [destination.parent, stage, stage.parent]:
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    if preparing:
        return {'operationId': operation, 'target': target, 'previousRevision': data['previousRevision'],
                'phase': status['phase'], 'writer': 'unchanged', 'binding': 'durable'}
    if after:
        after('before-switch')
    # The existing admission phase+target+original snapshot is already durable.
    # Publishing current is the crash-safe fence, before any original mutation.
    if not resumed:
        temporary = install / ('.current-predispatch-' + str(uuid.uuid4()))
        os.symlink(str(destination), temporary)
        try:
            os.replace(temporary, current)
            directory = os.open(install, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if temporary.is_symlink():
                temporary.unlink()
    if after:
        after('after-switch')
    require(os.readlink(current) == str(destination)
            and read(values['relay_consumer_config_path']) == consumer_before, 'CURRENT_READBACK_FAILED')
    return {'operationId': operation, 'target': target, 'previousRevision': data['previousRevision'],
            'phase': 'applying', 'writer': 'compatible', 'serviceSnapshot': 'retained'}


def observe_services(values):
    """The same bounded wire shape and native states as upgrade-lifecycle-observe."""
    require(os.geteuid() == 0, 'ROOT_REQUIRED')
    units = [('reviewer', values['relay_reviewer_service_name']), ('production', values['relay_production_runner_service_name']),
             ('general', values['relay_general_runner_service_name']),
             ('manualOutcome', values['relay_namespace'] + '-relay-manual-outcome.socket')]
    units += [('slot-' + slot['relay_execution_slot'], slot['relay_runner_service_name'])
              for slot in values.get('relay_additional_execution_slots', [])]
    result = {}
    for name, unit in units:
        process = subprocess.run(['/bin/systemctl', 'show', unit,
            '--property=MainPID,ExecMainStartTimestampMonotonic,ActiveState,SubState,UnitFileState,LoadState,NeedDaemonReload'],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=30)
        properties = dict(line.split('=', 1) for line in process.stdout.splitlines() if '=' in line)
        active, load, enabled = (properties.get('ActiveState'), properties.get('LoadState'), properties.get('UnitFileState', 'disabled'))
        require(active in ['active', 'inactive', 'failed'] and load in ['loaded', 'not-found']
                and (load == 'not-found' or enabled in ['enabled', 'enabled-runtime', 'disabled']), 'SERVICE_INTENT_UNPROVEN')
        if active == 'active':
            require(process.returncode == 0 and properties.get('SubState') == ('listening' if name == 'manualOutcome' else 'running')
                    and (name == 'manualOutcome' or enabled in ['enabled', 'enabled-runtime']
                         and re.fullmatch('[1-9][0-9]*', properties.get('MainPID', ''))
                         and re.fullmatch('[1-9][0-9]*', properties.get('ExecMainStartTimestampMonotonic', ''))),
                    'SERVICE_INTENT_UNPROVEN')
        if name == 'manualOutcome' and load == 'not-found':
            require(active == 'inactive' and properties.get('SubState') == 'dead'
                    and enabled in ['not-found', 'disabled'], 'SERVICE_INTENT_UNPROVEN')
        result[name] = {'active': active == 'active', 'enabled': enabled if enabled in ['enabled', 'enabled-runtime', 'disabled'] else 'disabled', 'load': load}
    if result['manualOutcome'] == {'active': False, 'enabled': 'disabled', 'load': 'not-found'}:
        del result['manualOutcome']
    return result


if __name__ == '__main__':
    try:
        data = json.loads(sys.stdin.buffer.read(1024 * 1024 + 1))
        require(sys.argv[1:] in [[], ['--snapshot']], 'ARGUMENTS_INVALID')
        print(json.dumps(observe_services(data['values']) if sys.argv[1:] else activate(data)))
    except (ValueError, RuntimeError, OSError, KeyError, TypeError, subprocess.SubprocessError):
        # No request, credential, private path or raw child output is published.
        print('PREDISPATCH_BRIDGE_UNPROVEN;preserve-current-and-use-same-operation-forward-recovery', file=sys.stderr)
        raise SystemExit(1)
