#!/usr/bin/env python3
"""Owner Apply's bounded shared runner reconciliation, never a worker API.

Pool state contains bindings and mutation intents only. Credentials arrive on
protected stdin and runner configuration runs under the General Runner UID.
"""
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request

CAPACITY = 32
PERMISSION = 'organization_self_hosted_runners'
# Fixed product projection path; not an owner-supplied arbitrary workflow list.
LIFECYCLE_WORKFLOW = '.github/workflows/manual-main-production-deploy.yml'


class PoolError(RuntimeError):
    pass


def require(value, code):
    if not value:
        raise PoolError('MANAGED_POOL_' + code)


def pool_contract(config):
    from config import execution_slot_label, general_pool_label, deployment_repository, configured_repositories
    consumer, environment = config['consumer'], config['environment']
    general = environment['generalRunner']
    name = general['name']
    repository = deployment_repository(config)
    repositories = configured_repositories(config)
    workflows = {target: [target + '/' + consumer[key] + '@refs/heads/' + consumer['baseBranch']
                          for key in ['routingWorkflow', 'recoveryWorkflow']]
                 for target in repositories}
    # The opt-in installed owner lifecycle runs on General so it can restart
    # Production. Only its protected installation anchor owns this workflow.
    if environment['localApply'].get('source') == 'installed':
        require(LIFECYCLE_WORKFLOW not in [consumer[key] for key in
                ['routingWorkflow', 'recoveryWorkflow', 'validationWorkflow']],
                'ELIGIBILITY_WORKFLOWS_UNPROVEN')
        workflows[repository].append(repository + '/' + LIFECYCLE_WORKFLOW
                                     + '@refs/heads/' + consumer['baseBranch'])
    return {'version': 1, 'name': name, 'runnerUser': general['user'],
            'organization': repository.split('/')[0], 'group': general['group'],
            'appId': general['poolApp']['appId'], 'installationId': general['poolApp']['installationId'],
            'desiredCapacity': consumer['generalRunnerPool']['desiredCapacity'],
            'repository': repository, 'repositories': repositories, 'namespace': environment['namespace'],
            'admission': '/opt/' + environment['namespace'] + '/relay-admission',
            'readiness': '/opt/' + environment['namespace'] + '/relay-reviewer-readiness',
            'workflowRefs': workflows[repository],
            'workflowRefsByRepository': workflows,
            'label': general_pool_label(config),
            'members': [{'id': slot['id'], 'name': slot['runnerName'],
                         'label': execution_slot_label(config, slot),
                         'root': '/opt/codex-relay-pools/' + name + '/runners/' + slot['id'],
                         'state': '/var/lib/codex-relay-pools/' + name + '/runners/' + slot['id'],
                         'service': name + f'-pool-{number}.service'}
                        for number, slot in enumerate(consumer['executionSlots'], 1)]}


def binding(contract):
    return {key: contract[key] for key in ['version', 'name', 'runnerUser', 'organization',
                                          'group', 'appId', 'installationId', 'label', 'members']}


def protected(path, *, directory=False):
    info = Path(path).lstat()
    require((stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
            and info.st_uid == 0 and not info.st_mode & 0o022
            and (directory or info.st_nlink == 1), 'PROTECTED_PATH_UNSAFE')
    return info


def protected_parents(path):
    for parent in [Path(path), *Path(path).parents]:
        protected(parent, directory=True)


class State:
    def __init__(self, root):
        self.root = Path(root)
        protected_parents(self.root)
        self.path = self.root / 'pool.json'

    def read(self):
        try:
            protected(self.path)
        except FileNotFoundError:
            return None
        descriptor = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor) as stream:
            require(os.fstat(stream.fileno()).st_size <= 1024 * 1024, 'STATE_SIZE')
            return json.load(stream)

    def write(self, value):
        temporary = self.root / ('.pool-' + str(os.getpid()))
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(descriptor, 'w') as stream:
                json.dump(value, stream, sort_keys=True)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            temporary.unlink(missing_ok=True)


class GitHub:
    def __init__(self, token, organization):
        self.token, self.organization = token, organization

    def request(self, method, path, body=None):
        request = urllib.request.Request('https://api.github.com' + path,
            data=None if body is None else json.dumps(body).encode(), method=method,
            headers={'Authorization': 'Bearer ' + self.token, 'Accept': 'application/vnd.github+json',
                     'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'codex-relay-managed-pool',
                     'Content-Type': 'application/json'})
        try:
            # Neither response diagnostics nor authorization values reach logs.
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read(8 * 1024 * 1024 + 1)
                require(len(raw) <= 8 * 1024 * 1024, 'API_RESPONSE_SIZE')
                return json.loads(raw) if raw else None
        except (urllib.error.URLError, ValueError) as error:
            raise PoolError('MANAGED_POOL_API_UNPROVEN_INSPECT_BEFORE_RETRY') from None

    def pages(self, path, field):
        values = []
        page = 1
        while True:
            body = self.request('GET', path + ('&' if '?' in path else '?') + f'per_page=100&page={page}')
            rows = body.get(field)
            require(isinstance(rows, list), 'API_LIST_INVALID')
            values.extend(rows)
            if len(rows) < 100:
                require(len(values) == body.get('total_count'), 'API_LIST_INCOMPLETE')
                return values
            page += 1

    def runners(self):
        return self.pages('/orgs/' + self.organization + '/actions/runners', 'runners')

    def qualify(self, contract, eligible=None):
        if eligible is None:
            from pool_eligibility import eligible_workflows
            eligible = eligible_workflows(contract)
        groups = self.pages('/orgs/' + self.organization + '/actions/runner-groups', 'runner_groups')
        matches = [group for group in groups if group.get('name') == contract['group']]
        require(len(matches) == 1, 'GROUP_UNPROVEN')
        group = self.request('GET', '/orgs/' + self.organization + '/actions/runner-groups/' + str(matches[0]['id']))
        require(group.get('visibility') == 'selected' and group.get('restricted_to_workflows') is True,
                'GROUP_RESTRICTIONS_UNPROVEN')
        repositories = self.pages('/orgs/' + self.organization + '/actions/runner-groups/'
                                 + str(group['id']) + '/repositories', 'repositories')
        selected = [repository.get('full_name') for repository in repositories]
        require(bool(selected), 'GROUP_REPOSITORY_UNPROVEN')
        require(all(isinstance(repository, str) and repository in eligible for repository in selected),
                'GROUP_ELIGIBLE_REPOSITORIES_UNPROVEN')
        workflows = group.get('selected_workflows')
        require(isinstance(workflows, list) and workflows and all(isinstance(value, str) for value in workflows),
                'GROUP_WORKFLOWS_UNPROVEN')
        trusted = {ref for repository in selected for ref in eligible[repository]}
        active = set(workflows)
        require(active <= trusted, 'GROUP_UNTRUSTED_WORKFLOW_REF')
        for repository in selected:
            automatic = set(eligible[repository][:2])
            require(not automatic.intersection(active) or automatic <= active,
                    'GROUP_TRUSTED_WORKFLOW_REFS_UNPROVEN')
        return group['id']

    def in_group(self, group_id, runner_id):
        return runner_id in [runner['id'] for runner in self.pages('/orgs/' + self.organization
            + '/actions/runner-groups/' + str(group_id) + '/runners', 'runners')]

    def ephemeral(self, purpose):
        value = self.request('POST', '/orgs/' + self.organization + '/actions/runners/' + purpose + '-token')
        require(isinstance(value.get('token'), str) and bool(value['token']), 'EPHEMERAL_TOKEN_UNPROVEN')
        return value['token']

    def labels(self, runner_id, labels):
        return self.request('PUT', '/orgs/' + self.organization + '/actions/runners/'
                            + str(runner_id) + '/labels', {'labels': labels})


class Host:
    def __init__(self, contract):
        import pwd
        self.contract = contract
        self.user = pwd.getpwnam(contract['runnerUser'])
        require(self.user.pw_uid != 0, 'ROOT_RUNNER_PROHIBITED')

    def command(self, argv, *, returncodes=(0,), **kwargs):
        result = subprocess.run(argv, env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'},
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, **kwargs)
        require(result.returncode in returncodes, 'HOST_OPERATION_UNPROVEN_INSPECT_BEFORE_RETRY')
        return result.stdout

    def registration(self, member):
        root = Path(member['root'])
        paths = [root / '.runner', root / '.credentials']
        exists = [path.exists() or path.is_symlink() for path in paths]
        require(exists[0] == exists[1], 'LOCAL_REGISTRATION_AMBIGUOUS')
        if not exists[0]:
            rsa = root / '.credentials_rsaparams'
            require(not rsa.exists() and not rsa.is_symlink(), 'LOCAL_REGISTRATION_AMBIGUOUS')
            return None
        for path in paths:
            info = path.lstat()
            require(stat.S_ISREG(info.st_mode) and info.st_uid == self.user.pw_uid
                    and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1,
                    'LOCAL_REGISTRATION_AMBIGUOUS')
        descriptor = os.open(paths[0], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, encoding='utf-8-sig') as stream:
            require(os.fstat(stream.fileno()).st_size <= 65536, 'LOCAL_REGISTRATION_AMBIGUOUS')
            value = json.load(stream)
        require(value.get('agentName') == member['name']
                and value.get('gitHubUrl') == 'https://github.com/' + self.contract['organization']
                and value.get('poolName') == self.contract['group']
                and value.get('workFolder') == member['state'] + '/work'
                and type(value.get('agentId')) is int and value['agentId'] > 0,
                'LOCAL_REGISTRATION_AMBIGUOUS')
        return value['agentId']

    def registration_metadata_present(self, member):
        return any((Path(member['root']) / name).exists() or (Path(member['root']) / name).is_symlink()
                   for name in ['.runner', '.credentials', '.credentials_rsaparams'])

    def configure(self, member, token, remove=False):
        arguments = ['remove', '--unattended'] if remove else [
            '--unattended', '--url', 'https://github.com/' + self.contract['organization'],
            '--name', member['name'], '--runnergroup', self.contract['group'],
            '--labels', self.contract['label'] + ',' + member['label'],
            '--work', member['state'] + '/work', '--disableupdate']
        environment = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8',
                       'HOME': member['state'] + '/home', 'ACTIONS_RUNNER_INPUT_TOKEN': token}
        result = subprocess.run(['/usr/sbin/runuser', '--preserve-environment', '-u',
            self.contract['runnerUser'], '--', '/bin/sh', '-c', 'umask 077; exec "$@"',
            'relay-pool-config', member['root'] + '/config.sh', *arguments],
            cwd=member['root'], env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        require(result.returncode == 0, 'RUNNER_MUTATION_UNPROVEN_INSPECT_BEFORE_RETRY')

    def forget_registration(self, member):
        # Runner v2.336.0's remove --local performs no remote mutation. Use it
        # only after observing an already-reserved removal absent on GitHub.
        self.command(['/usr/sbin/runuser', '-u', self.contract['runnerUser'], '--',
                      member['root'] + '/config.sh', 'remove', '--local', '--unattended'],
                     cwd=member['root'])

    def service(self, member):
        raw = self.command(['/usr/bin/systemctl', 'show', member['service'],
                            '-p', 'LoadState', '-p', 'ActiveState', '-p', 'MainPID', '-p', 'ControlPID', '-p', 'ControlGroup', '-p', 'FragmentPath'],
                           returncodes=(0, 4), text=True)
        return dict(row.split('=', 1) for row in raw.splitlines() if '=' in row)

    def removal_stopped(self, member):
        state = self.service(member)
        if (state.get('ActiveState') not in ['inactive', 'failed']
                or state.get('MainPID') != '0' or state.get('ControlPID') != '0'):
            return False
        group = state.get('ControlGroup', '')
        expected = '/system.slice/' + member['service']
        require(group in ['', expected], 'SERVICE_CGROUP_UNPROVEN')
        root = Path('/sys/fs/cgroup' + expected)
        return not root.exists() or not any((directory / 'cgroup.procs').read_text().strip()
            for directory in [root, *[path for path in root.rglob('*') if path.is_dir()]])

    def ready(self, member):
        state = self.service(member)
        return state.get('ActiveState') == 'active' and re.fullmatch('[1-9][0-9]*', state.get('MainPID', '')) is not None

    def start(self, member):
        protected(self.contract['readiness'])
        self.command([self.contract['readiness']])
        self.command(['/usr/bin/systemctl', 'enable', '--now', member['service']])

    def attempts_idle(self, consumers):
        for consumer in consumers.values():
            protected(consumer['admission'])
            result = json.loads(self.command([consumer['admission'], 'status'], text=True))
            if result.get('active') != [] or result.get('unknown') != []:
                return False
        return True

    def stop_idle(self, member, remote_idle, *, now=time.monotonic, wait=time.sleep, timeout=5):
        """Freeze before inspecting local workers; no signal can hit an active job.

        Labels have already been removed. A final remote read detects a job
        assigned before that mutation. Unknown descendants preserve the member.
        """
        state = self.service(member)
        if state.get('ActiveState') in ['inactive', 'failed']:
            return self.removal_stopped(member)
        require(state.get('ActiveState') == 'active', 'SERVICE_STATE_AMBIGUOUS')
        self.command(['/usr/bin/systemctl', 'freeze', member['service']])
        stop_deadline = None

        def stopped():
            while True:
                if self.removal_stopped(member):
                    return True
                remaining = 0 if stop_deadline is None else stop_deadline - now()
                if remaining <= 0:
                    return False
                wait(min(0.1, remaining))

        try:
            group = state.get('ControlGroup', '')
            require(group == '/system.slice/' + member['service'], 'SERVICE_CGROUP_UNPROVEN')
            root = Path('/sys/fs/cgroup' + group)
            require('frozen 1' in (root / 'cgroup.events').read_text(), 'SERVICE_FREEZE_UNPROVEN')
            processes = set()
            for directory in [root, *[path for path in root.rglob('*') if path.is_dir()]]:
                processes.update((directory / 'cgroup.procs').read_text().split())
            allowed = {'Runner.Listener', 'run.sh', 'run-helper.sh'}
            for process in processes:
                cmdline = Path('/proc/' + process + '/cmdline').read_bytes().split(b'\0')
                executable = Path('/proc/' + process + '/exe').resolve().name
                script = Path(os.fsdecode(cmdline[1])).name if len(cmdline) > 1 else ''
                if executable not in allowed and not (executable in ['bash', 'sh'] and script in allowed):
                    return False
            if not remote_idle():
                return False
            # Queue SIGTERM to the proven idle cgroup while frozen. This closes
            # the read/signal race without force-killing any worker process.
            self.command(['/usr/bin/systemctl', 'kill', '--kill-whom=all', '--signal=SIGTERM', member['service']])
            self.command(['/usr/bin/systemctl', 'disable', member['service']])
            self.command(['/usr/bin/systemctl', 'stop', '--no-block', member['service']])
            stop_deadline = now() + timeout
        finally:
            try:
                self.command(['/usr/bin/systemctl', 'thaw', member['service']])
            except PoolError:
                # Stop may reject thaw while still deactivating, or remove
                # the cgroup before thaw. Await only its read-only completion
                # proof within the same budget; never repeat a stop/signal.
                if not stopped():
                    raise
        return stopped()

    def retire(self, member):
        # Registration package is disposable; journals/attempt work live in
        # separate repository namespaces and are deliberately retained.
        import shutil
        service = Path('/etc/systemd/system') / member['service']
        if service.exists() or service.is_symlink():
            protected(service)
            service.unlink()
        for root in [Path(member['root']), Path(member['state'])]:
            require(root.name == member['id'] and root.parent.name == 'runners'
                    and root.parent.parent.name == self.contract['name'], 'RETIRE_PATH_UNPROVEN')
            protected_parents(root.parent)
            if root.exists() or root.is_symlink():
                require(root.is_dir() and not root.is_symlink(), 'RETIRE_PATH_UNPROVEN')
                shutil.rmtree(root)
        self.command(['/usr/bin/systemctl', 'daemon-reload'])


def wait_ready(member, runner_id, observe, host, *, now=time.monotonic, wait=time.sleep, timeout=30):
    deadline = now() + timeout
    while True:
        remote = observe(member)
        require(remote is not None and remote.get('id') == runner_id
                and host.registration(member) == runner_id, 'STARTUP_REGISTRATION_BINDING_UNPROVEN')
        if host.ready(member) and remote.get('status') == 'online':
            return
        require(now() < deadline, 'STARTUP_READINESS_UNPROVEN_INSPECT_BEFORE_RETRY')
        wait(min(0.5, max(0, deadline - now())))


def reconcile(contract, state_store, github, host):
    """Idempotent bounded pass. Busy members remain drained for a later Apply."""
    require(type(contract['desiredCapacity']) is int and 1 <= contract['desiredCapacity'] <= CAPACITY,
            'CAPACITY_INVALID')
    state = state_store.read()
    if state is None:
        state = {'version': 1, 'binding': binding(contract), 'ownerRepository': contract['repository'],
                 'desiredCapacity': contract['desiredCapacity'], 'consumers': {}, 'members': {}}
    require(state.get('binding') == binding(contract), 'BINDING_CONFLICT')
    require(state['ownerRepository'] == contract['repository']
            or state['desiredCapacity'] == contract['desiredCapacity'], 'DESIRED_CAPACITY_CONFLICT')
    group_id = github.qualify(contract)
    consumer_binding = {'namespace': contract['namespace'], 'admission': contract['admission']}
    for repository in contract.get('repositories', [contract['repository']]):
        require(state['consumers'].get(repository, consumer_binding) == consumer_binding,
                'CONSUMER_NAMESPACE_CONFLICT')
        state['consumers'][repository] = consumer_binding
    state['desiredCapacity'] = contract['desiredCapacity']
    state_store.write(state)

    def observe(member):
        matches = [runner for runner in github.runners() if runner.get('name') == member['name']]
        require(len(matches) <= 1, 'REMOTE_REGISTRATION_AMBIGUOUS')
        return matches[0] if matches else None

    report = {'capacity': contract['desiredCapacity'], 'ready': [], 'draining': [], 'retired': []}
    for number, member in enumerate(contract['members'], 1):
        record = state['members'].get(member['id'])
        if number > contract['desiredCapacity'] and record is None:
            # Foreign matching registrations are never adopted or removed.
            require(observe(member) is None, 'UNOWNED_REGISTRATION')
            continue
        if record is not None and record['phase'] == 'remove':
            # A successful remote removal can crash between sequential local
            # marker deletions. Never parse partial registration bytes here.
            def remote_absent():
                return not any(runner.get('name') == member['name'] or runner.get('id') == record['runnerId']
                               for runner in github.runners())
            require(remote_absent(), 'REMOVAL_UNCERTAIN_INSPECT_BEFORE_RETRY')
            require(host.attempts_idle(state['consumers']) and host.removal_stopped(member),
                    'REMOVAL_LOCAL_CLEANUP_UNPROVEN')
            if host.registration_metadata_present(member):
                host.forget_registration(member)
            require(not host.registration_metadata_present(member), 'REMOVAL_LOCAL_CLEANUP_UNPROVEN')
            host.retire(member)
            del state['members'][member['id']]
            state_store.write(state)
            report['retired'].append(member['id'])
            continue
        local = host.registration(member)
        remote = observe(member)
        if record is None:
            require(local is None and remote is None, 'UNOWNED_REGISTRATION')
            token = github.ephemeral('registration')
            record = {'phase': 'register', 'runnerId': None}
            state['members'][member['id']] = record
            state_store.write(state)  # reservation before config.sh
            host.configure(member, token)
            token = None
            local, remote = host.registration(member), observe(member)
        if record['phase'] == 'register':
            require(local is not None and remote is not None and remote.get('id') == local,
                    'REGISTRATION_UNCERTAIN_INSPECT_BEFORE_RETRY')
            record.update({'phase': 'registered', 'runnerId': local})
            state_store.write(state)
        require(local == record['runnerId'] and remote is not None and remote.get('id') == local
                and github.in_group(group_id, local), 'REGISTRATION_BINDING_UNPROVEN')
        if number <= contract['desiredCapacity']:
            labels = [contract['label'], member['label']]
            if {value.get('name') for value in remote.get('labels', []) if value.get('type') == 'custom'} != set(labels):
                github.labels(local, labels)
            remote = observe(member)
            require(remote is not None and {contract['label'], member['label']} <=
                    {label.get('name') for label in remote.get('labels', [])}, 'LABEL_MUTATION_UNPROVEN')
            if record['phase'] in ['registered', 'draining']:
                record['phase'] = 'starting'
                state_store.write(state)
                host.start(member)
            wait_ready(member, local, observe, host)
            record['phase'] = 'ready'
            state_store.write(state)
            report['ready'].append(member['id'])
            continue
        record['phase'] = 'draining'
        state_store.write(state)
        # Idempotent PUT is always followed by observation before any stop.
        if any(label.get('type') == 'custom' for label in remote.get('labels', [])):
            github.labels(local, [])
        remote = observe(member)
        require(remote is not None and not any(label.get('type') == 'custom' for label in remote.get('labels', [])),
                'DRAIN_LABELS_UNPROVEN')
        def remote_idle():
            current = observe(member)
            return current is not None and current.get('busy') is False
        if remote.get('busy') is not False or not host.attempts_idle(state['consumers']) or not host.stop_idle(member, remote_idle):
            report['draining'].append(member['id'])
            continue
        token = github.ephemeral('remove')
        record['phase'] = 'remove'
        state_store.write(state)  # unknown result may not invoke remove again
        host.configure(member, token, remove=True)
        token = None
        require(host.registration(member) is None and observe(member) is None, 'REMOVAL_UNCERTAIN_INSPECT_BEFORE_RETRY')
        host.retire(member)
        del state['members'][member['id']]
        state_store.write(state)
        report['retired'].append(member['id'])
    return report


def installed_main(revision):
    require(os.geteuid() == 0 and re.fullmatch('[0-9a-f]{40}', revision), 'ROOT_EXACT_REVISION_REQUIRED')
    from installed_config import verify
    source = Path(__file__).resolve().parents[1]
    config, config_digest, _ = verify(source, revision, require_local_apply=False)
    contract = pool_contract(config)
    payload = json.loads(sys.stdin.read(16385))
    require(set(payload) in [{'installationToken', 'appId', 'installationId', 'organization'},
                            {'installationToken', 'appId', 'installationId', 'organization', 'deploymentConfigSha256'}]
            and all(payload[key] == contract[key] for key in ['appId', 'installationId', 'organization'])
            and isinstance(payload['installationToken'], str) and 0 < len(payload['installationToken']) <= 4096,
            'TOKEN_BINDING_INVALID')
    require('deploymentConfigSha256' not in payload or payload['deploymentConfigSha256'] == config_digest,
            'TARGET_CONFIG_BINDING_UNPROVEN')
    github = GitHub(payload['installationToken'], contract['organization'])
    github.qualify(contract)
    from serial_pool_installation import preflight, current_consumer_digest
    transition = preflight(config, github, current_consumer_digest(config, source))
    if transition is not None and transition.get('phase') != 'retired':
        require(transition.get('phase') in ['stopped', 'target-ready', 'remove-intent'],
                'SERIAL_TRANSITION_STOP_UNPROVEN')
    root = Path('/var/lib/codex-relay-pools') / contract['name']
    protected_parents(root)
    descriptor = os.open(root / 'pool.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(descriptor)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1
                and stat.S_IMODE(info.st_mode) == 0o600, 'LOCK_UNSAFE')
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        report = reconcile(contract, State(root), github, Host(contract))
        print('MANAGED_POOL_RESULT=' + json.dumps(report, sort_keys=True))
    finally:
        os.close(descriptor)


def installation_plan(contract, unit_template, *, root=Path('/'), owner_uid=0,
                      runner_uid=None, service_probe=None):
    """Read existing ownership/bindings before any installer mutation.

    Missing directories are creation proposals. Existing objects are never an
    invitation to repair their ownership, replace a foreign unit or extract
    over an active/unknown package.
    """
    import pwd
    from types import SimpleNamespace
    if runner_uid is None:
        try:
            runner_uid = pwd.getpwnam(contract['runnerUser']).pw_uid
        except KeyError:
            pass  # a fresh check-mode plan may precede account creation
    require(runner_uid != 0, 'ROOT_RUNNER_PROHIBITED')
    plan = {'status': 'PASS', 'createParents': [], 'members': {}}

    def physical(logical):
        return root / logical.lstrip('/')

    def metadata(logical):
        try:
            return physical(logical).lstat()
        except FileNotFoundError:
            return None

    def directory(logical, uid, missing, *, private=False):
        info = metadata(logical)
        if info is None:
            missing.append(logical)
        else:
            require(stat.S_ISDIR(info.st_mode) and info.st_uid == uid
                    and not info.st_mode & (0o027 if private else 0o022), 'INSTALL_EXISTING_DIRECTORY_UNSAFE')
        return info

    parents = ['/opt/codex-relay-pools', '/var/lib/codex-relay-pools',
               '/opt/codex-relay-pools/' + contract['name'],
               '/var/lib/codex-relay-pools/' + contract['name'],
               '/opt/codex-relay-pools/' + contract['name'] + '/runners',
               '/var/lib/codex-relay-pools/' + contract['name'] + '/runners']
    ancestors = set()
    for logical in parents + ['/etc/systemd/system']:
        for parent in reversed(Path(logical).parents):
            if str(parent) not in ancestors:
                directory(str(parent), owner_uid, [])
                ancestors.add(str(parent))
        directory(logical, owner_uid, plan['createParents'] if logical in parents else [])
    state_path = '/var/lib/codex-relay-pools/' + contract['name'] + '/pool.json'
    state_info = metadata(state_path)
    state = None
    if state_info is not None:
        require(stat.S_ISREG(state_info.st_mode) and state_info.st_uid == owner_uid
                and stat.S_IMODE(state_info.st_mode) == 0o600 and state_info.st_nlink == 1
                and state_info.st_size <= 1024 * 1024, 'INSTALL_STATE_UNSAFE')
        state = json.loads(physical(state_path).read_text())
    if state is not None:
        require(state.get('binding') == binding(contract), 'BINDING_CONFLICT')
        require(state['ownerRepository'] == contract['repository']
                or state['desiredCapacity'] == contract['desiredCapacity'], 'DESIRED_CAPACITY_CONFLICT')
    inspector = object.__new__(Host)
    inspector.contract = contract
    inspector.user = SimpleNamespace(pw_uid=runner_uid)
    service_probe = service_probe or inspector.service
    inspected_members = [member for number, member in enumerate(contract['members'], 1)
                         if number <= contract['desiredCapacity'] or member['id'] in (state or {}).get('members', {})]
    for member in inspected_members:
        record = (state or {}).get('members', {}).get(member['id'])
        member_plan = {'createDirectories': [], 'installPackage': False, 'installUnit': False,
                       'retiring': record is not None and record['phase'] == 'remove'}
        plan['members'][member['id']] = member_plan
        for logical in [member['root'], member['state'], member['state'] + '/home', member['state'] + '/work']:
            directory(logical, runner_uid, member_plan['createDirectories'], private=True)
        mapped = {**member, 'root': str(physical(member['root']))}
        present = inspector.registration_metadata_present(mapped)
        if record is None:
            require(not present, 'INSTALL_UNOWNED_REGISTRATION')
        elif record['phase'] != 'remove':
            local = inspector.registration(mapped)
            require((record['phase'] == 'register' and (local is None or record['runnerId'] in [None, local]))
                    or local is not None and local == record['runnerId'], 'INSTALL_REGISTRATION_BINDING_UNPROVEN')
        unit_path = '/etc/systemd/system/' + member['service']
        unit_info = metadata(unit_path)
        expected = unit_template
        for field, value in {**{'relay_general_runner_pool.name': contract['name'],
                               'relay_general_runner_pool.runnerUser': contract['runnerUser']},
                             **{'relay_pool_member.' + key: member[key] for key in ['id', 'root', 'state']}}.items():
            expected = expected.replace('{{ ' + field + ' }}', value)
        require('{{' not in expected and '{%' not in expected, 'INSTALL_UNIT_TEMPLATE_UNPROVEN')
        if unit_info is not None:
            require(stat.S_ISREG(unit_info.st_mode) and unit_info.st_uid == owner_uid
                    and not unit_info.st_mode & 0o022 and unit_info.st_nlink == 1
                    and unit_info.st_size <= 65536, 'INSTALL_UNIT_UNSAFE')
            installed_unit = physical(unit_path).read_text()
            if installed_unit != expected:
                # Protected membership proves an existing managed unit. Keep
                # its stable process identity while permitting an accepted
                # template upgrade; an unbound prepared unit needs exact bytes.
                identity = {'Description': 'Relay managed shared General Runner ' + contract['name'] + '/' + member['id'],
                            'User': contract['runnerUser'], 'Group': contract['runnerUser'],
                            'WorkingDirectory': member['root'], 'ExecStart': member['root'] + '/run.sh'}
                require(record is not None and all(re.findall('(?m)^' + re.escape(key) + '=(.*)$', installed_unit) == [value]
                                                  for key, value in identity.items()), 'INSTALL_UNKNOWN_SERVICE')
        service = service_probe(member)
        require(service.get('LoadState') in ['loaded', 'not-found']
                and service.get('ActiveState') in ['active', 'inactive', 'failed'], 'INSTALL_SERVICE_STATE_UNPROVEN')
        if record is None:
            require(service['ActiveState'] != 'active' and service.get('MainPID') == '0'
                    and service.get('ControlPID') == '0', 'INSTALL_UNOWNED_SERVICE')
        if service['LoadState'] == 'loaded':
            require((unit_info is not None or member_plan['retiring'])
                    and service.get('FragmentPath') == unit_path, 'INSTALL_UNKNOWN_SERVICE')
        complete = True
        for logical in [member['root'] + '/config.sh', member['root'] + '/run.sh', member['root'] + '/bin/Runner.Listener']:
            info = metadata(logical)
            if info is None:
                complete = False
            else:
                require(stat.S_ISREG(info.st_mode) and info.st_uid == runner_uid
                        and info.st_mode & 0o111, 'INSTALL_PACKAGE_UNSAFE')
        if metadata(member['root'] + '/bin') is not None:
            directory(member['root'] + '/bin', runner_uid, [])
        if record is not None and record['phase'] == 'remove':
            # Preserve the exact retirement frontier; reconciliation owns local
            # marker cleanup, including a package/unit already partly removed.
            member_plan['createDirectories'] = []
            continue
        require(complete or service['ActiveState'] != 'active', 'INSTALL_ACTIVE_PACKAGE_UNPROVEN')
        member_plan['installPackage'] = not complete
        member_plan['installUnit'] = unit_info is None or installed_unit != expected
    return plan


def preflight(payload):
    require(os.geteuid() == 0 and isinstance(payload, dict)
            and set(payload) == {'contract', 'unitTemplate'}, 'ROOT_PREFLIGHT_INPUT_REQUIRED')
    print(json.dumps(installation_plan(payload['contract'], payload['unitTemplate']), sort_keys=True))


if __name__ == '__main__':
    try:
        if sys.argv[1:] == ['--preflight']:
            preflight(json.loads(sys.stdin.read(1048577)))
        else:
            require(len(sys.argv) == 3 and sys.argv[1] == '--installed-revision', 'ARGUMENTS')
            installed_main(sys.argv[2])
    except PoolError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
    except (OSError, ValueError, KeyError, TypeError):
        print('MANAGED_POOL_FAILED;inspect-before-retry', file=sys.stderr)
        raise SystemExit(1)
