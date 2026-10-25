"""Publish one protected consumer change while holding the existing Writer lock."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time
import uuid


class ConsumerPublicationError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise ConsumerPublicationError(code)


def _stamp(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_uid,
            info.st_gid, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _protected(path, *, directory=False, owner_uid=0, boundary=Path('/')):
    path, boundary = Path(path), Path(boundary)
    require(path.is_absolute() and path == Path(os.path.normpath(path)) and path.is_relative_to(boundary),
            'CONSUMER_PUBLICATION_PATH_INVALID')
    at = path
    target_info = None
    while True:
        info = at.lstat()
        require(not stat.S_ISLNK(info.st_mode) and info.st_uid == owner_uid and not info.st_mode & 0o022,
                'CONSUMER_PUBLICATION_PATH_UNSAFE')
        if at == path:
            target_info = info
            require(stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
                    'CONSUMER_PUBLICATION_PATH_UNSAFE')
        else:
            require(stat.S_ISDIR(info.st_mode), 'CONSUMER_PUBLICATION_PATH_UNSAFE')
        if at == boundary:
            return target_info
        require(at.parent != at, 'CONSUMER_PUBLICATION_PATH_INVALID')
        at = at.parent


def _read(path, options, limit=128 * 1024):
    before = _protected(path, **options)
    require(before.st_size <= limit, 'CONSUMER_PUBLICATION_INPUT_TOO_LARGE')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        require(_stamp(os.fstat(fd)) == _stamp(before), 'CONSUMER_PUBLICATION_INPUT_CHANGED')
        raw = os.read(fd, limit + 1)
        require(len(raw) == before.st_size and _stamp(os.fstat(fd)) == _stamp(before)
                and _stamp(Path(path).lstat()) == _stamp(before), 'CONSUMER_PUBLICATION_INPUT_CHANGED')
        return raw
    finally:
        os.close(fd)


def _atomic(path, raw, mode):
    path = Path(path)
    temporary = path.with_name('.' + path.name + '.tmp-' + str(uuid.uuid4()))
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(raw)
            output.flush()
            os.fchmod(output.fileno(), mode)
            os.fsync(output.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary.exists():
            temporary.unlink()


def _execute(argv, env):
    try:
        result = subprocess.run(argv, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, timeout=60, check=False)
        require(result.returncode == 0 and len(result.stdout) <= 4096, 'CONSUMER_PUBLICATION_CONTROLLER_FAILED')
        value = json.loads(result.stdout)
        require(isinstance(value, dict), 'CONSUMER_PUBLICATION_CONTROLLER_FAILED')
        return value
    except (OSError, subprocess.SubprocessError, ValueError):
        raise ConsumerPublicationError('CONSUMER_PUBLICATION_CONTROLLER_FAILED') from None


def publish(source, config_root, desired, claim_root, repository, operation, revision, *,
            owner_uid=0, boundary=Path('/'), execute=_execute):
    """All path arguments originate in the trusted installer, never runner input.

    owner_uid/boundary/execute are fixture seams, unavailable on the command line.
    """
    require(os.geteuid() == owner_uid, 'CONSUMER_PUBLICATION_ROOT_REQUIRED')
    require(re.fullmatch(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', operation or '') is not None
            and re.fullmatch(r'[a-f0-9]{40}', revision or '') is not None
            and re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository or '') is not None,
            'CONSUMER_PUBLICATION_BINDING_INVALID')
    source, config_root, desired, claim_root = map(Path, (source, config_root, desired, claim_root))
    options = {'owner_uid': owner_uid, 'boundary': Path(boundary)}
    for directory in (source, config_root, claim_root):
        _protected(directory, directory=True, **options)
    require(desired.parent == config_root and desired.name == '.consumer-' + operation + '.desired.json',
            'CONSUMER_PUBLICATION_DESIRED_PATH_INVALID')
    consumer = config_root / 'consumer.json'
    cli = source / 'controller/src/admission-cli.mjs'
    validator = source / 'consumer/consumer-config.mjs'
    for path in (cli, validator):
        _protected(path, **options)
    require(json.loads(_read(source / '.relay-source.json', options)).get('revision') == revision,
            'CONSUMER_PUBLICATION_SOURCE_MISMATCH')
    desired_bytes = _read(desired, options)
    lock_path = claim_root / 'publication-v2.lock'
    lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        _protected(lock_path, **options)
        require(_stamp(os.fstat(lock_fd)) == _stamp(lock_path.lstat()), 'CONSUMER_PUBLICATION_LOCK_CHANGED')
        deadline = time.monotonic() + 180
        while True:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                require(time.monotonic() < deadline, 'CONSUMER_PUBLICATION_LOCK_TIMEOUT')
                time.sleep(0.1)
        old_bytes = _read(consumer, options)
        backup = config_root / ('consumer-before-' + operation + '.json')
        env = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C',
               'RELAY_CONSUMER_CONFIG': str(consumer), 'RELAY_REPOSITORY': repository}

        def digest(path):
            # The product's actual validator owns normalization and digest rules.
            program = "import {pathToFileURL} from 'node:url'; const m=await import(pathToFileURL(process.argv[1])); console.log(JSON.stringify({digest:m.consumerDigest(m.loadConsumer(process.argv[2]))}));"
            value = execute(['/usr/bin/node', '--input-type=module', '-e', program, str(validator), str(path)], env).get('digest')
            require(isinstance(value, str) and re.fullmatch(r'[a-f0-9]{64}', value) is not None,
                    'CONSUMER_PUBLICATION_DIGEST_INVALID')
            return value

        desired_digest = digest(desired)
        require(_read(desired, options) == desired_bytes, 'CONSUMER_PUBLICATION_INPUT_CHANGED')
        current_digest = digest(consumer)
        receipt_path = config_root / 'serial-pool-compat-v1.json'
        pending_transition = False
        if backup.exists():
            _read(backup, options)
            backup_digest = digest(backup)
            if backup_digest != current_digest:
                gate_name = 'admission-pool-v1.json' if receipt_path.exists() else 'admission-v1.json'
                gate = json.loads(_read(claim_root / gate_name, options, limit=4096))
                require(gate.get('operationId') == operation and gate.get('target') == revision
                        and gate.get('phase') in ('drained', 'applying'),
                        'CONSUMER_PUBLICATION_BACKUP_OPERATION_MISMATCH')
                require(gate.get('consumerDigest') in (backup_digest, current_digest),
                        'CONSUMER_PUBLICATION_BACKUP_CHANGED')
                pending_transition = gate['consumerDigest'] == backup_digest
        if desired_digest == current_digest and not pending_transition:
            # Code-only upgrades retain the original consumer binding, including
            # outstanding manual handoffs. They need no new config-change drain.
            snapshot = config_root / 'serial-pool-target-consumer-v1.json'
            if receipt_path.exists() and snapshot.exists():
                receipt = json.loads(_read(receipt_path, options))
                _read(snapshot, options)
                require(digest(snapshot) == receipt.get('target', {}).get('consumerDigest'),
                        'CONSUMER_PUBLICATION_SERIAL_TARGET_CHANGED')
            return {'status': 'UNCHANGED', 'operationId': operation, 'target': revision, 'consumerDigest': current_digest}

        if old_bytes == desired_bytes and backup.exists():
            _read(backup, options)
            previous_digest = digest(backup)
        else:
            checked = execute(['/usr/bin/node', str(cli), 'consumer-transition-check', '--operation', operation,
                               '--revision', revision], env)
            previous_digest = checked.get('previousDigest')
            require(checked.get('operationId') == operation and checked.get('target') == revision
                    and isinstance(previous_digest, str) and re.fullmatch(r'[a-f0-9]{64}', previous_digest) is not None,
                    'CONSUMER_PUBLICATION_PRECHECK_INVALID')
            if old_bytes == desired_bytes:
                return {'status': 'UNCHANGED', 'operationId': operation, 'target': revision, 'consumerDigest': previous_digest}
            if backup.exists():
                require(_read(backup, options) == old_bytes, 'CONSUMER_PUBLICATION_BACKUP_CHANGED')
            else:
                _atomic(backup, old_bytes, 0o600)

        if receipt_path.exists():
            receipt = json.loads(_read(receipt_path, options))
            target_digest = receipt.get('target', {}).get('consumerDigest')
            require(isinstance(target_digest, str) and re.fullmatch(r'[a-f0-9]{64}', target_digest) is not None,
                    'CONSUMER_PUBLICATION_SERIAL_RECEIPT_INVALID')
            snapshot = config_root / 'serial-pool-target-consumer-v1.json'
            if snapshot.exists():
                _read(snapshot, options)
                require(digest(snapshot) == target_digest, 'CONSUMER_PUBLICATION_SERIAL_TARGET_CHANGED')
            else:
                require(previous_digest == target_digest, 'CONSUMER_PUBLICATION_SERIAL_TARGET_UNAVAILABLE')
                _atomic(snapshot, _read(backup, options), 0o644)
                require(digest(snapshot) == target_digest, 'CONSUMER_PUBLICATION_SERIAL_TARGET_CHANGED')
        # The same lock excludes both manual and automatic admissions until the
        # new gate is durable. Never roll back a config after an uncertain effect.
        if old_bytes != desired_bytes:
            require(_read(consumer, options) == old_bytes, 'CONSUMER_PUBLICATION_INPUT_CHANGED')
            _atomic(consumer, desired_bytes, 0o644)
        try:
            result = execute(['/usr/bin/node', str(cli), 'consumer-transition', '--operation', operation,
                              '--previous-digest', previous_digest, '--revision', revision], env)
            require(result.get('operationId') == operation and result.get('target') == revision
                    and result.get('phase') in ('drained', 'applying')
                    and result.get('consumerDigest') == desired_digest
                    and digest(consumer) == desired_digest, 'CONSUMER_PUBLICATION_TRANSITION_UNPROVEN')
        except ConsumerPublicationError:
            raise ConsumerPublicationError('CONSUMER_PUBLICATION_TRANSITION_REQUIRES_RECOVERY') from None
        return {'status': 'PUBLISHED', 'operationId': operation, 'target': revision, 'consumerDigest': result['consumerDigest']}
    finally:
        os.close(lock_fd)


def main():
    parser = argparse.ArgumentParser()
    for name in ('source', 'config-root', 'desired', 'claim-root', 'repository', 'operation', 'revision'):
        parser.add_argument('--' + name, required=True)
    args = vars(parser.parse_args())
    try:
        print(json.dumps(publish(**args)))
    except (ConsumerPublicationError, OSError, ValueError) as error:
        code = str(error) if isinstance(error, ConsumerPublicationError) else 'CONSUMER_PUBLICATION_FAILED'
        print(json.dumps({'error_code': code}))
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
