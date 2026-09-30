#!/usr/bin/env python3
"""Protect owner bootstrap mutations with the installed exact-head operation lock."""
import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import sys


MAX_KEY_BYTES = 65536


def require(condition, code):
    if not condition:
        raise ValueError(code)


def stamp(info):
    return (info.st_dev, info.st_ino, info.st_uid, info.st_gid,
            info.st_mode, info.st_nlink, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


class ProtectedPath:
    """Traverse protected parents with directory FDs and never follow links."""

    def __init__(self, value):
        self.path = Path(value)
        require(self.path.is_absolute() and str(self.path) == value
                and '..' not in self.path.parts and self.path.name, 'path')
        self.fd = None
        self.parents = []

    def __enter__(self):
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in self.path.parts[1:-1]:
                info = os.fstat(fd)
                require(info.st_uid == 0 and not info.st_mode & 0o022, 'parent')
                self.parents.append((info.st_dev, info.st_ino))
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                dir_fd=fd)
                os.close(fd)
                fd = child
            info = os.fstat(fd)
            require(info.st_uid == 0 and not info.st_mode & 0o022, 'parent')
            self.parents.append((info.st_dev, info.st_ino))
            self.fd = fd
            return self
        except BaseException:
            os.close(fd)
            raise

    def __exit__(self, *_):
        os.close(self.fd)

    def recheck_parents(self):
        with ProtectedPath(str(self.path)) as current:
            require(current.parents == self.parents, 'parent-changed')

    def metadata(self):
        return os.stat(self.path.name, dir_fd=self.fd, follow_symlinks=False)

    def read(self, modes, *, group=None, limit=MAX_KEY_BYTES, absent=False):
        try:
            fd = os.open(self.path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=self.fd)
        except FileNotFoundError:
            require(absent, 'missing-file')
            return None, None
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            require(stat.S_ISREG(info.st_mode) and info.st_uid == 0
                    and info.st_nlink == 1 and stat.S_IMODE(info.st_mode) in modes
                    and (group is None or info.st_gid == group), 'file-metadata')
            raw = stream.read(limit + 1)
            require(0 < len(raw) <= limit, 'file-size')
            require(stamp(os.fstat(stream.fileno())) == stamp(info), 'file-changed')
        self.recheck(stamp(info))
        return raw, stamp(info)

    def recheck(self, expected):
        self.recheck_parents()
        require(stamp(self.metadata()) == expected, 'file-changed')


@contextmanager
def mutation_guard(lock_file, operation_record, manifest, exact_head):
    require(os.geteuid() == 0, 'root-required')
    require(re.fullmatch('[0-9a-f]{40}', exact_head), 'exact-head')
    current = Path(manifest).parent
    require(current.name == 'current' and Path(manifest).name == 'artifact-manifest.json',
            'manifest-path')
    expected_release = current.parent / 'releases' / exact_head
    with ProtectedPath(lock_file) as lock, ProtectedPath(operation_record) as operation:
        lock_info = lock.metadata()
        require(stat.S_ISREG(lock_info.st_mode) and lock_info.st_uid == lock_info.st_gid == 0
                and lock_info.st_nlink == 1 and stat.S_IMODE(lock_info.st_mode) == 0o644,
                'operation-lock')
        fd = os.open(lock.path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=lock.fd)
        try:
            require(stamp(os.fstat(fd)) == stamp(lock_info), 'operation-lock-changed')
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            lock.recheck(stamp(lock_info))
            try:
                operation.metadata()
            except FileNotFoundError:
                pass
            else:
                raise ValueError('operation-recovery-required')
            with ProtectedPath(str(current)) as binding:
                info = binding.metadata()
                require(stat.S_ISLNK(info.st_mode) and info.st_uid == 0, 'installed-binding')
                require(os.readlink(binding.path.name, dir_fd=binding.fd) == str(expected_release),
                        'installed-binding')
                with ProtectedPath(str(expected_release / 'artifact-manifest.json')) as source:
                    raw, source_stamp = source.read({0o600, 0o640, 0o644}, limit=65536)
                    value = json.loads(raw)
                    require(isinstance(value, dict) and value.get('schemaVersion') == '1.0'
                            and value.get('commit') == exact_head
                            and value.get('installedRevision') == exact_head, 'installed-head')
                    source.recheck(source_stamp)
                binding.recheck(stamp(info))
                yield
                binding.recheck(stamp(info))
                lock.recheck(stamp(lock_info))
        finally:
            os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hold', action='store_true', required=True)
    for name in ['lock-file', 'operation-record', 'manifest', 'exact-head']:
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    require(os.geteuid() == 0, 'root-required')
    with mutation_guard(args.lock_file, args.operation_record, args.manifest, args.exact_head):
        print('BOOTSTRAP_GUARD_READY', flush=True)
        # The controller owns this pipe. EOF/disconnect releases the lock; no
        # detached process, persistent admission record or automatic retry.
        while sys.stdin.buffer.read(65536):
            pass


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, UnicodeError) as error:
        code = str(error) if type(error) is ValueError and re.fullmatch('[a-z-]+', str(error)) else 'invalid-input-or-io'
        print('BOOTSTRAP_GUARD_BLOCKED=' + code, file=sys.stderr)
        raise SystemExit(1)
