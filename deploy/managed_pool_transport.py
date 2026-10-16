"""Local owner App signing and ephemeral stdin-only pool Apply transport."""
import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import tempfile
import time

from managed_pool import GitHub, PERMISSION, require
from config import deployment_repository


OWNER_POOL_SOURCES = ['managed_pool', 'pool_eligibility', 'config', 'pool_migration',
                      'serial_pool_transition', 'serial_pool_host', 'serial_pool_installation']
OWNER_POOL_INPUT_BYTES = 262144
OWNER_POOL_OUTPUT_BYTES = 16384


OWNER_POOL_SCRIPT = '''import json, os, re, sys, types
try:
    raw = sys.stdin.buffer.read(262145)
    if len(raw) > 262144 or os.geteuid() != 0:
        raise ValueError()
    payload = json.loads(raw)
    for name in ['managed_pool', 'pool_eligibility', 'config', 'pool_migration',
                 'serial_pool_transition', 'serial_pool_host', 'serial_pool_installation']:
        module = types.ModuleType(name)
        module.__file__ = '/owner-source/' + name + '.py'
        sys.modules[name] = module
        exec(compile(payload['sources'][name], module.__file__, 'exec'), module.__dict__)
    pool = sys.modules['managed_pool']
    installation = sys.modules['serial_pool_installation']
    contract, auth = payload['contract'], payload['authorization']
    pool.require(pool.pool_contract(payload['config']) == contract
                 and all(auth[key] == contract[key] for key in ['organization', 'appId', 'installationId']),
                 'TOKEN_BINDING_INVALID')
    pool.require(isinstance(payload['targetDigest'], str)
                 and re.fullmatch('[0-9a-f]{64}', payload['targetDigest']), 'TARGET_DIGEST_UNPROVEN')
    github = pool.GitHub(auth['installationToken'], contract['organization'])
    # F1 remains before any original SERIAL reads or ownership transition.
    github.qualify(contract)
    proof = installation.preflight(payload['config'], github, payload['targetDigest'])
    pool.require(proof is None or isinstance(proof, dict) and
                 type(proof.get('completionRequired', False)) is bool, 'SERIAL_TRANSITION_RESULT_UNPROVEN')
    state = 'none' if proof is None else ('required' if proof.get('completionRequired') else
                                         'retained' if proof.get('phase') == 'retired' else 'required')
    action = payload['action']
    if action == 'preflight':
        operation = 'none' if proof is None else proof.get('operationId', 'none')
        pool.require(operation == 'none' or isinstance(operation, str) and
                     re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', operation),
                     'SERIAL_TRANSITION_OPERATION_INVALID')
        print('MANAGED_POOL_PREFLIGHT=PASS')
        print('MANAGED_POOL_SERIAL_TRANSITION=' + state)
        print('MANAGED_POOL_SERIAL_OPERATION=' + operation)
    else:
        pool.require(action in ['begin', 'finish']
                     and re.fullmatch('[0-9a-f]{40}', payload['revision'])
                     and re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', payload['operationId']),
                     'SERIAL_TRANSITION_OPERATION_INVALID')
        if proof is None:
            result = {'phase': 'none'}
        elif state == 'retained':
            result = proof
        elif action == 'begin':
            result = installation.begin(payload['config'], github, payload['targetDigest'],
                                        payload['operationId'], payload['revision'])
        else:
            result = installation.finish(payload['config'], github)
        public = {'phase': result['phase'],
                  'operationId': result.get('operationId', payload['operationId']),
                  'target': result.get('targetRevision', result.get('target', payload['revision']))}
        pool.require(public['phase'] in (['none', 'stopped', 'installed', 'retired'] if action == 'begin' else ['none', 'retired'])
                     and public['operationId'] == payload['operationId']
                     and public['target'] == payload['revision'], 'SERIAL_TRANSITION_RESULT_UNPROVEN')
        print('MANAGED_POOL_SERIAL_RESULT=' + json.dumps(public, separators=(',', ':')))
except Exception as error:
    # Fixed public error codes only. Never print payload, config or credentials.
    import re
    code = str(error)
    print(code if re.fullmatch('MANAGED_POOL_[A-Z_]{1,100}', code) else
          'MANAGED_POOL_PREFLIGHT_UNPROVEN_INSPECT_BEFORE_RETRY', file=sys.stderr)
    sys.exit(1)
'''


class PreflightProof(str):
    """Keep the original PASS string ABI and expose bounded transition facts."""
    def __new__(cls, transition_state, target_digest, operation_id=None):
        value = super().__new__(cls, 'MANAGED_POOL_PREFLIGHT=PASS')
        value.transition_state = transition_state
        value.serial_transition = transition_state == 'required'
        value.target_digest = target_digest
        value.operation_id = operation_id
        return value


def consumer_digest(consumer, source_root=None):
    """Use the qualified current Node resolver, including execution defaults.

    Do not import the Linux-only installed adapter on the owner workstation.
    No hash or profile normalization is reimplemented in this transport.
    """
    source_root = Path(source_root) if source_root is not None else Path(__file__).resolve().parents[1]
    code = ('import {consumerDigest,validateConsumer} from "./consumer/consumer-config.mjs";'
            'let s="";for await(const b of process.stdin)s+=b;'
            'console.log(JSON.stringify(consumerDigest(validateConsumer(JSON.parse(s)))));')
    result = subprocess.run(['node', '--input-type=module', '-e', code],
        input=json.dumps(consumer), cwd=source_root, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=60, check=False)
    require(result.returncode == 0 and len(result.stdout) <= 128, 'TARGET_DIGEST_UNPROVEN')
    try:
        digest = json.loads(result.stdout)
    except (ValueError, TypeError):
        require(False, 'TARGET_DIGEST_UNPROVEN')
    require(isinstance(digest, str) and re.fullmatch('[0-9a-f]{64}', digest), 'TARGET_DIGEST_UNPROVEN')
    return digest


def projected_consumer(config, source_root=None):
    """Use the existing backend compiler/template before binding a NEW target.

    The template's object order is part of the existing consumer digest ABI.
    Invoke the already-required Ansible executable so its Python environment
    need not be importable by the owner's separate Python interpreter.
    """
    from config import compile_inputs
    source_root = Path(source_root) if source_root is not None else Path(__file__).resolve().parents[1]
    backend = source_root / 'deploy/ansible'
    with tempfile.TemporaryDirectory(prefix='relay-consumer-projection-') as temporary:
        work = Path(temporary)
        destination = work / 'consumer.json'
        inventory = work / 'inventory.json'
        playbook = work / 'projection.json'
        inventory.write_text(json.dumps({'all': {'hosts': {'localhost': {
            **compile_inputs(config), 'ansible_connection': 'local', 'ansible_become': False,
            'ansible_remote_tmp': str(work / 'remote-tmp')}}}}))
        playbook.write_text(json.dumps([{'hosts': 'localhost', 'gather_facts': False,
            'become': False, 'tasks': [{'ansible.builtin.template': {
                'src': str(backend / 'roles/relay_controller/templates/consumer.json.j2'),
                'dest': str(destination), 'mode': '0600'}, 'no_log': True}]}]))
        for path in [inventory, playbook]:
            path.chmod(0o600)
        env = {key: os.environ[key] for key in ['HOME', 'PATH', 'USER', 'LANG', 'LC_ALL'] if key in os.environ}
        env.update(ANSIBLE_CONFIG=str(backend / 'ansible.cfg'), ANSIBLE_LOCAL_TEMP=str(work / 'local-tmp'))
        result = subprocess.run(['ansible-playbook', '-i', str(inventory), str(playbook), '--limit', 'localhost'],
            cwd=backend, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=60, check=False)
        require(result.returncode == 0, 'TARGET_DIGEST_UNPROVEN')
        return json.loads(destination.read_text())


def _owner_payload(config, action, revision=None, operation_id=None):
    from managed_pool import pool_contract
    contract = pool_contract(config)
    source_root = Path(__file__).parent
    digest = consumer_digest(projected_consumer(config, source_root.parent), source_root.parent)
    payload = {'sources': {name: (source_root / (name + '.py')).read_text(encoding='utf-8')
                          for name in OWNER_POOL_SOURCES},
               'contract': contract, 'config': config, 'targetDigest': digest,
               'action': action, 'revision': revision, 'operationId': operation_id}
    require(len(json.dumps(payload).encode()) <= OWNER_POOL_INPUT_BYTES - 8192, 'OWNER_PREFLIGHT_INPUT_SIZE')
    payload['authorization'] = installation_authorization(config)
    pending = json.dumps(payload)
    require(len(pending.encode()) <= OWNER_POOL_INPUT_BYTES, 'OWNER_PREFLIGHT_INPUT_SIZE')
    return pending, digest


def _owner_transport(target, key, pending, guard, *, local, extra_guard):
    """One bounded stdin exchange under the existing owner deployment guards."""
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
            codes = re.findall(r'^MANAGED_POOL_[A-Z_]{1,100}$', errors, re.MULTILINE)
            require(False, codes[-1].removeprefix('MANAGED_POOL_') if codes else 'OWNER_PREFLIGHT_UNPROVEN')
        require(len(output.encode()) <= OWNER_POOL_OUTPUT_BYTES, 'OWNER_POOL_RESULT_SIZE_UNPROVEN')
        return output
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def preflight_pool(target, key, config, guard=None, *, local=False, extra_guard=None):
    """Read-only root preflight, including before an installed pool helper."""
    require(local or guard is not None and guard.poll() is None, 'HOST_GUARD_LOST')
    require(extra_guard is None or extra_guard.poll() is None, 'POOL_GUARD_LOST')
    pending, digest = _owner_payload(config, 'preflight')
    output = _owner_transport(target, key, pending, guard, local=local, extra_guard=extra_guard)
    match = re.fullmatch('MANAGED_POOL_PREFLIGHT=PASS\nMANAGED_POOL_SERIAL_TRANSITION=(required|retained|none)\n'
        '(?:MANAGED_POOL_SERIAL_OPERATION=(none|[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})\n)?', output)
    require(match is not None, 'OWNER_PREFLIGHT_RESULT_UNPROVEN')
    operation_id = None if match[2] in [None, 'none'] else match[2]
    require(match[1] != 'none' or operation_id is None, 'OWNER_PREFLIGHT_RESULT_UNPROVEN')
    return PreflightProof(match[1], digest, operation_id)


def transition_pool(target, key, config, revision, operation_id, guard=None, *,
                    local=False, extra_guard=None, action='begin'):
    """Use fixed owner/root adapters; payload and ephemeral token stay on stdin."""
    require(action in ['begin', 'finish'] and isinstance(revision, str)
            and re.fullmatch('[0-9a-f]{40}', revision)
            and isinstance(operation_id, str)
            and re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', operation_id),
            'SERIAL_TRANSITION_OPERATION_INVALID')
    require(local or guard is not None and guard.poll() is None, 'HOST_GUARD_LOST')
    require(extra_guard is None or extra_guard.poll() is None, 'POOL_GUARD_LOST')
    pending, _ = _owner_payload(config, action, revision, operation_id)
    output = _owner_transport(target, key, pending, guard, local=local, extra_guard=extra_guard)
    require(output.startswith('MANAGED_POOL_SERIAL_RESULT=') and output.endswith('\n'),
            'SERIAL_TRANSITION_RESULT_UNPROVEN')
    try:
        result = json.loads(output.removeprefix('MANAGED_POOL_SERIAL_RESULT='))
    except (ValueError, TypeError):
        require(False, 'SERIAL_TRANSITION_RESULT_UNPROVEN')
    require(isinstance(result, dict) and set(result) == {'phase', 'operationId', 'target'}
            and result['phase'] in (['none', 'stopped', 'installed', 'retired'] if action == 'begin' else ['none', 'retired'])
            and result['operationId'] == operation_id and result['target'] == revision,
            'SERIAL_TRANSITION_RESULT_UNPROVEN')
    return result


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
