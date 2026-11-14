"""General preservation does not adopt Production cached startup semantics."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
import process_adoption as adoption
import source_upgrade_general as general

SOURCE = Path(__file__).parents[2]


@pytest.fixture
def component(tmp_path, monkeypatch):
    root = tmp_path / 'runner'; root.mkdir(mode=0o750)
    for name in ['bin', 'externals']:
        (root / name).mkdir(mode=0o750)
        (root / name / 'native-input').write_bytes(b'current native distribution')
    for name in ['run.sh', 'run-helper.sh', 'run-helper.sh.template', '.runner', '.credentials']:
        (root / name).write_bytes(b'current protected root input')
    (root / '_diag').mkdir()
    (root / '_diag/live-log').write_bytes(b'mutable diagnostics')
    unit = tmp_path / 'general.service'; unit.write_bytes(b'current root-owned unit')
    environment = tmp_path / 'relay.env'; environment.write_bytes(b'PUBLIC_CONTRACT=current\n')
    state = {'User': 'synthetic-general', 'MainPID': '111', 'ControlGroup': '/system.slice/general.service',
             'FragmentPath': str(unit), 'DropInPaths': '',
             'EnvironmentFiles': str(environment) + ' (ignore_errors=no)'}
    runner = {'label': 'member-runner-01', 'root': str(root), 'user': 'synthetic-general', 'service': 'general.service'}
    process = {'pid': '111', 'uid': os.getuid(), 'start': '123', 'command': 'unchanged',
               'environment': 'unchanged', 'executable': 'unchanged', 'maps': {'native': 'unchanged'}}
    monkeypatch.setattr(general.pwd, 'getpwnam', lambda name: SimpleNamespace(pw_uid=65534))
    monkeypatch.setattr(adoption, 'service', lambda name: copy.deepcopy(state))
    def typed_property(argv, **kwargs):
        value = {'type': 'o', 'data': ['/org/freedesktop/systemd1/unit/general_2eservice']} if 'call' in argv else {
            'type': 'a(sb)', 'data': [[str(environment), False]]}
        return SimpleNamespace(stdout=json.dumps(value).encode())
    monkeypatch.setattr(general.subprocess, 'run', typed_property)
    monkeypatch.setattr(adoption, 'cgroup_members', lambda path: ['111'])
    monkeypatch.setattr(general, '_process', lambda pid, uid, **kwargs: copy.deepcopy(process))
    monkeypatch.setattr(general, '_trust', lambda processes, uid, **kwargs: {'currentTrust': True})
    return root, unit, environment, runner, state, process


def test_post_start_general_root_and_files_are_valid_current_component(component):
    root, _, _, runner, _, _ = component
    # Actual current ctime is later than this retained startup. Production must
    # still refuse adopting it as a previously consumed immutable startup tree.
    with pytest.raises(ValueError):
        adoption.distribution_directory(root, time.time() - 10, 65534)
    proof = general.capture_general(runner, SOURCE)
    assert proof['root']['identity'] == adoption.identity(root.stat())
    assert proof['files'][str(root / 'run-helper.sh')]['sha256']


def test_production_cannot_select_the_general_component_proof(component):
    _, _, _, runner, _, _ = component
    with pytest.raises(ValueError):
        general.capture_general({**runner, 'label': 'production'}, SOURCE)


@pytest.mark.parametrize('case', ['empty', 'missing', 'wrong-type', 'malformed', 'failure', 'changed', 'bool-type', 'wrapper'])
def test_empty_environment_file_list_requires_explicit_native_property(monkeypatch, case):
    monkeypatch.setattr(adoption, 'service', lambda name: {'MainPID': '111'})
    replies = {'empty': {'type': 'a(sb)', 'data': []}, 'missing': {},
               'wrong-type': {'type': 'as', 'data': []}, 'malformed': {'type': 'a(sb)', 'data': [['relative.env', False]]},
               'changed': {'type': 'a(sb)', 'data': [['/etc/changed.env', False]]},
               'bool-type': {'type': 'a(sb)', 'data': [['/etc/file.env', 'false']]},
               'wrapper': {'type': 'a(sb)', 'data': [[]]}}
    def execute(argv, **kwargs):
        assert argv[:4] == ['/bin/busctl', '--system', '--json=short', '--timeout=5s']
        if case == 'failure': raise subprocess.CalledProcessError(1, argv)
        result = {'type': 'o', 'data': ['/org/freedesktop/systemd1/unit/general_2eservice']} if 'call' in argv else replies[case]
        return SimpleNamespace(stdout=json.dumps(result).encode())
    monkeypatch.setattr(general.subprocess, 'run', execute)
    if case == 'empty':
        assert general._service('general.service')['EnvironmentFiles'] == ''
    elif case == 'changed':
        before = general._service('general.service')
        replies['changed'] = {'type': 'a(sb)', 'data': [['/etc/new.env', False]]}
        assert general._service('general.service') != before
    else:
        with pytest.raises((ValueError, subprocess.SubprocessError)):
            general._service('general.service')


def test_disagreement_between_service_and_explicit_environment_query_refuses(monkeypatch):
    monkeypatch.setattr(adoption, 'service', lambda name: {'EnvironmentFiles': '/etc/old.env (ignore_errors=no)'})
    monkeypatch.setattr(general.subprocess, 'run', lambda argv, **kwargs: SimpleNamespace(stdout=json.dumps(
        {'type': 'o', 'data': ['/org/freedesktop/systemd1/unit/general_2eservice']} if 'call' in argv
        else {'type': 'a(sb)', 'data': []}).encode()))
    with pytest.raises(ValueError):
        general._service('general.service')


def test_loaded_environment_property_movement_during_snapshot_is_refused(component, monkeypatch):
    _, _, _, runner, state, _ = component
    state.pop('EnvironmentFiles')
    calls = [0]
    def query(argv, **kwargs):
        if 'call' in argv:
            result = {'type': 'o', 'data': ['/org/freedesktop/systemd1/unit/general_2eservice']}
        else:
            calls[0] += 1
            result = {'type': 'a(sb)', 'data': [] if calls[0] == 1 else [['/etc/changed.env', False]]}
        return SimpleNamespace(stdout=json.dumps(result).encode())
    monkeypatch.setattr(general.subprocess, 'run', query)
    with pytest.raises(ValueError):
        general.capture_general(runner, SOURCE)


@pytest.mark.parametrize('change', ['distribution', 'root-file', 'optional-setting', 'unit', 'environment', 'process', 'members'])
def test_component_changes_between_phases_cannot_match_original_proof(component, monkeypatch, change):
    root, unit, environment, runner, state, process = component
    before = general.capture_general(runner, SOURCE)
    if change == 'distribution': (root / 'bin/native-input').write_bytes(b'changed native software')
    elif change == 'root-file': (root / 'run-helper.sh').write_bytes(b'changed interpreted startup code')
    elif change == 'optional-setting': (root / '.runner_migrated').write_bytes(b'new optional cached setting')
    elif change == 'unit': unit.write_bytes(b'changed unit')
    elif change == 'environment': environment.write_bytes(b'changed service environment')
    elif change == 'process': process['start'] = '999'
    else: monkeypatch.setattr(adoption, 'cgroup_members', lambda path: ['111', '222'])
    assert general.capture_general(runner, SOURCE) != before


def test_only_mutable_diagnostic_contents_are_excluded(component):
    root, _, _, runner, _, _ = component
    before = general.capture_general(runner, SOURCE)
    (root / '_diag/live-log').write_bytes(b'new ordinary runtime diagnostic bytes')
    assert general.capture_general(runner, SOURCE) == before


@pytest.mark.parametrize('damage', ['write-mode', 'hardlink', 'root-file-alias', 'distribution-escape'])
def test_unsafe_current_inputs_are_refused_without_start_history(component, damage):
    root, _, _, runner, _, _ = component
    if damage == 'write-mode': (root / 'bin/native-input').chmod(0o666)
    elif damage == 'hardlink': os.link(root / 'bin/native-input', root / 'unexpected-alias')
    elif damage == 'root-file-alias':
        (root / '.credentials').unlink(); (root / '.credentials').symlink_to(root / '.runner')
    else: (root / 'externals/escape').symlink_to('/etc/passwd')
    with pytest.raises(ValueError):
        general.capture_general(runner, SOURCE)


def test_child_replacement_with_stable_main_pid_during_scan_is_refused(component, monkeypatch):
    _, _, _, runner, _, _ = component
    count = [0]
    def members(path):
        count[0] += 1
        return ['111'] if count[0] == 1 else ['111', '222']
    monkeypatch.setattr(adoption, 'cgroup_members', members)
    with pytest.raises(ValueError):
        general.capture_general(runner, SOURCE)


@pytest.mark.parametrize('change', ['unit', 'environment', 'distribution', 'root-file', 'create-delete-setting', 'trust'])
def test_current_input_movement_during_long_scan_is_refused(component, monkeypatch, change):
    root, unit, environment, runner, _, _ = component
    calls = [0]
    def trust(processes, uid, **kwargs):
        calls[0] += 1
        if calls[0] == 1:
            if change == 'unit': unit.write_bytes(b'new loaded-unit disk input')
            elif change == 'environment': environment.write_bytes(b'new environment disk input')
            elif change == 'distribution': (root / 'bin/native-input').write_bytes(b'changed library')
            elif change == 'root-file': (root / 'run-helper.sh').write_bytes(b'changed interpreted code')
            elif change == 'create-delete-setting':
                (root / '.runner_migrated').write_bytes(b'transient optional setting')
                (root / '.runner_migrated').unlink()
        return {'trustVersion': calls[0] if change == 'trust' else 1}
    monkeypatch.setattr(general, '_trust', trust)
    with pytest.raises(ValueError):
        general.capture_general(runner, SOURCE)


def test_current_native_npm_alias_remains_contained_and_snapshot_bound(component):
    root, _, _, runner, _, _ = component
    node = root / 'externals/node/bin'; node.mkdir(parents=True)
    library = root / 'externals/node/lib'; library.mkdir()
    (library / 'npm-cli.js').write_bytes(b'current official npm entrypoint')
    (node / 'npm').symlink_to('../lib/npm-cli.js')
    proof = general.capture_general(runner, SOURCE)
    assert proof['distribution']['externals'][str(node / 'npm')]['link'] == '../lib/npm-cli.js'


def test_current_mapped_inode_binding_is_not_pathname_only(tmp_path):
    path = tmp_path / 'mapped-current-library'; path.write_bytes(b'current mapped bytes')
    meta = path.stat()
    device = f'{os.major(meta.st_dev):x}:{os.minor(meta.st_dev):x}'
    assert general._file(path, os.getuid(), device=device, inode=str(meta.st_ino))['sha256']
    with pytest.raises(ValueError):
        general._file(path, os.getuid(), device=device, inode=str(meta.st_ino + 1))


def test_verified_bytes_are_hashed_once_but_each_use_opens_fresh_metadata(tmp_path, monkeypatch):
    path = tmp_path / 'immutable-library'; path.write_bytes(b'actual independently hashed bytes')
    original_open, original_digest = general.os.open, general.hashlib.file_digest
    meta = path.stat()
    counts = {'opens': 0, 'hashes': 0}
    def opening(selected, *args, **kwargs):
        if str(selected) == str(path): counts['opens'] += 1
        return original_open(selected, *args, **kwargs)
    def hashing(stream, algorithm):
        current = os.fstat(stream.fileno())
        if (current.st_dev, current.st_ino) == (meta.st_dev, meta.st_ino): counts['hashes'] += 1
        return original_digest(stream, algorithm)
    monkeypatch.setattr(general.os, 'open', opening)
    monkeypatch.setattr(general.hashlib, 'file_digest', hashing)
    verified = {}
    first = general._file(path, os.getuid(), verified=verified)
    assert general._file(path, os.getuid(), verified=verified) == first
    assert general._file(path, os.getuid(), verified=verified) == first
    assert counts == {'opens': 3, 'hashes': 1}
    device = f'{os.major(meta.st_dev):x}:{os.minor(meta.st_dev):x}'
    with pytest.raises(ValueError):
        general._file(path, os.getuid(), device=device, inode=str(meta.st_ino + 1), verified=verified)


@pytest.mark.parametrize('change', ['chmod', 'overwrite-restored-mtime', 'recreate', 'alias'])
def test_changed_identity_never_refreshes_previously_verified_bytes(tmp_path, change):
    path = tmp_path / 'current-library'; path.write_bytes(b'initial bytes')
    verified = {}
    first = general._file(path, os.getuid(), verified=verified)
    before = path.stat()
    if change == 'chmod': path.chmod(0o400)
    elif change == 'overwrite-restored-mtime':
        path.write_bytes(b'changed bytes')
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    elif change == 'recreate':
        path.unlink(); path.write_bytes(b'initial bytes')
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    else:
        target = tmp_path / 'other-library'; target.write_bytes(b'initial bytes')
        path.unlink(); path.symlink_to(target)
    with pytest.raises((ValueError, OSError)):
        general._file(path, os.getuid(), verified=verified)
    assert verified[str(path)] == first


def test_verified_file_reads_are_never_reused_across_capture_calls(component, monkeypatch):
    root, _, _, runner, _, _ = component
    path = root / 'bin/native-input'; meta = path.stat()
    original = general.hashlib.file_digest
    count = [0]
    def hashing(stream, algorithm):
        current = os.fstat(stream.fileno())
        if (current.st_dev, current.st_ino) == (meta.st_dev, meta.st_ino): count[0] += 1
        return original(stream, algorithm)
    monkeypatch.setattr(general.hashlib, 'file_digest', hashing)
    first = general.capture_general(runner, SOURCE)
    assert count[0] == 1
    assert general.capture_general(runner, SOURCE) == first
    assert count[0] == 2


def test_real_post_start_kernel_mapping_is_current_general_input_but_not_production_history():
    # A fresh process prevents unrelated deleted mappings leaked by other tests.
    code = '''
import json,mmap,os,sys,tempfile,time
sys.path.insert(0,sys.argv[1])
import source_upgrade_general as g
import process_adoption as a
with tempfile.NamedTemporaryFile(delete=False) as f:
    f.write(b'x'*4096); path=f.name
try:
    with open(path,'r+b') as f:
        mapped=mmap.mmap(f.fileno(),0)
        proof=g._process(str(os.getpid()),os.getuid())
        meta=os.stat(path)
        device=f'{os.major(meta.st_dev):x}:{os.minor(meta.st_dev):x}'
        refused=False
        try: a.mapped_digest(path,device,str(meta.st_ino),time.time()-1)
        except ValueError: refused=True
        print(json.dumps({'current':path in proof['maps'],'productionRefused':refused}))
        mapped.close()
finally: os.unlink(path)
'''
    result = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(SOURCE / 'deploy')],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {'current': True, 'productionRefused': True}


def test_current_trust_tracks_removed_and_new_certificates(tmp_path):
    store = tmp_path / 'certs'; store.mkdir()
    (store / 'root.pem').write_bytes(b'current certificate input')
    before = general._trust_tree(store, os.getuid(), boundary=tmp_path)
    (store / 'root.pem').unlink()
    assert general._trust_tree(store, os.getuid(), boundary=tmp_path) != before
    (store / 'new.pem').write_bytes(b'new root input')
    assert general._trust_tree(store, os.getuid(), boundary=tmp_path) != before


def test_current_trust_absence_changes_when_store_is_created(tmp_path):
    target = tmp_path / 'home/.dotnet/corefx/cryptography/x509stores'
    target.parent.mkdir(parents=True)
    before = general._trust_tree(target, os.getuid(), boundary=tmp_path)
    target.mkdir()
    assert general._trust_tree(target, os.getuid(), boundary=tmp_path) != before


def test_current_absence_parent_detects_store_create_then_delete(tmp_path):
    target = tmp_path / 'x509stores'
    before = general._trust_tree(target, os.getuid(), boundary=tmp_path)
    target.mkdir(); target.rmdir()
    assert general._trust_tree(target, os.getuid(), boundary=tmp_path) != before


def test_current_trust_records_every_intermediate_leaf_alias(tmp_path):
    selected = tmp_path / 'selected.pem'
    indirect = tmp_path / 'indirect.pem'
    certificate = tmp_path / 'actual.pem'; certificate.write_bytes(b'current certificate')
    selected.symlink_to(indirect)
    indirect.symlink_to(certificate)
    before = general._trust_tree(selected, os.getuid(), boundary=tmp_path)
    indirect.unlink(); indirect.symlink_to(certificate)
    assert general._trust_tree(selected, os.getuid(), boundary=tmp_path) != before
