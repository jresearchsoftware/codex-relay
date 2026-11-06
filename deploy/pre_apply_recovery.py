"""Continue the exact post-Begin/pre-publication pair with an accepted controller.

The original receipt is evidence, not mutable desired state. Product bytes come
from its original desired Git object; the corrected controller supplies only the
qualified orchestration and readers under the existing host/pool/Writer locks.
"""
from contextlib import ExitStack
import hashlib
import importlib.util
import inspect as source_inspect
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

import bounded_recovery as bounded
from config import loads


def require(value, code):
    if not value:
        raise ValueError('PRE_APPLY_RECOVERY_' + code)


def inspect(config, operation, retained, *, root=Path('/'), owner_uid=0):
    root = Path(root)
    p = bounded.paths(config, {'operationId': operation}, root)
    receipt = bounded.load_receipt(p['receipt'], root, owner_uid)
    binding = receipt['binding']
    require(binding['operationId'] == operation and binding['retainedTarget'] == retained
            and receipt['state'] == 'reserved', 'RESERVED_OPERATION_REQUIRED')
    require(bounded.inspect(config, binding, root=root, owner_uid=owner_uid) == receipt,
            'ORIGINAL_PROOF_CHANGED')
    current = p['install'] / 'current'
    require(os.readlink(current) in ['releases/' + retained,
            '/opt/' + p['install'].name + '/releases/' + retained], 'CURRENT_FRONTIER_CHANGED')
    gate = bounded.gate_value(bounded.read(p['gate'], root, owner_uid, private=True), binding)
    require(gate['phase'] in ['recovery-required', 'applying']
            and gate['target'] == binding['desiredRevision'], 'FRONTIER_UNSUPPORTED')
    bounded.backend_validate(p['record'], binding['desiredRevision'], operation,
                             root=root, owner_uid=owner_uid, expected_backend_absent=False)
    consumer = bounded.read(p['config'] / 'consumer.json', root, owner_uid)
    require(bounded.sha(consumer) == receipt['original']['consumerSha256'], 'CONSUMER_PUBLICATION_STARTED')
    backup = p['config'] / ('consumer-before-' + operation + '.json')
    if backup.exists() or backup.is_symlink():
        require(bounded.read(backup, root, owner_uid, private=True) == consumer, 'BEFORE_BACKUP_CHANGED')
    return {'receipt': receipt, 'gate': gate,
            'receiptSha256': bounded.sha(bounded.read(p['receipt'], root, owner_uid, private=True))}


def remote_inspect(target, key, config, operation, retained):
    from ansible_transport import run_target
    program = ('import json,sys,types,os\nfrom pathlib import Path\n'
        'b=types.ModuleType("bounded_recovery");exec(' + repr(Path(bounded.__file__).read_text()) + ',b.__dict__)\n'
        'scope={"bounded":b,"Path":Path,"os":os}\nexec('
        + repr(source_inspect.getsource(require) + '\n' + source_inspect.getsource(inspect)) + ',scope)\n'
        'try:\n p=json.load(sys.stdin);print(json.dumps(scope["inspect"](**p)))\n'
        'except Exception as error:\n import re\n code=str(error);print(code if '
        're.fullmatch(r"(?:PRE_APPLY_RECOVERY|BOUNDED_RECOVERY)_[A-Z_]{1,100}",code) '
        'else "PRE_APPLY_RECOVERY_PROOF_UNAVAILABLE",file=sys.stderr);sys.exit(1)\n')
    result = run_target(target, key, ['/usr/bin/python3', '-I', '-B', '-c', program],
        input=json.dumps({'config': config, 'operation': operation, 'retained': retained}), timeout=180)
    require(result.returncode == 0 and len(result.stdout.encode()) <= bounded.LIMIT, 'FRONTIER_UNPROVEN')
    return bounded.decode(result.stdout)


def selected(target, key, config, retained):
    """Navigation only; run() independently proves the complete frontier."""
    from ansible_transport import run_target
    namespace = config['environment']['namespace']
    require(__import__('re').fullmatch('[a-z][a-z0-9-]{0,30}', namespace)
            and bounded.SHA.fullmatch(retained or ''), 'ARGUMENTS_INVALID')
    program = ('import json,os,sys\np=json.load(sys.stdin);'
        'v=os.readlink("/opt/"+p["namespace"]+"/current");'
        'print(json.dumps(v in ["releases/"+p["retained"],'
        '"/opt/"+p["namespace"]+"/releases/"+p["retained"]]))')
    result = run_target(target, key, ['/usr/bin/python3', '-I', '-c', program],
        input=json.dumps({'namespace': namespace, 'retained': retained}), timeout=30)
    require(result.returncode == 0 and result.stdout.strip() in ['true', 'false'], 'CURRENT_UNPROVEN')
    return json.loads(result.stdout)


def run(args, root, identity, *, guard_factory=None):
    args._pre_apply_inner = None
    args._pre_apply_binding = None
    try:
        return _run(args, root, identity, guard_factory=guard_factory)
    except Exception as error:
        inner = args._pre_apply_inner
        binding = args._pre_apply_binding or {}
        code = str(error).split(';')[0]
        if not re.fullmatch(r'[A-Z][A-Z0-9_]{1,160}', code):
            code = 'PRE_APPLY_RECOVERY_PROOF_UNAVAILABLE'
        failure = {'status': 'FAIL', 'strategy': 'pre-apply-continuation',
            'controller': identity['revision'], 'target': binding.get('desiredRevision', 'unavailable'),
            'installed': binding.get('installedRevision', 'unavailable'),
            'operationId': args.install_recovery_operation,
            'stage': getattr(inner, '_intent_failure_stage', 'protected-frontier'), 'cause': code,
            'hostMutation': 'unknown' if getattr(inner, '_intent_mutation_started', False) else False,
            'automaticRetrySafe': False, 'recovery': 'same-operation-evidence-requires-readback',
            'next': 'Inspect the named stage and original operation before retrying; preserve the frozen pair, receipt and history.'}
        if getattr(inner, '_intent_log_path', None):
            failure['log'] = inner._intent_log_path
        print('RELAY_INSTALL_FAILURE=' + json.dumps(failure, sort_keys=True), flush=True)
        raise ValueError(code) from None


def _run(args, root, identity, *, guard_factory=None):
    from intent_install import qualify_identity, hold_install_guard, release_guard, phase_arguments
    from partial_install_recovery import accepted_controller, unchanged_tail
    root = Path(root)
    require(args.authorize_install_recovery and args.continue_install_recovery
            and args.resolved_revision == identity['revision'], 'EXPLICIT_CONTROLLER_REQUIRED')
    raw = args.config.read_bytes()
    config = loads(raw.decode(), root)
    target = dict(config['target'])
    if getattr(args, 'connection', None) is not None:
        target['connection'] = args.connection
    key = Path(target.get('identityFile', '/unused-local-identity')).expanduser()
    qualify_identity(target, key)
    def controller_unchanged():
        command = ['git', '-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=false', '-C', str(root)]
        require(subprocess.check_output([*command, 'rev-parse', 'HEAD'], text=True).strip() == identity['revision']
                and not subprocess.check_output([*command, 'status', '--porcelain', '--untracked-files=all'], text=True),
                'CONTROLLER_SOURCE_CHANGED')
    controller_unchanged()
    factory = guard_factory or (lambda target, key, namespace: hold_install_guard(target, key, namespace, root))
    with ExitStack() as stack:
        host = factory(target, key, config['environment']['namespace'])
        stack.callback(release_guard, host)
        pool = None
        if 'generalRunnerPool' in config['consumer']:
            pool = factory(target, key, 'codex-relay-pool-' + config['environment']['generalRunner']['name'])
            stack.callback(release_guard, pool)
        observed = remote_inspect(target, key, config, args.install_recovery_operation, args.install_recovery_target)
        receipt = observed['receipt']
        binding = receipt['binding']
        args._pre_apply_binding = binding
        require(hashlib.sha256(raw).hexdigest() == binding['gitConfigReceipt']['config_sha256'], 'CONFIG_BYTES_CHANGED')
        if getattr(args, 'retained_runner_maintenance', None) is not None:
            require(bounded.decode(args.retained_runner_maintenance.read_bytes()) == binding.get('runnerMaintenance'),
                    'MAINTENANCE_DECLARATION_CHANGED')
        acceptance = accepted_controller(root, binding, identity['revision'])
        unchanged_tail(root, binding['desiredRevision'], identity['revision'])
        # This frontier deliberately stages the original reader/runtime closure.
        # A controller needing changed Node/schema or registration-library code
        # cannot claim that executing the frozen closure applied those changes.
        unchanged = subprocess.check_output(['git', '-c', 'core.hooksPath=/dev/null', '-C', str(root),
            'diff', '--name-only', binding['desiredRevision'], identity['revision'], '--',
            'consumer', 'controller/src', 'runtime', 'contracts', 'reviewer',
            'deploy/managed_pool.py', 'deploy/runner_self_update.py', 'deploy/pool_authorization.py',
            'deploy/pool_eligibility.py'], text=True)
        require(not unchanged, 'FROZEN_READER_CONTRACT_CHANGED')
        # A separate clean Git checkout makes source_identity/archive select the
        # original product object. Never relabel corrected source as old bytes.
        with tempfile.TemporaryDirectory(prefix='relay-frozen-pre-apply-') as directory:
            frozen = Path(directory) / 'product'
            subprocess.run(['git', 'init', '-q', str(frozen)], check=True)
            command = ['git', '-c', 'core.hooksPath=/dev/null', '-C', str(frozen)]
            subprocess.run([*command, 'fetch', '-q', '--no-tags', str(root), binding['desiredRevision']], check=True)
            subprocess.run([*command, 'checkout', '-q', '--detach', binding['desiredRevision']], check=True)
            spec = importlib.util.spec_from_file_location('frozen_product_recovery', root / 'deploy/relay-deploy.py')
            engine = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(engine)
            engine.ROOT, engine.BACKEND = frozen, root / 'deploy/ansible'
            require(args.config.read_bytes() == raw and host.poll() is None
                    and (pool is None or pool.poll() is None), 'INPUT_OR_LOCK_CHANGED')
            require(remote_inspect(target, key, config, binding['operationId'], binding['retainedTarget']) == observed,
                    'FRONTIER_CHANGED')
            controller_unchanged()
            consumer = args.consumer_root or Path(subprocess.check_output(
                ['git', '-C', str(args.config.parent), 'rev-parse', '--show-toplevel'], text=True).strip())
            inner = phase_arguments(args, 'upgrade', binding['gitConfigReceipt'], consumer,
                                    binding['installedRevision'], host, pool)
            inner.resolved_revision = inner.requested_revision = binding['desiredRevision']
            inner.continue_install_recovery = False
            inner.retained_runner_maintenance = None
            inner.authorize_lifecycle_recovery = True
            inner.lifecycle_recovery_operation = binding['operationId']
            inner._intent_bounded_recovery = binding
            inner._intent_bounded_recovery_proof = receipt
            inner._intent_consumer = config['consumer']
            args._pre_apply_inner = inner
            engine.run(inner)
            result = {'status': 'PASS', 'strategy': 'pre-apply-continuation',
                'controller': identity['revision'], 'controllerAcceptance': acceptance,
                'product': binding['desiredRevision'], 'config': binding['gitConfigReceipt']['config_sha'],
                'operationId': binding['operationId'], 'originalReceiptSha256': observed['receiptSha256']}
    print('RELAY_INSTALL_RESULT=' + json.dumps(result, sort_keys=True), flush=True)
    return result
