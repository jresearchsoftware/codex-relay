"""Read-only proof of owner-declared, already restored registered runners.

The existing bounded continuation receipt owns the declaration. It never
changes the first service snapshot, starts a runner, or supplies execution
authority. Every observation is repeated before final lifecycle validation.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import bounded_recovery as retained
from config import compile_inputs
import managed_pool
import runner_self_update


def require(condition, code):
    if not condition:
        raise ValueError('RELAY_RETAINED_ACTIVATION_' + code)


def command(argv, *, cwd=None):
    result = subprocess.run(argv, capture_output=True, timeout=60, cwd=cwd,
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

    def runners(self, contract):
        from pool_authorization import installation_authorization
        authorization = installation_authorization(self.config)
        self.github = managed_pool.GitHub(authorization['installationToken'], contract['organization'])
        self.pool_group = self.github.qualify(contract)
        return self.github.runners()

    def runner(self, component, expected, identity, contract):
        value = runner_self_update.inspect(identity['root'], identity['service'], identity['user'],
                                           expected['runnerId'], expected['runnerName'])
        state = value['serviceState']
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
        process_uid = Path('/proc/' + state['MainPID']).stat().st_uid
        require(process_uid == uid and state['ControlGroup'] == '/system.slice/' + identity['service'],
                'LIVE_UNIX_IDENTITY_UNPROVEN')
        version = command(['/usr/sbin/runuser', '-u', identity['user'], '--',
                           identity['root'] + '/bin/Runner.Listener', '--version'], cwd=identity['root']).decode().strip()
        # GitHub online/idle is the current eligibility authority; a numerical
        # version or a successful local --version probe alone is insufficient.
        require(re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', version), 'VERSION_UNPROVEN')
        return {'service': identity['service'], 'runnerId': expected['runnerId'], 'version': version}

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


def prove(payload, native=None):
    config, binding = payload['config'], retained.binding_valid(payload['binding'])
    declaration = binding.get('runnerMaintenance')
    require(declaration is not None, 'OWNER_DECLARATION_REQUIRED')
    previous, observed = payload['previous'], payload['observed']
    require(previous.keys() == observed.keys(), 'COMPONENT_SET_CHANGED')
    # DRAIN closes admission and waits for work; it does not stop this service.
    # Neither the immutable original snapshot nor the maintenance declaration
    # proves why a subsequently restored Production process is now absent.
    require('production' not in declaration['runners'] or observed['production']['active'],
            'PRODUCTION_STOP_CAUSE_UNPROVEN')
    restored = {component for component in observed if observed[component]['active'] and not previous[component]['active']}
    require(restored == declaration['runners'].keys(), 'DECLARED_ACTIVITY_MISMATCH')
    require(previous['reviewer']['active'] and observed['reviewer']['active'], 'REVIEWER_UNPROVEN')
    native = native or Native(payload)
    native.authority()
    identities, contract = services(config)
    require(restored <= identities.keys(), 'FOREIGN_OR_NEW_COMPONENT')
    remote = native.runners(contract)
    proof = {}
    for component, expected in declaration['runners'].items():
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
                and matches[0].get('status') == 'online' and matches[0].get('busy') is False,
                'ONLINE_IDLE_REGISTRATION_UNPROVEN')
        proof[component] = native.runner(component, expected, identity, contract)
    reviewer = native.reviewer()
    if payload.get('before') is not None:
        require(payload['before'] == {'runners': proof, 'reviewer': reviewer}, 'MAINTAINED_RUNTIME_CHANGED')
    native.authority()
    return {'runners': proof, 'reviewer': reviewer}


def main():
    try:
        raw = sys.stdin.buffer.read(1024 * 1024 + 1)
        require(len(raw) <= 1024 * 1024, 'INPUT_LIMIT')
        print(json.dumps(prove(retained.decode(raw)), sort_keys=True))
    except Exception as error:
        code = str(error)
        print(code if re.fullmatch(r'(RELAY_RETAINED_ACTIVATION|BOUNDED_RECOVERY|MANAGED_POOL|RUNNER_SELF_UPDATE)_[A-Z_]{1,96}', code)
              else 'RELAY_RETAINED_ACTIVATION_UNPROVEN', file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
