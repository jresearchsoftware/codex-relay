#!/usr/bin/env python3
"""Inspect or retire only an unfinished apply that never installed a runtime.

Inputs come from the product's compiled owner configuration, never a runner.
No service command mutates state. All filesystem access is under the existing
operation lock; unknown contents, accounts or lifecycle state fail closed.
"""
import fcntl
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


def require(condition, code):
    if not condition:
        raise ValueError(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def metadata(path, kind, mode=None):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts, 'path')
    for parent in reversed(path.parents):
        info = parent.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0
                and not info.st_mode & 0o022, 'parent')
    info = path.lstat()
    require(kind(info.st_mode) and info.st_uid == info.st_gid == 0
            and not info.st_mode & 0o022, 'metadata')
    require(not stat.S_ISREG(info.st_mode) or info.st_nlink == 1, 'hardlink')
    require(mode is None or stat.S_IMODE(info.st_mode) == mode, 'mode')
    return {'device': info.st_dev, 'inode': info.st_ino,
            'mode': stat.S_IMODE(info.st_mode), 'uid': info.st_uid, 'gid': info.st_gid}


def read_file(path, mode):
    before = metadata(path, stat.S_ISREG, mode)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        opened = os.fstat(stream.fileno())
        require((opened.st_dev, opened.st_ino) == (before['device'], before['inode']), 'file-changed')
        raw = stream.read(16385)
    require(len(raw) <= 16384 and metadata(path, stat.S_ISREG, mode) == before, 'file-changed')
    return raw, before


def absent(path):
    # Validate existing ancestors as well; a missing child below a link is not
    # evidence that this consumer never installed a runtime.
    path = Path(path)
    for item in reversed([path, *path.parents]):
        try:
            info = item.lstat()
        except FileNotFoundError:
            return
        require(item != path and stat.S_ISDIR(info.st_mode)
                and info.st_uid == 0 and not info.st_mode & 0o022, 'unexpected-path')
    raise ValueError('unexpected-path')


def command(argv):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=15,
                            env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'})
    require(result.returncode == 0, 'host-query')
    return result.stdout


def archive_value(config, raw, state_hash):
    return {'schemaVersion': config['schemaVersion'], 'state': 'SUPERSEDED',
            'phase': 'apply', 'target_head': config['staleHead'],
            'superseded_by_head': config['head'],
            'disposition': 'STALE_APPLY_BOOTSTRAP_ONLY',
            'source_record_sha256': digest(raw), 'observed_apply_shape': 'bootstrap-only',
            'expected_state_hash': state_hash, 'current_state_hash': state_hash}


def inspect(config):
    raw, record_meta = read_file(config['record'], 0o600)
    require(json.loads(raw) == {'schemaVersion': config['schemaVersion'],
            'state': 'RECOVERY_REQUIRED', 'phase': 'apply', 'target_head': config['staleHead']}, 'record')
    for path in config['absentPaths']:
        absent(path)
    for user in config['users']:
        try:
            pwd.getpwnam(user)
        except KeyError:
            continue
        raise ValueError('account-present')
    for group in config['groups']:
        try:
            grp.getgrnam(group)
        except KeyError:
            continue
        raise ValueError('group-present')
    state = {'record': record_meta, 'recordSha256': digest(raw), 'directories': {},
             'units': {}, 'consumer': config['repository'], 'head': config['head'],
             'recordPath': config['record'], 'port': config['port'],
             'absentPaths': config['absentPaths'], 'users': config['users'], 'groups': config['groups']}
    archive_root = Path(config['archiveRoot'])
    archive = archive_root / ('apply-' + config['staleHead'] + '.json')
    allowed = {
        config['stateRoot']: ('production-apply', 'superseded-operations'),
        config['stageRoot']: (),
        config['runtimeRoot']: ('production-operation.lock',),
        config['dropinRoot']: ('production-local-apply.conf',),
    }
    for name, entries in allowed.items():
        mode = 0o700 if name in (config['stateRoot'], config['stageRoot']) else 0o755
        state['directories'][name] = metadata(name, stat.S_ISDIR, mode)
        actual = {p.name for p in Path(name).iterdir()}
        require(actual <= set(entries), 'unexpected-contents')
        # The stage, lock and exact drop-in must exist. Only the archive is optional.
        require(actual == set(entries) - ({'superseded-operations'} if not archive_root.exists() else set()),
                'missing-evidence')
    dropin, dropin_meta = read_file(Path(config['dropinRoot']) / 'production-local-apply.conf', 0o644)
    require(dropin == config['dropinContent'].encode(), 'dropin-content')
    state['dropin'] = {**dropin_meta, 'sha256': digest(dropin)}
    state['lock'] = metadata(config['lock'], stat.S_ISREG, 0o644)
    for unit in config['units']:
        for root in ('/etc/systemd/system', '/run/systemd/system'):
            absent(Path(root) / unit)
        output = command(['/bin/systemctl', 'show', unit,
                          '--property=LoadState,ActiveState,SubState,UnitFileState,MainPID,FragmentPath'])
        values = dict(line.split('=', 1) for line in output.splitlines() if '=' in line)
        require(values.get('LoadState') == 'not-found' and values.get('ActiveState') == 'inactive'
                and values.get('SubState') == 'dead' and values.get('UnitFileState', '') in ('', 'not-found')
                and values.get('MainPID', '0') == '0' and values.get('FragmentPath', '') == '', 'unit-present')
        state['units'][unit] = values
    listeners = command(['/usr/bin/ss', '-ltnH'])
    require(not any(line.split()[3].endswith(':' + str(config['port']))
                    for line in listeners.splitlines() if len(line.split()) >= 4), 'listener-present')
    state_hash = digest(canonical(state))
    if os.path.lexists(archive_root):
        metadata(archive_root, stat.S_ISDIR, 0o700)
        require({p.name for p in archive_root.iterdir()} <= {archive.name}, 'archive-contents')
        if os.path.lexists(archive):
            previous, _ = read_file(archive, 0o600)
            require(json.loads(previous) == archive_value(config, raw, state_hash), 'archive-conflict')
    return raw, state_hash


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def execute(config, mode):
    require(os.geteuid() == 0 and mode in ('inspect', 'dispose'), 'authority')
    require(all(re.fullmatch('[0-9a-f]{40}', config[k]) for k in ('head', 'staleHead')), 'head')
    if mode == 'dispose':
        require(config['head'] != config['staleHead'] and config.get('authorized') is True
                and re.fullmatch('[0-9a-f]{64}', config.get('expectedStateHash', '')), 'authority')
    # Bind the narrow layout before inspecting it. These are compiler-owned paths.
    require(config['stageRoot'] == config['stateRoot'] + '/production-apply'
            and config['archiveRoot'] == config['stateRoot'] + '/superseded-operations'
            and config['lock'] == config['runtimeRoot'] + '/production-operation.lock', 'layout')
    lock_meta = metadata(config['lock'], stat.S_ISREG, 0o644)
    lock = os.open(config['lock'], os.O_RDONLY | os.O_NOFOLLOW)
    try:
        opened = os.fstat(lock)
        require((opened.st_dev, opened.st_ino) == (lock_meta['device'], lock_meta['inode']), 'lock-changed')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        raw, state_hash = inspect(config)
        if mode == 'dispose':
            require(state_hash == config['expectedStateHash'], 'state-changed')
            archive_root = Path(config['archiveRoot'])
            if not archive_root.exists():
                archive_root.mkdir(mode=0o700)
                sync_directory(archive_root.parent)
            archive = archive_root / ('apply-' + config['staleHead'] + '.json')
            value = archive_value(config, raw, state_hash)
            if not archive.exists():
                fd = os.open(archive, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(canonical(value) + b'\n')
                    stream.flush()
                    os.fsync(stream.fileno())
            saved, _ = read_file(archive, 0o600)
            require(json.loads(saved) == value, 'archive-conflict')
            sync_directory(archive_root)
            # Recheck the complete shape after committing evidence, before retirement.
            after_raw, after_hash = inspect(config)
            require(after_raw == raw and after_hash == state_hash, 'state-changed')
            os.unlink(config['record'])
            sync_directory(Path(config['record']).parent)
        return {'classification': 'bootstrap-only', 'stateHash': state_hash,
                'staleHead': config['staleHead'], 'head': config['head'], 'mode': mode}
    finally:
        os.close(lock)


if __name__ == '__main__':
    try:
        print(json.dumps(execute(json.loads(sys.argv[2]), sys.argv[1]), sort_keys=True))
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as error:
        code = str(error) if type(error) is ValueError else type(error).__name__
        print('PRODUCTION_BOOTSTRAP_RECOVERY_BLOCKED=' + code, file=sys.stderr)
        sys.exit(1)
