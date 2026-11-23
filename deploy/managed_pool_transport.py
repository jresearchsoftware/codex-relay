"""Ansible transport of nonsecret pool requests and bounded target-local receipts."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from managed_pool import require
from ansible_transport import TargetProcess
from lifecycle import failure_reporting_source


OWNER_POOL_SOURCES = ['managed_pool', 'pool_eligibility', 'config', 'pool_migration',
                      'serial_pool_transition', 'serial_pool_host', 'serial_pool_installation', 'pool_authorization']
OWNER_POOL_INPUT_BYTES = 262144
OWNER_POOL_OUTPUT_BYTES = 16384


OWNER_POOL_SCRIPT = failure_reporting_source() + r'''import json, os, re, sys, types
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
    action = payload['action']
    pool.require(action in ['preflight', 'reconcile', 'pause', 'drain', 'restart', 'resume'], 'ACTION_UNSUPPORTED')
    installation = sys.modules['serial_pool_installation']
    contract = payload['contract']
    auth = sys.modules['pool_authorization'].installation_authorization(payload['config'])
    pool.require(pool.pool_contract(payload['config']) == contract
                 and all(auth[key] == contract[key] for key in ['organization', 'appId', 'installationId']),
                 'TOKEN_BINDING_INVALID')
    pool.require(isinstance(payload['targetDigest'], str)
                 and re.fullmatch('[0-9a-f]{64}', payload['targetDigest']), 'TARGET_DIGEST_UNPROVEN')
    github = pool.GitHub(auth['installationToken'], contract['organization'])
    if action in ['pause', 'drain', 'restart', 'resume']:
        import fcntl, stat
        from pathlib import Path
        operation = payload['operation']
        pool.require(re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', operation), 'MAINTENANCE_OPERATION_INVALID')
        root = Path('/var/lib/codex-relay-pools') / contract['name']
        pool.protected_parents(root)
        fd = os.open(root / 'pool.lock', os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(fd)
            pool.require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1
                         and stat.S_IMODE(info.st_mode) == 0o600, 'LOCK_UNSAFE')
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

            report = pool.maintenance(contract, pool.State(root), github, pool.Host(contract),
                operation=operation, action=action, owner_pid=payload['ownerPid'])
            print('MANAGED_POOL_MAINTENANCE=' + json.dumps(report, sort_keys=True))
        finally:
            os.close(fd)
        sys.exit(0)
    if action == 'reconcile':
        import hashlib, subprocess
        pool.require(re.fullmatch('[0-9a-f]{40}', payload['revision']), 'EXACT_REVISION_REQUIRED')
        helper = '/opt/' + payload['config']['environment']['namespace'] + '/relay-managed-pool'
        auth['deploymentConfigSha256'] = hashlib.sha256((json.dumps(payload['config'], sort_keys=True,
            separators=(',', ':'), ensure_ascii=False) + '\n').encode()).hexdigest()
        result = subprocess.run([helper, payload['revision']], input=json.dumps(auth),
            text=True, capture_output=True, check=False)
        if result.returncode:
            codes = re.findall(r'^MANAGED_POOL_[A-Z_]{1,100}$', result.stderr, re.MULTILINE)
            try:
                pool.require(False, codes[-1].removeprefix('MANAGED_POOL_') if codes else
                             'RECONCILIATION_UNPROVEN_INSPECT_BEFORE_RETRY')
            except Exception as error:
                raise error from subprocess.CalledProcessError(result.returncode, 'managed-pool-reconcile',
                    output=result.stdout, stderr=result.stderr)
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
    pool.require(payload['action'] == 'preflight', 'ACTION_UNSUPPORTED')
    github.qualify(contract)
    proof = installation.preflight(payload['config'], github, payload['targetDigest'])
    pool.require(proof is None or isinstance(proof, dict)
                 and proof.get('phase') == 'retired'
                 and not proof.get('completionRequired', False), 'SERIAL_TRANSITION_RETIRED')
    print('MANAGED_POOL_PREFLIGHT=PASS')
except Exception as error:
    report_failure(error, 'managed-pool-owner-transport')
    # Fixed public error codes only. Never print payload, config or credentials.
    import re
    code = str(error)
    print(code if re.fullmatch('MANAGED_POOL_[A-Z_]{1,100}', code) else
          'MANAGED_POOL_PREFLIGHT_UNPROVEN_INSPECT_BEFORE_RETRY', file=sys.stderr)
    sys.exit(1)
'''


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
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, check=False)
    if result.returncode != 0:
        try:
            require(False, 'TARGET_DIGEST_UNPROVEN')
        except Exception as error:
            raise error from subprocess.CalledProcessError(result.returncode, 'consumer-digest',
                output=result.stdout, stderr=result.stderr)
    require(len(result.stdout) <= 128, 'TARGET_DIGEST_UNPROVEN')
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
            cwd=backend, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=60, check=False)
        if result.returncode:
            try:
                require(False, 'TARGET_DIGEST_UNPROVEN')
            except Exception as error:
                raise error from subprocess.CalledProcessError(result.returncode, 'consumer-projection',
                    output=result.stdout, stderr=result.stderr)
        return json.loads(destination.read_text())


def _owner_payload(config, action, revision=None, operation=None, owner_pid=None):
    from managed_pool import pool_contract
    contract = pool_contract(config)
    source_root = Path(__file__).parent
    digest = consumer_digest(projected_consumer(config, source_root.parent), source_root.parent)
    payload = {'sources': {name: (source_root / (name + '.py')).read_text(encoding='utf-8')
                          for name in OWNER_POOL_SOURCES},
               'contract': contract, 'config': config, 'targetDigest': digest,
               'action': action, 'revision': revision}
    if operation is not None:
        payload.update(operation=operation, ownerPid=owner_pid)
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
            try:
                require(False, codes[-1].removeprefix('MANAGED_POOL_') if codes else 'OWNER_PREFLIGHT_UNPROVEN')
            except Exception as error:
                raise error from subprocess.CalledProcessError(process.returncode, 'owner-pool-target',
                    output=output, stderr=errors)
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
    require(output == 'MANAGED_POOL_PREFLIGHT=PASS\n', 'OWNER_PREFLIGHT_RESULT_UNPROVEN')
    return 'MANAGED_POOL_PREFLIGHT=PASS'


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


def maintain_pool(target, key, config, operation, action, guard=None, *, local=False, extra_guard=None):
    """Run the exact owner Apply's maintenance under the existing host/pool locks."""
    require(action in {'pause', 'drain', 'restart', 'resume'}, 'ACTION_UNSUPPORTED')
    owner_pid = os.getpid() if local or (target or {}).get('connection') == 'local' else None
    pending, _ = _owner_payload(config, action, operation=operation, owner_pid=owner_pid)
    output = _owner_transport(target, key, pending, guard, local=local, extra_guard=extra_guard)
    marker = 'MANAGED_POOL_MAINTENANCE='
    require(output.startswith(marker), 'MAINTENANCE_RESULT_UNPROVEN')
    result = json.loads(output.removeprefix(marker))
    require(result.get('operation') == operation and result.get('action') == action,
            'MAINTENANCE_RESULT_UNPROVEN')
    return result
