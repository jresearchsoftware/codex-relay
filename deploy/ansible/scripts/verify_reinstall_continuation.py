"""Fail closed on retained clean-reinstall evidence before backend mutations.

Only the public controller that just completed decommission under its host
mutex receives the exact journal digest. It is an internal continuation binding,
not an owner retry flag. No additional durable state or secret input is used.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys


LIMIT = 65536


def require(condition):
    if not condition:
        raise ValueError('REINSTALL_CONTINUATION_BLOCKED')


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result)
        result[key] = value
    return result


def _json(raw):
    require(len(raw) <= LIMIT)
    result = json.loads(raw, object_pairs_hook=_pairs)
    require(isinstance(result, dict))
    return result


def _present(path):
    try:
        path.lstat()
        return True
    except FileNotFoundError:
        return False


def _stamp(info):
    return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode,
            info.st_size, info.st_nlink, info.st_mtime_ns, info.st_ctime_ns)


@contextmanager
def _parent(path, boundary, owner_uid):
    relative = path.relative_to(boundary)
    descriptor = os.open(boundary, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in [None, *relative.parts[:-1]]:
            if part is not None:
                following = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = following
            info = os.fstat(descriptor)
            require(info.st_uid == owner_uid and not info.st_mode & 0o022)
        yield descriptor, relative.name
    finally:
        os.close(descriptor)


def verify(journal_path, target_head, phase, digest='', config_raw='', *,
           owner_uid=0, owner_gid=0, boundary=Path('/')):
    path, boundary = Path(journal_path), Path(boundary)
    require(path.is_absolute() and path.is_relative_to(boundary)
            and all(part not in ['.', '..'] for part in str(journal_path).split('/')))
    require(not _present(path.with_name(path.name + '.next')))
    if not _present(path):
        require(not digest)
        return 'none'
    require(phase in ['apply', 'post-check'] and re.fullmatch('[0-9a-f]{64}', digest or '')
            and re.fullmatch('[0-9a-f]{40}', target_head or ''))
    with _parent(path, boundary, owner_uid) as (parent, name):
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        with os.fdopen(descriptor, 'rb') as stream:
            info = os.fstat(stream.fileno())
            require(stat.S_ISREG(info.st_mode) and info.st_uid == owner_uid and info.st_gid == owner_gid
                    and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1 and info.st_size <= LIMIT)
            raw = stream.read(LIMIT + 1)
            require(_stamp(info) == _stamp(os.fstat(stream.fileno()))
                    and _stamp(info) == _stamp(os.stat(name, dir_fd=parent, follow_symlinks=False)))
    require(hashlib.sha256(raw).hexdigest() == digest)
    journal, config = _json(raw), _json(config_raw)
    namespace = config['environment']['namespace']
    require(re.fullmatch('[a-z][a-z0-9-]{0,30}', namespace)
            and path.name == namespace + '-clean-reinstall.json'
            and journal.get('schemaVersion') == 1 and journal.get('stage') == 'DECOMMISSIONED'
            and journal.get('targetRevision') == target_head
            and journal.get('configurationSha256') == hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest())
    return target_head


if __name__ == '__main__':
    try:
        require(len(sys.argv) == 5)
        result = verify(*sys.argv[1:], config_raw=sys.stdin.buffer.read(LIMIT + 1))
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        print('REINSTALL_CONTINUATION_BLOCKED;inspect-retained-reinstall-evidence', file=sys.stderr)
        sys.exit(1)
    print('REINSTALL_CONTINUATION_VALIDATED=' + result)
