"""Native source preparation uses the frozen helper and canonical templates."""
import base64
import gzip
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import zlib
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
import config
import source_stage as stage

OP = '12345678-1234-1234-1234-123456789abc'
HELPER = ROOT / 'deploy/ansible/roles/relay_artifacts/files/relay-intent-stage.py'


def test_native_entrypoint_list_matches_the_owning_frozen_play():
    import yaml
    tasks = yaml.safe_load((HELPER.parents[1] / 'tasks/intent-stage.yml').read_text())
    owner = next(task for task in tasks if task.get('name') ==
                 'Parse actual candidate entrypoints without executing their privileged main functions')
    assert stage.ENTRYPOINTS == tuple(owner['loop']) and len(stage.ENTRYPOINTS) == 6


@pytest.fixture
def source_fixture():
    if sys.platform != 'linux' or os.geteuid() != 0:
        pytest.skip('actual protected Linux root filesystem required')
    with tempfile.TemporaryDirectory(prefix='relay-native-source-', dir='/run') as temporary:
        root = Path(temporary)
        root.chmod(0o700)
        repository = root / 'repository'
        repository.mkdir()
        for name in stage.ENTRYPOINTS:
            path = repository / 'controller/src' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('export const valid = true;\n')
        environment = {'PATH': '/usr/bin:/bin', 'HOME': '/nonexistent', 'GIT_CONFIG_NOSYSTEM': '1',
                       'GIT_CONFIG_GLOBAL': '/dev/null'}
        def git(*args):
            return subprocess.run(['git', *args], cwd=repository, env=environment,
                                  capture_output=True, text=True, check=True).stdout.strip()
        git('init', '-q')
        install = root / 'relay'
        releases = install / 'releases'
        releases.mkdir(parents=True)
        operation = releases / ('.stage-' + OP)
        operation.mkdir(mode=0o700)
        archive = root / 'frozen.tar'
        def freeze():
            git('add', '.')
            tree = git('write-tree')
            revision = git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                           'commit-tree', tree, '-m', 'source fixture')
            git('archive', '--format=tar', '--output=' + str(archive), revision)
            identity = {key: 'a' * 64 for key in ['sourceTreeSha256', 'controllerSourceTreeSha256',
                'codexLauncherSourceTreeSha256', 'reviewerSourceTreeSha256', 'reviewerBuildInputsTreeSha256']}
            identity.update(revision=revision, tree=tree)
            return identity
        identity = freeze()
        values = config.compile_inputs(json.loads((ROOT / 'deploy/example.json').read_text()))
        values.update(relay_deployment_profile='production', relay_install_root=str(install),
                      relay_release_root=str(releases), relay_source_archive=str(archive))
        preparation = SimpleNamespace(identity=identity, operation=OP, stage=str(operation),
                                      values=values, reinstall=False)
        yield SimpleNamespace(root=root, repository=repository, operation=operation,
                              archive=archive, preparation=preparation, freeze=freeze)


def payload(fixture):
    preparation = fixture.preparation
    return {'operationId': OP, 'sourceIdentity': preparation.identity, 'stage': preparation.stage,
            'installRoot': preparation.values['relay_install_root'], 'releaseRoot': preparation.values['relay_release_root'],
            'reinstall': False, 'compatibilityLinks': [], 'helperSource': HELPER.read_text(),
            'archiveGzipBase64': base64.b64encode(gzip.compress(fixture.archive.read_bytes(), mtime=0)).decode(),
            'consumerBase64': base64.b64encode(b'{"private":"fixture"}\n').decode()}


@pytest.mark.parametrize('links', [[], [{'alias': 'compatibility.mjs', 'target': 'controller/src/entrypoint.mjs'}]])
def test_real_frozen_helper_and_all_six_node_checks_under_restrictive_umask(source_fixture, monkeypatch, links):
    fixture = source_fixture
    request = payload(fixture)
    request['compatibilityLinks'] = links
    run, checked = stage.subprocess.run, []
    def execute(argv, **options):
        checked.append(Path(argv[-1]).name)
        return run(argv, **options)
    monkeypatch.setattr(stage.subprocess, 'run', execute)
    previous = os.umask(0o077)
    try:
        result = stage.native(request)
    finally:
        os.umask(previous)
    assert result == {'status': 'SOURCE_STAGE_READY', 'operationId': OP,
                      'sourceIdentity': fixture.preparation.identity}
    assert checked == list(stage.ENTRYPOINTS)
    assert (fixture.operation / 'source.tar').stat().st_mode & 0o777 == 0o600
    assert (fixture.operation / 'consumer.json').stat().st_mode & 0o777 == 0o600
    assert (fixture.operation / 'consumer.json').read_bytes() == b'{"private":"fixture"}\n'
    source = fixture.operation / 'release/reviewed-source'
    for name in stage.ENTRYPOINTS:
        assert (source / 'controller/src' / name).read_bytes() == (fixture.repository / 'controller/src' / name).read_bytes()
    assert (source / 'compatibility.mjs').is_symlink() is bool(links)
    assert not (Path(fixture.preparation.values['relay_install_root']) / 'current').exists()


@pytest.mark.parametrize('name', stage.ENTRYPOINTS)
def test_each_actual_entrypoint_syntax_failure_stops_source_preparation(source_fixture, name):
    fixture = source_fixture
    (fixture.repository / 'controller/src' / name).write_text('export const invalid = ;\n')
    fixture.preparation.identity = fixture.freeze()
    with pytest.raises(ValueError, match='SOURCE_SYNTAX_INVALID'):
        stage.native(payload(fixture))


@pytest.mark.parametrize('change', ['identity', 'tree', 'stage-path', 'operation', 'consumer', 'archive-traversal'])
def test_frozen_input_and_private_namespace_failures_refuse_without_active_effects(source_fixture, change):
    fixture = source_fixture
    request = payload(fixture)
    if change == 'identity': request['sourceIdentity'] = {'revision': 'wrong'}
    elif change == 'tree': request['sourceIdentity'] = {**request['sourceIdentity'], 'tree': '0' * 40}
    elif change == 'stage-path': request['releaseRoot'] = str(fixture.root / 'foreign')
    elif change == 'operation': request['operationId'] = 'not-an-operation'
    elif change == 'consumer': request['consumerBase64'] = base64.b64encode(b'not-json').decode()
    else:
        raw = io.BytesIO()
        with tarfile.open(fileobj=raw, mode='w', format=tarfile.PAX_FORMAT,
                          pax_headers={'comment': request['sourceIdentity']['revision']}) as archive:
            member = tarfile.TarInfo('../outside')
            member.size = 4
            archive.addfile(member, io.BytesIO(b'evil'))
        request['archiveGzipBase64'] = base64.b64encode(gzip.compress(raw.getvalue(), mtime=0)).decode()
    with pytest.raises((ValueError, OSError, TypeError)):
        stage.native(request)
    assert not (fixture.root / 'outside').exists()
    assert not (Path(fixture.preparation.values['relay_install_root']) / 'current').exists()


def test_frontend_uses_exact_helper_and_fallback_is_only_before_transport(source_fixture, monkeypatch):
    fixture = source_fixture
    guard = SimpleNamespace(poll=lambda: None)
    calls = []
    def execute(argv, *, payload):
        calls.append((argv, payload))
        assert payload['helperSource'].encode() == HELPER.read_bytes()
        assert payload['compatibilityLinks'] == []
        return stage.native(payload)
    fixture.preparation.execute = execute
    assert stage.prepare(fixture.preparation, guard, guard) is True
    assert len(calls) == 1 and calls[0][0][:3] == ['/usr/bin/python3', '-I', '-c']
    fixture.preparation.identity = {'unsupported': True}
    assert stage.prepare(fixture.preparation, guard, guard) is False
    assert len(calls) == 1


def test_submitted_failure_or_lost_guard_is_never_retried_as_another_play(source_fixture):
    fixture = source_fixture
    guard = SimpleNamespace(poll=lambda: None)
    def failure(*_args, **_kwargs): raise RuntimeError('remote preparation failed')
    fixture.preparation.execute = failure
    with pytest.raises(RuntimeError, match='remote preparation failed'):
        stage.prepare(fixture.preparation, guard, guard)
    observations = iter([None, 1])
    lost = SimpleNamespace(poll=lambda: next(observations))
    fixture.preparation.execute = lambda *_args, **_kwargs: {
        'status': 'SOURCE_STAGE_READY', 'operationId': OP, 'sourceIdentity': fixture.preparation.identity}
    with pytest.raises(ValueError, match='HOST_LOCK_LOST'):
        stage.prepare(fixture.preparation, lost, guard)
    observations = iter([None, 1])
    lost = SimpleNamespace(poll=lambda: next(observations))
    with pytest.raises(ValueError, match='POOL_LOCK_LOST'):
        stage.prepare(fixture.preparation, guard, lost)


def test_consumer_bytes_match_real_owning_ansible_template_action(tmp_path):
    import yaml
    values = config.compile_inputs(json.loads((ROOT / 'deploy/example.json').read_text()))
    values['relay_deployment_profile'] = 'production'
    values['relay_review_check_name'] = 'JSON parity "quoted"'
    expected = stage.render_consumer(ROOT, values)
    defaults = yaml.safe_load((ROOT / 'deploy/ansible/group_vars/all.yml').read_text())
    destination = tmp_path / 'consumer.json'
    playbook = tmp_path / 'template.yml'
    playbook.write_text(yaml.safe_dump([{'hosts': 'localhost', 'gather_facts': False,
        'vars': {**defaults, **values}, 'tasks': [{'ansible.builtin.template': {
            'src': str(ROOT / 'deploy/ansible/roles/relay_controller/templates/consumer.json.j2'),
            'dest': str(destination), 'mode': '0600'}, 'no_log': True, 'diff': False}]}], sort_keys=False))
    result = subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(playbook)],
                            capture_output=True, timeout=30)
    assert result.returncode == 0
    assert destination.read_bytes() == expected
    assert isinstance(json.loads(expected), dict)


@pytest.mark.parametrize('change', ['invalid', 'truncated', 'trailing', 'member', 'crc', 'bomb'])
def test_compressed_archive_refuses_corrupt_trailing_and_unbounded_streams(monkeypatch, change):
    monkeypatch.setattr(stage, 'MAX_ARCHIVE', 1024)
    compressed = gzip.compress(b'actual archive', mtime=0)
    if change == 'invalid':
        compressed = b'not gzip'
    elif change == 'truncated':
        compressed = compressed[:-1]
    elif change == 'trailing':
        compressed += b'extra'
    elif change == 'member':
        compressed += gzip.compress(b'second member', mtime=0)
    elif change == 'crc':
        compressed = compressed[:-8] + bytes([compressed[-8] ^ 1]) + compressed[-7:]
    elif change == 'bomb':
        compressed = gzip.compress(b'x' * 1025, mtime=0)
    with pytest.raises((ValueError, zlib.error)):
        stage.decode_archive(base64.b64encode(compressed).decode())


def test_compressed_archive_preserves_exact_tar_bytes_and_limit(monkeypatch):
    monkeypatch.setattr(stage, 'MAX_ARCHIVE', 1024)
    original = b'x' * 1024
    assert stage.decode_archive(base64.b64encode(gzip.compress(original, mtime=0)).decode()) == original
