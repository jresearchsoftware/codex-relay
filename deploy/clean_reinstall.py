"""Owner-authorized runtime retirement; retained state is never recursive cleanup.

The public controller holds the host deployment mutex across retirement, fresh
apply and post-check. This helper additionally reserves the ordinary production
operation before stopping units or moving files. An interrupted invocation is
evidence for diagnosis, never implicit permission to retry.
"""
from contextlib import contextmanager
import fcntl
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shlex
import stat
import subprocess
import sys


def require(condition, code):
    if not condition:
        raise ValueError('REINSTALL_' + code)


def present(path):
    return path.exists() or path.is_symlink()


def protected(path, root, owner_uid, *, directory=False):
    require(path.is_relative_to(root), 'UNSAFE_PATH')
    first = True
    while True:
        info = path.lstat()
        kind = stat.S_ISDIR if directory or not first else stat.S_ISREG
        require(kind(info.st_mode) and info.st_uid == owner_uid and not info.st_mode & 0o022
                and (not first or directory or info.st_nlink == 1), 'UNSAFE_PATH')
        if path == root:
            return
        first = False
        path = path.parent


def fsync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_new(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, sort_keys=True)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        fsync_dir(path.parent)


def update_journal(path, journal, stage):
    journal['stage'] = stage
    temporary = path.with_name(path.name + '.next')
    write_new(temporary, journal)
    os.replace(temporary, path)
    fsync_dir(path.parent)


def namespace_paths(config, root):
    namespace = config['environment']['namespace']
    require(isinstance(namespace, str) and re.fullmatch('[a-z][a-z0-9-]{0,30}', namespace), 'NAMESPACE')
    return {
        'install': root / 'opt' / namespace,
        'config': root / 'etc' / namespace,
        'state': root / 'var/lib' / namespace,
        'operation': root / 'var/lib' / (namespace + '-production-operation.json'),
        'journal': root / 'var/lib' / (namespace + '-clean-reinstall.json'),
        'lock': root / 'run' / namespace / 'production-operation.lock',
    }


def unit_names(config):
    namespace = config['environment']['namespace']
    if config['environment'].get('instance'):
        return [namespace + suffix for suffix in [
            '-reviewer-recovery.timer', '-reviewer-recovery.service', '-reviewer.service',
            '-runner.service', '-general-runner.service', '-controller.service', '-openai-mtls-proxy.service']]
    return ['reviewer-mcp-recovery.timer', 'reviewer-mcp-recovery.service', 'reviewer-mcp.service',
            'relay-runner.service', 'relay-general-runner.service', 'relay-controller.service',
            'relay-openai-mtls-proxy.service']


def checked_systemctl(runner, *args):
    result = runner(['/bin/systemctl', *args], capture_output=True, text=True)
    require(result.returncode == 0, 'SERVICE_TRANSITION_FAILED')
    return result.stdout


def unknown_unit_text(path, root, owner_uid, metadata=None):
    """Read bounded regular content through protected unit roots and link chains."""
    roots = [root / value for value in ['etc/systemd/system', 'usr/lib/systemd/system',
                                       'lib/systemd/system']]
    def identity(info):
        # A successful read may update atime; mutation checks need nanosecond
        # modification/change times, not the lossy stat_result tuple or atime.
        return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_uid,
                info.st_gid, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    try:
        for _ in range(16):
            # Debian's usr-merge alias is the sole accepted directory symlink.
            if path.is_relative_to(root / 'lib') and (root / 'lib').is_symlink():
                protected(root, root, owner_uid, directory=True)
                alias = root / 'lib'
                require(alias.lstat().st_uid == owner_uid and os.readlink(alias) in
                        ['usr/lib', '/usr/lib'], 'UNKNOWN_UNIT_UNCLASSIFIABLE')
                path = root / 'usr/lib' / path.relative_to(root / 'lib')
            require(any(path.is_relative_to(base) for base in roots)
                    and path.suffix == '.service', 'UNKNOWN_UNIT_UNCLASSIFIABLE')
            protected(path.parent, root, owner_uid, directory=True)
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode):
                require(info.st_uid == owner_uid, 'UNKNOWN_UNIT_UNCLASSIFIABLE')
                target = Path(os.readlink(path))
                logical = root / str(target).lstrip('/') if target.is_absolute() else path.parent / target
                path = Path(os.path.normpath(logical))
                # A systemd mask is classified by device identity, without reading it.
                if path == root / 'dev/null':
                    protected(path.parent, root, owner_uid, directory=True)
                    masked = path.lstat()
                    require(stat.S_ISCHR(masked.st_mode) and masked.st_uid == owner_uid
                            and masked.st_rdev == os.makedev(1, 3), 'UNKNOWN_UNIT_UNCLASSIFIABLE')
                    return ''
                continue
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                    and info.st_size <= 1024 * 1024, 'UNKNOWN_UNIT_UNCLASSIFIABLE')
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, 'rb') as stream:
                require(identity(os.fstat(stream.fileno())) == identity(info), 'UNKNOWN_UNIT_UNCLASSIFIABLE')
                content = stream.read(1024 * 1024 + 1)
                require(len(content) <= 1024 * 1024 and identity(os.fstat(stream.fileno())) == identity(info)
                        and identity(path.lstat()) == identity(info), 'UNKNOWN_UNIT_UNCLASSIFIABLE')
                text = content.decode('utf-8')
                if metadata is not None:
                    metadata.update(path=path, info=info)
                return text
    except (OSError, UnicodeError, ValueError):
        raise ValueError('REINSTALL_UNKNOWN_UNIT_UNCLASSIFIABLE;inspect-top-level-systemd-service-links') from None
    raise ValueError('REINSTALL_UNKNOWN_UNIT_UNCLASSIFIABLE;inspect-top-level-systemd-service-links')


def foreign_unit_warning(unit, metadata, root, owner_uid):
    info = metadata.get('info')
    if info is None or (info.st_uid == owner_uid and not info.st_mode & 0o022):
        return None
    writers, lookup = [], 'not-group-writable'
    if info.st_mode & 0o020:
        try:
            group = grp.getgrgid(info.st_gid)
            writers = sorted({account.pw_uid for account in pwd.getpwall()
                              if (account.pw_gid == info.st_gid or account.pw_name in group.gr_mem)
                              and account.pw_uid != info.st_uid})
            lookup = 'listed-other-writers' if writers else 'no-other-listed-account'
        except KeyError:
            lookup = 'group-unavailable'
    return {'unit': '/' + str(unit.relative_to(root)),
            'inspectedPath': '/' + str(metadata['path'].relative_to(root)),
            'uid': info.st_uid, 'gid': info.st_gid, 'mode': format(stat.S_IMODE(info.st_mode), '04o'),
            'groupWriters': writers, 'groupLookup': lookup}


def emit_foreign_unit_warning(warning):
    print('REINSTALL_FOREIGN_UNIT_WARNING;' + json.dumps(warning, sort_keys=True)
          + ';review-unit-provenance-and-writers;current-content-unrelated;'
          'content-and-group-membership-can-change-after-inspection', file=sys.stderr)


def inspect_units(config, paths, root, owner_uid, runner, *, stopped=False, listeners=None, warnings=None):
    units = {}
    names = unit_names(config)
    prefix = '/opt/' + config['environment']['namespace'] + '/'
    systemd_root = root / 'etc/systemd/system'
    protected(systemd_root, root, owner_uid, directory=True)
    for path in systemd_root.glob('*.service'):
        if path.name in names:
            continue
        # A missing deployment snapshot cannot let a newly selected unit name
        # hide a differently named service still using this runtime namespace.
        metadata = {}
        if any(prefix in line and not line.lstrip().startswith(('#', ';'))
               for line in unknown_unit_text(path, root, owner_uid, metadata).splitlines()):
            raise ValueError('REINSTALL_UNSUPPORTED_RUNTIME_UNIT')
        warning = foreign_unit_warning(path, metadata, root, owner_uid)
        if warning is not None:
            identity = json.dumps(warning, sort_keys=True)
            if warnings is None or identity not in warnings:
                emit_foreign_unit_warning(warning)
                if warnings is not None:
                    warnings.add(identity)
    for name in names:
        path = root / 'etc/systemd/system' / name
        result = runner(['/bin/systemctl', 'show', name, '--no-pager',
                         '--property=LoadState,ActiveState,MainPID,ControlPID,FragmentPath,DropInPaths,ControlGroup'],
                        capture_output=True, text=True)
        require(result.returncode == 0, 'UNIT_OBSERVATION_UNAVAILABLE')
        fields = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
        if fields.get('LoadState') == 'not-found':
            require(not present(path), 'UNIT_IDENTITY_UNPROVEN')
            continue
        require(fields.get('LoadState') == 'loaded' and present(path), 'UNIT_IDENTITY_UNPROVEN')
        protected(path, root, owner_uid)
        lines = path.read_text().splitlines()
        binding = ('Unit=' + name.removesuffix('.timer') + '.service' in lines if name.endswith('.timer')
                   else any(line.startswith('ExecStart=' + prefix) for line in lines))
        require(binding and fields.get('FragmentPath') == '/etc/systemd/system/' + name,
                'UNIT_IDENTITY_UNPROVEN')
        identities = {names[2]: config['environment']['reviewerUser'],
                      names[3]: config['environment']['runner']['user'],
                      names[4]: config['environment']['generalRunner']['user']}
        if name in identities:
            require('User=' + identities[name] in lines, 'UNIT_IDENTITY_UNPROVEN')
        # The sole supported drop-in belongs to the fixed production-apply
        # boundary. Unknown persistent or transient overrides block retirement.
        allowed = '/etc/systemd/system/' + names[3] + '.d/production-local-apply.conf'
        drops = fields.get('DropInPaths', '').split()
        require(all(value == allowed for value in drops), 'UNIT_OVERRIDE_UNSUPPORTED')
        for drop in drops:
            protected(root / drop.lstrip('/'), root, owner_uid)
        require(fields.get('ActiveState') in ['active', 'inactive', 'failed']
                and fields.get('ControlPID') == '0', 'UNIT_TRANSITION_PENDING')
        require(re.fullmatch('[0-9]+', fields.get('MainPID', '')), 'UNIT_IDENTITY_UNPROVEN')
        if stopped:
            require(fields.get('ActiveState') in ['inactive', 'failed'] and fields.get('MainPID') == '0',
                    'WORKERS_NOT_QUIESCENT')
        elif name in names[3:5] and fields['ActiveState'] == 'active':
            runner_root = '/opt/' + config['environment']['namespace'] + '/' + (
                'runner' if name == names[3] else 'general-runner')
            require('ExecStart=' + runner_root + '/run.sh' in lines
                    and fields['MainPID'] != '0'
                    and fields.get('ControlGroup') == '/system.slice/' + name,
                    'WORKERS_NOT_QUIESCENT')
            if listeners is not None:
                listeners[name] = {'pid': fields['MainPID'], 'root': runner_root,
                                   'user': identities[name], 'cgroup': fields['ControlGroup']}
        elif name in names[3:5]:
            require(fields['MainPID'] == '0', 'WORKERS_NOT_QUIESCENT')
        elif name in [names[1], *names[5:]]:
            require(fields['ActiveState'] in ['inactive', 'failed'] and fields['MainPID'] == '0',
                    'WORKERS_NOT_QUIESCENT')
        units[name] = fields['ActiveState']
    return units


def workers_quiescent(config, root, user_ids=None, *, listeners=None, stopped_units=None):
    names = [config['consumer']['runtimeUser'], config['environment']['runner']['user'],
             config['environment']['generalRunner']['user']]
    ids = {}
    for name in names:
        try:
            value = user_ids[name] if user_ids is not None else pwd.getpwnam(name).pw_uid
            ids[name] = value[0] if isinstance(value, tuple) else value
        except KeyError:
            raise ValueError('REINSTALL_WORKER_IDENTITY_UNPROVEN') from None
    require(0 not in ids.values(), 'WORKER_IDENTITY_UNPROVEN')
    proc = root / 'proc'
    require(proc.is_dir(), 'PROCESS_OBSERVATION_UNAVAILABLE')
    observed = {}
    members = {name: set() for name in listeners or {}}
    for path in proc.iterdir():
        if not path.name.isdecimal():
            continue
        protected_process = False
        try:
            uid = path.stat().st_uid
            protected_process = uid in ids.values()
            groups = (path / 'cgroup').read_text().splitlines() if listeners or stopped_units else []
            for line in groups:
                group = line.split(':', 2)[2]
                for name, listener in (listeners or {}).items():
                    if group == listener['cgroup'] or group.startswith(listener['cgroup'] + '/'):
                        # Account for every managed member before filtering by
                        # UID, including foreign identities and child cgroups.
                        members[name].add(path.name)
                        protected_process = True
            status = dict(line.split(':', 1) for line in (path / 'status').read_text().splitlines() if ':' in line)
            uids = [int(value) for value in status['Uid'].split()]
            if stopped_units:
                # MainPID zero does not prove that a unit has no surviving
                # children (including Reviewer/root-owned service children).
                for line in groups:
                    group = line.split(':', 2)[2]
                    require(not any(group == '/system.slice/' + name or
                                    group.startswith('/system.slice/' + name + '/')
                                    for name in stopped_units), 'WORKERS_NOT_QUIESCENT')
            protected_process = protected_process or bool(set(uids) & set(ids.values()))
            if not protected_process:
                continue
            require(listeners, 'WORKERS_NOT_QUIESCENT')
            # Only the fixed idle runner chain, in its proven systemd cgroup,
            # may survive admission. Names alone do not establish idle state.
            def birth():
                fields = (path / 'stat').read_text().rsplit(') ', 1)[1].split()
                require(fields[0] not in ['Z', 'X'], 'WORKERS_NOT_QUIESCENT')
                return fields[19]
            before = birth()
            require(uids == [uid] * 4,
                    'WORKERS_NOT_QUIESCENT')
            argv = (path / 'cmdline').read_bytes().rstrip(b'\0').decode().split('\0')
            exe = os.readlink(path / 'exe')
            cwd = os.readlink(path / 'cwd')
            matches = [value for value in listeners.values() if ids[value['user']] == uid
                       and any(line == '0::' + value['cgroup'] or
                               line.split(':', 2)[1:] == ['name=systemd', value['cgroup']]
                               for line in groups)]
            require(len(matches) == 1, 'WORKERS_NOT_QUIESCENT')
            listener = matches[0]
            base = listener['root']
            # The supported run.sh unit has no arguments. Relative paths are
            # resolved only against that exact runner working directory.
            require(cwd == base and argv, 'WORKERS_NOT_QUIESCENT')
            executable = argv[0] if argv[0].startswith('/') else base + '/' + argv[0].removeprefix('./')
            shell = exe in ['/usr/bin/bash', '/bin/bash']
            if shell:
                require(len(argv) == 2 and argv[0] in ['/bin/bash', '/usr/bin/bash', 'bash'],
                        'WORKERS_NOT_QUIESCENT')
                script = argv[1] if argv[1].startswith('/') else base + '/' + argv[1].removeprefix('./')
                require(script in [base + '/run.sh', base + '/run-helper.sh'], 'WORKERS_NOT_QUIESCENT')
                role = script.removeprefix(base + '/')
            else:
                require(exe == base + '/bin/Runner.Listener' and executable == exe
                        and argv[1:] == ['run'], 'WORKERS_NOT_QUIESCENT')
                role = 'listener'
            require(birth() == before and path.stat().st_uid == uid,
                    'WORKERS_NOT_QUIESCENT')
            observed[path.name] = (status['PPid'].strip(), listener['pid'], role)
        except FileNotFoundError:
            # A disappearing protected identity or managed cgroup member
            # leaves its execution state ambiguous; guessing is not safe.
            require(not protected_process, 'WORKERS_NOT_QUIESCENT')
        except (OSError, KeyError, UnicodeError, IndexError):
            raise ValueError('REINSTALL_WORKERS_NOT_QUIESCENT') from None
    if listeners:
        for name, listener in listeners.items():
            require(listener['pid'] in observed and observed[listener['pid']][2] == 'run.sh',
                    'WORKERS_NOT_QUIESCENT')
            require(len(members[name]) == 3 and all(
                pid in observed and observed[pid][1] == listener['pid'] for pid in members[name]),
                'WORKERS_NOT_QUIESCENT')
            require({observed[pid][2] for pid in members[name]} == {'run.sh', 'run-helper.sh', 'listener'},
                    'WORKERS_NOT_QUIESCENT')
        for pid, (parent, main, role) in observed.items():
            if pid != main:
                require(parent in observed and (role, observed[parent][2]) in [
                    ('run-helper.sh', 'run.sh'), ('listener', 'run-helper.sh')], 'WORKERS_NOT_QUIESCENT')
            visited = set()
            while pid != main:
                require(pid in observed and pid not in visited and observed[pid][1] == main,
                        'WORKERS_NOT_QUIESCENT')
                visited.add(pid)
                pid = observed[pid][0]


def retained_paths_outside_runtime(config, install):
    paths = config['consumer']['paths']
    retained = [paths[key] for key in ['credentialEnv', 'credentialKeyFile', 'attemptRoot',
                                      'claimRoot', 'workRoot', 'diagnosticsRoot']]
    environment = config['environment']
    for name, field in [('reviewerCredential', 'sourceKeyFile'), ('writerCredential', 'sourceKeyFile'),
                        ('codexCredential', 'sourceTokenFile')]:
        if name in environment:
            retained.append(environment[name][field])
    retained.extend(environment.get('tls', {}).get('source', {}).values())
    retained.extend(environment['ingress']['protectedPaths'])
    logical_install = Path('/opt') / environment['namespace']
    for value in retained:
        path = Path(value)
        require(not path.is_relative_to(logical_install) and not logical_install.is_relative_to(path),
                'PROTECTED_STATE_OVERLAPS_RUNTIME')


def runtime_layout(install, root, owner_uid):
    """Unknown namespace contents need owner diagnosis; never silently absorb them."""
    directories = {'releases', 'codex-runtime', 'runner', 'general-runner'}
    for path in install.iterdir():
        if path.name == 'current' or path.name in ['runner', 'general-runner']:
            continue
        if path.name in directories:
            protected(path, root, owner_uid, directory=True)
        else:
            require(path.name.startswith('relay-'), 'UNSUPPORTED_RUNTIME_ENTRY')
            protected(path, root, owner_uid)


@contextmanager
def operation_lock(path, root, owner_uid):
    protected(path.parent, root, owner_uid, directory=True)
    try:
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
        os.fchmod(fd, 0o644)
    except FileExistsError:
        fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == owner_uid and info.st_nlink == 1
                and stat.S_IMODE(info.st_mode) in [0o600, 0o644], 'OPERATION_LOCK_UNSAFE')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('REINSTALL_OPERATION_BUSY') from None
        require(path.lstat().st_ino == info.st_ino, 'OPERATION_LOCK_CHANGED')
        yield
    finally:
        os.close(fd)


def decommission(config, revision, report, *, root=Path('/'), owner_uid=0,
                 runner=subprocess.run, user_ids=None):
    """Retire runtime under an already-held public host deployment mutex."""
    root = Path(root)
    require(re.fullmatch('[0-9a-f]{40}', revision or ''), 'TARGET_INVALID')
    require(not report.get('blockers') and report.get('configuration', {}).get('consumer') == 'equivalent'
            and report.get('configuration', {}).get('deployment') in ['equivalent', 'unavailable']
            and report.get('installed', {}).get('status') == 'present', 'INVENTORY_NOT_PROVEN')
    paths = namespace_paths(config, root)
    for key in ['install', 'config', 'state']:
        protected(paths[key], root, owner_uid, directory=True)
    protected(paths['operation'].parent, root, owner_uid, directory=True)
    require(not present(paths['journal']) and not present(paths['journal'].with_name(paths['journal'].name + '.next'))
            and not present(paths['operation']), 'RECOVERY_REQUIRED')
    retained_paths_outside_runtime(config, paths['install'])
    runtime_layout(paths['install'], root, owner_uid)
    current = paths['install'] / 'current'
    info = current.lstat()
    require(stat.S_ISLNK(info.st_mode) and info.st_uid == owner_uid, 'INSTALLED_IDENTITY_UNPROVEN')
    release = current.resolve(strict=True)
    require(release.parent == paths['install'] / 'releases' and re.fullmatch('[0-9a-f]{40}', release.name),
            'INSTALLED_IDENTITY_UNPROVEN')
    protected(release, root, owner_uid, directory=True)
    manifest_path = release / 'artifact-manifest.json'
    protected(manifest_path, root, owner_uid)
    manifest = json.loads(manifest_path.read_text())
    require(manifest.get('commit') == release.name and all(manifest.get(key, release.name) == release.name
            for key in ['installedRevision', 'resolvedRevision']),
            'INSTALLED_IDENTITY_UNPROVEN')
    identity_path = release / 'reviewed-source/.relay-source.json'
    protected(identity_path, root, owner_uid)
    identity = json.loads(identity_path.read_text())
    require(report['installed'].get('revision') == release.name and identity.get('revision') == release.name
            and isinstance(manifest.get('gitTree'), str) and re.fullmatch('[0-9a-f]{40}', manifest['gitTree'])
            and identity.get('tree') == manifest['gitTree'], 'INSTALLED_IDENTITY_UNPROVEN')
    require(release.name != revision, 'CURRENT_INSTALLATION_USE_APPLY')
    archive = paths['install'].parent / ('.' + paths['install'].name + '-retired-' + release.name + '-' + revision)
    require(not present(archive), 'RECOVERY_ARCHIVE_EXISTS')
    # Runner roots are retained as complete trees. Relative registration paths,
    # credential material and runner package identity therefore remain intact.
    runners = []
    for name, identity in [('runner', config['environment']['runner']['user']),
                           ('general-runner', config['environment']['generalRunner']['user'])]:
        path = paths['install'] / name
        if present(path):
            metadata = path.lstat()
            value = user_ids[identity] if user_ids is not None else pwd.getpwnam(identity).pw_uid
            uid = value[0] if isinstance(value, tuple) else value
            require(stat.S_ISDIR(metadata.st_mode) and metadata.st_uid == uid
                    and not metadata.st_mode & 0o022, 'RUNNER_ROOT_UNSAFE')
            runners.append(name)
    markers = []
    for name in ['reviewer-activation-authorized', 'reviewer-recovery-requires-activation']:
        path = paths['config'] / name
        if present(path):
            protected(path, root, owner_uid)
            require(stat.S_IMODE(path.stat().st_mode) == 0o600, 'ACTIVATION_MARKER_UNSAFE')
            markers.append(name)
    listeners = {}
    warnings = set()
    units = inspect_units(config, paths, root, owner_uid, runner, listeners=listeners, warnings=warnings)
    workers_quiescent(config, root, user_ids, listeners=listeners)
    journal = {'schemaVersion': 1, 'stage': 'RESERVED', 'sourceRevision': release.name,
               'targetRevision': revision,
               'previousEnvironmentComparison': report['configuration']['deployment'],
               'configurationSha256': hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
               'archive': '/' + str(archive.relative_to(root)), 'runners': runners,
               'activationMarkers': markers, 'units': units}
    with operation_lock(paths['lock'], root, owner_uid):
        require(not present(paths['operation']) and not present(paths['journal']), 'RECOVERY_REQUIRED')
        listeners = {}
        require(inspect_units(config, paths, root, owner_uid, runner, listeners=listeners, warnings=warnings) == units,
                'UNIT_STATE_CHANGED')
        workers_quiescent(config, root, user_ids, listeners=listeners)
        # Any interruption from this point leaves a durable reservation. Neither
        # this helper nor public reinstall automatically resets or replays it.
        write_new(paths['journal'], journal)
        write_new(paths['operation'], {'schemaVersion': '1', 'state': 'RECOVERY_REQUIRED',
                                      'phase': 'apply', 'target_head': revision})
        for name in units:
            for action in ['stop', 'disable']:
                journal['serviceTransition'] = {'unit': name, 'action': action}
                update_journal(paths['journal'], journal, 'RESERVED')
                checked_systemctl(runner, action, name)
        units_after = inspect_units(config, paths, root, owner_uid, runner, stopped=True, warnings=warnings)
        require(all(value in ['inactive', 'failed'] for value in units_after.values()), 'SERVICES_NOT_STOPPED')
        workers_quiescent(config, root, user_ids, stopped_units=units_after)
        journal.pop('serviceTransition')
        update_journal(paths['journal'], journal, 'SERVICES_STOPPED')
        archive.mkdir(mode=0o700)
        fsync_dir(archive.parent)
        for name in markers:
            os.rename(paths['config'] / name, archive / name)
        fsync_dir(paths['config'])
        fsync_dir(archive)
        metadata = paths['install'].stat()
        os.rename(paths['install'], archive / 'runtime')
        fsync_dir(archive)
        fsync_dir(paths['install'].parent)
        update_journal(paths['journal'], journal, 'RUNTIME_RETIRED')
        paths['install'].mkdir(mode=stat.S_IMODE(metadata.st_mode))
        os.chown(paths['install'], metadata.st_uid, metadata.st_gid)
        for name in runners:
            os.rename(archive / 'runtime' / name, paths['install'] / name)
            fsync_dir(archive / 'runtime')
            fsync_dir(paths['install'])
        fsync_dir(paths['install'].parent)
        update_journal(paths['journal'], journal, 'DECOMMISSIONED')
        journal_digest = hashlib.sha256(paths['journal'].read_bytes()).hexdigest()
    return {'state': 'DECOMMISSIONED', 'sourceRevision': release.name, 'targetRevision': revision,
            'recoveryPath': '/' + str(paths['journal'].relative_to(root)), 'journalSha256': journal_digest}


def _complete(config, revision, *, root=Path('/'), owner_uid=0):
    """Archive recovery evidence only after caller's clean apply/post-check proof."""
    root = Path(root)
    paths = namespace_paths(config, root)
    protected(paths['journal'], root, owner_uid)
    journal = json.loads(paths['journal'].read_text())
    require(journal.get('stage') == 'DECOMMISSIONED' and journal.get('targetRevision') == revision
            and journal.get('configurationSha256') == hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
            'COMPLETION_BINDING_CHANGED')
    require(not present(paths['operation']), 'OPERATION_STILL_PENDING')
    current = paths['install'] / 'current'
    require(current.is_symlink() and current.lstat().st_uid == owner_uid, 'FINAL_IDENTITY_UNPROVEN')
    release = current.resolve(strict=True)
    require(release == paths['install'] / 'releases' / revision, 'FINAL_IDENTITY_UNPROVEN')
    protected(release / 'artifact-manifest.json', root, owner_uid)
    manifest = json.loads((release / 'artifact-manifest.json').read_text())
    require(all(manifest.get(key) == revision for key in ['commit', 'installedRevision', 'resolvedRevision']),
            'FINAL_IDENTITY_UNPROVEN')
    expected_archive = paths['install'].parent / ('.' + paths['install'].name + '-retired-' + journal['sourceRevision'] + '-' + revision)
    require(journal['archive'] == '/' + str(expected_archive.relative_to(root)), 'ARCHIVE_BINDING_CHANGED')
    protected(expected_archive, root, owner_uid, directory=True)
    require(not present(expected_archive / 'decommission.json'), 'ARCHIVE_RECORD_EXISTS')
    update_journal(paths['journal'], journal, 'COMPLETE')
    os.rename(paths['journal'], expected_archive / 'decommission.json')
    fsync_dir(expected_archive)
    fsync_dir(paths['journal'].parent)
    return {'state': 'COMPLETE', 'installedRevision': revision, 'archive': journal['archive']}


def complete(config, revision, *, root=Path('/'), owner_uid=0):
    paths = namespace_paths(config, Path(root))
    with operation_lock(paths['lock'], Path(root), owner_uid):
        return _complete(config, revision, root=root, owner_uid=owner_uid)


def validate_remote_result(result, config, revision, report, action):
    require(isinstance(result, dict), 'REMOTE_RESULT_INVALID')
    namespace = config['environment']['namespace']
    if action == 'decommission':
        require(result.keys() == {'state', 'sourceRevision', 'targetRevision', 'recoveryPath', 'journalSha256'}
                and result['state'] == 'DECOMMISSIONED' and result['targetRevision'] == revision
                and isinstance(report, dict) and report.get('installed', {}).get('status') == 'present'
                and result['sourceRevision'] == report['installed'].get('revision')
                and isinstance(result['journalSha256'], str)
                and re.fullmatch('[0-9a-f]{64}', result['journalSha256'])
                and result['recoveryPath'] == '/var/lib/' + namespace + '-clean-reinstall.json',
                'REMOTE_RESULT_INVALID')
    else:
        require(result.keys() == {'state', 'installedRevision', 'archive'}
                and result['state'] == 'COMPLETE' and result['installedRevision'] == revision
                and isinstance(report, dict) and report.get('installed', {}).get('status') == 'present'
                and result['archive'] == '/opt/.' + namespace + '-retired-' + report['installed']['revision'] + '-' + revision,
                'REMOTE_RESULT_INVALID')
    return result


def safe_reinstall_diagnostic(value):
    """Admit bounded codes and only the helper's established actionable hints."""
    if not isinstance(value, str) or not re.fullmatch(r'REINSTALL_[A-Z0-9_]{1,96}(?:;[^;\n\r]+)?', value):
        return None
    code, separator, hint = value.partition(';')
    default = 'inspect-retained-operation-and-reinstall-evidence'
    if separator and hint not in [default, 'inspect-top-level-systemd-service-links', 'inspect-before-retry']:
        return None
    return code + ';' + (hint if separator else default)


def parse_remote_warning(line):
    prefix = 'REINSTALL_FOREIGN_UNIT_WARNING;'
    suffix = (';review-unit-provenance-and-writers;current-content-unrelated;'
              'content-and-group-membership-can-change-after-inspection')
    if not line.startswith(prefix) or not line.endswith(suffix) or len(line) > 65536:
        return None

    def unique_fields(pairs):
        fields = {}
        for key, value in pairs:
            if key in fields:
                raise ValueError('duplicate warning field')
            fields[key] = value
        return fields

    try:
        warning = json.loads(line[len(prefix):-len(suffix)], object_pairs_hook=unique_fields)
    except (ValueError, RecursionError):
        return None
    keys = {'unit', 'inspectedPath', 'uid', 'gid', 'mode', 'groupWriters', 'groupLookup'}
    if not isinstance(warning, dict) or warning.keys() != keys:
        return None

    def unit_path(value, roots, *, nested=False):
        if not isinstance(value, str) or len(value) > 4096:
            return False
        for root in roots:
            if value.startswith(root):
                name = value[len(root):]
                parts = name.split('/')
                return ((nested or len(parts) == 1)
                        and all(0 < len(part) <= 255 and part not in ['.', '..']
                                and part.isprintable() for part in parts)
                        and parts[-1].endswith('.service') and parts[-1] != '.service')
        return False

    roots = ['/etc/systemd/system/', '/usr/lib/systemd/system/', '/lib/systemd/system/']
    if not unit_path(warning['unit'], roots[:1]) or not unit_path(warning['inspectedPath'], roots, nested=True):
        return None
    if any(type(warning[key]) is not int or warning[key] < 0 for key in ['uid', 'gid']):
        return None
    if not isinstance(warning['mode'], str) or not re.fullmatch('[0-7]{4}', warning['mode']):
        return None
    writers = warning['groupWriters']
    if not isinstance(writers, list) or any(type(uid) is not int or uid < 0 for uid in writers):
        return None
    if warning['groupLookup'] not in ['not-group-writable', 'listed-other-writers',
                                     'no-other-listed-account', 'group-unavailable']:
        return None
    return warning


def forward_remote_diagnostics(error, returncode):
    """Forward validated warnings without reflecting arbitrary remote stderr."""
    lines = error.splitlines()
    diagnostics = []
    for line in lines:
        warning = parse_remote_warning(line)
        if warning is not None:
            emit_foreign_unit_warning(warning)
        elif returncode != 0:
            diagnostic = safe_reinstall_diagnostic(line)
            if diagnostic is not None:
                diagnostics.append(diagnostic)
    # SSH banners and opaque/malformed lines are never reflected or treated as
    # new blockers. Failure still needs one unambiguous final helper diagnostic.
    if returncode != 0:
        diagnostic = safe_reinstall_diagnostic(lines[-1]) if lines else None
        if diagnostic is None or len(diagnostics) != 1:
            raise ValueError('REINSTALL_REMOTE_ACTION_FAILED;inspect-retained-operation-and-reinstall-evidence')
        raise ValueError(diagnostic)


def remote_action(target, key, config, revision, report=None, *, action='decommission', guard=None):
    """Transport config references only; helper never receives token material."""
    require(action in ['decommission', 'complete'], 'ACTION_INVALID')
    source = Path(__file__).read_text()
    inventory_source = Path(__file__).with_name('inventory.py').read_text()
    program = source + '\nimport sys\ntry:\n'
    program += '    value = json.load(sys.stdin)\n'
    if action == 'decommission':
        program += '    probe = {"__name__": "relay_inventory"}\n'
        program += '    exec(' + repr(inventory_source) + ', probe)\n'
        program += '    current_report = probe["inspect"](value["config"])\n'
        program += '    result = decommission(value["config"], value["revision"], current_report)\n'
    else:
        program += '    result = complete(value["config"], value["revision"])\n'
    program += '    print(json.dumps(result, sort_keys=True))\n'
    program += ('except (ValueError, OSError, KeyError, TypeError, AttributeError) as error:\n'
                '    diagnostic = safe_reinstall_diagnostic(str(error)) or safe_reinstall_diagnostic("REINSTALL_BLOCKED")\n'
                '    print(diagnostic, file=sys.stderr)\n'
                '    raise SystemExit(1)\n')
    command = ['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'IdentitiesOnly=yes',
               '-i', str(key), target['user'] + '@' + target['host'],
               shlex.join(['/usr/bin/python3', '-I', '-c', program])]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True)
    payload = json.dumps({'config': config, 'revision': revision, 'report': report})
    try:
        while True:
            if guard is not None and guard.poll() is not None:
                raise ValueError('REINSTALL_HOST_LOCK_LOST;inspect-before-retry')
            try:
                output, error = process.communicate(input=payload, timeout=1)
                break
            except subprocess.TimeoutExpired:
                payload = None
        forward_remote_diagnostics(error, process.returncode)
        require(guard is None or guard.poll() is None, 'HOST_LOCK_LOST;inspect-before-retry')
        return validate_remote_result(json.loads(output), config, revision, report, action)
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
