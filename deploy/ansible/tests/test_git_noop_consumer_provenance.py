"""Exercise the ordinary read-only composition with historical consumer Git provenance."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
REVISION, TREE = 'a' * 40, 'b' * 40
pytestmark = pytest.mark.skipif(sys.platform != 'linux' or os.geteuid() != 0,
                               reason='root private mount namespace required')


@pytest.mark.parametrize('published', [False, True])
def test_ordinary_git_noop_retains_original_consumer_provenance_after_receiving_head_moves(published):
    probe = subprocess.run(['unshare', '--mount', '--fork', 'true'], capture_output=True)
    if probe.returncode:
        pytest.skip('private mount namespaces unavailable')
    with tempfile.TemporaryDirectory(prefix='relay-git-noop-') as directory:
        result = subprocess.run(['unshare', '--mount', '--fork', '--propagation', 'private',
            sys.executable, str(Path(__file__).resolve()), '--fixture', directory,
            'published' if published else 'unpublished', 'none'], capture_output=True, text=True, timeout=120,
            env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        assert result.returncode == 0, result.stdout + result.stderr
        proof = json.loads(result.stdout.splitlines()[-1])
        assert proof['strategy'] == 'verify' and proof['unchanged'] is True
        assert proof['installedConsumer'] != proof['receivingHead']
        assert proof['backendCalls'] == 1 and proof['targetInventoryProcesses'] >= 4
        assert proof['actualFinalAnsibleIdentity'] is True and proof['slots'] == 32


@pytest.mark.parametrize('fault,code', [
    ('consumer-missing', 'intent-readonly-consumer-provenance-unproven'),
    ('consumer-invalid', 'intent-readonly-consumer-provenance-unproven'),
    ('consumer-changed', 'intent-readonly-consumer-provenance-changed'),
    ('product', 'intent-installation-changed-before-reservation'),
    ('source', 'intent-installation-changed-before-reservation'),
    ('pair', 'intent-readonly-installed-binding-unproven'),
    ('receipt', 'intent-readonly-installed-binding-unproven'),
    ('config', 'intent-readonly-installed-binding-unproven'),
    ('host-lock', 'HOST_LOCK_LOST'),
    ('pool-lock', 'HOST_LOCK_LOST'),
])
def test_ordinary_git_noop_rejects_changed_protected_evidence_before_backend(fault, code):
    probe = subprocess.run(['unshare', '--mount', '--fork', 'true'], capture_output=True)
    if probe.returncode:
        pytest.skip('private mount namespaces unavailable')
    with tempfile.TemporaryDirectory(prefix='relay-git-noop-negative-') as directory:
        result = subprocess.run(['unshare', '--mount', '--fork', '--propagation', 'private',
            sys.executable, str(Path(__file__).resolve()), '--fixture', directory, 'unpublished', fault],
            capture_output=True, text=True, timeout=120,
            env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        assert result.returncode == 0, result.stdout + result.stderr
        proof = json.loads(result.stdout.splitlines()[-1])
        assert code.upper().replace('-', '_') in proof['blocked'] and proof['backendCalls'] == 0
        assert proof['unchanged'] is True


def test_expert_postcheck_still_rejects_a_different_selected_receiving_head():
    probe = subprocess.run(['unshare', '--mount', '--fork', 'true'], capture_output=True)
    if probe.returncode:
        pytest.skip('private mount namespaces unavailable')
    with tempfile.TemporaryDirectory(prefix='relay-expert-consumer-') as directory:
        result = subprocess.run(['unshare', '--mount', '--fork', '--propagation', 'private',
            sys.executable, str(Path(__file__).resolve()), '--fixture', directory, 'unpublished', 'expert'],
            capture_output=True, text=True, timeout=120,
            env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        assert result.returncode == 0, result.stdout + result.stderr
        assert 'relay_production_final_manifest.consumerRevision == relay_consumer_revision' in result.stdout
        proof = json.loads(result.stdout.splitlines()[-1])
        assert 'BACKEND_FAILED' in proof['blocked'] and proof['backendCalls'] == 1
        assert proof['unchanged'] is True


def fixture(root, published, fault):
    """No host, service, credential or GitHub operation escapes this mount namespace."""
    sys.path[:0] = [str(ROOT / 'deploy'), str(ROOT / 'deploy/tests')]
    import ansible_transport
    import config as configuration
    import install_recovery
    import intent_install
    import workflow_projection
    from managed_pool_transport import projected_consumer
    from test_managed_pool import inputs
    spec = importlib.util.spec_from_file_location('git_noop_primitive', ROOT / 'deploy/relay-deploy.py')
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    for name in ['opt', 'etc', 'var/lib']:
        (root / name).mkdir(parents=True, mode=0o755)
    for name in ['passwd', 'group', 'nsswitch.conf', 'ld.so.cache']:
        path = Path('/etc') / name
        if path.is_file():
            shutil.copyfile(path, root / 'etc' / name)
    for name in ['opt', 'etc', 'var/lib']:
        subprocess.run(['mount', '--bind', str(root / name), '/' + name], check=True)
    config = inputs(2, namespace='relay-noop-provenance')
    config['target']['connection'] = 'local'
    config['environment']['localApply'] = {'source': 'git', 'repository': 'example-org/private-config',
                                         'configPath': 'test/relay.json'}
    config = configuration.loads(json.dumps(config), ROOT)
    config = configuration.loads(json.dumps(config, sort_keys=True, separators=(',', ':')), ROOT)
    raw = json.dumps(config).encode()
    config_path = root / 'desired.json'
    config_path.write_bytes(raw)
    receipt = {'config_repository': 'example-org/private-config', 'config_repository_id': 1,
        'config_sha': 'c' * 40, 'config_blob_sha': 'd' * 40, 'config_path': 'test/relay.json',
        'config_sha256': hashlib.sha256(raw).hexdigest(), 'product_repository': 'example/codex-relay',
        'product_repository_id': 2, 'product_sha': REVISION, 'source_policy': 'accepted-main',
        'workflow_run_id': 12, 'action': 'apply'}
    attested = {**receipt, 'workflow_run_id': 9}
    values = configuration.compile_inputs(config)
    install = Path(values['relay_install_root'])
    release = install / 'releases' / REVISION
    source = release / 'reviewed-source'
    for component in ['consumer', 'controller', 'contracts', 'runtime', 'reviewer']:
        shutil.copytree(ROOT / component, source / component,
            ignore=shutil.ignore_patterns('__pycache__', 'node_modules', 'target'))
    for path in [install, *install.rglob('*')]:
        path.chmod(0o755 if path.is_dir() else 0o644)
    identity = {'revision': REVISION, 'tree': TREE,
                'controllerSourceTreeSha256': '1' * 64, 'reviewerSourceTreeSha256': '2' * 64,
                'sourceTreeSha256': '3' * 64, 'codexLauncherSourceTreeSha256': '4' * 64,
                'reviewerBuildInputsTreeSha256': '5' * 64}
    (source / '.relay-source.json').write_text(json.dumps(identity))
    snapshot = (json.dumps(config, sort_keys=True, separators=(',', ':'), ensure_ascii=False) + '\n').encode()
    (release / 'deployment-config.json').write_bytes(snapshot)
    (release / 'deployment-config.json').chmod(0o600)
    conf = Path(values['relay_config_root'])
    conf.mkdir(parents=True, mode=0o755)
    consumer = conf / 'consumer.json'
    consumer.write_text(json.dumps(projected_consumer(config, ROOT)))
    consumer.chmod(0o644)
    Path(values['relay_state_root']).mkdir(parents=True, mode=0o755)
    claims = Path(config['consumer']['paths']['claimRoot'])
    claims.mkdir(mode=0o700)
    env = {**os.environ, 'RELAY_CONSUMER_CONFIG': str(consumer),
           'RELAY_REPOSITORY': config['consumer']['repository']}
    gate_cli = source / 'controller/src/admission-cli.mjs'
    subprocess.run(['node', str(gate_cli), 'initialize'], env=env, check=True, capture_output=True)
    receiving = root / 'receiving'
    receiving.mkdir()
    git_env = {**os.environ, 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null'}
    def git(*args):
        return subprocess.check_output(['git', '-C', str(receiving), *args], env=git_env, text=True).strip()
    git('init', '--quiet', '--template=', '--initial-branch=main')
    def commit(message):
        git('add', '.')
        git('-c', 'user.name=fixture', '-c', 'user.email=fixture@example.invalid',
            'commit', '--quiet', '-m', message)
        return git('rev-parse', 'HEAD')
    (receiving / 'README.md').write_text('Original receiving repository.\n')
    original_consumer = commit('Original consumer installation provenance')
    (receiving / 'README.md').write_text('Independent receiving repository change.\n')
    commit('Independent consumer change')
    if published:
        workflow_projection.project(config, REVISION, ROOT, receiving)
        commit('Publish actual generated consumer integration')
    receiving_head = git('rev-parse', 'HEAD')
    manifest = {'commit': REVISION, 'installedRevision': REVISION, 'resolvedRevision': REVISION,
        'gitTree': TREE, 'consumerRevision': original_consumer, 'previousRevision': 'none',
        'controllerSourceTreeSha256': '1' * 64, 'reviewerSourceTreeSha256': '2' * 64,
        'deploymentConfigSha256': hashlib.sha256(snapshot).hexdigest(), 'gitConfigReceipt': attested,
        'deploymentContract': json.loads((ROOT / 'deploy/installation-contract.json').read_text()),
        'installationState': {'schemaVersion': 1, 'stage': 'ready',
                              'pairSha256': intent_install.pair_digest(attested)}}
    manifest_path = release / 'artifact-manifest.json'
    manifest_path.write_text(json.dumps(manifest))
    manifest_path.chmod(0o600)
    (install / 'current').symlink_to(str(release))
    guards, calls, probes, fault_baseline = [], [], [], []
    def damage():
        if fault == 'consumer-missing':
            manifest.pop('consumerRevision')
        elif fault == 'consumer-invalid':
            manifest['consumerRevision'] = 'main'
        elif fault == 'product':
            manifest['installedRevision'] = 'f' * 40
        elif fault == 'source':
            (source / '.relay-source.json').write_text(json.dumps({**identity, 'tree': 'f' * 40}))
        elif fault == 'pair':
            manifest['gitConfigReceipt'] = {**attested, 'config_sha': 'e' * 40}
        elif fault == 'receipt':
            manifest['gitConfigReceipt'] = {**attested, 'workflow_run_id': 777}
        elif fault == 'config':
            consumer_config = json.loads(consumer.read_bytes())
            consumer_config['defaultProfile']['effort'] = 'low'
            consumer.write_text(json.dumps(consumer_config))
        if fault not in ['source', 'config', 'host-lock', 'pool-lock', 'consumer-changed']:
            manifest_path.write_text(json.dumps(manifest))
        fault_baseline[:] = [evidence()]
    def guard_factory(_target, _key, namespace):
        path = '/var/lib/' + namespace + '-deployment.lock'
        guard = subprocess.Popen([sys.executable, '-I', '-c',
            (ROOT / 'deploy/deployment_lock.py').read_text(), path],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        assert guard.stdout.readline().strip() == 'DEPLOYMENT_LOCK_READY'
        guards.append(guard)
        if fault != 'none' and len(guards) == 1:
            damage()
        if ((fault == 'host-lock' and len(guards) == 1)
                or (fault == 'pool-lock' and len(guards) == 2)):
            guard.stdin.close()
            assert guard.wait(timeout=10) == 0
        return guard
    # Real target inventory source executes in a child process. This substitutes
    # transport only, never installed state, provenance, strategy or a PASS result.
    def target_process(target, key, argv, **options):
        assert target['connection'] == 'local' and argv[:3] == ['/usr/bin/python3', '-I', '-c']
        probes.append(argv)
        result = subprocess.run(argv, **options, capture_output=True, text=True)
        if fault == 'consumer-changed' and len(probes) == 2:
            manifest_path.write_text(json.dumps({**manifest, 'consumerRevision': 'e' * 40}))
            fault_baseline[:] = [evidence()]
        return result
    def backend(argv, _cwd, environment, log, guard, pool_guard):
        assert '--check' in argv
        if fault == 'expert':
            assert guard is pool_guard is None
        else:
            assert guard.poll() is pool_guard.poll() is None
        hosts = json.loads(Path(argv[argv.index('-i') + 1]).read_bytes())['all']['children']['relay']['hosts']
        selected = next(iter(hosts.values()))
        calls.append(selected)
        # Execute the owning final task, including its real manifest read and
        # strict product/consumer/config assertions; no fabricated success marker.
        tasks = [
            {'ansible.builtin.include_tasks': str(ROOT / 'deploy/ansible/roles/relay_artifacts/tasks/resolve-identities.yml')},
            {'ansible.builtin.stat': {'path': '{{ relay_install_root }}/current', 'follow': False},
             'register': 'current_stat', 'changed_when': False},
            {'ansible.builtin.slurp': {'src': '{{ relay_release_path }}/artifact-manifest.json'},
             'register': 'manifest_raw'},
            {'ansible.builtin.set_fact': {
                'relay_production_final_paths': {'results': ['{{ current_stat }}']},
                'relay_production_final_manifest': '{{ manifest_raw.content | b64decode | from_json }}'}},
            {'ansible.builtin.include_tasks': str(ROOT / 'deploy/ansible/tasks/installed-identity.yml')}]
        selected = {**yaml.safe_load((ROOT / 'deploy/ansible/group_vars/all.yml').read_text()),
                    **selected, 'ansible_python_interpreter': '/usr/bin/python3'}
        playbook = root / 'identity.yml'
        playbook.write_text(yaml.safe_dump([{'hosts': 'localhost', 'connection': 'local',
            'gather_facts': False, 'vars': selected, 'tasks': tasks}]))
        result = subprocess.run(['ansible-playbook', '-i', 'localhost,', '-c', 'local', '--check', str(playbook)],
            env={**environment, 'ANSIBLE_NOCOLOR': '1'}, capture_output=True, text=True, timeout=60)
        log.write(result.stdout + result.stderr)
        log.flush()
        if result.returncode:
            print(result.stdout + result.stderr, flush=True)
        return result.returncode
    # Pre-create the same kernel mutexes so acquisition cannot change baseline.
    for namespace in [config['environment']['namespace'],
                      'codex-relay-pool-' + config['environment']['generalRunner']['name']]:
        lock = Path('/var/lib/' + namespace + '-deployment.lock')
        lock.touch(mode=0o600)
    critical = [manifest_path, release / 'deployment-config.json', consumer, source / '.relay-source.json',
                claims / 'admission-v1.json', *Path('/var/lib').glob('*-deployment.lock')]
    def evidence():
        return {str(path): (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mode,
                           path.stat().st_ino, path.stat().st_mtime_ns, path.stat().st_ctime_ns)
                for path in critical}
    before = evidence()
    argv = ['relay-deploy', '--phase', 'post-check' if fault == 'expert' else 'install',
            '--config', str(config_path), '--connection', 'local',
            '--consumer-root', str(receiving), '--resolved-revision', REVISION, '--log-root', str(root / 'logs')]
    blocked = None
    with patch.object(sys, 'argv', argv), patch.object(cli, 'source_identity', return_value=identity), \
         patch.object(cli, 'apply_guard', side_effect=guard_factory), \
         patch.object(cli, 'run_backend', side_effect=backend), \
         patch.object(ansible_transport, 'run_target', side_effect=target_process), \
         patch.object(ansible_transport, 'qualify_target'), patch.object(intent_install, 'qualify_target'), \
         patch.object(install_recovery, 'remote_probe', return_value=None):
        args = cli.arguments()
        args.git_intent = receipt
        previous_umask = os.umask(0o022)
        try:
            try:
                cli.run(args)
            except RuntimeError as error:
                if fault == 'none':
                    raise
                blocked = str(error)
        finally:
            os.umask(previous_umask)
    assert all(guard.poll() == 0 for guard in guards)
    if fault == 'expert':
        assert blocked and len(calls) == 1
        assert calls[0]['relay_consumer_revision'] == receiving_head
        print(json.dumps({'blocked': blocked, 'backendCalls': len(calls), 'unchanged': before == evidence()}))
        return
    if fault != 'none':
        assert blocked and not calls
        print(json.dumps({'blocked': blocked, 'backendCalls': len(calls),
                          'unchanged': fault_baseline[0] == evidence()}))
        return
    assert calls[0]['relay_consumer_revision'] == original_consumer
    assert calls[0]['relay_git_config_receipt'] == attested
    gate = subprocess.run(['node', str(gate_cli), 'status'], env=env, check=True,
                          capture_output=True, text=True)
    assert json.loads(gate.stdout)['phase'] == 'open'
    print(json.dumps({'strategy': 'verify', 'unchanged': before == evidence(), 'slots': 32,
        'installedConsumer': original_consumer, 'receivingHead': receiving_head,
        'backendCalls': len(calls), 'targetInventoryProcesses': len(probes),
        'actualFinalAnsibleIdentity': True}))


if __name__ == '__main__' and len(sys.argv) == 5 and sys.argv[1] == '--fixture':
    fixture(Path(sys.argv[2]), sys.argv[3] == 'published', sys.argv[4])
