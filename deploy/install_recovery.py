"""Read-only same-target lifecycle recovery proof under the installer's mutexes.

The installed admission reader owns containment and digest validation. This
adapter neither changes its gate nor invents completion of a retained attempt.
"""
import json
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
    require(isinstance(proof, dict) and proof.keys() == {'operationId', 'target', 'installedRevision'}
            and UUID.fullmatch(proof.get('operationId', '')) and proof['target'] == revision
            and proof['installedRevision'] == expected_installed
            and report.get('installed', {}).get('status') == 'present'
            and report['installed'].get('revision') == expected_installed, 'INVENTORY_BINDING_CHANGED')
    return provisional_inventory(report)


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
    require(gate.get('phase') == 'recovery-required', 'REQUIRES_DIAGNOSIS')
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
    require(status.get('phase') == 'recovery-required' and UUID.fullmatch(status.get('operationId', ''))
            and status.get('target') == revision and status.get('active') == [] and status.get('unknown') == []
            and status.get('verifiedRevision') is None
            and all(status.get(key) == value for key, value in gate.items()), 'REQUIRES_DIAGNOSIS')
    return {'operationId': status['operationId'], 'target': revision,
            'installedRevision': expected_installed}


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
    require(value is None or isinstance(value, dict) and value.keys() == {'operationId', 'target', 'installedRevision'}
            and UUID.fullmatch(value.get('operationId', '')) and value['target'] == revision
            and value['installedRevision'] == expected_installed, 'RESULT_INVALID')
    return value


def revalidate(proof, target, key, config, revision, expected_installed, guard, pool_guard=None):
    repeated = remote_probe(target, key, config, revision, expected_installed, guard, pool_guard)
    require(proof is not None and repeated == proof, 'PROOF_CHANGED')
    return repeated
