"""Read one configured consumer with its existing Writer App, never Git intent credentials."""
import base64
from contextlib import contextmanager
from dataclasses import dataclass, field
import http.client
import json
import os
from pathlib import Path
import re
import ssl
import stat
import subprocess
import time


class ConsumerSourceError(ValueError):
    """Fixed public diagnostics only."""


class APIError(ConsumerSourceError):
    def __init__(self, status):
        self.status = status
        super().__init__('CONSUMER_SOURCE_HTTP_' + str(status))


def require(condition, code):
    if not condition:
        raise ConsumerSourceError('CONSUMER_SOURCE_' + code)


def positive(value):
    return type(value) is int and 0 < value <= 9007199254740991


def _object(value):
    return value if isinstance(value, dict) else {}


def _sha(value):
    return isinstance(value, str) and re.fullmatch('[a-f0-9]{40}', value) is not None


def _repository_name(value):
    return isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}', value) is not None


def _bearer(value, limit):
    return isinstance(value, str) and 1 <= len(value) <= limit and re.fullmatch(r'[A-Za-z0-9._~+/-]+=*', value) is not None


def github_api(method, path, token=None, body=None):
    require(method in ('GET', 'POST', 'DELETE') and isinstance(path, str)
            and re.fullmatch(r'/(?:app|installation|repos)(?:/[A-Za-z0-9_.-]+)*', path), 'API_PATH_INVALID')
    headers = {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28',
               'Content-Type': 'application/json', 'User-Agent': 'codex-relay-consumer-source'}
    if token is not None:
        require(_bearer(token, 16384), 'CREDENTIAL_INVALID')
        headers['Authorization'] = 'Bearer ' + token
    connection = http.client.HTTPSConnection('api.github.com', timeout=30, context=ssl.create_default_context())
    try:
        connection.request(method, path, body=None if body is None else json.dumps(body).encode(), headers=headers)
        response = connection.getresponse()
        expected = {'GET': 200, 'POST': 201, 'DELETE': 204}[method]
        if response.status != expected:
            raise APIError(response.status)
        raw = response.read(1024 * 1024 + 1)
        require(len(raw) <= 1024 * 1024, 'API_RESPONSE_TOO_LARGE')
        if method == 'DELETE':
            require(not raw, 'API_RESPONSE_INVALID')
            return None
        value = json.loads(raw)
        require(isinstance(value, dict), 'API_RESPONSE_INVALID')
        return value
    except ConsumerSourceError:
        raise
    except (OSError, http.client.HTTPException, ValueError):
        raise ConsumerSourceError('CONSUMER_SOURCE_API_UNAVAILABLE') from None
    finally:
        connection.close()


def _jwt(key_path, app_id, *, owner_uid=0, boundary=Path('/')):
    """Open the protected key once; OpenSSL reads that FD, not a mutable path."""
    key_path, boundary = Path(key_path), Path(boundary)
    require(key_path.is_absolute() and key_path == Path(os.path.normpath(key_path))
            and re.fullmatch(r'/[A-Za-z0-9_./-]+', str(key_path))
            and key_path.is_relative_to(boundary), 'KEY_PATH_INVALID')
    try:
        for parent in key_path.parents:
            info = parent.lstat()
            require(stat.S_ISDIR(info.st_mode) and info.st_uid == owner_uid and not info.st_mode & 0o022, 'KEY_PARENT_UNSAFE')
            if parent == boundary:
                break
        fd = os.open(key_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        raise ConsumerSourceError('CONSUMER_SOURCE_KEY_UNAVAILABLE') from None
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == owner_uid and info.st_nlink == 1
                and stat.S_IMODE(info.st_mode) in (0o400, 0o440, 0o600, 0o640)
                and 0 < info.st_size <= 32768, 'KEY_UNSAFE')
        encode = lambda raw: base64.urlsafe_b64encode(raw).rstrip(b'=')
        now = int(time.time())
        message = encode(b'{"alg":"RS256","typ":"JWT"}') + b'.' + encode(json.dumps({
            'iat': now - 30, 'exp': now + 300, 'iss': str(app_id)}, separators=(',', ':')).encode())
        signature = subprocess.run(['/usr/bin/openssl', 'dgst', '-sha256', '-sign', '/proc/self/fd/' + str(fd)],
            input=message, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, pass_fds=(fd,),
            env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'}, timeout=15, check=False)
        require(signature.returncode == 0 and 0 < len(signature.stdout) <= 8192, 'JWT_SIGNATURE_FAILED')
        return (message + b'.' + encode(signature.stdout)).decode('ascii')
    except ConsumerSourceError:
        raise
    except (OSError, subprocess.SubprocessError):
        raise ConsumerSourceError('CONSUMER_SOURCE_KEY_UNAVAILABLE') from None
    finally:
        os.close(fd)


def _repository(value, repository, private):
    require(isinstance(value, dict) and value.get('full_name') == repository and positive(value.get('id'))
            and value.get('private') is private and value.get('default_branch') == 'main', 'REPOSITORY_MISMATCH')
    return value


def _main(api, repository, token):
    value = api('GET', '/repos/' + repository + '/git/ref/heads/main', token)
    require(isinstance(value, dict) and value.get('ref') == 'refs/heads/main'
            and isinstance(value.get('object'), dict) and value['object'].get('type') == 'commit'
            and _sha(value['object'].get('sha')), 'MAIN_INVALID')
    return value['object']['sha']


@dataclass
class ConsumerSource:
    head: str
    repository_id: int
    private: bool
    token: str = field(default=None, repr=False)


@contextmanager
def consumer_access(config, repository, *, api=None):
    api = github_api if api is None else api
    consumer = _object(_object(config).get('consumer'))
    allowed = consumer.get('repositories', [consumer.get('repository')])
    require(_repository_name(repository) and isinstance(allowed, list) and repository in allowed, 'REPOSITORY_NOT_CONFIGURED')
    try:
        public = api('GET', '/repos/' + repository)
    except APIError as error:
        if error.status != 404:
            raise
    else:
        public = _repository(public, repository, False)
        yield ConsumerSource(_main(api, repository, None), public['id'], False)
        return
    require(os.geteuid() == 0, 'ROOT_REQUIRED')
    app = _object(consumer.get('writerApp'))
    try:
        app_id = int(app.get('appId', '')); installation_id = int(app.get('installationId', ''))
    except (ValueError, TypeError):
        raise ConsumerSourceError('CONSUMER_SOURCE_APP_BINDING_INVALID') from None
    slug = app.get('slug')
    key_path = _object(consumer.get('paths')).get('credentialKeyFile')
    require(positive(app_id) and positive(installation_id) and isinstance(slug, str)
            and re.fullmatch('[A-Za-z0-9][A-Za-z0-9-]{0,99}', slug)
            and isinstance(key_path, str), 'APP_BINDING_INVALID')
    namespace = _object(_object(config).get('environment')).get('namespace')
    require(isinstance(namespace, str) and re.fullmatch('[a-z][a-z0-9-]{0,30}', namespace)
            and key_path.startswith('/etc/' + namespace + '/')
            and re.fullmatch('/[A-Za-z0-9_./-]+', key_path)
            and key_path == os.path.normpath(key_path), 'KEY_NAMESPACE_MISMATCH')
    jwt = _jwt(key_path, app_id)
    identity = api('GET', '/app', jwt)
    require(_object(identity).get('id') == app_id and identity.get('slug') == slug
            and _object(identity.get('permissions')).get('contents') in ('read', 'write'), 'APP_IDENTITY_MISMATCH')
    owner, name = repository.split('/')
    installation = api('GET', '/app/installations/' + str(installation_id), jwt)
    grant = api('GET', '/repos/' + repository + '/installation', jwt)
    for value in (installation, grant):
        require(isinstance(value, dict) and value.get('id') == installation_id and value.get('app_id') == app_id
                and _object(value.get('account')).get('login') == owner and positive(_object(value.get('account')).get('id'))
                and value.get('target_type') in ('Organization', 'User')
                and _object(value.get('account')).get('type') == value.get('target_type')
                and value.get('suspended_at') is None and _object(value.get('permissions')).get('contents') in ('read', 'write'),
                'INSTALLATION_GRANT_MISMATCH')
    require(installation['account']['id'] == grant['account']['id'], 'INSTALLATION_GRANT_MISMATCH')
    token = None
    access = None
    try:
        try:
            issued = api('POST', '/app/installations/' + str(installation_id) + '/access_tokens', jwt,
                         {'repositories': [name], 'permissions': {'contents': 'read', 'metadata': 'read'}})
        except APIError:
            raise
        except ConsumerSourceError:
            raise ConsumerSourceError('CONSUMER_SOURCE_TOKEN_ISSUANCE_UNPROVEN') from None
        require(isinstance(issued, dict), 'TOKEN_INVALID')
        token = issued.get('token')
        require(_bearer(token, 4096), 'TOKEN_INVALID')
        require(issued.get('permissions') == {'contents': 'read', 'metadata': 'read'}
                and isinstance(issued.get('repositories'), list) and len(issued['repositories']) == 1,
                'TOKEN_SCOPE_MISMATCH')
        selected = issued['repositories'][0]
        require(_object(selected).get('full_name') == repository and positive(selected.get('id'))
                and selected.get('private') is True, 'TOKEN_SCOPE_MISMATCH')
        actual = _repository(api('GET', '/repos/' + repository, token), repository, True)
        require(actual['id'] == selected['id'] and _object(actual.get('owner')).get('login') == owner
                and _object(actual.get('owner')).get('id') == installation['account']['id']
                and _object(actual.get('owner')).get('type') == installation['account']['type'], 'REPOSITORY_MISMATCH')
        access = ConsumerSource(_main(api, repository, token), actual['id'], True, token)
        yield access
    finally:
        if access is not None:
            access.token = None
        if token:
            try:
                api('DELETE', '/installation/token', token)
            except Exception:
                raise ConsumerSourceError('CONSUMER_SOURCE_TOKEN_REVOCATION_UNPROVEN') from None


def git_read_environment(base, repository, token=None):
    require(_repository_name(repository), 'REPOSITORY_NOT_CONFIGURED')
    environment = {key: value for key, value in base.items()
                   if not key.startswith(('GIT_CONFIG_', 'GIT_TRACE')) and key not in ('GIT_ASKPASS', 'SSH_ASKPASS', 'GIT_CURL_VERBOSE')}
    environment.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null', GIT_TERMINAL_PROMPT='0')
    settings = [('credential.helper', ''), ('credential.interactive', 'false'),
                ('http.followRedirects', 'false'), ('http.extraHeader', '')]
    if token is not None:
        require(_bearer(token, 4096), 'TOKEN_INVALID')
        header = 'AUTHORIZATION: basic ' + base64.b64encode(('x-access-token:' + token).encode()).decode()
        settings.append(('http.https://github.com/' + repository + '.git.extraHeader', header))
    environment['GIT_CONFIG_COUNT'] = str(len(settings))
    for index, (key, value) in enumerate(settings):
        environment['GIT_CONFIG_KEY_' + str(index)] = key
        environment['GIT_CONFIG_VALUE_' + str(index)] = value
    return environment
