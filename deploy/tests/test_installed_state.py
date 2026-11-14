"""Desired bytes come from task owners, never a snapshot of observed files."""
import base64
import copy
import json
import os
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
import config
import installed_state as state

SOURCE = Path(__file__).parents[2]


@pytest.fixture(scope='module')
def catalogue():
    values = config.compile_inputs(json.loads((SOURCE / 'deploy/example.json').read_text()))
    values.update(relay_deployment_profile='production', relay_release_commit='a' * 40,
                  relay_release_sha256='b' * 64, relay_release_path='/opt/relay-test/releases/' + 'a' * 40,
                  relay_controller_source_tree_sha256='c' * 64,
                  relay_codex_launcher_source_tree_sha256='d' * 64, relay_consumer_revision='e' * 40)
    values['relay_github_repositories'] = values['relay_writer_repositories']
    return state.build_catalogue(SOURCE, values)


def test_actual_owned_templates_expand_all_fixed_routes(catalogue):
    assert catalogue['coverage']['routeCount'] == len(catalogue['probes']) == 32
    assert len({probe['label'] for probe in catalogue['probes']}) == 32
    assert len(catalogue['entries']) > 700
    for entry in catalogue['entries']:
        if 'contentBase64' in entry:
            raw = base64.b64decode(entry['contentBase64'])
            assert state.hashlib.sha256(raw).hexdigest() == entry['sha256']
    owners = catalogue['coverage']['owners']
    assert any('Create root-owned slot namespace parents' in owner for owner in owners)
    assert any('Reconcile only fixed repository work ancestor metadata' in owner for owner in owners)
    assert all(probe['argv'][0:2] == ['/usr/sbin/runuser', '-u'] and '/usr/bin/bwrap' in probe['argv']
               for probe in catalogue['probes'])


def test_render_uses_canonical_ansible_filters_and_trailing_newline():
    assert state.render('{{ value | to_nice_json }}\n', {'value': {'canonical': True}}) == '{\n    "canonical": true\n}\n'
    with pytest.raises(state.NotEligible):
        state.render('{{ missing }}', {})


def test_catalogued_bytes_match_real_ansible_template_action(tmp_path, catalogue):
    import subprocess
    import yaml
    raw = yaml.safe_load((SOURCE / 'deploy/ansible/group_vars/all.yml').read_text())
    values = config.compile_inputs(json.loads((SOURCE / 'deploy/example.json').read_text()))
    values.update(relay_deployment_profile='production', relay_release_commit='a' * 40,
                  relay_release_sha256='b' * 64, relay_release_path='/opt/relay-test/releases/' + 'a' * 40,
                  relay_controller_source_tree_sha256='c' * 64,
                  relay_codex_launcher_source_tree_sha256='d' * 64, relay_consumer_revision='e' * 40)
    destination = tmp_path / 'rendered.env'
    json_destination = tmp_path / 'rendered.json'
    play = [{'hosts': 'localhost', 'gather_facts': False, 'vars': {**raw, **values},
             'tasks': [{'ansible.builtin.template': {
                 'src': str(SOURCE / 'deploy/ansible/roles/relay_runtime/templates/relay.env.j2'),
                 'dest': str(destination), 'mode': '0600'}},
                       {'ansible.builtin.template': {
                           'src': str(SOURCE / 'deploy/ansible/roles/relay_runtime/templates/reviewer-mcp.json.j2'),
                           'dest': str(json_destination), 'mode': '0600'}}]}]
    playbook = tmp_path / 'canonical-render.yml'; playbook.write_text(yaml.safe_dump(play))
    result = subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(playbook)],
                            capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr.decode()
    expected = next(row for row in catalogue['entries'] if row['path'].endswith('/relay.env'))
    assert destination.read_bytes() == base64.b64decode(expected['contentBase64'])
    expected_json = next(row for row in catalogue['entries'] if row['path'].endswith('/reviewer-mcp.json'))
    # This catches native-JSON auto-conversion: str(dict) is not template bytes.
    assert json_destination.read_bytes() == base64.b64decode(expected_json['contentBase64'])
    json.loads(json_destination.read_bytes())


def test_new_unhandled_recipe_refuses_before_catalogue(tmp_path):
    root = tmp_path / 'source'
    (root / 'deploy/ansible').mkdir(parents=True)
    (root / 'deploy/ansible/new.yml').write_text('- ansible.builtin.command: unexpected\n')
    with pytest.raises(state.NotEligible, match='INSTALLED_RECIPE_NOT_SUPPORTED'):
        state.build_catalogue(root, {})


def test_new_mutating_owner_in_existing_task_file_cannot_escape_coverage(tmp_path):
    root = tmp_path / 'source'
    shutil.copytree(SOURCE / 'deploy/ansible', root / 'deploy/ansible',
                    ignore=shutil.ignore_patterns('tests', '__pycache__'))
    task = root / 'deploy/ansible/roles/relay_runtime/tasks/main.yml'
    task.write_text(task.read_text() + '\n- name: Unhandled managed mutation\n  ansible.builtin.copy:\n'
                    '    dest: /etc/unhandled\n    content: unqualified\n')
    with pytest.raises(state.NotEligible, match='INSTALLED_RECIPE_NOT_SUPPORTED'):
        state.build_catalogue(root, {})


@pytest.mark.parametrize('change', ['profile', 'routes', 'managed-ingress', 'extra-runtime'])
def test_unsupported_active_profile_refuses_before_proof(change):
    values = config.compile_inputs(json.loads((SOURCE / 'deploy/example.json').read_text()))
    values['relay_deployment_profile'] = 'production'
    if change == 'profile': values['relay_deployment_profile'] = 'qualification'
    elif change == 'routes': values['relay_additional_execution_slots'].pop()
    elif change == 'managed-ingress': values['relay_nginx_manage'] = True
    else: values['relay_additional_runtime_users'] = ['unsupported-additional-user']
    with pytest.raises(state.NotEligible, match='INSTALLED_PROFILE_NOT_SUPPORTED'):
        state.build_catalogue(SOURCE, values)


@pytest.mark.parametrize('publication', [False, True])
def test_both_publication_policies_keep_the_same_fixed_route_coverage(publication):
    values = config.compile_inputs(json.loads((SOURCE / 'deploy/example.json').read_text()))
    values.update(relay_deployment_profile='production', relay_release_commit='a' * 40,
                  relay_release_sha256='b' * 64, relay_release_path='/opt/relay-test/releases/' + 'a' * 40,
                  relay_controller_source_tree_sha256='c' * 64,
                  relay_codex_launcher_source_tree_sha256='d' * 64, relay_consumer_revision='e' * 40,
                  relay_reviewer_relay_enabled=publication)
    catalogue = state.build_catalogue(SOURCE, values)
    assert catalogue['coverage']['routeCount'] == 32
    entry = next(row for row in catalogue['entries'] if row['path'].endswith('/relay.env'))
    assert ('REVIEWER_RELAY_ENABLED=' + str(publication).lower()) in base64.b64decode(entry['contentBase64']).decode()


@pytest.fixture
def installed(tmp_path, catalogue):
    if sys.platform != 'linux' or os.geteuid() != 0:
        pytest.skip('root Linux metadata proof required')
    root = tmp_path / 'target'; root.mkdir()
    names = {entry['owner'] for entry in catalogue['entries'] if entry['kind'] != 'absent'}
    groups = {entry['group'] for entry in catalogue['entries'] if entry['kind'] != 'absent'}
    for account in catalogue['identities']:
        names.add(account['name'])
        groups.update(account['requiredGroups'] + account['forbiddenGroups'])
        if 'primaryGroup' in account: groups.add(account['primaryGroup'])
    group_ids = {name: index for index, name in enumerate(sorted(groups - {'root'}), 2000)}
    group_ids['root'] = 0
    users = {name: {'uid': index, 'gid': group_ids.get(name, 3000), 'shell': '/usr/sbin/nologin',
                    'groups': []} for index, name in enumerate(sorted(names - {'root'}), 4000)}
    users['root'] = {'uid': 0, 'gid': 0, 'groups': [0]}
    for account in catalogue['identities']:
        row = users[account['name']]
        if 'primaryGroup' in account: row['gid'] = group_ids[account['primaryGroup']]
        row['groups'] = [row['gid']] + [group_ids[group] for group in account['requiredGroups']]
    for entry in sorted(catalogue['entries'], key=lambda value: len(Path(value['path']).parts)):
        path = root / entry['path'].lstrip('/')
        path.parent.mkdir(parents=True, exist_ok=True)
        if entry['kind'] == 'absent': continue
        if entry['kind'] == 'directory': path.mkdir(exist_ok=True)
        elif entry['kind'] == 'link': path.symlink_to(entry['target'])
        else: path.write_bytes(base64.b64decode(entry['contentBase64']))
        os.chown(path, users[entry['owner']]['uid'], group_ids[entry['group']], follow_symlinks=False)
        if not path.is_symlink(): path.chmod(entry['mode'])
    live = {key: True for key in catalogue['requiredLiveChecks']}
    calls = []
    def execute(argv):
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout=b'')
    kwargs = {'root': root, 'users': users, 'groups': group_ids, 'execute': execute, 'live_checks': live}
    return root, kwargs, calls


def test_actual_catalogue_audit_checks_every_route_without_mutation(catalogue, installed):
    root, kwargs, calls = installed
    before = {str(path): path.lstat().st_ctime_ns for path in root.rglob('*')}
    proof = state.audit_catalogue(catalogue, **kwargs)
    assert proof['eligible'] and proof['routeCount'] == len(calls) == 32
    assert before == {str(path): path.lstat().st_ctime_ns for path in root.rglob('*')}


def test_consumer_publication_serialization_can_differ_but_not_any_effective_field(catalogue, installed):
    root, kwargs, _ = installed
    entry = next(row for row in catalogue['entries'] if row.get('contentKind') == 'consumer-json')
    path = root / entry['path'].lstrip('/')
    desired = json.loads(base64.b64decode(entry['contentBase64']))
    path.write_text(json.dumps(desired, sort_keys=True, separators=(',', ':')) + '\n')
    assert state.audit_catalogue(catalogue, **kwargs)['eligible']
    desired['version'] = True  # Python dict equality would conflate True and 1.
    path.write_text(json.dumps(desired))
    with pytest.raises(state.NotEligible, match='INSTALLED_CONTENT_DRIFT'):
        state.audit_catalogue(catalogue, **kwargs)


def test_duplicate_consumer_fields_are_not_equivalent(catalogue, installed):
    root, kwargs, _ = installed
    entry = next(row for row in catalogue['entries'] if row.get('contentKind') == 'consumer-json')
    path = root / entry['path'].lstrip('/')
    text = base64.b64decode(entry['contentBase64']).decode()
    path.write_text(text.replace('"version": 1', '"version": 9, "version": 1', 1))
    with pytest.raises(state.NotEligible, match='INSTALLED_CONTENT_DRIFT'):
        state.audit_catalogue(catalogue, **kwargs)


@pytest.mark.parametrize('encoding', ['utf-16', 'utf-8-sig'])
def test_consumer_bytes_must_be_native_utf8_json(catalogue, installed, encoding):
    root, kwargs, _ = installed
    entry = next(row for row in catalogue['entries'] if row.get('contentKind') == 'consumer-json')
    path = root / entry['path'].lstrip('/')
    path.write_bytes(base64.b64decode(entry['contentBase64']).decode().encode(encoding))
    with pytest.raises(state.NotEligible):
        state.audit_catalogue(catalogue, **kwargs)


@pytest.mark.parametrize('change', ['bytes', 'mode', 'owner', 'hardlink', 'symlink', 'absent', 'membership', 'root-user'])
def test_single_installed_drift_refuses_optimization(catalogue, installed, change):
    root, kwargs, _ = installed
    entry = next(row for row in catalogue['entries'] if row['kind'] == 'file')
    path = root / entry['path'].lstrip('/')
    if change == 'bytes': path.write_bytes(b'not the canonical source-owned bytes')
    elif change == 'mode': path.chmod(0o777)
    elif change == 'owner': os.chown(path, 9999, 9999)
    elif change == 'hardlink': os.link(path, root / 'unexpected-link')
    elif change == 'symlink':
        path.unlink(); path.symlink_to(root / 'outside')
    elif change == 'absent':
        absent = next(row for row in catalogue['entries'] if row['kind'] == 'absent')
        (root / absent['path'].lstrip('/')).write_bytes(b'unexpected historical service')
    else:
        account = next(row for row in catalogue['identities'] if row['requiredGroups'])
        kwargs['users'][account['name']]['uid' if change == 'root-user' else 'groups'] = 0 if change == 'root-user' else []
    with pytest.raises(state.NotEligible):
        state.audit_catalogue(catalogue, **kwargs)


def test_all_live_obligations_and_every_native_route_are_mandatory(catalogue, installed):
    _, kwargs, _ = installed
    for field in catalogue['requiredLiveChecks']:
        with pytest.raises(state.NotEligible, match='INSTALLED_LIVE_CHECK_UNPROVEN'):
            state.audit_catalogue(catalogue, **{**kwargs, 'live_checks': {**kwargs['live_checks'], field: False}})
    for rejected in range(32):
        count = [0]
        def execute(argv):
            index = count[0]; count[0] += 1
            return SimpleNamespace(returncode=int(index == rejected), stdout=b'')
        with pytest.raises(state.NotEligible, match='INSTALLED_NATIVE_PROBE_FAILED'):
            state.audit_catalogue(catalogue, **{**kwargs, 'execute': execute})


def test_movement_during_native_probe_refuses(catalogue, installed):
    root, kwargs, _ = installed
    entry = next(row for row in catalogue['entries'] if row['kind'] == 'file')
    def execute(argv):
        (root / entry['path'].lstrip('/')).write_bytes(b'changed during namespace checks')
        return SimpleNamespace(returncode=0, stdout=b'')
    with pytest.raises(state.NotEligible, match='INSTALLED_STATE_MOVED'):
        state.audit_catalogue(catalogue, **{**kwargs, 'execute': execute})


@pytest.mark.parametrize('change,field', [('mode', 'mode'), ('bytes', 'content'), ('missing', 'type'), ('probe', 'nativeProbe')])
def test_drift_diagnostics_expose_only_source_owner_field_and_index(catalogue, installed, change, field):
    root, kwargs, _ = installed
    index, entry = next((index, row) for index, row in enumerate(catalogue['entries']) if row['kind'] == 'file')
    path = root / entry['path'].lstrip('/')
    if change == 'mode': path.chmod(0o777)
    elif change == 'bytes': path.write_bytes(b'PRIVATE-CONTENT-CANARY-DO-NOT-EMIT')
    elif change == 'missing': path.unlink()
    else: kwargs['execute'] = lambda argv: SimpleNamespace(returncode=1, stdout=b'PRIVATE-PROBE-CANARY')
    with pytest.raises(state.NotEligible) as caught:
        state.audit_catalogue(catalogue, **kwargs)
    error = caught.value
    assert error.field == field and isinstance(error.index, int)
    if change == 'probe':
        assert error.index == 0 and error.owner.startswith('tasks/execution-slot.yml:')
    else:
        assert error.index == index and error.owner == catalogue['entryOwners'][index]
    report = json.dumps({'code': str(error), 'owner': error.owner, 'field': error.field, 'index': error.index})
    assert str(path) not in report and entry['path'] not in report and 'PRIVATE-' not in report
