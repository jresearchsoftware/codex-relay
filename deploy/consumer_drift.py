"""Restore only consumer bytes authenticated as the original admission context.

The owner installer holds the existing host/pool mutex. This bounded target
operation holds the existing Writer mutex continuously; the installed gate and
all attempt/receipt records remain owned by the actual installed Node graph.
"""
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import types

from clean_reinstall import namespace_paths, prove_consumer_resources, _recovery_identity
if 'publish_git_consumer' not in sys.modules:
    _publication_spec = importlib.util.spec_from_file_location('publish_git_consumer',
        Path(__file__).parent / 'ansible/scripts/publish_git_consumer.py')
    _publication_module = importlib.util.module_from_spec(_publication_spec)
    sys.modules['publish_git_consumer'] = _publication_module
    _publication_spec.loader.exec_module(_publication_module)
from publish_git_consumer import _protected, _read, _stamp


def require(condition, code):
    if not condition:
        raise ValueError('CONSUMER_DRIFT_' + code)


def install_interrupt_handlers():
    # A terminated target helper must unwind its Writer lock and reap a private
    # view child; default SIGTERM exit would skip Python finally blocks.
    def interrupted(_number, _frame):
        raise RuntimeError('CONSUMER_DRIFT_INTERRUPTED')
    for number in [signal.SIGTERM, signal.SIGHUP, signal.SIGINT]:
        signal.signal(number, interrupted)


def _publish(consumer, raw, operation_id, owner_uid):
    temporary = consumer.with_name('.consumer-drift-' + operation_id + '.restoring.json')
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(descriptor, 'wb') as output:
            os.fchown(output.fileno(), owner_uid, 0 if owner_uid == 0 else os.getgid())
            output.write(raw); output.flush()
            os.fchmod(output.fileno(), 0o644)
            os.fsync(output.fileno())
        os.replace(temporary, consumer)
        directory = os.open(consumer.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary.exists():
            temporary.unlink()


def _render_original(snapshot, source):
    """Use the original owning template/compiler, never copy its values as desired."""
    program = ('import json,sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);'
        'from managed_pool_transport import projected_consumer;'
        'print(json.dumps(projected_consumer(json.load(sys.stdin),Path(sys.argv[1]).parent)))')
    process = subprocess.Popen(['/usr/bin/python3', '-I', '-c', program, str(source / 'deploy')],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True,
        env={'PATH': '/usr/local/bin:/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8', 'HOME': '/root',
             'PYTHONDONTWRITEBYTECODE': '1'})
    try:
        output, _ = process.communicate(input=json.dumps(snapshot).encode(), timeout=90)
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)
    if process.returncode or len(output) > 131072:
        return None
    return json.loads(output)


def _original_contexts(config_root, release, manifest, options):
    # Existing source-owned backups are operational proof candidates only.
    # Every candidate must still match the authentic gate digest before use.
    names = []
    for path in config_root.iterdir():
        if re.fullmatch(r'consumer-(?:drift-)?before-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\.json', path.name):
            names.append(path)
    for path in sorted(names)[:32]:
        try:
            if stat.S_IMODE(path.lstat().st_mode) == 0o600:
                yield _read(path, options)
        except (OSError, ValueError):
            continue
    try:
        snapshot_path = release / 'deployment-config.json'
        raw = _read(snapshot_path, options)
        if (stat.S_IMODE(snapshot_path.lstat().st_mode) != 0o600
                or hashlib.sha256(raw).hexdigest() != manifest.get('deploymentConfigSha256')):
            return
        snapshot = json.loads(raw)
        if isinstance(snapshot.get('consumer'), dict):
            yield json.dumps(snapshot['consumer'], ensure_ascii=False, separators=(',', ':')).encode()
        source = release / 'reviewed-source'
        for relative in ['deploy/managed_pool_transport.py', 'deploy/managed_pool.py',
                         'deploy/ansible_transport.py', 'deploy/config.py', 'deploy/ansible/ansible.cfg',
                         'deploy/ansible/roles/relay_controller/templates/consumer.json.j2']:
            _protected(source / relative, **options)
        projected = _render_original(snapshot, source)
        if projected is not None:
            yield json.dumps(projected, ensure_ascii=False, separators=(',', ':')).encode()
        require(_read(snapshot_path, options) == raw, 'HISTORICAL_CONTEXT_CHANGED')
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        return


PRIVATE_VIEW = r'''import hashlib,json,os,subprocess,sys
def fail(code):
    print(json.dumps({'code':code}),file=sys.stderr);sys.exit(40)
parent,context,consumer,digest,node,cli,*arguments=sys.argv[1:]
if os.geteuid()!=0 or os.readlink('/proc/self/ns/mnt')==parent:
    fail('PRIVATE_MOUNT_NAMESPACE_UNAVAILABLE')
mounted=subprocess.run(['/usr/bin/mount','--bind',context,consumer],
    stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
if mounted.returncode:fail('PRIVATE_MOUNT_VIEW_UNAVAILABLE')
a,b=os.stat(context),os.stat(consumer)
if (a.st_dev,a.st_ino)!=(b.st_dev,b.st_ino) or hashlib.sha256(open(consumer,'rb').read()).hexdigest()!=digest:
    fail('PRIVATE_MOUNT_VIEW_UNPROVEN')
os.execve(node,[node,cli,*arguments],os.environ)
'''


def _execute(argv, env):
    process = subprocess.Popen(argv, env=env, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    try:
        try:
            output, errors = process.communicate(timeout=60)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)
            raise ValueError('CONSUMER_DRIFT_INSTALLED_CONTEXT_TIMED_OUT') from None
        if process.returncode:
            code = 'INSTALLED_CONTEXT_UNPROVEN'
            if argv[0] == '/usr/bin/unshare':
                try:
                    observed = json.loads(errors)
                except (ValueError, TypeError):
                    observed = {}
                code = (observed.get('code') if observed.get('code') in [
                    'PRIVATE_MOUNT_NAMESPACE_UNAVAILABLE', 'PRIVATE_MOUNT_VIEW_UNAVAILABLE',
                    'PRIVATE_MOUNT_VIEW_UNPROVEN'] else
                    'PRIVATE_MOUNT_NAMESPACE_UNAVAILABLE' if errors.startswith(b'unshare:')
                    else 'INSTALLED_CONTEXT_UNPROVEN')
            require(False, code)
        require(len(output) <= 131072, 'INSTALLED_CONTEXT_UNPROVEN')
        value = json.loads(output)
        require(isinstance(value, dict), 'INSTALLED_CONTEXT_UNPROVEN')
        return value
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)


def restore(config, desired, target_revision, operation_id, *, root=Path('/'), owner_uid=0,
            execute=_execute, node='/usr/bin/node', namespace_execute=None):
    """No caller-selected filesystem paths or gate digest are accepted.

    The root/UID/executor seams are fixture-only Python arguments, never CLI or
    worker capabilities. Desired bytes originate in the frozen Git projection.
    """
    require(os.geteuid() == owner_uid, 'ROOT_REQUIRED')
    require(re.fullmatch('[0-9a-f]{40}', target_revision or '')
            and re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', operation_id or ''),
            'OPERATION_BINDING_INVALID')
    root = Path(root)
    paths = namespace_paths(config, root)
    options = {'owner_uid': owner_uid, 'boundary': root}
    current = paths['install'] / 'current'
    _protected(paths['install'], directory=True, **options)
    link = current.lstat()
    require(stat.S_ISLNK(link.st_mode) and link.st_uid == owner_uid, 'INSTALLED_SOURCE_UNPROVEN')
    release = current.resolve(strict=True)
    require(release.parent == paths['install'] / 'releases'
            and re.fullmatch('[0-9a-f]{40}', release.name), 'INSTALLED_SOURCE_UNPROVEN')
    manifest = _recovery_identity(release, release.name, root, owner_uid, os.getgid())
    source = release / 'reviewed-source'
    consumer = paths['config'] / 'consumer.json'
    _protected(paths['config'], directory=True, **options)
    cli, validator = source / 'controller/src/admission-cli.mjs', source / 'consumer/consumer-config.mjs'
    for path in [cli, validator]:
        _protected(path, **options)
    claims = Path(config['consumer']['paths']['claimRoot'])
    require(claims.is_relative_to(root), 'WRITER_BOUNDARY_UNPROVEN')
    _protected(claims, directory=True, **options)
    lock = claims / 'publication-v2.lock'
    before_lock = _protected(lock, **options)
    require(stat.S_IMODE(before_lock.st_mode) == 0o600, 'WRITER_LOCK_UNSAFE')
    lock_fd = os.open(lock, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
    staged = None
    try:
        require(_stamp(os.fstat(lock_fd)) == _stamp(before_lock), 'WRITER_LOCK_CHANGED')
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('CONSUMER_DRIFT_WRITER_BUSY') from None
        gate_name = ('admission-pool-v1.json' if (paths['config'] / 'serial-pool-compat-v1.json').exists()
                     else 'admission-v1.json')
        gate_path = claims / gate_name
        gate_bytes = _read(gate_path, options, limit=4096)
        require(stat.S_IMODE(gate_path.stat().st_mode) == 0o600, 'GATE_UNSAFE')
        gate = json.loads(gate_bytes)
        require(isinstance(gate, dict) and gate.keys() == {'version', 'consumerDigest', 'phase',
                'operationId', 'target', 'previousActive', 'verifiedRevision'}
                and type(gate['version']) is int and gate['version'] == 1, 'GATE_UNPROVEN')
        gate_digest = gate.get('consumerDigest')
        require(isinstance(gate_digest, str) and re.fullmatch('[0-9a-f]{64}', gate_digest), 'GATE_UNPROVEN')
        env = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C',
               'RELAY_CONSUMER_CONFIG': str(consumer),
               'RELAY_REPOSITORY': config['environment'].get('repository', config['consumer'].get('repository'))}
        def digest(path):
            program = ('import{pathToFileURL}from"node:url";const m=await import(pathToFileURL(process.argv[1]));'
                       'console.log(JSON.stringify({digest:m.consumerDigest(m.loadConsumer(process.argv[2]))}));')
            value = execute([node, '--input-type=module', '-e', program, str(validator), str(path)], env).get('digest')
            require(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value), 'DIGEST_UNPROVEN')
            return value
        actual_bytes = _read(consumer, options)
        try:
            current_digest = digest(consumer)
        except (ValueError, KeyError, TypeError):
            current_digest = None
        if current_digest == gate_digest:
            return {'status': 'unchanged', 'operationId': None}
        # Only the known original context may be restored. A different future
        # policy plus unrecognized current drift cannot invent that context.
        try:
            current_consumer = json.loads(actual_bytes)
        except ValueError:
            current_consumer = None
        if current_consumer is not None:
            prove_consumer_resources(config, current_consumer, root=root, owner_uid=owner_uid)
        require(stat.S_IMODE(consumer.stat().st_mode) == 0o644, 'CONSUMER_UNSAFE')
        require(gate.get('phase') == 'open' and gate.get('operationId') is None
                and gate.get('target') is None and gate.get('previousActive') is None
                and gate.get('verifiedRevision') is None, 'ORIGINAL_CONTEXT_UNPROVEN')
        require(not any(path.exists() or path.is_symlink() for path in [paths['operation'], paths['journal']]),
                'RETAINED_OPERATION_REQUIRES_DIAGNOSIS')
        staged = paths['config'] / ('.consumer-drift-' + operation_id + '.context.json')
        require(not staged.exists() and not staged.is_symlink(), 'STAGING_ALREADY_EXISTS')
        descriptor = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        os.close(descriptor)
        requested = (json.dumps(desired, ensure_ascii=False, separators=(',', ':')) + '\n').encode()
        def candidates():
            yield requested
            yield from _original_contexts(paths['config'], release, manifest, options)
        matched = False
        for raw in candidates():
            descriptor = os.open(staged, os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW)
            with os.fdopen(descriptor, 'wb') as output:
                output.write(raw); output.flush(); os.fsync(output.fileno())
            try:
                matched = digest(staged) == gate_digest
            except (ValueError, KeyError, TypeError):
                matched = False
            if matched:
                break
        require(matched, 'ORIGINAL_CONTEXT_UNPROVEN')
        # Authentication by the installed digest precedes structural proof for
        # malformed live JSON; protected actual unit identities remain required.
        prove_consumer_resources(config, json.loads(raw), root=root, owner_uid=owner_uid)
        staged.chmod(0o644)  # The installed serial verifier requires canonical 0644 metadata.
        try:
            for tool in ['/usr/bin/unshare', '/usr/bin/mount']:
                metadata = _protected(Path(tool), **{'owner_uid': 0, 'boundary': Path('/')})
                require(metadata.st_mode & 0o111, 'PRIVATE_MOUNT_NAMESPACE_UNAVAILABLE')
        except FileNotFoundError:
            raise ValueError('CONSUMER_DRIFT_PRIVATE_MOUNT_NAMESPACE_UNAVAILABLE') from None
        parent_namespace = os.readlink('/proc/self/ns/mnt')
        def installed(*arguments):
            require(_read(consumer, options) == actual_bytes and _read(staged, options) == raw
                    and _stamp(lock.lstat()) == _stamp(before_lock), 'LIVE_CONTEXT_CHANGED')
            command = ['/usr/bin/unshare', '--mount', '--propagation', 'private', '--',
                '/usr/bin/python3', '-I', '-c', PRIVATE_VIEW, parent_namespace, str(staged), str(consumer),
                hashlib.sha256(raw).hexdigest(), node, str(cli), *arguments]
            return (namespace_execute or execute)(command, env)
        status = installed('status')
        require(status.get('phase') == 'open' and status.get('consumerDigest') == gate_digest
                and status.get('operationId') is None and status.get('target') is None
                and status.get('unknown') == [] and isinstance(status.get('active'), list),
                'ORIGINAL_CONTEXT_UNPROVEN')
        reserved = installed('quiesce', '--operation', operation_id, '--target', target_revision)
        require(reserved.get('phase') == 'quiesced' and reserved.get('operationId') == operation_id
                and reserved.get('target') == target_revision and reserved.get('consumerDigest') == gate_digest,
                'QUIESCE_UNPROVEN')
        actual_gate = json.loads(_read(gate_path, options, limit=4096))
        require(all(actual_gate.get(key) == reserved.get(key) for key in [
            'consumerDigest', 'phase', 'operationId', 'target']), 'QUIESCE_UNPROVEN')
        require(_read(consumer, options) == actual_bytes and _stamp(current.lstat()) == _stamp(link)
                and current.resolve(strict=True) == release and _stamp(lock.lstat()) == _stamp(before_lock),
                'LIVE_CONTEXT_CHANGED')
        backup = paths['config'] / ('consumer-drift-before-' + operation_id + '.json')
        require(not backup.exists() and not backup.is_symlink(), 'BACKUP_ALREADY_EXISTS')
        descriptor = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, 'wb') as output:
            output.write(actual_bytes); output.flush(); os.fsync(output.fileno())
        _publish(consumer, raw, operation_id, owner_uid)
        require(digest(consumer) == gate_digest, 'RESTORATION_UNPROVEN')
        return {'status': 'restored', 'operationId': operation_id}
    finally:
        if staged is not None and staged.exists():
            staged.unlink()
        os.close(lock_fd)


def prepare(target, key, config, revision, operation_id, guard, pool_guard=None):
    require(guard is not None and guard.poll() is None
            and (pool_guard is None or pool_guard.poll() is None), 'HOST_MUTEX_LOST')
    from managed_pool_transport import projected_consumer
    desired = projected_consumer(config)
    sources = {'publish_git_consumer': (Path(__file__).parent / 'ansible/scripts/publish_git_consumer.py').read_text(),
               'clean_reinstall': (Path(__file__).parent / 'clean_reinstall.py').read_text(),
               'consumer_drift': Path(__file__).read_text()}
    bootstrap = ('import json,sys,types\nraw=sys.stdin.buffer.read(524289)\n'
        'if len(raw)>524288:raise SystemExit(1)\n'
        'p=json.loads(raw)\n'
        'for name in ["publish_git_consumer","clean_reinstall","consumer_drift"]:\n'
        ' m=types.ModuleType(name);m.__file__="/owner-source/"+name+".py";sys.modules[name]=m;'
        'exec(compile(p["sources"][name],m.__file__,"exec"),m.__dict__)\n'
        'sys.modules["consumer_drift"].install_interrupt_handlers()\n'
        'try:\n print(json.dumps(sys.modules["consumer_drift"].restore(p["config"],p["desired"],p["revision"],p["operation"])))\n'
        'except Exception as e:\n'
        ' import re\n code=str(e).split(";")[0]\n'
        ' print(json.dumps({"error_code":code if re.fullmatch(r"(?:CONSUMER_DRIFT_|CONSUMER_PUBLICATION_|REINSTALL_)[A-Z_]{1,100}",code) else "CONSUMER_DRIFT_UNPROVEN"}));sys.exit(1)\n')
    from ansible_transport import TargetProcess
    process = TargetProcess(target, key, ['/usr/bin/python3', '-I', '-c', bootstrap])
    payload = json.dumps({'sources': sources, 'config': config, 'desired': desired,
                          'revision': revision, 'operation': operation_id})
    try:
        while True:
            require(guard.poll() is None and (pool_guard is None or pool_guard.poll() is None), 'HOST_MUTEX_LOST')
            try:
                output, _ = process.communicate(input=payload, timeout=1)
                break
            except subprocess.TimeoutExpired:
                payload = None
        result = json.loads(output)
        require(guard.poll() is None and (pool_guard is None or pool_guard.poll() is None), 'HOST_MUTEX_LOST')
        if process.returncode:
            code = result.get('error_code', 'CONSUMER_DRIFT_UNPROVEN')
            require(re.fullmatch(r'(?:CONSUMER_DRIFT_|CONSUMER_PUBLICATION_|REINSTALL_)[A-Z_]{1,100}', code), 'UNPROVEN')
            raise ValueError(code)
        require(result.keys() == {'status', 'operationId'} and result['status'] in ['unchanged', 'restored']
                and result['operationId'] == (operation_id if result['status'] == 'restored' else None), 'RESULT_UNPROVEN')
        return result
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait()
