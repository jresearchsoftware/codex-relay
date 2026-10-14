"""Qualify the complete root-owned official CLI payload; never inspect tokens."""
import json
import os
from pathlib import Path
import re
import stat
import sys


def require(value):
    if not value:
        raise ValueError('CODEX_PACKAGE_LINK_UNSAFE')


def qualify(home, command, version, *, normalize=False):
    home, command = Path(home), Path(command)
    require(home.is_absolute() and command.is_absolute() and os.geteuid() == 0)
    require(re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', version))
    metadata = home.lstat()
    require(stat.S_ISDIR(metadata.st_mode) and metadata.st_uid == metadata.st_gid == 0
            and not metadata.st_mode & 0o022)
    if normalize:
        # Installation is private until the complete payload has been checked
        # and normalized. Archive-preserved UID 1001 cannot write during this.
        require(stat.S_IMODE(metadata.st_mode) == 0o700)
    link = command.lstat()
    require(stat.S_ISLNK(link.st_mode) and link.st_uid == link.st_gid == 0)
    binary = command.resolve(strict=True)
    relative = binary.relative_to(home)
    parts = relative.parts
    require(len(parts) in [5, 6] and parts[:3] == ('packages', 'standalone', 'releases')
            and re.fullmatch(re.escape(version) + r'-[a-z0-9_-]+', parts[3])
            and parts[4:] in [('codex',), ('bin', 'codex')])
    packages = home / 'packages'
    require(packages.is_dir() and not packages.is_symlink())
    # Only distribution bytes are made public. Any other installer-home state
    # keeps its private modes and is never read, logged or treated as payload.
    entries = [home, packages]
    for directory, directories, files in os.walk(packages, followlinks=False):
        entries.extend(Path(directory) / name for name in directories + files)
    # Check the whole release first; no partial chmod/chown before aliases,
    # unsupported modes or escaping auxiliary-resource symlinks are rejected.
    for path in entries:
        info = path.lstat()
        require(stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode))
        if stat.S_ISLNK(info.st_mode):
            # Every reachable auxiliary byte must belong to the traversed and
            # qualified payload. Installer-home siblings remain private state.
            require(path.resolve(strict=True).is_relative_to(packages))
        elif stat.S_ISREG(info.st_mode):
            require(info.st_nlink == 1)
        if not normalize:
            require(info.st_uid == info.st_gid == 0 and (stat.S_ISLNK(info.st_mode) or not info.st_mode & 0o022))
            if stat.S_ISDIR(info.st_mode):
                require(stat.S_IMODE(info.st_mode) == 0o755)
            elif stat.S_ISREG(info.st_mode):
                require(stat.S_IMODE(info.st_mode) in [0o644, 0o755])
    require(binary.is_file() and binary.stat().st_mode & 0o111)
    if normalize:
        for path in reversed(entries):
            info = path.lstat()
            os.chown(path, 0, 0, follow_symlinks=False)
            if not stat.S_ISLNK(info.st_mode):
                os.chmod(path, 0o755 if stat.S_ISDIR(info.st_mode) or info.st_mode & 0o111 else 0o644)
    return {'binary': str(binary), 'packageHome': str(home), 'ownership': 'root', 'access': 'read-only'}


if __name__ == '__main__':
    try:
        require(len(sys.argv) == 5 and sys.argv[4] in ['normalize', 'check'])
        print(json.dumps(qualify(*sys.argv[1:4], normalize=sys.argv[4] == 'normalize'), sort_keys=True))
    except (ValueError, OSError):
        print('CODEX_PACKAGE_LINK_UNSAFE', file=sys.stderr)
        raise SystemExit(1)
