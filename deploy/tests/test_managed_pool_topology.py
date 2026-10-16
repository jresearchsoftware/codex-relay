"""Shared identity compatibility and concrete functional/protected access."""
import copy
from pathlib import Path
import stat
import sys
from types import SimpleNamespace

import pytest
import yaml
from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
import execution_topology as topology
from test_managed_pool import inputs


def tables():
    config = inputs()
    environment = config['environment']
    protected = [environment[key] for key in ['serviceUser', 'reviewerUser']]
    protected.append(environment['runner']['user'])
    runner, runtime = (config['consumer']['executionSlots'][0][key]
                       for key in ['runnerUser', 'runtimeUser'])
    users = [SimpleNamespace(pw_name=name, pw_uid=1000 + index, pw_gid=2000 + index,
                             pw_dir='/existing/home/' + name, pw_shell='/bin/bash')
             for index, name in enumerate([*protected, runner, runtime])]
    groups = [SimpleNamespace(gr_name=user.pw_name, gr_gid=user.pw_gid, gr_mem=[])
              for user in users]
    users[-1].pw_gid = 6001
    users[-2].pw_gid = 6002
    groups.extend([SimpleNamespace(gr_name='existing-primary-runtime', gr_gid=6001, gr_mem=[]),
                   SimpleNamespace(gr_name='existing-primary-runner', gr_gid=6002, gr_mem=[]),
                   SimpleNamespace(gr_name='existing-other-membership', gr_gid=6003, gr_mem=[runner, runtime]),
                   SimpleNamespace(gr_name=environment['codexWorkGroup'], gr_gid=6004, gr_mem=[runner, runtime])])
    return config, users, groups


def access_fixture(config):
    allowed = set()
    for slot in config['consumer']['executionSlots']:
        journal = str(Path(slot['paths']['attemptRoot']).parent)
        for user, paths in [(slot['runnerUser'], [slot['paths']['workRoot'], journal]),
                            (slot['runtimeUser'], [slot['paths']['workRoot']])]:
            allowed.update((user, flag, path) for flag in ['-w', '-x'] for path in paths)
        allowed.add((slot['runnerUser'], '-x', slot['paths']['dispatch']))
        allowed.add((slot['runtimeUser'], '-x', slot['paths']['launcher']))
    return allowed


def test_shared_accounts_keep_existing_primary_groups_home_shell_and_other_memberships():
    config, users, groups = tables()
    before = copy.deepcopy((users, groups))
    assert topology.numeric_preflight(config, users, groups)['numericIdentity'] == 'shared-pool'
    resolved, _ = topology.identities(config, users, groups)
    assert len(config['consumer']['executionSlots']) == 32
    assert len({slot['runtimeUser'] for slot in config['consumer']['executionSlots']}) == 1
    assert len(resolved) == len(users)
    assert (users, groups) == before


def test_installed_private_root_metadata_uses_managed_groups_without_changing_existing_primary_gid(monkeypatch):
    config, users, groups = tables()
    user = {entry.pw_name: entry for entry in users}
    group = {entry.gr_name: entry for entry in groups}
    metadata = {}
    base = Path('/fixture')
    namespace = config['environment']['namespace']
    for slot in config['consumer']['executionSlots']:
        credential = '/etc/' + namespace + ('' if slot['id'] == 'primary' else '/slots/' + slot['id']) + '/codex-credentials'
        entries = [
            (slot['paths']['workRoot'], user[slot['runnerUser']].pw_uid, group[slot['workGroup']].gr_gid, 0o2770),
            (str(Path(slot['paths']['attemptRoot']).parent), user[slot['runnerUser']].pw_uid,
             group[slot['runnerUser']].gr_gid, 0o700),
            (credential, user[slot['runtimeUser']].pw_uid, group[slot['runtimeUser']].gr_gid, 0o700),
            (slot['paths']['diagnosticsRoot'], 0, 0, 0o700),
        ]
        for path, uid, gid, mode in entries:
            metadata[base / path.lstrip('/')] = SimpleNamespace(st_mode=stat.S_IFDIR | mode, st_uid=uid, st_gid=gid)
    monkeypatch.setattr(Path, 'lstat', lambda path: metadata.get(path,
        SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_uid=0, st_gid=0)))
    allowed = access_fixture(config)
    result = topology.inspect(config, root=base, accounts=users, groups=groups, acl_reader=lambda path: '',
        access_probe=lambda user, flag, path: (user, flag, path) in allowed, sudo_probe=lambda user, argv: False)
    assert result == {'slots': 32, 'numericIdentity': 'shared-pool', 'access': 'isolated'}


@pytest.mark.parametrize('identity', ['runtime', 'runner', 'protected'])
def test_shared_pool_retains_nonroot_and_protected_uid_separation(identity):
    config, users, groups = tables()
    if identity == 'runtime':
        users[-1].pw_uid = 0
    elif identity == 'runner':
        users[-2].pw_uid = users[-1].pw_uid
    else:
        users[-1].pw_uid = users[0].pw_uid
    with pytest.raises(ValueError, match='ROOT_IDENTITY|UID_ALIAS'):
        topology.identities(config, users, groups)


def test_functional_access_checks_cover_all_retained_slots_without_opening_credentials_or_running_sudo():
    config, _, _ = tables()
    allowed = access_fixture(config)
    observed = set()
    sudo = []

    def probe(user, flag, path):
        assert flag in ['-r', '-w', '-x']
        observed.add((user, flag, path))
        return (user, flag, path) in allowed

    def sudo_probe(user, argv):
        sudo.append((user, argv))
        return False

    result = topology.pool_access(config, probe=probe, sudo_probe=sudo_probe)
    assert result == {'functionalAccess': 'verified', 'protectedAccess': 'denied'}
    assert allowed <= observed
    assert len(sudo) == 6
    assert all(user == config['environment']['generalRunner']['user'] for user, _ in sudo)
    assert any(argv[-1] == '0' * 40 for _, argv in sudo)


@pytest.mark.parametrize('boundary', ['writer-read', 'reviewer-write', 'runtime-journal', 'missing-work', 'root-shell'])
def test_shared_account_configuration_cannot_hide_concrete_boundary_failures(boundary):
    config, _, _ = tables()
    allowed = access_fixture(config)
    slot = config['consumer']['executionSlots'][0]
    runner, runtime = slot['runnerUser'], slot['runtimeUser']
    namespace = config['environment']['namespace']
    mutation = {
        'writer-read': (runtime, '-r', config['consumer']['paths']['credentialKeyFile']),
        'reviewer-write': (runner, '-w', '/etc/' + namespace + '/reviewer-credentials'),
        'runtime-journal': (runtime, '-x', str(Path(slot['paths']['attemptRoot']).parent)),
        'missing-work': (runtime, '-w', slot['paths']['workRoot']),
    }.get(boundary)

    def probe(user, flag, path):
        key = (user, flag, path)
        return not (key in allowed) if key == mutation else key in allowed

    with pytest.raises(ValueError, match='PROTECTED_ACCESS|FUNCTIONAL_ACCESS_MISSING|PROTECTED_SUDO_BYPASS'):
        topology.pool_access(config, probe=probe,
            sudo_probe=lambda user, argv: boundary == 'root-shell' and argv == ['/bin/sh'])


@pytest.mark.parametrize('role,name,prefix,existing', [
    ('relay_codex_runtime', 'Create the non-login Codex execution identity', 'codex', 'relay_codex_existing_account'),
    ('relay_base', 'Create the separate generic dispatch identity before runtime installation', 'dispatch', 'relay_base_existing_dispatch'),
    ('relay_runner', 'Create the isolated general runner identity with only Codex work membership', 'runner', 'relay_general_existing_account'),
])
def test_account_tasks_preserve_existing_pool_settings_and_still_initialize_new_accounts(role, name, prefix, existing):
    filename = 'general-runtime.yml' if role == 'relay_runner' else 'main.yml'
    tasks = yaml.safe_load((ROOT / 'deploy/ansible/roles' / role / 'tasks' / filename).read_text())
    task = next(task['ansible.builtin.user'] for task in tasks if task['name'] == name)
    values = {'omit': '__omitted__', 'relay_general_runner_pool': {}, 'relay_state_root': '/var/lib/sample',
              'relay_codex_work_group': 'sample-work', 'relay_' + prefix + '_user': 'sample-existing',
              'relay_' + prefix + '_group': 'sample-private', 'relay_' + prefix + '_home': '/var/lib/sample/new-home',
              existing: {'ansible_facts': {'getent_passwd': {'sample-existing': ['x', '1010', '6060', '', '/home/current', '/bin/bash']}}}}
    rendered = Templar(loader=DataLoader(), variables=values).template(task)
    assert {rendered[key] for key in ['group', 'home', 'shell']} == {'__omitted__'}
    if role == 'relay_runner':
        assert rendered['append'] is True
    values[existing]['ansible_facts']['getent_passwd'] = {'sample-existing': None}
    rendered = Templar(loader=DataLoader(), variables=values).template(task)
    assert rendered['group'] == 'sample-private'
    assert rendered['shell'] == '/usr/sbin/nologin'
    assert rendered['home'].startswith('/var/lib/sample/')
    values.pop('relay_general_runner_pool')
    values[existing]['ansible_facts']['getent_passwd']['sample-existing'] = ['existing']
    rendered = Templar(loader=DataLoader(), variables=values).template(task)
    assert rendered['group'] == 'sample-private'
    assert rendered['shell'] == '/usr/sbin/nologin'
