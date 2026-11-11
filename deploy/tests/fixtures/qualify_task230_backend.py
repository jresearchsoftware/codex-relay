#!/usr/bin/env python3
"""Run the public installer with real Ansible/systemd and offline TEST inputs.

Only external GitHub pool permission/registration observations and the external
Runner/Codex distributions are synthetic. The installer, artifact build, local
pool reconciliation, filesystem checks and services execute production code.
"""
import argparse
import fcntl
import grp
import hashlib
import io
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tarfile

sys.dont_write_bytecode = True


def prepare(root, source):
    root.chmod(0o755)
    defaults = __import__('yaml').safe_load((source / 'deploy/ansible/group_vars/all.yml').read_text())
    version = defaults['relay_runner_package_version']
    archive = root / 'synthetic-runner.tar.gz'
    config = '''#!/usr/bin/python3
import json,os,sys
from pathlib import Path
args=sys.argv[1:]
if args and args[0]=='remove':
 for name in ['.runner','.credentials']:Path(name).unlink(missing_ok=True)
else:
 def arg(name):return args[args.index(name)+1]
 name=arg('--name');identity=100+int(name.rsplit('-',1)[-1]) if name.rsplit('-',1)[-1].isdigit() else 101
 value={'agentName':name,'agentId':identity,'gitHubUrl':arg('--url'),'poolName':arg('--runnergroup'),'workFolder':arg('--work')}
 for path,data in [('.runner',json.dumps(value)),('.credentials','synthetic-offline-registration')]:
  Path(path).write_text(data);Path(path).chmod(0o600)
'''
    payloads = {'config.sh': config, 'run.sh': '#!/bin/sh\nwhile :; do sleep 1; done\n',
                'bin/Runner.Listener': '#!/bin/sh\nprintf "' + version + '\\n"\n',
                'externals/node24/bin/node': '#!/bin/sh\nexec /usr/bin/node "$@"\n'}
    with tarfile.open(archive, 'w:gz') as tar:
        entry = tarfile.TarInfo('./'); entry.type = tarfile.DIRTYPE; entry.mode = 0o755; tar.addfile(entry)
        for name, content in payloads.items():
            raw = content.encode(); entry = tarfile.TarInfo(name)
            entry.mode, entry.size = 0o755, len(raw); tar.addfile(entry, io.BytesIO(raw))
    mock_root = Path('/qualification/github-mock')
    mock_root.mkdir(exist_ok=True, mode=0o700)
    mock_archive = mock_root / f"actions-runner-{defaults['relay_runner_package_platform']}-{version}.tar.gz"
    assert not mock_archive.exists(), 'Do not replace a running transport fixture'
    shutil.copyfile(archive, mock_archive)
    mock_archive.chmod(0o600)
    mock_installer = mock_root / 'codex-install.sh'
    assert not mock_installer.exists(), 'Do not replace a running transport fixture'
    shutil.copyfile(source / 'deploy/ansible/tests/fake-codex-installer.sh', mock_installer)
    mock_installer.chmod(0o600)
    for name in ['fake-installed-codex.mjs', 'rust-development-probe.mjs']:
        shutil.copyfile(source / 'deploy/ansible/tests' / name, Path('/run') / name)
    variables = {'relay_manage_base_packages': False,
        'relay_rust_toolchain_root': '/qualification/toolchains/rust-1.90.0',
        'relay_rust_toolchain_cargo_home': '/qualification/cargo-home',
        'relay_runner_package_archive': str(archive),
        'relay_runner_package_sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}
    inputs = root / 'test-prerequisites.json'
    inputs.write_text(json.dumps(variables))
    directory = root / 'bin'; directory.mkdir(exist_ok=True)
    wrapper = directory / 'ansible-playbook'
    wrapper.write_text('#!/usr/bin/python3\nimport os,sys\nsys.dont_write_bytecode=True\n'
        + 'extra=' + repr(str(inputs)) + '\n'
        + 'os.environ["CARGO_NET_OFFLINE"]="true"\n'
        + 'os.execv("/usr/bin/ansible-playbook", ["/usr/bin/ansible-playbook", *sys.argv[1:], "--extra-vars", "@"+extra])\n')
    wrapper.chmod(0o755)
    os.environ['PATH'] = str(directory) + ':/usr/bin:/bin'
    config = json.loads((root / 'consumer/relay.json').read_text())
    namespace = config['environment']['namespace']
    unit = config['environment']['ingress']['service']
    if unit == namespace + '-test-ingress.service':
        # An external prerequisite, deliberately synthetic; Relay services and
        # the production backend remain unchanged. Preserve this real process.
        port = 41000 + int(hashlib.sha256(namespace.encode()).hexdigest()[:8], 16) % 2000
        path = Path('/etc/systemd/system') / unit
        assert not path.exists(), 'Do not replace a prior external prerequisite'
        path.write_text('[Unit]\nDescription=Task230 synthetic external ingress prerequisite\n'
            '[Service]\nUser=nobody\nGroup=nogroup\nExecStart=/usr/bin/python3 -m http.server '
            + str(port) + ' --bind 127.0.0.1 --directory ' + str(root / 'external-ingress')
            + '\n[Install]\nWantedBy=multi-user.target\n')
        path.chmod(0o644)
        subprocess.run(['systemctl', 'daemon-reload'], check=True)
        subprocess.run(['systemctl', 'start', unit], check=True)
        observed = subprocess.check_output(['systemctl', 'show', unit,
            '-p', 'MainPID', '-p', 'ExecMainStartTimestampMonotonic'], text=True)
        (root / 'external-ingress-before.txt').write_text(observed)


def seed_codex(root, source):
    """Supply a normalized synthetic distribution as an existing prerequisite.

    The unchanged product pin still requires the official HTTPS installer URL.
    Preseeding the external distribution keeps its downloader entirely skipped.
    """
    config = json.loads((root / 'consumer/relay.json').read_text())
    namespace = config['environment']['namespace']
    assert namespace.startswith(('t230-', 'task230-'))
    runtime = Path('/opt') / namespace / 'codex-runtime'
    home, packages, binary = runtime / 'package-home', runtime / 'package-bin', runtime / 'bin/codex'
    if not binary.exists():
        home.mkdir(parents=True, exist_ok=True, mode=0o700)
        home.chmod(0o700)
        packages.mkdir(exist_ok=True, mode=0o700)
        subprocess.run(['/bin/sh', str(source / 'deploy/ansible/tests/fake-codex-installer.sh'),
                        '--release', '0.167.0'], check=True,
                       env={'PATH': '/usr/bin:/bin', 'HOME': str(home), 'CODEX_HOME': str(home),
                            'CODEX_INSTALL_DIR': str(packages)})
        guard = source / 'deploy/ansible/roles/relay_codex_runtime/files/relay-codex-package-guard.py'
        subprocess.run(['/usr/bin/python3', str(guard), str(home), str(packages / 'codex'),
                        '0.167.0', 'normalize'], check=True)
        binary.parent.mkdir(exist_ok=True)
        binary.symlink_to((packages / 'codex').resolve(strict=True))


def seed_predispatch(root, source):
    """Add only synthetic no-worker history for the real subsequent upgrade."""
    config = json.loads((root / 'consumer/relay.json').read_text())
    consumer_path = '/etc/' + config['environment']['namespace'] + '/consumer.json'
    installed = json.loads(Path(consumer_path).read_text())
    program = """import {currentEnvelope} from './controller/test/fixture.mjs';
      import {CONSUMER} from './consumer/consumer.mjs';
      import {createPublicationStore} from './controller/src/attempt-store.mjs';
      import {pendingPredispatchRecord} from './controller/src/predispatch-recovery.mjs';
      const store=createPublicationStore(CONSUMER.paths.claimRoot+'/publication-v2');
      const envelope=currentEnvelope({runId:990099,step:2,transport:'label',executionSlot:'primary',
        readyEventId:71,readyLabel:'codex-ready-auto',readyEventAt:'2026-09-04T12:00:00Z'});
      const record={envelope,nativeAdmission:true,stepProjectionFrom:['step-1'],
        predispatchPending:{version:1,projectionFrom:['step-1']},
        controllerLifecycle:{version:1,status:'active'},publicationIntent:null,
        publishedHead:null,finalHead:null,outcome:null};
      if(!pendingPredispatchRecord(record))throw Error('Synthetic pending record is invalid');
      if(!await store.reserve(990099,record))throw Error('Do not replace existing synthetic history');
      console.log(CONSUMER.paths.claimRoot+'/publication-v2/990099.json');"""
    result = subprocess.run(['/usr/bin/flock', '-w', '5', installed['paths']['claimRoot'] + '/publication-v2.lock',
        '/usr/bin/node', '--input-type=module', '-e', program],
        cwd=source, env={'PATH': '/usr/bin:/bin', 'RELAY_CONSUMER_CONFIG': consumer_path},
        check=True, capture_output=True, text=True)
    path = Path(result.stdout.strip())
    before = path.read_bytes()
    (root / 'predispatch-record-before.json').write_bytes(before)
    return path, before


def seed_reviewer_credential(root):
    """Create a TEST-only RSA App key; actual readiness/start gates stay real."""
    config = json.loads((root / 'consumer/relay.json').read_text())
    namespace = config['environment']['namespace']
    assert namespace.startswith(('t230-', 'task230-'))
    directory = Path('/etc') / namespace / 'reviewer-credentials'
    assert directory.is_dir() and not directory.is_symlink()
    group = grp.getgrnam(config['environment']['reviewerUser']).gr_gid
    key = directory / 'github-app-private-key.pem'
    if not key.exists():
        subprocess.run(['/usr/bin/openssl', 'genpkey', '-algorithm', 'RSA', '-pkeyopt',
                        'rsa_keygen_bits:2048', '-out', str(key)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    environment = directory / 'github-app.env'
    app = config['consumer']['reviewerApp']
    environment.write_text('GITHUB_APP_ID=' + app['appId'] + '\nGITHUB_APP_INSTALLATION_ID='
        + app['installationId'] + '\nGITHUB_APP_PRIVATE_KEY_FILE=' + str(key) + '\n')
    for path in [key, environment]:
        os.chown(path, 0, group)
        path.chmod(0o640)
    certificate = Path('/etc') / namespace / 'certs/openai-client-ca.pem'
    if not certificate.exists():
        private = root / 'synthetic-ca'
        private.mkdir(exist_ok=True, mode=0o700)
        subprocess.run(['/usr/bin/openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
            '-keyout', str(private / 'key.pem'), '-out', str(certificate),
            '-subj', '/CN=Task230IsolatedTestCA', '-days', '2'], check=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        (private / 'key.pem').chmod(0o600)
    os.chown(certificate, 0, group)
    certificate.chmod(0o640)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--isolated-disposable-container', action='store_true', required=True)
    parser.add_argument('--fixture-root', required=True, type=Path)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--seed-predispatch-marker', action='store_true')
    parser.add_argument('--seed-reviewer-credential', action='store_true')
    parser.add_argument('--reconcile-pool-only', action='store_true',
                        help='finish only this TEST pool using actual State/Host/reconcile and synthetic remote observations')
    args, public_arguments = parser.parse_known_args()
    assert os.geteuid() == 0 and Path('/.dockerenv').exists()
    assert set(path.name for path in Path('/sys/class/net').iterdir()) == {'lo'}
    root = args.fixture_root.resolve(strict=True)
    assert root.parent == Path('/qualification') and root.name.startswith('task230-public-cli-')
    report = json.loads((root / 'report.json').read_text())
    source = Path(report.get('sourceRoot', str(root / 'source'))).resolve(strict=True)
    assert source.is_relative_to(Path('/qualification'))
    if args.prepare:
        prepare(root, source)
    else:
        os.environ['PATH'] = str(root / 'bin') + ':/usr/bin:/bin'
    config_namespace = json.loads((root / 'consumer/relay.json').read_text())['environment']['namespace']
    if not args.prepare and not args.reconcile_pool_only and '--phase' in public_arguments:
        phase_index = public_arguments.index('--phase')
        phase = public_arguments[phase_index + 1] if phase_index + 1 < len(public_arguments) else None
        if phase in {'install', 'apply', 'upgrade', 'bootstrap', 'reinstall', 'activate'} and (
                Path('/opt') / config_namespace / 'current').exists():
            # Seed only before a distinct public operation, so preflight sees
            # the TEST package before it snapshots the retained installation.
            seed_codex(root, source)
    certificate = root / 'external-prerequisites/server.pem'
    if certificate.exists():
        trust = Path('/usr/local/share/ca-certificates') / (config_namespace + '-test-server.crt')
        if not trust.exists():
            shutil.copyfile(certificate, trust)
            subprocess.run(['/usr/sbin/update-ca-certificates'], check=True, stdout=subprocess.DEVNULL)
    if (Path('/opt') / config_namespace / 'current').exists():
        seed_codex(root, source)
    if args.seed_reviewer_credential:
        seed_reviewer_credential(root)
    marker = seed_predispatch(root, source) if args.seed_predispatch_marker else None
    sys.path.insert(0, str(source / 'deploy'))
    import managed_pool as pool
    import managed_pool_transport as transport

    class SyntheticGitHub:
        def __init__(self, contract): self.contract, self.updated = contract, {}
        def qualify(self, contract):
            assert contract == self.contract
            return 7
        def runners(self):
            result = []
            for member in self.contract['members']:
                path = Path(member['root']) / '.runner'
                if path.exists():
                    value = json.loads(path.read_text())
                    labels = self.updated.get(value['agentId'], [])
                    result.append({'id': value['agentId'], 'name': value['agentName'],
                        'busy': False, 'status': 'online', 'labels': [{'name': name, 'type': 'custom'} for name in labels]})
            return result
        def in_group(self, group, runner): return group == 7
        def ephemeral(self, purpose): return 'synthetic-offline-' + purpose
        def labels(self, runner, labels): self.updated[runner] = labels

    def preflight(*_args, **_kwargs):
        return 'MANAGED_POOL_PREFLIGHT=PASS'

    def reconcile(_target, _key, config, revision, *_args, **_kwargs):
        contract = pool.pool_contract(config)
        # Defer synthetic external registration until the real separately
        # authorized activation has made Reviewer ready. Keep product guards.
        host = pool.Host(contract)
        host.command([contract['readiness']])
        state = pool.State(Path('/var/lib/codex-relay-pools') / contract['name'])
        lock = os.open(state.root / 'pool.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX)
            report = pool.reconcile(contract, state, SyntheticGitHub(contract), host)
        finally:
            os.close(lock)
        return 'MANAGED_POOL_RESULT=' + json.dumps(report)

    transport.preflight_pool, transport.reconcile_pool = preflight, reconcile
    if args.reconcile_pool_only:
        assert not public_arguments and marker is None
        sys.path.insert(0, str(source / 'deploy'))
        from config import load
        config = load(root / 'consumer/relay.json', source)
        print(reconcile(None, None, config, report['sourceFixtureRevision']), flush=True)
        return
    sys.argv = [str(source / 'deploy/relay-deploy.py'), *public_arguments]
    try:
        runpy.run_path(sys.argv[0], run_name='__main__')
    except SystemExit as result:
        if marker is not None and result.code in [None, 0]:
            assert marker[0].read_bytes() == marker[1], 'Upgrade changed immutable pre-dispatch history'
            print('TASK230_PREDISPATCH_HISTORY_PRESERVED=' + hashlib.sha256(marker[1]).hexdigest(), flush=True)
        raise


if __name__ == '__main__':
    main()
