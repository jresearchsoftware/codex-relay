"""Exercise pool Apply, shared capacity and uncertain-mutation reconciliation."""
import copy
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
import config
import managed_pool as pool
import managed_pool_transport as transport


def inputs(capacity=2, namespace='codex-relay', repository='example-org/sample-project'):
    value = json.loads((ROOT / 'deploy/example.json').read_text())
    value['consumer']['repository'] = repository
    value['consumer']['generalRunnerPool'] = {'desiredCapacity': capacity}
    value['environment']['instance'] = {'reviewerPort': 18787, 'publicationEnabled': False}
    value['environment']['namespace'] = namespace
    value['environment']['generalRunner'].update(scope='organization', group='sample-general', poolApp={
        'appId': '101', 'installationId': '201', 'privateKeyFile': '/owner-private/app.pem'})
    for key, path in value['consumer']['paths'].items():
        value['consumer']['paths'][key] = path.replace('/codex-relay/', '/' + namespace + '/')
    config.derive_managed_pool_slots(value)
    return value


class MemoryState:
    def __init__(self):
        self.value = None
        self.writes = []

    def read(self):
        return copy.deepcopy(self.value)

    def write(self, value):
        self.value = copy.deepcopy(value)
        self.writes.append(copy.deepcopy(value))


class Remote:
    def __init__(self):
        self.values = {}
        self.tokens = []
        self.label_mutations = []
        self.lose_labels_response = False
        self.lose_token_response = False

    def qualify(self, contract):
        return 7

    def runners(self):
        return copy.deepcopy(list(self.values.values()))

    def in_group(self, group, runner):
        return group == 7

    def ephemeral(self, purpose):
        if self.lose_token_response:
            raise pool.PoolError('TOKEN_NOT_CREATED')
        self.tokens.append(purpose)
        return 'ephemeral-' + purpose

    def labels(self, identity, labels):
        self.label_mutations.append((identity, labels))
        self.values[identity]['labels'] = [{'name': label, 'type': 'custom'} for label in labels]
        if self.lose_labels_response:
            self.lose_labels_response = False
            raise pool.PoolError('UNKNOWN_LABEL_RESULT')


class Host:
    def __init__(self, remote, state):
        self.remote, self.state = remote, state
        self.local, self.services = {}, set()
        self.next_id = 100
        self.mutations, self.stops, self.retired = [], [], []
        self.pending_attempts = False
        self.lose_registration = False
        self.lose_removal = False
        self.defer_stop = False
        self.local_only_cleanup = []

    def registration(self, member):
        return self.local.get(member['id'])

    def configure(self, member, token, remove=False):
        assert self.state.value['members'][member['id']]['phase'] == ('remove' if remove else 'register')
        assert token == 'ephemeral-' + ('remove' if remove else 'registration')
        self.mutations.append((member['id'], remove))
        if remove:
            assert member['id'] not in self.services
            identity = self.local.pop(member['id'])
            self.remote.values.pop(identity)
            if self.lose_removal:
                self.lose_removal = False
                raise pool.PoolError('UNKNOWN_REMOVE_RESULT')
        else:
            self.next_id += 1
            self.local[member['id']] = self.next_id
            self.remote.values[self.next_id] = {'id': self.next_id, 'name': member['name'],
                                               'busy': False, 'labels': [], 'status': 'online'}
            if self.lose_registration:
                self.lose_registration = False
                raise pool.PoolError('UNKNOWN_REGISTER_RESULT')

    def start(self, member):
        self.services.add(member['id'])

    def ready(self, member):
        return member['id'] in self.services

    def removal_stopped(self, member):
        return member['id'] not in self.services and not self.defer_stop

    def registration_metadata_present(self, member):
        return member['id'] in self.local

    def attempts_idle(self, consumers):
        assert consumers
        return not self.pending_attempts

    def stop_idle(self, member, remote_idle):
        if self.defer_stop or not remote_idle():
            return False
        self.stops.append(member['id'])
        self.services.discard(member['id'])
        return True

    def retire(self, member):
        assert member['id'] not in self.services and member['id'] not in self.local
        self.retired.append(member['id'])

    def forget_registration(self, member):
        self.local_only_cleanup.append(member['id'])
        self.local.pop(member['id'])


def setup(capacity=2):
    contract = pool.pool_contract(inputs(capacity))
    state, github = MemoryState(), Remote()
    host = Host(github, state)
    return contract, state, github, host


def test_public_capacity_is_one_scalar_and_internal_recovery_routes_stay_stable():
    first, second = inputs(2), inputs(15, 'another-relay', 'example-org/another-project')
    config.validate(first, ROOT)
    config.validate(second, ROOT)
    assert len(first['consumer']['executionSlots']) == len(second['consumer']['executionSlots']) == 32
    assert pool.binding(pool.pool_contract(first)) == pool.binding(pool.pool_contract(second))
    assert first['consumer']['executionSlots'][1]['paths'] != second['consumer']['executionSlots'][1]['paths']
    assert len({slot['runnerUser'] for slot in first['consumer']['executionSlots']}) == 1
    assert len({slot['runtimeUser'] for slot in first['consumer']['executionSlots']}) == 1
    before = copy.deepcopy(first['consumer']['executionSlots'])
    first['consumer']['generalRunnerPool']['desiredCapacity'] = 1
    config.derive_managed_pool_slots(first)
    assert first['consumer']['executionSlots'] == before
    assert config.loads(json.dumps(first), ROOT) == first


def test_legacy_omission_does_not_add_pool_or_change_registration_and_service():
    value = config.load(ROOT / 'deploy/example.json', ROOT)
    assert 'generalRunnerPool' not in value['consumer'] and 'executionSlots' not in value['consumer']
    assert 'relay_general_runner_pool' not in config.compile_inputs(value)


def test_create_repeat_and_expand_never_multiply_capacity_by_repository_or_runtime_user():
    contract, state, github, host = setup()
    result = pool.reconcile(contract, state, github, host)
    assert result['ready'] == ['primary', 'pool-2']
    assert len(host.mutations) == 2 and len(github.values) == 2
    label_count = len(github.label_mutations)
    pool.reconcile(contract, state, github, host)
    other = pool.pool_contract(inputs(2, 'another-relay', 'example-org/another-project'))
    pool.reconcile(other, state, github, host)
    assert len(host.mutations) == 2 and len(github.values) == 2
    assert len(github.label_mutations) == label_count
    contract['desiredCapacity'] = 4
    result = pool.reconcile(contract, state, github, host)
    assert len(result['ready']) == len(github.values) == 4
    assert set(state.value['consumers']) == {'example-org/sample-project', 'example-org/another-project'}


def test_busy_contraction_removes_scheduling_labels_but_never_stops_active_jobs():
    contract, state, github, host = setup(3)
    pool.reconcile(contract, state, github, host)
    github.values[host.local['pool-3']]['busy'] = True
    contract['desiredCapacity'] = 1
    result = pool.reconcile(contract, state, github, host)
    assert result['draining'] == ['pool-3'] and result['retired'] == ['pool-2']
    assert 'pool-3' not in host.stops and len(github.values) == 2
    assert github.values[host.local['pool-3']]['labels'] == []
    github.values[host.local['pool-3']]['busy'] = False
    result = pool.reconcile(contract, state, github, host)
    assert result['retired'] == ['pool-3'] and len(github.values) == 1


@pytest.mark.parametrize('boundary', ['pending_attempts', 'defer_stop'])
def test_idle_remote_is_insufficient_when_original_attempt_or_local_process_is_unresolved(boundary):
    contract, state, github, host = setup()
    pool.reconcile(contract, state, github, host)
    setattr(host, boundary, True)
    contract['desiredCapacity'] = 1
    result = pool.reconcile(contract, state, github, host)
    assert result['draining'] == ['pool-2'] and not host.stops
    assert len(github.values) == 2


def test_lost_registration_response_is_reconciled_by_identity_without_second_configure():
    contract, state, github, host = setup(1)
    host.lose_registration = True
    with pytest.raises(pool.PoolError, match='UNKNOWN_REGISTER'):
        pool.reconcile(contract, state, github, host)
    assert state.value['members']['primary']['phase'] == 'register'
    assert pool.reconcile(contract, state, github, host)['ready'] == ['primary']
    assert host.mutations == [('primary', False)] and github.tokens == ['registration']


def test_missing_local_half_of_ambiguous_registration_does_not_retry_or_adopt_remote():
    contract, state, github, host = setup(1)
    host.lose_registration = True
    with pytest.raises(pool.PoolError):
        pool.reconcile(contract, state, github, host)
    host.local.clear()
    with pytest.raises(pool.PoolError, match='REGISTRATION_UNCERTAIN'):
        pool.reconcile(contract, state, github, host)
    assert host.mutations == [('primary', False)]


def test_token_failure_before_configuration_does_not_leave_false_registration_intent():
    contract, state, github, host = setup(1)
    github.lose_token_response = True
    with pytest.raises(pool.PoolError):
        pool.reconcile(contract, state, github, host)
    assert state.value['members'] == {} and host.mutations == []


def test_lost_remove_response_is_observed_and_retired_without_second_removal():
    contract, state, github, host = setup()
    pool.reconcile(contract, state, github, host)
    contract['desiredCapacity'] = 1
    host.lose_removal = True
    with pytest.raises(pool.PoolError, match='UNKNOWN_REMOVE'):
        pool.reconcile(contract, state, github, host)
    assert state.value['members']['pool-2']['phase'] == 'remove'
    assert pool.reconcile(contract, state, github, host)['retired'] == ['pool-2']
    assert host.mutations.count(('pool-2', True)) == 1


def test_observed_remote_removal_reconciles_retained_local_metadata_without_new_remote_mutation():
    contract, state, github, host = setup()
    pool.reconcile(contract, state, github, host)
    identity = host.local['pool-2']
    state.value['members']['pool-2']['phase'] = 'remove'
    github.values.pop(identity)
    host.services.discard('pool-2')
    contract['desiredCapacity'] = 1
    result = pool.reconcile(contract, state, github, host)
    assert result['retired'] == ['pool-2']
    assert host.local_only_cleanup == ['pool-2']
    assert host.mutations == [('primary', False), ('pool-2', False)]


@pytest.mark.parametrize('remaining', ['.runner', '.credentials', '.credentials_rsaparams'])
def test_reserved_removal_reconciles_each_partial_local_marker_without_strict_parse_or_remote_retry(tmp_path, remaining):
    contract, state, github, host = setup(2)
    member = contract['members'][1]
    member['root'] = str(tmp_path)
    pool.reconcile(contract, state, github, host)
    identity = host.local['pool-2']
    state.value['members']['pool-2']['phase'] = 'remove'
    github.values.pop(identity)
    host.services.discard('pool-2')
    contract['desiredCapacity'] = 1
    marker = tmp_path / remaining
    marker.write_text('partial local bytes must not be parsed')
    marker.chmod(0o600)
    strict_host = object.__new__(pool.Host)
    strict_host.user = SimpleNamespace(pw_uid=os.getuid())
    strict_host.contract = contract
    original_registration = host.registration
    host.registration = lambda value: strict_host.registration(value) if value['id'] == 'pool-2' else original_registration(value)
    original_present = host.registration_metadata_present
    host.registration_metadata_present = lambda value: (strict_host.registration_metadata_present(value)
        if value['id'] == 'pool-2' else original_present(value))
    original_forget = host.forget_registration
    def forget(value):
        assert host.removal_stopped(value) and not github.values.get(identity)
        marker.unlink()
        original_forget(value)
    host.forget_registration = forget
    result = pool.reconcile(contract, state, github, host)
    assert result['retired'] == ['pool-2'] and host.local_only_cleanup == ['pool-2']
    assert host.mutations == [('primary', False), ('pool-2', False)]
    assert github.tokens == ['registration', 'registration']


@pytest.mark.parametrize('remaining', ['.runner', '.credentials', '.credentials_rsaparams'])
def test_unreserved_partial_registration_stays_ambiguous(tmp_path, remaining):
    contract, state, github, host = setup(1)
    member = contract['members'][0]
    member['root'] = str(tmp_path)
    (tmp_path / remaining).write_text('unreserved partial metadata')
    strict_host = object.__new__(pool.Host)
    strict_host.user = SimpleNamespace(pw_uid=os.getuid())
    strict_host.contract = contract
    host.registration = strict_host.registration
    with pytest.raises(pool.PoolError, match='LOCAL_REGISTRATION_AMBIGUOUS'):
        pool.reconcile(contract, state, github, host)
    assert host.mutations == [] and github.tokens == []


def test_reserved_remove_refuses_renamed_original_id_and_live_cgroup_before_local_cleanup():
    contract, state, github, host = setup(2)
    pool.reconcile(contract, state, github, host)
    identity = host.local['pool-2']
    state.value['members']['pool-2']['phase'] = 'remove'
    github.values[identity]['name'] = 'renamed-member'
    with pytest.raises(pool.PoolError, match='REMOVAL_UNCERTAIN'):
        pool.reconcile(contract, state, github, host)
    github.values.pop(identity)
    with pytest.raises(pool.PoolError, match='LOCAL_CLEANUP_UNPROVEN'):
        pool.reconcile(contract, state, github, host)
    assert host.local_only_cleanup == [] and host.mutations == [('primary', False), ('pool-2', False)]


def test_startup_requires_native_online_and_live_service_before_ready_without_second_start(monkeypatch):
    contract, state, github, host = setup(1)
    starts = []
    original_start = host.start
    def start(member):
        starts.append(member['id'])
        original_start(member)
        github.values[host.local[member['id']]]['status'] = 'offline'
    host.start = start
    real_wait_ready = pool.wait_ready
    monkeypatch.setattr(pool, 'wait_ready', lambda *args: real_wait_ready(*args, timeout=0))
    with pytest.raises(pool.PoolError, match='STARTUP_READINESS_UNPROVEN'):
        pool.reconcile(contract, state, github, host)
    assert state.value['members']['primary']['phase'] == 'starting'
    with pytest.raises(pool.PoolError, match='STARTUP_READINESS_UNPROVEN'):
        pool.reconcile(contract, state, github, host)
    assert starts == ['primary'] and host.mutations == [('primary', False)]
    github.values[host.local['primary']]['status'] = 'online'
    host.services.clear()
    with pytest.raises(pool.PoolError, match='STARTUP_READINESS_UNPROVEN'):
        pool.reconcile(contract, state, github, host)
    assert state.value['members']['primary']['phase'] == 'starting'
    host.services.add('primary')
    assert pool.reconcile(contract, state, github, host)['ready'] == ['primary']
    assert starts == ['primary'] and state.value['members']['primary']['phase'] == 'ready'


def test_lost_idempotent_label_response_is_observed_before_next_mutation():
    contract, state, github, host = setup(1)
    github.lose_labels_response = True
    with pytest.raises(pool.PoolError, match='UNKNOWN_LABEL'):
        pool.reconcile(contract, state, github, host)
    assert pool.reconcile(contract, state, github, host)['ready'] == ['primary']
    assert len(github.label_mutations) == 1 and host.mutations == [('primary', False)]


def test_secondary_stale_capacity_does_not_resize_pool_but_can_join_after_sync():
    contract, state, github, host = setup(2)
    pool.reconcile(contract, state, github, host)
    secondary = pool.pool_contract(inputs(2, 'another-relay', 'example-org/another-project'))
    pool.reconcile(secondary, state, github, host)
    contract['desiredCapacity'] = 4
    pool.reconcile(contract, state, github, host)
    with pytest.raises(pool.PoolError, match='DESIRED_CAPACITY_CONFLICT'):
        pool.reconcile(secondary, state, github, host)
    secondary['desiredCapacity'] = 4
    pool.reconcile(secondary, state, github, host)
    assert len(github.values) == 4


def test_repository_pool_binding_cannot_replace_group_or_app_to_adopt_credentials():
    contract, state, github, host = setup(1)
    pool.reconcile(contract, state, github, host)
    contract['installationId'] = '999'
    with pytest.raises(pool.PoolError, match='BINDING_CONFLICT'):
        pool.reconcile(contract, state, github, host)


def test_app_key_stays_local_and_installation_token_requests_only_runner_permission(tmp_path, monkeypatch):
    value = inputs(1)
    key = tmp_path / 'private.pem'
    key.write_text('synthetic key fixture')
    value['environment']['generalRunner']['poolApp']['privateKeyFile'] = str(key)
    calls = []
    monkeypatch.setattr(transport.subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=b'signature'))

    class App:
        def __init__(self, token, organization):
            assert organization == 'example-org' and token.count('.') == 2

        def request(self, method, path, body=None):
            calls.append((method, path, body))
            if path == '/app':
                return {'id': 101}
            if path == '/app/installations/201':
                return {'id': 201, 'app_id': 101, 'account': {'login': 'example-org', 'type': 'Organization'},
                        'permissions': {pool.PERMISSION: 'write'}}
            return {'token': 'synthetic-installation-token', 'permissions': {pool.PERMISSION: 'write'},
                    'expires_at': (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}

    result = transport.installation_authorization(value, App)
    assert result == {'appId': '101', 'installationId': '201', 'organization': 'example-org',
                      'installationToken': 'synthetic-installation-token'}
    assert calls[-1] == ('POST', '/app/installations/201/access_tokens', {'permissions': {pool.PERMISSION: 'write'}})
    assert 'privateKeyFile' not in json.dumps(pool.pool_contract(value))


def test_deployment_contract_uses_one_physical_member_per_capacity_not_internal_slot():
    compiled = config.compile_inputs(inputs(2))
    assert compiled['relay_general_runner_service_name'] == 'relay-general-pool-1.service'
    assert compiled['relay_additional_execution_slots'][0]['relay_runner_service_name'] == 'relay-general-pool-2.service'
    member = (ROOT / 'deploy/ansible/tasks/managed-pool-member.yml').read_text()
    assert "become_user: '{{ relay_general_runner_pool.runnerUser }}'" in member
    provision = (ROOT / 'deploy/ansible/tasks/managed-pool.yml').read_text()
    assert 'members[:relay_general_runner_pool.desiredCapacity]' in provision
    source = (ROOT / 'deploy/relay-deploy.py').read_text()
    assert source.index('pool_guard = apply_guard') < source.index('run_backend(argv, BACKEND, env, log, guard, pool_guard)')
    assert 'reconcile_pool(target, key, config, revision, guard' in source


def test_registration_sets_private_umask_after_identity_transition_without_token_in_argv(tmp_path, monkeypatch):
    import stat
    import subprocess
    contract = pool.pool_contract(inputs(1))
    member = {**contract['members'][0], 'root': str(tmp_path), 'state': str(tmp_path / 'state')}
    marker = {'agentName': member['name'], 'agentId': 101,
              'gitHubUrl': 'https://github.com/' + contract['organization'],
              'poolName': contract['group'], 'workFolder': member['state'] + '/work'}
    token = 'synthetic-ephemeral-registration-value'
    script = tmp_path / 'config.sh'
    script.write_text('#!/usr/bin/python3\nimport os\nfrom pathlib import Path\n'
                      f'assert os.environ["ACTIONS_RUNNER_INPUT_TOKEN"] == {token!r}\n'
                      f'Path(".runner").write_text({json.dumps(marker)!r})\n'
                      'Path(".credentials").write_text("synthetic fixture metadata")\n')
    script.chmod(0o750)
    real_run = subprocess.run
    calls = []

    def identity_transition(argv, **kwargs):
        calls.append(argv)
        assert argv[:5] == ['/usr/sbin/runuser', '--preserve-environment', '-u', contract['runnerUser'], '--']
        assert argv[5:9] == ['/bin/sh', '-c', 'umask 077; exec "$@"', 'relay-pool-config']
        assert token not in json.dumps(argv)
        assert kwargs['env']['ACTIONS_RUNNER_INPUT_TOKEN'] == token
        assert kwargs['stdout'] == kwargs['stderr'] == subprocess.DEVNULL
        # Simulate PAM resetting the inherited mask to a public default before
        # executing the real final shell/config boundary. No identity changes.
        return real_run(argv[5:], **kwargs, umask=0o022)

    monkeypatch.setattr(pool.subprocess, 'run', identity_transition)
    host = object.__new__(pool.Host)
    host.contract, host.user = contract, SimpleNamespace(pw_uid=os.getuid())
    host.configure(member, token)
    assert len(calls) == 1
    assert all(stat.S_IMODE((tmp_path / name).stat().st_mode) == 0o600 for name in ['.runner', '.credentials'])
    assert host.registration(member) == 101


@pytest.mark.parametrize('bad', ['unrestricted', 'foreign-ref', 'validation-ref', 'missing-recovery'])
def test_live_group_qualification_rejects_untrusted_current_repository_refs_without_mutating_acl(bad):
    contract = pool.pool_contract(inputs(1))
    group = {'id': 7, 'name': contract['group'], 'visibility': 'selected',
             'restricted_to_workflows': True, 'selected_workflows': contract['workflowRefs'][:]}
    if bad == 'unrestricted':
        group['restricted_to_workflows'] = False
    elif bad == 'foreign-ref':
        group['selected_workflows'][0] = group['selected_workflows'][0].replace('refs/heads/main', 'refs/heads/candidate')
    elif bad == 'validation-ref':
        group['selected_workflows'].append(contract['repository'] + '/.github/workflows/validation.yml@refs/heads/main')
    else:
        group['selected_workflows'].pop()
    github = pool.GitHub('synthetic-token', contract['organization'])
    requests = []
    github.request = lambda method, path: (requests.append((method, path)) or group)
    github.pages = lambda path, field: [group] if field == 'runner_groups' else [{'full_name': contract['repository']}]
    with pytest.raises(pool.PoolError, match='GROUP_'):
        github.qualify(contract)
    assert all(method == 'GET' for method, _ in requests)


def test_cgroup_freeze_precedes_inspection_and_never_signals_an_active_worker(monkeypatch):
    contract = pool.pool_contract(inputs(1))
    member = contract['members'][0]
    host = object.__new__(pool.Host)
    calls = []
    host.service = lambda member: {'ActiveState': 'active', 'MainPID': '50', 'ControlPID': '0',
                                   'ControlGroup': '/system.slice/' + member['service']}
    host.command = lambda argv: calls.append(argv) or b''

    class FakePath:
        def __init__(self, value):
            self.value = str(value)

        def __truediv__(self, value):
            return FakePath(self.value + '/' + str(value))

        def read_text(self):
            return 'frozen 1' if self.value.endswith('cgroup.events') else '51'

        def read_bytes(self):
            return b'Runner.Worker\x00run\x00'

        def rglob(self, pattern):
            return []

        def resolve(self):
            return SimpleNamespace(name='Runner.Worker')

        @property
        def name(self):
            return self.value.rsplit('/', 1)[-1]

    monkeypatch.setattr(pool, 'Path', FakePath)
    assert host.stop_idle(member, lambda: True) is False
    assert calls == [['/usr/bin/systemctl', 'freeze', member['service']],
                     ['/usr/bin/systemctl', 'thaw', member['service']]]


def test_dead_unit_with_remaining_cgroup_worker_is_not_retired(monkeypatch):
    member = pool.pool_contract(inputs(1))['members'][0]
    host = object.__new__(pool.Host)
    host.service = lambda member: {'ActiveState': 'failed', 'MainPID': '0', 'ControlPID': '0',
                                   'ControlGroup': '/system.slice/' + member['service']}

    class Cgroup:
        def __init__(self, value):
            pass

        def exists(self):
            return True

        def rglob(self, pattern):
            return []

        def __truediv__(self, value):
            return self

        def read_text(self):
            return '51\n'

    monkeypatch.setattr(pool, 'Path', Cgroup)
    assert host.stop_idle(member, lambda: True) is False


def install_fixture(tmp_path):
    contract = pool.pool_contract(inputs(1))
    template = (ROOT / 'deploy/ansible/roles/relay_runner/templates/relay-managed-pool.service.j2').read_text()
    runner_uid = os.getuid() if os.getuid() else 1001
    for directory in ['opt', 'var/lib', 'etc/systemd/system']:
        (tmp_path / directory).mkdir(parents=True, exist_ok=True)
    absent = lambda member: {'LoadState': 'not-found', 'ActiveState': 'inactive',
                             'MainPID': '0', 'ControlPID': '0', 'FragmentPath': ''}
    arguments = {'root': tmp_path, 'owner_uid': os.getuid(), 'runner_uid': runner_uid, 'service_probe': absent}
    plan = pool.installation_plan(contract, template, **arguments)
    for logical in plan['createParents']:
        (tmp_path / logical.lstrip('/')).mkdir(mode=0o755)
    member = contract['members'][0]
    for logical in plan['members']['primary']['createDirectories']:
        path = tmp_path / logical.lstrip('/')
        path.mkdir(mode=0o750)
        if os.getuid() != runner_uid:
            os.chown(path, runner_uid, -1)
    return contract, template, arguments, member


def fixture_file(tmp_path, logical, value, uid, mode=0o600):
    path = tmp_path / logical.lstrip('/')
    if not path.parent.exists():
        path.parent.mkdir(mode=0o750)
        if os.getuid() != uid:
            os.chown(path.parent, uid, -1)
    path.write_text(value)
    path.chmod(mode)
    if os.getuid() != uid:
        os.chown(path, uid, -1)
    return path


def fixture_unit(contract, template, member):
    for field, value in {'relay_general_runner_pool.name': contract['name'],
                         'relay_general_runner_pool.runnerUser': contract['runnerUser'],
                         **{'relay_pool_member.' + key: member[key] for key in ['id', 'root', 'state']}}.items():
        template = template.replace('{{ ' + field + ' }}', value)
    return template


def fixture_package(tmp_path, member, uid):
    for path in ['/config.sh', '/run.sh', '/bin/Runner.Listener']:
        fixture_file(tmp_path, member['root'] + path, 'synthetic-package', uid, 0o750)


def fixture_registration(tmp_path, contract, member, uid):
    fixture_file(tmp_path, member['root'] + '/.runner', json.dumps({'agentName': member['name'],
        'agentId': 101, 'gitHubUrl': 'https://github.com/' + contract['organization'],
        'poolName': contract['group'], 'workFolder': member['state'] + '/work'}), uid)
    fixture_file(tmp_path, member['root'] + '/.credentials', 'synthetic-credentials', uid)


def fixture_binding(tmp_path, contract):
    fixture_file(tmp_path, '/var/lib/codex-relay-pools/' + contract['name'] + '/pool.json',
        json.dumps({'binding': pool.binding(contract), 'ownerRepository': contract['repository'],
                    'desiredCapacity': 1, 'members': {'primary': {'phase': 'ready', 'runnerId': 101}}}), os.getuid())


def unchanged_tree(root):
    return {str(path.relative_to(root)): (path.lstat().st_uid, path.lstat().st_gid,
            path.lstat().st_mode, path.lstat().st_mtime_ns, path.lstat().st_ctime_ns,
            path.read_bytes() if path.is_file() and not path.is_symlink() else None)
            for path in root.rglob('*')}


@pytest.mark.parametrize('foreign', ['root', 'state', 'parent'])
def test_install_preflight_rejects_wrong_owner_or_unsafe_parent_without_chown_chmod_or_extraction(tmp_path, foreign):
    contract, template, arguments, member = install_fixture(tmp_path)
    logical = member[foreign] if foreign != 'parent' else '/opt/codex-relay-pools'
    path = tmp_path / logical.lstrip('/')
    if foreign == 'parent':
        path.chmod(0o777)
    elif os.getuid() == 0:
        os.chown(path, arguments['runner_uid'] + 1, -1)
    else:
        arguments['runner_uid'] += 1
    before = unchanged_tree(tmp_path)
    with pytest.raises(pool.PoolError, match='INSTALL_EXISTING_DIRECTORY_UNSAFE'):
        pool.installation_plan(contract, template, **arguments)
    assert unchanged_tree(tmp_path) == before


def test_unknown_unit_is_rejected_before_package_extraction_or_unit_replacement(tmp_path):
    contract, template, arguments, member = install_fixture(tmp_path)
    fixture_file(tmp_path, '/etc/systemd/system/' + member['service'],
                 '[Service]\nUser=foreign-user\nExecStart=/bin/sh\n', os.getuid(), 0o644)
    before = unchanged_tree(tmp_path)
    with pytest.raises(pool.PoolError, match='INSTALL_UNKNOWN_SERVICE'):
        pool.installation_plan(contract, template, **arguments)
    assert unchanged_tree(tmp_path) == before


def test_unowned_local_registration_is_rejected_before_any_installer_mutation(tmp_path):
    contract, template, arguments, member = install_fixture(tmp_path)
    fixture_registration(tmp_path, contract, member, arguments['runner_uid'])
    before = unchanged_tree(tmp_path)
    with pytest.raises(pool.PoolError, match='INSTALL_UNOWNED_REGISTRATION'):
        pool.installation_plan(contract, template, **arguments)
    assert unchanged_tree(tmp_path) == before


def test_prepared_unregistered_owned_package_and_exact_inactive_unit_are_reused(tmp_path):
    contract, template, arguments, member = install_fixture(tmp_path)
    fixture_package(tmp_path, member, arguments['runner_uid'])
    unit_path = '/etc/systemd/system/' + member['service']
    fixture_file(tmp_path, unit_path, fixture_unit(contract, template, member), os.getuid(), 0o644)
    arguments['service_probe'] = lambda member: {'LoadState': 'loaded', 'ActiveState': 'inactive',
        'MainPID': '0', 'ControlPID': '0', 'FragmentPath': unit_path}
    before = unchanged_tree(tmp_path)
    plan = pool.installation_plan(contract, template, **arguments)
    assert plan['createParents'] == []
    assert plan['members']['primary'] == {'createDirectories': [], 'installPackage': False,
                                          'installUnit': False, 'retiring': False}
    assert unchanged_tree(tmp_path) == before


@pytest.mark.parametrize('complete', [True, False])
def test_bound_active_package_is_reused_or_blocked_before_repair(tmp_path, complete):
    contract, template, arguments, member = install_fixture(tmp_path)
    fixture_package(tmp_path, member, arguments['runner_uid'])
    fixture_registration(tmp_path, contract, member, arguments['runner_uid'])
    fixture_binding(tmp_path, contract)
    unit_path = '/etc/systemd/system/' + member['service']
    fixture_file(tmp_path, unit_path, fixture_unit(contract, template, member), os.getuid(), 0o644)
    arguments['service_probe'] = lambda member: {'LoadState': 'loaded', 'ActiveState': 'active',
        'MainPID': '50', 'ControlPID': '0', 'FragmentPath': unit_path}
    if not complete:
        (tmp_path / (member['root'] + '/config.sh').lstrip('/')).unlink()
    before = unchanged_tree(tmp_path)
    if complete:
        assert pool.installation_plan(contract, template, **arguments)['members']['primary']['installPackage'] is False
    else:
        with pytest.raises(pool.PoolError, match='INSTALL_ACTIVE_PACKAGE_UNPROVEN'):
            pool.installation_plan(contract, template, **arguments)
    assert unchanged_tree(tmp_path) == before


@pytest.mark.parametrize('missing', ['config.sh', 'run.sh'])
@pytest.mark.parametrize('active', [False, True])
def test_listener_present_partial_package_repairs_only_when_inactive(tmp_path, missing, active):
    import yaml
    contract, template, arguments, member = install_fixture(tmp_path)
    fixture_package(tmp_path, member, arguments['runner_uid'])
    fixture_registration(tmp_path, contract, member, arguments['runner_uid'])
    fixture_binding(tmp_path, contract)
    unit_path = '/etc/systemd/system/' + member['service']
    fixture_file(tmp_path, unit_path, fixture_unit(contract, template, member), os.getuid(), 0o644)
    arguments['service_probe'] = lambda member: {'LoadState': 'loaded',
        'ActiveState': 'active' if active else 'inactive', 'MainPID': '50' if active else '0',
        'ControlPID': '0', 'FragmentPath': unit_path}
    (tmp_path / (member['root'] + '/' + missing).lstrip('/')).unlink()
    assert (tmp_path / (member['root'] + '/bin/Runner.Listener').lstrip('/')).is_file()
    before = unchanged_tree(tmp_path)
    if active:
        with pytest.raises(pool.PoolError, match='INSTALL_ACTIVE_PACKAGE_UNPROVEN'):
            pool.installation_plan(contract, template, **arguments)
    else:
        plan = pool.installation_plan(contract, template, **arguments)
        assert plan['members']['primary']['installPackage'] is True
        tasks = yaml.safe_load((ROOT / 'deploy/ansible/tasks/managed-pool-member.yml').read_text())
        extraction = next(task for task in tasks if 'ansible.builtin.unarchive' in task)
        assert extraction['when'] == 'relay_pool_install_plan.members[relay_pool_member.id].installPackage'
        assert 'creates' not in extraction['ansible.builtin.unarchive']
        assert extraction['become_user'] == '{{ relay_general_runner_pool.runnerUser }}'
    assert unchanged_tree(tmp_path) == before


def test_known_protected_unit_can_receive_new_template_without_an_unbound_unit_bypass(tmp_path):
    contract, template, arguments, member = install_fixture(tmp_path)
    fixture_package(tmp_path, member, arguments['runner_uid'])
    unit_path = '/etc/systemd/system/' + member['service']
    old_unit = fixture_unit(contract, template, member) + '# older accepted template\n'
    fixture_file(tmp_path, unit_path, old_unit, os.getuid(), 0o644)
    arguments['service_probe'] = lambda member: {'LoadState': 'loaded', 'ActiveState': 'inactive',
        'MainPID': '0', 'ControlPID': '0', 'FragmentPath': unit_path}
    with pytest.raises(pool.PoolError, match='INSTALL_UNKNOWN_SERVICE'):
        pool.installation_plan(contract, template, **arguments)
    fixture_registration(tmp_path, contract, member, arguments['runner_uid'])
    fixture_binding(tmp_path, contract)
    plan = pool.installation_plan(contract, template, **arguments)
    assert plan['members']['primary']['installUnit'] is True
    assert plan['members']['primary']['installPackage'] is False


def test_ansible_preflight_precedes_first_mutation_and_creates_only_planned_missing_paths():
    import yaml
    tasks = yaml.safe_load((ROOT / 'deploy/ansible/tasks/managed-pool.yml').read_text())
    assert 'ansible.builtin.command' in tasks[0] and tasks[0]['changed_when'] is False
    parent_creation = next(task for task in tasks if 'ansible.builtin.file' in task)
    assert parent_creation['loop'] == '{{ relay_pool_install_plan.createParents }}'
    member_tasks = yaml.safe_load((ROOT / 'deploy/ansible/tasks/managed-pool-member.yml').read_text())
    creation = next(task for task in member_tasks if 'ansible.builtin.file' in task)
    extraction = next(task for task in member_tasks if 'ansible.builtin.unarchive' in task)
    assert creation['loop'] == '{{ relay_pool_install_plan.members[relay_pool_member.id].createDirectories }}'
    assert extraction['when'] == 'relay_pool_install_plan.members[relay_pool_member.id].installPackage'


@pytest.mark.parametrize('backend', ['tar', 'ansible'])
def test_native_extraction_preserves_private_member_root_and_next_installation_plan(tmp_path, backend):
    import io
    import stat
    import subprocess
    import tarfile
    import yaml

    contract, template, arguments, member = install_fixture(tmp_path)
    destination = tmp_path / member['root'].lstrip('/')
    before = destination.stat()
    assert stat.S_IMODE(before.st_mode) == 0o750
    archive = tmp_path / 'pinned-runner-fixture.tar'
    with tarfile.open(archive, 'w') as stream:
        # The published runner archive includes a root entry; extraction must
        # not replace our independently established private directory mode.
        for name, directory in [('.', True), ('bin', True), ('config.sh', False),
                                ('run.sh', False), ('bin/Runner.Listener', False)]:
            entry = tarfile.TarInfo(name)
            entry.uid, entry.gid, entry.mode = arguments['runner_uid'], before.st_gid, 0o755
            if name == '.':
                entry.uid += 1
                entry.gid += 1
            if directory:
                entry.type = tarfile.DIRTYPE
                stream.addfile(entry)
            else:
                data = b'synthetic pinned runner executable\n'
                entry.size = len(data)
                stream.addfile(entry, io.BytesIO(data))
    tasks = yaml.safe_load((ROOT / 'deploy/ansible/tasks/managed-pool-member.yml').read_text())
    task = next(value for value in tasks if 'ansible.builtin.unarchive' in value)
    extraction = task['ansible.builtin.unarchive']
    assert task['become_user'] == '{{ relay_general_runner_pool.runnerUser }}'
    assert 'owner' not in extraction and 'group' not in extraction
    if backend == 'tar':
        result = subprocess.run(['tar', '--extract', '--file', str(archive), '--directory', str(destination),
                                 *extraction['extra_opts']], capture_output=True, text=True)
    else:
        import shutil
        if shutil.which('ansible-playbook') is None:
            pytest.skip('native Ansible extraction qualification requires ansible-playbook')
        playbook = tmp_path / 'extract.yml'
        parameters = {**extraction, 'src': str(archive), 'dest': str(destination)}
        playbook.write_text(yaml.safe_dump([{'hosts': 'localhost', 'gather_facts': False,
            'tasks': [{'name': 'Extract only the disposable runner fixture', 'ansible.builtin.unarchive': parameters}]}]))
        home = tmp_path / 'ansible-home'
        home.mkdir(mode=0o700)
        result = subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local',
            '-e', 'ansible_python_interpreter=/usr/bin/python3', str(playbook)],
            env={**os.environ, 'HOME': str(home), 'ANSIBLE_LOCAL_TEMP': str(tmp_path / 'ansible-local'),
                 'ANSIBLE_REMOTE_TEMP': str(tmp_path / 'ansible-remote'), 'PYTHONDONTWRITEBYTECODE': '1'},
            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    after = destination.stat()
    assert (after.st_uid, after.st_gid, stat.S_IMODE(after.st_mode)) == (
        before.st_uid, before.st_gid, 0o750)
    assert (destination / 'bin/Runner.Listener').stat().st_uid == arguments['runner_uid']
    plan = pool.installation_plan(contract, template, **arguments)
    assert plan['members']['primary']['createDirectories'] == []
    assert plan['members']['primary']['installPackage'] is False
