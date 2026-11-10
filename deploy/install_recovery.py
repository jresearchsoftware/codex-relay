"""Read-only same-target lifecycle recovery proof under the installer's mutexes.

The installed admission reader owns containment and digest validation. This
adapter neither changes its gate nor invents completion of a retained attempt.
"""
import json
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess

import clean_reinstall as retained

REVISION = re.compile(r'[0-9a-f]{40}')
UUID = re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')
DIGEST = re.compile(r'[0-9a-f]{64}')
OPERATION_BLOCKER = 'production-operation-recovery-present;inspect-before-retry'


def require(condition, code):
    if not condition:
        raise ValueError('RELAY_INSTALL_RECOVERY_' + code)


def provisional_inventory(report):
    """Permit strategy selection only; the original report still needs proof."""
    if (report.get('blockers') == [OPERATION_BLOCKER]
            and report.get('installed', {}).get('status') == 'present'):
        return {**report, 'blockers': []}
    return report


def proved_inventory(report, proof, revision, expected_installed):
    """Use only a fresh, exact recovery proof to pass its matching record."""
    if proof is None:
        return report
    require(isinstance(proof, dict) and proof.keys() in [ {'operationId', 'target', 'installedRevision'},
                {'operationId', 'target', 'installedRevision', 'predispatchBridge'}]
            and UUID.fullmatch(proof.get('operationId', '')) and proof['target'] == revision
            and proof['installedRevision'] == expected_installed
            and report.get('installed', {}).get('status') == 'present'
            and report['installed'].get('revision') == expected_installed, 'INVENTORY_BINDING_CHANGED')
    return provisional_inventory(report)


def original_record_digest(raw):
    # Use the original producer's actual JSON.stringify representation,
    # including Unicode, numeric keys and JS number formatting edge cases.
    program = ('import{createHash}from"node:crypto";const chunks=[];let size=0;'
        'for await(const c of process.stdin){size+=c.length;if(size>524288)throw Error();chunks.push(c);}'
        'const r=JSON.parse(Buffer.concat(chunks));delete r.predispatchRecovery;'
        'process.stdout.write(createHash("sha256").update(JSON.stringify(r)).digest("hex"));')
    result = subprocess.run(['/usr/bin/node', '--input-type=module', '-e', program], input=raw,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=30,
        env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'})
    require(result.returncode == 0 and re.fullmatch(rb'[a-f0-9]{64}', result.stdout),
            'PREDISPATCH_BRIDGE_ORIGINAL_UNPROVEN')
    return result.stdout.decode()


def predispatch_bridge_binding(paths, config, gate, status, revision, root, owner_uid):
    """Read-only classification of the existing staged operation snapshot.

    No target Python is imported. A later same-lease recovery rechecks native
    authorization and every actual sealed byte before finalization.
    """
    stage = paths['install'] / 'releases' / ('.stage-' + gate['operationId'])
    snapshot_path = stage / 'old-installation.json'
    if not retained.present(snapshot_path):
        return None
    read = lambda path: retained._recovery_bytes(path, root, owner_uid, owner_uid, private=True)
    snapshot = retained._recovery_json(read(snapshot_path))
    binding = snapshot.get('predispatchBridge')
    if binding is None:
        return None
    keys = {'version', 'operationId', 'target', 'previousRevision', 'runId', 'attemptId', 'authorizationId',
            'predispatchBinding', 'sourceIdentity', 'stageReceiptSha256', 'consumerSha256', 'writerWrapperSha256'}
    require(isinstance(binding, dict) and binding.keys() == keys and binding['version'] == 1
            and snapshot.get('operationId') == gate['operationId'] == binding['operationId']
            and snapshot.get('target') == revision == binding['target']
            and REVISION.fullmatch(binding.get('previousRevision', ''))
            and type(binding.get('runId')) is int and binding['runId'] > 0
            and binding.get('attemptId') == 'run-' + str(binding['runId'])
            and type(binding.get('authorizationId')) is int and binding['authorizationId'] > 0
            and binding.get('sourceIdentity', {}).get('revision') == revision
            and (isinstance(gate.get('previousActive'), dict)
                 or gate.get('previousActive') is None
                 and Path(os.readlink(paths['install'] / 'current')).name == binding['previousRevision'])
            and status.get('active') in [[], [binding['runId']]] and status.get('unknown') == []
            and all(DIGEST.fullmatch(binding.get(key, '')) for key in
                    ['stageReceiptSha256', 'consumerSha256', 'writerWrapperSha256']), 'PREDISPATCH_BRIDGE_UNPROVEN')
    receipt_raw = read(stage / 'receipt.json')
    receipt = retained._recovery_json(receipt_raw)
    require(hashlib.sha256(receipt_raw).hexdigest() == binding['stageReceiptSha256']
            and receipt.get('sourceIdentity') == binding['sourceIdentity'], 'PREDISPATCH_BRIDGE_STAGE_CHANGED')
    original = binding['predispatchBinding']
    require(isinstance(original, dict) and original.get('operation') == 'finalize-predispatch'
            and original.get('runId') == binding['runId'] and original.get('attemptId') == binding['attemptId']
            and DIGEST.fullmatch(original.get('recordDigest', ''))
            and re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', original.get('repository', '')),
            'PREDISPATCH_BRIDGE_ORIGINAL_UNPROVEN')
    claim = Path(config['consumer']['paths']['claimRoot'])
    if not claim.is_relative_to(root):
        claim = root / str(claim).lstrip('/')
    store = claim / 'publication-v2'
    candidates = [store / (str(binding['runId']) + '.json'),
                  store / 'repositories' / original['repository'] / (str(binding['runId']) + '.json')]
    # This native v4 bridge retains the current consumer digest. Historical
    # SERIAL records are never reinterpreted or rebound through this path.
    records = [read(path) for path in candidates if retained.present(path)]
    require(len(records) == 1, 'PREDISPATCH_BRIDGE_ORIGINAL_UNPROVEN')
    record = retained._recovery_json(records[0])
    recovered = record.get('predispatchRecovery')
    require(original_record_digest(records[0]) == original['recordDigest']
            and record.get('envelope', {}).get('runId') == binding['runId']
            and record.get('envelope', {}).get('repository') == original['repository']
            and record.get('envelope', {}).get('consumerDigest') == gate['consumerDigest'],
            'PREDISPATCH_BRIDGE_ORIGINAL_CHANGED')
    if recovered:
        require(recovered.get('status') == 'finalized' and recovered.get('authorizationId') == binding['authorizationId']
                and recovered.get('binding') == original and status['active'] == [],
                'PREDISPATCH_BRIDGE_RECOVERY_CHANGED')
    return binding, bool(recovered)


def _source_tree(source, root, owner_uid):
    """Reprove the actual installed graph without a deployment snapshot gate."""
    components = {'consumer', 'controller', 'contracts', 'runtime', 'reviewer'}
    files = total = 0
    canonical = '/' + str(source.relative_to(root))
    for directory, directories, names in os.walk(source, followlinks=False):
        retained.protected(Path(directory), root, owner_uid, directory=True)
        for name in [*directories, *names]:
            path = Path(directory) / name
            info = path.lstat()
            files += 1
            total += info.st_size
            require(files <= 10000 and total <= 64 * 1024 * 1024, 'SOURCE_LIMIT')
            if stat.S_ISLNK(info.st_mode):
                relative = path.relative_to(source).parts
                target = os.readlink(path)
                component = target.removeprefix(canonical + '/')
                require(info.st_uid == owner_uid and info.st_nlink == 1
                        and len(relative) >= 2 and relative[0] not in components | {'deploy'}
                        and component in components and target == canonical + '/' + component,
                        'SOURCE_ALIAS_UNPROVEN')
                retained.protected(source / component, root, owner_uid, directory=True)
            else:
                retained.protected(path, root, owner_uid, directory=stat.S_ISDIR(info.st_mode))


def inspect(config, revision, expected_installed, *, root=Path('/'), owner_uid=0,
            runner=subprocess.run, resource_probe=None):
    """Return the original UUID only for a qualified same-target recovery.

    Fixtures may supply a private filesystem root and read-only native adapters.
    The transported owner interface always uses the actual host root and code.
    """
    require(REVISION.fullmatch(revision or '') and REVISION.fullmatch(expected_installed or ''),
            'IDENTITY_INVALID')
    root = Path(root)
    paths = retained.namespace_paths(config, root)
    current = paths['install'] / 'current'
    retained.protected(paths['install'], root, owner_uid, directory=True)
    before = current.lstat()
    require(stat.S_ISLNK(before.st_mode) and before.st_uid == owner_uid, 'CURRENT_UNPROVEN')
    expected = paths['install'] / 'releases' / expected_installed
    link = os.readlink(current)
    require(link in ['/' + str(expected.relative_to(root)), 'releases/' + expected_installed],
            'CURRENT_CHANGED')
    retained._recovery_identity(expected, expected_installed, root, owner_uid, owner_uid)
    _source_tree(expected / 'reviewed-source', root, owner_uid)
    for path in [paths['journal'], paths['journal'].with_name(paths['journal'].name + '.next')]:
        require(not retained.present(path), 'REINSTALL_REQUIRES_DIAGNOSIS')
    operation = None
    if retained.present(paths['operation']):
        raw = retained._recovery_bytes(paths['operation'], root, owner_uid, owner_uid, private=True)
        operation = retained._recovery_json(raw)
        require(operation == {'schemaVersion': '1', 'state': 'RECOVERY_REQUIRED',
                              'phase': 'apply', 'target_head': revision}, 'BACKEND_TARGET_CHANGED')
    proof = resource_probe or retained.prove_git_resource_boundary
    proof(config, root=root, owner_uid=owner_uid)
    claim = Path(config['consumer']['paths']['claimRoot'])
    if not claim.is_relative_to(root):
        claim = root / str(claim).lstrip('/')
    gate_name = ('admission-pool-v1.json'
                 if retained.present(paths['config'] / 'serial-pool-compat-v1.json') else 'admission-v1.json')
    gate = retained._recovery_json(retained._recovery_bytes(
        claim / gate_name, root, owner_uid, owner_uid, private=True))
    require(gate.keys() == {'version', 'consumerDigest', 'phase', 'operationId', 'target',
                            'previousActive', 'verifiedRevision'}
            and type(gate['version']) is int and gate['version'] == 1
            and isinstance(gate.get('consumerDigest'), str) and DIGEST.fullmatch(gate['consumerDigest']),
            'ADMISSION_UNPROVEN')
    if gate.get('phase') == 'open':
        # No recovery authority is granted here. A valid manually drifted
        # consumer may not load under this old digest; the ordinary drift
        # helper must authenticate that original context before quiescing.
        require(operation is None and all(gate[key] is None for key in
                ['operationId', 'target', 'previousActive', 'verifiedRevision']), 'BACKEND_REQUIRES_DIAGNOSIS')
        after = current.lstat()
        require((before.st_dev, before.st_ino, before.st_mtime_ns, before.st_ctime_ns)
                == (after.st_dev, after.st_ino, after.st_mtime_ns, after.st_ctime_ns)
                and os.readlink(current) == link, 'CURRENT_CHANGED')
        return None
    require(gate.get('phase') in ['quiesced', 'applying', 'recovery-required'], 'REQUIRES_DIAGNOSIS')
    helper = paths['install'] / 'relay-admission'
    retained.protected(helper, root, owner_uid)
    result = runner([str(helper), 'status'], capture_output=True, text=True, timeout=60,
                    env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C', 'PYTHONDONTWRITEBYTECODE': '1'})
    require(result.returncode == 0, 'ADMISSION_UNPROVEN')
    status = retained._recovery_json(result.stdout)
    require(DIGEST.fullmatch(status.get('consumerDigest', '')), 'ADMISSION_UNPROVEN')
    after = current.lstat()
    require((before.st_dev, before.st_ino, before.st_mtime_ns, before.st_ctime_ns)
            == (after.st_dev, after.st_ino, after.st_mtime_ns, after.st_ctime_ns)
            and os.readlink(current) == link, 'CURRENT_CHANGED')
    require(status.get('phase') in ['quiesced', 'applying', 'recovery-required'] and UUID.fullmatch(status.get('operationId', ''))
            and status.get('target') == revision
            and status.get('verifiedRevision') is None
            and all(status.get(key) == value for key, value in gate.items()), 'REQUIRES_DIAGNOSIS')
    bridge = predispatch_bridge_binding(paths, config, gate, status, revision, root, owner_uid)
    if bridge is not None:
        binding, finalized = bridge
        require(expected_installed in [revision, binding['previousRevision']], 'PREDISPATCH_BRIDGE_CURRENT_CHANGED')
        require(not finalized or expected_installed == revision, 'PREDISPATCH_BRIDGE_CURRENT_CHANGED')
        if finalized and gate['phase'] == 'recovery-required':
            return {'operationId': status['operationId'], 'target': revision, 'installedRevision': expected_installed}
        return {'operationId': status['operationId'], 'target': revision,
                'installedRevision': expected_installed, 'predispatchBridge': binding}
    require(status['phase'] == 'recovery-required' and status['active'] == [] and status['unknown'] == [],
            'REQUIRES_DIAGNOSIS')
    return {'operationId': status['operationId'], 'target': revision, 'installedRevision': expected_installed}


def remote_probe(target, key, config, revision, expected_installed, guard, pool_guard=None):
    """Transport a fixed read-only classifier; never a caller-selected command."""
    from ansible_transport import run_target
    require(guard is not None and guard.poll() is None
            and (pool_guard is None or pool_guard.poll() is None), 'HOST_LOCK_LOST')
    clean_source = Path(retained.__file__).read_text()
    source = Path(__file__).read_text()
    program = ('import json,sys,types\n'
        'module=types.ModuleType("clean_reinstall");module.__file__="/owner-source/clean_reinstall.py"\n'
        'sys.modules["clean_reinstall"]=module\nexec(' + repr(clean_source) + ',module.__dict__)\n'
        'context={"__name__":"relay_install_recovery"}\nexec(' + repr(source) + ',context)\n'
        'try:\n value=json.load(sys.stdin); result=context["inspect"](value["config"],value["revision"],'
        'value["installed"]);print(json.dumps(result))\n'
        'except Exception as error:\n code=str(error);print(code if isinstance(error,ValueError) and '
        '__import__("re").fullmatch(r"(?:RELAY_INSTALL_RECOVERY_|REINSTALL_)[A-Z_]{1,96}",code) '
        'else "RELAY_INSTALL_RECOVERY_UNPROVEN",file=sys.stderr);sys.exit(1)\n')
    result = run_target(target, key, ['/usr/bin/python3', '-I', '-c', program],
        input=json.dumps({'config': config, 'revision': revision, 'installed': expected_installed}), timeout=120)
    require(guard.poll() is None and (pool_guard is None or pool_guard.poll() is None), 'HOST_LOCK_LOST')
    require(result.returncode == 0, 'UNPROVEN')
    value = json.loads(result.stdout)
    require(value is None or isinstance(value, dict) and value.keys() in [ {'operationId', 'target', 'installedRevision'},
                {'operationId', 'target', 'installedRevision', 'predispatchBridge'}]
            and UUID.fullmatch(value.get('operationId', '')) and value['target'] == revision
            and value['installedRevision'] == expected_installed, 'RESULT_INVALID')
    return value


def revalidate(proof, target, key, config, revision, expected_installed, guard, pool_guard=None):
    repeated = remote_probe(target, key, config, revision, expected_installed, guard, pool_guard)
    require(proof is not None and repeated == proof, 'PROOF_CHANGED')
    return repeated


def resume_predispatch_bridge(proof, request, target, key, config, guard, pool_guard=None, *, source_root):
    """Continue only the exact protected frontier, using verified staged code.

    The root request/token travels only on stdin. The fixed trusted verifier is
    transported from the accepted controller, before any staged import executes.
    """
    from ansible_transport import run_target
    require(guard is not None and guard.poll() is None and (pool_guard is None or pool_guard.poll() is None), 'HOST_LOCK_LOST')
    binding = proof.get('predispatchBridge')
    require(isinstance(binding, dict) and request.get('operation') == 'finalize-predispatch'
            and request.get('runId') == binding['runId'] and request.get('attemptId') == binding['attemptId']
            and request.get('authorizationId') == binding['authorizationId'], 'PREDISPATCH_BRIDGE_REQUEST_CHANGED')
    stage_source = (Path(source_root) / 'deploy/ansible/roles/relay_artifacts/files/relay-intent-stage.py').read_text()
    program = ('import json,sys,uuid\nfrom pathlib import Path\n'
        'v=json.load(sys.stdin);p=v["proof"];b=p["predispatchBridge"];ns={"__name__":"verified_stage"}\n'
        'exec(' + repr(stage_source) + ',ns)\n'
        'install=Path("/opt")/v["config"]["environment"]["namespace"];stage=install/"releases"/(".stage-"+p["operationId"])\n'
        'ns["run"]("verify",stage,{"operationId":p["operationId"],"sourceIdentity":b["sourceIdentity"]})\n'
        'assert ns["hash_bytes"](ns["read_regular"](stage/"receipt.json"))==b["stageReceiptSha256"]\n'
        'source=stage/"release/reviewed-source";sys.path.insert(0,str(source/"deploy"))\n'
        'from config import compile_inputs\nfrom install_preflight import PreparedInstall\n'
        'values=compile_inputs(v["config"]);values["relay_intent_expected_installed_revision"]=p["installedRevision"]\n'
        'prepared=PreparedInstall({"host":"localhost","connection":"local"},Path("/unused"),values,b["sourceIdentity"],p["operationId"],local=True)\n'
        'prepared.lease_path=str(stage/("writer-lock-continue-"+str(uuid.uuid4())+".json"))\n'
        'try:\n prepared.desired();prepared.consumer();prepared.captured=True\n'
        ' prepared.bridge_predispatch(v["request"],lambda:None,continuation=True)\n'
        ' prepared.execute([*prepared.admission_prefix(),"phase","--operation",p["operationId"],"--phase","recovery-required"])\n'
        ' print(json.dumps({"operationId":p["operationId"],"target":p["target"],"installedRevision":p["target"]}))\n'
        'finally:\n prepared.release_writer()\n')
    result = run_target(target, key, ['/usr/bin/python3', '-I', '-c', program],
        input=json.dumps({'proof': proof, 'request': request, 'config': config}), timeout=600)
    require(guard.poll() is None and (pool_guard is None or pool_guard.poll() is None), 'HOST_LOCK_LOST')
    require(result.returncode == 0 and len(result.stdout) <= 4096, 'PREDISPATCH_BRIDGE_CONTINUATION_FAILED')
    value = json.loads(result.stdout)
    require(value == {'operationId': proof['operationId'], 'target': proof['target'], 'installedRevision': proof['target']},
            'PREDISPATCH_BRIDGE_CONTINUATION_CHANGED')
    return value
