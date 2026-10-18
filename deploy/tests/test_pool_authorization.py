"""Target-local signing and credential boundaries, without live GitHub access."""
import base64
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ansible_transport
import managed_pool
import managed_pool_transport
import pool_authorization
from test_managed_pool import inputs


@pytest.mark.parametrize('damage', ['app', 'installation', 'organization', 'permission', 'token-permission', 'expiry'])
def test_target_authorization_fails_closed_before_returning_a_token(tmp_path, monkeypatch, damage):
    value = inputs(1)
    key = tmp_path / 'key.pem'
    key.write_text('synthetic-key-never-a-real-credential')
    key.chmod(0o600)
    value['environment']['generalRunner']['poolApp']['privateKeyFile'] = str(key)
    monkeypatch.setattr(pool_authorization.os, 'geteuid', lambda: 0)
    # Credential protection is exercised independently below; this isolates API binding.
    native_stat = os.fstat
    def target_stat(fd):
        fields = list(native_stat(fd))
        fields[4] = 0
        return os.stat_result(fields)
    monkeypatch.setattr(pool_authorization.os, 'fstat', target_stat)
    signing = Mock(return_value=type('Signature', (), {'returncode': 0, 'stdout': b'signature'})())
    monkeypatch.setattr(pool_authorization.subprocess, 'run', signing)

    class App:
        def __init__(self, *_args):
            pass

        def request(self, method, path, body=None):
            if path == '/app':
                return {'id': 999 if damage == 'app' else 101}
            if path.endswith('/201'):
                return {'id': 999 if damage == 'installation' else 201, 'app_id': 101,
                        'account': {'login': 'foreign' if damage == 'organization' else 'example-org', 'type': 'Organization'},
                        'permissions': {managed_pool.PERMISSION: 'read' if damage == 'permission' else 'write'}}
            assert body == {'permissions': {managed_pool.PERMISSION: 'write'}}
            return {'token': 'synthetic-private-token',
                    'permissions': {managed_pool.PERMISSION: 'read' if damage == 'token-permission' else 'write'},
                    'expires_at': (datetime.now(timezone.utc) + timedelta(seconds=5 if damage == 'expiry' else 3600)).isoformat()}

    with pytest.raises(managed_pool.PoolError) as error:
        pool_authorization.installation_authorization(value, App)
    assert 'synthetic-private-token' not in str(error.value)
    assert '/proc/self/fd/' in signing.call_args.args[0][-1]
    assert signing.call_args.kwargs['pass_fds']


@pytest.mark.skipif(os.geteuid() != 0, reason='target credential ownership is intentionally root-only')
@pytest.mark.parametrize('damage', ['permissions', 'symlink', 'hardlink', 'directory'])
def test_target_private_key_metadata_is_checked_before_signing(tmp_path, monkeypatch, damage):
    key = tmp_path / 'private.pem'
    key.write_text('synthetic-private-key')
    key.chmod(0o600)
    selected = key
    if damage == 'permissions':
        key.chmod(0o644)
    elif damage == 'symlink':
        selected = tmp_path / 'alias.pem'
        selected.symlink_to(key)
    elif damage == 'hardlink':
        os.link(key, tmp_path / 'other.pem')
    else:
        selected = tmp_path
    value = inputs(1)
    value['environment']['generalRunner']['poolApp']['privateKeyFile'] = str(selected)
    signing = Mock()
    monkeypatch.setattr(pool_authorization.subprocess, 'run', signing)
    with pytest.raises(managed_pool.PoolError):
        pool_authorization.installation_authorization(value)
    signing.assert_not_called()


@pytest.mark.skipif(os.geteuid() != 0, reason='real target root signing and Ansible execution')
def test_real_target_signing_returns_only_public_preflight_receipt():
    with tempfile.TemporaryDirectory(prefix='relay-target-app-test-', dir='/run') as directory:
        key = Path(directory) / 'private.pem'
        subprocess.run(['openssl', 'genpkey', '-algorithm', 'RSA', '-pkeyopt', 'rsa_keygen_bits:2048',
                        '-out', str(key)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        key.chmod(0o600)
        value = inputs(1)
        value['environment']['generalRunner']['poolApp']['privateKeyFile'] = str(key)
        contract = managed_pool.pool_contract(value)
        sources = {name: '' for name in managed_pool_transport.OWNER_POOL_SOURCES}
        sources['config'] = 'def deployment_repository(config): return config["consumer"]["repository"]\n'
        sources['pool_authorization'] = Path(pool_authorization.__file__).read_text()
        sources['managed_pool'] = '''import base64, json
from datetime import datetime, timedelta, timezone
PERMISSION='organization_self_hosted_runners'
def require(value, code):
    if not value: raise ValueError('MANAGED_POOL_'+code)
def pool_contract(config): return config['contract']
class GitHub:
    def __init__(self, token, organization):
        self.token=token
        if token.count('.')==2:
            claim=json.loads(base64.urlsafe_b64decode(token.split('.')[1]+'=='))
            require(claim['iss']=='101' and claim['exp']>claim['iat'], 'JWT_UNPROVEN')
    def request(self, method, path, body=None):
        require(self.token.count('.')==2,'TARGET_SIGNING_REQUIRED')
        if path=='/app': return {'id':101}
        if path.endswith('/201'): return {'id':201,'app_id':101,'account':{'login':'example-org','type':'Organization'},'permissions':{PERMISSION:'write'}}
        require(body=={'permissions':{PERMISSION:'write'}},'PERMISSION_UNPROVEN')
        return {'token':'synthetic-target-only-token','permissions':{PERMISSION:'write'},'expires_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()}
    def qualify(self, contract): require(self.token=='synthetic-target-only-token','TOKEN_UNPROVEN')
'''
        sources['serial_pool_installation'] = 'def preflight(config, github, digest): return None\n'
        value['contract'] = contract
        payload = json.dumps({'config': value, 'contract': contract, 'sources': sources,
                              'targetDigest': 'b' * 64, 'action': 'preflight'})
        assert key.read_text() not in payload and 'authorization' not in json.loads(payload)
        result = ansible_transport.run_target({'user': 'root', 'host': 'synthetic-target.invalid', 'connection': 'local'},
            None, ['/usr/bin/python3', '-I', '-c', managed_pool_transport.OWNER_POOL_SCRIPT],
            input=payload, timeout=45)
        assert result.returncode == 0, result.stderr
        assert result.stdout == ('MANAGED_POOL_PREFLIGHT=PASS\nMANAGED_POOL_SERIAL_TRANSITION=none\n'
                                 'MANAGED_POOL_SERIAL_OPERATION=none\n')
        assert result.stderr == ''
        assert 'synthetic-target-only-token' not in result.stdout
        assert key.exists() and key.stat().st_mode & 0o777 == 0o600
