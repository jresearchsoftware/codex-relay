"""Local owner App signing and ephemeral stdin-only pool Apply transport."""
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import shlex
import stat
import subprocess
import time

from managed_pool import GitHub, PERMISSION, require


OWNER_POOL_SCRIPT = '''import json, os, sys, types
try:
    payload = json.loads(sys.stdin.buffer.read(262145))
    if os.geteuid() != 0:
        raise ValueError()
    for name in ['managed_pool', 'pool_eligibility', 'pool_migration']:
        module = types.ModuleType(name)
        module.__file__ = '/owner-source/' + name + '.py'
        sys.modules[name] = module
        exec(compile(payload['sources'][name], module.__file__, 'exec'), module.__dict__)
    pool = sys.modules['managed_pool']
    migration = sys.modules['pool_migration']
    contract, auth = payload['contract'], payload['authorization']
    pool.require(all(auth[key] == contract[key] for key in ['organization', 'appId', 'installationId']),
                 'TOKEN_BINDING_INVALID')
    github = pool.GitHub(auth['installationToken'], contract['organization'])
    github.qualify(contract)
    migration.reject_serial_transition(contract)
    print('MANAGED_POOL_PREFLIGHT=PASS')
except Exception as error:
    # Fixed public error codes only. Never print payload, config or credentials.
    import re
    code = str(error)
    print(code if re.fullmatch('MANAGED_POOL_[A-Z_]{1,100}', code) else
          'MANAGED_POOL_PREFLIGHT_UNPROVEN_INSPECT_BEFORE_RETRY', file=sys.stderr)
    sys.exit(1)
'''


def preflight_pool(target, key, config, guard=None, *, local=False, extra_guard=None):
    """Read-only preflight also works before the first installed pool helper.

    Only the owner deploy process can use this SSH/root transport. Sources and
    private payload travel on stdin; no caller-selected installed executable or
    worker-accessible privilege entrypoint is introduced.
    """
    from managed_pool import pool_contract
    contract = pool_contract(config)
    source_root = Path(__file__).parent
    payload = {'sources': {name: (source_root / (name + '.py')).read_text()
                          for name in ['managed_pool', 'pool_eligibility', 'pool_migration']},
               'contract': contract, 'authorization': installation_authorization(config)}
    pending = json.dumps(payload)
    require(len(pending.encode()) <= 262144, 'OWNER_PREFLIGHT_INPUT_SIZE')
    command = ['/usr/bin/python3', '-I', '-c', OWNER_POOL_SCRIPT]
    argv = command if local else ['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
        '-o', 'IdentitiesOnly=yes', '-i', str(key), target['user'] + '@' + target['host'], shlex.join(command)]
    require(local or guard is not None and guard.poll() is None, 'HOST_GUARD_LOST')
    process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True)
    try:
        while True:
            require(local or guard.poll() is None, 'HOST_GUARD_LOST_INSPECT_BEFORE_RETRY')
            require(extra_guard is None or extra_guard.poll() is None, 'POOL_GUARD_LOST_INSPECT_BEFORE_RETRY')
            try:
                output, errors = process.communicate(input=pending, timeout=1)
                break
            except subprocess.TimeoutExpired:
                pending = None
        if process.returncode:
            import re
            codes = re.findall(r'^MANAGED_POOL_[A-Z_]{1,100}$', errors, re.MULTILINE)
            require(False, codes[-1].removeprefix('MANAGED_POOL_') if codes else 'OWNER_PREFLIGHT_UNPROVEN')
        require(output.strip() == 'MANAGED_POOL_PREFLIGHT=PASS',
                'OWNER_PREFLIGHT_RESULT_UNPROVEN')
        return output.strip()
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def installation_authorization(config, api_factory=GitHub):
    """Private key remains on the owner machine, never copied to a runner host."""
    app = config['environment']['generalRunner']['poolApp']
    key = Path(app['privateKeyFile'])
    try:
        metadata = key.lstat()
    except OSError:
        require(False, 'OWNER_APP_KEY_UNAVAILABLE_ON_OWNER_EXECUTION_HOST')
    require(stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1, 'OWNER_APP_KEY_INVALID')
    now = int(time.time())
    encode = lambda value: base64.urlsafe_b64encode(value).rstrip(b'=').decode('ascii')
    header = encode(b'{"alg":"RS256","typ":"JWT"}')
    payload = encode(json.dumps({'iat': now - 60, 'exp': now + 540, 'iss': app['appId']},
                                separators=(',', ':')).encode())
    message = (header + '.' + payload).encode('ascii')
    signature = subprocess.run(['openssl', 'dgst', '-sha256', '-sign', str(key)], input=message,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    require(signature.returncode == 0, 'OWNER_APP_SIGNING_FAILED')
    organization = config['consumer']['repository'].split('/')[0]
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


def reconcile_pool(target, key, config, revision, guard=None, *, local=False, extra_guard=None):
    """Caller retains the ordinary owner deployment lock for this whole call."""
    import re
    require(re.fullmatch('[0-9a-f]{40}', revision), 'EXACT_REVISION_REQUIRED')
    require(local or guard is not None and guard.poll() is None, 'HOST_GUARD_LOST')
    helper = '/opt/' + config['environment']['namespace'] + '/relay-managed-pool'
    authorization = installation_authorization(config)
    argv = [helper, revision] if local else ['ssh', '-o', 'BatchMode=yes', '-o',
        'StrictHostKeyChecking=yes', '-o', 'IdentitiesOnly=yes', '-i', str(key),
        target['user'] + '@' + target['host'], shlex.join([helper, revision])]
    process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True)
    try:
        pending = json.dumps(authorization)
        authorization = None
        while True:
            require(local or guard.poll() is None, 'HOST_GUARD_LOST_INSPECT_BEFORE_RETRY')
            require(extra_guard is None or extra_guard.poll() is None, 'POOL_GUARD_LOST_INSPECT_BEFORE_RETRY')
            try:
                output, errors = process.communicate(input=pending, timeout=1)
                break
            except subprocess.TimeoutExpired:
                pending = None
        if process.returncode:
            codes = re.findall(r'^MANAGED_POOL_[A-Z_]{1,100}$', errors, re.MULTILINE)
            require(False, codes[-1].removeprefix('MANAGED_POOL_') if codes else
                    'RECONCILIATION_UNPROVEN_INSPECT_BEFORE_RETRY')
        require(output.startswith('MANAGED_POOL_RESULT=') and len(output) <= 16384,
                'RESULT_UNPROVEN_INSPECT_BEFORE_RETRY')
        result = json.loads(output.removeprefix('MANAGED_POOL_RESULT='))
        require(result.get('capacity') == config['consumer']['generalRunnerPool']['desiredCapacity'],
                'RESULT_CAPACITY_UNPROVEN')
        return output.strip()
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
