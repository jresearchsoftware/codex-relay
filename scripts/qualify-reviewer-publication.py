#!/usr/bin/env python3
"""Exercise an explicitly synthetic Reviewer installation against loopback GitHub.

The feature-built executable uses real main/configuration, RSA signing, forwarded
mTLS verification, HTTP handlers and persistent state. All identities, keys,
native records and installation paths are disposable fixtures. No live GitHub,
root installation, systemd, existing consumer or model is used.
"""
import argparse
import base64
import concurrent.futures
import copy
import hashlib
import http.server
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = 'example-org/sample-project'
HEAD = 'a' * 40
OWNER = {'login': 'example-owner', 'id': 1, 'type': 'User'}
REVIEWER = {'login': 'example-reviewer[bot]', 'id': 2, 'type': 'Bot'}
WRITER = {'login': 'example-writer[bot]', 'id': 3, 'type': 'Bot'}
APP = {'slug': 'example-reviewer', 'id': 102}
CHARTER = ('Task 24: verify a bounded result.\nAuthority model: github-native-v1\n'
           'Issue closure policy: keep-open\nNo production mutation.')


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def free_port():
    with socket.socket() as reserve:
        reserve.bind(('127.0.0.1', 0))
        return reserve.getsockname()[1]


def make_crypto(root):
    def openssl(*args):
        subprocess.run(['openssl', *args], cwd=root, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    openssl('req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', 'ca.key',
            '-out', 'ca.pem', '-subj', '/CN=Disposable Reviewer fixture CA', '-days', '1',
            '-addext', 'basicConstraints=critical,CA:TRUE')
    openssl('req', '-newkey', 'rsa:2048', '-nodes', '-keyout', 'client.key',
            '-out', 'client.csr', '-subj', '/CN=Disposable connector')
    (root / 'client.ext').write_text('subjectAltName=DNS:mtls.prod.connectors.openai.com\n'
                                   'extendedKeyUsage=clientAuth\n')
    openssl('x509', '-req', '-in', 'client.csr', '-CA', 'ca.pem', '-CAkey', 'ca.key',
            '-CAcreateserial', '-out', 'client.pem', '-days', '1', '-extfile', 'client.ext')
    openssl('genpkey', '-algorithm', 'RSA', '-pkeyopt', 'rsa_keygen_bits:2048',
            '-out', 'fake-app.pem')
    for name in ['ca.key', 'client.key', 'fake-app.pem']:
        (root / name).chmod(0o600)


class Github:
    def __init__(self, fault='normal'):
        self.lock = threading.RLock()
        self.requests = []
        self.reviews = {}
        self.checks = []
        self.comments = []
        self.fault = fault
        self.fired = False
        self.fail_token = False
        self.accepted = threading.Event()
        self.release = threading.Event()
        self.prs = {number: self.pr(number, task) for number, task in [(25, 24), (27, 26)]}
        self.issues = {task: self.issue(task) for task in [24, 26]}

    @staticmethod
    def issue(task):
        return {'id': task * 10, 'number': task, 'state': 'open',
                'body': CHARTER if task == 24 else CHARTER.replace('Task 24', f'Task {task}'),
                'repository_url': f'https://api.github.com/repos/{REPOSITORY}',
                'user': OWNER, 'labels': [{'name': 'step-1'}, {'name': 'task'}]}

    @staticmethod
    def pr(number, task):
        return {'id': number * 10, 'number': number, 'state': 'open', 'draft': False,
                'merged': False, 'labels': [{'name': 'step-1'}], 'body': f'Related to #{task}',
                'title': f'Task {task} · Step 1 · Implementation',
                'base': {'ref': 'main', 'sha': 'b' * 40, 'repo': {'full_name': REPOSITORY}},
                'head': {'sha': HEAD, 'ref': f'codex/task-{task}', 'repo': {'full_name': REPOSITORY}},
                'user': {'login': 'author'}}

    def count(self, suffix):
        with self.lock:
            return sum(method == 'POST' and path.endswith(suffix) for method, path in self.requests)

    def route(self, method, url, body, authorization):
        path = urllib.parse.unquote(urllib.parse.urlsplit(url).path)
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        with self.lock:
            self.requests.append((method, path))
            if path == '/app' or path == '/app/installations/202/access_tokens':
                try:
                    token = authorization.removeprefix('Bearer ')
                    encoded = token.split('.')[1]
                    claims = json.loads(base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)))
                    assert str(claims['iss']) == '102' and claims['exp'] > time.time()
                except (ValueError, IndexError, KeyError, AssertionError):
                    return 401, {}, None
                if path == '/app':
                    return 200, APP, None
                if self.fail_token:
                    self.fail_token = False
                    return 403, {}, None
                assert body['repositories'] == ['sample-project']
                return 201, {'token': 'disposable-installation-token',
                             'expires_at': '2099-01-01T00:00:00Z'}, None
            if authorization != 'Bearer disposable-installation-token':
                return 401, {}, None
            if path.startswith('/users/'):
                identities = {user['login']: user for user in [OWNER, REVIEWER, WRITER]}
                return 200, identities.get(path.removeprefix('/users/'), {}), None
            prefix = f'/repos/{REPOSITORY}/'
            if not path.startswith(prefix):
                return 404, {}, None
            relative = path.removeprefix(prefix)
            parts = relative.split('/')
            if method == 'GET' and parts[0] == 'pulls' and len(parts) == 2:
                return 200, self.prs[int(parts[1])], None
            if method == 'GET' and parts[0] == 'issues' and len(parts) == 2 and parts[1].isdigit():
                return 200, self.issues[int(parts[1])], None
            if parts[0] == 'pulls' and len(parts) >= 3 and parts[2] == 'reviews':
                number = int(parts[1])
                reviews = self.reviews.setdefault(number, [])
                if method == 'GET':
                    if len(parts) == 4:
                        return 200, next(review for review in reviews if review['id'] == int(parts[3])), None
                    return 200, self.page(reviews, query), None
                if method == 'POST':
                    review_id = sum(len(items) for items in self.reviews.values()) + 1
                    native = {'id': review_id, 'body': body['body'], 'commit_id': body['commit_id'],
                              'state': 'APPROVED' if body['event'] == 'APPROVE' else 'CHANGES_REQUESTED',
                              'user': REVIEWER, 'pull_request_url': f'https://api.github.com/repos/{REPOSITORY}/pulls/{number}',
                              'html_url': f'https://github.com/{REPOSITORY}/pull/{number}#pullrequestreview-{review_id}'}
                    reviews.append(native)
                    if self.fault == 'crash-review' and not self.fired:
                        self.fired = True
                        self.accepted.set()
                        return 201, native, 'hold'
                    return 201, native, None
            if method == 'GET' and relative.startswith('commits/') and relative.endswith('/check-runs'):
                assert query.get('filter') == ['all']
                if self.fault == 'token-before-check' and not self.fired:
                    self.fired, self.fail_token = True, True
                checks = self.checks
                if self.fault == 'delayed-check' and self.count('/check-runs') < 2:
                    checks = []
                return 200, {'total_count': len(checks), 'check_runs': self.page(checks, query)}, None
            if method == 'POST' and relative == 'check-runs':
                if self.fault == 'reject-check' and not self.fired:
                    self.fired = True
                    return 422, {}, None
                if self.fault == 'missing-checks':
                    return 503, {}, 'drop'
                check = {**body, 'id': len(self.checks) + 1, 'app': APP,
                         'html_url': f'https://github.com/{REPOSITORY}/runs/{len(self.checks) + 1}'}
                check['output'] = {**check['output'], 'annotations_count': 0,
                    'annotations_url': f'https://api.github.com/repos/{REPOSITORY}/check-runs/{check["id"]}/annotations'}
                self.checks.append(check)
                if self.fault in ['lost-check', 'delayed-check'] and not self.fired:
                    self.fired = True
                    return 201, check, 'drop'
                return 201, check, None
            if method == 'GET' and relative.startswith('check-runs/'):
                return 200, next(check for check in self.checks if check['id'] == int(parts[1])), None
            if relative.startswith('issues/') and relative.endswith('/comments'):
                number = int(parts[1])
                if method == 'GET':
                    return 200, self.page([comment for comment in self.comments if comment['parent'] == number], query), None
                comment_id = len(self.comments) + 1000
                native = {'id': comment_id, 'body': body['body'], 'user': REVIEWER, 'parent': number,
                          'issue_url': f'https://api.github.com/repos/{REPOSITORY}/issues/{number}',
                          'html_url': f'https://github.com/{REPOSITORY}/issues/{number}#issuecomment-{comment_id}'}
                self.comments.append(native)
                return 201, native, None
            if method == 'GET' and relative.startswith('issues/comments/'):
                return 200, next(comment for comment in self.comments if comment['id'] == int(parts[2])), None
            if method == 'GET' and relative.startswith('labels/'):
                return 200, {'name': parts[1]}, None
            if method == 'PUT' and relative.endswith('/labels'):
                target = self.issues.get(int(parts[1]), self.prs.get(int(parts[1])))
                target['labels'] = [{'name': label} for label in body['labels']]
                return 200, target['labels'], None
            if method == 'PATCH' and parts[0] == 'pulls':
                self.prs[int(parts[1])].update(body)
                return 200, self.prs[int(parts[1])], None
            return 404, {}, None

    @staticmethod
    def page(items, query):
        size = int(query.get('per_page', ['100'])[0])
        page = int(query.get('page', ['1'])[0])
        return items[(page - 1) * size:page * size]


class MockServer:
    def __init__(self, state):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.request_api()
            do_POST = do_PUT = do_PATCH = do_GET

            def request_api(self):
                body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
                payload = json.loads(body) if body else None
                status, value, effect = state.route(self.command, self.path, payload,
                                                  self.headers.get('Authorization', ''))
                if effect == 'hold':
                    state.release.wait(20)
                    effect = 'drop'
                if effect == 'drop':
                    self.close_connection = True
                    try:
                        self.connection.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                    return
                encoded = json.dumps(value).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(encoded)))
                self.send_header('X-GitHub-Request-Id', 'SYNTHETIC:0001')
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, *_args):
                pass
        self.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


class Service:
    def __init__(self, binary, root, crypto, github_url, native=False, database=None,
                 enabled=True, override=None):
        root.mkdir(parents=True, exist_ok=True)
        self.port = free_port()
        self.url = f'http://127.0.0.1:{self.port}/mcp'
        config = {'repository': REPOSITORY, 'owner': OWNER['login'], 'baseBranch': 'main',
                  'reviewCheckName': 'chatgpt-review', 'writerActor': WRITER['login'],
                  'githubNativeAuthorityEnabled': native,
                  'githubApp': {**APP, 'appId': '102', 'installationId': '202',
                                'expectedActor': REVIEWER['login']},
                  'artifact': {'commit': HEAD, 'sha256': sha256(binary.read_bytes())},
                  'service': {'name': 'reviewer-mcp', 'bind_mode': 'a_only_loopback',
                              'bind_address': '127.0.0.1', 'bind_network': '',
                              'gateway_validated': False, 'bind_port': self.port, 'mount_path': '/mcp'}}
        path = root / 'reviewer-mcp.json'
        path.write_text(json.dumps(config))
        path.chmod(0o600)
        self.log = (root / 'service.log').open('wb')
        env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
               'REVIEWER_RELAY_ENABLED': str(enabled).lower(),
               'REVIEWER_RELAY_DB': str(database or root / 'reviewer.sqlite3'),
               'REVIEWER_CLIENT_CA_FILE': str(crypto / 'ca.pem'),
               'GITHUB_APP_ID': '102', 'GITHUB_APP_INSTALLATION_ID': '202',
               'GITHUB_APP_PRIVATE_KEY_FILE': str(crypto / 'fake-app.pem'),
               'REVIEWER_SYNTHETIC_GITHUB_API': override or github_url}
        self.process = subprocess.Popen([str(binary), '--config', str(path)], env=env,
                                        stdout=self.log, stderr=subprocess.STDOUT)
        self.headers = {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream',
                        'X-OpenAI-MTLS-Verified': '1',
                        'X-OpenAI-MTLS-Client-Cert': urllib.parse.quote((crypto / 'client.pem').read_text(), safe='')}

    def ready(self):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise AssertionError('Synthetic Reviewer failed to start; inspect fixture service.log')
            try:
                self.rpc('tools/list', {})
                return self
            except (urllib.error.URLError, TimeoutError):
                time.sleep(.02)
        raise AssertionError('Synthetic Reviewer readiness deadline exceeded')

    def rpc(self, method, params, headers=None):
        request = urllib.request.Request(self.url,
            data=json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}).encode(),
            headers=self.headers if headers is None else headers)
        with urllib.request.urlopen(request, timeout=12) as response:
            return json.load(response)

    def call(self, kind='approve', number=25):
        if kind == 'approve':
            name = 'submit_pr_review'
            args = {'repository': REPOSITORY, 'pr_number': number, 'expected_head_sha': HEAD,
                    'action': 'APPROVE', 'review_body': 'Synthetic exact-head independent fixture review.'}
        else:
            name = 'publish_task_authority'
            args = {'repository': REPOSITORY, 'record': {
                'schema_version': '4.0', 'kind': 'change-request', 'repository': REPOSITORY,
                'task': 24, 'parent': {'kind': 'pull_request', 'number': 25},
                'charter_sha256': sha256(CHARTER.encode()), 'purpose': 'Repair the exact reviewed defect',
                'branch': 'codex/task-24', 'base_sha': 'b' * 40, 'reviewed_head_sha': HEAD,
                'change_request_id': 'CR-24-001', 'findings': [{'id': 'F1', 'severity': 'major',
                    'problem': 'The input bound is missing.', 'impact': 'Unbounded input violates the admitted contract.',
                    'remediation': 'Enforce the bound.', 'acceptance_criteria': ['The oversized input is rejected.']}],
                'context': []}}
        response = self.rpc('tools/call', {'name': name, 'arguments': args})
        assert 'error' not in response, response.get('error')
        return response['result']

    def stop(self, kill=False):
        if self.process.poll() is None:
            self.process.kill() if kill else self.process.terminate()
        self.process.wait(timeout=5)
        self.log.close()


def assert_complete(result):
    assert result.get('isError') is not True, result


def run_case(binary, root, crypto, kind, fault):
    root.mkdir()
    state = Github(fault)
    mock = MockServer(state)
    services = []
    database = root / 'persistent.sqlite3'
    def start(name):
        service = Service(binary, root / name, crypto, mock.url,
                          native=kind == 'cr', database=database)
        services.append(service)
        return service.ready()
    try:
        first = start('first')
        # The real service must reject missing forwarded mTLS identity.
        try:
            first.rpc('tools/list', {}, {'Content-Type': 'application/json'})
        except urllib.error.HTTPError as error:
            assert error.code == 403
        else:
            raise AssertionError('Missing mTLS fixture identity was accepted')
        if fault == 'concurrent':
            second = start('second')
            barrier = threading.Barrier(2)
            def publish(service):
                barrier.wait(timeout=5)
                return service.call(kind)
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as workers:
                results = list(workers.map(publish, [first, second]))
            assert any(result.get('isError') is not True for result in results), results
            assert_complete(first.call(kind))
        elif fault == 'crash-review':
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as workers:
                pending = workers.submit(first.call, kind)
                assert state.accepted.wait(8), 'Decisive fixture review POST was not reached'
                first.stop(kill=True)
                state.release.set()
                try:
                    pending.result(timeout=5)
                except (OSError, urllib.error.URLError):
                    pass
            assert_complete(start('restarted').call(kind))
        elif fault == 'missing-checks':
            for _ in range(3):
                assert first.call(kind).get('isError') is True
            assert state.count('/check-runs') == 2, state.count('/check-runs')
            assert not state.checks
            # An unresolved auxiliary operation must not block another Task/PR.
            state.fault = 'normal'
            unrelated = Service(binary, root / 'unrelated', crypto, mock.url,
                                native=False, database=database).ready()
            services.append(unrelated)
            assert_complete(unrelated.call('approve', number=27))
            assert len(state.reviews[27]) == 1
        else:
            result = first.call(kind)
            if fault == 'normal':
                assert_complete(result)
            if fault == 'token-before-check':
                assert result.get('isError') is True, result
                assert state.count('/check-runs') == 0
            if fault == 'reject-check':
                assert result.get('isError') is True, result
                assert state.count('/check-runs') == 1 and not state.checks
            assert_complete(first.call(kind))
            expected = 2 if fault in ['reject-check', 'delayed-check'] else 1
            assert state.count('/check-runs') == expected, (fault, state.count('/check-runs'))
            if fault == 'normal':
                duplicate = copy.deepcopy(state.checks[0])
                duplicate['id'] += 100
                duplicate['html_url'] += '-late'
                duplicate['output']['annotations_url'] += '-late'
                state.checks.append(duplicate)
                assert_complete(first.call(kind))
                duplicate['conclusion'] = 'failure' if duplicate['conclusion'] == 'success' else 'success'
                assert first.call(kind).get('isError') is True
        assert len(state.reviews[25]) == 1, (kind, fault, state.reviews)
        return {'operation': kind, 'scenario': fault, 'decisive_reviews': len(state.reviews[25]),
                'check_posts': state.count('/check-runs') - int(fault == 'missing-checks'),
                'unrelated_check_posts': int(fault == 'missing-checks'),
                'observed_checks': len(state.checks)}
    finally:
        state.release.set()
        for service in reversed(services):
            service.stop()
        mock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, help='Prebuilt synthetic-github executable; otherwise build in disposable storage')
    parser.add_argument('--default-binary', type=Path, help='Optional default executable for override-is-ignored proof')
    parser.add_argument('--scenario', action='append', choices=['normal', 'token-before-check', 'reject-check',
                        'lost-check', 'delayed-check', 'missing-checks', 'concurrent', 'crash-review'])
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='relay-reviewer-publication-') as temporary:
        root = Path(temporary)
        crypto = root / 'fixture-credentials'
        crypto.mkdir(mode=0o700)
        make_crypto(crypto)
        if args.binary:
            built = args.binary.resolve()
        else:
            target = root / 'build-synthetic'
            subprocess.run(['cargo', 'build', '--locked', '--manifest-path', str(ROOT / 'reviewer/Cargo.toml'),
                            '--features', 'synthetic-github', '--target-dir', str(target)], check=True)
            built = target / 'debug/reviewer-mcp-http'
        install = root / 'installation' / 'current' / 'bin'
        install.mkdir(parents=True)
        binary = install / 'reviewer-mcp-http'
        shutil.copy2(built, binary)
        artifact = sha256(binary.read_bytes())
        controls = []
        if args.default_binary:
            service = Service(args.default_binary.resolve(), root / 'default-control', crypto,
                              'http://127.0.0.1:1', enabled=False, override='https://not-a-fixture.invalid').ready()
            service.stop()
            controls.append('default artifact ignores synthetic endpoint override')
        invalid = Service(binary, root / 'invalid-endpoint', crypto, 'http://127.0.0.1:1',
                          enabled=False, override='https://api.github.com')
        try:
            invalid.process.wait(timeout=5)
            assert invalid.process.returncode != 0, 'Synthetic artifact accepted an external endpoint'
        finally:
            invalid.stop()
        controls.append('synthetic artifact rejects external endpoint')
        scenarios = args.scenario or ['normal', 'token-before-check', 'reject-check', 'lost-check',
                                     'delayed-check', 'missing-checks', 'concurrent', 'crash-review']
        evidence = [run_case(binary, root / f'{kind}-{scenario}', crypto, kind, scenario)
                    for kind in ['approve', 'cr'] for scenario in scenarios]
        assert sha256(binary.read_bytes()) == artifact
        print(json.dumps({'qualification': 'SYNTHETIC_REVIEWER_PUBLICATION_PASS',
                          'artifact_sha256': artifact, 'controls': controls, 'evidence': evidence,
                          'scope': 'staged real feature-built service; real configuration/mTLS/RSA/SQLite; loopback fake GitHub',
                          'limitations': ['Synthetic compile-time transport artifact; default deployment artifact is separate.',
                                          'No root/Ansible/systemd installation, live GitHub Apps, external credentials or PROD proof.']}))


if __name__ == '__main__':
    main()
