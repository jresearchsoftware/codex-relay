#!/usr/bin/env python3
"""Exercise the public CLI offline without replacing its backend or transports.

This intentionally stops at an unavailable external GitHub App prerequisite;
it must never report a complete installed Apply from that refusal. Synthetic
Git repositories/configuration live only in the acknowledged TEST container.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[3]


def execute(argv, *, cwd, success=True):
    result = subprocess.run(list(map(str, argv)), cwd=cwd, capture_output=True, text=True,
                            timeout=240, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
    if success and result.returncode:
        raise AssertionError(f'Public command failed: {argv}\n{result.stdout}\n{result.stderr}')
    return result


def commit(root):
    execute(['git', 'init', '-q'], cwd=root)
    execute(['git', 'add', '--', '.'], cwd=root)
    execute(['git', '-c', 'user.name=isolated-test', '-c', 'user.email=test@example.invalid',
             'commit', '-qm', 'Synthetic isolated qualification input'], cwd=root)
    return execute(['git', 'rev-parse', 'HEAD'], cwd=root).stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--isolated-disposable-container', action='store_true', required=True)
    parser.add_argument('--namespace', default='task230-native')
    parser.add_argument('--source-root', type=Path, help='fresh exact Git clone under /qualification for final repeat')
    parser.add_argument('--expected-revision', help='required exact commit when source-root is supplied')
    parser.add_argument('--reviewer-only', action='store_true', help='disable automatic publication in this synthetic consumer')
    parser.add_argument('--test-external-prerequisites', action='store_true',
                        help='generate TEST RSA/TLS inputs for the actual public install route')
    args = parser.parse_args()
    assert re.fullmatch(r'(?:task230|t230)-[a-z0-9-]{1,14}', args.namespace)
    assert os.geteuid() == 0 and Path('/.dockerenv').exists()
    assert set(path.name for path in Path('/sys/class/net').iterdir()) == {'lo'}, 'TEST must be offline'
    root = Path(tempfile.mkdtemp(prefix='task230-public-cli-', dir='/qualification'))
    root.chmod(0o755)
    consumer = root / 'consumer'
    if args.source_root is not None:
        source = args.source_root.resolve(strict=True)
        assert source.is_relative_to(Path('/qualification')) and (source / '.git').is_dir()
        revision = execute(['git', 'rev-parse', 'HEAD'], cwd=source).stdout.strip()
        assert revision == args.expected_revision
        assert not execute(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=source).stdout
    else:
        assert args.expected_revision is None
        source = root / 'source'
        shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns('.git', 'target', 'node_modules', '__pycache__', '.pytest_cache'))
        for path in [source, *source.rglob('*')]:
            if not path.is_symlink():
                # Desktop copies do not retain Git executable-bit semantics.
                path.chmod(0o755 if path.is_dir() or path.suffix == '.sh' else 0o644)
        revision = commit(source)
    consumer.mkdir()
    config = json.loads((source / 'deploy/example.json').read_text())
    config['target'].update(host='localhost', user='root', connection='local')
    for key in ['identityFile', 'identityFingerprint']:
        config['target'].pop(key, None)
    host_key = Path('/etc/ssh/ssh_host_task230_key')
    host_key.parent.mkdir(exist_ok=True)
    if not host_key.exists():
        execute(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', host_key], cwd=root)
    config['target']['hostFingerprint'] = execute(['ssh-keygen', '-lf', str(host_key) + '.pub'], cwd=root).stdout.split()[1]
    namespace = args.namespace
    config['environment'].update(namespace=namespace, serviceUser=namespace + '-svc',
        reviewerUser=namespace + '-review', codexWorkGroup=namespace + '-work')
    config['environment']['runner'].update(user=namespace + '-prod', name=namespace + '-production')
    config['environment']['generalRunner'].update(user=namespace + '-general', name=namespace + '-pool')
    config['consumer']['runtimeUser'] = namespace + '-codex'
    config['environment']['instance']['reviewerPort'] = 10000 + int(hashlib.sha256(namespace.encode()).hexdigest()[:8], 16) % 30000
    config['environment']['reviewerBind']['mode'] = 'loopback'
    if args.reviewer_only:
        config['environment']['instance']['publicationEnabled'] = False
    if args.test_external_prerequisites:
        private = root / 'external-prerequisites'
        private.mkdir(mode=0o700)
        key, cert = private / 'app.pem', private / 'server.pem'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                        '-keyout', str(key), '-out', str(cert), '-days', '2',
                        '-subj', '/CN=reviewer.example.invalid',
                        '-addext', 'subjectAltName=DNS:reviewer.example.invalid'],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        key.chmod(0o600)
        config['environment']['reviewerCredential'] = {'sourceKeyFile': str(key)}
        config['environment']['tls'] = {'source': {'certificateFile': str(cert), 'privateKeyFile': str(key)}}
        ingress_root = root / 'external-ingress'
        ingress_root.mkdir()
        ingress_unit = namespace + '-test-ingress.service'
        config['environment']['ingress'].update(ownershipRoot=str(ingress_root), service=ingress_unit,
            protectedPaths=[str(ingress_root)], protectedServices=[ingress_unit])
        if not args.reviewer_only:
            config['environment']['writerCredential'] = {'sourceKeyFile': str(key)}
            token = private / 'codex-token'
            token.write_text('synthetic-offline-token')
            token.chmod(0o600)
            config['environment']['codexCredential'] = {'sourceTokenFile': str(token)}
    for key, value in config['consumer']['paths'].items():
        config['consumer']['paths'][key] = value.replace('codex-relay', namespace)
    config_path = consumer / 'relay.json'
    config_path.write_text(json.dumps(config))
    commit(consumer)
    command = [sys.executable, source / 'deploy/relay-deploy.py', '--config', config_path,
               '--consumer-root', consumer, '--resolved-revision', revision, '--connection', 'local',
               '--log-root', root / 'logs']
    results = {}
    for phase in ['validate', 'workflow-project']:
        options = ['--authorize-workflow-projection'] if phase == 'workflow-project' else []
        result = execute([*command, '--phase', phase, *options], cwd=source)
        results[phase] = {'exit': result.returncode}
    commit(consumer)
    for phase in ['workflow-verify', 'inventory']:
        result = execute([*command, '--phase', phase], cwd=source)
        results[phase] = {'exit': result.returncode}
        (root / (phase + '.stdout')).write_text(result.stdout)
    result = execute([*command, '--phase', 'apply'], cwd=source, success=False)
    (root / 'apply.stdout').write_text(result.stdout)
    (root / 'apply.stderr').write_text(result.stderr)
    assert result.returncode != 0, 'An offline fixture cannot authorize real GitHub App operations'
    assert 'MANAGED_POOL_OWNER_APP_KEY_UNAVAILABLE_ON_OWNER_EXECUTION_HOST' in result.stderr, result.stderr
    assert not (Path('/opt') / namespace / 'current').exists(), 'Failed prerequisite must not activate a source'
    results['apply'] = {'exit': result.returncode, 'qualified': False,
                        'limitation': 'No external GitHub installation credential/permission is supplied'}
    report = {'sourceFixtureRevision': revision, 'sourceRoot': str(source), 'syntheticSourceCommit': args.source_root is None,
              'namespace': namespace, 'artifactRoot': str(root), 'network': 'none', 'publicCli': results,
              'backendSubstituted': False, 'installationQualified': False}
    (root / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
