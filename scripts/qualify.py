#!/usr/bin/env python3
"""Credential-free qualification of one unchanged Relay candidate for three consumers."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import socket
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RUST = ROOT / 'reviewer'


def source_digest():
    files = [p for component in ('controller', 'runtime', 'contracts') for p in (ROOT / component / 'src').rglob('*')]
    files += list((ROOT / 'consumer').glob('*.mjs'))
    files += list((RUST / 'src').rglob('*')) + [RUST / 'Cargo.toml', RUST / 'Cargo.lock']
    digest = hashlib.sha256()
    for path in sorted(p for p in files if p.is_file()):
        digest.update(str(path.relative_to(ROOT)).encode() + b'\0' + path.read_bytes() + b'\0')
    return digest.hexdigest()


def build(command, test):
    built = subprocess.run(['cargo', command, '--locked', *(['--no-run'] if test else []), '--message-format=json'],
                           cwd=RUST, text=True, stdout=subprocess.PIPE, check=True)
    artifacts = [json.loads(line) for line in built.stdout.splitlines() if line.startswith('{')]
    executables = [Path(a['executable']) for a in artifacts
                   if a.get('reason') == 'compiler-artifact' and a.get('executable') and bool(a.get('profile', {}).get('test')) == test]
    if len(executables) != 1:
        raise RuntimeError('Reviewer artifact is ambiguous')
    return executables[0]


def qualify_binary(executable):
    # The actual production binary uses its full certificate verification.
    # All keys, trust, config and databases here are generated temporary fixtures.
    with tempfile.TemporaryDirectory(prefix='relay-consumers-') as directory:
        root = Path(directory)
        def openssl(*args):
            subprocess.run(['openssl', *args], cwd=root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        openssl('req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', 'ca.key', '-out', 'ca.pem',
                '-subj', '/CN=Isolated relay fixture CA', '-days', '1', '-addext', 'basicConstraints=critical,CA:TRUE')
        openssl('req', '-newkey', 'rsa:2048', '-nodes', '-keyout', 'leaf.key', '-out', 'leaf.csr', '-subj', '/CN=Isolated fixture')
        (root / 'leaf.ext').write_text('subjectAltName=DNS:mtls.prod.connectors.openai.com\nextendedKeyUsage=clientAuth\n')
        openssl('x509', '-req', '-in', 'leaf.csr', '-CA', 'ca.pem', '-CAkey', 'ca.key', '-CAcreateserial',
                '-out', 'leaf.pem', '-days', '1', '-extfile', 'leaf.ext')
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream',
                   'X-OpenAI-MTLS-Verified': '1',
                   'X-OpenAI-MTLS-Client-Cert': urllib.parse.quote((root / 'leaf.pem').read_text(), safe='')}
        for consumer in ['example', 'canary', 'inventory']:
            c = json.loads((ROOT / f'consumer/fixtures/{consumer}.json').read_text())
            with socket.socket() as reserve:
                reserve.bind(('127.0.0.1', 0))
                port = reserve.getsockname()[1]
            config = {'repository': c['repository'], 'baseBranch': c['baseBranch'],
                      'reviewCheckName': f'{consumer}-review', 'writerActor': c['writerApp']['expectedActor'],
                      'githubApp': c['reviewerApp'], 'validationNames': c.get('validationNames', []), 'artifact': {'commit': 'a' * 40, 'sha256': 'b' * 64},
                      'service': {'name': 'reviewer-mcp', 'bind_mode': 'a_only_loopback', 'bind_address': '127.0.0.1',
                                  'bind_network': '', 'gateway_validated': False, 'bind_port': port, 'mount_path': '/mcp'}}
            path = root / f'{consumer}.json'
            path.write_text(json.dumps(config))
            env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'REVIEWER_RELAY_ENABLED': 'false',
                   'REVIEWER_RELAY_DB': str(root / f'{consumer}.sqlite3'), 'REVIEWER_CLIENT_CA_FILE': str(root / 'ca.pem'),
                   'GITHUB_APP_ID': c['reviewerApp']['appId'], 'GITHUB_APP_INSTALLATION_ID': c['reviewerApp']['installationId']}
            process = subprocess.Popen([str(executable), '--config', str(path)], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            def rpc(method, params, supplied_headers=headers):
                request = urllib.request.Request(f'http://127.0.0.1:{port}/mcp',
                    data=json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}).encode(), headers=supplied_headers)
                with urllib.request.urlopen(request, timeout=2) as response:
                    return json.load(response)
            try:
                for _ in range(50):
                    if process.poll() is not None:
                        raise RuntimeError('Reviewer fixture failed to start')
                    try:
                        listed = rpc('tools/list', {})
                        break
                    except urllib.error.URLError:
                        time.sleep(.1)
                else:
                    raise RuntimeError('Reviewer fixture did not become ready')
                for tool in listed['result']['tools']:
                    assert tool['inputSchema']['properties']['repository']['const'] == c['repository']
                choices = listed['result']['tools'][1]['inputSchema']['properties']['change_request']['properties']['required_validation']['items']['enum']
                assert all(name in choices for name in c.get('validationNames', []))
                disabled = rpc('tools/call', {'name': 'submit_pr_review', 'arguments': {
                    'repository': c['repository'], 'pr_number': 1, 'expected_head_sha': 'a' * 40,
                    'action': 'APPROVE', 'review_body': 'Synthetic disabled-publication probe.'}})
                assert disabled['result']['content'][0]['text'] == 'RELAY_DISABLED'
                try:
                    rpc('tools/list', {}, {'Content-Type': 'application/json'})
                except urllib.error.HTTPError as error:
                    assert error.code == 403
                else:
                    raise RuntimeError('Reviewer accepted missing client identity')
                wrong = rpc('tools/call', {'name': 'check_pr_review_target', 'arguments':
                    {'repository': 'foreign/repository', 'pr_number': 1, 'expected_head_sha': 'a' * 40}})
                assert 'error' in wrong or wrong.get('result', {}).get('isError') is True
            finally:
                process.terminate()
                try:
                    stdout, stderr = process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    stdout, stderr = process.communicate()
                assert b'publication_mode' in stdout and b'false' in stdout


def main():
    before = source_digest()
    production = build('build', False)
    production_hash = hashlib.sha256(production.read_bytes()).hexdigest()
    qualify_binary(production)
    # Build the test executable once: real Reviewer handlers and GitHub client,
    # with loopback-only GitHub fixtures and generated ephemeral mTLS identities.
    executable = build('test', True)
    artifact_hash = hashlib.sha256(executable.read_bytes()).hexdigest()
    subprocess.run([str(executable), 'two_consumer_same_artifact', '--nocapture'], cwd=RUST, check=True)
    for consumer in ['example', 'canary', 'inventory']:
        env = {**os.environ, 'RELAY_CONSUMER_CONFIG': str(ROOT / f'consumer/fixtures/{consumer}.json')}
        subprocess.run(['node', '--test', 'consumer/test/portability.test.mjs'], cwd=ROOT, env=env, check=True)
    if (source_digest() != before or hashlib.sha256(executable.read_bytes()).hexdigest() != artifact_hash
            or hashlib.sha256(production.read_bytes()).hexdigest() != production_hash):
        raise RuntimeError('Qualification candidate changed')
    print(json.dumps({'qualification': 'THREE_CONSUMER_PASS', 'sourceSha256': before,
                      'reviewerArtifactSha256': production_hash, 'reviewerTestArtifactSha256': artifact_hash,
                      'consumers': ['example-org/sample-project', 'harmless-lab/relay-canary', 'sample-co/inventory-api'],
                      'scope': 'real handlers/modules; isolated Git and loopback mock GitHub; no production deployment, production credentials or model calls'}))


if __name__ == '__main__':
    main()
