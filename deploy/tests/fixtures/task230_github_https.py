#!/usr/bin/env python3
"""Offline HTTPS GitHub transport fixture; never a permission qualification.

Real Python urllib, Node fetch, JWT signing, credential parsing and production
authority/recovery validation still run. Only remote responses are synthetic.
The root-owned DNS/CA/Node launcher changes apply solely to an acknowledged
disposable container. Request logs deliberately omit bodies and credentials.
"""
import argparse
import base64
import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import ssl
import subprocess
import threading
from urllib.parse import urlsplit


ROOT = Path('/qualification/github-mock')
POOL_LOCK = threading.Lock()
APPS = {
    101: ('example-writer', 201, {'metadata': 'read', 'contents': 'write', 'issues': 'write',
                               'pull_requests': 'write', 'workflows': 'write'}),
    102: ('example-reviewer', 202, {'metadata': 'read', 'actions': 'read', 'pull_requests': 'write',
                                 'checks': 'write', 'issues': 'write'}),
    103: ('example-pool', 203, {'metadata': 'read', 'organization_self_hosted_runners': 'write'}),
}


def check_container():
    assert os.geteuid() == 0 and Path('/.dockerenv').exists()
    assert set(p.name for p in Path('/sys/class/net').iterdir()) == {'lo'}


def prepare():
    ROOT.mkdir(exist_ok=True, mode=0o700)
    key, cert = ROOT / 'private.pem', ROOT / 'certificate.pem'
    assert not cert.exists(), 'Do not replace a running transport fixture'
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
        '-keyout', str(key), '-out', str(cert), '-days', '2', '-subj', '/CN=Task230OfflineTransport',
        '-addext', 'subjectAltName=DNS:api.github.com,DNS:github.com,DNS:chatgpt.com,DNS:developers.openai.com',
        '-addext', 'keyUsage=critical,digitalSignature,keyEncipherment,keyCertSign'],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    key.chmod(0o600)
    shutil.copyfile(cert, '/usr/local/share/ca-certificates/task230-offline-transport.crt')
    subprocess.run(['/usr/sbin/update-ca-certificates'], check=True, stdout=subprocess.DEVNULL)
    hosts = Path('/etc/hosts')
    assert not re.search(r'\b(?:api[.]github[.]com|github[.]com|chatgpt[.]com|developers[.]openai[.]com)\b', hosts.read_text())
    with hosts.open('a') as stream:
        stream.write('\n127.0.0.1 api.github.com github.com chatgpt.com developers.openai.com\n')
    node = Path('/usr/bin/node')
    assert node.is_symlink() and node.resolve() == Path('/usr/local/bin/node').resolve(strict=True)
    node.unlink()
    node.write_text('#!/bin/sh\nexec /usr/local/bin/node --use-system-ca "$@"\n')
    node.chmod(0o755)
    print('TASK230_TRANSPORT_PREPARED;network=none;responses=synthetic;node=real-22-system-ca')


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def pool_request(self, path, body):
        """Simulate external observations, retaining actual installer transport.

        Only the explicitly configured disposable namespace is observable. Local
        config.sh registration and real services remain independent processes;
        observing their markers here is not proof of GitHub registration.
        """
        fixture = ROOT / 'pool-config.json'
        if not fixture.exists():
            return False
        config = json.loads(fixture.read_text())
        environment, consumer = config['environment'], config['consumer']
        namespace, general = environment['namespace'], environment['generalRunner']
        assert re.fullmatch(r'(?:task230|t230)-[a-z0-9-]{1,14}', namespace)
        organization = consumer.get('repository', environment.get('repository')).split('/')[0]
        base = '/orgs/' + organization + '/actions/'
        if not path.startswith(base):
            return False
        groups = [{'id': 7, 'name': general['group']},
                  {'id': 8, 'name': environment['runner']['group']}]
        labels_file = ROOT / 'runner-labels.json'
        with POOL_LOCK:
            labels = json.loads(labels_file.read_text()) if labels_file.exists() else {}
            markers = list((Path('/opt/codex-relay-pools') / general['name'] / 'runners').glob('*/.runner'))
            markers.append(Path('/opt') / namespace / 'runner/.runner')
            runners = []
            for marker in markers:
                if marker.exists():
                    value = json.loads(marker.read_text())
                    initial = marker.with_name('.task230-labels.json')
                    names = labels.get(str(value['agentId']), json.loads(initial.read_text()) if initial.exists() else [])
                    runners.append({'id': value['agentId'], 'name': value['agentName'],
                        'busy': False, 'status': 'online', 'group': value['poolName'],
                        'labels': [{'name': name, 'type': 'custom'} for name in names]})
            if self.command == 'PUT' and re.fullmatch(re.escape(base) + r'runners/[0-9]+/labels', path):
                identity = path.split('/')[-2]
                labels[identity] = body['labels']
                labels_file.write_text(json.dumps(labels))
                self.respond({'labels': [{'name': name, 'type': 'custom'} for name in body['labels']]})
                return True
        if self.command == 'POST' and path in [base + 'runners/registration-token', base + 'runners/remove-token']:
            self.respond({'token': 'synthetic-offline-runner-token'})
            return True
        if self.command != 'GET':
            return False
        if path == base + 'runners':
            self.respond({'total_count': len(runners), 'runners': runners})
            return True
        if path == base + 'runner-groups':
            self.respond({'total_count': len(groups), 'runner_groups': groups})
            return True
        match = re.fullmatch(re.escape(base) + r'runner-groups/(7|8)(?:/(repositories|runners))?', path)
        if not match:
            return False
        group = groups[int(match[1]) - 7]
        if match[2] == 'runners':
            members = [runner for runner in runners if runner['group'] == group['name']]
            self.respond({'total_count': len(members), 'runners': members})
        elif match[2] == 'repositories':
            repositories = consumer.get('repositories', [consumer.get('repository')])
            self.respond({'total_count': len(repositories),
                          'repositories': [{'full_name': name} for name in repositories]})
        else:
            repositories = consumer.get('repositories', [consumer.get('repository')])
            workflows = [repository + '/' + consumer[key] + '@refs/heads/' + consumer['baseBranch']
                         for repository in repositories for key in ['routingWorkflow', 'recoveryWorkflow']]
            self.respond({**group, 'visibility': 'selected', 'restricted_to_workflows': True,
                          'selected_workflows': workflows})
        return True

    def handle_request(self):
        path = urlsplit(self.path).path
        with (ROOT / 'requests.log').open('a') as stream:
            stream.write(self.command + ' ' + path + '\n')
        length = int(self.headers.get('Content-Length', '0'))
        assert length <= 1024 * 1024
        raw = self.rfile.read(length) if length else b''
        body = json.loads(raw) if raw else {}
        token = self.headers.get('Authorization', '').removeprefix('Bearer ')
        app_id = 101
        try:
            if token.count('.') == 2:
                payload = token.split('.')[1]
                app_id = int(json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))['iss'])
            elif token.startswith('synthetic-app-'):
                app_id = int(token.removeprefix('synthetic-app-'))
        except (ValueError, KeyError, TypeError):
            return self.respond({'message': 'invalid synthetic transport credential'}, 401)
        if app_id not in APPS:
            return self.respond({'message': 'unknown synthetic App'}, 403)
        slug, installation, permissions = APPS[app_id]
        install = {'id': installation, 'app_id': app_id, 'app_slug': slug,
            'account': {'login': 'example-org', 'type': 'Organization'},
            'permissions': permissions, 'repository_selection': 'selected'}
        if self.command == 'GET' and path == '/app':
            return self.respond({'id': app_id, 'slug': slug})
        if self.command == 'GET' and path == '/app/installations/' + str(installation):
            return self.respond(install)
        if self.command == 'GET' and path == '/repos/example-org/sample-project/installation':
            return self.respond(install)
        if self.command == 'POST' and path == '/app/installations/' + str(installation) + '/access_tokens':
            expiry = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=45)
            return self.respond({'token': 'synthetic-app-' + str(app_id),
                'expires_at': expiry.isoformat(), 'permissions': body.get('permissions', {'metadata': 'read'})})
        if self.command == 'GET' and path == '/repos/example-org/sample-project':
            return self.respond({'id': 500, 'full_name': 'example-org/sample-project', 'private': False})
        selected = ROOT / 'active.json'
        routes = json.loads(selected.read_text()) if selected.exists() else {}
        key = self.command + ' ' + path
        if key in routes:
            return self.respond(routes[key])
        if self.pool_request(path, body):
            return
        if self.command == 'GET' and re.fullmatch(
                r'/actions/runner/releases/download/v[0-9]+[.][0-9]+[.][0-9]+/actions-runner-linux-x64-[0-9]+[.][0-9]+[.][0-9]+[.]tar[.]gz',
                path):
            archive = ROOT / path.rsplit('/', 1)[-1]
            if archive.is_file():
                return self.respond(archive.read_bytes(), content_type='application/gzip')
        if self.command == 'GET' and path == '/codex/install.sh':
            installer = ROOT / 'codex-install.sh'
            if installer.is_file():
                return self.respond(installer.read_bytes(), content_type='text/x-shellscript')
        if self.command == 'GET' and path.startswith('/plugins/mtls/'):
            ca = ROOT / path.rsplit('/', 1)[-1]
            if ca.is_file():
                return self.respond(ca.read_bytes(), content_type='application/x-pem-file')
        return self.respond({'message': 'unconfigured offline fixture response'}, 404)

    def respond(self, value, status=200, content_type='application/json'):
        data = value if isinstance(value, bytes) else json.dumps(value).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = handle_request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--isolated-disposable-container', action='store_true', required=True)
    parser.add_argument('--prepare', action='store_true')
    args = parser.parse_args()
    check_container()
    if args.prepare:
        return prepare()
    server = ThreadingHTTPServer(('127.0.0.1', 443), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(ROOT / 'certificate.pem', ROOT / 'private.pem')
    server.socket = context.wrap_socket(server.socket, server_side=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
