"""Finish only the authenticated consumer-publication frontier of a reserved Apply.

The prior controller/final Git pair and immutable backend stay frozen. This
controller supplies corrected observation/publication code, then runs the
existing installation tail and its complete runtime/identity validation.
"""
from contextlib import ExitStack
import inspect as source_inspect
import json
from pathlib import Path
import re
import subprocess
import tempfile
import uuid

import bounded_recovery as bounded
from config import loads, compile_inputs
from ansible_transport import connection_vars, backend_environment, run_target


def require(value, code):
    if not value:
        raise ValueError('PARTIAL_INSTALL_' + code)


def inspect(config, operation, retained, *, root=Path('/'), owner_uid=0):
    """Read only; an on-disk final product is explicitly not running proof."""
    require(bounded.UUID.fullmatch(operation or '') and bounded.SHA.fullmatch(retained or ''), 'ARGUMENTS_INVALID')
    p = bounded.paths(config, {'operationId': operation}, root)
    receipt = bounded.load_receipt(p['receipt'], root, owner_uid)
    binding = receipt['binding']
    require(binding['operationId'] == operation and binding['retainedTarget'] == retained
            and receipt['state'] == 'reserved', 'RESERVED_OPERATION_REQUIRED')
    require(bounded.inspect(config, binding, root=root, owner_uid=owner_uid) == receipt, 'ORIGINAL_PROOF_CHANGED')
    bounded.final_installation(p['install'].name, receipt, root, owner_uid)
    gate = bounded.gate_value(bounded.read(p['gate'], root, owner_uid, private=True), binding)
    require(gate['phase'] == 'applying' and gate['target'] == binding['desiredRevision'], 'FRONTIER_UNSUPPORTED')
    backup = p['config'] / ('consumer-before-' + operation + '.json')
    require(bounded.sha(bounded.read(backup, root, owner_uid, private=True))
            == receipt['original']['consumerSha256'], 'BEFORE_BACKUP_CHANGED')
    release = p['install'] / 'releases' / binding['desiredRevision']
    manifest, snapshot, _ = bounded.installed(release, binding['desiredRevision'], root, owner_uid)
    source = bounded.decode(bounded.read(release / 'reviewed-source/.relay-source.json', root, owner_uid))
    require(source.get('revision') == binding['desiredRevision'] and snapshot == config, 'FROZEN_PAIR_CHANGED')
    current = bounded.read(p['config'] / 'consumer.json', root, owner_uid)
    desired = bounded.read(p['config'] / ('.consumer-' + operation + '.desired.json'), root, owner_uid, private=True)
    require(current == desired, 'LIVE_CONSUMER_CHANGED')
    return {'receipt': receipt, 'gate': gate, 'manifest': manifest, 'sourceIdentity': source,
            'consumerSha256': bounded.sha(current)}


def remote_inspect(target, key, config, operation, retained):
    # Same bounded protected transport as the original recovery adapter. No
    # worker input or installed old controller chooses executable code here.
    program = ('import json,sys\ncontext={"__name__":"bounded_observer"}\nexec('
        + repr(Path(bounded.__file__).read_text()) + ',context)\n'
        'import types\nm=types.ModuleType("bounded_recovery");m.__dict__.update(context);'
        'sys.modules["bounded_recovery"]=m\n'
        'from pathlib import Path\nscope={"bounded":m,"Path":Path}\nexec('
        + repr(source_inspect.getsource(require) + '\n' + source_inspect.getsource(inspect)) + ',scope)\n'
        'try:\n p=json.load(sys.stdin);print(json.dumps(scope["inspect"](**p)))\n'
        'except Exception as error:\n import re\n code=str(error);'
        'print(code if re.fullmatch(r"(?:PARTIAL_INSTALL|BOUNDED_RECOVERY)_[A-Z_]{1,100}",code) '
        'else "PARTIAL_INSTALL_PROOF_UNAVAILABLE",file=sys.stderr);sys.exit(1)\n')
    result = run_target(target, key, ['/usr/bin/python3', '-I', '-c', program],
        input=json.dumps({'config': config, 'operation': operation, 'retained': retained}), timeout=180)
    if result.returncode:
        codes = re.findall(r'(?m)^(?:PARTIAL_INSTALL|BOUNDED_RECOVERY)_[A-Z_]{1,100}$', result.stderr)
        raise ValueError(codes[-1] if codes else 'PARTIAL_INSTALL_PROOF_UNAVAILABLE')
    require(len(result.stdout.encode()) <= bounded.LIMIT, 'PROOF_LIMIT')
    return bounded.decode(result.stdout)


def unchanged_tail(root, desired, controller):
    """This bounded frontier cannot install future unrelated template changes."""
    command = ['git', '-c', 'core.hooksPath=/dev/null', '-C', str(root)]
    require(subprocess.run([*command, 'merge-base', '--is-ancestor', desired, controller],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0, 'DESIRED_SOURCE_NOT_ANCESTOR')
    changed = subprocess.check_output([*command, 'diff', '--name-only', desired, controller, '--',
        'deploy/config.py', 'deploy/ansible'], text=True).splitlines()
    allowed = {'deploy/ansible/site.yml', 'deploy/ansible/scripts/publish_git_consumer.py',
        'deploy/ansible/roles/relay_controller/tasks/runtime-entrypoints.yml',
        'deploy/ansible/tasks/upgrade-lifecycle-activate.yml',
        'deploy/ansible/tasks/upgrade-lifecycle-validation.yml'}
    require(all(path in allowed or path.startswith('deploy/ansible/tests/') for path in changed),
            'INSTALLATION_TAIL_CHANGED')


def admission(config, source, lease, operation, command):
    """Fixed final commands with independent controller and frozen target."""
    import os
    from writer_lock_lease import verify
    root = Path('/')
    source = Path(source)
    bounded.protect(source, root, 0, directory=True)
    identity = bounded.decode(bounded.read(source / '.relay-source.json', root, 0))
    p = bounded.paths(config, {'operationId': operation}, root)
    receipt = bounded.load_receipt(p['receipt'], root, 0)
    binding = receipt['binding']
    require(binding['operationId'] == operation and receipt['state'] in ['backend-complete', 'complete'], 'FINAL_RECEIPT_REQUIRED')
    bounded.final_installation(p['install'].name, receipt, root, 0)
    verify(lease, p['gate'].parent / 'publication-v2.lock', operation=operation,
        target=identity['revision'], consumer_digest=receipt['desiredDigest'])
    require(command in ['verify', 'resume', 'status']
            and (command != 'resume' or receipt['state'] == 'complete'), 'FINAL_COMMAND_INVALID')
    arguments = {'verify': ['phase', '--operation', operation, '--phase', 'verified', '--revision', binding['desiredRevision']],
        'resume': ['resume', '--operation', operation], 'status': ['status']}[command]
    result = subprocess.run(['/usr/bin/node', str(source / 'controller/src/admission-cli.mjs'), *arguments],
        env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C',
             'RELAY_CONSUMER_CONFIG': str(p['config'] / 'consumer.json'),
             'RELAY_REPOSITORY': config['environment'].get('repository', config['consumer'].get('repository'))},
        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=180)
    require(result.returncode == 0 and len(result.stdout) <= 1024 * 1024, 'FINAL_ADMISSION_FAILED')
    return bounded.decode(result.stdout)


def run(args, root, identity, *, guard_factory=None):
    from intent_install import qualify_identity, hold_install_guard, release_guard
    from install_preflight import PreparedInstall
    require(args.authorize_install_recovery and args.continue_install_recovery
            and args.resolved_revision == identity['revision'], 'EXPLICIT_CONTROLLER_REQUIRED')
    raw = args.config.read_bytes()
    config = loads(raw.decode(), root)
    target = dict(config['target'])
    if getattr(args, 'connection', None) is not None:
        target['connection'] = args.connection
    key = Path(target.get('identityFile', '/unused-local-identity')).expanduser()
    qualify_identity(target, key)
    factory = guard_factory or (lambda target, key, namespace: hold_install_guard(target, key, namespace, root))
    args.log_root.mkdir(parents=True, exist_ok=True)
    with ExitStack() as stack:
        host = factory(target, key, config['environment']['namespace'])
        stack.callback(release_guard, host)
        pool = None
        if 'generalRunnerPool' in config['consumer']:
            pool = factory(target, key, 'codex-relay-pool-' + config['environment']['generalRunner']['name'])
            stack.callback(release_guard, pool)
        def proof():
            require(host.poll() is None and (pool is None or pool.poll() is None), 'HOST_LOCK_LOST')
            require(args.config.read_bytes() == raw, 'CONFIG_CHANGED')
            return remote_inspect(target, key, config, args.install_recovery_operation, args.install_recovery_target)
        observed = proof()
        receipt, gate = observed['receipt'], observed['gate']
        binding = receipt['binding']
        desired = binding['desiredRevision']
        unchanged_tail(root, desired, identity['revision'])
        require(observed['sourceIdentity']['revision'] == desired, 'DESIRED_SOURCE_CHANGED')
        values = compile_inputs(config)
        values.update(relay_consumer_config_path=values['relay_config_root'] + '/consumer.json',
            relay_deployment_profile='production', relay_review_root=str(root),
            relay_admission_operation_id=binding['operationId'], relay_git_desired_state=True,
            relay_git_config_receipt=binding['gitConfigReceipt'], relay_bounded_recovery_binding=binding,
            relay_deployment_contract=observed['manifest']['deploymentContract'],
            relay_installation_state=observed['manifest'].get('installationState', {}),
            relay_source_identity=observed['sourceIdentity'], relay_requested_revision=desired,
            relay_consumer_revision=observed['manifest']['consumerRevision'],
            relay_production_operation_phase='apply', relay_production_operation_target_head=desired,
            relay_production_exact_head=desired, relay_reviewer_activation_exact_head=desired,
            relay_upgrade_requested=True, relay_upgrade_lifecycle_managed=True,
            relay_admission_recovery_authorized=True, relay_owner_apply_requested=False,
            relay_intent_expected_installed_revision=desired, relay_service_state_management='preserve',
            relay_runner_service_state_management='preserve', relay_service_activation_authorized=False,
            relay_runner_registration_enabled=False, relay_runner_registration_authorized=False,
            relay_production_runner_enable_authorized=False, relay_service_enabled=False,
            relay_runner_service_enabled=False, relay_production_defer_lifecycle=False,
            relay_consumer_publication_continuation=True)
        staging_id = str(uuid.uuid4())
        preparation = PreparedInstall(target, key, values, identity, staging_id)
        stack.callback(preparation.release_writer)
        preparation.create()
        with tempfile.TemporaryDirectory(prefix='relay-partial-continue-') as temporary:
            work = Path(temporary)
            archive = work / 'controller.tar'
            with archive.open('wb') as output:
                subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', '-C', str(root),
                    'archive', identity['revision']], stdout=output, check=True)
            def backend(name, selected):
                require(host.poll() is None and (pool is None or pool.poll() is None), 'HOST_LOCK_LOST')
                inventory = {'all': {'children': {'relay': {'hosts': {target['host']: {
                    **selected, **connection_vars(target, key)}}}}}}
                (work / 'inventory.json').write_text(json.dumps(inventory))
                log_path = args.log_root / ('continue-' + binding['operationId'] + '-' + name.removesuffix('.yml') + '.log')
                from importlib.util import spec_from_file_location, module_from_spec
                spec = spec_from_file_location('partial_backend', root / 'deploy/relay-deploy.py')
                engine = module_from_spec(spec); spec.loader.exec_module(engine)
                with log_path.open('w') as log:
                    code = engine.run_backend(['ansible-playbook', '-i', str(work / 'inventory.json'),
                        str(root / 'deploy/ansible' / name), '--limit', target['host']],
                        root / 'deploy/ansible', backend_environment(), log, host, pool)
                text = log_path.read_text()
                require(code == 0 and 'failed=0' in text, 'BACKEND_FAILED_INSPECT_LOG')
                return text
            stage_values = {**values, 'relay_source_identity': identity, 'relay_source_archive': str(archive),
                'relay_intent_stage_root': preparation.stage, 'relay_intent_stage_operation': staging_id,
                'relay_intent_stage_source_only': True, 'relay_compatibility_links': []}
            backend('relay-intent-stage.yml', stage_values)
            # Reprove the exact frontier after staging and before any effect.
            require(proof() == observed, 'FRONTIER_CHANGED')
            preparation.operation = binding['operationId']
            preparation.initial = {'claimRoot': values['relay_writer_claim_root'],
                'lockPath': values['relay_writer_claim_root'] + '/publication-v2.lock',
                'baselineDigest': gate['consumerDigest']}
            preparation.lock_writer()
            publisher = preparation.source + '/deploy/ansible/scripts/publish_git_consumer.py'
            desired_path = values['relay_config_root'] + '/.consumer-' + binding['operationId'] + '.desired.json'
            digest_program = ('import{pathToFileURL}from"node:url";'
                'const m=await import(pathToFileURL(process.argv[1]));'
                'console.log(JSON.stringify(process.argv.slice(2).map(p=>m.consumerDigest(m.loadConsumer(p)))));')
            digests = preparation.execute(['/usr/bin/node', '--input-type=module', '-e', digest_program,
                preparation.source + '/consumer/consumer-config.mjs', values['relay_consumer_config_path'], desired_path])
            require(digests == [receipt['desiredDigest'], receipt['desiredDigest']], 'DESIRED_CONSUMER_CHANGED')
            # The authentic desired file survived this specific failure. No
            # reconstructed or host-derived desired configuration is accepted.
            result = preparation.execute(['/usr/bin/python3', '-I', publisher,
                '--source', preparation.source, '--controller-revision', identity['revision'],
                '--config-root', values['relay_config_root'], '--desired', desired_path,
                '--claim-root', values['relay_writer_claim_root'], '--repository', values['relay_github_repository'],
                '--operation', binding['operationId'], '--revision', desired,
                '--writer-lock-lease', preparation.lease_path])
            require(result.get('consumerDigest') == receipt['desiredDigest'], 'CONSUMER_TRANSITION_UNPROVEN')
            preparation.release_writer()
            values.update(relay_consumer_publication_source=preparation.source,
                relay_consumer_publication_controller=identity['revision'])
            text = backend('site.yml', values)
            require('PRODUCTION_APPLY_VALIDATED=' + desired in text, 'RUNTIME_VALIDATION_MISSING')
            # The standard tail verifies the running executable/services and
            # archives the unchanged original backend before this final gate.
            preparation.initial['baselineDigest'] = receipt['desiredDigest']
            preparation.lock_writer()
            final_command = ('import json,sys;sys.path.insert(0,sys.argv[1]);import partial_install_recovery as p;'
                'v=json.load(sys.stdin);print(json.dumps(p.admission(**v)))')
            def admitted(command):
                return preparation.execute(['/usr/bin/python3', '-I', '-c', final_command, preparation.source + '/deploy'],
                    payload={'config': config, 'source': preparation.source, 'lease': preparation.lease_path,
                             'operation': binding['operationId'], 'command': command})
            admitted('verify')
            finish = ('import json,sys;sys.path.insert(0,sys.argv[1]);import bounded_recovery as b;'
                'p=json.load(sys.stdin);probe=b.fixed_probe(p["config"],p["controllerBinding"],p["source"],p["lease"],p["desiredDigest"]);'
                'print(json.dumps(b.finalize(p["config"],p["binding"],p["proof"],admission_probe=probe)))')
            preparation.execute(['/usr/bin/python3', '-I', '-c', finish, preparation.source + '/deploy'],
                payload={'config': config, 'binding': binding, 'controllerBinding': {**binding,
                    'controllerRevision': identity['revision']}, 'proof': receipt, 'source': preparation.source,
                    'lease': preparation.lease_path, 'desiredDigest': receipt['desiredDigest']})
            admitted('resume')
            status = admitted('status')
            require(status['phase'] == 'open' and status['consumerDigest'] == receipt['desiredDigest']
                    and status['active'] == status['unknown'] == [], 'FINAL_ADMISSION_UNPROVEN')
            preparation.release_writer()
            print('RELAY_INSTALL_RESULT=' + json.dumps({'status': 'PASS', 'strategy': 'consumer-publication-continuation',
                'controller': identity['revision'], 'retainedTarget': binding['retainedTarget'],
                'product': desired, 'config': binding['gitConfigReceipt']['config_sha'],
                'operationId': binding['operationId'], 'admission': 'open'}, sort_keys=True), flush=True)
