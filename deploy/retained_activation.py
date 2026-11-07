"""Prove owner-declared Runners and restore only eligible stopped Production.

The existing bounded continuation receipt owns the declaration. It never
changes the first service snapshot or supplies execution authority. An explicit
recover may start its exact declared Production through the normal start gate;
every live observation is repeated before final lifecycle validation.
"""
import hashlib
import fcntl
from contextlib import contextmanager
import copy
import json
import os
from pathlib import Path
import re
import subprocess
import stat
import sys
import time

import bounded_recovery as retained
from config import compile_inputs
import managed_pool
import runner_self_update


def require(condition, code):
    if not condition:
        raise ValueError('RELAY_RETAINED_ACTIVATION_' + code)


def command(argv, *, cwd=None, pass_fds=()):
    result = subprocess.run(argv, capture_output=True, timeout=60, cwd=cwd, pass_fds=pass_fds,
                            env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C',
                                 'PYTHONDONTWRITEBYTECODE': '1'})
    require(result.returncode == 0 and len(result.stdout) <= 1024 * 1024, 'OBSERVATION_UNAVAILABLE')
    return result.stdout


def services(config):
    values = compile_inputs(config)
    namespace = config['environment']['namespace']
    runner = config['environment']['runner']
    result = {'production': {'root': '/opt/' + namespace + '/runner',
        'user': runner['user'], 'service': values.get('relay_production_runner_service_name', 'relay-runner.service'),
        'name': runner['name'], 'group': runner['group'], 'work': '/var/lib/' + namespace + '/runner/work'}}
    # This continuation only covers the existing protected managed pool.
    contract = managed_pool.pool_contract(config)
    for index, member in enumerate(contract['members'][:contract['desiredCapacity']]):
        result['general' if index == 0 else 'slot-' + member['id']] = {
            **member, 'user': contract['runnerUser'], 'group': contract['group'], 'work': member['state'] + '/work'}
    return result, contract


class Native:
    def __init__(self, payload):
        self.payload = payload
        self.config, self.binding = payload['config'], payload['binding']
        self.paths = retained.paths(self.config, self.binding, Path('/'))

    def authority(self):
        require(os.geteuid() == 0, 'ROOT_REQUIRED')
        retained.backend_validate(self.paths['record'], self.binding['desiredRevision'],
                                  self.binding['operationId'], require_applying=True)
        receipt = retained.load_receipt(self.paths['receipt'], Path('/'), 0)
        require(receipt['binding'] == self.binding and receipt['desiredConfigSha256'] == retained.sha(
            json.dumps(self.config, sort_keys=True).encode()), 'DECLARATION_BINDING_CHANGED')
        original = retained.decode(__import__('base64').b64decode(receipt['original']['gateBytes']))
        previous = {'manualOutcome': {'active': False, 'enabled': 'disabled', 'load': 'not-found'},
                    **original['previousActive']}
        require(previous == self.payload['previous'], 'ORIGINAL_INTENT_CHANGED')
        # The caller holds the existing prepared Writer lease; the fixed prefix
        # uses that lease rather than acquiring a competing Writer lock.
        status = json.loads(command([*self.payload['admission'], 'status', '--operation', self.binding['operationId']]))
        require(status.get('operationId') == self.binding['operationId']
                and status.get('target') == self.binding['desiredRevision']
                and status.get('phase') == 'applying' and status.get('active') == []
                and status.get('unknown') == [] and status.get('previousActive') == original['previousActive'],
                'WORK_OR_OPERATION_UNPROVEN')

    @contextmanager
    def operation_lock(self):
        lock = Path('/run') / self.config['environment']['namespace'] / 'production-operation.lock'
        retained.protect(lock, Path('/'), 0)
        descriptor = os.open(lock, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield descriptor
        finally:
            os.close(descriptor)

    def configuration_transition(self):
        """Bind supplied render bytes to the frozen protected release artifacts.

        The caller renders the authentic desired product template. The old
        artifact identity is an allowed source transition, never an assertion
        about configuration loaded by a historical process.
        """
        release = self.paths['install'] / 'releases' / self.binding['desiredRevision']
        require(Path(self.payload['release']) == release, 'CONFIG_ADOPTION_RELEASE_CHANGED')
        original = self.paths['install'] / 'releases' / self.binding['installedRevision']
        manifests = [retained.decode(retained.read(path / 'artifact-manifest.json', Path('/'), 0))
                     for path in [original, release]]
        for manifest, revision in zip(manifests, [self.binding['installedRevision'], self.binding['desiredRevision']]):
            require(manifest.get('commit') == revision
                    and retained.DIGEST.fullmatch(manifest.get('releaseSourceTreeSha256', ''))
                    and retained.DIGEST.fullmatch(manifest.get('reviewerBinarySha256', '')),
                    'CONFIG_ADOPTION_ARTIFACT_UNPROVEN')
        require(manifests[0]['reviewerBinarySha256'] == manifests[1]['reviewerBinarySha256'],
                'CONFIG_ADOPTION_EXECUTABLE_CHANGED')
        expected = configuration_transition(self.payload.get('reviewerConfigTransition'), *manifests)
        current = retained.read(Path('/etc') / self.config['environment']['namespace'] / 'reviewer-mcp.json',
                                Path('/'), 0)
        require(current == expected['desired'], 'CONFIG_ADOPTION_DESIRED_CONFIG_CHANGED')
        return expected

    def restart_configuration(self, descriptor):
        installed = self.paths['install'] / 'relay-reviewer-operation-restart'
        helper = Path(self.payload.get('restart', str(installed)))
        staged = (helper.name == 'reviewer-config-adoption-restart'
                  and helper.parent.parent == self.paths['install'] / 'releases'
                  and helper.parent.name.startswith('.stage-')
                  and retained.UUID.fullmatch(helper.parent.name.removeprefix('.stage-')) is not None)
        require(helper == installed or staged, 'CONFIG_ADOPTION_RESTART_PATH_UNPROVEN')
        retained.read(helper, Path('/'), 0)
        require(stat.S_IMODE(helper.stat().st_mode) == (0o700 if staged else 0o750),
                'CONFIG_ADOPTION_RESTART_PATH_UNPROVEN')
        command([str(helper), '--maintained-config-adoption', self.binding['operationId'], str(descriptor)],
                pass_fds=(descriptor,))

    def wait_production(self, expected):
        """Observe the exact restarted registration; never repeat activation."""
        deadline = time.monotonic() + 30
        while True:
            remote = [runner for runner in self.github.runners() if runner.get('id') == expected['runnerId']
                      or runner.get('name') == expected['runnerName']]
            require(len(remote) == 1 and remote[0].get('id') == expected['runnerId']
                    and remote[0].get('name') == expected['runnerName']
                    and remote[0].get('status') in ['offline', 'online']
                    and remote[0].get('busy') is False, 'CONFIG_ADOPTION_PRODUCTION_REGISTRATION_UNPROVEN')
            if remote[0]['status'] == 'online':
                return
            require(time.monotonic() < deadline, 'CONFIG_ADOPTION_PRODUCTION_NOT_ONLINE')
            time.sleep(1)

    def transport_dependencies(self):
        """Keep known General transports outside this restart's stop edges.

        A retained Apply may have published its release before replacing a
        legacy General PartOf unit. Inspect the loaded graph, including
        drop-ins, rather than inferring completion from installed source.
        """
        identities, _ = services(self.config)
        general = {identity['service'] for component, identity in identities.items() if component != 'production'}
        reviewer = compile_inputs(self.config).get('relay_reviewer_service_name', 'reviewer-mcp.service')
        controls = {reviewer, identities['production']['service']}
        fields = {'LoadState', 'NeedDaemonReload', 'PartOf', 'Requires', 'BindsTo', 'PropagatesStopTo'}
        for unit in sorted(general | controls):
            rows = command(['/bin/systemctl', 'show', unit, '--property=' + ','.join(sorted(fields))]).decode().splitlines()
            pairs = [row.split('=', 1) for row in rows if '=' in row]
            require(len(pairs) == len(rows) and len({key for key, _ in pairs}) == len(pairs),
                    'CONFIG_ADOPTION_GENERAL_DEPENDENCY_UNPROVEN')
            observed = dict(pairs)
            require(observed.keys() == fields and observed['LoadState'] == 'loaded'
                    and observed['NeedDaemonReload'] == 'no', 'CONFIG_ADOPTION_GENERAL_DEPENDENCY_UNPROVEN')
            if unit in general:
                require(not any(set(observed[field].split()) & controls for field in ['PartOf', 'Requires', 'BindsTo']),
                        'CONFIG_ADOPTION_GENERAL_DEPENDENCY_UNSAFE')
            if unit in controls:
                stop_targets = set(observed['PropagatesStopTo'].split())
                require(not stop_targets & general,
                        'CONFIG_ADOPTION_GENERAL_DEPENDENCY_UNSAFE')
                require(stop_targets <= controls, 'CONFIG_ADOPTION_FOREIGN_STOP_UNSAFE')

    def runners(self, contract):
        from pool_authorization import installation_authorization
        authorization = installation_authorization(self.config)
        self.github = managed_pool.GitHub(authorization['installationToken'], contract['organization'])
        self.pool_group = self.github.qualify(contract)
        return self.github.runners()

    def runner(self, component, expected, identity, contract, *, stopped=False):
        value = runner_self_update.inspect(identity['root'], identity['service'], identity['user'],
                                           expected['runnerId'], expected['runnerName'])
        state = value['serviceState']
        if stopped:
            require(component == 'production' and state['ActiveState'] == 'inactive'
                    and state['SubState'] == 'dead' and state['MainPID'] == '0', 'STOPPED_RUNNER_UNPROVEN')
            runner_self_update.assert_stopped(identity['service'], identity['root'], identity['user'])
        else:
            require(state['ActiveState'] == 'active' and state['SubState'] == 'running'
                    and re.fullmatch('[1-9][0-9]*', state['MainPID']) is not None, 'RUNNER_NOT_HEALTHY')
        settings = value['settings']
        require(all(item['disableUpdate'] is False and item['agentName'] == identity['name']
                    and item['poolName'] == identity['group']
                    and item['workFolder'] == identity['work']
                    and item['gitHubUrl'] == 'https://github.com/' + contract['organization']
                    for item in settings), 'REGISTRATION_OR_UPDATE_SETTING_CHANGED')
        group_id = settings[0]['poolId']
        require(type(group_id) is int and group_id > 0 and self.github.in_group(group_id, expected['runnerId']),
                'GROUP_MEMBERSHIP_UNPROVEN')
        if component != 'production':
            pool = managed_pool.State('/var/lib/codex-relay-pools/' + contract['name']).read()
            require(pool is not None and pool['binding'] == managed_pool.binding(contract), 'POOL_BINDING_CHANGED')
            member = pool['members'].get(identity['id'])
            require(member == {'phase': 'ready', 'runnerId': expected['runnerId']}
                    and group_id == self.pool_group, 'ORIGINAL_RUNNER_ID_CHANGED')
        else:
            group = self.github.request('GET', '/orgs/' + contract['organization']
                                        + '/actions/runner-groups/' + str(group_id))
            require(group.get('name') == identity['group'] and group.get('visibility') == 'selected'
                    and group.get('restricted_to_workflows') is True, 'PRODUCTION_GROUP_UNPROVEN')
        unit = Path('/etc/systemd/system') / identity['service']
        retained.read(unit, Path('/'), 0)
        uid = runner_self_update.runner_uid(identity['user'])
        if not stopped:
            process_uid = Path('/proc/' + state['MainPID']).stat().st_uid
            require(process_uid == uid and state['ControlGroup'] == '/system.slice/' + identity['service'],
                    'LIVE_UNIX_IDENTITY_UNPROVEN')
        version = command(['/usr/sbin/runuser', '-u', identity['user'], '--',
                           identity['root'] + '/bin/Runner.Listener', '--version'], cwd=identity['root']).decode().strip()
        # GitHub online/idle is the current eligibility authority; a numerical
        # version or a successful local --version probe alone is insufficient.
        require(re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', version), 'VERSION_UNPROVEN')
        proof = {'service': identity['service'], 'runnerId': expected['runnerId'], 'version': version}
        if not stopped:
            proof.update(pid=state['MainPID'], startTicks=Path('/proc/' + state['MainPID'] + '/stat').read_text(
                ).rsplit(') ', 1)[1].split()[19])
        return proof

    def restore(self, expected, identity, contract):
        """Owner-selected recover may restore only its exact declared Production.

        This is current-state activation under the ordinary operation lock and
        start gate, never a claim that the old process survived or why it stopped.
        """
        lock = Path('/run') / self.config['environment']['namespace'] / 'production-operation.lock'
        retained.protect(lock, Path('/'), 0)
        descriptor = os.open(lock, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.authority()
            reviewer = self.reviewer()
            primary = self.primary(contract)
            self.runner('production', expected, identity, contract, stopped=True)
            remote = [r for r in self.github.runners() if r.get('id') == expected['runnerId']
                      or r.get('name') == expected['runnerName']]
            require(len(remote) == 1 and remote[0].get('id') == expected['runnerId']
                    and remote[0].get('name') == expected['runnerName']
                    and remote[0].get('status') in ['offline', 'online']
                    and remote[0].get('busy') is False, 'RESTORE_REGISTRATION_UNPROVEN')
            self.authority()
            require(self.reviewer() == reviewer and self.primary(contract) == primary, 'CONTROL_RUNTIME_CHANGED')
            command(['/bin/systemctl', 'start', identity['service']])
            deadline = time.monotonic() + 30
            while True:
                remote = [r for r in self.github.runners() if r.get('id') == expected['runnerId']
                          or r.get('name') == expected['runnerName']]
                require(len(remote) == 1 and remote[0].get('id') == expected['runnerId']
                        and remote[0].get('name') == expected['runnerName']
                        and remote[0].get('busy') is False, 'RESTORED_REGISTRATION_UNPROVEN')
                if remote[0].get('status') == 'online':
                    break
                require(time.monotonic() < deadline, 'RESTORED_REGISTRATION_NOT_ONLINE')
                time.sleep(1)
            self.runner('production', expected, identity, contract)
            require(self.reviewer() == reviewer and self.primary(contract) == primary, 'CONTROL_RUNTIME_CHANGED')
            self.authority()
        finally:
            os.close(descriptor)

    def primary(self, contract):
        identities, _ = services(self.config)
        identity = identities['general']
        pool = managed_pool.State('/var/lib/codex-relay-pools/' + contract['name']).read()
        require(pool is not None and pool['binding'] == managed_pool.binding(contract), 'POOL_BINDING_CHANGED')
        member = pool['members'].get(identity['id'])
        require(isinstance(member, dict) and member.get('phase') == 'ready'
                and type(member.get('runnerId')) is int and member['runnerId'] > 0, 'PRIMARY_IDENTITY_UNPROVEN')
        expected = {'runnerId': member['runnerId'], 'runnerName': identity['name']}
        matches = [r for r in self.github.runners() if r.get('id') == expected['runnerId']
                   or r.get('name') == expected['runnerName']]
        require(len(matches) == 1 and matches[0].get('id') == expected['runnerId']
                and matches[0].get('name') == expected['runnerName']
                and matches[0].get('status') == 'online' and type(matches[0].get('busy')) is bool,
                'PRIMARY_REGISTRATION_UNPROVEN')
        return self.runner('general', expected, identity, contract)

    def reviewer(self):
        namespace = self.config['environment']['namespace']
        values = compile_inputs(self.config)
        unit = values.get('relay_reviewer_service_name', 'reviewer-mcp.service')
        state = dict(line.split('=', 1) for line in command(['/bin/systemctl', 'show', unit,
            '--property=LoadState,ActiveState,SubState,MainPID,ExecMainStartTimestampMonotonic,User,NeedDaemonReload']).decode().splitlines())
        require(state.get('LoadState') == 'loaded' and state.get('ActiveState') == 'active'
                and state.get('SubState') == 'running' and state.get('NeedDaemonReload') == 'no'
                and state.get('User') == self.config['environment']['reviewerUser']
                and re.fullmatch('[1-9][0-9]*', state.get('MainPID', '')), 'REVIEWER_UNPROVEN')
        config_root = Path('/etc') / namespace
        # These are the same protected activation prerequisites as the Runner
        # start gate, without pretending that a RECOVERY_REQUIRED backend is STABLE.
        marker = config_root / 'reviewer-activation-authorized'
        require(retained.read(marker, Path('/'), 0, private=True).strip() == b'authorized', 'REVIEWER_GUARD_UNPROVEN')
        require(not (config_root / 'reviewer-recovery-requires-activation').exists()
                and not (config_root / 'reviewer-recovery-requires-activation').is_symlink(), 'REVIEWER_GUARD_UNPROVEN')
        listener = command(['/usr/bin/ss', '-H', '-ltn']).decode()
        require(any(row.split()[3] == self.payload['listener'] for row in listener.splitlines() if len(row.split()) >= 4),
                'REVIEWER_LISTENER_UNPROVEN')
        digest = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
        manifest = json.loads(retained.read(Path(self.payload['release']) / 'artifact-manifest.json', Path('/'), 0))
        executable = digest('/proc/' + state['MainPID'] + '/exe')
        require(executable == manifest['reviewerBinarySha256'], 'REVIEWER_RESTART_REQUIRED')
        return {'pid': state['MainPID'], 'start': state['ExecMainStartTimestampMonotonic'], 'executable': executable,
                'config': retained.sha(retained.read(config_root / 'reviewer-mcp.json', Path('/'), 0)),
                'environment': retained.sha(retained.read(config_root / 'relay.env', Path('/'), 0)),
                'unit': retained.sha(retained.read(Path('/etc/systemd/system') / unit, Path('/'), 0))}


def prove(payload, native=None, *, allow_restore=True):
    config, binding = payload['config'], retained.binding_valid(payload['binding'])
    declaration = binding.get('runnerMaintenance')
    require(declaration is not None, 'OWNER_DECLARATION_REQUIRED')
    previous, observed = payload['previous'], payload['observed']
    require(previous.keys() == observed.keys(), 'COMPONENT_SET_CHANGED')
    require(not previous['general']['active'] or observed['general']['active'], 'GENERAL_TRANSPORT_UNPROVEN')
    declared_stopped_production = ('production' in declaration['runners'] and not observed['production']['active'])
    stopped_production = declared_stopped_production and payload.get('before') is None
    restored = {component for component in observed if observed[component]['active'] and not previous[component]['active']}
    if declared_stopped_production:
        require(not previous['production']['active'], 'PRODUCTION_ACTIVITY_CHANGED')
        restored.add('production')
    require(restored == declaration['runners'].keys(), 'DECLARED_ACTIVITY_MISMATCH')
    require(previous['reviewer']['active'] and observed['reviewer']['active'], 'REVIEWER_UNPROVEN')
    native = native or Native(payload)
    native.authority()
    identities, contract = services(config)
    require(restored <= identities.keys(), 'FOREIGN_OR_NEW_COMPONENT')
    remote = native.runners(contract)
    proof = {}
    # Prove every General transport before an optional Production effect.
    for component, expected in sorted(declaration['runners'].items(), key=lambda item: item[0] == 'production'):
        identity = identities[component]
        require(previous[component]['load'] == 'loaded'
                and observed[component]['load'] == 'loaded'
                and previous[component]['enabled'] == observed[component]['enabled']
                and observed[component]['enabled'] in ['enabled', 'enabled-runtime']
                and identity['name'] == expected['runnerName'], 'ORIGINAL_SERVICE_CHANGED')
        matches = [runner for runner in remote if runner.get('id') == expected['runnerId']
                   or runner.get('name') == expected['runnerName']]
        require(len(matches) == 1 and matches[0].get('id') == expected['runnerId']
                and matches[0].get('name') == expected['runnerName']
                and matches[0].get('status') in (['online', 'offline'] if component == 'production'
                    and stopped_production else ['online']) and matches[0].get('busy') is False,
                'ONLINE_IDLE_REGISTRATION_UNPROVEN')
        if component == 'production' and stopped_production:
            require(allow_restore, 'CONFIG_ADOPTION_RESTORE_FORBIDDEN')
            native.restore(expected, identity, contract)
        proof[component] = native.runner(component, expected, identity, contract)
    reviewer = native.reviewer()
    if payload.get('before') is not None:
        require(payload['before'] == {'runners': proof, 'reviewer': reviewer}, 'MAINTAINED_RUNTIME_CHANGED')
    native.authority()
    return {'runners': proof, 'reviewer': reviewer}


def configuration_transition(value, original_manifest, desired_manifest):
    """Accept only the exact rendered artifact-identity configuration change."""
    require(isinstance(value, dict) and value.keys() == {'original', 'desired'}
            and all(isinstance(raw, str) and len(raw.encode('utf-8')) <= retained.LIMIT
                    for raw in value.values()), 'CONFIG_ADOPTION_RENDER_UNPROVEN')
    raw = {key: text.encode('utf-8') for key, text in value.items()}
    decoded = {key: retained.decode(text) for key, text in raw.items()}
    for key, manifest in [('original', original_manifest), ('desired', desired_manifest)]:
        require(isinstance(decoded[key], dict) and decoded[key].get('artifact') == {
            'commit': manifest['commit'], 'sha256': manifest['releaseSourceTreeSha256']},
            'CONFIG_ADOPTION_ARTIFACT_UNPROVEN')
    require(decoded['original']['artifact'] != decoded['desired']['artifact']
            and {key: item for key, item in decoded['original'].items() if key != 'artifact'}
            == {key: item for key, item in decoded['desired'].items() if key != 'artifact'},
            'CONFIG_ADOPTION_DELTA_UNSUPPORTED')
    return raw


def adopt_config(payload, native=None):
    """Adopt one frozen artifact-only configuration through the existing lock.

    The protected accepted controller renders the expected configuration; this
    internal API is not an authority surface for arbitrary supplied renders.
    This is a current-state, explicitly selected service transition. Strict
    maintenance remains unchanged. No supplied after-proof can authorize a
    process replacement, and the immutable continuation is never rewritten.
    """
    require(isinstance(payload.get('before'), dict)
            and payload.get('observed', {}).get('production', {}).get('active') is True,
            'CONFIG_ADOPTION_ACTIVE_PRODUCTION_REQUIRED')
    require('production' in payload.get('binding', {}).get('runnerMaintenance', {}).get('runners', {}),
            'CONFIG_ADOPTION_PRODUCTION_DECLARATION_REQUIRED')
    native = native or Native(payload)
    with native.operation_lock() as descriptor:
        expected = native.configuration_transition()
        baseline = copy.deepcopy(payload['before'])
        require(baseline.get('reviewer', {}).get('config') in [retained.sha(expected[key])
                                                            for key in ['original', 'desired']],
                'CONFIG_ADOPTION_DESIRED_CONFIG_CHANGED')
        # The same admitted Apply may have rendered the new bytes after the
        # original maintenance proof. Only this exact artifact-only config
        # digest is allowed to advance before the guarded process transition.
        baseline['reviewer']['config'] = retained.sha(expected['desired'])
        current_payload = {**payload, 'before': baseline}
        before = copy.deepcopy(prove(current_payload, native, allow_restore=False))
        _, contract = services(payload['config'])
        primary = native.primary(contract)
        native.transport_dependencies()
        # Repeat the exact live proof at the effect boundary while retaining
        # the same operation lock and the caller's protected Writer lease.
        require(prove(current_payload, native, allow_restore=False) == before
                and native.primary(contract) == primary, 'CONFIG_ADOPTION_RUNTIME_CHANGED')
        require(native.configuration_transition() == expected, 'CONFIG_ADOPTION_CONFIG_CHANGED')
        native.authority()
        native.transport_dependencies()
        native.restart_configuration(descriptor)
        native.wait_production(payload['binding']['runnerMaintenance']['runners']['production'])
        after = prove({**payload, 'before': None}, native, allow_restore=False)
        require(native.configuration_transition() == expected
                and native.primary(contract) == primary, 'CONFIG_ADOPTION_CONFIG_OR_TRANSPORT_CHANGED')
        reviewer_before, reviewer_after = before['reviewer'], after['reviewer']
        require(reviewer_after['pid'] != reviewer_before['pid']
                and reviewer_after['start'] != reviewer_before['start']
                and {key: item for key, item in reviewer_after.items() if key not in ['pid', 'start']}
                == {key: item for key, item in reviewer_before.items() if key not in ['pid', 'start']},
                'CONFIG_ADOPTION_REVIEWER_NOT_ADOPTED')
        require(after['runners'].keys() == before['runners'].keys(), 'CONFIG_ADOPTION_RUNNER_SET_CHANGED')
        for component, previous in before['runners'].items():
            current = after['runners'][component]
            if component == 'production':
                require(current['pid'] != previous['pid'] and current['startTicks'] != previous['startTicks']
                        and {key: item for key, item in current.items() if key not in ['pid', 'startTicks']}
                        == {key: item for key, item in previous.items() if key not in ['pid', 'startTicks']},
                        'CONFIG_ADOPTION_PRODUCTION_NOT_ADOPTED')
            else:
                require(current == previous, 'CONFIG_ADOPTION_GENERAL_TRANSPORT_CHANGED')
        native.authority()
        return {'before': before, 'after': after}


def main():
    try:
        raw = sys.stdin.buffer.read(1024 * 1024 + 1)
        require(len(raw) <= 1024 * 1024, 'INPUT_LIMIT')
        payload = retained.decode(raw)
        action = payload.get('action', 'prove')
        require(action in ['prove', 'prove-current', 'adopt-reviewer-config'], 'ACTION_INVALID')
        result = (adopt_config(payload) if action == 'adopt-reviewer-config'
                  else prove(payload, allow_restore=action != 'prove-current'))
        print(json.dumps(result, sort_keys=True))
    except Exception as error:
        code = str(error)
        print(code if re.fullmatch(r'(RELAY_RETAINED_ACTIVATION|BOUNDED_RECOVERY|MANAGED_POOL|RUNNER_SELF_UPDATE)_[A-Z_]{1,96}', code)
              else 'RELAY_RETAINED_ACTIVATION_UNPROVEN', file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
