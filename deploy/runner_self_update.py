#!/usr/bin/env python3
"""Inspect or enable native runner updates without replacing its registration.

This is Relay-owned maintenance of the persisted upstream RunnerSettings, not
an upstream reconfiguration command. Both .runner and optional .runner_migrated
are handled because the latter is preferred at startup. The operator owns the
stopped maintenance window; this helper never changes service state, software,
credentials, labels, or GitHub state. Each settings replacement is atomic. An
interruption between files is completed by the same identity-bound invocation.
"""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import uuid


SETTINGS = ('.runner', '.runner_migrated')
SERVICE_FIELDS = ('LoadState', 'ActiveState', 'SubState', 'MainPID', 'ControlPID',
                  'ControlGroup', 'WorkingDirectory', 'User', 'Restart')
PUBLIC_SETTINGS = ('agentId', 'agentName', 'gitHubUrl', 'poolId', 'poolName', 'workFolder')


class UpdateError(RuntimeError):
    pass


def require(value, code):
    if not value:
        raise UpdateError('RUNNER_SELF_UPDATE_' + code)


def runner_uid(user):
    import pwd
    require(re.fullmatch(r'[a-z_][a-z0-9_-]*', user) is not None, 'USER_INVALID')
    try:
        uid = pwd.getpwnam(user).pw_uid
    except KeyError:
        raise UpdateError('RUNNER_SELF_UPDATE_USER_UNKNOWN') from None
    require(uid != 0, 'ROOT_RUNNER_PROHIBITED')
    return uid


@contextmanager
def runner_directory(root, uid, *, exclusive=False):
    """Pin a directory descriptor; never follow even an ancestor symlink."""
    require(sys.platform == 'linux', 'LINUX_REQUIRED')
    path = Path(root)
    require(path.is_absolute() and path != Path('/') and '..' not in path.parts
            and str(path) == root, 'ROOT_INVALID')
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open('/', flags)
    try:
        for component in path.parts[1:]:
            following = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = following
        info = os.fstat(descriptor)
        require(info.st_uid == uid and not info.st_mode & 0o022, 'ROOT_UNSAFE')
        if exclusive:
            import fcntl
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise UpdateError('RUNNER_SELF_UPDATE_MIGRATION_BUSY') from None
        yield descriptor
    finally:
        os.close(descriptor)


def unique_object(pairs):
    result, seen = {}, set()
    for key, value in pairs:
        require(key.casefold() not in seen, 'SETTINGS_DUPLICATE_KEY')
        seen.add(key.casefold())
        result[key] = value
    return result


def read_settings(directory, name, uid):
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=directory)
    except FileNotFoundError:
        require(name != '.runner', 'REGISTRATION_MISSING')
        return None
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                and info.st_uid == uid and stat.S_IMODE(info.st_mode) == 0o600,
                'SETTINGS_UNSAFE')
        require(info.st_size <= 65536, 'SETTINGS_TOO_LARGE')
        raw = stream.read(65537)
    require(len(raw) <= 65536, 'SETTINGS_TOO_LARGE')
    value = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=unique_object)
    canonical = {key.casefold(): key for key in (*PUBLIC_SETTINGS, 'disableUpdate')}
    require(isinstance(value, dict), 'SETTINGS_INVALID')
    require(all(key.casefold() not in canonical or canonical[key.casefold()] == key
                for key in value), 'SETTINGS_NONCANONICAL_KEY')
    require(isinstance(value, dict) and type(value.get('agentId')) is int
            and value['agentId'] > 0 and isinstance(value.get('agentName'), str)
            and bool(value['agentName']), 'IDENTITY_INVALID')
    require(type(value.get('disableUpdate', False)) is bool, 'FLAG_INVALID')
    return {'name': name, 'value': value, 'raw': raw, 'info': info}


def settings_snapshot(directory, uid, agent_id=None, agent_name=None):
    files = [entry for name in SETTINGS
             if (entry := read_settings(directory, name, uid)) is not None]
    original = files[0]['value']
    for entry in files:
        value = entry['value']
        require(all(value.get(key) == original.get(key) for key in PUBLIC_SETTINGS),
                'IDENTITY_CONFLICT')
        require(agent_id is None or value['agentId'] == agent_id, 'IDENTITY_MISMATCH')
        require(agent_name is None or value['agentName'] == agent_name, 'IDENTITY_MISMATCH')
    return files


def service_snapshot(service, root, user):
    require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.@-]*\.service', service) is not None,
            'SERVICE_INVALID')
    result = subprocess.run(['/usr/bin/systemctl', 'show', service,
                             '--property=' + ','.join(SERVICE_FIELDS)],
                            env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'},
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            text=True, timeout=15, check=False)
    require(result.returncode == 0, 'SERVICE_UNPROVEN')
    rows = [row.split('=', 1) for row in result.stdout.splitlines() if '=' in row]
    require(len({row[0] for row in rows}) == len(rows), 'SERVICE_UNPROVEN')
    value = dict(rows)
    require(all(key in value for key in SERVICE_FIELDS), 'SERVICE_UNPROVEN')
    require(value['LoadState'] == 'loaded' and value['WorkingDirectory'] == root
            and value['User'] == user, 'SERVICE_IDENTITY_MISMATCH')
    require(value['Restart'] in ['always', 'on-failure'], 'SERVICE_RESTART_UNSUPPORTED')
    return {key: value[key] for key in SERVICE_FIELDS}


def assert_no_runner_processes(root):
    """Other runners sharing the UID are allowed; only this root is matched."""
    prefix = root + '/'
    for process in Path('/proc').iterdir():
        if not process.name.isdigit() or int(process.name) == os.getpid():
            continue
        try:
            for field in ['cwd', 'exe']:
                target = os.readlink(process / field)
                require(target != root and not target.startswith(prefix), 'PROCESS_PRESENT')
            arguments = (process / 'cmdline').read_bytes().split(b'\0')
            require(not any(argument.startswith(os.fsencode(prefix)) for argument in arguments),
                    'PROCESS_PRESENT')
        except (FileNotFoundError, ProcessLookupError):
            continue
        except PermissionError:
            raise UpdateError('RUNNER_SELF_UPDATE_PROCESS_STATE_UNPROVEN') from None


def assert_stopped(service, root, user):
    value = service_snapshot(service, root, user)
    require(value['ActiveState'] in ['inactive', 'failed']
            and value['MainPID'] == '0' and value['ControlPID'] == '0', 'STOP_REQUIRED')
    expected = '/system.slice/' + service
    require(value['ControlGroup'] in ['', expected], 'SERVICE_CGROUP_UNPROVEN')
    cgroup = Path('/sys/fs/cgroup' + expected)
    if cgroup.exists():
        def unreadable(_error):
            raise UpdateError('RUNNER_SELF_UPDATE_SERVICE_CGROUP_UNPROVEN')
        for directory, _, _ in os.walk(cgroup, onerror=unreadable):
            require(not (Path(directory) / 'cgroup.procs').read_text().strip(),
                    'SERVICE_PROCESSES_PRESENT')
    assert_no_runner_processes(root)
    return value


def unchanged(directory, files, uid):
    current = settings_snapshot(directory, uid)
    require([entry['name'] for entry in current] == [entry['name'] for entry in files],
            'SETTINGS_CHANGED')
    for old, new in zip(files, current):
        require(old['raw'] == new['raw'] and old['info'].st_ino == new['info'].st_ino
                and old['info'].st_dev == new['info'].st_dev, 'SETTINGS_CHANGED')


def replace_settings(directory, entry):
    value = dict(entry['value'], disableUpdate=False)
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    temporary = '.relay-runner-update-' + uuid.uuid4().hex
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=directory)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            os.fchown(stream.fileno(), entry['info'].st_uid, entry['info'].st_gid)
            os.fchmod(stream.fileno(), 0o600)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, entry['name'], src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    finally:
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass


def inspect(root, service, user, agent_id=None, agent_name=None):
    uid = runner_uid(user)
    with runner_directory(root, uid) as directory:
        files = settings_snapshot(directory, uid, agent_id, agent_name)
        state = service_snapshot(service, root, user)
        unchanged(directory, files, uid)
    return {'status': 'RUNNER_SELF_UPDATE_INSPECTED', 'root': root, 'user': user,
            'service': service, 'serviceState': state,
            'preferredSettings': files[-1]['name'],
            'settings': [{'file': entry['name'],
                          **{key: entry['value'].get(key) for key in PUBLIC_SETTINGS},
                          'disableUpdate': entry['value'].get('disableUpdate', False)}
                         for entry in files]}


def migrate(root, service, user, agent_id, agent_name):
    require(os.geteuid() == 0, 'ROOT_REQUIRED')
    require(type(agent_id) is int and agent_id > 0 and bool(agent_name), 'EXPECTED_IDENTITY_REQUIRED')
    uid = runner_uid(user)
    changed = []
    with runner_directory(root, uid, exclusive=True) as directory:
        files = settings_snapshot(directory, uid, agent_id, agent_name)
        assert_stopped(service, root, user)
        for entry in files:
            unchanged(directory, files, uid)
            assert_stopped(service, root, user)
            if entry['value'].get('disableUpdate', False):
                expected = dict(entry['value'], disableUpdate=False)
                replace_settings(directory, entry)
                completed = read_settings(directory, entry['name'], uid)
                require(completed is not None and completed['value'] == expected,
                        'MIGRATION_UNPROVEN')
                changed.append(entry['name'])
                # Refresh our own completed replacement; other files must remain
                # byte-identical until their turn. A crash needs no rollback.
                entry.update(completed)
        unchanged(directory, files, uid)
        result = settings_snapshot(directory, uid, agent_id, agent_name)
        require(all(not entry['value'].get('disableUpdate', False) for entry in result),
                'MIGRATION_UNPROVEN')
        assert_stopped(service, root, user)
    return {'status': 'RUNNER_SELF_UPDATE_ENABLED', 'root': root, 'service': service,
            'agentId': agent_id, 'agentName': agent_name, 'changed': changed,
            'preferredSettings': result[-1]['name']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['inspect', 'migrate'])
    for name in ['root', 'service', 'user']:
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--agent-id', type=int)
    parser.add_argument('--agent-name')
    args = parser.parse_args(argv)
    if args.action == 'migrate' and (args.agent_id is None or args.agent_name is None):
        parser.error('migrate requires --agent-id and --agent-name')
    try:
        operation = migrate if args.action == 'migrate' else inspect
        result = operation(args.root, args.service, args.user, args.agent_id, args.agent_name)
        print(json.dumps(result, sort_keys=True))
        return 0
    except UpdateError as error:
        print(str(error), file=sys.stderr)
    except (OSError, ValueError, subprocess.SubprocessError):
        # Never print settings bytes, subprocess diagnostics, or credential data.
        print('RUNNER_SELF_UPDATE_INSPECTION_OR_MIGRATION_UNPROVEN', file=sys.stderr)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
