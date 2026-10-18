"""Target-local GitHub App authorization for the managed General Runner pool."""
import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat
import subprocess
import time

from managed_pool import GitHub, PERMISSION, require
from config import deployment_repository


def installation_authorization(config, api_factory=GitHub):
    """Sign only on the protected target; never return authorization to a controller."""
    require(os.geteuid() == 0, 'TARGET_ROOT_REQUIRED')
    app = config['environment']['generalRunner']['poolApp']
    key = Path(app['privateKeyFile'])
    try:
        descriptor = os.open(key, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        require(False, 'OWNER_APP_KEY_UNAVAILABLE_ON_OWNER_EXECUTION_HOST')
    now = int(time.time())
    encode = lambda value: base64.urlsafe_b64encode(value).rstrip(b'=').decode('ascii')
    header = encode(b'{"alg":"RS256","typ":"JWT"}')
    payload = encode(json.dumps({'iat': now - 60, 'exp': now + 540, 'iss': app['appId']},
                                separators=(',', ':')).encode())
    message = (header + '.' + payload).encode('ascii')
    try:
        metadata = os.fstat(descriptor)
        require(stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1, 'OWNER_APP_KEY_INVALID')
        require(metadata.st_uid == 0 and stat.S_IMODE(metadata.st_mode) in [0o400, 0o600],
                'TARGET_APP_KEY_UNPROTECTED')
        signature = subprocess.run(['openssl', 'dgst', '-sha256', '-sign', '/proc/self/fd/' + str(descriptor)],
            pass_fds=(descriptor,), input=message, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, check=False)
    finally:
        os.close(descriptor)
    require(signature.returncode == 0, 'OWNER_APP_SIGNING_FAILED')
    organization = deployment_repository(config).split('/')[0]
    api = api_factory(message.decode() + '.' + encode(signature.stdout), organization)
    identity = api.request('GET', '/app')
    require(str(identity.get('id')) == app['appId'], 'OWNER_APP_IDENTITY_UNPROVEN')
    installation = api.request('GET', '/app/installations/' + app['installationId'])
    require(str(installation.get('id')) == app['installationId']
            and str(installation.get('app_id')) == app['appId']
            and installation.get('account', {}).get('login', '').lower() == organization.lower()
            and installation.get('account', {}).get('type') == 'Organization'
            and installation.get('permissions', {}).get(PERMISSION) == 'write',
            'OWNER_APP_INSTALLATION_PERMISSION_UNPROVEN')
    authorization = api.request('POST', '/app/installations/' + app['installationId'] + '/access_tokens',
                                {'permissions': {PERMISSION: 'write'}})
    require(authorization.get('permissions', {}).get(PERMISSION) == 'write'
            and isinstance(authorization.get('token'), str) and bool(authorization['token']),
            'OWNER_APP_INSTALLATION_TOKEN_UNPROVEN')
    try:
        remaining = (datetime.fromisoformat(authorization['expires_at'].replace('Z', '+00:00'))
                     - datetime.now(timezone.utc)).total_seconds()
    except (ValueError, TypeError, KeyError):
        remaining = 0
    require(60 <= remaining <= 7200, 'OWNER_APP_TOKEN_EXPIRY_UNPROVEN')
    return {'appId': app['appId'], 'installationId': app['installationId'],
            'organization': organization, 'installationToken': authorization['token']}
