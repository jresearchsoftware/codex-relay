"""The real primitive must advance only its post-bootstrap inventory identity."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[3]
REVISION = 'a' * 40
CONSUMER = 'c' * 40
pytestmark = pytest.mark.skipif(sys.platform != 'linux' or os.geteuid() != 0,
    reason='private native mount namespace requires root')


@pytest.mark.parametrize('already_installed', [False, True])
def test_bootstrap_post_check_uses_new_identity_without_weakening_initial_gate(already_installed):
    probe = subprocess.run(['unshare', '--mount', '--fork', 'true'], capture_output=True)
    if probe.returncode:
        pytest.skip('private mount namespaces unavailable')
    with tempfile.TemporaryDirectory(prefix='relay-post-bootstrap-', dir='/run') as temporary:
        result = subprocess.run(['unshare', '--mount', '--fork', '--propagation', 'private',
            sys.executable, str(Path(__file__).resolve()), '--primitive-fixture', temporary,
            'existing' if already_installed else 'absent'],
            env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}, capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stdout + result.stderr
        proof = json.loads(result.stdout.splitlines()[-1])
        assert proof == ({'initialGate': 'rejected', 'backendCalls': 0} if already_installed else
                         {'initialExpected': 'none', 'postCheckExpected': REVISION,
                          'originalArgument': 'none', 'backendCalls': 2})


def primitive_fixture(root, already_installed):
    """All target paths below exist only inside this child mount namespace."""
    from ansible.parsing.dataloader import DataLoader
    from ansible.template import Templar
    sys.path.insert(0, str(ROOT / 'deploy'))
    import ansible_transport
    import intent_install
    import inventory as inventory_module
    spec = importlib.util.spec_from_file_location('post_bootstrap_primitive', ROOT / 'deploy/relay-deploy.py')
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    for name in ['opt', 'etc']:
        (root / name).mkdir(mode=0o755)
    for name in ['passwd', 'group', 'nsswitch.conf', 'ld.so.cache']:
        path = Path('/etc') / name
        if path.is_file():
            shutil.copyfile(path, root / 'etc' / name)
    for name in ['opt', 'etc']:
        subprocess.run(['mount', '--bind', str(root / name), '/' + name], check=True)
    config = json.loads((ROOT / 'deploy/example.json').read_text())
    config['target'].update(host='192.0.2.63', connection='local')
    config_path = root / 'desired.json'
    raw = json.dumps(config).encode()
    config_path.write_bytes(raw)
    consumer_root = root / 'consumer'
    consumer_root.mkdir()
    with patch.object(sys, 'argv', ['relay-deploy', '--phase', 'bootstrap', '--authorize-bootstrap',
            '--config', str(config_path), '--connection', 'local', '--consumer-root', str(consumer_root),
            '--resolved-revision', REVISION, '--log-root', str(root / 'logs')]):
        args = cli.arguments()
    guard = SimpleNamespace(poll=lambda: None)
    args.intent_install = True
    args.intent_expected_installed_revision = 'none'
    args.git_intent = {'config_sha256': hashlib.sha256(raw).hexdigest()}
    args._intent_host_guard = guard
    args._intent_fresh_bootstrap = True
    install = Path('/opt') / config['environment']['namespace']
    config_root = Path('/etc') / config['environment']['namespace']
    calls = []

    def publish(revision):
        release = install / 'releases' / revision
        source = release / 'reviewed-source'
        source.mkdir(parents=True)
        (source / '.relay-source.json').write_text(json.dumps({'revision': revision, 'tree': 'd' * 40}))
        (release / 'artifact-manifest.json').write_text(json.dumps({'commit': revision,
            'installedRevision': revision, 'resolvedRevision': revision, 'gitTree': 'd' * 40}))
        config_root.mkdir(parents=True, exist_ok=True)
        (config_root / 'consumer.json').write_text(json.dumps(config['consumer']))
        (config_root / 'consumer.json').chmod(0o644)
        units = Path('/etc/systemd/system')
        units.mkdir(parents=True, exist_ok=True)
        import clean_reinstall
        names = clean_reinstall.unit_names(config)
        identities = {names[2]: config['environment']['reviewerUser'],
                      **{unit: user for _, user, unit in clean_reinstall.runner_specs(config)}}
        for unit, user in identities.items():
            (units / unit).write_text('[Service]\nUser=' + user + '\n')
        (install / 'current').symlink_to(release)

    if already_installed:
        publish('b' * 40)

    def observed(*_arguments, **_options):
        current = install / 'current'
        state = ({'status': 'present', 'revision': current.resolve().name} if current.exists()
                 else {'status': 'missing'})
        return {'installed': state, 'blockers': [], 'configuration': {'consumer': 'equivalent'}}

    def archive(_root, *arguments):
        assert arguments[0] == 'archive'
        Path(next(value.removeprefix('--output=') for value in arguments if value.startswith('--output='))).touch()
        return ''

    def backend(argv, _cwd, _environment, log, held_guard, _pool_guard=None):
        assert held_guard is guard and guard.poll() is None
        hosts = json.loads(Path(argv[argv.index('-i') + 1]).read_text())['all']['children']['relay']['hosts']
        values = hosts[config['target']['host']]
        values['playbook_dir'] = str(ROOT / 'deploy/ansible')
        loader = DataLoader()
        loader.set_basedir(values['playbook_dir'])
        task = loader.load_from_file(str(ROOT / 'deploy/ansible/tasks/upgrade-preflight.yml'))[0]
        template = Templar(loader=loader, variables=values)
        command = template.template(task['ansible.builtin.command']['argv'])
        stdin = template.template(task['ansible.builtin.command']['stdin'])
        expected = values['relay_intent_expected_installed_revision']
        calls.append(expected)
        checked = subprocess.run(command, input=stdin, capture_output=True, text=True, timeout=30)
        assert checked.returncode == 0, checked.stderr + '\nexpected=' + expected
        assert checked.stdout == 'RELAY_UPGRADE_SOURCE_VALIDATED=' + expected + '\n'
        if '--check' not in argv:
            assert expected == 'none' and not (install / 'current').exists()
            publish(REVISION)
            log.write('changed=1 failed=0\nPRODUCTION_APPLY_VALIDATED=' + REVISION + '\n')
        else:
            assert values['relay_production_operation_phase'] == 'post-check'
            log.write('changed=0 failed=0\nPRODUCTION_CHECK_VALIDATED=' + REVISION
                      + ';state=stable-no-op;recovery=none\n')
        log.write('RELAY_INSTALLED_REVISION=' + REVISION + ';consumer=' + CONSUMER + ';previous=none\n')
        return 0

    with patch.object(cli, 'source_identity', return_value={'revision': REVISION, 'tree': 'd' * 40}), \
         patch.object(cli, 'clean_git', return_value=CONSUMER), patch.object(cli, 'git', side_effect=archive), \
         patch.object(cli, 'run_backend', side_effect=backend), \
         patch.object(ansible_transport, 'qualify_target'), \
         patch.object(inventory_module, 'remote_inventory', side_effect=observed), \
         patch.object(intent_install, 'prepare_target', return_value=False):
        if already_installed:
            with pytest.raises(ValueError, match='intent-installation-changed-before-reservation'):
                cli.run(args)
            assert calls == []
            print(json.dumps({'initialGate': 'rejected', 'backendCalls': 0}))
        else:
            cli.run(args)
            assert args.intent_expected_installed_revision == 'none'
            print(json.dumps({'initialExpected': calls[0], 'postCheckExpected': calls[1],
                              'originalArgument': args.intent_expected_installed_revision,
                              'backendCalls': len(calls)}))


if __name__ == '__main__' and len(sys.argv) == 4 and sys.argv[1] == '--primitive-fixture':
    primitive_fixture(Path(sys.argv[2]), sys.argv[3] == 'existing')
