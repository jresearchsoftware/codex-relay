"""The narrow configuration-adoption effect, including refusals at each boundary.

Service/API observations here are explicit deterministic adapters. The separate
systemd qualification exercises actual Reviewer startup and process adoption.
"""
from contextlib import contextmanager
import copy
import io
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import retained_activation as activation
from test_retained_activation import Evidence, payload


def render(artifact, **changes):
    return json.dumps({'artifact': artifact, 'repository': 'example/relay',
                       'service': {'bind_address': '127.0.0.1', 'bind_port': 8787}, **changes}) + '\n'


def manifests():
    return ({'commit': 'a' * 40, 'releaseSourceTreeSha256': 'c' * 64},
            {'commit': 'b' * 40, 'releaseSourceTreeSha256': 'd' * 64})


def renders():
    old, desired = manifests()
    return {'original': render({'commit': old['commit'], 'sha256': old['releaseSourceTreeSha256']}),
            'desired': render({'commit': desired['commit'], 'sha256': desired['releaseSourceTreeSha256']})}


class AdoptionEvidence(Evidence):
    def __init__(self, value, damage=None):
        super().__init__(value)
        self.damage = damage
        self.restarted = False
        self.locked = False
        self.config_checks = 0
        self.dependency_checks = 0
        self.reviewer_value['config'] = activation.retained.sha(value['reviewerConfigTransition']['desired'].encode())
        self.reviewer_value['environment'] = 'e' * 64

    @contextmanager
    def operation_lock(self):
        self.locked = True
        try:
            yield 9
        finally:
            self.locked = False

    def configuration_transition(self):
        assert self.locked
        self.config_checks += 1
        expected = activation.configuration_transition(self.value['reviewerConfigTransition'], *manifests())
        if self.damage == 'config-race' and self.config_checks > 1:
            expected['desired'] += b' '
        return expected

    def primary(self, _contract):
        return {'pid': '202' if self.restarted and self.damage == 'primary' else '201', 'startTicks': '2010'}

    def transport_dependencies(self):
        assert self.locked and not self.restarted
        self.dependency_checks += 1
        activation.require(self.damage != 'dependency'
                           and not (self.damage == 'dependency-race' and self.dependency_checks > 1),
                           'CONFIG_ADOPTION_GENERAL_DEPENDENCY_UNSAFE')

    def runner(self, component, expected, identity, contract):
        proof = super().runner(component, expected, identity, contract)
        if self.restarted and component == 'production':
            if self.damage != 'production-noop':
                proof.update(pid='110', startTicks='1100')
            if self.damage == 'production-id':
                proof['runnerId'] += 1
        if self.restarted and component == 'slot-pool-2' and self.damage == 'general':
            proof['pid'] = '120'
        return proof

    def restart_configuration(self, descriptor):
        assert descriptor == 9 and self.locked
        self.events.append('restart')
        self.restarted = True
        if self.damage != 'reviewer-noop':
            self.reviewer_value = {**self.reviewer_value, 'pid': '51', 'start': '5100'}
        if self.damage == 'reviewer-start':
            self.reviewer_value['start'] = '4100'
        if self.damage in ['config', 'environment', 'unit', 'executable']:
            self.reviewer_value[self.damage] = 'f' * 64
        if self.damage == 'offline':
            self.remote[0]['status'] = 'offline'
        if self.damage == 'busy':
            self.remote[0]['busy'] = True

    def wait_production(self, expected):
        assert self.locked and self.restarted
        activation.require(self.remote[0]['status'] == 'online' and self.remote[0]['busy'] is False,
                           'ONLINE_IDLE_REGISTRATION_UNPROVEN')


def fixture(damage=None):
    value = payload()
    value['reviewerConfigTransition'] = renders()
    native = AdoptionEvidence(value, damage)
    value['before'] = copy.deepcopy(activation.prove(value, native))
    return value, native


def test_config_adoption_replaces_only_reviewer_and_production_processes():
    value, native = fixture()
    original = copy.deepcopy(value)
    result = activation.adopt_config(value, native)
    assert value == original
    assert not native.locked
    assert result['before'] == value['before']
    assert result['before']['reviewer']['config'] == result['after']['reviewer']['config']
    assert result['after']['reviewer']['pid'] == '51'
    assert result['after']['runners']['production']['pid'] == '110'
    assert native.events.count('restart') == 1
    assert native.dependency_checks == 2
    for component in value['binding']['runnerMaintenance']['runners']:
        assert result['before']['runners'][component]['runnerId'] == result['after']['runners'][component]['runnerId']
        if component != 'production':
            assert result['before']['runners'][component] == result['after']['runners'][component]
    value['before'] = result['after']
    assert activation.prove(value, native) == result['after']


def test_exact_original_config_digest_can_advance_before_same_operation_restart():
    value, native = fixture()
    value['before']['reviewer']['config'] = activation.retained.sha(value['reviewerConfigTransition']['original'].encode())
    result = activation.adopt_config(value, native)
    assert result['before']['reviewer']['config'] == activation.retained.sha(
        value['reviewerConfigTransition']['desired'].encode())
    assert native.events.count('restart') == 1


@pytest.mark.parametrize('active', [True, False])
def test_current_proof_cli_cannot_restore_a_lost_production(monkeypatch, capsys, active):
    from types import SimpleNamespace
    value = payload()
    value['action'] = 'prove-current'
    value['observed']['production']['active'] = active
    native = Evidence(value)
    if not active:
        native.remote[0]['status'] = 'offline'
    monkeypatch.setattr(activation, 'Native', lambda _payload: native)
    monkeypatch.setattr(sys, 'stdin', SimpleNamespace(buffer=io.BytesIO(json.dumps(value).encode())))
    if active:
        activation.main()
        assert json.loads(capsys.readouterr().out)['runners']['production']['runnerId'] == 55
    else:
        with pytest.raises(SystemExit) as error:
            activation.main()
        assert error.value.code == 1
        assert capsys.readouterr().err.strip() == 'RELAY_RETAINED_ACTIVATION_CONFIG_ADOPTION_RESTORE_FORBIDDEN'
    assert 'restore-production' not in native.events


@pytest.mark.parametrize('damage,code', [
    ('reviewer-noop', 'REVIEWER_NOT_ADOPTED'), ('reviewer-start', 'REVIEWER_NOT_ADOPTED'),
    ('production-noop', 'PRODUCTION_NOT_ADOPTED'), ('production-id', 'PRODUCTION_NOT_ADOPTED'),
    ('general', 'GENERAL_TRANSPORT_CHANGED'), ('primary', 'CONFIG_OR_TRANSPORT_CHANGED'),
    ('config', 'REVIEWER_NOT_ADOPTED'), ('environment', 'REVIEWER_NOT_ADOPTED'),
    ('unit', 'REVIEWER_NOT_ADOPTED'), ('executable', 'REVIEWER_NOT_ADOPTED'),
    ('offline', 'ONLINE_IDLE_REGISTRATION_UNPROVEN'), ('busy', 'ONLINE_IDLE_REGISTRATION_UNPROVEN'),
])
def test_failed_actual_adoption_never_returns_a_successful_new_baseline(damage, code):
    value, native = fixture(damage)
    with pytest.raises(ValueError, match=code):
        activation.adopt_config(value, native)
    assert native.events.count('restart') == 1
    assert not native.locked


@pytest.mark.parametrize('damage,code', [
    ('before', 'DESIRED_CONFIG_CHANGED'), ('stopped', 'ACTIVE_PRODUCTION_REQUIRED'),
    ('undeclared', 'PRODUCTION_DECLARATION_REQUIRED'), ('config-race', 'CONFIG_CHANGED'),
    ('dependency', 'GENERAL_DEPENDENCY_UNSAFE'), ('dependency-race', 'GENERAL_DEPENDENCY_UNSAFE'),
])
def test_pre_effect_refusals_preserve_processes(damage, code):
    value, native = fixture(damage)
    if damage == 'before':
        value['before']['reviewer']['config'] = '0' * 64
    elif damage == 'stopped':
        value['observed']['production']['active'] = False
    elif damage == 'undeclared':
        del value['binding']['runnerMaintenance']['runners']['production']
    with pytest.raises(ValueError, match=code):
        activation.adopt_config(value, native)
    assert 'restart' not in native.events
    assert 'restore-production' not in native.events
    assert not native.locked


@pytest.mark.parametrize('damage', ['policy', 'bind', 'original-artifact', 'desired-artifact', 'extra-artifact',
                                    'no-change', 'duplicate', 'missing', 'oversize'])
def test_only_frozen_artifact_fields_can_change(damage):
    value = renders()
    old, desired = manifests()
    decoded = json.loads(value['desired'])
    if damage == 'policy':
        decoded['repository'] = 'foreign/relay'
    elif damage == 'bind':
        decoded['service']['bind_port'] = 9999
    elif damage == 'original-artifact':
        value['original'] = value['desired']
    elif damage == 'desired-artifact':
        decoded['artifact']['commit'] = 'f' * 40
    elif damage == 'extra-artifact':
        decoded['artifact']['extra'] = True
    elif damage == 'no-change':
        old = desired
        value['original'] = value['desired']
    elif damage == 'duplicate':
        value['desired'] = '{"artifact":{},"artifact":{}}'
    elif damage == 'missing':
        del value['original']
    elif damage == 'oversize':
        value['original'] = ' ' * (activation.retained.LIMIT + 1)
    if damage in ['policy', 'bind', 'desired-artifact', 'extra-artifact']:
        value['desired'] = json.dumps(decoded)
    with pytest.raises(ValueError):
        activation.configuration_transition(value, old, desired)


@pytest.mark.parametrize('damage,code', [(None, None), ('release', 'RELEASE_CHANGED'),
    ('binary', 'EXECUTABLE_CHANGED'), ('source', 'ARTIFACT_UNPROVEN'),
    ('disk-bytes', 'DESIRED_CONFIG_CHANGED')])
def test_native_configuration_binds_both_manifests_and_exact_live_bytes(monkeypatch, damage, code):
    value = payload()
    value['release'] = '/opt/' + value['config']['environment']['namespace'] + '/releases/' + value['binding']['desiredRevision']
    value['reviewerConfigTransition'] = renders()
    old, desired = manifests()
    old['reviewerBinarySha256'] = desired['reviewerBinarySha256'] = 'a' * 64
    if damage == 'release':
        value['release'] += '-foreign'
    elif damage == 'binary':
        desired['reviewerBinarySha256'] = 'b' * 64
    elif damage == 'source':
        old['releaseSourceTreeSha256'] = 'f' * 64
    observed = []
    def read(path, *_args, **_kwargs):
        observed.append(str(path))
        if path.name == 'artifact-manifest.json':
            return json.dumps(old if path.parent.name == value['binding']['installedRevision'] else desired).encode()
        assert path.name == 'reviewer-mcp.json'
        return value['reviewerConfigTransition']['desired'].encode() + (b' ' if damage == 'disk-bytes' else b'')
    monkeypatch.setattr(activation.retained, 'read', read)
    native = activation.Native(value)
    if code is not None:
        with pytest.raises(ValueError, match=code):
            native.configuration_transition()
    else:
        assert native.configuration_transition() == {key: raw.encode() for key, raw in renders().items()}
        assert len(observed) == 3


@pytest.mark.parametrize('damage', [None, 'foreign', 'mode'])
def test_native_restart_transports_only_the_validated_helper_and_inherited_lock(tmp_path, monkeypatch, damage):
    value = payload()
    native = activation.Native(value)
    native.paths['install'] = tmp_path
    stage = tmp_path / 'releases' / ('.stage-' + value['binding']['operationId'])
    stage.mkdir(parents=True)
    helper = stage / 'reviewer-config-adoption-restart'
    helper.write_bytes(b'#!/bin/sh\nexit 0\n')
    helper.chmod(0o755 if damage == 'mode' else 0o700)
    value['restart'] = str(helper if damage != 'foreign' else Path('/usr/bin/true'))
    reads, calls = [], []
    monkeypatch.setattr(activation.retained, 'read', lambda path, *_a, **_k: reads.append(path))
    monkeypatch.setattr(activation, 'command', lambda argv, **options: calls.append((argv, options)))
    if damage is None:
        native.restart_configuration(9)
        assert reads == [helper]
        assert calls == [([str(helper), '--maintained-config-adoption', value['binding']['operationId'], '9'],
                          {'pass_fds': (9,)})]
    else:
        with pytest.raises(ValueError, match='RESTART_PATH_UNPROVEN'):
            native.restart_configuration(9)
        assert calls == []


@pytest.mark.parametrize('damage,code', [(None, None), ('id', 'REGISTRATION_UNPROVEN'),
    ('name', 'REGISTRATION_UNPROVEN'), ('duplicate', 'REGISTRATION_UNPROVEN'),
    ('busy', 'REGISTRATION_UNPROVEN'), ('status', 'REGISTRATION_UNPROVEN'),
    ('timeout', 'PRODUCTION_NOT_ONLINE'), ('unavailable', 'API_UNAVAILABLE')])
def test_native_production_registration_wait_is_bounded_read_only_and_exact(monkeypatch, damage, code):
    from types import SimpleNamespace
    value = payload()
    native = activation.Native(value)
    expected = value['binding']['runnerMaintenance']['runners']['production']
    runner = {'id': expected['runnerId'], 'name': expected['runnerName'], 'status': 'offline', 'busy': False}
    calls, sleeps = [], []
    def observed():
        calls.append('read')
        if damage == 'unavailable':
            raise ValueError('API_UNAVAILABLE')
        current = {**runner, 'status': 'online' if len(calls) > 1 else 'offline'}
        if damage == 'id':
            current['id'] += 1
        elif damage == 'name':
            current['name'] += '-foreign'
        elif damage == 'busy':
            current['busy'] = True
        elif damage == 'status':
            current['status'] = 'unknown'
        return [current, current] if damage == 'duplicate' else [current]
    native.github = SimpleNamespace(runners=observed)
    ticks = iter([0, 30] if damage == 'timeout' else [0, 1])
    monkeypatch.setattr(activation.time, 'monotonic', lambda: next(ticks))
    monkeypatch.setattr(activation.time, 'sleep', lambda value: sleeps.append(value))
    if code is None:
        native.wait_production(expected)
        assert calls == ['read', 'read'] and sleeps == [1]
    else:
        with pytest.raises(ValueError, match=code):
            native.wait_production(expected)
        assert calls == ['read'] and sleeps == []


@pytest.mark.parametrize('component,field,control', [
    (component, field, control) for component in ['general', 'slot-pool-2']
    for field in ['PartOf', 'Requires', 'BindsTo'] for control in ['reviewer', 'production']
] + [(component, 'PropagatesStopTo', control) for component in ['reviewer', 'production']
     for control in ['general', 'slot-pool-2']])
def test_native_known_general_restart_dependencies_are_refused(monkeypatch, component, field, control):
    value = payload()
    native = activation.Native(value)
    identities, _ = activation.services(value['config'])
    units = {name: identity['service'] for name, identity in identities.items()}
    units['reviewer'] = activation.compile_inputs(value['config']).get('relay_reviewer_service_name', 'reviewer-mcp.service')
    def command(argv):
        observed = {'LoadState': 'loaded', 'NeedDaemonReload': 'no', 'PartOf': '',
                    'Requires': 'sysinit.target', 'BindsTo': '', 'PropagatesStopTo': '',
                    'ConsistsOf': '', 'RequiredBy': '', 'BoundBy': '', 'RequisiteOf': ''}
        if argv[2] == units[component]:
            observed[field] = units[control]
        return '\n'.join(key + '=' + item for key, item in observed.items()).encode()
    monkeypatch.setattr(activation, 'command', command)
    with pytest.raises(ValueError, match='GENERAL_DEPENDENCY_UNSAFE'):
        native.transport_dependencies()


@pytest.mark.parametrize('component,target', [(component, target) for component in ['reviewer', 'production']
                                            for target in ['foreign.service', 'foreign.target']])
def test_native_control_restart_cannot_stop_an_explicit_foreign_unit(monkeypatch, component, target):
    value = payload()
    native = activation.Native(value)
    identities, _ = activation.services(value['config'])
    units = {'production': identities['production']['service'],
             'reviewer': activation.compile_inputs(value['config']).get('relay_reviewer_service_name', 'reviewer-mcp.service')}
    def command(argv):
        observed = {'LoadState': 'loaded', 'NeedDaemonReload': 'no', 'PartOf': '',
                    'Requires': '', 'BindsTo': '', 'PropagatesStopTo': '',
                    'ConsistsOf': '', 'RequiredBy': '', 'BoundBy': '', 'RequisiteOf': ''}
        if argv[2] == units[component]:
            observed['PropagatesStopTo'] = units['production'] + ' ' + target
        return '\n'.join(key + '=' + item for key, item in observed.items()).encode()
    monkeypatch.setattr(activation, 'command', command)
    with pytest.raises(ValueError, match='CONFIG_ADOPTION_FOREIGN_STOP_UNSAFE'):
        native.transport_dependencies()


@pytest.mark.parametrize('damage', [None, 'reload', 'not-loaded', 'missing', 'missing-reverse', 'duplicate', 'malformed'])
def test_native_dependency_read_is_complete_and_does_not_reject_foreign_graphs(monkeypatch, damage):
    value = payload()
    native = activation.Native(value)
    identities, _ = activation.services(value['config'])
    controls = {identities['production']['service'],
                activation.compile_inputs(value['config']).get('relay_reviewer_service_name', 'reviewer-mcp.service')}
    calls = []
    def command(argv):
        calls.append(argv)
        observed = {'LoadState': 'loaded', 'NeedDaemonReload': 'no', 'PartOf': 'foreign.service',
                    'Requires': 'sysinit.target foreign.service', 'BindsTo': 'unrelated.service',
                    'PropagatesStopTo': '' if argv[2] in controls else 'foreign.service',
                    'ConsistsOf': '', 'RequiredBy': '', 'BoundBy': '', 'RequisiteOf': ''}
        if damage == 'reload':
            observed['NeedDaemonReload'] = 'yes'
        elif damage == 'not-loaded':
            observed['LoadState'] = 'not-found'
        elif damage == 'missing':
            del observed['BindsTo']
        elif damage == 'missing-reverse':
            del observed['ConsistsOf']
        raw = '\n'.join(key + '=' + item for key, item in observed.items())
        if damage == 'duplicate':
            raw += '\nPartOf='
        elif damage == 'malformed':
            raw += '\nunknown row'
        return raw.encode()
    monkeypatch.setattr(activation, 'command', command)
    if damage is None:
        native.transport_dependencies()
        assert len(calls) == 8
    else:
        with pytest.raises(ValueError, match='GENERAL_DEPENDENCY_UNPROVEN'):
            native.transport_dependencies()
        assert len(calls) == 1


@pytest.mark.parametrize('edge', ['ConsistsOf', 'RequiredBy', 'BoundBy', 'RequisiteOf', 'PropagatesStopTo'])
@pytest.mark.parametrize('via_production', [False, True])
@pytest.mark.parametrize('target', ['foreign.service', 'foreign.target', 'general'])
def test_loaded_propagation_closure_refuses_foreign_and_general(monkeypatch, edge, via_production, target):
    native = activation.Native(payload())
    identities, _ = activation.services(native.config)
    reviewer = activation.compile_inputs(native.config).get('relay_reviewer_service_name', 'reviewer-mcp.service')
    production = identities['production']['service']
    forbidden = identities['general']['service'] if target == 'general' else target
    def command(argv):
        fields = argv[3].removeprefix('--property=').split(',')
        observed = dict.fromkeys(fields, '')
        observed.update(LoadState='loaded', NeedDaemonReload='no')
        if argv[2] == reviewer:
            if via_production:
                observed['ConsistsOf'] = production
            else:
                observed[edge] = forbidden
        if argv[2] == production and via_production:
            observed[edge] = forbidden
        return '\n'.join(key + '=' + item for key, item in observed.items()).encode()
    monkeypatch.setattr(activation, 'command', command)
    with pytest.raises(ValueError, match='GENERAL_DEPENDENCY_UNSAFE' if target == 'general' else 'FOREIGN_STOP_UNSAFE'):
        native.transport_dependencies()


def test_loaded_control_propagation_cycle_is_bounded(monkeypatch):
    native = activation.Native(payload())
    identities, _ = activation.services(native.config)
    production = identities['production']['service']
    reviewer = activation.compile_inputs(native.config).get('relay_reviewer_service_name', 'reviewer-mcp.service')
    calls = []
    def command(argv):
        calls.append(argv[2])
        observed = dict.fromkeys(argv[3].removeprefix('--property=').split(','), '')
        observed.update(LoadState='loaded', NeedDaemonReload='no')
        if argv[2] in [reviewer, production]:
            observed['ConsistsOf'] = production if argv[2] == reviewer else reviewer
        return '\n'.join(key + '=' + item for key, item in observed.items()).encode()
    monkeypatch.setattr(activation, 'command', command)
    native.transport_dependencies()
    assert len(calls) == len(set(calls)) == 8
