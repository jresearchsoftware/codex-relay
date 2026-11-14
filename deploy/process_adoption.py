"""Transient, fail-closed loaded-process proof for one managed Apply.

No receipt/cache is written. The caller retains the ordinary admission and
operation locks. A missing or older Reviewer capability selects normal restart.
"""
import hashlib
import fcntl
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import pwd
import re
import socket
import stat
import struct
import subprocess
import sys


def require(value):
    if not value:
        raise ValueError('PROCESS_ADOPTION_UNPROVEN')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def identity(meta):
    return (meta.st_dev, meta.st_ino, meta.st_size, meta.st_mtime_ns, meta.st_ctime_ns,
            meta.st_mode, meta.st_uid, meta.st_gid, meta.st_nlink)


def configuration(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result)
            result[key] = value
        return result
    value = json.loads(data, object_pairs_hook=unique)
    require(isinstance(value, dict) and isinstance(value.get('artifact'), dict))
    artifact = value['artifact']
    require(set(artifact) == {'commit', 'sha256'}
            and re.fullmatch('[0-9a-f]{40}', artifact['commit'])
            and re.fullmatch('[0-9a-f]{64}', artifact['sha256']))
    del value['artifact']
    return digest(canonical(value))


def protected(path, *, uid=0):
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as stream:
        meta = os.fstat(stream.fileno())
        require(stat.S_ISREG(meta.st_mode) and meta.st_uid == uid and not meta.st_mode & 0o022
                and meta.st_nlink == 1 and meta.st_size <= 1048576)
        data = stream.read(1048577)
        require(len(data) <= 1048576 and identity(os.fstat(stream.fileno())) == identity(meta))
        return data


def service(unit):
    require(unit.endswith('.service') and '/' not in unit)
    fields = 'LoadState,ActiveState,SubState,MainPID,ExecMainStartTimestamp,ExecMainStartTimestampMonotonic,NeedDaemonReload,User,ControlGroup,FragmentPath,DropInPaths,EnvironmentFiles,ExecStart,PartOf,Requires,BindsTo'
    result = subprocess.run(['/bin/systemctl', 'show', unit, '--property=' + fields],
                            capture_output=True, check=True, timeout=15,
                            env={**os.environ, 'TZ': 'UTC', 'LC_ALL': 'C'})
    values = dict(line.split('=', 1) for line in result.stdout.decode().splitlines())
    require(values['LoadState'] == 'loaded' and values['ActiveState'] == 'active'
            and values['SubState'] == 'running' and values['NeedDaemonReload'] == 'no'
            and values['MainPID'].isdigit() and int(values['MainPID']) > 0
            and values['ControlGroup'] == '/system.slice/' + unit
            and not values['DropInPaths'])
    return values


def environment(pid):
    parts = Path('/proc', str(pid), 'environ').read_bytes().split(b'\0')
    pairs = [part.decode().split('=', 1) for part in parts if part]
    require(len({key for key, _ in pairs}) == len(pairs))
    return dict(pairs)


def service_started(state):
    value = state['ExecMainStartTimestamp']
    for pattern in ['%a %Y-%m-%d %H:%M:%S UTC', '%a %Y-%m-%d %H:%M:%S.%f UTC']:
        try:
            return datetime.strptime(value, pattern).replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
    raise ValueError('PROCESS_ADOPTION_UNPROVEN')


def process(pid, service_start):
    root = Path('/proc', str(pid))
    start = root.joinpath('stat').read_text().rsplit(') ', 1)[1].split()[19]
    boot = next(int(row.split()[1]) for row in Path('/proc/stat').read_text().splitlines() if row.startswith('btime '))
    # Bound by both original systemd realtime and current boot conversion;
    # a wall-clock correction cannot make a later input appear pre-start.
    started = min(service_start, boot + int(start) / os.sysconf('SC_CLK_TCK'))
    # Pin the exact kernel-mapped inode/device, then prove no mutation since
    # process startup. This also works when map_files requires CAP_SYS_ADMIN;
    # a matching pathname by itself is never loaded artifact evidence.
    maps = {}
    mapped_ids = {}
    for row in root.joinpath('maps').read_text().splitlines():
        columns = row.split(None, 5)
        if len(columns) == 6 and columns[5].startswith('/'):
            if columns[5].startswith('/memfd:doublemapper '):
                continue  # .NET anonymous JIT allocation, not a disk dependency.
            require(not columns[5].endswith(' (deleted)'))
            identity = (columns[3], columns[4])
            require(columns[5] not in mapped_ids or mapped_ids[columns[5]] == identity)
            if columns[5] in maps:
                continue
            maps[columns[5]] = mapped_digest(columns[5], columns[3], columns[4], started)
            mapped_ids[columns[5]] = identity
    require(maps)
    return {'pid': str(pid), 'start': start, 'executable': digest(root.joinpath('exe').read_bytes()),
            'environment': digest(canonical(environment(pid))),
            'command': digest(root.joinpath('cmdline').read_bytes()), 'maps': maps}


def mapped_digest(path, device, inode, started):
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as stream:
        meta = os.fstat(stream.fileno())
        major, minor = (int(value, 16) for value in device.split(':'))
        require(stat.S_ISREG(meta.st_mode) and meta.st_ino == int(inode)
                and os.major(meta.st_dev) == major and os.minor(meta.st_dev) == minor
                and meta.st_nlink == 1 and not meta.st_mode & 0o022
                and meta.st_ctime < started - 2)
        result = hashlib.file_digest(stream, 'sha256').hexdigest()
        require(identity(os.fstat(stream.fileno())) == identity(meta))
        return result


def loaded_reviewer(payload, state):
    uid = pwd.getpwnam(payload['reviewerUser']).pw_uid
    require(uid != 0)
    pid = int(state['MainPID'])
    require(Path('/proc', str(pid)).stat().st_uid == uid and state['User'] == payload['reviewerUser'])
    path = Path(payload['socket'])
    directory = path.parent.lstat()
    meta = path.lstat()
    require(stat.S_ISDIR(directory.st_mode) and directory.st_uid == uid
            and stat.S_IMODE(directory.st_mode) == 0o700
            and stat.S_ISSOCK(meta.st_mode) and meta.st_uid == uid
            and stat.S_IMODE(meta.st_mode) == 0o600)
    with socket.socket(socket.AF_UNIX) as connection:
        connection.settimeout(5)
        connection.connect(str(path))
        peer_pid, peer_uid, _ = struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        require(peer_pid == pid and peer_uid == uid)
        data = bytearray()
        while True:
            chunk = connection.recv(4096)
            if not chunk:
                break
            data.extend(chunk)
            require(len(data) <= 16384)
    proof = json.loads(data)
    env = environment(pid)
    paths = env['REVIEWER_ADOPTION_ENV_FILES'].split(':')
    require(paths == payload['environmentFiles'] and env['REVIEWER_ADOPTION_SOCKET'] == payload['socket']
            and env['REVIEWER_ADOPTION_UNIT_FILE'] == state['FragmentPath'])
    expected = {'schemaVersion': 1, 'pid': pid,
                'config': configuration(protected(payload['config'])),
                'environment': digest(canonical(env)),
                'ca': digest(protected(env['REVIEWER_CLIENT_CA_FILE'])),
                'key': digest(protected(env['GITHUB_APP_PRIVATE_KEY_FILE'])),
                'unit': digest(protected(state['FragmentPath'])),
                'environmentFiles': {path: digest(protected(path)) for path in paths}}
    require(proof == expected)
    live = process(pid, service_started(state))
    for path, expected_digest in live['maps'].items():
        require(digest(Path(path).read_bytes()) == expected_digest)
    manifest = json.loads(protected(Path(payload['release']) / 'artifact-manifest.json'))
    require(live['executable'] == manifest['reviewerBinarySha256'])
    return {'loaded': proof, 'process': live, 'service': state}


def unchanged_since_start(path, earliest, uid):
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as stream:
        meta = os.fstat(stream.fileno())
        require(stat.S_ISREG(meta.st_mode) and meta.st_uid in [0, uid] and meta.st_nlink == 1
                and not meta.st_mode & 0o022 and meta.st_ctime < earliest - 2)
        result = hashlib.file_digest(stream, 'sha256').hexdigest()
        require(identity(os.fstat(stream.fileno())) == identity(meta))
        return result


def loaded_runner(payload, state):
    uid = pwd.getpwnam(payload['productionUser']).pw_uid
    require(state['User'] == payload['productionUser'])
    cgroup = Path('/sys/fs/cgroup') / state['ControlGroup'].lstrip('/') / 'cgroup.procs'
    pids = cgroup.read_text().splitlines()
    require(state['MainPID'] in pids and pids)
    processes = {pid: process(pid, service_started(state)) for pid in pids}
    require(all(Path('/proc', pid).stat().st_uid == uid for pid in pids))
    boot = next(int(row.split()[1]) for row in Path('/proc/stat').read_text().splitlines() if row.startswith('btime '))
    earliest = min(service_started(state), boot + min(int(value['start']) for value in processes.values()) / os.sysconf('SC_CLK_TCK'))
    root = Path(payload['productionRoot'])
    # Runner's own settings/credentials are cached on Listener startup. Kernel
    # ctime proves they have not changed since any retained service process
    # started; byte equality alone would not establish loaded settings.
    names = ['.runner', '.runner_migrated', '.credentials', '.credentials_rsaparams', '.env', '.path']
    files = {str(root / name): unchanged_since_start(root / name, earliest, uid)
             for name in names if (root / name).exists()}
    require(str(root / '.runner') in files and str(root / '.credentials') in files)
    # runsvc.sh/RunnerService.js and managed DLLs can be interpreted/read into
    # memory rather than represented by a distinct executable mapping. Prove
    # unchanged complete startup distribution, not only Runner.Listener's name.
    inputs = [path for path in root.iterdir() if path.is_file()]
    for directory in ['bin', 'externals']:
        entry = root / directory
        if entry.is_symlink():
            meta = entry.lstat()
            resolved = entry.resolve(strict=True)
            require(meta.st_uid == uid and meta.st_ctime < earliest - 2
                    and resolved.parent == root and resolved.name.startswith(directory + '.'))
            files[str(entry)] = digest(os.readlink(entry).encode())
            entry = resolved
        require(entry.is_dir())
        for parent, directories, names in os.walk(entry):
            require(all(not (Path(parent) / name).is_symlink() for name in directories))
            inputs.extend(Path(parent) / name for name in names)
            require(len(inputs) <= 20000)
    for path in inputs:
        files[str(path)] = unchanged_since_start(path, earliest, uid)
    for path in [state['FragmentPath'], *payload['environmentFiles']]:
        files[path] = unchanged_since_start(path, earliest, 0)
    for process_value in processes.values():
        for path, expected in process_value['maps'].items():
            # Same mapped object and same intended disk object, never a renamed
            # old DLL or runtime accepted against a new installation.
            require(digest(Path(path).read_bytes()) == expected)
    return {'service': state, 'processes': processes, 'files': files}


def capture_inputs(payload):
    reviewer_state = service(payload['reviewerUnit'])
    reviewer = loaded_reviewer(payload, reviewer_state)
    runner = None
    if payload['productionActive']:
        runner = loaded_runner(payload, service(payload['productionUnit']))
    # Recheck after bounded reads; service movement during proof is uncertain.
    require(service(payload['reviewerUnit']) == reviewer_state)
    if runner:
        require(service(payload['productionUnit']) == runner['service'])
    return {'reviewer': reviewer, 'production': runner}


def admission(payload):
    result = subprocess.run([*payload['admission'], 'status', '--operation', payload['operation']],
                            capture_output=True, check=True, timeout=60)
    gate = json.loads(result.stdout)
    require(gate['operationId'] == payload['operation'] and gate['target'] == payload['target']
            and gate['phase'] == 'applying' and gate['active'] == [] and gate['unknown'] == [])
    require(gate['previousActive']['reviewer']['active'] is True
            and gate['previousActive']['production']['active'] == payload['productionActive'])
    return gate


def capture(payload):
    with os.fdopen(os.open(payload['operationLock'], os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as lock:
        opened = os.fstat(lock.fileno())
        require(stat.S_ISREG(opened.st_mode) and opened.st_uid == 0 and not opened.st_mode & 0o022
                and opened.st_nlink == 1)
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        gate = admission(payload)
        if payload.get('before') is not None:
            record = json.loads(protected(payload['operationRecord']))
            require(record['state'] == 'RECOVERY_REQUIRED' and record['phase'] == 'apply'
                    and record['target_head'] == payload['target'])
        proof = capture_inputs(payload)
        require(admission(payload) == gate)
        current = os.lstat(payload['operationLock'])
        require((current.st_dev, current.st_ino) == (opened.st_dev, opened.st_ino))
        require(identity(os.fstat(lock.fileno())) == identity(opened))
        return proof


def main():
    payload = json.load(sys.stdin)
    try:
        current = capture(payload)
        previous = payload.get('before')
        require(previous is None or current == previous)
        print(json.dumps({'eligible': True, 'proof': current}))
    except (OSError, ValueError, KeyError, TypeError, StopIteration, subprocess.SubprocessError):
        # Normal fall back, with no exception/credential/path disclosure.
        print(json.dumps({'eligible': False}))


if __name__ == '__main__':
    main()
