"""Ansible transport of nonsecret pool requests and bounded target-local receipts."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from managed_pool import require
from ansible_transport import TargetProcess


OWNER_POOL_SOURCES = ['managed_pool', 'pool_eligibility', 'config', 'pool_migration',
                      'serial_pool_transition', 'serial_pool_host', 'serial_pool_installation', 'pool_authorization']
OWNER_POOL_INPUT_BYTES = 262144
OWNER_POOL_OUTPUT_BYTES = 16384


OWNER_POOL_SCRIPT = r'''import json, os, re, sys, types
try:
    raw = sys.stdin.buffer.read(262145)
    if len(raw) > 262144 or os.geteuid() != 0:
        raise ValueError()
    payload = json.loads(raw)
    for name in ['managed_pool', 'pool_eligibility', 'config', 'pool_migration',
                 'serial_pool_transition', 'serial_pool_host', 'serial_pool_installation', 'pool_authorization']:
        module = types.ModuleType(name)
        module.__file__ = '/owner-source/' + name + '.py'
        sys.modules[name] = module
        exec(compile(payload['sources'][name], module.__file__, 'exec'), module.__dict__)
    pool = sys.modules['managed_pool']
    installation = sys.modules['serial_pool_installation']
    contract = payload['contract']
    auth = sys.modules['pool_authorization'].installation_authorization(payload['config'])
    pool.require(pool.pool_contract(payload['config']) == contract
                 and all(auth[key] == contract[key] for key in ['organization', 'appId', 'installationId']),
                 'TOKEN_BINDING_INVALID')
    pool.require(isinstance(payload['targetDigest'], str)
                 and re.fullmatch('[0-9a-f]{64}', payload['targetDigest']), 'TARGET_DIGEST_UNPROVEN')
    github = pool.GitHub(auth['installationToken'], contract['organization'])
    if payload['action'] == 'reconcile':
        import hashlib, subprocess
        pool.require(re.fullmatch('[0-9a-f]{40}', payload['revision']), 'EXACT_REVISION_REQUIRED')
        helper = '/opt/' + payload['config']['environment']['namespace'] + '/relay-managed-pool'
        auth['deploymentConfigSha256'] = hashlib.sha256((json.dumps(payload['config'], sort_keys=True,
            separators=(',', ':'), ensure_ascii=False) + '\n').encode()).hexdigest()
        result = subprocess.run([helper, payload['revision']], input=json.dumps(auth),
            text=True, capture_output=True, check=False)
        if result.returncode:
            codes = re.findall(r'^MANAGED_POOL_[A-Z_]{1,100}$', result.stderr, re.MULTILINE)
            pool.require(False, codes[-1].removeprefix('MANAGED_POOL_') if codes else
                         'RECONCILIATION_UNPROVEN_INSPECT_BEFORE_RETRY')
        pool.require(len(result.stdout.encode()) <= 16384 and
                     result.stdout.startswith('MANAGED_POOL_RESULT='), 'RESULT_UNPROVEN_INSPECT_BEFORE_RETRY')
        public = json.loads(result.stdout.removeprefix('MANAGED_POOL_RESULT='))
        ids = {member['id'] for member in contract['members']}
        pool.require(isinstance(public, dict) and set(public) == {'capacity', 'ready', 'draining', 'retired'}
            and type(public['capacity']) is int and public['capacity'] == contract['desiredCapacity']
            and all(isinstance(public[key], list) and len(public[key]) <= 32
                    and all(isinstance(member, str) and member in ids for member in public[key])
                    for key in ['ready', 'draining', 'retired']), 'RESULT_UNPROVEN_INSPECT_BEFORE_RETRY')
        print('MANAGED_POOL_RESULT=' + json.dumps(public, sort_keys=True))
        sys.exit(0)
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
    pending = json.dumps(payload)
    require(len(pending.encode()) <= OWNER_POOL_INPUT_BYTES, 'OWNER_PREFLIGHT_INPUT_SIZE')
    return pending, digest


def _owner_transport(target, key, pending, guard, *, local, extra_guard):
    """One bounded stdin exchange under the existing owner deployment guards."""
    command = ['/usr/bin/python3', '-I', '-c', OWNER_POOL_SCRIPT]
    require(local or guard is not None and guard.poll() is None, 'HOST_GUARD_LOST')
    process = TargetProcess(target, key, command, local=local)
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


def reconcile_pool(target, key, config, revision, guard=None, *, local=False, extra_guard=None):
    """Sign and invoke the installed reconciliation helper entirely on the target."""
    require(re.fullmatch('[0-9a-f]{40}', revision), 'EXACT_REVISION_REQUIRED')
    pending, _ = _owner_payload(config, 'reconcile', revision)
    output = _owner_transport(target, key, pending, guard, local=local, extra_guard=extra_guard)
    require(output.startswith('MANAGED_POOL_RESULT=') and len(output) <= 16384,
            'RESULT_UNPROVEN_INSPECT_BEFORE_RETRY')
    result = json.loads(output.removeprefix('MANAGED_POOL_RESULT='))
    require(result.get('capacity') == config['consumer']['generalRunnerPool']['desiredCapacity'],
            'RESULT_CAPACITY_UNPROVEN')
    return output.strip()
