"""One host mutex for owner transport and installed local apply."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import stat
import sys


def require(condition, code):
    if not condition:
        raise ValueError(code)


@contextmanager
def acquire(value):
    require(os.geteuid() == 0, 'root-required')
    path = Path(value)
    require(path.is_absolute() and '..' not in path.parts, 'lock-path')
    for parent in path.parents:
        info = parent.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022,
                'unsafe-lock-parent')
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, 0o600)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == info.st_gid == 0
                and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1, 'unsafe-lock-file')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('deployment-lock-busy') from None
        current = path.lstat()
        require((current.st_dev, current.st_ino) == (info.st_dev, info.st_ino), 'lock-file-changed')
        yield fd
    finally:
        os.close(fd)


if __name__ == '__main__':
    try:
        require(len(sys.argv) == 2, 'argument-contract')
        with acquire(sys.argv[1]):
            print('DEPLOYMENT_LOCK_READY', flush=True)
            # The public controller owns this pipe. No detached service, lease,
            # timeout-based stealing, or removal/replacement of the lock inode.
            while sys.stdin.buffer.read(65536):
                pass
    except (ValueError, OSError):
        print('DEPLOYMENT_LOCK_BLOCKED', file=sys.stderr)
        raise SystemExit(1)
