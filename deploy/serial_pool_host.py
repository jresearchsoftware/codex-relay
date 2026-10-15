"""Fixed owner adapters for the registered SERIAL runner transition.

The transition core owns durable stop/removal reservations and gate drain.
These adapters reobserve the exact retained runner and never remove local
registration credentials, runner files or execution evidence.
"""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import pwd
import re
import stat

from config import compile_inputs
from managed_pool import Host, require


def _stamp(value):
    return tuple(getattr(value, 'st_' + field) for field in
                 ['dev', 'ino', 'mode', 'uid', 'gid', 'nlink', 'size', 'mtime_ns', 'ctime_ns'])


def _object(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'SERIAL_TRANSITION_REGISTRATION_INVALID')
            result[key] = value
        return result
    try:
        value = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=unique)
    except (ValueError, UnicodeError, RecursionError):
        require(False, 'SERIAL_TRANSITION_REGISTRATION_INVALID')
    require(isinstance(value, dict), 'SERIAL_TRANSITION_REGISTRATION_INVALID')
    return value


class SerialPoolGitHub:
    """Scope-correct native identity observation and one exact-id removal."""
    def __init__(self, api):
        self.api = api

    def _prefix(self, binding):
        repository = binding['repository']
        require(type(binding.get('runnerId')) is int and binding['runnerId'] > 0
                and isinstance(binding.get('runnerName'), str) and bool(binding['runnerName']),
                'SERIAL_TRANSITION_REMOTE_BINDING_UNPROVEN')
        require(isinstance(repository, str) and re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository),
                'SERIAL_TRANSITION_REMOTE_SCOPE_INVALID')
        require(binding.get('organization') == repository.split('/')[0], 'SERIAL_TRANSITION_REMOTE_SCOPE_INVALID')
        require(binding.get('scope') in ['repository', 'organization'], 'SERIAL_TRANSITION_REMOTE_SCOPE_INVALID')
        return ('/repos/' + repository if binding['scope'] == 'repository'
                else '/orgs/' + binding['organization']) + '/actions/runners'

    def observe_legacy(self, binding):
        # pages() enforces native total_count agreement. Missing read permission
        # raises before any registration/service/pool mutation by the core.
        rows = self.api.pages(self._prefix(binding), 'runners')
        require(isinstance(rows, list) and all(isinstance(row, dict) for row in rows),
                'SERIAL_TRANSITION_REMOTE_BINDING_UNPROVEN')
        matches = [row for row in rows if row.get('id') == binding['runnerId']
                   or row.get('name') == binding['runnerName']]
        if not matches:
            return None
        require(len(matches) == 1, 'SERIAL_TRANSITION_REMOTE_BINDING_UNPROVEN')
        value = matches[0]
        require(type(value.get('id')) is int and value['id'] == binding['runnerId']
                and value.get('name') == binding['runnerName'] and type(value.get('busy')) is bool,
                'SERIAL_TRANSITION_REMOTE_BINDING_UNPROVEN')
        return {key: value[key] for key in ['id', 'name', 'busy']}

    def remove_legacy(self, binding):
        # Called only after the core's durable remove-intent and target-ready
        # proof. An uncertain DELETE is reobserved by that original operation;
        # this adapter never retries it or cleans local credential markers.
        value = self.observe_legacy(binding)
        require(value is not None and value['busy'] is False, 'SERIAL_TRANSITION_LEGACY_BUSY')
        result = self.api.request('DELETE', self._prefix(binding) + '/' + str(binding['runnerId']))
        require(result is None, 'SERIAL_TRANSITION_REMOVE_UNCERTAIN_INSPECT_BEFORE_RETRY')


class SerialPoolHost:
    def __init__(self, github, *, root=Path('/'), owner_uid=0, identity=None,
                 host_factory=Host, pool_ready=None):
        self.github, self.root, self.owner_uid = github, Path(root), owner_uid
        self.identity = identity or pwd.getpwnam
        self.host_factory, self.readiness = host_factory, pool_ready
        self.configurations = {}

    def _path(self, logical):
        path = PurePosixPath(logical)
        require(path.is_absolute() and str(path) == logical and '..' not in path.parts,
                'SERIAL_TRANSITION_LEGACY_PATH_INVALID')
        return self.root / logical.lstrip('/')

    def _directory(self, logical, *, user=None, mutable=False):
        path = self._path(logical)
        info = path.lstat()
        require(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode),
                'SERIAL_TRANSITION_LEGACY_PARENT_UNSAFE')
        if mutable:
            require(info.st_uid == user.pw_uid and info.st_gid == user.pw_gid
                    and stat.S_IMODE(info.st_mode) == 0o750, 'SERIAL_TRANSITION_LEGACY_PARENT_UNSAFE')
        else:
            require(info.st_uid == self.owner_uid and not info.st_mode & 0o022,
                    'SERIAL_TRANSITION_LEGACY_PARENT_UNSAFE')

    def _parents(self, logical, mutable, user):
        root_info = self.root.lstat()
        require(stat.S_ISDIR(root_info.st_mode) and not stat.S_ISLNK(root_info.st_mode)
                and root_info.st_uid == self.owner_uid and not root_info.st_mode & 0o022,
                'SERIAL_TRANSITION_LEGACY_PARENT_UNSAFE')
        parts = PurePosixPath(logical).parts
        for number in range(2, len(parts)):
            parent = str(PurePosixPath(*parts[:number]))
            self._directory(parent, user=user, mutable=parent in mutable)

    def _read(self, logical, *, uid, gid=None, mode, mutable, user, content=True, limit=65536):
        self._parents(logical, mutable, user)
        path = self._path(logical)
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            before = os.fstat(descriptor)
            require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_uid == uid
                    and (gid is None or before.st_gid == gid) and stat.S_IMODE(before.st_mode) == mode
                    and before.st_size <= limit, 'SERIAL_TRANSITION_LEGACY_FILE_UNSAFE')
            raw = os.read(descriptor, limit + 1) if content else None
            require((raw is None or len(raw) <= limit) and _stamp(before) == _stamp(os.fstat(descriptor))
                    and _stamp(before) == _stamp(path.lstat()), 'SERIAL_TRANSITION_LEGACY_FILE_CHANGED')
            self._parents(logical, mutable, user)
            return raw
        finally:
            os.close(descriptor)

    def _local_worker(self, member, service):
        require(service.get('LoadState') == 'loaded'
                and service.get('FragmentPath') == member['unit'], 'SERIAL_TRANSITION_LEGACY_SERVICE_UNPROVEN')
        group = '/system.slice/' + member['service']
        require(service.get('ControlGroup', '') in ['', group], 'SERIAL_TRANSITION_LEGACY_SERVICE_UNPROVEN')
        if service.get('ActiveState') in ['inactive', 'failed']:
            require(service.get('MainPID') == '0' and service.get('ControlPID') == '0',
                    'SERIAL_TRANSITION_LEGACY_SERVICE_UNPROVEN')
        else:
            require(service.get('ActiveState') == 'active' and service.get('ControlGroup') == group
                    and re.fullmatch('[1-9][0-9]*', service.get('MainPID', ''))
                    and service.get('ControlPID') == '0', 'SERIAL_TRANSITION_LEGACY_SERVICE_UNPROVEN')
        cgroup = self._path('/sys/fs/cgroup' + group)
        if not cgroup.exists():
            require(service.get('ActiveState') in ['inactive', 'failed'], 'SERIAL_TRANSITION_LEGACY_SERVICE_UNPROVEN')
            return False
        processes = set()
        for directory in [cgroup, *[path for path in cgroup.rglob('*') if path.is_dir()]]:
            processes.update((directory / 'cgroup.procs').read_text().split())
        for process in processes:
            require(re.fullmatch('[1-9][0-9]*', process), 'SERIAL_TRANSITION_LEGACY_SERVICE_UNPROVEN')
            executable = self._path('/proc/' + process + '/exe').resolve().name
            arguments = self._path('/proc/' + process + '/cmdline').read_bytes().split(b'\0')
            script = Path(os.fsdecode(arguments[1])).name if len(arguments) > 1 else ''
            if executable not in ['Runner.Listener', 'run.sh', 'run-helper.sh'] and not (
                    executable in ['bash', 'sh'] and script in ['run.sh', 'run-helper.sh']):
                return True
        return False

    def inspect_legacy(self, original_config):
        general = original_config['environment']['generalRunner']
        namespace = original_config['environment']['namespace']
        require(re.fullmatch('[a-z][a-z0-9-]{0,30}', namespace)
                and 'generalRunnerPool' not in original_config['consumer']
                and 'executionSlots' not in original_config['consumer'], 'SERIAL_TRANSITION_ORIGINAL_NOT_SERIAL')
        values = compile_inputs(original_config)
        user = self.identity(general['user'])
        require(user.pw_uid > 0, 'SERIAL_TRANSITION_RUNNER_IDENTITY_CHANGED')
        member = {'runnerName': general['name'], 'runnerUser': general['user'], 'runnerUid': user.pw_uid,
                  'root': '/opt/' + namespace + '/general-runner',
                  'state': '/var/lib/' + namespace + '/general-runner',
                  'service': values.get('relay_general_runner_service_name', 'relay-general-runner.service'),
                  'scope': general.get('scope', 'repository'), 'repository': original_config['consumer']['repository']}
        member['organization'] = member['repository'].split('/')[0]
        member['unit'] = '/etc/systemd/system/' + member['service']
        member['workFolder'] = member['state'] + '/work'
        require(member['service'] in [namespace + '-general-runner.service', 'relay-general-runner.service']
                and member['scope'] in ['repository', 'organization'], 'SERIAL_TRANSITION_LEGACY_PATH_INVALID')
        mutable = {member['root']}
        self._parents(member['root'] + '/.runner', mutable, user)
        state_info = self._path(member['state']).lstat()
        state_mutable = {member['state']} if state_info.st_uid != self.owner_uid else set()
        self._parents(member['workFolder'] + '/.boundary', state_mutable | {member['workFolder']}, user)
        self._parents(member['state'] + '/home/.boundary', state_mutable | {member['state'] + '/home'}, user)
        raw = self._read(member['root'] + '/.runner', uid=user.pw_uid, gid=user.pw_gid,
                         mode=0o600, mutable=mutable, user=user)
        self._read(member['root'] + '/.credentials', uid=user.pw_uid, gid=user.pw_gid,
                   mode=0o600, mutable=mutable, user=user, content=False)
        registration = _object(raw)
        url = 'https://github.com/' + (member['repository'] if member['scope'] == 'repository' else member['organization'])
        require(type(registration.get('agentId')) is int and registration['agentId'] > 0
                and registration.get('agentName') == member['runnerName'] and registration.get('gitHubUrl') == url
                and registration.get('workFolder') == member['workFolder']
                and (member['scope'] != 'organization' or registration.get('poolName') == general.get('group')),
                'SERIAL_TRANSITION_REGISTRATION_INVALID')
        unit = self._read(member['unit'], uid=self.owner_uid, mode=0o644, mutable=set(), user=user)
        section = None
        properties = {}
        for row in unit.decode('utf-8').splitlines():
            row = row.strip()
            if not row or row.startswith(('#', ';')):
                continue
            if row.startswith('[') and row.endswith(']'):
                section = row[1:-1]
            elif section == 'Service' and '=' in row:
                key, value = row.split('=', 1)
                if key in ['User', 'Group', 'WorkingDirectory', 'ExecStart']:
                    require(key not in properties, 'SERIAL_TRANSITION_LEGACY_UNIT_UNPROVEN')
                    properties[key] = value
        require(properties == {'User': member['runnerUser'], 'Group': member['runnerUser'],
                               'WorkingDirectory': member['root'], 'ExecStart': member['root'] + '/run.sh'},
                'SERIAL_TRANSITION_LEGACY_UNIT_UNPROVEN')
        member.update(runnerId=registration['agentId'], registrationSha256=hashlib.sha256(raw).hexdigest(),
                      unitSha256=hashlib.sha256(unit).hexdigest())
        host = self.host_factory({'runnerUser': member['runnerUser']})
        loaded = host.command(['/usr/bin/systemctl', 'show', member['service'],
                               '-p', 'DropInPaths', '-p', 'NeedDaemonReload', '-p', 'User',
                               '-p', 'Group', '-p', 'WorkingDirectory'], returncodes=(0, 4), text=True)
        loaded = dict(row.split('=', 1) for row in loaded.splitlines() if '=' in row)
        require(loaded.get('DropInPaths') == '' and loaded.get('NeedDaemonReload') == 'no'
                and loaded.get('User') == member['runnerUser'] and loaded.get('Group') == member['runnerUser']
                and loaded.get('WorkingDirectory') == member['root'], 'SERIAL_TRANSITION_LEGACY_UNIT_UNPROVEN')
        member['ownWorker'] = self._local_worker(member, host.service(member))
        self.configurations[member['unitSha256']] = original_config
        return member

    def _bound(self, binding):
        config = self.configurations.get(binding.get('unitSha256'))
        require(config is not None, 'SERIAL_TRANSITION_LEGACY_BINDING_CHANGED')
        current = self.inspect_legacy(config)
        require({key: value for key, value in current.items() if key != 'ownWorker'} == binding,
                'SERIAL_TRANSITION_LEGACY_BINDING_CHANGED')
        return current, self.host_factory({'runnerUser': binding['runnerUser']})

    def stop_legacy(self, binding):
        current, host = self._bound(binding)
        require(current['ownWorker'] is False, 'SERIAL_TRANSITION_LEGACY_WORKER_PRESENT')
        def remote_idle():
            remote = self.github.observe_legacy(binding)
            return remote is not None and remote['busy'] is False
        require(remote_idle(), 'SERIAL_TRANSITION_LEGACY_BUSY')
        if host.service(binding).get('ActiveState') in ['inactive', 'failed']:
            # A registered SERIAL listener may already be inactive but enabled.
            # The core has durably reserved stop-intent; disable its proven
            # unit without sending any signal, then reobserve the stop proof.
            require(host.removal_stopped(binding), 'SERIAL_TRANSITION_STOP_UNCERTAIN_INSPECT_BEFORE_RETRY')
            if self._enablement(host, binding) != 'disabled':
                host.command(['/usr/bin/systemctl', 'disable', binding['service']])
        else:
            require(host.stop_idle(binding, remote_idle), 'SERIAL_TRANSITION_STOP_UNCERTAIN_INSPECT_BEFORE_RETRY')
        require(host.removal_stopped(binding) and self._enablement(host, binding) == 'disabled',
                'SERIAL_TRANSITION_STOP_UNCERTAIN_INSPECT_BEFORE_RETRY')

    def _enablement(self, host, binding):
        raw = host.command(['/usr/bin/systemctl', 'show', binding['service'], '-p', 'UnitFileState'],
                           returncodes=(0, 4), text=True)
        value = dict(row.split('=', 1) for row in raw.splitlines() if '=' in row).get('UnitFileState')
        require(value in ['enabled', 'enabled-runtime', 'disabled'], 'SERIAL_TRANSITION_LEGACY_SERVICE_UNPROVEN')
        return value

    def legacy_stopped(self, binding):
        current, host = self._bound(binding)
        return current['ownWorker'] is False and host.removal_stopped(binding) and self._enablement(host, binding) == 'disabled'

    def pool_ready(self, config):
        require(self.readiness is not None, 'SERIAL_TRANSITION_TARGET_READINESS_UNPROVEN')
        return self.readiness(config) is True
