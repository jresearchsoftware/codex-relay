"""Verify one live root Writer mutex holder during a bounded installer cutover.

The temporary lease is a rendezvous receipt, never lock or admission authority.
Every reuse proves the original process and its exclusive kernel flock.
"""
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import stat
import sys


LIMIT = 4096
FIELDS = {'version', 'pid', 'startTicks', 'fd', 'lockDev', 'lockIno', 'lockMode', 'lockGid',
          'operationId', 'target', 'consumerDigest'}
UUID = re.compile(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}')
SHA = re.compile(r'[a-f0-9]{40}')
DIGEST = re.compile(r'[a-f0-9]{64}')


def require(condition, code='WRITER_LOCK_LEASE_UNPROVEN'):
    if not condition:
        raise ValueError(code)


def unique(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value)
        value[key] = item
    return value


def _stamp(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _path(value, *, directory=False, owner_uid=0, boundary=Path('/')):
    path, boundary = Path(value), Path(boundary)
    require(path.is_absolute() and path == Path(os.path.normpath(path)) and '..' not in path.parts
            and path.is_relative_to(boundary), 'WRITER_LOCK_LEASE_PATH_UNSAFE')
    for at in [path, *path.parents]:
        info = at.lstat()
        require(info.st_uid == owner_uid and not info.st_mode & 0o022
                and not stat.S_ISLNK(info.st_mode), 'WRITER_LOCK_LEASE_PATH_UNSAFE')
        if at == path and not directory:
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
                    'WRITER_LOCK_LEASE_PATH_UNSAFE')
        else:
            require(stat.S_ISDIR(info.st_mode), 'WRITER_LOCK_LEASE_PATH_UNSAFE')
        if at == boundary:
            return path.lstat()
    raise ValueError('WRITER_LOCK_LEASE_PATH_UNSAFE')


def _read(path, *, owner_uid=0, boundary=Path('/'), private=False, limit=LIMIT):
    before = _path(path, owner_uid=owner_uid, boundary=boundary)
    require(before.st_size <= limit and (not private or
            stat.S_IMODE(before.st_mode) == 0o600 and before.st_gid == owner_uid))
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        require(_stamp(os.fstat(fd)) == _stamp(before))
        raw = os.read(fd, limit + 1)
        require(len(raw) == before.st_size and _stamp(os.fstat(fd)) == _stamp(before)
                and _stamp(Path(path).lstat()) == _stamp(before))
        return raw, before
    finally:
        os.close(fd)


def _start(pid):
    process = Path('/proc') / str(pid)
    require(process.stat().st_uid == 0)
    raw = (process / 'stat').read_text()
    fields = raw.rsplit(')', 1)[1].split()
    require(len(fields) > 19 and fields[0] not in ['Z', 'X', 'x'])
    return int(fields[19])


def verify(lease_path, expected_lock_path, *, operation=None, target=None,
           consumer_digest=None, owner_uid=0, boundary=Path('/')):
    """Prove the live root process, exact lock inode and exclusive kernel flock.

    owner_uid/boundary are fixture seams, never command-line choices. Callers
    retain the holder's transport for the whole critical section and fail closed
    if it exits; this observation does not transfer ownership of its lock.
    """
    require(os.geteuid() == owner_uid == 0, 'WRITER_LOCK_LEASE_ROOT_REQUIRED')
    lease_path, lock_path = Path(lease_path), Path(expected_lock_path)
    raw, lease_info = _read(lease_path, owner_uid=owner_uid, boundary=boundary, private=True)
    value = json.loads(raw, object_pairs_hook=unique)
    require(isinstance(value, dict) and set(value) == FIELDS and type(value['version']) is int
            and value['version'] == 1)
    require(all(type(value[key]) is int and value[key] > 0 for key in
                ['pid', 'startTicks', 'fd', 'lockIno'])
            and all(type(value[key]) is int and value[key] >= 0 for key in ['lockDev', 'lockMode', 'lockGid'])
            and isinstance(value['operationId'], str) and UUID.fullmatch(value['operationId'])
            and isinstance(value['target'], str) and SHA.fullmatch(value['target'])
            and isinstance(value['consumerDigest'], str) and DIGEST.fullmatch(value['consumerDigest']))
    require((operation is None or value['operationId'] == operation)
            and (target is None or value['target'] == target)
            and (consumer_digest is None or value['consumerDigest'] == consumer_digest))
    lock_info = _path(lock_path, owner_uid=owner_uid, boundary=boundary)
    require((lock_info.st_dev, lock_info.st_ino, stat.S_IMODE(lock_info.st_mode), lock_info.st_gid) ==
            (value['lockDev'], value['lockIno'], value['lockMode'], value['lockGid']))
    pid, fd = value['pid'], value['fd']
    require(_start(pid) == value['startTicks'])
    descriptor = Path('/proc') / str(pid) / 'fd' / str(fd)
    held = descriptor.stat()
    require((held.st_dev, held.st_ino) == (lock_info.st_dev, lock_info.st_ino)
            and os.readlink(descriptor) == str(lock_path))
    info_path = Path('/proc') / str(pid) / 'fdinfo' / str(fd)
    with info_path.open('rb') as stream:
        fdinfo = stream.read(LIMIT + 1)
    require(len(fdinfo) <= LIMIT)
    pattern = (rb'lock:\s+\d+:\s+FLOCK\s+ADVISORY\s+WRITE\s+' + str(pid).encode()
               + rb'\s+([a-fA-F0-9]+):([a-fA-F0-9]+):([0-9]+)\s+0\s+EOF')
    locks = re.findall(pattern, fdinfo)
    require(any((int(major, 16), int(minor, 16), int(inode)) ==
                (os.major(lock_info.st_dev), os.minor(lock_info.st_dev), lock_info.st_ino)
                for major, minor, inode in locks))
    require(_start(pid) == value['startTicks'] and _stamp(lock_path.lstat()) == _stamp(lock_info)
            and _stamp(lease_path.lstat()) == _stamp(lease_info))
    return value


def hold(lock_path, lease_path, operation, target, consumer_digest):
    require(os.geteuid() == 0, 'WRITER_LOCK_LEASE_ROOT_REQUIRED')
    require(UUID.fullmatch(operation or '') and SHA.fullmatch(target or '')
            and DIGEST.fullmatch(consumer_digest or ''), 'WRITER_LOCK_LEASE_BINDING_INVALID')
    lock_path, lease_path = Path(lock_path), Path(lease_path)
    before = _path(lock_path)
    _path(lease_path.parent, directory=True)
    require(lease_path.is_absolute() and lease_path == Path(os.path.normpath(lease_path))
            and '..' not in lease_path.parts, 'WRITER_LOCK_LEASE_PATH_UNSAFE')
    lock_fd = os.open(lock_path, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    owned = None
    try:
        require(_stamp(os.fstat(lock_fd)) == _stamp(before))
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('WRITER_LOCK_LEASE_BUSY') from None
        require(_stamp(lock_path.lstat()) == _stamp(before))
        value = {'version': 1, 'pid': os.getpid(), 'startTicks': _start(os.getpid()),
                 'fd': lock_fd, 'lockDev': before.st_dev, 'lockIno': before.st_ino,
                 'lockMode': stat.S_IMODE(before.st_mode), 'lockGid': before.st_gid,
                 'operationId': operation, 'target': target, 'consumerDigest': consumer_digest}
        raw = json.dumps(value, sort_keys=True, separators=(',', ':')).encode() + b'\n'
        lease_fd = os.open(lease_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        try:
            os.fchown(lease_fd, 0, 0)
            os.fchmod(lease_fd, 0o600)
            require(os.write(lease_fd, raw) == len(raw))
            os.fsync(lease_fd)
            owned = (os.fstat(lease_fd), raw)
        finally:
            os.close(lease_fd)
        verify(lease_path, lock_path, operation=operation, target=target, consumer_digest=consumer_digest)
        print('WRITER_LOCK_READY', flush=True)
        while sys.stdin.buffer.read(65536):
            pass
    finally:
        if owned is not None:
            try:
                current, _ = _read(lease_path, private=True)
                if _stamp(lease_path.lstat()) == _stamp(owned[0]) and current == owned[1]:
                    lease_path.unlink()
            except (OSError, ValueError):
                pass
        os.close(lock_fd)


def exec_admission(lease_path, source, consumer_path, repository, arguments):
    require(os.geteuid() == 0, 'WRITER_LOCK_LEASE_ROOT_REQUIRED')
    source = Path(source).resolve(strict=True)
    consumer_path = Path(consumer_path)
    _path(source, directory=True)
    cli = source / 'controller/src/admission-cli.mjs'
    _path(cli)
    identity, _ = _read(source / '.relay-source.json')
    identity = json.loads(identity, object_pairs_hook=unique)
    require(isinstance(identity, dict) and isinstance(identity.get('revision'), str)
            and SHA.fullmatch(identity['revision']))
    raw, _ = _read(consumer_path, limit=128 * 1024)
    consumer = json.loads(raw, object_pairs_hook=unique)
    require(isinstance(consumer, dict) and isinstance(consumer.get('paths'), dict)
            and isinstance(consumer['paths'].get('claimRoot'), str)
            and re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository or '')
            and repository in consumer.get('repositories', [consumer.get('repository')]))
    lock_path = Path(consumer['paths']['claimRoot']) / 'publication-v2.lock'
    allowed = {'initialize', 'quiesce', 'status', 'drain-check', 'phase', 'snapshot',
               'recovery-target', 'resume', 'consumer-transition-preflight',
               'consumer-transition-check', 'consumer-transition'}
    require(arguments and arguments[0] in allowed, 'WRITER_LOCK_LEASE_COMMAND_INVALID')
    value = verify(lease_path, lock_path)
    require(identity['revision'] == value['target'])
    # The real CLI owns full parsing. These bindings prevent a fixed command
    # from selecting a different lifecycle operation under an unrelated lease.
    for name, expected in [('--operation', value['operationId']), ('--target', value['target']),
                           ('--revision', value['target'])]:
        for index, argument in enumerate(arguments):
            if argument == name:
                require(index + 1 < len(arguments) and arguments[index + 1] == expected)
    environment = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C',
                   'RELAY_CONSUMER_CONFIG': str(consumer_path), 'RELAY_REPOSITORY': repository}
    os.execve('/usr/bin/node', ['/usr/bin/node', str(cli), *arguments], environment)


def main(arguments=None):
    arguments = sys.argv[1:] if arguments is None else arguments
    try:
        if len(arguments) == 6 and arguments[0] == '--hold':
            hold(*arguments[1:])
        elif len(arguments) >= 6 and arguments[0] == '--exec-admission':
            exec_admission(*arguments[1:5], arguments[5:])
        else:
            raise ValueError('WRITER_LOCK_LEASE_ARGUMENTS_INVALID')
        return 0
    except (ValueError, OSError, KeyError, TypeError, IndexError):
        print('WRITER_LOCK_LEASE_UNPROVEN', file=sys.stderr)
        return 1


if __name__ == '__main__':
    def interrupted(_signal, _frame):
        raise InterruptedError()
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    raise SystemExit(main())
