"""Qualify workflow publication artifacts through the real public CLI only.

All Git repositories and desired inputs are disposable local fixtures. These
checks neither contact GitHub nor use a target host, credentials, sudo or Apply.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
import config as configuration
import workflow_projection as workflows

RESULT = 'RELAY_WORKFLOW_PROJECTION_RESULT='
REPOSITORIES = ['example-org/public-' + str(index) for index in range(1, 5)] + [
    'example-org/private-deployment']


def git(root, *arguments):
    return subprocess.check_output([
        'git', '-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=false',
        '-C', str(root), *arguments], text=True).strip()


def commit(root):
    git(root, 'add', '.')
    git(root, '-c', 'user.name=fixture', '-c', 'user.email=fixture@example.invalid',
        '-c', 'commit.gpgsign=false', 'commit', '--quiet', '-m', 'reviewed fixture')
    return git(root, 'rev-parse', 'HEAD')


def initialize(root):
    git(root, 'init', '--quiet', '--template=', '--initial-branch=main')
    return commit(root)


def snapshot(root):
    """Include bytes and write-sensitive metadata, without traversing aliases."""
    result = {}
    for directory, names, files in os.walk(root, followlinks=False):
        names[:] = [name for name in names if name != '.git']
        for name in [*names, *files]:
            path = Path(directory) / name
            metadata = path.lstat()
            content = (('symlink', os.readlink(path)) if path.is_symlink() else
                       ('directory', None) if path.is_dir() else ('file', path.read_bytes()))
            result[str(path.relative_to(root))] = (
                content, metadata.st_ino, metadata.st_mtime_ns, metadata.st_mode)
    return result


@pytest.fixture(scope='module')
def product(tmp_path_factory):
    root = tmp_path_factory.mktemp('public-projection-product')
    for name in ['deploy', 'consumer', 'controller', 'runtime', 'contracts', 'reviewer']:
        shutil.copytree(ROOT / name, root / name,
                        ignore=shutil.ignore_patterns('__pycache__', 'target', '.pytest_cache'))
    revision = initialize(root)
    yield root, revision
    assert git(root, 'status', '--porcelain', '--untracked-files=all') == ''


@pytest.fixture
def fixture(tmp_path, product):
    source, revision = product
    value = json.loads((source / 'deploy/example.json').read_bytes())
    del value['consumer']['repository']
    value['consumer']['repositories'] = REPOSITORIES
    value['environment']['repository'] = REPOSITORIES[0]
    value['environment']['localApply'] = {
        'source': 'git', 'repository': REPOSITORIES[-1], 'configPath': 'prod/relay.json'}
    config_path = tmp_path / 'frozen-desired-config.json'
    # Deliberately retain formatting that differs from normalized JSON. The
    # public result must identify these exact input bytes across every target.
    raw = (json.dumps(value, indent=3) + '\n\n').encode()
    config_path.write_bytes(raw)
    validated = configuration.loads(raw.decode(), source)
    forbidden = tmp_path / 'forbidden-host-command'
    tools = tmp_path / 'bin'
    tools.mkdir()
    for name in ['sudo', 'ssh', 'ssh-keygen', 'ansible-playbook', 'systemctl', 'curl', 'gh']:
        tool = tools / name
        tool.write_text('#!' + sys.executable + '\nfrom pathlib import Path\n'
                        + 'Path(' + repr(str(forbidden)) + ').write_text(' + repr(name) + ')\n'
                        + 'raise SystemExit(97)\n')
        tool.chmod(0o755)
    environment = {**os.environ, 'PATH': str(tools) + os.pathsep + os.environ['PATH'],
                   'PYTHONDONTWRITEBYTECODE': '1'}

    class PublicCLI:
        config = validated
        path = config_path
        config_raw = raw
        product_root = source
        product_revision = revision

        def consumer(self, name='consumer'):
            root = tmp_path / name
            root.mkdir()
            (root / 'README.md').write_text('consumer-owned repository\n')
            workflows_root = root / '.github/workflows'
            workflows_root.mkdir(parents=True)
            (root / validated['consumer']['validationWorkflow']).write_text('consumer-owned CI\n')
            (root / workflows.PRODUCTION).write_text('consumer-owned lifecycle workflow\n')
            initialize(root)
            return root

        def invoke(self, phase, *arguments, consumer=None, repository=None,
                   authorize=True, resolved=None, config_file=None):
            command = [sys.executable, str(source / 'deploy/relay-deploy.py'),
                       '--config', str(config_file or config_path), '--phase', phase,
                       '--resolved-revision', resolved or revision]
            if authorize and phase in ['workflow-project', 'workflow-deployment-project']:
                command.append('--authorize-workflow-projection')
            if consumer is not None:
                command.extend(['--consumer-root', str(consumer)])
            if repository is not None:
                command.extend(['--repository', repository])
            completed = subprocess.run([*command, *map(str, arguments)], cwd=tmp_path,
                                       env=environment, text=True, capture_output=True, timeout=30)
            assert not forbidden.exists(), 'projection invoked a host/credential command'
            return completed

        def project(self, consumer, repository=REPOSITORIES[0]):
            return self.invoke('workflow-project', consumer=consumer, repository=repository)

    yield PublicCLI()
    assert config_path.read_bytes() == raw
    assert not forbidden.exists()


def result(completed):
    assert completed.returncode == 0, completed.stdout + completed.stderr
    lines = [line.removeprefix(RESULT) for line in completed.stdout.splitlines()
             if line.startswith(RESULT)]
    assert len(lines) == 1, completed.stdout
    return json.loads(lines[0])


def assert_identity(value, fixture, kind, repository):
    assert value['schemaVersion'] == 1
    assert value['kind'] == kind
    assert value['repository'] == repository
    assert value['productRevision'] == fixture.product_revision
    assert value['configSha256'] == hashlib.sha256(fixture.config_raw).hexdigest()


def test_one_frozen_pair_projects_all_five_consumers_and_deployment(fixture, tmp_path):
    digests, revisions = set(), set()
    for index, repository in enumerate(REPOSITORIES):
        consumer = fixture.consumer('consumer-' + str(index))
        original_head = git(consumer, 'rev-parse', 'HEAD')
        completed = fixture.project(consumer, repository)
        value = result(completed)
        assert_identity(value, fixture, 'consumer', repository)
        assert value['sourceRepository'] == fixture.config['source']['repository']
        assert value['consumerRevision'] == original_head
        assert value['compatibility'] == 'missing'
        assert value['changed'] is True
        assert 'RELAY_WORKFLOW_PROJECTION=PASS;' in completed.stdout
        assert 'RELAY_DEPLOYMENT_RESULT=PASS;phase=workflow-project' in completed.stdout
        rendered = workflows.render(fixture.config, fixture.product_revision,
                                    fixture.product_root, repository)
        assert set(value['files']) == {*rendered, workflows.MANIFEST}
        for path, content in rendered.items():
            assert (consumer / path).read_bytes() == content
            job, = yaml.safe_load(content)['jobs'].values()
            assert job['steps'][0]['env']['RELAY_REPOSITORY'] == repository
        assert (consumer / fixture.config['consumer']['validationWorkflow']).read_text() == 'consumer-owned CI\n'
        assert (consumer / workflows.PRODUCTION).read_text() == 'consumer-owned lifecycle workflow\n'
        assert git(consumer, 'rev-parse', 'HEAD') == original_head
        accepted_head = commit(consumer)
        before = snapshot(consumer)
        repeated = result(fixture.project(consumer, repository))
        assert repeated['compatibility'] == 'compatible'
        assert repeated['changed'] is False
        assert repeated['consumerRevision'] == accepted_head
        assert snapshot(consumer) == before
        verified = fixture.invoke('workflow-verify', consumer=consumer, repository=repository)
        assert verified.returncode == 0, verified.stdout + verified.stderr
        assert 'RELAY_WORKFLOW_PROJECTION=PASS;' in verified.stdout
        assert 'RELAY_DEPLOYMENT_RESULT=PASS;phase=workflow-verify' in verified.stdout
        assert snapshot(consumer) == before
        assert git(consumer, 'status', '--porcelain') == ''
        digests.add(value['configSha256'])
        revisions.add(value['productRevision'])

    output = tmp_path / 'deployment-artifact'
    value = result(fixture.invoke('workflow-deployment-project', '--projection-output', output))
    assert_identity(value, fixture, 'deployment', REPOSITORIES[-1])
    assert value['changed'] is True
    assert set(value['files']) == {workflows.PRODUCTION}
    digests.add(value['configSha256'])
    revisions.add(value['productRevision'])
    assert len(digests) == len(revisions) == 1
    rendered = workflows.render_deployment(fixture.config, fixture.product_revision, fixture.product_root)
    assert (output / workflows.PRODUCTION).read_bytes() == rendered[workflows.PRODUCTION]
    before = snapshot(output)
    repeated = result(fixture.invoke('workflow-deployment-project', '--projection-output', output))
    assert repeated['changed'] is False
    assert snapshot(output) == before
    # Installation integration and the standalone public artifact use one
    # dispatcher renderer, including the separate deployment repository binding.
    integrated = workflows.integration(fixture.config, fixture.product_revision,
        fixture.product_root, tmp_path / 'consumer-0', tmp_path / 'integration')
    assert (Path(integrated['deploymentDirectory']) / workflows.PRODUCTION).read_bytes() == rendered[workflows.PRODUCTION]
    assert not (output / workflows.MANIFEST).exists()


@pytest.mark.parametrize('compatibility', ['stale-compatible', 'incompatible'])
def test_public_result_classifies_intact_previous_baseline_before_writing(fixture, compatibility):
    consumer = fixture.consumer()
    result(fixture.project(consumer))
    manifest_path = consumer / workflows.MANIFEST
    manifest = json.loads(manifest_path.read_bytes())
    routing = fixture.config['consumer']['routingWorkflow']
    previous = (consumer / routing).read_bytes() + b'# accepted previous managed bytes\n'
    (consumer / routing).write_bytes(previous)
    manifest['files'][routing] = hashlib.sha256(previous).hexdigest()
    if compatibility == 'incompatible':
        manifest['workflowContract'] = 'relay-workflows-v999'
    manifest_path.write_text(json.dumps(manifest))
    accepted_head = commit(consumer)
    value = result(fixture.project(consumer))
    assert value['compatibility'] == compatibility
    assert value['consumerRevision'] == accepted_head
    assert value['changed'] is True
    assert (consumer / routing).read_bytes() != previous
    commit(consumer)
    repeated = result(fixture.project(consumer))
    assert repeated['compatibility'] == 'compatible'
    assert repeated['changed'] is False


def test_noncanonical_manifest_requires_a_write_and_then_becomes_a_noop(fixture, tmp_path):
    consumer = fixture.consumer()
    result(fixture.project(consumer))
    manifest_path = consumer / workflows.MANIFEST
    manifest_path.write_text(json.dumps(json.loads(manifest_path.read_bytes()), separators=(',', ':')))
    commit(consumer)
    # Preserve the existing Apply result contract, whose compatibility tests
    # parsed manifests. Public projection adds an exact canonical-byte no-op
    # promise without changing installation integration's classification.
    integrated = workflows.integration(fixture.config, fixture.product_revision,
        fixture.product_root, consumer, tmp_path / 'integration')
    assert integrated['compatibility'] == 'compatible'
    value = result(fixture.project(consumer))
    assert value['compatibility'] == 'stale-compatible'
    assert value['changed'] is True
    commit(consumer)
    before = snapshot(consumer)
    assert result(fixture.project(consumer))['changed'] is False
    assert snapshot(consumer) == before


@pytest.mark.parametrize('damage,diagnostic', [
    ('malformed', None), ('partial-manifest', 'workflow-manifest-keys'),
    ('partial-files', 'workflow-drift'), ('drift', 'workflow-drift'),
    ('consumer-binding', 'workflow-consumer-binding'),
    ('source-binding', 'workflow-consumer-binding'),
    ('path-migration', 'workflow-path-migration-required'),
    ('managed-symlink', 'workflow-file-unavailable'),
    ('manifest-symlink', 'workflow-file-unavailable'),
])
def test_rejected_existing_projection_preserves_every_consumer_file(fixture, damage, diagnostic):
    consumer = fixture.consumer()
    result(fixture.project(consumer))
    path = consumer / workflows.MANIFEST
    manifest = json.loads(path.read_bytes())
    routing = fixture.config['consumer']['routingWorkflow']
    if damage == 'malformed':
        path.write_bytes(b'{broken JSON\n')
    elif damage == 'partial-manifest':
        del manifest['files']
    elif damage == 'partial-files':
        (consumer / routing).unlink()
    elif damage == 'drift':
        (consumer / routing).write_bytes(b'owner changed a managed file\n')
    elif damage == 'consumer-binding':
        manifest['consumerRepository'] = REPOSITORIES[1]
    elif damage == 'source-binding':
        manifest['sourceRepository'] = 'https://github.com/foreign/relay.git'
    elif damage == 'path-migration':
        old_path = '.github/workflows/previous-routing.yml'
        (consumer / routing).rename(consumer / old_path)
        manifest['files'][old_path] = manifest['files'].pop(routing)
    elif damage in ['managed-symlink', 'manifest-symlink']:
        unsafe = consumer / routing if damage == 'managed-symlink' else path
        owner_file = consumer / 'owner-reference.txt'
        owner_file.write_bytes(unsafe.read_bytes())
        unsafe.unlink()
        unsafe.symlink_to(owner_file)
    if damage not in ['malformed', 'partial-files', 'drift', 'managed-symlink', 'manifest-symlink']:
        path.write_text(json.dumps(manifest))
    commit(consumer)
    before = snapshot(consumer)
    completed = fixture.project(consumer)
    assert completed.returncode != 0
    assert RESULT not in completed.stdout
    if diagnostic:
        assert diagnostic in completed.stdout + completed.stderr
    assert snapshot(consumer) == before


@pytest.mark.parametrize('collision', ['unmanaged-file', 'file-symlink', 'directory-symlink', 'directory-file'])
def test_initial_path_collisions_are_rejected_without_adopting_owner_bytes(fixture, tmp_path, collision):
    consumer = fixture.consumer()
    routing = consumer / fixture.config['consumer']['routingWorkflow']
    outside = tmp_path / 'outside-owner-file'
    outside.write_text('outside owner bytes\n')
    if collision == 'unmanaged-file':
        routing.write_text('unmanaged owner workflow\n')
    elif collision == 'file-symlink':
        routing.symlink_to(outside)
    else:
        shutil.rmtree(consumer / '.github/workflows')
        if collision == 'directory-symlink':
            (consumer / '.github/workflows').symlink_to(tmp_path, target_is_directory=True)
        else:
            (consumer / '.github/workflows').write_text('owner file at directory path\n')
    commit(consumer)
    before = snapshot(consumer)
    completed = fixture.project(consumer)
    assert completed.returncode != 0
    assert RESULT not in completed.stdout
    assert snapshot(consumer) == before
    assert outside.read_text() == 'outside owner bytes\n'


def test_edited_deployment_artifact_is_never_overwritten(fixture, tmp_path):
    output = tmp_path / 'deployment-artifact'
    result(fixture.invoke('workflow-deployment-project', '--projection-output', output))
    (output / workflows.PRODUCTION).write_bytes(b'owner-edited dispatcher artifact\n')
    before = snapshot(output)
    completed = fixture.invoke('workflow-deployment-project', '--projection-output', output)
    assert completed.returncode != 0
    assert 'deployment-artifact-changed' in completed.stdout + completed.stderr
    assert RESULT not in completed.stdout
    assert snapshot(output) == before


@pytest.mark.parametrize('collision', ['output-symlink', 'workflow-symlink', 'workflow-directory', 'directory-file'])
def test_deployment_artifact_path_collisions_preserve_owner_files(fixture, tmp_path, collision):
    output = tmp_path / 'deployment-artifact'
    outside = tmp_path / 'outside-artifact'
    outside.mkdir()
    (outside / 'owner.txt').write_text('outside owner artifact\n')
    if collision == 'output-symlink':
        output.symlink_to(outside, target_is_directory=True)
    else:
        output.mkdir()
        (output / '.github').mkdir()
        if collision == 'directory-file':
            (output / '.github/workflows').write_text('owner file at directory path\n')
        else:
            (output / '.github/workflows').mkdir()
            if collision == 'workflow-directory':
                (output / workflows.PRODUCTION).mkdir()
            else:
                (output / workflows.PRODUCTION).symlink_to(outside / 'owner.txt')
    before, outside_before = snapshot(output), snapshot(outside)
    completed = fixture.invoke('workflow-deployment-project', '--projection-output', output)
    assert completed.returncode != 0
    if collision == 'workflow-symlink':
        assert 'workflow-file-unavailable:' in completed.stderr
        assert 'inspect-file-type-and-access' in completed.stderr
    elif collision == 'workflow-directory':
        assert 'workflow-regular-file:' in completed.stderr
    assert RESULT not in completed.stdout
    assert snapshot(output) == before
    assert snapshot(outside) == outside_before


def test_deployment_artifact_cannot_be_written_into_the_product_checkout(fixture):
    output = fixture.product_root / 'unadmitted-workflow-artifact'
    completed = fixture.invoke('workflow-deployment-project', '--projection-output', output)
    assert completed.returncode != 0
    assert 'projection-output-outside-checkouts' in completed.stdout + completed.stderr
    assert RESULT not in completed.stdout
    assert not output.exists()


@pytest.mark.parametrize('phase', ['workflow-project', 'workflow-deployment-project'])
def test_projection_requires_authorization_and_the_exact_resolved_source(fixture, tmp_path, phase):
    consumer = fixture.consumer()
    output = tmp_path / 'deployment-artifact'
    options = {'consumer': consumer, 'repository': REPOSITORIES[0]} if phase == 'workflow-project' else {}
    arguments = [] if phase == 'workflow-project' else ['--projection-output', output]
    before = snapshot(consumer)
    for overrides, diagnostic in [({'authorize': False}, 'explicit-workflow-projection'),
                                  ({'resolved': 'f' * 40}, 'resolved-revision-mismatch')]:
        completed = fixture.invoke(phase, *arguments, **options, **overrides)
        assert completed.returncode != 0
        assert diagnostic in completed.stdout + completed.stderr
        assert RESULT not in completed.stdout
        assert snapshot(consumer) == before
        assert not output.exists()


def test_deployment_projection_rejects_non_git_lifecycle_source(fixture, tmp_path):
    value = copy.deepcopy(fixture.config)
    value['environment']['localApply'] = {'configPath': 'deploy/relay.json'}
    other_config = tmp_path / 'checkout-source-config.json'
    other_config.write_text(json.dumps(value))
    output = tmp_path / 'deployment-artifact'
    completed = fixture.invoke('workflow-deployment-project', '--projection-output', output,
                               config_file=other_config)
    assert completed.returncode != 0
    assert 'deployment-workflow-source' in completed.stdout + completed.stderr
    assert RESULT not in completed.stdout
    assert not output.exists()


def test_deployment_projection_rejects_consumer_checkout_and_foreign_target(fixture, tmp_path):
    consumer = fixture.consumer()
    output = tmp_path / 'deployment-artifact'
    before = snapshot(consumer)
    for options in [{'consumer': consumer}, {'repository': 'foreign/repository'}]:
        completed = fixture.invoke('workflow-deployment-project', '--projection-output', output, **options)
        assert completed.returncode != 0
        assert RESULT not in completed.stdout
        assert not output.exists()
        assert snapshot(consumer) == before
